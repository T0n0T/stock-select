from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class CandidateRecord:
    code: str
    pick_date: str
    method: str
    close: float
    turnover_n: float
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


@dataclass
class CandidateRun:
    pick_date: str
    method: str
    candidates: list[CandidateRecord]
    config: dict[str, Any]
    query: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pick_date": self.pick_date,
            "method": self.method,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "config": self.config,
            "query": self.query,
        }


@dataclass
class ReviewRecord:
    code: str
    pick_date: str
    decision: str
    signal_type: str
    comment: str
    score: float
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
