from __future__ import annotations

import pandas as pd


RT_K_COLUMN_MAP = {
    "代码": "code",
    "名称": "name",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "最新价": "close",
    "成交量": "vol",
    "成交额": "amount",
    "更新时间": "trade_time",
}


def _normalize_ts_code(code: str) -> str:
    stripped = code.strip()
    if stripped.endswith((".SZ", ".SH", ".BJ")):
        return stripped
    if stripped.startswith(("0", "2", "3")):
        return f"{stripped}.SZ"
    if stripped.startswith(("6", "9")):
        return f"{stripped}.SH"
    if stripped.startswith(("4", "8")):
        return f"{stripped}.BJ"
    msg = f"Unsupported ts_code: {code}"
    raise ValueError(msg)


def normalize_rt_k_snapshot(raw: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    renamed = raw.rename(columns=RT_K_COLUMN_MAP).copy()
    required = ["code", "name", "open", "high", "low", "close", "vol", "amount", "trade_time"]
    missing = [column for column in required if column not in renamed.columns]
    if missing:
        msg = f"rt_k snapshot missing columns: {missing}"
        raise ValueError(msg)

    normalized = pd.DataFrame(
        {
            "ts_code": renamed["code"].astype(str).map(_normalize_ts_code),
            "name": renamed["name"].astype(str),
            "trade_date": trade_date,
            "trade_time": renamed["trade_time"].astype(str),
            "open": renamed["open"].astype(float),
            "high": renamed["high"].astype(float),
            "low": renamed["low"].astype(float),
            "close": renamed["close"].astype(float),
            "vol": renamed["vol"].astype(float),
            "amount": renamed["amount"].astype(float),
        }
    )
    return normalized.sort_values(["ts_code"]).reset_index(drop=True)


def _require_columns(frame: pd.DataFrame, *, frame_name: str, required: list[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        msg = f"{frame_name} missing columns: {missing}"
        raise ValueError(msg)


def _normalize_trade_date_series(series: pd.Series) -> pd.Series:
    normalized = series.astype(str).str.strip()
    compact_mask = normalized.str.fullmatch(r"\d{8}")
    normalized.loc[compact_mask] = pd.to_datetime(
        normalized.loc[compact_mask],
        format="%Y%m%d",
    ).dt.strftime("%Y-%m-%d")
    normalized.loc[~compact_mask] = pd.to_datetime(normalized.loc[~compact_mask]).dt.strftime("%Y-%m-%d")
    return normalized


def build_intraday_market_frame(
    history: pd.DataFrame,
    snapshot: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    _require_columns(
        history,
        frame_name="history",
        required=["ts_code", "trade_date", "open", "high", "low", "close", "vol"],
    )
    _require_columns(
        snapshot,
        frame_name="snapshot",
        required=["ts_code", "trade_date", "open", "high", "low", "close", "vol"],
    )

    frame = history.copy()
    frame["trade_date"] = _normalize_trade_date_series(frame["trade_date"])
    normalized_trade_date = _normalize_trade_date_series(pd.Series([trade_date])).iloc[0]

    intraday_rows = snapshot[["ts_code", "trade_date", "open", "high", "low", "close", "vol"]].copy()
    intraday_rows["trade_date"] = normalized_trade_date

    frame = frame[
        ~(
            (frame["trade_date"] == normalized_trade_date)
            & (frame["ts_code"].isin(intraday_rows["ts_code"]))
        )
    ]
    combined = pd.concat([frame, intraday_rows], ignore_index=True)
    return combined.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
