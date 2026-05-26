#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check stock-select chart PNG artifacts.")
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--pick-date", required=True)
    parser.add_argument("--method", required=True, choices=["b1", "b2", "dribull"])
    parser.add_argument("--compare-root", type=Path)
    args = parser.parse_args()

    failures: list[str] = []
    candidates = load_candidate_codes(args.runtime_root, args.pick_date, args.method)
    chart_dir = chart_directory(args.runtime_root, args.pick_date, args.method)
    failures.extend(check_chart_set(chart_dir, candidates))

    if args.compare_root is not None:
        compare_chart_dir = chart_directory(args.compare_root, args.pick_date, args.method)
        failures.extend(compare_dimensions(chart_dir, compare_chart_dir, candidates))

    if failures:
        print("FAIL chart smoke check", file=sys.stderr)
        for failure in failures[:50]:
            print(f"- {failure}", file=sys.stderr)
        if len(failures) > 50:
            print(f"- ... {len(failures) - 50} more failures", file=sys.stderr)
        return 1

    print(
        f"PASS chart smoke method={args.method} pick_date={args.pick_date} "
        f"charts={len(candidates)}"
    )
    return 0


def load_candidate_codes(runtime_root: Path, pick_date: str, method: str) -> list[str]:
    path = runtime_root / "candidates" / f"{pick_date}.{method}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"candidate artifact not found: {path}") from None
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise SystemExit(f"candidate artifact missing list field: {path}")
    codes: list[str] = []
    for item in candidates:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str):
            raise SystemExit(f"invalid candidate item in {path}: {item!r}")
        codes.append(str(item["code"]))
    return codes


def chart_directory(runtime_root: Path, pick_date: str, method: str) -> Path:
    return runtime_root / "charts" / f"{pick_date}.{method}"


def check_chart_set(chart_dir: Path, codes: list[str]) -> list[str]:
    failures: list[str] = []
    if not chart_dir.is_dir():
        return [f"chart directory not found: {chart_dir}"]

    expected = {f"{code}_day.png" for code in codes}
    actual = {path.name for path in chart_dir.glob("*_day.png")}
    if expected != actual:
        failures.append(
            "chart filename set mismatch: "
            f"missing={sorted(expected - actual)[:30]} extra={sorted(actual - expected)[:30]}"
        )

    for code in codes:
        path = chart_dir / f"{code}_day.png"
        if not path.exists():
            continue
        failures.extend(check_png(path))
    return failures


def check_png(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [f"{path} cannot be read: {exc}"]
    if len(data) < 33:
        return [f"{path} too small to be a valid PNG"]
    if not data.startswith(PNG_SIGNATURE):
        return [f"{path} missing PNG signature"]
    if data[12:16] != b"IHDR":
        return [f"{path} missing IHDR chunk"]
    width, height = struct.unpack(">II", data[16:24])
    failures: list[str] = []
    if width <= 0 or height <= 0:
        failures.append(f"{path} invalid dimensions {width}x{height}")
    if path.stat().st_size <= 1024:
        failures.append(f"{path} suspiciously small size={path.stat().st_size}")
    return failures


def compare_dimensions(chart_dir: Path, compare_chart_dir: Path, codes: list[str]) -> list[str]:
    failures: list[str] = []
    if not compare_chart_dir.is_dir():
        return [f"compare chart directory not found: {compare_chart_dir}"]
    for code in codes:
        left = chart_dir / f"{code}_day.png"
        right = compare_chart_dir / f"{code}_day.png"
        if not left.exists() or not right.exists():
            continue
        try:
            left_dims = png_dimensions(left)
            right_dims = png_dimensions(right)
        except ValueError as exc:
            failures.append(f"{code} invalid PNG for dimension compare: {exc}")
            continue
        if left_dims != right_dims:
            failures.append(f"{code} dimensions mismatch: runtime={left_dims} compare={right_dims}")
    return failures


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise ValueError(str(path))
    return struct.unpack(">II", data[16:24])


if __name__ == "__main__":
    raise SystemExit(main())
