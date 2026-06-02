# Neutral Factor Effect Report

- scope: env=neutral, factor frequencies among ret3>5 samples
- sample_count: 1151
- ret3>5 count: 214
- PASS+WATCH ret3>5 count: 190

## Guidance

- 多数 ret3>5 样本拥有且相对 neutral 基准有 uplift 的因子，才视作正向参考。
- 高占比但 uplift 为负的因子只是环境基准特征，不应当单独加分。
- neutral 仍需和 veto/risk 条件一起使用；当前不直接扩 PASS。

## Majority Positive Features

| factor | key | base_share | ret3>5_share | uplift | PASS+WATCH ret3>5 share |
| --- | --- | ---: | ---: | ---: | ---: |
| obv | obv=flat | 0.9218 | 0.9346 | 0.0128 | 0.9421 |
| compression | compression=tight | 0.8219 | 0.8645 | 0.0426 | 0.8474 |
| support_stack | support_stack=bull_stack | 0.7654 | 0.7897 | 0.0243 | 0.8579 |
| midline_state | midline_state=above_hold | 0.6525 | 0.7523 | 0.0999 | 0.8158 |
| signal_type | signal_type=trend_start | 0.596 | 0.6449 | 0.0489 | 0.7211 |
| volume | volume=normal | 0.5908 | 0.6168 | 0.026 | 0.6211 |
| bbi_bias | bbi_bias=above_extended | 0.5421 | 0.5794 | 0.0373 | 0.6316 |
| price_bucket | price_bucket=upper | 0.4996 | 0.5654 | 0.0659 | 0.6105 |
| signal_combo | signal_combo=B2\|trend_start | 0.523 | 0.5561 | 0.0331 | 0.6211 |

## signal_combo

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B2\|trend_start | 602 | 0.523 | 119 | 0.5561 | 0.0331 | 118 | 0.6211 |
| B2\|rebound | 310 | 0.2693 | 45 | 0.2103 | -0.0591 | 25 | 0.1316 |
| B3\|rebound | 155 | 0.1347 | 31 | 0.1449 | 0.0102 | 28 | 0.1474 |
| B3\|trend_start | 82 | 0.0712 | 19 | 0.0888 | 0.0175 | 19 | 0.1 |

## signal

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B2 | 912 | 0.7924 | 164 | 0.7664 | -0.026 | 143 | 0.7526 |
| B3 | 237 | 0.2059 | 50 | 0.2336 | 0.0277 | 47 | 0.2474 |

## signal_type

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| trend_start | 686 | 0.596 | 138 | 0.6449 | 0.0489 | 137 | 0.7211 |
| rebound | 465 | 0.404 | 76 | 0.3551 | -0.0489 | 53 | 0.2789 |

## price_bucket

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| upper | 575 | 0.4996 | 121 | 0.5654 | 0.0659 | 116 | 0.6105 |
| near_high | 257 | 0.2233 | 44 | 0.2056 | -0.0177 | 44 | 0.2316 |
| extended_or_unknown | 135 | 0.1173 | 30 | 0.1402 | 0.0229 | 22 | 0.1158 |
| middle | 138 | 0.1199 | 17 | 0.0794 | -0.0405 | 8 | 0.0421 |
| near_low | 46 | 0.04 | 2 | 0.0093 | -0.0306 | 0 | 0.0 |

## midline_state

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| above_hold | 751 | 0.6525 | 161 | 0.7523 | 0.0999 | 155 | 0.8158 |
| reclaim_volume | 121 | 0.1051 | 21 | 0.0981 | -0.007 | 16 | 0.0842 |
| pullback_confirm | 152 | 0.1321 | 20 | 0.0935 | -0.0386 | 18 | 0.0947 |
| below_midline | 127 | 0.1103 | 12 | 0.0561 | -0.0543 | 1 | 0.0053 |

## support_stack

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bull_stack | 881 | 0.7654 | 169 | 0.7897 | 0.0243 | 163 | 0.8579 |
| close_above_ma60 | 238 | 0.2068 | 40 | 0.1869 | -0.0199 | 27 | 0.1421 |
| below_ma25_ma60 | 32 | 0.0278 | 5 | 0.0234 | -0.0044 | 0 | 0.0 |

## compression

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tight | 946 | 0.8219 | 185 | 0.8645 | 0.0426 | 161 | 0.8474 |
| normal | 189 | 0.1642 | 28 | 0.1308 | -0.0334 | 28 | 0.1474 |
| wide | 16 | 0.0139 | 1 | 0.0047 | -0.0092 | 1 | 0.0053 |

## volume

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| normal | 680 | 0.5908 | 132 | 0.6168 | 0.026 | 118 | 0.6211 |
| expanding | 447 | 0.3884 | 77 | 0.3598 | -0.0285 | 69 | 0.3632 |
| shrinking | 24 | 0.0209 | 5 | 0.0234 | 0.0025 | 3 | 0.0158 |

