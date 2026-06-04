import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ml.export_lgbm_scores import (
    assign_model_ranks,
    export_rows,
    export_scores,
    resolve_default_paths,
)


class FakeModel:
    def save_model(self, path):
        Path(path).write_text("tree\n", encoding="utf-8")


class LgbmScoreExportTest(unittest.TestCase):
    def test_default_paths_are_method_scoped(self):
        paths = resolve_default_paths("b1")

        self.assertIn("diagnostics/ml/b1", str(paths["output"]))
        self.assertEqual(paths["model_output_dir"].name, "model")
        self.assertEqual(paths["dataset"].name, "rank_dataset.csv")

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
                json.dumps({"numeric_features": ["close_to_zxdkx_pct"], "categorical_features": ["env"]}),
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
                        "feature_names": ["close_to_zxdkx_pct", "env=weak", "env=strong"],
                        "lightgbm_feature_names": ["close_to_zxdkx_pct", "env_weak", "env_strong"],
                        "category_levels": {"env": ["weak", "strong"]},
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
                    label_column="rank_label_3d",
                )

            metadata = json.loads((artifact_dir / "model_metadata.json").read_text(encoding="utf-8"))
            self.assertTrue((artifact_dir / "model.txt").exists())
            self.assertEqual(metadata["feature_names"], ["close_to_zxdkx_pct", "env=weak", "env=strong"])
            self.assertEqual(metadata["categorical_levels"], {"env": ["weak", "strong"]})
            self.assertEqual(metadata["label_column"], "rank_label_3d")
            self.assertEqual(summary["model_artifacts"]["model"], str(artifact_dir / "model.txt"))


if __name__ == "__main__":
    unittest.main()
