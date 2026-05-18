# 共用运行产物

运行时产物默认写入：

```text
~/.agents/skills/stock-select/runtime/
```

## EOD 产物

```text
candidates/<pick_date>.<method>.json
prepared/<pick_date>.feather
prepared/<pick_date>.meta.json
prepared/<pick_date>.hcr.feather
prepared/<pick_date>.hcr.meta.json
charts/<pick_date>.<method>/<code>_day.png
reviews/<pick_date>.<method>/<code>.json
reviews/<pick_date>.<method>/llm_review_tasks.json
reviews/<pick_date>.<method>/llm_review_results/<code>.json
reviews/<pick_date>.<method>/summary.json
watch_pool.csv
```

说明：

- `b1` / `b2` / `dribull` 共用 `prepared/<pick_date>.feather`
- `hcr` 使用 `prepared/<pick_date>.hcr.feather`
- `dribull` 的 warmup 历史按需现算，不单独落盘

## Intraday 产物

```text
candidates/<run_id>.<method>.json
prepared/<trade_date>.intraday.feather
prepared/<trade_date>.intraday.meta.json
prepared/<trade_date>.intraday.hcr.feather
prepared/<trade_date>.intraday.hcr.meta.json
charts/<run_id>.<method>/
reviews/<run_id>.<method>/
```

说明：

- intraday 的 candidate/chart/review 按 `run_id` 隔离
- intraday 的 prepared cache 按交易日共享

## 清理命令

```bash
uv run stock-select clean --pick-date YYYY-MM-DD
uv run stock-select clean --intraday
```

含义：

- `clean --pick-date` 删除该交易日 EOD 产物
- `clean --intraday` 删除历史盘中产物并保留当天盘中产物
