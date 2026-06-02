# Strong PASS Composition Report

- scope: env=strong and verdict=PASS
- sample_count: 46
- ret3>=5: 12
- ret3<=0: 16
- positive_rate: 0.261
- negative_rate: 0.348
- ret3_mean: 1.81
- ret3_median: 1.25
- ret5_mean: 2.58
- ret5_median: 1.71

- diagnosis: Current strong PASS is mostly not S-A; it is dominated by B3/B3+ structures. S-A is a high-quality strong WATCH family and should not be treated as the current PASS basis.

## Indicator Hit Rates

| indicator | hit_rate |
| --- | ---: |
| b2_trend_start | 0.217 |
| bull_stack | 1.0 |
| kdj_constructive | 0.304 |
| macd_weekly_push_daily_repair | 0.326 |
| midline_above_hold | 0.978 |
| price_upper_or_near_high | 0.978 |
| tight_compression | 0.935 |
| volume_confirm | 0.152 |

## Family Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| other | 39 | 0.848 | 10 | 14 | 0.256 | 0.359 | 1.97 | 1.21 | 2.19 | 1.47 |
| S-A | 3 | 0.065 | 1 | 1 | 0.333 | 0.333 | -5.05 | 1.26 | -5.98 | -0.21 |
| S-B | 2 | 0.043 | 1 | 1 | 0.5 | 0.5 | 7.17 | 7.17 | 21.01 | 21.01 |
| S-C | 2 | 0.043 | 0 | 0 | 0.0 | 0.0 | 3.67 | 3.67 | 4.54 | 4.54 |

## Signal Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B3\|trend_start | 20 | 0.435 | 5 | 6 | 0.25 | 0.3 | 2.24 | 1.22 | 2.25 | 1.64 |
| B3\|rebound | 15 | 0.326 | 3 | 7 | 0.2 | 0.467 | 0.87 | 0.32 | 2.04 | 1.47 |
| B2\|trend_start | 10 | 0.217 | 3 | 3 | 0.3 | 0.3 | 1.05 | 2.92 | 2.7 | 0.93 |
| B3+\|trend_start | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 14.95 | 14.95 | 15.93 | 15.93 |

## Top Factor Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 9 | 0.196 | 3 | 2 | 0.333 | 0.222 | 4.94 | 1.23 | 6.44 | 1.94 |
| strong\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 6 | 0.13 | 1 | 2 | 0.167 | 0.333 | 1.45 | 0.69 | -0.64 | 0.39 |
| strong\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 5 | 0.109 | 1 | 2 | 0.2 | 0.4 | 0.16 | 0.42 | 0.62 | 3.05 |
| strong\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 4 | 0.087 | 0 | 3 | 0.0 | 0.75 | -2.78 | -4.0 | 2.99 | 3.29 |
| strong\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 4 | 0.087 | 1 | 2 | 0.25 | 0.5 | -1.25 | -1.37 | -6.89 | -6.23 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 2 | 0.043 | 1 | 1 | 0.5 | 0.5 | 0.75 | 0.75 | -0.68 | -0.68 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 2 | 0.043 | 0 | 1 | 0.0 | 0.5 | -10.52 | -10.52 | -13.1 | -13.1 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.043 | 1 | 1 | 0.5 | 0.5 | 7.17 | 7.17 | 21.01 | 21.01 |
| strong\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 2 | 0.043 | 0 | 2 | 0.0 | 1.0 | -3.71 | -3.71 | -7.79 | -7.79 |
| strong\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=rising | 2 | 0.043 | 0 | 0 | 0.0 | 0.0 | 2.27 | 2.27 | 5.81 | 5.81 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 3.93 | 3.93 | 2.06 | 2.06 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 3.41 | 3.41 | 7.01 | 7.01 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 5.9 | 5.9 | 8.26 | 8.26 |
| strong\|B2\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 2.42 | 2.42 | -4.84 | -4.84 |
| strong\|B3+\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=repair_from_low | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 14.95 | 14.95 | 15.93 | 15.93 |
| strong\|B3\|rebound\|price=middle\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 6.29 | 6.29 | 16.18 | 16.18 |
| strong\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=rising | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 2.88 | 2.88 | -3.45 | -3.45 |
| strong\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 13.68 | 13.68 | 25.32 | 25.32 |

