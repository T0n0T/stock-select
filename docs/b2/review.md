# B2 Review 层

## 方法定位

`b2` review 重点是确认“启动是否有效”，而不是单纯看形态好不好。当前实现明显倾向：

- `PASS` 宁缺毋滥
- 优先保留结构完整、不过热的 `trend_start`
- 对高位、过热、后段 MACD 样本主动压制

## 输入与环境

baseline reviewer：

- `review_b2_symbol_history()`

额外输入：

- `signal`，来自筛选层，通常为 `B2` / `B3` / `B3+`

额外特性：

- 接入 market environment profile
- `weak`、`neutral`、`strong` 三种环境分别走不同 bundle / profile 逻辑

## baseline 五个子分

### 1. `trend_structure`

重点看：

- `close >= ma25 >= zxdkx`
- `zxdkx` 是否继续上行
- 周/日 MACD 是否构成建设性组合
- 日线是否处于上升初期
- 是否存在顶背离

倾向：

- 周升日升且日线处于上升初期，分最高
- 周升日调但结构未坏，给中高分
- 仅勉强站上长支撑，给中低分

### 2. `price_position`

基于近 `120` 日箱体位置：

- `0.70 ~ 0.85` 默认最高分
- 太低说明未启动
- 太高说明偏热

环境可修改这一偏好：

- `weak`: 更强调低风险位置
- `strong`: 更接受突破后的右侧位置

### 3. `volume_behavior`

重点看：

- 最新价格是否压回短均价下方
- 近 `20` 日高位附近是否仍有量能支持
- 最新量能相对 `5` 日、`20` 日均量的关系

倾向：

- 接近 `20` 日高位且量能不塌，分高
- 价跌量增，分低

### 4. `previous_abnormal_move`

找近 `90` 日最大量对应异常事件，再看其后价格回撤到什么程度。

逻辑不是“涨得越少越好”，而是：

- 异动后若冗余空间仍大，说明追高风险高
- 回撤到合理区间且未完全破坏，分高

环境对它也有不同模式：

- `strict`
- `default`
- `lenient`

### 5. `macd_phase`

`b2` 这里直接调用 `score_macd_review_context_from_history()`，本质上是更复杂的双周期 MACD 波段评分。

它会综合：

- 周线/日线波浪方向
- 阶段位置
- 零轴位置
- 周日共振
- 特定 setup bonus

最终得到 `1~5` 分。

## baseline 总分

默认权重：

- `trend_structure`: `0.14`
- `price_position`: `0.22`
- `volume_behavior`: `0.00`
- `previous_abnormal_move`: `0.14`
- `macd_phase`: `0.35`
- `signal`: `0.15`

`signal` 分：

- `B3` / `B3+` -> `5.0`
- `B2` -> `4.0`

若接入 environment profile，则总分和阈值改用环境 profile。

## 额外扣分：过热惩罚

`b2` 在 baseline 总分之后，还会扣一次 `overheat_penalty`。

主要看：

- 近 `10` 日是否横盘过窄
- 近 `30` 日是否涨幅过大
- 当前日线状态是否已处于高风险后段

环境不同，惩罚参数不同：

- `strong` 惩罚较轻
- `neutral` 惩罚更重
- `weak` 当前直接不加这类惩罚

## verdict 主逻辑

`b2` 的 `verdict` 不是简单阈值，而是很多白名单/升级规则叠加。

核心方向：

- `distribution_risk` 基本不会给 `PASS`
- 强 MACD setup 可以直接给 `PASS`
- `trend_start` 在结构完整、不过热时最容易拿到 `PASS`
- `B3/B3+` 在强环境下有额外升级通道
- 大多数 `total_score >= 3.3` 但未命中白名单的样本，落在 `WATCH`

## 分环境 bundle

### `weak`

弱环境会进入 `_score_b2_weak_bundle()`：

- 对位置安全要求更高
- 允许一部分“安全再启动”样本通过 relaunch override 被提级
- 部分 `WATCH` 可升级为 `PASS`，但条件非常窄

### `neutral`

中性环境会进入 `_score_b2_neutral_bundle()`：

- 对 price position 会做轻微修正
- 对中段趋势启动会开放少量 `PASS` 白名单

### `strong`

强环境不走单独 bundle，但 profile 本身会：

- 更偏好右侧确认
- 提高 `macd_phase` 权重
- 放宽 `previous_abnormal_move`

## elastic watch

`WATCH` 会进一步判断是否属于弹性观察样本：

- `mid_macd_elastic_watch`
- `low_volume_elastic_watch`

并据此生成：

- `watch_score`
- `watch_tier`

当前层级：

- `WATCH-A`
- `WATCH-B`
- `WATCH-C`

## 结果解读

对 `b2` 来说：

- `PASS` 表示“结构、位置、MACD、过热风险都相对协调，适合作为启动样本”
- `WATCH` 很多时候代表“已经有启动迹象，但不是足够干净的右侧确认”
- summary 阶段只有 `PASS` 且 `total_score >= 4.0` 才会进入推荐列表

## 当前胜率统计

`b2` 当前实现下的总体胜率、分环境分 `verdict` 胜率、以及 `PASS top3` 胜率，统一见：

- [方法胜率统计](../share/method-win-rates.md)
