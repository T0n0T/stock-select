# Python ML CLI 重构设计

## 背景

当前模型训练和维护入口分散在 `scripts/ml/*.py`、`scripts/model_maintenance.sh` 和 `scripts/backfill_run.py` 中。`scripts/ml/train_rank_lgbm.py` 已经承担特征选择、随机森林诊断、LightGBM 训练、rolling validation、报告和模型产物写入等职责，文件体量过大；`scripts/model_maintenance.sh` 还内嵌了一段较长的 Python status 逻辑；`backfill_run.py` 与 `backfill_candidates.py` 重复实现了 dotenv、交易日历、并发执行和命令构造逻辑。

本次重构目标是把这些能力收敛为仓库内独立 Python package 和统一 CLI。旧脚本路径不做兼容保留，文档、测试和维护 skill 直接迁到新命令。

## 目标

1. 新增仓库内 Python package `ml`，提供统一入口 `stock-select-ml` 和 `python -m ml`。
2. 覆盖训练、模型维护、score 导出、候选补齐、因子补齐、历史 run 并发补跑等现有动作。
3. 将 LightGBM 排序训练升级为可调参框架：支持 Top-K 评估、`eval_at`、early stopping、排序参数、抗过拟合参数和可选 Optuna。
4. 保持 runtime 产物契约稳定：生产 Rust 推理继续读取 `model.txt`、`model_metadata.json` 和 `feature_manifest.json`。
5. 删除旧散脚本入口及 shell 包装入口，避免双路径维护。

## 非目标

1. 不把 Python 训练系统拆到独立 repo。
2. 不改 Rust 生产推理的模型加载和排序主路径，除非新 metadata 字段需要最小兼容读取。
3. 不自动发布模型；发布仍需要显式 `model promote`，默认提供 dry-run。
4. 不在第一阶段实现无限制自动搜索；Optuna 只作为受控 tuner。

## CLI 形态

推荐命令：

```bash
uv run stock-select-ml <group> <command> [options]
uv run python -m ml <group> <command> [options]
```

命令分组：

```text
stock-select-ml backfill candidates
stock-select-ml backfill runs
stock-select-ml dataset build
stock-select-ml train lgbm-rank
stock-select-ml tune lgbm-rank
stock-select-ml score export-lgbm
stock-select-ml score evaluate-blends
stock-select-ml diagnostics controlled-rerank
stock-select-ml model status
stock-select-ml model archives
stock-select-ml model dry-run-promote
stock-select-ml model promote
stock-select-ml model rollback
```

示例：

```bash
stock-select-ml backfill candidates \
  --method b2 \
  --start-date 2026-01-01 \
  --end-date 2026-06-01 \
  --workers 16 \
  --export-factors

stock-select-ml backfill runs \
  --method b2 \
  --start-date 2026-01-01 \
  --end-date 2026-06-01 \
  --workers 8 \
  --recompute

stock-select-ml train lgbm-rank \
  --method b2 \
  --dataset diagnostics/ml/b2/rank_dataset.csv \
  --output-dir diagnostics/ml/b2/model \
  --feature-set raw_numeric \
  --top-k 3,5,10,20 \
  --eval-at 5,10,20 \
  --lambdarank-truncation-level 20 \
  --early-stopping-rounds 50 \
  --rolling-folds 5 \
  --rolling-train-dates 240 \
  --rolling-test-dates 40

stock-select-ml tune lgbm-rank \
  --method b2 \
  --strategy grid \
  --max-trials 12

stock-select-ml model dry-run-promote \
  --method b2 \
  --candidate-dir diagnostics/ml/b2/model \
  --require-report
```

## 包结构

