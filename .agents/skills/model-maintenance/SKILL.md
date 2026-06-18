---
name: model-maintenance
description: Use when retraining, validating, exporting, promoting, rolling back, or inspecting stock-select model artifacts.
---

# Model Maintenance

本 skill 用于新 Rust CLI 仓库的模型维护。LightGBM 训练维护通过 `stock-select-ml` Python CLI 按 `--method` 组织，可维护 b2/b3 等 method 的候选模型产物；生产 `run/review` 仍只走 Rust capability，不接入 Python predict。

## 边界

- 默认发布目标来自当前仓库 `.env` 的 `STOCK_SELECT_RUNTIME_ROOT`，发布到 `<runtime>/models/<method>/`。
- 归档目录按 method 隔离，写入 `<runtime>/models/archive/<method>/<version>/`；旧共享 archive 只在 `model_card.json.target` 匹配当前 method 时兼容读取。
- dataset 默认从当前 `candidates/<date>.<method>.json` 构建样本集合，但训练因子必须来自 Rust 生成的 `<runtime>/factors/<artifact_key>.<method>/factors.json`；`--source select` 只用于回放线上 run/display 样本上下文。
- `diagnostics/ml/<method>/` 下的 dataset、score CSV、report 只用于训练、回测和维护，不进入 Rust 生产推理。
- 不打印 `.env`、DSN、token 的具体值。

## 快速流程

先检查工作区：

```bash
git status --short --branch
```

训练窗口在每次训练时确定，默认取截至 `TRAIN_END_DATE` 的近一年 EOD 数据；不要依赖脚本内置日期。重训前补齐历史 EOD candidates；脚本从 `.env`/环境读取 `POSTGRES_DSN` 和 `STOCK_SELECT_RUNTIME_ROOT`，命令行不携带 DSN/token：

```bash
METHOD=b2

uv run stock-select-ml backfill candidates \
  --method "$METHOD" \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE" \
  --workers 16
```

缺少 factor artifact 时，先为对应日期运行：

```bash
stock-select-rs screen \
  --method "$METHOD" \
  --pick-date <YYYY-MM-DD> \
  --export-factors
```

如需先确认会执行哪些日期：

```bash
uv run stock-select-ml backfill candidates \
  --method "$METHOD" \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE" \
  --workers 16 \
  --dry-run
```

构建 dataset：

```bash
uv run stock-select-ml dataset build \
  --method "$METHOD" \
  --runtime-root "$STOCK_SELECT_RUNTIME_ROOT" \
  --source candidates \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE"
```

默认使用 Optuna 自动调参并输出 trial report。除非用户明确要求 RF/随机森林诊断、RF 阈值门禁或 RF 因子选择，训练命令必须传 `--skip-rf-diagnostics`；不要因为 CLI 默认会跑 RF 就保留它：

```bash
uv run stock-select-ml tune lgbm-rank \
  --method "$METHOD" \
  --dataset "diagnostics/ml/$METHOD/rank_dataset.csv" \
  --output-root "diagnostics/ml/$METHOD/tuning/optuna-<run-id>" \
  --strategy optuna \
  --max-trials 12 \
  --rolling-folds 5 \
  --rolling-train-dates 240 \
  --rolling-test-dates 40 \
  --skip-rf-diagnostics
```

默认先跑一轮不带因子裁剪的 Optuna baseline。随后由 agent 根据 method、schema、特征覆盖、领域含义和 baseline 指标自行决定是否做领域知识裁剪；用户未指定裁剪口径时，不要停下来问。裁剪不使用 RF feature selection 作为默认手段，且必须记录保留/剔除的因子组和理由。若当前 CLI 不支持自定义裁剪后的 Optuna 搜索，只使用已有 `feature_set`/config 能力做粗粒度裁剪，并在汇报中说明限制。

用户要求训练、重训或调参且没有明确要求“只跑一次”时，默认执行受限 Optuna 调参：最多 12 组 trial，逐个读取 report 比较 rolling 指标。样本不足、label 覆盖不足、关键指标明显劣化或连续多组没有改善时停止；选择候选后只做 export 和 promote dry-run，不自动发布。

训练结束必须向用户汇报模型效果，不只说“训练成功”。汇报至少包含 dataset 覆盖质量、每个 trial 的 rolling 指标、最佳 trial 参数、是否跳过 RF 诊断、因子裁剪决策、top features、是否建议发布、promote dry-run 结果和剩余风险；字段清单见 reference。

导出 score CSV 和候选模型产物：

```bash
uv run stock-select-ml score export-lgbm \
  --method "$METHOD" \
  --model-output-dir "diagnostics/ml/$METHOD/model"
```

若 `--model-output-dir` 指向 `diagnostics/ml/$METHOD/tuning/<trial>`，默认 feature manifest、score CSV 和 summary 都跟随该 trial 目录，dataset 仍来自 `diagnostics/ml/$METHOD/rank_dataset.csv`。

发布前先看 dataset summary 和训练 report。短窗口试训即使能成功训练，只要样本日期少、label 覆盖不足，或 `top3_ret3_le_0_rate` 明显偏高，就只保留为 diagnostics，不发布。

发布前 dry-run：

```bash
uv run stock-select-ml model dry-run-promote "diagnostics/ml/$METHOD/model" \
  --method "$METHOD" \
  --require-report
```

发布和回滚：

```bash
uv run stock-select-ml model promote "diagnostics/ml/$METHOD/model" \
  --method "$METHOD" \
  --require-report

uv run stock-select-ml model rollback <archive-version> \
  --method "$METHOD"

uv run stock-select-ml model status --method "$METHOD"
uv run stock-select-ml model archives --method "$METHOD"
```

## 验证

```bash
python -m unittest tests/test_candidate_backfill.py tests/test_rank_dataset.py tests/test_rank_lgbm.py tests/test_lgbm_score_export.py tests/test_lgbm_model_promotion.py
python -m py_compile $(find ml -name '*.py' -print)
cargo fmt --check
cargo test --quiet
```

更多目录和产物约定见 `references/model-maintenance.md`。
