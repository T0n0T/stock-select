import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml.training.lgbm_ranker import TrainedModelResult
from ml.training.rf_diagnostics import RandomForestThresholdError
from ml.training.train_lgbm_rank import train_and_report


class LgbmTrainingReportTest(unittest.TestCase):
    def write_dataset(
        self,
        path: Path,
        *,
        fieldnames: list[str],
        rows: list[dict[str, str]],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def basic_rows(self) -> list[dict[str, str]]:
        return [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
            {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "1"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0"},
        ]

    def dummy_model_result(self, train_rows, test_rows, **_kwargs):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        return TrainedModelResult(
            train_scored=[{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in train_rows],
            test_scored=[{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in test_rows],
            top_features=[{"feature": "x", "importance": 1}],
            feature_count=1,
            model=DummyModel(),
            feature_names=["x"],
            lightgbm_feature_names=["x"],
            category_levels={},
            categorical_code_maps={},
        )

    def test_train_report_writes_and_embeds_random_forest_diagnostics(self):
        rf_payload = {
            "enabled": True,
            "status": "passed",
            "label_column": "rank_label_3d",
            "feature_count": 1,
            "numeric_feature_count": 1,
            "categorical_feature_count": 0,
            "params": {"n_estimators": 300},
            "thresholds": {"min_oob_score": None, "min_test_rank_ic_ret3": None},
            "metrics": {"test": {"rank_ic_ret3": 0.12, "top3_ret3_positive_rate": 66.7}, "train": {}},
            "oob_score": 0.61,
            "accuracy": {"train": 0.8, "test": 0.7},
            "top_features": [{"feature": "x", "importance": 0.9}],
            "low_importance_features": [],
            "output_paths": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            self.write_dataset(dataset, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"], rows=self.basic_rows())
            output_dir = root / "model"

            with patch("ml.training.train_lgbm_rank.run_random_forest_diagnostics", return_value=rf_payload):
                with patch("ml.training.train_lgbm_rank.train_model_result", side_effect=self.dummy_model_result):
                    report = train_and_report(
                        dataset,
                        output_dir,
                        test_ratio=0.5,
                        feature_set="raw_numeric",
                        num_leaves=5,
                        min_data_in_leaf=1,
                        num_boost_round=1,
                        learning_rate=0.1,
                        label_column="rank_label_3d",
                        method="b2",
                    )

            rf_json = json.loads((output_dir / "rf_feature_diagnostics.json").read_text(encoding="utf-8"))
            rf_markdown = (output_dir / "rf_feature_diagnostics.md").read_text(encoding="utf-8")
            persisted = json.loads((output_dir / "lgbm_rank_report_raw_numeric.json").read_text(encoding="utf-8"))

        self.assertEqual(rf_json["output_paths"]["json"], str(output_dir / "rf_feature_diagnostics.json"))
        self.assertIn("# random forest factor diagnostics", rf_markdown)
        self.assertEqual(report["rf_diagnostics"]["status"], "passed")
        self.assertEqual(report["rf_diagnostics"]["oob_score"], 0.61)
        self.assertEqual(report["rf_diagnostics"]["top_features"], [{"feature": "x", "importance": 0.9}])
        self.assertEqual(persisted["rf_diagnostics"]["path"], str(output_dir / "rf_feature_diagnostics.json"))

    def test_random_forest_threshold_failure_writes_report_and_stops_lgbm(self):
        rf_payload = {
            "enabled": True,
            "status": "passed",
            "label_column": "rank_label_3d",
            "feature_count": 1,
            "numeric_feature_count": 1,
            "categorical_feature_count": 0,
            "params": {},
            "thresholds": {"min_oob_score": 0.7, "min_test_rank_ic_ret3": None},
            "metrics": {"test": {"rank_ic_ret3": 0.03}, "train": {}},
            "oob_score": 0.61,
            "accuracy": {"train": 0.8, "test": 0.7},
            "top_features": [{"feature": "x", "importance": 0.9}],
            "low_importance_features": [],
            "output_paths": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            self.write_dataset(dataset, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"], rows=self.basic_rows())
            output_dir = root / "model"

            with patch("ml.training.train_lgbm_rank.run_random_forest_diagnostics", return_value=rf_payload):
                with patch("ml.training.train_lgbm_rank.train_model_result") as train_lgbm:
                    with self.assertRaisesRegex(RandomForestThresholdError, "oob_score"):
                        train_and_report(
                            dataset,
                            output_dir,
                            test_ratio=0.5,
                            feature_set="raw_numeric",
                            num_leaves=5,
                            min_data_in_leaf=1,
                            num_boost_round=1,
                            learning_rate=0.1,
                            label_column="rank_label_3d",
                            rf_min_oob_score=0.7,
                            method="b2",
                        )

                    train_lgbm.assert_not_called()

            self.assertTrue((output_dir / "rf_feature_diagnostics.json").exists())
            self.assertFalse((output_dir / "model.txt").exists())

    def test_train_report_can_skip_random_forest_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            self.write_dataset(dataset, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"], rows=self.basic_rows())

            with patch("ml.training.train_lgbm_rank.run_random_forest_diagnostics") as rf_run:
                with patch("ml.training.train_lgbm_rank.train_model_result", side_effect=self.dummy_model_result):
                    report = train_and_report(
                        dataset,
                        root / "model",
                        test_ratio=0.5,
                        feature_set="raw_numeric",
                        num_leaves=5,
                        min_data_in_leaf=1,
                        num_boost_round=1,
                        learning_rate=0.1,
                        label_column="rank_label_3d",
                        rf_diagnostics=False,
                        method="b2",
                    )

        rf_run.assert_not_called()
        self.assertEqual(
            report["rf_diagnostics"],
            {
                "enabled": False,
                "path": None,
                "status": "skipped",
                "oob_score": None,
                "metrics": {"test": {}},
                "top_features": [],
                "low_importance_feature_count": 0,
            },
        )

    def test_train_and_report_persists_lambdarank_truncation_level(self):
        def fake_train_model_result(train_rows, test_rows, **kwargs):
            self.assertEqual(kwargs["label_gain"], [0, 1, 5, 15])
            self.assertEqual(kwargs["lambdarank_truncation_level"], 8)
            return self.dummy_model_result(train_rows, test_rows, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            rows = [
                {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                {"date": "2026-01-01", "code": "b", "rank_label_3d": "1", "ret3": "-1", "ret5": "0", "x": "2"},
                {"date": "2026-01-02", "code": "a", "rank_label_3d": "2", "ret3": "7", "ret5": "4", "x": "3"},
                {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "4"},
            ]
            self.write_dataset(dataset, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"], rows=rows)
            output_dir = root / "model"

            with patch("ml.training.train_lgbm_rank.train_model_result", side_effect=fake_train_model_result):
                report = train_and_report(
                    dataset,
                    output_dir,
                    test_ratio=0.5,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=120,
                    num_boost_round=10,
                    learning_rate=0.05,
                    label_column="ret3_ge5_label",
                    label_gain=[0, 1, 5, 15],
                    lambdarank_truncation_level=8,
                    method="b2",
                    rf_diagnostics=False,
                )

            metadata = json.loads((output_dir / "model_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(report["model_params"]["label_gain"], [0, 1, 5, 15])
        self.assertEqual(report["model_params"]["lambdarank_truncation_level"], 8)
        self.assertEqual(metadata["model_params"]["label_gain"], [0, 1, 5, 15])
        self.assertEqual(metadata["model_params"]["lambdarank_truncation_level"], 8)

    def test_train_and_report_writes_model_artifacts_when_rolling_is_enabled(self):
        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            result = self.dummy_model_result(train_rows, test_rows)
            result.feature_names = ["close_to_zxdkx_pct"]
            result.lightgbm_feature_names = ["close_to_zxdkx_pct"]
            result.category_levels = {"env": ["weak", "strong"]}
            result.categorical_code_maps = {"env": {"weak": 0, "strong": 1}}
            return result

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            rows = [
                {"date": "2026-01-01", "code": "a", "env": "weak", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "close_to_zxdkx_pct": "1"},
                {"date": "2026-01-01", "code": "b", "env": "strong", "rank_label_3d": "1", "ret3": "-1", "ret5": "0", "close_to_zxdkx_pct": "2"},
                {"date": "2026-01-02", "code": "a", "env": "weak", "rank_label_3d": "2", "ret3": "3", "ret5": "4", "close_to_zxdkx_pct": "3"},
                {"date": "2026-01-02", "code": "b", "env": "strong", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "close_to_zxdkx_pct": "4"},
                {"date": "2026-01-03", "code": "a", "env": "weak", "rank_label_3d": "3", "ret3": "8", "ret5": "9", "close_to_zxdkx_pct": "5"},
                {"date": "2026-01-03", "code": "b", "env": "strong", "rank_label_3d": "1", "ret3": "1", "ret5": "2", "close_to_zxdkx_pct": "6"},
            ]
            self.write_dataset(dataset, fieldnames=["date", "code", "env", "rank_label_3d", "ret3", "ret5", "close_to_zxdkx_pct"], rows=rows)
            output_dir = root / "model"

            with patch("ml.training.train_lgbm_rank.train_model_result", side_effect=fake_train_model_result):
                report = train_and_report(
                    dataset,
                    output_dir,
                    test_ratio=0.34,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=120,
                    num_boost_round=10,
                    learning_rate=0.05,
                    rolling_folds=1,
                    rolling_train_dates=2,
                    rolling_test_dates=1,
                    label_column="rank_label_3d",
                    method="b2",
                    rf_diagnostics=False,
                )

            self.assertEqual(report["feature_count"], 1)
            self.assertTrue((output_dir / "feature_manifest.json").exists())
            self.assertTrue((output_dir / "model.txt").exists())
            metadata = json.loads((output_dir / "model_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["feature_names"], ["close_to_zxdkx_pct"])
        self.assertEqual(metadata["numeric_columns"], ["close_to_zxdkx_pct"])
        self.assertEqual(metadata["categorical_columns"], [])
        self.assertEqual(metadata["label_column"], "rank_label_3d")

    def test_train_and_report_records_lgbm_ranking_tuning_params(self):
        captured_kwargs = {}

        def fake_train_model_result(train_rows, test_rows, **kwargs):
            captured_kwargs.update(kwargs)
            return self.dummy_model_result(train_rows, test_rows, **kwargs)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            rows = [
                {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                {"date": "2026-01-01", "code": "b", "rank_label_3d": "1", "ret3": "2", "ret5": "1", "x": "2"},
                {"date": "2026-01-02", "code": "a", "rank_label_3d": "2", "ret3": "3", "ret5": "4", "x": "3"},
                {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "4"},
            ]
            self.write_dataset(dataset, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"], rows=rows)
            output_dir = root / "model"

            with patch("ml.training.train_lgbm_rank.train_model_result", side_effect=fake_train_model_result):
                report = train_and_report(
                    dataset,
                    output_dir,
                    test_ratio=0.5,
                    feature_set="raw_numeric",
                    num_leaves=5,
                    min_data_in_leaf=120,
                    num_boost_round=10,
                    learning_rate=0.05,
                    boosting_type="dart",
                    bagging_fraction=0.8,
                    feature_fraction=0.7,
                    lambda_l1=1.0,
                    lambda_l2=2.0,
                    early_stopping_rounds=30,
                    top_k=[3, 5],
                    eval_at=[5, 10],
                    label_column="rank_label_3d",
                    method="b2",
                    rf_diagnostics=False,
                )

            metadata = json.loads((output_dir / "model_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(captured_kwargs["boosting_type"], "dart")
        self.assertEqual(captured_kwargs["bagging_fraction"], 0.8)
        self.assertEqual(captured_kwargs["feature_fraction"], 0.7)
        self.assertEqual(captured_kwargs["lambda_l1"], 1.0)
        self.assertEqual(captured_kwargs["lambda_l2"], 2.0)
        self.assertEqual(captured_kwargs["early_stopping_rounds"], 30)
        self.assertEqual(captured_kwargs["eval_at"], [5, 10])
        self.assertEqual(report["model_params"]["boosting_type"], "dart")
        self.assertEqual(report["model_params"]["bagging_fraction"], 0.8)
        self.assertEqual(report["model_params"]["feature_fraction"], 0.7)
        self.assertEqual(report["model_params"]["lambda_l1"], 1.0)
        self.assertEqual(report["model_params"]["lambda_l2"], 2.0)
        self.assertEqual(report["model_params"]["early_stopping_rounds"], 30)
        self.assertEqual(report["top_k"], [3, 5])
        self.assertEqual(report["eval_at"], [5, 10])
        self.assertEqual(metadata["model_params"]["boosting_type"], "dart")
        self.assertEqual(metadata["model_params"]["early_stopping_rounds"], 30)


if __name__ == "__main__":
    unittest.main()
