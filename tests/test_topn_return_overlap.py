from __future__ import annotations

import unittest

from ml.training.evaluation import topn_return_overlap


class TopNReturnOverlapTest(unittest.TestCase):
    def test_measures_daily_intersection_against_future_return_top_n(self):
        rows = [
            {"date": "2026-01-05", "code": "A", "model_score": 4, "ret5": 9},
            {"date": "2026-01-05", "code": "B", "model_score": 3, "ret5": 8},
            {"date": "2026-01-05", "code": "C", "model_score": 2, "ret5": 7},
            {"date": "2026-01-05", "code": "D", "model_score": 1, "ret5": 1},
            {"date": "2026-01-06", "code": "A", "model_score": 4, "ret5": 1},
            {"date": "2026-01-06", "code": "B", "model_score": 3, "ret5": 3},
            {"date": "2026-01-06", "code": "C", "model_score": 2, "ret5": 4},
            {"date": "2026-01-06", "code": "D", "model_score": 1, "ret5": 2},
        ]
        metrics = topn_return_overlap(rows, return_column="ret5", top_n=3)
        self.assertEqual(metrics["top3_ret5_overlap_dates"], 2)
        self.assertEqual(metrics["top3_ret5_mean_overlap"], 2.5)
        self.assertAlmostEqual(metrics["top3_ret5_overlap_rate"], 2.5 / 3 * 100, places=3)
        self.assertEqual(metrics["top3_ret5_exact_match_rate"], 50.0)

    def test_ignores_incomplete_targets_and_dates_with_too_few_labeled_candidates(self):
        rows = [
            {"date": "2026-01-05", "code": "A", "model_score": 4, "ret5": 8},
            {"date": "2026-01-05", "code": "B", "model_score": 3, "ret5": 7},
            {"date": "2026-01-05", "code": "C", "model_score": 2, "ret5": ""},
            {"date": "2026-01-05", "code": "D", "model_score": 1, "ret5": 6},
            {"date": "2026-01-05", "code": "E", "model_score": 0, "ret5": 9},
            {"date": "2026-01-06", "code": "A", "model_score": 4, "ret5": 3},
            {"date": "2026-01-06", "code": "B", "model_score": 3, "ret5": None},
        ]
        metrics = topn_return_overlap(rows, return_column="ret5", top_n=3)
        self.assertEqual(metrics["top3_ret5_overlap_dates"], 1)
        self.assertEqual(metrics["top3_ret5_mean_overlap"], 2.0)

    def test_rejects_invalid_top_n(self):
        with self.assertRaises(ValueError):
            topn_return_overlap([], return_column="ret5", top_n=0)

    def test_supports_fee_adjusted_exit_return_targets_even_when_all_are_negative(self):
        rows = [
            {"date": "2026-01-05", "code": "A", "model_score": 4, "exit_net_return": -1.0},
            {"date": "2026-01-05", "code": "B", "model_score": 3, "exit_net_return": -2.0},
            {"date": "2026-01-05", "code": "C", "model_score": 2, "exit_net_return": -3.0},
            {"date": "2026-01-05", "code": "D", "model_score": 1, "exit_net_return": -4.0},
        ]
        metrics = topn_return_overlap(rows, return_column="exit_net_return", top_n=3)
        self.assertEqual(metrics["top3_exit_net_return_mean_overlap"], 3.0)
        self.assertEqual(metrics["top3_exit_net_return_overlap_rate"], 100.0)


if __name__ == "__main__":
    unittest.main()
