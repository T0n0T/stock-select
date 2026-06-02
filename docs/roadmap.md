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
盘中数据获取已开始 Rust 原生化：新增 `intraday` snapshot 数据层，通过 Tushare Pro REST `rt_k` 拉取并归一化 `*.SH`、`*.SZ`、`*.BJ` 三市场快照；`screen --intraday` 和 `run --intraday` 已接入。盘中 artifact 使用日期级 key `<trade_date>.intraday`，同一交易日同一 method 的重复盘中运行会刷新同一组 candidates/reviews/charts；`run_id` 只作为本次抓取标记写入 payload/meta。独立 `review --intraday` 暂未开放。
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

配置读取优先级统一为：显式 CLI 参数 > 进程环境变量 > 当前工作目录 `.env`。当前覆盖 `POSTGRES_DSN`、`TUSHARE_TOKEN` 和 `STOCK_SELECT_POOL_FILE`。

`chart` 不再调用 `/home/pi/Documents/agents/stock-select` 的 Python CLI；它仍使用 Python 绘图库 `mplfinance/matplotlib`，但脚本和输入数据都在本仓库控制。Rust 会按 `--chart-workers` 把待绘图股票分片，并发启动多个本仓库 `scripts/render_charts.py` 进程。`run` 默认先完成 screen + review；只有传入 `--llm-review-limit` 或 `--llm-min-baseline-score` 时才进入 chart 阶段，且只绘制最终 `llm_review_tasks.json` 中需要给 LLM/subagent 查看图像的股票。`review` 和 `run` 不再委托源 Python CLI。当前 b1、b2 review/run 已完成 Rust native parity；dribull review/run 已原生实现，复用 b2 结构评分并采用 dribull MACD 与 verdict 口径；hcr 的 review 会显式返回未实现错误。

盘中数据获取采用 Rust REST provider，不默认调用上游 Python CLI，也不直接依赖 `tushare-api` crate。原因是当前只需要 `rt_k` 一个接口，直接构造 Tushare Pro JSON 请求更容易控制字段映射、错误信息与同步 CLI 依赖面。

盘中生产命令：

```bash
stock-select-rs screen --method b2 --intraday --tushare-token <token>
stock-select-rs run --method b2 --intraday --tushare-token <token>
```

盘中 prepared cache 按交易日共享：

```text
prepared/<trade_date>.intraday.bin
prepared/<trade_date>.intraday.meta.json
```

盘中 candidates/charts/reviews 按交易日刷新：

```text
candidates/<trade_date>.intraday.<method>.json
charts/<trade_date>.intraday.<method>/<code>_day.png
reviews/<trade_date>.intraday.<method>/summary.json
```

`review-list --intraday --pick-date <trade_date>` 会读取同一日期级 intraday review summary，用于展示本日刷新后的 PASS/WATCH/FAIL 列表。

`run --intraday` 沿用当前 Rust run 的 chart 优化：没有 `--llm-review-limit` 且没有 `--llm-min-baseline-score` 时跳过 chart；有 LLM 阈值时只为 `llm_review_tasks.json` 中的股票绘图。

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
analyze-symbol
completions
```

`chart` 已迁到本仓库 runner。`review`、`review-merge`、`review-list` 和 `run` 只走 Rust native review；当前 b1、b2 可用，其他方法会显式报未实现。`review` 和 `run` 会处理：

```text
--dsn
--environment-state
--environment-reason
--llm-min-baseline-score
--llm-review-limit
--chart-workers
--record
--record-window-trading-days
```

`review`/`run` 传入 `--record` 后，会在 review summary 写完后把当日 `PASS` 与 `WATCH` 写入文本观察票池：

```text
<runtime-root>/watch_pool.csv
```

观察票池沿用 Python CLI 的 CSV 字段：

```text
method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at
```

写入时按 `method + code` 去重；同一股票同一方法反复入选时刷新为最新 `pick_date`、`verdict`、分数和 `recorded_at`。默认保留本次 `pick_date` 往前 15 个交易日内的记录，可通过 `--record-window-trading-days <N>` 调整。更新使用 `watch_pool.csv.lock` 做轻量互斥，避免并发回填时覆盖。

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

`analyze-symbol` 已接入第一版单股分析：

```bash
stock-select-rs analyze-symbol \
  --method b2 \
  --symbol 002350.SZ \
  --pick-date 2026-04-21 \
  --runtime-root /tmp/stock-select-rs-analyze-symbol
```

当前范围是 b1/b2、end-of-day、Rust native baseline review。输出位于：

```text
ad_hoc/<pick_date>.<method>.<code>/result.json
ad_hoc/<pick_date>.<method>.<code>/<code>_day.png
```

该命令不等同于 custom-pool：即使指定股票没有入选候选，也会生成 baseline review 和 `selected_as_candidate=false`。

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

`screen`、`chart`、`run` 已接入默认开启的结构化 stderr 进度输出，覆盖 prepared/snapshot、pool、strategy、candidate write、chart payload/render 等关键阶段。需要关闭时使用 `--no-progress`，stdout 继续保留给命令返回路径或列表输出。

baseline review 回填脚本：

```bash
python3 scripts/backfill_baseline_reviews.py \
  --method b2 \
  --start-date 2026-05-20 \
  --end-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime \
  --dry-run
```

脚本从 PostgreSQL `daily_market` 读取交易日，按日期范围或 `--sample-size` 选取目标交易日；当 `reviews/<date>.<method>/summary.json` 和 `environment/daily/<date>.*.json` 都存在时默认跳过。实际执行时调用 `stock-select-rs run` 生成 Rust native baseline review。由于多个 run 共享同一个 runtime cache，脚本默认 `--max-workers 1` 串行回填；确认可接受失败后重试时，才显式提高并发。运行前默认检查 runtime root 所在文件系统至少有 1 GiB 可用空间，可用 `--min-free-gb 0` 关闭；执行中遇到 `No space left on device` / `os error 28` 会停止提交新日期，清理空间后重跑继续补缺失日期。Rust 侧对 environment history/latest/daily 的读改写使用 runtime lock，atomic write 临时文件使用进程级唯一后缀，避免并发进程复用同一个 `.tmp` 路径。默认不传 `--llm-min-baseline-score` 或 `--llm-review-limit`，因此不会触发 chart 阶段。如需同时生成 LLM/subagent review tasks，可显式传入这两个参数。

PASS topN 胜率统计脚本：

```bash
python3 scripts/review_top3_win_stats.py \
  --method b2 \
  --start-date 2026-04-01 \
  --end-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

脚本直接读取 Rust runtime 的 `reviews/<date>.<method>/summary.json`，每个交易日按 `total_score` 选出 `PASS topN`，再从 PostgreSQL `daily_market` 计算前瞻收益。统计主指标只使用“获胜比例”：样本级 `win_rate_ret3_pct`/`win_rate_ret5_pct`，以及交易日级 `day_hit_rate_ret3_pct`/`day_hit_rate_ret5_pct`。平均前瞻收益不作为好坏判断指标，避免个别极端样本拉高结论。

CLI shell completion 已通过 `clap_complete` 接入：

```bash
stock-select-rs completions zsh
stock-select-rs completions bash
stock-select-rs completions fish
```

支持 `bash`、`zsh`、`fish`、`powershell`、`elvish`，输出写到 stdout，方便按用户 shell 安装到对应 completion 目录。

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

