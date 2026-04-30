# b2 candidate 2026-03-03 以来 5日收益：signal × verdict 复盘与调参建议

日期：2026-04-29  
仓库：`stock-select`  
分析对象：b2 筛选层输出的 candidate 记录，以及对应 review 层 `verdict`

## 1. 研究背景

本次研究用于回答：

- 2026-03-03 以来，b2 candidate 各信号在 5 日收益上的表现如何？
- `signal × verdict` 是否能形成有效分层？
- 从 5 日涨幅榜 / 跌幅榜看，哪些组合更容易出大涨或大跌？
- 后续 b2 调参应优先关注哪些方向？

结论摘要：当前 b2 的 `verdict` 层未表现出理想的 `PASS > WATCH > FAIL` 分层。`B3-WATCH` 更像高弹性正向组合；`B2-FAIL` 中存在明显误杀；`B2-PASS-trend_start` 在 Bottom20 中过度集中，不符合“高置信精选池”的预期。

## 2. 数据口径

### 2.1 样本来源

- candidate 文件：`/home/pi/.agents/skills/stock-select/runtime/candidates/*.b2.json`
- review verdict：`/home/pi/.agents/skills/stock-select/runtime/reviews/<pick_date>.b2/summary.json`
- forward close 数据：`/home/pi/.agents/skills/stock-select/runtime/prepared/2026-04-29.intraday.pkl`

### 2.2 样本范围

- 日期范围：`2026-03-03` ~ `2026-04-28`
- 覆盖 b2 candidate 日期：40 个交易日
- 统计单位：记录级样本；同一股票不同入选日视为不同 occurrence
- 不纳入 intraday timestamp artifacts，例如 `2026-04-28T...b2.json`

### 2.3 5日收益定义

```text
5日收益 = 第5个后续交易日收盘价 / 入选日收盘价 - 1
```

实现口径：

```python
closes = df[df.trade_date >= pick_date][['trade_date', 'close']].dropna().head(6)
ret_5d_pct = closes.iloc[5].close / closes.iloc[0].close - 1
```

### 2.4 样本数

```text
完整可算 5日收益记录：3171
后续不足 5日记录：165
异常值过滤：1
missing verdict：0
```

异常值过滤说明：剔除 1 条明显缓存异常的 `-100%` 记录。

## 3. 各 candidate signal 的 5日表现

```text
信号   样本数   5日胜率    5日均值    5日中位数
B3+      33     48.48%    -1.79%     -0.25%
B4      360     45.83%    -0.79%     -0.62%
B3      614     44.30%    -0.28%     -1.02%
B2     1862     42.64%    -0.81%     -1.33%
B5      302     33.11%    -1.87%     -3.05%
```

初步观察：

- 单看 candidate signal，没有一个信号的 5日均值和中位数为正。
- `B3+` 胜率最高，但样本仅 33，不能过度解读。
- `B5` 明显最弱，胜率与中位数都垫底。
- `B2` 样本最大，但噪音较大，5日胜率仅 42.64%。

## 4. signal × verdict 的 5日胜率矩阵

### 4.1 B2

```text
verdict   n      胜率      5日均值    5日中位数
FAIL      645    43.57%    -0.12%     -0.93%
PASS      561    41.71%    -1.15%     -2.01%
WATCH     656    42.53%    -1.18%     -1.36%
```

结论：B2 内部几乎没有有效 verdict 分层，且 PASS 最差。

### 4.2 B3

```text
verdict   n      胜率      5日均值    5日中位数
FAIL      159    51.57%    +0.43%     +0.39%
PASS      178    37.64%    -1.46%     -1.59%
WATCH     277    44.40%    +0.07%     -1.02%
```

结论：B3 出现明显反向分层，FAIL 反而最好，PASS 最差。

### 4.3 B3+

```text
verdict   n      胜率      5日均值    5日中位数
FAIL       12    50.00%    -0.78%     -0.11%
PASS        6    33.33%    -7.64%     -8.71%
WATCH      15    53.33%    -0.26%     +0.75%
```

结论：样本过少，但 PASS 仍未体现优势。

### 4.4 B4

