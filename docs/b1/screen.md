# B1 筛选层

## 方法定位

`b1` 当前是偏左侧、偏回调低点的初筛方法。核心目标不是追右侧突破，而是找仍保留趋势支撑的 `N` 型回调候选。

## 输入字段

`b1` 依赖基础 `prepared` 层中的以下字段：

- `trade_date`
- `open`
- `high`
- `low`
- `J`
- `zxdq`
- `zxdkx`
- `close`
- `weekly_ma_bull`
- `max_vol_not_bearish`
- `chg_d`
- `v_shrink`
- `safe_mode`
- `lt_filter`
- `turnover_n`

缺任何必要字段，或字段无法转为有效数值时，都会记为 `fail_insufficient_history`。

## 默认票池

若使用默认 `--pool-source turnover-top`，在进入 B1 谓词链前，会先构建流动性票池：

- 按目标日 `turnover_n` 排序
- 只保留前 `5000` 只股票
- 同时要求目标日 `ma25 > ma60`

## 核心指标

### `turnover_n`

使用 `43` 日滚动成交额：

```text
((open + close) / 2) * volume
```

再做滚动求和。

### `zxdq` / `zxdkx`

- `zxdq`: 双重 `EMA(span=10)`
- `zxdkx`: `MA14`、`MA28`、`MA57`、`MA114` 的均值

### `weekly_ma_bull`

先按周取最后一个实际交易日收盘价，再计算周线均线多头：

- 短期周均线 > 中期周均线 > 长期周均线

实现里的窗口是：

- `10`
- `20`
- `30`

## tightening 与风险控制字段

`compute_b1_tightening_columns()` 会生成：

- `chg_d`
- `amp_d`
- `body_d`
- `vm3`
- `vm5`
- `vm10`
- `m5`
- `v_shrink`
- `safe_mode`
- `lt_filter`

### `v_shrink`

- 近 `3` 日均量 `<` 近 `10` 日均量

### `safe_mode`

识别近期放量派发后的冷却区：

- 若出现大阴/长黑并伴随异常放量，视为 `bad_dump`
- 普通冷却期为 `5` 天
- 近 `10` 天若出现两次及以上 `bad_dump`，冷却期扩为 `10` 天
- 只有走出冷却区后，`safe_mode` 才为真

### `lt_filter`

限制长趋势近 `30` 日内频繁翻向：

- 统计长趋势方向近 `30` 日翻向次数
- 默认要求翻向次数 `<= 2`
- 但若最近 `30` 日发生上穿长趋势，或短趋势明显高于长趋势 `3%` 以上，则允许豁免

## 实际筛选顺序

对单只股票，`run_b1_screen_with_stats()` 按以下顺序执行：

1. `J < 15`，或 `J <= 截至当日 expanding 10% 分位`
2. `zxdkx` 可计算
3. `close > zxdkx`
4. `zxdq > zxdkx`
5. `weekly_ma_bull == True`
6. `max_vol_not_bearish == True`
7. `chg_d <= 4.0`
8. `v_shrink == True`
9. `safe_mode == True`
10. `lt_filter == True`

全部通过后，股票入选候选。

入选后会额外标注主图公式中的黄色 `B1` 信号，写入候选字段 `yellow_b1`：

- `B1_环境 := TR_OK AND ABOVE_LT AND NOT(CUR_B2)`
- `转色 := V_DIFF > REF(V_DIFF, 1) AND REF(V_DIFF, 1) <= REF(V_DIFF, 2)`
- `B1_黄_原 := B1_环境 AND 转色 AND J < 29 AND PCT <= 3.7`
- `B1_黄 := B1_黄_原 AND COUNT(B1_黄_原, 5) <= 3`

## 失败计数含义

- `fail_j`: 当前位置不够低，未满足超卖或历史低分位
- `fail_insufficient_history`: 历史长度不足，或必要字段/数值无效
- `fail_close_zxdkx`: 收盘价未站上 `zxdkx`
- `fail_zxdq_zxdkx`: `zxdq` 未站上 `zxdkx`
- `fail_weekly_ma`: 周线均线不满足多头
- `fail_max_vol`: 近 `20` 日最大成交量对应 K 线偏空
- `fail_chg_cap`: 当日涨幅超过 `4%`
- `fail_v_shrink`: 未出现缩量
- `fail_safe_mode`: 仍在派发后的危险冷却区
- `fail_lt_filter`: 长趋势过于反复，且未命中例外放行条件

另有两个入选后统计项：

- `selected_yellow_b1`: 入选且命中黄色 `B1` 信号的数量
- `selected_non_yellow_b1`: 入选但未命中黄色 `B1` 信号的数量

## 输出候选字段

通过筛选后，输出：

- `code`
- `pick_date`
- `close`
- `turnover_n`
- `yellow_b1`
