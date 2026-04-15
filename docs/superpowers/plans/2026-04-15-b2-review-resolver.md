# B2 Review Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple method-specific review selection so `default` remains the current review path while `b2` gains a dedicated baseline reviewer and prompt without changing final review outputs.

**Architecture:** Keep result assembly, LLM normalization, merge, and summary logic shared in the existing orchestration layer, but move method-specific baseline review and prompt selection behind a small resolver module. Extract the current baseline review into a `default` reviewer, add a `b2` reviewer with stronger `b2`-aligned scoring, and route both end-of-day and intraday `review` flows through the resolver so task payloads pick the correct prompt path.

**Tech Stack:** Python 3.13, `pytest`, `typer`, `pandas`, JSON runtime artifacts, Markdown skill references

---

## File Structure

- Create: `src/stock_select/review_resolvers.py`
  - central method-to-resolver mapping
- Create: `src/stock_select/reviewers/__init__.py`
  - reviewer package exports
- Create: `src/stock_select/reviewers/default.py`
  - extracted current baseline review logic
- Create: `src/stock_select/reviewers/b2.py`
  - `b2`-specific baseline review logic
- Create: `.agents/skills/stock-select/references/prompt-b2.md`
  - `b2`-specific multimodal chart-review prompt
- Modify: `src/stock_select/review_orchestrator.py`
  - keep shared protocol helpers only
- Modify: `src/stock_select/cli.py`
  - resolve reviewer and prompt per method in both review entry points
- Modify: `.agents/skills/stock-select/SKILL.md`
  - document method-specific prompt selection for `b2`
- Modify: `tests/test_review_orchestrator.py`
  - shift baseline tests to shared-protocol coverage only
- Create: `tests/test_review_resolvers.py`
  - resolver selection and prompt-path coverage
- Create: `tests/test_reviewers_b2.py`
  - `b2` reviewer behavior coverage
- Modify: `tests/test_cli.py`
  - `review` task payload prompt-path routing coverage

### Task 1: Add Resolver Coverage First

**Files:**
- Create: `tests/test_review_resolvers.py`
- Create: `src/stock_select/review_resolvers.py`
- Create: `src/stock_select/reviewers/__init__.py`
- Create: `src/stock_select/reviewers/default.py`
- Create: `src/stock_select/reviewers/b2.py`

- [ ] **Step 1: Write the failing resolver tests**

```python
from stock_select.review_resolvers import get_review_resolver


def test_get_review_resolver_uses_default_for_b1_and_hcr() -> None:
    b1 = get_review_resolver("b1")
    hcr = get_review_resolver("hcr")

    assert b1.name == "default"
    assert hcr.name == "default"
    assert b1.prompt_path.endswith(".agents/skills/stock-select/references/prompt.md")
    assert hcr.prompt_path.endswith(".agents/skills/stock-select/references/prompt.md")


def test_get_review_resolver_uses_b2_prompt_and_name() -> None:
    resolver = get_review_resolver("b2")

    assert resolver.name == "b2"
    assert resolver.prompt_path.endswith(".agents/skills/stock-select/references/prompt-b2.md")


def test_get_review_resolver_returns_callable_review_history() -> None:
    resolver = get_review_resolver("b1")

    assert callable(resolver.review_history)
```

- [ ] **Step 2: Run the resolver tests to verify they fail**

Run: `uv run pytest tests/test_review_resolvers.py -v`
Expected: FAIL with `ModuleNotFoundError` or import failure because `stock_select.review_resolvers` does not exist yet

- [ ] **Step 3: Add the minimal resolver package and mapping**

```python
# src/stock_select/reviewers/default.py
from __future__ import annotations

from typing import Any

import pandas as pd


def review_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    msg = "default reviewer not implemented yet"
    raise NotImplementedError(msg)
```

```python
# src/stock_select/reviewers/b2.py
from __future__ import annotations

from typing import Any

import pandas as pd


def review_b2_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    msg = "b2 reviewer not implemented yet"
    raise NotImplementedError(msg)
```

```python
# src/stock_select/reviewers/__init__.py
from stock_select.reviewers.b2 import review_b2_symbol_history
from stock_select.reviewers.default import review_symbol_history

__all__ = ["review_b2_symbol_history", "review_symbol_history"]
```

