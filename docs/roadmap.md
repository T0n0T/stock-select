# Roadmap

## 概述

当前项目已落地 b2 model-first 主路径（screen → factor → LightGBM rank → display），以 Rust CLI 为核心。以下为下一步工作计划。

---

## 1. 补充因子系统缺失指标

### 背景

当前因子库（`src/factors/`）使用 Rust 从原始行情数据从头计算技术指标。但数据库 `daily_indicators` 表中已经预计算了大量指标，存储在 `extra_factors_jsonb` 字段和各指标列中，目前未接入因子系统。

### 缺失的 DB 指标

| 指标 | DB 位置 | 当前状态 |
|------|---------|---------|
| **KDJ** | `daily_indicators.k` / `d` / `j` 列 | screening 阶段使用过，但进入因子系统时被清零（`semantic.rs:236`） |
| **OBV** | `daily_indicators.extra_factors_jsonb` | 完全未读取 |
| **BIAS(5/10/20/60)** | `daily_indicators.extra_factors_jsonb` | 无对应因子（当前有等价计算 `close_to_ma25_pct` 等，但非 DB 原生 BIAS） |
| 其他 `extra_factors_jsonb` 中指标 | `daily_indicators.extra_factors_jsonb` | 需盘点后接入 |

### 任务

- [ ] `src/factors/registry.rs` 中从 `PreparedRow` / `FactorInputRow` 传递 KDJ 值到因子输出
- [ ] 新建 `src/factors/extra.rs` 或扩展 `volume.rs`，从 `PreparedRow` 引入 `extra_factors` JSONB 数据，解析 OBV、BIAS 等因子
- [ ] 更新 `build_rank_dataset.py` 确保训练集包含新增因子
- [ ] 更新 `model_metadata.json` 的 `numeric_columns` 列表
- [ ] 回归验证：新加入因子后模型排序效果不劣化

---

## 2. B2 策略与旧 CLI 对齐

### 背景

旧 CLI（`stock-select.v2`）的 `strategies/b2.rs` 实现了更完整的信号体系，新 CLI 仅实现了 B2 基本信号。需要对齐差异。

### 差异项

| 差异 | 旧 CLI | 新 CLI | 优先级 |
|------|--------|--------|--------|
| **涨跌幅限制区分** | 688/300 股票振幅上限 12%，普通 8% | 统一未区分 | 高 |
| **J 周期计数** | `count_dynamic(raw_b2, up_days+1)` 向量化 | `raw_b2_count_in_current_j_up_cycle` 手动回扫 | 低（逻辑等价） |
| **EMA 实现** | 标准 EMA（`indicators::ema`） | 自实现带 NaN 间隔处理的自适应衰减 | 低（功能更完善，但需验证一致性） |

### 任务

- [ ] `src/strategies/b2.rs` 增加 `amp_limit` 参数：`code.starts_with("688") || code.starts_with("300")` → 12%，否则 8%
- [ ] 回归验证：新旧策略在同日期候选池中的一致性

---

## 3. B3 独立筛选算法

### 背景

旧 CLI 中的 B3/B3+ 信号定义为 B2 次日的缩量震荡形态。新 CLI 将 B3 设计为**独立的筛选算法**（`src/strategies/b3.rs`），不再依赖 B2 前置信号，直接基于技术形态筛选。

### 旧 CLI B3 信号逻辑（参考）

B3 形态特征：

- 缩量震荡：振幅 < 5.05%，涨跌幅绝对值 < 5.05%
- 成交量 ≤ 前日 90%（B3）或 ≤ 52%（B3+）
- J 值继续向上
- 趋势 OK（`tr_ok`）、高于长期参考（`above_lt`）
- 区分 688/300（振幅上限 12%）vs 普通（8%）

### 任务

- [ ] 设计 B3 独立筛选条件（独立于 B2 信号触发）
- [ ] 新建 `src/strategies/b3.rs`，实现独立筛选逻辑
- [ ] 在 `src/screening.rs` 的策略调度中注册 B3
- [ ] `Candidate` 信号字段支持 B3 / B3+
- [ ] B3+ 作为 B3 的增强子集（强缩量 + 收涨）
- [ ] 统计计数：`selected_b3`、`selected_b3_plus`
- [ ] 回归验证：B3 独立选股与旧 CLI 同日期结果对比

---

## 4. 后续展望

### 短期

- [ ] `backfill_run.py` 合并到 `scripts/model_maintenance.sh` 统一入口
- [ ] run 命令支持 `--skip-factors` 跳过因子重算（增量模式）
- [ ] 补充 `chart` 命令的批量模式（多日期批量出图）
- [ ] 补充 LLM 复盘结果统计（`review-list` 增加 `--stats` 汇总模式）

### 中期

- [ ] 多方法并行训练框架（当前仅 b2，扩展 dribull 等）
- [ ] 盘中模式对接非 Tushare 数据源
- [ ] 自动化回溯测试 pipeline（从 dataset → train → promote → 回测 全自动）

### 远期

- [ ] 因子自动筛选（基于 feature importance + 相关系数）
- [ ] 集成 xgboost / CatBoost 作为备选排序模型
- [ ] 实时推单通道（websocket + 企业微信/钉钉推送）
