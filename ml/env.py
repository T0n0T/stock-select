from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def load_dotenv_values(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def resolve_config_value(
    cli_value: str | None,
    key: str,
    dotenv_values: Mapping[str, str],
    *,
    env: Mapping[str, str] | None = None,
) -> str | None:
    source = os.environ if env is None else env
    for value in (cli_value, source.get(key), dotenv_values.get(key)):
        if value is not None and str(value).strip():
            return str(value).strip()
    return None
