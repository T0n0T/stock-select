# HCR Method Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `hcr` as a first-class screening method alongside `b1`, keep the existing workflow intact, generalize method handling across the CLI and export surfaces, and update the repository skill file to document the multi-method workflow.

**Architecture:** Introduce a small strategy-dispatch layer so screening no longer assumes `b1`, move deterministic method logic behind explicit `b1` and `hcr` strategy modules, and keep `chart`, `review`, `review-merge`, and `render-html` method-agnostic by trusting the runtime payload metadata. Reuse the existing runtime layout and candidate payload shape, while generalizing hard-coded `B1` labels and expanding the CLI validation surface to allow both built-in methods.

**Tech Stack:** Python, pandas, Typer, psycopg, pytest

---

## File Structure

- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/__init__.py`
  - expose the strategy registry and common method helpers
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/common.py`
  - hold method-independent preparation helpers and shared constants
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b1.py`
  - move the current `b1` screening helpers into a dedicated strategy module
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/hcr.py`
  - implement `hcr` preparation, reference-price calculation, and screening stats
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
  - replace `_ensure_b1` with shared supported-method validation
  - dispatch `screen` by selected strategy
  - preserve `chart`, `review`, `review-merge`, `render-html`, and `run` behavior for both methods
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/html_export.py`
  - generalize hard-coded `B1` summary labels to the runtime method name
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/review_orchestrator.py`
  - keep summary generation method-agnostic and verify existing method propagation
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_b1_logic.py`
  - migrate or split current `b1` logic tests after the strategy-module move
- Create: `/home/pi/Documents/agents/stock-select/tests/test_hcr_logic.py`
  - add unit tests for `YX`, `P`, resonance, breakout, and insufficient-history behavior
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
  - expand CLI coverage to `hcr`, supported-method validation, and `run --method hcr`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_review_orchestrator.py`
  - keep summary method propagation explicit
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_models.py`
  - protect serialization with a non-`b1` method example
- Modify: `/home/pi/Documents/agents/stock-select/README.md`
  - describe the new `hcr` method and the fact that multiple built-in methods exist
- Modify: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/SKILL.md`
  - update operational instructions from single-method `b1` to built-in `b1` plus `hcr`

### Task 1: Add Strategy-Dispatch Coverage Before Refactoring

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_models.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_review_orchestrator.py`

- [ ] **Step 1: Add failing CLI and serialization tests for multi-method support**

```python
def test_screen_rejects_unknown_method() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["screen", "--method", "brick", "--pick-date", "2026-04-01"])

    assert result.exit_code != 0
    assert "supported methods" in result.stderr.lower()
    assert "b1" in result.stderr.lower()
    assert "hcr" in result.stderr.lower()


def test_chart_accepts_hcr_candidate_file_shape(tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "2026-04-01.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-01",
                "method": "hcr",
                "candidates": [{"code": "000001.SZ"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda **kwargs: pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-04-01"]),
                "open": [10.0],
                "high": [10.8],
                "low": [9.8],
                "close": [10.6],
                "vol": [100.0],
            }
        ),
    )
    monkeypatch.setattr(cli, "export_daily_chart", lambda df, code, out_path, bars=120: out_path.write_bytes(b"png") or out_path)

    result = runner.invoke(
        app,
        ["chart", "--method", "hcr", "--pick-date", "2026-04-01", "--runtime-root", str(runtime_root), "--dsn", "postgresql://example"],
    )

    monkeypatch.undo()

    assert result.exit_code == 0
    assert (runtime_root / "charts" / "2026-04-01" / "000001.SZ_day.png").exists()


def test_candidate_run_serializes_hcr_method() -> None:
    run = CandidateRun(
        pick_date="2026-04-01",
        method="hcr",
        candidates=[
            CandidateRecord(
                code="000001.SZ",
                pick_date="2026-04-01",
                method="hcr",
                close=10.0,
                turnover_n=20.0,
            )
        ],
        config={"resonance_tolerance_pct": 0.015},
        query={"start_date": "2025-01-01"},
    )

    payload = run.to_dict()

    assert payload["method"] == "hcr"
    assert payload["candidates"][0]["method"] == "hcr"


