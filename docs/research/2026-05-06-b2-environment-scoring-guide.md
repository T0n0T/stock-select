# 2026-05-06 b2 不同环境打分策略与分析重点

## 目的

本文件用于说明当前 `b2` 在 `weak / neutral / strong` 三种环境下的打分偏好、verdict 重点、以及后续调试时应该优先观察什么。

重点不是复述每一行代码，而是给后续调参一个统一理解框架：

- 当前环境希望捕捉什么样的样本
- 哪些小分更重要
- 哪些高分组合其实是风险
- 该环境下强样本通常长什么样

相关代码入口：

- 环境 profile：
  [src/stock_select/environment_profiles.py](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/src/stock_select/environment_profiles.py)
- b2 reviewer：
  [src/stock_select/reviewers/b2.py](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/src/stock_select/reviewers/b2.py)

## 一、总体理解

b2 不是一个纯低吸模型，也不是一个纯右侧突破模型。它更像：

> 在不同市场环境下，选择“启动结构”应该偏保守、偏中性，还是偏进攻。

五个核心小分里，各环境最值得关注的是：

- `trend_structure`
- `price_position`
- `previous_abnormal_move`
- `macd_phase`
- `volume_behavior`

但这五项在不同环境里并不是同样重要。

## 二、weak 环境

### 目标

弱环境的核心不是抓最猛，而是：

> 压制高位右侧追涨，优先保留位置安全、承接更强、离前期异动锚点不远的样本。

### 当前 profile 特征

- `trend_structure` 权重提高到 `0.24`
- `price_position` 权重降到 `0.14`
- `previous_abnormal_move` 提高到 `0.22`
- `macd_phase` 保持高权重 `0.25`
- `volume_behavior` 当前仍为 `0`

额外模式：

- `price_position = low_risk_required`
- `macd_phase = strict`
- `trend_structure = pullback_only`
- `previous_abnormal_move = strict`

### 调试重点

- 弱环境下先看 `price_position` 是否把高位样本压住
- 再看 `previous_abnormal_move` 是否能筛掉离异动锚点过远的票
- 高 `macd_phase` 在弱环境里不能直接当成进攻信号

### 强样本通常长什么样

- 不是高位新突破
- 更接近回踩后仍有承接
- 前期异动后的回撤不深不浅，仍在可控区

## 三、neutral 环境

### 目标

中性环境最容易误判。既不能按弱环境过度保守，也不能按强环境直接追右侧。

这一环境当前最重要的认识是：

> 强样本更像“回踩/整理后，在异动量锚点附近再启动”，不是“箱体低位抄底”，也不是“高 MACD 右侧追突破”。

### 当前 profile 特征

- `trend_structure` 权重 `0.16`
- `price_position` 权重 `0.25`
- `previous_abnormal_move` 权重 `0.14`
- `macd_phase` 权重降到 `0.20`
- `volume_behavior` 恢复到 `0.10`

额外 neutral verdict 逻辑：

- 压制 `trend_start + price=4 + high macd` 直接升 PASS
- 允许一类 `trend_start + price=4 + mid-macd` 升 PASS
- 新增一类：
  `rebound/trend_start + trend_structure=3 + volume=2/3 + prev=5 + macd<4.5`
  其中：
  - `price=4` 可直接考虑升 `PASS`
  - `price=3` 只有更强信号（如 `B3/B3+`）才考虑升 `PASS`
  - `B2 + price=3` 仍偏 `WATCH`
  - `volume=4` 在 neutral 下更接近确认段，当前不再直接升 `PASS`

### 当前分析结论

基于 `2026-01-01` 到 `2026-04-30` 的 neutral 样本：

- 高反馈样本里 `rebound` 多于 `trend_start`
- `trend_structure = 3` 明显优于大量 `4`
- `price_position < 3` 明显更差
- `macd_phase >= 4.5` 在 neutral 下更像过热风险
- `previous_abnormal_move = 5` 常见，但更像必要背景而不是核心 alpha
- `volume_behavior` 里 `2/3/4` 比 `5` 更适合 neutral 的强样本
- 进一步细看时，`volume=4` 在 current neutral `PASS` 里仍显著弱于 `2/3`，因此当前升档规则只保留 `2/3`
- 因此 neutral 权重不再允许 `macd_phase` 一维主导，而是改成 `price_position + trend_structure + volume_behavior` 共同决定升档

### 调试重点

neutral 环境优先看下面三件事：

1. 是否把“回踩/整理后再启动”抬起来了  
观察：
`signal_type in {rebound, trend_start}`、`trend_structure=3`

2. 是否把“高 MACD 右侧末端”压下去了  
观察：
`macd_phase >= 4.5` 的 verdict 和后续收益

3. 是否把“异动量锚点附近但不过热”的票分到更高层  
观察：
`previous_abnormal_move >= 5` 配合 `price_position >= 3`、`volume_behavior != 5`

### 强样本通常长什么样

