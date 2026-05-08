# 2026-05-08 b2 weak 当前状态与调参研究

本文聚焦 `feature/b2-environment-profile-tuning` worktree 中 `b2 weak` 的当前规则与样本表现，沿用本轮 `neutral` 的分析方法，只基于当前 `candidate-v4` 事实做整理，不预设要改哪条规则。

数据口径：

- artifact：`artifacts/review-tuning/b2-2026-01-01-2026-05-06-candidate-v4`
- 样本：`environment_state = weak` 且 `ret5_pct` 非空
- 总样本数：`2437`
- 研究明细：`artifacts/review-tuning/b2-2026-01-01-2026-05-06-candidate-v4/weak_analysis_dataset.csv`
- 结构化摘要：`artifacts/review-tuning/b2-2026-01-01-2026-05-06-candidate-v4/weak_analysis_summary.json`

## 一、当前 weak 的基础结论

当前 weak 不是靠普通总分阈值在做分层，而是：

- 基础 verdict 先给出 `PASS / WATCH / FAIL`
- 再由 `weak` 专用 `A/B relaunch override` 改写部分样本
- 当前 `PASS` 实际只来自很窄的 `A-clean + B2 + rebound + macd_phase < 4.0` 路径

当前分层表现：

- `PASS`
  - `7` 条
  - 5日均值 `+8.42%`
  - 5日中位数 `+4.29%`
  - 胜率 `71.4%`
- `WATCH`
  - `1852` 条
  - 5日均值 `-1.016%`
  - 5日中位数 `-1.335%`
  - 胜率 `41.0%`
- `FAIL`
  - `578` 条
  - 5日均值 `-0.717%`
  - 5日中位数 `-1.11%`
  - 胜率 `41.0%`

这说明当前 weak 的主要问题不是 `PASS` 方向再次反了，而是：

- `PASS` 太窄，样本只有 `7` 条
- `WATCH` 和 `FAIL` 仍然没有形成可靠的正向层次
- `WATCH` 甚至整体比 `FAIL` 更差，说明大部分矛盾还积压在大 `WATCH` 池里

## 二、当前矛盾样本

### 1. `PASS` 但后续走弱

当前只有 `2` 条：

- `688778.SH 2026-02-03`
  - `B2 rebound`
  - `ret5 = -2.17%`
  - `box_position = 0.659`
  - `zxdq_5d_slope_pct = +0.98`
- `002083.SZ 2026-02-03`
  - `B2 rebound`
  - `ret5 = -1.52%`
  - `box_position = 0.688`
  - `zxdq_5d_slope_pct = -2.772`

这两条都来自：

- `B2 rebound`
- `override_bucket = A-clean`

结论：

- 当前 `PASS` 的主要风险不是“整组方向错了”
- 更像 `A-clean` 里仍残留少数边界坏样本
- 但坏样本数量很少，不支持现在就继续大幅收紧 `PASS`

### 2. `WATCH` 但后续大涨

共有 `43` 条 `WATCH` 样本后续 `ret5 >= 20`。

代表性样本：

- `920088.BJ 2026-02-24`：`B2 trend_start WATCH-B`，`ret5=+63.3%`
- `300191.SZ 2026-02-24`：`B2 rebound WATCH-B`，`ret5=+52.05%`
- `603272.SH 2026-03-23`：`B2 trend_start WATCH-C`，`ret5=+48.25%`
- `301396.SZ 2026-03-09`：`B2 trend_start WATCH-B`，`ret5=+40.0%`
- `300461.SZ 2026-03-25`：`B2 rebound WATCH-C`，`ret5=+38.6%`

这批样本的共同点不是某个统一离散小分，而是：

- 绝大多数都不在 `A/B override` 内，`override_bucket = none`
- 大涨样本既有 `WATCH-B` 也有 `WATCH-C`
- 既有 `B2 rebound`，也有 `B2 trend_start`
- `box_position` 经常落在 `0.55 ~ 0.90` 的中右区，不是单纯左侧漏网

结论：

- `WATCH` 的问题不是“少一条简单升级阈值”
- 更像多个风格不同的强弹性样本混在一起
- 如果没有更窄的结构确认，不能直接整体抬升 `WATCH-B` 或 `WATCH-C`