def test_summarize_reviews_keeps_method_value_for_hcr() -> None:
    summary = summarize_reviews(
        "2026-04-01",
        "hcr",
        [{"code": "A", "review_mode": "baseline_local", "total_score": 4.6, "verdict": "PASS"}],
        min_score=4.0,
        failures=[],
    )

    assert summary["method"] == "hcr"
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "unknown_method or accepts_hcr_candidate_file_shape" tests/test_models.py -k hcr tests/test_review_orchestrator.py -k hcr -v`
Expected: FAIL because the CLI still hard-rejects non-`b1` methods and the tests do not exist yet

- [ ] **Step 3: Add the test code to the existing test files**

```python
def test_screen_rejects_unknown_method() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["screen", "--method", "brick", "--pick-date", "2026-04-01"])

    assert result.exit_code != 0
    assert "supported methods" in result.stderr.lower()
    assert "b1" in result.stderr.lower()
    assert "hcr" in result.stderr.lower()
```

```python
def test_candidate_run_serializes_hcr_method() -> None:
    run = CandidateRun(
        pick_date="2026-04-01",
        method="hcr",
        candidates=[
            CandidateRecord(
                code="000001.SZ",
                pick_date="2026-04-01",
                method="hcr",
                close=10.0,
                turnover_n=20.0,
            )
        ],
        config={"resonance_tolerance_pct": 0.015},
        query={"start_date": "2025-01-01"},
    )

    payload = run.to_dict()

    assert payload["method"] == "hcr"
    assert payload["candidates"][0]["method"] == "hcr"
```

- [ ] **Step 4: Re-run the targeted tests**

Run: `uv run pytest tests/test_cli.py -k "unknown_method or accepts_hcr_candidate_file_shape" tests/test_models.py -k hcr tests/test_review_orchestrator.py -k hcr -v`
Expected: FAIL on CLI method validation and `chart --method hcr` until the strategy dispatch changes are implemented

- [ ] **Step 5: Commit the failing coverage checkpoint**

```bash
git add tests/test_cli.py tests/test_models.py tests/test_review_orchestrator.py
git commit -m "test: add multi-method coverage for hcr"
```

### Task 2: Extract B1 Into A Strategy Module Without Changing Behavior

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/__init__.py`
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/common.py`
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b1.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_b1_logic.py`

- [ ] **Step 1: Add failing import-level tests for the new `b1` strategy module**

```python
from stock_select.strategies.b1 import DEFAULT_B1_CONFIG, run_b1_screen_with_stats


def test_b1_strategy_module_exports_current_defaults() -> None:
    assert DEFAULT_B1_CONFIG == {"j_threshold": 15.0, "j_q_threshold": 0.10}
```

- [ ] **Step 2: Run the B1 strategy tests to verify they fail**

Run: `uv run pytest tests/test_b1_logic.py -v`
Expected: FAIL because `stock_select.strategies.b1` does not exist yet

- [ ] **Step 3: Create the strategy package and move the current B1 helpers into `strategies/b1.py`**

```python
# src/stock_select/strategies/__init__.py
from stock_select.strategies.b1 import (
    DEFAULT_B1_CONFIG,
    DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool,
    compute_expanding_j_quantile,
    compute_kdj,
    compute_turnover_n,
    compute_weekly_close,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
    run_b1_screen_with_stats,
)

SUPPORTED_METHODS = ("b1", "hcr")


def normalize_method(method: str) -> str:
    return method.strip().lower()


def validate_method(method: str) -> str:
    normalized = normalize_method(method)
    if normalized not in SUPPORTED_METHODS:
        msg = f"Supported methods: {', '.join(SUPPORTED_METHODS)}"
        raise ValueError(msg)
    return normalized
```

```python
# src/stock_select/strategies/common.py
from __future__ import annotations

import pandas as pd


def ensure_volume_column(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "volume" not in out.columns and "vol" in out.columns:
        out["volume"] = out["vol"]
    return out
```

```python
# src/stock_select/strategies/b1.py
from stock_select.b1_logic import *  # noqa: F403
```

- [ ] **Step 4: Update `cli.py` imports to use the new strategy package without changing runtime behavior**

