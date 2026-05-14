from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from stock_select.analysis import macd_waves as macd_waves_module
from stock_select.analysis.macd_waves import MacdStateMachineResult
from stock_select.analysis.macd_waves import classify_macd_state_from_lines


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_GRADE_TABLE_PATH = _PROJECT_ROOT / "docs" / "research" / "macd-wave-score-grade-table.json"


@dataclass(frozen=True)
class MacdWaveStage:
    wave_cycle_phase: str
    current_wave_index: int
    current_opportunity_phase: str
    odd_push_stage: str
    history_confirmed: bool
    waiting_strength_tier: str
    supports_first_even_repair_window: bool
    bottom_divergence_valid: bool | None
    current_odd_peak_confirmed: bool
    current_odd_peak_value: float | None
    previous_odd_peak_value: float | None
    top_divergence_evaluable: bool
    top_divergence_level: str
    risk_flags: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class MacdScoreBreakdown:
    score_1_to_5: float
    raw_score: float
    weekly_score: float
    daily_score: float
    combo_score: float
    risk_adjustment: float
    method_bias: float
    setup_tag: str
    risk_flags: tuple[str, ...]
    reason: str
    review_context: dict[str, str]


@dataclass(frozen=True)
class MacdWaveScoreInputs:
    weekly_stage: MacdWaveStage
    daily_stage: MacdWaveStage


def derive_macd_wave_stage(
    state: MacdStateMachineResult,
    *,
    latest_dif: float,
    latest_dea: float,
    latest_hist: float,
    previous_odd_peak_value: float | None = None,
) -> MacdWaveStage:
    wave_cycle_phase = _derive_wave_cycle_phase(state)
    current_wave_index = _derive_current_wave_index(state, wave_cycle_phase=wave_cycle_phase)
    current_opportunity_phase = _derive_opportunity_phase(state, wave_cycle_phase=wave_cycle_phase)
    history_confirmed = wave_cycle_phase == "odd_confirmed"
    waiting_strength_tier = classify_waiting_strength_tier(
        latest_dif=latest_dif,
        latest_dea=latest_dea,
        latest_hist=latest_hist,
        wave_cycle_phase=wave_cycle_phase,
    )
    supports_first_even_repair_window = (
        wave_cycle_phase == "even_repairing"
        and state.current_wave_index == 2
        and state.valid_odd_wave_count == 1
    )
    odd_push_stage = "not_applicable"
    if wave_cycle_phase in {"pre_odd_pushing", "odd_confirmed"}:
        odd_push_stage = classify_odd_push_stage(
            latest_dif=latest_dif,
            latest_dea=latest_dea,
            latest_hist=latest_hist,
        )
    current_odd_peak_confirmed = "current_odd_peak_confirmed" in state.events
    current_odd_peak_value = state.current_wave_macd_max

    risk_flags: list[str] = []
    if wave_cycle_phase == "pre_odd_pushing" and state.baseline_H is not None and not history_confirmed:
        risk_flags.append("baseline_pending")
    if state.bottom_divergence_valid is False:
        risk_flags.append("bottom_divergence_invalid")
    top_divergence_evaluable, top_divergence_level = _derive_top_divergence(
        wave_cycle_phase=wave_cycle_phase,
        odd_push_stage=odd_push_stage,
        current_odd_peak_confirmed=current_odd_peak_confirmed,
        current_odd_peak_value=current_odd_peak_value,
        previous_odd_peak_value=previous_odd_peak_value,
    )

    return MacdWaveStage(
        wave_cycle_phase=wave_cycle_phase,
        current_wave_index=current_wave_index,
        current_opportunity_phase=current_opportunity_phase,
        odd_push_stage=odd_push_stage,
        history_confirmed=history_confirmed,
        waiting_strength_tier=waiting_strength_tier,
        supports_first_even_repair_window=supports_first_even_repair_window,
        bottom_divergence_valid=state.bottom_divergence_valid,
        current_odd_peak_confirmed=current_odd_peak_confirmed,
        current_odd_peak_value=current_odd_peak_value,
        previous_odd_peak_value=previous_odd_peak_value,
        top_divergence_evaluable=top_divergence_evaluable,
        top_divergence_level=top_divergence_level,
        risk_flags=tuple(risk_flags),
        reason=state.reason,
    )