### 3. `FAIL` 但后续大涨

共有 `8` 条 `FAIL` 样本后续 `ret5 >= 20`。

代表性样本：

- `300461.SZ 2026-03-26`：`B3 rebound`，`ret5=+42.17%`
- `301636.SZ 2026-02-03`：`B2 trend_start`，`ret5=+40.29%`
- `920675.BJ 2026-02-24`：`B2 rebound`，`price_position=1`，`ret5=+32.69%`
- `301182.SZ 2026-02-02`：`B2 rebound`，`price_position=2`，`ret5=+32.07%`

结论：

- `FAIL` 里确实有爆发样本
- 但数量很少，而且风格并不单一
- 不能因为这 `8` 条就整体上调 `FAIL` 池，必须继续做窄门候选

## 三、top / bottom 样本的小分结构

### 1. top 50 并没有明显被当前高层 verdict 捕获

weak `ret5` 前 50：

- `WATCH 41`
- `FAIL 8`
- `PASS 1`

也就是说：

- 当前 `PASS` 纯度高，但覆盖极弱
- 真正的大弹性样本主要仍落在 `WATCH`
- 甚至还有一部分留在 `FAIL`

### 2. top / bottom 的离散小分非常接近

top 50 均值：

- `total_score = 3.694`
- `price_position = 2.96`
- `macd_phase = 3.678`
- `box_position = 0.689`
- `zxdq_5d_slope_pct = 1.395`

bottom 50 均值：

- `total_score = 3.701`
- `price_position = 2.86`
- `macd_phase = 3.635`
- `box_position = 0.691`
- `zxdq_5d_slope_pct = 1.957`

这说明：

- 弱环境下 top / bottom 不是靠单个离散小分能清楚分开
- 连 `box_position`、`macd_phase`、`zxdq` 斜率在 top / bottom 的均值上都很接近
- 弱环境的难点是组合结构，而不是简单的单轴阈值

### 3. top 50 更偏 `B2 rebound / B2 trend_start`

top 50 组合：

- `B2 rebound`：`23`
- `B2 trend_start`：`20`
- `B3 rebound`：`7`

bottom 50 组合也很像：

- `B2 rebound`：`21`
- `B2 trend_start`：`18`
- `B3 rebound`：`7`

所以：

- `signal × signal_type` 本身不是充分条件
- 必须回到更窄的结构层继续拆

## 四、`WATCH` 的 `watch_score / watch_tier` 是否有分层

### 1. `watch_tier` 当前是反向的

当前 `WATCH` 分层：

- `WATCH-A`
  - `42` 条
  - 5日均值 `-3.553%`
  - 中位数 `-6.02%`
  - 胜率 `31.0%`
- `WATCH-B`
  - `971` 条
  - 5日均值 `-1.065%`
  - 中位数 `-1.39%`
  - 胜率 `40.6%`
- `WATCH-C`
  - `839` 条
  - 5日均值 `-0.833%`
  - 中位数 `-1.16%`
  - 胜率 `42.1%`

当前弱环境下不是 `WATCH-A > WATCH-B > WATCH-C`，而是相反：

- `WATCH-A` 最差
- `WATCH-C` 反而略好

因此：

- 当前 `watch_tier` 在 weak 里更像命名标签，不是可直接用于升档的排序层

### 2. `watch_score` 也不是单调越高越好

按 `watch_score` 分箱：

- `60-70`：`362` 条，5日均值 `-0.229%`
- `70-80`：`146` 条，5日均值 `-1.000%`
- `80-90`：`35` 条，5日均值 `-2.849%`
- `90-100`：`30` 条，5日均值 `-4.095%`
- `100+`：`23` 条，5日均值 `-4.483%`

说明：

- 高 `watch_score` 在 weak 里不是优势
- `80+` 以后明显更像过热/高风险混池
- `60-70` 才是当前最像“还有弹性但没走坏”的中段分带

### 3. 有一点价值的是 `B2 rebound WATCH 60-70`

`B2 rebound` 且 `watch_score in [60,70)`：

- `21` 条
- 5日均值 `+3.878%`
- 中位数 `+2.04%`
- 胜率 `61.9%`
- 大涨率 `14.3%`