```python
from stock_select.strategies import (
    DEFAULT_B1_CONFIG,
    DEFAULT_MAX_VOL_LOOKBACK,
    DEFAULT_TOP_M,
    DEFAULT_TURNOVER_WINDOW,
    DEFAULT_WEEKLY_MA_PERIODS,
    build_top_turnover_pool,
    compute_kdj,
    compute_turnover_n,
    compute_weekly_ma_bull,
    compute_zx_lines,
    max_vol_not_bearish,
    run_b1_screen,
    run_b1_screen_with_stats,
    validate_method,
)
```

- [ ] **Step 5: Run the B1 and CLI tests to confirm behavior is unchanged**

Run: `uv run pytest tests/test_b1_logic.py tests/test_cli.py -k "b1 or method" -v`
Expected: PASS for existing `b1` behavior, while `hcr` tests still fail

- [ ] **Step 6: Commit the strategy-package extraction**

```bash
git add src/stock_select/strategies/__init__.py src/stock_select/strategies/common.py src/stock_select/strategies/b1.py src/stock_select/cli.py tests/test_b1_logic.py
git commit -m "refactor: extract b1 strategy module"
```

### Task 3: Implement HCR Deterministic Logic

**Files:**
- Create: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/hcr.py`
- Create: `/home/pi/Documents/agents/stock-select/tests/test_hcr_logic.py`

- [ ] **Step 1: Write failing HCR unit tests for `YX`, `P`, resonance, breakout, and missing history**

```python
from __future__ import annotations

import pandas as pd

from stock_select.strategies.hcr import (
    compute_hcr_reference_price,
    compute_hcr_yx,
    prepare_hcr_frame,
    run_hcr_screen_with_stats,
)


def test_compute_hcr_yx_uses_30_bar_high_low_midpoint() -> None:
    frame = pd.DataFrame(
        {
            "high": [10.0 + idx * 0.1 for idx in range(30)],
            "low": [9.0 + idx * 0.1 for idx in range(30)],
        }
    )

    yx = compute_hcr_yx(frame)

    assert round(float(yx.iloc[-1]), 4) == 10.95


def test_compute_hcr_reference_price_uses_const_ref_hhv_300_shift_60_semantics() -> None:
    highs = [10.0] * 359 + [12.0]
    frame = pd.DataFrame({"high": highs})

    reference = compute_hcr_reference_price(frame)

    assert reference.isna().iloc[358]
    assert float(reference.iloc[-1]) == 10.0


def test_run_hcr_screen_with_stats_selects_symbol_when_resonance_and_breakout_pass() -> None:
    pick_date = pd.Timestamp("2026-04-01")
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-10-17", periods=380),
            "open": [9.8] * 380,
            "high": [10.2] * 350 + [10.4] * 30,
            "low": [9.6] * 350 + [9.8] * 30,
            "close": [9.9] * 379 + [10.25],
            "volume": [100.0] * 380,
            "turnover_n": [1000.0] * 380,
        }
    )
    frame = prepare_hcr_frame(frame)
    frame.loc[frame.index[-1], "p"] = frame.loc[frame.index[-1], "yx"] * 1.01
    frame.loc[frame.index[-1], "resonance_gap_pct"] = abs(frame.loc[frame.index[-1], "yx"] - frame.loc[frame.index[-1], "p"]) / frame.loc[frame.index[-1], "p"]

    candidates, stats = run_hcr_screen_with_stats({"000001.SZ": frame}, pick_date=pick_date)

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert stats["selected"] == 1


def test_run_hcr_screen_with_stats_counts_insufficient_history_separately() -> None:
    pick_date = pd.Timestamp("2026-04-01")
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2026-01-01", periods=50),
            "open": [9.8] * 50,
            "high": [10.2] * 50,
            "low": [9.6] * 50,
            "close": [10.1] * 50,
            "volume": [100.0] * 50,
            "turnover_n": [1000.0] * 50,
        }
    )
    frame = prepare_hcr_frame(frame)

    _candidates, stats = run_hcr_screen_with_stats({"000001.SZ": frame}, pick_date=pick_date)

    assert stats["fail_insufficient_history"] == 1
    assert stats["fail_resonance"] == 0
```

- [ ] **Step 2: Run the HCR unit tests to verify they fail**

Run: `uv run pytest tests/test_hcr_logic.py -v`
Expected: FAIL because `stock_select.strategies.hcr` does not exist yet

- [ ] **Step 3: Implement the minimal `hcr` strategy module**

```python
from __future__ import annotations

