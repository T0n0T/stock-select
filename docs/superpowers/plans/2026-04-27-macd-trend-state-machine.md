# MACD Trend State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace daily and weekly MACD wave judgment with a strict MACD trend state machine that reports rising/falling/ended/idle/invalid states plus rising-initial and top-divergence flags.

**Architecture:** Add a testable trend-state engine in `stock_select.analysis.macd_waves`, expose daily and weekly trend classifiers, then migrate dribull screening, baseline reviewers, score mapping, CLI task context, and prompts away from old wave labels. Keep artifact schemas stable where useful, but remove old wave-count wording from generated text.

**Tech Stack:** Python, pandas, pytest, Typer CLI, existing `stock_select` strategy and review pipeline.

---

## File Map

- `src/stock_select/analysis/macd_waves.py`: owns `MacdTrendState`, core line-based state machine, daily/weekly trend classifiers, and temporary old wave compatibility wrappers.
- `src/stock_select/analysis/__init__.py`: exports the new trend-state types and classifiers.
- `src/stock_select/review_orchestrator.py`: maps weekly/daily trend states into `macd_phase` and applies MACD verdict gates.
- `src/stock_select/strategies/dribull.py`: replaces wave gates with trend-state gates and renames MACD failure stats from wave terms to trend terms.
- `src/stock_select/reviewers/b1.py`: replaces wave classifiers and B1 weekly MACD context with trend-state comments and score input.
- `src/stock_select/reviewers/b2.py`: replaces wave classifiers, trend-structure wave checks, MACD score input, and comments.
- `src/stock_select/reviewers/dribull.py`: replaces wave classifiers, MACD score input, and comments.
- `src/stock_select/cli.py`: rewrites deterministic LLM task context content to trend-state terms while keeping existing context keys for compatibility.
- `.agents/skills/stock-select/references/prompt-b1.md`: removes old wave-count review instructions.
- `.agents/skills/stock-select/references/prompt-b2.md`: removes old wave-count review instructions. This file is currently dirty in the worktree; merge with existing user edits instead of overwriting them.
- `tests/test_macd_waves.py`: adds direct state-machine tests and public daily/weekly classifier tests.
- `tests/test_dribull_logic.py`: updates dribull screening expectations and stats names.
- `tests/test_review_orchestrator.py`: updates score mapping and verdict gate tests for trend states.
- `tests/test_reviewers_b1.py`, `tests/test_reviewers_b2.py`, `tests/test_reviewers_dribull.py`: updates reviewer tests to trend-state comments and scores.
- `tests/test_cli.py`: updates LLM task context tests and CLI progress stats tests.

---

### Task 1: Add MACD Trend State Engine

**Files:**
- Modify: `src/stock_select/analysis/macd_waves.py`
- Modify: `src/stock_select/analysis/__init__.py`
- Test: `tests/test_macd_waves.py`

- [ ] **Step 1: Write failing tests for line-based state transitions**

Add tests that use a private line-based helper so the transition rules are deterministic and independent of EMA warmup behavior.

