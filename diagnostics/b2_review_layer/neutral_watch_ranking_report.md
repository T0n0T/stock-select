# Neutral PASS/WATCH Ranking Report

- scope: env=neutral and verdict in PASS/WATCH
- sample_count: 966
- candidate_count: 966
- diagnosis: neutral_v1 is an offline WATCH/PASS+WATCH ranking experiment using the neutral positive skeleton and neutral veto candidates. Do not change production verdict before Phase 7 comparison improves.

## Top3 Comparison

| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 48 | 8 | 25 | 0.167 | 0.521 | -0.2 | -0.97 | -0.35 | 1.26 |
| neutral_v1_rank | 48 | 18 | 20 | 0.375 | 0.417 | 1.27 | 1.32 | 1.22 | 2.01 |

## Top5 Comparison

| ranking | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret3_median | ret5_mean | ret5_median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current_score | 80 | 18 | 40 | 0.225 | 0.5 | 0.36 | -0.01 | 0.52 | 0.75 |
| neutral_v1_rank | 80 | 23 | 37 | 0.287 | 0.463 | 0.44 | 0.46 | 0.15 | 1.26 |

## Daily Neutral V1 Rank Top3

| date | rank | code | verdict | neutral_v1_score | current_score | positive_score | risk_penalty | risk_flags | ret3 | ret5 | factor_segment |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| 2026-03-03 | 1 | 603836.SH | WATCH | 4.63 | 4.19 | 0.44 | 0.0 |  | -5.89 | -7.77 | neutral\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising |
| 2026-03-03 | 2 | 001278.SZ | WATCH | 4.6 | 4.04 | 0.56 | 0.0 |  | -5.39 | -2.62 | neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral |
| 2026-03-03 | 3 | 002952.SZ | WATCH | 4.55 | 4.05 | 0.5 | 0.0 |  | 6.96 | 11.67 | neutral\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising |
| 2026-03-10 | 1 | 688171.SH | WATCH | 4.85 | 4.19 | 0.66 | 0.0 |  | -2.77 | -9.27 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral |
| 2026-03-10 | 2 | 300873.SZ | WATCH | 4.79 | 4.19 | 0.6 | 0.0 |  | -4.33 | -9.72 | neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-03-10 | 3 | 920068.BJ | WATCH | 4.76 | 4.06 | 0.7 | 0.0 |  | -0.32 | 2.59 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-08 | 1 | 002467.SZ | WATCH | 4.75 | 4.05 | 0.7 | 0.0 |  | 5.21 | 2.01 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-08 | 2 | 603308.SH | WATCH | 4.75 | 4.05 | 0.7 | 0.0 |  | 1.91 | -2.97 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-08 | 3 | 300113.SZ | WATCH | 4.74 | 4.08 | 0.66 | 0.0 |  | 0.07 | 2.06 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low |
| 2026-04-09 | 1 | 002913.SZ | WATCH | 4.79 | 4.17 | 0.62 | 0.0 |  | 5.09 | 2.02 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-09 | 2 | 301018.SZ | WATCH | 4.77 | 4.19 | 0.58 | 0.0 |  | 20.15 | 17.77 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=overheat |
| 2026-04-09 | 3 | 300201.SZ | WATCH | 4.69 | 4.07 | 0.62 | 0.0 |  | 3.19 | 7.99 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-10 | 1 | 301509.SZ | WATCH | 4.79 | 4.19 | 0.6 | 0.0 |  | 7.32 | 2.46 | neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-10 | 2 | 688178.SH | WATCH | 4.75 | 4.05 | 0.7 | 0.0 |  | -2.81 | 8.69 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-10 | 3 | 003036.SZ | WATCH | 4.65 | 3.95 | 0.7 | 0.0 |  | 12.16 | 7.06 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-13 | 1 | 300438.SZ | WATCH | 4.8 | 4.18 | 0.62 | 0.0 |  | 15.28 | 13.28 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-13 | 2 | 301306.SZ | WATCH | 4.77 | 4.07 | 0.7 | 0.0 |  | 8.78 | 12.79 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-13 | 3 | 002709.SZ | WATCH | 4.71 | 4.09 | 0.62 | 0.0 |  | 5.25 | 6.29 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-14 | 1 | 688663.SH | WATCH | 4.76 | 4.18 | 0.58 | 0.0 |  | 0.59 | 1.88 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising |
| 2026-04-14 | 2 | 002693.SZ | WATCH | 4.7 | 4.18 | 0.52 | 0.0 |  | 1.67 | 7.89 | neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-14 | 3 | 002192.SZ | WATCH | 4.7 | 4.08 | 0.62 | 0.0 |  | 6.35 | 1.47 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-15 | 1 | 688618.SH | WATCH | 4.72 | 4.06 | 0.66 | 0.0 |  | 5.54 | 2.62 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral |
| 2026-04-15 | 2 | 002294.SZ | WATCH | 4.7 | 4.04 | 0.66 | 0.0 |  | -16.46 | -15.13 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral |
| 2026-04-15 | 3 | 301295.SZ | WATCH | 4.65 | 4.05 | 0.6 | 0.0 |  | 11.25 | 23.29 | neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-16 | 1 | 301179.SZ | WATCH | 4.71 | 4.09 | 0.62 | 0.0 |  | 0.33 | -5.62 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-16 | 2 | 000070.SZ | WATCH | 4.66 | 4.06 | 0.6 | 0.0 |  | -1.4 | 1.06 | neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-16 | 3 | 300804.SZ | WATCH | 4.66 | 3.96 | 0.7 | 0.0 |  | -7.99 | -7.15 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-04-17 | 1 | 605196.SH | WATCH | 4.79 | 4.17 | 0.62 | 0.0 |  | -8.46 | -13.04 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-04-17 | 2 | 001267.SZ | WATCH | 4.69 | 4.03 | 0.66 | 0.0 |  | 3.53 | 12.5 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising |
| 2026-04-17 | 3 | 600487.SH | WATCH | 4.57 | 3.87 | 0.7 | 0.0 |  | 18.2 | 24.96 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low |
| 2026-05-18 | 1 | 002066.SZ | WATCH | 4.81 | 4.19 | 0.62 | 0.0 |  | -1.77 | -4.15 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-05-18 | 2 | 300031.SZ | WATCH | 4.71 | 4.05 | 0.66 | 0.0 |  | 5.26 | 3.24 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral |
| 2026-05-18 | 3 | 300483.SZ | WATCH | 4.66 | 4.06 | 0.6 | 0.0 |  | -3.11 | -10.56 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising |
| 2026-05-21 | 1 | 603127.SH | WATCH | 4.79 | 4.19 | 0.6 | 0.0 |  | -12.37 | -14.75 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising |
| 2026-05-21 | 2 | 600207.SH | WATCH | 4.72 | 4.06 | 0.66 | 0.0 |  | 5.97 | 20.6 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral |
| 2026-05-21 | 3 | 002952.SZ | WATCH | 4.64 | 4.04 | 0.6 | 0.0 |  | 9.33 | 2.07 | neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-05-22 | 1 | 600699.SH | WATCH | 4.81 | 4.19 | 0.62 | 0.0 |  | -1.95 | -14.93 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-05-22 | 2 | 603002.SH | WATCH | 4.77 | 4.07 | 0.7 | 0.0 |  | 1.66 | 1.78 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-05-22 | 3 | 600207.SH | WATCH | 4.76 | 4.18 | 0.58 | 0.0 |  | 14.41 | 11.89 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral |
| 2026-05-25 | 1 | 001268.SZ | WATCH | 4.81 | 4.19 | 0.62 | 0.0 |  | -3.46 | -6.06 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-05-25 | 2 | 603002.SH | WATCH | 4.81 | 4.19 | 0.62 | 0.0 |  | 5.45 | 3.15 | neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-05-25 | 3 | 301129.SZ | WATCH | 4.79 | 4.33 | 0.46 | 0.0 |  | -5.52 | -10.35 | neutral\|B3\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-05-26 | 1 | 688593.SH | WATCH | 4.75 | 4.05 | 0.7 | 0.0 |  | -12.15 | -16.57 | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
| 2026-05-26 | 2 | 600060.SH | WATCH | 4.71 | 4.19 | 0.52 | 0.0 |  | -3.66 | -2.95 | neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=overheat |
| 2026-05-26 | 3 | 688310.SH | WATCH | 4.66 | 4.18 | 0.48 | 0.0 |  | -7.1 | -6.67 | neutral\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising |
| 2026-05-28 | 1 | 300305.SZ | WATCH | 4.83 | 4.19 | 0.64 | 0.0 |  | 1.11 | None | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=normal\|kdj=neutral |
| 2026-05-28 | 2 | 301183.SZ | WATCH | 4.77 | 4.07 | 0.7 | 0.0 |  | -15.77 | None | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising |
| 2026-05-28 | 3 | 300726.SZ | WATCH | 4.75 | 4.05 | 0.7 | 0.0 |  | 1.53 | None | neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral |
