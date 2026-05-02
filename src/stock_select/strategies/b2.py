from __future__ import annotations

import numpy as np
import pandas as pd

from stock_select.strategies.b1 import compute_kdj

_B2_REQUIRED_COLUMNS = (
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "turnover_n",
)
_B2_NUMERIC_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "turnover_n",
)


def run_b2_screen(
    prepared_table: pd.DataFrame,
    pick_date: pd.Timestamp,
) -> list[dict]:
    results, _stats = run_b2_screen_with_stats(prepared_table, pick_date=pick_date)
    return results


def run_b2_screen_with_stats(
    prepared_table: pd.DataFrame,
    pick_date: pd.Timestamp,
) -> tuple[list[dict], dict[str, int]]:
    target_date = pd.Timestamp(pick_date)
    candidates: list[dict] = []
    grouped = prepared_table.groupby("ts_code", sort=False) if not prepared_table.empty else []
    stats = {
        "total_symbols": prepared_table["ts_code"].nunique() if not prepared_table.empty and "ts_code" in prepared_table.columns else 0,
        "eligible": 0,
        "fail_insufficient_history": 0,
        "fail_pre_ok": 0,
        "fail_pct": 0,
        "fail_volume": 0,
        "fail_k_shape": 0,
        "fail_j_up": 0,
        "fail_tr_ok": 0,
        "fail_above_lt": 0,
        "fail_duplicate_b2": 0,
        "fail_no_signal": 0,
        "selected": 0,
        "selected_b2": 0,
        "selected_b3": 0,
        "selected_b3_plus": 0,
    }

    for code, prepared in grouped:
        if prepared.empty:
            continue

        if _missing_required_columns(prepared):
            stats["eligible"] += 1
            stats["fail_insufficient_history"] += 1
            continue

        frame = _normalize_b2_frame(prepared)
        if _has_invalid_required_inputs(prepared, frame):
            stats["eligible"] += 1
            stats["fail_insufficient_history"] += 1
            continue

        history = frame.loc[frame["trade_date"] <= target_date].reset_index(drop=True)
        daily = history.loc[history["trade_date"] == target_date]
        if daily.empty:
            continue

        stats["eligible"] += 1
        if len(history) < 3:
            stats["fail_insufficient_history"] += 1
            continue

        evaluated = _build_b2_signal_frame(history, code=code)
        row = evaluated.iloc[-1]
        signal = _resolve_signal(row)
        if signal is not None:
            candidates.append(
                {
                    "code": code,
                    "pick_date": target_date.strftime("%Y-%m-%d"),
                    "close": float(row["close"]),
                    "turnover_n": float(row["turnover_n"]),
                    "signal": signal,
                }
            )
            stats["selected"] += 1
            stats[f"selected_{signal.lower().replace('+', '_plus')}"] += 1
            continue

        if not bool(row["pre_ok"]):
            stats["fail_pre_ok"] += 1
        elif not bool(row["pct_ok"]):
            stats["fail_pct"] += 1
        elif not bool(row["volume_ok"]):
            stats["fail_volume"] += 1
        elif not bool(row["k_shape"]):
            stats["fail_k_shape"] += 1
        elif not bool(row["j_up"]):
            stats["fail_j_up"] += 1
        elif not bool(row["tr_ok"]):
            stats["fail_tr_ok"] += 1
        elif not bool(row["above_lt"]):
            stats["fail_above_lt"] += 1
        elif not bool(row["raw_b2_unique"]):
            stats["fail_duplicate_b2"] += 1
        else:
            stats["fail_no_signal"] += 1

    return candidates, stats


def _missing_required_columns(frame: pd.DataFrame) -> set[str]:
    return set(_B2_REQUIRED_COLUMNS) - set(frame.columns)


def _normalize_b2_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce", format="mixed")
    for column in _B2_NUMERIC_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "volume" in normalized.columns:
        normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce")
    elif "vol" in normalized.columns:
        normalized["volume"] = pd.to_numeric(normalized["vol"], errors="coerce")
    normalized = normalized.sort_values("trade_date").reset_index(drop=True)
    return normalized


