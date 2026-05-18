# 共用筛选流程

本文描述各方法在 `screen` 层共享的流程，方法自身的筛选条件见各自目录。

## 支持的方法

当前内置方法：

- `b1`
- `b2`
- `dribull`
- `hcr`

## 统一入口

CLI 入口：

```bash
uv run stock-select screen --method <method> --pick-date YYYY-MM-DD --dsn postgresql://...
```

盘中入口：

```bash
uv run stock-select screen --method <method> --intraday --dsn postgresql://...
```

## 数据准备层

### `b1` / `b2` / `dribull`

这三类方法共用基础 `prepared` 数据层，主要由以下准备字段构成：

- 原始日线：`open`、`high`、`low`、`close`、`volume/vol`
- 均线与衍生字段：`ma25`、`ma60`、`ma144`
- `KDJ`
- `zxdq`、`zxdkx`
- `turnover_n`
- `weekly_ma_bull`
- `max_vol_not_bearish`
- `chg_d`、`v_shrink`、`safe_mode`、`lt_filter`

其中：

- `turnover_n` 使用 `43` 日滚动成交额
- `weekly_ma_bull` 使用按周收盘重采样后的周线均线多头
- `dribull` 在基础 `prepared` 之外，还会按需补一段更长的 MACD warmup 历史，但不单独落盘

### `hcr`

`hcr` 使用独立的 `prepared` 数据层，主要字段为：

- 原始日线：`open`、`high`、`low`、`close`、`volume/vol`
- `ma25`、`ma60`
- `yx`
- `p`
- `resonance_gap_pct`

## 票池层

所有方法都会先根据 `pool_source` 决定参与筛选的股票集合，再在该集合上执行方法自身的筛选条件。

支持的 `pool_source`：

- `turnover-top`
- `record-watch`
- `custom`

### `turnover-top`

- 对 `b1` / `b2` / `dribull`：默认从 `prepared` 中构建流动性票池
- 对 `hcr`：不使用 `b1` 那套“前 `5000` 成交额池”特殊预过滤，只是在统一票池接口下继续跑自身筛选

### `record-watch`

- 从对应方法的 `watch_pool.csv` 派生有效股票集合
- 常用于只对近期已关注股票做复筛

### `custom`

- 从用户给定文件加载股票池

## 输出

EOD 运行产出：

```text
runtime/candidates/<pick_date>.<method>.json
```

盘中运行产出：

```text
runtime/candidates/<run_id>.<method>.json
```

候选文件至少包含：

- `method`
- `pick_date` 或 `trade_date`
- `pool_source`
- `candidates`

其中每个候选通常包含：

- `code`
- `pick_date`
- `close`
- `turnover_n`

方法特有字段例如：

- `b2`: `signal`
- `hcr`: `yx`、`p`、`resonance_gap_pct`、`hcr_score`

## 版本与缓存

- `b1` 的候选文件会写入 `screen_version`
- `hcr` 的 `prepared` cache 也有独立版本号
- `b1` / `b2` / `dribull` 共用基础 `prepared` cache
- intraday 只有在 `--recompute` 时才会重建当日共享 `prepared` cache
