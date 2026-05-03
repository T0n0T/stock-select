import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_select.environment_profiles import get_method_environment_profile


def test_b1_weak_profile_raises_price_position_weight() -> None:
    profile = get_method_environment_profile(method="b1", state="weak")

    assert profile.weights["price_position"] > profile.weights["trend_structure"]
    assert profile.pass_threshold >= 4.0


def test_b2_strong_profile_favors_macd_and_trend() -> None:
    profile = get_method_environment_profile(method="b2", state="strong")

    assert profile.weights["macd_phase"] >= 0.35
    assert profile.subscore_mode["price_position"] == "breakout_tolerant"


def test_get_method_environment_profile_rejects_unsupported_method() -> None:
    with pytest.raises(ValueError, match="Unsupported environment profile method"):
        get_method_environment_profile(method="dribull", state="strong")
