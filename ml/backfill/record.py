from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Sequence

from ml.dates import fetch_trade_dates, read_dates_file, validate_date, weekday_fallback
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import PROJECT_ROOT
from ml.subprocesses import format_returncode


DEFAULT_BINARY = PROJECT_ROOT / "target" / "debug" / "stock-select-rs"
DEFAULT_RUNTIME_ROOT = Path("runtime")
DEFAULT_DAYS = 10

Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RecordBackfillConfig:
    binary: Path
    runtime_root: Path
    methods: tuple[str, ...]
    workers: int
    dry_run: bool
    record_window_trading_days: int | None


@dataclass(frozen=True)
class RecordTask:
    pick_date: str
    method: str


@dataclass(frozen=True)
class RecordFailure:
    task: RecordTask
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class RecordBackfillResult:
    total: int
    success: int = 0
    dry_run: int = 0
    failures: list[RecordFailure] = field(default_factory=list)


def parse_methods(value: str | None) -> list[str]:
    if value is None:
        return []
    methods: list[str] = []
    seen: set[str] = set()
    for item in value.replace(",", " ").replace(";", " ").split():
        method = item.strip().lower()
        if not method or method in seen:
            continue
        methods.append(method)
        seen.add(method)
    return methods


def resolve_record_methods(
    cli_value: str | None,
    dotenv_values: dict[str, str],
    *,
    env: dict[str, str] | None = None,
) -> list[str]:
    source = os.environ if env is None else env
    if cli_value is not None:
        return parse_methods(cli_value)
    if "STOCK_SELECT_RECORD_METHODS" in source:
        return parse_methods(source["STOCK_SELECT_RECORD_METHODS"])
    return parse_methods(dotenv_values.get("STOCK_SELECT_RECORD_METHODS"))


def build_dates(trade_dates: Sequence[str], days: int) -> list[str]:
    if days <= 0:
        raise ValueError("days must be positive")
    return list(trade_dates)[-days:]


def recent_trade_dates(*, days: int, dsn: str | None, end_date: date) -> list[str]:
    start_date = end_date - timedelta(days=max(days * 3, 21))
    start_s = start_date.isoformat()
    end_s = end_date.isoformat()
    if dsn:
        dates = fetch_trade_dates(dsn, start_s, end_s)
    else:
        dates = weekday_fallback(start_s, end_s)
    return build_dates(dates, days)


def parse_inline_dates(value: str) -> list[str]:
    dates: list[str] = []
    for item in value.replace(",", " ").split():
        dates.append(validate_date(item.strip()))
    return sorted(dict.fromkeys(dates))


def build_record_run_command(
    *,
    binary: Path,
    runtime_root: Path,
    method: str,
    pick_date: str,
    record_window_trading_days: int | None,
) -> list[str]:
    command = [
        str(binary),
        "run",
        "--method",
        method,
        "--pick-date",
        pick_date,
        "--runtime-root",
        str(runtime_root),
        "--record",
    ]
    if record_window_trading_days is not None:
        command.extend(["--record-window-trading-days", str(record_window_trading_days)])
    return command


def build_run_command(
    *,
    binary: Path,
    runtime_root: Path,
    method: str,
    pick_date: str,
    record_window_trading_days: int | None,
) -> list[str]:
    return build_record_run_command(
        binary=binary,
        runtime_root=runtime_root,
        method=method,
        pick_date=pick_date,
        record_window_trading_days=record_window_trading_days,
    )


def build_tasks(methods: Sequence[str], dates: Sequence[str]) -> list[RecordTask]:
    return [
        RecordTask(pick_date=pick_date, method=method)
        for pick_date in dates
        for method in methods
    ]


def command_for_task(task: RecordTask, config: RecordBackfillConfig) -> list[str]:
    return build_record_run_command(
        binary=config.binary,
        runtime_root=config.runtime_root,
        method=task.method,
        pick_date=task.pick_date,
        record_window_trading_days=config.record_window_trading_days,
    )


def _run_one(
    task: RecordTask,
    *,
    config: RecordBackfillConfig,
    runner: Runner,
) -> tuple[RecordTask, subprocess.CompletedProcess[str]]:
    command = command_for_task(task, config)
    proc = runner(command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    return task, proc


def run_record_backfill(
    tasks: Sequence[RecordTask],
    *,
    config: RecordBackfillConfig,
    runner: Runner = subprocess.run,
) -> RecordBackfillResult:
    result = RecordBackfillResult(total=len(tasks))
    if config.dry_run:
        result.dry_run = len(tasks)
        return result
    if not tasks:
        return result

    worker_count = max(1, min(config.workers, len(tasks)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_run_one, task, config=config, runner=runner): task
            for task in tasks
        }
        for future in as_completed(futures):
            task = futures[future]
            command = command_for_task(task, config)
            try:
                actual_task, proc = future.result()
            except Exception as exc:  # pragma: no cover - defensive for subprocess launch errors
                result.failures.append(
                    RecordFailure(task=task, command=command, returncode=1, stderr=str(exc))
                )
                print(f"  ✗ [{task.pick_date} {task.method}] 失败 ({exc})")
                continue
            if proc.returncode == 0:
                result.success += 1
                print(f"  ✓ [{actual_task.pick_date} {actual_task.method}] 完成")
            else:
                result.failures.append(
                    RecordFailure(
                        task=actual_task,
                        command=command,
                        returncode=proc.returncode,
                        stdout=proc.stdout or "",
                        stderr=proc.stderr or "",
                    )
                )
                print(
                    f"  ✗ [{actual_task.pick_date} {actual_task.method}] "
                    f"失败 ({format_returncode(proc.returncode)})"
                )
    return result


def run_for_methods_and_dates(
    *,
    methods: Sequence[str],
    dates: Sequence[str],
    binary: Path,
    runtime_root: Path,
    record_window_trading_days: int | None,
    runner: Runner = subprocess.run,
) -> int:
    config = RecordBackfillConfig(
        binary=binary,
        runtime_root=runtime_root,
        methods=tuple(methods),
        workers=1,
        dry_run=False,
        record_window_trading_days=record_window_trading_days,
    )
    result = run_record_backfill(build_tasks(methods, dates), config=config, runner=runner)
    return 1 if result.failures else 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--methods",
        default=None,
        help="要补 record 的筛选方法；默认读取 STOCK_SELECT_RECORD_METHODS",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="未显式给日期时保留最近交易日数量，默认 10",
    )
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="最近交易日截止日期，默认今天",
    )
    parser.add_argument("--dates", default=None, help="逗号或空格分隔的交易日列表；优先于 --days/--end-date")
    parser.add_argument("--dates-file", type=Path, help="交易日文件；优先于 --days/--end-date")
    parser.add_argument("--runtime-root", type=Path, default=None, help="runtime 根目录")
    parser.add_argument("--binary", type=Path, default=None, help="stock-select-rs 二进制路径")
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN，用于读取交易日历")
    parser.add_argument("--postgres-dsn", dest="dsn", help="兼容旧参数；等同 --dsn")
    parser.add_argument("--workers", type=int, default=4, help="并发数，默认 4（设为 1 则串行）")
    parser.add_argument("--jobs", "-j", type=int, dest="workers", help="兼容旧参数；等同 --workers")
    parser.add_argument("--dry-run", action="store_true", help="只打印要执行的命令")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="补最近交易日的 runtime/record.csv")
    add_arguments(parser)
    return parser.parse_args(argv)


