from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.cli import _load_prepared_cache_v2


REVIEWS_DIR = Path("/home/pi/.agents/skills/stock-select/runtime/reviews")
PREPARED_DIR = Path("/home/pi/.agents/skills/stock-select/runtime/prepared")
SHARED_PREPARED_METHODS = {"b1", "b2", "dribull"}
SCORE_FIELDS = [
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "macd_phase",
]
DEFAULT_TOTAL_BIN_EDGES = [3.5, 4.0, 4.3, 4.6]


def parse_total_bin_edges(raw: str) -> list[float]:
    values = []
    for token in raw.split(","):
        item = token.strip()
        if not item:
            continue
        values.append(float(item))
    if not values:
        raise ValueError("total bin edges cannot be empty")
    ordered = sorted(set(values))
    if len(ordered) != len(values):
        raise ValueError("total bin edges must not contain duplicates")
    return ordered


def load_prepared(method: str, end_date: str) -> pd.DataFrame:
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
    for path in sorted(PREPARED_DIR.glob(feather_pattern)):
        if any(path.name.endswith(suffix) for suffix in ignored_feather_suffixes):
            continue
        date_part = path.name.removesuffix(feather_suffix)
        if date_part <= end_date:
            candidates.append((date_part, path))

    if not candidates:
        raise FileNotFoundError(
            f"No prepared cache found for method={method} on or before {end_date} in {PREPARED_DIR}"
        )

    data_path = sorted(candidates, key=lambda item: item[0])[-1][1]
    payload = _load_prepared_cache_v2(data_path, data_path.with_suffix(".meta.json"))
    prepared = payload.get("prepared_table")
    if not isinstance(prepared, pd.DataFrame):
        raise ValueError("Prepared cache prepared_table missing.")
    return prepared


