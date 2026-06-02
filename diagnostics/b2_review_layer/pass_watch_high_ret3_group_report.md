# PASS/WATCH High Ret3 Group Report

- scope: PASS+WATCH ret3>=5 group statistics and daily best priority groups
- diagnosis: Use skeleton groups to decide offline rank priority for daily榜首. Full factor groups are too sparse; production changes should wait until a priority group improves daily top1 without broad PASS expansion.

## strong

- sample_count: 894
- high_ret3_count: 277
- high_ret3_days: 20
- daily_best_day_count: 20
- daily_best_ret3_mean: 27.13
- daily_best_ret3_median: 25.77

### Priority Skeleton Groups

| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.65 | 13 | 30.66 | 33.55 | 34.82 | 28.23 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 0.1 | 2 | 24.21 | 24.21 | 23.09 | 23.09 |
| B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.1 | 2 | 17.83 | 17.83 | 17.86 | 17.86 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | 0.1 | 2 | 15.92 | 15.92 | 25.3 | 25.3 |

### Daily Best Skeleton Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 13 | 0.65 | 30.66 | 33.55 | 34.82 | 28.23 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | 2 | 0.1 | 15.92 | 15.92 | 25.3 | 25.3 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 2 | 0.1 | 24.21 | 24.21 | 23.09 | 23.09 |
| B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 2 | 0.1 | 17.83 | 17.83 | 17.86 | 17.86 |
| B2\|rebound\|price=upper_or_near_high\|midline=below_midline\|support=bull_stack | 1 | 0.05 | 28.03 | 28.03 | 32.26 | 32.26 |

### Daily Best Full Group Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 4 | 0.2 | 24.98 | 24.07 | 30.36 | 30.98 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 4 | 0.2 | 34.46 | 39.04 | 44.95 | 36.84 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 3 | 0.15 | 30.18 | 26.85 | 25.75 | 25.7 |
| B2\|rebound\|price=upper_or_near_high\|midline=below_midline\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.05 | 28.03 | 28.03 | 32.26 | 32.26 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 1 | 0.05 | 19.57 | 19.57 | 34.45 | 34.45 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.05 | 12.27 | 12.27 | 16.15 | 16.15 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0.05 | 22.95 | 22.95 | 10.45 | 10.45 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.05 | 47.29 | 47.29 | 63.78 | 63.78 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=normal\|kdj=low | 1 | 0.05 | 9.4 | 9.4 | 5.43 | 5.43 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.05 | 39.03 | 39.03 | 40.74 | 40.74 |
| B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.05 | 24.68 | 24.68 | 18.87 | 18.87 |
| B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=neutral | 1 | 0.05 | 10.98 | 10.98 | 16.84 | 16.84 |

### Daily Best MACD Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:1:强势\|D:rising:1:背离 | 2 | 0.1 | 32.61 | 32.61 | 23.68 | 23.68 |
| W:idle:0:等待启动\|D:falling:2:修复 | 1 | 0.05 | 28.03 | 28.03 | 32.26 | 32.26 |
| W:idle:0:等待启动\|D:rising:1:背离 | 1 | 0.05 | 22.95 | 22.95 | 10.45 | 10.45 |
| W:idle:0:等待启动\|D:rising:3:分歧 | 1 | 0.05 | 10.98 | 10.98 | 16.84 | 16.84 |
| W:rising:1:强势\|D:falling:2:修复 | 1 | 0.05 | 11.23 | 11.23 | 22.63 | 22.63 |
| W:rising:1:背离\|D:falling:4:修复 | 1 | 0.05 | 12.27 | 12.27 | 16.15 | 16.15 |
| W:rising:1:背离\|D:falling:4:背离 | 1 | 0.05 | 9.4 | 9.4 | 5.43 | 5.43 |
| W:rising:1:背离\|D:rising:1:背离 | 1 | 0.05 | 26.85 | 26.85 | 23.06 | 23.06 |
| W:rising:2:背离\|D:falling:2:修复 | 1 | 0.05 | 11.57 | 11.57 | 17.08 | 17.08 |
| W:rising:3:强势\|D:rising:1:背离 | 1 | 0.05 | 33.55 | 33.55 | 28.23 | 28.23 |
| W:rising:3:强势\|D:rising:2:背离 | 1 | 0.05 | 40.23 | 40.23 | 42.38 | 42.38 |
| W:rising:3:强势\|D:rising:3:分歧 | 1 | 0.05 | 44.53 | 44.53 | 45.46 | 45.46 |