```python
# src/stock_select/review_resolvers.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_select.reviewers import review_b2_symbol_history, review_symbol_history


ReviewHistoryFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ReviewResolver:
    name: str
    prompt_path: str
    review_history: ReviewHistoryFn


_REFERENCE_DIR = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "stock-select" / "references"
DEFAULT_PROMPT_PATH = str(_REFERENCE_DIR / "prompt.md")
B2_PROMPT_PATH = str(_REFERENCE_DIR / "prompt-b2.md")


def get_review_resolver(method: str) -> ReviewResolver:
    normalized = method.strip().lower()
    if normalized == "b2":
        return ReviewResolver(name="b2", prompt_path=B2_PROMPT_PATH, review_history=review_b2_symbol_history)
    return ReviewResolver(name="default", prompt_path=DEFAULT_PROMPT_PATH, review_history=review_symbol_history)
```

- [ ] **Step 4: Run the resolver tests to verify they pass**

Run: `uv run pytest tests/test_review_resolvers.py -v`
Expected: PASS with `b1`/`hcr` resolving to `default` and `b2` resolving to the `b2` prompt path

- [ ] **Step 5: Commit the resolver scaffold**

```bash
git add tests/test_review_resolvers.py src/stock_select/review_resolvers.py src/stock_select/reviewers/__init__.py src/stock_select/reviewers/default.py src/stock_select/reviewers/b2.py
git commit -m "test: add review resolver coverage"
```

### Task 2: Extract The Current Baseline Reviewer Into `default`

**Files:**
- Modify: `src/stock_select/review_orchestrator.py`
- Modify: `src/stock_select/reviewers/default.py`
- Modify: `tests/test_review_orchestrator.py`

- [ ] **Step 1: Write a failing default-reviewer extraction test**

```python
import pandas as pd

from stock_select.reviewers.default import review_symbol_history


def test_default_review_symbol_history_returns_watch_for_constructive_trend() -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=160, freq="B"),
            "open": [10.0 + idx * 0.05 for idx in range(160)],
            "high": [10.3 + idx * 0.05 for idx in range(160)],
            "low": [9.8 + idx * 0.05 for idx in range(160)],
            "close": [10.2 + idx * 0.05 for idx in range(160)],
            "vol": [1000.0 + idx * 5.0 for idx in range(160)],
        }
    )

    review = review_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-01",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["review_type"] == "baseline"
    assert review["signal_type"] == "trend_start"
    assert review["verdict"] == "WATCH"
    assert review["total_score"] == 3.84
```

- [ ] **Step 2: Run the extraction test to verify it fails correctly**

Run: `uv run pytest tests/test_review_orchestrator.py -k default_review_symbol_history_returns_watch_for_constructive_trend -v`
Expected: FAIL with `NotImplementedError: default reviewer not implemented yet`

- [ ] **Step 3: Move the current baseline review logic into the default reviewer and keep protocol helpers shared**

```python
# src/stock_select/reviewers/default.py
from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.review_orchestrator import build_baseline_comment, compute_weighted_total, infer_signal_type, infer_verdict
from stock_select.strategies import compute_macd


def review_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    frame = history.copy()
    if frame.empty:
        msg = "No daily history available for review."
        raise ValueError(msg)

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)

    ma20 = close.rolling(window=20, min_periods=20).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()
    latest_close = float(close.iloc[-1])
    latest_open = float(open_.iloc[-1])
    recent_window = frame.tail(20)
    recent_close = recent_window["close"].astype(float)
    recent_open = recent_window["open"].astype(float)
    recent_volume = recent_window["vol"].astype(float) if "vol" in recent_window.columns else recent_window["volume"].astype(float)

    trend_structure = _score_trend_structure(close, ma20, ma60)
    price_position = _score_price_position(close)
    volume_behavior = _score_volume_behavior(recent_open, recent_close, recent_volume)
    previous_abnormal_move = _score_previous_abnormal_move(close, volume)
    macd_phase = _score_macd_phase(close)
    total_score = compute_weighted_total(
        {
            "trend_structure": trend_structure,
            "price_position": price_position,
            "volume_behavior": volume_behavior,
            "previous_abnormal_move": previous_abnormal_move,
            "macd_phase": macd_phase,
        }
    )
    signal_type = infer_signal_type(
        latest_close=latest_close,
        latest_open=latest_open,
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        price_position=price_position,
    )
    verdict = infer_verdict(total_score=total_score, volume_behavior=volume_behavior, signal_type=signal_type)
    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "review_type": "baseline",
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
        "total_score": total_score,
        "signal_type": signal_type,
        "verdict": verdict,
        "comment": build_baseline_comment(signal_type=signal_type, verdict=verdict),
    }
```

