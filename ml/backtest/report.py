from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def _jsonable(value: Any) -> Any:
    import pandas as pd

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    try:
        missing = pd.isna(value)
        if not hasattr(missing, "__len__") and bool(missing):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def build_report(result: Any) -> dict[str, Any]:
    import pandas as pd

    metrics = getattr(result, "metrics", {})
    if isinstance(metrics, pd.DataFrame):
        metrics = metrics["value"].to_dict() if "value" in metrics.columns else metrics.to_dict()
    elif isinstance(metrics, dict):
        metrics = dict(metrics)
    else:
        metrics_frame = getattr(result, "metrics_df", None)
        if isinstance(metrics_frame, pd.DataFrame):
            metrics = (
                metrics_frame["value"].to_dict()
                if "value" in metrics_frame.columns
                else metrics_frame.to_dict()
            )
        else:
            metrics = {}
    equity = getattr(result, "equity_curve", pd.Series(dtype=float))
    equity_rows = [{"timestamp": _jsonable(index), "equity": float(value)} for index, value in equity.items()]
    cash = getattr(result, "cash_curve", pd.Series(dtype=float))
    cash_rows = [{"timestamp": _jsonable(index), "cash": float(value)} for index, value in cash.items()]
    orders = getattr(result, "orders_df", pd.DataFrame())
    trades = getattr(result, "trades_df", pd.DataFrame())
    strategy = getattr(result, "strategy", None)
    if hasattr(strategy, "open_batches"):
        metrics["open_batch_count"] = len(strategy.open_batches)
    actions = []
    for day, action in getattr(strategy, "action_history", []):
        actions.append({
            "date": day,
            "enter": list(action.enter),
            "exit": list(action.exit),
            "holding_day": action.holding_day,
            "reason": action.reason,
            "expired_signal_dates": list(action.expired_signal_dates),
            "entry_decision": asdict(action.entry_decision) if action.entry_decision is not None else None,
        })

    def records(method: str, **kwargs: Any) -> list[dict[str, Any]]:
        callback = getattr(result, method, None)
        if not callable(callback):
            return []
        frame = callback(**kwargs)
        return frame.to_dict(orient="records")

    return _jsonable({
        "metrics": _jsonable(metrics),
        "equity_curve": equity_rows,
        "cash_curve": cash_rows,
        "orders": orders.to_dict(orient="records") if isinstance(orders, pd.DataFrame) else [],
        "trades": trades.to_dict(orient="records") if isinstance(trades, pd.DataFrame) else [],
        "actions": actions,
        "strategy_config": getattr(strategy, "strategy_config", {}),
        "daily_budgets": getattr(strategy, "daily_budgets", []),
        "exit_events": getattr(strategy, "exit_events", []),
        "unfilled_entries": getattr(strategy, "unfilled_entries", []),
        "open_batches": getattr(strategy, "open_batches", []),
        "diagnostics": {
            "exposure": records("exposure_df"),
            "attribution_by_symbol": records("attribution_df", by="symbol"),
            "attribution_by_signal_date": records("attribution_df", by="entry_tag"),
            "attribution_by_environment": _environment_attribution(trades, actions),
        },
    })


def _environment_attribution(trades: Any, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import pandas as pd

    environments = {
        action["date"]: action["entry_decision"]["environment"]
        for action in actions if action["entry_decision"] and action["entry_decision"]["environment"]
    }
    if not environments or not isinstance(trades, pd.DataFrame) or trades.empty:
        return []
    frame = trades.copy()
    frame["group"] = frame["entry_tag"].map(environments).fillna("unknown")
    frame["net_win"] = frame["net_pnl"] > 0
    return frame.groupby("group", as_index=False).agg(
        trade_count=("net_pnl", "count"), total_pnl=("net_pnl", "sum"),
        avg_return_pct=("return_pct", "mean"), net_win_rate=("net_win", "mean"),
    ).to_dict(orient="records")


def write_report(result: Any, output: Path) -> dict[str, Any]:
    report = build_report(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_jsonable(report), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return report
