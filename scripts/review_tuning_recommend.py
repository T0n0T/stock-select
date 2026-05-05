from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from stock_select.research.review_tuning import build_recommendations, render_recommendation_summary


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_OUTPUT_DIR = DEFAULT_RUNTIME_ROOT / "research" / "review_tuning"


def _resolve_correlations_path(args: argparse.Namespace) -> Path:
    if args.correlations is not None:
        return args.correlations
    if args.artifact_dir is not None:
        return args.artifact_dir / "correlations.json"
    raise ValueError("correlations path is required")


def _resolve_segments_path(args: argparse.Namespace) -> Path:
    if args.segments is not None:
        return args.segments
    if args.artifact_dir is not None:
        return args.artifact_dir / "segments.json"
    raise ValueError("segments path is required")


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir is not None:
        return args.output_dir
    if args.artifact_dir is not None:
        return args.artifact_dir
    return DEFAULT_OUTPUT_DIR


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate review tuning recommendations")
    parser.add_argument("--correlations", type=Path)
    parser.add_argument("--segments", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    correlations = json.loads(_resolve_correlations_path(args).read_text(encoding="utf-8"))
    segments = json.loads(_resolve_segments_path(args).read_text(encoding="utf-8"))
    payload = build_recommendations(correlations, segments)

    output_dir = _resolve_output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "recommendations.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(
        render_recommendation_summary(payload),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