继续叠加 `zxdq_5d_slope_pct >= 0`：

- `16` 条
- 5日均值 `+5.504%`
- 中位数 `+3.165%`
- 胜率 `62.5%`
- 大涨率 `18.8%`

但这里的问题是：

- 样本仍只有 `16` 条
- 内部混有 `WATCH-A` 与 `WATCH-B`
- `price_position`、`volume_behavior` 仍然不统一

结论：

- 这是当前最值得继续观察的一条 `WATCH` 候选窄池
- 但还不够支持直接写成新升档规则

## 五、`FAIL` 的连续 `box_position / close_box_position / box_range_pct`

### 1. `FAIL` 大涨样本并不比全体 `FAIL` 更“极左”多少

全体 `FAIL`：

- `box_position` 中位数 `0.496`
- `close_box_position` 中位数 `0.552`

`FAIL` 里后续大涨样本：

- `box_position` 中位数 `0.551`
- `close_box_position` 中位数 `0.587`

这和 neutral 完全不同。weak 下的 `FAIL` 大涨样本并不是更偏左，反而中位数更靠右。

### 2. 只有极窄左侧门还有一点价值

`FAIL & box_position <= 0.35`：

- `77` 条
- 5日均值 `+0.565%`
- 中位数 `-0.66%`
- 胜率 `41.6%`
- 大涨率 `3.9%`

但一旦放宽到：

- `box_position <= 0.40`：均值只剩 `-0.011%`
- `box_position <= 0.50`：均值回到 `-0.388%`

说明：

- weak `FAIL` 的左侧候选确实存在
- 但有效区间很窄，只在 `box_position <= 0.35` 附近还有一点正均值
- 这个正均值也不够漂亮，中位数仍然为负

### 3. `box_range_pct` 不是 weak 下的有效抬升条件

在 weak 里：

- `box_range_pct >= 80`：5日均值 `-1.5%`
- `box_position <= 0.40 & box_range_pct >= 80`：5日均值 `-1.539%`
- `box_position <= 0.35 & box_range_pct >= 80`：5日均值 `-3.476%`

结论：

- weak 不像 neutral 那样存在“大箱体左侧再启动”优势
- 在 weak 里，大箱体反而更容易混入拖累样本

## 六、是否需要 `zxdq / zxdkx` 斜率 gate

### 1. 整体看，不能直接上斜率 gate

无论全池、`WATCH` 还是 `FAIL`：

- `zxdq_5d_slope_pct >= 0`
- `zxdkx_5d_slope_pct >= 0`

都没有稳定改善整体均值和胜率。

更明显的是：

- `zxdq_5d_slope_pct >= 1`
- `zxdkx_5d_slope_pct >= 1`

往往反而让整体样本更差。

这说明 weak 下：

- 斜率上行不等于更强
- 很多斜率更陡的样本，本身就是更右侧、更容易过热的样本

### 2. 斜率只在极窄子集里有辅助价值

目前只看到两个局部帮助：

- `B2 rebound WATCH score60-70 & zxdq_5d_slope_pct >= 0`
  - `16` 条
  - 5日均值 `+5.504%`
- `B2 rebound WATCH-A & zxdq_5d_slope_pct >= 0`
  - `5` 条
  - 5日均值 `+6.748%`

但这两组都很小：

- 第一组只有 `16` 条
- 第二组只有 `5` 条

结论：

- 当前不支持给 weak 整体加 `zxdq/zxdkx` 斜率 gate
- 斜率只能作为极窄候选池的辅助观察变量

## 七、可疑强组合的窄子集回放

### 1. 值得保留观察：`B2 rebound A-clean`

当前最有证据的一组仍是已存在的 `A-clean`：

- `B2 rebound A-clean` 全体
  - `17` 条
  - 5日均值 `+4.041%`
  - 中位数 `+0.13%`
  - 胜率 `52.9%`
  - 大涨率 `11.8%`

再加轻微收口：`macd_phase < 3.8`

- `10` 条
- 5日均值 `+4.149%`
- 中位数 `+1.975%`
- 胜率 `60.0%`
- 大涨率 `10.0%`

