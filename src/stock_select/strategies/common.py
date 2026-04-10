from __future__ import annotations

import pandas as pd


def ensure_volume_column(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "volume" not in out.columns and "vol" in out.columns:
        out["volume"] = out["vol"]
    return out
