# LSH 筛选方法设计

## 目标

将用户给出的条件选股公式接入当前 Rust CLI 体系，新增独立筛选方法 `lsh`，并支持后续按 `lsh` 生成候选、导出因子、构建训练数据集和训练 LightGBM 排序模型。

## 策略定义

`lsh` 在日线级别筛选候选，条件如下：

- 日线 MA25：`MA25 = MA(C, 25)`。
- 今日最低价低于 MA25：`L < MA25`。
- 今日收红：`C > O`。
- 今日收盘价高于 MA25：`C > MA25`。
- 月线 MACD：按自然月聚合日线收盘价，使用 MACD(12,26,9)，要求 `MACD` 柱值本身 `> 0`，且 `DEA > 0`。
- 周线 MACD：按 ISO 自然周聚合日线收盘价，使用 MACD(12,26,9)，要求 `MACD` 柱值本身 `> 0`，且 `DEA > 0`。

本仓库 `indicators::macd()` 的第三个返回值是 `DIF - DEA`。通达信常见展示会将 MACD 柱放大为 `2 * (DIF - DEA)`，但本策略只判断正负，缩放不影响结果。

## 接入方式

新增独立 `Method::Lsh`，命令行使用小写 `lsh`：

```bash
stock-select-rs screen --method lsh --pick-date 2026-06-08
```

候选产物按现有约定隔离：

- `runtime/candidates/<date>.lsh.json`
- `runtime/factors/<date>.lsh/factors.json`
- `diagnostics/ml/lsh/rank_dataset.csv`
- `diagnostics/ml/lsh/model/`

候选行 `signal` 写为 `LSH`。筛选池、custom pool、prepared cache、盘中 screen 和 factor artifact 复用现有 screen 流程。

## 能力边界

初始接入阶段支持：

- `screen`
- `chart`
- `factor_extraction`

`run/review/review-list/review-merge` 仍由 capability 控制。训练完成后先做模型导出和 promote dry-run，不自动发布为生产 run 能力，避免没有线上验证时改变模型主路径。

## 测试策略

按小步 TDD 实现：

- `Method` 解析测试：`"lsh"` 能解析并序列化为 `lsh`。
- 策略单测：构造日线穿越 MA25、周/月 MACD 柱和 DEA 均为正的历史，选出 `LSH`。
- 策略反例：日线条件不满足或周/月 MACD 柱不为正时不选出。
- screen 集成测试：`run_screen_with_loader` 或 prepared cache 能写出 `<date>.lsh.json`。
- capability 测试：`lsh` 支持 screen/factor/chart，不支持模型 run。

## 后续训练流程

实现和测试通过后，按当前 `.env` 读取 runtime root 和数据库配置，先查看机器核心数，再用至少半数核心作为 `--workers`/`--num-threads` 的基准。流程为：

```bash
uv run scripts/ml/backfill_candidates.py --method lsh --start-date <start> --end-date <end> --workers <n> --export-factors
uv run scripts/ml/build_rank_dataset.py --method lsh --runtime-root "$STOCK_SELECT_RUNTIME_ROOT" --source candidates --start-date <start> --end-date <end>
uv run scripts/ml/train_rank_lgbm.py --method lsh --dataset diagnostics/ml/lsh/rank_dataset.csv --output-dir diagnostics/ml/lsh/model ...
uv run scripts/ml/export_lgbm_scores.py --method lsh --model-output-dir diagnostics/ml/lsh/model
uv run scripts/ml/promote_lgbm_model.py --method lsh --candidate-dir diagnostics/ml/lsh/model --dry-run --require-report
```

训练结果需要汇报 dataset 覆盖质量、trial 指标、最佳参数、top features、是否建议发布和剩余风险。
