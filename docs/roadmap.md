# stock-select-rs 路线图

## 目标

记录 `/home/pi/Documents/agents/stock-select` Rust 重构进展，并给出继续推进 b1 Rust CLI 原生化的执行路径。后续文档默认使用中文，代码符号、命令和字段名保留原始英文。

## 当前快照

日期：2026-05-27

当前 checkpoint：

```text
latest commit: c6ddc8b feat: move chart rendering into rust repo
working tree: 移除源 Python CLI bridge，review/run 强制走 Rust native，待提交
```

项目正在推进 b1 Rust-native end-to-end。后续实现任务不要重算 Python golden，应直接读取既有 Python 产物：

```text
~/.agents/skills/stock-select/runtime
```

当前已完成的最近目标：

```text
stock-select-rs run --method b1 已使用 Rust native review 输出与 Python baseline 完全一致的 artifacts。
stock-select-rs chart 已改为本仓库内置 runner，不再调用源 Python CLI 项目。
stock-select-rs review/run 不再回退到源 Python CLI bridge。
```

2026-05-25.b1 已验证 104 个 baseline review、3 个 recommendations 与 Python golden 一致。chart PNG 由 `scripts/render_charts.py` 在本仓库内生成。

## 当前架构

Rust CLI 当前生产路径：

```text
stock-select-rs screen  -> Rust native
stock-select-rs chart   -> Rust prepared cache + 本仓库 Python/mplfinance runner
stock-select-rs review  -> Rust native review
stock-select-rs run     -> Rust screen + 本仓库 chart runner + Rust native review
```

`chart` 不再调用 `/home/pi/Documents/agents/stock-select` 的 Python CLI；它仍使用 Python 绘图库 `mplfinance/matplotlib`，但脚本和输入数据都在本仓库控制。`review` 和 `run` 不再委托源 Python CLI。当前只有 b1 review 完成 Rust native parity；b2 / dribull / hcr 的 review 会显式返回未实现错误。

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

已通过 Rust native b1 review parity：

```text
pick_date=2026-05-25
reviewed=104
recommendations=3
recommendation codes=000066.SZ,300292.SZ,301290.SZ
```

已通过 `stock-select-rs run --method b1` 端到端临时路径验证：

```text
runtime_root=/tmp/stock-select-rs-local-chart-run-b1
screen comparison: PASS candidates=104/104
review comparison: PASS reviewed=104 recommendations=3
chart smoke: PASS charts=104
run elapsed=74.051s
```

注意：当前 `run` 的 chart 阶段仍使用 Python/mplfinance 绘图库，但不再通过源 Python CLI bridge。

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

`chart` 已迁到本仓库 runner。`review` 和 `run` 只走 Rust native review；当前 b1 可用，其他方法会显式报未实现。`review` 和 `run` 会处理：

```text
--dsn
--environment-state
--environment-reason
--llm-min-baseline-score
--llm-review-limit
```

### Chart

Rust CLI 已有 `chart` command，当前 chart 渲染路径为：

```text
Rust Command -> 读取 runtime prepared/candidates -> 写 charts/*.payload.json -> uv run scripts/render_charts.py
```

`scripts/render_charts.py` 使用 PEP 723 inline dependencies 声明 `pandas`、`matplotlib`、`mplfinance`，不依赖源 Python CLI 项目的 `pyproject.toml` 或虚拟环境。

Rust CLI 生成路径下的 chart artifacts 已 smoke-check 为真实 PNG。既有 Python runtime 中 `2026-05-25.b1` 的 chart 文件存在 placeholder text artifacts，因此不能作为 PNG visual golden。

本阶段验证：

```text
runtime_root=/tmp/stock-select-rs-local-chart-run-b1
python3 scripts/check_charts.py --runtime-root /tmp/stock-select-rs-local-chart-run-b1 --pick-date 2026-05-25 --method b1
PASS chart smoke method=b1 pick_date=2026-05-25 charts=104
```

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
- `src/reviewers/b1_scoring.rs`
  - b1 trend/position/volume/previous abnormal move/environment gate 原生评分
- `src/macd_trends.rs`
  - b1 使用的 MACD state machine、weekly/daily trend classification、dual-period phase score
- `src/native_review.rs`
  - 读取 candidate/prepared cache
  - 写 per-stock review JSON、`summary.json`、`llm_review_tasks.json`
  - b1 watch reason/score/tier、wave task context 与 Python 对齐

当前 b1 native review 已通过 2026-05-25 全量 Python baseline parity：

