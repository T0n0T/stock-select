# Runtime Layout

Write all generated outputs under:

```text
~/.agents/skills/stock-select/runtime/
  candidates/<base_key>.<method>.json
  prepared/<base_key>.<method>.pkl
  charts/<base_key>.<method>/<code>_day.png
  reviews/<base_key>.<method>/<code>.json
  reviews/<base_key>.<method>/summary.json
  reviews/<base_key>.<method>/llm_review_tasks.json
  reviews/<base_key>.<method>/llm_review_results/<code>.json
```

Current behavior:

- `<base_key>` is `<pick_date>` for end-of-day runs and `<run_id>` for intraday snapshot runs.
- `candidates/<base_key>.<method>.json` stores mode metadata, selected `method`, and screened candidate rows.
- `prepared/<base_key>.<method>.pkl` stores the prepared per-symbol indicator cache reused by chart and review.
- `charts/<base_key>.<method>/<code>_day.png` stores rendered daily chart images for chart review.
- `reviews/<base_key>.<method>/<code>.json` stores the local structured review result for one candidate.
- `reviews/<base_key>.<method>/summary.json` stores the aggregated recommendations, exclusions, and failures.
- `reviews/<base_key>.<method>/llm_review_tasks.json` stores one dispatch task per candidate.
- `reviews/<base_key>.<method>/llm_review_results/<code>.json` stores raw subagent JSON before `review-merge` validation.

Optional additions:

- `logs/<run_id>.log` for execution logs
- config snapshot and query metadata embedded in candidate output JSON
