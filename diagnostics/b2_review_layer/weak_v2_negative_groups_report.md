# Weak V2 Negative Groups Report

- scope: env=weak, verdict in PASS/WATCH, daily weak_v2_rank topN negative samples
- diagnosis: Traces remaining weak_v2 ranked losers so weak-specific veto/risk candidates can be evaluated before changing production review.

## Daily Weak V2 Top3 Negatives

- selected_samples: 75
- ret3>=5 samples: 18
- ret3<=0 samples: 40
- negative_ret3_mean: -6.95
- negative_ret3_median: -7.13

### Family Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| other | 32 | 0.8 | 0 | 32 | 0.0 | 1.0 | -7.0 | -7.38 | -8.39 | -8.98 |
| W-B | 4 | 0.1 | 0 | 4 | 0.0 | 1.0 | -5.46 | -3.64 | -8.13 | -5.51 |
| W-A | 3 | 0.075 | 0 | 3 | 0.0 | 1.0 | -6.51 | -5.93 | -5.73 | -4.67 |
| W-D | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -12.89 | -12.89 | -12.41 | -12.41 |

### Factor Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 4 | 0.1 | 0 | 4 | 0.0 | 1.0 | -5.46 | -3.64 | -8.13 | -5.51 |
| weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.075 | 0 | 3 | 0.0 | 1.0 | -5.75 | -5.93 | -5.92 | -5.24 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.05 | 0 | 2 | 0.0 | 1.0 | -12.23 | -12.23 | -10.54 | -10.54 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 2 | 0.05 | 0 | 2 | 0.0 | 1.0 | -5.7 | -5.7 | -1.88 | -1.88 |
| weak\|B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.15 | -2.15 | -7.27 | -7.27 |
| weak\|B2\|trend_start\|price=middle\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -10.98 | -10.98 | -12.34 | -12.34 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -11.26 | -11.26 | -3.34 | -3.34 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=wide\|volume=normal\|kdj=rising | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -4.51 | -4.51 | -9.41 | -9.41 |
| weak\|B2\|trend_start\|price=near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -12.44 | -12.44 | -9.24 | -9.24 |
| weak\|B2\|trend_start\|price=near_high\|midline=pullback_confirm\|support=bull_stack\|compression=wide\|volume=expanding\|kdj=rising | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -9.23 | -9.23 | -12.24 | -12.24 |
| weak\|B2\|trend_start\|price=near_high\|midline=reclaim_volume\|support=bull_stack\|compression=wide\|volume=expanding\|kdj=rising | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -8.77 | -8.77 | -6.1 | -6.1 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=repair_from_low | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -8.52 | -8.52 | -18.78 | -18.78 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -6.9 | -6.9 | -12.76 | -12.76 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -7.53 | -7.53 | -14.12 | -14.12 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.7 | -2.7 | -8.73 | -8.73 |
| weak\|B2\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -9.42 | -9.42 | -9.25 | -9.25 |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=low | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.32 | -2.32 | -5.18 | -5.18 |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -4.34 | -4.34 | -1.82 | -1.82 |
| weak\|B3\|rebound\|price=extended_or_unknown\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=rising | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -0.73 | -0.73 | 3.93 | 3.93 |
| weak\|B3\|rebound\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -6.31 | -6.31 | -5.05 | -5.05 |

