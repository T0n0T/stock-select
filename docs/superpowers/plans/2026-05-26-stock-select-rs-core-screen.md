# stock-select-rs Core Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Rust `screen` command that reads EOD A-share market data, prepares shared indicator rows, caches them, and emits compatible candidate JSON for `b1`, `b2`, and `dribull`.

**Architecture:** The implementation uses a small `clap` CLI, typed market/prepared/candidate models, batched PostgreSQL reads, JSON cache storage for the first working cut, and vector-based indicator functions. Strategy modules operate on per-symbol prepared rows and return deterministic candidates plus stats.

**Tech Stack:** Rust 2024, `clap`, `chrono`, `serde`, `serde_json`, `anyhow`, `thiserror`, `postgres`, `rayon`, `tempfile`.

---

## File Structure

- `Cargo.toml`: dependencies and dev dependencies.
- `src/main.rs`: entry point that delegates to `cli::run`.
- `src/lib.rs`: module exports for tests and binary.
- `src/cli.rs`: CLI parsing, progress timing, and screen orchestration.
- `src/config.rs`: DSN resolution, runtime root, date window, and method parsing.
- `src/model.rs`: shared domain models.
- `src/db.rs`: PostgreSQL query implementation.
- `src/cache.rs`: cache metadata, cache path resolution, JSON cache read/write, candidate path resolution.
- `src/indicators.rs`: vector-based indicator helpers.
- `src/prepare.rs`: per-symbol grouping and prepared-row calculation.
- `src/strategies/mod.rs`: strategy dispatch and stat maps.
- `src/strategies/b1.rs`: B1 screening.
- `src/strategies/b2.rs`: B2 signal screening.
- `src/strategies/dribull.rs`: dribull screening.
- `src/output.rs`: atomic JSON output.
- `tests/screen_flow.rs`: fixture-level integration tests without a live DB.

## Tasks

### Task 1: Project Skeleton and Config

**Files:**
- Modify: `Cargo.toml`
- Modify: `src/main.rs`
- Create: `src/lib.rs`
- Create: `src/model.rs`
- Create: `src/config.rs`

- [ ] **Step 1: Add dependencies**

Update `Cargo.toml` with CLI, serialization, date, error, DB, and parallelism crates.

- [ ] **Step 2: Add domain models**

Create typed structs for market rows, prepared rows, candidates, screen results, and methods.

- [ ] **Step 3: Add config parsing tests**

Tests must cover method parsing, invalid methods, DSN precedence, and date window calculation.

- [ ] **Step 4: Implement config helpers**

Implement `Method::parse`, DSN resolution, default runtime root, and `pick_date - 366 days`.

- [ ] **Step 5: Run `cargo test`**

Expected: config and model tests pass.

### Task 2: Indicators

**Files:**
- Create: `src/indicators.rs`

- [ ] **Step 1: Write indicator tests**

Tests must cover EMA length/seed behavior, KDJ first values, rolling mean with minimum periods, `barslast`, and ZX line availability after long windows.

- [ ] **Step 2: Implement indicator helpers**

Implement `ema`, `rolling_mean`, `rolling_sum`, `rolling_min`, `rolling_max`, `kdj`, `macd`, `zx_lines`, `barslast`, and `count_dynamic`.

- [ ] **Step 3: Run indicator tests**

Expected: all indicator tests pass.

### Task 3: Prepared Rows and Cache

**Files:**
- Create: `src/prepare.rs`
- Create: `src/cache.rs`

- [ ] **Step 1: Write prepare/cache tests**

Tests must cover per-symbol grouping, prepared row fields on fixture rows, cache metadata matching, stale metadata rejection, and cache round trip.

- [ ] **Step 2: Implement prepared-row calculation**

Group rows by code, sort by date, compute volume, turnover, KDJ, ZX lines, MACD, MA25, MA60, MA144, and B1 helper fields.

- [ ] **Step 3: Implement JSON cache**

Use `runtime/prepared/<pick_date>.json` plus `runtime/prepared/<pick_date>.meta.json` for the first implementation, with atomic writes.

- [ ] **Step 4: Run prepare/cache tests**

Expected: all tests pass.

### Task 4: Strategies

**Files:**
- Create: `src/strategies/mod.rs`
- Create: `src/strategies/b1.rs`
- Create: `src/strategies/b2.rs`
- Create: `src/strategies/dribull.rs`

- [ ] **Step 1: Write strategy tests**

Tests must include at least one hand-built selected candidate per implemented method and one no-pick case for missing pick date.

- [ ] **Step 2: Implement B1**

Port the practical B1 filters using prepared fields: low-J/recent quantile, `close > zxdkx`, `zxdq > zxdkx`, weekly/long trend approximation, max-volume-day not bearish, and tightening helper filters.

- [ ] **Step 3: Implement B2**

Port B2/B3/B3+ signal logic over per-symbol prepared histories.

- [ ] **Step 4: Implement dribull**

Port the non-MACD dribull filters and use prepared MACD slope/phase approximation for the first Rust cut.

- [ ] **Step 5: Run strategy tests**

Expected: strategy tests pass.

### Task 5: DB, CLI, and Output

**Files:**
- Create: `src/db.rs`
- Create: `src/output.rs`
- Create: `src/cli.rs`
- Modify: `src/main.rs`

- [ ] **Step 1: Write CLI/output tests**

Tests must cover candidate JSON shape, atomic write result, and screen orchestration using fixture rows and an injected loader.

- [ ] **Step 2: Implement PostgreSQL loader**

Query `daily_market` once for `start_date..end_date`, ordered by `ts_code, trade_date`.

- [ ] **Step 3: Implement output writer**

Write `runtime/candidates/<pick_date>.<method>.json` atomically.

- [ ] **Step 4: Implement CLI orchestration**

Load cache when valid, otherwise query DB and prepare rows, then run strategy and write candidates.

- [ ] **Step 5: Run `cargo test`**

Expected: all tests pass.

### Task 6: Verification

**Files:**
- Modify as needed based on test failures only.

- [ ] **Step 1: Run format and tests**

Run `cargo fmt --check` and `cargo test`.

- [ ] **Step 2: Run live smoke if DSN exists**

If `POSTGRES_DSN` is set, run `cargo run -- screen --method b1 --pick-date 2026-05-25 --runtime-root /tmp/stock-select-rs-smoke`.

- [ ] **Step 3: Capture results**

Record whether tests passed, whether live smoke ran, and where the candidate output was written.

## Self-Review

- Spec coverage: the plan covers EOD screen, DSN/runtime config, DB reads, prepared cache, indicator calculation, strategies, candidate output, progress-ready CLI, and tests.
- Scope control: intraday, chart, review, HTML, watch pool, `hcr`, and `left_peak` remain outside this phase.
- Placeholder scan: no task depends on unspecified modules or deferred behavior; dribull explicitly uses a first-cut MACD approximation instead of claiming exact wave parity.
