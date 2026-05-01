from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import NamedTuple, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.db_access import fetch_available_trade_dates, load_dotenv_value, resolve_dsn
from stock_select.strategies import validate_method


DEFAULT_END_DATE = "2026-04-30"
DEFAULT_START_DATE = None  # None means use default behavior (last N days before end_date)
DEFAULT_SAMPLE_SIZE = 5
DEFAULT_METHOD = "b2"
DEFAULT_LLM_MIN_BASELINE_SCORE = 4.3
DEFAULT_MAX_WORKERS_BY_METHOD = {
    "b1": 6,
    "b2": 6,
    "dribull": 6,
    "hcr": 10,
}


class BackfillPlan(NamedTuple):
    completed_dates: list[str]
    missing_dates: list[str]


def default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def validate_pick_date(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        raise ValueError("pick_date must be a valid date in YYYY-MM-DD format.")
    try:
        return pd.Timestamp(normalized).strftime("%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError("pick_date must be a valid date in YYYY-MM-DD format.") from exc


def collect_target_trade_dates(
    trade_dates: pd.DataFrame,
    *,
    sample_size: int,
    end_date: str,
    start_date: str | None = None,
) -> list[str]:
    """
    Collect target trade dates within the specified range.
    
    If start_date is provided, returns all trade dates between start_date and end_date (inclusive).
    If start_date is None, returns the last sample_size trade dates on or before end_date.
    """
    if sample_size <= 0:
        raise ValueError("sample_size must be positive.")

    if "trade_date" not in trade_dates.columns:
        raise ValueError("trade_dates must include a trade_date column.")

    normalized = pd.to_datetime(trade_dates["trade_date"], errors="coerce", format="mixed")
    unique_dates = sorted({timestamp.strftime("%Y-%m-%d") for timestamp in normalized.loc[normalized.notna()]})

    # Filter by end_date
    filtered = [value for value in unique_dates if value <= end_date]
    
    if not filtered:
        raise ValueError(f"No trade dates found on or before {end_date}.")
    
    if start_date is not None:
        # Range mode: filter by start_date as well
        filtered = [value for value in filtered if value >= start_date]
        if not filtered:
            raise ValueError(f"No trade dates found between {start_date} and {end_date}.")
        return filtered
    
    # Default mode: return last sample_size dates
    if len(filtered) < sample_size:
        raise ValueError(
            f"Only found {len(filtered)} trade dates on or before {end_date}, fewer than requested {sample_size}."
        )
    return filtered[-sample_size:]


def review_summary_path(runtime_root: Path, *, pick_date: str, method: str) -> Path:
    return runtime_root / "reviews" / f"{pick_date}.{method}" / "summary.json"


def plan_backfill(*, target_dates: Sequence[str], runtime_root: Path, method: str) -> BackfillPlan:
    completed_dates: list[str] = []
    missing_dates: list[str] = []
    for pick_date in target_dates:
        if review_summary_path(runtime_root, pick_date=pick_date, method=method).exists():
            completed_dates.append(pick_date)
            continue
        missing_dates.append(pick_date)
    return BackfillPlan(completed_dates=completed_dates, missing_dates=missing_dates)


def build_run_command(
    *,
    pick_date: str,
    method: str,
    llm_min_baseline_score: float,
    dsn: str | None,
    stock_select_bin: str = "stock-select",
) -> list[str]:
    command = [
        stock_select_bin,
        "run",
        "--method",
        method,
        "--llm-min-baseline-score",
        str(llm_min_baseline_score),
        "--pick-date",
        pick_date,
    ]
    if dsn:
        command.extend(["--dsn", dsn])
    return command


def validate_max_workers(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max_workers must be a positive integer.") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("max_workers must be a positive integer.")
    return parsed


def method_default_max_workers(method: str) -> int:
    normalized = validate_method(method)
    return DEFAULT_MAX_WORKERS_BY_METHOD[normalized]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill run samples across a trade-date window, skipping dates with an existing review summary. "
            "Provide --start-date and --end-date to specify a date range, or just --end-date to run on the last N days."
        ),
    )
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--llm-min-baseline-score", type=float, default=DEFAULT_LLM_MIN_BASELINE_SCORE)
    parser.add_argument("--dsn")
    parser.add_argument("--runtime-root", type=Path, default=default_runtime_root())
    parser.add_argument("--stock-select-bin", default="stock-select")
    parser.add_argument("--max-workers", type=validate_max_workers)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    args.method = validate_method(args.method)
    if args.max_workers is None:
        args.max_workers = method_default_max_workers(args.method)

    # Validate dates
    args.end_date = validate_pick_date(args.end_date)
    
    if args.start_date is not None:
        args.start_date = validate_pick_date(args.start_date)
        if args.start_date > args.end_date:
            parser.error(f"start_date ({args.start_date}) cannot be after end_date ({args.end_date}).")

    return args


def resolve_script_dsn(cli_dsn: str | None) -> str:
    dotenv_dsn = load_dotenv_value(PROJECT_ROOT / ".env", "POSTGRES_DSN")
    return resolve_dsn(cli_dsn, os.getenv("POSTGRES_DSN"), dotenv_dsn)


def print_plan(*, target_dates: Sequence[str], plan: BackfillPlan) -> None:
    print(f"target trade dates ({len(target_dates)}): {', '.join(target_dates)}")
    print(f"completed dates ({len(plan.completed_dates)}): {', '.join(plan.completed_dates) if plan.completed_dates else '(none)'}")
    print(f"missing dates ({len(plan.missing_dates)}): {', '.join(plan.missing_dates) if plan.missing_dates else '(none)'}")


def run_single_backfill(
    *,
    index: int,
    total: int,
    pick_date: str,
    method: str,
    llm_min_baseline_score: float,
    dsn: str | None,
    stock_select_bin: str,
) -> str:
    command = build_run_command(
        pick_date=pick_date,
        method=method,
        llm_min_baseline_score=llm_min_baseline_score,
        dsn=dsn,
        stock_select_bin=stock_select_bin,
    )
    print(f"[{index}/{total}] running: {' '.join(command)}")
    subprocess.run(command, check=True)
    return pick_date


def run_missing_dates(
    *,
    missing_dates: Sequence[str],
    method: str,
    llm_min_baseline_score: float,
    dsn: str | None,
    stock_select_bin: str,
    max_workers: int,
) -> None:
    total = len(missing_dates)
    if total == 0:
        return

    worker_count = min(max_workers, total)
    print(f"starting {total} backfill runs with max_workers={worker_count}")

    failures: list[tuple[str, list[str], BaseException]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_job = {
            executor.submit(
                run_single_backfill,
                index=index,
                total=total,
                pick_date=pick_date,
                method=method,
                llm_min_baseline_score=llm_min_baseline_score,
                dsn=dsn,
                stock_select_bin=stock_select_bin,
            ): (
                pick_date,
                build_run_command(
                    pick_date=pick_date,
                    method=method,
                    llm_min_baseline_score=llm_min_baseline_score,
                    dsn=dsn,
                    stock_select_bin=stock_select_bin,
                ),
            )
            for index, pick_date in enumerate(missing_dates, start=1)
        }
        for future in as_completed(future_to_job):
            pick_date, command = future_to_job[future]
            try:
                future.result()
            except BaseException as exc:
                failures.append((pick_date, command, exc))
                print(f"failed {pick_date}: {' '.join(command)}")

    if failures:
        failed_dates = ", ".join(pick_date for pick_date, _, _ in failures)
        raise RuntimeError(f"Backfill failed for {len(failures)} date(s): {failed_dates}") from failures[0][2]


def run_backfill(argv: Sequence[str] | None = None) -> int:
    import psycopg

    args = parse_args(argv)
    dsn = resolve_script_dsn(args.dsn)

    with psycopg.connect(dsn) as connection:
        trade_dates = fetch_available_trade_dates(connection)

    target_dates = collect_target_trade_dates(
        trade_dates,
        end_date=args.end_date,
        start_date=args.start_date,
        sample_size=args.sample_size,
    )
    plan = plan_backfill(target_dates=target_dates, runtime_root=args.runtime_root, method=args.method)
    print_plan(target_dates=target_dates, plan=plan)

    if args.dry_run or not plan.missing_dates:
        return 0

    run_missing_dates(
        missing_dates=plan.missing_dates,
        method=args.method,
        llm_min_baseline_score=args.llm_min_baseline_score,
        dsn=args.dsn,
        stock_select_bin=args.stock_select_bin,
        max_workers=args.max_workers,
    )

    return 0


def main() -> int:
    return run_backfill()


if __name__ == "__main__":
    raise SystemExit(main())