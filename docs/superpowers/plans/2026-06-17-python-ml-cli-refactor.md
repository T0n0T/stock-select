# Python ML CLI 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `scripts/ml/*.py`、`scripts/backfill_run.py` 和 `scripts/model_maintenance.sh` 干净迁移为仓库内统一 Python package/CLI，并同时补齐 LightGBM 排序调参能力。

**Architecture:** 新建 `ml` package，以 `stock-select-ml` 和 `python -m ml` 作为唯一 Python ML 运维入口。旧脚本不做兼容 wrapper，能力迁入后删除旧入口，测试和文档直接改到新 CLI。训练模块按 dataset、feature/matrix/label、evaluation、RF diagnostics、LightGBM ranker、report/artifact、tuning、model ops 拆分。

**Tech Stack:** Python 3.11、argparse、uv/pyproject console scripts、LightGBM、NumPy、scikit-learn、可选 Optuna、unittest、Rust cargo tests。

---

## 文件结构

新增 package：

```text
ml/
  __init__.py
  __main__.py
  cli.py
  env.py
  dates.py
  paths.py
  subprocesses.py
  backfill/{commands.py,candidates.py,runs.py}
  dataset/{schema.py,factors.py,rank_dataset.py}
  training/{features.py,matrices.py,labels.py,evaluation.py,rf_diagnostics.py,lgbm_ranker.py,reports.py,artifacts.py,train_lgbm_rank.py}
  tuning/{configs.py,grid.py,objectives.py,optuna_search.py}
  scoring/{export_lgbm_scores.py,score_blends.py}
  diagnostics/{controlled_rerank.py}
  model_ops/{validate.py,promote.py,status.py,archive.py}
```

删除旧入口：

```text
scripts/ml/backfill_candidates.py
scripts/ml/build_rank_dataset.py
scripts/ml/controlled_rerank_diagnostics.py
scripts/ml/evaluate_lgbm_score_blends.py
scripts/ml/export_lgbm_scores.py
scripts/ml/promote_lgbm_model.py
scripts/ml/train_rank_lgbm.py
scripts/backfill_run.py
scripts/model_maintenance.sh
```

---

### Task 1: 建立 Python Package 和 CLI 骨架

**Files:**
- Create: `pyproject.toml`
- Create: `ml/__init__.py`
- Create: `ml/__main__.py`
- Create: `ml/cli.py`
- Create: `tests/test_ml_cli.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_ml_cli.py`：

```python
import contextlib
import io
import unittest

from ml.cli import main


class MlCliTest(unittest.TestCase):
    def test_main_prints_usage_for_no_args(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main([])
        self.assertEqual(rc, 2)
        self.assertIn("stock-select-ml", stderr.getvalue())

    def test_main_routes_version(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = main(["--version"])
        self.assertEqual(rc, 0)
        self.assertIn("stock-select-ml", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_ml_cli.py`

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'ml'`。

- [ ] **Step 3: 实现最小 package**

创建 `pyproject.toml`：

```toml
[project]
name = "stock-select-ml"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "numpy",
  "lightgbm",
  "scikit-learn",
  "psycopg[binary]",
]

[project.optional-dependencies]
tuning = ["optuna"]

[project.scripts]
stock-select-ml = "ml.cli:entrypoint"

[tool.setuptools.packages.find]
include = ["ml*"]
```

创建 `ml/__init__.py`：

```python
from __future__ import annotations

__version__ = "0.1.0"
```

创建 `ml/__main__.py`：

```python
from __future__ import annotations

from .cli import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint())
```

创建 `ml/cli.py`：

```python
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-select-ml")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_subparsers(dest="group")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.version:
        print(f"stock-select-ml {__version__}")
        return 0
    parser.print_usage(sys.stderr)
    return 2


def entrypoint() -> int:
    return main()
```

- [ ] **Step 4: 验证通过**

Run: `python -m unittest tests/test_ml_cli.py`

Expected: PASS。

Run: `uv run stock-select-ml --version`

Expected: 输出包含 `stock-select-ml 0.1.0`。

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml ml tests/test_ml_cli.py
git commit -m "feat: add stock-select-ml cli skeleton"
```

---

### Task 2: 公共 env、路径、日期和子进程模块

**Files:**
- Create: `ml/env.py`
- Create: `ml/paths.py`
- Create: `ml/dates.py`
- Create: `ml/subprocesses.py`
- Create: `tests/test_ml_common.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_ml_common.py`：

