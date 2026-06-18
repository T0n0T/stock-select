# LightGBM Model Maintenance Reference

## 当前目录约定

训练维护产物：

```text
<runtime>/candidates/<date>.<method>.json
diagnostics/ml/<method>/rank_dataset.csv
diagnostics/ml/<method>/rank_dataset_summary.json
diagnostics/ml/<method>/model/lgbm_rank_report*.json
diagnostics/ml/<method>/model/lgbm_rank_report*.md
diagnostics/ml/<method>/model/rf_feature_diagnostics.json  # 仅用户要求 RF 诊断时
diagnostics/ml/<method>/model/rf_feature_diagnostics.md    # 仅用户要求 RF 诊断时
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

`stock-select-ml model` 默认从当前目录 `.env` 读取：

```text
STOCK_SELECT_RUNTIME_ROOT=<runtime>
```

未传 `--target-dir` 时发布到 `<runtime>/models/<method>/`。没有 `.env` runtime 且未传 `--runtime-root` 时应失败，避免误发布到旧默认目录。

统一入口 Python CLI：

```bash
uv run stock-select-ml model status --method "$METHOD"
uv run stock-select-ml model archives --method "$METHOD"
uv run stock-select-ml model dry-run-promote <candidate_dir> --method "$METHOD"
uv run stock-select-ml model promote <candidate_dir> --method "$METHOD"
uv run stock-select-ml model rollback <archive_version> --method "$METHOD"
```

其中：

- `status` 读取当前激活模型摘要
- `archives` 列出 `<runtime>/models/archive/<method>/` 下可切换的历史模型；旧版共享 archive 只有在 `model_card.json` 的 target method 匹配时才兼容列出
- `rollback` 从 `<runtime>/models/archive/<method>/` 切换到指定归档版本

## 历史 Candidate 补齐

重训默认入口是 EOD candidate artifact。训练窗口必须在本次训练开始时显式确定；默认取截至 `TRAIN_END_DATE` 的近一年 EOD 数据，得到 `TRAIN_START_DATE`，不要依赖脚本内置日期。若训练窗口缺少 `<runtime>/candidates/<date>.<method>.json`，先运行：

```bash
uv run stock-select-ml backfill candidates \
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
- CLI 默认 `--method b2`；后续其他 method 接入 `screen` 后复用同一个 `stock-select-ml backfill candidates --method <method>`，不新增 method 专属补数据脚本。

## Dataset 输入

`stock-select-ml dataset build` 默认读取当前 candidate artifact：

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
uv run stock-select-ml dataset build \
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

默认规则：用户要求训练、重训或调参时，若没有明确说“只跑一次”，就执行受限 Optuna 自动调参。不要做无上限搜索，不要自动发布。

RF/随机森林诊断是 opt-in：除非用户明确要求“RF 诊断/随机森林诊断/RF 因子选择/RF 阈值门禁”，训练和调参命令必须传 `--skip-rf-diagnostics`。不要因为 `stock-select-ml train lgbm-rank` 的 CLI 默认会跑 RF 就保留它。RF 诊断只用于额外解释或门禁，不进入生产推理，也不替代 promote dry-run。

默认先跑不带因子裁剪的 Optuna baseline：

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
  --skip-rf-diagnostics \
  --visualize
```

Optuna 默认搜索空间覆盖：

```text
feature_set: raw_numeric, raw_plus_signal, raw_plus_signal_macd
label_column: rank_label_3d, rank_label_5d
num_leaves: 5, 9, 15
min_data_in_leaf: 30, 60, 120, 240
categorical_encoding: one_hot, native
boosting_type: gbdt, dart
num_boost_round, learning_rate, bagging_fraction, feature_fraction, lambda_l1/lambda_l2 等
```

领域知识因子裁剪规则：

- baseline 必须先保留所有当前 feature_set 能覆盖的候选因子，不用 RF feature selection。
- baseline 后由 agent 自行决定是否裁剪；用户未指定裁剪口径时不要停下来问。
- 裁剪优先按 method 与业务含义分组：公共价量/均线/箱体、市场环境、申万行业、资金流、筹码分布、method 专属语义因子等。
- 优先剔除明显不适用于当前 method、覆盖率极低、信息泄露风险高、review-only、重复派生过强或线上实时不可稳定计算的因子。
- 不用 RF 重要性作为默认裁剪依据；若用户明确要求 RF 裁剪，才使用 `--rf-feature-selection` 或 RF 诊断结果。
- 若当前 CLI 只支持 `feature_set` 粗粒度选择而不支持自定义 feature manifest 的 Optuna 搜索，则用 `raw_numeric` / `raw_plus_signal` / `raw_plus_signal_macd` 表达裁剪，并在汇报中说明限制。
- 每次裁剪 trial 必须记录：保留因子组、剔除因子组、理由、与 baseline 的 rolling 指标对比。

Optuna 不可用或用户明确要求小网格时，才使用小网格 fallback；推荐顺序：

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

样本量充足且前 8 组有可用改善时，再扩展到最多 12 组；否则停止并总结数据缺口。小网格 fallback 每组写到独立目录，且默认也跳过 RF 诊断，例如：

```bash
uv run stock-select-ml train lgbm-rank \
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
  --rolling-test-dates 40 \
  --skip-rf-diagnostics
