from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .configs import training_kwargs_from_trial
from .objectives import score_trial_report
from ml.training import train_lgbm_rank


def require_optuna() -> Any:
    try:
        import optuna
    except ImportError as exc:
        raise RuntimeError("Optuna is required for --strategy optuna") from exc
    if optuna is None:
        raise RuntimeError("Optuna is required for --strategy optuna")
    return optuna


def suggest_trial_params(trial: Any) -> dict[str, Any]:
    params = {
        "feature_set": trial.suggest_categorical(
            "feature_set",
            ["raw_numeric", "raw_plus_signal", "raw_plus_signal_macd"],
        ),
        "label_column": trial.suggest_categorical("label_column", ["rank_label_3d", "rank_label_5d"]),
        "categorical_encoding": trial.suggest_categorical("categorical_encoding", ["one_hot", "native"]),
        "boosting_type": trial.suggest_categorical("boosting_type", ["gbdt", "dart"]),
        "num_leaves": trial.suggest_categorical("num_leaves", [5, 9, 15]),
        "min_data_in_leaf": trial.suggest_categorical("min_data_in_leaf", [30, 60, 120, 240]),
        "num_boost_round": trial.suggest_categorical("num_boost_round", [40, 60, 80, 120, 160]),
        "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.08, log=True),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.65, 1.0),
        "bagging_freq": trial.suggest_categorical("bagging_freq", [0, 1, 3, 5]),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.65, 1.0),
        "lambda_l1": trial.suggest_float("lambda_l1", 0.0, 2.0),
        "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 3.0),
        "min_gain_to_split": trial.suggest_float("min_gain_to_split", 0.0, 0.1),
        "early_stopping_rounds": trial.suggest_categorical("early_stopping_rounds", [0, 10, 20, 40]),
        "lambdarank_truncation_level": trial.suggest_categorical(
            "lambdarank_truncation_level",
            [0, 5, 8, 10, 20],
        ),
        "top_k": [3, 5, 10, 20],
        "eval_at": [5, 10, 20],
    }
    if params["boosting_type"] == "dart":
        params["early_stopping_rounds"] = 0
    return params


def trial_output_dir(output_root: Path, trial_number: int) -> Path:
    return output_root / f"optuna-trial-{trial_number + 1:03d}"


def first_report_path(output_dir: Path) -> Path | None:
    reports = sorted(output_dir.glob("lgbm_rank_report*.json"))
    return reports[0] if reports else None


