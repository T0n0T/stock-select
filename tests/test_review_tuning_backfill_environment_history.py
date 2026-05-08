from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pandas as pd
import pytest


def _load_backfill_environment_history_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_backfill_environment_history.py"
    )
    spec = importlib.util.spec_from_file_location("review_tuning_backfill_environment_history", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_backfill_environment_history_main_writes_runtime_history_from_artifact_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backfill_environment_history_module()

    artifact_dir = tmp_path / "artifacts" / "review-tuning" / "baseline"
    artifact_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"method": "b2", "pick_date": "2026-04-03", "code": "000001.SZ"},
            {"method": "b2", "pick_date": "2026-04-01", "code": "000002.SZ"},
            {"method": "b2", "pick_date": "2026-04-01", "code": "000003.SZ"},
        ]
    ).to_csv(artifact_dir / "samples.csv", index=False)

    captured: dict[str, object] = {}

    monkeypatch.setattr(module, "_connect", lambda _dsn: object())

    def fake_fetch_index_history(_connection, *, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        captured.setdefault("fetches", []).append((symbol, start_date, end_date))
        return pd.DataFrame(
            [
                {
                    "ts_code": symbol,
                    "trade_date": "2026-04-01",
                    "open": 10.0,
                    "high": 10.2,
                    "low": 9.8,
                    "close": 10.1,
                    "vol": 1000.0,
                }
            ]
        )

    monkeypatch.setattr(module, "fetch_index_history", fake_fetch_index_history)

    def fake_rebuild_environment_history(*, runtime_root, pick_dates, sse_history, cn2000_history, overwrite, source="backfill"):
        captured["pick_dates"] = pick_dates
        captured["overwrite"] = overwrite
        path = runtime_root / "environment"
        path.mkdir(parents=True, exist_ok=True)
        daily_dir = path / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        (daily_dir / "2026-04-01.weak.json").write_text(
            json.dumps(
                {
                    "pick_date": "2026-04-01",
                    "state": "weak",
                    "score_based_state": "weak",
                    "rule_based_state": "weak",
                    "vote_based_state": "weak",
                    "evaluate_date": "2026-04-01",
                    "source": "backfill",
                    "reason": "backfilled",
                    "total_score": 0.0,
                    "score_based_total": 0.0,
                    "manual_override": False,
                }
            ),
            encoding="utf-8",
        )
        (path / "history.jsonl").write_text(
            '{"pick_date":"2026-04-01","state":"weak","score_based_state":"weak","rule_based_state":"weak","vote_based_state":"weak","evaluate_date":"2026-04-01","source":"backfill","reason":"backfilled","total_score":0.0,"score_based_total":0.0,"manual_override":false}\n',
            encoding="utf-8",
        )
        latest = path / "latest.json"
        latest.write_text(
            json.dumps(
                {
                    "daily": [
                        {
                            "pick_date": "2026-04-01",
                            "state": "weak",
                            "source": "backfill",
                            "reason": "backfilled",
                        }
                    ],
                    "intervals": [
                        {
                            "state": "weak",
                            "start_date": "2026-04-01",
                            "end_date": None,
                            "evaluated_at": "2026-04-01",
                            "source": "backfill",
                            "manual_override": False,
                            "reason": "backfilled",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return latest

    monkeypatch.setattr(module, "rebuild_environment_history", fake_rebuild_environment_history)

    runtime_root = tmp_path / "runtime"
    args = module.parse_args(
        [
            "--artifact-dir",
            str(artifact_dir),
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ]
    )

    assert module.main(args) == 0
    assert captured["pick_dates"] == ["2026-04-01", "2026-04-03"]
    assert captured["overwrite"] is False
    assert captured["fetches"] == [
        ("000001.SH", "2025-10-03", "2026-04-03"),
        ("399303.SZ", "2025-10-03", "2026-04-03"),
    ]

    latest = json.loads((runtime_root / "environment" / "latest.json").read_text(encoding="utf-8"))
    assert (runtime_root / "environment" / "daily" / "2026-04-01.weak.json").exists()
    assert (runtime_root / "environment" / "history.jsonl").exists()
    assert latest == {
        "daily": [
            {
                "pick_date": "2026-04-01",
                "state": "weak",
                "source": "backfill",
                "reason": "backfilled",
            }
        ],
        "intervals": [
            {
                "state": "weak",
                "start_date": "2026-04-01",
                "end_date": None,
                "evaluated_at": "2026-04-01",
                "source": "backfill",
                "manual_override": False,
                "reason": "backfilled",
            }
        ]
    }


def test_backfill_environment_history_main_rejects_existing_history_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backfill_environment_history_module()

    artifact_dir = tmp_path / "artifacts" / "review-tuning" / "baseline"
    artifact_dir.mkdir(parents=True)
    pd.DataFrame([{"method": "b2", "pick_date": "2026-04-01", "code": "000001.SZ"}]).to_csv(
        artifact_dir / "samples.csv", index=False
    )

    runtime_root = tmp_path / "runtime"
    environment_dir = runtime_root / "environment"
    environment_dir.mkdir(parents=True)
    (environment_dir / "history.jsonl").write_text(
        '{"state":"neutral","start_date":"2026-04-01","end_date":null,"evaluated_at":"2026-04-01","source":"scheduled","manual_override":false,"reason":"range"}\n',
        encoding="utf-8",
    )

    args = module.parse_args(
        [
            "--artifact-dir",
            str(artifact_dir),
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ]
    )

    monkeypatch.setattr(
        module,
        "rebuild_environment_history",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError(f"environment history already exists: {runtime_root / 'environment' / 'history.jsonl'}; rerun with --overwrite")
        ),
    )

    with pytest.raises(SystemExit, match="already exists"):
        module.main(args)


def test_backfill_environment_history_resolves_dsn_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_backfill_environment_history_module()

    monkeypatch.setenv("POSTGRES_DSN", "postgresql://env-dsn")

    assert module._resolve_cli_dsn(None) == "postgresql://env-dsn"


class _FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str]) -> None:
        self._rows = rows
        self.description = [(name, None, None, None, None, None, None) for name in columns]
        self.executed: list[tuple[str, dict[str, object]]] = []

    def execute(self, query: str, params: dict[str, object] | None = None) -> None:
        self.executed.append((query, params or {}))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str]) -> None:
        self.cursor_obj = _FakeCursor(rows, columns)
        self.rollback_called = False

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj

    def rollback(self) -> None:
        self.rollback_called = True


def test_fetch_index_history_with_fallback_reads_daily_index_when_index_daily_market_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_backfill_environment_history_module()
    connection = _FakeConnection(
        [("000001.SH", "2026-04-01", 3200.0, 3220.0, 3190.0, 3215.0, 4200000.0)],
        ["TS_CODE", "TRADE_DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOL"],
    )

    def raise_undefined_table(*args, **kwargs):
        raise module.psycopg.errors.UndefinedTable("missing relation")

    monkeypatch.setattr(module, "fetch_index_history", raise_undefined_table)

    result = module._fetch_index_history_with_fallback(
        connection,
        symbol="000001.SH",
        start_date="2026-04-01",
        end_date="2026-04-30",
    )

    assert result.to_dict("records") == [
        {
            "ts_code": "000001.SH",
            "trade_date": "2026-04-01",
            "open": 3200.0,
            "high": 3220.0,
            "low": 3190.0,
            "close": 3215.0,
            "vol": 4200000.0,
        }
    ]
    query, params = connection.cursor_obj.executed[0]
    assert "FROM daily_index" in query
    assert params == {
        "symbol": "000001.SH",
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
    }
    assert connection.rollback_called is True
