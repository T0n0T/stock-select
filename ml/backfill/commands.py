from __future__ import annotations

from pathlib import Path


def build_screen_command(
    *,
    binary: Path,
    pick_date: str,
    runtime_root: Path,
    method: str,
    recompute: bool,
    pool_source: str,
    export_factors: bool,
) -> list[str]:
    command = [
        str(binary),
        "screen",
        "--method",
        method,
        "--pick-date",
        pick_date,
        "--runtime-root",
        str(runtime_root),
        "--pool-source",
        pool_source,
    ]
    if recompute:
        command.append("--recompute")
    if export_factors:
        command.append("--export-factors")
    return command


def build_run_command(
    *,
    binary: Path,
    pick_date: str,
    runtime_root: Path,
    method: str,
    recompute: bool,
    pool_source: str,
) -> list[str]:
    command = [
        str(binary),
        "run",
        "--method",
        method,
        "--pick-date",
        pick_date,
        "--runtime-root",
        str(runtime_root),
        "--pool-source",
        pool_source,
    ]
    if recompute:
        command.append("--recompute")
    return command
