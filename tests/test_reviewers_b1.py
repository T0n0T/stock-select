from pathlib import Path

import pandas as pd
import pytest

from stock_select.environment_profiles import get_method_environment_profile
from stock_select.reviewers import b1 as b1_reviewer
from stock_select.reviewers.b2 import _score_b2_previous_abnormal_move
from stock_select.reviewers.b1 import review_b1_symbol_history


_MULTI_TIMEFRAME_CONFIRMATION_POINTS = 40


def _first_non_fallback_periods(end: str = "2026-04-30") -> int:
    for periods in range(_MULTI_TIMEFRAME_CONFIRMATION_POINTS, 1600):
        trade_dates = pd.bdate_range(end=end, periods=periods)
        weekly_closes = pd.Series(range(len(trade_dates)), index=trade_dates).resample("W-FRI").last().dropna()
        monthly_closes = pd.Series(range(len(trade_dates)), index=trade_dates).resample("ME").last().dropna()
        if len(weekly_closes) >= _MULTI_TIMEFRAME_CONFIRMATION_POINTS and len(monthly_closes) >= _MULTI_TIMEFRAME_CONFIRMATION_POINTS:
            return periods
    msg = "could not find non-fallback periods"
    raise AssertionError(msg)


def _constructive_b1_history() -> pd.DataFrame:
    tail = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=170),
            "open": [10.0] * 150
            + [
                12.4,
                12.8,
                13.2,
                13.4,
                13.1,
                12.9,
                12.8,
                12.85,
                12.95,
                13.1,
                13.2,
                13.3,
                13.35,
                13.4,
                13.5,
                13.55,
                13.6,
                13.65,
                13.7,
                13.8,
            ],
            "high": [10.2] * 150
            + [
                12.9,
                13.2,
                13.5,
                13.6,
                13.2,
                13.0,
                12.95,
                13.0,
                13.1,
                13.25,
                13.35,
                13.45,
                13.5,
                13.55,
                13.65,
                13.7,
                13.75,
                13.8,
                13.9,
                14.0,
            ],
            "low": [9.8] * 150
            + [
                12.1,
                12.6,
                13.0,
                13.0,
                12.8,
                12.7,
                12.7,
                12.8,
                12.9,
                13.0,
                13.1,
                13.2,
                13.25,
                13.3,
                13.35,
                13.4,
                13.45,
                13.5,
                13.6,
                13.7,
            ],
            "close": [10.0] * 150
            + [
                12.7,
                13.0,
                13.3,
                13.1,
                12.95,
                12.85,
                12.82,
                12.9,
                13.02,
                13.15,
                13.25,
                13.35,
                13.4,
                13.45,
                13.55,
                13.6,
                13.65,
                13.72,
                13.82,
                13.95,
            ],
            "vol": [900.0] * 150
            + [
                2500.0,
                3100.0,
                3600.0,
                2200.0,
                1400.0,
                1200.0,
                1100.0,
                1150.0,
                1180.0,
                1300.0,
                1320.0,
                1350.0,
                1380.0,
                1400.0,
                1450.0,
                1500.0,
                1520.0,
                1550.0,
                1600.0,
                1680.0,
            ],
        }
    )
    prefix_periods = _first_non_fallback_periods() - len(tail)
    prefix_dates = pd.bdate_range(end=tail["trade_date"].iloc[0] - pd.offsets.BDay(1), periods=prefix_periods)
    prefix = pd.DataFrame(
        {
            "trade_date": prefix_dates,
            "open": [10.0] * prefix_periods,
            "high": [10.2] * prefix_periods,
            "low": [9.8] * prefix_periods,
            "close": [10.0] * prefix_periods,
            "vol": [900.0] * prefix_periods,
        }
    )
    return pd.concat([prefix, tail], ignore_index=True)


def test_b1_review_keeps_schema_stable_without_extra_reasoning_fields() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "macd_reasoning" not in review
    assert "signal_reasoning" not in review


def test_b1_review_comment_mentions_weekly_and_daily_waves() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "周线" in review["comment"]
    assert "日线" in review["comment"]
    assert "b1" in review["comment"]


def test_b1_review_counts_macd_phase_in_total_score() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    score_without_macd = round(
        review["trend_structure"] * 0.225
        + review["price_position"] * 0.225
        + review["volume_behavior"] * 0.30
        + review["previous_abnormal_move"] * 0.25,
        2,
    )
    assert review["total_score"] != score_without_macd


def test_b1_review_caps_invalid_daily_wave_below_pass_band() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "日线MACD" in review["comment"]
    assert review["macd_phase"] <= 4.5
    assert review["verdict"] != "PASS"


def test_b1_trend_structure_rewards_pullback_to_zxdkx_with_rising_ma25_and_zxdkx() -> None:
    close = pd.Series([10.0] * 30)
    open_ = pd.Series([10.0] * 30)
    ma25 = pd.Series([10.6 + idx * 0.01 for idx in range(30)])
    zxdkx = pd.Series([9.6 + idx * 0.01 for idx in range(30)])
    bbi = ma25 + 0.4

    score = b1_reviewer._score_b1_trend_structure(open_=open_, close=close, ma25=ma25, zxdkx=zxdkx, bbi=bbi)

    assert score == 5.0


def test_b1_trend_structure_scores_three_for_price_above_ma25_with_ma25_above_zxdkx() -> None:
    close = pd.Series([10.0 + idx * 0.1 for idx in range(30)])
    open_ = close + 0.1
    ma25 = close - 0.8
    zxdkx = ma25 - 0.4
    bbi = ma25 - 0.1

    score = b1_reviewer._score_b1_trend_structure(open_=open_, close=close, ma25=ma25, zxdkx=zxdkx, bbi=bbi)

    assert score == 3.0


def test_b1_price_position_uses_deeper_box_pullback_as_better_odds() -> None:
    low_box = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 12.0, 11.5, 11.0])
    high_box = low_box + 1.0
    close = pd.Series([10.5, 11.5, 12.5, 13.5, 14.5, 12.5, 11.8, 11.2])
    ma25 = pd.Series([12.0] * len(close))
    zxdq = pd.Series([11.6] * len(close))

    score = b1_reviewer._score_b1_price_position(close=close, high=high_box, low=low_box, ma25=ma25, zxdq=zxdq)

    assert score == 5.0


def test_b1_price_position_keeps_high_position_observable_when_ma25_holds_zxdq() -> None:
    low = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    high = pd.Series([11.0, 12.0, 13.0, 14.0, 15.0])
    close = pd.Series([10.5, 11.5, 12.5, 13.5, 14.2])
    ma25 = pd.Series([13.0] * len(close))
    zxdq = pd.Series([12.7] * len(close))

    score = b1_reviewer._score_b1_price_position(close=close, high=high, low=low, ma25=ma25, zxdq=zxdq)

    assert score == 3.0


