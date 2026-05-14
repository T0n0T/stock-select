from __future__ import annotations

import pytest

from stock_select.analysis.macd_waves import MacdStateMachineResult
from stock_select.analysis.macd_wave_score import (
    _score_daily_stage,
    _score_weekly_stage,
    _weekly_coefficient,
    classify_daily_grade,
    classify_weekly_grade,
    derive_macd_wave_stage,
    load_macd_wave_score_grade_table,
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
    assert stage.supports_first_even_repair_window is False


def test_waiting_underwater_maps_to_waiting_phase() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.12,
        latest_dea=-0.08,
        latest_hist=-0.08,
    )

    assert stage.wave_cycle_phase == "waiting"
    assert stage.waiting_strength_tier == "waiting_flat"


def test_waiting_underwater_with_positive_dif_is_underwater_ready() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )

    assert stage.wave_cycle_phase == "waiting"
    assert stage.waiting_strength_tier == "underwater_ready"


def test_waiting_underwater_with_negative_dif_but_positive_hist_is_underwater_strengthening() -> None:
    stage = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.08,
        latest_dea=-0.14,
        latest_hist=0.12,
    )

    assert stage.wave_cycle_phase == "waiting"
    assert stage.waiting_strength_tier == "underwater_strengthening"


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
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    assert stage.wave_cycle_phase == "even_repairing"
    assert stage.supports_first_even_repair_window is True


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


def test_even_repairing_with_weekly_pre_odd_push_and_bottom_divergence_scores_above_plain_even_repair() -> None:
    strong_weekly = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    weak_weekly = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.03,
        latest_dea=-0.02,
        latest_hist=-0.02,
    )
    daily_with_divergence = derive_macd_wave_stage(
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
    plain_daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    stronger = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=strong_weekly,
        daily_stage=daily_with_divergence,
        signal="B2",
    )
    weaker = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weak_weekly,
        daily_stage=plain_daily,
        signal="B2",
    )

    assert stronger.score_1_to_5 > weaker.score_1_to_5
    assert stronger.score_1_to_5 < 3.8


def test_pre_odd_adjusting_with_bottom_divergence_does_not_score_above_even_repairing_window() -> None:
    weekly_odd_confirmed = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=1, current_wave_macd_max=0.5),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    pre_odd_adjusting = derive_macd_wave_stage(
        _state(
            current_state="pre_odd_adjusting",
            current_wave_index=3,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    even_repairing = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    pre_adjust_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_odd_confirmed,
        daily_stage=pre_odd_adjusting,
        signal="B2",
    )
    repair_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_odd_confirmed,
        daily_stage=even_repairing,
        signal="B2",
    )

    assert pre_adjust_score.score_1_to_5 < repair_score.score_1_to_5


def test_even_repairing_fail_compatible_case_stays_below_watch_like_repair_case() -> None:
    weekly_underwater = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.03,
        latest_dea=-0.02,
        latest_hist=-0.02,
    )
    fail_like_daily = derive_macd_wave_stage(
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
    watch_like_daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    weekly_strengthening = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )

    fail_like = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_underwater,
        daily_stage=fail_like_daily,
        signal="B2",
    )
    watch_like = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_strengthening,
        daily_stage=watch_like_daily,
        signal="B2",
    )

    assert fail_like.score_1_to_5 < watch_like.score_1_to_5


def test_even_repairing_strengthening_weekly_without_bottom_divergence_still_beats_fail_compatible_underwater_case() -> None:
    weekly_strengthening = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    weekly_underwater = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.03,
        latest_dea=-0.02,
        latest_hist=-0.02,
    )
    strengthening_daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    fail_compatible_daily = derive_macd_wave_stage(
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

    strengthening_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_strengthening,
        daily_stage=strengthening_daily,
        signal="B2",
    )
    fail_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_underwater,
        daily_stage=fail_compatible_daily,
        signal="B2",
    )

    assert strengthening_score.score_1_to_5 > fail_score.score_1_to_5


