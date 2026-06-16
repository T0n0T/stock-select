# LightGBM 原生分类特征 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让训练脚本、模型元数据、发布校验和 Rust runtime 支持 LightGBM native categorical，同时保持现有 one-hot 模型完全兼容。

**Architecture:** 引入显式的分类编码协议：旧模型默认 `one_hot`，新模型可声明 `native`。Python 训练/导出在 `native` 模式下把分类值编码为稳定整数并用 `categorical_feature` 训练；Rust runtime 根据 metadata 选择 one-hot 或 native 构造特征向量。发布校验要求 native 模型包含完整编码表，避免线上线下特征维度或编码不一致。

**Tech Stack:** Rust `lightgbm3` runtime、Python `lightgbm` 训练脚本、`unittest`、Cargo 集成测试、现有 `model_metadata.json`/`feature_manifest.json` contract。

---

## 当前结论

当前 Rust runtime 只支持 one-hot 分类展开：

- `src/engine/inference.rs::build_feature_vector()` 对 `categorical_columns` 生成 `column=level` 的 0/1 特征。
- `tests/engine_inference.rs::feature_vector_follows_metadata_order_and_defaults_missing_numeric_to_zero` 已固定该行为。
- 当前 production b3 的 `categorical_columns` 虽然包含 `env` 等列，但实际输入 LightGBM 的是 one-hot 后的 `env=strong/env=neutral/env=weak`。

方案 C 不能只改 Python 训练。必须同时引入 metadata 编码协议和 Rust runtime 原生分类编码。

## 文件结构

- Modify: `scripts/ml/train_rank_lgbm.py`
  - 新增分类编码模式参数、native categorical 矩阵构造、metadata 写入、LightGBM native categorical 训练。
- Modify: `scripts/ml/export_lgbm_scores.py`
  - 读取 trial/feature manifest 的编码模式，用同一编码模式重新训练导出发布模型。
- Modify: `scripts/ml/promote_lgbm_model.py`
  - 校验 native categorical metadata 的完整性，防止缺编码表的模型发布。
- Modify: `src/engine/inference.rs`
  - 扩展 `ModelFeatureMetadata`，支持 `categorical_encoding=one_hot|native` 和 `categorical_code_maps`。
  - `build_feature_vector()` 保持 one-hot 默认行为，新增 native 路径。
- Modify: `tests/test_rank_lgbm.py`
  - 覆盖 Python native categorical 矩阵、metadata、训练参数和旧 one-hot 回归。
- Modify: `tests/test_lgbm_score_export.py`
  - 覆盖 export 继承 native 编码协议并写出可发布 metadata。
- Modify: `tests/test_lgbm_model_promotion.py`
  - 覆盖 promote 对 native metadata 的校验。
- Modify: `tests/engine_inference.rs`
  - 覆盖 Rust native 编码和旧 one-hot 兼容。
- Create: `tests/test_native_categorical_parity.py`
  - 生成极小 native categorical LightGBM 模型和样本，导出 fixture，供 Rust parity 测试使用。
- Modify: `tests/engine_inference.rs`
  - 追加读取 parity fixture 的 Rust 预测一致性测试。
- Modify: `docs/model.md`
  - 记录新 metadata contract 和发布兼容策略。

## Metadata Contract

旧模型无需变更，缺省等价：

```json
{
  "categorical_encoding": "one_hot"
}
```

新 native categorical 模型必须写入：

```json
{
  "categorical_encoding": "native",
  "numeric_columns": ["close_to_ma25_pct"],
  "categorical_columns": ["env"],
  "categorical_levels": {
    "env": ["weak", "neutral", "strong"]
  },
  "categorical_code_maps": {
    "env": {
      "weak": 0,
      "neutral": 1,
      "strong": 2
    }
  },
  "feature_names": ["close_to_ma25_pct", "env"],
  "lightgbm_feature_names": ["close_to_ma25_pct", "env"]
}
```

规则：

- one-hot 模式：保持当前行为，`feature_names = numeric + column=level...`。
- native 模式：`feature_names = numeric + categorical_columns`。
- native 模式未知/缺失分类值编码为 `-1.0`，依赖 LightGBM 将负 categorical 值视作 missing。
- native 模式编码表按 `categorical_levels` 顺序生成，从 `0` 递增。
- `categorical_columns` 顺序必须参与 feature order，Rust 和 Python 必须一致。

## Task 1: Python 分类编码模式与矩阵构造

**Files:**
- Modify: `scripts/ml/train_rank_lgbm.py`
- Test: `tests/test_rank_lgbm.py`

- [ ] **Step 1: 写失败测试：native categorical 矩阵不 one-hot**

在 `tests/test_rank_lgbm.py` 中现有 `test_build_feature_matrix_one_hot_encodes_categoricals` 后添加：

```python
    def test_build_feature_matrix_native_encodes_categoricals_as_codes(self):
        rows = [
            {"date": "2026-01-01", "env": "weak", "signal_type": "rebound", "close_to_zxdkx_pct": "1.5"},
            {"date": "2026-01-01", "env": "strong", "signal_type": "trend_start", "close_to_zxdkx_pct": ""},
            {"date": "2026-01-01", "env": "missing_level", "signal_type": "", "close_to_zxdkx_pct": "2.5"},
        ]

        matrix, feature_names, code_maps = build_feature_matrix(
            rows,
            numeric_columns=["close_to_zxdkx_pct"],
            categorical_columns=["env", "signal_type"],
            levels={"env": ["weak", "strong"], "signal_type": ["rebound", "trend_start"]},
            categorical_encoding="native",
        )

        self.assertEqual(feature_names, ["close_to_zxdkx_pct", "env", "signal_type"])
        self.assertEqual(code_maps, {"env": {"weak": 0, "strong": 1}, "signal_type": {"rebound": 0, "trend_start": 1}})
        self.assertEqual(matrix[0], [1.5, 0.0, 0.0])
        self.assertEqual(matrix[1], [0.0, 1.0, 1.0])
        self.assertEqual(matrix[2], [2.5, -1.0, -1.0])
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_build_feature_matrix_native_encodes_categoricals_as_codes
```