b1、b2 review 已完成 Rust native parity。`stock-select-rs review --method b1|b2|dribull` 与 `stock-select-rs run --method b1|b2|dribull` 会输出 Rust native baseline review、summary、LLM task artifacts。dribull 当前按 Python CLI 口径复用 b2 结构评分、默认五因子权重、dribull MACD phase 和 `_refine_dribull_verdict`。

仍未原生化的 review 范围：

- hcr review 尚未移植；CLI 不再回退到 Python bridge，会显式报错
- b1 weekly slope / weekly MACD cooldown 当前对 2026-05-25 golden 为 `null/false`，后续多日期验证时需要继续补强
- b1 comment 已满足当前 compare 脚本与 task context 对齐，但如后续要逐字比对 per-stock `comment`，需要补全 Python 中周 MACD 红柱、水上、背离、近 3 日死叉描述片段

### Environment Profile 状态

Rust 当前已负责 `review` / `run` 的 market environment resolution。手动参数优先：

```bash
--environment-state weak \
--environment-reason "SSE neutral; CN2000 neutral; 双指数共振偏弱"
```

盘后 `review` / `run --pick-date` 如果未传入 `--environment-state`，Rust 会先尝试解析当前 runtime 中的环境记录；若不存在，则从 PostgreSQL `daily_index` 拉取 `000001.SH` 与 `399303.SZ` 最近 180 天数据，执行原生评估并写入：

```text
runtime/environment/history.jsonl
runtime/environment/latest.json
runtime/environment/daily/<pick_date>.<state>.json
```

盘中 `run --intraday` 只为本次 review 临时解析环境，不写入 `runtime/environment`。盘中仍支持手动 `--environment-state/--environment-reason`；未手动指定时会尝试自动评估当日指数环境，评估失败时只读已有 environment 历史作为 fallback。

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
3. 推进 hcr review 原生化；dribull 可继续补多日期 Python golden parity。
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

- 2026-06-01 b2 review 调参记录：已试验弱环境 `B2 rebound` 的底背离不破顶/底部修复口径。当前实现把 refined 底部修复在 weak/neutral 下映射到 `macd_phase` 小幅加分，并把 weak 环境 relaunch PASS 特例收窄为必须满足 refined 底部修复，否则保留为 WATCH。2026-03-01..2026-05-29 回测中，weak pass top5 从 14 个样本/8 天收缩到 3 个样本/3 天，3 日和 5 日正收益率由 50.0%/42.9% 提升到 100.0%/100.0%；strong/neutral pass top 统计不变。该版本提纯有效但覆盖明显收缩，并误伤 2026-03-24 603601.SH、2026-04-01 601975.SH 等正例，后续需要继续拆分“非 refined 但仍可 PASS”的形态。
- 2026-06-01 b2 strong PASS 内部排序记录：strong 环境中 `B3/B3+ trend_start + trend>=4 + price=5 + volume=5 + previous_abnormal=5 + macd_phase 3.0..3.8` 作为高弹性形态，在 PASS 内部 selection score 上加 0.30，并将 review summary 排序调整为优先顶层 selection `total_score`、baseline score 作为次级键。2026-03-01..2026-05-29 回测中，strong pass top3 的 3 日/5 日胜率从 61.1%/58.3% 提升到 63.9%/61.1%，ret5 均值从约 1.53% 提升到 2.00%；strong top5 基本不变。
- 2026-06-02 b2 weak review 更改方向：weak 不再优先扩 PASS，而是先把 `WATCH` 作为弱环境的主要承接层，在 PASS+WATCH 内做 `rank_score` 和风险扣分。离线样本中 weak WATCH 共 1071，ret3>0 445（41.5%）、ret5>0 404（37.7%）、ret3>=5 173（16.2%）、ret3<=0 601（56.1%），整体均值为 ret3=-0.83、ret5=-1.68，说明 broad WATCH -> PASS 放宽会显著引入负例。第一阶段更改方向是把 `B3/rebound + near_high + above_hold + bull_stack + tight + volume=expanding + kdj=rising` 定义为 `weak_watch_rebound_volume_confirm` 排序加分候选，只进入 weak 前五/前十排序增强；它 10 个样本中 ret3>0=6、ret5>0=5、ret3>=5=4、ret3<=0=2，具备进攻观察价值但样本不足，暂不直接放 PASS。`B2/trend_start + near_high + above_hold + bull_stack + tight + volume=normal + kdj=neutral` 定义为 `weak_watch_near_high_small_repair`，10 个样本 ret3>0=10、ret5>0=6、ret3>=5=1、ret3<=0=0，更偏小正收益修复，只适合作为 WATCH 内排序稳定器或低风险观察，不作为高弹性 PASS 条件。第二阶段先加入 veto/risk：`b3_rebound_extended_mixed`、`macd_w2_div_d4_repair`、`macd_w0_div_d4_repair`、`b2_near_high_normal_rising_no_red`、`b2_upper_expanding_neutral_red`、`b3_rebound_upper_no_red` 命中时保留 WATCH 或降低 rank，不允许参与 weak WATCH -> PASS override。BBI/BIAS/OBV 只作为上述 family 的二级确认和前五/前十排序增强，不单独作为 PASS 放行条件。生产实施顺序应为：先落 weak rank_score 加分/扣分并验证 top3/top5，之后只对同时满足候选 family、无 veto、ret3/ret5 离线稳定的单一形态族做最小 WATCH -> PASS override；每次必须列出新增 PASS 中 ret3<=0、被挤出 top5 中 ret3>=5、以及 weak/neutral/strong 分环境结果。
- 2026-06-02 b2 weak WATCH 排序实现记录：已按上述方向在 Rust native review 内实现 weak WATCH selection score 调整，不改变 baseline verdict。`weak_watch_rebound_volume_confirm` 对 weak/WATCH 的 `B3 rebound` 近 90 日高位、90 日中线之上、MA25>=MA60、多头支撑、当日振幅/20 日区间压缩 tight、近 5 日量比 expanding、KDJ rising 组合加 0.18；`weak_watch_near_high_small_repair` 对 weak/WATCH 的 `B2 trend_start` 近高位、above_hold、bull_stack、当日振幅/20 日区间压缩 tight、量能 normal、KDJ neutral 组合加 0.08。风险侧对 `b3_rebound_extended_mixed` 扣 0.30，对 `macd_w2_div_d4_repair` / `macd_w0_div_d4_repair` 扣 0.24，对 `b2_near_high_normal_rising_no_red`、`b2_upper_expanding_neutral_red`、`b3_rebound_upper_no_red` 扣 0.16。注意：离线报告中的 `compression=tight` 口径是“当日振幅 / 最近 20 日区间 <= 0.40”，不是“20 日区间 / 90 日区间”。生产实现已按该口径对齐。
- 2026-06-02 b2 weak WATCH -> PASS 小范围试验：离线模拟显示，若仅把 `weak_watch_near_high_small_repair` 加入 PASS，weak PASS 从 3 样本扩到 13 样本，整体 ret3>0=13/13、ret5>0=9/13、ret3>=5=4/13、ret3<=0=0/13，daily PASS top3 为 10 样本/5 天，ret3>0=10/10、ret5>0=8/10、ret3>=5=4/10、ret3<=0=0/10，ret3_mean=6.01、ret5_mean=8.14。相比之下 `weak_watch_rebound_volume_confirm` 加入 PASS 后，daily PASS top3 的有效 ret3 样本中 ret3>0=9/11、ret3<=0=2/11，暂不升 PASS。生产仅实现 `weak_watch_near_high_small_repair` 的 WATCH -> PASS override：要求 weak、当前 verdict=WATCH、B2 trend_start、近 90 日高位、90 日中线之上、MA25>=MA60、多头支撑、当日振幅/20 日区间压缩 tight、近 5 日量比 normal、KDJ neutral，并且不命中 `b3_rebound_extended_mixed`、`macd_w2_div_d4_repair`、`macd_w0_div_d4_repair`、`b2_near_high_normal_rising_no_red`、`b2_upper_expanding_neutral_red`、`b3_rebound_upper_no_red` 等 veto。该 override 仍是单一形态族试验；下一步必须重跑 2026-03-01..2026-05-29 runtime 并输出新增 PASS 中 ret3<=0、被挤出 top5 中 ret3>=5、以及分环境影响。
- 2026-06-02 Phase 7 回测结果：用当前 Rust 二进制重跑 `/home/pi/stock-select-rs-b2-phase7-current` 的 2026-03-02..2026-05-29 共 61 个 b2 日期后，weak PASS 从旧版 3 样本扩到 9 样本，ret3>0 为 9/9、ret3>=5 为 4/9、ret3<=0 为 0/9，ret3_mean=6.19、ret3_median=4.27；ret5>0 为 6/9、ret5_mean=8.10、ret5_median=10.13。weak PASS daily top3 有效 ret3 样本为 8 个，ret3>0=8/8、ret3>=5=4/8、ret3<=0=0/8，ret5>0=6/8。新增 PASS 6 个，ret3>0=6/6、ret3<=0=0/6，但 ret5>0 只有 3/6，说明该 override 更适合作为 3 日小修复 PASS，而不是 5 日稳态 PASS 扩张。neutral 与 strong PASS 指标不变；weak PASS+WATCH top5 的 ret3>0 从 43/120 提升到 46/120，ret3<=0 从 77/120 降到 74/120。刷新后的 `weak_watch_positive_report` 只统计仍为 WATCH 的样本，因此 `weak_watch_near_high_small_repair` 已不再出现在 WATCH 升级候选表中。
- 2026-06-02 strong/neutral 剩余负例整理：新增 `strong_neutral_risk_report.json` / `strong_neutral_risk_report.md`，把 strong_v1 topN 负例和 neutral WATCH veto 候选统一输出为离线 rank_score/veto 候选，不改变生产 verdict。strong 当前只有一个足够干净的扣分候选：`NONB3=B2|red_expanding|price_turnover_rise|trend_start|price=near_high|volume=expanding|kdj=rising`，top5 内 10 样本 ret3>=5=0、ret3<=0=10、ret3_mean=-3.09、ret5_mean=-2.53，其中包含 1 个当前 PASS 和 9 个 WATCH，后续优先做 strong rank_score 扣分实验。neutral 候选保持 WATCH 降权/veto 方向：`neutral_b2_near_high_expanding_macd_bad` 65 样本 ret3<=0=31、ret3>=5=12；`neutral_b2_rebound_extended_no_red` 41 样本 ret3<=0=23、ret3>=5=4、ret3_mean=-2.25；`neutral_b3_rebound_upper_no_red` 34 样本 ret3<=0=14、ret3>=5=10；`neutral_b3_near_high_turnover_mixed` 9 样本 ret3<=0=4、ret3>=5=1。neutral 仍不做 PASS 放宽，先做 WATCH 内降权并重跑 Phase 7。
- 2026-06-02 neutral 因子正向作用拆解：新增 `neutral_factor_effect_report.json` / `neutral_factor_effect_report.md`，专门回答 neutral 当前参考因子在 `ret3>5` 组里的占比和 uplift。neutral ret3>5 样本 199，PASS+WATCH 覆盖 176。多数 ret3>5 样本拥有且相对 neutral 基准有 uplift 的因子包括：`midline_state=above_hold`（76.9%，uplift +11.5%，PASS+WATCH ret3>5 中 83.5%）、`signal_type=trend_start`（63.8%，+6.0%，PASS+WATCH 中 71.6%）、`price_bucket=upper`（55.8%，+7.1%，PASS+WATCH 中 60.2%）、`support_stack=bull_stack`（78.9%，+3.3%）、`compression=tight`（87.9%，+4.4%）、`bbi_bias=above_extended`（58.3%，+4.2%）和 `signal_combo=B2|trend_start`（54.3%，+4.0%）。`signal=B2`、`price_turnover_rise`、`daily_macd_hist=green_or_zero`、`volume=expanding` 虽然常见，但 uplift 为负或接近 0，不应单独加分。neutral 的正向骨架应是 `trend_start + upper/near_high + above_hold + bull_stack + tight + BBI above_extended`，并必须叠加 `strong_neutral_risk_report` 里的 veto/risk 条件。

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