```python
from stock_select.analysis.macd_waves import _classify_macd_trend_from_lines


def _line_frame(dif: list[float], dea: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"dif": dif, "dea": dea})


def test_macd_trend_waits_for_both_lines_above_zero_after_underwater_cross() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, -0.12, -0.04],
            dea=[-0.28, -0.24, -0.16, -0.08],
        )
    )

    assert result.phase == "idle"
    assert result.direction == "neutral"
    assert result.reason == "waiting for both MACD lines above zero"


def test_macd_trend_enters_rising_after_underwater_cross_and_both_lines_above_zero() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, -0.12, 0.03, 0.08],
            dea=[-0.28, -0.24, -0.16, 0.01, 0.04],
        )
    )

    assert result.phase == "rising"
    assert result.direction == "rising"
    assert result.phase_index == 1
    assert result.bars_in_phase == 2
    assert result.is_rising_initial is True


def test_macd_trend_alternates_between_rising_and_falling_above_water() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.06, 0.05, 0.07],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.07, 0.06, 0.055],
        )
    )

    assert result.phase == "rising"
    assert result.direction == "rising"
    assert result.phase_index == 3
    assert result.bars_in_phase == 1


def test_macd_trend_marks_ended_when_dif_crosses_below_zero() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.08, 0.02, -0.01],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.01, 0.005],
        )
    )

    assert result.phase == "ended"
    assert result.direction == "neutral"
    assert result.reason == "DIF crossed below zero"


def test_macd_trend_uses_latest_cycle_after_prior_cycle_ended() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, -0.01, -0.20, -0.12, 0.02, 0.06],
            dea=[-0.28, -0.24, 0.01, 0.00, -0.18, -0.14, 0.01, 0.03],
        )
    )

    assert result.phase == "rising"
    assert result.phase_index == 1
    assert result.bars_in_phase == 2


def test_macd_trend_flags_top_divergence_when_rising_spread_shrinks() -> None:
    result = _classify_macd_trend_from_lines(
        _line_frame(
            dif=[-0.30, -0.22, 0.03, 0.09, 0.10],
            dea=[-0.28, -0.24, 0.01, 0.04, 0.07],
        )
    )

    assert result.phase == "rising"
    assert result.metrics["spread"] == 0.03
    assert result.metrics["previous_spread"] == 0.05
    assert result.is_top_divergence is True
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_macd_waves.py -k "macd_trend"
```

Expected: FAIL because `MacdTrendState` and `_classify_macd_trend_from_lines` do not exist.

- [ ] **Step 3: Implement the minimal state engine**

In `src/stock_select/analysis/macd_waves.py`, add:

```python
RISING_INITIAL_BARS = 3
_MIN_TREND_PERIODS = 4


@dataclass(frozen=True)
class MacdTrendState:
    phase: str
    direction: str
    is_rising_initial: bool
    is_top_divergence: bool
    bars_in_phase: int
    phase_index: int
    reason: str
    metrics: dict[str, float | int | bool | str]


def _classify_macd_trend_from_lines(lines: pd.DataFrame) -> MacdTrendState:
    working = lines.copy().reset_index(drop=True)
    if not {"dif", "dea"}.issubset(working.columns):
        return _invalid_trend_state("missing MACD line columns", 0)
    working["dif"] = pd.to_numeric(working["dif"], errors="coerce")
    working["dea"] = pd.to_numeric(working["dea"], errors="coerce")
    working = working.dropna(subset=["dif", "dea"]).reset_index(drop=True)
    if len(working) < _MIN_TREND_PERIODS:
        return _invalid_trend_state("insufficient MACD history", len(working))
    if _is_churn((working["dif"] - working["dea"]).tail(10)):
        return _invalid_trend_state("MACD trend churn", len(working))

    machine = "waiting_underwater_cross"
    phase = "idle"
    reason = "waiting for underwater golden cross"
    bars_in_phase = 0
    phase_index = 0
    latest_cycle_seen = False

    for idx in range(1, len(working)):
        previous = working.iloc[idx - 1]
        current = working.iloc[idx]
        prev_dif = float(previous["dif"])
        prev_dea = float(previous["dea"])
        dif = float(current["dif"])
        dea = float(current["dea"])
        above_water = dif > 0.0 and dea > 0.0
        underwater_golden_cross = prev_dif <= prev_dea and dif > dea and dif < 0.0 and dea < 0.0
        above_dead_cross = prev_dif >= prev_dea and dif < dea and above_water
        above_golden_cross = prev_dif <= prev_dea and dif > dea and above_water

        if phase in {"rising", "falling"} and dif < 0.0:
            phase = "ended"
            machine = "waiting_underwater_cross"
            bars_in_phase = 0
            phase_index = 0
            latest_cycle_seen = False
            reason = "DIF crossed below zero"
            continue

        if machine == "waiting_underwater_cross":
            if underwater_golden_cross:
                machine = "waiting_above_zero"
                phase = "idle"
                reason = "waiting for both MACD lines above zero"
            continue

        if machine == "waiting_above_zero":
            if dif < dea:
                machine = "waiting_underwater_cross"
                phase = "idle"
                reason = "underwater startup failed before zero-axis confirmation"
                continue
            if above_water:
                machine = "running"
                phase = "rising"
                reason = "upward MACD segment after zero-axis confirmation"
                bars_in_phase = 1
                phase_index = 1
                latest_cycle_seen = True
                continue
            reason = "waiting for both MACD lines above zero"
            continue

        if machine == "running":
            bars_in_phase += 1
            if phase == "rising" and above_dead_cross:
                phase = "falling"
                reason = "above-water MACD dead cross"
                bars_in_phase = 1
                phase_index += 1
            elif phase == "falling" and above_golden_cross:
                phase = "rising"
                reason = "above-water MACD golden cross"
                bars_in_phase = 1
                phase_index += 1

    latest_dif = float(working["dif"].iloc[-1])
    latest_dea = float(working["dea"].iloc[-1])
    spread = latest_dif - latest_dea
    previous_spread = float(working["dif"].iloc[-2] - working["dea"].iloc[-2])
    direction = phase if phase in {"rising", "falling"} else "neutral"
    return MacdTrendState(
        phase=phase,
        direction=direction,
        is_rising_initial=phase == "rising" and 1 <= bars_in_phase <= RISING_INITIAL_BARS,
        is_top_divergence=phase == "rising" and spread < previous_spread,
        bars_in_phase=bars_in_phase,
        phase_index=phase_index,
        reason=reason if latest_cycle_seen or phase in {"idle", "ended"} else "waiting for underwater golden cross",
        metrics={
            "periods": len(working),
            "dif": latest_dif,
            "dea": latest_dea,
            "spread": round(spread, 6),
            "previous_spread": round(previous_spread, 6),
        },
    )


def _invalid_trend_state(reason: str, periods: int) -> MacdTrendState:
    return MacdTrendState(
        phase="invalid",
        direction="neutral",
        is_rising_initial=False,
        is_top_divergence=False,
        bars_in_phase=0,
        phase_index=0,
        reason=reason,
        metrics={"periods": periods},
    )
```

