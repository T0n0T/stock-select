# 模型系统

## 总览

当前生产主路径是 **b2 LightGBM model-first** 架构。模型使用 LambdaRank 算法训练，对候选股进行排序，`model_rank` 和 `model_score` 决定最终展示顺序。LLM/人工复盘只做 annotation（风险标记、备注），不改 rank。

训练、导出、发布和回滚统一通过 `stock-select-ml` Python CLI 按 `--method` 维护产物，可用于 b2/b3 等类别；生产 `run/review` 是否能实际使用某个 method，取决于 Rust CLI 对该 method 的 capability，不接入 Python predict。

```mermaid
flowchart LR
    BC["stock-select-ml backfill candidates<br/>补齐历史候选"] --> BD["stock-select-ml dataset build<br/>构建样本集 + label"]
    BD --> RF["stock-select-ml train lgbm-rank<br/>随机森林因子诊断"]
    RF --> TR["stock-select-ml train lgbm-rank<br/>LightGBM 训练 + 评估"]

    BC -.-> C["candidates/"]
    BD -.-> D["diagnostics/ml/&lt;method&gt;/"]
    RF -.-> M["diagnostics/ml/&lt;method&gt;/model/"]
    TR -.-> M

    M --> EXP["stock-select-ml score export-lgbm"]
    EXP --> PROM["stock-select-ml model promote"]
    PROM --> R["runtime/models/&lt;method&gt;/<br/>model.txt + model_metadata.json"]
```

## 训练流程

### 1. 补齐历史候选

```bash
METHOD=b2

uv run stock-select-ml backfill candidates \
  --method "$METHOD" \
  --start-date <TRAIN_START> \
  --end-date <TRAIN_END> \
  --workers 16
```

- 从 DB 读取每日行情
- 运行 screen 逻辑生成历史候选
- 写入 `runtime/candidates/<date>.<method>.json`

### 2. 构建训练集

```bash
uv run stock-select-ml dataset build \
  --method "$METHOD" \
  --runtime-root runtime \
  --source candidates \
  --start-date <TRAIN_START> \
  --end-date <TRAIN_END>
```

- 加载候选 → 按 code+date 关联因子
- 从 DB 获取未来 3 日/5 日涨幅作为 label
- 每个交易日独立排序，生成分档标签：

| label | quartile | 含义 |
|-------|----------|------|
| 3 | top 25% | 未来 3 日涨幅最高 |
| 2 | 中上 25% | |
| 1 | 中下 25% | |
| 0 | bottom 25% | 未来 3 日涨幅最低 |

- 输出 CSV 到 `diagnostics/ml/<method>/rank_dataset.csv`

### 3. 训练

```bash
uv run stock-select-ml train lgbm-rank \
  --method "$METHOD" \
  --dataset "diagnostics/ml/$METHOD/rank_dataset.csv" \
  --output-dir "diagnostics/ml/$METHOD/model" \
  --feature-set raw_numeric \
  --num-leaves 9 \
  --min-data-in-leaf 120 \
  --num-boost-round 60 \
  --learning-rate 0.05 \
  --num-threads 16 \
  --rolling-folds 5 \
  --rolling-train-dates 240 \
  --rolling-test-dates 40
```

`stock-select-ml train lgbm-rank` 默认在 LightGBM 前运行随机森林因子诊断，用同一份特征选择、one-hot 编码、时间切分和 label 口径确认因子有效性。诊断产物写入同一输出目录：

```text
diagnostics/ml/<method>/model/rf_feature_diagnostics.json
diagnostics/ml/<method>/model/rf_feature_diagnostics.md
```

LightGBM report 的 `rf_diagnostics` 字段会嵌入随机森林摘要，包括诊断状态、OOB、测试集 RankIC、Top features 和低重要性因子数量。默认情况下随机森林只用于训练前诊断，不进入 Rust 生产推理；快速冒烟或依赖不可用时可传 `--skip-rf-diagnostics` 跳过，但正式候选 trial 应保留诊断。

如果需要让 RF 层实际承担筛选职责，训练时显式传 `--rf-feature-selection cumulative_importance`，并用 `--rf-cumulative-importance-threshold` 和 `--rf-min-selected-features` 控制累计重要性阈值与最小保留数量。开启后，RF 先在候选特征上计算完整重要性，类别 one-hot 重要性会聚合回原始类别列；随后 LightGBM 最终模型、rolling validation、`feature_manifest.json` 和 `model_metadata.json` 都只使用 RF 选中的特征。`rf_feature_diagnostics.json` 会保留完整 `feature_importances`，`top_features` 只作为展示截断列表。

### 3.1 Optuna 调参可视化

`stock-select-ml tune lgbm-rank --strategy optuna` 默认只写 `tuning_summary.json`。需要查看 trial 目标值变化、参数重要性和关键参数分布时，增加 `--visualize`：

