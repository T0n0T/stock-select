"""交易退出指标；只使用截至当前 bar 的数据，不复用默认参数的选股 KDJ。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def _tdx_sma(values: "pd.Series", n: int, m: int = 1) -> "pd.Series":
    # 与 src/indicators.rs::tdx_sma 的递推及首值初始化一致。
    return values.fillna(0.0).ewm(alpha=m/n, adjust=False).mean()


def tdx_sell_condition(frame: "pd.DataFrame") -> "pd.Series":
    k, d = frame["exit_kdj_k"], frame["exit_kdj_d"]
    slope = frame["exit_j1"]
    cross = (d > k) & (d.shift(1) <= k.shift(1))
    return (cross & (d > 65) & (slope < frame["exit_mj1"])
            & (slope.gt(1).rolling(3, min_periods=3).sum() >= 1)).fillna(False)


def exit_indicators(frame: "pd.DataFrame") -> "pd.DataFrame":
    result = frame.copy()
    close = result["close"].astype(float)
    ma20 = close.rolling(20, min_periods=20).mean()
    result["exit_ma25"] = close.rolling(25, min_periods=25).mean()
    result["exit_j1"] = (ma20 / ma20.shift(1) - 1) * 100
    result["exit_mj1"] = result["exit_j1"].rolling(3, min_periods=3).mean()
    low = result["low"].rolling(5, min_periods=1).min()
    high = result["high"].rolling(5, min_periods=1).max()
    rsv = ((close-low) / (high-low).replace(0, float("nan")) * 100).fillna(0.0)
    result["exit_kdj_k"] = _tdx_sma(rsv, 2)
    result["exit_kdj_d"] = _tdx_sma(result["exit_kdj_k"], 3)
    result["exit_tdx_sell"] = tdx_sell_condition(result)
    return result
