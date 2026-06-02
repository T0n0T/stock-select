# Stable Patterns

- min_samples: 10

## base

### Promising

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |

### Risky

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B2\|rebound | 746 | 125 | 409 | 0.168 | 0.548 | -0.45 | -1.36 |
| weak\|B2\|trend_start | 676 | 111 | 363 | 0.164 | 0.537 | -0.61 | -1.29 |
| neutral\|B2\|trend_start | 602 | 119 | 356 | 0.198 | 0.591 | -0.87 | -1.58 |
| weak\|B3\|rebound | 398 | 62 | 227 | 0.156 | 0.57 | -0.85 | -1.46 |
| neutral\|B2\|rebound | 311 | 46 | 187 | 0.148 | 0.601 | -0.98 | -0.56 |
| strong\|B2\|rebound | 175 | 38 | 85 | 0.217 | 0.486 | 0.54 | 1.51 |
| weak\|B3\|trend_start | 102 | 17 | 59 | 0.167 | 0.578 | -0.76 | -1.91 |
| strong\|B3\|rebound | 131 | 34 | 62 | 0.26 | 0.473 | 0.83 | 0.49 |

### Mixed High Sample

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong\|B2\|trend_start | 549 | 185 | 231 | 0.337 | 0.421 | 2.61 | 3.74 |
| neutral\|B3\|rebound | 155 | 31 | 72 | 0.2 | 0.465 | 1.27 | 1.13 |
| strong\|B3\|trend_start | 116 | 36 | 47 | 0.31 | 0.405 | 2.18 | 2.56 |
| neutral\|B3\|trend_start | 82 | 20 | 34 | 0.244 | 0.415 | 1.08 | -0.31 |

## macd

### Promising

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |

### Risky

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak\|B2\|rebound\|W:rising:3:背离\|D:falling:2:修复\|rising:3\|falling:2 | 75 | 13 | 43 | 0.173 | 0.573 | -1.25 | -2.18 |
| weak\|B2\|rebound\|W:rising:3:背离\|D:falling:4:修复\|rising:3\|falling:4 | 60 | 9 | 37 | 0.15 | 0.617 | -1.27 | -1.55 |
| neutral\|B2\|trend_start\|W:rising:3:背离\|D:falling:2:修复\|rising:3\|falling:2 | 42 | 4 | 29 | 0.095 | 0.69 | -2.83 | -4.39 |
| weak\|B3\|rebound\|W:rising:3:背离\|D:falling:2:修复\|rising:3\|falling:2 | 35 | 3 | 20 | 0.086 | 0.571 | -2.19 | -3.02 |
| weak\|B2\|trend_start\|W:rising:2:背离\|D:falling:2:修复\|rising:2\|falling:2 | 33 | 1 | 18 | 0.03 | 0.545 | -1.4 | -1.27 |
| weak\|B2\|trend_start\|W:rising:0:背离\|D:falling:2:修复\|rising:0\|falling:2 | 28 | 1 | 17 | 0.036 | 0.607 | -1.37 | -0.92 |
| weak\|B2\|rebound\|W:rising:0:背离\|D:falling:4:修复\|rising:0\|falling:4 | 16 | 0 | 15 | 0.0 | 0.938 | -6.37 | -4.31 |
| weak\|B3\|rebound\|W:rising:0:背离\|D:falling:2:修复\|rising:0\|falling:2 | 20 | 1 | 14 | 0.05 | 0.7 | -2.16 | -3.75 |
| weak\|B2\|rebound\|W:rising:0:背离\|D:falling:2:修复\|rising:0\|falling:2 | 31 | 5 | 18 | 0.161 | 0.581 | -0.57 | -3.38 |
| weak\|B3\|rebound\|W:rising:3:背离\|D:falling:4:修复\|rising:3\|falling:4 | 29 | 6 | 19 | 0.207 | 0.655 | -0.48 | -1.5 |
| neutral\|B2\|rebound\|W:rising:3:背离\|D:idle:0:等待启动\|rising:3\|idle:0 | 20 | 2 | 15 | 0.1 | 0.75 | -0.24 | 0.33 |
| neutral\|B2\|rebound\|W:rising:3:背离\|D:falling:2:修复\|rising:3\|falling:2 | 15 | 0 | 12 | 0.0 | 0.8 | -4.19 | -3.35 |
| weak\|B2\|trend_start\|W:rising:3:背离\|D:falling:4:修复\|rising:3\|falling:4 | 41 | 7 | 19 | 0.171 | 0.463 | 0.13 | 0.31 |
| weak\|B2\|trend_start\|W:rising:0:背离\|D:falling:4:修复\|rising:0\|falling:4 | 16 | 1 | 12 | 0.062 | 0.75 | -4.83 | -3.58 |
| weak\|B2\|rebound\|W:rising:2:背离\|D:falling:4:修复\|rising:2\|falling:4 | 12 | 0 | 11 | 0.0 | 0.917 | -2.31 | -1.02 |
| neutral\|B2\|trend_start\|W:idle:0:等待启动\|D:falling:2:修复\|idle:0\|falling:2 | 13 | 1 | 11 | 0.077 | 0.846 | -4.38 | -3.62 |
| weak\|B3\|rebound\|W:rising:1:背离\|D:falling:4:修复\|rising:1\|falling:4 | 14 | 1 | 11 | 0.071 | 0.786 | -2.63 | -3.78 |
| weak\|B3\|rebound\|W:idle:0:等待启动\|D:falling:2:修复\|idle:0\|falling:2 | 14 | 1 | 11 | 0.071 | 0.786 | -1.66 | -2.93 |
| weak\|B2\|trend_start\|W:rising:3:背离\|D:falling:2:修复\|rising:3\|falling:2 | 44 | 7 | 17 | 0.159 | 0.386 | 0.92 | 0.16 |
| neutral\|B2\|rebound\|W:idle:0:等待启动\|D:falling:2:修复\|idle:0\|falling:2 | 14 | 1 | 10 | 0.071 | 0.714 | -1.46 | -2.25 |

