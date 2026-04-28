from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from stock_select.indicators import compute_macd

_WEEKLY_CHURN_LOOKBACK_DAYS = 182
RISING_INITIAL_BARS = 3
_MIN_TREND_PERIODS = 4


@dataclass(frozen=True)
class MacdWaveClassification:
    label: str
    passed: bool
    reason: str
    details: dict[str, float | int | bool | str]


@dataclass(frozen=True)
class DailyMacdState:
    state: str
    valid_for_pullback: bool
    reason: str
    metrics: dict[str, float | int | bool | str]


@dataclass(frozen=True)
class MacdTrendState:
    phase: str
    direction: str
    is_rising_initial: bool
    is_top_divergence: bool
    bars_in_phase: int
    phase_index: int
    reason: str
    metrics: dict[str, float | int | bool | str]
    wave_label: str = ""
    wave_direction: str = "neutral"
    wave_stage: str = ""
    transition_warnings: tuple[str, ...] = ()


def classify_daily_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState:
    working = _slice_to_pick(frame, pick_date)
    if working.empty or "close" not in working.columns:
        return _invalid_trend_state("missing daily close history", len(working))
    macd = compute_macd(working[["close"]].astype(float))
    return _classify_macd_trend_from_lines(macd[["dif", "dea"]])


def classify_weekly_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState:
    working = _slice_to_pick(frame, pick_date)
    if working.empty or "close" not in working.columns:
        return _invalid_trend_state("missing weekly close history", len(working))
    weekly_close = working.set_index("trade_date")["close"].astype(float).resample("W-FRI").last().dropna()
    weekly_close = weekly_close.loc[weekly_close.index <= pd.Timestamp(pick_date)]
    macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    return _classify_macd_trend_from_lines(macd[["dif", "dea"]])


