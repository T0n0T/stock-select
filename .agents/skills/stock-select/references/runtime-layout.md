# Runtime Layout

Default runtime root:

```text
~/.agents/skills/stock-select/runtime
```

End-of-day:

```text
candidates/<pick_date>.<method>.json
prepared/<pick_date>.bin
prepared/<pick_date>.meta.json
charts/<pick_date>.<method>/<code>_day.png
reviews/<pick_date>.<method>/<code>.json
reviews/<pick_date>.<method>/summary.json
reviews/<pick_date>.<method>/llm_review_tasks.json
reviews/<pick_date>.<method>/llm_review_results/<code>.json
environment/history.jsonl
environment/latest.json
environment/daily/<pick_date>.<state>.json
custom-pool.txt
ad_hoc/<pick_date>.<method>.<code>/result.json
ad_hoc/<pick_date>.<method>.<code>/<code>_day.png
```

Intraday:

```text
prepared/<trade_date>.intraday.bin
prepared/<trade_date>.intraday.meta.json
candidates/<trade_date>.intraday.<method>.json
charts/<trade_date>.intraday.<method>/<code>_day.png
reviews/<trade_date>.intraday.<method>/<code>.json
reviews/<trade_date>.intraday.<method>/summary.json
reviews/<trade_date>.intraday.<method>/llm_review_tasks.json
reviews/<trade_date>.intraday.<method>/llm_review_results/<code>.json
```

Intraday path key is `<trade_date>.intraday`, so repeated intraday runs for the same trade date and method refresh one runtime group. `run_id` remains inside candidate/prepared metadata as the fetch marker for the current refresh.
