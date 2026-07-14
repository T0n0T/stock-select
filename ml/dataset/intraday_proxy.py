from __future__ import annotations

import csv
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .rank_dataset import IDENTITY_COLUMNS, LABEL_COLUMNS, REVIEW_METADATA_COLUMNS


INTRADAY_CZSC_PROXY_ALIASES = {
    "intraday_czsc_close_to_last_bi_high_pct": "czsc_close_to_last_bi_high_pct",
    "intraday_czsc_close_to_last_bi_low_pct": "czsc_close_to_last_bi_low_pct",
    "intraday_czsc_close_to_last_bi_mid_pct": "czsc_close_to_last_bi_mid_pct",
    "intraday_czsc_close_to_zs_zg_pct": "czsc_close_to_zs_zg_pct",
    "intraday_czsc_close_to_zs_zd_pct": "czsc_close_to_zs_zd_pct",
    "intraday_czsc_close_to_zs_zz_pct": "czsc_close_to_zs_zz_pct",
    "intraday_czsc_close_to_recent_peak_pct": "czsc_close_to_recent_peak_pct",
    "intraday_czsc_close_to_pricing_line_pct": "czsc_close_to_pricing_line_pct",
    "intraday_czsc_close_to_pricing_bear_high_pct": "czsc_close_to_pricing_bear_high_pct",
    "intraday_czsc_close_to_pricing_bear_low_pct": "czsc_close_to_pricing_bear_low_pct",
    "intraday_czsc_close_to_pricing_bear_close_pct": "czsc_close_to_pricing_bear_close_pct",
}

