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


def test_dribull_review_uses_trend_state_macd_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    weekly_trend = SimpleNamespace(
        phase="rising",
        is_rising_initial=False,
        is_top_divergence=False,
        phase_index=1,
        wave_stage="强势",
        metrics={"dif": 0.5, "dea": 0.3, "spread": 0.2, "previous_spread": 0.1},
        transition_warnings=(),
    )
    daily_trend = SimpleNamespace(
        phase="rising",
        is_rising_initial=True,
        is_top_divergence=False,
        phase_index=1,
        wave_stage="强势",
        metrics={"dif": 0.3, "dea": 0.1, "spread": 0.2, "previous_spread": 0.1},
        transition_warnings=(),
    )

    for module in (b2_reviewer, dribull_reviewer):
        monkeypatch.setattr(module, "_score_b2_trend_structure", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "_score_b2_price_position", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "_score_b2_volume_behavior", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "_score_b2_previous_abnormal_move", lambda **kwargs: 4.0, raising=False)
        monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: weekly_trend, raising=False)
        monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: daily_trend, raising=False)

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

    assert b2_review["macd_phase"] == 5.0
    assert dribull_review["macd_phase"] == 5.0
    assert "日线MACD上升浪（上升初期）" in dribull_review["comment"]
    assert "wave" not in dribull_review["comment"]
