from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd
import psycopg

from stock_select.cli import _load_prepared_cache_v2
from stock_select.environment_profiles import get_method_environment_profile
from stock_select.market_environment import resolve_market_environment
from stock_select.reviewers.b1 import review_b1_symbol_history


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recompute current b1 reviewer policy samples from runtime candidates.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--dsn", default=os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/stock_cache"))
    parser.add_argument("--resume", action="store_true", help="Reuse existing per-date CSV files under artifact-dir/daily.")
    return parser.parse_args(argv)


def _load_prepared(runtime_root: Path, pick_date: str) -> pd.DataFrame:
    path = runtime_root / "prepared" / f"{pick_date}.feather"
    meta_path = runtime_root / "prepared" / f"{pick_date}.meta.json"
    if not path.exists():
        raise FileNotFoundError(f"prepared cache not found: {path}")
    payload = _load_prepared_cache_v2(path, meta_path)
    prepared = payload.get("prepared_table")
    if not isinstance(prepared, pd.DataFrame):
        raise ValueError(f"prepared_table missing in {path}")
    prepared = prepared.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce", format="mixed")
    return prepared


def _load_candidates(runtime_root: Path, pick_date: str) -> list[dict[str, object]]:
    path = runtime_root / "candidates" / f"{pick_date}.b1.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates")
    return candidates if isinstance(candidates, list) else []


def _resolve_environment(runtime_root: Path, pick_date: str) -> str:
    payload = resolve_market_environment(runtime_root, pick_date=pick_date)
    return str(payload["state"])


