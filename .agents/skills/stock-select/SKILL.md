---
name: stock-select
description: Use when operating the local stock-select Rust CLI workspace for A-share screening, EOD or intraday ranking runs, review-list inspection, llm_tasks.json subagent review, or review-merge HTML reports.
---

# Stock Select CLI

本 skill 只服务当前工作区：

```text
/home/tiger/Documents/agents/stock-select
```

二进制是 `stock-select-rs`。开始操作前进入该目录，先运行 `git status --short --branch`，并把现有未提交改动视为用户改动。CLI、训练脚本和维护脚本默认读取当前目录 `.env`；不要打印 `POSTGRES_DSN`、`TUSHARE_TOKEN` 或 DSN/token 的具体值。

## 何时使用

- 用户要用 CLI 做某个交易日的盘后筛选排序、盘中筛选排序、查看排序结果或补跑 artifact。
- 用户要让智能体理解 runtime/select/charts/models 等工作区目录结构。
- 用户要对 `llm_tasks.json` 提到的股票分配 subagent 做 LLM review。
- 用户要结合 `chart_path` 图表、`display.json`、`factors.json`、`ranked.json` 等股票数据，输出 annotation/raw review，并用 `review-merge` 生成 `llm_report.html`。

## 快速流程

盘后 EOD：

```bash
stock-select-rs run --method b2 --pick-date <YYYY-MM-DD> --llm-review-limit 5
stock-select-rs review-list --method b2 --pick-date <YYYY-MM-DD> --limit 20
```

盘中 intraday：

```bash
stock-select-rs run --method b2 --intraday --llm-review-limit 3
stock-select-rs review-list --method b2 --intraday --limit 20
```

盘中 artifact key 是 `<date>.intraday.b2`；盘中相关 `review-list`、`review`、`review-merge`、`chart` 都要带 `--intraday`。盘中没有可用上一交易日环境时，补 `--environment-state weak|neutral|strong --environment-reason "<reason>"`。

## 子代理复盘

当用户要求“LLM 复盘”“游资复盘”“subagent review”“看图输出 HTML”：

1. 确认存在 `select/<artifact>.b2/llm_tasks.json`；没有就先运行 `run --llm-review-limit N` 或 `review --limit N`。
2. 读取 `references/youzi-subagent-review.md`，对 `llm_tasks.json` 的 rows 做真实 spawn：每行一个子代理，并发分派。
3. 主 agent 不得代写任何单票结论；主 agent 只负责准备任务、等待子代理、汇总原始输出、校验 JSON 和执行 `review-merge`。
4. 每个子代理同时读取该 row 的 `chart_path` 图表和股票数据字段，必要时补看同目录 `display.json`、`factors.json`、`ranked.json`。
5. 子代理写 `llm_raw/<code>.json` 详细复盘，raw 中保留 `agent_id`；汇总写 `llm_annotations.json`，只允许 `KEEP`、`CAUTION`、`REJECT`，不能改 `model_rank` 或 `model_score`。
6. 运行 `stock-select-rs review-merge ...` 生成合并后的 `display.json` 与 `llm_report.html`。

## References

- `references/cli-workflow.md`：EOD、盘中、review-list、review、review-merge 的 CLI 命令。
- `references/runtime-layout.md`：runtime 目录结构与 artifact key 规则。
- `references/youzi-subagent-review.md`：借鉴本地 `/home/tiger/Documents/agents/UZI-Skill` F 组游资口径的子代理复盘流程。
