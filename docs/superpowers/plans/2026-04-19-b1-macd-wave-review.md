# B1 MACD Wave Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the reusable weekly/daily MACD wave-analysis core into the `b1` review flow while keeping `b1` screening unchanged and keeping the final review schema stable.

**Architecture:** Add a dedicated `b1` reviewer and route `b1` away from the generic default reviewer path. Reuse the existing `analysis/macd_waves.py` core for weekly/daily wave classification, let `b1` baseline `comment` compress the wave conclusion, count `macd_phase` in `b1` total-score calculation, and pass deterministic wave context into a dedicated `b1` review prompt.

**Tech Stack:** Python, pandas, pytest, Typer CLI, existing `stock_select` review orchestration

---

### File Structure

Planned file ownership for this change:

- Create: `src/stock_select/reviewers/b1.py`
  - dedicated baseline reviewer for `b1`
  - owns `b1`-specific wave-aware `macd_phase` scoring and baseline `comment`
- Modify: `src/stock_select/reviewers/__init__.py`
  - export the new `b1` reviewer
- Modify: `src/stock_select/review_resolvers.py`
  - route `b1` to its own reviewer and prompt path
- Modify: `src/stock_select/review_orchestrator.py`
  - count `macd_phase` inside `b1` total-score calculation
- Modify: `src/stock_select/cli.py`
  - inject wave context into `b1` review tasks
- Create: `.agents/skills/stock-select/references/prompt-b1.md`
  - dedicated LLM review prompt for `b1`
- Modify: `tests/test_review_orchestrator.py`
  - update score-calculation expectations and payload-context coverage
- Create: `tests/test_reviewers_b1.py`
  - cover dedicated `b1` reviewer behavior
- Modify: `tests/test_review_resolvers.py`
  - verify `b1` resolver routing and prompt separation
- Modify: `tests/test_cli.py`
  - verify `b1` task context and prompt usage
- Modify: `README.md`
  - document `b1` review-level MACD wave integration
- Modify: `.agents/skills/stock-select/SKILL.md`
  - update skill/runtime guidance for `b1`
- Modify: `.agents/skills/stock-select/references/runtime-layout.md`
  - document `b1` wave-context task payloads

### Task 1: Add Dedicated B1 Reviewer

**Files:**
- Create: `src/stock_select/reviewers/b1.py`
- Modify: `src/stock_select/reviewers/__init__.py`
- Create: `tests/test_reviewers_b1.py`

- [ ] **Step 1: Write the failing B1 reviewer tests**

```python
import pandas as pd

from stock_select.reviewers.b1 import review_b1_symbol_history


def _constructive_b1_history() -> pd.DataFrame:
    trade_dates = pd.bdate_range(end="2026-04-30", periods=170)
    close = [10.0] * 150 + [
        12.7,
        13.0,
        13.3,
        13.1,
        12.95,
        12.85,
        12.82,
        12.9,
        13.02,
        13.15,
        13.25,
        13.35,
        13.4,
        13.45,
        13.55,
        13.6,
        13.65,
        13.72,
        13.82,
        13.95,
    ]
    return pd.DataFrame(
        {
            "trade_date": trade_dates,
            "open": close,
            "high": [value + 0.2 for value in close],
            "low": [value - 0.2 for value in close],
            "close": close,
            "vol": [900.0] * 150 + [2500.0, 3100.0, 3600.0, 2200.0, 1400.0, 1200.0, 1100.0, 1150.0, 1180.0, 1300.0, 1320.0, 1350.0, 1380.0, 1400.0, 1450.0, 1500.0, 1520.0, 1550.0, 1600.0, 1680.0],
        }
    )


def test_b1_review_keeps_schema_stable_without_extra_reasoning_fields() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "macd_reasoning" not in review
    assert "signal_reasoning" not in review


def test_b1_review_comment_mentions_weekly_and_daily_waves() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "周线" in review["comment"]
    assert "日线" in review["comment"]


def test_b1_review_counts_macd_phase_in_total_score() -> None:
    review = review_b1_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b1_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    score_without_macd = round(
        review["trend_structure"] * 0.225
        + review["price_position"] * 0.225
        + review["volume_behavior"] * 0.30
        + review["previous_abnormal_move"] * 0.25,
        2,
    )
    assert review["total_score"] != score_without_macd
```

- [ ] **Step 2: Run the reviewer tests to verify they fail**

Run: `uv run pytest tests/test_reviewers_b1.py -v`

