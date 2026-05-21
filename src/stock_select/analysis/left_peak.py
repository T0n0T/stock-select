from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LeftPeakBreakout:
    left_peak_date: str | None
    left_peak_high: float | None
    breakout_date: str | None
    breakout_close: float | None
    breakout_body_above_left_peak: bool
    is_valid: bool


def find_recent_left_peak_breakout(
    history: pd.DataFrame,
    pick_date: str,
    *,
    swing_lookback: int = 2,
    breakout_lookback: int = 5,
    high_cycle_days: int = 360,
    min_pullback_pct: float = 5.0,
) -> LeftPeakBreakout:
    if history.empty:
        return _empty_breakout()

    frame = history.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed")
    for column in ("open", "high", "low", "close"):
        if column not in frame.columns:
            return _empty_breakout()
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "open", "high", "low", "close"]).sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        return _empty_breakout()

    return find_recent_left_peak_breakout_prepared(
        frame,
        pd.Timestamp(pick_date),
        swing_lookback=swing_lookback,
        breakout_lookback=breakout_lookback,
        high_cycle_days=high_cycle_days,
        min_pullback_pct=min_pullback_pct,
    )


def find_recent_left_peak_breakout_prepared(
    history: pd.DataFrame,
    pick_date: pd.Timestamp,
    *,
    swing_lookback: int = 2,
    breakout_lookback: int = 5,
    high_cycle_days: int = 360,
    min_pullback_pct: float = 5.0,
) -> LeftPeakBreakout:
    if history.empty:
        return _empty_breakout()

    frame = history.loc[history["trade_date"] <= pick_date].reset_index(drop=True)
    if len(frame) < max(20, breakout_lookback + swing_lookback * 2 + 1):
        return _empty_breakout()

    recent_window_start = max(0, len(frame) - breakout_lookback)
    recent_window = frame.iloc[recent_window_start:].reset_index(drop=True)
    prior_frame = frame.iloc[:recent_window_start].reset_index(drop=True)
    if prior_frame.empty:
        return _empty_breakout()

    peak_indices = _find_swing_highs(prior_frame, swing_lookback=swing_lookback)
    if not peak_indices:
        return _empty_breakout()

    left_peak_idx = _resolve_left_peak_index_by_state_machine(
        prior_frame,
        peak_indices=peak_indices,
        high_cycle_days=high_cycle_days,
    )
    if left_peak_idx is None:
        return _empty_breakout()

    peak_row = prior_frame.iloc[left_peak_idx]
    peak_high = float(peak_row["high"])
    breakout_mask = recent_window["close"].astype(float) > peak_high
    if not bool(breakout_mask.any()):
        return _empty_breakout()
    breakout_recent_index = int(breakout_mask[breakout_mask].index[0])
    breakout_idx = recent_window_start + breakout_recent_index
    breakout_window_start = max(0, breakout_idx - breakout_lookback + 1)
    breakout_window = frame.iloc[breakout_window_start : breakout_idx + 1]
    breakout_body_above = bool(
        ((breakout_window["open"].astype(float) > peak_high) & (breakout_window["close"].astype(float) > peak_high)).any()
    )
    if not breakout_body_above:
        return _empty_breakout()
    after_peak = frame.iloc[left_peak_idx + 1 : breakout_idx + 1]
    if after_peak.empty or peak_high <= 0.0:
        return _empty_breakout()
    min_low = float(after_peak["low"].min())
    pullback_pct = (peak_high - min_low) / peak_high * 100.0
    if pullback_pct < min_pullback_pct:
        return _empty_breakout()

    return LeftPeakBreakout(
        left_peak_date=peak_row["trade_date"].strftime("%Y-%m-%d"),
        left_peak_high=peak_high,
        breakout_date=frame.iloc[breakout_idx]["trade_date"].strftime("%Y-%m-%d"),
        breakout_close=float(frame.iloc[breakout_idx]["close"]),
        breakout_body_above_left_peak=breakout_body_above,
        is_valid=True,
    )


def _resolve_left_peak_index_by_state_machine(
    frame: pd.DataFrame,
    *,
    peak_indices: list[int],
    high_cycle_days: int,
) -> int | None:
    cycle_end = len(frame) - 1
    cycle_start = max(0, cycle_end - high_cycle_days + 1)
    cycle_peak_indices = [idx for idx in peak_indices if cycle_start <= idx <= cycle_end]
    if not cycle_peak_indices:
        return None

    return max(
        cycle_peak_indices,
        key=lambda idx: (float(frame.iloc[idx]["high"]), idx),
    )


def _find_swing_highs(frame: pd.DataFrame, *, swing_lookback: int) -> list[int]:
    highs = frame["high"].astype(float).reset_index(drop=True)
    peaks: list[int] = []
    for idx in range(swing_lookback, len(frame) - swing_lookback):
        value = float(highs.iloc[idx])
        left = highs.iloc[idx - swing_lookback : idx]
        right = highs.iloc[idx + 1 : idx + swing_lookback + 1]
        if value > float(left.max()) and value >= float(right.max()):
            peaks.append(idx)
    return peaks


def _empty_breakout() -> LeftPeakBreakout:
    return LeftPeakBreakout(
        left_peak_date=None,
        left_peak_high=None,
        breakout_date=None,
        breakout_close=None,
        breakout_body_above_left_peak=False,
        is_valid=False,
    )
