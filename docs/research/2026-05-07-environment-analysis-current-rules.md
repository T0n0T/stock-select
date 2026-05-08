# 2026-05-07 当前环境分析规则说明

## 目的

本说明用于固定当前 `feature/b2-environment-profile-tuning` 分支上的环境分析口径，避免后续再把“环境状态机如何切换”“review 如何吃到环境”混在研究结论里口头传播。

本文只说明当前已经落到代码中的实现，不讨论备选方案。

## 一、环境分析链路

当前 EOD 主链路为：

1. `screen --pick-date` / `run --pick-date`
2. `ensure_market_environment(...)` 保证目标日有环境区间
3. `review` 读取目标日环境区间
4. `get_method_environment_profile(method, state)` 映射成方法级 profile
5. reviewer 按 profile 改变小分、总分和 verdict

对应代码位置：

- 环境状态机与区间读写：
  [src/stock_select/market_environment.py](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/src/stock_select/market_environment.py)
- review 侧接入：
  [src/stock_select/cli.py](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/src/stock_select/cli.py)
- 方法级环境 profile：
  [src/stock_select/environment_profiles.py](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/src/stock_select/environment_profiles.py)
- `b2` reviewer：
  [src/stock_select/reviewers/b2.py](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/src/stock_select/reviewers/b2.py)

## 二、当前状态机规则

当前分支已经切换为以下规则：

- 进入 `strong` 不需要缓冲，命中即切 `strong`
- 进入 `weak` 不需要缓冲，命中即切 `weak`
- 只有进入 `neutral` 需要缓冲
- 当上一状态为 `strong` 或 `weak` 时，必须连续两天 `raw_state == neutral`，才真正切到 `neutral`

可以把它理解为：

> `strong/weak` 是直接表态；`neutral` 是确认后的修复区，而不是任意转场时默认插入的一天占位状态。

因此当前实现不再保留旧逻辑中的两条规则：

- `weak -> strong` 强制先落一天 `neutral`
- `strong -> weak` 强制先落一天 `neutral`

## 三、区间表现含义

这套规则下，环境区间会比旧逻辑更少、更长：

- `strong` 与 `weak` 会更频繁直接相邻
- 单日 `neutral` 小岛大幅减少
- `neutral` 往往滞后一天开始
- 最新几天如果原始分数已经转强，不会因为“还没过渡完”而继续停在 `neutral`

对 `review` 来说，这意味着：

- profile 切换更及时
- 强弱环境下的 reviewer 权重与 verdict 门槛会更早生效
- `neutral` 只在确有修复/分化确认时才接管

## 四、当前 review 影响范围

当前真正受环境影响的是：

- `b1` profile
- `b2` profile
- `b2 reviewer` 中的多项子分与 verdict 逻辑

其中 `b2` 影响最大，包含：

- `trend_structure` 打分口径
- `price_position` 容忍度
- `previous_abnormal_move` 严格/宽松程度
- `macd_phase` 倾向
- `PASS/WATCH` 的阈值

因此环境不是只写入 `summary.json` 的说明字段，而是会真实改变 review 结论。

## 五、runtime 刷新方式

默认 runtime 环境历史文件位置为：

```text
~/.agents/skills/stock-select/runtime/environment/history.json
```

如果要用当前代码重建环境区间，推荐两种方式：

1. 通过 EOD `screen/run` 让缺失日期按需补齐。
2. 用调参 artifact 的 `samples.csv` 调用
   [scripts/review_tuning_backfill_environment_history.py](/home/pi/Documents/agents/stock-select/.worktrees/b2-environment-profile-tuning/scripts/review_tuning_backfill_environment_history.py)
   一次性回填历史区间。

第二种适合批量重建整段历史，且已经支持在 `index_daily_market` 缺失时回退到 `daily_index`。

## 六、当前确认口径

截至本文写入时，当前分支环境分析的确认口径是：

- 进入 `strong/weak` 直接切换
- 进入 `neutral` 需要两天确认
- 这套规则已经落到代码与测试，不再只是口头约定

