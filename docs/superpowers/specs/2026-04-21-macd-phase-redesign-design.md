# MACD Phase Baseline Redesign

## Goal

Redesign the baseline `macd_phase` scoring so that:

- `b1`, `b2`, `dribull`, and `hcr` no longer overload the same score with incompatible strategy meanings.
- baseline comments, MACD validity, numeric scores, and final verdicts stay internally consistent.
- obviously invalid daily MACD states can no longer receive high strategy-aligned scores.
- the implementation can be rolled out incrementally without breaking the current runtime artifact schema.

This spec only redesigns the `macd_phase` dimension. The other baseline score fields stay unchanged in the first implementation pass.

## Current Problems

The current baseline behavior has three major issues.

1. `b1` can assign a high `macd_phase` score when the weekly wave is constructive even if the daily wave is already `invalid`.
2. `dribull` baseline review currently reuses the `b2` reviewer even though the trading intent is not identical.
3. `comment`, `macd_phase`, and `verdict` are derived from partially different logic paths, so one stock can be described as “not符合 b1” while still receiving a strong baseline score or even `PASS`.

The result is that baseline outputs are hard to trust and hard to explain.

## Scope

In scope:

- redesign the MACD state model used by baseline review
- redesign method-specific `macd_phase` score mapping for `b1`, `b2`, `dribull`, and `hcr`
- add strategy-aware MACD gating for final baseline verdicts
- preserve current artifact fields while allowing additive metadata

Out of scope:

- changing screening selection logic
- changing chart rendering
- changing LLM review schema
- changing non-MACD baseline fields or score weights in the first pass

## Design Principles

- Use one shared daily MACD state machine for all methods.
- Keep strategy differences in the score-mapping layer, not in duplicated low-level signal detection.
- Treat `5` as rare and strategy-specific.
- Keep `3` as a true observation score, not a disguised buy score.
- Enforce hard caps so invalid daily MACD states cannot drift into high scores.
- Introduce verdict gating only after MACD scoring is stabilized and tested.

## Architecture

The redesign introduces two layers.

### Layer 1: Shared MACD State Detection

The analysis layer should produce a shared daily MACD state object that captures the actual MACD repair or deterioration status without embedding any method-specific trading preference.

Proposed daily state values:

- `hard_invalid`
- `deteriorating`
- `repair_candidate`
- `early_recross`
- `wave2_end_valid`
- `wave4_end_valid`
- `overextended`

This replaces the current practical behavior where too many different shapes collapse into `invalid`.

### Layer 2: Method-Specific Score Mapping

Each review method consumes:

- weekly wave classification
- daily MACD state
- daily MACD metrics

and maps that into a `macd_phase` score from `1` to `5`.

This keeps the methods meaningfully different while preserving one explainable shared signal engine.

## Shared Daily MACD State Model

The new daily MACD state object should contain:

- `state`
- `valid_for_pullback`
- `reason`
- `metrics`

Proposed metrics:

- `third_wave_gain`
- `bullish_now`
- `negative_hist_shrinking`
- `positive_hist_shrinking`
- `converging`
- `recent_cross_up`
- `recent_cross_down`
- `bars_since_cross`
- `bars_since_hist_peak`

The state detection order should be deterministic and mutually exclusive.

### Suggested Evaluation Order

1. If history is too short or recent MACD churn is excessive:
   classify as `hard_invalid`.
2. If `dif <= dea`:
   - if histogram is still worsening, classify as `deteriorating`
   - if histogram is shrinking and lines are converging, classify as `repair_candidate`
   - if that same repair also satisfies valid pullback-end conditions, upgrade to `wave2_end_valid` or `wave4_end_valid`
3. If `dif > dea`:
   - if the recross is too early or too abrupt, classify as `early_recross`
   - if the shape is valid as a completed second-wave repair, classify as `wave2_end_valid`
4. If the estimated third-wave gain exceeds the method-independent overextension limit:
   classify as `overextended`

The overextension check is a demotion rule, not a late-only branch. Implementation should allow it to override an otherwise constructive repair state whenever the move is already too extended for the intended setup.

### Meaning of States

