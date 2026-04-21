# B1 Selector Reference

Reproduce the current repository's B1 predicate behavior after a symbol reaches the prepared-screen stage.

This reference describes the deterministic selector predicates themselves. Runtime pool-source selection, candidate/cache reuse, and stale or malformed artifact handling are documented in `README.md` and the CLI implementation.

Required conditions:

- J is low enough by absolute threshold or low historical quantile.
- `close > zxdkx`.
- `zxdq > zxdkx`.
- Weekly moving averages are in bullish alignment.
- The max-volume day inside the lookback window is not bearish.
- `chg_d <= 4.0`.
- `v_shrink`.
- `safe_mode`.
- `lt_filter`.

Supporting calculations to preserve:

- `turnover_n` uses mid-price times volume over a rolling window.
- Volume input should map database `vol` to the internal volume field.
- `zxdq` and `zxdkx` should be recomputed locally.
- Weekly trend judgment should come from weekly close series and moving averages.
- The exact formulas for `chg_d`, `v_shrink`, `safe_mode`, and `lt_filter` should follow `stock_select.strategies.b1.compute_b1_tightening_columns()` as the source of truth.