def _derive_wave_cycle_phase(state: MacdStateMachineResult) -> str:
    if state.current_state == "waiting_underwater":
        return "waiting"
    if state.current_state in {"pre_odd_pushing", "pre_wave1_pushing"}:
        return "pre_odd_pushing"
    if state.current_state == "pre_odd_adjusting":
        return "pre_odd_adjusting"
    if state.current_state == "odd_wave_forming":
        return "odd_confirmed"
    if state.current_state == "even_wave_forming":
        if state.even_repair_started:
            return "even_repairing"
        return "even_adjusting"
    return "waiting"


def _derive_current_wave_index(state: MacdStateMachineResult, *, wave_cycle_phase: str) -> int:
    if wave_cycle_phase in {"pre_odd_pushing", "pre_odd_adjusting"}:
        return _next_odd_wave_index(state.current_wave_index)
    if state.current_state == "even_wave_forming" and state.golden_cross_imminent:
        return _next_odd_wave_index(state.current_wave_index)
    return state.current_wave_index


def _derive_opportunity_phase(state: MacdStateMachineResult, *, wave_cycle_phase: str) -> str:
    if state.current_state == "even_wave_forming" and state.golden_cross_imminent:
        return "pre_odd_imminent"
    if wave_cycle_phase == "pre_odd_pushing":
        return "pre_odd_starting"
    return "not_applicable"


def _next_odd_wave_index(current_wave_index: int) -> int:
    if current_wave_index <= 0:
        return 1
    return current_wave_index + 1 if current_wave_index % 2 == 0 else current_wave_index


def classify_odd_push_stage(*, latest_dif: float, latest_dea: float, latest_hist: float) -> str:
    if 0 < latest_dea < latest_hist and 0 < latest_dif < latest_hist:
        return "stage1_hist_dominant"
    if 0 < latest_dea < latest_hist and latest_hist < latest_dif:
        return "stage2_line_extending"
    if latest_hist < latest_dea and latest_hist < latest_dif:
        return "stage3_hist_lagging"
    return "not_applicable"


def classify_waiting_strength_tier(
    *,
    latest_dif: float,
    latest_dea: float,
    latest_hist: float,
    wave_cycle_phase: str,
) -> str:
    if wave_cycle_phase != "waiting":
        return "not_applicable"
    if latest_dif > 0 and latest_dea < 0 and latest_hist > 0:
        return "underwater_ready"
    if latest_dif < 0 and latest_dea < 0 and latest_hist > 0:
        return "underwater_strengthening"
    return "waiting_flat"


def classify_weekly_grade(stage: MacdWaveStage) -> str:
    if stage.wave_cycle_phase == "cycle_ended":
        return "很差"
    if stage.wave_cycle_phase == "waiting":
        if stage.waiting_strength_tier == "underwater_ready":
            return "差"
        return "很差"
    if stage.wave_cycle_phase == "even_adjusting":
        return "中"
    if stage.wave_cycle_phase == "even_repairing":
        return "中"
    if stage.wave_cycle_phase == "pre_odd_adjusting":
        return "差"
    if stage.wave_cycle_phase == "pre_odd_pushing":
        return "很好"
    if stage.wave_cycle_phase == "odd_confirmed":
        if stage.odd_push_stage == "stage1_hist_dominant":
            return "很好"
        if stage.odd_push_stage == "stage2_line_extending":
            return "好"
        if stage.odd_push_stage == "stage3_hist_lagging":
            return "中"
        return "中"
    return "很差"


def classify_daily_grade(stage: MacdWaveStage) -> str:
    if stage.wave_cycle_phase == "cycle_ended":
        return "很差"
    if stage.wave_cycle_phase == "waiting":
        return "很差"
    if stage.wave_cycle_phase == "even_adjusting":
        return "差"
    if stage.current_opportunity_phase == "pre_odd_imminent":
        return "很好" if stage.current_wave_index == 3 else "好"
    if stage.wave_cycle_phase == "even_repairing":
        if stage.bottom_divergence_valid is True:
            return "很好"
        if stage.supports_first_even_repair_window:
            return "好"
        if stage.bottom_divergence_valid is False:
            return "中"
        return "中"
    if stage.wave_cycle_phase == "pre_odd_pushing":
        return "好"
    if stage.wave_cycle_phase == "pre_odd_adjusting":
        return "中"
    if stage.wave_cycle_phase == "odd_confirmed":
        if stage.odd_push_stage == "stage1_hist_dominant":
            return "很好"
        if stage.odd_push_stage == "stage2_line_extending":
            return "好"
        if stage.odd_push_stage == "stage3_hist_lagging":
            return "中"
        return "中"
    return "很差"