Expected: FAIL with `ModuleNotFoundError` or import failure because `stock_select.reviewers.b1` does not exist yet

- [ ] **Step 3: Add the dedicated B1 reviewer module**

```python
# src/stock_select/reviewers/b1.py
from __future__ import annotations

from typing import Any

import pandas as pd

from stock_select.analysis import classify_daily_macd_wave, classify_weekly_macd_wave
from stock_select.review_protocol import infer_signal_type, infer_verdict
from stock_select.review_orchestrator import compute_method_total_score
from stock_select.reviewers.default import (
    _score_macd_phase as _legacy_score_macd_phase,
    _score_previous_abnormal_move,
    _score_price_position,
    _score_trend_structure,
    _score_volume_behavior,
)


def review_b1_symbol_history(
    *,
    code: str,
    pick_date: str,
    history: pd.DataFrame,
    chart_path: str,
) -> dict[str, Any]:
    frame = history.copy()
    if frame.empty:
        raise ValueError("No daily history available for review.")

    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    cutoff = pd.Timestamp(pick_date)
    frame = frame.loc[frame["trade_date"] <= cutoff].sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"No daily history available on or before pick_date: {pick_date}")

    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    volume = frame["vol"].astype(float) if "vol" in frame.columns else frame["volume"].astype(float)

    ma20 = close.rolling(window=20, min_periods=20).mean()
    ma60 = close.rolling(window=60, min_periods=60).mean()
    recent_window = frame.tail(20)
    recent_open = recent_window["open"].astype(float)
    recent_close = recent_window["close"].astype(float)
    recent_volume = recent_window["vol"].astype(float) if "vol" in recent_window.columns else recent_window["volume"].astype(float)

    trend_structure = _score_trend_structure(close, ma20, ma60)
    price_position = _score_price_position(close)
    volume_behavior = _score_volume_behavior(recent_open, recent_close, recent_volume)
    previous_abnormal_move = _score_previous_abnormal_move(close, volume)
    weekly_wave = classify_weekly_macd_wave(frame[["trade_date", "close"]], pick_date)
    daily_wave = classify_daily_macd_wave(frame[["trade_date", "close"]], pick_date)
    macd_phase = _score_b1_macd_phase(close=close, weekly_wave=weekly_wave, daily_wave=daily_wave)
    total_score = compute_method_total_score(
        "b1",
        {
            "trend_structure": trend_structure,
            "price_position": price_position,
            "volume_behavior": volume_behavior,
            "previous_abnormal_move": previous_abnormal_move,
            "macd_phase": macd_phase,
        },
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
        "comment": _build_b1_comment(weekly_wave=weekly_wave, daily_wave=daily_wave, verdict=verdict),
    }


def _score_b1_macd_phase(*, close: pd.Series, weekly_wave: Any, daily_wave: Any) -> float:
    if len(close) < 60:
        return 3.0
    if weekly_wave.label in {"wave1", "wave3"} and daily_wave.label in {"wave2_end", "wave4_end"}:
        if daily_wave.label != "wave4_end" or float(daily_wave.details.get("third_wave_gain", 0.0)) <= 0.30:
            return 5.0
    if weekly_wave.label in {"wave1", "wave3"}:
        return 4.0
    if daily_wave.label in {"wave2_end", "wave4_end"}:
        return 2.0
    return max(1.0, min(3.0, float(_legacy_score_macd_phase(close))))


def _build_b1_comment(*, weekly_wave: Any, daily_wave: Any, verdict: str) -> str:
    combo_ok = weekly_wave.label in {"wave1", "wave3"} and daily_wave.label in {"wave2_end", "wave4_end"}
    combo_text = "符合" if combo_ok else "不符合"
    if daily_wave.label == "wave4_end":
        gain = float(daily_wave.details.get("third_wave_gain", 0.0)) * 100.0
        return f"周线{weekly_wave.label}、日线{daily_wave.label}，三浪涨幅约{gain:.1f}%且该组合{combo_text}b1，当前结论为{verdict}。"
    return f"周线{weekly_wave.label}、日线{daily_wave.label}，该组合{combo_text}b1，当前结论为{verdict}。"
```

```python
# src/stock_select/reviewers/__init__.py
from stock_select.reviewers.b1 import review_b1_symbol_history
from stock_select.reviewers.b2 import review_b2_symbol_history
from stock_select.reviewers.default import review_symbol_history

__all__ = ["review_b1_symbol_history", "review_b2_symbol_history", "review_symbol_history"]
```

