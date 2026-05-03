from __future__ import annotations

import json
from pathlib import Path


def _environment_dir(runtime_root: Path) -> Path:
    return runtime_root / "environment"


def _history_path(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "history.json"


def load_environment_history(runtime_root: Path) -> list[dict[str, object]]:
    path = _history_path(runtime_root)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    intervals = payload.get("intervals")
    if not isinstance(intervals, list):
        raise ValueError("Invalid environment history payload.")
    return intervals


def write_environment_history(runtime_root: Path, intervals: list[dict[str, object]]) -> Path:
    path = _history_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"intervals": intervals}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_market_environment(runtime_root: Path, *, pick_date: str) -> dict[str, object]:
    for interval in load_environment_history(runtime_root):
        start = str(interval["start_date"])
        end = interval.get("end_date")
        if start <= pick_date and (end is None or pick_date <= str(end)):
            return {
                "state": interval["state"],
                "interval_start": start,
                "interval_end": end,
                "reason": interval.get("reason"),
                "source": interval.get("source"),
            }
    raise ValueError(f"No market environment interval covers pick_date {pick_date}.")
