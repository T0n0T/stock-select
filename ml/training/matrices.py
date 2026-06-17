from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Sequence

from .features import CATEGORICAL_ENCODINGS, DEFAULT_CATEGORICAL_ENCODING
from .labels import as_float


def category_levels(
    rows: Sequence[dict[str, Any]],
    categorical_columns: Sequence[str],
    *,
    max_levels: int = 32,
    fixed_categorical_levels: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    levels: dict[str, list[str]] = {}
    for column in categorical_columns:
        if fixed_categorical_levels and column in fixed_categorical_levels:
            levels[column] = list(fixed_categorical_levels[column])
            continue
        counts = Counter(str(row.get(column) or "unknown") for row in rows)
        levels[column] = [value for value, _count in counts.most_common(max_levels)]
    return levels


def categorical_code_maps(levels: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    return {
        column: {str(level): index for index, level in enumerate(values)}
        for column, values in levels.items()
    }


def build_feature_matrix(
    rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    levels: dict[str, list[str]] | None = None,
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
) -> tuple[list[list[float]], list[str], dict[str, dict[str, int]]]:
    if categorical_encoding not in CATEGORICAL_ENCODINGS:
        raise ValueError(f"unsupported categorical_encoding: {categorical_encoding}")
    levels = levels or category_levels(rows, categorical_columns)
    code_maps = categorical_code_maps(levels)
    feature_names = list(numeric_columns)
    if categorical_encoding == "one_hot":
        for column in categorical_columns:
            feature_names.extend(f"{column}={value}" for value in levels.get(column, []))
    else:
        feature_names.extend(categorical_columns)

    matrix: list[list[float]] = []
    for row in rows:
        values = [as_float(row.get(column)) or 0.0 for column in numeric_columns]
        for column in categorical_columns:
            current = str(row.get(column) or "unknown")
            if categorical_encoding == "one_hot":
                values.extend(1.0 if current == value else 0.0 for value in levels.get(column, []))
            else:
                values.append(float(code_maps.get(column, {}).get(current, -1)))
        matrix.append(values)
    return matrix, feature_names, code_maps


def build_feature_matrix_from_metadata(
    rows: Sequence[dict[str, Any]],
    metadata: dict[str, Any],
) -> tuple[list[list[float]], list[str], dict[str, dict[str, int]]]:
    numeric_columns = [str(value) for value in metadata.get("numeric_columns") or []]
    categorical_columns = [str(value) for value in metadata.get("categorical_columns") or []]
    levels = {
        str(column): [str(value) for value in values]
        for column, values in (metadata.get("categorical_levels") or {}).items()
        if isinstance(values, list)
    }
    categorical_encoding = str(metadata.get("categorical_encoding") or DEFAULT_CATEGORICAL_ENCODING)
    return build_feature_matrix(
        rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
        categorical_encoding=categorical_encoding,
    )


def safe_feature_names(feature_names: Sequence[str]) -> list[str]:
    result = []
    seen: dict[str, int] = defaultdict(int)
    for index, name in enumerate(feature_names):
        safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
        safe = safe.strip("_") or f"feature_{index}"
        seen[safe] += 1
        if seen[safe] > 1:
            safe = f"{safe}_{seen[safe]}"
        result.append(safe)
    return result
