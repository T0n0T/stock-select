"""以滚动样本外 AKQuant 组合净收益选择模型，留出期只用于最终检验。"""
from __future__ import annotations

from collections import Counter, defaultdict
from bisect import bisect_left
from dataclasses import asdict
import csv
import json
import math
from pathlib import Path
from typing import Any, Sequence

from ml.backtest.signal_bundle import SignalBundle, SignalRow
from ml.backtest.akquant_gateway import BacktestConfig, load_market_data, run_akquant_backtest
from ml.backtest.report import write_report
from ml.training.labels import as_float, rows_for_dates
from ml.training import train_lgbm_rank
from ml.training.lgbm_ranker import train_model_result
from ml.training.evaluation import average_metric_dicts, evaluate_model, partition_diagnostics
from ml.training.artifacts import build_model_metadata, write_feature_manifest, write_model_artifacts
from ml.training.features import (
    select_feature_columns, drop_optional_zero_coverage_features,
    validate_selected_feature_coverage, load_feature_manifest_with_levels,
)
from ml.training.trial_params import lightgbm_ranking_params_with_defaults
from ml.tuning.validation import distributed_backtest_splits, exclude_reserved_label_spans


def partition_backtest_dates(
    signal_dates: Sequence[str], sessions: Sequence[str], *, holding_days: int, holdout_dates: int
) -> tuple[list[str], list[str]]:
    calendar = sorted(set(sessions))
    indices = {day: index for index, day in enumerate(calendar)}
    offset = holding_days + 1
    eligible = sorted({day for day in signal_dates if day in indices and indices[day] + offset < len(calendar)})
    if holding_days <= 0 or holdout_dates <= 0 or len(eligible) <= holdout_dates + offset:
        raise ValueError("not enough dates for development and holdout")
    holdout = eligible[-holdout_dates:]
    development = [day for day in eligible if indices[day] + offset < indices[holdout[0]]]
    return development, holdout


def latest_oof_signals(rows: Sequence[dict[str, Any]], *, score_key: str = "candidate_score") -> SignalBundle:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["date"])].append(row)
    output = {}
    for day, day_rows in sorted(grouped.items()):
        latest = max(int(row.get("fold", 0)) for row in day_rows)
        selected = [row for row in day_rows if int(row.get("fold", 0)) == latest]
        ordered = sorted(selected, key=lambda row: (-float(row[score_key]), str(row["code"])))
        output[day] = tuple(
            SignalRow(day, str(row["code"]), float(row[score_key]), rank)
            for rank, row in enumerate(ordered, start=1)
        )
    return SignalBundle(output)


def anchored_training_windows(
    reference_splits: Sequence[tuple[list[str], list[str]]], *, train_date_count: int,
) -> list[tuple[list[str], list[str]]]:
    """只缩短训练历史，保留相同测试日期和隔离区间，供窗口漂移对照。"""
    if train_date_count <= 0 or any(len(train) < train_date_count for train, _ in reference_splits):
        raise ValueError("training window must be positive and fit every reference split")
    return [(list(train[-train_date_count:]), list(test)) for train, test in reference_splits]


def suggest_portfolio_params(trial: Any, *, holding_days: int, top_n: int, label_column: str | None = None) -> dict[str, Any]:
    if holding_days not in {3, 5, 10} or top_n <= 0:
        raise ValueError("supported holding_days are 3, 5, 10; top_n must be positive")
    params = {
        "feature_set": "all",
        "label_column": label_column or f"rank_label_{holding_days}d",
        "categorical_encoding": "one_hot",
        "boosting_type": trial.suggest_categorical("boosting_type", ["gbdt", "dart"]),
        "num_leaves": trial.suggest_categorical("num_leaves", [5, 9, 15]),
        "min_data_in_leaf": trial.suggest_categorical("min_data_in_leaf", [30, 60, 120, 240]),
        "num_boost_round": trial.suggest_categorical("num_boost_round", [40, 60, 80, 120]),
        "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.08, log=True),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.65, 1.0),
        "bagging_freq": 1,
        "feature_fraction": trial.suggest_float("feature_fraction", 0.65, 1.0),
        "lambda_l1": trial.suggest_float("lambda_l1", 0.0, 2.0),
        "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 5.0),
        "min_gain_to_split": trial.suggest_float("min_gain_to_split", 0.0, 0.1),
        "early_stopping_rounds": 0,
    }
    if label_column == "exit_net_return":
        params["training_objective"] = trial.suggest_categorical("training_objective", ["regression", "regression_l1"])
    else:
        params.update(lambdarank_truncation_level=trial.suggest_categorical("lambdarank_truncation_level", [top_n, 5, 10]),
                      eval_at=[top_n, 5, 10])
    return params


