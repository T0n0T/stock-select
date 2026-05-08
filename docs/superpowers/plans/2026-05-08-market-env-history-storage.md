# Market Env History Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a main CLI `market-env rebuild` command and migrate market environment history persistence to `history.jsonl + latest.json` without old `history.json` compatibility.

**Architecture:** Keep all environment-history serialization and rebuild logic inside `src/stock_select/market_environment.py`, then make both the main CLI and the existing backfill script call those shared helpers. Programmatic reads should use `history.jsonl`, while human-facing inspection should use `latest.json`.

**Tech Stack:** Python, Typer, pytest, JSON/JSONL, pandas, psycopg

---

### Task 1: Lock In New Storage Format With Market Environment Tests

**Files:**
- Modify: `tests/test_market_environment.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_market_environment.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:

```python
def test_write_environment_history_writes_jsonl_and_latest_json(tmp_path: Path) -> None:
    intervals = [
        {
            "state": "strong",
            "start_date": "2026-05-12",
            "end_date": None,
            "evaluated_at": "2026-05-12",
            "source": "scheduled",
            "manual_override": False,
            "reason": "broad rally",
        }
    ]

    write_environment_history(tmp_path, intervals)

    assert (tmp_path / "environment" / "history.jsonl").exists()
    assert (tmp_path / "environment" / "latest.json").exists()
```

```python
def test_load_environment_history_reads_jsonl(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True, exist_ok=True)
    (environment_dir / "history.jsonl").write_text(
        '{"state":"neutral","start_date":"2026-05-05","end_date":"2026-05-11","evaluated_at":"2026-05-05","source":"scheduled","manual_override":false,"reason":"range"}\n',
        encoding="utf-8",
    )

    assert load_environment_history(tmp_path) == [
        {
            "state": "neutral",
            "start_date": "2026-05-05",
            "end_date": "2026-05-11",
            "evaluated_at": "2026-05-05",
            "source": "scheduled",
            "manual_override": False,
            "reason": "range",
        }
    ]