这条的意义是：

- 它证明当前 weak `PASS` 主方向没有错
- 但继续靠这个子集再大幅提纯，样本会迅速缩小到 `10` 条级别
- 现阶段不值得再为了这 `10` 条继续加 gate

### 2. 暂不升级：`B2 trend_start A-borderline`

`B2 trend_start A-borderline`：

- `39` 条
- 5日均值 `+0.263%`
- 中位数 `-0.28%`
- 胜率 `43.6%`

加 `zxdq_5d_slope_pct >= 0` 后：

- `23` 条
- 5日均值 `+0.632%`
- 中位数 `+0.46%`
- 胜率 `52.2%`
- 大涨率 `0.0%`

这组虽然比大 `WATCH` 好一点，但仍然不够像可升档池。

结论：

- 可继续作为观察样本保留
- 当前不值得直接升到 `PASS`

### 3. 暂不升级：`B2 trend_start WATCH-B & macd<4.0`

这组是本轮最像“也许可以捞一部分”的另一类样本：

- `133` 条
- 5日均值 `-0.124%`
- 中位数 `-1.13%`
- 胜率 `41.4%`

不管继续叠加：

- `price_position >= 4`
- `prev >= 5`
- `score >= 4.0`
- `slope >= 0`

都没有形成稳定的正向池。

结论：

- 这条不是“差一刀就能变强”
- 现在更像噪音，不建议继续往升档方向推进

### 4. 暂不升级：`B2 rebound WATCH-A`

`B2 rebound WATCH-A` 全体：

- `17` 条
- 5日均值 `-0.053%`
- 中位数 `-1.33%`

其中：

- `A-clean` 只有 `4` 条，均值 `+5.03%`
- `slope >= 0` 只有 `5` 条，均值 `+6.748%`

这两组都太小。

结论：

- 只能记作小样本观察信号
- 不足以支撑规则改动

## 八、当前结论

### 值得保留的规则 / 候选

1. 保留当前 weak 的 `A-clean -> PASS` 主方向。
   它虽然样本很少，但当前 `PASS` 的正向层次是真实存在的，不应轻易回退。

2. 保留 `B2 rebound A-clean` 作为 weak 的核心正样本画像。
   这是当前最稳定、最接近 weak 主池 `PASS` 的结构。

3. 保留 `B2 rebound WATCH score60-70` 作为下一轮重点观察候选。
   这组已有正均值和较好胜率，但暂时只能继续研究，不能直接升档。

### 更像小样本噪音或暂不采用的方向

1. `WATCH-A / WATCH-B / WATCH-C` 当前排序不能直接用于 weak 升降档。
   尤其 `WATCH-A` 在 weak 下反而最差。

2. 不建议给 weak 整体加 `zxdq/zxdkx` 斜率 gate。
   斜率只在极窄子集里偶尔有帮助，放到整体会误伤更多样本。

3. 不建议整体上调 `FAIL` 左侧样本。
   `box_position <= 0.35` 虽有微弱正均值，但中位数仍为负，只能算窄观察门，不是可交易主池。

4. 不建议把 `B2 trend_start A-borderline`、`B2 trend_start WATCH-B & macd<4.0`、`B2 rebound WATCH-A` 直接升档。
   这些组合都缺少稳定的中位数和胜率支持。

## 九、下一步建议

1. 如果继续做 weak，优先只盯 `B2 rebound WATCH score60-70` 的进一步收口，不要扩到整池。
2. 如果要形成新规则，先补专门针对该窄池的回放测试，再决定是否进生产逻辑。
3. 在没有更强证据前，当前轮次先停在“研究完成、不改 weak 规则”是更稳妥的选择。

## 十、本轮最终候选规则与最新验证

在上述研究基础上，本轮继续只围绕：

- `B2 rebound`
- 原本落在 `WATCH`
- `watch_score` 中段分带

做窄口袋强化，并按 `TDD -> 实现 -> collect -> attach_environment -> correlations -> segments -> recommend -> verify` 重新完整验证。

### 1. 最终候选规则画像

当前保留下来的 weak 候选规则，不是整池放宽，而是一条很窄的 `WATCH -> PASS` 口袋：

