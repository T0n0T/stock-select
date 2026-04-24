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


def _dribull_wave_stats(*, total_symbols: int, eligible: int, selected: int) -> dict[str, int]:
    return {
        "total_symbols": total_symbols,
        "eligible": eligible,
        "fail_recent_j": 0,
        "fail_insufficient_history": 0,
        "fail_support_ma25": 0,
        "fail_volume_shrink": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_ma60_trend": 0,
        "fail_ma144_distance": 0,
        "fail_weekly_wave": 0,
        "fail_daily_wave": 0,
        "fail_wave_combo": 0,
        "selected": selected,
    }


def _b1_screen_stats(*, total_symbols: int, eligible: int, selected: int, **overrides: int) -> dict[str, int]:
    stats = {
        "total_symbols": total_symbols,
        "eligible": eligible,
        "fail_j": 0,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_weekly_ma": 0,
        "fail_max_vol": 0,
        "fail_chg_cap": 0,
        "fail_v_shrink": 0,
        "fail_safe_mode": 0,
        "fail_lt_filter": 0,
        "selected": selected,
    }
    stats.update(overrides)
    return stats


def _eod_key(pick_date: str, method: str = "b1") -> str:
    return f"{pick_date}.{method}"


def _intraday_key(run_id: str, method: str = "b1") -> str:
    return f"{run_id}.{method}"


def test_default_runtime_root_uses_agents_skill_runtime() -> None:
    expected = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"

    assert cli._default_runtime_root() == expected


def test_b2_prompt_reference_exists_and_preserves_default_json_contract() -> None:
    references_dir = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "stock-select"
        / "references"
    )
    default_prompt = references_dir / "prompt.md"
    b2_prompt = references_dir / "prompt-b2.md"

    assert default_prompt.exists()
    assert b2_prompt.exists()

    content = b2_prompt.read_text(encoding="utf-8")

    assert "b2" in content.lower()
    assert "output json format must remain identical to the default prompt contract" in content.lower()


def test_validate_eod_pick_date_has_market_data_rejects_placeholder_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    market = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": pd.to_datetime(["2026-04-14", "2026-04-14"]),
            "open": [None, None],
            "high": [None, None],
            "low": [None, None],
            "close": [None, None],
            "vol": [None, None],
        }
    )

    monkeypatch.setattr(
        cli,
        "fetch_nth_latest_trade_date",
        lambda _connection, *, end_date, n: "2026-04-13",
    )

    with pytest.raises(cli.typer.BadParameter, match="incomplete end-of-day rows"):
        cli._validate_eod_pick_date_has_market_data(object(), market=market, pick_date="2026-04-14")


def test_screen_rejects_unknown_method() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["screen", "--method", "brick", "--pick-date", "2026-04-01"])

    assert result.exit_code != 0
    stderr = result.stderr.lower()
    assert "supported methods:" in stderr
    assert "dribull" in stderr


def test_analyze_symbol_requires_symbol(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["analyze-symbol", "--method", "b2", "--runtime-root", str(tmp_path)])

    assert result.exit_code != 0
    assert "--symbol" in result.stderr


@pytest.mark.parametrize("method", ["b1", "dribull", "hcr"])
def test_analyze_symbol_accepts_supported_non_b2_methods(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_impl(*, method: str, symbol: str, pick_date: str | None, dsn: str | None, runtime_root: Path, reporter):
        captured["method"] = method
        captured["symbol"] = symbol
        captured["pick_date"] = pick_date
        captured["runtime_root"] = runtime_root
        return tmp_path / f"{method}.json"

    monkeypatch.setattr(cli, "_analyze_symbol_impl", fake_impl)

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            method,
            "--symbol",
            "002350.SZ",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["method"] == method
    assert captured["symbol"] == "002350.SZ"
    assert captured["pick_date"] is None
    assert captured["runtime_root"] == tmp_path
    assert str(tmp_path / f"{method}.json") in result.stdout


def test_analyze_symbol_defaults_to_latest_trade_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_impl(*, method: str, symbol: str, pick_date: str | None, dsn: str | None, runtime_root: Path, reporter):
        captured["method"] = method
        captured["symbol"] = symbol
        captured["pick_date"] = pick_date
        captured["runtime_root"] = runtime_root
        return tmp_path / "result.json"

    monkeypatch.setattr(cli, "_analyze_symbol_impl", fake_impl)

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b2",
            "--symbol",
            "002350.SZ",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["pick_date"] is None
    assert str(tmp_path / "result.json") in result.stdout


def test_analyze_symbol_rejects_invalid_pick_date(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b2",
            "--symbol",
            "002350.SZ",
            "--pick-date",
            "not-a-date",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "yyyy-mm-dd" in result.stderr.lower()


def test_analyze_symbol_rejects_path_like_pick_date(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b2",
            "--symbol",
            "002350.SZ",
            "--pick-date",
            "../../escape",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "yyyy-mm-dd" in result.stderr.lower()


def test_analyze_symbol_rejects_noncanonical_pick_date(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b2",
            "--symbol",
            "002350.SZ",
            "--pick-date",
            "2026/04/21",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "yyyy-mm-dd" in result.stderr.lower()


def test_analyze_symbol_rejects_invalid_symbol_cleanly(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b2",
            "--symbol",
            "ABC",
            "--pick-date",
            "2026-04-21",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "canonical stock code" in result.stderr.lower()


def test_clean_requires_pick_date_or_intraday(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["clean", "--runtime-root", str(tmp_path)])

    assert result.exit_code != 0
    assert "either --pick-date or --intraday is required" in result.stderr.lower()


def test_clean_rejects_pick_date_with_intraday(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "clean",
            "--pick-date",
            "2026-04-10",
            "--intraday",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "--pick-date and --intraday are mutually exclusive" in result.stderr.lower()


def test_clean_pick_date_removes_eod_artifacts_only(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    charts_dir = runtime_root / "charts"
    reviews_dir = runtime_root / "reviews"
    prepared_dir = runtime_root / "prepared"

    candidate_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    (candidate_dir / f"{_eod_key('2026-04-10')}.json").write_text("{}", encoding="utf-8")
    (candidate_dir / f"{_eod_key('2026-04-10', 'b2')}.json").write_text("{}", encoding="utf-8")
    (candidate_dir / f"{_intraday_key('2026-04-10T10-00-00+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "trade_date": "2026-04-10",
                "run_id": "2026-04-10T10-00-00+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (charts_dir / _eod_key("2026-04-10")).mkdir(parents=True, exist_ok=True)
    (charts_dir / _eod_key("2026-04-10", "hcr")).mkdir(parents=True, exist_ok=True)
    (charts_dir / _intraday_key("2026-04-10T10-00-00+08-00")).mkdir(parents=True, exist_ok=True)
    (reviews_dir / _eod_key("2026-04-10")).mkdir(parents=True, exist_ok=True)
    (reviews_dir / _eod_key("2026-04-10", "dribull")).mkdir(parents=True, exist_ok=True)
    (reviews_dir / _intraday_key("2026-04-10T10-00-00+08-00")).mkdir(parents=True, exist_ok=True)
    cli._write_prepared_cache(
        prepared_dir / "2026-04-10.pkl",
        method="b1",
        pick_date="2026-04-10",
        start_date="2025-04-09",
        end_date="2026-04-10",
        prepared_by_symbol={},
    )
    cli._write_prepared_cache(
        prepared_dir / "2026-04-10.hcr.pkl",
        method="hcr",
        pick_date="2026-04-10",
        start_date="2025-04-09",
        end_date="2026-04-10",
        prepared_by_symbol={},
    )
    cli._write_prepared_cache(
        prepared_dir / "2026-04-10.intraday.pkl",
        method="b1",
        pick_date="2026-04-10",
        start_date="2025-04-09",
        end_date="2026-04-10",
        prepared_by_symbol={},
        metadata_overrides={"mode": "intraday_snapshot"},
    )

    result = runner.invoke(
        app,
        [
            "clean",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert not (candidate_dir / f"{_eod_key('2026-04-10')}.json").exists()
    assert not (candidate_dir / f"{_eod_key('2026-04-10', 'b2')}.json").exists()
    assert (candidate_dir / f"{_intraday_key('2026-04-10T10-00-00+08-00')}.json").exists()
    assert not (charts_dir / _eod_key("2026-04-10")).exists()
    assert not (charts_dir / _eod_key("2026-04-10", "hcr")).exists()
    assert (charts_dir / _intraday_key("2026-04-10T10-00-00+08-00")).exists()
    assert not (reviews_dir / _eod_key("2026-04-10")).exists()
    assert not (reviews_dir / _eod_key("2026-04-10", "dribull")).exists()
    assert (reviews_dir / _intraday_key("2026-04-10T10-00-00+08-00")).exists()
    assert not (prepared_dir / "2026-04-10.pkl").exists()
    assert not (prepared_dir / "2026-04-10.hcr.pkl").exists()
    assert (prepared_dir / "2026-04-10.intraday.pkl").exists()


def test_clean_intraday_removes_only_non_current_trade_date_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    charts_dir = runtime_root / "charts"
    reviews_dir = runtime_root / "reviews"
    prepared_dir = runtime_root / "prepared"

    candidate_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    old_run_id = "2026-04-21T14-30-00+08-00"
    current_run_id = "2026-04-22T10-15-00+08-00"

    (candidate_dir / f"{_intraday_key(old_run_id)}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "trade_date": "2026-04-21",
                "run_id": old_run_id,
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / f"{_intraday_key(current_run_id, 'b2')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b2",
                "trade_date": "2026-04-22",
                "run_id": current_run_id,
                "candidates": [{"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / f"{_eod_key('2026-04-21')}.json").write_text("{}", encoding="utf-8")
    (charts_dir / _intraday_key(old_run_id)).mkdir(parents=True, exist_ok=True)
    (charts_dir / _intraday_key(current_run_id, "b2")).mkdir(parents=True, exist_ok=True)
    (charts_dir / _intraday_key("2026-04-20T09-35-00+08-00", "hcr")).mkdir(parents=True, exist_ok=True)
    (reviews_dir / _intraday_key(old_run_id)).mkdir(parents=True, exist_ok=True)
    (reviews_dir / _intraday_key(current_run_id, "b2")).mkdir(parents=True, exist_ok=True)
    (reviews_dir / _intraday_key("2026-04-20T09-35-00+08-00", "hcr")).mkdir(parents=True, exist_ok=True)
    cli._write_prepared_cache(
        prepared_dir / "2026-04-21.intraday.pkl",
        method="b1",
        pick_date="2026-04-21",
        start_date="2025-04-20",
        end_date="2026-04-21",
        prepared_by_symbol={},
        metadata_overrides={"mode": "intraday_snapshot"},
    )
    cli._write_prepared_cache(
        prepared_dir / "2026-04-21.intraday.hcr.pkl",
        method="hcr",
        pick_date="2026-04-21",
        start_date="2025-04-20",
        end_date="2026-04-21",
        prepared_by_symbol={},
        metadata_overrides={"mode": "intraday_snapshot"},
    )
    cli._write_prepared_cache(
        prepared_dir / "2026-04-22.intraday.pkl",
        method="b1",
        pick_date="2026-04-22",
        start_date="2025-04-21",
        end_date="2026-04-22",
        prepared_by_symbol={},
        metadata_overrides={"mode": "intraday_snapshot"},
    )
    cli._write_prepared_cache(
        prepared_dir / "2026-04-22.pkl",
        method="b1",
        pick_date="2026-04-22",
        start_date="2025-04-21",
        end_date="2026-04-22",
        prepared_by_symbol={},
    )

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-22 10:30:00", tz="Asia/Shanghai"),
        raising=False,
    )

    result = runner.invoke(app, ["clean", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code == 0
    assert not (candidate_dir / f"{_intraday_key(old_run_id)}.json").exists()
    assert (candidate_dir / f"{_intraday_key(current_run_id, 'b2')}.json").exists()
    assert (candidate_dir / f"{_eod_key('2026-04-21')}.json").exists()
    assert not (charts_dir / _intraday_key(old_run_id)).exists()
    assert (charts_dir / _intraday_key(current_run_id, "b2")).exists()
    assert not (charts_dir / _intraday_key("2026-04-20T09-35-00+08-00", "hcr")).exists()
    assert not (reviews_dir / _intraday_key(old_run_id)).exists()
    assert (reviews_dir / _intraday_key(current_run_id, "b2")).exists()
    assert not (reviews_dir / _intraday_key("2026-04-20T09-35-00+08-00", "hcr")).exists()
    assert not (prepared_dir / "2026-04-21.intraday.pkl").exists()
    assert not (prepared_dir / "2026-04-21.intraday.hcr.pkl").exists()
    assert (prepared_dir / "2026-04-22.intraday.pkl").exists()
    assert (prepared_dir / "2026-04-22.pkl").exists()


def test_analyze_symbol_rejects_path_like_symbol_cleanly(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b2",
            "--symbol",
            "../../escape.SZ",
            "--pick-date",
            "2026-04-21",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "symbol" in result.stderr.lower()


def test_analyze_symbol_impl_writes_result_under_ad_hoc_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-21")
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol] * 3,
                "trade_date": ["2026-04-17", "2026-04-18", "2026-04-21"],
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.5, 10.8],
                "low": [9.9, 10.1, 10.2],
                "close": [10.2, 10.4, 10.7],
                "vol": [100.0, 120.0, 150.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_chart_data",
        lambda history: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-21"),
                    "open": 10.4,
                    "high": 10.8,
                    "low": 10.2,
                    "close": 10.7,
                    "volume": 150.0,
                    "pct": 2.88,
                    "J": 18.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": True,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 2.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 2.0,
            "macd_phase": 4.0,
            "total_score": 2.82,
            "signal_type": "rebound",
            "verdict": "FAIL",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350.SZ",
        pick_date=None,
        dsn=None,
        runtime_root=tmp_path,
    )

    assert result_path == tmp_path / "ad_hoc" / "2026-04-21.b2.002350.SZ" / "result.json"
    assert result_path.exists()

    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["code"] == "002350.SZ"
    assert payload["pick_date"] == "2026-04-21"
    assert payload["method"] == "b2"
    assert payload["signal"] is None
    assert payload["selected_as_candidate"] is False
    assert payload["screen_conditions"]["pre_ok"] is True
    assert payload["latest_metrics"]["trade_date"] == "2026-04-21"
    assert payload["baseline_review"]["verdict"] == "FAIL"
    assert payload["chart_path"] == str((tmp_path / "ad_hoc" / "2026-04-21.b2.002350.SZ" / "002350.SZ_day.png").resolve())


def test_analyze_symbol_impl_uses_explicit_pick_date_and_fetches_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_nth_latest_trade_date",
        lambda connection, end_date, n: pytest.fail("latest trade date should not be fetched"),
    )
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: captured.update(
            {"symbol": symbol, "start_date": start_date, "end_date": end_date}
        )
        or pd.DataFrame(
            {
                "ts_code": [symbol],
                "trade_date": ["2026-04-21"],
                "open": [10.0],
                "high": [10.2],
                "low": [9.9],
                "close": [10.1],
                "vol": [100.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_chart_data",
        lambda history: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-21"),
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.9,
                    "close": 10.1,
                    "volume": 100.0,
                    "pct": 1.0,
                    "J": 20.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": False,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 3.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 3.0,
            "macd_phase": 3.0,
            "total_score": 3.0,
            "signal_type": "rebound",
            "verdict": "WATCH",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350.SZ",
        pick_date="2026-04-21",
        dsn=None,
        runtime_root=tmp_path,
    )

    assert result_path == tmp_path / "ad_hoc" / "2026-04-21.b2.002350.SZ" / "result.json"
    assert captured == {
        "symbol": "002350.SZ",
        "start_date": "2025-04-20",
        "end_date": "2026-04-21",
    }


@pytest.mark.parametrize(
    ("method", "expected_start_date", "prepare_kind"),
    [
        ("b1", "2025-04-20", "shared"),
        ("dribull", cli.DRIBULL_PERIOD_MACD_WARMUP_START_DATE, "shared"),
        ("hcr", "2025-01-02", "hcr"),
    ],
)
def test_analyze_symbol_impl_dispatches_supported_methods(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
    expected_start_date: str,
    prepare_kind: str,
) -> None:
    captured: dict[str, object] = {}
    history = pd.DataFrame(
        {
            "ts_code": ["002350.SZ", "002350.SZ"],
            "trade_date": ["2026-04-18", "2026-04-21"],
            "open": [10.0, 10.2],
            "high": [10.3, 10.5],
            "low": [9.9, 10.1],
            "close": [10.1, 10.4],
            "vol": [100.0, 120.0],
        }
    )
    prepared = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-04-18", "2026-04-21"]),
            "open": [10.0, 10.2],
            "high": [10.3, 10.5],
            "low": [9.9, 10.1],
            "close": [10.1, 10.4],
            "volume": [100.0, 120.0],
            "vol": [100.0, 120.0],
            "turnover_n": [110.0, 125.0],
        }
    )

    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_validate_eod_pick_date_has_market_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: captured.update(
            {"symbol": symbol, "start_date": start_date, "end_date": end_date}
        )
        or history,
    )
    monkeypatch.setattr(
        cli,
        "_prepare_chart_data",
        lambda frame: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)

    if method == "hcr":
        monkeypatch.setattr(
            cli,
            "_resolve_hcr_start_date",
            lambda connection, *, end_date, trading_days: captured.update(
                {"hcr_end_date": end_date, "hcr_trading_days": trading_days}
            )
            or expected_start_date,
        )
    else:
        monkeypatch.setattr(
            cli,
            "_resolve_hcr_start_date",
            lambda *args, **kwargs: pytest.fail("hcr history window should not be resolved"),
        )

    if prepare_kind == "shared":
        monkeypatch.setattr(
            cli,
            "_call_prepare_screen_data",
            lambda market, reporter=None: captured.update({"prepare_kind": "shared"}) or {"002350.SZ": prepared},
        )
        monkeypatch.setattr(
            cli,
            "_call_prepare_hcr_screen_data",
            lambda *args, **kwargs: pytest.fail("hcr prepare path should not run"),
        )
    else:
        monkeypatch.setattr(
            cli,
            "_call_prepare_hcr_screen_data",
            lambda market, reporter=None: captured.update({"prepare_kind": "hcr"}) or {"002350.SZ": prepared},
        )
        monkeypatch.setattr(
            cli,
            "_call_prepare_screen_data",
            lambda *args, **kwargs: pytest.fail("shared prepare path should not run"),
        )

    monkeypatch.setattr(
        cli,
        "run_b1_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: captured.update({"runner": "b1", "pick_ts": pick_date})
        or ([{"code": "002350.SZ", "pick_date": "2026-04-21", "close": 10.4, "turnover_n": 125.0}], _b1_screen_stats(total_symbols=1, eligible=1, selected=1))
        if method == "b1"
        else pytest.fail("b1 runner should not run"),
    )
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: captured.update({"runner": "dribull", "pick_ts": pick_date})
        or ([{"code": "002350.SZ", "pick_date": "2026-04-21", "close": 10.4, "turnover_n": 125.0}], _dribull_wave_stats(total_symbols=1, eligible=1, selected=1))
        if method == "dribull"
        else pytest.fail("dribull runner should not run"),
    )
    monkeypatch.setattr(
        cli,
        "run_hcr_screen_with_stats",
        lambda prepared_by_symbol, pick_date: captured.update({"runner": "hcr", "pick_ts": pick_date})
        or (
            [
                {
                    "code": "002350.SZ",
                    "pick_date": "2026-04-21",
                    "close": 10.4,
                    "turnover_n": 125.0,
                    "yx": 10.2,
                    "p": 10.1,
                    "resonance_gap_pct": 0.004,
                }
            ],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_resonance": 0,
                "fail_close_floor": 0,
                "fail_breakout": 0,
                "selected": 1,
            },
        )
        if method == "hcr"
        else pytest.fail("hcr runner should not run"),
    )
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda *args, **kwargs: pytest.fail("b2 signal frame should not run for non-b2 methods"),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda *args, **kwargs: pytest.fail("b2 signal resolver should not run"))
    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda requested_method: SimpleNamespace(
            name=requested_method,
            prompt_path="unused",
            review_history=lambda **kwargs: {
                "code": kwargs["code"],
                "pick_date": kwargs["pick_date"],
                "chart_path": kwargs["chart_path"],
                "review_type": "baseline",
                "trend_structure": 3.0,
                "price_position": 3.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 3.0,
                "macd_phase": 3.0,
                "total_score": 3.0,
                "signal_type": "rebound",
                "verdict": "WATCH",
                "comment": f"{requested_method} baseline",
            },
        ),
    )

    result_path = cli._analyze_symbol_impl(
        method=method,
        symbol="002350.SZ",
        pick_date="2026-04-21",
        dsn=None,
        runtime_root=tmp_path,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert captured["symbol"] == "002350.SZ"
    assert captured["start_date"] == expected_start_date
    assert captured["end_date"] == "2026-04-21"
    assert captured["prepare_kind"] == prepare_kind
    assert captured["runner"] == method
    assert str(captured["pick_ts"].date()) == "2026-04-21"
    if method == "hcr":
        assert captured["hcr_end_date"] == "2026-04-21"
        assert captured["hcr_trading_days"] == cli.HCR_SCREEN_TRADING_DAYS

    assert payload["method"] == method
    assert payload["signal"] is None
    assert payload["selected_as_candidate"] is True
    assert payload["screen_conditions"]["eligible"] is True
    assert payload["screen_conditions"]["selected"] is True
    assert payload["screen_conditions"]["first_failed_condition"] is None
    assert payload["latest_metrics"]["trade_date"] == "2026-04-21"
    assert payload["baseline_review"]["comment"] == f"{method} baseline"


def test_analyze_symbol_impl_normalizes_symbol_in_runtime_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-21")
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol],
                "trade_date": ["2026-04-21"],
                "open": [10.0],
                "high": [10.2],
                "low": [9.9],
                "close": [10.1],
                "vol": [100.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_chart_data",
        lambda history: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-21"),
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.9,
                    "close": 10.1,
                    "volume": 100.0,
                    "pct": 1.0,
                    "J": 20.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": False,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 3.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 3.0,
            "macd_phase": 3.0,
            "total_score": 3.0,
            "signal_type": "rebound",
            "verdict": "WATCH",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350",
        pick_date=None,
        dsn=None,
        runtime_root=tmp_path,
    )

    assert result_path == tmp_path / "ad_hoc" / "2026-04-21.b2.002350.SZ" / "result.json"


def test_analyze_symbol_impl_writes_baseline_review_even_when_signal_is_null(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-21")
    history = pd.DataFrame(
        {
            "ts_code": ["002350.SZ"] * 3,
            "trade_date": ["2026-04-17", "2026-04-18", "2026-04-21"],
            "open": [10.0, 10.2, 10.4],
            "high": [10.3, 10.5, 10.8],
            "low": [9.9, 10.1, 10.2],
            "close": [10.2, 10.4, 10.7],
            "vol": [100.0, 120.0, 150.0],
        }
    )
    monkeypatch.setattr(cli, "fetch_symbol_history", lambda connection, symbol, start_date, end_date: history)
    monkeypatch.setattr(
        cli,
        "_prepare_chart_data",
        lambda frame: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-21"),
                    "open": 10.4,
                    "high": 10.8,
                    "low": 10.2,
                    "close": 10.7,
                    "volume": 150.0,
                    "pct": 2.88,
                    "J": 18.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": False,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 1.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 2.0,
            "macd_phase": 5.0,
            "total_score": 2.84,
            "signal_type": "rebound",
            "verdict": "FAIL",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350.SZ",
        pick_date=None,
        dsn=None,
        runtime_root=tmp_path,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["signal"] is None
    assert payload["selected_as_candidate"] is False
    assert payload["baseline_review"]["verdict"] == "FAIL"
    assert payload["baseline_review"]["total_score"] == 2.84


def test_analyze_symbol_impl_validates_explicit_pick_date_before_dsn_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: pytest.fail("dsn should not be resolved"))
    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("db should not be opened"))

    with pytest.raises(cli.typer.BadParameter, match="YYYY-MM-DD"):
        cli._analyze_symbol_impl(
            method="b2",
            symbol="002350.SZ",
            pick_date="not-a-date",
            dsn=None,
            runtime_root=tmp_path,
        )


def test_analyze_symbol_impl_surfaces_missing_dsn_as_bad_parameter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli,
        "_resolve_cli_dsn",
        lambda _dsn: (_ for _ in ()).throw(ValueError("A database DSN is required.")),
    )

    with pytest.raises(cli.typer.BadParameter, match="database DSN is required"):
        cli._analyze_symbol_impl(
            method="b2",
            symbol="002350.SZ",
            pick_date="2026-04-21",
            dsn=None,
            runtime_root=tmp_path,
        )


def test_analyze_symbol_impl_serializes_absolute_chart_path_for_relative_runtime_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol],
                "trade_date": ["2026-04-21"],
                "open": [10.0],
                "high": [10.2],
                "low": [9.9],
                "close": [10.1],
                "vol": [100.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_chart_data",
        lambda history: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-21"),
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.9,
                    "close": 10.1,
                    "volume": 100.0,
                    "pct": 1.0,
                    "J": 20.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": False,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 3.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 3.0,
            "macd_phase": 3.0,
            "total_score": 3.0,
            "signal_type": "rebound",
            "verdict": "WATCH",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350.SZ",
        pick_date="2026-04-21",
        dsn=None,
        runtime_root=Path("runtime"),
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["chart_path"] == str(
        (tmp_path / "runtime" / "ad_hoc" / "2026-04-21.b2.002350.SZ" / "002350.SZ_day.png").resolve()
    )


def test_analyze_symbol_impl_rejects_incomplete_target_date_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-20")
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol, symbol],
                "trade_date": ["2026-04-20", "2026-04-21"],
                "open": [10.0, None],
                "high": [10.2, None],
                "low": [9.9, None],
                "close": [10.1, None],
                "vol": [100.0, None],
            }
        ),
    )
    monkeypatch.setattr(cli, "_build_b2_signal_frame", lambda *args, **kwargs: pytest.fail("signal frame should not run"))
    monkeypatch.setattr(cli, "_prepare_chart_data", lambda *args, **kwargs: pytest.fail("chart prep should not run"))
    monkeypatch.setattr(cli, "export_daily_chart", lambda *args, **kwargs: pytest.fail("chart export should not run"))
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda *args, **kwargs: pytest.fail("baseline review should not run"),
    )

    with pytest.raises(cli.typer.BadParameter, match="incomplete end-of-day rows"):
        cli._analyze_symbol_impl(
            method="b2",
            symbol="002350.SZ",
            pick_date="2026-04-21",
            dsn=None,
            runtime_root=tmp_path,
        )


def test_analyze_symbol_impl_rejects_missing_explicit_pick_date_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_validate_eod_pick_date_has_market_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol, symbol],
                "trade_date": ["2026-04-18", "2026-04-20"],
                "open": [10.0, 10.2],
                "high": [10.3, 10.5],
                "low": [9.9, 10.1],
                "close": [10.1, 10.4],
                "vol": [100.0, 120.0],
            }
        ),
    )
    monkeypatch.setattr(cli, "_build_b2_signal_frame", lambda *args, **kwargs: pytest.fail("signal frame should not run"))
    monkeypatch.setattr(cli, "_prepare_chart_data", lambda *args, **kwargs: pytest.fail("chart prep should not run"))
    monkeypatch.setattr(cli, "export_daily_chart", lambda *args, **kwargs: pytest.fail("chart export should not run"))
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda *args, **kwargs: pytest.fail("baseline review should not run"),
    )

    with pytest.raises(
        cli.typer.BadParameter,
        match=r"No end-of-day data found for symbol 002350\.SZ on pick_date 2026-04-21\.",
    ):
        cli._analyze_symbol_impl(
            method="b2",
            symbol="002350.SZ",
            pick_date="2026-04-21",
            dsn=None,
            runtime_root=tmp_path,
        )


