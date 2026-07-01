from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def artifact_key_for_date(pick_date: str, *, intraday: bool = False) -> str:
    return f"{pick_date}.intraday" if intraday else pick_date


def candidate_path(runtime_root: Path, pick_date: str, method: str, *, intraday: bool = False) -> Path:
    artifact_key = artifact_key_for_date(pick_date, intraday=intraday)
    return runtime_root / "candidates" / f"{artifact_key}.{method}.json"


def factor_artifact_path(runtime_root: Path, pick_date: str, method: str, *, intraday: bool = False) -> Path:
    artifact_key = artifact_key_for_date(pick_date, intraday=intraday)
    return runtime_root / "factors" / f"{artifact_key}.{method}" / "factors.json"


def select_dir(runtime_root: Path, pick_date: str, method: str, *, intraday: bool = False) -> Path:
    artifact_key = artifact_key_for_date(pick_date, intraday=intraday)
    return runtime_root / "select" / f"{artifact_key}.{method}"