def _classify_macd_trend_from_lines(lines: pd.DataFrame) -> MacdTrendState:
    working = lines.copy().reset_index(drop=True)
    if not {"dif", "dea"}.issubset(working.columns):
        return _invalid_trend_state("missing MACD line columns", 0)

    working["dif"] = pd.to_numeric(working["dif"], errors="coerce")
    working["dea"] = pd.to_numeric(working["dea"], errors="coerce")
    working = working.dropna(subset=["dif", "dea"]).reset_index(drop=True)
    if len(working) < _MIN_TREND_PERIODS:
        return _invalid_trend_state("insufficient MACD history", len(working))
    if len(working) >= 10 and _is_churn((working["dif"] - working["dea"]).tail(10)):
        has_recent_above_zero_run = bool(((working["dif"] > 0.0) & (working["dea"] > 0.0)).tail(10).sum() >= 5)
        if not has_recent_above_zero_run:
            return _invalid_trend_state("MACD trend churn", len(working))

    machine = "waiting_underwater_cross"
    phase = "idle"
    reason = "waiting for underwater golden cross"
    bars_in_phase = 0
    phase_index = 0
    last_completed_phase = "idle"
    last_completed_reason = reason

    for idx in range(1, len(working)):
        previous = working.iloc[idx - 1]
        current = working.iloc[idx]
        prev_dif = float(previous["dif"])
        prev_dea = float(previous["dea"])
        dif = float(current["dif"])
        dea = float(current["dea"])
        above_water = dif > 0.0 and dea > 0.0
        underwater_golden_cross = prev_dif <= prev_dea and dif > dea and dif < 0.0 and dea < 0.0
        above_dead_cross = prev_dif >= prev_dea and dif < dea and above_water
        above_golden_cross = prev_dif <= prev_dea and dif > dea and above_water

        if phase in {"rising", "falling"} and dif < 0.0:
            phase = "ended"
            last_completed_phase = "ended"
            last_completed_reason = "DIF crossed below zero"
            machine = "waiting_underwater_cross"
            bars_in_phase = 0
            phase_index = 0
            reason = "DIF crossed below zero"
            continue

        if machine == "waiting_underwater_cross":
            if phase in {"ended", "idle"} and above_water:
                machine = "running"
                if dif > dea:
                    phase = "rising"
                    reason = "above-zero recovery into MACD rising segment"
                    phase_index = 1
                else:
                    phase = "falling"
                    reason = "above-zero recovery into MACD falling segment"
                    phase_index = 2
                bars_in_phase = 1
                continue
            if underwater_golden_cross:
                machine = "waiting_above_zero"
                phase = last_completed_phase
                reason = (
                    "waiting for both MACD lines above zero"
                    if last_completed_phase == "idle"
                    else last_completed_reason
                )
            continue

        if machine == "waiting_above_zero":
            if dif < dea:
                machine = "waiting_underwater_cross"
                phase = last_completed_phase
                reason = last_completed_reason
                continue
            if above_water:
                machine = "running"
                phase = "rising"
                reason = "upward MACD segment after zero-axis confirmation"
                bars_in_phase = 1
                phase_index = 1
                continue
            reason = (
                "waiting for both MACD lines above zero"
                if last_completed_phase == "idle"
                else last_completed_reason
            )
            continue

        if machine == "running":
            bars_in_phase += 1
            if phase == "rising" and above_dead_cross:
                phase = "falling"
                reason = "above-water MACD dead cross"
                bars_in_phase = 1
                phase_index += 1
            elif phase == "falling" and above_golden_cross:
                phase = "rising"
                reason = "above-water MACD golden cross"
                bars_in_phase = 1
                phase_index += 1

    latest_dif = float(working["dif"].iloc[-1])
    latest_dea = float(working["dea"].iloc[-1])
    spread = latest_dif - latest_dea
    previous_spread = float(working["dif"].iloc[-2] - working["dea"].iloc[-2])
    direction = phase if phase in {"rising", "falling"} else "neutral"
    wave_label = _wave_label(phase_index) if phase in {"rising", "falling"} else ""
    wave_direction = "rising" if phase_index % 2 == 1 and phase_index > 0 else "falling" if phase_index > 0 else "neutral"
    wave_stage, stage_metrics = _judge_wave_stage(working, phase=phase, bars_in_phase=bars_in_phase)
    transition_warnings = _detect_stage_transition(working, current_stage=wave_stage, phase=phase)
    is_top_divergence = phase == "rising" and (spread < previous_spread or wave_stage == "背离")
    metrics = {
        "periods": len(working),
        "dif": latest_dif,
        "dea": latest_dea,
        "spread": round(spread, 6),
        "previous_spread": round(previous_spread, 6),
    }
    metrics.update(stage_metrics)
    return MacdTrendState(
        phase=phase,
        direction=direction,
        is_rising_initial=phase == "rising" and 1 <= bars_in_phase <= RISING_INITIAL_BARS,
        is_top_divergence=is_top_divergence,
        bars_in_phase=bars_in_phase,
        phase_index=phase_index,
        reason=reason,
        metrics=metrics,
        wave_label=wave_label,
        wave_direction=wave_direction,
        wave_stage=wave_stage,
        transition_warnings=tuple(transition_warnings),
    )


def _wave_label(phase_index: int) -> str:
    labels = {
        1: "一浪",
        2: "二浪",
        3: "三浪",
        4: "四浪",
        5: "五浪",
        6: "六浪",
        7: "七浪",
    }
    return labels.get(phase_index, f"第{phase_index}浪" if phase_index > 0 else "")


