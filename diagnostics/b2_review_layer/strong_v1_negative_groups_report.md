# Strong V1 Negative Groups Report

- scope: env=strong, verdict in PASS/WATCH, daily strong_v1_rank topN negative samples
- diagnosis: Compares strong_v1 ranked losers with the offline factor/MACD reports so recurring negative groups can be turned into ranking penalties or veto conditions before changing production review verdicts.

## Daily Strong V1 Top3 Negatives

- selected_samples: 60
- ret3>=5 samples: 21
- ret3<=0 samples: 27
- negative_ret3_mean: -5.22
- negative_ret3_median: -4.01

### Family Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| other | 19 | 0.704 | 0 | 19 | 0.0 | 1.0 | -3.54 | -3.69 | -2.85 | -2.97 |
| S-A | 3 | 0.111 | 0 | 3 | 0.0 | 1.0 | -10.28 | -7.85 | -12.63 | -11.03 |
| S-B | 3 | 0.111 | 0 | 3 | 0.0 | 1.0 | -7.72 | -6.1 | -2.06 | -0.39 |
| S-C | 2 | 0.074 | 0 | 2 | 0.0 | 1.0 | -9.88 | -9.88 | -9.31 | -9.31 |

### Factor Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 4 | 0.148 | 0 | 4 | 0.0 | 1.0 | -1.91 | -2.02 | 2.45 | 0.36 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 3 | 0.111 | 0 | 3 | 0.0 | 1.0 | -4.22 | -4.01 | -4.85 | -4.79 |
| strong\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.111 | 0 | 3 | 0.0 | 1.0 | -4.13 | -3.69 | -5.79 | -8.79 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 2 | 0.074 | 0 | 2 | 0.0 | 1.0 | -11.5 | -11.5 | -13.43 | -13.43 |
| strong\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.074 | 0 | 2 | 0.0 | 1.0 | -4.1 | -4.1 | -6.44 | -6.44 |
| strong\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.074 | 0 | 2 | 0.0 | 1.0 | -1.59 | -1.59 | 3.8 | 3.8 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -5.04 | -5.04 | -6.63 | -6.63 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.1 | -6.1 | 1.89 | 1.89 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -11.61 | -11.61 | -7.68 | -7.68 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -14.73 | -14.73 | -11.99 | -11.99 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -7.85 | -7.85 | -11.03 | -11.03 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -4.39 | -4.39 | -7.03 | -7.03 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -5.44 | -5.44 | -0.39 | -0.39 |
| strong\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.12 | -6.12 | 0.02 | 0.02 |
| strong\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -0.44 | -0.44 | -1.08 | -1.08 |
| strong\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -3.93 | -3.93 | 2.23 | 2.23 |
| strong\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -8.28 | -8.28 | -20.87 | -20.87 |

### B3/Condition Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising | 7 | 0.259 | 0 | 7 | 0.0 | 1.0 | -2.9 | -2.63 | -0.68 | -2.97 |
| red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising | 3 | 0.111 | 0 | 3 | 0.0 | 1.0 | -4.13 | -3.69 | -5.79 | -8.79 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral | 2 | 0.074 | 0 | 2 | 0.0 | 1.0 | -11.5 | -11.5 | -13.43 | -13.43 |
| red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=normal\|kdj=rising | 2 | 0.074 | 0 | 2 | 0.0 | 1.0 | -4.1 | -4.1 | -6.44 | -6.44 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -5.04 | -5.04 | -6.63 | -6.63 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -14.73 | -14.73 | -11.99 | -11.99 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=repair_from_low | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -7.85 | -7.85 | -11.03 | -11.03 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=normal\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -5.44 | -5.44 | -0.39 | -0.39 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.1 | -6.1 | 1.89 | 1.89 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -11.61 | -11.61 | -7.68 | -7.68 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -4.39 | -4.39 | -7.03 | -7.03 |
| green_or_zero\|mixed\|rebound\|price=upper\|volume=normal\|kdj=repair_from_low | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -0.44 | -0.44 | -1.08 | -1.08 |
| green_or_zero\|mixed\|trend_start\|price=upper\|volume=normal\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -0.15 | -0.15 | 6.68 | 6.68 |
| red_contracting\|mixed\|rebound\|price=near_high\|volume=normal\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.12 | -6.12 | 0.02 | 0.02 |
| red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=expanding\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -3.93 | -3.93 | 2.23 | 2.23 |
| red_expanding\|price_up_turnover_not\|trend_start\|price=upper\|volume=normal\|kdj=neutral | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -8.28 | -8.28 | -20.87 | -20.87 |
| red_expanding\|price_up_turnover_not\|trend_start\|price=upper\|volume=normal\|kdj=rising | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -3.03 | -3.03 | 0.92 | 0.92 |

