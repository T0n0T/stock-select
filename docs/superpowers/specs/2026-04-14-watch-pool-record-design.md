# Watch Pool Record Design

## Goal

Add a CLI command that imports `PASS` and `WATCH` symbols from an existing review summary into a per-method CSV watch pool, records when the import command ran, sorts rows by trading-day distance from the command execution date, and trims rows outside a configurable recent trading-day window.

## Scope

This feature changes two things:

- add a new CLI command for recording reviewed symbols into a CSV watch pool
- change the default runtime root from `~/.agents/skills/stock-select/runtime` to `~/.agent/skills/stock-select/runtime`

This design does not add an intraday watch-pool import path. The first version only imports end-of-day review outputs addressed by `--pick-date`.

## Command Contract

Add a new CLI command named `record-watch` with these options:

- `--method`
- `--pick-date`
- `--dsn`
- `--runtime-root`
- `--window-trading-days`
- `--overwrite/--no-overwrite`
- `--progress/--no-progress`

Behavior:

1. Read `reviews/<pick_date>.<method>/summary.json` under the selected runtime root.
2. Collect rows from both `recommendations` and `excluded`.
3. Keep only rows whose `verdict` is `PASS` or `WATCH`.
4. Write the filtered rows into `runtime/watch_pool/<method>.csv`.
5. If a row with the same `method + pick_date + code` already exists:
   - `--overwrite` replaces the existing row with the current review row
   - `--no-overwrite` aborts with a CLI error
6. Stamp each imported row with the command execution time in a `recorded_at` column.
7. Resolve the command execution date to the latest trading day on or before that date.
8. Compute the trading-day distance between each row's `pick_date` and the resolved execution trade date.
9. Sort CSV rows by that trading-day distance ascending, then by `pick_date` descending, then by `code` ascending.
10. Delete rows whose `pick_date` falls outside the latest `N` trading days counted from the resolved execution trade date, where `N` comes from `--window-trading-days`.

The command prints the CSV path to `stdout` and progress details to `stderr`.

## CSV Schema

The watch-pool CSV should have stable columns in this order:

- `method`
- `pick_date`
- `code`
- `verdict`
- `total_score`
- `signal_type`
- `comment`
- `recorded_at`

The CSV does not persist the transient trading-day distance column. That value is recalculated on each command run for sorting and trimming.

## Source Data Contract

The command reads the existing review summary JSON produced by `review` or `review-merge`.

For each selected item, extract:

- `code`
- `verdict`
- `total_score`
- `signal_type`
- `comment`

The imported `pick_date` comes from the command option, not from individual row payloads.

If `summary.json` is missing, malformed, or lacks list-shaped `recommendations` / `excluded` sections, the command should fail with a clear CLI error.

## Trading-Day Window Rules

The retention window is based on trading days, not calendar days.

- Let `execution_date` be the local command date in `YYYY-MM-DD`.
- Let `execution_trade_date` be the latest trade date on or before `execution_date`.
- Let `cutoff_trade_date` be the `N`th latest trade date on or before `execution_trade_date`.
- Keep rows where `pick_date >= cutoff_trade_date`.
- Drop rows where `pick_date < cutoff_trade_date`.

Examples with `N = 10`:

- if the command runs on a trading day, the current trade date counts toward the ten-day window
- if the command runs on a non-trading day, the window anchors on the latest earlier trading day in the database

## Implementation Shape

Keep CLI parsing in `src/stock_select/cli.py`, but move CSV-specific logic into a focused helper module so the command implementation does not further bloat the CLI file.

Recommended responsibilities:

- `cli.py`
  - command parsing
  - locating review summary and CSV paths
  - resolving DSN and database connection
  - progress messages
- new helper module
  - read and normalize summary rows
  - load existing CSV if present
  - detect duplicate `method + pick_date + code`
  - merge or reject duplicates
  - trim by trading-day cutoff
  - write stable CSV output

## Error Handling

The command should fail fast when:

- `summary.json` does not exist
- the JSON is malformed
- a selected review item has no `code`
- `--no-overwrite` is used and a duplicate row already exists
- no DSN can be resolved
- the trade-date lookup fails because the database has no trade dates on or before the execution date

An empty import set is allowed. In that case the command still writes or refreshes the CSV after applying retention rules and prints the output path.

## Testing

Add tests for:

- default runtime root now points to `~/.agent/skills/stock-select/runtime`
- `record-watch` writes a new CSV from a summary containing `PASS`, `WATCH`, and `FAIL`
- `record-watch` overwrites an existing `method + pick_date + code` row when overwrite is enabled
- `record-watch` rejects duplicates when overwrite is disabled
- retention drops rows older than the configured trading-day window
- rows are sorted by trading-day distance ascending
- README command examples and output-path documentation use the new runtime root and mention `record-watch`
