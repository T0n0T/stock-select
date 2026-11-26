# 工作流程

## 数据源和中间缓存

`DUCKDB_PATH` 支持本地 DuckDB 文件，例如 `../stock-cache/runtime/stock-cache.duckdb`，也支持 Quack URI，例如 `quack://host:9494`。两种方式都由 `duckdb-neo` 只读访问；Quack 认证使用 `QUACK_AUTH_TOKEN`，TLS 指纹可通过 `QUACK_SSL_FINGERPRINT` 设置。如果服务端显式使用 HTTP，客户端设置 `QUACK_DISABLE_SSL=true` 并移除指纹；token 和查询数据将明文传输。

prepared 中间缓存统一使用 Parquet（`.parquet`，schema 21），动态因子以数值列存储。旧二进制中间缓存不再兼容，升级后会按需重新生成。

## 场景一：每日常规 EOD 生产 run

收盘后运行一次完整流程。

```bash
# 1. 完整 run（含图表和 LLM 复盘任务）
stock-select-rs run \
  --method b2 \
  --pick-date 2026-06-05 \
  --llm-review-limit 5

# 2. 查看排序结果
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-06-05 \
  --limit 20

# 3. 多模态复盘（分配子代理读图并写 annotation）
# 子代理按 llm_tasks.json 的 chart_path 读图，
# 用 raw_response_path 写详细复盘，llm_annotations.json 只保留 action/flags/comment。

# 4. 合并复盘结果
stock-select-rs review-merge \
  --method b2 \
  --pick-date 2026-06-05

# 5. 查看列表符号和 HTML 报告
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-06-05 \
  --limit 20
```

SCM 的 `review-list` 第五列简写为 `开仓 | +0.123456`、`观察 | +0.228483` 或 `丢弃 | -0.300000`，原始分数保留正负号和六位小数。详细原因、门槛和试验状态保存在 `display.json` 的 `entry_assessment` 中。第六列仍为 LLM 的 ↑/→/↓，与开仓判断独立。门槛使用模型原始分数；原有按当日名次归一化的 `model_score` 不作为开仓门槛。

`review-list` 默认在终端显示带中文表头的对齐表格，按中文实际显示宽度排列股票名称和行业。管道或重定向输出自动保持六列 TSV，便于脚本读取；可用 `--format table` 或 `--format tsv` 显式指定。表格的第五列表头为“开仓 / 原分”（无开仓分档时为“评分”），第六列为“LLM”。

策略随候选模型的 `model_metadata.json` 保存并绑定模型文件。旧 SCM 模型或旧缓存没有校准门槛且缺少原分时显示 `观察 | 缺失`，有原分时显示原分。历史日期不晚于校准结束日、盘中模式或模型不匹配时也只观察，具体原因保存在 `entry_assessment.reason`。更新二进制即可看到简写格式，无需重补因子或重跑排序；实际启用新候选门槛仍需发布对应模型并重新运行排序。研究候选的试验标记保存在 JSON 中。

命令输出路径：

```text
runtime/
├── candidates/2026-06-05.b2.json
├── select/2026-06-05.b2/
│   ├── display.json        ← review-list 读取
│   ├── llm_tasks.json      ← review 生成
│   ├── llm_annotations.json ← 子代理/人工填写
│   ├── llm_report.html     ← review-merge 生成
│   ├── llm_raw/            ← 子代理详细复盘原文
│   └── ...
├── charts/2026-06-05.b2/   ← K 线图 PNG
└── factors/2026-06-05.b2/
```

## 场景二：盘中运行

```bash
# 不带 --pick-date，自动按本地日期推断
stock-select-rs run \
  --method b2 \
  --intraday

# 带参数
stock-select-rs run \
  --method b2 \
  --intraday \
  --llm-review-limit 3

# 查看盘中结果（也要带 --intraday）
stock-select-rs review-list \
  --method b2 \
  --intraday \
  --limit 10
```

盘中 artifact key 为 `<date>.intraday.b2`，与 EOD 隔离。

清理盘中运行产物：

```bash
# 预览可清理条目数量，不删除文件
stock-select-rs clean-intraday --dry-run

# 删除 runtime 中的盘中产物
stock-select-rs clean-intraday
```

