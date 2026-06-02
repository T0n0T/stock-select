# Strong B3 Red MACD Report

- scope: env=strong, verdict in PASS/WATCH, signal in B3/B3+
- sample_count: 238
- ret3>=5: 70
- ret3<=0: 105
- positive_rate: 0.294
- negative_rate: 0.441
- ret3_mean: 1.56
- ret3_median: 1.21

- diagnosis: Tests whether strong B3/B3+ is sensitive to renewed red MACD expansion plus price and turnover rising together.

## Condition Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| green_or_zero\|mixed | 72 | 0.303 | 24 | 35 | 0.333 | 0.486 | 0.58 | 0.64 | -0.27 | -1.6 |
| green_or_zero\|price_up_turnover_not | 61 | 0.256 | 14 | 26 | 0.23 | 0.426 | 1.38 | 0.91 | 0.93 | 0.0 |
| red_expanding\|price_up_turnover_not | 55 | 0.231 | 21 | 19 | 0.382 | 0.345 | 3.42 | 3.7 | 5.85 | 2.9 |
| red_expanding\|mixed | 33 | 0.139 | 7 | 17 | 0.212 | 0.515 | 0.84 | -0.48 | -1.59 | -0.96 |
| red_contracting\|mixed | 12 | 0.05 | 3 | 6 | 0.25 | 0.5 | 1.09 | 0.01 | 1.96 | -1.09 |
| red_contracting\|price_up_turnover_not | 5 | 0.021 | 1 | 2 | 0.2 | 0.4 | 3.13 | 3.57 | 7.96 | 8.03 |