### Daily Best Samples

| date | code | verdict | score | ret3 | ret5 | skeleton_group | full_group | macd |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 2026-03-02 | 920014.BJ | WATCH | 3.45 | 28.03 | 32.26 | B2\|rebound\|price=upper_or_near_high\|midline=below_midline\|support=bull_stack | B2\|rebound\|price=upper_or_near_high\|midline=below_midline\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | W:idle:0:等待启动\|D:falling:2:修复 |
| 2026-04-20 | 688268.SH | WATCH | 3.99 | 48.52 | 83.47 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:3:背离\|D:falling:4:修复 |
| 2026-04-21 | 301239.SZ | WATCH | 4.18 | 10.98 | 16.84 | B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=neutral | W:idle:0:等待启动\|D:rising:3:分歧 |
| 2026-04-22 | 300069.SZ | WATCH | 3.87 | 11.23 | 22.63 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:1:强势\|D:falling:2:修复 |
| 2026-04-23 | 688702.SH | WATCH | 4.13 | 13.22 | 27.54 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | W:rising:3:背离\|D:rising:9:背离 |
| 2026-04-24 | 300057.SZ | WATCH | 4.29 | 23.16 | 25.7 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | W:rising:5:强势\|D:rising:0:背离 |
| 2026-04-27 | 300632.SZ | WATCH | 3.9 | 39.03 | 40.74 | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:5:背离\|D:falling:2:修复 |
| 2026-04-28 | 300209.SZ | WATCH | 4.15 | 47.29 | 63.78 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | W:rising:5:强势转分歧\|D:rising:5:背离 |
| 2026-04-29 | 688400.SH | WATCH | 3.99 | 34.92 | 34.43 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | W:rising:3:背离\|D:falling:2:修复 |
| 2026-04-30 | 688069.SH | WATCH | 4.29 | 40.23 | 42.38 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | W:rising:3:强势\|D:rising:2:背离 |
| 2026-05-06 | 301319.SZ | WATCH | 4.15 | 33.55 | 28.23 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:3:强势\|D:rising:1:背离 |
| 2026-05-07 | 300292.SZ | WATCH | 4.16 | 26.85 | 23.06 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | W:rising:1:背离\|D:rising:1:背离 |
| 2026-05-08 | 300292.SZ | PASS | 4.27 | 24.68 | 18.87 | B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | W:rising:1:强势\|D:rising:1:背离 |
| 2026-05-11 | 300005.SZ | WATCH | 3.63 | 9.4 | 5.43 | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=normal\|kdj=low | W:rising:1:背离\|D:falling:4:背离 |
| 2026-05-12 | 003018.SZ | WATCH | 3.94 | 19.57 | 34.45 | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | W:rising:3:背离\|D:falling:6:背离 |
| 2026-05-13 | 688548.SH | WATCH | 4.03 | 12.27 | 16.15 | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:1:背离\|D:falling:4:修复 |
| 2026-05-14 | 300721.SZ | WATCH | 4.16 | 40.54 | 28.48 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | W:rising:1:强势\|D:rising:1:背离 |
| 2026-05-15 | 002407.SZ | WATCH | 3.63 | 11.57 | 17.08 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | W:rising:2:背离\|D:falling:2:修复 |
| 2026-05-19 | 301020.SZ | WATCH | 4.16 | 22.95 | 10.45 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | W:idle:0:等待启动\|D:rising:1:背离 |
| 2026-05-20 | 300835.SZ | WATCH | 4.08 | 44.53 | 45.46 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:3:强势\|D:rising:3:分歧 |

## weak

