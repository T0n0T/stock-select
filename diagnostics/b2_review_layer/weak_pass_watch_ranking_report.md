# Weak PASS/WATCH Ranking Report

- scope: env=weak and verdict in PASS/WATCH
- sample_count: 1074
- candidate_count: 1074
- diagnosis: Weak PASS/WATCH has almost no baseline edge over FAIL, so weak ranking should be used only to reduce top-list damage and find repair candidates, not to promote broad PASS rules. weak_v4 adds BBI/BIAS/OBV as an offline indicator experiment and should not be promoted unless it beats weak_v3 on both mean return and negative rate.

## Top3 Comparison

| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 75 | 14 | 46 | 0.187 | 0.613 | -1.54 | -3.71 | -3.65 | -5.32 |
| weak_v1_rank | 75 | 17 | 39 | 0.227 | 0.52 | -0.46 | -1.53 | -2.21 | -4.26 |
| weak_v2_rank | 75 | 18 | 40 | 0.24 | 0.533 | -0.53 | -1.53 | -2.03 | -4.26 |
| weak_v3_rank | 75 | 20 | 40 | 0.267 | 0.533 | 0.02 | -1.65 | -1.38 | -3.23 |
| weak_v4_rank | 75 | 19 | 42 | 0.253 | 0.56 | -0.31 | -2.12 | -1.67 | -4.26 |

## Top5 Comparison

| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 125 | 24 | 74 | 0.192 | 0.592 | -1.23 | -2.21 | -2.8 | -4.39 |
| weak_v1_rank | 125 | 29 | 69 | 0.232 | 0.552 | -0.81 | -1.72 | -1.9 | -2.3 |
| weak_v2_rank | 125 | 30 | 67 | 0.24 | 0.536 | -0.6 | -1.34 | -1.59 | -2.07 |
| weak_v3_rank | 125 | 30 | 67 | 0.24 | 0.536 | -0.47 | -1.52 | -1.42 | -2.07 |
| weak_v4_rank | 125 | 34 | 65 | 0.272 | 0.52 | 0.28 | -0.77 | -1.11 | -1.82 |

## Family Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| other | 1008 | 0.939 | 155 | 577 | 0.154 | 0.572 | -0.97 | -1.4 |
| W-B | 22 | 0.02 | 6 | 9 | 0.273 | 0.409 | 0.57 | 1.02 |
| W-A | 20 | 0.019 | 8 | 7 | 0.4 | 0.35 | 3.26 | 2.77 |
| W-C | 14 | 0.013 | 4 | 6 | 0.286 | 0.429 | 1.44 | 0.81 |
| W-D | 10 | 0.009 | 3 | 3 | 0.3 | 0.3 | 2.28 | 2.33 |

## Risk Flag Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| macd_w0_div_d4_repair | 32 | 0.372 | 2 | 24 | 0.062 | 0.75 | -5.58 | -5.83 |
| macd_w2_div_d4_repair | 16 | 0.186 | 0 | 15 | 0.0 | 0.938 | -3.97 | -3.12 |
| b2_near_high_normal_rising_no_red | 15 | 0.174 | 0 | 10 | 0.0 | 0.667 | -1.12 | -0.32 |
| b2_upper_expanding_neutral_red | 12 | 0.14 | 1 | 8 | 0.083 | 0.667 | -2.87 | -3.79 |
| b3_rebound_extended_mixed | 11 | 0.128 | 0 | 10 | 0.0 | 0.909 | -5.06 | -5.97 |

## Daily Weak V4 Rank Top3