def training_rows_before(
    rows: Sequence[dict[str, Any]], dates: set[str], cutoff: str,
    label_ends: dict[tuple[str, str], str], *, label_column: str,
) -> list[dict[str, Any]]:
    if label_column in {"rank_label_exit", "exit_net_return"}:
        from ml.training.policy_labels import policy_training_rows_before
        return policy_training_rows_before(rows, dates, cutoff)
    from ml.dataset.rank_dataset import quartile_labels

    safe = [dict(row) for row in rows_for_dates(rows, dates, label_column=label_column)
            if (end := label_ends.get((str(row["date"]), str(row["code"])))) and end < cutoff]
    # 停牌可把个股的第 N+1 根 K 线推迟到验证期；同时重建日内标签，
    # 避免尚未知晓收益的其他股票通过原有相对排名间接泄漏。
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in safe:
        grouped[str(row["date"])].append(row)
    return_column = label_column.replace("rank_label_", "ret").replace("d", "")
    for day_rows in grouped.values():
        labels = quartile_labels({str(row["code"]): as_float(row.get(return_column)) for row in day_rows})
        for row in day_rows:
            row[label_column] = labels[str(row["code"])]
    return safe


def align_strategy_labels(
    rows: Sequence[dict[str, Any]], market: dict[str, Any], *, holding_days: int,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], str]]:
    from ml.dataset.rank_dataset import quartile_labels

    opens = {symbol: dict(zip(frame["datetime"].dt.strftime("%Y-%m-%d"), frame["open"]))
             for symbol, frame in market.items()}
    dates = {symbol: sorted(prices) for symbol, prices in opens.items()}
    sessions = sorted({day for days in dates.values() for day in days})
    indices = {day: index for index, day in enumerate(sessions)}
    output, ends = [], {}
    column, label = f"ret{holding_days}", f"rank_label_{holding_days}d"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for original in rows:
        row = dict(original)
        day, code = str(row["date"]), str(row["code"])
        row[column], row[label] = "", ""
        index = indices.get(day, len(sessions))
        stock_days, prices = dates.get(code, []), opens.get(code, {})
        if index + holding_days + 1 < len(sessions):
            entry = sessions[index + 1]
            scheduled_exit = sessions[index + holding_days + 1]
            next_exit = bisect_left(stock_days, scheduled_exit)
            if entry in prices and next_exit < len(stock_days):
                exit_day = stock_days[next_exit]
                row[column] = (prices[exit_day] / prices[entry] - 1) * 100
                ends[(day, code)] = exit_day
        output.append(row)
        grouped[day].append(row)
    for day_rows in grouped.values():
        labels = quartile_labels({str(row["code"]): float(row[column]) for row in day_rows if row[column] != ""})
        for row in day_rows:
            row[label] = labels.get(str(row["code"]), "")
    return output, ends


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _write_signals(path: Path, signals: SignalBundle) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "code", "model_score", "model_rank"])
        writer.writeheader()
        for day in signals.dates:
            writer.writerows(asdict(row) for row in signals.rows_for_date(day))


