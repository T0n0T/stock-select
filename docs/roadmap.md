# stock-select-rs 新 CLI Roadmap

本文记录 `/home/tiger/Documents/agents/stock-select-new` 的新 Rust CLI 当前状态，以及距离替代旧 `stock-select-rs` 生产流程还差哪些能力。

## 当前状态

新项目已经具备独立 Rust crate、`stock-select-rs` binary、基础命令面和 `src/engine/` model-first 架构骨架。

当前筛选 parity 范围收敛为 **只实现 b2**。B3 后续单独评估；B4、B5 不接入新 Rust CLI 生产路径。

已存在命令：

```text
stock-select-rs screen
stock-select-rs chart
stock-select-rs review
stock-select-rs review-merge
stock-select-rs review-list
stock-select-rs run
stock-select-rs completions
```

当前已实现的真实能力：

1. Method capability matrix。
2. `review/run --method b1` 显式报错，不回退 baseline review。
3. `select/<key>.<method>/` artifact layout。
4. b2 model-first `run` 的 artifact 写入闭环。
5. `--intraday` artifact key 支持：`<date>.intraday.b2`。
6. `review-list` 优先读取 `select/<key>.b2/display.json`，并在 DSN 可用时按 code 从 `instruments` 回填缺失股票名称和行业。
7. b2 `run` 可通过 `lightgbm3` 读取 runtime 默认 LightGBM `model.txt` 和 metadata，按真实 LightGBM runtime 分数生成 `ranked.json`。
8. 有模型推理时写出 `feature_vectors.json` diagnostics，便于后续 parity 定位。
9. runtime root 可通过 `--runtime-root`、`STOCK_SELECT_RUNTIME_ROOT` 或当前目录 `.env` 指定；都未设置时回退旧 CLI 默认 `$HOME/.agents/skills/stock-select/runtime`。
10. 配置解析兼容旧 CLI：CLI 参数 > shell 环境变量 > 当前目录 `.env`，已支持 `STOCK_SELECT_RUNTIME_ROOT`、`POSTGRES_DSN` 和 `TUSHARE_TOKEN` 解析入口。
11. `src/engine/` 已承载 model-first shared types、presentation、inference metadata/vector builder、LLM annotation merge、structured logging。
12. `run --method b2` 省略 `--candidates-path` 时可自动调用 `screen`，EOD 复用 prepared cache 或通过 `POSTGRES_DSN` 查询数据源生成候选；`--intraday` 会通过 Tushare `rt_k` 快照生成盘中候选后继续 selection run。
13. `screen/run --method b2 --pool-file <path>` 支持 custom pool：读取文件中的股票代码，标准化去重后与 prepared universe 求交集，再执行 b2 strategy。
14. `screen/run --method b2 --pool-source custom` 支持从 `STOCK_SELECT_POOL_FILE` 或 `<runtime>/custom-pool.txt` 解析 custom pool 文件。
15. b2 strategy 已补齐旧 Rust B2 的同一 J 上行周期 raw signal 去重：同一轮只保留第一次 raw B2，不重复发出 B2 候选。
16. b2 strategy 已补齐旧 Rust B2 的 `above_lt` 过滤：非新股窗口要求收盘高于 14/28/57/114 均线组合长期参考。
17. b2 strategy 已补齐旧 Rust B2 的 `tr_ok` 趋势过滤：支持交叉 honeymoon、breakaway、长期参考稳定性和支撑条件。
18. b2 screening 已新增成熟趋势启动 golden fixture，并补齐旧 Rust B2 的关键 stats 口径：`eligible`、`fail_no_pick_date`、`fail_insufficient_history`、`fail_no_signal`、`selected`、`selected_b2`。
19. `screen --method b2` 已支持 prepared cache 作为独立数据源：命中 cache 时不需要解析 `POSTGRES_DSN`；缺 cache 需要查询数据库时仍稳定报 `A database DSN is required.`。
20. `run --method b2` 会在 stderr 打印进度和内部阶段，包括启动参数、候选来源、模型解析、候选加载、prepared history 注入检查、因子计算、排序、chart/review task 生成和 artifact 写入；stdout 仍保留最终完成行，便于脚本消费。
21. `chart --method b2` 已迁回旧 CLI 风格：读取 prepared cache 后生成 payload，按 `--chart-workers` 分片并发调用 `scripts/render_charts.py` 绘制 PNG；`--intraday` 读取独立的 `.intraday` prepared cache。
22. intraday 数据源已迁入 Tushare `rt_k` provider：按 `*.SH`、`*.SZ`、`*.BJ` 批量拉取，支持中英文字段归一化，并把盘中快照合并进历史窗口生成候选。
23. prepared cache 已支持 EOD 与 intraday 同日隔离：EOD 使用 `prepared/<date>.bin`，intraday 使用 `prepared/<date>.intraday.bin`，避免盘中运行覆盖收盘缓存。
24. `run --method b2` 已补齐旧 CLI 兼容参数 `--environment-state`、`--environment-reason`、`--model-path`、`--model-feature-metadata-path`、`--record`、`--record-window-trading-days` 和 `--recompute`；其中模型路径覆盖 LightGBM artifact 解析，`--recompute` 透传自动 screen，环境参数解析后写入 `run.json` 并注入 `factors.json` 的 `env` 分类因子。EOD 未手动传环境时会用 `POSTGRES_DSN` 读取 `daily_index` 中的上证指数 `000001.SH` 与国证 2000 `399303.SZ` 近约 180 天历史，按旧 Rust CLI 的指数评分口径自动评估并持久化环境；评估失败时只允许已有历史环境覆盖，否则明确失败，不再静默写 `default_neutral`。
25. `review --method b2` 已接受 `--environment-state`、`--environment-reason`、`--model-path`、`--model-feature-metadata-path`、`--record` 和 `--record-window-trading-days`，并把这些兼容参数写入 `llm_tasks.json` 顶层 metadata；未手动传环境时与 `run` 一样执行 EOD 指数环境评估并写完整 environment metadata；不恢复旧 baseline review，不改变 `model_rank`。
26. 为对齐旧 CLI 命名，selection run artifact 目录已从 `selection_runs/` 收敛为 `select/`；模型流水线模块已从 `src/selection_engine/` 更名为 `src/engine/`；b2 筛选策略核心已拆到 `src/strategies/b2.rs`，`src/screening.rs` 保留数据源、pool 和写候选产物 orchestration。
27. 已新增 `src/environment.rs`，保持旧 CLI runtime 环境产物结构：`environment/history.jsonl`、`environment/latest.json`、`environment/daily/<date>.<state>.json` 和 `.environment.lock`。已迁入旧 Rust CLI 的 `score_index_environment`、`score_based_state`、`rule_based_state`、`vote_based_state`、`reason` 和 `total_score` 口径。EOD `run/review` 会持久化 resolved environment；`--intraday` 手动传环境时不落盘，未传时只读取上一交易日已持久化环境并在 stderr 提示可用 `--environment-state` 覆盖，找不到上一交易日环境时明确失败，盘中不做临时指数评估。
28. LightGBM 维护脚本已迁入 `scripts/ml/`：`backfill_candidates.py` 可按数据库交易日并发补齐指定 method 的历史 EOD candidates，当前默认 `--method b2`；`build_rank_dataset.py` 默认从当前 `candidates/<date>.<method>.json` 读取，重新计算训练特征和 ret labels；`--source select` 可回放线上 run 特征快照。训练/score diagnostics 默认写 `diagnostics/ml/<method>/`，发布脚本从当前 `.env` 的 `STOCK_SELECT_RUNTIME_ROOT` 解析 runtime，并发布到 `<runtime>/models/<method>/`；Rust 默认模型解析已移除旧长目录回退，只认当前主目录或显式 override。

