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


IDENTITY_COLUMNS = ["date", "code", "name", "env", "method"]
REVIEW_COLUMNS = [
    "model_score",
    "model_rank",
    "llm_action",
    "risk_flags",
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


def factor_artifact_key_for_date(pick_date: str, *, intraday: bool = False) -> str:
    return f"{pick_date}.intraday" if intraday else pick_date


def load_factor_artifact_rows(runtime_root: Path, *, method: str, artifact_key: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    path = runtime_root / "factors" / f"{artifact_key}.{method}" / "factors.json"
    if not path.exists():
        return {}, [f"missing_factor_artifact:{artifact_key}.{method}"]
    payload = read_json(path)
    if payload is None:
        return {}, [f"invalid_factor_artifact:{path}"]
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


def merge_factor_artifact_values(row: dict[str, Any], factors: dict[str, Any]) -> None:
    for key, value in factors.items():
        if key in LABEL_COLUMNS or key not in DATASET_COLUMN_SET:
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
        }
    )
    for key, value in factors.items():
        if key in DATASET_COLUMN_SET:
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
    row = {column: "" for column in DATASET_COLUMNS}
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
            if key in DATASET_COLUMN_SET:
                row[key] = json_factor_value(value)
    for key, value in candidate.items():
        if key in DATASET_COLUMN_SET and format_csv_value(value) != "":
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
            merge_factor_artifact_values(row, factor_by_code.get(str(row.get("code") or ""), {}))
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


def build_dataset_rows(
    selection_rows: Sequence[dict[str, Any]],
    price_rows_by_symbol: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for selection_row in selection_rows:
        row = {column: "" for column in DATASET_COLUMNS}
        row.update({key: value for key, value in selection_row.items() if key in DATASET_COLUMN_SET})
        symbol_rows = price_rows_by_symbol.get(str(row.get("code")), [])
        for key, value in selection_row.items():
            if key in DATASET_COLUMN_SET and key not in LABEL_COLUMNS and format_csv_value(value) != "":
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
    parser.add_argument("--runtime-root", type=Path)
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
    missing_factor_artifacts = [warning for warning in warnings if warning.startswith("missing_factor_artifact:")]
    if missing_factor_artifacts:
        missing = ", ".join(item.removeprefix("missing_factor_artifact:") for item in missing_factor_artifacts[:10])
        raise SystemExit(
            "missing runtime factor artifacts: "
            f"{missing}. Run stock-select-rs screen --method {args.method} --pick-date <date> --export-factors "
            "for each missing EOD date, or rerun candidate backfill with factor export enabled."
        )
    symbols = sorted({str(row.get("code")) for row in training_input_rows if row.get("code")})
    query_start = (date.fromisoformat(args.start_date) - timedelta(days=args.min_history_days)).isoformat()
    query_end = (date.fromisoformat(args.end_date) + timedelta(days=args.forward_days)).isoformat()
    prices = fetch_price_rows(dsn, symbols, query_start, query_end)
    rows = build_dataset_rows(training_input_rows, prices)
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


if __name__ == "__main__":
    raise SystemExit(main())
