# Neutral WATCH Positive Report

- scope: env=neutral and current_verdict=WATCH
- sample_count: 958
- ret3>0: 416 (0.434)
- ret5>0: 353 (0.368)
- ret3>=5: 189 (0.197)
- ret3<=0: 541 (0.565)

## Candidate Guidance

- 只作为 neutral WATCH -> PASS 或 rank_score 的离线候选池，不改生产 verdict。
- 优先验证 B3 trend_start 放量红柱延续、B2 trend_start 近高位紧压缩、B3 rebound 量价确认三类 family。
- neutral 不能复用 weak 的 PASS 放宽结论；需要先比较 ret3>0、ret5>0、ret3>=5 与 ret3<=0 的稳定差异。
- 命中 veto_candidates 的组合先保留 WATCH 或降权。

## Return Groups

| group | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ret3_gt_0 | 416 | 416 | 281 | 189 | 0 | 6.21 | 5.86 |
| ret5_gt_0 | 353 | 281 | 353 | 156 | 72 | 5.45 | 8.62 |
| ret3_ge_5 | 189 | 189 | 156 | 189 | 0 | 10.82 | 11.58 |
| ret3_le_0 | 541 | 0 | 72 | 0 | 541 | -5.73 | -6.91 |

## Upgrade Candidates

| condition | key | samples | ret3>0 | ret5>0 | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | examples |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| condition | B3\|rebound\|family=other\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising\|hist=red_expanding\|turnover=mixed | 8 | 6 | 7 | 3 | 2 | 6.39 | 6.13 | 301157.SZ,002950.SZ,300502.SZ,300866.SZ,002966.SZ |

## Veto / Risk Candidates

| flag | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | examples |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| neutral_b3_rebound_upper_no_red | 34 | 11 | 15 | 0.441 | 1.53 | 002636.SZ,300938.SZ,000690.SZ,300499.SZ,301630.SZ |
| neutral_b3_near_high_turnover_mixed | 9 | 1 | 5 | 0.556 | -0.16 | 301509.SZ,000883.SZ,601077.SH,002960.SZ,300531.SZ |
| neutral_b2_near_high_expanding_macd_bad | 65 | 14 | 34 | 0.523 | 0.07 | 002741.SZ,603989.SH,688055.SH,301329.SZ,300620.SZ |
| neutral_b2_rebound_extended_no_red | 41 | 4 | 27 | 0.659 | -3.54 | 603618.SH,000988.SZ,002498.SZ,001896.SZ,300617.SZ |

## Negative Condition Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start\|family=other\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=repair_from_low\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -1.75 | 6.07 |
| B2\|trend_start\|family=other\|price=near_low\|midline=below_midline\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.35 | -5.62 |
| B2\|rebound\|family=other\|price=middle\|midline=below_midline\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.52 | -6.36 |
| B2\|trend_start\|family=other\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -1.66 | -12.47 |
| B2\|trend_start\|family=other\|price=middle\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising\|hist=red_expanding\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -7.96 | -13.94 |
| B2\|rebound\|family=other\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -1.91 | -2.33 |
| B2\|rebound\|family=other\|price=upper\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=neutral\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -4.01 | -7.39 |
| B2\|rebound\|family=other\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -6.37 | -11.2 |
| B2\|rebound\|family=other\|price=upper\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -4.35 | -4.35 |
| B3\|rebound\|family=N-C\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising\|hist=green_or_zero\|turnover=price_up_turnover_not | 1 | 0 | 1 | 1.0 | -5.85 | -10.08 |
| B2\|trend_start\|family=other\|price=middle\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=rising\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -2.6 | -2.23 |
| B2\|trend_start\|family=other\|price=middle\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -7.7 | -10.53 |
| B2\|rebound\|family=other\|price=upper\|midline=reclaim_volume\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -5.01 | -4.75 |
| B2\|trend_start\|family=other\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -0.73 | -5.2 |
| B2\|trend_start\|family=other\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -3.51 | -15.67 |
| B2\|rebound\|family=other\|price=extended_or_unknown\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=repair_from_low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -4.72 | -11.34 |
| B3\|rebound\|family=other\|price=middle\|midline=below_midline\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low\|hist=green_or_zero\|turnover=mixed | 1 | 0 | 1 | 1.0 | -3.58 | -9.69 |
| B3\|rebound\|family=other\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising\|hist=green_or_zero\|turnover=mixed | 1 | 0 | 1 | 1.0 | -0.92 | 3.05 |
| B2\|rebound\|family=other\|price=middle\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=rising\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -1.9 | -0.99 |
| B2\|rebound\|family=other\|price=middle\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=low\|hist=green_or_zero\|turnover=price_turnover_rise | 1 | 0 | 1 | 1.0 | -9.16 | -19.43 |

## Negative Family Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N-C | 8 | 0 | 8 | 1.0 | -4.17 | -7.19 |
| N-A | 10 | 0 | 10 | 1.0 | -5.01 | -7.39 |
| N-B | 183 | 0 | 183 | 1.0 | -5.72 | -7.71 |
| other | 340 | 0 | 340 | 1.0 | -5.79 | -6.47 |

