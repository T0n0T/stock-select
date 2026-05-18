# 共用 Review 流程

本文描述各方法在 `review` 层共享的流程与口径。方法特有的 baseline review 规则见各自目录。

## 统一入口

```bash
uv run stock-select review --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
```

盘中入口：

```bash
uv run stock-select review --method <method> --intraday
```

## Review 输入

`review` 阶段统一读取：

- `candidates/<pick_date>.<method>.json`
- `charts/<pick_date>.<method>/<code>_day.png`
- PostgreSQL 中该股票截至 `pick_date` 的历史日线

若缺少图表文件，则该股票记入 `failures`，不会生成单股 review。

## Review Resolver

各方法通过 `review_resolvers.py` 绑定：

- baseline reviewer
- LLM prompt 文件

当前映射关系：

- `b1` -> `review_b1_symbol_history` + `prompt-b1.md`
- `b2` -> `review_b2_symbol_history` + `prompt-b2.md`
- `dribull` -> `review_dribull_symbol_history` + `prompt-dribull.md`
- `hcr` -> 默认 reviewer + `prompt.md`

## baseline review 的统一输出骨架

单股 review 文件统一由 `build_review_result()` 组装，顶层至少包含：

- `code`
- `pick_date`
- `chart_path`
- `review_mode`
- `baseline_review`
- `llm_review`
- `total_score`
- `signal_type`
- `verdict`
- `comment`

其中：

- 初始 `review_mode` 为 `baseline_local`
- 合并 LLM 后为 `merged`

## baseline 共用评分字段

当前四个方法的 baseline review 都会输出以下五个子分：

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`

其中：

- `hcr` 也会产出 `macd_phase`
- 但 `hcr` 的 `total_score` 计算不使用 `macd_phase` 权重

`signal_type` 统一分为：

- `trend_start`
- `rebound`
- `distribution_risk`

`verdict` 统一分为：

- `PASS`
- `WATCH`
- `FAIL`

## baseline 总分口径

### 默认权重

默认方法权重：

- `trend_structure`: `0.18`
- `price_position`: `0.18`
- `volume_behavior`: `0.24`
- `previous_abnormal_move`: `0.20`
- `macd_phase`: `0.20`

### `b1` 权重

- `trend_structure`: `0.23`
- `price_position`: `0.20`
- `volume_behavior`: `0.22`
- `previous_abnormal_move`: `0.20`
- `macd_phase`: `0.15`

### `b2` 权重

- `trend_structure`: `0.14`
- `price_position`: `0.22`
- `volume_behavior`: `0.00`
- `previous_abnormal_move`: `0.14`
- `macd_phase`: `0.35`
- `signal`: `0.15`

其中 `signal` 分值：

- `B3` -> `5.0`
- `B3+` -> `5.0`
- `B2` -> `4.0`
- 其他 -> `3.0`

### `hcr` 权重

`hcr` 走“无 MACD”权重：

- `trend_structure`: `0.30`
- `price_position`: `0.25`
- `volume_behavior`: `0.40`
- `previous_abnormal_move`: `0.05`

## 市场环境 profile

仅 `b1` 与 `b2` 在 review 阶段接入 market environment profile。

环境状态来自运行时 market environment：

- `weak`
- `neutral`
- `strong`

profile 会影响：

- baseline 子分权重
- `PASS` / `WATCH` 阈值
- 部分子分模式
- 提供给 LLM task 的附加 focus context

`dribull` 与 `hcr` 当前不接 environment profile。

## LLM review task 生成

每次 `review` 会同时生成：

- 单股 baseline review json
- `llm_review_tasks.json`

任务文件固定写入：

- `prompt_path`
- `rubric_path`
- `input_mode: image`
- `dispatch: subagent`
- `max_concurrency: 6`

`b1` / `b2` / `dribull` 会额外附带：

- `weekly_wave_context`
- `daily_wave_context`
- `wave_combo_context`

`b1` / `b2` 在有 environment profile 时还会附带：

- `environment_state`
- `environment_reason`
- `environment_llm_focus`
- `review_focus_context`

是否进入 `llm_review_tasks.json` 由 `--llm-min-baseline-score` 控制：

- 未设置时，全部进入
- 设置后，仅 `baseline total_score >= 阈值` 的股票进入

## LLM review 归一化与合并

`review-merge` 阶段会：

1. 读取 `llm_review_results/*.json`
2. 校验 reasoning 与五个评分字段是否齐全
3. 重算 LLM `total_score`
4. 与 baseline 合并

合并口径：

- 默认参数名仍是 `baseline_weight=0.4`、`llm_weight=0.6`
- 但当前 `b1` / `b2` 的实现里会自动调换为 baseline `0.6` + llm `0.4`
- 其他方法按 baseline `0.4` + llm `0.6`

最终总分统一按：

- `>= 4.0` -> `PASS`
- `>= 3.2` -> `WATCH`
- 其他 -> `FAIL`

## summary 汇总口径

`summary.json` 统一输出：

- `reviewed_count`
- `recommendations`
- `excluded`
- `failures`

推荐入选规则：

- `b1`: 只要单股 `verdict == PASS` 就进入 `recommendations`
- 其他方法：要求 `verdict == PASS` 且 `total_score >= 4.0`

排序口径：

- 先按 `score_layer_score`
- 再按 `total_score`

其中 `score_layer_score` 目前主要对 `b1` 有意义。
