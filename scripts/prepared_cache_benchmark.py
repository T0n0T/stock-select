from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from stock_select.cli import (  # noqa: E402
    _default_runtime_root,
    _load_prepared_cache_v2,
    _prepared_cache_data_path,
    _prepared_cache_meta_path,
)


def _format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{size} B"


def _time_call(func, *args):
    started = time.perf_counter()
    try:
        payload = func(*args)
    except Exception as exc:  # pragma: no cover - benchmark status path
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {"ok": False, "elapsed_ms": elapsed_ms, "error": f"{type(exc).__name__}: {exc}"}
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {"ok": True, "elapsed_ms": elapsed_ms, "payload": payload}


def _payload_symbol_count(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    prepared = payload.get("prepared_table")
    if not hasattr(prepared, "columns") or not hasattr(prepared, "empty"):
        return None
    prepared_table = prepared
    if "ts_code" not in prepared_table.columns:
        return None
    return int(prepared_table["ts_code"].nunique())


def _print_v2_section(data_path: Path, meta_path: Path) -> None:
    print("v2_feather:")
    print(f"  data_path: {data_path}")
    print(f"  meta_path: {meta_path}")
    data_exists = data_path.exists()
    meta_exists = meta_path.exists()
    print(f"  data_exists: {'yes' if data_exists else 'no'}")
    print(f"  meta_exists: {'yes' if meta_exists else 'no'}")
    if data_exists:
        data_size = data_path.stat().st_size
        print(f"  data_size_bytes: {data_size}")
        print(f"  data_size_human: {_format_bytes(data_size)}")
    if meta_exists:
        meta_size = meta_path.stat().st_size
        print(f"  meta_size_bytes: {meta_size}")
        print(f"  meta_size_human: {_format_bytes(meta_size)}")
    if data_exists and meta_exists:
        total_size = data_path.stat().st_size + meta_path.stat().st_size
        print(f"  total_size_bytes: {total_size}")
        print(f"  total_size_human: {_format_bytes(total_size)}")
        timed = _time_call(_load_prepared_cache_v2, data_path, meta_path)
        print(f"  read_ms: {timed['elapsed_ms']:.3f}")
        if timed["ok"]:
            print(f"  symbol_count: {_payload_symbol_count(timed['payload'])}")
        else:
            print(f"  error: {timed['error']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark feather prepared cache reads")
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=_default_runtime_root(),
        help="Runtime root containing prepared cache artifacts",
    )
    parser.add_argument("--base-key", required=True, help="Prepared cache base key, e.g. 2026-04-30 or 2026-04-09.intraday")
    parser.add_argument("--method", required=True, help="Method name, e.g. b1, b2, dribull, hcr")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime_root = args.runtime_root.expanduser().resolve()
    method = args.method.strip().lower()
    base_key = args.base_key.strip()

    v2_data_path = _prepared_cache_data_path(runtime_root, base_key, method)
    v2_meta_path = _prepared_cache_meta_path(runtime_root, base_key, method)

    print("prepared_cache_benchmark:")
    print(f"  runtime_root: {runtime_root}")
    print(f"  base_key: {base_key}")
    print(f"  method: {method}")
    _print_v2_section(v2_data_path, v2_meta_path)


if __name__ == "__main__":
    main()
