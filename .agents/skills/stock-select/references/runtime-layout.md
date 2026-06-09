# Runtime Layout

## Runtime Root

优先来自 `STOCK_SELECT_RUNTIME_ROOT`，缺省为：

```text
~/.agents/skills/stock-select/runtime
```

也可在命令中显式传 `--runtime-root <path>`。

## EOD Artifact

`stock-select-rs run --method b2 --pick-date 2026-06-05 --llm-review-limit 5` 生成：

```text
<runtime>/
├── candidates/2026-06-05.b2.json
├── factors/2026-06-05.b2/
│   ├── factors.json
│   └── manifest.json
├── charts/2026-06-05.b2/
│   └── <code>_day.png
└── select/2026-06-05.b2/
    ├── run.json
    ├── candidates.json
    ├── factors.json
    ├── ranked.json
    ├── feature_vectors.json
    ├── display.json
    ├── llm_tasks.json
    ├── llm_annotations.json
    ├── llm_raw/
    │   └── <code>.json
    └── llm_report.html
```

## Intraday Artifact

盘中 key 多一个 `.intraday`：

```text
<runtime>/
├── candidates/2026-06-05.intraday.b2.json
├── factors/2026-06-05.intraday.b2/
├── charts/2026-06-05.intraday.b2/
└── select/2026-06-05.intraday.b2/
    ├── run.json
    ├── display.json
    ├── factors.json
    ├── ranked.json
    ├── llm_tasks.json
    ├── llm_annotations.json
    ├── llm_raw/
    └── llm_report.html
```

同一交易日重复盘中运行会刷新同一组 artifact，不按时间戳创建新目录。

## Review 数据关系

- `display.json`：review-list 的主输入，包含模型 rank/score、名称、行业和合并后的 LLM 字段。
- `ranked.json`：模型排序后的候选列表，不能由 LLM 改写。
- `factors.json`：因子矩阵，可给子代理查证量价、均线、MACD、异常放量等结构。
- `llm_tasks.json`：给子代理的任务入口，每行含 `chart_path`、`raw_response_path`、`llm_report_path` 和股票上下文。
- `llm_annotations.json`：子代理/人工复盘结论，只写 action、risk flags、comment 等 annotation。
- `llm_raw/<code>.json`：单票详细分析原文，供 HTML 报告展示。
- `llm_report.html`：`review-merge` 生成的图文报告。
