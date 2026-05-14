import pandas as pd
import pytest

from stock_select.analysis.macd_waves import (
    _classify_macd_trend_from_lines,
    classify_daily_macd_state,
    classify_daily_macd_trend,
    classify_macd_state_from_lines,
    classify_daily_macd_wave,
    classify_weekly_macd_trend,
    classify_weekly_macd_wave,
)


def _frame_with_close(close: list[float], *, start: str = "2026-01-05") -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=len(close))
    return pd.DataFrame({"trade_date": dates, "close": close})


def _frame_from_weekly_close(weekly_close: list[float], *, start: str = "2025-01-03") -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=len(weekly_close), freq="W-FRI")
    return pd.DataFrame({"trade_date": dates, "close": weekly_close})


def _line_frame(dif: list[float], dea: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"dif": dif, "dea": dea})


def test_public_daily_macd_trend_uses_state_machine_even_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = _line_frame(
        dif=[
            0.20,
            0.24,
            0.20,
            -0.30,
            -0.20,
            -0.08,
            0.12,
            0.26,
            0.34,
            0.22,
            0.12,
            0.03,
            0.07,
            0.18,
            0.32,
            0.44,
            0.54,
            0.42,
            0.28,
            0.10,
            0.04,
            0.09,
        ],
        dea=[
            0.10,
            0.11,
            0.12,
            -0.28,
            -0.22,
            -0.10,
            0.06,
            0.13,
            0.20,
            0.22,
            0.18,
            0.12,
            0.10,
            0.11,
            0.18,
            0.26,
            0.36,
            0.42,
            0.36,
            0.18,
            0.11,
            0.12,
        ],
    )
    monkeypatch.setattr("stock_select.analysis.macd_waves.compute_macd", lambda _frame: lines)

    result = classify_daily_macd_trend(_frame_with_close([10.0] * len(lines)), "2026-02-03")

    assert result.phase == "falling"
    assert result.direction == "falling"
    assert result.phase_index == 4
    assert result.wave_label == "四浪"
    assert result.wave_stage == "修复"
    assert result.metrics["state_machine_state"] == "even_wave_forming"
    assert result.metrics["bottom_divergence_valid"] is True
    assert "even wave repair" in result.reason


def test_public_daily_macd_trend_marks_imminent_odd_start(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = _line_frame(
        dif=[
            0.50,
            0.58,
            0.50,
            -0.30,
            -0.20,
            -0.08,
            0.10,
            0.08,
            -0.04,
            -0.30,
            -0.20,
            -0.08,
            0.09,
            0.13,
            0.16,
            0.14,
            0.10,
            0.09,
            0.085,
        ],
        dea=[
            0.20,
            0.23,
            0.26,
            -0.28,
            -0.22,
            -0.10,
            0.04,
            0.06,
            -0.01,
            -0.28,
            -0.22,
            -0.10,
            0.04,
            0.08,
            0.12,
            0.125,
            0.13,
            0.105,
            0.0925,
        ],
    )
    monkeypatch.setattr("stock_select.analysis.macd_waves.compute_macd", lambda _frame: lines)

    result = classify_daily_macd_trend(_frame_with_close([10.0] * len(lines)), "2026-01-29")

    assert result.phase == "falling"
    assert result.phase_index == 2
    assert result.wave_label == "二浪"
    assert result.wave_stage == "金叉临近"
    assert "golden cross imminent" in result.reason


def test_macd_state_machine_rebases_h_after_failed_pre_wave_push() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.58,
                0.62,
                0.58,
                -0.30,
                -0.20,
                -0.08,
                0.08,
                0.12,
                0.08,
                -0.02,
                0.03,
                0.18,
                0.32,
                0.35,
            ],
            dea=[
                0.40,
                0.43,
                0.46,
                -0.28,
                -0.22,
                -0.10,
                0.04,
                0.06,
                0.08,
                0.04,
                0.02,
                0.09,
                0.18,
                0.24,
            ],
        )
    )

    assert result.current_state == "odd_wave_forming"
    assert result.current_wave_index == 1
    assert result.valid_odd_wave_count == 1
    assert result.baseline_H == 0.12
    assert result.current_wave_macd_max == 0.28
    assert result.events.count("pre_odd_failed_rebase_H") == 1
    assert "odd_wave_confirmed" in result.events


