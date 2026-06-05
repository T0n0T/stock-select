import json
import tempfile
import unittest
from pathlib import Path

from scripts.ml.promote_lgbm_model import (
    describe_current_model,
    list_archived_models,
    promote_model,
    resolve_default_target_dir,
    rollback_model,
    validate_model_artifacts,
)


def write_candidate_model(path: Path, *, report: dict | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.txt").write_text("tree\n", encoding="utf-8")
    metadata = {
        "feature_manifest": "diagnostics/ml/b2/model/feature_manifest.json",
        "train_start": "2026-01-01",
        "train_end": "2026-03-31",
        "score_start": "2026-04-01",
        "score_end": "2026-05-31",
        "model_params": {"num_leaves": 9, "learning_rate": 0.05},
        "numeric_columns": ["close_to_zxdkx_pct"],
        "categorical_columns": ["env"],
        "categorical_levels": {"env": ["weak", "strong"]},
        "one_hot_levels": {"env": ["env=weak", "env=strong"]},
        "feature_names": ["close_to_zxdkx_pct", "env=weak", "env=strong"],
        "lightgbm_feature_names": ["close_to_zxdkx_pct", "env_weak", "env_strong"],
        "label_column": "rank_label_3d",
    }
    (path / "model_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if report is not None:
        (path / "lgbm_rank_report_raw_numeric.json").write_text(json.dumps(report), encoding="utf-8")


def passing_report() -> dict:
    return {
        "dataset": "diagnostics/ml/b2/rank_dataset.csv",
        "feature_manifest": "diagnostics/ml/b2/model/feature_manifest.json",
        "model_params": {"num_leaves": 9},
        "rolling_summary": {
            "test_avg": {
                "top3_ret3_ge_5_rate": 31.0,
                "top3_ret3_ge_5_capture_rate": 16.0,
                "rank_ic_ret3": 0.08,
            }
        },
        "rolling_folds": [{"fold": 1}],
    }


class LgbmModelPromotionTest(unittest.TestCase):
    def test_default_target_dir_uses_dotenv_runtime_root_and_current_model_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            dotenv = root / ".env"
            dotenv.write_text(f"STOCK_SELECT_RUNTIME_ROOT={runtime}\n", encoding="utf-8")

            target = resolve_default_target_dir(method="b1", dotenv_path=dotenv, env_runtime_root="/tmp/ignored-shell-runtime")

        self.assertEqual(target, runtime / "models" / "b1")

    def test_default_target_dir_requires_runtime_root_without_home_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv = Path(temp_dir) / ".env"

            with self.assertRaisesRegex(ValueError, "STOCK_SELECT_RUNTIME_ROOT"):
                resolve_default_target_dir(dotenv_path=dotenv, env_runtime_root=None)

    def test_validate_model_artifacts_accepts_complete_candidate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "candidate"
            write_candidate_model(candidate, report=passing_report())

            summary = validate_model_artifacts(candidate)

            self.assertEqual(summary["feature_count"], 3)
            self.assertEqual(summary["label_column"], "rank_label_3d")
            self.assertEqual(summary["decision"], "allow")

    def test_promote_archives_existing_current_model_and_replaces_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = root / "candidate"
            target = root / "runtime" / "models" / "b2"
            write_candidate_model(candidate, report=passing_report())
            write_candidate_model(target)
            (target / "model.txt").write_text("old\n", encoding="utf-8")

            summary = promote_model(candidate, target, now="20260603T010203Z")

            self.assertEqual((target / "model.txt").read_text(encoding="utf-8"), "tree\n")
            model_card = json.loads((target / "model_card.json").read_text(encoding="utf-8"))
            self.assertEqual(model_card["mode"], "promote")
            self.assertEqual(model_card["promotion_decision"], "allow")
            archive_path = Path(summary["archive_path"])
            self.assertTrue((archive_path / "model.txt").exists())
            self.assertEqual((archive_path / "model.txt").read_text(encoding="utf-8"), "old\n")
            self.assertEqual(archive_path, target.parent / "archive" / "20260603T010203Z")

    def test_promote_dry_run_does_not_modify_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = root / "candidate"
            target = root / "runtime" / "models" / "b2"
            write_candidate_model(candidate, report=passing_report())
            write_candidate_model(target)
            (target / "model.txt").write_text("old\n", encoding="utf-8")

            summary = promote_model(candidate, target, dry_run=True, now="20260603T010203Z")

            self.assertEqual(summary["mode"], "dry-run")
            self.assertEqual((target / "model.txt").read_text(encoding="utf-8"), "old\n")
            self.assertFalse((target.parent / "archive" / "20260603T010203Z").exists())

    def test_incomplete_candidate_fails_before_promotion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "candidate"
            candidate.mkdir()
            (candidate / "model.txt").write_text("tree\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "model_metadata.json"):
                validate_model_artifacts(candidate)

    def test_rollback_restores_archive_to_current_target_and_archives_current(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "runtime" / "models" / "b2"
            archive = target.parent / "archive" / "20260601T000000Z"
            write_candidate_model(target)
            write_candidate_model(archive)
            (target / "model.txt").write_text("current\n", encoding="utf-8")
            (archive / "model.txt").write_text("previous\n", encoding="utf-8")

            summary = rollback_model(target, "20260601T000000Z", now="20260603T010203Z")

            self.assertEqual((target / "model.txt").read_text(encoding="utf-8"), "previous\n")
            self.assertTrue((target.parent / "archive" / "rollback-current-20260603T010203Z" / "model.txt").exists())
            self.assertEqual(summary["rollback_version"], "20260601T000000Z")

    def test_describe_current_model_reads_active_target_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "runtime" / "models" / "b2"
            write_candidate_model(target, report=passing_report())

            summary = describe_current_model(target)

            self.assertEqual(summary["mode"], "describe-current")
            self.assertEqual(summary["validation"]["feature_count"], 3)
            self.assertEqual(summary["validation"]["label_column"], "rank_label_3d")
            self.assertEqual(summary["target"], str(target))

    def test_list_archived_models_returns_newest_first_with_validation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "runtime" / "models" / "b2"
            archive_root = target.parent / "archive"
            old_a = archive_root / "20260601T000000Z"
            old_b = archive_root / "20260602T000000Z"
            write_candidate_model(old_a, report=passing_report())
            write_candidate_model(old_b, report=passing_report())

            rows = list_archived_models(target)

            self.assertEqual([row["version"] for row in rows], ["20260602T000000Z", "20260601T000000Z"])
            self.assertEqual(rows[0]["validation"]["feature_count"], 3)
            self.assertEqual(rows[0]["validation"]["label_column"], "rank_label_3d")


if __name__ == "__main__":
    unittest.main()
