# stock-select

用于承载 `stock-select` 技能与 CLI 的独立仓库。

当前仓库的目标是提供一个可单独运行的 A 股初筛流程，包括：

- 从 PostgreSQL 读取 `daily_market` 数据
- 运行确定性的 `b1` / `b2` / `dribull` / `hcr` 初筛
- 为候选股票生成日线 PNG 图
- 对候选股票执行本地 review 流程

当前 `dribull` 筛选流程已经改为两阶段：

- 第一阶段只做非 `MACD` 结构预筛
- 第二阶段只做日线 / 周线 `MACD` 浪型识别
- `review` 与 LLM review task 会复用同一套浪型理解，但最终 review JSON schema 保持稳定

当前 `b1` 的改动只发生在 review 层：

- `screen` 阶段保持原有初筛条件不变
- baseline review 改为专用 `b1` reviewer，并复用与 `b2` 相同的周线 / 日线 `MACD` 浪型识别核心
- `b1` 的 baseline `comment` 会压缩写出周线 / 日线浪型判断
- `b1 total_score` 现已计入 `macd_phase`
- `b1` 的 LLM review task 会额外写入浪型文本上下文，并改为使用 `prompt-b1.md`

该仓库与 `/home/pi/Documents/agents/StockTradebyZ` 分离，后者当前仅作为迁移期间的只读参考。

## 安装

开发环境安装：

```bash
uv sync
```

`chart`/`run` 通过 `mplfinance` 直接导出 PNG，不再依赖 Kaleido 或 Chrome；变更依赖后重新执行 `uv sync` 即可安装。

在项目目录中直接运行 CLI：

```bash
uv run stock-select --help
```

安装为当前机器可直接调用的 CLI：

```bash
uv tool install .
```

如果已经安装过，并且需要用本地最新代码覆盖安装：

```bash
uv tool install --reinstall .
```

安装仓库内置的 `stock-select` skill 到 `~/.agents/skills/`：

```bash
mkdir -p ~/.agents/skills/stock-select && cp -R /home/pi/Documents/agents/stock-select/.agents/skills/stock-select/. ~/.agents/skills/stock-select/
```

## 基本用法

常用命令：

```bash
uv run stock-select screen --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select screen --method b2 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select screen --method dribull --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select screen --method hcr --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select chart --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select chart --method b2 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select chart --method dribull --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select chart --method hcr --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select review --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select review --method b2 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select review --method dribull --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select review --method hcr --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select record-watch --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select record-watch --method b2 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select record-watch --method dribull --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select record-watch --method hcr --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select analyze-symbol --method b2 --symbol 002350.SZ --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select run --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select run --method b2 --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select run --method dribull --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select run --method hcr --pick-date YYYY-MM-DD --dsn postgresql://...
```

## DSN 读取顺序

数据库 DSN 支持以下来源：

- 命令行参数 `--dsn postgresql://...`
- 进程环境变量 `POSTGRES_DSN`
- 当前工作目录下 `.env` 文件中的 `POSTGRES_DSN`

优先级如下：

```text
--dsn > POSTGRES_DSN 环境变量 > 当前目录 .env
```

## 进度输出

- 默认会把进度信息输出到 `stderr`
- 最终产物路径仍输出到 `stdout`
- 如果你只想要最终路径，可以使用 `--no-progress`

典型进度输出类似：

```text
[screen] connect db
[screen] fetch market window
[screen] prepare 500/5497 symbol=000001.SZ elapsed=12.4s
```

## Custom 初始票池文件格式

当使用 `--pool-source custom` 时，CLI 会从 `--pool-file PATH`、环境变量 `STOCK_SELECT_POOL_FILE`，或默认文件 `~/.agents/skills/stock-select/runtime/custom-pool.txt` 读取初始股票池。

文件格式规则：

- 文件内容按任意空白字符分隔，空格、换行、Tab 都可以
- 每个 token 应为一个股票代码
- 支持直接写标准 TS 代码，例如 `600519.SH`、`300750.SZ`
- 也支持只写 6 位代码，CLI 会自动补交易所后缀，例如：
  - `600519` -> `600519.SH`
  - `300750` -> `300750.SZ`
  - `830799` -> `830799.BJ`
- 也支持按行写带市场前缀和名称的列表，CLI 会从每行提取第一个 6 位数字代码，例如：
  - `SH603876 鼎胜新材` -> `603876.SH`
  - `SZ002008 大族激光` -> `002008.SZ`
