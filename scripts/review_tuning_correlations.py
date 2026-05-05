from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.research.review_tuning import build_correlation_frame, compute_correlations, read_rows_csv


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_OUTPUT_DIR = DEFAULT_RUNTIME_ROOT / "research" / "review_tuning"


def _resolve_samples_path(args: argparse.Namespace) -> Path:
    if args.samples is not None:
        return args.samples
    if args.artifact_dir is not None:
        return args.artifact_dir / "samples_with_env.csv"
    raise ValueError("samples path is required")


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir is not None:
        return args.output_dir
    if args.artifact_dir is not None:
        return args.artifact_dir
    return DEFAULT_OUTPUT_DIR


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute grouped score-return correlations for review tuning")
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--min-samples-strong", type=int, default=30)
    parser.add_argument("--min-samples-weak", type=int, default=10)
    return parser.parse_args(argv)


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    rows = read_rows_csv(_resolve_samples_path(args))
    payload = compute_correlations(
        rows,
        min_samples_strong=args.min_samples_strong,
        min_samples_weak=args.min_samples_weak,
    )
    output_dir = _resolve_output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "correlations.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    build_correlation_frame(payload).to_csv(output_dir / "correlations.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
