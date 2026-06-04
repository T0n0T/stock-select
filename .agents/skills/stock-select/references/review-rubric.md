# 多模态复盘 Rubric

本文件用于安排子代理读取图表并产出 LLM annotation。新 CLI 的复盘不改变模型排序：`model_rank` 和 `model_score` 只来自 b2 LightGBM。

## 输出位置

子代理完成后，把可合并结果写入：

```text
<runtime>/select/<key>.b2/llm_annotations.json
```

其中 `<key>` 为：

```text
EOD:      <pick_date>
Intraday: <pick_date>.intraday
```

原始多模态回复可另存到：

```text
<runtime>/select/<key>.b2/llm_raw/<code>.json
```

并在 annotation 的 `raw_response_path` 填相对 runtime 的路径。

## 可合并 Schema

`llm_annotations.json` 必须是：

```json
{
  "method": "b2",
  "artifact_key": "2026-05-25",
  "rows": [
    {
      "code": "000001.SZ",
      "llm_action": "CAUTION",
      "llm_confidence": 0.72,
      "llm_risk_flags": ["volume_distribution"],
      "llm_comment": "缩量不充分，先观察支撑确认。",
      "raw_response_path": "select/2026-05-25.b2/llm_raw/000001.SZ.json"
    }
  ]
}
```

字段要求：

- `code`：必须匹配 `llm_tasks.json` 中的股票代码。
- `llm_action`：只能使用 `KEEP`、`CAUTION`、`REJECT`。
- `llm_confidence`：可选，建议 `0.0..1.0`。
- `llm_risk_flags`：数组，可为空。
- `llm_comment`：可选，简短中文结论。
- `raw_response_path`：可选，指向原始子代理输出。

## 评估维度

多模态子代理读取 `<runtime>/select/<key>.b2/llm_tasks.json` 和对应图表后，重点判断：

- 趋势结构：是否处于早期趋势启动、反弹修复、还是破位/衰竭。
- 价格位置：是否靠近支撑，是否已经过度追高。
- 成交量：是否缩量回踩、放量突破，或出现派发风险。
- MACD/均线：日线与周线节奏是否支持继续观察。
- 异动风险：前期异常拉升、长上影、断崖放量、连续加速后的回撤风险。
- 信号质量：B2 信号是趋势起点、弱反弹，还是失败概率高。

## Action 口径

```text
KEEP     图形与模型排序方向一致，风险可接受。
CAUTION  有观察价值但存在明确条件或风险，需要备注。
REJECT   图形风险明显，不建议作为人工优先观察对象。
```

不要让子代理重排候选，不要输出新的 `model_rank`，不要修改 `ranked.json`。

## 合并

写好 `llm_annotations.json` 后运行：

```bash
stock-select-rs review-merge --method b2 --pick-date <YYYY-MM-DD>
```

盘中使用：

```bash
stock-select-rs review-merge --method b2 --intraday
```

