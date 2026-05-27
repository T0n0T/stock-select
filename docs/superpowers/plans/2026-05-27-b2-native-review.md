# b2 Native Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `stock-select-rs review/run --method b2` 切到 Rust 原生 review，并与 Python `2026-05-25.b2` baseline artifacts 对齐。

**Architecture:** 复用当前 `native_review.rs` 的 candidate/prepared/chart/summary/task 编排，新增 b2 baseline reviewer。b2 reviewer 直接移植 Python `stock_select/reviewers/b2.py` 的评分、verdict、watch、comment 和 task context 口径，不恢复源 Python CLI bridge。

**Tech Stack:** Rust、serde_json、chrono、现有 prepared cache、现有 MACD trend core、Python golden artifacts under `~/.agents/skills/stock-select/runtime`。

---

## 当前 Golden

固定读取 Python 既有产物，不重算：

```text
python_root=~/.agents/skills/stock-select/runtime
pick_date=2026-05-25
method=b2
reviewed=139
recommendations=0
failures=0
```

## 文件结构

- Modify: `src/native_review.rs`
  - 增加 `Method::B2` 分支。
  - 抽出 b1/b2 共用的 review 编排 helper，避免复制 candidate/prepared/chart/summary/task 写入逻辑。
  - b2 task 使用 `references/prompt-b2.md`。
- Create: `src/reviewers/b2.rs`
  - b2 baseline reviewer 主入口。
  - 移植 `review_b2_symbol_history` 的 weak/neutral/strong/default 分支。
  - 输出 Python-compatible baseline JSON 字段。
- Create: `src/reviewers/b2_scoring.rs`
  - b2 trend/position/volume/previous abnormal/macd/overheat/verdict/watch scoring。
  - 公开小粒度函数供测试。
- Modify: `src/reviewers/mod.rs`
  - 导出 b2 reviewer/scoring 模块。
- Create: `tests/b2_reviewer_golden.rs`
  - 读取 Python per-stock review JSON，验证 Rust b2 baseline 字段。
- Modify: `docs/roadmap.md`
  - 每完成一个阶段更新 b2 原生化状态和验证结果。
- Modify: `AGENTS.md`
  - b2 完成后更新当前实现边界。

## Task 1: Golden Fixture Harness

- [x] **Step 1: 添加 b2 golden 测试骨架**

Create `tests/b2_reviewer_golden.rs` with a test that loads Python review JSON from:

```text
~/.agents/skills/stock-select/runtime/reviews/2026-05-25.b2
```

The test initially asserts the fixture set shape only:

```rust
#[test]
fn b2_python_golden_fixture_shape_is_stable() {
    let root = std::path::PathBuf::from(std::env::var("HOME").unwrap())
        .join(".agents/skills/stock-select/runtime/reviews/2026-05-25.b2");
    let summary: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("summary.json")).unwrap()).unwrap();
    assert_eq!(summary["reviewed_count"], 139);
    assert_eq!(summary["recommendations"].as_array().unwrap().len(), 0);
    assert_eq!(summary["failures"].as_array().unwrap().len(), 0);
}
```

- [x] **Step 2: 运行 fixture 测试**

Run:

```bash
cargo test --test b2_reviewer_golden -- --nocapture
```

Expected: PASS fixture shape.

- [x] **Step 3: 更新 roadmap**

In `docs/roadmap.md`, add:

```text
b2 native review progress: fixture harness ready; Python golden shape reviewed=139 recommendations=0 failures=0.
```

## Task 2: b2 Scoring Port

- [x] **Step 1: 新增 `src/reviewers/b2_scoring.rs`**

Implement direct Rust equivalents for:

```text
_score_b2_trend_structure
_score_b2_price_position
_score_b2_volume_behavior
_score_b2_previous_abnormal_move
_compute_b2_overheat_penalty
infer_b2_verdict
infer_b2_elastic_watch
score_b2_watch
infer_b2_watch_tier
```

Use `f64::NAN` checks and helper functions that mirror Python thresholds exactly.

- [x] **Step 2: 添加 focused unit tests**

Add unit tests in `tests/b2_review_scoring.rs` for stable threshold examples:

```rust
#[test]
fn b2_watch_score_matches_python_formula() {
    let score = score_b2_watch(B2WatchInput {
        verdict: "WATCH",
        total_score: 4.0,
        trend_structure: 4.0,
        price_position: 4.0,
        volume_behavior: 3.0,
        previous_abnormal_move: 5.0,
        macd_phase: 4.3,
        elastic_watch_reason: Some("mid_macd_elastic_watch"),
        signal: Some("B3"),
        signal_type: "trend_start",
    });
    assert_eq!(score, Some(74.6));
}
```

- [x] **Step 3: 运行 scoring tests**

Run:

```bash
cargo test --test b2_review_scoring -- --nocapture
```

Expected: PASS.

## Task 3: b2 Baseline Reviewer

- [x] **Step 1: 新增 `src/reviewers/b2.rs`**

Create:

```rust
pub struct B2ReviewInput<'a> {
    pub code: &'a str,
    pub pick_date: chrono::NaiveDate,
    pub history: &'a [crate::model::PreparedRow],
    pub chart_path: &'a std::path::Path,
    pub signal: Option<&'a str>,
    pub profile: &'a crate::environment_profiles::MethodEnvironmentProfile,
}

pub struct B2BaselineOutput {
    pub review: serde_json::Value,
    pub wave_context: crate::native_review::WaveTaskContext,
}

pub fn review_b2_symbol_history(input: B2ReviewInput<'_>) -> anyhow::Result<B2BaselineOutput>
```

The output JSON must include:

```text
code, pick_date, chart_path, review_type, trend_structure, price_position,
volume_behavior, previous_abnormal_move, macd_phase, total_score, signal,
signal_type, verdict, elastic_watch, elastic_watch_reason, watch_score,
watch_tier, comment
```

- [x] **Step 2: Compare baseline fields against Python golden**

Extend `tests/b2_reviewer_golden.rs` to call `review_b2_symbol_history` for each Python fixture and compare:

```text
trend_structure
price_position
volume_behavior
previous_abnormal_move
macd_phase
total_score
signal
signal_type
verdict
elastic_watch
elastic_watch_reason
watch_score
watch_tier
comment
```

- [x] **Step 3: Run golden test**

Run:

```bash
cargo test --test b2_reviewer_golden -- --nocapture
```

Expected: all 139 b2 fixtures match.

## Task 4: Native Review Integration

- [x] **Step 1: 接入 `Method::B2`**

Modify `src/native_review.rs`:

```rust
pub fn run_native_review(args: NativeReviewArgs) -> anyhow::Result<PathBuf> {
    match args.method {
        Method::B1 => run_native_method_review(args),
        Method::B2 => run_native_method_review(args),
        _ => anyhow::bail!("native review is currently implemented only for b1 and b2; method={}", args.method.as_str()),
    }
}
```

Use method-specific reviewer dispatch inside the shared loop.

- [x] **Step 2: b2 LLM task payload**

For b2 tasks:

```text
prompt_path=references/prompt-b2.md
rubric_path=references/review-rubric.md
input_mode=image
dispatch=subagent
weekly_wave_context
daily_wave_context
wave_combo_context
review_focus_context
environment_state
environment_reason
environment_llm_focus
rank
baseline_score
baseline_verdict
signal
```

- [x] **Step 3: Verify `--llm-min-baseline-score` and `--llm-review-limit`**

Run:

```bash
cargo run --quiet -- review --method b2 --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-b2-review-limit \
  --environment-state weak \
  --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱" \
  --llm-min-baseline-score 4.0 \
  --llm-review-limit 5
```

Expected: `llm_review_tasks.json` has at most 5 tasks and all task `baseline_score >= 4.0`.

## Task 5: End-to-End Parity

- [x] **Step 1: Run b2 full runtime in `/tmp`**

Run:

```bash
rm -rf /tmp/stock-select-rs-native-run-b2
cargo run --release -- run \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-native-run-b2 \
  --environment-state weak \
  --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱" \
  --recompute
```

- [x] **Step 2: Compare artifacts**

Run:

```bash
python3 scripts/compare_screen.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-native-run-b2 \
  --pick-date 2026-05-25 \
  --method b2

python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-native-run-b2 \
  --pick-date 2026-05-25 \
  --method b2

python3 scripts/check_charts.py \
  --runtime-root /tmp/stock-select-rs-native-run-b2 \
  --pick-date 2026-05-25 \
  --method b2
```

Expected:

```text
screen comparison PASS
review comparison PASS reviewed=139 recommendations=0
chart smoke PASS charts=139
```

- [x] **Step 3: Final verification**

Run:

```bash
cargo fmt --check
cargo test --quiet
python3 -m py_compile scripts/check_charts.py scripts/compare_screen.py scripts/compare_review.py scripts/render_charts.py
```

- [x] **Step 4: Update docs and commit**

Update `docs/roadmap.md` and `AGENTS.md`:

```text
review/run native methods: b1, b2
b2 golden parity: 2026-05-25 reviewed=139 recommendations=0
```

Commit:

```bash
git add src tests docs AGENTS.md
git commit -m "feat: add native b2 review parity"
```

## 实施结果

```text
status=completed
verified_pick_date=2026-05-25
method=b2
runtime_root=/tmp/stock-select-rs-native-run-b2
reviewed=139
recommendations=0
charts=139
```

最终验证：

```text
PASS screen comparison method=b2 pick_date=2026-05-25 candidates=139/139
PASS review comparison method=b2 pick_date=2026-05-25 reviewed=139 recommendations=0
PASS chart smoke method=b2 pick_date=2026-05-25 charts=139
```

实现说明：原计划中的独立 `src/reviewers/b2.rs` 未单独创建，b2 baseline reviewer 接入在现有 `src/native_review.rs` 的共享编排内；小粒度 scoring helper 落在 `src/reviewers/b2_scoring.rs`。这个结构沿用了 b1 当前实现边界，避免在 parity 收敛时做额外模块搬迁。

## Self-Review

- Spec coverage: covers b2 review, run integration, task filtering/limit, LLM merge, and parity validation.
- Placeholder scan: no `TBD` or intentionally vague implementation step remains.
- Type consistency: public names follow current Rust module style；b2 reviewer 主流程保留在 `native_review` 内，后续如继续抽象 reviewers 可另起重构。
