# Review HTML 站点与 Serve 子命令设计

## 目标

为当前 review 结果增加一套可直接通过本地 HTTP 访问的静态 HTML 站点能力，并把现有混合在 `render-html` 中的职责拆分为独立子命令。

本次设计要解决三个具体问题：

- 让用户可以用一个简单的 `serve` 命令直接暴露整个 `runtime/reviews/` 对应的展示站点，而不是只看单日报告文件。
- 升级当前单日 HTML 报告的导航结构，用现有 `PASS` / `WATCH` / `FAIL` 与总分 `score` 的范围来区分当天股票结果。
- 将当前 HTML 生成、HTML 打包、HTML 服务拆分成清晰的子命令，避免一个命令承担过多职责。

## 范围

包含：

- 新增 `html` 命名空间子命令
- 生成多天索引页与单日报告页
- 将单日报告导航升级为 verdict 分组和 score 分桶导航
- 新增静态文件服务命令，用于暴露整个 review HTML 站点
- 将 ZIP 打包从渲染流程中拆出
- 保留旧 `render-html` 的兼容入口，并输出废弃提示
- 同步更新 README 与 `stock-select` skill，使文档与新命令结构一致

不包含：

- 修改 `review`、`review-merge`、打分逻辑或 verdict 规则
- 引入前端框架、模板引擎或数据库查询驱动的动态页面
- 在 `serve` 启动时动态生成页面
- 增加新的评分等级体系

## 当前状态

当前仓库已具备这些能力：

- `review` / `review-merge` 会在 `runtime/reviews/<pick_date>.<method>/summary.json` 生成单日汇总产物
- `src/stock_select/html_export.py` 可以从单个 `summary.json` 生成 `summary.html`，并复制图表、打包 zip
- CLI 里只有一个 `render-html` 命令，它同时负责：
  - 读取 review summary
  - 拉取股票名称
  - 生成 HTML
  - 复制图表
  - 生成 zip
- 仓库中已有一份 `serve` 设计，但它的目标是暴露某个 `charts/<pick_date>/` 目录，并不覆盖 review HTML 站点

这意味着当前展示能力仍然偏“单日报告导出”，而不是“多天浏览站点”。此外，`render-html` 的职责边界也已经偏重，不适合直接扩成多天入口和静态站点服务。

## 设计原则

本次设计遵守以下边界：

- review 原始产物与 HTML 展示产物分离
- HTML 站点完全静态，可离线打开，也可经 HTTP 服务暴露
- `render`、`zip`、`serve` 三类动作各自独立，不互相隐式触发
- 导航只使用现有业务字段：`verdict` 和总分 `score`
- 缺少辅助资源时优先降级展示，不改变 review 数据本身

## 方案比较

### 方案 A：保留 `render-html` 单命令，仅做内部重构

做法：继续使用 `render-html`，内部再拆函数，额外加一个 `serve`。

优点：

- 对现有调用方最兼容
- CLI 改动表面较小

缺点：

- `render-html` 语义仍然混合渲染与打包
- 新增多天首页后职责会更混乱
- 后续文档和自动化流程依然不够清楚

### 方案 B：新增 `html` 子命令组，分别提供 `render`、`zip`、`serve`

做法：将 HTML 能力整理为 `stock-select html render`、`stock-select html zip`、`stock-select html serve`，旧 `render-html` 保留兼容入口。

优点：

- 命令职责最清晰
- 适合“先生成站点，再打包，再服务”的静态产物模式
- 最适合支持多天入口

缺点：

- CLI 文档与测试需要更新
- 兼容层需要额外维护一段时间

### 方案 C：只新增 `serve`，在 HTTP 请求时动态拼装多天索引与单日报告

做法：不额外落盘站点产物，服务端在请求时读取 summary 目录并即时输出页面。

优点：

- 初始落盘文件更少
- 似乎可以少做一层“站点构建”

缺点：

- 页面逻辑与服务逻辑耦合
- 无法自然支持离线打包和直接打开 HTML
- 与仓库现有“运行产物先落盘”的模式不一致

