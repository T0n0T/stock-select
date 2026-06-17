import unittest
from pathlib import Path
import json
import tempfile
from unittest.mock import patch

from ml.scoring.score_blends import (
    blend_model_scores,
    evaluate_blended_score_sets,
    rolling_scores_for_trial,
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

    def test_rolling_scores_for_trial_restores_full_lightgbm_params(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "1", "factor": "1"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "2", "factor": "2"},
            {"date": "2026-01-03", "code": "c", "rank_label_3d": "3", "factor": "3"},
            {"date": "2026-01-04", "code": "d", "rank_label_3d": "0", "factor": "4"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            trial_dir = Path(temp_dir) / "trial"
            trial_dir.mkdir()
            (trial_dir / "feature_manifest.json").write_text(
                json.dumps({"numeric_features": ["factor"], "categorical_features": []}),
                encoding="utf-8",
            )
            (trial_dir / "lgbm_rank_report_raw_numeric.json").write_text(
                json.dumps(
                    {
                        "model_params": {
                            "num_leaves": 5,
                            "min_data_in_leaf": 2,
                            "num_boost_round": 7,
                            "learning_rate": 0.04,
                            "boosting_type": "dart",
                            "bagging_fraction": 0.72,
                            "bagging_freq": 3,
                            "feature_fraction": 0.83,
                            "lambda_l1": 0.11,
                            "lambda_l2": 0.22,
                            "min_gain_to_split": 0.33,
                            "num_threads": 2,
                            "label_gain": [0, 1, 5, 15],
                            "lambdarank_truncation_level": 6,
                            "eval_at": [3, 5],
                            "early_stopping_rounds": 9,
                            "seed": 31,
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch("ml.scoring.score_blends.train_model") as train_model:
                train_model.return_value = (
                    [],
                    [{"date": "2026-01-03", "code": "c", "model_score": 0.1, "ret3": 1, "ret5": 1}],
                    [],
                    1,
                )
                rolling_scores_for_trial(
                    rows,
                    trial_dir=trial_dir,
                    method="b2",
                    rolling_train_dates=2,
                    rolling_test_dates=1,
                    rolling_folds=1,
                )

        kwargs = train_model.call_args.kwargs
        self.assertEqual(kwargs["boosting_type"], "dart")
        self.assertEqual(kwargs["bagging_fraction"], 0.72)
        self.assertEqual(kwargs["bagging_freq"], 3)
        self.assertEqual(kwargs["feature_fraction"], 0.83)
        self.assertEqual(kwargs["lambda_l1"], 0.11)
        self.assertEqual(kwargs["lambda_l2"], 0.22)
        self.assertEqual(kwargs["min_gain_to_split"], 0.33)
        self.assertEqual(kwargs["eval_at"], [3, 5])
        self.assertEqual(kwargs["early_stopping_rounds"], 9)
        self.assertEqual(kwargs["seed"], 31)


if __name__ == "__main__":
    unittest.main()
