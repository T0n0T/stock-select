# B1 previous_abnormal_move 回测驱动重构设计

## Goal

把 `b1` review 中的 `previous_abnormal_move` 从当前复用 `b2` 异常波动事件逻辑的实现，改成一个 `b1` 专用、由多日期窗口 5 日涨幅回测驱动校准的新特征。

这次改造的目标不是让该小分精确预测短线收益，而是修正其方向性错误：

- 不再把 `2026-04-13 ~ 2026-04-24` 这类单一窗口里的负向现象继续固化为高分奖励
- 在多个日期窗口上，`previous_abnormal_move` 的分档表现不再呈系统性负相关
- `5` 分档不能再次成为明显弱于 `3` / `4` 分档的状态

## Scope

本次设计只改 `b1` baseline review 中 `previous_abnormal_move` 的定义与评分来源。

包含：

- 为 `b1` 定义独立于 `b2` 的新特征语义
- 基于 `pick_date` 之前历史构建少量可解释状态
- 用多日期窗口 5 日涨幅表现校准状态到 `1~5` 分的映射
- 更新 `b1` reviewer 单元测试
- 新增研究文档，记录回测样本、状态表现和最终映射依据

不包含：

- 修改 `b1 screen` 初筛逻辑
- 修改 review JSON schema 字段名
- 同步重写 `b1` 其它小分
- 同步调整 `B1_BASELINE_SCORE_WEIGHTS`
- 给 `b2` / `dribull` 引入同样逻辑

## Current Problem

当前 `review_b1_symbol_history()` 直接复用 `b2` 的 `_score_b2_previous_abnormal_move()`。

这有两个问题：

1. **策略语义不一致**

`b2` 的该函数关注“异常波动日后的回踩事件是否仍保持高位承接”，更偏事件驱动与异动后修复。`b1` 则更关心较早阶段的结构性低吸、关键承接位是否守住、回撤是否温和。两者不是同一问题。

2. **回测方向错误已经被显式观察到**

现有研究显示，当前实现下 `previous_abnormal_move` 在样本窗口中呈负相关，尤其高分档并不带来更好的短线收益表现。继续复用 `b2` 逻辑，只会把 `b2` 的形态偏好错误地转移到 `b1`。

## Design Principles

新设计遵循以下原则：

- **`b1` 语义优先**：特征表达的是“前高后承接质量”，而不是“异常事件后的价格修复”。
- **回测驱动而非主观打分**：先定义少量观测状态，再用多窗口 5 日收益结果决定分数映射。
- **只用历史数据**：任何状态判断只能依赖 `pick_date` 当日及之前的日线数据。
- **解释性优先于连续拟合**：不做高自由度连续分数拟合，避免在有限样本上过拟合。
- **不稳定状态宁可中性**：跨窗口表现不稳定的状态降为 `3` 分，不勉强给高分。

## Feature Semantics

字段名 `previous_abnormal_move` 保持不变，以避免打破现有 review schema 和下游展示，但其业务语义改为：

`b1` 候选在入选日前是否经历了一个对后续 5 日表现更友好的“前高后温和消化并保持承接”的过程。

这个特征不再尝试寻找单个“异常放量日”。它关注的是一个短窗口内的结构状态，核心是：

- 先前是否出现过足够明确的推动段
- 推动后回撤是否温和而未破坏结构
- 关键承接位是否守住
- 回撤过程量能是否收敛而非恶化

## Observable Inputs

新特征先提取 4 个低自由度、可解释的观测量。

### 1. push_strength

识别 `pick_date` 之前 `25` 个交易日内是否出现过可视为“推动段”的局部上攻。

只保留 3 个离散值：

- `weak`
- `normal`
- `strong`

推动段判断可以综合使用：

- 区间涨幅
- 推动期相对量能放大程度
- 推动后局部高点是否明确

目标不是识别所有上涨，而是避免把“根本没有前高”的样本误判为优质承接。

### 2. pullback_depth

衡量从局部推动高点到 `pick_date` 当前价格的回撤幅度。

只保留 3 个离散值：

- `shallow`
- `moderate`
- `deep`