```text
ml/
  __init__.py
  __main__.py
  cli.py
  config.py
  env.py
  dates.py
  subprocesses.py
  paths.py
  backfill/
    __init__.py
    candidates.py
    runs.py
    commands.py
  dataset/
    __init__.py
    rank_dataset.py
    schema.py
    factors.py
  training/
    __init__.py
    features.py
    matrices.py
    labels.py
    evaluation.py
    rf_diagnostics.py
    lgbm_ranker.py
    reports.py
    artifacts.py
  tuning/
    __init__.py
    configs.py
    grid.py
    optuna_search.py
    objectives.py
  scoring/
    __init__.py
    export_lgbm_scores.py
    score_blends.py
  diagnostics/
    __init__.py
    controlled_rerank.py
  model_ops/
    __init__.py
    validate.py
    promote.py
    status.py
    archive.py
```

`pyproject.toml` 新增 Python package 配置和 console script。项目仍可用 `uv run` 执行，不引入全局安装要求。

依赖分层：基础 CLI、dataset、backfill 和 model ops 依赖放入主依赖；LightGBM、scikit-learn 和 Optuna 作为训练相关依赖管理。Optuna 不是默认训练路径的硬依赖，只有执行 `--strategy optuna` 时才要求可用，并在缺失时输出明确错误。

## 数据和配置约定

`ml.env` 统一负责读取当前目录 `.env`、shell 环境和 CLI 参数。凭据类变量只用于连接和子进程环境，不打印具体值。常用变量包括：

- `STOCK_SELECT_RUNTIME_ROOT`
- `POSTGRES_DSN`
- `TUSHARE_TOKEN`
- `STOCK_SELECT_BIN`
- `STOCK_SELECT_METHOD`

`ml.dates` 统一提供交易日查询和 weekday fallback。候选补齐与 run 补跑复用同一套日期解析、`--dates-file`、`--start-date`、`--end-date` 和 `--workers` 行为。

并发任务执行前仍需由调用方或维护流程查看机器核心数。CLI 默认 worker 不低于 4；用户显式传更低值时尊重用户输入。

## Backfill 设计

`backfill candidates` 迁移 `scripts/ml/backfill_candidates.py` 的能力：

- 从 DB 查询交易日，失败时可兜底 weekday。
- 支持 `--dates-file`、`--skip-existing/--no-skip-existing`、`--recompute`、`--export-factors`、`--pool-source`、`--dry-run`。
- 调用 `stock-select-rs screen`，不把 DSN/token 放入命令行。
- 跳过逻辑只检查 EOD candidate；导出因子时同时检查 factor artifact。

`backfill runs` 迁移 `scripts/backfill_run.py` 的能力：

- 对交易日区间并发调用 `stock-select-rs run`。
- 支持 `--skip-existing/--no-skip-existing`、`--recompute`、`--pool-source`、`--dry-run`。
- 输出每个日期的成功/失败摘要，并对 signal exit 给出可读原因。

两个命令共用 `BackfillConfig`、命令构造、结果对象和并发 runner，减少重复实现。

## Dataset 设计

`dataset build` 迁移 `scripts/ml/build_rank_dataset.py`，并把 schema 常量拆到 `dataset/schema.py`：

- method 对应的 raw numeric、categorical、MACD/context 因子由 schema 统一导出。
- dataset 构建继续以 runtime factor artifact 为训练因子来源。
- `candidate` 和 `select` source 都复用同一因子装载逻辑。
- 输出 `rank_dataset.csv` 和 `rank_dataset_summary.json` 的字段保持稳定。

训练模块只依赖 `dataset.schema` 的公开函数，不再从脚本模块互相 import。

## LightGBM 训练设计

`train lgbm-rank` 迁移并拆分 `train_rank_lgbm.py`：

- `training/features.py`：feature set、manifest 加载、RF 选特征、coverage 校验。
- `training/matrices.py`：one-hot/native categorical 编码、feature name 清洗、metadata matrix 重放。
- `training/labels.py`：rank label 和收益阈值 label。
- `training/evaluation.py`：Top-K 收益指标、RankIC、NDCG@K、分 env/month 诊断。
- `training/rf_diagnostics.py`：随机森林因子诊断和阈值门禁。
- `training/lgbm_ranker.py`：LightGBM Dataset、训练、预测、feature importance。
- `training/reports.py`：JSON/Markdown report。
- `training/artifacts.py`：`model.txt`、`model_metadata.json`、`feature_manifest.json` 写入。

