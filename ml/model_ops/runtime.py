from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from ml.env import load_dotenv_values


RUNTIME_ROOT_ENV = "STOCK_SELECT_RUNTIME_ROOT"


def resolve_runtime_root(
    cli_runtime_root: Path | None = None,
    *,
    env_runtime_root: str | None = None,
    dotenv_path: Path = Path(".env"),
    env: Mapping[str, str] | None = None,
) -> Path:
    if cli_runtime_root is not None:
        return cli_runtime_root
    source_env = os.environ if env is None else env
    shell_value = env_runtime_root if env_runtime_root is not None else source_env.get(RUNTIME_ROOT_ENV)
    if shell_value and shell_value.strip():
        return Path(shell_value.strip())
    dotenv_value = load_dotenv_values(dotenv_path).get(RUNTIME_ROOT_ENV)
    if dotenv_value and dotenv_value.strip():
        return Path(dotenv_value.strip())
    raise ValueError(f"需要配置 {RUNTIME_ROOT_ENV}，或显式传 --runtime-root/--target-dir")


def resolve_default_target_dir(
    cli_runtime_root: Path | None = None,
    *,
    method: str = "b2",
    env_runtime_root: str | None = None,
    dotenv_path: Path = Path(".env"),
    env: Mapping[str, str] | None = None,
) -> Path:
    return resolve_runtime_root(
        cli_runtime_root,
        env_runtime_root=env_runtime_root,
        dotenv_path=dotenv_path,
        env=env,
    ) / "models" / method


def runtime_root_for_status(
    *,
    method: str,
    runtime_root: Path | None,
    target_dir: Path | None,
) -> Path:
    if runtime_root is not None:
        return runtime_root
    if target_dir is not None:
        if target_dir.parent.name == "models":
            return target_dir.parent.parent
        return target_dir.parent
    return resolve_runtime_root(None)