```python
import signal
import tempfile
import unittest
from pathlib import Path

from ml.dates import read_dates_file, validate_date, weekday_fallback
from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import candidate_path, factor_artifact_path, select_dir
from ml.subprocesses import format_returncode


class MlCommonTest(unittest.TestCase):
    def test_load_dotenv_values_handles_export_and_quotes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text("export STOCK_SELECT_RUNTIME_ROOT='runtime-x'\nPOSTGRES_DSN=postgres://secret\n", encoding="utf-8")
            values = load_dotenv_values(path)
        self.assertEqual(values["STOCK_SELECT_RUNTIME_ROOT"], "runtime-x")
        self.assertEqual(values["POSTGRES_DSN"], "postgres://secret")

    def test_resolve_config_value_prefers_cli_then_env_then_dotenv(self):
        self.assertEqual(resolve_config_value("cli", "KEY", {"KEY": "dotenv"}, env={"KEY": "env"}), "cli")
        self.assertEqual(resolve_config_value(None, "KEY", {"KEY": "dotenv"}, env={"KEY": "env"}), "env")
        self.assertEqual(resolve_config_value(None, "KEY", {"KEY": "dotenv"}, env={}), "dotenv")

    def test_dates_and_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dates.txt"
            path.write_text("2026-06-02\n# comment\n2026-06-01\n2026-06-02\n", encoding="utf-8")
            self.assertEqual(read_dates_file(path), ["2026-06-01", "2026-06-02"])
        self.assertEqual(validate_date("2026-06-03"), "2026-06-03")
        self.assertEqual(weekday_fallback("2026-06-05", "2026-06-08"), ["2026-06-05", "2026-06-08"])
        root = Path("/tmp/runtime")
        self.assertEqual(candidate_path(root, "2026-06-01", "b3"), root / "candidates" / "2026-06-01.b3.json")
        self.assertEqual(factor_artifact_path(root, "2026-06-01", "b3"), root / "factors" / "2026-06-01.b3" / "factors.json")
        self.assertEqual(select_dir(root, "2026-06-01", "b3"), root / "select" / "2026-06-01.b3")

    def test_format_returncode_labels_signals(self):
        self.assertEqual(format_returncode(-signal.SIGKILL), "signal=SIGKILL")
        self.assertEqual(format_returncode(2), "rc=2")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_ml_common.py`

Expected: FAIL，缺少公共模块。

- [ ] **Step 3: 实现公共模块**

实现内容从现有 `scripts/ml/backfill_candidates.py`、`scripts/backfill_run.py`、`scripts/ml/promote_lgbm_model.py` 中抽取，保留函数名：

```text
env.py: load_dotenv_values, resolve_config_value
paths.py: PROJECT_ROOT, candidate_path, factor_artifact_path, select_dir
dates.py: validate_date, weekday_fallback, read_dates_file, fetch_trade_dates
subprocesses.py: CommandFailure, CommandBatchResult, format_returncode, run_command
```

实现要求：

- `load_dotenv_values()` 支持 `export KEY=value` 和单双引号。
- `resolve_config_value()` 优先级为 CLI 参数、环境变量、`.env`。
- `fetch_trade_dates()` 只接收 DSN 参数，不打印 DSN。
- `format_returncode()` 对负数返回 `signal=SIGKILL` 这类格式。

- [ ] **Step 4: 验证通过并提交**

Run: `python -m unittest tests/test_ml_common.py`

Expected: PASS。

```bash
git add ml/env.py ml/paths.py ml/dates.py ml/subprocesses.py tests/test_ml_common.py
git commit -m "feat: add ml cli common utilities"
```

---

### Task 3: 迁移 Candidate 和 Run Backfill

**Files:**
- Create: `ml/backfill/__init__.py`
- Create: `ml/backfill/commands.py`
- Create: `ml/backfill/candidates.py`
- Create: `ml/backfill/runs.py`
- Modify: `ml/cli.py`
- Modify: `tests/test_candidate_backfill.py`
- Modify: `tests/test_run_backfill.py`
- Create: `tests/test_backfill_cli.py`
- Delete: `scripts/ml/backfill_candidates.py`
- Delete: `scripts/backfill_run.py`

- [ ] **Step 1: 写 CLI 失败测试**

创建 `tests/test_backfill_cli.py`，用临时 `dates.txt` 分别调用：

```python
main(["backfill", "candidates", "--start-date", "2026-06-01", "--end-date", "2026-06-01", "--runtime-root", "/tmp/runtime", "--binary", "stock-select-rs", "--method", "b3", "--dates-file", str(dates_file), "--dry-run"])
main(["backfill", "runs", "--start-date", "2026-06-01", "--end-date", "2026-06-01", "--runtime-root", "/tmp/runtime", "--binary", "stock-select-rs", "--method", "b3", "--dates-file", str(dates_file), "--dry-run"])
```

