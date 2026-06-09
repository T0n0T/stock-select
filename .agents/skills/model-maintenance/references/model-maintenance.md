# LightGBM Model Maintenance Reference

## 当前目录约定

训练维护产物：

```text
<runtime>/candidates/<date>.<method>.json
diagnostics/ml/<method>/rank_dataset.csv
diagnostics/ml/<method>/rank_dataset_summary.json
diagnostics/ml/<method>/model/lgbm_rank_report*.json
diagnostics/ml/<method>/model/lgbm_rank_report*.md
diagnostics/ml/<method>/model/rf_feature_diagnostics.json
diagnostics/ml/<method>/model/rf_feature_diagnostics.md
diagnostics/ml/<method>/model/model.txt
diagnostics/ml/<method>/model/model_metadata.json
diagnostics/ml/<method>/lgbm_scores.csv
diagnostics/ml/<method>/lgbm_scores_summary.json
```

发布产物：

```text
<runtime>/models/<method>/model.txt
<runtime>/models/<method>/model_metadata.json
<runtime>/models/<method>/model_card.json
<runtime>/models/archive/<method>/<version>/
<runtime>/models/archive/<method>/rollback-current-<version>/
```

`promote_lgbm_model.py` 默认从当前目录 `.env` 读取：

```text
STOCK_SELECT_RUNTIME_ROOT=<runtime>
```

未传 `--target-dir` 时发布到 `<runtime>/models/<method>/`。没有 `.env` runtime 且未传 `--runtime-root` 时应失败，避免误发布到旧默认目录。

统一入口 shell 脚本：

```bash
scripts/model_maintenance.sh --method "$METHOD" status
scripts/model_maintenance.sh --method "$METHOD" archives
scripts/model_maintenance.sh --method "$METHOD" promote <candidate_dir>
scripts/model_maintenance.sh --method "$METHOD" dry-run-promote <candidate_dir>
scripts/model_maintenance.sh --method "$METHOD" switch <archive_version>
```

其中：

- `status` 读取当前激活模型摘要
- `archives` 列出 `<runtime>/models/archive/<method>/` 下可切换的历史模型；旧版共享 archive 只有在 `model_card.json` 的 target method 匹配时才兼容列出
- `switch` 是 `promote_lgbm_model.py --rollback <version>` 的用户友好封装

## 历史 Candidate 补齐

重训默认入口是 EOD candidate artifact。训练窗口必须在本次训练开始时显式确定；默认取截至 `TRAIN_END_DATE` 的近一年 EOD 数据，得到 `TRAIN_START_DATE`，不要依赖脚本内置日期。若训练窗口缺少 `<runtime>/candidates/<date>.<method>.json`，先运行：

```bash
uv run scripts/ml/backfill_candidates.py \
  --method "$METHOD" \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE" \
  --workers 16
```

脚本从 PostgreSQL `daily_market` 查询交易日，并发执行：

```text
stock-select-rs screen --method <method> --pick-date <date> --runtime-root <runtime>
```

关键约定：

- 默认跳过已有 `<date>.<method>.json`；`<date>.intraday.<method>.json` 不算 EOD 训练样本。
- `--dry-run` 只打印将执行的 screen 命令，不调用真实 CLI。
- `--recompute` 会强制每个 screen 重新读取数据源，不复用已有 prepared cache。
- `--workers` 控制并发 screen 数；执行模型训练、候选补齐、因子补齐前先查看机器可用核心数，并至少使用最大可用核心数的 1/2，除非用户明确指定更低并发或机器负载不允许。
- 脚本从 `.env`、shell 环境或 CLI 参数读取 `POSTGRES_DSN`，但不会把 DSN/token 放到 screen 命令行。
- 脚本默认 `--method b2`；后续其他 method 接入 `screen` 后复用同一个 `backfill_candidates.py --method <method>`，不新增 method 专属补数据脚本。

## Dataset 输入

`build_rank_dataset.py` 默认读取当前 candidate artifact：

```text
<runtime>/candidates/<date>.<method>.json
```

脚本用候选代码作为训练样本，用数据库行情只补前向收益 label；训练因子统一读取 Rust 生成的 runtime factor artifact：

```text
<runtime>/factors/<artifact_key>.<method>/factors.json
<runtime>/factors/<artifact_key>.<method>/manifest.json
```

`candidate` 和 `select` source 都从这个目录装载因子，避免 Python 重复实现 MA、ZX、MACD、异常放量等自实现因子。缺少 factor artifact 时不要硬训，先运行 `stock-select-rs screen --method <method> --pick-date <date> --export-factors` 补齐；`run` 也会在 select 前写同一份 runtime factor artifact。

如果要回放线上实际 `run` 时的特征快照，可显式传 `--source select`，读取：

```text
<runtime>/select/<date>.<method>/run.json
<runtime>/select/<date>.<method>/display.json
```

