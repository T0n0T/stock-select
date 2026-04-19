from __future__ import annotations

import pandas as pd


def compute_macd(
    df: pd.DataFrame,
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    close = df["close"].astype(float)
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_hist = dif - dea
    return pd.DataFrame({"dif": dif, "dea": dea, "macd_hist": macd_hist}, index=df.index)
