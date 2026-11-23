from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

from ml.dataset import schema as rank_dataset_schema

from .labels import as_float


DEFAULT_METHOD = "b2"

IDENTITY_COLUMNS = {"date", "code", "name", "method"}
LABEL_COLUMNS = {
    "exit_return", "exit_net_return", "rank_label_exit", "exit_date", "exit_reason",
    "exit_entry_date", "exit_holding_sessions", "exit_label_status",
    "ret3",
    "ret5",
    "ret10",
    "ret_t1_open_to_t3_close",
    "benchmark_csi300_ret_t1_open_to_t3_close",
    "excess_ret_t1_open_to_t3_close",
    "max_drawdown_5d",
    "win3_vs_day_median",
    "win5_vs_day_median",
    "rank_label_3d",
    "rank_label_5d",
}
NON_FEATURE_COLUMNS = {
    "model_score",
    "model_rank",
    "llm_action",
    "risk_flags",
}
SIGNAL_CATEGORICAL_COLUMNS = {"env", "signal", "signal_type"}
MACD_CATEGORICAL_COLUMNS = {
    "daily_macd_phase_type",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
}
CONTEXT_CATEGORICAL_COLUMNS = set(rank_dataset_schema.CZSC_TRAINING_CATEGORICAL_COLUMNS)
FEATURE_SETS = {"raw_numeric", "raw_plus_signal", "raw_plus_signal_macd", "all"}
RF_FEATURE_SELECTION_MODES = {"none", "cumulative_importance"}
CATEGORICAL_ENCODINGS = {"one_hot", "native"}
DEFAULT_CATEGORICAL_ENCODING = "one_hot"
OPTIONAL_ZERO_COVERAGE_RAW_COLUMNS = {
    "macd_state_phase_score",
    "macd_state_daily_phase_type",
    "macd_state_daily_wave_index",
    "macd_state_daily_wave_stage",
    "macd_state_weekly_phase_type",
    "macd_state_weekly_wave_index",
    "macd_state_weekly_wave_stage",
    "macd_state_weekly_daily_combo_type",
    "bar_upper_shadow_pct",
    "signal_bullish_engulf_prev_bearish_flag",
    "signal_bullish_engulf_volume_ratio",
    "signal_yang_engulf_ma25_flag",
    "cyq_winner_rate",
    "cyq_cost_50_to_close_pct",
    "cyq_cost_85_to_close_pct",
    "cyq_weight_avg_to_close_pct",
    "cyq_cost_70_width_pct",
    "cyq_cost_90_width_pct",
    # The replacement SW2021 industry source does not expose legacy THS
    # sector volume, turnover, market-cap, or leader-stock fields.  Keep the
    # schema aliases for compatibility, but remove them when their coverage
    # is empty so they cannot block training.
    "sw_l2_main_vol",
    "sw_l2_main_turnover_rate",
    "sw_l2_main_total_mv",
    "sw_l2_main_float_mv",
    "sw_l2_main_lead_stock_pct_change",
    "intraday_czsc_close_to_last_bi_high_pct",
    "intraday_czsc_close_to_last_bi_low_pct",
    "intraday_czsc_close_to_last_bi_mid_pct",
    "intraday_czsc_close_to_zs_zg_pct",
    "intraday_czsc_close_to_zs_zd_pct",
    "intraday_czsc_close_to_zs_zz_pct",
    "intraday_czsc_close_to_recent_peak_pct",
    "intraday_czsc_close_to_pricing_line_pct",
    "intraday_czsc_close_to_pricing_bear_high_pct",
    "intraday_czsc_close_to_pricing_bear_low_pct",
    "intraday_czsc_close_to_pricing_bear_close_pct",
}

# 周月结构可能长于 Rust 的一年行情窗口；日历天数仍可精确计算。
# 交易日计数超窗时保留缺失，仅在整个训练窗无值时剔除这些补充列。
OPTIONAL_ZERO_COVERAGE_RAW_COLUMNS |= {
    f"czsc_{period}_{field}"
    for period in ("weekly", "monthly")
    for field in (
        "last_bi_duration_trade_days", "zs_duration_trade_days",
        "recent_peak_age_trade_days", "pricing_line_age_trade_days",
    )
}


def categorical_columns_for_method(method: str = DEFAULT_METHOD) -> set[str]:
    return set(rank_dataset_schema.training_categorical_columns_for_method(method)) | {"env"}


def raw_numeric_columns_for_method(method: str = DEFAULT_METHOD) -> set[str]:
    return (
        set(rank_dataset_schema.raw_factor_columns_for_method(method))
        | set(rank_dataset_schema.context_numeric_columns_for_method(method))
        | set(rank_dataset_schema.training_macd_numeric_columns_for_method(method))
    )


