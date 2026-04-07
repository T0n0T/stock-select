# Runtime Layout

Write all generated outputs under:

```text
~/.agents/skills/stock-select/runtime/
  candidates/<pick_date>.json
  charts/<pick_date>/<code>_day.png
  reviews/<pick_date>/<code>.json
  reviews/<pick_date>/summary.json
```

Current behavior:

- `candidates/<pick_date>.json` stores `pick_date`, `method`, and screened candidate rows.
- `charts/<pick_date>/<code>_day.png` stores rendered daily chart images for chart review.
- `reviews/<pick_date>/<code>.json` stores the local structured review result for one candidate.
- `reviews/<pick_date>/summary.json` stores the aggregated recommendations, exclusions, and failures.

Optional additions:

- `logs/<run_id>.log` for execution logs
- config snapshot and query metadata embedded in candidate output JSON