def test_macd_state_machine_uses_double_histogram_scale_for_internal_levels() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.20,
                0.24,
                0.20,
                -0.30,
                -0.20,
                -0.08,
                0.08,
                0.12,
                0.08,
                -0.02,
                0.03,
                0.18,
                0.32,
                0.35,
            ],
            dea=[
                0.10,
                0.14,
                0.16,
                -0.28,
                -0.22,
                -0.10,
                0.04,
                0.06,
                0.08,
                0.04,
                0.02,
                0.09,
                0.18,
                0.24,
            ],
        )
    )

    assert result.current_state == "odd_wave_forming"
    assert result.valid_odd_wave_count == 2
    assert result.baseline_H == 0.12
    assert result.current_wave_macd_max == 0.28


def test_macd_state_machine_rebases_failed_pre_wave_push_to_latest_failed_peak() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.50,
                0.55,
                0.55,
                -0.32,
                -0.20,
                -0.07,
                -0.13,
                -0.09,
                0.00,
                0.015,
                0.02,
            ],
            dea=[
                0.25,
                0.275,
                0.30,
                -0.28,
                -0.22,
                -0.16,
                -0.12,
                -0.10,
                -0.06,
                0.02,
                0.04,
            ],
        )
    )

    assert result.current_state == "pre_odd_adjusting"
    assert result.H == 0.12
    assert result.baseline_H == 0.12
    assert result.pre_odd_macd_max == -0.01
    assert result.events.count("pre_odd_failed_rebase_H") == 0


def test_macd_state_machine_identifies_even_repair_bottom_divergence() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.20,
                0.24,
                0.20,
                -0.30,
                -0.20,
                -0.08,
                0.12,
                0.26,
                0.34,
                0.22,
                0.12,
                0.03,
                0.07,
                0.18,
                0.32,
                0.44,
                0.54,
                0.42,
                0.28,
                0.10,
                0.04,
                0.09,
            ],
            dea=[
                0.10,
                0.11,
                0.12,
                -0.28,
                -0.22,
                -0.10,
                0.06,
                0.13,
                0.20,
                0.22,
                0.18,
                0.12,
                0.10,
                0.11,
                0.18,
                0.26,
                0.36,
                0.42,
                0.36,
                0.18,
                0.11,
                0.12,
            ],
        )
    )

    assert result.current_state == "even_wave_forming"
    assert result.current_wave_index == 4
    assert result.even_repair_started is True
    assert result.bottom_divergence_valid is True
    assert result.prev_even_L == -0.18
    assert result.current_even_L == -0.16


def test_macd_state_machine_flags_imminent_golden_cross_after_even_repair() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.50,
                0.58,
                0.50,
                -0.30,
                -0.20,
                -0.08,
                0.10,
                0.08,
                -0.04,
                -0.30,
                -0.20,
                -0.08,
                0.09,
                0.13,
                0.16,
                0.14,
                0.10,
                0.09,
                0.085,
            ],
            dea=[
                0.20,
                0.23,
                0.26,
                -0.28,
                -0.22,
                -0.10,
                0.04,
                0.06,
                -0.01,
                -0.28,
                -0.22,
                -0.10,
                0.04,
                0.08,
                0.12,
                0.125,
                0.13,
                0.105,
                0.0925,
            ],
        )
    )

    assert result.current_state == "even_wave_forming"
    assert result.even_repair_started is True
    assert result.reason == "golden cross imminent after even-wave repair"
    assert result.events[-1] == "golden_cross_imminent"


def test_macd_state_machine_resets_after_cycle_end_and_waits_for_new_start() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.30,
                0.36,
                0.30,
                -0.30,
                -0.20,
                0.10,
                0.08,
                -0.04,
                -0.30,
                -0.20,
                -0.08,
                0.09,
                0.13,
            ],
            dea=[
                0.10,
                0.12,
                0.14,
                -0.28,
                -0.22,
                0.04,
                0.06,
                -0.01,
                -0.28,
                -0.22,
                -0.10,
                0.04,
                0.08,
            ],
        )
    )

    assert result.current_state == "pre_wave1_pushing"
    assert result.events.count("cycle_ended") == 1
    assert result.events.count("underwater_gc_observed") == 2
    assert result.events.count("pre_wave1_started") == 2
    assert result.events.count("odd_wave_confirmed") == 0


