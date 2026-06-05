---
name: model-maintenance
description: Use when retraining, validating, exporting, promoting, rolling back, or inspecting stock-select-new model artifacts.
---

# Model Maintenance

本 skill 用于新 Rust CLI 仓库的模型维护。当前已落地的是 b2 LightGBM；训练维护脚本按 `--method` 组织，后续如接入其他方法或筛选维护流程，复用同一批脚本并按 method 增加配置章节。生产 `run/review` 仍只走 Rust，不接入 Python predict。

## 边界

- 默认发布目标来自当前仓库 `.env` 的 `STOCK_SELECT_RUNTIME_ROOT`，发布到 `<runtime>/models/<method>/`。
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

uv run scripts/ml/backfill_candidates.py \
  --method "$METHOD" \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE" \
  --workers 4
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
uv run scripts/ml/backfill_candidates.py \
  --method "$METHOD" \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE" \
  --workers 4 \
  --dry-run
```

构建 dataset：

```bash
uv run scripts/ml/build_rank_dataset.py \
  --method "$METHOD" \
  --runtime-root "$STOCK_SELECT_RUNTIME_ROOT" \
  --source candidates \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE"
```

训练并输出 report：

```bash
uv run scripts/ml/train_rank_lgbm.py \
  --method "$METHOD" \
  --dataset "diagnostics/ml/$METHOD/rank_dataset.csv" \
  --output-dir "diagnostics/ml/$METHOD/model" \
  --feature-set raw_numeric \
  --num-leaves 9 \
  --min-data-in-leaf 120 \
  --num-boost-round 60 \
  --learning-rate 0.05 \
  --num-threads 4 \
  --rolling-folds 5 \
  --rolling-train-dates 240 \
  --rolling-test-dates 40
```

用户要求训练、重训或调参且没有明确要求“只跑一次”时，默认执行受限自迭代调参：在小网格内最多 12 组 trial，逐个读取 report 比较 rolling 指标。样本不足、label 覆盖不足、关键指标明显劣化或连续多组没有改善时停止；选择候选后只做 export 和 promote dry-run，不自动发布。

训练结束必须向用户汇报模型效果，不只说“训练成功”。汇报至少包含 dataset 覆盖质量、每个 trial 的 rolling 指标、最佳 trial 参数、top features、是否建议发布、promote dry-run 结果和剩余风险；字段清单见 reference。

导出 score CSV 和候选模型产物：

```bash
uv run scripts/ml/export_lgbm_scores.py \
  --method "$METHOD" \
  --model-output-dir "diagnostics/ml/$METHOD/model"
```

发布前先看 dataset summary 和训练 report。短窗口试训即使能成功训练，只要样本日期少、label 覆盖不足，或 `top3_ret3_le_0_rate` 明显偏高，就只保留为 diagnostics，不发布。

发布前 dry-run：

```bash
uv run scripts/ml/promote_lgbm_model.py \
  --method "$METHOD" \
  --candidate-dir "diagnostics/ml/$METHOD/model" \
  --dry-run \
  --require-report
```

发布和回滚：

```bash
uv run scripts/ml/promote_lgbm_model.py \
  --method "$METHOD" \
  --candidate-dir "diagnostics/ml/$METHOD/model" \
  --require-report

uv run scripts/ml/promote_lgbm_model.py \
  --method "$METHOD" \
  --rollback <archive-version>
```

## 验证

```bash
python -m unittest tests/test_candidate_backfill.py tests/test_rank_dataset.py tests/test_rank_lgbm.py tests/test_lgbm_score_export.py tests/test_lgbm_model_promotion.py
python -m py_compile scripts/ml/backfill_candidates.py scripts/ml/build_rank_dataset.py scripts/ml/train_rank_lgbm.py scripts/ml/export_lgbm_scores.py scripts/ml/promote_lgbm_model.py
cargo fmt --check
cargo test --quiet
```

更多目录和产物约定见 `references/model-maintenance.md`。
