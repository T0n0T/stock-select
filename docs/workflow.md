# 工作流程

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

## 场景三：模型更新

当需要重新训练或更新模型时：

```bash
# 1. 确定训练窗口
METHOD=b2
TRAIN_START=2025-06-01
TRAIN_END=2026-06-04

# 训练/补数据前查看核心数，workers 至少取可用核心数的 1/2，除非机器负载不允许
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

`METHOD=b3` 可维护并发布到 `runtime/models/b3/`；生产 `run/review` 是否可直接使用 b3，仍取决于 Rust CLI 对 b3 的 capability。

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

当前 `screen` 支持 `b2`、`b3`、`lsh`。各方法的公共股票池过滤、具体策略条件和 `run` 阶段排序口径见 [选股筛选方法过滤条件](screening-methods.md)。

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

- 读取 `daily_market` 获取上证指数和国证 2000 数据
- 评估市场状态：`weak` / `neutral` / `strong`
- 写入 `runtime/environment/daily/<date>.json`

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
# 编辑 .env 填入 POSTGRES_DSN 和 TUSHARE_TOKEN
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
