from __future__ import annotations

from ml.methods import SUPPORTED_METHODS

import argparse
import shlex
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from ml.backfill.commands import build_screen_command
from ml.dates import fetch_trade_dates, read_dates_file, validate_date
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import PROJECT_ROOT, candidate_path, factor_artifact_path, resolve_stock_select_binary
from ml.subprocesses import format_returncode
from ml.parallelism import parse_worker_count, validate_worker_count


DEFAULT_METHOD = "b2"
DEFAULT_POOL_SOURCE = "turnover-top"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class _TimedRunError(Exception):
    def __init__(self, cause: Exception, elapsed_seconds: float) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.elapsed_seconds = elapsed_seconds


@dataclass(frozen=True)
class BackfillConfig:
    binary: Path
    runtime_root: Path
    method: str = DEFAULT_METHOD
    workers: int = 4
    recompute: bool = False
    export_factors: bool = False
    pool_source: str = DEFAULT_POOL_SOURCE
    dry_run: bool = False
    quiet: bool = True
    intraday: bool = False
    duckdb_path: str | None = None

    def __post_init__(self) -> None:
        validate_worker_count(self.workers)


@dataclass(frozen=True)
class BackfillFailure:
    pick_date: str
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class BackfillResult:
    total_count: int
    success_count: int = 0
    dry_run_count: int = 0
    failures: list[BackfillFailure] = field(default_factory=list)


def select_missing_dates(
    trade_dates: Sequence[str],
    *,
    runtime_root: Path,
    method: str,
    skip_existing: bool = True,
    require_factor_artifact: bool = False,
    intraday: bool = False,
) -> list[str]:
    dates = sorted(dict.fromkeys(validate_date(item) for item in trade_dates))
    if not skip_existing:
        return dates
    return [
        pick_date
        for pick_date in dates
        if not candidate_path(runtime_root, pick_date, method, intraday=intraday).exists()
        or (
            require_factor_artifact
            and not factor_artifact_path(runtime_root, pick_date, method, intraday=intraday).exists()
        )
    ]


def _run_one(
    pick_date: str,
    *,
    config: BackfillConfig,
    runner: Runner,
) -> tuple[str, subprocess.CompletedProcess[str]]:
    actual_date, completed, _ = _run_one_timed(pick_date, config=config, runner=runner)
    return actual_date, completed