```python
# src/stock_select/review_orchestrator.py
BASELINE_SCORE_WEIGHTS = {
    "trend_structure": 0.18,
    "price_position": 0.18,
    "volume_behavior": 0.24,
    "previous_abnormal_move": 0.20,
    "macd_phase": 0.20,
}


def compute_weighted_total(scores: dict[str, float]) -> float:
    return round(sum(float(scores[field]) * weight for field, weight in BASELINE_SCORE_WEIGHTS.items()), 2)


def infer_signal_type(
    *,
    latest_close: float,
    latest_open: float,
    trend_structure: float,
    volume_behavior: float,
    price_position: float,
) -> str:
    if trend_structure <= 2.0 or volume_behavior <= 2.0:
        return "distribution_risk"
    if latest_close >= latest_open and trend_structure >= 4.0 and price_position >= 3.0:
        return "trend_start"
    return "rebound"


def infer_verdict(*, total_score: float, volume_behavior: float, signal_type: str) -> str:
    if volume_behavior <= 1.0 or signal_type == "distribution_risk":
        return "FAIL"
    if total_score >= 4.0:
        return "PASS"
    if total_score >= 3.2:
        return "WATCH"
    return "FAIL"


def build_baseline_comment(*, signal_type: str, verdict: str) -> str:
    if signal_type == "distribution_risk":
        return "趋势走弱且量价失衡，前期异动后的承接不足，当前更偏出货风险。"
    if verdict == "PASS":
        return "趋势结构顺畅，量价配合正常，前期异动仍有承接，当前具备继续走强条件。"
    return "结构有修复迹象，但量价与位置优势一般，暂时更适合继续观察。"
```

- [ ] **Step 4: Run the shared orchestrator tests and default-reviewer tests**

Run: `uv run pytest tests/test_review_orchestrator.py -v`
Expected: PASS with shared protocol tests still green and baseline-review tests now passing through `stock_select.reviewers.default`

- [ ] **Step 5: Commit the default reviewer extraction**

```bash
git add src/stock_select/review_orchestrator.py src/stock_select/reviewers/default.py tests/test_review_orchestrator.py
git commit -m "refactor: extract default baseline reviewer"
```

### Task 3: Add `b2` Baseline Reviewer Coverage And Implementation

**Files:**
- Create: `tests/test_reviewers_b2.py`
- Modify: `src/stock_select/reviewers/b2.py`
- Modify: `src/stock_select/review_orchestrator.py`

- [ ] **Step 1: Write failing `b2` reviewer tests**

