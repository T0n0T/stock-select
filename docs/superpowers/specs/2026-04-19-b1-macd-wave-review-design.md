# B1 MACD Wave Review Design

## Goal

Extend the reusable MACD wave-analysis core into the `b1` review flow without changing `b1` deterministic screening.

The new `b1` behavior should:

- keep `screen --method b1` unchanged
- make `b1` baseline review reuse the same weekly/daily MACD wave interpretation already used by `b2`
- keep the final review JSON schema stable
- make `b1` baseline `comment` explicitly compress the weekly/daily wave conclusion
- add deterministic wave context into `b1` LLM review task payloads and prompt instructions
- start counting `macd_phase` inside `b1` total-score calculation

## User Decisions

The following decisions are fixed for this change:

- `b1` screening rules do not change
- only the post-screen review layer changes
- `b1` review reuses the same weekly/daily wave acceptance logic as `b2`
- `b1` baseline review must not add new structured output fields
- wave understanding stays in existing text output, mainly `comment`
- `b1` total score must now include `macd_phase`
- `b1` should get its own reviewer integration instead of continuing to reuse the generic default reviewer path
- `b1` should get its own prompt contract instead of sharing the current generic prompt with `hcr`

## Scope

In scope:

- add a dedicated `b1` baseline reviewer
- route `b1` through its own review resolver
- reuse `classify_weekly_macd_wave()` and `classify_daily_macd_wave()` for `b1` review
- reinterpret `b1` `macd_phase` as wave quality / setup readiness
- include `macd_phase` in `b1` total-score calculation
- add deterministic wave context to `b1` LLM review tasks
- add a dedicated `b1` review prompt
- update tests and docs affected by the `b1` review flow

Out of scope:

- changing `b1` screening filters
- changing `hcr` screening or review behavior
- changing the reusable wave core semantics again
- adding new structured wave-label fields into merged review JSON

## Current Problem

`b1` and `hcr` both currently flow through the generic default reviewer and shared prompt path.

That causes three issues:

- `b1` review cannot express the same weekly/daily wave interpretation already introduced for `b2`
- the current generic `macd_phase` scoring for `b1` is detached from the reusable wave-analysis core
- `hcr` and `b1` have different review needs, but they still share one prompt contract

## Design

### 1. Keep B1 Screening Unchanged

`run_b1_screen_with_stats()` and all `screen --method b1` behavior remain unchanged.

No wave classification is used as a deterministic gate during `b1` screening.

This preserves:

- the low-`J` entry logic
- `close > zxdkx`
- `zxdq > zxdkx`
- weekly moving-average alignment
- max-volume-day non-bearish filter

### 2. Add A Dedicated B1 Reviewer

Add:

- `src/stock_select/reviewers/b1.py`

This new reviewer becomes the implementation owner for `b1` baseline review instead of routing `b1` through `reviewers/default.py`.

Responsibilities:

- keep the existing `b1` trend / position / volume / abnormal-move scoring shape
- classify weekly and daily MACD waves using the shared analysis core
- score `macd_phase` from wave readiness instead of generic histogram shape alone
- compress the wave conclusion into the existing `comment`
- keep the final baseline-review schema unchanged

### 3. Reuse The Existing B2 Wave Rules

`b1` review uses the same weekly/daily wave acceptance logic as `b2`.

Accepted combinations:

- weekly `wave1` + daily `wave2_end`
- weekly `wave1` + daily `wave4_end`
- weekly `wave3` + daily `wave2_end`
- weekly `wave3` + daily `wave4_end`

Rejected or downgraded cases:

- weekly `wave2`
- weekly `invalid`
- daily `invalid`
- `wave4_end` with `third_wave_gain > 0.30`

The design remains left-biased:

- daily pullback-end setups are preferred
- already re-crossed right-side extensions should not be described as ideal `b1` review setups

### 4. Keep Review Schema Stable