`select` 模式用于 diagnostics，不是重训默认入口。`model_score/model_rank` 不会作为训练特征；`select/<key>/factors.json` 只保留为兼容副本，不是 dataset 的主因子来源。

大区间重训示例：

```bash
uv run scripts/ml/build_rank_dataset.py \
  --method "$METHOD" \
  --runtime-root "$STOCK_SELECT_RUNTIME_ROOT" \
  --source candidates \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE" \
  --output-dir "diagnostics/ml/$METHOD"
```

构建后先检查 `rank_dataset_summary.json`：

- `rows` 和 `date_count` 要覆盖目标训练窗口，不能只剩很短试训窗口。
- `ret3`、`ret5` label 覆盖率要足够；越靠近窗口末尾，前向 label 缺失越正常。
- `missing_price_row_count` 异常升高时，先查 candidate code 与行情表覆盖，不进入训练调参。

## 训练调参与发布判断

默认规则：用户要求训练、重训或调参时，若没有明确说“只跑一次”，就执行受限自迭代调参。不要做无上限搜索，不要自动发布。

小网格比较：

```text
feature_set: raw_numeric, raw_plus_signal, raw_plus_signal_macd
label_column: rank_label_3d, rank_label_5d
num_leaves: 5, 9, 15
min_data_in_leaf: 30, 60, 120, 240
```

推荐 trial 顺序：

```text
1. raw_numeric + rank_label_3d + leaves=9  + min_leaf=120
2. raw_numeric + rank_label_3d + leaves=5  + min_leaf=120
3. raw_numeric + rank_label_3d + leaves=15 + min_leaf=120
4. raw_numeric + rank_label_3d + leaves=9  + min_leaf=60
5. raw_numeric + rank_label_3d + leaves=9  + min_leaf=240
6. raw_plus_signal + rank_label_3d + leaves=9 + min_leaf=120
7. raw_plus_signal_macd + rank_label_3d + leaves=9 + min_leaf=120
8. raw_numeric + rank_label_5d + leaves=9 + min_leaf=120
```

样本量充足且前 8 组有可用改善时，再扩展到最多 12 组；否则停止并总结数据缺口。每组写到独立目录，例如：

```bash
uv run scripts/ml/train_rank_lgbm.py \
  --method "$METHOD" \
  --dataset "diagnostics/ml/$METHOD/rank_dataset.csv" \
  --output-dir "diagnostics/ml/$METHOD/tuning/trial-001" \
  --feature-set raw_numeric \
  --label-column rank_label_3d \
  --num-leaves 9 \
  --min-data-in-leaf 120 \
  --num-boost-round 60 \
  --learning-rate 0.05 \
  --num-threads 16 \
  --rolling-folds 5 \
  --rolling-train-dates 240 \
  --rolling-test-dates 40
```

每个 trial 默认先运行随机森林因子诊断，再训练 LightGBM。诊断使用同一份 feature set、one-hot levels、时间切分和 label，输出：

```text
rf_feature_diagnostics.json
rf_feature_diagnostics.md
```

LightGBM report 会写入 `rf_diagnostics` 摘要。该随机森林诊断只用于训练前确认因子有效性和汇报，不进入生产推理；只有显式配置 `--rf-min-oob-score` 或 `--rf-min-test-rank-ic-ret3` 时，`rf_diagnostics.status=failed_threshold` 才会阻止 LightGBM 训练。快速冒烟可传 `--skip-rf-diagnostics`，正式候选 trial 不建议跳过。

`train_rank_lgbm.py` 主训练路径应直接在 `output_dir` 写出：

```text
feature_manifest.json
model.txt
model_metadata.json
lgbm_rank_report*.json
lgbm_rank_report*.md
rf_feature_diagnostics.json
rf_feature_diagnostics.md
```

这样 rolling trial 目录可以直接拿去做 `promote_lgbm_model.py --dry-run`；`export_lgbm_scores.py` 只在需要补特定 score window 或额外 score CSV 时再跑。传入 `--model-output-dir diagnostics/ml/<method>/tuning/<trial>` 时，默认读取同一 trial 下的 `feature_manifest.json`，并把 `lgbm_scores.csv`、`lgbm_scores_summary.json` 写回该 trial 目录，dataset 仍来自 `diagnostics/ml/<method>/rank_dataset.csv`。

训练 report 至少检查：

- `rank_ic_ret3`
- `top3_ret3_positive_rate`
- `top3_ret3_le_0_rate`
- `top3_ret3_ge_5_rate`

随机森林因子诊断至少检查：

- `rf_diagnostics.status`
- `rf_diagnostics.oob_score`
- `rf_diagnostics.metrics.test.rank_ic_ret3`
- `rf_diagnostics.top_features`
- `rf_diagnostics.low_importance_feature_count`

候选选择优先级：

