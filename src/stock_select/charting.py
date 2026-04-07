from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from choreographer.browsers.chromium import ChromeNotFoundError
from plotly.subplots import make_subplots

from stock_select.b1_logic import compute_zx_lines


def _calc_rangebreaks_daily(trade_dates: pd.DatetimeIndex) -> list[dict]:
    if len(trade_dates) == 0:
        return [dict(bounds=["sat", "mon"])]

    normalized = trade_dates.normalize()
    min_date = normalized.min()
    max_date = normalized.max()
    business_days = pd.bdate_range(min_date, max_date)
    trade_set = set(normalized)
    missing = [day.strftime("%Y-%m-%d") for day in business_days if day not in trade_set]

    breaks: list[dict] = [dict(bounds=["sat", "mon"])]
    if missing:
        breaks.append(dict(values=missing))
    return breaks


def build_daily_chart(df: pd.DataFrame, code: str, bars: int = 120) -> go.Figure:
    chart_df = df.copy()
    chart_df["date"] = pd.to_datetime(chart_df["date"])
    chart_df = chart_df.sort_values("date").reset_index(drop=True)

    zxdq, zxdkx = compute_zx_lines(chart_df)
    chart_df["_zxdq"] = zxdq.values
    chart_df["_zxdkx"] = zxdkx.values
    if bars > 0:
        chart_df = chart_df.tail(bars).reset_index(drop=True)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
        subplot_titles=[f"{code} Daily", "Volume"],
        specs=[[{"type": "candlestick"}], [{"type": "bar"}]],
    )

    x = chart_df["date"]
    fig.add_trace(
        go.Candlestick(
            x=x,
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            increasing_line_color="#dc3545",
            decreasing_line_color="#28a745",
            increasing_fillcolor="#dc3545",
            decreasing_fillcolor="#28a745",
            name="K",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=x, y=chart_df["_zxdq"], mode="lines", name="zxdq", line=dict(color="#e67e22")),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=chart_df["_zxdkx"],
            mode="lines",
            name="zxdkx",
            line=dict(color="#2980b9", dash="dot"),
        ),
        row=1,
        col=1,
    )

    up_mask = chart_df["close"] >= chart_df["open"]
    colors = np.where(up_mask, "rgba(220,53,69,0.7)", "rgba(40,167,69,0.7)")
    fig.add_trace(
        go.Bar(x=x, y=chart_df["volume"], marker_color=colors.tolist(), name="volume"),
        row=2,
        col=1,
    )

    fig.update_layout(
        template="plotly_white",
        height=560,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    fig.update_xaxes(rangebreaks=_calc_rangebreaks_daily(pd.DatetimeIndex(x)))
    return fig


def export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
    fig = build_daily_chart(df, code, bars=bars)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pio.write_image(fig, str(out_path), format="png")
    except ChromeNotFoundError as exc:
        raise RuntimeError(
            "PNG chart export requires Google Chrome to be installed for Kaleido. "
            "Install Chrome manually or run `kaleido_get_chrome` in the active environment."
        ) from exc
    except RuntimeError as exc:
        message = str(exc)
        if "google chrome" not in message.lower():
            raise
        raise RuntimeError(
            "PNG chart export requires Google Chrome to be installed for Kaleido. "
            "Install Chrome manually or run `kaleido_get_chrome` in the active environment."
        ) from exc
    except ValueError as exc:
        message = str(exc)
        if "kaleido" not in message.lower():
            raise
        raise RuntimeError(
            "PNG chart export requires the optional 'kaleido' package. "
            "Install project dependencies again so Kaleido is available."
        ) from exc
    return out_path