该观测量只反映深浅，不独立判定好坏。对 `b1` 来说，过浅可能已经偏右侧，过深可能已经损坏，通常中浅回撤更值得关注。

### 3. support_quality

评估当前及回撤过程中对 `b1` 既有承接位的保持情况，重点观察：

- `ma25`
- `zxdkx`

只保留 3 个离散值：

- `held`
- `mixed`
- `broken`

这使新特征与 `b1` 原本的趋势结构语言保持一致，避免另造一套无关支撑体系。

### 4. volume_contraction

比较推动段峰值量能与回撤到 `pick_date` 附近的量能消化情况。

只保留 3 个离散值：

- `contracted`
- `neutral`
- `expanded`

这里不要求绝对缩量，只要求回撤量能不呈现明显恶化。若回撤中反而持续放量，应视为风险而非优势。

## State Compression

不直接对上述 4 个观测量做线性加总。

原因：

- 连续拟合容易在有限样本中放大噪音
- 状态空间过大时，很多组合样本数不足
- `b1` 更适合少量结构语言，而不是“每项加一点”的分数幻觉

因此先把观测量压缩成 `7` 类固定的 `b1` 结构状态。

状态类固定如下：

- `constructive_reset`
  - 有明确推动段
  - 回撤适中
  - 承接位守住
  - 量能收敛

- `tight_high_reset`
  - 推动较强
  - 回撤较浅
  - 承接位仍稳
  - 量能正常或略收敛

- `neutral_digest`
  - 有推动段
  - 但回撤深浅、支撑、量能没有形成明确优劣结论

- `overdeep_pullback`
  - 回撤偏深
  - 但承接位未完全损坏

- `support_breakdown`
  - 承接位明显失守

- `failed_distribution`
  - 推动后回撤放量恶化
  - 且结构走坏

- `no_prior_push`
  - 近窗口内没有足够明确的前期推动段

实现时不要求严格保留这些名字，但必须保持“少量、可解释、可回测”的状态设计。

## Backtest-Driven Calibration

### Objective

校准目标不是让状态在单一日期段上收益最高，而是让分档方向在多个日期窗口上不再系统性反向。

### Sample Definition

样本单位使用 `candidate occurrence`：

- 同一股票在不同 `pick_date` 入选，视为不同样本
- `5` 日涨幅定义为第 `5` 个后续交易日收盘价 / 入选日收盘价 - `1`

研究口径应延续当前仓库已有做法：

- 使用 prepared cache 中完整历史数据
- 所有 review 计算都按 `<= pick_date` 截断
- 不为每个日期单独重建整套重型缓存

### Windowing

必须使用多个日期窗口，而不是只验证 `2026-04-13 ~ 2026-04-24` 这一个样本段。

研究必须至少包含 `4` 个互不重叠的日期窗口，每个窗口固定为 `10` 个连续交易日的 `pick_date` 样本段，并且应覆盖不同市场节奏阶段。

每个窗口都独立统计状态表现。如果可用历史不足以支持 `4` 个窗口，则本次研究应显式失败，而不是缩减成单窗口或双窗口验证。

### Per-State Metrics

每个状态在每个窗口至少统计：

- 样本数
- 平均 `5` 日涨幅
- 中位 `5` 日涨幅
- 胜率

在汇总层面，再统计：

- 各状态跨窗口的平均表现
- 各状态相对排序的一致性
- 是否存在单一极端窗口驱动的假优势

### Mapping States To Scores

状态到 `1~5` 分的映射必须由上述结果驱动，不允许先主观指定“哪个状态天然值 5 分”。

状态到分数的映射按以下固定原则执行：

- 跨窗口稳定最优的状态映射到 `5`
- 跨窗口稳定偏优的状态映射到 `4`
- 表现中性或不稳定的状态映射到 `3`
- 跨窗口稳定偏弱的状态映射到 `2`
- 稳定最弱、且具有明显破坏特征的状态映射到 `1`

特别约束：

- 如果高分候选状态在不同窗口间显著摇摆，则降为 `3`
- 不允许把样本数极小但单窗口均值很高的状态直接映射为 `5`
- 不允许把明确呈负向分层的状态保留在 `4/5`

