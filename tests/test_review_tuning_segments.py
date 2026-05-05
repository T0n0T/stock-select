from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import stock_select.research.review_tuning as review_tuning


def _load_review_tuning_segments_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_segments.py"
    spec = importlib.util.spec_from_file_location("review_tuning_segments", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compute_segments_groups_by_verdict_and_score_band() -> None:
    rows = [
        {
            "method": "b1",
            "environment_state": "neutral",
            "verdict": "PASS",
            "total_score": 4.3,
            "price_position": 5.0,
            "ret3_pct": 2.0,
            "ret5_pct": 3.0,
        },
        {
            "method": "b1",
            "environment_state": "neutral",
            "verdict": "WATCH",
            "total_score": 3.5,
            "price_position": 3.0,
            "ret3_pct": 1.0,
            "ret5_pct": 0.0,
        },
    ]

    result = review_tuning.compute_segments(rows)

    assert any(item["segment_type"] == "verdict" and item["segment_value"] == "PASS" for item in result)
    assert any(item["segment_type"] == "total_score_band" for item in result)


def test_compute_segments_buckets_all_score_fields() -> None:
    rows = [
        {
            "method": "b1",
            "environment_state": "neutral",
            "verdict": "PASS",
            "total_score": 4.3,
            "trend_structure": 4.0,
            "price_position": 5.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 2.0,
            "macd_phase": 4.0,
            "ret3_pct": 2.0,
            "ret5_pct": 3.0,
        }
    ]

    result = review_tuning.compute_segments(rows)
    segment_types = {item["segment_type"] for item in result}

    assert "trend_structure_bucket" in segment_types
    assert "price_position_bucket" in segment_types
    assert "volume_behavior_bucket" in segment_types
    assert "previous_abnormal_move_bucket" in segment_types
    assert "macd_phase_bucket" in segment_types


def test_compute_segments_includes_scoped_breakdowns() -> None:
    rows = [
        {
            "method": "b1",
            "environment_state": "neutral",
            "verdict": "PASS",
            "total_score": 4.3,
            "price_position": 5.0,
            "macd_phase": 4.0,
            "ret3_pct": 2.0,
            "ret5_pct": 3.0,
        },
        {
            "method": "b2",
            "environment_state": "weak",
            "verdict": "WATCH",
            "total_score": 3.5,
            "price_position": 3.0,
            "macd_phase": 2.0,
            "ret3_pct": 1.0,
            "ret5_pct": 0.0,
        },
    ]

    result = review_tuning.compute_segments(rows)

    assert any(item["scope_type"] == "method" and item["method"] == "b1" for item in result)
    assert any(
        item["scope_type"] == "environment_state" and item["environment_state"] == "neutral"
        for item in result
    )
    assert any(
        item["scope_type"] == "method_environment_state"
        and item["method"] == "b1"
        and item["environment_state"] == "neutral"
        for item in result
    )
    assert all("group_key" in item for item in result)


def test_review_tuning_segments_main_writes_json(tmp_path: Path) -> None:
    module = _load_review_tuning_segments_module()

    samples_path = tmp_path / "samples_with_env.csv"
    samples_path.write_text(
        "\n".join(
            [
                "method,environment_state,verdict,total_score,price_position,macd_phase,ret3_pct,ret5_pct",
                "b1,neutral,PASS,4.3,5,4,2.0,3.0",
                "b1,neutral,WATCH,3.5,3,2,1.0,0.0",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    args = module.parse_args(
        [
            "--samples",
            str(samples_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert module.main(args) == 0

    payload = json.loads((output_dir / "segments.json").read_text(encoding="utf-8"))
    assert any(item["segment_type"] == "verdict" for item in payload)


def test_review_tuning_segments_main_writes_csv(tmp_path: Path) -> None:
    module = _load_review_tuning_segments_module()

    samples_path = tmp_path / "samples_with_env.csv"
    samples_path.write_text(
        "\n".join(
            [
                "method,environment_state,verdict,total_score,price_position,macd_phase,ret3_pct,ret5_pct",
                "b1,neutral,PASS,4.3,5,4,2.0,3.0",
                "b1,neutral,WATCH,3.5,3,2,1.0,0.0",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    args = module.parse_args(
        [
            "--samples",
            str(samples_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert module.main(args) == 0

    frame = pd.read_csv(output_dir / "segments.csv")
    assert "group_key" in frame.columns
    assert "segment_type" in frame.columns
    assert "ret3_n" in frame.columns
    assert "ret3_avg" in frame.columns
    assert "ret3_median" in frame.columns
    assert "ret3_win_rate" in frame.columns
    assert "ret3_max" in frame.columns
    assert "ret3_min" in frame.columns
    assert "ret5_n" in frame.columns
    assert "ret5_avg" in frame.columns
    assert "ret5_median" in frame.columns
    assert "ret5_win_rate" in frame.columns
    assert "ret5_max" in frame.columns
    assert "ret5_min" in frame.columns
    assert "ret3" not in frame.columns
    assert "ret5" not in frame.columns