def test_classify_b1_pass_family_marks_rebound_core() -> None:
    family = b1_reviewer._classify_b1_pass_family(
        signal_type="rebound",
        trend_structure=3.0,
        price_position=3.0,
        volume_behavior=4.0,
        previous_abnormal_move=5.0,
        macd_phase=3.5,
    )

    assert family["family"] == "rebound"
    assert family["tier"] == "core"


def test_classify_b1_pass_family_keeps_exact_core_cutoff_values() -> None:
    family = b1_reviewer._classify_b1_pass_family(
        signal_type="distribution_risk",
        trend_structure=3.0,
        price_position=4.0,
        volume_behavior=4.0,
        previous_abnormal_move=5.0,
        macd_phase=4.2,
    )

    assert family["family"] == "distribution"
    assert family["tier"] == "core"


def test_classify_b1_pass_family_prefers_core_when_core_and_near_both_match() -> None:
    family = b1_reviewer._classify_b1_pass_family(
        signal_type="trend_start",
        trend_structure=4.0,
        price_position=3.0,
        volume_behavior=4.0,
        previous_abnormal_move=5.0,
        macd_phase=3.3,
    )

    assert family["family"] == "trend_start"
    assert family["tier"] == "core"


def test_classify_b1_pass_family_marks_distribution_near() -> None:
    family = b1_reviewer._classify_b1_pass_family(
        signal_type="distribution_risk",
        trend_structure=2.0,
        price_position=5.0,
        volume_behavior=3.0,
        previous_abnormal_move=4.0,
        macd_phase=3.4,
    )

    assert family["family"] == "distribution"
    assert family["tier"] == "near"


def test_classify_b1_pass_family_returns_none_for_non_template_sample() -> None:
    family = b1_reviewer._classify_b1_pass_family(
        signal_type="rebound",
        trend_structure=2.0,
        price_position=5.0,
        volume_behavior=2.0,
        previous_abnormal_move=2.0,
        macd_phase=4.6,
    )

    assert family["family"] is None
    assert family["tier"] == "none"


def test_b1_score_combo_key_uses_discrete_subscores_and_half_point_macd_bucket() -> None:
    key = b1_reviewer._build_b1_score_combo_key(
        signal_type="rebound",
        trend_structure=3.0,
        price_position=3.0,
        volume_behavior=4.0,
        previous_abnormal_move=5.0,
        macd_phase=3.52,
    )

    assert key == "rebound|T3|P3|V4|A5|M3.5"


@pytest.mark.parametrize(
    ("signal_type", "trend_structure", "price_position", "volume_behavior", "previous_abnormal_move", "macd_phase", "expected_key"),
    [
        ("rebound", 3.0, 3.0, 4.0, 5.0, 3.52, "rebound|T3|P3|V4|A5|M3.5"),
        (
            "distribution_risk",
            2.0,
            4.0,
            4.0,
            5.0,
            3.8,
            "distribution_risk|T2|P4|V4|A5|M4.0",
        ),
        ("trend_start", 4.0, 3.0, 4.0, 5.0, 3.4, "trend_start|T4|P3|V4|A5|M3.5"),
    ],
)
def test_classify_b1_high_return_combo_marks_target_groups_as_exact(
    signal_type: str,
    trend_structure: float,
    price_position: float,
    volume_behavior: float,
    previous_abnormal_move: float,
    macd_phase: float,
    expected_key: str,
) -> None:
    result = b1_reviewer._classify_b1_high_return_combo(
        signal_type=signal_type,
        trend_structure=trend_structure,
        price_position=price_position,
        volume_behavior=volume_behavior,
        previous_abnormal_move=previous_abnormal_move,
        macd_phase=macd_phase,
    )

    assert result["combo_key"] == expected_key
    assert result["match_type"] == "exact"


def test_b1_environment_allows_all_exact_combos_in_neutral() -> None:
    for combo_key in b1_reviewer._B1_HIGH_RETURN_SCORE_COMBOS:
        assert b1_reviewer._is_b1_exact_combo_pass_allowed(
            combo_key=combo_key,
            environment_state="neutral",
        ) is True


def test_b1_environment_only_allows_trend_start_exact_combo_in_strong() -> None:
    assert b1_reviewer._is_b1_exact_combo_pass_allowed(
        combo_key="trend_start|T4|P3|V4|A5|M3.5",
        environment_state="strong",
    ) is True
    assert b1_reviewer._is_b1_exact_combo_pass_allowed(
        combo_key="distribution_risk|T2|P4|V4|A5|M4.0",
        environment_state="strong",
    ) is False
    assert b1_reviewer._is_b1_exact_combo_pass_allowed(
        combo_key="rebound|T3|P3|V4|A5|M3.5",
        environment_state="strong",
    ) is False


def test_b1_environment_only_allows_distribution_exact_combo_in_weak() -> None:
    assert b1_reviewer._is_b1_exact_combo_pass_allowed(
        combo_key="distribution_risk|T2|P4|V4|A5|M4.0",
        environment_state="weak",
    ) is True
    assert b1_reviewer._is_b1_exact_combo_pass_allowed(
        combo_key="rebound|T3|P3|V4|A5|M3.5",
        environment_state="weak",
    ) is False
    assert b1_reviewer._is_b1_exact_combo_pass_allowed(
        combo_key="trend_start|T4|P3|V4|A5|M3.5",
        environment_state="weak",
    ) is False


def test_b1_score_layer_promotes_neutral_distribution_pass_to_pass_a() -> None:
    layer = b1_reviewer._score_b1_layer(
        verdict="PASS",
        environment_state="neutral",
        score_combo_key="distribution_risk|T2|P4|V4|A5|M4.0",
        gate_flags=[],
    )

    assert layer["score_layer"] == "PASS-A"
    assert layer["score_layer_score"] >= 90.0


def test_b1_score_layer_marks_strong_trend_pass_as_pass_b() -> None:
    layer = b1_reviewer._score_b1_layer(
        verdict="PASS",
        environment_state="strong",
        score_combo_key="trend_start|T4|P3|V4|A5|M3.5",
        gate_flags=[],
    )

    assert layer["score_layer"] == "PASS-B"


def test_b1_score_layer_promotes_gated_strong_exact_watch_to_watch_a() -> None:
    layer = b1_reviewer._score_b1_layer(
        verdict="WATCH",
        environment_state="strong",
        score_combo_key="trend_start|T4|P3|V4|A5|M3.5",
        gate_flags=["runup_over_limit"],
    )

    assert layer["score_layer"] == "WATCH-A"


