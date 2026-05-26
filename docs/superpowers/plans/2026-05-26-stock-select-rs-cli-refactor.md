# stock-select-rs CLI Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve `stock-select-rs` from a fast `screen` prototype into a CLI-compatible replacement path whose user workflow and final artifacts match the Python `stock-select` CLI.

**Architecture:** Keep `screen` as the Rust-native foundation and validate it against Python golden artifacts before expanding. Add a temporary hybrid `run` command that uses Rust `screen` and delegates chart/review to the Python CLI, then replace chart and review only after their outputs have golden tests.

**Tech Stack:** Rust 2024, Python 3 via the existing `/home/pi/Documents/agents/stock-select` project, PostgreSQL through `POSTGRES_DSN`, shell-driven golden comparison scripts, `cargo test`, `uv run stock-select`.

---

## File Structure

- `scripts/compare_screen.py`: runs or compares Python/Rust screen outputs for one or more dates and methods.
- `scripts/compare_review.py`: compares Python/Rust review output directories after baseline review.
- `src/cli.rs`: add `run`, Python bridge options, and stage timing.
- `src/python_bridge.rs`: execute Python CLI commands with inherited DSN/runtime arguments.
- `src/lib.rs`: export `python_bridge`.
- `tests/cli_args.rs`: lightweight CLI command construction and Python bridge tests without invoking real DB.
- `docs/superpowers/plans/2026-05-26-stock-select-rs-cli-refactor.md`: this plan.

## Task 1: Golden Screen Comparison Script

**Files:**
- Create: `scripts/compare_screen.py`

- [ ] **Step 1: Add a comparison script**

Create `scripts/compare_screen.py` with arguments:

```text
--python-root PATH
--rust-root PATH
--pick-date YYYY-MM-DD
--method b1
--check-review-summary
```

The script reads:

```text
<root>/candidates/<pick_date>.<method>.json
```

and compares candidate code set, `close`, `turnover_n`, `yellow_b1` for b1, `signal` for b2, and Python-required top-level fields.

- [ ] **Step 2: Run against existing b1 artifacts**

Run:

```bash
python3 scripts/compare_screen.py \
  --python-root /tmp/stock-select-compare-python \
  --rust-root /tmp/stock-select-align-rust \
  --pick-date 2026-05-25 \
  --method b1
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/compare_screen.py docs/superpowers/plans/2026-05-26-stock-select-rs-cli-refactor.md
git commit -m "test: add screen golden comparison script"
```

## Task 2: Multi-Date b1 Regression

**Files:**
- Modify: `scripts/compare_screen.py`

- [ ] **Step 1: Add optional Rust command execution**

Add optional arguments:

```text
--run-rust-screen
--rust-bin target/release/stock-select-rs
```

Python golden artifacts are read from `~/.agents/skills/stock-select/runtime` by default and must not be recomputed during this task. When `--run-rust-screen` is enabled, the script removes the Rust runtime root, runs Rust `screen --recompute`, then compares artifacts against the existing Python runtime.

- [ ] **Step 2: Run b1 for at least three dates**

Use:

```bash
for d in 2026-05-25 2026-05-22 2026-05-21; do
  python3 scripts/compare_screen.py \
    --python-root ~/.agents/skills/stock-select/runtime \
    --rust-root /tmp/stock-select-reg-rust-$d \
    --pick-date $d \
    --method b1 \
    --run-rust-screen
done
```

Expected: all PASS. If a date fails, inspect missing/extra codes and fix Rust b1 before moving on.

- [ ] **Step 3: Commit**

```bash
git add scripts/compare_screen.py src
git commit -m "test: add multi-date b1 screen regression"
```

## Task 3: Hybrid Run Command

**Files:**
- Create: `src/python_bridge.rs`
- Modify: `src/lib.rs`
- Modify: `src/cli.rs`
- Create: `tests/cli_args.rs`

- [x] **Step 1: Add Python bridge**

