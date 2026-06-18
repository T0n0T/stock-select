from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .features import DEFAULT_CATEGORICAL_ENCODING


def build_model_metadata(
    *,
    feature_manifest: str | None,
    train_rows: Sequence[dict[str, Any]],
    score_rows: Sequence[dict[str, Any]],
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    levels: dict[str, list[str]],
    feature_names: Sequence[str],
    lightgbm_feature_names: Sequence[str],
    label_column: str,
    model_params: dict[str, Any],
    feature_selection: dict[str, Any] | None = None,
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
    categorical_code_maps: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    train_dates = sorted({str(row.get("date")) for row in train_rows})
    score_dates = sorted({str(row.get("date")) for row in score_rows})
    metadata = {
        "feature_manifest": feature_manifest,
        "train_start": train_dates[0] if train_dates else None,
        "train_end": train_dates[-1] if train_dates else None,
        "score_start": score_dates[0] if score_dates else None,
        "score_end": score_dates[-1] if score_dates else None,
        "model_params": model_params,
        "numeric_columns": list(numeric_columns),
        "categorical_columns": list(categorical_columns),
        "feature_names": list(feature_names),
        "lightgbm_feature_names": list(lightgbm_feature_names),
        "categorical_encoding": categorical_encoding,
        "categorical_code_maps": categorical_code_maps or {},
        "categorical_levels": {column: list(values) for column, values in levels.items()},
        "one_hot_levels": {column: [f"{column}={value}" for value in values] for column, values in levels.items()},
        "label_column": label_column,
    }
    if feature_selection is not None:
        metadata["feature_selection"] = feature_selection
    return metadata


def write_model_artifacts(model: Any, metadata: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.txt"
    metadata_path = output_dir / "model_metadata.json"
    model.save_model(str(model_path))
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"model": str(model_path), "metadata": str(metadata_path)}


def write_feature_manifest(
    output_dir: Path,
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    fixed_categorical_levels: dict[str, list[str]],
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "feature_manifest.json"
    payload = {
        "numeric_features": list(numeric_columns),
        "categorical_features": list(categorical_columns),
        "categorical_levels": {column: list(values) for column, values in fixed_categorical_levels.items()},
        "categorical_encoding": categorical_encoding,
        "excluded_features": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
