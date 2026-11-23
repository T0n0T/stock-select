import unittest
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from ml.dataset import rank_dataset
from ml.security_identity import canonicalize_security_rows, fetch_security_aliases


ALIAS = {
    "old_code": "831445.BJ",
    "new_code": "920445.BJ",
    "identical_raw_bars": 368,
    "old_last_date": "2025-04-30",
}


class SecurityIdentityTest(unittest.TestCase):
    def test_deduplicates_same_security_but_preserves_historical_factors_and_old_only_rows(self):
        originals = [
            {"date": "2023-02-20", "code": "920445.BJ", "close": 8.0},
            {"date": "2023-02-20", "code": "831445.BJ", "close": 9.0},
            {"date": "2023-02-21", "code": "831445.BJ", "close": 10.0},
            {"date": "2023-02-20", "code": "834445.BJ", "close": 11.0},
        ]
        rows, audit = canonicalize_security_rows(originals, [ALIAS])
        self.assertEqual(len(rows), 3)
        by_key = {(row["date"], row["code"]): row for row in rows}
        self.assertEqual(by_key[("2023-02-20", "920445.BJ")]["close"], 9.0)
        self.assertEqual(by_key[("2023-02-21", "920445.BJ")]["close"], 10.0)
        self.assertIn(("2023-02-20", "834445.BJ"), by_key)
        self.assertEqual(audit["duplicate_row_count"], 1)
        self.assertEqual(audit["remapped_source_row_count"], 2)
        self.assertEqual(originals[1]["code"], "831445.BJ")

    def test_ambiguous_identity_or_duplicate_source_rows_raise(self):
        for aliases in ([ALIAS, dict(ALIAS, new_code="920999.BJ")],
                        [ALIAS, dict(ALIAS, old_code="834445.BJ")],
                        [dict(ALIAS, identical_raw_bars=19)]):
            with self.subTest(aliases=aliases), self.assertRaises(ValueError):
                canonicalize_security_rows([], aliases)
        row = {"date": "2023-02-20", "code": "831445.BJ"}
        with self.assertRaisesRegex(ValueError, "duplicate source"):
            canonicalize_security_rows([row, row], [ALIAS])

    def test_price_lookup_uses_one_continuous_qfq_series_across_code_change(self):
        prices = [
            {"ts_code": "920445.BJ", "trade_date": "2025-04-30", "close": 9.0},
            {"ts_code": "920445.BJ", "trade_date": "2025-05-06", "open": 9.0, "close": 9.9},
            {"ts_code": "920445.BJ", "trade_date": "2025-05-07", "open": 9.9, "close": 10.8},
            {"ts_code": "920445.BJ", "trade_date": "2025-05-08", "open": 10.8, "close": 11.7},
        ]
        with patch("ml.dataset.rank_dataset.fetch_security_aliases", return_value=[ALIAS]), \
             patch("ml.dataset.rank_dataset.query_rows", return_value=prices) as query:
            histories = rank_dataset.fetch_price_rows("unused", ["831445.BJ", "920445.BJ"],
                                                      "2025-04-01", "2025-05-10")
        self.assertEqual(query.call_args.args[2][0], ["920445.BJ"])
        self.assertEqual(histories["831445.BJ"], histories["920445.BJ"])
        labels = rank_dataset.compute_forward_labels(histories["831445.BJ"], "2025-04-30")
        self.assertEqual(labels["ret_t1_open_to_t3_close"], 30.0)

    def test_new_codes_need_no_alias_query_and_old_codes_use_shared_verified_query(self):
        with patch("ml.security_identity.query_rows", return_value=[ALIAS]) as query:
            self.assertEqual(fetch_security_aliases("unused", ["920445.BJ", "000001.SZ"]), [])
            query.assert_not_called()
            self.assertEqual(fetch_security_aliases("unused", ["831445.BJ"]), [ALIAS])
            self.assertIn("stock_stk_factor_pro", query.call_args.args[1])

    def test_formal_dataset_entrypoint_normalizes_existing_artifacts_before_labels(self):
        inputs = [
            {"date": "2025-04-30", "code": "831445.BJ", "method": "scm", "close_to_ma25_pct": 10.04},
            {"date": "2025-04-30", "code": "920445.BJ", "method": "scm", "close_to_ma25_pct": 9.71385},
        ]
        history = [
            {"trade_date": "2025-04-30", "open": 9.0, "close": 9.0, "price_basis": "qfq"},
            {"trade_date": "2025-05-06", "open": 9.0, "close": 9.9, "price_basis": "qfq"},
            {"trade_date": "2025-05-07", "open": 9.9, "close": 10.8, "price_basis": "qfq"},
            {"trade_date": "2025-05-08", "open": 10.8, "close": 11.7, "price_basis": "qfq"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "out"
            args = rank_dataset.parse_args([
                "--method", "scm", "--start-date", "2025-04-30", "--end-date", "2025-04-30",
                "--runtime-root", str(root), "--output-dir", str(output), "--duckdb-path", "unused",
            ])
            with patch.object(rank_dataset, "load_candidate_rows", return_value=(inputs, [])), \
                 patch.object(rank_dataset, "fetch_security_aliases", return_value=[ALIAS]), \
                 patch.object(rank_dataset, "fetch_price_rows", return_value={"920445.BJ": history}) as prices, \
                 patch.object(rank_dataset, "fetch_benchmark_price_rows", return_value=[]):
                self.assertEqual(rank_dataset.main_from_args(args), 0)
            self.assertEqual(prices.call_args.args[1], ["920445.BJ"])
            with (output / "rank_dataset.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            summary = json.loads((output / "rank_dataset_summary.json").read_text())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], "920445.BJ")
        self.assertEqual(float(rows[0]["close_to_ma25_pct"]), 10.04)
        self.assertEqual(float(rows[0]["ret_t1_open_to_t3_close"]), 30.0)
        self.assertEqual(summary["security_identity"]["duplicate_row_count"], 1)


if __name__ == "__main__":
    unittest.main()
