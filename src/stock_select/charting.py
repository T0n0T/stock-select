from __future__ import annotations

from pathlib import Path

import mplfinance as mpf
import pandas as pd

from stock_select.b1_logic import compute_zx_lines


def _prepare_daily_chart_frame(df: pd.DataFrame, bars: int = 120) -> pd.DataFrame:
    chart_df = df.copy()
    chart_df["date"] = pd.to_datetime(chart_df["date"])
    chart_df = chart_df.sort_values("date").reset_index(drop=True)

    zxdq, zxdkx = compute_zx_lines(chart_df)
    chart_df["zxdq"] = zxdq.values
    chart_df["zxdkx"] = zxdkx.values
    if bars > 0:
        chart_df = chart_df.tail(bars).reset_index(drop=True)

    frame = pd.DataFrame(
        {
            "Open": chart_df["open"].astype(float).to_numpy(),
            "High": chart_df["high"].astype(float).to_numpy(),
            "Low": chart_df["low"].astype(float).to_numpy(),
            "Close": chart_df["close"].astype(float).to_numpy(),
            "Volume": chart_df["volume"].astype(float).to_numpy(),
            "zxdq": chart_df["zxdq"].astype(float).to_numpy(),
            "zxdkx": chart_df["zxdkx"].astype(float).to_numpy(),
        },
        index=pd.DatetimeIndex(chart_df["date"]),
    )
    frame.index.name = "Date"
    return frame


def export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
    frame = _prepare_daily_chart_frame(df, bars=bars)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    addplots = []
    if frame["zxdq"].notna().any():
        addplots.append(mpf.make_addplot(frame["zxdq"], color="#e67e22", width=1.0))
    if frame["zxdkx"].notna().any():
        addplots.append(mpf.make_addplot(frame["zxdkx"], color="#2980b9", width=1.0))
    style = mpf.make_mpf_style(
        marketcolors=mpf.make_marketcolors(up="#dc3545", down="#28a745", inherit=True),
        gridstyle="-",
        facecolor="white",
        figcolor="white",
    )
    mpf.plot(
        frame,
        type="candle",
        style=style,
        addplot=addplots,
        volume=True,
        title=f"{code} Daily",
        ylabel="Price",
        ylabel_lower="Volume",
        figsize=(10, 6),
        tight_layout=True,
        savefig=dict(fname=str(out_path), dpi=144),
    )
    return out_path