## kdj

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rising | 480 | 0.417 | 80 | 0.3738 | -0.0432 | 72 | 0.3789 |
| neutral | 359 | 0.3119 | 68 | 0.3178 | 0.0059 | 64 | 0.3368 |
| low | 148 | 0.1286 | 33 | 0.1542 | 0.0256 | 25 | 0.1316 |
| repair_from_low | 159 | 0.1381 | 30 | 0.1402 | 0.002 | 26 | 0.1368 |
| overheat | 5 | 0.0043 | 3 | 0.014 | 0.0097 | 3 | 0.0158 |

## daily_macd_hist

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| green_or_zero | 850 | 0.7385 | 155 | 0.7243 | -0.0142 | 132 | 0.6947 |
| red_expanding | 259 | 0.225 | 52 | 0.243 | 0.018 | 51 | 0.2684 |
| red_contracting | 42 | 0.0365 | 7 | 0.0327 | -0.0038 | 7 | 0.0368 |

## price_turnover

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| price_turnover_rise | 912 | 0.7924 | 164 | 0.7664 | -0.026 | 143 | 0.7526 |
| mixed | 148 | 0.1286 | 29 | 0.1355 | 0.0069 | 26 | 0.1368 |
| price_up_turnover_not | 91 | 0.0791 | 21 | 0.0981 | 0.0191 | 21 | 0.1105 |

## bbi_bias

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| above_extended | 624 | 0.5421 | 124 | 0.5794 | 0.0373 | 120 | 0.6316 |
| above | 413 | 0.3588 | 68 | 0.3178 | -0.0411 | 56 | 0.2947 |
| below_near | 96 | 0.0834 | 15 | 0.0701 | -0.0133 | 10 | 0.0526 |
| below_deep | 18 | 0.0156 | 7 | 0.0327 | 0.0171 | 4 | 0.0211 |

## bias

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| positive | 573 | 0.4978 | 99 | 0.4626 | -0.0352 | 90 | 0.4737 |
| neutral | 495 | 0.4301 | 90 | 0.4206 | -0.0095 | 77 | 0.4053 |
| high_positive | 78 | 0.0678 | 22 | 0.1028 | 0.035 | 22 | 0.1158 |
| negative | 4 | 0.0035 | 2 | 0.0093 | 0.0059 | 1 | 0.0053 |
| deep_negative | 1 | 0.0009 | 1 | 0.0047 | 0.0038 | 0 | 0.0 |

## obv

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| flat | 1061 | 0.9218 | 200 | 0.9346 | 0.0128 | 179 | 0.9421 |
| rising | 82 | 0.0712 | 13 | 0.0607 | -0.0105 | 11 | 0.0579 |
| falling | 8 | 0.007 | 1 | 0.0047 | -0.0023 | 0 | 0.0 |

## macd_wave

| value | base_count | base_share | ret3>5_count | ret3>5_share | uplift | PASS+WATCH ret3>5 count | PASS+WATCH ret3>5 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W:rising:3:背离\|D:falling:4:修复 | 52 | 0.0452 | 15 | 0.0701 | 0.0249 | 13 | 0.0684 |
| W:rising:2:背离\|D:falling:2:修复 | 41 | 0.0356 | 8 | 0.0374 | 0.0018 | 7 | 0.0368 |
| W:falling:2:修复\|D:falling:2:修复 | 8 | 0.007 | 6 | 0.028 | 0.0211 | 6 | 0.0316 |
| W:rising:0:背离\|D:falling:2:修复 | 26 | 0.0226 | 6 | 0.028 | 0.0054 | 4 | 0.0211 |
| W:rising:3:背离\|D:falling:2:修复 | 69 | 0.0599 | 6 | 0.028 | -0.0319 | 6 | 0.0316 |
| W:rising:3:背离\|D:falling:6:修复 | 16 | 0.0139 | 5 | 0.0234 | 0.0095 | 5 | 0.0263 |
| W:rising:3:强势\|D:falling:4:修复 | 4 | 0.0035 | 4 | 0.0187 | 0.0152 | 4 | 0.0211 |
| W:falling:2:背离\|D:idle:0:等待启动 | 13 | 0.0113 | 4 | 0.0187 | 0.0074 | 2 | 0.0105 |
| W:rising:5:背离\|D:falling:2:修复 | 24 | 0.0209 | 4 | 0.0187 | -0.0022 | 4 | 0.0211 |
| W:rising:1:背离\|D:falling:2:修复 | 27 | 0.0235 | 4 | 0.0187 | -0.0048 | 4 | 0.0211 |
| W:rising:5:背离\|D:falling:2:强势 | 3 | 0.0026 | 3 | 0.014 | 0.0114 | 2 | 0.0105 |
| W:rising:2:背离\|D:rising:0:背离 | 5 | 0.0043 | 3 | 0.014 | 0.0097 | 3 | 0.0158 |