```bash
uv run stock-select-ml tune lgbm-rank \
  --method "$METHOD" \
  --dataset "diagnostics/ml/$METHOD/rank_dataset.csv" \
  --output-root "diagnostics/ml/$METHOD/tuning" \
  --strategy optuna \
  --max-trials 24 \
  --visualize
```

默认输出到 `diagnostics/ml/$METHOD/tuning/visualizations/`，可用 `--visual-output-dir <DIR>` 改写目录；当前 `--visual-format` 只支持 `html`。产物包括 `optimization_history.html`、`param_importances.html`、`slice.html`，参数数量足够时还会生成 `parallel_coordinate.html`。`visualizations_summary.json` 记录 `files`、`trial_count`、`best_trial`、`best_value`、`target_metric` 和 `warnings`；单个图生成失败只写入 warning，不会让已完成的调参结果失败。若可视化目录创建或 `visualizations_summary.json` 写入失败，主 `tuning_summary.json` 仍会落盘，并在主 summary 的 `warnings` 中记录失败原因。

## factors.json 训练特征契约

`factors.json` 的 `rows[].factors` 只承载训练候选特征：数值因子、布尔因子和低基数类别因子。review-only 评分字段不进入 `rows[].factors`，包括 `trend_structure`、`price_position`、`volume_behavior`、`previous_abnormal_move`、`weekly_daily_combo_score`、`total_score` 和 `verdict`。

允许保留的训练语义字段必须被 schema 明确确认，例如数值字段 `macd_phase`、`daily_macd_wave_index`、`weekly_macd_wave_index`，原始位置字段 `box_mid_position_120d_pct`，以及类别字段 `signal_type`、`daily_macd_phase_type`、`daily_macd_wave_stage`、`weekly_macd_phase_type`、`weekly_macd_wave_stage`、`weekly_daily_combo_type` 和 `midline_state`。这些字段由 RF 和 LightGBM 共用同一份特征选择逻辑。

训练前会生成并校验 `feature_coverage`：每个被选中的训练特征必须在数据集中至少有一个非空值。若确认训练的特征 zero coverage，训练会失败并输出缺失列表，避免 schema 中的因子没有真实进入 RF/LightGBM。

可选门禁参数：

| 参数 | 说明 |
|------|------|
| `--rf-min-oob-score` | OOB 低于阈值时停止 LightGBM 训练 |
| `--rf-min-test-rank-ic-ret3` | 随机森林测试集 `rank_ic_ret3` 低于阈值时停止 LightGBM 训练 |

训练参数：

| 参数 | 值 | 说明 |
|------|------|------|
| objective | `lambdarank` | 排序学习目标 |
| metric | `ndcg` | 归一化折损累积增益 |
| label_gain | `[0, 1, 3, 7]` | label 0→0, 1→1, 2→3, 3→7 |
| num_leaves | 9 | 树叶子节点数 |
| min_data_in_leaf | 120 | 叶子最少样本 |
| num_boost_round | 60 | 迭代轮数 |
| seed | 17 | 随机种子 |

### LightGBM 分类特征编码

模型元数据通过 `categorical_encoding` 声明分类特征编码方式：

- `one_hot`：默认兼容模式。Rust runtime 按 `categorical_columns` 和 `categorical_levels` 展开为 `column=level` 的 0/1 特征，旧模型缺少该字段时按此模式处理。
- `native`：LightGBM 原生分类模式。Python 训练将分类值编码为稳定整数并传入 `categorical_feature`；Rust runtime 按 `categorical_code_maps` 将分类值映射为同一整数 code。

native 模型必须包含：

- `categorical_encoding`
- `categorical_columns`
- `categorical_levels`
- `categorical_code_maps`
- `feature_names`

native 模型的 `feature_names` 必须等于 `numeric_columns + categorical_columns`。未知或缺失分类值编码为 `-1`，由 LightGBM 按 missing categorical 处理。发布脚本会校验 `categorical_code_maps` 是否完整覆盖 `categorical_levels`，且 code 是否从 0 连续递增。

评估指标：

| 指标 | 说明 |
|------|------|
| top3_ret3_positive_rate | Top3 候选 3 日正收益率比例 |
| top3_ret3_ge_5_rate | Top3 涨幅≥5% 比例 |
| top3_ret3_le_0_rate | Top3 涨幅≤0 比例 |
| rank_ic_ret3 | 排序 IC（秩相关系数） |
| top3_ret5_ge_5_rate | Top3 5 日涨幅≥5% 比例 |

### 4. 导出模型

```bash
uv run stock-select-ml score export-lgbm \
  --method "$METHOD" \
  --model-output-dir "diagnostics/ml/$METHOD/model"
```

- 对诊断数据打分
- 输出 score CSV 到 diagnostics
- 若 `--model-output-dir` 指向 `diagnostics/ml/$METHOD/tuning/<trial>`，默认 feature manifest、score CSV 和 summary 都跟随该 trial 目录

### 5. 发布模型