当前 b2 `screen` 已接入 EOD 数据源首版：

```bash
stock-select-rs screen \
  --method b2 \
  --pick-date 2026-05-25
```

省略 `--runtime-root` 时会先读取 `STOCK_SELECT_RUNTIME_ROOT`，再读取当前目录 `.env`，都未设置时使用 `$HOME/.agents/skills/stock-select/runtime`。`POSTGRES_DSN` 解析顺序为 CLI 参数 > shell 环境变量 > 当前目录 `.env`。命令会优先复用匹配 metadata 的 prepared cache；缺 cache 或 `--recompute` 时从 PostgreSQL `daily_market` 拉取旧 screen window，写入 prepared cache，并输出 `<runtime>/candidates/<date>.b2.json`。

当前 b2 `run` 支持两种候选输入：显式外部候选 JSON，或省略 `--candidates-path` 自动执行 EOD `screen`：

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --candidates-path <candidates.json>

stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25
```

如果省略 `--runtime-root`，runtime root 解析顺序为 `STOCK_SELECT_RUNTIME_ROOT` shell 环境变量 > 当前目录 `.env` > 旧默认：

```text
$HOME/.agents/skills/stock-select/runtime
```

`POSTGRES_DSN` 和 `TUSHARE_TOKEN` 的解析顺序与旧 CLI 一致：CLI 参数 > shell 环境变量 > 当前目录 `.env`。EOD 缺 prepared cache 时使用 `POSTGRES_DSN` 读取 `daily_market`；intraday 自动 screen/run 使用 `TUSHARE_TOKEN` 调用 Tushare `rt_k` 快照。

执行后写入：

```text
<runtime>/select/2026-05-25.b2/run.json
<runtime>/select/2026-05-25.b2/candidates.json
<runtime>/select/2026-05-25.b2/factors.json
<runtime>/select/2026-05-25.b2/feature_vectors.json  # 有模型产物时写出
<runtime>/select/2026-05-25.b2/ranked.json
<runtime>/select/2026-05-25.b2/display.json
```

当前 LightGBM 训练和维护脚本（以 b2 为例）：

```bash
METHOD=b2

