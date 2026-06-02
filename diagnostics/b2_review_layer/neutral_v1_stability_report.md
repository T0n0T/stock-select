# Neutral V1 Stability Report

- scope: neutral_v1 daily top3 stability and loss review
- day_count: 16
- improved_days: 12
- regressed_days: 5
- neutral_better_positive_days: 9
- neutral_lower_negative_days: 6
- top3_loss_count: 20
- top3_loss_ret3_mean: -6.13
- diagnosis: neutral_v1 improves aggregate top3, but production rank_score should wait until regression days and top3 loss samples are reviewed by date and risk flag.

## Daily Deltas

| date | ret3>=5 delta | ret3<=0 delta | ret3_mean delta | current ret3>=5 | neutral ret3>=5 | current ret3<=0 | neutral ret3<=0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-03-03 | 1 | -1 | 4.55 | 0 | 1 | 3 | 2 |
| 2026-03-10 | 0 | 0 | 3.07 | 0 | 0 | 3 | 3 |
| 2026-04-08 | 1 | -1 | 2.61 | 0 | 1 | 1 | 0 |
| 2026-04-09 | 0 | 0 | -0.07 | 2 | 2 | 0 | 0 |
| 2026-04-10 | 1 | 0 | 2.54 | 1 | 2 | 1 | 1 |
| 2026-04-13 | 1 | 0 | 1.75 | 2 | 3 | 0 | 0 |
| 2026-04-14 | 0 | 0 | 0.19 | 1 | 1 | 0 | 0 |
| 2026-04-15 | 2 | 0 | -0.64 | 0 | 2 | 1 | 1 |
| 2026-04-16 | 0 | 1 | -4.33 | 0 | 0 | 1 | 2 |
| 2026-04-17 | 1 | -2 | 8.39 | 0 | 1 | 3 | 1 |
| 2026-05-18 | 1 | -1 | 3.76 | 0 | 1 | 3 | 2 |
| 2026-05-21 | 1 | -1 | 4.62 | 1 | 2 | 2 | 1 |
| 2026-05-22 | 0 | 0 | -0.82 | 1 | 1 | 1 | 1 |
| 2026-05-25 | 1 | 0 | 2.74 | 0 | 1 | 2 | 2 |
| 2026-05-26 | 0 | 1 | -5.49 | 0 | 0 | 2 | 3 |
| 2026-05-28 | 0 | -1 | 0.62 | 0 | 0 | 2 | 1 |

## Regression Days

| date | ret3>=5 delta | ret3<=0 delta | ret3_mean delta |
| --- | ---: | ---: | ---: |
| 2026-04-09 | 0 | 0 | -0.07 |
| 2026-04-15 | 2 | 0 | -0.64 |
| 2026-04-16 | 0 | 1 | -4.33 |
| 2026-05-22 | 0 | 0 | -0.82 |
| 2026-05-26 | 0 | 1 | -5.49 |

## Top3 Loss Risk Flags

| flag | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

## Top3 Loss Signal Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start | 13 | 0.65 | -6.98 | -5.39 | -6.77 | -8.52 |
| B3\|trend_start | 7 | 0.35 | -4.56 | -3.66 | -8.31 | -6.67 |

## Top3 Loss Factor Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 4 | 0.2 | -5.82 | -5.4 | -3.11 | -2.28 |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 2 | 0.1 | -7.74 | -7.74 | -12.66 | -12.66 |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 2 | 0.1 | -9.62 | -9.62 | -12.2 | -12.2 |
| neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.1 | -2.71 | -2.71 | -10.49 | -10.49 |
| neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.1 | -5.12 | -5.12 | -8.59 | -8.59 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.05 | -5.39 | -5.39 | -2.62 | -2.62 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.05 | -1.4 | -1.4 | 1.06 | 1.06 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.05 | -4.33 | -4.33 | -9.72 | -9.72 |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.05 | -15.77 | -15.77 | None | None |
| neutral\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0.05 | -5.89 | -5.89 | -7.77 | -7.77 |
| neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.05 | -7.1 | -7.1 | -6.67 | -6.67 |
| neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=overheat | 1 | 0.05 | -3.66 | -3.66 | -2.95 | -2.95 |
| neutral\|B3\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.05 | -5.52 | -5.52 | -10.35 | -10.35 |

