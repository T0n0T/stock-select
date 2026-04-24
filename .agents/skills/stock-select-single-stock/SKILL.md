---
name: stock-select-single-stock
description: Use when analyzing one explicitly named A-share stock with the local stock-select repository, especially when the user wants a b2 score/rating even if the stock would not enter the candidate pool.
---

# Stock Select Single Stock

## Overview

Use this skill for single-stock analysis against the local `stock-select` repository at:

```text
/home/pi/Documents/agents/stock-select
```

This wrapper exists for requests such as:

- “参考 b2 算一下这只票的评分评级”
- “看看北京科锐按 b2 怎么打分”
- “即使没入选，也分析这只股票”

Use the existing `stock-select` skill instead when the task is pool-based screening, candidate chart generation, `review-merge`, or multimodal review dispatch for multiple symbols.

## Current Scope

The current repository commands for this workflow are:

```bash
uv run stock-select analyze-symbol --method b1 --symbol 002350.SZ
uv run stock-select analyze-symbol --method b2 --symbol 002350.SZ
uv run stock-select analyze-symbol --method dribull --symbol 002350.SZ
uv run stock-select analyze-symbol --method hcr --symbol 002350.SZ
```

Current supported scope:

- single stock only
- `b1` / `b2` / `dribull` / `hcr`
- end-of-day only
- deterministic local baseline review only

Do not route single-stock requests through `screen --pool-source custom` unless the user explicitly wants the candidate-pool workflow. That path can still produce an empty candidate set and is not the authoritative single-stock interface.

## Required Workflow

1. Work from the repository root:

```bash
cd /home/pi/Documents/agents/stock-select
```

2. Resolve one explicit stock code.

- Prefer a direct TS code such as `002350.SZ`.
- If the user gives only a 6-digit code, normalize it to the expected suffix form before calling the CLI.
- If the user gives only a name and no code, resolve the code from the PostgreSQL `instruments` table before running the command.

3. Use `analyze-symbol` instead of `screen/chart/review` for the actual single-stock run.

4. If the user gives no `pick_date`, omit `--pick-date` and let the CLI resolve the latest complete usable trade date for that symbol.

5. Read the emitted `result.json` and report both layers of outcome:

- screening-style outcome
  - `signal`
  - `selected_as_candidate`
  - `screen_conditions`
- baseline-review outcome
  - `baseline_review.total_score`
  - `baseline_review.signal_type`
  - `baseline_review.verdict`
  - `baseline_review.comment`

Never collapse these into one conclusion. “Not selected as candidate” and “baseline review FAIL” are related but not equivalent.

## Command Pattern

Typical commands:

```bash
uv run stock-select analyze-symbol --method b1 --symbol 002350.SZ --pick-date 2026-04-21
uv run stock-select analyze-symbol --method b2 --symbol 002350.SZ --pick-date 2026-04-21
uv run stock-select analyze-symbol --method dribull --symbol 002350.SZ --pick-date 2026-04-21
uv run stock-select analyze-symbol --method hcr --symbol 002350.SZ --pick-date 2026-04-21
```

If quiet stdout-only output is useful for automation, use:

```bash
uv run stock-select analyze-symbol --method b2 --symbol 002350.SZ --pick-date 2026-04-21 --no-progress
```

If the user did not provide a date:

```bash
uv run stock-select analyze-symbol --method b2 --symbol 002350.SZ
```

## Expected Output

The command prints the `result.json` path. Current runtime layout:

```text
~/.agents/skills/stock-select/runtime/ad_hoc/<pick_date>.<method>.<code>/result.json
~/.agents/skills/stock-select/runtime/ad_hoc/<pick_date>.<method>.<code>/<code>_day.png
```

Read `result.json` and prefer quoting these fields in your response:

- `code`
- `pick_date`
- `signal`
- `selected_as_candidate`
- `baseline_review.total_score`
- `baseline_review.verdict`
- `baseline_review.comment`
- `chart_path`

## Error Handling

Treat these as user-correctable input/environment issues first:

- missing DSN
- invalid `pick_date`
- invalid `symbol`
- no daily history for the symbol
- requested explicit `pick_date` not present for the symbol
- incomplete EOD rows on the requested date

The CLI already normalizes many of these into `BadParameter`-style failures. Surface the error clearly instead of trying to patch around it inside the skill.

## Limits

- Current single-stock command supports `b1`, `b2`, `dribull`, and `hcr`.
- This skill does not perform multimodal chart-review subagent dispatch.
- This skill does not replace the existing pool-based `stock-select` skill.
