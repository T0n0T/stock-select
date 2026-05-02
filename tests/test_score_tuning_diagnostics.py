from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_score_tuning_diagnostics_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "score_tuning_diagnostics.py"
    spec = importlib.util.spec_from_file_location("score_tuning_diagnostics", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_total_bin_edges_sorts_and_deduplicates_rejected() -> None:
    module = _load_score_tuning_diagnostics_module()

    assert module.parse_total_bin_edges("4.3,3.5,4.0,4.6") == [3.5, 4.0, 4.3, 4.6]

    try:
        module.parse_total_bin_edges("3.5,4.0,4.0")
    except ValueError as exc:
        assert "duplicates" in str(exc)
    else:
        raise AssertionError("expected duplicate total bin edges to raise ValueError")


def test_total_bucket_respects_edges() -> None:
    module = _load_score_tuning_diagnostics_module()
    edges = [3.5, 4.0, 4.3, 4.6]

    assert module.total_bucket(3.49, edges) == "<3.5"
    assert module.total_bucket(3.5, edges) == "3.5-4.0"
    assert module.total_bucket(4.29, edges) == "4.0-4.3"
    assert module.total_bucket(4.6, edges) == ">=4.6"


def test_score_bucket_rounds_and_clamps_to_1_through_5() -> None:
    module = _load_score_tuning_diagnostics_module()

    assert module.score_bucket(None) is None
    assert module.score_bucket(0.2) == "1"
    assert module.score_bucket(1.49) == "1"
    assert module.score_bucket(1.5) == "2"
    assert module.score_bucket(4.6) == "5"
    assert module.score_bucket(5.7) == "5"


def test_correlations_detect_positive_and_negative_monotonic_relationships() -> None:
    module = _load_score_tuning_diagnostics_module()

    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys_positive = [2.0, 4.0, 6.0, 8.0, 10.0]
    ys_negative = [10.0, 8.0, 6.0, 4.0, 2.0]

    assert round(module.pearson(xs, ys_positive), 4) == 1.0
    assert round(module.spearman(xs, ys_positive), 4) == 1.0
    assert round(module.pearson(xs, ys_negative), 4) == -1.0
    assert round(module.spearman(xs, ys_negative), 4) == -1.0


def test_summarize_groups_reports_return_stats() -> None:
    module = _load_score_tuning_diagnostics_module()

    items = [
        {"verdict": "PASS", "ret3_pct": 3.0, "ret5_pct": 5.0},
        {"verdict": "PASS", "ret3_pct": -1.0, "ret5_pct": 2.0},
        {"verdict": "WATCH", "ret3_pct": 0.0, "ret5_pct": None},
    ]

    summary = module.summarize_groups(items, "verdict")

    assert summary["PASS"]["count"] == 2
    assert summary["PASS"]["ret3"]["avg"] == 1.0
    assert summary["PASS"]["ret3"]["win_rate"] == 50.0
    assert summary["WATCH"]["ret5"]["n"] == 0
