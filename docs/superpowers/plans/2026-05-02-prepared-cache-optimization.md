# Prepared Cache Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace prepared cache with a single-table Feather format and remove both pickle compatibility and `dict[str, DataFrame]` runtime usage from the main screening pipeline.

**Architecture:** Prepared cache will have one disk format (`.feather + .meta.json`) and one runtime format (a long-form `pd.DataFrame`). The screen strategies will consume filtered/grouped views of that single table directly. Research scripts will either read the same single-table cache or query the DB for small-sample studies.

**Tech Stack:** Python 3.13, pandas, pyarrow Feather, pytest, Typer CLI, PostgreSQL-backed market data

---

### Task 1: Lock The Final Single-Table Schema

**Files:**
- Modify: `docs/superpowers/specs/2026-05-02-prepared-cache-optimization-design.md`
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing schema-focused tests**

Add tests to `tests/test_cli.py` asserting the prepared producers return a single `pd.DataFrame`, not a symbol map:

```python
def test_prepare_screen_data_returns_single_prepared_table() -> None:
    market = pd.DataFrame(
        {
            "ts_code": ["AAA.SZ", "AAA.SZ", "BBB.SZ", "BBB.SZ"],
            "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-01", "2026-04-02"]),
            "open": [10.0, 10.2, 20.0, 20.1],
            "high": [10.3, 10.4, 20.4, 20.5],
            "low": [9.9, 10.1, 19.8, 20.0],
            "close": [10.2, 10.3, 20.2, 20.4],
            "vol": [100.0, 120.0, 200.0, 210.0],
        }
    )

    prepared = cli._prepare_screen_data(market)

    assert isinstance(prepared, pd.DataFrame)
    assert {"ts_code", "trade_date", "close", "turnover_n", "J", "ma25", "ma60", "zxdq", "zxdkx"}.issubset(prepared.columns)
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k 'returns_single_prepared_table' -q`

Expected: FAIL because `_prepare_screen_data(...)` currently returns `dict[str, DataFrame]`

- [ ] **Step 3: Change prepare producers to return a single sorted table**

In `src/stock_select/cli.py`:

- change `_prepare_screen_data(...)` to build one output table instead of a symbol map
- change `_prepare_hcr_screen_data(...)` the same way
- ensure the final table is sorted by `ts_code, trade_date`
- keep the current column set intact

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k 'returns_single_prepared_table' -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-05-02-prepared-cache-optimization-design.md src/stock_select/cli.py tests/test_cli.py
git commit -m "refactor: make prepared producers return single tables"
```

### Task 2: Remove Pickle And Dict Adapters From Prepared IO

**Files:**
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests for Feather-only prepared IO**

Add tests asserting:

```python
def test_prepared_cache_v2_round_trip_returns_single_table(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    data_path = cli._prepared_cache_data_path(runtime_root, "2026-04-01", "b1")
    meta_path = cli._prepared_cache_meta_path(runtime_root, "2026-04-01", "b1")
    prepared = pd.DataFrame(
        {
            "ts_code": ["AAA.SZ", "AAA.SZ"],
            "trade_date": pd.to_datetime(["2026-03-31", "2026-04-01"]),
            "close": [10.0, 10.5],
        }
    )

    cli._write_prepared_cache_v2(
        data_path,
        meta_path,
        method="b1",
        pick_date="2026-04-01",
        start_date="2025-03-31",
        end_date="2026-04-01",
        prepared_table=prepared,
    )
    payload = cli._load_prepared_cache_v2(data_path, meta_path)

    pd.testing.assert_frame_equal(payload["prepared_table"], prepared)
```

Also add a failure-mode test confirming `_load_prepared_cache(...)` no longer accepts legacy pickle-only artifacts.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k 'prepared_cache_v2_round_trip_returns_single_table or no_longer_accepts_pickle' -q`

Expected: FAIL

- [ ] **Step 3: Remove pickle compatibility and symbol-map adapters**

In `src/stock_select/cli.py`:

- delete or stop using:
  - `_write_prepared_cache(...)`
  - `_prepared_symbol_map_to_table(...)`
  - `_prepared_table_to_symbol_map(...)`
- make `_write_prepared_cache_v2(...)` accept `prepared_table: pd.DataFrame`
- make `_load_prepared_cache_v2(...)` return:
  - `pick_date`
  - `start_date`
  - `end_date`
  - `prepared_table`
  - `metadata`
- make `_load_prepared_cache(...)` either become a v2-only alias or remove it from main call paths

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k 'prepared_cache_v2_round_trip_returns_single_table or no_longer_accepts_pickle' -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/cli.py tests/test_cli.py
git commit -m "refactor: make prepared cache feather-only and table-native"
```

### Task 3: Convert Strategy Layer To Single-Table Input

**Files:**
- Modify: `src/stock_select/strategies/b1.py`
- Modify: `src/stock_select/strategies/b2.py`
- Modify: `src/stock_select/strategies/dribull.py`
- Modify: `src/stock_select/strategies/hcr.py`
- Modify: `tests/test_cli.py`
- Modify: strategy-specific test files as needed

- [ ] **Step 1: Write one failing test per strategy input shape**

For each method, add or update tests asserting the strategy runner accepts a single table and internally filters/groups by `ts_code`, not a prebuilt symbol map.

- [ ] **Step 2: Run the targeted strategy tests to verify they fail**

Run:

```bash
uv run pytest tests/test_b1_logic.py tests/test_b2_logic.py tests/test_dribull_logic.py tests/test_hcr_logic.py -q
```

Expected: FAIL at call sites or assumptions that `prepared_by_symbol` is a dict

- [ ] **Step 3: Update strategy signatures and internals**

Change:

- `run_b1_screen_with_stats(prepared, pick_date, config)`
- `run_b2_screen_with_stats(prepared, pick_date)`
- `run_dribull_screen_with_stats(prepared, pick_date, config)`
- `run_hcr_screen_with_stats(prepared, pick_date)`

Implementation rule:

1. receive a single table
2. optionally pre-filter by `ts_code`
3. `groupby("ts_code")`
4. run existing per-symbol logic over each group

- [ ] **Step 4: Run the targeted strategy tests to verify they pass**

Run:

```bash
uv run pytest tests/test_b1_logic.py tests/test_b2_logic.py tests/test_dribull_logic.py tests/test_hcr_logic.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/strategies/b1.py src/stock_select/strategies/b2.py src/stock_select/strategies/dribull.py src/stock_select/strategies/hcr.py tests/
git commit -m "refactor: make screen strategies consume prepared tables"
```

### Task 4: Convert Screen, Chart, Review, And Intraday Main Paths

**Files:**
- Modify: `src/stock_select/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing integration-shape tests**

Add or update tests to prove:

- `screen` writes Feather-only prepared artifacts
- `screen` reuses Feather-only prepared artifacts
- `chart --intraday` works by filtering a single prepared table
- `review --intraday` works by filtering a single prepared table

- [ ] **Step 2: Run the targeted integration tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli.py -k 'prepared_cache or chart_intraday or review_intraday' -q
```

Expected: FAIL where the CLI still expects dict-shaped prepared data

- [ ] **Step 3: Remove dict-based prepared consumption from main CLI paths**

In `src/stock_select/cli.py`:

- `screen` should pass filtered prepared tables into strategies
- `chart` should select `prepared[prepared["ts_code"] == code]`
- `review` should do the same
- intraday paths should do the same
- any old helper that rebuilds symbol maps should be removed

- [ ] **Step 4: Run the targeted integration tests to verify they pass**

Run:

```bash
uv run pytest tests/test_cli.py -k 'prepared_cache or chart_intraday or review_intraday' -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/cli.py tests/test_cli.py
git commit -m "refactor: make main cli paths consume prepared tables directly"
```

### Task 5: Convert Research Scripts And Benchmark Real Data

**Files:**
- Modify: `scripts/review_top3_stats.py`
- Modify: `scripts/score_tuning_diagnostics.py`
- Modify: `scripts/prepared_cache_benchmark.py`
- Modify: `tests/test_review_top3_stats.py`
- Modify: `tests/test_score_tuning_diagnostics.py`

- [ ] **Step 1: Write failing script tests for single-table prepared loading**

Update both script test files so they assert the scripts load Feather-only prepared cache and work with table-native access.

- [ ] **Step 2: Run script tests to verify they fail**

Run:

```bash
uv run pytest tests/test_review_top3_stats.py tests/test_score_tuning_diagnostics.py -q
```

Expected: FAIL until the scripts stop expecting dict-shaped prepared data

- [ ] **Step 3: Convert scripts to table-native access**

Rules:

- `review_top3_stats.py`
  - load prepared as a single table
  - for one code, filter by `ts_code`
- `score_tuning_diagnostics.py`
  - do the same
- `prepared_cache_benchmark.py`
  - compare Feather size/read time only against legacy pickle if still present on disk
  - do not reintroduce pickle into product logic

- [ ] **Step 4: Run script tests to verify they pass**

Run:

```bash
uv run pytest tests/test_review_top3_stats.py tests/test_score_tuning_diagnostics.py -q
```

Expected: PASS

- [ ] **Step 5: Run the real benchmark on 2026-04-30**

Run:

```bash
uv run stock-select screen --method b2 --pick-date 2026-04-30 --recompute
uv run python scripts/prepared_cache_benchmark.py --base-key 2026-04-30 --method b2
```

Expected:

- Feather cache artifacts written
- benchmark prints Feather file size and read time
- end-to-end result is usable for final judgment

- [ ] **Step 6: Commit**

```bash
git add scripts/review_top3_stats.py scripts/score_tuning_diagnostics.py scripts/prepared_cache_benchmark.py tests/test_review_top3_stats.py tests/test_score_tuning_diagnostics.py
git commit -m "refactor: make research scripts consume prepared tables"
```

## Spec Coverage Check

- Feather-only disk format: covered by Task 2.
- Single-table runtime model: covered by Task 1 through Task 4.
- No `dict[str, DataFrame]` main-path usage: covered by Task 3 and Task 4.
- Research script adaptation: covered by Task 5.
- Real benchmark validation: covered by Task 5.

## Placeholder Scan

- No `TODO` / `TBD` placeholders remain.
- All tasks point to exact files.
- All verification steps use explicit commands.

## Type Consistency Check

- Prepared runtime object is consistently described as `prepared_table: pd.DataFrame`.
- Strategy functions are consistently described as single-table consumers.
- Feather + meta is consistently the only target cache format.

Plan complete and saved to `docs/superpowers/plans/2026-05-02-prepared-cache-optimization.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
