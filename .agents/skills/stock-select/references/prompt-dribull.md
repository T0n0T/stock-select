# Dribull 多模态图表复盘 Prompt

新 CLI 当前只保留有限 method capability；不要把 dribull 当作当前 model-first 生产复盘主路径。

仅当用户明确要求人工查看 dribull 图表时使用本提示。读取图表后只给人工观察意见，不要暗示存在已接入的 dribull 模型排序。

关注：

- 趋势延续与回撤位置。
- 波动收敛或放大。
- 成交量是否出现派发风险。
- MACD/均线是否支持继续观察。

若需要写入新 CLI annotation，仍按 `review-rubric.md` 的 schema 输出，并保持 `model_rank` 不变。

