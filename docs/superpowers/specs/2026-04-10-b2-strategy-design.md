# B2 Strategy Design

## Goal

Add a new deterministic screening method named `b2` to the existing `stock-select` CLI so it works as a first-class peer of `b1` and `hcr`, while extending the chart and review pipeline to include daily `MACD`.

`b2` is intended to find symbols that:

- recently showed a `B1`-style low-`J` setup
- still maintain weekly bullish alignment
- remain above the `zxdq > zxdkx` trend filter
- are entering a fresh daily `MACD` expansion phase

The new method must:

- be selectable through the existing `--method` flag
- run through the existing `screen`, `chart`, `review`, `review-merge`, `run`, and `render-html` workflow
- preserve the current runtime artifact layout
- keep existing `b1` and `hcr` screening behavior unchanged
- upgrade chart rendering, baseline review, LLM review validation, and HTML export so daily `MACD` is a first-class review dimension

## Scope

In scope:

- support `--method b2` anywhere the CLI currently accepts built-in methods
- add deterministic `b2` preprocessing and screening logic
- compute daily `MACD` in reusable preprocessing and chart/review helpers
- render daily `MACD` in chart PNG files
- add a fifth review dimension named `macd_phase` to baseline review and `llm_review`
- update the LLM prompt contract to include `macd_reasoning` and `scores.macd_phase`
- update `review-merge` validation to enforce the new review schema
- update HTML export so `macd_phase` and `MACD` reasoning are visible in offline reports
- add automated coverage for the new method and the expanded review/chart contract

Out of scope:

- changing the existing `b1` formula or thresholds
- changing the existing `hcr` formula or thresholds
- adding weekly `MACD`
- introducing a weekly chart image or multi-chart review flow
- reworking the runtime directory structure
- introducing user-configurable `MACD` parameters in this version

## Current Problem

The repository already supports multiple methods at the CLI level, but `b2` does not exist yet and the review stack currently lacks `MACD` as a structured dimension.

Current limitations:

- no deterministic `b2` method exists
- chart PNG output does not include `MACD`
- baseline local review scores only four dimensions
- LLM review validation requires only the existing four score fields
- HTML export hard-codes the four current score dimensions and omits any `MACD` reasoning

This means the repository cannot express the user's desired workflow of:

- screening for a recent low-`J` setup that has transitioned into rising `MACD`
- showing `MACD` visually on the chart
- evaluating the `MACD` phase in both local and LLM-assisted review

## Design

### 1. Method Contract

The CLI should accept:

- `--method b1`
- `--method b2`
- `--method hcr`

Every command that already requires a method should continue to require one, and the artifact metadata must continue to store the true selected method.

No new runtime roots are needed. Existing method-keyed paths remain valid:

- `runtime/candidates/<pick_date>.<method>.json`
- `runtime/prepared/<pick_date>.<method>.pkl`
- `runtime/charts/<pick_date>.<method>/`
- `runtime/reviews/<pick_date>.<method>/`

The same applies to intraday `run_id`-keyed paths.

### 2. Strategy Architecture

`b2` should be implemented as a new strategy module under:

- `src/stock_select/strategies/b2.py`

The current strategy dispatch should expand to include `b2` as a true built-in method, not a `b1` mode switch.

The implementation should preserve these boundaries:

- shared daily indicator preparation in CLI preprocessing or common helpers
- method-specific screen logic in strategy modules
- method-agnostic chart orchestration
- method-agnostic review orchestration with a shared review schema

This keeps screening rules isolated per method while allowing chart, baseline review, LLM review, merge, and HTML export to evolve in one consistent schema.

### 3. Shared Daily Indicator Model

The prepared per-symbol daily frame should be extended with daily `MACD` fields so the same indicator data can be reused by:

- `b2` screening
- chart rendering
- baseline review
- intraday prepared-cache review

Required daily derived fields:

- `turnover_n`
- `J`
- `zxdq`
- `zxdkx`
- `weekly_ma_bull`
- `max_vol_not_bearish`
- `dif`
- `dea`
- `macd_hist`