@lru_cache(maxsize=1)
def load_macd_wave_score_grade_table() -> dict[str, dict[str, float]]:
    payload = json.loads(_GRADE_TABLE_PATH.read_text(encoding="utf-8"))
    return {
        "weekly_coeff": {
            env_key: {key: float(value) for key, value in dict(env_values).items()}
            for env_key, env_values in dict(payload["weekly_coeff"]).items()
        },
        "daily": {key: float(value) for key, value in dict(payload["daily"]).items()},
    }


def _derive_top_divergence(
    *,
    wave_cycle_phase: str,
    odd_push_stage: str,
    current_odd_peak_confirmed: bool,
    current_odd_peak_value: float | None,
    previous_odd_peak_value: float | None,
) -> tuple[bool, str]:
    if wave_cycle_phase == "cycle_ended":
        return False, "none"
    if wave_cycle_phase != "odd_confirmed":
        return False, "none"
    if odd_push_stage == "stage1_hist_dominant":
        return False, "none"
    if not current_odd_peak_confirmed:
        return False, "none"
    if (
        current_odd_peak_value is not None
        and previous_odd_peak_value is not None
        and current_odd_peak_value < previous_odd_peak_value
    ):
        return True, "B"
    return True, "none"


def score_macd_state_machine_combo(
    *,
    method: str,
    weekly_stage: MacdWaveStage,
    daily_stage: MacdWaveStage,
    signal: str,
    environment_state: str | None = None,
) -> MacdScoreBreakdown:
    daily_score = _score_daily_stage(daily_stage)
    weekly_score = _score_weekly_stage(
        weekly_stage,
        daily_base_score=daily_score,
        environment_state=environment_state,
    )
    combo_score = _score_combo(
        method=method,
        weekly_stage=weekly_stage,
        daily_stage=daily_stage,
        signal=signal,
        environment_state=environment_state,
    )
    risk_adjustment, risk_flags = _score_risk_adjustment(weekly_stage=weekly_stage, daily_stage=daily_stage)
    method_bias = _score_method_bias(method=method, weekly_stage=weekly_stage, daily_stage=daily_stage, signal=signal)
    raw_score = max(0.0, min(100.0, weekly_score + daily_score + combo_score + risk_adjustment + method_bias))
    score_1_to_5 = round(1.0 + (min(100.0, raw_score + 8.0) / 25.0), 2)
    setup_tag = _derive_setup_tag(weekly_stage=weekly_stage, daily_stage=daily_stage)
    reason = _build_score_reason(
        method=method,
        weekly_stage=weekly_stage,
        daily_stage=daily_stage,
        signal=signal,
        setup_tag=setup_tag,
        risk_flags=risk_flags,
    )
    review_context = render_macd_score_review_context(
        method=method,
        weekly_stage=weekly_stage,
        daily_stage=daily_stage,
        score_setup_tag=setup_tag,
        score_reason=reason,
    )
    return MacdScoreBreakdown(
        score_1_to_5=score_1_to_5,
        raw_score=raw_score,
        weekly_score=weekly_score,
        daily_score=daily_score,
        combo_score=combo_score,
        risk_adjustment=risk_adjustment,
        method_bias=method_bias,
        setup_tag=setup_tag,
        risk_flags=risk_flags,
        reason=reason,
        review_context=review_context,
    )


def _resolve_environment_state(environment_state: str | None) -> str:
    if environment_state in {"strong", "neutral", "weak"}:
        return environment_state
    return "default"


def _weekly_coefficient(stage: MacdWaveStage, *, environment_state: str | None = None) -> float:
    normalized_env = _resolve_environment_state(environment_state)
    table = load_macd_wave_score_grade_table()["weekly_coeff"][normalized_env]
    score = table[classify_weekly_grade(stage)]
    if stage.wave_cycle_phase == "waiting":
        if stage.waiting_strength_tier == "underwater_strengthening":
            score += 0.03
    if stage.wave_cycle_phase == "pre_odd_pushing" and stage.current_wave_index >= 4:
        score -= 0.20
    if stage.bottom_divergence_valid is True:
        score += 0.05
    elif stage.bottom_divergence_valid is False:
        score -= 0.05
    return score


def _score_weekly_stage(stage: MacdWaveStage, *, daily_base_score: float, environment_state: str | None = None) -> float:
    return round(daily_base_score * _weekly_coefficient(stage, environment_state=environment_state), 2)


