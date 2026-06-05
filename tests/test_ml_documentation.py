import json
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MlDocumentationTests(unittest.TestCase):
    def test_model_maintenance_reference_uses_method_placeholders(self):
        reference = (
            PROJECT_ROOT
            / ".agents"
            / "skills"
            / "model-maintenance"
            / "references"
            / "model-maintenance.md"
        ).read_text(encoding="utf-8")

        self.assertIn("<runtime>/candidates/<date>.<method>.json", reference)
        self.assertIn("<runtime>/select/<date>.<method>/run.json", reference)
        self.assertNotIn("<runtime>/candidates/<date>.b2.json", reference)
        self.assertNotIn("<runtime>/select/<date>.b2/", reference)

    def test_roadmap_names_training_scripts_method_neutrally(self):
        roadmap = (PROJECT_ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")

        self.assertNotIn("当前 b2 LightGBM 训练和维护脚本", roadmap)
        self.assertNotIn("### P7: b2 LightGBM 训练/维护脚本", roadmap)
        self.assertIn("### P7: LightGBM 训练/维护脚本", roadmap)

    def test_model_fixture_metadata_references_existing_feature_manifest(self):
        metadata_path = PROJECT_ROOT / "tests" / "fixtures" / "b2_model" / "model_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        feature_manifest = metadata.get("feature_manifest")
        self.assertIsInstance(feature_manifest, str)
        self.assertTrue((PROJECT_ROOT / feature_manifest).exists())

    def test_model_maintenance_docs_do_not_require_baseline_evaluator(self):
        paths = [
            PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "SKILL.md",
            PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "references" / "model-maintenance.md",
            PROJECT_ROOT / "docs" / "roadmap.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertNotIn("evaluate_rank_baseline.py", combined)
        self.assertNotIn("same-window baseline", combined)
        self.assertNotIn("baseline_compare", combined)
        self.assertNotIn("模型平均表现不优于", combined)

    def test_dataset_builder_does_not_recompute_training_factors_in_python(self):
        source = (PROJECT_ROOT / "scripts" / "ml" / "build_rank_dataset.py").read_text(encoding="utf-8")

        self.assertNotIn("def context_features", source)
        self.assertNotIn("def compute_macd_lines", source)
        self.assertNotIn("def compute_zx_lines", source)
        self.assertNotIn("def fetch_indicator_rows", source)
        self.assertNotIn("recompute_context", source)

    def test_model_maintenance_shell_entry_exposes_expected_commands(self):
        script = PROJECT_ROOT / "scripts" / "model_maintenance.sh"
        completed = subprocess.run(
            ["bash", str(script), "help"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("status", completed.stdout)
        self.assertIn("archives", completed.stdout)
        self.assertIn("promote", completed.stdout)
        self.assertIn("switch", completed.stdout)


if __name__ == "__main__":
    unittest.main()