### MACD Wave Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:2:背离\|D:rising:2:背离 | 2 | 0.074 | 0 | 2 | 0.0 | 1.0 | -3.16 | -3.16 | -6.29 | -6.29 |
| W:falling:2:修复\|D:rising:0:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -3.03 | -3.03 | 0.92 | 0.92 |
| W:idle:0:等待启动\|D:falling:2:金叉临近 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -5.44 | -5.44 | -0.39 | -0.39 |
| W:idle:0:等待启动\|D:rising:2:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -3.69 | -3.69 | -10.04 | -10.04 |
| W:rising:0:强势\|D:rising:5:强势 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -11.61 | -11.61 | -7.68 | -7.68 |
| W:rising:0:背离\|D:rising:1:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -5.0 | -5.0 | 1.47 | 1.47 |
| W:rising:0:背离\|D:rising:2:强势 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.14 | -6.14 | -6.43 | -6.43 |
| W:rising:0:背离\|D:rising:2:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -1.42 | -1.42 | -2.97 | -2.97 |
| W:rising:0:背离\|D:rising:4:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -4.01 | -4.01 | -7.8 | -7.8 |
| W:rising:1:分歧\|D:rising:0:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.47 | -6.47 | -1.96 | -1.96 |
| W:rising:1:强势\|D:rising:11:强势 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -3.93 | -3.93 | 2.23 | 2.23 |
| W:rising:1:强势\|D:rising:2:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -3.31 | -3.31 | 3.69 | 3.69 |
| W:rising:1:背离\|D:falling:16:修复 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -7.85 | -7.85 | -11.03 | -11.03 |
| W:rising:1:背离\|D:rising:0:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -0.69 | -0.69 | -0.88 | -0.88 |
| W:rising:2:分歧\|D:rising:4:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -22.31 | -22.31 | -25.98 | -25.98 |
| W:rising:2:强势转分歧\|D:rising:6:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -2.18 | -2.18 | -4.79 | -4.79 |
| W:rising:3:分歧\|D:falling:6:修复 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -0.15 | -0.15 | 6.68 | 6.68 |
| W:rising:3:强势\|D:falling:4:金叉临近 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -14.73 | -14.73 | -11.99 | -11.99 |
| W:rising:3:强势\|D:rising:0:分歧 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.12 | -6.12 | 0.02 | 0.02 |
| W:rising:3:强势\|D:rising:2:背离 | 1 | 0.037 | 0 | 1 | 0.0 | 1.0 | -6.1 | -6.1 | 1.89 | 1.89 |

### Worst Samples