断言返回 `0`，stdout 分别包含 `screen --method b3 --pick-date 2026-06-01` 和 `run --method b3 --pick-date 2026-06-01`。

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_backfill_cli.py`

Expected: FAIL，`backfill` 命令未注册。

- [ ] **Step 3: 搬迁实现**

从旧脚本移动并改 import：

```text
scripts/ml/backfill_candidates.py -> ml/backfill/candidates.py
scripts/backfill_run.py -> ml/backfill/runs.py
```

共享命令构造写入 `ml/backfill/commands.py`，公开：

```text
build_screen_command
build_run_command
```

保留公开对象：

```text
candidates.py: BackfillConfig, BackfillFailure, BackfillResult, select_missing_dates, run_backfill, parse_args, main_from_args, add_parser
runs.py: RunConfig, RunResult, build_dates, run_single, run_single_quiet, parse_args, main_from_args, add_parser
```

- [ ] **Step 4: 注册 CLI**

在 `ml/cli.py` 注册：

```text
backfill candidates
backfill runs
```

`main()` 通过 `args.handler(args)` 分发。

- [ ] **Step 5: 迁移测试 import**

`tests/test_candidate_backfill.py` 改为导入：

```python
from ml.backfill import candidates as backfill_candidates
from ml.backfill.candidates import BackfillConfig, parse_args, run_backfill, select_missing_dates
from ml.backfill.commands import build_screen_command
from ml.subprocesses import format_returncode
```

`tests/test_run_backfill.py` 改为导入：

```python
from ml.backfill import runs as backfill_run
from ml.backfill.runs import RunConfig, parse_args, run_single_quiet
from ml.backfill.candidates import parse_args as parse_candidate_args
```

- [ ] **Step 6: 验证 backfill**

Run: `python -m unittest tests/test_backfill_cli.py tests/test_candidate_backfill.py tests/test_run_backfill.py`

Expected: PASS。

- [ ] **Step 7: 删除旧入口并检查引用**

Run: `rm scripts/ml/backfill_candidates.py scripts/backfill_run.py`

Run: `rg "scripts/ml/backfill_candidates.py|scripts/backfill_run.py|from scripts import backfill_run|from scripts.ml import backfill_candidates" tests docs .agents scripts ml`

Expected: 没有输出。

- [ ] **Step 8: 提交**

```bash
git add ml/backfill ml/cli.py tests/test_backfill_cli.py tests/test_candidate_backfill.py tests/test_run_backfill.py scripts/ml/backfill_candidates.py scripts/backfill_run.py
git commit -m "feat: migrate backfill commands to ml cli"
```

---

### Task 4: 迁移 Dataset Build 和 Schema

**Files:**
- Create: `ml/dataset/__init__.py`
- Create: `ml/dataset/schema.py`
- Create: `ml/dataset/factors.py`
- Create: `ml/dataset/rank_dataset.py`
- Modify: `ml/cli.py`
- Modify: `tests/test_rank_dataset.py`
- Delete: `scripts/ml/build_rank_dataset.py`

- [ ] **Step 1: 写 CLI 失败测试**

在 `tests/test_ml_cli.py` 增加 `test_dataset_build_help_is_registered`，调用 `main(["dataset", "build", "--help"])`，断言退出码 `0` 且 stdout 包含 `rank dataset`。

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_ml_cli.py`

Expected: FAIL，`dataset build` 未注册。

- [ ] **Step 3: 拆分旧 dataset 脚本**

从 `scripts/ml/build_rank_dataset.py` 移动：

```text
schema.py: method 因子常量、raw_factor_columns_for_method、context_numeric_columns_for_method、training_macd_numeric_columns_for_method、training_categorical_columns_for_method
factors.py: runtime factor artifact 装载、manifest 校验、artifact version/library version 校验
rank_dataset.py: CLI parser、dataset 行构建、summary 写入、main_from_args、add_parser
```

- [ ] **Step 4: 注册 CLI 并迁移测试 import**

注册 `dataset build`。

`tests/test_rank_dataset.py` 改为：

```python
from ml.dataset import rank_dataset as build_rank_dataset
from ml.dataset import schema as rank_dataset_schema
```

- [ ] **Step 5: 验证 dataset**

Run: `python -m unittest tests/test_rank_dataset.py tests/test_ml_cli.py`

Expected: PASS。

- [ ] **Step 6: 删除旧入口并检查引用**

Run: `rm scripts/ml/build_rank_dataset.py`

