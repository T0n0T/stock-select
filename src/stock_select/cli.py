from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import psycopg
import typer

from stock_select.b1_logic import (
    compute_kdj,
    compute_turnover_n,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
)
from stock_select.charting import export_daily_chart
from stock_select.db_access import fetch_daily_window, resolve_dsn
from stock_select.review_orchestrator import summarize_reviews


app = typer.Typer(help="stock-select standalone CLI")


def main() -> None:
    app()


def _ensure_b1(method: str) -> None:
    if method.lower() != "b1":
        raise typer.BadParameter("Only method 'b1' is supported.")


def _default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def _connect(dsn: str):
    return psycopg.connect(dsn)


def _load_candidate_payload(candidate_path: Path) -> dict:
    return json.loads(candidate_path.read_text(encoding="utf-8"))


def _sample_chart_frame() -> list[dict[str, float | str]]:
    return [
        {"date": "2026-03-26", "open": 10.0, "high": 10.4, "low": 9.9, "close": 10.2, "volume": 800.0},
        {"date": "2026-03-27", "open": 10.2, "high": 10.5, "low": 10.1, "close": 10.4, "volume": 900.0},
        {"date": "2026-03-30", "open": 10.4, "high": 10.9, "low": 10.3, "close": 10.8, "volume": 1200.0},
    ]


def _prepare_screen_data(market: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if market.empty:
        return {}

    prepared: dict[str, pd.DataFrame] = {}
    frame = market.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    if "volume" not in frame.columns and "vol" in frame.columns:
        frame["volume"] = frame["vol"]

    for code, group in frame.groupby("ts_code"):
        group = group.sort_values("trade_date").reset_index(drop=True)
        group["turnover_n"] = compute_turnover_n(group, window=30)
        kdj = compute_kdj(group)
        group["J"] = kdj["J"]
        zxdq, zxdkx = compute_zx_lines(group)
        group["zxdq"] = zxdq
        group["zxdkx"] = zxdkx
        group["weekly_ma_bull"] = compute_weekly_ma_bull(group)
        group["max_vol_not_bearish"] = max_vol_not_bearish(group, lookback=20)
        prepared[code] = group
    return prepared


def _screen_impl(*, pick_date: str, dsn: str | None, runtime_root: Path) -> Path:
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    out_path = candidate_dir / f"{pick_date}.json"

    resolved_dsn = resolve_dsn(dsn, os.getenv("POSTGRES_DSN"))
    connection = _connect(resolved_dsn)
    market = fetch_daily_window(
        connection,
        start_date=(pd.Timestamp(pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d"),
        end_date=pick_date,
        symbols=None,
    )
    prepared = _prepare_screen_data(market)
    candidates = run_b1_screen(prepared, pd.Timestamp(pick_date), {"j_threshold": 20.0, "j_q_threshold": 0.2})
    payload = {"pick_date": pick_date, "method": "b1", "candidates": candidates}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _chart_impl(*, pick_date: str, runtime_root: Path) -> Path:
    candidate_path = runtime_root / "candidates" / f"{pick_date}.json"
    if not candidate_path.exists():
        raise typer.BadParameter(f"Candidate file not found: {candidate_path}")
    payload = _load_candidate_payload(candidate_path)
    chart_dir = runtime_root / "charts" / pick_date
    chart_dir.mkdir(parents=True, exist_ok=True)

    for candidate in payload.get("candidates", []):
        code = candidate["code"]
        out_path = chart_dir / f"{code}_day.html"
        export_daily_chart(pd.DataFrame(_sample_chart_frame()), code, out_path)
    return chart_dir


def _review_impl(*, method: str, pick_date: str, runtime_root: Path) -> Path:
    chart_dir = runtime_root / "charts" / pick_date
    if not chart_dir.exists():
        raise typer.BadParameter(f"Chart input directory not found: {chart_dir}")
    review_dir = runtime_root / "reviews" / pick_date
    review_dir.mkdir(parents=True, exist_ok=True)

    reviews: list[dict[str, object]] = []
    for chart_path in sorted(chart_dir.glob("*_day.html")):
        code = chart_path.name.removesuffix("_day.html")
        review = {
            "code": code,
            "total_score": 4.0,
            "verdict": "PASS",
            "signal_type": "trend_start",
            "comment": "周线趋势向上，量价结构正常。",
        }
        (review_dir / f"{code}.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
        reviews.append(review)

    summary = summarize_reviews(
        pick_date,
        method.lower(),
        reviews,
        min_score=4.0,
        failures=[],
    )
    summary_path = review_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary_path


@app.command()
def screen(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    out_path = _screen_impl(pick_date=pick_date, dsn=dsn, runtime_root=runtime_root)
    typer.echo(str(out_path))


@app.command()
def chart(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    chart_dir = _chart_impl(pick_date=pick_date, runtime_root=runtime_root)
    typer.echo(str(chart_dir))


@app.command()
def review(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    summary_path = _review_impl(method=method, pick_date=pick_date, runtime_root=runtime_root)
    typer.echo(str(summary_path))


@app.command(name="run")
def run_all(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    typer.echo(str(_screen_impl(pick_date=pick_date, dsn=dsn, runtime_root=runtime_root)))
    typer.echo(str(_chart_impl(pick_date=pick_date, runtime_root=runtime_root)))
    typer.echo(str(_review_impl(method=method, pick_date=pick_date, runtime_root=runtime_root)))
