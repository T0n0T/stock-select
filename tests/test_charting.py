from pathlib import Path

import pandas as pd

from stock_select.charting import _prepare_daily_chart_frame, export_daily_chart


def _sample_daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-04-06", "2026-04-01", "2026-04-03", "2026-04-02"]
            ),
            "open": [10.8, 10.0, 10.4, 10.5],
            "high": [11.2, 10.8, 10.7, 10.9],
            "low": [10.6, 9.8, 10.2, 10.1],
            "close": [11.0, 10.6, 10.5, 10.7],
            "volume": [1500.0, 1000.0, 900.0, 1200.0],
        }
    )


def test_prepare_daily_chart_frame_sorts_and_shapes_columns() -> None:
    frame = _prepare_daily_chart_frame(_sample_daily_frame(), bars=0)

    assert {"Open", "High", "Low", "Close", "Volume", "zxdq", "zxdkx"}.issubset(frame.columns)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.is_monotonic_increasing
    assert frame.index[0] == pd.Timestamp("2026-04-01")
    assert frame.index[-1] == pd.Timestamp("2026-04-06")


def test_export_daily_chart_writes_png_file(tmp_path: Path) -> None:
    out_path = tmp_path / "000001_day.png"

    result = export_daily_chart(_sample_daily_frame(), "000001.SZ", out_path)

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_export_daily_chart_respects_bars_limit() -> None:
    frame = _prepare_daily_chart_frame(_sample_daily_frame(), bars=2)

    assert len(frame) == 2
    assert list(frame.index) == [pd.Timestamp("2026-04-03"), pd.Timestamp("2026-04-06")]


def test_prepare_daily_chart_frame_includes_macd_columns() -> None:
    frame = _prepare_daily_chart_frame(_sample_daily_frame(), bars=0)

    assert list(frame.columns) == [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "zxdq",
        "zxdkx",
        "dif",
        "dea",
        "macd_hist",
    ]
    for column in ("dif", "dea", "macd_hist"):
        assert frame[column].index.equals(frame.index)


def test_prepare_daily_chart_frame_keeps_macd_series_aligned_after_bars_trim() -> None:
    frame = _prepare_daily_chart_frame(_sample_daily_frame(), bars=2)

    assert list(frame.index) == [pd.Timestamp("2026-04-03"), pd.Timestamp("2026-04-06")]
    assert list(frame[["dif", "dea", "macd_hist"]].columns) == ["dif", "dea", "macd_hist"]
