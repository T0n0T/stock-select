from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from stock_select.indicators import compute_macd


@dataclass(frozen=True)
class MacdWaveClassification:
    label: str
    passed: bool
    reason: str
    details: dict[str, float | int | bool | str]


def classify_weekly_macd_wave(frame: pd.DataFrame, pick_date: str) -> MacdWaveClassification:
    working = _slice_to_pick(frame, pick_date)
    weekly_close = working.set_index("trade_date")["close"].astype(float).resample("W-FRI").last().dropna()
    macd = compute_macd(pd.DataFrame({"close": weekly_close.to_numpy()}))
    hist = macd["macd_hist"].reset_index(drop=True)
    dif = macd["dif"].reset_index(drop=True)
    dea = macd["dea"].reset_index(drop=True)

    if len(hist) < 8 or _is_churn(hist):
        return MacdWaveClassification("invalid", False, "weekly MACD churn", {"periods": len(hist)})

    bullish = bool(dif.iloc[-1] > dea.iloc[-1])
    latest_hist = float(hist.iloc[-1])
    previous_hist = float(hist.iloc[-2])
    had_pullback = bool((hist < 0).any())
    fading_bullish_impulse = bool(
        len(weekly_close) >= 3
        and latest_hist > 0.0
        and previous_hist > 0.0
        and latest_hist < previous_hist
        and float(weekly_close.iloc[-1]) < float(weekly_close.iloc[-2])
    )

    if bullish and fading_bullish_impulse:
        return MacdWaveClassification("wave2", False, "weekly pullback after prior advance", {})
    if bullish and latest_hist > 0.0 and previous_hist > 0.0 and had_pullback:
        return MacdWaveClassification("wave3", True, "weekly second bullish advance after pullback", {})
    if bullish and latest_hist > 0.0:
        return MacdWaveClassification("wave1", True, "weekly first bullish advance after golden cross", {})
    if not bullish and had_pullback:
        return MacdWaveClassification("wave2", False, "weekly pullback after prior advance", {})
    return MacdWaveClassification("invalid", False, "weekly structure incomplete", {})


def classify_daily_macd_wave(frame: pd.DataFrame, pick_date: str) -> MacdWaveClassification:
    working = _slice_to_pick(frame, pick_date)
    macd = compute_macd(working[["close"]].astype(float))
    hist = macd["macd_hist"].reset_index(drop=True)
    dif = macd["dif"].reset_index(drop=True)
    dea = macd["dea"].reset_index(drop=True)

    if len(hist) < 12 or _is_churn(hist.tail(10)):
        return MacdWaveClassification(
            "invalid",
            False,
            "daily MACD churn",
            {"third_wave_gain": 0.0, "needs_recross": False},
        )

    third_wave_gain = _estimate_third_wave_gain(working["close"].astype(float))
    shrinking_negative = bool(hist.iloc[-1] < 0 and hist.iloc[-2] < 0 and abs(hist.iloc[-1]) < abs(hist.iloc[-2]))
    shrinking_positive = bool(
        len(hist) >= 4
        and hist.iloc[-1] > 0
        and hist.iloc[-2] > 0
        and hist.iloc[-3] > 0
        and float(hist.iloc[-1]) < float(hist.iloc[-2]) < float(hist.iloc[-3])
    )
    converging = bool(abs(dif.iloc[-1] - dea.iloc[-1]) < abs(dif.iloc[-2] - dea.iloc[-2]))
    bullish_now = bool(dif.iloc[-1] > dea.iloc[-1])

    if bullish_now and shrinking_positive and converging:
        if third_wave_gain > 0.30:
            return MacdWaveClassification(
                "invalid",
                False,
                "daily third-wave gain exceeded wave4 allowance",
                {"third_wave_gain": third_wave_gain, "needs_recross": False},
            )
        return MacdWaveClassification(
            "wave2_end",
            True,
            "daily second-wave pullback nearing end",
            {"third_wave_gain": third_wave_gain, "needs_recross": False},
        )

    if bullish_now:
        return MacdWaveClassification(
            "invalid",
            False,
            "daily pullback already re-crossed",
            {"third_wave_gain": third_wave_gain, "needs_recross": False},
        )

    if third_wave_gain > 0.30 and (
        (shrinking_positive and converging) or (shrinking_negative and converging)
    ):
        return MacdWaveClassification(
            "invalid",
            False,
            "daily third-wave gain exceeded wave4 allowance",
            {"third_wave_gain": third_wave_gain, "needs_recross": False},
        )

    if shrinking_negative and converging and third_wave_gain <= 0.30 and third_wave_gain > 0.0:
        return MacdWaveClassification(
            "wave4_end",
            True,
            "daily fourth-wave pullback nearing end",
            {"third_wave_gain": third_wave_gain, "needs_recross": False},
        )
    if shrinking_negative and converging:
        return MacdWaveClassification(
            "wave2_end",
            True,
            "daily second-wave pullback nearing end",
            {"third_wave_gain": third_wave_gain, "needs_recross": False},
        )
    return MacdWaveClassification(
        "invalid",
        False,
        "daily pullback still deteriorating",
        {"third_wave_gain": third_wave_gain, "needs_recross": False},
    )


def _slice_to_pick(frame: pd.DataFrame, pick_date: str) -> pd.DataFrame:
    working = frame.copy()
    working["trade_date"] = pd.to_datetime(working["trade_date"])
    working = (
        working.loc[working["trade_date"] <= pd.Timestamp(pick_date)]
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    return working


def _is_churn(hist: pd.Series) -> bool:
    signs = hist.apply(lambda value: 1 if value > 0 else (-1 if value < 0 else 0))
    flips = int((signs != signs.shift(1)).fillna(False).sum())
    return flips >= 4


def _estimate_third_wave_gain(close: pd.Series) -> float:
    recent = close.tail(20).reset_index(drop=True)
    if len(recent) < 8:
        return 0.0
    second_wave_low = float(recent.iloc[:10].min())
    third_wave_high = float(recent.max())
    if second_wave_low <= 0.0:
        return 0.0
    return round(third_wave_high / second_wave_low - 1.0, 4)