- sample_count: 1050
- high_ret3_count: 176
- high_ret3_days: 23
- daily_best_day_count: 23
- daily_best_ret3_mean: 23.6
- daily_best_ret3_median: 21.3

### Priority Skeleton Groups

| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.3478 | 8 | 27.49 | 31.04 | 20.32 | 9.66 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | 0.1304 | 3 | 22.43 | 18.48 | 14.3 | 13.72 |
| B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack | 0.087 | 2 | 24.82 | 24.82 | 23.19 | 23.19 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 0.087 | 2 | 14.84 | 14.84 | 5.55 | 5.55 |

### Daily Best Skeleton Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 8 | 0.348 | 27.49 | 31.04 | 20.32 | 9.66 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | 3 | 0.13 | 22.43 | 18.48 | 14.3 | 13.72 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 2 | 0.087 | 14.84 | 14.84 | 5.55 | 5.55 |
| B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack | 2 | 0.087 | 24.82 | 24.82 | 23.19 | 23.19 |
| B2\|rebound\|price=middle\|midline=above_hold\|support=close_above_ma60 | 1 | 0.043 | 15.96 | 15.96 | 10.42 | 10.42 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 1 | 0.043 | 16.52 | 16.52 | 20.65 | 20.65 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60 | 1 | 0.043 | 21.1 | 21.1 | 30.06 | 30.06 |
| B2\|trend_start\|price=middle\|midline=above_hold\|support=bull_stack | 1 | 0.043 | 40.75 | 40.75 | 23.41 | 23.41 |
| B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack | 1 | 0.043 | 13.52 | 13.52 | 3.94 | 3.94 |
| B3\|rebound\|price=extended_or_unknown\|midline=above_hold\|support=close_above_ma60 | 1 | 0.043 | 27.55 | 27.55 | 42.17 | 42.17 |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 1 | 0.043 | 23.27 | 23.27 | 21.34 | 21.34 |
| B3\|trend_start\|price=middle\|midline=below_midline\|support=bull_stack | 1 | 0.043 | 17.52 | 17.52 | 9.27 | 9.27 |

### Daily Best Full Group Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 3 | 0.13 | 23.82 | 30.85 | 19.28 | 9.1 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.087 | 26.93 | 26.93 | 20.98 | 20.98 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 2 | 0.087 | 19.96 | 19.96 | 9.66 | 9.66 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.087 | 37.74 | 37.74 | 30.54 | 30.54 |
| B2\|rebound\|price=middle\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.043 | 15.96 | 15.96 | 10.42 | 10.42 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.043 | 16.52 | 16.52 | 20.65 | 20.65 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60\|compression=normal\|volume=expanding\|kdj=low | 1 | 0.043 | 21.1 | 21.1 | 30.06 | 30.06 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 1 | 0.043 | 13.42 | 13.42 | 0.94 | 0.94 |
| B2\|trend_start\|price=middle\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=low | 1 | 0.043 | 40.75 | 40.75 | 23.41 | 23.41 |
| B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.043 | 13.52 | 13.52 | 3.94 | 3.94 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=rising | 1 | 0.043 | 33.07 | 33.07 | 13.65 | 13.65 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0.043 | 23.39 | 23.39 | 6.64 | 6.64 |

