# Watch Pool Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `record-watch` CLI command that imports `PASS` and `WATCH` review results into a per-method CSV watch pool with overwrite support and trading-day-window retention, while switching the default runtime root to `~/.agent/skills/stock-select/runtime`.

**Architecture:** Keep CLI option parsing and command wiring in `src/stock_select/cli.py`, and move watch-pool CSV normalization, duplicate handling, sorting, and trimming into a new helper module. The command will read the existing review summary JSON, resolve the latest trade-date window through the current DB helpers, then write a deterministic CSV under `runtime/watch_pool/`.

**Tech Stack:** Python 3.13, Typer, pandas, psycopg, pytest

---

### Task 1: Lock the new default runtime path with tests

**Files:**
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
def test_default_runtime_root_uses_agent_skill_runtime() -> None:
    expected = Path.home() / ".agent" / "skills" / "stock-select" / "runtime"

    assert cli._default_runtime_root() == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_default_runtime_root_uses_agent_skill_runtime -v`
Expected: FAIL because `_default_runtime_root()` still returns the `.agents` path.

- [ ] **Step 3: Write minimal implementation**

```python
def _default_runtime_root() -> Path:
    return Path.home() / ".agent" / "skills" / "stock-select" / "runtime"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_default_runtime_root_uses_agent_skill_runtime -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/stock_select/cli.py
git commit -m "feat: update default stock-select runtime path"
```

### Task 2: Add failing CLI tests for watch-pool recording

**Files:**
- Modify: `tests/test_cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_record_watch_writes_csv_from_pass_and_watch_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b1"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b1",
                "recommendations": [
                    {"code": "AAA.SZ", "verdict": "PASS", "total_score": 4.8, "signal_type": "trend_start", "comment": "go"}
                ],
                "excluded": [
                    {"code": "BBB.SZ", "verdict": "WATCH", "total_score": 3.8, "signal_type": "rebound", "comment": "wait"},
                    {"code": "CCC.SZ", "verdict": "FAIL", "total_score": 2.1, "signal_type": "distribution_risk", "comment": "skip"},
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda _connection, *, end_date, n: "2026-04-10" if n == 1 else "2026-03-30")
    monkeypatch.setattr(cli, "time", SimpleNamespace(strftime=lambda _fmt: "2026-04-14T16:21:22+08:00"))

    result = runner.invoke(
        app,
        [
            "record-watch",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
        ],
    )

    csv_path = runtime_root / "watch_pool" / "b1.csv"
    assert result.exit_code == 0
    assert result.stdout.strip() == str(csv_path)
    rows = pd.read_csv(csv_path).to_dict(orient="records")
    assert [row["code"] for row in rows] == ["AAA.SZ", "BBB.SZ"]
    assert [row["verdict"] for row in rows] == ["PASS", "WATCH"]
```

```python
def test_record_watch_rejects_duplicate_without_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b1"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b1",
                "recommendations": [],
                "excluded": [
                    {"code": "AAA.SZ", "verdict": "WATCH", "total_score": 3.6, "signal_type": "rebound", "comment": "updated"},
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    watch_dir = runtime_root / "watch_pool"
    watch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "method": "b1",
                "pick_date": "2026-04-10",
                "code": "AAA.SZ",
                "verdict": "PASS",
                "total_score": 4.2,
                "signal_type": "trend_start",
                "comment": "existing",
                "recorded_at": "2026-04-11T10:00:00+08:00",
            }
        ]
    ).to_csv(watch_dir / "b1.csv", index=False)
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda _connection, *, end_date, n: "2026-04-10" if n == 1 else "2026-04-01")

    result = runner.invoke(
        app,
        [
            "record-watch",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--no-overwrite",
        ],
    )

    assert result.exit_code != 0
    assert "duplicate" in result.stderr.lower()
