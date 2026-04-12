# B2 Selector Reference

Reproduce the current repository's B2 preselection behavior with deterministic Python logic.

Required conditions:

- Reuse the same top-turnover liquidity pool filter as `b1`.
- Look back the most recent 15 trading days ending on `pick_date`.
- Pass the recent-`J` rule if any day in that window satisfies the existing `b1` low-`J` condition:
  - `J < 15`
  - or `J <=` the expanding 10% quantile for that symbol
- On `pick_date`, require `zxdq > zxdkx`.
- On `pick_date`, require `support_valid`:
  - `low <= ma25 * 1.005`
  - `close >= ma25`
- On `pick_date`, require shrinking volume:
  - `volume < ref(volume, 1)`
- On `pick_date`, require bullish daily `MACD`:
  - `dif > dea`
- On `pick_date`, require bullish weekly `MACD`:
  - `dif_w > dea_w`
- On `pick_date`, require bullish monthly `MACD`:
  - `dif_m > dea_m`
- On `pick_date`, require `ma60 >= ref(ma60, 1)`.
- On `pick_date`, require `abs((close / ma144 - 1) * 100) <= 30`.

Important exclusions:

- `b2` does not require `close > zxdkx`.
- `b2` does not inherit the `b1` max-volume-day-not-bearish filter.
- `b2` no longer uses `weekly_ma_bull` or a strictly increasing five-day `macd_hist` rule.

Supporting calculations to preserve:

- `turnover_n` uses the same rolling turnover definition as `b1`.
- `J`, `zxdq`, and `zxdkx` should be recomputed locally.
- Daily frames should expose `ma25`, `ma60`, and `ma144`.
- Daily `MACD` should expose `dif`, `dea`, and raw signed `macd_hist`.
- Weekly and monthly `MACD` should align the latest period-close `dif` / `dea` values back onto each daily row as `dif_w`, `dea_w`, `dif_m`, and `dea_m`.
