# LSH Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `lsh` 筛选方法，并完成候选回填、dataset 构建和 LightGBM 训练验证。

**Architecture:** `lsh` 作为独立 `Method` 接入 CLI 和 screen 分发。策略实现放在 `src/strategies/lsh.rs`，从日线历史计算 MA25 条件，并按自然周、自然月聚合收盘价计算 MACD 柱值和 DEA。

**Tech Stack:** Rust CLI、chrono、serde、Python ML 脚本、LightGBM。

---

### Task 1: 方法枚举和能力边界

**Files:**
- Modify: `src/model.rs`
- Modify: `src/cache.rs`
- Modify: `src/engine/capability.rs`
- Test: `tests/engine_capability.rs`

- [ ] **Step 1: Write failing tests**

Add tests that `Method::from_str("lsh")` works, `Method::Lsh.as_str()` is `lsh`, and `method_capability(Method::Lsh)` supports screen/chart/factor extraction but rejects model run.

- [ ] **Step 2: Run tests to verify failure**

Run: `cargo test --quiet engine_capability`

Expected: compile failure because `Method::Lsh` does not exist.

- [ ] **Step 3: Implement minimal method support**

Add `Lsh` to `Method`, parse/display it as `lsh`, include it in prepared cache shared methods, and add capability with `run=false` and `model_inference=false`.

- [ ] **Step 4: Verify green**

Run: `cargo test --quiet engine_capability`

Expected: pass.

### Task 2: LSH 策略实现

**Files:**
- Create: `src/strategies/lsh.rs`
- Modify: `src/strategies/mod.rs`
- Modify: `src/screening.rs`
- Test: `src/strategies/lsh.rs`
- Test: `tests/screening.rs`

- [ ] **Step 1: Write failing tests**

Add strategy unit tests for selected and rejected LSH rows. Add a screen integration test asserting `candidates/<date>.lsh.json` is written with `signal = "LSH"`.

- [ ] **Step 2: Run tests to verify failure**

Run: `cargo test --quiet lsh`

Expected: compile failure or failing assertions because strategy does not exist.

- [ ] **Step 3: Implement strategy**

Create `run_lsh_strategy_from_refs`, group rows by symbol, find pick date, require MA25 and日线条件, aggregate weekly/monthly closes through pick date, compute `indicators::macd`, and require latest weekly/monthly `hist > 0 && dea > 0`.

- [ ] **Step 4: Wire screen dispatch**

Expose `strategies::lsh`, include `Method::Lsh` in `ensure_screen_supported`, and dispatch to `run_lsh_strategy_from_refs`.

- [ ] **Step 5: Verify green**

Run: `cargo test --quiet lsh screening`

Expected: pass.

### Task 3: Factor and dataset compatibility

**Files:**
- Modify: `src/factors/registry.rs` if needed
- Modify: `scripts/ml/build_rank_dataset.py` if needed
- Test: `tests/screening_factor_parity.rs` or Python dataset tests if needed

- [ ] **Step 1: Inspect current fallback behavior**

Confirm non-b2/b3 methods use raw common factors and dataset defaults to raw common columns.

- [ ] **Step 2: Add tests only if fallback is not covered**

If `lsh` needs explicit profile behavior, add a focused failing test for raw common factor profile.

- [ ] **Step 3: Implement minimal compatibility edits**

Only add explicit `lsh` entries if tests show default behavior is insufficient.

- [ ] **Step 4: Verify green**

Run: `cargo test --quiet factor` and `python -m unittest tests/test_rank_dataset.py`.

### Task 4: Full verification

**Files:**
- All touched Rust/Python files

- [ ] **Step 1: Format**

Run: `cargo fmt`

- [ ] **Step 2: Rust verification**

Run: `cargo fmt --check && cargo test --quiet`

- [ ] **Step 3: Python verification**

Run: `python -m unittest tests/test_candidate_backfill.py tests/test_rank_dataset.py tests/test_rank_lgbm.py tests/test_lgbm_score_export.py tests/test_lgbm_model_promotion.py`

### Task 5: 生成候选、构建数据集和训练

**Files:**
- Runtime artifacts under `$STOCK_SELECT_RUNTIME_ROOT`
- Diagnostics under `diagnostics/ml/lsh/`

- [ ] **Step 1: Inspect CPU count and training window**

Run: `nproc` and pick a recent one-year train window ending at the latest available trading date if not specified.

- [ ] **Step 2: Build binary**

Run: `cargo build --quiet`

- [ ] **Step 3: Backfill candidates and factors**

Run: `uv run scripts/ml/backfill_candidates.py --method lsh --start-date <start> --end-date <end> --workers <n> --export-factors`

- [ ] **Step 4: Build dataset**

Run: `uv run scripts/ml/build_rank_dataset.py --method lsh --runtime-root "$STOCK_SELECT_RUNTIME_ROOT" --source candidates --start-date <start> --end-date <end>`

- [ ] **Step 5: Train bounded LightGBM trials**

Run up to 12 small-grid trials with `scripts/ml/train_rank_lgbm.py`, compare reports, export best scores, and run promote dry-run only.

- [ ] **Step 6: Report metrics**

Summarize coverage, trial metrics, best parameters, top features, dry-run result, and release recommendation.