Run: `rg "scripts/ml/build_rank_dataset.py|scripts.ml.build_rank_dataset|from scripts.ml import build_rank_dataset" tests docs .agents ml`

Expected: 没有输出。

- [ ] **Step 7: 提交**

```bash
git add ml/dataset ml/cli.py tests/test_rank_dataset.py tests/test_ml_cli.py scripts/ml/build_rank_dataset.py
git commit -m "feat: migrate rank dataset build to ml cli"
```

---

### Task 5: 拆分训练基础模块

**Files:**
- Create: `ml/training/__init__.py`
- Create: `ml/training/features.py`
- Create: `ml/training/matrices.py`
- Create: `ml/training/labels.py`
- Create: `ml/training/evaluation.py`
- Create: `tests/test_lgbm_training_features.py`
- Create: `tests/test_lgbm_training_evaluation.py`

- [ ] **Step 1: 写 features/evaluation 失败测试**

从 `tests/test_rank_lgbm.py` 复制以下用例到新测试文件，并改 import 到 `ml.training.*`：

```text
test_select_feature_columns_excludes_artifact_scores_and_labels
test_select_feature_columns_supports_legacy_semantic_feature_sets
test_select_feature_columns_uses_method_registered_raw_factors
test_validate_selected_feature_coverage_fails_zero_coverage_feature
test_rows_for_dates_uses_requested_label_column
test_average_metric_dicts_ignores_missing_values
test_evaluate_model_reports_rank_ic_ret5
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_lgbm_training_features.py tests/test_lgbm_training_evaluation.py`

Expected: FAIL，缺少训练模块。

- [ ] **Step 3: 从旧训练脚本搬迁基础函数**

从 `scripts/ml/train_rank_lgbm.py` 搬迁：

```text
features.py: feature set 常量、feature 选择、coverage 校验、feature manifest 读取、RF importance feature selection
matrices.py: categorical levels/code maps、one-hot/native matrix、safe feature names、metadata matrix 重放
labels.py: as_float、pct、label_value、labels、rows_for_dates、TRAIN_LABEL_COLUMNS
evaluation.py: assign_scores、grouped_by_date、evaluate_model、rank_ic、pearson、average_metric_dicts、env/month partitions
```

`features.py` 只依赖 `ml.dataset.schema`，不再从脚本模块 import。

- [ ] **Step 4: 验证通过并提交**

Run: `python -m unittest tests/test_lgbm_training_features.py tests/test_lgbm_training_evaluation.py`

Expected: PASS。

```bash
git add ml/training tests/test_lgbm_training_features.py tests/test_lgbm_training_evaluation.py
git commit -m "refactor: split lgbm training feature and evaluation modules"
```

---

### Task 6: 迁移 RF、LightGBM、Report 和 Artifact 主训练路径

**Files:**
- Create: `ml/training/rf_diagnostics.py`
- Create: `ml/training/lgbm_ranker.py`
- Create: `ml/training/reports.py`
- Create: `ml/training/artifacts.py`
- Create: `ml/training/train_lgbm_rank.py`
- Modify: `ml/cli.py`
- Create: `tests/test_lgbm_training_report.py`

- [ ] **Step 1: 写训练 report 失败测试**

从 `tests/test_rank_lgbm.py` 复制以下用例到 `tests/test_lgbm_training_report.py`，并改 import 到新模块：

```text
test_train_report_writes_and_embeds_random_forest_diagnostics
test_random_forest_threshold_failure_writes_report_and_stops_lgbm
test_train_report_can_skip_random_forest_diagnostics
test_train_and_report_persists_lambdarank_truncation_level
test_train_and_report_writes_model_artifacts_when_rolling_is_enabled
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_lgbm_training_report.py`

Expected: FAIL，缺少 `ml.training.train_lgbm_rank`。

- [ ] **Step 3: 搬迁训练主路径**

从 `scripts/ml/train_rank_lgbm.py` 搬迁：

```text
rf_diagnostics.py: RandomForestDiagnosticsConfig、RandomForestThresholdError、run_random_forest_diagnostics、diagnostic report helpers、threshold failures
lgbm_ranker.py: DEFAULT_LABEL_GAIN、TrainedModelResult、group_sizes_by_date、train_model、train_model_result
artifacts.py: build_model_metadata、write_model_artifacts、write_feature_manifest
reports.py: markdown_report、report_paths
train_lgbm_rank.py: read_dataset、walk_forward_split_dates、rolling_walk_forward_splits、resolve paths、parse_label_gain、train_and_report、CLI parser
```

- [ ] **Step 4: 注册 `train lgbm-rank`**