def test_analyze_symbol_impl_omitted_pick_date_falls_back_to_latest_complete_symbol_date(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-21")
    monkeypatch.setattr(
        cli,
        "fetch_previous_trade_date",
        lambda connection, before_date: calls.append(before_date) or "2026-04-20",
    )

    def fake_history(connection, symbol, start_date, end_date):
        if end_date == "2026-04-21":
            return pd.DataFrame(
                {
                    "ts_code": [symbol, symbol],
                    "trade_date": ["2026-04-20", "2026-04-21"],
                    "open": [10.0, None],
                    "high": [10.2, None],
                    "low": [9.9, None],
                    "close": [10.1, None],
                    "vol": [100.0, None],
                }
            )
        if end_date == "2026-04-20":
            return pd.DataFrame(
                {
                    "ts_code": [symbol],
                    "trade_date": ["2026-04-20"],
                    "open": [10.0],
                    "high": [10.2],
                    "low": [9.9],
                    "close": [10.1],
                    "vol": [100.0],
                }
            )
        pytest.fail(f"unexpected end_date {end_date}")

    monkeypatch.setattr(cli, "fetch_symbol_history", fake_history)
    monkeypatch.setattr(
        cli,
        "_prepare_chart_data",
        lambda history: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-20"),
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.9,
                    "close": 10.1,
                    "volume": 100.0,
                    "pct": 1.0,
                    "J": 20.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": False,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 3.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 3.0,
            "macd_phase": 3.0,
            "total_score": 3.0,
            "signal_type": "rebound",
            "verdict": "WATCH",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350.SZ",
        pick_date=None,
        dsn=None,
        runtime_root=tmp_path,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert calls == ["2026-04-21"]
    assert payload["pick_date"] == "2026-04-20"
    assert result_path == tmp_path / "ad_hoc" / "2026-04-20.b2.002350.SZ" / "result.json"


def test_screen_accepts_b2_method(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    expected_path = runtime_root / "candidates" / f"{_eod_key('2026-04-01', 'b2')}.json"

    monkeypatch.setattr(
        cli,
        "_screen_impl",
        lambda **kwargs: expected_path if kwargs["method"] == "b2" else None,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b2",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected_path)


def test_screen_accepts_whitespace_padded_dribull_method(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    expected_path = runtime_root / "candidates" / f"{_eod_key('2026-04-01', 'dribull')}.json"

    monkeypatch.setattr(
        cli,
        "_screen_impl",
        lambda **kwargs: expected_path if kwargs["method"] == "dribull" else None,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            " dribull ",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected_path)


def test_screen_dribull_phase_one_does_not_filter_on_daily_macd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())

    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        close_values = [12.0] * 146 + [11.8, 11.7, 11.9, 12.1, 12.4, 12.8, 13.1, 13.4, 13.2, 13.0, 12.9, 12.92, 12.97, 13.02]
        if start_date == "2025-04-09":
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * len(trade_dates),
                    "trade_date": trade_dates,
                    "open": [value - 0.1 for value in close_values],
                    "high": [value + 0.2 for value in close_values],
                    "low": [value - 0.2 for value in close_values[:-1]] + [12.40],
                    "close": close_values,
                    "vol": [100.0 + idx for idx in range(len(trade_dates) - 1)] + [50.0],
                }
            )
        assert start_date == "2023-01-01"
        assert symbols == ["000001.SZ"]
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * len(trade_dates),
                "trade_date": trade_dates,
                "open": [value - 0.1 for value in close_values],
                "high": [value + 0.2 for value in close_values],
                "low": [value - 0.2 for value in close_values[:-1]] + [12.40],
                "close": close_values,
                "vol": [100.0 + idx for idx in range(len(trade_dates) - 1)] + [50.0],
            }
        )

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        prepared = {}
        for code, group in market.groupby("ts_code"):
            group = group.sort_values("trade_date").reset_index(drop=True).copy()
            group["turnover_n"] = 999.0
            group["J"] = 10.0
            group["zxdq"] = group["close"] + 0.3
            group["zxdkx"] = group["close"] - 0.1
            group["ma25"] = group["close"].rolling(window=25, min_periods=25).mean()
            group["ma60"] = group["close"].rolling(window=60, min_periods=60).mean()
            group["ma144"] = group["close"].rolling(window=144, min_periods=144).mean()
            group["low"] = group["close"] - 0.2
            group["volume"] = group["vol"]
            group.loc[group.index[-1], "low"] = float(group.loc[group.index[-1], "ma25"]) * 1.004
            group["dif"] = 0.02
            group["dea"] = 0.08
            group["dif_w"] = 0.12
            group["dea_w"] = 0.08
            group["dif_m"] = 0.18
            group["dea_m"] = 0.12
            prepared[code] = group
        return prepared

    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-10"): ["000001.SZ"]},
    )
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "000001.SZ", "pick_date": "2026-04-10", "close": 13.18, "turnover_n": 999.0}],
            _dribull_wave_stats(total_symbols=len(prepared_by_symbol), eligible=len(prepared_by_symbol), selected=1),
        ),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
            "--progress",
        ],
    )

    assert result.exit_code == 0
    assert "mode=macd_warmup" in result.stderr
    assert "fail_weekly_wave=" in result.stderr


def test_screen_accepts_whitespace_padded_b1_method(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    expected_path = runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json"

    monkeypatch.setattr(
        cli,
        "_screen_impl",
        lambda **kwargs: expected_path,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            " b1 ",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected_path)


def test_screen_accepts_pool_source_and_passes_it_to_screen_impl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    expected_path = runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json"

    def fake_screen_impl(**kwargs: object) -> Path:
        assert kwargs["method"] == "b1"
        assert kwargs["pick_date"] == "2026-04-01"
        assert kwargs["dsn"] == "postgresql://example"
        assert kwargs["runtime_root"] == runtime_root
        assert kwargs["pool_source"] == "record-watch"
        return expected_path

    monkeypatch.setattr(cli, "_screen_impl", fake_screen_impl)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--pool-source",
            " record-watch ",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected_path)


def test_screen_accepts_custom_pool_file_and_passes_it_to_screen_impl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    pool_file = tmp_path / "custom-pool.txt"
    expected_path = runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json"

    def fake_screen_impl(**kwargs: object) -> Path:
        assert kwargs["method"] == "b1"
        assert kwargs["pick_date"] == "2026-04-01"
        assert kwargs["dsn"] == "postgresql://example"
        assert kwargs["runtime_root"] == runtime_root
        assert kwargs["pool_source"] == "custom"
        assert kwargs["pool_file"] == pool_file
        return expected_path

    monkeypatch.setattr(cli, "_screen_impl", fake_screen_impl)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--pool-source",
            " custom ",
            "--pool-file",
            str(pool_file),
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected_path)


def test_screen_rejects_invalid_pool_source() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--pool-source",
            "nonsense",
        ],
    )

    assert result.exit_code != 0
    assert "unsupported pool source" in result.stderr.lower()
    assert "custom" in result.stderr
    assert "turnover-top" in result.stderr
    assert "record-watch" in result.stderr


def test_screen_custom_pool_rejects_missing_configuration_with_guidance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    missing_default_pool = tmp_path / "missing-custom-pool.txt"

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
                "ts_code": ["AAA.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
                    "turnover_n": [100.0],
                }
            )
        }

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "_default_custom_pool_path", lambda: missing_default_pool)
    monkeypatch.delenv("STOCK_SELECT_POOL_FILE", raising=False)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "custom",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "--pool-file" in result.stderr
    assert "STOCK_SELECT_POOL_FILE" in result.stderr
    normalized_stderr = result.stderr.replace("\n", "").replace(" ", "").replace("│", "")
    assert str(missing_default_pool).replace(" ", "") in normalized_stderr


def test_screen_custom_pool_rejects_empty_code_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    pool_file = tmp_path / "custom-pool.txt"
    pool_file.write_text(" \n\t ", encoding="utf-8")

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
                "ts_code": ["AAA.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
                    "turnover_n": [100.0],
                }
            )
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
            "2026-04-04",
            "--pool-source",
            "custom",
            "--pool-file",
            str(pool_file),
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "at least one stock code" in result.stderr.lower()


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


def test_chart_requires_dsn_when_real_history_fetch_is_needed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_eod_key('2026-04-01')}.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.chdir(tmp_path)

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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
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
    assert (runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json").exists()
    assert "[screen] connect db" in result.stderr
    assert "[screen] selected candidates=" in result.stderr


def test_screen_writes_hcr_candidate_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "_resolve_hcr_start_date",
        lambda connection, *, end_date, trading_days: "2024-10-16",
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "open": [10.0],
                "high": [10.8],
                "low": [9.8],
                "close": [10.6],
                "vol": [100.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-09"]),
                    "close": [10.6],
                    "yx": [10.4],
                    "p": [10.5],
                    "resonance_gap_pct": [0.0095],
                    "turnover_n": [1030.0],
                }
            )
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "run_hcr_screen_with_stats",
        lambda prepared_by_symbol, pick_date: (
            [
                {
                    "code": "000001.SZ",
                    "pick_date": "2026-04-01",
                    "close": 10.6,
                    "turnover_n": 1030.0,
                    "yx": 10.4,
                    "p": 10.5,
                    "resonance_gap_pct": 0.0095,
                }
            ],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_resonance": 0,
                "fail_close_floor": 0,
                "fail_breakout": 0,
                "selected": 1,
            },
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
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

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-01', 'hcr')}.json").read_text(encoding="utf-8"))
    assert payload["method"] == "hcr"
    assert payload["candidates"][0]["code"] == "000001.SZ"


def test_screen_rejects_pick_date_without_end_of_day_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    fetch_calls: list[dict[str, object]] = []

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, *, end_date, n: "2026-04-09")
    monkeypatch.setattr(cli, "_prepare_screen_data", lambda market, reporter=None: pytest.fail("b2 validation should reject before phase-one preparation"))

    def fake_fetch_daily_window(*args, **kwargs) -> pd.DataFrame:
        fetch_calls.append(dict(kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-09"]),
                "open": [10.0],
                "high": [10.8],
                "low": [9.8],
                "close": [10.6],
                "vol": [100.0],
            }
        )

    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "2026-04-10" in result.stderr
    assert "2026-04-09" in result.stderr
    assert "end-of-day" in result.stderr.lower()
    assert fetch_calls == [
        {
            "start_date": (pd.Timestamp("2026-04-10") - pd.Timedelta(days=cli.DEFAULT_SCREEN_LOOKBACK_DAYS)).strftime("%Y-%m-%d"),
            "end_date": "2026-04-10",
            "symbols": None,
        }
    ]


def test_screen_accepts_dribull_method_and_writes_dribull_candidate_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    expected_path = runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'dribull')}.json"

    def fake_screen_impl(**kwargs: object) -> Path:
        assert kwargs["method"] == "dribull"
        payload = {
            "pick_date": "2026-04-10",
            "method": "dribull",
            "candidates": [
                {
                    "code": "000001.SZ",
                    "pick_date": "2026-04-10",
                    "close": 10.4,
                    "turnover_n": 100.0,
                }
            ],
        }
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        expected_path.write_text(json.dumps(payload), encoding="utf-8")
        return expected_path

    monkeypatch.setattr(
        cli,
        "_screen_impl",
        fake_screen_impl,
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected_path)
    payload = json.loads(expected_path.read_text(encoding="utf-8"))
    assert payload["method"] == "dribull"
    assert payload["candidates"][0]["code"] == "000001.SZ"


def test_screen_hcr_uses_trade_date_lookback_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    fetch_args: dict[str, str] = {}

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "_resolve_hcr_start_date",
        lambda connection, *, end_date, trading_days: (
            "2025-04-29" if end_date == "2026-04-09" and trading_days == 240 else ""
        ),
        raising=False,
    )

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        fetch_args["start_date"] = start_date
        fetch_args["end_date"] = end_date
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-09"]),
                "open": [10.0],
                "high": [10.8],
                "low": [9.8],
                "close": [10.6],
                "vol": [100.0],
            }
        )

    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-09"]),
                    "close": [10.6],
                    "yx": [10.4],
                    "p": [10.5],
                    "resonance_gap_pct": [0.0095],
                    "turnover_n": [1030.0],
                }
            )
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "run_hcr_screen_with_stats",
        lambda prepared_by_symbol, pick_date: (
            [],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_resonance": 0,
                "fail_close_floor": 0,
                "fail_breakout": 1,
                "selected": 0,
            },
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--pick-date",
            "2026-04-09",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert fetch_args == {
        "start_date": "2025-04-29",
        "end_date": "2026-04-09",
    }


def test_chart_exports_png_for_candidates(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_eod_key('2026-04-01')}.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
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
    assert (runtime_root / "charts" / _eod_key("2026-04-01") / "000001.SZ_day.png").exists()
    assert "[chart] candidate 1/1 code=000001.SZ" in result.stderr


def test_chart_rejects_stale_b1_candidate_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_eod_key('2026-04-01')}.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("stale b1 candidate should be rejected before DB access"))

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

    assert result.exit_code != 0
    assert "stale b1 candidate file" in result.stderr.lower()


def test_chart_accepts_hcr_candidate_file_shape(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_eod_key('2026-04-01', 'hcr')}.json").write_text(
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
    assert (runtime_root / "charts" / _eod_key("2026-04-01", "hcr") / "000001.SZ_day.png").exists()


