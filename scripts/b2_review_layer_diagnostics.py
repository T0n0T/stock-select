# /// script
# dependencies = [
#   "psycopg[binary]",
# ]
# ///
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "diagnostics" / "b2_review_layer"
DEFAULT_METHOD = "b2"
DEFAULT_START_DATE = "2026-03-01"
DEFAULT_END_DATE = "2026-05-29"
FEATURE_COLUMNS = [
    "date",
    "code",
    "name",
    "env",
    "current_verdict",
    "baseline_verdict",
    "current_score",
    "baseline_score",
    "ret3",
    "ret5",
    "ret3_bucket",
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "macd_phase",
    "signal",
    "signal_type",
    "daily_macd_phase_type",
    "daily_macd_wave_index",
    "daily_macd_wave_stage",
    "daily_macd_rising_or_falling",
    "daily_macd_bottom_divergence",
    "daily_macd_top_divergence",
    "weekly_macd_phase_type",
    "weekly_macd_wave_index",
    "weekly_macd_wave_stage",
    "weekly_macd_bottom_divergence",
    "weekly_macd_top_divergence",
    "weekly_daily_combo_type",
    "price_vs_90d_high",
    "price_vs_90d_low",
    "price_vs_90d_mid",
    "midline_state",
    "midline_breakout_volume_ratio",
    "breakout_above_90d_mid_with_volume",
    "pullback_confirm_vs_90d_mid",
    "close_vs_ma25",
    "close_vs_ma60",
    "ma25_vs_ma60",
    "ma25_slope_5d",
    "ma60_slope_5d",
    "support_stack_type",
    "range_compression_20d",
    "range_compression_40d",
    "days_since_last_high",
    "days_since_last_low",
    "volume_ratio_5d",
    "volume_ratio_10d",
    "turnover_rate",
    "turnover_rate_ratio_5d",
    "daily_pct_chg",
    "daily_macd_hist",
    "daily_macd_hist_prev",
    "daily_macd_hist_state",
    "price_up_1d",
    "turnover_up_1d",
    "price_turnover_state",
    "k_value",
    "d_value",
    "j_value",
    "j_vs_k",
    "j_vs_d",
    "j_overheat",
    "j_repair_from_low",
    "bbi_bfq",
    "close_vs_bbi",
    "bbi_bias_state",
    "bias1_bfq",
    "bias2_bfq",
    "bias3_bfq",
    "bias_bucket",
    "obv_bfq",
    "obv_ratio_5d",
    "obv_state",
]


def load_dotenv_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        candidate_key, candidate_value = line.split("=", 1)
        if candidate_key.strip() != key:
            continue
        value = candidate_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def resolve_dsn(cli_dsn: str | None) -> str:
    for value in (cli_dsn, os.getenv("POSTGRES_DSN"), load_dotenv_value(PROJECT_ROOT / ".env", "POSTGRES_DSN")):
        if value and value.strip():
            return value.strip()
    raise ValueError("A database DSN is required.")