def test_first_even_repair_window_scores_above_later_repeated_even_repair_window() -> None:
    weekly_waiting = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.03,
        latest_dea=-0.02,
        latest_hist=-0.02,
    )
    first_repair = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    repeated_repair = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=4,
            even_repair_started=True,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    first_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_waiting,
        daily_stage=first_repair,
        signal="B2",
    )
    repeated_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_waiting,
        daily_stage=repeated_repair,
        signal="B2",
    )

    assert first_score.score_1_to_5 > repeated_score.score_1_to_5
    assert first_score.score_1_to_5 < 3.8


def test_even_repairing_with_unknown_bottom_divergence_scores_above_invalid_bottom_divergence() -> None:
    weekly_waiting = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.03,
        latest_dea=-0.02,
        latest_hist=-0.02,
    )
    unknown_divergence = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    invalid_divergence = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    unknown_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_waiting,
        daily_stage=unknown_divergence,
        signal="B2",
    )
    invalid_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_waiting,
        daily_stage=invalid_divergence,
        signal="B2",
    )

    assert unknown_score.score_1_to_5 > invalid_score.score_1_to_5


def test_repeated_even_repair_with_bottom_divergence_does_not_beat_first_even_repair_without_confirmation() -> None:
    weekly_waiting = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.03,
        latest_dea=-0.02,
        latest_hist=-0.02,
    )
    first_repair_unknown = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    repeated_repair_bottom_divergence = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=5,
            even_repair_started=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    first_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_waiting,
        daily_stage=first_repair_unknown,
        signal="B2",
    )
    repeated_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_waiting,
        daily_stage=repeated_repair_bottom_divergence,
        signal="B2",
    )

    assert first_score.score_1_to_5 > repeated_score.score_1_to_5


def test_even_repairing_with_underwater_ready_weekly_scores_above_underwater_flat_weekly() -> None:
    weekly_ready = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )
    weekly_flat = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.12,
        latest_dea=-0.08,
        latest_hist=-0.08,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=4,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    ready_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_ready,
        daily_stage=daily,
        signal="B2",
    )
    flat_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_flat,
        daily_stage=daily,
        signal="B2",
    )

    assert ready_score.score_1_to_5 > flat_score.score_1_to_5


def test_even_repairing_with_underwater_ready_weekly_scores_above_underwater_strengthening_weekly() -> None:
    weekly_ready = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )
    weekly_strengthening = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.08,
        latest_dea=-0.14,
        latest_hist=0.12,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=4,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    ready_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_ready,
        daily_stage=daily,
        signal="B2",
    )
    strengthening_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_strengthening,
        daily_stage=daily,
        signal="B2",
    )

    assert ready_score.score_1_to_5 > strengthening_score.score_1_to_5


def test_weekly_grade_order_follows_user_ranking() -> None:
    waiting_flat = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.12,
        latest_dea=-0.08,
        latest_hist=-0.08,
    )
    underwater_strengthening = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.08,
        latest_dea=-0.14,
        latest_hist=0.12,
    )
    underwater_ready = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )
    even_adjusting = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=False),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    even_repairing = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    pre_odd_adjusting = derive_macd_wave_stage(
        _state(current_state="pre_odd_adjusting", current_wave_index=3),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    pre_odd_pushing = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    odd_stage1 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    odd_stage2 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.20,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    odd_stage3 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.30,
        latest_dea=0.20,
        latest_hist=0.05,
    )
    cycle_ended = derive_macd_wave_stage(
        _state(current_state="waiting_underwater", events=("cycle_ended",), reason="dea crossed back under zero"),
        latest_dif=-0.02,
        latest_dea=-0.01,
        latest_hist=-0.02,
    )

    assert _weekly_coefficient(waiting_flat) <= _weekly_coefficient(underwater_strengthening)
    assert _weekly_coefficient(underwater_strengthening) < _weekly_coefficient(underwater_ready)
    assert _weekly_coefficient(underwater_ready) < _weekly_coefficient(even_adjusting)
    assert _weekly_coefficient(pre_odd_adjusting) < _weekly_coefficient(pre_odd_pushing)
    assert _weekly_coefficient(even_adjusting) <= _weekly_coefficient(even_repairing)
    assert _weekly_coefficient(odd_stage1) > _weekly_coefficient(odd_stage2) > _weekly_coefficient(odd_stage3)
    assert _weekly_coefficient(cycle_ended) <= _weekly_coefficient(waiting_flat)