def test_chart_intraday_uses_latest_intraday_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_intraday_key('2026-04-09T10-00-00+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T10-00-00+08-00",
                "candidates": [{"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "trade_date": "2026-04-09",
                "fetched_at": "2026-04-09T11-31-08+08-00",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / f"{_intraday_key('2026-04-09T12-00-00+08-00', 'hcr')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "hcr",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T12-00-00+08-00",
                "candidates": [{"code": "000003.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_intraday_prepared_cache",
        lambda current_runtime_root, *, method, run_id, trade_date: (
            {
                "000001.SZ": pd.DataFrame(
                    [
                        {"date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "volume": 120.0},
                        {"date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "volume": 150.0},
                    ]
                )
            }
            if current_runtime_root == runtime_root
            and method == "b1"
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
    assert (runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08+08-00") / "000001.SZ_day.png").exists()


def test_chart_intraday_warns_outside_trading_hours(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 15:30:00", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.setattr(cli, "_chart_intraday_impl", lambda **kwargs: tmp_path / "charts" / "fake")

    result = runner.invoke(
        app,
        ["chart", "--method", "b1", "--intraday", "--runtime-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "outside trading-day intraday market hours" in result.stderr


def test_chart_intraday_rejects_malformed_latest_candidate_payload(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_intraday_key('2026-04-09T10-00-00+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T10-00-00+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
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
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
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
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "mode": "intraday_snapshot",
                "run_id": "2026-04-09T11-31-08+08-00",
            },
        },
    )

    result = runner.invoke(app, ["chart", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code != 0
    assert "prepared intraday cache metadata mismatch" in result.stderr.lower()


def test_chart_intraday_rejects_stale_b1_prepared_cache(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-09.intraday.pkl",
        pick_date="2026-04-09",
        start_date="2025-04-08",
        end_date="2026-04-09",
        prepared_by_symbol={
            "000001.SZ": pd.DataFrame(
                [
                    {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                    {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
                ]
            )
        },
        metadata_overrides={
            "mode": "intraday_snapshot",
            "run_id": "2026-04-09T11-31-08+08-00",
            "previous_trade_date": "2026-04-08",
        },
    )

    result = runner.invoke(app, ["chart", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code != 0
    assert "stale intraday prepared cache" in result.stderr.lower()


def test_review_writes_summary_json(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    method_key = _eod_key("2026-04-01")
    review_dir = runtime_root / "reviews" / method_key
    (candidate_dir / f"{method_key}.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
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
    assert (review_dir / "summary.json").exists()
    assert (review_dir / "llm_review_tasks.json").exists()
    review = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    assert review["code"] == "000001.SZ"
    assert review["review_mode"] == "baseline_local"
    assert review["baseline_review"]["review_type"] == "baseline"
    assert review["llm_review"] is None
    assert tasks["pick_date"] == "2026-04-01"
    assert tasks["prompt_path"].endswith(".agents/skills/stock-select/references/prompt-b1.md")
    assert tasks["max_concurrency"] == 6
    assert tasks["tasks"][0]["code"] == "000001.SZ"
    assert tasks["tasks"][0]["rank"] == 1
    assert tasks["tasks"][0]["baseline_score"] == review["total_score"]
    assert tasks["tasks"][0]["baseline_verdict"] == review["verdict"]
    assert "total_score" in review
    assert "[review] candidate 1/1 code=000001.SZ" in result.stderr
    assert "[review] done reviewed=1 failures=0" in result.stderr


def test_review_rejects_stale_b1_candidate_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    method_key = _eod_key("2026-04-01")
    candidate_path = runtime_root / "candidates" / f"{method_key}.json"
    chart_dir = runtime_root / "charts" / method_key
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")

    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("stale b1 candidate should be rejected before DB access"))

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

    assert result.exit_code != 0
    assert "stale b1 candidate file" in result.stderr.lower()


def test_review_uses_method_specific_resolver_prompt_and_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    method_key = _eod_key("2026-04-01", "b2")
    review_dir = runtime_root / "reviews" / method_key
    candidate_path = runtime_root / "candidates" / f"{method_key}.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b2",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, *, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol, symbol, symbol],
                "trade_date": pd.to_datetime(["2026-03-28", "2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.6, 10.9],
                "low": [9.9, 10.1, 10.3],
                "close": [10.2, 10.5, 10.8],
                "vol": [100.0, 120.0, 150.0],
            }
        ),
    )

    prompt_path = str(tmp_path / "prompt-b2-stub.md")
    resolver_calls: list[dict[str, object]] = []
    resolver_methods: list[str] = []
    expected_rows = [
        {
            "ts_code": "000001.SZ",
            "trade_date": pd.Timestamp("2026-03-28"),
            "open": 10.0,
            "high": 10.3,
            "low": 9.9,
            "close": 10.2,
            "vol": 100.0,
        },
        {
            "ts_code": "000001.SZ",
            "trade_date": pd.Timestamp("2026-03-31"),
            "open": 10.2,
            "high": 10.6,
            "low": 10.1,
            "close": 10.5,
            "vol": 120.0,
        },
        {
            "ts_code": "000001.SZ",
            "trade_date": pd.Timestamp("2026-04-01"),
            "open": 10.4,
            "high": 10.9,
            "low": 10.3,
            "close": 10.8,
            "vol": 150.0,
        },
    ]

    def fake_review_history(
        *,
        code: str,
        pick_date: str,
        history: pd.DataFrame,
        chart_path: str,
    ) -> dict[str, object]:
        resolver_calls.append(
            {
                "code": code,
                "pick_date": pick_date,
                "chart_path": chart_path,
                "rows": history.to_dict(orient="records"),
            }
        )
        return {
            "review_type": "baseline",
            "total_score": 4.6,
            "signal_type": "trend_start",
            "verdict": "PASS",
            "comment": "resolver baseline",
        }

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: resolver_methods.append(method)
        or SimpleNamespace(
            name="b2",
            prompt_path=prompt_path,
            review_history=fake_review_history,
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b2",
            "--pick-date",
            "2026-04-01",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert resolver_methods == ["b2"]
    assert len(resolver_calls) == 1
    assert resolver_calls[0]["code"] == "000001.SZ"
    assert resolver_calls[0]["pick_date"] == "2026-04-01"
    assert resolver_calls[0]["chart_path"] == str(chart_dir / "000001.SZ_day.png")
    assert resolver_calls[0]["rows"] == expected_rows
    review = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    assert review["code"] == "000001.SZ"
    assert review["chart_path"] == str(chart_dir / "000001.SZ_day.png")
    assert review["review_mode"] == "baseline_local"
    assert review["llm_review"] is None
    assert review["baseline_review"]["review_type"] == "baseline"
    assert review["baseline_review"]["comment"] == "resolver baseline"
    assert review["total_score"] == 4.6
    assert review["signal_type"] == "trend_start"
    assert review["verdict"] == "PASS"
    assert summary == {
        "pick_date": "2026-04-01",
        "method": "b2",
        "reviewed_count": 1,
        "recommendations": [review],
        "excluded": [],
        "failures": [],
    }
    assert tasks["prompt_path"] == prompt_path
    assert tasks["method"] == "b2"
    assert tasks["max_concurrency"] == 6
    assert tasks["tasks"][0]["prompt_path"] == prompt_path
    assert tasks["tasks"][0]["chart_path"] == str(chart_dir / "000001.SZ_day.png")
    assert tasks["tasks"][0]["baseline_score"] == review["total_score"]
    assert tasks["tasks"][0]["baseline_verdict"] == review["verdict"]
    assert "weekly_wave_context" in tasks["tasks"][0]
    assert "daily_wave_context" in tasks["tasks"][0]
    assert "wave_combo_context" in tasks["tasks"][0]
    assert "周线" in tasks["tasks"][0]["weekly_wave_context"]
    assert "日线" in tasks["tasks"][0]["daily_wave_context"]
    assert "b2" in tasks["tasks"][0]["wave_combo_context"]


def test_review_filters_llm_tasks_by_min_baseline_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    method_key = _eod_key("2026-04-01", "b2")
    review_dir = runtime_root / "reviews" / method_key
    candidate_path = runtime_root / "candidates" / f"{method_key}.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b2",
                "candidates": [{"code": "000001.SZ"}, {"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (chart_dir / "000002.SZ_day.png").write_bytes(b"png")

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, *, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol, symbol, symbol],
                "trade_date": pd.to_datetime(["2026-03-28", "2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.6, 10.9],
                "low": [9.9, 10.1, 10.3],
                "close": [10.2, 10.5, 10.8],
                "vol": [100.0, 120.0, 150.0],
            }
        ),
    )

    baseline_scores = {"000001.SZ": 4.2, "000002.SZ": 3.9}

    def fake_review_history(
        *,
        code: str,
        pick_date: str,
        history: pd.DataFrame,
        chart_path: str,
    ) -> dict[str, object]:
        score = baseline_scores[code]
        return {
            "review_type": "baseline",
            "total_score": score,
            "signal_type": "trend_start" if score >= 4.0 else "rebound",
            "verdict": "PASS" if score >= 4.0 else "WATCH",
            "comment": f"{code} baseline",
        }

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: SimpleNamespace(
            name="b2",
            prompt_path=str(tmp_path / "prompt-b2-stub.md"),
            review_history=fake_review_history,
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b2",
            "--pick-date",
            "2026-04-01",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--llm-min-baseline-score",
            "4.0",
        ],
    )

    assert result.exit_code == 0
    high_review = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    low_review = json.loads((review_dir / "000002.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))

    assert high_review["total_score"] == 4.2
    assert low_review["total_score"] == 3.9
    assert summary["reviewed_count"] == 2
    assert [task["code"] for task in tasks["tasks"]] == ["000001.SZ"]
    assert tasks["tasks"][0]["baseline_score"] == 4.2
    assert "llm_tasks=1" in result.stderr
    assert "skipped_by_baseline_score=1" in result.stderr


def test_review_rejects_non_finite_llm_min_baseline_score(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

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
            "--llm-min-baseline-score",
            "nan",
        ],
    )

    assert result.exit_code != 0
    assert "llm-min-baseline-score" in result.stderr.lower()
    assert "finite" in result.stderr.lower()
    assert "non-negative" in result.stderr.lower()


def test_review_rejects_negative_llm_min_baseline_score(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(tmp_path),
            "--llm-min-baseline-score",
            "-0.1",
        ],
    )

    assert result.exit_code != 0
    assert "llm-min-baseline-score" in result.stderr.lower()
    assert "finite" in result.stderr.lower()
    assert "non-negative" in result.stderr.lower()


def test_review_dribull_uses_b2_resolver_prompt_and_dribull_artifact_method(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    method_key = _eod_key("2026-04-01", "dribull")
    review_dir = runtime_root / "reviews" / method_key
    candidate_path = runtime_root / "candidates" / f"{method_key}.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b2",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, *, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol, symbol, symbol],
                "trade_date": pd.to_datetime(["2026-03-28", "2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.6, 10.9],
                "low": [9.9, 10.1, 10.3],
                "close": [10.2, 10.5, 10.8],
                "vol": [100.0, 120.0, 150.0],
            }
        ),
    )

    prompt_path = str(tmp_path / "prompt-b2-stub.md")
    resolver_methods: list[str] = []

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: resolver_methods.append(method)
        or SimpleNamespace(
            name="b2",
            prompt_path=prompt_path,
            review_history=lambda **kwargs: {
                "review_type": "baseline",
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "resolver baseline",
            },
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-01",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert resolver_methods == ["dribull"]
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    assert tasks["prompt_path"] == prompt_path
    assert tasks["method"] == "dribull"
    assert summary["method"] == "dribull"
    assert "dribull" in tasks["tasks"][0]["wave_combo_context"]


def test_run_b2_uses_new_b2_screen_and_existing_b2_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_path = runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'b2')}.json"
    chart_dir = runtime_root / "charts" / _eod_key("2026-04-10", "b2")
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-10", "b2")
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")

    def fake_screen_impl(**kwargs):
        assert kwargs["method"] == "b2"
        candidate_path.write_text(
            json.dumps(
                {
                    "pick_date": "2026-04-10",
                    "method": "b2",
                    "candidates": [{"code": "000001.SZ", "signal": "B2", "close": 10.65, "turnover_n": 1000.0}],
                }
            ),
            encoding="utf-8",
        )
        return candidate_path

    monkeypatch.setattr(cli, "_screen_impl", fake_screen_impl)
    monkeypatch.setattr(cli, "_chart_impl", lambda **kwargs: chart_dir)
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, *, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol, symbol, symbol],
                "trade_date": pd.to_datetime(["2026-04-08", "2026-04-09", "2026-04-10"]),
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.6, 10.9],
                "low": [9.9, 10.1, 10.3],
                "close": [10.2, 10.5, 10.8],
                "vol": [100.0, 120.0, 150.0],
            }
        ),
    )

    prompt_path = str(tmp_path / "prompt-b2-stub.md")
    resolver_methods: list[str] = []

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: resolver_methods.append(method)
        or SimpleNamespace(
            name="b2",
            prompt_path=prompt_path,
            review_history=lambda **kwargs: {
                "review_type": "baseline",
                "total_score": 4.6,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "resolver baseline",
            },
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b2",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert resolver_methods == ["b2"]
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    assert tasks["method"] == "b2"
    assert summary["method"] == "b2"
    assert tasks["prompt_path"] == prompt_path


def test_review_intraday_uses_latest_intraday_candidate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08+08-00")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / f"{_intraday_key('2026-04-09T10-00-00+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T10-00-00+08-00",
                "candidates": [{"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "trade_date": "2026-04-09",
                "fetched_at": "2026-04-09T11-31-08+08-00",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    (candidate_dir / f"{_intraday_key('2026-04-09T12-00-00+08-00', 'hcr')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "hcr",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T12-00-00+08-00",
                "candidates": [{"code": "000003.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_intraday_prepared_cache",
        lambda current_runtime_root, *, method, run_id, trade_date: (
            {
                "000001.SZ": pd.DataFrame(
                    [
                        {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                        {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
                    ]
                )
            }
            if current_runtime_root == runtime_root
            and method == "b1"
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

    def fake_review_history(
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

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: SimpleNamespace(
            name="default",
            prompt_path="resolver-prompt.md",
            review_history=fake_review_history,
        ),
        raising=False,
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
    assert (runtime_root / "reviews" / _intraday_key("2026-04-09T11-31-08+08-00") / "summary.json").exists()


def test_review_intraday_rejects_stale_b1_prepared_cache(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08+08-00")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-09.intraday.pkl",
        pick_date="2026-04-09",
        start_date="2025-04-08",
        end_date="2026-04-09",
        prepared_by_symbol={
            "000001.SZ": pd.DataFrame(
                [
                    {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                    {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
                ]
            )
        },
        metadata_overrides={
            "mode": "intraday_snapshot",
            "run_id": "2026-04-09T11-31-08+08-00",
            "previous_trade_date": "2026-04-08",
        },
    )

    result = runner.invoke(app, ["review", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code != 0
    assert "stale intraday prepared cache" in result.stderr.lower()


def test_review_intraday_warns_outside_trading_hours(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 12:15:00", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.setattr(cli, "_review_intraday_impl", lambda **kwargs: tmp_path / "reviews" / "fake.json")

    result = runner.invoke(
        app,
        ["review", "--method", "b1", "--intraday", "--runtime-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "outside trading-day intraday market hours" in result.stderr


def test_review_intraday_uses_method_specific_resolver_prompt_and_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    run_id = "2026-04-09T11-31-08+08-00"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / _intraday_key(run_id, "b2")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / f"{_intraday_key(run_id, 'b2')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b2",
                "trade_date": "2026-04-09",
                "run_id": run_id,
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_intraday_prepared_cache",
        lambda current_runtime_root, *, method, run_id, trade_date: (
            {
                "000001.SZ": pd.DataFrame(
                    [
                        {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                        {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
                    ]
                )
            }
            if current_runtime_root == runtime_root
            and method == "b2"
            and run_id == "2026-04-09T11-31-08+08-00"
            and trade_date == "2026-04-09"
            else pytest.fail("review did not request the expected intraday prepared cache")
        ),
    )
    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("review --intraday should not connect to the database"))
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda *args, **kwargs: pytest.fail("review --intraday should not fetch symbol history"),
    )

    prompt_path = str(tmp_path / "prompt-b2-stub.md")
    resolver_calls: list[dict[str, object]] = []
    resolver_methods: list[str] = []
    expected_rows = [
        {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
        {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
    ]

    def fake_review_history(
        *,
        code: str,
        pick_date: str,
        history: pd.DataFrame,
        chart_path: str,
    ) -> dict[str, object]:
        resolver_calls.append(
            {
                "code": code,
                "pick_date": pick_date,
                "chart_path": chart_path,
                "rows": history.to_dict(orient="records"),
            }
        )
        return {
            "review_type": "baseline",
            "total_score": 4.3,
            "signal_type": "trend_start",
            "verdict": "PASS",
            "comment": "resolver intraday baseline",
        }

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: resolver_methods.append(method)
        or SimpleNamespace(
            name="b2",
            prompt_path=prompt_path,
            review_history=fake_review_history,
        ),
        raising=False,
    )

    result = runner.invoke(app, ["review", "--method", "b2", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code == 0
    assert resolver_methods == ["b2"]
    assert len(resolver_calls) == 1
    assert resolver_calls[0]["code"] == "000001.SZ"
    assert resolver_calls[0]["pick_date"] == "2026-04-09"
    assert resolver_calls[0]["chart_path"] == str(chart_dir / "000001.SZ_day.png")
    assert resolver_calls[0]["rows"] == expected_rows
    review_dir = runtime_root / "reviews" / _intraday_key(run_id, "b2")
    review = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    assert review["code"] == "000001.SZ"
    assert review["pick_date"] == "2026-04-09"
    assert review["chart_path"] == str(chart_dir / "000001.SZ_day.png")
    assert review["review_mode"] == "baseline_local"
    assert review["llm_review"] is None
    assert review["baseline_review"]["comment"] == "resolver intraday baseline"
    assert review["total_score"] == 4.3
    assert review["signal_type"] == "trend_start"
    assert review["verdict"] == "PASS"
    assert summary == {
        "pick_date": "2026-04-09",
        "method": "b2",
        "reviewed_count": 1,
        "recommendations": [review],
        "excluded": [],
        "failures": [],
    }
    assert tasks["prompt_path"] == prompt_path
    assert tasks["method"] == "b2"
    assert tasks["max_concurrency"] == 6
    assert tasks["tasks"][0]["prompt_path"] == prompt_path
    assert tasks["tasks"][0]["chart_path"] == str(chart_dir / "000001.SZ_day.png")
    assert tasks["tasks"][0]["baseline_score"] == review["total_score"]
    assert tasks["tasks"][0]["baseline_verdict"] == review["verdict"]
    assert "weekly_wave_context" in tasks["tasks"][0]
    assert "daily_wave_context" in tasks["tasks"][0]
    assert "wave_combo_context" in tasks["tasks"][0]


def test_review_intraday_filters_llm_tasks_by_min_baseline_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    run_id = "2026-04-09T11-31-08+08-00"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / _intraday_key(run_id, "b2")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (chart_dir / "000002.SZ_day.png").write_bytes(b"png")
    (candidate_dir / f"{_intraday_key(run_id, 'b2')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b2",
                "trade_date": "2026-04-09",
                "run_id": run_id,
                "candidates": [{"code": "000001.SZ"}, {"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_intraday_prepared_cache",
        lambda current_runtime_root, *, method, run_id, trade_date: {
            "000001.SZ": pd.DataFrame(
                [
                    {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                    {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
                ]
            ),
            "000002.SZ": pd.DataFrame(
                [
                    {"trade_date": "2026-04-08", "open": 21.9, "high": 22.1, "low": 21.8, "close": 22.0, "vol": 220.0},
                    {"trade_date": "2026-04-09", "open": 22.1, "high": 22.5, "low": 22.0, "close": 22.34, "vol": 250.0},
                ]
            ),
        },
    )

    baseline_scores = {"000001.SZ": 4.1, "000002.SZ": 3.8}

    def fake_review_history(
        *,
        code: str,
        pick_date: str,
        history: pd.DataFrame,
        chart_path: str,
    ) -> dict[str, object]:
        score = baseline_scores[code]
        return {
            "review_type": "baseline",
            "total_score": score,
            "signal_type": "trend_start" if score >= 4.0 else "rebound",
            "verdict": "PASS" if score >= 4.0 else "WATCH",
            "comment": f"{code} intraday baseline",
        }

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: SimpleNamespace(
            name="b2",
            prompt_path=str(tmp_path / "prompt-b2-stub.md"),
            review_history=fake_review_history,
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b2",
            "--intraday",
            "--runtime-root",
            str(runtime_root),
            "--llm-min-baseline-score",
            "4.0",
        ],
    )

    assert result.exit_code == 0
    review_dir = runtime_root / "reviews" / _intraday_key(run_id, "b2")
    high_review = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    low_review = json.loads((review_dir / "000002.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))

    assert high_review["total_score"] == 4.1
    assert low_review["total_score"] == 3.8
    assert summary["reviewed_count"] == 2
    assert [task["code"] for task in tasks["tasks"]] == ["000001.SZ"]
    assert tasks["tasks"][0]["baseline_score"] == 4.1
    assert "llm_tasks=1" in result.stderr
    assert "skipped_by_baseline_score=1" in result.stderr


def test_prompt_b2_requires_weekly_and_daily_wave_language() -> None:
    prompt_path = Path(".agents/skills/stock-select/references/prompt-b2.md")
    content = prompt_path.read_text(encoding="utf-8")

    assert "weekly_wave_context" in content
    assert "daily_wave_context" in content
    assert "wave_combo_context" in content
    assert "周线" in content
    assert "日线" in content
    assert "浪" in content


def test_review_b1_tasks_include_wave_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    method_key = _eod_key("2026-04-01", "b1")
    review_dir = runtime_root / "reviews" / method_key
    candidate_path = runtime_root / "candidates" / f"{method_key}.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")

    trade_dates = pd.bdate_range(end="2026-04-01", periods=180)
    close = [10.0 + 0.02 * idx for idx in range(len(trade_dates))]
    history = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * len(trade_dates),
            "trade_date": trade_dates,
            "open": [value - 0.05 for value in close],
            "high": [value + 0.1 for value in close],
            "low": [value - 0.1 for value in close],
            "close": close,
            "vol": [1000.0 + idx for idx in range(len(trade_dates))],
        }
    )

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, *, symbol, start_date, end_date: history,
    )
    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: SimpleNamespace(
            name="b1",
            prompt_path="prompt-b1-stub.md",
            review_history=lambda **kwargs: {
                "review_type": "baseline",
                "total_score": 4.1,
                "signal_type": "trend_start",
                "verdict": "PASS",
                "comment": "b1 baseline",
            },
        ),
        raising=False,
    )

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
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    task = tasks["tasks"][0]
    assert "weekly_wave_context" in task
    assert "daily_wave_context" in task
    assert "wave_combo_context" in task
    assert "组合判定" in task["wave_combo_context"]
    assert "b1" in task["wave_combo_context"]
    assert "候选要求" in task["wave_combo_context"]
    assert any(word in task["wave_combo_context"] for word in ("符合", "不符合"))


@pytest.mark.parametrize("method", ["b1", "b2"])
def test_build_wave_task_context_rejects_wave4_when_third_wave_gain_exceeds_limit(
    method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.bdate_range(end="2026-04-01", periods=10),
            "close": [10.0 + 0.1 * idx for idx in range(10)],
        }
    )
    monkeypatch.setattr(
        cli,
        "classify_weekly_macd_wave",
        lambda _history, _pick_date: SimpleNamespace(label="wave3", reason="weekly ok", details={}),
    )
    monkeypatch.setattr(
        cli,
        "classify_daily_macd_wave",
        lambda _history, _pick_date: SimpleNamespace(
            label="wave4_end",
            reason="daily wave4",
            details={"third_wave_gain": 0.35},
        ),
    )

    context = cli._build_wave_task_context(history, "2026-04-01", method=method)

    assert f"不符合 {method} 候选要求" in context["wave_combo_context"]
    assert "35.0%" in context["wave_combo_context"]


def test_prompt_b1_requires_weekly_and_daily_wave_language() -> None:
    content = Path(".agents/skills/stock-select/references/prompt-b1.md").read_text(encoding="utf-8")

    assert "weekly_wave_context" in content
    assert "daily_wave_context" in content
    assert "wave_combo_context" in content
    assert "周线" in content
    assert "日线" in content
    assert "signal_reasoning" in content
    assert "符合 `b1`" in content or "符合 b1" in content
    assert "Output JSON format must remain identical to the default prompt contract" in content


def test_review_default_resolver_method_uses_resolver_prompt_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    method_key = _eod_key("2026-04-02", "b1")
    review_dir = runtime_root / "reviews" / method_key
    candidate_path = runtime_root / "candidates" / f"{method_key}.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-02",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "candidates": [{"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000002.SZ_day.png").write_bytes(b"png")

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, *, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol],
                "trade_date": pd.to_datetime(["2026-04-02"]),
                "open": [8.0],
                "high": [8.4],
                "low": [7.9],
                "close": [8.3],
                "vol": [210.0],
            }
        ),
    )

    prompt_path = str(tmp_path / "prompt-default-stub.md")
    resolver_methods: list[str] = []

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: resolver_methods.append(method)
        or SimpleNamespace(
            name="default",
            prompt_path=prompt_path,
            review_history=lambda **kwargs: {
                "review_type": "baseline",
                "total_score": 3.7,
                "signal_type": "rebound",
                "verdict": "WATCH",
                "comment": "default resolver baseline",
            },
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-02",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert resolver_methods == ["b1"]
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    assert tasks["method"] == "b1"
    assert tasks["prompt_path"] == prompt_path
    assert tasks["max_concurrency"] == 6
    assert tasks["tasks"][0]["prompt_path"] == prompt_path
    assert tasks["tasks"][0]["code"] == "000002.SZ"


def test_review_intraday_rejects_prepared_cache_metadata_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08+08-00")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
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
                    "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                    "mode": "not_intraday_snapshot",
                },
            },
        )

    result = runner.invoke(app, ["review", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code != 0
    assert "prepared intraday cache metadata mismatch" in result.stderr.lower()


def test_record_watch_writes_csv_from_pass_and_watch_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-10")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b1",
                "recommendations": [
                    {
                        "code": "AAA.SZ",
                        "verdict": "PASS",
                        "total_score": 4.8,
                        "signal_type": "trend_start",
                        "comment": "go",
                    }
                ],
                "excluded": [
                    {
                        "code": "BBB.SZ",
                        "verdict": "WATCH",
                        "total_score": 3.8,
                        "signal_type": "rebound",
                        "comment": "wait",
                    },
                    {
                        "code": "CCC.SZ",
                        "verdict": "FAIL",
                        "total_score": 2.1,
                        "signal_type": "distribution_risk",
                        "comment": "skip",
                    },
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_today_local_date", lambda: "2026-04-14")
    monkeypatch.setattr(cli, "_recorded_at_timestamp", lambda: "2026-04-14T16:21:22+08:00")
    monkeypatch.setattr(
        cli,
        "fetch_nth_latest_trade_date",
        lambda _connection, *, end_date, n: "2026-04-14" if n == 1 else "2026-04-01",
    )
    monkeypatch.setattr(
        cli,
        "fetch_available_trade_dates",
        lambda _connection: pd.DataFrame(
            {"trade_date": ["2026-04-14", "2026-04-10", "2026-04-09", "2026-04-08", "2026-04-07", "2026-04-03", "2026-04-02", "2026-04-01", "2026-03-31", "2026-03-30"]}
        ),
    )

    result = runner.invoke(
        app,
        [
            "record-watch",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    csv_path = runtime_root / "watch_pool.csv"
    assert result.exit_code == 0
    assert result.stdout.strip() == str(csv_path)
    rows = pd.read_csv(csv_path).to_dict(orient="records")
    assert [row["code"] for row in rows] == ["AAA.SZ", "BBB.SZ"]
    assert [row["verdict"] for row in rows] == ["PASS", "WATCH"]
    assert all(row["recorded_at"] == "2026-04-14T16:21:22+08:00" for row in rows)


def test_record_watch_rejects_duplicate_without_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-10")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b1",
                "recommendations": [],
                "excluded": [
                    {
                        "code": "AAA.SZ",
                        "verdict": "WATCH",
                        "total_score": 3.6,
                        "signal_type": "rebound",
                        "comment": "updated",
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "method": "b1",
                "pick_date": "2026-04-10",
                "code": "AAA.SZ",
                "verdict": "PASS",
                "total_score": 4.2,
                "signal_type": "trend_start",
                "comment": "existing",
                "recorded_at": "2026-04-11T10:00:00+08:00",
            }
        ]
    ).to_csv(runtime_root / "watch_pool.csv", index=False)

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_today_local_date", lambda: "2026-04-14")
    monkeypatch.setattr(cli, "_recorded_at_timestamp", lambda: "2026-04-14T16:21:22+08:00")
    monkeypatch.setattr(
        cli,
        "fetch_nth_latest_trade_date",
        lambda _connection, *, end_date, n: "2026-04-14" if n == 1 else "2026-04-01",
    )
    monkeypatch.setattr(
        cli,
        "fetch_available_trade_dates",
        lambda _connection: pd.DataFrame(
            {"trade_date": ["2026-04-14", "2026-04-10", "2026-04-09", "2026-04-08", "2026-04-07", "2026-04-03", "2026-04-02", "2026-04-01", "2026-03-31", "2026-03-30"]}
        ),
    )

    result = runner.invoke(
        app,
        [
            "record-watch",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--no-overwrite",
        ],
    )

    assert result.exit_code != 0
    assert "duplicate" in result.stderr.lower()


def test_record_watch_overwrites_and_trims_old_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-10")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b1",
                "recommendations": [
                    {
                        "code": "AAA.SZ",
                        "verdict": "PASS",
                        "total_score": 4.9,
                        "signal_type": "trend_start",
                        "comment": "fresh",
                    }
                ],
                "excluded": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "method": "b1",
                "pick_date": "2026-04-10",
                "code": "AAA.SZ",
                "verdict": "WATCH",
                "total_score": 3.7,
                "signal_type": "rebound",
                "comment": "stale",
                "recorded_at": "2026-04-11T10:00:00+08:00",
            },
            {
                "method": "b1",
                "pick_date": "2026-03-20",
                "code": "OLD.SZ",
                "verdict": "WATCH",
                "total_score": 3.1,
                "signal_type": "rebound",
                "comment": "old",
                "recorded_at": "2026-03-20T10:00:00+08:00",
            },
        ]
    ).to_csv(runtime_root / "watch_pool.csv", index=False)

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_today_local_date", lambda: "2026-04-14")
    monkeypatch.setattr(cli, "_recorded_at_timestamp", lambda: "2026-04-14T16:21:22+08:00")
    monkeypatch.setattr(
        cli,
        "fetch_nth_latest_trade_date",
        lambda _connection, *, end_date, n: "2026-04-14" if n == 1 else "2026-04-01",
    )
    monkeypatch.setattr(
        cli,
        "fetch_available_trade_dates",
        lambda _connection: pd.DataFrame(
            {"trade_date": ["2026-04-14", "2026-04-10", "2026-04-09", "2026-04-08", "2026-04-07", "2026-04-03", "2026-04-02", "2026-04-01", "2026-03-31", "2026-03-30"]}
        ),
    )

    result = runner.invoke(
        app,
        [
            "record-watch",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--window-trading-days",
            "10",
            "--overwrite",
        ],
    )

    rows = pd.read_csv(runtime_root / "watch_pool.csv").to_dict(orient="records")
    assert result.exit_code == 0
    assert rows == [
        {
            "method": "b1",
            "pick_date": "2026-04-10",
            "code": "AAA.SZ",
            "verdict": "PASS",
            "total_score": 4.9,
            "signal_type": "trend_start",
            "comment": "fresh",
            "recorded_at": "2026-04-14T16:21:22+08:00",
        }
    ]


def test_record_watch_sorts_rows_by_trade_day_distance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-10")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b1",
                "recommendations": [],
                "excluded": [
                    {
                        "code": "CCC.SZ",
                        "verdict": "WATCH",
                        "total_score": 3.2,
                        "signal_type": "rebound",
                        "comment": "third",
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "method": "b1",
                "pick_date": "2026-04-09",
                "code": "AAA.SZ",
                "verdict": "WATCH",
                "total_score": 3.5,
                "signal_type": "rebound",
                "comment": "near",
                "recorded_at": "2026-04-09T10:00:00+08:00",
            },
            {
                "method": "b1",
                "pick_date": "2026-04-08",
                "code": "BBB.SZ",
                "verdict": "WATCH",
                "total_score": 3.4,
                "signal_type": "rebound",
                "comment": "mid",
                "recorded_at": "2026-04-08T10:00:00+08:00",
            },
        ]
    ).to_csv(runtime_root / "watch_pool.csv", index=False)

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_today_local_date", lambda: "2026-04-14")
    monkeypatch.setattr(cli, "_recorded_at_timestamp", lambda: "2026-04-14T16:21:22+08:00")
    monkeypatch.setattr(
        cli,
        "fetch_nth_latest_trade_date",
        lambda _connection, *, end_date, n: "2026-04-14" if n == 1 else "2026-04-01",
    )
    monkeypatch.setattr(
        cli,
        "fetch_available_trade_dates",
        lambda _connection: pd.DataFrame(
            {"trade_date": ["2026-04-14", "2026-04-10", "2026-04-09", "2026-04-08", "2026-04-07", "2026-04-03", "2026-04-02", "2026-04-01", "2026-03-31", "2026-03-30"]}
        ),
    )

    result = runner.invoke(
        app,
        [
            "record-watch",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    rows = pd.read_csv(runtime_root / "watch_pool.csv").to_dict(orient="records")
    assert result.exit_code == 0
    assert [row["code"] for row in rows] == ["CCC.SZ", "AAA.SZ", "BBB.SZ"]


def test_readme_mentions_record_watch_and_new_runtime_root() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "record-watch" in content
    assert "~/.agents/skills/stock-select/runtime" in content


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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
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
    assert (runtime_root / "reviews" / _eod_key("2026-04-01") / "summary.json").exists()
    assert "[run] step=screen start" in result.stderr
    assert "[run] step=screen done" in result.stderr
    assert "[run] step=chart start" in result.stderr
    assert "[run] step=review done" in result.stderr
    assert "elapsed=" in result.stderr


def test_run_accepts_pool_source_and_passes_it_to_screen_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    calls: list[tuple[str, str]] = []

    def fake_screen_impl(**kwargs: object) -> Path:
        assert kwargs["method"] == "b1"
        assert kwargs["pick_date"] == "2026-04-01"
        assert kwargs["dsn"] == "postgresql://example"
        assert kwargs["runtime_root"] == runtime_root
        assert kwargs["pool_source"] == "record-watch"
        calls.append(("screen", kwargs["pool_source"]))  # type: ignore[arg-type]
        return runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json"

    def fake_chart_impl(
        *,
        method: str,
        pick_date: str,
        dsn: str | None,
        runtime_root: Path,
        reporter: object | None = None,
    ) -> Path:
        assert method == "b1"
        assert pick_date == "2026-04-01"
        assert dsn == "postgresql://example"
        assert runtime_root == tmp_path / "runtime"
        calls.append(("chart", method))
        return runtime_root / "charts" / _eod_key("2026-04-01")

    def fake_review_impl(
        *,
        method: str,
        pick_date: str,
        dsn: str | None,
        runtime_root: Path,
        llm_min_baseline_score: float | None = None,
        reporter: object | None = None,
    ) -> Path:
        assert method == "b1"
        assert pick_date == "2026-04-01"
        assert dsn == "postgresql://example"
        assert runtime_root == tmp_path / "runtime"
        assert llm_min_baseline_score is None
        calls.append(("review", method))
        return runtime_root / "reviews" / _eod_key("2026-04-01") / "summary.json"

    monkeypatch.setattr(cli, "_screen_impl", fake_screen_impl)
    monkeypatch.setattr(cli, "_chart_impl", fake_chart_impl)
    monkeypatch.setattr(cli, "_review_impl", fake_review_impl)

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--pool-source",
            " record-watch ",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        ("screen", "record-watch"),
        ("chart", "b1"),
        ("review", "b1"),
    ]


def test_run_passes_llm_min_baseline_score_to_review_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    calls: list[tuple[str, object | None]] = []

    monkeypatch.setattr(
        cli,
        "_screen_impl",
        lambda **kwargs: runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json",
    )
    monkeypatch.setattr(
        cli,
        "_chart_impl",
        lambda **kwargs: runtime_root / "charts" / _eod_key("2026-04-01"),
    )

    def fake_review_impl(
        *,
        method: str,
        pick_date: str,
        dsn: str | None,
        runtime_root: Path,
        llm_min_baseline_score: float | None = None,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("review", llm_min_baseline_score))
        return runtime_root / "reviews" / _eod_key("2026-04-01") / "summary.json"

    monkeypatch.setattr(cli, "_review_impl", fake_review_impl)

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--llm-min-baseline-score",
            "4.0",
        ],
    )

    assert result.exit_code == 0
    assert calls == [("review", 4.0)]


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
        method: str,
        dsn: str | None,
        tushare_token: str | None,
        runtime_root: Path,
        pool_source: str,
        pool_file: Path | None,
        recompute: bool = False,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("screen", tushare_token))
        assert method == "b1"
        assert dsn == "postgresql://example"
        assert tushare_token == "token"
        assert runtime_root == tmp_path / "runtime"
        assert pool_source == "turnover-top"
        assert pool_file is None
        assert recompute is False
        return runtime_root / "candidates" / f"{_intraday_key('2026-04-09T11-31-08-123456+08-00')}.json"

    def fake_chart_intraday_impl(
        *,
        method: str,
        runtime_root: Path,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("chart", None))
        assert method == "b1"
        assert runtime_root == tmp_path / "runtime"
        return runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08-123456+08-00")

    def fake_review_intraday_impl(
        *,
        method: str,
        runtime_root: Path,
        llm_min_baseline_score: float | None = None,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("review", method))
        assert runtime_root == tmp_path / "runtime"
        assert llm_min_baseline_score is None
        return runtime_root / "reviews" / _intraday_key("2026-04-09T11-31-08-123456+08-00") / "summary.json"

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
        str(runtime_root / "candidates" / f"{_intraday_key('2026-04-09T11-31-08-123456+08-00')}.json"),
        str(runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08-123456+08-00")),
        str(runtime_root / "reviews" / _intraday_key("2026-04-09T11-31-08-123456+08-00") / "summary.json"),
    ]


def test_run_intraday_warns_outside_trading_hours(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 15:30:00", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "_screen_intraday_impl",
        lambda **kwargs: tmp_path / "candidates" / "fake.json",
    )
    monkeypatch.setattr(
        cli,
        "_chart_intraday_impl",
        lambda **kwargs: tmp_path / "charts" / "fake",
    )
    monkeypatch.setattr(
        cli,
        "_review_intraday_impl",
        lambda **kwargs: tmp_path / "reviews" / "fake.json",
    )

    result = runner.invoke(
        app,
        ["run", "--method", "b1", "--intraday", "--runtime-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "outside trading-day intraday market hours" in result.stderr


def test_run_intraday_accepts_pool_source_and_passes_it_to_intraday_screen_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    calls: list[tuple[str, str]] = []

    def fake_screen_intraday_impl(
        *,
        method: str,
        dsn: str | None,
        tushare_token: str | None,
        runtime_root: Path,
        pool_source: str,
        pool_file: Path | None,
        recompute: bool = False,
        reporter: object | None = None,
    ) -> Path:
        assert method == "b1"
        assert dsn == "postgresql://example"
        assert tushare_token == "token"
        assert runtime_root == tmp_path / "runtime"
        assert pool_source == "record-watch"
        assert pool_file is None
        assert recompute is False
        calls.append(("screen", pool_source))
        return runtime_root / "candidates" / f"{_intraday_key('2026-04-09T11-31-08-123456+08-00')}.json"

    def fake_chart_intraday_impl(
        *,
        method: str,
        runtime_root: Path,
        reporter: object | None = None,
    ) -> Path:
        assert method == "b1"
        assert runtime_root == tmp_path / "runtime"
        calls.append(("chart", method))
        return runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08-123456+08-00")

    def fake_review_intraday_impl(
        *,
        method: str,
        runtime_root: Path,
        llm_min_baseline_score: float | None = None,
        reporter: object | None = None,
    ) -> Path:
        assert method == "b1"
        assert runtime_root == tmp_path / "runtime"
        assert llm_min_baseline_score is None
        calls.append(("review", method))
        return runtime_root / "reviews" / _intraday_key("2026-04-09T11-31-08-123456+08-00") / "summary.json"

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
            "--pool-source",
            " record-watch ",
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
        ("screen", "record-watch"),
        ("chart", "b1"),
        ("review", "b1"),
    ]
    assert "[run] step=screen start" in result.stderr


def test_run_accepts_custom_pool_file_and_passes_it_to_screen_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    pool_file = tmp_path / "custom-pool.txt"
    calls: list[tuple[str, str]] = []

    def fake_screen_impl(**kwargs: object) -> Path:
        assert kwargs["method"] == "b1"
        assert kwargs["pick_date"] == "2026-04-01"
        assert kwargs["dsn"] == "postgresql://example"
        assert kwargs["runtime_root"] == runtime_root
        assert kwargs["pool_source"] == "custom"
        assert kwargs["pool_file"] == pool_file
        calls.append(("screen", kwargs["pool_source"]))  # type: ignore[arg-type]
        return runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json"

    def fake_chart_impl(
        *,
        method: str,
        pick_date: str,
        dsn: str | None,
        runtime_root: Path,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("chart", method))
        return runtime_root / "charts" / _eod_key("2026-04-01")

    def fake_review_impl(
        *,
        method: str,
        pick_date: str,
        dsn: str | None,
        runtime_root: Path,
        llm_min_baseline_score: float | None = None,
        reporter: object | None = None,
    ) -> Path:
        assert llm_min_baseline_score is None
        calls.append(("review", method))
        return runtime_root / "reviews" / _eod_key("2026-04-01") / "summary.json"

    monkeypatch.setattr(cli, "_screen_impl", fake_screen_impl)
    monkeypatch.setattr(cli, "_chart_impl", fake_chart_impl)
    monkeypatch.setattr(cli, "_review_impl", fake_review_impl)

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--pool-source",
            " custom ",
            "--pool-file",
            str(pool_file),
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        ("screen", "custom"),
        ("chart", "b1"),
        ("review", "b1"),
    ]
    assert "[run] step=chart start" in result.stderr
    assert "[run] step=review done" in result.stderr


def test_review_merge_combines_baseline_and_llm_results(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-01")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "000001.SZ.json").write_text(
        json.dumps(
            {
                "code": "000001.SZ",
                "pick_date": "2026-04-01",
                "chart_path": str(runtime_root / "charts" / _eod_key("2026-04-01") / "000001.SZ_day.png"),
                "review_mode": "baseline_local",
                "llm_review": None,
                "baseline_review": {
                    "review_type": "baseline",
                    "trend_structure": 3.0,
                    "price_position": 3.0,
                    "volume_behavior": 3.0,
                    "previous_abnormal_move": 4.0,
                    "macd_phase": 4.0,
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
                "macd_reasoning": "MACD 进入启动阶段",
                "signal_reasoning": "更像主升启动",
                "scores": {
                    "trend_structure": 5,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                    "macd_phase": 5,
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
    assert merged["baseline_review"] == {
        "review_type": "baseline",
        "trend_structure": 3.0,
        "price_position": 3.0,
        "volume_behavior": 3.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 4.0,
        "total_score": 3.4,
        "signal_type": "rebound",
        "verdict": "WATCH",
        "comment": "baseline",
    }
    assert merged["llm_review"]["verdict"] == "PASS"
    assert merged["llm_review"]["total_score"] == 4.62
    assert merged["llm_review"]["scores"] == {
        "trend_structure": 5.0,
        "price_position": 4.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 5.0,
    }
    assert merged["final_score"] == 4.13
    assert merged["total_score"] == 4.13
    assert merged["verdict"] == "PASS"
    assert summary["recommendations"][0]["code"] == "000001.SZ"
    assert "[review-merge] merged reviews=1 failures=0" in result.stderr


def test_review_merge_can_limit_merge_to_selected_codes(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-01")
    review_dir.mkdir(parents=True, exist_ok=True)
    for code in ("000001.SZ", "000002.SZ"):
        (review_dir / f"{code}.json").write_text(
            json.dumps(
                {
                    "code": code,
                    "pick_date": "2026-04-01",
                    "chart_path": str(runtime_root / "charts" / _eod_key("2026-04-01") / f"{code}_day.png"),
                    "review_mode": "baseline_local",
                    "llm_review": None,
                    "baseline_review": {
                        "review_type": "baseline",
                        "trend_structure": 3.0,
                        "price_position": 3.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 4.0,
                        "macd_phase": 4.0,
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
                "macd_reasoning": "MACD 进入启动阶段",
                "signal_reasoning": "更像主升启动",
                "scores": {
                    "trend_structure": 5,
                    "price_position": 4,
                    "volume_behavior": 5,
                    "previous_abnormal_move": 4,
                    "macd_phase": 5,
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
    assert merged["llm_review"]["total_score"] == 4.62
    assert untouched["review_mode"] == "baseline_local"
    assert untouched["baseline_review"] == {
        "review_type": "baseline",
        "trend_structure": 3.0,
        "price_position": 3.0,
        "volume_behavior": 3.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 4.0,
        "total_score": 3.4,
        "signal_type": "rebound",
        "verdict": "WATCH",
        "comment": "baseline",
    }
    assert summary["failures"] == []
    assert "[review-merge] merged reviews=2 failures=0" in result.stderr


def test_review_merge_selected_codes_does_not_fail_missing_unselected_results(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-01")
    review_dir.mkdir(parents=True, exist_ok=True)
    for code in ("000001.SZ", "000002.SZ"):
        (review_dir / f"{code}.json").write_text(
            json.dumps(
                {
                    "code": code,
                    "pick_date": "2026-04-01",
                    "chart_path": str(runtime_root / "charts" / _eod_key("2026-04-01") / f"{code}_day.png"),
                    "review_mode": "baseline_local",
                    "llm_review": None,
                    "baseline_review": {
                        "review_type": "baseline",
                        "trend_structure": 3.0,
                        "price_position": 3.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 4.0,
                        "macd_phase": 4.0,
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
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-01")
    chart_dir = runtime_root / "charts" / _eod_key("2026-04-01")
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
                            "macd_reasoning": "MACD 处于加强阶段",
                            "signal_reasoning": "主升启动",
                            "trend_structure": 4,
                            "price_position": 3,
                            "volume_behavior": 4,
                            "previous_abnormal_move": 4,
                            "macd_phase": 4,
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
                            "macd_phase": 5,
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
        assert "B1 Summary" in html_text
        assert "000001.SZ" in html_text
        assert "平安银行" in html_text
        assert "merged comment" in html_text
        assert "macd_phase" in html_text
        assert "MACD" in html_text
        assert "MACD 处于加强阶段" in html_text


def test_render_html_uses_hcr_method_label(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / _eod_key("2026-04-01", "hcr")
    chart_dir = runtime_root / "charts" / _eod_key("2026-04-01", "hcr")
    review_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png-bytes")
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "hcr",
                "reviewed_count": 1,
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "pick_date": "2026-04-01",
                        "chart_path": str(chart_dir / "000001.SZ_day.png"),
                        "review_mode": "baseline_local",
                        "baseline_review": {
                            "trend_structure": 4,
                            "price_position": 4,
                            "volume_behavior": 4,
                            "previous_abnormal_move": 4,
                            "macd_phase": 3,
                            "total_score": 4.0,
                            "signal_type": "trend_start",
                            "verdict": "PASS",
                            "comment": "baseline",
                        },
                        "llm_review": None,
                        "total_score": 4.0,
                        "signal_type": "trend_start",
                        "verdict": "PASS",
                        "comment": "hcr comment",
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
            "hcr",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    with zipfile.ZipFile(Path(result.stdout.strip())) as archive:
        html_text = archive.read("summary.html").decode("utf-8")
        assert "HCR Summary" in html_text


def test_screen_requires_dsn_when_real_data_fetch_is_needed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
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
                    "chg_d": [1.0, 1.0],
                    "amp_d": [2.0, 2.0],
                    "body_d": [-1.0, -1.0],
                    "vm3": [90.0, 90.0],
                    "vm5": [100.0, 100.0],
                    "vm10": [120.0, 120.0],
                    "m5": [10.2, 10.5],
                    "v_shrink": [True, True],
                    "safe_mode": [True, True],
                    "lt_filter": [True, True],
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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [9.2],
                    "v_shrink": [False],
                    "safe_mode": [False],
                    "lt_filter": [False],
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
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json").read_text(encoding="utf-8"))
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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
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
            _b1_screen_stats(
                total_symbols=10,
                eligible=8,
                selected=1,
                fail_j=2,
                fail_insufficient_history=3,
                fail_close_zxdkx=1,
                fail_zxdq_zxdkx=2,
                fail_weekly_ma=1,
                fail_max_vol=1,
                fail_chg_cap=4,
                fail_v_shrink=5,
                fail_safe_mode=6,
                fail_lt_filter=7,
            ),
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
        "fail_close_zxdkx=1 fail_zxdq_zxdkx=2 fail_weekly_ma=1 fail_max_vol=1 "
        "fail_chg_cap=4 fail_v_shrink=5 fail_safe_mode=6 fail_lt_filter=7 selected=1"
    ) in result.stderr


def test_screen_rejects_placeholder_end_of_day_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda connection, *, start_date, end_date, symbols=None: pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-14"]),
                "open": [None],
                "high": [None],
                "low": [None],
                "close": [None],
                "vol": [None],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "fetch_nth_latest_trade_date",
        lambda _connection, *, end_date, n: "2026-04-13",
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-14",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "incomplete end-of-day rows for pick_date 2026-04-14" in result.stderr
    assert "Latest complete trade date is 2026-04-13" in result.stderr


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
    assert {"dif", "dea", "macd_hist"}.issubset(prepared["000001.SZ"].columns)
    assert prepared["000001.SZ"]["dif"].notna().all()
    assert prepared["000001.SZ"]["dea"].notna().all()
    assert prepared["000001.SZ"]["macd_hist"].notna().all()


def test_prepared_cache_round_trip(tmp_path: Path) -> None:
    cache_path = tmp_path / "prepared" / f"{_eod_key('2026-04-01')}.pkl"
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


def test_prepared_cache_path_uses_shared_eod_file_for_b1_and_b2(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"

    assert cli._prepared_cache_path(runtime_root, "2026-04-01", "b1") == runtime_root / "prepared" / "2026-04-01.pkl"
    assert cli._prepared_cache_path(runtime_root, "2026-04-01", "b2") == runtime_root / "prepared" / "2026-04-01.pkl"
    assert cli._prepared_cache_path(runtime_root, "2026-04-01", "dribull") == runtime_root / "prepared" / "2026-04-01.pkl"
    assert cli._prepared_cache_path(runtime_root, "2026-04-01", "hcr") == runtime_root / "prepared" / "2026-04-01.hcr.pkl"


def test_prepared_cache_path_uses_shared_intraday_file_for_b1_and_b2(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"

    assert (
        cli._prepared_cache_path(runtime_root, "2026-04-09.intraday", "b1")
        == runtime_root / "prepared" / "2026-04-09.intraday.pkl"
    )
    assert (
        cli._prepared_cache_path(runtime_root, "2026-04-09.intraday", "b2")
        == runtime_root / "prepared" / "2026-04-09.intraday.pkl"
    )
    assert (
        cli._prepared_cache_path(runtime_root, "2026-04-09.intraday", "dribull")
        == runtime_root / "prepared" / "2026-04-09.intraday.pkl"
    )
    assert (
        cli._prepared_cache_path(runtime_root, "2026-04-09.intraday", "hcr")
        == runtime_root / "prepared" / "2026-04-09.intraday.hcr.pkl"
    )


def test_prepare_screen_data_adds_b1_tightening_columns() -> None:
    importlib.reload(cli)

    trade_dates = pd.date_range("2025-10-01", periods=130, freq="B")
    close = [10.0 + idx * 0.05 for idx in range(len(trade_dates))]
    market = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * len(trade_dates),
            "trade_date": trade_dates,
            "open": [value - 0.08 for value in close],
            "high": [value + 0.15 for value in close],
            "low": [value - 0.20 for value in close],
            "close": close,
            "vol": [1000.0] * 127 + [900.0, 850.0, 800.0],
        }
    )

    prepared = cli._prepare_screen_data(market)

    frame = prepared["000001.SZ"]
    row = frame.iloc[-1]
    assert {
        "chg_d",
        "amp_d",
        "body_d",
        "vm3",
        "vm5",
        "vm10",
        "m5",
        "v_shrink",
        "safe_mode",
        "lt_filter",
    }.issubset(frame.columns)
    assert round(float(row["chg_d"]), 4) == round((close[-1] - close[-2]) / close[-2] * 100.0, 4)
    assert bool(row["v_shrink"]) is True
    assert bool(row["safe_mode"]) is True
    assert bool(row["lt_filter"]) is True


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
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
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
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["BBB.SZ"]


def test_screen_uses_reference_dribull_defaults_shared_prep_and_liquidity_pool(tmp_path: Path) -> None:
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
                "trade_date": pd.to_datetime(["2026-04-10", "2026-04-10"]),
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
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "turnover_n": [100.0],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "low": [10.3],
                    "close": [10.6],
                    "volume": [100.0],
                    "ma25": [10.5],
                    "ma60": [10.4],
                    "ma144": [9.6],
                    "dif": [0.11],
                    "dea": [0.08],
                    "dif_w": [0.20],
                    "dea_w": [0.15],
                    "dif_m": [0.30],
                    "dea_m": [0.22],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "turnover_n": [200.0],
                    "J": [10.0],
                    "zxdq": [11.5],
                    "zxdkx": [11.2],
                    "low": [11.3],
                    "close": [11.6],
                    "volume": [120.0],
                    "ma25": [11.5],
                    "ma60": [11.4],
                    "ma144": [10.6],
                    "dif": [0.21],
                    "dea": [0.18],
                    "dif_w": [0.30],
                    "dea_w": [0.25],
                    "dif_m": [0.40],
                    "dea_m": [0.32],
                }
            ),
        }

    def fake_pool(prepared_by_symbol: dict[str, pd.DataFrame], top_m: int):
        assert top_m == 5000
        assert sorted(prepared_by_symbol) == ["AAA.SZ", "BBB.SZ"]
        return {pd.Timestamp("2026-04-10"): ["BBB.SZ"]}

    def fake_run_dribull_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["BBB.SZ"]
        assert pick_date == pd.Timestamp("2026-04-10")
        assert config == {"j_threshold": 15.0, "j_q_threshold": 0.10}
        return (
            [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 11.6, "turnover_n": 200.0}],
            _dribull_wave_stats(total_symbols=1, eligible=1, selected=1),
        )

    original_connect = cli._connect
    original_fetch = cli.fetch_daily_window
    original_prepare = cli._prepare_screen_data
    original_pool = cli.build_top_turnover_pool
    original_prefilter = cli.prefilter_dribull_non_macd
    original_run = cli.run_dribull_screen_with_stats

    cli._connect = fake_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fake_fetch_daily_window  # type: ignore[assignment]
    cli._prepare_screen_data = fake_prepare_screen_data  # type: ignore[assignment]
    cli.build_top_turnover_pool = fake_pool  # type: ignore[assignment]
    cli.prefilter_dribull_non_macd = lambda prepared_by_symbol, pick_date, config=None: ["BBB.SZ"]  # type: ignore[assignment]
    cli.run_dribull_screen_with_stats = fake_run_dribull_screen_with_stats  # type: ignore[assignment]

    try:
        result = runner.invoke(
            app,
            [
                "screen",
                "--method",
                "dribull",
                "--pick-date",
                "2026-04-10",
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
        cli.prefilter_dribull_non_macd = original_prefilter  # type: ignore[assignment]
        cli.run_dribull_screen_with_stats = original_run  # type: ignore[assignment]

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'dribull')}.json").read_text(encoding="utf-8"))
    assert payload["method"] == "dribull"
    assert [item["code"] for item in payload["candidates"]] == ["BBB.SZ"]


def test_screen_dribull_real_flow_uses_shared_prep_and_liquidity_pool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)
    valid_dribull_close = [12.0] * 146 + [11.8, 11.7, 11.9, 12.1, 12.4, 12.8, 13.1, 13.4, 13.2, 13.0, 12.9, 12.92, 12.97, 13.02]
    closes_by_code = {
        "AAA.SZ": [10.0 + 0.02 * idx for idx in range(len(trade_dates))],
        "BBB.SZ": valid_dribull_close,
    }

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        market_rows: list[dict[str, object]] = []
        for code in ("AAA.SZ", "BBB.SZ"):
            for idx, trade_date in enumerate(trade_dates):
                close = closes_by_code[code][idx]
                market_rows.append(
                    {
                        "ts_code": code,
                        "trade_date": trade_date,
                        "open": close - 0.1,
                        "high": close + 0.2,
                        "low": close - 0.2 if idx < len(trade_dates) - 1 else (12.40 if code == "BBB.SZ" else close - 0.30),
                        "close": close,
                        "vol": 100.0 + idx if idx < len(trade_dates) - 1 else 50.0,
                    }
                )
        return pd.DataFrame(market_rows)

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        prepared: dict[str, pd.DataFrame] = {}
        for code, group in market.groupby("ts_code"):
            group = group.sort_values("trade_date").reset_index(drop=True).copy()
            group["turnover_n"] = 100.0 if code == "AAA.SZ" else 200.0
            group["J"] = 10.0
            group["zxdq"] = group["close"] + 0.3
            group["zxdkx"] = group["close"] - 0.1
            group["low"] = group["close"] - 0.2
            group["volume"] = group["vol"]
            group["ma25"] = group["close"]
            group["ma60"] = group["close"]
            group["ma144"] = group["close"]
            prepared[code] = group
        return prepared

    run_calls: list[list[str]] = []

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-10"): ["BBB.SZ"]},
    )
    monkeypatch.setattr(cli, "prefilter_dribull_non_macd", lambda prepared_by_symbol, pick_date, config=None: ["BBB.SZ"])
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            run_calls.append(sorted(prepared_by_symbol))
            or [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 13.02, "turnover_n": 359.0}],
            _dribull_wave_stats(total_symbols=len(prepared_by_symbol), eligible=len(prepared_by_symbol), selected=1),
        ),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'dribull')}.json").read_text(encoding="utf-8"))
    assert payload["method"] == "dribull"
    assert run_calls == [["BBB.SZ"]]
    assert [item["code"] for item in payload["candidates"]] == ["BBB.SZ"]


def test_screen_dribull_uses_longer_warmup_start_date_for_period_macd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    fetch_calls: list[dict[str, object]] = []
    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        fetch_calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "symbols": None if symbols is None else list(symbols),
            }
        )
        return pd.DataFrame(
            {
                "ts_code": ["BBB.SZ"] * len(trade_dates),
                "trade_date": trade_dates,
                "open": [10.0] * len(trade_dates),
                "high": [10.2] * len(trade_dates),
                "low": [10.0 + 0.02 * idx - 0.1 for idx in range(len(trade_dates))],
                "close": [10.0 + 0.02 * idx for idx in range(len(trade_dates))],
                "vol": [100.0 + idx for idx in range(len(trade_dates) - 1)] + [100.0 + len(trade_dates) - 2],
            }
        )

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(
        cli,
        "_prepare_screen_data",
        lambda market, reporter=None: {
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [13.18],
                    "J": [10.0],
                    "zxdq": [13.4],
                    "zxdkx": [13.0],
                    "low": [13.0],
                    "volume": [120.0],
                    "vol": [120.0],
                    "ma25": [13.0],
                    "ma60": [12.8],
                    "ma144": [12.6],
                    "turnover_n": [200.0],
                }
            )
        },
    )
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-10"): ["BBB.SZ"]},
    )
    monkeypatch.setattr(cli, "prefilter_dribull_non_macd", lambda prepared_by_symbol, pick_date, config=None: ["BBB.SZ"])
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 13.18, "turnover_n": 200.0}],
            _dribull_wave_stats(total_symbols=1, eligible=1, selected=1),
        ),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert fetch_calls[-1] == {"start_date": "2023-01-01", "end_date": "2026-04-10", "symbols": ["BBB.SZ"]}


def test_screen_dribull_uses_two_phase_fetch_and_only_warms_pool_symbols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)
    fetch_calls: list[dict[str, object]] = []
    prepared_calls: list[list[str]] = []
    run_inputs: dict[str, pd.DataFrame] = {}

    def fake_connect(_: str) -> object:
        return object()

    def _market_frame(symbols: list[str]) -> pd.DataFrame:
        market_rows: list[dict[str, object]] = []
        for code, base in (("AAA.SZ", 10.0), ("BBB.SZ", 20.0), ("CCC.SZ", 30.0)):
            if code not in symbols:
                continue
            for idx, trade_date in enumerate(trade_dates):
                close = base + idx * 0.05
                market_rows.append(
                    {
                        "ts_code": code,
                        "trade_date": trade_date,
                        "open": close - 0.1,
                        "high": close + 0.2,
                        "low": close - 0.2,
                        "close": close,
                        "vol": 100.0 + idx,
                    }
                )
        return pd.DataFrame(market_rows)

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        request_symbols = ["AAA.SZ", "BBB.SZ", "CCC.SZ"] if symbols is None else list(symbols)
        fetch_calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "symbols": None if symbols is None else list(symbols),
            }
        )
        return _market_frame(request_symbols)

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        codes = sorted(market["ts_code"].unique().tolist())
        prepared_calls.append(codes)
        prepared: dict[str, pd.DataFrame] = {}
        for code, group in market.groupby("ts_code"):
            group = group.sort_values("trade_date").reset_index(drop=True).copy()
            group["turnover_n"] = 100.0 if code != "BBB.SZ" else 999.0
            group["J"] = 10.0
            group["zxdq"] = group["close"] + 0.3
            group["zxdkx"] = group["close"] - 0.1
            group["low"] = group["close"] - 0.2
            group["volume"] = group["vol"]
            group["ma25"] = group["close"]
            group["ma60"] = group["close"]
            group["ma144"] = group["close"]
            group["dif"] = 0.12
            group["dea"] = 0.08
            group["dif_w"] = 0.20
            group["dea_w"] = 0.15
            group["dif_m"] = 0.30
            group["dea_m"] = 0.22
            if code == "BBB.SZ":
                group.loc[group.index[-1], "volume"] = group.loc[group.index[-2], "volume"] - 1.0
                group.loc[group.index[-1], "vol"] = group.loc[group.index[-1], "volume"]
            prepared[code] = group
        return prepared

    pool_calls: list[list[str]] = []

    def fake_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        pool_calls.append(sorted(prepared_by_symbol))
        return {pd.Timestamp("2026-04-10"): ["BBB.SZ"]}

    def fake_run_dribull_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        run_inputs.update(prepared_by_symbol)
        return (
            [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 27.95, "turnover_n": 999.0}],
            _dribull_wave_stats(total_symbols=1, eligible=1, selected=1),
        )

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fake_pool)
    monkeypatch.setattr(cli, "run_dribull_screen_with_stats", fake_run_dribull_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert fetch_calls == [
        {"start_date": "2025-04-09", "end_date": "2026-04-10", "symbols": None},
        {"start_date": "2023-01-01", "end_date": "2026-04-10", "symbols": ["BBB.SZ"]},
    ]
    assert prepared_calls == [["AAA.SZ", "BBB.SZ", "CCC.SZ"], ["BBB.SZ"]]
    assert pool_calls == [["AAA.SZ", "BBB.SZ", "CCC.SZ"], ["BBB.SZ"]]
    assert sorted(run_inputs) == ["BBB.SZ"]


def test_screen_dribull_phase_one_prefilters_non_macd_rules_before_warmup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)
    fetch_calls: list[dict[str, object]] = []
    warmup_run_inputs: dict[str, pd.DataFrame] = {}

    def fake_connect(_: str) -> object:
        return object()

    def _market_frame(symbols: list[str]) -> pd.DataFrame:
        market_rows: list[dict[str, object]] = []
        for code, base in (("AAA.SZ", 10.0), ("BBB.SZ", 20.0), ("CCC.SZ", 30.0)):
            if code not in symbols:
                continue
            for idx, trade_date in enumerate(trade_dates):
                close = base + idx * 0.05
                market_rows.append(
                    {
                        "ts_code": code,
                        "trade_date": trade_date,
                        "open": close - 0.1,
                        "high": close + 0.2,
                        "low": close - 0.2,
                        "close": close,
                        "vol": 100.0 + idx,
                    }
                )
        return pd.DataFrame(market_rows)

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        request_symbols = ["AAA.SZ", "BBB.SZ", "CCC.SZ"] if symbols is None else list(symbols)
        fetch_calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "symbols": None if symbols is None else list(symbols),
            }
        )
        return _market_frame(request_symbols)

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        prepared: dict[str, pd.DataFrame] = {}
        for code, group in market.groupby("ts_code"):
            group = group.sort_values("trade_date").reset_index(drop=True).copy()
            group["turnover_n"] = 999.0
            group["J"] = 10.0
            group["zxdq"] = group["close"] + 0.3
            group["zxdkx"] = group["close"] - 0.1
            group["low"] = group["close"] - 0.2
            group["volume"] = group["vol"]
            group["ma25"] = group["close"]
            group["ma60"] = group["close"]
            group["ma144"] = group["close"]
            group["dif"] = 0.12
            group["dea"] = 0.08
            group["dif_w"] = 0.20
            group["dea_w"] = 0.15
            group["dif_m"] = 0.30
            group["dea_m"] = 0.22
            if code == "AAA.SZ":
                group.loc[group.index[-1], "zxdq"] = group.loc[group.index[-1], "zxdkx"] - 0.01
            elif code == "BBB.SZ":
                group.loc[group.index[-1], "volume"] = group.loc[group.index[-2], "volume"] - 1.0
                group.loc[group.index[-1], "vol"] = group.loc[group.index[-1], "volume"]
            elif code == "CCC.SZ":
                group.loc[group.index[-1], "volume"] = group.loc[group.index[-2], "volume"] + 1.0
                group.loc[group.index[-1], "vol"] = group.loc[group.index[-1], "volume"]
            prepared[code] = group
        return prepared

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            warmup_run_inputs.update(prepared_by_symbol) or [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 27.95, "turnover_n": 999.0}],
            _dribull_wave_stats(total_symbols=len(prepared_by_symbol), eligible=len(prepared_by_symbol), selected=1),
        ),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert fetch_calls == [
        {"start_date": "2025-04-09", "end_date": "2026-04-10", "symbols": None},
        {"start_date": "2023-01-01", "end_date": "2026-04-10", "symbols": ["BBB.SZ"]},
    ]
    assert sorted(warmup_run_inputs) == ["BBB.SZ"]


def test_screen_dribull_writes_prepared_cache_before_prefilter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)
    valid_dribull_close = [12.0] * 146 + [11.8, 11.7, 11.9, 12.1, 12.4, 12.8, 13.1, 13.4, 13.2, 13.0, 12.9, 12.92, 12.97, 13.02]

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        request_symbols = ["AAA.SZ", "BBB.SZ", "CCC.SZ"] if symbols is None else list(symbols)
        market_rows: list[dict[str, object]] = []
        for code, base in (("AAA.SZ", 10.0), ("BBB.SZ", 20.0), ("CCC.SZ", 30.0)):
            if code not in request_symbols:
                continue
            for idx, trade_date in enumerate(trade_dates):
                close = base + idx * 0.05
                market_rows.append(
                    {
                        "ts_code": code,
                        "trade_date": trade_date,
                        "open": close - 0.1,
                        "high": close + 0.2,
                        "low": close - 0.2,
                        "close": close,
                        "vol": 100.0 + idx,
                    }
                )
        return pd.DataFrame(market_rows)

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        prepared: dict[str, pd.DataFrame] = {}
        for code, group in market.groupby("ts_code"):
            group = group.sort_values("trade_date").reset_index(drop=True).copy()
            group["turnover_n"] = 999.0
            group["J"] = 10.0
            group["zxdq"] = group["close"] + 0.3
            group["zxdkx"] = group["close"] - 0.1
            group["low"] = group["close"] - 0.2
            group["volume"] = group["vol"]
            group["ma25"] = group["close"]
            group["ma60"] = group["close"]
            group["ma144"] = group["close"]
            group["dif"] = 0.12
            group["dea"] = 0.08
            group["dif_w"] = 0.20
            group["dea_w"] = 0.15
            group["dif_m"] = 0.30
            group["dea_m"] = 0.22
            prepared[code] = group
        return prepared

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "prefilter_dribull_non_macd", lambda prepared_by_symbol, pick_date, config=None: ["BBB.SZ"])
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 27.95, "turnover_n": 999.0}],
            _dribull_wave_stats(total_symbols=len(prepared_by_symbol), eligible=len(prepared_by_symbol), selected=1),
        ),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    cache_payload = cli._load_prepared_cache(runtime_root / "prepared" / "2026-04-10.pkl")
    assert cache_payload["start_date"] == "2025-04-09"
    assert sorted(cache_payload["prepared_by_symbol"]) == ["AAA.SZ", "BBB.SZ", "CCC.SZ"]


def test_screen_dribull_reuses_shared_b1_prepared_cache_for_phase_one(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    shared_prepared = {
        "BBB.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-10"]),
                "turnover_n": [200.0],
                "J": [10.0],
                "zxdq": [11.5],
                "zxdkx": [11.2],
                "low": [11.1],
                "close": [11.6],
                "ma25": [11.3],
                "ma60": [11.0],
                "ma144": [10.8],
                "dif": [0.12],
                "dea": [0.08],
                "dif_w": [0.20],
                "dea_w": [0.15],
                "dif_m": [0.30],
                "dea_m": [0.22],
                "volume": [120.0],
                "vol": [120.0],
            }
        )
    }
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-10.pkl",
        method="b1",
        pick_date="2026-04-10",
        start_date="2025-04-09",
        end_date="2026-04-10",
        prepared_by_symbol=shared_prepared,
    )

    original_connect = cli._connect
    original_fetch = cli.fetch_daily_window
    original_prepare = cli._prepare_screen_data
    original_prefilter = cli.prefilter_dribull_non_macd
    original_run = cli.run_dribull_screen_with_stats

    def fail_connect(_: str) -> object:
        raise AssertionError("dribull should reuse shared b1 prepared cache before phase-two warmup")

    def fail_fetch(*args, **kwargs):
        raise AssertionError("dribull should not fetch market window when shared prepared cache is reusable")

    def fail_prepare(_: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        raise AssertionError("dribull should not recompute phase-one prepare when shared prepared cache is reusable")

    def fake_prefilter_dribull_non_macd(prepared_by_symbol: dict[str, pd.DataFrame], pick_date: pd.Timestamp, config=None) -> list[str]:
        assert list(prepared_by_symbol) == ["BBB.SZ"]
        return []

    def fake_run_dribull_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert prepared_by_symbol == {}
        return (
            [],
            _dribull_wave_stats(total_symbols=0, eligible=0, selected=0),
        )

    cli._connect = fail_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fail_fetch  # type: ignore[assignment]
    cli._prepare_screen_data = fail_prepare  # type: ignore[assignment]
    cli.prefilter_dribull_non_macd = fake_prefilter_dribull_non_macd  # type: ignore[assignment]
    cli.run_dribull_screen_with_stats = fake_run_dribull_screen_with_stats  # type: ignore[assignment]

    try:
        result = runner.invoke(
            app,
            [
                "screen",
                "--method",
                "dribull",
                "--pick-date",
                "2026-04-10",
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
        cli.prefilter_dribull_non_macd = original_prefilter  # type: ignore[assignment]
        cli.run_dribull_screen_with_stats = original_run  # type: ignore[assignment]

    assert result.exit_code == 0
    assert "[screen] reuse prepared path=" in result.stderr


def test_screen_record_watch_uses_latest_effective_rows_per_symbol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "watch_pool.csv").write_text(
        "\n".join(
            [
                "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at",
                "b1,2026-04-01,AAA.SZ,WATCH,1.0,signal,first,2026-04-01T10:00:00+08:00",
                "b1,2026-04-02,AAA.SZ,WATCH,2.0,signal,second,2026-04-02T10:00:00+08:00",
                "b1,2026-04-02,AAA.SZ,WATCH,3.0,signal,latest-same-day,2026-04-02T11:00:00+08:00",
                "b1,2026-04-05,BBB.SZ,WATCH,4.0,signal,future,2026-04-05T10:00:00+08:00",
                "b1,2026-04-03,CCC.SZ,PASS,5.0,signal,eligible,2026-04-03T10:00:00+08:00",
                "b1,2026-04-04,DDD.SZ,WATCH,6.0,signal,missing-from-prepared,2026-04-04T10:00:00+08:00",
            ]
        ),
        encoding="utf-8",
    )

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
                "ts_code": ["AAA.SZ", "CCC.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04", "2026-04-04"]),
                "open": [10.0, 20.0],
                "high": [10.5, 20.5],
                "low": [9.8, 19.8],
                "close": [10.2, 20.2],
                "vol": [100.0, 200.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [100.0],
                }
            ),
            "CCC.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [20.2],
                    "J": [10.0],
                    "zxdq": [20.4],
                    "zxdkx": [20.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [200.0],
                }
            ),
        }

    def fake_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        raise AssertionError("turnover-top pool should not be used for record-watch")

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["AAA.SZ", "CCC.SZ"]
        assert pick_date == pd.Timestamp("2026-04-04")
        return (
            [
                {"code": "AAA.SZ", "pick_date": "2026-04-04", "close": 10.2, "turnover_n": 100.0},
                {"code": "CCC.SZ", "pick_date": "2026-04-04", "close": 20.2, "turnover_n": 200.0},
            ],
            _b1_screen_stats(total_symbols=2, eligible=2, selected=2),
        )

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fake_pool)
    monkeypatch.setattr(cli, "run_b1_screen_with_stats", fake_run_b1_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["AAA.SZ", "CCC.SZ"]


def test_screen_custom_pool_uses_whitespace_separated_file_codes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    pool_file = tmp_path / "custom-pool.txt"
    pool_file.write_text("000001 300058\n000001.SZ\t603138", encoding="utf-8")

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
                "ts_code": ["000001.SZ", "300058.SZ", "603138.SH", "688001.SH"],
                "trade_date": pd.to_datetime(["2026-04-04"] * 4),
                "open": [10.0, 20.0, 30.0, 40.0],
                "high": [10.5, 20.5, 30.5, 40.5],
                "low": [9.8, 19.8, 29.8, 39.8],
                "close": [10.2, 20.2, 30.2, 40.2],
                "vol": [100.0, 200.0, 300.0, 400.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            code: pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [close],
                    "J": [10.0],
                    "zxdq": [close + 0.2],
                    "zxdkx": [close - 0.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [turnover],
                }
            )
            for code, close, turnover in [
                ("000001.SZ", 10.2, 100.0),
                ("300058.SZ", 20.2, 200.0),
                ("603138.SH", 30.2, 300.0),
                ("688001.SH", 40.2, 400.0),
            ]
        }

    def fail_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        raise AssertionError("turnover-top pool should not be used for custom pool")

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["000001.SZ", "300058.SZ", "603138.SH"]
        assert pick_date == pd.Timestamp("2026-04-04")
        return (
            [
                {"code": "000001.SZ", "pick_date": "2026-04-04", "close": 10.2, "turnover_n": 100.0},
                {"code": "300058.SZ", "pick_date": "2026-04-04", "close": 20.2, "turnover_n": 200.0},
                {"code": "603138.SH", "pick_date": "2026-04-04", "close": 30.2, "turnover_n": 300.0},
            ],
            _b1_screen_stats(total_symbols=3, eligible=3, selected=3),
        )

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fail_pool)
    monkeypatch.setattr(cli, "run_b1_screen_with_stats", fake_run_b1_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "custom",
            "--pool-file",
            str(pool_file),
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["000001.SZ", "300058.SZ", "603138.SH"]


def test_screen_custom_pool_uses_env_file_when_pool_file_not_passed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    pool_file = tmp_path / "from-env.txt"
    pool_file.write_text("300058", encoding="utf-8")

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
                "ts_code": ["300058.SZ", "603138.SH"],
                "trade_date": pd.to_datetime(["2026-04-04", "2026-04-04"]),
                "open": [20.0, 30.0],
                "high": [20.5, 30.5],
                "low": [19.8, 29.8],
                "close": [20.2, 30.2],
                "vol": [200.0, 300.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "300058.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [20.2],
                    "J": [10.0],
                    "zxdq": [20.4],
                    "zxdkx": [20.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [200.0],
                }
            ),
            "603138.SH": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [30.2],
                    "J": [10.0],
                    "zxdq": [30.4],
                    "zxdkx": [30.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [300.0],
                }
            ),
        }

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(
        cli,
        "run_b1_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "300058.SZ", "pick_date": "2026-04-04", "close": 20.2, "turnover_n": 200.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
        )
        if list(prepared_by_symbol) == ["300058.SZ"]
        else pytest.fail("custom env pool should screen only env-provided symbols"),
    )
    monkeypatch.setenv("STOCK_SELECT_POOL_FILE", str(pool_file))

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "custom",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert payload["pool_file"] == str(pool_file)
    assert [item["code"] for item in payload["candidates"]] == ["300058.SZ"]


