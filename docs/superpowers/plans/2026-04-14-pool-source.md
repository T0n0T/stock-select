# Pool Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--pool-source turnover-top|record-watch` to `screen` and `run`, so `b1`, `b2`, and `hcr` can all screen against either the existing top-turnover pool or the per-method recorded watch pool.

**Architecture:** Keep CLI parsing and orchestration in `src/stock_select/cli.py`, but move watch-pool screening selection into focused helpers in `src/stock_select/watch_pool.py`. Introduce a single pool-resolution layer used by end-of-day and intraday screening so `b1`, `b2`, and `hcr` all share the same pool-source contract while `b2` preserves its two-phase warmup flow.

**Tech Stack:** Python 3, Typer CLI, pandas, pytest

---

## File Structure

- Modify: `src/stock_select/cli.py`
  - add CLI option parsing for `--pool-source`
  - add pool-source validation and shared resolution helpers
  - thread pool-source through `screen`, `run`, end-of-day screen, and intraday screen
  - apply resolved pool subsets to `b1`, `b2`, and `hcr`
- Modify: `src/stock_select/watch_pool.py`
  - add helpers that derive effective screening symbols from `watch_pool/<method>.csv`
  - keep CSV-specific row filtering out of the CLI body
- Modify: `tests/test_cli.py`
  - add CLI contract tests for `screen` and `run`
  - add `record-watch` pool behavior tests for `b1`, `b2`, and `hcr`
  - add `hcr` top-turnover pool regression coverage
- Optional modify: `README.md`
  - document the new `--pool-source` option on `screen` and `run` if the implementation updates command examples in the same change

### Task 1: Add failing CLI contract tests for `--pool-source`

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_screen_accepts_pool_source_and_passes_it_to_screen_impl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    expected_path = runtime_root / "candidates" / f"{_eod_key('2026-04-10', 'b2')}.json"

    def fake_screen_impl(**kwargs: object) -> Path:
        assert kwargs["method"] == "b2"
        assert kwargs["pick_date"] == "2026-04-10"
        assert kwargs["pool_source"] == "record-watch"
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        expected_path.write_text(json.dumps({"pick_date": "2026-04-10", "method": "b2", "candidates": []}), encoding="utf-8")
        return expected_path

    monkeypatch.setattr(cli, "_screen_impl", fake_screen_impl, raising=False)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b2",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected_path)


def test_run_accepts_pool_source_and_passes_it_to_screen_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    calls: list[tuple[str, str]] = []

    def fake_screen_impl(**kwargs: object) -> Path:
        calls.append(("screen", str(kwargs["pool_source"])))
        path = runtime_root / "candidates" / f"{_eod_key('2026-04-01')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"pick_date": "2026-04-01", "method": "b1", "candidates": [{"code": "000001.SZ"}]}), encoding="utf-8")
        return path

    def fake_chart_impl(**kwargs: object) -> Path:
        path = runtime_root / "charts" / _eod_key("2026-04-01")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def fake_review_impl(**kwargs: object) -> Path:
        path = runtime_root / "reviews" / _eod_key("2026-04-01") / "summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"pick_date": "2026-04-01", "method": "b1", "recommendations": [], "excluded": []}), encoding="utf-8")
        return path

    monkeypatch.setattr(cli, "_screen_impl", fake_screen_impl, raising=False)
    monkeypatch.setattr(cli, "_chart_impl", fake_chart_impl, raising=False)
    monkeypatch.setattr(cli, "_review_impl", fake_review_impl, raising=False)

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-01",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert calls == [("screen", "record-watch")]


