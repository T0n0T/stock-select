# HCR Review 层

## 现状说明

`hcr` 当前没有专门的 reviewer，实现上仍走默认 reviewer：

- `review_symbol_history(method=\"hcr\")`

LLM prompt 也仍走默认：

- `prompt.md`

因此它的 review 口径和 `b1` / `b2` / `dribull` 不同，没有方法专属的复杂规则层。

## baseline reviewer

默认 reviewer 会基于目标日前历史日线计算：

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`

然后通过 `compute_method_total_score(\"hcr\", ...)` 计算总分。

## `hcr` 的总分口径

`hcr` 当前总分不使用 `macd_phase` 权重，而是走无 MACD 权重：

- `trend_structure`: `0.30`
- `price_position`: `0.25`
- `volume_behavior`: `0.40`
- `previous_abnormal_move`: `0.05`

`macd_phase` 字段仍会产出，但不参与总分。

## 默认 reviewer 的子分含义

### `trend_structure`

主要看：

- 是否站上 `ma20`
- 是否站上 `ma60`
- 最近 `20` 日涨幅状态

### `price_position`

主要看：

- 近 `120` 日区间内的位置
- 越靠区间低位，默认给分越高
- 靠近高位且近端均价高于中期均价时，给低分

### `volume_behavior`

主要看：

- 阳线平均量与阴线平均量对比
- 最大量日是偏多还是偏空
- 最新一日是否收阳

### `previous_abnormal_move`

主要看：

- 近 `40~60` 日上涨幅度
- 区间峰值量能相对均量的放大倍数

## verdict 口径

默认 `infer_verdict()` 对 `hcr` 使用单独阈值：

- `PASS`: `total_score >= 3.5`
- `WATCH`: `total_score >= 3.0`
- 否则 `FAIL`

但若：

- `volume_behavior <= 1.0`
- 或 `signal_type == distribution_risk`

则直接 `FAIL`。

## MACD gate

`hcr` 当前不走 `b1` / `b2` / `dribull` 那种双周期 MACD trend gate，而是沿用默认 reviewer 的简单 MACD 状态映射。

## 结果解读

当前 `hcr` review 还不是一个深度定制层，更像：

- 用统一 baseline reviewer 给突破共振候选做二次排序和分档

若后续需要把 `hcr` 做成独立方法，建议补一套专门 reviewer，而不是继续复用默认逻辑。
