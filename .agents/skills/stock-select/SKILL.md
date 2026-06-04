---
name: stock-select
description: Use when screening, ranking, reviewing, listing, or merging A-share stock selection artifacts with the local Rust stock-select-rs CLI in the stock-select-new repository.
---

# Stock Select New CLI

本 skill 用于新 Rust CLI 仓库：

```text
/home/tiger/Documents/agents/stock-select-new
```

二进制名是 `stock-select-rs`。不要从本 skill 调用旧 Python CLI 或旧项目生产路径；旧仓库只用于迁移参考。

## 关键约束

- 当前生产主路径是 `b2` model-first：LightGBM 排序决定 `model_rank`，LLM/人工复盘只做 annotation。
- `b1 run/review` 必须报 `b1 model review is not available`，不能 fallback baseline。
- 默认 runtime root 是 `~/.agents/skills/stock-select/runtime`，也可用 `--runtime-root` 覆盖。
- 配置解析顺序：CLI 参数 > shell 环境变量 > 当前目录 `.env`。
- 涉及 `POSTGRES_DSN`、`TUSHARE_TOKEN` 时不要打印具体值。

## 当前命令

```text
screen
chart
review
review-merge
review-list
run
completions
```

实际命令名是 `review-merge`。如果用户说“merge-review”“merge review”“合并复盘”，应引导使用 `review-merge`，不要编造 `merge-review` 命令。

## 常用流程

EOD b2 生产 run：

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25
```

盘中 b2 run，可省略 `--pick-date`，CLI 会按本地日期推断：

```bash
stock-select-rs run \
  --method b2 \
  --intraday
```

只生成候选：

```bash
stock-select-rs screen \
  --method b2 \
  --pick-date 2026-05-25
```

生成图表：

```bash
stock-select-rs chart \
  --method b2 \
  --pick-date 2026-05-25 \
  --chart-workers 4
```

从已有 selection/display 生成 LLM task：

```bash
stock-select-rs review \
  --method b2 \
  --pick-date 2026-05-25 \
  --limit 5
```

查看排序结果：

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-05-25 \
  --limit 20
```

合并已填写的复盘 annotation：

```bash
stock-select-rs review-merge \
  --method b2 \
  --pick-date 2026-05-25
```

盘中 artifact key 为 `<date>.intraday.b2`；盘中 `review-list`、`chart`、`review-merge` 也要带 `--intraday`，省略 `--pick-date` 时同样按本地日期推断。

## Review Merge 引导

`run --llm-review-limit N` 或 `review --limit N` 会写：

```text
<runtime>/select/<key>.b2/llm_tasks.json
<runtime>/select/<key>.b2/llm_annotations.json
```

人工或子代理完成 annotation 后，必须运行：

```bash
stock-select-rs review-merge --method b2 --pick-date <YYYY-MM-DD>
```

如果是盘中：

```bash
stock-select-rs review-merge --method b2 --intraday
```

合并命令会读取 selection artifact，并输出合并后的展示产物。不要让 LLM 改写 `model_rank`；annotation 只补充风险、观察点和人工备注。

## 多模态评估与子代理

当用户要求“多模态评估”“看图复盘”“LLM 复盘”“安排 subagent 评估图表”时：

1. 确认已有 `select/<key>.b2/llm_tasks.json`；没有则先运行 `run --llm-review-limit N` 或 `review --limit N`。
2. 读取 `references/review-rubric.md` 和 `references/prompt-b2.md`。
3. 按 `llm_tasks.json` 的 rows 分配子代理查看对应 `chart_path`。
4. 子代理只输出 annotation，不输出或修改 `model_rank`。
5. 汇总为 `select/<key>.b2/llm_annotations.json`。
6. 运行 `stock-select-rs review-merge ...` 合并展示结果。

盘中任务必须使用同一个 `<date>.intraday.b2` artifact key；`review-merge` 命令也要带 `--intraday`。

## 环境评分

EOD `run/review` 未传 `--environment-state` 时会读取 `POSTGRES_DSN`，用上证指数 `000001.SH` 和国证 2000 `399303.SZ` 评估并持久化环境。评估失败且没有覆盖 pick date 的历史环境时应明确失败。

盘中不做临时指数评估：

- 手动传 `--environment-state` 时使用手动环境且不落盘。
- 未传时读取上一交易日已持久化环境。
- 找不到上一交易日环境时，提示用户传 `--environment-state` 或先跑 EOD。

## 自定义股票池

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --pool-source custom \
  --pool-file /tmp/custom-pool.txt
```

股票池文件可包含空白分隔代码：

```text
603138 300058 002350.SZ
```

## 验证

涉及 Rust 改动时运行：

```bash
cargo fmt --check
cargo test --quiet
```

## References

按需读取：

- `references/runtime-layout.md`：新 CLI runtime 路径和 artifact key。
- `references/review-rubric.md`：多模态子代理 annotation schema、风险维度和 `review-merge` 合并要求。
- `references/prompt-b2.md`：b2 图表复盘提示。
- `references/prompt-b1.md`：仅用户明确要求人工看 b1 图表时使用，不能当作 b1 model review。
- `references/prompt-dribull.md`：仅用户明确要求人工看 dribull 图表时使用。