def ret3_bucket(ret3: float | None) -> str:
    if ret3 is None:
        return ""
    if ret3 >= 10.0:
        return "A"
    if ret3 >= 5.0:
        return "B"
    if ret3 > 0.0:
        return "C"
    if ret3 > -5.0:
        return "D"
    if ret3 > -10.0:
        return "E"
    return "F"


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def rounded(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0.0:
        return None
    return (current / base - 1.0) * 100.0


def normalize_verdict(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text or "UNKNOWN"


def normalize_env(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"weak", "neutral", "strong"} else "unknown"


def field(source: dict[str, Any], key: str) -> Any:
    return source.get(key)


def optional_field(source: dict[str, Any], key: str) -> Any:
    if key not in source or source[key] is None:
        return ""
    return source[key]


def first_present(source: dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def extract_feature_row(
    *,
    pick_date: str,
    code: str,
    env: str,
    review: dict[str, Any],
    forward: dict[str, float | None],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline = review.get("baseline_review")
    if not isinstance(baseline, dict):
        baseline = review
    current_score = as_float(first_present(review, ("total_score", "score")))
    baseline_score = as_float(first_present(baseline, ("total_score", "score")))
    ret3 = rounded(forward.get("ret3"))
    ret5 = rounded(forward.get("ret5"))
    row = {
        "date": pick_date,
        "code": code,
        "name": review.get("name") or baseline.get("name") or "",
        "env": normalize_env(env),
        "current_verdict": normalize_verdict(review.get("verdict") or baseline.get("verdict")),
        "baseline_verdict": normalize_verdict(baseline.get("verdict")),
        "current_score": rounded(current_score),
        "baseline_score": rounded(baseline_score),
        "ret3": ret3,
        "ret5": ret5,
        "ret3_bucket": ret3_bucket(ret3),
        "trend_structure": rounded(as_float(field(baseline, "trend_structure"))),
        "price_position": rounded(as_float(field(baseline, "price_position"))),
        "volume_behavior": rounded(as_float(field(baseline, "volume_behavior"))),
        "previous_abnormal_move": rounded(as_float(field(baseline, "previous_abnormal_move"))),
        "macd_phase": rounded(as_float(field(baseline, "macd_phase"))),
        "signal": review.get("signal") or baseline.get("signal") or "",
        "signal_type": review.get("signal_type") or baseline.get("signal_type") or "",
        "daily_macd_phase_type": optional_field(baseline, "daily_macd_phase_type"),
        "daily_macd_wave_index": optional_field(baseline, "daily_macd_wave_index"),
        "daily_macd_wave_stage": optional_field(baseline, "daily_macd_wave_stage"),
        "daily_macd_rising_or_falling": optional_field(baseline, "daily_macd_rising_or_falling"),
        "daily_macd_bottom_divergence": optional_field(baseline, "daily_macd_bottom_divergence"),
        "daily_macd_top_divergence": optional_field(baseline, "daily_macd_top_divergence"),
        "weekly_macd_phase_type": optional_field(baseline, "weekly_macd_phase_type"),
        "weekly_macd_wave_index": optional_field(baseline, "weekly_macd_wave_index"),
        "weekly_macd_wave_stage": optional_field(baseline, "weekly_macd_wave_stage"),
        "weekly_macd_bottom_divergence": optional_field(baseline, "weekly_macd_bottom_divergence"),
        "weekly_macd_top_divergence": optional_field(baseline, "weekly_macd_top_divergence"),
        "weekly_daily_combo_type": optional_field(baseline, "weekly_daily_combo_type"),
    }
    if context:
        row.update(context)
    return row


def load_environment_by_date(runtime_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    daily_dir = runtime_root / "environment" / "daily"
    if not daily_dir.exists():
        return result
    for path in sorted(daily_dir.glob("????-??-??.*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        pick_date = str(payload.get("pick_date") or path.name[:10])
        result[pick_date] = normalize_env(payload.get("state"))
    return result


def env_from_summary(summary: dict[str, Any], fallback: str) -> str:
    snapshot = summary.get("environment_snapshot")
    if isinstance(snapshot, dict):
        state = normalize_env(snapshot.get("state"))
        if state != "unknown":
            return state
    return normalize_env(fallback)


def review_dirs(runtime_root: Path, method: str, start_date: str, end_date: str) -> list[Path]:
    root = runtime_root / "reviews"
    if not root.exists():
        return []
    dirs = []
    for path in sorted(root.glob(f"????-??-??.{method}")):
        pick_date = path.name.removesuffix(f".{method}")
        if start_date <= pick_date <= end_date:
            dirs.append(path)
    return dirs


def load_reviews_for_dir(review_dir: Path) -> list[dict[str, Any]]:
    reviews = []
    for path in sorted(review_dir.glob("*.json")):
        if path.name in {"summary.json", "llm_review_tasks.json"}:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            reviews.append(payload)
    return reviews


def collect_runtime_symbols(runtime_root: Path, method: str, start_date: str, end_date: str) -> list[str]:
    symbols: set[str] = set()
    for review_dir in review_dirs(runtime_root, method, start_date, end_date):
        for review in load_reviews_for_dir(review_dir):
            code = str(review.get("code") or "").strip()
            if code:
                symbols.add(code)
    return sorted(symbols)


def fetch_price_rows(dsn: str, symbols: Sequence[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    import psycopg

    if not symbols:
        return {}
    query = """
        SELECT ts_code, trade_date, close::double precision AS close
             , open::double precision AS open
             , high::double precision AS high
             , low::double precision AS low
             , vol::double precision AS vol
             , amount::double precision AS amount
             , turnover_rate::double precision AS turnover_rate
             , pct_chg::double precision AS pct_chg
        FROM daily_market
        WHERE ts_code = ANY(%s)
          AND trade_date >= %s
          AND trade_date <= %s
          AND close IS NOT NULL
        ORDER BY ts_code ASC, trade_date ASC
    """
    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (list(symbols), start_date, end_date))
            for ts_code, trade_date, close, open_, high, low, vol, amount, turnover_rate, pct_chg in cursor.fetchall():
                parsed_close = as_float(close)
                if parsed_close is None:
                    continue
                rows_by_symbol[str(ts_code)].append(
                    {
                        "trade_date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
                        "close": parsed_close,
                        "open": as_float(open_),
                        "high": as_float(high),
                        "low": as_float(low),
                        "vol": as_float(vol),
                        "amount": as_float(amount),
                        "turnover_rate": as_float(turnover_rate),
                        "pct_chg": as_float(pct_chg),
                    }
                )
    return dict(rows_by_symbol)


def fetch_indicator_rows(dsn: str, symbols: Sequence[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    import psycopg

    if not symbols:
        return {}
    query = """
        SELECT ts_code, trade_date
             , (extra_factors_jsonb->>'bbi_bfq')::double precision AS bbi_bfq
             , (extra_factors_jsonb->>'bias1_bfq')::double precision AS bias1_bfq
             , (extra_factors_jsonb->>'bias2_bfq')::double precision AS bias2_bfq
             , (extra_factors_jsonb->>'bias3_bfq')::double precision AS bias3_bfq
             , (extra_factors_jsonb->>'obv_bfq')::double precision AS obv_bfq
        FROM daily_indicators
        WHERE ts_code = ANY(%s)
          AND trade_date >= %s
          AND trade_date <= %s
          AND extra_factors_jsonb IS NOT NULL
        ORDER BY ts_code ASC, trade_date ASC
    """
    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (list(symbols), start_date, end_date))
            for ts_code, trade_date, bbi_bfq, bias1_bfq, bias2_bfq, bias3_bfq, obv_bfq in cursor.fetchall():
                rows_by_symbol[str(ts_code)].append(
                    {
                        "trade_date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
                        "bbi_bfq": as_float(bbi_bfq),
                        "bias1_bfq": as_float(bias1_bfq),
                        "bias2_bfq": as_float(bias2_bfq),
                        "bias3_bfq": as_float(bias3_bfq),
                        "obv_bfq": as_float(obv_bfq),
                    }
                )
    return dict(rows_by_symbol)


def merge_indicator_rows(
    price_rows: dict[str, list[dict[str, Any]]],
    indicator_rows: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    if not indicator_rows:
        return price_rows
    result: dict[str, list[dict[str, Any]]] = {}
    for symbol, rows in price_rows.items():
        indicators = {str(row.get("trade_date")): row for row in indicator_rows.get(symbol, [])}
        merged = []
        for row in rows:
            indicator = indicators.get(str(row.get("trade_date")), {})
            merged.append({**row, **{key: value for key, value in indicator.items() if key != "trade_date"}})
        result[symbol] = merged
    return result


def forward_returns(price_rows: Sequence[dict[str, Any]], pick_date: str) -> dict[str, float | None]:
    history = sorted(
        (row for row in price_rows if as_float(row.get("close")) is not None),
        key=lambda row: str(row.get("trade_date")),
    )
    current = [row for row in history if str(row.get("trade_date")) <= pick_date]
    if not current:
        return {"ret3": None, "ret5": None}
    entry_close = as_float(current[-1].get("close"))
    if entry_close is None or entry_close == 0.0:
        return {"ret3": None, "ret5": None}
    future = [row for row in history if str(row.get("trade_date")) > pick_date]

    def ret_at(index: int) -> float | None:
        if len(future) <= index:
            return None
        close = as_float(future[index].get("close"))
        if close is None:
            return None
        return (close / entry_close - 1.0) * 100.0

    return {"ret3": ret_at(2), "ret5": ret_at(4)}


def rolling_mean(values: Sequence[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def slope_pct(values: Sequence[float], window: int) -> float | None:
    if len(values) <= window:
        return None
    return pct_change(values[-1], values[-1 - window])


def days_since_tail_extreme(values: Sequence[float], *, high: bool) -> int | None:
    if not values:
        return None
    target = max(values) if high else min(values)
    for offset, value in enumerate(reversed(values)):
        if value == target:
            return offset
    return None


def compute_kdj(close: Sequence[float], high: Sequence[float], low: Sequence[float]) -> dict[str, float | None]:
    if not close or not high or not low:
        return {"k_value": None, "d_value": None, "j_value": None}
    k = 50.0
    d = 50.0
    for idx, latest_close in enumerate(close):
        start = max(0, idx - 8)
        low_n = min(low[start : idx + 1])
        high_n = max(high[start : idx + 1])
        rsv = 50.0 if high_n == low_n else (latest_close - low_n) / (high_n - low_n) * 100.0
        k = k * 2.0 / 3.0 + rsv / 3.0
        d = d * 2.0 / 3.0 + k / 3.0
    j = 3.0 * k - 2.0 * d
    return {"k_value": k, "d_value": d, "j_value": j}


def ema_values(values: Sequence[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def compute_macd_hist(close: Sequence[float]) -> list[float]:
    if not close:
        return []
    ema12 = ema_values(close, 12)
    ema26 = ema_values(close, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26)]
    dea = ema_values(dif, 9)
    return [d - e for d, e in zip(dif, dea)]


def macd_hist_state(latest: float | None, previous: float | None) -> str:
    if latest is None:
        return "unknown"
    if latest <= 0.0:
        return "green_or_zero"
    if previous is not None and latest > previous:
        return "red_expanding"
    return "red_contracting"


def price_turnover_state(price_up: bool | None, turnover_up: bool | None) -> str:
    if price_up and turnover_up:
        return "price_turnover_rise"
    if price_up is False and turnover_up:
        return "turnover_up_price_not"
    if price_up and turnover_up is False:
        return "price_up_turnover_not"
    return "mixed"


def bbi_bias_state(close: float | None, bbi: float | None) -> str:
    diff = pct_change(close, bbi)
    if diff is None:
        return "unknown"
    if diff >= 3.0:
        return "above_extended"
    if diff >= 0.0:
        return "above"
    if diff >= -3.0:
        return "below_near"
    return "below_deep"


def bias_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 8.0:
        return "high_positive"
    if value >= 3.0:
        return "positive"
    if value > -3.0:
        return "neutral"
    if value > -8.0:
        return "negative"
    return "deep_negative"


def obv_state(latest: float | None, ratio_5d: float | None) -> str:
    if latest is None:
        return "unknown"
    if ratio_5d is None:
        return "known"
    if ratio_5d >= 1.05:
        return "rising"
    if ratio_5d <= 0.95:
        return "falling"
    return "flat"


def support_stack_type(close: float | None, ma25: float | None, ma60: float | None) -> str:
    if close is None:
        return "unknown"
    if ma25 is not None and ma60 is not None:
        if close >= ma25 >= ma60:
            return "bull_stack"
        if close >= ma25:
            return "close_above_ma25"
        if close >= ma60:
            return "close_above_ma60"
        return "below_ma25_ma60"
    if ma25 is not None:
        return "close_above_ma25" if close >= ma25 else "below_ma25"
    if ma60 is not None:
        return "close_above_ma60" if close >= ma60 else "below_ma60"
    return "unknown"


def classify_midline_state(
    *,
    latest_close: float | None,
    previous_close: float | None,
    latest_low: float | None,
    mid_90: float | None,
    volume_ratio_5d: float | None,
) -> dict[str, Any]:
    if latest_close is None or mid_90 is None:
        return {
            "midline_state": "unknown",
            "midline_breakout_volume_ratio": None,
            "breakout_above_90d_mid_with_volume": False,
            "pullback_confirm_vs_90d_mid": False,
        }
    breakout_with_volume = bool(
        previous_close is not None
        and previous_close <= mid_90
        and latest_close > mid_90
        and volume_ratio_5d is not None
        and volume_ratio_5d >= 1.30
    )
    pullback_confirm = bool(
        latest_low is not None
        and latest_close >= mid_90
        and latest_low <= mid_90 * 1.02
        and latest_low >= mid_90 * 0.97
    )
    if breakout_with_volume:
        state = "reclaim_volume"
    elif pullback_confirm:
        state = "pullback_confirm"
    elif latest_close >= mid_90:
        state = "above_hold"
    else:
        state = "below_midline"
    return {
        "midline_state": state,
        "midline_breakout_volume_ratio": rounded(volume_ratio_5d),
        "breakout_above_90d_mid_with_volume": breakout_with_volume,
        "pullback_confirm_vs_90d_mid": pullback_confirm,
    }


def compute_context_features(price_rows: Sequence[dict[str, Any]], pick_date: str) -> dict[str, Any]:
    history = [
        row
        for row in sorted(price_rows, key=lambda item: str(item.get("trade_date")))
        if str(row.get("trade_date")) <= pick_date and as_float(row.get("close")) is not None
    ]
    base = {
        "price_vs_90d_high": None,
        "price_vs_90d_low": None,
        "price_vs_90d_mid": None,
        "midline_state": "unknown",
        "midline_breakout_volume_ratio": None,
        "breakout_above_90d_mid_with_volume": False,
        "pullback_confirm_vs_90d_mid": False,
        "close_vs_ma25": None,
        "close_vs_ma60": None,
        "ma25_vs_ma60": None,
        "ma25_slope_5d": None,
        "ma60_slope_5d": None,
        "support_stack_type": "unknown",
        "range_compression_20d": None,
        "range_compression_40d": None,
        "days_since_last_high": None,
        "days_since_last_low": None,
        "volume_ratio_5d": None,
        "volume_ratio_10d": None,
        "turnover_rate": None,
        "turnover_rate_ratio_5d": None,
        "daily_pct_chg": None,
        "daily_macd_hist": None,
        "daily_macd_hist_prev": None,
        "daily_macd_hist_state": "unknown",
        "price_up_1d": None,
        "turnover_up_1d": None,
        "price_turnover_state": "unknown",
        "k_value": None,
        "d_value": None,
        "j_value": None,
        "j_vs_k": None,
        "j_vs_d": None,
        "j_overheat": None,
        "j_repair_from_low": None,
        "bbi_bfq": None,
        "close_vs_bbi": None,
        "bbi_bias_state": "unknown",
        "bias1_bfq": None,
        "bias2_bfq": None,
        "bias3_bfq": None,
        "bias_bucket": "unknown",
        "obv_bfq": None,
        "obv_ratio_5d": None,
        "obv_state": "unknown",
    }
    if not history:
        return base

    close = [as_float(row.get("close")) for row in history]
    high = [as_float(row.get("high")) for row in history]
    low = [as_float(row.get("low")) for row in history]
    volume = [as_float(row.get("vol")) for row in history]
    turnover = [as_float(row.get("turnover_rate")) for row in history]
    pct_chg = [as_float(row.get("pct_chg")) for row in history]
    bbi_values = [as_float(row.get("bbi_bfq")) for row in history]
    bias1_values = [as_float(row.get("bias1_bfq")) for row in history]
    bias2_values = [as_float(row.get("bias2_bfq")) for row in history]
    bias3_values = [as_float(row.get("bias3_bfq")) for row in history]
    obv_values = [as_float(row.get("obv_bfq")) for row in history]
    if any(value is None for value in close):
        return base
    close_values = [float(value) for value in close if value is not None]
    high_values = [float(value) for value in high if value is not None]
    low_values = [float(value) for value in low if value is not None]
    volume_values = [float(value) for value in volume if value is not None]
    turnover_values = [float(value) for value in turnover if value is not None]
    latest_close = close_values[-1]
    previous_close = close_values[-2] if len(close_values) >= 2 else None
    tail_high = high_values[-90:] if high_values else []
    tail_low = low_values[-90:] if low_values else []
    high_90 = max(tail_high) if tail_high else None
    low_90 = min(tail_low) if tail_low else None
    mid_90 = (high_90 + low_90) / 2.0 if high_90 is not None and low_90 is not None else None
    ma25_series = [rolling_mean(close_values[: idx + 1], 25) for idx in range(len(close_values))]
    ma60_series = [rolling_mean(close_values[: idx + 1], 60) for idx in range(len(close_values))]
    ma25 = ma25_series[-1]
    ma60 = ma60_series[-1]
    avg5 = rolling_mean(volume_values, 5) if volume_values else None
    avg10 = rolling_mean(volume_values, 10) if volume_values else None
    latest_volume = volume_values[-1] if volume_values else None
    volume_ratio_5d = latest_volume / avg5 if latest_volume is not None and avg5 else None
    volume_ratio_10d = latest_volume / avg10 if latest_volume is not None and avg10 else None
    latest_turnover = turnover_values[-1] if turnover_values else None
    previous_turnover = turnover_values[-2] if len(turnover_values) >= 2 else None
    turnover_avg5 = rolling_mean(turnover_values, 5) if turnover_values else None
    turnover_ratio_5d = latest_turnover / turnover_avg5 if latest_turnover is not None and turnover_avg5 else None
    macd_hist = compute_macd_hist(close_values)
    latest_macd_hist = macd_hist[-1] if macd_hist else None
    previous_macd_hist = macd_hist[-2] if len(macd_hist) >= 2 else None
    price_up = (latest_close > previous_close) if previous_close is not None else None
    turnover_up = (latest_turnover > previous_turnover) if latest_turnover is not None and previous_turnover is not None else None
    kdj = compute_kdj(close_values, high_values, low_values)
    k_value = kdj["k_value"]
    d_value = kdj["d_value"]
    j_value = kdj["j_value"]
    latest_bbi = bbi_values[-1] if bbi_values and bbi_values[-1] is not None else None
    latest_bias1 = bias1_values[-1] if bias1_values and bias1_values[-1] is not None else None
    latest_bias2 = bias2_values[-1] if bias2_values and bias2_values[-1] is not None else None
    latest_bias3 = bias3_values[-1] if bias3_values and bias3_values[-1] is not None else None
    latest_obv = obv_values[-1] if obv_values and obv_values[-1] is not None else None
    obv_known = [value for value in obv_values if value is not None]
    obv_avg5 = rolling_mean(obv_known, 5) if obv_known else None
    obv_ratio = latest_obv / obv_avg5 if latest_obv is not None and obv_avg5 not in (None, 0.0) else None

    base.update(
        {
            "price_vs_90d_high": rounded(pct_change(latest_close, high_90)),
            "price_vs_90d_low": rounded(pct_change(latest_close, low_90)),
            "price_vs_90d_mid": rounded(pct_change(latest_close, mid_90)),
            **classify_midline_state(
                latest_close=latest_close,
                previous_close=previous_close,
                latest_low=low_values[-1] if low_values else None,
                mid_90=mid_90,
                volume_ratio_5d=volume_ratio_5d,
            ),
            "close_vs_ma25": rounded(pct_change(latest_close, ma25)),
            "close_vs_ma60": rounded(pct_change(latest_close, ma60)),
            "ma25_vs_ma60": rounded(pct_change(ma25, ma60)),
            "ma25_slope_5d": rounded(slope_pct([value for value in ma25_series if value is not None], 5)),
            "ma60_slope_5d": rounded(slope_pct([value for value in ma60_series if value is not None], 5)),
            "support_stack_type": support_stack_type(latest_close, ma25, ma60),
            "days_since_last_high": days_since_tail_extreme(tail_high, high=True),
            "days_since_last_low": days_since_tail_extreme(tail_low, high=False),
            "turnover_rate": rounded(latest_turnover),
            "turnover_rate_ratio_5d": rounded(turnover_ratio_5d),
            "daily_pct_chg": rounded(pct_chg[-1] if pct_chg and pct_chg[-1] is not None else pct_change(latest_close, previous_close)),
            "daily_macd_hist": rounded(latest_macd_hist),
            "daily_macd_hist_prev": rounded(previous_macd_hist),
            "daily_macd_hist_state": macd_hist_state(latest_macd_hist, previous_macd_hist),
            "price_up_1d": price_up,
            "turnover_up_1d": turnover_up,
            "price_turnover_state": price_turnover_state(price_up, turnover_up),
            "k_value": rounded(k_value),
            "d_value": rounded(d_value),
            "j_value": rounded(j_value),
            "j_vs_k": rounded((j_value - k_value) if j_value is not None and k_value is not None else None),
            "j_vs_d": rounded((j_value - d_value) if j_value is not None and d_value is not None else None),
            "j_overheat": bool(j_value is not None and j_value >= 100.0),
            "j_repair_from_low": bool(j_value is not None and k_value is not None and j_value > k_value and j_value < 50.0),
            "bbi_bfq": rounded(latest_bbi),
            "close_vs_bbi": rounded(pct_change(latest_close, latest_bbi)),
            "bbi_bias_state": bbi_bias_state(latest_close, latest_bbi),
            "bias1_bfq": rounded(latest_bias1),
            "bias2_bfq": rounded(latest_bias2),
            "bias3_bfq": rounded(latest_bias3),
            "bias_bucket": bias_bucket(latest_bias1),
            "obv_bfq": rounded(latest_obv),
            "obv_ratio_5d": rounded(obv_ratio),
            "obv_state": obv_state(latest_obv, obv_ratio),
        }
    )
    for window in (20, 40):
        tail_h = high_values[-window:]
        tail_l = low_values[-window:]
        tail_c = close_values[-window:]
        if len(tail_h) == window and len(tail_l) == window and tail_c:
            range_pct = pct_change(max(tail_h), min(tail_l))
            latest_amp = pct_change(tail_h[-1], tail_l[-1])
            base[f"range_compression_{window}d"] = rounded(
                (latest_amp / range_pct) if latest_amp is not None and range_pct not in (None, 0.0) else None
            )
    if volume_values:
        base["volume_ratio_5d"] = rounded(volume_ratio_5d)
        base["volume_ratio_10d"] = rounded(volume_ratio_10d)
    return base


def mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def median(values: Sequence[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def segment_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("env") or "unknown"),
            str(row.get("signal") or ""),
            str(row.get("signal_type") or ""),
        ]
    )


def value_or_unknown(value: Any) -> str:
    text = str(value).strip()
    return text if text else "unknown"


def macd_segment_key(row: dict[str, Any]) -> str:
    weekly = ":".join(
        [
            "W",
            value_or_unknown(row.get("weekly_macd_phase_type")),
            value_or_unknown(row.get("weekly_macd_wave_index")),
            value_or_unknown(row.get("weekly_macd_wave_stage")),
        ]
    )
    daily = ":".join(
        [
            "D",
            value_or_unknown(row.get("daily_macd_phase_type")),
            value_or_unknown(row.get("daily_macd_wave_index")),
            value_or_unknown(row.get("daily_macd_wave_stage")),
        ]
    )
    return "|".join(
        [
            str(row.get("env") or "unknown"),
            str(row.get("signal") or ""),
            str(row.get("signal_type") or ""),
            weekly,
            daily,
            value_or_unknown(row.get("weekly_daily_combo_type")),
        ]
    )


def price_position_bucket(row: dict[str, Any]) -> str:
    near_high = as_float(row.get("price_vs_90d_high"))
    above_low = as_float(row.get("price_vs_90d_low"))
    if near_high is not None:
        if near_high >= -5.0:
            return "near_high"
        if near_high >= -15.0:
            return "upper"
    if above_low is not None:
        if above_low <= 25.0:
            return "near_low"
        if above_low <= 60.0:
            return "middle"
    return "extended_or_unknown"


def compression_bucket(row: dict[str, Any]) -> str:
    compression = as_float(row.get("range_compression_20d"))
    if compression is None:
        return "unknown"
    if compression <= 0.40:
        return "tight"
    if compression <= 0.75:
        return "normal"
    return "wide"


def volume_bucket(row: dict[str, Any]) -> str:
    ratio = as_float(row.get("volume_ratio_5d"))
    if ratio is None:
        return "unknown"
    if ratio >= 1.30:
        return "expanding"
    if ratio <= 0.75:
        return "shrinking"
    return "normal"


def kdj_bucket(row: dict[str, Any]) -> str:
    j_value = as_float(row.get("j_value"))
    j_vs_d = as_float(row.get("j_vs_d"))
    if j_value is None:
        return "unknown"
    if j_value >= 100.0:
        return "overheat"
    if j_value < 20.0:
        return "low"
    if j_value < 50.0 and j_vs_d is not None and j_vs_d > 0.0:
        return "repair_from_low"
    if j_vs_d is not None and j_vs_d > 0.0:
        return "rising"
    return "neutral"


def factor_segment_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("env") or "unknown"),
            str(row.get("signal") or ""),
            str(row.get("signal_type") or ""),
            f"price={price_position_bucket(row)}",
            f"midline={value_or_unknown(row.get('midline_state'))}",
            f"support={value_or_unknown(row.get('support_stack_type'))}",
            f"compression={compression_bucket(row)}",
            f"volume={volume_bucket(row)}",
            f"kdj={kdj_bucket(row)}",
        ]
    )


def summarize_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ret3_values = [float(row["ret3"]) for row in rows if row.get("ret3") is not None]
    ret5_values = [float(row["ret5"]) for row in rows if row.get("ret5") is not None]
    verdicts = Counter(str(row.get("current_verdict") or "UNKNOWN") for row in rows)
    buckets = Counter(str(row.get("ret3_bucket") or "") for row in rows if row.get("ret3_bucket"))
    samples = sorted(
        rows,
        key=lambda row: (float(row["ret3"]) if row.get("ret3") is not None else -999.0),
        reverse=True,
    )[:8]
    return {
        "sample_count": len(rows),
        "ret3_ge_5_count": sum(1 for value in ret3_values if value >= 5.0),
        "ret3_le_0_count": sum(1 for value in ret3_values if value <= 0.0),
        "ret3_mean": mean(ret3_values),
        "ret3_median": median(ret3_values),
        "ret5_mean": mean(ret5_values),
        "ret5_median": median(ret5_values),
        "ret3_bucket_distribution": dict(sorted(buckets.items())),
        "current_verdict_distribution": dict(sorted(verdicts.items())),
        "typical_samples": [
            {
                "date": row.get("date"),
                "code": row.get("code"),
                "verdict": row.get("current_verdict"),
                "score": row.get("current_score"),
                "ret3": row.get("ret3"),
                "ret5": row.get("ret5"),
            }
            for row in samples
        ],
    }


def sample_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": row.get("date"),
        "code": row.get("code"),
        "verdict": row.get("current_verdict"),
        "score": row.get("current_score"),
        "ret3": row.get("ret3"),
        "ret5": row.get("ret5"),
        "signal": row.get("signal"),
        "signal_type": row.get("signal_type"),
        "weekly_daily_combo_type": row.get("weekly_daily_combo_type"),
        "support_stack_type": row.get("support_stack_type"),
    }


def top_segment_rows(rows: Sequence[dict[str, Any]], key_fn, *, limit: int = 10) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    ranked = sorted(
        grouped.items(),
        key=lambda item: (len(item[1]), mean([as_float(row.get("ret3")) or 0.0 for row in item[1]]) or -999.0),
        reverse=True,
    )
    return [{"segment": key, **summarize_rows(items)} for key, items in ranked[:limit]]


def build_environment_comparisons(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_env: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_env[str(row.get("env") or "unknown")].append(row)
    result: dict[str, dict[str, Any]] = {}
    for env, env_rows in sorted(by_env.items()):
        positive = [row for row in env_rows if str(row.get("ret3_bucket")) in {"A", "B"}]
        negative = [row for row in env_rows if str(row.get("ret3_bucket")) in {"D", "E", "F"}]
        a_rows = [row for row in env_rows if str(row.get("ret3_bucket")) == "A"]
        ef_rows = [row for row in env_rows if str(row.get("ret3_bucket")) in {"E", "F"}]
        b_rows = [row for row in env_rows if str(row.get("ret3_bucket")) == "B"]
        d_rows = [row for row in env_rows if str(row.get("ret3_bucket")) == "D"]
        watch_fail_high = [
            row
            for row in env_rows
            if normalize_verdict(row.get("current_verdict")) in {"WATCH", "FAIL"} and (as_float(row.get("ret3")) or -999.0) >= 5.0
        ]
        pass_negative = [
            row
            for row in env_rows
            if normalize_verdict(row.get("current_verdict")) == "PASS" and (as_float(row.get("ret3")) or 999.0) <= 0.0
        ]
        result[env] = {
            "sample_count": len(env_rows),
            "positive_group": summarize_rows(positive),
            "negative_group": summarize_rows(negative),
            "a_vs_ef": {"a": summarize_rows(a_rows), "ef": summarize_rows(ef_rows)},
            "b_vs_d": {"b": summarize_rows(b_rows), "d": summarize_rows(d_rows)},
            "positive_base_segments": top_segment_rows(positive, segment_key),
            "negative_base_segments": top_segment_rows(negative, segment_key),
            "positive_macd_segments": top_segment_rows(positive, macd_segment_key),
            "negative_macd_segments": top_segment_rows(negative, macd_segment_key),
            "positive_factor_segments": top_segment_rows(positive, factor_segment_key),
            "negative_factor_segments": top_segment_rows(negative, factor_segment_key),
            "watch_fail_high_ret3": [
                sample_brief(row)
                for row in sorted(watch_fail_high, key=lambda item: as_float(item.get("ret3")) or 0.0, reverse=True)[:30]
            ],
            "pass_negative_ret3": [
                sample_brief(row)
                for row in sorted(pass_negative, key=lambda item: as_float(item.get("ret3")) or 0.0)[:30]
            ],
        }
    return result


def build_segments(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[segment_key(row)].append(row)
    return {key: summarize_rows(items) for key, items in sorted(grouped.items())}


def build_macd_segments(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[macd_segment_key(row)].append(row)
    return {key: summarize_rows(items) for key, items in sorted(grouped.items())}


def macd_push_side(row: dict[str, Any]) -> str:
    weekly_phase = value_or_unknown(row.get("weekly_macd_phase_type"))
    daily_phase = value_or_unknown(row.get("daily_macd_phase_type"))
    weekly_wave = as_float(row.get("weekly_macd_wave_index"))
    daily_wave = as_float(row.get("daily_macd_wave_index"))
    weekly_push = weekly_phase == "rising" and weekly_wave is not None and int(weekly_wave) % 2 == 1
    daily_push = daily_phase == "rising" and daily_wave is not None and int(daily_wave) % 2 == 1
    if weekly_push and daily_push:
        return "both"
    if weekly_push:
        return "weekly"
    if daily_push:
        return "daily"
    return "none"


def macd_wave_rule_key(row: dict[str, Any]) -> str:
    weekly = ":".join(
        [
            "W",
            value_or_unknown(row.get("weekly_macd_phase_type")),
            value_or_unknown(row.get("weekly_macd_wave_index")),
            value_or_unknown(row.get("weekly_macd_wave_stage")),
        ]
    )
    daily = ":".join(
        [
            "D",
            value_or_unknown(row.get("daily_macd_phase_type")),
            value_or_unknown(row.get("daily_macd_wave_index")),
            value_or_unknown(row.get("daily_macd_wave_stage")),
        ]
    )
    return f"{weekly}|{daily}"


def macd_wave_rule_summary(
    wave_rule: str,
    rows: Sequence[dict[str, Any]],
    *,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    summary = summarize_rows(rows)
    sample_count = int(summary.get("sample_count") or 0)
    positive_count = int(summary.get("ret3_ge_5_count") or 0)
    negative_count = int(summary.get("ret3_le_0_count") or 0)
    positive_rate = round(positive_count / sample_count, 3) if sample_count else None
    negative_rate = round(negative_count / sample_count, 3) if sample_count else None
    baseline_positive_rate = as_float(baseline.get("positive_rate")) or 0.0
    baseline_negative_rate = as_float(baseline.get("negative_rate")) or 0.0
    push_sides = Counter(macd_push_side(row) for row in rows)
    return {
        "wave_rule": wave_rule,
        "push_wave_side": push_sides.most_common(1)[0][0] if push_sides else "none",
        **summary,
        "positive_rate": positive_rate,
        "negative_rate": negative_rate,
        "positive_rate_uplift": round((positive_rate or 0.0) - baseline_positive_rate, 3),
        "negative_rate_uplift": round((negative_rate or 0.0) - baseline_negative_rate, 3),
    }


def build_macd_wave_rules(rows: Sequence[dict[str, Any]], min_samples: int = 10) -> dict[str, Any]:
    by_env: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_env[str(row.get("env") or "unknown")].append(row)
    result: dict[str, Any] = {}
    for env, env_rows in sorted(by_env.items()):
        baseline_summary = summarize_rows(env_rows)
        sample_count = int(baseline_summary.get("sample_count") or 0)
        baseline = {
            **baseline_summary,
            "positive_rate": round((baseline_summary.get("ret3_ge_5_count") or 0) / sample_count, 3) if sample_count else None,
            "negative_rate": round((baseline_summary.get("ret3_le_0_count") or 0) / sample_count, 3) if sample_count else None,
        }
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in env_rows:
            if macd_push_side(row) == "none":
                continue
            grouped[macd_wave_rule_key(row)].append(row)
        summaries = [
            macd_wave_rule_summary(key, grouped_rows, baseline=baseline)
            for key, grouped_rows in sorted(grouped.items())
            if len(grouped_rows) >= min_samples
        ]
        positive_rules = [
            item
            for item in summaries
            if (item.get("positive_rate_uplift") or 0.0) > 0.03
            and int(item.get("ret3_ge_5_count") or 0) >= int(item.get("ret3_le_0_count") or 0)
        ]
        positive_rules.sort(
            key=lambda item: (
                item.get("positive_rate_uplift") or -999.0,
                item.get("positive_rate") or -999.0,
                item.get("sample_count") or 0,
                item.get("ret3_mean") or -999.0,
            ),
            reverse=True,
        )
        result[env] = {
            "baseline": baseline,
            "positive_rules": positive_rules[:30],
            "all_push_wave_rules": sorted(
                summaries,
                key=lambda item: (item.get("sample_count") or 0, item.get("positive_rate") or -999.0),
                reverse=True,
            )[:50],
        }
    return result


def build_factor_segments(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[factor_segment_key(row)].append(row)
    return {key: summarize_rows(items) for key, items in sorted(grouped.items())}


def strong_pattern_family(row: dict[str, Any]) -> str:
    if str(row.get("env") or "") != "strong":
        return "not_strong"
    if str(row.get("signal") or "") != "B2" or str(row.get("signal_type") or "") != "trend_start":
        return "other"
    price = price_position_bucket(row)
    midline = value_or_unknown(row.get("midline_state"))
    support = value_or_unknown(row.get("support_stack_type"))
    compression = compression_bucket(row)
    volume = volume_bucket(row)
    kdj = kdj_bucket(row)
    macd_support = macd_push_side(row) in {"weekly", "both"} and value_or_unknown(row.get("daily_macd_phase_type")) == "falling"
    if (
        price == "upper"
        and midline == "above_hold"
        and support == "bull_stack"
        and compression == "tight"
        and volume == "expanding"
        and kdj in {"neutral", "repair_from_low", "low"}
    ):
        return "S-A"
    if (
        price in {"near_high", "upper"}
        and midline == "above_hold"
        and support == "bull_stack"
        and compression == "tight"
        and volume in {"normal", "expanding"}
        and kdj == "neutral"
    ):
        return "S-B"
    if (
        price in {"near_high", "upper"}
        and midline == "above_hold"
        and support == "bull_stack"
        and macd_support
    ):
        return "S-C"
    return "other"


def strong_indicator_hits(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "b2_trend_start": str(row.get("signal") or "") == "B2" and str(row.get("signal_type") or "") == "trend_start",
        "price_upper_or_near_high": price_position_bucket(row) in {"upper", "near_high"},
        "midline_above_hold": value_or_unknown(row.get("midline_state")) == "above_hold",
        "bull_stack": value_or_unknown(row.get("support_stack_type")) == "bull_stack",
        "tight_compression": compression_bucket(row) == "tight",
        "volume_confirm": volume_bucket(row) == "expanding",
        "kdj_constructive": kdj_bucket(row) in {"neutral", "repair_from_low", "low"},
        "macd_weekly_push_daily_repair": macd_push_side(row) in {"weekly", "both"}
        and value_or_unknown(row.get("daily_macd_phase_type")) == "falling",
    }


def strong_ranked_sample(row: dict[str, Any], family_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    family = strong_pattern_family(row)
    stats = family_stats.get(family, {})
    hits = strong_indicator_hits(row)
    hit_count = sum(1 for matched in hits.values() if matched)
    positive_rate = as_float(stats.get("positive_rate")) or 0.0
    negative_rate = as_float(stats.get("negative_rate")) or 0.0
    ret3_median = as_float(stats.get("ret3_median")) or 0.0
    ret5_median = as_float(stats.get("ret5_median")) or 0.0
    family_rank_score = (
        100.0 * (positive_rate - negative_rate)
        + 6.0 * ret3_median
        + 3.0 * ret5_median
        + 4.0 * hit_count
        + {"S-A": 24.0, "S-B": 16.0, "S-C": 8.0}.get(family, 0.0)
        + (as_float(row.get("current_score")) or 0.0)
    )
    current_score = as_float(row.get("current_score")) or 0.0
    conservative_rank_score = (
        current_score
        + (0.06 if volume_bucket(row) == "expanding" else 0.0)
        + (0.03 if family == "S-B" else 0.0)
        + (0.02 if family == "S-A" else 0.0)
    )
    red_expanding = value_or_unknown(row.get("daily_macd_hist_state")) == "red_expanding"
    price_turnover = value_or_unknown(row.get("price_turnover_state"))
    b3_like = str(row.get("signal") or "") in {"B3", "B3+"}
    b3_trend_red = b3_like and str(row.get("signal_type") or "") == "trend_start" and red_expanding and price_turnover == "price_up_turnover_not"
    b3_rebound_risky = b3_like and str(row.get("signal_type") or "") == "rebound" and (
        (red_expanding and price_turnover == "mixed")
        or (value_or_unknown(row.get("daily_macd_hist_state")) == "green_or_zero" and kdj_bucket(row) == "rising")
    )
    signal = str(row.get("signal") or "")
    signal_type = str(row.get("signal_type") or "")
    price_bucket = price_position_bucket(row)
    compression = compression_bucket(row)
    volume = volume_bucket(row)
    kdj = kdj_bucket(row)
    weekly_stage = value_or_unknown(row.get("weekly_macd_wave_stage"))
    daily_stage = value_or_unknown(row.get("daily_macd_wave_stage"))
    daily_wave = as_float(row.get("daily_macd_wave_index"))
    risk_flags = []
    if signal == "B2" and signal_type == "trend_start" and price_bucket == "near_high" and volume == "expanding" and kdj == "rising":
        risk_flags.append("b2_near_high_expanding_kdj_rising")
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price_bucket == "near_high"
        and compression == "normal"
        and volume == "expanding"
        and kdj == "rising"
    ):
        risk_flags.append("b2_near_high_normal_compression")
    if b3_like and signal_type == "rebound" and red_expanding and price_turnover == "mixed":
        risk_flags.append("b3_rebound_mixed")
    if b3_like and signal_type == "rebound" and value_or_unknown(row.get("daily_macd_hist_state")) == "green_or_zero":
        risk_flags.append("b3_rebound_no_red_hist")
    macd_risk = (
        daily_stage == "背离"
        or weekly_stage in {"分歧", "背离", "强势转分歧"}
        or (daily_wave is not None and daily_wave >= 4.0 and daily_stage in {"背离", "修复", "金叉临近"})
    )
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price_bucket == "upper"
        and volume == "expanding"
        and kdj == "neutral"
        and macd_risk
    ):
        risk_flags.append("b2_upper_neutral_macd_risk")
    if b3_like and signal_type == "trend_start" and b3_trend_red and macd_risk:
        risk_flags.append("b3_red_trend_macd_risk")
    strong_v3_risk_flags = list(risk_flags)
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price_bucket == "near_high"
        and volume == "expanding"
        and kdj == "rising"
        and red_expanding
        and price_turnover == "price_turnover_rise"
    ):
        strong_v3_risk_flags.append("b2_near_high_expanding_red_turnover_rise")
    risk_penalty = (
        (0.12 if "b2_near_high_expanding_kdj_rising" in risk_flags else 0.0)
        + (0.08 if "b2_near_high_normal_compression" in risk_flags else 0.0)
        + (0.35 if "b3_rebound_mixed" in risk_flags else 0.0)
        + (0.12 if "b3_rebound_no_red_hist" in risk_flags else 0.0)
        + (0.15 if "b2_upper_neutral_macd_risk" in risk_flags else 0.0)
        + (0.12 if "b3_red_trend_macd_risk" in risk_flags else 0.0)
    )
    strong_v1_rank_score = (
        current_score
        + (0.20 if family == "S-A" else 0.0)
        + (0.12 if b3_trend_red else 0.0)
        + (
            0.05
            if price_position_bucket(row) in {"near_high", "upper"}
            and value_or_unknown(row.get("midline_state")) == "above_hold"
            and value_or_unknown(row.get("support_stack_type")) == "bull_stack"
            and compression_bucket(row) == "tight"
            else 0.0
        )
        + (0.03 if b3_like and volume_bucket(row) == "normal" else 0.0)
        - (0.15 if b3_rebound_risky else 0.0)
    )
    strong_v2_rank_score = strong_v1_rank_score - risk_penalty
    strong_v3_rank_score = strong_v2_rank_score - (
        0.65 if "b2_near_high_expanding_red_turnover_rise" in strong_v3_risk_flags else 0.0
    )
    s_a_priority_score = current_score + (100.0 if family == "S-A" else 0.0)
    return {
        "date": row.get("date"),
        "code": row.get("code"),
        "verdict": row.get("current_verdict"),
        "current_score": row.get("current_score"),
        "family_rank_score": round(family_rank_score, 3),
        "conservative_rank_score": round(conservative_rank_score, 3),
        "strong_v1_rank_score": round(strong_v1_rank_score, 3),
        "strong_v2_rank_score": round(strong_v2_rank_score, 3),
        "strong_v3_rank_score": round(strong_v3_rank_score, 3),
        "strong_v2_risk_penalty": round(risk_penalty, 3),
        "strong_v2_risk_flags": risk_flags,
        "strong_v3_risk_flags": strong_v3_risk_flags,
        "s_a_priority_score": round(s_a_priority_score, 3),
        "family": family,
        "indicator_hit_count": hit_count,
        "indicator_hits": hits,
        "ret3": row.get("ret3"),
        "ret5": row.get("ret5"),
        "factor_segment": factor_segment_key(row),
        "macd_wave_rule": macd_wave_rule_key(row),
    }


def summarize_ranked_samples(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows = [{"ret3": sample.get("ret3"), "ret5": sample.get("ret5"), "current_verdict": sample.get("verdict")} for sample in samples]
    summary = summarize_rows(rows)
    sample_count = int(summary.get("sample_count") or 0)
    return {
        **summary,
        "positive_rate": round((summary.get("ret3_ge_5_count") or 0) / sample_count, 3) if sample_count else None,
        "negative_rate": round((summary.get("ret3_le_0_count") or 0) / sample_count, 3) if sample_count else None,
    }


def build_strong_pass_watch_ranking_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    strong_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "strong" and normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
    ]
    family_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in strong_rows:
        family_groups[strong_pattern_family(row)].append(row)
    family_stats = {}
    for family, family_rows in sorted(family_groups.items()):
        summary = summarize_rows(family_rows)
        sample_count = int(summary.get("sample_count") or 0)
        family_stats[family] = {
            **summary,
            "positive_rate": round((summary.get("ret3_ge_5_count") or 0) / sample_count, 3) if sample_count else None,
            "negative_rate": round((summary.get("ret3_le_0_count") or 0) / sample_count, 3) if sample_count else None,
        }
    ranked_samples = [strong_ranked_sample(row, family_stats) for row in strong_rows]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in ranked_samples:
        by_date[str(sample.get("date"))].append(sample)
    daily_top3 = []
    ranking_variants = {
        "current_score": "current_score",
        "conservative_rank": "conservative_rank_score",
        "strong_v1_rank": "strong_v1_rank_score",
        "strong_v2_rank": "strong_v2_rank_score",
        "strong_v3_rank": "strong_v3_rank_score",
        "s_a_priority": "s_a_priority_score",
        "family_rank": "family_rank_score",
    }
    top3_by_variant = {name: [] for name in ranking_variants}
    top5_by_variant = {name: [] for name in ranking_variants}
    for date_key, date_samples in sorted(by_date.items()):
        day_payload: dict[str, Any] = {"date": date_key}
        for variant_name, score_key in ranking_variants.items():
            ranked = sorted(
                date_samples,
                key=lambda sample: (
                    as_float(sample.get(score_key)) or -999.0,
                    as_float(sample.get("current_score")) or 0.0,
                ),
                reverse=True,
            )
            top3 = ranked[:3]
            top5 = ranked[:5]
            top3_by_variant[variant_name].extend(top3)
            top5_by_variant[variant_name].extend(top5)
            day_payload[variant_name] = top3
            day_payload[f"{variant_name}_top5"] = top5
        daily_top3.append(day_payload)
    return {
        "scope": "env=strong and verdict in PASS/WATCH",
        "sample_count": len(strong_rows),
        "candidate_count": len(ranked_samples),
        "family_stats": family_stats,
        "ranking_variants": {
            "current_score": "baseline: existing current_score order",
            "conservative_rank": "current_score plus small boosts for expanding volume and accepted strong families",
            "strong_v1_rank": "current_score plus S-A, B3 red MACD re-acceleration, and B3 rebound risk adjustments",
            "strong_v2_rank": "diagnostic candidate: strong_v1_rank minus repeated negative-group risk flags; keep offline until it beats v1",
            "strong_v3_rank": "diagnostic candidate: strong_v2 plus penalty for strong B2 near-high expanding red-turnover losers",
            "s_a_priority": "diagnostic stress test: prioritize S-A family before current_score",
            "family_rank": "diagnostic stress test: rank by historical family strength and indicator hits",
        },
        "top3_comparison": {name: summarize_ranked_samples(samples) for name, samples in top3_by_variant.items()},
        "top5_comparison": {name: summarize_ranked_samples(samples) for name, samples in top5_by_variant.items()},
        "daily_top3": daily_top3,
        "ranked_samples": sorted(
            ranked_samples,
            key=lambda sample: (
                str(sample.get("date")),
                -(as_float(sample.get("conservative_rank_score")) or -999.0),
            ),
        ),
        "diagnosis": (
            "strong_v1 improves high-ret3 capture over current_score, while strong_v2 is only a risk-flag experiment. "
            "Do not promote strong_v2 unless regenerated diagnostics show it beats strong_v1 on top3/top5 positive and negative metrics."
        ),
        "next_step": "Keep strong_v1 as the current strong sorting candidate, then repeat the same route-specific report for neutral and weak with separate factor definitions.",
    }


def distribution_summary(rows: Sequence[dict[str, Any]], key_fn) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    result = {}
    for key, items in sorted(grouped.items()):
        summary = summarize_rows(items)
        sample_count = int(summary.get("sample_count") or 0)
        result[key] = {
            **summary,
            "share": round(sample_count / len(rows), 3) if rows else None,
            "positive_rate": round((summary.get("ret3_ge_5_count") or 0) / sample_count, 3) if sample_count else None,
            "negative_rate": round((summary.get("ret3_le_0_count") or 0) / sample_count, 3) if sample_count else None,
        }
    return dict(sorted(result.items(), key=lambda item: item[1].get("sample_count") or 0, reverse=True))


def summarize_daily_top3_hit(samples_by_day: Sequence[Sequence[dict[str, Any]]]) -> dict[str, Any]:
    valid_days = []
    for samples in samples_by_day:
        valid_samples = [sample for sample in samples if as_float(sample.get("ret3")) is not None]
        if valid_samples:
            valid_days.append(valid_samples)
    day_count = len(valid_days)
    hit_days = sum(1 for samples in valid_days if any((as_float(sample.get("ret3")) or -999.0) >= 5.0 for sample in samples))
    return {
        "day_count": day_count,
        "hit_days": hit_days,
        "hit_rate": round(hit_days / day_count, 3) if day_count else None,
    }


def summarize_top3_variant(samples_by_day: Sequence[Sequence[dict[str, Any]]]) -> dict[str, Any]:
    samples = [sample for day_samples in samples_by_day for sample in day_samples if as_float(sample.get("ret3")) is not None]
    winners = [sample for sample in samples if (as_float(sample.get("ret3")) or -999.0) >= 5.0]
    losses = [sample for sample in samples if (as_float(sample.get("ret3")) or 999.0) <= 0.0]
    risk_rows = []
    for sample in losses:
        flags = [
            *sample.get("weak_risk_flags", []),
            *sample.get("weak_v3_risk_flags", []),
            *sample.get("neutral_risk_flags", []),
        ]
        for flag in flags:
            risk_rows.append({**sample, "top3_risk_flag": flag})
    return {
        "top3_summary": summarize_ranked_samples(samples),
        "daily_hit_summary": summarize_daily_top3_hit(samples_by_day),
        "winner_factor_distribution": distribution_summary(winners, lambda sample: str(sample.get("factor_segment") or "unknown")),
        "winner_macd_distribution": distribution_summary(winners, lambda sample: str(sample.get("macd_wave_rule") or "unknown")),
        "loss_factor_distribution": distribution_summary(losses, lambda sample: str(sample.get("factor_segment") or "unknown")),
        "loss_macd_distribution": distribution_summary(losses, lambda sample: str(sample.get("macd_wave_rule") or "unknown")),
        "loss_risk_flag_distribution": distribution_summary(risk_rows, lambda sample: str(sample.get("top3_risk_flag") or "unknown")),
        "loss_samples": sorted(losses, key=lambda sample: as_float(sample.get("ret3")) or 999.0)[:40],
    }


def collect_daily_variant_samples(report: dict[str, Any], variant_name: str) -> list[list[dict[str, Any]]]:
    return [list(day.get(variant_name, [])) for day in report.get("daily_top3", []) if variant_name in day]


def build_weak_neutral_top3_followup_report(
    weak_report: dict[str, Any], neutral_report: dict[str, Any], neutral_v2_report: dict[str, Any] | None = None
) -> dict[str, Any]:
    environments = {
        "weak": {
            "frozen": False,
            "variants": {
                variant: summarize_top3_variant(collect_daily_variant_samples(weak_report, variant))
                for variant in ("current_score", "weak_v3_rank", "weak_v4_rank")
                if collect_daily_variant_samples(weak_report, variant)
            },
            "next_step": (
                "Use weak_v3 as the top3 hit-rate reference and weak_v4 as the top5/indicator reference; "
                "continue by reducing top3 ret3<=0 with loss factor/MACD/risk groups before any production promotion."
            ),
        },
        "neutral": {
            "frozen": False,
            "variants": {
                variant: summarize_top3_variant(collect_daily_variant_samples(neutral_report, variant))
                for variant in ("current_score", "neutral_v1_rank")
                if collect_daily_variant_samples(neutral_report, variant)
            },
            "next_step": (
                "Keep neutral_v1 as the current neutral candidate; neutral_v2 only remains useful if it reduces losses "
                "without lowering top3 ret3>=5 capture."
            ),
        },
    }
    if neutral_v2_report:
        neutral_v2_samples = collect_daily_variant_samples(neutral_v2_report, "neutral_v2_rank")
        if neutral_v2_samples:
            environments["neutral"]["variants"]["neutral_v2_rank"] = summarize_top3_variant(neutral_v2_samples)
    return {
        "scope": "weak and neutral top3 follow-up after freezing strong_v1_rank",
        "strong_policy": "strong_v1_rank is frozen for this tuning round; this report does not evaluate or change strong.",
        "environments": environments,
        "diagnosis": (
            "Neutral has the cleaner top3 ret3>=5 improvement through neutral_v1. Weak has improved hit rate through weak_v3/weak_v4 "
            "but still needs loss veto refinement before production ranking changes."
        ),
    }


WEAK_FINAL_PENALTY_CANDIDATES = {
    "rebound_near_high_normal_rising": {
        "penalty": 0.16,
        "factor_segment": "weak|B3|rebound|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising",
        "reason": "top3 recurring loss group; useful as risk observation, but final simulation is weaker than the reclaim-volume penalty",
    },
    "trend_upper_normal_rising": {
        "penalty": 0.16,
        "factor_segment": "weak|B3|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising",
        "reason": "recurring top3 loss group, but broader penalty reduces daily hit rate in simulation",
    },
    "b2_reclaim_expanding_rising": {
        "penalty": 0.16,
        "factor_segment": "weak|B2|trend_start|price=upper|midline=reclaim_volume|support=bull_stack|compression=tight|volume=expanding|kdj=rising",
        "reason": "best balanced weak top3 candidate: improves top3 ret3>=5, top3 ret3<=0, daily hit rate, and top5 metrics versus weak_v3 baseline",
    },
}


def weak_final_penalty(sample: dict[str, Any], penalties: dict[str, float]) -> float:
    total = 0.0
    factor = str(sample.get("factor_segment") or "")
    for key, config in WEAK_FINAL_PENALTY_CANDIDATES.items():
        if factor == config.get("factor_segment"):
            total += penalties.get(key, 0.0)
    if "existing_macd_flags" in penalties and (
        "b3_trend_red_macd_bad" in sample.get("weak_v3_risk_flags", [])
        or "b2_mid_near_expanding_red_macd_bad" in sample.get("weak_v3_risk_flags", [])
    ):
        total += penalties.get("existing_macd_flags", 0.0)
    return total


def summarize_weak_final_scenario(
    ranked_samples: Sequence[dict[str, Any]], score_key: str, penalties: dict[str, float], topn: int
) -> dict[str, Any]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in ranked_samples:
        if as_float(sample.get("ret3")) is None or as_float(sample.get(score_key)) is None:
            continue
        penalty = weak_final_penalty(sample, penalties)
        by_date[str(sample.get("date"))].append(
            {
                **sample,
                "weak_final_penalty": round(penalty, 3),
                "weak_final_rank_score": round((as_float(sample.get(score_key)) or 0.0) - penalty, 3),
            }
        )
    selected = []
    hit_days = 0
    day_count = 0
    for date_samples in sorted(by_date.values(), key=lambda samples: str(samples[0].get("date") if samples else "")):
        ranked = sorted(
            date_samples,
            key=lambda sample: (
                as_float(sample.get("weak_final_rank_score")) or -999.0,
                as_float(sample.get("current_score")) or 0.0,
            ),
            reverse=True,
        )[:topn]
        if ranked:
            day_count += 1
            hit_days += int(any((as_float(sample.get("ret3")) or -999.0) >= 5.0 for sample in ranked))
        selected.extend(ranked)
    summary = summarize_ranked_samples(selected)
    return {
        **summary,
        "daily_hit_days": hit_days,
        "day_count": day_count,
        "daily_hit_rate": round(hit_days / day_count, 3) if day_count else None,
        "penalized_distribution": distribution_summary(
            [sample for sample in selected if (as_float(sample.get("weak_final_penalty")) or 0.0) > 0.0],
            lambda sample: str(sample.get("factor_segment") or "unknown"),
        ),
    }


def build_weak_final_tuning_report(weak_report: dict[str, Any]) -> dict[str, Any]:
    ranked_samples = list(weak_report.get("ranked_samples", []))
    scenarios = {
        "weak_v3_final": {},
        "weak_v3_minus_rebound_near_high_normal_rising": {"rebound_near_high_normal_rising": 0.16},
        "weak_v3_minus_reclaim": {"b2_reclaim_expanding_rising": 0.16},
        "weak_v3_minus_three_loss_groups": {
            "rebound_near_high_normal_rising": 0.16,
            "trend_upper_normal_rising": 0.16,
            "b2_reclaim_expanding_rising": 0.16,
        },
        "weak_v3_minus_three_plus_macd": {
            "rebound_near_high_normal_rising": 0.24,
            "trend_upper_normal_rising": 0.24,
            "b2_reclaim_expanding_rising": 0.16,
            "existing_macd_flags": 0.18,
        },
        "weak_v4_reference": {},
    }
    scenario_payload = {}
    for name, penalties in scenarios.items():
        score_key = "weak_v4_rank_score" if name == "weak_v4_reference" else "weak_v3_rank_score"
        scenario_payload[name] = {
            "score_key": score_key,
            "penalties": penalties,
            "top3": summarize_weak_final_scenario(ranked_samples, score_key, penalties, 3),
            "top5": summarize_weak_final_scenario(ranked_samples, score_key, penalties, 5),
        }
    return {
        "scope": "final weak tuning decision after freezing strong_v1_rank",
        "recommended_top3_scenario": "weak_v3_minus_reclaim",
        "top5_reference_scenario": "weak_v4_reference",
        "production_boundary": "offline decision report only; do not change production review verdict in this step",
        "penalty_candidates": WEAK_FINAL_PENALTY_CANDIDATES,
        "scenarios": scenario_payload,
        "diagnosis": (
            "Weak top3 should settle on weak_v3 with one small penalty for B2 trend_start upper/reclaim_volume/expanding/rising. "
            "Broader weak veto sets reduce daily hit rate or top5 capture, while weak_v4 remains a top5 indicator reference only."
        ),
    }


def build_strong_pass_composition_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    pass_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "strong" and normalize_verdict(row.get("current_verdict")) == "PASS"
    ]
    summary = summarize_rows(pass_rows)
    sample_count = int(summary.get("sample_count") or 0)
    indicator_totals = Counter()
    for row in pass_rows:
        for key, matched in strong_indicator_hits(row).items():
            if matched:
                indicator_totals[key] += 1
    return {
        "scope": "env=strong and verdict=PASS",
        "sample_count": len(pass_rows),
        "summary": {
            **summary,
            "positive_rate": round((summary.get("ret3_ge_5_count") or 0) / sample_count, 3) if sample_count else None,
            "negative_rate": round((summary.get("ret3_le_0_count") or 0) / sample_count, 3) if sample_count else None,
        },
        "family_distribution": distribution_summary(pass_rows, strong_pattern_family),
        "signal_distribution": distribution_summary(pass_rows, lambda row: f"{row.get('signal') or ''}|{row.get('signal_type') or ''}"),
        "factor_distribution": distribution_summary(pass_rows, factor_segment_key),
        "macd_wave_distribution": distribution_summary(pass_rows, macd_wave_rule_key),
        "indicator_hit_rates": {
            key: round(value / len(pass_rows), 3) if pass_rows else None for key, value in sorted(indicator_totals.items())
        },
        "typical_samples": [
            {
                **sample_brief(row),
                "family": strong_pattern_family(row),
                "factor_segment": factor_segment_key(row),
                "macd_wave_rule": macd_wave_rule_key(row),
            }
            for row in sorted(pass_rows, key=lambda item: as_float(item.get("ret3")) or -999.0, reverse=True)[:30]
        ],
        "diagnosis": (
            "Current strong PASS is mostly not S-A; it is dominated by B3/B3+ structures. "
            "S-A is a high-quality strong WATCH family and should not be treated as the current PASS basis."
        ),
    }


def b3_red_macd_condition_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            value_or_unknown(row.get("daily_macd_hist_state")),
            value_or_unknown(row.get("price_turnover_state")),
        ]
    )


def build_strong_b3_red_macd_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    b3_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "strong"
        and normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
        and str(row.get("signal") or "") in {"B3", "B3+"}
    ]
    summary = summarize_rows(b3_rows)
    sample_count = int(summary.get("sample_count") or 0)
    return {
        "scope": "env=strong, verdict in PASS/WATCH, signal in B3/B3+",
        "sample_count": len(b3_rows),
        "summary": {
            **summary,
            "positive_rate": round((summary.get("ret3_ge_5_count") or 0) / sample_count, 3) if sample_count else None,
            "negative_rate": round((summary.get("ret3_le_0_count") or 0) / sample_count, 3) if sample_count else None,
        },
        "condition_distribution": distribution_summary(b3_rows, b3_red_macd_condition_key),
        "factor_condition_distribution": distribution_summary(
            b3_rows,
            lambda row: "|".join(
                [
                    str(row.get("signal") or ""),
                    str(row.get("signal_type") or ""),
                    b3_red_macd_condition_key(row),
                    f"price={price_position_bucket(row)}",
                    f"volume={volume_bucket(row)}",
                    f"kdj={kdj_bucket(row)}",
                ]
            ),
        ),
        "typical_samples": [
            {
                **sample_brief(row),
                "condition": b3_red_macd_condition_key(row),
                "daily_macd_hist": row.get("daily_macd_hist"),
                "daily_macd_hist_prev": row.get("daily_macd_hist_prev"),
                "turnover_rate": row.get("turnover_rate"),
                "turnover_rate_ratio_5d": row.get("turnover_rate_ratio_5d"),
                "daily_pct_chg": row.get("daily_pct_chg"),
            }
            for row in sorted(b3_rows, key=lambda item: as_float(item.get("ret3")) or -999.0, reverse=True)[:40]
        ],
        "diagnosis": (
            "Tests whether strong B3/B3+ is sensitive to renewed red MACD expansion plus price and turnover rising together."
        ),
    }


def strong_v1_negative_condition_key(row: dict[str, Any]) -> str:
    signal = str(row.get("signal") or "")
    signal_type = str(row.get("signal_type") or "")
    pieces = [
        value_or_unknown(row.get("daily_macd_hist_state")),
        value_or_unknown(row.get("price_turnover_state")),
        signal_type,
        f"price={price_position_bucket(row)}",
        f"volume={volume_bucket(row)}",
        f"kdj={kdj_bucket(row)}",
    ]
    if signal in {"B3", "B3+"}:
        return "|".join(pieces)
    return "|".join([f"NONB3={signal}", *pieces])


def build_strong_v1_negative_groups_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    strong_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "strong" and normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
    ]
    family_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in strong_rows:
        family_groups[strong_pattern_family(row)].append(row)
    family_stats = {}
    for family, family_rows in sorted(family_groups.items()):
        summary = summarize_rows(family_rows)
        sample_count = int(summary.get("sample_count") or 0)
        family_stats[family] = {
            **summary,
            "positive_rate": round((summary.get("ret3_ge_5_count") or 0) / sample_count, 3) if sample_count else None,
            "negative_rate": round((summary.get("ret3_le_0_count") or 0) / sample_count, 3) if sample_count else None,
        }

    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in strong_rows:
        ranked = strong_ranked_sample(row, family_stats)
        by_date[str(row.get("date"))].append({**row, **ranked})

    def build_scope(limit: int) -> dict[str, Any]:
        selected: list[dict[str, Any]] = []
        for date_key, date_rows in sorted(by_date.items()):
            ranked_rows = sorted(
                date_rows,
                key=lambda row: (
                    as_float(row.get("strong_v1_rank_score")) or -999.0,
                    as_float(row.get("current_score")) or 0.0,
                ),
                reverse=True,
            )
            for rank, row in enumerate(ranked_rows[:limit], start=1):
                selected.append({**row, "strong_v1_daily_rank": rank, "date": date_key})
        negatives = [row for row in selected if (as_float(row.get("ret3")) or 999.0) <= 0.0]
        positive = [row for row in selected if (as_float(row.get("ret3")) or -999.0) >= 5.0]
        return {
            "sample_count": len(selected),
            "positive_summary": summarize_rows(positive),
            "negative_summary": summarize_rows(negatives),
            "negative_family_distribution": distribution_summary(negatives, strong_pattern_family),
            "negative_factor_distribution": distribution_summary(negatives, factor_segment_key),
            "negative_macd_wave_distribution": distribution_summary(negatives, macd_wave_rule_key),
            "negative_b3_condition_distribution": distribution_summary(negatives, strong_v1_negative_condition_key),
            "worst_samples": [
                {
                    **sample_brief(row),
                    "family": strong_pattern_family(row),
                    "strong_v1_daily_rank": row.get("strong_v1_daily_rank"),
                    "strong_v1_rank_score": row.get("strong_v1_rank_score"),
                    "factor_segment": factor_segment_key(row),
                    "macd_wave_rule": macd_wave_rule_key(row),
                    "negative_condition": strong_v1_negative_condition_key(row),
                    "daily_macd_hist_state": row.get("daily_macd_hist_state"),
                    "price_turnover_state": row.get("price_turnover_state"),
                    "daily_pct_chg": row.get("daily_pct_chg"),
                    "turnover_rate": row.get("turnover_rate"),
                    "turnover_rate_ratio_5d": row.get("turnover_rate_ratio_5d"),
                }
                for row in sorted(negatives, key=lambda item: as_float(item.get("ret3")) or 0.0)[:40]
            ],
        }

    return {
        "scope": "env=strong, verdict in PASS/WATCH, daily strong_v1_rank topN negative samples",
        "diagnosis": (
            "Compares strong_v1 ranked losers with the offline factor/MACD reports so recurring negative groups can be "
            "turned into ranking penalties or veto conditions before changing production review verdicts."
        ),
        "top3": build_scope(3),
        "top5": build_scope(5),
    }


def weak_pattern_family(row: dict[str, Any]) -> str:
    if str(row.get("env") or "") != "weak":
        return "not_weak"
    signal = str(row.get("signal") or "")
    signal_type = str(row.get("signal_type") or "")
    price = price_position_bucket(row)
    midline = value_or_unknown(row.get("midline_state"))
    support = value_or_unknown(row.get("support_stack_type"))
    compression = compression_bucket(row)
    volume = volume_bucket(row)
    kdj = kdj_bucket(row)
    hist_state = value_or_unknown(row.get("daily_macd_hist_state"))
    price_turnover = value_or_unknown(row.get("price_turnover_state"))
    if (
        signal == "B3"
        and signal_type == "rebound"
        and price == "near_high"
        and midline == "above_hold"
        and support == "bull_stack"
        and compression == "tight"
        and volume in {"normal", "expanding"}
        and kdj == "rising"
        and hist_state == "red_expanding"
        and price_turnover == "price_up_turnover_not"
    ):
        return "W-A"
    if (
        signal == "B3"
        and signal_type == "trend_start"
        and price == "upper"
        and volume == "normal"
        and kdj == "rising"
        and price_turnover == "price_up_turnover_not"
    ):
        return "W-B"
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price == "near_high"
        and midline == "pullback_confirm"
        and compression == "normal"
        and volume == "expanding"
        and kdj == "rising"
    ):
        return "W-C"
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price == "extended_or_unknown"
        and volume == "normal"
        and kdj == "neutral"
        and hist_state == "green_or_zero"
        and price_turnover == "price_turnover_rise"
    ):
        return "W-D"
    return "other"


def weak_risk_flags(row: dict[str, Any]) -> list[str]:
    signal = str(row.get("signal") or "")
    signal_type = str(row.get("signal_type") or "")
    price = price_position_bucket(row)
    volume = volume_bucket(row)
    kdj = kdj_bucket(row)
    hist_state = value_or_unknown(row.get("daily_macd_hist_state"))
    price_turnover = value_or_unknown(row.get("price_turnover_state"))
    wave = macd_wave_rule_key(row)
    flags = []
    if (
        signal == "B3"
        and signal_type == "rebound"
        and price == "extended_or_unknown"
        and volume == "normal"
        and kdj == "repair_from_low"
        and hist_state == "green_or_zero"
        and price_turnover == "mixed"
    ):
        flags.append("b3_rebound_extended_mixed")
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price == "near_high"
        and volume == "normal"
        and kdj == "rising"
        and hist_state == "green_or_zero"
        and price_turnover == "price_turnover_rise"
    ):
        flags.append("b2_near_high_normal_rising_no_red")
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price == "upper"
        and volume == "expanding"
        and kdj == "neutral"
        and hist_state == "red_expanding"
        and price_turnover == "price_turnover_rise"
    ):
        flags.append("b2_upper_expanding_neutral_red")
    if wave == "W:rising:2:背离|D:falling:4:修复":
        flags.append("macd_w2_div_d4_repair")
    if wave == "W:rising:0:背离|D:falling:4:修复":
        flags.append("macd_w0_div_d4_repair")
    return flags


def weak_macd_bad(row: dict[str, Any]) -> bool:
    weekly_stage = value_or_unknown(row.get("weekly_macd_wave_stage"))
    daily_stage = value_or_unknown(row.get("daily_macd_wave_stage"))
    return weekly_stage in {"背离", "分歧", "强势转分歧"} or daily_stage in {"背离", "分歧", "强势转分歧"}


def weak_v3_risk_flags(row: dict[str, Any]) -> list[str]:
    signal = str(row.get("signal") or "")
    signal_type = str(row.get("signal_type") or "")
    price = price_position_bucket(row)
    volume = volume_bucket(row)
    kdj = kdj_bucket(row)
    hist_state = value_or_unknown(row.get("daily_macd_hist_state"))
    price_turnover = value_or_unknown(row.get("price_turnover_state"))
    macd_bad = weak_macd_bad(row)
    flags = []
    if (
        signal == "B3"
        and signal_type == "trend_start"
        and price in {"upper", "near_high"}
        and volume == "normal"
        and kdj == "rising"
        and hist_state == "red_expanding"
        and price_turnover == "price_up_turnover_not"
        and macd_bad
    ):
        flags.append("b3_trend_red_macd_bad")
    if signal == "B3" and signal_type == "rebound" and price == "upper" and volume == "normal" and kdj == "rising" and hist_state == "green_or_zero":
        flags.append("b3_rebound_upper_no_red")
    if (
        signal == "B3"
        and signal_type == "rebound"
        and price == "upper"
        and volume == "normal"
        and kdj == "rising"
        and hist_state == "red_expanding"
        and price_turnover == "mixed"
    ):
        flags.append("b3_rebound_upper_red_mixed")
    if signal == "B2" and signal_type == "trend_start" and price == "extended_or_unknown" and volume == "normal" and kdj == "neutral" and macd_bad:
        flags.append("b2_extended_neutral_macd_bad")
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price in {"middle", "near_high"}
        and volume == "expanding"
        and kdj == "rising"
        and hist_state == "red_expanding"
        and macd_bad
    ):
        flags.append("b2_mid_near_expanding_red_macd_bad")
    return flags


def weak_ranked_sample(row: dict[str, Any]) -> dict[str, Any]:
    current_score = as_float(row.get("current_score")) or 0.0
    family = weak_pattern_family(row)
    flags = weak_risk_flags(row)
    bbi_state = value_or_unknown(row.get("bbi_bias_state"))
    bias_state = value_or_unknown(row.get("bias_bucket"))
    obv = value_or_unknown(row.get("obv_state"))
    weak_v1_score = (
        current_score
        + {"W-A": 0.25, "W-B": 0.16, "W-C": 0.14, "W-D": 0.10}.get(family, 0.0)
        - sum(
            {
                "b3_rebound_extended_mixed": 0.45,
                "b2_near_high_normal_rising_no_red": 0.18,
                "b2_upper_expanding_neutral_red": 0.16,
                "macd_w2_div_d4_repair": 0.18,
                "macd_w0_div_d4_repair": 0.12,
            }.get(flag, 0.0)
            for flag in flags
        )
    )
    weak_v2_score = weak_v1_score
    if str(row.get("signal") or "") == "B2" and str(row.get("signal_type") or "") == "rebound":
        weak_v2_score -= 0.08
    if family in {"W-A", "W-C"} and not flags:
        weak_v2_score += 0.05
    v3_flags = weak_v3_risk_flags(row)
    weak_v3_score = weak_v2_score - sum(
        {
            "b3_trend_red_macd_bad": 0.22,
            "b3_rebound_upper_no_red": 0.20,
            "b3_rebound_upper_red_mixed": 0.18,
            "b2_extended_neutral_macd_bad": 0.18,
            "b2_mid_near_expanding_red_macd_bad": 0.16,
        }.get(flag, 0.0)
        for flag in v3_flags
    )
    indicator_boost = 0.0
    if bbi_state == "above_extended" and bias_state == "high_positive" and obv == "rising":
        indicator_boost += 0.18
    elif bbi_state == "above_extended" and bias_state in {"positive", "neutral"} and obv == "rising":
        indicator_boost += 0.08
    elif bbi_state == "above" and bias_state == "positive" and family in {"W-B", "W-D"}:
        indicator_boost += 0.06
    indicator_penalty = 0.0
    if bbi_state == "below_near" and bias_state in {"negative", "positive"}:
        indicator_penalty += 0.16
    if bbi_state == "below_deep" and bias_state == "neutral":
        indicator_penalty += 0.14
    if obv == "falling":
        indicator_penalty += 0.08
    weak_v4_score = weak_v3_score + indicator_boost - indicator_penalty
    return {
        "date": row.get("date"),
        "code": row.get("code"),
        "verdict": row.get("current_verdict"),
        "current_score": row.get("current_score"),
        "weak_v1_rank_score": round(weak_v1_score, 3),
        "weak_v2_rank_score": round(weak_v2_score, 3),
        "weak_v3_rank_score": round(weak_v3_score, 3),
        "weak_v4_rank_score": round(weak_v4_score, 3),
        "weak_risk_flags": flags,
        "weak_v3_risk_flags": v3_flags,
        "weak_indicator_boost": round(indicator_boost, 3),
        "weak_indicator_penalty": round(indicator_penalty, 3),
        "weak_indicator_key": weak_indicator_key(row),
        "family": family,
        "ret3": row.get("ret3"),
        "ret5": row.get("ret5"),
        "factor_segment": factor_segment_key(row),
        "macd_wave_rule": macd_wave_rule_key(row),
    }


def build_weak_pass_watch_ranking_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    weak_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "weak" and normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
    ]
    ranked_samples = [weak_ranked_sample(row) for row in weak_rows]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in ranked_samples:
        by_date[str(sample.get("date"))].append(sample)
    ranking_variants = {
        "current_score": "current_score",
        "weak_v1_rank": "weak_v1_rank_score",
        "weak_v2_rank": "weak_v2_rank_score",
        "weak_v3_rank": "weak_v3_rank_score",
        "weak_v4_rank": "weak_v4_rank_score",
    }
    top3_by_variant = {name: [] for name in ranking_variants}
    top5_by_variant = {name: [] for name in ranking_variants}
    daily_top3 = []
    for date_key, date_samples in sorted(by_date.items()):
        day_payload: dict[str, Any] = {"date": date_key}
        for variant_name, score_key in ranking_variants.items():
            ranked = sorted(
                date_samples,
                key=lambda sample: (
                    as_float(sample.get(score_key)) or -999.0,
                    as_float(sample.get("current_score")) or 0.0,
                ),
                reverse=True,
            )
            top3 = ranked[:3]
            top5 = ranked[:5]
            top3_by_variant[variant_name].extend(top3)
            top5_by_variant[variant_name].extend(top5)
            day_payload[variant_name] = top3
            day_payload[f"{variant_name}_top5"] = top5
        daily_top3.append(day_payload)
    return {
        "scope": "env=weak and verdict in PASS/WATCH",
        "sample_count": len(weak_rows),
        "candidate_count": len(ranked_samples),
        "family_distribution": distribution_summary(ranked_samples, lambda row: str(row.get("family") or "unknown")),
        "risk_flag_distribution": distribution_summary(
            [{**row, "weak_risk_flag": flag} for row in ranked_samples for flag in row.get("weak_risk_flags", [])],
            lambda row: str(row.get("weak_risk_flag") or "unknown"),
        ),
        "ranking_variants": {
            "current_score": "baseline: existing current_score order",
            "weak_v1_rank": "current_score plus weak repair families and explicit weak risk penalties",
            "weak_v2_rank": "weak_v1_rank plus a small B2 rebound penalty and clean W-A/W-C boost",
            "weak_v3_rank": "diagnostic candidate: weak_v2_rank minus remaining weak_v2 loser groups; improves mean but must reduce negatives before production use",
            "weak_v4_rank": "diagnostic candidate: weak_v3_rank plus BBI/BIAS/OBV boosts and penalties from daily_indicators.extra_factors_jsonb",
        },
        "top3_comparison": {name: summarize_ranked_samples(samples) for name, samples in top3_by_variant.items()},
        "top5_comparison": {name: summarize_ranked_samples(samples) for name, samples in top5_by_variant.items()},
        "daily_top3": daily_top3,
        "ranked_samples": sorted(
            ranked_samples,
            key=lambda sample: (
                str(sample.get("date")),
                -(as_float(sample.get("weak_v4_rank_score")) or -999.0),
            ),
        ),
        "diagnosis": (
            "Weak PASS/WATCH has almost no baseline edge over FAIL, so weak ranking should be used only to reduce top-list "
            "damage and find repair candidates, not to promote broad PASS rules. weak_v4 adds BBI/BIAS/OBV as an offline "
            "indicator experiment and should not be promoted unless it beats weak_v3 on both mean return and negative rate."
        ),
    }


