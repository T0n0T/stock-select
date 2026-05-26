# stock-select-rs 路线图

## 目标

记录 `/home/pi/Documents/agents/stock-select` Rust 重构进展，并给出继续推进 b1 Rust CLI 原生化的执行路径。后续文档默认使用中文，代码符号、命令和字段名保留原始英文。

## 当前快照

日期：2026-05-26

当前 checkpoint：

```text
latest commit: 55e5b16 docs: add rust refactor roadmap
working tree: 包含文档更新和当前 Phase 1 测试新增改动
```

项目正在推进 b1 Rust-native review。后续实现任务不要重算 Python golden，应直接读取既有 Python 产物：

```text
~/.agents/skills/stock-select/runtime
```

当前已完成的最近目标：

```text
已新增 2026-05-25.b1 全量 b1 decision fixture harness。
```

该测试验证 Rust b1 decision core 在 104 个 Python baseline-reviewed candidates 上与 Python 完全一致。下一步进入原生 OHLCV review score 输入计算层。

## 当前架构

Rust CLI 当前仍是混合替代路径：

```text
stock-select-rs screen  -> Rust native
stock-select-rs chart   -> Rust CLI bridge to Python chart
stock-select-rs review  -> Rust CLI bridge to Python review
stock-select-rs run     -> Rust screen + Python chart + Python review
```

不要把 `review` 或 `run` 当作 Rust-native review。它们当前是 CLI-compatible workflow，但 review 执行仍委托 Python，直到后续新增并验证 native 路径。

面向用户的 runtime layout 已与 Python 对齐：

```text
candidates/<pick_date>.<method>.json
charts/<pick_date>.<method>/<code>_day.png
reviews/<pick_date>.<method>/<code>.json
reviews/<pick_date>.<method>/summary.json
reviews/<pick_date>.<method>/llm_review_tasks.json
```

## 已验证 b1 对齐情况

Python golden artifacts 读取路径：

```text
~/.agents/skills/stock-select/runtime
```

除非用户明确要求，不要重算 Python 输出。

已验证 b1 screen parity：

```text
2026-05-25: 104/104
2026-05-22: 114/114
2026-05-21: 137/137
2026-05-20: 117/117
2026-05-19: 108/108
```

已通过 Rust CLI bridge 验证 b1 review parity：

```text
pick_date=2026-05-25
reviewed=104
recommendations=3
recommendation codes=000066.SZ,300292.SZ,301290.SZ
```

已通过 `stock-select-rs run --method b1` 端到端临时路径验证：

```text
runtime_root=/tmp/stock-select-rs-b1-run-final
screen comparison: PASS candidates=104/104
review comparison: PASS reviewed=104 recommendations=3
chart smoke: PASS charts=104
```

注意：当前 `run` 的 review 阶段仍通过 Python bridge 执行；本次验证证明 Rust CLI 用户流程和最终 artifacts 已与 Python baseline 对齐，不代表 b1 review 已完全 Rust-native。

代表性验证命令：

```bash
rm -rf /tmp/stock-select-rs-review-cli-b1

cargo run --release -- screen \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-review-cli-b1 \
  --recompute

cargo run --release -- chart \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-review-cli-b1

cargo run --release -- review \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-review-cli-b1 \
  --environment-state weak \
  --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱"

python3 scripts/compare_screen.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-review-cli-b1 \
  --pick-date 2026-05-25 \
  --method b1

python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-review-cli-b1 \
  --pick-date 2026-05-25 \
  --method b1
```

预期输出：

```text
PASS screen comparison method=b1 pick_date=2026-05-25 candidates=104/104
PASS review comparison method=b1 pick_date=2026-05-25 reviewed=104 recommendations=3
```

## 已完成 Rust-native 工作

本节记录已经可以直接复用的 Rust 实现。

### Screen

Rust-native screen 已包含：

- PostgreSQL `daily_market` loading.
- Prepared indicator cache under `prepared/*.bin` plus `*.meta.json`.
- b1/b2/dribull screen candidate generation.
- b1 candidate ordering aligned with Python by code ascending.
- turnover-top pool alignment with Python defaults.

已处理的重要 b1 对齐细节：

- preserve DB NULL OHLCV rows as NaN-like values during preparation semantics
- pandas-like rolling window invalidation
- pandas `ewm(adjust=False)` behavior after NaN gaps
- KDJ RSV invalid fallback to `0.0`
- weekly close aggregation using last non-NaN close while retaining last row date
- default pool source `turnover-top`, including `ma25 > ma60` and top 5000 by `turnover_n`

### CLI Bridge

Rust CLI 当前暴露：

```text
screen
chart
review
run
```

`chart`、`review` 和 `run` 在 Rust native 尚未完成的阶段桥接 Python。`review` 和 `run` 会转发：

```text
--dsn
--environment-state
--environment-reason
--llm-min-baseline-score
--llm-review-limit
```

### Chart

Rust CLI 已有 `chart` command，但 chart rendering 仍由 Python 执行：

