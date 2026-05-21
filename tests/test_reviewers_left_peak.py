from types import SimpleNamespace

import pandas as pd

from stock_select.environment_profiles import get_method_environment_profile
from stock_select.reviewers.left_peak import review_left_peak_symbol_history


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-05-19", periods=170),
            "open": [10.0] * 170,
            "high": [10.2] * 170,
            "low": [9.8] * 170,
            "close": [10.0] * 170,
            "vol": [1000.0] * 170,
        }
    )


def test_left_peak_review_returns_anchor_macd_and_layer_fields() -> None:
    profile = get_method_environment_profile(method="left_peak", state="neutral")

    review = review_left_peak_symbol_history(
        code="000001.SZ",
        pick_date="2026-05-19",
        history=_history(),
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["method"] == "left_peak"
    assert review["review_type"] == "baseline"
    assert {
        "trend_structure",
        "price_position",
        "volume_behavior",
        "previous_abnormal_move",
        "macd_phase",
        "left_peak_anchor_score",
        "structure_combo_score",
        "macd_context_score",
        "environment_score",
        "risk_penalty_score",
        "left_peak_date",
        "left_peak_first_bear_open",
        "left_peak_pick_close",
        "left_peak_b_div_a",
        "left_peak_abs_ba_minus_1",
        "weekly_macd_phase",
        "weekly_macd_wave_label",
        "weekly_macd_wave_stage",
        "daily_macd_phase",
        "score_layer",
        "score_layer_score",
    }.issubset(review)
    assert isinstance(review["total_score"], float)
    assert review["verdict"] in {"PASS", "WATCH", "FAIL"}
    assert "left_peak" in review["comment"]


def test_left_peak_review_promotes_tight_anchor_core_combo_with_unmature_macd(monkeypatch) -> None:
    import stock_select.reviewers.left_peak as left_peak_reviewer

    profile = get_method_environment_profile(method="left_peak", state="weak")

    monkeypatch.setattr(left_peak_reviewer, "_score_b1_trend_structure", lambda **kwargs: 3.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 4.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(left_peak_reviewer, "map_macd_phase_score", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(left_peak_reviewer, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("falling"))
    monkeypatch.setattr(
        left_peak_reviewer,
        "_compute_left_peak_anchor",
        lambda frame, pick_date: left_peak_reviewer.LeftPeakAnchor(
            left_peak_date="2026-05-01",
            left_peak_high=10.0,
            breakout_date="2026-05-10",
            first_bear_date="2026-05-02",
            first_bear_open=10.0,
            pick_close=10.03,
            b_div_a=1.003,
            abs_ba_minus_1=0.003,
            a_lt_b=True,
        ),
    )

    review = review_left_peak_symbol_history(
        code="000001.SZ",
        pick_date="2026-05-19",
        history=_history(),
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["score_combo_key"] == "T3|P3|V4|A5|M3.6"
    assert review["verdict"] == "PASS"
    assert review["score_layer"] == "PASS-A"
    assert review["left_peak_abs_ba_minus_1"] == 0.003


def test_left_peak_review_rejects_weak_environment_when_anchor_is_far(monkeypatch) -> None:
    import stock_select.reviewers.left_peak as left_peak_reviewer

    profile = get_method_environment_profile(method="left_peak", state="weak")

    monkeypatch.setattr(left_peak_reviewer, "_score_b1_trend_structure", lambda **kwargs: 3.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_price_position", lambda **kwargs: 3.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 4.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(left_peak_reviewer, "map_macd_phase_score", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(left_peak_reviewer, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("falling"))
    monkeypatch.setattr(
        left_peak_reviewer,
        "_compute_left_peak_anchor",
        lambda frame, pick_date: left_peak_reviewer.LeftPeakAnchor(
            left_peak_date="2026-05-01",
            left_peak_high=10.0,
            breakout_date="2026-05-10",
            first_bear_date="2026-05-02",
            first_bear_open=10.0,
            pick_close=11.2,
            b_div_a=1.12,
            abs_ba_minus_1=0.12,
            a_lt_b=True,
        ),
    )

    review = review_left_peak_symbol_history(
        code="000001.SZ",
        pick_date="2026-05-19",
        history=_history(),
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["verdict"] == "FAIL"
    assert review["score_layer"] == "FAIL-anchor"
    assert "anchor_far" in review["gate_flags"]


def test_left_peak_review_promotes_strong_tight_anchor_to_pass_b(monkeypatch) -> None:
    import stock_select.reviewers.left_peak as left_peak_reviewer

    profile = get_method_environment_profile(method="left_peak", state="strong")

    monkeypatch.setattr(left_peak_reviewer, "_score_b1_trend_structure", lambda **kwargs: 2.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_price_position", lambda **kwargs: 2.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 3.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 5.0)
    monkeypatch.setattr(left_peak_reviewer, "map_macd_phase_score", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(left_peak_reviewer, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("falling"))
    monkeypatch.setattr(
        left_peak_reviewer,
        "_compute_left_peak_anchor",
        lambda frame, pick_date: left_peak_reviewer.LeftPeakAnchor(
            left_peak_date="2026-05-01",
            left_peak_high=10.0,
            breakout_date="2026-05-10",
            first_bear_date="2026-05-02",
            first_bear_open=10.0,
            pick_close=10.02,
            b_div_a=1.002,
            abs_ba_minus_1=0.002,
            a_lt_b=True,
        ),
    )

    review = review_left_peak_symbol_history(
        code="000001.SZ",
        pick_date="2026-05-19",
        history=_history(),
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["verdict"] == "PASS"
    assert review["score_layer"] == "PASS-B"


def test_left_peak_review_keeps_neutral_non_core_anchor_as_watch_a(monkeypatch) -> None:
    import stock_select.reviewers.left_peak as left_peak_reviewer

    profile = get_method_environment_profile(method="left_peak", state="neutral")

    monkeypatch.setattr(left_peak_reviewer, "_score_b1_trend_structure", lambda **kwargs: 2.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_price_position", lambda **kwargs: 2.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b1_volume_behavior", lambda *args, **kwargs: 3.0)
    monkeypatch.setattr(left_peak_reviewer, "_score_b2_previous_abnormal_move", lambda **kwargs: 3.0)
    monkeypatch.setattr(left_peak_reviewer, "map_macd_phase_score", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "apply_b1_macd_divergence_penalty", lambda **kwargs: 3.6)
    monkeypatch.setattr(left_peak_reviewer, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(left_peak_reviewer, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("falling"))
    monkeypatch.setattr(
        left_peak_reviewer,
        "_compute_left_peak_anchor",
        lambda frame, pick_date: left_peak_reviewer.LeftPeakAnchor(
            left_peak_date="2026-05-01",
            left_peak_high=10.0,
            breakout_date="2026-05-10",
            first_bear_date="2026-05-02",
            first_bear_open=10.0,
            pick_close=10.09,
            b_div_a=1.009,
            abs_ba_minus_1=0.009,
            a_lt_b=True,
        ),
    )

    review = review_left_peak_symbol_history(
        code="000001.SZ",
        pick_date="2026-05-19",
        history=_history(),
        chart_path="/tmp/000001.SZ_day.png",
        profile=profile,
    )

    assert review["verdict"] == "WATCH"
    assert review["score_layer"] == "WATCH-A"


def _trend(phase: str) -> SimpleNamespace:
    return SimpleNamespace(
        phase=phase,
        direction="up" if phase == "rising" else "down",
        is_rising_initial=False,
        is_top_divergence=False,
        bars_in_phase=3,
        phase_index=1,
        reason="fixture",
        metrics={},
        wave_label="一浪",
        wave_direction="up",
        wave_stage="强势",
        transition_warnings=(),
    )