在 `ml/cli.py` 注册 `train lgbm-rank`，`train_lgbm_rank.add_parser()` 设置 `handler=main_from_args`。

- [ ] **Step 5: 验证通过并提交**

Run: `python -m unittest tests/test_lgbm_training_report.py`

Expected: PASS。

```bash
git add ml/training ml/cli.py tests/test_lgbm_training_report.py
git commit -m "refactor: migrate lgbm rank training modules"
```

---

### Task 7: 引入排序调参参数、Top-K、NDCG 和 Early Stopping

**Files:**
- Modify: `ml/training/evaluation.py`
- Modify: `ml/training/lgbm_ranker.py`
- Modify: `ml/training/train_lgbm_rank.py`
- Modify: `ml/training/reports.py`
- Modify: `ml/training/artifacts.py`
- Modify: `tests/test_lgbm_training_evaluation.py`
- Modify: `tests/test_lgbm_training_report.py`

- [ ] **Step 1: 写 Top-K/NDCG 失败测试**

在 `tests/test_lgbm_training_evaluation.py` 增加测试，构造 3 行同日样本，调用：

```python
metrics = evaluate_model(rows, top_k=[1, 2], label_column="rank_label_3d", ndcg_at=[1, 2])
```

断言：

```text
top1_ret3_ge_5_rate == 100.0
top2_ret3_positive_rate == 100.0
top2_ret3_le_0_rate == 0.0
ndcg_at_1 == 1.0
ndcg_at_2 == 1.0
```

- [ ] **Step 2: 写参数 report 失败测试**

在 `tests/test_lgbm_training_report.py` 增加用例，使用该文件已有小 dataset helper，调用 `train_and_report()` 并断言：

```text
model_params.boosting_type == dart
model_params.bagging_fraction == 0.8
model_params.feature_fraction == 0.7
model_params.lambda_l1 == 1.0
model_params.lambda_l2 == 2.0
model_params.early_stopping_rounds == 30
top_k == [3, 5]
eval_at == [5, 10]
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m unittest tests/test_lgbm_training_evaluation.py tests/test_lgbm_training_report.py`

Expected: FAIL，旧 `evaluate_model()` 不支持多 Top-K 或 report 缺参数。

- [ ] **Step 4: 实现评估升级**

将 `evaluate_model(rows, top_n=3)` 改为支持：

```python
evaluate_model(rows, top_k=[3, 5, 10, 20], label_column="rank_label_3d", ndcg_at=[5, 10, 20])
```

输出保留 `top3_*`，新增 `top5_*`、`top10_*`、`top20_*`、`ndcg_at_5`、`ndcg_at_10`、`ndcg_at_20`。将所有旧调用点改为 `top_k=[3]` 或传入 CLI 的 `top_k`。

- [ ] **Step 5: 实现 LightGBM 参数和 early stopping**

`train_model_result()`、`train_model()` 和 `train_and_report()` 新增参数：

```text
boosting_type
bagging_fraction
bagging_freq
feature_fraction
lambda_l1
lambda_l2
min_gain_to_split
eval_at
early_stopping_rounds
seed
top_k
```

实现时使用 LightGBM `valid_sets` 和 `lgb.early_stopping()`；预测使用 `best_iteration`，report/metadata 写入 `best_iteration` 和完整 `model_params`。

- [ ] **Step 6: parser 支持新参数**

`train lgbm-rank` parser 新增：

```text
--boosting-type gbdt|dart
--bagging-fraction
--bagging-freq
--feature-fraction
--lambda-l1
--lambda-l2
--min-gain-to-split
--top-k 3,5,10,20
--eval-at 5,10,20
--early-stopping-rounds
--seed
```

新增 `parse_int_list()` 解析逗号分隔整数列表。

- [ ] **Step 7: 验证通过并提交**

Run: `python -m unittest tests/test_lgbm_training_evaluation.py tests/test_lgbm_training_report.py`

Expected: PASS。

```bash
git add ml/training tests/test_lgbm_training_evaluation.py tests/test_lgbm_training_report.py
git commit -m "feat: add top-k ranking metrics and lgbm tuning params"
```

---

### Task 8: 实现 `tune lgbm-rank` Grid 和可选 Optuna

**Files:**
- Create: `ml/tuning/__init__.py`
- Create: `ml/tuning/configs.py`
- Create: `ml/tuning/grid.py`
- Create: `ml/tuning/objectives.py`
- Create: `ml/tuning/optuna_search.py`
- Modify: `ml/cli.py`
- Create: `tests/test_lgbm_tuning.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_lgbm_tuning.py`，覆盖：