- 重复代码会自动去重
- 无法识别的 token 会被忽略
- 如果过滤后一个有效代码都没有，CLI 会报错

示例：

```text
600519 300750 830799
002594.SZ
601318.SH
```

也可以使用这种每行一只、附带名称的格式：

```text
SH603876 鼎胜新材
SZ002008 大族激光
SZ002703 浙江世宝
```

## 运行行为

## 模式选择规则

- 只有在交易日盘中时段，且调用方明确需要盘中快照时，才应使用 `--intraday`
- 非交易日、交易日前开盘时段、交易日收盘后时段，默认都应使用常规的 `--pick-date`
- 即使 `runtime/` 下已经存在历史 `intraday` 产物，盘中时段之外也不应把它们当作默认最新结果继续沿用
- 盘中时段之外，如无额外说明，应显式解析目标 `pick_date` 并继续 end-of-day 工作流
- 只有用户明确要求盘中监控、盘中快照或实时交易时段信号时，才切换到 `intraday`

当前 CLI 的行为如下：

- `screen`
  - 从 PostgreSQL 的 `daily_market` 读取目标日前约 366 天窗口
  - 在本地计算 `b1` / `b2` / `dribull` 或 `hcr` 所需指标
  - `b1` 与 `dribull` 共用同一天的基础 prepared cache
  - 将候选结果写入 `~/.agents/skills/stock-select/runtime/candidates/`
- `chart`
  - 读取 candidate 文件
  - 为每个候选股票重新抓取日线历史
  - 将 PNG 图表写入 `~/.agents/skills/stock-select/runtime/charts/<pick_date>.<method>/`
- `review`
  - 读取候选与图表产物
  - 当前写出以本地 baseline 为主的 review 结果结构
  - 同时写出 `llm_review_tasks.json`，供 CLI 返回后由 skill 继续派发子代理图评
  - `llm_review_tasks.json` 顶层固定写入 `max_concurrency: 6`，作为 llm review 阶段的并发上限
  - 该结果结构已经预留 `llm_review` 字段，供后续基于 PNG + method-specific prompt 的子代理图评回填
  - `b1` 使用 `.agents/skills/stock-select/references/prompt-b1.md`
  - `b2` 与 `dribull` 的 review 都使用 `.agents/skills/stock-select/references/prompt-b2.md`
  - `hcr` 继续使用 `.agents/skills/stock-select/references/prompt.md`
  - `b1`、`b2` 与 `dribull` 都会在任务文件中额外写入周线 / 日线浪型和组合判定的文本上下文，供对应 prompt 使用
  - 将汇总结果写入 `~/.agents/skills/stock-select/runtime/reviews/<pick_date>.<method>/summary.json`
- `record-watch`
  - 读取 `reviews/<pick_date>.<method>/summary.json`
  - 抽取 `PASS` / `WATCH` 股票，写入 `watch_pool.csv`
  - 每条记录写入命令执行时间 `recorded_at`
  - 按距离本次执行日的交易日间隔排序
  - 按 `--window-trading-days` 保留最近窗口内的记录，删除更老的票
- `review-merge`
  - 读取 `reviews/<pick_date>.<method>/llm_review_results/*.json`
  - 校验并归一化子代理图评 JSON
  - 将 `llm_review` 回填到单股 review 文件
  - 以 baseline 40% + llm 60% 重算最终分数并重写 `summary.json`
- `analyze-symbol`
  - 直接从 PostgreSQL 拉取单只股票的日线历史
  - 在 `runtime/ad_hoc/` 下导出单张日线 PNG 图
  - 写出单个 `result.json`，包含确定性的信号条件和 baseline review
  - 不依赖 candidate 文件，也不依赖 `review-merge`
- `run`
  - 顺序执行 `screen`、`chart`、`review`

## B1 筛选说明

当前 B1 初筛的谓词过滤按以下顺序逐条执行。

若使用默认 `--pool-source turnover-top`，在进入这些条件前会先按目标日 `turnover_n` 构建流动性池，只保留成交额排名前 `5000` 的股票。

1. `J < 15` 或 `J <= 截至当日历史 J 的 10% expanding 分位`
2. `zxdkx` 历史是否足够，目标日是否可计算
3. `close > zxdkx`
4. `zxdq > zxdkx`
5. `weekly_ma_bull`
6. `max_vol_not_bearish`
7. `chg_d <= 4.0`
8. `v_shrink`
9. `safe_mode`
10. `lt_filter`

其中：

