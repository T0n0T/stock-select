# B2 baseline>=3.6 与 3日收益相关性复盘（2026-04-13 ~ 2026-04-23）

## 背景

本复盘用于评估 `stock-select b2` 在启用 `--llm-min-baseline-score 3.6` 后，baseline 总分与各小分对短线 3 日收益的解释力。

核心问题：

1. `baseline_total >= 3.6` 是否能有效压缩 b2 候选并保留较优样本？
2. baseline 总分与 3 日涨幅是否存在相关性？
3. baseline 小分中，哪些字段与最终涨幅排名更相关？
4. b2 的 `signal` 子类型（B2/B3/B4/B5）是否比总分更有区分度？

## 数据与口径

- 方法：`b2`
- 日期范围：`2026-04-13` ~ `2026-04-23`
- baseline 阈值：`baseline_total >= 3.6`
- 3 日涨幅定义：

```text
3日涨幅 = 第3个交易日后收盘价 / 入选日收盘价 - 1
```

即从入选日开始取 4 个交易日收盘价：第 0 天为入选日，第 3 天为 3 日后。

- 重复股票处理：同一股票在不同 `pick_date` 入选时按不同 occurrence 处理。
- 主相关性样本：仅纳入可观察满 3 个交易日的记录。
- 未满 3 日记录：保留在明细中，但不纳入主相关性统计。

## 运行说明

本次复盘使用最新完整 prepared cache 中的历史数据做回看。`run_b2_screen_with_stats(prepared_by_symbol, pick_date)` 与 `review_b2_symbol_history(..., pick_date=...)` 都会按 `<= pick_date` 截断历史，因此可用最新完整 cache 安全复用历史日期，避免为每个日期重复生成重型 prepared cache。

本次中间产物：

```text
/tmp/stock_select_b2_0413_0423_baseline_corr.json
/tmp/stock_select_b2_0413_0423_baseline_corr_summary.json
```

注意：原始汇总脚本曾因当前环境缺少 `scipy` 在 `Series.corr(method="spearman")` 处失败。最终采用“先 rank 后 Pearson”的方式手工计算 Spearman/排名相关，不依赖 `scipy`。

## B2 baseline 权重

> 说明：本节记录复盘当时的旧 baseline 权重。后续实现已将 `signal` 子类型并入 `total_score`，不再使用独立 `ranking_score`。本复盘保留旧口径用于解释为什么需要把 B2/B3/B4/B5 信号纳入总分。

`b2` baseline 总分权重如下：

```text
trend_structure          0.20
price_position           0.25
volume_behavior          0.15
previous_abnormal_move   0.10
macd_phase               0.30
```

即：

```text
baseline_total =
  0.20 * trend_structure
+ 0.25 * price_position
+ 0.15 * volume_behavior
+ 0.10 * previous_abnormal_move
+ 0.30 * macd_phase
```

## 样本概况

逐日筛选结果：

```text
日期          b2原始候选   baseline>=3.6   baseline<3.6
2026-04-13   39           9               30
2026-04-14   34           5               29
2026-04-15   51           6               45
2026-04-16   50           8               42
2026-04-17   40           5               35
2026-04-20   32           6               26
2026-04-21   26           5               21
2026-04-22   40           11              29
2026-04-23   26           6               20
```

汇总：

```text
原始 b2 候选合计：338 只次
baseline>=3.6 保留：61 只次
可计算完整3日涨幅：44 只次
未满3日/样本不足：17 只次
baseline review 失败：0
```

`baseline>=3.6` 的保留率约为：

```text
61 / 338 = 18.05%
```

说明 3.6 阈值对 b2 原始候选有明显压缩效果。

## 3 日收益整体表现

基于完整 3 日观察样本 `n=44`：

```text
平均3日涨幅：+1.8298%
中位数3日涨幅：+0.4042%
胜率：52.27%
最大值：+48.5181%
最小值：-16.4561%
```

收益分布存在明显右尾。最大正收益样本为 `688268.SH`，对均值有明显抬升。

## baseline 总分与 3 日涨幅相关性

```text
字段              Pearson    Spearman/排名相关
baseline_total    +0.0941    +0.2031
```

结论：

- baseline 总分与 3 日涨幅存在弱正相关。
- 排名相关性高于线性相关，说明 baseline 总分对“排序方向”有一定帮助。
- 相关性并不强，不能简单按 baseline_total 从高到低直接等同于 3 日收益排序。

## baseline 小分相关性

