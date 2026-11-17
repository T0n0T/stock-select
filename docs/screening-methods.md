# 选股筛选方法过滤条件

本文整理当前 Rust CLI 中各个选股筛选方法的实际硬过滤条件。口径以代码实现为准，主要来源为 `src/screening.rs`、`src/strategies/b2.rs`、`src/strategies/b3.rs`、`src/strategies/lsh.rs`、`src/strategies/scm_pbm.rs`、`src/strategies/qianlong.rs` 和 `src/engine/run.rs`。

实际接入 screen 的方法：`b2`、`b3`、`lsh`、`scm`、`pbm`、`qianlong`。

`b1`、`dribull` 当前没有 screen 策略实现；在 CLI 执行 `screen` 时会返回未实现错误，因此本文不列独立过滤条件。`qianlong` 当前只接入 `screen` 和因子导出，不接入模型 `run`、`review-list` 或 LLM 复盘。

## 公共流程

`screen` 以 stock-cache DB-native 日线窗口为主路径，读取截至 `pick_date` 的约 252 个交易日预计算行情和指标，并在进入具体策略前先完成预处理和股票池裁剪。EOD prepared cache 写入后会按日期保留最近 30 个 EOD artifact；可用 `STOCK_SELECT_PREPARED_CACHE_LIMIT` 调整保留数量。盘中 prepared cache 不计入这个保留数量，也不会被该策略清理。

### 预处理字段

每只股票按交易日排序后计算以下策略输入字段：

| 字段 | 口径 |
|------|------|
| `turnover_n` | 近 43 个交易日 `((open + close) / 2) * vol` 的滚动求和，缺失时按 0 写入 |
| `K/D/J` | 日线 KDJ，周期 9 |
| `DIF/DEA/MACD hist` | 日线 MACD，参数 12/26/9 |
| `MA25/MA60/MA144` | 日线收盘价滚动均线 |
| `zxdq/zxdkx` | 中道/中轨线 |
| `chg_d` | 相对前一交易日的收盘涨跌幅 |

### 股票池过滤

默认股票池是 `turnover-top` 股票池：

- 只取 `pick_date` 当天有 prepared 行情的股票。
- `b2` / `b3`：要求当日 `MA25 > MA60`，否则不会进入策略判断。
- `lsh` / `scm` / `pbm` / `qianlong`：不做 `MA25 > MA60` 前置过滤。
- 按 `turnover_n` 从高到低排序，同分按代码升序，取 `turnover_n` 最高的前 5000 只。

`custom` 股票池：

- 来源为 `--pool-file`、`STOCK_SELECT_POOL_FILE` 或 `runtime/custom-pool.txt`。
- 文件中的股票代码会被标准化为 `.SH` / `.SZ` 代码。
- 只保留在 `pick_date` 有 prepared 行情的股票。
- 不执行 `turnover-top` 排名，也不执行 `b2` / `b3` 的 `MA25 > MA60` 前置股票池过滤；后续仍会执行各方法自身的策略条件。

## `b2`

`b2` 是放量阳线突破类筛选，候选信号写为 `B2`。

### 基础过滤

- 股票在 `pick_date` 必须有行情行。
- 当前索引至少为 2，即至少有前两条历史记录用于比较前一日和前二日。
- 若使用默认 `turnover-top` 股票池，进入策略前还必须满足当日 `MA25 > MA60`。
- 当日触发 B2 信号后，还要求以日线历史按自然月聚合的最新月线 MACD `DEA > 0`。

### raw B2 条件

当前日同时满足以下条件时，先记为 raw B2：

| 条件 | 口径 |
|------|------|
| 当日涨幅 | 当日涨幅 `pct >= 3.7%`，其中 `pct = (close - prev_close) / prev_close * 100` |
| 成交量 | 当前成交量大于前一日成交量 |
| K 线形态 | 当日为阳线，且上影线不大于有效实体：`high - close <= close - min(open, prev_close)` |
| 前一日状态 | 前一日涨幅 `< 3.7%`，且前一日 `J < 39` |
| J 值 | 当前 `J` 值大于前一日 `J` 值 |
| 趋势结构 | `tr_ok` 为真 |
| 长期参考位 | `above_lt` 为真 |

### 趋势结构 `tr_ok`

`b2` 会先计算：

- `st_l = EMA(EMA(close, 10), 10)`。
- `lt_r = (MA14 + MA28 + MA57 + MA114) / 4`。
- `st_l` 向上穿越 `lt_r` 的最近天数。
- `lt_r` 方向在近 30 个交易日内的翻转次数。

当历史不足 114 个索引位时，视为新股窗口，`tr_ok = true`，`above_lt = true`。

历史进入成熟窗口后，`tr_ok` 满足以下任一条件即可：

- 最近 30 日内 `st_l` 向上穿越 `lt_r`，且当前 `st_l > lt_r`。
- `st_l > lt_r * 1.03`。
- `st_l > lt_r`、`close > lt_r`，且近 30 日 `lt_r` 方向翻转次数不超过 2 次。

成熟窗口的 `above_lt` 要求 `close > lt_r`。

### 去重条件

