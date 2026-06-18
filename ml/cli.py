from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .backfill import candidates as backfill_candidates
from .backfill import runs as backfill_runs
from .dataset import rank_dataset
from .diagnostics import controlled_rerank
from .model_ops import archive as model_archive
from .model_ops import promote as model_promote
from .model_ops import status as model_status
from .scoring import export_lgbm_scores, score_blends
from .training import train_lgbm_rank
from .tuning import grid as tune_lgbm_rank


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-select-ml")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    subparsers = parser.add_subparsers(dest="group")

    backfill = subparsers.add_parser("backfill")
    backfill_subparsers = backfill.add_subparsers(dest="command")
    backfill_candidates.add_parser(backfill_subparsers)
    backfill_runs.add_parser(backfill_subparsers)

    dataset = subparsers.add_parser("dataset")
    dataset_subparsers = dataset.add_subparsers(dest="command")
    rank_dataset.add_parser(dataset_subparsers)

    train = subparsers.add_parser("train")
    train_subparsers = train.add_subparsers(dest="command")
    train_lgbm_rank.add_parser(train_subparsers)

    tune = subparsers.add_parser("tune")
    tune_subparsers = tune.add_subparsers(dest="command")
    tune_lgbm_rank.add_parser(tune_subparsers)

    score = subparsers.add_parser("score")
    score_subparsers = score.add_subparsers(dest="command")
    export_lgbm_scores.add_parser(score_subparsers)
    score_blends.add_parser(score_subparsers)

    diagnostics = subparsers.add_parser("diagnostics")
    diagnostics_subparsers = diagnostics.add_subparsers(dest="command")
    controlled_rerank.add_parser(diagnostics_subparsers)

    model = subparsers.add_parser("model")
    model_subparsers = model.add_subparsers(dest="command")
    model_status.add_parser(model_subparsers)
    model_archive.add_parser(model_subparsers)
    model_promote.add_dry_run_promote_parser(model_subparsers)
    model_promote.add_promote_parser(model_subparsers)
    model_promote.add_rollback_parser(model_subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.version:
        print(f"stock-select-ml {__version__}")
        return 0
    handler = getattr(args, "handler", None)
    if handler is not None:
        return int(handler(args))
    parser.print_usage(sys.stderr)
    return 2


def entrypoint() -> int:
    return main()