Expected: FAIL，报 `build_feature_matrix()` 不接受 `categorical_encoding` 或返回值数量不匹配。

- [ ] **Step 3: 实现分类编码枚举与 native 矩阵**

在 `scripts/ml/train_rank_lgbm.py` 顶部常量区新增：

```python
CATEGORICAL_ENCODINGS = {"one_hot", "native"}
DEFAULT_CATEGORICAL_ENCODING = "one_hot"
```

新增函数：

```python
def categorical_code_maps(levels: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    return {
        column: {str(level): index for index, level in enumerate(values)}
        for column, values in levels.items()
    }
```

修改 `build_feature_matrix()` 签名和实现：

```python
def build_feature_matrix(
    rows: Sequence[dict[str, Any]],
    *,
    numeric_columns: Sequence[str],
    categorical_columns: Sequence[str],
    levels: dict[str, list[str]] | None = None,
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
) -> tuple[list[list[float]], list[str], dict[str, dict[str, int]]]:
    if categorical_encoding not in CATEGORICAL_ENCODINGS:
        raise ValueError(f"unsupported categorical_encoding: {categorical_encoding}")
    levels = levels or category_levels(rows, categorical_columns)
    code_maps = categorical_code_maps(levels)
    feature_names = list(numeric_columns)
    if categorical_encoding == "one_hot":
        for column in categorical_columns:
            feature_names.extend(f"{column}={value}" for value in levels.get(column, []))
    else:
        feature_names.extend(categorical_columns)

    matrix: list[list[float]] = []
    for row in rows:
        values = [as_float(row.get(column)) or 0.0 for column in numeric_columns]
        for column in categorical_columns:
            current = str(row.get(column) or "unknown")
            if categorical_encoding == "one_hot":
                values.extend(1.0 if current == value else 0.0 for value in levels.get(column, []))
            else:
                values.append(float(code_maps.get(column, {}).get(current, -1)))
        matrix.append(values)
    return matrix, feature_names, code_maps
```

更新所有调用点：

```python
matrix, feature_names, _code_maps = build_feature_matrix(...)
```

旧测试中只需要矩阵和 feature names 的地方改为：

```python
matrix, feature_names, _code_maps = build_feature_matrix(...)
```

- [ ] **Step 4: 运行相关测试确认通过**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_build_feature_matrix_one_hot_encodes_categoricals tests.test_rank_lgbm.RankLgbmTest.test_build_feature_matrix_native_encodes_categoricals_as_codes
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: add native categorical matrix encoding"
```

## Task 2: Metadata 写入和重建支持 native

**Files:**
- Modify: `scripts/ml/train_rank_lgbm.py`
- Test: `tests/test_rank_lgbm.py`

- [ ] **Step 1: 写失败测试：metadata native 重建矩阵**

在 `tests/test_rank_lgbm.py` 的 metadata 测试附近添加：

```python
    def test_model_metadata_rebuilds_native_categorical_matrix(self):
        rows = [
            {"date": "2026-01-03", "env": "neutral", "close_to_zxdkx_pct": ""},
            {"date": "2026-01-03", "env": "weak", "close_to_zxdkx_pct": "3.5"},
            {"date": "2026-01-03", "env": "unseen", "close_to_zxdkx_pct": "1.0"},
        ]
        metadata = {
            "numeric_columns": ["close_to_zxdkx_pct"],
            "categorical_columns": ["env"],
            "categorical_levels": {"env": ["weak", "neutral", "strong"]},
            "categorical_code_maps": {"env": {"weak": 0, "neutral": 1, "strong": 2}},
            "categorical_encoding": "native",
            "feature_names": ["close_to_zxdkx_pct", "env"],
        }

        matrix, rebuilt_names, code_maps = build_feature_matrix_from_metadata(rows, metadata)

        self.assertEqual(rebuilt_names, ["close_to_zxdkx_pct", "env"])
        self.assertEqual(code_maps, {"env": {"weak": 0, "neutral": 1, "strong": 2}})
        self.assertEqual(matrix, [[0.0, 1.0], [3.5, 0.0], [1.0, -1.0]])
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_model_metadata_rebuilds_native_categorical_matrix
```

Expected: FAIL，当前 `build_feature_matrix_from_metadata()` 没有 native 协议。

- [ ] **Step 3: 实现 metadata 编码字段**

修改 `build_feature_matrix_from_metadata()`：

```python
def build_feature_matrix_from_metadata(
    rows: Sequence[dict[str, Any]],
    metadata: dict[str, Any],
) -> tuple[list[list[float]], list[str], dict[str, dict[str, int]]]:
    numeric_columns = [str(value) for value in metadata.get("numeric_columns") or []]
    categorical_columns = [str(value) for value in metadata.get("categorical_columns") or []]
    levels = {
        str(column): [str(value) for value in values]
        for column, values in (metadata.get("categorical_levels") or {}).items()
        if isinstance(values, list)
    }
    categorical_encoding = str(metadata.get("categorical_encoding") or DEFAULT_CATEGORICAL_ENCODING)
    return build_feature_matrix(
        rows,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        levels=levels,
        categorical_encoding=categorical_encoding,
    )
```

修改 `build_model_metadata()` 签名，新增：

```python
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
    categorical_code_maps: dict[str, dict[str, int]] | None = None,
```

在 metadata payload 里新增：

```python
        "categorical_encoding": categorical_encoding,
        "categorical_code_maps": categorical_code_maps or {},
