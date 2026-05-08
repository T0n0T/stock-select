# 2026-05-06 b2 neutral 环境 5日涨幅前后 50 小分专项分析

## 目标

继续 `feature/b2-environment-profile-tuning` 分支上的 b2 调参，专门看 `neutral` 环境下 `2026-01-01` 到 `2026-04-30` 的样本，回答三个问题：

1. 5 日涨幅前 50 的小分有什么共同点。
2. 它们与后 50 的主要差异是什么。
3. 哪些小分维度最适合拿来恢复 neutral 下的胜率和 `verdict` 分层。

## 数据口径

- baseline：`artifacts/review-tuning/b2-2026-01-01-2026-04-30-baseline/samples_with_env.csv`
- candidate：`artifacts/review-tuning/b2-2026-01-01-2026-04-30-candidate/samples_with_env.csv`
- 环境过滤：`environment_state = neutral`
- 只保留完整 `ret5_pct` 样本，共 `3152` 条
- 另生成结构化分析产物：
  `artifacts/review-tuning/b2-2026-01-01-2026-04-30-candidate/neutral_top_bottom_analysis.json`

## 一、先看 current candidate 的整体问题

- current candidate 在这批完整 5 日 neutral 样本上已经没有 `PASS`，只剩：
  `WATCH 2509 / FAIL 643 / PASS 0`
- baseline 在同一批样本上是：
  `WATCH 1596 / PASS 769 / FAIL 787`
- 也就是说，这一轮 neutral profile 虽然去掉了原来表现很差的 `PASS`，但没有建立新的分层，而是把大部分样本都压进了 `WATCH`

更关键的是：

- candidate 全样本平均 5 日仅 `+0.51%`
- 但前 50 平均 `+36.81%`
- 后 50 平均 `-17.31%`
- 前后 50 在 current candidate 里几乎同样都是 `WATCH 46 / FAIL 4`

这说明 neutral 的问题已经不是“旧 PASS 太差”这么简单，而是：

> current neutral verdict 已经失去排序能力。

## 二、前 50 的共同点

### 1. 更偏 `trend_structure = 3`

- 前 50 中 `trend_structure = 3` 占 `34%`
- 后 50 中仅 `14%`
- 全体 `trend_structure = 3` 样本平均 5 日 `+1.21%`，高于 `trend_structure >= 4` 的 `+0.24%`

这和旧直觉相反。neutral 下的 `3` 不像“结构差”，更像：

> 还没走到过热右侧、仍有弹性的启动窗口。

### 2. 更偏 `price_position >= 3`

- `price_position >= 3` 的样本平均 5 日 `+0.85%`，胜率 `49.0%`
- `price_position < 3` 平均 5 日 `-1.10%`，胜率 `38.2%`

这说明 neutral 下 `price_position` 是最稳定的第一层分流维度。尤其 `< 3` 的样本，明显更接近低质量池。

### 3. 更偏 `macd_phase < 4.5`

- `macd_phase < 4.5` 平均 5 日 `+0.75%`，胜率 `48.3%`
- `macd_phase >= 4.5` 平均 5 日 `-0.57%`，胜率 `41.7%`
- 前 50 中 `>= 4.5` 占比 `16%`
- 后 50 中 `>= 4.5` 占比 `32%`

也就是说，在 neutral 环境里，高 MACD 分不是优势，反而更像：

> 已经偏右侧、偏热、偏末端。

### 4. `volume_behavior` 不是无效项

- `volume_behavior` 为 `2/4` 的样本平均 5 日 `+1.14%`，胜率 `50.5%`
- `volume_behavior` 为 `3/5` 的样本平均 5 日仅 `+0.26%`，胜率 `46.0%`
- `price_position = 4 & volume_behavior = 4` 平均 5 日 `+1.28%`
- `price_position = 4 & volume_behavior = 5` 只有 `+0.42%`

当前 neutral profile 把 `volume_behavior` 权重压到 `0`，会直接损失一部分可分层信号。

## 三、前后 50 的共同点，反而说明哪些维度没区分力

### 1. `price_position = 4` 两端都很多

- 前 50：`82%`
- 后 50：`80%`

