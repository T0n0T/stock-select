from pathlib import Path

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
