# Turnover-Top MA25 Above MA60 Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the default `turnover-top` pool so only symbols with `ma25 > ma60` can enter the shared top-turnover candidate pool.

**Architecture:** Keep the change narrow by enforcing the new gate inside `build_top_turnover_pool(...)`, the existing shared default-pool helper. This preserves the current CLI contract and automatically applies the tighter default pool to every method that uses `pool_source=turnover-top`, while leaving `record-watch` and `custom` unchanged.

**Tech Stack:** Python, pandas, Typer CLI, pytest

---

## File Structure

- Modify: `src/stock_select/strategies/b1.py`
  - tighten `build_top_turnover_pool(...)` so it skips rows where `ma25` or `ma60` are missing or where `ma25 <= ma60`
- Modify: `tests/test_b1_logic.py`
  - add focused helper-level tests for the new default-pool gate
- Modify: `tests/test_cli.py`
  - add one CLI-level regression test proving the shared `turnover-top` pool excludes symbols that fail the MA gate before method screening
- Modify: `README.md`
  - document the new default-pool rule in the runtime/screening behavior section

No new module is required. The rule belongs to the existing shared pool helper, not to a new abstraction.

### Task 1: Add helper-level failing tests for the MA gate

**Files:**
- Modify: `tests/test_b1_logic.py`
- Modify: `src/stock_select/strategies/b1.py`

- [ ] **Step 1: Write the failing test for excluding symbols where `ma25 <= ma60`**

Add this test near the existing `build_top_turnover_pool(...)` tests in `tests/test_b1_logic.py`:

```python
def test_build_top_turnover_pool_requires_ma25_above_ma60() -> None:
    pool = build_top_turnover_pool(
        {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": ["2026-04-24"],
                    "turnover_n": [200.0],
                    "ma25": [10.5],
                    "ma60": [10.0],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": ["2026-04-24"],
                    "turnover_n": [300.0],
                    "ma25": [9.8],
                    "ma60": [10.0],
                }
            ),
        },
        top_m=5,
    )

    assert pool == {pd.Timestamp("2026-04-24"): ["AAA.SZ"]}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_b1_logic.py::test_build_top_turnover_pool_requires_ma25_above_ma60 -v
```

Expected: FAIL because the current helper still includes `BBB.SZ` based only on `turnover_n`.

- [ ] **Step 3: Write the failing test for skipping rows with missing `ma25` or `ma60`**

Add this test:

```python
def test_build_top_turnover_pool_skips_rows_missing_ma25_or_ma60() -> None:
    pool = build_top_turnover_pool(
        {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": ["2026-04-24"],
                    "turnover_n": [200.0],
                    "ma25": [None],
                    "ma60": [10.0],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": ["2026-04-24"],
                    "turnover_n": [180.0],
                    "ma25": [10.2],
                    "ma60": [None],
                }
            ),
            "CCC.SZ": pd.DataFrame(
                {
                    "trade_date": ["2026-04-24"],
                    "turnover_n": [160.0],
                    "ma25": [10.3],
                    "ma60": [10.0],
                }
            ),
        },
        top_m=5,
    )

    assert pool == {pd.Timestamp("2026-04-24"): ["CCC.SZ"]}
```

- [ ] **Step 4: Run the second test to verify it fails**

Run:

```bash
uv run pytest tests/test_b1_logic.py::test_build_top_turnover_pool_skips_rows_missing_ma25_or_ma60 -v
```

Expected: FAIL because the current helper does not gate on `ma25` or `ma60`.

- [ ] **Step 5: Implement the minimal helper change**

Update `build_top_turnover_pool(...)` in `src/stock_select/strategies/b1.py` like this:

```python
def build_top_turnover_pool(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    *,
    top_m: int,
) -> dict[pd.Timestamp, list[str]]:
    if top_m <= 0:
        return {}

    pool: dict[pd.Timestamp, list[tuple[float, str]]] = {}
    for symbol, frame in prepared_by_symbol.items():
        if frame.empty:
            continue
        working = frame.copy()
        if "trade_date" in working.columns:
            date_col = "trade_date"
        elif "date" in working.columns:
            date_col = "date"
        else:
            continue
        if "turnover_n" not in working.columns or "ma25" not in working.columns or "ma60" not in working.columns:
            continue
        working[date_col] = pd.to_datetime(working[date_col], errors="coerce", format="mixed")
        working["turnover_n"] = pd.to_numeric(working["turnover_n"], errors="coerce")
        working["ma25"] = pd.to_numeric(working["ma25"], errors="coerce")
        working["ma60"] = pd.to_numeric(working["ma60"], errors="coerce")
        for _, row in working.iterrows():
            if pd.isna(row[date_col]) or pd.isna(row["turnover_n"]) or pd.isna(row["ma25"]) or pd.isna(row["ma60"]):
                continue
            if not float(row["ma25"]) > float(row["ma60"]):
                continue
            trade_date = pd.Timestamp(row[date_col])
            pool.setdefault(trade_date, []).append((float(row["turnover_n"]), symbol))

    result: dict[pd.Timestamp, list[str]] = {}
    for trade_date, items in pool.items():
        ranked = sorted(items, key=lambda item: item[0], reverse=True)[:top_m]
        result[trade_date] = [symbol for _, symbol in ranked]
    return result
```