def _score_daily_stage(stage: MacdWaveStage) -> float:
    table = load_macd_wave_score_grade_table()["daily"]
    grade = classify_daily_grade(stage)
    score = table[grade]

    # Keep the explicit grade table as the base, then use small semantic
    # adjustments so repeated repairs do not outrank earlier repair windows.
    if stage.current_opportunity_phase == "pre_odd_imminent":
        return table["很好"] + (4.0 if stage.current_wave_index == 3 else 1.0)
    if stage.wave_cycle_phase == "even_repairing":
        if stage.bottom_divergence_valid is True:
            if stage.supports_first_even_repair_window:
                return table["好"] + 3.0
            return table["中"] + 2.0
        if stage.supports_first_even_repair_window:
            return table["好"]
        return table["中"]
    return score


def _score_combo(
    *,
    method: str,
    weekly_stage: MacdWaveStage,
    daily_stage: MacdWaveStage,
    signal: str,
    environment_state: str | None = None,
) -> float:
    del method
    if "cycle_ended" in {weekly_stage.wave_cycle_phase, daily_stage.wave_cycle_phase}:
        return 0.0
    if daily_stage.current_opportunity_phase == "pre_odd_imminent" and daily_stage.current_wave_index == 3:
        if weekly_stage.wave_cycle_phase == "odd_confirmed" and weekly_stage.odd_push_stage == "stage1_hist_dominant":
            score = 20.0 if signal == "B3" else 18.0
            if environment_state == "weak":
                return score - 15.0
            if environment_state == "strong":
                return score - 12.0
            return score
        if weekly_stage.wave_cycle_phase == "odd_confirmed" and weekly_stage.odd_push_stage == "stage3_hist_lagging":
            score = 10.0 if signal == "B3" else 8.0
            if environment_state == "strong":
                return score - 2.0
            return score
        if weekly_stage.wave_cycle_phase in {"pre_odd_pushing", "even_repairing", "odd_confirmed"}:
            score = 16.0
            if weekly_stage.wave_cycle_phase == "pre_odd_pushing" and weekly_stage.current_wave_index >= 4:
                score = 6.0
            if environment_state == "weak":
                return score - 15.0
            if environment_state == "strong":
                return score - 4.0
            return score
    if daily_stage.current_opportunity_phase == "pre_odd_imminent":
        if environment_state == "weak":
            return 2.0
    if daily_stage.wave_cycle_phase == "even_repairing" and weekly_stage.wave_cycle_phase == "even_repairing":
        return 10.0
    if daily_stage.wave_cycle_phase == "odd_confirmed" and daily_stage.odd_push_stage == "stage3_hist_lagging":
        return 8.0
    return 6.0


def _score_risk_adjustment(
    *,
    weekly_stage: MacdWaveStage,
    daily_stage: MacdWaveStage,
) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    risk_flags: list[str] = list(weekly_stage.risk_flags) + list(daily_stage.risk_flags)
    if daily_stage.bottom_divergence_valid is True:
        if daily_stage.current_opportunity_phase == "pre_odd_imminent":
            score += 6.0
        elif daily_stage.supports_first_even_repair_window:
            score += 5.0
        elif daily_stage.wave_cycle_phase == "even_repairing":
            score += 1.0
        risk_flags.append("bottom_divergence_valid")
    if daily_stage.bottom_divergence_valid is False:
        score -= 6.0
    if "cycle_ended" in {weekly_stage.wave_cycle_phase, daily_stage.wave_cycle_phase}:
        score -= 10.0
        risk_flags.append("cycle_ended")
    if weekly_stage.top_divergence_level == "B" or daily_stage.top_divergence_level == "B":
        score -= 8.0
        risk_flags.append("top_divergence_B")
    if weekly_stage.current_wave_index >= 7 or daily_stage.current_wave_index >= 7:
        score -= 7.0
        risk_flags.append("late_odd_wave")
    deduped = tuple(dict.fromkeys(risk_flags))
    return score, deduped


