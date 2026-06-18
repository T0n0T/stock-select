from __future__ import annotations

from pathlib import Path
from typing import Any

from .features import DEFAULT_METHOD


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# {report.get('method', DEFAULT_METHOD)} LightGBM rank report",
        "",
        f"dataset: `{report['dataset']}`",
        f"train dates: `{report['train_date_count']}`",
        f"test dates: `{report['test_date_count']}`",
        f"features: `{report['feature_count']}`",
        "",
        "| split | top3 positive | top3 >=5 | top3 <=0 | top3 >=5 capture | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split in ["train", "test"]:
        metrics = report["metrics"][split]
        lines.append(
            "| {split} | {pos} | {ge5} | {le0} | {capture_ret3} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                split=split,
                pos=metrics.get("top3_ret3_positive_rate"),
                ge5=metrics.get("top3_ret3_ge_5_rate"),
                le0=metrics.get("top3_ret3_le_0_rate"),
                capture_ret3=metrics.get("top3_ret3_ge_5_capture_rate"),
                ic_ret3=metrics.get("rank_ic_ret3"),
                ge5_ret5=metrics.get("top3_ret5_ge_5_rate"),
                ic_ret5=metrics.get("rank_ic_ret5"),
            )
        )
    lines.extend(["", "## top features", ""])
    lines.extend(f"- {item['feature']}: {item['importance']}" for item in report.get("top_features", [])[:20])
    rf_summary = report.get("rf_diagnostics") or {}
    if rf_summary:
        rf_metrics = ((rf_summary.get("metrics") or {}).get("test") or {})
        lines.extend(
            [
                "",
                "## random forest factor diagnostics",
                "",
                f"- status: {rf_summary.get('status')}",
                f"- oob_score: {rf_summary.get('oob_score')}",
                f"- test rank_ic_ret3: {rf_metrics.get('rank_ic_ret3')}",
                f"- low importance features: {rf_summary.get('low_importance_feature_count')}",
            ]
        )
        lines.extend(
            f"- {item['feature']}: {item['importance']}" for item in list(rf_summary.get("top_features") or [])[:20]
        )
    if report.get("rolling_folds"):
        summary = report.get("rolling_summary") or {}
        test_avg = summary.get("test_avg") or {}
        if test_avg:
            lines.extend(
                [
                    "",
                    "## rolling summary",
                    "",
                    "| scope | top3 positive | top3 >=5 | top3 <=0 | top3 >=5 capture | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|",
                    "| model avg | {pos} | {ge5} | {le0} | {capture} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                        pos=test_avg.get("top3_ret3_positive_rate"),
                        ge5=test_avg.get("top3_ret3_ge_5_rate"),
                        le0=test_avg.get("top3_ret3_le_0_rate"),
                        capture=test_avg.get("top3_ret3_ge_5_capture_rate"),
                        ic_ret3=test_avg.get("rank_ic_ret3"),
                        ge5_ret5=test_avg.get("top3_ret5_ge_5_rate"),
                        ic_ret5=test_avg.get("rank_ic_ret5"),
                    ),
                ]
            )
        lines.extend(["", "## rolling folds", ""])
        lines.extend(
            [
                "| fold | train dates | test dates | top3 positive | top3 >=5 | top3 <=0 | top3 >=5 capture | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |",
                "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for fold in report["rolling_folds"]:
            metrics = fold["metrics"]["test"]
            lines.append(
                "| {fold} | {train_start}..{train_end} | {test_start}..{test_end} | {pos} | {ge5} | {le0} | {capture} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                    fold=fold["fold"],
                    train_start=fold["train_start_date"],
                    train_end=fold["train_end_date"],
                    test_start=fold["test_start_date"],
                    test_end=fold["test_end_date"],
                    pos=metrics.get("top3_ret3_positive_rate"),
                    ge5=metrics.get("top3_ret3_ge_5_rate"),
                    le0=metrics.get("top3_ret3_le_0_rate"),
                    capture=metrics.get("top3_ret3_ge_5_capture_rate"),
                    ic_ret3=metrics.get("rank_ic_ret3"),
                    ge5_ret5=metrics.get("top3_ret5_ge_5_rate"),
                    ic_ret5=metrics.get("rank_ic_ret5"),
                )
            )
        if any(fold.get("by_env") for fold in report["rolling_folds"]):
            lines.extend(["", "### rolling fold by-env", "", "| fold | env | rows | top3 >=5 | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |", "|---|---:|---:|---:|---:|---:|---:|"])
            for fold in report["rolling_folds"]:
                for env, diag in sorted((fold.get("by_env") or {}).items()):
                    m = diag.get("metrics") or {}
                    lines.append(
                        "| {fold} | {env} | {rows} | {ge5} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                            fold=fold["fold"],
                            env=env,
                            rows=diag.get("row_count"),
                            ge5=m.get("top3_ret3_ge_5_rate"),
                            ic_ret3=m.get("rank_ic_ret3"),
                            ge5_ret5=m.get("top3_ret5_ge_5_rate"),
                            ic_ret5=m.get("rank_ic_ret5"),
                        )
                    )
        if any(fold.get("by_month") for fold in report["rolling_folds"]):
            lines.extend(["", "### rolling fold by-month", "", "| fold | month | rows | top3 >=5 | rank ic ret3 | top3 ret5 >=5 | rank ic ret5 |", "|---|---:|---:|---:|---:|---:|---:|"])
            for fold in report["rolling_folds"]:
                for month, diag in sorted((fold.get("by_month") or {}).items()):
                    m = diag.get("metrics") or {}
                    lines.append(
                        "| {fold} | {month} | {rows} | {ge5} | {ic_ret3} | {ge5_ret5} | {ic_ret5} |".format(
                            fold=fold["fold"],
                            month=month,
                            rows=diag.get("row_count"),
                            ge5=m.get("top3_ret3_ge_5_rate"),
                            ic_ret3=m.get("rank_ic_ret3"),
                            ge5_ret5=m.get("top3_ret5_ge_5_rate"),
                            ic_ret5=m.get("rank_ic_ret5"),
                        )
                    )
    return "\n".join(lines) + "\n"


def report_paths(
    output_dir: Path,
    feature_set: str,
    train_mode: str = "overall",
    label_column: str = "rank_label_3d",
) -> tuple[Path, Path]:
    suffix = "" if feature_set == "all" else f"_{feature_set}"
    if train_mode != "overall":
        suffix = f"{suffix}_{train_mode}"
    if label_column != "rank_label_3d":
        suffix = f"{suffix}_{label_column}"
    return output_dir / f"lgbm_rank_report{suffix}.json", output_dir / f"lgbm_rank_report{suffix}.md"