## Top MACD Wave Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W:idle:0:等待启动\|D:falling:2:金叉临近 | 2 | 0.043 | 0 | 1 | 0.0 | 0.5 | -1.51 | -1.51 | -2.61 | -2.61 |
| W:idle:0:等待启动\|D:rising:2:背离 | 2 | 0.043 | 1 | 1 | 0.5 | 0.5 | 1.4 | 1.4 | -3.68 | -3.68 |
| W:rising:2:分歧\|D:rising:4:背离 | 2 | 0.043 | 1 | 1 | 0.5 | 0.5 | -6.28 | -6.28 | -8.71 | -8.71 |
| W:rising:3:背离\|D:falling:6:修复 | 2 | 0.043 | 0 | 1 | 0.0 | 0.5 | -0.75 | -0.75 | 2.43 | 2.43 |
| W:rising:3:背离\|D:rising:0:背离 | 2 | 0.043 | 1 | 0 | 0.5 | 0.0 | 6.25 | 6.25 | 0.69 | 0.69 |
| W:falling:2:修复\|D:falling:2:修复 | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 5.15 | 5.15 | 2.23 | 2.23 |
| W:falling:2:修复\|D:rising:0:背离 | 1 | 0.022 | 0 | 1 | 0.0 | 1.0 | -3.03 | -3.03 | 0.92 | 0.92 |
| W:falling:2:修复\|D:rising:2:背离 | 1 | 0.022 | 0 | 1 | 0.0 | 1.0 | -1.69 | -1.69 | 0.9 | 0.9 |
| W:falling:4:修复\|D:rising:1:分歧 | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 3.7 | 3.7 | -1.88 | -1.88 |
| W:falling:4:背离\|D:rising:0:背离 | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 1.21 | 1.21 | 1.94 | 1.94 |
| W:rising:0:分歧\|D:falling:2:修复 | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 1.41 | 1.41 | 3.05 | 3.05 |
| W:rising:0:背离\|D:falling:6:金叉临近 | 1 | 0.022 | 0 | 1 | 0.0 | 1.0 | -7.41 | -7.41 | -10.59 | -10.59 |
| W:rising:0:背离\|D:rising:1:背离 | 1 | 0.022 | 0 | 1 | 0.0 | 1.0 | -5.0 | -5.0 | 1.47 | 1.47 |
| W:rising:0:背离\|D:rising:2:强势 | 1 | 0.022 | 0 | 1 | 0.0 | 1.0 | -6.14 | -6.14 | -6.43 | -6.43 |
| W:rising:0:背离\|D:rising:4:背离 | 1 | 0.022 | 0 | 1 | 0.0 | 1.0 | -4.01 | -4.01 | -7.8 | -7.8 |
| W:rising:1:分歧\|D:falling:4:修复 | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 14.95 | 14.95 | 15.93 | 15.93 |
| W:rising:1:分歧\|D:falling:6:金叉临近 | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 3.41 | 3.41 | 7.01 | 7.01 |
| W:rising:1:分歧\|D:rising:6:背离 | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 0.71 | 0.71 | 0.35 | 0.35 |
| W:rising:1:强势\|D:rising:1:背离 | 1 | 0.022 | 1 | 0 | 1.0 | 0.0 | 24.68 | 24.68 | 18.87 | 18.87 |
| W:rising:1:背离\|D:falling:10:修复 | 1 | 0.022 | 0 | 0 | 0.0 | 0.0 | 0.42 | 0.42 | 5.44 | 5.44 |

## Typical PASS Samples

