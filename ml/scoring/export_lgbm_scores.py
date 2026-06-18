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
from pathlib import Path
from typing import Any, Sequence

from ml.paths import PROJECT_ROOT
from ml.training.artifacts import build_model_metadata, write_model_artifacts as persist_model_artifacts
from ml.training.evaluation import grouped_by_date
from ml.training.features import (
    CATEGORICAL_ENCODINGS,
    DEFAULT_CATEGORICAL_ENCODING,
    load_feature_manifest_encoding,
    load_feature_manifest_with_levels,
)
from ml.training.labels import as_float, rows_for_dates
from ml.training.lgbm_ranker import DEFAULT_LABEL_GAIN, train_model_result
from ml.training.train_lgbm_rank import parse_label_gain, read_dataset
from ml.training.trial_params import LIGHTGBM_RANKING_DEFAULTS, trial_report_defaults


DEFAULT_METHOD = "b2"

EXPORT_COLUMNS = [
    "date",
    "code",
    "model_score",
    "model_rank",
]


def resolve_default_paths(method: str, *, model_output_dir: Path | None = None) -> dict[str, Path]:
    root = PROJECT_ROOT / "diagnostics" / "ml" / method
    if model_output_dir is not None:
        if not model_output_dir.is_absolute():
            root = Path("diagnostics") / "ml" / method
        return {
            "dataset": root / "rank_dataset.csv",
            "feature_manifest": model_output_dir / "feature_manifest.json",
            "output": model_output_dir / "lgbm_scores.csv",
            "summary_output": model_output_dir / "lgbm_scores_summary.json",
            "model_output_dir": model_output_dir,
        }
    return {
        "dataset": root / "rank_dataset.csv",
        "feature_manifest": root / "model" / "feature_manifest.json",
        "output": root / "lgbm_scores.csv",
        "summary_output": root / "lgbm_scores_summary.json",
        "model_output_dir": root / "model",
    }


