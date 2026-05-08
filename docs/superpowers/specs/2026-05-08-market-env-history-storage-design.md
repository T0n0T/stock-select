# 市场环境历史存储与重建命令设计

## 背景

当前市场环境历史默认落盘为 `runtime/environment/history.json`，格式是整份 JSON：

```json
{
  "intervals": [
    ...
  ]
}
```

这个格式有两个问题：

1. 程序每次写入都需要整份重写，机器主存储不够轻量。
2. 用户虽然可以直接打开查看，但它同时承担“人类阅读”和“程序主存储”两种职责，后续如果要扩展或做更细粒度的持久化，约束较多。

另外，当前主 CLI 没有重建环境历史的入口。若环境判定逻辑发生变化，普通 `stock-select run ...` 只会在缺失区间时补写，不会自动按新逻辑重算历史；用户需要依赖单独脚本完成重建。

本设计的目标是：

- 提供主 CLI 的环境历史重建入口。
- 将环境历史改为“双层存储”。
- 保持人类查看直观，同时提升程序读写效率。
- 不保留旧 `history.json` 的兼容包袱。

## 目标与非目标

### 目标

- 新增 `stock-select market-env rebuild` 子命令。
- 新环境历史只认两份文件：
  - `runtime/environment/history.jsonl`
  - `runtime/environment/latest.json`
- 所有环境历史读写逻辑统一收口到 `stock_select.market_environment`。
- 普通 `run/screen` 在需要补写环境区间时，同步写出两份新文件。
- `market-env history` 默认输出 `latest.json` 的完整视图。

### 非目标

- 不兼容读取旧的 `runtime/environment/history.json`。
- 不在本次引入按年/月分片。
- 不在本次引入 append-only 增量写入协议。
- 不修改市场环境判定规则本身。

## 用户场景

### 场景 1：查看当前环境历史

用户执行：

```bash
stock-select market-env history
```

期望：

- 看到完整的区间列表。
- 输出结构与当前排查习惯接近，适合直接阅读。

### 场景 2：普通 run 自动补写缺失区间

用户执行：

```bash
stock-select run --method b2 --pick-date 2026-05-08
```

若 `pick_date` 对应环境区间缺失，系统应：

- 计算当前 `pick_date` 的市场环境。
- 将新区间写入内存中的 interval 列表。
- 同步写出 `history.jsonl` 与 `latest.json`。

若已有覆盖该日期的区间，则不重写环境历史。

### 场景 3：规则变化后整份重建

用户执行：

```bash
stock-select market-env rebuild --artifact-dir artifacts/review-tuning/foo --overwrite
```

期望：

- 按当前规则整份重建环境历史。
- 若目标文件已存在且未显式传入 `--overwrite`，则拒绝覆盖。

## 存储设计

### 文件布局

新格式固定为：

```text
runtime/
  environment/
    history.jsonl
    latest.json
```

### `history.jsonl`

机器主存储，按行保存区间记录。每一行都是一条完整 JSON 对象，例如：

```json
{"state":"strong","start_date":"2026-05-12","end_date":"2026-05-18","evaluated_at":"2026-05-12","source":"scheduled","manual_override":false,"reason":"broad rally"}
{"state":"weak","start_date":"2026-05-19","end_date":null,"evaluated_at":"2026-05-19","source":"manual_override","manual_override":true,"reason":"manual caution"}
```

选择 JSONL 的原因：

- 一行一条记录，diff 更容易阅读。
- 逐行解析简单，适合作为程序主存储。
- 相比整份 JSON，对“数据记录集合”的语义更直接。

### `latest.json`

人类可读快照，保存当前完整视图：

```json
{
  "intervals": [
    ...
  ]
}
```

选择保留该快照的原因：

- 用户直接打开文件即可看到完整历史。
- 保持与当前 `market-env history` 输出模型一致。
- 降低排查门槛，不需要手动从 JSONL 重建完整结构。

## 读写语义

### 读取规则

读取逻辑不再兼容旧 `history.json`。

统一规则如下：

- `load_environment_history(runtime_root)`：从 `history.jsonl` 读取并返回 interval 列表。
- `resolve_market_environment(...)`：基于 `load_environment_history(...)` 返回的 interval 列表解析指定 `pick_date`。
- `ensure_market_environment(...)`：若已存在覆盖 `pick_date` 的区间，直接复用；若不存在则评估并落盘。
- `market-env history`：优先读取 `latest.json` 输出。如果 `latest.json` 缺失或损坏，直接报错，不尝试回退旧格式。

说明：

- 程序内部主读取依赖 `history.jsonl`，保证“主存储只有一份语义来源”。
- `latest.json` 作为面向人的快照，不参与区间解析逻辑。

### 写入规则

所有写路径统一经过 `write_environment_history(runtime_root, intervals)`。

该函数负责：

1. 将传入 interval 列表校验并归一化为 `MarketEnvironmentInterval`。
2. 生成 `history.jsonl` 内容。
3. 生成 `latest.json` 内容。
4. 使用临时文件写入后原子替换目标文件，避免残缺文件。