def test_run_intraday_accepts_pool_source_and_passes_it_to_intraday_screen_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    calls: list[tuple[str, str]] = []

    def fake_screen_intraday_impl(**kwargs: object) -> Path:
        calls.append(("screen-intraday", str(kwargs["pool_source"])))
        path = runtime_root / "candidates" / f"{_intraday_key('2026-04-09T11-31-08-123456+08-00')}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"method": "b1", "trade_date": "2026-04-09", "candidates": []}), encoding="utf-8")
        return path

    monkeypatch.setattr(cli, "_screen_intraday_impl", fake_screen_intraday_impl, raising=False)
    monkeypatch.setattr(cli, "_chart_intraday_impl", lambda **kwargs: runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08-123456+08-00"), raising=False)
    monkeypatch.setattr(cli, "_review_intraday_impl", lambda **kwargs: runtime_root / "reviews" / _intraday_key("2026-04-09T11-31-08-123456+08-00") / "summary.json", raising=False)

    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "b1",
            "--intraday",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
            "--tushare-token",
            "token",
        ],
    )

    assert result.exit_code == 0
    assert calls == [("screen-intraday", "record-watch")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_screen_accepts_pool_source_and_passes_it_to_screen_impl tests/test_cli.py::test_run_accepts_pool_source_and_passes_it_to_screen_step tests/test_cli.py::test_run_intraday_accepts_pool_source_and_passes_it_to_intraday_screen_step -v`
Expected: FAIL because `screen`, `run`, and intraday `run` do not yet accept or forward `--pool-source`.

- [ ] **Step 3: Write minimal implementation**

```python
def _validate_pool_source(pool_source: str) -> str:
    normalized = str(pool_source).strip().lower()
    if normalized not in {"turnover-top", "record-watch"}:
        raise typer.BadParameter(f"Unsupported pool source: {pool_source}")
    return normalized


def _screen_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    pool_source: str = "turnover-top",
    recompute: bool = False,
    reporter: ProgressReporter | None = None,
) -> Path:
    ...


def _screen_intraday_impl(
    *,
    method: str,
    dsn: str | None,
    tushare_token: str | None,
    runtime_root: Path,
    pool_source: str = "turnover-top",
    reporter: ProgressReporter | None = None,
) -> Path:
    ...


