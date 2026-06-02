# Weak Indicator Report

- scope: env=weak indicator diagnostics from daily_indicators.extra_factors_jsonb
- sample_count: 1930
- pass_watch_count: 1074
- diagnosis: Adds BBI, BIAS and OBV from daily_indicators to test whether weak high-ret3 samples can be separated from negative samples after price/volume/MACD factors are already known.

## Weak Indicator Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bbi=above\|bias=neutral\|obv=flat | 594 | 0.308 | 91 | 303 | 0.153 | 0.51 | -0.29 | -0.07 | -0.87 | -0.89 |
| bbi=above_extended\|bias=positive\|obv=flat | 464 | 0.24 | 83 | 250 | 0.179 | 0.539 | -0.47 | -0.7 | -1.8 | -2.23 |
| bbi=below_near\|bias=neutral\|obv=flat | 283 | 0.147 | 42 | 167 | 0.148 | 0.59 | -1.39 | -1.58 | -1.05 | -2.08 |
| bbi=above\|bias=positive\|obv=flat | 167 | 0.087 | 25 | 95 | 0.15 | 0.569 | -0.94 | -1.42 | -2.24 | -1.6 |
| bbi=above_extended\|bias=neutral\|obv=flat | 143 | 0.074 | 21 | 78 | 0.147 | 0.545 | -1.07 | -0.69 | -1.63 | -1.53 |
| bbi=above_extended\|bias=high_positive\|obv=flat | 71 | 0.037 | 11 | 45 | 0.155 | 0.634 | -0.78 | -2.27 | -2.97 | -4.06 |
| bbi=above_extended\|bias=positive\|obv=rising | 49 | 0.025 | 9 | 27 | 0.184 | 0.551 | -0.55 | -1.45 | -2.96 | -5.45 |
| bbi=below_deep\|bias=neutral\|obv=flat | 39 | 0.02 | 7 | 26 | 0.179 | 0.667 | -0.92 | -1.89 | -0.8 | -2.7 |
| bbi=above\|bias=neutral\|obv=rising | 23 | 0.012 | 4 | 14 | 0.174 | 0.609 | -1.03 | -0.92 | -1.15 | -2.56 |
| bbi=above_extended\|bias=high_positive\|obv=rising | 20 | 0.01 | 8 | 7 | 0.4 | 0.35 | 4.87 | 3.06 | 4.44 | 1.69 |
| bbi=above\|bias=positive\|obv=rising | 13 | 0.007 | 3 | 8 | 0.231 | 0.615 | -1.26 | -3.78 | -2.63 | -3.5 |
| bbi=below_deep\|bias=negative\|obv=flat | 10 | 0.005 | 2 | 6 | 0.2 | 0.6 | 2.57 | -1.66 | 4.83 | 0.99 |
| bbi=above_extended\|bias=neutral\|obv=rising | 8 | 0.004 | 3 | 4 | 0.375 | 0.5 | 1.35 | 1.58 | -0.68 | 1.24 |
| bbi=below_near\|bias=positive\|obv=flat | 8 | 0.004 | 0 | 6 | 0.0 | 0.75 | -4.5 | -4.16 | -8.71 | -7.04 |
| bbi=above_extended\|bias=positive\|obv=falling | 6 | 0.003 | 2 | 3 | 0.333 | 0.5 | 2.34 | 0.89 | 1.2 | -3.66 |
| bbi=below_near\|bias=neutral\|obv=rising | 6 | 0.003 | 1 | 4 | 0.167 | 0.667 | 0.49 | -3.09 | -2.71 | -3.14 |
| bbi=above\|bias=neutral\|obv=falling | 5 | 0.003 | 1 | 3 | 0.2 | 0.6 | -1.64 | -0.11 | -0.99 | -2.46 |
| bbi=below_near\|bias=negative\|obv=flat | 5 | 0.003 | 0 | 5 | 0.0 | 1.0 | -5.34 | -2.11 | -6.43 | -8.17 |
| bbi=below_near\|bias=neutral\|obv=falling | 4 | 0.002 | 0 | 4 | 0.0 | 1.0 | -3.41 | -1.58 | -4.27 | -3.51 |
| bbi=above_extended\|bias=high_positive\|obv=falling | 2 | 0.001 | 0 | 1 | 0.0 | 0.5 | -2.48 | -2.48 | -6.25 | -6.25 |
| bbi=above\|bias=negative\|obv=flat | 2 | 0.001 | 0 | 1 | 0.0 | 0.5 | -2.69 | -2.69 | -1.42 | -1.42 |
| bbi=above\|bias=positive\|obv=falling | 2 | 0.001 | 0 | 2 | 0.0 | 1.0 | -3.48 | -3.48 | -5.58 | -5.58 |
| bbi=above\|bias=high_positive\|obv=rising | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 12.27 | 12.27 | 11.42 | 11.42 |
| bbi=below_deep\|bias=neutral\|obv=falling | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -1.36 | -1.36 | -1.05 | -1.05 |
| bbi=below_deep\|bias=neutral\|obv=rising | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -0.68 | -0.68 | -2.93 | -2.93 |
| bbi=below_deep\|bias=positive\|obv=flat | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 27.55 | 27.55 | 42.17 | 42.17 |
| bbi=below_near\|bias=positive\|obv=falling | 1 | 0.001 | 0 | 0 | 0.0 | 0.0 | 1.37 | 1.37 | 2.84 | 2.84 |
| bbi=below_near\|bias=positive\|obv=rising | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 6.76 | 6.76 | 1.69 | 1.69 |

