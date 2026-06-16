import unittest
from unittest.mock import patch

from scripts.ml.controlled_rerank_diagnostics import (
    TrialModelConfig,
    assign_date_local_model_ranks,
    rolling_oof_predictions,
    score_combined_alpha,
    score_env_switch,
    score_env_three_way,
    score_median_risk_demote,
    summarize_scored_folds,
    evaluate_rerank_rules,
)


class ControlledRerankDiagnosticsTest(unittest.TestCase):
    def test_assign_date_local_model_ranks_are_fold_and_date_local(self):
        rows = [
            {"fold": 1, "date": "2026-03-02", "code": "b", "main_score": 0.2, "risk_score": 0.1},
            {"fold": 1, "date": "2026-03-02", "code": "a", "main_score": 0.2, "risk_score": 0.3},
            {"fold": 1, "date": "2026-03-02", "code": "c", "main_score": 0.1, "risk_score": 0.2},
            {"fold": 2, "date": "2026-03-02", "code": "b", "main_score": 0.5, "risk_score": 0.1},
        ]

        ranked = assign_date_local_model_ranks(rows, model_names=["main", "risk"])

        ranks = {(row["fold"], row["date"], row["code"]): row for row in ranked}
        self.assertEqual(ranks[(1, "2026-03-02", "a")]["main_rank"], 1)
        self.assertEqual(ranks[(1, "2026-03-02", "b")]["main_rank"], 2)
        self.assertEqual(ranks[(1, "2026-03-02", "c")]["main_rank"], 3)
        self.assertEqual(ranks[(2, "2026-03-02", "b")]["main_rank"], 1)
        self.assertEqual(ranks[(1, "2026-03-02", "a")]["risk_rank"], 1)
        self.assertEqual(ranks[(1, "2026-03-02", "b")]["risk_rank"], 3)

    def test_median_risk_demote_only_penalizes_primary_topn_lagging_risk(self):
        rows = [
            {"fold": 1, "date": "2026-03-02", "code": "a", "sw4_rank": 1, "rf_rank": 5},
            {"fold": 1, "date": "2026-03-02", "code": "b", "sw4_rank": 2, "rf_rank": 1},
            {"fold": 1, "date": "2026-03-02", "code": "c", "sw4_rank": 3, "rf_rank": 2},
            {"fold": 1, "date": "2026-03-02", "code": "d", "sw4_rank": 4, "rf_rank": 4},
            {"fold": 1, "date": "2026-03-02", "code": "e", "sw4_rank": 5, "rf_rank": 3},
        ]

        scored = score_median_risk_demote(rows, primary="sw4", risk="rf", top_n=3)
        ordered_codes = [row["code"] for row in sorted(scored, key=lambda row: -row["model_score"])]

        self.assertEqual(ordered_codes[:3], ["b", "c", "d"])
        self.assertLess(scored[0]["model_score"], scored[3]["model_score"])
        self.assertEqual(scored[3]["model_score"], -4.0)

    def test_combined_alpha_and_env_switch_scores_are_interpretable(self):
        rows = [
            {"date": "2026-03-02", "code": "a", "env": "strong", "sw4_score": 1.0, "rf_score": 2.0, "sw5_score": 3.0},
            {"date": "2026-03-03", "code": "b", "env": "weak", "sw4_score": 1.0, "rf_score": 2.0, "sw5_score": 3.0},
            {"date": "2026-03-04", "code": "c", "env": "neutral", "sw4_score": 1.0, "rf_score": 2.0, "sw5_score": 3.0},
        ]

        combined = score_combined_alpha(rows, primary="sw4", risk="rf", alpha=0.4)
        switched = score_env_switch(rows, strong_model="sw4", fallback_model="sw5")

        self.assertEqual([row["model_score"] for row in combined], [1.8, 1.8, 1.8])
        self.assertEqual([row["model_score"] for row in switched], [1.0, 3.0, 3.0])

    def test_three_way_env_switch_scores_are_interpretable(self):
        rows = [
            {"date": "2026-03-02", "code": "a", "env": "strong", "sw4_score": 1.0, "rf_score": 2.0, "sw5_score": 3.0},
            {"date": "2026-03-03", "code": "b", "env": "weak", "sw4_score": 1.0, "rf_score": 2.0, "sw5_score": 3.0},
            {"date": "2026-03-04", "code": "c", "env": "neutral", "sw4_score": 1.0, "rf_score": 2.0, "sw5_score": 3.0},
            {"date": "2026-03-05", "code": "d", "env": "unknown", "sw4_score": 1.0, "rf_score": 2.0, "sw5_score": 3.0},
        ]

        switched = score_env_three_way(rows, strong_model="sw4", weak_model="sw5", neutral_model="rf")

        self.assertEqual([row["model_score"] for row in switched], [1.0, 3.0, 2.0, 2.0])

    def test_evaluate_rerank_rules_includes_three_way_env_candidate(self):
        rows = [
            {"fold": 1, "date": "2026-03-02", "code": "a", "env": "strong", "ret3": 1, "ret5": 1, "sw4_score": 3, "sw5_score": 1, "rf_score": 1},
            {"fold": 1, "date": "2026-03-02", "code": "b", "env": "weak", "ret3": 1, "ret5": 1, "sw4_score": 1, "sw5_score": 3, "rf_score": 1},
            {"fold": 1, "date": "2026-03-02", "code": "c", "env": "neutral", "ret3": 1, "ret5": 1, "sw4_score": 1, "sw5_score": 1, "rf_score": 3},
        ]
        ranked = assign_date_local_model_ranks(rows, model_names=["sw4", "sw5", "rf"])

        results = evaluate_rerank_rules(
            ranked,
            primary_models=["sw4", "sw5"],
            risk_model="rf",
            alphas=[0.2],
            top_n=1,
        )

        self.assertIn("env-strong-sw4-weak-sw5-neutral-rf", [result["rule"] for result in results])

    def test_summarize_scored_folds_averages_fold_metrics_and_partitions(self):
        rows = [
            {"fold": 1, "date": "2026-03-02", "code": "a", "env": "weak", "model_score": 3.0, "ret3": 1.0, "ret5": -1.0},
            {"fold": 1, "date": "2026-03-02", "code": "b", "env": "weak", "model_score": 2.0, "ret3": -1.0, "ret5": -1.0},
            {"fold": 1, "date": "2026-03-02", "code": "c", "env": "weak", "model_score": 1.0, "ret3": 5.0, "ret5": 5.0},
            {"fold": 2, "date": "2026-05-04", "code": "d", "env": "strong", "model_score": 3.0, "ret3": 6.0, "ret5": 6.0},
            {"fold": 2, "date": "2026-05-04", "code": "e", "env": "strong", "model_score": 2.0, "ret3": 4.0, "ret5": -1.0},
            {"fold": 2, "date": "2026-05-04", "code": "f", "env": "strong", "model_score": 1.0, "ret3": -2.0, "ret5": -1.0},
        ]

        summary = summarize_scored_folds(rows, top_n=2)

        self.assertEqual(summary["fold_count"], 2)
        self.assertEqual(summary["metrics"]["top2_ret3_positive_rate"], 75.0)
        self.assertEqual(summary["metrics"]["top2_ret3_ge_5_rate"], 25.0)
        self.assertEqual(summary["metrics"]["top2_ret3_le_0_rate"], 25.0)
        self.assertEqual(summary["metrics"]["top2_ret5_le_0_rate"], 75.0)
        self.assertEqual(summary["by_env"]["weak"]["metrics"]["top2_ret3_le_0_rate"], 50.0)
        self.assertEqual(summary["by_env"]["strong"]["metrics"]["top2_ret3_le_0_rate"], 0.0)
        self.assertEqual(summary["by_month"]["2026-03"]["metrics"]["top2_ret5_le_0_rate"], 100.0)
        self.assertEqual(summary["by_month"]["2026-05"]["metrics"]["top2_ret5_le_0_rate"], 50.0)

    def test_rolling_oof_predictions_export_only_test_fold_scores(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "1", "factor": "1", "ret3": "1", "ret5": "1"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "1", "factor": "2", "ret3": "1", "ret5": "1"},
            {"date": "2026-01-03", "code": "c", "rank_label_3d": "1", "factor": "3", "ret3": "1", "ret5": "1"},
            {"date": "2026-01-04", "code": "d", "rank_label_3d": "1", "factor": "4", "ret3": "1", "ret5": "1"},
            {"date": "2026-01-05", "code": "e", "rank_label_3d": "1", "factor": "5", "ret3": "1", "ret5": "1"},
        ]
        configs = [
            TrialModelConfig(
                name="main",
                numeric_columns=["factor"],
                categorical_columns=[],
                fixed_categorical_levels={},
                categorical_encoding="one_hot",
                label_column="rank_label_3d",
                model_params={
                    "num_leaves": 5,
                    "min_data_in_leaf": 1,
                    "num_boost_round": 3,
                    "learning_rate": 0.1,
                    "num_threads": 1,
                    "label_gain": [0, 1, 3, 7],
                    "lambdarank_truncation_level": 0,
                },
            )
        ]

        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            return type(
                "Result",
                (),
                {
                    "test_scored": [
                        {**row, "model_score": float(row["factor"])}
                        for row in test_rows
                    ]
                },
            )()

        with patch(
            "scripts.ml.controlled_rerank_diagnostics.train_model_result",
            side_effect=fake_train_model_result,
        ) as train_model_result:
            predictions = rolling_oof_predictions(
                rows,
                configs,
                rolling_train_dates=2,
                rolling_test_dates=1,
                rolling_folds=2,
            )

        self.assertEqual(train_model_result.call_count, 2)
        self.assertEqual([(row["fold"], row["date"], row["code"]) for row in predictions], [(1, "2026-01-03", "c"), (2, "2026-01-05", "e")])
        self.assertEqual([row["main_score"] for row in predictions], [3.0, 5.0])
        self.assertEqual([row["main_rank"] for row in predictions], [1, 1])


if __name__ == "__main__":
    unittest.main()
