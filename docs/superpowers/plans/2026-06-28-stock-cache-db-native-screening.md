# stock-cache 数据库原生筛选迁移实施计划

**目标：** 将筛选准备阶段从“拉取三年全市场数据并在 `stock-select` 内重复计算指标”迁移为“以 `stock-cache` 数据库预计算结果为主路径”，使用约 252 个交易日窗口，显著缩短 EOD 和盘中筛选准备时间，并重建训练因子注册体系。

**架构：** `stock-cache` 提供 Tushare 原始指标、本地版本化 MACD、滚动窗口、左峰结构和同花顺板块数据；`stock-select` 负责策略信号、MACD 状态机、特殊结构因子注册、prepared cache 和模型输入 artifact。旧训练 schema、申万行业字段和三年慢路径不再作为兼容目标。

**技术栈：** Rust、PostgreSQL、Serde prepared cache、Python ML schema、TDD。

---

## 已确认决策

- 数据主路径以 `stock-cache` 为准，缺关键 DB 指标默认 fail fast，不回退三年本地慢路径。
- EOD 窗口按最近 252 个交易日，不按自然年。
- prepared cache 继续保存一年窗口 `PreparedRow`，但 schema bump，旧 cache 全部失效。
- KDJ 直接以 Tushare `stock_stk_factor_pro.kdj_*_qfq` 为准。
- MACD 日/周/月使用 `stock_daily_asof_indicators` 和 `stock_period_indicator_state`，显式使用 `calc_version = 'macd_qfq_12_26_9_v1'`。
- MACD 状态机暂留 `stock-select`，输入改为 DB MACD 序列，不从 close 重算 MACD。
- 盘中长周期 MACD 用 period state + live qfq price 推演，不能用昨天 as-of 继续递推。
- 盘中 rolling/left-peak 第一版使用上一交易日 EOD 结构值，只实时更新当日 OHLCV、量价形态和 MACD。
- 同花顺板块使用当前 `index_ths_member` 成分关系；历史训练允许该口径，并在报告中标记为 current membership。
- 多板块归属按主板块 + 聚合板块特征处理，保证一股票一行。
- 训练因子重建注册，不兼容旧 schema，不保留 `sw_l2_*` 旧语义字段。

## 性能目标

- EOD prepared cache 重建：目标 30 秒内，理想 10 秒内。
- 已有 prepared cache 的 screen：目标 5 秒内。
- 盘中 snapshot prepared：目标 15 秒内，包含实时行情获取和 period-state 推演。
- 日终候选 + 因子导出整体：目标 60 秒内。
- 日志继续输出阶段耗时：DB load、prepare mapping、cache write、strategy run、factor build。

## 本地验证数据库

实现和验证阶段先使用用户提供的本地 `stock-cache` PostgreSQL 数据库连接，不把 DSN 写入代码、文档或测试 fixture。运行命令时通过环境变量 `POSTGRES_DSN` 注入。

该测试库当前约束：

- 已整理交易日：`2026-06-01` 到 `2026-06-15`。
- 已具备约三年 warmup 数据，可用于验证 252 交易日窗口、MACD state/as-of、rolling、left-peak 等计算表覆盖。
- 首批 EOD 验证 pick_date 建议使用该范围内日期，例如 `2026-06-15`。
- 验证时不要打印 `.env`、完整 DSN 或 token。

建议实现前先做只读覆盖探测：

- `stock_stk_factor_pro` 在 pick_date 的横截面行数。
- `stock_daily_asof_indicators` 在 pick_date 且 `calc_version = 'macd_qfq_12_26_9_v1'` 的行数。
- `stock_daily_rolling_factors` 在 pick_date 且 `calc_version = 'rolling_qfq_v1'` 的行数。
- `stock_daily_left_peak` 在 pick_date 且 `calc_version = 'left_peak_qfq_v1'` 的行数。
- `index_ths_daily`、`index_daily_asof_indicators`、`index_moneyflow_cnt_ths` 在 pick_date 的覆盖情况。
- 最近 252 个交易日的起止日期。