## Weak PASS/WATCH Indicator Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bbi=above\|bias=neutral\|obv=flat | 331 | 0.308 | 53 | 166 | 0.16 | 0.502 | -0.32 | 0.0 | -0.69 | -1.18 |
| bbi=above_extended\|bias=positive\|obv=flat | 294 | 0.274 | 51 | 157 | 0.173 | 0.534 | -0.74 | -0.61 | -2.07 | -2.13 |
| bbi=below_near\|bias=neutral\|obv=flat | 110 | 0.102 | 15 | 74 | 0.136 | 0.673 | -2.1 | -2.74 | -1.15 | -2.96 |
| bbi=above_extended\|bias=neutral\|obv=flat | 102 | 0.095 | 14 | 60 | 0.137 | 0.588 | -1.43 | -1.37 | -2.51 | -1.93 |
| bbi=above\|bias=positive\|obv=flat | 81 | 0.075 | 12 | 45 | 0.148 | 0.556 | -1.16 | -1.59 | -2.4 | -1.77 |
| bbi=above_extended\|bias=high_positive\|obv=flat | 41 | 0.038 | 7 | 27 | 0.171 | 0.659 | 0.36 | -3.05 | -2.48 | -3.94 |
| bbi=above_extended\|bias=positive\|obv=rising | 28 | 0.026 | 5 | 19 | 0.179 | 0.679 | -1.88 | -3.92 | -6.0 | -6.87 |
| bbi=below_deep\|bias=neutral\|obv=flat | 21 | 0.02 | 1 | 16 | 0.048 | 0.762 | -4.02 | -2.93 | -3.71 | -3.38 |
| bbi=above_extended\|bias=high_positive\|obv=rising | 16 | 0.015 | 6 | 6 | 0.375 | 0.375 | 3.83 | 3.06 | 3.12 | 1.69 |
| bbi=above\|bias=neutral\|obv=rising | 10 | 0.009 | 2 | 7 | 0.2 | 0.7 | -2.2 | -2.21 | -2.44 | -4.29 |
| bbi=above_extended\|bias=neutral\|obv=rising | 8 | 0.007 | 3 | 4 | 0.375 | 0.5 | 1.35 | 1.58 | -0.68 | 1.24 |
| bbi=above\|bias=positive\|obv=rising | 7 | 0.007 | 1 | 4 | 0.143 | 0.571 | -2.33 | -2.38 | -6.62 | -6.17 |
| bbi=below_deep\|bias=negative\|obv=flat | 6 | 0.006 | 2 | 4 | 0.333 | 0.667 | 3.6 | -2.43 | 7.71 | -0.85 |
| bbi=above_extended\|bias=positive\|obv=falling | 4 | 0.004 | 2 | 2 | 0.5 | 0.5 | 3.24 | 5.12 | 2.41 | 3.96 |
| bbi=below_near\|bias=negative\|obv=flat | 3 | 0.003 | 0 | 3 | 0.0 | 1.0 | -3.94 | -1.07 | -6.49 | -8.17 |
| bbi=above\|bias=negative\|obv=flat | 2 | 0.002 | 0 | 1 | 0.0 | 0.5 | -2.69 | -2.69 | -1.42 | -1.42 |
| bbi=above\|bias=neutral\|obv=falling | 2 | 0.002 | 0 | 2 | 0.0 | 1.0 | -7.55 | -7.55 | -6.93 | -6.93 |
| bbi=below_near\|bias=positive\|obv=flat | 2 | 0.002 | 0 | 1 | 0.0 | 0.5 | -2.96 | -2.96 | -3.24 | -3.24 |
| bbi=above\|bias=high_positive\|obv=rising | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 12.27 | 12.27 | 11.42 | 11.42 |
| bbi=below_deep\|bias=neutral\|obv=falling | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -1.36 | -1.36 | -1.05 | -1.05 |
| bbi=below_deep\|bias=neutral\|obv=rising | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -0.68 | -0.68 | -2.93 | -2.93 |
| bbi=below_deep\|bias=positive\|obv=flat | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 27.55 | 27.55 | 42.17 | 42.17 |
| bbi=below_near\|bias=neutral\|obv=falling | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -1.23 | -1.23 | -3.28 | -3.28 |
| bbi=below_near\|bias=neutral\|obv=rising | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -4.26 | -4.26 | -4.36 | -4.36 |

