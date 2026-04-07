# Stock Select Insufficient History Breakdown Design

## Goal

让 `stock-select screen` 在 B1 筛选时把“历史长度不足，无法计算 `zxdkx`”与“`close <= zxdkx` 的真实失败”区分开，避免误导性 breakdown。

## Scope

包含：

- 在筛选统计中新增 `fail_insufficient_history`
- 在 `zxdkx` 缺失时优先计入历史不足失败
- 在 CLI `breakdown` 输出中展示新字段
- 更新测试覆盖该行为
- 将 README 改为中文，并补充历史长度要求说明

不包含：

- 修改 B1 策略公式
- 放宽 `zxdkx` 的计算窗口
- 自动补写数据库历史数据

## Design

当前 `zxdkx` 由 `14/28/57/114` 四条均线平均得到，最后一条均线要求至少 `114` 个交易日，因此目标日 `zxdkx` 为 `NaN` 时，说明当前缓存窗口不足以支持该条件判断。

筛选顺序保持不变，但在 `close > zxdkx` 之前增加一条历史完整性判断：

- 若目标日 `zxdkx` 为 `NaN`，计入 `fail_insufficient_history`
- 只有目标日 `zxdkx` 可用时，才判断 `close > zxdkx`

这样 `fail_close_zxdkx` 将只表示“均线已算出，但收盘价未站上 `zxdkx`”，而不再混入数据窗口不足的样本。

## Behavior

- `breakdown` 新增 `fail_insufficient_history=<n>`
- 历史不足股票仍计入 `eligible`
- 历史不足股票不会继续进入后续条件
- README 明确说明：
  - `screen` 默认拉取目标日前 366 天窗口
  - 若缓存中的实际连续交易历史不足 `114` 个交易日，`zxdkx` 会缺失
  - 此类股票会被统计为 `fail_insufficient_history`

## Verification

- 单元测试覆盖 `zxdkx` 缺失时的统计归类
- CLI 测试覆盖 `breakdown` 输出新字段
- 相关测试通过