def _judge_wave_stage(lines: pd.DataFrame, *, phase: str, bars_in_phase: int = 0) -> tuple[str, dict[str, float]]:
    if phase not in {"rising", "falling"}:
        return "", {}

    working = lines.copy().reset_index(drop=True)
    dif = pd.to_numeric(working["dif"], errors="coerce")
    dea = pd.to_numeric(working["dea"], errors="coerce")
    hist_abs = ((dif - dea) * 2.0).abs()
    if len(working) < 10:
        return "分歧", {
            "hist_change_rate": 0.0,
            "dif_slope_5": 0.0,
            "dif_zero_distance_ratio": 0.0,
        }

    recent_avg = float(hist_abs.tail(5).mean())
    prior_avg = float(hist_abs.iloc[-10:-5].mean())
    latest_hist_abs = float(hist_abs.iloc[-1])
    previous_hist_abs = float(hist_abs.iloc[-2])
    if abs(prior_avg) <= 1e-12:
        hist_change_rate = 0.0 if abs(recent_avg) <= 1e-12 else 1.0
    else:
        hist_change_rate = (recent_avg - prior_avg) / abs(prior_avg)

    latest_dif = float(dif.iloc[-1])
    dif_slope_5 = (latest_dif - float(dif.iloc[-6])) / 5.0
    max_abs_dif_20 = float(dif.tail(20).abs().max())
    dif_zero_distance_ratio = abs(latest_dif) / max_abs_dif_20 if max_abs_dif_20 > 1e-12 else 0.0

    if phase == "rising":
        is_new_hist_peak = latest_hist_abs >= float(hist_abs.tail(10).max()) * 0.98
        if hist_change_rate > 0.05 and latest_hist_abs < previous_hist_abs and not is_new_hist_peak:
            stage = "背离"
        elif bars_in_phase > 5 and _is_recent_hist_flattening(hist_abs):
            stage = "强势转分歧" if hist_change_rate > 0.05 else "分歧"
        elif hist_change_rate > 0.05 and dif_slope_5 > 0.001 and dif_zero_distance_ratio > 0.6:
            stage = "强势"
        elif hist_change_rate < -0.05:
            stage = "背离"
        else:
            stage = "分歧"
    else:
        if bars_in_phase > 5 and _is_recent_hist_flattening(hist_abs):
            stage = "强势转分歧" if hist_change_rate > 0.05 else "分歧"
        elif hist_change_rate > 0.05 and dif_slope_5 < -0.001:
            stage = "强势"
        elif hist_change_rate < -0.05:
            stage = "背离"
        else:
            stage = "分歧"

    return stage, {
        "hist_change_rate": round(hist_change_rate, 6),
        "dif_slope_5": round(dif_slope_5, 6),
        "dif_zero_distance_ratio": round(dif_zero_distance_ratio, 6),
        "recent_hist_abs_avg": round(recent_avg, 6),
        "prior_hist_abs_avg": round(prior_avg, 6),
    }


def _is_recent_hist_flattening(hist_abs: pd.Series) -> bool:
    if len(hist_abs) < 4:
        return False
    values = [float(value) for value in hist_abs.tail(4).to_list()]
    latest = values[-1]
    peak = max(values)
    if peak <= 1e-12:
        return False
    last_delta = abs(values[-1] - values[-2]) / peak
    prev_delta = abs(values[-2] - values[-3]) / peak
    return last_delta <= 0.08 or (last_delta <= 0.12 and prev_delta <= 0.12)


def _detect_stage_transition(lines: pd.DataFrame, *, current_stage: str, phase: str) -> list[str]:
    if phase not in {"rising", "falling"}:
        return []

    dif = pd.to_numeric(lines["dif"], errors="coerce").reset_index(drop=True)
    dea = pd.to_numeric(lines["dea"], errors="coerce").reset_index(drop=True)
    hist_abs = ((dif - dea) * 2.0).abs()
    warnings: list[str] = []
    if len(hist_abs) >= 4:
        last4 = hist_abs.tail(4).to_list()
        deltas = [last4[i] - last4[i - 1] for i in range(1, len(last4))]
        max_hist = max(float(hist_abs.tail(10).max()), 1e-12)
        flat_threshold = max_hist * 0.05
        if current_stage == "强势" and (all(delta < 0 for delta in deltas) or all(abs(delta) <= flat_threshold for delta in deltas)):
            warnings.append("强势→分歧预警")
        if current_stage == "背离" and all(delta > 0 for delta in deltas):
            warnings.append("背离→分歧预警（反弹）")
        if current_stage in {"分歧", "背离"} and all(delta < 0 for delta in deltas):
            warnings.append("强势→分歧预警")

    if len(hist_abs) >= 5:
        mean_hist = float(hist_abs.tail(5).mean())
        latest_gap = abs(float(dif.iloc[-1] - dea.iloc[-1]))
        if mean_hist > 1e-12 and latest_gap < 0.25 * mean_hist:
            warnings.append("金叉/死叉临近，浪型可能切换")

    return warnings

def _invalid_trend_state(reason: str, periods: int) -> MacdTrendState:
    return MacdTrendState(
        phase="invalid",
        direction="neutral",
        is_rising_initial=False,
        is_top_divergence=False,
        bars_in_phase=0,
        phase_index=0,
        reason=reason,
        metrics={"periods": periods},
    )


