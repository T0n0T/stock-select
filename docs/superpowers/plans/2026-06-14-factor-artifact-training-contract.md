# Factor Artifact Training Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 规范 Rust `factors.json` 的训练特征契约，并让 Python RF/LightGBM 训练层显式校验“确认用于训练的因子”已完整进入训练矩阵。

**Architecture:** Rust artifact 只在 `rows[].factors` 输出可训练字段；review/评分字段不再混入训练因子集合。Python 侧把训练 schema 拆成 raw numeric、training categorical、review metadata 三类，并在 RF/LightGBM 共享特征选择后做覆盖率门禁，防止 schema 里确认启用的因子没有进入训练数据。

**Tech Stack:** Rust、Serde JSON、Python 3.11、unittest、scikit-learn `RandomForestClassifier`、LightGBM 训练脚本。

---

## Files and Responsibilities

- Modify: `src/factors/price_position.rs`
  - 新增 `box_mid_position_120d_pct`，输出最新 K 线中点在 120 日箱体内的位置。
- Modify: `src/factors/registry.rs`
  - 增加 artifact 输出前的 review-only 过滤边界。
  - 保证 `FactorRow.factors` 只保留训练候选字段；`diagnostics` 继续只放 provenance。
- Modify: `tests/screening_factor_parity.rs`
  - 增加 Rust 层契约测试：B3/B2 不输出 review-only score 字段，但仍输出确认训练字段。
- Modify: `tests/engine_b2.rs`
  - 更新 candidate payload provider 对 semantic review 字段的旧断言。
- Modify: `scripts/ml/build_rank_dataset.py`
  - 拆分 review metadata 与 training categorical schema。
  - 移除 `B2_REVIEW_COLUMNS/B3_REVIEW_COLUMNS` 对 dataset 的训练输入影响。
  - 暴露统一 schema 函数供训练层复用。
- Modify: `scripts/ml/train_rank_lgbm.py`
  - 从 dataset schema 读取 categorical 列，不再维护第二份硬编码口径。
  - 增加 selected feature coverage 校验，RF 与 LightGBM 共享同一校验结果。
- Modify: `tests/test_rank_dataset.py`
  - 覆盖 dataset schema 规范和 artifact merge 行为。
- Modify: `tests/test_rank_lgbm.py`
  - 覆盖 RF 前 feature coverage 门禁和 shared schema。
- Modify: `docs/model.md`
  - 记录 `factors.json` 契约、RF 门禁和 review 字段边界。
- Modify: `docs/workflow.md`
  - 更新模型训练流程中的校验说明。

---

## Contract Decisions

### Training fields stay in `rows[].factors`

Allowed values:

- numeric factors: `FactorValue::Number`
- boolean factors: `FactorValue::Bool`
- low-cardinality categorical factors: `FactorValue::Category`
- `FactorValue::Missing` only for a registered training key that can be absent for a row

Examples that stay:

- `close_to_ma25_pct`
- `close_to_zxdkx_pct`
- `box_mid_position_120d_pct`
- `b3_volume_shrink_ratio`
- `b3_prev_b2_flag`
- `signal_type`
- `macd_phase`
- `daily_macd_wave_index`
- `weekly_macd_wave_index`
- `daily_macd_phase_type`
- `daily_macd_wave_stage`
- `weekly_macd_phase_type`
- `weekly_macd_wave_stage`
- `weekly_daily_combo_type`
- `midline_state`
- `env`

### Review-only score fields leave `rows[].factors`

- `trend_structure`
- `price_position`
- `volume_behavior`
- `previous_abnormal_move`
- `weekly_daily_combo_score`
- `total_score`
- `verdict`

Reason: these are review scoring outputs or policy scores. They should not silently become RF/LGBM input features.

### Python RF/LGBM completeness gate

Before RF diagnostics and LightGBM training:

- compute selected `numeric_columns` and `categorical_columns`
- for every selected feature, require:
  - feature appears in dataset header/row keys
  - at least one row has a non-empty value