- 有回踩或整理痕迹
- 仍贴近前期异动量锚点
- 不是极低位抄底，而是箱体中上部整理后再启动
- MACD 不宜过热
- 对 `price=3` 的样本要更谨慎；如果只是 `B2`，通常仍不足以直接升为 `PASS`

## 四、strong 环境

### 目标

强环境允许更积极地接受右侧确认。

核心思路是：

> 市场强时，不必过分执着回踩深度，可以更重视突破确认、MACD 共振和前期强异动延续。

### 当前 profile 特征

- `trend_structure` 权重降到 `0.10`
- `price_position` `0.20`
- `previous_abnormal_move` `0.20`
- `macd_phase` `0.35`
- `volume_behavior` 当前为 `0`

额外模式：

- `price_position = breakout_tolerant`
- `macd_phase = aggressive`
- `trend_structure = aggressive`
- `previous_abnormal_move = lenient`

### 当前 review 条件

当前 strong `b2` 的 baseline review 重点不在“深回踩确认”，而在“右侧确认是否仍然健康”。

当前可以直接推到 `PASS` 的主要路径有三类：

- 高位强确认路径：
  - `macd_phase >= 4.5`
  - `previous_abnormal_move >= 5`
  - `trend_structure >= 3`
  - `price_position >= 2`
  - `volume_behavior >= 2`
  - `total_score >= 3.6`
- `trend_start` 中高 MACD 路径：
  - `signal_type = trend_start`
  - `trend_structure >= 4`
  - `previous_abnormal_move >= 5`
  - `price_position >= 3`
  - `volume_behavior >= 3`
  - `total_score >= pass_threshold`
  - `macd_phase >= 4.2`
  - 或 `macd_phase >= 3.5 且 price_position = 5`
- `B3 / B3+` 提前升级路径：
  - `signal in {B3, B3+}`
  - `signal_type in {trend_start, rebound}`
  - `trend_structure = 4`
  - `price_position >= 4`
  - `volume_behavior >= 4`
  - `previous_abnormal_move >= 3`
  - `3.0 <= macd_phase < 3.8`
  - `total_score >= 4.0`
  - 且不能落入过热扩张区

当前 strong 下还有两条重要的防守约束：

- 负 MACD guard 只对“高位且量能过热”的票生效：
  - `trend_structure = 4`
  - `price_position >= 4`
  - `volume_behavior >= 5`
  - 如果最新 `MACD hist < 0`，则要求 `abs(latest_hist) < 近期负柱波峰 * 0.5`
  - 否则 `PASS -> WATCH`
- `overheat_extension` 仍然保留：
  - `close_above_ma25_pct >= 10`
  - 或 `ma25_above_zxdkx_pct >= 15`
  - 命中后不直接升 `PASS`

### 调试重点

- 强环境下先看 `macd_phase` 是否能把真正右侧启动和伪突破分开
- 再看 `price_position` 是否过于宽松，导致末端加速票混进 PASS
- `trend_structure=5` 在 strong 环境可以接受，但必须配合 MACD 和总分验证

### 强样本通常长什么样

- 位置偏右侧但未失控
- MACD 处于强确认区
- 前期异动后未被明显破坏
- 更能接受启动确认而不是等待深回踩

### 当前希望筛到的 PASS 典型特征

当前 strong `PASS` 更希望筛到下面两类票，而不是简单把所有高分右侧票都抬进来：

- 右侧确认但不过热的 `B2 trend_start`
  - `trend_structure = 4`
  - `price_position = 5`
  - `previous_abnormal_move = 5`
  - `macd_phase` 高但结构健康
  - `volume_behavior` 以 `3 / 4` 为佳，不希望默认把 `5` 视为更优
- 具备弹性的 `B3 / B3+`
  - 尤其是 `rebound` 型 `B3`
  - `trend_structure = 4`
  - `price_position >= 4`
  - `previous_abnormal_move >= 5`
  - `3.0 <= macd_phase < 3.8` 时可以提前升级

当前 strong 下不希望进入 `PASS` 头部的典型形态是：

- `B2 + trend_start + volume_behavior = 5 + macd_phase` 高位
- 价格和均线关系已经明显扩张，但量价仍在加速
- 这类票不一定不能做，但更像“末端追高风险”，不应天然排在 strong `PASS top3` 前列

## 五、后续调参时的统一检查顺序

每次改 b2 环境逻辑，建议按下面顺序看：

1. 先看该环境下 `PASS/WATCH/FAIL` 的 5 日均值、胜率、中位数
2. 再看高涨幅前排样本最常出现的 `signal_type`、`trend_structure`、`price_position`
3. 再看低涨幅后排样本是否集中在某个过热或失真组合
4. 最后才看总分相关性

原因是：

> b2 在环境切片下，往往不是“总分越高越好”，而是“某几组小分组合是否把真正强样本提到了更高 verdict”。

## 六、一句话速记

- `weak`：先防守，优先安全位置和异动后承接
- `neutral`：抓回踩/整理后的再启动，防高 MACD 过热误升档
- `strong`：允许更积极的右侧确认，但要防末端追高
