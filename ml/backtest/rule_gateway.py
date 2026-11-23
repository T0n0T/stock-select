"""AKQuant 的逐批规则退出适配；买入 NextOpen，卖出 CurrentClose。"""
from __future__ import annotations

from dataclasses import asdict
from math import floor
from typing import Any, Mapping

from .entry_policy import EntryPolicy
from .policy import HoldingAction, TopNHoldPolicy
from .rule_exit import ExitMarket, ExitPolicyConfig, ExitState
from .signal_bundle import SignalBundle, normalize_date
from .score_gate import ScoreEntryGate, filter_score_signals


def run_rule_backtest(
    market_data: Mapping[str, Any], signals: SignalBundle, config: Any, *,
    exit_policy: ExitPolicyConfig, exit_market: ExitMarket | None = None,
    entry_policy: EntryPolicy | None = None, environments: Mapping[str, str] | None = None,
    end_date: str | None = None,
    score_gate: ScoreEntryGate | None = None,
) -> Any:
    import akquant as aq
    import pandas as pd
    from .akquant_gateway import _raise_on_rejected_orders

    if not config.t_plus_one:
        raise ValueError("rule exit strategy requires T+1")
    if not signals.dates:
        raise ValueError("no ranked signals to backtest")
    prepared = exit_market or ExitMarket(market_data, exit_policy)
    if prepared.config != exit_policy:
        raise ValueError("exit market must use the same exit policy")
    entry = entry_policy or EntryPolicy()
    if score_gate is not None:
        if score_gate.top_n != config.top_n:
            raise ValueError("score gate top_n must match backtest top_n")
        signals = filter_score_signals(signals, score_gate, environments or {})
    end = end_date or prepared.sessions[-1]
    first = signals.dates[0]
    if end not in prepared.indices or prepared.indices[end] <= prepared.indices[signals.dates[-1]]:
        raise ValueError("backtest end must include the next-open fill of the last signal")
    selector = TopNHoldPolicy(config.top_n, config.holding_days)
    selections = {}
    decisions = {}
    for day in signals.dates:
        decision = entry.decide(day, (environments or {}).get(day),
                                default_fraction=config.capital_allocation / config.holding_days)
        decisions[day] = decision
        selected = selector._select([(row.code, row.model_score, row.model_rank) for row in signals.rows_for_date(day)]) if decision.allow_new_positions else []
        selections[day] = tuple(code for code, _ in selected)
        for code, _ in selected:
            if not prepared.ready(code, day):
                raise ValueError(f"{day}: {code} lacks MA25 warmup or signal-day data")
            if code not in market_data:
                raise ValueError(f"{day}: {code} lacks execution market data")

    class RuleExitStrategy(aq.Strategy):
        def on_start(self) -> None:
            self.set_history_depth(1)
            self.active: list[dict[str, Any]] = []
            self.pending_entries: list[tuple[str, str, str]] = []
            self.action_history: list[tuple[str, HoldingAction]] = []
            self.daily_budgets: list[dict[str, Any]] = []
            self.exit_events: list[dict[str, Any]] = []
            self.unfilled_entries: list[dict[str, Any]] = []
            self.open_batches: list[dict[str, Any]] = []
            self.strategy_config = {"backtest": asdict(config), "entry_policy": entry.to_dict(),
                                    "exit_policy": asdict(exit_policy),
                                    "execution": {"buy": "next_open", "sell": "current_close", "t_plus_one": True},
                                    "end_date": end, "terminal_positions": "mark_to_market"}
            if score_gate is not None:
                self.strategy_config["score_entry_gate"] = score_gate.to_dict()

        def on_cross_section(self, trading_date: Any, timestamp: int) -> None:
            del timestamp
            day = normalize_date(trading_date)
            session = prepared.indices[day]
            pending = []
            for signal_day, code, order_id in self.pending_entries:
                order = self.get_order(order_id)
                if order is None or not order.filled_quantity:
                    entry_day = prepared.sessions[prepared.indices[signal_day]+1]
                    if day == entry_day and day not in prepared.bars[code]:
                        # 次日无法成交时撤销该批买单；保留原排名，不补选也不延至复牌买入。
                        if order is not None and "reject" not in str(order.status).lower():
                            self.cancel_order(order_id)
                        self.unfilled_entries.append({"signal_date": signal_day, "code": code,
                                                      "date": day, "order_id": order_id,
                                                      "reason": "untradable_next_open"})
                        continue
                    pending.append((signal_day, code, order_id))
                    continue
                entry_day = prepared.sessions[prepared.indices[signal_day]+1]
                state = ExitState(entry_day, prepared.indices[entry_day], float(order.average_filled_price))
                self.active.append({"signal_date": signal_day, "code": code,
                                    "quantity": float(order.filled_quantity), "state": state})
            self.pending_entries = pending
            before = self.get_account()
            expected_sales = 0.0
            remaining = []
            exited = []
            for batch in self.active:
                code, state = batch["code"], batch["state"]
                bar = prepared.bars[code].get(day)
                decision = state.observe(day, session, bar, exit_policy) if bar is not None else None
                if decision is None:
                    remaining.append(batch)
                    continue
                self.sell(code, quantity=batch["quantity"], tag=batch["signal_date"],
                          fill_mode=aq.CurrentClose())
                expected_sales += batch["quantity"] * bar.close
                exited.append(code)
                self.exit_events.append({"signal_date": batch["signal_date"], "code": code,
                                         "entry_date": state.entry_date, "entry_price": state.entry_price,
                                         "exit_date": day, "exit_price": bar.close,
                                         "quantity": batch["quantity"], "reasons": list(decision.reasons),
                                         "holding_sessions": session-state.entry_session+1})
            self.active = remaining
            codes = selections.get(day, ())
            decision = decisions.get(day)
            if decision is not None:
                account = self.get_account()
                # 同周期卖单可能尚待撮合；已即时到账的卖出所得不再重复相加。
                cash_headroom = max(account["cash"], before["cash"] + expected_sales)
                target = account["equity"] * decision.daily_equity_fraction if codes else 0.0
                budget = min(target, max(0.,cash_headroom)*config.capital_allocation)
                record = {"date": day, "equity": account["equity"], "cash": account["cash"],
                          "target_budget": target, "daily_budget": budget, "submitted_notional_at_close": 0.0}
                self.daily_budgets.append(record)
                for code in codes:
                    price = prepared.bars[code][day].close
                    slots = config.top_n if score_gate is not None else len(codes)
                    quantity = floor(budget/slots/price/config.lot_size)*config.lot_size
                    if quantity:
                        receipt = self.buy(code, quantity=quantity, tag=day, fill_mode=aq.NextOpen())
                        self.pending_entries.extend((day, code, order_id) for order_id in receipt.order_ids)
                        record["submitted_notional_at_close"] += quantity*price
            self.open_batches = [{"signal_date": batch["signal_date"], "code": batch["code"],
                                  "quantity": batch["quantity"], **asdict(batch["state"])} for batch in self.active]
            action = HoldingAction(enter=codes, exit=tuple(dict.fromkeys(exited)),
                                   holding_day=max((session-batch["state"].entry_session for batch in self.active),default=0),
                                   reason="rule_exit" if exited else ("enter" if codes else "holding"), entry_decision=decision)
            self.action_history.append((day, action))

    data = {}
    for code, frame in market_data.items():
        days = pd.to_datetime(frame["datetime"]).dt.strftime("%Y-%m-%d")
        window = frame.loc[days.between(first, end)].copy()
        if not window.empty:
            data[code] = window
    result = aq.run_backtest(data=data, strategy=RuleExitStrategy, symbols=sorted(data),
                             initial_cash=config.initial_cash, commission_rate=config.commission_rate,
                             stamp_tax_rate=config.stamp_tax_rate, transfer_fee_rate=config.transfer_fee_rate,
                             min_commission=config.min_commission, lot_size=config.lot_size,
                             t_plus_one=True, timezone=config.timezone, fill_policy=aq.NextOpen(), show_progress=False)
    _raise_on_rejected_orders(result, untradable_entry_order_ids={
        event["order_id"] for event in result.strategy.unfilled_entries})
    return result
