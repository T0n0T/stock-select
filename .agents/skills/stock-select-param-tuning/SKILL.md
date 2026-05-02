---
name: stock-select-param-tuning
description: Use when tuning stock-selection or review scoring parameters for b1, b2, dribull, or hcr using monthly review artifacts, prepared caches, score-vs-return diagnostics, and full-month recomputation.
---

# Stock Select Param Tuning

## Overview

用于 `stock-select` 的方法调参，重点不是主观聊想法，而是基于月度 review 产物、prepared cache 和未来 3 日/5 日收益做证据驱动的调参闭环。

适用对象：`b1`、`b2`、`dribull`、`hcr` 的筛选参数、review 子项评分、总分权重、`PASS/WATCH/FAIL` 阈值。

如果用户只是要跑一次选股、看单票、或生成图表，不用这个 skill，改用现有 `stock-select` 或 `stock-select-single-stock`。

## Use When

在这些场景使用：

- 用户要“调参”“重写打分”“优化阈值”“看分数和收益是否相关”
- 用户怀疑 `total_score` 或某个子项和未来收益负相关
- 用户要比较某个方法在 1 个月或多个月里的 `PASS top3`、全样本、或某个 `verdict` 分层表现
- 用户要先做诊断，再决定是微调阈值还是重写计分函数

不适用：

- 只看单日样本
- 只跑一次 `review_top3_stats.py` 就下结论
- 只想生成研究文档而不涉及调参决策

## Runtime Inputs

调参分析默认使用这些输入：

- review 目录：`~/.agents/skills/stock-select/runtime/reviews/<pick_date>.<method>/summary.json`
- prepared cache：`~/.agents/skills/stock-select/runtime/prepared/<pick_date>.pkl`
  - `b1` / `b2` / `dribull` 共享 `.pkl`
  - `hcr` 使用 `<pick_date>.hcr.pkl`
- 代码实现：`src/stock_select/`
- 通用调参诊断脚本：`scripts/score_tuning_diagnostics.py`
- 月度 top3 复盘脚本：`scripts/review_top3_stats.py`

注意：月度分析不是读取“按月一个 summary 文件”，而是遍历该月份内每个交易日的 `summary.json` 后再聚合。

## Required Workflow

### 1. 数据收集

按目标月份遍历 `runtime/reviews/<pick_date>.<method>/summary.json`，提取每个样本至少这些字段：

- `code`
- `pick_date`
- `total_score`
- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`
- `signal_type`
- `verdict`

然后结合 prepared cache 计算：

- 3 日涨幅
- 5 日涨幅

默认定义：

- `3日涨幅 = 第3个后续交易日收盘 / 入选日收盘 - 1`
- `5日涨幅 = 第5个后续交易日收盘 / 入选日收盘 - 1`

如果样本尾部后续交易日不足：

- 3 日或 5 日分别记为缺失
- 统计时显式记录剔除数量，不要静默忽略

### 2. 相关性诊断

优先直接运行：

```bash
uv run python scripts/score_tuning_diagnostics.py \
  --method b2 \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --output-dir /tmp/b2_april_tuning_diag
```

该脚本会输出：

- `diagnostics.json`
- `records.csv`

并在终端打印：

- `total_score` 与各子项对 `ret3_pct` / `ret5_pct` 的 Pearson / Spearman
- `verdict` 分层统计
- `total_score` 分桶统计

对以下变量分别计算与未来 3 日涨幅的相关性：

- `total_score`
- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`

至少同时看：

- Pearson r
- Spearman r

诊断目标：

- 是否明显正相关
- 是否接近 0
- 是否负相关
- 是否存在“线性不强但排序仍有用”的情况

不要只看总分。很多时候总分失效，真正的问题是某个子项权重过大，或者某个子项本身方向错了。

### 3. 分段分析

至少做三类分段：

- 按子项分数值分段：`1` 到 `5` 每档
- 按总分区间分段：例如 `<=3.5`、`3.5-4.0`、`4.0-4.3`、`4.3-4.6`、`>4.6`
- 按 `verdict` 分层：`PASS` / `WATCH` / `FAIL`

