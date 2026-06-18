from __future__ import annotations

import signal
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CommandFailure:
    key: str
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class CommandBatchResult:
    total_count: int
    success_count: int = 0
    dry_run_count: int = 0
    failures: list[CommandFailure] = field(default_factory=list)


def format_returncode(returncode: int) -> str:
    if returncode >= 0:
        return f"rc={returncode}"
    signum = -returncode
    try:
        signal_name = signal.Signals(signum).name
    except ValueError:
        signal_name = str(signum)
    return f"signal={signal_name}"


def run_command(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), cwd=cwd, text=True, capture_output=True, check=False)
