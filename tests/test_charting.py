from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from stock_select.charting import build_daily_chart, export_daily_chart


def _sample_daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-06"]
            ),
            "open": [10.0, 10.5, 10.4, 10.8],
            "high": [10.8, 10.9, 10.7, 11.2],
            "low": [9.8, 10.1, 10.2, 10.6],
            "close": [10.6, 10.7, 10.5, 11.0],
            "volume": [1000.0, 1200.0, 900.0, 1500.0],
        }
    )


def test_build_daily_chart_returns_plotly_figure() -> None:
    fig = build_daily_chart(_sample_daily_frame(), "000001.SZ")

    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 4


def test_export_daily_chart_writes_output_file(tmp_path: Path) -> None:
    out_path = tmp_path / "000001_day.html"

    result = export_daily_chart(_sample_daily_frame(), "000001.SZ", out_path)

    assert result == out_path
    assert out_path.exists()