def assign_model_ranks(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for _date, day_rows in sorted(grouped_by_date(rows).items()):
        ordered = sorted(day_rows, key=lambda row: (-(as_float(row.get("model_score")) or 0.0), str(row.get("code"))))
        for rank, row in enumerate(ordered, start=1):
            item = dict(row)
            item["model_rank"] = rank
            output.append(item)
    return output


def export_rows(scored_rows: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    ranked = assign_model_ranks(scored_rows)
    return [
        {
            "date": str(row.get("date") or ""),
            "code": str(row.get("code") or ""),
            "model_score": f"{float(row.get('model_score') or 0.0):.10f}",
            "model_rank": str(int(row.get("model_rank") or 0)),
        }
        for row in ranked
    ]


def write_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def score_rows_for_dates(rows: Sequence[dict[str, Any]], dates: set[str]) -> list[dict[str, Any]]:
    return sorted(
        [row for row in rows if str(row.get("date")) in dates],
        key=lambda row: (str(row.get("date")), str(row.get("code"))),
    )


def load_trial_feature_selection(model_output_dir: Path) -> dict[str, Any] | None:
    reports = sorted(model_output_dir.glob("lgbm_rank_report*.json"))
    for report in reports:
        payload = json.loads(report.read_text(encoding="utf-8"))
        feature_selection = payload.get("feature_selection")
        if isinstance(feature_selection, dict):
            return feature_selection
    return None


def export_scores(
    *,
    dataset: Path,
    feature_manifest: Path,
    output: Path,
    summary_output: Path,
    model_output_dir: Path,
    train_end_exclusive: str,
    score_start: str,
    score_end: str,
    num_leaves: int,
    min_data_in_leaf: int,
    num_boost_round: int,
    learning_rate: float,
    num_threads: int,
    label_gain: Sequence[int] | None = None,
    lambdarank_truncation_level: int = 0,
    boosting_type: str = "gbdt",
    bagging_fraction: float = 1.0,
    bagging_freq: int = 0,
    feature_fraction: float = 1.0,
    lambda_l1: float = 0.0,
    lambda_l2: float = 0.0,
    min_gain_to_split: float = 0.0,
    eval_at: Sequence[int] | None = None,
    early_stopping_rounds: int = 0,
    seed: int = 17,
    label_column: str = "rank_label_3d",
    method: str = DEFAULT_METHOD,
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
    write_model_artifacts: bool = False,
) -> dict[str, Any]:
    if categorical_encoding not in CATEGORICAL_ENCODINGS:
        raise ValueError(f"unsupported categorical_encoding: {categorical_encoding}")
    rows = read_dataset(dataset)
    if not rows:
        raise ValueError("dataset is empty")
    dates = sorted({str(row.get("date")) for row in rows})
    train_dates = {date for date in dates if date < train_end_exclusive}
    score_dates = {date for date in dates if score_start <= date <= score_end}
    train_rows = rows_for_dates(rows, train_dates, label_column=label_column)
    score_rows = score_rows_for_dates(rows, score_dates)
    if not train_rows:
        raise ValueError("no train rows after applying train date filter")
    if not score_rows:
        raise ValueError("no score rows after applying score date filter")
    resolved_label_gain = list(label_gain or DEFAULT_LABEL_GAIN)
    resolved_eval_at = [int(value) for value in (eval_at or LIGHTGBM_RANKING_DEFAULTS["eval_at"])]

    numeric_columns, categorical_columns, fixed_categorical_levels = load_feature_manifest_with_levels(
        feature_manifest,
        available_columns=set(rows[0].keys()),
        method=method,
    )
    model_result = train_model_result(
        train_rows,
        score_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        num_leaves=num_leaves,
        min_data_in_leaf=min_data_in_leaf,
        num_boost_round=num_boost_round,
        learning_rate=learning_rate,
        label_column=label_column,
        num_threads=num_threads,
        label_gain=resolved_label_gain,
        lambdarank_truncation_level=lambdarank_truncation_level,
        boosting_type=boosting_type,
        bagging_fraction=bagging_fraction,
        bagging_freq=bagging_freq,
        feature_fraction=feature_fraction,
        lambda_l1=lambda_l1,
        lambda_l2=lambda_l2,
        min_gain_to_split=min_gain_to_split,
        eval_at=resolved_eval_at,
        early_stopping_rounds=early_stopping_rounds,
        seed=seed,
        fixed_categorical_levels=fixed_categorical_levels,
        categorical_encoding=categorical_encoding,
    )
    score_scored = model_result.test_scored

    csv_rows = export_rows(score_scored)
    write_csv(output, csv_rows)
    model_params = {
        "boosting_type": boosting_type,
        "num_leaves": num_leaves,
        "min_data_in_leaf": min_data_in_leaf,
        "num_boost_round": num_boost_round,
        "learning_rate": learning_rate,
        "bagging_fraction": bagging_fraction,
        "bagging_freq": bagging_freq,
        "feature_fraction": feature_fraction,
        "lambda_l1": lambda_l1,
        "lambda_l2": lambda_l2,
        "min_gain_to_split": min_gain_to_split,
        "num_threads": num_threads,
        "label_gain": resolved_label_gain,
        "lambdarank_truncation_level": lambdarank_truncation_level,
        "eval_at": resolved_eval_at,
        "early_stopping_rounds": early_stopping_rounds,
        "seed": seed,
    }
    metadata = build_model_metadata(
        feature_manifest=str(feature_manifest),
        train_rows=train_rows,
        score_rows=score_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=model_result.category_levels,
        feature_names=model_result.feature_names,
        lightgbm_feature_names=model_result.lightgbm_feature_names,
        label_column=label_column,
        model_params=model_params,
        feature_selection=load_trial_feature_selection(model_output_dir),
        categorical_encoding=categorical_encoding,
        categorical_code_maps=model_result.categorical_code_maps,
    )
    model_artifacts = {
        "model": str(model_output_dir / "model.txt"),
        "metadata": str(model_output_dir / "model_metadata.json"),
    }
    if write_model_artifacts:
        model_artifacts = persist_model_artifacts(model_result.model, metadata, model_output_dir)
    summary = {
        "dataset": str(dataset),
        "feature_manifest": str(feature_manifest),
        "output": str(output),
        "model_artifacts": model_artifacts,
        "train_end_exclusive": train_end_exclusive,
        "score_start": score_start,
        "score_end": score_end,
        "scored_start": min(row["date"] for row in csv_rows),
        "scored_end": max(row["date"] for row in csv_rows),
        "train_date_count": len({row["date"] for row in train_rows}),
        "train_row_count": len(train_rows),
        "score_date_count": len({row["date"] for row in score_rows}),
        "score_row_count": len(score_rows),
        "feature_count": model_result.feature_count,
        "categorical_encoding": categorical_encoding,
        "model_params": model_params,
        "top_features": model_result.top_features[:20],
        "columns": EXPORT_COLUMNS,
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def load_trial_report_defaults(model_output_dir: Path | None) -> dict[str, Any]:
    feature_manifest = model_output_dir / "feature_manifest.json" if model_output_dir is not None else None
    return trial_report_defaults(model_output_dir, feature_manifest=feature_manifest)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export LightGBM model scores for Rust ranking layer consumption.")
    add_parser_arguments(parser)
    return parser.parse_args(argv)


def add_parser_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--feature-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--model-output-dir", type=Path)
    parser.add_argument("--train-end-exclusive", default="2026-03-01")
    parser.add_argument("--score-start", default="2026-03-01")
    parser.add_argument("--score-end", default="2026-06-02")
    parser.add_argument("--num-leaves", type=int)
    parser.add_argument("--min-data-in-leaf", type=int)
    parser.add_argument("--num-boost-round", type=int)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--num-threads", type=int)
    parser.add_argument("--label-column")
    parser.add_argument("--label-gain", type=parse_label_gain)
    parser.add_argument("--lambdarank-truncation-level", type=int)
    parser.add_argument("--boosting-type", choices=["gbdt", "dart"])
    parser.add_argument("--bagging-fraction", type=float)
    parser.add_argument("--bagging-freq", type=int)
    parser.add_argument("--feature-fraction", type=float)
    parser.add_argument("--lambda-l1", type=float)
    parser.add_argument("--lambda-l2", type=float)
    parser.add_argument("--min-gain-to-split", type=float)
    parser.add_argument("--eval-at", type=parse_label_gain)
    parser.add_argument("--early-stopping-rounds", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--categorical-encoding", choices=sorted(CATEGORICAL_ENCODINGS))
    parser.add_argument("--write-model-artifacts", action="store_true", help="rewrite model.txt/model_metadata.json; default only exports scores and summary")


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("export-lgbm", description="Export LightGBM model scores for Rust ranking layer consumption.")
    add_parser_arguments(parser)
    parser.set_defaults(handler=main_from_args)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return main_from_args(parse_args(argv))


def main_from_args(args: argparse.Namespace) -> int:
    defaults = resolve_default_paths(args.method, model_output_dir=args.model_output_dir)
    report_defaults = load_trial_report_defaults(args.model_output_dir)
    feature_manifest = args.feature_manifest or defaults["feature_manifest"]
    categorical_encoding = (
        args.categorical_encoding
        or report_defaults.get("categorical_encoding")
        or load_feature_manifest_encoding(feature_manifest)
    )
    summary = export_scores(
        dataset=args.dataset or defaults["dataset"],
        feature_manifest=feature_manifest,
        output=args.output or defaults["output"],
        summary_output=args.summary_output or defaults["summary_output"],
        model_output_dir=defaults["model_output_dir"],
        train_end_exclusive=args.train_end_exclusive,
        score_start=args.score_start,
        score_end=args.score_end,
        num_leaves=args.num_leaves if args.num_leaves is not None else int(report_defaults.get("num_leaves", 9)),
        min_data_in_leaf=args.min_data_in_leaf if args.min_data_in_leaf is not None else int(report_defaults.get("min_data_in_leaf", 120)),
        num_boost_round=args.num_boost_round if args.num_boost_round is not None else int(report_defaults.get("num_boost_round", 60)),
        learning_rate=args.learning_rate if args.learning_rate is not None else float(report_defaults.get("learning_rate", 0.05)),
        num_threads=args.num_threads if args.num_threads is not None else int(report_defaults.get("num_threads", 4)),
        label_gain=args.label_gain if args.label_gain is not None else report_defaults.get("label_gain", DEFAULT_LABEL_GAIN),
        lambdarank_truncation_level=args.lambdarank_truncation_level if args.lambdarank_truncation_level is not None else int(report_defaults.get("lambdarank_truncation_level", 0)),
        boosting_type=args.boosting_type or str(report_defaults.get("boosting_type", LIGHTGBM_RANKING_DEFAULTS["boosting_type"])),
        bagging_fraction=args.bagging_fraction if args.bagging_fraction is not None else float(report_defaults.get("bagging_fraction", LIGHTGBM_RANKING_DEFAULTS["bagging_fraction"])),
        bagging_freq=args.bagging_freq if args.bagging_freq is not None else int(report_defaults.get("bagging_freq", LIGHTGBM_RANKING_DEFAULTS["bagging_freq"])),
        feature_fraction=args.feature_fraction if args.feature_fraction is not None else float(report_defaults.get("feature_fraction", LIGHTGBM_RANKING_DEFAULTS["feature_fraction"])),
        lambda_l1=args.lambda_l1 if args.lambda_l1 is not None else float(report_defaults.get("lambda_l1", LIGHTGBM_RANKING_DEFAULTS["lambda_l1"])),
        lambda_l2=args.lambda_l2 if args.lambda_l2 is not None else float(report_defaults.get("lambda_l2", LIGHTGBM_RANKING_DEFAULTS["lambda_l2"])),
        min_gain_to_split=args.min_gain_to_split if args.min_gain_to_split is not None else float(report_defaults.get("min_gain_to_split", LIGHTGBM_RANKING_DEFAULTS["min_gain_to_split"])),
        eval_at=args.eval_at if args.eval_at is not None else report_defaults.get("eval_at", LIGHTGBM_RANKING_DEFAULTS["eval_at"]),
        early_stopping_rounds=args.early_stopping_rounds if args.early_stopping_rounds is not None else int(report_defaults.get("early_stopping_rounds", LIGHTGBM_RANKING_DEFAULTS["early_stopping_rounds"])),
        seed=args.seed if args.seed is not None else int(report_defaults.get("seed", LIGHTGBM_RANKING_DEFAULTS["seed"])),
        label_column=args.label_column or str(report_defaults.get("label_column", "rank_label_3d")),
        method=args.method,
        categorical_encoding=str(categorical_encoding),
        write_model_artifacts=bool(args.write_model_artifacts),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
