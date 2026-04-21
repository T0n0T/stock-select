# Analyze Symbol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `stock-select analyze-symbol` command that runs deterministic single-stock end-of-day `b2` analysis, writes an ad hoc chart plus `result.json`, and does not depend on candidate artifacts.

**Architecture:** Keep the CLI thin by adding one new command in `src/stock_select/cli.py` and one dedicated helper, `_analyze_symbol_impl(...)`, that reuses the existing PostgreSQL fetch, chart export, `b2` signal evaluation, and `b2` baseline reviewer logic. The new command writes its outputs under `runtime/ad_hoc/` so it stays isolated from the candidate-pool workflow.

**Tech Stack:** Python, Typer CLI, pandas, psycopg, pytest, mplfinance

---

## File Structure

- Modify: `src/stock_select/cli.py`
  - add the new `analyze-symbol` command
  - add `_analyze_symbol_impl(...)`
  - add any minimal helpers needed for symbol normalization or default pick-date resolution
- Modify: `tests/test_cli.py`
  - add CLI contract and implementation behavior coverage for `analyze-symbol`
- Modify: `README.md`
  - document the new command in the CLI usage section

No new module is required in the first pass because the behavior is intentionally narrow and can stay close to the existing CLI orchestration code.

### Task 1: Add CLI contract tests for `analyze-symbol`

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing CLI option test for missing `--symbol`**

Add this test near the other CLI contract tests in `tests/test_cli.py`:

```python
def test_analyze_symbol_requires_symbol(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["analyze-symbol", "--method", "b2", "--runtime-root", str(tmp_path)])

    assert result.exit_code != 0
    assert "--symbol" in result.stderr
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_requires_symbol -v
```

Expected: FAIL because `analyze-symbol` does not exist yet.

- [ ] **Step 3: Write the failing CLI option test for unsupported methods**

Add this test:

```python
def test_analyze_symbol_rejects_non_b2_method(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b1",
            "--symbol",
            "002350.SZ",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "only supports method b2" in result.stderr.lower()
```

- [ ] **Step 4: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_rejects_non_b2_method -v
```

Expected: FAIL because `analyze-symbol` does not exist yet.

- [ ] **Step 5: Add the minimal CLI command stub**

In `src/stock_select/cli.py`, add a new command after `review` and before `record-watch`:

```python
@app.command(name="analyze-symbol")
def analyze_symbol(
    method: str = typer.Option(..., "--method"),
    symbol: str = typer.Option(..., "--symbol"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_review_method(method)
    if normalized_method != "b2":
        raise typer.BadParameter("analyze-symbol currently only supports method b2.")
    reporter = ProgressReporter(enabled=progress)
    result_path = _analyze_symbol_impl(
        method=normalized_method,
        symbol=symbol,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        reporter=reporter,
    )
    typer.echo(str(result_path))
```

Also add a temporary implementation stub near the other `_..._impl` helpers:

```python
def _analyze_symbol_impl(
    *,
    method: str,
    symbol: str,
    pick_date: str | None,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    raise NotImplementedError("analyze-symbol is not implemented yet")
```

- [ ] **Step 6: Re-run the two CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_requires_symbol tests/test_cli.py::test_analyze_symbol_rejects_non_b2_method -v
```

Expected:

- `test_analyze_symbol_requires_symbol`: PASS because Typer enforces the required option
- `test_analyze_symbol_rejects_non_b2_method`: PASS because the command now rejects `b1`

- [ ] **Step 7: Commit the CLI contract scaffold**

Run:

```bash
git add tests/test_cli.py src/stock_select/cli.py
git commit -m "test: add analyze-symbol cli contract"
```

### Task 2: Add failing tests for default pick-date resolution and result path layout

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing default pick-date test**

Add this test:

```python
def test_analyze_symbol_defaults_to_latest_trade_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_impl(*, method: str, symbol: str, pick_date: str | None, dsn: str | None, runtime_root: Path, reporter):
        captured["method"] = method
        captured["symbol"] = symbol
        captured["pick_date"] = pick_date
        captured["runtime_root"] = runtime_root
        return tmp_path / "result.json"

    monkeypatch.setattr(cli, "_analyze_symbol_impl", fake_impl)

    result = runner.invoke(
        app,
        [
            "analyze-symbol",
            "--method",
            "b2",
            "--symbol",
            "002350.SZ",
            "--runtime-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert captured["pick_date"] is None
    assert str(tmp_path / "result.json") in result.stdout
```

- [ ] **Step 2: Run the test to verify it fails if the CLI contract changed unexpectedly**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_defaults_to_latest_trade_date -v
```

Expected: PASS once the command stub exists; this test locks the contract that omitted `--pick-date` reaches the implementation as `None`.

- [ ] **Step 3: Write the failing implementation-layout test**

Add this test:

```python
def test_analyze_symbol_impl_writes_result_under_ad_hoc_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-21")
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol] * 3,
                "trade_date": ["2026-04-17", "2026-04-18", "2026-04-21"],
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.5, 10.8],
                "low": [9.9, 10.1, 10.2],
                "close": [10.2, 10.4, 10.7],
                "vol": [100.0, 120.0, 150.0],
            }
        ),
    )
    monkeypatch.setattr(cli, "_prepare_chart_data", lambda history: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}))
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-21"),
                    "open": 10.4,
                    "high": 10.8,
                    "low": 10.2,
                    "close": 10.7,
                    "volume": 150.0,
                    "pct": 2.88,
                    "J": 18.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": True,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 2.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 2.0,
            "macd_phase": 4.0,
            "total_score": 2.82,
            "signal_type": "rebound",
            "verdict": "FAIL",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350.SZ",
        pick_date=None,
        dsn=None,
        runtime_root=tmp_path,
    )

    assert result_path == tmp_path / "ad_hoc" / "2026-04-21.b2.002350.SZ" / "result.json"
