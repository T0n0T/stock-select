from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import pandas as pd
import psycopg

from stock_select.db_access import fetch_index_history, load_dotenv_value, resolve_dsn
from stock_select.market_environment import (
    build_environment_history_for_dates,
    evaluate_market_environment,
    write_environment_history,
)


DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def _parser_error(args: argparse.Namespace, message: str) -> "Never":
    parser = getattr(args, "_parser", None)
    if parser is not None:
        parser.error(message)
    raise SystemExit(message)


def _connect(dsn: str):
    return psycopg.connect(dsn)


def _resolve_cli_dsn(dsn: str | None) -> str:
    dotenv_dsn = load_dotenv_value(Path.cwd() / ".env", "POSTGRES_DSN")
    return resolve_dsn(dsn, os.getenv("POSTGRES_DSN"), dotenv_dsn)


def _fetch_dataframe(
    connection,
    query: str,
    params: dict[str, object],
) -> pd.DataFrame:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [str(column[0]).lower() for column in (cursor.description or [])]
    return pd.DataFrame(rows, columns=columns)


def _fetch_index_history_from_daily_index(
    connection,
    *,
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    query = """
        SELECT ts_code, trade_date, open, high, low, close, vol
        FROM daily_index
        WHERE ts_code = %(symbol)s
          AND trade_date BETWEEN %(start_date)s AND %(end_date)s
        ORDER BY trade_date ASC
    """
    return _fetch_dataframe(
        connection,
        query,
        {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


def _fetch_index_history_with_fallback(
    connection,
    *,
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    try:
        return fetch_index_history(
            connection,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
    except psycopg.errors.UndefinedTable:
        rollback = getattr(connection, "rollback", None)
        if callable(rollback):
            rollback()
        return _fetch_index_history_from_daily_index(
            connection,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )


def _resolve_samples_path(args: argparse.Namespace) -> Path:
    if args.samples is not None:
        return args.samples
    if args.artifact_dir is not None:
        return args.artifact_dir / "samples.csv"
    _parser_error(args, "either --artifact-dir or --samples is required")


def _history_path(runtime_root: Path) -> Path:
    return runtime_root / "environment" / "history.json"


def _load_pick_dates(samples_path: Path) -> list[str]:
    frame = pd.read_csv(samples_path)
    if "pick_date" not in frame.columns:
        raise ValueError(f"samples file missing pick_date column: {samples_path}")
    return sorted({str(value).strip() for value in frame["pick_date"].tolist() if str(value).strip()})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill runtime market environment history from review tuning samples")
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--dsn")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.artifact_dir is None and args.samples is None:
        parser.error("either --artifact-dir or --samples is required")
    setattr(args, "_parser", parser)
    return args


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    samples_path = _resolve_samples_path(args)
    pick_dates = _load_pick_dates(samples_path)
    if not pick_dates:
        raise SystemExit(f"no pick_date values found in {samples_path}")

    history_path = _history_path(args.runtime_root)
    if history_path.exists() and not args.overwrite:
        raise SystemExit(f"environment history already exists: {history_path}; rerun with --overwrite")

    dsn = _resolve_cli_dsn(args.dsn)
    start_date = str((pd.Timestamp(pick_dates[0]) - pd.Timedelta(days=180)).strftime("%Y-%m-%d"))
    end_date = pick_dates[-1]

    connection = _connect(dsn)
    try:
        sse_history = _fetch_index_history_with_fallback(
            connection,
            symbol="000001.SH",
            start_date=start_date,
            end_date=end_date,
        )
        cn2000_history = _fetch_index_history_with_fallback(
            connection,
            symbol="399303.SZ",
            start_date=start_date,
            end_date=end_date,
        )
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    intervals = build_environment_history_for_dates(
        pick_dates,
        lambda pick_date: evaluate_market_environment(
            pick_date=pick_date,
            sse_history=sse_history,
            cn2000_history=cn2000_history,
        ),
    )

    for interval in intervals:
        interval["source"] = "backfill"

    write_environment_history(args.runtime_root, intervals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
