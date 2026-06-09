# Random Forest Factor Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 LightGBM 训练前默认运行随机森林因子诊断，把诊断报告写入训练 trial 目录，并更新模型维护文档和 skill。

**Architecture:** 在 `scripts/ml/train_rank_lgbm.py` 内复用现有特征选择、one-hot 和时间切分逻辑，新增随机森林诊断函数、报告写入函数和阈值门禁。LightGBM 生产产物保持不变，`lgbm_rank_report*.json/md` 只嵌入随机森林诊断摘要。

**Tech Stack:** Python 3.11、LightGBM、scikit-learn `RandomForestClassifier`、`unittest`、项目内 model-maintenance skill 文档。

---

## File Structure

- Modify: `scripts/ml/train_rank_lgbm.py`
  - 增加 `scikit-learn` uv dependency。
  - 增加 `RandomForestDiagnosticsConfig`、`RandomForestThresholdError`。
  - 增加随机森林诊断、概率打分、报告摘要、Markdown 写入、阈值门禁函数。
  - 扩展 `train_and_report()` 和 `parse_args()`。
- Modify: `tests/test_rank_lgbm.py`
  - 覆盖参数解析、随机森林诊断核心逻辑、报告落盘、阈值失败和跳过诊断。
- Modify: `docs/model.md`
  - 更新训练流程图、训练命令说明和训练产物说明。
- Modify: `.agents/skills/model-maintenance/SKILL.md`
  - 更新训练流程和汇报要求。
- Modify: `.agents/skills/model-maintenance/references/model-maintenance.md`
  - 更新产物清单、调参检查项、推荐汇报模板。
- Modify: `tests/test_ml_documentation.py`
  - 用文档测试约束模型文档和 skill 必须提到随机森林诊断产物和汇报字段。

---

### Task 1: CLI 参数和诊断配置

**Files:**
- Modify: `tests/test_rank_lgbm.py`
- Modify: `scripts/ml/train_rank_lgbm.py`

- [ ] **Step 1: 写失败测试，覆盖默认启用和跳过开关**

在 `tests/test_rank_lgbm.py` 的 `RankLgbmTest` 中新增：

```python
    def test_parse_args_enables_random_forest_diagnostics_by_default(self):
        args = parse_args([])

        self.assertTrue(args.rf_diagnostics)
        self.assertEqual(args.rf_n_estimators, 300)
        self.assertIsNone(args.rf_max_depth)
        self.assertEqual(args.rf_min_samples_leaf, 20)
        self.assertEqual(args.rf_max_features, "sqrt")
        self.assertIsNone(args.rf_min_oob_score)
        self.assertIsNone(args.rf_min_test_rank_ic_ret3)

    def test_parse_args_accepts_random_forest_thresholds_and_skip_flag(self):
        args = parse_args(
            [
                "--skip-rf-diagnostics",
                "--rf-n-estimators",
                "123",
                "--rf-max-depth",
                "7",
                "--rf-min-samples-leaf",
                "11",
                "--rf-max-features",
                "log2",
                "--rf-min-oob-score",
                "0.51",
                "--rf-min-test-rank-ic-ret3",
                "0.02",
            ]
        )

        self.assertFalse(args.rf_diagnostics)
        self.assertEqual(args.rf_n_estimators, 123)
        self.assertEqual(args.rf_max_depth, 7)
        self.assertEqual(args.rf_min_samples_leaf, 11)
        self.assertEqual(args.rf_max_features, "log2")
        self.assertEqual(args.rf_min_oob_score, 0.51)
        self.assertEqual(args.rf_min_test_rank_ic_ret3, 0.02)
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_parse_args_enables_random_forest_diagnostics_by_default tests.test_rank_lgbm.RankLgbmTest.test_parse_args_accepts_random_forest_thresholds_and_skip_flag
```

Expected: FAIL，错误包含 `Namespace` 缺少 `rf_diagnostics` 或 argparse 不识别新增参数。

- [ ] **Step 3: 实现最小参数解析和配置类型**

在 `scripts/ml/train_rank_lgbm.py` 顶部常量区新增：

```python
DEFAULT_RF_N_ESTIMATORS = 300
DEFAULT_RF_MIN_SAMPLES_LEAF = 20
DEFAULT_RF_MAX_FEATURES = "sqrt"
LOW_IMPORTANCE_THRESHOLD = 1e-6
```

在 `TrainedModelResult` 后新增：