## b2 Review 层重构 Roadmap

目标：不再以现有 `PASS/WATCH/FAIL` 或五维总分作为唯一建模起点，而是先在 b2 筛选池内建立能区分不同涨幅层级的 review/ranking 体系。后续允许重写原评分体系；不需要为了兼容旧五维而保留无效逻辑。

### 目标标签

第一阶段以 `ret3` 为主标签，`ret5` 作为稳健性验证：

```text
A: ret3 >= 10%
B: 5% <= ret3 < 10%
C: 0% < ret3 < 5%
D: -5% < ret3 <= 0%
E: -10% < ret3 <= -5%
F: ret3 <= -10%
```

核心目标：

- A/B 组在同日同环境排序中明显前移。
- D/E/F 组在同日同环境排序中明显后移。
- `PASS/WATCH/FAIL` 作为最后映射，而不是第一判断依据。
- 分环境验证：weak、neutral、strong 分别比较，不把不同环境样本混合下结论。

### Phase 1：离线诊断数据集

新增诊断脚本，先不改生产逻辑：

```text
scripts/b2_review_layer_diagnostics.py
```

阶段性状态：已建立脚本和单元测试，默认读取 Rust runtime review artifacts，并从 PostgreSQL `daily_market` 计算 `ret3` / `ret5`。`/home/pi/stock-select-rs-b2-review-layer-macd` 已重跑 2026-03-01..2026-05-29 样本并验证 MACD 字段填充完整：

```text
rows=4057
segments=17
macd_segments=1674
factor_segments=1067
output=diagnostics/b2_review_layer/
environments={'neutral': 1152, 'strong': 975, 'weak': 1930}
ret3 buckets={'A': 354, 'B': 458, 'C': 1030, 'D': 1166, 'E': 611, 'F': 264}
```

当前诊断先覆盖“当前五维 + signal/signal_type + ret3/ret5 + 环境分层 + 错配/漏配/排序错配”。MACD 浪型细分字段已接入 b2 baseline review 输出；新生成的 review artifacts 会持久化日/周 MACD phase、wave_index、wave_stage、背离布尔值和 `weekly_daily_combo_type`，诊断脚本会保留 `0` / `False` 这类有效取值，并额外输出 `macd_segments.json` 作为 `env + signal + signal_type + 周MACD + 日MACD + combo` 的细分组合。`macd_wave_rules.json` / `macd_wave_rules.md` 以推升浪和浪型阶段为主，按 weak/neutral/strong 计算环境基准、正向候选规则和相对基准的 positive_rate uplift。

