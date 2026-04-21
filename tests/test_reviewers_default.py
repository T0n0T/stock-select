import pandas as pd

from stock_select.reviewers.default import review_symbol_history


def test_default_review_keeps_invalid_macd_in_low_band() -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-30", periods=60),
            "open": [10.0] * 45 + [12.0, 12.5, 13.0, 13.4, 13.8, 13.6, 13.2, 12.8, 12.2, 11.8, 11.4, 11.0, 10.8, 10.6, 10.5],
            "high": [10.2] * 45 + [12.2, 12.8, 13.2, 13.6, 14.0, 13.8, 13.4, 13.0, 12.5, 12.0, 11.6, 11.2, 11.0, 10.8, 10.7],
            "low": [9.8] * 45 + [11.8, 12.2, 12.8, 13.2, 13.5, 13.1, 12.7, 12.3, 11.8, 11.4, 11.0, 10.7, 10.5, 10.4, 10.3],
            "close": [10.0] * 45 + [12.1, 12.7, 13.1, 13.5, 13.9, 13.3, 12.9, 12.4, 11.9, 11.5, 11.1, 10.8, 10.6, 10.5, 10.4],
            "vol": [1000.0] * 60,
        }
    )

    review = review_symbol_history(
        method="default",
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert 1.0 <= review["macd_phase"] <= 2.0
