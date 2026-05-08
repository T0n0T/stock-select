# 2026-05-08 b2 neutral 调参与当前状态总览

## 目的

本文件用于把本轮 `b2 neutral` 调参与研究结果整理成一份统一入口，回答四个问题：

1. neutral 当前到底改了什么。
2. 这些改动分别解决了什么问题。
3. 当前 neutral 的样本分层表现如何。
4. 下一步最值得继续调的方向是什么。

适用范围：

- worktree：`feature/b2-environment-profile-tuning`
- 方法：`b2`
- 环境：`neutral`
- 当前最新验证版本：
  `artifacts/review-tuning/b2-2026-01-01-2026-05-06-candidate-v6`

相关核心产物：

- neutral top/bottom 分析：
  `docs/research/2026-05-06-b2-neutral-top-bottom-analysis.md`
- neutral 冲突样本清单：
  `docs/research/2026-05-07-b2-neutral-conflicting-samples.md`
- neutral FAIL 箱体区间：
  `docs/research/2026-05-07-b2-neutral-fail-box-intervals.md`
- neutral WATCH score/tier：
  `docs/research/2026-05-07-b2-neutral-watch-score-tier-study.md`
- neutral WATCH 重点组合：
  `docs/research/2026-05-07-b2-neutral-watch-combo-study.md`
- 最新 neutral verify：
  `artifacts/review-tuning/b2-2026-01-01-2026-05-06-verify-neutral-v6/verification.json`

## 一、本轮 neutral 的主要变化

### 1. `PASS` 增加 `zxdq` 斜率 gate

当前 neutral 的 `PASS` 路径不再只看离散小分组合，还要求：

- `zxdq_5d_slope_pct >= 0`

这层 gate 的作用不是扩池，而是：

> 把一批已经进入右侧确认、但支撑线开始转弱的样本挡回 `WATCH`。

这层变化主要针对之前在 `PASS` 中出现的坏样本，例如：

- `301611.SZ`
- `603696.SH`
- `600838.SH`
- `301093.SZ`

这些样本的共同点不是分数不够，而是：

- 已经满足 neutral `PASS` 结构模板
- 但更像支撑转弱后的右侧再启动

### 2. 新增一条很窄的 `B3 trend_start` 升档规则

在原有 neutral `PASS` 逻辑之外，本轮新增了一条从 `WATCH` 中抬升的窄规则：

- `signal = B3`
- `signal_type = trend_start`
- `watch_tier = WATCH-A`
- `volume_behavior = 3`
- `total_score <= 4.28`
- `macd_phase <= 4.42`

这条规则来自 `WATCH` 组合专项分析，不是主观猜测。

它代表的是一类：

- 结构完整
- 位置够强
- MACD 已经确认
- 但总分和量能还没走到过热区

也就是：

> 当前 neutral 下被低估的一批 `B3 trend_start` 右侧确认样本。

## 二、当前 neutral 的主要研究结论

### 1. top/bottom 分析给出的主方向

neutral 最早的问题不是“PASS 太少”，而是：

- 原来的 `PASS` 缺乏正向分层
- 大量样本被压进 `WATCH`
- `trend_structure = 4 / price_position = 4 / previous_abnormal_move = 5` 这套高频模板内部拥挤严重

从 top/bottom 研究看，neutral 更支持：

- `price_position >= 3` 才值得进入高层分层
- `macd_phase >= 4.5` 在 neutral 更像过热风险，不应自动推动升档
- `trend_structure = 3` 在 neutral 下并不天然弱，反而常常代表“尚未过热、仍有空间的启动结构”
- `volume_behavior` 必须恢复区分力，不能继续视为弱项

### 2. `FAIL` 的问题不是简单改 `price_position` 打分

对 `FAIL` 的连续箱体值回看后，结论是：

- `FAIL` 大涨样本整体更偏左
- 但不是所有左侧样本都该被释放
- 最有区分力的是极左区：`box_position <= 0.30`

具体看：

- `FAIL` 大涨样本中，`box_position <= 0.30` 占 `25.0%`
- `FAIL` 下跌样本中，同条件占 `9.7%`

所以 `FAIL` 的问题更像：

> 若后面要在 `FAIL` 中开窄门，应考虑连续 `box_position`，而不是简单放宽 `price_position=1/2`。

### 3. `WATCH` 不是 box 问题，而是排序问题

对 `WATCH` 的研究结论比较稳定：

- `WATCH` 大涨样本和普通 `WATCH` 在离散小分上的差异很弱
- `watch_score` 不是单调越高越好
- `watch_tier` 也只有弱分层

因此 neutral `WATCH` 当前更像：

> 多种结构混在一起的观察池，问题在拆池与排序，而不是再切一个统一 box 阈值。

### 4. `B3 trend_start WATCH-A` 是当前最像可升档的 `WATCH` 子池

在 `WATCH` 组合里，`B3 trend_start WATCH-A` 的整体表现已经明显优于同类对照组：

- 样本数：`83`
- 5日均值：`+2.266%`
- 5日中位数：`+1.94%`
- 胜率：`59.0%`
- 大涨率：`4.8%`