诊断脚本已从 `daily_market` 补第一批非未来上下文因子：90 日价格位置、90 日高低中线确认关系、MA25/MA60 关系与 5 日斜率、20/40 日区间压缩、最近高低点距离、5/10 日量比、真实换手率、MACD 红柱状态、价格与换手率同步关系、KDJ 当前值与 J/K/D 关系。这些字段直接写入 `features.csv`，并额外输出 `factor_segments.json`，按 `env + signal + signal_type + price/midline/support/compression/volume/kdj bucket` 做聚合。诊断脚本也已从 PostgreSQL `daily_indicators.extra_factors_jsonb` 合并 BBI、BIAS 和 OBV：新增 `bbi_bfq`、`close_vs_bbi`、`bbi_bias_state`、`bias1_bfq`、`bias2_bfq`、`bias3_bfq`、`bias_bucket`、`obv_bfq`、`obv_ratio_5d` 和 `obv_state`，并输出 `weak_indicator_report.json` / `weak_indicator_report.md`。Tushare 每日筹码分布暂不进入第一版离线排序，原因是它需要额外确认接口权限、字段稳定性和缓存落库方案；当前优先用本地 PostgreSQL 已有指标验证区分度。

Phase 3 环境内比较已输出 `environment_comparisons.json`，按 weak/neutral/strong 分别汇总 A+B、D/E/F、A vs E/F、B vs D、高涨幅 WATCH/FAIL、负收益 PASS，以及正负组高频 base/MACD/factor segment。`strong_pass_watch_ranking_report.json` / `strong_pass_watch_ranking_report.md` 在 strong 路由内对 PASS/WATCH 样本做强组合分档和每日 top3 重排对比，用于先定 strong 的强势票排序；当前 strong_v1 相比 current_score 更能提升高 ret3 捕捉，strong_v2 仅作为负例扣分实验保留，未优于 strong_v1 前不进入生产排序。`weak_pass_watch_ranking_report.json` / `weak_pass_watch_ranking_report.md` 在 weak 路由内单独验证修复型 W-A/W-B/W-C/W-D family 与风险扣分，当前 weak_v2 主要用于降低 top 排名损伤；weak_v3 由 `weak_v2_negative_groups_report.json` / `weak_v2_negative_groups_report.md` 的剩余负例抽取，能改善 top3/top5 均值，但 top3 负例数未低于 weak_v2，暂不作为生产候选。weak_v4 在 weak_v3 基础上加入 BBI/BIAS/OBV 离线加减分；本次样本中 top5 的 ret3>=5 从 27/125 提升到 33/125，ret3<=0 从 70/125 降到 68/125，ret3_mean 从 -0.79 提升到 0.08，但 top3 的 ret3<=0 从 40/75 增至 41/75、ret3_mean 从 0.25 回落到 -0.05。因此 BBI/BIAS/OBV 更适合作为 weak 前五/前十扩展排序增强，不足以单独支撑 top3 或 PASS 放行。`weak_watch_positive_report.json` / `weak_watch_positive_report.md` 进一步只拆 `env=weak,current_verdict=WATCH`：样本 1071，ret3>0 为 445（41.5%），ret5>0 为 404（37.7%），ret3>=5 为 173（16.2%），ret3<=0 为 601（56.1%），整体 ret3_mean=-0.83、ret5_mean=-1.68。当前仅筛出两个离线升级候选：一是 `B3/rebound + near_high + above_hold + bull_stack + tight + volume=expanding + kdj=rising`，10 样本中 ret3>0=6、ret5>0=5、ret3>=5=4、ret3<=0=2，ret3_mean=4.66、ret5_mean=5.98；二是 `B2/trend_start + near_high + above_hold + bull_stack + tight + volume=normal + kdj=neutral`，10 样本中 ret3>0=10、ret5>0=6、ret3>=5=1、ret3<=0=0，ret3_mean=2.60、ret5_mean=1.82，更偏小正收益修复，不足以直接定义强 PASS。风险/veto 候选包括 `b3_rebound_extended_mixed`（11 样本 ret3>=5=0、ret3<=0=10、ret3_mean=-5.06）、`macd_w2_div_d4_repair`（16 样本 ret3>=5=0、ret3<=0=15、ret3_mean=-3.97）、`macd_w0_div_d4_repair`（32 样本 ret3>=5=2、ret3<=0=24、ret3_mean=-5.58）、`b2_near_high_normal_rising_no_red`、`b2_upper_expanding_neutral_red` 和 `b3_rebound_upper_no_red`。这些只作为离线候选和风险条件，不改变生产 review verdict。`strong_pass_composition_report.json` / `strong_pass_composition_report.md` 单独拆解当前 strong PASS 的基础组成，避免把 S-A 误认为当前 PASS 主体；`strong_b3_red_macd_report.json` / `strong_b3_red_macd_report.md` 专门检验 strong B3/B3+ 对红 MACD 再扩张、价格上涨和换手率同步放大的敏感性；`strong_v1_negative_groups_report.json` / `strong_v1_negative_groups_report.md` 反查 strong_v1 每日 top3/top5 中 ret3<=0 的 family、factor、MACD 浪型和 B3 条件，作为排序扣分或 veto 候选来源。不改变生产 review verdict。`stable_patterns.json` / `stable_patterns.md` 进一步从 base/MACD/factor 三层筛出样本数足够、正负样本差异较稳定的 promising/risky/mixed_high_sample 组合，作为后续 review 分层结构的离线观察池。不改变生产 review verdict。

`neutral_watch_positive_report.json` / `neutral_watch_positive_report.md` 已单独拆 `env=neutral,current_verdict=WATCH`：样本 958，ret3>0 为 386（40.3%），ret5>0 为 343（35.8%），ret3>=5 为 175（18.3%），ret3<=0 为 457（47.7%），整体 ret3_mean=0.03、ret5_mean=-0.81。当前候选仍不够干净：`B2/trend_start + N-B + near_high + above_hold + bull_stack + tight + volume=normal + kdj=neutral + green_or_zero + price_turnover_rise` 为 9 样本，ret3>=5=4、ret3<=0=3；`B3/rebound + near_high + above_hold + bull_stack + tight + volume=normal + kdj=rising + red_expanding + turnover=mixed` 为 8 样本，ret3>=5=3、ret3<=0=2；`W:rising:2:背离|D:falling:4:修复` 为 8 样本，ret3>=5=2、ret3<=0=1 且 ret5_mean=-0.01。因此 neutral 当前只完成离线拆分，不做生产 PASS 放宽。neutral 风险候选包括 `neutral_b2_rebound_extended_no_red`（41 样本 ret3<=0=23、ret3_mean=-2.25）、`neutral_b2_near_high_expanding_macd_bad`（65 样本 ret3<=0=31）、`neutral_b3_rebound_upper_no_red` 和 `neutral_b3_near_high_turnover_mixed`，后续更适合作为 rank_score 扣分或 veto 来源。

