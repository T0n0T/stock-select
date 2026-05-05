# 多方法多环境 Review 调参诊断 Skill 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `stock-select` 仓库内落地一套只做“分析诊断 + 调参建议 + 后续任务拆解”的 review 调参能力，覆盖 `b1/b2/dribull/hcr` 与 `weak/neutral/strong` 环境，并把 `review_top3_stats.py` 改造成末端复验入口。

**Architecture:** 把可测试的共享逻辑放到新的 `src/stock_select/research/review_tuning.py`，6 个 `scripts/review_tuning_*.py` 脚本只负责参数解析、产物写盘与用户入口；新增 `.agents/skills/review-tuning-diagnostics/SKILL.md` 约束智能体执行顺序；最后扩展 `scripts/review_top3_stats.py` 支持多方法、多环境和前后对比。

**Tech Stack:** Python, pandas, pytest, 现有 runtime/reviews + prepared cache 结构，仓库内 `.agents/skills/` 技能体系。

---

### Task 1: 建立共享研究模块与样本采集入口

**Files:**
- Create: `src/stock_select/research/__init__.py`
- Create: `src/stock_select/research/review_tuning.py`
- Create: `scripts/review_tuning_collect.py`
- Create: `tests/test_review_tuning_collect.py`

- [ ] **Step 1: 先写失败测试，锁定样本采集最小能力**

```python
from stock_select.research.review_tuning import collect_review_samples


def test_collect_review_samples_extracts_scores_and_forward_returns(tmp_path):
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "method": "b2",
                        "total_score": 4.2,
                        "trend_structure": 4.0,
                        "price_position": 5.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 5.0,
                        "macd_phase": 4.5,
                        "verdict": "PASS",
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    rows = collect_review_samples(
        methods=["b2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        runtime_root=runtime_root,
        prepared_root=tmp_path / "prepared",
    )

    assert rows[0]["code"] == "000001.SZ"
    assert rows[0]["total_score"] == 4.2
    assert "ret3_pct" in rows[0]
    assert "ret5_pct" in rows[0]
```

- [ ] **Step 2: 运行单测并确认失败**

Run: `uv run pytest -q tests/test_review_tuning_collect.py`

Expected: FAIL with `ModuleNotFoundError` or missing function / missing script behavior.

- [ ] **Step 3: 写最小实现，先打通共享研究模块与脚本薄封装**

```python
# src/stock_select/research/review_tuning.py
def collect_review_samples(*, methods, start_date, end_date, runtime_root, prepared_root):
    rows = []
    for method in methods:
        for review_dir in sorted((runtime_root / "reviews").glob(f"????-??-??.{method}")):
            ...
            rows.append(
                {
                    "method": method,
                    "pick_date": pick_date,
                    "code": code,
                    "total_score": float(item["total_score"]),
                    "trend_structure": float(item["trend_structure"]),
                    "price_position": float(item["price_position"]),
                    "volume_behavior": float(item["volume_behavior"]),
                    "previous_abnormal_move": float(item["previous_abnormal_move"]),
                    "macd_phase": float(item["macd_phase"]),
                    "verdict": str(item["verdict"]).upper(),
                    "ret3_pct": fwd.get("ret3_pct"),
                    "ret5_pct": fwd.get("ret5_pct"),
                }
            )
    return rows
```

```python
# scripts/review_tuning_collect.py
def main() -> None:
    args = parse_args()
    rows = collect_review_samples(
        methods=args.methods,
        start_date=args.start_date,
        end_date=args.end_date,
        runtime_root=args.runtime_root,
        prepared_root=args.prepared_root,
    )
    pd.DataFrame(rows).to_csv(args.output_dir / "samples.csv", index=False)
```

- [ ] **Step 4: 复跑测试并补一个脚本级 smoke case**

Run: `uv run pytest -q tests/test_review_tuning_collect.py`

Expected: PASS


### Task 2: 接入环境贴标能力

