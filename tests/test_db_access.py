import pandas as pd
import pytest
from pathlib import Path

from stock_select.db_access import (
    fetch_available_trade_dates,
    fetch_daily_window,
    fetch_instrument_names,
    load_dotenv_value,
    fetch_symbol_history,
    resolve_dsn,
)


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str]) -> None:
        self._rows = rows
        self.description = [(name, None, None, None, None, None, None) for name in columns]
        self.executed: list[tuple[str, dict[str, object] | None]] = []

    def execute(self, query: str, params: dict[str, object] | None = None) -> None:
        self.executed.append((query, params))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]], columns: list[str]) -> None:
        self.cursor_obj = FakeCursor(rows, columns)

    def cursor(self) -> FakeCursor:
        return self.cursor_obj


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor([], [])

    def cursor(self) -> FakeCursor:
        return self.cursor_obj


def test_resolve_dsn_prefers_argument() -> None:
    assert resolve_dsn("postgresql://example", None) == "postgresql://example"


def test_resolve_dsn_uses_env_when_argument_missing() -> None:
    assert resolve_dsn(None, "postgresql://env-only") == "postgresql://env-only"


def test_resolve_dsn_uses_dotenv_when_argument_and_env_missing() -> None:
    assert resolve_dsn(None, None, "postgresql://dotenv-only") == "postgresql://dotenv-only"


def test_resolve_dsn_raises_when_no_dsn_available() -> None:
    with pytest.raises(ValueError, match="database DSN"):
        resolve_dsn(None, None, None)


def test_load_dotenv_value_reads_postgres_dsn(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text('POSTGRES_DSN="postgresql://dotenv"\nOTHER=value\n', encoding="utf-8")

    assert load_dotenv_value(env_path, "POSTGRES_DSN") == "postgresql://dotenv"


def test_load_dotenv_value_supports_export_prefix(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("export POSTGRES_DSN=postgresql://dotenv-export\n", encoding="utf-8")

    assert load_dotenv_value(env_path, "POSTGRES_DSN") == "postgresql://dotenv-export"


def test_fetch_daily_window_normalizes_columns_and_params() -> None:
    connection = FakeConnection(
        rows=[("000001.SZ", "2026-04-01", 10.0, 10.8, 9.8, 10.5, 1200.0)],
        columns=["TS_CODE", "TRADE_DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOL"],
    )

    result = fetch_daily_window(
        connection,
        start_date="2026-04-01",
        end_date="2026-04-30",
        symbols=["000001.SZ"],
    )

    assert list(result.columns) == ["ts_code", "trade_date", "open", "high", "low", "close", "vol"]
    assert result.to_dict(orient="records") == [
        {
            "ts_code": "000001.SZ",
            "trade_date": "2026-04-01",
            "open": 10.0,
            "high": 10.8,
            "low": 9.8,
            "close": 10.5,
            "vol": 1200.0,
        }
    ]
    assert connection.cursor_obj.executed[0][1] == {
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
        "symbols": ["000001.SZ"],
    }


def test_fetch_daily_window_omits_symbol_filter_when_symbols_missing() -> None:
    connection = RecordingConnection()

    fetch_daily_window(
        connection,
        start_date="2026-04-01",
        end_date="2026-04-30",
        symbols=None,
    )

    query, params = connection.cursor_obj.executed[0]
    assert "ANY(%(symbols)s)" not in query
    assert "ts_code = ANY" not in query
    assert params == {
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
    }


def test_fetch_symbol_history_uses_symbol_and_date_window() -> None:
    connection = FakeConnection(
        rows=[("000001.SZ", "2026-04-01", 10.0, 10.8, 9.8, 10.5, 1200.0)],
        columns=["TS_CODE", "TRADE_DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOL"],
    )

    result = fetch_symbol_history(
        connection,
        symbol="000001.SZ",
        start_date="2026-04-01",
        end_date="2026-04-30",
    )

    assert isinstance(result, pd.DataFrame)
    assert result.to_dict(orient="records") == [
        {
            "ts_code": "000001.SZ",
            "trade_date": "2026-04-01",
            "open": 10.0,
            "high": 10.8,
            "low": 9.8,
            "close": 10.5,
            "vol": 1200.0,
        }
    ]
    assert connection.cursor_obj.executed[0][1] == {
        "symbol": "000001.SZ",
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
    }


def test_fetch_available_trade_dates_returns_normalized_frame() -> None:
    connection = FakeConnection(
        rows=[("2026-04-03",), ("2026-04-02",)],
        columns=["TRADE_DATE"],
    )

    result = fetch_available_trade_dates(connection)

    assert result.to_dict(orient="records") == [
        {"trade_date": "2026-04-03"},
        {"trade_date": "2026-04-02"},
    ]


def test_fetch_instrument_names_returns_code_name_mapping() -> None:
    connection = FakeConnection(
        rows=[("000001.SZ", "平安银行"), ("000002.SZ", "万科A")],
        columns=["TS_CODE", "NAME"],
    )

    result = fetch_instrument_names(connection, symbols=["000001.SZ", "000002.SZ"])

    assert result == {
        "000001.SZ": "平安银行",
        "000002.SZ": "万科A",
    }
    query, params = connection.cursor_obj.executed[0]
    assert "FROM instruments" in query
    assert "ts_code = ANY(%(symbols)s)" in query
    assert params == {"symbols": ["000001.SZ", "000002.SZ"]}
