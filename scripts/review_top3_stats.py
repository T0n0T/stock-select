from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.cli import _load_prepared_cache_v2
from stock_select.market_environment import load_environment_history
from stock_select.research.review_tuning import attach_environment_state


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
REVIEWS_DIR = DEFAULT_RUNTIME_ROOT / "reviews"
PREPARED_DIR = DEFAULT_RUNTIME_ROOT / "prepared"
SHARED_PREPARED_METHODS = {"b1", "b2", "dribull"}
DEFAULT_START_DATE = "2026-04-01"
DEFAULT_END_DATE = "2026-04-30"
TOP3_METRIC_FIELDS = (
    "avg_score",
    "avg_ret3_pct",
    "avg_ret5_pct",
    "win_rate_ret3_pct",
    "win_rate_ret5_pct",
    "record_count",
    "review_count",
)
TOP3_DELTA_FIELDS = {
    "avg_score": "delta_score",
    "avg_ret3_pct": "delta_ret3_pct",
    "avg_ret5_pct": "delta_ret5_pct",
    "win_rate_ret3_pct": "delta_win_rate_ret3_pct",
    "win_rate_ret5_pct": "delta_win_rate_ret5_pct",
    "record_count": "delta_record_count",
    "review_count": "delta_review_count",
}


def collect_pass_top_reviews(summary: dict, *, top_n: int = 3) -> list[dict]:
    candidates = summary.get("recommendations", []) + summary.get("excluded", [])
    passes = [item for item in candidates if str(item.get("verdict", "")).upper() == "PASS"]
    return sorted(
        passes,
        key=lambda item: float(item.get("total_score", 0)),
        reverse=True,
    )[:top_n]


def load_prepared(method: str, prepared_dir: Path | None = None) -> pd.DataFrame:
    prepared_root = prepared_dir or PREPARED_DIR
    normalized_method = method.strip().lower()
    if normalized_method in SHARED_PREPARED_METHODS:
        feather_pattern = "*-*-*.feather"
        ignored_feather_suffixes = {".hcr.feather"}
    else:
        feather_pattern = f"*-*-*.{normalized_method}.feather"
        ignored_feather_suffixes = set()

    candidates: list[Path] = []
    for path in sorted(prepared_root.glob(feather_pattern)):
        if any(path.name.endswith(suffix) for suffix in ignored_feather_suffixes):
            continue
        candidates.append(path)

    if not candidates:
        raise FileNotFoundError(
            f"No prepared cache matching {feather_pattern} in {prepared_root}"
        )

    data_path = sorted(candidates)[-1]
    payload = _load_prepared_cache_v2(data_path, data_path.with_suffix(".meta.json"))
    prepared = payload.get("prepared_table")
    if not isinstance(prepared, pd.DataFrame):
        raise ValueError("Prepared cache prepared_table missing.")
    return prepared


