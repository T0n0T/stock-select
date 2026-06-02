# Weak Final Tuning Report

- scope: final weak tuning decision after freezing strong_v1_rank
- recommended_top3_scenario: weak_v3_minus_reclaim
- top5_reference_scenario: weak_v4_reference
- production_boundary: offline decision report only; do not change production review verdict in this step
- diagnosis: Weak top3 should settle on weak_v3 with one small penalty for B2 trend_start upper/reclaim_volume/expanding/rising. Broader weak veto sets reduce daily hit rate or top5 capture, while weak_v4 remains a top5 indicator reference only.

## Scenario Comparison

| scenario | topN | samples | ret3>=5 | positive_rate | ret3<=0 | negative_rate | ret3_mean | ret3_median | daily_hit_days | daily_hit_rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak_v3_final | top3 | 72 | 19 | 0.264 | 41 | 0.569 | -0.25 | -1.98 | 15/24 | 0.625 |
| weak_v3_final | top5 | 120 | 30 | 0.25 | 67 | 0.558 | -0.44 | -1.52 | 18/24 | 0.75 |
| weak_v3_minus_rebound_near_high_normal_rising | top3 | 72 | 20 | 0.278 | 40 | 0.556 | 0.06 | -1.65 | 15/24 | 0.625 |
| weak_v3_minus_rebound_near_high_normal_rising | top5 | 120 | 27 | 0.225 | 68 | 0.567 | -0.69 | -1.72 | 18/24 | 0.75 |
| weak_v3_minus_reclaim | top3 | 72 | 20 | 0.278 | 40 | 0.556 | -0.23 | -1.98 | 16/24 | 0.667 |
| weak_v3_minus_reclaim | top5 | 120 | 31 | 0.258 | 65 | 0.542 | -0.37 | -1.34 | 19/24 | 0.792 |
| weak_v3_minus_three_loss_groups | top3 | 72 | 19 | 0.264 | 39 | 0.542 | 0.07 | -1.33 | 14/24 | 0.583 |
| weak_v3_minus_three_loss_groups | top5 | 120 | 28 | 0.233 | 67 | 0.558 | -0.52 | -1.41 | 18/24 | 0.75 |
| weak_v3_minus_three_plus_macd | top3 | 72 | 19 | 0.264 | 38 | 0.528 | 0.27 | -0.77 | 14/24 | 0.583 |
| weak_v3_minus_three_plus_macd | top5 | 120 | 27 | 0.225 | 67 | 0.558 | -0.34 | -1.41 | 16/24 | 0.667 |
| weak_v4_reference | top3 | 72 | 19 | 0.264 | 42 | 0.583 | -0.31 | -2.12 | 15/24 | 0.625 |
| weak_v4_reference | top5 | 120 | 34 | 0.283 | 65 | 0.542 | 0.28 | -0.77 | 20/24 | 0.833 |

## Penalty Candidates

| key | penalty | factor_segment | reason |
| --- | ---: | --- | --- |
| rebound_near_high_normal_rising | 0.16 | weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | top3 recurring loss group; useful as risk observation, but final simulation is weaker than the reclaim-volume penalty |
| trend_upper_normal_rising | 0.16 | weak\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | recurring top3 loss group, but broader penalty reduces daily hit rate in simulation |
| b2_reclaim_expanding_rising | 0.16 | weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | best balanced weak top3 candidate: improves top3 ret3>=5, top3 ret3<=0, daily hit rate, and top5 metrics versus weak_v3 baseline |