## 选定方案

采用方案 B。

原因：

- 用户明确希望直接用 `serve` 暴露整个 review 目录的展示结果。
- 当前需求同时包含“生成 HTML”、“ZIP 打包”、“本地服务”，这三件事天然应当拆开。
- 站点一旦采用静态产物结构，后续无论离线查看、归档、分享，还是通过本地 HTTP 查看，都能沿用同一套目录布局。

## CLI 设计

新增一个 `html` 子应用，命令形态如下：

```bash
stock-select html render --method <method> --pick-date YYYY-MM-DD
stock-select html zip --method <method> --pick-date YYYY-MM-DD
stock-select html serve --host 127.0.0.1 --port 8000
```

### `html render`

职责：

- 读取 `runtime/reviews/<pick_date>.<method>/summary.json`
- 解析引用的图表与股票名称
- 生成单日报告页
- 同步复制该日报告所需的 `summary.json` 与 `charts/*.png`
- 重建多天索引页

输出：

- stdout 输出单日报告 HTML 路径

### `html zip`

职责：

- 打包已经生成好的单日报告站点目录
- 不重新渲染 HTML

输出：

- stdout 输出 zip 路径

前置条件：

- 对应的单日报告站点目录必须已由 `html render` 生成

### `html serve`

职责：

- 直接服务整个 review HTML 站点根目录
- 默认首页为多天索引页
- 不参与渲染、不参与打包

输出：

- 启动后打印基础 URL，例如 `http://127.0.0.1:8000/`
- 进程持续运行直到被中断

### 兼容入口 `render-html`

旧命令保留，但只作为兼容层：

- 内部复用新实现完成渲染与打包
- 输出 deprecation 提示，指导迁移到：
  - `stock-select html render`
  - `stock-select html zip`

这样可以避免立即打断现有自动化或个人习惯，同时把新结构建立起来。

## 文档与 Skill 同步

本次变更不能只改 CLI 与代码实现，必须同步更新仓库内对外说明，避免 agent 继续沿用旧命令。

需要同步更新的内容包括：

- `README.md`
- `.agents/skills/stock-select/SKILL.md`

### README 更新要求

README 中所有与 HTML 导出相关的说明都需要改成新的命令结构：

- 将原先“`render-html` 直接生成 shareable zip”的描述改为：
  - `html render` 负责生成站点与单日报告
  - `html zip` 负责打包单日报告
  - `html serve` 负责暴露整个站点
- 明确多天首页位于 `runtime/reviews/site/index.html`
- 明确 `serve` 服务的是站点目录，而不是原始 review 目录或 charts 目录
- 如保留 `render-html` 兼容层，README 需要标注其为过渡入口

### Skill 更新要求

`stock-select` skill 中涉及 HTML 输出的工作流也必须改写，否则后续 agent 仍会默认走旧命令。

需要调整的点：

- 将“需要 shareable offline report 时运行 CLI `render-html` after `review-merge`”改为新的三段式能力说明
- 明确 HTML 相关命令为：
  - `stock-select html render`
  - `stock-select html zip`
  - `stock-select html serve`
- 明确 `html render` 会生成多天索引页与单日报告目录
- 明确 `html zip` 仅打包已渲染目录，不隐式触发渲染
- 明确 `html serve` 用于暴露整个 review HTML 站点
- 如果保留 `render-html` 兼容层，skill 中只能把它描述为兼容入口，不能再作为首选工作流

这样做的目的是保证：

- 人工使用 CLI 时，文档与真实行为一致
- 后续 agent 使用 skill 时，不会继续生成已经过时的命令建议

## 目录结构设计

原始 review 产物继续保留在：

```text
runtime/reviews/<pick_date>.<method>/summary.json
```

新增一个专门的 HTML 站点目录：

```text
runtime/reviews/site/
runtime/reviews/site/index.html
runtime/reviews/site/<pick_date>.<method>/index.html
runtime/reviews/site/<pick_date>.<method>/summary.json
runtime/reviews/site/<pick_date>.<method>/charts/*.png
runtime/reviews/site/<pick_date>.<method>/summary-package.zip
```

