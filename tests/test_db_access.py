import pandas as pd
import pytest

from stock_select.db_access import (
    fetch_available_trade_dates,
    fetch_daily_window,
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


def test_resolve_dsn_prefers_argument() -> None:
    assert resolve_dsn("postgresql://example", None) == "postgresql://example"


def test_resolve_dsn_uses_env_when_argument_missing() -> None:
    assert resolve_dsn(None, "postgresql://env-only") == "postgresql://env-only"


def test_resolve_dsn_raises_when_no_dsn_available() -> None:
    with pytest.raises(ValueError, match="database DSN"):
        resolve_dsn(None, None)


def test_fetch_daily_window_normalizes_columns_and_params() -> None:
    connection = FakeConnection(
        rows=[("000001.SZ", "2026-04-01", 10.0, 10.5)],
        columns=["TS_CODE", "TRADE_DATE", "OPEN", "CLOSE"],
    )

    result = fetch_daily_window(
        connection,
        start_date="2026-04-01",
        end_date="2026-04-30",
        symbols=["000001.SZ"],
    )

    assert list(result.columns) == ["ts_code", "trade_date", "open", "close"]
    assert result.to_dict(orient="records") == [
        {"ts_code": "000001.SZ", "trade_date": "2026-04-01", "open": 10.0, "close": 10.5}
    ]
    assert connection.cursor_obj.executed[0][1] == {
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
        "symbols": ["000001.SZ"],
    }


def test_fetch_symbol_history_uses_symbol_and_date_window() -> None:
    connection = FakeConnection(
        rows=[("000001.SZ", "2026-04-01", 10.5)],
        columns=["TS_CODE", "TRADE_DATE", "CLOSE"],
    )

    result = fetch_symbol_history(
        connection,
        symbol="000001.SZ",
        start_date="2026-04-01",
        end_date="2026-04-30",
    )

    assert isinstance(result, pd.DataFrame)
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
