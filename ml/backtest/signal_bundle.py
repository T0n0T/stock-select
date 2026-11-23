from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class SignalRow:
    date: str
    code: str
    model_score: float
    model_rank: int | None = None


@dataclass(frozen=True)
class SignalBundle:
    rows_by_date: dict[str, tuple[SignalRow, ...]]

    @property
    def dates(self) -> tuple[str, ...]:
        return tuple(sorted(self.rows_by_date))

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted({row.code for rows in self.rows_by_date.values() for row in rows}))

    def rows_for_date(self, trading_date: str | date | datetime) -> tuple[SignalRow, ...]:
        return self.rows_by_date.get(normalize_date(trading_date), ())


def normalize_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        raise ValueError("signal date is required")
    return text[:10]


def _number(value: Any, *, field: str, required: bool = False) -> float | None:
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric: {value!r}") from exc


def _infer_date_from_source(source: Path) -> str | None:
    """Infer the selection date from ``select/<date>.<method>/ranked.json``."""
    for part in reversed(source.parts):
        match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\.|$)", part)
        if match:
            return match.group(1)
    return None


def _row_from_mapping(
    raw: Mapping[str, Any], *, source: Path, default_date: str | None = None
) -> SignalRow:
    code = str(raw.get("code") or raw.get("symbol") or "").strip()
    if not code:
        raise ValueError(f"{source}: signal code is required")
    score = _number(raw.get("model_score", raw.get("score")), field="model_score", required=True)
    rank_value = _number(raw.get("model_rank", raw.get("rank")), field="model_rank")
    return SignalRow(
        date=normalize_date(raw.get("date") or raw.get("trading_date") or default_date),
        code=code,
        model_score=float(score),
        model_rank=int(rank_value) if rank_value is not None else None,
    )


def _json_rows(payload: Any, *, source: Path) -> list[SignalRow]:
    if isinstance(payload, Mapping):
        raw_rows = payload.get("rows", payload.get("signals"))
        if raw_rows is None and {"date", "code"}.issubset(payload):
            raw_rows = [payload]
    else:
        raw_rows = payload
    if not isinstance(raw_rows, list):
        raise ValueError(f"{source}: expected a JSON list or an object with rows")
    default_date = None
    if isinstance(payload, Mapping):
        artifact_key = payload.get("artifact_key")
        if artifact_key:
            default_date = normalize_date(artifact_key)
    default_date = default_date or _infer_date_from_source(source)
    return [
        _row_from_mapping(row, source=source, default_date=default_date)
        for row in raw_rows
        if isinstance(row, Mapping)
    ]


_DAILY_RUN_DIR = re.compile(r"\d{4}-\d{2}-\d{2}\.([^\.]+)")


def _daily_ranked_files(path: Path, method: str | None) -> list[Path]:
    files = [path / "ranked.json"] if (path / "ranked.json").is_file() else sorted(path.glob("*/ranked.json"))
    by_method: dict[str, list[Path]] = defaultdict(list)
    for child in files:
        match = _DAILY_RUN_DIR.fullmatch(child.parent.name)
        if match:
            by_method[match.group(1)].append(child)

    if method is None and len(by_method) > 1:
        raise ValueError(f"{path}: multiple daily methods found ({', '.join(sorted(by_method))}); specify --method")
    selected = by_method.get(method, []) if method is not None else next(iter(by_method.values()), [])
    if not selected:
        raise ValueError(f"{path}: no daily ranked.json files found for {method or 'any method'}")
    return selected


def load_signal_rows(path: Path, *, method: str | None = None) -> list[SignalRow]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir():
        return [row for child in _daily_ranked_files(path, method) for row in load_signal_rows(child)]
    if method is not None:
        raise ValueError("--method requires a signal directory")
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            default_date = _infer_date_from_source(path)
            return [
                _row_from_mapping(row, source=path, default_date=default_date)
                for row in csv.DictReader(handle)
            ]
    if path.suffix.lower() in {".json", ".jsonl"}:
        if path.suffix.lower() == ".jsonl":
            default_date = _infer_date_from_source(path)
            return [
                _row_from_mapping(json.loads(line), source=path, default_date=default_date)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        return _json_rows(json.loads(path.read_text(encoding="utf-8")), source=path)
    raise ValueError(f"unsupported signal file type: {path.suffix}")


def load_signal_bundle(path: Path, *, method: str | None = None) -> SignalBundle:
    rows = load_signal_rows(path, method=method)
    grouped: dict[str, list[SignalRow]] = defaultdict(list)
    for row in rows:
        grouped[row.date].append(row)
    for day_rows in grouped.values():
        day_rows.sort(key=lambda row: (row.model_rank if row.model_rank is not None else 2**31, -row.model_score, row.code))
    return SignalBundle({day: tuple(day_rows) for day, day_rows in grouped.items()})