## Weak Family + Indicator Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| other\|bbi=above\|bias=neutral\|obv=flat | 324 | 0.302 | 51 | 163 | 0.157 | 0.503 | -0.37 | -0.04 | -0.72 | -1.18 |
| other\|bbi=above_extended\|bias=positive\|obv=flat | 266 | 0.248 | 43 | 148 | 0.162 | 0.556 | -0.93 | -1.44 | -2.3 | -2.23 |
| other\|bbi=below_near\|bias=neutral\|obv=flat | 106 | 0.099 | 14 | 73 | 0.132 | 0.689 | -2.25 | -3.02 | -1.47 | -3.01 |
| other\|bbi=above_extended\|bias=neutral\|obv=flat | 98 | 0.091 | 14 | 56 | 0.143 | 0.571 | -1.39 | -1.37 | -2.61 | -1.97 |
| other\|bbi=above\|bias=positive\|obv=flat | 75 | 0.07 | 9 | 44 | 0.12 | 0.587 | -1.5 | -2.17 | -2.42 | -2.12 |
| other\|bbi=above_extended\|bias=high_positive\|obv=flat | 36 | 0.034 | 5 | 26 | 0.139 | 0.722 | -0.83 | -3.58 | -3.59 | -4.27 |
| other\|bbi=above_extended\|bias=positive\|obv=rising | 22 | 0.02 | 4 | 14 | 0.182 | 0.636 | -1.48 | -3.26 | -5.21 | -5.77 |
| other\|bbi=below_deep\|bias=neutral\|obv=flat | 21 | 0.02 | 1 | 16 | 0.048 | 0.762 | -4.02 | -2.93 | -3.71 | -3.38 |
| other\|bbi=above_extended\|bias=high_positive\|obv=rising | 12 | 0.011 | 3 | 6 | 0.25 | 0.5 | 2.95 | 1.16 | -0.8 | -2.77 |
| W-B\|bbi=above_extended\|bias=positive\|obv=flat | 11 | 0.01 | 3 | 3 | 0.273 | 0.273 | 1.54 | 1.56 | -0.19 | -2.3 |
| other\|bbi=above\|bias=neutral\|obv=rising | 10 | 0.009 | 2 | 7 | 0.2 | 0.7 | -2.2 | -2.21 | -2.44 | -4.29 |
| W-A\|bbi=above_extended\|bias=positive\|obv=flat | 8 | 0.007 | 3 | 1 | 0.375 | 0.125 | 3.16 | 3.4 | 1.62 | -0.21 |
| W-C\|bbi=above_extended\|bias=positive\|obv=flat | 7 | 0.007 | 2 | 4 | 0.286 | 0.571 | 0.02 | 0.0 | -1.28 | 0.26 |
| other\|bbi=above_extended\|bias=neutral\|obv=rising | 7 | 0.007 | 3 | 3 | 0.429 | 0.429 | 1.68 | 3.17 | -0.79 | 2.39 |
| other\|bbi=above\|bias=positive\|obv=rising | 7 | 0.007 | 1 | 4 | 0.143 | 0.571 | -2.33 | -2.38 | -6.62 | -6.17 |
| other\|bbi=below_deep\|bias=negative\|obv=flat | 6 | 0.006 | 2 | 4 | 0.333 | 0.667 | 3.6 | -2.43 | 7.71 | -0.85 |
| W-A\|bbi=above_extended\|bias=positive\|obv=rising | 4 | 0.004 | 1 | 3 | 0.25 | 0.75 | -1.1 | -5.47 | -5.85 | -6.25 |
| W-B\|bbi=above\|bias=positive\|obv=flat | 4 | 0.004 | 2 | 1 | 0.5 | 0.25 | 2.19 | 3.42 | -0.03 | -0.22 |
| W-C\|bbi=above_extended\|bias=high_positive\|obv=flat | 4 | 0.004 | 1 | 1 | 0.25 | 0.25 | 5.04 | 1.95 | 1.86 | 2.39 |
| W-D\|bbi=below_near\|bias=neutral\|obv=flat | 4 | 0.004 | 1 | 1 | 0.25 | 0.25 | 1.82 | 2.96 | 7.19 | 6.88 |
| W-A\|bbi=above_extended\|bias=high_positive\|obv=rising | 3 | 0.003 | 2 | 0 | 0.667 | 0.0 | 8.04 | 8.04 | 17.94 | 17.94 |
| W-A\|bbi=above_extended\|bias=neutral\|obv=flat | 3 | 0.003 | 0 | 3 | 0.0 | 1.0 | -3.01 | -2.1 | 0.16 | -0.49 |
| W-B\|bbi=above\|bias=neutral\|obv=flat | 3 | 0.003 | 1 | 1 | 0.333 | 0.333 | 1.23 | 0.71 | 1.98 | -0.14 |
| W-D\|bbi=above\|bias=neutral\|obv=flat | 3 | 0.003 | 1 | 1 | 0.333 | 0.333 | 6.45 | 1.01 | 1.13 | -5.02 |
| other\|bbi=above_extended\|bias=positive\|obv=falling | 3 | 0.003 | 1 | 2 | 0.333 | 0.667 | 0.75 | -0.47 | -2.36 | -4.92 |
| other\|bbi=below_near\|bias=negative\|obv=flat | 3 | 0.003 | 0 | 3 | 0.0 | 1.0 | -3.94 | -1.07 | -6.49 | -8.17 |
| W-B\|bbi=above_extended\|bias=positive\|obv=rising | 2 | 0.002 | 0 | 2 | 0.0 | 1.0 | -7.82 | -7.82 | -15.01 | -15.01 |
| W-D\|bbi=above_extended\|bias=positive\|obv=flat | 2 | 0.002 | 0 | 1 | 0.0 | 0.5 | -4.77 | -4.77 | 0.74 | 0.74 |
| other\|bbi=above\|bias=negative\|obv=flat | 2 | 0.002 | 0 | 1 | 0.0 | 0.5 | -2.69 | -2.69 | -1.42 | -1.42 |
| other\|bbi=above\|bias=neutral\|obv=falling | 2 | 0.002 | 0 | 2 | 0.0 | 1.0 | -7.55 | -7.55 | -6.93 | -6.93 |
| other\|bbi=below_near\|bias=positive\|obv=flat | 2 | 0.002 | 0 | 1 | 0.0 | 0.5 | -2.96 | -2.96 | -3.24 | -3.24 |
| W-A\|bbi=above_extended\|bias=high_positive\|obv=flat | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 23.27 | 23.27 | 21.34 | 21.34 |
| W-A\|bbi=above_extended\|bias=positive\|obv=falling | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 10.71 | 10.71 | 16.72 | 16.72 |
| W-B\|bbi=above_extended\|bias=neutral\|obv=flat | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -0.36 | -0.36 | -1.37 | -1.37 |
| W-B\|bbi=above_extended\|bias=neutral\|obv=rising | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -0.91 | -0.91 | 0.09 | 0.09 |
| W-C\|bbi=above_extended\|bias=high_positive\|obv=rising | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 5.98 | 5.98 | 20.46 | 20.46 |
| W-C\|bbi=above\|bias=neutral\|obv=flat | 1 | 0.001 | 0 | 1 | 0.0 | 1.0 | -9.42 | -9.42 | -4.48 | -4.48 |
| W-C\|bbi=above\|bias=positive\|obv=flat | 1 | 0.001 | 0 | 0 | 0.0 | 0.0 | 3.29 | 3.29 | 1.01 | 1.01 |
| W-D\|bbi=above\|bias=positive\|obv=flat | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 5.65 | 5.65 | -13.46 | -13.46 |
| other\|bbi=above\|bias=high_positive\|obv=rising | 1 | 0.001 | 1 | 0 | 1.0 | 0.0 | 12.27 | 12.27 | 11.42 | 11.42 |