```python
@dataclass
class RandomForestDiagnosticsConfig:
    enabled: bool = True
    n_estimators: int = DEFAULT_RF_N_ESTIMATORS
    max_depth: int | None = None
    min_samples_leaf: int = DEFAULT_RF_MIN_SAMPLES_LEAF
    max_features: str | int | float | None = DEFAULT_RF_MAX_FEATURES
    min_oob_score: float | None = None
    min_test_rank_ic_ret3: float | None = None


class RandomForestThresholdError(ValueError):
    pass
```

在 `parse_args()` 中加入 mutually exclusive group 和参数：

```python
    rf_group = parser.add_mutually_exclusive_group()
    rf_group.add_argument("--rf-diagnostics", dest="rf_diagnostics", action="store_true", default=True)
    rf_group.add_argument("--skip-rf-diagnostics", dest="rf_diagnostics", action="store_false")
    parser.add_argument("--rf-n-estimators", type=int, default=DEFAULT_RF_N_ESTIMATORS)
    parser.add_argument("--rf-max-depth", type=int)
    parser.add_argument("--rf-min-samples-leaf", type=int, default=DEFAULT_RF_MIN_SAMPLES_LEAF)
    parser.add_argument("--rf-max-features", default=DEFAULT_RF_MAX_FEATURES)
    parser.add_argument("--rf-min-oob-score", type=float)
    parser.add_argument("--rf-min-test-rank-ic-ret3", type=float)
```

- [ ] **Step 4: 运行测试并确认通过**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_parse_args_enables_random_forest_diagnostics_by_default tests.test_rank_lgbm.RankLgbmTest.test_parse_args_accepts_random_forest_thresholds_and_skip_flag
```

Expected: PASS。

- [ ] **Step 5: 提交任务 1**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: add rf diagnostic training options"
```

---

### Task 2: 随机森林诊断核心函数

**Files:**
- Modify: `tests/test_rank_lgbm.py`
- Modify: `scripts/ml/train_rank_lgbm.py`

- [ ] **Step 1: 写失败测试，覆盖共享特征矩阵、重要性和指标输出**

更新 `tests/test_rank_lgbm.py` import 列表，加入：

```python
    RandomForestDiagnosticsConfig,
    run_random_forest_diagnostics,
```

新增测试：

```python
    def test_random_forest_diagnostics_reports_importance_and_metrics(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "3", "env": "weak"},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0", "env": "strong"},
            {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "4", "env": "weak"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0", "env": "strong"},
        ]
        captured = {}

        class FakeRandomForestClassifier:
            def __init__(self, **kwargs):
                captured["kwargs"] = kwargs
                self.classes_ = [0, 3]
                self.feature_importances_ = [0.8, 0.2, 0.0]
                self.oob_score_ = 0.62

            def fit(self, matrix, labels):
                captured["fit_matrix"] = matrix
                captured["fit_labels"] = labels
                return self

            def predict_proba(self, matrix):
                return [[0.1, 0.9] if row[0] > 0 else [0.9, 0.1] for row in matrix]

            def predict(self, matrix):
                return [3 if row[0] > 0 else 0 for row in matrix]

            def score(self, matrix, labels):
                return 1.0

        fake_sklearn_ensemble = types.SimpleNamespace(RandomForestClassifier=FakeRandomForestClassifier)
        with patch.dict(sys.modules, {"sklearn.ensemble": fake_sklearn_ensemble}):
            diagnostics = run_random_forest_diagnostics(
                rows[:2],
                rows[2:],
                numeric_columns=["x"],
                categorical_columns=["env"],
                label_column="rank_label_3d",
                label_gain=[0, 1, 3, 7],
                num_threads=2,
                fixed_categorical_levels={"env": ["weak", "strong"]},
                config=RandomForestDiagnosticsConfig(n_estimators=17, min_samples_leaf=3),
            )

        self.assertEqual(captured["kwargs"]["n_estimators"], 17)
        self.assertEqual(captured["kwargs"]["min_samples_leaf"], 3)
        self.assertEqual(captured["kwargs"]["n_jobs"], 2)
        self.assertEqual(captured["kwargs"]["random_state"], 17)
        self.assertTrue(captured["kwargs"]["bootstrap"])
        self.assertTrue(captured["kwargs"]["oob_score"])
        self.assertEqual(captured["fit_labels"], [3, 0])
        self.assertEqual(diagnostics["status"], "passed")
        self.assertEqual(diagnostics["feature_count"], 3)
        self.assertEqual(diagnostics["top_features"][0], {"feature": "x", "importance": 0.8})
        self.assertEqual(diagnostics["low_importance_features"], [{"feature": "env=strong", "importance": 0.0}])
        self.assertEqual(diagnostics["oob_score"], 0.62)
        self.assertEqual(diagnostics["accuracy"], {"train": 1.0, "test": 1.0})
        self.assertEqual(diagnostics["metrics"]["test"]["top3_ret3_positive_rate"], 50.0)
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_random_forest_diagnostics_reports_importance_and_metrics
```

