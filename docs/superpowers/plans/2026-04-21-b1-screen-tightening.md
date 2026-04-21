# B1 Screen Tightening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten deterministic `b1` screening by adding four new hard filters: `CHG_D <= 4.0`, `V_SHRINK`, `SAFE_MODE`, and `LT_FILTER`.

**Architecture:** Keep `b1`’s existing first-stage identity unchanged, add a shared helper that computes the new tightening columns from daily OHLCV, persist those columns during `_prepare_screen_data()`, and then consume the prepared booleans in `run_b1_screen_with_stats()` after the existing legacy gates. Update CLI breakdown reporting and repository docs to match the new rule order.

**Tech Stack:** Python, pandas, pytest, Typer CLI, existing `stock_select` strategy pipeline.

---

## File Map

- `src/stock_select/strategies/b1.py`
  Responsibility: owns `b1` indicator helpers, default config/constants, and deterministic screening order.
- `src/stock_select/strategies/__init__.py`
  Responsibility: re-export strategy helpers used by `cli.py`.
- `src/stock_select/cli.py`
  Responsibility: computes per-symbol prepared frames and emits the user-facing filter breakdown.
- `tests/test_b1_logic.py`
  Responsibility: verifies `b1` strategy exports, screen ordering, and per-condition failure counters.
- `tests/test_cli.py`
  Responsibility: verifies prepared-frame shape, CLI breakdown output, and fake `b1` stats payloads used across screen tests.
- `README.md`
  Responsibility: user-facing `b1` rule order and counter semantics.
- `.agents/skills/stock-select/references/b1-selector.md`
  Responsibility: bundled deterministic `b1` selector reference.

### Task 1: Add Prepared Tightening Columns For B1

**Files:**
- Modify: `src/stock_select/strategies/b1.py`
- Modify: `src/stock_select/strategies/__init__.py`
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_b1_logic.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests for the new prepared columns**

Add one export test in `tests/test_b1_logic.py` and one prepared-frame test in `tests/test_cli.py`.

```python
# tests/test_b1_logic.py
from stock_select.strategies.b1 import compute_b1_tightening_columns
from stock_select.strategies import compute_b1_tightening_columns as exported_compute_b1_tightening_columns


def test_b1_strategy_module_exports_current_defaults_and_functions() -> None:
    assert set(strategy_b1.__all__) == {
        "DEFAULT_B1_CONFIG",
        "DEFAULT_MAX_VOL_LOOKBACK",
        "DEFAULT_TOP_M",
        "DEFAULT_TURNOVER_WINDOW",
        "DEFAULT_WEEKLY_MA_PERIODS",
        "build_top_turnover_pool",
        "compute_b1_tightening_columns",
        "compute_expanding_j_quantile",
        "compute_kdj",
        "compute_macd",
        "compute_turnover_n",
        "compute_weekly_close",
        "compute_weekly_ma_bull",
        "compute_zx_lines",
        "max_vol_not_bearish",
        "run_b1_screen",
        "run_b1_screen_with_stats",
    }
    assert exported_compute_b1_tightening_columns is compute_b1_tightening_columns
```

```python
# tests/test_cli.py
def test_prepare_screen_data_adds_b1_tightening_columns() -> None:
    importlib.reload(cli)

    trade_dates = pd.date_range("2025-10-01", periods=130, freq="B")
    close = [10.0 + idx * 0.05 for idx in range(len(trade_dates))]
    market = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * len(trade_dates),
            "trade_date": trade_dates,
            "open": [value - 0.08 for value in close],
            "high": [value + 0.15 for value in close],
            "low": [value - 0.20 for value in close],
            "close": close,
            "vol": [1000.0] * 127 + [900.0, 850.0, 800.0],
        }
    )

    prepared = cli._prepare_screen_data(market)

    frame = prepared["000001.SZ"]
    row = frame.iloc[-1]
    assert {
        "chg_d",
        "amp_d",
        "body_d",
        "vm3",
        "vm5",
        "vm10",
        "m5",
        "v_shrink",
        "safe_mode",
        "lt_filter",
    }.issubset(frame.columns)
    assert round(float(row["chg_d"]), 4) == round((close[-1] - close[-2]) / close[-2] * 100.0, 4)
    assert bool(row["v_shrink"]) is True
    assert bool(row["safe_mode"]) is True
    assert bool(row["lt_filter"]) is True
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `PYTHONPATH=src pytest -q tests/test_b1_logic.py tests/test_cli.py -k "exports_current_defaults_and_functions or prepare_screen_data_adds_b1_tightening_columns"`

Expected:

- `ImportError` or `AttributeError` for missing `compute_b1_tightening_columns`
- the new prepared-column assertion fails because `_prepare_screen_data()` does not yet emit those columns

- [ ] **Step 3: Implement `compute_b1_tightening_columns()` and wire it into `_prepare_screen_data()`**

Add a shared helper to `src/stock_select/strategies/b1.py` and export it through `src/stock_select/strategies/__init__.py`.

```python
# src/stock_select/strategies/b1.py
import numpy as np
import pandas as pd


