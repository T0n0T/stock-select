#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.review.recurring_candidates import add_arguments, main_from_args


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Mark recurring candidate symbols in review-list output.")
    add_arguments(parser)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return int(main_from_args(args))


if __name__ == "__main__":
    raise SystemExit(main())
