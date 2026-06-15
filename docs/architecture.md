# stock-select CLI 架构

## 总览

`stock-select-rs` 是一个 Rust CLI 工具，用于 A 股选股筛选、排序和复盘。核心流程是 **screen → factor → rank → display**，以 LightGBM 模型排序为主路径。

```mermaid
flowchart LR
    A["screen<br/>(候选池)"] --> B["factor<br/>(因子)"]
    B --> C["rank<br/>(排序)"]
    C --> D["display<br/>(展示)"]
    B -.-> E["factor artifact<br/>runtime/factors/"]
    D -.-> F["display.json<br/>llm_tasks.json<br/>charts/"]
```

## 二进制

```text
binary: stock-select-rs
source: src/main.rs
```

编译后安装在 `~/.cargo/bin/stock-select-rs`。

## 子命令

| 命令 | 功能 |
|------|------|
| `screen` | 筛选候选股，可选导出因子 |
| `run` | 完整流水线：screen → factor → rank → chart → review task |
| `review` | 从已有 display 生成 LLM task |
| `review-list` | 查看排序结果 |
| `review-merge` | 合并人工/LLM 复盘 annotation |
| `chart` | 生成 K 线图表 |
| `completions` | shell 补全 |

### screen

```bash
stock-select-rs screen --method b2 --pick-date 2026-06-05
stock-select-rs screen --method b2 --pick-date 2026-06-05 --export-factors
```

- 从 DB 或 Tushare API 获取行情数据
- 计算技术指标（均线、MACD、量价等）
- 按选股规则筛选候选股
- 写入 `runtime/candidates/<date>.<method>.json`
- `--export-factors` 额外导出因子到 `runtime/factors/`

当前已接入 `screen` 的方法为 `b2`、`b3`、`lsh`；各方法的股票池过滤和策略条件见 [选股筛选方法过滤条件](screening-methods.md)。

### run

```bash
stock-select-rs run --method b2 --pick-date 2026-06-05
stock-select-rs run --method b2 --llm-review-limit 5 --pick-date 2026-06-05
```

完整流水线：
1. **auto-screen** — 内部调用 screen（`export_factors: false`）
2. **环境评分** — 用上证指数/国证 2000 评估市场状态（weak / neutral / strong）
3. **selection**：
   - 加载候选 → 注入 prepared history → 计算因子 → 模型推理 → 排序 → 写 display artifact
4. **chart** — 为 top N 候选生成 K 线 PNG
5. **review task** — 生成 LLM 复盘任务文件

输出到 `runtime/select/<date>.<method>/`：
- `run.json` — 运行元信息
- `candidates.json` — 候选列表
- `factors.json` — 因子矩阵
- `ranked.json` — 排序结果
- `display.json` — 展示行（含 model_rank, model_score, llm_action 等）
- `feature_vectors.json` — 特征向量（用于调试）
- `llm_tasks.json` — LLM 复盘任务
- `llm_annotations.json` — 子代理/人工复盘 annotation
- `llm_report.html` — `review-merge` 生成的图文复盘报告
- `llm_raw/<code>.json` — 单票子代理原始复盘内容

### review-list

```bash
stock-select-rs review-list --method b2 --pick-date 2026-06-05 --limit 20
```

输出格式（tab 分隔）：

```text
rank  code    name    industry  score       bias  action  flags
1     000001  平安银行  银行       0.700000    ↑     KEEP    -
```

- `rank` — 模型排序位置（1-based）
- `score` — LightGBM 原始预测分
- `bias` — LLM 短线符号：`↑` 看多、`→` 谨慎、`↓` 看空、`-` 未复盘
- `action` — LLM 复盘动作
- `flags` — LLM 风险标记

### review / review-merge

```bash
stock-select-rs review --method b2 --pick-date 2026-06-05 --limit 5
stock-select-rs review-merge --method b2 --pick-date 2026-06-05
```

- `review` 从 `display.json` 生成 `llm_tasks.json`，包含 `chart_path`、建议的 `raw_response_path`、`llm_report_path` 和游资/短线读图提示
- `review-merge` 将填写的 `llm_annotations.json` 合并回 display，并生成 `llm_report.html`

### chart

```bash
stock-select-rs chart --method b2 --pick-date 2026-06-05 --chart-workers 4
```

生成 K 线图（含 MA25、中道/中轨、MACD、成交量）到 `runtime/charts/<date>.<method>/`。

### 通用参数