```text
verdict   n      胜率      5日均值    5日中位数
FAIL       89    43.82%    -0.45%     -0.75%
PASS      132    35.61%    -3.15%     -3.22%
WATCH     139    56.83%    +1.23%     +0.96%
```

结论：B4-WATCH 明显优于 B4-PASS，是最典型的 WATCH > PASS 失真组合。

### 4.5 B5

```text
verdict   n      胜率      5日均值    5日中位数
FAIL      103    38.83%    -0.95%     -1.55%
PASS      104    22.12%    -3.37%     -3.30%
WATCH      95    38.95%    -1.22%     -3.13%
```

结论：B5 整体偏弱，其中 B5-PASS 极差。

## 5. 5日涨幅榜 Top20 视角

### 5.1 Top20 的 signal × verdict 分布

```text
组合             Top20数   Top20占比   全样本占比   lift
B2 × FAIL          5        25.00%      20.34%     1.23
B3 × WATCH         5        25.00%       8.74%     2.86
B2 × PASS          4        20.00%      17.69%     1.13
B2 × WATCH         4        20.00%      20.69%     0.97
B3 × FAIL          1         5.00%       5.01%     1.00
B4 × WATCH         1         5.00%       4.38%     1.14
```

`lift = Top20占比 / 全样本占比`。

观察：

- `B3-WATCH` 在 Top20 中显著超配，`lift=2.86`。
- `B2-FAIL` 也在 Top20 中超配，说明 FAIL 中存在被误杀的大涨样本。
- `B2-PASS` 能抓到大涨票，但优势不显著，且后续 Bottom20 对照显示其风险较大。

### 5.2 Top20 样本摘要

```text
688268.SH  2026-04-20  B2  WATCH  trend_start        +83.47%
002580.SZ  2026-04-09  B2  PASS   trend_start        +61.16%
688485.SH  2026-04-02  B2  PASS   trend_start        +55.29%
603272.SH  2026-03-23  B2  WATCH  trend_start        +48.25%
301070.SZ  2026-04-01  B2  FAIL   distribution_risk  +47.06%
300461.SZ  2026-03-26  B3  WATCH  rebound            +42.17%
300868.SZ  2026-04-08  B2  WATCH  trend_start        +40.47%
301396.SZ  2026-03-09  B2  WATCH  trend_start        +40.00%
603601.SH  2026-03-24  B2  FAIL   distribution_risk  +39.42%
002082.SZ  2026-03-20  B3  WATCH  trend_start        +38.81%
300461.SZ  2026-03-25  B2  PASS   rebound            +38.60%
688097.SH  2026-03-06  B2  PASS   trend_start        +38.28%
300857.SZ  2026-04-09  B3  WATCH  rebound            +38.03%
300323.SZ  2026-03-04  B2  FAIL   distribution_risk  +37.82%
603618.SH  2026-04-16  B2  FAIL   rebound            +37.64%
000890.SZ  2026-04-16  B3  FAIL   distribution_risk  +35.27%
002384.SZ  2026-04-02  B3  WATCH  rebound            +35.11%
001896.SZ  2026-04-09  B3  WATCH  rebound            +33.28%
301396.SZ  2026-03-10  B4  WATCH  rebound            +32.94%
600683.SH  2026-04-15  B2  FAIL   trend_start        +32.69%
```

## 6. Top20 vs Bottom20 对照

### 6.1 组合对照

```text
组合             Top20数  Top20占比   Bottom20数  Bottom20占比   Top-Bottom
B2 × FAIL          5      25.00%        1          5.00%          +4
B2 × PASS          4      20.00%        7         35.00%          -3
B2 × WATCH         4      20.00%        6         30.00%          -2
B3 × FAIL          1       5.00%        0          0.00%          +1
B3 × PASS          0       0.00%        2         10.00%          -2
B3 × WATCH         5      25.00%        2         10.00%          +3
B4 × WATCH         1       5.00%        2         10.00%          -1
```

观察：

- `B3-WATCH`：Top20 多，Bottom20 少，是当前更值得上调关注级别的组合。
- `B2-FAIL`：Top20 明显多于 Bottom20，是当前最明显的“误杀池”。
- `B2-PASS`：Top20 有一定数量，但 Bottom20 更多，说明其并不是稳定高置信精选池。
- `B3-PASS`：Top20 为 0，Bottom20 有 2，表现弱于 B3-WATCH。

