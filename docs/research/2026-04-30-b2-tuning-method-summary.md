# 2026-04 ~ 2026-04-30 本轮 b2 调参方法总结

## 目标

本轮调参的核心目标不是“把 PASS 做大”，而是：

1. 保持 `PASS` 为相对高置信池，避免明显过宽。
2. 解决当前 live 代码状态下的主要问题：**强 `WATCH` 未能升为 `PASS`**。
3. 用真实 runtime 候选、review JSON、prepared cache 和多轮回测来验证，而不是只看主观印象或旧汇总文件。

---

## 一、先做 runtime / 代码真值对齐，不信旧 artifact

### 关键教训
在继续调 b2 之前，先验证“当前仓库 + 当前 runtime”到底在发生什么。

本轮首先做了：

- 读取 `runtime/reviews/<pick_date>.b2/*.json`
- 优先使用 `baseline_review` 里的字段：
  - `signal`
  - `signal_type`
  - `trend_structure`
  - `price_position`
  - `volume_behavior`
  - `previous_abnormal_move`
  - `macd_phase`
  - `total_score`
  - `verdict`
- 用 live 代码重新跑 `infer_b2_verdict(...)`
- 对比 JSON 里的旧结论和当前逻辑的重算结果

### 结论
此前怀疑存在大量 `PASS -> WATCH` 误降，但在**当前 live 代码状态**下重算后，这个问题并不存在或不再是主问题。

因此调参方向立即改为：

> 不再围绕 PASS->WATCH 误降，而是转向 **WATCH->PASS 漏升档** 与 **WATCH winners**。

---

## 二、用 WATCH winners 反推当前规则的真正漏点

### 做法
对 2026-04 当前 `WATCH` 样本做 3日 / 5日 forward return 分析，抽取高收益 `WATCH` 样本，逐条查看它们为什么没有升为 `PASS`。

使用数据来源：

- 候选：`runtime/candidates/*.b2.json`
- 逐票 review：`runtime/reviews/<pick_date>.b2/*.json`
- prepared cache：优先最新 full cache（本轮实际可用的是 `runtime/prepared/2026-04-28.pkl`）

### 关键发现
高收益 `WATCH` 的主因不是 `price_position` 或 `total_score`，而是：

```text
macd<4.5
```

也就是说：

> 当前 strict PASS 最大的漏点，是很多强 `trend_start` 样本只差一个 MACD 边界。

---

## 三、第一步最小化放宽：只给强 trend_start 开窄门

### 调整思路
不全面放宽 PASS，而是只给最可能被误伤的强 `trend_start` 开一个窄通道。

### 实现逻辑
在 `infer_b2_verdict(...)` 中新增分支：

```text
signal_type == trend_start
macd_phase >= 4.2
previous_abnormal_move >= 5.0
trend_structure >= 4.0
price_position >= 3.0
volume_behavior >= 3.0
total_score >= 4.0
=> PASS
```

### TDD 步骤
1. 先写失败测试：
   - 强 `trend_start` + `macd=4.3` 应升 `PASS`
   - `rebound` 同样配置仍保持 `WATCH`
   - `trend_start` 但 `total_score=3.99` 保持 `WATCH`
2. 跑 RED
3. 改代码
4. 跑 targeted tests 和 broader suites

### 效果
这一步显著增加了 `WATCH -> PASS` 数量，并提高了 `PASS` 对高收益 `trend_start` 的覆盖。

但同时发现：

- `PASS` 数量增加较多
- `PASS` 中位数和一部分胜率受到稀释

也就是说：

> 方向对了，但需要第二步收口，而不是继续无脑放宽。

---

## 四、第二步 refine：只对更强的 trend_start 再放一层更低 MACD

### 动机
第一步之后，仍有一批非常强的 `trend_start` WATCH 留在池子里，主要特征是：

- `trend_structure=4`
- `price_position` 很高（常见 5）
- `total_score` 很高（常见 4.2+）
- 但 `macd_phase` 只有 `3.5~4.2`

### 实现逻辑
将 relaxed `trend_start` 通道细化为：

```text
signal_type == trend_start
previous_abnormal_move >= 5.0
trend_structure >= 4.0
price_position >= 3.0
volume_behavior >= 3.0
total_score >= 4.0
and (
  macd_phase >= 4.2
  or (
    macd_phase >= 3.5
    and price_position >= 5.0
    and total_score >= 4.2
  )
)
=> PASS
```

### 核心思想
不是单纯降 MACD，而是：

- 只有在**更强 price_position + 更强 total_score** 下
- 才允许更低 MACD 的 `trend_start` 升为 `PASS`

### 效果
这一步比第一步更克制，吸收了更多高质量 `trend_start` 强票，同时没有明显把 `PASS` 再做脏。

---

## 五、第三步收口：加轻量 overheat / high-extension 过滤

### 动机
继续放宽 `trend_start` 后，必须防止：

- 高位过热
- 明显远离均线
- 高位滞涨 / late extension

这类样本混进 `PASS`。

### 实现方式
为 relaxed `trend_start` PASS 分支增加两个轻量几何代理：

```text
close_above_ma25_pct = (close / ma25 - 1) * 100
ma25_above_zxdkx_pct = (ma25 / zxdkx - 1) * 100
```

并定义：

```text
overheat_extension =
  close_above_ma25_pct >= 10
  or ma25_above_zxdkx_pct >= 15
```

只在 relaxed `trend_start` PASS 分支上要求：

