import json
import os
import subprocess
import sys
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

    def test_model_docs_and_skill_use_stock_select_ml_cli(self):
        paths = [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "AGENTS.md",
            PROJECT_ROOT / "docs" / "model.md",
            PROJECT_ROOT / "docs" / "workflow.md",
            PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "SKILL.md",
            PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "references" / "model-maintenance.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertIn("uv run stock-select-ml train lgbm-rank", combined)
        self.assertIn("uv run stock-select-ml model dry-run-promote", combined)
        self.assertIn("uv run stock-select-ml backfill runs", combined)
        for old_entrypoint in [
            "scripts/ml/",
            "scripts/model_maintenance.sh",
            "model_maintenance.sh",
            "scripts/backfill_run.py",
            "backfill_run.py",
        ]:
            with self.subTest(old_entrypoint=old_entrypoint):
                self.assertNotIn(old_entrypoint, combined)

    def test_screening_methods_document_current_filter_conditions(self):
        doc_path = PROJECT_ROOT / "docs" / "screening-methods.md"
        self.assertTrue(doc_path.exists(), "missing screening method filter documentation")
        docs = doc_path.read_text(encoding="utf-8")

        expected_fragments = [
            "# 选股筛选方法过滤条件",
            "实际接入 screen 的方法：`b2`、`b3`、`lsh`。",
            "`turnover-top` 股票池",
            "取 `turnover_n` 最高的前 5000 只",
            "`b2` / `b3`：要求当日 `MA25 > MA60`",
            "`custom` 股票池",
            "`b1`、`dribull` 当前没有 screen 策略实现",
            "`b2`",
            "当日涨幅 `pct >= 3.7%`",
            "当前成交量大于前一日成交量",
            "当前 `J` 值大于前一日 `J` 值",
            "同一轮 `J` 转强周期内只保留第一次 raw B2",
            "`b3`",
            "前一交易日已经触发 `B2`",
            "当前振幅 `amp` 小于阈值",
            "当前成交量不超过前一日的 `90%`",
            "`B3+`：在 `B3` 基础上",
            "`lsh`",
            "当日最低价跌破 `MA25`",
            "当日收盘价高于 `MA25`",
            "周线和月线最新 MACD 柱值与 DEA 都大于 0",
            "`run` 阶段不再增加硬过滤",
        ]
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, docs)

    def test_model_docs_describe_random_forest_factor_diagnostics(self):
        docs = (PROJECT_ROOT / "docs" / "model.md").read_text(encoding="utf-8")

        self.assertIn("随机森林因子诊断", docs)
        self.assertIn("rf_feature_diagnostics.json", docs)
        self.assertIn("rf_diagnostics", docs)
        self.assertIn("--skip-rf-diagnostics", docs)
        self.assertIn("不进入 Rust 生产推理", docs)

    def test_model_docs_describe_factor_artifact_training_contract(self):
        docs = (PROJECT_ROOT / "docs" / "model.md").read_text(encoding="utf-8")

        self.assertIn("factors.json", docs)
        self.assertIn("训练特征契约", docs)
        self.assertIn("review-only", docs)
        self.assertIn("box_mid_position_120d_pct", docs)
        self.assertIn("feature_coverage", docs)
        self.assertIn("zero coverage", docs)
    def test_model_maintenance_skill_reports_random_forest_diagnostics(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "SKILL.md",
                PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "references" / "model-maintenance.md",
            ]
        )

        self.assertIn("随机森林因子诊断", combined)
        self.assertIn("rf_feature_diagnostics.json", combined)
        self.assertIn("rf_diagnostics", combined)
        self.assertIn("low_importance_feature_count", combined)
        self.assertIn("不进入生产推理", combined)

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
        source = (PROJECT_ROOT / "ml" / "dataset" / "rank_dataset.py").read_text(encoding="utf-8")

        self.assertNotIn("def context_features", source)
        self.assertNotIn("def compute_macd_lines", source)
        self.assertNotIn("def compute_zx_lines", source)
        self.assertNotIn("def fetch_indicator_rows", source)
        self.assertNotIn("recompute_context", source)

    def test_model_maintenance_shell_entry_exposes_expected_commands(self):
        completed = subprocess.run(
            [sys.executable, "-m", "ml", "model", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("status", completed.stdout)
        self.assertIn("archives", completed.stdout)
        self.assertIn("promote", completed.stdout)
        self.assertIn("rollback", completed.stdout)
        self.assertIn("dry-run-promote", completed.stdout)

    def test_model_maintenance_status_prints_readable_model_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'status should not call uv' >&2\n"
                "exit 9\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            runtime = root / "runtime"
            model_dir = runtime / "models" / "b3"
            model_dir.mkdir(parents=True)
            (model_dir / "model_state.json").write_text(
                json.dumps({"eod": {"status": "ready", "model_dir": "models/b3"}}),
                encoding="utf-8",
            )
            (model_dir / "model.txt").write_text("tree\n", encoding="utf-8")
            (model_dir / "model_metadata.json").write_text(
                json.dumps(
                    {
                        "numeric_columns": ["a", "b"],
                        "categorical_columns": [],
                        "label_column": "rank_label_3d",
                    }
                ),
                encoding="utf-8",
            )
            (model_dir / "model_card.json").write_text(
                json.dumps(
                    {
                        "model_version": "20260608T010203Z",
                        "train_window": "2025-01-01..2025-12-31",
                        "score_window": "2026-01-01..2026-02-01",
                        "rolling_fold_count": 5,
                        "rolling_summary": {
                            "top3_ret3_positive_rate": 52.54,
                            "top3_ret3_ge_5_rate": 28.5,
                            "top3_ret3_le_0_rate": 47.46,
                            "top3_ret3_ge_5_capture_rate": 5.78,
                            "rank_ic_ret3": 0.0707,
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                [sys.executable, "-m", "ml", "model", "status", "--method", "b3", "--runtime-root", str(runtime)],
                check=True,
                capture_output=True,
                env=env,
                text=True,
            )

        self.assertIn("模型状态: b3", completed.stdout)
        self.assertIn("生产路由总览: b3", completed.stdout)
        self.assertIn("日终模型 (eod)", completed.stdout)
        self.assertIn("状态: ready (可用)", completed.stdout)
        self.assertIn("发布版本: 20260608T010203Z", completed.stdout)
        self.assertIn("训练窗口: 2025-01-01..2025-12-31", completed.stdout)
        self.assertIn("打分窗口: 2026-01-01..2026-02-01", completed.stdout)
        self.assertIn("特征/标签: 2 个特征 (数值 2, 分类 0), label=rank_label_3d", completed.stdout)
        self.assertIn("产物检查: OK", completed.stdout)
        self.assertIn("指标口径: rolling_summary (5 折滚动验证)", completed.stdout)
        self.assertIn(
            "Top3 3日表现: 正收益 52.54% | 涨幅>=5% 28.50% | 非正收益 47.46% | >=5%捕获 5.78% | RankIC 0.0707",
            completed.stdout,
        )
        self.assertNotIn("LightGBM 模型维护摘要", completed.stdout)
        self.assertNotIn("metrics_source=", completed.stdout)
        self.assertNotIn("model_sha256", completed.stdout)
        self.assertRegex(completed.stdout, r"={20,}")

    def test_model_maintenance_status_prints_intraday_model_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\n' 'LightGBM 模型维护摘要'\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            runtime = root / "runtime"
            lsh_dir = runtime / "models" / "lsh"
            intraday_dir = runtime / "models" / "lsh_intraday"
            lsh_dir.mkdir(parents=True)
            intraday_dir.mkdir(parents=True)
            (lsh_dir / "model_state.json").write_text(
                json.dumps(
                    {
                        "eod": {"status": "ready", "model_dir": "models/lsh"},
                        "intraday": {
                            "status": "ready",
                            "model_dir": "models/lsh_intraday",
                        },
                    }
                ),
                encoding="utf-8",
            )
            for model_dir in [lsh_dir, intraday_dir]:
                (model_dir / "model.txt").write_text("tree\n", encoding="utf-8")
                (model_dir / "model_metadata.json").write_text(
                    json.dumps(
                        {
                            "numeric_columns": ["a", "b"],
                            "categorical_columns": [],
                            "label_column": "rank_label_3d",
                        }
                    ),
                    encoding="utf-8",
                )
            (intraday_dir / "model_card.json").write_text(
                json.dumps(
                    {
                        "model_version": "intraday-test",
                        "mode": "intraday",
                        "test_metrics": {
                            "top3_ret3_positive_rate": 60.1,
                            "rank_ic_ret3": 0.0769,
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            env["STOCK_SELECT_RUNTIME_ROOT"] = str(runtime)
            completed = subprocess.run(
                [sys.executable, "-m", "ml", "model", "status", "--method", "lsh"],
                check=True,
                capture_output=True,
                env=env,
                text=True,
            )

        self.assertIn("盘中模型 (intraday)", completed.stdout)
        self.assertIn("指标口径: test_metrics (模型卡测试集)", completed.stdout)
        self.assertIn(
            "Top3 3日表现: 正收益 60.10% | 涨幅>=5% 指标缺失 | 非正收益 指标缺失 | >=5%捕获 指标缺失 | RankIC 0.0769",
            completed.stdout,
        )
        self.assertNotIn("intraday: status=ready", completed.stdout)
        self.assertNotIn("metrics_source=test_metrics", completed.stdout)

    def test_model_maintenance_status_discovers_intraday_only_model_without_state_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            intraday_dir = runtime / "models" / "lsh_intraday"
            intraday_dir.mkdir(parents=True)
            (intraday_dir / "model.txt").write_text("tree\n", encoding="utf-8")
            (intraday_dir / "model_metadata.json").write_text(
                json.dumps(
                    {
                        "feature_names": ["a", "b"],
                        "numeric_columns": ["a", "b"],
                        "categorical_columns": [],
                        "label_column": "rank_label_3d",
                    }
                ),
                encoding="utf-8",
            )
            (intraday_dir / "model_card.json").write_text(
                json.dumps(
                    {
                        "model_version": "intraday-only",
                        "mode": "promote",
                        "target": str(intraday_dir),
                        "rolling_summary": {
                            "top3_ret3_positive_rate": 57.1,
                            "rank_ic_ret3": 0.073,
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["STOCK_SELECT_RUNTIME_ROOT"] = str(runtime)
            completed = subprocess.run(
                [sys.executable, "-m", "ml", "model", "status", "--method", "lsh"],
                check=True,
                capture_output=True,
                env=env,
                text=True,
            )

        self.assertIn("盘中模型 (intraday)", completed.stdout)
        self.assertIn("模型目录: " + str(intraday_dir), completed.stdout)
        self.assertIn("产物检查: OK", completed.stdout)
        self.assertIn("发布版本: intraday-only", completed.stdout)
        self.assertNotIn("日终模型 (eod)", completed.stdout)
        self.assertNotIn("按默认日终模型目录展示", completed.stdout)

    def test_model_maintenance_status_understands_routed_model_without_state_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'status should not call uv' >&2\n"
                "exit 9\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            runtime = root / "runtime"
            model_dir = runtime / "models" / "b3"
            child_dir = model_dir / "models" / "neutral_rf"
            child_dir.mkdir(parents=True)
            (model_dir / "model_routing.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "default_model": "neutral_rf",
                        "models": {"neutral_rf": "models/neutral_rf"},
                        "routes": [],
                    }
                ),
                encoding="utf-8",
            )
            (child_dir / "model.txt").write_text("tree\n", encoding="utf-8")
            (child_dir / "model_metadata.json").write_text(
                json.dumps(
                    {
                        "feature_names": ["a", "b", "env=strong"],
                        "numeric_columns": ["a", "b"],
                        "categorical_columns": ["env"],
                        "label_column": "rank_label_3d",
                    }
                ),
                encoding="utf-8",
            )
            (model_dir / "model_card.json").write_text(
                json.dumps(
                    {
                        "model_version": "routed-test",
                        "feature_count": 3,
                        "label_column": "rank_label_3d",
                        "rolling_summary": {
                            "top3_ret3_positive_rate": 52.54,
                            "rank_ic_ret3": 0.0707,
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                [sys.executable, "-m", "ml", "model", "status", "--method", "b3", "--runtime-root", str(runtime)],
                check=True,
                capture_output=True,
                env=env,
                text=True,
            )

        self.assertIn("日终模型 (eod)", completed.stdout)
        self.assertIn("模型目录: " + str(model_dir), completed.stdout)
        self.assertIn("产物检查: OK", completed.stdout)
        self.assertIn("路由模型: default=neutral_rf, 子模型 1 个", completed.stdout)
        self.assertIn("特征/标签: 3 个特征 (数值 2, 分类 1), label=rank_label_3d", completed.stdout)
        self.assertNotIn("备注: 未找到 model_state.json", completed.stdout)
        self.assertNotIn("缺失 model.txt", completed.stdout)

    def test_model_maintenance_status_target_dir_falls_back_without_double_runtime(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp_dir:
            root = Path(temp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                "echo 'status should not call uv' >&2\n"
                "exit 9\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            model_dir = root / "runtime" / "models" / "b3"
            model_dir.mkdir(parents=True)
            (model_dir / "model.txt").write_text("tree\n", encoding="utf-8")
            (model_dir / "model_metadata.json").write_text(
                json.dumps(
                    {
                        "numeric_columns": ["a"],
                        "categorical_columns": [],
                        "label_column": "rank_label_3d",
                    }
                ),
                encoding="utf-8",
            )
            (model_dir / "model_card.json").write_text(
                json.dumps({"model_version": "target-dir-test"}),
                encoding="utf-8",
            )

            relative_target_dir = model_dir.relative_to(PROJECT_ROOT)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            completed = subprocess.run(
                [sys.executable, "-m", "ml", "model", "status", "--method", "b3", "--target-dir", str(relative_target_dir)],
                check=True,
                capture_output=True,
                env=env,
                text=True,
            )

        self.assertIn(f"模型目录: {relative_target_dir}", completed.stdout)
        self.assertIn("备注: 未找到 model_state.json；按默认日终模型目录展示", completed.stdout)
        self.assertNotIn("runtime/runtime", completed.stdout)

    def test_b2_post_rerank_rule_lives_in_b2_engine_module(self):
        run_source = (PROJECT_ROOT / "src" / "engine" / "run.rs").read_text(encoding="utf-8")
        b2_source = (PROJECT_ROOT / "src" / "engine" / "b2.rs").read_text(encoding="utf-8")

        self.assertNotIn("fn adjust_b2_cyq_post_rerank_score", run_source)
        self.assertIn("fn adjust_b2_cyq_post_rerank_score", b2_source)


if __name__ == "__main__":
    unittest.main()