---

## 数据源映射

### 股票 EOD 主表

从 `stock_stk_factor_pro` 读取：

- `open_qfq/high_qfq/low_qfq/close_qfq` 作为 prepared 价格。
- `vol`、`amount`、`turnover_rate`、`turnover_rate_f`、`volume_ratio`。
- Tushare 技术指标：`kdj_*_qfq`、`macd_*_qfq`、`rsi_*_qfq`、`boll_*_qfq`、`dmi_*_qfq`、`wr_qfq`、`bias*_qfq`、`roc_qfq`、`mtm_qfq`、`trix_qfq`、`obv_qfq`、`vr_qfq`、`psy_qfq` 等。
- 估值规模：`pe`、`pe_ttm`、`pb`、`ps`、`ps_ttm`、`dv_ratio`、`total_mv`、`circ_mv`、`total_share`、`free_share`。

### 版本化 MACD

从 `stock_daily_asof_indicators` 读取：

- `daily_dif_asof/daily_dea_asof/daily_hist_x2_asof`。
- `weekly_dif_asof/weekly_dea_asof/weekly_hist_x2_asof`。
- `monthly_dif_asof/monthly_dea_asof/monthly_hist_x2_asof`。
- `*_dea_pctile_asof` 和 `*_period_count`。

`hist_x2` 写入训练因子时除以 2，保持 `hist = dif - dea` 语义。

### 滚动窗口和左峰

从 `stock_daily_rolling_factors` 读取：

- `ma25_qfq`、`ma144_qfq`、`ma220_qfq`。
- `high_20_qfq`、`high_90_qfq`、`low_90_qfq`、`high_120_qfq`、`low_120_qfq`。
- `position_90d`、`position_120d`。
- `volume_ma5`、`volume_ma20`、`volume_to_ma5_ratio`、`volume_to_ma20_ratio`、`volume_ma5_to_ma20_ratio`。
- `turnover_rate_ma5`、`turnover_to_ma5_ratio`。
- `range_compression_20d`、`range_compression_40d`。

从 `stock_daily_left_peak` 读取：

- `left_peak_date`、`left_peak_high`、`breakout_date`、`breakout_close`。
- `breakout_body_above_left_peak`、`first_bear_date`、`first_bear_open`、`first_bear_missing`。
- `b_div_a`、`abs_ba_minus_1`、`a_lt_b`、`is_valid`、`status`。

### 同花顺板块

从 `index_ths_member`、`index_ths_daily`、`index_daily_asof_indicators`、`index_moneyflow_cnt_ths` 读取并衍生：

- 主板块行情、收益、量能、换手、MACD。
- 板块资金流、热度排名、领涨股涨幅。
- 股票相对主板块和所属板块集合的表现。

`index_ths_member` 是当前成分关系，不是历史快照。

---

## 新训练因子族

### DB 原生因子

- 行情与流动性：涨跌幅、成交额、成交量、换手率、量比、流通市值、总市值。
- 估值规模：PE/PB/PS/股息率/股本结构。
- Tushare 技术指标：KDJ、RSI、BOLL、DMI、WR、BIAS、ROC、MTM、TRIX、OBV、VR、PSY。
- 版本化 MACD：daily/weekly/monthly DIF、DEA、hist、DEA 分位、周期样本数。
- 滚动位置与量能：MA25/144/220、90/120 日位置、量能比、换手比、压缩度。
- 左峰结构：有效性、状态、突破、第一阴线、A/B 结构。
- THS 板块：主板块、最强板块、平均板块、资金流和相对板块表现。

### 特殊结构因子

箱体/位置：

