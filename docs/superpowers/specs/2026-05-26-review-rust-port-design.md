# stock-select-rs Review Rust Port Design

## Goal

Replace the Python `review` stage with Rust without changing final user-facing results. The Rust port must reproduce Python baseline review artifacts before `stock-select-rs run` stops delegating review to Python.

The first target is `b1` end-of-day review because `b1 screen` and hybrid `b1 run` already have golden parity for `2026-05-25`.

## Current State

Rust implements:

- PostgreSQL daily market read for screen.
- Prepared indicator cache for screen.
- `b1`, `b2`, and `dribull` screen candidate generation.
- Hybrid `run`: Rust screen, Python chart, Python review.
- Review golden comparison through `scripts/compare_review.py`.

Rust does not yet implement:

- market environment evaluation/history
- method environment profiles
- baseline review scoring
- MACD wave review context
- `llm_review_tasks.json` generation
- per-stock review JSON generation
- summary recommendation/exclusion ordering

Python review remains the source of truth until golden parity passes per stock.

## Required Python-to-Rust Module Mapping

### `review_protocol.py` -> `src/review_protocol.rs`

Rust responsibilities:

- score weights and score validation
- `compute_weighted_total`
- `compute_weighted_total_for_profile`
- b1/b2 weighted total helpers
- signal type inference
- verdict inference
- stable rounding behavior matching Python `round(value, 2)`

Acceptance:

- unit tests cover every weight set
- Python fixture scores produce identical totals and verdicts
- invalid score values return typed errors

### `environment_profiles.py` -> `src/environment_profiles.rs`

Rust responsibilities:

- `MethodEnvironmentProfile`
- `get_method_environment_profile(method, state)`
- b1/b2 profile weights, thresholds, `subscore_mode`, and `llm_focus`

Acceptance:

- all Python profile constants are mirrored exactly
- unsupported method/state errors match the Python behavior in meaning
- b1 weak/neutral/strong profile tests assert weights, thresholds, and `llm_focus`

### `market_environment.py` -> `src/market_environment.rs`

Rust responsibilities:

- read/write `runtime/environment/history.jsonl`
- read/write `runtime/environment/latest.json`
- resolve environment for a pick date
- support manual override payload shape
- later: evaluate market environment from index data

Initial scope:

- Implement history loading and `resolve_market_environment`.
- Do not implement automatic market environment evaluation in the first review port.
- If no environment exists and no manual state is provided, Rust review should fail with a clear error until evaluation is ported.

Rationale:

Python `screen` currently calls `ensure_market_environment`; Rust `screen` does not. The first Rust review port should avoid silently inventing a default environment because b1 scoring and gates are profile-sensitive.

Acceptance:

- fixtures for `history.jsonl`, `latest.json`, interval overlap, and manual override priority match Python tests
- `stock-select-rs run --environment-state weak --environment-reason ...` remains enough for golden b1 review parity

### `review_resolvers.py` -> `src/review_resolvers.rs`

Rust responsibilities:

- map method to reviewer implementation
- map method to prompt path
- expose supported review methods

Initial scope:

- `b1` only for native review
- `b2` and `dribull` continue to use Python bridge until their reviewers are ported

Acceptance:

- `b1` resolves to the b1 reviewer and prompt-b1 path
- unsupported native review method returns a clear error or falls back to Python only if explicitly configured

### `analysis/macd_waves.py` -> `src/analysis/macd_waves.rs`

Rust responsibilities:

- MACD state machine
- daily MACD trend classification
- weekly MACD trend classification
- wave labels and reason strings used by comments and LLM task context

Acceptance:

- fixture close series produce identical current state, wave index, labels, pass/fail flags, and reason strings
- tests include weekly aggregation and daily classification
- output structs serialize into the same task context strings used by Python review

### `reviewers/b1.py` -> `src/reviewers/b1.rs`

Rust responsibilities:

- compute b1 baseline review for one symbol history
- compute trend, price position, volume, previous abnormal move, MACD phase
- apply b1 high-return combo logic
- apply environment verdict gates
- compute watch reason, watch score, score layer
- build final per-stock review payload

Acceptance:

- for all 104 `2026-05-25 b1` candidates, per-stock stable fields match Python:
  - `trend_structure`
  - `price_position`
  - `volume_behavior`
  - `previous_abnormal_move`
  - `macd_phase`
  - `raw_total_score`
  - `total_score`
  - `signal_type`
  - `verdict`
  - `watch_reason`
  - `watch_score`
  - `watch_tier`
  - `score_combo_key`
  - `high_return_combo_match`
  - `pass_family`
  - `pass_family_tier`
  - `gate_flags`
  - `score_layer`
  - `score_layer_score`
  - `yellow_b1`
- comments match exactly for b1 baseline output

## Review Orchestration

Add a native review command after the module fixtures pass:

```text
stock-select-rs review --method b1 --pick-date DATE --runtime-root ROOT [--environment-state STATE --environment-reason TEXT]
```

Native review should:

1. Read `candidates/<pick_date>.b1.json`.
2. Resolve environment:
   - manual `--environment-state` wins
   - otherwise resolve existing runtime environment history
   - if neither is available, fail clearly in the first native version
3. Fetch one year of symbol history for candidates from PostgreSQL.
4. Run `reviewers::b1`.
5. Write per-stock JSON files.
6. Write `summary.json`.
7. Write `llm_review_tasks.json`.

`stock-select-rs run` should keep using Python review until this command passes golden tests.

## Artifact Contract

Native review must write the same paths as Python:

```text
reviews/<pick_date>.<method>/<code>.json
reviews/<pick_date>.<method>/summary.json
reviews/<pick_date>.<method>/llm_review_tasks.json
```

Path-valued fields such as `chart_path` may include the active runtime root. Golden comparison should ignore root-specific path prefixes and compare stable business fields.

## Golden Test Strategy

Use existing Python runtime artifacts under:

```text
~/.agents/skills/stock-select/runtime
```

Do not recompute Python screen during review port validation unless explicitly requested.

For each Rust native review milestone:

```bash
python3 scripts/compare_screen.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-native-review-b1 \
  --pick-date 2026-05-25 \
  --method b1

python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-native-review-b1 \
  --pick-date 2026-05-25 \
  --method b1
```

Acceptance before replacing Python review in `run`:

- screen comparison passes
- review comparison passes
- `cargo fmt --check && cargo test --quiet` passes
- native review writes 104 per-stock JSON files for `2026-05-25 b1`
- native review summary has `reviewed_count=104` and recommendation codes `000066.SZ`, `300292.SZ`, `301290.SZ`

## Phased Implementation

### Phase 1: Constants and Pure Scoring

Implement:

- `environment_profiles.rs`
- `review_protocol.rs`

This phase has no DB or file IO and should be fully unit-tested.

### Phase 2: MACD Wave Port

Implement:

- `analysis/macd_waves.rs`
- fixture tests for daily and weekly trend classification

This phase is the highest algorithmic risk because many b1 comments and gates depend on wave labels.

### Phase 3: b1 Reviewer

Implement:

- `reviewers/mod.rs`
- `reviewers/b1.rs`
- b1 per-symbol fixture tests

Use Rust-native series operations first. Introduce Polars only if it reduces complexity for rolling/window calculations without changing pandas semantics.

### Phase 4: Native Review CLI

Implement:

- `review` subcommand for b1
- JSON artifact writers
- summary and task generation
- comparison-script validation

### Phase 5: Run Switch

Only after golden parity:

- update `run` to use native Rust review for b1 by default
- keep Python review fallback behind an explicit option while b2/dribull remain bridged

## Environment Profile Status

Environment profile is implemented in Python today, not in Rust.

Current Rust hybrid behavior:

- accepts manual `--environment-state`
- accepts manual `--environment-reason`
- forwards both to Python review
- does not auto-evaluate environment
- does not apply profile-specific score weights or gates itself

Native Rust review must include `environment_profiles.rs` and at least environment history resolution before it can replace Python review.

## Self-Review

- No placeholders remain.
- The design keeps review replacement behind golden parity.
- The environment profile gap is explicit and included in the port scope.
- The first native review scope is b1 only, matching the existing aligned workflow.