**Files:**
- Modify: `src/stock_select/research/review_tuning.py`
- Create: `scripts/review_tuning_attach_environment.py`
- Create: `tests/test_review_tuning_attach_environment.py`

- [ ] **Step 1: 写失败测试，锁定按 `pick_date` 映射 `score_based_state` 的行为**

```python
from stock_select.research.review_tuning import attach_environment_state


def test_attach_environment_state_uses_score_based_state_window(tmp_path):
    rows = [
        {"method": "b1", "pick_date": "2026-04-10", "code": "000001.SZ"},
        {"method": "b2", "pick_date": "2026-04-20", "code": "000002.SZ"},
    ]
    environment_history = [
        {
            "start_date": "2026-04-01",
            "end_date": "2026-04-15",
            "score_based_state": "weak",
            "state": "neutral",
        },
        {
            "start_date": "2026-04-16",
            "end_date": "2026-04-30",
            "score_based_state": "strong",
            "state": "strong",
        },
    ]

    tagged = attach_environment_state(rows, environment_history, environment_key="score_based_state")

    assert tagged[0]["environment_state"] == "weak"
    assert tagged[1]["environment_state"] == "strong"
```

- [ ] **Step 2: 运行单测并确认失败**

Run: `uv run pytest -q tests/test_review_tuning_attach_environment.py`

Expected: FAIL with missing helper or wrong mapping.

- [ ] **Step 3: 写最小实现，复用现有环境历史结构**

```python
def attach_environment_state(rows, environment_history, *, environment_key):
    tagged = []
    for row in rows:
        pick_date = row["pick_date"]
        matched = next(
            (
                item
                for item in environment_history
                if item["start_date"] <= pick_date <= item["end_date"]
            ),
            None,
        )
        tagged.append(
            {
                **row,
                "environment_state": (
                    str(matched.get(environment_key) or matched.get("state")).lower()
                    if matched is not None
                    else "unknown"
                ),
            }
        )
    return tagged
```

```python
# scripts/review_tuning_attach_environment.py
rows = pd.read_csv(args.samples).to_dict("records")
history = load_environment_history(args.runtime_root)
tagged = attach_environment_state(rows, history, environment_key=args.environment_key)
pd.DataFrame(tagged).to_csv(args.output_dir / "samples_with_env.csv", index=False)
```

- [ ] **Step 4: 复跑测试**

Run: `uv run pytest -q tests/test_review_tuning_attach_environment.py tests/test_environment_tuning_diagnostics.py`

Expected: PASS


### Task 3: 实现相关性分析与分段统计

**Files:**
- Modify: `src/stock_select/research/review_tuning.py`
- Create: `scripts/review_tuning_correlations.py`
- Create: `scripts/review_tuning_segments.py`
- Create: `tests/test_review_tuning_correlations.py`
- Create: `tests/test_review_tuning_segments.py`

- [ ] **Step 1: 写失败测试，锁定 Pearson / Spearman 与样本不足降级输出**

```python
from stock_select.research.review_tuning import compute_correlations


def test_compute_correlations_marks_small_groups_as_insufficient():
    rows = [
        {"method": "b2", "environment_state": "weak", "total_score": 4.0, "ret3_pct": 1.0, "ret5_pct": 2.0},
        {"method": "b2", "environment_state": "weak", "total_score": 3.0, "ret3_pct": -1.0, "ret5_pct": -2.0},
    ]

    result = compute_correlations(rows, min_samples_strong=30, min_samples_weak=10)

    assert result["groups"][0]["conclusion_strength"] == "insufficient"
    assert "pearson_r" in result["groups"][0]["metrics"][0]
    assert "spearman_r" in result["groups"][0]["metrics"][0]
```

