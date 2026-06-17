from __future__ import annotations

import argparse
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Sequence

from ml.backfill.commands import build_run_command
from ml.dates import fetch_trade_dates, read_dates_file, weekday_fallback
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import PROJECT_ROOT, select_dir
from ml.subprocesses import format_returncode


DEFAULT_BINARY = PROJECT_ROOT / "target" / "debug" / "stock-select-rs"
DEFAULT_METHOD = "b2"
DEFAULT_POOL_SOURCE = "turnover-top"


@dataclass(frozen=True)
class RunConfig:
    binary: Path
    runtime_root: Path
    method: str
    workers: int
    skip_existing: bool
    dry_run: bool
    recompute: bool
    pool_source: str


@dataclass
class RunFailure:
    pick_date: str
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class RunResult:
    total: int = 0
    skipped: int = 0
    success: int = 0
    failed: int = 0
    failures: list[RunFailure] = field(default_factory=list)


def build_dates(
    start_date: date,
    end_date: date,
    dsn: str | None,
    runtime_root: Path,
    method: str,
    skip_existing: bool,
) -> tuple[list[str], int]:
    start_s = start_date.isoformat()
    end_s = end_date.isoformat()
    trade_dates: list[str] | None = None
    if dsn:
        try:
            trade_dates = fetch_trade_dates(dsn, start_s, end_s)
            print(f"  交易日历: 从 DB 查询到 {len(trade_dates)} 个交易日")
        except Exception:
            trade_dates = None
    if trade_dates is None:
        trade_dates = weekday_fallback(start_s, end_s)
        print(f"  交易日历: 兜底跳过周末，共 {len(trade_dates)} 天")

    selected: list[str] = []
    skipped = 0
    for day in trade_dates:
        if skip_existing and select_dir(runtime_root, day, method).exists():
            print(f"  跳过 (已存在): {day}")
            skipped += 1
        else:
            selected.append(day)
    return selected, skipped


def command_for_date(date_str: str, config: RunConfig) -> list[str]:
    return build_run_command(
        binary=config.binary,
        pick_date=date_str,
        runtime_root=config.runtime_root,
        method=config.method,
        recompute=config.recompute,
        pool_source=config.pool_source,
    )


def run_single_result(date_str: str, config: RunConfig, *, print_output: bool = False) -> tuple[str, subprocess.CompletedProcess[str]]:
    command = command_for_date(date_str, config)
    proc = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if print_output:
        for line in (proc.stdout or "").splitlines():
            if line.strip():
                print(f"  [{date_str}] {line.rstrip()}")
        if proc.stderr and proc.returncode != 0:
            for line in proc.stderr.strip().splitlines()[-3:]:
                print(f"  [{date_str}] {line.rstrip()}")
    return date_str, proc


def failure_from_completed(date_str: str, config: RunConfig, proc: subprocess.CompletedProcess[str]) -> RunFailure:
    command = list(proc.args) if isinstance(proc.args, list) else command_for_date(date_str, config)
    return RunFailure(
        pick_date=date_str,
        command=command,
        returncode=int(proc.returncode),
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )


def failure_from_exception(date_str: str, config: RunConfig, exc: BaseException) -> RunFailure:
    return RunFailure(
        pick_date=date_str,
        command=command_for_date(date_str, config),
        returncode=1,
        stderr=str(exc),
    )


def run_single(date_str: str, config: RunConfig) -> bool:
    try:
        _date, proc = run_single_result(date_str, config)
    except FileNotFoundError:
        print(f"  ✗ [{date_str}] 找不到二进制: {config.binary}")
        return False
    if proc.returncode == 0:
        print(f"  ✓ [{date_str}] 完成")
        return True
    print(f"  ✗ [{date_str}] 失败 ({format_returncode(proc.returncode)})")
    return False