@app.command()
def screen(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    pool_source: str = typer.Option("turnover-top", "--pool-source"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    normalized_pool_source = _validate_pool_source(pool_source)
    ...
    out_path = _screen_impl(
        method=normalized_method,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        pool_source=normalized_pool_source,
        recompute=recompute,
        reporter=reporter,
    )


@app.command(name="run")
def run_all(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    pool_source: str = typer.Option("turnover-top", "--pool-source"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    normalized_method = _validate_cli_method(method)
    normalized_pool_source = _validate_pool_source(pool_source)
    ...
    screen_path = _screen_impl(
        method=normalized_method,
        pick_date=pick_date,
        dsn=dsn,
        runtime_root=runtime_root,
        pool_source=normalized_pool_source,
        recompute=recompute,
        reporter=reporter,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_screen_accepts_pool_source_and_passes_it_to_screen_impl tests/test_cli.py::test_run_accepts_pool_source_and_passes_it_to_screen_step tests/test_cli.py::test_run_intraday_accepts_pool_source_and_passes_it_to_intraday_screen_step -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/stock_select/cli.py
git commit -m "feat: add pool-source cli option"
```

### Task 2: Add watch-pool symbol resolution helpers with failing tests

**Files:**
- Modify: `src/stock_select/watch_pool.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_screen_record_watch_uses_latest_effective_rows_per_symbol(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    watch_dir = runtime_root / "watch_pool"
    watch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"method": "b1", "pick_date": "2026-04-01", "code": "AAA.SZ", "verdict": "WATCH", "total_score": 5.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-11T09:00:00+08:00"},
            {"method": "b1", "pick_date": "2026-04-10", "code": "AAA.SZ", "verdict": "PASS", "total_score": 6.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-11T09:01:00+08:00"},
            {"method": "b1", "pick_date": "2026-04-09", "code": "BBB.SZ", "verdict": "WATCH", "total_score": 4.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-11T09:02:00+08:00"},
            {"method": "b1", "pick_date": "2026-04-12", "code": "CCC.SZ", "verdict": "WATCH", "total_score": 4.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-12T09:02:00+08:00"},
        ]
    ).to_csv(watch_dir / "b1.csv", index=False)

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ", "BBB.SZ", "CCC.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10", "2026-04-10", "2026-04-10"]),
                "open": [10.0, 11.0, 12.0],
                "high": [10.5, 11.5, 12.5],
                "low": [9.8, 10.8, 11.8],
                "close": [10.4, 11.4, 12.4],
                "vol": [100.0, 110.0, 120.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_screen_data",
        lambda market: {
            code: pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [idx + 10.0],
                    "J": [10.0],
                    "zxdq": [idx + 10.5],
                    "zxdkx": [idx + 10.2],
                    "weekly_ma_bull": [True],
                    "max_vol_not_bearish": [True],
                    "turnover_n": [100.0 + idx],
                }
            )
            for idx, code in enumerate(["AAA.SZ", "BBB.SZ", "CCC.SZ"], start=1)
        },
        raising=False,
    )

    seen_codes: list[str] = []

    def fake_run_b1_screen_with_stats(prepared_by_symbol, pick_date, config):
        seen_codes.extend(sorted(prepared_by_symbol))
        return ([], {"total_symbols": len(prepared_by_symbol), "eligible": 0, "fail_j": 0, "fail_insufficient_history": 0, "fail_close_zxdkx": 0, "fail_zxdq_zxdkx": 0, "fail_weekly_ma": 0, "fail_max_vol": 0, "selected": 0})

    monkeypatch.setattr(cli, "run_b1_screen_with_stats", fake_run_b1_screen_with_stats)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert seen_codes == ["AAA.SZ", "BBB.SZ"]


def test_screen_record_watch_rejects_missing_watch_pool_csv(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b1",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "watch pool" in result.stderr.lower()
    assert "b1.csv" in result.stderr


def test_screen_record_watch_rejects_empty_effective_pool_after_intersection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    watch_dir = runtime_root / "watch_pool"
    watch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"method": "hcr", "pick_date": "2026-04-09", "code": "ZZZ.SZ", "verdict": "WATCH", "total_score": 4.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-11T09:00:00+08:00"}
        ]
    ).to_csv(watch_dir / "hcr.csv", index=False)

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_resolve_hcr_start_date", lambda connection, *, end_date, trading_days: "2025-04-29", raising=False)
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10"]),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.4],
                "vol": [100.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "AAA.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-10"]),
                    "close": [10.4],
                    "yx": [10.0],
                    "p": [10.1],
                    "resonance_gap_pct": [0.01],
                    "turnover_n": [1000.0],
                }
            )
        },
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code != 0
    assert "no effective symbols" in result.stderr.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_screen_record_watch_uses_latest_effective_rows_per_symbol tests/test_cli.py::test_screen_record_watch_rejects_missing_watch_pool_csv tests/test_cli.py::test_screen_record_watch_rejects_empty_effective_pool_after_intersection -v`
Expected: FAIL because there is no screening-time watch-pool resolver yet.

- [ ] **Step 3: Write minimal implementation**

```python
def select_effective_watch_pool_codes(
    rows: pd.DataFrame,
    *,
    pick_date: str,
) -> list[str]:
    if rows.empty:
        return []

    frame = rows.copy()
    frame["pick_date"] = frame["pick_date"].astype(str)
    frame = frame[frame["pick_date"] <= pick_date].copy()
    if frame.empty:
        return []

    frame["_row_order"] = range(len(frame))
    frame = frame.sort_values(
        by=["code", "pick_date", "_row_order"],
        ascending=[True, False, False],
        kind="stable",
    )
    latest = frame.drop_duplicates(subset=["code"], keep="first")
    return latest["code"].astype(str).tolist()