def test_macd_state_machine_clears_h_and_l_after_cycle_end() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.30,
                0.36,
                0.30,
                -0.30,
                -0.20,
                -0.08,
                0.10,
                0.08,
                -0.04,
                -0.30,
                -0.20,
                -0.08,
                0.09,
                0.13,
            ],
            dea=[
                0.10,
                0.12,
                0.14,
                -0.28,
                -0.22,
                -0.10,
                0.04,
                0.06,
                -0.01,
                -0.28,
                -0.22,
                -0.10,
                0.04,
                0.08,
            ],
        )
    )

    assert result.current_state == "pre_wave1_pushing"
    assert result.events.count("cycle_ended") == 1
    assert result.baseline_H is None
    assert result.H is None


def test_macd_state_machine_waits_for_dea_above_zero_before_pre_wave1() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.30,
                0.36,
                0.30,
                -0.30,
                -0.20,
                -0.08,
                -0.02,
                -0.01,
            ],
            dea=[
                0.10,
                0.12,
                0.14,
                -0.28,
                -0.22,
                -0.10,
                -0.06,
                -0.03,
            ],
        )
    )

    assert result.current_state == "waiting_underwater"
    assert result.baseline_H is None
    assert result.events.count("underwater_gc_observed") == 1
    assert result.events.count("pre_wave1_started") == 0


def test_macd_state_machine_starts_pre_wave1_once_dea_turns_positive_without_requiring_red_histogram() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.30,
                0.36,
                0.30,
                -0.30,
                -0.20,
                0.02,
            ],
            dea=[
                0.10,
                0.12,
                0.14,
                -0.28,
                -0.22,
                0.03,
            ],
        )
    )

    assert result.current_state == "pre_wave1_pushing"
    assert result.current_wave_index == 0
    assert result.valid_odd_wave_count == 0
    assert result.baseline_H == 0.04
    assert result.events.count("underwater_gc_observed") == 1
    assert result.events.count("pre_wave1_started") == 1


def test_macd_state_machine_keeps_confirmed_odd_wave_until_above_water_dead_cross() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.20,
                0.25,
                0.20,
                -0.12,
                -0.08,
                0.02,
                0.12,
                0.20,
                0.18,
                0.10,
                0.06,
                0.08,
            ],
            dea=[
                0.10,
                0.12,
                0.13,
                -0.10,
                -0.11,
                -0.04,
                -0.05,
                0.01,
                0.05,
                0.07,
                0.07,
                0.085,
            ],
        )
    )

    assert result.current_state == "even_wave_forming"
    assert result.current_wave_index == 2
    assert result.events.count("odd_wave_confirmed") == 1
    assert result.events.count("cycle_ended") == 0


def test_macd_state_machine_confirms_wave1_when_no_prior_h_exists() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                -0.30,
                -0.20,
                -0.08,
                0.10,
                0.20,
                0.16,
                0.08,
                0.04,
            ],
            dea=[
                -0.28,
                -0.22,
                -0.10,
                0.02,
                0.08,
                0.12,
                0.10,
                0.09,
            ],
        )
    )

    assert result.current_state == "even_wave_forming"
    assert result.current_wave_index == 2
    assert result.valid_odd_wave_count == 1
    assert result.baseline_H is None
    assert result.current_wave_macd_max == 0.24
    assert "odd_wave_confirmed" in result.events


def test_macd_state_machine_confirms_first_wave_once_dea_turns_positive_without_prior_red_peak() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                -0.30,
                -0.26,
                -0.18,
                0.01,
            ],
            dea=[
                -0.28,
                -0.24,
                -0.16,
                0.03,
            ],
        )
    )

    assert result.current_state == "odd_wave_forming"
    assert result.current_wave_index == 1
    assert result.valid_odd_wave_count == 1
    assert result.baseline_H is None
    assert result.events.count("underwater_gc_observed") == 0
    assert result.events.count("odd_wave_confirmed") == 1


