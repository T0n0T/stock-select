from __future__ import annotations

import json
import os
import pickle
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg
import typer

from stock_select.analysis import classify_daily_macd_wave, classify_weekly_macd_wave
from stock_select.reviewers import review_b2_symbol_history
from stock_select.strategies import (
    DEFAULT_B1_CONFIG,
    DRIBULL_MACD_TREND_DAYS,
    DRIBULL_RECENT_J_LOOKBACK,
    DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool,
    compute_b1_tightening_columns,
    compute_kdj,
    compute_macd,
    compute_turnover_n,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    prefilter_dribull_non_macd,
    run_b1_screen,
    run_b1_screen_with_stats,
    run_b2_screen_with_stats,
    run_dribull_screen_with_stats,
    validate_method,
)
from stock_select.strategies.b2 import _build_b2_signal_frame, _resolve_signal
from stock_select.strategies.hcr import (
    HCR_REQUIRED_TRADING_DAYS,
    prepare_hcr_frame,
    run_hcr_screen_with_stats,
)
from stock_select.charting import export_daily_chart
from stock_select.db_access import (
    fetch_available_trade_dates,
    fetch_daily_window,
    fetch_instrument_names,
    fetch_nth_latest_trade_date,
    fetch_previous_trade_date,
    fetch_symbol_history,
    load_dotenv_value,
    resolve_dsn,
)
from stock_select.html_export import write_summary_package
from stock_select.intraday import _normalize_ts_code, build_intraday_market_frame, normalize_rt_k_snapshot
from stock_select.review_orchestrator import (
    build_review_payload,
    build_review_result,
    merge_review_result,
    normalize_llm_review,
    summarize_reviews,
)
from stock_select.review_resolvers import get_review_resolver
from stock_select.watch_pool import (
    effective_watch_pool_symbols,
    load_watch_pool,
    merge_watch_rows,
    summary_to_watch_rows,
    trim_and_sort_watch_rows,
    update_watch_pool,
    write_watch_pool,
)


app = typer.Typer(help="stock-select standalone CLI")

DEFAULT_SCREEN_LOOKBACK_DAYS = 366
LLM_REVIEW_MAX_CONCURRENCY = 6
DRIBULL_PERIOD_MACD_WARMUP_START_DATE = "2023-01-01"
HCR_SCREEN_TRADING_DAYS = HCR_REQUIRED_TRADING_DAYS
RT_K_MARKET_WILDCARDS = ("*.SH", "*.SZ", "*.BJ")
SHARED_PREPARED_METHODS = frozenset({"b1", "b2", "dribull"})
B1_ARTIFACT_VERSION = 1


class IntradayUserError(ValueError):
    pass


class IntradayArtifactError(ValueError):
    pass


class ProgressReporter:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self.started_at = time.monotonic()

    def emit(self, stage: str, message: str) -> None:
        if not self.enabled:
            return
        typer.echo(f"[{stage}] {message}", err=True)

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def checkpoint(self) -> float:
        return time.monotonic()

    def since(self, checkpoint: float) -> float:
        return time.monotonic() - checkpoint


def main() -> None:
    app()


def _validate_cli_method(method: str) -> str:
    try:
        return validate_method(method)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _validate_review_method(method: str) -> str:
    normalized = method.strip().lower()
    if normalized in {"b1", "b2", "dribull", "hcr"}:
        return normalized
    supported = ", ".join(("b1", "b2", "dribull", "hcr"))
    raise typer.BadParameter(f"Supported methods: {supported}")


def _validate_pool_source(pool_source: str) -> str:
    normalized = pool_source.strip().lower()
    supported_sources = {"turnover-top", "record-watch", "custom"}
    if normalized not in supported_sources:
        supported = ", ".join(sorted(supported_sources))
        raise typer.BadParameter(f"Unsupported pool source '{pool_source}'. Supported pool sources: {supported}")
    return normalized


def _default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def _validate_cli_pick_date(pick_date: str) -> str:
    normalized = pick_date.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        raise typer.BadParameter("pick_date must be a valid date in YYYY-MM-DD format.")
    try:
        return pd.Timestamp(normalized).strftime("%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter("pick_date must be a valid date in YYYY-MM-DD format.") from exc


def _validate_analyze_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not re.fullmatch(r"\d{6}(?:\.(?:SZ|SH|BJ))?", normalized):
        raise typer.BadParameter(
            "symbol must be a canonical stock code: NNNNNN, NNNNNN.SZ, NNNNNN.SH, or NNNNNN.BJ."
        )
    return normalized


def _connect(dsn: str):
    return psycopg.connect(dsn)


def _resolve_cli_dsn(dsn: str | None) -> str:
    dotenv_dsn = load_dotenv_value(Path.cwd() / ".env", "POSTGRES_DSN")
    return resolve_dsn(dsn, os.getenv("POSTGRES_DSN"), dotenv_dsn)


def _load_candidate_payload(candidate_path: Path) -> dict:
    return json.loads(candidate_path.read_text(encoding="utf-8"))


def _candidate_payload_matches_screen_version(payload: dict[str, object], *, method: str) -> bool:
    if method != "b1":
        return True
    return payload.get("screen_version") == B1_ARTIFACT_VERSION


def _require_current_candidate_payload(
    candidate_path: Path,
    payload: dict[str, object],
    *,
    method: str,
) -> dict[str, object]:
    if _candidate_payload_matches_screen_version(payload, method=method):
        return payload
    raise typer.BadParameter(
        f"Stale b1 candidate file: {candidate_path}. Re-run `screen --method b1` to rebuild candidates."
    )


def _load_summary_payload(summary_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid summary json: {summary_path}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"Invalid summary json: {summary_path}")
    return payload


def _build_wave_task_context(history: pd.DataFrame, pick_date: str, *, method: str) -> dict[str, str]:
    wave_input = history[["trade_date", "close"]].copy()
    weekly_wave = classify_weekly_macd_wave(wave_input, pick_date)
    daily_wave = classify_daily_macd_wave(wave_input, pick_date)
    combo_ok = _is_review_wave_combo_ok(weekly_wave=weekly_wave, daily_wave=daily_wave)
    weekly_context = f"确定性识别结果：周线 {weekly_wave.label}；原因：{weekly_wave.reason}。"
    daily_context = f"确定性识别结果：日线 {daily_wave.label}；原因：{daily_wave.reason}。"
    if daily_wave.label == "wave4_end":
        third_wave_gain = float(daily_wave.details.get('third_wave_gain', 0.0)) * 100.0
        combo_context = (
            f"组合判定：{'符合' if combo_ok else '不符合'} {method.lower()} 候选要求；"
            f"日线三浪涨幅约 {third_wave_gain:.1f}%，需不超过 30%。"
        )
    else:
        combo_context = f"组合判定：{'符合' if combo_ok else '不符合'} {method.lower()} 候选要求。"
    return {
        "weekly_wave_context": weekly_context,
        "daily_wave_context": daily_context,
        "wave_combo_context": combo_context,
    }


def _is_review_wave_combo_ok(*, weekly_wave: object, daily_wave: object) -> bool:
    weekly_label = str(getattr(weekly_wave, "label", ""))
    daily_label = str(getattr(daily_wave, "label", ""))
    combo_ok = weekly_label in {"wave1", "wave3"} and daily_label in {"wave2_end", "wave4_end"}
    if not combo_ok:
        return False
    if daily_label != "wave4_end":
        return True
    details = getattr(daily_wave, "details", {}) or {}
    return float(details.get("third_wave_gain", 0.0)) <= 0.30


def _artifact_key(base_key: str, method: str) -> str:
    return f"{base_key}.{method}"


def _candidate_path(runtime_root: Path, base_key: str, method: str) -> Path:
    return runtime_root / "candidates" / f"{_artifact_key(base_key, method)}.json"


def _prepared_cache_path(runtime_root: Path, base_key: str, method: str) -> Path:
    if method in SHARED_PREPARED_METHODS:
        return runtime_root / "prepared" / f"{base_key}.pkl"
    return runtime_root / "prepared" / f"{_artifact_key(base_key, method)}.pkl"


def _chart_dir_path(runtime_root: Path, base_key: str, method: str) -> Path:
    return runtime_root / "charts" / _artifact_key(base_key, method)


def _review_dir_path(runtime_root: Path, base_key: str, method: str) -> Path:
    return runtime_root / "reviews" / _artifact_key(base_key, method)


def _watch_pool_path(runtime_root: Path, method: str) -> Path:
    _ = method
    return runtime_root / "watch_pool.csv"


def _default_custom_pool_path() -> Path:
    return _default_runtime_root() / "custom-pool.txt"


def _intraday_candidate_path(runtime_root: Path, run_id: str, method: str) -> Path:
    return _candidate_path(runtime_root, run_id, method)


def _today_local_date() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _recorded_at_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _candidate_payload_method(candidate_path: Path, payload: dict[str, object]) -> str | None:
    payload_method = payload.get("method")
    if isinstance(payload_method, str) and payload_method.strip():
        return payload_method.strip().lower()
    if "." in candidate_path.stem:
        return candidate_path.stem.rsplit(".", 1)[1].lower()
    return None


def _fallback_run_id(candidate_path: Path) -> str:
    if "." in candidate_path.stem:
        return candidate_path.stem.rsplit(".", 1)[0]
    return candidate_path.stem


def _validate_intraday_candidate_payload(candidate_path: Path, payload: dict[str, object]) -> dict[str, object]:
    run_id = payload.get("run_id")
    trade_date = payload.get("trade_date")
    candidates = payload.get("candidates")

    if not isinstance(run_id, str) or not run_id.strip():
        raise IntradayArtifactError(f"Malformed intraday candidate file: {candidate_path}")
    if not isinstance(trade_date, str) or not trade_date.strip():
        raise IntradayArtifactError(f"Malformed intraday candidate file: {candidate_path}")
    if not isinstance(candidates, list):
        raise IntradayArtifactError(f"Malformed intraday candidate file: {candidate_path}")
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("code"), str) or not candidate["code"].strip():
            raise IntradayArtifactError(f"Malformed intraday candidate file: {candidate_path}")
    return payload