Recommended `MACD` parameters:

- fast EMA: `12`
- slow EMA: `26`
- signal EMA: `9`

The repository should treat:

- `dif = EMA(close, 12) - EMA(close, 26)`
- `dea = EMA(dif, 9)`
- `macd_hist = dif - dea`

`macd_hist` should be stored as the raw signed histogram value. The design intentionally does not multiply it by 2, because the workflow only needs relative expansion/contraction and phase comparison, not vendor-specific chart scaling.

### 4. B2 Screening Formula

`b2` should preserve the `b1` liquidity prefilter and weekly-trend framing, but shift the entry logic from “today is low-`J`” to “recently was low-`J`, now `MACD` is expanding.”

The screen should run on the target `pick_date` after the same top-turnover prefilter used by `b1`:

- `turnover_n` uses the existing 43-day rolling turnover definition
- each trade date keeps only the top 5000 symbols by `turnover_n`

After the liquidity pool filter, `b2` should require all of the following:

1. **Recent low-`J` window**
   - look back the most recent 15 trading days ending on `pick_date`
   - pass if any day in that window satisfies the existing `b1` `J` condition:
     - `J < 15`
     - or `J <= expanding 10% quantile for that symbol`
   - `pick_date` itself does not need to satisfy the `J` condition

2. **Current trend filter**
   - on `pick_date`, require `zxdq > zxdkx`

3. **Current weekly bullish alignment**
   - on `pick_date`, require weekly `10/20/30` moving averages in bullish alignment
   - the definition remains `MA10 > MA20 > MA30` on the weekly-close series, forward-filled back to daily rows

4. **Current `MACD` expansion**
   - on `pick_date`, require the latest five valid daily histogram values to be strictly increasing:
     - `hist[t-4] < hist[t-3] < hist[t-2] < hist[t-1] < hist[t]`

`b2` does **not** inherit the `b1` rule that the max-volume day in the recent window must be non-bearish. That filter remains specific to `b1` unless explicitly requested later.

### 5. B2 Failure Buckets

`b2` should report first-failed-condition stats similarly to `b1`, but with buckets aligned to its own rules.

Recommended stats:

- `total_symbols`
- `eligible`
- `fail_recent_j`
- `fail_insufficient_history`
- `fail_zxdq_zxdkx`
- `fail_weekly_ma`
- `fail_macd_trend`
- `selected`

`fail_insufficient_history` should cover cases where the target row cannot be evaluated because required derived values are missing, including:

- missing `zxdkx`
- insufficient history to compute the recent 15-day `J` window meaningfully
- fewer than five valid `MACD` histogram observations by `pick_date`

The first failing condition should win, matching the current `b1` reporting style.

### 6. Candidate Output

The candidate output shape should remain compatible with the current workflow:

- `code`
- `pick_date`
- `close`
- `turnover_n`

Optional additive fields are acceptable if they simplify later display, but they are not required for v1. If any are added, they should be additive only.

Acceptable examples:

- `recent_j_hit_date`
- `macd_hist`
- `dif`
- `dea`

### 7. Chart Rendering

Daily chart PNG rendering must be upgraded so `MACD` is visible to human reviewers and LLM reviewers.

Required chart layout:

- main panel:
  - candlesticks
  - `zxdq`
  - `zxdkx`
- volume panel:
  - existing volume bars
- `MACD` panel:
  - `DIF`
  - `DEA`
  - histogram bars for `macd_hist`

Rendering rules:

- `DIF` should be shown as the white line in prompt language, even if the actual plotted color is light/bright for visibility
- `DEA` should be shown as the yellow line in prompt language, even if exact color tuning changes slightly in code
- histogram bars should visually distinguish positive and negative values

The chart should remain a single PNG file so the current review pipeline remains unchanged.

### 8. Review Schema Upgrade

The current four-dimension review schema should be upgraded to five dimensions for all methods.

Required reasoning fields:

- `trend_reasoning`
- `position_reasoning`
- `volume_reasoning`
- `abnormal_move_reasoning`
- `macd_reasoning`
- `signal_reasoning`

