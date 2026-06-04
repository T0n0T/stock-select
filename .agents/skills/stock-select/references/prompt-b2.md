# B2 多模态图表复盘 Prompt

读取 `llm_tasks.json` 中分配给你的股票，并查看对应日线图。只做风险 annotation，不改变模型排序。

重点检查：

- B2 信号质量：趋势启动、反弹修复、还是失败风险。
- 回踩位置：是否接近支撑，是否远离均线后追高。
- MACD/均线节奏：日线与周线是否共振，是否处于衰竭或钝化风险。
- 成交量：缩量回踩、放量突破、放量滞涨、派发风险。
- 异常波动：前期异常拉升、长上影、跳空、断崖放量或连续加速。

输出应转换为 `review-rubric.md` 中的 annotation schema：`KEEP`、`CAUTION` 或 `REJECT`，附风险 flags 和简短中文 comment。