def test_daily_grade_order_follows_user_ranking() -> None:
    waiting = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.12,
        latest_dea=-0.08,
        latest_hist=-0.08,
    )
    even_adjusting = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=False),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    even_repairing_plain = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True, bottom_divergence_valid=None),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    even_repairing_first = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, valid_odd_wave_count=1, even_repair_started=True, bottom_divergence_valid=None),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    pre_odd_adjusting = derive_macd_wave_stage(
        _state(current_state="pre_odd_adjusting", current_wave_index=3),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )
    pre_odd_pushing = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    pre_wave3 = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True, golden_cross_imminent=True),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )
    odd_stage1 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    odd_stage2 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.20,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    odd_stage3 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
        latest_dif=0.30,
        latest_dea=0.20,
        latest_hist=0.05,
    )
    cycle_ended = derive_macd_wave_stage(
        _state(current_state="waiting_underwater", events=("cycle_ended",), reason="dea crossed back under zero"),
        latest_dif=-0.02,
        latest_dea=-0.01,
        latest_hist=-0.02,
    )

    assert _score_daily_stage(waiting) < _score_daily_stage(even_adjusting)
    assert _score_daily_stage(even_adjusting) <= _score_daily_stage(even_repairing_plain)
    assert _score_daily_stage(even_repairing_plain) < _score_daily_stage(even_repairing_first)
    assert _score_daily_stage(pre_odd_adjusting) <= _score_daily_stage(even_repairing_plain)
    assert _score_daily_stage(pre_odd_pushing) > _score_daily_stage(pre_odd_adjusting)
    assert _score_daily_stage(pre_wave3) > _score_daily_stage(pre_odd_pushing)
    assert _score_daily_stage(odd_stage1) > _score_daily_stage(odd_stage2) > _score_daily_stage(odd_stage3)
    assert _score_daily_stage(cycle_ended) <= _score_daily_stage(waiting)


def test_weekly_grade_labels_follow_user_table() -> None:
    assert classify_weekly_grade(
        derive_macd_wave_stage(
            _state(current_state="waiting_underwater"),
            latest_dif=-0.12,
            latest_dea=-0.08,
            latest_hist=-0.08,
        )
    ) == "很差"
    assert classify_weekly_grade(
        derive_macd_wave_stage(
            _state(current_state="waiting_underwater"),
            latest_dif=0.09,
            latest_dea=-0.02,
            latest_hist=0.22,
        )
    ) == "差"
    assert classify_weekly_grade(
        derive_macd_wave_stage(
            _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True),
            latest_dif=0.05,
            latest_dea=0.09,
            latest_hist=-0.08,
        )
    ) == "中"
    assert classify_weekly_grade(
        derive_macd_wave_stage(
            _state(current_state="pre_wave1_pushing", current_wave_index=0),
            latest_dif=0.05,
            latest_dea=0.03,
            latest_hist=0.08,
        )
    ) == "很好"
    assert classify_weekly_grade(
        derive_macd_wave_stage(
            _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.2),
            latest_dif=0.20,
            latest_dea=0.03,
            latest_hist=0.08,
        )
    ) == "好"


def test_daily_grade_labels_follow_user_table() -> None:
    assert classify_daily_grade(
        derive_macd_wave_stage(
            _state(current_state="waiting_underwater"),
            latest_dif=-0.12,
            latest_dea=-0.08,
            latest_hist=-0.08,
        )
    ) == "很差"
    assert classify_daily_grade(
        derive_macd_wave_stage(
            _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=False),
            latest_dif=0.05,
            latest_dea=0.09,
            latest_hist=-0.08,
        )
    ) == "差"
    assert classify_daily_grade(
        derive_macd_wave_stage(
            _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True, bottom_divergence_valid=None),
            latest_dif=0.05,
            latest_dea=0.09,
            latest_hist=-0.08,
        )
    ) == "中"
    assert classify_daily_grade(
        derive_macd_wave_stage(
            _state(current_state="even_wave_forming", current_wave_index=2, valid_odd_wave_count=1, even_repair_started=True, bottom_divergence_valid=None),
            latest_dif=0.05,
            latest_dea=0.09,
            latest_hist=-0.08,
        )
    ) == "好"
    assert classify_daily_grade(
        derive_macd_wave_stage(
            _state(current_state="even_wave_forming", current_wave_index=2, even_repair_started=True, golden_cross_imminent=True),
            latest_dif=0.09,
            latest_dea=0.08,
            latest_hist=-0.01,
        )
    ) == "很好"