Required score fields:

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`

Baseline review should return:

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`
- `total_score`
- `signal_type`
- `verdict`
- `comment`

LLM review validation should require the same fifth score and the new `macd_reasoning` field.

### 9. MACD Phase Semantics

`macd_phase` is a daily-chart-only dimension and must use the same five-point semantics in baseline review and the LLM prompt.

Required scoring meanings:

#### 5 points: Start Phase

- `DIF > DEA`
- histogram is above zero
- the recent five histogram bars are strictly increasing
- the structure still looks close to the initial bullish crossover / launch zone

This is the preferred “startup” stage.

#### 4 points: Strengthening Phase

- `DIF > DEA`
- histogram remains positive
- the trend has clearly expanded and the two lines are moving apart
- histogram is still increasing or remains strongly expanded

This is a healthy strengthening phase, but later than the ideal start.

#### 3 points: Divergence Phase

- price remains strong or near highs
- `MACD` momentum no longer confirms as cleanly
- lines show high-level flattening and histogram contracts

This is a warning-grade but not yet outright failure phase.

#### 2 points: Dead Cross

- `DIF < DEA`

This is a clear weakening phase.

#### 1 point: Just Turned Negative

- histogram has just turned from positive to negative, or just dropped below zero in the latest step

This is the weakest phase because it marks fresh momentum failure.

The distinction between 1 and 2 is temporal:

- `1` is the fresh breakdown / fresh negative turn
- `2` is the broader dead-cross weak state

### 10. Baseline Review Calculation

The local baseline review should compute daily `MACD` from the provided history and score `macd_phase` programmatically.

The scoring model should expand from four dimensions to five dimensions.

Recommended weights:

- `trend_structure`: `0.18`
- `price_position`: `0.18`
- `volume_behavior`: `0.24`
- `previous_abnormal_move`: `0.20`
- `macd_phase`: `0.20`

Decision thresholds should remain unchanged:

- `PASS` when total score is at least `4.0`
- `WATCH` when total score is at least `3.2` and below `4.0`
- `FAIL` when total score is below `3.2`

The current protective rule must remain:

- force `FAIL` if `volume_behavior == 1`

The baseline `comment` should be updated so it mentions the `MACD` phase in the final Chinese trader-style sentence.

### 11. LLM Prompt Contract

`.agents/skills/stock-select/references/prompt.md` should be updated so the multimodal reviewer is explicitly instructed to analyze the new `MACD` panel.

Required prompt changes:

- add `MACD` to the list of visible chart elements that may be analyzed
- add a fifth scoring section named `MACD Phase`
- define the five stage meanings using the agreed terms:
  - 启动阶段 = `5`
  - 加强阶段 = `4`
  - 背离阶段 = `3`
  - `MACD` 死叉 = `2`
  - 刚由正转负 = `1`
- add `macd_reasoning` to the mandatory reasoning sequence
- add `scores.macd_phase` to the required JSON object
- require the final Chinese comment to mention:
  - weekly trend
  - volume-price structure
  - previous abnormal move
  - `MACD` phase
  - present risk or upside room

The prompt should continue to emphasize that the model must judge only from visible chart information and must not invent unseen numeric values.

### 12. Review Merge Validation

`normalize_llm_review()` must reject any payload that omits:

- `macd_reasoning`
- `scores.macd_phase`

The normalized flattened output should expose:

- `macd_phase`

alongside the other flattened score fields.

`merge_review_result()` can keep the current baseline/LLM weighted blend logic. No special-case merge behavior is needed for `macd_phase`; it is included implicitly via the final `total_score` in each side's review.

### 13. HTML Export

The shareable HTML report must reflect the upgraded review schema.

Required changes:

- include `macd_phase` in baseline and LLM score grids
- include a `MACD` reasoning block in the expanded LLM reasoning view
- preserve all existing report structure, names lookup, packaged export behavior, and chart embedding

This is required because the current HTML exporter hard-codes the four old score labels and would otherwise silently hide the new dimension.

### 14. Method Compatibility

