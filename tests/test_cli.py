from pathlib import Path

import importlib
import json
import pickle
import zipfile
from types import SimpleNamespace

import pandas as pd
import pytest
from typer.testing import CliRunner

from stock_select import cli
from stock_select.cli import app


def test_screen_rejects_unknown_method() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["screen", "--method", "brick", "--pick-date", "2026-04-01"])

    assert result.exit_code != 0
    assert "supported methods" in result.stderr.lower()
    assert "b1" in result.stderr.lower()
    assert "hcr" in result.stderr.lower()


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


def test_chart_requires_dsn_when_real_history_fetch_is_needed(tmp_path: Path) -> None:
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

    assert result.exit_code != 0
    assert "dsn" in (result.stderr or str(result.exception)).lower()


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
    assert "[screen] connect db" in result.stderr
    assert "[screen] selected candidates=" in result.stderr


def test_chart_exports_png_for_candidates(tmp_path: Path) -> None:
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

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_symbol_history(
        connection: object,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        assert symbol == "000001.SZ"
        assert start_date == "2025-03-31"
        assert end_date == "2026-04-01"
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "trade_date": pd.to_datetime(["2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2],
                "high": [10.5, 10.8],
                "low": [9.9, 10.1],
                "close": [10.4, 10.7],
                "vol": [100.0, 120.0],
            }
        )

    def fake_export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
        assert code == "000001.SZ"
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert df.to_dict(orient="records") == [
            {
                "date": pd.Timestamp("2026-03-31"),
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "close": 10.4,
                "volume": 100.0,
            },
            {
                "date": pd.Timestamp("2026-04-01"),
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "close": 10.7,
                "volume": 120.0,
            },
        ]
        out_path.write_bytes(b"png")
        return out_path

    from stock_select import cli

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_symbol_history = fake_fetch_symbol_history  # type: ignore[assignment]
    cli.export_daily_chart = fake_export_daily_chart  # type: ignore[assignment]

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
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert (runtime_root / "charts" / "2026-04-01" / "000001.SZ_day.png").exists()
    assert "[chart] candidate 1/1 code=000001.SZ" in result.stderr


def test_chart_accepts_hcr_candidate_file_shape(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-01.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "hcr",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())

    def fake_fetch_symbol_history(
        connection: object,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        assert symbol == "000001.SZ"
        assert start_date == "2025-03-31"
        assert end_date == "2026-04-01"
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "trade_date": pd.to_datetime(["2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2],
                "high": [10.5, 10.8],
                "low": [9.9, 10.1],
                "close": [10.4, 10.7],
                "vol": [100.0, 120.0],
            }
        )

    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        fake_fetch_symbol_history,
    )

    def fake_export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
        assert code == "000001.SZ"
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert df.to_dict(orient="records") == [
            {
                "date": pd.Timestamp("2026-03-31"),
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "close": 10.4,
                "volume": 100.0,
            },
            {
                "date": pd.Timestamp("2026-04-01"),
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "close": 10.7,
                "volume": 120.0,
            },
        ]
        out_path.write_bytes(b"png")
        return out_path

    monkeypatch.setattr(
        cli,
        "export_daily_chart",
        fake_export_daily_chart,
    )

    result = runner.invoke(
        app,
        [
            "chart",
            "--method",
            "hcr",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    monkeypatch.undo()

    assert result.exit_code == 0
    assert (runtime_root / "charts" / "2026-04-01" / "000001.SZ_day.png").exists()


def test_chart_intraday_uses_latest_intraday_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-09T10-00-00+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T10-00-00+08-00",
                "candidates": [{"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / "2026-04-09T11-31-08+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "fetched_at": "2026-04-09T11-31-08+08-00",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_intraday_prepared_cache",
        lambda current_runtime_root, *, run_id, trade_date: (
            {
                "000001.SZ": pd.DataFrame(
                    [
                        {"date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "volume": 120.0},
                        {"date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "volume": 150.0},
                    ]
                )
            }
            if current_runtime_root == runtime_root
            and run_id == "2026-04-09T11-31-08+08-00"
            and trade_date == "2026-04-09"
            else pytest.fail("chart did not request the latest intraday prepared cache")
        ),
    )
    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("chart --intraday should not connect to the database"))
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda *args, **kwargs: pytest.fail("chart --intraday should not fetch symbol history"),
    )

    def fake_export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
        assert code == "000001.SZ"
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert df.to_dict(orient="records") == [
            {
                "date": pd.Timestamp("2026-04-08"),
                "open": 11.9,
                "high": 12.1,
                "low": 11.8,
                "close": 12.0,
                "volume": 120.0,
            },
            {
                "date": pd.Timestamp("2026-04-09"),
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "volume": 150.0,
            },
        ]
        out_path.write_bytes(b"png")
        return out_path

    monkeypatch.setattr(cli, "export_daily_chart", fake_export_daily_chart)

    result = runner.invoke(app, ["chart", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code == 0
    assert (runtime_root / "charts" / "2026-04-09T11-31-08+08-00" / "000001.SZ_day.png").exists()


def test_chart_intraday_rejects_malformed_latest_candidate_payload(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-09T10-00-00+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T10-00-00+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / "2026-04-09T11-31-08+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{}],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["chart", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code != 0
    assert "malformed intraday candidate file" in result.stderr.lower()


def test_chart_intraday_rejects_prepared_cache_metadata_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-09T11-31-08+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_prepared_cache",
        lambda _path: {
            "pick_date": "2026-04-08",
            "prepared_by_symbol": {
                "000001.SZ": pd.DataFrame(
                    [
                        {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                    ]
                )
            },
            "metadata": {
                "b1_config": cli.DEFAULT_B1_CONFIG,
                "turnover_window": cli.DEFAULT_TURNOVER_WINDOW,
                "weekly_ma_periods": cli.DEFAULT_WEEKLY_MA_PERIODS,
                "max_vol_lookback": cli.DEFAULT_MAX_VOL_LOOKBACK,
                "mode": "intraday_snapshot",
                "run_id": "2026-04-09T11-31-08+08-00",
            },
        },
    )

    result = runner.invoke(app, ["chart", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code != 0
    assert "prepared intraday cache metadata mismatch" in result.stderr.lower()


def test_review_writes_summary_json(tmp_path: Path) -> None:
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
    chart_dir = runtime_root / "charts" / "2026-04-01"
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_symbol_history(
        connection: object,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        assert symbol == "000001.SZ"
        assert start_date == "2025-03-31"
        assert end_date == "2026-04-01"
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
                "trade_date": pd.to_datetime(["2026-03-28", "2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.6, 10.9],
                "low": [9.9, 10.1, 10.3],
                "close": [10.2, 10.5, 10.8],
                "vol": [100.0, 120.0, 150.0],
            }
        )

    from stock_select import cli

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_symbol_history = fake_fetch_symbol_history  # type: ignore[assignment]

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert (runtime_root / "reviews" / "2026-04-01" / "summary.json").exists()
    assert (runtime_root / "reviews" / "2026-04-01" / "llm_review_tasks.json").exists()
    review = json.loads((runtime_root / "reviews" / "2026-04-01" / "000001.SZ.json").read_text(encoding="utf-8"))
    tasks = json.loads((runtime_root / "reviews" / "2026-04-01" / "llm_review_tasks.json").read_text(encoding="utf-8"))
    assert review["code"] == "000001.SZ"
    assert review["review_mode"] == "baseline_local"
    assert review["baseline_review"]["review_type"] == "baseline"
    assert review["llm_review"] is None
    assert tasks["pick_date"] == "2026-04-01"
    assert tasks["prompt_path"].endswith(".agents/skills/stock-select/references/prompt.md")
    assert tasks["tasks"][0]["code"] == "000001.SZ"
    assert tasks["tasks"][0]["rank"] == 1
    assert tasks["tasks"][0]["baseline_score"] == review["total_score"]
    assert tasks["tasks"][0]["baseline_verdict"] == review["verdict"]
    assert "total_score" in review
    assert "[review] candidate 1/1 code=000001.SZ" in result.stderr
    assert "[review] done reviewed=1 failures=0" in result.stderr


def test_review_intraday_uses_latest_intraday_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / "2026-04-09T11-31-08+08-00"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / "2026-04-09T10-00-00+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T10-00-00+08-00",
                "candidates": [{"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / "2026-04-09T11-31-08+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "trade_date": "2026-04-09",
                "fetched_at": "2026-04-09T11-31-08+08-00",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_intraday_prepared_cache",
        lambda current_runtime_root, *, run_id, trade_date: (
            {
                "000001.SZ": pd.DataFrame(
                    [
                        {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                        {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
                    ]
                )
            }
            if current_runtime_root == runtime_root
            and run_id == "2026-04-09T11-31-08+08-00"
            and trade_date == "2026-04-09"
            else pytest.fail("review did not request the latest intraday prepared cache")
        ),
    )
    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("review --intraday should not connect to the database"))
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda *args, **kwargs: pytest.fail("review --intraday should not fetch symbol history"),
    )

    def fake_review_symbol_history(
        *,
        code: str,
        pick_date: str,
        history: pd.DataFrame,
        chart_path: str,
    ) -> dict[str, object]:
        assert code == "000001.SZ"
        assert pick_date == "2026-04-09"
        assert Path(chart_path) == chart_dir / "000001.SZ_day.png"
        assert history.to_dict(orient="records") == [
            {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
            {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
        ]
        return {
            "review_type": "baseline",
            "total_score": 4.2,
            "signal_type": "trend_start",
            "verdict": "PASS",
            "comment": "intraday baseline",
        }

    monkeypatch.setattr(cli, "review_symbol_history", fake_review_symbol_history)
    monkeypatch.setattr(
        cli,
        "build_review_result",
        lambda **kwargs: {
            "code": kwargs["code"],
            "pick_date": kwargs["pick_date"],
            "chart_path": kwargs["chart_path"],
            "review_mode": "baseline_local",
            "baseline_review": kwargs["baseline_review"],
            "llm_review": None,
            "total_score": kwargs["baseline_review"]["total_score"],
            "signal_type": kwargs["baseline_review"]["signal_type"],
            "verdict": kwargs["baseline_review"]["verdict"],
            "comment": kwargs["baseline_review"]["comment"],
        },
    )
    monkeypatch.setattr(
        cli,
        "build_review_payload",
        lambda **kwargs: {
            "code": kwargs["code"],
            "pick_date": kwargs["pick_date"],
            "chart_path": kwargs["chart_path"],
            "rubric_path": kwargs["rubric_path"],
        },
    )
    monkeypatch.setattr(
        cli,
        "summarize_reviews",
        lambda pick_date, method, reviews, min_score, failures: {
            "pick_date": pick_date,
            "method": method,
            "reviewed_count": len(reviews),
            "recommendations": [{"code": reviews[0]["code"]}] if reviews else [],
            "excluded": [],
            "failures": failures,
        },
    )

    result = runner.invoke(app, ["review", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code == 0
    assert (runtime_root / "reviews" / "2026-04-09T11-31-08+08-00" / "summary.json").exists()


def test_review_intraday_rejects_prepared_cache_metadata_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / "2026-04-09T11-31-08+08-00"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / "2026-04-09T11-31-08+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_prepared_cache",
        lambda _path: {
            "pick_date": "2026-04-09",
            "prepared_by_symbol": {
                "000001.SZ": pd.DataFrame(
                    [
                        {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                    ]
                )
            },
            "metadata": {
                "b1_config": cli.DEFAULT_B1_CONFIG,
                "turnover_window": cli.DEFAULT_TURNOVER_WINDOW,
                "weekly_ma_periods": cli.DEFAULT_WEEKLY_MA_PERIODS,
                "max_vol_lookback": cli.DEFAULT_MAX_VOL_LOOKBACK,
                "mode": "intraday_snapshot",
                "run_id": "2026-04-09T10-00-00+08-00",
            },
        },
    )

    result = runner.invoke(app, ["review", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code != 0
    assert "prepared intraday cache metadata mismatch" in result.stderr.lower()


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

    def fake_fetch_symbol_history(
        connection: object,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        assert symbol == "000001.SZ"
        assert start_date == "2025-03-31"
        assert end_date == "2026-04-01"
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "trade_date": pd.to_datetime(["2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2],
                "high": [10.5, 10.8],
                "low": [9.9, 10.1],
                "close": [10.4, 10.7],
                "vol": [100.0, 120.0],
            }
        )

    def fake_export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
        assert code == "000001.SZ"
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
        out_path.write_bytes(b"png")
        return out_path

    from stock_select import cli

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]
    cli.fetch_symbol_history = fake_fetch_symbol_history  # type: ignore[assignment]
    cli.export_daily_chart = fake_export_daily_chart  # type: ignore[assignment]

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
    assert "[run] step=screen start" in result.stderr
    assert "[run] step=screen done" in result.stderr
    assert "[run] step=chart start" in result.stderr
    assert "[run] step=review done" in result.stderr
    assert "elapsed=" in result.stderr


def test_run_intraday_rejects_pick_date(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-09",
            "--intraday",
            "--runtime-root",
            str(tmp_path / "runtime"),
        ],
    )

    assert result.exit_code != 0
    assert "mutually exclusive" in result.stderr


def test_run_intraday_chains_intraday_steps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    calls: list[tuple[str, object | None]] = []

    def fake_screen_intraday_impl(
        *,
        dsn: str | None,
        tushare_token: str | None,
        runtime_root: Path,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("screen", tushare_token))
        assert dsn == "postgresql://example"
        assert tushare_token == "token"
        assert runtime_root == tmp_path / "runtime"
        return runtime_root / "candidates" / "2026-04-09T11-31-08-123456+08-00.json"

    def fake_chart_intraday_impl(
        *,
        runtime_root: Path,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("chart", None))
        assert runtime_root == tmp_path / "runtime"
        return runtime_root / "charts" / "2026-04-09T11-31-08-123456+08-00"

    def fake_review_intraday_impl(
        *,
        method: str,
        runtime_root: Path,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("review", method))
        assert runtime_root == tmp_path / "runtime"
        return runtime_root / "reviews" / "2026-04-09T11-31-08-123456+08-00" / "summary.json"

    monkeypatch.setattr(cli, "_screen_intraday_impl", fake_screen_intraday_impl)
    monkeypatch.setattr(cli, "_chart_intraday_impl", fake_chart_intraday_impl)
    monkeypatch.setattr(cli, "_review_intraday_impl", fake_review_intraday_impl)

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--intraday",
            "--dsn",
            "postgresql://example",
            "--tushare-token",
            "token",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        ("screen", "token"),
        ("chart", None),
        ("review", "b1"),
    ]
    stdout_lines = result.stdout.strip().splitlines()
    assert stdout_lines == [
        str(runtime_root / "candidates" / "2026-04-09T11-31-08-123456+08-00.json"),
        str(runtime_root / "charts" / "2026-04-09T11-31-08-123456+08-00"),
        str(runtime_root / "reviews" / "2026-04-09T11-31-08-123456+08-00" / "summary.json"),
    ]
    assert "[run] step=screen start" in result.stderr
    assert "[run] step=chart start" in result.stderr
    assert "[run] step=review done" in result.stderr


def test_review_merge_combines_baseline_and_llm_results(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-01"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "000001.SZ.json").write_text(
        json.dumps(
            {
                "code": "000001.SZ",
                "pick_date": "2026-04-01",
                "chart_path": str(runtime_root / "charts" / "2026-04-01" / "000001.SZ_day.png"),
                "review_mode": "baseline_local",
                "llm_review": None,
                "baseline_review": {
                    "review_type": "baseline",
                    "total_score": 3.4,
                    "signal_type": "rebound",
                    "verdict": "WATCH",
                    "comment": "baseline",
                },
                "total_score": 3.4,
                "signal_type": "rebound",
                "verdict": "WATCH",
                "comment": "baseline",
            }
        ),
        encoding="utf-8",
    )
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "reviewed_count": 1,
                "recommendations": [],
                "excluded": ["placeholder"],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    (review_dir / "llm_review_results").mkdir(parents=True, exist_ok=True)
    (review_dir / "llm_review_results" / "000001.SZ.json").write_text(
        json.dumps(
            {
                "trend_reasoning": "趋势向上",
                "position_reasoning": "位置中位",
                "volume_reasoning": "量价配合良好",
                "abnormal_move_reasoning": "前期有异动",
                "signal_reasoning": "更像主升启动",
                "scores": {
                    "trend_structure": 5,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                },
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "llm",
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "review-merge",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    merged = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    assert merged["review_mode"] == "merged"
    assert merged["llm_review"]["verdict"] == "PASS"
    assert merged["final_score"] == 4.12
    assert merged["total_score"] == 4.12
    assert merged["verdict"] == "PASS"
    assert summary["recommendations"][0]["code"] == "000001.SZ"
    assert "[review-merge] merged reviews=1 failures=0" in result.stderr


def test_review_merge_can_limit_merge_to_selected_codes(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-01"
    review_dir.mkdir(parents=True, exist_ok=True)
    for code in ("000001.SZ", "000002.SZ"):
        (review_dir / f"{code}.json").write_text(
            json.dumps(
                {
                    "code": code,
                    "pick_date": "2026-04-01",
                    "chart_path": str(runtime_root / "charts" / "2026-04-01" / f"{code}_day.png"),
                    "review_mode": "baseline_local",
                    "llm_review": None,
                    "baseline_review": {
                        "review_type": "baseline",
                        "total_score": 3.4,
                        "signal_type": "rebound",
                        "verdict": "WATCH",
                        "comment": "baseline",
                    },
                    "total_score": 3.4,
                    "signal_type": "rebound",
                    "verdict": "WATCH",
                    "comment": "baseline",
                }
            ),
            encoding="utf-8",
        )
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "reviewed_count": 2,
                "recommendations": [],
                "excluded": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    (review_dir / "llm_review_results").mkdir(parents=True, exist_ok=True)
    (review_dir / "llm_review_results" / "000001.SZ.json").write_text(
        json.dumps(
            {
                "trend_reasoning": "趋势向上",
                "position_reasoning": "位置中位",
                "volume_reasoning": "量价配合良好",
                "abnormal_move_reasoning": "前期有异动",
                "signal_reasoning": "更像主升启动",
                "scores": {
                    "trend_structure": 5,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                },
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "llm",
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "review-merge",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--codes",
            "000001.SZ",
        ],
    )

    assert result.exit_code == 0
    merged = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    untouched = json.loads((review_dir / "000002.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    assert merged["review_mode"] == "merged"
    assert untouched["review_mode"] == "baseline_local"
    assert summary["failures"] == []
    assert "[review-merge] merged reviews=2 failures=0" in result.stderr


def test_review_merge_selected_codes_does_not_fail_missing_unselected_results(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-01"
    review_dir.mkdir(parents=True, exist_ok=True)
    for code in ("000001.SZ", "000002.SZ"):
        (review_dir / f"{code}.json").write_text(
            json.dumps(
                {
                    "code": code,
                    "pick_date": "2026-04-01",
                    "chart_path": str(runtime_root / "charts" / "2026-04-01" / f"{code}_day.png"),
                    "review_mode": "baseline_local",
                    "llm_review": None,
                    "baseline_review": {
                        "review_type": "baseline",
                        "total_score": 3.4,
                        "signal_type": "rebound",
                        "verdict": "WATCH",
                        "comment": "baseline",
                    },
                    "total_score": 3.4,
                    "signal_type": "rebound",
                    "verdict": "WATCH",
                    "comment": "baseline",
                }
            ),
            encoding="utf-8",
        )
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "reviewed_count": 2,
                "recommendations": [],
                "excluded": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    (review_dir / "llm_review_results").mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "review-merge",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--codes",
            "000001.SZ",
        ],
    )

    assert result.exit_code == 0
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["failures"] == [{"code": "000001.SZ", "reason": f"LLM review result not found: {review_dir / 'llm_review_results' / '000001.SZ.json'}"}]


def test_render_html_creates_zip_with_summary_and_charts(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-01"
    chart_dir = runtime_root / "charts" / "2026-04-01"
    review_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    (chart_dir / "000001.SZ_day.png").write_bytes(b"png-bytes")
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "reviewed_count": 1,
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "pick_date": "2026-04-01",
                        "chart_path": str(chart_dir / "000001.SZ_day.png"),
                        "review_mode": "merged",
                        "llm_review": {
                            "trend_reasoning": "趋势向上",
                            "position_reasoning": "位置适中",
                            "volume_reasoning": "量价正常",
                            "abnormal_move_reasoning": "前期异动",
                            "signal_reasoning": "主升启动",
                            "trend_structure": 4,
                            "price_position": 3,
                            "volume_behavior": 4,
                            "previous_abnormal_move": 4,
                            "total_score": 3.8,
                            "signal_type": "trend_start",
                            "verdict": "WATCH",
                            "comment": "llm",
                        },
                        "baseline_review": {
                            "trend_structure": 5,
                            "price_position": 4,
                            "volume_behavior": 5,
                            "previous_abnormal_move": 5,
                            "total_score": 4.8,
                            "signal_type": "trend_start",
                            "verdict": "PASS",
                            "comment": "baseline",
                        },
                        "total_score": 4.2,
                        "final_score": 4.2,
                        "signal_type": "trend_start",
                        "verdict": "PASS",
                        "comment": "merged comment",
                    }
                ],
                "excluded": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_connect", lambda dsn: object())
    monkeypatch.setattr(cli, "fetch_instrument_names", lambda connection, symbols: {"000001.SZ": "平安银行"})

    result = runner.invoke(
        app,
        [
            "render-html",
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
    zip_path = Path(result.stdout.strip())
    assert zip_path.name == "summary-package.zip"
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "summary.html" in names
        assert "summary.json" in names
        assert "charts/000001.SZ_day.png" in names
        html_text = archive.read("summary.html").decode("utf-8")
        assert "000001.SZ" in html_text
        assert "平安银行" in html_text
        assert "merged comment" in html_text


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


def test_screen_uses_env_dsn_when_option_missing(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    def fake_connect(dsn: str) -> object:
        assert dsn == "postgresql://from-env"
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

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://from-env")

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


def test_screen_uses_dotenv_dsn_when_option_and_env_missing(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    env_path = tmp_path / ".env"
    env_path.write_text("POSTGRES_DSN=postgresql://from-dotenv\n", encoding="utf-8")

    def fake_connect(dsn: str) -> object:
        assert dsn == "postgresql://from-dotenv"
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

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.chdir(tmp_path)

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


def test_screen_option_dsn_overrides_dotenv(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    env_path = tmp_path / ".env"
    env_path.write_text("POSTGRES_DSN=postgresql://from-dotenv\n", encoding="utf-8")

    def fake_connect(dsn: str) -> object:
        assert dsn == "postgresql://from-option"
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

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.chdir(tmp_path)

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
            "postgresql://from-option",
        ],
    )

    assert result.exit_code == 0


def test_screen_can_disable_progress_output(tmp_path: Path) -> None:
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
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert result.stderr == ""


def test_screen_emits_filter_breakdown_stats(tmp_path: Path) -> None:
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
        return {"000001.SZ": pd.DataFrame()}

    from stock_select import cli

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]

    original_run = cli.run_b1_screen_with_stats
    original_pool = cli.build_top_turnover_pool

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["000001.SZ"]
        assert prepared_by_symbol["000001.SZ"].empty
        assert pick_date == pd.Timestamp("2026-04-01")
        assert config == {"j_threshold": 15.0, "j_q_threshold": 0.10}
        return (
            [{"code": "000001.SZ", "pick_date": "2026-04-01", "close": 10.6, "turnover_n": 1030.0}],
            {
                "total_symbols": 10,
                "eligible": 8,
                "fail_j": 2,
                "fail_insufficient_history": 3,
                "fail_close_zxdkx": 1,
                "fail_zxdq_zxdkx": 2,
                "fail_weekly_ma": 1,
                "fail_max_vol": 1,
                "selected": 1,
            },
        )

    def fake_build_top_turnover_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        assert top_m == 5000
        return {pd.Timestamp("2026-04-01"): ["000001.SZ"]}

    cli.run_b1_screen_with_stats = fake_run_b1_screen_with_stats  # type: ignore[assignment]
    cli.build_top_turnover_pool = fake_build_top_turnover_pool  # type: ignore[assignment]

    try:
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
    finally:
        cli.run_b1_screen_with_stats = original_run  # type: ignore[assignment]
        cli.build_top_turnover_pool = original_pool  # type: ignore[assignment]

    assert result.exit_code == 0
    assert (
        "[screen] breakdown total_symbols=10 eligible=8 fail_j=2 fail_insufficient_history=3 "
        "fail_close_zxdkx=1 "
        "fail_zxdq_zxdkx=2 fail_weekly_ma=1 fail_max_vol=1 selected=1"
    ) in result.stderr


def test_prepare_screen_data_uses_reference_b1_windows() -> None:
    importlib.reload(cli)

    market = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02"]),
            "open": [10.0, 10.2],
            "high": [10.5, 10.6],
            "low": [9.9, 10.1],
            "close": [10.4, 10.5],
            "vol": [100.0, 120.0],
        }
    )

    turnover_windows: list[int] = []
    weekly_periods: list[tuple[int, int, int]] = []

    def fake_turnover(df: pd.DataFrame, window: int) -> pd.Series:
        turnover_windows.append(window)
        return pd.Series([1000.0] * len(df), index=df.index)

    def fake_kdj(df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"J": [10.0] * len(df)}, index=df.index)

    def fake_zx(df: pd.DataFrame):
        return pd.Series([10.3] * len(df), index=df.index), pd.Series([10.1] * len(df), index=df.index)

    def fake_weekly(df: pd.DataFrame, ma_periods: tuple[int, int, int] = (20, 60, 120)) -> pd.Series:
        weekly_periods.append(ma_periods)
        return pd.Series([True] * len(df), index=df.index)

    original_turnover = cli.compute_turnover_n
    original_kdj = cli.compute_kdj
    original_zx = cli.compute_zx_lines
    original_weekly = cli.compute_weekly_ma_bull
    original_max_vol = cli.max_vol_not_bearish

    cli.compute_turnover_n = fake_turnover  # type: ignore[assignment]
    cli.compute_kdj = fake_kdj  # type: ignore[assignment]
    cli.compute_zx_lines = fake_zx  # type: ignore[assignment]
    cli.compute_weekly_ma_bull = fake_weekly  # type: ignore[assignment]
    cli.max_vol_not_bearish = lambda df, lookback: pd.Series([True] * len(df), index=df.index)  # type: ignore[assignment]

    try:
        prepared = cli._prepare_screen_data(market)
    finally:
        cli.compute_turnover_n = original_turnover  # type: ignore[assignment]
        cli.compute_kdj = original_kdj  # type: ignore[assignment]
        cli.compute_zx_lines = original_zx  # type: ignore[assignment]
        cli.compute_weekly_ma_bull = original_weekly  # type: ignore[assignment]
        cli.max_vol_not_bearish = original_max_vol  # type: ignore[assignment]

    assert list(prepared) == ["000001.SZ"]
    assert turnover_windows == [43]
    assert weekly_periods == [(10, 20, 30)]


def test_prepared_cache_round_trip(tmp_path: Path) -> None:
    cache_path = tmp_path / "prepared" / "2026-04-01.pkl"
    prepared_by_symbol = {
        "AAA.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "turnover_n": [100.0],
                "J": [10.0],
            }
        )
    }

    cli._write_prepared_cache(
        cache_path,
        pick_date="2026-04-01",
        start_date="2025-03-31",
        end_date="2026-04-01",
        prepared_by_symbol=prepared_by_symbol,
    )

    payload = cli._load_prepared_cache(cache_path)

    assert payload["pick_date"] == "2026-04-01"
    assert payload["start_date"] == "2025-03-31"
    assert payload["end_date"] == "2026-04-01"
    pd.testing.assert_frame_equal(payload["prepared_by_symbol"]["AAA.SZ"], prepared_by_symbol["AAA.SZ"])


def test_screen_uses_reference_b1_defaults_and_liquidity_pool(tmp_path: Path) -> None:
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
                "ts_code": ["AAA.SZ", "BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-01", "2026-04-01"]),
                "open": [10.0, 11.0],
                "high": [10.5, 11.5],
                "low": [9.9, 10.9],
                "close": [10.4, 11.4],
                "vol": [100.0, 120.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "turnover_n": [100.0],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "close": [10.6],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "turnover_n": [200.0],
                    "J": [10.0],
                    "zxdq": [11.5],
                    "zxdkx": [11.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "close": [11.6],
                }
            ),
        }

    def fake_pool(prepared_by_symbol: dict[str, pd.DataFrame], top_m: int):
        assert top_m == 5000
        assert sorted(prepared_by_symbol) == ["AAA.SZ", "BBB.SZ"]
        return {pd.Timestamp("2026-04-01"): ["BBB.SZ"]}

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["BBB.SZ"]
        assert pick_date == pd.Timestamp("2026-04-01")
        assert config == {"j_threshold": 15.0, "j_q_threshold": 0.10}
        return (
            [{"code": "BBB.SZ", "pick_date": "2026-04-01", "close": 11.6, "turnover_n": 200.0}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_j": 0,
                "fail_insufficient_history": 0,
                "fail_close_zxdkx": 0,
                "fail_zxdq_zxdkx": 0,
                "fail_weekly_ma": 0,
                "fail_max_vol": 0,
                "selected": 1,
            },
        )

    original_connect = cli._connect
    original_fetch = cli.fetch_daily_window
    original_prepare = cli._prepare_screen_data
    original_pool = cli.build_top_turnover_pool
    original_run = cli.run_b1_screen_with_stats

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]
    cli.build_top_turnover_pool = fake_pool  # type: ignore[assignment]
    cli.run_b1_screen_with_stats = fake_run_b1_screen_with_stats  # type: ignore[assignment]

    try:
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
    finally:
        cli._connect = original_connect  # type: ignore[assignment]
        cli.fetch_daily_window = original_fetch  # type: ignore[assignment]
        cli._prepare_screen_data = original_prepare  # type: ignore[assignment]
        cli.build_top_turnover_pool = original_pool  # type: ignore[assignment]
        cli.run_b1_screen_with_stats = original_run  # type: ignore[assignment]

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / "2026-04-01.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["BBB.SZ"]


def test_screen_reuses_existing_non_empty_candidate_file_without_recomputing(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / "2026-04-01.json"
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "candidates": [{"code": "AAA.SZ", "pick_date": "2026-04-01", "close": 10.5, "turnover_n": 100.0}],
            }
        ),
        encoding="utf-8",
    )

    original_connect = cli._connect
    original_fetch = cli.fetch_daily_window
    original_prepare = cli._prepare_screen_data

    def fail_connect(_: str) -> object:
        raise AssertionError("screen should not connect when candidate output is reusable")

    def fail_fetch(*args, **kwargs):
        raise AssertionError("screen should not fetch market window when candidate output is reusable")

    def fail_prepare(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        raise AssertionError("screen should not prepare data when candidate output is reusable")

    cli._connect = fail_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fail_fetch  # type: ignore[assignment]
    cli._prepare_screen_data = fail_prepare  # type: ignore[assignment]

    try:
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
    finally:
        cli._connect = original_connect  # type: ignore[assignment]
        cli.fetch_daily_window = original_fetch  # type: ignore[assignment]
        cli._prepare_screen_data = original_prepare  # type: ignore[assignment]

    assert result.exit_code == 0
    assert result.stdout.strip() == str(candidate_path)
    assert "[screen] reuse candidates path=" in result.stderr


def test_screen_ignores_existing_empty_candidate_file_and_recomputes(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-01.json").write_text(
        json.dumps({"pick_date": "2026-04-01", "method": "b1", "candidates": []}),
        encoding="utf-8",
    )

    calls = {"connect": 0, "prepare": 0}

    def fake_connect(_: str) -> object:
        calls["connect"] += 1
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
                "ts_code": ["AAA.SZ"],
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.9],
                "close": [10.4],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        calls["prepare"] += 1
        return {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "turnover_n": [100.0],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "close": [10.6],
                }
            )
        }

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        return (
            [{"code": "AAA.SZ", "pick_date": "2026-04-01", "close": 10.6, "turnover_n": 100.0}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_j": 0,
                "fail_insufficient_history": 0,
                "fail_close_zxdkx": 0,
                "fail_zxdq_zxdkx": 0,
                "fail_weekly_ma": 0,
                "fail_max_vol": 0,
                "selected": 1,
            },
        )

    original_connect = cli._connect
    original_fetch = cli.fetch_daily_window
    original_prepare = cli._prepare_screen_data
    original_run = cli.run_b1_screen_with_stats

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]
    cli.run_b1_screen_with_stats = fake_run_b1_screen_with_stats  # type: ignore[assignment]

    try:
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
    finally:
        cli._connect = original_connect  # type: ignore[assignment]
        cli.fetch_daily_window = original_fetch  # type: ignore[assignment]
        cli._prepare_screen_data = original_prepare  # type: ignore[assignment]
        cli.run_b1_screen_with_stats = original_run  # type: ignore[assignment]

    assert result.exit_code == 0
    assert calls == {"connect": 1, "prepare": 1}


def test_screen_reuses_prepared_cache_when_candidate_output_missing(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    prepared_by_symbol = {
        "BBB.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "turnover_n": [200.0],
                "J": [10.0],
                "zxdq": [11.5],
                "zxdkx": [11.2],
                "weekly_ma_bull": [True],
                "max_vol_not_bearish": [True],
                "close": [11.6],
            }
        )
    }
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-01.pkl",
        pick_date="2026-04-01",
        start_date="2025-03-31",
        end_date="2026-04-01",
        prepared_by_symbol=prepared_by_symbol,
    )

    original_connect = cli._connect
    original_fetch = cli.fetch_daily_window
    original_prepare = cli._prepare_screen_data
    original_run = cli.run_b1_screen_with_stats

    def fail_connect(_: str) -> object:
        raise AssertionError("screen should not connect when prepared cache is reusable")

    def fail_fetch(*args, **kwargs):
        raise AssertionError("screen should not fetch market window when prepared cache is reusable")

    def fail_prepare(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        raise AssertionError("screen should not prepare data when prepared cache is reusable")

    def fake_run_b1_screen_with_stats(
        prepared_subset: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_subset) == ["BBB.SZ"]
        return (
            [{"code": "BBB.SZ", "pick_date": "2026-04-01", "close": 11.6, "turnover_n": 200.0}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_j": 0,
                "fail_insufficient_history": 0,
                "fail_close_zxdkx": 0,
                "fail_zxdq_zxdkx": 0,
                "fail_weekly_ma": 0,
                "fail_max_vol": 0,
                "selected": 1,
            },
        )

    cli._connect = fail_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fail_fetch  # type: ignore[assignment]
    cli._prepare_screen_data = fail_prepare  # type: ignore[assignment]
    cli.run_b1_screen_with_stats = fake_run_b1_screen_with_stats  # type: ignore[assignment]

    try:
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
    finally:
        cli._connect = original_connect  # type: ignore[assignment]
        cli.fetch_daily_window = original_fetch  # type: ignore[assignment]
        cli._prepare_screen_data = original_prepare  # type: ignore[assignment]
        cli.run_b1_screen_with_stats = original_run  # type: ignore[assignment]

    assert result.exit_code == 0
    assert "[screen] reuse prepared path=" in result.stderr


def test_screen_recompute_bypasses_candidate_and_prepared_reuse(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-01.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "candidates": [{"code": "OLD.SZ", "pick_date": "2026-04-01", "close": 9.9, "turnover_n": 50.0}],
            }
        ),
        encoding="utf-8",
    )
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-01.pkl",
        pick_date="2026-04-01",
        start_date="2025-03-31",
        end_date="2026-04-01",
        prepared_by_symbol={"OLD.SZ": pd.DataFrame({"trade_date": pd.to_datetime(["2026-04-01"]), "turnover_n": [50.0]})},
    )

    calls = {"connect": 0, "prepare": 0}

    def fake_connect(_: str) -> object:
        calls["connect"] += 1
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
                "ts_code": ["NEW.SZ"],
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "open": [11.0],
                "high": [11.5],
                "low": [10.9],
                "close": [11.4],
                "vol": [120.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        calls["prepare"] += 1
        return {
            "NEW.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "turnover_n": [200.0],
                    "J": [10.0],
                    "zxdq": [11.5],
                    "zxdkx": [11.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "close": [11.6],
                }
            )
        }

    def fake_run_b1_screen_with_stats(
        prepared_subset: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        return (
            [{"code": "NEW.SZ", "pick_date": "2026-04-01", "close": 11.6, "turnover_n": 200.0}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_j": 0,
                "fail_insufficient_history": 0,
                "fail_close_zxdkx": 0,
                "fail_zxdq_zxdkx": 0,
                "fail_weekly_ma": 0,
                "fail_max_vol": 0,
                "selected": 1,
            },
        )

    original_connect = cli._connect
    original_fetch = cli.fetch_daily_window
    original_prepare = cli._prepare_screen_data
    original_run = cli.run_b1_screen_with_stats

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]
    cli.run_b1_screen_with_stats = fake_run_b1_screen_with_stats  # type: ignore[assignment]

    try:
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
                "--recompute",
            ],
        )
    finally:
        cli._connect = original_connect  # type: ignore[assignment]
        cli.fetch_daily_window = original_fetch  # type: ignore[assignment]
        cli._prepare_screen_data = original_prepare  # type: ignore[assignment]
        cli.run_b1_screen_with_stats = original_run  # type: ignore[assignment]

    assert result.exit_code == 0
    assert calls == {"connect": 1, "prepare": 1}
    payload = json.loads((candidate_dir / "2026-04-01.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["NEW.SZ"]


def test_screen_intraday_rejects_pick_date(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-09",
            "--intraday",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "mutually exclusive" in result.stderr


def test_screen_intraday_rejects_weekend_execution(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-11 10:00:00", tz="Asia/Shanghai"),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--intraday",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "weekend" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


def test_screen_intraday_requires_tushare_token(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 10:00:00", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--intraday",
            "--runtime-root",
            str(tmp_path / "runtime"),
        ],
    )

    assert result.exit_code != 0
    assert "tushare token" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()


@pytest.mark.parametrize(
    "message",
    [
        "Tushare package is required for intraday mode.",
        "Failed to fetch Tushare rt_k snapshot: boom",
        "Tushare rt_k returned no usable rows.",
    ],
)
def test_screen_intraday_surfaces_snapshot_errors_as_cli_messages(
    monkeypatch,
    tmp_path: Path,
    message: str,
) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 10:00:00.123456", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_resolve_tushare_token", lambda token: "token")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_resolve_previous_trade_date", lambda _connection, trade_date: "2026-04-08")
    monkeypatch.setattr(
        cli,
        "_fetch_rt_k_snapshot",
        lambda token, trade_date: (_ for _ in ()).throw(cli.IntradayUserError(message)),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--intraday",
            "--runtime-root",
            str(tmp_path / "runtime"),
        ],
    )

    assert result.exit_code != 0
    assert message in result.stderr
    assert "traceback" not in result.stderr.lower()


def test_format_intraday_run_id_is_filename_safe_and_microsecond_precise() -> None:
    run_id = cli._format_intraday_run_id(pd.Timestamp("2026-04-09 11:31:08.123456", tz="Asia/Shanghai"))

    assert run_id == "2026-04-09T11-31-08-123456+08-00"
    assert ":" not in run_id


@pytest.mark.parametrize(
    ("module_factory", "expected_message"),
    [
        (lambda: (_ for _ in ()).throw(ImportError("missing")), "Tushare package is required for intraday mode."),
        (
            lambda: SimpleNamespace(
                set_token=lambda _token: None,
                pro_api=lambda: SimpleNamespace(rt_k=lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
            ),
            "Failed to fetch Tushare rt_k snapshot: boom",
        ),
        (
            lambda: SimpleNamespace(
                set_token=lambda _token: None,
                pro_api=lambda: SimpleNamespace(rt_k=lambda: pd.DataFrame()),
            ),
            "Tushare rt_k returned no usable rows.",
        ),
    ],
)
def test_fetch_rt_k_snapshot_wraps_tushare_failures(monkeypatch, module_factory, expected_message: str) -> None:
    monkeypatch.setattr(cli, "_import_tushare_module", module_factory, raising=False)

    with pytest.raises(cli.IntradayUserError, match=expected_message):
        cli._fetch_rt_k_snapshot("token", "2026-04-09")


def test_screen_intraday_writes_timestamped_candidate_and_prepared(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    expected_run_id = "2026-04-09T11-31-08-123456+08-00"

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 11:31:08.123456", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.setattr(cli, "_resolve_tushare_token", lambda token: "token", raising=False)
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "_resolve_previous_trade_date",
        lambda _connection, trade_date: "2026-04-08",
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "_fetch_rt_k_snapshot",
        lambda token, trade_date: pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "trade_date": "2026-04-09",
                    "trade_time": "11:31:07",
                    "open": 12.1,
                    "high": 12.5,
                    "low": 12.0,
                    "close": 12.34,
                    "vol": 150.0,
                    "amount": 999.0,
                }
            ]
        ),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2026-04-08",
                    "open": 11.9,
                    "high": 12.1,
                    "low": 11.8,
                    "close": 12.0,
                    "vol": 120.0,
                }
            ]
        ),
    )
    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--intraday",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    candidate_path = runtime_root / "candidates" / f"{expected_run_id}.json"
    prepared_path = runtime_root / "prepared" / f"{expected_run_id}.pkl"
    assert candidate_path.exists()
    assert prepared_path.exists()

    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate_payload["run_id"] == expected_run_id
    assert candidate_payload["fetched_at"] == expected_run_id

    prepared_payload = pickle.loads(prepared_path.read_bytes())
    assert prepared_payload["metadata"]["mode"] == "intraday_snapshot"
    assert prepared_payload["metadata"]["source"] == "tushare_rt_k"
    assert prepared_payload["metadata"]["run_id"] == expected_run_id
    assert prepared_payload["metadata"]["previous_trade_date"] == "2026-04-08"
