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
DEFAULT_METHOD = "b2"
RUNTIME_ROOT_ENV = "STOCK_SELECT_RUNTIME_ROOT"
EXPECTED_FACTOR_ARTIFACT_VERSION = 2
EXPECTED_FACTOR_LIBRARY_VERSION = "rust-factor-library-v3"


IDENTITY_COLUMNS = ["date", "code", "name", "env", "method"]
REVIEW_METADATA_COLUMNS = [
    "model_score",
    "model_rank",
    "llm_action",
    "risk_flags",
]
TRAINING_CATEGORICAL_COLUMNS = [
    "signal",
    "signal_type",
    "daily_macd_phase_type",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
    "midline_state",
]
LSH_TRAINING_CATEGORICAL_COLUMNS = [
    "signal",
]

TRAINING_MACD_NUMERIC_COLUMNS = [
    "macd_phase",
    "daily_macd_wave_index",
    "weekly_macd_wave_index",
]
CONTEXT_NUMERIC_COLUMNS = [
    "price_vs_90d_high",
    "price_vs_90d_low",
    "price_vs_90d_mid",
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
    "box_mid_position_120d_pct",
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
    "range_compression_20d",
    "range_compression_40d",
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
    "boll_width_pct",
    "dmi_adxr_qfq",
    "dmi_adx_qfq",
    "dmi_pdi_qfq",
    "dmi_mdi_qfq",
    "dmi_pdi_mdi_spread_qfq",
    "dmi_adx_adxr_gap_qfq",
    "wr_qfq",
    "mtm_qfq",
    "roc_qfq",
    "trix_qfq",
    "obv_qfq",
    "vr_qfq",
    "psy_qfq",
    "bias1_qfq",
    "turnover_rate_f",
    "dist_to_up_limit_pct",
    "dist_to_down_limit_pct",
    "large_net_amount_to_amount_pct",
    "small_net_amount_to_amount_pct",
    "net_mf_amount_to_amount_pct",
    "turnover_n",
    "market_up_ratio",
    "market_ge5_ratio",
    "market_le_minus5_ratio",
    "market_median_pct_chg",
    "market_amount_ma5_ratio",
    "market_net_mf_to_amount_pct",
    "market_approx_limit_up_count",
    "market_approx_limit_down_count",
    "market_sse_ret5_pct",
    "market_sse_ret20_pct",
    "market_sse_ma20_bias_pct",
    "market_sse_volatility20_pct",
    "market_cn2000_ret5_pct",
    "market_cn2000_ret20_pct",
    "market_cn2000_ma20_bias_pct",
    "market_cn2000_volatility20_pct",
    "market_broad_ret5_pct",
    "market_broad_ret20_pct",
    "market_broad_ma20_bias_pct",
    "market_broad_volatility20_pct",
    "sw_l2_ret5_pct",
    "sw_l2_ret20_pct",
    "sw_l2_ma20_bias_pct",
    "sw_l2_volatility20_pct",
    "sw_l2_ret5_rank_pct",
    "sw_l2_ret20_rank_pct",
    "sw_l2_vs_market_ret5_pct",
    "sw_l2_vs_market_ret20_pct",
    "stock_vs_sw_l2_ret5_pct",
    "stock_vs_sw_l2_ret20_pct",
    "sw_l2_up_ratio",
    "sw_l2_ge5_ratio",
    "sw_l2_limit_up_ratio",
    "sw_l2_limit_down_ratio",
    "sw_l2_amount_share_pct",
    "sw_l2_amount_share_rank_pct",
    "sw_l2_amount_share_ma5_ratio",
    "sw_l2_top1_amount_share_pct",
    "sw_l2_top3_amount_share_pct",
    "sw_l2_top5_amount_share_pct",
    "sw_l2_net_mf_to_amount_pct",
    "sw_l2_net_mf_market_share_pct",
    "sw_l2_net_mf_rank_pct",
    "stock_amount_to_sw_l2_amount_pct",
    "stock_net_mf_to_sw_l2_amount_pct",
    "cyq_winner_rate",
    "cyq_cost_50_to_close_pct",
    "cyq_cost_85_to_close_pct",
    "cyq_weight_avg_to_close_pct",
    "cyq_cost_70_width_pct",
    "cyq_cost_90_width_pct",
]
B2_RDAGENT_RAW_FACTOR_COLUMNS = [
    "D",
    "close_to_lt_r_pct",
    "lt_r_to_ma60_pct",
    "hl90_position",
    "hl90_range_pct",
    "close_to_hl90_mid_pct",
    "bar_close_position",
    "upper_shadow_pct",
    "weekly_dea_pctile",
    "weekly_macd_hist",
    "monthly_dea_pctile",
    "monthly_macd_hist",
    "b2_bullish_engulf_prev_bearish_flag",
    "b2_volume_bullish_engulf_prev_bearish_flag",
    "b2_bullish_engulf_volume_ratio",
    "b2_yang_engulf_ma25",
    "b2_yang_engulf_ma25_vol_ratio",
    "b2_yang_engulf_ma25_strength",
]
CHIP_AGE_RAW_FACTOR_COLUMNS = [
    "total_mass",
    "chip_age_layer_sum",
    "chip_age_ultrashort_ratio",
    "chip_age_short_ratio",
    "chip_age_mid_ratio",
    "chip_age_long_ratio",
    "profit_ratio",
    "avg_cost_close_ratio",
    "peak_price_close_ratio",
    "chip_entropy",
    "chip_concentration",
    *[f"chip_age_l{layer}_b{bin_index:02}" for layer in range(4) for bin_index in range(32)],
]
B2_RAW_FACTOR_COLUMNS = RAW_FACTOR_COLUMNS + CHIP_AGE_RAW_FACTOR_COLUMNS + B2_RDAGENT_RAW_FACTOR_COLUMNS
B3_SPECIFIC_RAW_FACTOR_COLUMNS = [
    "b3_volume_shrink_ratio",
    "b3_amplitude_pct",
    "b3_body_pct",
    "b3_upper_shadow_pct",
    "b3_lower_shadow_pct",
    "b3_j_delta",
    "b3_prev_b2_flag",
    "b3_plus_flag",
]
B3_RAW_FACTOR_COLUMNS = RAW_FACTOR_COLUMNS + CHIP_AGE_RAW_FACTOR_COLUMNS + B3_SPECIFIC_RAW_FACTOR_COLUMNS
LSH_SPECIFIC_RAW_FACTOR_COLUMNS = [
    "lsh_daily_macd_wave_index",
    "lsh_weekly_macd_wave_index",
    "lsh_daily_macd_rising_initial_flag",
    "lsh_weekly_macd_rising_initial_flag",
    "lsh_daily_macd_top_divergence_flag",
    "lsh_weekly_macd_top_divergence_flag",
    "lsh_weekly_daily_constructive_combo_flag",
    "lsh_bullish_engulf_prev_bearish_flag",
    "lsh_volume_bullish_engulf_prev_bearish_flag",
    "lsh_bullish_engulf_volume_ratio",
]
LSH_EXCLUDED_RAW_FACTOR_COLUMNS = {
    "vr_qfq",
    "cyq_cost_85_to_close_pct",
}
LSH_RAW_FACTOR_COLUMNS = [
    column for column in RAW_FACTOR_COLUMNS if column not in LSH_EXCLUDED_RAW_FACTOR_COLUMNS
] + CHIP_AGE_RAW_FACTOR_COLUMNS + LSH_SPECIFIC_RAW_FACTOR_COLUMNS
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
METHOD_RAW_FACTOR_COLUMNS = {
    "b2": B2_RAW_FACTOR_COLUMNS,
    "b3": B3_RAW_FACTOR_COLUMNS,
    "lsh": LSH_RAW_FACTOR_COLUMNS,
}