def test_load_macd_wave_score_grade_table_reads_research_mapping() -> None:
    table = load_macd_wave_score_grade_table()

    default_weekly = table["weekly_coeff"]["default"]
    assert 0 < default_weekly["很差"] < default_weekly["差"] < default_weekly["中"] < default_weekly["好"] < default_weekly["很好"]
    assert table["daily"]["很差"] < table["daily"]["差"] < table["daily"]["中"] < table["daily"]["好"] < table["daily"]["很好"]


def test_score_functions_follow_grade_table_values() -> None:
    table = load_macd_wave_score_grade_table()
    weekly_ready = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )
    daily_first_repair = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, valid_odd_wave_count=1, even_repair_started=True),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    assert _weekly_coefficient(weekly_ready) == table["weekly_coeff"]["default"]["差"]
    assert _score_weekly_stage(weekly_ready, daily_base_score=table["daily"]["好"]) == pytest.approx(
        table["daily"]["好"] * table["weekly_coeff"]["default"]["差"]
    )
    assert _score_daily_stage(daily_first_repair) == table["daily"]["好"]


def test_environment_state_strong_lifts_same_setup_above_default_and_weak() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )
    daily = derive_macd_wave_stage(
        _state(current_state="even_wave_forming", current_wave_index=2, valid_odd_wave_count=1, even_repair_started=True),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    weak_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B2",
        environment_state="weak",
    )
    default_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B2",
    )
    strong_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B2",
        environment_state="strong",
    )

    assert weak_score.score_1_to_5 < default_score.score_1_to_5 < strong_score.score_1_to_5


def test_environment_state_weak_suppresses_pre_wave3_imminent_score() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
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

    weak_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B3",
        environment_state="weak",
    )
    strong_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B3",
        environment_state="strong",
    )

    assert weak_score.score_1_to_5 < strong_score.score_1_to_5
    assert weak_score.score_1_to_5 < 4.5


def test_environment_state_strong_promotes_first_even_repair_into_three_point_five_plus_band() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    strong_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B2",
        environment_state="strong",
    )

    assert strong_score.score_1_to_5 >= 3.5


def test_environment_state_strong_pre_wave3_does_not_saturate_to_five() -> None:
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

    strong_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B3",
        environment_state="strong",
    )

    assert strong_score.score_1_to_5 < 4.9


def test_environment_state_weak_penalizes_pre_odd_imminent_other_more_than_pre_wave3() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
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
    pre_wave5 = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=4,
            even_repair_started=True,
            golden_cross_imminent=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.09,
        latest_dea=0.08,
        latest_hist=-0.01,
    )

    weak_wave3 = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=pre_wave3,
        signal="B3",
        environment_state="weak",
    )
    weak_wave5 = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=pre_wave5,
        signal="B3",
        environment_state="weak",
    )

    assert weak_wave5.score_1_to_5 < weak_wave3.score_1_to_5
    assert weak_wave5.score_1_to_5 < 4.0


def test_environment_state_weak_penalizes_odd_confirmed_stage1_plus_pre_wave3_combo() -> None:
    weekly_odd_confirmed = derive_macd_wave_stage(
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

    weak_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_odd_confirmed,
        daily_stage=daily,
        signal="B2",
        environment_state="weak",
    )

    assert weak_score.score_1_to_5 < 4.2


def test_environment_state_weak_penalizes_pre_odd_pushing_plus_pre_wave3_combo() -> None:
    weekly_pre_odd = derive_macd_wave_stage(
        _state(current_state="pre_wave1_pushing", current_wave_index=0),
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

    weak_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_pre_odd,
        daily_stage=daily,
        signal="B2",
        environment_state="weak",
    )

    assert weak_score.score_1_to_5 < 4.2


def test_environment_state_weak_keeps_first_even_repair_observation_band_above_two_point_nine() -> None:
    weekly = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=0.09,
        latest_dea=-0.02,
        latest_hist=0.22,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    weak_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly,
        daily_stage=daily,
        signal="B2",
        environment_state="weak",
    )

    assert weak_score.score_1_to_5 >= 2.9


