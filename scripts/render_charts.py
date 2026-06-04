#!/usr/bin/env python3
# /// script
# dependencies = [
#   "matplotlib>=3.8",
#   "mplfinance>=0.12.10b0",
#   "pandas>=2.2",
# ]
# ///
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description="Render stock-select daily chart PNGs.")
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    charts = payload.get("charts")
    if not isinstance(charts, list):
        raise SystemExit("invalid chart payload: missing charts list")

    for idx, chart in enumerate(charts, start=1):
        code = str(chart["code"])
        out_path = Path(str(chart["out_path"]))
        rows = chart.get("rows")
        if not isinstance(rows, list) or not rows:
            raise SystemExit(f"no price history found for candidate: {code}")
        print(f"[chart] candidate {idx}/{len(charts)} code={code}", flush=True)
        export_daily_chart(rows, code, out_path)
    return 0


def export_daily_chart(rows: list[dict[str, Any]], code: str, out_path: Path, bars: int = 120) -> Path:
    frame = _prepare_daily_chart_frame(rows, bars=bars)
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


def _prepare_daily_chart_frame(rows: list[dict[str, Any]], bars: int) -> pd.DataFrame:
    source = pd.DataFrame(rows)
    source["date"] = pd.to_datetime(source["date"])
    source = source.sort_values("date").reset_index(drop=True)
    source["vol_ma120"] = source["volume"].astype(float).rolling(window=120, min_periods=1).mean()
    if bars > 0:
        source = source.tail(bars).reset_index(drop=True)

    frame = pd.DataFrame(
        {
            "Open": source["open"].astype(float).to_numpy(),
            "High": source["high"].astype(float).to_numpy(),
            "Low": source["low"].astype(float).to_numpy(),
            "Close": source["close"].astype(float).to_numpy(),
            "Volume": source["volume"].astype(float).to_numpy(),
            "ma25": pd.to_numeric(source["ma25"], errors="coerce").to_numpy(),
            "zxdq": pd.to_numeric(source["zxdq"], errors="coerce").to_numpy(),
            "zxdkx": pd.to_numeric(source["zxdkx"], errors="coerce").to_numpy(),
            "vol_ma120": source["vol_ma120"].astype(float).to_numpy(),
            "dif": pd.to_numeric(source["dif"], errors="coerce").to_numpy(),
            "dea": pd.to_numeric(source["dea"], errors="coerce").to_numpy(),
            "macd_hist": pd.to_numeric(source["macd_hist"], errors="coerce").to_numpy(),
        },
        index=pd.DatetimeIndex(source["date"]),
    )
    frame.index.name = "Date"
    return frame


if __name__ == "__main__":
    raise SystemExit(main())
