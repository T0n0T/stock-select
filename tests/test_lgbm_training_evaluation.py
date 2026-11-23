import unittest

from ml.training.evaluation import average_metric_dicts, evaluate_model, selection_success_analysis
from ml.training.labels import labels, rows_for_dates


class LgbmTrainingEvaluationTest(unittest.TestCase):
    def test_rows_for_dates_uses_requested_label_column(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "1", "rank_label_5d": ""},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "", "rank_label_5d": "3"},
        ]

        selected = rows_for_dates(rows, {"2026-01-01"}, label_column="rank_label_5d")

        self.assertEqual([row["code"] for row in selected], ["b"])

    def test_ret3_ge5_label_is_derived_from_forward_return(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "ret3": "6.2"},
            {"date": "2026-01-01", "code": "b", "ret3": "4.9"},
            {"date": "2026-01-01", "code": "c", "ret3": ""},
        ]

        selected = rows_for_dates(rows, {"2026-01-01"}, label_column="ret3_ge5_label")

        self.assertEqual([row["code"] for row in selected], ["a", "b"])
        self.assertEqual(labels(selected, label_column="ret3_ge5_label"), [3, 0])

    def test_average_metric_dicts_ignores_missing_values(self):
        average = average_metric_dicts(
            [
                {"rank_ic_ret3": "0.1", "top3_ret3_ge_5_rate": 20},
                {"rank_ic_ret3": "", "top3_ret3_ge_5_rate": 40},
            ]
        )

        self.assertEqual(average["rank_ic_ret3"], 0.1)
        self.assertEqual(average["top3_ret3_ge_5_rate"], 30.0)

    def test_evaluate_model_reports_rank_ic_ret5(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "model_score": 3, "ret3": "6", "ret5": "-1"},
            {"date": "2026-01-01", "code": "b", "model_score": 2, "ret3": "-1", "ret5": "8"},
            {"date": "2026-01-01", "code": "c", "model_score": 1, "ret3": "2", "ret5": "1"},
        ]

        metrics = evaluate_model(rows, top_n=2)

        self.assertEqual(metrics["top2_ret3_positive_rate"], 50.0)
        self.assertEqual(metrics["top2_ret3_ge_5_rate"], 50.0)
        self.assertEqual(metrics["top2_ret5_positive_rate"], 50.0)
        self.assertEqual(metrics["top2_ret5_ge_5_rate"], 50.0)
        self.assertIn("rank_ic_ret5", metrics)

    def test_evaluate_model_reports_multiple_top_k_and_ndcg(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "model_score": 3, "rank_label_3d": "3", "ret3": "6", "ret5": "6"},
            {"date": "2026-01-01", "code": "b", "model_score": 2, "rank_label_3d": "2", "ret3": "2", "ret5": "2"},
            {"date": "2026-01-01", "code": "c", "model_score": 1, "rank_label_3d": "0", "ret3": "-1", "ret5": "-1"},
        ]

        metrics = evaluate_model(rows, top_k=[1, 2], label_column="rank_label_3d", ndcg_at=[1, 2])

        self.assertEqual(metrics["top1_ret3_ge_5_rate"], 100.0)
        self.assertEqual(metrics["top2_ret3_positive_rate"], 100.0)
        self.assertEqual(metrics["top2_ret3_le_0_rate"], 0.0)
        self.assertEqual(metrics["ndcg_at_1"], 1.0)
        self.assertEqual(metrics["ndcg_at_2"], 1.0)

    def test_selection_success_analysis_uses_daily_top_k_and_market_environment(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "model_score": 3, "env": "weak",
             "ret_t1_open_to_t3_close": 8, "benchmark_csi300_ret_t1_open_to_t3_close": 2,
             "market_up_ratio": 0.2, "market_index_csi300_weight_pct": 0},
            {"date": "2026-01-01", "code": "b", "model_score": 2, "env": "weak",
             "ret_t1_open_to_t3_close": -2, "benchmark_csi300_ret_t1_open_to_t3_close": 2,
             "market_up_ratio": 0.2, "market_index_csi300_weight_pct": 5},
            {"date": "2026-01-02", "code": "c", "model_score": 3, "env": "weak",
             "ret_t1_open_to_t3_close": -4, "benchmark_csi300_ret_t1_open_to_t3_close": 1,
             "market_up_ratio": 0.8, "market_index_csi300_weight_pct": 0},
            {"date": "2026-01-02", "code": "d", "model_score": 2, "env": "weak",
             "ret_t1_open_to_t3_close": 5, "benchmark_csi300_ret_t1_open_to_t3_close": 1,
             "market_up_ratio": 0.8, "market_index_csi300_weight_pct": 0},
            {"date": "2026-01-03", "code": "e", "model_score": 3, "env": "strong",
             "ret_t1_open_to_t3_close": 3, "benchmark_csi300_ret_t1_open_to_t3_close": 1,
             "market_up_ratio": 0.4, "market_index_csi300_weight_pct": 0},
            {"date": "2026-01-03", "code": "f", "model_score": 2, "env": "strong",
             "ret_t1_open_to_t3_close": -1, "benchmark_csi300_ret_t1_open_to_t3_close": 1,
             "market_up_ratio": 0.4, "market_index_csi300_weight_pct": 0},
        ]

        analysis = selection_success_analysis(rows, top_k=1)

        self.assertEqual(analysis["date_count"], 3)
        self.assertEqual(analysis["selected_count"], 3)
        self.assertEqual(analysis["win_count"], 2)
        self.assertEqual(analysis["pooled_win_rate"], 66.7)
        self.assertEqual(analysis["benchmark_win_rate"], 66.7)
        self.assertEqual(analysis["mean_excess_return_pct"], 1.0)
        self.assertEqual(analysis["by_env"]["weak"]["date_count"], 2)
        self.assertEqual(analysis["by_env"]["strong"]["pooled_win_rate"], 100.0)
        self.assertEqual(analysis["environment_correlations"]["market_up_ratio"]["pearson_r"], -0.9449)
        self.assertNotIn("market_index_csi300_weight_pct", analysis["environment_correlations"])

    def test_selection_success_analysis_skips_days_without_return_labels(self):
        analysis = selection_success_analysis(
            [{"date": "2026-01-01", "code": "a", "model_score": 1, "ret_t1_open_to_t3_close": ""}],
            top_k=1,
        )

        self.assertEqual(analysis["date_count"], 0)
        self.assertIsNone(analysis["pooled_win_rate"])

    def test_selection_success_analysis_can_measure_all_daily_candidates(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "model_score": 2, "env": "weak", "ret_t1_open_to_t3_close": 4},
            {"date": "2026-01-01", "code": "b", "model_score": 1, "env": "weak", "ret_t1_open_to_t3_close": -2},
            {"date": "2026-01-02", "code": "c", "model_score": 2, "env": "strong", "ret_t1_open_to_t3_close": 1},
            {"date": "2026-01-02", "code": "d", "model_score": 1, "env": "strong", "ret_t1_open_to_t3_close": -1},
        ]

        analysis = selection_success_analysis(rows, top_k=None)

        self.assertEqual(analysis["selection_scope"], "all_candidates")
        self.assertEqual(analysis["date_count"], 2)
        self.assertEqual(analysis["selected_count"], 4)
        self.assertEqual(analysis["pooled_win_rate"], 50.0)


if __name__ == "__main__":
    unittest.main()
