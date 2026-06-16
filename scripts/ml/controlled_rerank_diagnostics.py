# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "lightgbm",
#   "numpy",
# ]
# ///
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ml.train_rank_lgbm import (
    DEFAULT_CATEGORICAL_ENCODING,
    DEFAULT_LABEL_GAIN,
    as_float,
    average_metric_dicts,
    evaluate_model,
    load_feature_manifest_encoding,
    load_feature_manifest_with_levels,
    read_dataset,
    rolling_walk_forward_splits,
    rows_for_dates,
    train_model_result,
)


DEFAULT_METHOD = "b3"
DEFAULT_DATASET = PROJECT_ROOT / "diagnostics" / "ml" / DEFAULT_METHOD / "controlled-online-window" / "rank_dataset.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "diagnostics" / "ml" / DEFAULT_METHOD / "controlled-online-window" / "rerank-diagnostics"
DEFAULT_ALPHAS = [0.2, 0.4, 0.6]


@dataclass(frozen=True)
class TrialModelConfig:
    name: str
    numeric_columns: list[str]
    categorical_columns: list[str]
    fixed_categorical_levels: dict[str, list[str]]
    categorical_encoding: str
    label_column: str
    model_params: dict[str, Any]
    trial_dir: str | None = None


def rows_by_fold(rows: Sequence[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row.get("fold") or 0)].append(row)
    return dict(grouped)


def partition_diagnostics_for_top_n(
    rows: Sequence[dict[str, Any]],
    *,
    partition: str,
    top_n: int,
) -> dict[str, Any]:
    partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if partition == "env":
            key = str(row.get("env") or "unknown").lower()
        elif partition == "month":
            key = str(row.get("date") or "unknown")[:7]
        else:
            raise ValueError(f"unsupported partition: {partition}")
        partitions[key].append(row)
    return {
        key: {
            "row_count": len(partition_rows),
            "metrics": evaluate_model(partition_rows, top_n=top_n),
        }
        for key, partition_rows in sorted(partitions.items())
        if partition_rows
    }


def average_partition_metrics(fold_values: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    row_counts: dict[str, int] = defaultdict(int)
    for value in fold_values:
        for key, diagnostics in (value or {}).items():
            by_key[str(key)].append(diagnostics.get("metrics") or {})
            row_counts[str(key)] += int(diagnostics.get("row_count") or 0)
    return {
        key: {
            "row_count": row_counts.get(key, 0),
            "metrics": average_metric_dicts(metrics),
        }
        for key, metrics in sorted(by_key.items())
    }


def assign_date_local_model_ranks(
    rows: Sequence[dict[str, Any]],
    *,
    model_names: Sequence[str],
) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows]
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in output:
        grouped[(int(row.get("fold") or 0), str(row.get("date") or ""))].append(row)

    for _key, day_rows in sorted(grouped.items()):
        for model_name in model_names:
            score_column = f"{model_name}_score"
            rank_column = f"{model_name}_rank"
            ordered = sorted(
                day_rows,
                key=lambda row: (-(as_float(row.get(score_column)) or 0.0), str(row.get("code") or "")),
            )
            for index, row in enumerate(ordered, start=1):
                row[rank_column] = index
    return sorted(output, key=lambda row: (int(row.get("fold") or 0), str(row.get("date") or ""), str(row.get("code") or "")))


def score_median_risk_demote(
    rows: Sequence[dict[str, Any]],
    *,
    primary: str,
    risk: str,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows]
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in output:
        grouped[(int(row.get("fold") or 0), str(row.get("date") or ""))].append(row)

    for _key, day_rows in sorted(grouped.items()):
        median_rank = (len(day_rows) + 1) / 2.0
        demotion = float(len(day_rows))
        for row in day_rows:
            primary_rank = int(row.get(f"{primary}_rank") or 0)
            risk_rank = int(row.get(f"{risk}_rank") or 0)
            score = -float(primary_rank)
            if primary_rank and primary_rank <= top_n and risk_rank > median_rank:
                score -= demotion
            row["model_score"] = score
    return output


