# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "psycopg[binary]",
# ]
# ///
from __future__ import annotations

import argparse
import csv
import math
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_METHOD = "b2"


IDENTITY_COLUMNS = ["date", "code", "name", "env", "method"]
REVIEW_COLUMNS = [
    "model_score",
    "model_rank",
    "llm_action",
    "risk_flags",
    "current_verdict",
    "baseline_verdict",
    "current_score",
    "baseline_score",
    "signal",
    "signal_type",
]
B2_REVIEW_COLUMNS = [
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "macd_phase",
    "daily_macd_phase_type",
    "daily_macd_wave_index",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_index",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
]
CONTEXT_COLUMNS = [
    "price_vs_90d_high",
    "price_vs_90d_low",
    "price_vs_90d_mid",
    "midline_state",
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
    "daily_macd_hist_state",
    "price_turnover_state",
    "k_value",
    "d_value",
    "j_value",
    "j_vs_k",
    "j_vs_d",
    "j_overheat",
    "j_repair_from_low",
    "close_vs_bbi",
    "bbi_bias_state",
    "bias_bucket",
    "obv_ratio_5d",
    "obv_state",
]
RAW_FACTOR_COLUMNS = [
    "close_to_ma25_pct",
    "close_to_zxdkx_pct",
    "ma25_to_zxdkx_pct",
    "ma25_slope_5d_pct",
    "zxdkx_slope_5d_pct",
    "zxdq_slope_5d_pct",
    "low_to_ma25_pct",
    "near_ma25_support_flag",
    "ma_aligned_flag",
    "zxdkx_up_1d_flag",
    "daily_rising_initial_flag",
    "macd_top_divergence_flag",
    "box_position_120d_pct",
    "close_to_120d_max_pct",
    "close_to_120d_min_pct",
    "close_to_120d_range_center_pct",
    "breakout_distance_120d_pct",
    "range_floor_distance_120d_pct",
    "range_width_120d_pct",
    "latest_bar_position_pct",
    "volume_to_ma5_ratio",
    "volume_to_ma20_ratio",
    "volume_ma5_to_ma20_ratio",
    "close_to_close_ma5_pct",
    "close_to_20d_max_close_pct",
    "pct_chg_1d",
    "price_up_1d_flag",
    "volume_up_1d_flag",
    "turnover_to_ma5_ratio",
    "abnormal_volume_event_days_ago",
    "abnormal_volume_to_ma20_ratio",
    "abnormal_event_body_pct",
    "abnormal_event_price_to_current_pct",
    "post_abnormal_min_body_to_event_price_pct",
    "post_abnormal_drawdown_pct",
    "abnormal_redundant_position_pct",
    "macd_dif_to_close_pct",
    "macd_dea_to_close_pct",
    "macd_hist_to_close_pct",
    "macd_hist_delta_to_close_pct",
    "macd_hist_slope_3d_to_close_pct",
    "macd_hist_positive_flag",
]
LABEL_COLUMNS = [
    "ret3",
    "ret5",
    "ret10",
    "max_drawdown_5d",
    "win3_vs_day_median",
    "win5_vs_day_median",
    "rank_label_3d",
    "rank_label_5d",
]
DATASET_COLUMNS = IDENTITY_COLUMNS + REVIEW_COLUMNS + B2_REVIEW_COLUMNS + CONTEXT_COLUMNS + RAW_FACTOR_COLUMNS + LABEL_COLUMNS


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def round4(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def normalize_env(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"weak", "neutral", "strong"} else "unknown"


def normalize_verdict(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"PASS", "WATCH", "FAIL"} else "UNKNOWN"


def pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0.0:
        return None
    return (current / base - 1.0) * 100.0


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
    return {"k_value": k, "d_value": d, "j_value": 3.0 * k - 2.0 * d}


def ema_values(values: Sequence[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def compute_macd_hist(close: Sequence[float]) -> list[float]:
    _dif, _dea, hist = compute_macd_lines(close)
    return hist


def compute_macd_lines(close: Sequence[float]) -> tuple[list[float], list[float], list[float]]:
    if not close:
        return [], [], []
    ema12 = ema_values(close, 12)
    ema26 = ema_values(close, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26)]
    dea = ema_values(dif, 9)
    hist = [d - e for d, e in zip(dif, dea)]
    return dif, dea, hist


def rolling_mean_series(values: Sequence[float], window: int, min_periods: int) -> list[float | None]:
    result: list[float | None] = []
    for idx in range(len(values)):
        start = max(0, idx - window + 1)
        count = idx - start + 1
        if count < min_periods:
            result.append(None)
            continue
        window_values = values[start : idx + 1]
        result.append(sum(window_values) / len(window_values))
    return result


def compute_zx_lines(close: Sequence[float]) -> tuple[list[float], list[float | None]]:
    if not close:
        return [], []
    first = ema_values(close, 10)
    zxdq = ema_values(first, 10)
    ma14 = rolling_mean_series(close, 14, 14)
    ma28 = rolling_mean_series(close, 28, 28)
    ma57 = rolling_mean_series(close, 57, 57)
    ma114 = rolling_mean_series(close, 114, 114)
    zxdkx: list[float | None] = []
    for values in zip(ma14, ma28, ma57, ma114):
        if any(value is None for value in values):
            zxdkx.append(None)
        else:
            zxdkx.append(sum(float(value) for value in values if value is not None) / 4.0)
    return zxdq, zxdkx


def ratio(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0.0:
        return None
    return current / base


def pct_of(value: float | None, base: float | None) -> float | None:
    computed = ratio(value, base)
    return None if computed is None else computed * 100.0


def flag(value: bool | None) -> int | str:
    if value is None:
        return ""
    return int(value)


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


def format_csv_value(value: Any) -> str:
    numeric = as_float(value)
    if numeric is not None and isinstance(value, (int, float)):
        return f"{numeric:.4f}".rstrip("0").rstrip(".")
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


def compute_forward_labels(price_rows: Sequence[dict[str, Any]], pick_date: str) -> dict[str, float | None]:
    history = sorted(price_rows, key=lambda row: str(row.get("trade_date")))
    current = [row for row in history if str(row.get("trade_date")) <= pick_date]
    if not current:
        return {"ret3": None, "ret5": None, "ret10": None, "max_drawdown_5d": None}
    entry_close = as_float(current[-1].get("close"))
    if entry_close is None or entry_close == 0.0:
        return {"ret3": None, "ret5": None, "ret10": None, "max_drawdown_5d": None}
    future = [row for row in history if str(row.get("trade_date")) > pick_date]

    def ret_at(position: int) -> float | None:
        index = position - 1
        if len(future) <= index:
            return None
        return round4(pct_change(as_float(future[index].get("close")), entry_close))

    lows = [as_float(row.get("low")) for row in future[:5]]
    valid_lows = [value for value in lows if value is not None]
    drawdown = round4(pct_change(min(valid_lows), entry_close)) if valid_lows else None
    return {
        "ret3": ret_at(3),
        "ret5": ret_at(5),
        "ret10": ret_at(10),
        "max_drawdown_5d": drawdown,
    }


def median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def quartile_labels(values_by_code: dict[str, float]) -> dict[str, int]:
    ordered = sorted(values_by_code.items(), key=lambda item: (item[1], item[0]))
    count = len(ordered)
    if count == 0:
        return {}
    if count == 1:
        return {ordered[0][0]: 3}
    result: dict[str, int] = {}
    for index, (code, _value) in enumerate(ordered):
        bucket = int(index * 3 / (count - 1))
        result[code] = min(bucket, 3)
    return result


def add_day_relative_labels(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row.get("date"))].append(dict(row))

    output: list[dict[str, Any]] = []
    for _pick_date, day_rows in sorted(by_date.items()):
        valid_ret3 = [as_float(row.get("ret3")) for row in day_rows]
        valid_ret3 = [value for value in valid_ret3 if value is not None]
        valid_ret5 = [as_float(row.get("ret5")) for row in day_rows]
        valid_ret5 = [value for value in valid_ret5 if value is not None]
        ret3_median = median(valid_ret3)
        ret5_median = median(valid_ret5)
        ret3_labels = quartile_labels(
            {str(row["code"]): as_float(row.get("ret3")) for row in day_rows if as_float(row.get("ret3")) is not None}
        )
        ret5_labels = quartile_labels(
            {str(row["code"]): as_float(row.get("ret5")) for row in day_rows if as_float(row.get("ret5")) is not None}
        )

        for row in day_rows:
            ret3 = as_float(row.get("ret3"))
            ret5 = as_float(row.get("ret5"))
            row["win3_vs_day_median"] = "" if ret3 is None or ret3_median is None else int(ret3 > ret3_median)
            row["win5_vs_day_median"] = "" if ret5 is None or ret5_median is None else int(ret5 > ret5_median)
            row["rank_label_3d"] = ret3_labels.get(str(row.get("code")), "")
            row["rank_label_5d"] = ret5_labels.get(str(row.get("code")), "")
            output.append(row)
    return output


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def selection_dirs(runtime_root: Path, method: str, start_date: str, end_date: str) -> list[Path]:
    root = runtime_root / "select"
    if not root.exists():
        return []
    dirs: list[Path] = []
    suffix = f".{method}"
    for path in sorted(root.glob(f"????-??-??{suffix}")):
        pick_date = path.name.removesuffix(suffix)
        if start_date <= pick_date <= end_date:
            dirs.append(path)
    return dirs


def json_factor_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def extract_selection_row(
    display: dict[str, Any],
    *,
    pick_date: str,
    method: str,
    env: str,
    factors: dict[str, Any],
) -> dict[str, Any]:
    row = {column: "" for column in DATASET_COLUMNS}
    risk_flags = display.get("llm_risk_flags")
    if isinstance(risk_flags, list):
        risk_flags_text = ",".join(str(value) for value in risk_flags)
    else:
        risk_flags_text = str(risk_flags or "")
    row.update(
        {
            "date": pick_date,
            "code": str(display.get("code") or "").strip(),
            "name": display.get("name") or "",
            "env": normalize_env(env),
            "method": method,
            "model_score": round4(as_float(display.get("model_score"))),
            "model_rank": display.get("model_rank") or "",
            "llm_action": display.get("llm_action") or "",
            "risk_flags": risk_flags_text,
            "current_score": round4(as_float(display.get("model_score"))),
        }
    )
    for key, value in factors.items():
        row[key] = json_factor_value(value)
    return row


def load_selection_rows(runtime_root: Path, *, method: str, start_date: str, end_date: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for select_dir in selection_dirs(runtime_root, method, start_date, end_date):
        pick_date = select_dir.name.removesuffix(f".{method}")
        run = read_json(select_dir / "run.json")
        display = read_json(select_dir / "display.json")
        factors = read_json(select_dir / "factors.json")
        if run is None:
            warnings.append(f"invalid_selection_json:{select_dir / 'run.json'}")
            continue
        if display is None:
            warnings.append(f"invalid_selection_json:{select_dir / 'display.json'}")
            continue
        if factors is None:
            warnings.append(f"invalid_selection_json:{select_dir / 'factors.json'}")
            continue

        environment = run.get("environment")
        env = "unknown"
        if isinstance(environment, dict):
            env = normalize_env(environment.get("state"))
        factor_rows = factors.get("rows") if isinstance(factors, dict) else None
        factor_by_code: dict[str, dict[str, Any]] = {}
        if isinstance(factor_rows, list):
            for factor_row in factor_rows:
                if not isinstance(factor_row, dict):
                    continue
                code = str(factor_row.get("code") or "").strip()
                payload = factor_row.get("factors")
                if code and isinstance(payload, dict):
                    factor_by_code[code] = payload

        display_rows = display.get("rows")
        if not isinstance(display_rows, list):
            warnings.append(f"invalid_selection_rows:{select_dir / 'display.json'}")
            continue
        for item in display_rows:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            row = extract_selection_row(
                item,
                pick_date=pick_date,
                method=method,
                env=env,
                factors=factor_by_code.get(code, {}),
            )
            if row["env"] == "unknown" and normalize_env(row.get("env")) == "unknown":
                factor_env = factor_by_code.get(code, {}).get("env")
                row["env"] = normalize_env(factor_env)
            rows.append(row)
    return rows, warnings


def candidate_files(runtime_root: Path, method: str, start_date: str, end_date: str) -> list[Path]:
    root = runtime_root / "candidates"
    if not root.exists():
        return []
    files: list[Path] = []
    suffix = f".{method}.json"
    for path in sorted(root.glob(f"????-??-??{suffix}")):
        pick_date = path.name.removesuffix(suffix)
        if start_date <= pick_date <= end_date:
            files.append(path)
    return files


def extract_candidate_row(candidate: dict[str, Any], *, pick_date: str, method: str, env: str = "unknown") -> dict[str, Any]:
    row = {column: "" for column in DATASET_COLUMNS}
    row.update(
        {
            "date": str(candidate.get("pick_date") or pick_date),
            "code": str(candidate.get("code") or candidate.get("ts_code") or "").strip(),
            "name": candidate.get("name") or "",
            "env": normalize_env(candidate.get("env") or env),
            "method": method,
            "signal": candidate.get("signal") or "",
            "signal_type": candidate.get("signal_type") or "",
        }
    )
    factors = candidate.get("factors")
    if isinstance(factors, dict):
        for key, value in factors.items():
            row[key] = json_factor_value(value)
    for key, value in candidate.items():
        if key in DATASET_COLUMNS and format_csv_value(value) != "":
            row[key] = json_factor_value(value)
    return row


def load_candidate_rows(runtime_root: Path, *, method: str, start_date: str, end_date: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in candidate_files(runtime_root, method, start_date, end_date):
        payload = read_json(path)
        if payload is None:
            warnings.append(f"invalid_candidate_json:{path}")
            continue
        pick_date = str(payload.get("pick_date") or path.name.removesuffix(f".{method}.json"))
        env = "unknown"
        environment = payload.get("environment")
        if isinstance(environment, dict):
            env = normalize_env(environment.get("state"))
        candidate_rows = payload.get("candidates")
        if not isinstance(candidate_rows, list):
            candidate_rows = payload.get("rows")
        if not isinstance(candidate_rows, list):
            warnings.append(f"invalid_candidate_rows:{path}")
            continue
        for candidate in candidate_rows:
            if not isinstance(candidate, dict):
                continue
            row = extract_candidate_row(candidate, pick_date=pick_date, method=method, env=env)
            if row["code"]:
                rows.append(row)
    return rows, warnings


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


def validate_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be a valid calendar date.") from exc


def resolve_output_dir(output_dir: Path | None, *, method: str) -> Path:
    return output_dir or PROJECT_ROOT / "diagnostics" / "ml" / method


def fetch_price_rows(dsn: str, symbols: Sequence[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    import psycopg

    if not symbols:
        return {}
    query = """
        SELECT ts_code, trade_date, open::double precision, close::double precision, high::double precision, low::double precision,
               vol::double precision, turnover_rate::double precision, pct_chg::double precision
        FROM daily_market
        WHERE ts_code = ANY(%s)
          AND trade_date >= %s
          AND trade_date <= %s
          AND close IS NOT NULL
        ORDER BY ts_code ASC, trade_date ASC
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (list(symbols), start_date, end_date))
            for ts_code, trade_date, open_price, close, high, low, vol, turnover_rate, pct_chg in cursor.fetchall():
                grouped[str(ts_code)].append(
                    {
                        "trade_date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
                        "open": as_float(open_price),
                        "close": as_float(close),
                        "high": as_float(high),
                        "low": as_float(low),
                        "vol": as_float(vol),
                        "turnover_rate": as_float(turnover_rate),
                        "pct_chg": as_float(pct_chg),
                    }
                )
    return dict(grouped)


def fetch_indicator_rows(dsn: str, symbols: Sequence[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    import psycopg

    if not symbols:
        return {}
    query = """
        SELECT ts_code, trade_date
             , (extra_factors_jsonb->>'bbi_bfq')::double precision
             , (extra_factors_jsonb->>'bias1_bfq')::double precision
             , (extra_factors_jsonb->>'bias2_bfq')::double precision
             , (extra_factors_jsonb->>'bias3_bfq')::double precision
             , (extra_factors_jsonb->>'obv_bfq')::double precision
        FROM daily_indicators
        WHERE ts_code = ANY(%s)
          AND trade_date >= %s
          AND trade_date <= %s
          AND extra_factors_jsonb IS NOT NULL
        ORDER BY ts_code ASC, trade_date ASC
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (list(symbols), start_date, end_date))
            for ts_code, trade_date, bbi, bias1, bias2, bias3, obv in cursor.fetchall():
                grouped[str(ts_code)].append(
                    {
                        "trade_date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
                        "bbi_bfq": as_float(bbi),
                        "bias1_bfq": as_float(bias1),
                        "bias2_bfq": as_float(bias2),
                        "bias3_bfq": as_float(bias3),
                        "obv_bfq": as_float(obv),
                    }
                )
    return dict(grouped)


def merge_indicator_rows(
    price_rows: dict[str, list[dict[str, Any]]], indicator_rows: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    if not indicator_rows:
        return price_rows
    merged_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol, rows in price_rows.items():
        indicators = {str(row.get("trade_date")): row for row in indicator_rows.get(symbol, [])}
        merged_rows = []
        for row in rows:
            indicator = indicators.get(str(row.get("trade_date")), {})
            merged_rows.append({**row, **{key: value for key, value in indicator.items() if key != "trade_date"}})
        merged_by_symbol[symbol] = merged_rows
    return merged_by_symbol


def context_features(price_rows: Sequence[dict[str, Any]], pick_date: str) -> dict[str, Any]:
    current = [
        row
        for row in sorted(price_rows, key=lambda row: str(row.get("trade_date")))
        if str(row.get("trade_date")) <= pick_date and as_float(row.get("close")) is not None
    ]
    base = {column: "" for column in CONTEXT_COLUMNS + RAW_FACTOR_COLUMNS}
    base.update(
        {
            "midline_state": "unknown",
            "support_stack_type": "unknown",
            "daily_macd_hist_state": "unknown",
            "price_turnover_state": "unknown",
            "bbi_bias_state": "unknown",
            "bias_bucket": "unknown",
            "obv_state": "unknown",
        }
    )
    if not current:
        return base

    close_values = [as_float(row.get("close")) for row in current]
    open_values = [as_float(row.get("open")) for row in current]
    high_values = [as_float(row.get("high")) for row in current]
    low_values = [as_float(row.get("low")) for row in current]
    if any(value is None for value in close_values):
        return base
    closes = [float(value) for value in close_values if value is not None]
    opens = [float(value) for value in open_values if value is not None]
    highs = [float(value) for value in high_values if value is not None]
    lows = [float(value) for value in low_values if value is not None]
    volumes = [float(value) for value in (as_float(row.get("vol")) for row in current) if value is not None]
    turnovers = [float(value) for value in (as_float(row.get("turnover_rate")) for row in current) if value is not None]
    latest_close = closes[-1]
    previous_close = closes[-2] if len(closes) >= 2 else None
    latest_open = opens[-1] if len(opens) == len(closes) else None
    latest_high = highs[-1] if highs else None
    latest_low = lows[-1] if lows else None
    tail_high = highs[-90:]
    tail_low = lows[-90:]
    high_90 = max(tail_high) if tail_high else None
    low_90 = min(tail_low) if tail_low else None
    mid_90 = (high_90 + low_90) / 2.0 if high_90 is not None and low_90 is not None else None
    ma25_series = [rolling_mean(closes[: idx + 1], 25) for idx in range(len(closes))]
    ma60_series = [rolling_mean(closes[: idx + 1], 60) for idx in range(len(closes))]
    zxdq_series, zxdkx_series = compute_zx_lines(closes)
    ma25 = ma25_series[-1]
    ma60 = ma60_series[-1]
    latest_zxdq = zxdq_series[-1] if zxdq_series else None
    latest_zxdkx = zxdkx_series[-1] if zxdkx_series else None
    previous_zxdkx = zxdkx_series[-2] if len(zxdkx_series) >= 2 else None
    avg_close5 = rolling_mean(closes, 5)
    high_close20 = max(closes[-20:]) if len(closes) >= 20 else None
    avg5 = rolling_mean(volumes, 5) if volumes else None
    avg10 = rolling_mean(volumes, 10) if volumes else None
    avg20 = rolling_mean(volumes, 20) if volumes else None
    latest_volume = volumes[-1] if volumes else None
    volume_ratio_5d = latest_volume / avg5 if latest_volume is not None and avg5 else None
    volume_ratio_10d = latest_volume / avg10 if latest_volume is not None and avg10 else None
    volume_ratio_20d = latest_volume / avg20 if latest_volume is not None and avg20 else None
    latest_turnover = turnovers[-1] if turnovers else None
    previous_turnover = turnovers[-2] if len(turnovers) >= 2 else None
    turnover_avg5 = rolling_mean(turnovers, 5) if turnovers else None
    turnover_ratio_5d = latest_turnover / turnover_avg5 if latest_turnover is not None and turnover_avg5 else None
    macd_dif, macd_dea, macd_hist = compute_macd_lines(closes)
    latest_macd_dif = macd_dif[-1] if macd_dif else None
    latest_macd_dea = macd_dea[-1] if macd_dea else None
    latest_macd_hist = macd_hist[-1] if macd_hist else None
    previous_macd_hist = macd_hist[-2] if len(macd_hist) >= 2 else None
    macd_hist_delta = latest_macd_hist - previous_macd_hist if latest_macd_hist is not None and previous_macd_hist is not None else None
    macd_hist_slope_3d = latest_macd_hist - macd_hist[-4] if len(macd_hist) >= 4 and latest_macd_hist is not None else None
    price_up = latest_close > previous_close if previous_close is not None else None
    previous_volume = volumes[-2] if len(volumes) >= 2 else None
    volume_up = latest_volume > previous_volume if latest_volume is not None and previous_volume is not None else None
    turnover_up = latest_turnover > previous_turnover if latest_turnover is not None and previous_turnover is not None else None
    kdj = compute_kdj(closes, highs, lows)
    k_value = kdj["k_value"]
    d_value = kdj["d_value"]
    j_value = kdj["j_value"]
    latest = current[-1]
    latest_bbi = as_float(latest.get("bbi_bfq"))
    latest_bias1 = as_float(latest.get("bias1_bfq"))
    latest_obv = as_float(latest.get("obv_bfq"))
    obv_values = [as_float(row.get("obv_bfq")) for row in current]
    known_obv = [float(value) for value in obv_values if value is not None]
    obv_avg5 = rolling_mean(known_obv, 5) if known_obv else None
    obv_ratio = latest_obv / obv_avg5 if latest_obv is not None and obv_avg5 not in (None, 0.0) else None
    range_values = list(zip(highs, lows))

    tail_high_120 = highs[-120:]
    tail_low_120 = lows[-120:]
    high_120 = max(tail_high_120) if tail_high_120 else None
    low_120 = min(tail_low_120) if tail_low_120 else None
    range_center_120 = (high_120 + low_120) / 2.0 if high_120 is not None and low_120 is not None else None
    range_width_120 = high_120 - low_120 if high_120 is not None and low_120 is not None else None
    box_position_120 = (
        (latest_close - low_120) / range_width_120 * 100.0
        if low_120 is not None and range_width_120 is not None and range_width_120 != 0.0
        else None
    )
    latest_bar_range = latest_high - latest_low if latest_high is not None and latest_low is not None else None
    latest_bar_position = (
        (latest_close - latest_low) / latest_bar_range * 100.0
        if latest_low is not None and latest_bar_range is not None and latest_bar_range != 0.0
        else None
    )

    abnormal: dict[str, Any] = {}
    if volumes:
        event_start = max(0, len(volumes) - 90)
        event_offset, event_volume = max(enumerate(volumes[event_start:]), key=lambda item: item[1])
        event_idx = event_start + event_offset
        event_open = opens[event_idx] if len(opens) == len(closes) else None
        event_close = closes[event_idx]
        event_price = max(event_open, event_close) if event_open is not None else event_close
        event_volume_ma20 = rolling_mean(volumes[: event_idx + 1], 20)
        min_body_after = None
        if len(opens) == len(closes):
            body_lows = [min(opens[idx], closes[idx]) for idx in range(event_idx + 1, len(closes))]
            if body_lows:
                min_body_after = min(body_lows)
        if min_body_after is None and event_open is not None:
            min_body_after = min(event_open, event_close)
        redundant_price = event_price * 0.90 if event_price is not None else None
        abnormal = {
            "abnormal_volume_event_days_ago": len(closes) - 1 - event_idx,
            "abnormal_volume_to_ma20_ratio": rounded(ratio(event_volume, event_volume_ma20)),
            "abnormal_event_body_pct": rounded(abs(pct_change(event_close, event_open) or 0.0) if event_open else None),
            "abnormal_event_price_to_current_pct": rounded(pct_change(event_price, latest_close)),
            "post_abnormal_min_body_to_event_price_pct": rounded(pct_change(min_body_after, event_price)),
            "post_abnormal_drawdown_pct": rounded(pct_change(min_body_after, event_price)),
            "abnormal_redundant_position_pct": rounded(pct_change(min_body_after, redundant_price)),
        }

    result = {
        "price_vs_90d_high": rounded(pct_change(latest_close, high_90)),
        "price_vs_90d_low": rounded(pct_change(latest_close, low_90)),
        "price_vs_90d_mid": rounded(pct_change(latest_close, mid_90)),
        "midline_state": "above_midline" if latest_close is not None and mid_90 is not None and latest_close >= mid_90 else "below_midline" if mid_90 is not None else "unknown",
        "close_vs_ma25": rounded(pct_change(latest_close, ma25)),
        "close_vs_ma60": rounded(pct_change(latest_close, ma60)),
        "ma25_vs_ma60": rounded(pct_change(ma25, ma60)),
        "ma25_slope_5d": rounded(slope_pct([value for value in ma25_series if value is not None], 5)),
        "ma60_slope_5d": rounded(slope_pct([value for value in ma60_series if value is not None], 5)),
        "support_stack_type": support_stack_type(latest_close, ma25, ma60),
        "days_since_last_high": days_since_tail_extreme(tail_high, high=True),
        "days_since_last_low": days_since_tail_extreme(tail_low, high=False),
        "volume_ratio_5d": rounded(volume_ratio_5d),
        "volume_ratio_10d": rounded(volume_ratio_10d),
        "turnover_rate": rounded(latest_turnover),
        "turnover_rate_ratio_5d": rounded(turnover_ratio_5d),
        "daily_pct_chg": rounded(as_float(latest.get("pct_chg")) or pct_change(latest_close, previous_close)),
        "daily_macd_hist_state": macd_hist_state(latest_macd_hist, previous_macd_hist),
        "price_turnover_state": price_turnover_state(price_up, turnover_up),
        "k_value": rounded(k_value),
        "d_value": rounded(d_value),
        "j_value": rounded(j_value),
        "j_vs_k": rounded((j_value - k_value) if j_value is not None and k_value is not None else None),
        "j_vs_d": rounded((j_value - d_value) if j_value is not None and d_value is not None else None),
        "j_overheat": bool(j_value is not None and j_value >= 100.0),
        "j_repair_from_low": bool(j_value is not None and k_value is not None and j_value > k_value and j_value < 50.0),
        "close_vs_bbi": rounded(pct_change(latest_close, latest_bbi)),
        "bbi_bias_state": bbi_bias_state(latest_close, latest_bbi),
        "bias_bucket": bias_bucket(latest_bias1),
        "obv_ratio_5d": rounded(obv_ratio),
        "obv_state": obv_state(latest_obv, obv_ratio),
        "close_to_ma25_pct": rounded(pct_change(latest_close, ma25)),
        "close_to_zxdkx_pct": rounded(pct_change(latest_close, latest_zxdkx)),
        "ma25_to_zxdkx_pct": rounded(pct_change(ma25, latest_zxdkx)),
        "ma25_slope_5d_pct": rounded(slope_pct([value for value in ma25_series if value is not None], 5)),
        "zxdkx_slope_5d_pct": rounded(slope_pct([value for value in zxdkx_series if value is not None], 5)),
        "zxdq_slope_5d_pct": rounded(slope_pct(zxdq_series, 5)),
        "low_to_ma25_pct": rounded(pct_change(latest_low, ma25)),
        "near_ma25_support_flag": flag(latest_low <= ma25 * 1.03 if latest_low is not None and ma25 is not None else None),
        "ma_aligned_flag": flag(latest_close >= ma25 >= latest_zxdkx if ma25 is not None and latest_zxdkx is not None else None),
        "zxdkx_up_1d_flag": flag(latest_zxdkx >= previous_zxdkx if latest_zxdkx is not None and previous_zxdkx is not None else None),
        "daily_rising_initial_flag": "",
        "macd_top_divergence_flag": "",
        "box_position_120d_pct": rounded(box_position_120),
        "close_to_120d_max_pct": rounded(pct_change(latest_close, high_120)),
        "close_to_120d_min_pct": rounded(pct_change(latest_close, low_120)),
        "close_to_120d_range_center_pct": rounded(pct_change(latest_close, range_center_120)),
        "breakout_distance_120d_pct": rounded(pct_change(latest_close, high_120)),
        "range_floor_distance_120d_pct": rounded(pct_change(latest_close, low_120)),
        "range_width_120d_pct": rounded((range_width_120 / latest_close * 100.0) if range_width_120 is not None and latest_close else None),
        "latest_bar_position_pct": rounded(latest_bar_position),
        "volume_to_ma5_ratio": rounded(volume_ratio_5d),
        "volume_to_ma20_ratio": rounded(volume_ratio_20d),
        "volume_ma5_to_ma20_ratio": rounded(ratio(avg5, avg20)),
        "close_to_close_ma5_pct": rounded(pct_change(latest_close, avg_close5)),
        "close_to_20d_max_close_pct": rounded(pct_change(latest_close, high_close20)),
        "pct_chg_1d": rounded(pct_change(latest_close, previous_close)),
        "price_up_1d_flag": flag(price_up),
        "volume_up_1d_flag": flag(volume_up),
        "turnover_to_ma5_ratio": rounded(turnover_ratio_5d),
        "macd_dif_to_close_pct": rounded(pct_of(latest_macd_dif, latest_close)),
        "macd_dea_to_close_pct": rounded(pct_of(latest_macd_dea, latest_close)),
        "macd_hist_to_close_pct": rounded(pct_of(latest_macd_hist, latest_close)),
        "macd_hist_delta_to_close_pct": rounded(pct_of(macd_hist_delta, latest_close)),
        "macd_hist_slope_3d_to_close_pct": rounded(pct_of(macd_hist_slope_3d, latest_close)),
        "macd_hist_positive_flag": flag(latest_macd_hist > 0.0 if latest_macd_hist is not None else None),
    }
    result.update(abnormal)
    for window in (20, 40):
        tail = range_values[-window:]
        if len(tail) >= window:
            max_high = max(high for high, _low in tail)
            min_low = min(low for _high, low in tail)
            result[f"range_compression_{window}d"] = rounded((max_high - min_low) / latest_close * 100.0)
    base.update(result)
    return base


def build_dataset_rows(
    selection_rows: Sequence[dict[str, Any]], price_rows_by_symbol: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for selection_row in selection_rows:
        row = {column: "" for column in DATASET_COLUMNS}
        row.update(selection_row)
        symbol_rows = price_rows_by_symbol.get(str(row.get("code")), [])
        row.update(context_features(symbol_rows, str(row.get("date"))))
        for key, value in selection_row.items():
            if key not in LABEL_COLUMNS and format_csv_value(value) != "":
                row[key] = value
        row.update(compute_forward_labels(symbol_rows, str(row.get("date"))))
        rows.append(row)
    return add_day_relative_labels(rows)


def dataset_summary(
    rows: Sequence[dict[str, Any]],
    *,
    runtime_root: Path,
    method: str,
    start_date: str,
    end_date: str,
    warnings: Sequence[str],
    source: str,
) -> dict[str, Any]:
    env_counts = {env: 0 for env in ["weak", "neutral", "strong", "unknown"]}
    for row in rows:
        env_counts[normalize_env(row.get("env"))] += 1
    label_counts = {
        label: sum(1 for row in rows if format_csv_value(row.get(label)) != "")
        for label in ["ret3", "ret5", "ret10", "max_drawdown_5d"]
    }
    return {
        "method": method,
        "source": source,
        "start_date": start_date,
        "end_date": end_date,
        "runtime_root": str(runtime_root),
        "row_count": len(rows),
        "date_count": len({str(row.get("date")) for row in rows}),
        "symbol_count": len({str(row.get("code")) for row in rows}),
        "env_counts": env_counts,
        "label_non_null_counts": label_counts,
        "invalid_selection_artifact_count": sum(1 for item in warnings if item.startswith("invalid_selection_")),
        "invalid_candidate_artifact_count": sum(1 for item in warnings if item.startswith("invalid_candidate_")),
        "missing_price_row_count": sum(1 for row in rows if format_csv_value(row.get("ret3")) == ""),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "warnings": list(warnings),
    }


def write_dataset(
    rows: Sequence[dict[str, Any]],
    output_dir: Path,
    *,
    runtime_root: Path,
    method: str,
    start_date: str,
    end_date: str,
    warnings: Sequence[str],
    source: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "rank_dataset.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DATASET_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_csv_value(row.get(column)) for column in DATASET_COLUMNS})
    (output_dir / "rank_dataset_summary.json").write_text(
        json.dumps(
            dataset_summary(
                rows,
                runtime_root=runtime_root,
                method=method,
                start_date=start_date,
                end_date=end_date,
                warnings=warnings,
                source=source,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build offline review ranking dataset.")
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--dsn")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--start-date", required=True, type=validate_date)
    parser.add_argument("--end-date", required=True, type=validate_date)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source", choices=["candidates", "select"], default="candidates")
    parser.add_argument("--min-history-days", type=int, default=120)
    parser.add_argument("--forward-days", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = resolve_output_dir(args.output_dir, method=args.method)
    if not args.runtime_root.exists():
        raise SystemExit(f"runtime root does not exist: {args.runtime_root}")
    dsn = resolve_dsn(args.dsn)
    if args.source == "select":
        training_input_rows, warnings = load_selection_rows(
            args.runtime_root, method=args.method, start_date=args.start_date, end_date=args.end_date
        )
    else:
        training_input_rows, warnings = load_candidate_rows(
            args.runtime_root, method=args.method, start_date=args.start_date, end_date=args.end_date
        )
    symbols = sorted({str(row.get("code")) for row in training_input_rows if row.get("code")})
    query_start = (date.fromisoformat(args.start_date) - timedelta(days=args.min_history_days)).isoformat()
    query_end = (date.fromisoformat(args.end_date) + timedelta(days=args.forward_days)).isoformat()
    prices = merge_indicator_rows(fetch_price_rows(dsn, symbols, query_start, query_end), fetch_indicator_rows(dsn, symbols, query_start, query_end))
    rows = build_dataset_rows(training_input_rows, prices)
    write_dataset(
        rows,
        output_dir,
        runtime_root=args.runtime_root,
        method=args.method,
        start_date=args.start_date,
        end_date=args.end_date,
        warnings=warnings,
        source=args.source,
    )
    print(f"wrote {len(rows)} rows to {output_dir / 'rank_dataset.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
