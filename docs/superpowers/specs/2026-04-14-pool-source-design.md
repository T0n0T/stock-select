# Pool Source Design

## Goal

Add a CLI option that lets `screen` and `run` choose the screening stock pool source, so the existing top-turnover pool can be replaced by the per-method `record-watch` pool.

The change must apply consistently to all currently supported screening methods:

- `b1`
- `b2`
- `hcr`

The default behavior must remain unchanged for existing users who do not pass the new option.

## Scope

In scope:

- add a new pool-source option to `screen`
- add the same pool-source option to `run`
- make `b1`, `b2`, and `hcr` all consume a shared pool-resolution layer
- keep `turnover-top` as the default source
- allow `record-watch` to replace the top-turnover pool for both end-of-day and intraday screening
- preserve existing candidate, chart, review, and render artifact formats
- add automated coverage for the new CLI contract and method behavior changes

Out of scope:

- adding the option to `chart`
- adding the option to `review`
- adding the option to `record-watch`
- adding the option to `review-merge`
- adding the option to `render-html`
- changing the watch-pool CSV schema
- adding a separate top-N parameter for pool size in this change

## Current Problem

The current CLI hard-codes a single stock-pool source for screening:

- `b1` uses the top-turnover pool
- `b2` uses the top-turnover pool, including its phase-one warmup gate
- `hcr` currently bypasses pool filtering in its end-of-day path

This creates two issues:

1. Users cannot run the normal screening workflow against the curated `record-watch` stock pool.
2. Pool behavior is inconsistent across methods, especially for `hcr`.

A direct method-specific patch would solve only the immediate request and would keep pool selection logic scattered across the CLI. The design should instead make pool source a shared screening concern.

## Command Contract

### 1. New CLI Option

Add this option to:

- `stock-select screen`
- `stock-select run`

Option shape:

- `--pool-source turnover-top|record-watch`

Default:

- `turnover-top`

The option should be accepted for both end-of-day and intraday runs, because `screen --intraday` and `run --intraday` already reuse the same command entrypoints.

### 2. Commands That Do Not Change

Do not add `--pool-source` to:

- `chart`
- `review`
- `record-watch`
- `review-merge`
- `render-html`

Those commands continue to consume the runtime artifacts created by `screen` or `run` without needing to know which stock pool produced them.

### 3. Method Coverage

The new pool-source contract applies to:

- `b1`
- `b2`
- `hcr`

This is an intentional behavior change for `hcr`. After this change, `hcr` should also run against a resolved stock pool instead of evaluating every prepared symbol.

## Pool Semantics

### 1. `turnover-top`

`turnover-top` keeps the current default behavior:

- build a per-trade-date pool from prepared symbol data using `turnover_n`
- keep only the top `5000` symbols for the target trade date
- run the selected method only on that subset

This source should now apply uniformly to `b1`, `b2`, and `hcr`.

### 2. `record-watch`

`record-watch` resolves the screening pool from:

`runtime/watch_pool/<method>.csv`

Resolution rules:

1. load the CSV for the selected method
2. keep rows where `pick_date <= current screening date`
3. collapse duplicate symbols by keeping only the most recent `pick_date`
4. if multiple rows still tie for the same symbol and date, keep the last row in CSV order
5. return the resulting symbol set as the screening pool

This source does not apply any additional top-5000 cutoff. It fully replaces the top-turnover pool.

### 3. Final Prepared-Data Intersection

Regardless of source, the resolved symbol list must be intersected with the keys present in `prepared_by_symbol` before strategy execution.

This avoids failures when:

- the watch-pool CSV contains stale symbols not present in the fetched market window
- the prepared cache or current run lacks data for one or more pool symbols

The screening engine should operate only on symbols that are both:

- in the resolved stock pool
- present in prepared market data

## Implementation Shape

### 1. Shared Pool Resolver

Introduce a small shared pool-resolution layer instead of embedding source-specific conditionals directly in each command branch.

Recommended responsibilities:

- validate and normalize the `pool_source` CLI value
- resolve pool codes for a given `method`, `pick_date`, `runtime_root`, and `prepared_by_symbol`
- keep source-specific logic behind one interface
- emit consistent progress metadata such as source name and resolved pool size

The exact helper names may vary, but the implementation should keep this boundary explicit.

### 2. CLI Responsibilities

Keep option parsing and orchestration in `src/stock_select/cli.py`.

