# Stock Select Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new standalone `uv`-managed repository that installs a global `stock-select` skill under `~/.agents/skills/stock-select`, reads PostgreSQL market tables directly, reproduces `B1` screening, renders daily charts, and orchestrates multimodal subagent review.

**Architecture:** Treat `/home/pi/Documents/agents/StockTradebyZ` as a reference repository only. Create a new standalone repository with bundled scripts and references. Keep deterministic screening and charting in Python, and reserve multimodal reasoning for subagent-based chart review.

**Tech Stack:** Python 3.13, uv, pandas, numpy, plotly, psycopg, PyYAML, optional numba

---

### Task 1: Initialize Standalone Repository

**Files:**
- Create: `<new-repo>/pyproject.toml`
- Create: `<new-repo>/.gitignore`
- Create: `<new-repo>/README.md`
- Create: `<new-repo>/src/stock_select/__init__.py`

- [ ] **Step 1: Create the new repository directory**

Run: `mkdir -p /home/pi/Documents/agents/stock-select`
Expected: directory exists and is empty or only contains files created for this project

- [ ] **Step 2: Initialize a git repository**

Run: `git init /home/pi/Documents/agents/stock-select`
Expected: output includes `Initialized empty Git repository`

- [ ] **Step 3: Initialize the project with uv**

Run: `uv init --package /home/pi/Documents/agents/stock-select`
Expected: `pyproject.toml` and package skeleton created

- [ ] **Step 4: Update project metadata and dependencies**

Edit `pyproject.toml` to include the runtime dependencies required for:

```toml
[project]
name = "stock-select"
version = "0.1.0"
description = "Standalone B1 stock screening and chart-review orchestration skill"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
  "numpy>=2.4.0",
  "pandas>=3.0.0",
  "plotly>=6.5.0",
  "psycopg[binary]>=3.2.0",
  "PyYAML>=6.0.0",
]
```

- [ ] **Step 5: Add an initial `.gitignore`**

Use:

```gitignore
.venv/
__pycache__/
*.pyc
runtime/
.pytest_cache/
dist/
build/
```

- [ ] **Step 6: Commit repository bootstrap**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add pyproject.toml .gitignore README.md src/stock_select/__init__.py
git commit -m "chore: bootstrap stock-select repo"
```

Expected: commit succeeds in the new repository

### Task 2: Add Skill Skeleton And References

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/SKILL.md`
- Create: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/references/b1-selector.md`
- Create: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/references/review-rubric.md`
- Create: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/references/runtime-layout.md`

- [ ] **Step 1: Write the skill frontmatter and overview**

Use this header:

```md
---
name: stock-select
description: Use when screening A-share stocks from the stock-cache PostgreSQL database with the B1 method, generating daily charts, and coordinating multimodal subagents for chart review and final conclusions.
---
```

- [ ] **Step 2: Document the required workflow in `SKILL.md`**

Include these requirements:

```md
- Always require `--method b1`
- Do not use `stock-cache read` CLI as the primary data source
- Read PostgreSQL tables directly
- Run deterministic screening in Python first
- Generate daily charts before review
- Spawn subagents in parallel for multimodal review
- Use the bundled review rubric, but let the framework choose the multimodal model
- Write outputs under `~/.agents/skills/stock-select/runtime/`
```

- [ ] **Step 3: Create the `B1` reference note**

Summarize the repository behavior to reproduce:

```md
- J low or low historical quantile
- close > zxdkx
- zxdq > zxdkx
- weekly MA bullish alignment
- max-volume day in lookback must be non-bearish
```

- [ ] **Step 4: Create the review rubric reference**

Copy the structure of the current repository prompt into a concise, model-agnostic rubric describing:

```md
- trend structure
- volume behavior
- previous abnormal move
- signal type
- scoring JSON format
```

- [ ] **Step 5: Create the runtime layout reference**

Document:

```md
~/.agents/skills/stock-select/runtime/
  candidates/<pick_date>.json
  charts/<pick_date>/<code>_day.jpg
  reviews/<pick_date>/<code>.json
  reviews/<pick_date>/summary.json
```

- [ ] **Step 6: Commit the skill skeleton**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add .agents/skills/stock-select
git commit -m "feat: add stock-select skill skeleton"
```

Expected: skill files are committed

### Task 3: Implement Database Access Layer

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/db_access.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_db_access.py`

- [ ] **Step 1: Write a failing test for DSN resolution and query shape**

Use:

```python
from stock_select.db_access import resolve_dsn


def test_resolve_dsn_prefers_argument():
    assert resolve_dsn("postgresql://example", None) == "postgresql://example"
```

- [ ] **Step 2: Run the test to verify failure**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_db_access.py -v`
Expected: FAIL because module does not exist yet

