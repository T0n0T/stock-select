# Intraday Screen Design

## Goal

Add a real-time screening mode to the existing `stock-select` CLI so a user can manually trigger one intraday B1 run for the current trading day using:

- the previous trading day's confirmed `daily_market` history from PostgreSQL
- the current trading day's live market snapshot from `Tushare rt_k`

The design must reuse the existing `screen`, `chart`, and `review` commands and should not introduce a separate `intraday-*` command family.

## Scope

In scope:

- add `--intraday` to `screen`, `chart`, and `review`
- use `Tushare rt_k` as the real-time snapshot source
- build a temporary current-day daily bar from the live snapshot
- reuse the existing B1 preparation and screening pipeline
- reuse the existing `candidates`, `charts`, `reviews`, and `prepared` runtime roots
- make `chart --intraday` and `review --intraday` automatically consume the latest intraday `screen` output

Out of scope:

- writing intraday data back to `stock-cache` or `daily_market`
- minute-bar ingestion
- automatic polling or continuous refresh
- introducing separate `intraday-chart` or `intraday-review` commands
- changing the baseline B1 logic itself

## Current Problem

The current standalone workflow only supports end-of-day analysis. `screen` reads one year of confirmed rows from PostgreSQL `daily_market`, and both `chart` and `review` assume the candidate file is keyed by a single `pick_date`.

This prevents users from running the same B1 logic during the trading session, even when they only need a one-shot manual intraday analysis at the time the command succeeds.

## Design

### 1. CLI Contract

Add a boolean option to `screen`, `chart`, and `review`:

`--intraday/--no-intraday`

Default:

`--no-intraday`

Intraday mode rules:

- `--intraday` and `--pick-date` are mutually exclusive
- when `--intraday` is set, the command derives the effective trade date from the current market day context rather than a user-supplied `pick_date`
- `screen --intraday` is the only command that talks to `Tushare rt_k`
- `chart --intraday` and `review --intraday` operate on the latest intraday candidate artifact already produced by `screen --intraday`

Non-intraday behavior remains unchanged.

### 2. Time Semantics

Intraday mode does not accept an explicit `as_of` parameter.

Instead, the run timestamp is defined as the instant when `screen --intraday` successfully receives a valid `rt_k` snapshot. This timestamp becomes the runtime identifier for the entire intraday run.

Use:

- `run_id = fetched_at`

Format:

- ISO 8601 timestamp safe for filenames
- example: `2026-04-09T11-31-08+08-00`

This `run_id` ties together the candidate file, prepared cache, chart directory, and review directory for one intraday execution.

### 3. Runtime Layout

Intraday outputs reuse the existing runtime roots and differ only by naming.

Expected paths:

- `runtime/candidates/<run_id>.json`
- `runtime/prepared/<run_id>.pkl`
- `runtime/charts/<run_id>/`
- `runtime/reviews/<run_id>/`

Examples:

- `candidates/2026-04-09T11-31-08+08-00.json`
- `prepared/2026-04-09T11-31-08+08-00.pkl`
- `charts/2026-04-09T11-31-08+08-00/000001.SZ_day.png`
- `reviews/2026-04-09T11-31-08+08-00/summary.json`

No additional `intraday_*` directory roots are introduced.

### 4. Data Source Contract

Intraday mode uses two data sources:

1. PostgreSQL `daily_market`
2. `Tushare rt_k`

Historical market rows continue to come from PostgreSQL. Intraday rows come only from `rt_k` and are treated as temporary input for the current run.

Minimum normalized `rt_k` fields required by the screening pipeline:

- `ts_code`
- `name`
- `open`
- `high`
- `low`
- `close`
- `vol`
- `amount`
- `trade_time`

The implementation should normalize provider-specific column names at the boundary so the rest of the code only sees the internal shape.

### 5. Intraday Market Overlay

`screen --intraday` should fetch approximately one year of history ending at the previous trading day, then append or override one temporary current-day daily row per symbol from the live `rt_k` snapshot.

Current-day row mapping:

- `trade_date`: current trading day
- `open`: snapshot open
- `high`: snapshot high
- `low`: snapshot low
- `close`: snapshot latest price
- `vol`: snapshot cumulative volume

This temporary row is only used in memory for the current intraday run and in the serialized prepared cache. It must not be written back into PostgreSQL.

The resulting combined market frame should then flow through the existing `_prepare_screen_data()` and `run_b1_screen_with_stats()` path without changing the B1 logic.

