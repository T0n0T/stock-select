from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from bisect import bisect_left
from math import floor
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    import pandas as pd
    from .rule_exit import ExitMarket, ExitPolicyConfig

from .policy import HoldingAction, TopNHoldPolicy
from .entry_policy import EntryPolicy
from .score_gate import ScoreEntryGate
from .signal_bundle import SignalBundle, normalize_date


@dataclass(frozen=True)
class BacktestConfig:
    top_n: int = 3
    holding_days: int = 3
    capital_allocation: float = 0.99
    initial_cash: float = 1_000_000.0
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    min_commission: float = 5.0
    lot_size: int = 100
    t_plus_one: bool = True
    timezone: str = "Asia/Shanghai"
    defer_suspended_exit: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.capital_allocation <= 1:
            raise ValueError("capital_allocation must be greater than zero and at most one")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be greater than zero")


def _market_frame(frame: "pd.DataFrame", *, source: Path) -> "pd.DataFrame":
    import pandas as pd

    renamed = {str(column).lower(): column for column in frame.columns}
    symbol_col = renamed.get("symbol") or renamed.get("code")
    date_col = renamed.get("datetime") or renamed.get("timestamp") or renamed.get("date")
    if symbol_col is None or date_col is None:
        raise ValueError(f"{source}: market data requires symbol/code and date/datetime columns")
    result = frame.rename(columns={symbol_col: "symbol", date_col: "datetime"}).copy()
    result["symbol"] = result["symbol"].astype(str)
    result["datetime"] = pd.to_datetime(result["datetime"])
    for column in ("open", "high", "low", "close", "volume"):
        if column not in result.columns:
            raise ValueError(f"{source}: market data requires {column!r}")
        result[column] = pd.to_numeric(result[column], errors="raise")
    return result[["symbol", "datetime", "open", "high", "low", "close", "volume"]]


def load_market_data(path: Path) -> dict[str, "pd.DataFrame"]:
    import pandas as pd

    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir():
        files = sorted([*path.glob("*.csv"), *path.glob("*.parquet")])
        if not files:
            raise ValueError(f"{path}: no CSV or Parquet market files found")
        frames = [load_market_data(child) for child in files]
        merged: dict[str, list[pd.DataFrame]] = {}
        for item in frames:
            for symbol, frame in item.items():
                merged.setdefault(symbol, []).append(frame)
        return {symbol: pd.concat(parts, ignore_index=True).sort_values("datetime") for symbol, parts in merged.items()}
    if path.suffix.lower() == ".csv":
        columns = pd.read_csv(path, nrows=0).columns
        code_columns = {column: str for column in columns if column.lower() in {"symbol", "code"}}
        frame = pd.read_csv(path, dtype=code_columns)
    else:
        frame = pd.read_parquet(path)
    normalized = _market_frame(frame, source=path)
    return {symbol: part.drop(columns=["symbol"]).reset_index(drop=True) for symbol, part in normalized.groupby("symbol", sort=True)}


