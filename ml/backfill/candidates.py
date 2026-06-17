from __future__ import annotations

import argparse
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from ml.backfill.commands import build_screen_command
from ml.dates import fetch_trade_dates, read_dates_file, validate_date
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import PROJECT_ROOT, candidate_path, factor_artifact_path
from ml.subprocesses import format_returncode


DEFAULT_BINARY = PROJECT_ROOT / "target" / "debug" / "stock-select-rs"
DEFAULT_METHOD = "b2"
DEFAULT_POOL_SOURCE = "turnover-top"

Runner = Callable[..., subprocess.CompletedProcess[str]]


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
) -> list[str]:
    dates = sorted(dict.fromkeys(validate_date(item) for item in trade_dates))
    if not skip_existing:
        return dates
    return [
        pick_date
        for pick_date in dates
        if not candidate_path(runtime_root, pick_date, method).exists()
        or (require_factor_artifact and not factor_artifact_path(runtime_root, pick_date, method).exists())
    ]


def _run_one(
    pick_date: str,
    *,
    config: BackfillConfig,
    runner: Runner,
) -> tuple[str, subprocess.CompletedProcess[str]]:
    command = build_screen_command(
        binary=config.binary,
        pick_date=pick_date,
        runtime_root=config.runtime_root,
        method=config.method,
        recompute=config.recompute,
        pool_source=config.pool_source,
        export_factors=config.export_factors,
    )
    completed = runner(command, cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return pick_date, completed


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
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_run_one, pick_date, config=config, runner=runner): pick_date
            for pick_date in dates
        }
        completed_count = 0
        for future in as_completed(futures):
            pick_date = futures[future]
            command = build_screen_command(
                binary=config.binary,
                pick_date=pick_date,
                runtime_root=config.runtime_root,
                method=config.method,
                recompute=config.recompute,
                pool_source=config.pool_source,
                export_factors=config.export_factors,
            )
            completed_count += 1
            try:
                actual_date, completed = future.result()
            except Exception as exc:  # pragma: no cover - defensive for subprocess launch errors
                result.failures.append(
                    BackfillFailure(pick_date=pick_date, command=command, returncode=1, stderr=str(exc))
                )
                if not config.quiet:
                    print(f"[{completed_count}/{len(dates)}] {pick_date} failed: {exc}")
                continue
            if completed.returncode == 0:
                result.success_count += 1
                if not config.quiet:
                    print(f"[{completed_count}/{len(dates)}] {actual_date} ok")
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
                    print(f"[{completed_count}/{len(dates)}] {actual_date} failed {format_returncode(completed.returncode)}")
    return result


def resolve_binary(cli_binary: Path | None) -> Path:
    if cli_binary is not None:
        return cli_binary
    if DEFAULT_BINARY.exists():
        return DEFAULT_BINARY
    return Path("stock-select-rs")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date", type=validate_date, required=True)
    parser.add_argument("--end-date", type=validate_date, required=True)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--dsn")
    parser.add_argument("--postgres-dsn", dest="dsn", help="Compatibility alias for --dsn.")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--jobs", "-j", type=int, dest="workers", help="Compatibility alias for --workers.")
    parser.add_argument("--pool-source", default=DEFAULT_POOL_SOURCE)
    parser.add_argument("--dates-file", type=Path)
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--export-factors", action="store_true")
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--force", action="store_true", dest="no_skip_existing", help="Compatibility alias for --no-skip-existing.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill candidate artifacts with concurrent screen runs.")
    add_arguments(parser)
    return parser.parse_args(argv)


def _resolve_trade_dates(args: argparse.Namespace, dotenv_values: dict[str, str]) -> list[str]:
    if args.dates_file:
        return read_dates_file(args.dates_file)
    dsn = resolve_config_value(args.dsn, "POSTGRES_DSN", dotenv_values)
    if not dsn:
        raise SystemExit("POSTGRES_DSN is required; set it in .env, export it, or pass --dsn.")
    return fetch_trade_dates(dsn, args.start_date, args.end_date)


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

    trade_dates = _resolve_trade_dates(args, dotenv_values)
    selected_dates = select_missing_dates(
        trade_dates,
        runtime_root=runtime_root,
        method=args.method,
        skip_existing=not args.no_skip_existing,
        require_factor_artifact=args.export_factors,
    )
    skipped_count = len(trade_dates) - len(selected_dates)
    print(
        "backfill candidates: "
        f"trade_dates={len(trade_dates)} selected={len(selected_dates)} skipped_existing={skipped_count}"
    )

    config = BackfillConfig(
        binary=resolve_binary(args.binary),
        runtime_root=runtime_root,
        method=args.method,
        workers=args.workers,
        recompute=args.recompute,
        export_factors=args.export_factors,
        pool_source=args.pool_source,
        dry_run=args.dry_run,
        quiet=args.quiet,
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
