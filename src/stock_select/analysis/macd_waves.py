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


@dataclass(frozen=True)
class MacdStateMachineResult:
    current_state: str
    current_wave_index: int
    valid_odd_wave_count: int
    H: float | None
    L: float | None
    baseline_H: float | None
    pre_odd_macd_max: float | None
    current_wave_macd_max: float | None
    current_even_macd_min: float | None
    current_even_L: float | None
    prev_even_L: float | None
    even_repair_started: bool
    golden_cross_imminent: bool
    bottom_divergence_valid: bool | None
    events: tuple[str, ...]
    reason: str


def classify_daily_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState:
    working = _slice_to_pick(frame, pick_date)
    if working.empty or "close" not in working.columns:
        return _invalid_trend_state("missing daily close history", len(working))
    macd = compute_macd(working[["close"]].astype(float))
    return _classify_macd_trend_with_state_machine_from_lines(macd[["dif", "dea"]])


def classify_macd_state_from_lines(lines: pd.DataFrame) -> MacdStateMachineResult:
    working = lines.copy().reset_index(drop=True)
    if not {"dif", "dea"}.issubset(working.columns):
        return _invalid_state_machine_result("missing MACD line columns")

    working["dif"] = pd.to_numeric(working["dif"], errors="coerce")
    working["dea"] = pd.to_numeric(working["dea"], errors="coerce")
    working = working.dropna(subset=["dif", "dea"]).reset_index(drop=True)
    if len(working) < _MIN_TREND_PERIODS:
        return _invalid_state_machine_result("insufficient MACD history")

    macd = ((working["dif"] - working["dea"]) * 2.0).astype(float).reset_index(drop=True)
    dif = working["dif"].astype(float).reset_index(drop=True)
    dea = working["dea"].astype(float).reset_index(drop=True)

    state = "waiting_underwater"
    current_wave_index = 0
    valid_odd_wave_count = 0
    H: float | None = None
    L: float | None = None
    baseline_H: float | None = None
    pre_odd_macd_max: float | None = None
    pre_odd_dead_crossed = False
    current_wave_macd_max: float | None = None
    current_even_macd_min: float | None = None
    current_even_L: float | None = None
    prev_even_L: float | None = None
    even_repair_started = False
    golden_cross_imminent = False
    bottom_divergence_valid: bool | None = None
    events: list[str] = []
    reason = "waiting for underwater golden cross"
    has_prior_completed_red_segment = False
    positive_segment_active = False

    def end_cycle(end_reason: str) -> None:
        nonlocal state
        nonlocal current_wave_index
        nonlocal H
        nonlocal L
        nonlocal baseline_H
        nonlocal pre_odd_macd_max
        nonlocal pre_odd_dead_crossed
        nonlocal current_wave_macd_max
        nonlocal current_even_macd_min
        nonlocal current_even_L
        nonlocal even_repair_started
        nonlocal golden_cross_imminent
        nonlocal bottom_divergence_valid
        nonlocal reason

        if state != "waiting_underwater" and not events[-1:] == ["cycle_ended"]:
            events.append("cycle_ended")
        state = "waiting_underwater"
        current_wave_index = 0
        H = None
        L = None
        baseline_H = None
        pre_odd_macd_max = None
        pre_odd_dead_crossed = False
        current_wave_macd_max = None
        current_even_macd_min = None
        current_even_L = None
        even_repair_started = False
        golden_cross_imminent = False
        bottom_divergence_valid = None
        reason = end_reason

    def confirm_odd_wave(confirm_reason: str) -> None:
        nonlocal state
        nonlocal current_wave_index
        nonlocal valid_odd_wave_count
        nonlocal current_wave_macd_max
        nonlocal reason

        state = "odd_wave_forming"
        current_wave_index = 1 if current_wave_index == 0 else current_wave_index + 1
        if current_wave_index % 2 == 0:
            current_wave_index += 1
        valid_odd_wave_count += 1
        current_wave_macd_max = pre_odd_macd_max
        reason = confirm_reason
        events.append("odd_wave_confirmed")

    def start_even_wave(start_reason: str) -> None:
        nonlocal state
        nonlocal current_wave_index
        nonlocal current_even_macd_min
        nonlocal current_even_L
        nonlocal even_repair_started
        nonlocal golden_cross_imminent
        nonlocal bottom_divergence_valid
        nonlocal reason

        state = "even_wave_forming"
        current_wave_index += 1
        current_even_macd_min = curr_macd
        current_even_L = None
        even_repair_started = False
        golden_cross_imminent = False
        bottom_divergence_valid = None
        reason = start_reason
        events.append("even_wave_started")

    def roll_even_adjustment_segment() -> None:
        nonlocal current_even_macd_min
        nonlocal current_even_L
        nonlocal prev_even_L
        nonlocal even_repair_started
        nonlocal golden_cross_imminent
        nonlocal bottom_divergence_valid

        if current_even_macd_min is not None:
            prev_even_L = current_even_macd_min
        current_even_macd_min = None
        current_even_L = None
        even_repair_started = False
        golden_cross_imminent = False
        bottom_divergence_valid = None

    def start_pre_odd_adjustment(adjust_reason: str) -> None:
        nonlocal state
        nonlocal H
        nonlocal baseline_H
        nonlocal pre_odd_dead_crossed
        nonlocal current_even_macd_min
        nonlocal current_even_L
        nonlocal even_repair_started
        nonlocal golden_cross_imminent
        nonlocal bottom_divergence_valid
        nonlocal reason

        state = "pre_odd_adjusting"
        current_even_macd_min = curr_macd
        current_even_L = None
        even_repair_started = False
        golden_cross_imminent = False
        bottom_divergence_valid = None
        if pre_odd_macd_max is not None and pre_odd_macd_max > 0.0:
            H = pre_odd_macd_max
            baseline_H = pre_odd_macd_max
            events.append("pre_odd_failed_rebase_H")
        pre_odd_dead_crossed = False
        reason = adjust_reason

    def update_even_repair_flags(idx: int, curr_macd: float, curr_dea: float) -> None:
        nonlocal even_repair_started
        nonlocal bottom_divergence_valid
        nonlocal reason

        recent_negative_contracting = (
            idx >= 3
            and float(macd.iloc[idx - 2]) <= 0.0
            and float(macd.iloc[idx - 1]) <= 0.0
            and curr_macd <= 0.0
            and abs(curr_macd) < abs(float(macd.iloc[idx - 1])) < abs(float(macd.iloc[idx - 2]))
        )
        first_negative_rebound_after_even_low = (
            idx >= 2
            and float(macd.iloc[idx - 1]) <= 0.0
            and curr_macd <= 0.0
            and curr_macd > float(macd.iloc[idx - 1])
            and float(macd.iloc[idx - 1]) <= float(macd.iloc[idx - 2])
        )
        if (
            current_even_macd_min is not None
            and (recent_negative_contracting or first_negative_rebound_after_even_low)
            and curr_macd <= 0.0
            and curr_dea > 0.0
        ):
            even_repair_started = True
            if prev_even_L is not None:
                bottom_divergence_valid = current_even_macd_min > prev_even_L
            reason = "even wave repair started"
            events.append("even_repair_started")

    for idx in range(1, len(working)):
        prev_macd = float(macd.iloc[idx - 1])
        curr_macd = float(macd.iloc[idx])
        prev_dif = float(dif.iloc[idx - 1])
        curr_dif = float(dif.iloc[idx])
        curr_dea = float(dea.iloc[idx])
        prev_dea = float(dea.iloc[idx - 1])

        if _is_positive_macd_peak(macd, idx - 1):
            H = prev_macd
        if _is_nonpositive_macd_valley(macd, idx - 1):
            L = prev_macd
            if state in {"even_wave_forming", "pre_odd_adjusting"}:
                current_even_L = prev_macd

        underwater_golden_cross = prev_dif <= prev_dea and curr_dif > curr_dea and curr_dif < 0.0 and curr_dea < 0.0
        above_golden_cross = prev_dif <= prev_dea and curr_dif > curr_dea and curr_dea > 0.0 and curr_macd > 0.0
        dead_cross_event = prev_macd > 0.0 and curr_macd <= 0.0 and prev_dif > prev_dea
        dea_reentered_underwater = prev_dea > 0.0 and curr_dea <= 0.0
        dea_crossed_above_zero = prev_dea <= 0.0 and curr_dea > 0.0

        if curr_macd > 0.0:
            positive_segment_active = True
        elif positive_segment_active and curr_macd <= 0.0:
            has_prior_completed_red_segment = True
            positive_segment_active = False

        if dea_reentered_underwater and state not in {"waiting_underwater", "pre_wave1_pushing"}:
            end_cycle("dea crossed below zero")
            continue

        if state == "waiting_underwater":
            if underwater_golden_cross:
                reason = "underwater golden cross observed while waiting for dea above zero"
                events.append("underwater_gc_observed")
            if dea_crossed_above_zero:
                if not has_prior_completed_red_segment:
                    state = "odd_wave_forming"
                    current_wave_index = 1
                    valid_odd_wave_count += 1
                    current_wave_macd_max = curr_macd
                    reason = "first dea-above-zero push without prior red peak counts as wave1"
                    events.append("odd_wave_confirmed")
                else:
                    state = "pre_wave1_pushing"
                    baseline_H = H
                    pre_odd_macd_max = curr_macd
                    reason = "dea crossed above zero and started pre wave1 push"
                    events.append("pre_wave1_started")
            continue

        if state in {"pre_wave1_pushing", "pre_odd_pushing"}:
            pre_odd_macd_max = curr_macd if pre_odd_macd_max is None else max(pre_odd_macd_max, curr_macd)
            if baseline_H is not None and pre_odd_macd_max > baseline_H:
                confirm_odd_wave("pre odd wave confirmed by macd_max above baseline_H")
                continue
            if dead_cross_event:
                if baseline_H is None and pre_odd_macd_max is not None:
                    confirm_odd_wave("pre odd wave confirmed because no prior baseline_H exists")
                    start_even_wave("valid odd wave ended with above-water dead cross")
                    continue
                if state == "pre_wave1_pushing" and dea_reentered_underwater:
                    end_cycle("pre wave1 failed adjustment invalidated by dea below zero")
                    continue
                if state == "pre_odd_pushing":
                    start_pre_odd_adjustment("pre odd failed and entered above-zero adjustment")
                    continue
                pre_odd_dead_crossed = True
                if state == "pre_wave1_pushing":
                    reason = "pre wave1 failed to exceed baseline_H"
                continue
            if state == "pre_wave1_pushing" and pre_odd_dead_crossed and dea_reentered_underwater:
                end_cycle("pre wave1 failed adjustment invalidated by dea below zero")
                continue
            if curr_macd <= 0.0 and curr_dea > 0.0 and prev_macd > curr_macd:
                start_pre_odd_adjustment("pre odd failed and entered above-zero adjustment")
            continue

        if state == "pre_odd_adjusting":
            current_even_macd_min = curr_macd if current_even_macd_min is None else min(current_even_macd_min, curr_macd)
            golden_cross_imminent = False
            update_even_repair_flags(idx, curr_macd, curr_dea)
            if above_golden_cross:
                if current_even_macd_min is not None:
                    prev_even_L = current_even_macd_min
                even_repair_started = False
                golden_cross_imminent = False
                bottom_divergence_valid = None
                state = "pre_odd_pushing"
                baseline_H = H
                pre_odd_macd_max = curr_macd
                pre_odd_dead_crossed = False
                reason = "above-water golden cross starts next pre odd push"
                events.append("pre_odd_repush_started")
            continue

        if state == "odd_wave_forming":
            current_wave_macd_max = curr_macd if current_wave_macd_max is None else max(current_wave_macd_max, curr_macd)
            if dead_cross_event:
                start_even_wave("valid odd wave ended with above-water dead cross")
            continue

        if state == "even_wave_forming":
            current_even_macd_min = curr_macd if current_even_macd_min is None else min(current_even_macd_min, curr_macd)
            golden_cross_imminent = False
            if (
                current_even_macd_min is not None
                and curr_macd <= 0.0
                and curr_dea > 0.0
            ):
                update_even_repair_flags(idx, curr_macd, curr_dea)
            if (
                even_repair_started
                and curr_dea > 0.0
                and curr_macd < 0.0
                and abs(curr_macd) <= 0.02
            ):
                golden_cross_imminent = True
                reason = "golden cross imminent after even-wave repair"
                if not events[-1:] == ["golden_cross_imminent"]:
                    events.append("golden_cross_imminent")
            if above_golden_cross:
                roll_even_adjustment_segment()
                state = "pre_odd_pushing"
                baseline_H = H
                pre_odd_macd_max = curr_macd
                pre_odd_dead_crossed = False
                reason = "even wave ended with above-water golden cross"
                events.append("pre_odd_started")
            continue

    if _is_positive_macd_peak(macd, len(working) - 1):
        H = float(macd.iloc[-1])
    if _is_nonpositive_macd_valley(macd, len(working) - 1):
        L = float(macd.iloc[-1])
        if state == "even_wave_forming":
            current_even_L = float(macd.iloc[-1])

    return MacdStateMachineResult(
        current_state=state,
        current_wave_index=current_wave_index,
        valid_odd_wave_count=valid_odd_wave_count,
        H=_round_optional(H),
        L=_round_optional(L),
        baseline_H=_round_optional(baseline_H),
        pre_odd_macd_max=_round_optional(pre_odd_macd_max),
        current_wave_macd_max=_round_optional(current_wave_macd_max),
        current_even_macd_min=_round_optional(current_even_macd_min),
        current_even_L=_round_optional(current_even_L),
        prev_even_L=_round_optional(prev_even_L),
        even_repair_started=even_repair_started,
        golden_cross_imminent=golden_cross_imminent,
        bottom_divergence_valid=bottom_divergence_valid,
        events=tuple(events),
        reason=reason,
    )