def test_macd_state_machine_treats_first_continuous_red_segment_as_wave1_even_if_it_has_internal_peak() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                -5.666663,
                -5.707572,
                -5.644267,
                -5.53593,
                -5.42067,
                -5.239077,
                -4.930204,
                -4.708606,
                -4.577056,
                -4.432201,
                -4.246662,
                -3.989084,
                -3.754582,
                -3.529663,
                -3.369859,
                -3.145627,
                -3.008287,
                -2.92623,
                -2.842155,
                -2.729536,
                -2.59823,
                -2.491273,
                -2.372702,
                -2.234418,
                -2.12215,
                -1.986076,
                -1.892729,
                -1.806002,
                -1.670406,
                -1.488496,
                -1.281148,
                -1.032301,
                -0.469787,
                0.026538,
                0.462958,
                0.924849,
                1.376703,
                1.605742,
                1.789226,
                1.798517,
                1.776526,
                1.652897,
                1.575491,
                1.464184,
                1.377842,
                1.186801,
                0.925481,
                0.707802,
                0.463777,
                0.471521,
            ],
            dea=[
                -4.624905,
                -4.841439,
                -5.002004,
                -5.10879,
                -5.171166,
                -5.184748,
                -5.133839,
                -5.048792,
                -4.954445,
                -4.849996,
                -4.729329,
                -4.58128,
                -4.415941,
                -4.238685,
                -4.06492,
                -3.881061,
                -3.706506,
                -3.550451,
                -3.408792,
                -3.272941,
                -3.137999,
                -3.008654,
                -2.881463,
                -2.752054,
                -2.626073,
                -2.498074,
                -2.377005,
                -2.262804,
                -2.144325,
                -2.013159,
                -1.866757,
                -1.699865,
                -1.45385,
                -1.157772,
                -0.833626,
                -0.481931,
                -0.110204,
                0.232985,
                0.544233,
                0.79509,
                0.991377,
                1.123681,
                1.214043,
                1.264071,
                1.286826,
                1.266821,
                1.198553,
                1.100403,
                0.973078,
                0.872766,
            ],
        )
    )

    assert result.current_state == "even_wave_forming"
    assert result.current_wave_index == 2
    assert result.valid_odd_wave_count == 1
    assert result.even_repair_started is True
    assert result.baseline_H is None
    assert "odd_wave_confirmed" in result.events
    assert "even_wave_started" in result.events


def test_macd_state_machine_uses_prior_even_wave_true_minimum_for_bottom_divergence() -> None:
    # 300193.SZ @ 2026-03-06:
    # compare the completed even-wave low on 2026-02-13 with the current low on 2026-03-04.
    previous_even_low_macd = -0.023655
    current_even_low_macd = -0.162382
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                -0.034035, -0.032326, -0.020249, -0.010556, -0.008425, -0.015435,
                -0.031121, -0.038270, -0.049817, -0.071059, -0.092476, -0.103416,
                -0.100438, -0.092174, -0.091828, -0.082533, -0.066334, -0.060863,
                -0.055085, -0.049931, -0.042133, -0.029959, -0.016889, -0.012838,
                -0.001540, 0.011317, 0.027643, 0.035333, 0.044944, 0.050366,
                0.067601, 0.092300, 0.105813, 0.114397, 0.124604, 0.135968,
                0.132951, 0.132264, 0.120645, 0.100594, 0.090918, 0.079110,
                0.083317, 0.108797, 0.106779, 0.115947, 0.142549, 0.149004,
                0.142790, 0.129115, 0.1097495, 0.116461, 0.122785, 0.135913,
                0.136672, 0.110183, 0.058658, 0.008845, 0.034333, 0.063484,
            ],
            dea=[
                -0.034774, -0.034285, -0.031478, -0.027293, -0.023520, -0.021903,
                -0.023746, -0.026651, -0.031284, -0.039239, -0.049887, -0.060592,
                -0.068561, -0.073284, -0.076993, -0.078101, -0.075747, -0.072770,
                -0.069233, -0.065373, -0.060725, -0.054572, -0.047035, -0.040196,
                -0.032464, -0.023708, -0.013438, -0.003684, 0.006042, 0.014907,
                0.025446, 0.038817, 0.052216, 0.064652, 0.076642, 0.088508,
                0.097396, 0.104370, 0.107625, 0.106219, 0.103159, 0.098349,
                0.095342, 0.098033, 0.099782, 0.103015, 0.110922, 0.118538,
                0.123389, 0.124534, 0.121577, 0.120554, 0.121000, 0.123983,
                0.126521, 0.123253, 0.110334, 0.090036, 0.078896, 0.075813,
            ],
        )
    )

    assert (current_even_low_macd > previous_even_low_macd) is False
    assert result.prev_even_L == previous_even_low_macd
    assert result.current_even_macd_min == current_even_low_macd
    assert result.bottom_divergence_valid is False