```

- [ ] **Step 4: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_impl_writes_result_under_ad_hoc_runtime -v
```

Expected: FAIL because `_analyze_symbol_impl(...)` is still a stub.

- [ ] **Step 5: Commit the red tests if the repository convention expects incremental test commits**

Run:

```bash
git add tests/test_cli.py
git commit -m "test: cover analyze-symbol runtime contract"
```

If you prefer to avoid a red-test-only commit in this repository, skip the commit and continue directly to Task 3.

### Task 3: Implement `_analyze_symbol_impl(...)`

**Files:**
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Replace the `_analyze_symbol_impl(...)` stub with the real implementation**

In `src/stock_select/cli.py`, implement:

```python
def _analyze_symbol_impl(
    *,
    method: str,
    symbol: str,
    pick_date: str | None,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    normalized_symbol = _normalize_ts_code(symbol.upper())
    resolved_dsn = _resolve_cli_dsn(dsn)
    connection = _connect(resolved_dsn)

    if pick_date is None:
        effective_pick_date = fetch_nth_latest_trade_date(connection, end_date=_today_local_date(), n=1)
    else:
        effective_pick_date = pick_date

    start_date = (pd.Timestamp(effective_pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d")
    history = fetch_symbol_history(
        connection,
        symbol=normalized_symbol,
        start_date=start_date,
        end_date=effective_pick_date,
    )
    if history.empty:
        raise typer.BadParameter(f"No daily history found for symbol: {normalized_symbol}")

    frame = history.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.loc[frame["trade_date"] <= pd.Timestamp(effective_pick_date)].sort_values("trade_date").reset_index(drop=True)
    if frame.empty or not bool((frame["trade_date"] == pd.Timestamp(effective_pick_date)).any()):
        raise typer.BadParameter(
            f"No end-of-day data found for symbol {normalized_symbol} on pick_date {effective_pick_date}."
        )
    if "volume" not in frame.columns and "vol" in frame.columns:
        frame["volume"] = frame["vol"]

    signal_frame = _build_b2_signal_frame(frame, code=normalized_symbol)
    row = signal_frame.iloc[-1]
    signal = _resolve_signal(row)

    out_dir = runtime_root / "ad_hoc" / f"{effective_pick_date}.{method}.{normalized_symbol}"
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_path = export_daily_chart(
        _prepare_chart_data(history),
        normalized_symbol,
        out_dir / f"{normalized_symbol}_day.png",
    )
    baseline_review = review_b2_symbol_history(
        code=normalized_symbol,
        pick_date=effective_pick_date,
        history=history,
        chart_path=str(chart_path),
    )

    payload = {
        "code": normalized_symbol,
        "pick_date": effective_pick_date,
        "method": method,
        "signal": signal,
        "selected_as_candidate": signal is not None,
        "screen_conditions": {
            "pre_ok": bool(row["pre_ok"]),
            "pct_ok": bool(row["pct_ok"]),
            "volume_ok": bool(row["volume_ok"]),
            "k_shape": bool(row["k_shape"]),
            "j_up": bool(row["j_up"]),
            "tr_ok": bool(row["tr_ok"]),
            "above_lt": bool(row["above_lt"]),
            "raw_b2_unique": bool(row["raw_b2_unique"]),
            "cur_b2": bool(row["cur_b2"]),
            "cur_b3": bool(row["cur_b3"]),
            "cur_b3_plus": bool(row["cur_b3_plus"]),
            "cur_b4": bool(row["cur_b4"]),
            "cur_b5": bool(row["cur_b5"]),
        },
        "latest_metrics": {
            "trade_date": str(pd.Timestamp(row["trade_date"]).date()),
            "open": round(float(row["open"]), 3),
            "high": round(float(row["high"]), 3),
            "low": round(float(row["low"]), 3),
            "close": round(float(row["close"]), 3),
            "pct": round(float(row["pct"]), 3),
            "volume": round(float(row["volume"]), 3),
            "j": round(float(row["J"]), 3),
        },
        "baseline_review": baseline_review,
        "chart_path": str(chart_path),
    }
    result_path = out_dir / "result.json"
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return result_path
```