def run_single_quiet(date_str: str, config: RunConfig) -> tuple[str, bool]:
    try:
        _date, proc = run_single_result(date_str, config, print_output=True)
    except FileNotFoundError:
        print(f"  ✗ [{date_str}] 找不到二进制: {config.binary}")
        return date_str, False
    ok = proc.returncode == 0
    for line in (proc.stdout or "").splitlines():
        if line.strip():
            print(f"  [{date_str}] {line.rstrip()}")
    if proc.stderr and not ok:
        for line in proc.stderr.strip().splitlines()[-3:]:
            print(f"  [{date_str}] {line.rstrip()}")
    if ok:
        print(f"  ✓ [{date_str}] 完成")
    else:
        print(f"  ✗ [{date_str}] 失败 ({format_returncode(proc.returncode)})")
    return date_str, ok


def run_dates(dates: Sequence[str], config: RunConfig, *, skipped: int = 0) -> RunResult:
    result = RunResult(total=len(dates), skipped=skipped)
    if config.workers <= 1:
        for day in dates:
            print(f"━━━ [{day}] 开始 ━━━")
            try:
                actual_day, proc = run_single_result(day, config, print_output=True)
            except FileNotFoundError as exc:
                print(f"  ✗ [{day}] 找不到二进制: {config.binary}")
                result.failed += 1
                result.failures.append(failure_from_exception(day, config, exc))
                print()
                continue
            if proc.returncode == 0:
                print(f"  ✓ [{actual_day}] 完成")
                result.success += 1
            else:
                print(f"  ✗ [{actual_day}] 失败 ({format_returncode(proc.returncode)})")
                result.failed += 1
                result.failures.append(failure_from_completed(actual_day, config, proc))
            print()
        return result

    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        futures = {pool.submit(run_single_result, day, config, print_output=True): day for day in dates}
        for future in as_completed(futures):
            day = futures[future]
            try:
                actual_day, proc = future.result()
            except FileNotFoundError as exc:
                print(f"  ✗ [{day}] 找不到二进制: {config.binary}")
                result.failed += 1
                result.failures.append(failure_from_exception(day, config, exc))
                continue
            except Exception as exc:
                print(f"  ✗ [{day}] 失败 ({exc})")
                result.failed += 1
                result.failures.append(failure_from_exception(day, config, exc))
                continue
            if proc.returncode == 0:
                print(f"  ✓ [{actual_day}] 完成")
                result.success += 1
            else:
                print(f"  ✗ [{actual_day}] 失败 ({format_returncode(proc.returncode)})")
                result.failed += 1
                result.failures.append(failure_from_completed(actual_day, config, proc))
    return result


def output_tail(value: str, *, max_lines: int = 3) -> str:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return " | ".join(lines[-max_lines:])


def print_failure_summary(failures: Sequence[RunFailure]) -> None:
    if not failures:
        return
    print("failed dates:")
    for failure in failures:
        print(f"- {failure.pick_date} returncode={failure.returncode} ({format_returncode(failure.returncode)})")
        stderr_tail = output_tail(failure.stderr)
        stdout_tail = output_tail(failure.stdout)
        if stderr_tail:
            print(f"  stderr: {stderr_tail}")
        if stdout_tail:
            print(f"  stdout: {stdout_tail}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date", required=True, type=date.fromisoformat, help="起始日期 (含)")
    parser.add_argument("--end-date", required=True, type=date.fromisoformat, help="截止日期 (含)")
    parser.add_argument("--method", default=None, help="筛选方法，默认 b2")
    parser.add_argument("--binary", type=Path, default=None, help="二进制路径")
    parser.add_argument("--force", action="store_true", dest="no_skip_existing", help="兼容旧参数；等同 --no-skip-existing")
    parser.add_argument("--no-skip-existing", action="store_true", help="覆盖已存在的 run artifact")
    parser.add_argument("--dry-run", action="store_true", help="只打印要执行的命令")
    parser.add_argument("--workers", type=int, default=4, help="并发数，默认 4（设为 1 则串行）")
    parser.add_argument("--jobs", "-j", type=int, dest="workers", help="兼容旧参数；等同 --workers")
    parser.add_argument("--runtime-root", type=Path, default=None, help="runtime 根目录")
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN（用于查交易日历）")
    parser.add_argument("--postgres-dsn", dest="dsn", help="兼容旧参数；等同 --dsn")
    parser.add_argument("--dates-file", type=Path)
    parser.add_argument("--pool-source", default=DEFAULT_POOL_SOURCE, help="传给 run 自动筛选的股票池来源")
    parser.add_argument("--recompute", action="store_true", help="传给 run 自动筛选，强制重算 prepared cache")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="补跑历史 run 数据")
    add_arguments(parser)
    return parser.parse_args(argv)


