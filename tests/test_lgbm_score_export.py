import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ml.export_lgbm_scores import (
    assign_model_ranks,
    export_rows,
    export_scores,
    main,
    resolve_default_paths,
)
from scripts.ml import build_rank_dataset as rank_dataset_schema


class FakeModel:
    def save_model(self, path):
        Path(path).write_text("tree\n", encoding="utf-8")


class LgbmScoreExportTest(unittest.TestCase):
    def test_default_paths_are_method_scoped(self):
        paths = resolve_default_paths("b1")

        self.assertIn("diagnostics/ml/b1", str(paths["output"]))
        self.assertEqual(paths["model_output_dir"].name, "model")
        self.assertEqual(paths["dataset"].name, "rank_dataset.csv")

    def test_default_paths_follow_explicit_model_output_dir_for_trial_exports(self):
        model_output_dir = Path("diagnostics/ml/b3/tuning/trial-001")

        paths = resolve_default_paths("b3", model_output_dir=model_output_dir)

        self.assertEqual(paths["dataset"], Path("diagnostics/ml/b3/rank_dataset.csv"))
        self.assertEqual(paths["feature_manifest"], model_output_dir / "feature_manifest.json")
        self.assertEqual(paths["output"], model_output_dir / "lgbm_scores.csv")
        self.assertEqual(paths["summary_output"], model_output_dir / "lgbm_scores_summary.json")
        self.assertEqual(paths["model_output_dir"], model_output_dir)

    def test_main_uses_trial_report_training_params_for_model_output_dir(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            model_output_dir = Path(temp_dir) / "trial-001"
            model_output_dir.mkdir()
            (model_output_dir / "lgbm_rank_report_raw_plus_signal.json").write_text(
                json.dumps(
                    {
                        "label_column": "ret3_ge5_label",
                        "model_params": {
                            "num_leaves": 5,
                            "min_data_in_leaf": 240,
                            "num_boost_round": 60,
                            "learning_rate": 0.05,
                            "num_threads": 16,
                            "label_gain": [0, 1, 5, 15],
                            "lambdarank_truncation_level": 8,
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("scripts.ml.export_lgbm_scores.export_scores", return_value={"ok": True}) as export_scores:
                rc = main(["--method", "b2", "--model-output-dir", str(model_output_dir)])

        self.assertEqual(rc, 0)
        kwargs = export_scores.call_args.kwargs
        self.assertEqual(kwargs["num_leaves"], 5)
        self.assertEqual(kwargs["min_data_in_leaf"], 240)
        self.assertEqual(kwargs["num_threads"], 16)
        self.assertEqual(kwargs["label_column"], "ret3_ge5_label")
        self.assertEqual(kwargs["label_gain"], [0, 1, 5, 15])
        self.assertEqual(kwargs["lambdarank_truncation_level"], 8)

    def test_assign_model_ranks_are_date_local_and_score_descending(self):
        rows = [
            {"date": "2026-03-02", "code": "b", "model_score": 0.2},
            {"date": "2026-03-02", "code": "a", "model_score": 0.2},
            {"date": "2026-03-02", "code": "c", "model_score": 0.1},
            {"date": "2026-03-03", "code": "d", "model_score": 0.5},
        ]

        ranked = assign_model_ranks(rows)

        ranks = {(row["date"], row["code"]): row["model_rank"] for row in ranked}
        self.assertEqual(ranks[("2026-03-02", "a")], 1)
        self.assertEqual(ranks[("2026-03-02", "b")], 2)
        self.assertEqual(ranks[("2026-03-02", "c")], 3)
        self.assertEqual(ranks[("2026-03-03", "d")], 1)

    def test_export_rows_uses_stable_contract_columns(self):
        rows = [{"date": "2026-03-02", "code": "a", "model_score": 0.12345678901}]

        exported = export_rows(rows)

        self.assertEqual(
            exported,
            [{"date": "2026-03-02", "code": "a", "model_score": "0.1234567890", "model_rank": "1"}],
        )

    def test_export_scores_persists_current_runtime_metadata_shape(self):
        import csv
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["date", "code", "rank_label_3d", "close_to_zxdkx_pct", "env"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "1", "close_to_zxdkx_pct": "1", "env": "weak"},
                        {"date": "2026-03-01", "code": "b", "rank_label_3d": "2", "close_to_zxdkx_pct": "2", "env": "strong"},
                    ]
                )
            feature_manifest = root / "feature_manifest.json"
            feature_manifest.write_text(
                json.dumps(
                    {
                        "numeric_features": ["close_to_zxdkx_pct"],
                        "categorical_features": ["env"],
                        "categorical_levels": {"env": ["weak", "strong", "neutral"]},
                    }
                ),
                encoding="utf-8",
            )
            artifact_dir = root / "model"

            with patch("scripts.ml.export_lgbm_scores.train_model_result") as train_model_result:
                train_model_result.return_value = type(
                    "Result",
                    (),
                    {
                        "train_scored": [],
                        "test_scored": [{"date": "2026-03-01", "code": "b", "model_score": 0.5}],
                        "top_features": [{"feature": "close_to_zxdkx_pct", "importance": 1}],
                        "feature_count": 3,
                        "model": FakeModel(),
                        "feature_names": ["close_to_zxdkx_pct", "env=weak", "env=strong", "env=neutral"],
                        "lightgbm_feature_names": ["close_to_zxdkx_pct", "env_weak", "env_strong", "env_neutral"],
                        "category_levels": {"env": ["weak", "strong", "neutral"]},
                    },
                )()

                summary = export_scores(
                    dataset=dataset,
                    feature_manifest=feature_manifest,
                    output=root / "scores.csv",
                    summary_output=root / "summary.json",
                    model_output_dir=artifact_dir,
                    train_end_exclusive="2026-03-01",
                    score_start="2026-03-01",
                    score_end="2026-03-31",
                    num_leaves=9,
                    min_data_in_leaf=120,
                    num_boost_round=60,
                    learning_rate=0.05,
                    num_threads=1,
                    label_gain=[0, 1, 5, 15],
                    lambdarank_truncation_level=8,
                    label_column="rank_label_3d",
                )

            metadata = json.loads((artifact_dir / "model_metadata.json").read_text(encoding="utf-8"))
            self.assertTrue((artifact_dir / "model.txt").exists())
            self.assertEqual(
                train_model_result.call_args.kwargs["fixed_categorical_levels"],
                {"env": ["weak", "strong", "neutral"]},
            )
            self.assertEqual(train_model_result.call_args.kwargs["label_gain"], [0, 1, 5, 15])
            self.assertEqual(train_model_result.call_args.kwargs["lambdarank_truncation_level"], 8)
            self.assertEqual(metadata["feature_names"], ["close_to_zxdkx_pct", "env=weak", "env=strong", "env=neutral"])
            self.assertEqual(metadata["categorical_levels"], {"env": ["weak", "strong", "neutral"]})
            self.assertEqual(metadata["label_column"], "rank_label_3d")
            self.assertEqual(metadata["model_params"]["label_gain"], [0, 1, 5, 15])
            self.assertEqual(metadata["model_params"]["lambdarank_truncation_level"], 8)
            self.assertEqual(summary["model_artifacts"]["model"], str(artifact_dir / "model.txt"))

    def test_export_scores_keeps_unlabeled_score_rows(self):
        import csv
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["date", "code", "rank_label_5d", "ret5", "close_to_zxdkx_pct"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "date": "2026-05-29",
                            "code": "a",
                            "rank_label_5d": "3",
                            "ret5": "6",
                            "close_to_zxdkx_pct": "1",
                        },
                        {
                            "date": "2026-06-05",
                            "code": "b",
                            "rank_label_5d": "",
                            "ret5": "",
                            "close_to_zxdkx_pct": "2",
                        },
                    ]
                )
            feature_manifest = root / "feature_manifest.json"
            feature_manifest.write_text(
                json.dumps({"numeric_features": ["close_to_zxdkx_pct"], "categorical_features": []}),
                encoding="utf-8",
            )

            with patch("scripts.ml.export_lgbm_scores.train_model_result") as train_model_result:
                train_model_result.return_value = type(
                    "Result",
                    (),
                    {
                        "train_scored": [],
                        "test_scored": [{"date": "2026-06-05", "code": "b", "model_score": 0.5}],
                        "top_features": [],
                        "feature_count": 1,
                        "model": FakeModel(),
                        "feature_names": ["close_to_zxdkx_pct"],
                        "lightgbm_feature_names": ["close_to_zxdkx_pct"],
                        "category_levels": {},
                    },
                )()

                summary = export_scores(
                    dataset=dataset,
                    feature_manifest=feature_manifest,
                    output=root / "scores.csv",
                    summary_output=root / "summary.json",
                    model_output_dir=root / "model",
                    train_end_exclusive="2026-06-01",
                    score_start="2026-06-05",
                    score_end="2026-06-05",
                    num_leaves=7,
                    min_data_in_leaf=80,
                    num_boost_round=100,
                    learning_rate=0.05,
                    num_threads=1,
                    label_column="rank_label_5d",
                )

            score_rows = train_model_result.call_args.args[1]
            self.assertEqual([row["code"] for row in score_rows], ["b"])
            self.assertEqual(summary["score_row_count"], 1)
            self.assertEqual(summary["score_start"], "2026-06-05")
            self.assertEqual(summary["score_end"], "2026-06-05")

    def test_export_scores_uses_method_registered_feature_manifest_columns(self):
        import csv
        import json
        import tempfile

        original = rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"]
        try:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = [*original, "b3_only_raw_factor"]
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                dataset = root / "dataset.csv"
                with dataset.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(
                        handle,
                        fieldnames=["date", "code", "rank_label_3d", "close_to_zxdkx_pct", "b3_only_raw_factor"],
                    )
                    writer.writeheader()
                    writer.writerows(
                        [
                            {
                                "date": "2026-01-01",
                                "code": "a",
                                "rank_label_3d": "1",
                                "close_to_zxdkx_pct": "1",
                                "b3_only_raw_factor": "11",
                            },
                            {
                                "date": "2026-03-01",
                                "code": "b",
                                "rank_label_3d": "2",
                                "close_to_zxdkx_pct": "2",
                                "b3_only_raw_factor": "12",
                            },
                        ]
                    )
                feature_manifest = root / "feature_manifest.json"
                feature_manifest.write_text(
                    json.dumps(
                        {
                            "numeric_features": ["close_to_zxdkx_pct", "b3_only_raw_factor"],
                            "categorical_features": [],
                        }
                    ),
                    encoding="utf-8",
                )

                with patch("scripts.ml.export_lgbm_scores.train_model_result") as train_model_result:
                    train_model_result.return_value = type(
                        "Result",
                        (),
                        {
                            "train_scored": [],
                            "test_scored": [{"date": "2026-03-01", "code": "b", "model_score": 0.5}],
                            "top_features": [],
                            "feature_count": 2,
                            "model": FakeModel(),
                            "feature_names": ["close_to_zxdkx_pct", "b3_only_raw_factor"],
                            "lightgbm_feature_names": ["close_to_zxdkx_pct", "b3_only_raw_factor"],
                            "category_levels": {},
                        },
                    )()

                    export_scores(
                        dataset=dataset,
                        feature_manifest=feature_manifest,
                        output=root / "scores.csv",
                        summary_output=root / "summary.json",
                        model_output_dir=root / "model",
                        train_end_exclusive="2026-03-01",
                        score_start="2026-03-01",
                        score_end="2026-03-31",
                        num_leaves=9,
                        min_data_in_leaf=120,
                        num_boost_round=60,
                        learning_rate=0.05,
                        num_threads=1,
                        label_column="rank_label_3d",
                        method="b3",
                    )

            self.assertEqual(
                train_model_result.call_args.kwargs["numeric_columns"],
                ["close_to_zxdkx_pct", "b3_only_raw_factor"],
            )
        finally:
            rank_dataset_schema.METHOD_RAW_FACTOR_COLUMNS["b3"] = original


if __name__ == "__main__":
    unittest.main()