```text
default_grid_trials(max_trials=4) 返回 4 组，且 trial 包含 lambdarank_truncation_level、eval_at、top_k
score_trial_report() 优先惩罚 top3_ret3_le_0_rate
require_optuna() 在缺依赖时抛出包含 Optuna 的 RuntimeError
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_lgbm_tuning.py`

Expected: FAIL，缺少 tuning 模块。

- [ ] **Step 3: 实现 grid 和 objective**

`default_grid_trials(max_trials)` 默认覆盖：

```text
feature_set
label_column
num_leaves
min_data_in_leaf
lambdarank_truncation_level
top_k
eval_at
boosting_type
bagging_fraction
feature_fraction
lambda_l1
lambda_l2
```

`score_trial_report()` 按主 Top-K 优先级评分：降低 `topK_ret3_le_0_rate` 权重大于提高 `positive_rate`。

- [ ] **Step 4: 实现 CLI 和 Optuna guard**

注册：

```text
tune lgbm-rank --strategy grid --max-trials 12
tune lgbm-rank --strategy optuna --max-trials N
```

`optuna_search.py` 中 `require_optuna()` 缺依赖时抛出明确错误：`Optuna is required for --strategy optuna`。

- [ ] **Step 5: 验证通过并提交**

Run: `python -m unittest tests/test_lgbm_tuning.py`

Expected: PASS。

```bash
git add ml/tuning ml/cli.py tests/test_lgbm_tuning.py
git commit -m "feat: add lgbm rank tuning cli"
```

---

### Task 9: 迁移 Scoring 和 Diagnostics 命令

**Files:**
- Create: `ml/scoring/__init__.py`
- Create: `ml/scoring/export_lgbm_scores.py`
- Create: `ml/scoring/score_blends.py`
- Create: `ml/diagnostics/__init__.py`
- Create: `ml/diagnostics/controlled_rerank.py`
- Modify: `ml/cli.py`
- Modify: `tests/test_lgbm_score_export.py`
- Modify: `tests/test_lgbm_score_blends.py`
- Modify: `tests/test_controlled_rerank_diagnostics.py`
- Delete: scoring/diagnostics old scripts

- [ ] **Step 1: 迁移 import 并运行失败测试**

测试改为从以下模块导入：

```text
ml.scoring.export_lgbm_scores
ml.scoring.score_blends
ml.diagnostics.controlled_rerank
```

Run: `python -m unittest tests/test_lgbm_score_export.py tests/test_lgbm_score_blends.py tests/test_controlled_rerank_diagnostics.py`

Expected: FAIL，缺少新模块。

- [ ] **Step 2: 搬迁实现并注册 CLI**

移动：

```text
scripts/ml/export_lgbm_scores.py -> ml/scoring/export_lgbm_scores.py
scripts/ml/evaluate_lgbm_score_blends.py -> ml/scoring/score_blends.py
scripts/ml/controlled_rerank_diagnostics.py -> ml/diagnostics/controlled_rerank.py
```

注册命令：

```text
score export-lgbm
score evaluate-blends
diagnostics controlled-rerank
```

- [ ] **Step 3: 验证、删除旧入口、提交**

Run: `python -m unittest tests/test_lgbm_score_export.py tests/test_lgbm_score_blends.py tests/test_controlled_rerank_diagnostics.py`

Expected: PASS。

Run: `rm scripts/ml/export_lgbm_scores.py scripts/ml/evaluate_lgbm_score_blends.py scripts/ml/controlled_rerank_diagnostics.py`

Run: `rg "scripts.ml.export_lgbm_scores|scripts.ml.evaluate_lgbm_score_blends|scripts.ml.controlled_rerank_diagnostics|scripts/ml/export_lgbm_scores.py|scripts/ml/evaluate_lgbm_score_blends.py|scripts/ml/controlled_rerank_diagnostics.py" tests docs .agents ml`

Expected: 没有输出。

```bash
git add ml/scoring ml/diagnostics ml/cli.py tests/test_lgbm_score_export.py tests/test_lgbm_score_blends.py tests/test_controlled_rerank_diagnostics.py scripts/ml/export_lgbm_scores.py scripts/ml/evaluate_lgbm_score_blends.py scripts/ml/controlled_rerank_diagnostics.py
git commit -m "feat: migrate scoring and diagnostics cli"
```

---

### Task 10: 迁移 Model Ops 和 Status