def _resolve_latest_intraday_candidate(runtime_root: Path, method: str) -> tuple[Path, dict[str, object]]:
    candidate_dir = runtime_root / "candidates"
    latest_path: Path | None = None
    latest_payload: dict[str, object] | None = None
    latest_run_id: str | None = None
    stale_b1_candidate_path: Path | None = None

    for candidate_path in sorted(candidate_dir.glob("*.json")):
        try:
            payload = _load_candidate_payload(candidate_path)
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if payload.get("mode") != "intraday_snapshot":
            continue
        if _candidate_payload_method(candidate_path, payload) != method:
            continue
        if not _candidate_payload_matches_screen_version(payload, method=method):
            stale_b1_candidate_path = candidate_path
            continue
        payload_run_id = payload.get("run_id")
        run_id = payload_run_id.strip() if isinstance(payload_run_id, str) and payload_run_id.strip() else _fallback_run_id(candidate_path)
        if latest_run_id is None or run_id > latest_run_id:
            latest_path = candidate_path
            latest_payload = payload
            latest_run_id = run_id

    if latest_path is None or latest_payload is None:
        if stale_b1_candidate_path is not None:
            raise IntradayArtifactError(
                f"Stale intraday b1 candidate file: {stale_b1_candidate_path}. "
                "Re-run `screen --method b1 --intraday` to rebuild candidates."
            )
        raise typer.BadParameter("No intraday candidate file found.")
    return latest_path, _validate_intraday_candidate_payload(latest_path, latest_payload)


def _write_prepared_cache(
    cache_path: Path,
    *,
    method: str | None = None,
    pick_date: str,
    start_date: str,
    end_date: str,
    prepared_by_symbol: dict[str, pd.DataFrame],
    metadata_overrides: dict[str, object] | None = None,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "b1_config": DEFAULT_B1_CONFIG,
        "turnover_window": DEFAULT_TURNOVER_WINDOW,
        "weekly_ma_periods": DEFAULT_WEEKLY_MA_PERIODS,
        "max_vol_lookback": DEFAULT_MAX_VOL_LOOKBACK,
    }
    if method:
        metadata["method"] = method
    if method in SHARED_PREPARED_METHODS:
        metadata["screen_version"] = B1_ARTIFACT_VERSION
    if metadata_overrides:
        metadata.update(metadata_overrides)
    payload = {
        "pick_date": pick_date,
        "start_date": start_date,
        "end_date": end_date,
        "prepared_by_symbol": prepared_by_symbol,
        "metadata": metadata,
    }
    cache_path.write_bytes(pickle.dumps(payload))


def _load_prepared_cache(cache_path: Path) -> dict[str, object]:
    payload = pickle.loads(cache_path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Prepared cache payload must be a dict.")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Prepared cache metadata missing.")

    if metadata.get("b1_config") != DEFAULT_B1_CONFIG:
        raise ValueError("Prepared cache b1_config mismatch.")
    if metadata.get("turnover_window") != DEFAULT_TURNOVER_WINDOW:
        raise ValueError("Prepared cache turnover_window mismatch.")
    if tuple(metadata.get("weekly_ma_periods", ())) != DEFAULT_WEEKLY_MA_PERIODS:
        raise ValueError("Prepared cache weekly_ma_periods mismatch.")
    if metadata.get("max_vol_lookback") != DEFAULT_MAX_VOL_LOOKBACK:
        raise ValueError("Prepared cache max_vol_lookback mismatch.")

    prepared_by_symbol = payload.get("prepared_by_symbol")
    if not isinstance(prepared_by_symbol, dict):
        raise ValueError("Prepared cache prepared_by_symbol missing.")
    payload["prepared_by_symbol"] = prepared_by_symbol
    return payload


def _prepared_cache_matches_screen_version(payload: dict[str, object], *, method: str) -> bool:
    if method != "b1":
        return True
    metadata = payload.get("metadata")
    return isinstance(metadata, dict) and metadata.get("screen_version") == B1_ARTIFACT_VERSION


def _require_current_intraday_prepared_cache(
    cache_path: Path,
    payload: dict[str, object],
    *,
    method: str,
) -> None:
    if _prepared_cache_matches_screen_version(payload, method=method):
        return
    raise IntradayArtifactError(
        f"Stale intraday prepared cache: {cache_path}. Re-run `screen --method b1 --intraday --recompute`."
    )


def _load_intraday_prepared_cache(
    runtime_root: Path,
    *,
    method: str,
    run_id: str,
    trade_date: str,
) -> dict[str, pd.DataFrame]:
    cache_path = _prepared_cache_path(runtime_root, f"{trade_date}.intraday", method)
    payload = _load_prepared_cache(cache_path)
    _require_current_intraday_prepared_cache(cache_path, payload, method=method)
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise IntradayArtifactError("Prepared intraday cache metadata mismatch.")
    if metadata.get("mode") != "intraday_snapshot":
        raise IntradayArtifactError("Prepared intraday cache metadata mismatch.")
    cached_method = metadata.get("method")
    if isinstance(cached_method, str) and cached_method not in {method, *SHARED_PREPARED_METHODS}:
        raise IntradayArtifactError("Prepared intraday cache metadata mismatch.")
    if payload.get("pick_date") != trade_date:
        raise IntradayArtifactError("Prepared intraday cache metadata mismatch.")

    prepared = payload["prepared_by_symbol"]
    if not isinstance(prepared, dict):
        raise IntradayArtifactError("Prepared intraday payload missing prepared_by_symbol.")
    return prepared  # type: ignore[return-value]


def _resolve_tushare_token(cli_token: str | None) -> str:
    dotenv_token = load_dotenv_value(Path.cwd() / ".env", "TUSHARE_TOKEN")
    token = cli_token or os.getenv("TUSHARE_TOKEN") or dotenv_token
    if token:
        return token
    msg = "A Tushare token is required for intraday mode."
    raise IntradayUserError(msg)


def _current_shanghai_timestamp() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Shanghai")


def _is_within_intraday_market_hours(current: pd.Timestamp) -> bool:
    if current.day_of_week >= 5:
        return False
    current_time = current.timetz().replace(tzinfo=None)
    morning_open = datetime.strptime("09:30", "%H:%M").time()
    morning_close = datetime.strptime("11:30", "%H:%M").time()
    afternoon_open = datetime.strptime("13:00", "%H:%M").time()
    afternoon_close = datetime.strptime("15:00", "%H:%M").time()
    return (morning_open <= current_time <= morning_close) or (afternoon_open <= current_time <= afternoon_close)


def _emit_intraday_hours_warning(reporter: ProgressReporter | None) -> None:
    current = _current_shanghai_timestamp()
    if _is_within_intraday_market_hours(current):
        return
    message = (
        "--intraday requested outside trading-day intraday market hours; "
        "prefer --pick-date unless you explicitly need a stale or special intraday workflow."
    )
    if reporter is not None:
        reporter.emit("warning", message)
        return
    typer.echo(f"[warning] {message}", err=True)


def _format_intraday_run_id(timestamp: pd.Timestamp) -> str:
    return timestamp.isoformat(timespec="microseconds").replace(":", "-").replace(".", "-")


def _resolve_intraday_trade_date() -> str:
    current = _current_shanghai_timestamp()
    if current.day_of_week >= 5:
        msg = f"Intraday mode is unavailable on weekends ({current.strftime('%Y-%m-%d')})."
        raise IntradayUserError(msg)
    return current.strftime("%Y-%m-%d")


def _resolve_previous_trade_date(connection, trade_date: str) -> str:
    return fetch_previous_trade_date(connection, before_date=trade_date)


def _resolve_hcr_start_date(connection, *, end_date: str, trading_days: int) -> str:
    return fetch_nth_latest_trade_date(connection, end_date=end_date, n=trading_days)


def _resolve_record_watch_pool_codes(
    *,
    runtime_root: Path,
    method: str,
    pick_date: str,
    prepared_by_symbol: dict[str, pd.DataFrame],
) -> list[str]:
    csv_path = _watch_pool_path(runtime_root, method)
    if not csv_path.exists():
        raise typer.BadParameter(f"Missing watch pool CSV for pool_source=record-watch: {csv_path}")

    watch_rows = load_watch_pool(csv_path)
    effective_symbols = effective_watch_pool_symbols(watch_rows, screening_date=pick_date)
    pool_codes = [code for code in effective_symbols if code in prepared_by_symbol]
    if not pool_codes:
        raise typer.BadParameter(
            f"Effective watch pool is empty after applying screening date {pick_date} and prepared-data intersection."
    )
    return pool_codes


def _custom_pool_guidance_message(path: Path) -> str:
    return (
        f"Missing custom pool file: {path}. Define a custom pool with --pool-file PATH, "
        f"or set STOCK_SELECT_POOL_FILE, or create {_default_custom_pool_path()}."
    )


def _resolve_custom_pool_file(pool_file: Path | None) -> Path:
    if pool_file is not None:
        return pool_file.expanduser()
    env_value = os.getenv("STOCK_SELECT_POOL_FILE")
    if env_value and env_value.strip():
        return Path(env_value.strip()).expanduser()
    return _default_custom_pool_path()


def _load_custom_pool_codes(*, pool_file: Path | None) -> tuple[Path, list[str]]:
    resolved_path = _resolve_custom_pool_file(pool_file)
    if not resolved_path.exists():
        raise typer.BadParameter(_custom_pool_guidance_message(resolved_path))

    def normalize_candidate_token(token: str) -> str | None:
        stripped = token.strip()
        if not stripped:
            return None
        try:
            return _normalize_ts_code(stripped.upper())
        except ValueError:
            match = re.search(r"(\d{6})", stripped)
            if match is None:
                return None
            try:
                return _normalize_ts_code(match.group(1))
            except ValueError:
                return None

    raw_content = resolved_path.read_text(encoding="utf-8")
    raw_tokens = [token.strip() for token in raw_content.split() if token.strip()]
    codes: list[str] = []
    for token in raw_tokens:
        normalized = normalize_candidate_token(token)
        if normalized is None:
            continue
        if normalized not in codes:
            codes.append(normalized)

    if not codes:
        for line in raw_content.splitlines():
            normalized = normalize_candidate_token(line)
            if normalized is None or normalized in codes:
                continue
            codes.append(normalized)

    if not codes:
        raise typer.BadParameter(
            "Custom pool must contain at least one stock code. "
            "Provide codes separated by whitespace, for example: 603138 300058"
        )
    return resolved_path, codes


