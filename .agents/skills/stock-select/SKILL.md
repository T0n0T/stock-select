---
name: stock-select
description: Use when screening A-share stocks from the stock-cache PostgreSQL database with the stock-select CLI, generating daily charts, and coordinating multimodal subagents for chart review and final conclusions.
---

# Stock Select

Use this skill when the task is to run the standalone `stock-select` workflow against the `stock-cache` PostgreSQL data source for either end-of-day `--pick-date` runs or intraday `--intraday` runs.

## Required Workflow

- Always require an explicit built-in method.
- Screening built-in methods are `b1`, `b2`, `dribull`, and `hcr`.
- Review built-in methods are `b1`, `b2`, `dribull`, and `hcr`.
- Pool sources are `turnover-top`, `record-watch`, and `custom`.
- Do not use `stock-cache read` CLI as the primary data source.
- Read PostgreSQL tables directly.
- Resolve DSN from `--dsn` or `POSTGRES_DSN` before any database-backed step.
- `screen`, `chart`, and `review` all support `--intraday` within this same skill.
- Run deterministic screening in Python first.
- Generate daily charts before review.
- Expect progress output on `stderr` by default; use `--no-progress` only when the caller needs quiet stdout-only path output.
- `review` and `run` support optional `--llm-min-baseline-score SCORE` to limit `llm_review_tasks.json` to candidates whose baseline `total_score` is at least `SCORE`.
- `--llm-min-baseline-score` filters only LLM dispatch tasks; baseline review files, `summary.json`, charts, and deterministic screening outputs still include every successfully baseline-reviewed candidate.
- `custom` pool uses `--pool-source custom` plus optional `--pool-file`.
- Custom pool path precedence is `--pool-file`, then `STOCK_SELECT_POOL_FILE`, then `~/.agents/skills/stock-select/runtime/custom-pool.txt`.
- Custom pool files contain whitespace-separated stock codes such as `603138 300058`.
- Custom pool codes still intersect with the prepared screening universe before the strategy runs.
- Use the bundled review rubric and runtime layout references.
- Use method-specific chart-review prompts from this skill when dispatching subagents:
  - `b1` uses `references/prompt-b1.md`
  - `dribull` uses `references/prompt-dribull.md`
  - `hcr` uses `references/prompt.md`
  - `b2` uses `references/prompt-b2.md`
- Review should use rendered chart images, not HTML text.
- Dispatch one subagent per candidate for multimodal chart review when chart quality is the priority.
- The main agent must use the platform's native subagent tools for chart review dispatch.
- Do not substitute external `codex exec` sessions, shell background jobs, ad-hoc Python multiprocessing, or any other multi-threaded / multi-process workaround for subagent review.
- If native subagent dispatch is temporarily unavailable, stop and surface that blocker instead of silently switching to another concurrency mechanism.
- Let the agent framework choose the model; do not hard-code a vendor-specific SDK in the workflow.
- Require each subagent to return strict JSON aligned with the prompt contract.
- If a subagent cannot return valid JSON, record that symbol in failures instead of fabricating a result.
- Write outputs under `~/.agents/skills/stock-select/runtime/`.
- Preserve existing end-of-day instructions for `--pick-date` runs.
- `screen --intraday` uses PostgreSQL confirmed history up to the previous trade date plus Tushare `rt_k` for the active trade date snapshot.
- `chart --intraday` and `review --intraday` must reuse the latest intraday candidate plus the same-trade-date shared prepared cache instead of fetching fresh realtime data.
- `stock-select html render` is the preferred way to build the review HTML site after `review-merge`.
- `stock-select html render` must look up stock names from PostgreSQL and render `code + name` in the HTML, not only the code.
- `stock-select html render` must generate `runtime/reviews/site/<pick_date>.<method>/index.html` and rebuild `runtime/reviews/site/index.html`.
- `stock-select html zip` packages `index.html`, `summary.json`, and the referenced chart PNG files under `charts/`.
- `stock-select html serve` exposes the full `runtime/reviews/site/` tree as a local static site.
- `render-html` is compatibility-only and not the preferred workflow.

## Runtime Paths By Mode

End-of-day `--pick-date` runs use:

- `runtime/candidates/<pick_date>.<method>.json`
- `runtime/prepared/<pick_date>.feather` + `runtime/prepared/<pick_date>.meta.json` for shared `b1` / `b2` / `dribull` base prepare
- `runtime/prepared/<pick_date>.hcr.feather` + `runtime/prepared/<pick_date>.hcr.meta.json` for `hcr`
- `runtime/charts/<pick_date>.<method>/`
- `runtime/reviews/<pick_date>.<method>/`
- `runtime/watch_pool.csv`
- `runtime/custom-pool.txt`

Intraday `--intraday` runs use:

- `runtime/candidates/<run_id>.<method>.json`
- `runtime/prepared/<trade_date>.intraday.feather` + `runtime/prepared/<trade_date>.intraday.meta.json` for shared `b1` / `b2` / `dribull` base prepare
- `runtime/prepared/<trade_date>.intraday.hcr.feather` + `runtime/prepared/<trade_date>.intraday.hcr.meta.json` for `hcr`
- `runtime/charts/<run_id>.<method>/`
- `runtime/reviews/<run_id>.<method>/`

Review and merge instructions must follow the active mode's runtime key:

- end-of-day mode: use `<pick_date>.<method>`
- intraday mode: use the latest intraday `<run_id>.<method>` selected by the candidate artifact
- prepared-cache is stored as `<stem>.feather` (data) + `<stem>.meta.json` (metadata):
  - end-of-day `b1` / `b2` / `dribull`: `<pick_date>`
  - intraday `b1` / `b2` / `dribull`: `<trade_date>.intraday`
  - `hcr`: keep method-specific `<pick_date>.hcr` / `<trade_date>.intraday.hcr` stems

## Execution Order

1. Resolve the active mode and CLI arguments.
2. For end-of-day runs, resolve `pick_date` and query PostgreSQL market data needed for the requested screening method.
3. For intraday runs, resolve the active trade date, fetch PostgreSQL confirmed history through the previous trade date, then overlay Tushare `rt_k`.
4. Run deterministic `b1`, `b2`, `dribull`, or `hcr` screening and write candidate outputs.
5. Render daily chart PNG files for each candidate.
6. Run CLI `review` first to write baseline review outputs and `llm_review_tasks.json`; add `--llm-min-baseline-score SCORE` when the caller wants LLM review tasks filtered by baseline score.
7. After the CLI command returns, dispatch subagents from the task file against the rendered PNG files and the method-specific prompt file (`b1` uses `references/prompt-b1.md`; `dribull` uses `references/prompt-dribull.md`; `hcr` uses `references/prompt.md`; `b2` uses `references/prompt-b2.md`).
8. Write raw subagent JSON results under `runtime/reviews/<mode_key>/llm_review_results/`, where `<mode_key>` is `<pick_date>.<method>` for end-of-day and `<run_id>.<method>` for intraday.
9. Run CLI `review-merge` to validate `llm_review`, merge it back into each per-stock review file, and rewrite the final summary in the same mode-specific review directory.
10. If the caller asks for HTML output, run `stock-select html render` after `review-merge`.
11. If the caller asks for an offline package, run `stock-select html zip` after `stock-select html render`.
12. If the caller asks for browser access to the full review site, run `stock-select html serve`.
13. If the caller wants to persist end-of-day `PASS` and `WATCH` ideas across review dates, run CLI `record-watch` after `review` or `review-merge`.

## Subagent Review Protocol

When running chart review for quality-first selection:

1. Run the Python CLI `review` command first.
2. Load `runtime/reviews/<mode_key>/llm_review_tasks.json`.
   - If `review` or `run` used `--llm-min-baseline-score`, this task list is an intentional subset of baseline-reviewed candidates.
   - Do not dispatch subagents for symbols absent from `llm_review_tasks.json` unless the caller explicitly asks to override the threshold.
3. Read `max_concurrency` from the task file and treat it as a hard cap for concurrent subagents.
4. Keep the `llm review` dispatch stage capped at 6 concurrent subagents.
5. Use only native subagent APIs such as `spawn_agent`, `send_input`, and `wait_agent` for dispatch and collection.
6. Do not launch extra CLI agent sessions, shell-managed workers, or detached background processes to emulate subagents.
7. Unless the user explicitly requests parallel subagent work, dispatch chart-review subagents serially: one candidate at a time, wait for completion, persist the JSON, then move to the next candidate.
8. Load the method-specific prompt and pass it as the subagent's core chart-review prompt:
   - `b1`: `references/prompt-b1.md`
   - `dribull`: `references/prompt-dribull.md`
   - `hcr`: `references/prompt.md`
   - `b2`: `references/prompt-b2.md`
