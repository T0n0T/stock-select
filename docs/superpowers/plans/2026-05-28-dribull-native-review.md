# Dribull Native Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reimplement the Python CLI `dribull` review/run path in Rust without reintroducing the Python CLI bridge.

**Architecture:** Reuse the existing Rust native review orchestration, candidate/runtime layout, b2 structural scorers, summary writer, LLM task builder, and chart gating. Add only the dribull-specific baseline review calculation: default five-factor weights, dribull MACD phase mapping, Python-compatible verdict refinement, and dribull comment/task context.

**Tech Stack:** Rust, serde_json, chrono, existing `stock-select-rs` native review modules.

---

### Task 1: Native Review Entry

**Files:**
- Modify: `src/native_review.rs`
- Test: `tests/native_review.rs`

- [ ] Add a failing test that builds a tiny dribull runtime with candidates and prepared cache, calls `run_native_review(Method::Dribull)`, and expects `reviews/<date>.dribull/summary.json`.
- [ ] Run `cargo test --test native_review dribull -- --nocapture` and verify it fails with the current “only for b1 and b2” error.
- [ ] Update `run_native_review` and `build_baseline_review` to dispatch `Method::Dribull`.
- [ ] Ensure dribull does not resolve b1/b2 environment profiles.

### Task 2: Dribull Baseline Reviewer

**Files:**
- Modify: `src/native_review.rs`
- Test: `tests/dribull_review.rs`

- [ ] Add unit tests for dribull elastic PASS, PASS back-pressure, and no MACD gate behavior.
- [ ] Implement `build_dribull_baseline_review` by reusing b2 structural scorers and `compute_weighted_total`.
- [ ] Implement `map_dribull_macd_phase_score` as the dribull wrapper over existing b2 MACD state mapping, with `history_len < 60` returning `3.0`.
- [ ] Implement `refine_dribull_verdict` and `build_dribull_comment`.

### Task 3: Runtime And Docs

**Files:**
- Modify: `src/native_review.rs`
- Modify: `docs/roadmap.md`
- Modify: `.agents/skills/stock-select/SKILL.md`

- [ ] Give dribull LLM tasks a dribull-focused review context and prompt path.
- [ ] Update roadmap and skill status from “dribull review not implemented” to native review/run supported.
- [ ] Run required verification: `git status --short`, `cargo fmt --check`, and `cargo test --quiet`.