Expected: FAIL，错误包含无法 import `run_random_forest_diagnostics`。

- [ ] **Step 3: 实现随机森林诊断核心函数**

在 `scripts/ml/train_rank_lgbm.py` 中 `assign_scores()` 后新增：

```python
def random_forest_n_jobs(num_threads: int) -> int | None:
    return num_threads if num_threads > 0 else None


def random_forest_probability_scores(model: Any, probabilities: Sequence[Sequence[float]], label_gain: Sequence[int]) -> list[float]:
    classes = [int(value) for value in getattr(model, "classes_", [])]
    if not classes:
        return []
    scores: list[float] = []
    for row in probabilities:
        total = 0.0
        for class_value, probability in zip(classes, row):
            gain = label_gain[class_value] if 0 <= class_value < len(label_gain) else float(class_value)
            total += float(probability) * float(gain)
        scores.append(total)
    return scores


def random_forest_fallback_scores(model: Any, matrix: Sequence[Sequence[float]]) -> list[float]:
    return [float(value) for value in model.predict(matrix)]


def run_random_forest_diagnostics(
    train_rows: Sequence[dict[str, Any]],
    test_rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    label_column: str,
    label_gain: Sequence[int],
    num_threads: int,
    fixed_categorical_levels: dict[str, list[str]],
    config: RandomForestDiagnosticsConfig,
) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestClassifier

    levels = category_levels(
        train_rows,
        categorical_columns,
        fixed_categorical_levels=fixed_categorical_levels,
    )
    train_matrix, feature_names = build_feature_matrix(
        train_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
    )
    test_matrix, _feature_names = build_feature_matrix(
        test_rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
    )
    model = RandomForestClassifier(
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        min_samples_leaf=config.min_samples_leaf,
        max_features=config.max_features,
        random_state=17,
        bootstrap=True,
        oob_score=True,
        n_jobs=random_forest_n_jobs(num_threads),
    )
    train_labels = labels(train_rows, label_column=label_column)
    test_labels = labels(test_rows, label_column=label_column)
    model.fit(train_matrix, train_labels)

    try:
        train_scores = random_forest_probability_scores(model, model.predict_proba(train_matrix), label_gain)
        test_scores = random_forest_probability_scores(model, model.predict_proba(test_matrix), label_gain)
    except Exception:
        train_scores = random_forest_fallback_scores(model, train_matrix)
        test_scores = random_forest_fallback_scores(model, test_matrix)

    importances = [float(value) for value in getattr(model, "feature_importances_", [])]
    ranked_features = sorted(zip(feature_names, importances), key=lambda item: (-item[1], item[0]))
    low_features = sorted(
        ((feature, importance) for feature, importance in zip(feature_names, importances) if importance <= LOW_IMPORTANCE_THRESHOLD),
        key=lambda item: (item[1], item[0]),
    )

    return {
        "enabled": True,
        "status": "passed",
        "label_column": label_column,
        "feature_count": len(feature_names),
        "numeric_feature_count": len(numeric_columns),
        "categorical_feature_count": len(categorical_columns),
        "params": {
            "n_estimators": config.n_estimators,
            "max_depth": config.max_depth,
            "min_samples_leaf": config.min_samples_leaf,
            "max_features": config.max_features,
            "random_state": 17,
            "bootstrap": True,
            "oob_score": True,
            "n_jobs": random_forest_n_jobs(num_threads),
        },
        "thresholds": {
            "min_oob_score": config.min_oob_score,
            "min_test_rank_ic_ret3": config.min_test_rank_ic_ret3,
        },
        "metrics": {
            "train": evaluate_model(assign_scores(train_rows, train_scores), top_n=3),
            "test": evaluate_model(assign_scores(test_rows, test_scores), top_n=3),
        },
        "oob_score": getattr(model, "oob_score_", None),
        "accuracy": {
            "train": float(model.score(train_matrix, train_labels)),
            "test": float(model.score(test_matrix, test_labels)),
        },
        "top_features": [{"feature": feature, "importance": round(importance, 8)} for feature, importance in ranked_features[:50]],
        "low_importance_features": [
            {"feature": feature, "importance": round(importance, 8)} for feature, importance in low_features
        ],
        "output_paths": {},
    }
```