```python
from stock_select.research.review_tuning import compute_segments


def test_compute_segments_groups_by_verdict_and_score_band():
    rows = [
        {"method": "b1", "environment_state": "neutral", "verdict": "PASS", "total_score": 4.3, "price_position": 5.0, "ret3_pct": 2.0, "ret5_pct": 3.0},
        {"method": "b1", "environment_state": "neutral", "verdict": "WATCH", "total_score": 3.5, "price_position": 3.0, "ret3_pct": 1.0, "ret5_pct": 0.0},
    ]

    result = compute_segments(rows)

    assert any(item["segment_type"] == "verdict" and item["segment_value"] == "PASS" for item in result)
    assert any(item["segment_type"] == "total_score_band" for item in result)
```

- [ ] **Step 2: 运行两组测试并确认失败**

Run: `uv run pytest -q tests/test_review_tuning_correlations.py tests/test_review_tuning_segments.py`

Expected: FAIL with missing functions or incorrect output schema.

- [ ] **Step 3: 写最小实现，统一 group key 和输出 schema**

```python
def compute_correlations(rows, *, min_samples_strong=30, min_samples_weak=10):
    groups = []
    for scope_name, scoped_rows in iter_scoped_rows(rows):
        metrics = []
        for score_field in SCORE_FIELDS:
            metrics.append(
                {
                    "score_field": score_field,
                    "target_field": "ret3_pct",
                    "pearson_r": safe_pearson(scoped_rows, score_field, "ret3_pct"),
                    "spearman_r": safe_spearman(scoped_rows, score_field, "ret3_pct"),
                }
            )
        groups.append(build_group_payload(scope_name, scoped_rows, metrics, min_samples_strong, min_samples_weak))
    return {"groups": groups}
```

```python
def compute_segments(rows):
    segments = []
    segments.extend(build_score_bucket_segments(rows, field="price_position"))
    segments.extend(build_score_bucket_segments(rows, field="macd_phase"))
    segments.extend(build_total_score_band_segments(rows))
    segments.extend(build_verdict_segments(rows))
    return segments
```

- [ ] **Step 4: 复跑测试直到通过**

Run: `uv run pytest -q tests/test_review_tuning_correlations.py tests/test_review_tuning_segments.py`

Expected: PASS


### Task 4: 实现建议生成器与后续任务拆解

**Files:**
- Modify: `src/stock_select/research/review_tuning.py`
- Create: `scripts/review_tuning_recommend.py`
- Create: `tests/test_review_tuning_recommend.py`

- [ ] **Step 1: 写失败测试，锁定三类建议分流规则**

```python
from stock_select.research.review_tuning import build_recommendations


def test_build_recommendations_prefers_threshold_only_when_layering_direction_is_correct():
    correlations = {
        "groups": [
            {
                "scope": "method=b2,environment=neutral",
                "sample_count": 60,
                "conclusion_strength": "strong",
                "metrics": [{"score_field": "total_score", "target_field": "ret3_pct", "pearson_r": 0.12, "spearman_r": 0.10}],
            }
        ]
    }
    segments = [
        {"scope": "method=b2,environment=neutral", "segment_type": "verdict", "segment_value": "PASS", "avg_ret3_pct": 2.1},
        {"scope": "method=b2,environment=neutral", "segment_type": "verdict", "segment_value": "WATCH", "avg_ret3_pct": 1.2},
        {"scope": "method=b2,environment=neutral", "segment_type": "verdict", "segment_value": "FAIL", "avg_ret3_pct": -0.5},
    ]

    result = build_recommendations(correlations, segments)

    assert result["recommendations"][0]["action_type"] == "threshold_only"
    assert "environment_profiles.py" in result["recommendations"][0]["target_files"][0]
```

- [ ] **Step 2: 运行单测并确认失败**

Run: `uv run pytest -q tests/test_review_tuning_recommend.py`

Expected: FAIL with missing builder or wrong decision tree.

- [ ] **Step 3: 写最小实现，输出 JSON + Markdown 共用的数据结构**

