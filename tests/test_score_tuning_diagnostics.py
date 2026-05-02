from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
from stock_select import cli


def _load_score_tuning_diagnostics_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "score_tuning_diagnostics.py"
    spec = importlib.util.spec_from_file_location("score_tuning_diagnostics", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_total_bin_edges_sorts_and_deduplicates() -> None:
    module = _load_score_tuning_diagnostics_module()

    assert module.parse_total_bin_edges("4.6, 3.5, 4.0") == [3.5, 4.0, 4.6]


def test_load_prepared_accepts_v2_prepared_cache(tmp_path: Path) -> None:
    module = _load_score_tuning_diagnostics_module()

    cli._write_prepared_cache_v2(
        tmp_path / "2026-04-10.feather",
        tmp_path / "2026-04-10.meta.json",
        method="b1",
        pick_date="2026-04-10",
        start_date="2025-04-10",
        end_date="2026-04-10",
        prepared_table=pd.DataFrame(
            [{"ts_code": "AAA.SZ", "trade_date": "2026-04-10", "open": 1.0, "close": 1.1}]
        ),
    )

    module.PREPARED_DIR = tmp_path

    assert sorted(module.load_prepared("b1", "2026-04-10")["ts_code"].unique()) == ["AAA.SZ"]