### 6.2 Top20 signal_type 细分

```text
组合 + signal_type                  Top20数   占比
B2 × WATCH × trend_start              4      20%
B3 × WATCH × rebound                  4      20%
B2 × FAIL  × distribution_risk        3      15%
B2 × PASS  × trend_start              3      15%
```

### 6.3 Bottom20 signal_type 细分

```text
组合 + signal_type                  Bottom20数   占比
B2 × PASS  × trend_start              6        30%
B2 × WATCH × trend_start              5        25%
B3 × PASS  × trend_start              2        10%
B3 × WATCH × trend_start              2        10%
```

关键启发：`B2-PASS-trend_start` 在 Bottom20 中占比 30%，说明该组合并不安全；`B2-FAIL-distribution_risk` 却在 Top20 中占比 15%，说明 distribution_risk 判定可能误杀高弹性票。

## 7. 调参建议

以下建议分为“低风险观测型调整”和“需要进一步样本验证的策略调整”。建议后续先做 research/backtest，再进入代码变更。

### 7.1 调参优先级一：重审 `B3-WATCH` 的升级条件

事实依据：

- `B3-WATCH` 在 Top20 中占 25%，全样本占比仅 8.74%，`lift=2.86`。
- `B3-WATCH` Top20 有 5 条，Bottom20 仅 2 条。
- B3 组内，PASS 胜率 37.64%，WATCH 胜率 44.40%，FAIL 胜率 51.57%。虽然 B3-FAIL 也强，但 B3-WATCH 的榜单弹性更明确。

建议：

1. 将 `B3-WATCH` 单独作为“高弹性观察池”输出，不急于直接升级为 PASS。
2. 后续研究 `B3-WATCH` 的共性条件，例如：
   - `signal_type=rebound` vs `trend_start`
   - 入选日是否缩量更充分
   - 是否站上 MA25 / zxdq
   - 5日内是否存在题材或行业共振
3. 如果新增高弹性标签，可考虑：
   - `verdict=WATCH`
   - 增加 `watch_reason=elastic_b3_watch`
   - 或在 summary/ranking 中提高排序权重，但不改变 PASS 口径。

### 7.2 调参优先级二：拆解 `B2-FAIL-distribution_risk` 的误杀来源

事实依据：

- `B2-FAIL` Top20 有 5 条，Bottom20 仅 1 条。
- `B2-FAIL-distribution_risk` 在 Top20 中有 3 条，占 15%。
- 代表样本：`301070.SZ`、`603601.SH`、`300323.SZ`。

建议：

1. 不建议简单把 `distribution_risk` 从 FAIL 放宽为 WATCH/PASS。
2. 应拆分 `distribution_risk`：
   - 真派发风险：高位长上影、放量滞涨、收盘弱、后续承接差。
   - 高弹性误杀：强趋势中加速前的高波动、题材驱动、放量突破后仍能承接。
3. 建议新增二级标签或诊断字段：
   - `distribution_risk_subtype=exhaustion_distribution`
   - `distribution_risk_subtype=elastic_breakout_risk`
4. 若满足“弹性强但风险高”的条件，优先从 FAIL 升为 WATCH，而不是直接升 PASS。

### 7.3 调参优先级三：收紧或重新定义 `B2-PASS-trend_start`

事实依据：

- `B2-PASS` Top20 有 4 条，但 Bottom20 有 7 条。
- `B2-PASS-trend_start` 在 Bottom20 中有 6 条，占 30%。
- B2 组内，FAIL 胜率 43.57%，WATCH 42.53%，PASS 41.71%，PASS 最差。

建议：

1. 当前 `B2-PASS-trend_start` 不应被视为高置信精选池。
2. 对 `B2-PASS-trend_start` 增加额外风险约束，例如：
   - 入选日不能出现明显冲高回落。
   - 入选日前 5~10 日不能已有过大累计涨幅。
   - 入选日相对 MA25 / zxdq 不宜过度乖离。
   - 成交量结构需避免“单日爆量后承接不足”。