def test_b1_calibrated_total_score_prioritizes_exact_high_return_combo() -> None:
    exact_score = b1_reviewer._compute_b1_calibrated_total_score(
        raw_total_score=3.67,
        verdict="PASS",
        environment_state="neutral",
        high_return_match="exact",
        pass_family="rebound",
        pass_family_tier="core",
        score_layer="PASS-A",
        score_layer_score=90.0,
        gate_flags=["sideways_tight_range"],
    )
    high_raw_non_target_score = b1_reviewer._compute_b1_calibrated_total_score(
        raw_total_score=4.51,
        verdict="FAIL",
        environment_state="neutral",
        high_return_match="none",
        pass_family=None,
        pass_family_tier="none",
        score_layer=None,
        score_layer_score=None,
        gate_flags=["below_ma25"],
    )

    assert exact_score >= 4.65
    assert high_raw_non_target_score < 4.0
    assert exact_score > high_raw_non_target_score


def test_b1_calibrated_total_score_places_core_combo_in_review_band() -> None:
    core_score = b1_reviewer._compute_b1_calibrated_total_score(
        raw_total_score=4.12,
        verdict="WATCH",
        environment_state="neutral",
        high_return_match="trend_core",
        pass_family="trend_start",
        pass_family_tier="near",
        score_layer="WATCH-A",
        score_layer_score=70.0,
        gate_flags=["cooldown_active", "sideways_tight_range"],
    )

    assert 4.0 <= core_score < 4.65


def test_b1_review_routes_high_return_distribution_combo_to_watch_when_neutral_below_ma25_gate_triggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    history = _constructive_b1_history()

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 2.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.8)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.8)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "distribution_risk")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(
        b1_reviewer,
        "_compute_b1_environment_gate",
        lambda **kwargs: {
            "score_penalty": 0.35,
            "cooldown_active": True,
            "cooldown_reason": "recent_death_cross_cooldown",
            "runup_pct": 58.0,
            "drawdown_pct": None,
            "below_ma25": True,
            "sideways_amplitude_pct": 12.0,
            "weekly_slope_26w": None,
            "weekly_macd_cooldown_active": False,
            "triggered_flags": ["cooldown_active", "below_ma25", "runup_over_limit", "sideways_tight_range"],
        },
    )

    review = review_b1_symbol_history(
        code="000009.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000009.SZ_day.png",
        profile=profile,
    )

    assert review["score_combo_key"] == "distribution_risk|T2|P4|V4|A5|M4.0"
    assert review["high_return_combo_match"] == "exact"
    assert review["verdict"] == "WATCH"
    assert review["gate_flags"] == ["cooldown_active", "below_ma25", "runup_over_limit", "sideways_tight_range"]
    assert review["gate_runup_pct"] == 58.0
    assert review["gate_sideways_amplitude_pct"] == 12.0


def test_infer_b1_family_verdict_keeps_trend_start_core_as_watch_before_exact_combo_match() -> None:
    verdict = b1_reviewer._infer_b1_family_verdict(
        family="trend_start",
        tier="core",
        environment_state="strong",
        total_score=3.95,
    )

    assert verdict == "WATCH"


def test_infer_b1_family_verdict_caps_distribution_core_to_watch_in_strong() -> None:
    verdict = b1_reviewer._infer_b1_family_verdict(
        family="distribution",
        tier="core",
        environment_state="strong",
        total_score=4.10,
    )

    assert verdict == "WATCH"


def test_infer_b1_family_verdict_caps_all_core_families_below_pass_in_weak() -> None:
    verdict = b1_reviewer._infer_b1_family_verdict(
        family="rebound",
        tier="core",
        environment_state="weak",
        total_score=4.50,
    )

    assert verdict == "WATCH"


def test_infer_b1_family_verdict_marks_none_family_as_fail() -> None:
    verdict = b1_reviewer._infer_b1_family_verdict(
        family=None,
        tier="none",
        environment_state="neutral",
        total_score=4.80,
    )

    assert verdict == "FAIL"


def test_b1_review_pass_family_routes_rebound_core_to_watch_when_not_exact_combo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    history = _constructive_b1_history()

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "rebound")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(
        b1_reviewer,
        "_compute_b1_environment_gate",
        lambda **kwargs: {
            "score_penalty": 0.0,
            "cooldown_active": False,
            "cooldown_reason": None,
            "runup_pct": None,
            "drawdown_pct": None,
            "below_ma25": False,
            "triggered_flags": [],
        },
    )

    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["pass_family"] == "rebound"
    assert review["pass_family_tier"] == "core"
    assert review["verdict"] == "WATCH"


def test_b1_review_pass_family_defaults_to_neutral_without_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _constructive_b1_history()

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "rebound")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(b1_reviewer, "compute_method_total_score", lambda method, fields: 3.92)
    monkeypatch.setattr(
        b1_reviewer,
        "_compute_b1_environment_gate",
        lambda **kwargs: {
            "score_penalty": 0.0,
            "cooldown_active": False,
            "cooldown_reason": None,
            "runup_pct": None,
            "drawdown_pct": None,
            "below_ma25": False,
            "triggered_flags": [],
        },
    )

    review = review_b1_symbol_history(
        code="000006.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000006.SZ_day.png",
    )

    assert review["pass_family"] == "rebound"
    assert review["pass_family_tier"] == "core"
    assert review["verdict"] == "WATCH"


def test_b1_review_pass_family_caps_rebound_core_to_watch_in_weak_even_if_legacy_verdict_would_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = get_method_environment_profile(method="b1", state="weak")
    history = _constructive_b1_history()
    history.loc[history.index[-1], "open"] = 14.0

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.1)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.8)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.8)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "rebound")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(
        b1_reviewer,
        "_resolve_series",
        lambda frame, column, fallback: pd.Series([14.5] * len(frame), index=frame.index)
        if column == "ma25"
        else fallback,
    )
    monkeypatch.setattr(
        b1_reviewer,
        "_resolve_zx_lines",
        lambda frame: (
            pd.Series([14.8] * len(frame), index=frame.index),
            pd.Series([13.0] * len(frame), index=frame.index),
        ),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "_compute_b1_environment_gate",
        lambda **kwargs: {
            "score_penalty": 0.0,
            "cooldown_active": False,
            "cooldown_reason": None,
            "runup_pct": None,
            "drawdown_pct": None,
            "below_ma25": False,
            "triggered_flags": [],
        },
    )

    review = review_b1_symbol_history(
        code="000004.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000004.SZ_day.png",
        profile=profile,
    )

    legacy_verdict = b1_reviewer.infer_b1_verdict(
        total_score=review["raw_total_score"],
        volume_behavior=5.0,
        signal_type="rebound",
        trend_structure=4.0,
        price_position=3.0,
        previous_abnormal_move=5.1,
        macd_phase=3.8,
        close_above_ma25_pct=(13.95 / 14.5 - 1.0) * 100.0,
        ma25_above_zxdkx_pct=(14.5 / 13.0 - 1.0) * 100.0,
        close_above_zxdkx_pct=(13.95 / 13.0 - 1.0) * 100.0,
        close_above_zxdq_pct=(13.95 / 14.8 - 1.0) * 100.0,
        day_pct=(13.95 / 14.0 - 1.0) * 100.0,
        profile=profile,
    )

    assert legacy_verdict == "PASS"
    assert review["pass_family"] == "rebound"
    assert review["pass_family_tier"] == "core"
    assert review["verdict"] == "WATCH"


