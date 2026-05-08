from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "b2_neutral_gate_box_analysis.py"
    spec = importlib.util.spec_from_file_location("b2_neutral_gate_box_analysis", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_payload_summarizes_gate_watch_and_fail_sections() -> None:
    module = _load_module()
    dataset = pd.DataFrame(
        [
            {
                "verdict": "PASS",
                "ret5_pct": -5.0,
                "ret3_pct": -2.0,
                "total_score": 4.0,
                "signal": "B2",
                "signal_type": "rebound",
                "trend_structure": 3.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 4.4,
                "zxdq_5d_slope_pct": -0.8,
                "zxdkx_5d_slope_pct": 0.3,
                "box_position": 0.72,
                "close_box_position": 0.74,
                "box_range_pct": 28.0,
                "pick_date": "2026-01-01",
                "code": "000001.SZ",
            },
            {
                "verdict": "PASS",
                "ret5_pct": 8.0,
                "ret3_pct": 3.0,
                "total_score": 3.8,
                "signal": "B3",
                "signal_type": "rebound",
                "trend_structure": 3.0,
                "price_position": 4.0,
                "volume_behavior": 2.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 3.8,
                "zxdq_5d_slope_pct": 0.2,
                "zxdkx_5d_slope_pct": 0.4,
                "box_position": 0.69,
                "close_box_position": 0.70,
                "box_range_pct": 25.0,
                "pick_date": "2026-01-02",
                "code": "000002.SZ",
            },
            {
                "verdict": "WATCH",
                "ret5_pct": 25.0,
                "ret3_pct": 10.0,
                "total_score": 4.1,
                "signal": "B2",
                "signal_type": "trend_start",
                "trend_structure": 4.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 4.3,
                "zxdq_5d_slope_pct": 0.5,
                "zxdkx_5d_slope_pct": 0.4,
                "box_position": 0.83,
                "close_box_position": 0.86,
                "box_range_pct": 31.0,
                "watch_score": 76.0,
                "watch_tier": "WATCH-A",
                "pick_date": "2026-01-03",
                "code": "000003.SZ",
            },
            {
                "verdict": "WATCH",
                "ret5_pct": 2.0,
                "ret3_pct": 1.0,
                "total_score": 3.6,
                "signal": "B2",
                "signal_type": "rebound",
                "trend_structure": 3.0,
                "price_position": 3.0,
                "volume_behavior": 4.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 4.5,
                "zxdq_5d_slope_pct": -0.1,
                "zxdkx_5d_slope_pct": 0.1,
                "box_position": 0.61,
                "close_box_position": 0.62,
                "box_range_pct": 22.0,
                "watch_score": 52.0,
                "watch_tier": "WATCH-B",
                "pick_date": "2026-01-04",
                "code": "000004.SZ",
            },
            {
                "verdict": "FAIL",
                "ret5_pct": 22.0,
                "ret3_pct": 8.0,
                "total_score": 3.0,
                "signal": "B3",
                "signal_type": "rebound",
                "trend_structure": 3.0,
                "price_position": 1.0,
                "volume_behavior": 2.0,
                "previous_abnormal_move": 3.0,
                "macd_phase": 1.8,
                "zxdq_5d_slope_pct": -0.5,
                "zxdkx_5d_slope_pct": -0.3,
                "box_position": 0.34,
                "close_box_position": 0.36,
                "box_range_pct": 18.0,
                "box_high": 12.0,
                "box_low": 10.0,
                "current_mid_price": 10.7,
                "pick_date": "2026-01-05",
                "code": "000005.SZ",
            },
            {
                "verdict": "FAIL",
                "ret5_pct": -6.0,
                "ret3_pct": -3.0,
                "total_score": 2.8,
                "signal": "B2",
                "signal_type": "rebound",
                "trend_structure": 3.0,
                "price_position": 2.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 2.0,
                "zxdq_5d_slope_pct": -0.6,
                "zxdkx_5d_slope_pct": -0.2,
                "box_position": 0.52,
                "close_box_position": 0.49,
                "box_range_pct": 20.0,
                "box_high": 13.0,
                "box_low": 10.0,
                "current_mid_price": 11.6,
                "pick_date": "2026-01-06",
                "code": "000006.SZ",
            },
        ]
    )

    payload = module.build_payload(dataset)

    assert payload["pass_gate"]["pass_all"]["count"] == 2
    assert payload["pass_gate"]["pass_gate_keep"]["count"] == 1
    assert payload["pass_gate"]["pass_gate_blocked"]["count"] == 1
    assert payload["watch_distinction"]["watch_big"]["count"] == 1
    assert payload["fail_box"]["fail_big"]["count"] == 1
    assert payload["fail_box"]["quantiles"]["fail_big"]["box_position_q50"] == 0.34

