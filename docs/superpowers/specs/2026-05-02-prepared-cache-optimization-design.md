# Prepared Cache 优化设计（2026-05-02）

## 1. 背景与问题

当前 `stock-select` 的 prepared cache 使用 `pickle(dict[str, DataFrame])` 作为落盘格式。

真实测量结果已经说明两个问题：

1. 旧格式单文件很大。
   - shared cache 约 `316MB`
   - hcr cache 约 `149MB`
   - prepared 目录总占用约 `27G`
2. 主瓶颈不是磁盘读取，而是 Python 对象重建。
   - `read_bytes()` 约 `0.19s`
   - `pickle.loads()` 约 `4.19s`

在本轮早期实验里，已经验证过另一件事：

- 仅仅把磁盘格式改成 `Feather`
- 但读取后仍然把单表重新拆成 `dict[str, DataFrame]`

不会得到性能收益，反而可能更慢。

因此真正的问题不是“是否换格式”，而是：

> 是否继续维持 `dict[str, DataFrame]` 作为 prepared cache 的运行时表示。

本轮结论是：**不再维持。**

## 2. 目标与边界

本轮目标：

1. prepared cache 的唯一磁盘格式改为 `Feather + meta.json`
2. prepared cache 的唯一运行时表示改为**单个长表 DataFrame**
3. 不再维护 `.pkl` 兼容逻辑
4. 不再维护 `dict[str, DataFrame]` 适配层
5. `screen/chart/review/intraday` 主链路全部直接消费单表
6. 优先追求“性能最好 + 实现最简”，不保留兼容包袱

本轮不做：

- 不调整选股逻辑
- 不调整评分逻辑
- 不把 prepared cache 迁入数据库
- 不引入 Rust/C++ 等跨语言实现
- 不做 method-specific addon cache 分层

## 3. 方案选择

### 3.1 继续保留 pickle

不选。

原因：

- 不能解决 Python 对象反序列化成本
- 结构本身就是瓶颈

### 3.2 Feather + 兼容 `dict[str, DataFrame]`

不选。

原因：

- 已经实测证明：读取后再拆成 5515 个 DataFrame，会吃掉 Feather 的优势
- 会继续保留双重模型：
  - 单表
  - symbol map
- 复杂度高，但收益不足

### 3.3 Feather + 单表唯一模型

选这个。

原因：

- 磁盘格式简单
- 运行时模型简单
- 最符合“性能最好 + 实现最简”
- 后续性能优化方向也最清晰：
  - 先按 `ts_code` 子集过滤
  - 再分组

## 4. 最终架构

prepared cache 采用双文件结构：

- `runtime/prepared/<base_key>.feather`
- `runtime/prepared/<base_key>.meta.json`

示例：

- EOD shared：`2026-04-30.feather` + `2026-04-30.meta.json`
- EOD hcr：`2026-04-30.hcr.feather` + `2026-04-30.hcr.meta.json`
- intraday shared：`2026-04-30.intraday.feather` + `2026-04-30.intraday.meta.json`

### 4.1 唯一运行时表示

prepared cache 在内存中的唯一表示为：

- 一个长表 `pd.DataFrame`

不再存在：

- `dict[str, DataFrame]`
- symbol map adapter
- `.pkl` fallback

### 4.2 单表 schema 约束

prepared 单表至少必须包含：

- `ts_code`
- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `vol` 或统一后的 `volume`
- 各方法当前需要的派生列

硬性约束：

- 必须按 `ts_code, trade_date` 排序
- `trade_date` 在内存里统一为 datetime
- `ts_code` 为稳定字符串列
- 列名不得在不同方法间漂移出多个别名

### 4.3 metadata 最小集

metadata json 至少包含：

- `method`
- `mode`
- `pick_date`
- `start_date`
- `end_date`
- `screen_version`
- `b1_config`
- `turnover_window`
- `weekly_ma_periods`
- `max_vol_lookback`

可选补充：

- `row_count`
- `symbol_count`
- `columns`
- `previous_trade_date`（intraday）

## 5. prepare 生产端设计

### 5.1 `_prepare_screen_data(...)`

当前返回 `dict[str, DataFrame]`。

本轮改为直接返回：

- 单个 prepared 长表 `pd.DataFrame`

实现方式：

- 保持现有计算逻辑
- 仍按 `ts_code` 分组逐票计算
- 但最终产出改为 `concat` 后的单表

### 5.2 `_prepare_hcr_screen_data(...)`

同样改为返回单表。

## 6. 读写层设计

### 6.1 写入

新增或保留单一写入入口：

- `_write_prepared_cache_v2(...)`

职责：

- 接收单表 prepared
- 写 `.feather`
- 写 `.meta.json`

不再负责：

- 接收 `dict[str, DataFrame]`
- 写 `.pkl`

### 6.2 读取

prepared 读取入口改为只读 v2：

- `_load_prepared_cache_v2(...)`

职责：

- 读 `.meta.json`
- 做 metadata 校验
- 读 `.feather`
- 返回统一 payload

不再保留：

- `_load_prepared_cache(...)` 的 pickle fallback 语义

如保留函数名，也只保留 v2 实现，不再做旧格式兼容。

## 7. 策略层设计

以下函数全部改为直接接收单表：

- `run_b1_screen_with_stats(...)`
- `run_b2_screen_with_stats(...)`
- `run_dribull_screen_with_stats(...)`
- `run_hcr_screen_with_stats(...)`

新模式：

1. 先对单表按 `ts_code` 做 pool/filter 缩小范围
2. 再在函数内部按 `ts_code` 分组
3. 对每组执行原有逐票判断逻辑

这一步是本轮最关键的性能改造点。

## 8. 主链路消费方式

### 8.1 screen

- prepared 只以单表形式传递
- pool_source 逻辑改成先过滤单表
- strategy 直接吃单表

### 8.2 chart

单票 chart 不再从 symbol map 取值，而是：

- `prepared[prepared["ts_code"] == code]`

### 8.3 review

单票 review 同样按 `ts_code == code` 过滤。

### 8.4 intraday

intraday chart/review/screen 都只操作单表。

### 8.5 analyze-symbol

这条链路本身更像“单票内存内 prepare”，它不依赖 runtime prepared cache。

本轮不强行让它绕 prepared 文件层。

## 9. 研究脚本策略

### 9.1 大样本研究脚本

例如：

- `review_top3_stats.py`
- `score_tuning_diagnostics.py`

如果需要用 prepared cache，就直接读取单表 Feather。

### 9.2 小样本研究

如果只是少量 code 的 forward return 或少量样本复盘，优先直接查 DB，而不是全量读 prepared。

## 10. 资源占用与性能预估

本轮新的预期，不再基于“Feather 后再拆 dict”的旧实验，而是基于“单表直用”的新目标。

### 10.1 文件体积

预估：

- shared cache：`120MB ~ 240MB`
- hcr cache：`60MB ~ 120MB`
- prepared 目录：`10G ~ 18G`

### 10.2 读取性能

目标：

- shared cache 读取明显优于当前 `4.37s`

期望区间：

- `0.5s ~ 1.5s`

前提是：读取后不再拆成 5515 个 DataFrame。

### 10.3 写入性能

目标：

- 不慢于当前
- 最好更快

### 10.4 内存

如果不再物化 symbol map，内存峰值应明显优于“单表 + 5515 个子表”的模式。

## 11. 测试策略

### 11.1 schema 测试

验证：

- 单表列齐全
- 排序稳定
- dtype 符合预期

### 11.2 读写 round-trip

验证：

- 写 Feather + meta
- 再读回
- 单表值一致
- metadata 一致

### 11.3 主链路最小回归

至少覆盖：

- screen EOD
- screen intraday
- chart intraday
- review intraday
- review_top3_stats
- score_tuning_diagnostics

### 11.4 不支持旧格式

本轮不再把“旧 `.pkl` 兼容”当成功标准。

可以允许旧格式测试删除或改写。

## 12. Benchmark 方案

必须做真实 benchmark，至少比较：

1. 单文件体积
2. Feather 读耗时
3. prepared 写耗时
4. `screen --method b2 --pick-date 2026-04-30 --recompute` 的端到端 wall time

重点是：

- 看单表直用后，读取是否真正变快
- 看 screen 主链路整体是否改善

## 13. 回滚策略

本轮不追求兼容回滚。

如果失败，回滚方式就是代码回滚，而不是 runtime 双格式并存。

这符合本轮目标：

- 实现最简
- 不保留兼容包袱

## 14. 实施顺序

本轮建议按 5 个阶段实现：

1. 定义最终单表 schema 与 metadata
2. 改 prepare 生产端返回单表
3. 改 Feather 读写层，只保留 v2
4. 改策略层与 screen 主链路为单表消费
5. 改 chart/review/intraday/研究脚本，并做 benchmark

## 15. 验收标准

完成标准：

1. prepared 的唯一磁盘格式是 Feather
2. prepared 的唯一运行时表示是单表 DataFrame
3. 主链路不再依赖 `dict[str, DataFrame]`
4. `screen/chart/review/intraday/研究脚本` 都能运行
5. 真实 benchmark 显示：单表 Feather 路径比当前 pickle 路径更优，或至少在主链路上更优
