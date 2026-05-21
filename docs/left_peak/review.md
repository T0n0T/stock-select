# Left Peak Review 层

## 方法定位

`left_peak` review 用来判断筛选出的“左峰突破后贴近左峰高点”样本是否仍具备再启动价值。它不是 `b1` 的 N 型深回调低点，也不是右侧强势追涨模型，核心是左峰锚定、突破后量价、周线推升和环境约束。

## 输入与环境

baseline reviewer：

- `review_left_peak_symbol_history()`

resolver：

- baseline review：`stock_select.reviewers.left_peak.review_left_peak_symbol_history`
- LLM prompt：`.agents/skills/stock-select/references/prompt-left-peak.md`

环境 profile：

- `left_peak/weak`
- `left_peak/neutral`
- `left_peak/strong`

环境说明：

- `weak`: 只保留锚点距离紧、五维组合命中的样本，严控偏离第一阴线开盘价过远。
- `neutral`: 优先保留周线推升、左峰锚定不过远且结构完整的样本。
- `strong`: 不默认放宽追高，只接受贴近左峰锚点的再启动确认。

## 左峰锚点字段

review 会额外输出：

- `left_peak_date`: 左峰日期
- `left_peak_high`: 左峰高点
- `left_peak_breakout_date`: 状态机确认突破日期
- `left_peak_first_bear_date`: 左峰后第一根阴线日期
- `left_peak_first_bear_open`: 左峰后第一根阴线开盘价，记为 `A`
- `left_peak_pick_close`: 入选日收盘价，记为 `B`
- `left_peak_b_div_a`: `B/A`
- `left_peak_abs_ba_minus_1`: `|B/A - 1|`
- `left_peak_a_lt_b`: `A < B`

锚点解释：

- `B/A` 越接近 `1` 越好，说明入选日仍贴近左峰后的关键换手锚点。
- `A < B` 更符合左峰突破后的站稳确认。
- 若 `B` 明显低于 `A`，或 `B/A` 明显偏离 `1`，应降低 verdict 层级。

## baseline 五个子分

### 1. `trend_structure`

基于以下结构判断：

- 左峰突破后是否保持趋势骨架
- `ma25 > ma60` 后中期趋势是否仍向上
- 当前价是否仍站在关键趋势支撑上方
- 突破后是否出现假突破或破位迹象

总体倾向：

- 越像“突破后贴锚蓄势”，分越高
- 跌回左峰下方、均线转弱或放量破位，分越低

### 2. `price_position`

核心看左峰高点、第一阴线开盘价 `A`、入选日收盘价 `B` 的关系：

- `B/A` 接近 `1` 且 `A < B`，分更高
- 当前价仍贴近左峰高点，分更高
- 已明显远离左峰锚点或上方空间不足，分下降
- 跌回 `A` 或左峰下方，视为锚点失效

### 3. `volume_behavior`

观察三段量价：

- 左峰突破时是否有效放量
- 突破后回踩是否缩量
- 入选日前后是否温和修复，而非放量冲高回落

总体倾向：

- 突破放量、回踩缩量、再启动温和放量 -> 高分
- 左峰附近放量长上影、放量阴线破坏结构 -> 低分

### 4. `previous_abnormal_move`

判断左峰突破前后是否有有效资金推动：

- 有清晰放量阳线或平台突破，且空间未透支 -> 高分
- 只有普通上涨，或异动后已经透支 -> 低分
- 异动后放量大阴线、冲高回落或结构破坏 -> 明显降分

### 5. `macd_phase`

`left_peak` 使用周线 MACD 状态作为重要背景：

- 周线推升、周 MACD 红柱有效、DIF/DEA 在水上、无顶背离 -> 加分
- 周 MACD 红柱轻微衰减 -> 中性观察
- 周 MACD 失效、顶背离或波段结束 -> 降分

周线推升是加分项，但不能覆盖左峰锚点失效或明显追高风险。

## 专用评分层

除五个通用子分外，baseline 还计算：

- `left_peak_anchor_score`: 左峰锚点分
- `structure_combo_score`: 五维组合结构分
- `macd_context_score`: 周线/日线 MACD 背景分
- `environment_score`: 环境匹配分
- `risk_penalty_score`: 风险惩罚分

`total_score` 会结合这些专用分与 `score_layer_score`，用于 summary 排序。

## verdict 与 score_layer

`left_peak` 输出统一 verdict：

- `PASS`
- `WATCH`
- `FAIL`

同时输出细分层：

- `PASS-A`
- `PASS-B`
- `WATCH-A`
- `WATCH-B`
- `FAIL-anchor`
- `FAIL-structure`

当前判定重点：

- 锚点距离过远优先进入 `FAIL-anchor`
- `neutral` 环境允许周线推升且锚点不过远的高胜率组合进入 `PASS-A`
- `weak` 环境要求 `|B/A - 1| <= 0.05` 且命中高胜率五维组合
- `strong` 环境不因市场强而放宽追高，只接受更贴近锚点的再启动确认
- 周线推升但结构不够完整时，优先进入 `WATCH-A` 或 `WATCH-B`

## LLM prompt 口径

`left_peak` 使用独立 prompt：

- `.agents/skills/stock-select/references/prompt-left-peak.md`

LLM 仍输出通用 JSON contract：

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

prompt 强制要求：

- `position_reasoning` 必须说明左峰高点、`A`、`B` 与 `B/A`
- `macd_reasoning` 必须说明周线波段状态、周 MACD 红柱、DIF/DEA 水上状态与背离风险
- `signal_reasoning` 必须说明当前是否符合 left_peak 的左峰贴锚再启动
- 不允许输出 `score_layer`、`gate_flags` 等 baseline 派生字段

## CLI 用法

筛选：

```bash
stock-select screen --method left_peak --pick-date 2026-05-19
```

完整 run：

```bash
stock-select run --method left_peak --pick-date 2026-05-19
```

仅 baseline review：

```bash
stock-select review --method left_peak --pick-date 2026-05-19
```

补样本：

```bash
python scripts/backfill_samples.py --method left_peak --start-date 2026-02-02 --end-date 2026-05-20
```

`left_peak` 与 `b1/b2/dribull` 共用基础 prepared cache：

- `runtime/prepared/<pick_date>.feather`
- `runtime/prepared/<pick_date>.meta.json`

## 当前胜率统计

`left_peak` 当前实现下的总体胜率、分环境分 `verdict` 胜率、以及 `PASS top3` 胜率，统一见：

- [方法胜率统计](../share/method-win-rates.md)
