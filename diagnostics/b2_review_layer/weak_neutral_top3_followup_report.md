# Weak/Neutral Top3 Follow-up Report

- scope: weak and neutral top3 follow-up after freezing strong_v1_rank
- strong_policy: strong_v1_rank is frozen for this tuning round; this report does not evaluate or change strong.
- diagnosis: Neutral has the cleaner top3 ret3>=5 improvement through neutral_v1. Weak has improved hit rate through weak_v3/weak_v4 but still needs loss veto refinement before production ranking changes.

## weak

- next_step: Use weak_v3 as the top3 hit-rate reference and weak_v4 as the top5/indicator reference; continue by reducing top3 ret3<=0 with loss factor/MACD/risk groups before any production promotion.

### Top3 Metrics

| variant | samples | ret3>=5 | pos_rate | ret3<=0 | neg_rate | ret3_mean | ret3_median | daily_hit_days | daily_hit_rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 72 | 14 | 0.194 | 46 | 0.639 | -1.54 | -3.71 | 9/24 | 0.375 |
| weak_v3_rank | 72 | 20 | 0.278 | 40 | 0.556 | 0.02 | -1.65 | 15/24 | 0.625 |
| weak_v4_rank | 72 | 19 | 0.264 | 42 | 0.583 | -0.31 | -2.12 | 15/24 | 0.625 |

### current_score Loss Factor Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 3 | 0.065 | -3.41 | -4.34 | -7.22 | -4.27 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.043 | -12.23 | -12.23 | -10.54 | -10.54 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 2 | 0.043 | -5.7 | -5.7 | -1.88 | -1.88 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.043 | -3.66 | -3.66 | -2.24 | -2.24 |
| weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.043 | -4.67 | -4.67 | -1.08 | -1.08 |
| weak\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.043 | -7.15 | -7.15 | -8.7 | -8.7 |
| weak\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.043 | -10.28 | -10.28 | -15.63 | -15.63 |
| weak\|B2\|rebound\|price=middle\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=low | 1 | 0.022 | -7.86 | -7.86 | -7.2 | -7.2 |
| weak\|B2\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.022 | -5.82 | -5.82 | -10.83 | -10.83 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.022 | -7.53 | -7.53 | -14.43 | -14.43 |

### current_score Loss Risk Flags

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| b2_mid_near_expanding_red_macd_bad | 4 | 0.444 | -8.75 | -9.0 | -9.37 | -9.52 |
| b3_trend_red_macd_bad | 3 | 0.333 | -10.49 | -10.91 | -14.7 | -12.83 |
| b2_extended_neutral_macd_bad | 2 | 0.222 | -12.23 | -12.23 | -10.54 | -10.54 |

### weak_v3_rank Loss Factor Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 3 | 0.075 | -3.41 | -4.34 | -7.22 | -4.27 |
| weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.075 | -5.75 | -5.93 | -5.92 | -5.24 |
| weak\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.075 | -7.33 | -6.36 | -13.22 | -9.64 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 2 | 0.05 | -5.7 | -5.7 | -1.88 | -1.88 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.05 | -3.94 | -3.94 | -1.66 | -1.66 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.025 | -7.53 | -7.53 | -14.43 | -14.43 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0.025 | -8.75 | -8.75 | 4.34 | 4.34 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0.025 | -1.85 | -1.85 | -3.23 | -3.23 |
| weak\|B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.025 | -2.15 | -2.15 | -7.27 | -7.27 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral | 1 | 0.025 | -11.26 | -11.26 | -3.34 | -3.34 |

### weak_v3_rank Loss Risk Flags

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| b3_trend_red_macd_bad | 2 | 0.667 | -10.28 | -10.28 | -15.63 | -15.63 |
| b2_mid_near_expanding_red_macd_bad | 1 | 0.333 | -9.23 | -9.23 | -12.24 | -12.24 |

