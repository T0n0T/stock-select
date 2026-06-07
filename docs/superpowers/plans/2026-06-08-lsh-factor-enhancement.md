# LSH Factor Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `lsh` 增加 MACD 状态机和放量阳反包因子，并重新构建训练产物。

**Architecture:** 新增 `LshSemantic` factor bundle，复用现有 MACD 状态机，只为 `Method::Lsh` 输出 `lsh_` 前缀因子。Python dataset schema 为 `lsh` 单独注册新增 raw numeric columns。

**Tech Stack:** Rust factor registry、macd_trends 状态机、Python ML dataset/schema、LightGBM。

---

### Task 1: Rust LSH 因子包

- [ ] 写 failing Rust 测试：`Method::Lsh` factor profile 包含 `raw_common` 和 `lsh_semantic`。
- [ ] 写 failing Rust 测试：`build_candidate_factor_rows(..., Method::Lsh, ...)` 输出 `lsh_daily_macd_wave_index`、`lsh_volume_bullish_engulf_prev_bearish_flag` 等。
- [ ] 实现 `FactorBundle::LshSemantic`、`push_lsh_semantic_factors()`。
- [ ] 运行 `cargo test --quiet factor lsh`。

### Task 2: Python dataset schema

- [ ] 写 failing Python 测试：`dataset_columns_for_method("lsh")` 包含新增因子，`b2` 不包含。
- [ ] 添加 `LSH_SPECIFIC_RAW_FACTOR_COLUMNS` 和 `METHOD_RAW_FACTOR_COLUMNS["lsh"]`。
- [ ] 运行 `python -m unittest tests/test_rank_dataset.py tests/test_rank_lgbm.py tests/test_lgbm_score_export.py`。

### Task 3: 全量验证和重训

- [ ] 运行 `cargo fmt --check && cargo test --quiet`。
- [ ] 运行 ML 单元测试。
- [ ] 重跑 `lsh` backfill `--export-factors --no-skip-existing`。
- [ ] 重建 `diagnostics/ml/lsh/rank_dataset.csv`。
- [ ] 重跑受限 LightGBM trials，复制最佳到 `diagnostics/ml/lsh/model`。
- [ ] 导出 scores，执行 promote dry-run，不发布。
