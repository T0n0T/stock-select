# 站点与清理命令

本文说明 `review-merge`、`html`、`render-html`、`clean`。

## `review-merge`

入口：

```bash
uv run stock-select review-merge --method <method> --pick-date YYYY-MM-DD
```

作用：

- 读取 `llm_review_results/*.json`
- 校验与归一化子代理图评结果
- 回填到单股 review
- 重写最终 `summary.json`

## `html render`

入口：

```bash
uv run stock-select html render --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
```

作用：

- 读取 `summary.json`
- 生成 `runtime/reviews/site/<pick_date>.<method>/index.html`
- 重建总索引页

## `html zip`

入口：

```bash
uv run stock-select html zip --method <method> --pick-date YYYY-MM-DD
```

作用：

- 打包已渲染的 HTML 报告与引用图表

## `html serve`

入口：

```bash
uv run stock-select html serve
```

作用：

- 暴露整个 `runtime/reviews/site/` 为本地静态站点

## `render-html`

兼容入口：

```bash
uv run stock-select render-html --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
```

内部仍转调 `html render` + `html zip`。

## `clean`

入口：

```bash
uv run stock-select clean --pick-date YYYY-MM-DD
uv run stock-select clean --intraday
```

作用：

- `clean --pick-date`：删除该交易日 EOD 产物
- `clean --intraday`：删除历史盘中产物并保留当天盘中产物

运行产物结构见：

- [共用运行产物](../share/runtime-artifacts.md)
