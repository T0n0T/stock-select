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

    @classmethod
    def from_payload(cls, payload: object) -> "MarketEnvironmentInterval":
        if not isinstance(payload, dict):
            raise ValueError("Invalid environment history payload.")
        return cls(
            state=_require_str(payload, "state"),
            start_date=_require_str(payload, "start_date"),
            end_date=_require_optional_str(payload, "end_date"),
            evaluated_at=_require_str(payload, "evaluated_at"),
            source=_require_str(payload, "source"),
            manual_override=_require_bool(payload, "manual_override"),
            reason=_require_optional_str(payload, "reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError("Invalid environment history payload.")
    return value


def _require_optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid environment history payload.")
    return value


def _require_bool(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError("Invalid environment history payload.")
    return value
