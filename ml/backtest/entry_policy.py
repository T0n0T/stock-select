from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from math import isfinite
from pathlib import Path
from typing import Mapping

from .signal_bundle import normalize_date


@dataclass(frozen=True)
class EntryRule:
    """New-batch permission and budget; existing batches keep their exit rules."""

    allow_new_positions: bool = True
    daily_equity_fraction: float | None = None

    def __post_init__(self) -> None:
        if type(self.allow_new_positions) is not bool:
            raise ValueError("allow_new_positions must be a boolean")
        fraction = self.daily_equity_fraction
        if fraction is not None and (
            isinstance(fraction, bool) or not isinstance(fraction, (int, float))
            or not isfinite(fraction) or not 0 <= fraction <= 1
        ):
            raise ValueError("daily_equity_fraction must be between zero and one")


@dataclass(frozen=True)
class EntryDecision:
    environment: str | None
    allow_new_positions: bool
    daily_equity_fraction: float
    reason: str


@dataclass(frozen=True)
class EntryPolicy:
    name: str = "always-enter"
    default: EntryRule = field(default_factory=EntryRule)
    by_environment: Mapping[str, EntryRule] = field(default_factory=dict)

    def decide(self, day: str, environment: str | None, *, default_fraction: float) -> EntryDecision:
        if self.by_environment:
            if environment not in self.by_environment:
                raise ValueError(f"{day}: missing or unconfigured environment {environment!r}")
            rule = self.by_environment[environment]
            reason = f"{self.name}:environment={environment}"
        else:
            rule = self.default
            reason = f"{self.name}:default"
        fraction = rule.daily_equity_fraction
        if fraction is None:
            fraction = default_fraction
        allowed = rule.allow_new_positions and fraction > 0
        return EntryDecision(environment, allowed, float(fraction) if allowed else 0.0, reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "default": asdict(self.default),
            "by_environment": {environment: asdict(rule) for environment, rule in self.by_environment.items()},
        }


def load_entry_policy(path: Path) -> EntryPolicy:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("entry policy must be a JSON object")
    unknown = raw.keys() - {"name", "default", "by_environment"}
    if unknown:
        raise ValueError(f"unknown entry policy fields: {sorted(unknown)}")

    def rule(value: object) -> EntryRule:
        if not isinstance(value, dict):
            raise ValueError("entry rule must be a JSON object")
        unknown = value.keys() - {"allow_new_positions", "daily_equity_fraction"}
        if unknown:
            raise ValueError(f"unknown entry rule fields: {sorted(unknown)}")
        return EntryRule(**value)

    environments = raw.get("by_environment", {})
    if not isinstance(environments, dict) or any(not key.strip() for key in environments):
        raise ValueError("by_environment must map nonempty environment names to rules")
    name = raw.get("name", path.stem)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("entry policy name must be nonempty")
    return EntryPolicy(
        name=name,
        default=rule(raw.get("default", {})),
        by_environment={environment: rule(value) for environment, value in environments.items()},
    )


def load_daily_environments(path: Path) -> dict[str, str]:
    """Read signal-date context, accepting repeated candidate rows per day."""
    environments: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        if not {"date", "env"}.issubset(rows.fieldnames or []):
            raise ValueError("daily context requires date and env columns")
        for row in rows:
            day = normalize_date(row["date"])
            environment = (row["env"] or "").strip()
            if not environment:
                raise ValueError(f"{day}: missing environment")
            if day in environments and environments[day] != environment:
                raise ValueError(f"conflicting environments for {day}")
            environments[day] = environment
    return environments