9. Send each subagent exactly one candidate at a time.
10. Provide these inputs to the subagent:
   - stock code
   - pick date
   - chart image path pointing to `<code>_day.png`
   - the prompt from the method-specific prompt file (`references/prompt-b1.md` for `b1`, `references/prompt-dribull.md` for `dribull`, `references/prompt-b2.md` for `b2`, `references/prompt.md` for `hcr`)
11. Require the subagent to return strict JSON matching the prompt contract:
   - `trend_reasoning`
   - `position_reasoning`
   - `volume_reasoning`
   - `abnormal_move_reasoning`
   - `macd_reasoning`
   - `signal_reasoning`
   - `scores.trend_structure`
   - `scores.price_position`
   - `scores.volume_behavior`
   - `scores.previous_abnormal_move`
   - `scores.macd_phase`
   - `total_score`
   - `signal_type`
   - `verdict`
   - `comment`
12. Write each raw subagent result to `runtime/reviews/<mode_key>/llm_review_results/<code>.json`.
13. Run CLI `review-merge` so the repository code validates the returned JSON before treating it as usable output.
14. If validation fails, let `review-merge` record the symbol in failures and continue.
15. Keep the local baseline review result alongside the validated subagent result.

Use `<mode_key>` as follows:

- end-of-day mode: `<pick_date>.<method>`
- intraday mode: latest intraday `<run_id>.<method>`

## Main-Agent Validation Gate

Before the main agent treats any subagent output as mergeable, it should verify all of the following:

1. The subagent wrote one raw JSON file per stock under `runtime/reviews/<mode_key>/llm_review_results/<code>.json`.
2. The JSON includes all required reasoning fields:
   - `trend_reasoning`
   - `position_reasoning`
   - `volume_reasoning`
   - `abnormal_move_reasoning`
   - `macd_reasoning`
   - `signal_reasoning`
3. The JSON includes all required score fields under `scores`:
   - `trend_structure`
   - `price_position`
   - `volume_behavior`
   - `previous_abnormal_move`
   - `macd_phase`
4. The JSON includes:
   - `total_score`
   - `signal_type`
   - `verdict`
   - `comment`
5. `signal_type` must be one of:
   - `trend_start`
   - `rebound`
   - `distribution_risk`
6. `verdict` must be one of:
   - `PASS`
   - `WATCH`
   - `FAIL`
7. All reasoning fields and `comment` must be non-empty strings.
8. The main agent should not manually trust or hand-wave this validation. It should run CLI `review-merge`, which applies the repository validation logic before merge.

If any of the checks above fail:

- do not hand-edit the JSON into shape
- do not merge the result manually
- record the symbol as a failed LLM review
- keep the baseline review as the only usable result for that symbol

## Current Implementation

- `screen --pick-date` reads one year of `daily_market` OHLCV data, computes the requested method's derived fields locally, and writes `runtime/candidates/<pick_date>.<method>.json`.
- `screen --intraday` combines PostgreSQL confirmed history with Tushare `rt_k`, writes `runtime/candidates/<run_id>.<method>.json`, stores shared base prepare as `runtime/prepared/<trade_date>.intraday.feather` + `runtime/prepared/<trade_date>.intraday.meta.json` for `b1` / `dribull`, and stores method-specific prepare for `b2` / `hcr`.
- `b1` keeps the low-`J`, `close > zxdkx`, `zxdq > zxdkx`, weekly bullish alignment, and non-bearish max-volume-day filters described in `references/b1-selector.md`.
- `b2` screening now follows the new主图信号口径 and emits deterministic `B2` / `B3` / `B3+` / `B4` / `B5` candidates from daily OHLCV + KDJ + trend context.
- `dribull` keeps the former two-stage screening rule:
  - phase 1 keeps only structural conditions: current `zxdq > zxdkx`, `MA25` support validity, shrinking volume, upward `MA60`, and `MA144` distance within 30%
  - phase 2 classifies weekly and daily `MACD` waves and only accepts weekly `wave1` / `wave3` with daily `wave2_end` / `wave4_end`