def optimize_portfolio(
    optuna: Any, evaluate: Any, *, output_root: Path, max_trials: int,
    patience: int, seed: int, holding_days: int, top_n: int,
    label_column: str | None = None,
) -> dict[str, Any]:
    if not 1 <= max_trials <= 12 or patience <= 0:
        raise ValueError("max_trials must be 1..12 and patience must be positive")
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed, n_startup_trials=4))
    trials = []
    best = -math.inf
    stale = 0

    def objective(trial: Any) -> float:
        nonlocal best, stale
        params = suggest_portfolio_params(trial, holding_days=holding_days, top_n=top_n, label_column=label_column)
        directory = output_root / f"optuna-trial-{trial.number + 1:03d}"
        evaluation = evaluate(params, directory)
        score = float(evaluation["backtest_metrics"]["total_return_pct"])
        if not math.isfinite(score):
            raise ValueError("AKQuant objective must be a finite portfolio return")
        item = {"trial": trial.number + 1, "score": score, "params": params, "output_dir": str(directory), **evaluation}
        trials.append(item)
        trial.set_user_attr("backtest_metrics", evaluation["backtest_metrics"])
        trial.set_user_attr("output_dir", str(directory))
        if score > best:
            best, stale = score, 0
        else:
            stale += 1
        _write_json(output_root / "trials_checkpoint.json", trials)
        if stale >= patience:
            study.stop()
        return score

    # 顺序 trial；每个 LightGBM 模型内部最多使用 8 线程。
    study.optimize(objective, n_trials=max_trials)
    winner = trials[study.best_trial.number]
    return {"strategy": "optuna", "objective": "akquant_oof_net_total_return_pct", "direction": "maximize",
            "optuna_version": optuna.__version__, "seed": seed, "sampler": "TPESampler(n_startup_trials=4)",
            "best_trial": winner["trial"], "best_score": winner["score"], "best_params": winner["params"],
            "best_output_dir": winner["output_dir"], "trials": trials,
            "stop_reason": "patience" if stale >= patience else "max_trials"}


