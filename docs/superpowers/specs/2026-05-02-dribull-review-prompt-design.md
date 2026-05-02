# Dribull Review Prompt Design

## 目标

为 `dribull` 新增独立的 LLM review prompt，使其与当前 `dribull` baseline review 的方法语义、权重、判定规则和文案口径保持一致，同时保持最终 `llm_review` JSON schema 不变。

本次设计的直接目标是消除当前 `dribull` 复用 `prompt-b2.md` 带来的语义漂移，避免 baseline review 与 LLM review 在 `PASS/WATCH/FAIL` 结论上长期失配。

## 已确认决策

以下决策在本设计中视为固定前提：

- `dribull` 不再继续复用 `prompt-b2.md`
- 新增独立 `prompt-dribull.md`
- `dribull` 的 LLM review JSON schema 保持不变
- `dribull` 的 review resolver 需要单独指向新 prompt
- `dribull` baseline review 不在本变更中继续改规则，只让 prompt 向现有 baseline 对齐
- skill 文档中关于 `dribull` 仍复用 `b2 reviewer` 的描述需要同步修正

## 范围

本次变更包含：

- 新增 `.agents/skills/stock-select/references/prompt-dribull.md`
- 将 `dribull` 的 resolver prompt 路由改为 `prompt-dribull.md`
- 更新 `stock-select` skill 文档中的 prompt 映射与实现说明
- 增加或更新测试，覆盖 resolver、CLI review task 元数据和 prompt 契约

本次变更不包含：

- 修改 `dribull` deterministic screening 规则
- 修改 `dribull` baseline review 算法或输出 schema
- 为 `dribull` 增加新的 `llm_review` 字段
- 修改 `review-merge`、`normalize_llm_review(...)` 或 merged review schema
- 修改 `b2`、`b1`、`hcr` 的 prompt 语义

## 当前问题

当前仓库中，`dribull` 已经拥有独立 baseline reviewer，但 LLM review 仍复用 `prompt-b2.md`。

这带来四类不一致：

1. 方法目标不一致

- `prompt-b2.md` 把任务定义为判断是否具备 `b2` 方法偏好的波段启动潜力
- `dribull` baseline review 的真实意图更接近强趋势内部回调修复、承接、再起动，而不是 `b2` 的右侧起爆确认

2. 判定规则不一致

- `prompt-b2.md` 只写了固定阈值：`PASS >= 4.0`
- 当前 `dribull` baseline review 已支持“弹性 PASS”：在总分略低于 `4.0` 时，只要高位置、前期异动、MACD 和结构条件足够强，仍可由 `WATCH` 晋级为 `PASS`
- 同时，`dribull` baseline review 还会对名义 `PASS` 做二次收紧：当总分不足 `4.2`、或 `price_position < 4.0`、或 `volume_behavior < 4.0` 时，会回落为 `WATCH`

3. 权重不一致

- `prompt-b2.md` 写的是 `b2` 风格权重
- `dribull` baseline 总分实际走默认权重，而不是 `b2` 专用权重

4. 推理口径不一致

- `prompt-b2.md` 要求 `signal_reasoning` 明确写是否符合 `b2`
- `dribull` 的 review task context 已经写成“是否符合 dribull 候选要求”
- 这使 prompt 主体和 task context 出现同一任务内部的双重口径

## 方案比较

### 方案 A：继续复用 `prompt-b2.md`，在文档中加 `dribull` 条件分支

优点：

- 文件数量更少
- 代码改动更小

缺点：

- `b2` 与 `dribull` 的方法语义继续耦合
- prompt 会变成条件分支文档，可读性和可维护性变差
- 后续如果 `dribull` baseline 再调参，prompt 更容易再次漂移

### 方案 B：新增独立 `prompt-dribull.md`

优点：

- 方法语义单独收束，最清晰
- 可以直接按当前 baseline 规则表达 `dribull` 的弹性 `PASS` 逻辑
- 后续 `dribull` 再调参时只需要维护自己的 prompt

缺点：

- 多一个 prompt 文件
- resolver 和文档需要同步更新

### 选择

采用方案 B。

原因很直接：`dribull` 已经从 reviewer 角度和 `b2` 分叉，继续共用 prompt 只会让“代码已分叉、任务定义未分叉”的问题持续扩大。

## 设计

### 1. 新增独立 `prompt-dribull.md`

新增文件：

- `.agents/skills/stock-select/references/prompt-dribull.md`

该 prompt 继续沿用当前 review 系统的统一 JSON 契约，不新增字段，不改字段名，只调整：

- 任务目标描述
- 方法观察重点
- 各评分维度的解释口径
- 权重说明
- verdict 判定规则
- 示例文案中的方法名与点评语义

### 2. 保持 JSON schema 不变

`dribull` 的 LLM review 输出仍必须保留以下字段：

- `trend_reasoning`
- `position_reasoning`
- `volume_reasoning`
- `abnormal_move_reasoning`
- `macd_reasoning`
- `signal_reasoning`
- `scores.trend_structure`
- `scores.price_position`
- `scores.volume_behavior`
- `scores.previous_abnormal_move`
- `scores.macd_phase`
- `total_score`
- `signal_type`
- `verdict`
- `comment`

这保证：

- `normalize_llm_review(...)` 不需要改动
- `review-merge` 不需要改动
- HTML export 不需要改动
- 既有 LLM review 文件结构不需要迁移

### 3. 调整任务定义为 `dribull` 语义

`prompt-dribull.md` 的任务目标应从“`b2` 方法偏好的波段启动潜力”改为更贴近当前 reviewer 的说法，例如：

- 强趋势内部的回调修复后再起动潜力
- 中期结构未坏前提下的承接和再发力质量
- 是否属于 `dribull` 偏好的可继续跟踪或可放行样本

它不应再把任务核心描述成：

- `b2` 的右侧起爆确认
- 单纯的平台再突破启动
- 明显更偏 `b2` 的“趋势启动池”逻辑

### 4. 明确 `signal_reasoning` 和 `comment` 的方法口径

`prompt-dribull.md` 必须要求：

- `signal_reasoning` 明确写出当前周线/日线 MACD 趋势组合是否符合 `dribull`
- `comment` 压缩表达时应使用 `dribull` 语义，而不是 `b2`

系统提供的三个上下文字段名可以继续保留：

- `weekly_wave_context`
- `daily_wave_context`
- `wave_combo_context`

但 prompt 中应明确说明：

- 这些字段名只是兼容旧 schema 的命名
- 其内容需要按照当前系统给出的 MACD 趋势状态和 `dribull` 候选要求理解

### 5. 权重与 baseline 对齐

`prompt-dribull.md` 中展示给 LLM 的权重说明应与当前 `dribull` baseline 使用的总分口径一致：

- `trend_structure`: `0.18`
- `price_position`: `0.18`
- `volume_behavior`: `0.24`
- `previous_abnormal_move`: `0.20`
- `macd_phase`: `0.20`

这样至少保证 LLM reviewer 在“如何组合分数”的认知上不再被 `b2` 权重误导。

### 6. Verdict 规则与 baseline 对齐

`prompt-dribull.md` 必须显式表达三层规则。

第一层，基础阈值：

- `PASS`: `total_score >= 4.0`
- `WATCH`: `3.2 <= total_score < 4.0`
- `FAIL`: `total_score < 3.2`

第二层，基础否决：

- `volume_behavior = 1` 时必须 `FAIL`
- 如果图形判断明显属于 `distribution_risk`，不应给 `PASS`

第三层，`dribull` 专属 verdict 细化：

- 当样本原始判断为 `WATCH`，但满足高位置弹性通过条件时，可以给 `PASS`
- 当样本原始判断为 `PASS`，但总分不够高，或位置/量价不够强时，应回落到 `WATCH`