def classify_weekly_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState:
    working = _slice_to_pick(frame, pick_date)
    if working.empty or "close" not in working.columns:
        return _invalid_trend_state("missing weekly close history", len(working))
    weekly_close = working.set_index("trade_date")["close"].astype(float).resample("W-FRI").last().dropna()
    weekly_close = weekly_close.loc[weekly_close.index <= pd.Timestamp(pick_date)]
    macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    return _classify_macd_trend_with_state_machine_from_lines(macd[["dif", "dea"]])


def _classify_macd_trend_with_state_machine_from_lines(lines: pd.DataFrame) -> MacdTrendState:
    legacy = _classify_macd_trend_from_lines(lines)
    state = classify_macd_state_from_lines(lines)
    if state.current_state == "invalid":
        return legacy
    if not state.events and state.current_wave_index <= 0:
        return legacy

    phase, direction, phase_index, wave_stage = _map_state_machine_trend_fields(state)
    if phase == "invalid":
        return legacy
    wave_stage = _resolve_state_machine_wave_stage(state_stage=wave_stage, legacy_stage=legacy.wave_stage)

    metrics = dict(legacy.metrics)
    metrics.update(_state_machine_metrics(state))
    return MacdTrendState(
        phase=phase,
        direction=direction,
        is_rising_initial=_is_state_machine_rising_initial(state, phase_index=phase_index),
        is_top_divergence=_is_state_machine_top_divergence(state=state, legacy=legacy),
        bars_in_phase=legacy.bars_in_phase,
        phase_index=phase_index,
        reason=state.reason,
        metrics=metrics,
        wave_label=_wave_label(phase_index),
        wave_direction="rising" if phase_index % 2 == 1 and phase_index > 0 else "falling" if phase_index > 0 else "neutral",
        wave_stage=wave_stage,
        transition_warnings=_state_machine_transition_warnings(state, legacy=legacy),
    )


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