def weak_condition_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("signal") or ""),
            str(row.get("signal_type") or ""),
            price_position_bucket(row),
            volume_bucket(row),
            kdj_bucket(row),
            value_or_unknown(row.get("daily_macd_hist_state")),
            value_or_unknown(row.get("price_turnover_state")),
        ]
    )


def weak_indicator_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            f"bbi={value_or_unknown(row.get('bbi_bias_state'))}",
            f"bias={value_or_unknown(row.get('bias_bucket'))}",
            f"obv={value_or_unknown(row.get('obv_state'))}",
        ]
    )


def weak_indicator_family_key(row: dict[str, Any]) -> str:
    return "|".join([weak_pattern_family(row), weak_indicator_key(row)])


def build_weak_indicator_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    weak_rows = [row for row in rows if str(row.get("env") or "") == "weak"]
    weak_pw_rows = [
        row
        for row in weak_rows
        if normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
    ]
    return {
        "scope": "env=weak indicator diagnostics from daily_indicators.extra_factors_jsonb",
        "sample_count": len(weak_rows),
        "pass_watch_count": len(weak_pw_rows),
        "indicator_distribution": distribution_summary(weak_rows, weak_indicator_key),
        "pass_watch_indicator_distribution": distribution_summary(weak_pw_rows, weak_indicator_key),
        "family_indicator_distribution": distribution_summary(weak_pw_rows, weak_indicator_family_key),
        "condition_indicator_distribution": distribution_summary(
            weak_pw_rows,
            lambda row: "|".join([weak_condition_key(row), weak_indicator_key(row)]),
        ),
        "diagnosis": (
            "Adds BBI, BIAS and OBV from daily_indicators to test whether weak high-ret3 samples can be separated from "
            "negative samples after price/volume/MACD factors are already known."
        ),
    }


