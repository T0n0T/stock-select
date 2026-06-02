# Environment Skeleton Top1 Report

- scope: environment-specific PASS+WATCH top1 skeleton ranking simulation
- diagnosis: Each environment uses only its own high-ret3 priority skeleton groups; no shared skeleton is forced across environments.

## neutral

- day_count: 16
- skeleton_top1_from_group_days: 16
- diagnosis: offline_candidate

### Top1 Comparison

| ranker | samples | ret3>0 | ret3>0 rate | ret3>=5 | ret3<=0 | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 16 | 8 | 0.5 | 3 | 8 | 0.64 | -0.59 | -0.22 | 1.16 |
| skeleton_rank | 16 | 8 | 0.5 | 4 | 8 | -0.5 | -0.23 | 1.56 | 1.06 |

### Environment Priority Skeleton Groups

| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.4375 | 7 | 21.98 | 18.2 | 30.5 | 26.63 |
| B3\|rebound\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.1875 | 3 | 17.61 | 12.55 | 21.62 | 10.06 |

### Skeleton Top1 Group Distribution

| group | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 16 | 1.0 | -0.5 | -0.23 | 1.56 | 1.06 |

### Daily Top1

| date | current_code | current_score | current_ret3 | skeleton_code | skeleton_score | boost | skeleton_ret3 | skeleton_group |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 2026-03-03 | 603836.SH | 4.19 | -5.89 | 002957.SZ | 4.947 | 0.887 | -10.33 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-10 | 688171.SH | 4.19 | -2.77 | 688171.SH | 5.078 | 0.887 | -2.77 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-08 | 301157.SZ | 4.19 | 0.94 | 301157.SZ | 5.078 | 0.887 | 0.94 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-09 | 301018.SZ | 4.19 | 20.15 | 300938.SZ | 4.838 | 0.887 | 10.97 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-10 | 301509.SZ | 4.19 | 7.32 | 301509.SZ | 5.078 | 0.887 | 7.32 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-13 | 300438.SZ | 4.18 | 15.28 | 301306.SZ | 4.958 | 0.887 | 8.78 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-14 | 688663.SH | 4.18 | 0.59 | 603139.SH | 4.978 | 0.887 | 5.8 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-15 | 600233.SH | 4.08 | -3.12 | 600233.SH | 4.968 | 0.887 | -3.12 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-16 | 002832.SZ | 4.16 | 4.99 | 000070.SZ | 4.947 | 0.887 | -1.4 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-17 | 605196.SH | 4.17 | -8.46 | 001267.SZ | 4.918 | 0.887 | 3.53 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-18 | 002066.SZ | 4.19 | -1.77 | 002937.SZ | 4.958 | 0.887 | -6.83 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-21 | 603127.SH | 4.19 | -12.37 | 603127.SH | 5.078 | 0.887 | -12.37 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-22 | 300305.SZ | 4.21 | -4.58 | 300554.SZ | 5.078 | 0.887 | 3.37 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-25 | 301129.SZ | 4.33 | -5.52 | 300236.SZ | 5.088 | 0.887 | -7.42 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-26 | 000883.SZ | 4.33 | 4.31 | 301487.SZ | 4.947 | 0.887 | -5.54 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-28 | 300305.SZ | 4.19 | 1.11 | 300305.SZ | 5.078 | 0.887 | 1.11 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |

## strong

- day_count: 20
- skeleton_top1_from_group_days: 20
- diagnosis: needs_narrower_veto

### Top1 Comparison

| ranker | samples | ret3>0 | ret3>0 rate | ret3>=5 | ret3<=0 | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 20 | 12 | 0.6 | 8 | 8 | 0.84 | 1.56 | 4.55 | 6.83 |
| skeleton_rank | 20 | 10 | 0.5 | 8 | 10 | 0.7 | -0.46 | 2.17 | -0.45 |

### Environment Priority Skeleton Groups

| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.65 | 13 | 30.66 | 33.55 | 34.82 | 28.23 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 0.1 | 2 | 24.21 | 24.21 | 23.09 | 23.09 |
| B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.1 | 2 | 17.83 | 17.83 | 17.86 | 17.86 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | 0.1 | 2 | 15.92 | 15.92 | 25.3 | 25.3 |

### Skeleton Top1 Group Distribution

| group | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 19 | 0.95 | 0.23 | -2.18 | 1.83 | -0.51 |
| B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 1 | 0.05 | 9.74 | 9.74 | 8.57 | 8.57 |

### Daily Top1

| date | current_code | current_score | current_ret3 | skeleton_code | skeleton_score | boost | skeleton_ret3 | skeleton_group |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 2026-03-02 | 002826.SZ | 4.44 | 1.05 | 688301.SH | 5.42 | 1.1 | -4.01 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-20 | 600522.SH | 4.17 | 10.08 | 600522.SH | 5.27 | 1.1 | 10.08 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-21 | 600869.SH | 4.64 | 3.84 | 001286.SZ | 5.28 | 1.1 | -2.97 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-22 | 300931.SZ | 4.34 | 1.86 | 301191.SZ | 5.37 | 1.1 | -2.18 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-23 | 002730.SZ | 4.19 | 8.2 | 603912.SH | 5.26 | 1.1 | -11.61 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-24 | 603819.SH | 4.31 | -6.47 | 603819.SH | 5.41 | 1.1 | -6.47 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-27 | 301165.SZ | 4.44 | -6.12 | 601208.SH | 5.42 | 1.1 | 8.51 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-28 | 300672.SZ | 4.54 | 6.15 | 300571.SZ | 5.36 | 1.1 | 32.44 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-29 | 301326.SZ | 4.32 | 7.77 | 301326.SZ | 5.42 | 1.1 | 7.77 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-30 | 603897.SH | 4.49 | 8.84 | 603897.SH | 5.59 | 1.1 | 8.84 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-06 | 300099.SZ | 4.73 | 1.26 | 300099.SZ | 5.83 | 1.1 | 1.26 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-07 | 002962.SZ | 4.7 | 5.9 | 002962.SZ | 5.8 | 1.1 | 5.9 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-08 | 603838.SH | 4.77 | 9.74 | 603838.SH | 5.32 | 0.55 | 9.74 | B3\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-11 | 301237.SZ | 4.28 | -4.39 | 301237.SZ | 5.38 | 1.1 | -4.39 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-12 | 300001.SZ | 4.32 | 9.74 | 000949.SZ | 5.25 | 1.1 | 1.72 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-13 | 002042.SZ | 4.62 | -5.44 | 002042.SZ | 5.72 | 1.1 | -5.44 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-14 | 603332.SH | 4.36 | -3.69 | 603520.SH | 5.41 | 1.1 | 6.49 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-15 | 300651.SZ | 4.32 | -22.31 | 300651.SZ | 5.42 | 1.1 | -22.31 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-19 | 002452.SZ | 4.64 | -3.03 | 300547.SZ | 5.42 | 1.1 | -4.55 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-20 | 603229.SH | 4.77 | -6.14 | 300438.SZ | 5.59 | 1.1 | -14.73 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |

## weak

- day_count: 24
- skeleton_top1_from_group_days: 24
- diagnosis: offline_candidate

### Top1 Comparison

| ranker | samples | ret3>0 | ret3>0 rate | ret3>=5 | ret3<=0 | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 24 | 9 | 0.375 | 5 | 15 | -1.36 | -4.66 | -4.89 | -5.46 |
| skeleton_rank | 24 | 13 | 0.542 | 7 | 11 | 3.5 | 1.2 | 1.97 | -0.54 |

### Environment Priority Skeleton Groups

| group | coverage | days | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 0.3478 | 8 | 27.49 | 31.04 | 20.32 | 9.66 |
| B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack | 0.1304 | 3 | 22.43 | 18.48 | 14.3 | 13.72 |
| B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack | 0.087 | 2 | 24.82 | 24.82 | 23.19 | 23.19 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 0.087 | 2 | 14.84 | 14.84 | 5.55 | 5.55 |

