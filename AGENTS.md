# AGENTS.md

本仓库是 `stock-select` 新 Rust CLI 实现，binary 为 `stock-select-rs`。后续所有项目文档、roadmap、计划、状态说明和交接记录默认使用中文编写；除非用户明确要求，避免新增英文文档。

## 当前方向

- 以新 Rust CLI 替代旧 `/home/tiger/Documents/agents/stock-select` 的日常 b2 生产流程。
- 优先保持 model-first 架构：模型排序是主路径，LLM 只做 annotation，不改变 `model_rank`。
- 旧项目只作为迁移参考；生产路径不要引入 Python CLI 或 Python predict。
- 接口和行为冲突时，以本仓库当前代码为准做最小适配。

## 已有关键行为

- 已有命令：`screen`、`chart`、`review`、`review-merge`、`review-list`、`run`、`completions`。
- `b1 run/review` 必须继续报 `b1 model review is not available`，不能 fallback baseline。
- `b2 run` 使用 runtime 默认 LightGBM text model 和 metadata 生成真实模型排序。
- `--intraday` 的 run/review-list artifact key 为 `<date>.intraday.b2`。
- `review-list` 优先读取 `selection_runs/<key>.b2/display.json`。
- 默认 runtime root 为 `$HOME/.agents/skills/stock-select/runtime`。
- 配置解析顺序为 CLI 参数 > shell 环境变量 > 当前目录 `.env`，当前重点变量是 `POSTGRES_DSN` 和 `TUSHARE_TOKEN`。

## 开发约束

- 开始工作前先运行 `git status --short --branch`。
- 不要覆盖或回退已有未提交改动。
- 严格小步 TDD：先写失败测试，再实现，再验证通过。
- 优先沿用 `selection_engine` 等现有模块边界，不做无关重构。
- 迁移旧实现时优先查找旧 Rust 代码，最小搬迁，不重写无关模块。
- 涉及数据源和凭据时，不要打印 `.env`、DSN、token 的具体值。

## 验证

Rust 改动完成后至少运行：

```bash
cargo fmt --check
cargo test --quiet
```

## Roadmap

当前详细进度以 `docs/roadmap.md` 为准。更新实现状态时同步更新该文档，并保持中文。
