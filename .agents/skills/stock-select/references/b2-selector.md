# B2 Selector Reference

Reproduce the current repository's B2 preselection behavior with deterministic Python logic.

Screening flow:

- Phase 1 is a non-MACD structural prefilter.
- Phase 2 is deterministic weekly/daily MACD wave classification.

Phase 1 required conditions:

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
- On `pick_date`, require `ma60 >= ref(ma60, 1)`.
- On `pick_date`, require `abs((close / ma144 - 1) * 100) <= 30`.

Phase 2 wave rules:

- Weekly waves allowed:
  - `wave1`
  - `wave3`
- Weekly `wave2` and `invalid` are rejected.
- Daily waves allowed:
  - `wave2_end`
  - `wave4_end`
- Daily `invalid` is rejected.
- `wave4_end` is only valid when `third_wave_gain <= 0.30`.
- Current `b2` is left-biased:
  - focus on daily second-wave pullback end
  - or fourth-wave pullback end after a third-wave gain no larger than 30%

Important exclusions:

- `b2` does not require `close > zxdkx`.
- `b2` does not inherit the `b1` max-volume-day-not-bearish filter.
- `b2` phase 1 does not require any daily `MACD` gate.
- `b2` no longer uses monthly `MACD` as a screening requirement.
- `b2` no longer uses `weekly_ma_bull` or a strictly increasing five-day `macd_hist` rule.

Supporting calculations to preserve:

- `turnover_n` uses the same rolling turnover definition as `b1`.
- `J`, `zxdq`, and `zxdkx` should be recomputed locally.
- Daily frames should expose `ma25`, `ma60`, and `ma144`.
- Wave classification is computed on demand from `trade_date` and `close`; phase 1 no longer depends on precomputed `dif` / `dea` columns.
- `review` task payloads for `b2` should include:
  - `weekly_wave_context`
  - `daily_wave_context`
  - `wave_combo_context`