| 参数 | 说明 |
|------|------|
| `--method` | 筛选方法，当前 `screen` 支持 `b2` / `b3` / `lsh`，默认 `b2` |
| `--pick-date` | 交易日（默认取当前日期） |
| `--intraday` | 盘中模式 |
| `--runtime-root` | runtime 根目录（默认 `~/.agents/skills/stock-select/runtime`） |
| `--dsn` | PostgreSQL DSN |
| `--pool-source` | 候选池来源（`turnover-top` 等） |
| `--pool-file` | 自定义股票池文件 |

## 配置优先级

```text
CLI 参数  >  shell 环境变量  >  当前目录 .env
```

关键环境变量：

| 变量 | 说明 |
|------|------|
| `STOCK_SELECT_RUNTIME_ROOT` | runtime 根目录 |
| `POSTGRES_DSN` | PostgreSQL 连接串 |
| `TUSHARE_TOKEN` | Tushare API token |
| `STOCK_SELECT_BIN` | 二进制路径（用于脚本） |

## Runtime 目录布局

```text
runtime/
├── candidates/         候选 JSON
│   └── <date>.<method>.json
├── factors/            因子矩阵
│   └── <date>.<method>/
│       ├── factors.json
│       └── manifest.json
├── select/             排序结果
│   └── <date>.<method>/
│       ├── run.json
│       ├── candidates.json
│       ├── factors.json
│       ├── ranked.json
│       ├── display.json
│       ├── feature_vectors.json
│       ├── llm_tasks.json
│       └── llm_annotations.json
├── charts/             K 线图
│   └── <date>.<method>/
│       └── <code>_day.png
├── models/             模型产物
│   ├── b2/
│   │   ├── model.txt            (LightGBM booster)
│   │   └── model_metadata.json  (特征元信息)
│   └── archive/        历史归档
├── prepared/           预处理缓存
└── environment/        环境状态
    └── daily/
```

# 运行时架构全图

