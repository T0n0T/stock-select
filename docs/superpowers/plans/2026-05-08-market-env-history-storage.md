# Market Env Daily Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change market environment persistence to generate per-day human-readable files while keeping `history.jsonl` as a machine-readable daily index and `latest.json` as a combined daily/interval snapshot.

**Architecture:** Treat daily environment evaluations as the canonical persistence unit. Store full per-day payloads under `runtime/environment/daily/`, derive a compact daily `history.jsonl` for machine reads, and regenerate `latest.json` from those daily records so CLI history and interval resolution share one source of truth.

**Tech Stack:** Python, Typer, pytest, JSON/JSONL, pandas, psycopg

---

### Task 1: Lock In Daily-File Persistence Expectations

**Files:**
- Modify: `tests/test_market_environment.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_market_environment.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:

```python
def test_write_environment_history_writes_daily_files_jsonl_and_latest(tmp_path: Path) -> None:
    daily_records = [
        {
            "pick_date": "2026-05-12",
            "state": "strong",
            "score_based_state": "strong",
            "rule_based_state": "strong",
            "vote_based_state": "strong",
            "evaluate_date": "2026-05-12",
            "source": "scheduled",
            "reason": "broad rally",
            "total_score": 12.0,
            "score_based_total": 12.0,
        }
    ]

    write_environment_history(tmp_path, daily_records)

    assert (tmp_path / "environment" / "daily" / "2026-05-12.strong.json").exists()
    assert (tmp_path / "environment" / "history.jsonl").exists()
    assert (tmp_path / "environment" / "latest.json").exists()
```

```python
def test_load_environment_history_reads_daily_jsonl(tmp_path: Path) -> None:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True, exist_ok=True)
    (environment_dir / "history.jsonl").write_text(
        '{"pick_date":"2026-05-05","state":"neutral","score_based_state":"neutral","rule_based_state":"neutral","vote_based_state":"neutral","evaluate_date":"2026-05-05","source":"scheduled","reason":"range","total_score":0.0,"score_based_total":0.0}\n',
        encoding="utf-8",
    )

    assert load_environment_history(tmp_path) == [
        {
            "pick_date": "2026-05-05",
            "state": "neutral",
            "score_based_state": "neutral",
            "rule_based_state": "neutral",
            "vote_based_state": "neutral",
            "evaluate_date": "2026-05-05",
            "source": "scheduled",
            "reason": "range",
            "total_score": 0.0,
            "score_based_total": 0.0,
        }
    ]
```

```python
def test_latest_snapshot_contains_daily_and_intervals(tmp_path: Path) -> None:
    daily_records = [
        {
            "pick_date": "2026-05-05",
            "state": "neutral",
            "score_based_state": "neutral",
            "rule_based_state": "neutral",
            "vote_based_state": "neutral",
            "evaluate_date": "2026-05-05",
            "source": "scheduled",
            "reason": "range",
            "total_score": 0.0,
            "score_based_total": 0.0,
        }
    ]

    write_environment_history(tmp_path, daily_records)

    latest = json.loads((tmp_path / "environment" / "latest.json").read_text(encoding="utf-8"))
    assert "daily" in latest
    assert "intervals" in latest
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_market_environment.py -k "daily_files or daily_jsonl or latest_snapshot" -v`
Expected: FAIL because the implementation still treats persisted records as intervals.

- [ ] **Step 3: Implement the minimal storage helpers**

In `src/stock_select/market_environment.py`, add helpers shaped like:

```python
def _daily_dir(runtime_root: Path) -> Path:
    return _environment_dir(runtime_root) / "daily"


def _daily_record_filename(record: dict[str, object]) -> str:
    return f\"{record['pick_date']}.{record['state']}.json\"
```

and update `write_environment_history(...)` / `load_environment_history(...)` to work on daily records.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_market_environment.py -k "daily_files or daily_jsonl or latest_snapshot" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_market_environment.py src/stock_select/market_environment.py
git commit -m "refactor: persist market environment daily files"
```

### Task 2: Rebuild Interval Resolution From Daily Records

**Files:**
- Modify: `tests/test_market_environment.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_market_environment.py`

- [ ] **Step 1: Write the failing regression tests**

Add tests that assert:

```python
def test_resolve_market_environment_builds_interval_from_consecutive_daily_records(tmp_path: Path) -> None:
    write_environment_history(
        tmp_path,
        [
            {
                "pick_date": "2026-05-12",
                "state": "strong",
                "score_based_state": "strong",
                "rule_based_state": "strong",
                "vote_based_state": "strong",
                "evaluate_date": "2026-05-12",
                "source": "scheduled",
                "reason": "day 1",
                "total_score": 11.0,
                "score_based_total": 11.0,
            },
            {
                "pick_date": "2026-05-13",
                "state": "strong",
                "score_based_state": "strong",
                "rule_based_state": "strong",
                "vote_based_state": "strong",
                "evaluate_date": "2026-05-13",
                "source": "scheduled",
                "reason": "day 2",
                "total_score": 12.0,
                "score_based_total": 12.0,
            },
        ],
    )

    resolved = resolve_market_environment(tmp_path, pick_date="2026-05-13")
    assert resolved["state"] == "strong"
    assert resolved["interval_start"] == "2026-05-12"
    assert resolved["interval_end"] == "2026-05-13"
```

