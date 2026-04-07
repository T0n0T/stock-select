---
name: stock-select
description: Use when screening A-share stocks from the stock-cache PostgreSQL database with the B1 method, generating daily charts, and coordinating multimodal subagents for chart review and final conclusions.
---

# Stock Select

Use this skill when the task is to run the standalone `stock-select` workflow against the `stock-cache` PostgreSQL data source.

## Required Workflow

- Always require `--method b1`.
- Reject any method other than `b1`.
- Do not use `stock-cache read` CLI as the primary data source.
- Read PostgreSQL tables directly.
- Resolve DSN from `--dsn` or `POSTGRES_DSN` before any database-backed step.
- Run deterministic screening in Python first.
- Generate daily charts before review.
- Expect progress output on `stderr` by default; use `--no-progress` only when the caller needs quiet stdout-only path output.
- Use the bundled review rubric and runtime layout references.
- Use `references/prompt.md` from this skill as the chart-review prompt source when dispatching subagents.
- Review should use rendered chart images, not HTML text.
- Dispatch one subagent per candidate for multimodal chart review when chart quality is the priority.
- Let the agent framework choose the model; do not hard-code a vendor-specific SDK in the workflow.
- Require each subagent to return strict JSON aligned with the prompt contract.
- If a subagent cannot return valid JSON, record that symbol in failures instead of fabricating a result.
- Write outputs under `~/.agents/skills/stock-select/runtime/`.

## Execution Order

1. Resolve the pick date and CLI arguments.
2. Query PostgreSQL market data needed for B1 screening.
3. Run deterministic B1 screening and write candidate outputs.
4. Render daily chart PNG files for each candidate.
5. Run CLI `review` first to write baseline review outputs and `llm_review_tasks.json`.
6. After the CLI command returns, dispatch subagents from the task file against the rendered PNG files and `references/prompt.md`.
7. Write raw subagent JSON results under `runtime/reviews/<pick_date>/llm_review_results/`.
8. Run CLI `review-merge` to validate `llm_review`, merge it back into each per-stock review file, and rewrite the final summary.

## Subagent Review Protocol

When running chart review for quality-first selection:

1. Run the Python CLI `review` command first.
2. Load `runtime/reviews/<pick_date>/llm_review_tasks.json`.
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
   - `signal_reasoning`
   - `scores.trend_structure`
   - `scores.price_position`
   - `scores.volume_behavior`
   - `scores.previous_abnormal_move`
   - `total_score`
   - `signal_type`
   - `verdict`
   - `comment`
7. Write each raw subagent result to `runtime/reviews/<pick_date>/llm_review_results/<code>.json`.
8. Run CLI `review-merge` so the repository code validates the returned JSON before treating it as usable output.
9. If validation fails, let `review-merge` record the symbol in failures and continue.
10. Keep the local baseline review result alongside the validated subagent result.

## Main-Agent Validation Gate

Before the main agent treats any subagent output as mergeable, it should verify all of the following:

1. The subagent wrote one raw JSON file per stock under `runtime/reviews/<pick_date>/llm_review_results/<code>.json`.
2. The JSON includes all required reasoning fields:
   - `trend_reasoning`
   - `position_reasoning`
   - `volume_reasoning`
   - `abnormal_move_reasoning`
   - `signal_reasoning`
3. The JSON includes all required score fields under `scores`:
   - `trend_structure`
   - `price_position`
   - `volume_behavior`
   - `previous_abnormal_move`
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

- `screen` reads one year of `daily_market` OHLCV data, computes the B1-derived fields locally, and writes candidate JSON.
- `chart` fetches one year of real symbol history for each candidate and writes `<code>_day.png`.
- `review` currently writes a baseline local structured scoring result in a schema that also reserves `llm_review` for future subagent output.
- The baseline review returns `trend_structure`, `price_position`, `volume_behavior`, `previous_abnormal_move`, `total_score`, `signal_type`, `verdict`, and a short Chinese comment.
- `run` chains `screen`, `chart`, and `review`, while emitting stage progress and elapsed time to `stderr`.

## Future Upgrade Path

- The intended end state is multimodal subagent chart review driven by `references/prompt.md`.
- Keep the deterministic `screen` and `chart` stages unchanged and swap only the `review` stage orchestration.

## Bundled References

- `references/b1-selector.md`
- `references/prompt.md`
- `references/review-rubric.md`
- `references/runtime-layout.md`
