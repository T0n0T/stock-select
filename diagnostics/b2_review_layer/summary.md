# b2 Review Layer Diagnostics

- rows: 4057
- environments: {'neutral': 1152, 'strong': 975, 'weak': 1930}
- ret3 buckets: {'A': 359, 'B': 469, 'C': 1049, 'D': 1188, 'E': 656, 'F': 293}
- segment_count: 17
- macd_segment_count: 1674
- factor_segment_count: 1067
- stable_pattern_counts: {'base': {'promising': 0, 'risky': 8, 'mixed_high_sample': 4}, 'macd': {'promising': 0, 'risky': 30, 'mixed_high_sample': 5}, 'factor': {'promising': 4, 'risky': 30, 'mixed_high_sample': 10}}

## Top Base Segments

| segment | samples | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| weak|B2|rebound | 746 | 125 | 409 | -0.45 | -1.36 | {"FAIL": 600, "PASS": 3, "WATCH": 143} |
| weak|B2|trend_start | 676 | 111 | 363 | -0.61 | -1.29 | {"FAIL": 99, "PASS": 6, "WATCH": 571} |
| neutral|B2|trend_start | 602 | 119 | 356 | -0.87 | -1.58 | {"FAIL": 1, "PASS": 1, "WATCH": 600} |
| strong|B2|trend_start | 549 | 185 | 231 | 2.61 | 3.74 | {"FAIL": 10, "PASS": 10, "WATCH": 529} |
| weak|B3|rebound | 398 | 62 | 227 | -0.85 | -1.46 | {"FAIL": 153, "WATCH": 245} |
| neutral|B2|rebound | 311 | 46 | 187 | -0.98 | -0.56 | {"FAIL": 156, "PASS": 6, "WATCH": 149} |
| strong|B2|rebound | 175 | 38 | 85 | 0.54 | 1.51 | {"FAIL": 58, "WATCH": 117} |
| neutral|B3|rebound | 155 | 31 | 72 | 1.27 | 1.13 | {"FAIL": 29, "PASS": 1, "WATCH": 125} |
| strong|B3|rebound | 131 | 34 | 62 | 0.83 | 0.49 | {"FAIL": 13, "PASS": 15, "WATCH": 103} |
| strong|B3|trend_start | 116 | 36 | 47 | 2.18 | 2.56 | {"PASS": 20, "WATCH": 96} |
| weak|B3|trend_start | 102 | 17 | 59 | -0.76 | -1.91 | {"WATCH": 102} |
| neutral|B3|trend_start | 82 | 20 | 34 | 1.08 | -0.31 | {"WATCH": 82} |
| weak|B3+|rebound | 5 | 0 | 2 | -1.32 | -4.23 | {"FAIL": 4, "WATCH": 1} |
| strong|B3+|trend_start | 3 | 3 | 0 | 12.52 | 12.43 | {"PASS": 1, "WATCH": 2} |
| weak|B3+|trend_start | 3 | 1 | 1 | 3.54 | 2.48 | {"WATCH": 3} |
| neutral|B3+|trend_start | 2 | 0 | 1 | 1.07 | -0.35 | {"WATCH": 2} |
| strong|B3+|rebound | 1 | 0 | 1 | -1.19 | -3.88 | {"WATCH": 1} |

## Top MACD Segments

