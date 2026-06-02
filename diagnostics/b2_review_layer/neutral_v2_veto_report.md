# Neutral V2 Veto Report

- scope: neutral_v2 offline veto/risk experiment from neutral_v1 top3 loss-only groups
- diagnosis: neutral_v2 penalizes only loss-only factor/MACD groups from neutral_v1 top3. Keep this offline until top3/top5 metrics improve without materially reducing ret3>=5 capture.

## Top3 Comparison

| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral_v1_rank | 48 | 18 | 20 | 0.375 | 0.417 | 1.27 | 1.32 | 1.22 | 2.01 |
| neutral_v2_rank | 48 | 18 | 20 | 0.375 | 0.417 | 1.31 | 1.59 | 1.73 | 2.06 |

## Top5 Comparison

| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral_v1_rank | 80 | 23 | 37 | 0.287 | 0.463 | 0.44 | 0.46 | 0.15 | 1.26 |
| neutral_v2_rank | 80 | 23 | 35 | 0.287 | 0.438 | 0.75 | 0.94 | 0.64 | 1.47 |

## Veto Candidates: factor

| key | samples | ret3>=5 | ret3<=0 | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 2 | 0 | 2 | -7.74 | -7.74 | -12.66 | -12.66 |
| neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 3 | 0 | 2 | -1.69 | -1.95 | -8.87 | -6.06 |

## Veto Candidates: macd

| key | samples | ret3>=5 | ret3<=0 | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:2:背离\|D:rising:2:背离 | 2 | 0 | 2 | -2.36 | -2.36 | -12.1 | -12.1 |

## Penalized Samples

| date | code | neutral_v1_score | neutral_v2_score | penalty | ret3 | ret5 | signal | signal_type | veto_hits |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 2026-03-10 | 688535.SH | 4.66 | 4.01 | 0.65 | -5.74 | -8.02 | B2 | trend_start | factor_loss_only |
| 2026-03-10 | 301446.SZ | 4.64 | 3.99 | 0.65 | -10.96 | -16.43 | B2 | trend_start | factor_loss_only |
| 2026-03-10 | 688171.SH | 4.85 | 4.5 | 0.35 | -2.77 | -9.27 | B2 | trend_start | macd_loss_only |
| 2026-04-08 | 002789.SZ | 4.51 | 3.86 | 0.65 | 5.0 | 8.33 | B3 | trend_start | factor_loss_only |
| 2026-04-08 | 688125.SH | 4.42 | 3.77 | 0.65 | 4.51 | -0.59 | B2 | trend_start | factor_loss_only |
| 2026-04-08 | 603701.SH | 4.39 | 4.04 | 0.35 | -1.65 | -0.95 | B2 | trend_start | macd_loss_only |
| 2026-04-08 | 002960.SZ | 4.23 | 3.88 | 0.35 | -0.74 | 0.57 | B2 | rebound | macd_loss_only |
| 2026-04-09 | 002960.SZ | 4.33 | 3.98 | 0.35 | 1.74 | 0.75 | B3 | trend_start | macd_loss_only |
| 2026-04-13 | 688663.SH | 4.66 | 4.01 | 0.65 | 2.81 | 12.81 | B2 | trend_start | factor_loss_only |
| 2026-04-13 | 300750.SZ | 4.7 | 4.35 | 0.35 | 6.29 | 1.26 | B3 | trend_start | macd_loss_only |
| 2026-04-14 | 300301.SZ | 4.44 | 3.79 | 0.65 | 7.1 | 3.83 | B2 | trend_start | factor_loss_only |
| 2026-04-15 | 688251.SH | 4.14 | 3.49 | 0.65 | -4.06 | -9.49 | B2 | trend_start | factor_loss_only |
| 2026-04-16 | 301179.SZ | 4.71 | 4.06 | 0.65 | 0.33 | -5.62 | B3 | trend_start | factor_loss_only |
| 2026-04-16 | 300651.SZ | 4.52 | 3.87 | 0.65 | -3.94 | -6.25 | B3 | trend_start | factor_loss_only |
| 2026-04-17 | 301338.SZ | 4.45 | 3.8 | 0.65 | 6.51 | -1.31 | B2 | trend_start | factor_loss_only |
| 2026-05-18 | 300483.SZ | 4.66 | 4.01 | 0.65 | -3.11 | -10.56 | B2 | trend_start | factor_loss_only |
| 2026-05-18 | 002850.SZ | 4.55 | 3.9 | 0.65 | 1.92 | -2.61 | B2 | trend_start | factor_loss_only |
| 2026-05-21 | 603127.SH | 4.79 | 4.14 | 0.65 | -12.37 | -14.75 | B2 | trend_start | factor_loss_only |
| 2026-05-21 | 688347.SH | 4.53 | 4.18 | 0.35 | 31.61 | 47.72 | B3 | rebound | macd_loss_only |
| 2026-05-22 | 600699.SH | 4.81 | 3.81 | 1.0 | -1.95 | -14.93 | B3 | trend_start | factor_loss_only,macd_loss_only |
| 2026-05-22 | 301265.SZ | 4.62 | 3.97 | 0.65 | 0.29 | -0.29 | B2 | trend_start | factor_loss_only |
| 2026-05-25 | 001268.SZ | 4.81 | 4.16 | 0.65 | -3.46 | -6.06 | B3 | trend_start | factor_loss_only |
| 2026-05-25 | 688313.SH | 4.79 | 4.14 | 0.65 | -10.07 | -19.67 | B3 | trend_start | factor_loss_only |
| 2026-05-25 | 300870.SZ | 4.68 | 4.03 | 0.65 | -29.46 | -39.95 | B3 | trend_start | factor_loss_only |
| 2026-05-25 | 002531.SZ | 4.65 | 4.0 | 0.65 | -7.64 | -14.79 | B2 | trend_start | factor_loss_only |
| 2026-05-25 | 300570.SZ | 4.51 | 3.86 | 0.65 | 4.41 | -9.47 | B3 | trend_start | factor_loss_only |
| 2026-05-25 | 002951.SZ | 4.67 | 4.32 | 0.35 | -0.79 | 10.04 | B2 | trend_start | macd_loss_only |
| 2026-05-25 | 000883.SZ | 4.49 | 4.14 | 0.35 | 1.17 | 6.07 | B2 | trend_start | macd_loss_only |
| 2026-05-26 | 000883.SZ | 4.41 | 4.06 | 0.35 | 4.31 | 4.11 | B3 | trend_start | macd_loss_only |
| 2026-05-28 | 920047.BJ | 4.65 | 4.0 | 0.65 | -36.21 | None | B2 | trend_start | factor_loss_only |