```text
小分字段                  Pearson    Spearman/排名相关
trend_structure           +0.1460    +0.1186
price_position            -0.0731    -0.0435
volume_behavior           +0.1317    +0.1855
previous_abnormal_move    -0.1273    +0.0356
macd_phase                +0.0693    +0.0154
```

### 观察

1. `volume_behavior` 是本次样本中与 3 日涨幅排名最相关的小分。

```text
volume_behavior Spearman = +0.1855
```

它虽然只是弱正相关，但强于其他小分。对 b2 这种偏短线延续/回踩再启动的信号，量能结构比单纯 MACD 阶段更接近短期表现。

2. `trend_structure` 有一定正向贡献。

```text
trend_structure Spearman = +0.1186
```

趋势结构对短线表现有帮助，但解释力弱于量能结构。

3. `macd_phase` 权重最高，但短期收益相关性最低。

```text
macd_phase Spearman = +0.0154
```

当前 `b2` baseline 中 `macd_phase` 权重为 30%，但在本次样本中几乎不能解释 3 日收益排名。它更像形态门槛/风险过滤项，而不是短线收益排序因子。

4. `price_position` 略负相关。

```text
price_position Spearman = -0.0435
```

较高 price_position 小分没有带来更好的 3 日收益排序。可能原因是较低位置不代表马上启动，而强势票虽然位置偏高，仍可能有短期动量。

5. `previous_abnormal_move` 线性相关为负，排名相关接近 0。

```text
previous_abnormal_move Pearson = -0.1273
previous_abnormal_move Spearman = +0.0356
```

它更像风险识别/形态过滤项，不适合作为 3 日收益排序核心。

## 按 b2 signal 分组

```text
signal   样本数   平均3日涨幅   中位数3日涨幅
B2       24       +1.6206%      -0.6669%
B3       11       +4.6780%      +5.7754%
B4       5        +1.0969%      +2.2180%
B5       4        -3.8312%      -2.9728%
```

关键发现：

- `B3` 在本次样本中明显优于 B2/B4/B5。
- `B5` 表现明显偏弱。
- signal 子类型的区分度，可能高于 baseline_total 本身。

后续如果优化 b2 筛选，建议优先对 signal 子类型做分层，而不是只调整 baseline_total 阈值。

## 按 baseline_total 分桶

```text
baseline_total区间   样本数   平均3日涨幅   中位数3日涨幅
3.6~3.8              22       +1.1083%      -1.3681%
3.8~4.0              13       +3.6322%      +2.7708%
4.0~4.2              6        -1.2739%      +1.6701%
4.2~5.0              3        +5.5180%      +8.7181%
```

观察：

- `3.8~4.0` 桶显著优于 `3.6~3.8`。
- `4.2+` 桶表现最好，但样本数仅 3，稳定性不足。
- `4.0~4.2` 平均为负，说明高分并非单调更优，个别下跌样本会显著影响结果。

## 涨幅前 15 样本

```text
日期          代码        signal  3日涨幅    baseline  小分[趋势/位置/量能/异动/MACD]
2026-04-20   688268.SH   B2      +48.52%   3.80      5/3/3/1/5
2026-04-16   603268.SH   B3      +16.54%   4.00      5/3/3/3/5
2026-04-21   301239.SZ   B3      +10.98%   3.90      4/3/5/4/4
2026-04-20   600522.SH   B2      +10.08%   4.00      5/3/3/3/5
2026-04-20   300191.SZ   B3      +9.99%    4.25      5/4/3/3/5
2026-04-13   001203.SZ   B2      +8.72%    4.25      5/3/4/4/5
2026-04-13   301509.SZ   B3      +7.98%    3.90      4/3/5/4/4
2026-04-17   301338.SZ   B2      +6.51%    4.20      5/3/3/5/5
2026-04-13   300750.SZ   B3      +6.29%    3.70      4/3/3/5/4
2026-04-15   600821.SH   B2      +6.22%    3.65      3/4/3/1/5
2026-04-14   603139.SH   B2      +5.80%    4.05      5/3/2/5/5
2026-04-14   001203.SZ   B3      +5.78%    3.75      4/3/4/4/4
2026-04-21   600869.SH   B3      +3.84%    3.60      4/3/3/1/5
2026-04-16   600251.SH   B2      +3.73%    4.00      5/3/3/3/5
2026-04-17   001267.SZ   B2      +3.53%    4.05      5/3/2/5/5
```

典型样本：

```text
688268.SH
2026-04-20 入选
3日涨幅 +48.52%
baseline_total 3.80
```

它说明爆发型样本未必来自最高 baseline 总分。

## 跌幅前 15 样本