两份文件的写入语义为：

- `history.jsonl`：整份重写，不做增量 append。
- `latest.json`：整份重写。

本次不做 append-only 的原因：

- 当前环境历史体量很小，整份重写成本可以忽略。
- 整份重写逻辑最简单，也最容易保持两份文件一致。
- 未来如需升级为 append-only，可只改写入实现，不改 CLI 与外部接口。

### 一致性要求

对调用方保证：

- 调用 `write_environment_history(...)` 成功后，两份文件必须同时处于同一版本。
- 任一目标文件若写入失败，最终不应留下部分写入的坏文件。

## CLI 设计

### 新增子命令

主 CLI 新增：

```bash
stock-select market-env rebuild
```

参数设计：

```bash
stock-select market-env rebuild --artifact-dir <dir> --overwrite
stock-select market-env rebuild --artifact-dir <dir> --runtime-root <path> --dsn <dsn> --overwrite
```

规则：

- `--artifact-dir` 必填，且目录下必须存在 `samples.csv`。
- `--runtime-root` 默认保持现状。
- `--dsn` 用于数据库连接，解析规则沿用现有 CLI。
- `--overwrite` 为显式覆盖开关。

### `--overwrite` 语义

重建命令的覆盖规则如下：

- 若 `environment/history.jsonl` 或 `environment/latest.json` 任一已存在，且未传 `--overwrite`，命令失败。
- 传入 `--overwrite` 后，允许整份重建并覆盖两份文件。

### 现有命令行为

- `market-env show`：接口不变。
- `market-env history`：接口不变，但底层改为从 `latest.json` 输出。
- `market-env override`：接口不变，但写入落到新双层格式。
- `run` / `screen`：接口不变，不新增 `--overwrite`。

## 与现有脚本的关系

当前单独脚本 `scripts/review_tuning_backfill_environment_history.py` 已能从样本文件构建环境历史。

本次调整：

- 将其核心逻辑下沉为可复用函数。
- `market-env rebuild` 复用该实现。
- 脚本保留，但只作为薄封装入口，避免主 CLI 与脚本各维护一套逻辑。

这样可以避免：

- 参数行为漂移。
- 一个入口支持新存储、另一个入口忘记同步。

## 错误处理

### 文件不存在

- `load_environment_history(...)` 在 `history.jsonl` 不存在时返回空列表。
- `market-env history` 在 `latest.json` 不存在时应报明确错误，提示用户先运行 `run` 或 `market-env rebuild`。

### 文件格式错误

- `history.jsonl` 某一行不是合法 JSON，或字段无法转成 `MarketEnvironmentInterval`，抛出明确的 `ValueError`。
- `latest.json` 不是合法 JSON，或缺失 `intervals` 数组，`market-env history` 直接报错。

### 重建覆盖冲突

- 重建命令发现目标文件已存在但未传 `--overwrite`，直接失败并给出明确提示。

## 测试计划

### `market_environment` 单测

新增或调整测试覆盖：

- `write_environment_history(...)` 同时写出 `history.jsonl` 与 `latest.json`。
- `load_environment_history(...)` 能从 `history.jsonl` 正确恢复 interval 列表。
- `resolve_market_environment(...)` 在新格式上行为不变。
- `ensure_market_environment(...)` 在首次补写时会生成两份文件。
- `override_market_environment(...)` 会同步更新两份文件。
- `history.jsonl` 非法行会触发明确异常。

### CLI 单测

新增或调整测试覆盖：

- `market-env history` 输出 `latest.json` 中的完整区间结构。
- `market-env rebuild --artifact-dir ... --overwrite` 成功写出新格式。
- 目标文件已存在且未传 `--overwrite` 时拒绝执行。

### 回归测试

- 普通 `screen` 调用 `ensure_market_environment(...)` 时，首次补写后的环境目录为新双文件格式。
- 现有依赖 `load_environment_history(...)` 和 `resolve_market_environment(...)` 的脚本/CLI 流程继续正常工作。

## 实施顺序

1. 为新存储格式和新 CLI 命令编写失败测试。
2. 在 `market_environment` 中引入 JSONL/快照读写 helper。
3. 修改 `load_environment_history`、`write_environment_history`、`ensure_market_environment`、`override_market_environment` 使用新格式。
4. 在主 CLI 中新增 `market-env rebuild`。
5. 让 `scripts/review_tuning_backfill_environment_history.py` 复用相同实现。
6. 运行目标测试与 smoke check，确认 `run`、`market-env history`、`market-env rebuild` 行为符合预期。

## 方案取舍总结

本方案选择：

- 程序主存储：`history.jsonl`
- 人类可读快照：`latest.json`
- 主 CLI 提供重建命令：`market-env rebuild`
- 不兼容旧 `history.json`

放弃的方案包括：

- 继续使用单文件 `history.json`
- 只写 JSONL、不提供直观快照
- 直接引入按月/按年分片

原因是当前方案在“直观性、实现复杂度、读写效率、后续可演进性”之间更均衡，且能以最小改动覆盖当前真实需求。