LightGBM 参数层新增：

```text
boosting_type
num_leaves
min_data_in_leaf
learning_rate
num_boost_round
bagging_fraction
bagging_freq
feature_fraction
lambda_l1
lambda_l2
min_gain_to_split
lambdarank_truncation_level
eval_at
early_stopping_rounds
seed
num_threads
```

默认仍偏保守：`boosting_type=gbdt`，`learning_rate=0.05`，`num_leaves` 小范围，采样和正则默认可配置但不强制改变旧行为。`dart` 作为 trial 参数进入 tuning，不直接替代默认。

训练时构造 validation dataset，配置 `valid_sets`、`eval_at` 和 early stopping。report 和 metadata 记录 `best_iteration`、`eval_at`、`top_k`、完整 LightGBM 参数。

## 排序评估设计

现有 report 中固定 `top3_*` 指标升级为多 Top-K：

```text
top3_ret3_positive_rate
top5_ret3_positive_rate
top10_ret3_positive_rate
top20_ret3_positive_rate
topK_ret3_ge_5_rate
topK_ret3_le_0_rate
topK_ret3_ge_5_capture_rate
topK_ret5_ge_5_rate
rank_ic_ret3
rank_ic_ret5
ndcg_at_5
ndcg_at_10
ndcg_at_20
```

`--top-k` 控制收益评估口径，默认 `3,5,10,20`，确保现有 `top3_*` 发布和状态展示口径继续存在。`--eval-at` 控制 LightGBM NDCG 评估口径，默认 `5,10,20`。两者允许分开：例如训练验证看 `5,10,20`，发布决策主看 `top3/top5`。

候选选择优先级迁移为参数化规则：

1. 主 Top-K 的 `ret3_le_0_rate` 更低。
2. 主 Top-K 的 `ret3_positive_rate` 更高。
3. 主 Top-K 的 `ret3_ge_5_rate` 和 `rank_ic_ret3` 更高。
4. 3 日指标接近时看 `ret5`。
5. 指标接近时选择更简单模型。

## Tuning 设计

`tune lgbm-rank` 提供两种策略：

```text
--strategy grid
--strategy optuna
```

`grid` 为默认策略，读取内置 trial schema 或 `--config tuning.json`。默认 trial 先覆盖：

- `feature_set`
- `label_column`
- `num_leaves`
- `min_data_in_leaf`
- `lambdarank_truncation_level`
- `top_k`
- `eval_at`
- `boosting_type`
- `bagging_fraction`
- `feature_fraction`
- `lambda_l1/lambda_l2`

`optuna` 为可选策略，仅负责生成参数。训练、rolling validation、报告、候选排序和发布建议仍走项目内部逻辑。Optuna 约束：

- 必须设置 `--max-trials`。
- 固定 seed。
- 每个 trial 写独立目录。
- 不自动发布。
- objective 使用项目指标组合，不直接使用单一 LightGBM validation 分数。

## 模型维护设计

`model_ops` 迁移 `promote_lgbm_model.py` 和 `model_maintenance.sh` 的能力。

命令：

```text
model status
model archives
model dry-run-promote
model promote
model rollback
```

`model status` 不再通过 shell 内嵌 Python 实现，直接读取 runtime model dir、`model_card.json`、`model_state.json`、routing manifest 和 metadata。输出继续包含：

- eod/intraday 路由状态。
- 模型目录和产物检查。
- 发布版本、训练窗口、打分窗口。
- 特征/标签摘要。
- test 或 rolling 指标。

`dry-run-promote` 和 `promote` 保持现有验证要求：metadata 必填字段、native categorical code maps、routing manifest、report rolling summary、归档目录和 hash。

