from __future__ import annotations

import importlib.util
import pickle
from pathlib import Path

import pandas as pd

from stock_select import cli


def _load_convert_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "convert_prepared_cache_v2.py"
    spec = importlib.util.spec_from_file_location("convert_prepared_cache_v2", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_convert_prepared_cache_converts_legacy_pickle_to_v2(tmp_path: Path) -> None:
    module = _load_convert_module()
    pickle_path = tmp_path / "2026-04-29.pkl"
    payload = {
        "pick_date": "2026-04-29",
        "start_date": "2025-04-28",
        "end_date": "2026-04-29",
        "prepared_by_symbol": {
            "AAA.SZ": pd.DataFrame(
                {
                    "ts_code": ["AAA.SZ", "AAA.SZ"],
                    "trade_date": pd.to_datetime(["2026-04-28", "2026-04-29"]),
                    "open": [10.0, 10.1],
                    "close": [10.2, 10.3],
                }
            ),
            "BBB.SZ": pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2026-04-29"]),
                    "open": [20.0],
                    "close": [20.4],
                }
            ),
        },
        "metadata": {
            "b1_config": cli.DEFAULT_B1_CONFIG,
            "turnover_window": cli.DEFAULT_TURNOVER_WINDOW,
            "weekly_ma_periods": cli.DEFAULT_WEEKLY_MA_PERIODS,
            "max_vol_lookback": cli.DEFAULT_MAX_VOL_LOOKBACK,
            "method": "b1",
            "screen_version": cli.B1_ARTIFACT_VERSION,
            "pool_source": "turnover-top",
        },
    }
    pickle_path.write_bytes(pickle.dumps(payload))

    data_path, meta_path = module.convert_prepared_cache(pickle_path)

    assert data_path.exists()
    assert meta_path.exists()

    loaded = cli._load_prepared_cache(pickle_path)
    assert loaded["pick_date"] == "2026-04-29"
    assert loaded["start_date"] == "2025-04-28"
    assert loaded["end_date"] == "2026-04-29"
    assert loaded["metadata"]["method"] == "b1"
    assert loaded["metadata"]["pool_source"] == "turnover-top"
    assert sorted(loaded["prepared_table"]["ts_code"].unique()) == ["AAA.SZ", "BBB.SZ"]