- [ ] **Step 4: Add public daily and weekly classifiers**

In the same file, add:

```python
def classify_daily_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState:
    working = _slice_to_pick(frame, pick_date)
    if working.empty or "close" not in working.columns:
        return _invalid_trend_state("missing daily close history", len(working))
    macd = compute_macd(working[["close"]].astype(float))
    return _classify_macd_trend_from_lines(macd[["dif", "dea"]])


def classify_weekly_macd_trend(frame: pd.DataFrame, pick_date: str) -> MacdTrendState:
    working = _slice_to_pick(frame, pick_date)
    if working.empty or "close" not in working.columns:
        return _invalid_trend_state("missing weekly close history", len(working))
    weekly_close = working.set_index("trade_date")["close"].astype(float).resample("W-FRI").last().dropna()
    macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    return _classify_macd_trend_from_lines(macd[["dif", "dea"]])
```

Keep `classify_daily_macd_wave()` and `classify_weekly_macd_wave()` temporarily, but do not use them in migrated production call sites.

- [ ] **Step 5: Export new API**

In `src/stock_select/analysis/__init__.py`, export `MacdTrendState`, `classify_daily_macd_trend`, and `classify_weekly_macd_trend`.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_macd_waves.py
```

Expected: PASS.

---

### Task 2: Replace MACD Score Mapping And Verdict Gates

**Files:**
- Modify: `src/stock_select/review_orchestrator.py`
- Test: `tests/test_review_orchestrator.py`

- [ ] **Step 1: Write failing score mapping tests**

Add tests using `SimpleNamespace` or `MacdTrendState` objects with `phase`, `is_rising_initial`, and `is_top_divergence` attributes.

```python
from types import SimpleNamespace


def _trend(phase: str, *, initial: bool = False, divergence: bool = False):
    return SimpleNamespace(phase=phase, is_rising_initial=initial, is_top_divergence=divergence)


def test_map_macd_phase_scores_rising_initial_without_divergence_as_five() -> None:
    assert map_macd_phase_score(
        method="b2",
        history_len=120,
        weekly_trend=_trend("rising"),
        daily_trend=_trend("rising", initial=True),
    ) == 5.0


