#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "psycopg[binary]",
# ]
# ///
"""
backfill_run.py — 并发补跑历史 run 数据

对日期区间内的每个交易日执行:
    stock-select-rs run --method <method> --pick-date <YYYY-MM-DD>

用法:
    scripts/backfill_run.py --start-date 2026-01-01 --end-date 2026-06-04
    scripts/backfill_run.py --start-date 2026-05-01 --end-date 2026-05-31 --force
    scripts/backfill_run.py --start-date 2026-03-01 --end-date 2026-06-04 --jobs 4
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_BINARY = PROJECT_ROOT / "target" / "debug" / "stock-select-rs"
DEFAULT_METHOD = "b2"


# ── 工具函数 ────────────────────────────────────────────────────────────────

def load_dotenv(path: Path = DOTENV_PATH) -> dict[str, str]:
    """简易 .env 加载（仅解析 KEY=VALUE）。"""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip("\"'")
    return values


def resolve_env(key: str, fallback: str | None = None, dotenv: dict[str, str] | None = None) -> str | None:
    """CLI 参数 > shell 环境变量 > .env > fallback。"""
    val = os.environ.get(key)
    if val is not None:
        return val
    if dotenv is not None and key in dotenv:
        return dotenv[key]
    return fallback


# ── 交易日历 ────────────────────────────────────────────────────────────────

def fetch_trade_dates(dsn: str, start_date: str, end_date: str) -> list[str] | None:
    """从 PostgreSQL 查实际交易日，失败返回 None。"""
    try:
        import psycopg
    except ImportError:
        return None

    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT trade_date FROM daily_market "
                    "WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date",
                    (start_date, end_date),
                )
                return [row[0].isoformat() for row in cur.fetchall()]
    except Exception:
        return None


def weekday_fallback(start_date: date, end_date: date) -> list[date]:
    """兜底：只跳过周末，不考虑节假日。"""
    dates: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


# ── schema ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RunConfig:
    binary: Path
    runtime_root: Path
    method: str
    workers: int
    skip_existing: bool
    dry_run: bool


@dataclass
class RunResult:
    total: int = 0
    skipped: int = 0
    success: int = 0
    failed: int = 0


# ── 核心逻辑 ─────────────────────────────────────────────────────────────────

def select_dir(runtime_root: Path, pick_date: str, method: str) -> Path:
    return runtime_root / "select" / f"{pick_date}.{method}"


def build_dates(start_date: date, end_date: date, dsn: str | None, runtime_root: Path, method: str, skip_existing: bool) -> tuple[list[str], int]:
    """确定待处理的日期列表，返回 (dates_iso, skipped_count)。"""
    start_s = start_date.isoformat()
    end_s = end_date.isoformat()

    # 取交易日
    trade_dates: list[str] | None = None
    if dsn:
        trade_dates = fetch_trade_dates(dsn, start_s, end_s)
        if trade_dates is not None:
            print(f"  交易日历: 从 DB 查询到 {len(trade_dates)} 个交易日")
    if trade_dates is None:
        trade_dates = [d.isoformat() for d in weekday_fallback(start_date, end_date)]
        print(f"  交易日历: 兜底跳过周末，共 {len(trade_dates)} 天")

    selected: list[str] = []
    skipped = 0
    for ds in trade_dates:
        if skip_existing and select_dir(runtime_root, ds, method).exists():
            print(f"  跳过 (已存在): {ds}")
            skipped += 1
        else:
            selected.append(ds)
    return selected, skipped


def run_single(date_str: str, config: RunConfig) -> bool:
    """执行一次 run，返回 True=成功。"""
    cmd = [str(config.binary), "run", "--method", config.method, "--pick-date", date_str]
    prefix = f"[{date_str}]"

    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=False,
            text=True,
        )
        if proc.returncode == 0:
            print(f"  ✓ [{date_str}] 完成")
            return True
        else:
            print(f"  ✗ [{date_str}] 失败 (exit={proc.returncode})")
            # 打印最后几行 stderr 帮助排查
            if proc.stderr:
                last = "\n".join(proc.stderr.strip().splitlines()[-5:])
                for line in last.splitlines():
                    print(f"    {date_str} | {line}")
            return False
    except FileNotFoundError:
        print(f"  ✗ [{date_str}] 找不到二进制: {config.binary}")
        return False


def run_single_quiet(date_str: str, config: RunConfig) -> tuple[str, bool]:
    """给并发用的静默执行，返回 (date_str, success)。"""
    cmd = [str(config.binary), "run", "--method", config.method, "--pick-date", date_str]

    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        # 打印输出（带日期前缀防混淆）
        for line in (proc.stdout or "").splitlines():
            if line.strip():
                print(f"  [{date_str}] {line.rstrip()}")
        if proc.stderr and not ok:
            for line in proc.stderr.strip().splitlines()[-3:]:
                print(f"  [{date_str}] {line.rstrip()}")
        if ok:
            print(f"  ✓ [{date_str}] 完成")
        else:
            print(f"  ✗ [{date_str}] 失败 (exit={proc.returncode})")
        return date_str, ok
    except FileNotFoundError:
        print(f"  ✗ [{date_str}] 找不到二进制: {config.binary}")
        return date_str, False


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析命令行参数，自动加载 .env 中的默认值。"""
    dotenv = load_dotenv()

    parser = argparse.ArgumentParser(
        description="补跑历史 run 数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s --start-date 2026-01-01 --end-date 2026-06-04\n"
            "  %(prog)s --start-date 2026-05-01 --end-date 2026-05-31 --force\n"
            "  %(prog)s --start-date 2026-03-01 --end-date 2026-06-04 --jobs 4\n"
        ),
    )

    parser.add_argument("--start-date", required=True, type=date.fromisoformat, help="起始日期 (含)")
    parser.add_argument("--end-date", required=True, type=date.fromisoformat, help="截止日期 (含)")
    parser.add_argument("--method", default=resolve_env("STOCK_SELECT_METHOD", DEFAULT_METHOD, dotenv), help="筛选方法，默认 b2")
    parser.add_argument("--binary", type=Path, default=Path(resolve_env("STOCK_SELECT_BIN", str(DEFAULT_BINARY), dotenv) or str(DEFAULT_BINARY)), help="二进制路径")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 run artifact")
    parser.add_argument("--dry-run", action="store_true", help="只打印要执行的命令")
    parser.add_argument("--jobs", "-j", type=int, default=2, help="并发数，默认 2（设为 1 则串行）")
    parser.add_argument("--runtime-root", type=Path, default=Path(resolve_env("STOCK_SELECT_RUNTIME_ROOT", "runtime", dotenv) or "runtime"), help="runtime 根目录")
    parser.add_argument("--postgres-dsn", default=resolve_env("POSTGRES_DSN", dotenv=dotenv), help="PostgreSQL DSN（用于查交易日历）")

    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    dotenv = load_dotenv()

    # 确定 DSN：优先参数，其次环境变量，其次 .env
    dsn = args.postgres_dsn or resolve_env("POSTGRES_DSN", dotenv=dotenv)

    config = RunConfig(
        binary=args.binary,
        runtime_root=args.runtime_root,
        method=args.method,
        workers=args.jobs,
        skip_existing=not args.force,
        dry_run=args.dry_run,
    )

    # ── 阶段 1：确定待处理日期 ─────────────────────────────────────────────
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
    for d in dates:
        print(f"  - {d}")
    print()

    # ── 阶段 2：执行 ────────────────────────────────────────────────────────
    if config.dry_run:
        print("━━━ DRY RUN ━━━")
        for d in dates:
            print(f"  {config.binary} run --method {config.method} --pick-date {d}")
        print(f"总计 {len(dates)} 天")
        return 0

    result = RunResult(total=len(dates), skipped=skipped)

    print(f"━━━ 开始补跑 (并发={config.workers}) ━━━")

    if config.workers <= 1:
        # 串行
        for ds in dates:
            print(f"━━━ [{ds}] 开始 ━━━")
            if run_single(ds, config):
                result.success += 1
            else:
                result.failed += 1
            print()
    else:
        # 并发
        with ThreadPoolExecutor(max_workers=config.workers) as pool:
            futures = {
                pool.submit(run_single_quiet, ds, config): ds
                for ds in dates
            }
            for future in as_completed(futures):
                _ds, ok = future.result()
                if ok:
                    result.success += 1
                else:
                    result.failed += 1

    # ── 汇总 ───────────────────────────────────────────────────────────────
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
    print("═" * 45)

    return 1 if result.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
