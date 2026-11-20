from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from ml.env import load_dotenv_values, resolve_config_value
from ml.paths import resolve_stock_select_binary


def query_rows(
    source: str, sql: str, params: Sequence[Any], *, binary: str | Path | None = None
) -> list[dict[str, Any]]:
    """Run a read query through the same duckdb-neo client used by screening."""
    configured = resolve_config_value(None, "STOCK_SELECT_BIN", load_dotenv_values()) if binary is None else None
    executable = resolve_stock_select_binary(binary, configured)
    resolved_binary = str(executable) if executable.is_file() else shutil.which(str(executable))
    if resolved_binary is None:
        raise RuntimeError("stock-select-rs not found; build it with cargo build --release or set STOCK_SELECT_BIN")
    request = json.dumps({"source": source, "sql": sql, "params": list(params)}, ensure_ascii=False)
    completed = subprocess.run([resolved_binary, "db-query"], input=request, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"DuckDB query failed: {completed.stderr.strip()}")
    rows = json.loads(completed.stdout)
    if not isinstance(rows, list):
        raise RuntimeError("DuckDB query returned an invalid response")
    return rows
