from __future__ import annotations

import pytest

from stock_select.analysis.macd_waves import MacdStateMachineResult
from stock_select.analysis.macd_wave_score import (
    derive_macd_wave_stage,
    render_macd_score_review_context,
    score_macd_state_machine_combo,
)


def _state(**overrides: object) -> MacdStateMachineResult:
    defaults: dict[str, object] = {
        "current_state": "waiting_underwater",
        "current_wave_index": 0,
        "valid_odd_wave_count": 0,
        "H": None,
        "L": None,
        "baseline_H": None,
        "pre_odd_macd_max": None,
        "current_wave_macd_max": None,
        "current_even_macd_min": None,
        "current_even_L": None,
        "prev_even_L": None,
        "even_repair_started": False,
        "golden_cross_imminent": False,
        "bottom_divergence_valid": None,
        "events": (),
        "reason": "test",
    }
    defaults.update(overrides)
    return MacdStateMachineResult(**defaults)


def test_pre_odd_pushing_keeps_current_opportunity_even_without_baseline_breakout() -> None:
    stage = derive_macd_wave_stage(
        _state(
            current_state="pre_odd_pushing",
            current_wave_index=2,
            baseline_H=0.8,
            pre_odd_macd_max=0.2,
            current_wave_macd_max=None,
        ),
        latest_dif=0.12,
        latest_dea=0.08,
        latest_hist=0.08,
        previous_odd_peak_value=0.8,
    )

    assert stage.wave_cycle_phase == "pre_odd_pushing"
    assert stage.current_wave_index == 3
    assert stage.current_opportunity_phase == "pre_odd_starting"
    assert stage.history_confirmed is False
    assert "baseline_pending" in stage.risk_flags


def test_waiting_underwater_maps_to_waiting_phase() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.12,
        latest_dea=-0.08,
        latest_hist=-0.08,
    )

    assert stage.wave_cycle_phase == "waiting"


def test_even_wave_without_repair_is_even_adjusting() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=False),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    assert stage.wave_cycle_phase == "even_adjusting"


def test_even_wave_with_repair_is_even_repairing() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    assert stage.wave_cycle_phase == "even_repairing"


def test_even_wave_with_golden_cross_imminent_maps_to_pre_odd_imminent() -> None:
    stage = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )

    assert stage.wave_cycle_phase == "even_repairing"
    assert stage.current_opportunity_phase == "pre_odd_imminent"
    assert stage.current_wave_index == 3


def test_odd_wave_forming_maps_to_odd_confirmed() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.22,
        latest_dea=0.12,
        latest_hist=0.2,
    )

    assert stage.wave_cycle_phase == "odd_confirmed"
    assert stage.history_confirmed is True


def test_waiting_underwater_with_cycle_ended_event_stays_waiting_not_latest_active_cycle() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="waiting_underwater", events=("cycle_ended",)),
        latest_dif=-0.20,
        latest_dea=-0.10,
        latest_hist=-0.20,
    )

    assert stage.wave_cycle_phase == "waiting"


def test_prior_cycle_ended_event_does_not_override_current_even_repairing_state() -> None:
    stage = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
            events=("cycle_ended", "even_wave_started", "even_repair_started", "golden_cross_imminent"),
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )

    assert stage.wave_cycle_phase == "even_repairing"
    assert stage.current_opportunity_phase == "pre_odd_imminent"


def test_odd_push_stage1_hist_dominant() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )

    assert stage.odd_push_stage == "stage1_hist_dominant"


def test_odd_push_stage3_hist_lagging() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.30,
        latest_dea=0.20,
        latest_hist=0.05,
    )

    assert stage.odd_push_stage == "stage3_hist_lagging"


def test_strengthening_phase_does_not_evaluate_top_divergence() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.6),
        latest_dif=0.06,
        latest_dea=0.04,
        latest_hist=0.10,
        previous_odd_peak_value=0.8,
    )

    assert stage.top_divergence_evaluable is False
    assert stage.top_divergence_level == "none"


def test_b_level_top_divergence_requires_current_peak_confirmed() -> None:
    stage = derive_macd_wave_stage(
        _state(
            current_state="odd_wave_forming",
            current_wave_index=5,
            current_wave_macd_max=0.5,
            events=("current_odd_peak_confirmed",),
        ),
        latest_dif=0.28,
        latest_dea=0.14,
        latest_hist=0.06,
        previous_odd_peak_value=0.8,
    )

    assert stage.top_divergence_evaluable is True
    assert stage.current_odd_peak_confirmed is True
    assert stage.top_divergence_level == "B"


def test_b_level_top_divergence_not_set_without_confirmed_peak() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=5, current_wave_macd_max=0.5),
        latest_dif=0.28,
        latest_dea=0.14,
        latest_hist=0.06,
        previous_odd_peak_value=0.8,
    )

    assert stage.current_odd_peak_confirmed is False
    assert stage.top_divergence_level != "B"


@pytest.mark.parametrize(
    ("state", "latest_dif", "latest_dea", "latest_hist"),
    [
        (_state(current_state="waiting_underwater"), -0.10, -0.08, -0.04),
        (_state(current_state="waiting_underwater", events=("cycle_ended",), reason="dea crossed back under zero"), -0.02, -0.01, -0.02),
    ],
)
def test_dea_reentering_underwater_is_cycle_ended_not_c_level_divergence(
    state: MacdStateMachineResult,
    latest_dif: float,
    latest_dea: float,
    latest_hist: float,
) -> None:
    stage = derive_macd_wave_stage(
        state,
        latest_dif=latest_dif,
        latest_dea=latest_dea,
        latest_hist=latest_hist,
        previous_odd_peak_value=0.8,
    )

    assert stage.wave_cycle_phase in {"waiting", "cycle_ended"}
    assert stage.top_divergence_level != "C"