def _coerced_numeric_columns(original: pd.DataFrame, normalized: pd.DataFrame) -> set[str]:
    invalid_columns: set[str] = set()
    for column in _B2_NUMERIC_COLUMNS:
        original_series = original[column]
        normalized_series = normalized[column]
        invalid_mask = original_series.notna() & normalized_series.isna()
        if bool(invalid_mask.any()):
            invalid_columns.add(column)
    if "volume" in original.columns:
        volume_mask = original["volume"].notna() & normalized["volume"].isna()
        if bool(volume_mask.any()):
            invalid_columns.add("volume")
    elif "vol" in original.columns:
        volume_mask = original["vol"].notna() & normalized["volume"].isna()
        if bool(volume_mask.any()):
            invalid_columns.add("volume")
    else:
        invalid_columns.add("volume")
    return invalid_columns


def _has_invalid_required_inputs(original: pd.DataFrame, normalized: pd.DataFrame) -> bool:
    return bool(normalized["trade_date"].isna().any() or _coerced_numeric_columns(original, normalized))


def _build_b2_signal_frame(history: pd.DataFrame, *, code: str) -> pd.DataFrame:
    frame = history.copy()
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["volume"].astype(float)

    kdj = compute_kdj(frame[["high", "low", "close"]].copy())
    frame["K"] = kdj["K"].astype(float)
    frame["D"] = kdj["D"].astype(float)
    frame["J"] = kdj["J"].astype(float)

    days_l = pd.Series(np.arange(1, len(frame) + 1), index=frame.index, dtype=float)
    st_l = close.ewm(span=10, adjust=False).mean().ewm(span=10, adjust=False).mean()
    ma14 = close.rolling(window=14, min_periods=14).mean()
    ma28 = close.rolling(window=28, min_periods=28).mean()
    ma57 = close.rolling(window=57, min_periods=57).mean()
    ma114 = close.rolling(window=114, min_periods=114).mean()
    lt_r = (ma14 + ma28 + ma57 + ma114) / 4.0
    lt_r = lt_r.where(days_l > 114)

    cross_up = (st_l > lt_r) & (st_l.shift(1) <= lt_r.shift(1))
    c_days = _barslast(cross_up.fillna(False))
    honeymoon = (c_days >= 0) & (c_days <= 30) & (st_l > lt_r)
    breakaway = st_l > (lt_r * 1.03)

    lt_dir = pd.Series(1.0, index=frame.index)
    mature = days_l > 114
    lt_dir.loc[mature] = np.where(
        (lt_r.loc[mature].shift(1).notna()) & (lt_r.loc[mature] >= lt_r.loc[mature].shift(1) * 0.9999),
        1.0,
        -1.0,
    )
    flip_c = (lt_dir != lt_dir.shift(1)).fillna(False).rolling(window=30, min_periods=1).sum()
    lt_stable = flip_c <= 2
    support = close >= (lt_r * 0.95)
    is_new = days_l <= 114
    tr_ok = is_new | honeymoon | breakaway | ((st_l > lt_r) & (close > lt_r) & lt_stable & support)
    above_lt = pd.Series(np.where(is_new, True, close > lt_r), index=frame.index)

    pct = close.pct_change() * 100.0
    amp_limit = 12.0 if code.startswith(("688", "300")) else 8.0
    amp = ((high - low) / close.shift(1)) * 100.0
    shake = pct.abs() < 5.05
    shake &= amp < amp_limit

    j_up = frame["J"] > frame["J"].shift(1)
    j_turn_up = j_up & (frame["J"].shift(1) <= frame["J"].shift(2))
    up_days = _barslast(j_turn_up.fillna(False))

    pre_ok = (pct.shift(1) < 3.7) & (frame["J"].shift(1) < 39.0)
    up_shadow = high - close
    ef_body = close - pd.concat([open_, close.shift(1)], axis=1).min(axis=1)
    k_shape = (up_shadow <= ef_body) & (close > open_)

    pct_ok = pct >= 3.7
    volume_ok = volume > volume.shift(1)
    raw_b2 = pct_ok & volume_ok & k_shape & pre_ok & j_up & tr_ok & above_lt
    raw_b2_unique = _count_dynamic(raw_b2.fillna(False), up_days + 1) == 1
    cur_b2 = raw_b2 & raw_b2_unique

    distance_b2 = _barslast(cur_b2.fillna(False))
    b2_last_c = _ref_with_dynamic(close, distance_b2)
    b2_last_h = _ref_with_dynamic(high, distance_b2)
    b2_last_l = _ref_with_dynamic(low, distance_b2)
    b2_last_o = _ref_with_dynamic(open_, distance_b2)
    b2_ref1_c = _ref_with_dynamic(close.shift(1), distance_b2)
    b2_upper = (b2_last_h - pd.concat([b2_last_c, b2_last_o], axis=1).max(axis=1)) / (
        (b2_last_h - b2_last_l).clip(lower=0.001)
    )

    ref_cur_b2 = cur_b2.shift(1).fillna(False)
    cur_b3 = ref_cur_b2 & shake & (volume <= volume.shift(1) * 0.9) & j_up & tr_ok & above_lt
    cur_b3_plus = cur_b3 & (volume <= volume.shift(1) * 0.52) & (close > b2_ref1_c) & (b2_upper < (1.0 / 3.0))
    cur_b4 = ref_cur_b2 & shake & (volume > volume.shift(1) * 0.9) & (volume <= volume.shift(1) * 1.3) & j_up & tr_ok & above_lt
    cur_b5 = (cur_b3.shift(1).fillna(False) | cur_b4.shift(1).fillna(False)) & shake & (volume <= volume.shift(1) * 0.9) & j_up & tr_ok & above_lt

    return frame.assign(
        pct=pct,
        pct_ok=pct_ok.fillna(False),
        volume_ok=volume_ok.fillna(False),
        pre_ok=pre_ok.fillna(False),
        k_shape=k_shape.fillna(False),
        j_up=j_up.fillna(False),
        tr_ok=tr_ok.fillna(False),
        above_lt=above_lt.fillna(False),
        raw_b2=raw_b2.fillna(False),
        raw_b2_unique=raw_b2_unique.fillna(False),
        cur_b2=cur_b2.fillna(False),
        cur_b3=cur_b3.fillna(False),
        cur_b3_plus=cur_b3_plus.fillna(False),
        cur_b4=cur_b4.fillna(False),
        cur_b5=cur_b5.fillna(False),
    )