```text
Rust Command -> uv run stock-select chart
```

Rust CLI 生成路径下的 chart artifacts 已 smoke-check 为真实 PNG。既有 Python runtime 中 `2026-05-25.b1` 的 chart 文件存在 placeholder text artifacts，因此不能作为 PNG visual golden。

### Review Core

Rust-native review 已有基础：

- `src/environment_profiles.rs`
  - b1/b2 weak/neutral/strong profile constants
  - weights, thresholds, subscore modes, and `llm_focus`
- `src/review_protocol.rs`
  - baseline score weighting
  - b1/b2 score weighting
  - profile-aware score weighting
  - signal type and verdict helpers
  - Python-compatible two-decimal float formatting behavior
- `src/reviewers/b1.rs`
  - b1 decision core for final baseline decision fields
  - score combo key
  - high-return combo classification
  - pass family/tier classification
  - environment verdict gate
  - score layer and calibrated total score

当前 b1 native decision core 已通过代表性 Python baseline 样本验证：

```text
000066.SZ exact distribution PASS-B total_score=4.78
runup-over-limit exact distribution WATCH-A total_score=4.32
300166.SZ rebound near WATCH-C total_score=3.54
002428.SZ non-family rebound FAIL total_score=2.91
```

decision core 的范围刻意小于完整 review。它假设以下输入已经计算完成：

```text
signal_type
trend_structure
price_position
volume_behavior
previous_abnormal_move
macd_phase
raw_total_score
environment_state
gate_flags
```

当前已新增全量 Python baseline fixture，并验证 2026-05-25.b1 的 104 个样本全部通过。下一步是移植 score-input computation。

新增测试：

```text
tests/b1_reviewer_decision_golden.rs
```

验证结果：

```text
cargo test --test b1_reviewer_decision_golden -- --nocapture
PASS: 104/104 b1 decision fixtures match Python for 2026-05-25
```

## 已知缺口

### Review 尚未完全原生化

`stock-select-rs review` 仍把完整逐股 review 执行委托给 Python。Rust-native 代码目前可以在拿到相同输入后决定最终 b1 字段，但尚未从 OHLCV 历史数据原生计算所有必要输入。

缺失的 b1 native 部分：

- one-year per-candidate history loading for review
- review prepared frame construction
- b1 trend structure score
- b1 price position score
- b1 volume behavior score
- previous abnormal move score
- MACD wave classification
- MACD phase score and divergence penalty
- environment gate metrics:
  - cooldown flags
  - below MA25
  - runup percent
  - sideways amplitude
  - weekly MACD cooldown
- comment generation
- `llm_review_tasks.json` task context generation
- summary/recommendation writer

### Environment Profile 状态

Python 当前仍负责自动 market environment resolution 和 profile application。

Rust 当前支持：

- profile constants
- profile-aware scoring helpers
- manual environment forwarding to Python review

Rust 尚不支持：

- automatic market environment evaluation
- runtime `environment/history.jsonl` resolution
- environment daily/latest file writing

当前做 parity 验证时应继续显式传入环境：

```bash
--environment-state weak \
--environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱"
```

### Chart 状态

Chart rendering 仍由 Python 执行。在 review parity 原生化稳定、chart visual smoke tests 更充分之前，先保持该策略。

Rust CLI `chart` command 当前作为稳定 workflow entrypoint，并桥接到：

```text
uv run stock-select chart
```

`2026-05-25` Python runtime chart files 不是可靠 PNG golden set，因为历史文件中存在 placeholder text artifacts。Chart validation 应使用新的 Rust runtime 临时目录和 PNG smoke checks。

## 下一步路线图

### Phase 1：b1 Review Fixture Harness（已完成）

目标：将 Rust-native b1 decision core 与所有 Python baseline review artifact 对比。

为什么先做这一层：

```text
b1 final decision logic 已经完成移植。继续增加 native scoring code 之前，先用完整 Python baseline corpus 锁定 decision layer，这样后续失败可以定位在输入评分层，而不是最终分类层。
```

任务状态：

1. 已新增 `reviews/2026-05-25.b1/*.json` fixture loader。
2. 已从每个 Python baseline review 提取：
   - `signal_type`
   - `trend_structure`
   - `price_position`
   - `volume_behavior`
   - `previous_abnormal_move`
   - `macd_phase`
   - `raw_total_score`
   - `gate_flags`
   - `environment_state`
3. 已将这些值输入 `decide_b1_review`。
4. 已断言 Rust output 匹配 Python：
   - `score_combo_key`
   - `high_return_combo_match`
   - `pass_family`
   - `pass_family_tier`
   - `verdict`
   - `total_score`
   - `score_layer`
   - `score_layer_score`

验收结果：

```text
PASS: 104/104 b1 decision fixtures match Python for 2026-05-25
```

实现文件：

```text
tests/b1_reviewer_decision_golden.rs
src/reviewers/b1.rs
```