def _resolve_record_watch_pool_codes(
    *,
    method: str,
    pick_date: str,
    runtime_root: Path,
    prepared_by_symbol: Mapping[str, pd.DataFrame],
) -> list[str]:
    csv_path = _watch_pool_path(runtime_root, method)
    if not csv_path.exists():
        raise typer.BadParameter(f"Watch pool file not found: {csv_path}")
    watch_rows = load_watch_pool(csv_path)
    effective_codes = select_effective_watch_pool_codes(watch_rows, pick_date=pick_date)
    prepared_codes = {str(code) for code in prepared_by_symbol}
    resolved_codes = [code for code in effective_codes if code in prepared_codes]
    if not resolved_codes:
        raise typer.BadParameter(
            f"Watch pool has no effective symbols for method={method} pick_date={pick_date}: {csv_path}"
        )
    return resolved_codes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_screen_record_watch_uses_latest_effective_rows_per_symbol tests/test_cli.py::test_screen_record_watch_rejects_missing_watch_pool_csv tests/test_cli.py::test_screen_record_watch_rejects_empty_effective_pool_after_intersection -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/stock_select/watch_pool.py src/stock_select/cli.py
git commit -m "feat: resolve record-watch screening pool"
```

### Task 3: Add shared pool-resolution flow for `b1`, `b2`, and `hcr`

**Files:**
- Modify: `src/stock_select/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_screen_hcr_turnover_top_uses_liquidity_pool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_resolve_hcr_start_date", lambda connection, *, end_date, trading_days: "2025-04-29", raising=False)
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ", "BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10", "2026-04-10"]),
                "open": [10.0, 20.0],
                "high": [10.5, 20.5],
                "low": [9.8, 19.8],
                "close": [10.4, 20.4],
                "vol": [100.0, 200.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "AAA.SZ": pd.DataFrame({"trade_date": pd.to_datetime(["2026-04-10"]), "close": [10.4], "yx": [10.0], "p": [10.1], "resonance_gap_pct": [0.01], "turnover_n": [100.0]}),
            "BBB.SZ": pd.DataFrame({"trade_date": pd.to_datetime(["2026-04-10"]), "close": [20.4], "yx": [20.0], "p": [20.1], "resonance_gap_pct": [0.01], "turnover_n": [200.0]}),
        },
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "build_top_turnover_pool",
        lambda prepared_by_symbol, *, top_m: {pd.Timestamp("2026-04-10"): ["BBB.SZ"]},
    )

    seen_codes: list[str] = []

    def fake_run_hcr_screen_with_stats(prepared_by_symbol, pick_date):
        seen_codes.extend(sorted(prepared_by_symbol))
        return ([], {"total_symbols": len(prepared_by_symbol), "eligible": 0, "fail_insufficient_history": 0, "fail_resonance": 0, "fail_close_floor": 0, "fail_breakout": 0, "selected": 0})

    monkeypatch.setattr(cli, "run_hcr_screen_with_stats", fake_run_hcr_screen_with_stats, raising=False)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "turnover-top",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert seen_codes == ["BBB.SZ"]