`clean-intraday` 只清理 `candidates/`、`prepared/`、`factors/`、`charts/`、`select/` 下文件名或目录名包含 `.intraday.` 的条目，不扫描或删除 `runtime/models/` 下的模型产物。

EOD prepared cache 默认只保留最近 30 个交易日 artifact，以减少 `runtime/prepared/` 的磁盘占用；可在当前目录 `.env` 或 shell 环境中设置 `STOCK_SELECT_PREPARED_CACHE_LIMIT=<正整数>` 调整。这个限制只作用于 EOD cache，盘中 `.intraday.` cache 不计入也不会被自动删除。

### 历史行情价格基准校验

DB-native EOD 加载保留原始 OHLC，再将每只股票的历史行情统一复权到该次窗口末日；选股日收盘仍是当日实际收盘价。数据库当前前复权基准的 CZSC 价格锚点、均线、布林线、MTM 和个股日/周/月 MACD 价格值，使用 `close / close_qfq` 换算到同一窗口基准。参考值取自较早日期时，还需乘该日 `adj_factor / 窗口末日 adj_factor`。日期、周期数、百分位、成交量、成交额、无量纲指标和行业指数因子不参与价格缩放，原始成交额在行情复权前计算。缺少有效参考且无法回退时明确报错，不落盘混合基准的缓存。

Parquet 格式使用 schema 21，DB-native 元数据增加 `calc_versions.price_basis = asof_qfq_v1`。缺失或不匹配此标记的缓存，下一次请求该日期时按需重建，不会自动扫描或冲刷全年。SCM、PBM、B2 等共享同日修正后的 prepared cache；SCM 重建完成后，PBM 正常读取不需要再次刷新。`--force` 覆盖 candidate/factor 的语义不变，但它不会绕过价格基准校验；旧 candidate/factor 不会因修改此标记自动更新，重训前需要另行刷新并重新构建数据集。

三种方法的 DB-native 缓存均需带有 `calc_versions.monthly_macd_history = previous_completed_month_v1`，标识加载逻辑已包含上月最后交易日的 DuckDB 月柱；源数据缺失时按策略的月柱缺失规则处理。缺少或不匹配此标记时，任一方法请求都会触发按需重建；新 Parquet 缓存继续使用 schema 21 并在各方法间共享。此修复不需要运行 stock-cache refresh；数据库行情缺行仍需先补行情、重算指标，再重新生成 prepared 和 candidate/factor。

## 场景三：模型更新

当需要重新训练或更新模型时：

```bash
# 1. 确定训练窗口
METHOD=scm
TRAIN_START=<本次训练起始日期>
TRAIN_END=<本次训练结束日期>

# 训练/补数据前查看核心数，并发通常为 4～8，最多 8；SCM/PBM 回填会强制单 worker 控制内存峰值
nproc

# 2. 补齐历史候选（如果缺失）
uv run stock-select-ml backfill candidates \
  --method "$METHOD" \
  --start-date "$TRAIN_START" \
  --end-date "$TRAIN_END" \
  --workers 8

# 3. 补齐 factor artifact（如果缺失）
# 对缺失日期的候选执行 screen --export-factors

# 4. 构建训练集
uv run stock-select-ml dataset build \
  --method "$METHOD" \
  --runtime-root runtime \
  --source candidates \
  --start-date "$TRAIN_START" \
  --end-date "$TRAIN_END"

# 5. 训练
uv run stock-select-ml train lgbm-rank \
  --method "$METHOD" \
  --dataset "diagnostics/ml/$METHOD/rank_dataset.csv" \
  --output-dir "diagnostics/ml/$METHOD/model" \
  --feature-set raw_numeric \
  --num-leaves 9 \
  --min-data-in-leaf 120 \
  --num-boost-round 60 \
  --learning-rate 0.05 \
  --num-threads 8 \
  --rolling-folds 5 \
  --rolling-train-dates 120 \
  --rolling-test-dates 20 \
  --skip-rf-diagnostics

# 训练前会校验 feature_coverage；zero coverage 的确认训练特征会中断训练，需先修复 Rust artifact 或 Python schema。

# 6. 查看训练 report 评估效果

# 7. 导出并发布
uv run stock-select-ml score export-lgbm \
  --method "$METHOD" \
  --model-output-dir "diagnostics/ml/$METHOD/model"

uv run stock-select-ml model dry-run-promote "diagnostics/ml/$METHOD/model" \
  --method "$METHOD" \
  --require-report

# 确认无误后正式发布
uv run stock-select-ml model promote "diagnostics/ml/$METHOD/model" \
  --method "$METHOD" \
  --require-report
```

