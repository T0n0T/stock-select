from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from stock_select.cli import _build_prepared_cache_metadata


def _prepared_symbol_map_to_table(prepared_by_symbol: dict[str, pd.DataFrame]) -> pd.DataFrame:
    tables: list[pd.DataFrame] = []
    for code, frame in prepared_by_symbol.items():
        if frame.empty:
            continue
        table = frame.copy()
        if "ts_code" not in table.columns:
            table.insert(0, "ts_code", code)
        else:
            ts_codes = table["ts_code"].dropna()
            if not ts_codes.empty and not ts_codes.astype(str).eq(code).all():
                raise ValueError(f"Prepared cache frame for {code} has inconsistent ts_code values.")
        tables.append(table)
    if not tables:
        return pd.DataFrame(columns=["ts_code"])
    prepared = pd.concat(tables, ignore_index=True)
    if "trade_date" in prepared.columns:
        prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce", format="mixed")
    return prepared.sort_values(["ts_code", "trade_date"], na_position="last").reset_index(drop=True)


def convert_prepared_cache(
    pickle_path: Path,
    *,
    delete_pickle: bool = False,
) -> tuple[Path, Path]:
    data_path = pickle_path.with_suffix(".feather")
    meta_path = pickle_path.with_suffix(".meta.json")
    if data_path.exists() and meta_path.exists():
        return data_path, meta_path

    payload = pickle.loads(pickle_path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"Prepared cache payload must be a dict: {pickle_path}")

    prepared_by_symbol = payload.get("prepared_by_symbol")
    if not isinstance(prepared_by_symbol, dict):
        raise ValueError(f"Prepared cache prepared_by_symbol missing: {pickle_path}")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"Prepared cache metadata missing: {pickle_path}")

    method = metadata.get("method")
    metadata_overrides = dict(metadata)
    metadata_overrides.pop("b1_config", None)
    metadata_overrides.pop("turnover_window", None)
    metadata_overrides.pop("weekly_ma_periods", None)
    metadata_overrides.pop("max_vol_lookback", None)
    if method in {"b1", "b2", "dribull", "hcr"}:
        metadata_overrides.pop("screen_version", None)
    metadata_overrides.pop("method", None)

    prepared_table = _prepared_symbol_map_to_table(prepared_by_symbol)
    prepared_table.to_feather(data_path)
    meta_payload = {
        "pick_date": payload.get("pick_date"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "metadata": _build_prepared_cache_metadata(method=method, metadata_overrides=metadata_overrides),
    }
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")

    if delete_pickle:
        pickle_path.unlink()

    return data_path, meta_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert legacy prepared cache pickle artifacts to feather + meta.json")
    parser.add_argument(
        "--prepared-dir",
        type=Path,
        default=Path.home() / ".agents" / "skills" / "stock-select" / "runtime" / "prepared",
        help="Directory containing legacy .pkl prepared cache artifacts",
    )
    parser.add_argument(
        "--delete-pickle",
        action="store_true",
        help="Delete legacy .pkl after successful conversion",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Convert only the first N matching pickle files",
    )
    parser.add_argument(
        "--pattern",
        default="*.pkl",
        help="Glob pattern used inside prepared-dir, e.g. '2026-04-*.pkl'",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepared_dir = args.prepared_dir.expanduser().resolve()
    paths = sorted(prepared_dir.glob(args.pattern))
    if args.limit is not None:
        paths = paths[: args.limit]

    converted = 0
    for pickle_path in paths:
        data_path, meta_path = convert_prepared_cache(pickle_path, delete_pickle=args.delete_pickle)
        print(f"converted {pickle_path.name} -> {data_path.name}, {meta_path.name}")
        converted += 1
    print(f"converted_total={converted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