## Implementation Outline

### 1. Replace b1 abnormal-move scoring source

在 `src/stock_select/reviewers/b1.py` 中新增 `b1` 专用评分函数，替代当前对 `_score_b2_previous_abnormal_move()` 的调用。

实现固定拆成两层：

- `_classify_b1_previous_abnormal_move_state(...)`
  - 提取观测量并输出离散状态
- `_score_b1_previous_abnormal_move(...)`
  - 负责把状态映射到 `1~5`

`review_b1_symbol_history()` 继续输出 `previous_abnormal_move` 字段，但值来自新函数。

### 2. Keep schema stable

以下对外结构保持不变：

- review JSON 中字段名仍为 `previous_abnormal_move`
- `total_score` 的计算方式和字段集合不变
- `html_export` 和 `review-merge` 不需要 schema 适配

### 3. Preserve pick-date truncation safety

新函数必须只读取 `pick_date` 及之前的日线。任何为研究脚本或状态识别引入的辅助逻辑都不能依赖未来数据。

## Testing Plan

### Unit Tests

更新 `tests/test_reviewers_b1.py`：

- 删除绑定旧语义的测试：
  - `b1` 复用 `b2` event logic 的断言不再成立

- 新增 `b1` 专用状态测试：
  - 温和回撤、守住承接位、量能收敛时给高分
  - 推动后浅回撤但仍稳定时给偏高分
  - 回撤过深但未彻底损坏时给中性分
  - 跌破承接位且放量恶化时给低分
  - 没有前期推动段时不得给高分

- 新增历史截断测试：
  - 同一段历史在追加未来行后，`pick_date` 对应 review 结果不变

### Research Artifact

在 `docs/research/` 新增一份 `b1` 回测文档，必须包含：

- 使用的日期窗口
- 样本总数与各窗口样本数
- 各状态类的 `5` 日涨幅统计
- 最终 `1~5` 分映射依据
- 分档表现是否仍存在负相关或高分劣化

这份文档是改造依据，不是可选附录。

## Acceptance Criteria

### Functional

- `b1` review 不再依赖 `_score_b2_previous_abnormal_move()`
- `previous_abnormal_move` 仍按原字段名输出
- `b1` review schema 保持兼容

### Backtest Validation

- 多日期窗口上，`previous_abnormal_move` 分档表现不再呈系统性负相关
- `5` 分档不能再次系统性弱于 `3` / `4` 分档
- 高分状态若不稳定，必须降档处理，而不是保留名义高分

### Engineering

- `tests/test_reviewers_b1.py` 及相关 review 测试通过
- `analyze-symbol --method b1` 仍能复用并解释该字段
- 不引入对 `b2` reviewer 语义的耦合

## Risks And Tradeoffs

- 多窗口样本可能不足以支撑过细分桶，因此状态设计必须克制
- 用离散状态替代连续拟合会牺牲部分表面拟合度，但换来更强可解释性和稳定性
- 保留字段名 `previous_abnormal_move` 会有历史语义残留，但相比直接改 schema，兼容性更高
- 只修正该小分，不同步调权，意味着 `b1 total_score` 仍可能存在其它排序问题；这属于后续独立问题，不在本次范围内

## Implementation Sequence

1. 为 `b1 previous_abnormal_move` 写失败测试，覆盖新语义和历史截断约束。
2. 在 `b1 reviewer` 中实现新状态分类与分数映射。
3. 运行单元测试，确认旧的 `b2` 复用关系已移除且 `b1` review schema 未破坏。
4. 运行多日期窗口研究，记录状态分桶与最终映射依据。
5. 根据研究结果微调状态到分数的映射，但不扩展范围去重写其它因子或总权重。

## Non-Goals

这次设计明确不解决以下问题：

- `b1 total_score` 是否整体适合做 5 日收益排序
- `price_position` 是否也需要回测驱动重构
- `b1` / `b2` / `dribull` 是否应共享统一的结构承接因子
- 是否需要把分数映射从离散值进一步升级为概率或分位输出
