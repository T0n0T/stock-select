# Screen Reuse Design

## Goal

Reduce repeated `screen` runtime for the same `pick_date` by reusing previously computed outputs unless the user explicitly requests recomputation.

## Scope

This design changes only the `screen` execution path in the standalone `stock-select` CLI.

In scope:

- reuse an existing candidate output for the same `pick_date` when it already contains one or more candidates
- cache prepared screening data for the same `pick_date`
- allow explicit bypass via a CLI recompute flag
- emit clear progress messages when reuse occurs

Out of scope:

- cross-date incremental computation
- database-level materialized views
- broad refactors of B1 indicator implementations
- reuse of empty candidate outputs

## Current Problem

`screen` currently fetches roughly one year of market history and recomputes all per-symbol screening indicators on every run. This is expensive even when:

- the same `pick_date` has already produced a non-empty candidate file
- the same `pick_date` has already completed the expensive prepare phase

The result is unnecessary repeated database work and repeated CPU-heavy indicator calculation.

## Design

### 1. Candidate Short-Circuit

Before connecting to PostgreSQL, `screen` should check:

`runtime/candidates/<pick_date>.json`

If the file exists and `candidates` contains at least one item, `screen` should:

- return that file path immediately
- skip database access
- skip prepare work
- emit a progress line indicating candidate reuse

If the file exists but `candidates` is empty, `screen` should continue with the normal execution path. Empty outputs are not considered reusable because they may reflect incomplete or stale data.

### 2. Prepared Data Cache

Prepared per-symbol screening data should be cached under:

`runtime/prepared/<pick_date>.pkl`

The cache payload should contain:

- `pick_date`
- `start_date`
- `end_date`
- `prepared_by_symbol`
- metadata describing the parameters required to interpret the cache

Minimum metadata fields:

- `b1_config`
- `turnover_window`
- `weekly_ma_periods`
- `max_vol_lookback`

This keeps the cache format explicit and gives the loader enough information to reject obviously incompatible files in future changes.

### 3. Recompute Flag

Add a CLI boolean option:

`--recompute/--no-recompute`

Default:

`--no-recompute`

Behavior:

- `--no-recompute`: allow candidate short-circuit and prepared-cache reuse
- `--recompute`: ignore reusable candidate output and prepared cache, then recompute and overwrite outputs

`run` should pass the same flag through to its internal `screen` step so repeated end-to-end runs inherit the same reuse behavior.

### 4. Execution Flow

For `screen`:

1. Resolve `candidate_path`
2. If `recompute` is false and candidate file exists with non-empty candidates, return it
3. Resolve `prepared_cache_path`
4. If `recompute` is false and prepared cache is present and valid, load it
5. Otherwise connect to DB, fetch market window, compute prepared data, and write cache
6. Build the liquidity pool for `pick_date`
7. Run B1 on the prepared subset
8. Write candidate output

## Error Handling

- Corrupt or incompatible prepared cache files should not abort `screen`
- On cache load failure, emit a progress message and fall back to recomputation
- Candidate JSON parse failures should also fall back to recomputation unless `--recompute` is already forcing that path

## Testing

Required automated coverage:

- `screen` reuses an existing non-empty candidate file without connecting to DB
- `screen` ignores an existing empty candidate file and still recomputes
- `screen` reuses prepared cache when candidate output is absent
- `screen --recompute` bypasses both reuse paths
- helper tests for prepared cache read/write round-trip

## Success Criteria

- Rerunning `screen` for a `pick_date` with existing non-empty candidates returns quickly without database work
- Rerunning `screen` for a `pick_date` without candidates but with prepared cache skips the expensive prepare phase
- Users can force a fresh run with `--recompute`