def classify_weekly_macd_wave(frame: pd.DataFrame, pick_date: str) -> MacdWaveClassification:
    working = _slice_to_pick(frame, pick_date)
    weekly_close = working.set_index("trade_date")["close"].astype(float).resample("W-FRI").last().dropna()
    macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    hist = macd["macd_hist"].reset_index(drop=True)
    dif = macd["dif"].reset_index(drop=True)
    dea = macd["dea"].reset_index(drop=True)
    recent_weekly = pd.DataFrame(
        {
            "trade_date": weekly_close.index,
            "hist": hist.to_numpy(),
            "dif": dif.to_numpy(),
            "dea": dea.to_numpy(),
        }
    )
    recent_cutoff = pd.Timestamp(pick_date) - pd.Timedelta(days=_WEEKLY_CHURN_LOOKBACK_DAYS)
    recent_weekly = recent_weekly.loc[recent_weekly["trade_date"] >= recent_cutoff].reset_index(drop=True)
    recent_hist = recent_weekly["hist"].reset_index(drop=True)
    recent_dif = recent_weekly["dif"].reset_index(drop=True)
    recent_dea = recent_weekly["dea"].reset_index(drop=True)

    if len(hist) < 8 or _is_churn(recent_hist):
        return MacdWaveClassification("invalid", False, "weekly MACD churn", {"periods": len(hist)})

    bullish = bool(dif.iloc[-1] > dea.iloc[-1])
    latest_hist = float(hist.iloc[-1])
    previous_hist = float(hist.iloc[-2])
    had_pullback = bool((hist < 0).any())
    recent_underwater_pair = bool(((recent_dif < 0) & (recent_dea < 0)).any())
    fading_bullish_impulse = bool(
        len(weekly_close) >= 3
        and latest_hist > 0.0
        and previous_hist > 0.0
        and latest_hist < previous_hist
        and float(weekly_close.iloc[-1]) < float(weekly_close.iloc[-2])
    )

    if bullish and fading_bullish_impulse:
        return MacdWaveClassification("wave2", False, "weekly pullback after prior advance", {})
    if bullish and latest_hist > 0.0 and previous_hist > 0.0 and had_pullback and recent_underwater_pair:
        return MacdWaveClassification("wave3", True, "weekly second bullish advance after pullback", {})
    if bullish and latest_hist > 0.0:
        return MacdWaveClassification("wave1", True, "weekly first bullish advance after golden cross", {})
    if not bullish and had_pullback:
        return MacdWaveClassification("wave2", False, "weekly pullback after prior advance", {})
    return MacdWaveClassification("invalid", False, "weekly structure incomplete", {})


def classify_daily_macd_wave(frame: pd.DataFrame, pick_date: str) -> MacdWaveClassification:
    state = classify_daily_macd_state(frame, pick_date)
    third_wave_gain = float(state.metrics.get("third_wave_gain", 0.0))
    if state.state == "wave2_end_valid":
        return MacdWaveClassification(
            "wave2_end",
            True,
            state.reason,
            {"third_wave_gain": third_wave_gain, "needs_recross": False},
        )
    if state.state == "wave4_end_valid":
        return MacdWaveClassification(
            "wave4_end",
            True,
            state.reason,
            {"third_wave_gain": third_wave_gain, "needs_recross": False},
        )
    if state.state == "hard_invalid":
        reason = "daily MACD churn"
    elif state.state == "early_recross":
        reason = "daily pullback already re-crossed"
    elif state.state == "overextended":
        reason = "daily third-wave gain exceeded wave4 allowance"
    else:
        reason = "daily pullback still deteriorating"
    return MacdWaveClassification(
        "invalid",
        False,
        reason,
        {"third_wave_gain": third_wave_gain, "needs_recross": False},
    )