def training_categorical_columns_for_method(method: str) -> list[str]:
    if method == "lsh":
        return list(LSH_TRAINING_CATEGORICAL_COLUMNS)
    return list(TRAINING_CATEGORICAL_COLUMNS)


def training_macd_numeric_columns_for_method(method: str) -> list[str]:
    if method == "lsh":
        return []
    return list(TRAINING_MACD_NUMERIC_COLUMNS)


def context_numeric_columns_for_method(method: str) -> list[str]:
    if method == "lsh":
        return []
    return list(CONTEXT_NUMERIC_COLUMNS)


def raw_factor_columns_for_method(method: str) -> list[str]:
    return list(METHOD_RAW_FACTOR_COLUMNS.get(method, RAW_FACTOR_COLUMNS))


def confirmed_training_columns_for_method(method: str) -> list[str]:
    return (
        training_categorical_columns_for_method(method)
        + training_macd_numeric_columns_for_method(method)
        + context_numeric_columns_for_method(method)
        + raw_factor_columns_for_method(method)
    )


def dataset_columns_for_method(method: str) -> list[str]:
    return (
        IDENTITY_COLUMNS
        + REVIEW_METADATA_COLUMNS
        + confirmed_training_columns_for_method(method)
        + LABEL_COLUMNS
    )