def _resolve_signal(row: pd.Series) -> str | None:
    if bool(row["cur_b2"]):
        return "B2"
    if bool(row["cur_b3_plus"]):
        return "B3+"
    if bool(row["cur_b3"]):
        return "B3"
    return None


def _barslast(condition: pd.Series) -> pd.Series:
    values = condition.astype(bool).tolist()
    out: list[float] = []
    last_true: int | None = None
    for idx, value in enumerate(values):
        if value:
            last_true = idx
            out.append(0.0)
        elif last_true is None:
            out.append(float(idx + 1))
        else:
            out.append(float(idx - last_true))
    return pd.Series(out, index=condition.index)


def _count_dynamic(condition: pd.Series, windows: pd.Series) -> pd.Series:
    values = condition.astype(bool).tolist()
    counts: list[int] = []
    for idx, value in enumerate(values):
        _ = value
        window = max(int(float(windows.iloc[idx])), 1)
        start = max(0, idx - window + 1)
        counts.append(int(sum(values[start : idx + 1])))
    return pd.Series(counts, index=condition.index, dtype=float)


def _ref_with_dynamic(series: pd.Series, distances: pd.Series) -> pd.Series:
    values = series.tolist()
    out: list[float] = []
    for idx, value in enumerate(values):
        _ = value
        distance = int(float(distances.iloc[idx]))
        ref_idx = idx - distance
        if 0 <= ref_idx < len(values):
            ref_value = values[ref_idx]
            out.append(float(ref_value) if pd.notna(ref_value) else np.nan)
        else:
            out.append(np.nan)
    return pd.Series(out, index=series.index, dtype=float)


__all__ = [
    "run_b2_screen",
    "run_b2_screen_with_stats",
]