def _prepare_run(
    market_data: Mapping[str, "pd.DataFrame"],
    signals: SignalBundle,
    config: BacktestConfig,
    entry_policy: EntryPolicy | None = None,
    environments: Mapping[str, str] | None = None,
) -> tuple[dict[str, "pd.DataFrame"], dict[str, HoldingAction]]:
    import pandas as pd

    policy = TopNHoldPolicy(config.top_n, config.holding_days)
    entry_policy = entry_policy or EntryPolicy()
    signal_dates = [day for day in signals.dates if signals.rows_for_date(day)]
    if not signal_dates:
        raise ValueError("no ranked signals to backtest")

    daily_data: dict[str, pd.DataFrame] = {}
    symbol_days: dict[str, set[str]] = {}
    for symbol, frame in market_data.items():
        times = pd.DatetimeIndex(pd.to_datetime(frame["datetime"]))
        if times.tz is not None:
            times = times.tz_convert(config.timezone).tz_localize(None)
        days = times.normalize()
        if days.hasnans or days.has_duplicates:
            raise ValueError(f"{symbol}: market data requires one bar per trading day with a valid date")
        daily_data[symbol] = frame.assign(datetime=days)
        symbol_days[symbol] = set(days.strftime("%Y-%m-%d"))

    sessions = sorted(set().union(*symbol_days.values()))
    session_index = {day: index for index, day in enumerate(sessions)}
    exit_offset = config.holding_days + 1
    for day in signal_dates:
        if day not in session_index:
            raise ValueError(f"{day}: no market data on signal day")
        if session_index[day] + exit_offset >= len(sessions):
            raise ValueError(f"{day}: market data must include at least {exit_offset} later trading sessions")

    start = session_index[signal_dates[0]]
    end = session_index[signal_dates[-1]] + exit_offset
    actions = {}
    index = start
    while index <= end:
        day = sessions[index]
        rows = signals.rows_for_date(day)
        decision = entry_policy.decide(
            day, (environments or {}).get(day),
            default_fraction=config.capital_allocation / config.holding_days,
        ) if rows else None
        if decision is not None and not decision.allow_new_positions:
            rows = ()
        action = policy.on_trading_day(day, [(row.code, row.model_score, row.model_rank) for row in rows])
        action = replace(action, entry_decision=decision)
        actions[day] = action
        for symbol in action.enter:
            available = symbol_days.get(symbol, set())
            required_days = [day, sessions[index + 1]]
            scheduled_exit = sessions[index + exit_offset]
            if config.defer_suspended_exit:
                tradable = sorted(available)
                next_bar = bisect_left(tradable, scheduled_exit)
                if next_bar == len(tradable):
                    raise ValueError(f"{symbol}: no tradable exit data on or after {scheduled_exit} for signal {day}")
                end = max(end, session_index[tradable[next_bar]])
            else:
                required_days.append(scheduled_exit)
            for required_day in required_days:
                if required_day not in available:
                    raise ValueError(f"{symbol}: missing daily market data on {required_day} for signal {day}")
        index += 1

    first, last = pd.Timestamp(sessions[start]), pd.Timestamp(sessions[end])
    return {
        symbol: window
        for symbol, frame in daily_data.items()
        if not (window := frame[frame["datetime"].between(first, last)]).empty
    }, actions


def _make_strategy(
    aq: Any, actions: Mapping[str, HoldingAction], config: BacktestConfig,
    tradable_next: Mapping[str, set[str]] | None = None,
    entry_policy: EntryPolicy | None = None,
) -> type:
    class RankedTopNStrategy(aq.Strategy):
        def on_start(self) -> None:
            self.set_history_depth(1)
            self.action_history: list[tuple[str, HoldingAction]] = []
            self.batch_orders: dict[str, list[tuple[str, str]]] = {}
            self.pending_exits: list[tuple[str, str, str]] = []
            self.daily_budgets: list[dict[str, Any]] = []
            self.strategy_config = {
                "backtest": asdict(config),
                "entry_policy": (entry_policy or EntryPolicy()).to_dict(),
            }

        def on_cross_section(self, trading_date: Any, timestamp: int) -> None:
            del timestamp
            day = normalize_date(trading_date)
            action = actions[day]
            self.action_history.append((day, action))
            for signal_date in action.expired_signal_dates:
                for symbol, order_id in self.batch_orders.pop(signal_date):
                    self.pending_exits.append((symbol, order_id, signal_date))
            remaining = []
            expected_sale_cash = 0.0
            for symbol, order_id, signal_date in self.pending_exits:
                # NextOpen 在无 K 线日会拒单；这里只用可交易状态模拟到期卖单
                # 等待复牌，不读取未来价格，也不改变选股、数量或资金到账时点。
                if config.defer_suspended_exit and symbol not in (tradable_next or {}).get(day, set()):
                    remaining.append((symbol, order_id, signal_date))
                    continue
                order = self.get_order(order_id)
                if order.filled_quantity:
                    self.sell(symbol, quantity=order.filled_quantity, tag=signal_date)
                    closes = self.get_history(1, symbol=symbol, field="close")
                    if len(closes):
                        expected_sale_cash += order.filled_quantity * closes[-1]
            self.pending_exits = remaining

            if action.enter or action.entry_decision is not None:
                account = self.get_account()
                fraction = (action.entry_decision.daily_equity_fraction if action.entry_decision is not None
                            else config.capital_allocation / config.holding_days)
                target_budget = account["equity"] * fraction if action.enter else 0.0
                daily_budget = min(
                    target_budget,
                    max(0.0, account["cash"] + expected_sale_cash) * config.capital_allocation,
                )
                budget_record = {"date": day, "equity": account["equity"], "cash": account["cash"],
                                 "target_budget": target_budget, "daily_budget": daily_budget,
                                 "submitted_notional_at_close": 0.0}
                self.daily_budgets.append(budget_record)
            if action.enter:
                budget = daily_budget / len(action.enter)
                purchases = []
                for symbol in action.enter:
                    closes = self.get_history(1, symbol=symbol, field="close")
                    if len(closes) == 0 or not closes[-1] > 0:
                        raise ValueError(f"{day}: no valid close price for selected symbol {symbol}")
                    quantity = floor(budget / closes[-1] / config.lot_size) * config.lot_size
                    if quantity:
                        receipt = self.buy(symbol, quantity=quantity, tag=day)
                        purchases.extend((symbol, order_id) for order_id in receipt.order_ids)
                        budget_record["submitted_notional_at_close"] += quantity * closes[-1]
                self.batch_orders[day] = purchases

    return RankedTopNStrategy


