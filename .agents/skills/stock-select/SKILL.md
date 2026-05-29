---
name: stock-select
description: Use when screening or reviewing A-share stocks with the local Rust stock-select-rs CLI, including b1/b2 runs, intraday rt_k snapshots, custom pools, review merge/list workflows, or single named-stock requests in this repository.
---

# Stock Select Rust

Use this skill for the Rust repository at:

```text
/home/pi/Documents/agents/stock-select-rs
```

The Rust CLI binary is `stock-select-rs`. Build with:

```bash
cargo build --release && cp target/release/stock-select-rs ~/.local/bin/
```

Do not call the upstream Python `stock-select` CLI from this skill unless the user explicitly asks for a Python comparison or golden parity check.

When the Rust CLI is stable enough to replace the Python version entirely, rename the binary to `stock-select` and update references accordingly.

## Configuration

Run commands from the Rust repo root. Configuration precedence is:

```text
CLI argument > process environment > current working directory .env
```

Supported config keys:

- `POSTGRES_DSN`
- `TUSHARE_TOKEN`
- `STOCK_SELECT_POOL_FILE`

Default runtime root is:

```text
~/.agents/skills/stock-select/runtime
```

For Rust/Python parity checks, keep Rust runtime under `/tmp` unless the user asks otherwise.

## Supported Methods

- `b1`: native screen, chart, review, run
- `b2`: native screen, chart, review, run
- `dribull`: native screen, chart, review, run
- `hcr`: not supported by the current Rust CLI

Current command set:

```text
screen
chart
review
review-merge
review-list
run
analyze-symbol
completions
```

`analyze-symbol` currently supports `b1` and `b2` end-of-day single-stock analysis.

## Common Workflows

End-of-day b1/b2/dribull run:

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-run-b2 \
  --recompute
```

Intraday b1/b2/dribull run:

```bash
stock-select-rs run \
  --method b2 \
  --intraday \
  --runtime-root /tmp/stock-select-rs-intraday-b2
```

`run` performs screen + native review. It skips chart unless `--llm-review-limit` or `--llm-min-baseline-score` is set. With a threshold, it reviews first, writes `llm_review_tasks.json`, then charts only the task codes.

Add `--record` to `run` or `review` to write same-day PASS/WATCH results into `<runtime-root>/watch_pool.csv`. Rows are keyed by `method + code`; repeated selections refresh the saved pick date and review fields. The retention window defaults to 15 trade dates and can be changed with `--record-window-trading-days`.

`screen`、`chart`、`run` 默认向 stderr 输出结构化进度行，例如 `[screen] step=strategy status=done candidates=139`。需要安静运行时追加 `--no-progress`；普通结果路径或列表仍保持 stdout。

生成 shell completion：

```bash
stock-select-rs completions zsh > /tmp/_stock-select-rs
stock-select-rs completions bash > /tmp/stock-select-rs.bash
```

支持 `bash`、`zsh`、`fish`、`powershell`、`elvish`。

Generate charts for all candidates explicitly:

```bash
stock-select-rs chart \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-run-b2 \
  --chart-workers 4
```

Run review against existing candidates/prepared cache:

```bash
stock-select-rs review \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-run-b2 \
  --llm-review-limit 5
```

Inspect review results:

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-run-b2 \
  --verdict WATCH
```

Inspect intraday review results for the refreshed date-scoped group:

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-05-27 \
  --intraday \
  --runtime-root /tmp/stock-select-rs-intraday-b2 \
  --verdict WATCH
```

Merge validated LLM/subagent results:

```bash
stock-select-rs review-merge \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-run-b2
```

## Intraday Semantics

`screen --intraday` and `run --intraday` fetch Tushare Pro REST `rt_k` for `*.SH`, `*.SZ`, and `*.BJ`, overlay the active trade date snapshot on PostgreSQL confirmed history through the previous trade date, and write a timestamped `run_id` inside the payload as the fetch marker.

Intraday artifacts use the date-scoped key `<trade_date>.intraday`. Repeated intraday runs for the same trade date and method refresh the same candidates/reviews/charts instead of creating timestamped runtime groups. `run --intraday` must keep screen/review/chart on that same date-scoped artifact key.

Independent `review --intraday` is currently not exposed. Use `run --intraday`.

## Custom Pool And Single Stock

Custom pool workflow:

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --pool-source custom \
  --pool-file /tmp/custom-pool.txt \
  --runtime-root /tmp/stock-select-rs-custom
```

Custom pool file contains whitespace-separated codes:

```text
603138 300058 002350.SZ
```

For a single named stock request, first resolve a TS code. If the user wants the candidate workflow for one stock, create a one-code custom pool and run `screen` or `run` with `--pool-source custom`.

If the user asks for “score this stock even if it would not enter the candidate pool”, use Rust `analyze-symbol` when the method is `b1` or `b2` and the request is end-of-day:

```bash
stock-select-rs analyze-symbol \
  --method b2 \
  --symbol 002350.SZ \
  --pick-date 2026-04-21
```

It writes `ad_hoc/<pick_date>.<method>.<code>/result.json` plus `<code>_day.png`, and returns baseline review even when `selected_as_candidate=false`.

For `dribull`, `hcr`, or intraday single-stock analysis, say that Rust `analyze-symbol` does not support that scope yet. Do not pretend `custom` pool is equivalent; it can still produce no candidate and no baseline review.

## Review And Subagent Results

Native review writes per-stock JSON, `summary.json`, and `llm_review_tasks.json`.

If the user asks for multimodal/LLM chart review:

1. Run Rust `review` or `run` with `--llm-review-limit` or `--llm-min-baseline-score`.
2. Read `reviews/<key>.<method>/llm_review_tasks.json`.
3. Use native subagent tools for chart review; do not spawn external agent CLI processes.
4. Write raw JSON to `reviews/<key>.<method>/llm_review_results/<code>.json`.
5. Run `review-merge` so repository validation merges or records failures.

Method prompts and review rubric are available in `references/`.

## References

Read these only when needed:

- `references/runtime-layout.md`: current Rust runtime paths.
- `references/review-rubric.md`: review JSON contract and scoring fields.
- `references/prompt-b1.md`, `references/prompt-b2.md`, `references/prompt-dribull.md`: chart-review prompts copied from upstream.