def test_macd_state_machine_does_not_end_confirmed_wave_while_dea_remains_underwater() -> None:
    result = classify_macd_state_from_lines(
        _line_frame(
            dif=[
                0.05,
                0.09,
                0.05,
                -0.30,
                -0.20,
                -0.08,
                0.03,
                0.08,
                0.12,
                0.18,
            ],
            dea=[
                0.01,
                0.03,
                0.04,
                -0.28,
                -0.22,
                -0.10,
                -0.08,
                -0.07,
                -0.05,
                -0.02,
            ],
        )
    )

    assert result.current_state == "waiting_underwater"
    assert result.current_wave_index == 0
    assert result.valid_odd_wave_count == 0
    assert result.events.count("cycle_ended") == 0


def test_macd_trend_waits_for_both_lines_above_zero_after_underwater_cross() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, -0.12, -0.04],
            dea=[-0.28, -0.24, -0.16, -0.08],
        )
    )

    assert result.phase == "idle"
    assert result.direction == "neutral"
    assert result.reason == "waiting for both MACD lines above zero"


def test_macd_trend_enters_rising_after_underwater_cross_and_both_lines_above_zero() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, -0.12, 0.03, 0.08],
            dea=[-0.28, -0.24, -0.16, 0.01, 0.04],
        )
    )

    assert result.phase == "rising"
    assert result.direction == "rising"
    assert result.phase_index == 1
    assert result.bars_in_phase == 2
    assert result.is_rising_initial is True


def test_macd_trend_alternates_between_rising_and_falling_above_water() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.06, 0.05, 0.07],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.07, 0.06, 0.055],
        )
    )

    assert result.phase == "rising"
    assert result.direction == "rising"
    assert result.phase_index == 3
    assert result.bars_in_phase == 1


def test_macd_trend_marks_ended_when_dif_crosses_below_zero() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.02, -0.01],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.01, 0.005],
        )
    )

    assert result.phase == "ended"
    assert result.direction == "neutral"
    assert result.reason == "DIF crossed below zero"


def test_macd_trend_uses_latest_cycle_after_prior_cycle_ended() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, -0.01, -0.20, -0.12, 0.02, 0.06],
            dea=[-0.28, -0.24, 0.01, 0.00, -0.18, -0.14, 0.01, 0.03],
        )
    )

    assert result.phase == "rising"
    assert result.phase_index == 1
    assert result.bars_in_phase == 2


def test_macd_trend_stays_ended_when_next_startup_has_not_reached_zero_axis() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, -0.01, -0.20, -0.12, -0.08],
            dea=[-0.28, -0.24, 0.01, 0.00, -0.18, -0.14, -0.10],
        )
    )

    assert result.phase == "ended"
    assert result.reason == "DIF crossed below zero"


def test_macd_trend_recovers_running_above_zero_after_prior_ended_state() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.04, 0.035, 0.033, 0.032, 0.031, 0.0305, -0.01, 0.20, 0.40, 0.60, 0.80, 0.90, 0.75, 0.60],
            dea=[-0.28, -0.24, 0.01, 0.02, 0.025, 0.028, 0.029, 0.03, 0.0302, 0.00, 0.05, 0.20, 0.40, 0.60, 0.70, 0.78, 0.75],
        )
    )

    assert result.phase == "falling"
    assert result.direction == "falling"
    assert result.reason in {
        "above-zero recovery into MACD falling segment",
        "above-water MACD dead cross",
    }
    assert result.phase_index == 2
    assert result.wave_label == "二浪"
    assert result.wave_stage in {"分歧", "背离"}


def test_macd_trend_recovers_idle_above_zero_as_rising_divergence() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[0.3747, 0.3506, 0.3436, 0.3869, 0.5465, 0.7762, 1.1100, 1.5216, 1.8547, 2.2963, 2.4726, 2.4389],
            dea=[0.3479, 0.3484, 0.3475, 0.3554, 0.3936, 0.4701, 0.5981, 0.7828, 0.9972, 1.2570, 1.5001, 1.6879],
        )
    )

    assert result.phase == "rising"
    assert result.direction == "rising"
    assert result.wave_label in {"一浪", "三浪"}
    assert result.wave_stage == "背离"
    assert result.is_top_divergence is True


