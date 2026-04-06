from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import pandas as pd


class CursorLike(Protocol):
    description: Sequence[Sequence[Any] | None] | None

    def execute(self, query: str, params: dict[str, object] | None = None) -> None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...

    def __enter__(self) -> "CursorLike": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...


class ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...


def resolve_dsn(cli_dsn: str | None, env_dsn: str | None) -> str:
    if cli_dsn:
        return cli_dsn
    if env_dsn:
        return env_dsn
    msg = "A database DSN is required."
    raise ValueError(msg)


def fetch_daily_window(
    connection: ConnectionLike,
    *,
    start_date: str,
    end_date: str,
    symbols: Sequence[str] | None = None,
) -> pd.DataFrame:
    query = """
        SELECT ts_code, trade_date, open, close
        FROM daily_market
        WHERE trade_date BETWEEN %(start_date)s AND %(end_date)s
          AND (%(symbols)s IS NULL OR ts_code = ANY(%(symbols)s))
        ORDER BY trade_date ASC, ts_code ASC
    """
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "symbols": list(symbols) if symbols is not None else None,
    }
    return _fetch_dataframe(connection, query, params)


def fetch_symbol_history(
    connection: ConnectionLike,
    *,
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    query = """
        SELECT ts_code, trade_date, close
        FROM daily_market
        WHERE ts_code = %(symbol)s
          AND trade_date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY trade_date ASC
    """
    params = {
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
    }
    return _fetch_dataframe(connection, query, params)


def fetch_available_trade_dates(connection: ConnectionLike) -> pd.DataFrame:
    query = """
        SELECT trade_date
        FROM daily_market
        GROUP BY trade_date
        ORDER BY trade_date DESC
    """
    return _fetch_dataframe(connection, query, None)


def _fetch_dataframe(
    connection: ConnectionLike,
    query: str,
    params: dict[str, object] | None,
) -> pd.DataFrame:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [str(column[0]).lower() for column in (cursor.description or [])]
    return pd.DataFrame(rows, columns=columns)
