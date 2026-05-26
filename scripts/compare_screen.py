#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Python and Rust stock-select screen artifacts.")
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--rust-root", required=True, type=Path)
    parser.add_argument("--pick-date", required=True)
    parser.add_argument("--method", required=True, choices=["b1", "b2", "dribull"])
    parser.add_argument("--check-review-summary", action="store_true")
    args = parser.parse_args()

    py_payload = load_candidate_payload(args.python_root, args.pick_date, args.method)
    rs_payload = load_candidate_payload(args.rust_root, args.pick_date, args.method)

    failures: list[str] = []
    failures.extend(compare_top_level(py_payload, rs_payload, method=args.method, pick_date=args.pick_date))
    failures.extend(compare_candidates(py_payload, rs_payload, method=args.method))
    if args.check_review_summary:
        failures.extend(compare_review_summary(args.python_root, args.rust_root, args.pick_date, args.method))

    if failures:
        print("FAIL screen comparison", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    py_count = len(py_payload.get("candidates", []))
    rs_count = len(rs_payload.get("candidates", []))
    print(
        f"PASS screen comparison method={args.method} pick_date={args.pick_date} "
        f"candidates={py_count}/{rs_count}"
    )
    return 0


def load_candidate_payload(root: Path, pick_date: str, method: str) -> dict[str, Any]:
    path = root / "candidates" / f"{pick_date}.{method}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"candidate artifact not found: {path}") from None
    if not isinstance(payload, dict):
        raise SystemExit(f"candidate artifact is not a JSON object: {path}")
    return payload


def compare_top_level(
    py_payload: dict[str, Any],
    rs_payload: dict[str, Any],
    *,
    method: str,
    pick_date: str,
) -> list[str]:
    failures: list[str] = []
    for key, expected in [("method", method), ("pick_date", pick_date), ("pool_source", "turnover-top")]:
        if py_payload.get(key) != expected:
            failures.append(f"python top-level {key}: expected {expected!r}, got {py_payload.get(key)!r}")
        if rs_payload.get(key) != expected:
            failures.append(f"rust top-level {key}: expected {expected!r}, got {rs_payload.get(key)!r}")
    if method == "b1":
        if py_payload.get("screen_version") != 2:
            failures.append(f"python screen_version expected 2, got {py_payload.get('screen_version')!r}")
        if rs_payload.get("screen_version") != 2:
            failures.append(f"rust screen_version expected 2, got {rs_payload.get('screen_version')!r}")
    return failures


def compare_candidates(py_payload: dict[str, Any], rs_payload: dict[str, Any], *, method: str) -> list[str]:
    py_candidates = candidate_map(py_payload)
    rs_candidates = candidate_map(rs_payload)
    py_codes = set(py_candidates)
    rs_codes = set(rs_candidates)
    failures: list[str] = []
    if py_codes != rs_codes:
        only_py = sorted(py_codes - rs_codes)
        only_rs = sorted(rs_codes - py_codes)
        failures.append(
            f"candidate code set mismatch: python={len(py_codes)} rust={len(rs_codes)} "
            f"only_python={only_py[:30]} only_rust={only_rs[:30]}"
        )
        return failures

    for code in sorted(py_codes):
        py_item = py_candidates[code]
        rs_item = rs_candidates[code]
        failures.extend(compare_float_field(code, py_item, rs_item, "close", abs_tol=1e-9, rel_tol=0.0))
        failures.extend(compare_float_field(code, py_item, rs_item, "turnover_n", abs_tol=1e-4, rel_tol=1e-12))
        if method == "b1" and py_item.get("yellow_b1") != rs_item.get("yellow_b1"):
            failures.append(
                f"{code} yellow_b1 mismatch: python={py_item.get('yellow_b1')!r} "
                f"rust={rs_item.get('yellow_b1')!r}"
            )
        if method == "b2" and py_item.get("signal") != rs_item.get("signal"):
            failures.append(
                f"{code} signal mismatch: python={py_item.get('signal')!r} rust={rs_item.get('signal')!r}"
            )
    return failures


def candidate_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise SystemExit("candidate payload missing list field: candidates")
    result: dict[str, dict[str, Any]] = {}
    for item in raw_candidates:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str):
            raise SystemExit(f"invalid candidate item: {item!r}")
        result[item["code"]] = item
    return result


def compare_float_field(
    code: str,
    py_item: dict[str, Any],
    rs_item: dict[str, Any],
    field: str,
    *,
    abs_tol: float,
    rel_tol: float,
) -> list[str]:
    py_value = float(py_item[field])
    rs_value = float(rs_item[field])
    if math.isclose(py_value, rs_value, rel_tol=rel_tol, abs_tol=abs_tol):
        return []
    return [f"{code} {field} mismatch: python={py_value!r} rust={rs_value!r}"]


def compare_review_summary(python_root: Path, rust_root: Path, pick_date: str, method: str) -> list[str]:
    py_path = python_root / "reviews" / f"{pick_date}.{method}" / "summary.json"
    rs_path = rust_root / "reviews" / f"{pick_date}.{method}" / "summary.json"
    if not py_path.exists() or not rs_path.exists():
        return [f"review summary missing: python_exists={py_path.exists()} rust_exists={rs_path.exists()}"]
    py_payload = json.loads(py_path.read_text(encoding="utf-8"))
    rs_payload = json.loads(rs_path.read_text(encoding="utf-8"))
    py_recs = [item.get("code") for item in py_payload.get("recommendations", [])]
    rs_recs = [item.get("code") for item in rs_payload.get("recommendations", [])]
    if py_recs != rs_recs:
        return [f"recommendation codes mismatch: python={py_recs} rust={rs_recs}"]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