- `b1`, `b2`, and `dribull` share the same base prepared frame shape for EOD and intraday reuse.
- `chart --pick-date` fetches one year of real symbol history for each candidate and writes `<code>_day.png`.
- Daily chart PNGs include `zxdq`, `zxdkx`, and a separate `MACD` panel with `dif`, `dea`, and `macd_hist`.
- `chart --intraday` reuses the latest intraday candidate for the requested method plus the same-trade-date shared prepared cache and writes charts under `runtime/charts/<run_id>.<method>/` without fetching fresh realtime data.
- `review --pick-date` writes a baseline local structured scoring result in a schema that also reserves `llm_review` for future subagent output.
- `review --intraday` reuses the latest intraday candidate for the requested method plus the same-trade-date shared prepared cache, writes baseline reviews under `runtime/reviews/<run_id>.<method>/`, and does not fetch fresh realtime data.
- `review --pick-date`, `review --intraday`, and `run` accept `--llm-min-baseline-score`; when provided, only candidates with baseline `total_score >= SCORE` are written to `llm_review_tasks.json`, while all successful baseline reviews still remain in per-stock files and `summary.json`.
- The baseline review returns `trend_structure`, `price_position`, `volume_behavior`, `previous_abnormal_move`, `macd_phase`, `total_score`, `signal_type`, `verdict`, and a short Chinese comment.
- `b1` deterministic screening remains unchanged; only the review layer is wave-aware.
- `b1` review now uses a dedicated reviewer plus `references/prompt-b1.md`.
- For `b1`, the baseline comment compresses the same weekly/daily wave interpretation used by the shared MACD wave core, while keeping the final baseline schema stable.
- `b1` total-score calculation now counts `macd_phase`.
- `b1` review task payloads add text-only deterministic context:
  - `weekly_wave_context`
  - `daily_wave_context`
  - `wave_combo_context`
- For review namespace `b2`, the baseline comment compresses the same weekly/daily wave interpretation used by the legacy `b2` deterministic screening, while keeping the final baseline schema stable.
- `b2` review task payloads add text-only deterministic context:
  - `weekly_wave_context`
  - `daily_wave_context`
  - `wave_combo_context`
- `review --method dribull` now uses a dedicated reviewer plus `references/prompt-dribull.md`, while review artifacts keep the method key `dribull`.
- `run --method b2` currently means: new `b2` screening + existing legacy `b2` review.
- `screen --intraday --recompute` forces the shared same-trade-date prepared cache to be rewritten; without it, the command reuses the existing shared cache when compatible.
- `run` chains `screen`, `chart`, and `review`, while emitting stage progress and elapsed time to `stderr`; `--intraday` keeps those stages on the same latest intraday `run_id` for the requested method.
- `review-merge` must read and write within the review directory chosen by the active mode: `runtime/reviews/<pick_date>.<method>/` for end-of-day or `runtime/reviews/<run_id>.<method>/` for intraday.
- `record-watch` is end-of-day only. It reads `runtime/reviews/<pick_date>.<method>/summary.json`, keeps rows with verdict `PASS` or `WATCH`, writes or overwrites `runtime/watch_pool.csv`, stamps `recorded_at`, sorts by trading-day distance from the command execution day, and trims rows older than the configured `--window-trading-days` window.
- `record-watch` de-duplicates by `method + code`: when the same stock is selected again for the same method, replace the old row with the new summary row so `pick_date` and `recorded_at` reflect the latest selection.
- `record-watch` keeps the `method` column in the CSV for traceability, but the runtime watch pool is shared across methods and is no longer split into per-method files.
- `stock-select html render` reads the final `summary.json`, looks up stock names from PostgreSQL `instruments`, renders `runtime/reviews/site/<pick_date>.<method>/index.html`, and rebuilds `runtime/reviews/site/index.html`.
- `stock-select html zip` packages the rendered report into a shareable zip file that includes `index.html`, `summary.json`, and `charts/`.
- `stock-select html serve` exposes the full rendered site tree for local browser access.
- `render-html` remains available as a compatibility wrapper around `stock-select html render` plus `stock-select html zip`.

## Future Upgrade Path

- The intended end state is multimodal subagent chart review driven by the method-specific prompt files: `references/prompt-b1.md` for `b1`, `references/prompt-dribull.md` for `dribull`, `references/prompt-b2.md` for `b2`, and `references/prompt.md` for `hcr`.
- Keep the deterministic `screen` and `chart` stages unchanged and swap only the `review` stage orchestration.

## Bundled References

- `references/b1-selector.md`
- `references/b2-selector.md`
- `references/prompt-b1.md`
- `references/prompt-dribull.md`
- `references/prompt.md`
- `references/prompt-b2.md`
- `references/review-rubric.md`
- `references/runtime-layout.md`
