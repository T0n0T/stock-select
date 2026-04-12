# B2 Formula Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `b2`'s old weekly-bull and MACD-hist-rising logic with the new Tongdaxin-style MA/MACD formula while keeping recent `B1` J-hit history and `zxdq > zxdkx`.

**Architecture:** Keep the change narrow: update `b2` strategy evaluation, align CLI breakdown stats to the new failure buckets, and refresh tests to cover the new rule set and insufficient-history handling.

**Tech Stack:** Python, pandas, Typer, pytest

---

## File Structure

- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b2.py`
  - replace the old `b2` rule set with the new MA/MACD rule set
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
  - update `b2` screen breakdown output for the new failure buckets
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_b2_logic.py`
  - add failing coverage for the new `b2` contract
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`
  - keep mocked `b2` stats and real-flow fixtures aligned with the new contract

### Task 1: Write Failing B2 Tests

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_b2_logic.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`

- [ ] **Step 1: Rewrite `b2` strategy tests for the new formula**
- [ ] **Step 2: Update mocked CLI `b2` stats to the new failure buckets**
- [ ] **Step 3: Run `uv run pytest tests/test_b2_logic.py tests/test_cli.py -k b2 -q` and confirm failures**

### Task 2: Implement The New B2 Logic

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b2.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`

- [ ] **Step 1: Implement the new `b2` filters and insufficient-history checks**
- [ ] **Step 2: Update CLI `b2` breakdown output**
- [ ] **Step 3: Run `uv run pytest tests/test_b2_logic.py tests/test_cli.py -k b2 -q` and confirm pass**

### Task 3: Regression Check

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/strategies/b2.py`
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_b2_logic.py`
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`

- [ ] **Step 1: Run `uv run pytest tests/test_b2_logic.py tests/test_b1_logic.py tests/test_cli.py -q`**
- [ ] **Step 2: Inspect the diff and verify only `b2` rewrite changes are included**
