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
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ml.train_rank_lgbm import (
    as_float,
    build_model_metadata,
    grouped_by_date,
    load_feature_manifest_with_levels,
    read_dataset,
    rows_for_dates,
    train_model_result,
    write_model_artifacts,
)


DEFAULT_METHOD = "b2"

EXPORT_COLUMNS = [
    "date",
    "code",
    "model_score",
    "model_rank",
]


def resolve_default_paths(method: str) -> dict[str, Path]:
    root = PROJECT_ROOT / "diagnostics" / "ml" / method
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
    label_column: str = "rank_label_3d",
    method: str = DEFAULT_METHOD,
) -> dict[str, Any]:
    rows = read_dataset(dataset)
    if not rows:
        raise ValueError("dataset is empty")
    dates = sorted({str(row.get("date")) for row in rows})
    train_dates = {date for date in dates if date < train_end_exclusive}
    score_dates = {date for date in dates if score_start <= date <= score_end}
    train_rows = rows_for_dates(rows, train_dates, label_column=label_column)
    score_rows = rows_for_dates(rows, score_dates, label_column=label_column)
    if not train_rows:
        raise ValueError("no train rows after applying train date filter")
    if not score_rows:
        raise ValueError("no score rows after applying score date filter")

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
        fixed_categorical_levels=fixed_categorical_levels,
    )
    score_scored = model_result.test_scored

    csv_rows = export_rows(score_scored)
    write_csv(output, csv_rows)
    model_params = {
        "num_leaves": num_leaves,
        "min_data_in_leaf": min_data_in_leaf,
        "num_boost_round": num_boost_round,
        "learning_rate": learning_rate,
        "num_threads": num_threads,
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
    )
    model_artifacts = write_model_artifacts(model_result.model, metadata, model_output_dir)
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
        "model_params": model_params,
        "top_features": model_result.top_features[:20],
        "columns": EXPORT_COLUMNS,
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export LightGBM model scores for Rust ranking layer consumption.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--feature-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--model-output-dir", type=Path)
    parser.add_argument("--train-end-exclusive", default="2026-03-01")
    parser.add_argument("--score-start", default="2026-03-01")
    parser.add_argument("--score-end", default="2026-06-02")
    parser.add_argument("--num-leaves", type=int, default=9)
    parser.add_argument("--min-data-in-leaf", type=int, default=120)
    parser.add_argument("--num-boost-round", type=int, default=60)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--num-threads", type=int, default=4)
    parser.add_argument("--label-column", default="rank_label_3d")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    defaults = resolve_default_paths(args.method)
    summary = export_scores(
        dataset=args.dataset or defaults["dataset"],
        feature_manifest=args.feature_manifest or defaults["feature_manifest"],
        output=args.output or defaults["output"],
        summary_output=args.summary_output or defaults["summary_output"],
        model_output_dir=args.model_output_dir or defaults["model_output_dir"],
        train_end_exclusive=args.train_end_exclusive,
        score_start=args.score_start,
        score_end=args.score_end,
        num_leaves=args.num_leaves,
        min_data_in_leaf=args.min_data_in_leaf,
        num_boost_round=args.num_boost_round,
        learning_rate=args.learning_rate,
        num_threads=args.num_threads,
        label_column=args.label_column,
        method=args.method,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
