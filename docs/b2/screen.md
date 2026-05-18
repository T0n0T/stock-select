# B2 筛选层

## 方法定位

`b2` 当前是偏右侧启动确认的筛选方法，重点识别：

- `B2`
- `B3`
- `B3+`

## 输入字段

`b2` 依赖：

- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `turnover_n`
- `volume/vol`

## 核心思想

先在历史序列上构造 `B2` 信号框架，再判断目标日是否命中：

- `B2`
- `B3+`
- `B3`

若三者都未命中，再按首个失败条件计入对应统计。

## 长趋势过滤

`b2` 先构造：

- 短趋势 `st_l`: 双重 `EMA(span=10)`
- 长趋势 `lt_r`: `MA14/28/57/114` 均值

再得到：

- `honeymoon`: 最近 `30` 天内上穿且仍站上长趋势
- `breakaway`: 短趋势高于长趋势 `3%`
- `lt_stable`: 长趋势近 `30` 日翻向次数 `<= 2`
- `support`: `close >= lt_r * 0.95`

最终：

- 新股或短历史可放宽
- 否则要求满足 `tr_ok`
- 同时要求 `above_lt`

## 信号前置条件

### `pre_ok`

前一日要求：

- 涨幅 `< 3.7%`
- 前一日 `J < 39`

### `pct_ok`

当日涨幅：

- `>= 3.7%`

### `volume_ok`

当日量能：

- `volume > volume.shift(1)`

### `k_shape`

当日 K 线形态：

- 上影不能明显过长
- 收盘必须高于开盘

### `j_up`

- `J` 当日高于前一日

## `B2` 定义

`raw_b2` 同时满足：

- `pct_ok`
- `volume_ok`
- `k_shape`
- `pre_ok`
- `j_up`
- `tr_ok`
- `above_lt`

再要求：

- 在“本轮 J 上拐以来”的动态窗口内，`raw_b2` 只出现一次

即：

- `raw_b2_unique == True`

最终：

- `cur_b2 = raw_b2 & raw_b2_unique`

## `B3` / `B3+` 定义

在前一日刚出现 `B2` 的前提下继续看延伸：

### `B3`

- 前一日是 `B2`
- 当日属于窄幅整理
- 当日量能 `<=` 前一日的 `90%`
- `j_up`
- `tr_ok`
- `above_lt`

### `B3+`

在 `B3` 基础上，再要求：

- 当日量能 `<=` 前一日的 `52%`
- 收盘高于该次 `B2` 的前一日收盘
- 对应 `B2` K 线的上影占比 `< 1/3`

## 信号优先级

若目标日同时满足多个标记，输出优先级为：

1. `B2`
2. `B3+`
3. `B3`

## 失败计数含义

未命中任一信号时，按顺序统计首个失败原因：

- `fail_pre_ok`
- `fail_pct`
- `fail_volume`
- `fail_k_shape`
- `fail_j_up`
- `fail_tr_ok`
- `fail_above_lt`
- `fail_duplicate_b2`
- `fail_no_signal`

另有：

- `fail_insufficient_history`

## 输出候选字段

通过筛选后，输出：

- `code`
- `pick_date`
- `close`
- `turnover_n`
- `signal`

其中 `signal` 只会是：

- `B2`
- `B3`
- `B3+`
