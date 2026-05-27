# Review Rubric

Baseline review and LLM/subagent review JSON should preserve these core fields:

```text
trend_reasoning
position_reasoning
volume_reasoning
abnormal_move_reasoning
macd_reasoning
signal_reasoning
scores.trend_structure
scores.price_position
scores.volume_behavior
scores.previous_abnormal_move
scores.macd_phase
total_score
signal_type
verdict
comment
```

Allowed `signal_type` values:

```text
trend_start
rebound
distribution_risk
```

Allowed `verdict` values:

```text
PASS
WATCH
FAIL
```

Do not hand-edit subagent JSON to make it pass. Put raw subagent output in `llm_review_results/<code>.json` and run `review-merge` so Rust validation decides whether it is mergeable.
