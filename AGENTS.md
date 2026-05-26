# AGENTS

本仓库是 `/home/pi/Documents/agents/stock-select` 的 Rust 重构项目。协作时应同时遵守上游 Python 项目的约定，并以本文件作为本仓库的项目级规则。

## 协作约定

1. 开发时默认使用分支进行，不直接在 `master` 分支上开发。
2. 默认流程是：先切回最新的 `master`，再从 `master` 拉出新的功能分支；不要默认从上一个功能分支继续拉分支。
3. 只有在明确需要 stacked PR / 依赖上游未合并分支时，才允许从非 `master` 分支继续拉新分支，并在 PR 说明里写清 base 分支。
4. 新功能或修复完成后，通过 PR 合并到 `master`。
5. 项目文档、设计说明、研究记录与协作说明默认使用中文。

## 重构目标

1. Rust CLI 的用户流程和最终产物需要与 Python `stock-select` CLI 对齐。
2. `prepare cache` 的内部格式可以不兼容 Python，但 CLI 使用方式、runtime 目录结构和最终结果需要保持一致。
3. 当前优先级是推进 `b1` 的 Rust 原生能力，特别是 `screen`、`chart`、`review`、`run` 的端到端对齐。
4. CLI 生产路径不再保留源 Python CLI bridge；未完成 Rust 原生实现的方法应显式报错，不允许静默回退到 Python CLI。

## Python Golden 约束

1. Python 侧历史结果默认从以下路径读取：

   ```text
   ~/.agents/skills/stock-select/runtime
   ```

2. 除非用户明确要求，不要重算 Python golden 结果。
3. 做 Rust 对齐验证时，Rust runtime 默认使用 `/tmp` 下的临时路径。
4. b1 基准日期优先使用 `2026-05-25`，当前已知 Python baseline 为：

   ```text
   candidates=104
   reviewed=104
   recommendations=3
   recommendation codes=000066.SZ,300292.SZ,301290.SZ
   ```

## 当前实现边界

1. `stock-select-rs screen` 已是 Rust 原生路径。
2. `stock-select-rs chart` 已迁到本仓库内置 chart runner：Rust 读取 prepared cache 并调用 `scripts/render_charts.py`，不再调用源 Python CLI 项目。
3. `stock-select-rs review` 直接调用 Rust native review；当前只有 `b1` 已完成原生 parity，其他方法会显式返回未实现错误。
4. `stock-select-rs run` 当前是 Rust screen + 本仓库 chart runner + Rust native review；只有 `b1` review 完整可用。
5. 环境 profile 目前 Rust 侧已有常量和 scoring helper，但自动环境评估仍未完全原生化。

## 文档规则

1. 后续新增或更新的项目文档默认使用中文，包括 `docs/` 下的 roadmap、plan、spec、研究记录和协作说明。
2. 若需要引用 Python 源码、命令输出或字段名，保留原始英文标识，不强行翻译代码符号。
3. `docs/roadmap.md` 是当前重构现状和下一步推进顺序的主入口。
4. 重要阶段切换必须同步更新 roadmap，例如：
   - review/run 默认原生行为发生变化
   - run 默认编排发生变化
   - environment profile 原生化完成
   - chart 渲染策略发生变化

## 验证规则

完成实现或文档阶段性更新前，至少检查：

```bash
git status --short
```

涉及 Rust 代码时，运行：

```bash
cargo fmt --check
cargo test --quiet
```

涉及 Python 脚本时，运行：

```bash
python3 -m py_compile scripts/check_charts.py scripts/compare_screen.py scripts/compare_review.py
```

如果修改 chart runner，同时检查：

```bash
python3 -m py_compile scripts/render_charts.py
python3 scripts/check_charts.py --runtime-root <rust-runtime-root> --pick-date 2026-05-25 --method b1
```

涉及 b1 CLI 对齐时，优先使用：

```bash
python3 scripts/compare_screen.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root <rust-runtime-root> \
  --pick-date 2026-05-25 \
  --method b1

python3 scripts/compare_review.py \
  --python-root ~/.agents/skills/stock-select/runtime \
  --rust-root <rust-runtime-root> \
  --pick-date 2026-05-25 \
  --method b1
```

## 开发注意事项

1. 优先沿用已有模块边界，不做无关重构。
2. 修改已有文件前，先确认是否存在用户或其他协作者的未提交改动，不要覆盖无关修改。
3. 新增 Rust 原生能力时，优先补 golden fixture 或小粒度单元测试，再实现逻辑。
4. parity 失败时按层定位：候选集、score 输入字段、MACD wave context、gate flags、最终 decision、summary/recommendation。
5. 不要重新引入源 Python CLI bridge；如需 Python 绘图库，只允许通过本仓库受控脚本调用。