def _run_one_timed(
    pick_date: str,
    *,
    config: BackfillConfig,
    runner: Runner,
) -> tuple[str, subprocess.CompletedProcess[str], float]:
    command = build_screen_command(
        binary=config.binary,
        pick_date=pick_date,
        runtime_root=config.runtime_root,
        method=config.method,
        recompute=config.recompute,
        pool_source=config.pool_source,
        export_factors=config.export_factors,
        intraday=config.intraday,
        duckdb_path=config.duckdb_path,
    )
    started = time.monotonic()
    try:
        completed = runner(command, cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    except Exception as exc:
        raise _TimedRunError(exc, time.monotonic() - started) from exc
    return pick_date, completed, time.monotonic() - started


def run_backfill(
    trade_dates: Sequence[str],
    *,
    config: BackfillConfig,
    runner: Runner = subprocess.run,
) -> BackfillResult:
    dates = list(trade_dates)
    result = BackfillResult(total_count=len(dates))
    if config.dry_run:
        result.dry_run_count = len(dates)
        return result
    if not dates:
        return result

    worker_count = max(1, min(config.workers, len(dates)))
    if worker_count == 1:
        for completed_count, pick_date in enumerate(dates, start=1):
            command = build_screen_command(
                binary=config.binary,
                pick_date=pick_date,
                runtime_root=config.runtime_root,
                method=config.method,
                recompute=config.recompute,
                pool_source=config.pool_source,
                export_factors=config.export_factors,
                intraday=config.intraday,
                duckdb_path=config.duckdb_path,
            )
            try:
                actual_date, completed, elapsed_seconds = _run_one_timed(
                    pick_date, config=config, runner=runner
                )
            except Exception as exc:  # pragma: no cover - defensive for subprocess launch errors
                elapsed_seconds = exc.elapsed_seconds if isinstance(exc, _TimedRunError) else 0.0
                cause = exc.cause if isinstance(exc, _TimedRunError) else exc
                result.failures.append(
                    BackfillFailure(pick_date=pick_date, command=command, returncode=1, stderr=str(cause))
                )
                if not config.quiet:
                    print(f"[{completed_count}/{len(dates)}] {pick_date} failed: {cause} elapsed={elapsed_seconds:.3f}s")
                continue
            if completed.returncode == 0:
                result.success_count += 1
                if not config.quiet:
                    print(f"[{completed_count}/{len(dates)}] {actual_date} ok elapsed={elapsed_seconds:.3f}s")
            else:
                result.failures.append(
                    BackfillFailure(
                        pick_date=actual_date,
                        command=command,
                        returncode=completed.returncode,
                        stdout=completed.stdout or "",
                        stderr=completed.stderr or "",
                    )
                )
                if not config.quiet:
                    print(
                        f"[{completed_count}/{len(dates)}] {actual_date} failed "
                        f"{format_returncode(completed.returncode)} elapsed={elapsed_seconds:.3f}s"
                    )
        return result

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        remaining = iter(dates)
        futures = {}
        completed_count = 0
        while completed_count < len(dates):
            # Leave remaining dates unscheduled so interrupting does not drain a backlog.
            for _ in range(worker_count - len(futures)):
                pick_date = next(remaining, None)
                if pick_date is None:
                    break
                futures[executor.submit(_run_one_timed, pick_date, config=config, runner=runner)] = pick_date
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            while done:
                future = done.pop()
                pick_date = futures.pop(future)
                command = build_screen_command(
                    binary=config.binary,
                    pick_date=pick_date,
                    runtime_root=config.runtime_root,
                    method=config.method,
                    recompute=config.recompute,
                    pool_source=config.pool_source,
                    export_factors=config.export_factors,
                    intraday=config.intraday,
                    duckdb_path=config.duckdb_path,
                )
                completed_count += 1
                try:
                    actual_date, completed, elapsed_seconds = future.result()
                except Exception as exc:  # pragma: no cover - defensive for subprocess launch errors
                    elapsed_seconds = exc.elapsed_seconds if isinstance(exc, _TimedRunError) else 0.0
                    cause = exc.cause if isinstance(exc, _TimedRunError) else exc
                    result.failures.append(
                        BackfillFailure(pick_date=pick_date, command=command, returncode=1, stderr=str(cause))
                    )
                    if not config.quiet:
                        print(f"[{completed_count}/{len(dates)}] {pick_date} failed: {cause} elapsed={elapsed_seconds:.3f}s")
                    continue
                if completed.returncode == 0:
                    result.success_count += 1
                    if not config.quiet:
                        print(f"[{completed_count}/{len(dates)}] {actual_date} ok elapsed={elapsed_seconds:.3f}s")
                else:
                    result.failures.append(
                        BackfillFailure(
                            pick_date=actual_date,
                            command=command,
                            returncode=completed.returncode,
                            stdout=completed.stdout or "",
                            stderr=completed.stderr or "",
                        )
                    )
                    if not config.quiet:
                        print(
                            f"[{completed_count}/{len(dates)}] {actual_date} failed "
                            f"{format_returncode(completed.returncode)} elapsed={elapsed_seconds:.3f}s"
                        )
    return result


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date", type=validate_date, required=True)
    parser.add_argument("--end-date", type=validate_date, required=True)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--duckdb-path")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--method", choices=SUPPORTED_METHODS, default=DEFAULT_METHOD)
    parser.add_argument("--workers", type=parse_worker_count, default=4, help="并发数，1～8，默认 4")
    parser.add_argument("--jobs", "-j", type=parse_worker_count, dest="workers", help="Compatibility alias for --workers.")
    parser.add_argument("--pool-source", default=DEFAULT_POOL_SOURCE)
    parser.add_argument("--dates-file", type=Path)
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--export-factors", action="store_true")
    parser.add_argument("--intraday", action="store_true")
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--force", action="store_true", dest="no_skip_existing", help="Compatibility alias for --no-skip-existing.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill candidate artifacts with concurrent screen runs.")
    add_arguments(parser)
    return parser.parse_args(argv)