- `turnover_n` 使用 `43` 日滚动成交额，公式为 `((open + close) / 2) * volume` 的滚动求和
- `zxdq/zxdkx` 参数与参考仓库当前 B1 运行口径一致，分别基于 `14/28/57/114`
- `weekly_ma_bull` 使用周线 `10/20/30` 均线多头排列，周线收盘价按 ISO 周内最后一个实际交易日计算

新增失败计数含义：

- `fail_chg_cap`: 当日涨幅超过 4%
- `fail_v_shrink`: 近 3 日均量未低于近 10 日均量
- `fail_safe_mode`: 近期出现放量派发后，仍处于危险冷却区，或虽进入受控修复窗口但未满足 `shape_ok` / `cg_ok` 检查
- `fail_lt_filter`: 长趋势方向近 30 日翻向次数过多，且不满足近期上穿或强偏离的例外条件

### 关于 `fail_insufficient_history`

`zxdkx` 由 14、28、57、114 日均线的平均值构成，因此目标日通常需要至少 114 个有效交易日历史才能算出该值。

这会带来两个实际影响：

- 即使 `screen` 默认会读取目标日前约 366 天窗口，如果缓存里的实际连续交易历史不足，`zxdkx` 仍然可能为空
- 当目标日 `zxdkx` 为空，或缓存里缺少当前 `b1` 所需的 tightening 字段时，该股票会计入 `fail_insufficient_history`

这类股票不会再被误记为 `fail_close_zxdkx`。因此：

- `fail_insufficient_history` 表示“历史长度或 prepared 数据完整性不足，无法继续执行当前 `b1` 判断”
- `fail_close_zxdkx` 只表示“`zxdkx` 已算出，但收盘价没有站上去”

## HCR 筛选说明

`hcr` 是 `Historical High & Center Resonance Breakout` 的缩写，对应“历史高点与中心共振突破”初筛。当前实现口径为：

- `YX = (HHV(high, 30) + LLV(low, 30)) / 2`
- `P = CONST(REF(HHV(high, 180), 60))` 的符号级常量参考价
- `abs(YX - P) / abs(P) <= 0.015`
- `close > 1.0`
- `close > YX`
- 只在目标 `pick_date` 精确匹配当日数据，不向前回退

`hcr` 不使用 `b1` 的成交额前 `5000` 流动性池预过滤。

## 输出目录

运行时产物默认写入：

```text
~/.agents/skills/stock-select/runtime/
```

其中常见目录包括：

```text
candidates/<pick_date>.<method>.json
prepared/<pick_date>.pkl                 # b1 / b2 / dribull 共享基础 prepare
prepared/<pick_date>.hcr.pkl             # hcr 独立 prepare
charts/<pick_date>.<method>/<code>_day.png
reviews/<pick_date>.<method>/llm_review_tasks.json
reviews/<pick_date>.<method>/llm_review_results/<code>.json
reviews/<pick_date>.<method>/summary.json
watch_pool.csv
```

盘中 `--intraday` 运行保持候选、图表、review 目录按 `<run_id>.<method>` 隔离，但 prepared cache 改为按交易日共享：

```text
candidates/<run_id>.<method>.json
prepared/<trade_date>.intraday.pkl       # b1 / b2 / dribull 共享基础 prepare
prepared/<trade_date>.intraday.hcr.pkl   # hcr 独立 prepare
charts/<run_id>.<method>/
reviews/<run_id>.<method>/
```

其中：

- `b1`、`b2` 和 `dribull` 在 EOD 与 intraday 下都共用基础 prepared cache
- `dribull` 的二阶段 MACD warmup 仍是按需现算，不单独落盘
- intraday 只有在 `screen --intraday --recompute` 时才会重写当日共享 prepared cache

## 当前限制

- 当前筛选内置方法为 `b1`、`b2`、`dribull` 和 `hcr`
- `review` 命名空间仍保留旧 `b2`，且 `review --method dribull` 复用现有 `b2` reviewer 与 `prompt-b2.md`
- `run --method b2` 当前组合为“新的 `b2` 筛选 + 现有旧的 `b2 review`”
- `screen`、`chart`、`run` 都依赖可访问的 PostgreSQL
- 当前 Python CLI 里的 `review` 仍以本地 baseline 打分为主
- Python CLI 不直接调用子代理；多模态子代理图评在 CLI 返回后通过 skill workflow 驱动
- 子代理图评的提示词来源为 `.agents/skills/stock-select/references/prompt.md`
- 当前建议链路为：`review` 生成 baseline 和任务清单，子代理写入 `llm_review_results/`，再执行 `review-merge`