- `structure_box_position_120d_pct`
- `structure_box_mid_position_120d_pct`
- `structure_close_to_120d_max_pct`
- `structure_close_to_120d_min_pct`
- `structure_close_to_120d_range_center_pct`
- `structure_range_width_120d_pct`
- `structure_hl90_position`
- `structure_hl90_range_pct`
- `structure_range_compression_20d`
- `structure_range_compression_40d`

均线/中线：

- `structure_close_to_ma25_pct`
- `structure_low_to_ma25_pct`
- `structure_near_ma25_support_flag`
- `structure_ma25_slope_5d_pct`
- `structure_ma_aligned_flag`
- `structure_zxdkx`
- `structure_close_to_zxdkx_pct`
- `structure_zxdq_slope_5d_pct`
- `structure_zxdkx_slope_5d_pct`

MACD 状态机：

- `macd_state_phase_score`
- `macd_state_daily_phase_type`
- `macd_state_daily_wave_index`
- `macd_state_daily_wave_stage`
- `macd_state_weekly_phase_type`
- `macd_state_weekly_wave_index`
- `macd_state_weekly_wave_stage`
- `macd_state_weekly_daily_combo_type`
- `macd_state_daily_rising_initial_flag`
- `macd_state_top_divergence_flag`

MACD 数值结构：

- `macd_daily_dif_to_close_pct`
- `macd_daily_dea_to_close_pct`
- `macd_daily_hist_to_close_pct`
- `macd_daily_hist_delta_to_close_pct`
- `macd_daily_hist_slope_3d_to_close_pct`
- `macd_daily_hist_positive_flag`
- `macd_weekly_dea_pctile`
- `macd_weekly_hist`
- `macd_monthly_dea_pctile`
- `macd_monthly_hist`

异常量/事件：

- `volume_event_abnormal_days_ago`
- `volume_event_abnormal_to_ma20_ratio`
- `volume_event_body_pct`
- `volume_event_price_to_current_pct`
- `volume_event_post_drawdown_pct`
- `volume_event_redundant_position_pct`

K 线和信号上下文：

- `bar_close_position_pct`
- `bar_upper_shadow_pct`
- `bar_lower_shadow_pct`
- `bar_amplitude_pct`
- `bar_body_pct`
- `signal_bullish_engulf_prev_bearish_flag`
- `signal_bullish_engulf_volume_ratio`
- `signal_yang_engulf_ma25_flag`
- `signal_prev_b2_flag`
- `signal_b3_plus_flag`

左峰：

- `left_peak_valid`
- `left_peak_status`
- `left_peak_distance_pct`
- `left_peak_breakout_close_to_peak_pct`
- `left_peak_b_div_a`
- `left_peak_abs_ba_minus_1`
- `left_peak_a_lt_b`
- `left_peak_breakout_body_above_flag`
- `left_peak_first_bear_missing_flag`
- `left_peak_days_since_peak`
- `left_peak_days_since_breakout`
- `left_peak_days_since_first_bear`

---

## 盘中路径

盘中模式必须区分 EOD 结构背景和实时推演：

1. 读取上一交易日前 252 个交易日 EOD prepared 数据。
2. 用 Tushare `rt_k` 构造当日 live OHLCV。
3. 将 live 未复权价转换为与 `close_qfq` 一致的 `price_live_qfq`。
4. 从 `stock_period_indicator_state` 取上一完成 daily/weekly/monthly 状态，递推当日 live MACD。
5. 从 `index_period_indicator_state` 取同花顺板块/指数上一完成状态，递推 live 板块/指数 MACD。
6. rolling/left-peak 第一版使用上一交易日 EOD 结构值，并在 diagnostics 标记 `intraday_structure_source = previous_eod`。

禁止使用昨天 weekly/monthly as-of 继续递推今天。

---

## 覆盖门禁

默认硬失败：

