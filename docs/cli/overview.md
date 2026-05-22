# CLI 总览

`stock-select` CLI 面向两类工作：

- 选股主流程：`screen`、`chart`、`review`、`run`
- 辅助命令：`market-env`、`analyze-symbol`、`record-watch`、`review-merge`、`html`、`clean`

## 常见入口

EOD：

```bash
uv run stock-select run --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
```

盘中：

```bash
uv run stock-select run --method b1 --intraday --dsn postgresql://...
```

只做 baseline review：

```bash
uv run stock-select review --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
```

## 模式选择

- `--pick-date`：收盘后或明确指定某个交易日时使用
- `--intraday`：只在交易日盘中、且明确需要盘中快照时使用

当前实现里，`intraday` 的个股数据来自：

- PostgreSQL 中前一交易日及更早的确认历史
- Tushare `rt_k` 提供的当日盘中快照

市场环境不是独立的盘中快照模型；默认仍按当前命令能解析到的环境状态运行。

## 环境临时覆盖

以下命令支持临时覆盖环境状态：

- `screen`
- `review`
- `run`
- `analyze-symbol`

参数：

- `--environment-state {strong|neutral|weak}`
- `--environment-reason "..."`（可选）

说明：

- 只作用于当前命令
- 不写入 `runtime/environment/` 历史
- 不写入 candidate 产物
- `reason` 只用于本次 `summary.json` / `environment_snapshot` 留痕

## 相关文档

- [screen / chart / review / run](./screen-chart-review-run.md)
- [market-env](./market-environment.md)
- [analyze-symbol / record-watch](./analyze-symbol-and-watch.md)
- [html / clean / review-merge](./html-and-clean.md)
- [方法文档总览](../README.md)