| date | rank | code | verdict | family | weak_v4_score | current_score | ret3 | ret5 | indicator | risk_flags |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 2026-03-04 | 1 | 300423.SZ | WATCH | other | 3.95 | 3.95 | 10.77 | 9.07 | bbi=above_extended\|bias=neutral\|obv=flat |  |
| 2026-03-04 | 2 | 300042.SZ | WATCH | other | 3.83 | 3.83 | 12.84 | 13.63 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-04 | 3 | 920062.BJ | WATCH | other | 3.83 | 3.83 | 9.51 | 6.04 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-05 | 1 | 688517.SH | WATCH | other | 4.08 | 4.0 | 5.91 | 2.39 | bbi=above_extended\|bias=neutral\|obv=rising |  |
| 2026-03-05 | 2 | 300259.SZ | WATCH | other | 4.01 | 4.01 | 2.62 | 3.83 | bbi=above_extended\|bias=neutral\|obv=flat |  |
| 2026-03-05 | 3 | 300747.SZ | WATCH | W-B | 3.93 | 3.91 | -0.91 | 0.09 | bbi=above_extended\|bias=neutral\|obv=rising |  |
| 2026-03-06 | 1 | 688201.SH | WATCH | W-B | 4.28 | 4.12 | 2.12 | -5.32 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-06 | 2 | 688334.SH | WATCH | W-B | 4.13 | 3.89 | -1.45 | -8.39 | bbi=above_extended\|bias=positive\|obv=rising |  |
| 2026-03-06 | 3 | 300980.SZ | WATCH | other | 4.1 | 3.92 | -0.22 | -4.39 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-09 | 1 | 300209.SZ | WATCH | W-A | 4.27 | 3.79 | 5.76 | 25.88 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-09 | 2 | 301606.SZ | WATCH | other | 4.04 | 4.02 | -6.01 | -6.79 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-09 | 3 | 920493.BJ | WATCH | other | 4.04 | 3.86 | -2.38 | -9.44 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-11 | 1 | 603601.SH | WATCH | other | 4.09 | 4.01 | -7.39 | -5.46 | bbi=above_extended\|bias=positive\|obv=rising |  |
| 2026-03-11 | 2 | 603328.SH | WATCH | W-B | 4.06 | 3.84 | 1.34 | 0.71 | bbi=above\|bias=positive\|obv=flat |  |
| 2026-03-11 | 3 | 688253.SH | WATCH | W-A | 4.04 | 3.74 | 7.17 | 6.8 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-12 | 1 | 601388.SH | WATCH | other | 4.0 | 4.0 | -7.53 | -14.12 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-12 | 2 | 002361.SZ | WATCH | other | 3.98 | 3.98 | -11.57 | -12.31 | bbi=above\|bias=positive\|obv=rising |  |
| 2026-03-12 | 3 | 603612.SH | WATCH | other | 3.94 | 3.94 | -8.52 | -18.78 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-13 | 1 | 300672.SZ | WATCH | W-A | 4.04 | 3.74 | 23.27 | 21.34 | bbi=above_extended\|bias=high_positive\|obv=flat |  |
| 2026-03-13 | 2 | 601011.SH | WATCH | other | 3.89 | 3.89 | -4.74 | -10.0 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-13 | 3 | 600740.SH | WATCH | other | 3.81 | 3.81 | -7.98 | -10.18 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-16 | 1 | 002356.SZ | WATCH | W-B | 3.93 | 3.91 | -14.19 | -21.62 | bbi=above_extended\|bias=positive\|obv=rising |  |
| 2026-03-16 | 2 | 601975.SH | WATCH | other | 3.87 | 3.87 | -2.7 | -8.73 | bbi=above_extended\|bias=high_positive\|obv=flat |  |
| 2026-03-16 | 3 | 002286.SZ | WATCH | other | 3.86 | 3.86 | -5.75 | -15.58 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-17 | 1 | 688628.SH | WATCH | W-A | 4.12 | 3.74 | -5.68 | -4.67 | bbi=above_extended\|bias=positive\|obv=rising |  |
| 2026-03-17 | 2 | 920403.BJ | WATCH | other | 3.96 | 3.96 | -12.75 | -18.1 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-17 | 3 | 300393.SZ | WATCH | other | 3.87 | 3.87 | -7.37 | -8.57 | bbi=below_near\|bias=neutral\|obv=flat |  |
| 2026-03-18 | 1 | 688319.SH | WATCH | other | 4.03 | 4.03 | -12.44 | -9.24 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-18 | 2 | 688517.SH | WATCH | other | 3.93 | 3.93 | -11.26 | -3.34 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-18 | 3 | 001400.SZ | WATCH | other | 3.9 | 3.9 | -5.17 | 5.41 | bbi=above_extended\|bias=neutral\|obv=flat |  |
| 2026-03-19 | 1 | 002897.SZ | WATCH | other | 4.0 | 4.0 | -4.58 | -9.97 | bbi=below_near\|bias=neutral\|obv=flat |  |
| 2026-03-19 | 2 | 300332.SZ | WATCH | other | 3.92 | 3.92 | -4.34 | -1.82 | bbi=above_extended\|bias=high_positive\|obv=flat |  |
| 2026-03-19 | 3 | 300164.SZ | WATCH | other | 3.87 | 3.87 | -7.53 | -14.43 | bbi=above_extended\|bias=neutral\|obv=flat |  |
| 2026-03-20 | 1 | 300693.SZ | WATCH | other | 3.87 | 3.87 | -2.32 | -5.18 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-20 | 2 | 300782.SZ | WATCH | other | 3.85 | 3.67 | -2.1 | -4.68 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-20 | 3 | 000966.SZ | WATCH | other | 3.67 | 3.67 | 8.16 | 6.99 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-23 | 1 | 300345.SZ | WATCH | other | 4.05 | 4.03 | -9.23 | -12.24 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-23 | 2 | 002506.SZ | WATCH | other | 4.01 | 3.93 | -6.9 | -12.76 | bbi=above_extended\|bias=positive\|obv=rising |  |
| 2026-03-23 | 3 | 300868.SZ | WATCH | W-C | 3.88 | 3.67 | 5.98 | 20.46 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-24 | 1 | 300080.SZ | WATCH | other | 3.99 | 3.99 | -7.87 | -20.06 | bbi=above_extended\|bias=neutral\|obv=flat |  |
| 2026-03-24 | 2 | 000692.SZ | WATCH | other | 3.9 | 3.9 | 14.35 | 16.94 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-24 | 3 | 000993.SZ | WATCH | other | 3.89 | 3.89 | 14.02 | 14.3 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-25 | 1 | 688272.SH | WATCH | W-A | 4.22 | 3.74 | 10.32 | 10.0 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-03-25 | 2 | 001289.SZ | WATCH | W-A | 4.14 | 3.76 | -7.92 | -15.59 | bbi=above_extended\|bias=positive\|obv=rising |  |
| 2026-03-25 | 3 | 688796.SH | WATCH | W-A | 4.04 | 3.82 | 10.71 | 16.72 | bbi=above_extended\|bias=positive\|obv=falling |  |
| 2026-03-26 | 1 | 002281.SZ | WATCH | other | 4.02 | 4.02 | -0.82 | -1.29 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-26 | 2 | 300072.SZ | WATCH | other | 3.94 | 3.94 | -9.42 | -9.25 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-26 | 3 | 301307.SZ | WATCH | other | 3.9 | 3.9 | -2.8 | -5.75 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-27 | 1 | 002408.SZ | WATCH | W-B | 4.03 | 3.81 | 6.9 | -1.15 | bbi=above\|bias=positive\|obv=flat |  |
| 2026-03-27 | 2 | 000833.SZ | WATCH | other | 3.87 | 3.87 | -2.15 | -7.27 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-03-27 | 3 | 688319.SH | WATCH | other | 3.86 | 3.86 | 2.15 | -0.54 | bbi=above\|bias=positive\|obv=rising |  |
| 2026-03-30 | 1 | 600872.SH | WATCH | W-A | 4.04 | 3.74 | 1.15 | -0.21 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-30 | 2 | 000912.SZ | WATCH | other | 3.9 | 3.9 | -6.31 | -5.05 | bbi=above\|bias=positive\|obv=flat |  |
| 2026-03-30 | 3 | 002903.SZ | WATCH | other | 3.89 | 3.89 | -2.17 | -2.07 | bbi=above\|bias=positive\|obv=flat |  |
| 2026-03-31 | 1 | 603211.SH | WATCH | W-A | 3.89 | 3.59 | -5.93 | 3.08 | bbi=above_extended\|bias=neutral\|obv=flat |  |
| 2026-03-31 | 2 | 601000.SH | WATCH | other | 3.67 | 3.67 | 0.43 | -0.21 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-03-31 | 3 | 301179.SZ | WATCH | other | 3.56 | 3.56 | 6.82 | 9.66 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-04-01 | 1 | 300257.SZ | WATCH | other | 3.87 | 3.87 | 0.92 | 4.01 | bbi=below_near\|bias=neutral\|obv=flat |  |
| 2026-04-01 | 2 | 603803.SH | WATCH | other | 3.86 | 3.86 | -4.02 | 4.82 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-04-01 | 3 | 688158.SH | WATCH | other | 3.84 | 3.84 | -8.75 | 4.34 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-04-02 | 1 | 300831.SZ | WATCH | other | 3.77 | 3.77 | 1.36 | -4.26 | bbi=above\|bias=positive\|obv=flat |  |
| 2026-04-02 | 2 | 603306.SH | WATCH | W-B | 3.75 | 3.59 | 6.63 | 23.02 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-04-02 | 3 | 002382.SZ | WATCH | other | 3.69 | 3.69 | -3.41 | -5.24 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-04-03 | 1 | 688226.SH | WATCH | other | 3.69 | 3.67 | 3.44 | 2.78 | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-04-03 | 2 | 300720.SZ | WATCH | other | 3.67 | 3.67 | 5.27 | -14.59 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-04-03 | 3 | 603619.SH | WATCH | other | 3.65 | 3.65 | -0.73 | 3.93 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-04-07 | 1 | 002025.SZ | WATCH | other | 4.04 | 4.04 | 14.25 | 17.93 | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-04-07 | 2 | 300651.SZ | WATCH | other | 3.8 | 3.8 | -4.51 | -9.41 | bbi=above_extended\|bias=high_positive\|obv=flat |  |
| 2026-04-07 | 3 | 300720.SZ | WATCH | other | 3.63 | 3.63 | -15.77 | -11.03 | bbi=above\|bias=neutral\|obv=flat |  |
| 2026-05-27 | 1 | 000539.SZ | WATCH | other | 3.94 | 3.94 | 33.11 | None | bbi=above_extended\|bias=high_positive\|obv=flat |  |
| 2026-05-27 | 2 | 300617.SZ | WATCH | other | 3.93 | 3.93 | 2.81 | None | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-05-27 | 3 | 603335.SH | WATCH | other | 3.93 | 3.93 | 3.28 | None | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-05-29 | 1 | 300877.SZ | WATCH | W-A | 4.22 | 3.92 | None | None | bbi=above_extended\|bias=positive\|obv=flat |  |
| 2026-05-29 | 2 | 688006.SH | WATCH | W-A | 4.21 | 3.73 | None | None | bbi=above_extended\|bias=high_positive\|obv=rising |  |
| 2026-05-29 | 3 | 300265.SZ | WATCH | other | 3.87 | 3.87 | None | None | bbi=above_extended\|bias=positive\|obv=flat |  |
