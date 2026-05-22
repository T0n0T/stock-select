# stock-select

用于承载 `stock-select` 技能与 CLI 的独立仓库。

当前仓库提供一套可单独运行的 A 股选股流程，包括：

- 从 PostgreSQL 读取市场数据
- 运行 `b1` / `b2` / `dribull` / `left_peak` / `hcr` 的确定性筛选
- 为候选股票导出日线 PNG 图
- 对候选执行 baseline review，并生成后续 LLM 图评任务

## 安装

开发环境：

```bash
uv sync
```

在项目目录中直接运行 CLI：

```bash
uv run stock-select --help
```

安装为当前机器可直接调用的 CLI：

```bash
uv tool install .
```

如需用本地最新代码覆盖安装：

```bash
uv tool install --reinstall .
```

## 快速开始

完整 EOD 流程：

```bash
uv run stock-select run --method b1 --pick-date YYYY-MM-DD --dsn postgresql://...
```

盘中流程：

```bash
uv run stock-select run --method b1 --intraday --dsn postgresql://...
```

只做 review，并临时覆盖环境：

```bash
uv run stock-select review --method b1 --pick-date YYYY-MM-DD \
  --environment-state weak \
  --environment-reason "manual caution" \
  --dsn postgresql://...
```

## 文档索引

CLI 文档：

- [CLI 总览](./docs/cli/overview.md)
- [选股主流程：screen / chart / review / run](./docs/cli/screen-chart-review-run.md)
- [市场环境命令：market-env](./docs/cli/market-environment.md)
- [单票分析与观察池：analyze-symbol / record-watch](./docs/cli/analyze-symbol-and-watch.md)
- [站点与清理：html / clean / review-merge](./docs/cli/html-and-clean.md)

方法文档：

- [方法文档总览](./docs/README.md)
- [共用筛选流程](./docs/share/screen-common.md)
- [共用 Review 流程](./docs/share/review-common.md)
- [共用运行产物](./docs/share/runtime-artifacts.md)

## Review 调参诊断

调参诊断 workflow 仍保留在仓库内，推荐按以下顺序执行：

```bash
uv run python scripts/review_tuning_collect.py \
  --methods b1 b2 dribull hcr \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --runtime-root ~/.agents/skills/stock-select/runtime \
  --prepared-root ~/.agents/skills/stock-select/runtime/prepared \
  --artifact-dir artifacts/review-tuning/<run-id>

uv run python scripts/review_tuning_attach_environment.py \
  --artifact-dir artifacts/review-tuning/<run-id> \
  --runtime-root ~/.agents/skills/stock-select/runtime \
  --environment-key score_based_state

uv run python scripts/review_tuning_correlations.py \
  --artifact-dir artifacts/review-tuning/<run-id>

uv run python scripts/review_tuning_segments.py \
  --artifact-dir artifacts/review-tuning/<run-id>

uv run python scripts/review_tuning_recommend.py \
  --artifact-dir artifacts/review-tuning/<run-id>
```

如需做调参前后复验：

```bash
uv run python scripts/review_tuning_verify.py \
  --baseline-artifact-dir artifacts/review-tuning/<baseline-run-id> \
  --candidate-artifact-dir artifacts/review-tuning/<candidate-run-id> \
  --artifact-dir artifacts/review-tuning/<verify-run-id>
```
