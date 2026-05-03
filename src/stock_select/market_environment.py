from __future__ import annotations

import json
from pathlib import Path

from stock_select.environment_models import MarketEnvironmentInterval


def _environment_dir(runtime_root: Path) -> Path:
    return runtime_root / "environment"


def _history_path(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "history.json"


def _load_interval_models(runtime_root: Path) -> list[MarketEnvironmentInterval]:
    path = _history_path(runtime_root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid environment history payload.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid environment history payload.")
    intervals = payload.get("intervals")
    if not isinstance(intervals, list):
        raise ValueError("Invalid environment history payload.")
    return [MarketEnvironmentInterval.from_payload(interval) for interval in intervals]


def load_environment_history(runtime_root: Path) -> list[dict[str, object]]:
    return [interval.to_dict() for interval in _load_interval_models(runtime_root)]


def write_environment_history(runtime_root: Path, intervals: list[dict[str, object]]) -> Path:
    path = _history_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    validated_intervals = [interval.to_dict() for interval in (MarketEnvironmentInterval.from_payload(item) for item in intervals)]
    path.write_text(json.dumps({"intervals": validated_intervals}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_market_environment(runtime_root: Path, *, pick_date: str) -> dict[str, object]:
    applicable_intervals = [
        interval
        for interval in _load_interval_models(runtime_root)
        if interval.start_date <= pick_date and (interval.end_date is None or pick_date <= interval.end_date)
    ]
    if applicable_intervals:
        preferred_intervals = [interval for interval in applicable_intervals if interval.manual_override]
        ranked_intervals = preferred_intervals or applicable_intervals
        newest = max(
            ranked_intervals,
            key=lambda interval: (interval.start_date, interval.evaluated_at, interval.manual_override),
        )
        return {
            "state": newest.state,
            "interval_start": newest.start_date,
            "interval_end": newest.end_date,
            "reason": newest.reason,
            "source": newest.source,
        }
    raise ValueError(f"No market environment interval covers pick_date {pick_date}.")