```python
def test_override_market_environment_replaces_same_day_daily_file(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_market_environment.py -k "consecutive_daily_records or same_day_daily_file" -v`
Expected: FAIL until interval compaction is rebuilt from daily records.

- [ ] **Step 3: Implement daily-to-interval compaction**

Add a helper in `src/stock_select/market_environment.py` shaped like:

```python
def _build_intervals_from_daily_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    ...
```

Use it from both `resolve_market_environment(...)` and `latest.json` snapshot generation.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_market_environment.py -k "consecutive_daily_records or same_day_daily_file" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_market_environment.py src/stock_select/market_environment.py
git commit -m "refactor: derive market environment intervals from daily records"
```

### Task 3: Update Mutation Paths To Rewrite Daily/JSONL/Snapshot Together

**Files:**
- Modify: `tests/test_market_environment.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_market_environment.py`

- [ ] **Step 1: Write the failing mutation tests**

Add tests that assert:

```python
def test_ensure_market_environment_writes_daily_file_and_jsonl(tmp_path: Path) -> None:
    ...
```

```python
def test_override_market_environment_rebuilds_latest_daily_and_intervals(tmp_path: Path) -> None:
    ...
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_market_environment.py -k "writes_daily_file_and_jsonl or rebuilds_latest_daily_and_intervals" -v`
Expected: FAIL until `ensure_market_environment(...)` and `override_market_environment(...)` use the new persistence entrypoint.

- [ ] **Step 3: Route all mutation paths through one daily-record writer**

Keep a single writer in `src/stock_select/market_environment.py` that:

- removes stale same-day daily files
- rewrites the `daily/` directory entries it owns
- rewrites `history.jsonl`
- rewrites `latest.json`

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_market_environment.py -k "writes_daily_file_and_jsonl or rebuilds_latest_daily_and_intervals" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_market_environment.py src/stock_select/market_environment.py
git commit -m "test: cover daily market environment persistence mutations"
```

### Task 4: Update CLI And Rebuild Script To Produce Daily Files

**Files:**
- Modify: `src/stock_select/cli.py`
- Modify: `scripts/review_tuning_backfill_environment_history.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_review_tuning_backfill_environment_history.py`
- Modify: `src/stock_select/market_environment.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_review_tuning_backfill_environment_history.py`

- [ ] **Step 1: Write the failing CLI and script tests**

Add tests that assert:

```python
assert (tmp_path / "environment" / "daily" / "2026-04-01.weak.json").exists()
assert (tmp_path / "environment" / "history.jsonl").exists()
assert (tmp_path / "environment" / "latest.json").exists()
```

for both `market-env rebuild --artifact-dir ... --overwrite` and `review_tuning_backfill_environment_history.py`.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "market_env_rebuild or market_env_history_prints_intervals" -v`
Run: `uv run pytest tests/test_review_tuning_backfill_environment_history.py -v`
Expected: FAIL until rebuild writes daily files and latest snapshot structure changes.

- [ ] **Step 3: Implement CLI/script integration**

Update:

- `market-env history` to emit the new `latest.json`
- `market-env rebuild` to regenerate daily files plus aggregate files
- `scripts/review_tuning_backfill_environment_history.py` to reuse the same rebuild helper

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k "market_env_rebuild or market_env_history_prints_intervals" -v`
Run: `uv run pytest tests/test_review_tuning_backfill_environment_history.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_select/cli.py scripts/review_tuning_backfill_environment_history.py src/stock_select/market_environment.py tests/test_cli.py tests/test_review_tuning_backfill_environment_history.py
git commit -m "feat: rebuild market environment daily files from artifacts"
```

### Task 5: Update Documentation And Run Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-08-market-env-history-storage-design.md`
- Modify: `docs/superpowers/plans/2026-05-08-market-env-history-storage.md`
- Modify: `src/stock_select/market_environment.py`
- Modify: `src/stock_select/cli.py`
- Modify: `scripts/review_tuning_backfill_environment_history.py`
- Modify: `tests/test_market_environment.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_review_tuning_backfill_environment_history.py`

- [ ] **Step 1: Update README examples and storage explanation**

Document:

- `daily/YYYY-MM-DD.<state>.json`
- `history.jsonl`
- `latest.json`
- `market-env rebuild --artifact-dir ... --overwrite`

- [ ] **Step 2: Run targeted market environment tests**

Run: `uv run pytest tests/test_market_environment.py -v`
Expected: PASS

- [ ] **Step 3: Run targeted CLI and script tests**

Run: `uv run pytest tests/test_cli.py -k "market_env or screen_calls_ensure_market_environment_before_fetch" -v`
Run: `uv run pytest tests/test_review_tuning_backfill_environment_history.py -v`
Expected: PASS

- [ ] **Step 4: Run CLI smoke checks**

Run:

```bash
uv run stock-select market-env --help
uv run stock-select market-env rebuild --help
```

Expected: both commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-05-08-market-env-history-storage-design.md docs/superpowers/plans/2026-05-08-market-env-history-storage.md src/stock_select/market_environment.py src/stock_select/cli.py scripts/review_tuning_backfill_environment_history.py tests/test_market_environment.py tests/test_cli.py tests/test_review_tuning_backfill_environment_history.py
git commit -m "docs: document market environment daily storage workflow"
```
