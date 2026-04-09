# Intraday Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--intraday` support to the existing `screen`, `chart`, and `review` commands so the CLI can run a real-time B1 workflow from `Tushare rt_k` while preserving the existing end-of-day workflow.

**Architecture:** Keep the current command family and B1 logic intact, and add a thin intraday data path that normalizes `rt_k`, overlays a temporary current-day bar onto confirmed PostgreSQL history, and writes timestamped runtime artifacts. Reuse the latest intraday candidate and prepared cache for `chart --intraday` and `review --intraday`, and update the repository skill documentation in the same implementation.

**Tech Stack:** Python, Typer, pandas, psycopg, Tushare, pytest

---

## File Structure

- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
  - add `--intraday` command options
  - add latest intraday artifact resolution helpers
  - wire `screen`, `chart`, and `review` into the new intraday path
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/intraday.py`
  - normalize `Tushare rt_k` rows
  - build the intraday overlay frame
  - resolve latest intraday candidate and prepared cache metadata
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/db_access.py`
  - add any narrow DB helpers needed to derive the previous confirmed trade date for intraday mode
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
  - add end-to-end CLI tests for `--intraday`
- Create: `/home/pi/Documents/agents/stock-select/tests/test_intraday.py`
  - add unit tests for rt_k normalization and overlay behavior
- Modify: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/SKILL.md`
  - document the intraday workflow and runtime path conventions

### Task 1: Add Intraday Data Helpers

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/intraday.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_intraday.py`

- [ ] **Step 1: Write the failing unit tests for rt_k normalization and overlay**

```python
from __future__ import annotations

import pandas as pd

from stock_select.intraday import build_intraday_market_frame, normalize_rt_k_snapshot


def test_normalize_rt_k_snapshot_maps_required_columns() -> None:
    raw = pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "平安银行",
                "开盘价": 12.1,
                "最高价": 12.5,
                "最低价": 12.0,
                "最新价": 12.34,
                "成交量": 1234567,
                "成交额": 152300000.0,
                "更新时间": "11:31:07",
            }
        ]
    )

    normalized = normalize_rt_k_snapshot(raw, trade_date="2026-04-09")

    assert list(normalized.columns) == [
        "ts_code",
        "name",
        "trade_date",
        "trade_time",
        "open",
        "high",
        "low",
        "close",
        "vol",
        "amount",
    ]
    assert normalized.iloc[0]["ts_code"] == "000001.SZ"
    assert normalized.iloc[0]["close"] == 12.34


def test_build_intraday_market_frame_appends_current_day_bar() -> None:
    history = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "2026-04-07", "open": 11.8, "high": 12.0, "low": 11.7, "close": 11.9, "vol": 100.0},
            {"ts_code": "000001.SZ", "trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "trade_date": "2026-04-09",
                "trade_time": "11:31:07",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "vol": 150.0,
                "amount": 999.0,
            }
        ]
    )

    combined = build_intraday_market_frame(history, snapshot, trade_date="2026-04-09")

    assert list(combined["trade_date"].astype(str))[-1] == "2026-04-09"
    assert float(combined.iloc[-1]["close"]) == 12.34
    assert float(combined.iloc[-1]["vol"]) == 150.0
```

- [ ] **Step 2: Run the new unit tests to verify they fail**

Run: `uv run pytest tests/test_intraday.py -v`
Expected: FAIL because `stock_select.intraday` does not exist yet

- [ ] **Step 3: Implement the minimal intraday helper module**

