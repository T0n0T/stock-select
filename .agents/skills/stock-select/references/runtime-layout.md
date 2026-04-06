# Runtime Layout

Write all generated outputs under:

```text
~/.agents/skills/stock-select/runtime/
  candidates/<pick_date>.json
  charts/<pick_date>/<code>_day.jpg
  reviews/<pick_date>/<code>.json
  reviews/<pick_date>/summary.json
```

Recommended additions:

- `logs/<run_id>.log` for execution logs
- config snapshot and query metadata embedded in candidate output JSON
