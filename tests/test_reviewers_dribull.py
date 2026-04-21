from types import SimpleNamespace

import pandas as pd
import pytest

import stock_select.reviewers.b2 as b2_reviewer
import stock_select.reviewers.dribull as dribull_reviewer


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=170),
            "open": [10.0] * 170,
            "high": [10.2] * 170,
            "low": [9.8] * 170,
            "close": [10.0] * 170,
            "vol": [1000.0] * 170,
        }
    )


@pytest.mark.parametrize(
    ("weekly_label", "daily_state_name", "expected_b2", "expected_dribull"),
    [
        ("wave3", "wave2_end_valid", 5.0, 4.0),
        ("wave3", "wave4_end_valid", 5.0, 5.0),
    ],
)
def test_dribull_review_uses_distinct_macd_mapping_from_b2(
    monkeypatch: pytest.MonkeyPatch,
    weekly_label: str,
    daily_state_name: str,
    expected_b2: float,
    expected_dribull: float,
) -> None:
    fake_weekly = SimpleNamespace(label=weekly_label, details={})
    fake_daily_wave = SimpleNamespace(label="wave2_end" if daily_state_name == "wave2_end_valid" else "wave4_end", details={"third_wave_gain": 0.10})
    fake_daily_state = SimpleNamespace(state=daily_state_name, metrics={"third_wave_gain": 0.10})

    for module in (b2_reviewer, dribull_reviewer):
        monkeypatch.setattr(module, "_score_b2_trend_structure", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "_score_b2_price_position", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "_score_b2_volume_behavior", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "_score_b2_previous_abnormal_move", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "classify_weekly_macd_wave", lambda *args, **kwargs: fake_weekly, raising=False)
        monkeypatch.setattr(module, "classify_daily_macd_wave", lambda *args, **kwargs: fake_daily_wave, raising=False)
        monkeypatch.setattr(module, "classify_daily_macd_state", lambda *args, **kwargs: fake_daily_state, raising=False)

    history = _history()
    b2_review = b2_reviewer.review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )
    dribull_review = dribull_reviewer.review_dribull_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert b2_review["macd_phase"] == expected_b2
    assert dribull_review["macd_phase"] == expected_dribull
