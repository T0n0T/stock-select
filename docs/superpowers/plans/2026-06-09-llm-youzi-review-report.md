# LLM Youzi Review Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lightweight bullish/bearish symbols to `review-list`, merge LLM comments, and generate a UZI-style HTML review report from subagent annotations.

**Architecture:** Keep the existing model-first review pipeline. `review` writes richer task instructions, subagents still write annotation artifacts, and `review-merge` becomes the aggregation point for both `display.json` and `llm_report.html`.

**Tech Stack:** Rust CLI, serde JSON artifacts, focused Rust integration tests, project-local stock-select skill docs.

---

### Task 1: Review-list Symbol Column

**Files:**
- Modify: `src/engine/presentation.rs`
- Modify: `src/engine/types.rs`
- Modify: `tests/engine_presentation.rs`
- Modify: `tests/cli_review_list.rs`

- [ ] Write failing tests for `KEEP -> ↑`, `CAUTION -> →`, `REJECT -> ↓`, and unreviewed `-`.
- [ ] Run `cargo test --quiet engine_presentation` and confirm the output still lacks the symbol column.
- [ ] Add `review_signal_symbol()` and include the symbol in formatted display lines.
- [ ] Add `llm_comment` to `DisplayRow` with serde default compatibility.
- [ ] Update exact stdout tests for the new column.
- [ ] Run the targeted tests again.

### Task 2: Merge Comment And HTML Report

**Files:**
- Modify: `src/main.rs`
- Modify: `tests/cli_review_flow.rs`

- [ ] Write a failing CLI test that `review-merge` copies `llm_comment` into `display.json` and writes `llm_report.html`.
- [ ] Include a raw response fixture and assert the report references the chart, contains the comment, and escapes HTML.
- [ ] Implement report generation inside `run_review_merge_command()` after display rows are merged.
- [ ] Run the targeted CLI review flow test.

### Task 3: UZI-style Task Prompt And Skill Docs

**Files:**
- Modify: `src/main.rs`
- Modify: `tests/cli_review_flow.rs`
- Modify: `.agents/skills/stock-select/SKILL.md`
- Modify: `.agents/skills/stock-select/references/review-rubric.md`
- Modify: `.agents/skills/stock-select/references/prompt-b2.md`
- Modify: `.agents/skills/stock-select/references/runtime-layout.md`
- Modify: `docs/architecture.md`
- Modify: `docs/workflow.md`

- [ ] Write a failing test that `llm_tasks.json` includes UZI-style shortline instructions.
- [ ] Add the richer `llm_instruction` text to review task rows.
- [ ] Update skill docs and project docs to describe `llm_report.html`, `llm_raw`, and the review-list symbol column.
- [ ] Run targeted tests, `cargo fmt --check`, and the relevant test suite.