| segment | samples | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| weak|B2|rebound|W:rising:3:背离|D:falling:2:修复|rising:3|falling:2 | 75 | 13 | 43 | -1.25 | -2.18 | {"FAIL": 60, "WATCH": 15} |
| weak|B2|rebound|W:rising:3:背离|D:falling:4:修复|rising:3|falling:4 | 60 | 9 | 37 | -1.27 | -1.55 | {"FAIL": 40, "PASS": 1, "WATCH": 19} |
| weak|B2|trend_start|W:rising:3:背离|D:falling:2:修复|rising:3|falling:2 | 44 | 7 | 17 | 0.92 | 0.16 | {"FAIL": 5, "WATCH": 39} |
| neutral|B2|trend_start|W:rising:3:背离|D:falling:2:修复|rising:3|falling:2 | 42 | 4 | 29 | -2.83 | -4.39 | {"WATCH": 42} |
| weak|B2|trend_start|W:rising:3:背离|D:falling:4:修复|rising:3|falling:4 | 41 | 7 | 19 | 0.13 | 0.31 | {"FAIL": 3, "WATCH": 38} |
| weak|B2|rebound|W:idle:0:等待启动|D:falling:2:修复|idle:0|falling:2 | 40 | 8 | 16 | -0.03 | -2.56 | {"FAIL": 38, "WATCH": 2} |
| strong|B2|trend_start|W:rising:3:背离|D:falling:2:修复|rising:3|falling:2 | 37 | 13 | 13 | 2.83 | 3.09 | {"WATCH": 37} |
| weak|B3|rebound|W:rising:3:背离|D:falling:2:修复|rising:3|falling:2 | 35 | 3 | 20 | -2.19 | -3.02 | {"FAIL": 15, "WATCH": 20} |
| weak|B2|trend_start|W:rising:2:背离|D:falling:2:修复|rising:2|falling:2 | 33 | 1 | 18 | -1.4 | -1.27 | {"FAIL": 7, "WATCH": 26} |
| weak|B2|rebound|W:rising:0:背离|D:falling:2:修复|rising:0|falling:2 | 31 | 5 | 18 | -0.57 | -3.38 | {"FAIL": 27, "WATCH": 4} |
| weak|B3|rebound|W:rising:3:背离|D:falling:4:修复|rising:3|falling:4 | 29 | 6 | 19 | -0.48 | -1.5 | {"FAIL": 10, "WATCH": 19} |
| weak|B2|rebound|W:rising:2:背离|D:falling:2:修复|rising:2|falling:2 | 28 | 5 | 12 | 1.42 | 0.94 | {"FAIL": 23, "WATCH": 5} |
| weak|B2|trend_start|W:rising:0:背离|D:falling:2:修复|rising:0|falling:2 | 28 | 1 | 17 | -1.37 | -0.92 | {"FAIL": 7, "WATCH": 21} |
| strong|B2|trend_start|W:rising:3:背离|D:falling:4:修复|rising:3|falling:4 | 25 | 8 | 11 | 1.95 | 3.44 | {"WATCH": 25} |
| strong|B2|trend_start|W:rising:3:背离|D:falling:6:修复|rising:3|falling:6 | 25 | 8 | 9 | 2.36 | 3.2 | {"FAIL": 2, "WATCH": 23} |
| weak|B2|trend_start|W:rising:1:背离|D:falling:4:修复|rising:1|falling:4 | 24 | 7 | 13 | 1.38 | -1.51 | {"FAIL": 4, "WATCH": 20} |
| weak|B2|trend_start|W:idle:0:等待启动|D:falling:2:修复|idle:0|falling:2 | 24 | 4 | 8 | 0.71 | -1.31 | {"FAIL": 6, "WATCH": 18} |
| neutral|B2|trend_start|W:rising:3:背离|D:falling:4:修复|rising:3|falling:4 | 23 | 6 | 12 | -0.2 | -1.19 | {"WATCH": 23} |
| neutral|B2|trend_start|W:rising:2:背离|D:falling:2:修复|rising:2|falling:2 | 22 | 5 | 11 | 0.42 | -3.57 | {"WATCH": 22} |
| weak|B2|rebound|W:rising:3:背离|D:idle:0:等待启动|rising:3|idle:0 | 21 | 5 | 13 | -2.18 | -0.83 | {"FAIL": 16, "WATCH": 5} |
| neutral|B2|rebound|W:rising:3:背离|D:idle:0:等待启动|rising:3|idle:0 | 20 | 2 | 15 | -0.24 | 0.33 | {"FAIL": 18, "WATCH": 2} |
| weak|B3|rebound|W:rising:0:背离|D:falling:2:修复|rising:0|falling:2 | 20 | 1 | 14 | -2.16 | -3.75 | {"FAIL": 11, "WATCH": 9} |
| neutral|B2|rebound|W:rising:3:背离|D:falling:4:修复|rising:3|falling:4 | 19 | 6 | 6 | 2.48 | 5.8 | {"FAIL": 5, "PASS": 2, "WATCH": 12} |
| weak|B2|rebound|W:rising:1:背离|D:idle:0:等待启动|rising:1|idle:0 | 19 | 5 | 11 | -1.62 | -0.89 | {"FAIL": 15, "PASS": 1, "WATCH": 3} |
| strong|B2|trend_start|W:rising:2:背离|D:falling:2:修复|rising:2|falling:2 | 18 | 6 | 5 | 4.56 | 5.79 | {"WATCH": 18} |
| weak|B2|rebound|W:rising:3:背离|D:falling:6:修复|rising:3|falling:6 | 18 | 5 | 8 | 1.01 | 0.11 | {"FAIL": 14, "PASS": 1, "WATCH": 3} |
| weak|B2|rebound|W:rising:1:背离|D:falling:2:修复|rising:1|falling:2 | 17 | 3 | 12 | -0.08 | -1.94 | {"FAIL": 14, "WATCH": 3} |
| neutral|B2|trend_start|W:rising:4:背离|D:falling:2:修复|rising:4|falling:2 | 17 | 2 | 9 | -2.3 | 1.25 | {"WATCH": 17} |
| weak|B3|rebound|W:rising:2:背离|D:falling:2:修复|rising:2|falling:2 | 16 | 6 | 4 | 3.02 | 3.63 | {"FAIL": 6, "WATCH": 10} |
| weak|B2|rebound|W:rising:1:背离|D:falling:4:修复|rising:1|falling:4 | 16 | 3 | 10 | 0.92 | -0.49 | {"FAIL": 10, "WATCH": 6} |