import pandas as pd

HCR_RESONANCE_TOLERANCE_PCT = 0.015
HCR_MIN_CLOSE = 1.0


def compute_hcr_yx(frame: pd.DataFrame) -> pd.Series:
    high_30 = frame["high"].astype(float).rolling(window=30, min_periods=30).max()
    low_30 = frame["low"].astype(float).rolling(window=30, min_periods=30).min()
    return (high_30 + low_30) / 2.0


def compute_hcr_reference_price(frame: pd.DataFrame) -> pd.Series:
    rolling_high = frame["high"].astype(float).rolling(window=300, min_periods=300).max()
    reference = rolling_high.shift(60)
    return pd.Series([reference.iloc[-1]] * len(frame), index=frame.index, dtype=float)


def prepare_hcr_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    prepared["yx"] = compute_hcr_yx(prepared)
    prepared["p"] = compute_hcr_reference_price(prepared)
    prepared["resonance_gap_pct"] = (prepared["yx"] - prepared["p"]).abs() / prepared["p"].abs()
    return prepared


def run_hcr_screen_with_stats(
    prepared_by_symbol: dict[str, pd.DataFrame],
    pick_date: pd.Timestamp,
) -> tuple[list[dict], dict[str, int]]:
    target_date = pd.Timestamp(pick_date)
    candidates: list[dict] = []
    stats = {
        "total_symbols": len(prepared_by_symbol),
        "eligible": 0,
        "fail_insufficient_history": 0,
        "fail_resonance": 0,
        "fail_close_floor": 0,
        "fail_breakout": 0,
        "selected": 0,
    }

    for code, frame in prepared_by_symbol.items():
        daily = frame.loc[pd.to_datetime(frame["trade_date"]) == target_date]
        if daily.empty:
            continue
        stats["eligible"] += 1
        row = daily.iloc[-1]
        if pd.isna(row["yx"]) or pd.isna(row["p"]) or float(row["p"]) == 0.0:
            stats["fail_insufficient_history"] += 1
            continue
        if float(row["resonance_gap_pct"]) > HCR_RESONANCE_TOLERANCE_PCT:
            stats["fail_resonance"] += 1
            continue
        if float(row["close"]) <= HCR_MIN_CLOSE:
            stats["fail_close_floor"] += 1
            continue
        if float(row["close"]) <= float(row["yx"]):
            stats["fail_breakout"] += 1
            continue
        candidates.append(
            {
                "code": code,
                "pick_date": target_date.strftime("%Y-%m-%d"),
                "close": float(row["close"]),
                "turnover_n": float(row["turnover_n"]),
                "yx": float(row["yx"]),
                "p": float(row["p"]),
                "resonance_gap_pct": float(row["resonance_gap_pct"]),
            }
        )
        stats["selected"] += 1

    return candidates, stats
```

- [ ] **Step 4: Run the HCR unit tests again**

Run: `uv run pytest tests/test_hcr_logic.py -v`
Expected: PASS

- [ ] **Step 5: Commit the HCR logic**

```bash
git add src/stock_select/strategies/hcr.py tests/test_hcr_logic.py
git commit -m "feat: add hcr screening strategy"
```

### Task 4: Wire Strategy Dispatch Through `screen` And `run`

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/__init__.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`

- [ ] **Step 1: Add failing CLI tests for `screen --method hcr` and `run --method hcr`**