## Factor Condition Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B3\|trend_start\|red_expanding\|price_up_turnover_not\|price=near_high\|volume=normal\|kdj=rising | 18 | 0.076 | 8 | 7 | 0.444 | 0.389 | 3.34 | 4.03 | 3.79 | 1.98 |
| B3\|trend_start\|green_or_zero\|price_up_turnover_not\|price=upper\|volume=normal\|kdj=rising | 16 | 0.067 | 3 | 9 | 0.188 | 0.562 | 0.22 | -0.33 | -0.07 | -0.04 |
| B3\|trend_start\|red_expanding\|price_up_turnover_not\|price=upper\|volume=normal\|kdj=rising | 16 | 0.067 | 6 | 6 | 0.375 | 0.375 | 3.15 | 3.61 | 7.68 | 4.43 |
| B3\|rebound\|green_or_zero\|mixed\|price=upper\|volume=normal\|kdj=rising | 11 | 0.046 | 3 | 5 | 0.273 | 0.455 | -0.38 | 2.5 | 2.56 | 1.17 |
| B3\|rebound\|green_or_zero\|mixed\|price=upper\|volume=normal\|kdj=neutral | 10 | 0.042 | 4 | 5 | 0.4 | 0.5 | 0.39 | -1.02 | 2.45 | -0.56 |
| B3\|rebound\|red_expanding\|mixed\|price=upper\|volume=normal\|kdj=rising | 10 | 0.042 | 1 | 5 | 0.1 | 0.5 | -0.36 | -0.51 | 0.45 | 1.06 |
| B3\|rebound\|red_expanding\|mixed\|price=near_high\|volume=normal\|kdj=rising | 9 | 0.038 | 2 | 5 | 0.222 | 0.556 | -0.15 | -1.64 | -4.83 | -5.92 |
| B3\|trend_start\|green_or_zero\|price_up_turnover_not\|price=upper\|volume=normal\|kdj=neutral | 9 | 0.038 | 2 | 4 | 0.222 | 0.444 | 0.79 | 0.91 | -1.18 | -1.01 |
| B3\|rebound\|green_or_zero\|mixed\|price=near_high\|volume=normal\|kdj=rising | 7 | 0.029 | 1 | 4 | 0.143 | 0.571 | -4.51 | -1.24 | -4.85 | -2.17 |
| B3\|trend_start\|green_or_zero\|price_up_turnover_not\|price=near_high\|volume=normal\|kdj=rising | 7 | 0.029 | 2 | 2 | 0.286 | 0.286 | 1.89 | 1.41 | 1.96 | 3.05 |
| B3\|rebound\|green_or_zero\|mixed\|price=extended_or_unknown\|volume=normal\|kdj=repair_from_low | 5 | 0.021 | 2 | 1 | 0.4 | 0.2 | 5.01 | 2.41 | 2.98 | -1.03 |
| B3\|rebound\|green_or_zero\|mixed\|price=upper\|volume=normal\|kdj=repair_from_low | 5 | 0.021 | 0 | 4 | 0.0 | 0.8 | -2.75 | -3.5 | -4.88 | -2.23 |
| B3\|rebound\|green_or_zero\|price_up_turnover_not\|price=upper\|volume=normal\|kdj=rising | 4 | 0.017 | 0 | 1 | 0.0 | 0.25 | 1.06 | 1.37 | -3.97 | -4.35 |
| B3\|trend_start\|green_or_zero\|price_up_turnover_not\|price=upper\|volume=normal\|kdj=repair_from_low | 4 | 0.017 | 0 | 0 | 0.0 | 0.0 | 1.84 | 1.56 | 3.91 | 4.17 |
| B3\|trend_start\|red_expanding\|mixed\|price=near_high\|volume=normal\|kdj=rising | 4 | 0.017 | 1 | 2 | 0.25 | 0.5 | 1.45 | 1.32 | 0.24 | 0.04 |
| B3\|trend_start\|red_expanding\|price_up_turnover_not\|price=near_high\|volume=expanding\|kdj=rising | 4 | 0.017 | 1 | 2 | 0.25 | 0.5 | 2.04 | -0.89 | 4.69 | 2.56 |
| B3\|rebound\|green_or_zero\|mixed\|price=upper\|volume=shrinking\|kdj=rising | 3 | 0.013 | 0 | 2 | 0.0 | 0.667 | 0.38 | -0.68 | -2.97 | -3.81 |
| B3\|rebound\|red_contracting\|mixed\|price=near_high\|volume=normal\|kdj=rising | 3 | 0.013 | 0 | 2 | 0.0 | 0.667 | -2.73 | -3.71 | -1.98 | 0.02 |
| B3\|rebound\|red_contracting\|mixed\|price=upper\|volume=normal\|kdj=neutral | 3 | 0.013 | 2 | 1 | 0.667 | 0.333 | 5.43 | 9.18 | 10.71 | 14.29 |
| B3\|rebound\|red_expanding\|mixed\|price=middle\|volume=normal\|kdj=rising | 3 | 0.013 | 1 | 1 | 0.333 | 0.333 | 0.8 | 0.33 | 1.45 | 6.02 |
| B3\|rebound\|red_expanding\|price_up_turnover_not\|price=near_high\|volume=normal\|kdj=rising | 3 | 0.013 | 2 | 0 | 0.667 | 0.0 | 7.81 | 10.26 | 23.6 | 15.88 |
| B3\|trend_start\|green_or_zero\|mixed\|price=upper\|volume=normal\|kdj=neutral | 3 | 0.013 | 1 | 2 | 0.333 | 0.667 | 0.61 | -2.11 | -0.18 | -2.12 |
| B3\|trend_start\|red_contracting\|price_up_turnover_not\|price=upper\|volume=normal\|kdj=neutral | 3 | 0.013 | 0 | 1 | 0.0 | 0.333 | 2.3 | 3.57 | 2.03 | 8.03 |
| B3\|trend_start\|red_expanding\|mixed\|price=upper\|volume=normal\|kdj=rising | 3 | 0.013 | 2 | 1 | 0.667 | 0.333 | 9.97 | 6.56 | 4.56 | 2.56 |
| B3\|trend_start\|red_expanding\|price_up_turnover_not\|price=upper\|volume=normal\|kdj=neutral | 3 | 0.013 | 1 | 1 | 0.333 | 0.333 | 1.32 | 3.7 | -3.65 | -1.88 |
| B3\|rebound\|green_or_zero\|mixed\|price=middle\|volume=shrinking\|kdj=low | 2 | 0.008 | 1 | 1 | 0.5 | 0.5 | 2.01 | 2.01 | 5.15 | 5.15 |
| B3\|rebound\|green_or_zero\|mixed\|price=near_low\|volume=normal\|kdj=rising | 2 | 0.008 | 1 | 1 | 0.5 | 0.5 | -4.57 | -4.57 | -11.29 | -11.29 |
| B3\|rebound\|green_or_zero\|mixed\|price=upper\|volume=normal\|kdj=low | 2 | 0.008 | 1 | 1 | 0.5 | 0.5 | 4.35 | 4.35 | 4.47 | 4.47 |
| B3\|rebound\|green_or_zero\|mixed\|price=upper\|volume=shrinking\|kdj=neutral | 2 | 0.008 | 1 | 1 | 0.5 | 0.5 | 2.31 | 2.31 | -8.62 | -8.62 |
| B3\|rebound\|green_or_zero\|price_up_turnover_not\|price=near_high\|volume=normal\|kdj=rising | 2 | 0.008 | 1 | 1 | 0.5 | 0.5 | 11.96 | 11.96 | 19.47 | 19.47 |