| date | code | family | verdict | score | ret3 | ret5 | signal | signal_type |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 2026-05-08 | 300292.SZ | other | PASS | 4.27 | 24.68 | 18.87 | B3 | trend_start |
| 2026-05-06 | 603938.SH | S-B | PASS | 4.32 | 19.79 | 42.41 | B2 | trend_start |
| 2026-04-28 | 603557.SH | other | PASS | 4.22 | 14.95 | 15.93 | B3+ | trend_start |
| 2026-04-28 | 603580.SH | other | PASS | 4.25 | 13.68 | 25.32 | B3 | rebound |
| 2026-05-07 | 000791.SZ | other | PASS | 4.64 | 12.18 | 10.46 | B3 | trend_start |
| 2026-05-08 | 603838.SH | other | PASS | 4.77 | 9.74 | 8.57 | B3 | trend_start |
| 2026-05-12 | 300866.SZ | other | PASS | 4.16 | 6.49 | 2.67 | B3 | rebound |
| 2026-04-29 | 600236.SH | other | PASS | 4.02 | 6.29 | 16.18 | B3 | rebound |
| 2026-04-28 | 300672.SZ | other | PASS | 4.54 | 6.15 | 19.87 | B3 | trend_start |
| 2026-05-07 | 002962.SZ | S-A | PASS | 4.7 | 5.9 | 8.26 | B2 | trend_start |
| 2026-04-30 | 000042.SZ | other | PASS | 4.32 | 5.5 | 6.44 | B2 | trend_start |
| 2026-05-07 | 300684.SZ | other | PASS | 4.32 | 5.15 | 2.23 | B3 | trend_start |
| 2026-05-06 | 000420.SZ | S-C | PASS | 4.49 | 3.93 | 2.06 | B2 | trend_start |
| 2026-04-21 | 600869.SH | other | PASS | 4.64 | 3.84 | 11.27 | B3 | trend_start |
| 2026-05-07 | 301165.SZ | other | PASS | 4.34 | 3.73 | -1.39 | B3 | rebound |
| 2026-05-19 | 603626.SH | other | PASS | 4.23 | 3.7 | -1.88 | B3 | trend_start |
| 2026-05-06 | 603912.SH | S-C | PASS | 4.39 | 3.41 | 7.01 | B2 | trend_start |
| 2026-05-19 | 301393.SZ | other | PASS | 4.25 | 2.88 | -3.45 | B3 | rebound |
| 2026-05-07 | 600268.SH | other | PASS | 4.3 | 2.8 | -0.25 | B3 | trend_start |
| 2026-05-13 | 603788.SH | other | PASS | 4.42 | 2.42 | -4.84 | B2 | trend_start |
| 2026-04-22 | 300931.SZ | other | PASS | 4.34 | 1.86 | 15.4 | B3 | rebound |
| 2026-05-06 | 605016.SH | other | PASS | 4.64 | 1.41 | 3.05 | B3 | trend_start |
| 2026-05-06 | 300099.SZ | S-A | PASS | 4.73 | 1.26 | -0.21 | B2 | trend_start |
| 2026-04-29 | 301081.SZ | other | PASS | 4.3 | 1.23 | 3.88 | B3 | trend_start |
| 2026-05-07 | 002126.SZ | other | PASS | 4.66 | 1.21 | 1.94 | B3 | trend_start |
| 2026-03-02 | 002826.SZ | other | PASS | 4.44 | 1.05 | 5.75 | B3 | rebound |
| 2026-04-30 | 688638.SH | other | PASS | 4.11 | 0.96 | 1.33 | B3 | trend_start |
| 2026-05-07 | 603912.SH | other | PASS | 4.24 | 0.71 | 0.35 | B3 | trend_start |
| 2026-04-30 | 605117.SH | other | PASS | 4.01 | 0.42 | 5.44 | B3 | trend_start |
| 2026-05-20 | 002678.SZ | other | PASS | 4.34 | 0.32 | -9.09 | B3 | rebound |