# Static capability contract derived from Tushare rt_k (OHLCVA), the previous-EOD
# stock-cache window, and the Rust intraday factor path. Runtime availability on a
# single date must never expand this list.
LIVE_RECOMPUTED_FROM_RT_K = [
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
    "macd_weekly_hist",
    "macd_monthly_hist",
    "structure_zxdkx",
    "boll_width_pct",
    "wr_qfq",
    "mtm_qfq",
    "roc_qfq",
    "psy_qfq",
    "bias1_qfq",
    "dist_to_up_limit_pct",
    "dist_to_down_limit_pct",
    "turnover_n",
    "market_up_ratio",
    "market_ge5_ratio",
    "market_le_minus5_ratio",
    "market_median_pct_chg",
    "market_amount_ma5_ratio",
    "market_approx_limit_up_count",
    "market_approx_limit_down_count",
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

# Available from the same live path, but excluded from the selected model after
# controlled comparison. Keeping them classified makes the audit exhaustive.
LIVE_RECOMPUTED_EXCLUDED_AFTER_VALIDATION = ["structure_zxdkx"]

PREVIOUS_EOD_SNAPSHOT = [
    "czsc_snapshot_available",
    "czsc_source_bar_valid",
    "czsc_available_finished_bi_count",
    "czsc_recent_bi_count",
    "czsc_bi_available",
    "czsc_status",
    "czsc_last_bi_direction",
    "czsc_last_bi_range_width_pct",
    "czsc_last_bi_move_pct",
    "czsc_last_bi_duration_trade_days",
    "czsc_zs_available",
    "czsc_zs_width_pct",
    "czsc_zs_bi_count",
    "czsc_zs_duration_trade_days",
    "czsc_recent_peak_available",
    "czsc_recent_peak_age_trade_days",
    "czsc_pricing_line_available",
    "czsc_pricing_line_missing_after_peak",
    "czsc_pricing_line_age_trade_days",
    "czsc_pricing_bear_body_pct",
    "czsc_pricing_bear_amplitude_pct",
]

LIVE_PRICE_AGAINST_PREVIOUS_STRUCTURE = list(INTRADAY_CZSC_PROXY_ALIASES)

UNAVAILABLE_INTRADAY = [
    "turnover_to_ma5_ratio",
    "turnover_rate_f",
    "dmi_adxr_qfq",
    "dmi_adx_qfq",
    "dmi_pdi_qfq",
    "dmi_mdi_qfq",
    "dmi_pdi_mdi_spread_qfq",
    "dmi_adx_adxr_gap_qfq",
    "trix_qfq",
    "obv_qfq",
    "stock_mf_net_amount",
    "stock_mf_net_d5_amount",
    "stock_mf_buy_lg_amount",
    "stock_mf_buy_lg_amount_rate",
    "stock_mf_buy_md_amount",
    "stock_mf_buy_md_amount_rate",
    "stock_mf_buy_sm_amount",
    "stock_mf_buy_sm_amount_rate",
    "large_net_amount_to_amount_pct",
    "mid_net_amount_to_amount_pct",
    "small_net_amount_to_amount_pct",
    "net_mf_amount_to_amount_pct",
    "macd_weekly_dea_pctile",
    "macd_monthly_dea_pctile",
    "macd_state_phase_score",
    "macd_state_daily_phase_type",
    "macd_state_daily_wave_index",
    "macd_state_daily_wave_stage",
    "macd_state_weekly_phase_type",
    "macd_state_weekly_wave_index",
    "macd_state_weekly_wave_stage",
    "macd_state_weekly_daily_combo_type",
    "macd_state_daily_rising_initial_flag",
    "macd_state_top_divergence_flag",
    "bar_upper_shadow_pct",
    "bar_lower_shadow_pct",
    "bar_amplitude_pct",
    "bar_body_pct",
    "signal_bullish_engulf_prev_bearish_flag",
    "signal_bullish_engulf_volume_ratio",
    "signal_yang_engulf_ma25_flag",
    "signal_prev_b2_flag",
    "signal_b3_plus_flag",
]

DUPLICATE_RUNTIME_ALIASES = [
    "macd_daily_dif_to_close_pct",
    "macd_daily_dea_to_close_pct",
    "macd_daily_hist_to_close_pct",
    "macd_daily_hist_delta_to_close_pct",
    "macd_daily_hist_slope_3d_to_close_pct",
    "macd_daily_hist_positive_flag",
    "volume_event_abnormal_days_ago",
    "volume_event_abnormal_to_ma20_ratio",
    "volume_event_body_pct",
    "volume_event_price_to_current_pct",
    "volume_event_post_drawdown_pct",
    "volume_event_redundant_position_pct",
    "bar_close_position_pct",
]

INTRADAY_FACTOR_GROUPS = {
    "live_recomputed_from_rt_k": LIVE_RECOMPUTED_FROM_RT_K,
    "live_recomputed_excluded_after_validation": LIVE_RECOMPUTED_EXCLUDED_AFTER_VALIDATION,
    "previous_eod_snapshot": PREVIOUS_EOD_SNAPSHOT,
    "live_price_against_previous_structure": LIVE_PRICE_AGAINST_PREVIOUS_STRUCTURE,
    "unavailable_intraday": UNAVAILABLE_INTRADAY,
    "duplicate_runtime_alias": DUPLICATE_RUNTIME_ALIASES,
    "constant_strategy_metadata": ["signal"],
}

_INTRADAY_FACTOR_CLASS = {
    column: group
    for group, columns in INTRADAY_FACTOR_GROUPS.items()
    for column in columns
}


def classify_intraday_factor(column: str) -> str | None:
    if column.startswith("ths_") or column.startswith("stock_vs_ths_"):
        return "previous_eod_snapshot"
    if column.startswith("stock_env_"):
        return "previous_eod_snapshot"
    if column.startswith("market_") and column not in LIVE_RECOMPUTED_FROM_RT_K:
        return "unavailable_intraday"
    if column.startswith("cyq_") or (
        column.startswith("structure_") and column not in _INTRADAY_FACTOR_CLASS
    ):
        return "unavailable_intraday"
    if column.startswith("czsc_") and column not in _INTRADAY_FACTOR_CLASS:
        return "unavailable_intraday"
    return _INTRADAY_FACTOR_CLASS.get(column)


def _value_present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or value.strip() != "")


def _ordered_unique(columns: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(columns))


def _round4(value: float | None) -> str:
    if value is None:
        return ""
    return f"{round(value, 4):.4f}".rstrip("0").rstrip(".")


def _pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0.0:
        return None
    return (current / base - 1.0) * 100.0


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _bool_csv(value: Any) -> str:
    if value is None:
        return ""
    return "1" if bool(value) else "0"


