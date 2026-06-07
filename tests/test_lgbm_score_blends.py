import unittest

from scripts.ml.evaluate_lgbm_score_blends import (
    blend_model_scores,
    evaluate_blended_score_sets,
    normalized_scores_by_key,
)


class LgbmScoreBlendTest(unittest.TestCase):
    def test_normalized_scores_are_date_local_and_deterministic(self):
        rows = [
            {"date": "2026-03-02", "code": "b", "model_score": 0.2},
            {"date": "2026-03-02", "code": "a", "model_score": 0.2},
            {"date": "2026-03-02", "code": "c", "model_score": 0.1},
            {"date": "2026-03-03", "code": "d", "model_score": -1.0},
        ]

        scores = normalized_scores_by_key(rows)

        self.assertEqual(scores[("2026-03-02", "a")], 1.0)
        self.assertEqual(scores[("2026-03-02", "b")], 0.5)
        self.assertEqual(scores[("2026-03-02", "c")], 0.0)
        self.assertEqual(scores[("2026-03-03", "d")], 1.0)

    def test_blend_applies_auxiliary_weight_only_to_requested_env(self):
        base_rows = [
            {"date": "2026-03-02", "code": "a", "env": "weak", "model_score": 2.0, "ret3": "1"},
            {"date": "2026-03-02", "code": "b", "env": "weak", "model_score": 1.0, "ret3": "6"},
            {"date": "2026-03-03", "code": "c", "env": "strong", "model_score": 1.0, "ret3": "7"},
            {"date": "2026-03-03", "code": "d", "env": "strong", "model_score": 0.0, "ret3": "0"},
        ]
        aux_rows = [
            {"date": "2026-03-02", "code": "a", "env": "weak", "model_score": 0.0},
            {"date": "2026-03-02", "code": "b", "env": "weak", "model_score": 1.0},
            {"date": "2026-03-03", "code": "c", "env": "strong", "model_score": 0.0},
            {"date": "2026-03-03", "code": "d", "env": "strong", "model_score": 1.0},
        ]

        blended = blend_model_scores(
            base_rows,
            {"base": base_rows, "aux": aux_rows},
            weights={"base": 1.0, "aux": 0.75},
            apply_env="weak",
        )
        by_code = {row["code"]: row for row in blended}

        self.assertAlmostEqual(by_code["a"]["model_score"], 1.0)
        self.assertAlmostEqual(by_code["b"]["model_score"], 0.75)
        self.assertAlmostEqual(by_code["c"]["model_score"], 1.0)
        self.assertAlmostEqual(by_code["d"]["model_score"], 0.0)
        self.assertEqual(by_code["b"]["ret3"], "6")

    def test_blend_metrics_are_averaged_by_fold_when_test_dates_overlap(self):
        base_rows = [
            {"fold": 1, "date": "2026-03-02", "code": "a", "model_score": 4, "ret3": "6", "ret5": "6"},
            {"fold": 1, "date": "2026-03-02", "code": "b", "model_score": 3, "ret3": "6", "ret5": "6"},
            {"fold": 1, "date": "2026-03-02", "code": "c", "model_score": 2, "ret3": "6", "ret5": "6"},
            {"fold": 1, "date": "2026-03-02", "code": "d", "model_score": 1, "ret3": "0", "ret5": "0"},
            {"fold": 2, "date": "2026-03-02", "code": "a", "model_score": 4, "ret3": "0", "ret5": "0"},
            {"fold": 2, "date": "2026-03-02", "code": "b", "model_score": 3, "ret3": "0", "ret5": "0"},
            {"fold": 2, "date": "2026-03-02", "code": "c", "model_score": 2, "ret3": "0", "ret5": "0"},
            {"fold": 2, "date": "2026-03-02", "code": "d", "model_score": 1, "ret3": "6", "ret5": "6"},
        ]

        report = evaluate_blended_score_sets(
            {"base": base_rows, "aux": base_rows},
            weights={"base": 1.0, "aux": 0.0},
            apply_env=None,
        )

        self.assertEqual(report["metrics"]["top3_ret3_ge_5_rate"], 50.0)
        self.assertEqual([fold["metrics"]["top3_ret3_ge_5_rate"] for fold in report["folds"]], [100.0, 0.0])


if __name__ == "__main__":
    unittest.main()
