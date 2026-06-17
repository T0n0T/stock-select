from __future__ import annotations

import math
from typing import Any, Sequence


TRAIN_LABEL_COLUMNS = {"rank_label_3d", "rank_label_5d", "ret3_ge5_label", "ret5_ge5_label"}


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def pct(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100.0, 1) if denominator else None


def label_value(row: dict[str, Any], *, label_column: str) -> int | None:
    if label_column == "ret3_ge5_label":
        ret3 = as_float(row.get("ret3"))
        if ret3 is None:
            return None
        return 3 if ret3 >= 5.0 else 0
    if label_column == "ret5_ge5_label":
        ret5 = as_float(row.get("ret5"))
        if ret5 is None:
            return None
        return 3 if ret5 >= 5.0 else 0
    value = as_float(row.get(label_column))
    return None if value is None else int(value)


def rows_for_dates(
    rows: Sequence[dict[str, Any]],
    dates: set[str],
    *,
    label_column: str = "rank_label_3d",
) -> list[dict[str, Any]]:
    filtered = [
        row
        for row in rows
        if str(row.get("date")) in dates and label_value(row, label_column=label_column) is not None
    ]
    return sorted(filtered, key=lambda row: (str(row.get("date")), str(row.get("code"))))


def labels(rows: Sequence[dict[str, Any]], *, label_column: str) -> list[int]:
    return [int(label_value(row, label_column=label_column) or 0) for row in rows]