### Condition Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B3\|trend_start\|upper\|normal\|rising\|red_expanding\|price_up_turnover_not | 4 | 0.1 | 0 | 4 | 0.0 | 1.0 | -5.46 | -3.64 | -8.13 | -5.51 |
| B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise | 2 | 0.05 | 0 | 2 | 0.0 | 1.0 | -9.0 | -9.0 | -9.17 | -9.17 |
| B2\|trend_start\|upper\|normal\|low\|green_or_zero\|price_turnover_rise | 2 | 0.05 | 0 | 2 | 0.0 | 1.0 | -5.7 | -5.7 | -1.88 | -1.88 |
| B3\|rebound\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not | 2 | 0.05 | 0 | 2 | 0.0 | 1.0 | -6.92 | -6.92 | -6.25 | -6.25 |
| B2\|trend_start\|extended_or_unknown\|normal\|neutral\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -12.89 | -12.89 | -12.41 | -12.41 |
| B2\|trend_start\|extended_or_unknown\|normal\|neutral\|red_expanding\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -11.58 | -11.58 | -8.68 | -8.68 |
| B2\|trend_start\|middle\|expanding\|rising\|red_expanding\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -10.98 | -10.98 | -12.34 | -12.34 |
| B2\|trend_start\|middle\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.15 | -2.15 | -7.27 | -7.27 |
| B2\|trend_start\|near_high\|expanding\|neutral\|red_expanding\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -12.44 | -12.44 | -9.24 | -9.24 |
| B2\|trend_start\|near_high\|normal\|neutral\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -11.26 | -11.26 | -3.34 | -3.34 |
| B2\|trend_start\|near_high\|normal\|rising\|red_expanding\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -4.51 | -4.51 | -9.41 | -9.41 |
| B2\|trend_start\|upper\|expanding\|low\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.32 | -2.32 | -5.18 | -5.18 |
| B2\|trend_start\|upper\|expanding\|neutral\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -6.9 | -6.9 | -12.76 | -12.76 |
| B2\|trend_start\|upper\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -8.52 | -8.52 | -18.78 | -18.78 |
| B2\|trend_start\|upper\|expanding\|rising\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -7.53 | -7.53 | -14.12 | -14.12 |
| B2\|trend_start\|upper\|expanding\|rising\|red_expanding\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -4.34 | -4.34 | -1.82 | -1.82 |
| B2\|trend_start\|upper\|normal\|neutral\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.7 | -2.7 | -8.73 | -8.73 |
| B2\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -9.42 | -9.42 | -9.25 | -9.25 |
| B3\|rebound\|extended_or_unknown\|normal\|rising\|green_or_zero\|price_up_turnover_not | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -0.73 | -0.73 | 3.93 | 3.93 |
| B3\|rebound\|middle\|normal\|repair_from_low\|green_or_zero\|mixed | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -6.31 | -6.31 | -5.05 | -5.05 |

### Risk Flag Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |

### MACD Wave Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:2:背离\|D:rising:2:背离 | 3 | 0.075 | 0 | 3 | 0.0 | 1.0 | -5.87 | -4.51 | -5.78 | -6.1 |
| W:rising:3:背离\|D:falling:4:修复 | 2 | 0.05 | 0 | 2 | 0.0 | 1.0 | -3.37 | -3.37 | -8.62 | -8.62 |
| W:falling:2:金叉临近\|D:rising:2:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -4.74 | -4.74 | -10.0 | -10.0 |
| W:falling:4:修复\|D:falling:2:修复 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.8 | -2.8 | -5.75 | -5.75 |
| W:idle:0:等待启动\|D:rising:2:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -7.92 | -7.92 | -15.59 | -15.59 |
| W:idle:0:等待启动\|D:rising:3:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -12.75 | -12.75 | -18.1 | -18.1 |
| W:rising:0:强势转分歧\|D:rising:2:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -6.36 | -6.36 | -9.64 | -9.64 |
| W:rising:0:背离\|D:falling:2:修复 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -11.57 | -11.57 | -12.31 | -12.31 |
| W:rising:0:背离\|D:falling:8:修复 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -12.89 | -12.89 | -12.41 | -12.41 |
| W:rising:0:背离\|D:rising:4:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -9.23 | -9.23 | -12.24 | -12.24 |
| W:rising:1:强势\|D:falling:4:修复 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -6.31 | -6.31 | -5.05 | -5.05 |
| W:rising:1:强势转分歧\|D:falling:4:修复 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -7.98 | -7.98 | -10.18 | -10.18 |
| W:rising:1:背离\|D:rising:2:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -5.68 | -5.68 | -4.67 | -4.67 |
| W:rising:1:背离\|D:rising:5:强势转分歧 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -11.58 | -11.58 | -8.68 | -8.68 |
| W:rising:2:强势\|D:falling:2:修复 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -2.32 | -2.32 | -5.18 | -5.18 |
| W:rising:2:强势\|D:falling:2:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -4.02 | -4.02 | 4.82 | 4.82 |
| W:rising:2:强势\|D:rising:2:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -12.44 | -12.44 | -9.24 | -9.24 |
| W:rising:2:背离\|D:falling:2:修复 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -8.52 | -8.52 | -18.78 | -18.78 |
| W:rising:2:背离\|D:rising:3:分歧 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -7.87 | -7.87 | -20.06 | -20.06 |
| W:rising:2:背离\|D:rising:4:背离 | 1 | 0.025 | 0 | 1 | 0.0 | 1.0 | -0.91 | -0.91 | 0.09 | 0.09 |

