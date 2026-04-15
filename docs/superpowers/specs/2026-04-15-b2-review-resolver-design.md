# B2 Review Resolver Design

**Goal:** Decouple method-specific review behavior so `default` review remains the current baseline path, while `b2` gains a stronger baseline review implementation and a dedicated LLM review prompt without changing final review outputs.

**Scope:** Review-stage orchestration in the standalone `stock-select` repository, including baseline review selection, review task prompt selection, and skill documentation for multimodal chart review.

**Non-goals:**
- Changing `screen` behavior or `b2` screening formula
- Changing the final per-stock review JSON schema
- Changing `summary.json` schema
- Introducing method-specific `llm_review` validation or merge rules
- Changing the final `llm_review` output format expected by `review-merge`

## Context

Current review behavior is effectively hard-coded as one generic path:

- `review_symbol_history(...)` computes one baseline review shape for every method
- `build_review_payload(...)` always points to one shared prompt file
- `review-merge` assumes one fixed `llm_review` JSON shape and merge contract

This is sufficient for the original generic review flow, but it blocks method-specific review behavior. `b2` now needs two targeted changes:

1. a stronger baseline review scoring model aligned with `b2`'s structure
2. a dedicated chart-review prompt for subagents

At the same time, downstream consumers already rely on the current final review output shape, so the repository must preserve compatibility.

## Requirements

### 1. Resolver-based method selection

The review stage must stop assuming a single hard-coded baseline reviewer and a single hard-coded prompt.

Introduce a small method-aware resolver layer that returns:

- a stable resolver name, such as `default` or `b2`
- the baseline review function for the requested method
- the prompt path for the requested method

This resolver layer is only responsible for choosing review behavior. It is not responsible for merge logic, summary generation, or schema validation.

### 2. `default` remains the current behavior

The existing baseline review logic becomes the `default` resolver behavior.

Methods that do not have specialized review handling must continue to use:

- the current generic baseline review logic
- the current default chart-review prompt

For this change set, that means at least:

- `b1` uses `default`
- `hcr` uses `default`

### 3. `b2` gets a specialized baseline review

`b2` must resolve to a dedicated baseline review implementation that keeps the current output field names but changes the scoring logic to better reflect `b2` semantics.

The `b2` baseline review must continue to emit the existing baseline fields:

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `macd_phase`
- `total_score`
- `signal_type`
- `verdict`
- `comment`

The output field names and top-level review structure must remain compatible with the current repository contract.

### 4. `b2` gets a dedicated chart-review prompt

The repository must add a second prompt file specifically for `b2`.

`review` must write `llm_review_tasks.json` so that:

- `b1` and `hcr` continue to point at the current default prompt
- `b2` points at the new `b2` prompt

The prompt switch is metadata only. The repository does not implement actual LLM inference; it only prepares task payloads for external chart-review workers.

### 5. Final outputs must remain unchanged

The final output contract must remain compatible for all methods.

This includes:

- per-stock review files under `runtime/reviews/<key>.<method>/<code>.json`
- merged results written by `review-merge`
- `summary.json`
- HTML export input expectations

The repository may add internal metadata to support resolver selection if needed, but it must not break existing consumers of the final output.

### 6. `llm_review` schema stays shared

The `llm_review` payload shape, normalization rules, and merge rules must stay shared across methods.

Specifically:

- `normalize_llm_review(...)` remains method-agnostic
- `merge_review_result(...)` remains method-agnostic
- the expected LLM result JSON structure remains unchanged

The only method-specific LLM behavior in this scope is prompt selection.

## Proposed Architecture

### Public review contract

Keep these responsibilities in the shared review orchestration layer:

- building final review records
- normalizing LLM review payloads
- merging baseline and LLM reviews
- summarizing reviews

These functions remain shared because their output contract is intentionally method-independent.

### Resolver layer

Add a dedicated resolver module that maps `method` to a review configuration object.

That object should expose:

- `name`
- `review_history(...)`
- `prompt_path`

This layer becomes the only place that knows which review implementation or prompt belongs to each method.

### Baseline review implementations

Split baseline review implementations by responsibility:

- one implementation for the current generic/default behavior
- one implementation for `b2`

This prevents `review_orchestrator.py` from growing into a mixed protocol-plus-strategy file and keeps future method additions isolated.

## `b2` Baseline Review Semantics

The `b2` baseline review should become more aligned with the current `b2` setup and the earlier confirmed strategy language, while still producing the same field names.

### Trend structure

`b2` trend scoring should prioritize:

- support and re-acceptance around the 25-day line
- constructive behavior relative to the 60-day line
- the feel of a resumed up move after a reset, instead of only a generic rising MA stack

