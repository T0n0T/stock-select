# b2 Review 排序层设计

## 目标

为 b2 review 排序层建立离线升级路径。第一阶段只产出可复现的数据集和 baseline 排序评估，用来比较当前规则排序、后续 LightGBM/CatBoost、Kronos 因子和 RD-Agent 实验结果；不修改 `src/native_review.rs` 的生产 verdict 逻辑。

## 范围

本设计只覆盖 Phase 1：

- 从现有 runtime review artifacts 和 PostgreSQL 行情数据构建按交易日分组的 b2 排序数据集。
- 对当前 b2 排序 baseline 做按日 topN 和分环境评估。
- 产出后续 LightGBM/CatBoost、Kronos、RD-Agent 实验可以复用的稳定 artifacts。

本设计明确不做：

- 不向生产 Rust 代码引入模型依赖。
- 不修改 PASS/WATCH/FAIL verdict 规则。
- 不继续新增 weak/neutral/strong 的人工 override 规则。
- 第一阶段不运行 RD-Agent。

## 当前上下文

仓库当前已有 `scripts/b2_review_layer_diagnostics.py`。该脚本会读取 b2 runtime review artifacts，从 PostgreSQL 补 forward `ret3` / `ret5`，提取 review 特征，并把诊断报告写到 `diagnostics/b2_review_layer*`。

现有诊断脚本适合规则研究，但排序层升级需要更窄、更稳定的实验契约：

1. 数据集生成应输出稳定表格，每行对应一个 `(date, code)` 候选。
2. 排序评估应按交易日比较不同 ranking policy，而不是只看全局 segment 聚合。
3. 离线 ML/ranking artifacts 应与生产 review 输出分离。

## 推荐架构

新增一个小型 `scripts/ml/` 离线层：

```text
scripts/ml/build_b2_rank_dataset.py
scripts/ml/evaluate_b2_rank_baseline.py
diagnostics/ml/b2_rank_layer/
```

`build_b2_rank_dataset.py` 读取现有 review artifacts 和行情数据，输出：

```text
diagnostics/ml/b2_rank_layer/b2_rank_dataset.csv
diagnostics/ml/b2_rank_layer/b2_rank_dataset_summary.json
```

`evaluate_b2_rank_baseline.py` 读取数据集，输出：

```text
diagnostics/ml/b2_rank_layer/baseline_ranking_report.json
diagnostics/ml/b2_rank_layer/baseline_ranking_report.md
```

数据集脚本可以复用 `scripts/b2_review_layer_diagnostics.py` 中的纯 helper。若复用会让新脚本难以理解，可以少量复制解析逻辑，避免继续膨胀现有诊断脚本。

## 数据集契约

每一行代表某个交易日被 b2 review 的一只候选股票。

必要身份字段：

```text
date
code
name
env
method
```

必要 review 字段：

```text
current_verdict
baseline_verdict
current_score
baseline_score
signal
signal_type
```

必要 b2 review 特征：

```text
trend_structure
price_position
volume_behavior
previous_abnormal_move
macd_phase
daily_macd_phase_type
daily_macd_wave_index
daily_macd_wave_stage
weekly_macd_phase_type
weekly_macd_wave_index
weekly_macd_wave_stage
weekly_daily_combo_type
```

必要上下文特征，沿用现有诊断脚本已经能提取的字段：

```text
price_vs_90d_high
price_vs_90d_low
price_vs_90d_mid
midline_state
close_vs_ma25
close_vs_ma60
ma25_vs_ma60
ma25_slope_5d
ma60_slope_5d
support_stack_type
range_compression_20d
range_compression_40d
days_since_last_high
days_since_last_low
volume_ratio_5d
volume_ratio_10d
turnover_rate
turnover_rate_ratio_5d
daily_pct_chg
daily_macd_hist_state
price_turnover_state
k_value
d_value
j_value
j_vs_k
j_vs_d
j_overheat
j_repair_from_low
close_vs_bbi
bbi_bias_state
bias_bucket
obv_ratio_5d
obv_state
```

必要 label：

```text
ret3
ret5
ret10
max_drawdown_5d
win3_vs_day_median
win5_vs_day_median
rank_label_3d
rank_label_5d
```

label 定义：