def test_b1_review_pass_family_routes_non_family_sample_to_fail_before_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    history = _constructive_b1_history()

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 2.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 2.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 2.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 4.5)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 4.5)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "rebound")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(
        b1_reviewer,
        "_compute_b1_environment_gate",
        lambda **kwargs: {
            "score_penalty": 0.0,
            "cooldown_active": False,
            "cooldown_reason": None,
            "runup_pct": None,
            "drawdown_pct": None,
            "below_ma25": False,
            "triggered_flags": [],
        },
    )

    review = review_b1_symbol_history(
        code="000002.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000002.SZ_day.png",
        profile=profile,
    )

    assert review["pass_family"] is None
    assert review["pass_family_tier"] == "none"
    assert review["verdict"] == "FAIL"


def test_b1_review_pass_family_keeps_core_watch_when_environment_cooldown_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    history = _constructive_b1_history()
    history.loc[history.index[-1], "open"] = 14.0

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.8)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.8)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "rebound")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(
        b1_reviewer,
        "_resolve_series",
        lambda frame, column, fallback: pd.Series([14.5] * len(frame), index=frame.index)
        if column == "ma25"
        else fallback,
    )
    monkeypatch.setattr(
        b1_reviewer,
        "_resolve_zx_lines",
        lambda frame: (
            pd.Series([14.8] * len(frame), index=frame.index),
            pd.Series([13.0] * len(frame), index=frame.index),
        ),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "_compute_b1_environment_gate",
        lambda **kwargs: {
            "score_penalty": 0.0,
            "cooldown_active": True,
            "cooldown_reason": "recent_death_cross_cooldown",
            "runup_pct": None,
            "drawdown_pct": None,
            "below_ma25": False,
            "triggered_flags": ["cooldown_active"],
        },
    )

    review = review_b1_symbol_history(
        code="000003.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000003.SZ_day.png",
        profile=profile,
    )

    matrix_verdict = b1_reviewer._infer_b1_family_verdict(
        family=review["pass_family"],
        tier=review["pass_family_tier"],
        environment_state=profile.state,
        total_score=review["total_score"],
    )
    legacy_verdict = b1_reviewer.infer_b1_verdict(
        total_score=review["raw_total_score"],
        volume_behavior=5.0,
        signal_type="rebound",
        trend_structure=4.0,
        price_position=3.0,
        previous_abnormal_move=5.0,
        macd_phase=3.8,
        close_above_ma25_pct=(13.95 / 14.5 - 1.0) * 100.0,
        ma25_above_zxdkx_pct=(14.5 / 13.0 - 1.0) * 100.0,
        close_above_zxdkx_pct=(13.95 / 13.0 - 1.0) * 100.0,
        close_above_zxdq_pct=(13.95 / 14.8 - 1.0) * 100.0,
        day_pct=(13.95 / 14.0 - 1.0) * 100.0,
        profile=profile,
    )

    assert matrix_verdict == "WATCH"
    assert legacy_verdict == "PASS"
    assert review["pass_family"] == "rebound"
    assert review["pass_family_tier"] == "core"
    assert review["verdict"] == "WATCH"


def test_b1_review_high_return_trend_start_keeps_pass_and_records_below_ma25_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = get_method_environment_profile(method="b1", state="strong")
    history = _constructive_b1_history()
    history.loc[history.index[-1], "close"] = 13.0
    history.loc[history.index[-1], "open"] = 12.9

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "trend_start")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(
        b1_reviewer,
        "_resolve_series",
        lambda frame, column, fallback: pd.Series([14.0] * len(frame), index=frame.index)
        if column == "ma25"
        else fallback,
    )
    monkeypatch.setattr(
        b1_reviewer,
        "compute_macd",
        lambda frame: pd.DataFrame(
            {
                "dif": [0.4, 0.5, 0.55, 0.6],
                "dea": [0.3, 0.4, 0.48, 0.55],
                "macd_hist": [0.2, 0.2, 0.14, 0.1],
            }
        ),
    )

    review = review_b1_symbol_history(
        code="000005.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000005.SZ_day.png",
        profile=profile,
    )

    assert review["pass_family"] == "trend_start"
    assert review["pass_family_tier"] == "core"
    assert review["score_combo_key"] == "trend_start|T4|P3|V4|A5|M3.5"
    assert review["high_return_combo_match"] == "exact"
    assert review["verdict"] == "PASS"
    assert review["signal_type"] == "trend_start"
    gate = b1_reviewer._compute_b1_environment_gate(
        close=history["close"].astype(float),
        ma25=pd.Series([14.0] * len(history), index=history.index),
        dif=pd.Series([0.4, 0.5, 0.55, 0.6]),
        dea=pd.Series([0.3, 0.4, 0.48, 0.55]),
        profile=profile,
    )
    assert gate["below_ma25"] is True
    assert "below_ma25" in gate["triggered_flags"]
    assert review["gate_below_ma25"] is True
    assert "below_ma25" in review["gate_flags"]


def test_b1_environment_verdict_gate_cooldown_is_diagnostic_only() -> None:
    rebound_verdict = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="rebound",
        environment_state="neutral",
        current_verdict="PASS",
        gate_flags=["cooldown_active"],
    )
    distribution_verdict = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="distribution",
        environment_state="strong",
        current_verdict="PASS",
        gate_flags=["cooldown_active"],
    )

    assert rebound_verdict == "PASS"
    assert distribution_verdict == "PASS"


def test_b1_environment_verdict_gate_below_ma25_does_not_demote_strong_exact_passes() -> None:
    trend_gate = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="trend_start",
        environment_state="strong",
        current_verdict="PASS",
        gate_flags=["below_ma25"],
    )
    rebound_gate = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="rebound",
        environment_state="strong",
        current_verdict="PASS",
        gate_flags=["below_ma25"],
    )

    assert trend_gate == "PASS"
    assert rebound_gate == "PASS"


def test_b1_environment_verdict_gate_below_ma25_caps_exact_pass_in_neutral() -> None:
    verdict = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="distribution",
        environment_state="neutral",
        current_verdict="PASS",
        gate_flags=["below_ma25"],
    )

    assert verdict == "WATCH"


