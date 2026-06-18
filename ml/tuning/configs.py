from __future__ import annotations

from typing import Any


def training_kwargs_from_trial(trial: dict[str, Any]) -> dict[str, Any]:
    return dict(trial)