这样划分的理由：

- `runtime/reviews/` 仍然是 review 原始产物区
- `runtime/reviews/site/` 作为纯展示产物区，可以直接由静态文件服务器暴露
- `html zip` 只需打包 `site/<pick_date>.<method>/` 即可
- 不会把 HTML、图表副本和原始 review JSON 混写到同一目录层级

## 多天首页设计

多天首页位于：

```text
runtime/reviews/site/index.html
```

它展示所有已经执行过 `html render` 的单日报告入口，按日期倒序排列，每个卡片代表一个 `<pick_date>.<method>`。

每个卡片至少展示：

- `pick_date`
- `method`
- `reviewed_count`
- `PASS` 数量
- `WATCH` 数量
- `FAIL` 数量
- 最高分
- 最低分
- 进入单日报告的链接

这里不强行聚合同一天不同方法的结果。若存在：

- `2026-05-01.b1`
- `2026-05-01.b2`

则首页展示为两个独立入口。

这样最直接，也最符合当前 runtime 目录本身就以 `<pick_date>.<method>` 为粒度的设计。

## 单日报告导航设计

单日报告继续保留当前卡片式明细阅读模式，但顶部导航需要升级成两类区分：

- 按 `verdict` 分组
- 按总分 `score` 分桶

### Verdict 导航

导航中固定包含这三类入口：

- `PASS`
- `WATCH`
- `FAIL`

点击后跳转到页面内对应分区。

### Score 导航

不引入新的业务等级命名，只按现有分值做范围桶。推荐固定使用四档：

- `>= 4.5`
- `4.0 - 4.49`
- `3.0 - 3.99`
- `< 3.0`

原因：

- 当前总分本身就是 0 到 5 的体系
- 这四档能区分高置信、边界、观察和明显弱势结果
- 不会发明额外的领域标签，仍然只是对现有 score 做可视化组织

### Score 取值规则

单条记录的 score 取值优先级固定为：

1. `final_score`
2. `total_score`

如果两者都缺失，则该条记录：

- 仍保留在 verdict 分组中显示
- 不进入 score 分桶统计
- 在展示层标记为不可用分数

## 单日报告内容设计

单日报告仍然以当前 summary 内容为数据源，并继续包含：

- 顶部概览指标
- `PASS` / `WATCH` / `FAIL` 分组结果
- 每只股票的卡片详情
- 基线 review / LLM review 的打分拆解
- reasoning 文本
- 图表预览

但结构上做两点增强：

### 1. 明确展示三类 verdict 区域

当前 `summary.json` 中只有：

- `recommendations`
- `excluded`

展示层需要根据每条记录里的 `verdict` 再细分出：

- `PASS`
- `WATCH`
- `FAIL`

也就是说，即使原始 summary 只有 “推荐 / 排除” 两大类，HTML 页面仍会重新组织为三类 verdict 分区。

### 2. 增加 score 区间导航与统计块

页面头部或导航旁边增加 score 范围统计，显示每个区间有多少只股票。点击后可跳到对应锚点或对应分组清单。

这里不要求把每只股票在页面上复制两遍。推荐做法是：

- 主内容仍按 `PASS/WATCH/FAIL` 展开
- 导航区域单独展示 score 区间统计与锚点
- 每张卡片显示自己的 score 区间标签

这样能兼顾可读性与实现复杂度，不会出现同一只股票在页面中重复渲染两次的问题。

## 数据与渲染边界

HTML 站点层只消费已有 review 产物，不修改任何上游数据。

需要保持的容错行为：

- `llm_review` 缺失时，仍可正常渲染
- `final_score` 缺失时，回退到 `total_score`
- 图表文件缺失时，页面显示缺图占位或提示，而不是整体失败
- 文本内容一律 HTML escape

需要保持的失败行为：