def _czsc_proxy_values(snapshot: Mapping[str, Any]) -> dict[str, str]:
    close = _number(snapshot.get("current_close_qfq"))
    bi_high = _number(snapshot.get("last_bi_high"))
    bi_low = _number(snapshot.get("last_bi_low"))
    bi_mid = _number(snapshot.get("last_bi_mid"))
    zs_zg = _number(snapshot.get("latest_zs_zg"))
    zs_zd = _number(snapshot.get("latest_zs_zd"))
    zs_zz = _number(snapshot.get("latest_zs_zz"))
    peak = _number(snapshot.get("recent_peak_high"))
    bear_open = _number(snapshot.get("post_peak_first_bear_open"))
    bear_high = _number(snapshot.get("post_peak_first_bear_high"))
    bear_low = _number(snapshot.get("post_peak_first_bear_low"))
    bear_close = _number(snapshot.get("post_peak_first_bear_close"))
    direction = str(snapshot.get("last_bi_direction") or "")
    bi_range = _pct_change(bi_high, bi_low)
    return {
        "czsc_snapshot_available": _bool_csv(snapshot.get("snapshot_available")),
        "czsc_source_bar_valid": _bool_csv(snapshot.get("source_bar_valid")),
        "czsc_status": str(snapshot.get("status") or "missing_snapshot"),
        "czsc_available_finished_bi_count": _round4(_number(snapshot.get("available_finished_bi_count"))),
        "czsc_recent_bi_count": _round4(_number(snapshot.get("recent_bi_count"))),
        "czsc_bi_available": _bool_csv(None not in (bi_high, bi_low, bi_mid)),
        "czsc_last_bi_direction": direction or "missing",
        "czsc_last_bi_range_width_pct": _round4(bi_range),
        "czsc_last_bi_move_pct": _round4(-bi_range if direction == "down" and bi_range is not None else bi_range),
        "czsc_zs_available": _bool_csv(None not in (zs_zg, zs_zd, zs_zz)),
        "czsc_zs_width_pct": _round4(_pct_change(zs_zg, zs_zd)),
        "czsc_zs_bi_count": _round4(_number(snapshot.get("latest_zs_bi_count"))),
        "czsc_zs_region": (
            "missing"
            if None in (close, zs_zg, zs_zd, zs_zz)
            else "above_zg"
            if close > zs_zg
            else "below_zd"
            if close < zs_zd
            else "inside_upper"
            if close >= zs_zz
            else "inside_lower"
        ),
        "czsc_recent_peak_available": _bool_csv(peak is not None and snapshot.get("recent_peak_date_present")),
        "czsc_pricing_line_available": _bool_csv(bear_open is not None and snapshot.get("post_peak_first_bear_date_present")),
        "czsc_pricing_line_missing_after_peak": _bool_csv(snapshot.get("post_peak_first_bear_missing")),
        "czsc_pricing_bear_body_pct": _round4(_pct_change(bear_close, bear_open)),
        "czsc_pricing_bear_amplitude_pct": _round4(_pct_change(bear_high, bear_low)),
        "intraday_czsc_close_to_last_bi_high_pct": _round4(_pct_change(close, bi_high)),
        "intraday_czsc_close_to_last_bi_low_pct": _round4(_pct_change(close, bi_low)),
        "intraday_czsc_close_to_last_bi_mid_pct": _round4(_pct_change(close, bi_mid)),
        "intraday_czsc_close_to_zs_zg_pct": _round4(_pct_change(close, zs_zg)),
        "intraday_czsc_close_to_zs_zd_pct": _round4(_pct_change(close, zs_zd)),
        "intraday_czsc_close_to_zs_zz_pct": _round4(_pct_change(close, zs_zz)),
        "intraday_czsc_close_to_recent_peak_pct": _round4(_pct_change(close, peak)),
        "intraday_czsc_close_to_pricing_line_pct": _round4(_pct_change(close, bear_open)),
        "intraday_czsc_close_to_pricing_bear_high_pct": _round4(_pct_change(close, bear_high)),
        "intraday_czsc_close_to_pricing_bear_low_pct": _round4(_pct_change(close, bear_low)),
        "intraday_czsc_close_to_pricing_bear_close_pct": _round4(_pct_change(close, bear_close)),
    }