| date | rank | code | verdict | family | score | v1_score | ret3 | ret5 | signal | signal_type | condition |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| 2026-05-15 | 1 | 300651.SZ | PASS | S-A | 4.32 | 4.57 | -22.31 | -25.98 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral |
| 2026-05-20 | 2 | 300438.SZ | WATCH | S-C | 4.49 | 4.54 | -14.73 | -11.99 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=rising |
| 2026-04-23 | 2 | 603912.SH | WATCH | S-B | 4.16 | 4.21 | -11.61 | -7.68 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral |
| 2026-05-08 | 3 | 002796.SZ | WATCH | other | 4.41 | 4.61 | -8.28 | -20.87 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=upper\|volume=normal\|kdj=neutral |
| 2026-05-12 | 2 | 605098.SH | WATCH | S-A | 4.03 | 4.28 | -7.85 | -11.03 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=repair_from_low |
| 2026-04-24 | 3 | 603819.SH | WATCH | other | 4.31 | 4.31 | -6.47 | -1.96 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-05-20 | 1 | 603229.SH | PASS | other | 4.77 | 4.97 | -6.14 | -6.43 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=normal\|kdj=rising |
| 2026-04-27 | 1 | 301165.SZ | WATCH | other | 4.44 | 4.52 | -6.12 | 0.02 | B3 | rebound | red_contracting\|mixed\|rebound\|price=near_high\|volume=normal\|kdj=rising |
| 2026-04-24 | 2 | 603158.SH | WATCH | S-B | 4.29 | 4.34 | -6.1 | 1.89 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral |
| 2026-05-13 | 1 | 002042.SZ | PASS | S-B | 4.62 | 4.67 | -5.44 | -0.39 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=normal\|kdj=neutral |
| 2026-05-20 | 3 | 300568.SZ | WATCH | S-C | 4.42 | 4.42 | -5.04 | -6.63 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral |
| 2026-05-12 | 3 | 301607.SZ | PASS | other | 4.28 | 4.21 | -5.0 | 1.47 | B3 | rebound | red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising |
| 2026-05-11 | 2 | 301237.SZ | WATCH | other | 4.28 | 4.33 | -4.39 | -7.03 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=rising |
| 2026-03-02 | 3 | 688301.SH | PASS | other | 4.32 | 4.32 | -4.01 | -7.8 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-03-02 | 1 | 300448.SZ | WATCH | other | 4.25 | 4.42 | -3.93 | 2.23 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-05-14 | 2 | 603332.SH | PASS | other | 4.36 | 4.29 | -3.69 | -10.04 | B3 | rebound | red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising |
| 2026-05-19 | 3 | 688063.SH | WATCH | other | 4.47 | 4.4 | -3.69 | -8.79 | B3 | rebound | red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising |
| 2026-05-15 | 3 | 688129.SH | WATCH | other | 4.31 | 4.36 | -3.31 | 3.69 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-05-19 | 1 | 002452.SZ | PASS | other | 4.64 | 4.84 | -3.03 | 0.92 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=upper\|volume=normal\|kdj=rising |
| 2026-05-13 | 3 | 601138.SH | WATCH | other | 4.32 | 4.37 | -2.63 | -3.8 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-04-22 | 3 | 301191.SZ | WATCH | other | 4.27 | 4.27 | -2.18 | -4.79 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-05-11 | 1 | 003027.SZ | WATCH | other | 4.28 | 4.48 | -2.07 | -6.44 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=normal\|kdj=rising |
| 2026-05-15 | 2 | 603390.SH | WATCH | other | 4.32 | 4.37 | -1.42 | -2.97 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-04-27 | 2 | 301031.SZ | WATCH | S-A | 4.18 | 4.43 | -0.69 | -0.88 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral |
| 2026-04-22 | 1 | 600389.SH | PASS | other | 4.22 | 4.3 | -0.44 | -1.08 | B3 | rebound | green_or_zero\|mixed\|rebound\|price=upper\|volume=normal\|kdj=repair_from_low |
| 2026-04-21 | 2 | 300931.SZ | WATCH | other | 4.18 | 4.23 | -0.29 | 12.87 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-04-20 | 3 | 301338.SZ | WATCH | other | 4.11 | 4.19 | -0.15 | 6.68 | B3 | trend_start | green_or_zero\|mixed\|trend_start\|price=upper\|volume=normal\|kdj=rising |

## Daily Strong V1 Top5 Negatives

- selected_samples: 100
- ret3>=5 samples: 31
- ret3<=0 samples: 51
- negative_ret3_mean: -4.94
- negative_ret3_median: -4.35

### Family Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| other | 36 | 0.706 | 0 | 36 | 0.0 | 1.0 | -3.8 | -3.6 | -3.86 | -4.29 |
| S-B | 7 | 0.137 | 0 | 7 | 0.0 | 1.0 | -6.5 | -5.79 | -3.77 | -3.89 |
| S-A | 6 | 0.118 | 0 | 6 | 0.0 | 1.0 | -8.3 | -6.26 | -10.63 | -12.19 |
| S-C | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -9.88 | -9.88 | -9.31 | -9.31 |