### 6. Prepared Cache Contents

Intraday runs should store a prepared cache under:

`runtime/prepared/<run_id>.pkl`

The payload should include at minimum:

- `mode = intraday_snapshot`
- `run_id`
- `trade_date`
- `fetched_at`
- `prepared_by_symbol`
- metadata needed to validate compatibility with the current B1 configuration

The cache may also include the normalized snapshot rows or overlay frame if that materially simplifies `chart --intraday`.

This file is the canonical source for later intraday `chart` and debugging reuse. No separate snapshot JSON is required.

### 7. Candidate Output

The intraday candidate file should follow the existing candidate payload style with additional metadata:

- `mode = intraday_snapshot`
- `method = b1`
- `trade_date`
- `fetched_at`
- `run_id`
- `source = tushare_rt_k`
- `candidates`

The payload must make it obvious that the result is based on a temporary intraday snapshot rather than an end-of-day confirmed close.

### 8. Latest Intraday Artifact Resolution

`chart --intraday` and `review --intraday` should not accept `pick_date`.

Instead they should resolve the latest intraday candidate by scanning:

`runtime/candidates/*.json`

and selecting the most recent payload whose metadata marks it as:

- `mode = intraday_snapshot`

If no intraday candidate exists, the command should fail with a clear error and must not fall back to end-of-day candidate files.

Once the latest intraday candidate is selected:

- `chart --intraday` writes to `runtime/charts/<run_id>/`
- `review --intraday` writes to `runtime/reviews/<run_id>/`

### 9. Chart Behavior

`chart --intraday` should reuse the existing daily chart rendering path. For each candidate:

1. load the latest intraday candidate payload
2. use the matching prepared cache for the same `run_id`
3. reconstruct the symbol history including the temporary current-day intraday row
4. render the same `<code>_day.png` artifact shape as the end-of-day flow

The chart remains a daily chart with the last candle representing the intraday snapshot state at `fetched_at`.

### 10. Review Behavior

`review --intraday` should reuse the existing baseline review structure and the current review runtime shape.

The only differences are:

- input comes from the latest intraday candidate file and corresponding `charts/<run_id>/`
- outputs go to `reviews/<run_id>/`
- metadata should preserve `mode`, `trade_date`, `fetched_at`, and `run_id`

The review interpretation remains a point-in-time intraday judgement, not an end-of-day confirmation.

### 11. Error Handling

Required behavior:

- if `Tushare rt_k` returns no usable rows, `screen --intraday` fails
- if the token is missing, `screen --intraday` fails with a clear configuration error
- if a symbol's snapshot row is missing required price or volume fields, that symbol is excluded from the overlay input
- if no intraday candidate file exists, `chart --intraday` and `review --intraday` fail explicitly
- if the matching intraday prepared cache for the resolved `run_id` is missing or invalid, `chart --intraday` fails explicitly rather than silently re-fetching real-time data

### 12. Compatibility

This design preserves the existing end-of-day workflow:

- `screen --method b1 --pick-date YYYY-MM-DD`
- `chart --method b1 --pick-date YYYY-MM-DD`
- `review --method b1 --pick-date YYYY-MM-DD`

Intraday mode is additive and should not alter any existing end-of-day output path or runtime naming.

## Testing

Required automated coverage:

- `screen --intraday` rejects simultaneous `--pick-date`
- `screen --intraday` normalizes `rt_k` rows into the expected internal columns
- intraday overlay correctly sets the temporary current-day `close` to the live snapshot price
- `screen --intraday` writes `candidates/<run_id>.json`
- `screen --intraday` writes `prepared/<run_id>.pkl`
- `chart --intraday` resolves the latest intraday candidate and writes `charts/<run_id>/`
- `review --intraday` resolves the latest intraday candidate and writes `reviews/<run_id>/`
- `chart --intraday` fails if no intraday candidate exists
- `review --intraday` fails if no intraday candidate exists
- end-of-day commands continue to pass existing tests unchanged

## Success Criteria

- a user can run `screen --intraday` during the session without providing `pick_date`
- the command uses the previous confirmed market history plus the current `Tushare rt_k` snapshot
- the resulting intraday candidate file is timestamped by the actual successful fetch time
- `chart --intraday` and `review --intraday` reuse the latest intraday candidate automatically
- no intraday data is written back to PostgreSQL
- the existing end-of-day workflow remains intact
