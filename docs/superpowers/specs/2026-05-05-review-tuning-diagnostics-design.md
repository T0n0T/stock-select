# 多方法多环境 Review 调参诊断 Skill 设计

## 目标

在 `stock-select` 仓库内新增一套可复用的调参诊断能力，用于评估不同方法在不同市场环境下的 review 打分是否真正对未来收益有解释力，并据此给出后续调参建议与实现任务。

本次设计只覆盖：

- 分析诊断
- 调参建议
- 后续任务拆解
- 验证脚本体系

本次设计明确不直接覆盖：

- 自动修改 `src/` 下的生产代码
- 自动提交代码 PR
- 自动替用户决定最终参数

## 背景与问题

当前仓库已经积累了按日期和方法输出的 review 结果，也已有 `review_top3_stats.py` 这类验证脚本，但这些能力还不够支撑“按方法 + 按环境 + 按未来收益”系统诊断 review 打分质量。

当前缺口主要有四类：

1. 样本采集分散
   - review 样本散落在 `reviews/YYYY-MM-DD.<method>/summary.json`
   - 没有统一脚本抽取总分、子项分数、verdict 和未来收益

2. 环境标签未纳入统一研究流程
   - 正式环境口径已经以 `score_based_state` 为主
   - 但 review 样本还没有形成稳定的“样本 -> 环境状态”映射产物

3. 调参判断缺少统一规则
   - 什么时候只调阈值
   - 什么时候调权重
   - 什么时候应建议改 reviewer 计分函数
   - 目前没有固定决策树

4. 验证脚本职责不清
   - `scripts/review_top3_stats.py` 更像单次研究工具
   - 还不是“调参后复验”的统一末端验证脚本

因此，本次需要先建立一套“可重复执行、能约束智能体步骤、输出结构化结论”的诊断体系。

## 范围

### In Scope

- 新增仓库内 skill，用于约束智能体执行调参诊断流程
- 新增一组 `scripts/` 下的诊断脚本
- 支持所有方法：
  - `b1`
  - `b2`
  - `dribull`
  - `hcr`
- 支持所有环境组合：
  - `weak`
  - `neutral`
  - `strong`
- 默认环境口径使用 `score_based_state`
- 统一输出结构化 artifacts
- 改造 `scripts/review_top3_stats.py`，使其更适合调参后的复验
- 补充对应测试

### Out Of Scope

- 自动直接修改 `src/stock_select/environment_profiles.py`
- 自动直接修改 `src/stock_select/reviewers/*.py`
- 自动创建或提交 PR
- 自动替换现有研究文档体系
- 处理与本次诊断无关的 runtime 结构调整

## 已确认约束

用户已明确要求本次能力满足以下边界：

1. 覆盖所有方法和环境组合，不只服务 `b2`
2. 这套 skill 的职责是：
   - 分析诊断
   - 给出调参建议
   - 指导后续任务
3. 这套 skill 不直接执行代码改动闭环
4. 最后的验证阶段允许并预计需要先改造 `scripts/review_top3_stats.py`

## 总体方案

采用“通用 skill + 模块化脚本 + 统一 artifacts 目录”的方案。

不采用单一大脚本，原因如下：

- 单脚本同时承担采集、分析、建议、验证，职责会迅速膨胀
- 各方法和环境维度的扩展会让一个总控脚本变得脆弱
- 单步骤脚本更容易单测和重复执行
- skill 可以只负责约束智能体顺序与决策，不承担重计算

总体结构如下：

1. skill 负责流程
2. `scripts/` 负责计算
3. `artifacts/review-tuning/<run_id>/` 负责沉淀结果
4. 末端验证复用并扩展 `review_top3_stats.py`

## Skill 设计

### 路径

新增 skill：

```text
.agents/skills/review-tuning-diagnostics/
```

至少包含：

```text
.agents/skills/review-tuning-diagnostics/SKILL.md
```

如果后续需要，也可以再增加：

- `references/`
- `agents/openai.yaml`

但第一版不要求过度扩展。

### Skill 职责

skill 只做三件事：

1. 规范智能体按固定顺序完成诊断
2. 约束智能体按统一决策树形成建议
3. 输出后续实现任务，而不是直接进入代码改动

### Skill 必须强制的执行顺序

每次执行调参诊断都必须遵循以下顺序：

1. 收集样本
2. 贴环境标签
3. 计算相关性
4. 计算分段统计
5. 生成调参建议
6. 如存在改后结果，再做复验

不允许跳过中间任何一步直接下调参结论。

### Skill 输出要求

每次执行后，智能体至少要交付：

- `summary.md`
- `recommendations.json`
- 对关键证据的简要总结
- 下一轮实现任务列表
- 建议测试命令
- 建议验证命令