### Daily Best MACD Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:1:背离\|D:falling:4:修复 | 2 | 0.087 | 34.25 | 34.25 | 13.72 | 13.72 |
| W:rising:3:背离\|D:falling:4:修复 | 2 | 0.087 | 18.53 | 18.53 | 20.24 | 20.24 |
| W:falling:2:修复\|D:falling:2:修复 | 1 | 0.043 | 17.52 | 17.52 | 9.27 | 9.27 |
| W:falling:2:背离\|D:idle:0:等待启动 | 1 | 0.043 | 9.39 | 9.39 | 9.1 | 9.1 |
| W:rising:0:强势转分歧\|D:falling:4:修复 | 1 | 0.043 | 6.82 | 6.82 | 9.66 | 9.66 |
| W:rising:0:背离\|D:falling:2:修复 | 1 | 0.043 | 30.85 | 30.85 | 8.74 | 8.74 |
| W:rising:1:分歧\|D:falling:8:修复 | 1 | 0.043 | 54.18 | 54.18 | 55.29 | 55.29 |
| W:rising:1:背离\|D:falling:2:修复 | 1 | 0.043 | 27.55 | 27.55 | 42.17 | 42.17 |
| W:rising:1:背离\|D:rising:2:背离 | 1 | 0.043 | 31.23 | 31.23 | 40.0 | 40.0 |
| W:rising:2:强势\|D:falling:4:背离 | 1 | 0.043 | 13.52 | 13.52 | 3.94 | 3.94 |
| W:rising:2:强势\|D:rising:0:背离 | 1 | 0.043 | 16.52 | 16.52 | 20.65 | 20.65 |
| W:rising:2:强势转分歧\|D:falling:4:背离 | 1 | 0.043 | 40.75 | 40.75 | 23.41 | 23.41 |

### Daily Best Samples

| date | code | verdict | score | ret3 | ret5 | skeleton_group | full_group | macd |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 2026-03-04 | 688176.SH | WATCH | 3.6 | 29.19 | 22.53 | B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | W:rising:2:背离\|D:idle:0:等待启动 |
| 2026-03-05 | 688229.SH | WATCH | 3.66 | 40.75 | 23.41 | B2\|trend_start\|price=middle\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=middle\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=low | W:rising:2:强势转分歧\|D:falling:4:背离 |
| 2026-03-06 | 688158.SH | WATCH | 3.49 | 35.38 | 13.72 | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:1:背离\|D:falling:4:修复 |
| 2026-03-09 | 301396.SZ | WATCH | 3.67 | 31.23 | 40.0 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | W:rising:1:背离\|D:rising:2:背离 |
| 2026-03-11 | 300243.SZ | WATCH | 3.67 | 23.39 | 6.64 | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | W:rising:3:强势转分歧\|D:rising:4:背离 |
| 2026-03-12 | 600367.SH | WATCH | 3.53 | 21.3 | 5.8 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:3:强势\|D:rising:1:分歧 |
| 2026-03-13 | 300672.SZ | WATCH | 3.74 | 23.27 | 21.34 | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | W:rising:3:强势转分歧\|D:rising:4:强势 |
| 2026-03-16 | 301081.SZ | WATCH | 3.51 | 6.28 | 4.47 | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | W:rising:5:背离\|D:falling:2:修复 |
| 2026-03-18 | 300483.SZ | WATCH | 3.67 | 13.52 | 3.94 | B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack | B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:2:强势\|D:falling:4:背离 |
| 2026-03-19 | 001896.SZ | WATCH | 3.49 | 13.42 | 0.94 | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | W:rising:3:强势\|D:falling:4:背离 |
| 2026-03-20 | 002309.SZ | WATCH | 3.56 | 33.07 | 13.65 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=rising | W:rising:2:背离\|D:rising:0:背离 |
| 2026-03-23 | 000688.SZ | PASS | 3.61 | 21.1 | 30.06 | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60 | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60\|compression=normal\|volume=expanding\|kdj=low | W:rising:3:背离\|D:falling:4:修复 |
| 2026-03-24 | 000767.SZ | WATCH | 3.67 | 30.85 | 8.74 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | W:rising:0:背离\|D:falling:2:修复 |
| 2026-03-25 | 688353.SH | WATCH | 3.98 | 17.52 | 9.27 | B3\|trend_start\|price=middle\|midline=below_midline\|support=bull_stack | B3\|trend_start\|price=middle\|midline=below_midline\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | W:falling:2:修复\|D:falling:2:修复 |
| 2026-03-26 | 300461.SZ | WATCH | 3.41 | 27.55 | 42.17 | B3\|rebound\|price=extended_or_unknown\|midline=above_hold\|support=close_above_ma60 | B3\|rebound\|price=extended_or_unknown\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=shrinking\|kdj=repair_from_low | W:rising:1:背离\|D:falling:2:修复 |
| 2026-03-27 | 688331.SH | WATCH | 3.82 | 16.52 | 20.65 | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | W:rising:2:强势\|D:rising:0:背离 |
| 2026-03-30 | 600105.SH | WATCH | 3.67 | 9.39 | 9.1 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | W:falling:2:背离\|D:idle:0:等待启动 |
| 2026-03-31 | 301179.SZ | WATCH | 3.56 | 6.82 | 9.66 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | W:rising:0:强势转分歧\|D:falling:4:修复 |
| 2026-04-01 | 601975.SH | WATCH | 3.74 | 15.96 | 10.42 | B2\|rebound\|price=middle\|midline=above_hold\|support=close_above_ma60 | B2\|rebound\|price=middle\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=neutral | W:rising:3:背离\|D:falling:4:修复 |
| 2026-04-02 | 688485.SH | WATCH | 3.44 | 54.18 | 55.29 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:1:分歧\|D:falling:8:修复 |
| 2026-04-03 | 688345.SH | WATCH | 3.5 | 20.44 | 23.84 | B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | W:rising:3:强势转分歧\|D:falling:4:修复 |
| 2026-04-07 | 300209.SZ | WATCH | 3.51 | 18.48 | 28.23 | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:5:背离\|D:falling:4:修复 |
| 2026-05-27 | 000539.SZ | WATCH | 3.94 | 33.11 | None | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | W:rising:1:背离\|D:falling:4:修复 |

