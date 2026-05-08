from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "b2_weak_analysis.py"
    spec = importlib.util.spec_from_file_location("b2_weak_analysis", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_summary_reports_weak_metrics_and_candidates() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        [
            {
                "pick_date": "2026-02-03",
                "code": "000001.SZ",
                "signal": "B2",
                "signal_type": "rebound",
                "verdict": "PASS",
                "watch_tier": None,
                "watch_score": None,
                "total_score": 3.87,
                "ret5_pct": 8.0,
                "trend_structure": 3.0,
                "price_position": 4.0,
                "volume_behavior": 2.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 3.56,
                "box_position": 0.66,
                "close_box_position": 0.68,
                "box_range_pct": 110.0,
                "zxdq_5d_slope_pct": 0.98,
                "zxdkx_5d_slope_pct": 1.64,
                "override_bucket": "A-clean",
            },
            {
                "pick_date": "2026-02-04",
                "code": "000002.SZ",
                "signal": "B2",
                "signal_type": "rebound",
                "verdict": "PASS",
                "watch_tier": None,
                "watch_score": None,
                "total_score": 3.45,
                "ret5_pct": -1.5,
                "trend_structure": 3.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 1.88,
                "box_position": 0.69,
                "close_box_position": 0.71,
                "box_range_pct": 215.0,
                "zxdq_5d_slope_pct": -2.77,
                "zxdkx_5d_slope_pct": 0.41,
                "override_bucket": "A-clean",
            },
            {
                "pick_date": "2026-03-01",
                "code": "000003.SZ",
                "signal": "B2",
                "signal_type": "trend_start",
                "verdict": "WATCH",
                "watch_tier": "WATCH-B",
                "watch_score": 68.0,
                "total_score": 4.16,
                "ret5_pct": 63.3,
                "trend_structure": 4.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 3.76,
                "box_position": 0.65,
                "close_box_position": 0.76,
                "box_range_pct": 116.8,
                "zxdq_5d_slope_pct": 3.55,
                "zxdkx_5d_slope_pct": 4.63,
                "override_bucket": "none",
            },
            {
                "pick_date": "2026-03-02",
                "code": "000004.SZ",
                "signal": "B2",
                "signal_type": "trend_start",
                "verdict": "WATCH",
                "watch_tier": "WATCH-B",
                "watch_score": 72.0,
                "total_score": 3.91,
                "ret5_pct": 32.65,
                "trend_structure": 4.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 3.0,
                "macd_phase": 4.5,
                "box_position": 0.78,
                "close_box_position": 0.83,
                "box_range_pct": 268.9,
                "zxdq_5d_slope_pct": 0.03,
                "zxdkx_5d_slope_pct": 2.74,
                "override_bucket": "none",
            },
            {
                "pick_date": "2026-03-03",
                "code": "000005.SZ",
                "signal": "B2",
                "signal_type": "rebound",
                "verdict": "WATCH",
                "watch_tier": "WATCH-C",
                "watch_score": 62.0,
                "total_score": 3.67,
                "ret5_pct": 38.6,
                "trend_structure": 3.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 3.0,
                "macd_phase": 4.5,
                "box_position": 0.61,
                "close_box_position": 0.62,
                "box_range_pct": 268.0,
                "zxdq_5d_slope_pct": -5.63,
                "zxdkx_5d_slope_pct": 0.55,
                "override_bucket": "none",
            },
            {
                "pick_date": "2026-03-04",
                "code": "000006.SZ",
                "signal": "B2",
                "signal_type": "trend_start",
                "verdict": "WATCH",
                "watch_tier": "WATCH-A",
                "watch_score": 92.0,
                "total_score": 4.3,
                "ret5_pct": -12.0,
                "trend_structure": 4.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 4.34,
                "box_position": 0.74,
                "close_box_position": 0.77,
                "box_range_pct": 180.0,
                "zxdq_5d_slope_pct": -0.87,
                "zxdkx_5d_slope_pct": 0.5,
                "override_bucket": "A-clean",
            },
            {
                "pick_date": "2026-03-05",
                "code": "000007.SZ",
                "signal": "B2",
                "signal_type": "rebound",
                "verdict": "FAIL",
                "watch_tier": None,
                "watch_score": None,
                "total_score": 3.14,
                "ret5_pct": 32.69,
                "trend_structure": 4.0,
                "price_position": 1.0,
                "volume_behavior": 4.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 1.36,
                "box_position": 0.34,
                "close_box_position": 0.39,
                "box_range_pct": 57.2,
                "zxdq_5d_slope_pct": 1.03,
                "zxdkx_5d_slope_pct": 0.92,
                "override_bucket": "none",
            },
            {
                "pick_date": "2026-03-06",
                "code": "000008.SZ",
                "signal": "B3",
                "signal_type": "trend_start",
                "verdict": "FAIL",
                "watch_tier": None,
                "watch_score": None,
                "total_score": 3.0,
                "ret5_pct": -8.0,
                "trend_structure": 4.0,
                "price_position": 1.0,
                "volume_behavior": 4.0,
                "previous_abnormal_move": 3.0,
                "macd_phase": 1.5,
                "box_position": 0.55,
                "close_box_position": 0.59,
                "box_range_pct": 48.0,
                "zxdq_5d_slope_pct": -1.2,
                "zxdkx_5d_slope_pct": -0.2,
                "override_bucket": "none",
            },
        ]
    )

    payload = module.build_summary(frame, top_n=2)

    assert payload["verdict_stats"]["PASS"]["count"] == 2
    assert payload["verdict_stats"]["WATCH"]["count"] == 4
    assert payload["watch_tier_stats"]["WATCH-A"]["avg_ret5_pct"] == -12.0
    assert payload["contradictions"]["pass_but_weak"][0]["code"] == "000002.SZ"
    assert payload["contradictions"]["watch_but_surge"][0]["code"] == "000003.SZ"
    assert payload["contradictions"]["fail_but_surge"][0]["code"] == "000007.SZ"
    assert payload["top_bottom"]["top"]["verdict_counts"] == {"WATCH": 2}
    assert payload["top_bottom"]["bottom"]["verdict_counts"] == {"WATCH": 1, "FAIL": 1}
    assert payload["watch_score_bins"][0]["watch_score_bin"] == "60-70"
    assert payload["fail_interval_tests"][0]["rule_name"] == "box_position<=0.35"
    assert payload["candidate_playbacks"]["B2_rebound_A_clean_all"]["count"] == 2
    assert payload["candidate_playbacks"]["FAIL_left_box_rebound"]["count"] == 1