def run_akquant_backtest(
    market_data: Mapping[str, "pd.DataFrame"],
    signals: SignalBundle,
    config: BacktestConfig | None = None,
    *,
    entry_policy: EntryPolicy | None = None,
    environments: Mapping[str, str] | None = None,
    exit_policy: "ExitPolicyConfig | None" = None,
    exit_market: "ExitMarket | None" = None,
    end_date: str | None = None,
    score_gate: ScoreEntryGate | None = None,
) -> Any:
    """Run a ranked signal bundle through AKQuant's public backtest API."""
    import akquant as aq

    resolved = config or BacktestConfig()
    if exit_policy is not None:
        from .rule_gateway import run_rule_backtest
        return run_rule_backtest(market_data, signals, resolved, exit_policy=exit_policy,
                                 exit_market=exit_market, entry_policy=entry_policy,
                                 environments=environments, end_date=end_date, score_gate=score_gate)
    if score_gate is not None:
        raise ValueError("score entry gate requires a shared exit policy")
    data, actions = _prepare_run(market_data, signals, resolved, entry_policy, environments)
    sessions = sorted(actions)
    next_day = dict(zip(sessions, sessions[1:]))
    available = {symbol: set(frame["datetime"].dt.strftime("%Y-%m-%d")) for symbol, frame in data.items()}
    tradable_next = {day: {symbol for symbol, days in available.items() if following in days}
                     for day, following in next_day.items()}
    strategy = _make_strategy(aq, actions, resolved, tradable_next, entry_policy)
    result = aq.run_backtest(
        data=data,
        strategy=strategy,
        symbols=sorted(data),
        initial_cash=resolved.initial_cash,
        commission_rate=resolved.commission_rate,
        stamp_tax_rate=resolved.stamp_tax_rate,
        transfer_fee_rate=resolved.transfer_fee_rate,
        min_commission=resolved.min_commission,
        lot_size=resolved.lot_size,
        t_plus_one=resolved.t_plus_one,
        timezone=resolved.timezone,
        fill_policy=aq.NextOpen(),
        show_progress=False,
    )
    _raise_on_rejected_orders(result)
    return result


def _raise_on_rejected_orders(result: Any, *, untradable_entry_order_ids: set[str] | None = None) -> None:
    """Fail fast when the engine could not execute a requested order."""
    orders = getattr(result, "orders_df", None)
    if orders is None or orders.empty or "status" not in orders.columns:
        return
    rejected = orders[orders["status"].astype(str).str.lower().isin({"rejected", "cancelled", "expired"})]
    if untradable_entry_order_ids and {"id", "reject_reason"}.issubset(rejected.columns):
        status = rejected["status"].astype(str).str.lower()
        expected = (rejected["id"].isin(untradable_entry_order_ids)
                    & (status.eq("cancelled") | (status.eq("rejected")
                       & rejected["reject_reason"].astype(str).str.startswith("Missing market data for symbol "))))
        rejected = rejected.loc[~expected]
    if rejected.empty:
        return
    details = rejected[[column for column in ("symbol", "side", "quantity", "status", "reject_reason") if column in rejected.columns]]
    raise RuntimeError(f"AKQuant failed to execute {len(rejected)} order(s): {details.to_dict(orient='records')}")