## neutral

- sample_count: 965
- high_ret3_count: 191
- high_ret3_days: 16
- daily_best_day_count: 16
- daily_best_ret3_mean: 20.95
- daily_best_ret3_median: 18.99

### Priority Skeleton Groups

| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.4375 | 7 | 21.98 | 18.2 | 30.5 | 26.63 |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.1875 | 3 | 17.61 | 12.55 | 21.62 | 10.06 |

### Daily Best Skeleton Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 7 | 0.438 | 21.98 | 18.2 | 30.5 | 26.63 |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 3 | 0.188 | 17.61 | 12.55 | 21.62 | 10.06 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 1 | 0.062 | 19.79 | 19.79 | 21.26 | 21.26 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60 | 1 | 0.062 | 22.56 | 22.56 | 23.41 | 23.41 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | 1 | 0.062 | 33.09 | 33.09 | 37.28 | 37.28 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 1 | 0.062 | 22.01 | 22.01 | None | None |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60 | 1 | 0.062 | 15.81 | 15.81 | 25.2 | 25.2 |
| B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 1 | 0.062 | 15.28 | 15.28 | 13.28 | 13.28 |

### Daily Best Full Group Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 4 | 0.25 | 22.17 | 20.38 | 34.96 | 33.55 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.062 | 19.79 | 19.79 | 21.26 | 21.26 |
| B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=low | 1 | 0.062 | 22.56 | 22.56 | 23.41 | 23.41 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=low | 1 | 0.062 | 33.09 | 33.09 | 37.28 | 37.28 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0.062 | 17.45 | 17.45 | 39.55 | 39.55 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral | 1 | 0.062 | 29.52 | 29.52 | 9.13 | 9.13 |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 1 | 0.062 | 18.2 | 18.2 | 24.96 | 24.96 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=normal\|kdj=rising | 1 | 0.062 | 22.01 | 22.01 | None | None |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.062 | 12.55 | 12.55 | 7.09 | 7.09 |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.062 | 8.67 | 8.67 | 10.06 | 10.06 |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.062 | 31.61 | 31.61 | 47.72 | 47.72 |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.062 | 15.81 | 15.81 | 25.2 | 25.2 |

