# Stock Select Progress Output Design

## Goal

Add human-readable progress output to the `stock-select` CLI so long-running commands clearly show that work is still advancing.

## Scope

Included:

- text progress lines on `stderr`
- progress support for `screen`, `chart`, `review`, and `run`
- a CLI switch to disable progress output
- regression tests ensuring `stdout` still only carries final result paths

Excluded:

- rich TUI progress bars
- persistent log files
- changes to screening or review semantics

## Design

Add a lightweight reporter helper inside the CLI module. It will emit fixed-format lines such as:

- `[screen] connect db`
- `[screen] fetched rows=508691 symbols=5497`
- `[screen] prepare 500/5497 symbol=000001.SZ elapsed=12.4s`
- `[chart] candidate 3/12 code=600519.SH`
- `[review] candidate 2/12 code=688111.SH`
- `[run] step=screen done path=/.../candidates/2026-04-03.json`

The reporter writes to `stderr` via `typer.echo(..., err=True)` so machine-readable `stdout` remains unchanged.

## Behavior

- Progress is enabled by default.
- `--no-progress` suppresses all progress lines.
- `screen` emits stage messages and periodic heartbeats while preprocessing grouped symbols.
- `chart` and `review` emit one line per candidate.
- `run` emits stage start/done lines around each subcommand implementation.

## Verification

- CLI tests assert progress text appears on `stderr` by default.
- CLI tests assert `--no-progress` suppresses those lines.
- Full test suite must pass after the change.