`b2` 不会把同一轮 `J` 转强周期内的多个 raw B2 都输出为候选。

实现口径：用 `J` 从非上升转为上升的位置作为周期起点，统计当前周期内 raw B2 出现次数；同一轮 `J` 转强周期内只保留第一次 raw B2，即 `raw_b2_count == 1`。

## `b3`

`b3` 是 B2 次日缩量震荡类筛选，候选信号写为 `B3` 或 `B3+`。当前实现依赖前一交易日已经触发 `B2`，并非完全独立的 B3 公式。

### 基础过滤

- 股票在 `pick_date` 必须有行情行。
- 当前索引至少为 3。
- 若使用默认 `turnover-top` 股票池，进入策略前还必须满足当日 `MA25 > MA60`。

### B3 条件

当前日同时满足以下条件时，输出 `B3`：

| 条件 | 口径 |
|------|------|
| 前置信号 | 前一交易日已经触发 `B2` |
| 当日震荡 | `abs(pct) < 5.05%`，其中 `pct = (close - prev_close) / prev_close * 100` |
| 当日振幅 | 当前振幅 `amp` 小于阈值，`amp = (high - low) / prev_close * 100` |
| 振幅阈值 | `300` 或 `688` 开头股票阈值为 12%，其他股票阈值为 8% |
| 缩量 | 当前成交量不超过前一日的 `90%` |
| J 值 | 当前 `J` 值大于前一日 `J` 值 |
| 趋势结构 | 沿用 B2 的 `tr_ok`，当前日必须为真 |
| 长期参考位 | 沿用 B2 的 `above_lt`，当前日必须为真 |

### B3+ 条件

`B3+`：在 `B3` 基础上，再同时满足：

- 当前成交量不超过前一日的 `52%`。
- 当前收盘价高于前一日收盘价。

当同一天同时满足 `B3` 和 `B3+` 时，候选信号优先写为 `B3+`。

## `lsh`

`lsh` 保留原策略和模型路径，供旧候选与模型兼容。新策略使用 `scm`（Sustained Cross MA25）和 `pbm`（Pullback MA25），两者分别训练和加载模型。

### 基础过滤

- 股票在 `pick_date` 必须有行情行。
- 当前索引至少为 25，且昨日、当日 `MA25` 均已计算出来。
- 默认 `turnover-top` 股票池不对 `lsh` 做 `MA25 > MA60` 前置过滤。

### 日线形态条件

当前日必须同时满足：

- 昨日最低价低于昨日 `MA25`：`REF(low, 1) < REF(MA25, 1)`。
- 当日为阳线：`close > open`。
- 当日收盘价高于 `MA25`：`close > MA25`。
- 昨日成交量低于前一日成交量：`REF(volume, 1) < REF(volume, 2)`。

### 周线/月线 MACD 条件

旧 `lsh` 会在日线视角聚合周线/月线收盘序列：

- 周线：按 ISO 自然周分组，取已结束周的最后一个日线收盘价；最新未结束周使用当前最新日线收盘价。
- 月线：按自然月分组，取已结束月的最后一个日线收盘价；最新未结束月使用当前最新日线收盘价。

分别对周线和月线模拟收盘序列计算 MACD，参数为 12/26/9。周线和月线最新 DIF 与 DEA 都大于 0 时，才通过过滤。

## `scm` / `pbm`

`scm`（Sustained Cross MA25）与 `pbm`（Pullback MA25）共享昨日 MA25 回踩、当日阳线收复和当日放量日线形态，候选信号分别写为 `SCM` 和 `PBM`。

- 昨日最低价低于昨日 `MA25`：`REF(low, 1) < REF(MA25, 1)`。
- 入选日为阳线：`close > open`，且收盘价高于当日 `MA25`。
- 入选日成交量严格大于前一交易日：`volume > REF(volume, 1)`。

按最近 20 个交易日收盘价相对 `MA25` 的状态区分 SCM 与 PBM：

- `scm`：最近 20 日中至少 16 日收盘高于当日 `MA25`，且最近 10 日中至少 8 日收盘高于当日 `MA25`。
- `pbm`：不满足 SCM 条件，但最近 5 日内至少发生一次有效收盘上穿，即前一日 `close <= MA25`、当日 `close > MA25`。
- 选股日收盘必须高于当日 `MA25`；否则不进入 SCM 或 PBM。最近 20 日所需 MA25 数据不足时也不进入任一类别。
- 两个方法都不做 `MA25 > MA60` 股票池前置过滤。

### 周线/月线 MACD 条件

- 月 MACD 柱体必须较上一个月增加：当前月 `macd_monthly_hist` 大于前一个月；月线按自然月聚合。
- 周 MACD 柱体必须大于 0，即红柱；周线按 ISO 自然周聚合。
- 周线使用选股日的 prepared `macd_weekly_hist`；字段缺失时，按日线聚合周收盘价并用 12/26/9 参数计算。
- 月线比较上一完整月最后交易日与选股日的 prepared `macd_monthly_hist`。DB-native 加载会额外读取上月最后交易日的数据库月柱，与本月柱一起换算到选股日的前复权基准。周期内每天都从上一完整周期状态推演一次，本月未结束时使用截至选股日的临时月柱。
- 月柱比较的两侧必须同源：数据库值均有效时直接比较；两侧均无数据库值时，统一按窗口内月收盘价计算；仅缺一侧时不通过，禁止混用长历史预热值和短窗口重算值。
- 不要求周线/月线 DIF 或 DEA 为正。

