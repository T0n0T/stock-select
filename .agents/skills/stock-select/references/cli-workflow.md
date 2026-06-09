# CLI Workflow

## 固定工作区

所有命令在当前项目执行：

```bash
cd /home/tiger/Documents/agents/stock-select
git status --short --branch
```

配置优先级是 CLI 参数 > shell 环境变量 > 当前目录 `.env`。常用变量：

- `STOCK_SELECT_RUNTIME_ROOT`
- `POSTGRES_DSN`
- `TUSHARE_TOKEN`

不要打印凭据值。缺少 runtime 时优先使用 `.env` 的 `STOCK_SELECT_RUNTIME_ROOT`；仍缺省时 CLI 默认 `~/.agents/skills/stock-select/runtime`。

## 盘后筛选排序

```bash
stock-select-rs run \
  --method b2 \
  --pick-date <YYYY-MM-DD> \
  --llm-review-limit 5
```

常用检查：

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date <YYYY-MM-DD> \
  --limit 20
```

输出位于 `select/<YYYY-MM-DD>.b2/`，包含 `display.json`、`factors.json`、`ranked.json`、`llm_tasks.json`。`review-list` 显示模型排序和 LLM 短线符号：`KEEP` => `↑`，`CAUTION` => `→`，`REJECT` => `↓`，未复盘 => `-`。

## 盘中筛选排序

```bash
stock-select-rs run \
  --method b2 \
  --intraday \
  --llm-review-limit 3
```

需要指定日期时：

```bash
stock-select-rs run \
  --method b2 \
  --intraday \
  --pick-date <YYYY-MM-DD> \
  --llm-review-limit 3
```

盘中 artifact key 是 `<YYYY-MM-DD>.intraday.b2`。查询、复盘和合并时也要带 `--intraday`：

```bash
stock-select-rs review-list --method b2 --intraday --limit 20
stock-select-rs review --method b2 --intraday --limit 3
stock-select-rs review-merge --method b2 --intraday
```

盘中不临时计算市场环境。没有上一交易日环境时，手动给环境：

```bash
stock-select-rs run \
  --method b2 \
  --intraday \
  --environment-state neutral \
  --environment-reason "manual intraday context"
```

## 复盘与 HTML

仅从已有 selection 生成任务：

```bash
stock-select-rs review \
  --method b2 \
  --pick-date <YYYY-MM-DD> \
  --limit 5
```

子代理填好 `llm_annotations.json` 和 `llm_raw/*.json` 后：

```bash
stock-select-rs review-merge \
  --method b2 \
  --pick-date <YYYY-MM-DD>
```

合并后查看：

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date <YYYY-MM-DD> \
  --limit 20
```

图文报告在 `select/<artifact>.b2/llm_report.html`。报告引用 `chart_path`，合并 `llm_comment` 和 raw review，不改变 `model_rank`、`model_score`。