### Mixed High Sample

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong\|B2\|trend_start\|W:rising:3:背离\|D:falling:2:修复\|rising:3\|falling:2 | 37 | 13 | 13 | 0.351 | 0.351 | 2.83 | 3.09 |
| weak\|B2\|rebound\|W:rising:2:背离\|D:falling:2:修复\|rising:2\|falling:2 | 28 | 5 | 12 | 0.179 | 0.429 | 1.42 | 0.94 |
| strong\|B2\|trend_start\|W:rising:3:背离\|D:falling:4:修复\|rising:3\|falling:4 | 25 | 8 | 11 | 0.32 | 0.44 | 1.95 | 3.44 |
| strong\|B2\|trend_start\|W:rising:3:背离\|D:falling:6:修复\|rising:3\|falling:6 | 25 | 8 | 9 | 0.32 | 0.36 | 2.36 | 3.2 |
| weak\|B2\|trend_start\|W:rising:1:背离\|D:falling:4:修复\|rising:1\|falling:4 | 24 | 7 | 13 | 0.292 | 0.542 | 1.38 | -1.51 |

## factor

### Promising

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 33 | 17 | 9 | 0.515 | 0.273 | 4.34 | 5.72 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=repair_from_low | 12 | 7 | 4 | 0.583 | 0.333 | 8.5 | 9.57 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=low | 16 | 8 | 5 | 0.5 | 0.312 | 3.84 | 7.21 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 45 | 19 | 16 | 0.422 | 0.356 | 3.74 | 6.87 |

### Risky

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 103 | 24 | 55 | 0.233 | 0.534 | -0.09 | -1.72 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 69 | 15 | 40 | 0.217 | 0.58 | -0.81 | -0.16 |
| weak\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 57 | 10 | 34 | 0.175 | 0.596 | -1.7 | -1.88 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 23 | 0 | 22 | 0.0 | 0.957 | -5.93 | -8.73 |
| weak\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 57 | 12 | 33 | 0.211 | 0.579 | -0.12 | -0.59 |
| weak\|B2\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 37 | 6 | 22 | 0.162 | 0.595 | -0.54 | -2.31 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 21 | 2 | 16 | 0.095 | 0.762 | -1.64 | -0.31 |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 27 | 6 | 18 | 0.222 | 0.667 | -1.45 | -0.62 |
| weak\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 15 | 1 | 12 | 0.067 | 0.8 | -3.88 | -3.31 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 25 | 4 | 15 | 0.16 | 0.6 | -1.94 | -1.89 |
| weak\|B3\|rebound\|price=extended_or_unknown\|midline=above_hold\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=repair_from_low | 13 | 1 | 11 | 0.077 | 0.846 | -4.34 | -5.36 |
| weak\|B2\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 21 | 2 | 12 | 0.095 | 0.571 | -2.61 | -8.82 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 27 | 7 | 17 | 0.259 | 0.63 | -0.56 | -1.81 |
| weak\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 21 | 3 | 13 | 0.143 | 0.619 | 0.46 | -1.84 |
| weak\|B2\|trend_start\|price=upper\|midline=reclaim_volume\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 14 | 1 | 10 | 0.071 | 0.714 | -2.19 | -2.56 |
| weak\|B2\|rebound\|price=extended_or_unknown\|midline=pullback_confirm\|support=close_above_ma60\|compression=tight\|volume=normal\|kdj=repair_from_low | 13 | 1 | 10 | 0.077 | 0.769 | -1.16 | -2.1 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 19 | 3 | 12 | 0.158 | 0.632 | -1.07 | -1.51 |
| neutral\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 23 | 3 | 12 | 0.13 | 0.522 | -0.78 | -2.65 |
| weak\|B3\|rebound\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 24 | 4 | 13 | 0.167 | 0.542 | -0.72 | -3.85 |
| weak\|B2\|trend_start\|price=upper\|midline=pullback_confirm\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 24 | 4 | 13 | 0.167 | 0.542 | 0.03 | 1.23 |

### Mixed High Sample

| segment | samples | ret3>=5 | ret3<=0 | pos_rate | neg_rate | ret3_mean | ret5_mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=neutral | 78 | 24 | 39 | 0.308 | 0.5 | 2.13 | 3.99 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=rising | 43 | 12 | 21 | 0.279 | 0.488 | 2.97 | 3.42 |
| strong\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 37 | 12 | 17 | 0.324 | 0.459 | 2.93 | 4.33 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 34 | 9 | 16 | 0.265 | 0.471 | 1.8 | 2.68 |
| strong\|B3\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 29 | 11 | 11 | 0.379 | 0.379 | 2.73 | 2.86 |
| strong\|B2\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=low | 26 | 9 | 7 | 0.346 | 0.269 | 2.86 | 2.53 |
| neutral\|B3\|trend_start\|price=upper\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 25 | 8 | 12 | 0.32 | 0.48 | 1.28 | 2.23 |
| neutral\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=normal\|volume=expanding\|kdj=rising | 22 | 6 | 12 | 0.273 | 0.545 | 1.22 | 4.7 |
| neutral\|B3\|rebound\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=normal\|kdj=rising | 20 | 4 | 10 | 0.2 | 0.5 | 1.52 | -0.44 |
| strong\|B2\|trend_start\|price=near_high\|midline=above_hold\|support=bull_stack\|compression=tight\|volume=expanding\|kdj=neutral | 20 | 7 | 9 | 0.35 | 0.45 | 4.69 | 5.59 |