def load_previous_eod_czsc_lookup(
    *,
    source_dataset: Path,
    dsn: str | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Load previous-trading-day CZSC anchors for each dataset (date, code)."""

    import psycopg

    with source_dataset.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    dates = sorted({str(row.get("date") or "") for row in rows if row.get("date")})
    if not dates:
        return {}
    resolved_dsn = dsn or os.getenv("POSTGRES_DSN")
    if not resolved_dsn:
        raise ValueError("POSTGRES_DSN is required to load previous-EOD CZSC anchors")
    sql = """
        WITH requested AS (
            SELECT * FROM unnest(%s::date[], %s::text[]) AS r(sample_date, ts_code)
        ),
        resolved AS (
            SELECT
                r.sample_date,
                r.ts_code,
                (
                    SELECT max(s.trade_date)
                    FROM stock_stk_factor_pro s
                    WHERE s.trade_date < r.sample_date
                ) AS previous_trade_date
            FROM requested r
        )
        SELECT
            r.sample_date,
            r.ts_code,
            current.close_qfq AS current_close_qfq,
            (c.ts_code IS NOT NULL) AS snapshot_available,
            c.source_bar_valid,
            c.status,
            c.available_finished_bi_count,
            c.recent_bi_count,
            c.last_bi_direction,
            c.last_bi_high,
            c.last_bi_low,
            c.last_bi_mid,
            c.latest_zs_zg,
            c.latest_zs_zd,
            c.latest_zs_zz,
            c.latest_zs_bi_count,
            c.recent_peak_high,
            (c.recent_peak_date IS NOT NULL) AS recent_peak_date_present,
            c.post_peak_first_bear_open,
            c.post_peak_first_bear_high,
            c.post_peak_first_bear_low,
            c.post_peak_first_bear_close,
            (c.post_peak_first_bear_date IS NOT NULL) AS post_peak_first_bear_date_present,
            c.post_peak_first_bear_missing
        FROM resolved r
        JOIN stock_stk_factor_pro current
          ON current.trade_date = r.sample_date
         AND current.ts_code = r.ts_code
        LEFT JOIN stock_daily_czsc_structure c
          ON c.trade_date = r.previous_trade_date
         AND c.ts_code = r.ts_code
         AND c.calc_version = 'czsc_structure_qfq_min6_r7_v1'
    """
    requested_dates = [str(row["date"]) for row in rows]
    requested_codes = [str(row["code"]) for row in rows]
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    with psycopg.connect(resolved_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (requested_dates, requested_codes))
            columns = [description.name for description in cursor.description or []]
            for values in cursor.fetchall():
                record = dict(zip(columns, values, strict=True))
                key = (str(record.pop("sample_date")), str(record.pop("ts_code")))
                lookup[key] = record
    return lookup


def write_static_feature_manifest(summary: Mapping[str, Any], path: Path) -> Path:
    categorical = {"czsc_status", "czsc_last_bi_direction", "czsc_zs_region"}
    features = [str(column) for column in summary.get("feature_columns") or []]
    payload = {
        "numeric_features": [column for column in features if column not in categorical],
        "categorical_features": [column for column in features if column in categorical],
        "categorical_levels": {},
        "categorical_encoding": "one_hot",
        "excluded_features": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_intraday_proxy_dataset(
    *,
    source_dataset: Path,
    output_dir: Path,
    previous_eod_czsc_lookup: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an EOD-labelled dataset restricted to factors available intraday."""

    with source_dataset.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        source_columns = list(reader.fieldnames or [])
        source_rows = list(reader)
    if not source_columns:
        raise ValueError(f"source dataset has no columns: {source_dataset}")

    non_empty_counts = {
        column: sum(_value_present(row.get(column)) for row in source_rows)
        for column in source_columns
    }
    metadata_columns = set(IDENTITY_COLUMNS) | set(REVIEW_METADATA_COLUMNS) | set(LABEL_COLUMNS)
    direct_feature_columns = {
        column
        for column in source_columns
        if classify_intraday_factor(column) == "live_recomputed_from_rt_k"
        and non_empty_counts[column] > 0
    }
    constant_strategy_metadata_columns = sorted(
        column
        for column in source_columns
        if classify_intraday_factor(column) == "constant_strategy_metadata"
    )
    derived_czsc_keys = set().union(
        *(_czsc_proxy_values(snapshot).keys() for snapshot in (previous_eod_czsc_lookup or {}).values())
    ) if previous_eod_czsc_lookup else set()
    previous_eod_czsc_columns = [
        column
        for column in PREVIOUS_EOD_SNAPSHOT
        if column in derived_czsc_keys
    ]
    proxy_aliases = {
        column: "previous_eod_stock_daily_czsc_structure"
        for column in LIVE_PRICE_AGAINST_PREVIOUS_STRUCTURE
        if previous_eod_czsc_lookup
    }

    output_columns: list[str] = []
    for column in source_columns:
        if (
            column in metadata_columns
            or column in direct_feature_columns
        ):
            output_columns.append(column)
    if previous_eod_czsc_lookup:
        output_columns.extend(previous_eod_czsc_columns)
        output_columns.extend(LIVE_PRICE_AGAINST_PREVIOUS_STRUCTURE)
    output_columns = _ordered_unique(output_columns)

    output_rows = []
    for source_row in source_rows:
        czsc_values = _czsc_proxy_values(
            (previous_eod_czsc_lookup or {}).get(
                (str(source_row.get("date") or ""), str(source_row.get("code") or "")),
                {},
            )
        )
        output_row = {}
        for column in output_columns:
            output_row[column] = czsc_values.get(column, source_row.get(column, ""))
        output_rows.append(output_row)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "rank_dataset.csv"
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_columns)
        writer.writeheader()
        writer.writerows(output_rows)

    non_feature_columns = (
        {"date", "code", "name", "method", "env"}
        | set(REVIEW_METADATA_COLUMNS)
        | set(LABEL_COLUMNS)
    )
    feature_columns = [column for column in output_columns if column not in non_feature_columns]
    summary = {
        "method": next(
            (str(row.get("method")) for row in source_rows if row.get("method")),
            "b2",
        ),
        "source": "eod_proxy",
        "source_dataset": str(source_dataset),
        "row_count": len(output_rows),
        "date_count": len({row.get("date") for row in output_rows if row.get("date")}),
        "symbol_count": len({row.get("code") for row in output_rows if row.get("code")}),
        "env_counts": dict(Counter(row.get("env") or "unknown" for row in output_rows)),
        "label_non_null_counts": {
            column: sum(_value_present(row.get(column)) for row in output_rows)
            for column in LABEL_COLUMNS
            if column in output_columns
        },
        "feature_columns": feature_columns,
        "feature_count": len(feature_columns),
        "direct_intraday_feature_columns": sorted(direct_feature_columns),
        "constant_strategy_metadata_columns": constant_strategy_metadata_columns,
        "previous_eod_czsc_columns": sorted(previous_eod_czsc_columns),
        "proxy_aliases": proxy_aliases,
        "previous_eod_czsc_lookup_covered_rows": sum(
            (str(row.get("date") or ""), str(row.get("code") or "")) in (previous_eod_czsc_lookup or {})
            for row in source_rows
        ),
        "factor_groups": {
            group: {
                "reason": {
                    "live_recomputed_from_rt_k": "由 rt_k 当日 OHLCVA 与截至上一交易日历史窗口重算",
                    "live_recomputed_excluded_after_validation": "盘中可重算，但受控验证后未进入最终模型",
                    "previous_eod_snapshot": "使用上一交易日 stock-cache 稳定快照",
                    "live_price_against_previous_structure": "用 rt_k 实时价对上一交易日结构锚点重算",
                    "unavailable_intraday": "盘中无当天数据源",
                    "duplicate_runtime_alias": "盘中存在，但与已保留实时因子完全同源同值",
                    "constant_strategy_metadata": "盘中可得，但对单一策略候选恒定，不进入模型",
                }[group],
                "source_columns": sorted(
                    column for column in source_columns if classify_intraday_factor(column) == group
                ),
                "selected_columns": sorted(
                    column for column in feature_columns if classify_intraday_factor(column) == group
                ),
            }
            for group in INTRADAY_FACTOR_GROUPS
        },
        "unclassified_source_columns": sorted(
            column
            for column in source_columns
            if column not in metadata_columns and classify_intraday_factor(column) is None
        ),
        "dropped_zero_coverage_columns": sorted(
            column
            for column in source_columns
            if classify_intraday_factor(column) == "live_recomputed_from_rt_k"
            and non_empty_counts[column] == 0
        ),
        "selection_policy": (
            "静态 rt_k 能力清单；当前 EOD proxy 仅保留公式同源的实时重算因子。"
            "上一日快照和实时价对结构因子仅在完成历史 as-of 重建时进入训练；"
            "策略 signal 虽盘中可得，但对 LSH 候选恒定，作为元数据剔除。"
        ),
        "capability_basis": {
            "rt_k_fields": [
                "ts_code",
                "name",
                "trade_date",
                "trade_time",
                "open",
                "high",
                "low",
                "close",
                "vol",
                "amount",
            ],
            "previous_eod_tables": [
                "stock_stk_factor_pro",
                "stock_daily_czsc_structure",
                "stock_daily_rolling_factors",
                "stock_period_indicator_state",
            ],
            "runtime_paths": [
                "src/intraday.rs::build_intraday_market_rows_with_macd_states",
                "src/screening.rs::prepare_rows",
                "src/factors/registry.rs::history_factor_fields_for_profile",
            ],
        },
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (output_dir / "rank_dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
