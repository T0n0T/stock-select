"""按实际成交批次观察退出条件；标签和回测共用这一状态机。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from .exit_indicators import exit_indicators


@dataclass(frozen=True)
class ExitPolicyConfig:
    volume_lookback: int = 5
    volume_multiple: float = 1.5
    timeout_days: int = 3
    timeout_return_pct: float = 3.0

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in (self.volume_lookback, self.timeout_days)):
            raise ValueError("volume_lookback and timeout_days must be positive integers")
        if not isfinite(self.volume_multiple) or self.volume_multiple <= 0:
            raise ValueError("volume_multiple must be positive and finite")
        if not isfinite(self.timeout_return_pct):
            raise ValueError("timeout_return_pct must be finite")


def load_exit_policy(path: Path) -> ExitPolicyConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("exit policy must be a JSON object")
    allowed = {"volume_lookback", "volume_multiple", "timeout_days", "timeout_return_pct"}
    if unknown := raw.keys() - allowed:
        raise ValueError(f"unknown exit policy fields: {sorted(unknown)}")
    return ExitPolicyConfig(**raw)


@dataclass(frozen=True)
class ExitBar:
    open: float
    close: float
    high: float
    volume: float
    previous_close: float | None
    previous_volume_mean: float | None
    ma25: float | None
    tdx_sell: bool


@dataclass(frozen=True)
class ExitDecision:
    date: str
    reasons: tuple[str, ...]


@dataclass
class ExitState:
    entry_date: str
    entry_session: int
    entry_price: float
    bull_midpoint: float | None = None
    bull_date: str | None = None
    timeout_checked: bool = False

    def observe(self, day: str, session: int, bar: ExitBar, config: ExitPolicyConfig) -> ExitDecision | None:
        age = session - self.entry_session
        if age < 0:
            raise ValueError("cannot observe a bar before entry")
        if (bar.previous_close is not None and bar.previous_volume_mean is not None
                and bar.previous_volume_mean > 0 and bar.close > bar.open
                and bar.close > bar.previous_close
                and bar.volume >= bar.previous_volume_mean * config.volume_multiple):
            self.bull_midpoint = (bar.open + bar.close) / 2
            self.bull_date = day
        # 买入日只更新放量阳线状态；可卖日起才判断退出，遵守 A 股 T+1。
        if age == 0:
            return None
        reasons = []
        if bar.ma25 is not None and bar.close < bar.ma25:
            reasons.append("below_ma25")
        if self.bull_midpoint is not None and bar.close < self.bull_midpoint:
            reasons.append("below_volume_bull_midpoint")
        if age >= config.timeout_days and not self.timeout_checked:
            self.timeout_checked = True
            # 直接比较价格，避免 10.3/10 的浮点舍入误判恰好达到 3%。
            if bar.close < self.entry_price * (1 + config.timeout_return_pct / 100):
                reasons.append("t3_return_below_3pct")
        if bar.tdx_sell:
            reasons.append("tdx_kdj_slope")
        return ExitDecision(day, tuple(reasons)) if reasons else None


class ExitMarket:
    """预计算每根 bar 的历史指标；查询只按当天日期取值。"""

    def __init__(self, market: Mapping[str, Any], config: ExitPolicyConfig):
        import pandas as pd

        self.config = config
        self.bars: dict[str, dict[str, ExitBar]] = {}
        for code, frame in market.items():
            ordered = frame.sort_values("datetime").reset_index(drop=True)
            days = pd.DatetimeIndex(pd.to_datetime(ordered["datetime"]))
            if days.has_duplicates or days.hasnans:
                raise ValueError(f"{code}: requires unique valid daily bars")
            features = exit_indicators(ordered)
            previous_close = ordered["close"].shift(1)
            previous_volume = ordered["volume"].shift(1).rolling(config.volume_lookback, min_periods=config.volume_lookback).mean()
            nullable = lambda value: float(value) if pd.notna(value) else None
            self.bars[code] = {
                day.strftime("%Y-%m-%d"): ExitBar(
                    open=float(row.open), close=float(row.close), high=float(row.high), volume=float(row.volume),
                    previous_close=nullable(previous_close.iloc[index]),
                    previous_volume_mean=nullable(previous_volume.iloc[index]),
                    ma25=nullable(row.exit_ma25), tdx_sell=bool(row.exit_tdx_sell),
                )
                for index, (day, row) in enumerate(zip(days, features.itertuples(index=False)))
            }
        self.sessions = sorted({day for bars in self.bars.values() for day in bars})
        self.indices = {day: index for index, day in enumerate(self.sessions)}

    def ready(self, code: str, day: str) -> bool:
        bar = self.bars.get(code, {}).get(day)
        return bar is not None and bar.ma25 is not None

    def outcome(self, code: str, signal_date: str, *, as_of: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"status": "missing_warmup"}
        if not self.ready(code, signal_date):
            return result
        entry_index = self.indices[signal_date] + 1
        if entry_index >= len(self.sessions):
            return {"status": "no_entry_session"}
        bars = self.bars[code]
        entry_date = self.sessions[entry_index]
        if entry_date not in bars:
            return {"status": "untradable_entry"}
        entry_price = bars[entry_date].open
        state = ExitState(entry_date, entry_index, entry_price)
        result = {"status": "right_censored", "entry_date": entry_date, "entry_price": entry_price}
        for index in range(entry_index, len(self.sessions)):
            day = self.sessions[index]
            if as_of is not None and day > as_of:
                break
            if (bar := bars.get(day)) is None:
                continue
            decision = state.observe(day, index, bar, self.config)
            if decision is not None:
                return {**result, "status": "closed", "exit_date": day, "exit_price": bar.close,
                        "exit_reason": decision.reasons[0], "exit_reasons": list(decision.reasons),
                        "holding_sessions": index-entry_index+1, "return_pct": (bar.close/entry_price-1)*100}
        return result
