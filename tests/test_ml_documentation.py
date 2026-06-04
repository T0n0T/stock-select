import json
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


if __name__ == "__main__":
    unittest.main()
