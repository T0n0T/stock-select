---
name: stock-select
description: Use when screening A-share stocks from the stock-cache PostgreSQL database with the stock-select CLI, generating daily charts, and coordinating multimodal subagents for chart review and final conclusions.
---

# Stock Select

Use this skill when the task is to run the standalone `stock-select` workflow against the `stock-cache` PostgreSQL data source for either end-of-day `--pick-date` runs or intraday `--intraday` runs.

## Required Workflow

- Always require an explicit built-in method.
- Built-in methods are `b1`, `b2`, and `hcr`.
- Pool sources are `turnover-top`, `record-watch`, and `custom`.
- Do not use `stock-cache read` CLI as the primary data source.
- Read PostgreSQL tables directly.
- Resolve DSN from `--dsn` or `POSTGRES_DSN` before any database-backed step.
- `screen`, `chart`, and `review` all support `--intraday` within this same skill.
- Run deterministic screening in Python first.
- Generate daily charts before review.
- Expect progress output on `stderr` by default; use `--no-progress` only when the caller needs quiet stdout-only path output.
- `custom` pool uses `--pool-source custom` plus optional `--pool-file`.
- Custom pool path precedence is `--pool-file`, then `STOCK_SELECT_POOL_FILE`, then `~/.agents/skills/stock-select/runtime/custom-pool.txt`.
- Custom pool files contain whitespace-separated stock codes such as `603138 300058`.
- Custom pool codes still intersect with the prepared screening universe before the strategy runs.
- Use the bundled review rubric and runtime layout references.
- Use `references/prompt.md` from this skill as the chart-review prompt source when dispatching subagents.
- Review should use rendered chart images, not HTML text.
- Dispatch one subagent per candidate for multimodal chart review when chart quality is the priority.
- Let the agent framework choose the model; do not hard-code a vendor-specific SDK in the workflow.
- Require each subagent to return strict JSON aligned with the prompt contract.
- If a subagent cannot return valid JSON, record that symbol in failures instead of fabricating a result.
- Write outputs under `~/.agents/skills/stock-select/runtime/`.
- Preserve existing end-of-day instructions for `--pick-date` runs.
- `screen --intraday` uses PostgreSQL confirmed history up to the previous trade date plus Tushare `rt_k` for the active trade date snapshot.
- `chart --intraday` and `review --intraday` must reuse the latest intraday candidate plus the same-trade-date shared prepared cache instead of fetching fresh realtime data.
- When the caller needs a shareable offline report, run CLI `render-html` after `review-merge`.
- `render-html` must look up stock names from PostgreSQL and render `code + name` in the HTML, not only the code.
- The packaged export should be a zip containing `summary.html`, `summary.json`, and the referenced chart PNG files under `charts/`.

## Runtime Paths By Mode

End-of-day `--pick-date` runs use:

- `runtime/candidates/<pick_date>.<method>.json`
- `runtime/prepared/<pick_date>.pkl` for shared `b1` / `b2` base prepare
- `runtime/prepared/<pick_date>.hcr.pkl` for `hcr`
- `runtime/charts/<pick_date>.<method>/`
- `runtime/reviews/<pick_date>.<method>/`
- `runtime/watch_pool/<method>.csv`
- `runtime/custom-pool.txt`

Intraday `--intraday` runs use:

- `runtime/candidates/<run_id>.<method>.json`
- `runtime/prepared/<trade_date>.intraday.pkl` for shared `b1` / `b2` base prepare
- `runtime/prepared/<trade_date>.intraday.hcr.pkl` for `hcr`
- `runtime/charts/<run_id>.<method>/`
- `runtime/reviews/<run_id>.<method>/`

Review and merge instructions must follow the active mode's runtime key:

- end-of-day mode: use `<pick_date>.<method>`
- intraday mode: use the latest intraday `<run_id>.<method>` selected by the candidate artifact
- prepared-cache lookup is different from candidate/review lookup:
  - end-of-day `b1` / `b2`: `<pick_date>.pkl`
  - intraday `b1` / `b2`: `<trade_date>.intraday.pkl`
  - `hcr`: keep method-specific prepared files

## Execution Order

1. Resolve the active mode and CLI arguments.
2. For end-of-day runs, resolve `pick_date` and query PostgreSQL market data needed for the requested screening method.
3. For intraday runs, resolve the active trade date, fetch PostgreSQL confirmed history through the previous trade date, then overlay Tushare `rt_k`.
4. Run deterministic `b1`, `b2`, or `hcr` screening and write candidate outputs.
5. Render daily chart PNG files for each candidate.
6. Run CLI `review` first to write baseline review outputs and `llm_review_tasks.json`.
7. After the CLI command returns, dispatch subagents from the task file against the rendered PNG files and `references/prompt.md`.
8. Write raw subagent JSON results under `runtime/reviews/<mode_key>/llm_review_results/`, where `<mode_key>` is `<pick_date>.<method>` for end-of-day and `<run_id>.<method>` for intraday.
9. Run CLI `review-merge` to validate `llm_review`, merge it back into each per-stock review file, and rewrite the final summary in the same mode-specific review directory.
10. If the caller asks for packaged HTML output, run CLI `render-html` after `review-merge`.
11. If the caller wants to persist end-of-day `PASS` and `WATCH` ideas across review dates, run CLI `record-watch` after `review` or `review-merge`.

