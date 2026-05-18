# B1 Review 层

## 方法定位

`b1` review 重点不是右侧确认，而是判断“回调是否充分、支撑是否仍在、当前是否仍有左侧赔率”。

## 输入与环境

baseline reviewer：

- `review_b1_symbol_history()`

额外特性：

- 接入 market environment profile
- 会输出 `score_layer`、`watch_tier`、`gate_flags` 等 `b1` 专有字段

## baseline 五个子分

### 1. `trend_structure`

基于以下结构判断：

- `ma25` 是否近端走平向上
- `zxdkx` 是否近端走平向上
- 当日中值价是否在 `ma25` 下方、但仍靠近或站在 `zxdkx` 之上
- `BBI` 是否持续位于 `ma25` 之上
- `ma25` 是否持续位于 `zxdkx` 之上

总体倾向：

- 越像“趋势未坏、正在回调到支撑附近”，分越高
- 已经明显回到 `ma25` 之上偏右侧，分反而下降

### 2. `price_position`

基于近 `120` 日箱体位置判断：

- 越偏箱体左侧，分越高
- 若位置偏高，但 `ma25` 仍能稳住 `zxdq`，可保留中性分

环境会影响偏好：

- `weak`: 更偏好左侧低位
- `strong`: 减轻左侧偏执，更接受再启动位置

### 3. `volume_behavior`

核心看两件事：

- 历史最大量是否来自偏多 K 线
- 回调阶段是否出现“缩后再放”的承接迹象

倾向：

- 高量阳线 + 回调承接仍在 -> 高分
- 最大量偏空、承接差 -> 低分

### 4. `previous_abnormal_move`

`b1` 这里复用了 `b2` 的前异常波动评分逻辑：

- 找近 `90` 日最大量对应异常事件
- 看异常事件后价格回撤是否充分
- 回撤越充分且没有彻底走坏，越偏高分

### 5. `macd_phase`

`b1` 的 `macd_phase` 不是简单日线金叉死叉，而是：

- 周线 MACD 趋势
- 日线 MACD 趋势
- 双周期组合状态
- 顶背离惩罚
- 环境状态下的非线性微调

若存在周/日顶背离，会进一步扣分。

## baseline 总分

默认权重：

- `trend_structure`: `0.23`
- `price_position`: `0.20`
- `volume_behavior`: `0.22`
- `previous_abnormal_move`: `0.20`
- `macd_phase`: `0.15`

若有 environment profile，则改为使用 profile 中的环境权重与阈值。

## 信号分类

统一先分成：

- `distribution_risk`
- `rebound`
- `trend_start`

后续判定重点不在“总分高低”本身，而在是否落入已知的高收益 family / combo。

## `b1` 特有判定层

### 高收益 score combo

当前内置了少量高收益组合 key，例如：

- `rebound|T3|P3|V4|A5|M3.5`
- `distribution_risk|T2|P4|V4|A5|M4.0`
- `trend_start|T4|P3|V4|A5|M3.5`

其中：

- 命中 `exact` 组合时，有机会直接给 `PASS`
- 但是否允许 `PASS` 还受 environment state 约束

### pass family

除 exact combo 外，还会把样本归类到：

- `rebound`
- `distribution`
- `trend_start`

再区分 `core` / `near`。

当前实现里，family 本身更多用于 `WATCH` 分类与分层，不直接大规模放出 `PASS`。

### environment gate

`b1` 还有一层环境门控，会计算：

- `below_ma25`
- `runup_pct`
- `sideways_amplitude_pct`
- `weekly_slope_26w`
- `weekly_macd_cooldown_active`
- 日线死叉 cooldown

可能触发的标记包括：

- `cooldown_active`
- `weekly_macd_cooldown_active`
- `weekly_slope_not_rising`
- `below_ma25`
- `runup_over_limit`
- `sideways_tight_range`

这些标记会影响：

- `PASS` 是否降级到 `WATCH`
- `score_layer_score`

## verdict 生成逻辑

大致顺序：

1. 先计算五个子分与 `total_score`
2. 推断 `signal_type`
3. 匹配高收益 combo 与 pass family
4. 初步得到 `verdict`
5. 经过 MACD trend gate
6. 再经过 environment verdict gate
7. 生成 `watch_reason`、`watch_score`、`watch_tier`
8. 生成 `score_layer`

## `WATCH` 解释层

`WATCH` 会进一步生成：

- `watch_reason`
- `watch_score`
- `watch_tier`

当前常见 `watch_reason` 包括：

- `distribution_elastic`
- `rebound_elastic`
- `trend_start_repair`
- `rebound_near_pass_flawed`
- `trend_start_weak`

`watch_tier` 分三档：

- `WATCH-A`
- `WATCH-B`
- `WATCH-C`

## `score_layer`

`b1` 专门对 `PASS/WATCH` 做层级评分：

- `PASS-A`
- `PASS-B`
- `PASS-C`
- `WATCH-A`
- `WATCH-B`
- `WATCH-C`

同时输出数值：

- `score_layer_score`

该数值会参与 summary 排序。

## 结果解读

对 `b1` 来说：

- `PASS` 表示当前更接近“支撑仍在、回调充分、可作为左侧低点跟踪”
- `WATCH` 不等于差，很多是结构接近但门控未完全放行
- summary 阶段中，`b1` 只要 `verdict == PASS` 就会进入推荐列表，不额外要求 `total_score >= 4.0`

## 当前胜率统计

`b1` 当前实现下的总体胜率、分环境分 `verdict` 胜率、以及 `PASS top3` 胜率，统一见：

- [方法胜率统计](../share/method-win-rates.md)