def test_map_macd_phase_scores_top_divergence_as_two() -> None:
    assert map_macd_phase_score(
        method="b2",
        history_len=120,
        weekly_trend=_trend("rising", divergence=True),
        daily_trend=_trend("rising", initial=True),
    ) == 2.0


def test_apply_macd_verdict_gate_fails_invalid_or_ended_trend() -> None:
    assert apply_macd_verdict_gate(
        method="dribull",
        current_verdict="PASS",
        weekly_trend=_trend("rising"),
        daily_trend=_trend("ended"),
    ) == "FAIL"
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_review_orchestrator.py -k "macd"
```

Expected: FAIL because `map_macd_phase_score()` and `apply_macd_verdict_gate()` do not accept trend-state arguments yet.

- [ ] **Step 3: Update function signatures and mapping**

Change `map_macd_phase_score()` to accept `weekly_trend` and `daily_trend`; leave old arguments optional only until migrated callers are updated.

```python
def map_macd_phase_score(
    *,
    method: str,
    history_len: int,
    weekly_trend: Any | None = None,
    daily_trend: Any | None = None,
    daily_state: DailyMacdState | None = None,
    weekly_wave: Any | None = None,
    daily_recent_death_cross: bool = False,
) -> float:
    normalized = str(method).strip().lower()
    if normalized in {"b1", "b2", "dribull"} and history_len < 60:
        return 3.0
    if weekly_trend is None or daily_trend is None:
        return 3.0

    weekly_phase = str(getattr(weekly_trend, "phase", ""))
    daily_phase = str(getattr(daily_trend, "phase", ""))
    has_divergence = bool(getattr(weekly_trend, "is_top_divergence", False)) or bool(
        getattr(daily_trend, "is_top_divergence", False)
    )
    daily_initial = bool(getattr(daily_trend, "is_rising_initial", False))

    if weekly_phase in {"invalid", "ended"} or daily_phase in {"invalid", "ended"}:
        return 1.0
    if weekly_phase == "falling" and daily_phase == "falling":
        return 1.0
    if has_divergence or (weekly_phase == "falling" and daily_phase == "rising"):
        return 2.0
    if weekly_phase == "rising" and daily_phase == "rising" and daily_initial:
        return 5.0
    if weekly_phase == "rising" and daily_phase == "rising":
        return 4.0
    if weekly_phase == "rising" and daily_phase == "falling":
        return 3.0
    return 2.0
```

Update `apply_macd_verdict_gate()` similarly:

```python
def apply_macd_verdict_gate(
    *,
    method: str,
    current_verdict: str,
    weekly_trend: Any | None = None,
    daily_trend: Any | None = None,
    daily_state: DailyMacdState | None = None,
    weekly_wave: Any | None = None,
    daily_recent_death_cross: bool = False,
) -> str:
    if weekly_trend is None or daily_trend is None:
        return current_verdict
    weekly_phase = str(getattr(weekly_trend, "phase", ""))
    daily_phase = str(getattr(daily_trend, "phase", ""))
    has_divergence = bool(getattr(weekly_trend, "is_top_divergence", False)) or bool(
        getattr(daily_trend, "is_top_divergence", False)
    )
    if weekly_phase in {"invalid", "ended"} or daily_phase in {"invalid", "ended"}:
        return "FAIL"
    if weekly_phase == "falling" and daily_phase == "falling":
        return "FAIL"
    if has_divergence and current_verdict == "PASS":
        return "WATCH"
    return current_verdict
```

- [ ] **Step 4: Verify GREEN**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_review_orchestrator.py
```

Expected: PASS.

---

### Task 3: Migrate Dribull Screening To Trend States

**Files:**
- Modify: `src/stock_select/strategies/dribull.py`
- Test: `tests/test_dribull_logic.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing dribull screening tests**

Update tests to monkeypatch `classify_weekly_macd_trend()` and `classify_daily_macd_trend()` instead of old wave classifiers.

```python
def _trend(phase: str, *, initial: bool = False, divergence: bool = False):
    return SimpleNamespace(phase=phase, is_rising_initial=initial, is_top_divergence=divergence)


