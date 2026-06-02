# Weak WATCH Positive Report

- scope: env=weak and current_verdict=WATCH
- sample_count: 1065
- ret3>0: 439 (0.412)
- ret5>0: 401 (0.377)
- ret3>=5: 172 (0.162)
- ret3<=0: 602 (0.565)

## Candidate Guidance

- 只作为 weak WATCH -> PASS 的离线候选池，不改生产 verdict。
- 优先看 ret3>0 与 ret5>0 同时稳定、ret3>=5 数量明显多于 ret3<=0 的组合。
- BBI/BIAS/OBV 只作为 family 内排序增强或二级确认，不单独作为 PASS 放行条件。
- 命中 veto_candidates 的组合先保留 WATCH 或降权，等更多样本验证后再讨论放行。

## Return Groups

| group | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ret3_gt_0 | 439 | 439 | 300 | 172 | 0 | 5.76 | 4.75 |
| ret5_gt_0 | 401 | 300 | 401 | 153 | 101 | 4.41 | 6.91 |
| ret3_ge_5 | 172 | 172 | 153 | 172 | 0 | 11.52 | 10.01 |
| ret3_le_0 | 602 | 0 | 101 | 0 | 602 | -5.68 | -6.4 |

## Upgrade Candidates

| condition | key | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | examples |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| family_indicator | W-A\|bbi=above_extended\|bias=positive\|obv=flat | 8 | 6 | 3 | 3 | 1 | 3.16 | 1.62 | 688253.SH,600773.SH,301555.SZ,000682.SZ,688178.SH |
| factor | weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 10 | 6 | 5 | 4 | 3 | 3.3 | 5.98 | 300672.SZ,688253.SH,301176.SZ,300209.SZ,600872.SH |

## Veto / Risk Candidates

| flag | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | examples |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| b2_extended_neutral_macd_bad | 13 | 3 | 6 | 0.462 | -0.66 | 688158.SH,300209.SZ,603353.SH,688143.SH,300936.SZ |
| b3_trend_red_macd_bad | 14 | 4 | 7 | 0.5 | 0.27 | 300932.SZ,688330.SH,301200.SZ,300259.SZ,301299.SZ |
| b3_rebound_upper_red_mixed | 9 | 1 | 5 | 0.556 | -2.55 | 688268.SH,688226.SH,601187.SH,301303.SZ,002221.SZ |
| b2_upper_expanding_neutral_red | 12 | 1 | 8 | 0.667 | -2.87 | 300335.SZ,688337.SH,300669.SZ,688662.SH,601139.SH |
| b2_near_high_normal_rising_no_red | 15 | 0 | 10 | 0.667 | -1.12 | 600137.SH,603183.SH,002637.SZ,002687.SZ,002802.SZ |
| b3_rebound_extended_mixed | 11 | 0 | 10 | 0.909 | -5.06 | 300620.SZ,688167.SH,603619.SH,600330.SH,002378.SZ |
| b2_mid_near_expanding_red_macd_bad | 28 | 4 | 15 | 0.536 | -0.52 | 301396.SZ,300243.SZ,301516.SZ,300868.SZ,600475.SH |
| b3_rebound_upper_no_red | 33 | 3 | 18 | 0.545 | -1.9 | 300246.SZ,301179.SZ,600667.SH,688335.SH,000823.SZ |
| macd_w2_div_d4_repair | 16 | 0 | 15 | 0.938 | -3.97 | 000823.SZ,300030.SZ,301132.SZ,002971.SZ,000021.SZ |
| macd_w0_div_d4_repair | 32 | 2 | 24 | 0.75 | -5.58 | 301268.SZ,301268.SZ,300936.SZ,600590.SH,300936.SZ |