def score_combined_alpha(
    rows: Sequence[dict[str, Any]],
    *,
    primary: str,
    risk: str,
    alpha: float,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["model_score"] = (as_float(row.get(f"{primary}_score")) or 0.0) + alpha * (
            as_float(row.get(f"{risk}_score")) or 0.0
        )
        scored.append(item)
    return scored


def score_env_switch(
    rows: Sequence[dict[str, Any]],
    *,
    strong_model: str,
    fallback_model: str,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        model_name = strong_model if str(row.get("env") or "").lower() == "strong" else fallback_model
        item["model_score"] = as_float(row.get(f"{model_name}_score")) or 0.0
        scored.append(item)
    return scored


def score_env_three_way(
    rows: Sequence[dict[str, Any]],
    *,
    strong_model: str,
    weak_model: str,
    neutral_model: str,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        env = str(row.get("env") or "").lower()
        if env == "strong":
            model_name = strong_model
        elif env == "weak":
            model_name = weak_model
        else:
            model_name = neutral_model
        item["model_score"] = as_float(row.get(f"{model_name}_score")) or 0.0
        scored.append(item)
    return scored


def score_single_model(rows: Sequence[dict[str, Any]], *, model_name: str) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["model_score"] = as_float(row.get(f"{model_name}_score")) or 0.0
        scored.append(item)
    return scored


def summarize_scored_folds(rows: Sequence[dict[str, Any]], *, top_n: int = 3) -> dict[str, Any]:
    fold_reports = []
    for fold, fold_rows in sorted(rows_by_fold(rows).items()):
        if not fold_rows:
            continue
        fold_reports.append(
            {
                "fold": fold,
                "row_count": len(fold_rows),
                "date_count": len({str(row.get("date") or "") for row in fold_rows}),
                "test_start_date": min(str(row.get("date") or "") for row in fold_rows),
                "test_end_date": max(str(row.get("date") or "") for row in fold_rows),
                "metrics": evaluate_model(fold_rows, top_n=top_n),
                "by_env": partition_diagnostics_for_top_n(fold_rows, partition="env", top_n=top_n),
                "by_month": partition_diagnostics_for_top_n(fold_rows, partition="month", top_n=top_n),
            }
        )
    return {
        "fold_count": len(fold_reports),
        "row_count": len(rows),
        "date_count_with_fold_duplicates": sum(fold["date_count"] for fold in fold_reports),
        "metrics": average_metric_dicts([fold["metrics"] for fold in fold_reports]),
        "by_env": average_partition_metrics([fold["by_env"] for fold in fold_reports]),
        "by_month": average_partition_metrics([fold["by_month"] for fold in fold_reports]),
        "folds": fold_reports,
    }


def load_trial_model_config(
    name: str,
    trial_dir: Path,
    *,
    rows: Sequence[dict[str, Any]],
    method: str,
) -> TrialModelConfig:
    reports = sorted(trial_dir.glob("lgbm_rank_report*.json"))
    if not reports:
        raise FileNotFoundError(f"no lgbm_rank_report*.json under {trial_dir}")
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    params = report.get("model_params") or {}
    feature_manifest = trial_dir / "feature_manifest.json"
    numeric_columns, categorical_columns, fixed_levels = load_feature_manifest_with_levels(
        feature_manifest,
        available_columns=set(rows[0].keys()),
        method=method,
    )
    categorical_encoding = str(
        report.get("categorical_encoding")
        or load_feature_manifest_encoding(feature_manifest)
        or DEFAULT_CATEGORICAL_ENCODING
    )
    return TrialModelConfig(
        name=name,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        fixed_categorical_levels=fixed_levels,
        categorical_encoding=categorical_encoding,
        label_column=str(report.get("label_column") or "rank_label_3d"),
        model_params={
            "num_leaves": int(params.get("num_leaves", 9)),
            "min_data_in_leaf": int(params.get("min_data_in_leaf", 120)),
            "num_boost_round": int(params.get("num_boost_round", 60)),
            "learning_rate": float(params.get("learning_rate", 0.05)),
            "num_threads": int(params.get("num_threads", 0)),
            "label_gain": list(params.get("label_gain") or DEFAULT_LABEL_GAIN),
            "lambdarank_truncation_level": int(params.get("lambdarank_truncation_level", 0)),
        },
        trial_dir=str(trial_dir),
    )


def rolling_oof_predictions(
    rows: Sequence[dict[str, Any]],
    configs: Sequence[TrialModelConfig],
    *,
    rolling_train_dates: int,
    rolling_test_dates: int,
    rolling_folds: int,
) -> list[dict[str, Any]]:
    if not rows:
        raise ValueError("dataset is empty")
    if not configs:
        raise ValueError("at least one trial config is required")
    splits = rolling_walk_forward_splits(
        [str(row.get("date") or "") for row in rows],
        train_date_count=rolling_train_dates,
        test_date_count=rolling_test_dates,
        fold_count=rolling_folds,
    )
    output_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}
    model_names = [config.name for config in configs]

    for fold_index, (train_dates, test_dates) in enumerate(splits, start=1):
        for config in configs:
            train_rows = rows_for_dates(rows, set(train_dates), label_column=config.label_column)
            test_rows = rows_for_dates(rows, set(test_dates), label_column=config.label_column)
            if not train_rows or not test_rows:
                continue
            result = train_model_result(
                train_rows,
                test_rows,
                numeric_columns=config.numeric_columns,
                categorical_columns=config.categorical_columns,
                num_leaves=int(config.model_params["num_leaves"]),
                min_data_in_leaf=int(config.model_params["min_data_in_leaf"]),
                num_boost_round=int(config.model_params["num_boost_round"]),
                learning_rate=float(config.model_params["learning_rate"]),
                label_column=config.label_column,
                num_threads=int(config.model_params["num_threads"]),
                label_gain=list(config.model_params["label_gain"]),
                lambdarank_truncation_level=int(config.model_params["lambdarank_truncation_level"]),
                fixed_categorical_levels=config.fixed_categorical_levels,
                categorical_encoding=config.categorical_encoding,
            )
            for row in result.test_scored:
                key = (fold_index, str(row.get("date") or ""), str(row.get("code") or ""))
                if key not in output_by_key:
                    item = dict(row)
                    item["fold"] = fold_index
                    item["train_start_date"] = train_dates[0]
                    item["train_end_date"] = train_dates[-1]
                    item["test_start_date"] = test_dates[0]
                    item["test_end_date"] = test_dates[-1]
                    output_by_key[key] = item
                output_by_key[key][f"{config.name}_score"] = float(row.get("model_score") or 0.0)

    predictions = list(output_by_key.values())
    missing = [
        (row.get("fold"), row.get("date"), row.get("code"), name)
        for row in predictions
        for name in model_names
        if f"{name}_score" not in row
    ]
    if missing:
        fold, date, code, name = missing[0]
        raise ValueError(f"missing OOF score for model={name} fold={fold} date={date} code={code}")
    return assign_date_local_model_ranks(predictions, model_names=model_names)


def evaluate_rerank_rules(
    predictions: Sequence[dict[str, Any]],
    *,
    primary_models: Sequence[str],
    risk_model: str,
    alphas: Sequence[float],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for model_name in primary_models:
        results.append(
            {
                "rule": f"single-{model_name}",
                "description": f"{model_name} OOF baseline",
                **summarize_scored_folds(score_single_model(predictions, model_name=model_name), top_n=top_n),
            }
        )
    if risk_model not in primary_models:
        results.append(
            {
                "rule": f"single-{risk_model}",
                "description": f"{risk_model} OOF risk-filter baseline",
                **summarize_scored_folds(score_single_model(predictions, model_name=risk_model), top_n=top_n),
            }
        )
    for primary in primary_models:
        results.append(
            {
                "rule": f"{primary}-median-risk-demote-{risk_model}",
                "description": f"{primary} rank, demote primary top{top_n} rows when {risk_model} rank is worse than same-day median",
                **summarize_scored_folds(
                    score_median_risk_demote(predictions, primary=primary, risk=risk_model, top_n=top_n),
                    top_n=top_n,
                ),
            }
        )
        for alpha in alphas:
            results.append(
                {
                    "rule": f"{primary}-plus-{alpha:g}-{risk_model}",
                    "description": f"{primary}_score + {alpha:g} * {risk_model}_score",
                    **summarize_scored_folds(
                        score_combined_alpha(predictions, primary=primary, risk=risk_model, alpha=alpha),
                        top_n=top_n,
                    ),
                }
            )
    if "sw4" in primary_models:
        for fallback in [risk_model, *[name for name in primary_models if name != "sw4"]]:
            results.append(
                {
                    "rule": f"env-strong-sw4-else-{fallback}",
                    "description": f"strong uses sw4; weak/neutral use {fallback}",
                    **summarize_scored_folds(
                        score_env_switch(predictions, strong_model="sw4", fallback_model=fallback),
                        top_n=top_n,
                    ),
                }
            )
        if "sw5" in primary_models and risk_model in {"rf", *primary_models}:
            results.append(
                {
                    "rule": f"env-strong-sw4-weak-sw5-neutral-{risk_model}",
                    "description": f"strong uses sw4; weak uses sw5; neutral/unknown use {risk_model}",
                    **summarize_scored_folds(
                        score_env_three_way(
                            predictions,
                            strong_model="sw4",
                            weak_model="sw5",
                            neutral_model=risk_model,
                        ),
                        top_n=top_n,
                    ),
                }
            )
    return results


def write_oof_predictions_csv(rows: Sequence[dict[str, Any]], path: Path, *, model_names: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base_columns = [
        "fold",
        "train_start_date",
        "train_end_date",
        "test_start_date",
        "test_end_date",
        "date",
        "code",
        "name",
        "env",
        "ret3",
        "ret5",
        "rank_label_3d",
        "rank_label_5d",
    ]
    columns = [column for column in base_columns if any(column in row for row in rows)]
    for model_name in model_names:
        columns.extend([f"{model_name}_score", f"{model_name}_rank"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def markdown_report(report: dict[str, Any]) -> str:
    metric_names = [
        "top3_ret3_positive_rate",
        "top3_ret3_ge_5_rate",
        "top3_ret3_le_0_rate",
        "rank_ic_ret3",
        "top3_ret5_positive_rate",
        "top3_ret5_ge_5_rate",
        "top3_ret5_le_0_rate",
        "rank_ic_ret5",
    ]
    lines = [
        "# B3 controlled rerank diagnostics",
        "",
        f"dataset: `{report.get('dataset')}`",
        f"oof predictions: `{report.get('outputs', {}).get('oof_predictions_csv')}`",
        "",
        "## results",
        "",
        "| rule | ret3 pos | ret3 >=5 | ret3 <=0 | IC3 | ret5 pos | ret5 >=5 | ret5 <=0 | IC5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report.get("results") or []:
        metrics = result.get("metrics") or {}
        values = [metrics.get(name) for name in metric_names]
        lines.append("| {rule} | {values} |".format(rule=result.get("rule"), values=" | ".join(str(value) for value in values)))

    for section, title in [("by_env", "by env"), ("by_month", "by month")]:
        lines.extend(["", f"## {title}", ""])
        for result in report.get("results") or []:
            lines.extend(["", f"### {result.get('rule')}", ""])
            lines.append("| key | rows | ret3 pos | ret3 >=5 | ret3 <=0 | IC3 | ret5 pos | ret5 >=5 | ret5 <=0 | IC5 |")
            lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for key, diagnostics in sorted((result.get(section) or {}).items()):
                metrics = diagnostics.get("metrics") or {}
                values = [metrics.get(name) for name in metric_names]
                lines.append(
                    "| {key} | {rows} | {values} |".format(
                        key=key,
                        rows=diagnostics.get("row_count"),
                        values=" | ".join(str(value) for value in values),
                    )
                )
    return "\n".join(lines) + "\n"


def parse_model_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("model spec must use name=trial_dir")
    name, raw_path = value.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("model name cannot be empty")
    return name, Path(raw_path)


def evaluate_controlled_rerank(
    *,
    dataset: Path,
    model_specs: Sequence[tuple[str, Path]],
    method: str,
    risk_model: str,
    primary_models: Sequence[str],
    alphas: Sequence[float],
    rolling_train_dates: int,
    rolling_test_dates: int,
    rolling_folds: int,
    top_n: int,
) -> dict[str, Any]:
    rows = read_dataset(dataset)
    if not rows:
        raise ValueError("dataset is empty")
    configs = [
        load_trial_model_config(name, trial_dir, rows=rows, method=method)
        for name, trial_dir in model_specs
    ]
    predictions = rolling_oof_predictions(
        rows,
        configs,
        rolling_train_dates=rolling_train_dates,
        rolling_test_dates=rolling_test_dates,
        rolling_folds=rolling_folds,
    )
    model_names = [config.name for config in configs]
    missing_primary = [name for name in primary_models if name not in model_names]
    if missing_primary:
        raise ValueError(f"primary model not loaded: {', '.join(missing_primary)}")
    if risk_model not in model_names:
        raise ValueError(f"risk model not loaded: {risk_model}")
    return {
        "dataset": str(dataset),
        "method": method,
        "row_count": len(rows),
        "date_count": len({str(row.get("date") or "") for row in rows}),
        "rolling": {
            "train_date_count": rolling_train_dates,
            "test_date_count": rolling_test_dates,
            "fold_count": rolling_folds,
        },
        "top_n": top_n,
        "models": {
            config.name: {
                "trial_dir": config.trial_dir,
                "label_column": config.label_column,
                "feature_count": len(config.numeric_columns) + len(config.categorical_columns),
                "numeric_feature_count": len(config.numeric_columns),
                "categorical_feature_count": len(config.categorical_columns),
                "categorical_encoding": config.categorical_encoding,
                "model_params": config.model_params,
            }
            for config in configs
        },
        "model_names": model_names,
        "oof_prediction_count": len(predictions),
        "oof_predictions": predictions,
        "results": evaluate_rerank_rules(
            predictions,
            primary_models=primary_models,
            risk_model=risk_model,
            alphas=alphas,
            top_n=top_n,
        ),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate B3 controlled rolling OOF rerank/risk-filter diagnostics.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", action="append", type=parse_model_spec, required=True)
    parser.add_argument("--primary-model", action="append", required=True)
    parser.add_argument("--risk-model", required=True)
    parser.add_argument("--alpha", action="append", type=float, default=None)
    parser.add_argument("--rolling-folds", type=int, default=5)
    parser.add_argument("--rolling-train-dates", type=int, default=160)
    parser.add_argument("--rolling-test-dates", type=int, default=16)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report = evaluate_controlled_rerank(
        dataset=args.dataset,
        model_specs=args.model,
        method=args.method,
        risk_model=args.risk_model,
        primary_models=args.primary_model,
        alphas=args.alpha or DEFAULT_ALPHAS,
        rolling_train_dates=args.rolling_train_dates,
        rolling_test_dates=args.rolling_test_dates,
        rolling_folds=args.rolling_folds,
        top_n=args.top_n,
    )
    model_names = list(report["model_names"])
    predictions = list(report.pop("oof_predictions"))
    oof_csv = output_dir / "rolling_oof_predictions.csv"
    report_json = output_dir / "rerank_report.json"
    report_md = output_dir / "rerank_report.md"
    write_oof_predictions_csv(predictions, oof_csv, model_names=model_names)
    report["outputs"] = {
        "oof_predictions_csv": str(oof_csv),
        "report_json": str(report_json),
        "report_md": str(report_md),
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"outputs": report["outputs"], "results": report["results"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
