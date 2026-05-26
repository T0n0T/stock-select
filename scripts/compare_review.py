#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


SUMMARY_ITEM_FIELDS = [
    "total_score",
    "signal_type",
    "verdict",
    "watch_reason",
    "watch_score",
    "watch_tier",
    "score_combo_key",
    "high_return_combo_match",
    "pass_family",
    "pass_family_tier",
    "gate_flags",
    "gate_cooldown_active",
    "gate_below_ma25",
    "gate_runup_pct",
    "gate_sideways_amplitude_pct",
    "gate_weekly_macd_cooldown_active",
    "score_layer",
    "score_layer_score",
    "yellow_b1",
]

BASELINE_FIELDS = [
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "macd_phase",
    "raw_total_score",
    "total_score",
    "signal_type",
    "score_combo_key",
    "high_return_combo_match",
    "pass_family",
    "pass_family_tier",
    "verdict",
    "gate_flags",
    "gate_cooldown_active",
    "gate_below_ma25",
    "gate_runup_pct",
    "gate_sideways_amplitude_pct",
    "gate_drawdown_pct",
    "gate_weekly_slope_26w",
    "gate_weekly_macd_cooldown_active",
    "watch_reason",
    "watch_score",
    "watch_tier",
    "score_layer",
    "score_layer_score",
]

TASK_FIELDS = [
    "code",
    "rank",
    "baseline_score",
    "baseline_verdict",
    "weekly_wave_context",
    "daily_wave_context",
    "wave_combo_context",
    "environment_state",
    "environment_reason",
    "environment_llm_focus",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Python and Rust stock-select review artifacts.")
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--rust-root", required=True, type=Path)
    parser.add_argument("--pick-date", required=True)
    parser.add_argument("--method", required=True, choices=["b1", "b2", "dribull"])
    parser.add_argument("--max-failures", type=int, default=50)
    args = parser.parse_args()

    failures: list[str] = []
    py_review = review_dir(args.python_root, args.pick_date, args.method)
    rs_review = review_dir(args.rust_root, args.pick_date, args.method)

    failures.extend(compare_summary(py_review, rs_review, args.pick_date, args.method))
    failures.extend(compare_stock_files(py_review, rs_review, args.pick_date))
    failures.extend(compare_tasks(py_review, rs_review, args.pick_date, args.method))

    if failures:
        print("FAIL review comparison", file=sys.stderr)
        for failure in failures[: args.max_failures]:
            print(f"- {failure}", file=sys.stderr)
        if len(failures) > args.max_failures:
            print(f"- ... {len(failures) - args.max_failures} more failures", file=sys.stderr)
        return 1

    py_summary = load_json(py_review / "summary.json")
    reviewed = py_summary.get("reviewed_count")
    rec_count = len(py_summary.get("recommendations", []))
    print(
        f"PASS review comparison method={args.method} pick_date={args.pick_date} "
        f"reviewed={reviewed} recommendations={rec_count}"
    )
    return 0


def review_dir(root: Path, pick_date: str, method: str) -> Path:
    return root / "reviews" / f"{pick_date}.{method}"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"artifact not found: {path}") from None


def compare_summary(py_dir: Path, rs_dir: Path, pick_date: str, method: str) -> list[str]:
    py = load_json(py_dir / "summary.json")
    rs = load_json(rs_dir / "summary.json")
    failures: list[str] = []
    for key, expected in [("pick_date", pick_date), ("method", method)]:
        failures.extend(compare_value(f"summary.{key}", py.get(key), expected))
        failures.extend(compare_value(f"summary.{key}", rs.get(key), expected))
    for key in ["reviewed_count"]:
        failures.extend(compare_value(f"summary.{key}", py.get(key), rs.get(key)))

    for section in ["recommendations", "excluded", "failures"]:
        py_items = py.get(section, [])
        rs_items = rs.get(section, [])
        if not isinstance(py_items, list) or not isinstance(rs_items, list):
            failures.append(f"summary.{section} must be a list")
            continue
        py_codes = [item.get("code") for item in py_items if isinstance(item, dict)]
        rs_codes = [item.get("code") for item in rs_items if isinstance(item, dict)]
        if py_codes != rs_codes:
            failures.append(f"summary.{section} code order mismatch: python={py_codes[:30]} rust={rs_codes[:30]}")
            continue
        for code, py_item, rs_item in zip(py_codes, py_items, rs_items):
            failures.extend(compare_review_item(f"summary.{section}.{code}", py_item, rs_item))
    return failures