def test_screen_custom_pool_uses_default_file_when_no_override_is_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    default_pool_file = Path.home() / ".agents" / "skills" / "stock-select" / "runtime" / "custom-pool.txt"
    default_pool_file.parent.mkdir(parents=True, exist_ok=True)
    original_content = default_pool_file.read_text(encoding="utf-8") if default_pool_file.exists() else None
    default_pool_file.write_text("603138", encoding="utf-8")

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
                "ts_code": ["603138.SH", "300058.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04", "2026-04-04"]),
                "open": [30.0, 20.0],
                "high": [30.5, 20.5],
                "low": [29.8, 19.8],
                "close": [30.2, 20.2],
                "vol": [300.0, 200.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "603138.SH": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [30.2],
                    "J": [10.0],
                    "zxdq": [30.4],
                    "zxdkx": [30.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [30.0],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
                    "turnover_n": [300.0],
                }
            ),
            "300058.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [20.2],
                    "J": [10.0],
                    "zxdq": [20.4],
                    "zxdkx": [20.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [20.0],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
                    "turnover_n": [200.0],
                }
            ),
        }

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(
        cli,
        "run_b1_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "603138.SH", "pick_date": "2026-04-04", "close": 30.2, "turnover_n": 300.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
        )
        if list(prepared_by_symbol) == ["603138.SH"]
        else pytest.fail("default custom pool should screen only default-file symbols"),
    )
    monkeypatch.delenv("STOCK_SELECT_POOL_FILE", raising=False)

    try:
        result = runner.invoke(
            app,
            [
                "screen",
                "--method",
                "b1",
                "--pick-date",
                "2026-04-04",
                "--pool-source",
                "custom",
                "--runtime-root",
                str(runtime_root),
                "--dsn",
                "postgresql://example",
            ],
        )
    finally:
        if original_content is None:
            default_pool_file.unlink(missing_ok=True)
        else:
            default_pool_file.write_text(original_content, encoding="utf-8")

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert payload["pool_file"] == str(default_pool_file)
    assert [item["code"] for item in payload["candidates"]] == ["603138.SH"]


