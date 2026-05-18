# HCR 筛选层

## 方法定位

`hcr` 是 `Historical High & Center Resonance Breakout`，即“历史高点与中心共振突破”。

它不是 `b1` 系列那种回调型筛选，而是一个更独立的突破共振模型。

## 输入字段

`hcr` 依赖独立 `prepared` 层中的字段：

- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `ma25`
- `ma60`
- `yx`
- `p`
- `resonance_gap_pct`
- `turnover_n`

## 核心指标

### `YX`

```text
(HHV(high, 30) + LLV(low, 30)) / 2
```

### `P`

当前实现是：

- 先做 `180` 日最高价滚动
- 再整体向后移 `60` 日
- 取最后一个有效值，作为当前全序列共享的符号级参考价

### `resonance_gap_pct`

```text
abs(YX - P) / abs(P)
```

## 硬筛选条件

`run_hcr_screen_with_stats()` 对目标日按以下顺序检查：

1. `yx`、`p` 可用，且 `p != 0`
2. `resonance_gap_pct <= 0.005`
3. `close > 1.0`
4. `close > yx`

全部通过后才入选。

## 历史要求

`hcr` 的参考价依赖：

- `180` 日 lookback
- `60` 日 shift

因此至少需要约 `240` 个交易日历史，仓库里常量名为：

- `HCR_REQUIRED_TRADING_DAYS = 240`

## 排名分数 `hcr_score`

`hcr` 在入选后还会额外计算一个排序分，并据此对候选池排序。

该分数不参与是否入选的硬判定，只参与候选池内部优先级。

### 评分组成

1. 共振紧密度
2. 收盘相对 `ma25` 的伸展幅度
3. `ma25` 相对 `ma60` 的趋势支撑幅度
4. 流动性

### 额外惩罚

- 若 `close_above_ma25_pct > 20%`，减 `22`
- 若当日涨幅 `> 5%` 且前一日涨幅 `> 4%`，减 `18`

## 输出候选字段

通过筛选后，输出：

- `code`
- `pick_date`
- `close`
- `turnover_n`
- `yx`
- `p`
- `resonance_gap_pct`
- `close_above_ma25_pct`
- `ma25_above_ma60_pct`
- `hcr_score`

## 排序规则

候选按以下顺序排序：

1. `hcr_score` 降序
2. `turnover_n` 降序
3. `resonance_gap_pct` 升序
4. `code` 升序
