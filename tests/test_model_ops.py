import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml.cli import main


class ModelOpsTest(unittest.TestCase):
    def test_model_status_prints_active_model_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir) / "runtime"
            model_dir = runtime / "models" / "b2"
            model_dir.mkdir(parents=True)
            (model_dir / "model.txt").write_text("tree\n", encoding="utf-8")
            (model_dir / "model_metadata.json").write_text(
                json.dumps(
                    {
                        "numeric_columns": ["x"],
                        "categorical_columns": [],
                        "feature_names": ["x"],
                        "label_column": "rank_label_3d",
                    }
                ),
                encoding="utf-8",
            )
            (model_dir / "model_card.json").write_text(
                json.dumps(
                    {
                        "model_version": "v1",
                        "feature_count": 1,
                        "numeric_feature_count": 1,
                        "categorical_feature_count": 0,
                        "label_column": "rank_label_3d",
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = main(["model", "status", "--method", "b2", "--runtime-root", str(runtime)])

        self.assertEqual(rc, 0)
        self.assertIn("生产路由总览: b2", stdout.getvalue())
        self.assertIn("发布版本: v1", stdout.getvalue())

    def test_model_status_fails_without_runtime_root_or_target_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stderr = io.StringIO()
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(stderr):
                    rc = main(["model", "status", "--method", "b2"])
            finally:
                os.chdir(original_cwd)

        self.assertNotEqual(rc, 0)
        self.assertIn("STOCK_SELECT_RUNTIME_ROOT", stderr.getvalue())

    def test_model_subcommands_use_shell_runtime_root_consistently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shell_runtime = root / "shell-runtime"
            dotenv_runtime = root / "dotenv-runtime"
            (root / ".env").write_text(f"STOCK_SELECT_RUNTIME_ROOT={dotenv_runtime}\n", encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            expected_target = shell_runtime / "models" / "b2"
            env = {"STOCK_SELECT_RUNTIME_ROOT": str(shell_runtime)}

            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, env, clear=True):
                    with patch("ml.model_ops.status.print_status") as print_status:
                        main(["model", "status", "--method", "b2"])
                    with patch("ml.model_ops.archive.list_archived_models", return_value=[]) as list_archived:
                        main(["model", "archives", "--method", "b2"])
                    with patch("ml.model_ops.promote.promote_model", return_value={"validation": {}}) as promote_model:
                        main(["model", "dry-run-promote", str(candidate), "--method", "b2"])
                    with patch("ml.model_ops.promote.rollback_model", return_value={"validation": {}}) as rollback_model:
                        main(["model", "rollback", "20260601T000000Z", "--method", "b2", "--dry-run"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(print_status.call_args.kwargs["runtime_root"], shell_runtime)
        self.assertEqual(list_archived.call_args.args[0], expected_target)
        self.assertEqual(promote_model.call_args.args[1], expected_target)
        self.assertEqual(rollback_model.call_args.args[0], expected_target)


if __name__ == "__main__":
    unittest.main()