- fail with a clear error listing zero-coverage features
- write feature coverage into `lgbm_rank_report*.json`

This gate applies to the shared selected feature set, not RF-only columns.

---

## Task 1: Rust artifact excludes review-only factors

**Files:**
- Modify: `tests/screening_factor_parity.rs`
- Modify: `src/factors/registry.rs`
- Modify: `tests/engine_b2.rs`

- [ ] **Step 1: Add failing B3 artifact contract test**

Add this test near `b3_factor_profile_adds_b3_specific_raw_factors_only_for_b3` in `tests/screening_factor_parity.rs`:

```rust
#[test]
fn b3_factor_artifact_excludes_review_scores_but_keeps_training_context() {
    let first_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    let pick_date = first_date + Duration::days(130);
    let prepared = (0..=130)
        .map(|offset| PreparedRow {
            open: 10.0 + offset as f64 * 0.03,
            high: 10.4 + offset as f64 * 0.03,
            low: 9.8 + offset as f64 * 0.03,
            close: 10.2 + offset as f64 * 0.03,
            volume: if offset == 130 { 600.0 } else { 1000.0 },
            j: 30.0 + offset as f64 * 0.1,
            ..prepared_row(
                "000001.SZ",
                first_date + Duration::days(offset),
                10.2 + offset as f64 * 0.03,
                if offset == 130 { 600.0 } else { 1000.0 },
            )
        })
        .collect::<Vec<_>>();
    let latest = prepared.last().unwrap();
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: latest.close,
        turnover_n: latest.turnover_n,
        signal: Some("B3+".to_string()),
        yellow_b1: None,
    };

    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B3, Some("neutral"));
    let factors = &rows[0].factors;

    for key in [
        "trend_structure",
        "price_position",
        "volume_behavior",
        "previous_abnormal_move",
        "weekly_daily_combo_score",
        "total_score",
        "verdict",
    ] {
        assert!(!factors.contains_key(key), "review-only key leaked into factors: {key}");
    }

    for key in [
        "signal_type",
        "daily_macd_phase_type",
        "daily_macd_wave_stage",
        "weekly_macd_phase_type",
        "weekly_macd_wave_stage",
        "weekly_daily_combo_type",
        "macd_phase",
        "daily_macd_wave_index",
        "weekly_macd_wave_index",
        "box_mid_position_120d_pct",
        "b3_volume_shrink_ratio",
        "b3_prev_b2_flag",
        "b3_plus_flag",
        "env",
    ] {
        assert!(factors.contains_key(key), "training key missing from factors: {key}");
    }
}
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
cargo test b3_factor_artifact_excludes_review_scores_but_keeps_training_context
```

Expected: FAIL. At least `trend_structure` or another review-only key is still present in `factors`.


- [ ] **Step 2a: Add failing raw position factor test**

In the same B3 test, assert the new raw position field exists and is numeric:

```rust
assert!(matches!(
    factors.get("box_mid_position_120d_pct"),
    Some(FactorValue::Number(value)) if value.is_finite()
));
```

Expected: FAIL before implementation because Rust only emits `box_position_120d_pct`, which uses latest close instead of the latest K-line midpoint.
- [ ] **Step 3: Implement minimal Rust filtering**

In `src/factors/registry.rs`, add a review-only list near the factor profile constants:

```rust
const REVIEW_ONLY_FACTOR_KEYS: &[&str] = &[
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "weekly_daily_combo_score",
    "total_score",
    "verdict",
];
```

Add this helper near `record_factor_profile_diagnostics`:

```rust
fn remove_review_only_factors(row: &mut FactorRow) {
    for key in REVIEW_ONLY_FACTOR_KEYS {
        row.factors.remove(*key);
    }
}
```

Call it in `build_candidate_factor_rows_from_refs()` after inserting `history_factors` and before setting `factor_count`:

```rust
for (key, value) in history_factors {
    row.factors.insert(key, value);
}
remove_review_only_factors(&mut row);
```

