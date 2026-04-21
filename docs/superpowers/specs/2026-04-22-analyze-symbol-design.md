# Analyze Symbol Design

## Goal

Add a new CLI command, `analyze-symbol`, so callers can run a deterministic single-stock end-of-day analysis for one explicitly named symbol without depending on the candidate-pool workflow.

The first implementation pass only supports `b2`.

## Scope

In scope:

- add `stock-select analyze-symbol`
- support `--method b2`
- require explicit `--symbol`
- allow optional `--pick-date`
- resolve the effective end-of-day date to the latest complete trade date when `--pick-date` is omitted
- fetch one year of daily history for the symbol from PostgreSQL
- compute the same deterministic `b2` signal state used by screening
- compute the same deterministic baseline review used by `review --method b2`
- export a single daily chart PNG for the symbol
- write one structured JSON result file under an `ad_hoc` runtime directory
- keep the command independent from candidate files, chart directories, review directories, and `review-merge`

Out of scope:

- supporting `b1`, `dribull`, or `hcr` in the first pass
- supporting `--intraday`
- supporting `--name` lookup in the first pass
- adding LLM review dispatch or `review-merge` integration
- changing the existing `screen`, `chart`, `review`, `run`, or `custom pool` command behavior

## Why a New Command

The current workflow is candidate-driven:

- `screen` writes only selected candidates
- `chart` renders only symbols from the candidate file
- `review` scores only symbols listed in the candidate file

That contract works for pool-based screening, but it cannot reliably answer the question “score this one stock even if it did not enter the candidate set.”

Using `--pool-source custom` with one stock is not sufficient because it still routes through the same candidate contract. If the stock does not trigger `B2`, `B3`, `B3+`, `B4`, or `B5`, downstream `chart` and `review` do not produce a per-stock result.

`analyze-symbol` should therefore be a separate command with separate runtime output and no dependency on candidate artifacts.

## CLI Contract

New command:

```bash
uv run stock-select analyze-symbol --method b2 --symbol 002350.SZ [--pick-date YYYY-MM-DD] [--dsn postgresql://...]
```

Options in the first pass:

- `--method`
- `--symbol`
- `--pick-date`
- `--dsn`
- `--runtime-root`
- `--progress/--no-progress`

Rules:

- `--method` is required and only `b2` is accepted in the first pass.
- `--symbol` is required.
- `--pick-date` is optional.
- if `--pick-date` is omitted, the command resolves the latest complete trade date on or before the command execution date
- `--intraday` is not accepted by this command in the first pass
- `--name` is not accepted by this command in the first pass

The command writes the result path to stdout, consistent with other CLI commands in this repository.

## Runtime Layout

The command writes outputs under:

```text
runtime/ad_hoc/<pick_date>.<method>.<code>/
```

The first pass writes:

- `runtime/ad_hoc/<pick_date>.b2.<code>/result.json`
- `runtime/ad_hoc/<pick_date>.b2.<code>/<code>_day.png`

This runtime area is intentionally separate from:

- `runtime/candidates/`
- `runtime/charts/`
- `runtime/reviews/`

because the command does not participate in the pool-based workflow.

## Result Contract

`result.json` should contain:

- `code`
- `pick_date`
- `method`
- `signal`
- `selected_as_candidate`
- `screen_conditions`
- `latest_metrics`
- `baseline_review`
- `chart_path`

### Field Semantics

#### `signal`

The resolved deterministic `b2` signal for the target date:

- `B2`
- `B3`
- `B3+`
- `B4`
- `B5`
- `null`

#### `selected_as_candidate`

Boolean shorthand for whether `signal` is non-null.

This field must not be inferred from `baseline_review.verdict`.

#### `screen_conditions`

The latest-row condition flags from the deterministic `b2` signal frame:

- `pre_ok`
- `pct_ok`
- `volume_ok`
- `k_shape`
- `j_up`
- `tr_ok`
- `above_lt`
- `raw_b2_unique`
- `cur_b2`
- `cur_b3`
- `cur_b3_plus`
- `cur_b4`
- `cur_b5`

This keeps the command explainable when a symbol is not selected.

#### `latest_metrics`

Minimal latest-bar metrics needed for inspection:

- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `pct`
- `volume`
- `j`

#### `baseline_review`

The existing `b2` baseline review payload returned by `review_b2_symbol_history(...)`.