class PortfolioEvaluator:
    """固定数据、成本、仓位与切分；trial 只能改变模型参数。"""

    def __init__(self, args: Any):
        self.args = args
        self.root = args.output_root or Path("diagnostics") / "ml" / args.method / "tuning"
        self.dataset = train_lgbm_rank.resolve_dataset_path(args.dataset, method=args.method)
        self.rows = train_lgbm_rank.read_dataset(self.dataset)
        if not self.rows:
            raise ValueError("dataset is empty")
        print(f"[akquant] dataset rows={len(self.rows)} dates={len({row['date'] for row in self.rows})}", flush=True)
        self.market = load_market_data(args.market_data)
        print(f"[akquant] market symbols={len(self.market)}", flush=True)
        symbol_dates = {symbol: sorted(frame["datetime"].dt.strftime("%Y-%m-%d")) for symbol, frame in self.market.items()}
        sessions = sorted({day for dates in symbol_dates.values() for day in dates})
        self.validation_plan = None
        self.holdout_splits = []
        if getattr(args, "validation_scheme", "tail") == "quarter-blocks":
            self.validation_plan = distributed_backtest_splits(
                [str(row["date"]) for row in self.rows], sessions,
                initial_train_dates=args.initial_train_dates, test_dates=args.rolling_test_dates,
                holdout_dates=args.holdout_dates, purge_gap=args.holding_days + 1, seed=args.seed,
            )
            self.development = self.validation_plan["development_dates"]
            self.holdout = self.validation_plan["holdout_dates"]
            self.holdout_splits = self.validation_plan["holdout_splits"]
        else:
            self.development, self.holdout = partition_backtest_dates(
                [str(row["date"]) for row in self.rows], sessions,
                holding_days=args.holding_days, holdout_dates=args.holdout_dates,
            )
        self.label_column = f"rank_label_{args.holding_days}d"
        self.exit_policy = self.exit_market = None
        self.label_summary = {}
        self.root.mkdir(parents=True, exist_ok=True)
        if getattr(args, "exit_policy", None):
            from ml.backtest.rule_exit import ExitMarket, load_exit_policy
            from ml.training.policy_labels import align_exit_labels
            self.exit_policy = load_exit_policy(args.exit_policy)
            self.exit_market = ExitMarket(self.market, self.exit_policy)
            labelled, self.label_ends = align_exit_labels(self.rows, self.exit_market)
            regression = getattr(args, "learning_task", "rank") == "return-regression"
            self.label_column = "exit_net_return" if regression else "rank_label_exit"
            self.label_summary = {"row_count": len(labelled), "statuses": dict(Counter(row["exit_label_status"] for row in labelled)),
                                  "exit_reasons": dict(Counter(row["exit_reason"] for row in labelled if row["exit_reason"])),
                                  "target": ("按规则退出的比例费率净收益百分比（连续有符号值）" if regression
                                             else "按规则退出的比例费率净收益，同日四分位（同收益同档）"),
                                  "cost_limit": "标签不含随成交金额变化的最低佣金；组合回测包含最低佣金",
                                  "censoring": "无退出事件的样本不填零收益，训练按实际退出日期隔离"}
            with (self.root / "policy_dataset.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(labelled[0]))
                writer.writeheader()
                writer.writerows(labelled)
            # 只按信号当日历史是否足够过滤，不按未来是否有标签过滤预测候选。
            self.rows = [row for row in labelled if self.exit_market.ready(str(row["code"]), str(row["date"]))]
            self.label_summary["prediction_ready_rows"] = len(self.rows)
            _write_json(self.root / "label_summary.json", self.label_summary)
        else:
            self.rows, self.label_ends = align_strategy_labels(self.rows, self.market, holding_days=args.holding_days)
        self.fit_rows = (exclude_reserved_label_spans(self.rows, self.label_ends, self.holdout)
                         if self.validation_plan else self.rows)
        self.development_end = sessions[-1] if self.validation_plan else sessions[sessions.index(self.holdout[0])-1]
        self.holdout_end = sessions[-1]
        self.calendar_symbol = max(self.market, key=lambda code: len(self.market[code]))
        self.splits = self.validation_plan["development_splits"] if self.validation_plan else train_lgbm_rank.rolling_walk_forward_splits(
            self.development, train_date_count=args.rolling_train_dates,
            test_date_count=args.rolling_test_dates, fold_count=args.rolling_folds,
            purge_gap=args.holding_days + 1,
        )
        first_train = training_rows_before(self.fit_rows, set(self.splits[0][0]), self.splits[0][1][0],
                                         self.label_ends, label_column=self.label_column)
        self.fixed_levels = {}
        if args.feature_manifest:
            numeric, categorical, self.fixed_levels = load_feature_manifest_with_levels(
                args.feature_manifest, available_columns=set(self.rows[0]), method=args.method)
        else:
            numeric, categorical = select_feature_columns(self.rows[0].keys(), feature_set="all", method=args.method)
        self.numeric, self.categorical, self.dropped = drop_optional_zero_coverage_features(
            first_train, numeric_columns=numeric, categorical_columns=categorical)
        self.coverage = validate_selected_feature_coverage(first_train, numeric_columns=self.numeric, categorical_columns=self.categorical)
        print(f"[akquant] ready development_folds={len(self.splits)} holdout_dates={len(self.holdout)} "
              f"features={len(self.numeric) + len(self.categorical)} training_pool_rows={len(self.fit_rows)}", flush=True)
        self.config = BacktestConfig(top_n=args.top_n, holding_days=args.holding_days,
                                    capital_allocation=args.capital_allocation, stamp_tax_rate=0.0005,
                                    defer_suspended_exit=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.split_summary = {
            "validation_scheme": getattr(args, "validation_scheme", "tail"),
            "distributed_plan": self.validation_plan,
            "reserved_label_span_rows_excluded": len(self.rows) - len(self.fit_rows),
            "development_dates": self.development, "holdout_dates": self.holdout,
            "rolling_splits": [{"train": train, "test": test} for train, test in self.splits],
            "purge_gap": args.holding_days + 1, "additional_label_end_purge": True,
            "holdout_used_for_selection": False, "backtest_config": asdict(self.config),
            "label_column": self.label_column,
            "label_alignment": ("共享退出状态机，次日开盘买入，当日收盘退出；训练按实际退出日隔离"
                                if self.exit_policy else "按全市场交易日持有 N 日；退出日无 K 线则延至首个可交易开盘；训练检查实际退出日"),
            "exit_policy": asdict(self.exit_policy) if self.exit_policy else None,
            "label_summary": self.label_summary,
            "development_backtest_end": self.development_end,
            "factor_pruning": {"baseline_no_pruning": True, "dropped_zero_coverage": self.dropped,
                               "reason": "仅自动剔除首折训练区间全空的可选特征，保留其他 method 适用特征"},
        }
        _write_json(self.root / "split.json", self.split_summary)

    def _fit(self, train_dates: Sequence[str], test_dates: Sequence[str], params: dict[str, Any], *, metrics_as_of: str | None = None) -> tuple[Any, dict[str, Any]]:
        train = training_rows_before(self.fit_rows, set(train_dates), test_dates[0], self.label_ends, label_column=self.label_column)
        test = rows_for_dates(self.rows, set(test_dates), label_column=self.label_column, require_label=False)
        model_params = lightgbm_ranking_params_with_defaults(params)
        objective = model_params.get("training_objective", "lambdarank")
        if self.label_column == "exit_net_return" and objective not in {"regression", "regression_l1"}:
            raise ValueError("exit_net_return requires a regression training_objective")
        if self.label_column != "exit_net_return" and objective != "lambdarank":
            raise ValueError("rank labels require lambdarank training_objective")
        if objective != "lambdarank":
            for key in ("label_gain", "eval_at", "lambdarank_truncation_level"):
                model_params.pop(key, None)
        model_params.update(num_threads=self.args.num_threads, seed=self.args.seed, early_stopping_rounds=0)
        model_params.pop("categorical_encoding", None)
        result = train_model_result(train, test, numeric_columns=self.numeric, categorical_columns=self.categorical,
                                    fixed_categorical_levels=self.fixed_levels, categorical_encoding="one_hot",
                                    label_column=self.label_column, **model_params)
        if result.model is None:
            raise ValueError("not enough matured training labels or prediction candidates for this split")
        print(f"[akquant] fit train={train_dates[0]}..{train_dates[-1]} test={test_dates[0]}..{test_dates[-1]} rows={len(train)}/{len(test)}", flush=True)
        metric_test = self._metric_rows(result.test_scored, metrics_as_of or test_dates[-1])
        report = {
            "method": self.args.method, "dataset": str(self.dataset), "feature_set": "all", "train_mode": "overall",
            "label_column": self.label_column, "model_params": model_params, "categorical_encoding": "one_hot",
            "train_start_date": train_dates[0], "train_end_date": train_dates[-1],
            "test_start_date": test_dates[0], "test_end_date": test_dates[-1],
            "train_row_count": len(train), "test_row_count": len(test), "feature_count": result.feature_count,
            "actual_train_date_count": len({str(row["date"]) for row in train}),
            "metrics_as_of": metrics_as_of or test_dates[-1],
            "purged_unavailable_labels": len(rows_for_dates(self.rows, set(train_dates), label_column=self.label_column)) - len(train),
            "purge_gap": self.args.holding_days + 1, "metrics": {
                "train": evaluate_model(result.train_scored, top_n=self.args.top_n),
                "test": evaluate_model(metric_test, top_n=self.args.top_n),
            },
            "top_features": result.top_features, "rf_diagnostics": {"status": "skipped_by_default"},
            "factor_pruning": self.split_summary["factor_pruning"],
            "feature_coverage": self.coverage,
        }
        return result, {"report": report, "train": train, "test": test}

    def _metric_rows(self, scored: Sequence[dict[str, Any]], as_of: str) -> list[dict[str, Any]]:
        output = []
        for original in scored:
            row = dict(original)
            if self.exit_policy and (not row.get("exit_date") or str(row["exit_date"]) > as_of):
                row.update(exit_return="", exit_net_return="", rank_label_exit="")
            output.append(row)
        return output

    def _portfolio(self, signals: SignalBundle, directory: Path) -> dict[str, Any]:
        directory.mkdir(parents=True, exist_ok=True)
        _write_signals(directory / "signals.csv", signals)
        selected = {row.code for day in signals.dates for row in signals.rows_for_date(day)[:self.config.top_n]}
        selected.add(self.calendar_symbol)
        end_date = self.development_end if not self.validation_plan and signals.dates[-1] < self.holdout[0] else self.holdout_end
        result = run_akquant_backtest({code: self.market[code] for code in selected}, signals, self.config,
                                     exit_policy=self.exit_policy, exit_market=self.exit_market,
                                     end_date=end_date if self.exit_policy else None)
        report = write_report(result, directory / "backtest.json")
        if self.exit_market is not None:
            for event in report["exit_events"]:
                expected = self.exit_market.outcome(event["code"], event["signal_date"], as_of=end_date)
                if expected.get("exit_date") != event["exit_date"] or expected.get("exit_price") != event["exit_price"]:
                    raise RuntimeError("label and backtest exit mismatch")
        return report["metrics"]

    def evaluate(self, params: dict[str, Any], directory: Path) -> dict[str, Any]:
        print(f"[akquant] evaluate {directory.name}", flush=True)
        predictions, fold_reports = [], []
        for fold, (train_dates, test_dates) in enumerate(self.splits, 1):
            result, details = self._fit(train_dates, test_dates, params,
                                        metrics_as_of=self.development_end if self.validation_plan else None)
            fold_reports.append({"fold": fold, **details["report"]})
            predictions.extend({**row, "fold": fold, "candidate_score": row["model_score"]} for row in result.test_scored)
        signals = latest_oof_signals(predictions)
        metrics = self._portfolio(signals, directory)
        predictions = self._metric_rows(predictions, self.development_end)
        rolling = {"fold_count": len(fold_reports), "train_date_count": None if self.validation_plan else self.args.rolling_train_dates,
                   "actual_train_date_counts": [fold["actual_train_date_count"] for fold in fold_reports],
                   "test_date_count": self.args.rolling_test_dates,
                   "test_avg": average_metric_dicts([fold["metrics"]["test"] for fold in fold_reports])}
        summary = {"backtest_metrics": metrics, "rolling_summary": rolling, "folds": fold_reports,
                   "by_month": partition_diagnostics(predictions, partition="month"),
                   "by_env": partition_diagnostics(predictions, partition="env"),
                   "signal_start": signals.dates[0], "signal_end": signals.dates[-1], "signal_dates": len(signals.dates)}
        _write_json(directory / "evaluation.json", summary)
        print(f"[akquant] result {directory.name} return_pct={metrics.get('total_return_pct')} "
              f"drawdown_pct={metrics.get('max_drawdown_pct')}", flush=True)
        return summary

    def evaluate_holdout(
        self, params: dict[str, Any], directory: Path, *, development_evaluation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        training_dates = self.development[-self.args.rolling_train_dates:] if self.exit_policy else self.development
        splits = self.holdout_splits or [(training_dates, self.holdout)]
        scored, holdout_reports = [], []
        for fold, (train_dates, test_dates) in enumerate(splits, 1):
            result, details = self._fit(train_dates, test_dates, params, metrics_as_of=self.holdout_end)
            scored.extend({**row, "fold": fold, "candidate_score": row["model_score"]} for row in result.test_scored)
            holdout_reports.append({"fold": fold, **details["report"]})
        signals = latest_oof_signals(scored)
        metrics = self._portfolio(signals, directory)
        metric_scored = self._metric_rows(scored, self.holdout_end)
        manifest = write_feature_manifest(directory, numeric_columns=self.numeric, categorical_columns=self.categorical,
                                          fixed_categorical_levels=result.category_levels, categorical_encoding="one_hot")
        metadata = build_model_metadata(
            feature_manifest=str(manifest), train_rows=details["train"], score_rows=details["test"],
            numeric_columns=self.numeric, categorical_columns=self.categorical, levels=result.category_levels,
            feature_names=result.feature_names, lightgbm_feature_names=result.lightgbm_feature_names,
            label_column=self.label_column, model_params=details["report"]["model_params"],
            categorical_encoding="one_hot", categorical_code_maps=result.categorical_code_maps)
        if self.exit_policy is not None:
            metadata["training_target"] = {"label_column": self.label_column, "exit_policy": asdict(self.exit_policy),
                                           "entry": "next_open", "exit": "current_close", "t_plus_one": True,
                                           "rank_bins": (None if self.label_column == "exit_net_return"
                                                         else "four_equal_count_bins_ties_share_bin"),
                                           "score_units": ("net_return_percentage_points" if self.label_column == "exit_net_return"
                                                           else "relative_rank_score"),
                                           "training_objective": details["report"]["model_params"].get("training_objective", "lambdarank")}
        artifacts = write_model_artifacts(result.model, metadata, directory)
        report = {**details["report"], "backtest_metrics": metrics, "model_artifacts": artifacts,
                  "metrics": {"train": details["report"]["metrics"]["train"],
                              "test": evaluate_model(metric_scored, top_n=self.args.top_n)},
                  "evaluated_prediction_rows": len(metric_scored),
                  "evaluated_signal_dates": signals.dates,
                  "feature_manifest": str(manifest),
                  "rolling_summary": (development_evaluation or {}).get("rolling_summary", {}),
                  "rolling_folds": (development_evaluation or {}).get("folds", []),
                  "validation_roles": {"rolling": "development_only_parameter_selection",
                                       "test": "distributed_walk_forward_holdout" if self.holdout_splits else "final_holdout",
                                       "exported_model": "last_holdout_fold"},
                  "holdout_folds": holdout_reports,
                  "by_month": partition_diagnostics(metric_scored, partition="month"),
                  "by_env": partition_diagnostics(metric_scored, partition="env")}
        _write_json(directory / "lgbm_rank_report_holdout.json", report)
        return {"output_dir": str(directory), "backtest_metrics": metrics, "metrics": report["metrics"],
                "top_features": result.top_features, "feature_count": result.feature_count,
                "holdout_folds": holdout_reports,
                "by_month": report["by_month"], "by_env": report["by_env"]}


def run_akquant_study(args: Any, optuna: Any) -> dict[str, Any]:
    if args.market_data is None:
        raise ValueError("--objective akquant requires --market-data")
    if args.holding_days not in {3, 5, 10}:
        raise ValueError("holding-days must match a supported label horizon: 3, 5, 10")
    evaluator = PortfolioEvaluator(args)
    baseline_params = {"feature_set": "all", "label_column": evaluator.label_column, "num_leaves": 15,
                       "min_data_in_leaf": 20, "num_boost_round": 120, "learning_rate": 0.05,
                       "early_stopping_rounds": 0, "categorical_encoding": "one_hot"}
    if evaluator.label_column == "exit_net_return":
        baseline_params["training_objective"] = "regression"
    baseline = evaluator.evaluate(baseline_params, evaluator.root / "fixed-baseline")
    summary = optimize_portfolio(optuna, evaluator.evaluate, output_root=evaluator.root,
                                 max_trials=args.max_trials, patience=args.patience, seed=args.seed,
                                 holding_days=args.holding_days, top_n=args.top_n,
                                 label_column=evaluator.label_column)
    # 必须先选出 winner，再读取留出期的收益；留出结果不会回流给 study。
    _write_json(evaluator.root / "selection.json", summary)
    winner = next(trial for trial in summary["trials"] if trial["trial"] == summary["best_trial"])
    summary["holdout"] = evaluator.evaluate_holdout(
        summary["best_params"], evaluator.root / "holdout_model", development_evaluation=winner)
    summary["baseline_holdout"] = evaluator.evaluate_holdout(
        baseline_params, evaluator.root / "baseline_holdout", development_evaluation=baseline)
    summary.update(method=args.method, dataset=str(evaluator.dataset), output_root=str(evaluator.root),
                   split=evaluator.split_summary, baseline=baseline)
    return summary