### Worst Samples

| date | rank | code | verdict | family | score | weak_v2_score | ret3 | ret5 | signal | signal_type | condition | risk_flags |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 2026-04-07 | 3 | 300720.SZ | WATCH | other | 3.63 | 3.63 | -15.77 | -11.03 | B3 | rebound | B3\|rebound\|upper\|shrinking\|low\|green_or_zero\|mixed |  |
| 2026-03-16 | 1 | 002356.SZ | WATCH | W-B | 3.91 | 4.07 | -14.19 | -21.62 | B3 | trend_start | B3\|trend_start\|upper\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-04-01 | 1 | 300895.SZ | WATCH | W-D | 3.84 | 3.94 | -12.89 | -12.41 | B2 | trend_start | B2\|trend_start\|extended_or_unknown\|normal\|neutral\|green_or_zero\|price_turnover_rise |  |
| 2026-03-17 | 2 | 920403.BJ | WATCH | other | 3.96 | 3.96 | -12.75 | -18.1 | B3 | trend_start | B3\|trend_start\|middle\|normal\|rising\|red_expanding\|mixed |  |
| 2026-03-18 | 1 | 688319.SH | WATCH | other | 4.03 | 4.03 | -12.44 | -9.24 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|neutral\|red_expanding\|price_turnover_rise |  |
| 2026-03-18 | 2 | 002202.SZ | WATCH | other | 4.02 | 4.02 | -11.58 | -8.68 | B2 | trend_start | B2\|trend_start\|extended_or_unknown\|normal\|neutral\|red_expanding\|price_turnover_rise |  |
| 2026-03-12 | 2 | 002361.SZ | WATCH | other | 3.98 | 3.98 | -11.57 | -12.31 | B3 | trend_start | B3\|trend_start\|extended_or_unknown\|expanding\|rising\|green_or_zero\|price_up_turnover_not |  |
| 2026-03-18 | 3 | 688517.SH | WATCH | other | 3.93 | 3.93 | -11.26 | -3.34 | B2 | trend_start | B2\|trend_start\|near_high\|normal\|neutral\|green_or_zero\|price_turnover_rise |  |
| 2026-03-04 | 2 | 000798.SZ | WATCH | other | 3.91 | 3.91 | -10.98 | -12.34 | B2 | trend_start | B2\|trend_start\|middle\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-03-27 | 1 | 300736.SZ | WATCH | other | 4.04 | 4.04 | -10.91 | -12.83 | B3 | trend_start | B3\|trend_start\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-26 | 2 | 300072.SZ | WATCH | other | 3.94 | 3.94 | -9.42 | -9.25 | B2 | trend_start | B2\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise |  |
| 2026-03-23 | 1 | 300345.SZ | WATCH | other | 4.03 | 4.03 | -9.23 | -12.24 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-03-05 | 2 | 300389.SZ | WATCH | other | 4.03 | 4.03 | -8.77 | -6.1 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-03-12 | 3 | 603612.SH | WATCH | other | 3.94 | 3.94 | -8.52 | -18.78 | B2 | trend_start | B2\|trend_start\|upper\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise |  |
| 2026-03-13 | 3 | 600740.SH | WATCH | other | 3.81 | 3.81 | -7.98 | -10.18 | B3 | trend_start | B3\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_up_turnover_not |  |
| 2026-03-25 | 2 | 001289.SZ | WATCH | W-A | 3.76 | 4.06 | -7.92 | -15.59 | B3 | rebound | B3\|rebound\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-24 | 1 | 300080.SZ | WATCH | other | 3.99 | 3.99 | -7.87 | -20.06 | B3 | rebound | B3\|rebound\|upper\|normal\|neutral\|red_expanding\|mixed |  |
| 2026-03-12 | 1 | 601388.SH | WATCH | other | 4.0 | 4.0 | -7.53 | -14.12 | B2 | trend_start | B2\|trend_start\|upper\|expanding\|rising\|green_or_zero\|price_turnover_rise |  |
| 2026-03-11 | 2 | 603601.SH | WATCH | other | 4.01 | 4.01 | -7.39 | -5.46 | B3 | trend_start | B3\|trend_start\|upper\|expanding\|repair_from_low\|green_or_zero\|price_up_turnover_not |  |
| 2026-03-17 | 3 | 300393.SZ | WATCH | other | 3.87 | 3.87 | -7.37 | -8.57 | B2 | trend_start | B2\|trend_start\|upper\|normal\|low\|green_or_zero\|price_turnover_rise |  |
| 2026-03-23 | 2 | 002506.SZ | WATCH | other | 3.93 | 3.93 | -6.9 | -12.76 | B2 | trend_start | B2\|trend_start\|upper\|expanding\|neutral\|green_or_zero\|price_turnover_rise |  |
| 2026-03-09 | 1 | 688118.SH | WATCH | W-B | 4.08 | 4.24 | -6.36 | -9.64 | B3 | trend_start | B3\|trend_start\|upper\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-30 | 2 | 000912.SZ | WATCH | other | 3.9 | 3.9 | -6.31 | -5.05 | B3 | rebound | B3\|rebound\|middle\|normal\|repair_from_low\|green_or_zero\|mixed |  |
| 2026-03-31 | 1 | 603211.SH | WATCH | W-A | 3.59 | 3.89 | -5.93 | 3.08 | B3 | rebound | B3\|rebound\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-17 | 1 | 688628.SH | WATCH | W-A | 3.74 | 4.04 | -5.68 | -4.67 | B3 | rebound | B3\|rebound\|near_high\|expanding\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-13 | 2 | 601011.SH | WATCH | other | 3.89 | 3.89 | -4.74 | -10.0 | B3 | rebound | B3\|rebound\|near_low\|normal\|repair_from_low\|red_expanding\|mixed |  |
| 2026-03-19 | 1 | 002897.SZ | WATCH | other | 4.0 | 4.0 | -4.58 | -9.97 | B3 | trend_start | B3\|trend_start\|upper\|normal\|low\|green_or_zero\|mixed |  |
| 2026-04-07 | 2 | 300651.SZ | WATCH | other | 3.8 | 3.8 | -4.51 | -9.41 | B2 | trend_start | B2\|trend_start\|near_high\|normal\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-03-19 | 3 | 300332.SZ | WATCH | other | 3.92 | 3.92 | -4.34 | -1.82 | B2 | trend_start | B2\|trend_start\|upper\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-04-01 | 3 | 603803.SH | WATCH | other | 3.86 | 3.86 | -4.02 | 4.82 | B2 | trend_start | B2\|trend_start\|upper\|normal\|low\|green_or_zero\|price_turnover_rise |  |

## Daily Weak V2 Top5 Negatives

- selected_samples: 125
- ret3>=5 samples: 30
- ret3<=0 samples: 67
- negative_ret3_mean: -6.63
- negative_ret3_median: -6.36

### Family Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| other | 56 | 0.836 | 0 | 56 | 0.0 | 1.0 | -6.66 | -6.78 | -8.12 | -8.71 |
| W-B | 5 | 0.075 | 0 | 5 | 0.0 | 1.0 | -4.65 | -1.45 | -8.19 | -8.39 |
| W-A | 3 | 0.045 | 0 | 3 | 0.0 | 1.0 | -6.51 | -5.93 | -5.73 | -4.67 |
| W-C | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -7.64 | -7.64 | -10.55 | -10.55 |
| W-D | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -12.89 | -12.89 | -12.41 | -12.41 |

### Factor Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 5 | 0.075 | 0 | 5 | 0.0 | 1.0 | -4.65 | -1.45 | -8.19 | -8.39 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 4 | 0.06 | 0 | 4 | 0.0 | 1.0 | -5.2 | -4.89 | -1.86 | -2.05 |
| weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.045 | 0 | 3 | 0.0 | 1.0 | -5.75 | -5.93 | -5.92 | -5.24 |
| weak\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 3 | 0.045 | 0 | 3 | 0.0 | 1.0 | -13.03 | -13.82 | -18.05 | -16.29 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -4.58 | -4.58 | 4.34 | 4.34 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -12.23 | -12.23 | -10.54 | -10.54 |
| weak\|B2\|trend_start\|price=near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -7.64 | -7.64 | -10.55 | -10.55 |
| weak\|B2\|trend_start\|price=near_high\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -7.33 | -7.33 | -11.92 | -11.92 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -5.7 | -5.7 | -1.88 | -1.88 |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -5.04 | -5.04 | -8.7 | -8.7 |
| weak\|B2\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -5.82 | -5.82 | -10.83 | -10.83 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -7.53 | -7.53 | -14.43 | -14.43 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -1.59 | -1.59 | 0.23 | 0.23 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -1.85 | -1.85 | -3.23 | -3.23 |
| weak\|B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -2.15 | -2.15 | -7.27 | -7.27 |
| weak\|B2\|trend_start\|price=middle\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -10.98 | -10.98 | -12.34 | -12.34 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -5.16 | -5.16 | -5.51 | -5.51 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -11.26 | -11.26 | -3.34 | -3.34 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=wide\|volume=normal\|kdj=rising | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -4.51 | -4.51 | -9.41 | -9.41 |
| weak\|B2\|trend_start\|price=near_high\|midline=pullback_confirm\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -12.44 | -12.44 | -9.24 | -9.24 |

