from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from stock_select.indicators import compute_macd


DEFAULT_B1_CONFIG: dict[str, float] = {
    "j_threshold": 15.0,
    "j_q_threshold": 0.10,
}

DEFAULT_TURNOVER_WINDOW = 43
DEFAULT_WEEKLY_MA_PERIODS = (10, 20, 30)
DEFAULT_MAX_VOL_LOOKBACK = 20
DEFAULT_TOP_M = 5000


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


def compute_weekly_close(df: pd.DataFrame) -> pd.Series:
    if isinstance(df.index, pd.DatetimeIndex):
        close = df["close"].astype(float)
    else:
        date_col = "trade_date" if "trade_date" in df.columns else "date"
        close = df.assign(**{date_col: pd.to_datetime(df[date_col])}).set_index(date_col)["close"].astype(float)

    idx = close.index
    year_week = idx.isocalendar().year.astype(str) + "-" + idx.isocalendar().week.astype(str).str.zfill(2)
    weekly = close.groupby(year_week).last()
    last_date_per_week = close.groupby(year_week).apply(lambda s: s.index[-1])
    weekly.index = pd.DatetimeIndex(last_date_per_week.to_numpy())
    return weekly.dropna()


def compute_weekly_ma_bull(
    df: pd.DataFrame,
    ma_periods: tuple[int, int, int] = (20, 60, 120),
) -> pd.Series:
    daily = df.copy()
    date_col = "trade_date" if "trade_date" in daily.columns else "date"
    daily[date_col] = pd.to_datetime(daily[date_col])
    daily = daily.sort_values(date_col)
    weekly_close = compute_weekly_close(daily)
    short, medium, long = ma_periods
    ma_short = weekly_close.rolling(short, min_periods=short).mean()
    ma_medium = weekly_close.rolling(medium, min_periods=medium).mean()
    ma_long = weekly_close.rolling(long, min_periods=long).mean()
    weekly_bull = ((ma_short > ma_medium) & (ma_medium > ma_long)).astype(float)
    aligned = weekly_bull.reindex(pd.DatetimeIndex(daily[date_col])).ffill().fillna(0.0).astype(bool)
    return pd.Series(aligned.to_numpy(), index=df.index)


def compute_expanding_j_quantile(series: pd.Series, q_threshold: float) -> pd.Series:
    values = pd.Series(series, copy=False).astype(float)
    return values.expanding(min_periods=1).quantile(q_threshold)


def max_vol_not_bearish(df: pd.DataFrame, lookback: int) -> pd.Series:
    volume = _resolve_volume_series(df)
    out: list[bool] = []
    for idx in range(len(df)):
        start = max(0, idx - lookback + 1)
        window = volume.iloc[start : idx + 1].dropna()
        if window.empty:
            out.append(False)
            continue
        max_index = window.idxmax()
        out.append(bool(df.loc[max_index, "close"] >= df.loc[max_index, "open"]))
    return pd.Series(out, index=df.index)


def build_top_turnover_pool(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    *,
    top_m: int,
) -> dict[pd.Timestamp, list[str]]:
    if top_m <= 0:
        return {}

    pool: dict[pd.Timestamp, list[tuple[float, str]]] = {}
    for symbol, frame in prepared_by_symbol.items():
        if frame.empty:
            continue
        working = frame.copy()
        if "trade_date" in working.columns:
            date_col = "trade_date"
        elif "date" in working.columns:
            date_col = "date"
        else:
            continue
        if "turnover_n" not in working.columns:
            continue
        working[date_col] = pd.to_datetime(working[date_col], errors="coerce", format="mixed")
        working["turnover_n"] = pd.to_numeric(working["turnover_n"], errors="coerce")
        for _, row in working.iterrows():
            if pd.isna(row[date_col]) or pd.isna(row["turnover_n"]):
                continue
            trade_date = pd.Timestamp(row[date_col])
            pool.setdefault(trade_date, []).append((float(row["turnover_n"]), symbol))

    result: dict[pd.Timestamp, list[str]] = {}
    for trade_date, items in pool.items():
        ranked = sorted(items, key=lambda item: item[0], reverse=True)[:top_m]
        result[trade_date] = [symbol for _, symbol in ranked]
    return result


def run_b1_screen(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    config: dict,
) -> list[dict]:
    results, _stats = run_b1_screen_with_stats(prepared_by_symbol, pick_date, config)
    return results


def run_b1_screen_with_stats(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    pick_date: pd.Timestamp,
    config: dict,
) -> tuple[list[dict], dict[str, int]]:
    results: list[dict] = []
    target_date = pd.Timestamp(pick_date)
    stats = {
        "total_symbols": len(prepared_by_symbol),
        "eligible": 0,
        "fail_j": 0,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_weekly_ma": 0,
        "fail_max_vol": 0,
        "selected": 0,
    }

    for symbol, prepared in prepared_by_symbol.items():
        if prepared.empty:
            continue

        frame = prepared.copy()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        daily = frame.loc[frame["trade_date"] == target_date]
        if daily.empty:
            continue

        stats["eligible"] += 1
        row = daily.iloc[-1]
        j_threshold = float(config.get("j_threshold", DEFAULT_B1_CONFIG["j_threshold"]))
        q_threshold = float(config.get("j_q_threshold", DEFAULT_B1_CONFIG["j_q_threshold"]))
        j_series = frame.loc[frame["trade_date"] <= target_date, "J"]
        j_quantile = float(compute_expanding_j_quantile(j_series, q_threshold).iloc[-1])

        if not (float(row["J"]) < j_threshold or float(row["J"]) <= j_quantile):
            stats["fail_j"] += 1
            continue
        if pd.isna(row["zxdkx"]):
            stats["fail_insufficient_history"] += 1
            continue
        if not (float(row["close"]) > float(row["zxdkx"])):
            stats["fail_close_zxdkx"] += 1
            continue
        if not (float(row["zxdq"]) > float(row["zxdkx"])):
            stats["fail_zxdq_zxdkx"] += 1
            continue
        if not bool(row["weekly_ma_bull"]):
            stats["fail_weekly_ma"] += 1
            continue
        if not bool(row["max_vol_not_bearish"]):
            stats["fail_max_vol"] += 1
            continue

        results.append(
            {
                "code": symbol,
                "pick_date": target_date.strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "turnover_n": float(row["turnover_n"]),
            }
        )
        stats["selected"] += 1

    return results, stats


def _resolve_volume_series(df: pd.DataFrame) -> pd.Series:
    if "volume" in df.columns:
        return df["volume"].astype(float)
    if "vol" in df.columns:
        return df["vol"].astype(float)
    msg = "Expected a volume or vol column."
    raise KeyError(msg)


__all__ = [
    "DEFAULT_B1_CONFIG",
    "DEFAULT_MAX_VOL_LOOKBACK",
    "DEFAULT_TOP_M",
    "DEFAULT_TURNOVER_WINDOW",
    "DEFAULT_WEEKLY_MA_PERIODS",
        "build_top_turnover_pool",
        "compute_expanding_j_quantile",
        "compute_kdj",
        "compute_macd",
        "compute_turnover_n",
        "compute_weekly_close",
        "compute_weekly_ma_bull",
    "compute_zx_lines",
    "max_vol_not_bearish",
    "run_b1_screen",
    "run_b1_screen_with_stats",
]
