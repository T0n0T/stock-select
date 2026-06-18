# stock-select

`stock-select` 是新的 Rust CLI 实现，二进制为 `stock-select-rs`。model-first 架构，生产排序以 LightGBM 模型为主路径。

## 环境变量

本仓库默认从当前目录 `.env` 读取运行环境。常用变量：

```env
STOCK_SELECT_RUNTIME_ROOT=runtime
POSTGRES_DSN=...
TUSHARE_TOKEN=...
```

Rust CLI 和 `stock-select-ml` Python CLI 都按 `CLI 参数 > shell 环境变量 > 当前目录 .env` 解析配置。

## 常用命令

筛选候选：

```bash
cargo run -- screen --method b2 --pick-date 2026-06-05
```

生成候选并导出因子：

```bash
cargo run -- screen --method b2 --pick-date 2026-06-05 --export-factors
```

完整 run：

```bash
cargo run -- run --method b2 --pick-date 2026-06-05
```

查看排序结果：

```bash
cargo run -- review-list --method b2 --pick-date 2026-06-05 --limit 20
```

## stock-select-ml 典型命令

`stock-select-ml` 是 Python 侧统一入口，负责历史补跑、训练集构建、模型训练/调参、评分导出和模型发布维护。

查看命令树：

```bash
uv run stock-select-ml --help
uv run stock-select-ml backfill --help
uv run stock-select-ml model --help
```

补历史候选、run 和 record：

```bash
# 补齐 screen 候选 artifact
uv run stock-select-ml backfill candidates \
  --method b2 \
  --start-date 2026-01-01 \
  --end-date 2026-06-04 \
  --workers 4

# 补跑历史 run artifact；默认覆盖 STOCK_SELECT_RECORD_METHODS 为空，不写 record.csv
uv run stock-select-ml backfill runs \
  --method b2 \
  --start-date 2026-01-01 \
  --end-date 2026-06-04 \
  --workers 4

# 按 STOCK_SELECT_RECORD_METHODS 或 --methods 补 runtime/record.csv
uv run stock-select-ml backfill records \
  --methods b2,lsh \
  --days 10 \
  --workers 4
```

构建训练集、训练和调参：

```bash
uv run stock-select-ml dataset build \
  --method b2 \
  --runtime-root runtime \
  --source candidates \
  --start-date 2026-01-01 \
  --end-date 2026-06-04

uv run stock-select-ml train lgbm-rank \
  --method b2 \
  --dataset diagnostics/ml/b2/rank_dataset.csv \
  --output-dir diagnostics/ml/b2/model \
  --feature-set raw_numeric \
  --num-threads 8

uv run stock-select-ml tune lgbm-rank \
  --method b2 \
  --dataset diagnostics/ml/b2/rank_dataset.csv \
  --output-root diagnostics/ml/b2/tuning \
  --strategy optuna \
  --max-trials 30
```

导出评分、诊断和模型维护：

```bash
uv run stock-select-ml score export-lgbm \
  --method b2 \
  --model-output-dir diagnostics/ml/b2/model

uv run stock-select-ml score evaluate-blends \
  --method b2 \
  --dataset diagnostics/ml/b2/rank_dataset.csv \
  --model base=diagnostics/ml/b2/tuning/base \
  --model aux=diagnostics/ml/b2/tuning/aux \
  --aux-weight 0.15

uv run stock-select-ml diagnostics controlled-rerank \
  --method b3 \
  --dataset diagnostics/ml/b3/controlled-online-window/rank_dataset.csv \
  --model primary=diagnostics/ml/b3/tuning/primary \
  --model risk=diagnostics/ml/b3/tuning/risk \
  --primary-model primary \
  --risk-model risk

uv run stock-select-ml model status --method b2
uv run stock-select-ml model archives --method b2
uv run stock-select-ml model dry-run-promote diagnostics/ml/b2/model --method b2 --require-report
uv run stock-select-ml model promote diagnostics/ml/b2/model --method b2 --require-report
uv run stock-select-ml model rollback <archive_version> --method b2
```

模型维护入口封装当前模型查看、归档浏览、发布和回滚旧归档模型。历史补跑会优先从 DB 查询交易日历（`daily_market` 表），无 DB 连接时兜底跳过周末；`backfill runs` 默认跳过 record 写入，专门补 `record.csv` 时使用 `backfill records`。

## 参考

- 项目进度：`docs/roadmap.md`
- 模型维护说明：`.agents/skills/model-maintenance/references/model-maintenance.md`
- 代理约束：`AGENTS.md`