def weak_watch_positive_condition_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("signal") or ""),
            str(row.get("signal_type") or ""),
            f"family={weak_pattern_family(row)}",
            f"price={price_position_bucket(row)}",
            f"midline={value_or_unknown(row.get('midline_state'))}",
            f"volume={volume_bucket(row)}",
            f"kdj={kdj_bucket(row)}",
            f"hist={value_or_unknown(row.get('daily_macd_hist_state'))}",
            f"turnover={value_or_unknown(row.get('price_turnover_state'))}",
        ]
    )


def weak_watch_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_rows(rows)
    sample_count = int(summary.get("sample_count") or 0)
    ret3_values = [value for value in (as_float(row.get("ret3")) for row in rows) if value is not None]
    ret5_values = [value for value in (as_float(row.get("ret5")) for row in rows) if value is not None]
    ret3_gt_0_count = sum(1 for value in ret3_values if value > 0.0)
    ret5_gt_0_count = sum(1 for value in ret5_values if value > 0.0)
    ret3_ge_5_count = int(summary.get("ret3_ge_5_count") or 0)
    ret3_le_0_count = int(summary.get("ret3_le_0_count") or 0)
    return {
        **summary,
        "ret3_gt_0_count": ret3_gt_0_count,
        "ret5_gt_0_count": ret5_gt_0_count,
        "ret3_gt_0_rate": round(ret3_gt_0_count / sample_count, 3) if sample_count else None,
        "ret5_gt_0_rate": round(ret5_gt_0_count / sample_count, 3) if sample_count else None,
        "positive_rate": round(ret3_ge_5_count / sample_count, 3) if sample_count else None,
        "negative_rate": round(ret3_le_0_count / sample_count, 3) if sample_count else None,
        "edge_count": ret3_ge_5_count - ret3_le_0_count,
    }


def weak_watch_distribution(rows: Sequence[dict[str, Any]], key_fn) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    result = {}
    for key, items in grouped.items():
        summary = weak_watch_summary(items)
        sample_count = int(summary.get("sample_count") or 0)
        result[key] = {
            **summary,
            "share": round(sample_count / len(rows), 3) if rows else None,
        }
    return dict(
        sorted(
            result.items(),
            key=lambda item: (
                item[1].get("edge_count") or -999,
                item[1].get("ret3_gt_0_rate") or -999.0,
                item[1].get("sample_count") or 0,
            ),
            reverse=True,
        )
    )


def weak_watch_candidate_rows(
    distributions: dict[str, dict[str, dict[str, Any]]],
    *,
    min_samples: int,
) -> list[dict[str, Any]]:
    candidates = []
    for condition, payload in distributions.items():
        for key, summary in payload.items():
            sample_count = int(summary.get("sample_count") or 0)
            ret3_gt_0_count = int(summary.get("ret3_gt_0_count") or 0)
            ret5_gt_0_count = int(summary.get("ret5_gt_0_count") or 0)
            ret3_ge_5_count = int(summary.get("ret3_ge_5_count") or 0)
            ret3_le_0_count = int(summary.get("ret3_le_0_count") or 0)
            if sample_count < min_samples:
                continue
            if ret3_gt_0_count < ret3_le_0_count + 1:
                continue
            if ret5_gt_0_count < ret3_le_0_count + 1:
                continue
            if ret3_ge_5_count < ret3_le_0_count + 1:
                continue
            candidates.append({"condition": condition, "key": key, **summary})
    candidates.sort(
        key=lambda item: (
            item.get("edge_count") or -999,
            item.get("ret3_ge_5_count") or 0,
            item.get("ret3_gt_0_rate") or -999.0,
            item.get("ret5_gt_0_rate") or -999.0,
            item.get("sample_count") or 0,
            item.get("ret3_mean") or -999.0,
        ),
        reverse=True,
    )
    return candidates[:40]


def build_weak_watch_positive_report(rows: Sequence[dict[str, Any]], *, min_samples: int = 8) -> dict[str, Any]:
    watch_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "weak" and normalize_verdict(row.get("current_verdict")) == "WATCH"
    ]
    ret3_positive_rows = [row for row in watch_rows if (ret3 := as_float(row.get("ret3"))) is not None and ret3 > 0.0]
    ret5_positive_rows = [row for row in watch_rows if (ret5 := as_float(row.get("ret5"))) is not None and ret5 > 0.0]
    ret3_high_rows = [row for row in watch_rows if (ret3 := as_float(row.get("ret3"))) is not None and ret3 >= 5.0]
    ret3_non_positive_rows = [row for row in watch_rows if (ret3 := as_float(row.get("ret3"))) is not None and ret3 <= 0.0]
    return_groups = {
        "ret3_gt_0": weak_watch_summary(ret3_positive_rows),
        "ret5_gt_0": weak_watch_summary(ret5_positive_rows),
        "ret3_ge_5": weak_watch_summary(ret3_high_rows),
        "ret3_le_0": weak_watch_summary(ret3_non_positive_rows),
    }
    distributions = {
        "family_indicator": weak_watch_distribution(watch_rows, weak_indicator_family_key),
        "condition": weak_watch_distribution(watch_rows, weak_watch_positive_condition_key),
        "macd_wave": weak_watch_distribution(watch_rows, macd_wave_rule_key),
        "factor": weak_watch_distribution(watch_rows, factor_segment_key),
        "indicator": weak_watch_distribution(watch_rows, weak_indicator_key),
    }
    veto_rows = []
    for row in watch_rows:
        for flag in [*weak_risk_flags(row), *weak_v3_risk_flags(row)]:
            veto_rows.append({**row, "veto_flag": flag})
    veto_candidates = {
        key: summary
        for key, summary in weak_watch_distribution(veto_rows, lambda row: str(row.get("veto_flag") or "unknown")).items()
        if int(summary.get("sample_count") or 0) >= max(1, min_samples // 2)
        and int(summary.get("ret3_le_0_count") or 0) >= int(summary.get("ret3_ge_5_count") or 0)
    }
    return {
        "scope": "env=weak and current_verdict=WATCH",
        "sample_count": len(watch_rows),
        "summary": weak_watch_summary(watch_rows),
        "return_groups": return_groups,
        "upgrade_candidates": weak_watch_candidate_rows(distributions, min_samples=min_samples),
        "veto_candidates": veto_candidates,
        "positive_distributions": distributions,
        "negative_distributions": {
            "condition": weak_watch_distribution(return_groups_rows := ret3_non_positive_rows, weak_watch_positive_condition_key),
            "family_indicator": weak_watch_distribution(return_groups_rows, weak_indicator_family_key),
            "macd_wave": weak_watch_distribution(return_groups_rows, macd_wave_rule_key),
            "factor": weak_watch_distribution(return_groups_rows, factor_segment_key),
        },
        "candidate_guidance": [
            "只作为 weak WATCH -> PASS 的离线候选池，不改生产 verdict。",
            "优先看 ret3>0 与 ret5>0 同时稳定、ret3>=5 数量明显多于 ret3<=0 的组合。",
            "BBI/BIAS/OBV 只作为 family 内排序增强或二级确认，不单独作为 PASS 放行条件。",
            "命中 veto_candidates 的组合先保留 WATCH 或降权，等更多样本验证后再讨论放行。",
        ],
    }


def neutral_watch_pattern_family(row: dict[str, Any]) -> str:
    signal = str(row.get("signal") or "")
    signal_type = str(row.get("signal_type") or "")
    price = price_position_bucket(row)
    midline = value_or_unknown(row.get("midline_state"))
    support = value_or_unknown(row.get("support_stack_type"))
    compression = compression_bucket(row)
    volume = volume_bucket(row)
    kdj = kdj_bucket(row)
    hist_state = value_or_unknown(row.get("daily_macd_hist_state"))
    price_turnover = value_or_unknown(row.get("price_turnover_state"))
    if (
        signal == "B3"
        and signal_type == "trend_start"
        and price in {"near_high", "upper"}
        and midline == "above_hold"
        and support == "bull_stack"
        and compression == "tight"
        and volume in {"expanding", "normal"}
        and kdj in {"rising", "neutral"}
        and hist_state == "red_expanding"
    ):
        return "N-A"
    if (
        signal == "B2"
        and signal_type == "trend_start"
        and price in {"near_high", "upper"}
        and midline == "above_hold"
        and support == "bull_stack"
        and compression == "tight"
        and volume in {"expanding", "normal"}
        and kdj in {"neutral", "repair_from_low", "rising"}
    ):
        return "N-B"
    if (
        signal == "B3"
        and signal_type == "rebound"
        and price in {"middle", "upper", "near_high"}
        and midline == "above_hold"
        and support in {"bull_stack", "close_above_ma25"}
        and price_turnover in {"price_turnover_rise", "price_up_turnover_not"}
    ):
        return "N-C"
    return "other"


def neutral_watch_condition_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("signal") or ""),
            str(row.get("signal_type") or ""),
            f"family={neutral_watch_pattern_family(row)}",
            f"price={price_position_bucket(row)}",
            f"midline={value_or_unknown(row.get('midline_state'))}",
            f"support={value_or_unknown(row.get('support_stack_type'))}",
            f"compression={compression_bucket(row)}",
            f"volume={volume_bucket(row)}",
            f"kdj={kdj_bucket(row)}",
            f"hist={value_or_unknown(row.get('daily_macd_hist_state'))}",
            f"turnover={value_or_unknown(row.get('price_turnover_state'))}",
        ]
    )


def neutral_watch_risk_flags(row: dict[str, Any]) -> list[str]:
    signal = str(row.get("signal") or "")
    signal_type = str(row.get("signal_type") or "")
    price = price_position_bucket(row)
    volume = volume_bucket(row)
    kdj = kdj_bucket(row)
    hist_state = value_or_unknown(row.get("daily_macd_hist_state"))
    price_turnover = value_or_unknown(row.get("price_turnover_state"))
    macd_bad = weak_macd_bad(row)
    flags = []
    if signal == "B3" and signal_type == "rebound" and price == "upper" and volume == "normal" and hist_state == "green_or_zero":
        flags.append("neutral_b3_rebound_upper_no_red")
    if signal == "B2" and signal_type == "trend_start" and price == "near_high" and volume == "expanding" and kdj == "rising" and macd_bad:
        flags.append("neutral_b2_near_high_expanding_macd_bad")
    if signal == "B3" and signal_type == "trend_start" and price == "near_high" and volume == "normal" and price_turnover == "mixed":
        flags.append("neutral_b3_near_high_turnover_mixed")
    if signal == "B2" and signal_type == "rebound" and price == "extended_or_unknown" and hist_state == "green_or_zero":
        flags.append("neutral_b2_rebound_extended_no_red")
    return flags


