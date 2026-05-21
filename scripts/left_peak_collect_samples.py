from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd
import psycopg

from stock_select.cli import _load_prepared_cache_v2, _prepare_screen_data, _write_prepared_cache_v2
from stock_select.db_access import fetch_available_trade_dates, fetch_daily_window, load_dotenv_value, resolve_dsn
from stock_select.strategies.b1 import DEFAULT_TOP_M, build_top_turnover_pool
from stock_select.strategies.left_peak import iter_left_peak_screen_rows


def _default_runtime_root() -> Path:
    return PROJECT_ROOT / "runtime"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect left_peak screen samples across a trade-date range.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--runtime-root", type=Path, default=_default_runtime_root())
    parser.add_argument("--dsn")
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(argv)


def _output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir is not None:
        return args.output_dir
    return args.runtime_root / "research" / "left_peak_samples"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime_root = args.runtime_root
    prepared_root = runtime_root / "prepared"
    output_dir = _output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / f"samples_{args.start_date}_{args.end_date}.csv"
    stats_path = output_dir / f"daily_stats_{args.start_date}_{args.end_date}.csv"

    dsn = resolve_dsn(args.dsn, os.getenv("POSTGRES_DSN"), load_dotenv_value(PROJECT_ROOT / ".env", "POSTGRES_DSN"))
    with psycopg.connect(dsn) as conn:
        trade_dates = fetch_available_trade_dates(conn)
        trade_dates["trade_date"] = pd.to_datetime(trade_dates["trade_date"], errors="coerce", format="mixed")
        target_dates = (
            trade_dates.loc[
                (trade_dates["trade_date"] >= pd.Timestamp(args.start_date))
                & (trade_dates["trade_date"] <= pd.Timestamp(args.end_date))
            ]
            .sort_values("trade_date")["trade_date"]
            .dt.strftime("%Y-%m-%d")
            .tolist()
        )

        rows: list[dict[str, object]] = []
        daily_stats: list[dict[str, object]] = []
        done_dates: set[str] = set()
        if samples_path.exists() and samples_path.stat().st_size > 0:
            rows = pd.read_csv(samples_path).to_dict("records")
        if stats_path.exists() and stats_path.stat().st_size > 0:
            daily_stats = pd.read_csv(stats_path).to_dict("records")
            done_dates = {str(row["pick_date"]) for row in daily_stats if row.get("pick_date")}

        print(f"target_dates={len(target_dates)} done_dates={len(done_dates)}")
        for index, pick_date in enumerate(target_dates, start=1):
            if pick_date in done_dates:
                continue

            print(f"[{index}/{len(target_dates)}] {pick_date}")
            data_path = prepared_root / f"{pick_date}.feather"
            meta_path = prepared_root / f"{pick_date}.meta.json"
            if data_path.exists() and meta_path.exists():
                payload = _load_prepared_cache_v2(data_path, meta_path)
                prepared = payload["prepared_table"]
                print(f"  reuse prepared rows={len(prepared)}")
            else:
                start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d")
                market = fetch_daily_window(conn, start_date=start_date, end_date=pick_date, symbols=None)
                print(f"  fetched market rows={len(market)}")
                prepared = _prepare_screen_data(market)
                _write_prepared_cache_v2(
                    data_path,
                    meta_path,
                    method="left_peak",
                    pick_date=pick_date,
                    start_date=start_date,
                    end_date=pick_date,
                    prepared_table=prepared,
                )
                print(f"  wrote prepared rows={len(prepared)}")

            pool_codes = build_top_turnover_pool(prepared, top_m=DEFAULT_TOP_M).get(pd.Timestamp(pick_date), [])
            prepared_for_pick = prepared.loc[prepared["ts_code"].isin(pool_codes)].copy() if pool_codes else prepared.iloc[0:0].copy()
            candidates, stats = iter_left_peak_screen_rows(prepared_for_pick, pd.Timestamp(pick_date))

            daily_stats.append({"pick_date": pick_date, "pool_size": len(pool_codes), **stats})
            for item in candidates:
                rows.append(
                    {
                        "pick_date": pick_date,
                        "code": item["code"],
                        "close": item["close"],
                        "turnover_n": item["turnover_n"],
                    }
                )

            if index % 5 == 0 or index == len(target_dates):
                pd.DataFrame(rows).to_csv(samples_path, index=False)
                pd.DataFrame(daily_stats).to_csv(stats_path, index=False)
            print(f"  pool={len(pool_codes)} selected={len(candidates)} total_rows={len(rows)}")

    sample_frame = pd.DataFrame(rows)
    pd.DataFrame(rows).to_csv(samples_path, index=False)
    pd.DataFrame(daily_stats).to_csv(stats_path, index=False)
    print(f"samples={samples_path}")
    print(f"daily_stats={stats_path}")
    print(f"total_rows={len(sample_frame)}")
    if not sample_frame.empty:
        month_counts = sample_frame.assign(month=sample_frame["pick_date"].astype(str).str.slice(0, 7)).groupby("month").size().to_dict()
        print(f"month_counts={json.dumps(month_counts, ensure_ascii=True, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
