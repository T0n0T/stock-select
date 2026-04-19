# B2 MACD Wave Design

## Goal

Refactor `b2` so screening no longer treats `MACD` as a simple bullish/bearish gate. Instead:

- phase 1 performs only non-`MACD` structural prefiltering
- phase 2 performs deterministic daily and weekly `MACD` wave classification
- `review` and LLM review use the same wave interpretation in text reasoning

The `MACD` wave logic should be reusable by future methods such as `b1`, so the core implementation must be method-agnostic.

## Scope

In scope:

- remove `MACD` gating from `b2` phase-1 prefilter
- replace current `b2` phase-2 `MACD` boolean checks with deterministic weekly/daily wave classification
- introduce a reusable `MACD` wave-analysis core
- keep `b2` review JSON schema stable while making text reasoning explicitly describe waves
- extend `b2` LLM review task context and prompt guidance so review language matches deterministic wave screening
- update tests for screening, review, and prompt/task contracts

Out of scope:

- changing `b1` screening behavior immediately
- adding new structured review result fields for wave labels
- requiring LLM reviewers to infer weekly waves from an unseen weekly chart
- preserving the old monthly `MACD` requirement for `b2`

## Current Problem

Current `b2` behavior mixes two different ideas:

- phase 1 claims to be non-`MACD`, but still requires daily `dif > dea`
- phase 2 uses simple daily/weekly/monthly `dif > dea` gates instead of identifying wave position

This conflicts with the desired workflow:

- screen for structural candidates first
- then identify whether the symbol is in an acceptable weekly and daily `MACD` wave combination
- then make review language explicitly state the weekly and daily wave interpretation

Current `b2` review also only expresses a generic `macd_phase` score, so the screening logic and review language cannot stay aligned.

## Design

### 1. B2 Screening Flow

`b2` remains a two-phase screen.

#### Phase 1: Structural Prefilter Only

Phase 1 keeps these conditions:

- recent 15-trading-day low-`J` hit using the existing `b1`-style rule
- `zxdq > zxdkx`
- `MA25` support validity:
  - `low <= ma25 * 1.005`
  - `close >= ma25`
- shrinking daily volume versus the previous trading day
- `ma60 >= ref(ma60, 1)`
- `abs((close / ma144 - 1) * 100) <= 30`

Phase 1 must not require any `MACD` condition.

Specifically, the current daily `dif > dea` check must be removed from the phase-1 prefilter path.

#### Phase 2: Wave Classification

Phase 2 evaluates only weekly and daily `MACD` wave position and uses that to decide whether a symbol becomes a final candidate.

`b2` passing combinations:

- weekly wave `wave1` + daily wave `wave2_end`
- weekly wave `wave1` + daily wave `wave4_end`
- weekly wave `wave3` + daily wave `wave2_end`
- weekly wave `wave3` + daily wave `wave4_end`

`b2` failing combinations:

- weekly wave `wave2`
- weekly wave `invalid`
- daily wave `invalid`

No monthly `MACD` rule is used in the new design.

### 2. Reusable MACD Wave Core

Create a method-agnostic analysis module, for example:

- `src/stock_select/analysis/macd_waves.py`

This module owns reusable logic only:

- daily and weekly `MACD` sampling helpers
- effective cross detection
- expansion / pullback segment recognition
- churn / invalid-state detection
- reusable explanatory fragments for wave reasoning

It must not contain `b2`-only pass rules.

Recommended public surface:

- `classify_weekly_macd_wave(frame, pick_date) -> WaveClassification`
- `classify_daily_macd_wave(frame, pick_date) -> WaveClassification`
- `analyze_macd_wave_context(frame, pick_date) -> MacdWaveContext`

Recommended result shape:

- `label`
- `passed`
- `reason`
- `details`

For daily wave analysis, `details` should also expose `third_wave_gain` when relevant.

### 3. Effective Cross Rules

To reduce false signals from `DIF` / `DEA` weaving, a cross is only valid when the crossing is followed by confirmation.

Recommended rules:

- effective golden cross:
  - `DIF` moves above `DEA`
  - histogram turns positive
  - positive histogram does not weaken immediately, with at least two constructive bars
- effective dead cross:
  - `DIF` moves below `DEA`
  - histogram turns negative
  - negative histogram does not weaken immediately, with at least two constructive bars

These rules may be implemented with slightly different low-level mechanics, but the tests must preserve the intent: avoid classifying one-bar noise as a true wave transition.

### 4. Weekly Wave Semantics

Weekly output labels:

- `wave1`
  - current state is the first valid bullish advance after an effective golden cross
  - no later effective dead cross has ended that segment
- `wave2`
  - the market has moved from `wave1` into a confirmed pullback after an effective dead cross
  - implementation may also classify a still-bullish but clearly fading weekly impulse as `wave2` when the fixture evidence shows momentum has rolled over before a full bearish cross
- `wave3`
  - a complete sequence of bullish advance, pullback, and second bullish advance has formed:
    - effective golden cross
    - effective dead cross
    - effective golden cross
  - current state is inside the second bullish advance
- `invalid`
  - wave state is unclear due to insufficient structure or excessive churn

Recommended churn rejection:

- if histogram sign or effective-cross state flips too frequently within the recent evaluation window, classify as `invalid`

### 5. Daily Wave Semantics

Daily output labels:

- `wave2_end`
  - a first bullish advance already exists
  - the symbol is in the pullback after that advance
  - the pullback is near its end on a left-side basis
  - required traits:
    - negative histogram bars are shrinking
    - `DIF` and `DEA` are converging
    - no renewed golden cross yet
  - implementation may also classify a still-bullish but clearly fading left-side pullback as `wave2_end` when histogram contraction and line convergence indicate the setup still matches the intended fixture-driven business behavior
- `wave4_end`
  - a first advance, second-wave pullback, and third-wave advance already exist
  - the current state is the later pullback near its end on a left-side basis
  - required traits:
    - negative histogram bars are shrinking
    - `DIF` and `DEA` are converging
    - no renewed golden cross yet
  - additional gating:
    - `third_wave_gain = third_wave_high / second_wave_low - 1 <= 0.30`
- `invalid`
  - structure is too noisy
  - the pullback is still deteriorating
  - a renewed golden cross has already started the next advance
  - the prior sequence is incomplete or ambiguous

The design is intentionally left-side:

- no renewed daily golden cross is required
- a setup that has already re-crossed bullish should no longer be called a pullback-end setup

For the reusable Task 1 wave core, fixture-driven business intent takes precedence over a stricter literal branch sketch when they conflict. If the starter branch sketch and the approved test fixtures disagree, the implementation should preserve the fixture outcomes and the plan should be corrected to match.

### 6. B2-Specific Strategy Adapter

Create a small `b2`-specific adapter layer, for example inside:

- `src/stock_select/strategies/b2.py`

or a helper such as:

- `src/stock_select/strategies/b2_wave_rules.py`

This layer owns only method-specific logic:

- allowed weekly + daily wave combinations
- `wave4_end` acceptance only when `third_wave_gain <= 30%`
- any `b2`-specific reasoning phrasing used by screen statistics or review

This separation keeps the `MACD` core reusable for future `b1` work.

### 7. Screening Statistics

Replace the current `b2` `MACD` failure buckets with wave-oriented buckets.

Recommended buckets:

- `total_symbols`
- `eligible`
- `fail_recent_j`
- `fail_insufficient_history`
- `fail_support_ma25`
- `fail_volume_shrink`
- `fail_zxdq_zxdkx`
- `fail_ma60_trend`
- `fail_ma144_distance`
- `fail_weekly_wave`
- `fail_daily_wave`
- `fail_wave_combo`
- `selected`

`fail_insufficient_history` should include:

- missing required derived fields
- too little history to identify the requested wave sequence credibly
- unusable weekly or daily `MACD` alignment inputs

### 8. Baseline Review