def build_neutral_watch_positive_report(rows: Sequence[dict[str, Any]], *, min_samples: int = 8) -> dict[str, Any]:
    watch_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "neutral" and normalize_verdict(row.get("current_verdict")) == "WATCH"
    ]
    ret3_positive_rows = [row for row in watch_rows if (ret3 := as_float(row.get("ret3"))) is not None and ret3 > 0.0]
    ret5_positive_rows = [row for row in watch_rows if (ret5 := as_float(row.get("ret5"))) is not None and ret5 > 0.0]
    ret3_high_rows = [row for row in watch_rows if (ret3 := as_float(row.get("ret3"))) is not None and ret3 >= 5.0]
    ret3_non_positive_rows = [row for row in watch_rows if (ret3 := as_float(row.get("ret3"))) is not None and ret3 <= 0.0]
    return_groups = {
        "ret3_gt_0": weak_watch_summary(ret3_positive_rows),
        "ret5_gt_0": weak_watch_summary(ret5_positive_rows),
        "ret3_ge_5": weak_watch_summary(ret3_high_rows),
        "ret3_le_0": weak_watch_summary(ret3_non_positive_rows),
    }

    distributions = {
        "condition": weak_watch_distribution(watch_rows, neutral_watch_condition_key),
        "family": weak_watch_distribution(watch_rows, neutral_watch_pattern_family),
        "macd_wave": weak_watch_distribution(watch_rows, macd_wave_rule_key),
        "factor": weak_watch_distribution(watch_rows, factor_segment_key),
        "indicator": weak_watch_distribution(watch_rows, weak_indicator_key),
    }
    veto_rows = []
    for row in watch_rows:
        for flag in neutral_watch_risk_flags(row):
            veto_rows.append({**row, "veto_flag": flag})
    veto_candidates = {
        key: summary
        for key, summary in weak_watch_distribution(veto_rows, lambda row: str(row.get("veto_flag") or "unknown")).items()
        if int(summary.get("sample_count") or 0) >= max(1, min_samples // 2)
        and int(summary.get("ret3_le_0_count") or 0) >= int(summary.get("ret3_ge_5_count") or 0)
    }
    return {
        "scope": "env=neutral and current_verdict=WATCH",
        "sample_count": len(watch_rows),
        "summary": weak_watch_summary(watch_rows),
        "return_groups": return_groups,
        "upgrade_candidates": weak_watch_candidate_rows(distributions, min_samples=min_samples),
        "veto_candidates": veto_candidates,
        "positive_distributions": distributions,
        "negative_distributions": {
            "condition": weak_watch_distribution(return_groups_rows := ret3_non_positive_rows, neutral_watch_condition_key),
            "family": weak_watch_distribution(return_groups_rows, neutral_watch_pattern_family),
            "macd_wave": weak_watch_distribution(return_groups_rows, macd_wave_rule_key),
            "factor": weak_watch_distribution(return_groups_rows, factor_segment_key),
        },
        "candidate_guidance": [
            "只作为 neutral WATCH -> PASS 或 rank_score 的离线候选池，不改生产 verdict。",
            "优先验证 B3 trend_start 放量红柱延续、B2 trend_start 近高位紧压缩、B3 rebound 量价确认三类 family。",
            "neutral 不能复用 weak 的 PASS 放宽结论；需要先比较 ret3>0、ret5>0、ret3>=5 与 ret3<=0 的稳定差异。",
            "命中 veto_candidates 的组合先保留 WATCH 或降权。",
        ],
    }
    distributions = {
        "family_indicator": weak_watch_distribution(watch_rows, weak_indicator_family_key),
        "condition": weak_watch_distribution(watch_rows, weak_watch_positive_condition_key),
        "macd_wave": weak_watch_distribution(watch_rows, macd_wave_rule_key),
        "factor": weak_watch_distribution(watch_rows, factor_segment_key),
        "indicator": weak_watch_distribution(watch_rows, weak_indicator_key),
    }
    veto_rows = []
    for row in watch_rows:
        for flag in [*weak_risk_flags(row), *weak_v3_risk_flags(row)]:
            veto_rows.append({**row, "veto_flag": flag})
    veto_candidates = {
        key: summary
        for key, summary in weak_watch_distribution(veto_rows, lambda row: str(row.get("veto_flag") or "unknown")).items()
        if int(summary.get("sample_count") or 0) >= max(1, min_samples // 2)
        and int(summary.get("ret3_le_0_count") or 0) >= int(summary.get("ret3_ge_5_count") or 0)
    }
    return {
        "scope": "env=weak and current_verdict=WATCH",
        "sample_count": len(watch_rows),
        "summary": weak_watch_summary(watch_rows),
        "return_groups": return_groups,
        "upgrade_candidates": weak_watch_candidate_rows(distributions, min_samples=min_samples),
        "veto_candidates": veto_candidates,
        "positive_distributions": distributions,
        "negative_distributions": {
            "condition": weak_watch_distribution(return_groups_rows := ret3_non_positive_rows, weak_watch_positive_condition_key),
            "family_indicator": weak_watch_distribution(return_groups_rows, weak_indicator_family_key),
            "macd_wave": weak_watch_distribution(return_groups_rows, macd_wave_rule_key),
            "factor": weak_watch_distribution(return_groups_rows, factor_segment_key),
        },
        "candidate_guidance": [
            "只作为 weak WATCH -> PASS 的离线候选池，不改生产 verdict。",
            "优先看 ret3>0 与 ret5>0 同时稳定、ret3>=5 数量明显多于 ret3<=0 的组合。",
            "BBI/BIAS/OBV 只作为 family 内排序增强或二级确认，不单独作为 PASS 放行条件。",
            "命中 veto_candidates 的组合先保留 WATCH 或降权，等更多样本验证后再讨论放行。",
        ],
    }


def build_strong_neutral_risk_report(rows: Sequence[dict[str, Any]], *, min_samples: int = 5) -> dict[str, Any]:
    strong_report = build_strong_v1_negative_groups_report(rows)
    neutral_report = build_neutral_watch_positive_report(rows, min_samples=min_samples)

    strong_candidates: dict[str, dict[str, Any]] = {}
    for scope_key in ("top3", "top5"):
        scope = strong_report.get(scope_key, {})
        for key, summary in scope.get("negative_b3_condition_distribution", {}).items():
            sample_count = int(summary.get("sample_count") or 0)
            if sample_count < min_samples:
                continue
            if int(summary.get("ret3_le_0_count") or 0) < int(summary.get("ret3_ge_5_count") or 0):
                continue
            existing = strong_candidates.get(key)
            if existing is None or sample_count > int(existing.get("sample_count") or 0):
                strong_candidates[key] = {**summary, "source_scope": scope_key}

    neutral_candidates = {
        key: {**summary, "source_scope": "neutral_watch_veto"}
        for key, summary in neutral_report.get("veto_candidates", {}).items()
        if int(summary.get("sample_count") or 0) >= min_samples
        and int(summary.get("ret3_le_0_count") or 0) >= int(summary.get("ret3_ge_5_count") or 0)
    }

    return {
        "scope": "strong_v1 topN negatives + neutral WATCH veto candidates",
        "diagnosis": (
            "Aggregates strong and neutral residual loser groups into offline rank_score penalty or veto candidates. "
            "This report does not change production review verdicts."
        ),
        "strong": {
            "source": "strong_v1_negative_groups_report.top3/top5.negative_b3_condition_distribution",
            "risk_candidates": dict(
                sorted(strong_candidates.items(), key=lambda item: int(item[1].get("sample_count") or 0), reverse=True)
            ),
        },
        "neutral": {
            "source": "neutral_watch_positive_report.veto_candidates",
            "risk_candidates": dict(
                sorted(neutral_candidates.items(), key=lambda item: int(item[1].get("sample_count") or 0), reverse=True)
            ),
        },
        "next_step": [
            "strong 先将高频 topN 负例组合做 rank_score 扣分实验，不直接改 verdict。",
            "neutral 先把 veto_candidates 用于 WATCH 内降权；未出现 ret3/ret5 同时干净的组合前不做 PASS 放宽。",
            "每个候选进入生产前必须重新跑 Phase 7 指标，并列出新增 top5 负例与被挤出正例。",
        ],
    }


def neutral_factor_value(row: dict[str, Any], factor: str) -> str:
    if factor == "signal_combo":
        return f"{value_or_unknown(row.get('signal'))}|{value_or_unknown(row.get('signal_type'))}"
    if factor == "price_bucket":
        return price_position_bucket(row)
    if factor == "compression":
        return compression_bucket(row)
    if factor == "volume":
        return volume_bucket(row)
    if factor == "kdj":
        return kdj_bucket(row)
    if factor == "macd_wave":
        return macd_wave_rule_key(row)
    mapping = {
        "signal": "signal",
        "signal_type": "signal_type",
        "midline_state": "midline_state",
        "support_stack": "support_stack_type",
        "daily_macd_hist": "daily_macd_hist_state",
        "price_turnover": "price_turnover_state",
        "bbi_bias": "bbi_bias_state",
        "bias": "bias_bucket",
        "obv": "obv_state",
    }
    return value_or_unknown(row.get(mapping[factor]))


def build_neutral_factor_effect_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    neutral_rows = [row for row in rows if str(row.get("env") or "") == "neutral" and as_float(row.get("ret3")) is not None]
    positive_rows = [row for row in neutral_rows if (as_float(row.get("ret3")) or -999.0) > 5.0]
    pass_watch_positive_rows = [
        row for row in positive_rows if normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
    ]
    factors = [
        "signal_combo",
        "signal",
        "signal_type",
        "price_bucket",
        "midline_state",
        "support_stack",
        "compression",
        "volume",
        "kdj",
        "daily_macd_hist",
        "price_turnover",
        "bbi_bias",
        "bias",
        "obv",
        "macd_wave",
    ]
    factor_effects: dict[str, dict[str, dict[str, Any]]] = {}
    majority_positive_features: list[dict[str, Any]] = []
    for factor in factors:
        base_counts = Counter(neutral_factor_value(row, factor) for row in neutral_rows)
        positive_counts = Counter(neutral_factor_value(row, factor) for row in positive_rows)
        pass_watch_counts = Counter(neutral_factor_value(row, factor) for row in pass_watch_positive_rows)
        factor_payload: dict[str, dict[str, Any]] = {}
        for value, positive_count in sorted(positive_counts.items()):
            base_count = base_counts.get(value, 0)
            pass_watch_count = pass_watch_counts.get(value, 0)
            ret3_share = positive_count / len(positive_rows) if positive_rows else 0.0
            base_share = base_count / len(neutral_rows) if neutral_rows else 0.0
            pass_watch_share = pass_watch_count / len(pass_watch_positive_rows) if pass_watch_positive_rows else 0.0
            payload = {
                "base_count": base_count,
                "base_share": round(base_share, 4),
                "ret3_gt_5_count": positive_count,
                "ret3_gt_5_share": round(ret3_share, 4),
                "uplift": round(ret3_share - base_share, 4),
                "pass_watch_ret3_gt_5_count": pass_watch_count,
                "pass_watch_ret3_gt_5_share": round(pass_watch_share, 4),
            }
            factor_payload[value] = payload
            if ret3_share >= 0.5 and ret3_share > base_share:
                majority_positive_features.append({"factor": factor, "key": f"{factor}={value}", **payload})
        factor_effects[factor] = dict(
            sorted(factor_payload.items(), key=lambda item: (item[1]["ret3_gt_5_share"], item[1]["uplift"]), reverse=True)
        )
    majority_positive_features.sort(key=lambda item: (item["ret3_gt_5_share"], item["uplift"]), reverse=True)
    return {
        "scope": "env=neutral, factor frequencies among ret3>5 samples",
        "sample_count": len(neutral_rows),
        "ret3_gt_5_count": len(positive_rows),
        "pass_watch_ret3_gt_5_count": len(pass_watch_positive_rows),
        "factor_effects": factor_effects,
        "majority_positive_features": majority_positive_features,
        "guidance": [
            "多数 ret3>5 样本拥有且相对 neutral 基准有 uplift 的因子，才视作正向参考。",
            "高占比但 uplift 为负的因子只是环境基准特征，不应当单独加分。",
            "neutral 仍需和 veto/risk 条件一起使用；当前不直接扩 PASS。",
        ],
    }


def neutral_positive_score(row: dict[str, Any]) -> float:
    score = 0.0
    if str(row.get("signal_type") or "") == "trend_start":
        score += 0.10
    if str(row.get("signal") or "") == "B2" and str(row.get("signal_type") or "") == "trend_start":
        score += 0.08
    if price_position_bucket(row) == "upper":
        score += 0.10
    if value_or_unknown(row.get("midline_state")) == "above_hold":
        score += 0.16
    if value_or_unknown(row.get("support_stack_type")) == "bull_stack":
        score += 0.08
    if compression_bucket(row) == "tight":
        score += 0.06
    if volume_bucket(row) == "normal":
        score += 0.04
    if value_or_unknown(row.get("bbi_bias_state")) == "above_extended":
        score += 0.08
    return score


def neutral_ranked_sample(row: dict[str, Any]) -> dict[str, Any]:
    positive_score = neutral_positive_score(row)
    risk_flags = neutral_watch_risk_flags(row)
    risk_penalty = (
        (0.30 if "neutral_b2_near_high_expanding_macd_bad" in risk_flags else 0.0)
        + (0.62 if "neutral_b2_rebound_extended_no_red" in risk_flags else 0.0)
        + (0.18 if "neutral_b3_rebound_upper_no_red" in risk_flags else 0.0)
        + (0.20 if "neutral_b3_near_high_turnover_mixed" in risk_flags else 0.0)
    )
    current_score = as_float(row.get("current_score")) or 0.0
    return {
        "date": row.get("date"),
        "code": row.get("code"),
        "verdict": row.get("current_verdict"),
        "current_score": row.get("current_score"),
        "neutral_positive_score": round(positive_score, 3),
        "neutral_risk_penalty": round(risk_penalty, 3),
        "neutral_risk_flags": risk_flags,
        "neutral_v1_rank_score": round(current_score + positive_score - risk_penalty, 3),
        "ret3": row.get("ret3"),
        "ret5": row.get("ret5"),
        "signal": row.get("signal"),
        "signal_type": row.get("signal_type"),
        "factor_segment": factor_segment_key(row),
        "macd_wave_rule": macd_wave_rule_key(row),
    }


def build_neutral_watch_ranking_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    neutral_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "neutral" and normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
    ]
    ranked_samples = [neutral_ranked_sample(row) for row in neutral_rows]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in ranked_samples:
        by_date[str(sample.get("date"))].append(sample)
    ranking_variants = {
        "current_score": "current_score",
        "neutral_v1_rank": "neutral_v1_rank_score",
    }
    top3_by_variant = {name: [] for name in ranking_variants}
    top5_by_variant = {name: [] for name in ranking_variants}
    daily_top3 = []
    for date_key, date_samples in sorted(by_date.items()):
        day_payload: dict[str, Any] = {"date": date_key}
        for variant_name, score_key in ranking_variants.items():
            ranked = sorted(
                date_samples,
                key=lambda sample: (
                    as_float(sample.get(score_key)) or -999.0,
                    as_float(sample.get("current_score")) or 0.0,
                ),
                reverse=True,
            )
            top3 = ranked[:3]
            top5 = ranked[:5]
            top3_by_variant[variant_name].extend(top3)
            top5_by_variant[variant_name].extend(top5)
            day_payload[variant_name] = top3
            day_payload[f"{variant_name}_top5"] = top5
        daily_top3.append(day_payload)
    return {
        "scope": "env=neutral and verdict in PASS/WATCH",
        "sample_count": len(neutral_rows),
        "candidate_count": len(ranked_samples),
        "ranking_variants": {
            "current_score": "baseline: existing current_score order",
            "neutral_v1_rank": "diagnostic candidate: neutral positive skeleton boosts minus neutral veto/risk penalties",
        },
        "top3_comparison": {name: summarize_ranked_samples(samples) for name, samples in top3_by_variant.items()},
        "top5_comparison": {name: summarize_ranked_samples(samples) for name, samples in top5_by_variant.items()},
        "daily_top3": daily_top3,
        "ranked_samples": sorted(
            ranked_samples,
            key=lambda sample: (
                str(sample.get("date")),
                -(as_float(sample.get("neutral_v1_rank_score")) or -999.0),
            ),
        ),
        "diagnosis": (
            "neutral_v1 is an offline WATCH/PASS+WATCH ranking experiment using the neutral positive skeleton "
            "and neutral veto candidates. Do not change production verdict before Phase 7 comparison improves."
        ),
    }


def build_neutral_v1_stability_report(ranking_report: dict[str, Any]) -> dict[str, Any]:
    daily_deltas = []
    regression_days = []
    top3_loss_samples = []
    risk_flag_rows = []
    improved_days = 0
    regressed_days = 0
    neutral_better_positive_days = 0
    neutral_lower_negative_days = 0

    for day in ranking_report.get("daily_top3", []):
        date_key = str(day.get("date"))
        current_top3 = list(day.get("current_score", []))
        neutral_top3 = list(day.get("neutral_v1_rank", []))
        current_summary = summarize_ranked_samples(current_top3)
        neutral_summary = summarize_ranked_samples(neutral_top3)
        ret3_ge_5_delta = int(neutral_summary.get("ret3_ge_5_count") or 0) - int(
            current_summary.get("ret3_ge_5_count") or 0
        )
        ret3_le_0_delta = int(neutral_summary.get("ret3_le_0_count") or 0) - int(
            current_summary.get("ret3_le_0_count") or 0
        )
        ret3_mean_delta = round(
            (as_float(neutral_summary.get("ret3_mean")) or 0.0) - (as_float(current_summary.get("ret3_mean")) or 0.0),
            2,
        )
        delta = {
            "date": date_key,
            "current_top3": current_summary,
            "neutral_v1_top3": neutral_summary,
            "ret3_ge_5_delta": ret3_ge_5_delta,
            "ret3_le_0_delta": ret3_le_0_delta,
            "ret3_mean_delta": ret3_mean_delta,
        }
        daily_deltas.append(delta)
        if ret3_ge_5_delta > 0 or ret3_mean_delta > 0:
            improved_days += 1
        if ret3_le_0_delta > 0 or ret3_mean_delta < 0:
            regressed_days += 1
            regression_days.append(delta)
        if ret3_ge_5_delta > 0:
            neutral_better_positive_days += 1
        if ret3_le_0_delta < 0:
            neutral_lower_negative_days += 1
        for sample in neutral_top3:
            if (as_float(sample.get("ret3")) or 0.0) <= 0.0:
                loss_sample = {
                    "date": date_key,
                    "code": sample.get("code"),
                    "verdict": sample.get("verdict"),
                    "current_score": sample.get("current_score"),
                    "neutral_v1_rank_score": sample.get("neutral_v1_rank_score"),
                    "neutral_positive_score": sample.get("neutral_positive_score"),
                    "neutral_risk_penalty": sample.get("neutral_risk_penalty"),
                    "neutral_risk_flags": sample.get("neutral_risk_flags", []),
                    "ret3": sample.get("ret3"),
                    "ret5": sample.get("ret5"),
                    "signal": sample.get("signal"),
                    "signal_type": sample.get("signal_type"),
                    "factor_segment": sample.get("factor_segment"),
                    "macd_wave_rule": sample.get("macd_wave_rule"),
                }
                top3_loss_samples.append(loss_sample)
                for flag in sample.get("neutral_risk_flags", []):
                    risk_flag_rows.append({**loss_sample, "neutral_risk_flag": flag})

    top3_loss_samples.sort(key=lambda sample: as_float(sample.get("ret3")) or 0.0)
    return {
        "scope": "neutral_v1 daily top3 stability and loss review",
        "daily_summary": {
            "day_count": len(daily_deltas),
            "improved_days": improved_days,
            "regressed_days": regressed_days,
            "neutral_better_positive_days": neutral_better_positive_days,
            "neutral_lower_negative_days": neutral_lower_negative_days,
        },
        "daily_deltas": daily_deltas,
        "regression_days": regression_days,
        "top3_loss_summary": summarize_ranked_samples(top3_loss_samples),
        "top3_loss_risk_flags": distribution_summary(risk_flag_rows, lambda row: str(row.get("neutral_risk_flag") or "none")),
        "top3_loss_signal_distribution": distribution_summary(
            top3_loss_samples,
            lambda row: f"{value_or_unknown(row.get('signal'))}|{value_or_unknown(row.get('signal_type'))}",
        ),
        "top3_loss_factor_distribution": distribution_summary(
            top3_loss_samples, lambda row: str(row.get("factor_segment") or "unknown")
        ),
        "top3_loss_macd_distribution": distribution_summary(
            top3_loss_samples, lambda row: str(row.get("macd_wave_rule") or "unknown")
        ),
        "top3_loss_samples": top3_loss_samples[:80],
        "diagnosis": (
            "neutral_v1 improves aggregate top3, but production rank_score should wait until regression days and "
            "top3 loss samples are reviewed by date and risk flag."
        ),
    }


def build_neutral_v2_veto_report(ranking_report: dict[str, Any]) -> dict[str, Any]:
    neutral_v1_top3 = [sample for day in ranking_report.get("daily_top3", []) for sample in day.get("neutral_v1_rank", [])]

    def loss_only_candidates(key_fn: Callable[[dict[str, Any]], str]) -> dict[str, dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in neutral_v1_top3:
            groups[key_fn(sample)].append(sample)
        candidates = {}
        for key, samples in groups.items():
            summary = summarize_ranked_samples(samples)
            if (summary.get("ret3_le_0_count") or 0) >= 2 and (summary.get("ret3_ge_5_count") or 0) == 0:
                candidates[key] = summary
        return dict(
            sorted(
                candidates.items(),
                key=lambda item: (
                    item[1].get("ret3_le_0_count") or 0,
                    -(item[1].get("ret3_ge_5_count") or 0),
                    -(as_float(item[1].get("ret3_mean")) or 0.0),
                ),
                reverse=True,
            )
        )

    factor_candidates = loss_only_candidates(lambda sample: str(sample.get("factor_segment") or "unknown"))
    macd_candidates = loss_only_candidates(lambda sample: str(sample.get("macd_wave_rule") or "unknown"))
    factor_keys = set(factor_candidates)
    macd_keys = set(macd_candidates)

    ranked_samples = []
    for sample in ranking_report.get("ranked_samples", []):
        factor_hit = str(sample.get("factor_segment") or "unknown") in factor_keys
        macd_hit = str(sample.get("macd_wave_rule") or "unknown") in macd_keys
        penalty = (0.65 if factor_hit else 0.0) + (0.35 if macd_hit else 0.0)
        v1_score = as_float(sample.get("neutral_v1_rank_score")) or -999.0
        ranked_samples.append(
            {
                **sample,
                "neutral_v2_penalty": round(penalty, 3),
                "neutral_v2_veto_hits": [
                    hit
                    for hit in [
                        "factor_loss_only" if factor_hit else None,
                        "macd_loss_only" if macd_hit else None,
                    ]
                    if hit
                ],
                "neutral_v2_rank_score": round(v1_score - penalty, 3),
            }
        )

    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in ranked_samples:
        by_date[str(sample.get("date"))].append(sample)

    top3_by_variant = {"neutral_v1_rank": [], "neutral_v2_rank": []}
    top5_by_variant = {"neutral_v1_rank": [], "neutral_v2_rank": []}
    daily_top3 = []
    for date_key, date_samples in sorted(by_date.items()):
        v1_ranked = sorted(
            date_samples,
            key=lambda sample: (
                as_float(sample.get("neutral_v1_rank_score")) or -999.0,
                as_float(sample.get("current_score")) or 0.0,
            ),
            reverse=True,
        )
        v2_ranked = sorted(
            date_samples,
            key=lambda sample: (
                as_float(sample.get("neutral_v2_rank_score")) or -999.0,
                as_float(sample.get("neutral_v1_rank_score")) or -999.0,
                as_float(sample.get("current_score")) or 0.0,
            ),
            reverse=True,
        )
        top3_by_variant["neutral_v1_rank"].extend(v1_ranked[:3])
        top3_by_variant["neutral_v2_rank"].extend(v2_ranked[:3])
        top5_by_variant["neutral_v1_rank"].extend(v1_ranked[:5])
        top5_by_variant["neutral_v2_rank"].extend(v2_ranked[:5])
        daily_top3.append(
            {
                "date": date_key,
                "neutral_v1_rank": v1_ranked[:3],
                "neutral_v2_rank": v2_ranked[:3],
                "neutral_v1_rank_top5": v1_ranked[:5],
                "neutral_v2_rank_top5": v2_ranked[:5],
            }
        )

    penalized_samples = [sample for sample in ranked_samples if (as_float(sample.get("neutral_v2_penalty")) or 0.0) > 0.0]
    return {
        "scope": "neutral_v2 offline veto/risk experiment from neutral_v1 top3 loss-only groups",
        "veto_candidates": {
            "factor": factor_candidates,
            "macd": macd_candidates,
        },
        "top3_comparison": {name: summarize_ranked_samples(samples) for name, samples in top3_by_variant.items()},
        "top5_comparison": {name: summarize_ranked_samples(samples) for name, samples in top5_by_variant.items()},
        "daily_top3": daily_top3,
        "penalized_summary": summarize_ranked_samples(penalized_samples),
        "penalized_samples": sorted(
            penalized_samples,
            key=lambda sample: (
                str(sample.get("date")),
                -(as_float(sample.get("neutral_v2_penalty")) or 0.0),
                -(as_float(sample.get("neutral_v1_rank_score")) or -999.0),
            ),
        )[:120],
        "diagnosis": (
            "neutral_v2 penalizes only loss-only factor/MACD groups from neutral_v1 top3. Keep this offline until "
            "top3/top5 metrics improve without materially reducing ret3>=5 capture."
        ),
    }


def parse_factor_segment(segment: Any) -> dict[str, str]:
    parts = str(segment or "").split("|")
    parsed: dict[str, str] = {}
    if len(parts) >= 3:
        parsed["env"] = parts[0]
        parsed["signal"] = parts[1]
        parsed["signal_type"] = parts[2]
    for part in parts[3:]:
        if "=" in part:
            key, value = part.split("=", 1)
            parsed[key] = value
    return parsed


def pass_watch_skeleton_key(sample: dict[str, Any]) -> str:
    parsed = parse_factor_segment(sample.get("factor_segment"))
    price = parsed.get("price", "unknown")
    if price in {"upper", "near_high"}:
        price = "upper_or_near_high"
    return "|".join(
        [
            parsed.get("signal") or value_or_unknown(sample.get("signal")),
            parsed.get("signal_type") or value_or_unknown(sample.get("signal_type")),
            f"price={price}",
            f"midline={parsed.get('midline', 'unknown')}",
            f"support={parsed.get('support', 'unknown')}",
        ]
    )


def pass_watch_full_group_key(sample: dict[str, Any]) -> str:
    parsed = parse_factor_segment(sample.get("factor_segment"))
    price = parsed.get("price", "unknown")
    if price in {"upper", "near_high"}:
        price = "upper_or_near_high"
    return "|".join(
        [
            parsed.get("signal") or value_or_unknown(sample.get("signal")),
            parsed.get("signal_type") or value_or_unknown(sample.get("signal_type")),
            f"price={price}",
            f"midline={parsed.get('midline', 'unknown')}",
            f"support={parsed.get('support', 'unknown')}",
            f"compression={parsed.get('compression', 'unknown')}",
            f"volume={parsed.get('volume', 'unknown')}",
            f"kdj={parsed.get('kdj', 'unknown')}",
        ]
    )


def build_pass_watch_high_ret3_group_report(ranking_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    environments = {}
    for env, report in ranking_reports.items():
        samples = [sample for sample in report.get("ranked_samples", []) if as_float(sample.get("ret3")) is not None]
        high_samples = [sample for sample in samples if (as_float(sample.get("ret3")) or 0.0) >= 5.0]
        by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in high_samples:
            by_date[str(sample.get("date"))].append(sample)
        daily_best = []
        for date_key, date_samples in sorted(by_date.items()):
            best = max(date_samples, key=lambda sample: as_float(sample.get("ret3")) or -999.0)
            daily_best.append({**best, "skeleton_group": pass_watch_skeleton_key(best), "full_group": pass_watch_full_group_key(best)})

        skeleton_distribution = distribution_summary(daily_best, pass_watch_skeleton_key)
        full_distribution = distribution_summary(daily_best, pass_watch_full_group_key)
        macd_distribution = distribution_summary(daily_best, lambda sample: str(sample.get("macd_wave_rule") or "unknown"))
        day_count = len(daily_best)
        priority_groups = []
        for key, summary in skeleton_distribution.items():
            coverage = round((summary.get("sample_count") or 0) / day_count, 4) if day_count else 0.0
            if (summary.get("sample_count") or 0) >= 2:
                priority_groups.append({"group": key, "coverage": coverage, **summary})
        priority_groups.sort(key=lambda item: (item.get("coverage") or 0.0, item.get("ret3_mean") or 0.0), reverse=True)

        environments[env] = {
            "sample_count": len(samples),
            "high_ret3_count": len(high_samples),
            "high_ret3_days": len(by_date),
            "high_ret3_distribution": {
                "skeleton": distribution_summary(high_samples, pass_watch_skeleton_key),
                "full_group": distribution_summary(high_samples, pass_watch_full_group_key),
                "macd": distribution_summary(high_samples, lambda sample: str(sample.get("macd_wave_rule") or "unknown")),
            },
            "daily_best_summary": {
                "day_count": day_count,
                "best_ret3_gt_0_days": sum(1 for sample in daily_best if (as_float(sample.get("ret3")) or 0.0) > 0.0),
                "ret3_mean": round(sum(as_float(sample.get("ret3")) or 0.0 for sample in daily_best) / day_count, 2)
                if day_count
                else None,
                "ret3_median": median([as_float(sample.get("ret3")) for sample in daily_best]),
            },
            "daily_best_skeleton_distribution": skeleton_distribution,
            "daily_best_full_group_distribution": full_distribution,
            "daily_best_macd_distribution": macd_distribution,
            "priority_skeleton_groups": priority_groups,
            "daily_best_samples": sorted(daily_best, key=lambda sample: (str(sample.get("date")), -(as_float(sample.get("ret3")) or 0.0))),
        }
    return {
        "scope": "PASS+WATCH ret3>=5 group statistics and daily best priority groups",
        "environments": environments,
        "diagnosis": (
            "Use skeleton groups to decide offline rank priority for daily榜首. Full factor groups are too sparse; "
            "production changes should wait until a priority group improves daily top1 without broad PASS expansion."
        ),
    }


def summarize_top1_samples(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_ranked_samples(samples)
    sample_count = int(summary.get("sample_count") or 0)
    ret3_gt_0_count = sum(1 for sample in samples if (as_float(sample.get("ret3")) or -999.0) > 0.0)
    return {
        **summary,
        "ret3_gt_0_count": ret3_gt_0_count,
        "ret3_gt_0_rate": round(ret3_gt_0_count / sample_count, 3) if sample_count else None,
    }


def build_env_skeleton_top1_report(
    high_ret3_group_report: dict[str, Any], ranking_reports: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    environments = {}
    high_envs = high_ret3_group_report.get("environments", {})
    for env, ranking_report in sorted(ranking_reports.items()):
        priority_groups = high_envs.get(env, {}).get("priority_skeleton_groups", [])
        group_weights = {
            str(group.get("group")): 0.45 + (as_float(group.get("coverage")) or 0.0)
            for group in priority_groups
            if group.get("group")
        }
        by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in ranking_report.get("ranked_samples", []):
            if as_float(sample.get("ret3")) is None:
                continue
            skeleton = pass_watch_skeleton_key(sample)
            boost = group_weights.get(skeleton, 0.0)
            base_score = as_float(sample.get("current_score")) or 0.0
            ranked = {
                **sample,
                "skeleton_group": skeleton,
                "skeleton_top1_boost": round(boost, 3),
                "skeleton_top1_score": round(base_score + boost, 3),
            }
            by_date[str(sample.get("date"))].append(ranked)

        current_top1 = []
        skeleton_top1 = []
        daily_top1 = []
        for date_key, samples in sorted(by_date.items()):
            current = max(samples, key=lambda sample: as_float(sample.get("current_score")) or -999.0)
            skeleton = max(
                samples,
                key=lambda sample: (
                    as_float(sample.get("skeleton_top1_score")) or -999.0,
                    as_float(sample.get("current_score")) or -999.0,
                ),
            )
            current_top1.append(current)
            skeleton_top1.append(skeleton)
            daily_top1.append({"date": date_key, "current_score": current, "skeleton_rank": skeleton})

        skeleton_from_group = [sample for sample in skeleton_top1 if (as_float(sample.get("skeleton_top1_boost")) or 0.0) > 0.0]
        environments[env] = {
            "priority_skeleton_groups": priority_groups,
            "day_count": len(daily_top1),
            "skeleton_top1_from_group_days": len(skeleton_from_group),
            "top1_comparison": {
                "current_score": summarize_top1_samples(current_top1),
                "skeleton_rank": summarize_top1_samples(skeleton_top1),
            },
            "skeleton_top1_group_distribution": distribution_summary(skeleton_from_group, lambda sample: str(sample.get("skeleton_group"))),
            "daily_top1": daily_top1,
            "diagnosis": (
                "offline_candidate"
                if summarize_top1_samples(skeleton_top1).get("ret3_le_0_count", 0)
                <= summarize_top1_samples(current_top1).get("ret3_le_0_count", 0)
                else "needs_narrower_veto"
            ),
        }
    return {
        "scope": "environment-specific PASS+WATCH top1 skeleton ranking simulation",
        "environments": environments,
        "diagnosis": "Each environment uses only its own high-ret3 priority skeleton groups; no shared skeleton is forced across environments.",
    }


def build_weak_v2_negative_groups_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    weak_rows = [
        row
        for row in rows
        if str(row.get("env") or "") == "weak" and normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}
    ]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in weak_rows:
        ranked = weak_ranked_sample(row)
        by_date[str(row.get("date"))].append({**row, **ranked})

    def build_scope(limit: int) -> dict[str, Any]:
        selected = []
        for date_key, date_rows in sorted(by_date.items()):
            ranked_rows = sorted(
                date_rows,
                key=lambda row: (
                    as_float(row.get("weak_v2_rank_score")) or -999.0,
                    as_float(row.get("current_score")) or 0.0,
                ),
                reverse=True,
            )
            for rank, row in enumerate(ranked_rows[:limit], start=1):
                selected.append({**row, "weak_v2_daily_rank": rank, "date": date_key})
        negatives = [row for row in selected if (as_float(row.get("ret3")) or 999.0) <= 0.0]
        positives = [row for row in selected if (as_float(row.get("ret3")) or -999.0) >= 5.0]
        return {
            "sample_count": len(selected),
            "positive_summary": summarize_rows(positives),
            "negative_summary": summarize_rows(negatives),
            "negative_family_distribution": distribution_summary(negatives, weak_pattern_family),
            "negative_factor_distribution": distribution_summary(negatives, factor_segment_key),
            "negative_macd_wave_distribution": distribution_summary(negatives, macd_wave_rule_key),
            "negative_condition_distribution": distribution_summary(negatives, weak_condition_key),
            "negative_risk_flag_distribution": distribution_summary(
                [{**row, "weak_risk_flag": flag} for row in negatives for flag in row.get("weak_risk_flags", [])],
                lambda row: str(row.get("weak_risk_flag") or "unknown"),
            ),
            "worst_samples": [
                {
                    **sample_brief(row),
                    "family": weak_pattern_family(row),
                    "weak_v2_daily_rank": row.get("weak_v2_daily_rank"),
                    "weak_v2_rank_score": row.get("weak_v2_rank_score"),
                    "factor_segment": factor_segment_key(row),
                    "macd_wave_rule": macd_wave_rule_key(row),
                    "negative_condition": weak_condition_key(row),
                    "weak_risk_flags": row.get("weak_risk_flags", []),
                    "daily_macd_hist_state": row.get("daily_macd_hist_state"),
                    "price_turnover_state": row.get("price_turnover_state"),
                }
                for row in sorted(negatives, key=lambda item: as_float(item.get("ret3")) or 0.0)[:40]
            ],
        }

    return {
        "scope": "env=weak, verdict in PASS/WATCH, daily weak_v2_rank topN negative samples",
        "diagnosis": (
            "Traces remaining weak_v2 ranked losers so weak-specific veto/risk candidates can be evaluated before changing production review."
        ),
        "top3": build_scope(3),
        "top5": build_scope(5),
    }


def classify_misclassified(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    pass_poor = []
    missed_high = []
    ranking_mismatch = []
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ret3 = as_float(row.get("ret3"))
        if ret3 is None:
            continue
        verdict = normalize_verdict(row.get("current_verdict"))
        if verdict == "PASS" and ret3 <= 0.0:
            pass_poor.append(row)
        if verdict in {"WATCH", "FAIL"} and ret3 >= 5.0:
            missed_high.append(row)
        by_date[str(row.get("date"))].append(row)
    for date_rows in by_date.values():
        eligible = [row for row in date_rows if normalize_verdict(row.get("current_verdict")) in {"PASS", "WATCH"}]
        ranked = sorted(eligible, key=lambda row: as_float(row.get("current_score")) or 0.0, reverse=True)
        for idx, row in enumerate(ranked, start=1):
            ret3 = as_float(row.get("ret3"))
            if ret3 is not None and ret3 >= 5.0 and idx > 10:
                ranking_mismatch.append({**row, "current_rank": idx})
    return {
        "pass_poor": sorted(pass_poor, key=lambda row: as_float(row.get("ret3")) or 0.0)[:50],
        "missed_high": sorted(missed_high, key=lambda row: as_float(row.get("ret3")) or 0.0, reverse=True)[:50],
        "ranking_mismatch": sorted(
            ranking_mismatch,
            key=lambda row: (str(row.get("date")), int(row.get("current_rank") or 0)),
        )[:50],
    }


def collect_feature_rows(
    *,
    runtime_root: Path,
    method: str,
    start_date: str,
    end_date: str,
    price_rows: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    env_by_date = load_environment_by_date(runtime_root)
    rows = []
    for review_dir in review_dirs(runtime_root, method, start_date, end_date):
        pick_date = review_dir.name.removesuffix(f".{method}")
        summary_path = review_dir / "summary.json"
        summary = {}
        if summary_path.exists():
            try:
                parsed = json.loads(summary_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    summary = parsed
            except json.JSONDecodeError:
                summary = {}
        env = env_from_summary(summary, env_by_date.get(pick_date, "unknown"))
        for review in load_reviews_for_dir(review_dir):
            code = str(review.get("code") or "").strip()
            if not code:
                continue
            rows.append(
                extract_feature_row(
                    pick_date=pick_date,
                    code=code,
                    env=env,
                    review=review,
                    forward=forward_returns(price_rows.get(code, []), pick_date),
                    context=compute_context_features(price_rows.get(code, []), pick_date),
                )
            )
    return rows


def write_features_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_recommendations(
    segments: dict[str, dict[str, Any]],
    macd_segments: dict[str, dict[str, Any]] | None = None,
    factor_segments: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ranked = sorted(
        segments.items(),
        key=lambda item: (
            item[1].get("sample_count", 0),
            item[1].get("ret3_ge_5_count", 0) - item[1].get("ret3_le_0_count", 0),
            item[1].get("ret3_mean") or -999.0,
        ),
        reverse=True,
    )
    promising = [
        {"segment": key, **value}
        for key, value in ranked
        if value.get("sample_count", 0) >= 3 and value.get("ret3_ge_5_count", 0) > value.get("ret3_le_0_count", 0)
    ][:20]
    risky = [
        {"segment": key, **value}
        for key, value in ranked
        if value.get("sample_count", 0) >= 3 and value.get("ret3_le_0_count", 0) >= value.get("ret3_ge_5_count", 0)
    ][:20]
    payload = {
        "next_step": "Use these segments to inspect stable high-ret3 WATCH forms before changing production verdict rules.",
        "promising_segments": promising,
        "risky_segments": risky,
    }
    if macd_segments is not None:
        macd_ranked = sorted(
            macd_segments.items(),
            key=lambda item: (
                item[1].get("sample_count", 0),
                item[1].get("ret3_ge_5_count", 0) - item[1].get("ret3_le_0_count", 0),
                item[1].get("ret3_mean") or -999.0,
            ),
            reverse=True,
        )
        payload["promising_macd_segments"] = [
            {"segment": key, **value}
            for key, value in macd_ranked
            if value.get("sample_count", 0) >= 3 and value.get("ret3_ge_5_count", 0) > value.get("ret3_le_0_count", 0)
        ][:20]
        payload["risky_macd_segments"] = [
            {"segment": key, **value}
            for key, value in macd_ranked
            if value.get("sample_count", 0) >= 3 and value.get("ret3_le_0_count", 0) >= value.get("ret3_ge_5_count", 0)
        ][:20]
    if factor_segments is not None:
        factor_ranked = sorted(
            factor_segments.items(),
            key=lambda item: (
                item[1].get("sample_count", 0),
                item[1].get("ret3_ge_5_count", 0) - item[1].get("ret3_le_0_count", 0),
                item[1].get("ret3_mean") or -999.0,
            ),
            reverse=True,
        )
        payload["promising_factor_segments"] = [
            {"segment": key, **value}
            for key, value in factor_ranked
            if value.get("sample_count", 0) >= 3 and value.get("ret3_ge_5_count", 0) > value.get("ret3_le_0_count", 0)
        ][:20]
        payload["risky_factor_segments"] = [
            {"segment": key, **value}
            for key, value in factor_ranked
            if value.get("sample_count", 0) >= 3 and value.get("ret3_le_0_count", 0) >= value.get("ret3_ge_5_count", 0)
        ][:20]
    return payload


def segment_with_rates(segment: str, payload: dict[str, Any]) -> dict[str, Any]:
    sample_count = int(payload.get("sample_count") or 0)
    ret3_ge_5 = int(payload.get("ret3_ge_5_count") or 0)
    ret3_le_0 = int(payload.get("ret3_le_0_count") or 0)
    positive_rate = round(ret3_ge_5 / sample_count, 3) if sample_count else None
    negative_rate = round(ret3_le_0 / sample_count, 3) if sample_count else None
    return {
        "segment": segment,
        **payload,
        "positive_rate": positive_rate,
        "negative_rate": negative_rate,
        "edge_count": ret3_ge_5 - ret3_le_0,
    }


def classify_stable_segment(segment: str, payload: dict[str, Any], min_samples: int) -> tuple[str, dict[str, Any]] | None:
    sample_count = int(payload.get("sample_count") or 0)
    if sample_count < min_samples:
        return None
    item = segment_with_rates(segment, payload)
    ret3_ge_5 = int(payload.get("ret3_ge_5_count") or 0)
    ret3_le_0 = int(payload.get("ret3_le_0_count") or 0)
    ret3_mean = as_float(payload.get("ret3_mean")) or 0.0
    if ret3_ge_5 >= ret3_le_0 + 3 and ret3_mean > 0.0:
        return ("promising", item)
    if ret3_le_0 >= ret3_ge_5 + 3 and ret3_mean < 1.0:
        return ("risky", item)
    if sample_count >= min_samples * 2:
        return ("mixed_high_sample", item)
    return None


def stable_patterns_for_segments(segments: dict[str, dict[str, Any]], min_samples: int) -> dict[str, list[dict[str, Any]]]:
    result = {"promising": [], "risky": [], "mixed_high_sample": []}
    for segment, payload in segments.items():
        classified = classify_stable_segment(segment, payload, min_samples)
        if classified is None:
            continue
        bucket, item = classified
        result[bucket].append(item)
    result["promising"].sort(key=lambda item: (item["edge_count"], item.get("ret3_mean") or -999, item["sample_count"]), reverse=True)
    result["risky"].sort(key=lambda item: (-item["edge_count"], -(item.get("ret3_mean") or 999), item["sample_count"]), reverse=True)
    result["mixed_high_sample"].sort(key=lambda item: item["sample_count"], reverse=True)
    return {key: value[:30] for key, value in result.items()}


def build_stable_patterns(
    *,
    base_segments: dict[str, dict[str, Any]],
    macd_segments: dict[str, dict[str, Any]],
    factor_segments: dict[str, dict[str, Any]],
    min_samples: int = 10,
) -> dict[str, Any]:
    return {
        "min_samples": min_samples,
        "base": stable_patterns_for_segments(base_segments, min_samples),
        "macd": stable_patterns_for_segments(macd_segments, min_samples),
        "factor": stable_patterns_for_segments(factor_segments, min_samples),
    }


def write_stable_patterns_markdown(path: Path, patterns: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Stable Patterns",
        "",
        f"- min_samples: {patterns.get('min_samples')}",
        "",
    ]
    for group in ("base", "macd", "factor"):
        lines.extend([f"## {group}", ""])
        for bucket, title in [
            ("promising", "Promising"),
            ("risky", "Risky"),
            ("mixed_high_sample", "Mixed High Sample"),
        ]:
            lines.extend(
                [
                    f"### {title}",
                    "",
                    "| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for item in patterns.get(group, {}).get(bucket, [])[:20]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_cell(item.get("segment")),
                            md_cell(item.get("sample_count")),
                            md_cell(item.get("ret3_ge_5_count")),
                            md_cell(item.get("ret3_le_0_count")),
                            md_cell(item.get("positive_rate")),
                            md_cell(item.get("negative_rate")),
                            md_cell(item.get("ret3_mean")),
                            md_cell(item.get("ret5_mean")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_macd_wave_rules_markdown(path: Path, rules: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = ["# MACD Wave Rules", ""]
    for env, payload in sorted(rules.items()):
        baseline = payload.get("baseline", {})
        lines.extend(
            [
                f"## {env}",
                "",
                (
                    f"- baseline: samples={baseline.get('sample_count')} "
                    f"positive_rate={baseline.get('positive_rate')} negative_rate={baseline.get('negative_rate')} "
                    f"ret3_mean={baseline.get('ret3_mean')}"
                ),
                "",
                "### Positive Rules",
                "",
                "| wave_rule | push_side | samples | pos_rate | pos_uplift | neg_rate | ret3_mean | ret5_mean |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in payload.get("positive_rules", [])[:20]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(item.get("wave_rule")),
                        md_cell(item.get("push_wave_side")),
                        md_cell(item.get("sample_count")),
                        md_cell(item.get("positive_rate")),
                        md_cell(item.get("positive_rate_uplift")),
                        md_cell(item.get("negative_rate")),
                        md_cell(item.get("ret3_mean")),
                        md_cell(item.get("ret5_mean")),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "### All Push Wave Rules",
                "",
                "| wave_rule | push_side | samples | pos_rate | pos_uplift | neg_rate | ret3_mean | ret5_mean |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in payload.get("all_push_wave_rules", [])[:20]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(item.get("wave_rule")),
                        md_cell(item.get("push_wave_side")),
                        md_cell(item.get("sample_count")),
                        md_cell(item.get("positive_rate")),
                        md_cell(item.get("positive_rate_uplift")),
                        md_cell(item.get("negative_rate")),
                        md_cell(item.get("ret3_mean")),
                        md_cell(item.get("ret5_mean")),
                    ]
                )
                + " |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_strong_pass_watch_ranking_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Strong PASS/WATCH Ranking Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- candidate_count: {report.get('candidate_count')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
        "## Family Stats",
        "",
        "| family | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_median | ret5_median | verdicts |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for family, stats in sorted(report.get("family_stats", {}).items()):
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(family),
                    md_cell(stats.get("sample_count")),
                    md_cell(stats.get("ret3_ge_5_count")),
                    md_cell(stats.get("ret3_le_0_count")),
                    md_cell(stats.get("positive_rate")),
                    md_cell(stats.get("negative_rate")),
                    md_cell(stats.get("ret3_median")),
                    md_cell(stats.get("ret5_median")),
                    md_cell(json.dumps(stats.get("current_verdict_distribution", {}), ensure_ascii=False)),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Top3 Comparison",
            "",
            "| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, summary in report.get("top3_comparison", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(name),
                    md_cell(summary.get("sample_count")),
                    md_cell(summary.get("ret3_ge_5_count")),
                    md_cell(summary.get("ret3_le_0_count")),
                    md_cell(summary.get("positive_rate")),
                    md_cell(summary.get("negative_rate")),
                    md_cell(summary.get("ret3_mean")),
                    md_cell(summary.get("ret3_median")),
                    md_cell(summary.get("ret5_mean")),
                    md_cell(summary.get("ret5_median")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Top5 Comparison",
            "",
            "| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, summary in report.get("top5_comparison", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(name),
                    md_cell(summary.get("sample_count")),
                    md_cell(summary.get("ret3_ge_5_count")),
                    md_cell(summary.get("ret3_le_0_count")),
                    md_cell(summary.get("positive_rate")),
                    md_cell(summary.get("negative_rate")),
                    md_cell(summary.get("ret3_mean")),
                    md_cell(summary.get("ret3_median")),
                    md_cell(summary.get("ret5_mean")),
                    md_cell(summary.get("ret5_median")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Daily Strong V1 Rank Top3",
            "",
            "| date | rank | code | verdict | family | strong_v1_score | current_score | ret3 | ret5 |",
            "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for day in report.get("daily_top3", [])[:30]:
        for idx, sample in enumerate(day.get("strong_v1_rank", []), start=1):
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(day.get("date")),
                        md_cell(idx),
                        md_cell(sample.get("code")),
                        md_cell(sample.get("verdict")),
                        md_cell(sample.get("family")),
                        md_cell(sample.get("strong_v1_rank_score")),
                        md_cell(sample.get("current_score")),
                        md_cell(sample.get("ret3")),
                        md_cell(sample.get("ret5")),
                    ]
                )
                + " |"
            )
    lines.extend(["", f"- next_step: {report.get('next_step')}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_strong_pass_composition_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    summary = report.get("summary", {})
    lines = [
        "# Strong PASS Composition Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- ret3>=5: {summary.get('ret3_ge_5_count')}",
        f"- ret3<=0: {summary.get('ret3_le_0_count')}",
        f"- positive_rate: {summary.get('positive_rate')}",
        f"- negative_rate: {summary.get('negative_rate')}",
        f"- ret3_mean: {summary.get('ret3_mean')}",
        f"- ret3_median: {summary.get('ret3_median')}",
        f"- ret5_mean: {summary.get('ret5_mean')}",
        f"- ret5_median: {summary.get('ret5_median')}",
        "",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
        "## Indicator Hit Rates",
        "",
        "| indicator | hit_rate |",
        "| --- | ---: |",
    ]
    for key, value in report.get("indicator_hit_rates", {}).items():
        lines.append(f"| {md_cell(key)} | {md_cell(value)} |")
    for section, title in [
        ("family_distribution", "Family Distribution"),
        ("signal_distribution", "Signal Distribution"),
        ("factor_distribution", "Top Factor Distribution"),
        ("macd_wave_distribution", "Top MACD Wave Distribution"),
    ]:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, payload in list(report.get(section, {}).items())[:20]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(payload.get("sample_count")),
                        md_cell(payload.get("share")),
                        md_cell(payload.get("ret3_ge_5_count")),
                        md_cell(payload.get("ret3_le_0_count")),
                        md_cell(payload.get("positive_rate")),
                        md_cell(payload.get("negative_rate")),
                        md_cell(payload.get("ret3_mean")),
                        md_cell(payload.get("ret3_median")),
                        md_cell(payload.get("ret5_mean")),
                        md_cell(payload.get("ret5_median")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Typical PASS Samples",
            "",
            "| date | code | family | verdict | score | ret3 | ret5 | signal | signal_type |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for sample in report.get("typical_samples", [])[:30]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(sample.get("date")),
                    md_cell(sample.get("code")),
                    md_cell(sample.get("family")),
                    md_cell(sample.get("verdict")),
                    md_cell(sample.get("score")),
                    md_cell(sample.get("ret3")),
                    md_cell(sample.get("ret5")),
                    md_cell(sample.get("signal")),
                    md_cell(sample.get("signal_type")),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_strong_b3_red_macd_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    summary = report.get("summary", {})
    lines = [
        "# Strong B3 Red MACD Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- ret3>=5: {summary.get('ret3_ge_5_count')}",
        f"- ret3<=0: {summary.get('ret3_le_0_count')}",
        f"- positive_rate: {summary.get('positive_rate')}",
        f"- negative_rate: {summary.get('negative_rate')}",
        f"- ret3_mean: {summary.get('ret3_mean')}",
        f"- ret3_median: {summary.get('ret3_median')}",
        "",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
    ]
    for section, title in [
        ("condition_distribution", "Condition Distribution"),
        ("factor_condition_distribution", "Factor Condition Distribution"),
    ]:
        lines.extend(
            [
                f"## {title}",
                "",
                "| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, payload in list(report.get(section, {}).items())[:30]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(payload.get("sample_count")),
                        md_cell(payload.get("share")),
                        md_cell(payload.get("ret3_ge_5_count")),
                        md_cell(payload.get("ret3_le_0_count")),
                        md_cell(payload.get("positive_rate")),
                        md_cell(payload.get("negative_rate")),
                        md_cell(payload.get("ret3_mean")),
                        md_cell(payload.get("ret3_median")),
                        md_cell(payload.get("ret5_mean")),
                        md_cell(payload.get("ret5_median")),
                    ]
                )
                + " |"
            )
        lines.append("")
    lines.extend(
        [
            "## Typical Positive Samples",
            "",
            "| date | code | condition | verdict | score | ret3 | ret5 | signal | signal_type | macd_hist | turnover | pct_chg |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for sample in report.get("typical_samples", [])[:30]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(sample.get("date")),
                    md_cell(sample.get("code")),
                    md_cell(sample.get("condition")),
                    md_cell(sample.get("verdict")),
                    md_cell(sample.get("score")),
                    md_cell(sample.get("ret3")),
                    md_cell(sample.get("ret5")),
                    md_cell(sample.get("signal")),
                    md_cell(sample.get("signal_type")),
                    md_cell(sample.get("daily_macd_hist")),
                    md_cell(sample.get("turnover_rate")),
                    md_cell(sample.get("daily_pct_chg")),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_strong_v1_negative_groups_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Strong V1 Negative Groups Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
    ]
    for scope_key, title in [("top3", "Daily Strong V1 Top3 Negatives"), ("top5", "Daily Strong V1 Top5 Negatives")]:
        payload = report.get(scope_key, {})
        negative = payload.get("negative_summary", {})
        positive = payload.get("positive_summary", {})
        lines.extend(
            [
                f"## {title}",
                "",
                f"- selected_samples: {payload.get('sample_count')}",
                f"- ret3>=5 samples: {positive.get('sample_count')}",
                f"- ret3<=0 samples: {negative.get('sample_count')}",
                f"- negative_ret3_mean: {negative.get('ret3_mean')}",
                f"- negative_ret3_median: {negative.get('ret3_median')}",
                "",
            ]
        )
        for section, section_title in [
            ("negative_family_distribution", "Family Distribution"),
            ("negative_factor_distribution", "Factor Distribution"),
            ("negative_b3_condition_distribution", "B3/Condition Distribution"),
            ("negative_macd_wave_distribution", "MACD Wave Distribution"),
        ]:
            lines.extend(
                [
                    f"### {section_title}",
                    "",
                    "| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for key, summary in list(payload.get(section, {}).items())[:20]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_cell(key),
                            md_cell(summary.get("sample_count")),
                            md_cell(summary.get("share")),
                            md_cell(summary.get("ret3_ge_5_count")),
                            md_cell(summary.get("ret3_le_0_count")),
                            md_cell(summary.get("positive_rate")),
                            md_cell(summary.get("negative_rate")),
                            md_cell(summary.get("ret3_mean")),
                            md_cell(summary.get("ret3_median")),
                            md_cell(summary.get("ret5_mean")),
                            md_cell(summary.get("ret5_median")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        lines.extend(
            [
                "### Worst Samples",
                "",
                "| date | rank | code | verdict | family | score | v1_score | ret3 | ret5 | signal | signal_type | condition |",
                "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
            ]
        )
        for sample in payload.get("worst_samples", [])[:30]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(sample.get("date")),
                        md_cell(sample.get("strong_v1_daily_rank")),
                        md_cell(sample.get("code")),
                        md_cell(sample.get("verdict")),
                        md_cell(sample.get("family")),
                        md_cell(sample.get("score")),
                        md_cell(sample.get("strong_v1_rank_score")),
                        md_cell(sample.get("ret3")),
                        md_cell(sample.get("ret5")),
                        md_cell(sample.get("signal")),
                        md_cell(sample.get("signal_type")),
                        md_cell(sample.get("negative_condition")),
                    ]
                )
                + " |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_weak_pass_watch_ranking_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Weak PASS/WATCH Ranking Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- candidate_count: {report.get('candidate_count')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
        "## Top3 Comparison",
        "",
        "| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, summary in report.get("top3_comparison", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(name),
                    md_cell(summary.get("sample_count")),
                    md_cell(summary.get("ret3_ge_5_count")),
                    md_cell(summary.get("ret3_le_0_count")),
                    md_cell(summary.get("positive_rate")),
                    md_cell(summary.get("negative_rate")),
                    md_cell(summary.get("ret3_mean")),
                    md_cell(summary.get("ret3_median")),
                    md_cell(summary.get("ret5_mean")),
                    md_cell(summary.get("ret5_median")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Top5 Comparison",
            "",
            "| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, summary in report.get("top5_comparison", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(name),
                    md_cell(summary.get("sample_count")),
                    md_cell(summary.get("ret3_ge_5_count")),
                    md_cell(summary.get("ret3_le_0_count")),
                    md_cell(summary.get("positive_rate")),
                    md_cell(summary.get("negative_rate")),
                    md_cell(summary.get("ret3_mean")),
                    md_cell(summary.get("ret3_median")),
                    md_cell(summary.get("ret5_mean")),
                    md_cell(summary.get("ret5_median")),
                ]
            )
            + " |"
        )
    for section, title in [
        ("family_distribution", "Family Distribution"),
        ("risk_flag_distribution", "Risk Flag Distribution"),
    ]:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, payload in list(report.get(section, {}).items())[:20]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(payload.get("sample_count")),
                        md_cell(payload.get("share")),
                        md_cell(payload.get("ret3_ge_5_count")),
                        md_cell(payload.get("ret3_le_0_count")),
                        md_cell(payload.get("positive_rate")),
                        md_cell(payload.get("negative_rate")),
                        md_cell(payload.get("ret3_mean")),
                        md_cell(payload.get("ret3_median")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Daily Weak V4 Rank Top3",
            "",
            "| date | rank | code | verdict | family | weak_v4_score | current_score | ret3 | ret5 | indicator | risk_flags |",
            "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for day in report.get("daily_top3", [])[:40]:
        for idx, sample in enumerate(day.get("weak_v4_rank", []), start=1):
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(day.get("date")),
                        md_cell(idx),
                        md_cell(sample.get("code")),
                        md_cell(sample.get("verdict")),
                        md_cell(sample.get("family")),
                        md_cell(sample.get("weak_v4_rank_score")),
                        md_cell(sample.get("current_score")),
                        md_cell(sample.get("ret3")),
                        md_cell(sample.get("ret5")),
                        md_cell(sample.get("weak_indicator_key")),
                        md_cell(",".join(sample.get("weak_risk_flags", []))),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_weak_v2_negative_groups_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Weak V2 Negative Groups Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
    ]
    for scope_key, title in [("top3", "Daily Weak V2 Top3 Negatives"), ("top5", "Daily Weak V2 Top5 Negatives")]:
        payload = report.get(scope_key, {})
        negative = payload.get("negative_summary", {})
        positive = payload.get("positive_summary", {})
        lines.extend(
            [
                f"## {title}",
                "",
                f"- selected_samples: {payload.get('sample_count')}",
                f"- ret3>=5 samples: {positive.get('sample_count')}",
                f"- ret3<=0 samples: {negative.get('sample_count')}",
                f"- negative_ret3_mean: {negative.get('ret3_mean')}",
                f"- negative_ret3_median: {negative.get('ret3_median')}",
                "",
            ]
        )
        for section, section_title in [
            ("negative_family_distribution", "Family Distribution"),
            ("negative_factor_distribution", "Factor Distribution"),
            ("negative_condition_distribution", "Condition Distribution"),
            ("negative_risk_flag_distribution", "Risk Flag Distribution"),
            ("negative_macd_wave_distribution", "MACD Wave Distribution"),
        ]:
            lines.extend(
                [
                    f"### {section_title}",
                    "",
                    "| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for key, summary in list(payload.get(section, {}).items())[:20]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_cell(key),
                            md_cell(summary.get("sample_count")),
                            md_cell(summary.get("share")),
                            md_cell(summary.get("ret3_ge_5_count")),
                            md_cell(summary.get("ret3_le_0_count")),
                            md_cell(summary.get("positive_rate")),
                            md_cell(summary.get("negative_rate")),
                            md_cell(summary.get("ret3_mean")),
                            md_cell(summary.get("ret3_median")),
                            md_cell(summary.get("ret5_mean")),
                            md_cell(summary.get("ret5_median")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        lines.extend(
            [
                "### Worst Samples",
                "",
                "| date | rank | code | verdict | family | score | weak_v2_score | ret3 | ret5 | signal | signal_type | condition | risk_flags |",
                "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
            ]
        )
        for sample in payload.get("worst_samples", [])[:30]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(sample.get("date")),
                        md_cell(sample.get("weak_v2_daily_rank")),
                        md_cell(sample.get("code")),
                        md_cell(sample.get("verdict")),
                        md_cell(sample.get("family")),
                        md_cell(sample.get("score")),
                        md_cell(sample.get("weak_v2_rank_score")),
                        md_cell(sample.get("ret3")),
                        md_cell(sample.get("ret5")),
                        md_cell(sample.get("signal")),
                        md_cell(sample.get("signal_type")),
                        md_cell(sample.get("negative_condition")),
                        md_cell(",".join(sample.get("weak_risk_flags", []))),
                    ]
                )
                + " |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_weak_indicator_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Weak Indicator Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- pass_watch_count: {report.get('pass_watch_count')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
    ]
    for section, title, limit in [
        ("indicator_distribution", "Weak Indicator Distribution", 30),
        ("pass_watch_indicator_distribution", "Weak PASS/WATCH Indicator Distribution", 30),
        ("family_indicator_distribution", "Weak Family + Indicator Distribution", 40),
        ("condition_indicator_distribution", "Weak Condition + Indicator Distribution", 40),
    ]:
        lines.extend(
            [
                f"## {title}",
                "",
                "| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, summary in list(report.get(section, {}).items())[:limit]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("share")),
                        md_cell(summary.get("ret3_ge_5_count")),
                        md_cell(summary.get("ret3_le_0_count")),
                        md_cell(summary.get("positive_rate")),
                        md_cell(summary.get("negative_rate")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret3_median")),
                        md_cell(summary.get("ret5_mean")),
                        md_cell(summary.get("ret5_median")),
                    ]
                )
                + " |"
            )
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_weak_watch_positive_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    summary = report.get("summary", {})
    lines = [
        "# Weak WATCH Positive Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- ret3>0: {summary.get('ret3_gt_0_count')} ({summary.get('ret3_gt_0_rate')})",
        f"- ret5>0: {summary.get('ret5_gt_0_count')} ({summary.get('ret5_gt_0_rate')})",
        f"- ret3>=5: {summary.get('ret3_ge_5_count')} ({summary.get('positive_rate')})",
        f"- ret3<=0: {summary.get('ret3_le_0_count')} ({summary.get('negative_rate')})",
        "",
        "## Candidate Guidance",
        "",
    ]
    for item in report.get("candidate_guidance", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Return Groups",
            "",
            "| group | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for key, payload in report.get("return_groups", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(key),
                    md_cell(payload.get("sample_count")),
                    md_cell(payload.get("ret3_gt_0_count")),
                    md_cell(payload.get("ret5_gt_0_count")),
                    md_cell(payload.get("ret3_ge_5_count")),
                    md_cell(payload.get("ret3_le_0_count")),
                    md_cell(payload.get("ret3_mean")),
                    md_cell(payload.get("ret5_mean")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Upgrade Candidates",
            "",
            "| condition | key | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | examples |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in report.get("upgrade_candidates", [])[:30]:
        examples = ",".join(str(sample.get("code")) for sample in item.get("typical_samples", [])[:5])
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(item.get("condition")),
                    md_cell(item.get("key")),
                    md_cell(item.get("sample_count")),
                    md_cell(item.get("ret3_gt_0_count")),
                    md_cell(item.get("ret5_gt_0_count")),
                    md_cell(item.get("ret3_ge_5_count")),
                    md_cell(item.get("ret3_le_0_count")),
                    md_cell(item.get("ret3_mean")),
                    md_cell(item.get("ret5_mean")),
                    md_cell(examples),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Veto / Risk Candidates",
            "",
            "| flag | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | examples |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for key, payload in report.get("veto_candidates", {}).items():
        examples = ",".join(str(sample.get("code")) for sample in payload.get("typical_samples", [])[:5])
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(key),
                    md_cell(payload.get("sample_count")),
                    md_cell(payload.get("ret3_ge_5_count")),
                    md_cell(payload.get("ret3_le_0_count")),
                    md_cell(payload.get("negative_rate")),
                    md_cell(payload.get("ret3_mean")),
                    md_cell(examples),
                ]
            )
            + " |"
        )
    for section, title in [
        ("condition", "Negative Condition Distribution"),
        ("family_indicator", "Negative Family + Indicator Distribution"),
        ("macd_wave", "Negative MACD Wave Distribution"),
        ("factor", "Negative Factor Distribution"),
    ]:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, payload in list(report.get("negative_distributions", {}).get(section, {}).items())[:20]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(payload.get("sample_count")),
                        md_cell(payload.get("ret3_ge_5_count")),
                        md_cell(payload.get("ret3_le_0_count")),
                        md_cell(payload.get("negative_rate")),
                        md_cell(payload.get("ret3_mean")),
                        md_cell(payload.get("ret5_mean")),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_neutral_watch_positive_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    summary = report.get("summary", {})
    lines = [
        "# Neutral WATCH Positive Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- ret3>0: {summary.get('ret3_gt_0_count')} ({summary.get('ret3_gt_0_rate')})",
        f"- ret5>0: {summary.get('ret5_gt_0_count')} ({summary.get('ret5_gt_0_rate')})",
        f"- ret3>=5: {summary.get('ret3_ge_5_count')} ({summary.get('positive_rate')})",
        f"- ret3<=0: {summary.get('ret3_le_0_count')} ({summary.get('negative_rate')})",
        "",
        "## Candidate Guidance",
        "",
    ]
    for item in report.get("candidate_guidance", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Return Groups",
            "",
            "| group | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for key, payload in report.get("return_groups", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(key),
                    md_cell(payload.get("sample_count")),
                    md_cell(payload.get("ret3_gt_0_count")),
                    md_cell(payload.get("ret5_gt_0_count")),
                    md_cell(payload.get("ret3_ge_5_count")),
                    md_cell(payload.get("ret3_le_0_count")),
                    md_cell(payload.get("ret3_mean")),
                    md_cell(payload.get("ret5_mean")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Upgrade Candidates",
            "",
            "| condition | key | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | examples |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in report.get("upgrade_candidates", [])[:30]:
        examples = ",".join(str(sample.get("code")) for sample in item.get("typical_samples", [])[:5])
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(item.get("condition")),
                    md_cell(item.get("key")),
                    md_cell(item.get("sample_count")),
                    md_cell(item.get("ret3_gt_0_count")),
                    md_cell(item.get("ret5_gt_0_count")),
                    md_cell(item.get("ret3_ge_5_count")),
                    md_cell(item.get("ret3_le_0_count")),
                    md_cell(item.get("ret3_mean")),
                    md_cell(item.get("ret5_mean")),
                    md_cell(examples),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Veto / Risk Candidates",
            "",
            "| flag | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | examples |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for key, payload in report.get("veto_candidates", {}).items():
        examples = ",".join(str(sample.get("code")) for sample in payload.get("typical_samples", [])[:5])
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(key),
                    md_cell(payload.get("sample_count")),
                    md_cell(payload.get("ret3_ge_5_count")),
                    md_cell(payload.get("ret3_le_0_count")),
                    md_cell(payload.get("negative_rate")),
                    md_cell(payload.get("ret3_mean")),
                    md_cell(examples),
                ]
            )
            + " |"
        )
    for section, title in [
        ("condition", "Negative Condition Distribution"),
        ("family", "Negative Family Distribution"),
        ("macd_wave", "Negative MACD Wave Distribution"),
        ("factor", "Negative Factor Distribution"),
    ]:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, payload in list(report.get("negative_distributions", {}).get(section, {}).items())[:20]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(payload.get("sample_count")),
                        md_cell(payload.get("ret3_ge_5_count")),
                        md_cell(payload.get("ret3_le_0_count")),
                        md_cell(payload.get("negative_rate")),
                        md_cell(payload.get("ret3_mean")),
                        md_cell(payload.get("ret5_mean")),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_strong_neutral_risk_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Strong / Neutral Risk Candidate Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
        "## Next Step",
        "",
    ]
    for item in report.get("next_step", []):
        lines.append(f"- {item}")
    for env_key, title in [("strong", "Strong Risk Candidates"), ("neutral", "Neutral Risk Candidates")]:
        payload = report.get(env_key, {})
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                f"- source: {payload.get('source')}",
                "",
                "| key | source_scope | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean | examples |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for key, summary in payload.get("risk_candidates", {}).items():
            examples = ",".join(str(sample.get("code")) for sample in summary.get("typical_samples", [])[:5])
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(summary.get("source_scope")),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("ret3_ge_5_count")),
                        md_cell(summary.get("ret3_le_0_count")),
                        md_cell(summary.get("negative_rate")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret5_mean")),
                        md_cell(examples),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_neutral_factor_effect_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Neutral Factor Effect Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- ret3>5 count: {report.get('ret3_gt_5_count')}",
        f"- PASS+WATCH ret3>5 count: {report.get('pass_watch_ret3_gt_5_count')}",
        "",
        "## Guidance",
        "",
    ]
    for item in report.get("guidance", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Majority Positive Features",
            "",
            "| factor | key | base_share | ret3>5_share | uplift | PASS+WATCH ret3>5 share |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report.get("majority_positive_features", [])[:30]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(item.get("factor")),
                    md_cell(item.get("key")),
                    md_cell(item.get("base_share")),
                    md_cell(item.get("ret3_gt_5_share")),
                    md_cell(item.get("uplift")),
                    md_cell(item.get("pass_watch_ret3_gt_5_share")),
                ]
            )
            + " |"
        )
    for factor, payload in report.get("factor_effects", {}).items():
        lines.extend(
            [
                "",
                f"## {factor}",
                "",
                "| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for value, summary in list(payload.items())[:12]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(value),
                        md_cell(summary.get("base_count")),
                        md_cell(summary.get("base_share")),
                        md_cell(summary.get("ret3_gt_5_count")),
                        md_cell(summary.get("ret3_gt_5_share")),
                        md_cell(summary.get("uplift")),
                        md_cell(summary.get("pass_watch_ret3_gt_5_count")),
                        md_cell(summary.get("pass_watch_ret3_gt_5_share")),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_neutral_watch_ranking_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Neutral PASS/WATCH Ranking Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- sample_count: {report.get('sample_count')}",
        f"- candidate_count: {report.get('candidate_count')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
        "## Top3 Comparison",
        "",
        "| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, summary in report.get("top3_comparison", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(name),
                    md_cell(summary.get("sample_count")),
                    md_cell(summary.get("ret3_ge_5_count")),
                    md_cell(summary.get("ret3_le_0_count")),
                    md_cell(summary.get("positive_rate")),
                    md_cell(summary.get("negative_rate")),
                    md_cell(summary.get("ret3_mean")),
                    md_cell(summary.get("ret3_median")),
                    md_cell(summary.get("ret5_mean")),
                    md_cell(summary.get("ret5_median")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Top5 Comparison",
            "",
            "| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, summary in report.get("top5_comparison", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(name),
                    md_cell(summary.get("sample_count")),
                    md_cell(summary.get("ret3_ge_5_count")),
                    md_cell(summary.get("ret3_le_0_count")),
                    md_cell(summary.get("positive_rate")),
                    md_cell(summary.get("negative_rate")),
                    md_cell(summary.get("ret3_mean")),
                    md_cell(summary.get("ret3_median")),
                    md_cell(summary.get("ret5_mean")),
                    md_cell(summary.get("ret5_median")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Daily Neutral V1 Rank Top3",
            "",
            "| date | rank | code | verdict | neutral_v1_score | current_score | positive_score | risk_penalty | risk_flags | ret3 | ret5 | factor_segment |",
            "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for day in report.get("daily_top3", [])[:40]:
        for idx, sample in enumerate(day.get("neutral_v1_rank", []), start=1):
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(day.get("date")),
                        md_cell(idx),
                        md_cell(sample.get("code")),
                        md_cell(sample.get("verdict")),
                        md_cell(sample.get("neutral_v1_rank_score")),
                        md_cell(sample.get("current_score")),
                        md_cell(sample.get("neutral_positive_score")),
                        md_cell(sample.get("neutral_risk_penalty")),
                        md_cell(",".join(sample.get("neutral_risk_flags", []))),
                        md_cell(sample.get("ret3")),
                        md_cell(sample.get("ret5")),
                        md_cell(sample.get("factor_segment")),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_neutral_v1_stability_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    daily_summary = report.get("daily_summary", {})
    loss_summary = report.get("top3_loss_summary", {})
    lines = [
        "# Neutral V1 Stability Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- day_count: {daily_summary.get('day_count')}",
        f"- improved_days: {daily_summary.get('improved_days')}",
        f"- regressed_days: {daily_summary.get('regressed_days')}",
        f"- neutral_better_positive_days: {daily_summary.get('neutral_better_positive_days')}",
        f"- neutral_lower_negative_days: {daily_summary.get('neutral_lower_negative_days')}",
        f"- top3_loss_count: {loss_summary.get('sample_count')}",
        f"- top3_loss_ret3_mean: {loss_summary.get('ret3_mean')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
        "## Daily Deltas",
        "",
        "| date | ret3>=5 delta | ret3<=0 delta | ret3_mean delta | current ret3>=5 | neutral ret3>=5 | current ret3<=0 | neutral ret3<=0 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.get("daily_deltas", []):
        current = item.get("current_top3", {})
        neutral = item.get("neutral_v1_top3", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(item.get("date")),
                    md_cell(item.get("ret3_ge_5_delta")),
                    md_cell(item.get("ret3_le_0_delta")),
                    md_cell(item.get("ret3_mean_delta")),
                    md_cell(current.get("ret3_ge_5_count")),
                    md_cell(neutral.get("ret3_ge_5_count")),
                    md_cell(current.get("ret3_le_0_count")),
                    md_cell(neutral.get("ret3_le_0_count")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Regression Days",
            "",
            "| date | ret3>=5 delta | ret3<=0 delta | ret3_mean delta |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in report.get("regression_days", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(item.get("date")),
                    md_cell(item.get("ret3_ge_5_delta")),
                    md_cell(item.get("ret3_le_0_delta")),
                    md_cell(item.get("ret3_mean_delta")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Top3 Loss Risk Flags",
            "",
            "| flag | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for flag, payload in report.get("top3_loss_risk_flags", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(flag),
                    md_cell(payload.get("sample_count")),
                    md_cell(payload.get("share")),
                    md_cell(payload.get("ret3_mean")),
                    md_cell(payload.get("ret3_median")),
                    md_cell(payload.get("ret5_mean")),
                    md_cell(payload.get("ret5_median")),
                ]
            )
            + " |"
        )
    for section, title in [
        ("top3_loss_signal_distribution", "Top3 Loss Signal Distribution"),
        ("top3_loss_factor_distribution", "Top3 Loss Factor Distribution"),
        ("top3_loss_macd_distribution", "Top3 Loss MACD Distribution"),
    ]:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, payload in list(report.get(section, {}).items())[:20]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(payload.get("sample_count")),
                        md_cell(payload.get("share")),
                        md_cell(payload.get("ret3_mean")),
                        md_cell(payload.get("ret3_median")),
                        md_cell(payload.get("ret5_mean")),
                        md_cell(payload.get("ret5_median")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Worst Neutral V1 Top3 Losses",
            "",
            "| date | code | verdict | neutral_v1_score | current_score | positive_score | risk_penalty | ret3 | ret5 | signal | signal_type | risk_flags |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for sample in report.get("top3_loss_samples", [])[:40]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(sample.get("date")),
                    md_cell(sample.get("code")),
                    md_cell(sample.get("verdict")),
                    md_cell(sample.get("neutral_v1_rank_score")),
                    md_cell(sample.get("current_score")),
                    md_cell(sample.get("neutral_positive_score")),
                    md_cell(sample.get("neutral_risk_penalty")),
                    md_cell(sample.get("ret3")),
                    md_cell(sample.get("ret5")),
                    md_cell(sample.get("signal")),
                    md_cell(sample.get("signal_type")),
                    md_cell(",".join(sample.get("neutral_risk_flags", []))),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_neutral_v2_veto_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Neutral V2 Veto Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- diagnosis: {report.get('diagnosis')}",
    ]
    for section, title in [("top3_comparison", "Top3 Comparison"), ("top5_comparison", "Top5 Comparison")]:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, summary in report.get(section, {}).items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(name),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("ret3_ge_5_count")),
                        md_cell(summary.get("ret3_le_0_count")),
                        md_cell(summary.get("positive_rate")),
                        md_cell(summary.get("negative_rate")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret3_median")),
                        md_cell(summary.get("ret5_mean")),
                        md_cell(summary.get("ret5_median")),
                    ]
                )
                + " |"
            )
    for kind, payload in report.get("veto_candidates", {}).items():
        lines.extend(
            [
                "",
                f"## Veto Candidates: {kind}",
                "",
                "| key | samples | ret3>=5 | ret3<=0 | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key, summary in payload.items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(key),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("ret3_ge_5_count")),
                        md_cell(summary.get("ret3_le_0_count")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret3_median")),
                        md_cell(summary.get("ret5_mean")),
                        md_cell(summary.get("ret5_median")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Penalized Samples",
            "",
            "| date | code | neutral_v1_score | neutral_v2_score | penalty | ret3 | ret5 | signal | signal_type | veto_hits |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for sample in report.get("penalized_samples", [])[:60]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(sample.get("date")),
                    md_cell(sample.get("code")),
                    md_cell(sample.get("neutral_v1_rank_score")),
                    md_cell(sample.get("neutral_v2_rank_score")),
                    md_cell(sample.get("neutral_v2_penalty")),
                    md_cell(sample.get("ret3")),
                    md_cell(sample.get("ret5")),
                    md_cell(sample.get("signal")),
                    md_cell(sample.get("signal_type")),
                    md_cell(",".join(sample.get("neutral_v2_veto_hits", []))),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_pass_watch_high_ret3_group_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# PASS/WATCH High Ret3 Group Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- diagnosis: {report.get('diagnosis')}",
    ]
    for env, payload in report.get("environments", {}).items():
        daily = payload.get("daily_best_summary", {})
        lines.extend(
            [
                "",
                f"## {env}",
                "",
                f"- sample_count: {payload.get('sample_count')}",
                f"- high_ret3_count: {payload.get('high_ret3_count')}",
                f"- high_ret3_days: {payload.get('high_ret3_days')}",
                f"- daily_best_day_count: {daily.get('day_count')}",
                f"- daily_best_ret3_mean: {daily.get('ret3_mean')}",
                f"- daily_best_ret3_median: {daily.get('ret3_median')}",
                "",
                "### Priority Skeleton Groups",
                "",
                "| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in payload.get("priority_skeleton_groups", [])[:12]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(item.get("group")),
                        md_cell(item.get("coverage")),
                        md_cell(item.get("sample_count")),
                        md_cell(item.get("ret3_mean")),
                        md_cell(item.get("ret3_median")),
                        md_cell(item.get("ret5_mean")),
                        md_cell(item.get("ret5_median")),
                    ]
                )
                + " |"
            )
        for section, title in [
            ("daily_best_skeleton_distribution", "Daily Best Skeleton Distribution"),
            ("daily_best_full_group_distribution", "Daily Best Full Group Distribution"),
            ("daily_best_macd_distribution", "Daily Best MACD Distribution"),
        ]:
            lines.extend(
                [
                    "",
                    f"### {title}",
                    "",
                    "| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for key, summary in list(payload.get(section, {}).items())[:12]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_cell(key),
                            md_cell(summary.get("sample_count")),
                            md_cell(summary.get("share")),
                            md_cell(summary.get("ret3_mean")),
                            md_cell(summary.get("ret3_median")),
                            md_cell(summary.get("ret5_mean")),
                            md_cell(summary.get("ret5_median")),
                        ]
                    )
                    + " |"
                )
        lines.extend(
            [
                "",
                "### Daily Best Samples",
                "",
                "| date | code | verdict | score | ret3 | ret5 | skeleton_group | full_group | macd |",
                "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
            ]
        )
        for sample in payload.get("daily_best_samples", [])[:40]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(sample.get("date")),
                        md_cell(sample.get("code")),
                        md_cell(sample.get("verdict")),
                        md_cell(sample.get("current_score")),
                        md_cell(sample.get("ret3")),
                        md_cell(sample.get("ret5")),
                        md_cell(sample.get("skeleton_group")),
                        md_cell(sample.get("full_group")),
                        md_cell(sample.get("macd_wave_rule")),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_env_skeleton_top1_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Environment Skeleton Top1 Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- diagnosis: {report.get('diagnosis')}",
    ]
    for env, payload in report.get("environments", {}).items():
        lines.extend(
            [
                "",
                f"## {env}",
                "",
                f"- day_count: {payload.get('day_count')}",
                f"- skeleton_top1_from_group_days: {payload.get('skeleton_top1_from_group_days')}",
                f"- diagnosis: {payload.get('diagnosis')}",
                "",
                "### Top1 Comparison",
                "",
                "| ranker | samples | ret3>0 | ret3>0 rate | ret3>=5 | ret3<=0 | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for ranker, summary in payload.get("top1_comparison", {}).items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(ranker),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("ret3_gt_0_count")),
                        md_cell(summary.get("ret3_gt_0_rate")),
                        md_cell(summary.get("ret3_ge_5_count")),
                        md_cell(summary.get("ret3_le_0_count")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret3_median")),
                        md_cell(summary.get("ret5_mean")),
                        md_cell(summary.get("ret5_median")),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "### Environment Priority Skeleton Groups",
                "",
                "| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for group in payload.get("priority_skeleton_groups", [])[:12]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(group.get("group")),
                        md_cell(group.get("coverage")),
                        md_cell(group.get("sample_count")),
                        md_cell(group.get("ret3_mean")),
                        md_cell(group.get("ret3_median")),
                        md_cell(group.get("ret5_mean")),
                        md_cell(group.get("ret5_median")),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "### Skeleton Top1 Group Distribution",
                "",
                "| group | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for group, summary in payload.get("skeleton_top1_group_distribution", {}).items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(group),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("share")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret3_median")),
                        md_cell(summary.get("ret5_mean")),
                        md_cell(summary.get("ret5_median")),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "### Daily Top1",
                "",
                "| date | current_code | current_score | current_ret3 | skeleton_code | skeleton_score | boost | skeleton_ret3 | skeleton_group |",
                "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for row in payload.get("daily_top1", [])[:80]:
            current = row.get("current_score", {})
            skeleton = row.get("skeleton_rank", {})
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(row.get("date")),
                        md_cell(current.get("code")),
                        md_cell(current.get("current_score")),
                        md_cell(current.get("ret3")),
                        md_cell(skeleton.get("code")),
                        md_cell(skeleton.get("skeleton_top1_score")),
                        md_cell(skeleton.get("skeleton_top1_boost")),
                        md_cell(skeleton.get("ret3")),
                        md_cell(skeleton.get("skeleton_group")),
                    ]
                )
                + " |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_weak_neutral_top3_followup_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Weak/Neutral Top3 Follow-up Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- strong_policy: {report.get('strong_policy')}",
        f"- diagnosis: {report.get('diagnosis')}",
    ]
    for env, payload in report.get("environments", {}).items():
        lines.extend(
            [
                "",
                f"## {env}",
                "",
                f"- next_step: {payload.get('next_step')}",
                "",
                "### Top3 Metrics",
                "",
                "| variant | samples | ret3>=5 | pos_rate | ret3<=0 | neg_rate | ret3_mean | ret3_median | daily_hit_days | daily_hit_rate |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for variant, variant_payload in payload.get("variants", {}).items():
            summary = variant_payload.get("top3_summary", {})
            daily = variant_payload.get("daily_hit_summary", {})
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(variant),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("ret3_ge_5_count")),
                        md_cell(summary.get("positive_rate")),
                        md_cell(summary.get("ret3_le_0_count")),
                        md_cell(summary.get("negative_rate")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret3_median")),
                        md_cell(f"{daily.get('hit_days')}/{daily.get('day_count')}"),
                        md_cell(daily.get("hit_rate")),
                    ]
                )
                + " |"
            )
        for variant, variant_payload in payload.get("variants", {}).items():
            lines.extend(
                [
                    "",
                    f"### {variant} Loss Factor Distribution",
                    "",
                    "| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for key, summary in list(variant_payload.get("loss_factor_distribution", {}).items())[:10]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_cell(key),
                            md_cell(summary.get("sample_count")),
                            md_cell(summary.get("share")),
                            md_cell(summary.get("ret3_mean")),
                            md_cell(summary.get("ret3_median")),
                            md_cell(summary.get("ret5_mean")),
                            md_cell(summary.get("ret5_median")),
                        ]
                    )
                    + " |"
                )
            lines.extend(
                [
                    "",
                    f"### {variant} Loss Risk Flags",
                    "",
                    "| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for key, summary in list(variant_payload.get("loss_risk_flag_distribution", {}).items())[:10]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_cell(key),
                            md_cell(summary.get("sample_count")),
                            md_cell(summary.get("share")),
                            md_cell(summary.get("ret3_mean")),
                            md_cell(summary.get("ret3_median")),
                            md_cell(summary.get("ret5_mean")),
                            md_cell(summary.get("ret5_median")),
                        ]
                    )
                    + " |"
                )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_weak_final_tuning_markdown(path: Path, report: dict[str, Any]) -> None:
    def md_cell(value: Any) -> str:
        return str(value).replace("|", r"\|")

    lines = [
        "# Weak Final Tuning Report",
        "",
        f"- scope: {report.get('scope')}",
        f"- recommended_top3_scenario: {report.get('recommended_top3_scenario')}",
        f"- top5_reference_scenario: {report.get('top5_reference_scenario')}",
        f"- production_boundary: {report.get('production_boundary')}",
        f"- diagnosis: {report.get('diagnosis')}",
        "",
        "## Scenario Comparison",
        "",
        "| scenario | topN | samples | ret3>=5 | positive_rate | ret3<=0 | negative_rate | ret3_mean | ret3_median | daily_hit_days | daily_hit_rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario, payload in report.get("scenarios", {}).items():
        for topn in ("top3", "top5"):
            summary = payload.get(topn, {})
            lines.append(
                "| "
                + " | ".join(
                    [
                        md_cell(scenario),
                        md_cell(topn),
                        md_cell(summary.get("sample_count")),
                        md_cell(summary.get("ret3_ge_5_count")),
                        md_cell(summary.get("positive_rate")),
                        md_cell(summary.get("ret3_le_0_count")),
                        md_cell(summary.get("negative_rate")),
                        md_cell(summary.get("ret3_mean")),
                        md_cell(summary.get("ret3_median")),
                        md_cell(f"{summary.get('daily_hit_days')}/{summary.get('day_count')}"),
                        md_cell(summary.get("daily_hit_rate")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Penalty Candidates",
            "",
            "| key | penalty | factor_segment | reason |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for key, payload in report.get("penalty_candidates", {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(key),
                    md_cell(payload.get("penalty")),
                    md_cell(payload.get("factor_segment")),
                    md_cell(payload.get("reason")),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_segment_table(lines: list[str], title: str, segments: dict[str, dict[str, Any]], limit: int) -> None:
    lines.extend(
        [
            "",
            f"## {title}",
            "",
            "| segment | samples | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | verdicts |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    top_segments = sorted(
        segments.items(),
        key=lambda item: (item[1].get("sample_count", 0), item[1].get("ret3_ge_5_count", 0)),
        reverse=True,
    )[:limit]
    for key, value in top_segments:
        lines.append(
            "| "
            + " | ".join(
                [
                    key,
                    str(value.get("sample_count")),
                    str(value.get("ret3_ge_5_count")),
                    str(value.get("ret3_le_0_count")),
                    str(value.get("ret3_mean")),
                    str(value.get("ret5_mean")),
                    json.dumps(value.get("current_verdict_distribution", {}), ensure_ascii=False),
                ]
            )
            + " |"
        )


def write_summary(
    path: Path,
    rows: Sequence[dict[str, Any]],
    segments: dict[str, dict[str, Any]],
    macd_segments: dict[str, dict[str, Any]],
    factor_segments: dict[str, dict[str, Any]],
    environment_comparisons: dict[str, dict[str, Any]],
    stable_patterns: dict[str, Any],
) -> None:
    env_counts = Counter(str(row.get("env") or "unknown") for row in rows)
    bucket_counts = Counter(str(row.get("ret3_bucket") or "") for row in rows if row.get("ret3_bucket"))
    stable_counts = {
        group: {bucket: len(items) for bucket, items in stable_patterns.get(group, {}).items()}
        for group in ("base", "macd", "factor")
    }
    lines = [
        "# b2 Review Layer Diagnostics",
        "",
        f"- rows: {len(rows)}",
        f"- environments: {dict(sorted(env_counts.items()))}",
        f"- ret3 buckets: {dict(sorted(bucket_counts.items()))}",
        f"- segment_count: {len(segments)}",
        f"- macd_segment_count: {len(macd_segments)}",
        f"- factor_segment_count: {len(factor_segments)}",
        f"- stable_pattern_counts: {stable_counts}",
    ]
    append_segment_table(lines, "Top Base Segments", segments, 30)
    append_segment_table(lines, "Top MACD Segments", macd_segments, 30)
    append_segment_table(lines, "Top Factor Segments", factor_segments, 30)
    lines.extend(["", "## Environment Split", ""])
    lines.append("| env | samples | A+B count | A+B ret3_mean | D/E/F count | D/E/F ret3_mean | WATCH/FAIL ret3>=5 | PASS ret3<=0 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for env, payload in sorted(environment_comparisons.items()):
        positive = payload.get("positive_group", {})
        negative = payload.get("negative_group", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    env,
                    str(payload.get("sample_count")),
                    str(positive.get("sample_count")),
                    str(positive.get("ret3_mean")),
                    str(negative.get("sample_count")),
                    str(negative.get("ret3_mean")),
                    str(len(payload.get("watch_fail_high_ret3", []))),
                    str(len(payload.get("pass_negative_ret3", []))),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_misclassified(path: Path, classified: dict[str, list[dict[str, Any]]]) -> None:
    titles = {
        "pass_poor": "当前 PASS 但 ret3 <= 0",
        "missed_high": "当前 WATCH/FAIL 但 ret3 >= 5",
        "ranking_mismatch": "PASS+WATCH 中 ret3 >= 5 但排在 top10 之后",
    }
    lines = ["# Misclassified Samples", ""]
    for key, title in titles.items():
        rows = classified.get(key, [])
        lines.extend([f"## {title}", "", f"count: {len(rows)}", ""])
        lines.append("| date | code | env | verdict | score | ret3 | ret5 | signal | signal_type | rank |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: |")
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    str(row.get(column, ""))
                    for column in (
                        "date",
                        "code",
                        "env",
                        "current_verdict",
                        "current_score",
                        "ret3",
                        "ret5",
                        "signal",
                        "signal_type",
                        "current_rank",
                    )
                )
                + " |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build offline b2 review-layer diagnostics from Rust runtime artifacts.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dsn")
    parser.add_argument("--price-end-date", default=date.today().isoformat())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    method = args.method.strip().lower()
    if method != "b2":
        raise SystemExit("This diagnostic script currently supports --method b2 only.")
    dsn = resolve_dsn(args.dsn)
    symbols = collect_runtime_symbols(args.runtime_root, method, args.start_date, args.end_date)
    price_start_date = (date.fromisoformat(args.start_date) - timedelta(days=240)).isoformat()
    price_rows = fetch_price_rows(dsn, symbols, price_start_date, args.price_end_date)
    indicator_rows = fetch_indicator_rows(dsn, symbols, price_start_date, args.price_end_date)
    price_rows = merge_indicator_rows(price_rows, indicator_rows)
    rows = collect_feature_rows(
        runtime_root=args.runtime_root,
        method=method,
        start_date=args.start_date,
        end_date=args.end_date,
        price_rows=price_rows,
    )
    segments = build_segments(rows)
    macd_segments = build_macd_segments(rows)
    macd_wave_rules = build_macd_wave_rules(rows, min_samples=10)
    factor_segments = build_factor_segments(rows)
    environment_comparisons = build_environment_comparisons(rows)
    strong_pass_watch_ranking = build_strong_pass_watch_ranking_report(rows)
    strong_pass_composition = build_strong_pass_composition_report(rows)
    strong_b3_red_macd = build_strong_b3_red_macd_report(rows)
    strong_v1_negative_groups = build_strong_v1_negative_groups_report(rows)
    weak_pass_watch_ranking = build_weak_pass_watch_ranking_report(rows)
    weak_v2_negative_groups = build_weak_v2_negative_groups_report(rows)
    weak_indicator = build_weak_indicator_report(rows)
    weak_watch_positive = build_weak_watch_positive_report(rows)
    neutral_watch_positive = build_neutral_watch_positive_report(rows)
    strong_neutral_risk = build_strong_neutral_risk_report(rows)
    neutral_factor_effect = build_neutral_factor_effect_report(rows)
    neutral_watch_ranking = build_neutral_watch_ranking_report(rows)
    neutral_v1_stability = build_neutral_v1_stability_report(neutral_watch_ranking)
    neutral_v2_veto = build_neutral_v2_veto_report(neutral_watch_ranking)
    weak_neutral_top3_followup = build_weak_neutral_top3_followup_report(
        weak_pass_watch_ranking, neutral_watch_ranking, neutral_v2_veto
    )
    weak_final_tuning = build_weak_final_tuning_report(weak_pass_watch_ranking)
    pass_watch_high_ret3_group = build_pass_watch_high_ret3_group_report(
        {
            "strong": strong_pass_watch_ranking,
            "weak": weak_pass_watch_ranking,
            "neutral": neutral_watch_ranking,
        }
    )
    env_skeleton_top1 = build_env_skeleton_top1_report(
        pass_watch_high_ret3_group,
        {
            "strong": strong_pass_watch_ranking,
            "weak": weak_pass_watch_ranking,
            "neutral": neutral_watch_ranking,
        },
    )
    stable_patterns = build_stable_patterns(
        base_segments=segments,
        macd_segments=macd_segments,
        factor_segments=factor_segments,
        min_samples=10,
    )
    classified = classify_misclassified(rows)
    output_dir = args.output_dir
    write_features_csv(output_dir / "features.csv", rows)
    write_json(output_dir / "segments.json", segments)
    write_json(output_dir / "macd_segments.json", macd_segments)
    write_json(output_dir / "macd_wave_rules.json", macd_wave_rules)
    write_macd_wave_rules_markdown(output_dir / "macd_wave_rules.md", macd_wave_rules)
    write_json(output_dir / "factor_segments.json", factor_segments)
    write_json(output_dir / "environment_comparisons.json", environment_comparisons)
    write_json(output_dir / "strong_pass_watch_ranking_report.json", strong_pass_watch_ranking)
    write_strong_pass_watch_ranking_markdown(output_dir / "strong_pass_watch_ranking_report.md", strong_pass_watch_ranking)
    write_json(output_dir / "strong_pass_composition_report.json", strong_pass_composition)
    write_strong_pass_composition_markdown(output_dir / "strong_pass_composition_report.md", strong_pass_composition)
    write_json(output_dir / "strong_b3_red_macd_report.json", strong_b3_red_macd)
    write_strong_b3_red_macd_markdown(output_dir / "strong_b3_red_macd_report.md", strong_b3_red_macd)
    write_json(output_dir / "strong_v1_negative_groups_report.json", strong_v1_negative_groups)
    write_strong_v1_negative_groups_markdown(
        output_dir / "strong_v1_negative_groups_report.md", strong_v1_negative_groups
    )
    write_json(output_dir / "weak_pass_watch_ranking_report.json", weak_pass_watch_ranking)
    write_weak_pass_watch_ranking_markdown(output_dir / "weak_pass_watch_ranking_report.md", weak_pass_watch_ranking)
    write_json(output_dir / "weak_v2_negative_groups_report.json", weak_v2_negative_groups)
    write_weak_v2_negative_groups_markdown(output_dir / "weak_v2_negative_groups_report.md", weak_v2_negative_groups)
    write_json(output_dir / "weak_indicator_report.json", weak_indicator)
    write_weak_indicator_markdown(output_dir / "weak_indicator_report.md", weak_indicator)
    write_json(output_dir / "weak_watch_positive_report.json", weak_watch_positive)
    write_weak_watch_positive_markdown(output_dir / "weak_watch_positive_report.md", weak_watch_positive)
    write_json(output_dir / "neutral_watch_positive_report.json", neutral_watch_positive)
    write_neutral_watch_positive_markdown(output_dir / "neutral_watch_positive_report.md", neutral_watch_positive)
    write_json(output_dir / "strong_neutral_risk_report.json", strong_neutral_risk)
    write_strong_neutral_risk_markdown(output_dir / "strong_neutral_risk_report.md", strong_neutral_risk)
    write_json(output_dir / "neutral_factor_effect_report.json", neutral_factor_effect)
    write_neutral_factor_effect_markdown(output_dir / "neutral_factor_effect_report.md", neutral_factor_effect)
    write_json(output_dir / "neutral_watch_ranking_report.json", neutral_watch_ranking)
    write_neutral_watch_ranking_markdown(output_dir / "neutral_watch_ranking_report.md", neutral_watch_ranking)
    write_json(output_dir / "neutral_v1_stability_report.json", neutral_v1_stability)
    write_neutral_v1_stability_markdown(output_dir / "neutral_v1_stability_report.md", neutral_v1_stability)
    write_json(output_dir / "neutral_v2_veto_report.json", neutral_v2_veto)
    write_neutral_v2_veto_markdown(output_dir / "neutral_v2_veto_report.md", neutral_v2_veto)
    write_json(output_dir / "weak_neutral_top3_followup_report.json", weak_neutral_top3_followup)
    write_weak_neutral_top3_followup_markdown(
        output_dir / "weak_neutral_top3_followup_report.md", weak_neutral_top3_followup
    )
    write_json(output_dir / "weak_final_tuning_report.json", weak_final_tuning)
    write_weak_final_tuning_markdown(output_dir / "weak_final_tuning_report.md", weak_final_tuning)
    write_json(output_dir / "pass_watch_high_ret3_group_report.json", pass_watch_high_ret3_group)
    write_pass_watch_high_ret3_group_markdown(
        output_dir / "pass_watch_high_ret3_group_report.md", pass_watch_high_ret3_group
    )
    write_json(output_dir / "env_skeleton_top1_report.json", env_skeleton_top1)
    write_env_skeleton_top1_markdown(output_dir / "env_skeleton_top1_report.md", env_skeleton_top1)
    write_json(output_dir / "stable_patterns.json", stable_patterns)
    write_stable_patterns_markdown(output_dir / "stable_patterns.md", stable_patterns)
    write_json(output_dir / "recommendations.json", build_recommendations(segments, macd_segments, factor_segments))
    write_summary(output_dir / "summary.md", rows, segments, macd_segments, factor_segments, environment_comparisons, stable_patterns)
    write_misclassified(output_dir / "misclassified_samples.md", classified)
    print(
        f"wrote diagnostics rows={len(rows)} segments={len(segments)} "
        f"macd_segments={len(macd_segments)} factor_segments={len(factor_segments)} "
        f"stable_patterns={sum(len(items) for group in stable_patterns.values() if isinstance(group, dict) for items in group.values())} "
        f"output_dir={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