## Negative MACD Wave Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:3:强势转分歧\|D:rising:4:背离 | 1 | 0 | 1 | 1.0 | -10.33 | -12.22 |
| W:rising:3:背离\|D:falling:4:背离 | 1 | 0 | 1 | 1.0 | -9.17 | -6.24 |
| W:falling:4:修复\|D:rising:4:分歧 | 1 | 0 | 1 | 1.0 | -2.35 | -5.62 |
| W:rising:1:强势\|D:rising:5:分歧 | 1 | 0 | 1 | 1.0 | -6.98 | -16.39 |
| W:rising:3:分歧\|D:rising:3:背离 | 1 | 0 | 1 | 1.0 | -0.68 | -6.12 |
| W:idle:0:等待启动\|D:rising:4:分歧 | 1 | 0 | 1 | 1.0 | -7.32 | -10.02 |
| W:rising:2:强势转分歧\|D:rising:5:背离 | 1 | 0 | 1 | 1.0 | -2.3 | -2.67 |
| W:rising:2:背离\|D:rising:4:背离 | 1 | 0 | 1 | 1.0 | -7.98 | -15.97 |
| W:rising:2:强势\|D:rising:6:背离 | 1 | 0 | 1 | 1.0 | -12.61 | -18.13 |
| W:rising:0:强势\|D:rising:2:背离 | 1 | 0 | 1 | 1.0 | -4.33 | -9.72 |
| W:rising:2:分歧\|D:rising:0:背离 | 1 | 0 | 1 | 1.0 | -4.3 | -8.1 |
| W:rising:3:背离\|D:rising:0:背离 | 1 | 0 | 1 | 1.0 | -3.87 | -3.17 |
| W:rising:3:强势转分歧\|D:falling:4:背离 | 1 | 0 | 1 | 1.0 | -7.16 | -12.55 |
| W:rising:0:背离\|D:rising:3:强势 | 1 | 0 | 1 | 1.0 | -2.53 | -8.72 |
| W:rising:7:背离\|D:falling:0:修复 | 1 | 0 | 1 | 1.0 | -4.35 | -4.35 |
| W:rising:5:背离\|D:falling:4:金叉临近 | 1 | 0 | 1 | 1.0 | -2.6 | -2.23 |
| W:rising:3:背离\|D:falling:4:强势 | 1 | 0 | 1 | 1.0 | -3.09 | -7.71 |
| W:rising:3:强势转分歧\|D:rising:2:背离 | 1 | 0 | 1 | 1.0 | -9.21 | -13.67 |
| W:falling:6:强势\|D:falling:8:修复 | 1 | 0 | 1 | 1.0 | -0.53 | -7.04 |
| W:rising:1:背离\|D:rising:0:背离 | 1 | 0 | 1 | 1.0 | -2.59 | -4.54 |

## Negative Factor Distribution

| key | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral\|B2\|trend_start\|price=near_low\|midline=below_midline\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 1 | 0 | 1 | 1.0 | -2.35 | -5.62 |
| neutral\|B2\|rebound\|price=middle\|midline=below_midline\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=low | 1 | 0 | 1 | 1.0 | -2.52 | -6.36 |
| neutral\|B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -1.66 | -12.47 |
| neutral\|B2\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0 | 1 | 1.0 | -1.91 | -2.33 |
| neutral\|B2\|rebound\|price=upper\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=neutral | 1 | 0 | 1 | 1.0 | -4.01 | -7.39 |
| neutral\|B2\|rebound\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 1 | 0 | 1 | 1.0 | -6.37 | -11.2 |
| neutral\|B2\|rebound\|price=upper\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -4.35 | -4.35 |
| neutral\|B2\|trend_start\|price=middle\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=rising | 1 | 0 | 1 | 1.0 | -2.6 | -2.23 |
| neutral\|B2\|rebound\|price=upper\|midline=reclaim_volume\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=low | 1 | 0 | 1 | 1.0 | -5.01 | -4.75 |
| neutral\|B2\|trend_start\|price=middle\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=low | 1 | 0 | 1 | 1.0 | -0.73 | -5.2 |
| neutral\|B2\|trend_start\|price=extended_or_unknown\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -3.51 | -15.67 |
| neutral\|B2\|rebound\|price=extended_or_unknown\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | -4.72 | -11.34 |
| neutral\|B2\|rebound\|price=middle\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=rising | 1 | 0 | 1 | 1.0 | -1.9 | -0.99 |
| neutral\|B2\|rebound\|price=middle\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=low | 1 | 0 | 1 | 1.0 | -9.16 | -19.43 |
| neutral\|B2\|rebound\|price=middle\|midline=below_midline\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=repair_from_low | 1 | 0 | 1 | 1.0 | 0.0 | 9.88 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=rising | 1 | 0 | 1 | 1.0 | -2.88 | 0.79 |
| neutral\|B2\|rebound\|price=extended_or_unknown\|midline=above_hold\|support=below_ma25_ma60\|compression=tight\|volume=normal\|kdj=rising | 1 | 0 | 1 | 1.0 | -3.05 | 3.96 |
| neutral\|B2\|rebound\|price=near_high\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=expanding\|kdj=neutral | 1 | 0 | 1 | 1.0 | -3.12 | 1.9 |
| neutral\|B2\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 1 | 0 | 1 | 1.0 | -2.15 | -5.32 |
| neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=shrinking\|kdj=rising | 1 | 0 | 1 | 1.0 | -2.2 | -2.66 |