- [ ] **Step 4: Run the reviewer tests and make them pass**

Run: `uv run pytest tests/test_reviewers_b1.py -v`

Expected: PASS

- [ ] **Step 5: Commit the dedicated B1 reviewer**

```bash
git add src/stock_select/reviewers/b1.py src/stock_select/reviewers/__init__.py tests/test_reviewers_b1.py
git commit -m "feat: add b1 wave-aware baseline reviewer"
```

### Task 2: Route B1 Through Its Own Resolver And Count MACD In Total Score

**Files:**
- Modify: `src/stock_select/review_resolvers.py`
- Modify: `src/stock_select/review_orchestrator.py`
- Modify: `tests/test_review_resolvers.py`
- Modify: `tests/test_review_orchestrator.py`

- [ ] **Step 1: Write failing resolver and total-score tests**

```python
def test_get_review_resolver_uses_dedicated_b1_prompt() -> None:
    b1 = get_review_resolver("b1")

    assert b1.name == "b1"
    assert b1.prompt_path.endswith(".agents/skills/stock-select/references/prompt-b1.md")


def test_compute_method_total_score_includes_macd_for_b1() -> None:
    scores = {
        "trend_structure": 5.0,
        "price_position": 4.0,
        "volume_behavior": 5.0,
        "previous_abnormal_move": 4.0,
        "macd_phase": 1.0,
    }

    assert compute_method_total_score("b1", scores) == pytest.approx(3.82)
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_review_resolvers.py tests/test_review_orchestrator.py -k "dedicated_b1_prompt or includes_macd_for_b1" -v`

Expected: FAIL because `b1` still resolves to the generic prompt and `compute_method_total_score("b1", ...)` still excludes `macd_phase`

- [ ] **Step 3: Update resolver wiring and B1 scoring**

```python
# src/stock_select/review_resolvers.py
from stock_select.reviewers import review_b1_symbol_history, review_b2_symbol_history, review_symbol_history

_REFERENCE_DIR = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "stock-select" / "references"
DEFAULT_PROMPT_PATH = str(_REFERENCE_DIR / "prompt.md")
B1_PROMPT_PATH = str(_REFERENCE_DIR / "prompt-b1.md")
B2_PROMPT_PATH = str(_REFERENCE_DIR / "prompt-b2.md")


def get_review_resolver(method: str) -> ReviewResolver:
    normalized = method.strip().lower()
    if normalized == "b1":
        return ReviewResolver(
            name="b1",
            prompt_path=B1_PROMPT_PATH,
            review_history=review_b1_symbol_history,
        )
    if normalized == "b2":
        return ReviewResolver(
            name="b2",
            prompt_path=B2_PROMPT_PATH,
            review_history=review_b2_symbol_history,
        )
    return ReviewResolver(
        name="default",
        prompt_path=DEFAULT_PROMPT_PATH,
        review_history=lambda **kwargs: review_symbol_history(method=normalized or "default", **kwargs),
    )
```

```python
# src/stock_select/review_orchestrator.py
def compute_method_total_score(method: str, scores: dict[str, float]) -> float:
    normalized = str(method).strip().lower()
    if normalized == "hcr":
        return compute_weighted_total_without_macd(scores)
    return compute_weighted_total(scores)
```

- [ ] **Step 4: Run the focused resolver/orchestrator tests**

Run: `uv run pytest tests/test_review_resolvers.py tests/test_review_orchestrator.py -v`

Expected: PASS

- [ ] **Step 5: Commit the resolver and score changes**

```bash
git add src/stock_select/review_resolvers.py src/stock_select/review_orchestrator.py tests/test_review_resolvers.py tests/test_review_orchestrator.py
git commit -m "feat: route b1 review through wave-aware resolver"
```

### Task 3: Add B1 Wave Context To Review Tasks And Split Prompt Contract

**Files:**
- Modify: `src/stock_select/cli.py`
- Create: `.agents/skills/stock-select/references/prompt-b1.md`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI and prompt tests**

```python
def test_review_b1_tasks_include_wave_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    runtime_root = tmp_path / "runtime"
    ...
    result = runner.invoke(
        app,
        ["review", "--method", "b1", "--pick-date", "2026-04-01", "--runtime-root", str(runtime_root), "--dsn", "postgresql://example"],
    )

    assert result.exit_code == 0
    tasks = json.loads((runtime_root / "reviews" / "2026-04-01.b1" / "llm_review_tasks.json").read_text(encoding="utf-8"))
    task = tasks["tasks"][0]
    assert "weekly_wave_context" in task
    assert "daily_wave_context" in task
    assert "wave_combo_context" in task


def test_prompt_b1_requires_weekly_and_daily_wave_language() -> None:
    content = Path(".agents/skills/stock-select/references/prompt-b1.md").read_text(encoding="utf-8")

    assert "weekly_wave_context" in content
    assert "daily_wave_context" in content
    assert "wave_combo_context" in content
    assert "周线" in content
    assert "日线" in content
```

- [ ] **Step 2: Run the focused B1 task/prompt tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k "review_b1_tasks_include_wave_context or prompt_b1_requires_weekly_and_daily_wave_language" -v`

Expected: FAIL because `b1` tasks do not yet include wave context and `prompt-b1.md` does not exist

- [ ] **Step 3: Add B1 wave task context and prompt**

```python
# src/stock_select/cli.py
        task = build_review_payload(
            code=code,
            pick_date=pick_date,
            chart_path=str(chart_path),
            rubric_path="references/review-rubric.md",
            prompt_path=resolver.prompt_path,
            extra_context=_build_b2_wave_task_context(history, pick_date) if method.lower() in {"b1", "b2"} else None,
        )
```

```md
# .agents/skills/stock-select/references/prompt-b1.md
你是一名专业波段交易员，当前任务是评估 `b1` 候选股的图形质量。

你会收到系统提供的：

- `weekly_wave_context`
- `daily_wave_context`
- `wave_combo_context`

必须遵守：

- 周线浪型以系统提供结果为准，不要臆造未展示的周线图细节
- 必须在 `macd_reasoning` 中明确写出周线几浪、日线几浪，以及你是否认可当前浪型解释
- 必须在 `signal_reasoning` 中明确写出当前周线/日线组合是否符合 `b1`
- 必须在 `comment` 中压缩表达周线与日线浪型结论

输出 JSON contract 与当前默认 review prompt 保持一致：

- `trend_reasoning`
- `position_reasoning`
- `volume_reasoning`
- `abnormal_move_reasoning`
- `macd_reasoning`
- `signal_reasoning`
- `scores.trend_structure`
- `scores.price_position`
- `scores.volume_behavior`
- `scores.previous_abnormal_move`
- `scores.macd_phase`
- `total_score`
- `signal_type`
- `verdict`
- `comment`
```

- [ ] **Step 4: Run the focused B1 CLI tests**

Run: `uv run pytest tests/test_cli.py -k "b1 and (review or prompt)" -v`

Expected: PASS

- [ ] **Step 5: Commit the B1 task-context and prompt split**

```bash
git add src/stock_select/cli.py .agents/skills/stock-select/references/prompt-b1.md tests/test_cli.py
git commit -m "feat: pass macd wave context into b1 llm review"
```

### Task 4: Update Docs And Run The Relevant Regression Suite

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/stock-select/SKILL.md`
- Modify: `.agents/skills/stock-select/references/runtime-layout.md`
- Test: `tests/test_reviewers_b1.py`
- Test: `tests/test_review_resolvers.py`
- Test: `tests/test_review_orchestrator.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Update docs to reflect B1 review-level wave integration**

```md
# README.md
- `b1` screening remains unchanged.
- `b1` review now reuses weekly/daily MACD wave classification in baseline comment and LLM review-task context.
- `b1` total review score now counts `macd_phase`.
```

```md
# .agents/skills/stock-select/SKILL.md
- `b1` deterministic screening remains unchanged.
- `b1` review uses a dedicated prompt contract and receives deterministic weekly/daily wave context in `llm_review_tasks.json`.
```

```md
# .agents/skills/stock-select/references/runtime-layout.md
- `b1` review tasks now include `weekly_wave_context`, `daily_wave_context`, and `wave_combo_context`.
```

- [ ] **Step 2: Run the relevant regression suite**

Run: `uv run pytest tests/test_reviewers_b1.py tests/test_review_resolvers.py tests/test_review_orchestrator.py tests/test_cli.py -k "b1 or prompt_b1 or review_b1" -v`

Expected: PASS

- [ ] **Step 3: Commit the docs and regression sweep**

```bash
git add README.md .agents/skills/stock-select/SKILL.md .agents/skills/stock-select/references/runtime-layout.md
git commit -m "docs: align b1 review flow with macd wave analysis"
```