- 原始 `summary.json` 缺失时，`html render` 直接失败
- 原始 `summary.json` 非法时，`html render` 直接失败
- `html zip` 找不到站点目录时，直接提示先执行 `html render`
- `html serve` 找不到站点根目录时，直接提示先执行至少一次 `html render`

## Serve 设计

`html serve` 使用标准库静态 HTTP 服务能力即可，不新增第三方依赖。

服务根目录固定为：

```text
runtime/reviews/site/
```

默认参数建议：

- `--host 127.0.0.1`
- `--port 8000`

行为约束：

- 若端口被占用，直接抛出错误，不自动切换端口
- 若首页 `index.html` 不存在，则视为站点尚未生成，报错退出
- 服务逻辑不动态拼接页面，仅服务静态文件

## 实现分层建议

建议将 `src/stock_select/html_export.py` 从“单函数做完所有事情”拆成更清晰的职责层：

- 读取和校验 summary
- 构造单日报告视图模型
- 渲染单日报告 HTML
- 渲染多天首页 HTML
- 同步单日报告站点资源
- 打包单日报告目录为 zip

CLI 层只负责：

- 参数校验
- 调用数据库名称查询
- 调用站点构建 / 打包 / 服务函数
- 输出路径与日志

这样后续如果再扩展 HTML 站点样式或索引筛选逻辑，不需要把代码继续堆在 CLI 中。

## 测试设计

本次需要补充的自动化测试分为三类。

### CLI 测试

覆盖：

- `stock-select html render` 成功生成单日报告并输出路径
- `stock-select html zip` 成功打包已生成目录
- `stock-select html zip` 在目录缺失时失败
- `stock-select html serve` 在站点根缺失时失败
- `stock-select html serve` 成功调用服务 helper，并输出 URL
- 旧 `render-html` 仍可调用，并输出兼容结果与废弃提示

### HTML 导出测试

覆盖：

- 单日报告包含 `PASS` / `WATCH` / `FAIL` 导航入口
- 单日报告包含 score 范围导航文案
- 页面中正确显示 `MACD` 维度及已有 reasoning
- HCR 等方法的标题仍使用实际 method label

### 多天索引测试

覆盖：

- 能汇总多个 `<pick_date>.<method>` 目录
- 按日期倒序展示
- 每张卡片展示 PASS/WATCH/FAIL 统计
- 首页链接指向对应单日报告目录

## 风险与约束

### 兼容风险

旧 `render-html` 当前直接输出 zip 路径。拆分后如果完全删除会破坏现有习惯或脚本，因此必须保留兼容入口至少一个过渡阶段。

### 站点一致性风险

多天首页只会反映已经执行过 `html render` 的报告，而不是扫描所有原始 `summary.json` 自动补建。这个行为必须在文档中说清楚。

这样做是有意的：

- 站点目录只暴露“已渲染完成”的展示产物
- 避免 `serve` 或 `zip` 隐式触发渲染，造成职责不清

### 缺图风险

历史数据目录中可能出现 `summary.json` 在，但图表文件已经被清理或移动的情况。这里应保证页面仍能打开，只是对应卡片缺少预览图。

## 验证标准

当以下条件同时满足时，认为本次设计落地成功：

- 能通过 `stock-select html render` 为某个 `<pick_date>.<method>` 生成单日报告目录
- 能在 `runtime/reviews/site/index.html` 看到多天入口首页
- 单日报告能按 `PASS/WATCH/FAIL` 和 score 范围帮助区分当天股票结果
- 能通过 `stock-select html zip` 打包单日报告目录
- 能通过 `stock-select html serve` 直接暴露整个 review HTML 站点
- 旧 `render-html` 仍然可用，但会引导迁移到新子命令

## 实施顺序建议

建议按以下顺序实施：

1. 重构 `html_export.py`，拆出单日报告构建、索引页构建、站点同步、zip 打包 helper
2. 引入 `html` 子应用和三个子命令
3. 实现静态服务 helper
4. 保留并改造 `render-html` 兼容层
5. 更新测试与 README / skill 文档

这个顺序可以先稳定内部能力边界，再接 CLI，最后处理兼容层和文档。