def test_screen_custom_pool_does_not_reuse_artifacts_from_different_pool_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    prepared_dir = runtime_root / "prepared"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    old_pool_file = tmp_path / "old.txt"
    new_pool_file = tmp_path / "new.txt"
    old_pool_file.write_text("000001", encoding="utf-8")
    new_pool_file.write_text("300058", encoding="utf-8")

    (candidate_dir / f"{_eod_key('2026-04-04')}.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-04",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "pool_source": "custom",
                "pool_file": str(old_pool_file),
                "candidates": [{"code": "000001.SZ", "pick_date": "2026-04-04", "close": 10.2, "turnover_n": 100.0}],
            }
        ),
        encoding="utf-8",
    )
    cli._write_prepared_cache(
        prepared_dir / f"{_eod_key('2026-04-04')}.pkl",
        method="b1",
        pick_date="2026-04-04",
        start_date="2025-04-03",
        end_date="2026-04-04",
        prepared_by_symbol={
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [100.0],
                }
            )
        },
        metadata_overrides={"pool_source": "custom", "pool_file": str(old_pool_file)},
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
                "ts_code": ["300058.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04"]),
                "open": [20.0],
                "high": [20.5],
                "low": [19.8],
                "close": [20.2],
                "vol": [200.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        calls["prepare"] += 1
        return {
            "300058.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [20.2],
                    "J": [10.0],
                    "zxdq": [20.4],
                    "zxdkx": [20.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [200.0],
                }
            )
        }

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(
        cli,
        "run_b1_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "300058.SZ", "pick_date": "2026-04-04", "close": 20.2, "turnover_n": 200.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
        )
        if list(prepared_by_symbol) == ["300058.SZ"]
        else pytest.fail("custom pool should recompute for a different pool file"),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "custom",
            "--pool-file",
            str(new_pool_file),
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert calls == {"connect": 1, "prepare": 1}
    payload = json.loads((candidate_dir / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert payload["pool_file"] == str(new_pool_file)
    assert [item["code"] for item in payload["candidates"]] == ["300058.SZ"]


def test_screen_custom_pool_extracts_numeric_codes_from_prefixed_lines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    pool_file = tmp_path / "custom-pool.txt"
    pool_file.write_text(
        "\n".join(
            [
                "SH603876 鼎胜新材",
                "SZ002008 大族激光",
                "SZ002703 浙江世宝",
                "垃圾行",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["603876.SH", "002008.SZ", "002703.SZ", "300058.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04"] * 4),
                "open": [10.0, 20.0, 30.0, 40.0],
                "high": [10.5, 20.5, 30.5, 40.5],
                "low": [9.8, 19.8, 29.8, 39.8],
                "close": [10.2, 20.2, 30.2, 40.2],
                "vol": [100.0, 200.0, 300.0, 400.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_screen_data",
        lambda _market, reporter=None: {
            code: pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.0],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [100.0],
                }
            )
            for code in ["603876.SH", "002008.SZ", "002703.SZ", "300058.SZ"]
        },
    )
    monkeypatch.setattr(
        cli,
        "run_b1_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [
                {"code": code, "pick_date": "2026-04-04", "close": 10.2, "turnover_n": 100.0}
                for code in prepared_by_symbol
            ],
            _b1_screen_stats(
                total_symbols=len(prepared_by_symbol),
                eligible=len(prepared_by_symbol),
                selected=len(prepared_by_symbol),
            ),
        )
        if list(prepared_by_symbol) == ["603876.SH", "002008.SZ", "002703.SZ"]
        else pytest.fail("custom pool should extract numeric codes from prefixed lines only"),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "custom",
            "--pool-file",
            str(pool_file),
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["603876.SH", "002008.SZ", "002703.SZ"]