## Top3 Loss MACD Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:2:背离\|D:rising:2:背离 | 2 | 0.1 | -2.36 | -2.36 | -12.1 | -12.1 |
| W:falling:4:背离\|D:rising:2:背离 | 1 | 0.05 | -3.11 | -3.11 | -10.56 | -10.56 |
| W:idle:0:等待启动\|D:rising:0:背离 | 1 | 0.05 | -0.32 | -0.32 | 2.59 | 2.59 |
| W:idle:0:等待启动\|D:rising:2:分歧 | 1 | 0.05 | -7.1 | -7.1 | -6.67 | -6.67 |
| W:idle:0:等待启动\|D:rising:2:强势 | 1 | 0.05 | -3.66 | -3.66 | -2.95 | -2.95 |
| W:rising:0:强势\|D:rising:2:背离 | 1 | 0.05 | -4.33 | -4.33 | -9.72 | -9.72 |
| W:rising:0:强势\|D:rising:5:背离 | 1 | 0.05 | -7.99 | -7.99 | -7.15 | -7.15 |
| W:rising:2:强势\|D:rising:0:背离 | 1 | 0.05 | -5.52 | -5.52 | -10.35 | -10.35 |
| W:rising:2:背离\|D:rising:0:背离 | 1 | 0.05 | -12.37 | -12.37 | -14.75 | -14.75 |
| W:rising:3:强势\|D:rising:3:分歧 | 1 | 0.05 | -1.4 | -1.4 | 1.06 | 1.06 |
| W:rising:3:强势\|D:rising:5:强势转分歧 | 1 | 0.05 | -2.81 | -2.81 | 8.69 | 8.69 |
| W:rising:3:强势转分歧\|D:falling:6:修复 | 1 | 0.05 | -5.39 | -5.39 | -2.62 | -2.62 |
| W:rising:3:背离\|D:falling:2:修复 | 1 | 0.05 | -3.46 | -3.46 | -6.06 | -6.06 |
| W:rising:3:背离\|D:rising:1:背离 | 1 | 0.05 | -12.15 | -12.15 | -16.57 | -16.57 |
| W:rising:4:背离\|D:rising:0:背离 | 1 | 0.05 | -5.89 | -5.89 | -7.77 | -7.77 |
| W:rising:4:背离\|D:rising:17:强势 | 1 | 0.05 | -8.46 | -8.46 | -13.04 | -13.04 |
| W:rising:5:分歧\|D:rising:2:强势 | 1 | 0.05 | -1.77 | -1.77 | -4.15 | -4.15 |
| W:rising:5:强势转分歧\|D:falling:4:修复 | 1 | 0.05 | -15.77 | -15.77 | None | None |
| W:rising:5:背离\|D:falling:2:修复 | 1 | 0.05 | -16.46 | -16.46 | -15.13 | -15.13 |

## Worst Neutral V1 Top3 Losses

| date | code | verdict | neutral_v1_score | current_score | positive_score | risk_penalty | ret3 | ret5 | signal | signal_type | risk_flags |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 2026-04-15 | 002294.SZ | WATCH | 4.7 | 4.04 | 0.66 | 0.0 | -16.46 | -15.13 | B2 | trend_start |  |
| 2026-05-28 | 301183.SZ | WATCH | 4.77 | 4.07 | 0.7 | 0.0 | -15.77 | None | B2 | trend_start |  |
| 2026-05-21 | 603127.SH | WATCH | 4.79 | 4.19 | 0.6 | 0.0 | -12.37 | -14.75 | B2 | trend_start |  |
| 2026-05-26 | 688593.SH | WATCH | 4.75 | 4.05 | 0.7 | 0.0 | -12.15 | -16.57 | B2 | trend_start |  |
| 2026-04-17 | 605196.SH | WATCH | 4.79 | 4.17 | 0.62 | 0.0 | -8.46 | -13.04 | B3 | trend_start |  |
| 2026-04-16 | 300804.SZ | WATCH | 4.66 | 3.96 | 0.7 | 0.0 | -7.99 | -7.15 | B2 | trend_start |  |
| 2026-05-26 | 688310.SH | WATCH | 4.66 | 4.18 | 0.48 | 0.0 | -7.1 | -6.67 | B3 | trend_start |  |
| 2026-03-03 | 603836.SH | WATCH | 4.63 | 4.19 | 0.44 | 0.0 | -5.89 | -7.77 | B2 | trend_start |  |
| 2026-05-25 | 301129.SZ | WATCH | 4.79 | 4.33 | 0.46 | 0.0 | -5.52 | -10.35 | B3 | trend_start |  |
| 2026-03-03 | 001278.SZ | WATCH | 4.6 | 4.04 | 0.56 | 0.0 | -5.39 | -2.62 | B2 | trend_start |  |
| 2026-03-10 | 300873.SZ | WATCH | 4.79 | 4.19 | 0.6 | 0.0 | -4.33 | -9.72 | B2 | trend_start |  |
| 2026-05-26 | 600060.SH | WATCH | 4.71 | 4.19 | 0.52 | 0.0 | -3.66 | -2.95 | B3 | trend_start |  |
| 2026-05-25 | 001268.SZ | WATCH | 4.81 | 4.19 | 0.62 | 0.0 | -3.46 | -6.06 | B3 | trend_start |  |
| 2026-05-18 | 300483.SZ | WATCH | 4.66 | 4.06 | 0.6 | 0.0 | -3.11 | -10.56 | B2 | trend_start |  |
| 2026-04-10 | 688178.SH | WATCH | 4.75 | 4.05 | 0.7 | 0.0 | -2.81 | 8.69 | B2 | trend_start |  |
| 2026-03-10 | 688171.SH | WATCH | 4.85 | 4.19 | 0.66 | 0.0 | -2.77 | -9.27 | B2 | trend_start |  |
| 2026-05-22 | 600699.SH | WATCH | 4.81 | 4.19 | 0.62 | 0.0 | -1.95 | -14.93 | B3 | trend_start |  |
| 2026-05-18 | 002066.SZ | WATCH | 4.81 | 4.19 | 0.62 | 0.0 | -1.77 | -4.15 | B3 | trend_start |  |
| 2026-04-16 | 000070.SZ | WATCH | 4.66 | 4.06 | 0.6 | 0.0 | -1.4 | 1.06 | B2 | trend_start |  |
| 2026-03-10 | 920068.BJ | WATCH | 4.76 | 4.06 | 0.7 | 0.0 | -0.32 | 2.59 | B2 | trend_start |  |