## Weak Condition + Indicator Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|upper\|normal\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 42 | 0.039 | 6 | 22 | 0.143 | 0.524 | -0.35 | -1.76 | 0.9 | -0.93 |
| B2\|trend_start\|upper\|expanding\|rising\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 39 | 0.036 | 6 | 22 | 0.154 | 0.564 | -0.68 | -2.02 | -2.35 | -4.54 |
| B2\|trend_start\|upper\|normal\|low\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 26 | 0.024 | 7 | 13 | 0.269 | 0.5 | -1.54 | -0.53 | -1.62 | -2.06 |
| B2\|trend_start\|upper\|expanding\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 23 | 0.021 | 4 | 14 | 0.174 | 0.609 | -1.4 | -1.08 | 0.54 | -2.33 |
| B2\|trend_start\|near_high\|expanding\|rising\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 20 | 0.019 | 5 | 11 | 0.25 | 0.55 | 1.0 | -0.32 | -1.17 | -1.07 |
| B2\|trend_start\|upper\|normal\|neutral\|red_expanding\|price_turnover_rise\|bbi=above_extended\|bias=neutral\|obv=flat | 15 | 0.014 | 2 | 10 | 0.133 | 0.667 | -2.1 | -1.87 | -1.59 | -2.87 |
| B3\|rebound\|upper\|normal\|rising\|green_or_zero\|mixed\|bbi=above\|bias=neutral\|obv=flat | 14 | 0.013 | 0 | 9 | 0.0 | 0.643 | -3.12 | -2.27 | -5.87 | -7.59 |
| B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 13 | 0.012 | 1 | 7 | 0.077 | 0.538 | -2.51 | -3.31 | -2.29 | -1.32 |
| B2\|trend_start\|upper\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 13 | 0.012 | 2 | 8 | 0.154 | 0.615 | -1.27 | -2.96 | -3.41 | -2.23 |
| B2\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 13 | 0.012 | 3 | 5 | 0.231 | 0.385 | -0.37 | 0.36 | 2.15 | 2.54 |
| B2\|trend_start\|near_high\|normal\|rising\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 10 | 0.009 | 0 | 8 | 0.0 | 0.8 | -1.88 | -0.45 | -1.34 | -1.9 |
| B3\|rebound\|upper\|normal\|neutral\|green_or_zero\|mixed\|bbi=above\|bias=neutral\|obv=flat | 10 | 0.009 | 0 | 5 | 0.0 | 0.5 | -1.23 | -0.02 | -2.26 | -1.6 |
| B2\|trend_start\|near_high\|expanding\|neutral\|red_expanding\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 9 | 0.008 | 1 | 5 | 0.111 | 0.556 | -3.57 | -4.61 | -4.97 | -7.03 |
| B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise\|bbi=above_extended\|bias=high_positive\|obv=flat | 9 | 0.008 | 3 | 4 | 0.333 | 0.444 | 6.0 | 1.43 | 3.82 | -3.32 |
| B2\|trend_start\|near_high\|normal\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 9 | 0.008 | 0 | 3 | 0.0 | 0.333 | -0.8 | 0.86 | -1.24 | 0.39 |
| B2\|trend_start\|upper\|expanding\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 9 | 0.008 | 2 | 4 | 0.222 | 0.444 | 1.81 | 0.58 | -0.01 | 0.61 |
| B2\|trend_start\|upper\|normal\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=neutral\|obv=flat | 9 | 0.008 | 1 | 5 | 0.111 | 0.556 | -4.45 | -3.53 | -2.57 | -2.42 |
| B3\|rebound\|near_high\|normal\|rising\|red_expanding\|mixed\|bbi=above_extended\|bias=positive\|obv=flat | 9 | 0.008 | 2 | 6 | 0.222 | 0.667 | -2.02 | -3.41 | -1.97 | -1.09 |
| B2\|trend_start\|near_high\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 8 | 0.007 | 0 | 3 | 0.0 | 0.375 | 0.27 | 0.86 | -0.77 | -0.77 |
| B3\|rebound\|upper\|normal\|rising\|green_or_zero\|mixed\|bbi=above\|bias=positive\|obv=flat | 8 | 0.007 | 1 | 5 | 0.125 | 0.625 | -3.84 | -3.82 | -5.34 | -5.2 |
| B2\|trend_start\|extended_or_unknown\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 7 | 0.007 | 0 | 4 | 0.0 | 0.571 | -4.31 | -4.01 | -7.12 | -11.0 |
| B2\|trend_start\|near_high\|expanding\|rising\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=high_positive\|obv=flat | 7 | 0.007 | 1 | 3 | 0.143 | 0.429 | 0.07 | 0.16 | -0.15 | -2.82 |
| B2\|trend_start\|upper\|expanding\|rising\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 7 | 0.007 | 0 | 6 | 0.0 | 0.857 | -5.05 | -5.0 | -7.44 | -8.61 |
| B2\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=positive\|obv=flat | 7 | 0.007 | 2 | 2 | 0.286 | 0.286 | 3.38 | 2.01 | 1.88 | 2.17 |
| B2\|rebound\|middle\|expanding\|rising\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 6 | 0.006 | 0 | 3 | 0.0 | 0.5 | -1.33 | -0.21 | -1.94 | -1.59 |
| B2\|trend_start\|extended_or_unknown\|normal\|low\|green_or_zero\|price_turnover_rise\|bbi=below_near\|bias=neutral\|obv=flat | 6 | 0.006 | 2 | 3 | 0.333 | 0.5 | 0.06 | -0.34 | 1.52 | 2.12 |
| B2\|trend_start\|upper\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 6 | 0.006 | 1 | 2 | 0.167 | 0.333 | -0.63 | 0.18 | -4.13 | -4.83 |
| B2\|trend_start\|upper\|expanding\|rising\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=high_positive\|obv=flat | 6 | 0.006 | 1 | 3 | 0.167 | 0.5 | 5.19 | 1.15 | 0.29 | 1.62 |
| B2\|trend_start\|upper\|normal\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 6 | 0.006 | 1 | 4 | 0.167 | 0.667 | -0.35 | -4.02 | -1.24 | -2.23 |
| B2\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 6 | 0.006 | 1 | 4 | 0.167 | 0.667 | -5.39 | -6.65 | -7.25 | -5.72 |
| B3\|rebound\|extended_or_unknown\|normal\|repair_from_low\|green_or_zero\|mixed\|bbi=below_near\|bias=neutral\|obv=flat | 6 | 0.006 | 0 | 5 | 0.0 | 0.833 | -2.36 | -1.8 | -4.77 | -4.12 |
| B3\|rebound\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not\|bbi=above_extended\|bias=positive\|obv=flat | 6 | 0.006 | 2 | 1 | 0.333 | 0.167 | 2.76 | 3.4 | 0.95 | -3.54 |
| B3\|rebound\|upper\|shrinking\|neutral\|green_or_zero\|mixed\|bbi=above\|bias=neutral\|obv=flat | 6 | 0.006 | 1 | 1 | 0.167 | 0.167 | 1.74 | 1.59 | -2.4 | -1.04 |
| B3\|trend_start\|upper\|normal\|rising\|red_expanding\|price_up_turnover_not\|bbi=above_extended\|bias=positive\|obv=flat | 6 | 0.006 | 2 | 1 | 0.333 | 0.167 | 2.18 | 2.58 | -0.12 | 0.68 |
| B2\|rebound\|extended_or_unknown\|normal\|neutral\|green_or_zero\|price_turnover_rise\|bbi=below_near\|bias=neutral\|obv=flat | 5 | 0.005 | 0 | 5 | 0.0 | 1.0 | -5.38 | -4.36 | -3.43 | -3.66 |
| B2\|rebound\|extended_or_unknown\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise\|bbi=below_near\|bias=neutral\|obv=flat | 5 | 0.005 | 0 | 3 | 0.0 | 0.6 | -2.32 | 0.0 | -1.49 | -1.54 |
| B2\|rebound\|middle\|normal\|low\|green_or_zero\|price_turnover_rise\|bbi=below_near\|bias=neutral\|obv=flat | 5 | 0.005 | 0 | 4 | 0.0 | 0.8 | -10.08 | -7.86 | -11.18 | -7.2 |
| B2\|trend_start\|near_high\|expanding\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above\|bias=neutral\|obv=flat | 5 | 0.005 | 1 | 2 | 0.2 | 0.4 | -0.3 | 0.05 | -1.04 | 0.0 |
| B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise\|bbi=above_extended\|bias=high_positive\|obv=rising | 5 | 0.005 | 1 | 2 | 0.2 | 0.4 | -0.55 | 3.06 | 2.25 | 2.78 |
| B2\|trend_start\|near_high\|normal\|neutral\|green_or_zero\|price_turnover_rise\|bbi=above_extended\|bias=positive\|obv=flat | 5 | 0.005 | 0 | 2 | 0.0 | 0.4 | 0.88 | 1.02 | 5.88 | 3.07 |
