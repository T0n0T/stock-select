from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from ml.db import query_rows


def validate_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def weekday_fallback(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(validate_date(start_date))
    end = date.fromisoformat(validate_date(end_date))
    dates: list[str] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def read_dates_file(path: Path) -> list[str]:
    dates: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        dates.append(validate_date(value))
    return sorted(dict.fromkeys(dates))


def fetch_trade_dates(duckdb_path: str, start_date: str, end_date: str, *, binary: Path | None = None) -> list[str]:
    options = {"binary": binary} if binary is not None else {}
    rows = query_rows(duckdb_path, """
        SELECT DISTINCT trade_date FROM stock_stk_factor_pro
        WHERE trade_date BETWEEN $1::DATE AND $2::DATE
        ORDER BY trade_date
        """, [validate_date(start_date), validate_date(end_date)], **options)
    return [str(row["trade_date"]) for row in rows]
