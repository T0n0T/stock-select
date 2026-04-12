# B2 Formula Rewrite Design

## Goal

Rewrite `b2` so it keeps the existing "recent B1 J-hit" history condition, retains `zxdq > zxdkx`, and replaces the old weekly-bull / MACD-hist-rising entry logic with the supplied Tongdaxin-style daily, weekly, and monthly conditions.

## Screening Contract

`b2` continues to use the existing top-turnover liquidity pool and the existing recent-`J` history condition:

- look back the most recent 15 trading days ending on `pick_date`
- pass if any day in that window satisfies the existing `b1` `J` condition:
  - `J < 15`
  - or `J <= expanding 10% quantile for that symbol`

On `pick_date`, `b2` now requires all of the following:

- `zxdq > zxdkx`
- `ma25 = MA(close, 25)`
- `support_valid = low <= ma25 * 1.005 and close >= ma25`
- `volume_shrink = volume < ref(volume, 1)`
- daily `MACD` bullish: `dif > dea`
- weekly `MACD` bullish: weekly `dif > dea`
- monthly `MACD` bullish: monthly `dif > dea`
- `ma60_up = ma60 >= ref(ma60, 1)`
- `ma144_distance_ok = abs((close / ma144 - 1) * 100) <= 30`

The old `weekly_ma_bull` and five-day strictly rising `macd_hist` checks are removed from `b2`.

## Implementation Notes

- Keep the rewrite isolated to `src/stock_select/strategies/b2.py` plus any directly affected CLI breakdown strings and tests.
- Reuse existing daily `MACD` helpers where practical.
- Compute weekly and monthly `MACD` from history up to `pick_date`, using the latest close observed in each week or month as of that date.
- Treat missing or malformed inputs, missing previous volume, and insufficient MA history as `fail_insufficient_history`.

## Failure Buckets

`b2` should report first-failed-condition stats with these buckets:

- `total_symbols`
- `eligible`
- `fail_recent_j`
- `fail_insufficient_history`
- `fail_support_ma25`
- `fail_volume_shrink`
- `fail_zxdq_zxdkx`
- `fail_daily_macd`
- `fail_weekly_macd`
- `fail_monthly_macd`
- `fail_ma60_trend`
- `fail_ma144_distance`
- `selected`