Phase 7 current runtime 已新增 `strong_neutral_risk_report.json` / `strong_neutral_risk_report.md`、`neutral_factor_effect_report.json` / `neutral_factor_effect_report.md`、`neutral_watch_ranking_report.json` / `neutral_watch_ranking_report.md`、`neutral_v1_stability_report.json` / `neutral_v1_stability_report.md`、`neutral_v2_veto_report.json` / `neutral_v2_veto_report.md`、`pass_watch_high_ret3_group_report.json` / `pass_watch_high_ret3_group_report.md` 和 `env_skeleton_top1_report.json` / `env_skeleton_top1_report.md`。结论分四层：strong 的 `strong_v3_rank` 将 `B2 + trend_start + near_high + volume=expanding + KDJ rising + MACD red_expanding + price_turnover_rise` 作为风险扣分，但实际 top3 只从 current_score 的 ret3>=5=19/60、ret3<=0=27/60 变为 21/60、28/60，top5 从 28/100、52/100 变为 30/100、55/100，弱于 strong_v1 的 top3 21/60、27/60 和 top5 31/100、51/100，因此 strong_v3 不进入生产候选。neutral 的 `neutral_v1_rank` 用正向骨架加分（`above_hold`、`trend_start`、`upper`、`bull_stack`、`tight`、`above_extended` 等）叠加四类 veto 扣分，top3 从 current_score 的 ret3>=5=8/48、ret3<=0=23/48、ret3_mean=0.12 提升到 18/48、19/48、ret3_mean=1.64，top5 从 18/80、36/80、ret3_mean=0.75 提升到 23/80、34/80、ret3_mean=0.81；按日期看 16 天中 11 天改善、5 天回归，ret3>=5 更好的日期为 9 天、ret3<=0 更少的日期为 5 天。neutral_v1 top3 负例仍有 22 个，ret3<=0 为 19/22、ret3_mean=-5.63、ret3_median=-4.33、ret5_mean=-7.07，且现有四类 risk flag 基本没有覆盖；负例集中在 `B2|trend_start`（15/22，ret3_mean=-6.25）和 `B3|trend_start`（7/22，ret3_mean=-4.56），说明不能直接按 signal_type 或 trend_start 扣分。neutral_v2 只从 neutral_v1 top3 中抽 `loss_count>=2 且 ret3>=5=0` 的 factor/MACD 组做离线扣分：候选包括 `B2 trend_start + upper + above_hold + bull_stack + compression=normal + volume=expanding + kdj=rising`（2 样本 ret3<=0=2、ret3_mean=-7.74）、`B3 trend_start + upper + above_hold + bull_stack + tight + volume=normal + kdj=neutral`（3 样本 ret3>=5=0、ret3<=0=2、ret3_mean=-1.69）和 `W:rising:2:背离|D:rising:2:背离`（2 样本 ret3<=0=2、ret5_mean=-12.10）。neutral_v2 top3 与 neutral_v1 同为 ret3>=5=18/48、ret3<=0=19/48，仅 ret3_mean 从 1.64 提至 1.69；top5 从 ret3>=5=23/80、ret3<=0=34/80、ret3_mean=0.81 改善到 23/80、32/80、ret3_mean=1.14。由于被扣分全集仍含 ret3>=5=5/30，neutral_v2 只能作为前五/前十离线排序观察，不进入生产 verdict 或 rank_score。`pass_watch_high_ret3_group_report` 进一步只看 PASS+WATCH 中 `ret3>=5` 和每日最高涨幅样本：strong 有 277 个高涨幅样本、20 个高涨幅日，日内最高涨幅的强环境基础骨架 `B2|trend_start|price=upper_or_near_high|midline=above_hold|support=bull_stack` 覆盖 13/20（65.0%），ret3_mean=30.66；neutral 有 191 个高涨幅样本、16 个高涨幅日，环境内前两组为同一 B2 骨架 7/16（43.8%，ret3_mean=21.98）和 `B3|rebound|price=upper_or_near_high|midline=above_hold|support=bull_stack` 3/16（18.8%，ret3_mean=17.61）；weak 有 176 个高涨幅样本、23 个高涨幅日，环境内前四组为同一 B2 骨架 8/23（34.8%，ret3_mean=27.49）、`B2|trend_start|price=extended_or_unknown|midline=above_hold|support=bull_stack` 3/23（13.0%，ret3_mean=22.43）、`B2|trend_start|price=upper_or_near_high|midline=reclaim_volume|support=bull_stack` 2/23（8.7%，ret3_mean=24.82）和 `B2|trend_start|price=upper_or_near_high|midline=pullback_confirm|support=bull_stack` 2/23（8.7%，ret3_mean=14.84）。因此基础骨架应按环境分别找，不强制共用。`env_skeleton_top1_report` 用各环境自己的 priority skeleton groups 做 PASS+WATCH top1 离线模拟：weak 从 current_score 的 ret3>0=9/24、ret3>=5=5/24、ret3<=0=15/24、ret3_mean=-1.36 改善到 13/24、7/24、11/24、ret3_mean=3.50，是当前最明确的推进方向；strong 从 12/20、8/20、8/20、ret3_mean=0.84 变为 10/20、8/20、10/20、ret3_mean=0.70，说明 naive 骨架加权会误伤 strong，需要回到 strong_v1 或更窄 veto；neutral 从 8/16、3/16、8/16、ret3_mean=0.64 变为 8/16、4/16、8/16、ret3_mean=-0.50，仅提高 ret3>=5 和 ret5_mean，仍需要更细的风险过滤。下一步优先在 weak 环境把多骨架 top1 加权拆成可解释条件和 veto；strong/neutral 暂不跟随 weak 的骨架权重进入生产。

本轮 strong 调参先冻结在 `strong_v1_rank`，新增 `weak_neutral_top3_followup_report.json` / `weak_neutral_top3_followup_report.md` 只推进 weak 和 neutral。按 top3 样本口径，weak current_score 为 ret3>=5=14/72、ret3<=0=46/72、日命中率 9/24；weak_v3 提升到 ret3>=5=20/72、ret3<=0=40/72、日命中率 15/24，weak_v4 为 19/72、42/72、日命中率 15/24。结论是 weak_v3 更适合作为 top3 命中率参考，weak_v4 更适合作为 top5/指标层参考；weak 下一步不是继续粗加分，而是针对 top3 负例集中组继续 veto，例如 `B3 rebound + near_high + above_hold + bull_stack + tight + volume=normal + kdj=rising`、`B3 trend_start + upper + above_hold + bull_stack + tight + volume=normal + kdj=rising`、`B2 trend_start + upper + reclaim_volume + bull_stack + tight + volume=expanding + kdj=rising`，并继续观察 `b3_trend_red_macd_bad` 和 `b2_mid_near_expanding_red_macd_bad`。neutral current_score 为 ret3>=5=8/48、ret3<=0=25/48、日命中率 6/16；neutral_v1 提升到 ret3>=5=18/48、ret3<=0=20/48、日命中率 12/16，neutral_v2 保持 18/48、20/48、日命中率 12/16，仅均值略升。结论是 neutral 当前以 `neutral_v1_rank` 作为主候选，neutral_v2 只保留为 top5 风险修正观察，不进入生产 verdict。