3. 在未验证前，不建议继续放宽 PASS；更适合将一部分 B2-PASS 下调为 WATCH。

### 7.4 调参优先级四：降低 `B5` 权重

事实依据：

- B5 全样本 5日胜率仅 33.11%。
- B5-PASS 胜率仅 22.12%，5日均值 -3.37%，中位数 -3.30%。
- Top20 中没有 B5，说明其缺乏短期尖峰弹性。

建议：

1. 暂时不把 B5 作为主要进攻信号。
2. 若保留 B5，应默认降为低优先级观察，或要求额外强过滤：
   - 放量结构改善；
   - MA25/zxdq 支撑明确；
   - MACD 共振强；
   - 近期未出现连续回撤。
3. 可考虑在 review 层规定：B5 仅在强条件共振时才允许 WATCH/PASS，否则默认 FAIL/WATCH 下沿。

### 7.5 调参优先级五：不要只优化 PASS 总数，要优化 PASS 的尾部风险

目前问题不是 PASS 太少，而是 PASS 的尾部亏损样本过多。尤其 `B2-PASS-trend_start` 在 Bottom20 中集中。

建议后续评价指标增加：

```text
PASS 5日胜率
PASS 5日中位数
PASS Bottom20 占比
PASS 最大回撤尾部数量
WATCH Top20 占比
FAIL Top20 占比（误杀率）
```

其中：

- `FAIL Top20 占比` 可作为误杀率 proxy。
- `PASS Bottom20 占比` 可作为高置信池风险污染 proxy。

## 8. 后续研究计划建议

### 8.1 样本层面

1. 做 `Top50 vs Bottom50`，降低 Top20 极端值偶然性。
2. 对 Top20/Bottom20 做按股票去重版本，检查是否被重复样本驱动。
3. 按 4/20 筛选层改版前后拆分，判断新 b2 screening flow 对分布的影响。

### 8.2 因子层面

建议对以下组合逐条做因子画像：

- `B3-WATCH` 赢家 vs 输家
- `B2-FAIL-distribution_risk` 赢家 vs 普通 FAIL
- `B2-PASS-trend_start` 输家 vs 赢家

候选因子：

```text
入选日前 5/10 日累计涨幅
入选日涨幅与振幅
入选日上影线比例
入选日成交量 / 前5日均量
前20日最大量 / 入选日成交量
close 与 MA25 / zxdq 的偏离
MA25 近5日斜率
zxdq 近5日斜率
MACD weekly/daily state
是否题材/行业共振
```

### 8.3 代码调参顺序

建议顺序：

1. 先写研究脚本，不改生产逻辑。
2. 确认 `B3-WATCH` 和 `B2-FAIL-distribution_risk` 的共性因子。
3. 再增加测试，覆盖：
   - `B3-WATCH` 高弹性升级/标记逻辑；
   - `distribution_risk` 子类型拆分；
   - `B2-PASS-trend_start` 尾部风险降级。
4. 最后才修改 `src/stock_select/reviewers/b2.py` 的 verdict 逻辑。

最低验证命令：

```bash
/home/pi/.local/bin/uv run pytest tests/test_reviewers_b2.py tests/test_b2_logic.py tests/test_review_orchestrator.py -q
```

完整验证：

```bash
/home/pi/.local/bin/uv run python -m pytest -q
```

## 9. 结论

本次复盘的核心结论是：

```text
1. 当前 b2 verdict 层没有形成 PASS > WATCH > FAIL 的理想分层。
2. B3-WATCH 是目前最值得上调关注级别的组合，具备明显 5日涨幅榜超配。
3. B2-FAIL，尤其 B2-FAIL-distribution_risk，是明显误杀池。
4. B2-PASS-trend_start 在 Bottom20 中过度集中，不符合“高置信精选池”的预期。
5. B5 当前表现最弱，应降权或附加强过滤条件。
```

后续调参不建议简单放宽 PASS，而应优先做三件事：

```text
A. 给 B3-WATCH 增加高弹性观察标签或排序加权；
B. 拆分 distribution_risk，识别真实派发与高弹性误杀；
C. 收紧 B2-PASS-trend_start 的尾部风险条件。
```