```python
import pandas as pd

from stock_select.reviewers.b2 import review_b2_symbol_history


def test_b2_review_prefers_shrink_on_retest_structure() -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=170, freq="B"),
            "open": [10.0] * 150 + [12.4, 12.8, 13.2, 13.4, 13.1, 12.9, 12.8, 12.85, 12.95, 13.1, 13.2, 13.3, 13.35, 13.4, 13.5, 13.55, 13.6, 13.65, 13.7, 13.8],
            "high": [10.2] * 150 + [12.9, 13.2, 13.5, 13.6, 13.2, 13.0, 12.95, 13.0, 13.1, 13.25, 13.35, 13.45, 13.5, 13.55, 13.65, 13.7, 13.75, 13.8, 13.9, 14.0],
            "low": [9.8] * 150 + [12.1, 12.6, 13.0, 13.0, 12.8, 12.7, 12.7, 12.8, 12.9, 13.0, 13.1, 13.2, 13.25, 13.3, 13.35, 13.4, 13.45, 13.5, 13.6, 13.7],
            "close": [10.0] * 150 + [12.7, 13.0, 13.3, 13.1, 12.95, 12.85, 12.82, 12.9, 13.02, 13.15, 13.25, 13.35, 13.4, 13.45, 13.55, 13.6, 13.65, 13.72, 13.82, 13.95],
            "vol": [900.0] * 150 + [2500.0, 3100.0, 3600.0, 2200.0, 1400.0, 1200.0, 1100.0, 1150.0, 1180.0, 1300.0, 1320.0, 1350.0, 1380.0, 1400.0, 1450.0, 1500.0, 1520.0, 1550.0, 1600.0, 1680.0],
        }
    )

    review = review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert review["review_type"] == "baseline"
    assert review["volume_behavior"] >= 4.0
    assert review["macd_phase"] >= 4.0
    assert review["signal_type"] in {"trend_start", "rebound"}
    assert review["verdict"] in {"WATCH", "PASS"}


def test_b2_review_penalizes_distribution_damage() -> None:
    history = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=170, freq="B"),
            "open": [16.0 - idx * 0.02 for idx in range(170)],
            "high": [16.2 - idx * 0.02 for idx in range(170)],
            "low": [15.7 - idx * 0.02 for idx in range(170)],
            "close": [15.9 - idx * 0.02 for idx in range(170)],
            "vol": [1000.0 + idx * 12.0 for idx in range(170)],
        }
    )

    review = review_b2_symbol_history(
        code="000002.SZ",
        pick_date="2026-04-30",
        history=history,
        chart_path="/tmp/000002.SZ_day.png",
    )

    assert review["volume_behavior"] <= 2.0
    assert review["macd_phase"] <= 2.0
    assert review["verdict"] == "FAIL"
```

- [ ] **Step 2: Run the `b2` reviewer tests to verify they fail**

Run: `uv run pytest tests/test_reviewers_b2.py -v`
Expected: FAIL with `NotImplementedError: b2 reviewer not implemented yet`

- [ ] **Step 3: Implement the `b2` reviewer with the shared output shape**

```python
# src/stock_select/reviewers/b2.py
from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.review_orchestrator import build_baseline_comment, compute_weighted_total, infer_signal_type, infer_verdict
from stock_select.strategies import compute_macd


def review_b2_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    frame = history.copy()
    if frame.empty:
        msg = "No daily history available for review."
        raise ValueError(msg)

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)
    ma25 = close.rolling(window=25, min_periods=25).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()

    trend_structure = _score_b2_trend_structure(close=close, ma25=ma25, ma60=ma60, low=low)
    price_position = _score_b2_price_position(close=close, high=high, ma25=ma25)
    volume_behavior = _score_b2_volume_behavior(open_=open_, close=close, volume=volume)
    previous_abnormal_move = _score_b2_previous_abnormal_move(close=close, volume=volume)
    macd_phase = _score_b2_macd_phase(close=close)

    total_score = compute_weighted_total(
        {
            "trend_structure": trend_structure,
            "price_position": price_position,
            "volume_behavior": volume_behavior,
            "previous_abnormal_move": previous_abnormal_move,
            "macd_phase": macd_phase,
        }
    )
    signal_type = infer_signal_type(
        latest_close=float(close.iloc[-1]),
        latest_open=float(open_.iloc[-1]),
        trend_structure=trend_structure,
        volume_behavior=volume_behavior,
        price_position=price_position,
    )
    verdict = infer_verdict(total_score=total_score, volume_behavior=volume_behavior, signal_type=signal_type)
    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "review_type": "baseline",
        "trend_structure": trend_structure,
        "price_position": price_position,
        "volume_behavior": volume_behavior,
        "previous_abnormal_move": previous_abnormal_move,
        "macd_phase": macd_phase,
        "total_score": total_score,
        "signal_type": signal_type,
        "verdict": verdict,
        "comment": build_baseline_comment(signal_type=signal_type, verdict=verdict),
    }
```

- [ ] **Step 4: Run the `b2` reviewer tests and shared review tests**

Run: `uv run pytest tests/test_reviewers_b2.py tests/test_review_resolvers.py tests/test_review_orchestrator.py -v`
Expected: PASS with `b2` reviewer returning the shared output shape and default/shared review coverage still green

- [ ] **Step 5: Commit the `b2` reviewer**

