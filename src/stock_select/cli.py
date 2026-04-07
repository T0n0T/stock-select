from __future__ import annotations

import json
import os
import pickle
import time
from pathlib import Path

import pandas as pd
import psycopg
import typer

from stock_select.b1_logic import (
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
)
from stock_select.charting import export_daily_chart
from stock_select.db_access import fetch_daily_window, fetch_symbol_history, load_dotenv_value, resolve_dsn
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


def _ensure_b1(method: str) -> None:
    if method.lower() != "b1":
        raise typer.BadParameter("Only method 'b1' is supported.")


def _default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def _connect(dsn: str):
    return psycopg.connect(dsn)


def _resolve_cli_dsn(dsn: str | None) -> str:
    dotenv_dsn = load_dotenv_value(Path.cwd() / ".env", "POSTGRES_DSN")
    return resolve_dsn(dsn, os.getenv("POSTGRES_DSN"), dotenv_dsn)


def _load_candidate_payload(candidate_path: Path) -> dict:
    return json.loads(candidate_path.read_text(encoding="utf-8"))


def _prepared_cache_path(runtime_root: Path, pick_date: str) -> Path:
    return runtime_root / "prepared" / f"{pick_date}.pkl"


def _write_prepared_cache(
    cache_path: Path,
    *,
    pick_date: str,
    start_date: str,
    end_date: str,
    prepared_by_symbol: dict[str, pd.DataFrame],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pick_date": pick_date,
        "start_date": start_date,
        "end_date": end_date,
        "prepared_by_symbol": prepared_by_symbol,
        "metadata": {
            "b1_config": DEFAULT_B1_CONFIG,
            "turnover_window": DEFAULT_TURNOVER_WINDOW,
            "weekly_ma_periods": DEFAULT_WEEKLY_MA_PERIODS,
            "max_vol_lookback": DEFAULT_MAX_VOL_LOOKBACK,
        },
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

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return pd.DataFrame(
        {
            "date": frame["trade_date"],
            "open": frame["open"].astype(float),
            "high": frame["high"].astype(float),
            "low": frame["low"].astype(float),
            "close": frame["close"].astype(float),
            "volume": frame["vol"].astype(float),
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


def _screen_impl(
    *,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    recompute: bool = False,
    reporter: ProgressReporter | None = None,
) -> Path:
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    out_path = candidate_dir / f"{pick_date}.json"
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

    start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d")
    prepared_cache_path = _prepared_cache_path(runtime_root, pick_date)
    prepared: dict[str, pd.DataFrame] | None = None
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
        prepared = _call_prepare_screen_data(market, reporter=reporter)
        _write_prepared_cache(
            prepared_cache_path,
            pick_date=pick_date,
            start_date=start_date,
            end_date=pick_date,
            prepared_by_symbol=prepared,
        )
        if reporter:
            reporter.emit("screen", f"write prepared path={prepared_cache_path}")
    top_turnover_pool = build_top_turnover_pool(prepared, top_m=DEFAULT_TOP_M)
    pool_codes = top_turnover_pool.get(pd.Timestamp(pick_date), [])
    prepared_for_pick = {code: prepared[code] for code in pool_codes if code in prepared}
    if reporter:
        reporter.emit("screen", "run b1 screen")
    candidates, stats = run_b1_screen_with_stats(
        prepared_for_pick,
        pd.Timestamp(pick_date),
        DEFAULT_B1_CONFIG,
    )
    payload = {"pick_date": pick_date, "method": "b1", "candidates": candidates}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if reporter:
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
        reporter.emit("screen", f"selected candidates={len(candidates)} write={out_path}")
    return out_path


def _chart_impl(
    *,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    candidate_path = runtime_root / "candidates" / f"{pick_date}.json"
    if not candidate_path.exists():
        raise typer.BadParameter(f"Candidate file not found: {candidate_path}")
    payload = _load_candidate_payload(candidate_path)
    chart_dir = runtime_root / "charts" / pick_date
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


def _review_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    chart_dir = runtime_root / "charts" / pick_date
    if not chart_dir.exists():
        raise typer.BadParameter(f"Chart input directory not found: {chart_dir}")
    candidate_path = runtime_root / "candidates" / f"{pick_date}.json"
    if not candidate_path.exists():
        raise typer.BadParameter(f"Candidate file not found: {candidate_path}")
    review_dir = runtime_root / "reviews" / pick_date
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


def _review_merge_impl(
    *,
    method: str,
    pick_date: str,
    runtime_root: Path,
    codes: list[str] | None = None,
    reporter: ProgressReporter | None = None,
) -> Path:
    review_dir = runtime_root / "reviews" / pick_date
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


@app.command()
def screen(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    _ensure_b1(method)
    reporter = ProgressReporter(enabled=progress)
    out_path = _screen_impl(
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        recompute=recompute,
        reporter=reporter,
    )
    typer.echo(str(out_path))


@app.command()
def chart(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    _ensure_b1(method)
    reporter = ProgressReporter(enabled=progress)
    chart_dir = _chart_impl(pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, reporter=reporter)
    typer.echo(str(chart_dir))


@app.command()
def review(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    _ensure_b1(method)
    reporter = ProgressReporter(enabled=progress)
    summary_path = _review_impl(method=method, pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, reporter=reporter)
    typer.echo(str(summary_path))


@app.command(name="review-merge")
def review_merge(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    codes: str | None = typer.Option(None, "--codes"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    _ensure_b1(method)
    reporter = ProgressReporter(enabled=progress)
    selected_codes = [code.strip() for code in codes.split(",") if code.strip()] if codes else None
    summary_path = _review_merge_impl(
        method=method,
        pick_date=pick_date,
        runtime_root=runtime_root,
        codes=selected_codes,
        reporter=reporter,
    )
    typer.echo(str(summary_path))


@app.command(name="run")
def run_all(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    _ensure_b1(method)
    reporter = ProgressReporter(enabled=progress)
    reporter.emit("run", "step=screen start")
    screen_started_at = reporter.checkpoint()
    screen_path = _screen_impl(
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
    chart_path = _chart_impl(pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, reporter=reporter)
    reporter.emit("run", f"step=chart done path={chart_path} elapsed={reporter.since(chart_started_at):.1f}s")
    typer.echo(str(chart_path))
    reporter.emit("run", "step=review start")
    review_started_at = reporter.checkpoint()
    review_path = _review_impl(method=method, pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, reporter=reporter)
    reporter.emit("run", f"step=review done path={review_path} elapsed={reporter.since(review_started_at):.1f}s")
    typer.echo(str(review_path))
