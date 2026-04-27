from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from stock_select.strategies import compute_macd, compute_zx_lines


def _prepare_daily_chart_frame(df: pd.DataFrame, bars: int = 120) -> pd.DataFrame:
    chart_df = df.copy()
    chart_df["date"] = pd.to_datetime(chart_df["date"])
    chart_df = chart_df.sort_values("date").reset_index(drop=True)

    chart_df["ma25"] = chart_df["close"].astype(float).rolling(window=25, min_periods=25).mean()
    chart_df["vol_ma120"] = chart_df["volume"].astype(float).rolling(window=120, min_periods=1).mean()
    zxdq, zxdkx = compute_zx_lines(chart_df)
    chart_df["zxdq"] = zxdq.values
    chart_df["zxdkx"] = zxdkx.values
    macd = compute_macd(chart_df)
    chart_df["dif"] = macd["dif"].to_numpy()
    chart_df["dea"] = macd["dea"].to_numpy()
    chart_df["macd_hist"] = macd["macd_hist"].to_numpy()
    if bars > 0:
        chart_df = chart_df.tail(bars).reset_index(drop=True)

    frame = pd.DataFrame(
        {
            "Open": chart_df["open"].astype(float).to_numpy(),
            "High": chart_df["high"].astype(float).to_numpy(),
            "Low": chart_df["low"].astype(float).to_numpy(),
            "Close": chart_df["close"].astype(float).to_numpy(),
            "Volume": chart_df["volume"].astype(float).to_numpy(),
            "ma25": chart_df["ma25"].astype(float).to_numpy(),
            "zxdq": chart_df["zxdq"].astype(float).to_numpy(),
            "zxdkx": chart_df["zxdkx"].astype(float).to_numpy(),
            "vol_ma120": chart_df["vol_ma120"].astype(float).to_numpy(),
            "dif": chart_df["dif"].astype(float).to_numpy(),
            "dea": chart_df["dea"].astype(float).to_numpy(),
            "macd_hist": chart_df["macd_hist"].astype(float).to_numpy(),
        },
        index=pd.DatetimeIndex(chart_df["date"]),
    )
    frame.index.name = "Date"
    return frame


def export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
    frame = _prepare_daily_chart_frame(df, bars=bars)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    addplots = []
    if frame["ma25"].notna().any():
        addplots.append(mpf.make_addplot(frame["ma25"], color="#7d3c98", width=1.0, label="MA25"))
    if frame["zxdq"].notna().any():
        addplots.append(mpf.make_addplot(frame["zxdq"], color="#e67e22", width=1.0, label="zxdq"))
    if frame["zxdkx"].notna().any():
        addplots.append(mpf.make_addplot(frame["zxdkx"], color="#2980b9", width=1.0, label="zxdkx"))
    if frame["vol_ma120"].notna().any():
        addplots.append(mpf.make_addplot(frame["vol_ma120"], panel=1, color="#6c757d", width=1.0, label="Vol MA120"))
    if frame["dif"].notna().any():
        addplots.append(mpf.make_addplot(frame["dif"], panel=2, color="#1f4e79", width=1.0, ylabel="MACD", label="DIF"))
    if frame["dea"].notna().any():
        addplots.append(mpf.make_addplot(frame["dea"], panel=2, color="#f1c40f", width=1.0, label="DEA"))
    if frame["macd_hist"].notna().any():
        addplots.append(
            mpf.make_addplot(
                frame["macd_hist"],
                panel=2,
                type="bar",
                color=["#d84f4f" if value >= 0 else "#2f9d57" for value in frame["macd_hist"]],
                alpha=0.7,
            )
        )
    style = mpf.make_mpf_style(
        marketcolors=mpf.make_marketcolors(up="#dc3545", down="#28a745", inherit=True),
        gridstyle="-",
        facecolor="white",
        figcolor="white",
    )
    fig, axes = mpf.plot(
        frame,
        type="candle",
        style=style,
        addplot=addplots,
        volume=True,
        panel_ratios=(5, 2, 2),
        title=f"{code} Daily",
        ylabel="Price",
        ylabel_lower="Volume",
        figsize=(10, 6),
        tight_layout=True,
        returnfig=True,
    )
    try:
        axes[0].legend(loc="upper left", fontsize=8)
        axes[2].legend(loc="upper left", fontsize=8)
        axes[4].legend(loc="upper left", fontsize=8)
        fig.savefig(str(out_path), dpi=144)
    finally:
        plt.close(fig)
    return out_path