def classify_daily_macd_state(frame: pd.DataFrame, pick_date: str) -> DailyMacdState:
    working = _slice_to_pick(frame, pick_date)
    macd = compute_macd(working[["close"]].astype(float))
    hist = macd["macd_hist"].reset_index(drop=True)
    dif = macd["dif"].reset_index(drop=True)
    dea = macd["dea"].reset_index(drop=True)

    if len(hist) < 12 or _is_churn(hist.tail(10)):
        return DailyMacdState(
            "hard_invalid",
            False,
            "daily MACD churn",
            {
                "third_wave_gain": 0.0,
                "bullish_now": False,
                "negative_hist_shrinking": False,
                "positive_hist_shrinking": False,
                "converging": False,
                "recent_cross_up": False,
                "recent_cross_down": False,
                "bars_since_cross": -1,
                "bars_since_hist_peak": -1,
            },
        )

    third_wave_gain = _estimate_third_wave_gain(working["close"].astype(float))
    shrinking_negative = bool(hist.iloc[-1] < 0 and hist.iloc[-2] < 0 and abs(hist.iloc[-1]) < abs(hist.iloc[-2]))
    shrinking_positive = bool(
        len(hist) >= 4
        and hist.iloc[-1] > 0
        and hist.iloc[-2] > 0
        and hist.iloc[-3] > 0
        and float(hist.iloc[-1]) < float(hist.iloc[-2]) < float(hist.iloc[-3])
    )
    converging = bool(abs(dif.iloc[-1] - dea.iloc[-1]) < abs(dif.iloc[-2] - dea.iloc[-2]))
    bullish_now = bool(dif.iloc[-1] > dea.iloc[-1])
    recent_cross_up = bool(((dif.shift(1) <= dea.shift(1)) & (dif > dea)).tail(5).any())
    recent_cross_down = bool(((dif.shift(1) >= dea.shift(1)) & (dif < dea)).tail(5).any())
    bars_since_cross = _bars_since_last_cross(dif, dea)
    bars_since_hist_peak = _bars_since_hist_peak(hist)
    metrics: dict[str, float | int | bool | str] = {
        "third_wave_gain": third_wave_gain,
        "bullish_now": bullish_now,
        "negative_hist_shrinking": shrinking_negative,
        "positive_hist_shrinking": shrinking_positive,
        "converging": converging,
        "recent_cross_up": recent_cross_up,
        "recent_cross_down": recent_cross_down,
        "bars_since_cross": bars_since_cross,
        "bars_since_hist_peak": bars_since_hist_peak,
    }

    if bullish_now and shrinking_positive and converging:
        if third_wave_gain > 0.30:
            return DailyMacdState("overextended", False, "daily third-wave gain exceeded wave4 allowance", metrics)
        return DailyMacdState("wave2_end_valid", True, "daily second-wave pullback nearing end", metrics)

    if bullish_now:
        return DailyMacdState("early_recross", False, "daily pullback already re-crossed", metrics)

    if shrinking_negative and converging:
        if third_wave_gain > 0.30:
            return DailyMacdState("overextended", False, "daily third-wave gain exceeded wave4 allowance", metrics)
        if third_wave_gain > 0.0:
            return DailyMacdState("wave4_end_valid", True, "daily fourth-wave pullback nearing end", metrics)
        return DailyMacdState("wave2_end_valid", True, "daily second-wave pullback nearing end", metrics)

    if shrinking_negative or converging:
        return DailyMacdState("repair_candidate", False, "daily pullback is stabilizing but not complete", metrics)

    return DailyMacdState("deteriorating", False, "daily pullback still deteriorating", metrics)


def _slice_to_pick(frame: pd.DataFrame, pick_date: str) -> pd.DataFrame:
    working = frame.copy()
    working["trade_date"] = pd.to_datetime(working["trade_date"])
    working = (
        working.loc[working["trade_date"] <= pd.Timestamp(pick_date)]
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    return working


def _is_churn(hist: pd.Series) -> bool:
    signs = hist.apply(lambda value: 1 if value > 0 else (-1 if value < 0 else 0))
    flips = int((signs != signs.shift(1)).fillna(False).sum())
    return flips >= 4


def _estimate_third_wave_gain(close: pd.Series) -> float:
    recent = close.tail(20).reset_index(drop=True)
    if len(recent) < 8:
        return 0.0
    second_wave_low = float(recent.iloc[:10].min())
    third_wave_high = float(recent.max())
    if second_wave_low <= 0.0:
        return 0.0
    return round(third_wave_high / second_wave_low - 1.0, 4)


def _bars_since_last_cross(dif: pd.Series, dea: pd.Series) -> int:
    cross_mask = ((dif.shift(1) <= dea.shift(1)) & (dif > dea)) | ((dif.shift(1) >= dea.shift(1)) & (dif < dea))
    indices = cross_mask[cross_mask.fillna(False)].index.tolist()
    if not indices:
        return -1
    return int(len(dif) - 1 - indices[-1])


def _bars_since_hist_peak(hist: pd.Series) -> int:
    if hist.empty:
        return -1
    peak_idx = int(hist.abs().idxmax())
    return int(len(hist) - 1 - peak_idx)