```bash
# 预览
uv run stock-select-ml model dry-run-promote "diagnostics/ml/$METHOD/model" \
  --method "$METHOD" \
  --require-report

# 正式发布
uv run stock-select-ml model promote "diagnostics/ml/$METHOD/model" \
  --method "$METHOD" \
  --require-report

# 回滚
uv run stock-select-ml model rollback <archive-version> \
  --method "$METHOD"
```

发布后产物在 `runtime/models/<method>/`：

```text
runtime/models/<method>/
├── model.txt              # LightGBM booster 序列化
├── model_metadata.json    # 特征元信息
├── model_card.json        # 发布摘要
└── feature_manifest.json  # 特征清单
```

归档在 `runtime/models/archive/<method>/<version>/`。

## 推理

### 特征向量构建

`build_feature_vector()`（`src/engine/inference.rs`）过程：

1. 从 `FactorRow` 中提取 `metadata.numeric_columns` 对应的数值特征
2. 缺失的数值特征补 `0.0`
3. 根据 `metadata.categorical_encoding` 处理 `metadata.categorical_columns`：`one_hot` 展开为 0/1 特征，`native` 映射为 LightGBM 分类整数 code
4. 特征顺序严格对齐 `metadata.feature_names`

```rust
pub struct BuiltFeatureVector {
    pub feature_names: Vec<String>,
    pub values: Vec<f64>,
    pub missing_numeric_features: Vec<String>,
}
```

### 模型加载

```rust
pub struct LightGbmRuntimeModel {
    booster: lightgbm3::Booster,
}
```

- 从 `model.txt` 文件加载 LightGBM booster
- 推理时调用 `predict(&[f64])` 返回原始预测分
- 强制单线程推理（`num_threads=1`）

### 打分排序

```rust
fn rank_candidates(...) -> Vec<RankedCandidate> {
    // 1. 为每个候选计算特征向量
    // 2. 模型 predict 得到 model_score
    // 3. 按 score 倒序排序
    // 4. 分配 model_rank（从 1 开始）
}
```

## 模型维护 CLI

统一入口 `uv run stock-select-ml model`：

| 命令 | 功能 |
|------|------|
| `status --method <method>` | 查看当前激活模型 |
| `archives --method <method>` | 列出当前 method 的归档版本 |
| `dry-run-promote <dir> --method <method>` | 预览发布 |
| `promote <dir> --method <method>` | 正式发布 |
| `rollback <version> --method <method>` | 回滚到指定版本 |

## 因子系统

因子在 `src/factors/` 中定义，通过 `registry.rs` 注册：

| 模块 | 因子 |
|------|------|
| `ma.rs` | 均线相关（MA5, MA25, 均线斜率等） |
| `macd.rs` | MACD 指标（DIF, DEA, 柱状图, 金叉死叉） |
| `volume.rs` | 成交量相关（量比, 均量比） |
| `price_position.rs` | 价格位置（箱体位置, 高/低点比例） |
| `abnormal_volume.rs` | 异常放量检测 |
| `semantic.rs` | 语义因子（趋势结构, 波动率等） |
| `series.rs` | 时间序列辅助函数 |
| `zx.rs` | 中道/中轨线 |

因子数据流：

```text
screening 阶段:
  行情数据 → 技术指标计算 → raw_payload (JSON)

run 阶段:
  raw_payload → CandidatePayloadFactorProvider.factor_row()
    ├── 顶层信号字段 (close, turnover_n, signal, env)
    ├── raw_payload.factors (已有计算因子)
    └── history → history_factor_fields() (历史窗口因子)

  → FactorRow { code, method, factors: BTreeMap<String, FactorValue> }
```

`FactorValue` 枚举：

```rust
pub enum FactorValue {
    Number(f64),
    Category(String),
    Bool(bool),
}
```

## 评分规则

b2 评分系统（`src/reviewers/b2_scoring.rs`）在模型排序之外提供规则化评分，用于 PASS/WATCH/FAIL 判定：

| 评分维度 | 函数 | 范围 | 说明 |
|----------|------|------|------|
| trend_structure | `score_b2_trend_structure()` | 1-5 | 趋势结构（多周期均线排列、顶背离） |
| price_position | `score_b2_price_position()` | 1-5 | 价格在 120 日箱体中的位置 |
| volume_behavior | `score_b2_volume_behavior()` | 1-5 | 量价配合（放量突破、缩量调整） |
| previous_abnormal_move | `score_b2_previous_abnormal_move()` | 1-5 | 前 90 日异常放量后的回调深度 |
| macd_phase | (环境传入) | 1-5 | MACD 相位（金叉、强多头、顶背离等） |

`infer_b2_verdict()` 综合上述评分判断：

| verdict | 含义 |
|---------|------|
| PASS | 强信号，综合评分和结构满足买入条件 |
| WATCH | 中等信号，可关注（细分为 A/B/C 三级） |
| FAIL | 不满足条件 |

WATCH 分级（`infer_b2_watch_tier()`）：

| 级别 | 条件 |
|------|------|
| WATCH-A | 弹性观察 + score ≥ 65 |
| WATCH-B | score ≥ 50 |
| WATCH-C | 其他 |