def test_macd_trend_treats_flattening_falling_histogram_as_divergence_warning() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.12, 0.16, 0.20, 1.9431, 1.9714, 2.0988, 2.0358, 1.9569, 1.7468, 1.4777, 1.1662, 0.9616, 0.7608, 0.5963],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.08, 0.11, 0.14, 1.7970, 1.8319, 1.8853, 1.9154, 1.9237, 1.8883, 1.8062, 1.6782, 1.5349, 1.3800, 1.2233],
        )
    )

    assert result.phase == "falling"
    assert result.wave_label == "二浪"
    assert result.wave_stage in {"强势转分歧", "分歧"}


def test_macd_trend_flags_top_divergence_when_rising_spread_shrinks() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.09, 0.10],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.07],
        )
    )

    assert result.phase == "rising"
    assert result.metrics["spread"] == 0.03
    assert result.metrics["previous_spread"] == 0.05
    assert result.is_top_divergence is True


def test_macd_trend_tracks_wave_number_and_odd_even_wave_names() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.06, 0.05, 0.07, 0.11, 0.09],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.07, 0.06, 0.055, 0.08, 0.10],
        )
    )

    assert result.phase == "falling"
    assert result.direction == "falling"
    assert result.phase_index == 4
    assert result.wave_label == "四浪"
    assert result.wave_direction == "falling"


def test_macd_trend_quantifies_rising_wave_strength_stage() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.06, 0.09, 0.13, 0.18, 0.24, 0.31, 0.39, 0.48, 0.58],
            dea=[-0.28, -0.24, 0.01, 0.025, 0.04, 0.06, 0.085, 0.115, 0.15, 0.19, 0.235, 0.285],
        )
    )

    assert result.phase == "rising"
    assert result.wave_label == "一浪"
    assert result.wave_stage == "强势"
    assert result.metrics["hist_change_rate"] > 0.05
    assert result.metrics["dif_slope_5"] > 0.001
    assert result.metrics["dif_zero_distance_ratio"] > 0.6


def test_macd_trend_quantifies_rising_wave_divergence_stage() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.15, 0.23, 0.32, 0.42, 0.50, 0.55, 0.58, 0.60, 0.61],
            dea=[-0.28, -0.24, 0.01, 0.03, 0.06, 0.10, 0.16, 0.24, 0.34, 0.43, 0.50, 0.56, 0.59],
        )
    )

    assert result.phase == "rising"
    assert result.wave_stage == "背离"
    assert result.is_top_divergence is True
    assert result.metrics["hist_change_rate"] < -0.05


def test_macd_trend_quantifies_falling_wave_strength_stage() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.10, 0.16, 0.22, 0.18, 0.14, 0.10, 0.07, 0.04],
            dea=[-0.28, -0.24, 0.01, 0.05, 0.09, 0.13, 0.20, 0.21, 0.22, 0.23, 0.24],
        )
    )

    assert result.phase == "falling"
    assert result.wave_label == "二浪"
    assert result.wave_stage == "强势"
    assert result.metrics["hist_change_rate"] > 0.05
    assert result.metrics["dif_slope_5"] < -0.001


def test_macd_trend_emits_stage_transition_warnings() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.09, 0.16, 0.22, 0.27, 0.31, 0.34, 0.36, 0.37],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.08, 0.12, 0.17, 0.22, 0.27, 0.315, 0.355],
        )
    )

    assert result.wave_stage == "背离"
    assert "强势→分歧预警" in result.transition_warnings
    assert "金叉/死叉临近，浪型可能切换" in result.transition_warnings


def test_classify_weekly_macd_wave_returns_wave1_for_first_constructive_advance() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.1, 10.4, 10.8, 11.2, 11.6, 12.0, 12.3, 12.6, 12.9]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave1"
    assert "golden cross" in result.reason.lower()


def test_classify_weekly_macd_wave_returns_wave2_for_confirmed_pullback() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.2, 10.6, 11.0, 11.4, 11.7, 11.5, 11.2, 10.9, 10.6, 10.4, 10.3]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave2"


def test_classify_daily_macd_wave_returns_wave2_end_for_left_side_pullback() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.1, 10.4, 10.8, 11.1, 11.4, 11.2, 11.0, 10.9, 10.92, 10.97, 11.02]
    )

    result = classify_daily_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave2_end"
    assert result.details["needs_recross"] is False


