from __future__ import annotations

import json
from pathlib import Path

import typer


app = typer.Typer(help="stock-select standalone CLI")


def main() -> None:
    app()


def _ensure_b1(method: str) -> None:
    if method.lower() != "b1":
        raise typer.BadParameter("Only method 'b1' is supported.")


def _default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


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
    typer.echo(str(candidate_path))


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
    typer.echo(str(chart_dir))


@app.command(name="run")
def run_all(
    method: str = typer.Option(..., "--method"),
    pick_date: str = typer.Option(..., "--pick-date"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
) -> None:
    _ensure_b1(method)
    typer.echo(
        json.dumps(
            {
                "pick_date": pick_date,
                "method": "b1",
                "runtime_root": str(runtime_root),
            }
        )
    )