def select_feature_columns(
    columns: Sequence[str],
    *,
    feature_set: str = "all",
    method: str = DEFAULT_METHOD,
) -> tuple[list[str], list[str]]:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unsupported feature_set: {feature_set}")
    numeric: list[str] = []
    categorical: list[str] = []
    raw_numeric_columns = raw_numeric_columns_for_method(method)
    method_categorical_columns = categorical_columns_for_method(method)
    if feature_set == "raw_numeric":
        allowed_categorical: set[str] = set()
    elif feature_set == "raw_plus_signal":
        allowed_categorical = SIGNAL_CATEGORICAL_COLUMNS & method_categorical_columns
    elif feature_set == "raw_plus_signal_macd":
        allowed_categorical = (
            SIGNAL_CATEGORICAL_COLUMNS | MACD_CATEGORICAL_COLUMNS | CONTEXT_CATEGORICAL_COLUMNS
        ) & method_categorical_columns
    else:
        allowed_categorical = method_categorical_columns
    excluded = IDENTITY_COLUMNS | LABEL_COLUMNS | NON_FEATURE_COLUMNS
    for column in columns:
        if column in excluded:
            continue
        if column in allowed_categorical:
            categorical.append(column)
        elif column in raw_numeric_columns or rank_dataset_schema.is_index_context_factor_column(column):
            numeric.append(column)
    return numeric, categorical


def feature_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, float) and math.isnan(value):
        return False
    return True