`cli.py` should:

- parse `--pool-source`
- pass the normalized source into end-of-day and intraday screen flows
- use the shared resolver before invoking any strategy-specific screen function
- preserve existing output payload shapes

`cli.py` should not duplicate CSV filtering rules or source-specific ranking logic in multiple places.

### 3. Watch-Pool Helpers

Reuse `src/stock_select/watch_pool.py` for CSV loading, and extend it with focused helper logic for screening-time selection if needed.

The screening flow should not manually manipulate watch-pool CSV rows inline inside command handlers if a helper can keep that logic isolated and testable.

## Method-Specific Screening Flow

### 1. `b1`

`b1` should:

- resolve the stock pool using the selected source
- subset prepared symbols to the resolved pool
- run the existing `b1` screen on that subset

No other `b1` behavior changes are required.

### 2. `b2`

`b2` keeps its two-phase structure, but the entry pool changes:

1. resolve the stock pool using the selected source
2. restrict phase-one prepared data to that pool
3. run the existing non-MACD prefilter on the pooled subset
4. fetch warmup history only for the phase-one survivors
5. run the full `b2` screen on the warmed subset

Important consequence:

- when `pool-source=record-watch`, `b2` warmup must only fetch symbols from the resolved watch pool that survive phase one
- the implementation must not silently reintroduce the top-turnover pool ahead of `record-watch`

### 3. `hcr`

`hcr` should now also respect the resolved pool source.

That means:

- `hcr --pool-source turnover-top` uses the same top-5000 pool concept as `b1` and `b2`
- `hcr --pool-source record-watch` uses the method-specific watch pool

This is a deliberate behavior change from the prior design where `hcr` evaluated all prepared symbols.

## `run` Command Behavior

`run` should remain a thin orchestration wrapper.

Required change:

- accept `--pool-source`
- pass it through to the internal screening step

The downstream stages:

- `chart`
- `review`
- `review-merge`
- `render-html`

should remain unchanged. They operate on the candidate artifacts already produced by the selected pool source.

## Error Handling

### 1. Invalid Source

If the CLI receives an unsupported `--pool-source` value, it should fail as a normal option validation error.

### 2. Missing Watch Pool

If `pool-source=record-watch` and the expected CSV file does not exist, fail with a clear CLI error naming the missing file.

### 3. Empty Effective Watch Pool

If the watch-pool CSV exists but contains no effective rows for the screening date after applying:

- `pick_date <= screening date`
- per-symbol recency collapse
- prepared-data intersection

fail with a clear CLI error instead of silently running against an empty symbol set.

### 4. Turnover Pool

Keep existing default behavior for `turnover-top`.

If a method resolves to an empty top-turnover pool because prepared data is empty or malformed, the current behavior may continue. This design does not require introducing a new hard failure for that case.

## Progress Reporting

Add explicit progress lines that identify:

- `pool_source`
- the pool size after source resolution
- for `record-watch`, the watch-pool path being used

This is necessary so users can later confirm whether a candidate file came from:

- the default top-turnover pool
- the recorded watch pool

## Testing

Add or update automated tests to cover at minimum:

- `screen --pool-source turnover-top` preserves existing `b1` behavior
- `screen --pool-source turnover-top` preserves existing `b2` behavior
- `screen --pool-source turnover-top` now constrains `hcr` by the top-turnover pool
- `screen --pool-source record-watch` uses watch-pool rows for `b1`
- `screen --pool-source record-watch` uses watch-pool rows for `b2`
- `screen --pool-source record-watch` uses watch-pool rows for `hcr`
- `screen --pool-source record-watch` rejects a missing watch-pool CSV
- `screen --pool-source record-watch` rejects a watch-pool CSV with no effective symbols for the pick date
- `run --pool-source ...` passes the source through to the internal screening step
- `b2` warmup fetches only pool-resolved symbols under `record-watch`
- intraday `screen` still honors the selected pool source
- intraday `run` still honors the selected pool source

## Success Criteria

The feature is successful when all of the following are true:

- users can switch `screen` and `run` between `turnover-top` and `record-watch`
- existing users who omit the new option see no behavior change
- `b1`, `b2`, and `hcr` all respect the same pool-source contract
- `b2` warmup remains efficient and only fetches symbols that survive the selected pool gate
- watch-pool selection failures are explicit and easy to diagnose
- downstream artifacts and non-screening commands remain compatible without additional options
