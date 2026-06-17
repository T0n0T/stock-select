from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .configs import training_kwargs_from_trial
from .objectives import score_trial_report
from ml.training import train_lgbm_rank


def default_grid_trials(max_trials: int = 12) -> list[dict[str, Any]]:
    base_trials: list[dict[str, Any]] = []
    for boosting_type in ["gbdt", "dart"]:
        for num_leaves in [15, 31]:
            for truncation in [5, 10, 20]:
                base_trials.append(
                    {
                        "feature_set": "raw_numeric",
                        "label_column": "rank_label_3d",
                        "num_leaves": num_leaves,
                        "min_data_in_leaf": 60 if num_leaves == 31 else 30,
                        "lambdarank_truncation_level": truncation,
                        "top_k": [3, 5, 10, 20],
                        "eval_at": [5, 10, 20],
                        "boosting_type": boosting_type,
                        "bagging_fraction": 0.8,
                        "feature_fraction": 0.8,
                        "lambda_l1": 0.0 if boosting_type == "gbdt" else 1.0,
                        "lambda_l2": 1.0 if boosting_type == "gbdt" else 2.0,
                    }
                )
    return base_trials[:max_trials]


def run_grid_search(args: argparse.Namespace) -> int:
    output_root = args.output_root or Path("diagnostics") / "ml" / args.method / "tuning"
    dataset = train_lgbm_rank.resolve_dataset_path(args.dataset, method=args.method)
    results = []
    for index, trial in enumerate(default_grid_trials(args.max_trials), start=1):
        output_dir = output_root / f"trial_{index:03d}"
        kwargs = training_kwargs_from_trial(trial)
        kwargs.setdefault("seed", args.seed)
        report = train_lgbm_rank.train_and_report(
            dataset,
            output_dir,
            test_ratio=args.test_ratio,
            num_boost_round=args.num_boost_round,
            learning_rate=args.learning_rate,
            rolling_folds=args.rolling_folds,
            rolling_train_dates=args.rolling_train_dates,
            rolling_test_dates=args.rolling_test_dates,
            method=args.method,
            rf_diagnostics=not args.skip_rf_diagnostics,
            **kwargs,
        )
        results.append({"trial": index, "output_dir": str(output_dir), "score": score_trial_report(report), "params": trial})
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "tuning_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "strategy": "grid",
                "method": args.method,
                "dataset": str(dataset),
                "output_root": str(output_root),
                "trials": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote tuning summary to {summary_path}")
    return 0


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("lgbm-rank", description="Tune LightGBM ranker.")
    parser.add_argument("--method", default="b2")
    parser.add_argument("--strategy", choices=["grid", "optuna"], default="grid")
    parser.add_argument("--max-trials", type=int, default=12)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--num-boost-round", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--rolling-folds", type=int, default=0)
    parser.add_argument("--rolling-train-dates", type=int, default=240)
    parser.add_argument("--rolling-test-dates", type=int, default=40)
    parser.add_argument("--skip-rf-diagnostics", action="store_true")
    parser.set_defaults(handler=main_from_args)
    return parser


def main_from_args(args: argparse.Namespace) -> int:
    if args.strategy == "optuna":
        from .optuna_search import run_optuna_search

        return run_optuna_search(args)
    return run_grid_search(args)