def _resolve_trade_dates(
    args: argparse.Namespace, dotenv_values: dict[str, str], *, binary: Path | None = None
) -> list[str]:
    if args.dates_file:
        return read_dates_file(args.dates_file)
    duckdb_path = resolve_config_value(args.duckdb_path, "DUCKDB_PATH", dotenv_values)
    if not duckdb_path:
        raise SystemExit("DUCKDB_PATH is required; set it in .env, export it, or pass --duckdb-path.")
    return fetch_trade_dates(duckdb_path, args.start_date, args.end_date, binary=binary or getattr(args, "binary", None))


def main_from_args(args: argparse.Namespace) -> int:
    dotenv_values = load_dotenv_values()
    runtime_root_value = resolve_config_value(
        str(args.runtime_root) if args.runtime_root else None,
        "STOCK_SELECT_RUNTIME_ROOT",
        dotenv_values,
    )
    if not runtime_root_value:
        raise SystemExit("STOCK_SELECT_RUNTIME_ROOT is required; set it in .env or pass --runtime-root.")
    runtime_root = Path(runtime_root_value).expanduser()

    binary = resolve_stock_select_binary(args.binary, resolve_config_value(None, "STOCK_SELECT_BIN", dotenv_values))
    trade_dates = _resolve_trade_dates(args, dotenv_values, binary=binary)
    selected_dates = select_missing_dates(
        trade_dates,
        runtime_root=runtime_root,
        method=args.method,
        skip_existing=not args.no_skip_existing,
        require_factor_artifact=args.export_factors,
        intraday=args.intraday,
    )
    skipped_count = len(trade_dates) - len(selected_dates)
    print(
        "backfill candidates: "
        f"trade_dates={len(trade_dates)} selected={len(selected_dates)} skipped_existing={skipped_count}"
    )

    config = BackfillConfig(
        binary=binary,
        runtime_root=runtime_root,
        method=args.method,
        workers=args.workers,
        recompute=args.recompute,
        export_factors=args.export_factors,
        pool_source=args.pool_source,
        dry_run=args.dry_run,
        quiet=args.quiet,
        intraday=args.intraday,
        duckdb_path=args.duckdb_path,
    )
    if args.dry_run:
        for pick_date in selected_dates:
            command = build_screen_command(
                binary=config.binary,
                pick_date=pick_date,
                runtime_root=config.runtime_root,
                method=config.method,
                recompute=config.recompute,
                pool_source=config.pool_source,
                export_factors=config.export_factors,
                intraday=config.intraday,
                duckdb_path=config.duckdb_path,
            )
            print(shlex.join(command))
    try:
        result = run_backfill(selected_dates, config=config)
    except KeyboardInterrupt:
        print("backfill interrupted; cancel pending work and rerun remaining dates.")
        return 130
    print(
        "backfill summary: "
        f"success={result.success_count} dry_run={result.dry_run_count} failed={len(result.failures)}"
    )
    if result.failures:
        print("failed dates:")
        for failure in result.failures:
            message = (failure.stderr or failure.stdout or "").strip().splitlines()
            suffix = f" {message[-1]}" if message else ""
            print(f"- {failure.pick_date} {format_returncode(failure.returncode)}{suffix}")
        return 1
    return 0


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("candidates", description="Backfill candidate artifacts with concurrent screen runs.")
    add_arguments(parser)
    parser.set_defaults(handler=main_from_args)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return main_from_args(parse_args(argv))