`METHOD` 仅可取 `b2`、`scm` 或 `pbm`，三种方法分别发布到各自的模型目录。

## 场景四：历史数据补跑

```bash
# 全量补跑（自动跳过已有）
uv run stock-select-ml backfill runs \
  --start-date 2026-01-01 \
  --end-date 2026-06-04 \
  --workers 4

# 覆盖重跑
uv run stock-select-ml backfill runs \
  --start-date 2026-01-01 \
  --end-date 2026-06-04 \
  --no-skip-existing

# 只补某个月
uv run stock-select-ml backfill runs \
  --start-date 2026-05-01 \
  --end-date 2026-05-31
```

## 场景五：仅筛选候选

当前 `screen` 支持 `b2`、`scm`、`pbm`。旧策略及历史产物兼容代码已删除。`scm` 和 `pbm` 分别使用独立模型；各方法的公共股票池过滤、具体策略条件和 `run` 阶段排序口径见 [选股筛选方法过滤条件](screening-methods.md)。

```bash
# 只生成候选（不跑模型）
stock-select-rs screen --method b2 --pick-date 2026-06-05

# 生成候选并导出因子
stock-select-rs screen \
  --method b2 \
  --pick-date 2026-06-05 \
  --export-factors

# 自定义股票池
stock-select-rs run \
  --method b2 \
  --pick-date 2026-06-05 \
  --pool-source custom \
  --pool-file /tmp/custom-pool.txt

# 仅生成 K 线图（需要先有 run artifact）
stock-select-rs chart \
  --method b2 \
  --pick-date 2026-06-05 \
  --chart-workers 4
```

## 场景六：复盘

```bash
# 查看当天排序
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-06-05 \
  --limit 10

# 生成本日 LLM 复盘任务
stock-select-rs review \
  --method b2 \
  --pick-date 2026-06-05 \
  --limit 5

# 查看生成的 task
cat runtime/select/2026-06-05.b2/llm_tasks.json

# 填写 annotation 后合并
stock-select-rs review-merge \
  --method b2 \
  --pick-date 2026-06-05

# review-list 会显示 ↑/→/↓ 短线符号，详细图文复盘见：
# runtime/select/2026-06-05.b2/llm_report.html
```

## 场景七：AKQuant 排名回测

Python 侧通过 `uv` 的 `backtest` 可选依赖引入 AKQuant。回测读取 Rust `run` 生成的每日 `ranked.json` 和外部日线行情。

首次使用时同步回测依赖：

```bash
uv sync --locked --extra backtest
```

首版每天按 `model_rank` 取前三名，缺少排名时按 `model_score` 排序。每个信号日独立建一批仓位，多个批次可以同时持有。若周一收盘生成信号，周二开盘买入，持有周二至周四，周五开盘卖出。同一只股票连续入选时，每批按各自的实际买入数量到期卖出。

每批预算为信号日组合权益乘以资金比例，再除以持有天数，同时受现金加预计当批卖出所得的上限约束，并预留资金比例对应的缓冲。默认参数下每批预算至多约为当日权益的 33%。按当批入选数等分预算，以信号日收盘价计算买入股数，再按交易手数向下取整。实际成交金额取决于下一交易日开盘价；仍停牌的到期持仓不能作为已回收资金。

```bash
uv run --locked --extra backtest stock-select-ml backtest run \
  --signals runtime/select \
  --method scm \
  --market-data data/daily_ohlcv.parquet \
  --output diagnostics/backtest/scm.json
```

`--signals` 可以传 `runtime/select`，命令会读取其下 `YYYY-MM-DD.<method>/ranked.json` 格式的收盘产物。目录中有多种筛选方法时，用 `--method` 选择一种。也可以传单个产物目录，或直接传 CSV、JSON 或 JSONL 文件。每条信号需提供 `code`（或 `symbol`）和 `model_score`（或 `score`）。日期取自 `date`、`trading_date`、JSON 的 `artifact_key` 或产物目录名。