- `hard_invalid`
  Structural noise, churn, or insufficient data. No strategy should interpret this positively.
- `deteriorating`
  Pullback remains in progress; downside momentum is not yet repaired.
- `repair_candidate`
  Repair has started but is not yet mature enough to count as a completed pullback.
- `early_recross`
  MACD has returned to the bullish side too early to qualify as a clean left-biased pullback end.
- `wave2_end_valid`
  A valid second-wave-style daily pullback completion.
- `wave4_end_valid`
  A valid fourth-wave-style daily pullback completion under controlled extension.
- `overextended`
  The repair exists mechanically, but the move is already too extended for left-biased interpretation.

## Unified Score Semantics

All methods should share the same meaning of score values.

- `5`: textbook match for the strategy’s preferred MACD setup
- `4`: good but not ideal; tradable, not perfect
- `3`: neutral observation; some constructive evidence but not a mature setup
- `2`: early repair or partial fit only
- `1`: invalid or opposite to the strategy’s intent

## Method-Specific Mapping

### B1

`b1` is the strictest left-biased method. It should heavily prefer a weekly constructive context plus a genuinely completed daily second-wave or shallow fourth-wave pullback.

Suggested mapping:

- `5`
  - weekly `wave1` or `wave3`
  - daily `wave2_end_valid`
- `5`
  - weekly `wave1` or `wave3`
  - daily `wave4_end_valid`
  - and `third_wave_gain <= 0.15`
- `4`
  - weekly `wave1` or `wave3`
  - daily `wave4_end_valid`
  - and `0.15 < third_wave_gain <= 0.30`
- `4`
  - weekly `wave1` or `wave3`
  - daily `repair_candidate`
  - and the repair is strong enough to be close to completion
- `3`
  - weekly `wave1` or `wave3`
  - daily `early_recross`
- `3`
  - weekly `wave2`
  - daily valid repair
- `2`
  - daily `repair_candidate`
  - but weekly context is not `wave1` or `wave3`
- `1`
  - daily `hard_invalid`
  - daily `deteriorating`
  - daily `overextended`

Hard caps:

- daily `hard_invalid`, `deteriorating`, or `overextended`: max `1`
- daily `early_recross`: max `3`
- weekly not in `{wave1, wave3}`: max `3`

### B2

`b2` is still left-biased but should be more tolerant of constructive repair that is slightly more mature or slightly more right-sided than `b1`.

Suggested mapping:

- `5`
  - weekly `wave1` or `wave3`
  - daily `wave2_end_valid`
- `5`
  - weekly `wave1` or `wave3`
  - daily `wave4_end_valid`
  - and `third_wave_gain <= 0.30`
- `4`
  - weekly `wave1` or `wave3`
  - daily `repair_candidate`
- `4`
  - weekly `wave1` or `wave3`
  - daily `early_recross`
  - and the recross is controlled rather than exhausted
- `3`
  - weekly `wave2`
  - daily valid repair
- `3`
  - weekly constructive but daily neutral bullish continuation rather than a clear pullback-end
- `2`
  - weekly invalid but daily `repair_candidate`
- `2`
  - daily `overextended`
- `1`
  - daily `hard_invalid`
  - daily `deteriorating`

Hard caps:

- daily `hard_invalid` or `deteriorating`: max `1`
- daily `overextended`: max `2`
- weekly invalid: max `2`

### Dribull

`dribull` should stop blindly reusing the `b2` scoring table. It is closer to a trend-internal pullback and relaunch pattern and should prefer fourth-wave-style repairs more strongly than `b2`.

Suggested mapping:

- `5`
  - weekly `wave3`
  - daily `wave4_end_valid`
  - and retreat quality remains strong
- `5`
  - weekly `wave1`
  - daily `wave2_end_valid`
  - and position remains sufficiently left-biased
- `4`
  - weekly `wave3`
  - daily `repair_candidate`
- `4`
  - weekly `wave1` or `wave3`
  - daily valid pullback end
  - but with weaker volume/support quality
- `3`
  - weekly `wave1` or `wave3`
  - daily `early_recross`