## Subagent Review Protocol

When running chart review for quality-first selection:

1. Run the Python CLI `review` command first.
2. Load `runtime/reviews/<mode_key>/llm_review_tasks.json`.
3. Load `references/prompt.md` and pass it as the subagent's core chart-review prompt.
4. Send each subagent exactly one candidate at a time.
5. Provide these inputs to the subagent:
   - stock code
   - pick date
   - chart image path pointing to `<code>_day.png`
   - the prompt from `references/prompt.md`
6. Require the subagent to return strict JSON matching the prompt contract:
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
7. Write each raw subagent result to `runtime/reviews/<mode_key>/llm_review_results/<code>.json`.
8. Run CLI `review-merge` so the repository code validates the returned JSON before treating it as usable output.
9. If validation fails, let `review-merge` record the symbol in failures and continue.
10. Keep the local baseline review result alongside the validated subagent result.

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
- `screen --intraday` combines PostgreSQL confirmed history with Tushare `rt_k`, writes `runtime/candidates/<run_id>.<method>.json`, and stores shared base prepare at `runtime/prepared/<trade_date>.intraday.pkl` for `b1` / `b2`.
- `b1` keeps the low-`J`, `close > zxdkx`, `zxdq > zxdkx`, weekly bullish alignment, and non-bearish max-volume-day filters described in `references/b1-selector.md`.
- `b2` keeps the same top-turnover prefilter and the same recent 15-trading-day `b1` low-`J` history hit, then requires current `zxdq > zxdkx`, `MA25` support validity, shrinking volume, bullish daily/weekly/monthly `MACD`, upward `MA60`, and `MA144` distance within 30%.
- `b1` and `b2` share the same base prepared frame shape for EOD and intraday reuse.
- Prepared `b2` frames still require the same daily `ma25`, `ma60`, `ma144`, plus weekly/monthly aligned `dif` and `dea` fields (`dif_w`, `dea_w`, `dif_m`, `dea_m`) for deterministic screening reuse.
- `b2` phase-two MACD warmup remains on-demand and is not written as a separate prepared cache.
- `chart --pick-date` fetches one year of real symbol history for each candidate and writes `<code>_day.png`.
- Daily chart PNGs include `zxdq`, `zxdkx`, and a separate `MACD` panel with `dif`, `dea`, and `macd_hist`.
- `chart --intraday` reuses the latest intraday candidate for the requested method plus the same-trade-date shared prepared cache and writes charts under `runtime/charts/<run_id>.<method>/` without fetching fresh realtime data.
- `review --pick-date` writes a baseline local structured scoring result in a schema that also reserves `llm_review` for future subagent output.
- `review --intraday` reuses the latest intraday candidate for the requested method plus the same-trade-date shared prepared cache, writes baseline reviews under `runtime/reviews/<run_id>.<method>/`, and does not fetch fresh realtime data.
- The baseline review returns `trend_structure`, `price_position`, `volume_behavior`, `previous_abnormal_move`, `macd_phase`, `total_score`, `signal_type`, `verdict`, and a short Chinese comment.
- `screen --intraday --recompute` forces the shared same-trade-date prepared cache to be rewritten; without it, the command reuses the existing shared cache when compatible.
- `run` chains `screen`, `chart`, and `review`, while emitting stage progress and elapsed time to `stderr`; `--intraday` keeps those stages on the same latest intraday `run_id` for the requested method.
- `review-merge` must read and write within the review directory chosen by the active mode: `runtime/reviews/<pick_date>.<method>/` for end-of-day or `runtime/reviews/<run_id>.<method>/` for intraday.
- `record-watch` is end-of-day only. It reads `runtime/reviews/<pick_date>.<method>/summary.json`, keeps rows with verdict `PASS` or `WATCH`, writes or overwrites `runtime/watch_pool/<method>.csv`, stamps `recorded_at`, sorts by trading-day distance from the command execution day, and trims rows older than the configured `--window-trading-days` window.
- `render-html` reads the final `summary.json`, looks up stock names from PostgreSQL `instruments`, renders `summary.html`, copies linked PNG charts, and packages them into a shareable zip file that includes `summary.html`, `summary.json`, and `charts/`.

## Future Upgrade Path

- The intended end state is multimodal subagent chart review driven by `references/prompt.md`.
- Keep the deterministic `screen` and `chart` stages unchanged and swap only the `review` stage orchestration.

## Bundled References

- `references/b1-selector.md`
- `references/b2-selector.md`
- `references/prompt.md`
- `references/review-rubric.md`
- `references/runtime-layout.md`
