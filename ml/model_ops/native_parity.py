from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from ml.model_ops.promote import file_hash, read_json
from ml.training.labels import as_float
from ml.training.matrices import build_feature_matrix_from_metadata


def read_dataset_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parity_factor_rows(rows: Sequence[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    numeric_columns = [str(value) for value in metadata.get("numeric_columns") or []]
    categorical_columns = [str(value) for value in metadata.get("categorical_columns") or []]
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        factors: dict[str, Any] = {}
        for column in numeric_columns:
            factors[column] = as_float(row.get(column)) or 0.0
        for column in categorical_columns:
            factors[column] = str(row.get(column) or "unknown")
        result.append(
            {
                "code": f"{row.get('date') or 'unknown'}|{row.get('code') or index}",
                "method": "b2",
                "factors": factors,
                "diagnostics": {},
            }
        )
    return result


def select_sample_rows(rows: Sequence[dict[str, Any]], sample_size: int) -> list[dict[str, Any]]:
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    ordered = sorted(rows, key=lambda row: (str(row.get("date") or ""), str(row.get("code") or "")))
    if len(ordered) <= sample_size:
        return list(ordered)
    if sample_size == 1:
        return [ordered[-1]]
    step = (len(ordered) - 1) / (sample_size - 1)
    indexes = sorted({round(index * step) for index in range(sample_size)})
    return [ordered[index] for index in indexes]


def python_predictions(model_path: Path, rows: Sequence[dict[str, Any]], metadata: dict[str, Any]) -> list[float]:
    try:
        import lightgbm as lgb
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"native parity requires Python dependency: {exc.name}") from exc
    matrix, feature_names, _code_maps = build_feature_matrix_from_metadata(rows, metadata)
    expected = list(metadata.get("feature_names") or [])
    if expected and feature_names != expected:
        raise ValueError("metadata feature_names do not match rebuilt Python feature order")
    model = lgb.Booster(model_file=str(model_path))
    return [float(value) for value in model.predict(np.array(matrix, dtype=float))]


def rust_predictions(
    *,
    binary: Path,
    model_path: Path,
    metadata_path: Path,
    rows_path: Path,
) -> list[float]:
    completed = subprocess.run(
        [
            str(binary),
            "model-predict",
            "--model-path",
            str(model_path),
            "--model-feature-metadata-path",
            str(metadata_path),
            "--rows",
            str(rows_path),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = json.loads(completed.stdout)
    predictions = payload.get("predictions")
    if not isinstance(predictions, list):
        raise ValueError("Rust model-predict output missing predictions")
    return [float(row["score"]) for row in predictions]


def generate_native_parity_report(
    *,
    candidate_dir: Path,
    dataset: Path,
    binary: Path,
    output: Path | None = None,
    sample_size: int = 128,
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    model_path = candidate_dir / "model.txt"
    metadata_path = candidate_dir / "model_metadata.json"
    metadata = read_json(metadata_path)
    if str(metadata.get("categorical_encoding") or "one_hot") != "native":
        raise ValueError("native parity only applies to native categorical models")
    rows = select_sample_rows(read_dataset_rows(dataset), sample_size)
    if not rows:
        raise ValueError("dataset has no rows for parity")
    py_scores = python_predictions(model_path, rows, metadata)
    factor_rows = parity_factor_rows(rows, metadata)
    with tempfile.TemporaryDirectory() as temp_dir:
        rows_path = Path(temp_dir) / "parity_rows.json"
        rows_path.write_text(json.dumps(factor_rows, ensure_ascii=False), encoding="utf-8")
        rust_scores = rust_predictions(
            binary=binary,
            model_path=model_path,
            metadata_path=metadata_path,
            rows_path=rows_path,
        )
    if len(py_scores) != len(rust_scores):
        raise ValueError("Python/Rust prediction count mismatch")
    diffs = [abs(left - right) for left, right in zip(py_scores, rust_scores)]
    max_abs_diff = max(diffs) if diffs else 0.0
    report = {
        "status": "passed" if max_abs_diff <= tolerance else "failed",
        "sample_count": len(rows),
        "max_abs_diff": max_abs_diff,
        "tolerance": tolerance,
        "model_sha256": file_hash(model_path),
        "metadata_sha256": file_hash(metadata_path),
        "dataset": str(dataset),
        "binary": str(binary),
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    output_path = output or (candidate_dir / "native_parity_report.json")
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["status"] != "passed":
        raise ValueError(f"native parity failed: max_abs_diff={max_abs_diff} tolerance={tolerance}")
    return report


def add_native_parity_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("native-parity", description="生成 native categorical 模型 Python/Rust parity 报告")
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=Path("target/release/stock-select-rs"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-size", type=int, default=128)
    parser.add_argument("--tolerance", type=float, default=1e-9)
    parser.set_defaults(handler=main_from_args)
    return parser


def main_from_args(args: argparse.Namespace) -> int:
    report = generate_native_parity_report(
        candidate_dir=args.candidate_dir,
        dataset=args.dataset,
        binary=args.binary,
        output=args.output,
        sample_size=args.sample_size,
        tolerance=args.tolerance,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0
