from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from stock_select.market_environment import load_environment_history


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Environment-layered tuning diagnostics for b1 and b2")
    parser.add_argument("--env-start-date", default="2025-11-01")
    parser.add_argument("--env-end-date", default="2026-04-30")
    parser.add_argument("--methods", nargs="+", default=["b1", "b2"])
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    return parser.parse_args(argv)


def collect_method_records(*, method: str, runtime_root: Path) -> list[dict[str, object]]:
    return []


def _resolve_interval_state(intervals: list[dict[str, object]], *, pick_date: str) -> str | None:
    applicable = [
        interval
        for interval in intervals
        if str(interval["start_date"]) <= pick_date
        and (interval.get("end_date") is None or pick_date <= str(interval["end_date"]))
    ]
    if not applicable:
        return None
    preferred = [interval for interval in applicable if bool(interval.get("manual_override"))]
    ranked = preferred or applicable
    newest = max(
        ranked,
        key=lambda interval: (
            str(interval["start_date"]),
            str(interval.get("evaluated_at") or interval["start_date"]),
            bool(interval.get("manual_override")),
        ),
    )
    return str(newest["state"])


def build_environment_layered_records(*, runtime_root: Path, methods: list[str]) -> list[dict[str, object]]:
    intervals = load_environment_history(runtime_root)
    records: list[dict[str, object]] = []
    for method in methods:
        for row in collect_method_records(method=method, runtime_root=runtime_root):
            state = _resolve_interval_state(intervals, pick_date=str(row["pick_date"]))
            records.append({**row, "environment_state": state})
    return records


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    records = build_environment_layered_records(runtime_root=args.runtime_root, methods=args.methods)
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