def test_highest_score_prefers_daily_pre_wave3_imminent_weekly_strengthening_with_left_divergence() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=1, current_wave_macd_max=0.5),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )

    score = score_macd_state_machine_combo(method="b2", weekly_stage=weekly, daily_stage=daily, signal="B3")

    assert score.score_1_to_5 >= 4.7
    assert score.setup_tag == "pre_wave3_imminent"
    assert "bottom_divergence_valid" in score.risk_flags or "left_bottom_divergence" in score.reason


def test_same_setup_without_bottom_divergence_scores_lower() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=1, current_wave_macd_max=0.5),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    daily_with_divergence = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )
    daily_without_divergence = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )

    high_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily_with_divergence,
        signal="B3",
    )
    lower_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily_without_divergence,
        signal="B3",
    )

    assert lower_score.score_1_to_5 < high_score.score_1_to_5


def test_daily_odd_confirmed_stage3_scores_lower_than_pre_wave3_imminent() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=1, current_wave_macd_max=0.5),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    pre_wave3 = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )
    late_odd = derive_macd_wave_stage(
        _state(
            current_state="odd_wave_forming",
            current_wave_index=3,
            current_wave_macd_max=0.35,
            events=("current_odd_peak_confirmed",),
        ),
        latest_dif=0.30,
        latest_dea=0.20,
        latest_hist=0.05,
        previous_odd_peak_value=0.40,
    )

    high_score = score_macd_state_machine_combo(method="b2", weekly_stage=weekly, daily_stage=pre_wave3, signal="B3")
    lower_score = score_macd_state_machine_combo(method="b2", weekly_stage=weekly, daily_stage=late_odd, signal="B3")

    assert lower_score.score_1_to_5 < high_score.score_1_to_5


def test_seven_wave_or_higher_cannot_score_five() -> None:
    weekly = derive_macd_wave_stage(
        _state(
            current_state="odd_wave_forming",
            current_wave_index=7,
            current_wave_macd_max=0.8,
            events=("current_odd_peak_confirmed",),
        ),
        latest_dif=0.25,
        latest_dea=0.14,
        latest_hist=0.04,
        previous_odd_peak_value=1.0,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=6,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )

    score = score_macd_state_machine_combo(method="b2", weekly_stage=weekly, daily_stage=daily, signal="B3")

    assert score.score_1_to_5 < 5.0


def test_cycle_ended_scores_below_two_point_five() -> None:
    ended = derive_macd_wave_stage(
        _state(current_state="waiting_underwater", events=("cycle_ended",)),
        latest_dif=-0.10,
        latest_dea=-0.08,
        latest_hist=-0.04,
    )

    score = score_macd_state_machine_combo(method="b2", weekly_stage=ended, daily_stage=ended, signal="B3")

    assert score.score_1_to_5 < 2.5


def test_b1_favors_even_repair_more_than_b2_for_same_setup() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True),
        latest_dif=0.04,
        latest_dea=0.06,
        latest_hist=-0.04,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    b1_score = score_macd_state_machine_combo(method="b1", weekly_stage=weekly, daily_stage=daily, signal="B1")
    b2_score = score_macd_state_machine_combo(method="b2", weekly_stage=weekly, daily_stage=daily, signal="B1")

    assert b1_score.score_1_to_5 > b2_score.score_1_to_5


def test_dribull_penalizes_weak_weekly_context_more_than_b2() -> None:
    weak_weekly = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.03,
        latest_dea=-0.02,
        latest_hist=-0.02,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )

    dribull_score = score_macd_state_machine_combo(
        method="dribull",
        weekly_stage=weak_weekly,
        daily_stage=daily,
        signal="B3",
    )
    b2_score = score_macd_state_machine_combo(method="b2", weekly_stage=weak_weekly, daily_stage=daily, signal="B3")

    assert dribull_score.score_1_to_5 < b2_score.score_1_to_5


def test_review_context_includes_weekly_daily_and_combo_in_chinese() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=1, current_wave_macd_max=0.5),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )
    score = score_macd_state_machine_combo(method="b2", weekly_stage=weekly, daily_stage=daily, signal="B3")

    context = render_macd_score_review_context(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        score=score,
    )

    assert "周线" in context["weekly_wave_context"]
    assert "柱体主导强化阶段" in context["weekly_wave_context"]
    assert "日线" in context["daily_wave_context"]
    assert "预备三浪金叉临近" in context["daily_wave_context"]
    assert "b2" in context["wave_combo_context"]
    assert "pre_wave3_imminent" not in context["wave_combo_context"]


def test_review_context_uses_even_repairing_and_stage3_chinese_labels() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True),
        latest_dif=0.04,
        latest_dea=0.06,
        latest_hist=-0.04,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="odd_wave_forming",
            current_wave_index=3,
            current_wave_macd_max=0.35,
            events=("current_odd_peak_confirmed",),
        ),
        latest_dif=0.30,
        latest_dea=0.20,
        latest_hist=0.05,
        previous_odd_peak_value=0.40,
    )
    score = score_macd_state_machine_combo(method="b2", weekly_stage=weekly, daily_stage=daily, signal="B3")

    context = render_macd_score_review_context(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        score=score,
    )

    assert "偶数浪修复" in context["weekly_wave_context"]
    assert "推进后段" in context["daily_wave_context"]
    assert "stage3_hist_lagging" not in context["daily_wave_context"]
