# AGENTS

本仓库是 `/home/pi/Documents/agents/stock-select` 的 Rust 重构项目。项目文档、设计记录和协作说明默认使用中文。

## 协作约定

1. 默认不要直接在 `master` 上开发；从最新 `master` 拉功能分支。
2. 只有明确需要 stacked PR 时，才从非 `master` 分支继续开发，并说明 base 分支。
3. 完成后通过 PR 或明确的本地合并流程回到 `master`。
4. 修改前先检查工作区状态，不覆盖用户或其他协作者的未提交改动。

## 实现边界

1. Rust CLI 的用户流程、runtime 目录结构和最终产物应与 Python `stock-select` CLI 对齐；prepared cache 内部格式可以不同。
2. 日常筛选、复盘、画图、review、run、intraday 和单股分析优先使用本仓库 Rust CLI；上游 Python CLI 只用于明确要求的 golden 对照或历史结果读取。
3. 生产路径不再保留源 Python CLI bridge。未完成的 Rust 原生方法必须显式报错，不允许静默回退到 Python CLI。
4. 如需 Python 绘图库，只允许通过本仓库受控脚本调用，不重新引入上游 Python CLI。
5. 优先沿用既有模块边界和数据结构，避免无关重构。

## Golden 与 Runtime

1. Python golden 默认从 `~/.agents/skills/stock-select/runtime` 读取；除非用户明确要求，不要重算 Python golden。
2. 做 Rust/Python 对齐验证时，Rust runtime 默认放在 `/tmp` 下的临时目录。
3. 详细状态、命令清单、runtime layout 和下一步推进顺序以 `docs/roadmap.md` 为准。

## 验证规则

完成实现或文档阶段性更新前，至少运行：

```bash
git status --short
```

涉及 Rust 代码时运行：

```bash
cargo fmt --check
cargo test --quiet
```

涉及 Python 脚本时运行：

```bash
python3 -m py_compile scripts/check_charts.py scripts/compare_screen.py scripts/compare_review.py
```

修改 chart runner 时额外运行：

```bash
python3 -m py_compile scripts/render_charts.py
python3 scripts/check_charts.py --runtime-root <rust-runtime-root> --pick-date 2026-05-25 --method b1
```

## 开发注意事项

1. 新增 Rust 原生能力时，优先补小粒度单元测试或 golden fixture，再实现逻辑。
2. parity 失败时按层定位：候选集、score 输入字段、MACD wave context、gate flags、最终 decision、summary/recommendation。
3. 重要用户流程或 runtime 行为变化，需要同步更新 `docs/roadmap.md`。