- [ ] **Step 4: 运行测试并确认通过**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_random_forest_diagnostics_reports_importance_and_metrics
```

Expected: PASS。

- [ ] **Step 5: 提交任务 2**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: compute rf factor diagnostics"
```

---

### Task 3: 诊断报告落盘并嵌入 LightGBM report

**Files:**
- Modify: `tests/test_rank_lgbm.py`
- Modify: `scripts/ml/train_rank_lgbm.py`

- [ ] **Step 1: 写失败测试，覆盖默认落盘和 report 摘要**

在 `tests/test_rank_lgbm.py` 中新增：

```python
    def test_train_report_writes_and_embeds_random_forest_diagnostics(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            from scripts.ml.train_rank_lgbm import TrainedModelResult

            scored = [{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in test_rows]
            return TrainedModelResult(
                train_scored=[{**row, "model_score": float(row.get("rank_label_3d") or 0)} for row in train_rows],
                test_scored=scored,
                top_features=[{"feature": "x", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["x"],
                lightgbm_feature_names=["x"],
                category_levels={},
            )

        rf_payload = {
            "enabled": True,
            "status": "passed",
            "label_column": "rank_label_3d",
            "feature_count": 1,
            "numeric_feature_count": 1,
            "categorical_feature_count": 0,
            "params": {"n_estimators": 300},
            "thresholds": {"min_oob_score": None, "min_test_rank_ic_ret3": None},
            "metrics": {"test": {"rank_ic_ret3": 0.12, "top3_ret3_positive_rate": 66.7}, "train": {}},
            "oob_score": 0.61,
            "accuracy": {"train": 0.8, "test": 0.7},
            "top_features": [{"feature": "x", "importance": 0.9}],
            "low_importance_features": [],
            "output_paths": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "1"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.run_random_forest_diagnostics", return_value=rf_payload):
                with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                    report = train_and_report(
                        dataset,
                        output_dir,
                        test_ratio=0.5,
                        feature_set="raw_numeric",
                        num_leaves=5,
                        min_data_in_leaf=1,
                        num_boost_round=1,
                        learning_rate=0.1,
                        label_column="rank_label_3d",
                        method="b2",
                    )

            rf_json = json.loads((output_dir / "rf_feature_diagnostics.json").read_text(encoding="utf-8"))
            rf_markdown = (output_dir / "rf_feature_diagnostics.md").read_text(encoding="utf-8")
            persisted = json.loads((output_dir / "lgbm_rank_report_raw_numeric.json").read_text(encoding="utf-8"))

        self.assertEqual(rf_json["output_paths"]["json"], str(output_dir / "rf_feature_diagnostics.json"))
        self.assertIn("# random forest factor diagnostics", rf_markdown)
        self.assertEqual(report["rf_diagnostics"]["status"], "passed")
        self.assertEqual(report["rf_diagnostics"]["oob_score"], 0.61)
        self.assertEqual(report["rf_diagnostics"]["top_features"], [{"feature": "x", "importance": 0.9}])
        self.assertEqual(persisted["rf_diagnostics"]["path"], str(output_dir / "rf_feature_diagnostics.json"))
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_train_report_writes_and_embeds_random_forest_diagnostics
```

Expected: FAIL，`rf_feature_diagnostics.json` 不存在或 report 缺少 `rf_diagnostics`。

- [ ] **Step 3: 实现报告路径、Markdown 和摘要函数**

在 `scripts/ml/train_rank_lgbm.py` 中 `report_paths()` 前新增：

```python
def rf_diagnostic_paths(output_dir: Path) -> tuple[Path, Path]:
    return output_dir / "rf_feature_diagnostics.json", output_dir / "rf_feature_diagnostics.md"


def rf_diagnostics_summary(diagnostics: dict[str, Any], json_path: Path | None = None) -> dict[str, Any]:
    return {
        "enabled": bool(diagnostics.get("enabled")),
        "path": str(json_path) if json_path is not None else None,
        "status": diagnostics.get("status"),
        "oob_score": diagnostics.get("oob_score"),
        "metrics": {"test": (diagnostics.get("metrics") or {}).get("test") or {}},
        "top_features": list(diagnostics.get("top_features") or [])[:20],
        "low_importance_feature_count": len(diagnostics.get("low_importance_features") or []),
    }


def markdown_rf_diagnostics(diagnostics: dict[str, Any]) -> str:
    metrics = ((diagnostics.get("metrics") or {}).get("test") or {})
    lines = [
        "# random forest factor diagnostics",
        "",
        f"status: `{diagnostics.get('status')}`",
        f"label: `{diagnostics.get('label_column')}`",
        f"features: `{diagnostics.get('feature_count')}`",
        f"oob_score: `{diagnostics.get('oob_score')}`",
        f"test rank_ic_ret3: `{metrics.get('rank_ic_ret3')}`",
        f"test top3_ret3_positive_rate: `{metrics.get('top3_ret3_positive_rate')}`",
        "",
        "## top features",
        "",
    ]
    lines.extend(f"- {item['feature']}: {item['importance']}" for item in list(diagnostics.get("top_features") or [])[:20])
    return "\n".join(lines) + "\n"


def write_rf_diagnostics_artifacts(diagnostics: dict[str, Any], output_dir: Path) -> tuple[dict[str, Any], Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = rf_diagnostic_paths(output_dir)
    payload = dict(diagnostics)
    payload["output_paths"] = {"json": str(json_path), "markdown": str(markdown_path)}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_rf_diagnostics(payload), encoding="utf-8")
    return payload, json_path, markdown_path
```