def _score_method_bias(
    *,
    method: str,
    weekly_stage: MacdWaveStage,
    daily_stage: MacdWaveStage,
    signal: str,
) -> float:
    bias = 0.0
    if method == "b1":
        if daily_stage.wave_cycle_phase == "even_repairing":
            bias += 4.0
        if daily_stage.current_opportunity_phase == "pre_odd_imminent":
            bias += 2.0
    elif method == "b2":
        if daily_stage.current_opportunity_phase == "pre_odd_imminent" and daily_stage.current_wave_index == 3:
            bias += 4.0 if signal == "B3" else 2.0
        elif daily_stage.wave_cycle_phase == "even_repairing":
            bias += 1.0
    elif method == "dribull":
        if weekly_stage.wave_cycle_phase == "waiting":
            bias -= 5.0
        elif weekly_stage.wave_cycle_phase == "odd_confirmed":
            bias += 1.0
    return bias


def _derive_setup_tag(*, weekly_stage: MacdWaveStage, daily_stage: MacdWaveStage) -> str:
    if "cycle_ended" in {weekly_stage.wave_cycle_phase, daily_stage.wave_cycle_phase}:
        return "cycle_ended"
    if daily_stage.current_opportunity_phase == "pre_odd_imminent" and daily_stage.current_wave_index == 3:
        return "pre_wave3_imminent"
    if daily_stage.current_opportunity_phase == "pre_odd_imminent":
        return "pre_odd_imminent"
    if daily_stage.wave_cycle_phase == "even_repairing":
        return "even_repairing"
    if daily_stage.wave_cycle_phase == "odd_confirmed" and daily_stage.odd_push_stage == "stage3_hist_lagging":
        return "odd_stage3_late"
    return f"{weekly_stage.wave_cycle_phase}__{daily_stage.wave_cycle_phase}"


def _build_score_reason(
    *,
    method: str,
    weekly_stage: MacdWaveStage,
    daily_stage: MacdWaveStage,
    signal: str,
    setup_tag: str,
    risk_flags: tuple[str, ...],
) -> str:
    parts: list[str] = [
        f"method={method}",
        f"signal={signal}",
        f"setup={setup_tag}",
        f"weekly={weekly_stage.wave_cycle_phase}:{weekly_stage.odd_push_stage}",
        f"daily={daily_stage.wave_cycle_phase}:{daily_stage.current_opportunity_phase}:{daily_stage.odd_push_stage}",
    ]
    if "bottom_divergence_valid" in risk_flags:
        parts.append("left_bottom_divergence")
    if risk_flags:
        parts.append(f"risk={','.join(risk_flags)}")
    return "; ".join(parts)


def render_macd_score_review_context(
    *,
    method: str,
    weekly_stage: MacdWaveStage,
    daily_stage: MacdWaveStage,
    score: MacdScoreBreakdown | None = None,
    score_setup_tag: str | None = None,
    score_reason: str | None = None,
) -> dict[str, str]:
    setup_tag = score.setup_tag if score is not None else (score_setup_tag or "")
    reason = score.reason if score is not None else (score_reason or "")
    return {
        "weekly_wave_context": _render_stage_context("周线", weekly_stage),
        "daily_wave_context": _render_stage_context("日线", daily_stage),
        "wave_combo_context": f"{method} 组合：{_describe_setup_tag(setup_tag)}；{_render_combo_reason(reason)}",
    }


def _render_stage_context(prefix: str, stage: MacdWaveStage) -> str:
    wave_label = _describe_wave_phase(stage)
    odd_push = _describe_odd_push_stage(stage.odd_push_stage)
    parts = [prefix, wave_label]
    if odd_push:
        parts.append(odd_push)
    if stage.bottom_divergence_valid is True:
        parts.append("左侧底背离有效")
    elif stage.bottom_divergence_valid is False:
        parts.append("左侧底背离未成立")
    if stage.reason:
        parts.append(stage.reason)
    return "，".join(parts)


def _describe_wave_phase(stage: MacdWaveStage) -> str:
    if stage.current_opportunity_phase == "pre_odd_imminent":
        wave_name = "预备奇数浪" if stage.current_wave_index <= 1 else f"预备{_wave_number_to_cn(stage.current_wave_index)}浪"
        return f"{wave_name}金叉临近"
    if stage.wave_cycle_phase == "pre_odd_pushing":
        wave_name = "预备奇数浪" if stage.current_wave_index <= 1 else f"预备{_wave_number_to_cn(stage.current_wave_index)}浪"
        return f"{wave_name}启动"
    mapping = {
        "waiting": "水下等待",
        "pre_odd_adjusting": "预备奇数浪调整",
        "odd_confirmed": f"{_wave_number_to_cn(stage.current_wave_index)}浪确认" if stage.current_wave_index > 0 else "奇数浪确认",
        "even_adjusting": "偶数浪调整",
        "even_repairing": "偶数浪修复",
        "cycle_ended": "本轮周期结束",
    }
    return mapping.get(stage.wave_cycle_phase, stage.wave_cycle_phase)