**Files:**
- Create: `ml/model_ops/__init__.py`
- Create: `ml/model_ops/validate.py`
- Create: `ml/model_ops/promote.py`
- Create: `ml/model_ops/status.py`
- Create: `ml/model_ops/archive.py`
- Modify: `ml/cli.py`
- Modify: `tests/test_lgbm_model_promotion.py`
- Create: `tests/test_model_ops.py`
- Delete: `scripts/ml/promote_lgbm_model.py`
- Delete: `scripts/model_maintenance.sh`

- [ ] **Step 1: 写 status 失败测试**

创建 `tests/test_model_ops.py`，构造临时 `runtime/models/b2/model_card.json`、`model_metadata.json`、`model.txt`，调用：

```python
rc = main(["model", "status", "--method", "b2", "--runtime-root", str(root)])
self.assertEqual(rc, 0)
self.assertIn("生产路由总览: b2", stdout.getvalue())
self.assertIn("发布版本: v1", stdout.getvalue())
```

- [ ] **Step 2: 迁移 promotion 测试 import 并运行失败测试**

`tests/test_lgbm_model_promotion.py` 改为：

```python
from ml.model_ops import promote as promote_lgbm_model
```

Run: `python -m unittest tests/test_model_ops.py tests/test_lgbm_model_promotion.py`

Expected: FAIL，缺少 model ops。

- [ ] **Step 3: 搬迁 promote 和 status**

拆分：

```text
validate.py: read_json, validate_metadata, validate_report, validate_model_routing_manifest, validate_model_artifacts
archive.py: archive discovery, archive path helpers
promote.py: promote, dry-run, rollback, list archives, CLI parser
status.py: 原 scripts/model_maintenance.sh 内嵌 Python status 逻辑
```

注册命令：

```text
model status
model archives
model dry-run-promote
model promote
model rollback
```

- [ ] **Step 4: 验证、删除旧入口、提交**

Run: `python -m unittest tests/test_model_ops.py tests/test_lgbm_model_promotion.py`

Expected: PASS。

Run: `rm scripts/ml/promote_lgbm_model.py scripts/model_maintenance.sh`

Run: `rg "promote_lgbm_model.py|model_maintenance.sh|scripts.ml.promote_lgbm_model" tests docs .agents scripts ml`

Expected: 实现文件、测试和操作文档不再引用旧入口。

```bash
git add ml/model_ops ml/cli.py tests/test_model_ops.py tests/test_lgbm_model_promotion.py scripts/ml/promote_lgbm_model.py scripts/model_maintenance.sh
git commit -m "feat: migrate model operations to ml cli"
```

---

### Task 11: 删除旧训练脚本并迁移剩余训练测试

**Files:**
- Delete: `scripts/ml/train_rank_lgbm.py`
- Modify: `tests/test_rank_lgbm.py`
- Modify: `tests/test_native_categorical_parity.py`
- Modify: `tests/test_ml_documentation.py`

- [ ] **Step 1: 搜索旧训练引用**

Run: `rg "scripts.ml.train_rank_lgbm|train_rank_lgbm.py|scripts/ml/train_rank_lgbm.py" tests ml docs .agents`

Expected: 输出列出仍需迁移位置。

- [ ] **Step 2: 迁移或删除 `tests/test_rank_lgbm.py`**

把仍有价值但未迁移的用例移到：

```text
tests/test_lgbm_training_features.py
tests/test_lgbm_training_evaluation.py
tests/test_lgbm_training_report.py
tests/test_lgbm_tuning.py
```

如果 `tests/test_rank_lgbm.py` 只剩旧聚合 import，删除该文件；如果保留，文件中只能从 `ml.*` import。

- [ ] **Step 3: 迁移 parity 测试 import**

`tests/test_native_categorical_parity.py` 改为从 `ml.training.matrices` 和 `ml.scoring.export_lgbm_scores` 导入。

- [ ] **Step 4: 删除旧训练脚本并验证**

Run: `rm scripts/ml/train_rank_lgbm.py`

Run: `rg "scripts.ml.train_rank_lgbm|train_rank_lgbm.py|scripts/ml/train_rank_lgbm.py" tests ml docs .agents`

Expected: 只允许出现在 spec/plan 历史设计文件中。

