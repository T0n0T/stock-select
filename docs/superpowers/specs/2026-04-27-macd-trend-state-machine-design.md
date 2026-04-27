# MACD Trend State Machine Design

## Goal

Replace the current MACD wave classifier with a strict MACD trend state machine for both daily and weekly analysis.

The new model no longer exposes or depends on labels such as `wave1`, `wave3`, `wave2_end`, or `wave4_end`. It describes the current MACD position as an upward trend segment, downward trend segment, ended segment, idle state, or invalid state, with explicit flags for early upward trend and top-divergence risk.

## Background

The current implementation in `src/stock_select/analysis/macd_waves.py` is a heuristic classifier. It classifies weekly data into `wave1`, `wave2`, `wave3`, or `invalid`, and daily data into pullback-end labels such as `wave2_end` and `wave4_end`.

That model differs from the desired state machine:

- it does not require an underwater golden cross followed by both `DIF` and `DEA` moving above zero before starting the trend segment
- it does not advance through alternating above-water golden/dead crosses as explicit states
- it does not end the active segment on `DIF` crossing below zero
- it mixes wave-count terms with setup-quality terms

This redesign makes MACD phase detection deterministic and easier to explain in review output.

## Scope

In scope:

- add a strict MACD trend state machine shared by daily and weekly analysis
- replace daily and weekly MACD wave judgment in screening and review call sites
- remove user-facing `wave1`, `wave3`, `wave2_end`, and `wave4_end` wording from baseline comments and LLM task context
- add explicit rising-initial and top-divergence flags
- keep current review artifact schemas stable where practical

Out of scope:

- changing non-MACD score dimensions
- changing chart rendering
- changing the LLM JSON schema
- adding visual divergence based on price highs in this pass
- tuning divergence thresholds beyond the first strict definition

## State Model

The analysis layer should expose a new result object, named for example `MacdTrendState`:

```python
@dataclass(frozen=True)
class MacdTrendState:
    phase: str
    direction: str
    is_rising_initial: bool
    is_top_divergence: bool
    bars_in_phase: int
    phase_index: int
    reason: str
    metrics: dict[str, float | int | bool | str]
```

`phase` values:

- `idle`: the current sequence has not completed the startup condition
- `rising`: the active segment is an above-water upward MACD segment
- `falling`: the active segment is an above-water downward MACD segment
- `ended`: the previous active segment ended because `DIF` crossed below zero
- `invalid`: the result is unreliable because history is too short or MACD churn is excessive

`direction` values:

- `neutral` for `idle`, `ended`, and `invalid`
- `rising` for `phase == "rising"`
- `falling` for `phase == "falling"`

`phase_index` records the active above-water alternating segment count inside the current MACD cycle. It is for diagnostics and score mapping only; review comments should not call it first wave, third wave, or similar wave-count language.

## State Transitions

The state machine scans MACD rows from oldest to newest. It starts from `idle` and waits for a valid cycle startup.

Startup condition:

1. underwater golden cross: previous `DIF <= DEA`, current `DIF > DEA`, and current `DIF < 0` and `DEA < 0`
2. after that cross, both lines must move above zero: current `DIF > 0` and `DEA > 0`
3. when both lines are above zero, enter `rising`

Running transitions:

- `rising -> falling`: above-water dead cross, meaning previous `DIF >= DEA`, current `DIF < DEA`, and current `DIF > 0` and `DEA > 0`
- `falling -> rising`: above-water golden cross, meaning previous `DIF <= DEA`, current `DIF > DEA`, and current `DIF > 0` and `DEA > 0`
- active `rising` or `falling` -> `ended`: current `DIF < 0`
- after `ended`, the machine returns to waiting for the next underwater golden cross startup

If the machine ends and later finds a new startup sequence, the later active sequence becomes the current result. The final returned state always describes the latest cycle available at `pick_date`.

## Rising Initial Flag

The same threshold is used for daily and weekly analysis.

- `RISING_INITIAL_BARS = 3`
- `is_rising_initial = True` when `phase == "rising"` and `bars_in_phase <= 3`
- otherwise `is_rising_initial = False`

`bars_in_phase` starts at `1` on the bar that enters the current phase.

## Top-Divergence Flag

Top divergence is defined by weakening MACD line spread during an upward segment.

- `spread = DIF - DEA`
- `is_top_divergence = True` when `phase == "rising"` and current `spread < previous_spread`
- otherwise `is_top_divergence = False`