- 找不到最近 252 个交易日窗口。
- EOD pick_date 缺 `stock_stk_factor_pro` 横截面。
- 缺 `stock_daily_asof_indicators` 的 `macd_qfq_12_26_9_v1`。
- 缺 `stock_daily_rolling_factors` 的 `rolling_qfq_v1`。
- 缺 `stock_daily_left_peak` 的 `left_peak_qfq_v1`。
- intraday 缺 `stock_period_indicator_state`。

THS 板块因子缺失时，如果方法配置要求板块因子则失败；否则该族因子写 missing 并记录覆盖率。

可保留内部诊断环境变量 `STOCK_SELECT_ALLOW_INCOMPLETE_DB_NATIVE=1`，只用于测试覆盖问题，不作为正式筛选 fallback。

---

## Files and Responsibilities

- Modify: `src/db.rs`
  - 新增 DB-native loader SQL，读取 252 交易日窗口和 DB 预计算表。
  - 移除旧 `daily_market` + 申万行业聚合路径作为主路径。
- Modify: `src/model.rs`
  - 必要时扩展 `MarketRow`/`PreparedRow` 的 DB-native 字段承载能力。
- Modify: `src/screening.rs`
  - 252 交易日窗口。
  - `prepare_rows` 优先映射 DB 指标，只保留必要本地序列逻辑。
  - 盘中 period-state 推演入口。
- Modify: `src/cache.rs`
  - bump prepared cache schema。
  - metadata 记录 DB-native source、252 交易日窗口、calc_version。
- Modify: `src/factors/registry.rs`
  - 重建训练因子注册，按 DB-native 因子族和特殊结构因子族输出。
- Modify: `src/factors/*`
  - 将旧因子函数拆为可复用的 DB-native 衍生函数，旧 schema 名称不再作为约束。
- Modify: `ml/dataset/rank_dataset.py`
  - 重建训练 schema 注册，不兼容旧字段。
- Modify: `docs/architecture.md`
  - 更新数据主路径和盘中路径。
- Modify: `docs/model.md`
  - 更新新训练因子族和模型契约。
- Modify: `docs/workflow.md`
  - 更新 EOD/盘中运行流程和覆盖检查说明。

---

## Implementation Tasks

### Task 1: DB-native loader 契约

- [ ] 写 failing Rust 测试：DB-native loader 从 fixture row 映射 `stock_stk_factor_pro` 的 qfq OHLC、KDJ、Tushare 技术指标。
- [ ] 写 failing Rust 测试：loader 映射 `stock_daily_asof_indicators` 的 daily/weekly/monthly MACD，并将 `hist_x2 / 2` 写入内部 hist 语义。
- [ ] 写 failing Rust 测试：loader 映射 rolling/left-peak 字段到 `db_factors`。
- [ ] 使用本地验证数据库只读探测 `2026-06-01` 到 `2026-06-15` 的关键表覆盖，不打印 DSN。
- [ ] 实现 SQL 和 row mapping。
- [ ] 验证缺 calc_version 时 fail fast。

### Task 2: 252 交易日窗口和 prepared cache

- [ ] 写 failing 测试：`screen_window()` 使用最近 252 个交易日，而不是自然三年。
- [ ] 写 failing 测试：prepared metadata 记录 DB-native source、window trading days、calc_versions。
- [ ] bump `PREPARED_CACHE_SCHEMA_VERSION`。
- [ ] 实现旧 cache 失效和新 metadata。

### Task 3: EOD prepare 路径瘦身

- [ ] 写 failing 测试：`PreparedRow.k/d/j` 来自 DB KDJ，不调用本地 KDJ。
- [ ] 写 failing 测试：`PreparedRow.dif/dea/macd_hist` 来自 DB daily as-of。
- [ ] 写 failing 测试：`ma25/ma144` 来自 rolling 表。
- [ ] 保留本地 `st_l/lt_r/zx`、B2/B3 信号序列和 MACD 状态机计算。
- [ ] 添加阶段耗时日志。

### Task 4: 盘中 period-state 推演