This is stricter than the current generic trend review that mainly looks at `ma20`, `ma60`, and recent gain.

### Price position

`b2` position scoring should prioritize:

- post-breakout retest quality
- second-entry or re-launch structure
- whether price looks like it is re-accepting a support area rather than merely sitting below recent highs

This should better capture the intended `b2` "restart" character.

### Volume behavior

`b2` volume scoring should put more weight on:

- earlier advance with expansion
- pullback with contraction
- absence of destructive heavy-volume down bars

This is stronger than the current generic logic because `b2` explicitly values shrink-on-retest behavior.

### Previous abnormal move

`b2` should still identify whether the chart shows a meaningful earlier abnormal move or sponsor-like initiation, but must avoid over-rewarding charts that have already completed an extended major run.

### MACD phase

`b2` MACD scoring should remain within the existing 1-5 scoring framework, but should better reflect:

- whether daily momentum still looks constructive instead of decaying
- whether multi-timeframe MACD context appears supportive rather than contradictory
- whether the chart looks early or mid-phase rather than late-stage exhaustion

The score output remains the same field and range; only the scoring criteria change.

### Signal type and verdict

`signal_type` remains limited to the current shared enum:

- `trend_start`
- `rebound`
- `distribution_risk`

`b2` does not introduce a new signal type.

`verdict` remains limited to:

- `PASS`
- `WATCH`
- `FAIL`

This preserves merge and summary compatibility.

## CLI Flow Changes

Both end-of-day and intraday review flows must:

1. resolve the review configuration for the requested method
2. call the resolved baseline review function
3. build review task payloads with the resolved prompt path
4. continue using the shared result-building and summary logic

No resolver-specific behavior should be introduced in `review-merge`.

## Files

### New files

- `src/stock_select/review_resolvers.py`
  - method-to-review resolver mapping
- `src/stock_select/reviewers/default.py`
  - current generic baseline review logic extracted into a default reviewer
- `src/stock_select/reviewers/b2.py`
  - `b2`-specific baseline review logic
- `.agents/skills/stock-select/references/prompt-b2.md`
  - dedicated multimodal chart-review prompt for `b2`

### Modified files

- `src/stock_select/review_orchestrator.py`
  - keep shared protocol logic only
  - stop owning hard-coded prompt selection and baseline review strategy
- `src/stock_select/cli.py`
  - resolve reviewer/prompt by method in both review entry points
- `.agents/skills/stock-select/SKILL.md`
  - document that `b2` chart review must use `prompt-b2.md`
- tests covering review orchestration and CLI review task generation

## Testing Requirements

### Resolver tests

Add tests that verify:

- `b1` resolves to `default`
- `hcr` resolves to `default`
- `b2` resolves to `b2`
- the resolved prompt path matches the correct file for each method

### Baseline review tests

Keep current tests that prove the default review behavior.

Add focused `b2` review tests that verify at least:

- a constructive shrink-on-retest setup scores materially better than a damaged setup
- a weak or distribution-like setup gets a weaker `volume_behavior`, `macd_phase`, or final verdict

The tests should assert behavior through the shared output fields rather than relying on internal helper implementation details.

### CLI tests

Add tests that verify:

- `review --method b1` writes tasks pointing to the default prompt
- `review --method b2` writes tasks pointing to `prompt-b2.md`
- top-level review JSON remains compatible
- `review-merge` continues to accept and merge `b2` LLM outputs using the existing shared schema

## Compatibility Rules

This design must preserve the following invariants:

- no change to the final top-level review file shape
- no change to `llm_review` result payload shape
- no change to merge weighting behavior unless explicitly requested in a separate change
- no method-specific branch added to `review-merge`
- no requirement for external LLM workers to emit different JSON for `b2`

## Risks

### Risk: resolver split without real isolation

If method-specific logic remains partly hard-coded in `cli.py` or `review_orchestrator.py`, the new resolver layer becomes cosmetic. The implementation should ensure prompt selection and baseline review selection both flow through the resolver layer.

### Risk: `b2` review becomes overfit to hidden indicator data

The baseline `b2` review should remain grounded in the prepared history already available to the repository and must still produce stable deterministic output. It should not quietly create a second screening stage with unrelated rules.

### Risk: prompt divergence without skill update

If the repository writes `prompt-b2.md` in tasks but the skill instructions still tell workers to use only the old prompt, runtime behavior will diverge from repository intent. The skill file must explicitly document the method-specific prompt rule.

## Implementation Direction

The implementation should favor a minimal, explicit resolver design:

- one place for method-to-review mapping
- shared output contract untouched
- `b2` specialization only where it adds signal quality: baseline scoring and prompt guidance

This is enough to decouple review behavior now without turning the review pipeline into a full strategy framework before it is needed.