### Factor Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 6 | 0.118 | 0 | 6 | 0.0 | 1.0 | -2.62 | -2.97 | -1.71 | -3.38 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 4 | 0.078 | 0 | 4 | 0.0 | 1.0 | -3.8 | -3.27 | -3.77 | -3.38 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 4 | 0.078 | 0 | 4 | 0.0 | 1.0 | -10.1 | -8.69 | -13.72 | -14.01 |
| strong\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 4 | 0.078 | 0 | 4 | 0.0 | 1.0 | -3.65 | -3.69 | -4.58 | -4.88 |
| strong\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 4 | 0.078 | 0 | 4 | 0.0 | 1.0 | -4.27 | -4.44 | -8.14 | -6.44 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 3 | 0.059 | 0 | 3 | 0.0 | 1.0 | -8.49 | -8.06 | -5.11 | -7.68 |
| strong\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 3 | 0.059 | 0 | 3 | 0.0 | 1.0 | -6.4 | -7.41 | -11.19 | -10.59 |
| strong\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.059 | 0 | 3 | 0.0 | 1.0 | -1.56 | -1.49 | 2.06 | 0.92 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -4.5 | -4.5 | -3.39 | -3.39 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.55 | -3.55 | -6.22 | -6.22 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -5.53 | -5.53 | -2.14 | -2.14 |
| strong\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.88 | -3.88 | 1.09 | 1.09 |
| strong\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.71 | -3.71 | -7.79 | -7.79 |
| strong\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.68 | -3.68 | -2.08 | -2.08 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -5.04 | -5.04 | -6.63 | -6.63 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -9.0 | -9.0 | 1.01 | 1.01 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -14.73 | -14.73 | -11.99 | -11.99 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=low | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -1.6 | -1.6 | 2.14 | 2.14 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -7.85 | -7.85 | -11.03 | -11.03 |
| strong\|B2\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -6.44 | -6.44 | -4.83 | -4.83 |

### B3/Condition Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising | 10 | 0.196 | 0 | 10 | 0.0 | 1.0 | -3.09 | -2.97 | -2.53 | -3.38 |
| red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising | 4 | 0.078 | 0 | 4 | 0.0 | 1.0 | -3.65 | -3.69 | -4.58 | -4.88 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral | 3 | 0.059 | 0 | 3 | 0.0 | 1.0 | -8.8 | -9.0 | -1.21 | 1.01 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral | 3 | 0.059 | 0 | 3 | 0.0 | 1.0 | -9.22 | -4.67 | -13.4 | -13.35 |
| red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=normal\|kdj=rising | 3 | 0.059 | 0 | 3 | 0.0 | 1.0 | -4.19 | -4.35 | -6.16 | -6.43 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.96 | -3.96 | -7.64 | -7.64 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -9.58 | -9.58 | -9.75 | -9.75 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=normal\|kdj=neutral | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -5.53 | -5.53 | -2.14 | -2.14 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=rising | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.55 | -3.55 | -6.22 | -6.22 |
| green_or_zero\|mixed\|rebound\|price=upper\|volume=normal\|kdj=repair_from_low | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.71 | -3.71 | -7.79 | -7.79 |
| red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=expanding\|kdj=rising | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.68 | -3.68 | -2.08 | -2.08 |
| red_expanding\|price_up_turnover_not\|trend_start\|price=upper\|volume=normal\|kdj=rising | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -2.26 | -2.26 | -0.24 | -0.24 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -8.06 | -8.06 | -10.7 | -10.7 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=rising | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -14.73 | -14.73 | -11.99 | -11.99 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=low | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -1.6 | -1.6 | 2.14 | 2.14 |
| NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=repair_from_low | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -7.85 | -7.85 | -11.03 | -11.03 |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -6.1 | -6.1 | 1.89 | 1.89 |
| green_or_zero\|mixed\|trend_start\|price=near_high\|volume=shrinking\|kdj=rising | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -4.98 | -4.98 | -6.41 | -6.41 |
| green_or_zero\|mixed\|trend_start\|price=upper\|volume=normal\|kdj=neutral | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -3.52 | -3.52 | -2.12 | -2.12 |
| green_or_zero\|mixed\|trend_start\|price=upper\|volume=normal\|kdj=rising | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -0.15 | -0.15 | 6.68 | 6.68 |