def _resolve_pool_codes(
    *,
    pool_source: str,
    runtime_root: Path,
    method: str,
    pick_date: str,
    prepared_by_symbol: dict[str, pd.DataFrame],
    pool_file: Path | None = None,
) -> list[str]:
    if pool_source == "record-watch":
        return _resolve_record_watch_pool_codes(
            runtime_root=runtime_root,
            method=method,
            pick_date=pick_date,
            prepared_by_symbol=prepared_by_symbol,
        )
    if pool_source == "custom":
        _resolved_path, custom_codes = _load_custom_pool_codes(pool_file=pool_file)
        pool_codes = [code for code in custom_codes if code in prepared_by_symbol]
        if not pool_codes:
            raise typer.BadParameter("Effective custom pool is empty after prepared-data intersection.")
        return pool_codes
    top_turnover_pool = build_top_turnover_pool(prepared_by_symbol, top_m=DEFAULT_TOP_M)
    return top_turnover_pool.get(pd.Timestamp(pick_date), [])


def _candidate_payload_matches_pool_source(
    payload: dict[str, object],
    *,
    pool_source: str,
    pool_file: Path | None = None,
) -> bool:
    payload_pool_source = payload.get("pool_source")
    if isinstance(payload_pool_source, str):
        if payload_pool_source.strip().lower() != pool_source:
            return False
        if pool_source == "custom":
            payload_pool_file = payload.get("pool_file")
            resolved_pool_file = str(_resolve_custom_pool_file(pool_file))
            return isinstance(payload_pool_file, str) and payload_pool_file == resolved_pool_file
        return True
    return pool_source == "turnover-top"


def _prepared_cache_matches_pool_source(
    payload: dict[str, object],
    *,
    pool_source: str,
    pool_file: Path | None = None,
) -> bool:
    # Prepared data is the raw indicator universe before pool selection.
    # It is reusable across pool sources as long as the date window and base config match.
    return True


def _validate_eod_pick_date_has_market_data(connection, *, market: pd.DataFrame, pick_date: str) -> None:
    if not market.empty:
        trade_dates = pd.to_datetime(market["trade_date"], errors="coerce")
        target_rows = market.loc[trade_dates == pd.Timestamp(pick_date)]
        if not target_rows.empty:
            price_columns = [column for column in ("open", "high", "low", "close") if column in target_rows.columns]
            volume_columns = [column for column in ("vol", "volume") if column in target_rows.columns]
            required_columns = price_columns + volume_columns
            if required_columns:
                usable_mask = target_rows[required_columns].notna().all(axis=1)
                if bool(usable_mask.any()):
                    return
                latest_trade_date = fetch_nth_latest_trade_date(connection, end_date=pick_date, n=1)
                raise typer.BadParameter(
                    f"Found incomplete end-of-day rows for pick_date {pick_date}. "
                    f"Latest complete trade date is {latest_trade_date}."
                )
            return
    latest_trade_date = fetch_nth_latest_trade_date(connection, end_date=pick_date, n=1)
    raise typer.BadParameter(
        f"No end-of-day data found for pick_date {pick_date}. Latest available trade date is {latest_trade_date}."
    )


def _validate_eod_pick_date_has_prepared_data(
    connection,
    *,
    prepared_by_symbol: dict[str, pd.DataFrame],
    pick_date: str,
) -> None:
    target_date = pd.Timestamp(pick_date)
    for frame in prepared_by_symbol.values():
        if frame.empty or "trade_date" not in frame.columns:
            continue
        trade_dates = pd.to_datetime(frame["trade_date"], errors="coerce")
        if bool((trade_dates == target_date).any()):
            return
    latest_trade_date = fetch_nth_latest_trade_date(connection, end_date=pick_date, n=1)
    raise typer.BadParameter(
        f"No end-of-day data found for pick_date {pick_date}. Latest available trade date is {latest_trade_date}."
    )


def _prepared_cache_covers_pick_date(prepared_by_symbol: dict[str, pd.DataFrame], *, pick_date: str) -> bool:
    target_date = pd.Timestamp(pick_date)
    for frame in prepared_by_symbol.values():
        if frame.empty or "trade_date" not in frame.columns:
            continue
        trade_dates = pd.to_datetime(frame["trade_date"], errors="coerce")
        if bool((trade_dates == target_date).any()):
            return True
    return False


def _import_tushare_module():
    try:
        import tushare as ts
    except ImportError as exc:  # pragma: no cover - wrapper behavior is tested via monkeypatch
        msg = "Tushare package is required for intraday mode."
        raise IntradayUserError(msg) from exc
    return ts


def _fetch_rt_k_snapshot(tushare_token: str, trade_date: str) -> pd.DataFrame:
    try:
        ts = _import_tushare_module()
    except ImportError as exc:
        msg = "Tushare package is required for intraday mode."
        raise IntradayUserError(msg) from exc

    ts.set_token(tushare_token)
    pro = ts.pro_api()
    try:
        snapshots: list[pd.DataFrame] = []
        for ts_code in RT_K_MARKET_WILDCARDS:
            market_snapshot = pro.rt_k(ts_code=ts_code)
            if market_snapshot is not None and not market_snapshot.empty:
                snapshots.append(market_snapshot)
    except Exception as exc:
        msg = f"Failed to fetch Tushare rt_k snapshot: {exc}"
        raise IntradayUserError(msg) from exc
    if not snapshots:
        msg = "Tushare rt_k returned no usable rows."
        raise IntradayUserError(msg)
    raw_snapshot = pd.concat(snapshots, ignore_index=True)
    fallback_trade_time = _current_shanghai_timestamp().strftime("%H:%M:%S")
    return normalize_rt_k_snapshot(
        raw_snapshot,
        trade_date=trade_date,
        fallback_trade_time=fallback_trade_time,
    )

def _prepare_screen_data(
    market: pd.DataFrame,
    *,
    reporter: ProgressReporter | None = None,
    progress_every: int = 500,
) -> dict[str, pd.DataFrame]:
    if market.empty:
        return {}

    prepared: dict[str, pd.DataFrame] = {}
    frame = market.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    if "volume" not in frame.columns and "vol" in frame.columns:
        frame["volume"] = frame["vol"]

    groups = list(frame.groupby("ts_code"))
    total = len(groups)
    if reporter:
        reporter.emit("screen", f"preparing symbols={total}")

    for idx, (code, group) in enumerate(groups, start=1):
        group = group.sort_values("trade_date").reset_index(drop=True)
        group["turnover_n"] = compute_turnover_n(group, window=DEFAULT_TURNOVER_WINDOW)
        kdj = compute_kdj(group)
        group["J"] = kdj["J"]
        group["ma25"] = group["close"].astype(float).rolling(window=25, min_periods=25).mean()
        group["ma60"] = group["close"].astype(float).rolling(window=60, min_periods=60).mean()
        group["ma144"] = group["close"].astype(float).rolling(window=144, min_periods=144).mean()
        zxdq, zxdkx = compute_zx_lines(group)
        group["zxdq"] = zxdq
        group["zxdkx"] = zxdkx
        macd = compute_macd(group)
        group["dif"] = macd["dif"]
        group["dea"] = macd["dea"]
        group["macd_hist"] = macd["macd_hist"]
        weekly_macd = _compute_period_macd_alignment(group, period="W")
        group["dif_w"] = weekly_macd["dif"]
        group["dea_w"] = weekly_macd["dea"]
        monthly_macd = _compute_period_macd_alignment(group, period="ME")
        group["dif_m"] = monthly_macd["dif"]
        group["dea_m"] = monthly_macd["dea"]
        group["weekly_ma_bull"] = compute_weekly_ma_bull(group, ma_periods=DEFAULT_WEEKLY_MA_PERIODS)
        group["max_vol_not_bearish"] = max_vol_not_bearish(group, lookback=DEFAULT_MAX_VOL_LOOKBACK)
        tightening = compute_b1_tightening_columns(group)
        group[list(tightening.columns)] = tightening
        prepared[code] = group
        if reporter and (idx == 1 or idx == total or idx % progress_every == 0):
            reporter.emit(
                "screen",
                f"prepare {idx}/{total} symbol={code} elapsed={reporter.elapsed_seconds():.1f}s",
            )
    return prepared


def _compute_period_macd_alignment(group: pd.DataFrame, *, period: str) -> pd.DataFrame:
    daily = group.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    close = daily.set_index("trade_date")["close"].astype(float)
    sampled_close = _sample_close_by_period(close, period=period)
    sampled_close = sampled_close.dropna()
    sampled_frame = pd.DataFrame({"close": sampled_close.to_numpy()}, index=sampled_close.index)
    period_macd = compute_macd(sampled_frame)
    aligned = period_macd.reindex(close.index, method="ffill")
    return pd.DataFrame(
        {
            "dif": aligned["dif"].to_numpy(),
            "dea": aligned["dea"].to_numpy(),
        },
        index=group.index,
    )


def _sample_close_by_period(close: pd.Series, *, period: str) -> pd.Series:
    idx = close.index
    if period == "W":
        period_key = idx.isocalendar().year.astype(str) + "-" + idx.isocalendar().week.astype(str).str.zfill(2)
    elif period == "ME":
        period_key = idx.year.astype(str) + "-" + idx.month.astype(str).str.zfill(2)
    else:
        msg = f"Unsupported period alignment: {period}"
        raise ValueError(msg)

    grouped = pd.DataFrame({"trade_date": idx, "close": close.to_numpy(), "period_key": period_key}).groupby(
        "period_key",
        sort=False,
        observed=True,
    )
    sampled = grouped.agg(trade_date=("trade_date", "last"), close=("close", "last"))
    return pd.Series(sampled["close"].to_numpy(), index=pd.DatetimeIndex(sampled["trade_date"].to_numpy()))