- `3`
  - weekly `wave2`
  - daily `wave4_end_valid`
- `2`
  - daily `repair_candidate`
  - but retreat quality is poor
- `2`
  - daily `overextended`
- `1`
  - daily `hard_invalid`
  - daily `deteriorating`

Hard caps:

- daily `hard_invalid` or `deteriorating`: max `1`
- weekly invalid: max `1`
- weekly `wave2`: max `3`

### HCR / Default

`hcr` should not be tightly wave-gated. It should remain a momentum-repair quality score rather than a weekly/daily wave-combination score.

Suggested mapping:

- `5`
  - recent bullish recross
  - histogram strengthening
  - positive momentum intact
  - line separation not yet overextended
- `4`
  - bullish side confirmed
  - histogram improving
  - healthy but not fresh
- `3`
  - neutral
  - or mixed but not broken
- `2`
  - below zero line but shrinking downside pressure
- `1`
  - `hard_invalid`
  - fresh bearish transition
  - obvious momentum deterioration

Hard caps:

- `hard_invalid`: `1`
- `deteriorating`: max `2`
- `early_recross`: max `4`

## Verdict Gating

Changing `macd_phase` alone will improve scores but will not fully remove false `PASS` outputs in wave-aware methods. A second-phase rollout should therefore add a strategy MACD gate.

Proposed gate outcomes:

- `pass_ok`
- `watch_only`
- `fail_only`

Suggested behavior:

- `b1`
  only weekly `wave1/wave3` plus daily `wave2_end_valid`, `wave4_end_valid`, or strong `repair_candidate` may remain eligible for `PASS`
- `b2`
  can allow `WATCH` for broader constructive states, but should not `PASS` daily invalid structures
- `dribull`
  should require a strong trend-context plus a valid repair state to remain `PASS` eligible
- `hcr`
  should not use the same wave gate

This gate should be introduced after the new `macd_phase` scoring has been verified.

## Implementation Strategy

Rollout should happen in four steps.

### Step 1: Add New Daily MACD State Detection

- add `DailyMacdState`
- add `classify_daily_macd_state()`
- keep `classify_daily_macd_wave()` as a compatibility wrapper

### Step 2: Centralize MACD Score Mapping

- add a shared `map_macd_phase_score(method, weekly_wave, daily_state)` function
- route all reviewers through this entry point

### Step 3: Split Dribull Review From B2

- add a dedicated `dribull` reviewer
- keep shared low-level MACD state detection
- allow different strategy score mapping

### Step 4: Add Verdict Gate

- add method-aware MACD eligibility gating
- apply this only after score behavior has been stabilized

## Compatibility

Keep existing fields in baseline review payloads unchanged:

- `macd_phase`
- `total_score`
- `signal_type`
- `verdict`
- `comment`

Additive fields are allowed:

- `daily_macd_state`
- `weekly_macd_state`
- `macd_gate`
- `macd_metrics`

This preserves artifact compatibility for `summary.json`, LLM task generation, and HTML export consumers.

## Testing Plan

### Unit Tests

- shared daily MACD state classification covers all new states
- `b1` never awards high score to daily invalid states
- `dribull` no longer behaves identically to `b2`
- verdict-gate tests prevent “comment says invalid but verdict is PASS”

### Replay Tests

- replay at least 20 historical review dates
- compare distribution of `PASS`, `WATCH`, and `FAIL`
- inspect all cases where `PASS` disappears after the redesign

### Human Spot Checks

For each method:

- 10 examples scored `5`
- 10 examples scored `4`
- 10 examples scored `1`

Verify that examples match method intent, especially for `b1` and `dribull`.

## Risks

- `b1` scores will likely shift downward substantially; this is expected.
- `dribull` output will diverge from `b2` after reviewer separation.
- if verdict gating is enabled too early, `PASS` counts may collapse before score calibration is validated.

## Recommendation

Proceed with the redesign in two phases:

1. shared MACD state model plus method-aware `macd_phase` remapping
2. strategy verdict gating once replay data confirms the score distribution is reasonable

This sequence fixes the current score inconsistency without forcing a risky all-at-once behavior change.