```python
def test_screen_writes_hcr_candidate_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_daily_window",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * 380,
                "trade_date": pd.bdate_range("2024-10-17", periods=380),
                "open": [9.8] * 380,
                "high": [10.2] * 350 + [10.4] * 30,
                "low": [9.6] * 350 + [9.8] * 30,
                "close": [9.9] * 379 + [10.25],
                "vol": [100.0] * 380,
            }
        ),
    )

    result = runner.invoke(
        app,
        ["screen", "--method", "hcr", "--pick-date", "2026-04-01", "--runtime-root", str(runtime_root), "--dsn", "postgresql://example"],
    )

    assert result.exit_code == 0
    payload = json.loads((runtime_root / "candidates" / "2026-04-01.json").read_text(encoding="utf-8"))
    assert payload["method"] == "hcr"


def test_run_passes_hcr_method_through_all_stages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(cli, "_screen_impl", lambda **kwargs: calls.append(("screen", kwargs["method"])) or (tmp_path / "screen.json"))
    monkeypatch.setattr(cli, "_chart_impl", lambda **kwargs: calls.append(("chart", kwargs["method"])) or (tmp_path / "charts"))
    monkeypatch.setattr(cli, "_review_impl", lambda **kwargs: calls.append(("review", kwargs["method"])) or (tmp_path / "summary.json"))

    result = runner.invoke(
        app,
        ["run", "--method", "hcr", "--pick-date", "2026-04-01", "--runtime-root", str(tmp_path), "--dsn", "postgresql://example"],
    )

    assert result.exit_code == 0
    assert calls == [("screen", "hcr"), ("chart", "hcr"), ("review", "hcr")]
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "screen_writes_hcr_candidate_file or run_passes_hcr_method_through_all_stages" -v`
Expected: FAIL because `_screen_impl` and `_chart_impl` do not accept or dispatch on `hcr`

- [ ] **Step 3: Add shared strategy dispatch helpers to `strategies/__init__.py`**

```python
from stock_select.strategies import b1, hcr


STRATEGY_REGISTRY = {
    "b1": {
        "prepare": None,
        "screen": b1.run_b1_screen_with_stats,
    },
    "hcr": {
        "prepare": hcr.prepare_hcr_frame,
        "screen": hcr.run_hcr_screen_with_stats,
    },
}
```

- [ ] **Step 4: Update `cli.py` to validate methods once and route screen-stage preparation and selection by strategy**

```python
def _validate_method(method: str) -> str:
    try:
        return validate_method(method)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _prepare_screen_data(
    market: pd.DataFrame,
    *,
    method: str,
    reporter: ProgressReporter | None = None,
    progress_every: int = 500,
) -> dict[str, pd.DataFrame]:
    normalized_method = validate_method(method)
    if market.empty:
        return {}

    prepared: dict[str, pd.DataFrame] = {}
    frame = market.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    if "volume" not in frame.columns and "vol" in frame.columns:
        frame["volume"] = frame["vol"]
    groups = list(frame.groupby("ts_code"))
    for idx, (code, group) in enumerate(groups, start=1):
        group = group.sort_values("trade_date").reset_index(drop=True)
        group["turnover_n"] = compute_turnover_n(group, window=DEFAULT_TURNOVER_WINDOW)
        if normalized_method == "b1":
            kdj = compute_kdj(group)
            group["J"] = kdj["J"]
            zxdq, zxdkx = compute_zx_lines(group)
            group["zxdq"] = zxdq
            group["zxdkx"] = zxdkx
            group["weekly_ma_bull"] = compute_weekly_ma_bull(group, ma_periods=DEFAULT_WEEKLY_MA_PERIODS)
            group["max_vol_not_bearish"] = max_vol_not_bearish(group, lookback=DEFAULT_MAX_VOL_LOOKBACK)
        elif normalized_method == "hcr":
            group = prepare_hcr_frame(group)
        prepared[code] = group
    return prepared
```

```python
def _screen_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    recompute: bool = False,
    reporter: ProgressReporter | None = None,
) -> Path:
    normalized_method = validate_method(method)
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    out_path = candidate_dir / f"{pick_date}.json"
    start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d")
    resolved_dsn = _resolve_cli_dsn(dsn)
    connection = _connect(resolved_dsn)
    market = fetch_daily_window(connection, start_date=start_date, end_date=pick_date, symbols=None)
    prepared = _call_prepare_screen_data(market, method=normalized_method, reporter=reporter)
    if normalized_method == "b1":
        top_turnover_pool = build_top_turnover_pool(prepared, top_m=DEFAULT_TOP_M)
        pool_codes = top_turnover_pool.get(pd.Timestamp(pick_date), [])
        prepared_for_pick = {code: prepared[code] for code in pool_codes if code in prepared}
        candidates, stats = run_b1_screen_with_stats(prepared_for_pick, pd.Timestamp(pick_date), DEFAULT_B1_CONFIG)
    else:
        prepared_for_pick = prepared
        candidates, stats = run_hcr_screen_with_stats(prepared_for_pick, pd.Timestamp(pick_date))
    payload = {"pick_date": pick_date, "method": normalized_method, "candidates": candidates}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
```