The final baseline-review payload for `b1` keeps the current field set:

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`
- `total_score`
- `signal_type`
- `verdict`
- `comment`

No new structured fields such as `weekly_wave`, `daily_wave`, `macd_reasoning`, or `signal_reasoning` are added to baseline output.

Wave interpretation must be represented inside `comment`.

### 5. Change B1 MACD Phase Semantics

For `b1`, `macd_phase` will no longer mean generic MACD strength.

It will mean wave-quality / setup-readiness instead.

Recommended scoring shape:

- `5.0`: weekly/daily wave combination fully matches the reused preferred setup
- `4.0`: wave context is constructive but slightly less ideal
- `3.0`: neutral / incomplete / insufficiently confirmed structure
- `2.0`: only part of the wave context is acceptable
- `1.0`: wave context is clearly poor or contradictory

Exact thresholds may differ in implementation, but tests must preserve the intent:

- short or incomplete history should stay conservative
- ideal wave combinations should score highest
- invalid or rejected wave combinations should score lower

### 6. Count MACD Phase In B1 Total Score

`compute_method_total_score("b1", scores)` must now include `macd_phase`.

This changes `b1` review semantics:

- baseline `total_score` changes
- baseline `PASS` / `WATCH` / `FAIL` distribution may change
- merged review scores after `review-merge` may change

This is intentional and should be treated as part of the feature, not as an incidental regression.

### 7. Add B1 Wave Context To Review Tasks

During `review --method b1`, task payloads in `llm_review_tasks.json` should include:

- `weekly_wave_context`
- `daily_wave_context`
- `wave_combo_context`

These fields must be generated from the same deterministic wave analysis used by baseline review.

They are text-only helper context and must not change the final merged JSON schema.

### 8. Split Prompt Contracts

Add:

- `.agents/skills/stock-select/references/prompt-b1.md`

Then update review resolver wiring so:

- `b1` uses `prompt-b1.md`
- `b2` keeps `prompt-b2.md`
- `hcr` continues using the generic prompt path

`prompt-b1.md` must instruct the LLM reviewer:

- weekly wave context is system-provided and must not be invented from an unseen weekly chart
- daily wave context is also system-provided and should be checked against the visible daily chart
- `macd_reasoning` must mention weekly and daily wave interpretation
- `signal_reasoning` must mention whether the combination fits the preferred setup
- `comment` must compress the same wave conclusion into one short Chinese sentence

The output JSON contract remains the same as the current review-merge validator expects.

### 9. Review Resolver Changes

`src/stock_select/review_resolvers.py` should route:

- `b1` -> dedicated `b1` reviewer + `prompt-b1.md`
- `b2` -> dedicated `b2` reviewer + `prompt-b2.md`
- others -> existing default path

This prevents `b1`-specific wave semantics from leaking into `hcr`.

### 10. Tests

Update or add tests in these areas:

#### B1 reviewer tests

- `comment` mentions weekly and daily wave conclusion
- baseline output schema does not expand
- `macd_phase` follows wave-readiness semantics
- `total_score` for `b1` now includes `macd_phase`

#### Review orchestrator tests

- `compute_method_total_score("b1", ...)` now includes `macd_phase`
- `build_review_payload()` can carry extra wave context for `b1`

#### Resolver tests

- `b1` now resolves to a dedicated reviewer and `prompt-b1.md`
- `hcr` keeps the generic default prompt path

#### CLI review tests

- `review --method b1` writes `llm_review_tasks.json` with wave-context fields
- `prompt-b1.md` includes required weekly/daily wave language
- existing `b1` review generation still works with unchanged final merged schema

## Risks

- `b1` review score distributions will change because `macd_phase` is now counted
- old exact-score tests for `b1` review will need recalculation
- a shared generic prompt can no longer safely represent both `b1` and `hcr`, so prompt routing must be separated cleanly

## Migration Strategy

Implement in this order:

1. add the dedicated `b1` reviewer and resolver wiring
2. change `b1` total-score calculation to include `macd_phase`
3. add `b1` review-task wave context and `prompt-b1.md`
4. update tests
5. align docs
