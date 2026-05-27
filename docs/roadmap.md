# stock-select-rs 路线图

## 目标

记录 `/home/pi/Documents/agents/stock-select` Rust 重构进展，并给出继续推进 b1 Rust CLI 原生化的执行路径。后续文档默认使用中文，代码符号、命令和字段名保留原始英文。

## 当前快照

日期：2026-05-27

当前 checkpoint：

```text
latest commit: 9feff66 feat: add native b2 review parity
working tree: Rust 原生自动环境评估与 custom-pool 已验证，待提交
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
stock-select-rs review/run 已接入 Rust 原生 environment resolution：手动环境优先，缺省时读取或生成 runtime/environment。
stock-select-rs screen/run 已支持 custom-pool，与 Python CLI 的路径优先级和 prepared universe 交集规则对齐。
```

2026-05-25.b1 已验证 104 个 baseline review、3 个 recommendations 与 Python golden 一致。chart PNG 由 `scripts/render_charts.py` 在本仓库内生成。

当前最近完成的目标：

```text
b2 Rust native review parity
golden pick_date=2026-05-25 method=b2
python reviewed=139 recommendations=0 failures=0 llm_tasks=5
plan=docs/superpowers/plans/2026-05-27-b2-native-review.md
progress=Task 1-5 completed；b2 screen/review/run 已通过 2026-05-25 Python golden parity 与 chart smoke
```

## 当前架构

Rust CLI 当前生产路径：

```text
stock-select-rs screen  -> Rust native
stock-select-rs chart   -> Rust prepared cache + 本仓库 Python/mplfinance runner
stock-select-rs review  -> Rust native review
stock-select-rs run     -> Rust screen + Rust native review + 条件式 chart runner
```

`chart` 不再调用 `/home/pi/Documents/agents/stock-select` 的 Python CLI；它仍使用 Python 绘图库 `mplfinance/matplotlib`，但脚本和输入数据都在本仓库控制。Rust 会按 `--chart-workers` 把待绘图股票分片，并发启动多个本仓库 `scripts/render_charts.py` 进程。`run` 默认先完成 screen + review；只有传入 `--llm-review-limit` 或 `--llm-min-baseline-score` 时才进入 chart 阶段，且只绘制最终 `llm_review_tasks.json` 中需要给 LLM/subagent 查看图像的股票。`review` 和 `run` 不再委托源 Python CLI。当前 b1、b2 review/run 已完成 Rust native parity；dribull / hcr 的 review 会显式返回未实现错误。

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

注意：当前 `run` 的 chart 阶段仍使用 Python/mplfinance 绘图库，但不再通过源 Python CLI bridge；且只有配置 LLM review 限制时才触发 chart。

## b2 原生化进度

目标：`stock-select-rs review/run --method b2` 走 Rust native review，并与 Python `2026-05-25.b2` baseline artifacts 全量一致。

当前 golden：

```text
python_root=~/.agents/skills/stock-select/runtime
pick_date=2026-05-25
method=b2
reviewed=139
recommendations=0
failures=0
llm_review_tasks=5
```

实施计划：

```text
docs/superpowers/plans/2026-05-27-b2-native-review.md
```

进度：

```text
Task 1: golden fixture harness - completed
Task 2: b2 scoring port - completed，score subfields/watch/verdict/selection score 已对齐
Task 3: b2 baseline reviewer - completed，CLI 可输出与 Python golden 一致的 b2 review artifacts
Task 4: native_review b2 integration - completed，screen parity、LLM task limit、LLM merge、task context 已对齐
Task 5: b2 run parity validation - completed
```

已验证：

