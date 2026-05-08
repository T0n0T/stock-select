# 市场环境每日文件与聚合历史设计

## 背景

当前市场环境历史已经从旧的单文件 `history.json` 迁移为：

- `runtime/environment/history.jsonl`
- `runtime/environment/latest.json`

但这套实现仍然不满足两个核心需求：

1. 人工观察需求  
   现在没有“按交易日落盘”的环境文件，用户不能直接按日期查看某一天的完整环境评估结果。

2. 机器读取需求  
   当前 `history.jsonl` 实际上保存的是压缩后的区间历史，而不是每日记录。这不利于后续按日期、按状态进行研究和筛选，也不符合“机器快速读取每日环境事实”的目标。

因此，本次设计要把环境持久化改造成“三层结构”：

- 每日文件：给人看
- 每日聚合文件：给机器读
- 概览快照：给快速总览和 CLI 输出

## 目标与非目标

### 目标

- 为每个交易日生成一份环境评估文件，即使连续多天状态相同也照样落盘。
- 每日文件名包含日期和环境类型，便于人工观察。
- `history.jsonl` 改为保存每日记录，而不是区间记录。
- `latest.json` 同时提供：
  - 每日状态概览
  - 压缩后的连续区间概览
- 普通 `run/screen`、`market-env override`、`market-env rebuild` 使用统一的持久化入口。

### 非目标

- 本次不引入 SQLite / DuckDB。
- 本次不引入按月或按年分片。
- 本次不修改市场环境评分逻辑。
- 本次不引入旧格式兼容层。

## 文件布局

环境目录调整为：

```text
runtime/
  environment/
    daily/
      2026-05-08.weak.json
      2026-05-09.weak.json
      2026-05-12.strong.json
    history.jsonl
    latest.json
```

三类文件职责如下：

- `daily/*.json`
  - 每个交易日一份完整环境评估结果
  - 主要给人观察和排查
- `history.jsonl`
  - 每日聚合记录
  - 主要给机器快速顺序读取
- `latest.json`
  - 当前完整概览快照
  - 同时包含每日视图和压缩区间视图

## 每日文件设计

### 命名规则

每日文件命名固定为：

```text
YYYY-MM-DD.<state>.json
```

例如：

- `2026-05-08.weak.json`
- `2026-05-09.neutral.json`
- `2026-05-12.strong.json`

### 内容结构

每日文件保存当天完整评估 payload，而不是只存一个简写状态。示例：

```json
{
  "pick_date": "2026-05-08",
  "state": "weak",
  "score_based_state": "weak",
  "rule_based_state": "neutral",
  "vote_based_state": "weak",
  "evaluate_date": "2026-05-08",
  "source": "scheduled",
  "reason": "...",
  "total_score": -6.0,
  "score_based_total": -6.0,
  "score_thresholds": {
    "strong": 10.0,
    "weak": -4.0
  },
  "indices": {
    "sse": { "...": "..." },
    "cn2000": { "...": "..." }
  },
  "monthly_bias": {
    "sse": "...",
    "cn2000": "..."
  }
}
```

### 每日文件写入语义

- 即使前后两天状态相同，也每天各写一份文件。
- 同一 `pick_date` 如果重算并得到不同状态：
  - 删除旧文件
  - 写入新状态文件

## `history.jsonl` 设计

### 语义

`history.jsonl` 保存“每日记录”，不再保存压缩后的区间记录。

每行一条 daily evaluation 的核心字段。示例：

```json
{"pick_date":"2026-05-08","state":"weak","score_based_state":"weak","rule_based_state":"neutral","vote_based_state":"weak","evaluate_date":"2026-05-08","source":"scheduled","reason":"...","total_score":-6.0,"score_based_total":-6.0}
```

### 保存字段

建议至少保存：

- `pick_date`
- `state`
- `score_based_state`
- `rule_based_state`
- `vote_based_state`
- `evaluate_date`
- `source`
- `reason`
- `total_score`
- `score_based_total`

不要求在 `history.jsonl` 中重复保存完整嵌套 payload，因为完整细节已经存在每日文件中。

### 使用方式

- 机器需要按日期和状态快速读取时，优先读 `history.jsonl`
- `resolve_market_environment(...)` 从 `history.jsonl` 读取 daily records，再在内存中压缩为 intervals

## `latest.json` 设计

`latest.json` 不再只是区间快照，而是完整概览快照：

```json
{
  "daily": [
    {
      "pick_date": "2026-05-08",
      "state": "weak",
      "source": "scheduled",
      "reason": "..."
    }
  ],
  "intervals": [
    {
      "state": "weak",
      "start_date": "2026-05-08",
      "end_date": "2026-05-09",
      "evaluated_at": "2026-05-09",
      "source": "scheduled",
      "reason": "..."
    }
  ]
}
```

其中：

- `daily`
  - 只保留便于快速概览的关键字段
