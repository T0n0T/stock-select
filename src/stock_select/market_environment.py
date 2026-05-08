from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from stock_select.environment_models import MarketEnvironmentInterval
from stock_select.strategies.b1 import compute_zx_lines


_STRONG_TREND_STATES = {"S4_near_strong", "S5_strong"}
_WEAK_TREND_STATES = {
    "S6_strong_to_weak_initial",
    "S7_strong_to_weak_accelerating",
    "S8_fast_weakening",
    "S9_risk_increasing",
    "S10_weak",
}
_STRONG_MACD_STATES = {"M3_underwater_golden_cross", "M5_underwater_advance", "M12_primary_advance"}
_REPAIR_MACD_STATES = {"M1_deep_pullback", "M2_bottom_divergence_setup", "M4_repair_extension", "M11_repairing"}
_WEAK_MACD_STATES = {"M7_uptrend_exhausting", "M8_above_water_dead_cross", "M9_pullback"}
_SCORE_BASED_STRONG_THRESHOLD = 10.0
_SCORE_BASED_WEAK_THRESHOLD = -4.0
_UNDERWATER_ADVANCE_MAX_BARS_SINCE_CROSS = 8


def _environment_dir(runtime_root: Path) -> Path:
    return runtime_root / "environment"


def _daily_dir(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "daily"


def _history_jsonl_path(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "history.jsonl"


def _latest_snapshot_path(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "latest.json"


def _lock_path(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / ".lock"


def environment_history_exists(runtime_root: Path) -> bool:
    return _history_jsonl_path(runtime_root).exists() or _latest_snapshot_path(runtime_root).exists()


def _write_text_atomic(path: Path, content: str) -> None:
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


@contextmanager
def _locked_environment(runtime_root: Path):
    environment_dir = _environment_dir(runtime_root)
    environment_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path(runtime_root)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _require_daily_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid environment history payload.")
    required_str_fields = (
        "pick_date",
        "state",
        "score_based_state",
        "rule_based_state",
        "vote_based_state",
        "evaluate_date",
        "source",
        "reason",
    )
    for field in required_str_fields:
        if not isinstance(payload.get(field), str):
            raise ValueError("Invalid environment history payload.")
    for field in ("total_score", "score_based_total"):
        value = payload.get(field)
        if not isinstance(value, int | float):
            raise ValueError("Invalid environment history payload.")
    manual_override = payload.get("manual_override", False)
    if not isinstance(manual_override, bool):
        raise ValueError("Invalid environment history payload.")
    return {
        "pick_date": str(payload["pick_date"]),
        "state": str(payload["state"]),
        "score_based_state": str(payload["score_based_state"]),
        "rule_based_state": str(payload["rule_based_state"]),
        "vote_based_state": str(payload["vote_based_state"]),
        "evaluate_date": str(payload["evaluate_date"]),
        "source": str(payload["source"]),
        "reason": str(payload["reason"]),
        "total_score": float(payload["total_score"]),
        "score_based_total": float(payload["score_based_total"]),
        "manual_override": manual_override,
    }


def _normalize_daily_record(record: dict[str, object]) -> dict[str, object]:
    normalized = _require_daily_payload(record)
    return normalized


def _daily_record_from_evaluation(
    *,
    pick_date: str,
    evaluation: dict[str, object],
    source: str | None = None,
) -> dict[str, object]:
    state = str(evaluation["state"])
    return {
        "pick_date": pick_date,
        "state": state,
        "score_based_state": str(evaluation.get("score_based_state") or state),
        "rule_based_state": str(evaluation.get("rule_based_state") or state),
        "vote_based_state": str(evaluation.get("vote_based_state") or state),
        "evaluate_date": str(evaluation.get("evaluate_date") or pick_date),
        "source": str(source or evaluation.get("source") or "scheduled"),
        "reason": str(evaluation.get("reason") or ""),
        "total_score": float(evaluation.get("total_score") or 0.0),
        "score_based_total": float(evaluation.get("score_based_total") or evaluation.get("total_score") or 0.0),
        "manual_override": bool(source == "manual_override" or evaluation.get("manual_override") is True),
    }


def _records_from_interval_payloads(intervals: list[dict[str, object]]) -> list[dict[str, object]]:
    expanded: dict[str, dict[str, object]] = {}
    for payload in intervals:
        interval = MarketEnvironmentInterval.from_payload(payload)
        end_date = interval.end_date or interval.start_date
        for date in pd.date_range(interval.start_date, end_date, freq="D"):
            pick_date = date.strftime("%Y-%m-%d")
            candidate = {
                "pick_date": pick_date,
                "state": interval.state,
                "score_based_state": interval.state,
                "rule_based_state": interval.state,
                "vote_based_state": interval.state,
                "evaluate_date": interval.evaluated_at,
                "source": interval.source,
                "reason": interval.reason or "",
                "total_score": 0.0,
                "score_based_total": 0.0,
                "manual_override": interval.manual_override or interval.source == "manual",
            }
            existing = expanded.get(pick_date)
            if existing is None:
                expanded[pick_date] = candidate
                continue
            if bool(candidate["manual_override"]) and not bool(existing["manual_override"]):
                expanded[pick_date] = candidate
                continue
            if bool(existing["manual_override"]) and not bool(candidate["manual_override"]):
                continue
            expanded[pick_date] = candidate
    return [expanded[pick_date] for pick_date in sorted(expanded)]


def _coerce_daily_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    if not records:
        return []
    first = records[0]
    if "pick_date" in first:
        return [_normalize_daily_record(item) for item in records]
    if "start_date" in first:
        return _records_from_interval_payloads(records)
    raise ValueError("Invalid environment history payload.")


def _load_daily_records(runtime_root: Path) -> list[dict[str, object]]:
    path = _history_jsonl_path(runtime_root)
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            records.append(_normalize_daily_record(payload))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "Invalid environment history payload.":
            raise
        raise ValueError("Invalid environment history payload.") from exc
    return records


def _daily_record_filename(record: dict[str, object]) -> str:
    return f"{record['pick_date']}.{record['state']}.json"


def _build_intervals_from_daily_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    ordered = sorted(records, key=lambda item: str(item["pick_date"]))
    if not ordered:
        return []
    intervals: list[dict[str, object]] = []
    for record in ordered:
        pick_date = str(record["pick_date"])
        state = str(record["state"])
        source = str(record["source"])
        reason = str(record["reason"])
        evaluate_date = str(record["evaluate_date"])
        if intervals and intervals[-1]["state"] == state:
            intervals[-1]["end_date"] = pick_date
            intervals[-1]["evaluated_at"] = evaluate_date
            intervals[-1]["source"] = source
            intervals[-1]["reason"] = reason
            continue
        intervals.append(
            {
                "state": state,
                "start_date": pick_date,
                "end_date": pick_date,
                "evaluated_at": evaluate_date,
                "source": source,
                "manual_override": bool(record.get("manual_override")),
                "reason": reason,
            }
        )
    if intervals:
        intervals[-1]["end_date"] = None
    return intervals


def load_environment_history(runtime_root: Path) -> list[dict[str, object]]:
    return _build_intervals_from_daily_records(_load_daily_records(runtime_root))


def load_environment_history_snapshot(runtime_root: Path) -> dict[str, object]:
    path = _latest_snapshot_path(runtime_root)
    if not path.exists():
        raise ValueError(f"Market environment snapshot not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid environment history snapshot payload.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid environment history snapshot payload.")
    daily = payload.get("daily")
    intervals = payload.get("intervals")
    if not isinstance(daily, list) or not isinstance(intervals, list):
        raise ValueError("Invalid environment history snapshot payload.")
    validated_daily: list[dict[str, object]] = []
    for item in daily:
        if not isinstance(item, dict):
            raise ValueError("Invalid environment history snapshot payload.")
        for field in ("pick_date", "state", "source", "reason"):
            if not isinstance(item.get(field), str):
                raise ValueError("Invalid environment history snapshot payload.")
        validated_daily.append(
            {
                "pick_date": str(item["pick_date"]),
                "state": str(item["state"]),
                "source": str(item["source"]),
                "reason": str(item["reason"]),
            }
        )
    validated_intervals = [interval.to_dict() for interval in (MarketEnvironmentInterval.from_payload(item) for item in intervals)]
    return {"daily": validated_daily, "intervals": validated_intervals}


def _raise_if_out_of_order_insertion(intervals: list[dict[str, object]], *, pick_date: str) -> None:
    if intervals and pick_date < str(intervals[-1]["start_date"]):
        raise ValueError(f"Out-of-order market environment insertion is not supported for pick_date {pick_date}.")


def _insert_environment_interval(
    intervals: list[dict[str, object]],
    *,
    new_interval: dict[str, object],
) -> list[dict[str, object]]:
    ordered = [dict(interval) for interval in intervals]
    insert_index = 0
    start_date = str(new_interval["start_date"])
    while insert_index < len(ordered) and str(ordered[insert_index]["start_date"]) < start_date:
        insert_index += 1

    if insert_index < len(ordered):
        next_start = str(ordered[insert_index]["start_date"])
        new_interval["end_date"] = str((pd.Timestamp(next_start) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    else:
        new_interval["end_date"] = None

    ordered.insert(insert_index, new_interval)
    return ordered


def _write_environment_history_unlocked(runtime_root: Path, records: list[dict[str, object]]) -> Path:
    validated_records = sorted(_coerce_daily_records(records), key=lambda item: str(item["pick_date"]))
    environment_dir = _environment_dir(runtime_root)
    environment_dir.mkdir(parents=True, exist_ok=True)
    daily_dir = _daily_dir(runtime_root)
    daily_dir.mkdir(parents=True, exist_ok=True)
    history_path = _history_jsonl_path(runtime_root)
    latest_path = _latest_snapshot_path(runtime_root)
    for path in daily_dir.glob("*.json"):
        path.unlink()
    for record in validated_records:
        _write_text_atomic(
            daily_dir / _daily_record_filename(record),
            json.dumps(record, ensure_ascii=False, indent=2),
        )
    history_content = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in validated_records
    )
    if history_content:
        history_content += "\n"
    latest_content = json.dumps(
        {
            "daily": [
                {
                    "pick_date": str(item["pick_date"]),
                    "state": str(item["state"]),
                    "source": str(item["source"]),
                    "reason": str(item["reason"]),
                }
                for item in validated_records
            ],
            "intervals": _build_intervals_from_daily_records(validated_records),
        },
        ensure_ascii=False,
        indent=2,
    )
    _write_text_atomic(history_path, history_content)
    _write_text_atomic(latest_path, latest_content)
    return latest_path


def write_environment_history(runtime_root: Path, records: list[dict[str, object]]) -> Path:
    with _locked_environment(runtime_root):
        return _write_environment_history_unlocked(runtime_root, records)


def rebuild_environment_history(
    *,
    runtime_root: Path,
    pick_dates: list[str],
    sse_history: pd.DataFrame,
    cn2000_history: pd.DataFrame,
    overwrite: bool,
    source: str = "backfill",
) -> Path:
    history_path = _history_jsonl_path(runtime_root)
    latest_path = _latest_snapshot_path(runtime_root)
    if (history_path.exists() or latest_path.exists()) and not overwrite:
        raise ValueError(f"environment history already exists: {history_path}; rerun with --overwrite")
    records: list[dict[str, object]] = []
    for pick_date in sorted({str(item) for item in pick_dates if str(item).strip()}):
        evaluation = evaluate_market_environment(
            pick_date=pick_date,
            sse_history=sse_history,
            cn2000_history=cn2000_history,
        )
        records.append(_daily_record_from_evaluation(pick_date=pick_date, evaluation=evaluation, source=source))
    return write_environment_history(runtime_root, records)


def build_environment_history_for_dates(
    pick_dates: list[str],
    evaluator: Callable[[str], dict[str, object]],
) -> list[dict[str, object]]:
    ordered_dates = sorted({str(pick_date) for pick_date in pick_dates if str(pick_date).strip()})
    if not ordered_dates:
        return []

    evaluations = [(pick_date, evaluator(pick_date)) for pick_date in ordered_dates]
    intervals: list[dict[str, object]] = []

    for index, (pick_date, evaluation) in enumerate(evaluations):
        state = str(evaluation.get("score_based_state") or evaluation["state"]).lower()
        next_pick_date = evaluations[index + 1][0] if index + 1 < len(evaluations) else None
        end_date = (
            str((pd.Timestamp(next_pick_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
            if next_pick_date is not None
            else pick_date
        )

        interval = {
            "state": state,
            "start_date": pick_date,
            "end_date": end_date,
            "evaluated_at": str(evaluation.get("evaluate_date") or pick_date),
            "source": str(evaluation.get("source") or "scheduled"),
            "manual_override": False,
            "reason": None if evaluation.get("reason") is None else str(evaluation.get("reason")),
        }

        if intervals and intervals[-1]["state"] == state:
            intervals[-1]["end_date"] = end_date
            intervals[-1]["evaluated_at"] = interval["evaluated_at"]
            intervals[-1]["source"] = interval["source"]
            intervals[-1]["reason"] = interval["reason"]
            continue

        intervals.append(interval)

    return intervals


def resolve_market_environment(runtime_root: Path, *, pick_date: str) -> dict[str, object]:
    applicable_intervals = [
        interval
        for interval in (
            MarketEnvironmentInterval.from_payload(item) for item in _build_intervals_from_daily_records(_load_daily_records(runtime_root))
        )
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


def ensure_market_environment(
    runtime_root: Path,
    *,
    pick_date: str,
    evaluation_loader: Callable[[], dict[str, object]] | None = None,
) -> dict[str, object]:
    with _locked_environment(runtime_root):
        records = _load_daily_records(runtime_root)
        if any(str(record["pick_date"]) == pick_date for record in records):
            return resolve_market_environment(runtime_root, pick_date=pick_date)
        no_interval_message = f"No market environment interval covers pick_date {pick_date}."
        try:
            resolved = resolve_market_environment(runtime_root, pick_date=pick_date)
        except ValueError as exc:
            if str(exc) != no_interval_message or evaluation_loader is None:
                raise
            evaluation = evaluation_loader()
            records.append(_daily_record_from_evaluation(pick_date=pick_date, evaluation=evaluation))
            _write_environment_history_unlocked(runtime_root, records)
            return resolve_market_environment(runtime_root, pick_date=pick_date)
        if evaluation_loader is None:
            return resolved
        evaluation = evaluation_loader()
        records.append(_daily_record_from_evaluation(pick_date=pick_date, evaluation=evaluation))
        _write_environment_history_unlocked(runtime_root, records)
        return resolve_market_environment(runtime_root, pick_date=pick_date)


def override_market_environment(runtime_root: Path, *, pick_date: str, state: str, reason: str) -> dict[str, object]:
    with _locked_environment(runtime_root):
        intervals = load_environment_history(runtime_root)
        _raise_if_out_of_order_insertion(intervals, pick_date=pick_date)
        new_interval = {
            "state": state,
            "start_date": pick_date,
            "end_date": None,
            "evaluated_at": pick_date,
            "source": "manual_override",
            "manual_override": True,
            "reason": reason,
        }
        if intervals and intervals[-1].get("end_date") is None:
            last_start_date = str(intervals[-1]["start_date"])
            if last_start_date == pick_date:
                intervals[-1] = new_interval
                _write_environment_history_unlocked(runtime_root, intervals)
                return new_interval
            if last_start_date < pick_date:
                intervals[-1]["end_date"] = str((pd.Timestamp(pick_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
                intervals.append(new_interval)
                _write_environment_history_unlocked(runtime_root, intervals)
                return new_interval
        for index in range(len(intervals) - 1, -1, -1):
            interval = intervals[index]
            if interval["start_date"] <= pick_date <= str(interval["end_date"]):
                if interval["start_date"] == pick_date:
                    intervals[index] = new_interval
                    _write_environment_history_unlocked(runtime_root, intervals)
                    return new_interval
                interval["end_date"] = str((pd.Timestamp(pick_date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
                intervals.append(new_interval)
                _write_environment_history_unlocked(runtime_root, intervals)
                return new_interval
        intervals.append(new_interval)
        _write_environment_history_unlocked(runtime_root, intervals)
        return new_interval


def evaluate_market_environment(
    *,
    pick_date: str,
    sse_history: pd.DataFrame,
    cn2000_history: pd.DataFrame,
) -> dict[str, object]:
    snapshots: list[dict[str, object]] = []
    trade_dates = sorted(
        set(pd.to_datetime(sse_history["trade_date"])) & set(pd.to_datetime(cn2000_history["trade_date"]))
    )
    for trade_ts in trade_dates:
        if trade_ts > pd.Timestamp(pick_date):
            break
        trade_date = trade_ts.strftime("%Y-%m-%d")
        try:
            sse_score = _score_index_environment_frame(sse_history, pick_date=trade_date)
            cn2000_score = _score_index_environment_frame(cn2000_history, pick_date=trade_date)
        except ValueError as exc:
            if "Insufficient history" in str(exc):
                continue
            raise
        sse_monthly_bias = _build_monthly_macd_bias(sse_history, pick_date=trade_date)
        cn2000_monthly_bias = _build_monthly_macd_bias(cn2000_history, pick_date=trade_date)
        rule_based_state = _compute_raw_environment_state(
            sse_score=sse_score,
            cn2000_score=cn2000_score,
            sse_monthly_bias=sse_monthly_bias,
            cn2000_monthly_bias=cn2000_monthly_bias,
        )
        combined_total = round(float(sse_score["total_score"]) + float(cn2000_score["total_score"]), 2)
        raw_state = _score_based_raw_environment_state(
            combined_total=combined_total,
            sse_monthly_bias=sse_monthly_bias,
            cn2000_monthly_bias=cn2000_monthly_bias,
        )
        snapshots.append(
            {
                "date": trade_date,
                "sse_score": sse_score,
                "cn2000_score": cn2000_score,
                "sse_monthly_bias": sse_monthly_bias,
                "cn2000_monthly_bias": cn2000_monthly_bias,
                "combined_total": combined_total,
                "raw_state": raw_state,
                "rule_based_state": rule_based_state,
                "vote_based_state": _vote_based_environment_state(sse_score=sse_score, cn2000_score=cn2000_score),
                "hard_strong_trigger": False,
                "hard_weak_trigger": False,
            }
        )

    if not snapshots:
        raise ValueError("Insufficient history for market environment evaluation.")

    smoothed_states = _smooth_score_based_states(
        raw_states=[str(item["raw_state"]) for item in snapshots],
    )
    latest = snapshots[-1]
    sse_score = latest["sse_score"]
    cn2000_score = latest["cn2000_score"]
    sse_monthly_bias = latest["sse_monthly_bias"]
    cn2000_monthly_bias = latest["cn2000_monthly_bias"]
    raw_state = str(latest["raw_state"])
    rule_based_state = str(latest["rule_based_state"])
    vote_based_state = str(latest["vote_based_state"])
    state = smoothed_states[-1]
    total_score = float(latest["combined_total"])
    return {
        "evaluate_date": pick_date,
        "state": state,
        "score_based_state": state,
        "raw_state": raw_state,
        "rule_based_state": rule_based_state,
        "vote_based_state": vote_based_state,
        "total_score": total_score,
        "score_based_total": total_score,
        "score_thresholds": {
            "strong": _SCORE_BASED_STRONG_THRESHOLD,
            "weak": _SCORE_BASED_WEAK_THRESHOLD,
        },
        "indices": {
            "sse": sse_score,
            "cn2000": cn2000_score,
        },
        "monthly_bias": {
            "sse": sse_monthly_bias,
            "cn2000": cn2000_monthly_bias,
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
    if working.empty or working.iloc[-1]["trade_date"] != pd.Timestamp(pick_date):
        raise ValueError(f"No market environment data found for pick_date {pick_date}.")
    if len(working) < 60:
        raise ValueError("Insufficient history for market environment evaluation.")
    prepared = _prepare_index_environment_frame(working)
    box_component = _box_volume_component(prepared)
    trend_component = _trend_component(prepared)
    macd_component = _macd_component(prepared)
    total_score = round(
        float(box_component["score"]) + float(trend_component["score"]) + float(macd_component["score"]),
        3,
    )
    state_hint = _component_state_hint(
        box_score=float(box_component["score"]),
        trend_score=float(trend_component["score"]),
        macd_score=float(macd_component["score"]),
    )
    return {
        "box_volume": box_component,
        "trend": trend_component,
        "macd": macd_component,
        "total_score": total_score,
        "state_hint": state_hint,
        "close": round(float(prepared["close"].iloc[-1]), 3),
        "ma25": round(float(prepared["ma25"].iloc[-1]), 3) if pd.notna(prepared["ma25"].iloc[-1]) else None,
        "ma60": round(float(prepared["ma60"].iloc[-1]), 3) if pd.notna(prepared["ma60"].iloc[-1]) else None,
    }


def _summarize_environment_reason(*, state: str, sse_score: dict[str, object], cn2000_score: dict[str, object]) -> str:
    sse_reason = f"SSE {sse_score['state_hint']}"
    cn_reason = f"CN2000 {cn2000_score['state_hint']}"
    if state == "strong":
        return f"{sse_reason}; {cn_reason}; 双指数共振偏强"
    if state == "weak":
        return f"{sse_reason}; {cn_reason}; 双指数共振偏弱"
    return f"{sse_reason}; {cn_reason}; 修复或分化，环境中立"


def _prepare_index_environment_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    close = prepared["close"].astype(float)
    prepared["ma25"] = close.rolling(window=25, min_periods=25).mean()
    prepared["ma60"] = close.rolling(window=60, min_periods=60).mean()
    prepared["bbi"] = _compute_bbi(close)
    zxdq, zxdkx = compute_zx_lines(prepared[["trade_date", "open", "high", "low", "close", "vol"]].copy())
    prepared["zxdq"] = zxdq.astype(float)
    prepared["zxdkx"] = zxdkx.astype(float)
    dif, dea, hist = _compute_macd_triplet(close)
    prepared["dif"] = dif
    prepared["dea"] = dea
    prepared["hist"] = hist
    prepared["golden_cross"] = (dif > dea) & (dif.shift(1) <= dea.shift(1))
    prepared["death_cross"] = (dif < dea) & (dif.shift(1) >= dea.shift(1))
    prepared["hist_shrink_streak"] = _compute_hist_shrink_streak(hist)
    prepared["bars_since_golden_cross"] = _compute_bars_since_true(prepared["golden_cross"])
    prepared["vol_ma20"] = prepared["vol"].astype(float).rolling(window=20, min_periods=20).mean()
    return prepared


def _compute_bbi(close: pd.Series) -> pd.Series:
    return (
        close.rolling(window=3, min_periods=3).mean()
        + close.rolling(window=6, min_periods=6).mean()
        + close.rolling(window=12, min_periods=12).mean()
        + close.rolling(window=24, min_periods=24).mean()
    ) / 4.0


def _compute_macd_triplet(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def _compute_hist_shrink_streak(hist: pd.Series) -> pd.Series:
    streak: list[int] = []
    current = 0
    prev_abs: float | None = None
    prev_sign: int | None = None
    for value in hist.astype(float):
        sign = 1 if value > 0 else -1 if value < 0 else 0
        abs_value = abs(value)
        if (
            prev_abs is not None
            and prev_sign is not None
            and sign == prev_sign
            and sign != 0
            and abs_value < prev_abs
        ):
            current += 1
        else:
            current = 1
        streak.append(current)
        prev_abs = abs_value
        prev_sign = sign
    return pd.Series(streak, index=hist.index, dtype="int64")


def _compute_bars_since_true(values: pd.Series) -> pd.Series:
    bars: list[int | None] = []
    current: int | None = None
    for value in values.astype(bool):
        if value:
            current = 0
        elif current is not None:
            current += 1
        bars.append(current)
    return pd.Series(bars, index=values.index, dtype="float64")


def _build_monthly_macd_bias(frame: pd.DataFrame, *, pick_date: str) -> dict[str, object]:
    working = frame.copy()
    working["trade_date"] = pd.to_datetime(working["trade_date"])
    working = working.loc[working["trade_date"] <= pd.Timestamp(pick_date)].sort_values("trade_date").reset_index(drop=True)
    if len(working) < 40:
        return {"bias": "neutral"}

    monthly_close = working.set_index("trade_date")["close"].astype(float).resample("ME").last().dropna()
    if len(monthly_close) < 6:
        return {"bias": "neutral"}

    dif, dea, hist = _compute_macd_triplet(monthly_close)
    latest_idx = monthly_close.index[-1]
    latest_dif = float(dif.loc[latest_idx])
    latest_dea = float(dea.loc[latest_idx])
    latest_hist = float(hist.loc[latest_idx])
    prev_dea = float(dea.iloc[-2]) if len(dea) >= 2 else latest_dea
    dea_up = latest_dea > prev_dea

    if latest_dea > 0 and latest_hist > 0 and dea_up:
        return {"bias": "positive"}
    if latest_dea < 0 and latest_hist < 0 and dea_up:
        return {"bias": "repairing"}
    if latest_dea < 0:
        return {"bias": "negative"}
    if latest_dif < latest_dea:
        return {"bias": "negative"}
    return {"bias": "neutral"}


def _compute_raw_environment_state(
    *,
    sse_score: dict[str, object],
    cn2000_score: dict[str, object],
    sse_monthly_bias: dict[str, object],
    cn2000_monthly_bias: dict[str, object],
) -> str:
    combined = _combine_environment_state(sse_score=sse_score, cn2000_score=cn2000_score)
    monthly_biases = {str(sse_monthly_bias["bias"]), str(cn2000_monthly_bias["bias"])}
    if combined == "strong" and "negative" in monthly_biases:
        return "neutral"
    return combined


def _compute_raw_environment_state_from_previous_trade_date(
    *,
    sse_history: pd.DataFrame,
    cn2000_history: pd.DataFrame,
    pick_date: str,
) -> str | None:
    current_ts = pd.Timestamp(pick_date)
    prev_dates = sse_history.loc[pd.to_datetime(sse_history["trade_date"]) < current_ts, "trade_date"]
    if prev_dates.empty:
        return None
    prev_date = pd.to_datetime(prev_dates).max().strftime("%Y-%m-%d")
    try:
        prev_sse_score = _score_index_environment_frame(sse_history, pick_date=prev_date)
        prev_cn_score = _score_index_environment_frame(cn2000_history, pick_date=prev_date)
    except ValueError as exc:
        if "Insufficient history" in str(exc):
            return None
        raise
    prev_sse_monthly_bias = _build_monthly_macd_bias(sse_history, pick_date=prev_date)
    prev_cn_monthly_bias = _build_monthly_macd_bias(cn2000_history, pick_date=prev_date)
    return _compute_raw_environment_state(
        sse_score=prev_sse_score,
        cn2000_score=prev_cn_score,
        sse_monthly_bias=prev_sse_monthly_bias,
        cn2000_monthly_bias=prev_cn_monthly_bias,
    )


def _compute_consecutive_raw_state_counts(
    *,
    sse_history: pd.DataFrame,
    cn2000_history: pd.DataFrame,
    pick_date: str,
    raw_state: str,
) -> dict[str, int]:
    states = {"strong": 0, "neutral": 0, "weak": 0}
    states[raw_state] = 1

    current_ts = pd.Timestamp(pick_date)
    trade_dates = (
        pd.to_datetime(sse_history["trade_date"])
        .loc[pd.to_datetime(sse_history["trade_date"]) < current_ts]
        .drop_duplicates()
        .sort_values(ascending=False)
    )
    for ts in trade_dates:
        d = ts.strftime("%Y-%m-%d")
        try:
            sse_score = _score_index_environment_frame(sse_history, pick_date=d)
            cn_score = _score_index_environment_frame(cn2000_history, pick_date=d)
        except ValueError as exc:
            if "Insufficient history" in str(exc):
                break
            raise
        sse_monthly_bias = _build_monthly_macd_bias(sse_history, pick_date=d)
        cn_monthly_bias = _build_monthly_macd_bias(cn2000_history, pick_date=d)
        state = _compute_raw_environment_state(
            sse_score=sse_score,
            cn2000_score=cn_score,
            sse_monthly_bias=sse_monthly_bias,
            cn2000_monthly_bias=cn_monthly_bias,
        )
        if state != raw_state:
            break
        states[raw_state] += 1
    return states


def _apply_environment_state_machine(
    *,
    previous_state: str | None,
    raw_state: str,
    consecutive_raw_counts: dict[str, int],
    hard_strong_trigger: bool,
    hard_weak_trigger: bool,
) -> str:
    if previous_state is None:
        return raw_state
    if previous_state == raw_state:
        return raw_state
    if raw_state == "neutral":
        if previous_state in {"strong", "weak"} and consecutive_raw_counts["neutral"] < 2:
            return previous_state
        return "neutral"
    if raw_state == "strong":
        return "strong"
    if raw_state == "weak":
        return "weak"
    return raw_state


def _smooth_environment_states(
    *,
    raw_states: list[str],
    hard_strong_triggers: list[bool],
    hard_weak_triggers: list[bool],
) -> list[str]:
    if not raw_states:
        return []
    smoothed: list[str] = []
    counts = {"strong": 0, "neutral": 0, "weak": 0}
    previous_state: str | None = None
    for raw_state, hard_strong_trigger, hard_weak_trigger in zip(
        raw_states, hard_strong_triggers, hard_weak_triggers, strict=True
    ):
        counts = {key: (counts[key] + 1) if raw_state == key else 0 for key in counts}
        current = _apply_environment_state_machine(
            previous_state=previous_state,
            raw_state=raw_state,
            consecutive_raw_counts=counts,
            hard_strong_trigger=hard_strong_trigger,
            hard_weak_trigger=hard_weak_trigger,
        )
        smoothed.append(current)
        previous_state = current

    for index in range(1, len(smoothed)):
        if smoothed[index - 1] == "neutral" and smoothed[index] == "strong" and raw_states[index - 1] == "strong":
            if index < 2 or smoothed[index - 2] != "weak":
                smoothed[index - 1] = "strong"
        if smoothed[index - 1] == "neutral" and smoothed[index] == "weak" and raw_states[index - 1] == "weak":
            if index < 2 or smoothed[index - 2] != "strong":
                smoothed[index - 1] = "weak"
    return smoothed


def _collapse_single_day_neutral_islands(states: list[str]) -> list[str]:
    if len(states) < 3:
        return list(states)
    collapsed = list(states)
    for index in range(1, len(states) - 1):
        if (
            collapsed[index] == "neutral"
            and collapsed[index - 1] == collapsed[index + 1]
            and collapsed[index - 1] != "neutral"
        ):
            collapsed[index] = collapsed[index - 1]
    return collapsed


def _smooth_score_based_states(*, raw_states: list[str]) -> list[str]:
    smoothed = _smooth_environment_states(
        raw_states=raw_states,
        hard_strong_triggers=[False for _ in raw_states],
        hard_weak_triggers=[False for _ in raw_states],
    )
    return _collapse_single_day_neutral_islands(smoothed)


def _box_volume_component(frame: pd.DataFrame) -> dict[str, object]:
    latest = frame.iloc[-1]
    phase_window = frame.tail(60).reset_index(drop=True)

    box_low = float(phase_window["low"].min())
    low_pivot_idx = int(phase_window["low"].idxmin())
    for i in range(len(phase_window) - 2, 0, -1):
        if phase_window["low"].iloc[i] < phase_window["low"].iloc[i - 1] and phase_window["low"].iloc[i] < phase_window["low"].iloc[i + 1]:
            box_low = float(phase_window["low"].iloc[i])
            low_pivot_idx = i
            break

    box_high = float(phase_window["high"].max())
    high_pivot_idx = int(phase_window["high"].idxmax())
    for i in range(len(phase_window) - 2, 0, -1):
        if phase_window["high"].iloc[i] > phase_window["high"].iloc[i - 1] and phase_window["high"].iloc[i] > phase_window["high"].iloc[i + 1]:
            box_high = float(phase_window["high"].iloc[i])
            high_pivot_idx = i
            break

    p_value = (box_high + box_low) / 2.0
    weak_phase = low_pivot_idx > high_pivot_idx

    left_window = frame.iloc[:-60] if len(frame) > 60 else frame.iloc[:-1]
    if left_window.empty:
        left_window = frame.iloc[:-1]
    if left_window.empty:
        left_window = frame
    max_vol_idx = left_window["vol"].astype(float).idxmax()
    v_value = float(frame.loc[max_vol_idx, "open"])
    n_value = float(latest["open"])
    pct_vol_change = None
    if len(frame) >= 2:
        prev_vol = float(frame["vol"].iloc[-2])
        if prev_vol > 0:
            pct_vol_change = float(frame["vol"].iloc[-1]) / prev_vol - 1.0
    is_bearish = float(latest["close"]) < float(latest["open"])
    is_bullish = float(latest["close"]) > float(latest["open"])
    volume_up = pct_vol_change is not None and pct_vol_change >= 0.1
    volume_strong = pct_vol_change is not None and pct_vol_change >= 0.2

    zone = "neutral"
    score = 0.0
    if weak_phase:
        if v_value > p_value:
            if n_value < p_value * 0.95:
                zone = "opportunity"
                score = 1.5
            elif p_value * 0.95 <= n_value < p_value:
                zone = "risk" if not volume_up else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            elif p_value <= n_value < p_value * 1.05:
                zone = "risk" if volume_up and is_bearish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            elif p_value * 1.05 <= n_value < v_value * 0.95:
                zone = "opportunity"
                score = 1.0
            elif v_value * 0.95 <= n_value < v_value:
                zone = "opportunity" if volume_strong else "risk"
                score = 1.0 if zone == "opportunity" else -1.0
            elif v_value <= n_value < v_value * 1.05:
                zone = "risk" if volume_up and is_bearish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            else:
                zone = "opportunity"
                score = 1.0
        else:
            if n_value < v_value * 0.95:
                zone = "opportunity"
                score = 1.5
            elif v_value * 0.95 <= n_value < v_value:
                zone = "opportunity" if volume_strong else "risk"
                score = 1.0 if zone == "opportunity" else -1.0
            elif v_value <= n_value < p_value * 0.95:
                zone = "risk" if volume_up and is_bearish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            elif p_value * 0.95 <= n_value < p_value:
                zone = "opportunity" if volume_up else "risk"
                score = 1.0 if zone == "opportunity" else -1.0
            elif p_value <= n_value < p_value * 1.05:
                zone = "risk" if volume_up and is_bearish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            else:
                zone = "neutral"
                score = 0.0
    else:
        if v_value < p_value:
            if n_value < v_value * 0.95:
                zone = "opportunity" if volume_strong else "risk"
                score = 1.0 if zone == "opportunity" else -1.0
            elif v_value * 0.95 <= n_value < v_value:
                zone = "risk" if volume_up and is_bullish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            elif v_value <= n_value < p_value * 0.95:
                zone = "opportunity" if volume_up else "risk"
                score = 1.0 if zone == "opportunity" else -1.0
            elif p_value * 0.95 <= n_value < p_value:
                zone = "risk" if volume_up and is_bullish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            else:
                zone = "neutral"
                score = 0.0
        else:
            if n_value < p_value * 0.95:
                zone = "risk"
                score = -1.5
            elif p_value * 0.95 <= n_value < p_value:
                zone = "risk" if volume_up and is_bullish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            elif p_value <= n_value < p_value * 1.05:
                zone = "opportunity" if volume_up and is_bullish else "risk"
                score = 1.0 if zone == "opportunity" else -1.0
            elif p_value * 1.05 <= n_value < v_value * 0.95:
                zone = "risk"
                score = -1.0
            elif v_value * 0.95 <= n_value < v_value:
                zone = "risk" if volume_up and is_bullish else "opportunity"
                score = -1.0 if zone == "risk" else 1.0
            elif v_value <= n_value < v_value * 1.05:
                zone = "opportunity" if volume_up and is_bullish else "risk"
                score = 1.0 if zone == "opportunity" else -1.0
            else:
                zone = "neutral"
                score = 0.0

    return {
        "phase": "weak_box" if weak_phase else "strong_box",
        "zone": zone,
        "score": score,
        "P": round(p_value, 3),
        "V": round(v_value, 3),
        "N": round(n_value, 3),
        "Q": "low_first" if weak_phase else "high_first",
        "volume_up": volume_up,
    }


def _trend_component(frame: pd.DataFrame) -> dict[str, object]:
    latest = frame.iloc[-1]
    prev = frame.iloc[-2]
    bbi_slope_up = float(latest["bbi"]) > float(prev["bbi"])
    ma25_slope_up = pd.notna(latest["ma25"]) and pd.notna(prev["ma25"]) and float(latest["ma25"]) > float(prev["ma25"])
    ma60_slope_up = pd.notna(latest["ma60"]) and pd.notna(prev["ma60"]) and float(latest["ma60"]) > float(prev["ma60"])
    close_above_zxdkx = pd.notna(latest["zxdkx"]) and float(latest["close"]) > float(latest["zxdkx"])
    ma25_above_ma60 = pd.notna(latest["ma25"]) and pd.notna(latest["ma60"]) and float(latest["ma25"]) > float(latest["ma60"])
    dual_up = bool(ma25_slope_up and ma60_slope_up)
    dual_down = bool((not ma25_slope_up) and (not ma60_slope_up))

    if bbi_slope_up and not close_above_zxdkx and not ma25_above_ma60 and dual_down:
        state, score = "S1_weak_to_strong_initial", 0.5
    elif bbi_slope_up and close_above_zxdkx and not ma25_above_ma60 and dual_down:
        state, score = "S2_weak_to_strong_follow", 1.0
    elif bbi_slope_up and close_above_zxdkx and not ma25_above_ma60 and ma25_slope_up and not dual_up:
        state, score = "S3_weak_to_strong_strengthen", 2.0
    elif bbi_slope_up and close_above_zxdkx and not ma25_above_ma60 and dual_up:
        state, score = "S4_near_strong", 3.0
    elif bbi_slope_up and close_above_zxdkx and ma25_above_ma60 and dual_up:
        state, score = "S5_strong", 4.0
    elif (not bbi_slope_up) and close_above_zxdkx and ma25_above_ma60 and dual_up:
        state, score = "S6_strong_to_weak_initial", -1.0
    elif (not bbi_slope_up) and close_above_zxdkx and ma25_above_ma60 and (not ma25_slope_up):
        state, score = "S7_strong_to_weak_accelerating", -2.0
    elif (not bbi_slope_up) and close_above_zxdkx and (not ma25_above_ma60) and (not ma25_slope_up):
        state, score = "S8_fast_weakening", -3.0
    elif (not bbi_slope_up) and (not close_above_zxdkx) and (not ma25_above_ma60) and not dual_down:
        state, score = "S9_risk_increasing", -4.0
    elif (not bbi_slope_up) and (not close_above_zxdkx) and (not ma25_above_ma60) and dual_down:
        state, score = "S10_weak", -5.0
    else:
        state, score = "Sx_mixed", 0.0

    return {
        "state": state,
        "score": score,
        "bbi_slope": "up" if bbi_slope_up else "down",
        "close_vs_zxdkx": "above" if close_above_zxdkx else "below",
        "ma25_vs_ma60": "above" if ma25_above_ma60 else "below",
        "ma25_slope": "up" if ma25_slope_up else "down",
        "ma60_slope": "up" if ma60_slope_up else "down",
    }


def _macd_component(frame: pd.DataFrame) -> dict[str, object]:
    latest = frame.iloc[-1]
    prev = frame.iloc[-2]
    dif = float(latest["dif"])
    dea = float(latest["dea"])
    hist = float(latest["hist"])
    prev_hist = float(prev["hist"])
    dea_up = dea > float(prev["dea"])
    golden_cross = bool(latest["golden_cross"])
    death_cross = bool(latest["death_cross"])
    hist_abs_up = abs(hist) > abs(prev_hist)
    hist_shrinking = abs(hist) < abs(prev_hist)
    hist_shrink_streak = int(latest["hist_shrink_streak"]) if "hist_shrink_streak" in latest else 1

    dif_down = dif < float(prev["dif"])
    if "bars_since_golden_cross" in latest and pd.notna(latest["bars_since_golden_cross"]):
        bars_since_golden_cross = int(latest["bars_since_golden_cross"])
    else:
        bars_since_golden_cross = _infer_bars_since_golden_cross(frame)

    if dea < 0 and not dea_up and hist < 0 and hist_abs_up:
        state, score = "M1_deep_pullback", -4.0
    elif dea < 0 and not dea_up and hist < 0 and hist_shrinking:
        state, score = "M2_bottom_divergence_setup", -1.0
    elif dea < 0 and dea_up and golden_cross:
        state, score = "M3_underwater_golden_cross", 4.0
    elif (
        dea < 0
        and dea_up
        and hist > 0
        and dif > dea
        and hist_abs_up
        and bars_since_golden_cross is not None
        and bars_since_golden_cross <= _UNDERWATER_ADVANCE_MAX_BARS_SINCE_CROSS
    ):
        state, score = "M5_underwater_advance", 4.0
    elif dea < 0 and dea_up and hist < 0 and dif > dea:
        state, score = "M4_repair_extension", 2.0
    elif dea > 0 and dea_up and hist > 0 and hist_abs_up:
        state, score = "M12_primary_advance", 4.5
    elif dea > 0 and dea_up and hist > 0 and hist_shrinking and hist_shrink_streak <= 2:
        state, score = "M12_primary_advance", 4.5
    elif dea > 0 and hist > 0 and hist_shrinking and hist_shrink_streak >= 4 and dif_down:
        state, score = "M7_uptrend_exhausting", -1.0
    elif dea > 0 and dea_up and hist > 0 and hist_shrinking and hist_shrink_streak >= 3:
        state, score = "M6_top_divergence_setup", 1.0
    elif dea > 0 and not dea_up and hist > 0 and hist_shrinking:
        state, score = "M7_uptrend_exhausting", -1.0
    elif dea > 0 and death_cross:
        state, score = "M8_above_water_dead_cross", -2.5
    elif dea > 0 and not dea_up and hist < 0:
        state, score = "M9_pullback", -3.0
    elif dea < 0 and dea_up and hist < 0:
        state, score = "M11_repairing", 1.0
    else:
        state, score = "Mx_mixed", 0.0

    return {
        "state": state,
        "score": score,
        "golden_cross": golden_cross,
        "death_cross": death_cross,
        "dea_sign": "above_zero" if dea > 0 else "below_zero",
        "dea_trend": "up" if dea_up else "down",
        "hist_trend": "expand" if hist_abs_up else "shrink",
    }


def _infer_bars_since_golden_cross(frame: pd.DataFrame) -> int | None:
    if "golden_cross" not in frame:
        return None
    flags = frame["golden_cross"].astype(bool).tolist()
    for offset, flag in enumerate(reversed(flags)):
        if flag:
            return offset
    return None


def _component_state_hint(*, box_score: float, trend_score: float, macd_score: float) -> str:
    total = box_score + trend_score + macd_score
    if macd_score >= 4.0 and trend_score >= 2.0:
        return "strong"
    if macd_score <= -2.5 and trend_score <= -2.0:
        return "weak"
    return "neutral"


def _score_based_environment_state(*, combined_total: float) -> str:
    if combined_total >= _SCORE_BASED_STRONG_THRESHOLD:
        return "strong"
    if combined_total <= _SCORE_BASED_WEAK_THRESHOLD:
        return "weak"
    return "neutral"


def _score_based_raw_environment_state(
    *,
    combined_total: float,
    sse_monthly_bias: dict[str, object],
    cn2000_monthly_bias: dict[str, object],
) -> str:
    state = _score_based_environment_state(combined_total=combined_total)
    monthly_biases = {str(sse_monthly_bias["bias"]), str(cn2000_monthly_bias["bias"])}
    if state == "strong" and "negative" in monthly_biases:
        return "neutral"
    return state


def _diagnostic_macd_environment_state(score: dict[str, object]) -> str:
    macd_state = str(score["macd"]["state"])
    trend_state = str(score["trend"]["state"])
    box_zone = str(score["box_volume"]["zone"])
    trend_weak = trend_state in _WEAK_TREND_STATES
    risk_box = box_zone == "risk"

    if macd_state in _STRONG_MACD_STATES:
        return "strong"
    if macd_state == "M7_uptrend_exhausting":
        return "neutral"
    if macd_state in {"M8_above_water_dead_cross", "M9_pullback"}:
        return "weak" if trend_weak or risk_box else "neutral"
    return "neutral"


def _diagnostic_trend_environment_state(score: dict[str, object]) -> str:
    trend_state = str(score["trend"]["state"])
    if trend_state in _STRONG_TREND_STATES:
        return "strong"
    if trend_state in _WEAK_TREND_STATES:
        return "weak"
    return "neutral"


def _diagnostic_box_environment_state(score: dict[str, object]) -> str:
    zone = str(score["box_volume"]["zone"])
    box_score = float(score["box_volume"]["score"])
    if zone == "risk" or box_score < 0:
        return "weak"
    if zone == "opportunity" and box_score > 0:
        return "strong"
    return "neutral"


def _vote_based_environment_state(*, sse_score: dict[str, object], cn2000_score: dict[str, object]) -> str:
    votes = {"strong": 0, "neutral": 0, "weak": 0}
    for score in (sse_score, cn2000_score):
        for state in (
            _diagnostic_box_environment_state(score),
            _diagnostic_trend_environment_state(score),
            _diagnostic_macd_environment_state(score),
        ):
            votes[state] += 1
    if votes["strong"] > votes["neutral"] and votes["strong"] > votes["weak"]:
        return "strong"
    if votes["weak"] > votes["neutral"] and votes["weak"] > votes["strong"]:
        return "weak"
    return "neutral"


def _combine_environment_state(*, sse_score: dict[str, object], cn2000_score: dict[str, object]) -> str:
    sse_hint = _classify_index_environment(sse_score)
    small_hint = _classify_index_environment(cn2000_score)
    sse_macd = str(sse_score["macd"]["state"])
    small_macd = str(cn2000_score["macd"]["state"])
    if "strong" in {sse_hint, small_hint} and "weak" not in {sse_hint, small_hint}:
        return "strong"
    if sse_hint == "weak" and small_hint == "weak":
        return "weak"
    if sse_macd == "M7_uptrend_exhausting" and small_macd == "M7_uptrend_exhausting":
        return "weak"
    if sse_hint == "weak" and sse_macd != "M7_uptrend_exhausting" and small_hint != "strong":
        return "weak"
    if small_hint == "weak" and small_macd != "M7_uptrend_exhausting" and sse_hint != "strong":
        return "weak"
    return "neutral"


def _classify_index_environment(score: dict[str, object]) -> str:
    trend_state = str(score["trend"]["state"])
    macd_state = str(score["macd"]["state"])
    box_zone = str(score["box_volume"]["zone"])

    if macd_state in _STRONG_MACD_STATES and trend_state not in _WEAK_TREND_STATES:
        return "strong"
    if macd_state in _WEAK_MACD_STATES:
        return "weak"
    if trend_state in _WEAK_TREND_STATES and macd_state not in _REPAIR_MACD_STATES:
        return "weak"
    if macd_state in _REPAIR_MACD_STATES:
        return "neutral"
    if trend_state in _STRONG_TREND_STATES:
        return "neutral"
    if box_zone == "risk" and trend_state in _WEAK_TREND_STATES:
        return "weak"
    return "neutral"
