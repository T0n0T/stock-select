# LLM Baseline Threshold Design

## Goal

Allow `review` and `run` workflows to reduce LLM chart-review volume by filtering `llm_review_tasks.json` with a baseline score threshold.

The baseline review stage should still score every candidate. The threshold controls only which already-scored candidates are handed to LLM review.

## Current Problem

The current `review` workflow does this for every candidate with a chart:

1. run deterministic baseline review
2. write the per-symbol review JSON
3. append one entry to `llm_review_tasks.json`
4. write `summary.json`

When baseline produces many candidates, the generated task file can ask the LLM to review symbols that the deterministic review already considers low quality. This wastes review time and context without improving the final selection much.

## Design Decision

Add an optional CLI threshold:

```bash
--llm-min-baseline-score FLOAT
```

When the option is omitted, behavior remains unchanged: every successfully baseline-reviewed candidate is included in `llm_review_tasks.json`.

When the option is provided, only candidates whose baseline `total_score` is greater than or equal to the threshold are included in `llm_review_tasks.json`.

This filtering belongs in the review task generation layer, not in screen or chart, because:

- the filter depends on baseline review output
- baseline review artifacts remain useful even for skipped LLM candidates
- screen and chart should continue to represent deterministic candidate generation, not LLM dispatch policy

## Scope

In scope:

- add `--llm-min-baseline-score` to `review`
- add `--llm-min-baseline-score` to `run` and pass it into the review step
- support both end-of-day and intraday review flows
- preserve all baseline review JSON files and `summary.json` contents
- filter only `llm_review_tasks.json`
- add focused test coverage for end-of-day, intraday, and `run`

Out of scope:

- changing baseline scoring formulas
- changing final summary recommendation thresholds
- changing `review-merge`
- deleting or hiding low-score baseline review files
- adding verdict-based filtering
- adding method-specific default thresholds
- changing chart generation

## Rule Semantics

For every candidate that reaches baseline review:

1. write the per-symbol baseline review result exactly as today
2. include the review in the summary input exactly as today
3. compute `baseline_score = float(review["total_score"])`
4. include the candidate in `llm_review_tasks.json` when either:
   - no threshold was provided
   - `baseline_score >= llm_min_baseline_score`

Candidates skipped by the threshold are not failures. They remain ordinary baseline-reviewed candidates and may still appear in `summary.json` recommendations or excluded lists according to existing summary rules.

## CLI Contract

End-of-day review:

```bash
stock-select review --method b2 --pick-date 2026-04-24 --llm-min-baseline-score 4.0
```

Intraday review:

```bash
stock-select review --method b2 --intraday --llm-min-baseline-score 4.0
```

Full run:

```bash
stock-select run --method b2 --pick-date 2026-04-24 --llm-min-baseline-score 4.0
```

The option should reject negative values because baseline and LLM scores are normalized non-negative values. A value of `0` is valid and effectively includes all normally scored candidates.

## Artifact Behavior

Per-symbol review files:

- unchanged
- still written for every successfully baseline-reviewed candidate
- keep `review_mode="baseline_local"` until a later merge succeeds

`summary.json`:

- unchanged in structure
- still summarizes all baseline-reviewed candidates
- still uses the existing recommendation threshold and verdict logic

`llm_review_tasks.json`:

- same top-level structure as today
- `tasks` contains only candidates that pass the optional threshold
- each included task keeps existing fields such as `rank`, `baseline_score`, `baseline_verdict`, `prompt_path`, and method-specific wave context

Progress logging:

- keep existing candidate progress messages
- final review progress should report reviewed count, failures count, LLM task count, and threshold-skipped count

## Implementation Shape

Add a small helper that centralizes threshold behavior, for example:

```python
def _should_include_llm_review_task(review: dict[str, object], threshold: float | None) -> bool:
    ...
```

Use the helper in both `_review_impl(...)` and `_review_intraday_impl(...)` immediately before appending to `llm_review_tasks`.

Thread the optional threshold through:

- `review(...)`
- `run_all(...)`
- `_review_impl(...)`
- `_review_intraday_impl(...)`

Do not change `build_review_payload(...)`, `build_review_result(...)`, or `summarize_reviews(...)`; those functions should remain independent of dispatch policy.

## Edge Cases

### Missing Charts

Candidates skipped because their chart file is missing should continue to be recorded as failures and should not run baseline review. The threshold does not affect this behavior.

### Missing Intraday Prepared History

Intraday candidates without prepared history should continue to be recorded as failures. The threshold does not affect this behavior.

### Invalid Scores

Baseline review normally emits numeric `total_score`. If conversion to float fails, the review command should fail instead of silently dispatching or skipping an ambiguous candidate.

### Empty LLM Task List

It is valid for `llm_review_tasks.json` to contain an empty `tasks` list when all baseline scores are below the threshold. The command should still succeed because baseline review completed.

## Test Plan

Add focused tests in [tests/test_cli.py](/home/pi/Documents/agents/stock-select/tests/test_cli.py).

### End-of-Day Review

Create two candidates with baseline scores on opposite sides of the threshold. Verify:

- both per-symbol review files are written
- `summary.json` includes both reviewed candidates through existing summary behavior
- `llm_review_tasks.json` includes only the candidate with `baseline_score >= threshold`

### Intraday Review

Create two intraday candidates backed by prepared history and thresholded baseline scores. Verify:

- both baseline review files are written
- only the passing candidate appears in `llm_review_tasks.json`

### Run Command

Patch `_review_impl(...)` or `_review_intraday_impl(...)` in a `run` test and verify `run` forwards `llm_min_baseline_score` into the review step.

### Default Compatibility

Verify that when `--llm-min-baseline-score` is omitted, `llm_review_tasks.json` includes all successfully baseline-reviewed candidates as it does today.

### Invalid Threshold

Verify that a negative `--llm-min-baseline-score` is rejected at the CLI boundary.

## Expected Outcome

After this change:

- users can keep the deterministic baseline review complete
- low-score candidates can be excluded from LLM review without losing baseline artifacts
- existing workflows remain unchanged unless the new option is provided
- end-of-day and intraday review behavior stays aligned
