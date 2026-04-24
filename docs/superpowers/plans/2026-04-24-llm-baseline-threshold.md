# LLM Baseline Threshold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional baseline-score threshold that filters `llm_review_tasks.json` without changing baseline review artifacts or summaries.

**Architecture:** Keep the dispatch policy inside `src/stock_select/cli.py`, where review artifacts and task payloads are already written. Thread an optional `llm_min_baseline_score` from `review` and `run` into the end-of-day and intraday review implementations, and gate only the append to `llm_review_tasks`.

**Tech Stack:** Python, Typer CLI, pandas, pytest

---

## File Structure

- Modify: `src/stock_select/cli.py`
  - add `_validate_llm_min_baseline_score(...)`
  - add `_should_include_llm_review_task(...)`
  - thread `llm_min_baseline_score` through `review`, `run_all`, `_review_impl`, and `_review_intraday_impl`
  - apply the threshold immediately before appending to `llm_review_tasks`
- Modify: `tests/test_cli.py`
  - add end-of-day threshold filtering coverage
  - add intraday threshold filtering coverage
  - add run command forwarding coverage
  - add CLI rejection coverage for negative threshold

No new module is needed because the behavior is a CLI review dispatch policy, not a reusable domain rule.

### Task 1: Add End-Of-Day Review Threshold Behavior

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing end-of-day test**

Add this test near the existing `test_review_uses_method_specific_resolver_prompt_and_baseline(...)` test in `tests/test_cli.py`:

```python
def test_review_filters_llm_tasks_by_min_baseline_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    method_key = _eod_key("2026-04-01", "b2")
    review_dir = runtime_root / "reviews" / method_key
    candidate_path = runtime_root / "candidates" / f"{method_key}.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "b2",
                "candidates": [{"code": "000001.SZ"}, {"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (chart_dir / "000002.SZ_day.png").write_bytes(b"png")

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda connection, *, symbol, start_date, end_date: pd.DataFrame(
            {
                "ts_code": [symbol, symbol, symbol],
                "trade_date": pd.to_datetime(["2026-03-28", "2026-03-31", "2026-04-01"]),
                "open": [10.0, 10.2, 10.4],
                "high": [10.3, 10.6, 10.9],
                "low": [9.9, 10.1, 10.3],
                "close": [10.2, 10.5, 10.8],
                "vol": [100.0, 120.0, 150.0],
            }
        ),
    )

    baseline_scores = {"000001.SZ": 4.2, "000002.SZ": 3.9}

    def fake_review_history(
        *,
        code: str,
        pick_date: str,
        history: pd.DataFrame,
        chart_path: str,
    ) -> dict[str, object]:
        score = baseline_scores[code]
        return {
            "review_type": "baseline",
            "total_score": score,
            "signal_type": "trend_start" if score >= 4.0 else "rebound",
            "verdict": "PASS" if score >= 4.0 else "WATCH",
            "comment": f"{code} baseline",
        }

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: SimpleNamespace(
            name="b2",
            prompt_path=str(tmp_path / "prompt-b2-stub.md"),
            review_history=fake_review_history,
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b2",
            "--pick-date",
            "2026-04-01",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--llm-min-baseline-score",
            "4.0",
        ],
    )

    assert result.exit_code == 0
    high_review = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    low_review = json.loads((review_dir / "000002.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))

    assert high_review["total_score"] == 4.2
    assert low_review["total_score"] == 3.9
    assert summary["reviewed_count"] == 2
    assert [task["code"] for task in tasks["tasks"]] == ["000001.SZ"]
    assert tasks["tasks"][0]["baseline_score"] == 4.2
    assert "llm_tasks=1" in result.stderr
    assert "skipped_by_baseline_score=1" in result.stderr
```

- [ ] **Step 2: Run the failing end-of-day test**

Run:

```bash
uv run pytest tests/test_cli.py::test_review_filters_llm_tasks_by_min_baseline_score -q
```

Expected: FAIL because `review` does not accept `--llm-min-baseline-score`.

- [ ] **Step 3: Add validation and helper functions**

In `src/stock_select/cli.py`, add these helpers near the existing CLI validation helpers:

```python
def _validate_llm_min_baseline_score(value: float | None) -> float | None:
    if value is None:
        return None
    if value < 0.0:
        raise typer.BadParameter("--llm-min-baseline-score must be non-negative.")
    return float(value)


def _should_include_llm_review_task(review: dict[str, object], threshold: float | None) -> bool:
    if threshold is None:
        return True
    return float(review["total_score"]) >= threshold
```

- [ ] **Step 4: Thread the option into end-of-day review**

Update `_review_impl(...)` signature in `src/stock_select/cli.py`:

```python
def _review_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    llm_min_baseline_score: float | None = None,
    reporter: ProgressReporter | None = None,
) -> Path:
```

Inside `_review_impl(...)`, add a counter before the candidate loop:

```python
    skipped_by_baseline_score = 0
```

Replace the unconditional `llm_review_tasks.append(...)` with:

```python
        if _should_include_llm_review_task(review, llm_min_baseline_score):
            llm_review_tasks.append(
                {
                    **task,
                    "rank": idx,
                    "baseline_score": review["total_score"],
                    "baseline_verdict": review["verdict"],
                }
            )
        else:
            skipped_by_baseline_score += 1
```

Update the final progress line in `_review_impl(...)`:

```python
        reporter.emit(
            "review",
            (
                f"done reviewed={len(reviews)} failures={len(failures)} "
                f"llm_tasks={len(llm_review_tasks)} skipped_by_baseline_score={skipped_by_baseline_score} "
                f"write={summary_path}"
            ),
        )
```

Update the `review(...)` command options and call:

```python
    llm_min_baseline_score: float | None = typer.Option(None, "--llm-min-baseline-score"),
```

```python
    normalized_llm_min_baseline_score = _validate_llm_min_baseline_score(llm_min_baseline_score)
```

Pass the value to `_review_impl(...)`:

```python
            llm_min_baseline_score=normalized_llm_min_baseline_score,
```

- [ ] **Step 5: Run the end-of-day test to verify it passes**

Run:

```bash
uv run pytest tests/test_cli.py::test_review_filters_llm_tasks_by_min_baseline_score -q
```

Expected: PASS

### Task 2: Add Intraday Review Threshold Behavior

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing intraday test**

Add this test near `test_review_intraday_uses_method_specific_resolver_prompt_and_baseline(...)` in `tests/test_cli.py`:

```python
def test_review_intraday_filters_llm_tasks_by_min_baseline_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    run_id = "2026-04-09T11-31-08+08-00"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / _intraday_key(run_id, "b2")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (chart_dir / "000002.SZ_day.png").write_bytes(b"png")
    (candidate_dir / f"{_intraday_key(run_id, 'b2')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b2",
                "trade_date": "2026-04-09",
                "run_id": run_id,
                "candidates": [{"code": "000001.SZ"}, {"code": "000002.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "_load_intraday_prepared_cache",
        lambda current_runtime_root, *, method, run_id, trade_date: {
            "000001.SZ": pd.DataFrame(
                [
                    {"trade_date": "2026-04-08", "open": 11.9, "high": 12.1, "low": 11.8, "close": 12.0, "vol": 120.0},
                    {"trade_date": "2026-04-09", "open": 12.1, "high": 12.5, "low": 12.0, "close": 12.34, "vol": 150.0},
                ]
            ),
            "000002.SZ": pd.DataFrame(
                [
                    {"trade_date": "2026-04-08", "open": 21.9, "high": 22.1, "low": 21.8, "close": 22.0, "vol": 220.0},
                    {"trade_date": "2026-04-09", "open": 22.1, "high": 22.5, "low": 22.0, "close": 22.34, "vol": 250.0},
                ]
            ),
        },
    )

    baseline_scores = {"000001.SZ": 4.1, "000002.SZ": 3.8}

    def fake_review_history(
        *,
        code: str,
        pick_date: str,
        history: pd.DataFrame,
        chart_path: str,
    ) -> dict[str, object]:
        score = baseline_scores[code]
        return {
            "review_type": "baseline",
            "total_score": score,
            "signal_type": "trend_start" if score >= 4.0 else "rebound",
            "verdict": "PASS" if score >= 4.0 else "WATCH",
            "comment": f"{code} intraday baseline",
        }

    monkeypatch.setattr(
        cli,
        "get_review_resolver",
        lambda method: SimpleNamespace(
            name="b2",
            prompt_path=str(tmp_path / "prompt-b2-stub.md"),
            review_history=fake_review_history,
        ),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b2",
            "--intraday",
            "--runtime-root",
            str(runtime_root),
            "--llm-min-baseline-score",
            "4.0",
        ],
    )

    assert result.exit_code == 0
    review_dir = runtime_root / "reviews" / _intraday_key(run_id, "b2")
    high_review = json.loads((review_dir / "000001.SZ.json").read_text(encoding="utf-8"))
    low_review = json.loads((review_dir / "000002.SZ.json").read_text(encoding="utf-8"))
    summary = json.loads((review_dir / "summary.json").read_text(encoding="utf-8"))
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))

    assert high_review["total_score"] == 4.1
    assert low_review["total_score"] == 3.8
    assert summary["reviewed_count"] == 2
    assert [task["code"] for task in tasks["tasks"]] == ["000001.SZ"]
    assert tasks["tasks"][0]["baseline_score"] == 4.1
    assert "llm_tasks=1" in result.stderr
    assert "skipped_by_baseline_score=1" in result.stderr
```

