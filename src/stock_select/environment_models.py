from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class MarketEnvironmentInterval:
    state: str
    start_date: str
    end_date: str | None
    evaluated_at: str
    source: str
    manual_override: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