继续往下拆后，最强子集不是整池，而是：

- `volume_behavior = 3`
- `total_score <= 4.28`

这组样本进一步提纯后：

- 样本数：`29`
- 5日均值：`+5.624%`
- 胜率：`72.4%`

再加一层：

- `macd_phase <= 4.42`

会收成：

- 样本数：`21`
- 5日均值：`+5.894%`
- 5日中位数：`+6.28%`
- 胜率：`76.2%`
- 大涨率：`9.5%`

这就是当前 `candidate-v6` 中新增升档规则的直接来源。

## 三、当前 neutral 的最新验证结果

### 1. 相对 baseline 的 neutral verify

基于：

- baseline：`b2-2026-01-01-2026-05-06-baseline`
- candidate：`b2-2026-01-01-2026-05-06-candidate-v6`

neutral verify 结果为：

- baseline 平均分：`4.24`
- candidate 平均分：`3.97`
- baseline 5日均值：`+1.53%`
- candidate 5日均值：`+3.81%`
- baseline 5日胜率：`50.5%`
- candidate 5日胜率：`60.2%`
- baseline record 数：`124`
- candidate record 数：`95`

也就是说：

> current neutral 候选比 baseline 更少，但质量更高，5日均值和胜率都显著抬升。

### 2. 当前 neutral 内部分层

最新 `candidate-v6` 在 neutral 内的 `verdict` 表现：

- `PASS`
  - 样本数：`241`
  - 5日均值：`+3.851%`
  - 5日中位数：`+3.06%`
  - 胜率：`62.4%`
- `WATCH`
  - 样本数：`2825`
  - 5日均值：`+0.457%`
  - 5日中位数：`-0.58%`
  - 胜率：`47.1%`
- `FAIL`
  - 样本数：`489`
  - 5日均值：`-0.44%`
  - 5日中位数：`-1.43%`
  - 胜率：`41.3%`

当前 neutral 已经形成稳定的正向分层：

- `PASS > WATCH > FAIL`

### 3. 相对上一版 neutral 的变化

相对 `candidate-v4`，本轮 `v6` 的核心变化是：

- `PASS` 从 `220` 条增加到 `241` 条
- `PASS` 5日均值从 `+3.679%` 提升到 `+3.851%`
- `PASS` 胜率从 `61.2%` 提升到 `62.4%`
- `WATCH` 5日均值从 `+0.498%` 小幅回落到 `+0.457%`
- `FAIL` 维持 `-0.44%`

这说明新抬升的 `B3 trend_start` 子池并没有稀释 `PASS`，反而继续抬高了 `PASS` 质量。

## 四、当前 neutral 的限制

虽然 `verdict` 分层已经变好，但 neutral 仍然存在两个限制：

### 1. `total_score` 依然不适合直接排序

最新 `candidate-v6` 的 neutral 相关性里：

- `total_score -> ret5_pct`
  - `Pearson = 0.0319`
  - `Spearman = 0.0171`

这仍然是很弱的相关性。

说明：

> neutral 目前更像“依靠结构规则和筛选分层”，而不是“总分已经能直接排序”。

### 2. `WATCH` 仍然是大池

虽然 `PASS` 已经明显改善，但 `WATCH` 仍有：

- `2825` 条
- 5日中位数为负

后面 neutral 如果要继续做精细化调参，最值得继续的不是整体放宽 `PASS`，而是：

- 继续拆 `WATCH` 里的结构类型
- 找出还能单独抬升或单独降档的子池

## 五、建议的后续方向

按优先级排序，当前更建议：

### 1. 继续细化 `PASS` 的风险护栏

优先看：

- 新升档的 `B3 trend_start` 子池里剩余负收益样本
- 是否还需要更轻的扩张/斜率/位置过滤

目标不是扩大 `PASS`，而是继续净化 `PASS`。

### 2. 继续拆 `WATCH`

优先方向：

- `B3 rebound WATCH-C` 低分高弹性子池
- `B2 trend_start WATCH-A/B` 内部哪些样本只是高分噪音

### 3. 在 `FAIL` 中尝试极左窄门，而不是整体放宽

如果后面要试 `FAIL` 恢复样本，建议从：

- `box_position <= 0.30`

这类极左连续区间开始，而不是直接改 `price_position=1/2`。

## 六、当前结论

截至 `candidate-v6`，neutral 已经从“没有有效分层”推进到：

- `PASS` 形成明显正收益层
- `WATCH` 作为中间池保留
- `FAIL` 维持负向特征

其中最关键的两步是：

1. 给 neutral `PASS` 加 `zxdq_5d_slope >= 0` 质量护栏
2. 从 `WATCH` 中识别并抬升一条窄的 `B3 trend_start` 强样本规则

当前 neutral 的主要矛盾已经不再是“有没有 `PASS`”，而是：

> `PASS` 如何继续净化，`WATCH` 如何继续拆池，`FAIL` 是否值得开极左窄门。

这也是后续继续调 `b2 neutral` 时最应该围绕的三件事。