每段至少输出：

- 样本数
- 3 日均值
- 3 日中位数
- 3 日胜率
- 5 日均值
- 5 日中位数
- 5 日胜率

如果用户关心交易使用，再额外看：

- `PASS` 池内按 `total_score` 排序后的 top1 / top3 / 全部差异

### 4. 判断是否需要改动

按以下原则做判断：

- 如果 `total_score` 和 3 日涨幅已经正相关或接近 0 且分段单调性基本正常，优先考虑微调阈值，不要急着重写评分函数
- 如果 `total_score` 明显负相关，优先检查是不是某个子项方向错误或权重失衡
- 如果总分不差，但某个子项单独负相关，优先改该子项定义或降权
- 如果总分和主要子项都负相关，才考虑重写计分逻辑或重配权重
- 如果 `verdict` 分层有效、但 `PASS` 池内部排序无效，优先调总分权重，不要先动 `PASS/WATCH/FAIL` 阈值
- 如果 `PASS` 池内相关性不错、但 `PASS` 总体收益差，优先怀疑筛选入口太宽或 `verdict` 门槛太松

### 5. 实施改动

确认要调参后，再修改实现。

常见改动点：

- 子项打分函数方向
- 子项离散档位或阈值
- 总分权重
- `PASS/WATCH/FAIL` 阈值
- `signal_type` 归类规则
- 前置筛选条件

实施时要求：

- 改动尽量小步，不要一轮同时改 5 个变量
- 每轮改动必须能说明“为什么改”以及“预期改善哪一项诊断结果”
- 如果是重写计分函数，要先明确旧函数为什么错，而不是只说“感觉不准”

### 6. 重算验证

改完后必须重跑全月，不接受只看单日或手抽样本。

推荐顺序：

1. 用 `stock-select` 或现有回填脚本重跑目标月份
2. 确认新的 review 产物已写入 runtime
3. 再跑 `scripts/score_tuning_diagnostics.py` 看全样本诊断是否改善
4. 再跑 `scripts/review_top3_stats.py` 看 top3 结果
5. 重新做同口径相关性与分段分析
6. 只在“新旧对比”成立时再宣布调参有效

最少要比较：

- `PASS top3` 的 3 日/5 日收益
- `total_score vs 3日涨幅` 的 Pearson / Spearman
- `PASS/WATCH/FAIL` 的分层表现是否更干净

## Output Expectations

调参结论至少回答这几个问题：

1. 当前总分与未来 3 日收益是正相关、零相关还是负相关？
2. 问题主要出在总分权重、单个子项、还是 verdict 阈值？
3. 本轮应该微调，还是应该重写？
4. 改完后，相比改前到底改善了什么？

如果最终写研究文档，必须写清：

- 时间范围
- 方法名
- 样本口径
- 剔除口径
- 改动前后对比

## Common Mistakes

- 只看 `PASS top3`，不看全样本和 `verdict` 分层
- 只看均值，不看中位数和胜率
- 只看 Pearson，不看 Spearman
- 把“样本太少”当万能借口，不先检查分数方向是否反了
- 改动过大，导致无法归因哪一项真正起作用
- 没有重跑全月，就宣称调参成功

## Practical Notes

- 研究文档默认用中文
- 调参前后都保留原始统计结果，方便回滚与比较
- 如果现有仓库已经有临时分析脚本，优先复用；不要每轮都手写一遍 ad-hoc 统计逻辑

## Recommended Commands

全样本调参诊断：

```bash
uv run python scripts/score_tuning_diagnostics.py \
  --method dribull \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --output-dir /tmp/dribull_april_tuning_diag
```

PASS top3 结果复盘：

```bash
uv run python scripts/review_top3_stats.py \
  --method dribull \
  --start 2026-04-01 \
  --end 2026-04-30
```

整月回填重跑示例：

```bash
uv run scripts/backfill_samples.py \
  --method dribull \
  --start-date 2026-04-01 \
  --end-date 2026-04-30
```