def _describe_odd_push_stage(stage_name: str) -> str:
    mapping = {
        "stage1_hist_dominant": "柱体主导强化阶段",
        "stage2_line_extending": "线体延伸阶段",
        "stage3_hist_lagging": "推进后段",
    }
    return mapping.get(stage_name, "")


def _describe_setup_tag(tag: str) -> str:
    mapping = {
        "pre_wave3_imminent": "预备三浪金叉临近",
        "pre_odd_imminent": "预备奇数浪金叉临近",
        "even_repairing": "偶数浪修复观察窗口",
        "odd_stage3_late": "奇数浪推进后段",
        "cycle_ended": "周期结束低分段",
    }
    return mapping.get(tag, tag.replace("__", " / "))


def _wave_number_to_cn(wave_index: int) -> str:
    mapping = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
    }
    return mapping.get(wave_index, str(wave_index))


def _render_combo_reason(reason: str) -> str:
    replacements = {
        "setup=pre_wave3_imminent": "形态=预备三浪金叉临近",
        "setup=pre_odd_imminent": "形态=预备奇数浪金叉临近",
        "setup=even_repairing": "形态=偶数浪修复观察窗口",
        "setup=odd_stage3_late": "形态=奇数浪推进后段",
        "weekly=odd_confirmed:stage1_hist_dominant": "周线=奇数浪确认/柱体主导强化阶段",
        "weekly=odd_confirmed:stage2_line_extending": "周线=奇数浪确认/线体延伸阶段",
        "weekly=odd_confirmed:stage3_hist_lagging": "周线=奇数浪确认/推进后段",
        "weekly=even_repairing:not_applicable": "周线=偶数浪修复",
        "weekly=waiting:not_applicable": "周线=水下等待",
        "daily=even_repairing:pre_odd_imminent:not_applicable": "日线=偶数浪修复/预备奇数浪金叉临近",
        "daily=odd_confirmed:not_applicable:stage3_hist_lagging": "日线=奇数浪确认/推进后段",
        "left_bottom_divergence": "左侧底背离支持",
        "risk=bottom_divergence_valid": "风险标记=底背离有效",
    }
    rendered = reason
    for source, target in replacements.items():
        rendered = rendered.replace(source, target)
    return rendered


def compute_weekly_and_daily_stages(history: pd.DataFrame) -> MacdWaveScoreInputs:
    daily_macd = macd_waves_module.compute_macd(history[["close"]].astype(float))
    daily_state = classify_macd_state_from_lines(daily_macd[["dif", "dea"]])
    daily_stage = derive_macd_wave_stage(
        daily_state,
        latest_dif=float(daily_macd.iloc[-1]["dif"]),
        latest_dea=float(daily_macd.iloc[-1]["dea"]),
        latest_hist=float((daily_macd.iloc[-1]["dif"] - daily_macd.iloc[-1]["dea"]) * 2.0),
        previous_odd_peak_value=daily_state.H,
    )

    weekly_close = (
        history.assign(trade_date=pd.to_datetime(history["trade_date"]))
        .set_index("trade_date")["close"]
        .astype(float)
        .resample("W-FRI")
        .last()
        .dropna()
    )
    weekly_macd = macd_waves_module.compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    weekly_state = classify_macd_state_from_lines(weekly_macd[["dif", "dea"]])
    weekly_stage = derive_macd_wave_stage(
        weekly_state,
        latest_dif=float(weekly_macd.iloc[-1]["dif"]),
        latest_dea=float(weekly_macd.iloc[-1]["dea"]),
        latest_hist=float((weekly_macd.iloc[-1]["dif"] - weekly_macd.iloc[-1]["dea"]) * 2.0),
        previous_odd_peak_value=weekly_state.H,
    )
    return MacdWaveScoreInputs(weekly_stage=weekly_stage, daily_stage=daily_stage)


def score_macd_review_context_from_history(
    history: pd.DataFrame,
    *,
    method: str,
    signal: str,
    environment_state: str | None = None,
) -> MacdScoreBreakdown:
    stages = compute_weekly_and_daily_stages(history)
    return score_macd_state_machine_combo(
        method=method,
        weekly_stage=stages.weekly_stage,
        daily_stage=stages.daily_stage,
        signal=signal,
        environment_state=environment_state,
    )