- `ret3`、`ret5`、`ret10`：从 pick-date close 到后续第 3、5、10 个可用交易 bar close 的 forward percentage return。
- `max_drawdown_5d`：从 pick-date close 开始，未来 5 个可用交易 bar 的最低 low 对应的最大回撤。
- `win3_vs_day_median`：若该股票 `ret3` 大于同一交易日 b2 候选池 `ret3` 中位数，则为 `1`，否则为 `0`；缺失 label 留空。
- `win5_vs_day_median`：同上，使用 `ret5`。
- `rank_label_3d`、`rank_label_5d`：同一交易日内按 forward return 分成 `0..3` 四档，`3` 表示最强 quartile。

## Baseline 评估契约

评估脚本按交易日分组，在每个交易日候选池内部比较排序策略。

第一阶段必须比较的 ranking policy：

```text
current_score_desc
baseline_score_desc
pass_then_current_score_desc
pass_watch_then_current_score_desc
```

后续可以加入规则实验 policy，但 Phase 1 不依赖任何已训练模型。

每个 policy 至少输出以下指标：

```text
top3_ret3_positive_rate
top3_ret5_positive_rate
top3_ret3_ge_5_rate
top3_ret3_le_0_rate
top3_day_hit_rate_ret3
top3_day_hit_rate_ret5
top5_ret3_positive_rate
top5_ret5_positive_rate
top5_ret3_ge_5_rate
top5_ret3_le_0_rate
top5_day_hit_rate_ret3
top5_day_hit_rate_ret5
rank_ic_ret3
rank_ic_ret5
```

所有指标都需要同时输出 overall 和按 `env` 分层的结果，`env` 分层包括 `weak`、`neutral`、`strong`、`unknown`。Markdown 报告应先给紧凑对比表，再列出剩余风险，例如样本量不足、label 缺失、环境样本不均衡。

## Kronos 扩展点

Kronos 只作为离线因子提供方，不直接作为交易决策引擎。后续可以新增脚本，把 Kronos 预测路径转成以下因子并合入同一份数据集：

```text
kronos_ret_1d
kronos_ret_3d
kronos_ret_5d
kronos_max_upside_5d
kronos_max_drawdown_5d
kronos_path_smoothness
kronos_risk_reward
kronos_direction_confidence
```

这些字段进入相同数据集和评估契约后，才能严肃比较 `baseline`、`baseline + Kronos`、`LightGBM + Kronos` 的差异，而不需要改变 artifacts 格式。

## RD-Agent 扩展点

RD-Agent 适合后续做自动因子和模型研究，但不进入 Phase 1。第一阶段必须先建立稳定评估基座，否则自动研究系统提出的因子和模型无法判断是否过拟合。

后续接入时，RD-Agent 实验目录建议为：

```text
experiments/rd_agent/b2_rank_layer/
```

RD-Agent 产出的候选因子、模型参数或组合策略，必须回到 `evaluate_b2_rank_baseline.py` 或未来 model-aware 评估脚本里验证。RD-Agent 不应直接修改生产 Rust review 逻辑，也不能绕过 walk-forward 评估。

## 数据泄漏约束

排序层必须遵守以下约束：

- 排序结论不得使用随机 train/test split。
- feature 中不得包含未来数据。
- forward return 和 drawdown 只能作为 label 或评估目标。
- 同日 median 和 quantile label 必须在该日所有 feature row 构建完成后计算。
- 横截面特征只能在同一个 pick date 内计算。
- 后续任何模型训练都必须使用 chronological walk-forward split。

## 测试要求

Phase 1 的单元测试覆盖纯逻辑和小 fixture：

- dataset label bucketing 和同日 median win label。
- 按日分组 topN 指标计算。
- 分环境指标计算。
- 小型确定性 fixture 上的 RankIC 行为。
- 缺失 label 处理。

单元测试不依赖 live PostgreSQL。数据库脚本执行只作为 smoke/integration 命令。

## 验证命令

Phase 1 实现完成后运行：

```bash
python3 -m py_compile scripts/ml/build_b2_rank_dataset.py scripts/ml/evaluate_b2_rank_baseline.py
python3 -m unittest tests/test_b2_rank_dataset.py tests/test_b2_rank_baseline.py
git status --short
```

如果后续触碰 Rust 生产文件，再额外运行：

```bash
cargo fmt --check
cargo test --quiet
```

## 验收标准

Phase 1 完成标准：

- 能从已有 runtime root 生成 `b2_rank_dataset.csv`。
- 能输出 `baseline_ranking_report.json` 和 `baseline_ranking_report.md`，比较必要 baseline ranking policies。
- 指标按交易日分组计算，并按环境分层输出。
- 单元测试无需 live database 即可通过。
- 不要求修改生产 Rust review 行为。