## Typical Positive Samples

| date | code | condition | verdict | score | ret3 | ret5 | signal | signal_type | macd_hist | turnover | pct_chg |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |
| 2026-05-06 | 301369.SZ | green_or_zero\|price_up_turnover_not | WATCH | 4.1 | 28.79 | 44.7 | B3 | rebound | -0.06 | 3.65 | 1.26 |
| 2026-05-08 | 300292.SZ | red_expanding\|mixed | PASS | 4.27 | 24.68 | 18.87 | B3 | trend_start | 0.03 | 7.24 | -0.72 |
| 2026-05-08 | 301200.SZ | green_or_zero\|mixed | WATCH | 4.08 | 24.6 | 18.2 | B3 | trend_start | -1.74 | 1.14 | -3.18 |
| 2026-04-30 | 301387.SZ | red_expanding\|price_up_turnover_not | WATCH | 4.32 | 22.45 | 27.98 | B3 | trend_start | 0.46 | 9.59 | 2.38 |
| 2026-05-08 | 002897.SZ | green_or_zero\|mixed | WATCH | 3.67 | 18.52 | 7.69 | B3 | rebound | -0.58 | 5.7 | -1.13 |
| 2026-05-20 | 600114.SH | green_or_zero\|mixed | WATCH | 3.58 | 17.69 | 16.51 | B3 | rebound | -0.24 | 3.08 | -1.72 |
| 2026-05-08 | 300394.SZ | green_or_zero\|mixed | WATCH | 3.94 | 15.9 | 22.58 | B3 | rebound | -4.23 | 4.59 | -0.56 |
| 2026-04-28 | 603557.SH | green_or_zero\|price_up_turnover_not | PASS | 4.22 | 14.95 | 15.93 | B3+ | trend_start | -0.02 | 0.68 | 4.88 |
| 2026-05-08 | 300502.SZ | green_or_zero\|mixed | WATCH | 4.03 | 14.02 | 10.58 | B3 | rebound | -5.88 | 3.37 | -2.1 |
| 2026-05-06 | 688127.SH | red_expanding\|price_up_turnover_not | WATCH | 4.26 | 13.86 | 20.04 | B3 | trend_start | 0.4 | 3.16 | 1.94 |
| 2026-04-28 | 603580.SH | red_contracting\|mixed | PASS | 4.25 | 13.68 | 25.32 | B3 | rebound | 0.04 | 1.55 | -0.76 |
| 2026-05-08 | 300131.SZ | red_expanding\|price_up_turnover_not | WATCH | 4.28 | 12.76 | 19.48 | B3 | trend_start | 0.09 | 15.27 | 2.1 |
| 2026-04-30 | 601133.SH | green_or_zero\|mixed | WATCH | 3.96 | 12.73 | 13.04 | B3 | rebound | -0.38 | 3.78 | -2.4 |
| 2026-05-07 | 688478.SH | red_expanding\|price_up_turnover_not | WATCH | 3.62 | 12.43 | 46.09 | B3 | rebound | 0.59 | 5.65 | 3.91 |
| 2026-05-07 | 000791.SZ | red_expanding\|price_up_turnover_not | PASS | 4.64 | 12.18 | 10.46 | B3 | trend_start | 0.04 | 3.66 | 2.59 |
| 2026-05-08 | 301095.SZ | red_expanding\|price_up_turnover_not | WATCH | 4.28 | 11.85 | 20.53 | B3 | trend_start | 0.88 | 6.3 | 2.27 |
| 2026-05-07 | 003004.SZ | red_expanding\|price_up_turnover_not | WATCH | 3.85 | 11.75 | 9.86 | B3+ | trend_start | 0.39 | 0.74 | 5.01 |
| 2026-04-30 | 601975.SH | green_or_zero\|mixed | WATCH | 3.59 | 11.61 | 4.02 | B3 | rebound | -0.03 | 4.56 | -1.97 |
| 2026-04-28 | 300651.SZ | green_or_zero\|price_up_turnover_not | WATCH | 4.01 | 11.51 | 9.44 | B3 | trend_start | -0.12 | 14.67 | 0.93 |
| 2026-05-06 | 301232.SZ | green_or_zero\|price_up_turnover_not | WATCH | 4.36 | 11.47 | 8.89 | B3 | trend_start | -0.07 | 14.96 | 2.57 |
| 2026-04-21 | 301239.SZ | red_contracting\|mixed | WATCH | 4.18 | 10.98 | 16.84 | B3 | trend_start | 0.08 | 1.03 | -0.36 |
| 2026-05-07 | 301235.SZ | red_expanding\|price_up_turnover_not | WATCH | 4.35 | 10.86 | 11.5 | B3+ | trend_start | 0.45 | 7.48 | 1.18 |
| 2026-05-08 | 300776.SZ | red_contracting\|price_up_turnover_not | WATCH | 4.41 | 10.57 | 28.66 | B3 | trend_start | 0.84 | 7.99 | 1.13 |
| 2026-04-28 | 300811.SZ | red_expanding\|price_up_turnover_not | WATCH | 4.1 | 10.26 | 8.83 | B3 | rebound | 0.7 | 4.41 | 1.74 |
| 2026-05-06 | 688418.SH | green_or_zero\|price_up_turnover_not | WATCH | 3.59 | 10.15 | 8.4 | B3 | trend_start | -0.11 | 5.77 | 3.49 |
| 2026-04-20 | 300191.SZ | green_or_zero\|price_up_turnover_not | WATCH | 3.5 | 9.99 | 4.21 | B3 | trend_start | -0.17 | 5.47 | 1.68 |
| 2026-05-06 | 301196.SZ | green_or_zero\|mixed | WATCH | 4.13 | 9.87 | 45.93 | B3 | rebound | -1.18 | 5.23 | -2.27 |
| 2026-05-08 | 603838.SH | red_expanding\|price_up_turnover_not | PASS | 4.77 | 9.74 | 8.57 | B3 | trend_start | 0.01 | 0.49 | 2.27 |
| 2026-05-08 | 002559.SZ | red_expanding\|mixed | WATCH | 4.26 | 9.56 | 4.23 | B3 | rebound | 0.03 | 3.92 | -1.0 |
| 2026-05-08 | 688679.SH | green_or_zero\|mixed | WATCH | 4.0 | 9.28 | 16.88 | B3 | rebound | -0.27 | 2.57 | -3.6 |
