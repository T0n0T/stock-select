from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review_top3_win_stats.py"
spec = importlib.util.spec_from_file_location("review_top3_win_stats", SCRIPT_PATH)
stats = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = stats
spec.loader.exec_module(stats)


def test_collect_pass_top_reviews_uses_score_not_average_return() -> None:
    summary = {
        "recommendations": [
            {"code": "AAA.SZ", "verdict": "PASS", "total_score": 4.1},
            {"code": "BBB.SZ", "verdict": "WATCH", "total_score": 5.0},
            {"code": "CCC.SZ", "verdict": "PASS", "total_score": 4.8},
        ],
        "excluded": [
            {"code": "DDD.SZ", "verdict": "PASS", "total_score": 3.9},
            {"code": "EEE.SZ", "verdict": "FAIL", "total_score": 5.0},
        ],
    }

    rows = stats.collect_pass_top_reviews(summary, top_n=2)

    assert [row["code"] for row in rows] == ["CCC.SZ", "AAA.SZ"]


def test_get_forward_data_computes_positive_win_flags() -> None:
    rows = [
        {"ts_code": "AAA.SZ", "trade_date": "2026-05-20", "open": 10.0, "close": 10.0},
        {"ts_code": "AAA.SZ", "trade_date": "2026-05-21", "open": 10.2, "close": 10.5},
        {"ts_code": "AAA.SZ", "trade_date": "2026-05-22", "open": 10.6, "close": 10.1},
        {"ts_code": "AAA.SZ", "trade_date": "2026-05-25", "open": 10.1, "close": 10.3},
        {"ts_code": "AAA.SZ", "trade_date": "2026-05-26", "open": 10.3, "close": 9.8},
        {"ts_code": "AAA.SZ", "trade_date": "2026-05-27", "open": 9.8, "close": 10.8},
    ]

    fwd = stats.get_forward_data(rows, "AAA.SZ", "2026-05-20")

    assert fwd["ret3_pct"] == 3.0
    assert fwd["ret5_pct"] == 8.0
    assert fwd["win_ret3"] is True
    assert fwd["win_ret5"] is True


def test_summarize_win_metrics_prioritizes_win_rates_and_day_hit_rates() -> None:
    records = [
        {"method": "b2", "pick_date": "2026-05-20", "environment_state": "weak", "ret3_pct": 10.0, "ret5_pct": -1.0},
        {"method": "b2", "pick_date": "2026-05-20", "environment_state": "weak", "ret3_pct": -2.0, "ret5_pct": -2.0},
        {"method": "b2", "pick_date": "2026-05-21", "environment_state": "weak", "ret3_pct": -1.0, "ret5_pct": 2.0},
        {"method": "b2", "pick_date": "2026-05-21", "environment_state": "weak", "ret3_pct": -3.0, "ret5_pct": 3.0},
    ]

    rows = stats.summarize_win_metrics(records)

    assert rows == [
        {
            "method": "b2",
            "environment_state": "weak",
            "record_count": 4,
            "review_count": 2,
            "win_rate_ret3_pct": 25.0,
            "win_rate_ret5_pct": 50.0,
            "day_hit_rate_ret3_pct": 50.0,
            "day_hit_rate_ret5_pct": 50.0,
        }
    ]
    assert "avg_ret3_pct" not in rows[0]
    assert "avg_ret5_pct" not in rows[0]
