---
name: stock-select
description: Use when screening A-share stocks from the stock-cache PostgreSQL database with the B1 method, generating daily charts, and coordinating multimodal subagents for chart review and final conclusions.
---

# Stock Select

Use this skill when the task is to run the standalone `stock-select` workflow against the `stock-cache` PostgreSQL data source.

## Required Workflow

- Always require `--method b1`.
- Reject any method other than `b1`.
- Do not use `stock-cache read` CLI as the primary data source.
- Read PostgreSQL tables directly.
- Run deterministic screening in Python first.
- Generate daily charts before review.
- Spawn subagents in parallel for multimodal review.
- Use the bundled review rubric, but let the framework choose the multimodal model.
- Write outputs under `~/.agents/skills/stock-select/runtime/`.

## Execution Order

1. Resolve the pick date and CLI arguments.
2. Query PostgreSQL market data needed for B1 screening.
3. Run deterministic B1 screening and write candidate outputs.
4. Render daily chart images for each candidate.
5. Dispatch multimodal subagents in parallel for chart review.
6. Aggregate per-stock review results into a final summary.

## Bundled References

- `references/b1-selector.md`
- `references/review-rubric.md`
- `references/runtime-layout.md`
