from __future__ import annotations

import pandas as pd
import pytest

from stock_select.intraday import build_intraday_market_frame, normalize_rt_k_snapshot


def test_normalize_rt_k_snapshot_maps_required_columns() -> None:
    raw = pd.DataFrame(
        [
            {
                "代码": "000001",
                "名称": "平安银行",
                "开盘价": 12.1,
                "最高价": 12.5,
                "最低价": 12.0,
                "最新价": 12.34,
                "成交量": 1234567,
                "成交额": 152300000.0,
                "更新时间": "11:31:07",
            }
        ]
    )

    normalized = normalize_rt_k_snapshot(raw, trade_date="2026-04-09")

    assert list(normalized.columns) == [
        "ts_code",
        "name",
        "trade_date",
        "trade_time",
        "open",
        "high",
        "low",
        "close",
        "vol",
        "amount",
    ]
    assert normalized.iloc[0]["ts_code"] == "000001.SZ"
    assert normalized.iloc[0]["close"] == 12.34


def test_build_intraday_market_frame_appends_current_day_bar() -> None:
    history = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-07",
                "open": 11.8,
                "high": 12.0,
                "low": 11.7,
                "close": 11.9,
                "vol": 100.0,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-08",
                "open": 11.9,
                "high": 12.1,
                "low": 11.8,
                "close": 12.0,
                "vol": 120.0,
            },
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "trade_date": "2026-04-09",
                "trade_time": "11:31:07",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "vol": 150.0,
                "amount": 999.0,
            }
        ]
    )

    combined = build_intraday_market_frame(history, snapshot, trade_date="2026-04-09")

    assert list(combined["trade_date"].astype(str))[-1] == "2026-04-09"
    assert float(combined.iloc[-1]["close"]) == 12.34
    assert float(combined.iloc[-1]["vol"]) == 150.0


def test_build_intraday_market_frame_replaces_existing_same_day_bar() -> None:
    history = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": 20260408,
                "open": 11.9,
                "high": 12.1,
                "low": 11.8,
                "close": 12.0,
                "vol": 120.0,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": 20260409,
                "open": 12.0,
                "high": 12.2,
                "low": 11.9,
                "close": 12.05,
                "vol": 130.0,
            },
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "trade_date": "2026-04-09",
                "trade_time": "11:31:07",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "vol": 150.0,
                "amount": 999.0,
            }
        ]
    )

    combined = build_intraday_market_frame(history, snapshot, trade_date="2026-04-09")

    assert combined.to_dict(orient="records") == [
        {
            "ts_code": "000001.SZ",
            "trade_date": "2026-04-08",
            "open": 11.9,
            "high": 12.1,
            "low": 11.8,
            "close": 12.0,
            "vol": 120.0,
        },
        {
            "ts_code": "000001.SZ",
            "trade_date": "2026-04-09",
            "open": 12.1,
            "high": 12.5,
            "low": 12.0,
            "close": 12.34,
            "vol": 150.0,
        },
    ]


def test_build_intraday_market_frame_normalizes_compact_trade_date_argument() -> None:
    history = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-08",
                "open": 11.9,
                "high": 12.1,
                "low": 11.8,
                "close": 12.0,
                "vol": 120.0,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-09",
                "open": 12.0,
                "high": 12.2,
                "low": 11.9,
                "close": 12.05,
                "vol": 130.0,
            },
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "trade_date": "2026-04-09",
                "trade_time": "11:31:07",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "vol": 150.0,
                "amount": 999.0,
            }
        ]
    )

    combined = build_intraday_market_frame(history, snapshot, trade_date=20260409)

    assert combined.to_dict(orient="records") == [
        {
            "ts_code": "000001.SZ",
            "trade_date": "2026-04-08",
            "open": 11.9,
            "high": 12.1,
            "low": 11.8,
            "close": 12.0,
            "vol": 120.0,
        },
        {
            "ts_code": "000001.SZ",
            "trade_date": "2026-04-09",
            "open": 12.1,
            "high": 12.5,
            "low": 12.0,
            "close": 12.34,
            "vol": 150.0,
        },
    ]


def test_build_intraday_market_frame_validates_required_history_columns() -> None:
    history = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-08",
                "open": 11.9,
                "high": 12.1,
                "low": 11.8,
                "close": 12.0,
            }
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-09",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "vol": 150.0,
            }
        ]
    )

    with pytest.raises(ValueError, match=r"history missing columns: \['vol'\]"):
        build_intraday_market_frame(history, snapshot, trade_date="2026-04-09")


def test_build_intraday_market_frame_validates_required_snapshot_columns() -> None:
    history = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-08",
                "open": 11.9,
                "high": 12.1,
                "low": 11.8,
                "close": 12.0,
                "vol": 120.0,
            }
        ]
    )
    snapshot = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2026-04-09",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
            }
        ]
    )

    with pytest.raises(ValueError, match=r"snapshot missing columns: \['vol'\]"):
        build_intraday_market_frame(history, snapshot, trade_date="2026-04-09")