def _barslast(flags: pd.Series) -> pd.Series:
    values = flags.fillna(False).astype(bool).to_numpy()
    out = np.empty(len(values), dtype=int)
    last_true = -1
    for idx, flag in enumerate(values):
        if flag:
            last_true = idx
        out[idx] = idx - last_true if last_true >= 0 else len(values)
    return pd.Series(out, index=flags.index)


def compute_b1_tightening_columns(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = _resolve_volume_series(df)

    ref_close = close.shift(1)
    chg_d = close.sub(ref_close).div(ref_close).mul(100.0)
    amp_d = high.sub(low).div(ref_close).mul(100.0)
    body_d = open_.sub(close).div(ref_close).mul(100.0)

    vm3 = volume.rolling(window=3, min_periods=1).mean()
    vm5 = volume.rolling(window=5, min_periods=1).mean()
    vm10 = volume.rolling(window=10, min_periods=1).mean()
    m5 = close.rolling(window=5, min_periods=1).mean()
    v_shrink = vm3 < vm10

    high_pos = (
        high.rolling(window=20, min_periods=1).max().sub(low.rolling(window=20, min_periods=1).min())
        .div(low.rolling(window=20, min_periods=1).min())
        .mul(100.0)
        > 15.0
    )
    vol_big = (volume > vm5 * 1.3) | (volume > vm10 * 1.5)
    bad_dump = ((body_d > 6.0) | (chg_d < -5.5)) & vol_big & high_pos
    dump_day = _barslast(bad_dump)
    cool_off = pd.Series(
        np.where(bad_dump.astype(int).rolling(window=10, min_periods=1).sum() >= 2, 10, 5),
        index=df.index,
    )
    in_recovery = (dump_day >= cool_off) & (dump_day <= 15)
    shape_ok = (amp_d <= 10.0) & (chg_d >= -4.0) & (chg_d <= 4.0)
    cg_ok = (close > m5) | (m5 >= m5.shift(1)) | (close.sub(m5).abs().div(m5).mul(100.0) < 1.5)
    safe_mode = (dump_day >= cool_off) & pd.Series(np.where(in_recovery, shape_ok & cg_ok, True), index=df.index)

    st_t1 = close.ewm(span=10, adjust=False).mean().ewm(span=10, adjust=False).mean()
    lt_t1 = (
        close.rolling(14, min_periods=1).mean()
        + close.rolling(28, min_periods=1).mean()
        + close.rolling(57, min_periods=1).mean()
        + close.rolling(114, min_periods=1).mean()
    ) / 4.0
    cross_up = (st_t1 > lt_t1) & (st_t1.shift(1) <= lt_t1.shift(1))
    c_days = _barslast(cross_up)
    waiver = ((c_days >= 0) & (c_days <= 30) & (st_t1 > lt_t1)) | (st_t1 > lt_t1 * 1.03)
    barscount = pd.Series(np.arange(1, len(df) + 1), index=df.index)
    lt_dir = pd.Series(
        np.where(barscount > 114, np.where(lt_t1 > lt_t1.shift(1), 1, -1), 1),
        index=df.index,
    )
    lt_filter = ((lt_dir != lt_dir.shift(1)).astype(int).rolling(window=30, min_periods=1).sum() <= 2) | waiver

    return pd.DataFrame(
        {
            "chg_d": chg_d,
            "amp_d": amp_d,
            "body_d": body_d,
            "vm3": vm3,
            "vm5": vm5,
            "vm10": vm10,
            "m5": m5,
            "v_shrink": v_shrink.fillna(False),
            "safe_mode": safe_mode.fillna(False),
            "lt_filter": lt_filter.fillna(False),
        },
        index=df.index,
    )
```

```python
# src/stock_select/strategies/__init__.py
from stock_select.strategies.b1 import (
    ...
    compute_b1_tightening_columns,
    ...
)

__all__ = [
    ...
    "compute_b1_tightening_columns",
    ...
]
```

```python
# src/stock_select/cli.py
from stock_select.strategies import (
    ...
    compute_b1_tightening_columns,
    ...
)


def _prepare_screen_data(...):
    ...
    tightening = compute_b1_tightening_columns(group)
    for column in ("chg_d", "amp_d", "body_d", "vm3", "vm5", "vm10", "m5", "v_shrink", "safe_mode", "lt_filter"):
        group[column] = tightening[column]
    ...
```

- [ ] **Step 4: Re-run the focused tests and verify they pass**

Run: `PYTHONPATH=src pytest -q tests/test_b1_logic.py tests/test_cli.py -k "exports_current_defaults_and_functions or prepare_screen_data_adds_b1_tightening_columns"`

Expected: `2 passed`

- [ ] **Step 5: Commit the preparation helper**

```bash
git add src/stock_select/strategies/b1.py src/stock_select/strategies/__init__.py src/stock_select/cli.py tests/test_b1_logic.py tests/test_cli.py
git commit -m "feat: prepare b1 tightening columns"
```

### Task 2: Apply The New B1 Screening Gates And Stats

**Files:**
- Modify: `src/stock_select/strategies/b1.py`
- Test: `tests/test_b1_logic.py`

- [ ] **Step 1: Write failing strategy tests for the new first-failure counters and order**

Extend `tests/test_b1_logic.py` so the existing stats test covers the new fields and add a sequencing test proving the new gates run after the legacy ones.

```python
# tests/test_b1_logic.py
def test_run_b1_screen_with_stats_reports_first_failed_condition_counts() -> None:
    pick_date = pd.Timestamp("2026-04-03")

    def make_frame(
        *,
        j: float = 10.0,
        close: float = 11.0,
        zxdq: float = 10.8,
        zxdkx: float = 10.4,
        weekly_ma_bull: bool = True,
        max_vol_not_bearish_value: bool = True,
        chg_d: float = 1.0,
        v_shrink: bool = True,
        safe_mode: bool = True,
        lt_filter: bool = True,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03"]),
                "open": [10.0, 10.2, 10.5],
                "close": [10.4, 10.8, close],
                "high": [10.5, 10.9, 11.1],
                "low": [9.9, 10.1, 10.4],
                "volume": [100.0, 120.0, 150.0],
                "J": [12.0, 11.0, j],
                "zxdq": [10.2, 10.5, zxdq],
                "zxdkx": [10.0, 10.2, zxdkx],
                "weekly_ma_bull": [True, True, weekly_ma_bull],
                "max_vol_not_bearish": [True, True, max_vol_not_bearish_value],
                "chg_d": [0.5, 0.6, chg_d],
                "amp_d": [2.0, 2.1, 2.2],
                "body_d": [-1.0, -1.0, -1.0],
                "vm3": [100.0, 110.0, 90.0],
                "vm5": [100.0, 110.0, 105.0],
                "vm10": [100.0, 110.0, 120.0],
                "m5": [10.2, 10.4, 10.6],
                "v_shrink": [True, True, v_shrink],
                "safe_mode": [True, True, safe_mode],
                "lt_filter": [True, True, lt_filter],
                "turnover_n": [1020.0, 2280.0, 3892.5],
            }
        )

    candidates, stats = run_b1_screen_with_stats(
        {
            "PASS.SZ": make_frame(),
            "FAILJ.SZ": make_frame(j=85.0),
            "FAILCLOSE.SZ": make_frame(close=10.2),
            "FAILZXDQ.SZ": make_frame(zxdq=10.1),
            "FAILWEEKLY.SZ": make_frame(weekly_ma_bull=False),
            "FAILMAXVOL.SZ": make_frame(max_vol_not_bearish_value=False),
            "FAILCHG.SZ": make_frame(chg_d=5.2),
            "FAILSHRINK.SZ": make_frame(v_shrink=False),
            "FAILSAFE.SZ": make_frame(safe_mode=False),
            "FAILLT.SZ": make_frame(lt_filter=False),
            "MISSING.SZ": make_frame().iloc[[0, 1]].copy(),
        },
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert [candidate["code"] for candidate in candidates] == ["PASS.SZ"]
    assert stats == {
        "total_symbols": 11,
        "eligible": 10,
        "fail_j": 1,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 1,
        "fail_zxdq_zxdkx": 1,
        "fail_weekly_ma": 1,
        "fail_max_vol": 1,
        "fail_chg_cap": 1,
        "fail_v_shrink": 1,
        "fail_safe_mode": 1,
        "fail_lt_filter": 1,
        "selected": 1,
    }
```

```python
def test_run_b1_screen_with_stats_keeps_legacy_order_before_new_filters() -> None:
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
            "zxdkx": [10.0, 10.2, 10.4],
            "weekly_ma_bull": [True, True, False],
            "max_vol_not_bearish": [True, True, True],
            "chg_d": [0.5, 0.6, 5.5],
            "amp_d": [2.0, 2.0, 2.0],
            "body_d": [-1.0, -1.0, -1.0],
            "vm3": [90.0, 90.0, 150.0],
            "vm5": [95.0, 95.0, 120.0],
            "vm10": [100.0, 100.0, 110.0],
            "m5": [10.2, 10.4, 10.6],
            "v_shrink": [True, True, False],
            "safe_mode": [True, True, False],
            "lt_filter": [True, True, False],
            "turnover_n": [1020.0, 2280.0, 3892.5],
        }
    )

    _, stats = run_b1_screen_with_stats(
        {"ORDER.SZ": frame},
        pick_date=pick_date,
        config={"j_threshold": 20.0, "j_q_threshold": 0.5},
    )

    assert stats["fail_weekly_ma"] == 1
    assert stats["fail_chg_cap"] == 0
    assert stats["fail_v_shrink"] == 0
    assert stats["fail_safe_mode"] == 0
    assert stats["fail_lt_filter"] == 0