```

只有用户明确要求 RF 诊断时，每个 trial 才先运行随机森林因子诊断，再训练 LightGBM。诊断使用同一份 feature set、one-hot levels、时间切分和 label，输出：

```text
rf_feature_diagnostics.json
rf_feature_diagnostics.md
```

启用 RF 时，LightGBM report 会写入 `rf_diagnostics` 摘要。只有显式配置 `--rf-min-oob-score` 或 `--rf-min-test-rank-ic-ret3` 时，`rf_diagnostics.status=failed_threshold` 才会阻止 LightGBM 训练。默认训练没有 RF 产物，汇报写明 `rf_diagnostics=skipped_by_default`。

分类特征编码：

- 缺省 `categorical_encoding=one_hot`，保持旧模型兼容。
- LightGBM 原生分类试验传 `--categorical-encoding native`。
- `native` 模式下，`feature_manifest.json`、`model_metadata.json` 和 report 都会写入 `categorical_encoding=native`；`model_metadata.json` 必须包含 `categorical_code_maps`。
- Rust runtime 使用 `categorical_code_maps` 把分类值映射成 LightGBM 原生分类整数 code，未知或缺失分类值映射为 `-1`。
- native 模型发布前必须跑 Python/Rust parity 测试和 `stock-select-ml model dry-run-promote --require-report`。

`stock-select-ml train lgbm-rank` 主训练路径应直接在 `output_dir` 写出：

```text
feature_manifest.json
model.txt
model_metadata.json
lgbm_rank_report*.json
lgbm_rank_report*.md
rf_feature_diagnostics.json
rf_feature_diagnostics.md
```

其中 `rf_feature_diagnostics.*` 仅在用户明确要求 RF 诊断时出现。

这样 rolling trial 目录可以直接拿去做 `stock-select-ml model dry-run-promote`；`stock-select-ml score export-lgbm` 只在需要补特定 score window 或额外 score CSV 时再跑。传入 `--model-output-dir diagnostics/ml/<method>/tuning/<trial>` 时，默认读取同一 trial 下的 `feature_manifest.json`，并把 `lgbm_scores.csv`、`lgbm_scores_summary.json` 写回该 trial 目录，dataset 仍来自 `diagnostics/ml/<method>/rank_dataset.csv`。

训练 report 至少检查：

- `rank_ic_ret3`
- `top3_ret3_positive_rate`
- `top3_ret3_le_0_rate`
- `top3_ret3_ge_5_rate`

若启用了随机森林因子诊断，至少检查：

- `rf_diagnostics.status`
- `rf_diagnostics.oob_score`
- `rf_diagnostics.metrics.test.rank_ic_ret3`
- `rf_diagnostics.top_features`
- `rf_diagnostics.low_importance_feature_count`

若未启用 RF，检查并汇报：

- `rf_diagnostics=skipped_by_default`
- `factor_pruning.baseline_no_pruning=true`
- `factor_pruning.domain_pruning_decision`
- 裁剪前后 rolling 指标对比（如执行了裁剪）

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
- 用户明确启用 RF 阈值且 `rf_diagnostics.status=failed_threshold`。
- 连续 4 组 trial 没有改善。
- top3 非正收益比例明显偏高，或 rolling 指标整体不可接受。

短窗口试训、样本日期少或 `top3_ret3_le_0_rate` 明显偏高时，不发布；只把 report、score CSV 和模型候选保留在 `diagnostics/ml/<method>/` 用于定位。

选出候选 trial 后执行：

```bash
uv run stock-select-ml score export-lgbm \
  --method "$METHOD" \
  --model-output-dir "diagnostics/ml/$METHOD/tuning/<winning-trial>"

uv run stock-select-ml model dry-run-promote "diagnostics/ml/$METHOD/tuning/<winning-trial>" \
  --method "$METHOD" \
  --require-report
```

发布和归档查看也走同一 CLI：

```bash
uv run stock-select-ml model promote "diagnostics/ml/$METHOD/tuning/<winning-trial>" --method "$METHOD" --require-report
uv run stock-select-ml model archives --method "$METHOD"
uv run stock-select-ml model rollback <archive-version> --method "$METHOD"
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
  rf_diagnostics: skipped_by_default | enabled
  rf_diagnostics.status                 # 仅启用 RF 时
  rf_diagnostics.oob_score              # 仅启用 RF 时
  rf_diagnostics.metrics.test.rank_ic_ret3  # 仅启用 RF 时
  factor_pruning.baseline_no_pruning
  factor_pruning.domain_pruning_decision
  factor_pruning.kept_groups
  factor_pruning.dropped_groups
  factor_pruning.reasoning
  factor_pruning.metric_delta_if_any
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

RF 诊断与因子裁剪：
- rf_diagnostics=skipped_by_default / enabled
- baseline_no_pruning=...
- domain_pruning_decision=不裁剪/裁剪/仅粗粒度 feature_set 裁剪
- kept_groups=...
- dropped_groups=...
- reasoning=...
- metric_delta=...

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
