from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_select.cli import SHARED_PREPARED_METHODS, _load_prepared_cache_v2


SCORE_FIELDS = (
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "macd_phase",
)


def _load_prepared(method: str, prepared_root: Path, *, end_date: str) -> pd.DataFrame:
    normalized_method = method.strip().lower()
    if normalized_method in SHARED_PREPARED_METHODS:
        feather_pattern = "*.feather"
        ignored_feather_suffixes = {".hcr.feather"}
        feather_suffix = ".feather"
    else:
        feather_pattern = f"*.{normalized_method}.feather"
        ignored_feather_suffixes = set()
        feather_suffix = f".{normalized_method}.feather"

    candidates: list[tuple[str, Path]] = []
    for path in sorted(prepared_root.glob(feather_pattern)):
        if any(path.name.endswith(suffix) for suffix in ignored_feather_suffixes):
            continue
        date_part = path.name.removesuffix(feather_suffix)
        if date_part <= end_date:
            candidates.append((date_part, path))

    if not candidates:
        raise FileNotFoundError(
            f"No prepared cache found for method={method} on or before {end_date} in {prepared_root}"
        )

    data_path = sorted(candidates, key=lambda item: item[0])[-1][1]
    payload = _load_prepared_cache_v2(data_path, data_path.with_suffix(".meta.json"))
    prepared = payload.get("prepared_table")
    if not isinstance(prepared, pd.DataFrame):
        raise ValueError("Prepared cache prepared_table missing.")
    return prepared


def _get_forward_returns(prepared: pd.DataFrame, *, code: str, pick_date: str) -> dict[str, float | None] | None:
    if prepared.empty or "ts_code" not in prepared.columns:
        return None

    df = prepared.loc[prepared["ts_code"] == code].copy()
    if df.empty:
        return None

    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce", format="mixed")
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    current = df[df["trade_date"] <= pd.Timestamp(pick_date)].tail(1)
    if current.empty or pd.isna(current.iloc[0]["close"]):
        return None

    entry_close = float(current.iloc[0]["close"])
    future = df[df["trade_date"] > pd.Timestamp(pick_date)].reset_index(drop=True)

    result: dict[str, float | None] = {"ret3_pct": None, "ret5_pct": None}
    if len(future) >= 3 and pd.notna(future.iloc[2]["close"]):
        result["ret3_pct"] = round((float(future.iloc[2]["close"]) / entry_close - 1.0) * 100, 2)
    if len(future) >= 5 and pd.notna(future.iloc[4]["close"]):
        result["ret5_pct"] = round((float(future.iloc[4]["close"]) / entry_close - 1.0) * 100, 2)
    return result


def _get_score(item: dict[str, object], field: str) -> float | None:
    if field in item and item[field] is not None:
        return float(item[field])
    baseline = item.get("baseline_review") or {}
    value = baseline.get(field)
    return None if value is None else float(value)


def _get_verdict(item: dict[str, object]) -> str:
    top_level = item.get("verdict")
    if top_level:
        return str(top_level).upper()
    baseline = item.get("baseline_review") or {}
    return str(baseline.get("verdict") or "").upper()


def collect_review_samples(
    *,
    methods: list[str],
    start_date: str,
    end_date: str,
    runtime_root: Path,
    prepared_root: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for method in methods:
        normalized_method = method.strip().lower()
        prepared = _load_prepared(normalized_method, prepared_root, end_date=end_date)
        reviews_root = runtime_root / "reviews"
        for review_dir in sorted(reviews_root.glob(f"????-??-??.{normalized_method}")):
            pick_date = review_dir.name.replace(f".{normalized_method}", "")
            if pick_date < start_date or pick_date > end_date:
                continue

            summary_path = review_dir / "summary.json"
            if not summary_path.exists():
                continue

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            items = summary.get("recommendations", []) + summary.get("excluded", [])
            summary_pick_date = str(summary.get("pick_date", pick_date))
            for item in items:
                code = str(item["code"])
                fwd = _get_forward_returns(prepared, code=code, pick_date=summary_pick_date)
                row = {
                    "method": normalized_method,
                    "pick_date": summary_pick_date,
                    "code": code,
                    "total_score": float(item["total_score"]),
                    "verdict": _get_verdict(item),
                    "ret3_pct": None if fwd is None else fwd.get("ret3_pct"),
                    "ret5_pct": None if fwd is None else fwd.get("ret5_pct"),
                }
                for field in SCORE_FIELDS:
                    row[field] = _get_score(item, field)
                rows.append(
                    row
                )

    return rows
