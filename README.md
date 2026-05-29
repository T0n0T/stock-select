# stock-select

`stock-select` is the Rust-native CLI for A-share screening, chart generation, native baseline review, review merge/list workflows, intraday snapshots, watch-pool recording, and review statistics.

This repository is the successor to the original Python CLI. The Python CLI has reached its final release and should remain available only as a historical/secondary branch for golden references and migration checks. New production work should target the Rust CLI.

## Status

- Rust binary: `stock-select-rs`
- Primary branch target: Rust CLI
- Historical Python implementation: keep as a secondary branch after the final Python release
- Supported native methods: `b1`, `b2`, `dribull`
- Unsupported method: `hcr`

The production path no longer falls back to the upstream Python CLI. Chart rendering still uses controlled Python scripts in this repository for `matplotlib`/`mplfinance`, not the historical Python CLI.

## Build

```bash
cargo build --release
cp target/release/stock-select-rs ~/.local/bin/
```

Generate shell completions:

```bash
stock-select-rs completions zsh > /tmp/_stock-select-rs
stock-select-rs completions bash > /tmp/stock-select-rs.bash
```

## Configuration

Configuration precedence:

```text
CLI argument > process environment > current working directory .env
```

Supported keys:

- `POSTGRES_DSN`
- `TUSHARE_TOKEN`
- `STOCK_SELECT_POOL_FILE`

Default runtime root:

```text
~/.agents/skills/stock-select/runtime
```

## Common Commands

End-of-day run:

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime \
  --recompute
```

Intraday run:

```bash
stock-select-rs run \
  --method b2 \
  --intraday \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

Review existing screen output:

```bash
stock-select-rs review \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

List review results:

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-05-25 \
  --verdict WATCH
```

Analyze a single stock:

```bash
stock-select-rs analyze-symbol \
  --method b2 \
  --symbol 002350.SZ \
  --pick-date 2026-04-21
```

## Watch Pool

Add `--record` to `run` or `review` to import same-day `PASS` and `WATCH` results into:

```text
<runtime-root>/watch_pool.csv
```

Rows are keyed by `method + code`. Repeated selections refresh the saved pick date, verdict, score, comment, and `recorded_at`.

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --record
```

Retention defaults to 15 trade dates:

```bash
stock-select-rs review \
  --method b2 \
  --pick-date 2026-05-25 \
  --record \
  --record-window-trading-days 20
```

## Batch And Stats Scripts

Backfill baseline reviews:

```bash
python3 scripts/backfill_baseline_reviews.py \
  --method b2 \
  --start-date 2026-05-20 \
  --end-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

Compute PASS topN win-rate statistics:

```bash
python3 scripts/review_top3_win_stats.py \
  --method b2 \
  --start-date 2026-04-01 \
  --end-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

The stats script prioritizes win proportion, not average forward return:

- `win_rate_ret3_pct`
- `win_rate_ret5_pct`
- `day_hit_rate_ret3_pct`
- `day_hit_rate_ret5_pct`

This avoids overvaluing a PASS top3 set because of a small number of extreme winners.

## Runtime Layout

End-of-day artifacts:

```text
candidates/<pick_date>.<method>.json
charts/<pick_date>.<method>/<code>_day.png
reviews/<pick_date>.<method>/<code>.json
reviews/<pick_date>.<method>/summary.json
reviews/<pick_date>.<method>/llm_review_tasks.json
```

Intraday artifacts use a date-scoped key:

```text
candidates/<trade_date>.intraday.<method>.json
charts/<trade_date>.intraday.<method>/<code>_day.png
reviews/<trade_date>.intraday.<method>/summary.json
prepared/<trade_date>.intraday.bin
prepared/<trade_date>.intraday.meta.json
```

## Verification

Before merging Rust changes:

```bash
cargo fmt --check
cargo test --quiet
python3 -m py_compile \
  scripts/check_charts.py \
  scripts/compare_screen.py \
  scripts/compare_review.py \
  scripts/render_charts.py \
  scripts/backfill_baseline_reviews.py \
  scripts/review_top3_win_stats.py
```

Python golden parity checks should read historical artifacts from:

```text
~/.agents/skills/stock-select/runtime
```

Do not recompute Python golden outputs unless explicitly needed.
