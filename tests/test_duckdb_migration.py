import csv
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ml.backfill import candidates, record, runs
from ml.db import query_rows
from ml.dates import fetch_trade_dates
from ml.dataset.intraday_proxy import load_previous_eod_czsc_lookup
from ml.dataset.rank_dataset import fetch_price_rows
from ml.review import recurring_candidates


class DuckDbMigrationTests(unittest.TestCase):
    def test_query_bridge_uses_explicit_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "stock-select-rs"
            binary.touch()
            with patch("ml.db.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as run:
                self.assertEqual(query_rows("cache.duckdb", "SELECT 1", [], binary=binary), [])
        self.assertEqual(run.call_args.args[0], [str(binary), "db-query"])

    def test_configured_binary_can_be_resolved_on_path(self):
        with patch("ml.db.resolve_config_value", return_value="stock-select-rs"), \
             patch("ml.db.shutil.which", return_value="/usr/local/bin/stock-select-rs"), \
             patch("ml.db.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as run:
            query_rows("cache.duckdb", "SELECT 1", [])
        self.assertEqual(run.call_args.args[0], ["/usr/local/bin/stock-select-rs", "db-query"])

    def test_explicit_binary_is_used_for_backfill_calendar_queries(self):
        binary = Path("/tmp/explicit-stock-select")
        args = SimpleNamespace(dates_file=None, duckdb_path="cache.duckdb", start_date="2026-06-01",
                               end_date="2026-06-02", binary=binary)
        with patch("ml.backfill.candidates.fetch_trade_dates", return_value=[]) as query:
            candidates._resolve_trade_dates(args, {})
        self.assertEqual(query.call_args.kwargs["binary"], binary)
        with patch("ml.backfill.runs.fetch_trade_dates", return_value=[]) as query:
            runs.build_dates(date(2026, 6, 1), date(2026, 6, 2), "cache.duckdb", Path("/tmp"),
                             "b2", False, binary=binary)
        self.assertEqual(query.call_args.kwargs["binary"], binary)
        with patch("ml.backfill.record.fetch_trade_dates", return_value=[]) as query:
            record.recent_trade_dates(days=2, duckdb_path="cache.duckdb", end_date=date(2026, 6, 2), binary=binary)
        self.assertEqual(query.call_args.kwargs["binary"], binary)
        with patch("ml.review.recurring_candidates.query_rows", return_value=[]) as query:
            recurring_candidates.fetch_recent_trade_dates("cache.duckdb", "2026-06-02", 2, binary=binary)
        self.assertEqual(query.call_args.kwargs["binary"], binary)

    def test_backfill_subprocesses_receive_explicit_data_source(self):
        binary = Path("/tmp/stock-select")
        source = "quack://127.0.0.1:9494"
        run_config = runs.RunConfig(binary, Path("/tmp"), "b2", 1, False, True, False, "turnover-top", duckdb_path=source)
        self.assertEqual(runs.command_for_date("2026-06-02", run_config)[-2:], ["--duckdb-path", source])
        record_config = record.RecordBackfillConfig(binary, Path("/tmp"), ("b2",), 1, True, None, duckdb_path=source)
        self.assertEqual(record.command_for_task(record.RecordTask("2026-06-02", "b2"), record_config)[-2:], ["--duckdb-path", source])
        candidate_config = candidates.BackfillConfig(binary, Path("/tmp"), duckdb_path=source)
        runner = lambda command, **kwargs: subprocess.CompletedProcess(command, 0)
        _, completed = candidates._run_one("2026-06-02", config=candidate_config, runner=runner)
        self.assertEqual(completed.args[-2:], ["--duckdb-path", source])

    def test_trade_dates_use_market_rows(self):
        with patch("ml.dates.query_rows", return_value=[{"trade_date": "2026-06-01"}]) as query:
            self.assertEqual(fetch_trade_dates("cache.duckdb", "2026-06-01", "2026-06-02"), ["2026-06-01"])
        self.assertIn("stock_stk_factor_pro", query.call_args.args[1])
        self.assertEqual(query.call_args.args[2], ["2026-06-01", "2026-06-02"])

    def test_price_rows_preserve_qfq_labels(self):
        row = {"ts_code": "000001.SZ", "trade_date": "2026-06-01", "open": 10.0, "close": 10.5,
               "high": 11.0, "low": 9.0, "vol": 1000.0, "turnover_rate": 2.5, "pct_chg": 5.0, "adj_factor": 1.2}
        with patch("ml.dataset.rank_dataset.query_rows", return_value=[row]) as query:
            rows = fetch_price_rows("cache.duckdb", ["000001.SZ"], "2026-06-01", "2026-06-02")
        self.assertEqual(rows["000001.SZ"][0]["adj_factor"], 1.2)
        self.assertEqual(rows["000001.SZ"][0]["price_basis"], "qfq")
        self.assertEqual(query.call_args.args[2][0], ["000001.SZ"])

    def test_czsc_anchors_use_v3_daily_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            path.write_text("date,code\n2026-06-02,000001.SZ\n", encoding="utf-8")
            row = {"sample_date": "2026-06-02", "ts_code": "000001.SZ", "status": "ok", "last_bi_high": 12.0}
            with patch("ml.dataset.intraday_proxy.query_rows", return_value=[row]) as query:
                result = load_previous_eod_czsc_lookup(source_dataset=path, duckdb_path="cache.duckdb")
        self.assertEqual(result[("2026-06-02", "000001.SZ")]["last_bi_high"], 12.0)
        sql = query.call_args.args[1]
        self.assertIn("calc_daily_czsc_structure", sql)
        self.assertIn("daily_last_bi_high", sql)
        self.assertIn("v3-macd-kdj-czsc-1", sql)


if __name__ == "__main__":
    unittest.main()