def test_screen_record_watch_rejects_missing_watch_pool_csv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
                "ts_code": ["AAA.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
                    "turnover_n": [100.0],
                }
            )
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
            "2026-04-04",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "watch pool csv" in result.stderr.lower()
    normalized_stderr = result.stderr.replace("\n", "").replace(" ", "").replace("│", "")
    assert "watch_pool.csv" in normalized_stderr


def test_screen_record_watch_rejects_empty_effective_pool_after_intersection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "watch_pool.csv").write_text(
        "\n".join(
            [
                "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at",
                "b1,2026-04-02,ZZZ.SZ,WATCH,1.0,signal,not-in-prepared,2026-04-02T10:00:00+08:00",
                "b1,2026-04-05,AAA.SZ,WATCH,2.0,signal,too-new,2026-04-05T10:00:00+08:00",
            ]
        ),
        encoding="utf-8",
    )

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
                "ts_code": ["AAA.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame) -> dict[str, pd.DataFrame]:
        return {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
                    "turnover_n": [100.0],
                }
            )
        }

    def fake_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        raise AssertionError("turnover-top pool should not be used for record-watch")

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fake_pool)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "effective watch pool" in result.stderr.lower()
    assert "2026-04-04" in result.stderr


def test_screen_dribull_record_watch_drives_phase_one_and_warmup_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "watch_pool.csv").write_text(
        "\n".join(
            [
                "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at",
                "dribull,2026-04-08,BBB.SZ,WATCH,1.0,signal,chosen,2026-04-08T10:00:00+08:00",
            ]
        ),
        encoding="utf-8",
    )

    fetch_calls: list[tuple[str, tuple[str, ...] | None]] = []

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        fetch_calls.append((start_date, tuple(symbols) if symbols is not None else None))
        if start_date == "2025-04-09":
            return pd.DataFrame(
                {
                    "ts_code": ["AAA.SZ", "BBB.SZ"],
                    "trade_date": pd.to_datetime(["2026-04-10", "2026-04-10"]),
                    "open": [10.0, 20.0],
                    "high": [10.5, 20.5],
                    "low": [9.8, 19.8],
                    "close": [10.2, 20.2],
                    "vol": [100.0, 200.0],
                }
            )
        assert start_date == "2023-01-01"
        assert symbols == ["BBB.SZ"]
        return pd.DataFrame(
            {
                "ts_code": ["BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10"]),
                "open": [20.0],
                "high": [20.5],
                "low": [19.8],
                "close": [20.2],
                "vol": [200.0],
            }
        )

    prepare_calls: list[list[str]] = []

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        symbols = sorted(market["ts_code"].astype(str).unique().tolist())
        prepare_calls.append(symbols)
        return {
            code: pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [10.0 if code == "AAA.SZ" else 20.2],
                    "J": [10.0],
                    "zxdq": [10.5 if code == "AAA.SZ" else 20.4],
                    "zxdkx": [10.0 if code == "AAA.SZ" else 20.0],
                    "low": [9.9 if code == "AAA.SZ" else 19.9],
                    "volume": [100.0 if code == "AAA.SZ" else 200.0],
                    "ma25": [10.0 if code == "AAA.SZ" else 20.0],
                    "ma60": [9.8 if code == "AAA.SZ" else 19.8],
                    "ma144": [9.6 if code == "AAA.SZ" else 19.6],
                    "dif": [0.11],
                    "dea": [0.08],
                    "dif_w": [0.20],
                    "dea_w": [0.15],
                    "dif_m": [0.30],
                    "dea_m": [0.22],
                    "turnover_n": [100.0 if code == "AAA.SZ" else 200.0],
                }
            )
            for code in symbols
        }

    def fail_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        raise AssertionError("turnover-top pool should not gate dribull record-watch screening")

    def fake_prefilter_dribull_non_macd(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> list[str]:
        assert list(prepared_by_symbol) == ["BBB.SZ"]
        assert pick_date == pd.Timestamp("2026-04-10")
        return ["BBB.SZ"]

    def fake_run_dribull_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["BBB.SZ"]
        assert pick_date == pd.Timestamp("2026-04-10")
        return (
            [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 20.2, "turnover_n": 200.0}],
            _dribull_wave_stats(total_symbols=1, eligible=1, selected=1),
        )

    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fail_pool)
    monkeypatch.setattr(cli, "prefilter_dribull_non_macd", fake_prefilter_dribull_non_macd)
    monkeypatch.setattr(cli, "run_dribull_screen_with_stats", fake_run_dribull_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert fetch_calls == [
        ("2025-04-09", None),
        ("2023-01-01", ("BBB.SZ",)),
    ]
    assert prepare_calls == [["AAA.SZ", "BBB.SZ"], ["BBB.SZ"]]
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'dribull')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["BBB.SZ"]