def _load_price_history(dsn: str, *, codes: list[str], start_date: str) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    by_code: dict[str, list[tuple[pd.Timestamp, float]]] = defaultdict(list)
    if not codes:
        return by_code
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ts_code, trade_date, close
                FROM daily_market
                WHERE ts_code = ANY(%s)
                  AND trade_date >= (%s::date - interval '80 days')
                  AND close IS NOT NULL
                ORDER BY ts_code, trade_date
                """,
                (codes, start_date),
            )
            rows = cursor.fetchall()
    for code, trade_date, close in rows:
        by_code[str(code)].append((pd.Timestamp(trade_date), float(close)))
    return by_code


def _forward_returns(
    price_history: dict[str, list[tuple[pd.Timestamp, float]]], *, code: str, pick_date: str
) -> dict[str, float | None]:
    values = [(date, close) for date, close in price_history.get(code, []) if date >= pd.Timestamp(pick_date)]
    result: dict[str, float | None] = {"ret5_pct": None, "ret10_pct": None}
    if not values:
        return result
    base = values[0][1]
    if base <= 0.0:
        return result
    if len(values) > 5:
        result["ret5_pct"] = round((values[5][1] / base - 1.0) * 100.0, 2)
    if len(values) > 10:
        result["ret10_pct"] = round((values[10][1] / base - 1.0) * 100.0, 2)
    return result


def _metrics(frame: pd.DataFrame, *, group_fields: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    def summarize(group: pd.DataFrame) -> pd.Series:
        ret5 = pd.to_numeric(group["ret5_pct"], errors="coerce").dropna()
        ret10 = pd.to_numeric(group["ret10_pct"], errors="coerce").dropna()
        return pd.Series(
            {
                "count": len(group),
                "ret5_n": len(ret5),
                "ret5_win_rate": round(float((ret5 > 0).mean() * 100.0), 2) if len(ret5) else None,
                "ret5_mean": round(float(ret5.mean()), 2) if len(ret5) else None,
                "ret5_median": round(float(ret5.median()), 2) if len(ret5) else None,
                "ret10_n": len(ret10),
                "ret10_win_rate": round(float((ret10 > 0).mean() * 100.0), 2) if len(ret10) else None,
                "ret10_mean": round(float(ret10.mean()), 2) if len(ret10) else None,
                "ret10_median": round(float(ret10.median()), 2) if len(ret10) else None,
            }
        )

    return frame.groupby(group_fields, dropna=False).apply(summarize, include_groups=False).reset_index()


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)

    candidate_paths = sorted((args.runtime_root / "candidates").glob("????-??-??.b1.json"))
    pick_dates = [path.name[:10] for path in candidate_paths if args.start_date <= path.name[:10] <= args.end_date]

    all_codes: set[str] = set()
    candidates_by_date: dict[str, list[dict[str, object]]] = {}
    for pick_date in pick_dates:
        candidates = _load_candidates(args.runtime_root, pick_date)
        candidates_by_date[pick_date] = candidates
        for candidate in candidates:
            code = str(candidate["code"])
            all_codes.add(code)
    price_history = _load_price_history(args.dsn, codes=sorted(all_codes), start_date=args.start_date)

    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    environment_by_date: dict[str, str] = {}
    processed = 0
    total = sum(len(candidates) for candidates in candidates_by_date.values())
    daily_dir = args.artifact_dir / "daily"
    failure_dir = args.artifact_dir / "daily_failures"
    for pick_date in pick_dates:
        daily_path = daily_dir / f"{pick_date}.csv"
        daily_failure_path = failure_dir / f"{pick_date}.csv"
        if args.resume and daily_path.exists():
            processed += len(candidates_by_date[pick_date])
            print(f"resume skip date={pick_date} processed={processed}/{total}", flush=True)
            continue

        daily_rows: list[dict[str, object]] = []
        daily_failures: list[dict[str, object]] = []
        prepared = _load_prepared(args.runtime_root, pick_date)
        prepared_by_code = {
            str(code): group.sort_values("trade_date").reset_index(drop=True)
            for code, group in prepared.groupby("ts_code", sort=False)
        }
        environment_by_date[pick_date] = _resolve_environment(args.runtime_root, pick_date)
        environment_state = environment_by_date[pick_date]
        profile = get_method_environment_profile(method="b1", state=environment_state)
        for candidate in candidates_by_date[pick_date]:
            processed += 1
            code = str(candidate["code"])
            symbol_history = prepared_by_code.get(code)
            history = pd.DataFrame() if symbol_history is None else symbol_history[symbol_history["trade_date"] <= pd.Timestamp(pick_date)].copy()
            if history.empty:
                daily_failures.append({"pick_date": pick_date, "code": code, "reason": "missing_history"})
                continue
            try:
                review = review_b1_symbol_history(
                    code=code,
                    pick_date=pick_date,
                    history=history,
                    chart_path=f"/tmp/{code}_day.png",
                    profile=profile,
                )
            except Exception as exc:  # noqa: BLE001 - research artifact records failures and continues.
                daily_failures.append({"pick_date": pick_date, "code": code, "reason": str(exc)})
                continue
            returns = _forward_returns(price_history, code=code, pick_date=pick_date)
            daily_rows.append(
                {
                    "method": "b1",
                    "pick_date": pick_date,
                    "environment_state": environment_state,
                    "code": code,
                    "total_score": review["total_score"],
                    "verdict": review["verdict"],
                    "signal_type": review["signal_type"],
                    "score_combo_key": review.get("score_combo_key"),
                    "high_return_combo_match": review.get("high_return_combo_match"),
                    "pass_family": review.get("pass_family"),
                    "pass_family_tier": review.get("pass_family_tier"),
                    "score_layer": review.get("score_layer"),
                    "score_layer_score": review.get("score_layer_score"),
                    "trend_structure": review["trend_structure"],
                    "price_position": review["price_position"],
                    "volume_behavior": review["volume_behavior"],
                    "previous_abnormal_move": review["previous_abnormal_move"],
                    "macd_phase": review["macd_phase"],
                    "gate_flags": ",".join(review.get("gate_flags") or []),
                    "gate_runup_pct": review.get("gate_runup_pct"),
                    "gate_below_ma25": review.get("gate_below_ma25"),
                    "gate_cooldown_active": review.get("gate_cooldown_active"),
                    "gate_sideways_amplitude_pct": review.get("gate_sideways_amplitude_pct"),
                    "ret5_pct": returns["ret5_pct"],
                    "ret10_pct": returns["ret10_pct"],
                }
            )
            if processed % 500 == 0:
                print(
                    f"processed={processed}/{total} rows={len(rows) + len(daily_rows)} "
                    f"failures={len(failures) + len(daily_failures)}",
                    flush=True,
                )
        _write_csv(daily_path, daily_rows)
        _write_csv(daily_failure_path, daily_failures)
        rows.extend(daily_rows)
        failures.extend(daily_failures)
        print(f"date={pick_date} rows={len(daily_rows)} failures={len(daily_failures)}", flush=True)

    if args.resume:
        loaded_rows = [pd.read_csv(path) for path in sorted(daily_dir.glob("????-??-??.csv"))]
        loaded_failures = [pd.read_csv(path) for path in sorted(failure_dir.glob("????-??-??.csv")) if path.stat().st_size > 0]
        samples = pd.concat(loaded_rows, ignore_index=True) if loaded_rows else pd.DataFrame()
        failures_frame = pd.concat(loaded_failures, ignore_index=True) if loaded_failures else pd.DataFrame()
    else:
        samples = pd.DataFrame(rows)
        failures_frame = pd.DataFrame(failures)

    samples.to_csv(args.artifact_dir / "samples.csv", index=False)
    failures_frame.to_csv(args.artifact_dir / "failures.csv", index=False)

    pass_samples = samples[samples["verdict"] == "PASS"].copy() if not samples.empty else pd.DataFrame()
    _metrics(pass_samples, group_fields=["environment_state", "score_combo_key"]).to_csv(
        args.artifact_dir / "pass_distribution.csv", index=False
    )
    _metrics(samples, group_fields=["environment_state", "verdict"]).to_csv(
        args.artifact_dir / "verdict_distribution.csv", index=False
    )
    _metrics(samples, group_fields=["environment_state", "score_combo_key", "verdict"]).to_csv(
        args.artifact_dir / "combo_verdict_distribution.csv", index=False
    )
    _metrics(samples, group_fields=["environment_state", "score_layer", "verdict"]).to_csv(
        args.artifact_dir / "score_layer_distribution.csv", index=False
    )

    summary = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "runtime_root": str(args.runtime_root),
        "sample_count": len(samples),
        "failure_count": len(failures_frame),
        "pass_count": int((samples["verdict"] == "PASS").sum()) if not samples.empty else 0,
        "dates": len(pick_dates),
    }
    (args.artifact_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