weak 本轮调参已收口，新增 `weak_final_tuning_report.json` / `weak_final_tuning_report.md`。最终 weak top3 推荐为 `weak_v3_minus_reclaim`：在 weak_v3 基础上，仅对 `B2 trend_start + price=upper + midline=reclaim_volume + bull_stack + compression=tight + volume=expanding + kdj=rising` 做 0.16 小扣分。该方案相对 weak_v3 top3 从 ret3>=5=19/72、ret3<=0=41/72、日命中率 15/24 改善到 20/72、40/72、16/24；top5 从 30/120、67/120、日命中率 18/24 改善到 31/120、65/120、19/24。`weak_v4_reference` 虽然 top5 更强（ret3>=5=34/120、ret3<=0=65/120、日命中率 20/24），但 top3 为 19/72、42/72，弱于最终 weak top3 方案，因此只作为前五/指标层参考。更宽的 three-loss-group 和 MACD 组合 veto 会降低日命中率或 top5 捕捉，不作为本轮 weak 最终方案。weak 本轮仍不扩 PASS，不改生产 verdict；若进入实现阶段，只允许落排序层小扣分。

三类环境本轮调参冻结结论：strong 冻结为 `strong_v1_rank`，不采用 strong_v3 或环境主骨架 top1 加权；weak 冻结为 `weak_v3_minus_reclaim`，top5 只参考 `weak_v4_reference`，不扩 weak PASS；neutral 冻结为 `neutral_v1_rank`，不采用 neutral_v2 作为 top3 主线。核心指标如下：strong_v1 top3 ret3>=5=21/60、ret3<=0=27/60、ret3_mean=2.53，top5 为 31/100、51/100、ret3_mean=1.58；weak final top3 为 20/72、40/72、日命中率 16/24，top5 为 31/120、65/120、日命中率 19/24；neutral_v1 top3 为 18/48、20/48、日命中率 12/16，top5 为 23/80、37/80。neutral_v2 top3 与 neutral_v1 相同，只把 top5 ret3<=0 从 37/80 降到 35/80、ret3_mean 从 0.44 提到 0.75，因此只作为后续 top5 风险修正观察，不作为本轮冻结方案。下一阶段若进入生产实现，应只改排序层：strong 使用 strong_v1，weak 使用 weak_v3 加单一 reclaim 扣分，neutral 使用 neutral_v1；三者均不改变 review verdict。

三类环境冻结方案已进入 Rust native review 排序层实现：strong 沿用既有 `adjust_b2_strong_pass_selection_score` 的 high-elastic PASS 加分；weak 完整补齐离线 `weak_v3_minus_reclaim` 分数链：W-A/W-B/W-C/W-D family 加分、weak_v1 风险扣分、B2 rebound 小扣分、W-A/W-C 无风险清洁加分、weak_v3 五类剩余负例扣分，并对 `B2 trend_start + upper + reclaim_volume + bull_stack + tight + expanding + rising` 做 0.16 小扣分；生产路径继续停止 weak WATCH->PASS override。neutral 新增 `adjust_b2_neutral_v1_selection_score`，按 `trend_start`、`B2 trend_start`、`upper`、`above_hold`、`bull_stack`、`tight`、`normal volume` 加分，并按 `neutral_b2_near_high_expanding_macd_bad`、`neutral_b2_rebound_extended_no_red`、`neutral_b3_rebound_upper_no_red`、`neutral_b3_near_high_turnover_mixed` 对应条件扣分。实现边界仍是 selection score 排序层，不改变最终 review verdict。

2026-06-02 当前 runtime 复算记录：用户覆盖 `~/.agents/skills/stock-select/runtime` 后，先用旧的 weak 局部实现复算，发现 weak PASS+WATCH top3 只有 ret3>=5=16/72、ret3<=0=45/72、ret3_mean=-1.15，低于离线冻结 `weak_v3_minus_reclaim` 的 20/72。根因是生产 `adjust_b2_weak_watch_selection_score` 只落了两个正向 WATCH 候选、部分 veto 和 reclaim 小扣分，没有完整落离线 `weak_v3` 分数链。修正并重建 `stock-select-rs` 后，直接逐日重跑当前 runtime 的 2026-03-02..2026-05-29 b2 review，复算结果为：strong PASS+WATCH top3 ret3>=5=20/60、ret3<=0=25/60、ret3_mean=2.36；neutral PASS+WATCH top3 ret3>=5=19/48、ret3<=0=20/48、ret3_mean=1.55；weak PASS+WATCH top3 ret3>=5=20/72、ret3<=0=42/72、ret3_mean=-0.13，top5 ret3>=5=29/120、ret3<=0=70/120、ret3_mean=-0.57。weak top3 高涨幅命中已回到离线冻结目标，但 top3 负例和 top5 捕捉仍弱于离线报告中的 40/72、31/120，说明生产特征桶与离线特征桶仍有轻微口径差异，下一步只针对 weak 剩余 top3/top5 负例继续做口径对齐或更窄 veto，不扩 PASS。

2026-06-02 weak 口径差异检查：继续检查 weak 剩余偏差时发现生产 `b2_midline_state` 只有 `above_hold/below_midline`，而 diagnostics 离线分桶依赖 `reclaim_volume/pullback_confirm/above_hold/below_midline`，导致 W-C 和 `b2_reclaim_expanding_rising` 扣分口径不能稳定命中。已按 diagnostics 的 `classify_midline_state` 对齐生产口径：前一日不在 90 日中线之上、当日放量站上中线为 `reclaim_volume`；低点回踩 90 日中线 0.97..1.02 且收在中线之上为 `pullback_confirm`；否则再判 `above_hold/below_midline`。重建二进制后只重跑 weak 日期，复算结果：weak PASS+WATCH top3 ret3>=5 从 20/72 提升到 21/72，ret3<=0 从 42/72 降到 40/72，ret3_mean 从 -0.13 提升到 -0.01，日 ret3>=5 命中从 13/24 提升到 14/24；top5 ret3>=5 从 29/120 提升到 30/120，ret3<=0 从 70/120 降到 68/120。至此 weak 离线 top3 目标已完成并略超预期；top5 仍低于离线 `31/120、65/120`，下一步只继续查 weak top5 剩余负例，不扩 PASS。

2026-06-02 weak top5 剩余负例检查：新增 `weak_top5_residual_negative_report.json` / `weak_top5_residual_negative_report.md`，只基于当前 runtime 的 weak PASS+WATCH 实际每日 top5 做负例分组，不用四位小数 score 重新排序。当前 top5 为 ret3>=5 30/120、ret3<=0 68/120、ret3_mean=-0.5152；剩余 68 个 ret3<=0 负例没有出现足够大的单一干净 veto 组。高频的 `B3 upper/near_high + above_hold + bull_stack + tight + normal + rising` 在 top5 中负例较多，但全量同组仍有 ret3>=5 23/110，粗扣会误伤高涨幅捕捉；`B3 turnover=mixed/price_up_turnover_not` 全量也有 ret3>=5 38/203，不适合作为 broad 扣分。相对干净的窄风险组只有 `B2 trend_start + price=extended_or_unknown + above_hold + bull_stack + tight + volume=expanding + kdj=repair_from_low + green MACD + price_turnover_rise`，全量 n=5、ret3>=5=0、ret3<=0=4，但样本太小，只保留为后续 top5-only 风险观察。BBI/BIAS/OBV 在剩余 top5 负例中没有形成独立 veto，`high_positive` bias 甚至在 B2 above_hold 子集里均值偏正，因此本轮不追加 weak top5 生产扣分、不改 PASS/WATCH verdict；weak 排序暂以已落地的 `weak_v3_minus_reclaim` 加 midline 口径对齐为收口状态。