`b1` screening behavior must remain unchanged.

`hcr` screening behavior must remain unchanged.

However, because the review schema becomes shared and five-dimensional, all methods should benefit from:

- the upgraded chart that includes `MACD`
- the upgraded baseline review shape
- the upgraded LLM prompt and validation contract
- the upgraded HTML export shape

This is acceptable because the chart/review layer is method-agnostic and is not the same thing as the screening formula.

### 15. Intraday Compatibility

The `b2` design should remain compatible with the repository's intraday architecture.

If intraday `b2` is implemented in the same change, it should follow the existing method-aware runtime layout and use prepared intraday data with the same indicator columns.

If intraday `b2` is deferred, the CLI must fail clearly rather than silently mapping `b2` to another method.

This design does not require immediate intraday `b2` support, but it does require that method dispatch remain explicit and honest.

### 16. Error Handling

Required behavior:

- unsupported methods fail fast with a clear supported-method list
- `b2` symbols with missing derived data are counted under `fail_insufficient_history`
- `review-merge` rejects LLM JSON that omits the new `MACD` fields
- chart rendering should fail clearly if daily history is empty or malformed, as it does today

For `b2` screening specifically:

- the 15-day recent-`J` window should use only rows up to `pick_date`
- if the target row does not exist, the symbol is not eligible for that day
- if there are fewer than five valid histogram values by `pick_date`, treat the symbol as insufficient history rather than as a normal `MACD` trend failure

### 17. Testing

Required automated coverage:

#### B2 strategy tests

Create dedicated tests for the new method:

- recent-window `J` pass when the trigger day is inside the last 15 trading days but not on `pick_date`
- fail when no day in the last 15 satisfies the `B1` `J` condition
- fail when `zxdq <= zxdkx` on `pick_date`
- fail when weekly moving averages are not bullish on `pick_date`
- fail when the last five histogram values are not strictly increasing
- insufficient-history counting for missing `zxdkx`, missing `MACD`, or too-short evaluation windows
- liquidity pool behavior remains aligned with `b1`

#### Charting tests

Extend charting tests to verify:

- `_prepare_daily_chart_frame()` includes `dif`, `dea`, and `macd_hist`
- the chart frame still sorts correctly and honors the `bars` limit
- `export_daily_chart()` still writes a non-empty PNG file with the expanded multi-panel layout

#### Review orchestrator tests

Extend review tests to verify:

- baseline review returns `macd_phase`
- `normalize_llm_review()` requires `macd_reasoning`
- `normalize_llm_review()` requires `scores.macd_phase`
- flattened normalized output exposes `macd_phase`
- five-dimension total scoring behaves as expected
- `volume_behavior == 1` still forces `FAIL`

#### CLI tests

Extend CLI tests to verify:

- `--method b2` is accepted
- `screen --method b2` writes correct metadata and candidate output
- the method dispatch does not silently route `b2` through `b1`
- `review` writes `llm_review_tasks.json` for `b2`
- `review-merge` accepts valid five-dimension LLM payloads
- `render-html` includes `macd_phase` and `MACD` reasoning in exported output

## Recommended Implementation Notes

- keep the `MACD` computation in one shared helper so charting and review cannot drift
- keep `b2` deterministic and free of subjective review heuristics
- keep review schema shared across methods even though `b2` motivates the new dimension
- do not attempt a broader strategy-framework refactor in this change; add `b2` pragmatically inside the existing architecture

## Summary

`b2` should be added as a new deterministic method that:

- keeps the `b1` liquidity pool
- looks back 15 trading days for any `B1`-style low-`J` trigger
- requires current `zxdq > zxdkx`
- requires current weekly `10/20/30` bullish alignment
- requires the latest five daily `MACD` histogram bars to be strictly increasing

The chart/review pipeline should be upgraded alongside it so:

- the chart PNG includes daily `MACD`
- baseline review and `llm_review` both score `macd_phase`
- the prompt, merge validation, and HTML export all understand the new fifth dimension

This preserves the existing workflow while making `b2` and `MACD` review first-class citizens of the repository.