### weak_v4_rank Loss Factor Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.071 | -5.75 | -5.93 | -5.92 | -5.24 |
| weak\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.071 | -5.52 | -1.45 | -9.97 | -8.39 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 2 | 0.048 | -5.7 | -5.7 | -1.88 | -1.88 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.048 | -3.94 | -3.94 | -1.66 | -1.66 |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 2 | 0.048 | -5.04 | -5.04 | -8.7 | -8.7 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.024 | -7.53 | -7.53 | -14.43 | -14.43 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0.024 | -8.75 | -8.75 | 4.34 | 4.34 |
| weak\|B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.024 | -2.15 | -2.15 | -7.27 | -7.27 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral | 1 | 0.024 | -11.26 | -11.26 | -3.34 | -3.34 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=wide\|volume=normal\|kdj=rising | 1 | 0.024 | -4.51 | -4.51 | -9.41 | -9.41 |

### weak_v4_rank Loss Risk Flags

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| b2_mid_near_expanding_red_macd_bad | 2 | 0.5 | -7.62 | -7.62 | -9.52 | -9.52 |
| b3_trend_red_macd_bad | 2 | 0.5 | -7.55 | -7.55 | -10.77 | -10.77 |

## neutral

- next_step: Keep neutral_v1 as the current neutral candidate; neutral_v2 only remains useful if it reduces losses without lowering top3 ret3>=5 capture.

### Top3 Metrics

| variant | samples | ret3>=5 | pos_rate | ret3<=0 | neg_rate | ret3_mean | ret3_median | daily_hit_days | daily_hit_rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 48 | 8 | 0.167 | 25 | 0.521 | -0.2 | -0.97 | 6/16 | 0.375 |
| neutral_v1_rank | 48 | 18 | 0.375 | 20 | 0.417 | 1.27 | 1.32 | 12/16 | 0.75 |
| neutral_v2_rank | 48 | 18 | 0.375 | 20 | 0.417 | 1.31 | 1.59 | 12/16 | 0.75 |

### current_score Loss Factor Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 3 | 0.12 | -4.92 | -5.53 | 0.96 | 0.96 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 2 | 0.08 | -6.72 | -6.72 | -5.53 | -5.53 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.08 | -4.31 | -4.31 | -8.91 | -8.91 |
| neutral\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 2 | 0.08 | -3.88 | -3.88 | -5.29 | -5.29 |
| neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.08 | -2.06 | -2.06 | -4.69 | -4.69 |
| neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.08 | -5.12 | -5.12 | -8.59 | -8.59 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0.04 | -7.42 | -7.42 | -18.11 | -18.11 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.04 | -4.51 | -4.51 | 3.47 | 3.47 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.04 | -1.4 | -1.4 | 1.06 | 1.06 |
| neutral\|B2\|trend_start\|price=near_high\|midline=pullback_confirm\|support=bull_stack\|compression=wide\|volume=expanding\|kdj=rising | 1 | 0.04 | -8.54 | -8.54 | None | None |

### current_score Loss Risk Flags

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral_b2_near_high_expanding_macd_bad | 8 | 0.8 | -6.16 | -6.55 | -4.57 | -1.62 |
| neutral_b3_near_high_turnover_mixed | 2 | 0.2 | -2.06 | -2.06 | -4.69 | -4.69 |

### neutral_v1_rank Loss Factor Distribution

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

### neutral_v1_rank Loss Risk Flags

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

### neutral_v2_rank Loss Factor Distribution

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 6 | 0.3 | -6.39 | -5.54 | -6.95 | -6.59 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 2 | 0.1 | -4.95 | -4.95 | 0.43 | 0.43 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.1 | -2.97 | -2.97 | -6.98 | -6.98 |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.1 | -9.24 | -9.24 | -10.34 | -10.34 |
| neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 2 | 0.1 | -5.12 | -5.12 | -8.59 | -8.59 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.05 | -1.4 | -1.4 | 1.06 | 1.06 |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.05 | -16.46 | -16.46 | -15.13 | -15.13 |
| neutral\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0.05 | -5.89 | -5.89 | -7.77 | -7.77 |
| neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.05 | -7.1 | -7.1 | -6.67 | -6.67 |
| neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=overheat | 1 | 0.05 | -3.66 | -3.66 | -2.95 | -2.95 |

### neutral_v2_rank Loss Risk Flags

| key | samples | share | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