def _prepared_cache_mismatch_reason(
    *,
    cached_pick_date: object,
    expected_pick_date: str,
    cached_start_date: object,
    expected_start_date: str | None,
    cached_end_date: object,
    expected_end_date: str,
) -> str | None:
    reasons: list[str] = []
    if cached_pick_date != expected_pick_date:
        reasons.append("stale_pick_date")
    if cached_start_date != expected_start_date:
        reasons.append("stale_start_date")
    if cached_end_date != expected_end_date:
        reasons.append("stale_end_date")
    if not reasons:
        return None
    return ",".join(reasons)


def _prepare_chart_data(history: pd.DataFrame) -> pd.DataFrame:
    frame = history.copy()
    if frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    date_column = "trade_date" if "trade_date" in frame.columns else "date"
    volume_column = "vol" if "vol" in frame.columns else "volume"
    frame[date_column] = pd.to_datetime(frame[date_column])
    return pd.DataFrame(
        {
            "date": frame[date_column],
            "open": frame["open"].astype(float),
            "high": frame["high"].astype(float),
            "low": frame["low"].astype(float),
            "close": frame["close"].astype(float),
            "volume": frame[volume_column].astype(float),
        }
    )


def _call_prepare_screen_data(
    market: pd.DataFrame,
    *,
    reporter: ProgressReporter | None = None,
) -> dict[str, pd.DataFrame]:
    try:
        return _prepare_screen_data(market, reporter=reporter)
    except TypeError as exc:
        if "unexpected keyword argument 'reporter'" not in str(exc):
            raise
        return _prepare_screen_data(market)