def trial_summary(
    *,
    trial_number: int,
    output_dir: Path,
    score: float,
    params: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    report_path = first_report_path(output_dir)
    metrics = report.get("metrics") or {}
    rolling_summary = report.get("rolling_summary") or {}
    summary: dict[str, Any] = {
        "trial": trial_number,
        "output_dir": str(output_dir),
        "report_path": str(report_path) if report_path is not None else None,
        "score": score,
        "params": params,
        "metrics": {"test": metrics.get("test") or {}},
        "rolling_summary": {"test_avg": rolling_summary.get("test_avg") or {}},
        "model_params": report.get("model_params") or {},
    }
    if "model_artifacts" in report:
        summary["model_artifacts"] = report["model_artifacts"]
    return summary


def best_trial_summary(trials: list[dict[str, Any]], best_number: int | None) -> dict[str, Any] | None:
    if best_number is None:
        return None
    for trial in trials:
        if trial.get("trial") == best_number:
            return trial
    return None


def optuna_visualization_module(optuna: Any) -> Any:
    visualization = getattr(optuna, "visualization", None)
    if visualization is not None:
        return visualization
    try:
        import importlib

        return importlib.import_module("optuna.visualization")
    except ImportError as exc:
        raise RuntimeError("Optuna visualization requires plotly. Install with: pip install 'stock-select-ml[tuning]'") from exc
    except Exception as exc:
        raise RuntimeError(f"Optuna visualization import failed: {type(exc).__name__}: {exc}") from exc


def study_parameter_count(study: Any) -> int:
    names: set[str] = set()
    for trial in getattr(study, "trials", []) or []:
        names.update((getattr(trial, "params", None) or {}).keys())
    return len(names)


def write_plot_html(figure: Any, path: Path) -> None:
    write_html = getattr(figure, "write_html", None)
    if write_html is None:
        raise RuntimeError("Optuna visualization did not return a Plotly figure with write_html")
    write_html(str(path))


def write_optuna_visualizations(
    *,
    optuna: Any,
    study: Any,
    tuning_summary: dict[str, Any],
    output_dir: Path,
    visual_format: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "visualizations_summary.json"
    visual_summary: dict[str, Any] = {
        "format": visual_format,
        "output_dir": str(output_dir),
        "trial_count": len(getattr(study, "trials", []) or []),
        "best_trial": tuning_summary.get("best_trial"),
        "best_value": tuning_summary.get("best_score"),
        "target_metric": "score_trial_report",
        "files": [],
        "warnings": [],
    }

    def add_warning(message: str) -> None:
        visual_summary["warnings"].append(message)
        print(f"warning: {message}")

    if visual_format != "html":
        add_warning(f"unsupported visualization format: {visual_format}")
    else:
        try:
            visualization = optuna_visualization_module(optuna)
        except RuntimeError as exc:
            add_warning(str(exc))
        else:
            plots = [
                ("optimization_history", "optimization_history.html", "plot_optimization_history"),
                ("param_importances", "param_importances.html", "plot_param_importances"),
                ("slice", "slice.html", "plot_slice"),
            ]
            if study_parameter_count(study) >= 2:
                plots.append(("parallel_coordinate", "parallel_coordinate.html", "plot_parallel_coordinate"))

            for name, filename, function_name in plots:
                path = output_dir / filename
                try:
                    plot_function = getattr(visualization, function_name)
                    figure = plot_function(study)
                    write_plot_html(figure, path)
                except Exception as exc:
                    add_warning(f"{filename} generation failed: {exc}")
                else:
                    visual_summary["files"].append({"name": name, "path": str(path)})

    summary_path.write_text(json.dumps(visual_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def add_summary_warning(summary: dict[str, Any], message: str) -> None:
    summary.setdefault("warnings", []).append(message)
    print(f"warning: {message}")


def run_optuna_study(args: argparse.Namespace, optuna: Any) -> dict[str, Any]:
    output_root = args.output_root or Path("diagnostics") / "ml" / args.method / "tuning"
    dataset = train_lgbm_rank.resolve_dataset_path(args.dataset, method=args.method)
    trials: list[dict[str, Any]] = []

    def objective(trial: Any) -> float:
        params = suggest_trial_params(trial)
        output_dir = trial_output_dir(output_root, int(trial.number))
        kwargs = training_kwargs_from_trial(params)
        kwargs.setdefault("seed", args.seed)
        report = train_lgbm_rank.train_and_report(
            dataset,
            output_dir,
            test_ratio=args.test_ratio,
            rolling_folds=args.rolling_folds,
            rolling_train_dates=args.rolling_train_dates,
            rolling_test_dates=args.rolling_test_dates,
            method=args.method,
            rf_diagnostics=not args.skip_rf_diagnostics,
            **kwargs,
        )
        score = score_trial_report(report)
        summary = trial_summary(
            trial_number=int(trial.number) + 1,
            output_dir=output_dir,
            score=score,
            params=params,
            report=report,
        )
        if hasattr(trial, "set_user_attr"):
            trial.set_user_attr("output_dir", str(output_dir))
            trial.set_user_attr("report_path", summary["report_path"])
            trial.set_user_attr("score", score)
        trials.append(summary)
        return score

    sampler = optuna.samplers.TPESampler(seed=args.seed)
    direction = "maximize"
    study = optuna.create_study(direction=direction, sampler=sampler)
    study.optimize(objective, n_trials=args.max_trials)
    best_trial = getattr(study, "best_trial", None)
    best_number = int(getattr(best_trial, "number", 0)) + 1 if best_trial is not None else None
    best_value = getattr(study, "best_value", None)
    best_summary = best_trial_summary(trials, best_number)
    best_params = (best_summary or {}).get("params") or getattr(study, "best_params", None) or (getattr(best_trial, "params", {}) if best_trial is not None else {})
    summary = {
        "strategy": "optuna",
        "method": args.method,
        "dataset": str(dataset),
        "output_root": str(output_root),
        "seed": args.seed,
        "optuna_version": getattr(optuna, "__version__", None),
        "sampler": "TPESampler",
        "study_name": getattr(study, "study_name", None),
        "direction": direction,
        "best_trial": best_number,
        "best_score": best_value,
        "best_params": best_params,
        "best_output_dir": (best_summary or {}).get("output_dir"),
        "best_report_path": (best_summary or {}).get("report_path"),
        "trials": trials,
    }
    if getattr(args, "visualize", False):
        visual_output_dir = args.visual_output_dir or output_root / "visualizations"
        try:
            visual_summary_path = write_optuna_visualizations(
                optuna=optuna,
                study=study,
                tuning_summary=summary,
                output_dir=visual_output_dir,
                visual_format=args.visual_format,
            )
        except Exception as exc:
            add_summary_warning(summary, f"visualization output failed for {visual_output_dir}: {type(exc).__name__}: {exc}")
        else:
            summary["visualizations_summary_path"] = str(visual_summary_path)
    return summary


def run_optuna_search(args: argparse.Namespace) -> int:
    try:
        optuna = require_optuna()
    except RuntimeError as exc:
        print(f"错误: {exc}. Install with: pip install 'stock-select-ml[tuning]'", file=sys.stderr)
        return 2
    summary = run_optuna_study(args, optuna)
    output_root = Path(summary["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "tuning_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote tuning summary to {summary_path}")
    return 0