```bash
git add src/stock_select/reviewers/b2.py tests/test_reviewers_b2.py src/stock_select/review_resolvers.py
git commit -m "feat: add b2 baseline reviewer"
```

### Task 4: Route CLI Review Through Resolvers

**Files:**
- Modify: `src/stock_select/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests for method-specific prompt selection**

```python
def test_review_b2_writes_b2_prompt_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    method_key = _eod_key("2026-04-01", "b2")
    review_dir = runtime_root / "reviews" / method_key
    (candidate_dir / f"{method_key}.json").write_text(
        json.dumps({"pick_date": "2026-04-01", "method": "b2", "candidates": [{"code": "000001.SZ"}]}),
        encoding="utf-8",
    )
    chart_dir = runtime_root / "charts" / method_key
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")

    monkeypatch.setattr(cli, "_connect", lambda _dsn: object())
    monkeypatch.setattr(
        cli,
        "fetch_symbol_history",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "trade_date": pd.date_range("2026-01-01", periods=160, freq="B"),
                "open": [10.0] * 160,
                "high": [10.3] * 160,
                "low": [9.8] * 160,
                "close": [10.1] * 160,
                "vol": [1000.0] * 160,
            }
        ),
    )

    result = runner.invoke(
        app,
        ["review", "--method", "b2", "--pick-date", "2026-04-01", "--dsn", "postgresql://example", "--runtime-root", str(runtime_root)],
    )

    assert result.exit_code == 0
    tasks = json.loads((review_dir / "llm_review_tasks.json").read_text(encoding="utf-8"))
    assert tasks["prompt_path"].endswith(".agents/skills/stock-select/references/prompt-b2.md")
    assert tasks["tasks"][0]["prompt_path"].endswith(".agents/skills/stock-select/references/prompt-b2.md")
```

```python
def test_review_intraday_uses_resolved_prompt_and_reviewer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    candidate_dir = runtime_root / "candidates"
    chart_dir = runtime_root / "charts" / _intraday_key("2026-04-09T11-31-08+08-00")
    candidate_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "000001.SZ_day.png").write_bytes(b"png")
    (candidate_dir / f"{_intraday_key('2026-04-09T11-31-08+08-00')}.json").write_text(
        json.dumps(
            {
                "mode": "intraday_snapshot",
                "method": "b1",
                "trade_date": "2026-04-09",
                "run_id": "2026-04-09T11-31-08+08-00",
                "candidates": [{"code": "000001.SZ"}],
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
            )
        },
    )
    result = runner.invoke(app, ["review", "--method", "b1", "--intraday", "--runtime-root", str(runtime_root)])
    assert result.exit_code == 0
    tasks = json.loads(
        (runtime_root / "reviews" / _intraday_key("2026-04-09T11-31-08+08-00") / "llm_review_tasks.json").read_text(
            encoding="utf-8"
        )
    )
    assert tasks["prompt_path"].endswith(".agents/skills/stock-select/references/prompt.md")
```

- [ ] **Step 2: Run the CLI review tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "review_b2_writes_b2_prompt_path or review_intraday_uses_latest_intraday_candidate" -v`
Expected: FAIL because `review` still hard-codes `REFERENCE_PROMPT_PATH` and still calls `review_symbol_history` directly

- [ ] **Step 3: Wire both review entry points through the resolver**

```python
# src/stock_select/cli.py
from stock_select.review_resolvers import get_review_resolver
```

```python
# src/stock_select/cli.py
def _review_impl(
    *,
    method: str,
    pick_date: str,
    dsn: str | None,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    resolver = get_review_resolver(method)
    chart_dir = _chart_dir_path(runtime_root, pick_date, method)
    candidate_path = _candidate_path(runtime_root, pick_date, method)
    review_dir = _review_dir_path(runtime_root, pick_date, method)
    review_dir.mkdir(parents=True, exist_ok=True)
    payload = _load_candidate_payload(candidate_path)
    resolved_dsn = _resolve_cli_dsn(dsn)
    connection = _connect(resolved_dsn)
    start_date = (pd.Timestamp(pick_date) - pd.Timedelta(days=366)).strftime("%Y-%m-%d")
    candidates = payload.get("candidates", [])
    reviews: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    llm_review_tasks: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates, start=1):
        code = candidate["code"]
        baseline_review = resolver.review_history(
            code=code,
            pick_date=pick_date,
            history=history,
            chart_path=str(chart_path),
        )
        task = build_review_payload(
            code=code,
            pick_date=pick_date,
            chart_path=str(chart_path),
            rubric_path="references/review-rubric.md",
            prompt_path=resolver.prompt_path,
        )
    tasks_payload = {
        "pick_date": pick_date,
        "method": method.lower(),
        "prompt_path": resolver.prompt_path,
        "tasks": llm_review_tasks,
    }
```