行情支持 CSV 或 Parquet，可以放在一个文件中，也可以拆分到同一目录。文件需包含 `symbol`/`code`、`datetime`/`timestamp`/`date`、`open`、`high`、`low`、`close` 和 `volume`，每只股票每个交易日一条日线，代码与信号一致。回测用行情中的日期确定交易日，请提供连续覆盖的交易日数据。默认策略要求行情覆盖最后一个信号日之后至少四个交易日。入选股票在信号日、买入日和退出日都须有行情。

常用策略和资金参数：

```text
--top-n N                 每次信号选取的排名数量，默认 3
--holding-days N          持有交易日数量，默认 3
--entry-policy FILE       独立开仓许可/每日权益预算 JSON，默认每天允许开仓
--daily-context FILE      信号日环境 CSV（date/env 列），可直接读取 rank_dataset.csv
--capital-allocation F   用于计算批次预算的权益比例，默认 0.99
--initial-cash F          初始资金，默认 1000000
--commission-rate F       佣金费率，默认 0.0003
--stamp-tax-rate F        卖出印花税率，默认 0.0005
--transfer-fee-rate F     过户费率，默认 0.00001
--min-commission F        最低佣金，默认 5
--lot-size N              最小交易股数，默认 100
--t-plus-one/--no-t-plus-one  是否启用 T+1，默认启用
--defer-suspended-exit    到期停牌则等待首个可交易开盘，默认关闭
```

报告从第一个信号日统计到最后一批实际退出日。`metrics.total_return_pct` 是组合累计收益率，单位为百分比。报告还包含净值、现金、订单、成交和每日策略动作。`strategy_config` 保存持仓与开仓配置，`daily_budgets` 记录目标预算、受现金约束后的预算及按收盘价估计的下单金额；次日开盘实际成交金额会受跳空影响。`actions[].entry_decision` 保存信号日环境、开仓许可、预算比例与原因。订单的 `tag` 记录其所属批次的信号日期，策略动作中的 `expired_signal_dates` 记录当天到期的批次。`diagnostics` 包含 AKQuant 原生仓位暴露、按股票/信号日的净盈亏贡献，以及根据本地环境数据关联的交易归因；环境归因金额是已成交组合的盈亏贡献，不能当作禁止该环境后的反事实组合收益。

默认要求信号、买入和退出日行情完整；开启 `--defer-suspended-exit` 后，到期无行情的卖出等待复牌开盘，延长实际持仓并占用资金，若数据末尾仍无可交易退出则报错。引擎拒单仍会使回测失败。涨跌停和滑点留待正式回测时配置。

开仓与预算规则属于交易策略，不修改模型、排名或三天收益标签。以下 JSON 仅为待验证的环境规则示例：

```json
{
  "name": "环境开仓试验",
  "by_environment": {
    "weak": {"allow_new_positions": false},
    "neutral": {"daily_equity_fraction": 0.15},
    "strong": {"daily_equity_fraction": 0.30}
  }
}
```

在回测命令中追加 `--entry-policy <策略.json> --daily-context <rank_dataset.csv>`。环境取信号当日收盘已知的 `env`，用于次日开盘的新批次；同日多条候选的环境必须一致。使用环境规则时，每个有信号日期都必须有环境且命中配置，缺失或未知环境直接报错。无需环境的固定规则写作 `{"default":{"daily_equity_fraction":0.15}}`。

`daily_equity_fraction` 表示当天新批次的目标金额占当前权益的比例，范围 0～1，再由可用现金与预计到期卖出所得封顶、保留现金缓冲；它不是调整整个账户的目标仓位。未指定时沿用 `capital_allocation / holding_days`。设为 0 或禁止开仓均停止所有新批次买入，已有持仓仍按原退出规则执行；不补买前面被跳过的批次。策略配置和每日环境文件独立于模型文件保存。比较规则时固定排名 CSV，并加入统一减仓对照，同时检查收益、回撤、平均暴露、空仓日和成本；现有留出区间已观察，后续规则仍须新前推数据验证。

