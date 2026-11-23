from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("run", description="Run ranked stock signals with AKQuant.")
    parser.add_argument("--signals", type=Path, required=True, help="CSV/JSON/JSONL signal file or daily Rust run directory")
    parser.add_argument("--method", help="select one screening method from a Rust run directory")
    parser.add_argument("--market-data", type=Path, required=True, help="CSV/Parquet OHLCV data or a directory of files")
    parser.add_argument("--output", type=Path, required=True, help="JSON report output path")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--holding-days", type=int, default=3)
    parser.add_argument("--entry-policy", type=Path, help="独立的开仓许可与每日预算 JSON 配置")
    parser.add_argument("--exit-policy", type=Path, help="MA25/放量阳线半线/T+3/KDJ 的退出 JSON 配置，替代固定持有期")
    parser.add_argument("--backtest-end-date", help="规则退出的最后估值日期 YYYY-MM-DD，未退出持仓保留市值")
    parser.add_argument("--daily-context", type=Path, help="信号日环境 CSV，含 date/env 列；可直接使用排名数据集")
    parser.add_argument("--capital-allocation", type=float, default=0.99, help="fraction of portfolio equity divided across holding days for daily baskets")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.0003)
    parser.add_argument("--stamp-tax-rate", type=float, default=0.0005)
    parser.add_argument("--transfer-fee-rate", type=float, default=0.00001)
    parser.add_argument("--min-commission", type=float, default=5.0)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--t-plus-one", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--defer-suspended-exit", action=argparse.BooleanOptionalAction, default=False,
                        help="退出日无 K 线时延至首个可交易开盘；默认要求完整成交行情")
    parser.set_defaults(handler=main_from_args)
    return parser


def main_from_args(args: argparse.Namespace) -> int:
    from .akquant_gateway import BacktestConfig, load_market_data, run_akquant_backtest
    from .report import write_report
    from .signal_bundle import load_signal_bundle
    from .entry_policy import load_daily_environments, load_entry_policy
    from .rule_exit import load_exit_policy

    config = BacktestConfig(
        top_n=args.top_n,
        holding_days=args.holding_days,
        capital_allocation=args.capital_allocation,
        initial_cash=args.initial_cash,
        commission_rate=args.commission_rate,
        stamp_tax_rate=args.stamp_tax_rate,
        transfer_fee_rate=args.transfer_fee_rate,
        min_commission=args.min_commission,
        lot_size=args.lot_size,
        t_plus_one=args.t_plus_one,
        defer_suspended_exit=args.defer_suspended_exit,
    )
    signals = load_signal_bundle(args.signals, method=args.method)
    entry_policy = load_entry_policy(args.entry_policy) if args.entry_policy else None
    environments = load_daily_environments(args.daily_context) if args.daily_context else None
    result = run_akquant_backtest(load_market_data(args.market_data), signals, config,
                                 entry_policy=entry_policy, environments=environments,
                                 exit_policy=load_exit_policy(args.exit_policy) if args.exit_policy else None,
                                 end_date=args.backtest_end_date)
    report = write_report(result, args.output)
    print(f"wrote {args.output} ({len(report['equity_curve'])} equity points)")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stock-select-ml backtest")
    subparsers = parser.add_subparsers(dest="command")
    add_parser(subparsers)
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_usage()
        return 2
    return int(handler(args))