```

- [ ] **Step 2: Run the focused strategy tests and verify failure**

Run: `PYTHONPATH=src pytest -q tests/test_b1_logic.py -k "reports_first_failed_condition_counts or keeps_legacy_order_before_new_filters"`

Expected:

- stats mismatch because the new counters do not exist yet
- `run_b1_screen_with_stats()` ignores the new prepared columns

- [ ] **Step 3: Implement the new counters and screening order**

Update the stats dict and append the new gates after `fail_max_vol`.

```python
# src/stock_select/strategies/b1.py
def run_b1_screen_with_stats(...):
    stats = {
        "total_symbols": len(prepared_by_symbol),
        "eligible": 0,
        "fail_j": 0,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_weekly_ma": 0,
        "fail_max_vol": 0,
        "fail_chg_cap": 0,
        "fail_v_shrink": 0,
        "fail_safe_mode": 0,
        "fail_lt_filter": 0,
        "selected": 0,
    }
    ...
    if not bool(row["max_vol_not_bearish"]):
        stats["fail_max_vol"] += 1
        continue
    if not (float(row["chg_d"]) <= 4.0):
        stats["fail_chg_cap"] += 1
        continue
    if not bool(row["v_shrink"]):
        stats["fail_v_shrink"] += 1
        continue
    if not bool(row["safe_mode"]):
        stats["fail_safe_mode"] += 1
        continue
    if not bool(row["lt_filter"]):
        stats["fail_lt_filter"] += 1
        continue
