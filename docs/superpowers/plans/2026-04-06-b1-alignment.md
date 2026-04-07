# B1 Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the standalone `stock-select` B1 screening behavior with the current `StockTradebyZ` repository defaults for the six confirmed screening differences.

**Architecture:** Keep the existing CLI shape and deterministic screen flow, but centralize B1 defaults in the standalone project, add liquidity-pool filtering ahead of screening, and align weekly and J-quantile calculations with `pipeline/Selector.py` and `pipeline/select_stock.py`. Preserve existing chart and review behavior outside of the screen-stage input set.

**Tech Stack:** Python, pandas, Typer, pytest

---

### Task 1: Add regression tests for B1 alignment

**Files:**
- Modify: `tests/test_b1_logic.py`
- Modify: `tests/test_cli.py`

- [ ] Add failing tests covering:
  - B1 default config uses `j_threshold=15.0`, `j_q_threshold=0.10`
  - turnover rolling window uses `43`
  - weekly MA periods use `10/20/30`
  - weekly aggregation uses the last actual trade day of the ISO week
  - liquidity pool selection keeps only top turnover names for the pick date
  - J quantile path uses expanding historical quantile semantics

### Task 2: Align deterministic B1 helpers

**Files:**
- Modify: `src/stock_select/b1_logic.py`

- [ ] Add or update helper logic for:
  - central B1 defaults
  - ISO-week last-trade-date weekly aggregation
  - expanding historical J quantile series
  - liquidity pool selection helper

### Task 3: Align CLI screen-stage behavior

**Files:**
- Modify: `src/stock_select/cli.py`

- [ ] Update screen preparation and invocation to:
  - use the aligned B1 defaults
  - compute `turnover_n` with window `43`
  - compute weekly bull values using `10/20/30`
  - restrict screening to the top-turnover liquidity pool before B1 evaluation

### Task 4: Update docs and verify

**Files:**
- Modify: `README.md`

- [ ] Update the README B1 description to match the aligned defaults and liquidity-pool behavior
- [ ] Run targeted pytest commands for the changed B1 and CLI tests
