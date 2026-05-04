# 环境分析改为三维累计评分设计

## 目标

把当前市场环境分析从“单一维度状态触发”改为“箱体 / 趋势 / MACD 三维累计评分”，避免 `MACD` 单维度直接把环境打成 `weak`。

本次改版的目标是：

- 不再允许单一 `MACD` 状态直接决定最终 `strong / neutral / weak`
- 保留现有三维底层评分函数，减少改动范围
- 用双指数累计总分作为正式环境状态来源
- 同时输出旧规则结果与多数表决结果，便于比较区间变化
- 用你已经确认的关键样本验证新口径：
  - `2026-01-20 ~ 2026-01-22` 倾向 `neutral`
  - `2026-01-30 ~ 2026-02-03` 倾向 `weak`
  - `2026-02-05 ~ 2026-03-02` 倾向 `neutral`

## 当前问题

当前实现的问题不在三维打分本身，而在后续状态合成逻辑：

1. `_classify_index_environment()` 直接把 `M7_uptrend_exhausting`、`M8_above_water_dead_cross`、`M9_pullback` 放进弱势 `MACD` 集合。
2. `_combine_environment_state()` 再基于单指数的 `weak`/`strong` 提示直接合成双指数原始状态。
3. `_smooth_environment_states()` 只负责平滑，不会修正上游的单维误判。

结果是：

- `M7` 这种“上升趋势中的衰竭”会被直接打成 `weak`
- `M9` 这种“回撤中”也会在趋势仍强、箱体仍有机会时被直接打成 `weak`
- 结构上更像“高位震荡/修复中”的阶段被压成整段 `weak`

这和当前需求冲突：环境状态应该由三个维度共同决定，而不是由 `MACD` 一票否决。

## 范围

本次只改环境分析层，不改选股或 review 的个股评分逻辑。

### In Scope

- 调整 `market_environment.py` 的状态合成逻辑
- 保留现有 `_box_volume_component()`、`_trend_component()`、`_macd_component()` 的分值产出
- 新增“累计总分映射环境状态”的正式判定路径
- 保留“旧规则路径”和“多数表决路径”作为诊断输出
- 增加对应测试
- 生成 `2026-01-01 ~ 2026-04-30` 的三套结果对照

### Out Of Scope

- 调整 `b1` / `b2` / `dribull` / `hcr` 的个股 review 评分函数
- 修改环境 profile 权重
- 修改数据库 schema
- 重构环境历史存储格式
- 解决 CLI 当前读取 `index_daily_market` 与本机实际 `daily_index` 表名不一致的问题

## 已确认规则

用户已确认本次改版遵循以下边界：

1. 最终环境状态以三维累计总分为主，不以单一维度直接判断。
2. `M7` 不再单独触发 `weak`。
3. `M8` 只有叠加 `S6+` 或箱体 `risk` 时，才把该指数压入弱侧。
4. `M9` 只有叠加 `S6+` 或箱体 `risk` 时，才把该指数压入弱侧。
5. `weak -> neutral` 的恢复不额外加主观提前规则，允许 `2026-02-04` 仍保留 `weak`，从 `2026-02-05` 再回 `neutral`。
6. 展示结果时同时给出：
   - 新累计评分结果
   - 当前旧规则结果
   - 多数表决诊断结果

## 设计原则

- 保留现有三维打分数值，优先调整“如何用这些分数得到状态”
- 正式状态来源只能有一套，诊断输出可以有多套
- 新逻辑先追求可解释，再追求复杂性
- 尽量不要在状态机后面再加太多例外规则
- 样本验证要直接覆盖用户指定区间，而不是只看单日

## 新架构

### Layer 1: 保留三维底层评分

每个指数继续输出：

- `box_volume.score`
- `trend.score`
- `macd.score`

单指数总分保持不变：

```text
index_total = box_score + trend_score + macd_score
```

双指数总分为：

```text
combined_total = sse_total + cn2000_total
```

### Layer 2: 新正式状态路径

新增一条正式判定路径：

```text
combined_total >= strong_threshold -> strong
combined_total <= weak_threshold -> weak
otherwise -> neutral
```

第一版阈值采用：

- `strong_threshold = 10.0`
- `weak_threshold = -4.0`

这组阈值的出发点：

- `2026-01-20`：`4 + 4 = 8`，应更接近 `neutral`
- `2026-01-30`：`-5 + -5 = -10`，应明确 `weak`
- `2026-02-05`：`2 + 2 = 4`，应回到 `neutral`
- `2026-02-27`：`9.5 + 9.5 = 19`，应明确 `strong`