def get_forward_data(
    prepared: pd.DataFrame,
    code: str,
    pick_date: str,
) -> dict[str, object] | None:
    if prepared.empty or "ts_code" not in prepared.columns:
        return None
    df = prepared.loc[prepared["ts_code"] == code].copy()
    if df.empty:
        return None
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce", format="mixed")
    df = df.sort_values("trade_date").reset_index(drop=True)
    for col in ["open", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    cutoff = pd.Timestamp(pick_date)
    cur = df[df["trade_date"] <= cutoff].tail(1)
    if cur.empty:
        return None

    entry_close = float(cur.iloc[0]["close"])
    future = df[df["trade_date"] > cutoff]

    result: dict[str, object] = {"entry_close": entry_close}
    if not future.empty:
        nxt = future.iloc[0]
        gap_pct = (float(nxt["open"]) / entry_close - 1.0) * 100
        result["next_date"] = str(nxt["trade_date"]).split()[0]
        result["next_open"] = round(float(nxt["open"]), 2)
        result["open_gap_pct"] = round(gap_pct, 2)
        if gap_pct > 0.05:
            result["open_class"] = "high"
        elif gap_pct < -0.05:
            result["open_class"] = "low"
        else:
            result["open_class"] = "flat"
    else:
        result["open_gap_pct"] = None
        result["open_class"] = "missing"

    if len(future) >= 3:
        exit3 = float(future.iloc[2]["close"])
        result["ret3_pct"] = round((exit3 / entry_close - 1.0) * 100, 2)
        result["exit3_date"] = str(future.iloc[2]["trade_date"]).split()[0]
    else:
        result["ret3_pct"] = None

    if len(future) >= 5:
        exit5 = float(future.iloc[4]["close"])
        result["ret5_pct"] = round((exit5 / entry_close - 1.0) * 100, 2)
        result["exit5_date"] = str(future.iloc[4]["trade_date"]).split()[0]
    else:
        result["ret5_pct"] = None

    return result


def _normalize_method(method: str) -> str:
    return method.strip().lower()


def _normalize_environment_state(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_score(row: dict[str, object]) -> float | None:
    return _coerce_float(row.get("total_score", row.get("score")))


def _load_artifact_rows(artifact_dir: Path) -> list[dict[str, object]]:
    for name in ("samples_with_env.csv", "samples.csv"):
        path = artifact_dir / name
        if path.exists():
            frame = pd.read_csv(path)
            if frame.empty:
                return []
            return frame.to_dict("records")
    raise FileNotFoundError(
        f"Expected samples_with_env.csv or samples.csv under artifact dir: {artifact_dir}"
    )


def _select_top3_records_from_rows(
    rows: list[dict[str, object]],
    *,
    methods: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    environment_state: str | None,
) -> list[dict[str, object]]:
    method_filter = {_normalize_method(method) for method in methods or []}
    environment_filter = _normalize_environment_state(environment_state)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)

    for row in rows:
        method = _normalize_method(str(row.get("method", "")))
        if method_filter and method not in method_filter:
            continue
        pick_date = str(row.get("pick_date", "")).strip()
        if start_date is not None and pick_date < start_date:
            continue
        if end_date is not None and pick_date > end_date:
            continue
        if str(row.get("verdict", "")).upper() != "PASS":
            continue

        normalized_environment = _normalize_environment_state(row.get("environment_state"))
        if environment_filter is not None and normalized_environment != environment_filter:
            continue

        enriched = {
            **row,
            "method": method,
            "pick_date": pick_date,
            "environment_state": normalized_environment,
            "total_score": _record_score(row),
            "ret3_pct": _coerce_float(row.get("ret3_pct")),
            "ret5_pct": _coerce_float(row.get("ret5_pct")),
        }
        grouped[(method, pick_date)].append(enriched)

    records: list[dict[str, object]] = []
    for (_, _), items in sorted(grouped.items(), key=lambda item: item[0]):
        top3 = sorted(
            items,
            key=lambda item: float(item.get("total_score") or 0.0),
            reverse=True,
        )[:3]
        for rank, item in enumerate(top3, 1):
            records.append({**item, "rank": rank, "score": item.get("total_score")})
    return records


def _collect_runtime_top3_records(
    *,
    methods: list[str],
    start_date: str,
    end_date: str,
    environment_state: str | None,
    runtime_root: Path | None,
    prepared_root: Path | None,
) -> list[dict[str, object]]:
    reviews_root = REVIEWS_DIR if runtime_root is None else runtime_root / "reviews"
    history_root = REVIEWS_DIR.parent if runtime_root is None else runtime_root
    prepared_dir = PREPARED_DIR if prepared_root is None else prepared_root
    records: list[dict[str, object]] = []

    for method in methods:
        normalized_method = _normalize_method(method)
        prepared = load_prepared(normalized_method, prepared_dir)
        for review_dir in sorted(reviews_root.glob(f"????-??-??.{normalized_method}")):
            pick_date = review_dir.name.replace(f".{normalized_method}", "")
            if pick_date < start_date or pick_date > end_date:
                continue

            summary_path = review_dir / "summary.json"
            if not summary_path.exists():
                continue

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary_pick_date = str(summary.get("pick_date", pick_date))
            top3 = collect_pass_top_reviews(summary, top_n=3)
            for rank, item in enumerate(top3, 1):
                code = str(item["code"])
                fwd = get_forward_data(prepared, code, summary_pick_date)
                if fwd is None:
                    continue
                records.append(
                    {
                        "method": normalized_method,
                        "pick_date": summary_pick_date,
                        "code": code,
                        "rank": rank,
                        "score": float(item.get("total_score", 0.0)),
                        "total_score": float(item.get("total_score", 0.0)),
                        "open_gap_pct": fwd.get("open_gap_pct"),
                        "open_class": fwd.get("open_class", "missing"),
                        "ret3_pct": fwd.get("ret3_pct"),
                        "ret5_pct": fwd.get("ret5_pct"),
                    }
                )

    if records:
        history = load_environment_history(history_root)
        records = attach_environment_state(records, history, environment_key="score_based_state")

    environment_filter = _normalize_environment_state(environment_state)
    if environment_filter is None:
        return records
    return [
        record
        for record in records
        if _normalize_environment_state(record.get("environment_state")) == environment_filter
    ]


def collect_review_top3_records(
    *,
    methods: list[str],
    start_date: str | None,
    end_date: str | None,
    environment_state: str | None = None,
    artifact_dir: Path | None = None,
    runtime_root: Path | None = None,
    prepared_root: Path | None = None,
) -> list[dict[str, object]]:
    normalized_methods = [_normalize_method(method) for method in methods]
    if artifact_dir is not None:
        rows = _load_artifact_rows(artifact_dir)
        return _select_top3_records_from_rows(
            rows,
            methods=normalized_methods,
            start_date=start_date,
            end_date=end_date,
            environment_state=environment_state,
        )
    if start_date is None or end_date is None:
        raise ValueError("start_date and end_date are required when collecting from runtime reviews")
    return _collect_runtime_top3_records(
        methods=normalized_methods,
        start_date=start_date,
        end_date=end_date,
        environment_state=environment_state,
        runtime_root=runtime_root,
        prepared_root=prepared_root,
    )


def summarize_top3_metrics(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str | None], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        method = _normalize_method(str(record.get("method", "")))
        environment_state = _normalize_environment_state(record.get("environment_state"))
        grouped[(method, environment_state)].append(record)

    rows: list[dict[str, object]] = []
    for (method, environment_state), items in sorted(grouped.items(), key=lambda item: item[0]):
        scores = [value for item in items if (value := _record_score(item)) is not None]
        ret3_values = [value for item in items if (value := _coerce_float(item.get("ret3_pct"))) is not None]
        ret5_values = [value for item in items if (value := _coerce_float(item.get("ret5_pct"))) is not None]
        review_count = len({(str(item.get("pick_date", "")), str(item.get("method", ""))) for item in items})

        rows.append(
            {
                "method": method,
                "environment_state": environment_state,
                "record_count": len(items),
                "review_count": review_count,
                "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
                "avg_ret3_pct": round(sum(ret3_values) / len(ret3_values), 2) if ret3_values else None,
                "avg_ret5_pct": round(sum(ret5_values) / len(ret5_values), 2) if ret5_values else None,
                "win_rate_ret3_pct": (
                    round(sum(1 for value in ret3_values if value > 0) / len(ret3_values) * 100, 1)
                    if ret3_values
                    else None
                ),
                "win_rate_ret5_pct": (
                    round(sum(1 for value in ret5_values if value > 0) / len(ret5_values) * 100, 1)
                    if ret5_values
                    else None
                ),
            }
        )
    return rows


def compare_top3_metrics(
    *,
    baseline: list[dict[str, object]],
    candidate: list[dict[str, object]],
) -> dict[str, object]:
    baseline_map = {
        (_normalize_method(str(row.get("method", ""))), _normalize_environment_state(row.get("environment_state"))): row
        for row in baseline
    }
    candidate_map = {
        (_normalize_method(str(row.get("method", ""))), _normalize_environment_state(row.get("environment_state"))): row
        for row in candidate
    }
    keys = sorted(set(baseline_map) | set(candidate_map))

    rows: list[dict[str, object]] = []
    for key in keys:
        baseline_row = baseline_map.get(key, {})
        candidate_row = candidate_map.get(key, {})
        row = {
            "method": key[0],
            "environment_state": key[1],
        }
        for field in TOP3_METRIC_FIELDS:
            baseline_value = baseline_row.get(field)
            candidate_value = candidate_row.get(field)
            row[f"baseline_{field}"] = baseline_value
            row[f"candidate_{field}"] = candidate_value
            baseline_number = _coerce_float(baseline_value)
            candidate_number = _coerce_float(candidate_value)
            if baseline_number is None or candidate_number is None:
                row[TOP3_DELTA_FIELDS[field]] = None
                continue
            if field in {"record_count", "review_count"}:
                row[TOP3_DELTA_FIELDS[field]] = int(candidate_number - baseline_number)
            else:
                row[TOP3_DELTA_FIELDS[field]] = round(candidate_number - baseline_number, 2)
        rows.append(row)

    return {"rows": rows}


def compare_artifact_dirs(
    *,
    baseline_artifact_dir: Path,
    candidate_artifact_dir: Path,
    methods: list[str],
    environment_state: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    baseline_records = collect_review_top3_records(
        methods=methods,
        start_date=start_date,
        end_date=end_date,
        environment_state=environment_state,
        artifact_dir=baseline_artifact_dir,
    )
    candidate_records = collect_review_top3_records(
        methods=methods,
        start_date=start_date,
        end_date=end_date,
        environment_state=environment_state,
        artifact_dir=candidate_artifact_dir,
    )
    baseline_metrics = summarize_top3_metrics(baseline_records)
    candidate_metrics = summarize_top3_metrics(candidate_records)
    return {
        "methods": [_normalize_method(method) for method in methods],
        "environment_state": _normalize_environment_state(environment_state),
        "baseline": {
            "path": str(baseline_artifact_dir),
            "exists": baseline_artifact_dir.is_dir(),
            "top3_record_count": len(baseline_records),
            "metrics": baseline_metrics,
        },
        "candidate": {
            "path": str(candidate_artifact_dir),
            "exists": candidate_artifact_dir.is_dir(),
            "top3_record_count": len(candidate_records),
            "metrics": candidate_metrics,
        },
        "comparison": compare_top3_metrics(
            baseline=baseline_metrics,
            candidate=candidate_metrics,
        ),
    }


def _gap_stats(items: list[dict[str, object]]) -> dict[str, object]:
    valid = [item for item in items if item.get("open_gap_pct") is not None]
    if not valid:
        return {}
    gaps = [float(item["open_gap_pct"]) for item in valid]
    classes = Counter(str(item.get("open_class", "missing")) for item in valid)
    return {
        "n": len(valid),
        "high": classes.get("high", 0),
        "low": classes.get("low", 0),
        "flat": classes.get("flat", 0),
        "high_pct": round(classes.get("high", 0) / len(valid) * 100, 1),
        "low_pct": round(classes.get("low", 0) / len(valid) * 100, 1),
        "avg_gap": round(sum(gaps) / len(gaps), 2),
        "median_gap": round(statistics.median(gaps), 2),
    }


def _ret_stats(items: list[dict[str, object]], key: str) -> dict[str, object]:
    valid = [item for item in items if item.get(key) is not None]
    if not valid:
        return {}
    rets = [float(item[key]) for item in valid]
    wins = sum(1 for value in rets if value > 0)
    return {
        "n": len(valid),
        "win": wins,
        "loss": len(valid) - wins,
        "win_pct": round(wins / len(valid) * 100, 1),
        "avg_ret": round(sum(rets) / len(rets), 2),
        "median_ret": round(statistics.median(rets), 2),
        "max_ret": round(max(rets), 2),
        "min_ret": round(min(rets), 2),
    }


def _print_records_summary(
    records: list[dict[str, object]],
    *,
    methods: list[str],
    start_date: str | None,
    end_date: str | None,
    environment_state: str | None,
) -> None:
    if not records:
        print("No PASS top3 records found for the requested filters.")
        return

    scores = [value for item in records if (value := _record_score(item)) is not None]
    label = ", ".join(methods)
    print(f"\n{'=' * 60}")
    print(f"  Methods: {label}")
    if start_date is not None and end_date is not None:
        print(f"  Date range: {start_date} ~ {end_date}")
    if environment_state is not None:
        print(f"  Environment: {_normalize_environment_state(environment_state)}")
    print(f"  Total top3 records: {len(records)}")
    if scores:
        print(f"  Score range: {min(scores):.2f} ~ {max(scores):.2f}  (avg {sum(scores) / len(scores):.2f})")
    print(f"{'=' * 60}")

    if any(item.get("open_gap_pct") is not None for item in records):
        print("\n--- Open Gap (top3) ---")
        gap_stats = _gap_stats(records)
        if gap_stats:
            print(
                f"  n={gap_stats['n']}  high={gap_stats['high']}({gap_stats['high_pct']}%)  "
                f"low={gap_stats['low']}({gap_stats['low_pct']}%)  flat={gap_stats['flat']}"
            )
            print(f"  avg_gap={gap_stats['avg_gap']}%  median_gap={gap_stats['median_gap']}%")

    print("\n--- 3-Day Return (top3) ---")
    ret3 = _ret_stats(records, "ret3_pct")
    if ret3:
        print(f"  n={ret3['n']}  win={ret3['win']}({ret3['win_pct']}%)  loss={ret3['loss']}")
        print(f"  avg={ret3['avg_ret']}%  median={ret3['median_ret']}%  max={ret3['max_ret']}%  min={ret3['min_ret']}%")

    print("\n--- 5-Day Return (top3) ---")
    ret5 = _ret_stats(records, "ret5_pct")
    if ret5:
        print(f"  n={ret5['n']}  win={ret5['win']}({ret5['win_pct']}%)  loss={ret5['loss']}")
        print(f"  avg={ret5['avg_ret']}%  median={ret5['median_ret']}%  max={ret5['max_ret']}%  min={ret5['min_ret']}%")


def _print_comparison_summary(payload: dict[str, object]) -> None:
    print("\n# Top3 Verification Comparison")
    print(f"- baseline: {payload['baseline']['path']}")
    print(f"- candidate: {payload['candidate']['path']}")
    if payload.get("methods"):
        print(f"- methods: {', '.join(payload['methods'])}")
    if payload.get("environment_state") is not None:
        print(f"- environment_state: {payload['environment_state']}")
    for row in payload["comparison"]["rows"]:
        print(
            f"- method={row['method']} environment={row.get('environment_state') or 'all'} "
            f"delta_ret3_pct={row.get('delta_ret3_pct')} delta_ret5_pct={row.get('delta_ret5_pct')}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review-oriented top3 PASS verification stats and artifact comparisons"
    )
    parser.add_argument("--method", "-m", help="Single method alias kept for backward compatibility")
    parser.add_argument("--methods", nargs="+", help="Method names to include")
    parser.add_argument("--start", "--start-date", dest="start_date", default=DEFAULT_START_DATE)
    parser.add_argument("--end", "--end-date", dest="end_date", default=DEFAULT_END_DATE)
    parser.add_argument("--environment-state")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--baseline-artifact-dir", type=Path)
    parser.add_argument("--candidate-artifact-dir", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--prepared-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    methods = args.methods or ([args.method] if args.method else ["hcr"])

    if args.baseline_artifact_dir is not None or args.candidate_artifact_dir is not None:
        if args.baseline_artifact_dir is None or args.candidate_artifact_dir is None:
            raise SystemExit("Both --baseline-artifact-dir and --candidate-artifact-dir are required.")
        payload = compare_artifact_dirs(
            baseline_artifact_dir=args.baseline_artifact_dir,
            candidate_artifact_dir=args.candidate_artifact_dir,
            methods=methods,
            environment_state=args.environment_state,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        _print_comparison_summary(payload)
        return 0

    records = collect_review_top3_records(
        methods=methods,
        start_date=args.start_date,
        end_date=args.end_date,
        environment_state=args.environment_state,
        artifact_dir=args.artifact_dir,
        runtime_root=args.runtime_root,
        prepared_root=args.prepared_root,
    )
    _print_records_summary(
        records,
        methods=methods,
        start_date=args.start_date,
        end_date=args.end_date,
        environment_state=args.environment_state,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
