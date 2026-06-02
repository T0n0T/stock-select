# Strong / Neutral Risk Candidate Report

- scope: strong_v1 topN negatives + neutral WATCH veto candidates
- diagnosis: Aggregates strong and neutral residual loser groups into offline rank_score penalty or veto candidates. This report does not change production review verdicts.

## Next Step

- strong 先将高频 topN 负例组合做 rank_score 扣分实验，不直接改 verdict。
- neutral 先把 veto_candidates 用于 WATCH 内降权；未出现 ret3/ret5 同时干净的组合前不做 PASS 放宽。
- 每个候选进入生产前必须重新跑 Phase 7 指标，并列出新增 top5 负例与被挤出正例。

## Strong Risk Candidates

- source: strong_v1_negative_groups_report.top3/top5.negative_b3_condition_distribution

| key | source_scope | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean | examples |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| NONB3=B2\|red_expanding\|price_turnover_rise\|trend_start\|price=near_high\|volume=expanding\|kdj=rising | top5 | 10 | 0 | 10 | 1.0 | -3.09 | -2.53 | 300931.SZ,603390.SH,301191.SZ,300018.SZ,601138.SH |

## Neutral Risk Candidates

- source: neutral_watch_positive_report.veto_candidates

| key | source_scope | samples | ret3>=5 | ret3<=0 | neg_rate | ret3_mean | ret5_mean | examples |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| neutral_b2_near_high_expanding_macd_bad | neutral_watch_veto | 65 | 14 | 34 | 0.523 | 0.07 | -0.17 | 002741.SZ,603989.SH,688055.SH,301329.SZ,300620.SZ |
| neutral_b2_rebound_extended_no_red | neutral_watch_veto | 41 | 4 | 27 | 0.659 | -3.54 | -1.28 | 603618.SH,000988.SZ,002498.SZ,001896.SZ,300617.SZ |
| neutral_b3_rebound_upper_no_red | neutral_watch_veto | 34 | 11 | 15 | 0.441 | 1.53 | 0.04 | 002636.SZ,300938.SZ,000690.SZ,300499.SZ,301630.SZ |
| neutral_b3_near_high_turnover_mixed | neutral_watch_veto | 9 | 1 | 5 | 0.556 | -0.16 | -0.5 | 301509.SZ,000883.SZ,601077.SH,002960.SZ,300531.SZ |