## Negative Condition Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|family=other\|price=middle\|midline=reclaim_volume\|volume=expanding\|kdj=rising\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -10.98 | -12.34 |
| B3\|rebound\|family=other\|price=upper\|midline=above_hold\|volume=expanding\|kdj=rising\|hist=red_contracting\|turnover=mixed | 1 | 0 | 1 | 1.0 | -12.02 | -6.82 |
| B2\|trend_start\|family=other\|price=upper\|midline=pullback_confirm\|volume=shrinking\|kdj=neutral\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.56 | 2.37 |
| B2\|rebound\|family=other\|price=upper\|midline=below_midline\|volume=expanding\|kdj=neutral\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -1.14 | -0.45 |
| B2\|trend_start\|family=other\|price=middle\|midline=above_hold\|volume=shrinking\|kdj=neutral\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -6.2 | -14.67 |
| B2\|rebound\|family=other\|price=extended_or_unknown\|midline=above_hold\|volume=expanding\|kdj=rising\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -3.53 | -8.84 |
| B2\|rebound\|family=other\|price=extended_or_unknown\|midline=pullback_confirm\|volume=expanding\|kdj=low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -1.64 | -6.87 |
| B2\|trend_start\|family=other\|price=middle\|midline=above_hold\|volume=shrinking\|kdj=low\|hist=red_contracting\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -6.41 | -11.75 |
| B2\|trend_start\|family=other\|price=upper\|midline=above_hold\|volume=shrinking\|kdj=neutral\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -0.63 | 5.62 |
| B2\|rebound\|family=other\|price=upper\|midline=above_hold\|volume=expanding\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -4.08 | -8.71 |
| B2\|trend_start\|family=other\|price=middle\|midline=reclaim_volume\|volume=expanding\|kdj=low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.65 | -6.51 |
| B2\|trend_start\|family=other\|price=extended_or_unknown\|midline=pullback_confirm\|volume=normal\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.29 | 4.5 |
| B2\|trend_start\|family=other\|price=near_high\|midline=above_hold\|volume=normal\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.49 | -4.97 |
| B2\|rebound\|family=other\|price=upper\|midline=below_midline\|volume=normal\|kdj=low\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -1.69 | -1.69 |
| B2\|trend_start\|family=other\|price=upper\|midline=pullback_confirm\|volume=shrinking\|kdj=low\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -3.02 | -5.55 |
| B2\|rebound\|family=other\|price=upper\|midline=below_midline\|volume=expanding\|kdj=rising\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -4.99 | -3.94 |
| B2\|rebound\|family=other\|price=upper\|midline=above_hold\|volume=normal\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | 0.0 | 7.17 |
| B3\|rebound\|family=other\|price=near_high\|midline=above_hold\|volume=shrinking\|kdj=rising\|hist=red_expanding\|turnover=mixed | 1 | 0 | 1 | 1.0 | -0.32 | -4.32 |
| B2\|trend_start\|family=other\|price=upper\|midline=pullback_confirm\|volume=normal\|kdj=repair_from_low\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.42 | 4.64 |
| B2\|rebound\|family=other\|price=near_high\|midline=above_hold\|volume=normal\|kdj=neutral\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -3.82 | -9.14 |

## Negative Family + Indicator Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W-B\|bbi=above_extended\|bias=neutral\|obv=rising | 1 | 0 | 1 | 1.0 | -0.91 | 0.09 |
| other\|bbi=above\|bias=negative\|obv=flat | 1 | 0 | 1 | 1.0 | -6.41 | -11.75 |
| W-B\|bbi=above_extended\|bias=neutral\|obv=flat | 1 | 0 | 1 | 1.0 | -0.36 | -1.37 |
| W-B\|bbi=above\|bias=positive\|obv=flat | 1 | 0 | 1 | 1.0 | -4.97 | -6.5 |
| W-A\|bbi=above_extended\|bias=positive\|obv=flat | 1 | 0 | 1 | 1.0 | -3.89 | -5.58 |
| other\|bbi=below_near\|bias=positive\|obv=flat | 1 | 0 | 1 | 1.0 | -5.97 | -8.21 |
| W-C\|bbi=above_extended\|bias=high_positive\|obv=flat | 1 | 0 | 1 | 1.0 | -7.15 | -3.45 |
| W-C\|bbi=above\|bias=neutral\|obv=flat | 1 | 0 | 1 | 1.0 | -9.42 | -4.48 |
| W-D\|bbi=below_near\|bias=neutral\|obv=flat | 1 | 0 | 1 | 1.0 | -17.1 | -13.21 |
| W-D\|bbi=above\|bias=neutral\|obv=flat | 1 | 0 | 1 | 1.0 | -17.04 | -5.31 |
| other\|bbi=below_near\|bias=neutral\|obv=rising | 1 | 0 | 1 | 1.0 | -4.26 | -4.36 |
| other\|bbi=below_deep\|bias=neutral\|obv=rising | 1 | 0 | 1 | 1.0 | -0.68 | -2.93 |
| W-B\|bbi=above\|bias=neutral\|obv=flat | 1 | 0 | 1 | 1.0 | -3.05 | -1.64 |
| other\|bbi=below_near\|bias=neutral\|obv=falling | 1 | 0 | 1 | 1.0 | -1.23 | -3.28 |
| other\|bbi=below_deep\|bias=neutral\|obv=falling | 1 | 0 | 1 | 1.0 | -1.36 | -1.05 |
| W-D\|bbi=above_extended\|bias=positive\|obv=flat | 1 | 0 | 1 | 1.0 | -12.89 | -12.41 |
| other\|bbi=above\|bias=neutral\|obv=falling | 2 | 0 | 2 | 1.0 | -7.55 | -6.93 |
| W-B\|bbi=above_extended\|bias=positive\|obv=rising | 2 | 0 | 2 | 1.0 | -7.82 | -15.01 |
| other\|bbi=above_extended\|bias=positive\|obv=falling | 2 | 0 | 2 | 1.0 | -5.21 | -9.95 |
| other\|bbi=below_near\|bias=negative\|obv=flat | 3 | 0 | 3 | 1.0 | -3.94 | -6.49 |

