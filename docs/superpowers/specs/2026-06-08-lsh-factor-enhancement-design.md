# LSH 因子增强设计

## 目标

在 `lsh` 筛选方法已有候选逻辑基础上，新增一组 `lsh` 专属训练因子：MACD 状态机分析因子，以及“放量阳反包前一日阴线”相关因子。新增因子进入 `lsh` dataset 和 LightGBM 训练，不影响 b2/b3 现有因子 profile。

## 因子范围

### MACD 状态机因子

复用 `src/macd_trends.rs` 已实现的状态机：

- `classify_daily_macd_trend()`
- `classify_weekly_macd_trend()`
- `is_constructive_macd_trend_combo()`

新增因子命名使用 `lsh_` 前缀，避免与 b2/b3 语义列混淆：

- `lsh_daily_macd_wave_index`
- `lsh_weekly_macd_wave_index`
- `lsh_daily_macd_rising_initial_flag`
- `lsh_weekly_macd_rising_initial_flag`
- `lsh_daily_macd_top_divergence_flag`
- `lsh_weekly_macd_top_divergence_flag`
- `lsh_weekly_daily_constructive_combo_flag`

### 放量阳反包前阴线因子

定义：

- 前一日阴线：`prev_close < prev_open`
- 当日阳线：`close > open`
- 当日阳线实体反包前一日阴线实体：`open <= prev_close && close >= prev_open`
- 放量：`volume > prev_volume`

新增因子：

- `lsh_bullish_engulf_prev_bearish_flag`
- `lsh_volume_bullish_engulf_prev_bearish_flag`
- `lsh_bullish_engulf_volume_ratio`

其中 volume ratio 为 `volume / prev_volume`，前一日成交量缺失或为 0 时输出 missing。

## 接入方式

新增 `FactorBundle::LshSemantic` 和 `LSH_FACTOR_BUNDLES = [RawCommon, LshSemantic]`。`factor_profile_for_method(Method::Lsh)` 使用该 profile；其他 method 不变。

Python dataset schema 新增 `LSH_SPECIFIC_RAW_FACTOR_COLUMNS`，并注册：

```python
METHOD_RAW_FACTOR_COLUMNS = {
    "b2": RAW_FACTOR_COLUMNS,
    "b3": B3_RAW_FACTOR_COLUMNS,
    "lsh": LSH_RAW_FACTOR_COLUMNS,
}
```

训练仍默认使用 `--feature-set raw_numeric`，因此上述布尔因子会作为数值特征进入 LightGBM。

## 验证

- Rust：新增 factor profile 和 factor row 单测，验证 `lsh` 有新因子，b2/b3 不被污染。
- Python：新增 dataset schema 单测，验证 `lsh` schema 包含新因子且 b2 不包含。
- 全量验证：`cargo fmt --check && cargo test --quiet`，以及 ML 脚本单元测试。
- 数据流程：重跑 `lsh` factors、dataset、训练 trial、export scores、promote dry-run。