```text
cargo fmt --check
cargo test --quiet
python3 scripts/compare_screen.py --python-root ~/.agents/skills/stock-select/runtime --rust-root /tmp/stock-select-rs-native-run-b1 --pick-date 2026-05-25 --method b1
python3 scripts/compare_review.py --python-root ~/.agents/skills/stock-select/runtime --rust-root /tmp/stock-select-rs-native-run-b1 --pick-date 2026-05-25 --method b1
python3 scripts/check_charts.py --runtime-root /tmp/stock-select-rs-native-run-b1 --pick-date 2026-05-25 --method b1
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

### Review 原生化状态

b1 review 已完成 Rust native parity。`stock-select-rs review --method b1` 与 `stock-select-rs run --method b1` 会输出与 Python CLI 一致的 baseline review、summary、LLM task artifacts。

仍未原生化的 review 范围：

- b2 / dribull / hcr review 尚未移植；CLI 不再回退到 Python bridge，会显式报错
- b1 自动 market environment resolution 尚未移植
- b1 weekly slope / weekly MACD cooldown 当前对 2026-05-25 golden 为 `null/false`，后续多日期验证时需要继续补强
- b1 comment 已满足当前 compare 脚本与 task context 对齐，但如后续要逐字比对 per-stock `comment`，需要补全 Python 中周 MACD 红柱、水上、背离、近 3 日死叉描述片段

### Environment Profile 状态

Python 当前仍负责自动 market environment resolution；Rust b1 native review 已支持 manual profile application。

Rust 当前支持：

- profile constants
- profile-aware scoring helpers
- manual environment state/reason
- b1 native review 使用 profile weights/subscore mode/llm_focus

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

Chart rendering 已从源 Python CLI bridge 迁到本仓库。当前仍使用 Python/mplfinance 绘图库，但执行入口、输入 payload 和 runtime 写入都由 Rust 仓库控制。

Rust CLI `chart` command 当前作为稳定 workflow entrypoint，调用：

```text
uv run scripts/render_charts.py --input <runtime>/charts/<pick_date>.<method>.payload.json
```

`2026-05-25` Python runtime chart files 不是可靠 PNG golden set，因为历史文件中存在 placeholder text artifacts。Chart validation 应使用新的 Rust runtime 临时目录和 PNG smoke checks。

后续可选增强：

- 将 chart payload 临时文件改为缓存可复用或运行后清理
- 对 PNG 做尺寸/非空像素/关键 panel 存在性检查
- 若要完全去 Python 运行时，再另起阶段做纯 Rust 绘图

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
已完成并接入 src/reviewers/b1_scoring.rs：
- compute_bbi
- score_b1_trend_structure
- score_b1_price_position
- score_b1_volume_behavior
- score_b1_previous_abnormal_move
- compute_b1_environment_gate（已覆盖 daily cooldown、below_ma25、runup、sideways）
- b1_raw_total_score
```

新增测试：

```text
tests/b1_review_scoring.rs
```

验收标准：

```text
For 2026-05-25 b1, all 104 symbols match Python baseline score fields.
已通过。
```

推荐执行方式：

```text
1. Add score field fixtures from Python JSON.
2. Implement one score function at a time.
3. Compare only that field before composing the full native reviewer.
4. 历史策略曾允许 Python bridge 作为 CLI 默认；当前生产代码已移除该 bridge。
```

### Phase 3: MACD Wave Port

目标：移植 Python `analysis/macd_waves.py` 和 b1 MACD phase logic。

当前状态：

```text
已新增 src/macd_trends.rs，并接入 native b1 review。
已修正 pandas resample("W-FRI") 对未完成周的排除行为。
```

验收标准：

```text
For 2026-05-25 b1, all 104 symbols match Python macd_phase and wave task context.
已通过 compare_review.py。
```

参考源码：

```text
/home/pi/Documents/agents/stock-select/src/stock_select/analysis/macd_waves.py
```

### Phase 4：Native b1 Review Command

目标：在切换默认行为前，先通过显式选项增加 native Rust review path。

当前状态：已完成。

拟定 CLI：

```bash
stock-select-rs review \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-native-review-b1 \
  --environment-state weak \
  --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱"
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

当前状态已更新：源 Python CLI bridge 已移除，`review` 默认即为 Rust native。

### Phase 5：切换 b1 run Review 默认路径

当前状态：已完成 `run` review 阶段切换为 Rust native。

保留策略：

- `review --method b1` 默认使用 native review
- `run --method b1` 默认使用 native review
- 其他方法 review 尚未移植，显式报错
- 不保留源 Python CLI bridge fallback

最终验收：

```text
stock-select-rs run --method b1 uses Rust screen + Rust native review by default,
and compare_review.py still reports 104 reviewed candidates and 3 recommendations
for 2026-05-25.
已通过。
```

## 实现约束

- b1 native review 开发期间不要重算 Python golden artifacts。
- parity validation 使用 `/tmp` 下的 Rust runtime 临时目录。
- `prepare cache` 内部可以不同于 Python，但 CLI 使用方式和最终 runtime artifacts 必须保持一致。
- chart 当前不再依赖源 Python CLI 项目；不要重新引入 `/home/pi/Documents/agents/stock-select` 的 chart bridge。
- review/run 已默认使用 Rust native review；不要重新加入源 Python CLI fallback。
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
python3 -m py_compile scripts/check_charts.py scripts/compare_screen.py scripts/compare_review.py scripts/render_charts.py
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