### Condition Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise | 4 | 0.06 | 0 | 4 | 0.0 | 1.0 | -8.48 | -9.0 | -10.17 | -9.52 |
| B3\|trend_start\|upper\|normal\|rising\|red_expanding\|price_up_turnover_not | 4 | 0.06 | 0 | 4 | 0.0 | 1.0 | -5.46 | -3.64 | -8.13 | -5.51 |
| B2\|trend_start\|upper\|normal\|neutral\|red_expanding\|price_turnover_rise | 3 | 0.045 | 0 | 3 | 0.0 | 1.0 | -4.51 | -5.17 | -1.33 | -1.02 |
| B2\|trend_start\|extended_or_unknown\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -4.58 | -4.58 | 4.34 | 4.34 |
| B2\|trend_start\|near_high\|expanding\|neutral\|red_expanding\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -8.8 | -8.8 | -7.38 | -7.38 |
| B2\|trend_start\|near_high\|expanding\|rising\|green_or_zero\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -7.01 | -7.01 | -11.3 | -11.3 |
| B2\|trend_start\|upper\|expanding\|rising\|green_or_zero\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -6.64 | -6.64 | -14.85 | -14.85 |
| B2\|trend_start\|upper\|expanding\|rising\|red_expanding\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -2.79 | -2.79 | -1.92 | -1.92 |
| B2\|trend_start\|upper\|normal\|low\|green_or_zero\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -5.7 | -5.7 | -1.88 | -1.88 |
| B2\|trend_start\|upper\|normal\|neutral\|green_or_zero\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -3.66 | -3.66 | -2.24 | -2.24 |
| B2\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -7.87 | -7.87 | -9.25 | -9.25 |
| B3\|rebound\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -6.92 | -6.92 | -6.25 | -6.25 |
| B2\|rebound\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -5.82 | -5.82 | -10.83 | -10.83 |
| B2\|trend_start\|extended_or_unknown\|expanding\|neutral\|green_or_zero\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -7.53 | -7.53 | -14.43 | -14.43 |
| B2\|trend_start\|extended_or_unknown\|expanding\|rising\|red_expanding\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -1.85 | -1.85 | -3.23 | -3.23 |
| B2\|trend_start\|extended_or_unknown\|normal\|low\|green_or_zero\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -1.59 | -1.59 | 0.23 | 0.23 |
| B2\|trend_start\|extended_or_unknown\|normal\|neutral\|green_or_zero\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -12.89 | -12.89 | -12.41 | -12.41 |
| B2\|trend_start\|extended_or_unknown\|normal\|neutral\|red_expanding\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -11.58 | -11.58 | -8.68 | -8.68 |
| B2\|trend_start\|middle\|expanding\|rising\|red_expanding\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -10.98 | -10.98 | -12.34 | -12.34 |
| B2\|trend_start\|middle\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -2.15 | -2.15 | -7.27 | -7.27 |

