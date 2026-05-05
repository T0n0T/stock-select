---
name: review-tuning-diagnostics
description: Use when evaluating review scoring quality across methods and market environments and deciding whether to tune thresholds, weights, or reviewer logic.
---

# Review Tuning Diagnostics

## Workflow

- 必须按顺序执行：`collect -> attach_environment -> correlations -> segments -> recommend -> verify`
- 只有 baseline 和 candidate 两套 artifacts 都存在时才允许执行 `verify`
- 不允许跳过中间步骤直接下调参结论

## 禁止事项

- 禁止在这个 workflow 里直接编辑 `src/` 下的生产代码
- 禁止在样本覆盖率不足时下强结论
- 禁止只看总分均值而忽略分层和环境切片
- 禁止根据单个环境的小样本直接建议重写 reviewer

## 交付要求

- 必须输出 `summary.md`
- 必须输出 `recommendations.json`
- 必须给出下一步实现任务列表
