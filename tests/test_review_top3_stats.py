from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
from stock_select import cli


def _load_review_top3_stats_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_top3_stats.py"
    spec = importlib.util.spec_from_file_location("review_top3_stats", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_collect_pass_top3_includes_pass_items_from_excluded() -> None:
    module = _load_review_top3_stats_module()

    summary = {
        "recommendations": [
            {"code": "AAA.SZ", "verdict": "PASS", "total_score": 4.5},
            {"code": "BBB.SZ", "verdict": "PASS", "total_score": 4.2},
        ],
        "excluded": [
            {"code": "CCC.SZ", "verdict": "PASS", "total_score": 3.9},
            {"code": "DDD.SZ", "verdict": "WATCH", "total_score": 4.8},
            {"code": "EEE.SZ", "verdict": "FAIL", "total_score": 4.7},
        ],
    }

    top3 = module.collect_pass_top_reviews(summary, top_n=3)

    assert [item["code"] for item in top3] == ["AAA.SZ", "BBB.SZ", "CCC.SZ"]


def test_load_prepared_uses_shared_cache_name_for_b1_b2_and_dribull(tmp_path: Path) -> None:
    module = _load_review_top3_stats_module()

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
    cli._write_prepared_cache_v2(
        tmp_path / "2026-04-10.hcr.feather",
        tmp_path / "2026-04-10.hcr.meta.json",
        method="hcr",
        pick_date="2026-04-10",
        start_date="2025-04-10",
        end_date="2026-04-10",
        prepared_table=pd.DataFrame(
            [{"ts_code": "HCR.SZ", "trade_date": "2026-04-10", "open": 2.0, "close": 2.1}]
        ),
    )

    module.PREPARED_DIR = tmp_path

    assert sorted(module.load_prepared("b1")["ts_code"].unique()) == ["AAA.SZ"]
    assert sorted(module.load_prepared("b2")["ts_code"].unique()) == ["AAA.SZ"]
    assert sorted(module.load_prepared("dribull")["ts_code"].unique()) == ["AAA.SZ"]
    assert sorted(module.load_prepared("hcr")["ts_code"].unique()) == ["HCR.SZ"]


def test_load_prepared_accepts_v2_prepared_cache(tmp_path: Path) -> None:
    module = _load_review_top3_stats_module()

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

    assert sorted(module.load_prepared("b1")["ts_code"].unique()) == ["AAA.SZ"]
