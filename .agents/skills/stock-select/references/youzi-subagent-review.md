# Youzi Subagent Review

本流程借鉴本地 `/home/tiger/Documents/agents/UZI-Skill` 中 F 组 A 股游资口径，重点吸收“射程、题材、龙虎榜、量价、情绪周期”的判断框架。不要迁移 UZI 的抓数脚本、投资者投票系统或大报告流水线；当前项目的数据入口是 `stock-select-rs` 已生成的 chart 和 JSON artifact。

## 输入

每个子代理分配 `llm_tasks.json` 中的一行：

- `code`、`name`、`industry`
- `model_rank`、`model_score`
- `chart_path`
- `raw_response_path`
- `llm_report_path`
- row 内携带的因子、候选或展示字段

必要时补读同一 selection 目录：

- `display.json`
- `factors.json`
- `ranked.json`
- `run.json`

如果 `chart_path` 指向的 PNG 不存在，先运行对应 `chart` 或重新 `run --llm-review-limit N`，不要凭空读图。

## 分派规则

- 必须真实 spawn 子代理：按 `llm_tasks.json` 每行一个子代理并发分派，不能由主 agent 在当前上下文直接代写单票 review。
- 主 agent 不得代写股票结论，不得在子代理返回前自行补全 `llm_raw/<code>.json` 或 `llm_annotations.json`。
- 主 agent 的职责是准备 row 输入、传递 `chart_path` 图表、等待子代理结果、汇总 JSON、运行 `review-merge`，以及校验最终 `display.json` 和 `llm_report.html`。
- 每个子代理的 raw JSON 需要包含 `agent_id`，并在 summary/evidence 中说明使用了图表与哪些股票数据。
- 子代理结果缺失、JSON 无效或未读图时，重新分派该股票；不要用主 agent 的推断替代。

## 评审口径

用游资短线视角，不做长线 DCF：

- 射程：市值/成交额/换手是否适合短线资金，过大白马或流动性不足要降权。
- 题材：是否有板块辨识度、近期催化、主线热度或低位新题材。
- 连板与涨停：是否有首板、二板、连板接力、反包或断板修复条件。
- 量价承接：突破、缩量回踩、放量滞涨、高位派发、长上影、炸板回落。
- 情绪周期：当前是启动、分歧、加速、一致高潮还是退潮。
- 龙虎榜：如 artifact 或任务文本提供席位信息，识别游资/机构主导、拉萨天团等反向风险；没有龙虎榜数据时明确写“未见龙虎榜输入”，不要编造席位。
- 图表：必须结合 `chart_path` 的 K 线、均线、成交量、MACD 等可见结构，与 `factors.json` 数值互相校验。

## 输出

每个子代理写详细 raw review 到任务给出的 `raw_response_path`。建议 JSON：

```json
{
  "code": "000001.SZ",
  "agent_id": "subagent-id",
  "action": "KEEP",
  "bias": "bullish",
  "summary": "一句话结论",
  "chart_read": ["K线/均线/量能/MACD观察"],
  "youzi_read": ["题材/情绪/龙虎榜/接力判断"],
  "risks": ["长上影", "放量滞涨"],
  "evidence": {
    "model_rank": 1,
    "model_score": 0.73,
    "chart_path": "charts/2026-06-05.b2/000001.SZ_day.png"
  }
}
```

汇总写 `llm_annotations.json`，结构按 CLI 已有合并逻辑，核心字段：

```json
{
  "rows": [
    {
      "code": "000001.SZ",
      "llm_action": "KEEP",
      "llm_risk_flags": ["volume_confirmed"],
      "llm_comment": "题材与量价承接匹配，短线继续观察接力强度。"
    }
  ]
}
```

动作含义：

- `KEEP`：短线结构仍可跟踪，review-list 显示 `↑`。
- `CAUTION`：有机会但风险或确认不足，review-list 显示 `→`。
- `REJECT`：短线不适合，review-list 显示 `↓`。

禁止事项：

- 不改 `model_rank`、`model_score`、`ranked.json`。
- 不把 raw 长文塞进 `llm_comment`；`llm_comment` 保持一句中文短线结论。
- 不编造龙虎榜席位、题材催化或财务数据。
- 不把 HTML 手工写入 `llm_report.html`；由 `stock-select-rs review-merge` 生成。

## 合并

全部 annotation 和 raw review 完成后运行：

```bash
stock-select-rs review-merge --method b2 --pick-date <YYYY-MM-DD>
```

盘中：

```bash
stock-select-rs review-merge --method b2 --intraday --pick-date <YYYY-MM-DD>
```

成功后查看 `select/<artifact>.b2/llm_report.html`，以及：

```bash
stock-select-rs review-list --method b2 --pick-date <YYYY-MM-DD> --limit 20
```