### Skeleton Top1 Group Distribution

| group | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack | 21 | 0.875 | 4.85 | 2.15 | 3.33 | 1.69 |
| B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack | 2 | 0.083 | -4.17 | -4.17 | -5.98 | -5.98 |
| B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack | 1 | 0.042 | -9.42 | -9.42 | -9.25 | -9.25 |

### Daily Top1

| date | current_code | current_score | current_ret3 | skeleton_code | skeleton_score | boost | skeleton_ret3 | skeleton_group |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 2026-03-04 | 300423.SZ | 3.95 | 10.77 | 688662.SH | 4.578 | 0.798 | 0.49 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-05 | 300389.SZ | 4.03 | -8.77 | 300259.SZ | 4.808 | 0.798 | 2.62 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-06 | 300259.SZ | 4.13 | 5.19 | 001216.SZ | 4.708 | 0.798 | 4.86 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-09 | 688118.SH | 4.08 | -6.36 | 301606.SZ | 4.557 | 0.537 | -6.01 | B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack |
| 2026-03-11 | 603601.SH | 4.01 | -7.39 | 000830.SZ | 4.598 | 0.798 | -10.86 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-12 | 601388.SH | 4.0 | -7.53 | 601388.SH | 4.798 | 0.798 | -7.53 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-13 | 601011.SH | 3.89 | -4.74 | 605222.SH | 4.468 | 0.798 | -1.99 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-16 | 002356.SZ | 3.91 | -14.19 | 601975.SH | 4.668 | 0.798 | -2.7 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-17 | 920403.BJ | 3.96 | -12.75 | 300393.SZ | 4.668 | 0.798 | -7.37 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-18 | 688319.SH | 4.03 | -12.44 | 688517.SH | 4.728 | 0.798 | -11.26 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-19 | 002897.SZ | 4.0 | -4.58 | 000968.SZ | 4.658 | 0.798 | 6.83 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-20 | 300693.SZ | 3.87 | -2.32 | 300693.SZ | 4.407 | 0.537 | -2.32 | B2\|trend_start\|price=upper_or_near_high\|midline=reclaim_volume\|support=bull_stack |
| 2026-03-23 | 300345.SZ | 4.03 | -9.23 | 002506.SZ | 4.728 | 0.798 | -6.9 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-24 | 300080.SZ | 3.99 | -7.87 | 000692.SZ | 4.698 | 0.798 | 14.35 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-25 | 688607.SH | 4.02 | 14.06 | 002281.SZ | 4.698 | 0.798 | 1.91 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-26 | 002281.SZ | 4.02 | -0.82 | 300072.SZ | 4.477 | 0.537 | -9.42 | B2\|trend_start\|price=upper_or_near_high\|midline=pullback_confirm\|support=bull_stack |
| 2026-03-27 | 300736.SZ | 4.04 | -10.91 | 688319.SH | 4.658 | 0.798 | 2.15 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-30 | 000912.SZ | 3.9 | -6.31 | 600105.SH | 4.468 | 0.798 | 9.39 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-03-31 | 601000.SH | 3.67 | 0.43 | 301179.SZ | 4.358 | 0.798 | 6.82 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-01 | 300257.SZ | 3.87 | 0.92 | 603803.SH | 4.658 | 0.798 | -4.02 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-02 | 300831.SZ | 3.77 | 1.36 | 688485.SH | 4.238 | 0.798 | 54.18 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-03 | 688226.SH | 3.67 | 3.44 | 688226.SH | 4.468 | 0.798 | 3.44 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-04-07 | 002025.SZ | 4.04 | 14.25 | 002025.SZ | 4.838 | 0.798 | 14.25 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
| 2026-05-27 | 000539.SZ | 3.94 | 33.11 | 000539.SZ | 4.738 | 0.798 | 33.11 | B2\|trend_start\|price=upper_or_near_high\|midline=above_hold\|support=bull_stack |