```text
cargo test --test b2_reviewer_golden -- --nocapture
PASS b2_python_golden_fixture_shape_is_stable

cargo test --test b2_review_scoring -- --nocapture
PASS 7 b2 scoring tests

cargo run --release -- run --method b2 --pick-date 2026-05-25 --runtime-root /tmp/stock-select-rs-b2-native-wip --environment-state weak --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱" --recompute
WIP completed: screen=147 candidates, chart=147 PNG, review completed

python3 scripts/compare_screen.py --python-root ~/.agents/skills/stock-select/runtime --rust-root /tmp/stock-select-rs-b2-native-wip --pick-date 2026-05-25 --method b2
FAIL only_rust=['300458.SZ', '300474.SZ', '301267.SZ', '600508.SH', '600985.SH', '603289.SH', '688286.SH', '920139.BJ']

After ST/LT b2 screen fix:
python3 scripts/compare_screen.py --python-root ~/.agents/skills/stock-select/runtime --rust-root /tmp/stock-select-rs-b2-screen-fix --pick-date 2026-05-25 --method b2
PASS screen comparison method=b2 pick_date=2026-05-25 candidates=139/139

After b2 review native WIP:
cargo run --release -- review --method b2 --pick-date 2026-05-25 --runtime-root /tmp/stock-select-rs-b2-screen-fix --environment-state weak --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱" --llm-review-limit 5
review completed

cargo test --test b2_reviewer_golden -- --nocapture
PASS 1 fixture shape test

cargo test --test b2_review_scoring -- --nocapture
PASS 7 b2 scoring tests

python3 scripts/compare_review.py --python-root ~/.agents/skills/stock-select/runtime --rust-root /tmp/stock-select-rs-b2-screen-fix --pick-date 2026-05-25 --method b2
PASS review comparison method=b2 pick_date=2026-05-25 reviewed=139 recommendations=0

stock-select-rs run --method b2 --pick-date 2026-05-25 --runtime-root /tmp/stock-select-rs-native-run-b2 --environment-state weak --environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱" --llm-review-limit 5 --recompute
run elapsed=91.722s

python3 scripts/compare_screen.py --python-root ~/.agents/skills/stock-select/runtime --rust-root /tmp/stock-select-rs-native-run-b2 --pick-date 2026-05-25 --method b2
PASS screen comparison method=b2 pick_date=2026-05-25 candidates=139/139

python3 scripts/compare_review.py --python-root ~/.agents/skills/stock-select/runtime --rust-root /tmp/stock-select-rs-native-run-b2 --pick-date 2026-05-25 --method b2
PASS review comparison method=b2 pick_date=2026-05-25 reviewed=139 recommendations=0

python3 scripts/check_charts.py --runtime-root /tmp/stock-select-rs-native-run-b2 --pick-date 2026-05-25 --method b2
PASS chart smoke method=b2 pick_date=2026-05-25 charts=139
```

当前状态：

```text
b2 screen candidate set 已对齐。
b2 review 原生流程已通过 Python golden parity：per-stock review、summary、llm_review_tasks 均一致。
Python golden 的 2026-05-25.b2 不是纯 baseline：603308.SH 已经是 review-merge 后结果，baseline_review.verdict=PASS，但顶层 verdict=WATCH；临时 Rust runtime 比较 merge 后状态时需要复制该 llm_review_results 文件。
llm_review_tasks 的 `--llm-review-limit 5` 排序规则已对齐为 baseline_score 降序、rank 升序，top5 code 与 task context 已一致。
2026-05-27 进度：恢复 Python `calibrate_b2_selection_score` 对应的 Rust 原生 selection score，补齐 weak relaunch tier、688786.SH MACD 边界、b2 task context 周线阶段后，compare_review.py 已通过。
后续工作：
- b2 当前无 parity 阻塞；后续可扩展多日期回归或推进其他方法。
```

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
review-merge
review-list
run
```

`chart` 已迁到本仓库 runner。`review`、`review-merge`、`review-list` 和 `run` 只走 Rust native review；当前 b1、b2 可用，其他方法会显式报未实现。`review` 和 `run` 会处理：

```text
--dsn
--environment-state
--environment-reason
--llm-min-baseline-score
--llm-review-limit
--chart-workers
```

`review-merge` 会处理：

```text
--method
--pick-date
--runtime-root
--codes <comma-separated optional list>
```

`review-merge` 会读取 `reviews/<pick_date>.<method>/llm_review_results/<code>.json`，校验 LLM review schema，合并回个股 review 文件，并重写 `summary.json`。传入 `--codes` 时只尝试合并指定代码，未指定代码保持原 review 状态。

`review-list` 会处理：

```text
--method
--pick-date
--runtime-root
--verdict PASS|WATCH|FAIL
--dsn <optional>
```

`review-list` 从 `reviews/<pick_date>.<method>/summary.json` 读取指定 verdict 的结果，沿用 summary 中的排序，输出 tab-separated 行：

```text
code    name    signal    signal_type
```

名称来自 PostgreSQL `instruments(ts_code, name)`；如果未配置 DSN 或查询不到名称，则输出 `-`。示例：

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-review-merge-b2 \
  --verdict WATCH
```