```python
def build_recommendations(correlations, segments):
    recommendations = []
    for scope in collect_scopes(correlations, segments):
        decision = classify_scope_decision(scope, correlations, segments)
        recommendations.append(
            {
                "scope": scope,
                "action_type": decision.action_type,
                "reason": decision.reason,
                "target_files": decision.target_files,
                "next_tasks": decision.next_tasks,
                "success_criteria": decision.success_criteria,
            }
        )
    return {"recommendations": recommendations}
```

```python
# scripts/review_tuning_recommend.py
payload = build_recommendations(correlations, segments)
write_json(args.output_dir / "recommendations.json", payload)
(args.output_dir / "summary.md").write_text(render_recommendation_summary(payload), encoding="utf-8")
```

- [ ] **Step 4: 复跑测试**

Run: `uv run pytest -q tests/test_review_tuning_recommend.py`

Expected: PASS


### Task 5: 写 skill 并把 6 个脚本入口补齐

**Files:**
- Create: `.agents/skills/review-tuning-diagnostics/SKILL.md`
- Create: `scripts/review_tuning_verify.py`
- Modify: `scripts/review_tuning_collect.py`
- Modify: `scripts/review_tuning_attach_environment.py`
- Modify: `scripts/review_tuning_correlations.py`
- Modify: `scripts/review_tuning_segments.py`
- Modify: `scripts/review_tuning_recommend.py`

- [ ] **Step 1: 写 skill，先锁定“只能诊断、不能直接改代码”的流程约束**

```md
---
name: review-tuning-diagnostics
description: Use when evaluating review scoring quality across methods and market environments and deciding whether to tune thresholds, weights, or reviewer logic
---

# Review Tuning Diagnostics

- Always run: collect -> attach_environment -> correlations -> segments -> recommend
- Only run verify when baseline and candidate artifacts both exist
- Do not edit `src/` production code in this workflow
- Final output must include `summary.md`, `recommendations.json`, and next-step implementation tasks
```

- [ ] **Step 2: 给每个脚本补 `parse_args()` 与统一输出目录约定**

```python
def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    ...
    return parser.parse_args(argv)
```

- [ ] **Step 3: 给 `verify` 入口先写最小壳子，后面由 Task 6 接入实际对比逻辑**

```python
def main() -> None:
    args = parse_args()
    baseline = load_artifact_dir(args.baseline_artifact_dir)
    candidate = load_artifact_dir(args.candidate_artifact_dir)
    payload = {"baseline_dir": str(args.baseline_artifact_dir), "candidate_dir": str(args.candidate_artifact_dir)}
    write_json(args.output_dir / "verification.json", payload)
```

- [ ] **Step 4: 做一次最小 smoke 验证**

Run: `uv run python scripts/review_tuning_collect.py --help`

Run: `uv run python scripts/review_tuning_attach_environment.py --help`

Run: `uv run python scripts/review_tuning_correlations.py --help`

Run: `uv run python scripts/review_tuning_segments.py --help`

Run: `uv run python scripts/review_tuning_recommend.py --help`

Run: `uv run python scripts/review_tuning_verify.py --help`

Expected: 每个脚本都能打印帮助信息并退出 0。


### Task 6: 扩展 `review_top3_stats.py` 作为末端复验入口

**Files:**
- Modify: `scripts/review_top3_stats.py`
- Modify: `tests/test_review_top3_stats.py`
- Modify: `scripts/review_tuning_verify.py`

- [ ] **Step 1: 先写失败测试，锁定多方法与环境过滤**

```python
def test_collect_pass_top_reviews_supports_multiple_methods_and_environment_filter(tmp_path):
    module = _load_review_top3_stats_module()
    ...
    result = module.collect_review_top3_records(
        methods=["b1", "b2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        environment_state="weak",
    )
    assert all(item["environment_state"] == "weak" for item in result)
```

```python
def test_compare_artifact_dirs_reports_delta():
    module = _load_review_top3_stats_module()
    payload = module.compare_top3_metrics(
        baseline=[{"method": "b2", "avg_ret3_pct": 0.5}],
        candidate=[{"method": "b2", "avg_ret3_pct": 1.2}],
    )
    assert payload["rows"][0]["delta_ret3_pct"] == 0.7
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest -q tests/test_review_top3_stats.py`

Expected: FAIL with missing compare helpers or unsupported args.

- [ ] **Step 3: 写最小实现，复用 Task 1/2 的样本与环境数据**

```python
def collect_review_top3_records(*, methods, start_date, end_date, environment_state=None):
    records = []
    for method in methods:
        ...
        if environment_state and record["environment_state"] != environment_state:
            continue
        records.append(record)
    return records
```

```python
def compare_top3_metrics(*, baseline, candidate):
    return {"rows": build_delta_rows(baseline, candidate)}
```

```python
# scripts/review_tuning_verify.py
comparison = review_top3_stats.compare_top3_metrics(baseline=baseline_rows, candidate=candidate_rows)
write_json(args.output_dir / "verification.json", comparison)
```

- [ ] **Step 4: 复跑测试**

Run: `uv run pytest -q tests/test_review_top3_stats.py`

Expected: PASS


### Task 7: 端到端验证与交付检查

**Files:**
- No new files expected unless verification reveals a gap

- [ ] **Step 1: 运行新增测试切片**

Run: `uv run pytest -q tests/test_review_tuning_collect.py tests/test_review_tuning_attach_environment.py tests/test_review_tuning_correlations.py tests/test_review_tuning_segments.py tests/test_review_tuning_recommend.py tests/test_review_top3_stats.py`

Expected: 全部 PASS

- [ ] **Step 2: 跑一个最小真实流程，确认 artifacts 目录结构完整**

Run:

```bash
uv run python scripts/review_tuning_collect.py \
  --methods b1 b2 \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --runtime-root ~/.agents/skills/stock-select/runtime \
  --prepared-root ~/.agents/skills/stock-select/runtime/prepared \
  --output-dir artifacts/review-tuning/smoke
```

Then:

```bash
uv run python scripts/review_tuning_attach_environment.py \
  --samples artifacts/review-tuning/smoke/samples.csv \
  --runtime-root ~/.agents/skills/stock-select/runtime \
  --environment-key score_based_state \
  --output-dir artifacts/review-tuning/smoke
```

Then:

```bash
uv run python scripts/review_tuning_correlations.py \
  --samples artifacts/review-tuning/smoke/samples_with_env.csv \
  --output-dir artifacts/review-tuning/smoke
```

Then:

```bash
uv run python scripts/review_tuning_segments.py \
  --samples artifacts/review-tuning/smoke/samples_with_env.csv \
  --output-dir artifacts/review-tuning/smoke
```

Then:

```bash
uv run python scripts/review_tuning_recommend.py \
  --correlations artifacts/review-tuning/smoke/correlations.json \
  --segments artifacts/review-tuning/smoke/segments.json \
  --output-dir artifacts/review-tuning/smoke
```

Expected:

- `artifacts/review-tuning/smoke/samples.csv`
- `artifacts/review-tuning/smoke/samples_with_env.csv`
- `artifacts/review-tuning/smoke/correlations.json`
- `artifacts/review-tuning/smoke/segments.json`
- `artifacts/review-tuning/smoke/recommendations.json`
- `artifacts/review-tuning/smoke/summary.md`

- [ ] **Step 3: 检查 skill 文案和产物命名是否与 spec 一致**

Checklist:

- skill 明确禁止直接改 `src/`
- skill 明确要求固定执行顺序
- 建议输出包含下一轮实现任务
- 复验入口依赖扩展后的 `review_top3_stats.py`

- [ ] **Step 4: 检查最终 diff，仅包含本计划内文件**

Run: `git status --short`

Expected: 只出现本计划列出的 skill、scripts、src 共享模块和 tests 变更。