def _map_state_machine_trend_fields(state: MacdStateMachineResult) -> tuple[str, str, int, str]:
    wave_index = int(state.current_wave_index or 0)
    if state.current_state == "odd_wave_forming":
        wave_index = wave_index if wave_index > 0 else 1
        return "rising", "rising", wave_index, "启动"
    if state.current_state == "even_wave_forming":
        wave_index = wave_index if wave_index > 0 else 2
        stage = "金叉临近" if state.golden_cross_imminent else "修复" if state.even_repair_started else "调整"
        return "falling", "falling", wave_index, stage
    if state.current_state in {"pre_odd_pushing", "pre_wave1_pushing"}:
        next_wave = 1 if wave_index <= 0 else wave_index + 1
        if next_wave % 2 == 0:
            next_wave += 1
        return "rising", "rising", next_wave, "预启动"
    if state.current_state == "pre_odd_adjusting":
        wave_index = wave_index if wave_index > 0 else 2
        stage = "修复" if state.even_repair_started else "调整"
        return "falling", "falling", wave_index, stage
    if state.current_state == "waiting_underwater":
        return "idle", "neutral", 0, "等待启动"
    return "invalid", "neutral", 0, ""


def _resolve_state_machine_wave_stage(*, state_stage: str, legacy_stage: str) -> str:
    if state_stage in {"修复", "金叉临近", "等待启动"}:
        return state_stage
    return legacy_stage or state_stage