所以“拿到 4 分”本身不够，真正有用的是：

- `< 3` 应该明确降档
- `= 4` 内部还要继续看别的小分组合

### 2. `previous_abnormal_move = 5` 两端都几乎是默认值

- 前 50：`90%`
- 后 50：`94%`

这个维度在 neutral 下更多像“准入门槛”，不是有效的排序维度。继续给它太高权重，只会让大量普通样本共享高分模板。

### 3. `trend_structure = 4 / price_position = 4 / previous_abnormal_move = 5` 变成了过度拥挤的默认模板

前 50 和后 50 的最高频组合都是：

- `trend_structure = 4`
- `price_position = 4`
- `previous_abnormal_move = 5`

其中最常见的一组：

- 前 50：`trend=4 / price=4 / volume=3 / prev=5` 共 `11` 条
- 后 50：同组合共 `19` 条

这说明这组模板在 neutral 下根本不适合作为高层 verdict 的核心。

## 四、对恢复 verdict 分层最有利的组合

### 候选 PASS 原型

组合：

- `price_position >= 3`
- `trend_structure = 3`
- `macd_phase < 4.5`

表现：

- 样本数 `493`
- 平均 5 日 `+2.54%`
- 中位 5 日 `+1.51%`
- 胜率 `57.6%`

这个组合明显优于全体 neutral 样本，也优于当前 WATCH 大池，适合做下一轮 PASS 原型。

### 候选 WATCH 中层

组合：

- `price_position >= 3`
- `macd_phase < 4.5`
- 但不满足上面的 `trend_structure = 3`

表现：

- 样本数 `1576`
- 平均 5 日 `+0.72%`
- 胜率 `48.3%`

这更像一个中间层观察池，而不是 PASS。

### 候选 FAIL 原型

组合：

- `price_position < 3`
  或
- `macd_phase >= 4.5`

表现：

- 样本数 `1083`
- 平均 5 日 `-0.71%`
- 中位 5 日 `-1.55%`
- 胜率 `40.6%`

这组已经有明显负向特征，适合作为 neutral 下的低层候选。

## 五、baseline 对照告诉我们的事

baseline 在这批完整 neutral 样本上的 verdict 表现是：

- `PASS`：平均 5 日 `-0.22%`，胜率 `43.8%`
- `WATCH`：平均 5 日 `+1.02%`，胜率 `49.1%`
- `FAIL`：平均 5 日 `+0.19%`，胜率 `46.3%`

也就是说，旧 neutral `PASS` 本身就已经是反向分层。

再看前后 50：

- 前 50 中 baseline `PASS` 只有 `9`
- 后 50 中 baseline `PASS` 却有 `20`

所以这次调参不应该是“设法把旧 PASS 捞回来”，而应该是：

> 直接重建 neutral 下的分层逻辑。

## 六、对下一轮调参的建议

### 1. 下调 `macd_phase` 在 neutral 下的正向权重

尤其是：

- 不允许 `>= 4.5` 单独推动升档
- 必要时把 `>= 4.5` 视为风险项，而不是加分项

### 2. 提高 `price_position` 的 veto 权重

- `< 3` 应明显偏向 `FAIL`
- `>= 3` 才进入更高层分层

### 3. 重新定义 neutral 下 `trend_structure = 3` 的含义

现在的数据更支持：

- `3` 代表“尚未过热、仍有空间的启动结构”
- 不是天然弱于 `4`

### 4. 恢复 `volume_behavior` 的区分力

至少要让：

- `2/4` 高于 `3/5`

否则很多 `price=4` 的普通样本会被继续混在一起。

## 结论

这一轮 neutral 诊断最重要的结论不是某个单点阈值，而是分层方向已经很清楚：

- `price_position` 应承担第一层过滤
- `macd_phase` 在 neutral 下不应继续高分偏好
- `trend_structure = 3` 需要从“弱结构”改为“有弹性的早段结构”
- `volume_behavior` 应恢复为有效分层维度

如果下一轮 profile 调整围绕这四点展开，neutral 下的 `PASS/WATCH/FAIL` 才有机会重新形成正向收益层次。