- [ ] 写 failing 测试：live qfq price 使用 `stock_stk_factor_pro.close_qfq` 口径转换。
- [ ] 写 failing 测试：daily/weekly/monthly live MACD 从 `stock_period_indicator_state` 递推。
- [ ] 写 failing 测试：禁止用昨天 as-of 推今天。
- [ ] 写 failing 测试：rolling/left-peak 盘中使用 previous EOD 并写 diagnostics。
- [ ] 实现 intraday DB-native prepared 路径。

### Task 5: THS 板块因子

- [ ] 写 failing 测试：允许 current `index_ths_member` 关联历史日期，并记录口径。
- [ ] 写 failing 测试：多板块股票只输出一行。
- [ ] 实现主板块选择：rank 升序、net_amount 降序、pct_change 降序、ts_code 稳定排序。
- [ ] 实现聚合板块特征：板块数量、最佳板块、平均板块、相对板块表现。

### Task 6: 新训练因子注册

- [ ] 写 failing Rust 测试：factor artifact 输出 DB-native 因子族。
- [ ] 写 failing Rust 测试：特殊结构因子族包含箱体、MACD 状态机、异常量、K 线、左峰。
- [ ] 实现新 factor profile，不保留旧 schema 兼容约束。
- [ ] 写 Python failing 测试：dataset schema 注册新字段族。
- [ ] 实现 Python schema 和 coverage 门禁。

### Task 7: 文档和验证

- [ ] 更新 `docs/architecture.md` 的数据流程图，使用 Mermaid。
- [ ] 更新 `docs/model.md` 的训练因子契约。
- [ ] 更新 `docs/workflow.md` 的 EOD/盘中流程。
- [ ] 增加性能日志样例和覆盖缺失排查说明。
- [ ] 跑 Rust 相关测试、Python dataset/schema 测试。

---

## Open Follow-ups

- 是否将 `st_l`、`lt_r/zxdkx`、MACD 状态机进一步下沉到 `stock-cache` 预计算。
- 是否让 `stock-cache` 增加历史 THS 成分快照，减少历史训练偏差。
- 是否在 `stock-cache` 增加 `amount_sum_43d` 或其他流动性预计算，替代旧 `turnover_n` 口径。
- 是否实现盘中 rolling/left-peak live 推演。

---

## 实现启动 Prompt

```text
你在 /home/tiger/Documents/agents/stock-select 工作区实现 docs/superpowers/plans/2026-06-28-stock-cache-db-native-screening.md。

约束：
- 先运行 git status --short --branch，不能覆盖用户未提交改动。
- 严格小步 TDD：先写 failing test，再实现，再验证。
- 文档/状态说明使用中文。
- 不打印 .env、完整 DSN 或 token。
- 使用用户提供的本地 POSTGRES_DSN 环境变量连接 stock-cache 测试库；不要把 DSN 写入代码或文档。
- 测试库已整理 2026-06-01 到 2026-06-15，并有约三年 warmup。首个 EOD 验证日期建议 2026-06-15。

当前目标：先完成 Task 1：DB-native loader 契约。

实施顺序：
1. 阅读计划文档、stock-cache docs/data-usage-guide.md、stock-cache docs/calc-version-v1.md，以及本仓库 src/db.rs、src/screening.rs、src/model.rs、tests/cli_screen.rs、tests/screening.rs。
2. 写最小 failing Rust 测试，覆盖 DB-native row 映射：qfq OHLC、Tushare KDJ、daily/weekly/monthly MACD hist_x2/2、rolling、left-peak。
3. 增加只读数据库覆盖探测函数或测试辅助，针对 2026-06-15 验证关键表和 calc_version 行数；测试/日志不得输出 DSN。
4. 实现 DB-native loader 的第一版 SQL 和 row mapping，先不改完整筛选主路径。
5. 跑相关 cargo test，给出失败/通过情况和下一步建议。

不要开始 Task 2 之后的改造，除非 Task 1 已完成并验证。
```