这部分不要求 LLM 精确复刻 Python 分支结构，但 prompt 必须把判断意图讲清楚，避免 LLM 继续按“只要 `>=4.0` 就直接 `PASS`”执行。

### 7. `dribull` 专属图形观察重点

`prompt-dribull.md` 的观察重点应从 `b2` 风格改成 `dribull` 风格，核心包括：

- 优先判断它是否是强趋势中的回踩修复，而不是单纯跌深反弹
- 高位置不自动减分到最差，关键看 `MA25`、`zxdq`、中期支撑和承接质量是否还成立
- 量价并非要求绝对完美缩量，但必须避免结构性放量破坏
- 前期异动和承接质量要被当作核心加分项，而不是次要背景
- MACD 趋势上下文仍然重要，但需要服务于 `dribull` 的“修复后再起动”判断，而不是直接套用 `b2` 的启动叙事

### 8. Resolver 路由调整

`src/stock_select/review_resolvers.py` 需要改成：

- `b2` -> `prompt-b2.md`
- `dribull` -> `prompt-dribull.md`

`dribull` 仍继续使用自己的 baseline reviewer：

- `review_dribull_symbol_history(...)`

这次只改 prompt 路由，不改 reviewer 选择逻辑。

### 9. Skill 文档同步

`.agents/skills/stock-select/SKILL.md` 需要同步两类信息：

1. prompt 映射

- `dribull` 使用 `references/prompt-dribull.md`

2. 当前实现说明

- 不再写 `dribull` 复用 `b2 reviewer`
- 改为说明 `dribull` 使用 dedicated reviewer，并使用独立 prompt

### 10. 测试策略

需要增加或更新以下测试。

#### Resolver 测试

- `get_review_resolver("dribull")` 返回的 `prompt_path` 指向 `prompt-dribull.md`
- reviewer 模块仍然是 `stock_select.reviewers.dribull`

#### CLI review 测试

- `review --method dribull` 生成的 `llm_review_tasks.json` 顶层 `prompt_path` 指向 `prompt-dribull.md`
- task 中的 `wave_combo_context` 仍保留 `dribull` 方法名

#### Prompt 契约测试

至少验证 `prompt-dribull.md` 中存在以下关键信息：

- `signal_reasoning` 需要写是否符合 `dribull`
- 权重是 `0.18 / 0.18 / 0.24 / 0.20 / 0.20`
- 存在弹性 `PASS` 规则说明
- 示例 comment 使用 `dribull` 语义，而不是 `b2`

#### 文档一致性测试

如果现有测试已覆盖 skill 中的 prompt 映射，应同步更新断言。

## 风险

1. prompt 与 baseline 仍不可能做到逐行等价

LLM review 本质上仍是图形主观评审，不可能像 Python baseline 一样完全按分支执行。因此本次目标是“规则意图对齐”，而不是“逐分逐点完全相同”。

2. 后续 baseline 再调参时仍有同步成本

新增独立 prompt 之后，这个成本会降低，但不会消失。后续任何 `dribull` verdict 规则变更都应把 prompt 同步视为同一变更的一部分。

3. `wave_*_context` 字段名仍带旧命名

这次不改 schema，因此字段名中的 `wave` 会继续存在。但 prompt 需要明确这些字段现在表达的是 MACD 趋势状态与组合判断，不再要求使用旧的 wave-count 语言。

## 实施结果标准

完成后应满足：

- `dribull` review task 不再引用 `prompt-b2.md`
- `dribull` LLM reviewer 接收到的方法说明、评分权重和 verdict 规则与当前 baseline 口径一致
- 既有 `llm_review` JSON schema、merge 流程和 HTML 展示均不需要改动
- skill 文档与实际运行时路由一致，不再保留“复用 b2 reviewer”的过时描述
