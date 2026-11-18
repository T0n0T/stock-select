# 工作流程

## 数据源和中间缓存

`DUCKDB_PATH` 支持本地 DuckDB 文件，例如 `../stock-cache/runtime/stock-cache.duckdb`，也支持 Quack URI，例如 `quack://host:9494`。两种方式都由 `duckdb-neo` 只读访问；Quack 认证使用 `QUACK_AUTH_TOKEN`，TLS 指纹可通过 `QUACK_SSL_FINGERPRINT` 设置。

prepared 中间缓存统一使用 Parquet（`.parquet`，schema 14），动态因子以数值列存储。旧二进制中间缓存不再兼容，升级后会按需重新生成。

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

Parquet 格式使用 schema 14，DB-native 元数据增加 `calc_versions.price_basis = asof_qfq_v1`。缺失或不匹配此标记的缓存，下一次请求该日期时按需重建，不会自动扫描或冲刷全年。SCM、PBM、B2 等共享同日修正后的 prepared cache；SCM 重建完成后，PBM 正常读取不需要再次刷新。`--force` 覆盖 candidate/factor 的语义不变，但它不会绕过价格基准校验；旧 candidate/factor 不会因修改此标记自动更新，重训前需要另行刷新并重新构建数据集。

三种方法的 DB-native 缓存均需带有 `calc_versions.monthly_macd_history = previous_completed_month_v1`，标识加载逻辑已包含上月最后交易日的 DuckDB 月柱；源数据缺失时按策略的月柱缺失规则处理。缺少或不匹配此标记时，任一方法请求都会触发按需重建；新 Parquet 缓存继续使用 schema 14 并在各方法间共享。此修复不需要运行 stock-cache refresh；数据库行情缺行仍需先补行情、重算指标，再重新生成 prepared 和 candidate/factor。

## 场景三：模型更新

当需要重新训练或更新模型时：

```bash
# 1. 确定训练窗口
METHOD=b2
TRAIN_START=2025-06-01
TRAIN_END=2026-06-04

# 训练/补数据前查看核心数，workers 至少取可用核心数的 1/2，除非机器负载不允许；SCM/PBM 回填会强制单 worker 控制内存峰值
nproc

# 2. 补齐历史候选（如果缺失）
uv run stock-select-ml backfill candidates \
  --method "$METHOD" \
  --start-date "$TRAIN_START" \
  --end-date "$TRAIN_END" \
  --workers 16

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
  --num-threads 16

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
# 步骤 1: screen（仅生成候选）
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