### Skill 禁止事项

skill 必须明确禁止智能体：

- 直接改动 `src/` 代码
- 不看样本覆盖率就下强结论
- 只看总分均值而忽略分层
- 根据单个环境的小样本直接建议重写 reviewer

## 脚本体系设计

脚本全部放在仓库 `scripts/` 目录下。

### 1. `scripts/review_tuning_collect.py`

职责：

- 遍历 `reviews/YYYY-MM-DD.<method>/summary.json`
- 抽取每个样本的：
  - `total_score`
  - `trend_structure`
  - `price_position`
  - `volume_behavior`
  - `previous_abnormal_move`
  - `macd_phase`
  - `verdict`
- 从 prepared cache 计算：
  - `ret3_pct`
  - `ret5_pct`

输入参数：

- `--methods`
- `--start-date`
- `--end-date`
- `--runtime-root`
- `--prepared-root`
- `--output-dir`

输出：

- `samples.csv`

样本主键至少包含：

- `method`
- `pick_date`
- `code`

### 2. `scripts/review_tuning_attach_environment.py`

职责：

- 给每条样本补环境标签
- 默认按 `score_based_state` 贴标签
- 保留将来切换其他环境口径的参数位

输入参数：

- `--samples`
- `--runtime-root`
- `--environment-key`
- `--output-dir`

输出：

- `samples_with_env.csv`

新增字段至少包括：

- `environment_state`

### 3. `scripts/review_tuning_correlations.py`

职责：

- 分别计算总分和子项分数与未来收益之间的相关性
- 同时输出 Pearson 和 Spearman
- 同时支持整体、按方法、按环境、按 `method x environment` 四种切法

输入参数：

- `--samples`
- `--output-dir`

输出：

- `correlations.json`
- `correlations.csv`

至少覆盖：

- `total_score` vs `ret3_pct`
- `total_score` vs `ret5_pct`
- 每个子项 vs `ret3_pct`
- 每个子项 vs `ret5_pct`

### 4. `scripts/review_tuning_segments.py`

职责：

- 按子项分数 1-5 每档分析收益
- 按总分区间分析收益
- 按 `verdict` 分层分析收益
- 按方法、环境、`method x environment` 输出统计

输入参数：

- `--samples`
- `--output-dir`

输出：

- `segments.json`
- `segments.csv`

每个分段至少输出：

- 样本数
- `ret3_pct` 平均值
- `ret5_pct` 平均值
- `ret3_pct` 胜率
- `ret5_pct` 胜率

### 5. `scripts/review_tuning_recommend.py`

职责：

- 基于相关性与分段结果生成调参建议
- 不直接改代码
- 只输出建议和后续任务

输入参数：

- `--correlations`
- `--segments`
- `--output-dir`

输出：

- `recommendations.json`
- `summary.md`

建议类别至少包括：

1. 只调阈值
2. 调权重 + 阈值
3. reviewer 计分函数可能需要重写

### 6. `scripts/review_tuning_verify.py`

职责：

- 复用并扩展 `review_top3_stats.py`
- 对比调参前后表现
- 输出末端复验结果

建议输入参数：

- `--methods`
- `--environment-state`
- `--baseline-artifact-dir`
- `--candidate-artifact-dir`
- `--output-dir`

输出：

- `verification.json`
- `verification.md`

## Artifacts 目录设计

所有调参诊断结果统一写入：

```text
artifacts/review-tuning/<run_id>/
```

其中至少包括：

- `samples.csv`
- `samples_with_env.csv`
- `correlations.json`
- `correlations.csv`
- `segments.json`
- `segments.csv`
- `recommendations.json`
- `summary.md`

如执行复验，则再输出：

- `verification.json`
- `verification.md`

这样做的目的：

- 让智能体有固定产物可以回看
- 让调参前后可以直接比较
- 减少“分析只留在终端输出里”的不可复用问题

## 决策树设计

skill 在给出建议前，必须先做样本有效性检查，然后按固定规则判断“只调阈值 / 调权重 / 建议改 reviewer”。

### Step 1: 样本有效性门槛

默认门槛：

- 单个 `method x environment` 样本数 `>= 30`，可下强结论
- 单个 `method x environment` 样本数 `10-29`，只下弱结论
- 单个 `method x environment` 样本数 `< 10`，只记录样本不足，不建议调参

此外还要检查：

- `ret3_pct` 和 `ret5_pct` 覆盖率是否足够
- `PASS/WATCH/FAIL` 是否至少有两个层级有样本

若这些条件不满足，skill 只能输出“样本不足/覆盖不足”，不能直接建议大改。

### Step 2: 只调阈值的条件

满足以下条件时，优先建议“只改阈值”：

