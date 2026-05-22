# 市场环境命令

`market-env` 用于查看、维护和重建市场环境区间历史。

## 常用命令

```bash
uv run stock-select market-env show --pick-date YYYY-MM-DD
uv run stock-select market-env history
uv run stock-select market-env override --pick-date YYYY-MM-DD --state weak --reason "manual caution"
uv run stock-select market-env rebuild --artifact-dir artifacts/review-tuning/<run-id> --overwrite --dsn postgresql://...
```

## 子命令

### `market-env show`

- 查看某个 `pick_date` 命中的环境区间

### `market-env history`

- 输出当前完整环境历史快照

### `market-env override`

- 从指定 `pick_date` 起手动覆盖环境状态
- `--state` 使用 `strong` / `neutral` / `weak`

### `market-env rebuild`

- 按当前规则重建整份环境历史
- 输入是包含 `samples.csv` 的 artifact 目录
- 已存在目标文件时必须显式传 `--overwrite`

## 典型使用场景

- 你修改了市场环境判定逻辑，想整体重算历史
- 你已有 `review_tuning_collect.py` 产出的 `samples.csv`
- 你希望 `run` / `review` / 调参脚本共用同一份最新环境历史

## 落盘位置

```text
~/.agents/skills/stock-select/runtime/environment/daily/
~/.agents/skills/stock-select/runtime/environment/history.jsonl
~/.agents/skills/stock-select/runtime/environment/latest.json
```

## 说明

- 普通 `run --pick-date ...` 只会在目标日缺少环境时补写
- 不会默认整份重建环境历史
- 若规则调整，应显式执行 `market-env rebuild ... --overwrite`