def drop_optional_zero_coverage_features(
    rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> tuple[list[str], list[str], list[str]]:
    selected = list(numeric_columns) + list(categorical_columns)
    dropped = [
        column
        for column in selected
        if (column in OPTIONAL_ZERO_COVERAGE_RAW_COLUMNS or column.startswith("cyq_"))
        and not any(feature_value_present(row.get(column)) for row in rows)
    ]
    dropped_set = set(dropped)
    return (
        [column for column in numeric_columns if column not in dropped_set],
        [column for column in categorical_columns if column not in dropped_set],
        dropped,
    )


def _verified_unavailable_index_context(rows: Sequence[dict[str, Any]], column: str) -> bool:
    """成员掩码或明确的无中枢状态允许缺失，源数据缺口仍失败。"""
    aliases = ("sse50", "csi300", "csi500", "guozheng2000", "chinext",
               "sci50", "bse50", "csi_a50", "csi_dividend")
    index_prefix = next((f"market_index_{alias}_" for alias in aliases
                         if column.startswith(f"market_index_{alias}_")), None)
    if index_prefix is None or column == index_prefix + "member_flag" or not rows:
        return False
    prefix = next((index_prefix + f"calc_daily_czsc_structure_{period}_"
                   for period in ("daily", "weekly", "monthly")
                   if column.startswith(index_prefix + f"calc_daily_czsc_structure_{period}_")), "")
    suffixes = {"bi_count", "duration_calendar_days", "end_age_calendar_days",
                "start_age_calendar_days", "zd_to_close_pct", "zg_to_close_pct", "zz_to_close_pct"}
    zs_field = bool(prefix) and column in {prefix + "latest_zs_" + suffix for suffix in suffixes}
    for row in rows:
        if column not in row:
            return False
        member = str(row.get(index_prefix + "member_flag"))
        if member in {"0", "0.0", "False"}:
            continue
        if (not zs_field or member not in {"1", "1.0", "True"}
                or str(row.get(prefix + "source_bar_valid")) not in {"1", "1.0", "True"}
                or str(row.get(prefix + "status_code")) not in {"1", "1.0", "2", "2.0", "3", "3.0"}):
            return False
    return True


def validate_selected_feature_coverage(
    rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> dict[str, Any]:
    selected = list(numeric_columns) + list(categorical_columns)
    features: dict[str, dict[str, int]] = {}
    zero_coverage: list[str] = []
    structural: list[str] = []
    row_count = len(rows)

    for column in selected:
        present_count = sum(1 for row in rows if column in row)
        non_empty_count = sum(1 for row in rows if feature_value_present(row.get(column)))
        features[column] = {
            "present_count": present_count,
            "non_empty_count": non_empty_count,
        }
        if non_empty_count == 0:
            if column in numeric_columns and _verified_unavailable_index_context(rows, column):
                structural.append(column)
            else:
                zero_coverage.append(column)

    report = {
        "row_count": row_count,
        "feature_count": len(selected),
        "features": features,
        "zero_coverage_features": zero_coverage,
        "structurally_unavailable_features": structural,
    }
    if zero_coverage:
        raise ValueError(f"selected training features have zero coverage: {', '.join(zero_coverage)}")
    return report


def base_feature_from_rf_feature(feature: str, categorical_columns: set[str]) -> str:
    if "=" in feature:
        prefix, _level = feature.split("=", 1)
        if prefix in categorical_columns:
            return prefix
    return feature


def select_features_by_rf_importance(
    diagnostics: dict[str, Any],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    threshold: float,
    min_selected_features: int,
) -> dict[str, Any]:
    if threshold <= 0.0 or threshold > 1.0:
        raise ValueError("RF cumulative importance threshold must be in (0, 1]")
    if min_selected_features < 1:
        raise ValueError("RF minimum selected feature count must be positive")

    numeric = list(numeric_columns)
    categorical = list(categorical_columns)
    candidate_features = numeric + categorical
    candidate_set = set(candidate_features)
    categorical_set = set(categorical)
    feature_importance: dict[str, float] = {feature: 0.0 for feature in candidate_features}
    ordered_base_features: list[str] = []

    importance_items = diagnostics.get("feature_importances") or diagnostics.get("top_features") or []
    for item in importance_items:
        if not isinstance(item, dict):
            continue
        feature = str(item.get("feature") or "")
        base_feature = base_feature_from_rf_feature(feature, categorical_set)
        if base_feature not in candidate_set:
            continue
        importance = as_float(item.get("importance")) or 0.0
        feature_importance[base_feature] = feature_importance.get(base_feature, 0.0) + max(0.0, importance)
        if base_feature not in ordered_base_features:
            ordered_base_features.append(base_feature)

    for feature in candidate_features:
        if feature not in ordered_base_features:
            ordered_base_features.append(feature)

    total_importance = sum(feature_importance.values())
    if total_importance <= 0.0:
        selected_features = candidate_features
        selected_importance_sum = 1.0 if candidate_features else 0.0
    else:
        ranked = sorted(
            ordered_base_features,
            key=lambda feature: (-feature_importance.get(feature, 0.0), candidate_features.index(feature)),
        )
        selected_features = []
        selected_raw_importance = 0.0
        min_count = min(min_selected_features, len(candidate_features))
        for feature in ranked:
            if feature in selected_features:
                continue
            selected_features.append(feature)
            selected_raw_importance += feature_importance.get(feature, 0.0)
            if selected_raw_importance / total_importance >= threshold and len(selected_features) >= min_count:
                break
        selected_importance_sum = selected_raw_importance / total_importance if total_importance else 0.0

    selected_set = set(selected_features)
    selected_numeric = [feature for feature in numeric if feature in selected_set]
    selected_categorical = [feature for feature in categorical if feature in selected_set]
    dropped_features = [feature for feature in candidate_features if feature not in selected_set]
    return {
        "mode": "cumulative_importance",
        "candidate_feature_count": len(candidate_features),
        "selected_feature_count": len(selected_numeric) + len(selected_categorical),
        "dropped_feature_count": len(dropped_features),
        "cumulative_importance_threshold": threshold,
        "min_selected_features": min_selected_features,
        "selected_importance_sum": round(selected_importance_sum, 8),
        "numeric_columns": selected_numeric,
        "categorical_columns": selected_categorical,
        "selected_features": selected_numeric + selected_categorical,
        "dropped_features": dropped_features,
        "feature_importance": {
            feature: round(feature_importance.get(feature, 0.0), 8) for feature in candidate_features
        },
    }


def load_feature_manifest_with_levels(
    path: Path,
    *,
    available_columns: set[str],
    method: str = DEFAULT_METHOD,
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature manifest must be a JSON object")
    excluded = set(payload.get("excluded_features") or []) | IDENTITY_COLUMNS | LABEL_COLUMNS | NON_FEATURE_COLUMNS
    raw_numeric_columns = raw_numeric_columns_for_method(method)
    categorical_columns = categorical_columns_for_method(method)

    def clean(values: Any, *, allowed_columns: set[str]) -> list[str]:
        if not isinstance(values, list):
            return []
        result = []
        for value in values:
            column = str(value)
            if (
                column in allowed_columns
                and column in available_columns
                and column not in excluded
                and column not in result
            ):
                result.append(column)
        return result

    numeric = clean(payload.get("numeric_features"), allowed_columns=raw_numeric_columns)
    categorical = clean(payload.get("categorical_features"), allowed_columns=categorical_columns)
    fixed_levels: dict[str, list[str]] = {}
    raw_levels = payload.get("categorical_levels")
    if isinstance(raw_levels, dict):
        for column in categorical:
            values = raw_levels.get(column)
            if not isinstance(values, list):
                continue
            cleaned_values = []
            for value in values:
                level = str(value)
                if level not in cleaned_values:
                    cleaned_values.append(level)
            if cleaned_values:
                fixed_levels[column] = cleaned_values
    return numeric, categorical, fixed_levels


def load_feature_manifest_encoding(path: Path) -> str:
    if not path.exists():
        return DEFAULT_CATEGORICAL_ENCODING
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature manifest must be a JSON object")
    categorical_encoding = str(payload.get("categorical_encoding") or DEFAULT_CATEGORICAL_ENCODING)
    if categorical_encoding not in CATEGORICAL_ENCODINGS:
        raise ValueError(f"unsupported categorical_encoding: {categorical_encoding}")
    return categorical_encoding


def load_feature_manifest(
    path: Path,
    *,
    available_columns: set[str],
    method: str = DEFAULT_METHOD,
) -> tuple[list[str], list[str]]:
    numeric, categorical, _fixed_levels = load_feature_manifest_with_levels(
        path,
        available_columns=available_columns,
        method=method,
    )
    return numeric, categorical