This keeps score calculation and comment generation aligned with the current `b2` review contract and avoids a second, partially duplicated single-stock scoring path.

#### `chart_path`

Absolute path to the generated daily chart PNG.

## Behavioral Rules

The command must always return both layers of outcome:

1. screening-style outcome
   - `signal`
   - `selected_as_candidate`
   - `screen_conditions`
2. review-style outcome
   - `baseline_review.total_score`
   - `baseline_review.signal_type`
   - `baseline_review.verdict`
   - `baseline_review.comment`

This distinction is the core product requirement.

The command must not collapse these into one field or imply that a missing `signal` automatically means the same thing as `baseline_review.verdict = FAIL`.

## Architecture

### CLI Layer

Add a new command handler in `src/stock_select/cli.py`:

- validate command-line options
- normalize and validate `method`
- normalize and validate `symbol`
- create a progress reporter
- call an internal implementation helper
- surface user-facing errors as `typer.BadParameter`

### Implementation Helper

Add a dedicated helper in `src/stock_select/cli.py` for the first pass:

- `_analyze_symbol_impl(...)`

Responsibilities:

1. resolve DSN
2. connect to PostgreSQL
3. resolve effective `pick_date`
4. fetch symbol history for the one-year lookback window
5. build the deterministic `b2` signal frame
6. resolve the latest `signal`
7. export the daily chart PNG
8. compute the baseline review using the existing `b2` reviewer
9. assemble the output JSON payload
10. write `result.json`

This helper is intentionally separate from `_screen_impl`, `_chart_impl`, and `_review_impl` because it has a different contract and no artifact dependencies.

## Reused Repository Logic

The command should reuse existing repository code wherever possible.

Reuse:

- `fetch_nth_latest_trade_date(...)` for default trade-date resolution
- `fetch_symbol_history(...)` for historical data access
- `_prepare_chart_data(...)` plus `export_daily_chart(...)` for chart generation
- `_build_b2_signal_frame(...)` and `_resolve_signal(...)` for deterministic latest-row signal evaluation
- `review_b2_symbol_history(...)` for baseline score, verdict, and comment generation

Do not:

- recreate a second `b2` scoring implementation inside the new command
- generate ad hoc chart data differently from existing chart output
- hand-maintain a second schema for baseline review output

## Error Handling

User-facing errors should be clear and specific.

Minimum cases:

- unsupported method in the first pass
- missing `--symbol`
- no resolved DSN
- no trade date found on or before the requested date
- no history for the requested symbol in the required lookback window
- no row present on the effective `pick_date`
- chart export failure

The command should raise `typer.BadParameter` for user-correctable input and artifact issues, consistent with the existing CLI style.

## Testing

Follow TDD and add CLI-focused tests before implementation.

Minimum coverage:

- `analyze-symbol` rejects unsupported methods in the first pass
- `analyze-symbol` requires `--symbol`
- omitted `--pick-date` resolves to the latest available trade date
- the command fetches one symbol history window and does not depend on candidate artifacts
- the command writes chart and result outputs under `runtime/ad_hoc/<pick_date>.b2.<code>/`
- the result payload includes both `selected_as_candidate` and `baseline_review`
- the command still writes a baseline review when `signal` is null
- empty history or missing target-date rows fail clearly

At least one CLI contract test should validate that the stdout path points to `result.json`.

## Verification

Implementation verification should include at minimum:

```bash
uv run pytest tests/test_cli.py -k "analyze_symbol" -v
uv run stock-select analyze-symbol --help
```

If a live PostgreSQL instance is available, run one real command against a known symbol and confirm:

- stdout is a `result.json` path
- the JSON contains the expected top-level fields
- the PNG chart file exists

## Skill Follow-Up

After this command exists and is verified, add a separate skill for single-stock analysis rather than overloading the current `stock-select` skill.

That future skill should instruct agents to prefer `analyze-symbol` for requests such as:

- “看看这只票按 b2 怎么评分”
- “参考 b2 方法分析北京科锐”
- “即使没入选，也帮我看这只股票的评级”

This follow-up is intentionally out of scope for the first implementation pass.

## Future Extension Path

If the command proves stable, later changes can add:

- method expansion to `b1`, `dribull`, and `hcr`
- optional `--name` resolution with explicit ambiguity handling
- optional additive metadata such as `name`
- optional shared implementation extraction out of `cli.py` if multi-method logic grows

The first pass should stay narrow and avoid speculative generalization.