更新 `markdown_report()`，在 top features 后加入：

```python
    rf_summary = report.get("rf_diagnostics") or {}
    if rf_summary:
        rf_metrics = ((rf_summary.get("metrics") or {}).get("test") or {})
        lines.extend(
            [
                "",
                "## random forest factor diagnostics",
                "",
                f"- status: {rf_summary.get('status')}",
                f"- oob_score: {rf_summary.get('oob_score')}",
                f"- test rank_ic_ret3: {rf_metrics.get('rank_ic_ret3')}",
                f"- low importance features: {rf_summary.get('low_importance_feature_count')}",
            ]
        )
        lines.extend(f"- {item['feature']}: {item['importance']}" for item in list(rf_summary.get("top_features") or [])[:20])
```

在 `train_and_report()` 选择完特征后、LightGBM 训练前加入：

```python
    rf_config = RandomForestDiagnosticsConfig(
        enabled=rf_diagnostics,
        n_estimators=rf_n_estimators,
        max_depth=rf_max_depth,
        min_samples_leaf=rf_min_samples_leaf,
        max_features=rf_max_features,
        min_oob_score=rf_min_oob_score,
        min_test_rank_ic_ret3=rf_min_test_rank_ic_ret3,
    )
    if rf_config.enabled:
        rf_payload = run_random_forest_diagnostics(
            train_rows,
            test_rows,
            numeric_columns=numeric_columns,
            categorical_columns=categorical_columns,
            label_column=label_column,
            label_gain=resolved_label_gain,
            num_threads=num_threads,
            fixed_categorical_levels=fixed_categorical_levels,
            config=rf_config,
        )
        rf_payload, rf_json_path, _rf_markdown_path = write_rf_diagnostics_artifacts(rf_payload, output_dir)
        rf_summary = rf_diagnostics_summary(rf_payload, rf_json_path)
    else:
        rf_payload = {"enabled": False, "status": "skipped", "output_paths": {}}
        rf_summary = rf_diagnostics_summary(rf_payload, None)
```

扩展 `train_and_report()` signature，加入随机森林参数；在 report 字典中加入：

```python
        "rf_diagnostics": rf_summary,
```

在 `main()` 调用 `train_and_report()` 时透传新增参数。

- [ ] **Step 4: 运行测试并确认通过**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_train_report_writes_and_embeds_random_forest_diagnostics
```

Expected: PASS。

- [ ] **Step 5: 提交任务 3**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: write rf diagnostics with lgbm reports"
```

---

### Task 4: 阈值门禁和跳过诊断

**Files:**
- Modify: `tests/test_rank_lgbm.py`
- Modify: `scripts/ml/train_rank_lgbm.py`

- [ ] **Step 1: 写失败测试，覆盖阈值失败阻止 LightGBM**

更新 import 列表，加入：

```python
    RandomForestThresholdError,
```

新增测试：

```python
    def test_random_forest_threshold_failure_writes_report_and_stops_lgbm(self):
        rf_payload = {
            "enabled": True,
            "status": "passed",
            "label_column": "rank_label_3d",
            "feature_count": 1,
            "numeric_feature_count": 1,
            "categorical_feature_count": 0,
            "params": {},
            "thresholds": {"min_oob_score": 0.7, "min_test_rank_ic_ret3": None},
            "metrics": {"test": {"rank_ic_ret3": 0.03}, "train": {}},
            "oob_score": 0.61,
            "accuracy": {"train": 0.8, "test": 0.7},
            "top_features": [{"feature": "x", "importance": 0.9}],
            "low_importance_features": [],
            "output_paths": {},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "1"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0"},
                    ]
                )
            output_dir = root / "model"

            with patch("scripts.ml.train_rank_lgbm.run_random_forest_diagnostics", return_value=rf_payload):
                with patch("scripts.ml.train_rank_lgbm.train_model_result") as train_lgbm:
                    with self.assertRaisesRegex(RandomForestThresholdError, "oob_score"):
                        train_and_report(
                            dataset,
                            output_dir,
                            test_ratio=0.5,
                            feature_set="raw_numeric",
                            num_leaves=5,
                            min_data_in_leaf=1,
                            num_boost_round=1,
                            learning_rate=0.1,
                            label_column="rank_label_3d",
                            rf_min_oob_score=0.7,
                            method="b2",
                        )

                    train_lgbm.assert_not_called()

            self.assertTrue((output_dir / "rf_feature_diagnostics.json").exists())
            self.assertFalse((output_dir / "model.txt").exists())
```