### Daily Best MACD Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:3:强势转分歧\|D:falling:6:修复 | 2 | 0.125 | 22.41 | 22.41 | 10.35 | 10.35 |
| W:falling:2:修复\|D:falling:2:修复 | 1 | 0.062 | 15.28 | 15.28 | 13.28 | 13.28 |
| W:falling:2:修复\|D:rising:4:强势 | 1 | 0.062 | 19.79 | 19.79 | 21.26 | 21.26 |
| W:rising:0:强势\|D:rising:1:背离 | 1 | 0.062 | 33.16 | 33.16 | 61.16 | 61.16 |
| W:rising:0:背离\|D:falling:2:修复 | 1 | 0.062 | 12.55 | 12.55 | 7.09 | 7.09 |
| W:rising:1:强势\|D:rising:0:分歧 | 1 | 0.062 | 25.46 | 25.46 | 40.47 | 40.47 |
| W:rising:1:背离\|D:falling:2:修复 | 1 | 0.062 | 15.81 | 15.81 | 25.2 | 25.2 |
| W:rising:2:背离\|D:falling:2:修复 | 1 | 0.062 | 22.01 | 22.01 | None | None |
| W:rising:2:背离\|D:rising:2:背离 | 1 | 0.062 | 31.61 | 31.61 | 47.72 | 47.72 |
| W:rising:3:分歧\|D:falling:2:修复 | 1 | 0.062 | 33.09 | 33.09 | 37.28 | 37.28 |
| W:rising:3:强势转分歧\|D:falling:4:背离 | 1 | 0.062 | 14.76 | 14.76 | 26.63 | 26.63 |
| W:rising:3:背离\|D:falling:6:修复 | 1 | 0.062 | 22.56 | 22.56 | 23.41 | 23.41 |

### Daily Best Samples

| date | code | verdict | score | ret3 | ret5 | skeleton_group | full_group | macd |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 2026-03-03 | 301093.SZ | WATCH | 3.87 | 8.67 | 10.06 | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | W:rising:5:背离\|D:falling:8:修复 |
| 2026-03-10 | 688519.SH | WATCH | 3.97 | 15.3 | 11.57 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:3:强势转分歧\|D:falling:6:修复 |
| 2026-04-08 | 300868.SZ | WATCH | 3.65 | 25.46 | 40.47 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:1:强势\|D:rising:0:分歧 |
| 2026-04-09 | 002580.SZ | WATCH | 3.86 | 33.16 | 61.16 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:0:强势\|D:rising:1:背离 |
| 2026-04-10 | 300938.SZ | WATCH | 3.65 | 15.81 | 25.2 | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60 | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=repair_from_low | W:rising:1:背离\|D:falling:2:修复 |
| 2026-04-13 | 300438.SZ | WATCH | 4.18 | 15.28 | 13.28 | B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | W:falling:2:修复\|D:falling:2:修复 |
| 2026-04-14 | 001400.SZ | WATCH | 3.83 | 14.76 | 26.63 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:3:强势转分歧\|D:falling:4:背离 |
| 2026-04-15 | 603268.SH | WATCH | 3.33 | 22.56 | 23.41 | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60 | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=low | W:rising:3:背离\|D:falling:6:修复 |
| 2026-04-16 | 605298.SH | WATCH | 3.85 | 19.79 | 21.26 | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:falling:2:修复\|D:rising:4:强势 |
| 2026-04-17 | 600487.SH | WATCH | 3.87 | 18.2 | 24.96 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | W:rising:5:分歧\|D:falling:6:修复 |
| 2026-05-18 | 603989.SH | WATCH | 4.07 | 17.45 | 39.55 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | W:rising:5:背离\|D:rising:0:背离 |
| 2026-05-21 | 688347.SH | WATCH | 4.01 | 31.61 | 47.72 | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | W:rising:2:背离\|D:rising:2:背离 |
| 2026-05-22 | 300626.SZ | WATCH | 3.96 | 29.52 | 9.13 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral | W:rising:3:强势转分歧\|D:falling:6:修复 |
| 2026-05-25 | 600726.SH | WATCH | 3.54 | 33.09 | 37.28 | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=low | W:rising:3:分歧\|D:falling:2:修复 |
| 2026-05-26 | 000690.SZ | WATCH | 3.98 | 12.55 | 7.09 | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | W:rising:0:背离\|D:falling:2:修复 |
| 2026-05-28 | 002951.SZ | WATCH | 4.04 | 22.01 | None | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=normal\|kdj=rising | W:rising:2:背离\|D:falling:2:修复 |