## Score 和 Diagnostics 设计

`score export-lgbm` 迁移 `export_lgbm_scores.py`：

- 默认从 `model-output-dir` 读取 `feature_manifest.json` 和 metadata。
- 输出 score CSV 和 summary。
- 支持 trial 目录内就地输出。

`score evaluate-blends` 迁移 `evaluate_lgbm_score_blends.py`。

`diagnostics controlled-rerank` 迁移 `controlled_rerank_diagnostics.py`。

这两个命令先做等价迁移，不在第一阶段扩展行为。

## 删除和迁移策略

本重构不保留旧脚本路径兼容。最终删除：

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

删除发生在对应能力迁入新 CLI、测试和文档更新之后。若某一步尚未迁完，不能提前删除入口。

## 测试计划

测试按模块迁移，而不是保留旧脚本 import：

- `tests/test_backfill_cli.py`：candidate/run backfill 参数、命令构造、dry-run、失败收集。
- `tests/test_rank_dataset.py`：dataset schema、summary、factor artifact 读取。
- `tests/test_lgbm_training_features.py`：特征选择、manifest、categorical 编码、coverage。
- `tests/test_lgbm_training_evaluation.py`：Top-K、RankIC、NDCG@K、分区诊断。
- `tests/test_lgbm_training_report.py`：report、metadata、artifacts。
- `tests/test_lgbm_tuning.py`：grid trial 生成、Optuna 缺依赖/受控 trial。
- `tests/test_lgbm_score_export.py`：score export。
- `tests/test_model_ops.py`：status、promote dry-run、rollback、archive。
- `tests/test_ml_cli.py`：`ml.cli.main([...])` smoke tests。
- Rust parity tests 保留，用于校验 native categorical 模型推理一致性。

验证命令：

```bash
python -m unittest tests/test_backfill_cli.py tests/test_rank_dataset.py tests/test_lgbm_training_features.py tests/test_lgbm_training_evaluation.py tests/test_lgbm_training_report.py tests/test_lgbm_tuning.py tests/test_lgbm_score_export.py tests/test_model_ops.py tests/test_ml_cli.py
python -m py_compile $(find ml -name '*.py' -print)
cargo fmt --check
cargo test --quiet
```

## 文档更新

更新以下文档和 skill：

- `docs/model.md`
- `docs/workflow.md`
- `docs/roadmap.md`
- `.agents/skills/model-maintenance/SKILL.md`
- `.agents/skills/model-maintenance/references/model-maintenance.md`

文档中的旧命令全部替换为 `stock-select-ml`。模型训练、调参和发布汇报要求继续保持中文。

## 风险和处理

1. **改动面大**：按能力分阶段迁移，每阶段都保持测试通过。
2. **旧脚本删除导致文档遗漏**：用 `rg "scripts/ml|model_maintenance.sh|backfill_run.py"` 做迁移检查。
3. **Optuna 增加依赖**：Optuna 作为可选依赖；未安装时 `--strategy optuna` 给出明确错误，默认 grid 不受影响。
4. **训练结果变化**：第一阶段等价迁移默认参数，排序增强通过显式参数或 tuning trial 启用。
5. **metadata 契约漂移**：发布 dry-run 和 Rust parity 测试作为门禁。

## 实施分期

1. 建立 `ml` package、CLI 框架、公共 env/date/path/subprocess 模块。
2. 迁移 candidate/run backfill，并删除对应旧入口。
3. 迁移 dataset build 和 schema。
4. 拆分 LightGBM 训练模块，先保持默认行为等价。
5. 引入 Top-K、`eval_at`、early stopping 和新 LightGBM 参数。
6. 实现 `tune lgbm-rank` grid 策略。
7. 接入可选 Optuna 策略。
8. 迁移 score、diagnostics 和 model ops。
9. 删除旧脚本，更新文档和 skill，跑完整验证。