In `src/factors/price_position.rs`, extend `push_price_position_factors()` after `box_position_120` is computed:

```rust
let box_mid_position_120 = match (latest_high, latest_low, low_120, range_width_120) {
    (Some(high), Some(low), Some(box_low), Some(width)) if width != 0.0 => {
        let current_mid_price = (high + low) / 2.0;
        Some((current_mid_price - box_low) / width * 100.0)
    }
    _ => None,
};
```

Then push it beside `box_position_120d_pct`:

```rust
push_number(factors, "box_mid_position_120d_pct", box_mid_position_120);
```

Also call it in `CandidatePayloadFactorProvider` path if that path inserts `history_factor_fields_for_method()` into `row.factors`.

- [ ] **Step 4: Update stale Rust assertions**

In `tests/engine_b2.rs`, replace assertions that require review-only scores in `row.factors`.

Remove assertions like:

```rust
assert!(matches!(
    row.factors.get("trend_structure"),
    Some(FactorValue::Number(value)) if *value >= 1.0
));
```

Keep assertions for training categorical fields:

```rust
assert_eq!(
    row.factors.get("signal_type"),
    Some(&FactorValue::Category("trend_start".to_string()))
);
assert_eq!(
    row.factors.get("daily_macd_phase_type"),
    Some(&FactorValue::Category("rising".to_string()))
);
assert_eq!(
    row.factors.get("weekly_macd_phase_type"),
    Some(&FactorValue::Category("rising".to_string()))
);
assert_eq!(
    row.factors.get("midline_state"),
    Some(&FactorValue::Category("above_hold".to_string()))
);
```

Add explicit negative assertions:

```rust
for key in ["trend_structure", "price_position", "volume_behavior", "macd_phase"] {
    assert!(!row.factors.contains_key(key), "review-only key leaked into factors: {key}");
}
```

- [ ] **Step 5: Run Rust tests to verify GREEN**

Run:

```bash
cargo test b3_factor_artifact_excludes_review_scores_but_keeps_training_context candidate_payload_factor_provider
```

Expected: PASS.

- [ ] **Step 6: Commit Rust artifact contract change**

```bash
git add src/factors/registry.rs tests/screening_factor_parity.rs tests/engine_b2.rs
git commit -m "refactor: keep review scores out of factor artifacts"
```

---

## Task 2: Python dataset schema separates training features from review metadata

**Files:**
- Modify: `scripts/ml/build_rank_dataset.py`
- Modify: `tests/test_rank_dataset.py`

- [ ] **Step 1: Add failing dataset schema test**

Add this test near `test_b3_dataset_schema_has_independent_method_entry_with_b3_specific_factors` in `tests/test_rank_dataset.py`:

```python
def test_dataset_schema_excludes_review_scores_but_keeps_training_categoricals(self):
    for method in ["b2", "b3"]:
        columns = dataset_columns_for_method(method)
        for review_score in [
            "trend_structure",
            "price_position",
            "volume_behavior",
            "previous_abnormal_move",
            "weekly_daily_combo_score",
            "total_score",
            "verdict",
        ]:
            self.assertNotIn(review_score, columns)

        for training_category in [
            "signal_type",
            "daily_macd_phase_type",
            "daily_macd_wave_stage",
            "weekly_macd_phase_type",
            "weekly_macd_wave_stage",
            "weekly_daily_combo_type",
            "midline_state",
        ]:
            self.assertIn(training_category, columns)

        for training_numeric in [
            "macd_phase",
            "daily_macd_wave_index",
            "weekly_macd_wave_index",
            "box_mid_position_120d_pct",
        ]:
            self.assertIn(training_numeric, columns)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m unittest tests.test_rank_dataset.RankDatasetTest.test_dataset_schema_excludes_review_scores_but_keeps_training_categoricals
```

Expected: FAIL because `B2_REVIEW_COLUMNS/B3_REVIEW_COLUMNS` still place review scores in dataset schema.

