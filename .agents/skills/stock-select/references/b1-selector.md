# B1 Selector Reference

Reproduce the current repository's B1 preselection behavior with deterministic Python logic.

Required conditions:

- J is low enough by absolute threshold or low historical quantile.
- `close > zxdkx`.
- `zxdq > zxdkx`.
- Weekly moving averages are in bullish alignment.
- The max-volume day inside the lookback window is not bearish.

Supporting calculations to preserve:

- `turnover_n` uses mid-price times volume over a rolling window.
- Volume input should map database `vol` to the internal volume field.
- `zxdq` and `zxdkx` should be recomputed locally.
- Weekly trend judgment should come from weekly close series and moving averages.