### Risk Flag Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |

### MACD Wave Distribution

| key | samples | share | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:2:背离\|D:rising:2:背离 | 3 | 0.045 | 0 | 3 | 0.0 | 1.0 | -5.87 | -4.51 | -5.78 | -6.1 |
| W:rising:3:强势转分歧\|D:falling:4:修复 | 3 | 0.045 | 0 | 3 | 0.0 | 1.0 | -6.6 | -7.87 | -10.54 | -10.97 |
| W:rising:3:背离\|D:falling:4:修复 | 3 | 0.045 | 0 | 3 | 0.0 | 1.0 | -2.38 | -2.15 | -8.62 | -8.62 |
| W:rising:1:背离\|D:falling:4:修复 | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -4.34 | -4.34 | -4.84 | -4.84 |
| W:rising:3:背离\|D:falling:2:修复 | 2 | 0.03 | 0 | 2 | 0.0 | 1.0 | -4.49 | -4.49 | -11.25 | -11.25 |
| W:falling:2:金叉临近\|D:rising:2:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -4.74 | -4.74 | -10.0 | -10.0 |
| W:falling:4:修复\|D:falling:2:修复 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -2.8 | -2.8 | -5.75 | -5.75 |
| W:idle:0:等待启动\|D:falling:2:修复 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -6.31 | -6.31 | None | None |
| W:idle:0:等待启动\|D:falling:2:金叉临近 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -8.65 | -8.65 | -17.05 | -17.05 |
| W:idle:0:等待启动\|D:rising:2:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -7.92 | -7.92 | -15.59 | -15.59 |
| W:idle:0:等待启动\|D:rising:3:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -12.75 | -12.75 | -18.1 | -18.1 |
| W:rising:0:强势\|D:rising:2:强势 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -5.16 | -5.16 | -5.51 | -5.51 |
| W:rising:0:强势\|D:rising:2:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -1.23 | -1.23 | -2.01 | -2.01 |
| W:rising:0:强势转分歧\|D:rising:2:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -6.36 | -6.36 | -9.64 | -9.64 |
| W:rising:0:强势转分歧\|D:rising:6:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -8.29 | -8.29 | -8.37 | -8.37 |
| W:rising:0:背离\|D:falling:0:修复 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -5.75 | -5.75 | -15.58 | -15.58 |
| W:rising:0:背离\|D:falling:2:修复 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -11.57 | -11.57 | -12.31 | -12.31 |
| W:rising:0:背离\|D:falling:8:修复 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -12.89 | -12.89 | -12.41 | -12.41 |
| W:rising:0:背离\|D:rising:2:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -2.1 | -2.1 | -4.68 | -4.68 |
| W:rising:0:背离\|D:rising:4:背离 | 1 | 0.015 | 0 | 1 | 0.0 | 1.0 | -9.23 | -9.23 | -12.24 | -12.24 |

