# stock-select

`stock-select` 是面向 A 股的 Rust 原生 CLI，支持筛选、图表生成、原生基线复盘、复盘合并/列表、盘中快照、观察池记录和复盘统计。

本仓库是原 Python CLI 的后续重构项目。Python CLI 已进入最终发布状态，后续只作为 golden 参考和迁移校验的历史/辅助分支保留；新的生产能力应优先在 Rust CLI 中实现。

## 当前状态

- Rust 二进制：`stock-select-rs`
- 主分支目标：Rust CLI
- 历史 Python 实现：最终 Python 版本发布后保留为辅助分支
- 已支持的原生方法：`b1`、`b2`、`dribull`
- 暂不支持的方法：`hcr`

生产路径不再回退到上游 Python CLI。图表渲染仍通过本仓库内受控 Python 脚本调用 `matplotlib`/`mplfinance`，不会调用历史 Python CLI。

## 构建

```bash
cargo build --release
cp target/release/stock-select-rs ~/.local/bin/
```

生成 shell completion：

```bash
stock-select-rs completions zsh > /tmp/_stock-select-rs
stock-select-rs completions bash > /tmp/stock-select-rs.bash
```

## 配置

配置优先级：

```text
CLI 参数 > 进程环境变量 > 当前工作目录 .env
```

支持的配置项：

- `POSTGRES_DSN`
- `TUSHARE_TOKEN`
- `STOCK_SELECT_POOL_FILE`

默认 runtime 根目录：

```text
~/.agents/skills/stock-select/runtime
```

## 常用命令

日线运行：

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime \
  --recompute
```

盘中运行：

```bash
stock-select-rs run \
  --method b2 \
  --intraday \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

复盘已有筛选结果：

```bash
stock-select-rs review \
  --method b2 \
  --pick-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

查看复盘结果：

```bash
stock-select-rs review-list \
  --method b2 \
  --pick-date 2026-05-25 \
  --verdict WATCH
```

分析单只股票：

```bash
stock-select-rs analyze-symbol \
  --method b2 \
  --symbol 002350.SZ \
  --pick-date 2026-04-21
```

## 观察池

在 `run` 或 `review` 中追加 `--record`，可将当天 `PASS` 和 `WATCH` 结果导入：

```text
<runtime-root>/watch_pool.csv
```

记录以 `method + code` 为键。重复入选时会刷新保存的选股日期、结论、分数、备注和 `recorded_at`。

```bash
stock-select-rs run \
  --method b2 \
  --pick-date 2026-05-25 \
  --record
```

默认保留最近 15 个交易日：

```bash
stock-select-rs review \
  --method b2 \
  --pick-date 2026-05-25 \
  --record \
  --record-window-trading-days 20
```

## 批处理和统计脚本

补跑基线复盘：

```bash
python3 scripts/backfill_baseline_reviews.py \
  --method b2 \
  --start-date 2026-05-20 \
  --end-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

补跑脚本默认使用 `--max-workers 1`，因为每次运行会共享同一个 runtime cache。只有在可以接受失败日期重试时，才建议显式调大并发数。

计算 PASS topN 胜率统计：

```bash
python3 scripts/review_top3_win_stats.py \
  --method b2 \
  --start-date 2026-04-01 \
  --end-date 2026-05-25 \
  --runtime-root ~/.agents/skills/stock-select/runtime
```

统计脚本优先关注胜率比例，而不是平均远期收益：

- `win_rate_ret3_pct`
- `win_rate_ret5_pct`
- `day_hit_rate_ret3_pct`
- `day_hit_rate_ret5_pct`

这样可以避免因为少数极端上涨样本而高估 PASS top3 集合。

## Runtime 布局

日线产物：

```text
candidates/<pick_date>.<method>.json
charts/<pick_date>.<method>/<code>_day.png
reviews/<pick_date>.<method>/<code>.json
reviews/<pick_date>.<method>/summary.json
reviews/<pick_date>.<method>/llm_review_tasks.json
```

盘中产物使用按日期划分的 key：

```text
candidates/<trade_date>.intraday.<method>.json
charts/<trade_date>.intraday.<method>/<code>_day.png
reviews/<trade_date>.intraday.<method>/summary.json
prepared/<trade_date>.intraday.bin
prepared/<trade_date>.intraday.meta.json
```

## 验证

合并 Rust 改动前运行：

```bash
cargo fmt --check
cargo test --quiet
python3 -m py_compile \
  scripts/check_charts.py \
  scripts/compare_screen.py \
  scripts/compare_review.py \
  scripts/render_charts.py \
  scripts/backfill_baseline_reviews.py \
  scripts/review_top3_win_stats.py
```

Python golden 对齐校验默认读取历史产物：

```text
~/.agents/skills/stock-select/runtime
```

除非明确需要，不要重新计算 Python golden 输出。
