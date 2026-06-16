# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "psycopg[binary]",
# ]
# ///
from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOTENV_PATH = PROJECT_ROOT / ".env"
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


def load_dotenv_values(env_path: Path = DOTENV_PATH) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def resolve_config_value(cli_value: str | None, key: str, dotenv_values: dict[str, str]) -> str | None:
    for value in (cli_value, os.getenv(key), dotenv_values.get(key)):
        if value and value.strip():
            return value.strip()
    return None


def validate_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def fetch_trade_dates(dsn: str, start_date: str, end_date: str) -> list[str]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select distinct trade_date
                from daily_market
                where trade_date between %s and %s
                order by trade_date
                """,
                (start_date, end_date),
            )
            return [row[0].isoformat() for row in cur.fetchall()]


def read_dates_file(path: Path) -> list[str]:
    dates: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        dates.append(validate_date(value))
    return sorted(dict.fromkeys(dates))


def candidate_path(runtime_root: Path, pick_date: str, method: str) -> Path:
    return runtime_root / "candidates" / f"{pick_date}.{method}.json"


def factor_artifact_path(runtime_root: Path, pick_date: str, method: str) -> Path:
    return runtime_root / "factors" / f"{pick_date}.{method}" / "factors.json"


def format_returncode(returncode: int) -> str:
    if returncode >= 0:
        return f"rc={returncode}"
    signum = -returncode
    try:
        signal_name = signal.Signals(signum).name
    except ValueError:
        signal_name = str(signum)
    return f"signal={signal_name}"


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


def build_screen_command(
    *,
    binary: Path,
    pick_date: str,
    runtime_root: Path,
    method: str,
    recompute: bool,
    pool_source: str,
    export_factors: bool,
) -> list[str]:
    command = [
        str(binary),
        "screen",
        "--method",
        method,
        "--pick-date",
        pick_date,
        "--runtime-root",
        str(runtime_root),
        "--pool-source",
        pool_source,
    ]
    if recompute:
        command.append("--recompute")
    if export_factors:
        command.append("--export-factors")
    return command


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
    completed = runner(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
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
                    BackfillFailure(
                        pick_date=pick_date,
                        command=command,
                        returncode=1,
                        stderr=str(exc),
                    )
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill candidate artifacts with concurrent screen runs.")
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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    dotenv_values = load_dotenv_values()
    runtime_root_value = resolve_config_value(
        str(args.runtime_root) if args.runtime_root else None,
        "STOCK_SELECT_RUNTIME_ROOT",
        dotenv_values,
    )
    if not runtime_root_value:
        raise SystemExit("STOCK_SELECT_RUNTIME_ROOT is required; set it in .env or pass --runtime-root.")
    runtime_root = Path(runtime_root_value).expanduser()

    if args.dates_file:
        trade_dates = read_dates_file(args.dates_file)
    else:
        dsn = resolve_config_value(args.dsn, "POSTGRES_DSN", dotenv_values)
        if not dsn:
            raise SystemExit("POSTGRES_DSN is required; set it in .env, export it, or pass --dsn.")
        trade_dates = fetch_trade_dates(dsn, args.start_date, args.end_date)

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


if __name__ == "__main__":
    raise SystemExit(main())