- [ ] **Step 2: 写失败测试，覆盖 skip 不调用 sklearn 诊断**

新增测试：

```python
    def test_train_report_can_skip_random_forest_diagnostics(self):
        class DummyModel:
            def save_model(self, path: str) -> None:
                Path(path).write_text("dummy model", encoding="utf-8")

        def fake_train_model_result(train_rows, test_rows, **_kwargs):
            from scripts.ml.train_rank_lgbm import TrainedModelResult

            return TrainedModelResult(
                train_scored=[{**row, "model_score": 1.0} for row in train_rows],
                test_scored=[{**row, "model_score": 1.0} for row in test_rows],
                top_features=[{"feature": "x", "importance": 1}],
                feature_count=1,
                model=DummyModel(),
                feature_names=["x"],
                lightgbm_feature_names=["x"],
                category_levels={},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "ret3", "ret5", "x"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "5", "x": "1"},
                        {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "0", "x": "0"},
                        {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "7", "ret5": "6", "x": "1"},
                        {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "-2", "ret5": "-1", "x": "0"},
                    ]
                )

            with patch("scripts.ml.train_rank_lgbm.run_random_forest_diagnostics") as rf_run:
                with patch("scripts.ml.train_rank_lgbm.train_model_result", side_effect=fake_train_model_result):
                    report = train_and_report(
                        dataset,
                        root / "model",
                        test_ratio=0.5,
                        feature_set="raw_numeric",
                        num_leaves=5,
                        min_data_in_leaf=1,
                        num_boost_round=1,
                        learning_rate=0.1,
                        label_column="rank_label_3d",
                        rf_diagnostics=False,
                        method="b2",
                    )

        rf_run.assert_not_called()
        self.assertEqual(report["rf_diagnostics"], {
            "enabled": False,
            "path": None,
            "status": "skipped",
            "oob_score": None,
            "metrics": {"test": {}},
            "top_features": [],
            "low_importance_feature_count": 0,
        })
```

- [ ] **Step 3: 运行测试并确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_random_forest_threshold_failure_writes_report_and_stops_lgbm tests.test_rank_lgbm.RankLgbmTest.test_train_report_can_skip_random_forest_diagnostics
```

Expected: FAIL，阈值未阻断或 skip 摘要不匹配。

- [ ] **Step 4: 实现阈值检查**

在 `scripts/ml/train_rank_lgbm.py` 中 `write_rf_diagnostics_artifacts()` 后新增：

```python
def random_forest_threshold_failures(diagnostics: dict[str, Any]) -> list[str]:
    thresholds = diagnostics.get("thresholds") or {}
    failures: list[str] = []
    min_oob = as_float(thresholds.get("min_oob_score"))
    oob_score = as_float(diagnostics.get("oob_score"))
    if min_oob is not None and (oob_score is None or oob_score < min_oob):
        failures.append(f"oob_score {oob_score} < {min_oob}")
    min_rank_ic = as_float(thresholds.get("min_test_rank_ic_ret3"))
    test_metrics = ((diagnostics.get("metrics") or {}).get("test") or {})
    rank_ic = as_float(test_metrics.get("rank_ic_ret3"))
    if min_rank_ic is not None and (rank_ic is None or rank_ic < min_rank_ic):
        failures.append(f"test rank_ic_ret3 {rank_ic} < {min_rank_ic}")
    return failures
```

在 `train_and_report()` 写完 RF 诊断后加入：

```python
        failures = random_forest_threshold_failures(rf_payload)
        if failures:
            rf_payload["status"] = "failed_threshold"
            rf_payload, rf_json_path, _rf_markdown_path = write_rf_diagnostics_artifacts(rf_payload, output_dir)
            raise RandomForestThresholdError(
                f"random forest diagnostics failed thresholds: {', '.join(failures)}; report={rf_json_path}"
            )
