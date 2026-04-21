# MACD Phase Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the baseline `macd_phase` scoring with a shared MACD state model plus method-specific score mapping for `b1`, `b2`, `dribull`, and `hcr/default`.

**Architecture:** Add a shared daily MACD state classifier in the analysis layer, route reviewers through one centralized `macd_phase` mapping function, split `dribull` review away from `b2`, and keep current output schema stable while adding internal structure.

**Tech Stack:** Python, pandas, pytest, Typer CLI, existing `stock_select` review pipeline.

---

### Task 1: Add the Shared Daily MACD State Model

**Files:**
- Modify: `src/stock_select/analysis/macd_waves.py`
- Test: `tests/test_macd_waves.py`

- [ ] **Step 1: Write failing tests for the new daily MACD states**

- [ ] **Step 2: Run the focused tests and confirm the new cases fail**

Run: `PYTHONPATH=src pytest -q tests/test_macd_waves.py`

- [ ] **Step 3: Implement `DailyMacdState` and `classify_daily_macd_state()`**

- [ ] **Step 4: Keep `classify_daily_macd_wave()` as a compatibility wrapper**

- [ ] **Step 5: Re-run `tests/test_macd_waves.py` until green**


### Task 2: Centralize Method-Specific MACD Score Mapping

**Files:**
- Modify: `src/stock_select/review_orchestrator.py`
- Modify: `src/stock_select/reviewers/b1.py`
- Modify: `src/stock_select/reviewers/b2.py`
- Modify: `src/stock_select/reviewers/default.py`
- Test: `tests/test_reviewers_b1.py`
- Test: `tests/test_reviewers_b2.py`
- Create or modify: `tests/test_reviewers_default.py`

- [ ] **Step 1: Write failing reviewer tests for the redesigned score caps and mappings**

- [ ] **Step 2: Run the focused reviewer tests and verify failure**

Run: `PYTHONPATH=src pytest -q tests/test_reviewers_b1.py tests/test_reviewers_b2.py tests/test_reviewers_default.py`

- [ ] **Step 3: Implement a centralized `map_macd_phase_score()` helper**

- [ ] **Step 4: Route `b1`, `b2`, and `default/hcr` reviewers through the shared helper**

- [ ] **Step 5: Re-run the focused reviewer tests until green**


### Task 3: Split Dribull Review From B2

**Files:**
- Create: `src/stock_select/reviewers/dribull.py`
- Modify: `src/stock_select/reviewers/__init__.py`
- Modify: `src/stock_select/review_resolvers.py`
- Create or modify: `tests/test_reviewers_dribull.py`

- [ ] **Step 1: Write failing tests proving `dribull` no longer reuses the `b2` mapping**

- [ ] **Step 2: Run the new dribull tests and confirm failure**

Run: `PYTHONPATH=src pytest -q tests/test_reviewers_dribull.py`

- [ ] **Step 3: Implement the dedicated dribull reviewer using the shared state and score mapper**

- [ ] **Step 4: Update resolver wiring to use the new reviewer**

- [ ] **Step 5: Re-run the dribull tests until green**


### Task 4: Add Strategy-Aware MACD Verdict Gating

**Files:**
- Modify: `src/stock_select/review_protocol.py`
- Modify: `src/stock_select/reviewers/b1.py`
- Modify: `src/stock_select/reviewers/b2.py`
- Modify: `src/stock_select/reviewers/dribull.py`
- Test: `tests/test_reviewers_b1.py`
- Test: `tests/test_reviewers_b2.py`
- Test: `tests/test_reviewers_dribull.py`

- [ ] **Step 1: Write failing tests for “invalid MACD cannot PASS” behavior**

- [ ] **Step 2: Run the focused gate tests and verify failure**

Run: `PYTHONPATH=src pytest -q tests/test_reviewers_b1.py tests/test_reviewers_b2.py tests/test_reviewers_dribull.py`

- [ ] **Step 3: Implement a strategy-aware MACD gate helper and apply it in wave-aware reviewers**

- [ ] **Step 4: Re-run the focused gate tests until green**


### Task 5: Run End-to-End Verification

**Files:**
- No code changes expected unless verification exposes defects

- [ ] **Step 1: Run the targeted full test set**

Run: `PYTHONPATH=src pytest -q tests/test_macd_waves.py tests/test_reviewers_b1.py tests/test_reviewers_b2.py tests/test_reviewers_default.py tests/test_reviewers_dribull.py`

- [ ] **Step 2: Run a small CLI integration slice**

Run: `PYTHONPATH=src pytest -q tests/test_cli.py -k "review and (b1 or b2 or dribull)"`

- [ ] **Step 3: Inspect failures, fix minimal defects, and re-run until green**


### Task 6: Commit the Implementation

**Files:**
- Modify: only files touched by Tasks 1-5

- [ ] **Step 1: Review the final diff for accidental scope creep**

- [ ] **Step 2: Commit the implementation**

Run: `git add <touched files>`
Run: `git commit -m "feat: redesign baseline macd phase scoring"`
