# Runtime Layout

默认 runtime root：

```text
~/.agents/skills/stock-select/runtime
```

EOD b2：

```text
candidates/<pick_date>.b2.json
prepared/<pick_date>.bin
prepared/<pick_date>.meta.json
select/<pick_date>.b2/run.json
select/<pick_date>.b2/candidates.json
select/<pick_date>.b2/factors.json
select/<pick_date>.b2/ranked.json
select/<pick_date>.b2/feature_vectors.json
select/<pick_date>.b2/display.json
select/<pick_date>.b2/llm_tasks.json
select/<pick_date>.b2/llm_annotations.json
select/<pick_date>.b2/llm_raw/<code>.json
charts/<pick_date>.b2/<code>_day.png
environment/history.jsonl
environment/latest.json
environment/daily/<pick_date>.<state>.json
custom-pool.txt
```

Intraday b2：

```text
candidates/<pick_date>.intraday.b2.json
prepared/<pick_date>.intraday.bin
prepared/<pick_date>.intraday.meta.json
select/<pick_date>.intraday.b2/run.json
select/<pick_date>.intraday.b2/candidates.json
select/<pick_date>.intraday.b2/factors.json
select/<pick_date>.intraday.b2/ranked.json
select/<pick_date>.intraday.b2/feature_vectors.json
select/<pick_date>.intraday.b2/display.json
select/<pick_date>.intraday.b2/llm_tasks.json
select/<pick_date>.intraday.b2/llm_annotations.json
select/<pick_date>.intraday.b2/llm_raw/<code>.json
charts/<pick_date>.intraday.b2/<code>_day.png
```

盘中 artifact key 是 `<pick_date>.intraday.b2`。重复盘中运行会刷新同一日期组，不按时间戳创建新组。

