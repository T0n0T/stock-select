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

## 模型维护

统一入口：

```bash
uv run stock-select-ml model status --method b2
uv run stock-select-ml model archives --method b2
uv run stock-select-ml model dry-run-promote <candidate_dir> --method b2 --require-report
uv run stock-select-ml model promote <candidate_dir> --method b2 --require-report
uv run stock-select-ml model rollback <archive_version> --method b2
```

这个入口会封装当前模型查看、归档浏览、发布和回滚旧归档模型。

## 历史补跑

批量补跑历史日期的 run 数据：

```bash
# 补跑 2026-01-01 ~ 2026-06-04 的数据
uv run stock-select-ml backfill runs --start-date 2026-01-01 --end-date 2026-06-04

# 覆盖已有的重新跑
uv run stock-select-ml backfill runs --start-date 2026-05-01 --end-date 2026-05-31 --force

# 先预览要跑的日期
uv run stock-select-ml backfill runs --start-date 2026-05-01 --end-date 2026-05-31 --dry-run

# 并发补跑（4 个 worker 同时跑，加快历史回填）
uv run stock-select-ml backfill runs --start-date 2026-01-01 --end-date 2026-05-31 --jobs 4
```

Python CLI 直接从 DB 查询交易日历（`daily_market` 表），精确跳过非交易日；
无 DB 连接时兜底跳过周末。支持 `--jobs N` 并发补跑（默认 4，设为 1 则串行）。

## 参考

- 项目进度：`docs/roadmap.md`
- 模型维护说明：`.agents/skills/model-maintenance/references/model-maintenance.md`
- 代理约束：`AGENTS.md`