```text
日期          代码        signal  3日涨幅     baseline  verdict / signal_type
2026-04-15   002294.SZ   B2      -16.46%    4.05      FAIL / distribution_risk
2026-04-13   002150.SZ   B5      -9.86%     3.80      WATCH / trend_start
2026-04-20   301560.SZ   B2      -6.83%     4.10      PASS / trend_start
2026-04-16   002422.SZ   B3      -6.63%     3.60      WATCH / trend_start
2026-04-16   300069.SZ   B2      -6.57%     3.75      WATCH / trend_start
2026-04-16   300895.SZ   B2      -5.08%     3.65      WATCH / rebound
2026-04-15   002422.SZ   B2      -4.87%     3.95      FAIL / distribution_risk
2026-04-13   601908.SH   B2      -4.38%     3.80      WATCH / trend_start
2026-04-15   000989.SZ   B2      -4.15%     3.75      WATCH / trend_start
2026-04-20   300464.SZ   B5      -3.85%     3.80      WATCH / trend_start
2026-04-14   300143.SZ   B2      -3.13%     3.80      WATCH / rebound
2026-04-15   600233.SH   B2      -3.12%     3.85      FAIL / distribution_risk
2026-04-14   300204.SZ   B2      -3.01%     3.70      WATCH / rebound
2026-04-14   601908.SH   B4      -2.44%     3.90      FAIL / distribution_risk
2026-04-13   300813.SZ   B3      -2.16%     4.45      FAIL / distribution_risk
```

关键观察：部分下跌样本虽然 baseline_total 高，但 `verdict=FAIL` 或 `signal_type=distribution_risk`。例如：

```text
002294.SZ baseline_total=4.05，3日涨幅=-16.46%，FAIL / distribution_risk
300813.SZ baseline_total=4.45，3日涨幅=-2.16%，FAIL / distribution_risk
```

因此实盘候选过滤不能只看 `baseline_total >= 3.6`，还应叠加 verdict/signal_type 风险过滤。

## 策略含义与建议

### 1. baseline_total 可作为质量过滤线，但不宜单独排序

`baseline_total` 的排名相关约 `+0.2031`，有弱正贡献，但不足以单独承担最终排序。

建议继续保留 `baseline_total >= 3.6` 作为 LLM review 减量阈值或候选质量线，但不要直接按总分排序决定优先级。

### 2. 优先增强 volume_behavior 与 trend_structure

本次样本里：

```text
volume_behavior Spearman = +0.1855
trend_structure Spearman = +0.1186
```

二者是小分中相对更有效的短线收益解释项。

### 3. macd_phase 更适合作为门槛，不适合作为短线排序核心

`macd_phase` 当前权重最高，但与 3 日收益排名几乎无关。

后续可考虑：

- 保留 `macd_phase` 作为 PASS/WATCH/FAIL 或形态门槛。
- 在短线排序分中降低其权重。
- 对 `macd_phase` 高但 `volume_behavior <= 2` 的样本加严处理。

### 4. signal 子类型值得纳入排序/过滤

本次样本中：

```text
B3 明显优于 B2/B4/B5
B5 明显偏弱
```

建议后续排序逻辑加入 signal 分层：

```text
优先：B3
次选：B2、B4
谨慎：B5
```

### 5. 建议候选过滤组合

偏稳健版本：

```text
baseline_total >= 3.6
signal in {B2, B3, B4}
verdict != FAIL
signal_type != distribution_risk
volume_behavior >= 3
```

偏进攻版本：

```text
baseline_total >= 3.8
signal = B3
volume_behavior >= 3
signal_type != distribution_risk
```

## 后续验证方向

1. 扩大样本日期窗口，验证 B3 优势是否稳定。
2. 单独回测：
   - `baseline_total >= 3.6` 原始版本
   - 加 `verdict != FAIL`
   - 加 `signal_type != distribution_risk`
   - 加 `volume_behavior >= 3`
   - 只保留 B3
3. 对 `macd_phase` 权重做消融测试，比较降低权重后的排序相关性。
4. 对 `B5` 单独复盘，判断是否需要降权、延后观察或剔除。

## 结论摘要

```text
baseline_total 与 3日收益：弱正相关，Spearman +0.2031
最有效小分：volume_behavior，其次 trend_structure
macd_phase：权重最高，但短期涨幅相关性几乎为 0
signal 分层：B3 显著优于 B2/B4/B5，B5 偏弱
建议：baseline_total 作为过滤线，最终排序应更多结合 signal、volume_behavior、trend_structure 与 distribution_risk 过滤
```