def test_classify_daily_macd_state_returns_wave2_end_valid_for_left_side_pullback() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.1, 10.4, 10.8, 11.1, 11.4, 11.2, 11.0, 10.9, 10.92, 10.97, 11.02]
    )

    result = classify_daily_macd_state(frame, pick_date="2026-03-31")

    assert result.state == "wave2_end_valid"
    assert result.valid_for_pullback is True


def test_classify_daily_macd_state_returns_overextended_when_wave4_shape_exceeds_30_pct_gain() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.7, 9.5, 9.8, 10.2, 10.6, 11.0, 10.6, 10.3, 10.5, 11.0, 11.8, 12.9, 13.6, 13.2, 12.9, 12.7, 12.8]
    )

    result = classify_daily_macd_state(frame, pick_date="2026-03-31")

    assert result.state == "overextended"
    assert result.metrics["third_wave_gain"] > 0.30


def test_classify_daily_macd_state_returns_deteriorating_when_pullback_keeps_worsening() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.8, 9.7, 9.9, 10.3, 10.8, 11.3, 11.9, 12.4, 12.8, 13.0, 12.8, 12.5, 12.0, 11.5, 11.0, 10.6, 10.1]
    )

    result = classify_daily_macd_state(frame, pick_date="2026-04-03")

    assert result.state == "deteriorating"
    assert result.valid_for_pullback is False


def test_classify_daily_macd_wave_invalidates_wave4_when_third_wave_gain_exceeds_30_pct() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.7, 9.5, 9.8, 10.2, 10.6, 11.0, 10.6, 10.3, 10.5, 11.0, 11.8, 12.9, 13.6, 13.2, 12.9, 12.7, 12.8]
    )

    result = classify_daily_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "invalid"
    assert result.details["third_wave_gain"] > 0.30


def test_classify_daily_macd_wave_invalidates_negative_converging_pullback_above_30_pct() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.7, 9.5, 9.8, 10.2, 10.7, 11.2, 11.8, 12.4, 13.0, 13.4, 13.0, 12.6, 12.2, 11.9, 11.7, 11.6, 11.58, 11.57]
    )

    result = classify_daily_macd_wave(frame, pick_date="2026-04-10")

    assert result.label == "invalid"
    assert result.details["third_wave_gain"] > 0.30


def test_classify_weekly_macd_wave_prefers_wave2_for_fading_bullish_pullback_before_wave3() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [9.6, 9.4, 9.3, 9.5, 9.9, 10.4, 10.9, 11.4, 11.8, 12.1, 12.4, 12.1, 11.8, 11.5, 11.2, 11.0, 10.9, 10.85, 10.8]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-04-10")

    assert result.label == "wave2"


def test_classify_weekly_macd_wave_returns_invalid_for_churn() -> None:
    frame = _frame_with_close(
        [10.0, 10.2, 9.9, 10.1, 9.8, 10.0, 9.85, 10.05, 9.9, 10.1] * 8
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-04-10")

    assert result.label == "invalid"


def test_classify_weekly_macd_wave_ignores_churn_outside_recent_six_month_window() -> None:
    frame = _frame_from_weekly_close(
        [10.0, 12.0, 9.0, 11.0, 8.0, 10.0, 12.0, 9.0, 11.0, 8.0, 10.0, 12.0, 9.0, 11.0]
        + [11.2, 11.4, 11.6, 11.8, 12.0, 12.2, 12.5, 12.8, 13.1, 13.4, 13.8, 14.2, 14.6, 15.0, 15.5, 16.0, 16.6, 17.2, 17.9, 18.6, 19.4, 20.2, 21.1, 22.0, 23.0, 24.0]
    )

    result = classify_weekly_macd_wave(frame, pick_date=str(frame["trade_date"].iloc[-1].date()))

    assert result.label == "wave1"


def test_classify_weekly_macd_wave_defaults_to_wave1_when_recent_window_has_no_underwater_cross() -> None:
    frame = _frame_with_close(
        [10.0] * 40
        + [10.1, 10.2, 10.3, 10.4, 10.6, 10.8, 11.0, 11.3, 11.7, 12.1, 12.6, 13.2]
    )

    result = classify_weekly_macd_wave(frame, pick_date="2026-03-31")

    assert result.label == "wave1"