```

- [ ] **Step 4: Re-run the focused strategy tests and verify they pass**

Run: `PYTHONPATH=src pytest -q tests/test_b1_logic.py -k "reports_first_failed_condition_counts or keeps_legacy_order_before_new_filters"`

Expected: `2 passed`

- [ ] **Step 5: Commit the screening-order change**

```bash
git add src/stock_select/strategies/b1.py tests/test_b1_logic.py
git commit -m "feat: tighten b1 screen conditions"
```

### Task 3: Update CLI B1 Fixtures And Breakdown Output

**Files:**
- Modify: `src/stock_select/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI test updates**

First, add a helper for reusable `b1` stats payloads so every fake `run_b1_screen_with_stats()` return can carry the new keys without hand-copying the whole dict.

```python
# tests/test_cli.py
def _b1_screen_stats(*, total_symbols: int, eligible: int, selected: int, **overrides: int) -> dict[str, int]:
    stats = {
        "total_symbols": total_symbols,
        "eligible": eligible,
        "fail_j": 0,
        "fail_insufficient_history": 0,
        "fail_close_zxdkx": 0,
        "fail_zxdq_zxdkx": 0,
        "fail_weekly_ma": 0,
        "fail_max_vol": 0,
        "fail_chg_cap": 0,
        "fail_v_shrink": 0,
        "fail_safe_mode": 0,
        "fail_lt_filter": 0,
        "selected": selected,
    }
    stats.update(overrides)
    return stats
```

