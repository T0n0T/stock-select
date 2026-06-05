# stock-select-new

`stock-select-new` 是新的 Rust CLI 实现，二进制为 `stock-select-rs`。当前目标是替代旧仓库的日常 `b2` 流程，保持 model-first 架构，生产排序以 LightGBM 模型为主路径。

## 环境变量

本仓库默认从当前目录 `.env` 读取运行环境。常用变量：

```env
STOCK_SELECT_RUNTIME_ROOT=runtime
POSTGRES_DSN=...
TUSHARE_TOKEN=...
```

CLI、训练脚本和模型维护脚本都按 `CLI 参数 > shell 环境变量 > 当前目录 .env` 解析配置。

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
scripts/model_maintenance.sh status
scripts/model_maintenance.sh archives
scripts/model_maintenance.sh dry-run-promote <candidate_dir>
scripts/model_maintenance.sh promote <candidate_dir>
scripts/model_maintenance.sh switch <archive_version>
```

这个入口会封装当前模型查看、归档浏览、发布和切换旧归档模型。

## 参考

- 项目进度：`docs/roadmap.md`
- 模型维护说明：`.agents/skills/model-maintenance/references/model-maintenance.md`
- 代理约束：`AGENTS.md`