1. rolling `top3_ret3_le_0_rate` 更低。
2. rolling `top3_ret3_positive_rate` 更高。
3. rolling `top3_ret3_ge_5_rate` 和 `rank_ic_ret3` 更高。
4. 3 日目标接近时再看 `top3_ret5_ge_5_rate` 和 `rank_ic_ret5`。
5. 指标接近时选择更简单模型：更少 categorical、更小 `num_leaves`、更大的 `min_data_in_leaf`。

停止条件：

- dataset `date_count` 太少，或 `ret3`/`ret5` label 覆盖不足。
- `missing_price_row_count` 异常，说明候选与行情数据不一致。
- rolling fold 数不足，或 walk-forward split 无法构建。
- 配置了随机森林阈值且 `rf_diagnostics.status=failed_threshold`。
- 连续 4 组 trial 没有改善。
- top3 非正收益比例明显偏高，或 rolling 指标整体不可接受。

短窗口试训、样本日期少或 `top3_ret3_le_0_rate` 明显偏高时，不发布；只把 report、score CSV 和模型候选保留在 `diagnostics/ml/<method>/` 用于定位。

选出候选 trial 后执行：

```bash
uv run scripts/ml/export_lgbm_scores.py \
  --method "$METHOD" \
  --model-output-dir "diagnostics/ml/$METHOD/tuning/<winning-trial>"

uv run scripts/ml/promote_lgbm_model.py \
  --method "$METHOD" \
  --candidate-dir "diagnostics/ml/$METHOD/tuning/<winning-trial>" \
  --dry-run \
  --require-report
```

也可以直接走 shell 入口：

```bash
scripts/model_maintenance.sh --method "$METHOD" dry-run-promote "diagnostics/ml/$METHOD/tuning/<winning-trial>"
scripts/model_maintenance.sh --method "$METHOD" promote "diagnostics/ml/$METHOD/tuning/<winning-trial>"
scripts/model_maintenance.sh --method "$METHOD" archives
scripts/model_maintenance.sh --method "$METHOD" switch <archive-version>
```

只有用户明确确认发布时，才去掉 `--dry-run`。

## 训练完成汇报

训练、重训或调参结束后，必须给出模型效果摘要。不要只说命令成功；即使命令失败，也要说明停在哪一步和可恢复的下一步。汇报时不要打印 `.env`、DSN、token 的具体值。

至少包含：

```text
dataset:
  row_count
  date_count
  symbol_count
  env_counts
  label_non_null_counts
  missing_price_row_count

best_trial:
  output_dir
  feature_set
  label_column
  train_mode
  feature_count
  num_leaves
  min_data_in_leaf
  num_boost_round
  learning_rate

rolling_summary:
  fold_count
  train_date_count
  test_date_count
  test_avg.top3_ret3_positive_rate
  test_avg.top3_ret3_ge_5_rate
  test_avg.top3_ret3_le_0_rate
  test_avg.rank_ic_ret3
  test_avg.top3_ret5_ge_5_rate
  test_avg.rank_ic_ret5

diagnostics:
  rf_diagnostics.status
  rf_diagnostics.oob_score
  rf_diagnostics.metrics.test.rank_ic_ret3
  rf_diagnostics.metrics.test.top3_ret3_positive_rate
  rf_diagnostics.top_features
  rf_diagnostics.low_importance_feature_count
  top_features
  by_env weak/neutral/strong if present
  by_month weak months if present
  promote_dry_run status
  publish_recommendation
  remaining_risks
```

推荐汇报格式：

```text
训练结果：建议发布/不建议发布/需要补数据后重训

数据覆盖：
- rows=...
- date_count=...
- label_non_null_counts=...
- missing_price_row_count=...

最佳 trial：
- path=...
- feature_set=...
- label_column=...
- params=...

Rolling 平均：
- top3_ret3_positive_rate=...
- top3_ret3_ge_5_rate=...
- top3_ret3_le_0_rate=...
- rank_ic_ret3=...
- top3_ret5_ge_5_rate=...
- rank_ic_ret5=...

随机森林因子诊断：
- status=...
- oob_score=...
- test_rank_ic_ret3=...
- top_features=...
- low_importance_feature_count=...

解释与风险：
- top_features=...
- by_env/by_month 弱点=...
- dry-run=...
- 剩余风险=...
```

## Metadata Contract

Rust runtime 必需字段：

```text
numeric_columns
categorical_columns
categorical_levels
feature_names
```

发布校验还要求：

```text
label_column
train_start
train_end
score_start
score_end
model_params
```

`feature_names` 必须等于 Rust 根据 metadata 展开的顺序：先 `numeric_columns`，再按 `categorical_columns` 和 `categorical_levels` 展开为 `<column>=<level>`。

## 禁止事项

- 不把 Python predict 接入 `stock-select-rs run/review`。
- 不发布到旧长目录。
- 不从旧 `reviews/` 构建默认 dataset。
- 不提交 `diagnostics/` 下的大模型、大 CSV 或临时实验输出。