def _prepare_dribull_screen_data_for_pick(
    connection,
    *,
    pick_date: str,
    pool_source: str,
    pool_file: Path | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    short_start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    if reporter:
        reporter.emit("screen", f"fetch market window end_date={pick_date} mode=pool start_date={short_start_date}")
    short_market = fetch_daily_window(
        connection,
        start_date=short_start_date,
        end_date=pick_date,
        symbols=None,
    )
    if reporter:
        reporter.emit(
            "screen",
            f"fetched pool rows={len(short_market)} symbols={short_market['ts_code'].nunique() if not short_market.empty else 0}",
        )
    _validate_eod_pick_date_has_market_data(connection, market=short_market, pick_date=pick_date)
    short_prepared = _call_prepare_screen_data(short_market, reporter=reporter)
    pool_codes = _resolve_pool_codes(
        pool_source=pool_source,
        runtime_root=runtime_root,
        method="dribull",
        pick_date=pick_date,
        prepared_by_symbol=short_prepared,
        pool_file=pool_file,
    )
    pooled_prepared = {code: short_prepared[code] for code in pool_codes if code in short_prepared}
    if not pooled_prepared:
        return short_prepared, {}
    filtered_codes = prefilter_dribull_non_macd(
        pooled_prepared,
        pd.Timestamp(pick_date),
        DEFAULT_B1_CONFIG,
    )
    if not filtered_codes:
        return short_prepared, {}
    if reporter:
        reporter.emit(
            "screen",
            f"fetch market window end_date={pick_date} mode=macd_warmup start_date={DRIBULL_PERIOD_MACD_WARMUP_START_DATE} symbols={len(filtered_codes)}",
        )
    warm_market = fetch_daily_window(
        connection,
        start_date=DRIBULL_PERIOD_MACD_WARMUP_START_DATE,
        end_date=pick_date,
        symbols=filtered_codes,
    )
    if reporter:
        reporter.emit(
            "screen",
            f"fetched warmup rows={len(warm_market)} symbols={warm_market['ts_code'].nunique() if not warm_market.empty else 0}",
    )
    return short_prepared, _call_prepare_screen_data(warm_market, reporter=reporter)


def _prepare_dribull_warmup_from_base_prepared(
    connection,
    *,
    pick_date: str,
    pool_source: str,
    pool_file: Path | None,
    runtime_root: Path,
    base_prepared: dict[str, pd.DataFrame],
    reporter: ProgressReporter | None = None,
) -> dict[str, pd.DataFrame]:
    pool_codes = _resolve_pool_codes(
        pool_source=pool_source,
        runtime_root=runtime_root,
        method="dribull",
        pick_date=pick_date,
        prepared_by_symbol=base_prepared,
        pool_file=pool_file,
    )
    pooled_prepared = {code: base_prepared[code] for code in pool_codes if code in base_prepared}
    if not pooled_prepared:
        return {}

    filtered_codes = prefilter_dribull_non_macd(
        pooled_prepared,
        pd.Timestamp(pick_date),
        DEFAULT_B1_CONFIG,
    )
    if not filtered_codes:
        return {}

    if reporter:
        reporter.emit(
            "screen",
            f"fetch market window end_date={pick_date} mode=macd_warmup start_date={DRIBULL_PERIOD_MACD_WARMUP_START_DATE} symbols={len(filtered_codes)}",
        )
    warm_market = fetch_daily_window(
        connection,
        start_date=DRIBULL_PERIOD_MACD_WARMUP_START_DATE,
        end_date=pick_date,
        symbols=filtered_codes,
    )
    if reporter:
        reporter.emit(
            "screen",
            f"fetched warmup rows={len(warm_market)} symbols={warm_market['ts_code'].nunique() if not warm_market.empty else 0}",
        )
    return _call_prepare_screen_data(warm_market, reporter=reporter)


def _resolve_shared_base_prepared_payload(
    runtime_root: Path,
    *,
    method: str,
    pick_date: str,
    intraday: bool,
) -> tuple[Path, dict[str, object] | None]:
    if intraday:
        base_key = f"{pick_date}.intraday"
    else:
        base_key = pick_date
    cache_method = "b1" if method in SHARED_PREPARED_METHODS else method
    cache_path = _prepared_cache_path(runtime_root, base_key, cache_method)
    if not cache_path.exists():
        return cache_path, None
    try:
        payload = _load_prepared_cache(cache_path)
    except (OSError, ValueError, pickle.PickleError):
        return cache_path, None
    if not _prepared_cache_matches_screen_version(payload, method=method):
        return cache_path, None
    return cache_path, payload


def _prepare_hcr_screen_data(
    market: pd.DataFrame,
    *,
    reporter: ProgressReporter | None = None,
    progress_every: int = 500,
) -> dict[str, pd.DataFrame]:
    if market.empty:
        return {}

    prepared: dict[str, pd.DataFrame] = {}
    frame = market.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    if "volume" not in frame.columns and "vol" in frame.columns:
        frame["volume"] = frame["vol"]

    groups = list(frame.groupby("ts_code"))
    total = len(groups)
    if reporter:
        reporter.emit("screen", f"preparing symbols={total}")

    for idx, (code, group) in enumerate(groups, start=1):
        group = group.sort_values("trade_date").reset_index(drop=True)
        group["turnover_n"] = compute_turnover_n(group, window=DEFAULT_TURNOVER_WINDOW)
        prepared[code] = prepare_hcr_frame(group)
        if reporter and (idx == 1 or idx == total or idx % progress_every == 0):
            reporter.emit(
                "screen",
                f"prepare {idx}/{total} symbol={code} elapsed={reporter.elapsed_seconds():.1f}s",
            )
    return prepared


def _call_prepare_hcr_screen_data(
    market: pd.DataFrame,
    *,
    reporter: ProgressReporter | None = None,
) -> dict[str, pd.DataFrame]:
    try:
        return _prepare_hcr_screen_data(market, reporter=reporter)
    except TypeError as exc:
        if "unexpected keyword argument 'reporter'" not in str(exc):
            raise
        return _prepare_hcr_screen_data(market)


def _emit_screen_breakdown(method: str, stats: dict[str, int], reporter: ProgressReporter | None) -> None:
    if not reporter:
        return
    if method == "b1":
        reporter.emit(
            "screen",
            "breakdown "
            f"total_symbols={stats['total_symbols']} "
            f"eligible={stats['eligible']} "
            f"fail_j={stats['fail_j']} "
            f"fail_insufficient_history={stats['fail_insufficient_history']} "
            f"fail_close_zxdkx={stats['fail_close_zxdkx']} "
            f"fail_zxdq_zxdkx={stats['fail_zxdq_zxdkx']} "
            f"fail_weekly_ma={stats['fail_weekly_ma']} "
            f"fail_max_vol={stats['fail_max_vol']} "
            f"fail_chg_cap={stats['fail_chg_cap']} "
            f"fail_v_shrink={stats['fail_v_shrink']} "
            f"fail_safe_mode={stats['fail_safe_mode']} "
            f"fail_lt_filter={stats['fail_lt_filter']} "
            f"selected={stats['selected']}",
        )
        return
    if method == "dribull":
        reporter.emit(
            "screen",
            "breakdown "
            f"total_symbols={stats['total_symbols']} "
            f"eligible={stats['eligible']} "
            f"fail_recent_j={stats['fail_recent_j']} "
            f"fail_insufficient_history={stats['fail_insufficient_history']} "
            f"fail_support_ma25={stats['fail_support_ma25']} "
            f"fail_volume_shrink={stats['fail_volume_shrink']} "
            f"fail_zxdq_zxdkx={stats['fail_zxdq_zxdkx']} "
            f"fail_ma60_trend={stats['fail_ma60_trend']} "
            f"fail_ma144_distance={stats['fail_ma144_distance']} "
            f"fail_weekly_wave={stats['fail_weekly_wave']} "
            f"fail_daily_wave={stats['fail_daily_wave']} "
            f"fail_wave_combo={stats['fail_wave_combo']} "
            f"selected={stats['selected']}",
        )
        return
    if method == "b2":
        reporter.emit(
            "screen",
            "breakdown "
            f"total_symbols={stats['total_symbols']} "
            f"eligible={stats['eligible']} "
            f"fail_insufficient_history={stats['fail_insufficient_history']} "
            f"fail_pre_ok={stats['fail_pre_ok']} "
            f"fail_pct={stats['fail_pct']} "
            f"fail_volume={stats['fail_volume']} "
            f"fail_k_shape={stats['fail_k_shape']} "
            f"fail_j_up={stats['fail_j_up']} "
            f"fail_tr_ok={stats['fail_tr_ok']} "
            f"fail_above_lt={stats['fail_above_lt']} "
            f"fail_duplicate_b2={stats['fail_duplicate_b2']} "
            f"fail_no_signal={stats['fail_no_signal']} "
            f"selected={stats['selected']} "
            f"selected_b2={stats['selected_b2']} "
            f"selected_b3={stats['selected_b3']} "
            f"selected_b3_plus={stats['selected_b3_plus']} "
            f"selected_b4={stats['selected_b4']} "
            f"selected_b5={stats['selected_b5']}",
        )
        return
    reporter.emit(
        "screen",
        "breakdown "
        f"total_symbols={stats['total_symbols']} "
        f"eligible={stats['eligible']} "
        f"fail_insufficient_history={stats['fail_insufficient_history']} "
        f"fail_resonance={stats['fail_resonance']} "
        f"fail_close_floor={stats['fail_close_floor']} "
        f"fail_breakout={stats['fail_breakout']} "
        f"selected={stats['selected']}",
    )

def _screen_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    pool_source: str,
    pool_file: Path | None,
    recompute: bool = False,
    reporter: ProgressReporter | None = None,
) -> Path:
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    out_path = _candidate_path(runtime_root, pick_date, method)
    allow_reuse = not recompute
    if allow_reuse and out_path.exists():
        try:
            existing_payload = _load_candidate_payload(out_path)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            if reporter:
                reporter.emit("screen", f"candidate reuse skipped path={out_path} reason={type(exc).__name__}")
        else:
            if not _candidate_payload_matches_pool_source(existing_payload, pool_source=pool_source, pool_file=pool_file):
                if reporter:
                    reporter.emit("screen", f"candidate reuse skipped path={out_path} reason=pool_source_mismatch")
            elif not _candidate_payload_matches_screen_version(existing_payload, method=method):
                if reporter:
                    reporter.emit("screen", f"candidate reuse skipped path={out_path} reason=stale_screen_version")
            else:
                existing_candidates = existing_payload.get("candidates", [])
                if isinstance(existing_candidates, list) and existing_candidates:
                    if reporter:
                        reporter.emit("screen", f"reuse candidates path={out_path}")
                    return out_path

    prepared_cache_path = _prepared_cache_path(runtime_root, pick_date, method)
    prepared: dict[str, pd.DataFrame] | None = None
    screen_prepared: dict[str, pd.DataFrame] | None = None
    reused_base_prepared = False
    if method in {"b1", "b2", "dribull"}:
        start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    else:
        start_date = None
    if allow_reuse and prepared_cache_path.exists():
        try:
            cache_payload = _load_prepared_cache(prepared_cache_path)
        except (OSError, ValueError, pickle.PickleError) as exc:
            if reporter:
                reporter.emit("screen", f"prepared reuse skipped path={prepared_cache_path} reason={type(exc).__name__}")
        else:
            if not _prepared_cache_matches_pool_source(cache_payload, pool_source=pool_source, pool_file=pool_file):
                if reporter:
                    reporter.emit("screen", f"prepared reuse skipped path={prepared_cache_path} reason=pool_source_mismatch")
            elif not _prepared_cache_matches_screen_version(cache_payload, method=method):
                if reporter:
                    reporter.emit("screen", f"prepared reuse skipped path={prepared_cache_path} reason=stale_screen_version")
            else:
                cached_pick_date = cache_payload.get("pick_date")
                cached_start_date = cache_payload.get("start_date")
                cached_end_date = cache_payload.get("end_date")
                if cached_pick_date == pick_date and cached_start_date == start_date and cached_end_date == pick_date:
                    cached_prepared = cache_payload["prepared_by_symbol"]  # type: ignore[assignment]
                    if _prepared_cache_covers_pick_date(cached_prepared, pick_date=pick_date):
                        prepared = cached_prepared
                        screen_prepared = cached_prepared
                        reused_base_prepared = True
                        if reporter:
                            reporter.emit("screen", f"reuse prepared path={prepared_cache_path}")
                    elif reporter:
                        reporter.emit("screen", f"prepared reuse skipped path={prepared_cache_path} reason=stale_pick_date")
                elif reporter:
                    mismatch_reason = _prepared_cache_mismatch_reason(
                        cached_pick_date=cached_pick_date,
                        expected_pick_date=pick_date,
                        cached_start_date=cached_start_date,
                        expected_start_date=start_date,
                        cached_end_date=cached_end_date,
                        expected_end_date=pick_date,
                    )
                    if mismatch_reason:
                        reporter.emit("screen", f"prepared reuse skipped path={prepared_cache_path} reason={mismatch_reason}")

    if prepared is None:
        resolved_dsn = _resolve_cli_dsn(dsn)
        if reporter:
            reporter.emit("screen", "connect db")
        connection = _connect(resolved_dsn)
        if method == "hcr":
            start_date = _resolve_hcr_start_date(
                connection,
                end_date=pick_date,
                trading_days=HCR_SCREEN_TRADING_DAYS,
            )
        elif method == "dribull":
            screen_prepared, prepared = _prepare_dribull_screen_data_for_pick(
                connection,
                pick_date=pick_date,
                pool_source=pool_source,
                pool_file=pool_file,
                runtime_root=runtime_root,
                reporter=reporter,
            )
            start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        elif start_date is None:
            start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        if prepared is None:
            if reporter:
                reporter.emit("screen", "fetch market window")
            market = fetch_daily_window(
                connection,
                start_date=start_date,
                end_date=pick_date,
                symbols=None,
            )
            if reporter:
                reporter.emit(
                    "screen",
                    f"fetched rows={len(market)} symbols={market['ts_code'].nunique() if not market.empty else 0}",
                )
            _validate_eod_pick_date_has_market_data(connection, market=market, pick_date=pick_date)
            if method in {"b1", "b2", "dribull"}:
                prepared = _call_prepare_screen_data(market, reporter=reporter)
                screen_prepared = prepared
            else:
                prepared = _call_prepare_hcr_screen_data(market, reporter=reporter)
        _write_prepared_cache(
            prepared_cache_path,
            method=method,
            pick_date=pick_date,
            start_date=start_date,
            end_date=pick_date,
            prepared_by_symbol=screen_prepared if screen_prepared is not None else prepared,
            metadata_overrides={
                "pool_source": pool_source,
                "pool_file": str(_resolve_custom_pool_file(pool_file)) if pool_source == "custom" else None,
            },
        )
        if reporter:
            reporter.emit("screen", f"write prepared path={prepared_cache_path}")
    elif method == "dribull" and reused_base_prepared:
        pool_codes = _resolve_pool_codes(
            pool_source=pool_source,
            runtime_root=runtime_root,
            method=method,
            pick_date=pick_date,
            prepared_by_symbol=prepared,
            pool_file=pool_file,
        )
        pooled_prepared = {code: prepared[code] for code in pool_codes if code in prepared}
        filtered_codes = prefilter_dribull_non_macd(
            pooled_prepared,
            pd.Timestamp(pick_date),
            DEFAULT_B1_CONFIG,
        )
        if filtered_codes:
            resolved_dsn = _resolve_cli_dsn(dsn)
            if reporter:
                reporter.emit("screen", "connect db")
            connection = _connect(resolved_dsn)
            prepared = _prepare_dribull_warmup_from_base_prepared(
                connection,
                pick_date=pick_date,
                pool_source=pool_source,
                pool_file=pool_file,
                runtime_root=runtime_root,
                base_prepared=screen_prepared if screen_prepared is not None else prepared,
                reporter=reporter,
            )
        else:
            prepared = {}
    if method in {"b1", "b2", "dribull"}:
        if prepared is None:
            prepared = {}
        if method == "dribull" and pool_source == "record-watch" and screen_prepared is not None:
            pool_codes = list(prepared)
        else:
            pool_codes = _resolve_pool_codes(
                pool_source=pool_source,
                runtime_root=runtime_root,
                method=method,
                pick_date=pick_date,
                prepared_by_symbol=prepared,
                pool_file=pool_file,
            )
        prepared_for_pick = {code: prepared[code] for code in pool_codes if code in prepared}
        if reporter:
            reporter.emit("screen", f"pool_source={pool_source} pool_size={len(prepared_for_pick)}")
            if pool_source == "record-watch":
                reporter.emit("screen", f"watch_pool_path={_watch_pool_path(runtime_root, method)}")
            reporter.emit("screen", f"run {method} screen")
        if method == "b1":
            candidates, stats = run_b1_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(pick_date),
                DEFAULT_B1_CONFIG,
            )
        elif method == "b2":
            candidates, stats = run_b2_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(pick_date),
            )
        else:
            candidates, stats = run_dribull_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(pick_date),
                DEFAULT_B1_CONFIG,
            )
    else:
        if prepared is None:
            prepared = {}
        pool_codes = _resolve_pool_codes(
            pool_source=pool_source,
            runtime_root=runtime_root,
                method=method,
                pick_date=pick_date,
                prepared_by_symbol=prepared,
                pool_file=pool_file,
            )
        prepared = {code: prepared[code] for code in pool_codes if code in prepared}
        if reporter:
            reporter.emit("screen", f"pool_source={pool_source} pool_size={len(prepared)}")
            if pool_source == "record-watch":
                reporter.emit("screen", f"watch_pool_path={_watch_pool_path(runtime_root, method)}")
            reporter.emit("screen", "run hcr screen")
        candidates, stats = run_hcr_screen_with_stats(prepared, pd.Timestamp(pick_date))
    payload = {"pick_date": pick_date, "method": method, "pool_source": pool_source, "candidates": candidates}
    if method == "b1":
        payload["screen_version"] = B1_ARTIFACT_VERSION
    if pool_source == "custom":
        payload["pool_file"] = str(_resolve_custom_pool_file(pool_file))
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _emit_screen_breakdown(method, stats, reporter)
    if reporter:
        reporter.emit("screen", f"selected candidates={len(candidates)} write={out_path}")
    return out_path


def _screen_intraday_impl(
    *,
    method: str,
    dsn: str | None,
    tushare_token: str | None,
    runtime_root: Path,
    pool_source: str,
    pool_file: Path | None,
    recompute: bool = False,
    reporter: ProgressReporter | None = None,
) -> Path:
    trade_date = _resolve_intraday_trade_date()
    run_id = _format_intraday_run_id(_current_shanghai_timestamp())
    prepared_cache_path, cache_payload = _resolve_shared_base_prepared_payload(
        runtime_root,
        method=method,
        pick_date=trade_date,
        intraday=True,
    )
    prepared: dict[str, pd.DataFrame]
    previous_trade_date: str
    if not recompute and cache_payload is not None:
        metadata = cache_payload.get("metadata")
        cached_prepared = cache_payload.get("prepared_by_symbol")
        if (
            isinstance(metadata, dict)
            and metadata.get("mode") == "intraday_snapshot"
            and cache_payload.get("pick_date") == trade_date
            and isinstance(cached_prepared, dict)
        ):
            prepared = cached_prepared  # type: ignore[assignment]
            previous_trade_date = str(metadata.get("previous_trade_date") or "")
            if reporter:
                reporter.emit("screen", f"reuse prepared path={prepared_cache_path}")
        else:
            cache_payload = None
    if recompute or cache_payload is None:
        resolved_token = _resolve_tushare_token(tushare_token)
        resolved_dsn = _resolve_cli_dsn(dsn)
        if reporter:
            reporter.emit("screen", "connect db")
        connection = _connect(resolved_dsn)
        previous_trade_date = _resolve_previous_trade_date(connection, trade_date)
        if reporter:
            reporter.emit("screen", f"fetch snapshot trade_date={trade_date}")
        snapshot = _fetch_rt_k_snapshot(resolved_token, trade_date)
        if method == "hcr":
            start_date = _resolve_hcr_start_date(
                connection,
                end_date=previous_trade_date,
                trading_days=HCR_SCREEN_TRADING_DAYS - 1,
            )
        else:
            start_date = (pd.Timestamp(previous_trade_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime(
                "%Y-%m-%d"
            )
        if reporter:
            reporter.emit("screen", f"fetch market window end_date={previous_trade_date}")
        market = fetch_daily_window(
            connection,
            start_date=start_date,
            end_date=previous_trade_date,
            symbols=None,
        )
        overlay_market = build_intraday_market_frame(market, snapshot, trade_date=trade_date)
        if method in {"b1", "b2", "dribull"}:
            prepared = _call_prepare_screen_data(overlay_market, reporter=reporter)
        else:
            prepared = _call_prepare_hcr_screen_data(overlay_market, reporter=reporter)
        _write_prepared_cache(
            prepared_cache_path,
            method=method,
            pick_date=trade_date,
            start_date=start_date,
            end_date=trade_date,
            prepared_by_symbol=prepared,
            metadata_overrides={
                "method": method,
                "mode": "intraday_snapshot",
                "source": "tushare_rt_k",
                "run_id": run_id,
                "previous_trade_date": previous_trade_date,
            },
        )
        if reporter:
            reporter.emit("screen", f"write prepared path={prepared_cache_path}")

    if method in {"b1", "b2", "dribull"}:
        pool_codes = _resolve_pool_codes(
            pool_source=pool_source,
            runtime_root=runtime_root,
            method=method,
            pick_date=trade_date,
            prepared_by_symbol=prepared,
            pool_file=pool_file,
        )
        prepared_for_pick = {code: prepared[code] for code in pool_codes if code in prepared}
        if reporter:
            reporter.emit("screen", f"pool_source={pool_source} pool_size={len(prepared_for_pick)}")
            if pool_source == "record-watch":
                reporter.emit("screen", f"watch_pool_path={_watch_pool_path(runtime_root, method)}")
            reporter.emit("screen", f"run {method} screen")
        if method == "b1":
            candidates, stats = run_b1_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(trade_date),
                DEFAULT_B1_CONFIG,
            )
        elif method == "b2":
            candidates, stats = run_b2_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(trade_date),
            )
        else:
            candidates, stats = run_dribull_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(trade_date),
                DEFAULT_B1_CONFIG,
            )
    else:
        pool_codes = _resolve_pool_codes(
            pool_source=pool_source,
            runtime_root=runtime_root,
            method=method,
            pick_date=trade_date,
            prepared_by_symbol=prepared,
            pool_file=pool_file,
        )
        prepared = {code: prepared[code] for code in pool_codes if code in prepared}
        if reporter:
            reporter.emit("screen", f"pool_source={pool_source} pool_size={len(prepared)}")
            if pool_source == "record-watch":
                reporter.emit("screen", f"watch_pool_path={_watch_pool_path(runtime_root, method)}")
            reporter.emit("screen", "run hcr screen")
        candidates, stats = run_hcr_screen_with_stats(prepared, pd.Timestamp(trade_date))
    out_path = _intraday_candidate_path(runtime_root, run_id, method)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": "intraday_snapshot",
        "method": method,
        "trade_date": trade_date,
        "fetched_at": run_id,
        "run_id": run_id,
        "source": "tushare_rt_k",
        "pool_source": pool_source,
        "candidates": candidates,
    }
    if method == "b1":
        payload["screen_version"] = B1_ARTIFACT_VERSION
    if pool_source == "custom":
        payload["pool_file"] = str(_resolve_custom_pool_file(pool_file))
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _emit_screen_breakdown(method, stats, reporter)
    if reporter:
        reporter.emit("screen", f"selected candidates={len(candidates)} write={out_path}")
    return out_path


def _chart_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    candidate_path = _candidate_path(runtime_root, pick_date, method)
    if not candidate_path.exists():
        raise typer.BadParameter(f"Candidate file not found: {candidate_path}")
    payload = _require_current_candidate_payload(
        candidate_path,
        _load_candidate_payload(candidate_path),
        method=method,
    )
    chart_dir = _chart_dir_path(runtime_root, pick_date, method)
    chart_dir.mkdir(parents=True, exist_ok=True)
    resolved_dsn = _resolve_cli_dsn(dsn)
    connection = _connect(resolved_dsn)
    start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d")
    candidates = payload.get("candidates", [])
    if reporter:
        reporter.emit("chart", f"candidates={len(candidates)}")

    for idx, candidate in enumerate(candidates, start=1):
        code = candidate["code"]
        if reporter:
            reporter.emit("chart", f"candidate {idx}/{len(candidates)} code={code}")
        out_path = chart_dir / f"{code}_day.png"
        history = fetch_symbol_history(
            connection,
            symbol=code,
            start_date=start_date,
            end_date=pick_date,
        )
        chart_data = _prepare_chart_data(history)
        if chart_data.empty:
            raise typer.BadParameter(f"No price history found for candidate: {code}")
        export_daily_chart(chart_data, code, out_path)
    if reporter:
        reporter.emit("chart", f"done write={chart_dir}")
    return chart_dir


