from pathlib import Path

import json

from typer.testing import CliRunner

from stock_select.cli import app


def test_screen_rejects_non_b1_method() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["screen", "--method", "brick", "--pick-date", "2026-04-01"])

    assert result.exit_code != 0
    assert "b1" in result.stderr.lower()


def test_chart_requires_candidate_file(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    result = runner.invoke(
        app,
        [
            "chart",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code != 0
    assert "candidate" in result.stderr.lower()


def test_screen_writes_candidate_file(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert (runtime_root / "candidates" / "2026-04-01.json").exists()


def test_chart_exports_html_for_candidates(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-01.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "chart",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert (runtime_root / "charts" / "2026-04-01" / "000001.SZ_day.html").exists()


def test_review_writes_summary_json(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    chart_dir = runtime_root / "charts" / "2026-04-01"
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.html").write_text("<html></html>", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert (runtime_root / "reviews" / "2026-04-01" / "summary.json").exists()


def test_run_writes_final_summary(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert (runtime_root / "reviews" / "2026-04-01" / "summary.json").exists()