## Top Factor Segments

| segment | samples | ret3>=5 | ret3<=0 | ret3_mean | ret5_mean | verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| neutral|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 103 | 24 | 55 | -0.09 | -1.72 | {"WATCH": 103} |
| strong|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 78 | 24 | 39 | 2.13 | 3.99 | {"PASS": 2, "WATCH": 76} |
| weak|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 69 | 15 | 40 | -0.81 | -0.16 | {"FAIL": 4, "WATCH": 65} |
| weak|B3|rebound|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 57 | 12 | 33 | -0.12 | -0.59 | {"FAIL": 18, "WATCH": 39} |
| weak|B3|rebound|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 57 | 10 | 34 | -1.7 | -1.88 | {"FAIL": 23, "WATCH": 34} |
| strong|B2|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 45 | 19 | 16 | 3.74 | 6.87 | {"WATCH": 45} |
| strong|B2|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=expanding|kdj=rising | 43 | 12 | 21 | 2.97 | 3.42 | {"PASS": 1, "WATCH": 42} |
| neutral|B2|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=expanding|kdj=rising | 38 | 10 | 18 | 0.09 | -0.49 | {"WATCH": 38} |
| strong|B3|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 37 | 12 | 17 | 2.93 | 4.33 | {"PASS": 9, "WATCH": 28} |
| weak|B2|rebound|price=near_high|midline=above_hold|support=bull_stack|compression=normal|volume=expanding|kdj=rising | 37 | 6 | 22 | -0.54 | -2.31 | {"FAIL": 33, "WATCH": 4} |
| strong|B2|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=normal|volume=expanding|kdj=rising | 34 | 9 | 16 | 1.8 | 2.68 | {"PASS": 2, "WATCH": 32} |
| strong|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=expanding|kdj=neutral | 33 | 17 | 9 | 4.34 | 5.72 | {"PASS": 2, "WATCH": 31} |
| strong|B3|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 29 | 11 | 11 | 2.73 | 2.86 | {"PASS": 5, "WATCH": 24} |
| neutral|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=expanding|kdj=neutral | 29 | 8 | 16 | -0.8 | -1.55 | {"WATCH": 29} |
| weak|B3|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 29 | 7 | 14 | 0.34 | -0.75 | {"WATCH": 29} |
| weak|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=low | 28 | 7 | 15 | -0.86 | -0.47 | {"WATCH": 28} |
| neutral|B2|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 27 | 7 | 17 | -0.56 | -1.81 | {"WATCH": 27} |
| neutral|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=low | 27 | 6 | 18 | -1.45 | -0.62 | {"WATCH": 27} |
| strong|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=low | 26 | 9 | 7 | 2.86 | 2.53 | {"WATCH": 26} |
| neutral|B3|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 25 | 8 | 12 | 1.28 | 2.23 | {"WATCH": 25} |
| weak|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=expanding|kdj=neutral | 25 | 4 | 15 | -1.94 | -1.89 | {"WATCH": 25} |
| weak|B2|rebound|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 24 | 8 | 12 | 0.43 | 0.26 | {"FAIL": 22, "WATCH": 2} |
| weak|B2|trend_start|price=upper|midline=pullback_confirm|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 24 | 4 | 13 | 0.03 | 1.23 | {"FAIL": 8, "WATCH": 16} |
| weak|B3|rebound|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral | 24 | 4 | 13 | -0.72 | -3.85 | {"FAIL": 3, "WATCH": 21} |
| strong|B3|rebound|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 23 | 6 | 12 | 0.15 | 1.3 | {"PASS": 6, "WATCH": 17} |
| neutral|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 23 | 3 | 12 | -0.78 | -2.65 | {"WATCH": 23} |
| neutral|B2|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 23 | 0 | 22 | -5.93 | -8.73 | {"WATCH": 23} |
| neutral|B2|trend_start|price=near_high|midline=above_hold|support=bull_stack|compression=normal|volume=expanding|kdj=rising | 22 | 6 | 12 | 1.22 | 4.7 | {"WATCH": 22} |
| strong|B3|rebound|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising | 22 | 4 | 12 | -0.5 | -0.06 | {"PASS": 4, "WATCH": 18} |
| weak|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=expanding|kdj=rising | 21 | 3 | 13 | 0.46 | -1.84 | {"WATCH": 21} |

## Environment Split

| env | samples | A+B count | A+B ret3_mean | D/E/F count | D/E/F ret3_mean | WATCH/FAIL ret3>=5 | PASS ret3<=0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral | 1152 | 216 | 10.86 | 650 | -5.48 | 30 | 5 |
| strong | 975 | 296 | 11.86 | 426 | -5.17 | 30 | 16 |
| weak | 1930 | 316 | 10.94 | 1061 | -5.32 | 30 | 0 |
