# Stock Select Design

## Goal

Create a global skill named `stock-select` under `~/.agents/skills/stock-select` that:

- reads A-share market data directly from the PostgreSQL database used by `stock-cache`
- reproduces the repository's current `B1` quantitative preselection without using an LLM
- generates daily chart images for selected candidates
- instructs the main agent to spawn multimodal subagents to review each candidate chart in parallel
- aggregates subagent outputs into a final conclusion report

The first version only supports `B1`. Any other selection method must be rejected explicitly.

## Scope

Included:

- direct database reads from the `stock-cache` PostgreSQL schema
- `B1` screening in a Python CLI
- chart generation for candidate stocks
- subagent-based multimodal review
- structured output files in the skill runtime directory

Excluded from v1:

- `Brick` strategy support
- dependence on `stock-cache read` CLI
- dependence on this repository's runtime paths such as `data/raw` or `data/review`
- binding the review stage to a specific model vendor such as Gemini

## Source Assessment

The installed `stock-cache` package schema is sufficient to use PostgreSQL tables as the primary data source for `B1`.

Relevant tables:

- `daily_market`
  - fields include `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount`, `turnover_rate`, `total_mv`
- `daily_indicators`
  - fields include `ts_code`, `trade_date`, `kdj_k`, `kdj_d`, `kdj_j`, `macd`
- `instruments`
  - symbol metadata and name lookup support

This covers the stored market data needed for `B1`. The remaining `B1` features must be recomputed locally in the new CLI:

- 知行线: `zxdq`, `zxdkx`
- 周线均线多头排列
- 最大成交量日非阴线过滤
- rolling liquidity metric compatible with current `turnover_n`

## Functional Architecture

The system is divided into two deterministic stages and one agentic stage.

### 1. Deterministic Screening

A Python CLI reads market rows from PostgreSQL, reconstructs the `B1` signal, and writes candidate outputs.

Responsibilities:

- query the database for the requested date window and symbols
- normalize field names and types
- calculate derived fields needed by `B1`
- resolve `pick_date`
- build the liquidity pool
- evaluate the `B1` selector
- write candidate JSON and run metadata

This stage does not use any LLM.

### 2. Deterministic Chart Export

A Python chart exporter renders daily chart images for the screened candidates.

Responsibilities:

- load candidate list from runtime outputs
- load full daily history for each candidate from PostgreSQL
- render daily chart images compatible with the current repository's review flow
- write chart files into the runtime chart directory

The chart appearance should follow the current repository's charting logic closely enough that the existing review prompt remains applicable.

### 3. Agentic Review

The main agent orchestrates multimodal review using subagents.

Responsibilities:

- read candidate list and chart file paths
- spawn one or more subagents in parallel for per-stock review
- provide each subagent with the review rubric derived from the repository's current chart-review prompt
- let the agent framework choose the actual multimodal model
- collect structured per-stock review JSON
- aggregate recommendations and exclusions into a final summary

The skill must explicitly instruct the main agent to use subagents for review rather than reviewing all candidates serially in the main thread.

## B1 Logic To Reproduce

The new CLI must reproduce the current repository's `B1` logic, based on the behavior implemented in `pipeline/Selector.py`.

Required screening conditions:

1. `KDJQuantileFilter`
   - pass when `J < j_threshold` or `J <= expanding historical quantile(j_q_threshold)`
2. `ZXConditionFilter`
   - require `close > zxdkx`
   - require `zxdq > zxdkx`
3. `WeeklyMABullFilter`
   - require weekly moving averages in bullish alignment
4. `MaxVolNotBearishFilter`
   - within the lookback window, the max-volume day must satisfy `close >= open`

Required supporting calculations:

- `turnover_n`
  - current repository behavior uses `(open + close) / 2 * volume` rolling sum
  - database column mapping must normalize `vol` to the volume field used in the computation
- KDJ values
  - prefer `daily_indicators.kdj_j` if fully available and compatible
  - otherwise compute locally for consistency
- `zxdq` and `zxdkx`
- weekly close series and weekly MA alignment

The default parameter set must mirror the repository's current `B1` defaults unless explicitly overridden by CLI options or a skill-local config file.

## CLI Design

The skill should ship a main script, for example `scripts/stock_select.py`, with the following command structure.

### `screen`

Reads PostgreSQL data and runs quantitative screening.

Required behavior:

- requires `--method b1`
- rejects unsupported methods
- supports `--pick-date YYYY-MM-DD`
- supports optional date-window arguments for fetching enough history
- writes candidate JSON and run metadata

### `chart`

Generates daily charts for candidates from the runtime candidate JSON.

Required behavior:

- reads candidate file for a pick date
- fetches enough daily history for plotting
- writes `<code>_day.jpg` files

### `review`

Runs multimodal review via subagents.

Required behavior:

- reads candidate list and chart outputs
- spawns parallel subagents
- passes the review rubric based on the repository prompt
- writes one JSON result per stock plus a final summary

### `run`

One-shot end-to-end execution.

Required behavior:

- runs `screen`
- runs `chart`
- runs `review`
- returns a final structured summary path

## Runtime Layout

The skill must not write into this repository's `data/` tree.

Default runtime root:

- `~/.agents/skills/stock-select/runtime/`

Recommended layout:

- `runtime/candidates/<pick_date>.json`
- `runtime/charts/<pick_date>/<code>_day.jpg`
- `runtime/reviews/<pick_date>/<code>.json`
- `runtime/reviews/<pick_date>/summary.json`
- `runtime/logs/<run_id>.log`

Candidate JSON should include:

- `pick_date`
- `method`
- `candidates`
- per-candidate `code`, `close`, `turnover_n`
- config snapshot and database query metadata

Review summary JSON should include:

- `pick_date`
- `method`
- `reviewed_count`
- `recommendations`
- `excluded`
- failures and skipped codes with reasons

## Code Organization

The skill should include bundled scripts instead of depending on imports from this repository.

Recommended script modules:

- `scripts/stock_select.py`
  - CLI entrypoint
- `scripts/db_access.py`
  - PostgreSQL connection and query helpers
- `scripts/b1_logic.py`
  - indicator calculations and `B1` filters
- `scripts/models.py`
  - dataclasses or typed structures for candidates and review results
- `scripts/charting.py`
  - daily chart generation
- `scripts/review_orchestrator.py`
  - subagent review dispatch and aggregation

Recommended references:

- repository `agent/prompt.md` as the rubric source for multimodal review behavior
- repository `pipeline/Selector.py` as the reference implementation for `B1`

## Error Handling

### Database Layer

Fail fast with structured errors when:

- PostgreSQL is unreachable
- required tables do not exist
- requested date coverage is unavailable

### Screening Layer

Skip individual symbols with recorded reasons when:

- required OHLCV fields are missing
- history length is insufficient for warmup
- derived indicators cannot be computed

### Review Layer

Allow partial completion:

- missing charts only fail that symbol
- subagent failure only fails that symbol
- final summary still emits completed results and an explicit failure list

## Validation Strategy

Before full usage, run a smoke test with a narrow date range and a small candidate set.

Required checks:

1. database connectivity and schema availability
2. `screen --method b1` emits a valid candidate file
3. `chart` produces daily images for emitted candidates
4. `review` successfully spawns subagents and writes per-stock JSON
5. `run` produces a final summary without requiring repository-local `data/` directories

## Design Decisions

- Use PostgreSQL tables directly as the source of truth
- Keep quantitative screening deterministic and local to Python
- Reserve multimodal reasoning for chart review only
- Make review backend model-agnostic
- Require subagent-based parallel review orchestration
- Limit v1 to `B1`

## Open Questions Resolved

- Skill name: `stock-select`
- Install location: `~/.agents/skills`
- Supported method in v1: `b1` only
- Runtime directory: skill-local runtime directory
- Review mechanism: multimodal subagents, prompt based on repository rubric, model chosen by agent framework