```

- [ ] **Step 4: 更新旧 one-hot metadata 测试**

现有 `test_model_metadata_rebuilds_feature_matrix_with_training_levels` 改为接收三元组：

```python
expected_matrix, feature_names, _code_maps = build_feature_matrix(...)
matrix, rebuilt_names, _rebuilt_code_maps = build_feature_matrix_from_metadata(score_rows, metadata)
```

并断言：

```python
self.assertEqual(metadata["categorical_encoding"], "one_hot")
```

- [ ] **Step 5: 运行 metadata 测试**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_model_metadata_rebuilds_feature_matrix_with_training_levels tests.test_rank_lgbm.RankLgbmTest.test_model_metadata_rebuilds_native_categorical_matrix
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: persist categorical encoding metadata"
```

## Task 3: Python 训练使用 LightGBM native categorical

**Files:**
- Modify: `scripts/ml/train_rank_lgbm.py`
- Test: `tests/test_rank_lgbm.py`

- [ ] **Step 1: 写失败测试：native 模式传 categorical_feature**

在 `tests/test_rank_lgbm.py` 中训练 fake lightgbm 的测试附近新增：

```python
    def test_train_model_result_passes_native_categorical_features_to_lightgbm(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "6", "x": "1", "env": "weak"},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "-1", "x": "0", "env": "strong"},
            {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "5", "ret5": "5", "x": "2", "env": "weak"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "0", "ret5": "0", "x": "0", "env": "strong"},
        ]
        captured = {}

        class DummyDataset:
            def __init__(self, matrix, **kwargs):
                captured["dataset_matrix"] = matrix
                captured["dataset_kwargs"] = kwargs

        class DummyModel:
            def predict(self, matrix):
                return [float(row[0] + row[1]) for row in matrix]

            def feature_importance(self):
                return [1, 1]

            def save_model(self, path):
                pathlib.Path(path).write_text("tree\n", encoding="utf-8")

        def fake_train(params, dataset, num_boost_round):
            captured["params"] = params
            captured["num_boost_round"] = num_boost_round
            return DummyModel()

        fake_lightgbm = types.SimpleNamespace(Dataset=DummyDataset, train=fake_train)
        fake_numpy = types.SimpleNamespace(array=lambda values, dtype=None: values)
        with patch.dict(sys.modules, {"lightgbm": fake_lightgbm, "numpy": fake_numpy}):
            result = train_model_result(
                rows[:2],
                rows[2:],
                numeric_columns=["x"],
                categorical_columns=["env"],
                num_leaves=5,
                min_data_in_leaf=1,
                num_boost_round=3,
                learning_rate=0.1,
                label_column="rank_label_3d",
                num_threads=1,
                fixed_categorical_levels={"env": ["weak", "strong"]},
                categorical_encoding="native",
            )

        self.assertEqual(captured["dataset_kwargs"]["categorical_feature"], ["env"])
        self.assertEqual(result.feature_names, ["x", "env"])
        self.assertEqual(result.category_levels, {"env": ["weak", "strong"]})
        self.assertEqual(result.categorical_code_maps, {"env": {"weak": 0, "strong": 1}})
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_train_model_result_passes_native_categorical_features_to_lightgbm
```

Expected: FAIL，`train_model_result()` 不接受 `categorical_encoding`，`TrainedModelResult` 没有 `categorical_code_maps`。

- [ ] **Step 3: 扩展 TrainedModelResult 和 train_model_result**

修改 dataclass：

```python
@dataclass
class TrainedModelResult:
    train_scored: list[dict[str, Any]]
    test_scored: list[dict[str, Any]]
    top_features: list[dict[str, Any]]
    feature_count: int
    model: Any
    feature_names: list[str]
    lightgbm_feature_names: list[str]
    category_levels: dict[str, list[str]]
    categorical_code_maps: dict[str, dict[str, int]]
```

修改空结果返回：

```python
return TrainedModelResult([], [], [], 0, None, [], [], {}, {})
```

修改 `train_model_result()` 参数新增：

```python
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
```

调用矩阵构造：

```python
train_matrix, feature_names, code_maps = build_feature_matrix(
    train_rows,
    numeric_columns=numeric_columns,
    categorical_columns=categorical_columns,
    levels=levels,
    categorical_encoding=categorical_encoding,
)
test_matrix, _feature_names, _test_code_maps = build_feature_matrix(
    test_rows,
    numeric_columns=numeric_columns,
    categorical_columns=categorical_columns,
    levels=levels,
    categorical_encoding=categorical_encoding,
)
```

构建 Dataset：

```python
dataset_kwargs = {
    "label": np.array(labels(train_rows, label_column=label_column), dtype=int),
    "group": group_sizes_by_date(train_rows),
    "feature_name": lightgbm_feature_names,
    "free_raw_data": False,
}
if categorical_encoding == "native" and categorical_columns:
    dataset_kwargs["categorical_feature"] = [safe_feature_names([column])[0] for column in categorical_columns]
train_dataset = lgb.Dataset(train_array, **dataset_kwargs)
```

返回结果带 `categorical_code_maps=code_maps`。

- [ ] **Step 4: 更新 build_model_metadata 调用**

在 `train_and_report()` 中调用 `build_model_metadata()` 时传入：

```python
categorical_encoding=categorical_encoding,
categorical_code_maps=model_result.categorical_code_maps,
```

这里 `categorical_encoding` 来自 Task 4 的 CLI 参数；Task 3 可先在函数默认参数中保持 one-hot，调用点先传默认值。