def test_run_dribull_screen_accepts_preferred_rising_initial_trend(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("rising", initial=True))

    candidates, stats = module.run_dribull_screen_with_stats(
        {"000001.SZ": _base_dribull_frame()},
        pick_date=pd.Timestamp("2026-04-10"),
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert [item["code"] for item in candidates] == ["000001.SZ"]
    assert stats["selected"] == 1
    assert "fail_weekly_trend" in stats
    assert "fail_weekly_wave" not in stats


def test_run_dribull_screen_rejects_top_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("stock_select.strategies.dribull")
    monkeypatch.setattr(module, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(module, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("rising", initial=True, divergence=True))

    candidates, stats = module.run_dribull_screen_with_stats(
        {"000001.SZ": _base_dribull_frame()},
        pick_date=pd.Timestamp("2026-04-10"),
        config={"j_threshold": 15.0, "j_q_threshold": 0.10},
    )

    assert candidates == []
    assert stats["fail_trend_combo"] == 1
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_dribull_logic.py -k "dribull_screen"
```

Expected: FAIL because dribull still imports old wave classifiers and old stat names.

- [ ] **Step 3: Replace imports and stats**

In `src/stock_select/strategies/dribull.py`:

```python
from stock_select.analysis.macd_waves import classify_daily_macd_trend, classify_weekly_macd_trend
```

Rename stats:

```python
"fail_weekly_trend": 0,
"fail_daily_trend": 0,
"fail_trend_combo": 0,
```

Add helper:

```python
def _is_dribull_trend_combo_ok(*, weekly_trend: object, daily_trend: object) -> bool:
    weekly_phase = str(getattr(weekly_trend, "phase", ""))
    daily_phase = str(getattr(daily_trend, "phase", ""))
    if weekly_phase in {"invalid", "ended"} or daily_phase in {"invalid", "ended"}:
        return False
    if bool(getattr(weekly_trend, "is_top_divergence", False)) or bool(getattr(daily_trend, "is_top_divergence", False)):
        return False
    if weekly_phase == "rising" and daily_phase == "rising" and bool(getattr(daily_trend, "is_rising_initial", False)):
        return True
    if weekly_phase == "rising" and daily_phase == "falling":
        return True
    return False
```

Replace the old wave block with:

```python
weekly_trend = classify_weekly_macd_trend(history[["trade_date", "close"]], target_date.strftime("%Y-%m-%d"))
if weekly_trend.phase in {"invalid", "ended"}:
    stats["fail_weekly_trend"] += 1
    continue

daily_trend = classify_daily_macd_trend(history[["trade_date", "close"]], target_date.strftime("%Y-%m-%d"))
if daily_trend.phase in {"invalid", "ended"}:
    stats["fail_daily_trend"] += 1
    continue

if not _is_dribull_trend_combo_ok(weekly_trend=weekly_trend, daily_trend=daily_trend):
    stats["fail_trend_combo"] += 1
    continue
```

- [ ] **Step 4: Update CLI progress/test expectations for stat names**

In `src/stock_select/cli.py`, replace progress keys `fail_weekly_wave`, `fail_daily_wave`, and `fail_wave_combo` with `fail_weekly_trend`, `fail_daily_trend`, and `fail_trend_combo`.

In `tests/test_cli.py`, update helper dictionaries and assertions that refer to the old stat names.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_dribull_logic.py tests/test_cli.py -k "dribull and (wave or trend or stats or phase)"
```

Expected: PASS for the selected tests.

---

### Task 4: Migrate Reviewers To Trend-State Comments And Scores

**Files:**
- Modify: `src/stock_select/reviewers/b1.py`
- Modify: `src/stock_select/reviewers/b2.py`
- Modify: `src/stock_select/reviewers/dribull.py`
- Test: `tests/test_reviewers_b1.py`
- Test: `tests/test_reviewers_b2.py`
- Test: `tests/test_reviewers_dribull.py`

- [ ] **Step 1: Write failing reviewer tests**

Use monkeypatched trend classifiers and assert comments contain trend wording and no old wave labels.

```python
def _trend(phase: str, *, initial: bool = False, divergence: bool = False, reason: str = "test"):
    return SimpleNamespace(
        phase=phase,
        direction=phase if phase in {"rising", "falling"} else "neutral",
        is_rising_initial=initial,
        is_top_divergence=divergence,
        bars_in_phase=1,
        phase_index=1,
        reason=reason,
        metrics={},
    )


def test_b2_review_comment_uses_trend_state_not_wave_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(b2_reviewer, "classify_weekly_macd_trend", lambda *args, **kwargs: _trend("rising"))
    monkeypatch.setattr(b2_reviewer, "classify_daily_macd_trend", lambda *args, **kwargs: _trend("rising", initial=True))
    review = b2_reviewer.review_b2_symbol_history(
        code="000001.SZ",
        pick_date="2026-04-30",
        history=_constructive_b2_history(),
        chart_path="/tmp/000001.SZ_day.png",
    )

    assert "周线MACD上升浪" in review["comment"]
    assert "日线MACD上升初期" in review["comment"]
    assert "wave" not in review["comment"]
    assert "三浪" not in review["comment"]
    assert review["macd_phase"] == 5.0
```

Add analogous tests for `b1` and `dribull`, including one divergence case that expects `macd_phase == 2.0` and a comment containing `顶背离风险`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_reviewers_b1.py tests/test_reviewers_b2.py tests/test_reviewers_dribull.py -k "macd or comment or wave or trend"
```

Expected: FAIL because reviewers still call old wave classifiers and old comment builders.

- [ ] **Step 3: Add shared trend comment helpers locally or in orchestrator**

Prefer a small helper in `review_orchestrator.py` so reviewer wording is consistent:

```python
def describe_macd_trend_state(label: str, trend: Any) -> str:
    phase = str(getattr(trend, "phase", "invalid"))
    phase_text = {
        "rising": "上升浪",
        "falling": "下跌浪",
        "idle": "等待启动",
        "ended": "波段结束",
        "invalid": "状态无效",
    }.get(phase, "状态无效")
    extras: list[str] = []
    if bool(getattr(trend, "is_rising_initial", False)):
        extras.append("上升初期")
    if bool(getattr(trend, "is_top_divergence", False)):
        extras.append("顶背离风险")
    suffix = f"（{'、'.join(extras)}）" if extras else ""
    return f"{label}MACD{phase_text}{suffix}"
```

- [ ] **Step 4: Update reviewer imports and score calls**

For each reviewer, import:

```python
from stock_select.analysis import classify_daily_macd_trend, classify_weekly_macd_trend
from stock_select.review_orchestrator import describe_macd_trend_state
```

Replace wave calls with:

```python
weekly_trend = classify_weekly_macd_trend(frame[["trade_date", "close"]], pick_date)
daily_trend = classify_daily_macd_trend(frame[["trade_date", "close"]], pick_date)
macd_phase = map_macd_phase_score(
    method="b2",
    history_len=len(frame),
    weekly_trend=weekly_trend,
    daily_trend=daily_trend,
)
verdict = apply_macd_verdict_gate(
    method="b2",
    current_verdict=verdict,
    weekly_trend=weekly_trend,
    daily_trend=daily_trend,
)
```

For `b1`, remove `_score_b1_macd_phase()` use in favor of `map_macd_phase_score(method="b1", ...)`. Keep non-MACD B1 scoring unchanged.

- [ ] **Step 5: Replace comment builders**

Use comments shaped like:

```python
def _build_b2_comment(*, weekly_trend: Any, daily_trend: Any, verdict: str) -> str:
    weekly_text = describe_macd_trend_state("周线", weekly_trend)
    daily_text = describe_macd_trend_state("日线", daily_trend)
    combo_ok = _is_trend_combo_constructive(weekly_trend=weekly_trend, daily_trend=daily_trend)
    combo_text = "符合" if combo_ok else "不符合"
    return f"{weekly_text}、{daily_text}，该MACD组合{combo_text}b2，当前结论为{verdict}。"
```

Implement `_is_trend_combo_constructive()` with the same preferred/acceptable logic from Task 3, without old wave labels.

- [ ] **Step 6: Update B2 trend-structure scoring inputs**

Change `_score_b2_trend_structure()` parameters from `weekly_wave`, `daily_wave`, `daily_state` to `weekly_trend`, `daily_trend` and use trend phases:

```python
trend_window = (
    str(getattr(weekly_trend, "phase", "")) == "rising"
    and str(getattr(daily_trend, "phase", "")) == "rising"
    and bool(getattr(daily_trend, "is_rising_initial", False))
)
if trend_window and ma_aligned and latest_zxdkx >= previous_zxdkx and near_ma25_support:
    return 5.0
if str(getattr(weekly_trend, "phase", "")) == "rising" and ma_aligned:
    return 4.0
```

- [ ] **Step 7: Verify GREEN**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_reviewers_b1.py tests/test_reviewers_b2.py tests/test_reviewers_dribull.py
```

Expected: PASS.

---

### Task 5: Migrate CLI LLM Context And Prompts

**Files:**
- Modify: `src/stock_select/cli.py`
- Modify: `.agents/skills/stock-select/references/prompt-b1.md`
- Modify: `.agents/skills/stock-select/references/prompt-b2.md`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI context tests**

Update tests around `_build_wave_task_context()` to expect trend wording and absence of old labels.

```python
def test_build_wave_task_context_uses_macd_trend_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "classify_weekly_macd_trend", lambda *args, **kwargs: SimpleNamespace(phase="rising", is_rising_initial=False, is_top_divergence=False, reason="weekly rising"))
    monkeypatch.setattr(cli, "classify_daily_macd_trend", lambda *args, **kwargs: SimpleNamespace(phase="rising", is_rising_initial=True, is_top_divergence=False, reason="daily rising initial"))
    context = cli._build_wave_task_context(_history(), "2026-04-30", method="b2")

    assert "周线MACD上升浪" in context["weekly_wave_context"]
    assert "日线MACD上升浪" in context["daily_wave_context"]
    assert "上升初期" in context["daily_wave_context"]
    combined = " ".join(context.values())
    assert "wave1" not in combined
    assert "wave3" not in combined
    assert "wave2_end" not in combined
    assert "wave4_end" not in combined
    assert "三浪" not in combined
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_cli.py -k "wave_task_context or prompt_b1 or prompt_b2"
```

Expected: FAIL because CLI still builds old wave context and prompts still reference old wave wording.

- [ ] **Step 3: Update CLI imports and context builder**

In `src/stock_select/cli.py`, import trend classifiers and `describe_macd_trend_state`. Replace `_is_review_wave_combo_ok()` with a trend-state combo helper.

```python
def _build_wave_task_context(history: pd.DataFrame, pick_date: str, *, method: str) -> dict[str, str]:
    trend_input = history[["trade_date", "close"]].copy()
    weekly_trend = classify_weekly_macd_trend(trend_input, pick_date)
    daily_trend = classify_daily_macd_trend(trend_input, pick_date)
    combo_ok = _is_review_trend_combo_ok(weekly_trend=weekly_trend, daily_trend=daily_trend)
    weekly_context = f"确定性识别结果：{describe_macd_trend_state('周线', weekly_trend)}；原因：{weekly_trend.reason}。"
    daily_context = f"确定性识别结果：{describe_macd_trend_state('日线', daily_trend)}；原因：{daily_trend.reason}。"
    combo_context = f"组合判定：{'符合' if combo_ok else '不符合'} {method.lower()} 候选要求。"
    return {
        "weekly_wave_context": weekly_context,
        "daily_wave_context": daily_context,
        "wave_combo_context": combo_context,
    }
```

Keep the existing context keys for compatibility.

- [ ] **Step 4: Update prompt wording**

In both prompt files, replace old wording:

- `MACD 浪型位置` -> `MACD 波段状态`
- `浪型上下文` -> `MACD 波段状态上下文`
- `周线几浪、日线几浪` -> `周线/日线处于上升浪、下跌浪、等待启动、波段结束或无效状态`
- remove lists that say weekly accepts `wave1`/`wave3` and daily accepts `wave2_end`/`wave4_end`
- add that `DIF - DEA` 收窄 is the deterministic top-divergence signal supplied by the system context

When editing `.agents/skills/stock-select/references/prompt-b2.md`, preserve existing dirty worktree changes and modify only the MACD wording.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_cli.py -k "wave_task_context or prompt_b1 or prompt_b2"
```

Expected: PASS.

---

### Task 6: Remove Production Dependence On Old Wave Labels

**Files:**
- Modify: source and tests found by `rg`

- [ ] **Step 1: Search remaining production references**

Run:

```bash
rg -n "wave1|wave3|wave2_end|wave4_end|三浪|几浪" src .agents/skills/stock-select/references tests
```

Expected: remaining matches are only compatibility-wrapper tests or explicit assertions that old labels are absent.

- [ ] **Step 2: Remove or update stale references**

For any production source match outside temporary compatibility wrappers, migrate it to trend-state language. For any test that still expects old labels, update it to trend-state expectations.

- [ ] **Step 3: Keep compatibility wrappers isolated**

If `classify_daily_macd_wave()` and `classify_weekly_macd_wave()` remain, mark them as compatibility wrappers in code comments and ensure no production caller imports them except legacy tests.

- [ ] **Step 4: Re-run search**

Run:

```bash
rg -n "classify_daily_macd_wave|classify_weekly_macd_wave|wave1|wave3|wave2_end|wave4_end|三浪|几浪" src .agents/skills/stock-select/references tests
```

Expected: no production call sites use old classifiers; no prompt or generated-comment tests require old wave labels.

---

### Task 7: End-To-End Verification

**Files:**
- No planned edits unless verification exposes defects.

- [ ] **Step 1: Run focused MACD and review tests**

Run:

```bash
PYTHONPATH=src pytest -q \
  tests/test_macd_waves.py \
  tests/test_dribull_logic.py \
  tests/test_review_orchestrator.py \
  tests/test_reviewers_b1.py \
  tests/test_reviewers_b2.py \
  tests/test_reviewers_dribull.py
```

Expected: PASS.

- [ ] **Step 2: Run CLI integration slices**

Run:

```bash
PYTHONPATH=src pytest -q tests/test_cli.py -k "dribull or wave_task_context or prompt_b1 or prompt_b2 or review"
```

Expected: PASS.

- [ ] **Step 3: Run the full test suite if focused tests pass**

Run:

```bash
PYTHONPATH=src pytest -q
```

Expected: PASS. If unrelated failures appear from the pre-existing dirty worktree, record the failing tests and inspect whether they are caused by this MACD change before editing.

- [ ] **Step 4: Review diff for accidental reversions**

Run:

```bash
git diff --stat
git diff -- src/stock_select/analysis/macd_waves.py src/stock_select/review_orchestrator.py src/stock_select/strategies/dribull.py src/stock_select/reviewers/b1.py src/stock_select/reviewers/b2.py src/stock_select/reviewers/dribull.py src/stock_select/cli.py tests/test_macd_waves.py
```

Expected: diff only contains MACD trend-state migration and necessary test/prompt updates. Do not revert unrelated dirty files.

---

### Task 8: Commit Implementation

**Files:**
- Commit only files intentionally changed for this implementation.

- [ ] **Step 1: Check worktree status**

Run:

```bash
git status --short
```

Expected: includes this implementation's files plus any pre-existing unrelated dirty files. Do not stage unrelated files.

- [ ] **Step 2: Stage implementation files explicitly**

Run:

```bash
git add \
  src/stock_select/analysis/macd_waves.py \
  src/stock_select/analysis/__init__.py \
  src/stock_select/review_orchestrator.py \
  src/stock_select/strategies/dribull.py \
  src/stock_select/reviewers/b1.py \
  src/stock_select/reviewers/b2.py \
  src/stock_select/reviewers/dribull.py \
  src/stock_select/cli.py \
  .agents/skills/stock-select/references/prompt-b1.md \
  .agents/skills/stock-select/references/prompt-b2.md \
  tests/test_macd_waves.py \
  tests/test_dribull_logic.py \
  tests/test_review_orchestrator.py \
  tests/test_reviewers_b1.py \
  tests/test_reviewers_b2.py \
  tests/test_reviewers_dribull.py \
  tests/test_cli.py
```

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "feat: replace macd waves with trend state machine"
```

Expected: commit succeeds after tests pass.