def _resolve_config(args: argparse.Namespace) -> tuple[RunConfig, str | None]:
    dotenv = load_dotenv_values()
    method = args.method or resolve_config_value(None, "STOCK_SELECT_METHOD", dotenv) or DEFAULT_METHOD
    binary_value = args.binary or Path(resolve_config_value(None, "STOCK_SELECT_BIN", dotenv) or str(DEFAULT_BINARY))
    runtime_value = resolve_config_value(
        str(args.runtime_root) if args.runtime_root else None,
        "STOCK_SELECT_RUNTIME_ROOT",
        dotenv,
    ) or "runtime"
    dsn = resolve_config_value(args.dsn, "POSTGRES_DSN", dotenv)
    config = RunConfig(
        binary=Path(binary_value),
        runtime_root=Path(runtime_value),
        method=method,
        workers=args.workers,
        skip_existing=not args.no_skip_existing,
        dry_run=args.dry_run,
        recompute=args.recompute,
        pool_source=args.pool_source,
    )
    return config, dsn


def main_from_args(args: argparse.Namespace) -> int:
    config, dsn = _resolve_config(args)
    print("配置:")
    print(f"  二进制:        {config.binary}")
    print(f"  方法:          {config.method}")
    print(f"  日期区间:      {args.start_date}  ~  {args.end_date}")
    print(f"  runtime 根目录: {config.runtime_root}")
    print(f"  跳过已存在:    {config.skip_existing}")
    print(f"  并发数:        {config.workers}")
    print(f"  DRY-RUN:       {config.dry_run}")
    print(f"  PostgreSQL:    {'已配置' if dsn else '未配置（跳过周末兜底）'}")
    print()

    if args.dates_file:
        dates = read_dates_file(args.dates_file)
        skipped = 0
    else:
        dates, skipped = build_dates(
            start_date=args.start_date,
            end_date=args.end_date,
            dsn=dsn,
            runtime_root=config.runtime_root,
            method=config.method,
            skip_existing=config.skip_existing,
        )
    if not dates:
        print("没有需要补跑的日期。")
        return 0

    print(f"\n待处理日期 ({len(dates)} 天):")
    for day in dates:
        print(f"  - {day}")
    print()

    if config.dry_run:
        print("━━━ DRY RUN ━━━")
        for day in dates:
            command = command_for_date(day, config)
            print(f"  {shlex.join(command)}")
        print(f"总计 {len(dates)} 天")
        return 0

    print(f"━━━ 开始补跑 (并发={config.workers}) ━━━")
    try:
        result = run_dates(dates, config, skipped=skipped)
    except KeyboardInterrupt:
        print("backfill runs interrupted; rerun remaining dates.")
        return 130
    print()
    print("═" * 45)
    print("  汇总")
    print("─" * 45)
    print(f"  区间:           {args.start_date} ~ {args.end_date}")
    print(f"  总处理:         {result.total}")
    if result.skipped:
        print(f"  跳过(已存在):   {result.skipped}")
    print(f"  成功:           {result.success}")
    print(f"  失败:           {result.failed}")
    print_failure_summary(result.failures)
    print("═" * 45)
    return 1 if result.failed > 0 else 0


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("runs", description="补跑历史 run 数据")
    add_arguments(parser)
    parser.set_defaults(handler=main_from_args)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return main_from_args(parse_args(argv))
