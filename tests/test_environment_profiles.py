import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_select.environment_profiles import get_method_environment_profile
from stock_select.review_protocol import compute_b2_weighted_total_for_profile


@pytest.mark.parametrize(
    ("method", "state"),
    [
        ("b1", "weak"),
        ("b1", "neutral"),
        ("b1", "strong"),
        ("b2", "weak"),
        ("b2", "neutral"),
        ("b2", "strong"),
    ],
)
def test_all_supported_method_environment_profiles_resolve(method: str, state: str) -> None:
    profile = get_method_environment_profile(method=method, state=state)

    assert profile.method == method
    assert profile.state == state


def test_b1_weak_profile_raises_price_position_weight() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")

    assert profile.weights["price_position"] > profile.weights["trend_structure"]
    assert profile.pass_threshold >= 4.0
    assert profile.signal_weight is None


def test_b2_strong_profile_favors_macd_and_trend() -> None:
    profile = get_method_environment_profile(method="b2", state="strong")

    assert profile.weights["macd_phase"] >= 0.35
    assert profile.subscore_mode["price_position"] == "breakout_tolerant"
    assert "signal" not in profile.weights
    assert profile.signal_weight == 0.15


def test_b2_neutral_profile_rebalances_toward_price_and_volume() -> None:
    profile = get_method_environment_profile(method="b2", state="neutral")

    assert profile.weights["price_position"] > profile.weights["macd_phase"]
    assert profile.weights["volume_behavior"] > 0.0
    assert profile.weights["trend_structure"] >= 0.16


def test_retrieved_profile_mutation_does_not_affect_fresh_lookup() -> None:
    profile = get_method_environment_profile(method="b2", state="weak")
    profile.weights["macd_phase"] = 9.99
    profile.subscore_mode["price_position"] = "mutated"

    fresh_profile = get_method_environment_profile(method="b2", state="weak")

    assert fresh_profile.weights["macd_phase"] == 0.25
    assert fresh_profile.subscore_mode["price_position"] == "low_risk_required"


def test_get_method_environment_profile_rejects_unsupported_method() -> None:
    with pytest.raises(ValueError, match="Unsupported environment profile method"):
        get_method_environment_profile(method="dribull", state="strong")


def test_get_method_environment_profile_rejects_unsupported_state() -> None:
    with pytest.raises(ValueError, match="Unsupported environment profile method"):
        get_method_environment_profile(method="b1", state="panic")


def test_b2_profiles_produce_distinct_weighted_totals_for_same_scores() -> None:
    scores = {
        "trend_structure": 4.0,
        "price_position": 5.0,
        "volume_behavior": 3.0,
        "previous_abnormal_move": 5.0,
        "macd_phase": 4.5,
    }
    weak = compute_b2_weighted_total_for_profile(
        scores,
        profile=get_method_environment_profile(method="b2", state="weak"),
        signal="B2",
    )
    neutral = compute_b2_weighted_total_for_profile(
        scores,
        profile=get_method_environment_profile(method="b2", state="neutral"),
        signal="B2",
    )
    strong = compute_b2_weighted_total_for_profile(
        scores,
        profile=get_method_environment_profile(method="b2", state="strong"),
        signal="B2",
    )

    assert weak < strong
    assert neutral != weak
    assert neutral != strong