def dataset_column_set_for_method(method: str) -> set[str]:
    return set(dataset_columns_for_method(method))


DATASET_COLUMNS = dataset_columns_for_method(DEFAULT_METHOD)
DATASET_COLUMN_SET = set(DATASET_COLUMNS)


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
    entry_adj_factor = valid_adj_factor(current[-1].get("adj_factor"))
    entry_close = adjusted_price(
        current[-1].get("close"),
        current[-1].get("adj_factor"),
        entry_adj_factor,
    )
    if entry_close is None or entry_close == 0.0:
        return {"ret3": None, "ret5": None, "ret10": None, "max_drawdown_5d": None}
    future = [row for row in history if str(row.get("trade_date")) > pick_date]

    def ret_at(position: int) -> float | None:
        index = position - 1
        if len(future) <= index:
            return None
        close = adjusted_price(
            future[index].get("close"),
            future[index].get("adj_factor"),
            entry_adj_factor,
        )
        return round4(pct_change(close, entry_close))

    lows = [
        adjusted_price(row.get("low"), row.get("adj_factor"), entry_adj_factor)
        for row in future[:5]
    ]
    valid_lows = [value for value in lows if value is not None]
    drawdown = round4(pct_change(min(valid_lows), entry_close)) if valid_lows else None
    return {
        "ret3": ret_at(3),
        "ret5": ret_at(5),
        "ret10": ret_at(10),
        "max_drawdown_5d": drawdown,
    }


def valid_adj_factor(value: Any) -> float | None:
    parsed = as_float(value)
    if parsed is None or parsed <= 0.0:
        return None
    return parsed


def adjusted_price(value: Any, adj_factor: Any, base_adj_factor: float | None) -> float | None:
    price = as_float(value)
    if price is None:
        return None
    current_factor = valid_adj_factor(adj_factor)
    if current_factor is None or base_adj_factor is None:
        return price
    return price * current_factor / base_adj_factor


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


def factor_artifact_key_for_date(pick_date: str, *, intraday: bool = False) -> str:
    return f"{pick_date}.intraday" if intraday else pick_date


def validate_factor_artifact_contract(payload: dict[str, Any], *, method: str, artifact_key: str) -> str | None:
    artifact_version = payload.get("artifact_version")
    library_version = payload.get("factor_library_version")
    if artifact_version == EXPECTED_FACTOR_ARTIFACT_VERSION and library_version == EXPECTED_FACTOR_LIBRARY_VERSION:
        return None
    return (
        f"stale_factor_artifact:{artifact_key}.{method}:"
        f"artifact_version={artifact_version}:factor_library_version={library_version}"
    )


def load_factor_artifact_rows(runtime_root: Path, *, method: str, artifact_key: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    path = runtime_root / "factors" / f"{artifact_key}.{method}" / "factors.json"
    if not path.exists():
        return {}, [f"missing_factor_artifact:{artifact_key}.{method}"]
    payload = read_json(path)
    if payload is None:
        return {}, [f"invalid_factor_artifact:{path}"]
    stale_warning = validate_factor_artifact_contract(payload, method=method, artifact_key=artifact_key)
    if stale_warning is not None:
        return {}, [stale_warning]
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}, [f"invalid_factor_rows:{path}"]
    factors_by_code: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip()
        payload_factors = row.get("factors")
        if not code or not isinstance(payload_factors, dict):
            continue
        factors_by_code[code] = {key: json_factor_value(value) for key, value in payload_factors.items()}
    if not factors_by_code:
        warnings.append(f"empty_factor_artifact:{artifact_key}.{method}")
    return factors_by_code, warnings