def test_screen_hcr_record_watch_uses_watch_pool_subset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    watch_dir = runtime_root / "watch_pool"
    watch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"method": "hcr", "pick_date": "2026-04-09", "code": "AAA.SZ", "verdict": "WATCH", "total_score": 4.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-11T09:00:00+08:00"}
        ]
    ).to_csv(watch_dir / "hcr.csv", index=False)

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_resolve_hcr_start_date", lambda connection, *, end_date, trading_days: "2025-04-29", raising=False)
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ", "BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-10", "2026-04-10"]),
                "open": [10.0, 20.0],
                "high": [10.5, 20.5],
                "low": [9.8, 19.8],
                "close": [10.4, 20.4],
                "vol": [100.0, 200.0],
            }
        ),
    )
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "AAA.SZ": pd.DataFrame({"trade_date": pd.to_datetime(["2026-04-10"]), "close": [10.4], "yx": [10.0], "p": [10.1], "resonance_gap_pct": [0.01], "turnover_n": [100.0]}),
            "BBB.SZ": pd.DataFrame({"trade_date": pd.to_datetime(["2026-04-10"]), "close": [20.4], "yx": [20.0], "p": [20.1], "resonance_gap_pct": [0.01], "turnover_n": [200.0]}),
        },
        raising=False,
    )

    seen_codes: list[str] = []

    def fake_run_hcr_screen_with_stats(prepared_by_symbol, pick_date):
        seen_codes.extend(sorted(prepared_by_symbol))
        return ([], {"total_symbols": len(prepared_by_symbol), "eligible": 0, "fail_insufficient_history": 0, "fail_resonance": 0, "fail_close_floor": 0, "fail_breakout": 0, "selected": 0})

    monkeypatch.setattr(cli, "run_hcr_screen_with_stats", fake_run_hcr_screen_with_stats, raising=False)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert seen_codes == ["AAA.SZ"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_screen_hcr_turnover_top_uses_liquidity_pool tests/test_cli.py::test_screen_hcr_record_watch_uses_watch_pool_subset -v`
Expected: FAIL because `hcr` does not yet use the shared pool resolver.

- [ ] **Step 3: Write minimal implementation**

```python
def _resolve_pool_codes(
    *,
    method: str,
    pick_date: str,
    pool_source: str,
    runtime_root: Path,
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    reporter: ProgressReporter | None = None,
) -> list[str]:
    if pool_source == "turnover-top":
        top_turnover_pool = build_top_turnover_pool(prepared_by_symbol, top_m=DEFAULT_TOP_M)
        resolved_codes = top_turnover_pool.get(pd.Timestamp(pick_date), [])
    else:
        resolved_codes = _resolve_record_watch_pool_codes(
            method=method,
            pick_date=pick_date,
            runtime_root=runtime_root,
            prepared_by_symbol=prepared_by_symbol,
        )
    if reporter:
        reporter.emit("screen", f"pool source={pool_source} size={len(resolved_codes)}")
    return [code for code in resolved_codes if code in prepared_by_symbol]


def _subset_prepared_by_codes(
    prepared_by_symbol: Mapping[str, pd.DataFrame],
    codes: Sequence[str],
) -> dict[str, pd.DataFrame]:
    return {code: prepared_by_symbol[code] for code in codes if code in prepared_by_symbol}


if prepared is None:
    prepared = {}
pool_codes = _resolve_pool_codes(
    method=method,
    pick_date=pick_date,
    pool_source=pool_source,
    runtime_root=runtime_root,
    prepared_by_symbol=prepared,
    reporter=reporter,
)
prepared_for_pick = _subset_prepared_by_codes(prepared, pool_codes)

if method == "b1":
    candidates, stats = run_b1_screen_with_stats(prepared_for_pick, pd.Timestamp(pick_date), DEFAULT_B1_CONFIG)
elif method == "b2":
    candidates, stats = run_b2_screen_with_stats(prepared_for_pick, pd.Timestamp(pick_date), DEFAULT_B1_CONFIG)
else:
    candidates, stats = run_hcr_screen_with_stats(prepared_for_pick, pd.Timestamp(pick_date))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_screen_hcr_turnover_top_uses_liquidity_pool tests/test_cli.py::test_screen_hcr_record_watch_uses_watch_pool_subset -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/stock_select/cli.py src/stock_select/watch_pool.py
git commit -m "feat: unify screening pool resolution"
```

### Task 4: Preserve `b2` two-phase behavior under both pool sources

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_screen_b2_record_watch_only_warms_watch_pool_symbols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    watch_dir = runtime_root / "watch_pool"
    watch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"method": "b2", "pick_date": "2026-04-09", "code": "BBB.SZ", "verdict": "WATCH", "total_score": 5.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-11T09:00:00+08:00"}
        ]
    ).to_csv(watch_dir / "b2.csv", index=False)

    trade_dates = pd.bdate_range(end="2026-04-10", periods=160)
    fetch_calls: list[dict[str, object]] = []

    def fake_connect(_: str) -> object:
        return object()

    def _market_frame(symbols: list[str]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for code, base in (("AAA.SZ", 10.0), ("BBB.SZ", 20.0), ("CCC.SZ", 30.0)):
            if code not in symbols:
                continue
            for idx, trade_date in enumerate(trade_dates):
                close = base + idx * 0.05
                rows.append(
                    {
                        "ts_code": code,
                        "trade_date": trade_date,
                        "open": close - 0.1,
                        "high": close + 0.2,
                        "low": close - 0.2,
                        "close": close,
                        "vol": 100.0 + idx,
                    }
                )
        return pd.DataFrame(rows)

    def fake_fetch_daily_window(connection, *, start_date, end_date, symbols=None):
        fetch_calls.append({"start_date": start_date, "end_date": end_date, "symbols": None if symbols is None else list(symbols)})
        request_symbols = ["AAA.SZ", "BBB.SZ", "CCC.SZ"] if symbols is None else list(symbols)
        return _market_frame(request_symbols)

    def fake_prepare_screen_data(market: pd.DataFrame, reporter=None):
        prepared: dict[str, pd.DataFrame] = {}
        for code, group in market.groupby("ts_code"):
            group = group.sort_values("trade_date").reset_index(drop=True).copy()
            group["turnover_n"] = 100.0 if code != "BBB.SZ" else 999.0
            group["J"] = 10.0
            group["zxdq"] = group["close"] + 0.3
            group["zxdkx"] = group["close"] - 0.1
            group["low"] = group["close"] - 0.2
            group["volume"] = group["vol"]
            group["ma25"] = group["close"]
            group["ma60"] = group["close"]
            group["ma144"] = group["close"]
            group["dif"] = 0.12
            group["dea"] = 0.08
            group["dif_w"] = 0.20
            group["dea_w"] = 0.15
            group["dif_m"] = 0.30
            group["dea_m"] = 0.22
            prepared[code] = group
        return prepared

    monkeypatch.setattr(cli, "_connect", fake_connect)
    monkeypatch.setattr(cli, "fetch_daily_window", fake_fetch_daily_window)
    monkeypatch.setattr(cli, "_prepare_screen_data", fake_prepare_screen_data)
    monkeypatch.setattr(cli, "run_b2_screen_with_stats", lambda prepared_by_symbol, pick_date, config: ([], {"total_symbols": len(prepared_by_symbol), "eligible": 0, "fail_recent_j": 0, "fail_insufficient_history": 0, "fail_support_ma25": 0, "fail_volume_shrink": 0, "fail_zxdq_zxdkx": 0, "fail_daily_macd": 0, "fail_weekly_macd": 0, "fail_monthly_macd": 0, "fail_ma60_trend": 0, "fail_ma144_distance": 0, "selected": 0}))

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "b2",
            "--pick-date",
            "2026-04-10",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
        ],
    )

    assert result.exit_code == 0
    assert fetch_calls == [
        {"start_date": "2025-04-09", "end_date": "2026-04-10", "symbols": None},
        {"start_date": "2023-01-01", "end_date": "2026-04-10", "symbols": ["BBB.SZ"]},
    ]


def test_screen_intraday_hcr_record_watch_uses_watch_pool_subset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    watch_dir = runtime_root / "watch_pool"
    watch_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"method": "hcr", "pick_date": "2026-04-09", "code": "BBB.SZ", "verdict": "WATCH", "total_score": 5.0, "signal_type": "", "comment": "", "recorded_at": "2026-04-10T09:00:00+08:00"}
        ]
    ).to_csv(watch_dir / "hcr.csv", index=False)

    monkeypatch.setattr(cli, "_resolve_intraday_trade_date", lambda: "2026-04-10")
    monkeypatch.setattr(cli, "_resolve_tushare_token", lambda token: "token")
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(cli, "_resolve_previous_trade_date", lambda connection, trade_date: "2026-04-09")
    monkeypatch.setattr(cli, "_fetch_rt_k_snapshot", lambda token, trade_date: pd.DataFrame())
    monkeypatch.setattr(cli, "_current_shanghai_timestamp", lambda: pd.Timestamp("2026-04-10T11:31:08+08:00"))
    monkeypatch.setattr(cli, "_resolve_hcr_start_date", lambda connection, *, end_date, trading_days: "2025-04-29", raising=False)
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["AAA.SZ", "BBB.SZ"],
                "trade_date": pd.to_datetime(["2026-04-09", "2026-04-09"]),
                "open": [10.0, 20.0],
                "high": [10.5, 20.5],
                "low": [9.8, 19.8],
                "close": [10.4, 20.4],
                "vol": [100.0, 200.0],
            }
        ),
    )
    monkeypatch.setattr(cli, "build_intraday_market_frame", lambda market, snapshot, trade_date: market)
    monkeypatch.setattr(
        cli,
        "_prepare_hcr_screen_data",
        lambda market, reporter=None: {
            "AAA.SZ": pd.DataFrame({"trade_date": pd.to_datetime(["2026-04-10"]), "close": [10.4], "yx": [10.0], "p": [10.1], "resonance_gap_pct": [0.01], "turnover_n": [100.0]}),
            "BBB.SZ": pd.DataFrame({"trade_date": pd.to_datetime(["2026-04-10"]), "close": [20.4], "yx": [20.0], "p": [20.1], "resonance_gap_pct": [0.01], "turnover_n": [200.0]}),
        },
        raising=False,
    )

    seen_codes: list[str] = []

    def fake_run_hcr_screen_with_stats(prepared_by_symbol, pick_date):
        seen_codes.extend(sorted(prepared_by_symbol))
        return ([], {"total_symbols": len(prepared_by_symbol), "eligible": 0, "fail_insufficient_history": 0, "fail_resonance": 0, "fail_close_floor": 0, "fail_breakout": 0, "selected": 0})

    monkeypatch.setattr(cli, "run_hcr_screen_with_stats", fake_run_hcr_screen_with_stats, raising=False)

    result = runner.invoke(
        app,
        [
            "screen",
            "--method",
            "hcr",
            "--intraday",
            "--pool-source",
            "record-watch",
            "--runtime-root",
            str(runtime_root),
            "--dsn",
            "postgresql://example",
            "--tushare-token",
            "token",
        ],
    )

    assert result.exit_code == 0
    assert seen_codes == ["BBB.SZ"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_screen_b2_record_watch_only_warms_watch_pool_symbols tests/test_cli.py::test_screen_intraday_hcr_record_watch_uses_watch_pool_subset -v`
Expected: FAIL because the current `b2` prefetch path and intraday `hcr` flow do not yet use the shared pool-source resolver.

- [ ] **Step 3: Write minimal implementation**

```python
def _prepare_b2_screen_data_for_pick(
    connection,
    *,
    pick_date: str,
    runtime_root: Path,
    pool_source: str,
    reporter: ProgressReporter | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    ...
    short_prepared = _call_prepare_screen_data(short_market, reporter=reporter)
    pool_codes = _resolve_pool_codes(
        method="b2",
        pick_date=pick_date,
        pool_source=pool_source,
        runtime_root=runtime_root,
        prepared_by_symbol=short_prepared,
        reporter=reporter,
    )
    pooled_prepared = _subset_prepared_by_codes(short_prepared, pool_codes)
    ...


screen_prepared, prepared = _prepare_b2_screen_data_for_pick(
    connection,
    pick_date=pick_date,
    runtime_root=runtime_root,
    pool_source=pool_source,
    reporter=reporter,
)


pool_codes = _resolve_pool_codes(
    method=method,
    pick_date=trade_date,
    pool_source=pool_source,
    runtime_root=runtime_root,
    prepared_by_symbol=prepared,
    reporter=reporter,
)
prepared_for_pick = _subset_prepared_by_codes(prepared, pool_codes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_screen_b2_record_watch_only_warms_watch_pool_symbols tests/test_cli.py::test_screen_intraday_hcr_record_watch_uses_watch_pool_subset -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/stock_select/cli.py src/stock_select/watch_pool.py
git commit -m "fix: apply pool source to b2 warmup and intraday screen"
```

### Task 5: Run the focused regression suite and update docs if needed

**Files:**
- Modify: `README.md`
- Test: `tests/test_cli.py`
- Modify: `src/stock_select/cli.py`
- Modify: `src/stock_select/watch_pool.py`

- [ ] **Step 1: Add any final failing doc test or README assertions if command examples are updated**

```python
def test_readme_mentions_pool_source_for_screen_and_run() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "--pool-source" in content
    assert "turnover-top" in content
    assert "record-watch" in content
```

- [ ] **Step 2: Run tests to verify current failures**

Run: `pytest tests/test_cli.py::test_readme_mentions_pool_source_for_screen_and_run -v`
Expected: FAIL if README has not yet been updated. If README is intentionally unchanged, skip this test and do not add it.

- [ ] **Step 3: Write minimal implementation**

```markdown
- `screen` and `run` accept `--pool-source turnover-top|record-watch`
- default is `turnover-top`
- `record-watch` reads `runtime/watch_pool/<method>.csv`
```

- [ ] **Step 4: Run the focused regression suite**

Run: `pytest tests/test_cli.py -k "pool_source or record_watch or liquidity_pool or run_intraday or run_writes_final_summary or hcr" -v`
Expected: PASS

Run: `pytest tests/test_cli.py::test_screen_uses_reference_b1_defaults_and_liquidity_pool tests/test_cli.py::test_screen_uses_reference_b2_defaults_shared_prep_and_liquidity_pool tests/test_cli.py::test_screen_b2_uses_two_phase_fetch_and_only_warms_pool_symbols tests/test_cli.py::test_screen_writes_hcr_candidate_file tests/test_cli.py::test_screen_intraday_hcr_uses_trade_date_lookback_window -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_cli.py src/stock_select/cli.py src/stock_select/watch_pool.py
git commit -m "test: cover shared pool-source screening flows"
```

## Self-Review

Spec coverage checklist:

- `screen` and `run` both gain `--pool-source`: covered by Task 1
- `chart`, `review`, `record-watch`, `review-merge`, and `render-html` stay unchanged: preserved by Task 1 and no task expands their option surface
- `record-watch` screening semantics and errors: covered by Task 2
- `b1`, `b2`, and `hcr` all use one resolver: covered by Task 3
- `hcr` now respects top-turnover and watch-pool sources: covered by Task 3
- `b2` warmup remains pool-aware: covered by Task 4
- intraday `screen` and `run` honor pool-source: covered by Tasks 1 and 4
- progress logging and focused regression coverage: covered by Tasks 3, 4, and 5

Placeholder scan:

- no `TODO`, `TBD`, or undefined helper references remain outside code introduced in earlier tasks
- helper names are consistent across tasks: `_validate_pool_source`, `_resolve_pool_codes`, `_resolve_record_watch_pool_codes`, `_subset_prepared_by_codes`, and `select_effective_watch_pool_codes`

Type consistency:

- `pool_source` is always treated as a normalized string
- `pick_date` remains a string at resolver boundaries and converts to `pd.Timestamp` only when needed for pool lookup and strategy execution
- `prepared_by_symbol` remains `Mapping[str, pd.DataFrame]` throughout helper boundaries
