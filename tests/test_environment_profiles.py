import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_select.environment_profiles import get_method_environment_profile


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