Keep the existing `b2` review output schema stable:

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`
- `total_score`
- `signal_type`
- `verdict`
- `comment`

Do not add structured wave-label fields.

Instead, `review_b2_symbol_history()` must call the same deterministic `MACD` wave-analysis core used by screening and write the result into text fields:

- `macd_reasoning` must explicitly state:
  - weekly wave label
  - daily wave label
  - why the setup does or does not fit `b2`
- `signal_reasoning` must explicitly state:
  - whether the weekly/daily combination is acceptable
  - if `wave4_end`, whether the third-wave gain remains within 30%
- `comment` must compress the same conclusion into one short Chinese sentence

`macd_phase` may remain as the numeric score field, but its interpretation for `b2` should shift toward wave-quality and setup readiness rather than a generic bullish-strength grade.

### 9. LLM Review Task Context

Keep the final LLM review JSON schema stable.

Do not add structured wave output fields.

For `b2`, augment `llm_review_tasks.json` task payloads with textual context generated from deterministic wave analysis, for example:

- `weekly_wave_context`
- `daily_wave_context`
- `wave_combo_context`

These fields should summarize the deterministic result that screening and baseline review already used.

This is required because the current `b2` LLM review consumes a daily chart PNG only and cannot reliably infer weekly wave position from an unseen weekly chart.

### 10. B2 Prompt Update

Update:

- `.agents/skills/stock-select/references/prompt-b2.md`

The prompt must explicitly instruct the reviewer:

- weekly wave context is supplied by the system and must not be re-invented from an unseen weekly chart
- the reviewer should assess whether the supplied wave interpretation is consistent with the visible daily chart and with the broader setup quality
- `macd_reasoning`, `signal_reasoning`, and `comment` must explicitly mention:
  - weekly wave interpretation
  - daily wave interpretation
  - whether the combination fits `b2`

The prompt should keep the same JSON contract, but the language for `MACD` assessment should shift from generic phase wording toward wave-position interpretation.

### 11. Tests

Add or update tests in four areas.

#### Screening tests

- phase 1 no longer rejects on daily `MACD`
- phase 2 identifies:
  - weekly `wave1`
  - weekly `wave2`
  - weekly `wave3`
  - weekly `invalid`
  - daily `wave2_end`
  - daily `wave4_end`
  - daily `invalid`
- `wave4_end` fails when third-wave gain exceeds 30%
- final combination pass/fail behavior matches `b2` rules

#### MACD wave core tests

- effective cross detection rejects one-bar noise
- weekly wave state machine behaves as specified
- daily wave state machine behaves as specified
- churn detection yields `invalid`

#### Baseline review tests

- `macd_reasoning` includes weekly and daily wave interpretation
- `signal_reasoning` explains combination acceptance or rejection
- `comment` mentions the same conclusion in compressed form

#### Prompt/task tests

- `b2` review tasks include wave-context fields
- `prompt-b2.md` documents required weekly/daily wave reasoning
- review merge and HTML export keep working with unchanged JSON structure

## Migration Strategy

Implement in two steps.

### Step 1

- add reusable `MACD` wave-analysis core
- refactor `b2 screen` phase 1 and phase 2
- replace old `MACD` failure buckets with wave-oriented buckets
- stabilize candidate selection behavior first

### Step 2

- refactor `b2` baseline review text reasoning to use wave analysis
- add LLM task wave-context fields
- update `prompt-b2.md`
- update review/task/prompt tests

This split reduces the risk of mixing screening regressions with review-language regressions in the same iteration.

## Risks

- `b2` candidate counts will likely change materially
- `macd_phase` will remain schema-compatible but semantically narrower for `b2`
- if the wave-analysis core is placed directly under a `b2`-named module, future `b1` reuse will become awkward
- if LLM review is not given deterministic weekly-wave context, the review language will drift from the screening logic

## Decision Summary

- `b2` phase 1 becomes non-`MACD` only
- `b2` phase 2 becomes weekly/daily `MACD` wave classification
- monthly `MACD` is removed from `b2`
- wave logic is implemented in a reusable core, not a `b2`-specific kernel
- wave conclusions stay in review text only, not in new structured JSON fields
- LLM review receives deterministic wave context instead of guessing weekly waves from a daily chart