def test_b1_environment_verdict_gate_below_ma25_caps_rebound_exact_pass_in_neutral() -> None:
    verdict = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="rebound",
        environment_state="neutral",
        current_verdict="PASS",
        gate_flags=["below_ma25"],
    )

    assert verdict == "WATCH"


def test_b1_compute_environment_gate_strong_cooldown_expires_at_two_bar_boundary() -> None:
    profile = get_method_environment_profile(method="b1", state="strong")

    gate = b1_reviewer._compute_b1_environment_gate(
        close=pd.Series([10.0, 10.1, 10.2, 10.3]),
        ma25=pd.Series([9.5, 9.5, 9.5, 9.5]),
        dif=pd.Series([0.3, -0.1, -0.2, -0.3]),
        dea=pd.Series([0.2, 0.0, 0.0, 0.0]),
        profile=profile,
    )

    assert gate["cooldown_active"] is False
    assert "cooldown_active" not in gate["triggered_flags"]


def test_b1_compute_environment_gate_weak_cooldown_expires_at_four_bar_boundary() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")

    gate = b1_reviewer._compute_b1_environment_gate(
        close=pd.Series([10.0, 10.1, 10.2, 10.3, 10.4, 10.5]),
        ma25=pd.Series([9.5, 9.5, 9.5, 9.5, 9.5, 9.5]),
        dif=pd.Series([0.3, -0.1, -0.2, -0.2, -0.2, -0.2]),
        dea=pd.Series([0.2, 0.0, 0.0, 0.0, 0.0, 0.0]),
        profile=profile,
    )

    assert gate["cooldown_active"] is False
    assert "cooldown_active" not in gate["triggered_flags"]


def test_b1_compute_environment_gate_golden_cross_cancels_recent_death_cross_cooldown() -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")

    gate = b1_reviewer._compute_b1_environment_gate(
        close=pd.Series([10.0, 10.1, 10.2, 10.3, 10.4]),
        ma25=pd.Series([9.5, 9.5, 9.5, 9.5, 9.5]),
        dif=pd.Series([0.3, -0.1, -0.2, 0.1, 0.2]),
        dea=pd.Series([0.2, 0.0, -0.1, 0.0, 0.05]),
        profile=profile,
    )

    assert gate["cooldown_active"] is False
    assert "cooldown_active" not in gate["triggered_flags"]


def test_b1_compute_environment_gate_does_not_set_runup_flag_below_70pct_threshold() -> None:
    profile = get_method_environment_profile(method="b1", state="strong")
    close = pd.Series([10.0] * 25 + [10.5, 11.0, 12.0, 13.5, 15.2])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
    )

    assert gate["runup_pct"] == 52.0
    assert "runup_over_limit" not in gate["triggered_flags"]


def test_b1_compute_environment_gate_sets_runup_flag_in_strong_at_60pct_threshold() -> None:
    profile = get_method_environment_profile(method="b1", state="strong")
    close = pd.Series([10.0] * 25 + [10.5, 11.0, 12.0, 14.0, 16.2])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
    )

    assert gate["runup_pct"] == 62.0
    assert "runup_over_limit" in gate["triggered_flags"]


def test_b1_compute_environment_gate_uses_80pct_runup_threshold_in_weak() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")
    close = pd.Series([10.0] * 25 + [10.2, 11.0, 14.0, 16.0, 17.5])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
    )

    assert gate["runup_pct"] == 75.0
    assert "runup_over_limit" not in gate["triggered_flags"]


def test_b1_compute_environment_gate_sets_runup_flag_in_weak_at_80pct_threshold() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")
    close = pd.Series([10.0] * 25 + [10.2, 11.0, 14.0, 16.0, 18.2])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
    )

    assert gate["runup_pct"] == 82.0
    assert "runup_over_limit" in gate["triggered_flags"]


def test_b1_compute_environment_gate_sets_sideways_flag_for_tight_recent_range() -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    close = pd.Series([10.0] * 20 + [10.0, 10.08, 10.05, 10.12, 10.09, 10.11, 10.07, 10.1, 10.06, 10.1])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.9] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
    )

    assert gate["sideways_amplitude_pct"] == 1.2
    assert "sideways_tight_range" in gate["triggered_flags"]


def test_b1_compute_environment_gate_does_not_set_sideways_flag_above_20pct_threshold() -> None:
    profile = get_method_environment_profile(method="b1", state="strong")
    close = pd.Series([10.0] * 20 + [10.0, 10.5, 11.0, 11.5, 12.0, 11.8, 11.7, 11.6, 11.9, 12.1])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.9] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
    )

    assert gate["sideways_amplitude_pct"] == 21.0
    assert "sideways_tight_range" not in gate["triggered_flags"]


def test_b1_compute_environment_gate_sets_weekly_slope_flag_when_26w_slope_is_not_rising() -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    trade_dates = pd.bdate_range(end="2026-04-30", periods=140)
    close = pd.Series([10.0] * len(trade_dates))

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
        trade_dates=pd.Series(trade_dates),
    )

    assert gate["weekly_slope_26w"] == 0.0
    assert "weekly_slope_not_rising" in gate["triggered_flags"]


def test_b1_compute_environment_gate_does_not_set_weekly_slope_flag_above_threshold() -> None:
    profile = get_method_environment_profile(method="b1", state="strong")
    trade_dates = pd.bdate_range(end="2026-04-30", periods=140)
    close = pd.Series([10.0 + idx * 0.15 for idx in range(len(trade_dates))])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
        trade_dates=pd.Series(trade_dates),
    )

    assert gate["weekly_slope_26w"] > 0.2
    assert "weekly_slope_not_rising" not in gate["triggered_flags"]


def test_b1_compute_environment_gate_sets_weekly_macd_cooldown_flag_on_recent_weekly_death_cross() -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    trade_dates = pd.bdate_range(end="2026-04-30", periods=140)
    close = pd.Series([10.0 + idx * 0.05 for idx in range(len(trade_dates))])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
        trade_dates=pd.Series(trade_dates),
        weekly_dif=pd.Series([0.4, 0.3, 0.1, -0.1]),
        weekly_dea=pd.Series([0.2, 0.25, 0.2, 0.05]),
    )

    assert gate["weekly_macd_cooldown_active"] is True
    assert "weekly_macd_cooldown_active" in gate["triggered_flags"]