## Negative MACD Wave Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:6:背离\|D:rising:1:背离 | 1 | 0 | 1 | 1.0 | -10.98 | -12.34 |
| W:idle:0:等待启动\|D:rising:0:强势 | 1 | 0 | 1 | 1.0 | -2.56 | 2.37 |
| W:rising:3:背离\|D:falling:2:强势 | 1 | 0 | 1 | 1.0 | -0.31 | 5.28 |
| W:rising:4:强势\|D:falling:2:修复 | 1 | 0 | 1 | 1.0 | -6.2 | -14.67 |
| W:rising:2:背离\|D:rising:0:背离 | 1 | 0 | 1 | 1.0 | -6.41 | -11.75 |
| W:rising:6:分歧\|D:falling:4:金叉临近 | 1 | 0 | 1 | 1.0 | 0.0 | 13.75 |
| W:rising:4:分歧\|D:falling:2:金叉临近 | 1 | 0 | 1 | 1.0 | 0.0 | -1.84 |
| W:rising:5:背离\|D:rising:0:背离 | 1 | 0 | 1 | 1.0 | -3.02 | -5.55 |
| W:rising:5:背离\|D:rising:3:背离 | 1 | 0 | 1 | 1.0 | -0.07 | -1.02 |
| W:rising:0:分歧\|D:falling:2:修复 | 1 | 0 | 1 | 1.0 | 0.0 | -1.48 |
| W:rising:4:分歧\|D:rising:3:背离 | 1 | 0 | 1 | 1.0 | -0.36 | -1.37 |
| W:rising:4:背离\|D:rising:0:背离 | 1 | 0 | 1 | 1.0 | -2.82 | -2.99 |
| W:rising:1:分歧\|D:rising:3:分歧 | 1 | 0 | 1 | 1.0 | -4.11 | -7.18 |
| W:rising:0:强势\|D:rising:0:分歧 | 1 | 0 | 1 | 1.0 | -0.96 | -3.35 |
| W:rising:0:背离\|D:rising:1:背离 | 1 | 0 | 1 | 1.0 | -0.65 | -2.54 |
| W:rising:3:背离\|D:rising:3:分歧 | 1 | 0 | 1 | 1.0 | -6.01 | -6.79 |
| W:rising:2:背离\|D:falling:2:金叉临近 | 1 | 0 | 1 | 1.0 | -1.6 | 1.28 |
| W:rising:4:背离\|D:rising:1:背离 | 1 | 0 | 1 | 1.0 | -2.1 | -2.1 |
| W:rising:3:强势\|D:rising:3:背离 | 1 | 0 | 1 | 1.0 | -2.57 | 0.07 |
| W:rising:1:强势\|D:rising:2:背离 | 1 | 0 | 1 | 1.0 | -1.5 | -4.77 |

## Negative Factor Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B2\|trend_start\|price=middle\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0 | 1 | 1.0 | -10.98 | -12.34 |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=wide\|volume=expanding\|kdj=neutral | 1 | 0 | 1 | 1.0 | -0.87 | 1.28 |
| weak\|B2\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=neutral | 1 | 0 | 1 | 1.0 | -2.56 | 2.37 |
| weak\|B2\|rebound\|price=upper\|midline=below_midline\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=neutral | 1 | 0 | 1 | 1.0 | -1.14 | -0.45 |
| weak\|B2\|trend_start\|price=middle\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=neutral | 1 | 0 | 1 | 1.0 | -6.2 | -14.67 |
| weak\|B2\|rebound\|price=extended_or_unknown\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0 | 1 | 1.0 | -3.53 | -8.84 |
| weak\|B2\|rebound\|price=extended_or_unknown\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=low | 1 | 0 | 1 | 1.0 | -1.64 | -6.87 |
| weak\|B2\|trend_start\|price=middle\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=low | 1 | 0 | 1 | 1.0 | -6.41 | -11.75 |
| weak\|B2\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -4.08 | -8.71 |
| weak\|B2\|trend_start\|price=middle\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=low | 1 | 0 | 1 | 1.0 | -2.65 | -6.51 |
| weak\|B2\|trend_start\|price=extended_or_unknown\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -2.29 | 4.5 |
| weak\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -2.49 | -4.97 |
| weak\|B2\|trend_start\|price=near_high\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -0.42 | -0.84 |
| weak\|B2\|rebound\|price=upper\|midline=below_midline\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 1 | 0 | 1 | 1.0 | -1.69 | -1.69 |
| weak\|B3\|rebound\|price=upper\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=rising | 1 | 0 | 1 | 1.0 | 0.0 | -1.84 |
| weak\|B2\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=low | 1 | 0 | 1 | 1.0 | -3.02 | -5.55 |
| weak\|B2\|rebound\|price=upper\|midline=below_midline\|support=bull_stack\|compression=wide\|volume=expanding\|kdj=rising | 1 | 0 | 1 | 1.0 | -4.99 | -3.94 |
| weak\|B2\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=wide\|volume=normal\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | 0.0 | 7.17 |
| weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=rising | 1 | 0 | 1 | 1.0 | -0.32 | -4.32 |
| weak\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0 | 1 | 1.0 | -0.22 | -4.39 |