- [ ] **Step 3: Split schema lists in `build_rank_dataset.py`**

Replace the top schema section with this structure, preserving the existing raw factor lists below it:

```python
IDENTITY_COLUMNS = ["date", "code", "name", "env", "method"]
REVIEW_METADATA_COLUMNS = [
    "model_score",
    "model_rank",
    "llm_action",
    "risk_flags",
]
TRAINING_CATEGORICAL_COLUMNS = [
    "signal",
    "signal_type",
    "daily_macd_phase_type",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
    "midline_state",
]
TRAINING_MACD_NUMERIC_COLUMNS = [
    "macd_phase",
    "daily_macd_wave_index",
    "weekly_macd_wave_index",
]
TRAINING_POSITION_NUMERIC_COLUMNS = [
    "box_mid_position_120d_pct",
]
CONTEXT_NUMERIC_COLUMNS = [
    "price_vs_90d_high",
    "price_vs_90d_low",
    "price_vs_90d_mid",
]
```

Remove `REVIEW_COLUMNS`, `B2_REVIEW_COLUMNS`, `B3_REVIEW_COLUMNS`, `CONTEXT_COLUMNS`, and `METHOD_REVIEW_COLUMNS` if no longer used.

Add functions near `raw_factor_columns_for_method()`:

```python
def training_categorical_columns_for_method(method: str) -> list[str]:
    return list(TRAINING_CATEGORICAL_COLUMNS)


def context_numeric_columns_for_method(method: str) -> list[str]:
    return list(CONTEXT_NUMERIC_COLUMNS)


def confirmed_training_columns_for_method(method: str) -> list[str]:
    return (
        training_categorical_columns_for_method(method)
        + context_numeric_columns_for_method(method)
        + list(TRAINING_MACD_NUMERIC_COLUMNS)
        + list(TRAINING_POSITION_NUMERIC_COLUMNS)
        + raw_factor_columns_for_method(method)
    )
```

Update `dataset_columns_for_method()`:

```python
def dataset_columns_for_method(method: str) -> list[str]:
    return (
        IDENTITY_COLUMNS
        + REVIEW_METADATA_COLUMNS
        + training_categorical_columns_for_method(method)
        + context_numeric_columns_for_method(method)
        + list(TRAINING_MACD_NUMERIC_COLUMNS)
        + list(TRAINING_POSITION_NUMERIC_COLUMNS)
        + raw_factor_columns_for_method(method)
        + LABEL_COLUMNS
    )
```

- [ ] **Step 4: Update imports and tests if needed**

If tests or scripts import removed names, update them to use:

```python
training_categorical_columns_for_method
context_numeric_columns_for_method
confirmed_training_columns_for_method
```

Do not keep aliases for removed review lists. This is a clean cutover.

- [ ] **Step 5: Run dataset tests**

Run:

```bash
python -m unittest tests.test_rank_dataset.RankDatasetTest.test_dataset_schema_excludes_review_scores_but_keeps_training_categoricals tests.test_rank_dataset.RankDatasetTest.test_load_candidate_rows_reads_b3_factor_artifact_with_b3_schema tests.test_rank_dataset.RankDatasetTest.test_load_candidate_rows_merges_runtime_factor_artifact
```

Expected: PASS.

- [ ] **Step 6: Commit dataset schema split**

```bash
git add scripts/ml/build_rank_dataset.py tests/test_rank_dataset.py
git commit -m "refactor: split training schema from review metadata"
```

---

## Task 3: RF/LightGBM training uses shared schema and fails on zero-coverage confirmed features

**Files:**
- Modify: `scripts/ml/train_rank_lgbm.py`
- Modify: `tests/test_rank_lgbm.py`

- [ ] **Step 1: Add failing coverage validation tests**

In `tests/test_rank_lgbm.py`, add imports from `scripts.ml.train_rank_lgbm`:

```python
    validate_selected_feature_coverage,
```

