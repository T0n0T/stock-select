import json
import os
import subprocess
import tempfile
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
        self.assertIn("<runtime>/models/archive/<method>/<version>/", reference)
        self.assertNotIn("<runtime>/candidates/<date>.b2.json", reference)
        self.assertNotIn("<runtime>/select/<date>.b2/", reference)
        self.assertNotIn("<runtime>/models/archive/<version>/", reference)

    def test_model_docs_name_training_scripts_method_neutrally(self):
        docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PROJECT_ROOT / "docs" / "model.md",
                PROJECT_ROOT / "docs" / "workflow.md",
            ]
        )

        self.assertNotIn("当前 b2 LightGBM 训练和维护脚本", docs)
        self.assertNotIn("### P7: b2 LightGBM 训练/维护脚本", docs)
        self.assertIn("LightGBM", docs)

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
            PROJECT_ROOT / "docs" / "model.md",
            PROJECT_ROOT / "docs" / "workflow.md",
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
        self.assertIn("--method <method>", completed.stdout)

    def test_model_maintenance_status_prints_formatted_heading(self):
        script = PROJECT_ROOT / "scripts" / "model_maintenance.sh"
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_dir = Path(temp_dir) / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' 'LightGBM 模型维护摘要'\n"
                "printf '%s\\n' '模式: describe-current'\n"
                "printf '%s\\n' '目标: runtime/models/b3'\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                ["bash", str(script), "--method", "b3", "status"],
                check=True,
                capture_output=True,
                env=env,
                text=True,
            )

        self.assertIn("模型状态: b3", completed.stdout)
        self.assertIn("LightGBM 模型维护摘要", completed.stdout)
        self.assertIn("目标: runtime/models/b3", completed.stdout)
        self.assertRegex(completed.stdout, r"={20,}")

    def test_b2_post_rerank_rule_lives_in_b2_engine_module(self):
        run_source = (PROJECT_ROOT / "src" / "engine" / "run.rs").read_text(encoding="utf-8")
        b2_source = (PROJECT_ROOT / "src" / "engine" / "b2.rs").read_text(encoding="utf-8")

        self.assertNotIn("fn adjust_b2_cyq_post_rerank_score", run_source)
        self.assertIn("fn adjust_b2_cyq_post_rerank_score", b2_source)


if __name__ == "__main__":
    unittest.main()