```python
# src/stock_select/cli.py
def _review_intraday_impl(
    *,
    method: str,
    runtime_root: Path,
    reporter: ProgressReporter | None = None,
) -> Path:
    resolver = get_review_resolver(method)
    _, payload = _resolve_latest_intraday_candidate(runtime_root, method)
    run_id = str(payload["run_id"])
    pick_date = str(payload["trade_date"])
    chart_dir = _chart_dir_path(runtime_root, run_id, method)
    review_dir = _review_dir_path(runtime_root, run_id, method)
    review_dir.mkdir(parents=True, exist_ok=True)
    prepared_by_symbol = _load_intraday_prepared_cache(
        runtime_root,
        method=method,
        run_id=run_id,
        trade_date=pick_date,
    )
    candidates = payload.get("candidates", [])
    reviews: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    llm_review_tasks: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates, start=1):
        code = candidate["code"]
        baseline_review = resolver.review_history(
            code=code,
            pick_date=pick_date,
            history=history,
            chart_path=str(chart_path),
        )
        task = build_review_payload(
            code=code,
            pick_date=pick_date,
            chart_path=str(chart_path),
            rubric_path="references/review-rubric.md",
            prompt_path=resolver.prompt_path,
        )
    tasks_payload = {
        "pick_date": pick_date,
        "method": method.lower(),
        "prompt_path": resolver.prompt_path,
        "tasks": llm_review_tasks,
    }
```

```python
# src/stock_select/review_orchestrator.py
def build_review_payload(
    *,
    code: str,
    pick_date: str,
    chart_path: str,
    rubric_path: str,
    prompt_path: str,
) -> dict[str, str]:
    return {
        "code": code,
        "pick_date": pick_date,
        "chart_path": chart_path,
        "rubric_path": rubric_path,
        "prompt_path": prompt_path,
        "input_mode": "image",
        "dispatch": "subagent",
    }
```

- [ ] **Step 4: Run the targeted CLI and orchestrator tests**

Run: `uv run pytest tests/test_cli.py -k "review_writes_summary_json or review_b2_writes_b2_prompt_path or review_intraday_uses_latest_intraday_candidate" tests/test_review_orchestrator.py -v`
Expected: PASS with `b1` still using the default prompt and `b2` now writing `prompt-b2.md`

- [ ] **Step 5: Commit the CLI resolver wiring**

```bash
git add src/stock_select/cli.py src/stock_select/review_orchestrator.py tests/test_cli.py tests/test_review_orchestrator.py
git commit -m "feat: route review through method resolvers"
```

### Task 5: Add The `b2` Prompt And Update Skill Documentation

**Files:**
- Create: `.agents/skills/stock-select/references/prompt-b2.md`
- Modify: `.agents/skills/stock-select/SKILL.md`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write a failing documentation-oriented test for the `b2` prompt file**

```python
def test_b2_review_prompt_file_exists() -> None:
    prompt_path = Path(".agents/skills/stock-select/references/prompt-b2.md")

    assert prompt_path.exists()
    text = prompt_path.read_text(encoding="utf-8")
    assert "25日线" in text
    assert "缩量回踩" in text
    assert "MACD" in text
```

- [ ] **Step 2: Run the prompt-file test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k b2_review_prompt_file_exists -v`
Expected: FAIL because `prompt-b2.md` does not exist yet

- [ ] **Step 3: Add the `b2` prompt and update the skill guidance**

```markdown
# .agents/skills/stock-select/references/prompt-b2.md
你是一名专业波段交易员，当前任务是专门评估 `b2` 候选图形。

重点比默认 prompt 更强调以下观察顺序：