### MACD Wave Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:0:背离\|D:rising:0:背离 | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -4.54 | -4.54 | -12.28 | -12.28 |
| W:rising:2:背离\|D:rising:2:背离 | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -3.16 | -3.16 | -6.29 | -6.29 |
| W:rising:3:背离\|D:rising:2:背离 | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -0.89 | -0.89 | 5.73 | 5.73 |
| W:rising:4:背离\|D:rising:0:背离 | 2 | 0.039 | 0 | 2 | 0.0 | 1.0 | -4.37 | -4.37 | -6.32 | -6.32 |
| W:falling:2:修复\|D:rising:0:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -3.03 | -3.03 | 0.92 | 0.92 |
| W:falling:2:背离\|D:rising:2:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -2.71 | -2.71 | -5.41 | -5.41 |
| W:idle:0:等待启动\|D:falling:2:金叉临近 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -5.44 | -5.44 | -0.39 | -0.39 |
| W:idle:0:等待启动\|D:rising:0:强势 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -0.31 | -0.31 | 4.75 | 4.75 |
| W:idle:0:等待启动\|D:rising:2:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -3.69 | -3.69 | -10.04 | -10.04 |
| W:rising:0:强势\|D:rising:5:强势 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -11.61 | -11.61 | -7.68 | -7.68 |
| W:rising:0:强势转分歧\|D:falling:6:修复 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -4.98 | -4.98 | -6.41 | -6.41 |
| W:rising:0:背离\|D:falling:6:金叉临近 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -7.41 | -7.41 | -10.59 | -10.59 |
| W:rising:0:背离\|D:rising:1:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -5.0 | -5.0 | 1.47 | 1.47 |
| W:rising:0:背离\|D:rising:2:强势 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -6.14 | -6.14 | -6.43 | -6.43 |
| W:rising:0:背离\|D:rising:2:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -1.42 | -1.42 | -2.97 | -2.97 |
| W:rising:0:背离\|D:rising:4:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -4.01 | -4.01 | -7.8 | -7.8 |
| W:rising:1:分歧\|D:rising:0:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -6.47 | -6.47 | -1.96 | -1.96 |
| W:rising:1:强势\|D:rising:0:强势 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -5.79 | -5.79 | 3.05 | 3.05 |
| W:rising:1:强势\|D:rising:11:强势 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -3.93 | -3.93 | 2.23 | 2.23 |
| W:rising:1:强势\|D:rising:2:背离 | 1 | 0.02 | 0 | 1 | 0.0 | 1.0 | -3.31 | -3.31 | 3.69 | 3.69 |

### Worst Samples