```python
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


RT_K_COLUMN_MAP = {
    "代码": "code",
    "名称": "name",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "最新价": "close",
    "成交量": "vol",
    "成交额": "amount",
    "更新时间": "trade_time",
}


def _normalize_ts_code(code: str) -> str:
    stripped = code.strip()
    if stripped.endswith((".SZ", ".SH", ".BJ")):
        return stripped
    if stripped.startswith(("0", "2", "3")):
        return f"{stripped}.SZ"
    if stripped.startswith(("6", "9")):
        return f"{stripped}.SH"
    if stripped.startswith(("4", "8")):
        return f"{stripped}.BJ"
    msg = f"Unsupported ts_code: {code}"
    raise ValueError(msg)


def normalize_rt_k_snapshot(raw: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    renamed = raw.rename(columns=RT_K_COLUMN_MAP).copy()
    required = ["code", "name", "open", "high", "low", "close", "vol", "amount", "trade_time"]
    missing = [column for column in required if column not in renamed.columns]
    if missing:
        msg = f"rt_k snapshot missing columns: {missing}"
        raise ValueError(msg)

    normalized = pd.DataFrame(
        {
            "ts_code": renamed["code"].astype(str).map(_normalize_ts_code),
            "name": renamed["name"].astype(str),
            "trade_date": trade_date,
            "trade_time": renamed["trade_time"].astype(str),
            "open": renamed["open"].astype(float),
            "high": renamed["high"].astype(float),
            "low": renamed["low"].astype(float),
            "close": renamed["close"].astype(float),
            "vol": renamed["vol"].astype(float),
            "amount": renamed["amount"].astype(float),
        }
    )
    return normalized.sort_values(["ts_code"]).reset_index(drop=True)


def build_intraday_market_frame(
    history: pd.DataFrame,
    snapshot: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    frame = history.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d")

    intraday_rows = snapshot[["ts_code", "trade_date", "open", "high", "low", "close", "vol"]].copy()
    intraday_rows["trade_date"] = trade_date

    frame = frame[~((frame["trade_date"] == trade_date) & (frame["ts_code"].isin(intraday_rows["ts_code"])))]
    combined = pd.concat([frame, intraday_rows], ignore_index=True)
    return combined.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
```

- [ ] **Step 4: Run the unit tests again**

Run: `uv run pytest tests/test_intraday.py -v`
Expected: PASS

- [ ] **Step 5: Commit the helper module and tests**

```bash
git add src/stock_select/intraday.py tests/test_intraday.py
git commit -m "feat: add intraday snapshot helpers"
```

### Task 2: Add Intraday CLI Behavior To `screen`

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/db_access.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
- Test: `/home/pi/Documents/agents/stock-select/tests/test_intraday.py`

- [ ] **Step 1: Write failing CLI tests for `screen --intraday`**

```python
def test_screen_intraday_rejects_pick_date(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["screen", "--method", "b1", "--pick-date", "2026-04-09", "--intraday", "--runtime-root", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.stderr


def test_screen_intraday_writes_timestamped_candidate_and_prepared(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(cli, "_resolve_intraday_trade_date", lambda: "2026-04-09")
    monkeypatch.setattr(cli, "_resolve_previous_trade_date", lambda _connection, trade_date: "2026-04-08")
    monkeypatch.setattr(cli, "_fetch_rt_k_snapshot", lambda token, trade_date: (pd.DataFrame([{
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "trade_date": "2026-04-09",
        "trade_time": "11:31:07",
        "open": 12.1,
        "high": 12.5,
        "low": 12.0,
        "close": 12.34,
        "vol": 150.0,
        "amount": 999.0,
    }]), "2026-04-09T11-31-08+08-00"))
    monkeypatch.setattr(cli, "fetch_daily_window", lambda *args, **kwargs: pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0}
    ]))
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_resolve_tushare_token", lambda token: "token")

    result = runner.invoke(
        app,
        ["screen", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)],
    )

    assert result.exit_code == 0
    assert (runtime_root / "candidates" / "2026-04-09T11-31-08+08-00.json").exists()
    assert (runtime_root / "prepared" / "2026-04-09T11-31-08+08-00.pkl").exists()
```

- [ ] **Step 2: Run the focused CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_screen_intraday_rejects_pick_date tests/test_cli.py::test_screen_intraday_writes_timestamped_candidate_and_prepared -v`
Expected: FAIL because `screen` does not yet accept `--intraday`

- [ ] **Step 3: Implement `screen --intraday` in the CLI**

```python
def _resolve_tushare_token(cli_token: str | None) -> str:
    dotenv_token = load_dotenv_value(Path.cwd() / ".env", "TUSHARE_TOKEN")
    token = cli_token or os.getenv("TUSHARE_TOKEN") or dotenv_token
    if not token:
        raise ValueError("A Tushare token is required for intraday mode.")
    return token


def _intraday_candidate_path(runtime_root: Path, run_id: str) -> Path:
    return runtime_root / "candidates" / f"{run_id}.json"


def _resolve_intraday_trade_date() -> str:
    return pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d")


def _resolve_previous_trade_date(connection, trade_date: str) -> str:
    available = fetch_available_trade_dates(connection)
    dates = sorted(str(value) for value in available["trade_date"].astype(str).tolist())
    earlier = [value for value in dates if value < trade_date]
    if not earlier:
        raise ValueError(f"No previous trade date found before {trade_date}.")
    return earlier[-1]