def test_b1_compute_environment_gate_clears_weekly_macd_cooldown_after_weekly_golden_cross() -> None:
    profile = get_method_environment_profile(method="b1", state="neutral")
    trade_dates = pd.bdate_range(end="2026-04-30", periods=140)
    close = pd.Series([10.0 + idx * 0.05 for idx in range(len(trade_dates))])

    gate = b1_reviewer._compute_b1_environment_gate(
        close=close,
        ma25=pd.Series([9.5] * len(close)),
        dif=pd.Series([0.3, 0.35, 0.4, 0.45, 0.5]),
        dea=pd.Series([0.2, 0.25, 0.3, 0.35, 0.4]),
        profile=profile,
        trade_dates=pd.Series(trade_dates),
        weekly_dif=pd.Series([0.4, -0.1, -0.2, 0.1]),
        weekly_dea=pd.Series([0.2, 0.0, -0.1, 0.0]),
    )

    assert gate["weekly_macd_cooldown_active"] is False
    assert "weekly_macd_cooldown_active" not in gate["triggered_flags"]


def test_b1_environment_verdict_gate_runup_demotes_but_sideways_is_diagnostic() -> None:
    runup_verdict = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="trend_start",
        environment_state="strong",
        current_verdict="PASS",
        gate_flags=["runup_over_limit"],
    )
    sideways_verdict = b1_reviewer._apply_b1_environment_verdict_gate(
        high_return_match="exact",
        family="distribution",
        environment_state="neutral",
        current_verdict="PASS",
        gate_flags=["sideways_tight_range"],
    )

    assert runup_verdict == "WATCH"
    assert sideways_verdict == "PASS"


def test_b1_review_high_return_trend_start_keeps_pass_and_records_weekly_slope_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = get_method_environment_profile(method="b1", state="strong")
    history = _constructive_b1_history()
    history["dif"] = 0.5
    history["dea"] = 0.4

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.5)
    monkeypatch.setattr(b1_reviewer, "infer_signal_type", lambda **kwargs: "trend_start")
    monkeypatch.setattr(b1_reviewer, "apply_macd_verdict_gate", lambda **kwargs: kwargs["current_verdict"])
    monkeypatch.setattr(
        b1_reviewer,
        "_compute_b1_environment_gate",
        lambda **kwargs: {
            "score_penalty": 0.0,
            "cooldown_active": False,
            "cooldown_reason": None,
            "runup_pct": None,
            "drawdown_pct": None,
            "below_ma25": False,
            "sideways_amplitude_pct": None,
            "weekly_slope_26w": 0.05,
            "weekly_macd_cooldown_active": False,
            "triggered_flags": ["weekly_slope_not_rising"],
        },
    )

    review = review_b1_symbol_history(
        code="000007.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000007.SZ_day.png",
        profile=profile,
    )

    assert review["pass_family"] == "trend_start"
    assert review["pass_family_tier"] == "core"
    assert review["score_combo_key"] == "trend_start|T4|P3|V4|A5|M3.5"
    assert review["high_return_combo_match"] == "exact"
    assert review["verdict"] == "PASS"
    assert review["gate_weekly_slope_26w"] == 0.05
    assert "weekly_slope_not_rising" in review["gate_flags"]


def test_b1_resolve_daily_macd_lines_prefers_precomputed_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame(
        {
            "close": [10.0, 10.1, 10.2],
            "dif": [0.1, 0.2, 0.3],
            "dea": [0.05, 0.1, 0.15],
        }
    )

    def _unexpected_compute_macd(frame: pd.DataFrame) -> pd.DataFrame:
        raise AssertionError("compute_macd should not be called when dif/dea are precomputed")

    monkeypatch.setattr(b1_reviewer, "compute_macd", _unexpected_compute_macd)

    dif, dea = b1_reviewer._resolve_daily_macd_lines(frame)

    assert dif.tolist() == [0.1, 0.2, 0.3]
    assert dea.tolist() == [0.05, 0.1, 0.15]


def test_b1_review_uses_environment_profile_for_price_position_scoring() -> None:
    profile_weak = get_method_environment_profile(method="b1", state="weak")
    profile_strong = get_method_environment_profile(method="b1", state="strong")
    history = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=130),
            "open": [10.0] * 120 + [8.7, 8.8, 8.9, 9.0, 9.1, 9.2, 9.3, 9.4, 9.45, 9.5],
            "high": [10.2] * 120 + [9.0, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.65, 9.7, 9.75],
            "low": [9.8] * 120 + [8.6, 8.7, 8.8, 8.9, 9.0, 9.05, 9.1, 9.15, 9.18, 9.2],
            "close": [10.0] * 120 + [8.8, 8.9, 9.0, 9.1, 9.2, 9.3, 9.4, 9.45, 9.5, 9.55],
            "vol": [900.0] * 130,
        }
    )

    weak_review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile_weak,
    )
    strong_review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile_strong,
    )

    assert weak_review["price_position"] == 4.0
    assert strong_review["price_position"] == 3.0
    assert weak_review["total_score"] > strong_review["total_score"]


def test_b1_review_uses_environment_profile_for_verdict_thresholds() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")
    history = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=130),
            "open": [10.0] * 120 + [8.7, 8.8, 8.9, 9.0, 9.1, 9.2, 9.3, 9.4, 9.45, 9.5],
            "high": [10.2] * 120 + [9.0, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.65, 9.7, 9.75],
            "low": [9.8] * 120 + [8.6, 8.7, 8.8, 8.9, 9.0, 9.05, 9.1, 9.15, 9.18, 9.2],
            "close": [10.0] * 120 + [8.8, 8.9, 9.0, 9.1, 9.2, 9.3, 9.4, 9.45, 9.5, 9.55],
            "vol": [900.0] * 130,
        }
    )

    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["verdict"] in {"WATCH", "FAIL"}
    assert review["verdict"] != "PASS"
    assert review["total_score"] < profile.pass_threshold


def test_b1_weak_profile_caps_even_high_score_setups_below_pass() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")

    verdict = b1_reviewer.infer_b1_verdict(
        total_score=4.45,
        volume_behavior=4.0,
        signal_type="rebound",
        trend_structure=4.0,
        price_position=4.0,
        previous_abnormal_move=5.0,
        macd_phase=3.9,
        close_above_ma25_pct=-4.0,
        ma25_above_zxdkx_pct=8.0,
        close_above_zxdq_pct=-6.0,
        day_pct=-1.0,
        profile=profile,
    )

    assert verdict == "WATCH"