- `intervals`
  - 由 daily 记录压缩得到
  - 供人工快速看连续状态区间

## 读取规则

### `load_environment_history(runtime_root)`

- 从 `history.jsonl` 读取 daily records
- 返回每日记录列表

### `resolve_market_environment(runtime_root, pick_date=...)`

- 从 `history.jsonl` 读取 daily records
- 按日期排序
- 在内存中压缩出连续区间
- 再解析指定 `pick_date` 命中的区间

### `market-env history`

- 默认输出 `latest.json`

### 人工排查

- 看某一天细节：打开 `daily/YYYY-MM-DD.<state>.json`
- 看整体概览：打开 `latest.json`

## 写入规则

### 统一持久化入口

所有写入都应收口到一套 helper，负责同时更新：

- `daily/`
- `history.jsonl`
- `latest.json`

### 普通 `run/screen`

若目标日尚无 daily 文件：

1. 评估当天环境
2. 写入 `daily/YYYY-MM-DD.<state>.json`
3. 更新 `history.jsonl`
4. 重建 `latest.json`

若目标日已有 daily 文件：

- 默认直接复用，不重写

### `market-env override`

1. 删除同日期已有 daily 文件
2. 写入新的 `daily/YYYY-MM-DD.<state>.json`
3. 在 `history.jsonl` 中替换该日期记录
4. 重建 `latest.json`

### `market-env rebuild --artifact-dir ... --overwrite`

1. 清空并重建 `daily/`
2. 对 `samples.csv` 中的每个 `pick_date` 重新评估
3. 逐日写入 daily 文件
4. 全量重写 `history.jsonl`
5. 全量重写 `latest.json`

## 区间压缩规则

`latest.json["intervals"]` 以及 `resolve_market_environment(...)` 使用相同压缩逻辑：

- daily records 按 `pick_date` 排序
- 连续相同 `state` 压缩成一个 interval
- interval 字段包括：
  - `state`
  - `start_date`
  - `end_date`
  - `evaluated_at`
  - `source`
  - `reason`

其中：

- `end_date` 是该连续状态最后一个交易日
- `evaluated_at` 取该 interval 最后一天的 `evaluate_date`

## CLI 设计

本次不增加新的 CLI 子命令，仅调整已有行为。

### `market-env history`

- 继续保留原命令
- 底层改为输出新的 `latest.json`

### `market-env override`

- 接口保持不变
- 底层改为更新 daily / jsonl / latest 三类文件

### `market-env rebuild`

- 继续保留
- 输入保持为：

```bash
stock-select market-env rebuild --artifact-dir <dir> --overwrite
```

- 从 `<artifact-dir>/samples.csv` 中提取 `pick_date`
- 重建三类环境文件

## 测试计划

### `market_environment` 单测

新增或调整测试覆盖：

- 每日文件会按 `YYYY-MM-DD.<state>.json` 命名
- 每次写入会同步生成：
  - `daily/*.json`
  - `history.jsonl`
  - `latest.json`
- `load_environment_history(...)` 从 `history.jsonl` 读取 daily records
- `resolve_market_environment(...)` 能从 daily records 正确压缩出 intervals
- `override_market_environment(...)` 会替换当日 daily 文件并重建聚合文件

### CLI 单测

新增或调整测试覆盖：

- `market-env history` 输出新的 `latest.json`
- `market-env rebuild --artifact-dir ... --overwrite` 会重建 `daily/`
- 普通 `screen/run` 首次补写环境时会生成当天 daily 文件
- 已有同日 daily 文件时，普通 `run` 默认不重写

### 脚本测试

调整 `scripts/review_tuning_backfill_environment_history.py` 的测试，验证：

- 通过 artifact 目录重建时，会写出 daily 文件集
- 未传 `--overwrite` 且已有环境历史时仍会拒绝覆盖

## 实施顺序

1. 先写失败测试，定义新的 daily/jsonl/latest 预期。
2. 引入 daily record 序列化/反序列化 helper。
3. 将 `history.jsonl` 从 interval 记录改为 daily 记录。
4. 加入从 daily records 生成 `latest.json` 的 helper。
5. 修改 `ensure_market_environment(...)`、`override_market_environment(...)`、`rebuild_environment_history(...)` 统一走新持久化入口。
6. 运行目标测试与 smoke check。

## 方案取舍总结

本方案选择：

- 人类观察面：`daily/YYYY-MM-DD.<state>.json`
- 机器读取面：`history.jsonl`
- 概览面：`latest.json`

放弃的方案包括：

- 仅保留 `history.jsonl + latest.json`
- 使用 SQLite 作为机器主读取层
- 只在状态变化日落文件

原因是当前目标优先级是：

1. 每日都有可直接观察的环境文件
2. 机器仍有一份简单快速的聚合读取文件
3. 不额外引入新的数据库技术栈