- [ ] **Step 3: Implement minimal DSN and query helpers**

Create functions for:

```python
def resolve_dsn(cli_dsn: str | None, env_dsn: str | None) -> str: ...
def fetch_daily_window(...): ...
def fetch_symbol_history(...): ...
def fetch_available_trade_dates(...): ...
```

Use `psycopg` and return pandas DataFrames with normalized column names.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_db_access.py -v`
Expected: PASS

- [ ] **Step 5: Commit database access layer**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add src/stock_select/db_access.py tests/test_db_access.py
git commit -m "feat: add database access helpers"
```

Expected: commit succeeds

### Task 4: Implement B1 Logic

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/b1_logic.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_b1_logic.py`

- [ ] **Step 1: Write failing tests for `turnover_n`, `zxdq/zxdkx`, and B1 pass/fail**

Use tests like:

```python
import pandas as pd

from stock_select.b1_logic import compute_turnover_n


def test_compute_turnover_n_uses_midprice_times_volume():
    df = pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "close": [12.0, 13.0],
            "volume": [100.0, 200.0],
        }
    )
    out = compute_turnover_n(df, window=2)
    assert round(float(out.iloc[-1]), 2) == 3400.0
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_b1_logic.py -v`
Expected: FAIL because implementation does not exist yet

- [ ] **Step 3: Implement deterministic B1 calculations**

Add functions for:

```python
def compute_turnover_n(df: pd.DataFrame, window: int) -> pd.Series: ...
def compute_kdj(df: pd.DataFrame, n: int = 9) -> pd.DataFrame: ...
def compute_zx_lines(df: pd.DataFrame, ...) -> tuple[pd.Series, pd.Series]: ...
def compute_weekly_ma_bull(df: pd.DataFrame, ...) -> pd.Series: ...
def max_vol_not_bearish(df: pd.DataFrame, lookback: int) -> pd.Series: ...
def run_b1_screen(prepared_by_symbol: dict[str, pd.DataFrame], pick_date: pd.Timestamp, config: dict) -> list[dict]: ...
```

Map database `vol` to the internal volume field before calculation.

- [ ] **Step 4: Run the tests to verify passing behavior**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_b1_logic.py -v`
Expected: PASS

- [ ] **Step 5: Commit B1 logic**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add src/stock_select/b1_logic.py tests/test_b1_logic.py
git commit -m "feat: implement deterministic b1 screening"
```

Expected: commit succeeds

### Task 5: Implement Runtime Models And Candidate Serialization

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/models.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_models.py`

- [ ] **Step 1: Write failing tests for candidate serialization**

Use:

```python
from stock_select.models import CandidateRecord


def test_candidate_record_omits_none_fields():
    record = CandidateRecord(code="000001.SZ", pick_date="2026-04-01", method="b1", close=10.0, turnover_n=20.0)
    payload = record.to_dict()
    assert payload["code"] == "000001.SZ"
    assert payload["method"] == "b1"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_models.py -v`
Expected: FAIL

- [ ] **Step 3: Implement runtime models**

Include:

```python
@dataclass
class CandidateRecord: ...

@dataclass
class CandidateRun: ...

@dataclass
class ReviewRecord: ...
```

Each should support `to_dict()` for JSON output.

- [ ] **Step 4: Run the tests to verify passing behavior**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit models**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add src/stock_select/models.py tests/test_models.py
git commit -m "feat: add runtime data models"
```

Expected: commit succeeds

### Task 6: Implement Daily Chart Generation

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/charting.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_charting.py`

- [ ] **Step 1: Write a failing test for chart object creation**

Use:

```python
import pandas as pd

from stock_select.charting import build_daily_chart


def test_build_daily_chart_returns_plotly_figure():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-04-01", "2026-04-02"]),
            "open": [10.0, 10.5],
            "high": [10.8, 10.9],
            "low": [9.8, 10.1],
            "close": [10.6, 10.7],
            "volume": [1000.0, 1200.0],
        }
    )
    fig = build_daily_chart(df, "000001.SZ")
    assert fig is not None
```

- [ ] **Step 2: Run the test to verify failure**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_charting.py -v`
Expected: FAIL

- [ ] **Step 3: Implement chart generation**

Recreate the core current-repository behavior:

```python
def build_daily_chart(df: pd.DataFrame, code: str, bars: int = 120):
    ...

def export_daily_chart(df: pd.DataFrame, code: str, out_path: Path, bars: int = 120) -> Path:
    ...
```

Render candlesticks, moving overlays needed for visual review, and volume panel. Keep the output suitable for multimodal review.

- [ ] **Step 4: Run the test to verify passing behavior**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_charting.py -v`
Expected: PASS

