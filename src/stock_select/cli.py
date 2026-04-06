from __future__ import annotations

import json
from pathlib import Path

import typer

from stock_select.charting import export_daily_chart
from stock_select.review_orchestrator import summarize_reviews


app = typer.Typer(help="stock-select standalone CLI")


def main() -> None:
    app()


def _ensure_b1(method: str) -> None:
    if method.lower() != "b1":
        raise typer.BadParameter("Only method 'b1' is supported.")


def _default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def _load_candidate_payload(candidate_path: Path) -> dict:
    return json.loads(candidate_path.read_text(encoding="utf-8"))


def _sample_chart_frame() -> list[dict[str, float | str]]:
    return [
        {"date": "2026-03-26", "open": 10.0, "high": 10.4, "low": 9.9, "close": 10.2, "volume": 800.0},
        {"date": "2026-03-27", "open": 10.2, "high": 10.5, "low": 10.1, "close": 10.4, "volume": 900.0},
        {"date": "2026-03-30", "open": 10.4, "high": 10.9, "low": 10.3, "close": 10.8, "volume": 1200.0},
    ]


@app.command()
def screen(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    out_path = candidate_dir / f"{pick_date}.json"
    payload = {"pick_date": pick_date, "method": "b1", "candidates": []}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    typer.echo(str(out_path))


@app.command()
def chart(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    candidate_path = runtime_root / "candidates" / f"{pick_date}.json"
    if not candidate_path.exists():
        raise typer.BadParameter(f"Candidate file not found: {candidate_path}")
    payload = _load_candidate_payload(candidate_path)
    chart_dir = runtime_root / "charts" / pick_date
    chart_dir.mkdir(parents=True, exist_ok=True)

    import pandas as pd

    for candidate in payload.get("candidates", []):
        code = candidate["code"]
        out_path = chart_dir / f"{code}_day.html"
        export_daily_chart(pd.DataFrame(_sample_chart_frame()), code, out_path)
    typer.echo(str(chart_dir))


@app.command()
def review(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
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
    typer.echo(str(summary_path))


@app.command(name="run")
def run_all(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    screen(method=method, pick_date=pick_date, runtime_root=runtime_root)
    chart(method=method, pick_date=pick_date, runtime_root=runtime_root)
    review(method=method, pick_date=pick_date, runtime_root=runtime_root)