fixture test 直接读取 `~/.agents/skills/stock-select/runtime/reviews/2026-05-25.b1/` 下的 Python review JSON，并跳过 `summary.json`、`llm_review_tasks.json` 等非个股支持文件。

### Phase 2：Native b1 History Scoring

目标：从 OHLCV history 原生计算 b1 input scores。

当前进展：

```text
已新增 src/reviewers/b1_scoring.rs，完成第一批不依赖数据库的 b1 评分纯函数：
- compute_bbi
- score_b1_trend_structure
- score_b1_price_position
- score_b1_volume_behavior
- score_b1_previous_abnormal_move
- compute_b1_environment_gate（已覆盖 daily cooldown、below_ma25、runup、sideways；weekly slope / weekly MACD cooldown 后续接 MACD wave 阶段）
- b1_raw_total_score
```

新增测试：

```text
tests/b1_review_scoring.rs
```

下一步应继续把这些纯函数接入真实 candidate history，并补全：

```text
MACD phase / wave context
weekly environment gate metrics
```

建议顺序：

1. Fetch one-year candidate histories in Rust.
2. Port or reuse MA25, BBI, zxdq/zxdkx, MACD helpers.
3. Implement and fixture-test:
   - trend structure
   - price position
   - volume behavior
   - previous abnormal move
4. Keep each score function independently tested before composing the full reviewer.

验收标准：

```text
For 2026-05-25 b1, all 104 symbols match Python baseline score fields.
```

推荐执行方式：

```text
1. Add score field fixtures from Python JSON.
2. Implement one score function at a time.
3. Compare only that field before composing the full native reviewer.
4. Keep the Python bridge as the CLI default during this phase.
```

### Phase 3: MACD Wave Port

目标：移植 Python `analysis/macd_waves.py` 和 b1 MACD phase logic。

任务：

1. Implement MACD state machine structs.
2. Implement daily MACD trend classification.
3. Implement weekly aggregation and weekly MACD trend classification.
4. Generate text context:
   - `weekly_wave_context`
   - `daily_wave_context`
   - `wave_combo_context`
5. Match Python reason strings where they affect comments/tasks.

验收标准：

```text
For 2026-05-25 b1, all 104 symbols match Python macd_phase and wave task context.
```

参考源码：

```text
/home/pi/Documents/agents/stock-select/src/stock_select/analysis/macd_waves.py
```

### Phase 4：Native b1 Review Command

目标：在切换默认行为前，先通过显式选项增加 native Rust review path。

拟定 CLI：

```bash
stock-select-rs review \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-native-review-b1 \
  --environment-state weak \
  --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱" \
  --native
```

验收标准：

```text
python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root /tmp/stock-select-rs-native-review-b1 \
  --pick-date 2026-05-25 \
  --method b1

PASS review comparison method=b1 pick_date=2026-05-25 reviewed=104 recommendations=3
```

在 full comparison 通过前，native path 可以与 Python bridge 共存。本阶段不要切换 `run` 默认行为。

### Phase 5：切换 b1 run Review 默认路径

只有 native b1 review 通过 full golden comparison 后才执行：

- make `stock-select-rs review --method b1` native by default
- keep Python bridge behind an explicit fallback option
- update `stock-select-rs run --method b1` to use native review

最终验收：

```text
stock-select-rs run --method b1 uses Rust screen + Rust native review by default,
and compare_review.py still reports 104 reviewed candidates and 3 recommendations
for 2026-05-25.
```

## 实现约束

- b1 native review 开发期间不要重算 Python golden artifacts。
- parity validation 使用 `/tmp` 下的 Rust runtime 临时目录。
- `prepare cache` 内部可以不同于 Python，但 CLI 使用方式和最终 runtime artifacts 必须保持一致。
- review parity 稳定前保持 `chart` bridged。
- 改默认行为前，先通过显式 opt-in 增加 native b1 review。
- parity test 失败时按层对比：
  - candidate set
  - score input fields
  - MACD wave context
  - gate flags
  - final decision fields
  - summary/recommendation fields

## 验证基线

声明阶段性进展前运行：

```bash
cargo fmt --check
cargo test --quiet
python3 -m py_compile scripts/check_charts.py scripts/compare_screen.py scripts/compare_review.py
```

做 b1 CLI parity 时运行：

```bash
python3 scripts/compare_screen.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root <rust-runtime-root> \
  --pick-date 2026-05-25 \
  --method b1

python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root <rust-runtime-root> \
  --pick-date 2026-05-25 \
  --method b1
```

## 最近提交记录

```text
fbbb1fc feat: add b1 reviewer decision core
c989bf4 feat: add review command bridge
7c86956 feat: add review profile scoring core
c5805c0 feat: add chart command bridge
46b3003 docs: add review rust port design
1e93035 docs: add chart bridge design
c8b14be test: add review golden comparison script
4d23d46 feat: add hybrid run command
56262ea test: add multi-date b1 screen regression
2683a51 test: add screen golden comparison script
```
