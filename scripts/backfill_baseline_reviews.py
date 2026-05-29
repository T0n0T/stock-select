# /// script
# dependencies = [
#   "psycopg[binary]",
# ]
# ///
from __future__ import annotations

import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METHOD = "b2"
DEFAULT_SAMPLE_SIZE = 5
DEFAULT_END_DATE = "2026-04-30"
SUPPORTED_METHODS = {"b1", "b2", "dribull"}
DEFAULT_MAX_WORKERS = 1


@dataclass(frozen=True)
class BackfillPlan:
    completed_dates: list[str]
    missing_dates: list[str]


def default_runtime_root() -> Path:
    return Path.home() / ".agents" / "skills" / "stock-select" / "runtime"


def default_stock_select_bin() -> str:
    local_debug = PROJECT_ROOT / "target" / "debug" / "stock-select-rs"
    if local_debug.exists():
        return str(local_debug)
    return "stock-select-rs"


def load_dotenv_value(env_path: Path, key: str) -> str | None:
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        candidate_key, candidate_value = line.split("=", 1)
        if candidate_key.strip() != key:
            continue
        value = candidate_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def resolve_dsn(cli_dsn: str | None) -> str:
    for value in (cli_dsn, os.getenv("POSTGRES_DSN"), load_dotenv_value(PROJECT_ROOT / ".env", "POSTGRES_DSN")):
        if value and value.strip():
            return value.strip()
    raise ValueError("A database DSN is required.")


def validate_method(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_METHODS:
        raise argparse.ArgumentTypeError("method must be one of: b1, b2, dribull.")
    return normalized


def validate_pick_date(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be a valid calendar date.") from exc


def validate_positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer.") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer.")
    return parsed


def fetch_available_trade_dates(dsn: str) -> list[str]:
    import psycopg

    query = """
        SELECT trade_date
        FROM daily_market
        GROUP BY trade_date
        ORDER BY trade_date ASC
    """
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return [row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]) for row in cursor.fetchall()]


def collect_target_trade_dates(
    trade_dates: Sequence[str],
    *,
    sample_size: int,
    end_date: str,
    start_date: str | None = None,
) -> list[str]:
    if sample_size <= 0:
        raise ValueError("sample_size must be positive.")
    unique_dates = sorted({validate_pick_date(value) for value in trade_dates})
    filtered = [value for value in unique_dates if value <= end_date]
    if start_date is not None:
        filtered = [value for value in filtered if value >= start_date]
        if not filtered:
            raise ValueError(f"No trade dates found between {start_date} and {end_date}.")
        return filtered
    if len(filtered) < sample_size:
        raise ValueError(
            f"Only found {len(filtered)} trade dates on or before {end_date}, fewer than requested {sample_size}."
        )
    return filtered[-sample_size:]


def review_summary_path(runtime_root: Path, *, pick_date: str, method: str) -> Path:
    return runtime_root / "reviews" / f"{pick_date}.{method}" / "summary.json"


def environment_daily_exists(runtime_root: Path, *, pick_date: str) -> bool:
    return any((runtime_root / "environment" / "daily").glob(f"{pick_date}.*.json"))


def plan_backfill(
    *,
    target_dates: Sequence[str],
    runtime_root: Path,
    method: str,
    force: bool,
) -> BackfillPlan:
    completed_dates: list[str] = []
    missing_dates: list[str] = []
    for pick_date in target_dates:
        if not force and review_summary_path(runtime_root, pick_date=pick_date, method=method).exists() and environment_daily_exists(
            runtime_root, pick_date=pick_date
        ):
            completed_dates.append(pick_date)
        else:
            missing_dates.append(pick_date)
    return BackfillPlan(completed_dates=completed_dates, missing_dates=missing_dates)


def build_run_command(
    *,
    pick_date: str,
    method: str,
    dsn: str | None,
    runtime_root: Path,
    stock_select_bin: str,
    llm_min_baseline_score: float | None,
    llm_review_limit: int | None,
    recompute: bool,
    no_progress: bool,
) -> list[str]:
    command = [
        stock_select_bin,
        "run",
        "--method",
        method,
        "--pick-date",
        pick_date,
    ]
    if dsn:
        command.extend(["--dsn", dsn])
    command.extend(["--runtime-root", str(runtime_root)])
    if llm_min_baseline_score is not None:
        command.extend(["--llm-min-baseline-score", str(llm_min_baseline_score)])
    if llm_review_limit is not None:
        command.extend(["--llm-review-limit", str(llm_review_limit)])
    if recompute:
        command.append("--recompute")
    if no_progress:
        command.append("--no-progress")
    return command


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill Rust baseline review results over a trade-date window. "
            "With --start-date it processes every trade date in the range; otherwise it processes the last N dates on or before --end-date."
        )
    )
    parser.add_argument("--method", type=validate_method, default=DEFAULT_METHOD)
    parser.add_argument("--start-date", type=validate_pick_date)
    parser.add_argument("--end-date", type=validate_pick_date, default=DEFAULT_END_DATE)
    parser.add_argument("--sample-size", type=validate_positive_int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--dsn")
    parser.add_argument("--runtime-root", type=Path, default=default_runtime_root())
    parser.add_argument("--stock-select-bin", default=default_stock_select_bin())
    parser.add_argument(
        "--max-workers",
        type=validate_positive_int,
        default=DEFAULT_MAX_WORKERS,
        help="parallel run count; defaults to 1 because backfills share one runtime cache",
    )
    parser.add_argument("--llm-min-baseline-score", type=float)
    parser.add_argument("--llm-review-limit", type=validate_positive_int)
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--force", action="store_true", help="run dates even when summary and environment files already exist")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-progress", action="store_true", default=True)
    args = parser.parse_args(argv)
    if args.start_date and args.start_date > args.end_date:
        parser.error(f"start_date ({args.start_date}) cannot be after end_date ({args.end_date}).")
    return args


