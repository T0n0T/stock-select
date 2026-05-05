from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.research.review_tuning import compute_correlations


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_OUTPUT_DIR = DEFAULT_RUNTIME_ROOT / "research" / "review_tuning"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute grouped score-return correlations for review tuning")
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-samples-strong", type=int, default=30)
    parser.add_argument("--min-samples-weak", type=int, default=10)
    return parser.parse_args(argv)


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    rows = pd.read_csv(args.samples).to_dict("records")
    payload = compute_correlations(
        rows,
        min_samples_strong=args.min_samples_strong,
        min_samples_weak=args.min_samples_weak,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "correlations.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