Implement a bridge that runs:

```text
uv run stock-select chart --method METHOD --pick-date DATE --runtime-root ROOT
uv run stock-select review --method METHOD --pick-date DATE --runtime-root ROOT
```

with working directory `/home/pi/Documents/agents/stock-select`, inherited `POSTGRES_DSN`, and optional `--environment-state` / `--environment-reason` forwarding for review.

- [x] **Step 2: Add `run` command**

`stock-select-rs run` should accept the same core options as `screen`:

```text
--method
--pick-date
--dsn
--runtime-root
--recompute
--environment-state
--environment-reason
```

It executes:

```text
Rust screen -> Python chart -> Python review
```

and prints stage elapsed time to stderr.

- [x] **Step 3: Add unit tests for command construction**

Tests verify bridge command arguments for chart/review and that `run` rejects unsupported methods through existing method parsing.

- [x] **Step 4: Run a full hybrid b1 run**

Run:

```bash
rm -rf /tmp/stock-select-rs-run-b1
cargo run --release -- run \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-run-b1 \
  --environment-state weak \
  --environment-reason "match python scheduled weak env"
```

Expected: candidates, charts, reviews, `summary.json`, and `llm_review_tasks.json` exist.

- [x] **Step 5: Commit**

```bash
git add src tests
git commit -m "feat: add hybrid run command"
```

## Task 4: Review Artifact Comparison

**Files:**
- Create: `scripts/compare_review.py`

- [x] **Step 1: Add review comparison script**

Compare:

```text
reviews/<pick_date>.<method>/*.json
reviews/<pick_date>.<method>/summary.json
reviews/<pick_date>.<method>/llm_review_tasks.json
```

For b1, assert `total_score`, `verdict`, `signal_type`, `yellow_b1`, recommendation codes, and task baseline fields match.

- [x] **Step 2: Compare Python run vs hybrid Rust run**

Run Python `run` and Rust hybrid `run` into separate temp roots, then:

```bash
python3 scripts/compare_screen.py --python-root PY_ROOT --rust-root RS_ROOT --pick-date 2026-05-25 --method b1
python3 scripts/compare_review.py --python-root PY_ROOT --rust-root RS_ROOT --pick-date 2026-05-25 --method b1
```

Expected: both PASS.

- [x] **Step 3: Commit**

```bash
git add scripts/compare_review.py
git commit -m "test: add review golden comparison script"
```

## Task 5: Chart Bridge Replacement Planning Gate

**Files:**
- Create: `docs/superpowers/specs/2026-05-26-chart-bridge-design.md`

- [x] **Step 1: Write chart bridge design**

Specify whether the next chart phase uses:

```text
Rust Command -> uv run python bridge
```

or:

```text
Rust pyo3 embedded Python -> mplfinance
```

Acceptance requires PNG file count, filenames, and visual smoke parity for b1 candidates.

- [x] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-26-chart-bridge-design.md
git commit -m "docs: add chart bridge design"
```

## Task 6: Review Rust Port Planning Gate

**Files:**
- Create: `docs/superpowers/specs/2026-05-26-review-rust-port-design.md`

- [ ] **Step 1: Write review port design**

Map Python modules to Rust modules:

```text
review_protocol.py -> src/review_protocol.rs
review_resolvers.py -> src/review_resolvers.rs
reviewers/b1.py -> src/reviewers/b1.rs
analysis/macd_waves.py -> src/analysis/macd_waves.rs
```

Acceptance requires per-stock golden parity before replacing Python review in `run`.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-26-review-rust-port-design.md
git commit -m "docs: add review rust port design"
```

## Self-Review

- Spec coverage: the plan covers screen regression, hybrid run, review artifact comparison, and planning gates for chart/review native migration.
- Scope control: it does not start native chart/review implementation until screen/run parity is testable.
- Placeholder scan: every task has concrete files, commands, and expected outcomes.