第一版实现不引入单日硬触发。是否保留“强弱切换必须经过 neutral”的平滑状态机，在实现阶段以测试结果决定，但默认保留一层轻量平滑，避免日间抖动过大。

### Layer 3: 旧规则与多数表决仅做诊断

除正式状态外，再同时产出两套非正式结果：

1. `current_rule_based`
   - 完全复用当前逻辑，作为回归对照
2. `vote_based_diagnostic`
   - 先把 `box / trend / macd` 各自映射到 `strong / neutral / weak`
   - 再按多数表决给出诊断状态

这两套结果不影响正式环境状态，只用于分析和输出。

## 单维映射调整

虽然正式状态不再由单维直接决定，但诊断和解释仍需要单维映射。

### MACD 诊断映射

当前 `MACD` 状态在诊断层按以下规则解释：

- `M3_underwater_golden_cross`、`M12_primary_advance`：偏强
- `M1_deep_pullback`、`M2_bottom_divergence_setup`、`M4_repair_extension`、`M6_top_divergence_setup`、`M11_repairing`、`Mx_mixed`：中性
- `M7_uptrend_exhausting`：中性，不单独判弱
- `M8_above_water_dead_cross`：只有叠加 `trend in S6+` 或 `box_zone == risk` 才解释为弱，否则中性
- `M9_pullback`：只有叠加 `trend in S6+` 或 `box_zone == risk` 才解释为弱，否则中性

这里的 `S6+` 指：

- `S6_strong_to_weak_initial`
- `S7_strong_to_weak_accelerating`
- `S8_fast_weakening`
- `S9_risk_increasing`
- `S10_weak`

### Trend 诊断映射

- `S4`、`S5`：偏强
- `S1`、`S2`、`S3`、`Sx`：中性
- `S6`、`S7`、`S8`、`S9`、`S10`：偏弱

### Box 诊断映射

- `score > 0` 或 `zone == opportunity`：偏强/中性，由多数表决细节决定
- `score < 0` 或 `zone == risk`：偏弱/中性，由多数表决细节决定

多数表决只是辅助展示，不要求完全等同于正式评分结果。

## 对外输出

### `evaluate_market_environment()` 返回值

正式 `state` 改为来自累计总分路径。

同时新增诊断字段：

- `score_based_state`
- `rule_based_state`
- `vote_based_state`
- `score_based_total`
- `score_thresholds`

其中：

- `state` 与 `score_based_state` 保持一致
- `raw_state` 保留为兼容字段，但语义改成“正式路径平滑前的 score-based raw state”

### 研究输出

为这次重算额外产出一份对照表，至少包含：

- 日期
- `combined_total`
- `score_based_state`
- `current_rule_based_state`
- `vote_based_state`
- SSE / CN2000 各自三维分数
- SSE / CN2000 各自三维诊断状态

## 测试策略

新增或修改测试时，重点覆盖以下行为：

1. `M7` 不再单独让单指数解释为 `weak`
2. `M8` + `S5` + `opportunity` 不应直接解释为 `weak`
3. `M8` + `S6` 或 `risk` 应能解释为 `weak`
4. `M9` + `S5` + `opportunity` 不应直接解释为 `weak`
5. `M9` + `S6` 或 `risk` 应能解释为 `weak`
6. 累计总分阈值能把关键样本映射到预期区间
7. 旧规则结果作为对照保持不变
8. 新增诊断字段不会破坏现有 CLI/历史调用

## 实施步骤

1. 先补测试，锁定新口径与关键样本。
2. 提炼新的 score-based 状态映射函数。
3. 把旧规则逻辑改为诊断函数，避免直接删除。
4. 更新 `evaluate_market_environment()` 输出结构。
5. 跑 `2026-01-01 ~ 2026-04-30` 重算，导出三套结果。
6. 如阈值与样本不匹配，只允许微调阈值，不扩大改动范围。

## 风险

1. 只用总分阈值可能让某些极端结构被“均值化”，出现该弱不弱的问题。
2. 现有平滑状态机是围绕旧规则设计的，套到新 score-based raw state 上可能出现新的边界抖动。
3. CLI 当前数据库读取的是 `index_daily_market`，本机实库是 `daily_index`，本次研究重算仍需单独处理数据入口。

## 成功标准

满足以下条件即可认为本次改版有效：

- `2026-01-20 ~ 2026-01-22` 不再整段被压成 `weak`
- `2026-01-30 ~ 2026-02-03` 仍能明确落在 `weak`
- `2026-02-05 ~ 2026-03-02` 能回到 `neutral`
- 环境状态解释能直接落到“三维分数累计”而不是“某个 MACD 名称直接定性”
- 输出中能同时看到新旧两套口径与多数表决诊断