```

```python
def test_record_watch_overwrites_and_trims_old_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b1"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b1",
                "recommendations": [{"code": "AAA.SZ", "verdict": "PASS", "total_score": 4.9, "signal_type": "trend_start", "comment": "fresh"}],
                "excluded": [],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    watch_dir = runtime_root / "watch_pool"
    watch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "method": "b1",
                "pick_date": "2026-04-10",
                "code": "AAA.SZ",
                "verdict": "WATCH",
                "total_score": 3.7,
                "signal_type": "rebound",
                "comment": "stale",
                "recorded_at": "2026-04-11T10:00:00+08:00",
            },
            {
                "method": "b1",
                "pick_date": "2026-03-20",
                "code": "OLD.SZ",
                "verdict": "WATCH",
                "total_score": 3.1,
                "signal_type": "rebound",
                "comment": "old",
                "recorded_at": "2026-03-20T10:00:00+08:00",
            },
        ]
    ).to_csv(watch_dir / "b1.csv", index=False)
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "fetch_nth_latest_trade_date", lambda _connection, *, end_date, n: "2026-04-10" if n == 1 else "2026-04-01")

    result = runner.invoke(
        app,
        [
            "record-watch",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--window-trading-days",
            "8",
            "--overwrite",
        ],
    )

    rows = pd.read_csv(runtime_root / "watch_pool" / "b1.csv").to_dict(orient="records")
    assert result.exit_code == 0
    assert rows == [
        {
            "method": "b1",
            "pick_date": "2026-04-10",
            "code": "AAA.SZ",
            "verdict": "PASS",
            "total_score": 4.9,
            "signal_type": "trend_start",
            "comment": "fresh",
            "recorded_at": rows[0]["recorded_at"],
        }
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::test_record_watch_writes_csv_from_pass_and_watch_summary tests/test_cli.py::test_record_watch_rejects_duplicate_without_overwrite tests/test_cli.py::test_record_watch_overwrites_and_trims_old_rows -v`
Expected: FAIL because `record-watch` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@app.command(name="record-watch")
def record_watch(...):
    ...
```

```python
def _record_watch_impl(...):
    ...
```

```python
def merge_watch_pool_rows(...):
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py::test_record_watch_writes_csv_from_pass_and_watch_summary tests/test_cli.py::test_record_watch_rejects_duplicate_without_overwrite tests/test_cli.py::test_record_watch_overwrites_and_trims_old_rows -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/stock_select/cli.py src/stock_select/watch_pool.py
git commit -m "feat: add watch pool record command"
```

### Task 3: Add the watch-pool helper module

**Files:**
- Create: `src/stock_select/watch_pool.py`
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing helper-focused test**

```python
def test_record_watch_sorts_rows_by_trade_day_distance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_record_watch_sorts_rows_by_trade_day_distance -v`
Expected: FAIL because sorting and trimming helpers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
WATCH_POOL_COLUMNS = [
    "method",
    "pick_date",
    "code",
    "verdict",
    "total_score",
    "signal_type",
    "comment",
    "recorded_at",
]
```

```python
def load_watch_pool(csv_path: Path) -> pd.DataFrame:
    ...
```

```python
def summary_to_watch_rows(summary_payload: dict[str, object], *, method: str, pick_date: str, recorded_at: str) -> pd.DataFrame:
    ...
```

```python
def merge_watch_rows(existing: pd.DataFrame, incoming: pd.DataFrame, *, overwrite: bool) -> pd.DataFrame:
    ...
```

```python
def trim_and_sort_watch_rows(rows: pd.DataFrame, *, cutoff_trade_date: str, execution_trade_date: str) -> pd.DataFrame:
    ...
```

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `pytest tests/test_cli.py::test_record_watch_writes_csv_from_pass_and_watch_summary tests/test_cli.py::test_record_watch_rejects_duplicate_without_overwrite tests/test_cli.py::test_record_watch_overwrites_and_trims_old_rows tests/test_cli.py::test_record_watch_sorts_rows_by_trade_day_distance -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/watch_pool.py src/stock_select/cli.py tests/test_cli.py
git commit -m "refactor: isolate watch pool csv logic"
```

### Task 4: Update docs and run focused verification

**Files:**
- Modify: `README.md`
- Modify: `src/stock_select/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing documentation expectation test or assertion**

```python
def test_readme_mentions_record_watch_and_new_runtime_root() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "record-watch" in content
    assert "~/.agent/skills/stock-select/runtime" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_readme_mentions_record_watch_and_new_runtime_root -v`
Expected: FAIL because the README still mentions the old runtime root and lacks the new command.

- [ ] **Step 3: Write minimal implementation**

```markdown
uv run stock-select record-watch --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
```

```markdown
~/.agent/skills/stock-select/runtime/
```

- [ ] **Step 4: Run focused verification**

Run: `pytest tests/test_cli.py::test_default_runtime_root_uses_agent_skill_runtime tests/test_cli.py::test_record_watch_writes_csv_from_pass_and_watch_summary tests/test_cli.py::test_record_watch_rejects_duplicate_without_overwrite tests/test_cli.py::test_record_watch_overwrites_and_trims_old_rows tests/test_cli.py::test_record_watch_sorts_rows_by_trade_day_distance tests/test_cli.py::test_readme_mentions_record_watch_and_new_runtime_root -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_cli.py src/stock_select/cli.py
git commit -m "docs: describe watch pool recording command"
```