- [ ] **Step 5: Update `chart`, `review`, `review-merge`, `render-html`, and `run` to call the shared validator and pass the normalized method through**

```python
@app.command()
def chart(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    method = _validate_method(method)
    reporter = ProgressReporter(enabled=progress)
    if intraday:
        if pick_date is not None:
            raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
        chart_dir = _chart_intraday_impl(method=method, runtime_root=runtime_root, reporter=reporter)
    else:
        if pick_date is None:
            raise typer.BadParameter("--pick-date is required unless --intraday is set.")
        chart_dir = _chart_impl(method=method, pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, reporter=reporter)
    typer.echo(str(chart_dir))
```

```python
@app.command(name="run")
def run_all(
    method: str = typer.Option(..., "--method"),
    pick_date: str | None = typer.Option(None, "--pick-date"),
    dsn: str | None = typer.Option(None, "--dsn"),
    tushare_token: str | None = typer.Option(None, "--tushare-token"),
    runtime_root: Path = typer.Option(_default_runtime_root(), "--runtime-root"),
    intraday: bool = typer.Option(False, "--intraday/--no-intraday"),
    recompute: bool = typer.Option(False, "--recompute/--no-recompute"),
    progress: bool = typer.Option(True, "--progress/--no-progress"),
) -> None:
    method = _validate_method(method)
    reporter = ProgressReporter(enabled=progress)
    if intraday and pick_date is not None:
        raise typer.BadParameter("--pick-date and --intraday are mutually exclusive.")
    if not intraday and pick_date is None:
        raise typer.BadParameter("--pick-date is required unless --intraday is set.")
    if intraday:
        screen_path = _screen_intraday_impl(method=method, dsn=dsn, tushare_token=tushare_token, runtime_root=runtime_root, reporter=reporter)
        chart_path = _chart_intraday_impl(method=method, runtime_root=runtime_root, reporter=reporter)
        review_path = _review_intraday_impl(method=method, runtime_root=runtime_root, reporter=reporter)
    else:
        screen_path = _screen_impl(method=method, pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, recompute=recompute, reporter=reporter)
        chart_path = _chart_impl(method=method, pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, reporter=reporter)
        review_path = _review_impl(method=method, pick_date=pick_date, dsn=dsn, runtime_root=runtime_root, reporter=reporter)
    typer.echo(str(screen_path))
    typer.echo(str(chart_path))
    typer.echo(str(review_path))
```

- [ ] **Step 6: Run the focused CLI tests**

Run: `uv run pytest tests/test_cli.py -k "method or hcr" -v`
Expected: PASS for the new `hcr` method routing and existing method validation coverage

- [ ] **Step 7: Commit the CLI strategy dispatch**

```bash
git add src/stock_select/cli.py src/stock_select/strategies/__init__.py tests/test_cli.py
git commit -m "feat: route screen workflow by method"
```

### Task 5: Generalize Export Surfaces And Method Labels

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/html_export.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_review_orchestrator.py`

- [ ] **Step 1: Add failing tests for HCR method labels in summaries and HTML**

```python
from stock_select.html_export import render_summary_html


def test_render_summary_html_uses_runtime_method_label() -> None:
    html = render_summary_html(
        {
            "pick_date": "2026-04-01",
            "method": "hcr",
            "reviewed_count": 1,
            "recommendations": [],
            "excluded": [],
            "failures": [],
        }
    )

    assert "<title>HCR Summary 2026-04-01</title>" in html
    assert "HCR Summary Dashboard" in html
```

- [ ] **Step 2: Run the export and summary tests to verify they fail**

Run: `uv run pytest tests/test_review_orchestrator.py -k hcr tests/test_cli.py -k render_html -v`
Expected: FAIL because the HTML renderer still hard-codes `B1`

- [ ] **Step 3: Update the HTML renderer to derive the display label from `summary["method"]`**

```python
def _display_method(method: object) -> str:
    text = str(method or "").strip()
    return text.upper() if text else "-"