### Worst Samples

| date | rank | code | verdict | family | score | weak_v2_score | ret3 | ret5 | signal | signal_type | condition | risk_flags |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 2026-04-07 | 3 | 300720.SZ | WATCH | other | 3.63 | 3.63 | -15.77 | -11.03 | B3 | rebound | B3\|rebound\|upper\|shrinking\|low\|green_or_zero\|mixed |  |
| 2026-03-13 | 5 | 603612.SH | WATCH | other | 3.68 | 3.68 | -15.11 | -21.76 | B3 | rebound | B3\|rebound\|upper\|normal\|rising\|green_or_zero\|price_up_turnover_not |  |
| 2026-03-16 | 1 | 002356.SZ | WATCH | W-B | 3.91 | 4.07 | -14.19 | -21.62 | B3 | trend_start | B3\|trend_start\|upper\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-12 | 5 | 301518.SZ | WATCH | other | 3.85 | 3.85 | -13.82 | -16.29 | B3 | rebound | B3\|rebound\|upper\|normal\|rising\|red_expanding\|mixed |  |
| 2026-04-01 | 1 | 300895.SZ | WATCH | W-D | 3.84 | 3.94 | -12.89 | -12.41 | B2 | trend_start | B2\|trend_start\|extended_or_unknown\|normal\|neutral\|green_or_zero\|price_turnover_rise |  |
| 2026-03-17 | 2 | 920403.BJ | WATCH | other | 3.96 | 3.96 | -12.75 | -18.1 | B3 | trend_start | B3\|trend_start\|middle\|normal\|rising\|red_expanding\|mixed |  |
| 2026-03-18 | 1 | 688319.SH | WATCH | other | 4.03 | 4.03 | -12.44 | -9.24 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|neutral\|red_expanding\|price_turnover_rise |  |
| 2026-03-18 | 2 | 002202.SZ | WATCH | other | 4.02 | 4.02 | -11.58 | -8.68 | B2 | trend_start | B2\|trend_start\|extended_or_unknown\|normal\|neutral\|red_expanding\|price_turnover_rise |  |
| 2026-03-12 | 2 | 002361.SZ | WATCH | other | 3.98 | 3.98 | -11.57 | -12.31 | B3 | trend_start | B3\|trend_start\|extended_or_unknown\|expanding\|rising\|green_or_zero\|price_up_turnover_not |  |
| 2026-03-18 | 3 | 688517.SH | WATCH | other | 3.93 | 3.93 | -11.26 | -3.34 | B2 | trend_start | B2\|trend_start\|near_high\|normal\|neutral\|green_or_zero\|price_turnover_rise |  |
| 2026-03-04 | 2 | 000798.SZ | WATCH | other | 3.91 | 3.91 | -10.98 | -12.34 | B2 | trend_start | B2\|trend_start\|middle\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-03-27 | 1 | 300736.SZ | WATCH | other | 4.04 | 4.04 | -10.91 | -12.83 | B3 | trend_start | B3\|trend_start\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-27 | 5 | 300072.SZ | WATCH | other | 3.83 | 3.83 | -10.16 | -16.11 | B3 | rebound | B3\|rebound\|upper\|normal\|rising\|green_or_zero\|mixed |  |
| 2026-03-12 | 4 | 601038.SH | WATCH | W-C | 3.67 | 3.86 | -9.92 | -15.55 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-03-26 | 2 | 300072.SZ | WATCH | other | 3.94 | 3.94 | -9.42 | -9.25 | B2 | trend_start | B2\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_turnover_rise |  |
| 2026-03-26 | 4 | 688021.SH | WATCH | other | 3.9 | 3.9 | -9.24 | -11.93 | B3 | rebound | B3\|rebound\|upper\|normal\|repair_from_low\|green_or_zero\|mixed |  |
| 2026-03-23 | 1 | 300345.SZ | WATCH | other | 4.03 | 4.03 | -9.23 | -12.24 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-03-05 | 2 | 300389.SZ | WATCH | other | 4.03 | 4.03 | -8.77 | -6.1 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|rising\|red_expanding\|price_turnover_rise |  |
| 2026-04-01 | 4 | 688158.SH | WATCH | other | 3.84 | 3.84 | -8.75 | 4.34 | B2 | trend_start | B2\|trend_start\|extended_or_unknown\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise |  |
| 2026-03-16 | 5 | 002724.SZ | WATCH | other | 3.84 | 3.84 | -8.65 | -17.05 | B2 | trend_start | B2\|trend_start\|near_high\|expanding\|rising\|green_or_zero\|price_turnover_rise |  |
| 2026-03-12 | 3 | 603612.SH | WATCH | other | 3.94 | 3.94 | -8.52 | -18.78 | B2 | trend_start | B2\|trend_start\|upper\|expanding\|repair_from_low\|green_or_zero\|price_turnover_rise |  |
| 2026-03-18 | 5 | 688158.SH | WATCH | other | 3.89 | 3.89 | -8.29 | -8.37 | B2 | trend_start | B2\|trend_start\|upper\|normal\|neutral\|red_expanding\|price_turnover_rise |  |
| 2026-03-13 | 3 | 600740.SH | WATCH | other | 3.81 | 3.81 | -7.98 | -10.18 | B3 | trend_start | B3\|trend_start\|upper\|normal\|repair_from_low\|green_or_zero\|price_up_turnover_not |  |
| 2026-03-25 | 2 | 001289.SZ | WATCH | W-A | 3.76 | 4.06 | -7.92 | -15.59 | B3 | rebound | B3\|rebound\|near_high\|normal\|rising\|red_expanding\|price_up_turnover_not |  |
| 2026-03-24 | 1 | 300080.SZ | WATCH | other | 3.99 | 3.99 | -7.87 | -20.06 | B3 | rebound | B3\|rebound\|upper\|normal\|neutral\|red_expanding\|mixed |  |
| 2026-03-24 | 5 | 601975.SH | WATCH | other | 3.86 | 3.86 | -7.87 | -10.97 | B2 | trend_start | B2\|trend_start\|upper\|normal\|rising\|green_or_zero\|price_turnover_rise |  |
| 2026-03-12 | 1 | 601388.SH | WATCH | other | 4.0 | 4.0 | -7.53 | -14.12 | B2 | trend_start | B2\|trend_start\|upper\|expanding\|rising\|green_or_zero\|price_turnover_rise |  |
| 2026-03-19 | 4 | 300164.SZ | WATCH | other | 3.87 | 3.87 | -7.53 | -14.43 | B2 | trend_start | B2\|trend_start\|extended_or_unknown\|expanding\|neutral\|green_or_zero\|price_turnover_rise |  |
| 2026-03-11 | 2 | 603601.SH | WATCH | other | 4.01 | 4.01 | -7.39 | -5.46 | B3 | trend_start | B3\|trend_start\|upper\|expanding\|repair_from_low\|green_or_zero\|price_up_turnover_not |  |
| 2026-03-17 | 3 | 300393.SZ | WATCH | other | 3.87 | 3.87 | -7.37 | -8.57 | B2 | trend_start | B2\|trend_start\|upper\|normal\|low\|green_or_zero\|price_turnover_rise |  |