| date | rank | code | verdict | family | score | v1_score | ret3 | ret5 | signal | signal_type | condition |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| 2026-05-15 | 1 | 300651.SZ | PASS | S-A | 4.32 | 4.57 | -22.31 | -25.98 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral |
| 2026-05-20 | 2 | 300438.SZ | WATCH | S-C | 4.49 | 4.54 | -14.73 | -11.99 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=rising |
| 2026-05-14 | 4 | 603016.SH | WATCH | S-A | 3.96 | 4.21 | -12.71 | -14.67 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral |
| 2026-04-23 | 2 | 603912.SH | WATCH | S-B | 4.16 | 4.21 | -11.61 | -7.68 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral |
| 2026-04-24 | 4 | 301165.SZ | WATCH | other | 4.29 | 4.29 | -9.0 | 1.01 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral |
| 2026-05-08 | 3 | 002796.SZ | WATCH | other | 4.41 | 4.61 | -8.28 | -20.87 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=upper\|volume=normal\|kdj=neutral |
| 2026-04-22 | 4 | 301312.SZ | WATCH | S-B | 4.17 | 4.22 | -8.06 | -10.7 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral |
| 2026-05-12 | 2 | 605098.SH | WATCH | S-A | 4.03 | 4.28 | -7.85 | -11.03 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=repair_from_low |
| 2026-05-07 | 4 | 600590.SH | PASS | other | 4.59 | 4.67 | -7.41 | -10.59 | B3 | trend_start | green_or_zero\|price_up_turnover_not\|trend_start\|price=upper\|volume=normal\|kdj=neutral |
| 2026-05-15 | 4 | 300804.SZ | PASS | other | 4.21 | 4.29 | -6.98 | -14.5 | B3 | rebound | green_or_zero\|mixed\|rebound\|price=upper\|volume=normal\|kdj=repair_from_low |
| 2026-04-24 | 3 | 603819.SH | WATCH | other | 4.31 | 4.31 | -6.47 | -1.96 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-04-23 | 5 | 000019.SZ | WATCH | other | 4.1 | 4.1 | -6.44 | -4.83 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral |
| 2026-05-20 | 1 | 603229.SH | PASS | other | 4.77 | 4.97 | -6.14 | -6.43 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=normal\|kdj=rising |
| 2026-04-27 | 1 | 301165.SZ | WATCH | other | 4.44 | 4.52 | -6.12 | 0.02 | B3 | rebound | red_contracting\|mixed\|rebound\|price=near_high\|volume=normal\|kdj=rising |
| 2026-04-24 | 2 | 603158.SH | WATCH | S-B | 4.29 | 4.34 | -6.1 | 1.89 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral |
| 2026-05-13 | 4 | 001313.SZ | WATCH | S-B | 4.31 | 4.36 | -5.79 | 3.05 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=normal\|kdj=neutral |
| 2026-04-23 | 4 | 300055.SZ | WATCH | S-B | 4.08 | 4.13 | -5.62 | -3.89 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=normal\|kdj=neutral |
| 2026-05-13 | 1 | 002042.SZ | PASS | S-B | 4.62 | 4.67 | -5.44 | -0.39 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=upper\|volume=normal\|kdj=neutral |
| 2026-05-20 | 3 | 300568.SZ | WATCH | S-C | 4.42 | 4.42 | -5.04 | -6.63 | B2 | trend_start | NONB3=B2\|green_or_zero\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=neutral |
| 2026-05-12 | 3 | 301607.SZ | PASS | other | 4.28 | 4.21 | -5.0 | 1.47 | B3 | rebound | red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising |
| 2026-03-02 | 4 | 600754.SH | WATCH | other | 4.16 | 4.21 | -4.98 | -6.41 | B3 | trend_start | green_or_zero\|mixed\|trend_start\|price=near_high\|volume=shrinking\|kdj=rising |
| 2026-05-19 | 5 | 301252.SZ | WATCH | S-A | 4.08 | 4.33 | -4.67 | -13.35 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=neutral |
| 2026-05-19 | 4 | 300547.SZ | WATCH | other | 4.32 | 4.37 | -4.55 | -10.48 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-05-20 | 4 | 300547.SZ | WATCH | other | 4.27 | 4.35 | -4.53 | -14.08 | B3 | trend_start | red_expanding\|mixed\|trend_start\|price=near_high\|volume=normal\|kdj=rising |
| 2026-05-11 | 2 | 301237.SZ | WATCH | other | 4.28 | 4.33 | -4.39 | -7.03 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=upper\|volume=expanding\|kdj=rising |
| 2026-05-07 | 5 | 301125.SZ | WATCH | other | 4.41 | 4.61 | -4.35 | -5.61 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=normal\|kdj=rising |
| 2026-03-02 | 3 | 688301.SH | PASS | other | 4.32 | 4.32 | -4.01 | -7.8 | B2 | trend_start | NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-03-02 | 1 | 300448.SZ | WATCH | other | 4.25 | 4.42 | -3.93 | 2.23 | B3 | trend_start | red_expanding\|price_up_turnover_not\|trend_start\|price=near_high\|volume=expanding\|kdj=rising |
| 2026-05-14 | 2 | 603332.SH | PASS | other | 4.36 | 4.29 | -3.69 | -10.04 | B3 | rebound | red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising |
| 2026-05-19 | 3 | 688063.SH | WATCH | other | 4.47 | 4.4 | -3.69 | -8.79 | B3 | rebound | red_expanding\|mixed\|rebound\|price=upper\|volume=normal\|kdj=rising |