固定初始样本范围：

```text
method=b2
date=2026-03-01..2026-05-29
sample=进入 b2 筛选池的全部股票
label=ret3_bucket + ret3 + ret5
environment=weak/neutral/strong
```

输出：

```text
diagnostics/b2_review_layer/features.csv
diagnostics/b2_review_layer/summary.md
diagnostics/b2_review_layer/segments.json
diagnostics/b2_review_layer/macd_segments.json
diagnostics/b2_review_layer/macd_wave_rules.json
diagnostics/b2_review_layer/macd_wave_rules.md
diagnostics/b2_review_layer/factor_segments.json
diagnostics/b2_review_layer/environment_comparisons.json
diagnostics/b2_review_layer/strong_pass_watch_ranking_report.json
diagnostics/b2_review_layer/strong_pass_watch_ranking_report.md
diagnostics/b2_review_layer/strong_pass_composition_report.json
diagnostics/b2_review_layer/strong_pass_composition_report.md
diagnostics/b2_review_layer/strong_b3_red_macd_report.json
diagnostics/b2_review_layer/strong_b3_red_macd_report.md
diagnostics/b2_review_layer/strong_v1_negative_groups_report.json
diagnostics/b2_review_layer/strong_v1_negative_groups_report.md
diagnostics/b2_review_layer/weak_pass_watch_ranking_report.json
diagnostics/b2_review_layer/weak_pass_watch_ranking_report.md
diagnostics/b2_review_layer/weak_v2_negative_groups_report.json
diagnostics/b2_review_layer/weak_v2_negative_groups_report.md
diagnostics/b2_review_layer/weak_indicator_report.json
diagnostics/b2_review_layer/weak_indicator_report.md
diagnostics/b2_review_layer/weak_watch_positive_report.json
diagnostics/b2_review_layer/weak_watch_positive_report.md
diagnostics/b2_review_layer/neutral_watch_positive_report.json
diagnostics/b2_review_layer/neutral_watch_positive_report.md
diagnostics/b2_review_layer/strong_neutral_risk_report.json
diagnostics/b2_review_layer/strong_neutral_risk_report.md
diagnostics/b2_review_layer/neutral_factor_effect_report.json
diagnostics/b2_review_layer/neutral_factor_effect_report.md
diagnostics/b2_review_layer/neutral_watch_ranking_report.json
diagnostics/b2_review_layer/neutral_watch_ranking_report.md
diagnostics/b2_review_layer/neutral_v1_stability_report.json
diagnostics/b2_review_layer/neutral_v1_stability_report.md
diagnostics/b2_review_layer/neutral_v2_veto_report.json
diagnostics/b2_review_layer/neutral_v2_veto_report.md
diagnostics/b2_review_layer/pass_watch_high_ret3_group_report.json
diagnostics/b2_review_layer/pass_watch_high_ret3_group_report.md
diagnostics/b2_review_layer/env_skeleton_top1_report.json
diagnostics/b2_review_layer/env_skeleton_top1_report.md
diagnostics/b2_review_layer/weak_neutral_top3_followup_report.json
diagnostics/b2_review_layer/weak_neutral_top3_followup_report.md
diagnostics/b2_review_layer/weak_final_tuning_report.json
diagnostics/b2_review_layer/weak_final_tuning_report.md
diagnostics/b2_review_layer/weak_top5_residual_negative_report.json
diagnostics/b2_review_layer/weak_top5_residual_negative_report.md
diagnostics/b2_review_layer/stable_patterns.json
diagnostics/b2_review_layer/stable_patterns.md
diagnostics/b2_review_layer/misclassified_samples.md
diagnostics/b2_review_layer/recommendations.json
```

每行至少包含：

```text
date, code, env, current_verdict, current_score, ret3, ret5, ret3_bucket,
trend_structure, price_position, volume_behavior, previous_abnormal_move, macd_phase,
signal, signal_type
```

### Phase 2：补全可解释因子

从当前五维开始扩展，不引入未来收益字段作为生产特征。

MACD 浪型因子：

```text
daily_macd_phase_type
daily_macd_wave_index
daily_macd_wave_stage
daily_macd_rising_or_falling
daily_macd_bottom_divergence
daily_macd_top_divergence
daily_macd_divergence_price_relation
weekly_macd_phase_type
weekly_macd_wave_index
weekly_macd_wave_stage
weekly_macd_bottom_divergence
weekly_macd_top_divergence
weekly_daily_combo_type
```

价格结构因子：

```text
price_vs_90d_high
price_vs_90d_low
price_vs_90d_mid
pullback_confirm_vs_90d_mid
pullback_confirm_vs_left_high
left_high_reclaim_ratio
left_high_hold_tolerance
current_top_vs_left_top
current_low_vs_left_bottom
```

均线和支撑因子：

```text
close_vs_zxdkx
close_vs_bbi
bbi_bias_state
close_vs_ma25
close_vs_ma60
ma25_vs_ma60
zxdkx_slope_5d
bbi_slope_5d
ma25_slope_5d
ma60_slope_5d
support_stack_type
bias1_bfq
bias2_bfq
bias3_bfq
bias_bucket
obv_bfq
obv_ratio_5d
obv_state
```

横盘和压缩因子：

```text
sideways_days
range_compression_20d
range_compression_40d
breakout_after_sideways
days_since_last_high
days_since_last_low
```

量能因子：

```text
volume_ratio_5d
volume_ratio_10d
breakout_volume_ratio
pullback_volume_ratio
volume_shrink_on_pullback
abnormal_volume_without_breakout
```

KDJ 因子：

```text
k_value
d_value
j_value
j_vs_k
j_vs_d
j_overheat
j_repair_from_low
kdj_cross_state
```

### Phase 3：环境内分层比较

每个环境单独比较：

```text
A+B vs D+E+F
A vs E/F
B vs D
```

每个环境输出：

```text
高涨幅组高频组合：已输出 environment_comparisons.json 和 stable_patterns.json/promising
低涨幅/负收益组高频组合：已输出 environment_comparisons.json 和 stable_patterns.json/risky
胜负不明确但样本多的组合：已输出 stable_patterns.json/mixed_high_sample
当前 PASS 命中的正例
当前 PASS 命中的负例
当前 WATCH 漏配的高涨幅例
当前 FAIL 漏配的高涨幅例
```

组合分析优先级：

```text
env + signal + signal_type + 日MACD浪型 + 周MACD浪型 + 价格回踩关系 + 量能状态 + 支撑斜率
```

### Phase 4：错配和漏配分类

诊断输出按三类组织：

```text
错配：当前 PASS，但 ret3/ret5 表现差。
漏配：当前 WATCH/FAIL，但 ret3 >= 5% 或 ret3 >= 10%。
排序错配：同一天 PASS+WATCH 池内，高涨幅票存在，但当前排序靠后。
```

每类给出：

```text
组合样本数
ret3>=5% 数量
ret3<=0% 数量
ret3 均值/中位数
ret5 均值/中位数
当前 verdict 分布
典型样本列表
```

### Phase 5：重建 Review 分层结构

生产 review 层最终拆为三层：

