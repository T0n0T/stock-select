# 单票分析与观察池

本文说明 `analyze-symbol` 和 `record-watch`。

## `analyze-symbol`

入口：

```bash
uv run stock-select analyze-symbol --method b1 --symbol 002350.SZ --pick-date YYYY-MM-DD --dsn postgresql://...
```

作用：

- 直接从 PostgreSQL 拉取单只股票历史
- 导出单张日线 PNG
- 复用方法现有 baseline review 逻辑
- 写出单个 `result.json`

适合：

- 不走 candidate 文件，直接看单只票
- 检查某个方法对单票的 baseline 结论
- 临时用 `--environment-state` 看环境变化对评分的影响

## `record-watch`

入口：

```bash
uv run stock-select record-watch --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
```

作用：

- 读取 `reviews/<pick_date>.<method>/summary.json`
- 抽取 `PASS` / `WATCH` 股票
- 更新 `watch_pool.csv`

特点：

- 同一 `method + code` 再次入选时刷新为最新 `pick_date`
- 按交易日窗口裁剪老记录
- 可供 `--pool-source record-watch` 复用