def _state_machine_metrics(state: MacdStateMachineResult) -> dict[str, float | int | bool | str]:
    metrics: dict[str, float | int | bool | str] = {
        "state_machine_state": state.current_state,
        "state_machine_wave_index": state.current_wave_index,
        "state_machine_valid_odd_wave_count": state.valid_odd_wave_count,
        "even_repair_started": state.even_repair_started,
        "golden_cross_imminent": state.golden_cross_imminent,
        "state_machine_reason": state.reason,
    }
    optional_values: dict[str, float | bool | None] = {
        "H": state.H,
        "L": state.L,
        "baseline_H": state.baseline_H,
        "pre_odd_macd_max": state.pre_odd_macd_max,
        "current_wave_macd_max": state.current_wave_macd_max,
        "current_even_macd_min": state.current_even_macd_min,
        "current_even_L": state.current_even_L,
        "prev_even_L": state.prev_even_L,
        "bottom_divergence_valid": state.bottom_divergence_valid,
    }
    for key, value in optional_values.items():
        if value is not None:
            metrics[key] = value
    return metrics


def _is_state_machine_rising_initial(state: MacdStateMachineResult, *, phase_index: int) -> bool:
    if state.current_state in {"pre_odd_pushing", "pre_wave1_pushing"}:
        return True
    return state.current_state == "odd_wave_forming" and phase_index in {1, 3}


