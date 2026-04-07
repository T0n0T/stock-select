# Stock Select Insufficient History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distinguish missing `zxdkx` history from real `close <= zxdkx` failures in B1 screening stats and document the behavior in a Chinese README.

**Architecture:** Keep the existing B1 filter order, but insert an explicit insufficient-history check before the `close > zxdkx` condition. Update CLI breakdown formatting and align tests and documentation with the new stat.

**Tech Stack:** Python 3.13, pandas, Typer, pytest, Markdown

---

### Task 1: Add regression tests for insufficient-history classification

**Files:**
- Modify: `tests/test_b1_logic.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing unit test in `tests/test_b1_logic.py`**

```python
def test_run_b1_screen_with_stats_counts_missing_zxdkx_as_insufficient_history() -> None:
    pick_date = pd.Timestamp("2026-04-03")
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03"]),
            "open": [10.0, 10.2, 10.5],
            "close": [10.4, 10.8, 11.0],
            "high": [10.5, 10.9, 11.1],
            "low": [9.9, 10.1, 10.4],
            "volume": [100.0, 120.0, 150.0],
            "J": [12.0, 11.0, 10.0],
            "zxdq": [10.2, 10.5, 10.8],
            "zxdkx": [10.0, 10.2, float("nan")],
            "weekly_ma_bull": [True, True, True],
            "max_vol_not_bearish": [True, True, True],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )

    candidates, stats = run_b1_screen_with_stats(
        {"MISSINGZXDKX.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert candidates == []
    assert stats["fail_insufficient_history"] == 1
    assert stats["fail_close_zxdkx"] == 0
```

- [ ] **Step 2: Run the targeted unit test to verify it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_b1_logic.py::test_run_b1_screen_with_stats_counts_missing_zxdkx_as_insufficient_history -v`
Expected: FAIL because `fail_insufficient_history` is missing or remains zero.

- [ ] **Step 3: Write the failing CLI test in `tests/test_cli.py`**

```python
assert (
    "[screen] breakdown total_symbols=10 eligible=8 fail_j=2 fail_insufficient_history=3 "
    "fail_close_zxdkx=1 fail_zxdq_zxdkx=2 fail_weekly_ma=1 fail_max_vol=1 selected=1"
) in result.stderr
```

- [ ] **Step 4: Run the targeted CLI test to verify it fails**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_cli.py::test_screen_emits_filter_breakdown_stats -v`
Expected: FAIL because the emitted breakdown does not include `fail_insufficient_history`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_b1_logic.py tests/test_cli.py
git commit -m "test: cover insufficient history breakdown"
```

### Task 2: Implement insufficient-history stats and CLI output

**Files:**
- Modify: `src/stock_select/b1_logic.py`
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_b1_logic.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add the new stat field in `src/stock_select/b1_logic.py`**

```python
    stats = {
        "total_symbols": len(prepared_by_symbol),
        "eligible": 0,
        "fail_j": 0,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_weekly_ma": 0,
        "fail_max_vol": 0,
        "selected": 0,
    }
```

- [ ] **Step 2: Classify missing `zxdkx` before the close-vs-zxdkx check**

```python
        if pd.isna(row["zxdkx"]):
            stats["fail_insufficient_history"] += 1
            continue
        if not (float(row["close"]) > float(row["zxdkx"])):
            stats["fail_close_zxdkx"] += 1
            continue
```

- [ ] **Step 3: Update CLI breakdown formatting in `src/stock_select/cli.py`**

```python
            f"fail_j={stats['fail_j']} "
            f"fail_insufficient_history={stats['fail_insufficient_history']} "
            f"fail_close_zxdkx={stats['fail_close_zxdkx']} "
```

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_b1_logic.py tests/test_cli.py -v`
Expected: PASS for the updated insufficient-history and breakdown coverage.

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/b1_logic.py src/stock_select/cli.py tests/test_b1_logic.py tests/test_cli.py
git commit -m "feat: report insufficient history in b1 stats"
```

### Task 3: Rewrite README in Chinese and document runtime behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README headings and sections in Chinese**

```md
# stock-select

独立仓库，用于承载 `stock-select` 技能和 CLI。
```

- [ ] **Step 2: Add a dedicated explanation for screening prerequisites and insufficient history**

```md
## 筛选说明

- `screen` 会读取目标日前约 366 天的 `daily_market` 窗口。
- B1 的 `zxdkx` 由 14、28、57、114 日均线平均得到，因此目标日通常需要至少 114 个有效交易日历史。
- 如果缓存中该股票在目标日前的实际连续交易历史不足，目标日 `zxdkx` 会为空。
- 这类股票会计入 `fail_insufficient_history`，不会再被误记为 `fail_close_zxdkx`。
```

- [ ] **Step 3: Run a quick README review pass**

Run: `sed -n '1,240p' README.md`
Expected: Chinese wording throughout, command examples preserved, insufficient-history behavior clearly documented.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: rewrite readme in chinese"
```

### Task 4: Final verification

**Files:**
- Modify: `README.md`
- Modify: `src/stock_select/b1_logic.py`
- Modify: `src/stock_select/cli.py`
- Modify: `tests/test_b1_logic.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Run the focused verification suite**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_b1_logic.py tests/test_cli.py -q`
Expected: all targeted tests pass.

- [ ] **Step 2: Inspect the diff for scope control**

Run: `git diff -- README.md src/stock_select/b1_logic.py src/stock_select/cli.py tests/test_b1_logic.py tests/test_cli.py`
Expected: only insufficient-history reporting and README localization changes appear.

- [ ] **Step 3: Commit final polish if needed**

```bash
git add README.md src/stock_select/b1_logic.py src/stock_select/cli.py tests/test_b1_logic.py tests/test_cli.py
git commit -m "chore: finalize insufficient history reporting"
```