def test_screen_record_watch_bypasses_existing_candidate_and_prepared_reuse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    prepared_dir = runtime_root / "prepared"
    watch_file = runtime_root / "watch_pool.csv"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)
    runtime_root.mkdir(parents=True, exist_ok=True)

    (candidate_dir / f"{_eod_key('2026-04-04')}.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-04",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "candidates": [{"code": "OLD.SZ", "pick_date": "2026-04-04", "close": 9.9, "turnover_n": 90.0}],
            }
        ),
        encoding="utf-8",
    )
    cli._write_prepared_cache(
        prepared_dir / f"{_eod_key('2026-04-04')}.pkl",
        method="b1",
        pick_date="2026-04-04",
        start_date="2025-04-03",
        end_date="2026-04-04",
        prepared_by_symbol={
            "OLD.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [9.9],
                    "J": [10.0],
                    "zxdq": [10.1],
                    "zxdkx": [9.8],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [90.0],
                }
            )
        },
    )
    watch_file.write_text(
        "\n".join(
            [
                "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at",
                "b1,2026-04-03,NEW.SZ,WATCH,1.0,signal,chosen,2026-04-03T10:00:00+08:00",
            ]
        ),
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
                "ts_code": ["NEW.SZ"],
                "trade_date": pd.to_datetime(["2026-04-04"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        calls["prepare"] += 1
        return {
            "NEW.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [100.0],
                }
            )
        }

    def fail_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        raise AssertionError("turnover-top pool should not be used for record-watch")

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["NEW.SZ"]
        return (
            [{"code": "NEW.SZ", "pick_date": "2026-04-04", "close": 10.2, "turnover_n": 100.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
        )

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fail_pool)
    monkeypatch.setattr(cli, "run_b1_screen_with_stats", fake_run_b1_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert calls == {"connect": 1, "prepare": 1}
    assert "[screen] reuse candidates path=" not in result.stderr
    assert "[screen] reuse prepared path=" not in result.stderr
    payload = json.loads((candidate_dir / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["NEW.SZ"]


def test_screen_turnover_top_does_not_reuse_record_watch_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    prepared_dir = runtime_root / "prepared"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    (candidate_dir / f"{_eod_key('2026-04-04')}.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-04",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
                "pool_source": "record-watch",
                "candidates": [{"code": "OLD.SZ", "pick_date": "2026-04-04", "close": 9.9, "turnover_n": 90.0}],
            }
        ),
        encoding="utf-8",
    )
    cli._write_prepared_cache(
        prepared_dir / f"{_eod_key('2026-04-04')}.pkl",
        method="b1",
        pick_date="2026-04-04",
        start_date="2025-04-03",
        end_date="2026-04-04",
        prepared_by_symbol={
            "OLD.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [9.9],
                    "J": [10.0],
                    "zxdq": [10.1],
                    "zxdkx": [9.8],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [90.0],
                }
            )
        },
        metadata_overrides={"pool_source": "record-watch"},
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
                "trade_date": pd.to_datetime(["2026-04-04"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "vol": [100.0],
            }
        )

    def fake_prepare_screen_data(_: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        calls["prepare"] += 1
        return {
            "NEW.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-04"]),
                    "close": [10.2],
                    "J": [10.0],
                    "zxdq": [10.4],
                    "zxdkx": [10.0],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [100.0],
                }
            )
        }

    def fake_turnover_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        return {pd.Timestamp("2026-04-04"): ["NEW.SZ"]}

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_by_symbol) == ["NEW.SZ"]
        return (
            [{"code": "NEW.SZ", "pick_date": "2026-04-04", "close": 10.2, "turnover_n": 100.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
        )

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fake_turnover_pool)
    monkeypatch.setattr(cli, "run_b1_screen_with_stats", fake_run_b1_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-04",
            "--pool-source",
            "turnover-top",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert calls == {"connect": 1, "prepare": 1}
    assert "[screen] reuse candidates path=" not in result.stderr
    assert "[screen] reuse prepared path=" not in result.stderr
    payload = json.loads((candidate_dir / f"{_eod_key('2026-04-04')}.json").read_text(encoding="utf-8"))
    assert payload["pool_source"] == "turnover-top"
    assert [item["code"] for item in payload["candidates"]] == ["NEW.SZ"]
    cache_payload = cli._load_prepared_cache(prepared_dir / "2026-04-04.pkl")
    assert cache_payload["pick_date"] == "2026-04-04"


def test_screen_turnover_top_uses_ma25_above_ma60_pool_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    prepared_dir = runtime_root / "prepared"
    captured: dict[str, object] = {}

    def fake_connect(dsn: str):
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
                "trade_date": ["2026-04-24", "2026-04-24"],
                "open": [10.0, 10.0],
                "high": [10.8, 10.8],
                "low": [9.9, 9.9],
                "close": [10.7, 10.7],
                "vol": [100.0, 120.0],
            }
        )

    prepared = {
        "AAA.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-24"]),
                "turnover_n": [200.0],
                "ma25": [10.5],
                "ma60": [10.0],
                "J": [10.0],
                "zxdq": [10.6],
                "zxdkx": [10.1],
                "close": [10.7],
                "weekly_ma_bull": [True],
                "max_vol_not_bearish": [True],
                "chg_d": [1.0],
                "v_shrink": [True],
                "safe_mode": [True],
                "lt_filter": [True],
            }
        ),
        "BBB.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-24"]),
                "turnover_n": [300.0],
                "ma25": [9.8],
                "ma60": [10.0],
                "J": [10.0],
                "zxdq": [10.6],
                "zxdkx": [10.1],
                "close": [10.7],
                "weekly_ma_bull": [True],
                "max_vol_not_bearish": [True],
                "chg_d": [1.0],
                "v_shrink": [True],
                "safe_mode": [True],
                "lt_filter": [True],
            }
        ),
    }

    def fake_prepare_screen_data(_: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        return prepared

    def fake_run_b1_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        captured["codes"] = sorted(prepared_by_symbol)
        return ([], _b1_screen_stats(total_symbols=len(prepared_by_symbol), eligible=len(prepared_by_symbol), selected=0))

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_validate_eod_pick_date_has_market_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "run_b1_screen_with_stats", fake_run_b1_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-24",
            "--pool-source",
            "turnover-top",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert captured["codes"] == ["AAA.SZ"]
    payload = json.loads((candidate_dir / f"{_eod_key('2026-04-24')}.json").read_text(encoding="utf-8"))
    assert payload["pool_source"] == "turnover-top"
    assert payload["candidates"] == []
    cache_payload = cli._load_prepared_cache(prepared_dir / "2026-04-24.pkl")
    assert cache_payload["pick_date"] == "2026-04-24"


def test_screen_dribull_record_watch_zero_phase_one_survivors_writes_empty_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "watch_pool.csv").write_text(
        "\n".join(
            [
                "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at",
                "dribull,2026-04-08,BBB.SZ,WATCH,1.0,signal,chosen,2026-04-08T10:00:00+08:00",
            ]
        ),
        encoding="utf-8",
    )

    fetch_calls: list[tuple[str, tuple[str, ...] | None]] = []

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        fetch_calls.append((start_date, tuple(symbols) if symbols is not None else None))
        return pd.DataFrame(
            {
                "ts_code": ["BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10"]),
                "open": [20.0],
                "high": [20.5],
                "low": [19.8],
                "close": [20.2],
                "vol": [200.0],
            }
        )

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        return {
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [20.2],
                    "J": [10.0],
                    "zxdq": [20.4],
                    "zxdkx": [20.0],
                    "low": [19.9],
                    "volume": [200.0],
                    "ma25": [20.0],
                    "ma60": [19.8],
                    "ma144": [19.6],
                    "dif": [0.11],
                    "dea": [0.08],
                    "dif_w": [0.20],
                    "dea_w": [0.15],
                    "dif_m": [0.30],
                    "dea_m": [0.22],
                    "turnover_n": [200.0],
                }
            )
        }

    def fail_pool(prepared_by_symbol: dict[str, pd.DataFrame], *, top_m: int):
        raise AssertionError("turnover-top pool should not gate dribull record-watch screening")

    def fake_prefilter_dribull_non_macd(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> list[str]:
        assert list(prepared_by_symbol) == ["BBB.SZ"]
        return []

    def fake_run_dribull_screen_with_stats(
        prepared_by_symbol: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        assert prepared_by_symbol == {}
        return (
            [],
            _dribull_wave_stats(total_symbols=0, eligible=0, selected=0),
        )

    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "build_top_turnover_pool", fail_pool)
    monkeypatch.setattr(cli, "prefilter_dribull_non_macd", fake_prefilter_dribull_non_macd)
    monkeypatch.setattr(cli, "run_dribull_screen_with_stats", fake_run_dribull_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert "effective watch pool" not in result.stderr.lower()
    assert fetch_calls == [("2025-04-09", None)]
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'dribull')}.json").read_text(encoding="utf-8"))
    assert payload["pool_source"] == "record-watch"
    assert payload["candidates"] == []


def test_screen_hcr_turnover_top_uses_liquidity_pool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "_resolve_hcr_start_date",
        lambda connection, *, end_date, trading_days: "2025-04-29",
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ", "BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10", "2026-04-10"]),
                "open": [10.0, 20.0],
                "high": [10.8, 20.8],
                "low": [9.8, 19.8],
                "close": [10.6, 20.6],
                "vol": [100.0, 200.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [10.6],
                    "yx": [10.4],
                    "p": [10.5],
                    "resonance_gap_pct": [0.003],
                    "turnover_n": [100.0],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [20.6],
                    "yx": [20.4],
                    "p": [20.5],
                    "resonance_gap_pct": [0.003],
                    "turnover_n": [200.0],
                }
            ),
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-10"): ["BBB.SZ"]},
    )
    monkeypatch.setattr(
        cli,
        "run_hcr_screen_with_stats",
        lambda prepared_by_symbol, pick_date: (
            [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 20.6, "turnover_n": 200.0, "yx": 20.4, "p": 20.5, "resonance_gap_pct": 0.003}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_resonance": 0,
                "fail_close_floor": 0,
                "fail_breakout": 0,
                "selected": 1,
            },
        )
        if list(prepared_by_symbol) == ["BBB.SZ"]
        else pytest.fail("hcr should screen only the turnover-top subset"),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "turnover-top",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'hcr')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["BBB.SZ"]


def test_screen_hcr_record_watch_uses_shared_watch_pool_subset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "watch_pool.csv").write_text(
        "\n".join(
            [
                "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at",
                "b1,2026-04-08,AAA.SZ,WATCH,1.0,signal,chosen,2026-04-08T10:00:00+08:00",
                "dribull,2026-04-08,CCC.SZ,WATCH,1.0,signal,missing,2026-04-08T10:00:00+08:00",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "_resolve_hcr_start_date",
        lambda connection, *, end_date, trading_days: "2025-04-29",
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ", "BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10", "2026-04-10"]),
                "open": [10.0, 20.0],
                "high": [10.8, 20.8],
                "low": [9.8, 19.8],
                "close": [10.6, 20.6],
                "vol": [100.0, 200.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [10.6],
                    "yx": [10.4],
                    "p": [10.5],
                    "resonance_gap_pct": [0.003],
                    "turnover_n": [100.0],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [20.6],
                    "yx": [20.4],
                    "p": [20.5],
                    "resonance_gap_pct": [0.003],
                    "turnover_n": [200.0],
                }
            ),
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: pytest.fail("turnover-top pool should not be used for hcr record-watch"),
    )
    monkeypatch.setattr(
        cli,
        "run_hcr_screen_with_stats",
        lambda prepared_by_symbol, pick_date: (
            [{"code": "AAA.SZ", "pick_date": "2026-04-10", "close": 10.6, "turnover_n": 100.0, "yx": 10.4, "p": 10.5, "resonance_gap_pct": 0.003}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_resonance": 0,
                "fail_close_floor": 0,
                "fail_breakout": 0,
                "selected": 1,
            },
        )
        if list(prepared_by_symbol) == ["AAA.SZ"]
        else pytest.fail("hcr should screen only the effective watch-pool subset"),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'hcr')}.json").read_text(encoding="utf-8"))
    assert payload["pool_source"] == "record-watch"
    assert [item["code"] for item in payload["candidates"]] == ["AAA.SZ"]


def test_screen_dribull_real_flow_skips_malformed_pool_rows_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)
    valid_dribull_close = [12.0] * 146 + [11.8, 11.7, 11.9, 12.1, 12.4, 12.8, 13.1, 13.4, 13.2, 13.0, 12.9, 12.92, 12.97, 13.02]

    def fake_connect(_: str) -> object:
        return object()

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        market_rows: list[dict[str, object]] = []
        for code, base_close in (("AAA.SZ", 10.0), ("BBB.SZ", 12.0)):
            for idx, trade_date in enumerate(trade_dates):
                if code == "BBB.SZ":
                    close = valid_dribull_close[idx]
                else:
                    close = base_close + idx * 0.1
                market_rows.append(
                    {
                        "ts_code": code,
                        "trade_date": trade_date,
                        "open": close - 0.1,
                        "high": close + 0.2,
                        "low": close - 0.2 if idx < len(trade_dates) - 1 else (12.40 if code == "BBB.SZ" else close - 0.30),
                        "close": close,
                        "vol": 100.0 + idx if idx < len(trade_dates) - 1 else 50.0,
                    }
                )
        return pd.DataFrame(market_rows)

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        prepared: dict[str, pd.DataFrame] = {}
        for code, group in market.groupby("ts_code"):
            group = group.sort_values("trade_date").reset_index(drop=True).copy()
            group["turnover_n"] = 100.0 if code == "AAA.SZ" else 200.0
            group["J"] = 10.0
            group["zxdq"] = group["close"] + 0.3
            group["zxdkx"] = group["close"] - 0.1
            group["low"] = group["close"] - 0.2
            group["volume"] = group["vol"]
            group["ma25"] = group["close"]
            group["ma60"] = group["close"]
            group["ma144"] = group["close"]
            prepared[code] = group
        return prepared

    run_calls: list[list[str]] = []

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-10"): ["BBB.SZ"]},
    )
    monkeypatch.setattr(cli, "prefilter_dribull_non_macd", lambda prepared_by_symbol, pick_date, config=None: ["BBB.SZ"])
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            run_calls.append(sorted(prepared_by_symbol))
            or [{"code": "BBB.SZ", "pick_date": "2026-04-10", "close": 13.02, "turnover_n": 359.0}],
            _dribull_wave_stats(total_symbols=len(prepared_by_symbol), eligible=len(prepared_by_symbol), selected=1),
        ),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'dribull')}.json").read_text(encoding="utf-8"))
    assert payload["method"] == "dribull"
    assert run_calls == [["BBB.SZ"]]
    assert [item["code"] for item in payload["candidates"]] == ["BBB.SZ"]


def test_screen_reuses_existing_non_empty_candidate_file_without_recomputing(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / f"{_eod_key('2026-04-01')}.json"
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1),
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


def test_screen_ignores_stale_b1_candidate_file_without_screen_version_and_recomputes(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / f"{_eod_key('2026-04-01')}.json"
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b1",
                "candidates": [{"code": "OLD.SZ", "pick_date": "2026-04-01", "close": 9.9, "turnover_n": 50.0}],
            }
        ),
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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
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
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
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
    assert "[screen] reuse candidates path=" not in result.stderr


def test_screen_ignores_existing_empty_candidate_file_and_recomputes(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_eod_key('2026-04-01')}.json").write_text(
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
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
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
                "chg_d": [1.0],
                "amp_d": [2.0],
                "body_d": [-1.0],
                "vm3": [90.0],
                "vm5": [100.0],
                "vm10": [120.0],
                "m5": [10.4],
                "v_shrink": [True],
                "safe_mode": [True],
                "lt_filter": [True],
            }
        )
    }
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-01.pkl",
        method="b1",
        pick_date="2026-04-01",
        start_date="2025-03-31",
        end_date="2026-04-01",
        prepared_by_symbol=prepared_by_symbol,
        metadata_overrides={"screen_version": getattr(cli, "B1_ARTIFACT_VERSION", 1)},
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
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
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


