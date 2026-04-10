from __future__ import annotations

import json
import os
import pickle
import time
from pathlib import Path

import pandas as pd
import psycopg
import typer

from stock_select.strategies import (
    DEFAULT_B1_CONFIG,
    DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool,
    compute_kdj,
    compute_turnover_n,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
    run_b1_screen_with_stats,
    run_b2_screen_with_stats,
    validate_method,
)
from stock_select.strategies.hcr import (
    HCR_REQUIRED_TRADING_DAYS,
    prepare_hcr_frame,
    run_hcr_screen_with_stats,
)
from stock_select.charting import export_daily_chart
from stock_select.db_access import (
    fetch_daily_window,
    fetch_instrument_names,
    fetch_nth_latest_trade_date,
    fetch_previous_trade_date,
    fetch_symbol_history,
    load_dotenv_value,
    resolve_dsn,
)
from stock_select.html_export import write_summary_package
from stock_select.intraday import build_intraday_market_frame, normalize_rt_k_snapshot
from stock_select.review_orchestrator import (
    REFERENCE_PROMPT_PATH,
    build_review_payload,
    build_review_result,
    merge_review_result,
    normalize_llm_review,
    review_symbol_history,
    summarize_reviews,
)


app = typer.Typer(help="stock-select standalone CLI")

DEFAULT_SCREEN_LOOKBACK_DAYS = 366
HCR_SCREEN_TRADING_DAYS = HCR_REQUIRED_TRADING_DAYS


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


def _default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def _connect(dsn: str):
    return psycopg.connect(dsn)


def _resolve_cli_dsn(dsn: str | None) -> str:
    dotenv_dsn = load_dotenv_value(Path.cwd() / ".env", "POSTGRES_DSN")
    return resolve_dsn(dsn, os.getenv("POSTGRES_DSN"), dotenv_dsn)


def _load_candidate_payload(candidate_path: Path) -> dict:
    return json.loads(candidate_path.read_text(encoding="utf-8"))


def _artifact_key(base_key: str, method: str) -> str:
    return f"{base_key}.{method}"


def _candidate_path(runtime_root: Path, base_key: str, method: str) -> Path:
    return runtime_root / "candidates" / f"{_artifact_key(base_key, method)}.json"


def _prepared_cache_path(runtime_root: Path, base_key: str, method: str) -> Path:
    return runtime_root / "prepared" / f"{_artifact_key(base_key, method)}.pkl"


def _chart_dir_path(runtime_root: Path, base_key: str, method: str) -> Path:
    return runtime_root / "charts" / _artifact_key(base_key, method)


def _review_dir_path(runtime_root: Path, base_key: str, method: str) -> Path:
    return runtime_root / "reviews" / _artifact_key(base_key, method)


def _intraday_candidate_path(runtime_root: Path, run_id: str, method: str) -> Path:
    return _candidate_path(runtime_root, run_id, method)


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

    for candidate_path in sorted(candidate_dir.glob("*.json")):
        try:
            payload = _load_candidate_payload(candidate_path)
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if payload.get("mode") != "intraday_snapshot":
            continue
        if _candidate_payload_method(candidate_path, payload) != method:
            continue
        payload_run_id = payload.get("run_id")
        run_id = payload_run_id.strip() if isinstance(payload_run_id, str) and payload_run_id.strip() else _fallback_run_id(candidate_path)
        if latest_run_id is None or run_id > latest_run_id:
            latest_path = candidate_path
            latest_payload = payload
            latest_run_id = run_id

    if latest_path is None or latest_payload is None:
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


def _load_intraday_prepared_cache(
    runtime_root: Path,
    *,
    method: str,
    run_id: str,
    trade_date: str,
) -> dict[str, pd.DataFrame]:
    payload = _load_prepared_cache(_prepared_cache_path(runtime_root, run_id, method))
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise IntradayArtifactError("Prepared intraday cache metadata mismatch.")
    if metadata.get("mode") != "intraday_snapshot":
        raise IntradayArtifactError("Prepared intraday cache metadata mismatch.")
    if metadata.get("run_id") != run_id:
        raise IntradayArtifactError("Prepared intraday cache metadata mismatch.")
    if metadata.get("method", method) != method:
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
        raw_snapshot = pro.rt_k()
    except Exception as exc:
        msg = f"Failed to fetch Tushare rt_k snapshot: {exc}"
        raise IntradayUserError(msg) from exc
    if raw_snapshot is None or raw_snapshot.empty:
        msg = "Tushare rt_k returned no usable rows."
        raise IntradayUserError(msg)

    return normalize_rt_k_snapshot(raw_snapshot, trade_date=trade_date)


