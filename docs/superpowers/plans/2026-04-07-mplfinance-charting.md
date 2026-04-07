# Mplfinance Charting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Plotly and Kaleido based chart export with `mplfinance` while preserving the existing PNG output contract for CLI and review workflows.

**Architecture:** Keep the public export function signature stable, but change chart preparation into a normalized OHLCV DataFrame builder and render the figure directly with `mplfinance`. Remove browser-dependent dependencies and rewrite tests around observable PNG export behavior rather than Plotly figure internals.

**Tech Stack:** Python 3.13, pandas, mplfinance, matplotlib, pytest, uv

---

### Task 1: Replace Plotly-Centric Tests With Export-Contract Tests

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_charting.py`

- [ ] **Step 1: Write the failing tests for the new charting contract**

Add tests covering:

```python
def test_prepare_daily_chart_frame_sorts_and_shapes_columns() -> None: ...
def test_export_daily_chart_writes_png_file(tmp_path: Path) -> None: ...
def test_export_daily_chart_respects_bars_limit(tmp_path: Path) -> None: ...
```

- [ ] **Step 2: Run the charting test file to verify failure**

Run: `uv run pytest tests/test_charting.py -v`
Expected: FAIL because `charting.py` still exposes Plotly-specific behavior

- [ ] **Step 3: Remove Plotly-only assertions**

Delete tests that require:

- `plotly.graph_objects.Figure`
- `pio.write_image`
- Kaleido and Chrome runtime error shims

- [ ] **Step 4: Run the charting test file again**

Run: `uv run pytest tests/test_charting.py -v`
Expected: FAIL only on the new `mplfinance`-oriented expectations

### Task 2: Implement `mplfinance` Chart Preparation And PNG Export

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/charting.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_charting.py`

- [ ] **Step 1: Add a normalized chart-frame helper**

Implement a helper shaped like:

```python
def _prepare_daily_chart_frame(df: pd.DataFrame, bars: int = 120) -> pd.DataFrame:
    ...
```

It should:

- convert `date` to datetime
- sort by date ascending
- compute `zxdq` and `zxdkx`
- tail by `bars` when `bars > 0`
- return a DataFrame indexed by date with `Open/High/Low/Close/Volume/zxdq/zxdkx`

- [ ] **Step 2: Replace Plotly export with `mplfinance.plot()`**

Implement `export_daily_chart()` around:

```python
frame = _prepare_daily_chart_frame(df, bars=bars)
apds = [
    mpf.make_addplot(frame["zxdq"], color="#e67e22"),
    mpf.make_addplot(frame["zxdkx"], color="#2980b9"),
]
mpf.plot(
    frame,
    type="candle",
    volume=True,
    addplot=apds,
    savefig=dict(fname=str(out_path), dpi=144),
)
```

Use a stable style and set the title from `code`.

- [ ] **Step 3: Remove Plotly and Kaleido specific code**

Delete:

- `plotly.graph_objects`
- `plotly.io`
- `ChromeNotFoundError`
- Plotly range-break logic

- [ ] **Step 4: Run the charting tests to verify they pass**

Run: `uv run pytest tests/test_charting.py -v`
Expected: PASS

### Task 3: Update Dependencies And Documentation

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/pyproject.toml`
- Modify: `/home/pi/Documents/agents/stock-select/README.md`

- [ ] **Step 1: Update runtime dependencies**

Change `pyproject.toml` to:

```toml
dependencies = [
    "mplfinance>=0.12.10b0",
    "numpy>=2.4.0",
    "pandas>=3.0.0",
    "psycopg[binary]>=3.2.0",
    "PyYAML>=6.0.0",
    "typer>=0.16.0",
]
```

- [ ] **Step 2: Update README charting note**

Replace browser/Kaleido guidance with a short note that static PNG export now uses `mplfinance` and no longer requires Chrome.

- [ ] **Step 3: Run focused verification**

Run: `uv run pytest tests/test_charting.py tests/test_cli.py -q`
Expected: all tests pass

- [ ] **Step 4: Commit the migration**

Run:

```bash
git add src/stock_select/charting.py tests/test_charting.py pyproject.toml README.md
git commit -m "refactor: switch chart export to mplfinance"
```

Expected: commit succeeds with only charting migration changes