- [ ] **Step 6: Run the focused helper tests to verify they pass**

Run:

```bash
uv run pytest tests/test_b1_logic.py::test_build_top_turnover_pool_requires_ma25_above_ma60 tests/test_b1_logic.py::test_build_top_turnover_pool_skips_rows_missing_ma25_or_ma60 -q
```

Expected: PASS

- [ ] **Step 7: Commit the helper gate change**

Run:

```bash
git add src/stock_select/strategies/b1.py tests/test_b1_logic.py
git commit -m "feat: gate turnover-top pool on ma25 above ma60"
```

### Task 2: Add CLI-level regression coverage for the shared default pool

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing CLI regression test for `turnover-top`**

Add this test near the other pool-source tests in `tests/test_cli.py`:

```python
def test_screen_turnover_top_uses_ma25_above_ma60_pool_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    captured: dict[str, object] = {}

    prepared = {
        "AAA.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-24"]),
                "turnover_n": [200.0],
                "ma25": [10.5],
                "ma60": [10.0],
                "J": [10.0],
                "zxdq": [10.6],
                "zxdkx": [10.1],
                "close": [10.7],
                "weekly_ma_bull": [True],
                "max_vol_not_bearish": [True],
                "chg_d": [1.0],
                "v_shrink": [True],
                "safe_mode": [True],
                "lt_filter": [True],
            }
        ),
        "BBB.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-24"]),
                "turnover_n": [300.0],
                "ma25": [9.8],
                "ma60": [10.0],
                "J": [10.0],
                "zxdq": [10.6],
                "zxdkx": [10.1],
                "close": [10.7],
                "weekly_ma_bull": [True],
                "max_vol_not_bearish": [True],
                "chg_d": [1.0],
                "v_shrink": [True],
                "safe_mode": [True],
                "lt_filter": [True],
            }
        ),
    }

    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda connection, start_date, end_date, symbols=None: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ", "BBB.SZ"],
                "trade_date": ["2026-04-24", "2026-04-24"],
                "open": [10.0, 10.0],
                "high": [10.8, 10.8],
                "low": [9.9, 9.9],
                "close": [10.7, 10.7],
                "vol": [100.0, 120.0],
            }
        ),
    )
    monkeypatch.setattr(cli, "_validate_eod_pick_date_has_market_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_call_prepare_screen_data", lambda market, reporter=None: prepared)

    def fake_run_b1(prepared_by_symbol, pick_date, config):
        captured["codes"] = sorted(prepared_by_symbol)
        return ([], _b1_screen_stats(total_symbols=len(prepared_by_symbol), eligible=len(prepared_by_symbol), selected=0))

    monkeypatch.setattr(cli, "run_b1_screen_with_stats", fake_run_b1)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-24",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert captured["codes"] == ["AAA.SZ"]
```

- [ ] **Step 2: Run the regression test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_screen_turnover_top_uses_ma25_above_ma60_pool_gate -v
```

Expected: FAIL because the current default pool still allows `BBB.SZ`.

- [ ] **Step 3: Update README to document the default-pool gate**

Add this bullet in the runtime-behavior section under the `turnover-top` / screening explanation in `README.md`:

```markdown
- 默认 `turnover-top` 票池除成交额排序外，还要求目标日 `ma25 > ma60`
```

Place it near the existing description of the default top-turnover pool so the rule is visible to users of `screen` and `run`.

- [ ] **Step 4: Run the focused CLI regression test after the helper fix**

Run:

```bash
uv run pytest tests/test_cli.py::test_screen_turnover_top_uses_ma25_above_ma60_pool_gate -q
```

Expected: PASS

- [ ] **Step 5: Commit the CLI regression test and README update**

Run:

```bash
git add tests/test_cli.py README.md
git commit -m "test: cover turnover-top ma25 ma60 pool gate"
```

### Task 3: Run final verification and review the diff

**Files:**
- Modify: `src/stock_select/strategies/b1.py`
- Modify: `tests/test_b1_logic.py`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Run the full focused verification set**

Run:

```bash
uv run pytest tests/test_b1_logic.py tests/test_cli.py -k "build_top_turnover_pool or turnover_top_uses_ma25_above_ma60_pool_gate" -v
```

Expected:

- all new helper tests PASS
- the CLI regression test PASS
- no unrelated pool-source regressions appear in the selected subset

- [ ] **Step 2: Inspect the final diff**

Run:

```bash
git diff --stat HEAD~2..HEAD
git diff HEAD~2..HEAD -- src/stock_select/strategies/b1.py tests/test_b1_logic.py tests/test_cli.py README.md
```

Expected:

- only the shared `turnover-top` helper, targeted tests, and README docs changed
- no method-specific screening formulas changed
- no `record-watch` or `custom` logic changed

- [ ] **Step 3: Create the completion commit if additional fixups were needed after Task 2**

If verification required extra edits, run:

```bash
git add src/stock_select/strategies/b1.py tests/test_b1_logic.py tests/test_cli.py README.md
git commit -m "fix: finalize turnover-top ma25 ma60 gate"
```

If no additional edits were needed, skip this step.
