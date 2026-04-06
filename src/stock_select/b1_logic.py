from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def compute_turnover_n(df: pd.DataFrame, window: int) -> pd.Series:
    volume = _resolve_volume_series(df)
    turnover = ((df["open"] + df["close"]) / 2.0) * volume
    return turnover.rolling(window=window, min_periods=1).sum()


def compute_kdj(df: pd.DataFrame, n: int = 9) -> pd.DataFrame:
    if df.empty:
        return df.assign(K=pd.Series(dtype=float), D=pd.Series(dtype=float), J=pd.Series(dtype=float))

    low_n = df["low"].rolling(window=n, min_periods=1).min()
    high_n = df["high"].rolling(window=n, min_periods=1).max()
    rsv = ((df["close"] - low_n) / (high_n - low_n + 1e-9) * 100.0).fillna(0.0)

    k_values: list[float] = []
    d_values: list[float] = []
    prev_k = 50.0
    prev_d = 50.0
    for idx, value in enumerate(rsv):
        if idx == 0:
            current_k = 50.0
            current_d = 50.0
        else:
            current_k = (2.0 * prev_k + float(value)) / 3.0
            current_d = (2.0 * prev_d + current_k) / 3.0
        k_values.append(current_k)
        d_values.append(current_d)
        prev_k = current_k
        prev_d = current_d

    k_series = pd.Series(k_values, index=df.index, name="K")
    d_series = pd.Series(d_values, index=df.index, name="D")
    j_series = 3.0 * k_series - 2.0 * d_series
    return df.assign(K=k_series, D=d_series, J=j_series)


def compute_zx_lines(
    df: pd.DataFrame,
    m1: int = 14,
    m2: int = 28,
    m3: int = 57,
    m4: int = 114,
    zxdq_span: int = 10,
) -> tuple[pd.Series, pd.Series]:
    close = df["close"].astype(float)
    zxdq = close.ewm(span=zxdq_span, adjust=False).mean().ewm(span=zxdq_span, adjust=False).mean()
    zxdkx = (
        close.rolling(m1, min_periods=m1).mean()
        + close.rolling(m2, min_periods=m2).mean()
        + close.rolling(m3, min_periods=m3).mean()
        + close.rolling(m4, min_periods=m4).mean()
    ) / 4.0
    return zxdq, zxdkx


def compute_weekly_ma_bull(
    df: pd.DataFrame,
    ma_periods: tuple[int, int, int] = (20, 60, 120),
) -> pd.Series:
    daily = df.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    daily = daily.sort_values("trade_date")
    weekly_close = (
        daily.set_index("trade_date")["close"].astype(float).resample("W-FRI").last().dropna()
    )
    short, medium, long = ma_periods
    ma_short = weekly_close.rolling(short, min_periods=short).mean()
    ma_medium = weekly_close.rolling(medium, min_periods=medium).mean()
    ma_long = weekly_close.rolling(long, min_periods=long).mean()
    weekly_bull = ((ma_short > ma_medium) & (ma_medium > ma_long)).astype(float)
    aligned = weekly_bull.reindex(daily["trade_date"]).ffill().fillna(0.0).astype(bool)
    return pd.Series(aligned.to_numpy(), index=df.index)


def max_vol_not_bearish(df: pd.DataFrame, lookback: int) -> pd.Series:
    volume = _resolve_volume_series(df)
    out: list[bool] = []
    for idx in range(len(df)):
        start = max(0, idx - lookback + 1)
        window = volume.iloc[start : idx + 1]
        max_index = window.idxmax()
        out.append(bool(df.loc[max_index, "close"] >= df.loc[max_index, "open"]))
    return pd.Series(out, index=df.index)


def run_b1_screen(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    config: dict,
) -> list[dict]:
    results: list[dict] = []
    target_date = pd.Timestamp(pick_date)
    for symbol, prepared in prepared_by_symbol.items():
        if prepared.empty:
            continue

        frame = prepared.copy()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        daily = frame.loc[frame["trade_date"] == target_date]
        if daily.empty:
            continue

        row = daily.iloc[-1]
        j_threshold = float(config.get("j_threshold", 20.0))
        q_threshold = float(config.get("j_q_threshold", 0.2))
        j_series = frame.loc[frame["trade_date"] <= target_date, "J"]
        j_quantile = float(j_series.quantile(q_threshold))

        passes = bool(
            (float(row["J"]) < j_threshold or float(row["J"]) <= j_quantile)
            and float(row["close"]) > float(row["zxdkx"])
            and float(row["zxdq"]) > float(row["zxdkx"])
            and bool(row["weekly_ma_bull"])
            and bool(row["max_vol_not_bearish"])
        )
        if not passes:
            continue

        results.append(
            {
                "code": symbol,
                "pick_date": target_date.strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "turnover_n": float(row["turnover_n"]),
            }
        )

    return results


def _resolve_volume_series(df: pd.DataFrame) -> pd.Series:
    if "volume" in df.columns:
        return df["volume"].astype(float)
    if "vol" in df.columns:
        return df["vol"].astype(float)
    msg = "Expected a volume or vol column."
    raise KeyError(msg)
