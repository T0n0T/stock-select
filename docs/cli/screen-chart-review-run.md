# 选股主流程

本文说明 `screen`、`chart`、`review`、`run` 四个主命令。

## `screen`

入口：

```bash
uv run stock-select screen --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select screen --method <method> --intraday --dsn postgresql://...
```

作用：

- 准备方法所需的指标数据
- 按 `pool_source` 解析票池
- 执行方法自身的确定性筛选
- 输出 candidate 文件

详细流程见：

- [共用筛选流程](../share/screen-common.md)
- 各方法 `screen.md`

## `chart`

入口：

```bash
uv run stock-select chart --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select chart --method <method> --intraday
```

作用：

- 读取 candidate
- 为每只候选输出 `<code>_day.png`

EOD 会重新抓取股票历史；intraday 会复用同交易日 prepared cache。

## `review`

入口：

```bash
uv run stock-select review --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select review --method <method> --intraday
```

作用：

- 读取 candidate 与 chart
- 生成 baseline review
- 生成 `llm_review_tasks.json`
- 输出 `summary.json`

详细流程见：

- [共用 Review 流程](../share/review-common.md)
- 各方法 `review.md`

## `run`

入口：

```bash
uv run stock-select run --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
uv run stock-select run --method <method> --intraday --dsn postgresql://...
```

作用：

- 顺序执行 `screen`
- 顺序执行 `chart`
- 顺序执行 `review`

适合：

- 一次性跑完整 EOD 流程
- 盘中快速生成候选、图和 baseline review

## 主流程产物

运行产物说明见：

- [共用运行产物](../share/runtime-artifacts.md)

## 常见补充参数

- `--pool-source turnover-top|record-watch|custom`
- `--pool-file PATH`
- `--llm-min-baseline-score SCORE`
- `--llm-review-limit N`
- `--recompute`
- `--environment-state`
- `--environment-reason`