```mermaid
flowchart TD
    subgraph CLI["CLI Entry (src/main.rs)"]
        CMD["Commands"]
        CMD --> SCREEN["screen"]
        CMD --> RUN["run<br/>(全流水线)"]
        CMD --> REVIEW["review"]
        CMD --> RL["review-list"]
        CMD --> RM["review-merge"]
        CMD --> CHART["chart"]
        CMD --> CI["clean-intraday"]
    end

    %% ── screen 子命令 ──
    SCREEN --> SCR["run_screen_with_loader()<br/>src/screening.rs"]
    SCR --> POOL{"pool_source"}
    POOL -->|turnover-top| TOP["fetch turnover_top N<br/>from PostgreSQL"]
    POOL -->|custom| POOLF["读取 pool_file"]
    TOP --> WINDOW["fetch_daily_window()<br/>366 天行情窗口<br/>src/db.rs"]
    POOLF --> WINDOW
    WINDOW --> LOCAL["enrich_local_market_factors()<br/>boll_width / bias / roc / mtm / psy / wr"]
    LOCAL --> IND["计算技术指标<br/>KDJ / MACD / Bollinger / ZX"]
    IND --> PREP["write_prepared_cache()<br/>→ runtime/prepared/"]
    PREP --> STRAT{"策略筛选"}
    STRAT -->|b2| B2STRAT["run_b2_strategy_from_refs()<br/>src/strategies/b2.rs"]
    STRAT -->|b3| B3STRAT["run_b3_strategy_from_refs()<br/>src/strategies/b3.rs"]
    STRAT -->|lsh| LSHSTRAT["run_lsh_strategy_from_refs()<br/>src/strategies/lsh.rs"]
    B2STRAT --> CAND["candidates JSON<br/>→ runtime/candidates/"]
    B3STRAT --> CAND
    LSHSTRAT --> CAND
    CAND --> EXP{"--export-factors"}
    EXP -->|yes| EFACT["build_candidate_factor_rows_from_refs()<br/>→ runtime/factors/"]
    EXP -->|no| SDONE["screen 完成"]

    %% ── intraday 路径 ──
    SCREEN -.->|intraday| RT["TushareRestProvider<br/>fetch_rt_k() 实时快照<br/>src/intraday.rs"]
    RT --> IWINDOW["build_intraday_market_rows()"]
    IWINDOW -.-> PREP

    %% ── run 全流水线 ──
    RUN --> RPICK["resolve_pick_date()"]
    RPICK --> ASCREEN["auto-screen<br/>ScreenRequest{export_factors:false}"]
    ASCREEN --> CAND
    ASCREEN --> ENV["resolve_command_environment()<br/>src/environment.rs"]
    ENV --> ENVEVAL{"手动指定?"}
    ENVEVAL -->|manual_state| MREC["upsert manual EnvironmentRecord"]
    ENVEVAL -->|自动| EVAL["ensure_market_environment()<br/>上证/国证2000 评分<br/>→ weak / neutral / strong"]
    EVAL --> PERSIST["persist → runtime/environment/daily/"]
    MREC --> ENVDONE["ResolvedEnvironment"]
    PERSIST --> ENVDONE

    ENVDONE --> SEL["run_selection()<br/>src/engine/run.rs"]

    subgraph SELECTION["Selection Engine"]
        SEL --> MART["resolve_method_model_artifacts()<br/>→ runtime/models/{method}/"]
        MART --> LOADM["load_model()<br/>LightGbmRuntimeModel<br/>src/engine/inference.rs"]
        LOADM --> RCAND["read_candidates()"]
        RCAND --> INJENV["inject_environment_factor()"]
        INJENV --> INJPREP["inject_prepared_history()"]
        INJPREP --> PCACHE["load factor_rows from<br/>prepared cache 或<br/>recompute"]
        PCACHE --> FACTROW["FactorRow 计算<br/>src/factors/registry.rs"]

        subgraph FACTORS["Factor Registry"]
            FACTROW --> BUNDLE{"method → FactorBundle"}
            BUNDLE -->|b2| B2F["RawCommon + B2ChipAge + B2Semantic"]
            BUNDLE -->|b3| B3F["RawCommon + B3Semantic"]
            BUNDLE -->|lsh| LSHF["RawCommon + LshSemantic"]
            B2F --> COMMON["RawCommon 因子<br/>macd / ma_support / volume_turnover<br/>price_position / bar_shape<br/>range_compression / zx_pullback<br/>abnormal_volume / volume_shrink"]
            B2F --> CHIP["B2ChipAge<br/>chip_age_summary"]
            B2F --> B2SEM["B2Semantic<br/>语义因子"]
            B3F --> COMMON
            B3F --> B3SEM["B3Semantic<br/>语义因子"]
            LSHF --> COMMON
            LSHF --> LSHSEM["LshSemantic<br/>语义因子"]
        end

        FACTROW --> WRFACT["write_factor_artifact()<br/>→ runtime/select/.../factors.json"]
        WRFACT --> RANK["rank_candidates()"]
        RANK --> FVEC["build_feature_vector()<br/>按 model_metadata 特征顺序"]
        FVEC --> PRED["LightGbmRuntimeModel.predict()<br/>num_threads=1"]
        PRED --> SORT["sort by model_score ↓ → assign model_rank"]
        SORT --> DROW["display_rows()<br/>merge name/industry"]
    end

    DROW --> WART["write artifacts<br/>run.json / candidates.json<br/>factors.json / ranked.json<br/>display.json / feature_vectors.json"]

    WART --> CHARTBLK["write_chart_artifacts()"]
    CHARTBLK --> CHIST["load_chart_histories()<br/>从 prepared cache 取日线"]
    CHIST --> CPAYLOAD["write_chart_payloads()<br/>分批 JSON payload"]
    CPAYLOAD --> CREND["run_chart_renderers()<br/>uv run scripts/render_charts.py<br/>→ runtime/charts/{date}.{method}/"]

    CREND --> REVBLK["write_review_task_artifacts()"]
    REVBLK --> LLMT["→ llm_tasks.json<br/>含 chart_path / 复盘提示"]

    %% ── LLM 复盘回路 ──
    LLMT -.-> SUBAGENT["子代理复盘<br/>逐票填 annotation"]
    SUBAGENT -.-> LLMANN["→ llm_annotations.json"]
    LLMANN -.-> RMERGE["review-merge"]
    RMERGE -.-> HTML["生成 llm_report.html<br/>图文复盘报告"]

    %% ── Styles ──
    style CLI fill:#1a1a2e,stroke:#16213e,color:#eee
    style SELECTION fill:#0f3460,stroke:#16213e,color:#eee
    style FACTORS fill:#16213e,stroke:#0f3460,color:#eee
```

## 数据流

```mermaid
flowchart LR
    PG[("PostgreSQL<br/>daily_market")] --> SC["screening"]
    SC --> CJ["candidates JSON"]

    CJ --> CPI["inject prepared history"]
    CPI --> FP["CandidatePayload<br/>FactorProvider"]
    FP --> FR["FactorRow<br/>(技术指标 + 量价因子)"]

    FR --> BF["build_feature_vector"]
    BF --> LGB["LightGBM predict"]
    LGB --> MS["model_score (f64)"]

    MS --> SORT["sort by score ↓"]
    SORT --> RC["RankedCandidate<br/>model_rank (usize)"]

    RC --> MERGE["merge name / industry"]
    MERGE --> DR["DisplayRow"]
    DR --> RL["display.json<br/>→ review-list"]
```