- [ ] **Step 5: 运行训练相关测试**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_train_model_result_passes_native_categorical_features_to_lightgbm tests.test_rank_lgbm.RankLgbmTest.test_train_model_result_uses_lightgbm
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: train native categorical lightgbm models"
```

## Task 4: CLI 参数、report 和 feature manifest 支持编码模式

**Files:**
- Modify: `scripts/ml/train_rank_lgbm.py`
- Test: `tests/test_rank_lgbm.py`

- [ ] **Step 1: 写失败测试：train_and_report 写出 native metadata**

在 `tests/test_rank_lgbm.py` 中添加：

```python
    def test_train_and_report_writes_native_categorical_metadata(self):
        rows = [
            {"date": "2026-01-01", "code": "a", "rank_label_3d": "3", "ret3": "6", "ret5": "6", "close_to_zxdkx_pct": "1", "env": "weak"},
            {"date": "2026-01-01", "code": "b", "rank_label_3d": "0", "ret3": "-1", "ret5": "-1", "close_to_zxdkx_pct": "0", "env": "strong"},
            {"date": "2026-01-02", "code": "a", "rank_label_3d": "3", "ret3": "5", "ret5": "5", "close_to_zxdkx_pct": "2", "env": "weak"},
            {"date": "2026-01-02", "code": "b", "rank_label_3d": "0", "ret3": "0", "ret5": "0", "close_to_zxdkx_pct": "0", "env": "strong"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = pathlib.Path(temp_dir) / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            output_dir = pathlib.Path(temp_dir) / "model"

            with patch("scripts.ml.train_rank_lgbm.train_model_result") as train_model:
                train_model.return_value = TrainedModelResult(
                    train_scored=[],
                    test_scored=[{**rows[-1], "model_score": 1.0}],
                    top_features=[{"feature": "env", "importance": 1}],
                    feature_count=2,
                    model=FakeModel(),
                    feature_names=["close_to_zxdkx_pct", "env"],
                    lightgbm_feature_names=["close_to_zxdkx_pct", "env"],
                    category_levels={"env": ["weak", "strong"]},
                    categorical_code_maps={"env": {"weak": 0, "strong": 1}},
                )
                train_and_report(
                    dataset,
                    output_dir,
                    test_ratio=0.5,
                    feature_set="raw_plus_signal",
                    method="b3",
                    categorical_encoding="native",
                    num_leaves=5,
                    min_data_in_leaf=1,
                    num_boost_round=3,
                    learning_rate=0.1,
                    num_threads=1,
                    rf_diagnostics=False,
                )

            metadata = json.loads((output_dir / "model_metadata.json").read_text(encoding="utf-8"))
            report = json.loads(next(output_dir.glob("lgbm_rank_report*.json")).read_text(encoding="utf-8"))
            manifest = json.loads((output_dir / "feature_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["categorical_encoding"], "native")
            self.assertEqual(metadata["categorical_code_maps"], {"env": {"weak": 0, "strong": 1}})
            self.assertEqual(report["categorical_encoding"], "native")
            self.assertEqual(manifest["categorical_encoding"], "native")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_train_and_report_writes_native_categorical_metadata
```

Expected: FAIL，`train_and_report()` 不接受 `categorical_encoding`。

- [ ] **Step 3: 实现 CLI 参数和 manifest 字段**

修改 `write_feature_manifest()` 签名新增：

```python
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
```

payload 增加：

```python
"categorical_encoding": categorical_encoding,
```

修改 `load_feature_manifest_with_levels()` 返回值增加 encoding：

```python
) -> tuple[list[str], list[str], dict[str, list[str]], str]:
```

解析：

```python
encoding = str(payload.get("categorical_encoding") or DEFAULT_CATEGORICAL_ENCODING)
if encoding not in CATEGORICAL_ENCODINGS:
    raise ValueError(f"unsupported categorical_encoding in feature manifest: {encoding}")
return numeric, categorical, fixed_levels, encoding
```

同步调整 `load_feature_manifest()` 只返回前两个字段。

修改 `train_and_report()` 参数新增：

```python
    categorical_encoding: str = DEFAULT_CATEGORICAL_ENCODING,
```

当传入 feature_manifest 时，用 manifest encoding 覆盖 CLI 默认：

```python
numeric_columns, categorical_columns, fixed_categorical_levels, manifest_encoding = load_feature_manifest_with_levels(...)
categorical_encoding = manifest_encoding
```

当没有 manifest 时，`write_feature_manifest()` 写入 CLI encoding。

报告 payload 增加：

```python
"categorical_encoding": categorical_encoding,
```

parser 增加：

```python
parser.add_argument("--categorical-encoding", choices=sorted(CATEGORICAL_ENCODINGS), default=DEFAULT_CATEGORICAL_ENCODING)
```

main 调用传入 `categorical_encoding=args.categorical_encoding`。

- [ ] **Step 4: 运行相关测试**

Run:

```bash
python -m unittest tests.test_rank_lgbm.RankLgbmTest.test_train_and_report_writes_native_categorical_metadata tests.test_rank_lgbm.RankLgbmTest.test_train_report_uses_fixed_categorical_levels_from_feature_manifest
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/ml/train_rank_lgbm.py tests/test_rank_lgbm.py
git commit -m "feat: expose categorical encoding in training metadata"
```

## Task 5: export_lgbm_scores 继承 native encoding

**Files:**
- Modify: `scripts/ml/export_lgbm_scores.py`
- Test: `tests/test_lgbm_score_export.py`

- [ ] **Step 1: 写失败测试：export 传递 native encoding**

在 `tests/test_lgbm_score_export.py` 中新增：

```python
    def test_export_scores_preserves_native_categorical_encoding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            dataset = root / "dataset.csv"
            with dataset.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "code", "rank_label_3d", "close_to_zxdkx_pct", "env"])
                writer.writeheader()
                writer.writerows([
                    {"date": "2026-01-01", "code": "a", "rank_label_3d": "1", "close_to_zxdkx_pct": "1", "env": "weak"},
                    {"date": "2026-03-01", "code": "b", "rank_label_3d": "2", "close_to_zxdkx_pct": "2", "env": "strong"},
                ])
            feature_manifest = root / "feature_manifest.json"
            feature_manifest.write_text(json.dumps({
                "numeric_features": ["close_to_zxdkx_pct"],
                "categorical_features": ["env"],
                "categorical_levels": {"env": ["weak", "strong"]},
                "categorical_encoding": "native",
            }), encoding="utf-8")
            artifact_dir = root / "model"

            with patch("scripts.ml.export_lgbm_scores.train_model_result") as train_model_result:
                train_model_result.return_value = type("Result", (), {
                    "train_scored": [],
                    "test_scored": [{"date": "2026-03-01", "code": "b", "model_score": 0.5}],
                    "top_features": [{"feature": "env", "importance": 1}],
                    "feature_count": 2,
                    "model": FakeModel(),
                    "feature_names": ["close_to_zxdkx_pct", "env"],
                    "lightgbm_feature_names": ["close_to_zxdkx_pct", "env"],
                    "category_levels": {"env": ["weak", "strong"]},
                    "categorical_code_maps": {"env": {"weak": 0, "strong": 1}},
                })()
                export_scores(
                    dataset=dataset,
                    feature_manifest=feature_manifest,
                    output=root / "scores.csv",
                    summary_output=root / "summary.json",
                    model_output_dir=artifact_dir,
                    train_end_exclusive="2026-03-01",
                    score_start="2026-03-01",
                    score_end="2026-03-31",
                    num_leaves=9,
                    min_data_in_leaf=120,
                    num_boost_round=60,
                    learning_rate=0.05,
                    num_threads=1,
                    label_column="rank_label_3d",
                )

            metadata = json.loads((artifact_dir / "model_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(train_model_result.call_args.kwargs["categorical_encoding"], "native")
            self.assertEqual(metadata["categorical_encoding"], "native")
            self.assertEqual(metadata["categorical_code_maps"], {"env": {"weak": 0, "strong": 1}})
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest tests.test_lgbm_score_export.LgbmScoreExportTest.test_export_scores_preserves_native_categorical_encoding
```

Expected: FAIL，export 未传递 categorical_encoding。

- [ ] **Step 3: 修改 export 读取 manifest encoding**

在 `scripts/ml/export_lgbm_scores.py` 中调整 import：

```python
from scripts.ml.train_rank_lgbm import (
    DEFAULT_LABEL_GAIN,
    DEFAULT_CATEGORICAL_ENCODING,
    ...
)
```

调用 `load_feature_manifest_with_levels()` 改为接收四元组：

```python
numeric_columns, categorical_columns, fixed_categorical_levels, categorical_encoding = load_feature_manifest_with_levels(...)
```

传给 `train_model_result()`：

```python
categorical_encoding=categorical_encoding,
```

传给 `build_model_metadata()`：

```python
categorical_encoding=categorical_encoding,
categorical_code_maps=model_result.categorical_code_maps,
```

summary 增加：

```python
"categorical_encoding": categorical_encoding,
```

- [ ] **Step 4: 运行 export 测试**

Run:

```bash
python -m unittest tests.test_lgbm_score_export.LgbmScoreExportTest.test_export_scores_preserves_native_categorical_encoding tests.test_lgbm_score_export.LgbmScoreExportTest.test_export_scores_uses_feature_manifest_from_model_output_dir
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/ml/export_lgbm_scores.py tests/test_lgbm_score_export.py
git commit -m "feat: export native categorical model artifacts"
```

## Task 6: Rust runtime 支持 native categorical

**Files:**
- Modify: `src/engine/inference.rs`
- Test: `tests/engine_inference.rs`

- [ ] **Step 1: 写失败测试：native metadata 生成整数 code**

在 `tests/engine_inference.rs` 中 one-hot 特征测试后添加：

```rust
#[test]
fn feature_vector_supports_native_categorical_encoding() {
    let metadata = ModelFeatureMetadata {
        numeric_columns: vec!["close_to_zxdkx_pct".to_string()],
        categorical_columns: vec!["env".to_string()],
        categorical_levels: BTreeMap::from([(
            "env".to_string(),
            vec!["weak".to_string(), "neutral".to_string(), "strong".to_string()],
        )]),
        categorical_code_maps: BTreeMap::from([(
            "env".to_string(),
            BTreeMap::from([
                ("weak".to_string(), 0),
                ("neutral".to_string(), 1),
                ("strong".to_string(), 2),
            ]),
        )]),
        categorical_encoding: "native".to_string(),
        feature_names: vec!["close_to_zxdkx_pct".to_string(), "env".to_string()],
    };
    let mut row = FactorRow::new("000001.SZ", Method::B3);
    row.factors
        .insert("close_to_zxdkx_pct".to_string(), FactorValue::Number(1.5));
    row.factors
        .insert("env".to_string(), FactorValue::Category("neutral".to_string()));

    let vector = build_feature_vector(&row, &metadata).unwrap();

    assert_eq!(vector.feature_names, metadata.feature_names);
    assert_eq!(vector.values, vec![1.5, 1.0]);
    assert!(vector.missing_numeric_features.is_empty());
}

#[test]
fn feature_vector_native_categorical_unknown_maps_to_missing_code() {
    let metadata = ModelFeatureMetadata {
        numeric_columns: vec!["close_to_zxdkx_pct".to_string()],
        categorical_columns: vec!["env".to_string()],
        categorical_levels: BTreeMap::from([("env".to_string(), vec!["weak".to_string()])]),
        categorical_code_maps: BTreeMap::from([(
            "env".to_string(),
            BTreeMap::from([("weak".to_string(), 0)]),
        )]),
        categorical_encoding: "native".to_string(),
        feature_names: vec!["close_to_zxdkx_pct".to_string(), "env".to_string()],
    };
    let mut row = FactorRow::new("000001.SZ", Method::B3);
    row.factors
        .insert("env".to_string(), FactorValue::Category("unseen".to_string()));

    let vector = build_feature_vector(&row, &metadata).unwrap();

    assert_eq!(vector.values, vec![0.0, -1.0]);
    assert_eq!(vector.missing_numeric_features, vec!["close_to_zxdkx_pct"]);
}
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cargo test --test engine_inference feature_vector_supports_native_categorical_encoding feature_vector_native_categorical_unknown_maps_to_missing_code -- --nocapture
```

Expected: FAIL，`ModelFeatureMetadata` 缺字段。

- [ ] **Step 3: 实现 Rust metadata 字段和分支**

在 `src/engine/inference.rs` 修改 struct：

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelFeatureMetadata {
    #[serde(default)]
    pub numeric_columns: Vec<String>,
    #[serde(default)]
    pub categorical_columns: Vec<String>,
    #[serde(default)]
    pub categorical_levels: BTreeMap<String, Vec<String>>,
    #[serde(default)]
    pub categorical_code_maps: BTreeMap<String, BTreeMap<String, i32>>,
    #[serde(default = "default_categorical_encoding")]
    pub categorical_encoding: String,
    #[serde(default)]
    pub feature_names: Vec<String>,
}

fn default_categorical_encoding() -> String {
    "one_hot".to_string()
}
```

在 `build_feature_vector()` 中分类处理前加入：

```rust
let categorical_encoding = metadata.categorical_encoding.as_str();
if categorical_encoding != "one_hot" && categorical_encoding != "native" {
    anyhow::bail!("unsupported categorical_encoding: {categorical_encoding}");
}
```

替换分类循环：

```rust
for column in &metadata.categorical_columns {
    let current = match row.factors.get(column) {
        Some(FactorValue::Category(value)) => value.as_str(),
        Some(FactorValue::Bool(true)) => "true",
        Some(FactorValue::Bool(false)) => "false",
        _ => "unknown",
    };

    if categorical_encoding == "native" {
        feature_names.push(column.clone());
        let code = metadata
            .categorical_code_maps
            .get(column)
            .and_then(|values| values.get(current))
            .copied()
            .unwrap_or(-1);
        values.push(code as f64);
    } else {
        for level in metadata
            .categorical_levels
            .get(column)
            .cloned()
            .unwrap_or_default()
        {
            feature_names.push(format!("{column}={level}"));
            values.push(if current == level { 1.0 } else { 0.0 });
        }
    }
}
```

更新现有 one-hot 测试初始化，补：

```rust
categorical_code_maps: BTreeMap::new(),
categorical_encoding: "one_hot".to_string(),
```

- [ ] **Step 4: 运行 Rust inference 测试**

Run:

```bash
cargo test --test engine_inference -- --nocapture
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/engine/inference.rs tests/engine_inference.rs
git commit -m "feat: support native categorical runtime vectors"
```

## Task 7: 发布校验支持 native metadata

**Files:**
- Modify: `scripts/ml/promote_lgbm_model.py`
- Test: `tests/test_lgbm_model_promotion.py`

- [ ] **Step 1: 写失败测试：native metadata 缺 code map 不能发布**

在 `tests/test_lgbm_model_promotion.py` 中新增：

```python
    def test_validate_model_artifacts_rejects_native_categorical_without_code_maps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "candidate"
            candidate.mkdir()
            (candidate / "model.txt").write_text("tree\n", encoding="utf-8")
            metadata = {
                "feature_names": ["x", "env"],
                "numeric_columns": ["x"],
                "categorical_columns": ["env"],
                "categorical_levels": {"env": ["weak", "strong"]},
                "categorical_encoding": "native",
                "label_column": "rank_label_3d",
                "train_start": "2026-01-01",
                "train_end": "2026-01-31",
                "score_start": "2026-02-01",
                "score_end": "2026-02-28",
                "model_params": {"num_leaves": 5},
            }
            (candidate / "model_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "categorical_code_maps"):
                validate_model_artifacts(candidate)
```

- [ ] **Step 2: 写通过测试：native metadata 完整可发布**

```python
    def test_validate_model_artifacts_accepts_native_categorical_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "candidate"
            candidate.mkdir()
            (candidate / "model.txt").write_text("tree\n", encoding="utf-8")
            metadata = {
                "feature_names": ["x", "env"],
                "numeric_columns": ["x"],
                "categorical_columns": ["env"],
                "categorical_levels": {"env": ["weak", "strong"]},
                "categorical_code_maps": {"env": {"weak": 0, "strong": 1}},
                "categorical_encoding": "native",
                "label_column": "rank_label_3d",
                "train_start": "2026-01-01",
                "train_end": "2026-01-31",
                "score_start": "2026-02-01",
                "score_end": "2026-02-28",
                "model_params": {"num_leaves": 5},
            }
            (candidate / "model_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

            summary = validate_model_artifacts(candidate)

            self.assertEqual(summary["feature_count"], 2)
            self.assertEqual(summary["categorical_encoding"], "native")
```

- [ ] **Step 3: 运行测试确认至少第一个失败**

Run:

```bash
python -m unittest tests.test_lgbm_model_promotion.LgbmModelPromotionTest.test_validate_model_artifacts_rejects_native_categorical_without_code_maps tests.test_lgbm_model_promotion.LgbmModelPromotionTest.test_validate_model_artifacts_accepts_native_categorical_metadata
```

Expected: FAIL，当前校验不理解 native code map。

- [ ] **Step 4: 实现校验**

在 `validate_metadata()` 中读取：

```python
categorical_encoding = str(metadata.get("categorical_encoding") or "one_hot")
if categorical_encoding not in {"one_hot", "native"}:
    raise ValueError("model_metadata.json categorical_encoding 必须是 one_hot 或 native")
```

如果 native：

```python
code_maps = metadata.get("categorical_code_maps")
if not isinstance(code_maps, dict):
    raise ValueError("model_metadata.json categorical_code_maps 是 native 分类模型必需字段")
for column in categorical_columns:
    levels = categorical_levels.get(column)
    mapping = code_maps.get(column)
    if not isinstance(mapping, dict):
        raise ValueError(f"model_metadata.json categorical_code_maps.{column} 必须是对象")
    expected = {str(level): index for index, level in enumerate(levels)}
    actual = {str(key): value for key, value in mapping.items()}
    if actual != expected:
        raise ValueError(f"model_metadata.json categorical_code_maps.{column} 必须与 categorical_levels 顺序一致")
expected_feature_names = list(numeric_columns) + list(categorical_columns)
if feature_names != expected_feature_names:
    raise ValueError("native categorical model feature_names 必须等于 numeric_columns + categorical_columns")
```

返回 summary 增加：

```python
"categorical_encoding": categorical_encoding,
```

- [ ] **Step 5: 运行 promotion 测试**

Run:

```bash
python -m unittest tests.test_lgbm_model_promotion
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add scripts/ml/promote_lgbm_model.py tests/test_lgbm_model_promotion.py
git commit -m "feat: validate native categorical model metadata"
```

## Task 8: Python/Rust native categorical 预测一致性 fixture

**Files:**
- Create: `tests/test_native_categorical_parity.py`
- Modify: `tests/engine_inference.rs`

- [ ] **Step 1: 写 Python parity 生成测试**

创建 `tests/test_native_categorical_parity.py`：

```python
import json
import tempfile
import unittest
from pathlib import Path

import lightgbm as lgb
import numpy as np

from scripts.ml.train_rank_lgbm import build_model_metadata, write_model_artifacts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "native_categorical_model"


class NativeCategoricalParityTest(unittest.TestCase):
    def test_generate_native_categorical_fixture(self):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        train_matrix = np.array(
            [
                [1.0, 0.0],
                [0.0, 1.0],
                [2.0, 0.0],
                [0.5, 1.0],
            ],
            dtype=float,
        )
        labels = np.array([3, 0, 3, 0], dtype=int)
        train = lgb.Dataset(
            train_matrix,
            label=labels,
            group=[2, 2],
            feature_name=["x", "env"],
            categorical_feature=["env"],
            free_raw_data=False,
        )
        model = lgb.train(
            {
                "objective": "lambdarank",
                "metric": "ndcg",
                "learning_rate": 0.1,
                "num_leaves": 3,
                "min_data_in_leaf": 1,
                "label_gain": [0, 1, 3, 7],
                "seed": 17,
                "verbosity": -1,
                "num_threads": 1,
            },
            train,
            num_boost_round=5,
        )
        score_rows = [
            {"date": "2026-01-03", "x": "1.5", "env": "weak"},
            {"date": "2026-01-03", "x": "1.5", "env": "strong"},
            {"date": "2026-01-03", "x": "1.5", "env": "unknown"},
        ]
        encoded = np.array([[1.5, 0.0], [1.5, 1.0], [1.5, -1.0]], dtype=float)
        predictions = [float(value) for value in model.predict(encoded)]
        metadata = build_model_metadata(
            feature_manifest=None,
            train_rows=[{"date": "2026-01-01"}, {"date": "2026-01-02"}],
            score_rows=score_rows,
            numeric_columns=["x"],
            categorical_columns=["env"],
            levels={"env": ["weak", "strong"]},
            feature_names=["x", "env"],
            lightgbm_feature_names=["x", "env"],
            label_column="rank_label_3d",
            model_params={"num_leaves": 3, "min_data_in_leaf": 1},
            categorical_encoding="native",
            categorical_code_maps={"env": {"weak": 0, "strong": 1}},
        )
        write_model_artifacts(model, metadata, FIXTURE_DIR)
        (FIXTURE_DIR / "expected_predictions.json").write_text(
            json.dumps(
                {
                    "rows": [
                        {"x": 1.5, "env": "weak", "prediction": predictions[0]},
                        {"x": 1.5, "env": "strong", "prediction": predictions[1]},
                        {"x": 1.5, "env": "unknown", "prediction": predictions[2]},
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        self.assertTrue((FIXTURE_DIR / "model.txt").exists())
        self.assertTrue((FIXTURE_DIR / "model_metadata.json").exists())
        self.assertTrue((FIXTURE_DIR / "expected_predictions.json").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行生成 fixture**

Run:

```bash
uv run --with lightgbm python -m unittest tests.test_native_categorical_parity
```

Expected: PASS，并生成：

- `tests/fixtures/native_categorical_model/model.txt`
- `tests/fixtures/native_categorical_model/model_metadata.json`
- `tests/fixtures/native_categorical_model/expected_predictions.json`

- [ ] **Step 3: 写 Rust parity 测试**

在 `tests/engine_inference.rs` 添加 imports：

```rust
use serde::Deserialize;
```

添加测试：

```rust
#[derive(Debug, Deserialize)]
struct ExpectedNativePredictions {
    rows: Vec<ExpectedNativePrediction>,
}

#[derive(Debug, Deserialize)]
struct ExpectedNativePrediction {
    x: f64,
    env: String,
    prediction: f64,
}

#[test]
fn lightgbm_runtime_matches_python_native_categorical_predictions() {
    let fixture = std::path::Path::new("tests/fixtures/native_categorical_model");
    let metadata: ModelFeatureMetadata =
        serde_json::from_slice(&std::fs::read(fixture.join("model_metadata.json")).unwrap())
            .unwrap();
    let expected: ExpectedNativePredictions =
        serde_json::from_slice(&std::fs::read(fixture.join("expected_predictions.json")).unwrap())
            .unwrap();
    let model = LightGbmRuntimeModel::from_file(fixture.join("model.txt").to_str().unwrap()).unwrap();

    for expected_row in expected.rows {
        let mut row = FactorRow::new("000001.SZ", Method::B3);
        row.factors
            .insert("x".to_string(), FactorValue::Number(expected_row.x));
        row.factors
            .insert("env".to_string(), FactorValue::Category(expected_row.env));
        let vector = build_feature_vector(&row, &metadata).unwrap();
        let actual = model.predict(&vector.values).unwrap();
        assert!(
            (actual - expected_row.prediction).abs() < 1e-10,
            "actual={actual} expected={}",
            expected_row.prediction
        );
    }
}
```

- [ ] **Step 4: 运行 Rust parity 测试**

Run:

```bash
cargo test --test engine_inference lightgbm_runtime_matches_python_native_categorical_predictions -- --nocapture
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add tests/test_native_categorical_parity.py tests/fixtures/native_categorical_model tests/engine_inference.rs
git commit -m "test: verify rust native categorical prediction parity"
```

## Task 9: 文档更新

**Files:**
- Modify: `docs/model.md`
- Modify: `.agents/skills/model-maintenance/references/model-maintenance.md`

- [ ] **Step 1: 更新 `docs/model.md`**

新增一节：

```markdown
## LightGBM 分类特征编码

模型元数据通过 `categorical_encoding` 声明分类特征编码方式：

- `one_hot`：默认兼容模式。Rust runtime 将 `categorical_columns` 按 `categorical_levels` 展开为 `column=level` 的 0/1 特征。
- `native`：LightGBM 原生分类模式。Rust runtime 按 `categorical_code_maps` 将分类值编码为整数，未知或缺失值编码为 `-1`。

发布 native 模型必须包含：

- `categorical_encoding`
- `categorical_columns`
- `categorical_levels`
- `categorical_code_maps`
- `feature_names`

native 模型的 `feature_names` 必须等于 `numeric_columns + categorical_columns`。
```

- [ ] **Step 2: 更新 model-maintenance reference**

在 `.agents/skills/model-maintenance/references/model-maintenance.md` 的 Metadata Contract 增加：

```markdown
分类特征编码：

- 缺省 `categorical_encoding=one_hot`，保持旧模型兼容。
- `categorical_encoding=native` 时，`categorical_code_maps` 是必需字段，Rust runtime 用它把分类值映射成 LightGBM 原生分类整数 code。
- native 模型发布前必须跑 Python/Rust parity 测试。
```

- [ ] **Step 3: 提交**

```bash
git add docs/model.md .agents/skills/model-maintenance/references/model-maintenance.md
git commit -m "docs: describe lightgbm categorical encoding contract"
```

## Task 10: 集成验证和 b3 native 试训

**Files:**
- No code files expected.
- Output ignored diagnostics under `diagnostics/ml/b3/tuning/`.

- [ ] **Step 1: 运行 Python 单元测试**

Run:

```bash
python -m unittest tests/test_rank_lgbm.py tests/test_lgbm_score_export.py tests/test_lgbm_model_promotion.py tests/test_native_categorical_parity.py
```

Expected: PASS。

- [ ] **Step 2: 运行 Rust 相关测试**

Run:

```bash
cargo test --test engine_inference -- --nocapture
```

Expected: PASS。

- [ ] **Step 3: 编译检查**

Run:

```bash
python -m py_compile scripts/ml/train_rank_lgbm.py scripts/ml/export_lgbm_scores.py scripts/ml/promote_lgbm_model.py
cargo fmt --check
cargo test --quiet
```

Expected: 全部 PASS。若 `cargo test --quiet` 因既有测试耗时或外部依赖失败，记录失败测试名和错误，不要掩盖。

- [ ] **Step 4: b3 native 小网格试训**

在用户确认可用核心数后执行。若用户仍要求 8 核，使用 `--num-threads 8`。

Run:

```bash
BATCH=diagnostics/ml/b3/tuning/native-categorical-$(date +%Y%m%dT%H%M%S)
uv run scripts/ml/train_rank_lgbm.py \
  --method b3 \
  --dataset diagnostics/ml/b3/rank_dataset.csv \
  --output-dir "$BATCH/trial-001" \
  --feature-set raw_plus_signal_macd \
  --categorical-encoding native \
  --label-column rank_label_3d \
  --num-leaves 5 \
  --min-data-in-leaf 60 \
  --num-boost-round 60 \
  --learning-rate 0.05 \
  --num-threads 8 \
  --rolling-folds 5 \
  --rolling-train-dates 160 \
  --rolling-test-dates 16
```

Expected:

- report 包含 `"categorical_encoding": "native"`。
- `model_metadata.json` 包含 `categorical_code_maps`。
- rolling 指标可读。

- [ ] **Step 5: 导出并 dry-run promote**

Run:

```bash
uv run scripts/ml/export_lgbm_scores.py \
  --method b3 \
  --model-output-dir "$BATCH/trial-001"

uv run scripts/ml/promote_lgbm_model.py \
  --method b3 \
  --candidate-dir "$BATCH/trial-001" \
  --dry-run \
  --require-report
```

Expected: dry-run PASS，不发布生产模型。

- [ ] **Step 6: 提交最终集成变更**

```bash
git status --short
git add scripts/ml/train_rank_lgbm.py scripts/ml/export_lgbm_scores.py scripts/ml/promote_lgbm_model.py src/engine/inference.rs tests/test_rank_lgbm.py tests/test_lgbm_score_export.py tests/test_lgbm_model_promotion.py tests/test_native_categorical_parity.py tests/fixtures/native_categorical_model tests/engine_inference.rs docs/model.md .agents/skills/model-maintenance/references/model-maintenance.md
git commit -m "feat: support native categorical lightgbm models"
```

## 实施顺序和风险控制

1. 先实现 Python 矩阵和 metadata，不碰 Rust runtime。
2. 再实现 Rust native vector，保持 one-hot 默认兼容。
3. 再做发布校验，防止坏 native metadata 上线。
4. 最后做 Python/Rust parity fixture，证明 LightGBM 原生分类预测一致。
5. native b3 只做试训和 dry-run，不自动发布。

## Self-Review

- Spec coverage: 覆盖了训练、导出、发布校验、Rust runtime、Python/Rust parity、文档和 b3 试训。
- Placeholder scan: 无 `TBD`、`TODO`、`implement later`。
- Type consistency: `categorical_encoding`、`categorical_code_maps`、`categorical_levels` 在 Python metadata、Rust struct、promotion 校验中名称一致。
- Compatibility: 缺省 `categorical_encoding=one_hot`，旧模型继续走现有 one-hot 路径。