```

```python
def test_load_environment_history_rejects_invalid_jsonl_line(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True, exist_ok=True)
    (environment_dir / "history.jsonl").write_text("{\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid environment history payload"):
        load_environment_history(tmp_path)
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_market_environment.py -k "jsonl or latest_json" -v`
Expected: FAIL because the implementation still reads and writes `history.json`.

- [ ] **Step 3: Implement the minimal serialization changes**

In `src/stock_select/market_environment.py`, add helpers shaped like:

```python
def _jsonl_history_path(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "history.jsonl"


def _latest_history_path(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "latest.json"
```

and update `write_environment_history(...)` / `load_environment_history(...)` to use those helpers.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_market_environment.py -k "jsonl or latest_json" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_market_environment.py src/stock_select/market_environment.py
git commit -m "refactor: store market environment history as jsonl"
```

### Task 2: Keep Environment Resolution And Mutation Behavior Green On New Storage

**Files:**
- Modify: `tests/test_market_environment.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_market_environment.py`

- [ ] **Step 1: Write the failing regression tests**

Add tests that assert `ensure_market_environment(...)` and `override_market_environment(...)` both update `history.jsonl` and `latest.json`, for example:

```python
def test_ensure_market_environment_writes_new_dual_files(tmp_path: Path) -> None:
    def fake_loader() -> dict[str, object]:
        return {
            "state": "neutral",
            "evaluate_date": "2026-05-12",
            "source": "scheduled",
            "reason": "range",
        }

    ensure_market_environment(tmp_path, pick_date="2026-05-12", evaluation_loader=fake_loader)

    assert (tmp_path / "environment" / "history.jsonl").exists()
    assert (tmp_path / "environment" / "latest.json").exists()
```

```python
def test_override_market_environment_updates_latest_snapshot(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "state": "strong",
                "start_date": "2026-05-12",
                "end_date": None,
                "evaluated_at": "2026-05-12",
                "source": "scheduled",
                "manual_override": False,
                "reason": "broad rally",
            }
        ],
    )

    override_market_environment(tmp_path, pick_date="2026-05-19", state="weak", reason="manual caution")

    latest = json.loads((tmp_path / "environment" / "latest.json").read_text(encoding="utf-8"))
    assert latest["intervals"][-1]["state"] == "weak"
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_market_environment.py -k "dual_files or latest_snapshot" -v`
Expected: FAIL until all write paths use the new storage helper.

- [ ] **Step 3: Route all mutation paths through the shared writer**

Ensure `ensure_market_environment(...)` and `override_market_environment(...)` only mutate the in-memory interval list and then call `write_environment_history(...)`.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_market_environment.py -k "dual_files or latest_snapshot" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_market_environment.py src/stock_select/market_environment.py
git commit -m "test: cover market environment dual-file persistence"
```

### Task 3: Add Main CLI `market-env rebuild` Command

**Files:**
- Modify: `src/stock_select/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

Add tests that invoke:

```python
result = runner.invoke(
    app,
    [
        "market-env",
        "rebuild",
        "--artifact-dir",
        str(artifact_dir),
        "--runtime-root",
        str(tmp_path),
        "--dsn",
        "postgresql://example",
        "--overwrite",
    ],
)
```

and assert:

```python
assert result.exit_code == 0
assert (tmp_path / "environment" / "history.jsonl").exists()
assert (tmp_path / "environment" / "latest.json").exists()
```

Also add a rejection case:

```python
assert result.exit_code != 0
assert "--overwrite" in result.stdout
```

- [ ] **Step 2: Run the focused CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "market_env_rebuild" -v`
Expected: FAIL because the command does not exist yet.

- [ ] **Step 3: Implement the command and shared rebuild helper**

Expose a reusable helper in `src/stock_select/market_environment.py` with a shape like:

```python
def rebuild_environment_history(
    *,
    runtime_root: Path,
    pick_dates: list[str],
    sse_history: pd.DataFrame,
    cn2000_history: pd.DataFrame,
    overwrite: bool,
) -> Path:
    ...
```

Then wire `@market_env_app.command("rebuild")` in `src/stock_select/cli.py` to:

- parse `--artifact-dir`
- load pick dates
- fetch index histories
- call `rebuild_environment_history(...)`

- [ ] **Step 4: Run the focused CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "market_env_rebuild" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/cli.py src/stock_select/market_environment.py tests/test_cli.py
git commit -m "feat: add market-env rebuild command"
```

### Task 4: Make `market-env history` Read Human Snapshot And Keep Script Reuse

**Files:**
- Modify: `src/stock_select/cli.py`
- Modify: `scripts/review_tuning_backfill_environment_history.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_review_tuning_backfill_environment_history.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_review_tuning_backfill_environment_history.py`

- [ ] **Step 1: Write the failing tests**

Add a CLI test asserting `market-env history` reflects `latest.json`:

```python
def test_market_env_history_reads_latest_snapshot(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True, exist_ok=True)
    (environment_dir / "latest.json").write_text(
        json.dumps({"intervals": [{"state": "neutral", "start_date": "2026-05-05", "end_date": None, "evaluated_at": "2026-05-05", "source": "scheduled", "manual_override": False, "reason": "range"}]}),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["market-env", "history", "--runtime-root", str(tmp_path)])
    assert result.exit_code == 0
    assert '"state": "neutral"' in result.stdout
```

Add a script test asserting the script now writes `history.jsonl` and `latest.json`.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "latest_snapshot" -v`
Run: `uv run pytest tests/test_review_tuning_backfill_environment_history.py -v`
Expected: FAIL until both entrypoints share the new persistence layer.

- [ ] **Step 3: Implement snapshot reads and script reuse**

In `src/stock_select/market_environment.py`, add a helper shaped like:

```python
def load_environment_history_snapshot(runtime_root: Path) -> dict[str, object]:
    ...
```

Use it from `market-env history`, and update `scripts/review_tuning_backfill_environment_history.py` to reuse the new rebuild helper instead of owning its own final write path.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "latest_snapshot" -v`
Run: `uv run pytest tests/test_review_tuning_backfill_environment_history.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/cli.py src/stock_select/market_environment.py scripts/review_tuning_backfill_environment_history.py tests/test_cli.py tests/test_review_tuning_backfill_environment_history.py
git commit -m "refactor: share environment history rebuild storage"
```

### Task 5: Run End-To-End Verification

**Files:**
- Modify: `tests/test_market_environment.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_review_tuning_backfill_environment_history.py`
- Modify: `src/stock_select/market_environment.py`
- Modify: `src/stock_select/cli.py`
- Modify: `scripts/review_tuning_backfill_environment_history.py`

- [ ] **Step 1: Run targeted market environment tests**

Run: `uv run pytest tests/test_market_environment.py -v`
Expected: PASS

- [ ] **Step 2: Run targeted CLI tests**

Run: `uv run pytest tests/test_cli.py -k "market_env or screen_calls_ensure_market_environment_before_fetch" -v`
Expected: PASS

- [ ] **Step 3: Run targeted rebuild script tests**

Run: `uv run pytest tests/test_review_tuning_backfill_environment_history.py -v`
Expected: PASS

- [ ] **Step 4: Run one CLI smoke check**

Run:

```bash
uv run stock-select market-env --help
uv run stock-select market-env rebuild --help
```

Expected: both commands exit 0 and show the new subcommand/options.

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/market_environment.py src/stock_select/cli.py scripts/review_tuning_backfill_environment_history.py tests/test_market_environment.py tests/test_cli.py tests/test_review_tuning_backfill_environment_history.py
git commit -m "test: verify market environment rebuild workflow"
```
