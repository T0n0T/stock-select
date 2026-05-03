from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

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


def evaluate_market_environment(
    *,
    pick_date: str,
    sse_history: pd.DataFrame,
    cn2000_history: pd.DataFrame,
) -> dict[str, object]:
    sse_score = _score_index_environment_frame(sse_history, pick_date=pick_date)
    cn2000_score = _score_index_environment_frame(cn2000_history, pick_date=pick_date)
    total_score = round(float(sse_score["total_score"]) + float(cn2000_score["total_score"]), 2)
    if total_score >= 8.0:
        state = "strong"
    elif total_score <= 3.5:
        state = "weak"
    else:
        state = "neutral"
    return {
        "evaluate_date": pick_date,
        "state": state,
        "total_score": total_score,
        "indices": {
            "sse": sse_score,
            "cn2000": cn2000_score,
        },
        "reason": _summarize_environment_reason(
            state=state,
            sse_score=sse_score,
            cn2000_score=cn2000_score,
        ),
        "source": "scheduled",
    }


def _score_index_environment_frame(frame: pd.DataFrame, *, pick_date: str) -> dict[str, object]:
    working = frame.copy()
    working["trade_date"] = pd.to_datetime(working["trade_date"])
    working = working.loc[working["trade_date"] <= pd.Timestamp(pick_date)].sort_values("trade_date").reset_index(drop=True)
    close = working["close"].astype(float)
    volume = working["vol"].astype(float)
    short_mean = close.tail(min(25, len(close))).mean()
    long_mean = close.tail(min(60, len(close))).mean()
    trend_score = 2.0 if close.iloc[-1] >= short_mean >= long_mean else 0.0
    position_score = 1.0 if close.iloc[-1] >= close.tail(min(60, len(close))).median() else 0.0
    volume_score = 1.0 if volume.iloc[-1] >= volume.tail(min(20, len(volume))).mean() else 0.0
    macd_base = close.iloc[-20] if len(close) >= 20 else close.iloc[0]
    macd_score = 1.0 if close.iloc[-1] >= macd_base else 0.0
    return {
        "trend_score": trend_score,
        "position_score": position_score,
        "volume_score": volume_score,
        "macd_score": macd_score,
        "total_score": trend_score + position_score + volume_score + macd_score,
    }


def _summarize_environment_reason(*, state: str, sse_score: dict[str, object], cn2000_score: dict[str, object]) -> str:
    if state == "strong":
        return "indices trend up"
    if state == "weak":
        return "indices break down"
    return "mixed market signals"