def _is_state_machine_top_divergence(*, state: MacdStateMachineResult, legacy: MacdTrendState) -> bool:
    if state.current_state != "odd_wave_forming":
        return False
    return bool(legacy.is_top_divergence)


def _state_machine_transition_warnings(state: MacdStateMachineResult, *, legacy: MacdTrendState) -> tuple[str, ...]:
    warnings = list(legacy.transition_warnings)
    if state.golden_cross_imminent:
        warnings.append("金叉临近，奇数浪可能启动")
    if state.bottom_divergence_valid is True:
        warnings.append("偶数浪底背离有效")
    if state.bottom_divergence_valid is False:
        warnings.append("偶数浪底背离无效")
    return tuple(dict.fromkeys(warnings))


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


def _invalid_state_machine_result(reason: str) -> MacdStateMachineResult:
    return MacdStateMachineResult(
        current_state="invalid",
        current_wave_index=0,
        valid_odd_wave_count=0,
        H=None,
        L=None,
        baseline_H=None,
        pre_odd_macd_max=None,
        current_wave_macd_max=None,
        current_even_macd_min=None,
        current_even_L=None,
        prev_even_L=None,
        even_repair_started=False,
        golden_cross_imminent=False,
        bottom_divergence_valid=None,
        events=(),
        reason=reason,
    )


def _is_positive_macd_peak(macd: pd.Series, idx: int) -> bool:
    if idx <= 0 or idx >= len(macd) - 1:
        return False
    value = float(macd.iloc[idx])
    return value > 0.0 and value >= float(macd.iloc[idx - 1]) and value >= float(macd.iloc[idx + 1])


def _is_nonpositive_macd_valley(macd: pd.Series, idx: int) -> bool:
    if idx <= 0 or idx >= len(macd) - 1:
        return False
    value = float(macd.iloc[idx])
    return value <= 0.0 and value <= float(macd.iloc[idx - 1]) and value <= float(macd.iloc[idx + 1])


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


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
