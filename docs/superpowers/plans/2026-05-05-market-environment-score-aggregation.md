# 环境分析三维累计评分实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 把环境分析正式状态从旧的规则合成改为三维累计评分映射，同时保留旧规则与多数表决诊断结果，最终重算 `2026-01-01 ~ 2026-04-30` 的三套区间对照。

**架构：** 保留箱体 / 趋势 / MACD 底层打分函数；新增 score-based 状态映射函数作为正式状态来源；把旧规则合成提取为诊断路径；新增 vote-based 诊断路径；补充测试并输出研究窗口重算结果。

**技术栈：** Python, pandas, pytest, 现有 `stock_select.market_environment` 模块。

---

### Task 1: 锁定新口径测试

**Files:**
- Modify: `tests/test_market_environment.py`

- [ ] **Step 1: 写失败测试覆盖新的单维诊断边界**
  - `M7` 不再单独解释为 `weak`
  - `M8/M9` 只有叠加 `S6+` 或 `box risk` 才解释为 `weak`

- [ ] **Step 2: 写失败测试覆盖 score-based 状态映射阈值**
  - `combined_total=8` -> `neutral`
  - `combined_total=-10` -> `weak`
  - `combined_total=19` -> `strong`

- [ ] **Step 3: 写失败测试覆盖 `evaluate_market_environment()` 的新增诊断字段**

- [ ] **Step 4: 运行聚焦测试并确认失败**

Run: `uv run pytest -q tests/test_market_environment.py`


### Task 2: 实现新的环境状态聚合层

**Files:**
- Modify: `src/stock_select/market_environment.py`

- [ ] **Step 1: 提炼 MACD / trend / box 诊断映射 helper**

- [ ] **Step 2: 实现 score-based 单指数与双指数状态映射 helper**
  - 新正式状态来源基于 `combined_total`
  - 初始阈值：`strong >= 10.0`，`weak <= -4.0`

- [ ] **Step 3: 把旧规则合成逻辑保留为独立诊断路径**

- [ ] **Step 4: 新增多数表决诊断路径**

- [ ] **Step 5: 更新 `evaluate_market_environment()` 输出结构**
  - `state`
  - `score_based_state`
  - `rule_based_state`
  - `vote_based_state`
  - `score_based_total`
  - `score_thresholds`
  - `raw_state` 改为 score-based raw state 的兼容字段


### Task 3: 让平滑逻辑兼容新正式状态

**Files:**
- Modify: `src/stock_select/market_environment.py`
- Modify: `tests/test_market_environment.py`

- [ ] **Step 1: 判断现有平滑状态机是否继续复用**
  - 若可复用，则把输入切到新的 score-based raw state
  - 若不稳定，则缩减为更轻量的平滑规则

- [ ] **Step 2: 为关键边界补测试**
  - `2026-01-20 ~ 2026-01-22` 不整段落到 `weak`
  - `2026-01-30 ~ 2026-02-03` 保持 `weak`
  - `2026-02-05 ~ 2026-03-02` 回到 `neutral`

- [ ] **Step 3: 重新运行聚焦测试直到通过**

Run: `uv run pytest -q tests/test_market_environment.py`


### Task 4: 产出研究窗口三套结果对照

**Files:**
- No required code changes unless验证暴露问题

- [ ] **Step 1: 写一个最小诊断脚本或临时命令，直接读取指数历史并打印三套状态**

- [ ] **Step 2: 运行 `2026-01-01 ~ 2026-04-30` 重算**

- [ ] **Step 3: 提取区间切换点与关键样本日对照**

- [ ] **Step 4: 若阈值与用户目标不一致，只微调阈值并回归测试**


### Task 5: 最终验证

**Files:**
- No code changes expected unless验证失败

- [ ] **Step 1: 运行聚焦测试**

Run: `uv run pytest -q tests/test_market_environment.py`

- [ ] **Step 2: 如环境输出结构影响 CLI，再补跑相关切片**

Run: `uv run pytest -q tests/test_cli.py -k "market_env or environment_snapshot"`

- [ ] **Step 3: 检查最终 diff，确认没有误伤既有改动**