1. 是否属于突破后的回踩再启动，而不是高位追涨
2. 是否围绕 25 日线完成缩量回踩并重新站稳
3. 60 日线是否维持向上或至少不走坏
4. 上涨阶段是否明显强于回踩阶段的量能
5. MACD 是否仍处于有利的启动/加强阶段，而不是死叉衰退阶段

输出 JSON 格式必须与默认 prompt 完全一致，不允许新增字段或改字段名。
```

```markdown
# .agents/skills/stock-select/SKILL.md
- `review` should resolve prompt files by method.
- `b1` and `hcr` use `references/prompt.md`.
- `b2` uses `references/prompt-b2.md`.
- All methods must still return the same `llm_review` JSON format for `review-merge`.
```

- [ ] **Step 4: Run the prompt and skill-adjacent tests**

Run: `uv run pytest tests/test_cli.py -k "b2_review_prompt_file_exists or review_b2_writes_b2_prompt_path" -v`
Expected: PASS with `prompt-b2.md` present and the `b2` review tasks pointing to it

- [ ] **Step 5: Commit the prompt and skill update**

```bash
git add .agents/skills/stock-select/references/prompt-b2.md .agents/skills/stock-select/SKILL.md tests/test_cli.py
git commit -m "docs: add b2 review prompt guidance"
```

### Task 6: Run The Full Targeted Verification Set

**Files:**
- Modify: none
- Test: `tests/test_review_resolvers.py`
- Test: `tests/test_reviewers_b2.py`
- Test: `tests/test_review_orchestrator.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run the resolver, reviewer, orchestrator, and CLI review tests together**

Run: `uv run pytest tests/test_review_resolvers.py tests/test_reviewers_b2.py tests/test_review_orchestrator.py tests/test_cli.py -k "review or resolver or prompt" -v`
Expected: PASS with method-aware review selection, unchanged final review schema, and correct prompt routing

- [ ] **Step 2: Run a focused merge regression check**

Run: `uv run pytest tests/test_cli.py -k "review_merge_combines_baseline_and_llm_results or review_merge_can_limit_merge_to_selected_codes or review_merge_selected_codes_does_not_fail_missing_unselected_results" -v`
Expected: PASS, proving `b2` review changes did not alter shared LLM merge behavior

- [ ] **Step 3: Inspect the final diff for scope**

Run: `git diff -- src/stock_select/cli.py src/stock_select/review_orchestrator.py src/stock_select/review_resolvers.py src/stock_select/reviewers/__init__.py src/stock_select/reviewers/default.py src/stock_select/reviewers/b2.py .agents/skills/stock-select/SKILL.md .agents/skills/stock-select/references/prompt-b2.md tests/test_review_resolvers.py tests/test_reviewers_b2.py tests/test_review_orchestrator.py tests/test_cli.py`
Expected: only resolver, reviewer, prompt-routing, and skill documentation changes

- [ ] **Step 4: Commit the final integrated change**

```bash
git add src/stock_select/cli.py src/stock_select/review_orchestrator.py src/stock_select/review_resolvers.py src/stock_select/reviewers/__init__.py src/stock_select/reviewers/default.py src/stock_select/reviewers/b2.py .agents/skills/stock-select/SKILL.md .agents/skills/stock-select/references/prompt-b2.md tests/test_review_resolvers.py tests/test_reviewers_b2.py tests/test_review_orchestrator.py tests/test_cli.py
git commit -m "feat: add b2 review resolver and prompt"
```

## Self-Review

- Spec coverage:
  - resolver-based review selection is covered by Tasks 1 and 4
  - `default` preservation is covered by Task 2 and Task 4 regression coverage
  - `b2` baseline review specialization is covered by Task 3
  - `b2` prompt addition and skill guidance are covered by Task 5
  - unchanged final output and shared merge contract are verified in Tasks 4 and 6
- Placeholder scan:
  - no `TODO`, `TBD`, or deferred implementation markers remain
- Type consistency:
  - the plan uses `get_review_resolver(...)`, `ReviewResolver.prompt_path`, and `ReviewResolver.review_history(...)` consistently across resolver, CLI, and test tasks

Plan complete and saved to `docs/superpowers/plans/2026-04-15-b2-review-resolver.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