- [ ] **Step 2: Run the failing intraday test**

Run:

```bash
uv run pytest tests/test_cli.py::test_review_intraday_filters_llm_tasks_by_min_baseline_score -q
```

Expected: FAIL because `_review_intraday_impl(...)` does not accept or apply the threshold.

- [ ] **Step 3: Thread the option into intraday review**

Update `_review_intraday_impl(...)` signature:

```python
def _review_intraday_impl(
    *,
    method: str,
    runtime_root: Path,
    llm_min_baseline_score: float | None = None,
    reporter: ProgressReporter | None = None,
) -> Path:
```

Inside `_review_intraday_impl(...)`, add before the candidate loop:

```python
    skipped_by_baseline_score = 0
```

Replace the unconditional `llm_review_tasks.append(...)` with the same gated block used in `_review_impl(...)`:

```python
        if _should_include_llm_review_task(review, llm_min_baseline_score):
            llm_review_tasks.append(
                {
                    **task,
                    "rank": idx,
                    "baseline_score": review["total_score"],
                    "baseline_verdict": review["verdict"],
                }
            )
        else:
            skipped_by_baseline_score += 1
```

Update the final progress line in `_review_intraday_impl(...)`:

```python
        reporter.emit(
            "review",
            (
                f"done reviewed={len(reviews)} failures={len(failures)} "
                f"llm_tasks={len(llm_review_tasks)} skipped_by_baseline_score={skipped_by_baseline_score} "
                f"write={summary_path}"
            ),
        )
```

Pass `normalized_llm_min_baseline_score` into `_review_intraday_impl(...)` from the `review(...)` command:

```python
            llm_min_baseline_score=normalized_llm_min_baseline_score,
```

- [ ] **Step 4: Run the intraday test to verify it passes**

Run:

```bash
uv run pytest tests/test_cli.py::test_review_intraday_filters_llm_tasks_by_min_baseline_score -q
```

Expected: PASS

### Task 3: Add Run Forwarding And Threshold Validation

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing run forwarding test**

Add this test near `test_run_accepts_pool_source_and_passes_it_to_screen_step(...)`:

```python
def test_run_passes_llm_min_baseline_score_to_review_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    calls: list[tuple[str, object | None]] = []

    monkeypatch.setattr(
        cli,
        "_screen_impl",
        lambda **kwargs: runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json",
    )
    monkeypatch.setattr(
        cli,
        "_chart_impl",
        lambda **kwargs: runtime_root / "charts" / _eod_key("2026-04-01"),
    )

    def fake_review_impl(
        *,
        method: str,
        pick_date: str,
        dsn: str | None,
        runtime_root: Path,
        llm_min_baseline_score: float | None = None,
        reporter: object | None = None,
    ) -> Path:
        calls.append(("review", llm_min_baseline_score))
        return runtime_root / "reviews" / _eod_key("2026-04-01") / "summary.json"

    monkeypatch.setattr(cli, "_review_impl", fake_review_impl)

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--dsn",
            "postgresql://example",
            "--runtime-root",
            str(runtime_root),
            "--llm-min-baseline-score",
            "4.0",
        ],
    )

    assert result.exit_code == 0
    assert calls == [("review", 4.0)]
```

