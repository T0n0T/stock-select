# Dribull Review 层

## 方法定位

`dribull` 的 review 基本复用了 `b2` 的大部分结构评分逻辑，但最终结论更偏向“MACD 组合是否仍然健康”。

## baseline reviewer

使用：

- `review_dribull_symbol_history()`

当前不接 environment profile。

## baseline 五个子分

除 `macd_phase` 外，当前全部复用 `b2` 子分函数：

- `trend_structure` -> 复用 `_score_b2_trend_structure()`
- `price_position` -> 复用 `_score_b2_price_position()`
- `volume_behavior` -> 复用 `_score_b2_volume_behavior()`
- `previous_abnormal_move` -> 复用 `_score_b2_previous_abnormal_move()`

### `macd_phase`

通过 `map_macd_phase_score(method=\"dribull\")` 计算，依赖：

- 周线 MACD 趋势
- 日线 MACD 趋势

## baseline 总分

`dribull` 当前走默认五因子权重：

- `trend_structure`: `0.18`
- `price_position`: `0.18`
- `volume_behavior`: `0.24`
- `previous_abnormal_move`: `0.20`
- `macd_phase`: `0.20`

## verdict 逻辑

大致分三步：

1. 用默认 `infer_verdict()` 先给出基础结论
2. 进入 `_refine_dribull_verdict()` 做一次方法特有修正
3. 再经过 `apply_macd_verdict_gate(method=\"dribull\")`

## `dribull` 特有修正

### 弹性 `PASS`

若初始 verdict 是 `WATCH`，但满足：

- `3.9 <= total_score < 4.2`
- `trend_structure >= 4.0`
- `price_position >= 5.0`
- `volume_behavior >= 2.0`
- `previous_abnormal_move >= 5.0`
- `macd_phase >= 4.0`

则会升级为 `PASS`。

### `PASS` 回压

即便初始判定为 `PASS`，只要出现以下情况，也会回压到 `WATCH`：

- `total_score < 4.2`
- `price_position < 4.0`
- `volume_behavior < 4.0`

也就是说，`dribull` 的 `PASS` 比默认阈值更严格。

## MACD gate

`apply_macd_verdict_gate(method=\"dribull\")` 会进一步限制：

- 若日线状态为 `hard_invalid` 或 `deteriorating`，直接 `FAIL`

## 结果解读

对 `dribull` 来说：

- `PASS` 必须同时满足结构、位置、MACD 组合都比较顺
- `WATCH` 里会保留不少“结构还行，但发动时点未完全对齐”的样本
