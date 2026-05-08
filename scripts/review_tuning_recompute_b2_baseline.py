from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.cli import _load_prepared_cache_v2
from stock_select.environment_profiles import get_method_environment_profile
from stock_select.market_environment import resolve_market_environment
from stock_select.research.review_tuning import collect_review_samples
from stock_select.reviewers.b2 import review_b2_symbol_history


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_PREPARED_ROOT = DEFAULT_RUNTIME_ROOT / "prepared"


def _load_prepared_for_pick_date(*, prepared_root: Path, pick_date: str) -> pd.DataFrame:
    candidates = sorted(path for path in prepared_root.glob("*.feather") if path.name <= f"{pick_date}.feather")
    if not candidates:
        raise FileNotFoundError(f"no prepared cache found on or before {pick_date}")
    data_path = candidates[-1]
    payload = _load_prepared_cache_v2(data_path, data_path.with_suffix(".meta.json"))
    prepared = payload.get("prepared_table")
    if not isinstance(prepared, pd.DataFrame):
        raise ValueError("prepared cache prepared_table missing")
    return prepared


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recompute b2 baseline reviews into a candidate tuning artifact")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--source-runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--prepared-root", type=Path, default=DEFAULT_PREPARED_ROOT)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def _resolve_profile_for_pick_date(*, runtime_root: Path, pick_date: str):
    environment = resolve_market_environment(runtime_root, pick_date=pick_date)
    return get_method_environment_profile(method="b2", state=str(environment["state"]))


def _rewrite_summary(*, source_path: Path, target_path: Path, prepared_root: Path, runtime_root: Path) -> None:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    pick_date = str(payload.get("pick_date") or source_path.parent.name.replace(".b2", ""))
    prepared = _load_prepared_for_pick_date(prepared_root=prepared_root, pick_date=pick_date)
    profile = _resolve_profile_for_pick_date(runtime_root=runtime_root, pick_date=pick_date)

    def rewrite_item(item: dict[str, object]) -> dict[str, object]:
        code = str(item["code"])
        chart_path = str(item.get("chart_path") or "")
        signal = None
        baseline_review = item.get("baseline_review")
        if isinstance(baseline_review, dict):
            signal = baseline_review.get("signal")
        history = prepared.loc[prepared["ts_code"] == code].copy()
        new_baseline = review_b2_symbol_history(
            code=code,
            pick_date=pick_date,
            history=history,
            chart_path=chart_path,
            signal=None if signal is None else str(signal),
            profile=profile,
        )
        return {
            **item,
            "baseline_review": new_baseline,
            "total_score": new_baseline["total_score"],
            "signal_type": new_baseline["signal_type"],
            "verdict": new_baseline["verdict"],
            "comment": new_baseline["comment"],
            "watch_score": new_baseline["watch_score"],
            "watch_tier": new_baseline["watch_tier"],
            "watch_reason": new_baseline["elastic_watch_reason"],
        }

    payload["recommendations"] = [rewrite_item(item) for item in payload.get("recommendations", [])]
    payload["excluded"] = [rewrite_item(item) for item in payload.get("excluded", [])]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    artifact_runtime_root = args.artifact_dir
    profile_runtime_root = artifact_runtime_root / "env-runtime"
    review_target_root = artifact_runtime_root / "reviews"
    if review_target_root.exists():
        shutil.rmtree(review_target_root)
    review_target_root.mkdir(parents=True, exist_ok=True)

    source_reviews_root = args.source_runtime_root / "reviews"
    for review_dir in sorted(source_reviews_root.glob("????-??-??.b2")):
        pick_date = review_dir.name.replace(".b2", "")
        if pick_date < args.start_date or pick_date > args.end_date:
            continue
        source_summary = review_dir / "summary.json"
        if not source_summary.exists():
            continue
        target_summary = review_target_root / review_dir.name / "summary.json"
        _rewrite_summary(
            source_path=source_summary,
            target_path=target_summary,
            prepared_root=args.prepared_root,
            runtime_root=profile_runtime_root,
        )

    rows = collect_review_samples(
        methods=["b2"],
        start_date=args.start_date,
        end_date=args.end_date,
        runtime_root=artifact_runtime_root,
        prepared_root=args.prepared_root,
    )
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.artifact_dir / "samples.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
