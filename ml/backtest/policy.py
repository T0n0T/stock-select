from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Mapping

from .entry_policy import EntryDecision


@dataclass(frozen=True)
class HoldingAction:
    """Portfolio action produced for one trading day."""

    enter: tuple[str, ...] = ()
    exit: tuple[str, ...] = ()
    holding_day: int = 0
    reason: str = ""
    expired_signal_dates: tuple[str, ...] = ()
    entry_decision: EntryDecision | None = None


class TopNHoldPolicy:
    """Select ranked symbols and hold them for a fixed number of trading days.

    Each signal day creates a batch. Batches overlap and expire independently
    after ``holding_days`` trading sessions.
    """

    def __init__(self, top_n: int = 3, holding_days: int = 3) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be greater than zero")
        if holding_days <= 0:
            raise ValueError("holding_days must be greater than zero")
        self.top_n = int(top_n)
        self.holding_days = int(holding_days)
        self._batches: list[tuple[str, tuple[str, ...], int]] = []

    @property
    def held_symbols(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(symbol for _day, symbols, _age in self._batches for symbol in symbols)
        )

    @property
    def holding_day(self) -> int:
        return max((age for _day, _symbols, age in self._batches), default=0)

    def on_trading_day(
        self,
        trading_date: str,
        ranked_rows: Iterable[tuple[str, float] | tuple[str, float, int] | Mapping[str, object]],
    ) -> HoldingAction:
        aged = [(day, symbols, age + 1) for day, symbols, age in self._batches]
        expired = [(day, symbols, age) for day, symbols, age in aged if age >= self.holding_days]
        self._batches = [batch for batch in aged if batch[2] < self.holding_days]
        selected = self._select(ranked_rows)
        entered = tuple(code for code, _score in selected)
        if entered:
            self._batches.append((trading_date, entered, 0))

        active = self.held_symbols
        active_set = set(active)
        exited = tuple(
            dict.fromkeys(
                symbol for _day, symbols, _age in expired
                for symbol in symbols if symbol not in active_set
            )
        )
        expired_holding_day = max((age for _day, _symbols, age in expired), default=0)
        expired_signal_dates = tuple(day for day, _symbols, _age in expired)
        if not active:
            return HoldingAction(
                exit=exited,
                holding_day=expired_holding_day,
                reason="holding_days_reached" if exited else "no_signal",
                expired_signal_dates=expired_signal_dates,
            )
        return HoldingAction(
            enter=entered,
            exit=exited,
            holding_day=expired_holding_day or self.holding_day,
            reason="rollover" if expired else ("enter" if entered else "holding"),
            expired_signal_dates=expired_signal_dates,
        )

    def _select(
        self,
        ranked_rows: Iterable[tuple[str, float] | tuple[str, float, int] | Mapping[str, object]],
    ) -> list[tuple[str, float]]:
        normalized: list[tuple[str, float, int | None]] = []
        for row in ranked_rows:
            if isinstance(row, Mapping):
                code = str(row.get("code") or "").strip()
                score_value = row.get("model_score", 0.0)
                rank_value = row.get("model_rank")
            else:
                if len(row) < 2:
                    continue
                code = str(row[0]).strip()
                score_value = row[1]
                rank_value = row[2] if len(row) > 2 else None
            if not code:
                continue
            try:
                score = float(score_value)
            except (TypeError, ValueError):
                score = 0.0
            if not isfinite(score):
                score = 0.0
            try:
                rank = int(rank_value) if rank_value is not None else None
            except (TypeError, ValueError):
                rank = None
            normalized.append((code, score, rank))

        if any(rank is not None for _code, _score, rank in normalized):
            normalized.sort(
                key=lambda item: (
                    item[2] if item[2] is not None else 2**31,
                    -item[1],
                    item[0],
                )
            )
        else:
            normalized.sort(key=lambda item: (-item[1], item[0]))
        unique: list[tuple[str, float]] = []
        seen: set[str] = set()
        for code, score, _rank in normalized:
            if code in seen:
                continue
            seen.add(code)
            unique.append((code, score))
            if len(unique) == self.top_n:
                break
        return unique