```

```python
method_label = _display_method(summary.get("method"))
<title>{_escape(method_label)} Summary {_escape(summary.get("pick_date", ""))}</title>
<h1>{_escape(method_label)} Summary Dashboard</h1>
```

- [ ] **Step 4: Re-run the export and summary tests**

Run: `uv run pytest tests/test_review_orchestrator.py tests/test_cli.py -k "hcr or render_html" -v`
Expected: PASS

- [ ] **Step 5: Commit the generalized method labels**

```bash
git add src/stock_select/html_export.py tests/test_cli.py tests/test_review_orchestrator.py
git commit -m "feat: generalize summary labels by method"
```

### Task 6: Update Skill And README Documentation

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/SKILL.md`
- Modify: `/home/pi/Documents/agents/stock-select/README.md`

- [ ] **Step 1: Add the documentation updates for `hcr` support and method-agnostic workflow**

```markdown
- Support built-in deterministic methods `b1` and `hcr`.
- Resolve the selected method before any screening step and reject only unsupported methods.
- `screen`, `chart`, `review`, and `run` preserve the same runtime layout across methods.
- `b1` keeps the turnover-pool prefilter.
- `hcr` evaluates all prepared symbols and selects on Historical High & Center Resonance Breakout semantics.
```

```markdown
## 当前支持的方法

- `b1`
- `hcr` (`Historical High & Center Resonance Breakout`)

### HCR 筛选说明

- `YX = (30 日最高价 + 30 日最低价) / 2`
- `P` 采用 `CONST(REF(HHV(H,300),60))` 的固定历史高点参考位语义
- 共振条件：`abs(YX - P) / abs(P) <= 1.5%`
- 价格条件：`close > 1.0` 且 `close > YX`
```

- [ ] **Step 2: Review the updated docs for contradictions against the spec**

Run: `rg -n "Only method 'b1'|always require --method b1|Current only supports --method b1" README.md .agents/skills/stock-select/SKILL.md`
Expected: no matches

- [ ] **Step 3: Commit the documentation updates**

```bash
git add README.md .agents/skills/stock-select/SKILL.md
git commit -m "docs: document hcr method support"
```

### Task 7: Full Verification Pass

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/__init__.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b1.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/common.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/hcr.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/html_export.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_b1_logic.py`
- Create: `/home/pi/Documents/agents/stock-select/tests/test_hcr_logic.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_models.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_review_orchestrator.py`
- Modify: `/home/pi/Documents/agents/stock-select/README.md`
- Modify: `/home/pi/Documents/agents/stock-select/.agents/skills/stock-select/SKILL.md`

- [ ] **Step 1: Run the targeted method and strategy test suites**

Run: `uv run pytest tests/test_b1_logic.py tests/test_hcr_logic.py tests/test_cli.py tests/test_models.py tests/test_review_orchestrator.py -v`
Expected: PASS

- [ ] **Step 2: Run a narrower CLI smoke check for `hcr` candidate generation**

Run: `uv run pytest tests/test_cli.py -k "screen_writes_hcr_candidate_file or run_passes_hcr_method_through_all_stages or accepts_hcr_candidate_file_shape" -v`
Expected: PASS

- [ ] **Step 3: Inspect the final diff for accidental regressions**

Run: `git diff --stat HEAD~6..HEAD`
Expected: only the planned strategy, CLI, docs, and test files appear

- [ ] **Step 4: Commit any final verification-only fixes**

```bash
git add src/stock_select/cli.py src/stock_select/strategies/__init__.py src/stock_select/strategies/b1.py src/stock_select/strategies/common.py src/stock_select/strategies/hcr.py src/stock_select/html_export.py tests/test_b1_logic.py tests/test_hcr_logic.py tests/test_cli.py tests/test_models.py tests/test_review_orchestrator.py README.md .agents/skills/stock-select/SKILL.md
git commit -m "test: verify hcr multi-method workflow"
```

## Self-Review

- Spec coverage:
  - multi-method CLI support: Task 1, Task 4
  - strategy-layer extraction: Task 2
  - `hcr` formula semantics and stats: Task 3
  - method-agnostic review/export surfaces: Task 5
  - skill update: Task 6
  - verification: Task 7
- Placeholder scan:
  - no unresolved placeholder markers remain in the plan
- Type consistency:
  - plan uses `hcr`, `yx`, `p`, `resonance_gap_pct`, and `validate_method` consistently across tasks
