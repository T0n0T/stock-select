from __future__ import annotations

import importlib.util
import pickle
from pathlib import Path

import pandas as pd


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

    shared_payload = {
        "prepared_by_symbol": {
            "AAA.SZ": pd.DataFrame([{"trade_date": "2026-04-10", "open": 1.0, "close": 1.1}])
        }
    }
    hcr_payload = {
        "prepared_by_symbol": {
            "HCR.SZ": pd.DataFrame([{"trade_date": "2026-04-10", "open": 2.0, "close": 2.1}])
        }
    }
    (tmp_path / "2026-04-10.pkl").write_bytes(pickle.dumps(shared_payload))
    (tmp_path / "2026-04-10.hcr.pkl").write_bytes(pickle.dumps(hcr_payload))

    module.PREPARED_DIR = tmp_path

    assert sorted(module.load_prepared("b1")) == ["AAA.SZ"]
    assert sorted(module.load_prepared("b2")) == ["AAA.SZ"]
    assert sorted(module.load_prepared("dribull")) == ["AAA.SZ"]
    assert sorted(module.load_prepared("hcr")) == ["HCR.SZ"]