### 周线最大成交量 K 线条件

- 检查最近 10 根 ISO 周 K 线，包含截至选股日的当前未结束周。
- 周 K 开盘价取该周首个日线开盘价，收盘价取该周最后一个日线收盘价，成交量为周内日成交量之和。
- 最近 10 周中成交量最大的一根周 K 必须为红 K（收盘价高于开盘价）。
- 选股日当前价格必须严格高于该最大量红周 K 的开盘价；盘中优先使用实时前复权价，EOD 使用选股日收盘价。
- SCM/PBM 回填会将日期任务限制为单 worker，因为每个 screen 需要加载全市场历史窗口；`--workers` 对其他方法保持原行为。

`scm` 和 `pbm` 是两个独立的 `--method` 值，模型产物分别位于 `runtime/models/scm/` 和 `runtime/models/pbm/`。

## `qianlong`

`qianlong` 是三级别 MACD 反转叠加阳包阴和放量大涨的筛选，候选信号写为 `QIANLONG`。

### 基础过滤

- 股票在 `pick_date` 必须有行情行，且代码不能以 `.BJ` 结尾。
- 当前索引至少为 14，即至少有 15 条日线记录用于判断绿柱背离。
- 默认 `turnover-top` 股票池不对 `qianlong` 做 `MA25 > MA60` 前置过滤。

### 周线/月线 MACD 条件

`qianlong` 跟随 B2/B3/LSH 的既有 MACD 取值方式，复用 shared prepared cache 中已有的周期字段：

- 周线优先读取 `macd_weekly_dif` / `macd_weekly_dea`。
- 月线优先读取 `macd_monthly_dif` / `macd_monthly_dea`。
- 周线和月线的最新 DIF 与 DEA 都大于 0 时，才通过过滤。
- 任一周期字段缺失时按日线聚合周线/月线收盘价，再以 12/26/9 参数计算对应周期 MACD；聚合口径与 LSH 相同。

通过 `calc_versions.price_basis = asof_qfq_v1` 校验后，已有 schema 11 prepared cache 可以直接复用，不需要为 `qianlong` 重建整份缓存。缺少此价格基准标记的旧 DB-native 缓存会按需重建，这属于共享数据纠错，而非潜龙专用升级。潜龙不依赖潜龙专用的上一周期字段，EOD 缓存命中后不会为潜龙补查周期状态，也不改写原缓存文件。

### 日线绿柱背离条件

日线只统计 `macd_hist < 0` 的绿柱段。允许两种形态：

- 最近两段绿柱：两段都必须已经出现峰值后的缩短，第二段绝对峰值小于第一段绝对峰值。
- 最近一段连续绿柱：段内必须出现两个已经缩短的局部峰，第二个绝对峰值小于第一个绝对峰值。

第二段峰值必须已经开始缩短；如果第二段仍在继续放大，则不通过。峰值后跨到红柱或零轴以上，也视为已经缩短；最新一根不要求仍处于绿柱段。

### K 线和量能条件

当前最新 K 线必须为阳包阴：

- 昨日为阴线：`REF(close, 1) < REF(open, 1)`。
- 今日为阳线：`close > open`。
- 今日收盘价高于昨日最高价：`close > REF(high, 1)`。
- 今日开盘价低于昨日收盘价：`open < REF(close, 1)`。

近 22 条记录内还必须出现至少一次放量大涨：

- 当日涨幅 `pct >= 9.5%`。
- 当日成交量 / 前 3 到 5 条记录均量 `>= 1.5`。

### 盘中口径

盘中 `screen --method qianlong --intraday` 会把 Tushare `rt_k` 快照接入最新日线：

- 实时日线 MACD 可作为第二段峰值后的缩短柱。
- 实时周线/月线 DIF 和 DEA 从本周/本月开始前的已完成周期状态外推，并沿用上述正值条件。
- 实时 K 线可触发阳包阴；实时成交量可触发近 22 条记录内的放量大涨。

## run 阶段

对支持模型推理的方法，`run` 阶段不再增加硬过滤。它会读取 `screen` 产出的候选，补 prepared history，计算因子，然后使用对应 method 的 LightGBM 模型打分排序。`qianlong` 当前没有已发布模型，执行 `run` 或 `review-list` 会被 capability 保护拒绝。

当前排序阶段还有一个后置分数调整：在模型原始分排序后先归一化分数，再根据筹码因子调整排名分数。该调整只改变排序，不剔除候选：

- `env = neutral` 时，`cyq_winner_rate` 超过 80 会产生最高 0.14 的扣分。
- `env = strong` 时，`cyq_cost_90_width_pct > 25` 会扣 0.35。

LLM 或人工复盘只写 annotation，不改变 `model_rank` 或 `model_score`。