def test_weekly_stage3_plus_pre_wave3_scores_below_stage1_plus_pre_wave3() -> None:
    weekly_stage1 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.5),
        latest_dif=0.05,
        latest_dea=0.03,
        latest_hist=0.08,
    )
    weekly_stage3 = derive_macd_wave_stage(
        _state(current_state="odd_wave_forming", current_wave_index=3, current_wave_macd_max=0.5),
        latest_dif=0.30,
        latest_dea=0.20,
        latest_hist=0.05,
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

    strong_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_stage1,
        daily_stage=daily,
        signal="B2",
        environment_state="strong",
    )
    late_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_stage3,
        daily_stage=daily,
        signal="B2",
        environment_state="strong",
    )

    assert late_score.score_1_to_5 < strong_score.score_1_to_5


def test_high_order_pre_odd_push_plus_pre_wave3_stays_below_four_point_three() -> None:
    weekly_high_order = derive_macd_wave_stage(
        _state(current_state="pre_odd_pushing", current_wave_index=4),
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

    score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_high_order,
        daily_stage=daily,
        signal="B2",
        environment_state="strong",
    )

    assert score.score_1_to_5 < 4.3


def test_late_odd_wave_penalty_keeps_high_order_confirmed_combo_below_mid_four_band() -> None:
    weekly_late = derive_macd_wave_stage(
        _state(
            current_state="odd_wave_forming",
            current_wave_index=9,
            current_wave_macd_max=0.8,
            events=("current_odd_peak_confirmed",),
        ),
        latest_dif=0.20,
        latest_dea=0.03,
        latest_hist=0.08,
        previous_odd_peak_value=1.0,
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

    score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_late,
        daily_stage=daily,
        signal="B2",
        environment_state="neutral",
    )

    assert score.score_1_to_5 < 4.4


def test_even_repairing_with_bottom_divergence_true_and_underwater_strengthening_weekly_beats_bottom_divergence_true_with_flat_weekly() -> None:
    weekly_strengthening = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.08,
        latest_dea=-0.14,
        latest_hist=0.12,
    )
    weekly_flat = derive_macd_wave_stage(
        _state(current_state="waiting_underwater"),
        latest_dif=-0.12,
        latest_dea=-0.08,
        latest_hist=-0.08,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=5,
            even_repair_started=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.03,
        latest_dea=0.05,
        latest_hist=-0.04,
    )

    strengthening_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_strengthening,
        daily_stage=daily,
        signal="B2",
    )
    flat_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_flat,
        daily_stage=daily,
        signal="B2",
    )

    assert strengthening_score.score_1_to_5 > flat_score.score_1_to_5


def test_weekly_bottom_divergence_invalid_penalizes_same_setup() -> None:
    weekly_valid = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    weekly_invalid = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    valid_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_valid,
        daily_stage=daily,
        signal="B2",
    )
    invalid_score = score_macd_state_machine_combo(
        method="b2",
        weekly_stage=weekly_invalid,
        daily_stage=daily,
        signal="B2",
    )

    assert invalid_score.score_1_to_5 < valid_score.score_1_to_5


def test_weekly_bottom_divergence_signal_changes_weekly_coefficient_not_daily_base() -> None:
    weekly_valid = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    weekly_invalid = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    daily = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    assert _score_daily_stage(daily) == _score_daily_stage(daily)
    assert _weekly_coefficient(weekly_invalid) < _weekly_coefficient(weekly_valid)


def test_daily_bottom_divergence_signal_changes_daily_base_not_weekly_coefficient() -> None:
    weekly = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            even_repair_started=True,
            bottom_divergence_valid=None,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    daily_valid = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=True,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )
    daily_invalid = derive_macd_wave_stage(
        _state(
            current_state="even_wave_forming",
            current_wave_index=2,
            valid_odd_wave_count=1,
            even_repair_started=True,
            bottom_divergence_valid=False,
        ),
        latest_dif=0.05,
        latest_dea=0.09,
        latest_hist=-0.08,
    )

    assert _weekly_coefficient(weekly) == _weekly_coefficient(weekly)
    assert _score_daily_stage(daily_valid) > _score_daily_stage(daily_invalid)


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