`screen` 和 `run` 会处理：

```text
--pool-source turnover-top|custom
--pool-file <path>
```

`--pool-source custom` 的路径优先级与 Python CLI 对齐：

```text
1. --pool-file
2. STOCK_SELECT_POOL_FILE
3. <runtime-root>/custom-pool.txt
```

自定义票池文件为 whitespace-separated stock codes，例如 `603138 300058`。Rust 会把 6 位代码补成 `.SH` / `.SZ`，去重后再与 prepared universe 相交；策略仍按 prepared 数据顺序运行。

### Chart

Rust CLI 已有 `chart` command，当前 chart 渲染路径为：

```text
Rust Command -> 读取 runtime prepared/candidates -> 按 --chart-workers 写 charts/*.payload*.json -> 并发 uv run scripts/render_charts.py
```

`scripts/render_charts.py` 使用 PEP 723 inline dependencies 声明 `pandas`、`matplotlib`、`mplfinance`，不依赖源 Python CLI 项目的 `pyproject.toml` 或虚拟环境。

并发模型：

```text
--chart-workers 默认为 4
worker 数自动不超过待绘图股票数
每个 worker 对应一个 payload 分片和一个 Python 渲染进程
新一轮同日期同 method 绘图会清理旧 payload 分片，避免混淆
```

Rust CLI 生成路径下的 chart artifacts 已 smoke-check 为真实 PNG。既有 Python runtime 中 `2026-05-25.b1` 的 chart 文件存在 placeholder text artifacts，因此不能作为 PNG visual golden。

`chart` command 独立运行时仍会为全部 candidate 绘图。`run` command 的 chart 阶段已经改为条件式：

```text
无 --llm-review-limit 且无 --llm-min-baseline-score：跳过 chart
有 --llm-review-limit 或 --llm-min-baseline-score：先 review 生成 llm_review_tasks.json，再只为 task 中的 code 绘图
```

本阶段验证：

```text
runtime_root=/tmp/stock-select-rs-local-chart-run-b1
python3 scripts/check_charts.py --runtime-root /tmp/stock-select-rs-local-chart-run-b1 --pick-date 2026-05-25 --method b1
PASS chart smoke method=b1 pick_date=2026-05-25 charts=104

parallel chart smoke:
runtime_root=/tmp/stock-select-rs-chart-workers
stock-select-rs run --method b2 --pick-date 2026-05-25 --llm-review-limit 5 --chart-workers 3 --recompute
payload shards=3
charts=5

stock-select-rs chart --method b2 --pick-date 2026-05-25 --runtime-root /tmp/stock-select-rs-chart-workers --chart-workers 4
PASS chart smoke method=b2 pick_date=2026-05-25 charts=139
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

b1、b2 review 已完成 Rust native parity。`stock-select-rs review --method b1|b2` 与 `stock-select-rs run --method b1|b2` 会输出与 Python CLI 一致的 baseline review、summary、LLM task artifacts。

仍未原生化的 review 范围：

- dribull / hcr review 尚未移植；CLI 不再回退到 Python bridge，会显式报错
- b1 weekly slope / weekly MACD cooldown 当前对 2026-05-25 golden 为 `null/false`，后续多日期验证时需要继续补强
- b1 comment 已满足当前 compare 脚本与 task context 对齐，但如后续要逐字比对 per-stock `comment`，需要补全 Python 中周 MACD 红柱、水上、背离、近 3 日死叉描述片段

### Environment Profile 状态

Rust 当前已负责 `review` / `run` 的 market environment resolution。手动参数优先：

```bash
--environment-state weak \
--environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱"
```

如果未传入 `--environment-state`，Rust 会先尝试解析当前 runtime 中的环境记录；若不存在，则从 PostgreSQL `daily_index` 拉取 `000001.SH` 与 `399303.SZ` 最近 180 天数据，执行原生评估并写入：

```text
runtime/environment/history.jsonl
runtime/environment/latest.json
runtime/environment/daily/<pick_date>.<state>.json
```

Rust 当前支持：

- profile constants
- profile-aware scoring helpers
- manual environment state/reason
- b1 native review 使用 profile weights/subscore mode/llm_focus
- automatic market environment evaluation
- runtime `environment/history.jsonl` resolution
- environment daily/latest file writing

注意：为了和既有 Python golden 做逐项 parity，仍建议在 golden 对比命令中显式传入 Python golden 使用的环境参数，避免自动评估策略差异影响 review profile。

验证状态：

```text
cargo test --test market_environment -- --nocapture
PASS 4 tests
```

### Custom Pool 状态

Rust 已接入 Python CLI 的 custom-pool 使用流程：

```bash
stock-select-rs screen \
  --method b1 \
  --pick-date 2026-05-25 \
  --runtime-root /tmp/stock-select-rs-custom-pool \
  --pool-source custom \
  --pool-file /tmp/custom-pool.txt \
  --recompute