Add tests near existing feature selection tests:

```python
def test_select_feature_columns_uses_dataset_training_categoricals(self):
    columns = [
        "env",
        "signal",
        "signal_type",
        "daily_macd_phase_type",
        "daily_macd_wave_stage",
        "weekly_macd_phase_type",
        "weekly_macd_wave_stage",
        "weekly_daily_combo_type",
        "midline_state",
        "trend_structure",
        "close_to_zxdkx_pct",
    ]

    numeric, categorical = select_feature_columns(columns, feature_set="raw_plus_signal_macd", method="b3")

    self.assertIn("close_to_zxdkx_pct", numeric)
    self.assertNotIn("trend_structure", numeric)
    self.assertEqual(
        categorical,
        [
            "env",
            "signal",
            "signal_type",
            "daily_macd_phase_type",
            "daily_macd_wave_stage",
            "weekly_macd_phase_type",
            "weekly_macd_wave_stage",
            "weekly_daily_combo_type",
            "midline_state",
        ],
    )


def test_validate_selected_feature_coverage_fails_zero_coverage_confirmed_feature(self):
    rows = [
        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "close_to_zxdkx_pct": "1.2", "b3_volume_shrink_ratio": ""},
        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "close_to_zxdkx_pct": "0.8", "b3_volume_shrink_ratio": ""},
    ]

    with self.assertRaisesRegex(ValueError, "zero coverage.*b3_volume_shrink_ratio"):
        validate_selected_feature_coverage(
            rows,
            numeric_columns=["close_to_zxdkx_pct", "b3_volume_shrink_ratio"],
            categorical_columns=[],
        )


def test_validate_selected_feature_coverage_reports_non_empty_counts(self):
    rows = [
        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "close_to_zxdkx_pct": "1.2", "signal_type": "trend_start"},
        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "close_to_zxdkx_pct": "", "signal_type": "rebound"},
    ]

    report = validate_selected_feature_coverage(
        rows,
        numeric_columns=["close_to_zxdkx_pct"],
        categorical_columns=["signal_type"],
    )

    self.assertEqual(report["features"]["close_to_zxdkx_pct"]["non_empty_count"], 1)
    self.assertEqual(report["features"]["signal_type"]["non_empty_count"], 2)
    self.assertEqual(report["zero_coverage_features"], [])
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_select_feature_columns_uses_dataset_training_categoricals tests.test_rank_lgbm.RankLgbmTest.test_validate_selected_feature_coverage_fails_zero_coverage_confirmed_feature tests.test_rank_lgbm.RankLgbmTest.test_validate_selected_feature_coverage_reports_non_empty_counts
```

Expected: FAIL because `validate_selected_feature_coverage` does not exist and `select_feature_columns` still has local hardcoded categorical sets.

- [ ] **Step 3: Rewire categorical schema in `train_rank_lgbm.py`**

Replace local categorical constants with schema-derived values:

```python
CATEGORICAL_COLUMNS = set(rank_dataset_schema.training_categorical_columns_for_method(DEFAULT_METHOD)) | {"env"}
SIGNAL_CATEGORICAL_COLUMNS = {"env", "signal", "signal_type"}
MACD_CATEGORICAL_COLUMNS = {
    "daily_macd_phase_type",
    "daily_macd_wave_stage",
    "weekly_macd_phase_type",
    "weekly_macd_wave_stage",
    "weekly_daily_combo_type",
}
CONTEXT_CATEGORICAL_COLUMNS = {"midline_state"}
RAW_NUMERIC_COLUMNS = set(rank_dataset_schema.raw_factor_columns_for_method(DEFAULT_METHOD))
LEGACY_CONTEXT_NUMERIC_COLUMNS = set(rank_dataset_schema.context_numeric_columns_for_method(DEFAULT_METHOD))
```

Update method-specific helpers:

```python
def categorical_columns_for_method(method: str) -> set[str]:
    return set(rank_dataset_schema.training_categorical_columns_for_method(method)) | {"env"}


def raw_numeric_columns_for_method(method: str) -> set[str]:
    return set(rank_dataset_schema.raw_factor_columns_for_method(method)) | set(
        rank_dataset_schema.context_numeric_columns_for_method(method)
    )
```

Update `select_feature_columns()` to use `categorical_columns_for_method(method)` instead of local `CATEGORICAL_COLUMNS`.

- [ ] **Step 4: Implement feature coverage validation**

Add this function near `select_feature_columns()`:

```python
def feature_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, float) and math.isnan(value):
        return False
    return True


def validate_selected_feature_coverage(
    rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
) -> dict[str, Any]:
    selected = list(numeric_columns) + list(categorical_columns)
    features: dict[str, dict[str, int]] = {}
    zero_coverage: list[str] = []
    row_count = len(rows)

    for column in selected:
        present_count = sum(1 for row in rows if column in row)
        non_empty_count = sum(1 for row in rows if feature_value_present(row.get(column)))
        features[column] = {
            "present_count": present_count,
            "non_empty_count": non_empty_count,
        }
        if non_empty_count == 0:
            zero_coverage.append(column)

    report = {
        "row_count": row_count,
        "feature_count": len(selected),
        "features": features,
        "zero_coverage_features": zero_coverage,
    }
    if zero_coverage:
        raise ValueError(f"selected training features have zero coverage: {', '.join(zero_coverage)}")
    return report
```

- [ ] **Step 5: Call validation before RF and LightGBM**

In `train_and_report()`, after `numeric_columns/categorical_columns` are resolved and before `RandomForestDiagnosticsConfig`, add:

```python
feature_coverage = validate_selected_feature_coverage(
    train_rows + test_rows,
    numeric_columns=numeric_columns,
    categorical_columns=categorical_columns,
)
```

Add to `report`:

```python
"feature_coverage": feature_coverage,
```

If `feature_manifest` is used, this validation still applies to the manifest-selected columns.

- [ ] **Step 6: Run RF/LGBM unit tests**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_select_feature_columns_uses_dataset_training_categoricals tests.test_rank_lgbm.RankLgbmTest.test_validate_selected_feature_coverage_fails_zero_coverage_confirmed_feature tests.test_rank_lgbm.RankLgbmTest.test_validate_selected_feature_coverage_reports_non_empty_counts tests.test_rank_lgbm.RankLgbmTest.test_random_forest_diagnostics_reports_importance_and_metrics
```

Expected: PASS.

- [ ] **Step 7: Commit RF feature coverage gate**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: validate training feature coverage before rf diagnostics"
```

---

## Task 4: End-to-end B3 schema/artifact parity guard

**Files:**
- Modify: `tests/test_rank_dataset.py`
- Modify: `scripts/ml/build_rank_dataset.py` only if helper extraction is needed

- [ ] **Step 1: Add failing B3 fixture merge test for review-score exclusion and training-factor inclusion**

Add this test near `test_load_candidate_rows_reads_b3_factor_artifact_with_b3_schema`:

```python
def test_b3_factor_artifact_merge_ignores_review_scores_and_keeps_training_features(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        candidate_dir = root / "candidates"
        factor_dir = root / "factors" / "2026-05-25.b3"
        candidate_dir.mkdir(parents=True)
        factor_dir.mkdir(parents=True)
        (candidate_dir / "2026-05-25.b3.json").write_text(
            json.dumps(
                {
                    "method": "b3",
                    "pick_date": "2026-05-25",
                    "candidates": [{"code": "000001.SZ", "name": "平安银行", "signal": "B3+"}],
                }
            ),
            encoding="utf-8",
        )
        (factor_dir / "factors.json").write_text(
            json.dumps(
                {
                    "method": "b3",
                    "artifact_key": "2026-05-25",
                    "rows": [
                        {
                            "code": "000001.SZ",
                            "factors": {
                                "env": "neutral",
                                "signal_type": "trend_start",
                                "daily_macd_phase_type": "rising",
                                "weekly_daily_combo_type": "rising:2|rising:1",
                                "midline_state": "above_hold",
                                "b3_volume_shrink_ratio": 0.5,
                                "close_to_zxdkx_pct": 1.25,
                                "macd_phase": 4.5,
                                "daily_macd_wave_index": 2,
                                "box_mid_position_120d_pct": 74.0,
                                "weekly_macd_wave_index": 1,
                                "trend_structure": 4.0,
                                "price_position": 3.0,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        rows, warnings = load_candidate_rows(
            root,
            method="b3",
            start_date="2026-05-25",
            end_date="2026-05-25",
        )

    self.assertEqual(warnings, [])
    self.assertEqual(rows[0]["signal_type"], "trend_start")
    self.assertEqual(rows[0]["daily_macd_phase_type"], "rising")
    self.assertEqual(rows[0]["weekly_daily_combo_type"], "rising:2|rising:1")
    self.assertEqual(rows[0]["midline_state"], "above_hold")
    self.assertEqual(rows[0]["b3_volume_shrink_ratio"], 0.5)
    self.assertEqual(rows[0]["close_to_zxdkx_pct"], 1.25)
    self.assertEqual(rows[0]["macd_phase"], 4.5)
    self.assertEqual(rows[0]["daily_macd_wave_index"], 2)
    self.assertEqual(rows[0]["weekly_macd_wave_index"], 1)
    self.assertEqual(rows[0]["box_mid_position_120d_pct"], 74.0)
    self.assertNotIn("trend_structure", rows[0])
    self.assertNotIn("price_position", rows[0])
```

- [ ] **Step 2: Run test to verify expected behavior**

Run:

```bash
python -m unittest tests.test_rank_dataset.RankDatasetTest.test_b3_factor_artifact_merge_ignores_review_scores_and_keeps_training_features
```

Expected before Task 2 implementation: FAIL because review score columns are still present in dataset schema. Expected after Task 2: PASS.

- [ ] **Step 3: Run combined B3 parity tests**

Run:

```bash
cargo test b3_factor_artifact_excludes_review_scores_but_keeps_training_context b3_factor_profile_adds_b3_specific_raw_factors_only_for_b3
python -m unittest tests.test_rank_dataset.RankDatasetTest.test_b3_dataset_schema_has_independent_method_entry_with_b3_specific_factors tests.test_rank_dataset.RankDatasetTest.test_b3_factor_artifact_merge_ignores_review_scores_and_keeps_training_features tests.test_rank_lgbm.RankLgbmTest.test_select_feature_columns_uses_method_registered_raw_factors tests.test_rank_lgbm.RankLgbmTest.test_select_feature_columns_uses_dataset_training_categoricals
```

Expected: PASS.

- [ ] **Step 4: Commit parity guard**

```bash
git add tests/test_rank_dataset.py
git commit -m "test: guard b3 training feature parity"
```

---

## Task 5: Documentation updates

**Files:**
- Modify: `docs/model.md`
- Modify: `docs/workflow.md`
- Test: `tests/test_ml_documentation.py`

- [ ] **Step 1: Add failing documentation assertions**

In `tests/test_ml_documentation.py`, add a test:

```python
def test_model_docs_describe_factor_artifact_training_contract(self):
    docs = (PROJECT_ROOT / "docs" / "model.md").read_text(encoding="utf-8")

    self.assertIn("factors.json", docs)
    self.assertIn("训练特征契约", docs)
    self.assertIn("review-only", docs)
    self.assertIn("feature_coverage", docs)
    self.assertIn("zero coverage", docs)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m unittest tests.test_ml_documentation.MlDocumentationTest.test_model_docs_describe_factor_artifact_training_contract
```

Expected: FAIL because docs do not describe the new contract yet.

- [ ] **Step 3: Update `docs/model.md`**

Add a concise section near the RF diagnostics section:

```markdown
## factors.json 训练特征契约

`factors.json` 的 `rows[].factors` 只承载训练候选特征：数值因子、布尔因子和低基数类别因子。review-only 评分字段不进入 `rows[].factors`，包括 `trend_structure`、`price_position`、`volume_behavior`、`previous_abnormal_move`、`weekly_daily_combo_score`、`total_score` 和 `verdict`。

允许保留的训练语义字段必须被 schema 明确确认，例如数值字段 `macd_phase`、`daily_macd_wave_index`、`weekly_macd_wave_index`，新增原始位置字段 `box_mid_position_120d_pct`，以及类别字段 `signal_type`、`daily_macd_phase_type`、`daily_macd_wave_stage`、`weekly_macd_phase_type`、`weekly_macd_wave_stage`、`weekly_daily_combo_type` 和 `midline_state`。这些字段由 RF 和 LightGBM 共用同一份特征选择逻辑。

训练前会生成并校验 `feature_coverage`：每个被选中的训练特征必须在数据集中有至少一个非空值。若确认训练的特征 zero coverage，训练会失败并输出缺失列表，避免 schema 中的因子没有真实进入 RF/LightGBM。

- [ ] **Step 4: Update `docs/workflow.md`**

In 模型更新流程 after build dataset or train step, add:

```markdown
训练脚本会在随机森林诊断和 LightGBM 训练前校验 `feature_coverage`。如果某个已确认训练特征在训练窗口内 zero coverage，说明 Rust artifact、Python schema 或训练窗口数据不一致；先修复因子产出或 schema，不要用缺失填 0 继续训练。
```

- [ ] **Step 5: Run documentation tests**

Run:

```bash
python -m unittest tests.test_ml_documentation.MlDocumentationTest.test_model_docs_describe_factor_artifact_training_contract tests.test_ml_documentation.MlDocumentationTest.test_model_docs_describe_random_forest_factor_diagnostics
```

Expected: PASS.

- [ ] **Step 6: Commit docs**

```bash
git add docs/model.md docs/workflow.md tests/test_ml_documentation.py
git commit -m "docs: document factor artifact training contract"
```

---

## Task 6: Final verification

**Files:**
- No code edits unless verification finds a real defect.

- [ ] **Step 1: Run focused Rust test set**

Run:

```bash
cargo test b3_factor_artifact_excludes_review_scores_but_keeps_training_context b3_factor_profile_adds_b3_specific_raw_factors_only_for_b3 candidate_payload_factor_provider
```

Expected: PASS.

- [ ] **Step 2: Run focused Python test set**

Run:

```bash
python -m unittest tests.test_rank_dataset tests.test_rank_lgbm tests.test_ml_documentation
```

Expected: PASS.

- [ ] **Step 3: Inspect generated training report behavior using unit tests only**

Do not run full training unless the user asks. The unit tests must cover:

- review-only fields are excluded from dataset schema
- B3 training fields are retained
- selected RF/LGBM features are coverage-validated
- zero-coverage selected features fail fast
- RF diagnostics still run on the shared selected features

- [ ] **Step 4: Final commit if any verification-only fixes were needed**

```bash
git add <changed-files>
git commit -m "fix: align factor training contract verification"
```

---

## Self-Review

- Spec coverage: covers Rust `factors.json` cleanup, Python RF/LGBM feature completeness, B3-specific factor parity, tests, and docs.
- Placeholder scan: no TBD/TODO placeholders. Every code step includes concrete snippets or exact assertions.
- Type consistency: Rust uses existing `FactorRow` and `FactorValue`; Python functions use existing `Sequence[dict[str, Any]]` style and existing schema module import alias `rank_dataset_schema`.
- Scope: intentionally does not introduce automatic RF-based feature elimination. RF remains diagnostics plus shared feature gate.
- Risk: zero-coverage gate may expose existing sparse DB/schema problems. That is intended; failure message must list exact feature names so schema or Rust production can be fixed.