def test_b1_review_weak_profile_caps_high_score_setup_below_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = get_method_environment_profile(method="b1", state="weak")
    history = _constructive_b1_history()

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 5.0)
    monkeypatch.setattr(
        b1_reviewer,
        "classify_weekly_macd_trend",
        lambda frame, pick_date: type(
            "Trend",
            (),
            {
                "phase": "rising",
                "is_rising_initial": False,
                "is_top_divergence": False,
                "phase_index": 3,
                "wave_stage": "强势",
                "metrics": {"dif": 1.0, "dea": 0.8, "previous_spread": 0.1, "hist_change_rate": 1.0},
                "transition_warnings": (),
            },
        )(),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "classify_daily_macd_trend",
        lambda frame, pick_date: type(
            "Trend",
            (),
            {
                "phase": "falling",
                "is_rising_initial": False,
                "is_top_divergence": False,
                "phase_index": 2,
                "wave_stage": "强势",
                "metrics": {"dif": 0.1, "dea": 0.2, "previous_spread": -0.1, "hist_change_rate": 0.6},
                "transition_warnings": (),
            },
        )(),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "_has_recent_daily_macd_death_cross",
        lambda frame: False,
    )

    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["raw_total_score"] > profile.pass_threshold
    assert review["total_score"] < profile.pass_threshold
    assert review["signal_type"] in {"rebound", "trend_start"}
    assert review["pass_family"] is None
    assert review["pass_family_tier"] == "none"
    assert review["verdict"] == "FAIL"


def test_b1_weak_profile_restores_pass_for_zxdkx_repair_whitelist() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")

    verdict = b1_reviewer.infer_b1_verdict(
        total_score=4.4,
        volume_behavior=5.0,
        signal_type="rebound",
        trend_structure=4.0,
        price_position=4.0,
        previous_abnormal_move=5.0,
        macd_phase=3.84,
        close_above_ma25_pct=-6.0,
        ma25_above_zxdkx_pct=8.0,
        close_above_zxdq_pct=-6.0,
        day_pct=-1.0,
        close_above_zxdkx_pct=1.5,
        profile=profile,
    )

    assert verdict == "PASS"


def test_b1_weak_profile_restores_pass_for_zxdkx_repair_whitelist_with_price_position_four() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")

    verdict = b1_reviewer.infer_b1_verdict(
        total_score=4.18,
        volume_behavior=4.0,
        signal_type="rebound",
        trend_structure=4.0,
        price_position=4.0,
        previous_abnormal_move=5.0,
        macd_phase=3.88,
        close_above_ma25_pct=-4.98,
        ma25_above_zxdkx_pct=6.83,
        close_above_zxdkx_pct=1.51,
        close_above_zxdq_pct=-5.2,
        day_pct=-0.3,
        profile=profile,
    )

    assert verdict == "PASS"


def test_b1_review_weak_whitelist_excludes_weekly_initial_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = get_method_environment_profile(method="b1", state="weak")
    history = _constructive_b1_history()

    monkeypatch.setattr(b1_reviewer, "_score_b1_trend_structure", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_price_position", lambda **kwargs: 4.0)
    monkeypatch.setattr(b1_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(b1_reviewer, "map_macd_phase_score", lambda **kwargs: 3.9)
    monkeypatch.setattr(
        b1_reviewer,
        "_resolve_zx_lines",
        lambda frame: (
            pd.Series([10.0] * len(frame), index=frame.index),
            pd.Series([9.4] * len(frame), index=frame.index),
        ),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "_resolve_series",
        lambda frame, column, fallback: pd.Series([10.0] * len(frame), index=frame.index)
        if column == "ma25"
        else fallback,
    )
    monkeypatch.setattr(
        b1_reviewer,
        "classify_weekly_macd_trend",
        lambda frame, pick_date: type(
            "Trend",
            (),
            {
                "phase": "rising",
                "phase_index": 1,
                "wave_stage": "背离",
                "wave_label": "一浪",
                "is_rising_initial": True,
                "is_top_divergence": True,
                "metrics": {"dif": 1.0, "dea": 0.8, "previous_spread": 0.1, "hist_change_rate": 1.0},
                "transition_warnings": (),
            },
        )(),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "classify_daily_macd_trend",
        lambda frame, pick_date: type(
            "Trend",
            (),
            {
                "phase": "falling",
                "phase_index": 2,
                "wave_stage": "强势转分歧",
                "wave_label": "二浪",
                "is_rising_initial": False,
                "is_top_divergence": False,
                "metrics": {"dif": 0.1, "dea": 0.2, "previous_spread": -0.1, "hist_change_rate": 0.6},
                "transition_warnings": (),
            },
        )(),
    )
    monkeypatch.setattr(b1_reviewer, "_has_recent_daily_macd_death_cross", lambda frame: False)

    review = review_b1_symbol_history(
        code="301636.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/301636.SZ_day.png",
        profile=profile,
    )

    assert review["raw_total_score"] >= 4.18
    assert review["total_score"] < 4.18
    assert review["verdict"] == "WATCH"


def test_b1_review_weak_profile_caps_real_002452_wave3_divergence_sample_to_watch() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")
    prepared = pd.read_feather(Path("/home/pi/.agents/skills/stock-select/runtime/prepared/2026-04-30.feather"))
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce", format="mixed")
    history = (
        prepared[
            (prepared["ts_code"] == "002452.SZ")
            & (prepared["trade_date"] <= pd.Timestamp("2026-03-24"))
        ]
        .copy()
        .sort_values("trade_date")
        .reset_index(drop=True)
    )

    review = review_b1_symbol_history(
        code="002452.SZ",
        pick_date="2026-03-24",
        history=history,
        chart_path="/tmp/002452.SZ_day.png",
        profile=profile,
    )

    assert review["signal_type"] == "rebound"
    assert review["pass_family"] == "rebound"
    assert review["pass_family_tier"] == "near"
    assert review["verdict"] == "WATCH"


def test_b1_previous_abnormal_move_reuses_b2_event_logic() -> None:
    open_ = pd.Series([10.0] * 92 + [100.0, 92.0, 94.0, 96.0])
    close = pd.Series([10.0] * 92 + [100.0, 92.0, 94.0, 96.0])
    low = pd.Series([9.8] * 92 + [100.0, 91.0, 93.0, 95.0])
    volume = pd.Series([1000.0] * 92 + [9000.0, 2000.0, 1800.0, 1600.0])

    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=pd.DataFrame(
            {
                "trade_date": pd.bdate_range(end="2026-04-30", periods=len(close)),
                "open": open_,
                "high": close + 1.0,
                "low": low,
                "close": close,
                "vol": volume,
            }
        ),
        chart_path="/tmp/000001.SZ_day.png",
    )

    expected = _score_b2_previous_abnormal_move(open_=open_, close=close, low=low, volume=volume)
    assert expected == 5.0
    assert review["previous_abnormal_move"] == expected


def test_b1_volume_behavior_scores_peak_bullish_and_pullback_volume_expansion() -> None:
    open_ = pd.Series([10.0] * 20)
    close = pd.Series([10.2] * 20)
    volume = pd.Series([1000.0] * 20)
    volume.iloc[5] = 3600.0
    volume.iloc[-3:] = [1200.0, 1400.0, 1600.0]
    close.iloc[-3:] = [10.0, 9.9, 9.8]

    score = b1_reviewer._score_b1_volume_behavior(open_=open_, close=close, volume=volume)

    assert score == 5.0


def test_b1_volume_behavior_treats_any_pullback_expansion_as_support() -> None:
    open_ = pd.Series([10.0] * 20)
    close = pd.Series([10.2] * 20)
    volume = pd.Series([1000.0] * 20)
    volume.iloc[5] = 1760.0
    close.iloc[-3:] = [9.9, 9.8, 9.7]
    volume.iloc[-3:] = [1000.0, 1100.0, 950.0]

    score = b1_reviewer._score_b1_volume_behavior(open_=open_, close=close, volume=volume)

    assert score == 4.0


def test_b1_volume_behavior_scores_four_for_large_bearish_peak_with_pullback_volume_expansion() -> None:
    open_ = pd.Series([10.0] * 20)
    close = pd.Series([10.2] * 20)
    volume = pd.Series([1000.0] * 20)
    open_.iloc[5] = 10.5
    close.iloc[5] = 10.0
    volume.iloc[5] = 4800.0
    volume.iloc[-3:] = [1200.0, 1400.0, 1600.0]
    close.iloc[-3:] = [10.0, 9.9, 9.8]

    score = b1_reviewer._score_b1_volume_behavior(open_=open_, close=close, volume=volume)

    assert score == 4.0


def test_b1_macd_phase_rewards_weekly_red_histogram_above_water_without_divergence() -> None:
    score = b1_reviewer._score_b1_macd_phase(
        history_len=80,
        weekly_macd=b1_reviewer.B1WeeklyMacdContext(
            red_histogram=True,
            above_water=True,
            diverging=False,
            improving=True,
        ),
        daily_recent_death_cross=False,
    )

    assert score == 5.0


def test_b1_macd_phase_penalizes_recent_three_day_daily_death_cross() -> None:
    score = b1_reviewer._score_b1_macd_phase(
        history_len=80,
        weekly_macd=b1_reviewer.B1WeeklyMacdContext(
            red_histogram=True,
            above_water=True,
            diverging=False,
            improving=True,
        ),
        daily_recent_death_cross=True,
    )

    assert score == 2.0


def test_b1_macd_phase_scores_one_when_weekly_histogram_is_not_red() -> None:
    score = b1_reviewer._score_b1_macd_phase(
        history_len=80,
        weekly_macd=b1_reviewer.B1WeeklyMacdContext(
            red_histogram=False,
            above_water=True,
            diverging=False,
            improving=False,
        ),
        daily_recent_death_cross=False,
    )

    assert score == 1.0


def test_b1_review_uses_precomputed_zx_fields_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    history = _constructive_b1_history()
    history["ma25"] = 14.5
    history["zxdq"] = 14.2
    history["zxdkx"] = 13.7
    history["bbi"] = 14.8

    monkeypatch.setattr(
        b1_reviewer,
        "classify_weekly_macd_trend",
        lambda frame, pick_date: type("Trend", (), {"phase": "rising", "is_rising_initial": False, "is_top_divergence": False})(),
    )
    monkeypatch.setattr(
        b1_reviewer,
        "classify_daily_macd_trend",
        lambda frame, pick_date: type("Trend", (), {"phase": "rising", "is_rising_initial": True, "is_top_divergence": False})(),
    )

    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["trend_structure"] == 5.0
    assert "N型回调" in review["comment"]
    assert "超卖" in review["comment"]


def test_infer_b1_verdict_caps_generic_trend_start_pass_to_watch() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=4.2,
        volume_behavior=4.0,
        signal_type="trend_start",
        trend_structure=4.0,
        price_position=4.0,
        macd_phase=4.0,
        close_above_ma25_pct=-1.0,
        ma25_above_zxdkx_pct=4.5,
        close_above_zxdq_pct=-3.0,
        day_pct=1.3,
    )

    assert verdict == "WATCH"