Run: `python -m unittest tests/test_lgbm_training_features.py tests/test_lgbm_training_evaluation.py tests/test_lgbm_training_report.py tests/test_lgbm_tuning.py tests/test_native_categorical_parity.py`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add tests/test_rank_lgbm.py tests/test_native_categorical_parity.py tests/test_ml_documentation.py scripts/ml/train_rank_lgbm.py
git commit -m "refactor: remove legacy lgbm training script"
```

---

### Task 12: 更新文档、Skill 和最终验证

**Files:**
- Modify: `docs/model.md`
- Modify: `docs/workflow.md`
- Modify: `docs/roadmap.md`
- Modify: `.agents/skills/model-maintenance/SKILL.md`
- Modify: `.agents/skills/model-maintenance/references/model-maintenance.md`
- Modify: `tests/test_ml_documentation.py`

- [ ] **Step 1: 写文档失败测试**

在 `tests/test_ml_documentation.py` 增加：

```python
def test_docs_use_ml_cli(self):
    paths = [
        Path("docs/model.md"),
        Path("docs/workflow.md"),
        Path(".agents/skills/model-maintenance/SKILL.md"),
        Path(".agents/skills/model-maintenance/references/model-maintenance.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    self.assertIn("stock-select-ml train lgbm-rank", combined)
    self.assertIn("stock-select-ml model dry-run-promote", combined)
    self.assertNotIn("scripts/ml/train_rank_lgbm.py", combined)
    self.assertNotIn("scripts/model_maintenance.sh", combined)
    self.assertNotIn("scripts/backfill_run.py", combined)
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m unittest tests/test_ml_documentation.py`

Expected: FAIL，旧命令仍存在。

- [ ] **Step 3: 更新文档和 skill**

替换命令：

```text
uv run scripts/ml/backfill_candidates.py -> uv run stock-select-ml backfill candidates
uv run scripts/ml/build_rank_dataset.py -> uv run stock-select-ml dataset build
uv run scripts/ml/train_rank_lgbm.py -> uv run stock-select-ml train lgbm-rank
uv run scripts/ml/export_lgbm_scores.py -> uv run stock-select-ml score export-lgbm
uv run scripts/ml/promote_lgbm_model.py -> uv run stock-select-ml model promote / dry-run-promote / rollback
scripts/model_maintenance.sh -> uv run stock-select-ml model
scripts/backfill_run.py -> uv run stock-select-ml backfill runs
```

训练文档补充参数：`boosting_type`、`eval_at`、`top_k`、`early_stopping_rounds`、`bagging_fraction`、`feature_fraction`、`lambda_l1`、`lambda_l2`。model-maintenance skill 中默认调参改为 `tune lgbm-rank --strategy grid --max-trials 12`，Optuna 仅在用户明确要求精搜时使用。

- [ ] **Step 4: 删除空目录并全局检查**

Run: `find scripts/ml -type f -maxdepth 1 -print`

Expected: 没有输出。

Run: `rm -rf scripts/ml/__pycache__ && rmdir scripts/ml`

Expected: 命令成功。

Run: `rg "scripts/ml|model_maintenance.sh|backfill_run.py|scripts\.ml" . --glob '!docs/superpowers/specs/*' --glob '!docs/superpowers/plans/*'`

Expected: 没有旧入口引用。

- [ ] **Step 5: 完整验证**

Run:

```bash
python -m unittest \
  tests/test_ml_common.py \
  tests/test_ml_cli.py \
  tests/test_backfill_cli.py \
  tests/test_candidate_backfill.py \
  tests/test_run_backfill.py \
  tests/test_rank_dataset.py \
  tests/test_lgbm_training_features.py \
  tests/test_lgbm_training_evaluation.py \
  tests/test_lgbm_training_report.py \
  tests/test_lgbm_tuning.py \
  tests/test_lgbm_score_export.py \
  tests/test_lgbm_score_blends.py \
  tests/test_controlled_rerank_diagnostics.py \
  tests/test_model_ops.py \
  tests/test_lgbm_model_promotion.py \
  tests/test_native_categorical_parity.py \
  tests/test_ml_documentation.py
```

Expected: PASS。

Run: `python -m py_compile $(find ml -name '*.py' -print)`

Expected: PASS。

Run: `cargo fmt --check`

Expected: PASS。

Run: `cargo test --quiet`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add docs/model.md docs/workflow.md docs/roadmap.md .agents/skills/model-maintenance/SKILL.md .agents/skills/model-maintenance/references/model-maintenance.md tests/test_ml_documentation.py scripts/ml
git commit -m "docs: update model maintenance for ml cli"
```

---

## 自检结果

- Spec 覆盖：package/CLI、backfill、dataset、training、Top-K/eval_at/early stopping、tuning grid/Optuna、score、diagnostics、model ops、旧脚本删除和文档更新均有对应任务。
- 无兼容策略：Task 3、4、9、10、11、12 明确删除旧脚本，不创建 wrapper。
- TDD：每个功能阶段先写或迁移失败测试，再实现，再验证。
- 风险控制：每阶段都有单元测试和阶段提交，最终有旧入口 `rg` 检查和完整 Python/Rust 验证。