uv run scripts/ml/backfill_candidates.py \
  --method "$METHOD" \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE" \
  --workers 4

uv run scripts/ml/build_rank_dataset.py \
  --method "$METHOD" \
  --runtime-root "$STOCK_SELECT_RUNTIME_ROOT" \
  --source candidates \
  --start-date "$TRAIN_START_DATE" \
  --end-date "$TRAIN_END_DATE"

uv run scripts/ml/train_rank_lgbm.py \
  --method "$METHOD" \
  --dataset "diagnostics/ml/$METHOD/rank_dataset.csv" \
  --output-dir "diagnostics/ml/$METHOD/model" \
  --feature-set raw_numeric

uv run scripts/ml/export_lgbm_scores.py \
  --method "$METHOD" \
  --model-output-dir "diagnostics/ml/$METHOD/model"

uv run scripts/ml/promote_lgbm_model.py \
  --method "$METHOD" \
  --candidate-dir "diagnostics/ml/$METHOD/model" \
  --dry-run \
  --require-report
```

补候选脚本默认跳过已有 `<runtime>/candidates/<date>.<method>.json`，不会把 `.intraday.<method>.json` 当作 EOD 训练样本；命令行不携带 DSN/token。发布脚本默认读取当前目录 `.env` 中的 `STOCK_SELECT_RUNTIME_ROOT`，目标为 `<runtime>/models/<method>/`；未传 `--runtime-root` 且 `.env` 没有 runtime 时会失败，避免误发布到旧默认目录。`diagnostics/ml/<method>/` 下的 score CSV、report 和候选模型只用于研究/维护，不进入 Rust 生产 predict 路径。

## 当前能力边界

### 已可用

- `run --method b2`：可从 `--candidates-path` 读取候选；如果 runtime 默认模型产物完整，则读取 `model.txt` 和 `model_metadata.json`，按真实 LightGBM 分数排序并生成 selection artifacts。可通过 `--model-path` 与 `--model-feature-metadata-path` 成对覆盖模型产物；`--recompute` 会强制自动 screen 重新读取数据源；`--environment-state`、`--environment-reason` 会解析为旧兼容 environment artifact，并注入 `factors.json` 的 `env` 因子；`--record` 和 `--record-window-trading-days` 写入 `run.json` 元数据。
- `run --method b2 --intraday`：省略 `--candidates-path` 时通过 Tushare `rt_k` 生成 `<runtime>/candidates/<date>.intraday.b2.json`，写入 `select/<date>.intraday.b2/`。
- `chart --method b2 --pick-date <date>`：读取 selection display artifact 和 prepared cache 历史序列，通过 Python renderer 生成 `<runtime>/charts/<artifact_key>.b2/<code>_day.png`；`--intraday` 读取 `.intraday` prepared cache。
- `review --method b2 --pick-date <date>`：读取 display artifact，按 `--limit` 生成 `llm_tasks.json`，并初始化空 `llm_annotations.json`；兼容 `--environment-state`、`--environment-reason`、`--model-path`、`--model-feature-metadata-path`、`--record` 和 `--record-window-trading-days` 写入 task metadata；不调用外部 LLM，不改变 `model_rank`。
- `review-merge --method b2 --pick-date <date>`：读取 `llm_annotations.json`，把 annotation 合并回 `display.json`，保留原模型排序。
- `review-list --method b2`：如果 display artifact 存在，则按模型排名展示，支持 `--limit`；输出列为 `rank code name industry model_score llm_action risk_flags`。display 行缺少 `name` 或 `industry` 且 DSN 可用时，会按旧 CLI 口径从 `instruments` 回填股票名称和行业。没有 DSN 时仍展示 `-`，不为了展示信息强制连库。
- `completions --shell <bash|zsh|fish|powershell|elvish>`：通过 `clap_complete` 生成 shell completion。
- `review/run --method b1`：明确不可用，保持 model-first 边界。

### 仍是占位或未完整接入

- `screen`：b2 EOD 首版已接 PostgreSQL `daily_market`、prepared cache 复用/写入和候选文件输出；intraday 首版已接 Tushare `rt_k` 快照并写入 `.intraday` prepared/candidates artifacts；完整旧 b2 prepare/strategy parity 仍需继续补齐。
- `chart`：已接旧 CLI 风格 Python renderer，使用 prepared cache 的真实 OHLC/指标序列生成 PNG；尚未补 chart existence checks。
- `review`：已有 LLM task artifact 生成；尚未接外部 LLM 调用、raw response 保存和自动 annotation 生产。
- `review-merge`：已有 annotation 合并到 display 的最小实现；尚未接更完整的 review audit/final action 输出。
- `run`：b2 EOD/intraday 已可自动执行 screen/factors/inference/display，并串接 chart 与 review task artifact；尚未自动执行 review-merge。
- `intraday`：artifact key、候选文件、prepared cache、history 注入和 chart 均支持 `.intraday`；CLI 生产路径已通过 `daily_market` 查询 `pick_date` 之前的最大 `trade_date` 作为上一交易日，测试 wrapper 仍保留 `pick_date - 1 day` 的兼容默认。

## 距离新 CLI 完整实现还差多少

按“能替代旧仓库日常 b2 生产 workflow”衡量，当前约完成 **70% 到 78%**。

已经完成的是架构边界、artifact contract、CLI guard、b2 run 闭环、`lightgbm3` runtime 推理、review-list 新 artifact 读取、缺失股票名称/行业回填、旧 CLI Python chart renderer、review task artifact、review-merge annotation 合并、intraday `rt_k` 快照接入、上一交易日 DB resolver 和 shell completion 生成。缺口主要集中在 chart existence checks、外部 LLM 调用、生产 intraday 细节、完整旧 b2 parity 和性能/迁移验证。

## 剩余 Roadmap

### P0: 让 b2 run 成为真实模型排序流程（已完成首版）

目标：`run --method b2` 不再依赖外部 `model_score`，而是读取 runtime model artifacts 并执行真实 LightGBM predict。

任务：

1. 接入 `lightgbm3` LightGBM runtime predictor。
2. 读取 `models/b2/model.txt`。
3. 读取 `model_metadata.json`，按 metadata 构建 feature vector。
4. 把 `ranked.json` 的 `model_score/model_rank` 改为真实预测结果。
5. 写入 feature vector diagnostics，便于 parity 定位。
6. 增加 fixture 测试，覆盖模型 artifact 完整、缺失、半部署三类情况。

完成后进度约到 **50%**。

当前状态：首版已完成。`run --method b2` 要求 runtime 默认目录 `models/b2/` 存在完整 `model.txt` 和 `model_metadata.json`，会通过 `lightgbm3::Booster::from_file` 加载 LightGBM runtime、按 metadata 构建 feature vector、写出 `feature_vectors.json`，并用真实 runtime 预测分数生成 `ranked.json` 的 `model_score/model_rank`。解析逻辑只读取当前主目录 `models/b2/`，也支持成对显式传入 `--model-path` 和 `--model-feature-metadata-path`；两个模型文件都不存在时报 `missing default b2 model artifacts`；只存在其中一个文件继续报 `incomplete default b2 model artifacts`。旧自实现 LightGBM text parser 已从生产路径移除。

### P1: 接入 b2 candidate screening

目标：`screen --method b2` 和 `run --method b2` 能自己产生候选，不再要求 `--candidates-path`。

任务：

1. 设计 runtime data source 参数：prepared cache、数据库、或文件 fixture。
2. 迁移/重写 b2 screening adapter。
3. 输出 `select/<key>.b2/candidates.json`。
4. 支持 `--pool-file`、`--pool-source` 或等价参数。
5. 对齐旧 CLI 的日常筛选参数和默认 runtime layout。

完成后进度约到 **60%**。

当前状态：已完成配置兼容、prepared cache 读取/写入、b2 EOD screen 首版数据源接入、intraday `rt_k` 首版接入和环境评分完整迁移。新 CLI 已迁入旧 CLI 的默认 runtime root，并新增 `STOCK_SELECT_RUNTIME_ROOT` 覆盖入口；`screen/run/review-list` 省略 `--runtime-root` 时会按 CLI 参数 > shell 环境变量 > 当前目录 `.env` > `$HOME/.agents/skills/stock-select/runtime` 解析 runtime root；`POSTGRES_DSN` 和 `TUSHARE_TOKEN` 支持 CLI 参数、shell 环境变量和 `.env` 解析，优先级为 CLI > shell env > `.env`。已新增旧 prepared cache 路径契约、`SSPRBIN1` 二进制 decoder/encoder 和 metadata 校验；EOD cache 使用 `<runtime>/prepared/<date>.bin`，intraday cache 使用 `<runtime>/prepared/<date>.intraday.bin`，二者可同日并存。`screen --method b2` 会优先复用匹配 EOD cache，缺 cache 或 `--recompute` 时从 PostgreSQL `daily_market` 拉取旧 screen window，并写回 prepared cache 与 `<runtime>/candidates/<date>.b2.json`；`screen --method b2 --intraday` 会读取 `TUSHARE_TOKEN`，先通过 `daily_market` 查询上一交易日，再按 `*.SH`、`*.SZ`、`*.BJ` 拉取 Tushare `rt_k` 快照，将快照合并进历史窗口，写入 `.intraday` prepared cache 与 `<runtime>/candidates/<date>.intraday.b2.json`。EOD `run/review` 未手动传环境时会从 `daily_index` 拉取上证指数和国证 2000 历史并自动评估环境，写入旧兼容 environment 产物、`run.json`、`llm_tasks.json` 和 `factors.json` 的 `env` 因子；盘中未手动传环境时只读取上一交易日已持久化环境，不做临时指数评估。`screen/run --method b2 --pool-file <path>` 已支持 custom pool 文件，按旧 CLI 口径标准化代码、去重并与 prepared universe 求交集；`screen/run --method b2 --pool-source custom` 已支持 `STOCK_SELECT_POOL_FILE` 和 `<runtime>/custom-pool.txt` fallback；b2 strategy 已补齐旧 Rust B2 的同一 J 上行周期 raw signal 去重、`above_lt` 长期参考过滤和 `tr_ok` 趋势过滤，并新增成熟趋势启动 golden fixture 锁定候选和关键 stats；`run --method b2` 可省略 `--candidates-path` 自动执行 EOD 或 intraday screen，并读取 screen 产物的 `candidates` 数组继续 selection run；候选缺少 `history` 时会按 EOD/intraday mode 从对应 prepared cache 自动注入 `history`，再进入 b2 factor provider。完整旧 b2 screening parity、生产级 intraday 细节和真实数据库指数表 schema 的生产验证仍需继续补齐；B3/B4/B5 parity 不属于当前实现范围。

### P2: 接入 b2 factor extraction

目标：从候选和行情数据计算 b2 LightGBM 所需 raw factors。

任务：

1. 定义 b2 factor provider trait。
2. 迁移现有 b2 raw factors 计算逻辑。
3. 写 `factors.json`，包含 factors 和 diagnostics。
4. 增加 factor fixture/golden 测试。
5. parity 失败时能按字段定位。

完成后进度约到 **70%**。

当前状态：已完成 embedded history raw factor 公式的首轮迁移，并接入 prepared cache history 注入。新增 b2 factor provider 边界，`run --method b2` 现在通过候选 payload 提取 `factors.json`：支持嵌套 `factors` 对象、顶层 primitive raw factor 字段，以及 `close`、`turnover_n`、`signal`、`env` 等筛选字段，并写入 `factor_source/factor_count` diagnostics。候选 payload 或 prepared cache 注入的 `history` 会按旧 Rust/Python 口径计算 b2 raw factors，包括价线距离、量能/换手、120 日箱体位置/宽度/距离、20 日最高收盘距离、MACD hist 比例/变化/3 日斜率、range compression、abnormal volume event 和若干 0/1 flags。`ma25/zxdq/zxdkx` 和 MACD 字段可由 close 自动推导；显式历史字段存在时优先使用显式值。后续仍需增加旧 Rust/Python 逐字段 parity fixture，并接数据库/Tushare fallback 数据源。

### P3: 完成经典 run orchestration

目标：`run --method b2` 成为完整流水线入口。

目标流程：

```text
screen
-> chart
-> factors
-> model inference
-> ranked artifact
-> optional LLM tasks
-> optional review merge
-> display artifact
```

任务：

1. `run` 支持自动调用 screen/factors/inference。
2. chart 可选生成，并记录 chart paths。
3. 明确 `--skip-chart`、`--review-limit`、`--llm-review-limit` 等参数边界。
4. run 输出稳定 summary，便于脚本调用。
5. intraday run 使用实时/快照数据源，并写 `.intraday` artifacts。

完成后进度约到 **80%**。

当前状态：已完成 EOD 与 intraday 首版 orchestration。`run --method b2` 仍保留 `--candidates-path` 显式覆盖；省略时会按 mode 调用 `screen` 生成 `<runtime>/candidates/<date>.b2.json` 或 `<runtime>/candidates/<date>.intraday.b2.json`，再进入 factors/model inference/ranked/display artifact 写入；`--pool-file` 会传递到自动 screen 分支。run 过程会在 stderr 输出 `[run]` 和 `[selection]` 前缀的阶段进度，stdout 只输出最终 `selection run complete` 行。selection 完成后会自动生成 chart artifacts 和 `llm_tasks.json`/空 `llm_annotations.json`，供 review-list/review-merge 后续消费；review-merge 仍作为显式独立命令执行，不在 run 中自动改变 display。

### P4: LLM review 和 review-merge

目标：LLM 只做 annotation，不改变 `model_rank`。

任务：

1. `review --method b2` 读取 ranked/display artifacts。
2. 只对 topN 生成 LLM tasks。
3. 保存 `llm_tasks.json`、`llm_annotations.json` 和 raw responses。
4. `review-merge` 合并 annotation 到 display artifact。
5. `final_action` 独立于 `model_rank`，不恢复旧 baseline verdict 主导逻辑。

完成后进度约到 **88%**。

当前状态：已完成最小 artifact 流程。`review --method b2 --pick-date <date>` 读取 `display.json`，按 `--limit` 生成 `llm_tasks.json`，并初始化空 `llm_annotations.json`；`review-merge --method b2 --pick-date <date>` 读取 annotation 并合并回 `display.json`，不改变 `model_rank`。外部 LLM 调用、raw response 保存和 final action audit 仍未接入。

### P5: chart 命令和 artifact 对齐

目标：`chart --method b2` 能按候选生成图表，并被 review/run 引用。

任务：

1. 设计 chart output layout。
2. 接入受控 chart runner 或 Rust-native chart path。
3. `require_chart_files` 类行为迁移到新 CLI。
4. `review` task 引用 chart path。
5. 增加 chart existence checks。

完成后进度约到 **92%**。

当前状态：已完成旧 CLI 风格 Python renderer 接入。`chart --method b2 --pick-date <date>` 读取 `display.json` 和 prepared cache，写出 payload 分片到 `<runtime>/charts/`，通过 `uv run scripts/render_charts.py --input <payload>` 并发生成 `<runtime>/charts/<artifact_key>.b2/<code>_day.png`；`chart --intraday` 读取 `.intraday` prepared cache；`review` task 直接按确定性路径引用 PNG，不再需要 `charts.json` 中间索引。chart existence checks 仍需补齐。

### P6: CLI 参数兼容和 shell completion

目标：外部命令面替代旧 `stock-select-rs`。

任务：

1. 对齐旧 CLI 的 `screen/chart/review/review-list/run` 参数。
2. 保留用户已依赖的默认 runtime root、pick date、method 行为。
3. `completions` 输出 bash/zsh/fish completion。
4. 增加 CLI snapshot tests。
5. 对错误信息做稳定化，避免脚本难以判断。

完成后进度约到 **96%**。

当前状态：`completions --shell <shell>` 已通过 `clap_complete` 输出 completion；`run` 已补齐 `--environment-state`、`--environment-reason`、`--model-path`、`--model-feature-metadata-path`、`--record`、`--record-window-trading-days` 和 `--recompute`；`review` 已补齐对应 metadata 参数但不恢复 baseline review。CLI 参数兼容仍需继续对齐旧项目脚本，包括 `--no-progress`、`review-merge --codes` 和 `analyze-symbol` 等剩余缺口。

### P7: LightGBM 训练/维护脚本（当前验证 b2，已完成首版）

目标：保留 Python 训练和维护脚本作为研究/发布工具，但不进入 Rust 生产 predict 路径。

当前状态：已完成。`scripts/ml/backfill_candidates.py` 可从 `daily_market` 查询交易日，并发执行 `screen --method <method> --pick-date <date>` 补齐历史 EOD candidates，当前默认 b2，默认跳过已有 candidate，支持 dry-run 和失败汇总。`scripts/ml/build_rank_dataset.py` 默认读取当前 `candidates/<date>.<method>.json`，用数据库行情重算 context/raw factors 并合并前向收益 label 后输出 `diagnostics/ml/<method>/rank_dataset.csv`；显式 `--source select` 时可读取 `select/<date>.<method>/` 的 `run.json`、`display.json` 和 `factors.json`，用于回放线上实际 run 的特征快照。`train_rank_lgbm.py` 支持 `--method`、feature set、rolling validation、report 输出和 metadata 构建。`model-maintenance` skill 已补充受限自迭代调参约定：训练/重训默认先跑 baseline，再最多比较 12 组小网格 trial，按 rolling 指标选择候选，只做 export 和 promote dry-run，不自动发布；训练结束必须汇报 dataset 覆盖、最佳 trial、rolling 指标、baseline 对比、top features、dry-run 状态、发布建议和剩余风险。`export_lgbm_scores.py` 输出 score CSV、summary，并写候选 `model.txt` 和 `model_metadata.json`。`promote_lgbm_model.py` 支持 metadata/report 校验、dry-run、发布、归档、回滚和 `model_card.json`，默认从当前 `.env` 读取 `STOCK_SELECT_RUNTIME_ROOT` 并发布到 `<runtime>/models/<method>/`。新增 `model-maintenance` skill 和 references 记录 operator 流程；当前章节已验证 b2，后续可继续扩展 b1。

剩余边界：真实数据库 dataset 构建、完整训练和发布仍需 operator 在有 DSN 和数据的环境中执行；score CSV、baseline evaluator、rolling diagnostics 只作为研究材料，不参与 `stock-select-rs run/review` 排序。

### P8: parity、性能和迁移收尾

目标：证明新 CLI 可替代旧 CLI，并安全切换。

任务：

1. b2 Rust/Python 或旧 Rust path parity fixture。
2. runtime artifact layout 对齐检查。
3. intraday snapshot fixture。（首版已覆盖 `rt_k` 字段归一化、市场通配符批量拉取、API 错误、空 token 和同日快照替换。）
4. 性能基准：screen/factors/inference/run。
5. 文档和 operator workflow 更新。
6. 维护脚本在真实 runtime 上做一次 dry-run、发布和回滚演练。

完成后进度约到 **100%**。

## 推荐下一步

优先顺序：

1. P1/P3：补 intraday 生产数据跑通、run_id/fetched_at 细节和旧 CLI 参数细节。
2. P2/P8：补 b2 raw factor 与旧仓库逐字段 parity fixture，并做 2026-06-03 等真实样本回归。
3. P5：补 chart existence checks 和与旧图表产物的尺寸/文件集合 smoke check。
4. P4：再接外部 LLM annotation、raw response 保存和 final action audit。

原因：模型预测、筛选、因子、排序、chart/review task 和 intraday 首版已经形成主链路；下一步最影响可替代性的，是生产日期/交易日细节、旧实现 parity 和可观察的端到端回归。

## 当前验证命令

Rust 改动后运行：

```bash
cargo fmt --check
cargo test --quiet
```

当前已通过上述验证。