def merge_factor_artifact_values(row: dict[str, Any], factors: dict[str, Any], *, method: str = DEFAULT_METHOD) -> None:
    dataset_column_set = dataset_column_set_for_method(method)
    for key, value in factors.items():
        if key in LABEL_COLUMNS or key not in dataset_column_set:
            continue
        row[key] = json_factor_value(value)
    if normalize_env(row.get("env")) == "unknown" and normalize_env(factors.get("env")) != "unknown":
        row["env"] = normalize_env(factors.get("env"))


def extract_selection_row(
    display: dict[str, Any],
    *,
    pick_date: str,
    method: str,
    env: str,
    factors: dict[str, Any],
) -> dict[str, Any]:
    dataset_columns = dataset_columns_for_method(method)
    dataset_column_set = set(dataset_columns)
    row = {column: "" for column in dataset_columns}
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
        }
    )
    for key, value in factors.items():
        if key in dataset_column_set:
            row[key] = json_factor_value(value)
    return row


def load_selection_rows(runtime_root: Path, *, method: str, start_date: str, end_date: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for select_dir in selection_dirs(runtime_root, method, start_date, end_date):
        pick_date = select_dir.name.removesuffix(f".{method}")
        artifact_key = factor_artifact_key_for_date(pick_date)
        run = read_json(select_dir / "run.json")
        display = read_json(select_dir / "display.json")
        if run is None:
            warnings.append(f"invalid_selection_json:{select_dir / 'run.json'}")
            continue
        if display is None:
            warnings.append(f"invalid_selection_json:{select_dir / 'display.json'}")
            continue

        environment = run.get("environment")
        env = "unknown"
        if isinstance(environment, dict):
            env = normalize_env(environment.get("state"))
        factor_by_code, factor_warnings = load_factor_artifact_rows(runtime_root, method=method, artifact_key=artifact_key)
        warnings.extend(factor_warnings)
        if not factor_by_code:
            continue

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
    dataset_columns = dataset_columns_for_method(method)
    dataset_column_set = set(dataset_columns)
    row = {column: "" for column in dataset_columns}
    row.update(
        {
            "date": str(candidate.get("pick_date") or pick_date),
            "code": str(candidate.get("code") or candidate.get("ts_code") or "").strip(),
            "name": candidate.get("name") or "",
            "env": normalize_env(candidate.get("env") or env),
            "method": method,
            "signal": candidate.get("signal") or "",
        }
    )
    factors = candidate.get("factors")
    if isinstance(factors, dict):
        for key, value in factors.items():
            if key in dataset_column_set:
                row[key] = json_factor_value(value)
    for key, value in candidate.items():
        if key in dataset_column_set and format_csv_value(value) != "":
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
        artifact_key = factor_artifact_key_for_date(pick_date)
        factor_by_code, factor_warnings = load_factor_artifact_rows(runtime_root, method=method, artifact_key=artifact_key)
        warnings.extend(factor_warnings)
        if not factor_by_code:
            continue
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
            merge_factor_artifact_values(
                row,
                factor_by_code.get(str(row.get("code") or ""), {}),
                method=method,
            )
            if row["code"]:
                rows.append(row)
    return rows, warnings


ExternalFeatureKey = tuple[str, str]


def external_feature_columns_for_method(method: str) -> set[str]:
    return set(raw_factor_columns_for_method(method))


def load_external_feature_rows(
    paths: Path | Sequence[Path],
    *,
    method: str = DEFAULT_METHOD,
) -> tuple[dict[ExternalFeatureKey, dict[str, Any]], list[str]]:
    feature_paths = [paths] if isinstance(paths, Path) else list(paths)
    allowed_columns = external_feature_columns_for_method(method)
    rows: dict[ExternalFeatureKey, dict[str, Any]] = {}
    warnings: list[str] = []

    for path in feature_paths:
        if not path.exists():
            warnings.append(f"missing_external_feature_csv:{path}")
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_index, raw_row in enumerate(reader, start=2):
                row_date = str(raw_row.get("date") or raw_row.get("trade_date") or "").strip()
                code = str(raw_row.get("code") or raw_row.get("symbol") or raw_row.get("ts_code") or "").strip()
                if not row_date or not code:
                    warnings.append(f"invalid_external_feature_key:{path}:{row_index}")
                    continue
                values: dict[str, Any] = {}
                for column, raw_value in raw_row.items():
                    if column not in allowed_columns:
                        continue
                    value = as_float(raw_value)
                    if value is None:
                        continue
                    values[column] = value
                if values:
                    rows[(row_date, code)] = values
    return rows, warnings


def merge_external_feature_values(
    row: dict[str, Any],
    external_features_by_key: dict[ExternalFeatureKey, dict[str, Any]],
    *,
    method: str = DEFAULT_METHOD,
) -> None:
    allowed_columns = external_feature_columns_for_method(method)
    features = external_features_by_key.get((str(row.get("date") or ""), str(row.get("code") or "")))
    if not features:
        return
    for key, value in features.items():
        if key in allowed_columns and format_csv_value(value) != "":
            row[key] = value


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


def resolve_runtime_root(
    cli_runtime_root: Path | None,
    *,
    env_runtime_root: str | None = None,
    dotenv_path: Path = PROJECT_ROOT / ".env",
) -> Path:
    if cli_runtime_root is not None:
        return cli_runtime_root.expanduser()
    if env_runtime_root and env_runtime_root.strip():
        return Path(env_runtime_root.strip()).expanduser()
    dotenv_value = load_dotenv_value(dotenv_path, RUNTIME_ROOT_ENV)
    if dotenv_value:
        return Path(dotenv_value).expanduser()
    raise ValueError(f"runtime root is required; set {RUNTIME_ROOT_ENV} in .env or pass --runtime-root.")


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
               vol::double precision, turnover_rate::double precision, pct_chg::double precision,
               CASE
                   WHEN extra_market_jsonb ? 'adj_factor'
                   THEN (extra_market_jsonb->>'adj_factor')::double precision
               END AS adj_factor
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
            for ts_code, trade_date, open_price, close, high, low, vol, turnover_rate, pct_chg, adj_factor in cursor.fetchall():
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
                        "adj_factor": as_float(adj_factor),
                    }
                )
    return dict(grouped)