- [ ] **Step 2: Add minimal progress messages**

Inside `_analyze_symbol_impl(...)`, emit small checkpoints only if `reporter` is present:

```python
if reporter:
    reporter.emit("analyze-symbol", f"symbol={normalized_symbol}")
    reporter.emit("analyze-symbol", f"pick_date={effective_pick_date}")
    reporter.emit("analyze-symbol", "export chart")
    reporter.emit("analyze-symbol", f"done write={result_path}")
```

- [ ] **Step 3: Run the targeted implementation test**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_impl_writes_result_under_ad_hoc_runtime -v
```

Expected: PASS

- [ ] **Step 4: Add the failing payload-content test**

Add this test:

```python
def test_analyze_symbol_impl_writes_baseline_review_even_when_signal_is_null(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-21")
    history = pd.DataFrame(
        {
            "ts_code": ["002350.SZ"] * 3,
            "trade_date": ["2026-04-17", "2026-04-18", "2026-04-21"],
            "open": [10.0, 10.2, 10.4],
            "high": [10.3, 10.5, 10.8],
            "low": [9.9, 10.1, 10.2],
            "close": [10.2, 10.4, 10.7],
            "vol": [100.0, 120.0, 150.0],
        }
    )
    monkeypatch.setattr(cli, "fetch_symbol_history", lambda connection, symbol, start_date, end_date: history)
    monkeypatch.setattr(cli, "_prepare_chart_data", lambda frame: pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}))
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path: out_path)
    monkeypatch.setattr(
        cli,
        "_build_b2_signal_frame",
        lambda history, code: pd.DataFrame(
            [
                {
                    "trade_date": pd.Timestamp("2026-04-21"),
                    "open": 10.4,
                    "high": 10.8,
                    "low": 10.2,
                    "close": 10.7,
                    "volume": 150.0,
                    "pct": 2.88,
                    "J": 18.0,
                    "pre_ok": True,
                    "pct_ok": False,
                    "volume_ok": False,
                    "k_shape": True,
                    "j_up": True,
                    "tr_ok": True,
                    "above_lt": True,
                    "raw_b2_unique": False,
                    "cur_b2": False,
                    "cur_b3": False,
                    "cur_b3_plus": False,
                    "cur_b4": False,
                    "cur_b5": False,
                }
            ]
        ),
    )
    monkeypatch.setattr(cli, "_resolve_signal", lambda row: None)
    monkeypatch.setattr(
        cli,
        "review_b2_symbol_history",
        lambda code, pick_date, history, chart_path: {
            "code": code,
            "pick_date": pick_date,
            "chart_path": chart_path,
            "review_type": "baseline",
            "trend_structure": 3.0,
            "price_position": 1.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 2.0,
            "macd_phase": 5.0,
            "total_score": 2.84,
            "signal_type": "rebound",
            "verdict": "FAIL",
            "comment": "baseline",
        },
    )

    result_path = cli._analyze_symbol_impl(
        method="b2",
        symbol="002350.SZ",
        pick_date=None,
        dsn=None,
        runtime_root=tmp_path,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["signal"] is None
    assert payload["selected_as_candidate"] is False
    assert payload["baseline_review"]["verdict"] == "FAIL"
    assert payload["baseline_review"]["total_score"] == 2.84
```

- [ ] **Step 5: Run the payload-content test**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_impl_writes_baseline_review_even_when_signal_is_null -v
```

Expected: PASS

- [ ] **Step 6: Commit the implementation**

Run:

```bash
git add src/stock_select/cli.py tests/test_cli.py
git commit -m "feat: add analyze-symbol command"
```

### Task 4: Cover user-facing error cases

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing empty-history test**

Add this test:

```python
def test_analyze_symbol_impl_rejects_missing_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda connection, end_date, n: "2026-04-21")
    monkeypatch.setattr(cli, "fetch_symbol_history", lambda connection, symbol, start_date, end_date: pd.DataFrame())

    with pytest.raises(typer.BadParameter, match="No daily history found for symbol"):
        cli._analyze_symbol_impl(
            method="b2",
            symbol="002350.SZ",
            pick_date=None,
            dsn=None,
            runtime_root=tmp_path,
        )
```

- [ ] **Step 2: Run the test to verify it fails if error handling is missing**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_impl_rejects_missing_history -v
```

Expected: PASS once Task 3 implementation is in place.

- [ ] **Step 3: Write the failing missing-target-date-row test**

Add this test:

```python
def test_analyze_symbol_impl_rejects_missing_pick_date_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "_resolve_cli_dsn", lambda _dsn: "postgresql://example")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    history = pd.DataFrame(
        {
            "ts_code": ["002350.SZ"] * 2,
            "trade_date": ["2026-04-17", "2026-04-18"],
            "open": [10.0, 10.2],
            "high": [10.3, 10.5],
            "low": [9.9, 10.1],
            "close": [10.2, 10.4],
            "vol": [100.0, 120.0],
        }
    )
    monkeypatch.setattr(cli, "fetch_symbol_history", lambda connection, symbol, start_date, end_date: history)

    with pytest.raises(typer.BadParameter, match="No end-of-day data found for symbol 002350.SZ on pick_date 2026-04-21"):
        cli._analyze_symbol_impl(
            method="b2",
            symbol="002350.SZ",
            pick_date="2026-04-21",
            dsn=None,
            runtime_root=tmp_path,
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/test_cli.py::test_analyze_symbol_impl_rejects_missing_pick_date_row -v
```

Expected: PASS

- [ ] **Step 5: Run the focused CLI test group**

Run:

```bash
uv run pytest tests/test_cli.py -k "analyze_symbol" -v
```

Expected: all new `analyze_symbol` tests PASS.

- [ ] **Step 6: Commit the error-handling coverage**

Run:

```bash
git add tests/test_cli.py src/stock_select/cli.py
git commit -m "test: cover analyze-symbol error cases"
```

### Task 5: Document and verify the new command

**Files:**
- Modify: `README.md`
- Test: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Add the new command to the README usage section**

In `README.md`, add:

```text
uv run stock-select analyze-symbol --method b2 --symbol 002350.SZ --pick-date YYYY-MM-DD --dsn postgresql://...
```

Also add a short note in the usage or workflow section:

```text
- `analyze-symbol`
  - fetches one symbol directly from PostgreSQL
  - exports one daily PNG chart under `runtime/ad_hoc/`
  - writes one `result.json` containing deterministic signal conditions and baseline review
  - does not depend on candidate files or `review-merge`
```

- [ ] **Step 2: Run the command help output**

Run:

```bash
uv run stock-select analyze-symbol --help
```

Expected: help text shows `--method`, `--symbol`, `--pick-date`, `--dsn`, `--runtime-root`, and `--progress`.

- [ ] **Step 3: Run the focused test suite again**

Run:

```bash
uv run pytest tests/test_cli.py -k "analyze_symbol" -v
```

Expected: PASS

- [ ] **Step 4: Run one broader CLI smoke verification**

Run:

```bash
uv run pytest tests/test_cli.py -k "analyze_symbol or review_writes_summary_json or screen_accepts_pool_source_and_passes_it_to_screen_impl" -v
```

Expected: PASS, confirming the new command did not break unrelated CLI dispatch in nearby code.

- [ ] **Step 5: Commit the docs update**

Run:

```bash
git add README.md src/stock_select/cli.py tests/test_cli.py
git commit -m "docs: document analyze-symbol command"
```

## Self-Review

Spec coverage:

- new command: covered by Task 1 and Task 3
- default `pick_date`: covered by Task 2
- isolated `runtime/ad_hoc` output: covered by Task 2 and Task 3
- deterministic `b2` signal plus baseline review: covered by Task 3
- clear missing-history and missing-target-date errors: covered by Task 4
- README plus help verification: covered by Task 5

Placeholder scan:

- no `TODO`
- no deferred code steps
- every verification step names a concrete command and expected outcome

Type consistency:

- command name is consistently `analyze-symbol`
- helper name is consistently `_analyze_symbol_impl(...)`
- runtime path is consistently `runtime/ad_hoc/<pick_date>.<method>.<code>/result.json`
- payload field names match the spec: `signal`, `selected_as_candidate`, `screen_conditions`, `latest_metrics`, `baseline_review`, `chart_path`

## Execution Handoff

Plan complete and saved to `/home/pi/Documents/agents/stock-select/docs/superpowers/plans/2026-04-22-analyze-symbol.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
