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


def compute_b1_tightening_columns(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = _resolve_volume_series(df)
    ref_close = close.shift(1)

    chg_d = (close - ref_close) / ref_close * 100.0
    amp_d = (high - low) / ref_close * 100.0
    body_d = (open_ - close) / ref_close * 100.0
    vm3 = volume.rolling(window=3, min_periods=1).mean()
    vm5 = volume.rolling(window=5, min_periods=1).mean()
    vm10 = volume.rolling(window=10, min_periods=1).mean()
    m5 = close.rolling(window=5, min_periods=1).mean()
    v_shrink = (vm3 < vm10).fillna(False)

    high_pos = ((high.rolling(window=20, min_periods=1).max() - low.rolling(window=20, min_periods=1).min()) /
                low.rolling(window=20, min_periods=1).min() * 100.0) > 15.0
    vol_big = (volume > vm5 * 1.3) | (volume > vm10 * 1.5)
    bad_dump = (((body_d > 6.0) | (chg_d < -5.5)) & vol_big & high_pos).fillna(False)
    dump_day = _barslast(bad_dump)
    cool_off = pd.Series(5.0, index=df.index)
    cool_off = cool_off.mask(bad_dump.rolling(window=10, min_periods=1).sum() >= 2, 10.0)
    in_rev = (dump_day >= cool_off) & (dump_day <= 15.0)
    shape_ok = ((amp_d <= 10.0) & (chg_d >= -4.0) & (chg_d <= 4.0)).fillna(False)
    cg_ok = ((close > m5) | (m5 >= m5.shift(1)) | (((close - m5).abs() / m5) * 100.0 < 1.5)).fillna(False)
    safe_mode = ((dump_day >= cool_off) & (~in_rev | (shape_ok & cg_ok))).fillna(False)

    st_t1 = close.ewm(span=10, adjust=False).mean().ewm(span=10, adjust=False).mean()
    lt_t1 = (
        close.rolling(window=14, min_periods=1).mean()
        + close.rolling(window=28, min_periods=1).mean()
        + close.rolling(window=57, min_periods=1).mean()
        + close.rolling(window=114, min_periods=1).mean()
    ) / 4.0
    cross_up = (st_t1 > lt_t1) & (st_t1.shift(1) <= lt_t1.shift(1))
    c_days = _barslast(cross_up.fillna(False))
    waiver = (((c_days >= 0.0) & (c_days <= 30.0) & (st_t1 > lt_t1)) | (st_t1 > lt_t1 * 1.03)).fillna(False)

    lt_dir = pd.Series(1.0, index=df.index)
    mature = pd.Series(range(1, len(df) + 1), index=df.index, dtype=float) > 114.0
    lt_dir.loc[mature] = (lt_t1.loc[mature] > lt_t1.shift(1).loc[mature]).map({True: 1.0, False: -1.0})
    lt_flips = lt_dir.ne(lt_dir.shift(1)).fillna(False).rolling(window=30, min_periods=1).sum()
    lt_filter = ((lt_flips <= 2.0) | waiver).fillna(False)

    return pd.DataFrame(
        {
            "chg_d": chg_d,
            "amp_d": amp_d,
            "body_d": body_d,
            "vm3": vm3,
            "vm5": vm5,
            "vm10": vm10,
            "m5": m5,
            "v_shrink": v_shrink,
            "safe_mode": safe_mode,
            "lt_filter": lt_filter,
        },
        index=df.index,
    )


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


def _barslast(flags: pd.Series) -> pd.Series:
    values = flags.fillna(False).astype(bool).tolist()
    out: list[float] = []
    last_true: int | None = None
    default_distance = float(len(values) + 1)
    for idx, value in enumerate(values):
        if value:
            last_true = idx
            out.append(0.0)
        elif last_true is None:
            out.append(default_distance)
        else:
            out.append(float(idx - last_true))
    return pd.Series(out, index=flags.index, dtype=float)


__all__ = [
    "DEFAULT_B1_CONFIG",
    "DEFAULT_MAX_VOL_LOOKBACK",
    "DEFAULT_TOP_M",
    "DEFAULT_TURNOVER_WINDOW",
    "DEFAULT_WEEKLY_MA_PERIODS",
    "build_top_turnover_pool",
    "compute_b1_tightening_columns",
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
