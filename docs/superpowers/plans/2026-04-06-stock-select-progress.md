# Stock Select Progress Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stderr progress output to the stock-select CLI so long-running commands visibly report forward progress without changing stdout result contracts.

**Architecture:** Keep progress reporting in the CLI layer via a tiny reporter helper. Thread that helper through `screen`, `chart`, `review`, and `run`, and use TDD to lock stderr/stdout behavior before implementation.

**Tech Stack:** Python 3.13, Typer, pytest

---

### Task 1: Add CLI Progress Behavior Tests

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/tests/test_cli.py`

- [ ] **Step 1: Write failing tests for progress stderr output**
- [ ] **Step 2: Run `uv run pytest -q tests/test_cli.py` to verify failure**
- [ ] **Step 3: Implement minimal CLI progress reporter and wiring**
- [ ] **Step 4: Run `uv run pytest -q tests/test_cli.py` to verify pass**

### Task 2: Verify Full CLI Behavior

**Files:**
- Modify: `/home/pi/Documents/agents/stock-select/src/stock_select/cli.py`
- Modify: `/home/pi/Documents/agents/stock-select/README.md`

- [ ] **Step 1: Add concise README note for `--progress/--no-progress`**
- [ ] **Step 2: Run `uv run pytest -q`**
- [ ] **Step 3: If needed, run one real smoke command and confirm stderr progress appears**
