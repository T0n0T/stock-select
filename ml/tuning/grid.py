from __future__ import annotations

from ml.methods import SUPPORTED_METHODS

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .configs import training_kwargs_from_trial
from .objectives import resolve_objective
from ml.training import train_lgbm_rank
from ml.parallelism import MAX_WORKERS, parse_worker_count


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
    if getattr(args, "visualize", False):
        print("warning: --visualize only applies to --strategy optuna; ignoring for grid search")
    objective_fn = resolve_objective(args.objective)
    output_root = args.output_root or Path("diagnostics") / "ml" / args.method / "tuning"
    dataset = train_lgbm_rank.resolve_dataset_path(args.dataset, method=args.method)
    results = []
    for index, trial in enumerate(default_grid_trials(args.max_trials), start=1):
        output_dir = output_root / f"trial_{index:03d}"
        kwargs = training_kwargs_from_trial(trial)
        kwargs.setdefault("seed", args.seed)
        if getattr(args, "num_threads", 0):
            kwargs.setdefault("num_threads", args.num_threads)
        report = train_lgbm_rank.train_and_report(
            dataset,
            output_dir,
            test_ratio=args.test_ratio,
            num_boost_round=args.num_boost_round,
            learning_rate=args.learning_rate,
            rolling_folds=args.rolling_folds,
            rolling_train_dates=args.rolling_train_dates,
            rolling_test_dates=args.rolling_test_dates,
            purge_gap=getattr(args, "purge_gap", None),
            method=args.method,
            feature_manifest=getattr(args, "feature_manifest", None),
            rf_diagnostics=not args.skip_rf_diagnostics,
            **kwargs,
        )
        results.append({"trial": index, "output_dir": str(output_dir), "score": objective_fn(report), "params": trial})
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "tuning_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "strategy": "grid",
                "method": args.method,
                "objective": args.objective,
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
    parser.add_argument("--method", choices=SUPPORTED_METHODS, default="b2")
    parser.add_argument("--strategy", choices=["grid", "optuna"], default="grid")
    parser.add_argument("--max-trials", type=int, default=12)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--feature-manifest", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--num-boost-round", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--rolling-folds", type=int, default=0)
    parser.add_argument("--rolling-train-dates", type=int, default=240)
    parser.add_argument("--rolling-test-dates", type=int, default=40)
    parser.add_argument("--skip-rf-diagnostics", action="store_true")
    parser.add_argument("--num-threads", type=parse_worker_count, default=MAX_WORKERS, help="训练线程数，1～8，默认 8")
    parser.add_argument("--purge-gap", type=int, help="训练与验证之间剔除的日期数；默认按 label 前视窗口计算")
    parser.add_argument(
        "--allow-native-categorical",
        action="store_true",
        help="include LightGBM native categorical encoding in Optuna search; default keeps one-hot only",
    )
    parser.add_argument(
        "--objective",
        choices=["default", "top3_ret10_ge_10", "akquant"],
        default="default",
        help="Optuna/grid objective used to rank trials",
    )
    parser.add_argument("--market-data", type=Path, help="AKQuant 目标需要的 OHLCV CSV/Parquet")
    parser.add_argument("--exit-policy", type=Path, help="规则退出 JSON；同步生成 rank_label_exit 并用于 AKQuant 执行")
    parser.add_argument("--learning-task", choices=["rank", "return-regression"], default="rank",
                        help="规则退出目标：四档相对排序，或直接回归扣费收益百分比")
    parser.add_argument("--holdout-dates", type=int, default=40, help="末段留出日期数；quarter-blocks 模式为每季度留出日期数")
    parser.add_argument("--validation-scheme", choices=["tail", "quarter-blocks"], default="tail",
                        help="AKQuant 验证：末段留出，或按季度随机分配连续选参/留出窗口")
    parser.add_argument("--initial-train-dates", type=int, default=120,
                        help="quarter-blocks 开始抽取测试窗口前的训练日期数，之后扩展历史")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--holding-days", type=int, choices=[3, 5, 10], default=3)
    parser.add_argument("--capital-allocation", type=float, default=0.99)
    parser.add_argument("--patience", type=int, default=4, help="AKQuant 目标连续未改善的停止次数")
    parser.add_argument("--visualize", action="store_true", help="generate Optuna visualization HTML files")
    parser.add_argument("--visual-output-dir", type=Path, help="directory for Optuna visualization output")
    parser.add_argument("--visual-format", choices=["html"], default="html", help="visualization output format")
    parser.set_defaults(handler=main_from_args)
    return parser


def main_from_args(args: argparse.Namespace) -> int:
    if getattr(args, "validation_scheme", "tail") == "quarter-blocks" and args.objective != "akquant":
        raise ValueError("quarter-blocks requires --objective akquant")
    if getattr(args, "learning_task", "rank") == "return-regression" and (
        args.objective != "akquant" or getattr(args, "exit_policy", None) is None
    ):
        raise ValueError("return-regression requires --objective akquant and --exit-policy")
    if getattr(args, "exit_policy", None) is not None and args.objective != "akquant":
        raise ValueError("--exit-policy requires --objective akquant")
    if args.objective == "akquant" and args.strategy != "optuna":
        raise ValueError("--objective akquant requires --strategy optuna")
    if args.strategy == "optuna":
        from .optuna_search import run_optuna_search

        return run_optuna_search(args)
    return run_grid_search(args)