- [ ] **Step 5: Commit charting**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add src/stock_select/charting.py tests/test_charting.py
git commit -m "feat: add daily chart rendering"
```

Expected: commit succeeds

### Task 7: Implement Review Orchestration Contract

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/review_orchestrator.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_review_orchestrator.py`

- [ ] **Step 1: Write a failing test for summary aggregation**

Use:

```python
from stock_select.review_orchestrator import summarize_reviews


def test_summarize_reviews_sorts_recommendations():
    reviews = [
        {"code": "A", "total_score": 3.0, "verdict": "FAIL"},
        {"code": "B", "total_score": 5.0, "verdict": "PASS"},
    ]
    summary = summarize_reviews("2026-04-01", "b1", reviews, min_score=4.0, failures=[])
    assert summary["recommendations"][0]["code"] == "B"
```

- [ ] **Step 2: Run the test to verify failure**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_review_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement orchestration helpers**

Create functions that the skill instructions can call around agent behavior:

```python
def build_review_payload(...): ...
def summarize_reviews(...): ...
```

The module should not hard-code Gemini. It should define the JSON contract and the aggregation behavior for subagent results.

- [ ] **Step 4: Run the test to verify passing behavior**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_review_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: Commit review orchestration helpers**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add src/stock_select/review_orchestrator.py tests/test_review_orchestrator.py
git commit -m "feat: add review aggregation helpers"
```

Expected: commit succeeds

### Task 8: Implement CLI Commands

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Update: `/home/pi/Documents/agents/stock-select/pyproject.toml`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`

- [ ] **Step 1: Write failing tests for `--method b1` enforcement**

Use:

```python
from typer.testing import CliRunner

from stock_select.cli import app


def test_screen_rejects_non_b1_method():
    runner = CliRunner()
    result = runner.invoke(app, ["screen", "--method", "brick"])
    assert result.exit_code != 0
    assert "b1" in result.stdout.lower()
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the CLI**

Expose:

```python
screen
chart
review
run
```

And add a console script entry:

```toml
[project.scripts]
stock-select = "stock_select.cli:main"
```

The CLI must:

- accept only `--method b1`
- use the skill-local runtime directory by default
- return structured errors on missing DB or missing candidate/chart inputs

- [ ] **Step 4: Run the tests to verify passing behavior**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit CLI**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add src/stock_select/cli.py pyproject.toml tests/test_cli.py
git commit -m "feat: add stock-select cli"
```

Expected: commit succeeds

### Task 9: Install Skill To Global Location

**Files:**
- Create: `~/.agents/skills/stock-select/SKILL.md`
- Create: `~/.agents/skills/stock-select/references/b1-selector.md`
- Create: `~/.agents/skills/stock-select/references/review-rubric.md`
- Create: `~/.agents/skills/stock-select/references/runtime-layout.md`

- [ ] **Step 1: Copy the skill files from the repository into the global skill location**

Run:

```bash
mkdir -p /home/pi/.agents/skills/stock-select
```

Then copy the skill folder contents from the new repository.

- [ ] **Step 2: Verify the installed skill files exist**

Run: `find /home/pi/.agents/skills/stock-select -maxdepth 2 -type f | sort`
Expected: list includes `SKILL.md` and reference files

- [ ] **Step 3: Commit the installable skill source**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add .agents/skills/stock-select
git commit -m "feat: add installable global skill source"
```

Expected: commit succeeds

### Task 10: End-To-End Smoke Test

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/README.md`

- [ ] **Step 1: Install dependencies**

Run: `cd /home/pi/Documents/agents/stock-select && uv sync`
Expected: virtual environment and dependencies installed

- [ ] **Step 2: Run unit tests**

Run: `cd /home/pi/Documents/agents/stock-select && uv run pytest -q`
Expected: all tests pass

- [ ] **Step 3: Run CLI smoke test for screening**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
uv run stock-select screen --method b1 --pick-date 2026-03-30
```

Expected: candidate JSON written under runtime directory or a structured DB reachability error

- [ ] **Step 4: Run CLI smoke test for chart generation**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
uv run stock-select chart --method b1 --pick-date 2026-03-30
```

Expected: chart files written for available candidates

- [ ] **Step 5: Document exact smoke-test commands in `README.md`**

Add usage examples for:

```md
uv run stock-select screen --method b1 --pick-date YYYY-MM-DD
uv run stock-select chart --method b1 --pick-date YYYY-MM-DD
uv run stock-select review --method b1 --pick-date YYYY-MM-DD
uv run stock-select run --method b1 --pick-date YYYY-MM-DD
```

- [ ] **Step 6: Commit smoke-test documentation**

Run:

```bash
cd /home/pi/Documents/agents/stock-select
git add README.md
git commit -m "docs: add stock-select usage examples"
```

Expected: commit succeeds
