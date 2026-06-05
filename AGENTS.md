# AGENTS.md

## 文档约束

- 项目文档、roadmap、计划、状态说明和交接记录默认使用中文。
- 除非用户明确要求，避免新增英文文档。

## 运行环境

- 本仓库的 CLI、训练脚本和模型维护脚本统一以当前目录 `.env` 作为环境变量来源。
- 常用变量包括：
  - `STOCK_SELECT_RUNTIME_ROOT`
  - `POSTGRES_DSN`
  - `TUSHARE_TOKEN`
- 涉及凭据时，不要打印 `.env`、DSN 或 token 的具体值。

## 开发约束

- 开始工作前先运行 `git status --short --branch`。
- 不要覆盖、回退或清理用户已有的未提交改动。
- 严格小步 TDD：先写失败测试，再实现，再验证通过。
- 迁移旧实现时优先复用旧 Rust 代码，做最小搬迁，不做无关重构。

## 指针

- 详细进度与阶段状态见 `docs/roadmap.md`。
- 模型训练、发布、回滚和归档切换见 `scripts/model_maintenance.sh` 与 `.agents/skills/model-maintenance/references/model-maintenance.md`。