- `total_score` 与 `ret3_pct` 或 `ret5_pct` 为非负相关
- `PASS` 层平均收益高于 `WATCH`
- `WATCH` 层平均收益不差于 `FAIL`
- 分层方向基本正确，但层间差距太小
- 或者 `PASS` 数量明显过多/过少

这类结论对应的后续任务应优先指向：

- `src/stock_select/environment_profiles.py`

### Step 3: 调权重 + 阈值的条件

满足以下条件时，建议“调权重 + 阈值”：

- `total_score` 整体相关性非负，但偏弱
- 某些子项与未来收益方向不一致
- 不同环境下，高收益样本依赖的子项存在明显差异
- `PASS/WATCH/FAIL` 虽然存在分层，但结构不稳定

典型例子包括：

- `strong` 环境下 `macd_phase` 高分段收益更好
- `weak` 环境下 `price_position` 高分段收益更好
- `previous_abnormal_move` 近似常量，对收益解释力接近于零

这类结论的后续任务仍优先指向：

- `src/stock_select/environment_profiles.py`

### Step 4: reviewer 计分函数可能需要重写的条件

满足以下条件时，才允许建议“改 reviewer 计分函数”：

- `total_score` 与未来收益出现负相关
- 多个核心子项也呈负相关
- `PASS` 层收益不如 `WATCH` 或 `FAIL`
- 分档和 `verdict` 分层都无法解释收益
- 该现象不只出现在单一小样本环境，而是跨多个环境重复出现

这类结论的后续任务应指向：

- `src/stock_select/reviewers/<method>.py`

但仍只输出“后续任务建议”，不直接改代码。

### Step 5: 环境 profile 是否有效的判定

skill 还必须单独回答：

“环境 profile 是否真正把不同环境下的输出结构拉开了？”

判断时至少检查：

- `PASS` 占比是否出现合理差异
- `WATCH` 是否真正承担过渡层
- `strong > neutral > weak` 是否在某个关键维度上有方向性
- 相同总分区间在不同环境下是否呈现不同收益表现

若三档环境在这些指标上几乎无差异，则结论必须明确写成：

- 当前环境 profile 已接入
- 但尚未形成有效分层
- 后续优先任务是增强环境间阈值或权重差异

## `review_top3_stats.py` 的改造定位

`scripts/review_top3_stats.py` 不再被视为主诊断脚本，而应定位为复验脚本的一部分。

改造方向如下：

1. 从“单方法 top3 PASS 统计”扩展为支持：
   - `--methods`
   - `--environment-state`
   - 调参前后 artifact 对比参数

2. 输出调参前后对比，而不是只输出单次统计

3. 支持按环境拆出 top3 表现

4. 保持其职责是末端验证，而不是前置诊断

## 测试策略

至少补充以下测试：

1. `tests/test_review_tuning_collect.py`
   - 能正确遍历多个 `summary.json`
   - 能统一展开 `recommendations` 与 `excluded`
   - 能补充 `ret3_pct` / `ret5_pct`

2. `tests/test_review_tuning_attach_environment.py`
   - 能按 `pick_date` 正确贴 `score_based_state`
   - 无命中环境时行为明确

3. `tests/test_review_tuning_correlations.py`
   - 能输出 Pearson / Spearman
   - 样本不足时不报错，而是降级输出

4. `tests/test_review_tuning_segments.py`
   - 能按 1-5 分档
   - 能按总分区间和 `verdict` 分层
   - 各段统计值正确

5. `tests/test_review_tuning_recommend.py`
   - 能命中三类建议：
     - 只调阈值
     - 调权重 + 阈值
     - reviewer 计分函数可能需要重写

6. `tests/test_review_top3_stats.py`
   - 覆盖多方法和环境过滤
   - 覆盖调参前后对比输出

## 推荐实施顺序

建议后续实现任务按以下顺序推进：

1. 先创建 skill 骨架和 `SKILL.md`
2. 实现 `review_tuning_collect.py`
3. 实现 `review_tuning_attach_environment.py`
4. 实现 `review_tuning_correlations.py`
5. 实现 `review_tuning_segments.py`
6. 实现 `review_tuning_recommend.py`
7. 最后改造 `review_top3_stats.py` 作为复验入口

每一步都应以对应测试先行。

## 成功标准

这套能力完成后，应能稳定回答以下问题：

1. 某个方法在某个环境下，当前 review 总分与未来收益是正相关、零相关还是负相关
2. 哪些子项真正有解释力，哪些子项已经退化
3. 当前问题更像：
   - 只调阈值
   - 调权重
   - 需要改 reviewer 计分逻辑
4. 下一轮应改哪些文件，并如何验证
5. 调参后的复验可以通过扩展后的 `review_top3_stats.py` 重复执行