This pass intentionally uses a single-bar spread contraction with no minimum threshold. If review output becomes too noisy, a later pass can add consecutive contraction or percentage-shrink requirements.

## Daily And Weekly Interfaces

The public analysis API should add:

```python
classify_daily_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState
classify_weekly_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState
```

Daily input uses the existing daily close series through `pick_date`.

Weekly input first resamples daily data to `W-FRI` close, then computes MACD and runs the same state machine.

The old functions `classify_daily_macd_wave()` and `classify_weekly_macd_wave()` may remain as temporary compatibility wrappers, but production call sites for screening and review should migrate to the trend-state API and stop depending on old wave labels.

## Screening Integration

`dribull` currently accepts candidates only when weekly labels are `wave1` or `wave3` and daily labels are `wave2_end` or `wave4_end`.

The redesigned MACD gate should use trend-state combinations instead:

- preferred: weekly `rising`, daily `rising`, daily `is_rising_initial`, and no top divergence
- acceptable watch/setup context: weekly `rising` and daily `falling`, representing a pullback inside a larger upward MACD cycle
- reject: weekly or daily `invalid`
- reject: weekly or daily `ended`
- reject or strongly penalize: weekly and daily both `falling`
- reject or strongly penalize: any top-divergence flag when the method requires a clean continuation signal

The first implementation should keep this conservative. It should prefer fewer candidates over admitting states that the new model calls ended, invalid, or divergent.

## Review Integration

Baseline review comments and LLM task context should describe MACD in trend terms:

- weekly upward segment / downward segment / idle / ended / invalid
- daily upward segment / downward segment / idle / ended / invalid
- upward initial stage when `is_rising_initial` is true
- top-divergence risk when `is_top_divergence` is true

Existing task context keys such as `weekly_wave_context`, `daily_wave_context`, and `wave_combo_context` may remain for schema compatibility in the first pass. Their values should no longer contain old wave labels or wave-count language.

Prompt text that asks reviewers to reason about `wave1`, `wave3`, `wave2_end`, or `wave4_end` should be rewritten to ask for MACD trend-segment reasoning instead.

## MACD Phase Score Mapping

The first score mapping should be simple and shared enough to remain explainable:

- `5`: weekly and daily are both `rising`, daily is in the rising initial stage, and neither has top divergence
- `4`: weekly and daily are both `rising`, daily is not initial, and neither has top divergence
- `3`: weekly is `rising` and daily is `falling`, representing a pullback inside a larger upward cycle
- `2`: top-divergence risk exists, or weekly is `falling` while daily is `rising`
- `1`: either state is `invalid` or `ended`, or weekly and daily are both `falling`

Method-specific reviewers may cap or slightly adjust these scores, but they should not reintroduce old wave-count labels.

## Error Handling And Edge Cases

History that is too short to compute a meaningful MACD state should return `invalid` with a clear reason and metrics showing the available period count.

Recent excessive MACD churn should return `invalid`. The existing churn filter may be reused initially, but it should operate on trend-state reliability rather than old wave labels.

Rows after `pick_date` must be ignored.

If an active cycle ends and no later valid startup sequence appears, the final state should be `ended`.

If an active cycle ends and a later valid startup appears, the final state should describe the later cycle.

## Testing Strategy

State-machine tests should be written before implementation and should verify:

- underwater golden cross alone keeps the state `idle`
- both `DIF` and `DEA` moving above zero after underwater golden cross enters `rising`
- above-water dead cross changes `rising` to `falling`
- above-water golden cross changes `falling` to `rising`
- `DIF < 0` ends the active cycle
- a new underwater startup after an ended cycle becomes the latest active cycle
- the first three bars of a rising segment set `is_rising_initial`
- a rising segment with shrinking `DIF - DEA` sets `is_top_divergence`
- daily and weekly classifiers expose the same state semantics

Integration tests should verify:

- `dribull` screening no longer checks old wave labels
- `b1`, `b2`, and `dribull` review comments no longer mention old wave labels
- LLM task context no longer contains `wave1`, `wave3`, `wave2_end`, or `wave4_end`
- `macd_phase` follows the new trend-state score mapping

## Rollout Notes

This is a behavior change with a broad blast radius. It should be implemented with focused tests around the analysis layer first, then migrated through screening, review scoring, comments, CLI task context, and prompts.

The implementation should not delete old compatibility functions until all internal call sites have moved to the new trend-state API and tests prove the old labels are no longer used in outputs.
