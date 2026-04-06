from pathlib import Path

import json
from types import SimpleNamespace

import pandas as pd
from typer.testing import CliRunner

from stock_select import cli
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
    runtime_root.mkdir(parents=True, exist_ok=True)

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "open": [10.0],
                "high": [10.8],
                "low": [9.8],
                "close": [10.6],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "close": [10.6],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [1030.0],
                }
            )
        }

    from stock_select import cli

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]

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
            "--dsn",
            "postgresql://example",
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

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "open": [10.0],
                "high": [10.8],
                "low": [9.8],
                "close": [10.6],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "close": [10.6],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [1030.0],
                }
            )
        }

    from stock_select import cli

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]

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
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert (runtime_root / "reviews" / "2026-04-01" / "summary.json").exists()


def test_screen_requires_dsn_when_real_data_fetch_is_needed(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(tmp_path / "runtime"),
        ],
    )

    assert result.exit_code != 0
    assert "dsn" in (result.stderr or str(result.exception)).lower()


def test_screen_writes_candidate_records_from_market_data(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    def fake_connect(dsn: str) -> object:
        assert dsn == "postgresql://example"
        return object()

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        assert start_date == "2025-03-31"
        assert end_date == "2026-04-01"
        assert symbols is None
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2026-03-31", "2026-04-01", "2026-04-01"]),
                "open": [10.0, 10.2, 9.5],
                "high": [10.5, 10.8, 9.8],
                "low": [9.9, 10.1, 9.2],
                "close": [10.4, 10.7, 9.3],
                "vol": [100.0, 120.0, 80.0],
            }
        )

    def fake_prepare_screen_data(market: pd.DataFrame) -> dict[str, pd.DataFrame]:
        assert not market.empty
        return {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-03-31", "2026-04-01"]),
                    "close": [10.4, 10.7],
                    "J": [11.0, 10.0],
                    "zxdq": [10.2, 10.5],
                    "zxdkx": [10.0, 10.2],
                    "weekly_ma_bull": [True, True],
                    "max_vol_not_bearish": [True, True],
                    "turnover_n": [1020.0, 2280.0],
                }
            ),
            "000002.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "close": [9.3],
                    "J": [90.0],
                    "zxdq": [9.1],
                    "zxdkx": [9.4],
                    "weekly_ma_bull": [False],
                    "max_vol_not_bearish": [False],
                    "turnover_n": [760.0],
                }
            ),
        }

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)

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
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / "2026-04-01.json").read_text(encoding="utf-8"))
    assert payload["pick_date"] == "2026-04-01"
    assert payload["method"] == "b1"
    assert payload["candidates"] == [
        {
            "code": "000001.SZ",
            "pick_date": "2026-04-01",
            "close": 10.7,
            "turnover_n": 2280.0,
        }
    ]
