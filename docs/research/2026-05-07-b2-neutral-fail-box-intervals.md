# 2026-05-07 b2 neutral `FAIL` 箱体区间与 `WATCH` 大涨样本区分

数据口径：

- artifact：`artifacts/review-tuning/b2-2026-01-01-2026-05-06-candidate-v4`
- 环境：`environment_state = neutral`
- `FAIL` 连续箱体值来源：
  `artifacts/review-tuning/b2-2026-01-01-2026-05-06-candidate-v4/neutral_fail_box_values.csv`
- `box_position` 定义：
  `(current_mid_price - box_low) / (box_high - box_low)`
- `close_box_position` 定义：
  `(latest_close - box_low) / (box_high - box_low)`

## 一、`FAIL` 的连续 box 区间

### 全体 `FAIL`

- 样本数：`460`
- `box_position` 均值：`0.430`
- `box_position` 中位数：`0.440`
- `close_box_position` 中位数：`0.470`
- `box_range_pct` 中位数：`65.245%`

分位数：

- `q10 = 0.304`
- `q25 = 0.362`
- `q50 = 0.440`
- `q75 = 0.495`
- `q90 = 0.546`

### `FAIL` 里后续大涨样本

- 样本数：`8`
- `box_position` 均值：`0.374`
- `box_position` 中位数：`0.392`
- `close_box_position` 中位数：`0.450`
- `box_range_pct` 中位数：`88.926%`

分位数：

- `q10 = 0.197`
- `q25 = 0.306`
- `q50 = 0.392`
- `q75 = 0.469`
- `q90 = 0.505`

### `FAIL` 里后续下跌样本

- 样本数：`268`
- `box_position` 均值：`0.420`
- `box_position` 中位数：`0.421`
- `close_box_position` 中位数：`0.457`
- `box_range_pct` 中位数：`64.084%`

分位数：

- `q10 = 0.302`
- `q25 = 0.358`
- `q50 = 0.421`
- `q75 = 0.481`
- `q90 = 0.533`

## 二、`FAIL` 箱体区间的解释

结论不是“越左越好”，而是：

- `FAIL` 大涨样本整体更偏左，`box_position` 中位数从 `0.421` 下移到 `0.392`
- 但差距不算极大，说明单纯把 `price_position` 低分样本整体抬升会误伤过滤器
- 真正更有辨识度的是：
  - 极左样本占比在大涨组更高
  - 同时它们的 `box_range_pct` 明显更大，很多是大箱体里的左侧再启动

阈值观察：

- `box_position <= 0.25`
  - 大涨组占比：`25.0%`
  - 下跌组占比：`2.6%`
- `box_position <= 0.30`
  - 大涨组占比：`25.0%`
  - 下跌组占比：`9.7%`
- `box_position <= 0.35`
  - 大涨组占比：`37.5%`
  - 下跌组占比：`23.1%`
- `box_position <= 0.40`
  - 大涨组占比：`50.0%`
  - 下跌组占比：`41.0%`

因此更像有效候选区间的是：

- `box_position <= 0.30`：更偏稀缺的极左候选
- `0.30 ~ 0.40`：有一定差异，但区分度明显下降
- `>= 0.45`：对大涨和下跌几乎没什么区分力

## 三、代表性 `FAIL` 大涨样本

|日期|代码|5日|price_position|box_position|close_box_position|box_range_pct|
|---|---|---:|---:|---:|---:|---:|
|2026-01-30|603618.SH|+51.66%|1|0.341|0.440|87.289%|
|2026-03-04|300323.SZ|+37.82%|2|0.459|0.590|30.705%|
|2026-01-05|301256.SZ|+28.14%|2|0.433|0.460|90.562%|
|2026-04-09|301248.SZ|+28.00%|3|0.522|0.516|185.061%|
|2026-04-09|301667.SZ|+25.22%|1|0.188|0.183|200.050%|
|2026-04-24|603937.SH|+21.16%|2|0.498|0.664|38.190%|
|2026-04-08|301667.SZ|+20.38%|1|0.200|0.212|200.050%|
|2026-04-08|603063.SH|+20.27%|1|0.350|0.427|30.450%|

这批样本进一步说明：

- `price_position = 1/2` 里确实有该保留的左侧爆发型样本
- 但它们并不都落在同一个窄区间
- 更像是两类混在一起：
  - `box_position <= 0.25` 的极左爆发型
  - `0.43 ~ 0.52` 附近但箱体很大的再启动型

## 四、`WATCH` 大涨样本和普通 `WATCH` 的差异

### 均值差

- `total_score`：`4.073 vs 4.045`，差异很小
- `trend_structure`：`3.869 vs 3.876`，几乎无差异
- `price_position`：`3.919 vs 3.795`，略高
- `volume_behavior`：`3.737 vs 3.823`，略低
- `previous_abnormal_move`：`4.859 vs 4.886`，几乎无差异
- `macd_phase`：`3.898 vs 3.818`，略高

### 分布差

- `WATCH` 大涨样本里 `price_position = 4` 占 `95/99`
- 普通 `WATCH` 里 `price_position = 4` 也很多，占 `2151/2420`

所以 `WATCH` 大涨样本并没有一个单独的小分维度能明显跳出来。更像：

- 它们已经被现有规则压进一个很大的 `WATCH` 池
- 单看离散小分，几乎不足以再把它们捞出来
- 需要继续看连续特征，例如：
  - `zxdq/zxdkx` 斜率
  - `watch_score/watch_tier`
  - 连续 box 位置

## 五、当前建议

### 对 `FAIL`

- 不建议仅凭这轮结果直接整体上调 `price_position=1/2`
- 更合理的是加一个窄门候选：
  - `box_position <= 0.30`
  - 再叠加别的确认条件
- `0.30 ~ 0.40` 不能直接放，噪音仍较大

### 对 `WATCH`

- 先不要继续靠 `trend_structure / previous_abnormal_move / total_score` 微调
- 更应该研究：
  - `watch_score`
  - `watch_tier`
  - `zxdq/zxdkx` 斜率
  - 连续 box 值

### 对 `PASS`

- `neutral PASS` 增加 `zxdq_5d_slope >= 0` gate 是合理方向
- 这层更像质量护栏，不是扩池手段