def get_forward_data(
    prepared: pd.DataFrame,
    code: str,
    pick_date: str,
) -> dict | None:
    if prepared.empty or "ts_code" not in prepared.columns:
        return None
    df = prepared.loc[prepared["ts_code"] == code].copy()
    if df.empty:
        return None
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce", format="mixed")
    df = df.sort_values("trade_date").reset_index(drop=True)
    for col in ["close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    cutoff = pd.Timestamp(pick_date)
    cur = df[df["trade_date"] <= cutoff].tail(1)
    if cur.empty or pd.isna(cur.iloc[0]["close"]):
        return None

    entry_close = float(cur.iloc[0]["close"])
    future = df[df["trade_date"] > cutoff]

    result = {"entry_close": round(entry_close, 2), "ret3_pct": None, "ret5_pct": None}
    if len(future) >= 3:
        exit3 = float(future.iloc[2]["close"])
        result["ret3_pct"] = round((exit3 / entry_close - 1.0) * 100, 2)
        result["exit3_date"] = str(future.iloc[2]["trade_date"]).split()[0]
    if len(future) >= 5:
        exit5 = float(future.iloc[4]["close"])
        result["ret5_pct"] = round((exit5 / entry_close - 1.0) * 100, 2)
        result["exit5_date"] = str(future.iloc[4]["trade_date"]).split()[0]
    return result


def get_score(item: dict, field: str) -> float | None:
    if field in item and item[field] is not None:
        return float(item[field])
    baseline = item.get("baseline_review") or {}
    value = baseline.get(field)
    return None if value is None else float(value)


def get_signal(item: dict) -> str | None:
    if item.get("signal"):
        return str(item["signal"])
    baseline = item.get("baseline_review") or {}
    value = baseline.get("signal")
    return None if value is None else str(value)


def collect_records(
    *,
    method: str,
    start_date: str,
    end_date: str,
) -> tuple[list[dict], list[dict], list[str]]:
    prepared = load_prepared(method, end_date)
    records: list[dict] = []
    missing: list[dict] = []
    review_dates: list[str] = []

    for review_dir in sorted(REVIEWS_DIR.glob(f"????-??-??.{method}")):
        review_date = review_dir.name.replace(f".{method}", "")
        if review_date < start_date or review_date > end_date:
            continue

        summary_path = review_dir / "summary.json"
        if not summary_path.exists():
            continue

        review_dates.append(review_date)
        summary = json.loads(summary_path.read_text())
        pick_date = str(summary["pick_date"])
        items = (summary.get("recommendations") or []) + (summary.get("excluded") or [])

        for item in items:
            code = str(item.get("code") or "").strip()
            if not code:
                continue

            total_score = get_score(item, "total_score")
            if total_score is None:
                continue

            forward = get_forward_data(prepared, code, pick_date)
            if forward is None:
                missing.append({"pick_date": pick_date, "code": code, "reason": "no_forward_frame"})
                continue

            row = {
                "pick_date": pick_date,
                "review_date": review_date,
                "code": code,
                "name": item.get("name"),
                "signal": get_signal(item),
                "signal_type": item.get("signal_type") or (item.get("baseline_review") or {}).get("signal_type"),
                "verdict": str(item.get("verdict") or (item.get("baseline_review") or {}).get("verdict") or "").upper(),
                "total_score": total_score,
                **forward,
            }
            for field in SCORE_FIELDS:
                row[field] = get_score(item, field)
            records.append(row)

    return records, missing, review_dates


def finite_pairs(xs: list[float | None], ys: list[float | None]) -> list[tuple[float, float]]:
    pairs = []
    for x, y in zip(xs, ys):
        if x is None or y is None:
            continue
        xf = float(x)
        yf = float(y)
        if math.isfinite(xf) and math.isfinite(yf):
            pairs.append((xf, yf))
    return pairs


def pearson(xs: list[float | None], ys: list[float | None]) -> float | None:
    pairs = finite_pairs(xs, ys)
    if len(pairs) < 3:
        return None
    x_mean = sum(x for x, _ in pairs) / len(pairs)
    y_mean = sum(y for _, y in pairs) / len(pairs)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_scale = math.sqrt(sum((x - x_mean) ** 2 for x, _ in pairs))
    y_scale = math.sqrt(sum((y - y_mean) ** 2 for _, y in pairs))
    if x_scale == 0 or y_scale == 0:
        return None
    return numerator / (x_scale * y_scale)


def rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: list[float | None], ys: list[float | None]) -> float | None:
    pairs = finite_pairs(xs, ys)
    if len(pairs) < 3:
        return None
    x_ranks = rankdata([x for x, _ in pairs])
    y_ranks = rankdata([y for _, y in pairs])
    return pearson(x_ranks, y_ranks)


def return_stats(items: list[dict], key: str) -> dict:
    values = [float(item[key]) for item in items if item.get(key) is not None]
    if not values:
        return {"n": 0}
    wins = sum(value > 0 for value in values)
    return {
        "n": len(values),
        "avg": round(sum(values) / len(values), 3),
        "median": round(statistics.median(values), 3),
        "win_rate": round(wins / len(values) * 100, 1),
        "max": round(max(values), 3),
        "min": round(min(values), 3),
    }


def total_bucket(value: float, edges: list[float]) -> str:
    if value < edges[0]:
        return f"<{edges[0]:.1f}"
    for left, right in zip(edges, edges[1:]):
        if left <= value < right:
            return f"{left:.1f}-{right:.1f}"
    return f">={edges[-1]:.1f}"


def score_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    rounded = int(round(float(value)))
    bounded = max(1, min(5, rounded))
    return str(bounded)


def summarize_groups(items: list[dict], key: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        group_key = item.get(key)
        if group_key is None:
            continue
        grouped.setdefault(str(group_key), []).append(item)

    summary: dict[str, dict] = {}
    for group_key in sorted(grouped):
        group_items = grouped[group_key]
        summary[group_key] = {
            "count": len(group_items),
            "ret3": return_stats(group_items, "ret3_pct"),
            "ret5": return_stats(group_items, "ret5_pct"),
        }
    return summary


def build_diagnostics(
    *,
    method: str,
    start_date: str,
    end_date: str,
    total_bin_edges: list[float],
) -> dict:
    records, missing, review_dates = collect_records(method=method, start_date=start_date, end_date=end_date)
    if not records:
        raise ValueError(f"No review records found for method={method} date=[{start_date}, {end_date}]")

    correlations = []
    for field in ["total_score"] + SCORE_FIELDS:
        xs = [record.get(field) for record in records]
        for ret_key in ["ret3_pct", "ret5_pct"]:
            ys = [record.get(ret_key) for record in records]
            correlations.append(
                {
                    "field": field,
                    "return_key": ret_key,
                    "n": len(finite_pairs(xs, ys)),
                    "pearson": None if pearson(xs, ys) is None else round(pearson(xs, ys), 4),
                    "spearman": None if spearman(xs, ys) is None else round(spearman(xs, ys), 4),
                }
            )

    enriched_records = []
    for record in records:
        enriched = dict(record)
        enriched["total_bucket"] = total_bucket(float(record["total_score"]), total_bin_edges)
        for field in SCORE_FIELDS:
            enriched[f"{field}_bucket"] = score_bucket(record.get(field))
        enriched_records.append(enriched)

    by_verdict = summarize_groups(enriched_records, "verdict")
    by_total_bucket = summarize_groups(enriched_records, "total_bucket")
    by_field_bucket = {
        field: summarize_groups(enriched_records, f"{field}_bucket")
        for field in SCORE_FIELDS
    }

    ret3_valid = [record for record in enriched_records if record.get("ret3_pct") is not None]
    best_ret3 = sorted(ret3_valid, key=lambda item: float(item["ret3_pct"]), reverse=True)[:20]
    worst_ret3 = sorted(ret3_valid, key=lambda item: float(item["ret3_pct"]))[:20]

    return {
        "summary": {
            "method": method,
            "start_date": start_date,
            "end_date": end_date,
            "review_dates": review_dates,
            "review_date_count": len(review_dates),
            "record_count": len(enriched_records),
            "missing_count": len(missing),
            "verdict_counts": dict(Counter(record["verdict"] for record in enriched_records)),
        },
        "correlations": correlations,
        "layers": {
            "by_verdict": by_verdict,
            "by_total_bucket": by_total_bucket,
            "by_field_bucket": by_field_bucket,
        },
        "records": enriched_records,
        "best_ret3": best_ret3,
        "worst_ret3": worst_ret3,
        "missing_sample": missing[:50],
    }


def write_outputs(output_dir: Path, diagnostics: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2)
    )
    pd.DataFrame(diagnostics["records"]).to_csv(output_dir / "records.csv", index=False)


def print_console_summary(diagnostics: dict) -> None:
    summary = diagnostics["summary"]
    print(
        json.dumps(
            {
                "summary": summary,
                "correlations": diagnostics["correlations"],
                "by_verdict": diagnostics["layers"]["by_verdict"],
                "by_total_bucket": diagnostics["layers"]["by_total_bucket"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monthly score-vs-return diagnostics for stock-select review tuning"
    )
    parser.add_argument("--method", "-m", required=True, help="Method name: b1, b2, dribull, or hcr")
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD")
    parser.add_argument(
        "--total-bins",
        default="3.5,4.0,4.3,4.6",
        help="Comma-separated total score bucket edges. Default: 3.5,4.0,4.3,4.6",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/score_tuning_diagnostics"),
        help="Directory for diagnostics.json and records.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    diagnostics = build_diagnostics(
        method=args.method.strip().lower(),
        start_date=args.start_date,
        end_date=args.end_date,
        total_bin_edges=parse_total_bin_edges(args.total_bins),
    )
    write_outputs(args.output_dir, diagnostics)
    print_console_summary(diagnostics)
    print(f"OUT {args.output_dir}")


if __name__ == "__main__":
    main()
