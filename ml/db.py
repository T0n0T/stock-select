from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import PROJECT_ROOT


def query_rows(
    source: str, sql: str, params: Sequence[Any], *, binary: str | Path | None = None
) -> list[dict[str, Any]]:
    """Run a read query through the same duckdb-neo client used by screening."""
    configured = str(binary) if binary is not None else resolve_config_value(None, "STOCK_SELECT_BIN", load_dotenv_values())
    if configured:
        resolved_binary = configured if Path(configured).is_file() else shutil.which(configured)
    else:
        candidates = [
            PROJECT_ROOT / "target" / "release" / "stock-select-rs",
            PROJECT_ROOT / "target" / "debug" / "stock-select-rs",
        ]
        existing = [path for path in candidates if path.is_file()]
        resolved_binary = str(max(existing, key=lambda path: path.stat().st_mtime_ns)) if existing else shutil.which("stock-select-rs")
    if resolved_binary is None:
        raise RuntimeError("stock-select-rs not found; build it with cargo build or set STOCK_SELECT_BIN")
    request = json.dumps({"source": source, "sql": sql, "params": list(params)}, ensure_ascii=False)
    completed = subprocess.run([resolved_binary, "db-query"], input=request, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"DuckDB query failed: {completed.stderr.strip()}")
    rows = json.loads(completed.stdout)
    if not isinstance(rows, list):
        raise RuntimeError("DuckDB query returned an invalid response")
    return rows