def _resolve_dates(args: argparse.Namespace, dsn: str | None) -> list[str]:
    if args.dates_file:
        return read_dates_file(args.dates_file)
    if args.dates:
        return parse_inline_dates(args.dates)
    return recent_trade_dates(days=args.days, dsn=dsn, end_date=args.end_date)


def _resolve_record_window(dotenv_values: dict[str, str]) -> int | None:
    value = resolve_config_value(None, "STOCK_SELECT_RECORD_WINDOW_TRADING_DAYS", dotenv_values)
    if not value:
        return None
    parsed = int(value)
    if parsed <= 0:
        raise SystemExit("STOCK_SELECT_RECORD_WINDOW_TRADING_DAYS must be a positive integer.")
    return parsed


def main_from_args(args: argparse.Namespace) -> int:
    dotenv_values = load_dotenv_values()
    methods = resolve_record_methods(args.methods, dotenv_values)
    if not methods:
        print("未配置 STOCK_SELECT_RECORD_METHODS，无法确定需要补 record 的方法。")
        return 2

    runtime_root = Path(
        resolve_config_value(
            str(args.runtime_root) if args.runtime_root else None,
            "STOCK_SELECT_RUNTIME_ROOT",
            dotenv_values,
        )
        or str(DEFAULT_RUNTIME_ROOT)
    )
    binary = Path(
        resolve_config_value(
            str(args.binary) if args.binary else None,
            "STOCK_SELECT_BIN",
            dotenv_values,
        )
        or str(DEFAULT_BINARY)
    )
    dsn = resolve_config_value(args.dsn, "POSTGRES_DSN", dotenv_values)
    record_window_trading_days = _resolve_record_window(dotenv_values)
    dates = _resolve_dates(args, dsn)
    tasks = build_tasks(methods, dates)
    config = RecordBackfillConfig(
        binary=binary,
        runtime_root=runtime_root,
        methods=tuple(methods),
        workers=args.workers,
        dry_run=args.dry_run,
        record_window_trading_days=record_window_trading_days,
    )

    print("配置:")
    print(f"  二进制:        {config.binary}")
    print(f"  方法:          {', '.join(config.methods)}")
    print(f"  日期:          {', '.join(dates)}")
    print(f"  runtime 根目录: {config.runtime_root}")
    print(
        "  record 窗口:   "
        f"{record_window_trading_days if record_window_trading_days is not None else 'Rust 默认值'}"
    )
    print(f"  并发数:        {config.workers}")
    print(f"  DRY-RUN:       {config.dry_run}")
    print(f"  PostgreSQL:    {'已配置' if dsn else '未配置（跳过周末兜底）'}")
    print()

    if not tasks:
        print("没有需要补 record 的日期/方法。")
        return 0

    if config.dry_run:
        print("━━━ DRY RUN ━━━")
        for task in tasks:
            print(f"  {shlex.join(command_for_task(task, config))}")
        print(f"总计 {len(tasks)} 次 run")
        return 0

    print(f"━━━ 开始补 record (并发={config.workers}) ━━━")
    try:
        result = run_record_backfill(tasks, config=config)
    except KeyboardInterrupt:
        print("backfill records interrupted; rerun remaining dates.")
        return 130
    print()
    print("═" * 45)
    print("  汇总")
    print("─" * 45)
    print(f"  总处理:         {result.total}")
    print(f"  成功:           {result.success}")
    print(f"  失败:           {len(result.failures)}")
    if result.failures:
        print("failed tasks:")
        for failure in result.failures:
            message = (failure.stderr or failure.stdout or "").strip().splitlines()
            suffix = f" {message[-1]}" if message else ""
            print(
                f"- {failure.task.pick_date} {failure.task.method} "
                f"{format_returncode(failure.returncode)}{suffix}"
            )
    print("═" * 45)
    return 1 if result.failures else 0


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("records", description="补最近交易日的 runtime/record.csv")
    add_arguments(parser)
    parser.set_defaults(handler=main_from_args)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return main_from_args(parse_args(argv))