```text
and not overheat_extension
```

### 为什么这样做
这两个量里：

- `close_above_ma25_pct` 更像风险护栏
- `ma25_above_zxdkx_pct` 在当前窗口下比单纯 `close/MA25` 更有信息量

### TDD 步骤
1. 加失败测试：
   - 正常 moderate extension 仍 `PASS`
   - `close_above_ma25_pct >= 10` 时保持 `WATCH`
   - `ma25_above_zxdkx_pct >= 15` 时保持 `WATCH`
2. 跑 RED
3. 修改 `review_b2_symbol_history()`，把这两个输入传给 `infer_b2_verdict(...)`
4. 跑 targeted 和 broader tests

### 效果
这一步之后：

- `PASS` 胜率提升
- `PASS` 平均 5 日收益继续提升
- `WATCH` 进一步被削弱
- 没有产生 `PASS -> WATCH` 的误伤回滚

也就是说：

> 这层过滤像“质量护栏”，不是重新收紧整个 PASS。

---

## 六、实时验证方式：每一步都要重算，不凭感觉

### 统一验证口径
每次改完都做两层验证：

#### 1. 规则层 / 测试层
至少跑：

```bash
/home/pi/.local/bin/uv run pytest tests/test_reviewers_b2.py tests/test_b2_logic.py tests/test_review_orchestrator.py -q
/home/pi/.local/bin/uv run python -m pytest tests/test_macd_waves.py tests/test_review_orchestrator.py tests/test_reviewers_b2.py tests/test_b2_logic.py tests/test_reviewers_b1.py tests/test_reviewers_dribull.py tests/test_dribull_logic.py -q
```

#### 2. 运行时 / 回测层
使用当前 live 代码重新计算：

- `PASS/WATCH/FAIL` 统计
- 3日 / 5日收益
- Top20 / Top50 涨幅榜里 PASS / WATCH 占比
- `WATCH -> PASS` / `PASS -> WATCH` 迁移数量
- 相关性

### 重要原则
> 测试通过 ≠ 调参有效。  
> 必须再跑真实 runtime + prepared cache 的表现验证。

---

## 七、相关性与排序验证：不是只看 verdict，还要看 PASS 内部分层

### 相关性
本轮后期的 current b2 5日相关性显示：

相对更有用的因子：

- `total_score`
- `price_position`
- `ma25_above_zxdkx_pct`
- `macd_phase`
- `verdict_num`

相对弱的因子：

- `volume_behavior`
- `previous_abnormal_move`
- 单独的 `close_above_ma25_pct`

这说明：

> `close_above_ma25_pct` 更适合作为风险护栏，而不是正向打分主轴。

### PASS 内部排序
本轮还验证了：

- “所有 PASS 一起看”不如“PASS 内部按分数再排序”
- 每日 top-1 / top-3 PASS 的表现，显著优于全部 PASS

这意味着：

> 当前 b2 的价值不仅在 `PASS/WATCH` 分层，也在 `PASS` 池内部的排序能力。

---

## 八、为什么不能把 4 月结论直接套到 3 月
本轮也把同样的“每日 top-3 PASS”方法套到了 3 月，结果明显更差：

- 次日接近打平甚至偏弱
- 3日明显为负
- `rebound` 尤其差

结论非常清楚：

> 4 月有效，不代表 3 月有效。
> 当前 b2 调参结果是**有 regime 依赖**的。

因此每次总结都必须强调：

- 按月份 / 市场阶段拆开验证
- 不要把 4 月强势环境下的细化规则，直接当成跨阶段稳定真理

---

## 九、本轮 b2 调参的可复用方法论
最终可以沉淀成下面这套流程：

### 1. 先做 live 代码 / live runtime 对齐
- 不信旧 artifact
- 用当前代码重算当前 JSON 样本
- 先确认主问题是不是还存在

### 2. 优先找 `WATCH winners`
- 不是先盯着 `PASS losers`
- 先找最该升档却没升的样本

### 3. 不做大改，只开窄门
- 先锁定最强的一类（本轮是 `trend_start`）
- 只给它加一条窄放宽路径
- 不要同步放宽所有 signal_type

### 4. 放宽之后必须马上收口
- 一旦 PASS 扩容成功，就要立刻找“过热 / late extension / 滞涨”样本
- 用轻量风险护栏把脏样本挡掉

### 5. 用真实回测结果来决定下一步，而不是靠直觉
每轮至少看：
- PASS / WATCH / FAIL 5日表现
- Top20 / Top50 里 PASS 占比
- PASS 内部分数排序表现
- 相关性
- 月份分拆表现

### 6. prompt 跟机械规则同步收束
- 让 LLM 重点看：
  - `trend_start` vs `rebound`
  - 结构是否完整
  - 是否过热 / 高位滞涨
  - 量价只做辅助，不做机械一票否决
- prompt 要像裁判规则，不要像规则大全

---

## 十、适合长期保留的原则
可以把本轮 b2 调参归纳成几句话：

```text
先验证 live 代码问题是否真实存在。
先找 WATCH winners，不先找 PASS losers。
先开窄门，不搞大放水。
放宽后立刻加护栏，优先防过热而不是继续降 MACD。
用 runtime + prepared cache 重算结果，用月度分拆验证，不凭主观印象。
LLM prompt 只强调少数关键裁判点，和机械口径对齐。
```

这套东西，已经可以当成之后继续调 b2 的固定作业流了。