def _chart_intraday_impl(
    *,
    method: str,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    try:
        _, payload = _resolve_latest_intraday_candidate(runtime_root, method)
    except IntradayArtifactError as exc:
        raise typer.BadParameter(str(exc)) from exc
    run_id = str(payload["run_id"])
    trade_date = str(payload["trade_date"])

    chart_dir = _chart_dir_path(runtime_root, run_id, method)
    chart_dir.mkdir(parents=True, exist_ok=True)
    try:
        prepared_by_symbol = _load_intraday_prepared_cache(
            runtime_root,
            method=method,
            run_id=run_id,
            trade_date=trade_date,
        )
    except IntradayArtifactError as exc:
        raise typer.BadParameter(str(exc)) from exc
    candidates = payload.get("candidates", [])
    if reporter:
        reporter.emit("chart", f"candidates={len(candidates)} intraday_run_id={run_id}")

    for idx, candidate in enumerate(candidates, start=1):
        code = candidate["code"]
        if reporter:
            reporter.emit("chart", f"candidate {idx}/{len(candidates)} code={code}")
        history = prepared_by_symbol.get(code)
        if history is None:
            raise typer.BadParameter(f"Prepared intraday history not found for candidate: {code}")
        chart_data = _prepare_chart_data(history)
        if chart_data.empty:
            raise typer.BadParameter(f"No prepared intraday history found for candidate: {code}")
        export_daily_chart(chart_data, code, chart_dir / f"{code}_day.png")

    if reporter:
        reporter.emit("chart", f"done write={chart_dir}")
    return chart_dir


def _review_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    resolver = get_review_resolver(method)
    chart_dir = _chart_dir_path(runtime_root, pick_date, method)
    if not chart_dir.exists():
        raise typer.BadParameter(f"Chart input directory not found: {chart_dir}")
    candidate_path = _candidate_path(runtime_root, pick_date, method)
    if not candidate_path.exists():
        raise typer.BadParameter(f"Candidate file not found: {candidate_path}")
    review_dir = _review_dir_path(runtime_root, pick_date, method)
    review_dir.mkdir(parents=True, exist_ok=True)
    payload = _require_current_candidate_payload(
        candidate_path,
        _load_candidate_payload(candidate_path),
        method=method,
    )
    resolved_dsn = _resolve_cli_dsn(dsn)
    connection = _connect(resolved_dsn)
    start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d")
    candidates = payload.get("candidates", [])
    if reporter:
        reporter.emit("review", f"candidates={len(candidates)}")

    reviews: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    llm_review_tasks: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates, start=1):
        code = candidate["code"]
        if reporter:
            reporter.emit("review", f"candidate {idx}/{len(candidates)} code={code}")
        chart_path = chart_dir / f"{code}_day.png"
        if not chart_path.exists():
            failures.append({"code": code, "reason": f"Chart file not found: {chart_path}"})
            if reporter:
                reporter.emit("review", f"skip code={code} reason=missing_chart")
            continue
        history = fetch_symbol_history(
            connection,
            symbol=code,
            start_date=start_date,
            end_date=pick_date,
        )
        baseline_review = resolver.review_history(
            code=code,
            pick_date=pick_date,
            history=history,
            chart_path=str(chart_path),
        )
        review = build_review_result(
            code=code,
            pick_date=pick_date,
            chart_path=str(chart_path),
            baseline_review=baseline_review,
        )
        (review_dir / f"{code}.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
        reviews.append(review)
        task = build_review_payload(
            code=code,
            pick_date=pick_date,
            chart_path=str(chart_path),
            rubric_path="references/review-rubric.md",
            prompt_path=resolver.prompt_path,
            extra_context=(
                _build_wave_task_context(history, pick_date, method=method)
                if method.lower() in {"b1", "b2", "dribull"}
                else None
            ),
        )
        llm_review_tasks.append(
            {
                **task,
                "rank": idx,
                "baseline_score": review["total_score"],
                "baseline_verdict": review["verdict"],
            }
        )

    summary = summarize_reviews(
        pick_date,
        method.lower(),
        reviews,
        min_score=4.0,
        failures=failures,
    )
    summary_path = review_dir / "summary.json"
    tasks_path = review_dir / "llm_review_tasks.json"
    tasks_payload = {
        "pick_date": pick_date,
        "method": method.lower(),
        "prompt_path": resolver.prompt_path,
        "max_concurrency": LLM_REVIEW_MAX_CONCURRENCY,
        "tasks": llm_review_tasks,
    }
    tasks_path.write_text(json.dumps(tasks_payload, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if reporter:
        reporter.emit("review", f"done reviewed={len(reviews)} failures={len(failures)} write={summary_path}")
    return summary_path


def _review_intraday_impl(
    *,
    method: str,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    resolver = get_review_resolver(method)
    try:
        _, payload = _resolve_latest_intraday_candidate(runtime_root, method)
    except IntradayArtifactError as exc:
        raise typer.BadParameter(str(exc)) from exc
    run_id = str(payload["run_id"])
    pick_date = str(payload["trade_date"])

    chart_dir = _chart_dir_path(runtime_root, run_id, method)
    if not chart_dir.exists():
        raise typer.BadParameter(f"Chart input directory not found: {chart_dir}")
    review_dir = _review_dir_path(runtime_root, run_id, method)
    review_dir.mkdir(parents=True, exist_ok=True)
    try:
        prepared_by_symbol = _load_intraday_prepared_cache(
            runtime_root,
            method=method,
            run_id=run_id,
            trade_date=pick_date,
        )
    except IntradayArtifactError as exc:
        raise typer.BadParameter(str(exc)) from exc
    candidates = payload.get("candidates", [])
    if reporter:
        reporter.emit("review", f"candidates={len(candidates)} intraday_run_id={run_id}")

    reviews: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    llm_review_tasks: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates, start=1):
        code = candidate["code"]
        if reporter:
            reporter.emit("review", f"candidate {idx}/{len(candidates)} code={code}")
        chart_path = chart_dir / f"{code}_day.png"
        if not chart_path.exists():
            failures.append({"code": code, "reason": f"Chart file not found: {chart_path}"})
            if reporter:
                reporter.emit("review", f"skip code={code} reason=missing_chart")
            continue

        history = prepared_by_symbol.get(code)
        if history is None or history.empty:
            failures.append({"code": code, "reason": f"Prepared intraday history not found: {code}"})
            if reporter:
                reporter.emit("review", f"skip code={code} reason=missing_prepared_history")
            continue

        baseline_review = resolver.review_history(
            code=code,
            pick_date=pick_date,
            history=history,
            chart_path=str(chart_path),
        )
        review = build_review_result(
            code=code,
            pick_date=pick_date,
            chart_path=str(chart_path),
            baseline_review=baseline_review,
        )
        (review_dir / f"{code}.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
        reviews.append(review)
        task = build_review_payload(
            code=code,
            pick_date=pick_date,
            chart_path=str(chart_path),
            rubric_path="references/review-rubric.md",
            prompt_path=resolver.prompt_path,
            extra_context=(
                _build_wave_task_context(history, pick_date, method=method)
                if method.lower() in {"b1", "b2", "dribull"}
                else None
            ),
        )
        llm_review_tasks.append(
            {
                **task,
                "rank": idx,
                "baseline_score": review["total_score"],
                "baseline_verdict": review["verdict"],
            }
        )

    summary = summarize_reviews(
        pick_date,
        method.lower(),
        reviews,
        min_score=4.0,
        failures=failures,
    )
    summary_path = review_dir / "summary.json"
    tasks_path = review_dir / "llm_review_tasks.json"
    tasks_payload = {
        "pick_date": pick_date,
        "method": method.lower(),
        "prompt_path": resolver.prompt_path,
        "max_concurrency": LLM_REVIEW_MAX_CONCURRENCY,
        "tasks": llm_review_tasks,
    }
    tasks_path.write_text(json.dumps(tasks_payload, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if reporter:
        reporter.emit("review", f"done reviewed={len(reviews)} failures={len(failures)} write={summary_path}")
    return summary_path


def _review_merge_impl(
    *,
    method: str,
    pick_date: str,
    runtime_root: Path,
    codes: list[str] | None = None,
    reporter: ProgressReporter | None = None,
) -> Path:
    review_dir = _review_dir_path(runtime_root, pick_date, method)
    if not review_dir.exists():
        raise typer.BadParameter(f"Review directory not found: {review_dir}")

    llm_results_dir = review_dir / "llm_review_results"
    if not llm_results_dir.exists():
        raise typer.BadParameter(f"LLM review result directory not found: {llm_results_dir}")

    selected_codes = set(codes or [])
    restrict_codes = bool(selected_codes)
    merged_reviews: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for review_path in sorted(review_dir.glob("*.json")):
        if review_path.name in {"summary.json", "llm_review_tasks.json"}:
            continue
        existing_review = json.loads(review_path.read_text(encoding="utf-8"))
        code = existing_review["code"]
        if restrict_codes and code not in selected_codes:
            merged_reviews.append(existing_review)
            continue
        llm_path = llm_results_dir / f"{code}.json"
        if not llm_path.exists():
            failures.append({"code": code, "reason": f"LLM review result not found: {llm_path}"})
            merged_reviews.append(existing_review)
            continue

        llm_payload = json.loads(llm_path.read_text(encoding="utf-8"))
        try:
            normalized_llm = normalize_llm_review({**llm_payload, "method": method})
        except ValueError as exc:
            failures.append({"code": code, "reason": str(exc)})
            merged_reviews.append(existing_review)
            continue

        merged_review = merge_review_result(method=method, existing_review=existing_review, llm_review=normalized_llm)
        review_path.write_text(json.dumps(merged_review, indent=2), encoding="utf-8")
        merged_reviews.append(merged_review)

    summary = summarize_reviews(
        pick_date,
        method.lower(),
        merged_reviews,
        min_score=4.0,
        failures=failures,
    )
    summary_path = review_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if reporter:
        reporter.emit("review-merge", f"merged reviews={len(merged_reviews)} failures={len(failures)} write={summary_path}")
    return summary_path


def _analyze_symbol_impl(
    *,
    method: str,
    symbol: str,
    pick_date: str | None,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    try:
        normalized_symbol = _normalize_ts_code(_validate_analyze_symbol(symbol))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    resolved_dsn = _resolve_cli_dsn(dsn)
    connection = _connect(resolved_dsn)

    if pick_date is None:
        resolved_pick_date = fetch_nth_latest_trade_date(connection, end_date=_today_local_date(), n=1)
    else:
        resolved_pick_date = _validate_cli_pick_date(pick_date)

    start_date = (pd.Timestamp(resolved_pick_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime(
        "%Y-%m-%d"
    )
    history = fetch_symbol_history(
        connection,
        symbol=normalized_symbol,
        start_date=start_date,
        end_date=resolved_pick_date,
    )
    if history.empty:
        raise typer.BadParameter(f"No daily history found for symbol: {normalized_symbol}")

    frame = history.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.loc[frame["trade_date"] <= pd.Timestamp(resolved_pick_date)].sort_values("trade_date").reset_index(
        drop=True
    )
    if "volume" not in frame.columns and "vol" in frame.columns:
        frame["volume"] = frame["vol"]
    if frame.empty or not bool((frame["trade_date"] == pd.Timestamp(resolved_pick_date)).any()):
        raise typer.BadParameter(
            f"No end-of-day data found for symbol {normalized_symbol} on pick_date {resolved_pick_date}."
        )

    signal_frame = _build_b2_signal_frame(frame, code=normalized_symbol)
    row = signal_frame.iloc[-1]
    signal = _resolve_signal(row)

    result_dir = runtime_root / "ad_hoc" / f"{resolved_pick_date}.{method}.{normalized_symbol}"
    result_dir.mkdir(parents=True, exist_ok=True)

    if reporter:
        reporter.emit("analyze-symbol", f"symbol={normalized_symbol}")
        reporter.emit("analyze-symbol", f"pick_date={resolved_pick_date}")
        reporter.emit("analyze-symbol", "export chart")

    chart_path = export_daily_chart(
        _prepare_chart_data(history),
        normalized_symbol,
        result_dir / f"{normalized_symbol}_day.png",
    )
    baseline_review = review_b2_symbol_history(
        code=normalized_symbol,
        pick_date=resolved_pick_date,
        history=history,
        chart_path=str(chart_path),
    )

    payload = {
        "code": normalized_symbol,
        "pick_date": resolved_pick_date,
        "method": method,
        "signal": signal,
        "selected_as_candidate": signal is not None,
        "screen_conditions": {
            "pre_ok": bool(row["pre_ok"]),
            "pct_ok": bool(row["pct_ok"]),
            "volume_ok": bool(row["volume_ok"]),
            "k_shape": bool(row["k_shape"]),
            "j_up": bool(row["j_up"]),
            "tr_ok": bool(row["tr_ok"]),
            "above_lt": bool(row["above_lt"]),
            "raw_b2_unique": bool(row["raw_b2_unique"]),
            "cur_b2": bool(row["cur_b2"]),
            "cur_b3": bool(row["cur_b3"]),
            "cur_b3_plus": bool(row["cur_b3_plus"]),
            "cur_b4": bool(row["cur_b4"]),
            "cur_b5": bool(row["cur_b5"]),
        },
        "latest_metrics": {
            "trade_date": str(pd.Timestamp(row["trade_date"]).date()),
            "open": round(float(row["open"]), 3),
            "high": round(float(row["high"]), 3),
            "low": round(float(row["low"]), 3),
            "close": round(float(row["close"]), 3),
            "pct": round(float(row["pct"]), 3),
            "volume": round(float(row["volume"]), 3),
            "j": round(float(row["J"]), 3),
        },
        "baseline_review": baseline_review,
        "chart_path": str(chart_path),
    }

    result_path = result_dir / "result.json"
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if reporter:
        reporter.emit("analyze-symbol", f"done write={result_path}")
    return result_path


def _render_html_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    review_dir = _review_dir_path(runtime_root, pick_date, method)
    summary_path = review_dir / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(f"Summary file not found: {summary_path}")

    resolved_dsn = _resolve_cli_dsn(dsn)
    if reporter:
        reporter.emit("render-html", "connect db")
    connection = _connect(resolved_dsn)

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    codes: list[str] = []
    for key in ("recommendations", "excluded"):
        values = summary_payload.get(key, [])
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code") or "").strip()
                if code:
                    codes.append(code)
    unique_codes = sorted(set(codes))

    if reporter:
        reporter.emit("render-html", f"lookup names count={len(unique_codes)}")
    names_by_code = fetch_instrument_names(connection, symbols=unique_codes)

    package_dir = review_dir / "summary-package"
    zip_path = write_summary_package(
        summary_path=summary_path,
        output_dir=package_dir,
        names_by_code=names_by_code,
    )
    if reporter:
        reporter.emit("render-html", f"write package={zip_path}")
    return zip_path


def _record_watch_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    window_trading_days: int,
    overwrite: bool,
    reporter: ProgressReporter | None = None,
) -> Path:
    if window_trading_days <= 0:
        raise typer.BadParameter("--window-trading-days must be positive.")

    summary_path = _review_dir_path(runtime_root, pick_date, method) / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(f"Summary file not found: {summary_path}")

    if reporter:
        reporter.emit("record-watch", f"load summary path={summary_path}")
    summary_payload = _load_summary_payload(summary_path)
    incoming_rows = summary_to_watch_rows(
        summary_payload,
        method=method,
        pick_date=pick_date,
        recorded_at=_recorded_at_timestamp(),
    )

    resolved_dsn = _resolve_cli_dsn(dsn)
    if reporter:
        reporter.emit("record-watch", "connect db")
    connection = _connect(resolved_dsn)
    execution_date = _today_local_date()
    execution_trade_date = fetch_nth_latest_trade_date(connection, end_date=execution_date, n=1)
    cutoff_trade_date = fetch_nth_latest_trade_date(connection, end_date=execution_trade_date, n=window_trading_days)
    trade_dates_frame = fetch_available_trade_dates(connection)
    if "trade_date" not in trade_dates_frame.columns:
        raise typer.BadParameter("Trade date calendar is unavailable.")
    trade_dates_desc = [str(value) for value in trade_dates_frame["trade_date"].tolist()]
    if not trade_dates_desc:
        raise typer.BadParameter("Trade date calendar is unavailable.")

    csv_path = _watch_pool_path(runtime_root, method)
    overwritten_count = 0
    imported_count = 0
    trimmed_count = 0

    def apply_watch_pool_update(existing_rows: pd.DataFrame) -> pd.DataFrame:
        nonlocal overwritten_count, imported_count, trimmed_count
        merged_rows, overwritten_count, imported_count = merge_watch_rows(
            existing_rows,
            incoming_rows,
            overwrite=overwrite,
        )
        final_rows, trimmed_count = trim_and_sort_watch_rows(
            merged_rows,
            trade_dates_desc=trade_dates_desc,
            execution_trade_date=execution_trade_date,
            cutoff_trade_date=cutoff_trade_date,
        )
        return final_rows

    try:
        update_watch_pool(csv_path, apply_watch_pool_update)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if reporter:
        reporter.emit(
            "record-watch",
            (
                f"done imported={imported_count} overwritten={overwritten_count} trimmed={trimmed_count} "
                f"execution_trade_date={execution_trade_date} cutoff_trade_date={cutoff_trade_date} write={csv_path}"
            ),
        )
    return csv_path


@app.command()
def screen(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    pool_source: str = typer.Option("turnover-top", "--pool-source"),
    pool_file: Path | None = typer.Option(None, "--pool-file"),
    dsn: str | None = typer.Option(None, "--dsn"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    normalized_pool_source = _validate_pool_source(pool_source)
    reporter = ProgressReporter(enabled=progress)
    try:
        if intraday:
            if pick_date is not None:
                raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
            _emit_intraday_hours_warning(reporter)
            out_path = _screen_intraday_impl(
                method=normalized_method,
                dsn=dsn,
                tushare_token=tushare_token,
                runtime_root=runtime_root,
                pool_source=normalized_pool_source,
                pool_file=pool_file,
                recompute=recompute,
                reporter=reporter,
            )
        else:
            if pick_date is None:
                raise typer.BadParameter("--pick-date is required unless --intraday is set.")
            out_path = _screen_impl(
                method=normalized_method,
                pick_date=pick_date,
                dsn=dsn,
                runtime_root=runtime_root,
                pool_source=normalized_pool_source,
                pool_file=pool_file,
                recompute=recompute,
                reporter=reporter,
            )
    except IntradayUserError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(str(out_path))


@app.command()
def chart(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    reporter = ProgressReporter(enabled=progress)
    if intraday:
        if pick_date is not None:
            raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
        _emit_intraday_hours_warning(reporter)
        chart_dir = _chart_intraday_impl(method=normalized_method, runtime_root=runtime_root, reporter=reporter)
    else:
        if pick_date is None:
            raise typer.BadParameter("--pick-date is required unless --intraday is set.")
        chart_dir = _chart_impl(
            method=normalized_method,
            pick_date=pick_date,
            dsn=dsn,
            runtime_root=runtime_root,
            reporter=reporter,
        )
    typer.echo(str(chart_dir))


@app.command()
def review(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    reporter = ProgressReporter(enabled=progress)
    if intraday:
        if pick_date is not None:
            raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
        _emit_intraday_hours_warning(reporter)
        summary_path = _review_intraday_impl(
            method=normalized_method,
            runtime_root=runtime_root,
            reporter=reporter,
        )
    else:
        if pick_date is None:
            raise typer.BadParameter("--pick-date is required unless --intraday is set.")
        summary_path = _review_impl(
            method=normalized_method,
            pick_date=pick_date,
            dsn=dsn,
            runtime_root=runtime_root,
            reporter=reporter,
        )
    typer.echo(str(summary_path))


@app.command(name="analyze-symbol")
def analyze_symbol(
    method: str = typer.Option(..., "--method"),
    symbol: str = typer.Option(..., "--symbol"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    if normalized_method != "b2":
        raise typer.BadParameter("analyze-symbol currently only supports method b2.")
    reporter = ProgressReporter(enabled=progress)
    result_path = _analyze_symbol_impl(
        method=normalized_method,
        symbol=symbol,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        reporter=reporter,
    )
    typer.echo(str(result_path))


@app.command(name="record-watch")
def record_watch(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    window_trading_days: int = typer.Option(10, "--window-trading-days"),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    reporter = ProgressReporter(enabled=progress)
    csv_path = _record_watch_impl(
        method=normalized_method,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        window_trading_days=window_trading_days,
        overwrite=overwrite,
        reporter=reporter,
    )
    typer.echo(str(csv_path))


@app.command(name="review-merge")
def review_merge(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    codes: str | None = typer.Option(None, "--codes"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    reporter = ProgressReporter(enabled=progress)
    selected_codes = [code.strip() for code in codes.split(",") if code.strip()] if codes else None
    summary_path = _review_merge_impl(
        method=normalized_method,
        pick_date=pick_date,
        runtime_root=runtime_root,
        codes=selected_codes,
        reporter=reporter,
    )
    typer.echo(str(summary_path))


@app.command(name="render-html")
def render_html(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    reporter = ProgressReporter(enabled=progress)
    zip_path = _render_html_impl(
        method=normalized_method,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        reporter=reporter,
    )
    typer.echo(str(zip_path))


@app.command(name="run")
def run_all(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    pool_source: str = typer.Option("turnover-top", "--pool-source"),
    pool_file: Path | None = typer.Option(None, "--pool-file"),
    dsn: str | None = typer.Option(None, "--dsn"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    normalized_pool_source = _validate_pool_source(pool_source)
    reporter = ProgressReporter(enabled=progress)
    if intraday and pick_date is not None:
        raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
    if not intraday and pick_date is None:
        raise typer.BadParameter("--pick-date is required unless --intraday is set.")

    reporter.emit("run", "step=screen start")
    screen_started_at = reporter.checkpoint()
    if intraday:
        _emit_intraday_hours_warning(reporter)
        screen_path = _screen_intraday_impl(
            method=normalized_method,
            dsn=dsn,
            tushare_token=tushare_token,
            runtime_root=runtime_root,
            pool_source=normalized_pool_source,
            pool_file=pool_file,
            recompute=recompute,
            reporter=reporter,
        )
    else:
        screen_path = _screen_impl(
            method=normalized_method,
            pick_date=pick_date,
            dsn=dsn,
            runtime_root=runtime_root,
            pool_source=normalized_pool_source,
            pool_file=pool_file,
            recompute=recompute,
            reporter=reporter,
        )
    reporter.emit("run", f"step=screen done path={screen_path} elapsed={reporter.since(screen_started_at):.1f}s")
    typer.echo(str(screen_path))
    reporter.emit("run", "step=chart start")
    chart_started_at = reporter.checkpoint()
    if intraday:
        chart_path = _chart_intraday_impl(method=normalized_method, runtime_root=runtime_root, reporter=reporter)
    else:
        chart_path = _chart_impl(
            method=normalized_method,
            pick_date=pick_date,
            dsn=dsn,
            runtime_root=runtime_root,
            reporter=reporter,
        )
    reporter.emit("run", f"step=chart done path={chart_path} elapsed={reporter.since(chart_started_at):.1f}s")
    typer.echo(str(chart_path))
    reporter.emit("run", "step=review start")
    review_started_at = reporter.checkpoint()
    if intraday:
        review_path = _review_intraday_impl(
            method=normalized_method,
            runtime_root=runtime_root,
            reporter=reporter,
        )
    else:
        review_path = _review_impl(
            method=normalized_method,
            pick_date=pick_date,
            dsn=dsn,
            runtime_root=runtime_root,
            reporter=reporter,
        )
    reporter.emit("run", f"step=review done path={review_path} elapsed={reporter.since(review_started_at):.1f}s")
    typer.echo(str(review_path))
