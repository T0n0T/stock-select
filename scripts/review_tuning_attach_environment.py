from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.market_environment import load_environment_history
from stock_select.research.review_tuning import attach_environment_state


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_OUTPUT_DIR = DEFAULT_RUNTIME_ROOT / "research" / "review_tuning"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attach market environment labels to review tuning samples")
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--environment-key", default="score_based_state")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    rows = pd.read_csv(args.samples).to_dict("records")
    history = load_environment_history(args.runtime_root)
    tagged = attach_environment_state(rows, history, environment_key=args.environment_key)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(tagged).to_csv(args.output_dir / "samples_with_env.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