```text
1. environment profile
决定 weak/neutral/strong 下哪些形态允许进攻，哪些只能观察。

2. pattern family
识别具体形态族，例如：
- weak refined bottom repair
- neutral B3 low-macd rebound
- neutral B3 trend_start volume-confirm
- strong high-elastic trend_start
- high-wave top-divergence exhaustion
- failed breakout with heavy volume

3. ranking score
用于同一候选池内排序，目标是提高 ret3>=5% / ret3>=10% 的前排覆盖率。
```

建议 review 输出结构逐步演化为：

```json
{
  "environment": "neutral",
  "pattern_family": "neutral_b3_low_macd_rebound",
  "risk_family": "none",
  "quality_flags": [],
  "risk_flags": [],
  "review_score": 4.12,
  "rank_score": 4.35,
  "verdict": "PASS"
}
```

### Phase 6：实施顺序

优先改排序，后改 verdict：

```text
1. PASS+WATCH 内 rank_score
目标：每日 ret3 前5/前10 更靠前。

weak 当前优先在这一层推进：用 `weak_watch_rebound_volume_confirm` 和 `weak_watch_near_high_small_repair` 做 WATCH 内排序增强，同时对 `b3_rebound_extended_mixed`、`macd_w2_div_d4_repair`、`macd_w0_div_d4_repair` 等风险组合扣分。

2. WATCH -> PASS override
目标：放入当前漏配的高涨幅 WATCH。

weak 暂不做 broad override；只有单一形态族在离线报告中同时满足 ret3>0、ret5>0、ret3>=5 稳定且无 veto 时，才允许小样本试验。

3. PASS -> WATCH/FAIL
目标：剔除当前 PASS 负例。
```

每次只改一个形态族，必须列出新增正例、误伤样本和环境分层结果。

### Phase 7：验证指标

每次调整后至少输出：

```text
按环境：
PASS top3/top5 ret3/ret5 胜率
PASS top3/top5 ret3/ret5 均值、中位数
PASS+WATCH top5 ret3 均值
PASS+WATCH top10 ret3 均值
ret3>=5% 样本在 top5/top10 的覆盖率
ret3<=-5% 样本进入 top5/top10 的比例
```

错配指标：

```text
新增 PASS 中 ret3<=0 的数量
被降级 PASS 中 ret3>=5 的数量
新增 top5 中 ret3<=0 的数量
被挤出 top5 中 ret3>=5 的数量
```

当前优先级：

```text
1. [done] 建立 b2_review_layer_diagnostics.py
2. [done] 先分析 ret3>=5% vs ret3<=0%，按环境拆分。
3. [done] 先从当前五维 + signal/signal_type + MACD浪型做组合分层。
4. [done] 再逐步加入价格回踩、均线支撑、横盘、量能、KDJ。
5. [done] 加入 PostgreSQL `daily_indicators.extra_factors_jsonb` 的 BBI/BIAS/OBV，先验证 weak 排序增强。
6. [done] 针对 weak WATCH 单独输出 `weak_watch_positive_report`，拆 ret3>0、ret5>0、ret3>=5、ret3<=0 的候选升级组合和 veto/risk 条件。
7. [done] 拆出 neutral WATCH 专项离线报告；当前未发现足够干净的 neutral WATCH -> PASS 组合，暂不生产放宽。
8. [done] 重跑已实现的 weak 小范围 override 和 weak/strong 排序调整，输出 Phase 7 指标；确认 weak 新增 PASS 没有 ret3<=0，neutral/strong PASS 指标不变。
9. [done] 继续把 strong/neutral 剩余负例组合整理为 rank_score 扣分或 veto 候选；weak 仅观察 `weak_watch_near_high_small_repair` 的 5 日稳定性，暂不继续 broad PASS 扩张。
10. [done] 固化 neutral 因子正向作用报告，识别多数 ret3>5 样本拥有且有 uplift 的正向骨架。
11. [done] 对 `strong_neutral_risk_report` 中的 strong B2 近高位放量红柱负例做 rank_score 扣分离线模拟；strong_v3 未优于 strong_v1，不进入生产候选。neutral 以 `neutral_factor_effect_report` 的正向骨架叠加四个 veto 候选做 WATCH 内 `neutral_v1_rank` 实验，并输出 `neutral_v1_stability_report`。
12. [done] 基于 `neutral_v1_stability_report` 中 22 个 top3 负例，继续拆 `B2|trend_start` / `B3|trend_start` 的 factor + MACD 组合，形成 `neutral_v2_veto_report`；结果只改善 top5，不足以进入生产。
13. [done] 统计 PASS+WATCH 中 ret3>=5 和每日最高涨幅样本，输出 `pass_watch_high_ret3_group_report`；确认基础骨架需要按环境分别找，strong 主骨架覆盖最高，neutral/weak 需要多骨架组合。
14. [done] 输出 `env_skeleton_top1_report`，以各环境自己的 priority skeleton groups 做 PASS+WATCH top1 模拟；weak 明显改善，strong 变差，neutral 混合，因此不能共用一套骨架权重。
15. [done] 冻结 strong_v1_rank 后输出 `weak_neutral_top3_followup_report`；确认 neutral_v1 的 top3 ret3>=5 命中率和日命中率提升最干净，weak_v3/weak_v4 虽提升命中率但 top3 ret3<=0 仍偏高。
16. [done] 输出 `weak_final_tuning_report`，weak 本轮调参完成：top3 采用 `weak_v3_minus_reclaim`，top5 仅参考 `weak_v4_reference`，不扩 weak PASS、不改 production verdict。
17. [done] 三类环境冻结完成：strong=`strong_v1_rank`，weak=`weak_v3_minus_reclaim`，neutral=`neutral_v1_rank`；neutral_v2 和 weak_v4 只保留为 top5/风险观察，不作为 top3 主线。
18. [done] 三类环境冻结方案已实现到 Rust native review selection score：strong 使用既有 strong_v1 加分，weak 完整补齐 weak_v3_minus_reclaim 分数链且停止 WATCH->PASS override，neutral 增加 neutral_v1 正向骨架/风险扣分；不改 review verdict。
19. [done] 已重跑当前 `~/.agents/skills/stock-select/runtime` 的 2026-03-02..2026-05-29 b2 review，并复算实现后 summary 排序；weak top3 ret3>=5 回到 20/72，但 top3 ret3<=0 和 top5 ret3>=5 仍弱于离线预期。
20. [done] 已对齐生产 `midline_state` 与 diagnostics 口径，补齐 `reclaim_volume/pullback_confirm`；weak top3 ret3>=5=21/72、ret3<=0=40/72，top3 目标完成。
21. [next] 继续只针对 weak top5 剩余差距做检查：当前 top5 ret3>=5=30/120、ret3<=0=68/120，仍弱于离线 31/120、65/120。优先看 top5 中 `no_risk` 负例是否需要新增更窄 veto，不扩 PASS。
```

## 验证基线

声明阶段性进展前运行：

```bash
cargo fmt --check
cargo test --quiet
python3 -m py_compile scripts/check_charts.py scripts/compare_screen.py scripts/compare_review.py scripts/render_charts.py
python3 -m py_compile scripts/backfill_baseline_reviews.py scripts/review_top3_win_stats.py scripts/b2_review_layer_diagnostics.py
python3 -m unittest tests/test_b2_review_layer_diagnostics.py
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
