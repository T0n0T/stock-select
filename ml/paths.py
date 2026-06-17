from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def candidate_path(runtime_root: Path, pick_date: str, method: str) -> Path:
    return runtime_root / "candidates" / f"{pick_date}.{method}.json"


def factor_artifact_path(runtime_root: Path, pick_date: str, method: str) -> Path:
    return runtime_root / "factors" / f"{pick_date}.{method}" / "factors.json"


def select_dir(runtime_root: Path, pick_date: str, method: str) -> Path:
    return runtime_root / "select" / f"{pick_date}.{method}"
