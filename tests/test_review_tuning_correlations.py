from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pandas as pd
import stock_select.research.review_tuning as review_tuning


def _load_review_tuning_correlations_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_correlations.py"
    spec = importlib.util.spec_from_file_location("review_tuning_correlations", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compute_correlations_marks_small_groups_as_insufficient() -> None:
    rows = [
        {
            "method": "b2",
            "environment_state": "weak",
            "total_score": 4.0,
            "ret3_pct": 1.0,
            "ret5_pct": 2.0,
        },
        {
            "method": "b2",
            "environment_state": "weak",
            "total_score": 3.0,
            "ret3_pct": -1.0,
            "ret5_pct": -2.0,
        },
    ]

    result = review_tuning.compute_correlations(rows, min_samples_strong=30, min_samples_weak=10)

    assert result["groups"][0]["conclusion_strength"] == "insufficient"
    assert "pearson_r" in result["groups"][0]["metrics"][0]
    assert "spearman_r" in result["groups"][0]["metrics"][0]


def test_compute_correlations_adds_metric_level_coverage_strength() -> None:
    rows = [
        {
            "method": "b2",
            "environment_state": "weak",
            "total_score": 4.0,
            "ret3_pct": 1.0,
            "ret5_pct": 2.0,
        },
        {
            "method": "b2",
            "environment_state": "weak",
            "total_score": 3.0,
            "ret3_pct": -1.0,
            "ret5_pct": -2.0,
        },
    ]

    result = review_tuning.compute_correlations(rows, min_samples_strong=3, min_samples_weak=2)

    metric = next(
        item
        for item in result["groups"][0]["metrics"]
        if item["score_field"] == "total_score" and item["target_field"] == "ret3_pct"
    )
    assert metric["pair_count"] == 2
    assert metric["coverage_strength"] == "weak"


def test_review_tuning_correlations_main_writes_json(tmp_path: Path) -> None:
    module = _load_review_tuning_correlations_module()

    samples_path = tmp_path / "samples_with_env.csv"
    samples_path.write_text(
        "\n".join(
            [
                "method,environment_state,total_score,trend_structure,price_position,volume_behavior,previous_abnormal_move,macd_phase,ret3_pct,ret5_pct",
                "b1,strong,4.2,4,5,4,3,4,1.5,2.5",
                "b1,strong,3.8,3,4,3,2,3,-0.5,0.5",
                "b2,weak,4.0,4,4,4,4,4,1.0,2.0",
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

    payload = json.loads((output_dir / "correlations.json").read_text(encoding="utf-8"))
    assert "groups" in payload
    assert payload["groups"]


def test_review_tuning_correlations_main_writes_csv(tmp_path: Path) -> None:
    module = _load_review_tuning_correlations_module()

    samples_path = tmp_path / "samples_with_env.csv"
    samples_path.write_text(
        "\n".join(
            [
                "method,environment_state,total_score,trend_structure,price_position,volume_behavior,previous_abnormal_move,macd_phase,ret3_pct,ret5_pct",
                "b1,strong,4.2,4,5,4,3,4,1.5,2.5",
                "b1,strong,3.8,3,4,3,2,3,-0.5,0.5",
                "b2,weak,4.0,4,4,4,4,4,1.0,2.0",
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

    frame = pd.read_csv(output_dir / "correlations.csv")
    assert "group_key" in frame.columns
    assert "score_field" in frame.columns


def test_compute_correlations_skips_missing_environment_state_scopes() -> None:
    rows = [
        {
            "method": "b1",
            "environment_state": math.nan,
            "total_score": 4.0,
            "ret3_pct": 1.0,
            "ret5_pct": 2.0,
        }
    ]

    result = review_tuning.compute_correlations(rows)

    group_keys = [item["group_key"] for item in result["groups"]]
    assert "environment_state:nan" not in group_keys
    assert not any(item["scope_type"] == "environment_state" for item in result["groups"])


def test_review_tuning_correlations_main_handles_empty_file_with_stable_outputs(tmp_path: Path) -> None:
    module = _load_review_tuning_correlations_module()

    samples_path = tmp_path / "samples_with_env.csv"
    samples_path.write_text("", encoding="utf-8")

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

    payload = json.loads((output_dir / "correlations.json").read_text(encoding="utf-8"))
    assert payload == {"groups": []}

    frame = pd.read_csv(output_dir / "correlations.csv")
    assert list(frame.columns) == [
        "group_key",
        "scope_type",
        "method",
        "environment_state",
        "sample_count",
        "conclusion_strength",
        "score_field",
        "target_field",
        "pair_count",
        "coverage_strength",
        "pearson_r",
        "spearman_r",
    ]
    assert frame.empty


def test_review_tuning_correlations_main_uses_artifact_dir_defaults(tmp_path: Path) -> None:
    module = _load_review_tuning_correlations_module()

    artifact_dir = tmp_path / "artifacts" / "review-tuning" / "smoke"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "samples_with_env.csv").write_text(
        "\n".join(
            [
                "method,environment_state,total_score,trend_structure,price_position,volume_behavior,previous_abnormal_move,macd_phase,ret3_pct,ret5_pct",
                "b1,strong,4.2,4,5,4,3,4,1.5,2.5",
                "b1,strong,3.8,3,4,3,2,3,-0.5,0.5",
            ]
        ),
        encoding="utf-8",
    )

    args = module.parse_args(["--artifact-dir", str(artifact_dir)])

    assert module.main(args) == 0
    assert (artifact_dir / "correlations.json").exists()
    assert (artifact_dir / "correlations.csv").exists()