def _screen_intraday_impl(
    *,
    dsn: str | None,
    tushare_token: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    resolved_dsn = _resolve_cli_dsn(dsn)
    resolved_token = _resolve_tushare_token(tushare_token)
    connection = _connect(resolved_dsn)
    trade_date = _resolve_intraday_trade_date()
    previous_trade_date = _resolve_previous_trade_date(connection, trade_date)
    snapshot, run_id = _fetch_rt_k_snapshot(resolved_token, trade_date)
    market = fetch_daily_window(connection, start_date=(pd.Timestamp(previous_trade_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d"), end_date=previous_trade_date)
    overlay_market = build_intraday_market_frame(market, snapshot, trade_date=trade_date)
    prepared = _prepare_screen_data(overlay_market, reporter=reporter)
    _write_prepared_cache(runtime_root / "prepared" / f"{run_id}.pkl", pick_date=trade_date, start_date=str((pd.Timestamp(previous_trade_date) - pd.Timedelta(days=366)).date()), end_date=trade_date, prepared_by_symbol=prepared)
    candidates, _stats = run_b1_screen_with_stats(prepared, pd.Timestamp(trade_date), DEFAULT_B1_CONFIG)
    out_path = _intraday_candidate_path(runtime_root, run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"mode": "intraday_snapshot", "method": "b1", "trade_date": trade_date, "fetched_at": run_id, "run_id": run_id, "source": "tushare_rt_k", "candidates": candidates}, indent=2), encoding="utf-8")
    return out_path
```

- [ ] **Step 4: Run the focused CLI tests again**

Run: `uv run pytest tests/test_cli.py::test_screen_intraday_rejects_pick_date tests/test_cli.py::test_screen_intraday_writes_timestamped_candidate_and_prepared -v`
Expected: PASS

- [ ] **Step 5: Commit the `screen --intraday` CLI work**

```bash
git add src/stock_select/cli.py src/stock_select/db_access.py tests/test_cli.py src/stock_select/intraday.py tests/test_intraday.py
git commit -m "feat: add intraday screen mode"
```

### Task 3: Add Latest Intraday Reuse To `chart` And `review`

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests for latest intraday reuse**

```python
def test_chart_intraday_uses_latest_intraday_candidate(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-09T11-31-08+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "trade_date": "2026-04-09",
                "fetched_at": "2026-04-09T11-31-08+08-00",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_load_intraday_prepared_cache", lambda runtime_root, run_id: {"000001.SZ": pd.DataFrame([
        {"date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "volume": 120.0},
        {"date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "volume": 150.0},
    ])})
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path, bars=120: out_path.write_bytes(b"png") or out_path)

    result = runner.invoke(app, ["chart", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code == 0
    assert (runtime_root / "charts" / "2026-04-09T11-31-08+08-00" / "000001.SZ_day.png").exists()


def test_review_intraday_uses_latest_intraday_candidate(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / "2026-04-09T11-31-08+08-00"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / "2026-04-09T11-31-08+08-00.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "trade_date": "2026-04-09",
                "fetched_at": "2026-04-09T11-31-08+08-00",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_load_intraday_prepared_cache", lambda runtime_root, run_id: {"000001.SZ": pd.DataFrame([
        {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
        {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
    ])})

    result = runner.invoke(app, ["review", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])

    assert result.exit_code == 0
    assert (runtime_root / "reviews" / "2026-04-09T11-31-08+08-00" / "summary.json").exists()
```

- [ ] **Step 2: Run the focused CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_chart_intraday_uses_latest_intraday_candidate tests/test_cli.py::test_review_intraday_uses_latest_intraday_candidate -v`
Expected: FAIL because `chart` and `review` do not yet resolve latest intraday artifacts

- [ ] **Step 3: Implement latest intraday resolution for `chart` and `review`**

```python
def _resolve_latest_intraday_candidate(runtime_root: Path) -> tuple[Path, dict]:
    candidate_dir = runtime_root / "candidates"
    latest_path: Path | None = None
    latest_payload: dict | None = None
    latest_run_id: str | None = None

    for candidate_path in sorted(candidate_dir.glob("*.json")):
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        if payload.get("mode") != "intraday_snapshot":
            continue
        run_id = str(payload.get("run_id") or candidate_path.stem)
        if latest_run_id is None or run_id > latest_run_id:
            latest_path = candidate_path
            latest_payload = payload
            latest_run_id = run_id

    if latest_path is None or latest_payload is None:
        raise typer.BadParameter("No intraday candidate file found.")
    return latest_path, latest_payload


def _load_intraday_prepared_cache(runtime_root: Path, run_id: str) -> dict[str, pd.DataFrame]:
    payload = _load_prepared_cache(runtime_root / "prepared" / f"{run_id}.pkl")
    prepared = payload["prepared_by_symbol"]
    if not isinstance(prepared, dict):
        raise ValueError("Prepared intraday payload missing prepared_by_symbol.")
    return prepared
```

- [ ] **Step 4: Run the focused CLI tests again**

Run: `uv run pytest tests/test_cli.py::test_chart_intraday_uses_latest_intraday_candidate tests/test_cli.py::test_review_intraday_uses_latest_intraday_candidate -v`
Expected: PASS

- [ ] **Step 5: Commit the latest intraday reuse behavior**

```bash
git add src/stock_select/cli.py tests/test_cli.py
git commit -m "feat: reuse latest intraday candidate for chart and review"
```

### Task 4: Update The Repository Skill File

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/SKILL.md`

- [ ] **Step 1: Write the updated skill guidance**

```markdown
## Required Workflow

- Always require `--method b1`.
- Reject any method other than `b1`.
- Use end-of-day mode when the caller supplies `--pick-date`.
- Use intraday mode when the caller requests live B1 analysis and run the existing commands with `--intraday`.
- In intraday mode, `screen --intraday` must combine PostgreSQL confirmed history with `Tushare rt_k`.
- In intraday mode, `chart --intraday` and `review --intraday` must reuse the latest intraday candidate and matching prepared cache instead of requesting a fresh real-time snapshot.
- Intraday runtime outputs must follow:
  - `runtime/candidates/<run_id>.json`
  - `runtime/prepared/<run_id>.pkl`
  - `runtime/charts/<run_id>/`
  - `runtime/reviews/<run_id>/`
```

- [ ] **Step 2: Update the execution order for intraday runs**

```markdown
## Execution Order

1. Resolve whether the run is end-of-day or intraday.
2. For end-of-day runs, resolve `pick_date` and query PostgreSQL market data needed for B1 screening.
3. For intraday runs, call `screen --intraday` first so the latest `run_id` candidate and prepared cache exist.
4. Run deterministic B1 screening and write candidate outputs.
5. Render daily chart PNG files for each candidate.
6. Run CLI `review` first to write baseline review outputs and `llm_review_tasks.json`.
7. After the CLI command returns, dispatch subagents from the task file against the rendered PNG files and `references/prompt.md`.
8. Write raw subagent JSON results under the matching `runtime/reviews/.../llm_review_results/`.
9. Run CLI `review-merge` to validate `llm_review`, merge it back into each per-stock review file, and rewrite the final summary.
```

- [ ] **Step 3: Review the skill file for consistency**

Run: `sed -n '1,260p' .agents/skills/stock-select/SKILL.md`
Expected: the skill text documents both end-of-day and intraday B1 workflows without contradicting the runtime path design

- [ ] **Step 4: Commit the skill file update**

```bash
git add .agents/skills/stock-select/SKILL.md
git commit -m "docs: add intraday workflow to stock-select skill"
```

### Task 5: Run Verification

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/db_access.py`
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/intraday.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
- Create: `/home/pi/Documents/agents/stock-select/tests/test_intraday.py`
- Modify: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/SKILL.md`

- [ ] **Step 1: Run the focused intraday test files**

Run: `uv run pytest tests/test_intraday.py tests/test_cli.py -q`
Expected: PASS for the new intraday coverage and no regression in existing CLI behavior

- [ ] **Step 2: Run the broader targeted suite**

Run: `uv run pytest tests/test_db_access.py tests/test_b1_logic.py tests/test_charting.py tests/test_review_orchestrator.py -q`
Expected: PASS so the intraday changes do not break the existing supporting modules

- [ ] **Step 3: Inspect the final git diff**

Run: `git status --short && git diff --stat`
Expected: only the intended intraday implementation files and the skill file are modified

- [ ] **Step 4: Commit any final verification fixes**

```bash
git add src/stock_select/cli.py src/stock_select/db_access.py src/stock_select/intraday.py tests/test_cli.py tests/test_intraday.py .agents/skills/stock-select/SKILL.md
git commit -m "feat: add intraday b1 workflow"
```
