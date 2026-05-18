# Dribull 筛选层

## 方法定位

`dribull` 可以理解为“先用偏结构性的条件做一次非 MACD 预筛，再用双周期 MACD 趋势组合做二次确认”的方法。

## 输入字段

`dribull` 依赖：

- `trade_date`
- `J`
- `zxdq`
- `zxdkx`
- `low`
- `close`
- `ma25`
- `ma60`
- `ma144`
- `turnover_n`
- `volume/vol`

## 两阶段结构

### 第一阶段：非 MACD 预筛

`prefilter_dribull_non_macd()` 与正式筛选共用大部分条件，主要作用是：

- 先缩小需要拉长历史窗口做 MACD warmup 的股票范围

### 第二阶段：正式筛选

在第一阶段通过后，再补足更长历史并做周日 MACD 趋势组合判断。

## 非 MACD 条件

### 1. 最低历史要求

要求：

- 历史长度至少覆盖 `144` 日
- 最近 `15` 日 `J` 不能有空值
- 当日必要字段不能缺
- 前一日 `ma60`、`volume` 不能缺

### 2. 最近 `J` 触发过低位规则

不是要求“今天”低位，而是要求近 `15` 天内至少有一天满足：

- `J < 15`
- 或 `J <= 历史 expanding 10% 分位`

### 3. `zxdq > zxdkx`

要求当前短趋势仍在长趋势之上。

### 4. `ma25` 支撑有效

要求：

- 当日最低价 `<= ma25 * 1.005`
- 当日收盘价 `>= ma25`

即要有回踩支撑，又不能收破。

### 5. 缩量

要求：

- 当日 `volume < 前一日 volume`

### 6. `ma60` 继续向上

要求：

- `latest_ma60 >= previous_ma60`

### 7. 距离 `ma144` 不可过远

要求：

- `abs(close / ma144 - 1) <= 30%`

## MACD 趋势条件

通过第一阶段后，再计算：

- 周线 MACD 趋势
- 日线 MACD 趋势

### 周线 / 日线无效直接失败

若任一周期 phase 属于：

- `invalid`
- `ended`

则失败。

### 双周期组合要求

当前接受两种组合：

1. 周线 `rising` + 日线 `rising`，且日线是 `is_rising_initial`
2. 周线 `rising` + 日线 `falling`

同时还有两个硬限制：

- 周线不能顶背离
- 日线不能顶背离

## 失败计数含义

- `fail_recent_j`
- `fail_insufficient_history`
- `fail_support_ma25`
- `fail_volume_shrink`
- `fail_zxdq_zxdkx`
- `fail_ma60_trend`
- `fail_ma144_distance`
- `fail_weekly_trend`
- `fail_daily_trend`
- `fail_trend_combo`

## 输出候选字段

通过筛选后，输出：

- `code`
- `pick_date`
- `close`
- `turnover_n`