按当前持仓规则执行 Optuna 调参时，使用 `tune lgbm-rank --strategy optuna --objective akquant --market-data <行情文件>`；完整示例见 [模型系统](model.md#32-以-akquant-组合净收益调参)。此路径以滚动样本外的 AKQuant 组合净收益选参数，并在选择完成后单独检验末段留出期。

规则退出实验使用 `--exit-policy <退出规则.json>` 替代固定天数退出；同一文件也传给 `tune lgbm-rank --objective akquant`，同步生成 `rank_label_exit`。若要对照连续收益目标，再追加 `--learning-task return-regression`，改为学习 `exit_net_return`；Optuna 搜索 L2/L1 损失，仍由 OOF 组合净收益选优，仓位与退出规则保持固定。规则细节见 [规则退出标签](model.md#33-按交易规则退出的排序标签)及[连续规则收益回归](model.md#34-连续规则收益回归)。回测示例：

```bash
uv run --extra backtest stock-select-ml backtest run \
  --signals <已保存的样本外排名.csv> --market-data <日线.parquet> \
  --exit-policy <退出规则.json> --backtest-end-date 2026-11-19 \
  --top-n 3 --holding-days 3 --capital-allocation 0.9 \
  --output <回测报告.json>
```

规则模式下 `holding_days=3` 只保留默认每日预算分母的作用，默认新批次目标为权益的 30%，实际投入还受现金约束；需要自定义每日金额时用独立 `EntryPolicy` 覆盖。退出为当日收盘近似成交，要求 T+1，停牌日不下退出单；T+3 停牌时在首个复牌收盘补检。行情须包含信号日之前至少 25 根同基准日线作为 MA25 历史，并覆盖最后信号的次日开盘。`--backtest-end-date` 是最后估值日，省略时使用行情末日；规则尚未触发的持仓保留市值。报告新增 `exit_events`（逐批日期、价格及所有触发原因）和 `open_batches`（尚未退出的批次）。

## 环境评分

EOD run 自动评分：

- 读取 DB-native stock-cache 覆盖窗口和环境因子输入
- 评估市场状态：`weak` / `neutral` / `strong`
- 写入 `runtime/environment/daily/<date>.json`

run record 相关环境变量：

- `STOCK_SELECT_RECORD_METHODS`：开启自动写 `record.csv` 的方法列表，例如 `b2,scm,pbm`。
- `STOCK_SELECT_RECORD_WINDOW_TRADING_DAYS`：`record.csv` 保留最近 N 个入选交易日，默认 10。
- `STOCK_SELECT_RECORD_LIMIT`：每次 `update_run_record` 最多写入排名前 N 条，默认 30；`run --record` 和 `review-list --record` 自动补跑都会使用。

盘中模式：

```bash
# 手动指定环境（不落盘）
stock-select-rs run \
  --method b2 \
  --intraday \
  --environment-state weak \
  --environment-reason "最近连续缩量调整"
```

## 安装

首次使用安装脚本：

```bash
bash scripts/install.sh
```

等价于：
```bash
# 编译安装二进制
cargo install --path .

# 同步技能到 ~/.agents/skills/
cp -r .agents/skills/* ~/.agents/skills/

# 手动配置环境变量
cp .env.example .env
# 编辑 .env 填入 DUCKDB_PATH 和 TUSHARE_TOKEN；使用 Quack 时再配置认证 token
```

## 高级：分段执行

如果想手动分段执行 run 中的各步骤：

```bash
# 步骤 1: screen（仅生成候选；默认不写 prepared cache，加 --write-prepared-cache 才写）
stock-select-rs screen --method b2 --pick-date 2026-06-05

# 步骤 2: screen --export-factors（导出因子）
stock-select-rs screen --method b2 --pick-date 2026-06-05 --export-factors

# 步骤 3: run 指定候选文件（跳过 auto-screen）
stock-select-rs run \
  --method b2 \
  --pick-date 2026-06-05 \
  --candidates-path runtime/candidates/2026-06-05.b2.json

# 步骤 4: 单独生成图表
stock-select-rs chart \
  --method b2 \
  --pick-date 2026-06-05 \
  --chart-workers 4

# 步骤 5: 单独生成 LLM 复盘任务
stock-select-rs review \
  --method b2 \
  --pick-date 2026-06-05 \
  --limit 5
```

## 验证

```bash
# Rust 代码检查
cargo fmt --check
cargo test --quiet

# Python CLI 检查
uv run python -m py_compile $(find ml -name '*.py' -print)

# 模型训练测试
uv run python3 -m unittest \
  tests/test_candidate_backfill.py \
  tests/test_rank_dataset.py \
  tests/test_rank_lgbm.py
```
