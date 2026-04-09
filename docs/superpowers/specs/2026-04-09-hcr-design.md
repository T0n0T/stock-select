# HCR Method Design

## Goal

Add a new deterministic screening method named `hcr` to the existing `stock-select` CLI so it is supported as a first-class peer of `b1` instead of a `b1` variant.

`hcr` stands for:

`Historical High & Center Resonance Breakout`

The new method must:

- be selectable through the existing `--method` flag
- run through the existing `screen`, `chart`, `review`, `run`, and `render-html` workflow
- preserve the current end-to-end runtime layout
- keep existing `b1` behavior unchanged
- update the repository skill file so the operational instructions reflect the new multi-method workflow

## Scope

In scope:

- support `--method hcr` anywhere the CLI currently accepts `--method b1`
- refactor method dispatch so `b1` and `hcr` are both valid first-class methods
- add deterministic `hcr` preprocessing and screening logic
- preserve candidate, chart, review, and summary artifact shapes
- generalize method-specific labels in user-facing output where the text is currently hard-coded to `B1`
- add automated coverage for the new method and the expanded CLI contract
- update `.agents/skills/stock-select/SKILL.md` so the documented workflow no longer claims that only `b1` exists

Out of scope:

- changing the existing `b1` formula or thresholds
- introducing method-specific chart styles
- changing the multimodal review rubric
- redesigning the runtime directory structure
- adding configuration files or user-supplied `hcr` threshold overrides in this first version

## Current Problem

The current repository is structurally centered on `b1`:

- the CLI rejects every method other than `b1`
- screening helpers live in `src/stock_select/b1_logic.py`
- runtime metadata and summary output assume `b1`
- the skill file explicitly requires `--method b1`

This prevents adding `hcr` as a real peer method. A direct one-off `elif method == "hcr"` patch would make the new method runnable, but it would leave the method boundary unclear and would make the next strategy addition harder.

## Design

### 1. Method Contract

The CLI should accept:

- `--method b1`
- `--method hcr`

Every command that already requires a method should continue to require one, but method validation should move from a `b1`-only guard to a shared supported-method check.

The runtime artifact payloads should continue to include a `method` field, and that field must now always reflect the true method used for the run.

No new runtime roots are needed. Existing paths remain valid:

- `runtime/candidates/<pick_date or run_id>.json`
- `runtime/prepared/<pick_date or run_id>.pkl`
- `runtime/charts/<pick_date or run_id>/`
- `runtime/reviews/<pick_date or run_id>/`

### 2. Strategy Architecture

The implementation should stop treating `b1` as the only built-in strategy and instead introduce a small method-dispatch layer.

Recommended structure:

- `src/stock_select/strategies/common.py`
- `src/stock_select/strategies/b1.py`
- `src/stock_select/strategies/hcr.py`

The exact filenames may vary, but the design requires these boundaries:

- common market preprocessing helpers that are reusable across strategies
- method-specific preparation logic
- method-specific screen execution logic
- a shared registry or dispatch map keyed by method name

The CLI should ask the registry for the selected method rather than branching on hard-coded method names throughout the file.

This keeps `b1` unchanged while giving `hcr` a clean home and makes a future third strategy additive instead of invasive.

### 3. HCR Formula Semantics

The source formula is a Tongdaxin stock-picking expression:

```text
YX:=IF(CURRBARSCOUNT<=30,CONST((HHV(H,30)+LLV(L,30))/2),DRAWNULL);
常数:=CONST(REF(HHV(H,300),60));
天数:=BARSLAST(常数=H);
P:=IF(BARSLAST(CURRBARSCOUNT-1=CONST(天数))>=0,常数,DRAWNULL);
XG:ABS(YX-P)<0.05 AND C>1.0 AND C>YX;
```

For the Python implementation, the agreed behavior is:

- keep the structural meaning of the formula
- replace the absolute tolerance with a relative tolerance
- define the resonance condition as `abs(YX - P) / abs(P) <= 0.015`

The resulting daily pick condition is:

1. compute `YX` as the midpoint of the recent 30-bar range:
   - `YX = (HHV(high, 30) + LLV(low, 30)) / 2`
2. compute `P` from the Tongdaxin `CONST(REF(HHV(H,300),60))` semantics:
   - first compute the rolling 300-bar high
   - shift that series backward by 60 bars
   - take the end-of-series constant result as one fixed reference price for the symbol
3. require resonance:
   - `abs(YX - P) / abs(P) <= 0.015`
4. require price floor:
   - `close > 1.0`
5. require breakout over the center line:
   - `close > YX`

`P` is intentionally treated as a symbol-level constant reference derived from the end-of-series result, because that best matches the Tongdaxin `CONST(...)` behavior the user approved for this repository.

### 4. HCR Data Requirements

`hcr` needs more history than `b1` for the reference-price calculation:

- `YX` needs 30 bars
- `P` needs a 300-bar high series and then a 60-bar backward reference

That means a target day needs roughly 360 valid bars of history for a stable evaluation.

The existing end-of-day screen window of about one year of trading data is usually sufficient, but the implementation must explicitly track insufficient history for `hcr` instead of silently treating missing values as a normal filter failure.

Required behavior:

- if `YX` or `P` cannot be computed on the target day, count the symbol under an `hcr` insufficient-history failure bucket
- do not misclassify missing-history cases as failed resonance or failed breakout

### 5. Preprocessing Model

The current repository already builds prepared per-symbol daily frames before screening. `hcr` should reuse that pattern.

The prepared frame for `hcr` should include at minimum:

- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `volume` or `vol`
- `turnover_n`
- `yx`
- `p`
- `resonance_gap_pct`

`turnover_n` should remain available in the prepared frame and candidate output for consistency with current payloads and downstream display, even though `hcr` itself does not depend on the `b1` liquidity-pool gate.

`hcr` should not inherit the `b1` top-turnover prefilter in this first version. The method should evaluate all prepared symbols for the target day.

### 6. Candidate Output

The candidate output shape should remain compatible with the current workflow:

- `code`
- `pick_date`
- `close`
- `turnover_n`

The implementation may additionally include method-specific fields if that simplifies review or HTML display, but this is optional for v1. If optional fields are added, they should be additive rather than replacing the current keys.

Examples of acceptable optional fields:

- `yx`
- `p`
- `resonance_gap_pct`

### 7. Review, Chart, and Summary Compatibility

`chart` should remain method-agnostic. Once a candidate set exists, chart rendering can continue to use the same symbol-history rendering path.

`review` should remain method-agnostic at the orchestration level. The baseline local review can continue to score chart structure without introducing `hcr`-specific rubric branches in this change.

However, user-facing text must be generalized where it is currently hard-coded to `B1`. This includes at least:

- HTML page title
- dashboard heading
- any summary labels that imply the workflow only applies to `b1`

The result should be that a `hcr` run produces correct metadata and shareable artifacts without pretending that the underlying method was `b1`.

### 8. CLI Changes

The CLI design should preserve the existing command family:

- `screen`
- `chart`
- `review`
- `review-merge`
- `render-html`
- `run`

Required changes:

- replace the `b1`-only validator with shared method validation
- route `screen` to the correct strategy implementation based on `--method`
- preserve the existing runtime artifact contract for both end-of-day and intraday runs
- keep `chart`, `review`, `review-merge`, and `render-html` compatible with `method = hcr`

The `run` command should remain a thin orchestration wrapper that passes the selected method through all stages without forcing `b1`.

### 9. Intraday Compatibility

The repository now supports `--intraday` runs for the existing workflow. `hcr` should be designed so it can coexist with that architecture.

This design does not require fully implementing intraday `hcr` support immediately, but the method-dispatch refactor must not make intraday support structurally impossible.

If `hcr` is allowed in intraday mode during implementation, it should use the same temporary current-day bar overlay model as other methods and write the same style of mode-aware runtime artifacts.

If intraday `hcr` is deferred during implementation, the CLI must fail clearly rather than silently running `b1` logic.

### 10. Skill File Update

The implementation scope must include updating:

`.agents/skills/stock-select/SKILL.md`

The skill currently states that agents must always require `--method b1` and reject anything else. That becomes incorrect once `hcr` exists.

Minimum required skill updates:

- describe the workflow as supporting multiple built-in deterministic methods
- list `b1` and `hcr` as supported methods
- remove instructions that hard-reject all non-`b1` methods
- explain that `screen` must dispatch to the selected strategy while preserving the same runtime layout
- preserve the current intraday workflow documentation, but make it clear that method compatibility depends on the selected built-in strategy
- keep the review and merge runtime instructions method-agnostic

The skill file must stay aligned with the repository behavior in the same implementation task so future agent runs do not apply stale operational rules.

### 11. Error Handling

Required behavior:

- unsupported methods fail fast with a clear error that lists supported values
- `hcr` symbols with insufficient history are counted explicitly
- `hcr` must not divide by zero when evaluating `resonance_gap_pct`
- empty or malformed candidate payloads must still fail in the same places they fail today
- downstream commands must trust the candidate file `method` metadata rather than silently assuming `b1`

For the resonance calculation:

- if `P` is zero or missing, treat the row as non-evaluable and record insufficient history or invalid reference data rather than forcing a percentage gap

### 12. Testing

Required automated coverage:

- method validation accepts `b1` and `hcr` and rejects unknown values
- `screen --method hcr --pick-date YYYY-MM-DD` writes a valid candidate file
- the `run` command passes `hcr` through all stages
- `hcr` computes `YX` correctly from a 30-bar range midpoint
- `hcr` computes the symbol-level `P` reference consistently with the agreed `CONST(REF(HHV(H,300),60))` interpretation
- resonance passes when the gap is within `1.5%`
- resonance fails when the gap exceeds `1.5%`
- `close > 1.0` and `close > YX` are both enforced
- insufficient history is reported separately from resonance failure
- existing `b1` tests continue to pass unchanged
- HTML export and review summaries reflect the actual method name rather than hard-coded `B1`

## Recommended Implementation Direction

Use the structured refactor approach rather than a one-off `elif method == "hcr"` patch.

That means:

- keep `b1` behavior intact
- extract strategy dispatch into a shared layer
- implement `hcr` in its own module
- generalize CLI and summary surfaces from single-method to multi-method
- update the skill file in the same change

This is the smallest design that keeps the repository coherent once two peer methods exist.