def compare_stock_files(py_dir: Path, rs_dir: Path, pick_date: str) -> list[str]:
    py_files = stock_json_files(py_dir)
    rs_files = stock_json_files(rs_dir)
    failures: list[str] = []
    if set(py_files) != set(rs_files):
        failures.append(
            "stock review file set mismatch: "
            f"only_python={sorted(set(py_files) - set(rs_files))[:30]} "
            f"only_rust={sorted(set(rs_files) - set(py_files))[:30]}"
        )
        return failures

    for code in sorted(py_files):
        py = load_json(py_files[code])
        rs = load_json(rs_files[code])
        failures.extend(compare_value(f"{code}.code", py.get("code"), code))
        failures.extend(compare_value(f"{code}.pick_date", py.get("pick_date"), pick_date))
        failures.extend(compare_review_item(code, py, rs))
    return failures


def stock_json_files(directory: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in directory.glob("*.json"):
        if path.name in {"summary.json", "llm_review_tasks.json"}:
            continue
        result[path.stem] = path
    return result


def compare_review_item(label: str, py: dict[str, Any], rs: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in SUMMARY_ITEM_FIELDS:
        failures.extend(compare_value(f"{label}.{key}", py.get(key), rs.get(key)))

    py_baseline = py.get("baseline_review")
    rs_baseline = rs.get("baseline_review")
    if not isinstance(py_baseline, dict) or not isinstance(rs_baseline, dict):
        failures.append(f"{label}.baseline_review missing or invalid")
        return failures
    for key in BASELINE_FIELDS:
        failures.extend(compare_value(f"{label}.baseline_review.{key}", py_baseline.get(key), rs_baseline.get(key)))
    return failures


def compare_tasks(py_dir: Path, rs_dir: Path, pick_date: str, method: str) -> list[str]:
    py = load_json(py_dir / "llm_review_tasks.json")
    rs = load_json(rs_dir / "llm_review_tasks.json")
    failures: list[str] = []
    for key, expected in [("pick_date", pick_date), ("method", method)]:
        failures.extend(compare_value(f"tasks.{key}", py.get(key), expected))
        failures.extend(compare_value(f"tasks.{key}", rs.get(key), expected))
    failures.extend(compare_value("tasks.max_concurrency", py.get("max_concurrency"), rs.get("max_concurrency")))

    py_tasks = py.get("tasks")
    rs_tasks = rs.get("tasks")
    if not isinstance(py_tasks, list) or not isinstance(rs_tasks, list):
        return failures + ["tasks must be lists"]
    py_codes = [task.get("code") for task in py_tasks if isinstance(task, dict)]
    rs_codes = [task.get("code") for task in rs_tasks if isinstance(task, dict)]
    if py_codes != rs_codes:
        failures.append(f"task code order mismatch: python={py_codes[:30]} rust={rs_codes[:30]}")
        return failures

    for code, py_task, rs_task in zip(py_codes, py_tasks, rs_tasks):
        for key in TASK_FIELDS:
            failures.extend(compare_value(f"task.{code}.{key}", py_task.get(key), rs_task.get(key)))
    return failures


def compare_value(label: str, py_value: Any, rs_value: Any) -> list[str]:
    if isinstance(py_value, float) or isinstance(rs_value, float):
        if py_value is None or rs_value is None:
            return [] if py_value is rs_value else [f"{label} mismatch: python={py_value!r} rust={rs_value!r}"]
        if math.isclose(float(py_value), float(rs_value), rel_tol=0.0, abs_tol=1e-9):
            return []
    elif py_value == rs_value:
        return []
    return [f"{label} mismatch: python={py_value!r} rust={rs_value!r}"]


if __name__ == "__main__":
    raise SystemExit(main())