def test_infer_b1_verdict_lifts_elastic_distribution_risk_to_watch() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=3.2,
        volume_behavior=4.0,
        signal_type="distribution_risk",
        trend_structure=1.0,
        price_position=3.0,
        previous_abnormal_move=5.0,
        macd_phase=3.5,
        close_above_ma25_pct=-4.0,
        day_pct=-3.0,
    )

    assert verdict == "WATCH"


def test_infer_b1_verdict_keeps_non_elastic_distribution_risk_failed() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=3.2,
        volume_behavior=4.0,
        signal_type="distribution_risk",
        trend_structure=1.0,
        price_position=5.0,
        previous_abnormal_move=5.0,
        macd_phase=3.5,
        close_above_ma25_pct=1.0,
        day_pct=1.0,
    )

    assert verdict == "FAIL"


def test_infer_b1_verdict_lifts_elastic_rebound_fail_to_watch() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=3.1,
        volume_behavior=4.0,
        signal_type="rebound",
        trend_structure=3.0,
        price_position=2.0,
        previous_abnormal_move=3.0,
        macd_phase=3.2,
    )

    assert verdict == "WATCH"


def test_infer_b1_verdict_keeps_weak_rebound_failed() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=3.1,
        volume_behavior=4.0,
        signal_type="rebound",
        trend_structure=2.0,
        price_position=2.0,
        previous_abnormal_move=3.0,
        macd_phase=3.2,
    )

    assert verdict == "FAIL"


def test_infer_b1_verdict_allows_repair_style_trend_start_pass() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=3.85,
        volume_behavior=4.0,
        signal_type="trend_start",
        trend_structure=4.0,
        price_position=3.0,
        macd_phase=3.8,
        close_above_ma25_pct=-2.0,
        ma25_above_zxdkx_pct=4.0,
        close_above_zxdq_pct=-6.5,
        day_pct=0.5,
    )

    assert verdict == "PASS"


def test_infer_b1_verdict_keeps_repair_style_rebound_pass() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=4.05,
        volume_behavior=4.0,
        signal_type="rebound",
        trend_structure=4.0,
        price_position=4.0,
        macd_phase=3.9,
        close_above_ma25_pct=-4.0,
        ma25_above_zxdkx_pct=8.0,
        close_above_zxdq_pct=-6.0,
        day_pct=-1.0,
    )

    assert verdict == "PASS"


def test_infer_b1_verdict_caps_overextended_rebound_pass_to_watch() -> None:
    verdict = b1_reviewer.infer_b1_verdict(
        total_score=4.2,
        volume_behavior=5.0,
        signal_type="rebound",
        trend_structure=3.0,
        price_position=5.0,
        macd_phase=3.8,
        close_above_ma25_pct=1.5,
        ma25_above_zxdkx_pct=9.0,
        close_above_zxdq_pct=-4.0,
        day_pct=-1.0,
    )

    assert verdict == "WATCH"
