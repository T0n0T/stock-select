from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .features import DEFAULT_CATEGORICAL_ENCODING, load_feature_manifest_encoding
from .lgbm_ranker import DEFAULT_LABEL_GAIN


LIGHTGBM_RANKING_DEFAULTS: dict[str, Any] = {
    "boosting_type": "gbdt",
    "num_leaves": 9,
    "min_data_in_leaf": 120,
    "num_boost_round": 60,
    "learning_rate": 0.05,
    "bagging_fraction": 1.0,
    "bagging_freq": 0,
    "feature_fraction": 1.0,
    "lambda_l1": 0.0,
    "lambda_l2": 0.0,
    "min_gain_to_split": 0.0,
    "num_threads": 4,
    "label_gain": DEFAULT_LABEL_GAIN,
    "lambdarank_truncation_level": 0,
    "eval_at": [5, 10, 20],
    "early_stopping_rounds": 0,
    "seed": 17,
}

_INT_KEYS = {
    "num_leaves",
    "min_data_in_leaf",
    "num_boost_round",
    "bagging_freq",
    "num_threads",
    "lambdarank_truncation_level",
    "early_stopping_rounds",
    "seed",
}
_FLOAT_KEYS = {
    "learning_rate",
    "bagging_fraction",
    "feature_fraction",
    "lambda_l1",
    "lambda_l2",
    "min_gain_to_split",
}
_LIST_INT_KEYS = {"label_gain", "eval_at"}


def first_lgbm_report(trial_dir: Path) -> dict[str, Any] | None:
    reports = sorted(trial_dir.glob("lgbm_rank_report*.json"))
    if not reports:
        return None
    return json.loads(reports[0].read_text(encoding="utf-8"))


def coerce_lightgbm_ranking_params(params: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in params.items():
        if key not in LIGHTGBM_RANKING_DEFAULTS and key != "categorical_encoding":
            continue
        if value is None:
            continue
        if key in _INT_KEYS:
            result[key] = int(value)
        elif key in _FLOAT_KEYS:
            result[key] = float(value)
        elif key in _LIST_INT_KEYS:
            result[key] = [int(item) for item in value]
        elif key == "categorical_encoding":
            result[key] = str(value)
        else:
            result[key] = value
    return result


def lightgbm_ranking_params_with_defaults(params: dict[str, Any] | None) -> dict[str, Any]:
    resolved = dict(LIGHTGBM_RANKING_DEFAULTS)
    resolved["label_gain"] = list(LIGHTGBM_RANKING_DEFAULTS["label_gain"])
    resolved["eval_at"] = list(LIGHTGBM_RANKING_DEFAULTS["eval_at"])
    if params:
        resolved.update(coerce_lightgbm_ranking_params(params))
    return resolved


def trial_report_defaults(trial_dir: Path | None, *, feature_manifest: Path | None = None) -> dict[str, Any]:
    if trial_dir is None:
        return {}
    payload = first_lgbm_report(trial_dir)
    if payload is None:
        return {}
    params = payload.get("model_params") or {}
    result = coerce_lightgbm_ranking_params(params)
    if payload.get("label_column"):
        result["label_column"] = str(payload["label_column"])
    if payload.get("categorical_encoding"):
        result["categorical_encoding"] = str(payload["categorical_encoding"])
    elif params.get("categorical_encoding"):
        result["categorical_encoding"] = str(params["categorical_encoding"])
    elif feature_manifest is not None:
        result["categorical_encoding"] = load_feature_manifest_encoding(feature_manifest) or DEFAULT_CATEGORICAL_ENCODING
    return result


def trial_config_from_report(trial_dir: Path, *, feature_manifest: Path | None = None) -> dict[str, Any]:
    payload = first_lgbm_report(trial_dir)
    if payload is None:
        raise FileNotFoundError(f"no lgbm_rank_report*.json under {trial_dir}")
    params = lightgbm_ranking_params_with_defaults(payload.get("model_params") or {})
    categorical_encoding = (
        str(payload.get("categorical_encoding") or "")
        or str((payload.get("model_params") or {}).get("categorical_encoding") or "")
        or (load_feature_manifest_encoding(feature_manifest) if feature_manifest is not None else None)
        or DEFAULT_CATEGORICAL_ENCODING
    )
    return {
        "payload": payload,
        "label_column": str(payload.get("label_column") or "rank_label_3d"),
        "categorical_encoding": categorical_encoding,
        "model_params": params,
    }
