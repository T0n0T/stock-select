# stock-select-rs Core Screen Design

## Goal

Build a Rust implementation of the performance-critical end-of-day `screen` workflow from `/home/pi/Documents/agents/stock-select`, focused on faster PostgreSQL reads, prepared-cache reads and writes, and indicator/strategy computation.

The first phase intentionally does not replace chart rendering, baseline review, LLM review orchestration, HTML export, intraday runs, or watch-pool maintenance. Those workflows can continue to use the Python CLI and existing runtime artifacts.

## Scope

The Rust CLI will provide:

- `stock-select-rs screen --method <b1|b2|dribull> --pick-date YYYY-MM-DD`
- DSN resolution from `--dsn`, then `POSTGRES_DSN`
- runtime root resolution from `--runtime-root`, defaulting to `~/.agents/skills/stock-select/runtime`
- batched PostgreSQL reads from `daily_market`
- prepared data generation for shared `b1`, `b2`, and `dribull` columns
- cache metadata validation and reuse
- deterministic candidate output under `runtime/candidates/<pick_date>.<method>.json`
- progress messages on stderr

The first phase will not implement:

- `hcr` and `left_peak`
- intraday `--intraday`
- chart PNG rendering
- review, review-merge, record-watch, HTML, or clean commands
- Tushare realtime reads
- Python extension bindings

## Compatibility

The candidate JSON should preserve the Python workflow's practical downstream contract:

- file path: `runtime/candidates/<pick_date>.<method>.json`
- top-level keys include `method`, `pick_date`, `generated_at`, `count`, `candidates`, and `stats`
- each candidate includes at least `code`, `pick_date`, `close`, and `turnover_n`
- `b2` candidates include `signal`

Prepared cache should use a Rust-native fast columnar format plus a JSON metadata file in phase one:

- file path: `runtime/prepared/<pick_date>.arrow`
- metadata path: `runtime/prepared/<pick_date>.meta.json`

The metadata will include:

- `artifact_version`
- `method`
- `shared_methods`
- `pick_date`
- `start_date`
- `end_date`
- `schema_version`
- `row_count`
- `symbol_count`
- `source_table`

If later Python compatibility requires direct `pd.read_feather`, a follow-up phase can switch the data file to Feather v2 while preserving the same metadata schema.

## Architecture

The Rust project will be split into focused modules:

- `main.rs`: process entry point only
- `cli.rs`: `clap` command definitions and argument validation
- `config.rs`: DSN, runtime root, date window, and method resolution
- `db.rs`: PostgreSQL connection and batched `daily_market` loading
- `model.rs`: `MarketRow`, `PreparedRow`, `Candidate`, `ScreenResult`, and `Method`
- `cache.rs`: prepared-cache paths, metadata, load, save, and validation
- `indicators.rs`: EMA, rolling statistics, KDJ, MACD, ZX lines, moving averages, dynamic references, and `barslast`
- `prepare.rs`: group market rows by symbol and compute prepared rows in parallel
- `strategies/mod.rs`: strategy dispatch
- `strategies/b1.rs`: B1 deterministic screening
- `strategies/b2.rs`: B2/B3/B3+ deterministic signal screening
- `strategies/dribull.rs`: dribull non-MACD and MACD-wave screening approximation aligned to the Python behavior
- `output.rs`: candidate JSON serialization and runtime file writes
- `error.rs`: shared error type and user-facing messages

## Data Flow

1. Parse CLI arguments and validate `method` and `pick_date`.
2. Resolve DSN and runtime root.
3. Compute an EOD market-data window from `pick_date - 366 days` through `pick_date`.
4. Check prepared cache metadata for matching date window, schema version, and shared method compatibility.
5. If cache is valid, load prepared rows from cache.
6. If cache is missing or stale, query `daily_market` once for the whole date window and compute prepared rows grouped by `ts_code`.
7. Run the selected strategy against prepared rows for `pick_date`.
8. Sort candidates deterministically by descending `turnover_n`, then ascending code unless the Python method has stricter ordering for the method.
9. Write candidate JSON to the runtime candidate path.
10. Emit elapsed timing for DB, prepare/cache, strategy, and output stages.

## Performance Design

The implementation should avoid DataFrame-style overhead in the hot path:

- store each symbol's history in contiguous vectors
- compute rolling and EMA indicators in single forward passes where possible
- parallelize per-symbol preparation and strategy evaluation with `rayon`
- use batched SQL ordered by `ts_code, trade_date` so grouping is linear
- reuse prepared cache when metadata matches
- write output atomically by writing to a temporary file and renaming

The DB layer should avoid per-symbol round trips. The first-phase query is:

```sql
SELECT ts_code, trade_date, open, high, low, close, vol
FROM daily_market
WHERE trade_date BETWEEN $1 AND $2
ORDER BY ts_code ASC, trade_date ASC
```

## Error Handling

The CLI should return clear non-zero errors for:

- missing DSN
- invalid pick date
- unsupported method
- database connection/query failure
- no market rows found for the requested window
- no rows available on the requested pick date
- unreadable or incompatible prepared cache
- candidate output write failure

Stale or unreadable cache should not fail the run by default. The CLI should log the cache skip reason and recompute.

## Testing

Tests will be written before implementation for each core unit:

- date and method parsing
- cache path and metadata validation
- indicator fixtures for EMA, KDJ, ZX, and `barslast`
- prepared-row generation from small multi-symbol fixtures
- B2 signal resolution for a small hand-built history
- candidate JSON shape and stable ordering

Integration tests will use fixture rows instead of a live database. A live DB smoke test can be run manually when `POSTGRES_DSN` is available.

## Acceptance Criteria

The first phase is complete when:

- `cargo test` passes
- `cargo run -- screen --method b1 --pick-date YYYY-MM-DD --dsn ...` can produce a candidate JSON file from PostgreSQL
- repeated runs reuse the prepared cache when metadata matches
- `b1`, `b2`, and `dribull` commands produce deterministic candidate JSON
- output paths match the Python runtime layout for candidates
- the implementation reports elapsed time for DB/cache, calculation, strategy, and output stages