Then update `test_screen_emits_filter_breakdown_stats()` to expect the new counters.

```python
def fake_run_b1_screen_with_stats(...):
    return (
        [{"code": "000001.SZ", "pick_date": "2026-04-01", "close": 10.6, "turnover_n": 1030.0}],
        _b1_screen_stats(
            total_symbols=10,
            eligible=8,
            selected=1,
            fail_j=2,
            fail_insufficient_history=3,
            fail_close_zxdkx=1,
            fail_zxdq_zxdkx=2,
            fail_weekly_ma=1,
            fail_max_vol=1,
            fail_chg_cap=4,
            fail_v_shrink=5,
            fail_safe_mode=6,
            fail_lt_filter=7,
        ),
    )


assert (
    "[screen] breakdown total_symbols=10 eligible=8 fail_j=2 fail_insufficient_history=3 "
    "fail_close_zxdkx=1 fail_zxdq_zxdkx=2 fail_weekly_ma=1 fail_max_vol=1 "
    "fail_chg_cap=4 fail_v_shrink=5 fail_safe_mode=6 fail_lt_filter=7 selected=1"
) in result.stderr
```

Also sweep fake prepared frames used by real `b1` screen paths so they provide pass-through defaults:

```python
"chg_d": [1.0],
"amp_d": [2.0],
"body_d": [-1.0],
"vm3": [90.0],
"vm5": [100.0],
"vm10": [120.0],
"m5": [10.4],
"v_shrink": [True],
"safe_mode": [True],
"lt_filter": [True],
```

- [ ] **Step 2: Run the focused CLI tests and verify failure**

Run: `PYTHONPATH=src pytest -q tests/test_cli.py -k "screen_emits_filter_breakdown_stats or prepare_screen_data_uses_reference_b1_windows"`

Expected:

- breakdown string assertion fails because `_emit_screen_breakdown()` still prints the old payload
- some `b1` CLI tests may fail with `KeyError` until all fake prepared frames and fake stats payloads are updated

- [ ] **Step 3: Implement the CLI breakdown update and finish the test sweep**

Update `_emit_screen_breakdown()` to print the new counters and convert the major fake `b1` stats dictionaries in `tests/test_cli.py` to `_b1_screen_stats(...)`.

```python
# src/stock_select/cli.py
if method == "b1":
    reporter.emit(
        "screen",
        "breakdown "
        f"total_symbols={stats['total_symbols']} "
        f"eligible={stats['eligible']} "
        f"fail_j={stats['fail_j']} "
        f"fail_insufficient_history={stats['fail_insufficient_history']} "
        f"fail_close_zxdkx={stats['fail_close_zxdkx']} "
        f"fail_zxdq_zxdkx={stats['fail_zxdq_zxdkx']} "
        f"fail_weekly_ma={stats['fail_weekly_ma']} "
        f"fail_max_vol={stats['fail_max_vol']} "
        f"fail_chg_cap={stats['fail_chg_cap']} "
        f"fail_v_shrink={stats['fail_v_shrink']} "
        f"fail_safe_mode={stats['fail_safe_mode']} "
        f"fail_lt_filter={stats['fail_lt_filter']} "
        f"selected={stats['selected']}",
    )
```

- [ ] **Step 4: Re-run the focused CLI tests and verify they pass**

Run: `PYTHONPATH=src pytest -q tests/test_cli.py -k "screen_emits_filter_breakdown_stats or prepare_screen_data_uses_reference_b1_windows"`

Expected: `2 passed`

- [ ] **Step 5: Commit the CLI/test fixture alignment**

```bash
git add src/stock_select/cli.py tests/test_cli.py
git commit -m "test: align b1 cli fixtures with tighter screening"
```