```

同样适用于 `run`。当前单元验证：

```text
cargo test --test custom_pool -- --nocapture
PASS 2 tests
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

### Phase 0：运行编排补齐（进行中）

目标：补齐 Python CLI 常用运行入口，使 Rust `screen/review/run` 的使用流程与结果结构保持一致。

当前进度：

```text
Task 1: review/run 自动环境评估 - completed
Task 2: screen/run custom-pool - completed
Task 3: 重新跑 cargo fmt/test 与 b1/b2 smoke - completed
Task 4: review-merge 原生命令 - completed
Task 5: 根据验证结果提交 - pending
```

已验证：

```text
cargo fmt --check
cargo test --quiet
PASS

custom-pool smoke:
runtime_root=/tmp/stock-select-rs-custom-pool
pool_source=custom
pool_file=/tmp/stock-select-rs-custom-pool.txt
candidates=3

auto environment smoke:
runtime_root=/tmp/stock-select-rs-auto-env
stock-select-rs run --method b2 --pick-date 2026-05-25 --llm-review-limit 5 --recompute
environment state=neutral source=scheduled
generated:
- environment/history.jsonl
- environment/latest.json
- environment/daily/2026-05-25.neutral.json
screen parity: PASS candidates=139/139
chart smoke: PASS charts=139

b1 manual environment regression:
runtime_root=/tmp/stock-select-rs-env-regression-b1
screen parity: PASS candidates=104/104
review parity: PASS reviewed=104 recommendations=3
chart smoke: PASS charts=104

review-merge b2 regression:
runtime_root=/tmp/stock-select-rs-review-merge-b2
copied llm_review_results/603308.SH.json from Python golden
stock-select-rs review-merge --method b2 --pick-date 2026-05-25 --codes 603308.SH
screen parity: PASS candidates=139/139
review parity after merge: PASS reviewed=139 recommendations=0
chart smoke: PASS charts=139

conditional run chart:
runtime_root=/tmp/stock-select-rs-run-no-chart
stock-select-rs run --method b2 --pick-date 2026-05-25 --recompute
reviewed=139
chart skipped

runtime_root=/tmp/stock-select-rs-run-chart-limit
stock-select-rs run --method b2 --pick-date 2026-05-25 --llm-review-limit 5 --recompute
llm_review_tasks=5
charts=5

runtime_root=/tmp/stock-select-rs-run-chart-minscore
stock-select-rs run --method b2 --pick-date 2026-05-25 --llm-min-baseline-score 4.03 --recompute
llm_review_tasks=3
charts=3
```

注意：`/tmp/stock-select-rs-auto-env` 的 b2 自动环境 run 使用 Rust 自动评估得到 `neutral`，因此不用于和 Python weak-profile golden 做 review parity。Python golden 的 `603308.SH` 是 review-merge 后的 WATCH；Rust 现在可通过 `review-merge --codes 603308.SH` 合并同一份 LLM 结果，并通过 Python golden parity。

后续可继续推进：

```text
1. 对自动环境评估与 Python market_environment.py 做更多日期回归。
2. 扩展 screen 命令是否需要显式环境参数；当前环境只在 review/run 阶段使用。
3. 推进 dribull / hcr review 原生化。
```

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
