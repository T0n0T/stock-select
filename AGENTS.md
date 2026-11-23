# AGENTS.md

## 文档约束

- 项目文档、roadmap、计划、状态说明和交接记录默认使用中文。
- 除非用户明确要求，避免新增英文文档。
- 所有结构图和流程图优先使用 Mermaid 语法（````mermaid` 代码块），禁止使用 ASCII 手工绘图。

## 运行环境

- 本仓库的 CLI、训练脚本和模型维护脚本统一以当前目录 `.env` 作为环境变量来源。
- 执行模型训练、候选补齐、因子补齐等可并行任务前，先查看机器可用核心数（例如 `nproc` 或 `getconf _NPROCESSORS_ONLN`）；并发 worker 数和模型线程数通常使用 4～8，最高 8，用户明确指定更低并发或机器负载不允许时可降低。
- 训练窗口按具体实验和用户指定显式设置，并以模型元数据记录的实际日期为准；不要把历史实验窗口当作通用默认值。构建历史技术因子所需的行情回看窗口仍由 Rust 管理。
- 常用变量包括：
  - `STOCK_SELECT_RUNTIME_ROOT`
  - `DUCKDB_PATH`
  - `QUACK_AUTH_TOKEN`
  - `QUACK_SSL_FINGERPRINT`
  - `TUSHARE_TOKEN`
- 涉及凭据时，不要打印 `.env`、数据库路径或 token 的具体值。

## 开发约束

- 开始工作前先运行 `git status --short --branch`。
- 不要覆盖、回退或清理用户已有的未提交改动。
- 严格小步 TDD：先写失败测试，再实现，再验证通过。
- 迁移旧实现时优先复用旧 Rust 代码，做最小搬迁，不做无关重构。

## 指针

- CLI 架构说明见 `docs/architecture.md`。
- 模型训练、推理和评分规则见 `docs/model.md`。
- 常见工作流程见 `docs/workflow.md`。
- 后续计划和待办事项见 `docs/roadmap.md`。
- 模型训练、发布、回滚和归档切换见 `stock-select-ml` Python CLI 与 `.agents/skills/model-maintenance/references/model-maintenance.md`。
