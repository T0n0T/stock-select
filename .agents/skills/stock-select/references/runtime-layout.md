# Runtime Layout

Write all generated outputs under:

```text
~/.agents/skills/stock-select/runtime/
  candidates/<base_key>.<method>.json
  prepared/<pick_date>.pkl
  prepared/<pick_date>.hcr.pkl
  prepared/<trade_date>.intraday.pkl
  prepared/<trade_date>.intraday.hcr.pkl
  charts/<base_key>.<method>/<code>_day.png
  reviews/<base_key>.<method>/<code>.json
  reviews/<base_key>.<method>/summary.json
  reviews/<base_key>.<method>/llm_review_tasks.json
  reviews/<base_key>.<method>/llm_review_results/<code>.json
  watch_pool.csv
```

Current behavior:

- `<base_key>` is `<pick_date>` for end-of-day runs and `<run_id>` for intraday snapshot runs.
- `candidates/<base_key>.<method>.json` stores mode metadata, selected `method`, and screened candidate rows.
- `prepared/<pick_date>.pkl` stores the shared end-of-day base prepare reused by `b1` and `b2`.
- `prepared/<trade_date>.intraday.pkl` stores the shared intraday base prepare reused by `b1` and `b2`.
- `prepared/<pick_date>.hcr.pkl` and `prepared/<trade_date>.intraday.hcr.pkl` stay method-specific for `hcr`.
- `charts/<base_key>.<method>/<code>_day.png` stores rendered daily chart images for chart review.
- `reviews/<base_key>.<method>/<code>.json` stores the local structured review result for one candidate.
- `reviews/<base_key>.<method>/summary.json` stores the aggregated recommendations, exclusions, and failures.
- `reviews/<base_key>.<method>/llm_review_tasks.json` stores one dispatch task per candidate.
- `reviews/<base_key>.<method>/llm_review_results/<code>.json` stores raw subagent JSON before `review-merge` validation.
- `watch_pool.csv` stores end-of-day `PASS` and `WATCH` rows imported by `record-watch`, including `recorded_at`, with retention trimmed by trading-day window.
- The watch pool is shared across methods; the CSV still keeps a `method` column, but runtime storage is no longer split into per-method files.
- `b2` phase-two MACD warmup is on-demand and is not stored as a separate prepared cache.

Optional additions:

- `logs/<run_id>.log` for execution logs
- config snapshot and query metadata embedded in candidate output JSON