def build_dataset_rows(
    selection_rows: Sequence[dict[str, Any]],
    price_rows_by_symbol: dict[str, list[dict[str, Any]]],
    *,
    method: str = DEFAULT_METHOD,
    external_features_by_key: dict[ExternalFeatureKey, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    dataset_columns = dataset_columns_for_method(method)
    dataset_column_set = set(dataset_columns)
    external_features_by_key = external_features_by_key or {}
    rows: list[dict[str, Any]] = []
    for selection_row in selection_rows:
        row = {column: "" for column in dataset_columns}
        row.update({key: value for key, value in selection_row.items() if key in dataset_column_set})
        symbol_rows = price_rows_by_symbol.get(str(row.get("code")), [])
        for key, value in selection_row.items():
            if key in dataset_column_set and key not in LABEL_COLUMNS and format_csv_value(value) != "":
                row[key] = value
        merge_external_feature_values(row, external_features_by_key, method=method)
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
    dataset_columns = dataset_columns_for_method(method)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "rank_dataset.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=dataset_columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: format_csv_value(row.get(column)) for column in dataset_columns})
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


FATAL_FACTOR_WARNING_PREFIXES = (
    "missing_factor_artifact:",
    "stale_factor_artifact:",
    "invalid_factor_artifact:",
    "invalid_factor_rows:",
    "empty_factor_artifact:",
)


def factor_artifact_label_from_warning(warning: str, *, method: str) -> str:
    details = warning.split(":", 1)[1] if ":" in warning else warning
    token = details.split(":", 1)[0]
    path = Path(token)
    candidates = [token, path.parent.name]
    suffix = f".{method}"
    for candidate in candidates:
        if candidate.endswith(suffix):
            return candidate
    return token


def rerun_factor_artifact_hint(label: str, *, method: str) -> str:
    suffix = f".{method}"
    artifact_key = label.removesuffix(suffix) if label.endswith(suffix) else label
    if artifact_key.endswith(".intraday"):
        pick_date = artifact_key.removesuffix(".intraday")
    else:
        pick_date = artifact_key
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pick_date):
        return f"stock-select-rs screen --method {method} --pick-date {pick_date} --export-factors"
    return f"stock-select-rs screen --method {method} --pick-date <date> --export-factors"


def fatal_factor_warning_message(warnings: Sequence[str], *, method: str, limit: int = 10) -> str | None:
    fatal = [warning for warning in warnings if warning.startswith(FATAL_FACTOR_WARNING_PREFIXES)]
    if not fatal:
        return None
    labels = [factor_artifact_label_from_warning(warning, method=method) for warning in fatal]
    unique_labels = list(dict.fromkeys(labels))
    shown_labels = unique_labels[:limit]
    hints = list(dict.fromkeys(rerun_factor_artifact_hint(label, method=method) for label in shown_labels))
    return (
        "fatal runtime factor artifact warnings: "
        f"{', '.join(fatal[:limit])}. Affected artifacts: {', '.join(shown_labels)}. "
        f"Rerun: {'; '.join(hints)}. "
        "Or rerun candidate backfill with factor export enabled."
    )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--dsn")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--start-date", required=True, type=validate_date)
    parser.add_argument("--end-date", required=True, type=validate_date)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source", choices=["candidates", "select"], default="candidates")
    parser.add_argument("--min-history-days", type=int, default=120)
    parser.add_argument("--forward-days", type=int, default=15)
    parser.add_argument(
        "--external-feature-csv",
        type=Path,
        action="append",
        default=[],
        help="Optional local feature CSV(s), joined by date plus code/symbol/ts_code.",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build rank dataset for offline review ranking.")
    add_arguments(parser)
    return parser.parse_args(argv)


def main_from_args(args: argparse.Namespace) -> int:
    output_dir = resolve_output_dir(args.output_dir, method=args.method)
    runtime_root = resolve_runtime_root(args.runtime_root, env_runtime_root=os.getenv(RUNTIME_ROOT_ENV))
    if not runtime_root.exists():
        raise SystemExit(f"runtime root does not exist: {runtime_root}")
    dsn = resolve_dsn(args.dsn)
    if args.source == "select":
        training_input_rows, warnings = load_selection_rows(
            runtime_root, method=args.method, start_date=args.start_date, end_date=args.end_date
        )
    else:
        training_input_rows, warnings = load_candidate_rows(
            runtime_root, method=args.method, start_date=args.start_date, end_date=args.end_date
        )
    fatal_factor_message = fatal_factor_warning_message(warnings, method=args.method)
    if fatal_factor_message is not None:
        raise SystemExit(fatal_factor_message)
    symbols = sorted({str(row.get("code")) for row in training_input_rows if row.get("code")})
    query_start = (date.fromisoformat(args.start_date) - timedelta(days=args.min_history_days)).isoformat()
    query_end = (date.fromisoformat(args.end_date) + timedelta(days=args.forward_days)).isoformat()
    prices = fetch_price_rows(dsn, symbols, query_start, query_end)
    external_features, external_warnings = load_external_feature_rows(args.external_feature_csv, method=args.method)
    warnings.extend(external_warnings)
    rows = build_dataset_rows(
        training_input_rows,
        prices,
        method=args.method,
        external_features_by_key=external_features,
    )
    write_dataset(
        rows,
        output_dir,
        runtime_root=runtime_root,
        method=args.method,
        start_date=args.start_date,
        end_date=args.end_date,
        warnings=warnings,
        source=args.source,
    )
    print(f"wrote {len(rows)} rows to {output_dir / 'rank_dataset.csv'}")
    return 0


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("build", description="Build rank dataset for offline review ranking.")
    add_arguments(parser)
    parser.set_defaults(handler=main_from_args)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return main_from_args(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
