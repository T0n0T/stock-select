# Left Peak 筛选层

## 方法定位

`left_peak` 是一个独立的左峰回踩筛选方法，复用 `b1/b2/dribull` 的基础 `prepared cache`，专门捕捉近期突破后仍靠近左峰高点的样本。

## 输入字段

`left_peak` 依赖：

- `trade_date`
- `J`
- `close`
- `ma25`
- `ma60`
- `turnover_n`
- `open`
- `high`
- `low`

## 筛选条件

1. 最近 `15` 日内至少一天收盘价创 `60` 日新高
2. 最近 `15` 日内至少一天满足 `J < 15`，或 `J <= 截至当日 expanding 10% 分位`
3. `ma25 > ma60`
4. 最近 `30` 日 `ma25` 的线性斜率 `> 0`
5. `close > zxdkx`
6. `zxdq > zxdkx`
7. `chg_d <= 4.0`
8. `v_shrink == True`
9. `lt_filter == True`
10. 通过 `src/stock_select/analysis/left_peak.py` 识别出有效左峰
11. 当日收盘价在左峰高点上下 `5%` 内

## 左峰判定

左峰识别复用 `find_recent_left_peak_breakout()`，筛选层只消费它返回的 `left_peak_high` 与有效标记，不再重复实现峰值状态机。

## 输出候选字段

通过筛选后，输出：

- `code`
- `pick_date`
- `close`
- `turnover_n`

## Review 分层

`left_peak` 使用专用 baseline review，不再复用 `b1` 占位口径。review 会额外计算：

- 左峰日期与左峰高点
- 左峰后第一根阴线的开盘价 `A`
- 入选日收盘价 `B`
- `B/A` 与 `|B/A - 1|`
- 周线/日线 MACD 状态机输出

PASS 分层优先考虑环境、左峰锚定距离、五维组合与 MACD 成熟度：

- `neutral` 环境相对放宽，但仍要求锚定距离不过远
- `weak` 环境严格要求 `|B/A - 1| <= 0.05` 且命中高胜率五维组合
- `strong` 环境不默认放宽，只接受更贴近锚点的再启动确认