```

- [ ] **Step 5: 运行测试并确认通过**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_random_forest_threshold_failure_writes_report_and_stops_lgbm tests.test_rank_lgbm.RankLgbmTest.test_train_report_can_skip_random_forest_diagnostics
```

Expected: PASS。

- [ ] **Step 6: 提交任务 4**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: gate lgbm training with rf diagnostics"
```

---

### Task 5: 依赖、主入口和 Python 单元测试回归

**Files:**
- Modify: `scripts/ml/train_rank_lgbm.py`
- Modify: `tests/test_rank_lgbm.py`

- [ ] **Step 1: 写失败测试，确认 `main()` 透传随机森林参数**

新增测试：

```python
    def test_main_passes_random_forest_options_to_train_and_report(self):
        captured = {}

        def fake_train_and_report(dataset, output_dir, **kwargs):
            captured["dataset"] = dataset
            captured["output_dir"] = output_dir
            captured["kwargs"] = kwargs
            return {"metrics": {"test": {}}}

        with patch("scripts.ml.train_rank_lgbm.train_and_report", side_effect=fake_train_and_report):
            from scripts.ml.train_rank_lgbm import main

            exit_code = main(
                [
                    "--method",
                    "b2",
                    "--skip-rf-diagnostics",
                    "--rf-n-estimators",
                    "19",
                    "--rf-max-depth",
                    "5",
                    "--rf-min-oob-score",
                    "0.6",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertFalse(captured["kwargs"]["rf_diagnostics"])
        self.assertEqual(captured["kwargs"]["rf_n_estimators"], 19)
        self.assertEqual(captured["kwargs"]["rf_max_depth"], 5)
        self.assertEqual(captured["kwargs"]["rf_min_oob_score"], 0.6)
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_main_passes_random_forest_options_to_train_and_report
```

Expected: FAIL，`train_and_report()` 未收到随机森林参数。

- [ ] **Step 3: 实现主入口透传和 dependency**

在 `scripts/ml/train_rank_lgbm.py` uv dependencies 中加入：

```python
#   "scikit-learn",
```

在 `main()` 调用 `train_and_report()` 时加入：

```python
        rf_diagnostics=args.rf_diagnostics,
        rf_n_estimators=args.rf_n_estimators,
        rf_max_depth=args.rf_max_depth,
        rf_min_samples_leaf=args.rf_min_samples_leaf,
        rf_max_features=args.rf_max_features,
        rf_min_oob_score=args.rf_min_oob_score,
        rf_min_test_rank_ic_ret3=args.rf_min_test_rank_ic_ret3,
```

- [ ] **Step 4: 跑 Python 训练脚本测试和编译检查**

Run:

```bash
python -m unittest tests/test_rank_lgbm.py
python -m py_compile scripts/ml/train_rank_lgbm.py
```

Expected: PASS，`py_compile` 无输出。

- [ ] **Step 5: 提交任务 5**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "test: cover rf diagnostics cli integration"
```

---

### Task 6: 模型文档和 model-maintenance skill 更新

**Files:**
- Modify: `tests/test_ml_documentation.py`
- Modify: `docs/model.md`
- Modify: `.agents/skills/model-maintenance/SKILL.md`
- Modify: `.agents/skills/model-maintenance/references/model-maintenance.md`

- [ ] **Step 1: 写失败文档测试，约束 docs 和 skill 内容**

在 `tests/test_ml_documentation.py` 中新增：

```python
    def test_model_docs_describe_random_forest_factor_diagnostics(self):
        docs = (PROJECT_ROOT / "docs" / "model.md").read_text(encoding="utf-8")

        self.assertIn("随机森林因子诊断", docs)
        self.assertIn("rf_feature_diagnostics.json", docs)
        self.assertIn("rf_diagnostics", docs)
        self.assertIn("--skip-rf-diagnostics", docs)
        self.assertIn("不进入 Rust 生产推理", docs)

    def test_model_maintenance_skill_reports_random_forest_diagnostics(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "SKILL.md",
                PROJECT_ROOT / ".agents" / "skills" / "model-maintenance" / "references" / "model-maintenance.md",
            ]
        )

        self.assertIn("随机森林因子诊断", combined)
        self.assertIn("rf_feature_diagnostics.json", combined)
        self.assertIn("rf_diagnostics", combined)
        self.assertIn("low_importance_feature_count", combined)
        self.assertIn("不进入生产推理", combined)
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
python -m unittest tests.test_ml_documentation.MlDocumentationTests.test_model_docs_describe_random_forest_factor_diagnostics tests.test_ml_documentation.MlDocumentationTests.test_model_maintenance_skill_reports_random_forest_diagnostics
```

Expected: FAIL，文档缺少随机森林诊断说明。

- [ ] **Step 3: 更新 `docs/model.md`**

修改训练流程 Mermaid，在 `BD -> TR` 中间加入随机森林诊断节点：

```mermaid
flowchart LR
    BC["backfill_candidates.py<br/>补齐历史候选"] --> BD["build_rank_dataset.py<br/>构建样本集 + label"]
    BD --> RF["train_rank_lgbm.py<br/>随机森林因子诊断"]
    RF --> TR["train_rank_lgbm.py<br/>LightGBM 训练 + 评估"]
```

在训练命令后补充参数说明：

```markdown
训练前默认运行随机森林因子诊断，输出：

```text
diagnostics/ml/<method>/model/rf_feature_diagnostics.json
diagnostics/ml/<method>/model/rf_feature_diagnostics.md
```

诊断报告会嵌入 `lgbm_rank_report*.json/md` 的 `rf_diagnostics` 字段。随机森林只用于训练前确认因子有效性，不进入 Rust 生产推理；需要快速跳过时可传 `--skip-rf-diagnostics`。
```

- [ ] **Step 4: 更新 model-maintenance skill 主文档**

在 `.agents/skills/model-maintenance/SKILL.md` 的训练命令后加入：

```markdown
`train_rank_lgbm.py` 默认在 LightGBM 前运行随机森林因子诊断，诊断产物写到同一 `output-dir`：`rf_feature_diagnostics.json/md`。该诊断只用于确认因子有效性和调参汇报，不进入生产推理，也不替代 promote dry-run。临时快速训练可传 `--skip-rf-diagnostics`，但正式候选 trial 应保留诊断。
```

在训练完成汇报字段清单加入：

```text
random_forest_diagnostics:
  status
  oob_score
  metrics.test.rank_ic_ret3
  metrics.test.top3_ret3_positive_rate
  top_features
  low_importance_feature_count
  threshold_status
```

- [ ] **Step 5: 更新 model-maintenance reference**

在 `.agents/skills/model-maintenance/references/model-maintenance.md` 的训练维护产物清单和 trial 产物清单加入：

```text
diagnostics/ml/<method>/model/rf_feature_diagnostics.json
diagnostics/ml/<method>/model/rf_feature_diagnostics.md
```

在训练 report 检查项加入：

```markdown
随机森林因子诊断至少检查：

- `rf_diagnostics.status`
- `rf_diagnostics.oob_score`
- `rf_diagnostics.metrics.test.rank_ic_ret3`
- `rf_diagnostics.top_features`
- `rf_diagnostics.low_importance_feature_count`
```

在停止条件加入：

```markdown
- 配置了随机森林阈值且 `rf_diagnostics.status=failed_threshold`。
```

- [ ] **Step 6: 运行文档测试并确认通过**

Run:

```bash
python -m unittest tests.test_ml_documentation.MlDocumentationTests.test_model_docs_describe_random_forest_factor_diagnostics tests.test_ml_documentation.MlDocumentationTests.test_model_maintenance_skill_reports_random_forest_diagnostics
```

Expected: PASS。

- [ ] **Step 7: 提交任务 6**

```bash
git add docs/model.md .agents/skills/model-maintenance/SKILL.md .agents/skills/model-maintenance/references/model-maintenance.md tests/test_ml_documentation.py
git commit -m "docs: document rf factor diagnostics"
```

---

### Task 7: 全量验证和收尾

**Files:**
- Read/verify only: modified files from tasks 1-6

- [ ] **Step 1: 运行目标 Python 测试**

Run:

```bash
python -m unittest tests/test_rank_lgbm.py tests/test_ml_documentation.py
```

Expected: PASS。

- [ ] **Step 2: 运行训练脚本编译检查**

Run:

```bash
python -m py_compile scripts/ml/train_rank_lgbm.py
```

Expected: 无输出，exit code 0。

- [ ] **Step 3: 检查工作区状态**

Run:

```bash
git status --short --branch
```

Expected: 分支 ahead 多个本次提交，工作区无未提交改动。

- [ ] **Step 4: 汇报实现结果**

最终回复包含：

```text
已实现：随机森林训练前诊断、报告落盘、LightGBM report 摘要、阈值门禁、skip 开关、docs 和 model-maintenance skill 更新。
验证：列出实际运行的 unittest 和 py_compile 命令结果。
注意：随机森林不进入 Rust 生产推理；发布仍走 LightGBM promote dry-run。
```