- `signal = B2`
- `signal_type = rebound`
- `trend_structure >= 4`
- `price_position <= 2`
- `volume_behavior >= 4`
- `previous_abnormal_move >= 5`
- `macd_phase >= 4.34`
- `4.00 <= total_score <= 4.06`
- `60 <= watch_score_candidate < 70`
- `zxdq_5d_slope_pct >= 0`
- `abnormal_gap_pct <= 12%`

其中：

- `watch_score_candidate` 表示“如果该样本仍留在 WATCH 时”的候选 watch score
- `abnormal_gap_pct` 表示当前价相对“前期最大异动量对应价格”的距离

最后这一条 `abnormal_gap_pct <= 12%` 是本轮最终强化的关键：

- 它不是新的离散小分
- 而是当前新增组内部最有解释力的连续变量
- 作用是剔除“已经离前期异动锚点太远”的右侧透支样本

### 2. 最终 candidate 与 verify 结果

最终 candidate artifact：

- `artifacts/review-tuning/b2-2026-01-01-2026-05-06-candidate-v7-weak-pocket`

最终 weak verify：

- [verification.json](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/artifacts/review-tuning/b2-2026-01-01-2026-05-06-verify-weak-v7/verification.json)

核心结果：

- `delta_ret3_pct = +8.55`
- `delta_ret5_pct = +9.67`
- `candidate_record_count = 13`
- `candidate_win_rate_ret5_pct = 83.3%`

这是本轮 weak 候选规则里，系统级 verify 最好的一版。

### 3. 当前 weak PASS 的最终形态

最终版本下，weak `PASS` 为：

- `14` 条
- 5日均值 `+7.584%`
- 中位数 `+4.25%`
- 胜率 `71.4%`

和最初原始 weak `PASS` 相比：

- 原始 weak `PASS`：`7` 条，5日均值 `+8.42%`
- 本轮最终 weak `PASS`：`14` 条，5日均值 `+7.584%`

这说明：

- 本轮没有明显牺牲纯度
- 但把覆盖从 `7` 条扩到了 `14` 条
- 已经回到接近原始窄池质量的水平

### 4. 真正由新规则新增放行的样本

相对 `candidate-v4`，最终版真正新增进入 `PASS` 的样本为：

- `7` 条
- 5日均值 `+6.749%`
- 中位数 `+4.21%`
- 胜率 `71.4%`
- 大涨率 `28.6%`

这组新增样本已经明显优于：

- 早期放宽到 `27` 条新增的版本
- 以及后续 `14` 条新增的中间版本

也就是说：

- `watch_score` 中段分带 + `abnormal_gap_pct <= 12%`
  这套收口，确实把噪音压下去了

### 5. 当前仍需说明的残余风险

最终新增组里仍有一个明显不符合新规则画像的样本：

- `301308.SZ`
  - `trend_structure = 3`
  - `price_position = 4`
  - `volume_behavior = 3`
  - `macd_phase = 1.88`

这更像：

- 重算口径带来的旁路变化
- 而不是当前这条新规则本身直接抬升的结果

因此现在更合理的判断是：

- 规则主画像已经比较干净
- 剩余个别脏样本，不宜继续归咎到这条新规则本身

### 6. 本轮最终结论

本轮 weak 调参到这里，可以形成明确结论：

1. 当前这条 `B2 rebound` 窄口袋规则，已经从“研究候选”提升到“值得保留的 weak 当前最优候选规则”。
2. `watch_score_candidate` 的中段分带，以及 `abnormal_gap_pct <= 12%`，是这轮真正有效的提纯条件。
3. `box_position` 在这组内部不如“前期异动价距离”有效，不应再作为主收口轴。
4. 当前版本已经不需要继续整池放宽；如果后续还要迭代，应优先解释旁路样本，而不是重新打散这条候选规则。

### 7. 本轮完成态建议

本轮 `b2 weak` 建议到此收工，作为：

- `weak` 当前候选规则保留
- 后续若继续，只做旁路样本复盘或更长期外样本验证

也就是说，本轮目标已从：

- “有没有一条值得试的 weak 规则”

推进到：

- “已经形成一条值得保留的 weak 候选规则，并完成系统级验证”