def compute_macd(
    frame: pd.DataFrame,
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    close = frame["close"].astype(float)
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_hist = dif - dea
    return pd.DataFrame({"dif": dif, "dea": dea, "macd_hist": macd_hist}, index=frame.index)


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
        zxdq, zxdkx = compute_zx_lines(group)
        group["zxdq"] = zxdq
        group["zxdkx"] = zxdkx
        macd = compute_macd(group)
        group["dif"] = macd["dif"]
        group["dea"] = macd["dea"]
        group["macd_hist"] = macd["macd_hist"]
        group["weekly_ma_bull"] = compute_weekly_ma_bull(group, ma_periods=DEFAULT_WEEKLY_MA_PERIODS)
        group["max_vol_not_bearish"] = max_vol_not_bearish(group, lookback=DEFAULT_MAX_VOL_LOOKBACK)
        prepared[code] = group
        if reporter and (idx == 1 or idx == total or idx % progress_every == 0):
            reporter.emit(
                "screen",
                f"prepare {idx}/{total} symbol={code} elapsed={reporter.elapsed_seconds():.1f}s",
            )
    return prepared


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
            f"selected={stats['selected']}",
        )
        return
    if method == "b2":
        reporter.emit(
            "screen",
            "breakdown "
            f"total_symbols={stats['total_symbols']} "
            f"eligible={stats['eligible']} "
            f"fail_recent_j={stats['fail_recent_j']} "
            f"fail_insufficient_history={stats['fail_insufficient_history']} "
            f"fail_zxdq_zxdkx={stats['fail_zxdq_zxdkx']} "
            f"fail_weekly_ma={stats['fail_weekly_ma']} "
            f"fail_macd_trend={stats['fail_macd_trend']} "
            f"selected={stats['selected']}",
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
    recompute: bool = False,
    reporter: ProgressReporter | None = None,
) -> Path:
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    out_path = _candidate_path(runtime_root, pick_date, method)
    if not recompute and out_path.exists():
        try:
            existing_payload = _load_candidate_payload(out_path)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            if reporter:
                reporter.emit("screen", f"candidate reuse skipped path={out_path} reason={type(exc).__name__}")
        else:
            existing_candidates = existing_payload.get("candidates", [])
            if isinstance(existing_candidates, list) and existing_candidates:
                if reporter:
                    reporter.emit("screen", f"reuse candidates path={out_path}")
                return out_path

    prepared_cache_path = _prepared_cache_path(runtime_root, pick_date, method)
    prepared: dict[str, pd.DataFrame] | None = None
    start_date = (
        (pd.Timestamp(pick_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        if method in {"b1", "b2"}
        else None
    )
    if not recompute and prepared_cache_path.exists():
        try:
            cache_payload = _load_prepared_cache(prepared_cache_path)
        except (OSError, ValueError, pickle.PickleError) as exc:
            if reporter:
                reporter.emit("screen", f"prepared reuse skipped path={prepared_cache_path} reason={type(exc).__name__}")
        else:
            cached_pick_date = cache_payload.get("pick_date")
            cached_start_date = cache_payload.get("start_date")
            cached_end_date = cache_payload.get("end_date")
            if cached_pick_date == pick_date and cached_start_date == start_date and cached_end_date == pick_date:
                prepared = cache_payload["prepared_by_symbol"]  # type: ignore[assignment]
                if reporter:
                    reporter.emit("screen", f"reuse prepared path={prepared_cache_path}")

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
        elif start_date is None:
            start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
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
        if method in {"b1", "b2"}:
            prepared = _call_prepare_screen_data(market, reporter=reporter)
        else:
            prepared = _call_prepare_hcr_screen_data(market, reporter=reporter)
        _write_prepared_cache(
            prepared_cache_path,
            method=method,
            pick_date=pick_date,
            start_date=start_date,
            end_date=pick_date,
            prepared_by_symbol=prepared,
        )
        if reporter:
            reporter.emit("screen", f"write prepared path={prepared_cache_path}")
    if method in {"b1", "b2"}:
        if prepared is None:
            prepared = {}
        top_turnover_pool = build_top_turnover_pool(prepared, top_m=DEFAULT_TOP_M)
        pool_codes = top_turnover_pool.get(pd.Timestamp(pick_date), [])
        prepared_for_pick = {code: prepared[code] for code in pool_codes if code in prepared}
        if reporter:
            reporter.emit("screen", f"run {method} screen")
        if method == "b1":
            candidates, stats = run_b1_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(pick_date),
                DEFAULT_B1_CONFIG,
            )
        else:
            candidates, stats = run_b2_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(pick_date),
                DEFAULT_B1_CONFIG,
            )
    else:
        if reporter:
            reporter.emit("screen", "run hcr screen")
        candidates, stats = run_hcr_screen_with_stats(prepared, pd.Timestamp(pick_date))
    payload = {"pick_date": pick_date, "method": method, "candidates": candidates}
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
    reporter: ProgressReporter | None = None,
) -> Path:
    trade_date = _resolve_intraday_trade_date()
    resolved_token = _resolve_tushare_token(tushare_token)
    resolved_dsn = _resolve_cli_dsn(dsn)
    if reporter:
        reporter.emit("screen", "connect db")
    connection = _connect(resolved_dsn)
    previous_trade_date = _resolve_previous_trade_date(connection, trade_date)
    if reporter:
        reporter.emit("screen", f"fetch snapshot trade_date={trade_date}")
    snapshot = _fetch_rt_k_snapshot(resolved_token, trade_date)
    run_id = _format_intraday_run_id(_current_shanghai_timestamp())
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
    if method in {"b1", "b2"}:
        prepared = _call_prepare_screen_data(overlay_market, reporter=reporter)
    else:
        prepared = _call_prepare_hcr_screen_data(overlay_market, reporter=reporter)
    prepared_cache_path = _prepared_cache_path(runtime_root, run_id, method)
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

    if method in {"b1", "b2"}:
        top_turnover_pool = build_top_turnover_pool(prepared, top_m=DEFAULT_TOP_M)
        pool_codes = top_turnover_pool.get(pd.Timestamp(trade_date), [])
        prepared_for_pick = {code: prepared[code] for code in pool_codes if code in prepared}
        if reporter:
            reporter.emit("screen", f"run {method} screen")
        if method == "b1":
            candidates, stats = run_b1_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(trade_date),
                DEFAULT_B1_CONFIG,
            )
        else:
            candidates, stats = run_b2_screen_with_stats(
                prepared_for_pick,
                pd.Timestamp(trade_date),
                DEFAULT_B1_CONFIG,
            )
    else:
        if reporter:
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
        "candidates": candidates,
    }
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
    payload = _load_candidate_payload(candidate_path)
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
    chart_dir = _chart_dir_path(runtime_root, pick_date, method)
    if not chart_dir.exists():
        raise typer.BadParameter(f"Chart input directory not found: {chart_dir}")
    candidate_path = _candidate_path(runtime_root, pick_date, method)
    if not candidate_path.exists():
        raise typer.BadParameter(f"Candidate file not found: {candidate_path}")
    review_dir = _review_dir_path(runtime_root, pick_date, method)
    review_dir.mkdir(parents=True, exist_ok=True)
    payload = _load_candidate_payload(candidate_path)
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
        baseline_review = review_symbol_history(
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
        "prompt_path": REFERENCE_PROMPT_PATH,
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

        baseline_review = review_symbol_history(
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
        "prompt_path": REFERENCE_PROMPT_PATH,
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
            normalized_llm = normalize_llm_review(llm_payload)
        except ValueError as exc:
            failures.append({"code": code, "reason": str(exc)})
            merged_reviews.append(existing_review)
            continue

        merged_review = merge_review_result(existing_review=existing_review, llm_review=normalized_llm)
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


@app.command()
def screen(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    reporter = ProgressReporter(enabled=progress)
    try:
        if intraday:
            if pick_date is not None:
                raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
            out_path = _screen_intraday_impl(
                method=normalized_method,
                dsn=dsn,
                tushare_token=tushare_token,
                runtime_root=runtime_root,
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
    normalized_method = _validate_cli_method(method)
    reporter = ProgressReporter(enabled=progress)
    if intraday:
        if pick_date is not None:
            raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
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


@app.command(name="review-merge")
def review_merge(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    codes: str | None = typer.Option(None, "--codes"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
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
    normalized_method = _validate_cli_method(method)
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
    dsn: str | None = typer.Option(None, "--dsn"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    reporter = ProgressReporter(enabled=progress)
    if intraday and pick_date is not None:
        raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
    if not intraday and pick_date is None:
        raise typer.BadParameter("--pick-date is required unless --intraday is set.")

    reporter.emit("run", "step=screen start")
    screen_started_at = reporter.checkpoint()
    if intraday:
        screen_path = _screen_intraday_impl(
            method=normalized_method,
            dsn=dsn,
            tushare_token=tushare_token,
            runtime_root=runtime_root,
            reporter=reporter,
        )
    else:
        screen_path = _screen_impl(
            method=normalized_method,
            pick_date=pick_date,
            dsn=dsn,
            runtime_root=runtime_root,
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
