# Clean Command Design

## Goal

Add a `clean` CLI subcommand that can:

- remove end-of-day screening artifacts for one selected `pick_date`
- remove intraday artifacts from dates other than the current Shanghai date

The command should only touch `candidates/`, `charts/`, `reviews/`, and `prepared/`.

## Scope

Included:

- `clean --pick-date YYYY-MM-DD`
- `clean --intraday`
- removal across all built-in methods: `b1`, `b2`, `dribull`, `hcr`
- concise CLI summary output describing what was deleted

Excluded:

- `watch_pool.csv`
- HTML render archives
- per-method filtering such as `clean --method b1`

## Artifact Rules

### End-of-day

`clean --pick-date YYYY-MM-DD` removes the selected day’s end-of-day artifacts:

- `candidates/<pick_date>.<method>.json`
- `charts/<pick_date>.<method>/`
- `reviews/<pick_date>.<method>/`
- `prepared/<pick_date>.pkl`
- `prepared/<pick_date>.hcr.pkl`

It does not remove intraday artifacts for the same date.

### Intraday

`clean --intraday` keeps artifacts whose trade date matches the current Shanghai date and removes older intraday artifacts:

- `candidates/<run_id>.<method>.json` when the run id or payload resolves to an older trade date
- `charts/<run_id>.<method>/`
- `reviews/<run_id>.<method>/`
- `prepared/<trade_date>.intraday.pkl`
- `prepared/<trade_date>.intraday.hcr.pkl`

End-of-day artifacts are never removed by `clean --intraday`.

## CLI Contract

- `--pick-date` and `--intraday` are mutually exclusive
- one of them is required
- `--pick-date` must use `YYYY-MM-DD`
- no-op cleanup is allowed and still exits successfully

## Test Coverage

Add CLI tests for:

- missing mode selection
- mutually exclusive arguments
- end-of-day cleanup removes only end-of-day artifacts
- intraday cleanup removes only non-current intraday artifacts