- [ ] **Step 2: Write the failing negative-threshold CLI test**

Add this test near CLI validation tests:

```python
def test_review_rejects_negative_llm_min_baseline_score(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "review",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--runtime-root",
            str(tmp_path),
            "--llm-min-baseline-score",
            "-0.1",
        ],
    )

    assert result.exit_code != 0
    assert "llm-min-baseline-score must be non-negative" in result.stderr.lower()
```

- [ ] **Step 3: Run both tests to verify they fail**

Run:

```bash
uv run pytest tests/test_cli.py::test_run_passes_llm_min_baseline_score_to_review_step tests/test_cli.py::test_review_rejects_negative_llm_min_baseline_score -q
```

Expected: FAIL because `run` does not accept the option yet.

- [ ] **Step 4: Thread the option through `run_all(...)`**

Add the option to `run_all(...)`:

```python
    llm_min_baseline_score: float | None = typer.Option(None, "--llm-min-baseline-score"),
```

Add validation after pool-source validation:

```python
    normalized_llm_min_baseline_score = _validate_llm_min_baseline_score(llm_min_baseline_score)
```

Pass it to `_review_intraday_impl(...)`:

```python
            llm_min_baseline_score=normalized_llm_min_baseline_score,
```

Pass it to `_review_impl(...)`:

```python
            llm_min_baseline_score=normalized_llm_min_baseline_score,
```

- [ ] **Step 5: Run the run forwarding and validation tests**

Run:

```bash
uv run pytest tests/test_cli.py::test_run_passes_llm_min_baseline_score_to_review_step tests/test_cli.py::test_review_rejects_negative_llm_min_baseline_score -q
```

Expected: PASS

### Task 4: Verify Compatibility And Focused Regression Set

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Run existing compatibility tests that should still pass**

Run:

```bash
uv run pytest \
  tests/test_cli.py::test_review_writes_baseline_reviews_and_llm_tasks \
  tests/test_cli.py::test_review_uses_method_specific_resolver_prompt_and_baseline \
  tests/test_cli.py::test_review_intraday_uses_method_specific_resolver_prompt_and_baseline \
  tests/test_cli.py::test_run_accepts_pool_source_and_passes_it_to_screen_step \
  -q
```

Expected: PASS. These tests prove omitted `--llm-min-baseline-score` still includes all successfully baseline-reviewed candidates and run still preserves existing pool-source forwarding.

- [ ] **Step 2: Run the new threshold tests together**

Run:

```bash
uv run pytest \
  tests/test_cli.py::test_review_filters_llm_tasks_by_min_baseline_score \
  tests/test_cli.py::test_review_intraday_filters_llm_tasks_by_min_baseline_score \
  tests/test_cli.py::test_run_passes_llm_min_baseline_score_to_review_step \
  tests/test_cli.py::test_review_rejects_negative_llm_min_baseline_score \
  -q
```

Expected: PASS

- [ ] **Step 3: Run the full CLI test module**

Run:

```bash
uv run pytest tests/test_cli.py -q
```

Expected: PASS

- [ ] **Step 4: Inspect the final diff**

Run:

```bash
git diff -- src/stock_select/cli.py tests/test_cli.py
```

Expected: Diff only adds the CLI option, threshold helper, gated task append logic, progress counts, and tests.

- [ ] **Step 5: Commit the implementation**

Run:

```bash
git add src/stock_select/cli.py tests/test_cli.py
git commit -m "feat: filter llm review tasks by baseline score"
```

Expected: Commit succeeds.

## Self-Review

Spec coverage:

- `review` option is covered by Task 1 and Task 3.
- `run` forwarding is covered by Task 3.
- End-of-day and intraday behavior are covered by Task 1 and Task 2.
- Baseline artifacts and summaries staying unchanged are asserted in Task 1 and Task 2.
- `llm_review_tasks.json` filtering is asserted in Task 1 and Task 2.
- Negative threshold rejection is asserted in Task 3.
- Default compatibility is covered in Task 4.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or unspecified code steps remain.

Type consistency:

- The option is consistently named `llm_min_baseline_score`.
- The CLI flag is consistently named `--llm-min-baseline-score`.
- The helper receives `dict[str, object]` and `float | None`, matching review dict usage in `cli.py`.