def test_screen_ignores_stale_b1_prepared_cache_without_screen_version_and_recomputes(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-01.pkl",
        pick_date="2026-04-01",
        start_date="2025-03-31",
        end_date="2026-04-01",
        prepared_by_symbol={
            "OLD.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-01"]),
                    "turnover_n": [50.0],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "close": [10.6],
                }
            )
        },
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
                "ts_code": ["BBB.SZ"],
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
                    "chg_d": [1.0],
                    "amp_d": [2.0],
                    "body_d": [-1.0],
                    "vm3": [90.0],
                    "vm5": [100.0],
                    "vm10": [120.0],
                    "m5": [10.4],
                    "v_shrink": [True],
                    "safe_mode": [True],
                    "lt_filter": [True],
                }
            )
        }

    def fake_run_b1_screen_with_stats(
        prepared_subset: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
        config: dict,
    ) -> tuple[list[dict], dict[str, int]]:
        return (
            [{"code": "BBB.SZ", "pick_date": "2026-04-01", "close": 11.6, "turnover_n": 200.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
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
    assert "[screen] reuse prepared path=" not in result.stderr


def test_screen_b2_reuses_shared_prepared_cache_when_candidate_output_missing(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    prepared_by_symbol = {
        "BBB.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "open": [11.2],
                "high": [11.8],
                "low": [11.0],
                "close": [11.6],
                "turnover_n": [200.0],
                "volume": [120.0],
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
    original_run = cli.run_b2_screen_with_stats

    def fail_connect(_: str) -> object:
        raise AssertionError("b2 screen should not connect when shared prepared cache is reusable")

    def fail_fetch(*args, **kwargs):
        raise AssertionError("b2 screen should not fetch market window when shared prepared cache is reusable")

    def fail_prepare(_: pd.DataFrame, reporter=None) -> dict[str, pd.DataFrame]:
        raise AssertionError("b2 screen should not prepare data when shared prepared cache is reusable")

    def fake_run_b2_screen_with_stats(
        prepared_subset: dict[str, pd.DataFrame],
        pick_date: pd.Timestamp,
    ) -> tuple[list[dict], dict[str, int]]:
        assert list(prepared_subset) == ["BBB.SZ"]
        return (
            [{"code": "BBB.SZ", "pick_date": "2026-04-01", "close": 11.6, "turnover_n": 200.0, "signal": "B2"}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_pre_ok": 0,
                "fail_pct": 0,
                "fail_volume": 0,
                "fail_k_shape": 0,
                "fail_j_up": 0,
                "fail_tr_ok": 0,
                "fail_above_lt": 0,
                "fail_duplicate_b2": 0,
                "fail_no_signal": 0,
                "selected": 1,
                "selected_b2": 1,
                "selected_b3": 0,
                "selected_b3_plus": 0,
                "selected_b4": 0,
                "selected_b5": 0,
            },
        )

    cli._connect = fail_connect  # type: ignore[assignment]
    cli.fetch_daily_window = fail_fetch  # type: ignore[assignment]
    cli._prepare_screen_data = fail_prepare  # type: ignore[assignment]
    cli.run_b2_screen_with_stats = fake_run_b2_screen_with_stats  # type: ignore[assignment]

    try:
        result = runner.invoke(
            app,
            [
                "screen",
                "--method",
                "b2",
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
        cli.run_b2_screen_with_stats = original_run  # type: ignore[assignment]

    assert result.exit_code == 0
    assert "[screen] reuse prepared path=" in result.stderr


def test_screen_recompute_bypasses_candidate_and_prepared_reuse(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / f"{_eod_key('2026-04-01')}.json").write_text(
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
        runtime_root / "prepared" / f"{_eod_key('2026-04-01')}.pkl",
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
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
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
    payload = json.loads((candidate_dir / f"{_eod_key('2026-04-01')}.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in payload["candidates"]] == ["NEW.SZ"]


def test_screen_skips_prepared_reuse_when_cache_does_not_cover_pick_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    prepared_path = runtime_root / "prepared" / "2026-04-10.pkl"
    prepared_path.parent.mkdir(parents=True, exist_ok=True)
    cli._write_prepared_cache(
        prepared_path,
        method="dribull",
        pick_date="2026-04-10",
        start_date="2025-04-09",
        end_date="2026-04-10",
        prepared_by_symbol={
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-09"]),
                    "turnover_n": [1030.0],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "low": [10.3],
                    "close": [10.6],
                    "volume": [100.0],
                    "ma25": [10.5],
                    "ma60": [10.4],
                    "ma144": [9.6],
                    "dif": [0.11],
                    "dea": [0.08],
                    "dif_w": [0.20],
                    "dea_w": [0.15],
                    "dif_m": [0.30],
                    "dea_m": [0.22],
                }
            )
        },
    )

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10"]),
                "open": [10.0],
                "high": [10.8],
                "low": [9.8],
                "close": [10.6],
                "vol": [100.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_screen_data",
        lambda market, reporter=None: {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "turnover_n": [1030.0],
                    "J": [10.0],
                    "zxdq": [10.5],
                    "zxdkx": [10.2],
                    "low": [10.3],
                    "close": [10.6],
                    "volume": [100.0],
                    "ma25": [10.5],
                    "ma60": [10.4],
                    "ma144": [9.6],
                    "dif": [0.11],
                    "dea": [0.08],
                    "dif_w": [0.20],
                    "dea_w": [0.15],
                    "dif_m": [0.30],
                    "dea_m": [0.22],
                }
            )
        },
    )
    monkeypatch.setattr(cli, "build_top_turnover_pool", lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-10"): ["000001.SZ"]})
    monkeypatch.setattr(
        cli,
        "run_dribull_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "000001.SZ", "pick_date": "2026-04-10", "close": 10.6, "turnover_n": 1030.0}],
            _dribull_wave_stats(total_symbols=1, eligible=1, selected=1),
        ),
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "dribull",
            "--pick-date",
            "2026-04-10",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert "reason=stale_pick_date" in result.stderr
    assert "[screen] fetch market window" in result.stderr


def test_compute_period_macd_alignment_uses_current_week_close_on_pick_date() -> None:
    trade_dates = pd.bdate_range("2026-03-23", "2026-04-10")
    close = [
        10.0,
        10.1,
        10.2,
        10.3,
        11.0,
        11.1,
        11.2,
        11.3,
        11.4,
        12.8,
        12.9,
        13.0,
        13.1,
        13.2,
        15.0,
    ]
    frame = pd.DataFrame({"trade_date": trade_dates, "close": close})

    aligned = cli._compute_period_macd_alignment(frame, period="W")
    sampled = pd.DataFrame(
        {"close": [11.0, 12.8, 15.0]},
        index=pd.to_datetime(["2026-03-27", "2026-04-03", "2026-04-10"]),
    )
    expected = cli.compute_macd(sampled)

    assert aligned.iloc[-1]["dif"] == pytest.approx(expected.iloc[-1]["dif"])
    assert aligned.iloc[-1]["dea"] == pytest.approx(expected.iloc[-1]["dea"])
    assert aligned.iloc[-1]["dif"] != pytest.approx(expected.iloc[-2]["dif"])
    assert aligned.iloc[-1]["dea"] != pytest.approx(expected.iloc[-2]["dea"])


def test_compute_period_macd_alignment_uses_current_month_close_on_pick_date() -> None:
    trade_dates = pd.bdate_range("2026-02-23", "2026-04-10")
    close = [20.0 + idx * 0.1 for idx in range(len(trade_dates))]
    close[4] = 21.5
    close[-1] = 30.0
    frame = pd.DataFrame({"trade_date": trade_dates, "close": close})

    aligned = cli._compute_period_macd_alignment(frame, period="ME")
    sampled = pd.DataFrame(
        {"close": [21.5, 22.6, 30.0]},
        index=pd.to_datetime(["2026-02-27", "2026-03-31", "2026-04-10"]),
    )
    expected = cli.compute_macd(sampled)

    assert aligned.iloc[-1]["dif"] == pytest.approx(expected.iloc[-1]["dif"])
    assert aligned.iloc[-1]["dea"] == pytest.approx(expected.iloc[-1]["dea"])
    assert aligned.iloc[-1]["dif"] != pytest.approx(expected.iloc[-2]["dif"])
    assert aligned.iloc[-1]["dea"] != pytest.approx(expected.iloc[-2]["dea"])


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


def test_screen_intraday_warns_outside_trading_hours_before_open(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 08:45:00", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.setattr(cli, "_screen_intraday_impl", lambda **kwargs: tmp_path / "candidates" / "fake.json")

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

    assert result.exit_code == 0
    assert "outside trading-day intraday market hours" in result.stderr


def test_screen_intraday_does_not_warn_during_trading_hours(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 10:15:00", tz="Asia/Shanghai"),
        raising=False,
    )
    monkeypatch.setattr(cli, "_screen_intraday_impl", lambda **kwargs: tmp_path / "candidates" / "fake.json")

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

    assert result.exit_code == 0
    assert "outside trading-day intraday market hours" not in result.stderr


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
                pro_api=lambda: SimpleNamespace(
                    rt_k=lambda *, ts_code: (_ for _ in ()).throw(RuntimeError("boom"))
                ),
            ),
            "Failed to fetch Tushare rt_k snapshot: boom",
        ),
        (
            lambda: SimpleNamespace(
                set_token=lambda _token: None,
                pro_api=lambda: SimpleNamespace(rt_k=lambda *, ts_code: pd.DataFrame()),
            ),
            "Tushare rt_k returned no usable rows.",
        ),
    ],
)
def test_fetch_rt_k_snapshot_wraps_tushare_failures(monkeypatch, module_factory, expected_message: str) -> None:
    monkeypatch.setattr(cli, "_import_tushare_module", module_factory, raising=False)

    with pytest.raises(cli.IntradayUserError, match=expected_message):
        cli._fetch_rt_k_snapshot("token", "2026-04-09")


def test_fetch_rt_k_snapshot_batches_market_wildcards_and_normalizes_rows(monkeypatch) -> None:
    calls: list[str] = []

    def fake_rt_k(*, ts_code: str) -> pd.DataFrame:
        calls.append(ts_code)
        if ts_code == "*.SH":
            return pd.DataFrame(
                [
                    {
                        "ts_code": "600000.SH",
                        "name": "浦发银行",
                        "open": 10.1,
                        "high": 10.5,
                        "low": 10.0,
                        "close": 10.34,
                        "vol": 2234567,
                        "amount": 252300000.0,
                        "trade_time": "11:31:07",
                    }
                ]
            )
        if ts_code == "*.SZ":
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "name": "平安银行",
                        "open": 12.1,
                        "high": 12.5,
                        "low": 12.0,
                        "close": 12.34,
                        "vol": 1234567,
                        "amount": 152300000.0,
                        "trade_time": "11:31:08",
                    }
                ]
            )
        if ts_code == "*.BJ":
            return pd.DataFrame()
        raise AssertionError(f"unexpected ts_code={ts_code}")

    module = SimpleNamespace(
        set_token=lambda _token: None,
        pro_api=lambda: SimpleNamespace(rt_k=fake_rt_k),
    )
    monkeypatch.setattr(cli, "_import_tushare_module", lambda: module, raising=False)

    snapshot = cli._fetch_rt_k_snapshot("token", "2026-04-09")

    assert calls == ["*.SH", "*.SZ", "*.BJ"]
    assert snapshot.to_dict(orient="records") == [
        {
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "trade_date": "2026-04-09",
            "trade_time": "11:31:08",
            "open": 12.1,
            "high": 12.5,
            "low": 12.0,
            "close": 12.34,
            "vol": 12345.67,
            "amount": 152300.0,
        },
        {
            "ts_code": "600000.SH",
            "name": "浦发银行",
            "trade_date": "2026-04-09",
            "trade_time": "11:31:07",
            "open": 10.1,
            "high": 10.5,
            "low": 10.0,
            "close": 10.34,
            "vol": 22345.67,
            "amount": 252300.0,
        },
    ]


def test_fetch_rt_k_snapshot_uses_fetch_timestamp_when_trade_time_missing(monkeypatch) -> None:
    module = SimpleNamespace(
        set_token=lambda _token: None,
        pro_api=lambda: SimpleNamespace(
            rt_k=lambda *, ts_code: pd.DataFrame(
                [
                    {
                        "ts_code": "600000.SH",
                        "name": "浦发银行",
                        "pre_close": 10.0,
                        "open": 10.1,
                        "high": 10.5,
                        "low": 10.0,
                        "close": 10.34,
                        "vol": 2234567,
                        "amount": 252300000.0,
                        "num": 8133,
                    }
                ]
            )
            if ts_code == "*.SH"
            else pd.DataFrame()
        ),
    )
    monkeypatch.setattr(cli, "_import_tushare_module", lambda: module, raising=False)
    monkeypatch.setattr(
        cli,
        "_current_shanghai_timestamp",
        lambda: pd.Timestamp("2026-04-09 10:15:30.123456", tz="Asia/Shanghai"),
        raising=False,
    )

    snapshot = cli._fetch_rt_k_snapshot("token", "2026-04-09")

    assert snapshot.to_dict(orient="records") == [
        {
            "ts_code": "600000.SH",
            "name": "浦发银行",
            "trade_date": "2026-04-09",
            "trade_time": "10:15:30",
            "open": 10.1,
            "high": 10.5,
            "low": 10.0,
            "close": 10.34,
            "vol": 22345.67,
            "amount": 252300.0,
        }
    ]


def test_screen_intraday_writes_timestamped_candidate_and_shared_prepared(monkeypatch, tmp_path: Path) -> None:
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
    candidate_path = runtime_root / "candidates" / f"{_intraday_key(expected_run_id)}.json"
    prepared_path = runtime_root / "prepared" / "2026-04-09.intraday.pkl"
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


def test_screen_intraday_reuses_shared_prepared_cache_without_recompute(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    prepared_by_symbol = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-09"]),
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
        runtime_root / "prepared" / "2026-04-09.intraday.pkl",
        method="b1",
        pick_date="2026-04-09",
        start_date="2025-04-08",
        end_date="2026-04-09",
        prepared_by_symbol=prepared_by_symbol,
        metadata_overrides={
            "mode": "intraday_snapshot",
            "source": "tushare_rt_k",
            "run_id": "2026-04-09T10-00-00+08-00",
            "previous_trade_date": "2026-04-08",
        },
    )

    monkeypatch.setattr(cli, "_current_shanghai_timestamp", lambda: pd.Timestamp("2026-04-09 11:31:08.123456", tz="Asia/Shanghai"), raising=False)
    monkeypatch.setattr(cli, "_resolve_intraday_trade_date", lambda: "2026-04-09", raising=False)
    monkeypatch.setattr(cli, "_resolve_tushare_token", lambda _token: pytest.fail("intraday cache reuse should not require a tushare token"), raising=False)
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: pytest.fail("intraday cache reuse should not resolve a dsn"))
    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("intraday cache reuse should not connect to the database"))
    monkeypatch.setattr(cli, "_fetch_rt_k_snapshot", lambda token, trade_date: pytest.fail("intraday cache reuse should not fetch a fresh snapshot"), raising=False)
    monkeypatch.setattr(cli, "fetch_daily_window", lambda *args, **kwargs: pytest.fail("intraday cache reuse should not fetch market history"))
    monkeypatch.setattr(cli, "_prepare_screen_data", lambda *args, **kwargs: pytest.fail("intraday cache reuse should not recompute prepare"))
    monkeypatch.setattr(
        cli,
        "run_b1_screen_with_stats",
        lambda prepared_subset, pick_date, config: (
            [{"code": "000001.SZ", "pick_date": "2026-04-09", "close": 11.6, "turnover_n": 200.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
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
    assert "[screen] reuse prepared path=" in result.stderr


def test_screen_intraday_b2_reuses_shared_prepared_cache_without_recompute(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    prepared_by_symbol = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-09"]),
                "open": [11.9],
                "high": [12.1],
                "low": [11.8],
                "close": [12.0],
                "turnover_n": [200.0],
                "volume": [120.0],
            }
        )
    }
    cli._write_prepared_cache(
        runtime_root / "prepared" / "2026-04-09.intraday.pkl",
        method="b1",
        pick_date="2026-04-09",
        start_date="2025-04-08",
        end_date="2026-04-09",
        prepared_by_symbol=prepared_by_symbol,
        metadata_overrides={
            "mode": "intraday_snapshot",
            "source": "tushare_rt_k",
            "run_id": "2026-04-09T10-00-00+08-00",
            "previous_trade_date": "2026-04-08",
        },
    )

    monkeypatch.setattr(cli, "_current_shanghai_timestamp", lambda: pd.Timestamp("2026-04-09 11:31:08.123456", tz="Asia/Shanghai"), raising=False)
    monkeypatch.setattr(cli, "_resolve_intraday_trade_date", lambda: "2026-04-09", raising=False)
    monkeypatch.setattr(cli, "_resolve_tushare_token", lambda _token: pytest.fail("intraday b2 cache reuse should not require a tushare token"), raising=False)
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: pytest.fail("intraday b2 cache reuse should not resolve a dsn"))
    monkeypatch.setattr(cli, "_connect", lambda _dsn: pytest.fail("intraday b2 cache reuse should not connect to the database"))
    monkeypatch.setattr(cli, "_fetch_rt_k_snapshot", lambda token, trade_date: pytest.fail("intraday b2 cache reuse should not fetch a fresh snapshot"), raising=False)
    monkeypatch.setattr(cli, "fetch_daily_window", lambda *args, **kwargs: pytest.fail("intraday b2 cache reuse should not fetch market history"))
    monkeypatch.setattr(cli, "_prepare_screen_data", lambda *args, **kwargs: pytest.fail("intraday b2 cache reuse should not recompute prepare"))
    monkeypatch.setattr(
        cli,
        "run_b2_screen_with_stats",
        lambda prepared_subset, pick_date: (
            [{"code": "000001.SZ", "pick_date": "2026-04-09", "close": 12.0, "turnover_n": 200.0, "signal": "B2"}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_pre_ok": 0,
                "fail_pct": 0,
                "fail_volume": 0,
                "fail_k_shape": 0,
                "fail_j_up": 0,
                "fail_tr_ok": 0,
                "fail_above_lt": 0,
                "fail_duplicate_b2": 0,
                "fail_no_signal": 0,
                "selected": 1,
                "selected_b2": 1,
                "selected_b3": 0,
                "selected_b3_plus": 0,
                "selected_b4": 0,
                "selected_b5": 0,
            },
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b2",
            "--intraday",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert "[screen] reuse prepared path=" in result.stderr
    candidate_payload = json.loads(
        (
            runtime_root
            / "candidates"
            / f"{_intraday_key('2026-04-09T11-31-08-123456+08-00', 'b2')}.json"
        ).read_text(encoding="utf-8")
    )
    assert candidate_payload["run_id"] == "2026-04-09T11-31-08-123456+08-00"
    assert candidate_payload["trade_date"] == "2026-04-09"


def test_screen_intraday_record_watch_uses_watch_pool_subset(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "watch_pool.csv").write_text(
        "\n".join(
            [
                "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at",
                "b1,2026-04-08,000001.SZ,WATCH,1.0,signal,chosen,2026-04-08T10:00:00+08:00",
                "b1,2026-04-08,000002.SZ,WATCH,1.0,signal,missing,2026-04-08T10:00:00+08:00",
            ]
        ),
        encoding="utf-8",
    )

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
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: pytest.fail("turnover-top pool should not be used for intraday record-watch"),
    )
    monkeypatch.setattr(
        cli,
        "run_b1_screen_with_stats",
        lambda prepared_by_symbol, pick_date, config: (
            [{"code": "000001.SZ", "pick_date": "2026-04-09", "close": 12.34, "turnover_n": 120.0}],
            _b1_screen_stats(total_symbols=1, eligible=1, selected=1),
        )
        if list(prepared_by_symbol) == ["000001.SZ"]
        else pytest.fail("intraday record-watch should screen only the watch-pool subset"),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--intraday",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    candidate_files = list((runtime_root / "candidates").glob("*.json"))
    assert len(candidate_files) == 1
    candidate_payload = json.loads(candidate_files[0].read_text(encoding="utf-8"))
    assert candidate_payload["pool_source"] == "record-watch"
    assert [item["code"] for item in candidate_payload["candidates"]] == ["000001.SZ"]
    prepared_payload = pickle.loads(next((runtime_root / "prepared").glob("*.pkl")).read_bytes())
    assert prepared_payload["metadata"]["mode"] == "intraday_snapshot"


def test_screen_intraday_hcr_turnover_top_uses_liquidity_pool(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

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
        "_resolve_hcr_start_date",
        lambda connection, *, end_date, trading_days: "2025-04-29",
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
                },
                {
                    "ts_code": "000002.SZ",
                    "name": "万科A",
                    "trade_date": "2026-04-09",
                    "trade_time": "11:31:07",
                    "open": 22.1,
                    "high": 22.5,
                    "low": 22.0,
                    "close": 22.34,
                    "vol": 250.0,
                    "amount": 1999.0,
                },
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
                },
                {
                    "ts_code": "000002.SZ",
                    "trade_date": "2026-04-08",
                    "open": 21.9,
                    "high": 22.1,
                    "low": 21.8,
                    "close": 22.0,
                    "vol": 220.0,
                },
            ]
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-08", "2026-04-09"]),
                    "close": [12.0, 12.34],
                    "yx": [11.9, 12.2],
                    "p": [12.0, 12.25],
                    "resonance_gap_pct": [0.0083, 0.0041],
                    "turnover_n": [900.0, 1000.0],
                }
            ),
            "000002.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-08", "2026-04-09"]),
                    "close": [22.0, 22.34],
                    "yx": [21.9, 22.2],
                    "p": [22.0, 22.25],
                    "resonance_gap_pct": [0.0045, 0.0020],
                    "turnover_n": [1900.0, 2000.0],
                }
            ),
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-09"): ["000002.SZ"]},
    )
    monkeypatch.setattr(
        cli,
        "run_hcr_screen_with_stats",
        lambda prepared_by_symbol, pick_date: (
            [{"code": "000002.SZ", "pick_date": "2026-04-09", "close": 22.34, "turnover_n": 2000.0, "yx": 22.2, "p": 22.25, "resonance_gap_pct": 0.0020}],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_resonance": 0,
                "fail_close_floor": 0,
                "fail_breakout": 0,
                "selected": 1,
            },
        )
        if list(prepared_by_symbol) == ["000002.SZ"]
        else pytest.fail("intraday hcr turnover-top should screen only the liquidity pool subset"),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--intraday",
            "--pool-source",
            "turnover-top",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    candidate_payload = json.loads(next((runtime_root / "candidates").glob("*.json")).read_text(encoding="utf-8"))
    assert candidate_payload["pool_source"] == "turnover-top"
    assert [item["code"] for item in candidate_payload["candidates"]] == ["000002.SZ"]


def test_screen_intraday_hcr_uses_trade_date_lookback_window(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    fetch_args: dict[str, str] = {}

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
        "_resolve_hcr_start_date",
        lambda connection, *, end_date, trading_days: (
            "2025-04-29" if end_date == "2026-04-08" and trading_days == 239 else ""
        ),
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

    def fake_fetch_daily_window(
        connection: object,
        *,
        start_date: str,
        end_date: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        fetch_args["start_date"] = start_date
        fetch_args["end_date"] = end_date
        return pd.DataFrame(
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
        )

    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "000001.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-08", "2026-04-09"]),
                    "close": [12.0, 12.34],
                    "yx": [11.9, 12.2],
                    "p": [12.0, 12.25],
                    "resonance_gap_pct": [0.0083, 0.0041],
                    "turnover_n": [900.0, 1000.0],
                }
            )
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "run_hcr_screen_with_stats",
        lambda prepared_by_symbol, pick_date: (
            [],
            {
                "total_symbols": 1,
                "eligible": 1,
                "fail_insufficient_history": 0,
                "fail_resonance": 0,
                "fail_close_floor": 0,
                "fail_breakout": 1,
                "selected": 0,
            },
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--intraday",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    assert result.exit_code == 0
    assert fetch_args == {
        "start_date": "2025-04-29",
        "end_date": "2026-04-08",
    }
