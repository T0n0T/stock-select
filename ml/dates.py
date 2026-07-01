from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path


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


def fetch_trade_dates(dsn: str, start_date: str, end_date: str) -> list[str]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select distinct trade_date
                from stock_stk_factor_pro
                where trade_date between %s and %s
                order by trade_date
                """,
                (validate_date(start_date), validate_date(end_date)),
            )
            return [row[0].isoformat() for row in cur.fetchall()]