def print_plan(*, target_dates: Sequence[str], plan: BackfillPlan) -> None:
    print(f"target trade dates ({len(target_dates)}): {', '.join(target_dates)}")
    print(f"completed dates ({len(plan.completed_dates)}): {', '.join(plan.completed_dates) if plan.completed_dates else '(none)'}")
    print(f"missing dates ({len(plan.missing_dates)}): {', '.join(plan.missing_dates) if plan.missing_dates else '(none)'}")


def run_single_backfill(*, index: int, total: int, command: Sequence[str], pick_date: str) -> str:
    print(f"[{index}/{total}] running: {' '.join(command)}")
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    return pick_date


def run_missing_dates(
    *,
    missing_dates: Sequence[str],
    method: str,
    dsn: str | None,
    runtime_root: Path,
    stock_select_bin: str,
    llm_min_baseline_score: float | None,
    llm_review_limit: int | None,
    recompute: bool,
    no_progress: bool,
    max_workers: int,
) -> None:
    total = len(missing_dates)
    if total == 0:
        return
    worker_count = min(max_workers, total)
    failures: list[tuple[str, list[str], BaseException]] = []
    print(f"starting {total} backfill runs with max_workers={worker_count}")
    if worker_count > 1:
        print(
            "warning: concurrent backfills share one runtime root; "
            "Rust protects environment writes, but resource pressure can still require retrying failed dates."
        )
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_job = {}
        for index, pick_date in enumerate(missing_dates, start=1):
            command = build_run_command(
                pick_date=pick_date,
                method=method,
                dsn=dsn,
                runtime_root=runtime_root,
                stock_select_bin=stock_select_bin,
                llm_min_baseline_score=llm_min_baseline_score,
                llm_review_limit=llm_review_limit,
                recompute=recompute,
                no_progress=no_progress,
            )
            future = executor.submit(run_single_backfill, index=index, total=total, command=command, pick_date=pick_date)
            future_to_job[future] = (pick_date, command)
        for future in as_completed(future_to_job):
            pick_date, command = future_to_job[future]
            try:
                future.result()
            except BaseException as exc:
                failures.append((pick_date, command, exc))
                print(f"failed {pick_date}: {' '.join(command)}")
                if isinstance(exc, subprocess.CalledProcessError):
                    if exc.stdout:
                        print(f"--- stdout {pick_date} ---")
                        print(exc.stdout, end="" if exc.stdout.endswith("\n") else "\n")
                    if exc.stderr:
                        print(f"--- stderr {pick_date} ---")
                        print(exc.stderr, end="" if exc.stderr.endswith("\n") else "\n")
    if failures:
        failed_dates = ", ".join(pick_date for pick_date, _, _ in failures)
        raise RuntimeError(f"Backfill failed for {len(failures)} date(s): {failed_dates}") from failures[0][2]


def run_backfill(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    dsn = resolve_dsn(args.dsn)
    trade_dates = fetch_available_trade_dates(dsn)
    target_dates = collect_target_trade_dates(
        trade_dates,
        sample_size=args.sample_size,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    plan = plan_backfill(
        target_dates=target_dates,
        runtime_root=args.runtime_root,
        method=args.method,
        force=args.force,
    )
    print_plan(target_dates=target_dates, plan=plan)
    if args.dry_run or not plan.missing_dates:
        return 0
    run_missing_dates(
        missing_dates=plan.missing_dates,
        method=args.method,
        dsn=args.dsn,
        runtime_root=args.runtime_root,
        stock_select_bin=args.stock_select_bin,
        llm_min_baseline_score=args.llm_min_baseline_score,
        llm_review_limit=args.llm_review_limit,
        recompute=args.recompute,
        no_progress=args.no_progress,
        max_workers=args.max_workers,
    )
    return 0


def main() -> int:
    return run_backfill()


if __name__ == "__main__":
    raise SystemExit(main())