### Task 4: Update User-Facing B1 Documentation

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/stock-select/references/b1-selector.md`

- [ ] **Step 1: Write the documentation changes**

Update the `README.md` `B1` screening section so the rule order matches the code:

```md
## B1 筛选说明

当前 B1 初筛按以下顺序逐条过滤：

0. 先按目标日 `turnover_n` 构建流动性池，只保留成交额排名前 `5000` 的股票
1. `J < 15` 或 `J <= 截至当日历史 J 的 10% expanding 分位`
2. `zxdkx` 历史是否足够，目标日是否可计算
3. `close > zxdkx`
4. `zxdq > zxdkx`
5. `weekly_ma_bull`
6. `max_vol_not_bearish`
7. `chg_d <= 4.0`
8. `v_shrink`
9. `safe_mode`
10. `lt_filter`

新增失败计数含义：

- `fail_chg_cap`: 当日涨幅超过 4%
- `fail_v_shrink`: 近 3 日均量未低于近 10 日均量
- `fail_safe_mode`: 近期出现放量派发后仍处于危险冷却区
- `fail_lt_filter`: 长趋势方向近 30 日翻向次数过多，且不满足 waiver
```

Update `.agents/skills/stock-select/references/b1-selector.md`:

```md
Required conditions:

- J is low enough by absolute threshold or low historical quantile.
- `close > zxdkx`.
- `zxdq > zxdkx`.
- Weekly moving averages are in bullish alignment.
- The max-volume day inside the lookback window is not bearish.
- `chg_d <= 4.0`.
- `v_shrink`.
- `safe_mode`.
- `lt_filter`.
```

- [ ] **Step 2: Review the docs diff for wording drift**

Run: `git diff -- README.md .agents/skills/stock-select/references/b1-selector.md`

Expected:

- no mention of `HLTH_SPC`, `ENV_OK`, `TOP_RES`, or other out-of-scope branches
- the documented order matches the code order from Task 2 exactly

- [ ] **Step 3: Commit the doc update**

```bash
git add README.md .agents/skills/stock-select/references/b1-selector.md
git commit -m "docs: document tighter b1 screening rules"
```

### Task 5: Run Verification And Close Out

**Files:**
- Modify: only files touched by Tasks 1-4 if verification exposes missed stubs or counters

- [ ] **Step 1: Run the full `b1` strategy tests**

Run: `PYTHONPATH=src pytest -q tests/test_b1_logic.py`

Expected: all `tests/test_b1_logic.py` cases pass

- [ ] **Step 2: Run the focused CLI `b1` slice**

Run: `PYTHONPATH=src pytest -q tests/test_cli.py -k "b1 and (screen or prepare_screen_data)"`

Expected: all targeted `b1` screen/preparation cases pass without `KeyError` for missing new stats or columns

- [ ] **Step 3: Fix any remaining fake `b1` payloads revealed by the CLI slice**

Use this exact default stub shape anywhere a fake `b1` stats payload still exists:

```python
_b1_screen_stats(total_symbols=1, eligible=1, selected=1)
```

Use this exact prepared-row default anywhere a fake prepared frame still hits real `run_b1_screen_with_stats()`:

```python
{
    "trade_date": pd.to_datetime(["2026-04-01"]),
    "close": [10.6],
    "J": [10.0],
    "zxdq": [10.5],
    "zxdkx": [10.2],
    "weekly_ma_bull": [True],
    "max_vol_not_bearish": [True],
    "chg_d": [1.0],
    "amp_d": [2.0],
    "body_d": [-1.0],
    "vm3": [90.0],
    "vm5": [100.0],
    "vm10": [120.0],
    "m5": [10.4],
    "v_shrink": [True],
    "safe_mode": [True],
    "lt_filter": [True],
    "turnover_n": [1030.0],
}
```

- [ ] **Step 4: Re-run the verification commands until green**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_b1_logic.py
PYTHONPATH=src pytest -q tests/test_cli.py -k "b1 and (screen or prepare_screen_data)"
```

Expected: both commands finish green

- [ ] **Step 5: Commit the final integrated implementation**

```bash
git add src/stock_select/strategies/b1.py src/stock_select/strategies/__init__.py src/stock_select/cli.py tests/test_b1_logic.py tests/test_cli.py README.md .agents/skills/stock-select/references/b1-selector.md
git commit -m "feat: tighten b1 screen with risk filters"
```
