# 后续计划

当前主路径为 `screen → factor → LightGBM rank → display`，支持 B2、SCM、PBM。数据源和中间缓存已完成迁移，本分支不再维护旧策略及历史产物兼容。

## 已完成

- [x] 使用 `duckdb-neo` 读取 stock-cache 本地 DuckDB 文件及 Quack 远程服务。
- [x] prepared 缓存改为 Parquet schema 14，校验价格基准及上一完整月 MACD 版本。
- [x] 删除旧策略实现、策略名、专用因子和历史候选、模型归档兼容逻辑。
- [x] SCM/PBM 共享语义因子统一命名为 `ma25_*`，因子库升级为 `rust-factor-library-v5`。
- [x] 通用候选适配归入 `engine/candidates.rs`，产物命名归入 `engine/artifacts.rs`。

## 近期

- [ ] 按当前因子契约重新生成候选、数据集和模型，完成滚动样本外验证。
- [ ] 分别统计数据加载、Parquet 读写、因子计算和推理的完整耗时及峰值内存，确定性能热点。
- [ ] 在性能证据支持时，针对批量 rolling、横截面或 Python 数据集关联比较 DuckDB、Rust 和 Polars；MACD/CZSC 状态机继续单独分析。
- [ ] `main.rs` 按命令编排、图表执行、HTML 报告拆分为私有模块。

## 按变更需要推进

- [ ] 将 `db.rs` 的连接/参数绑定与 stock-cache 行情映射拆入私有子模块，保持加载接口集中。
- [ ] 新增缓存类型时独立 Parquet 编解码，新增因子族时独立数据库字段映射，避免纯转发模块。
- [ ] 为 B2、SCM、PBM 建立 dataset → train → 验证 → promote 的完整回归流程。
