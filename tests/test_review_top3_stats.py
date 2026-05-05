from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest
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


def test_collect_pass_top_reviews_supports_multiple_methods_and_environment_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_review_top3_stats_module()

    runtime_root = tmp_path / "runtime"
    reviews_root = runtime_root / "reviews"
    prepared_root = tmp_path / "prepared"
    reviews_root.mkdir(parents=True)
    prepared_root.mkdir()

    for pick_date, method, code, score in [
        ("2026-04-10", "b1", "000001.SZ", 4.5),
        ("2026-04-12", "b2", "000002.SZ", 4.3),
        ("2026-04-22", "b2", "000003.SZ", 4.8),
    ]:
        review_dir = reviews_root / f"{pick_date}.{method}"
        review_dir.mkdir()
        (review_dir / "summary.json").write_text(
            json.dumps(
                {
                    "pick_date": pick_date,
                    "recommendations": [
                        {"code": code, "total_score": score, "verdict": "PASS"},
                    ],
                    "excluded": [],
                }
            ),
            encoding="utf-8",
        )

    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-30.feather",
        prepared_root / "2026-04-30.meta.json",
        method="b1",
        pick_date="2026-04-30",
        start_date="2026-04-01",
        end_date="2026-04-30",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000002.SZ", "trade_date": "2026-04-12", "open": 20.0, "close": 20.0},
                {"ts_code": "000002.SZ", "trade_date": "2026-04-13", "open": 20.1, "close": 20.2},
                {"ts_code": "000002.SZ", "trade_date": "2026-04-14", "open": 20.2, "close": 20.4},
                {"ts_code": "000002.SZ", "trade_date": "2026-04-15", "open": 20.3, "close": 20.6},
                {"ts_code": "000003.SZ", "trade_date": "2026-04-22", "open": 30.0, "close": 30.0},
                {"ts_code": "000003.SZ", "trade_date": "2026-04-23", "open": 30.1, "close": 30.2},
                {"ts_code": "000003.SZ", "trade_date": "2026-04-24", "open": 30.2, "close": 30.4},
                {"ts_code": "000003.SZ", "trade_date": "2026-04-25", "open": 30.3, "close": 30.6},
            ]
        ),
    )

    module.REVIEWS_DIR = reviews_root
    module.PREPARED_DIR = prepared_root
    monkeypatch.setattr(
        module,
        "load_environment_history",
        lambda _runtime_root: [
            {
                "start_date": "2026-04-01",
                "end_date": "2026-04-15",
                "score_based_state": "weak",
                "state": "neutral",
            },
            {
                "start_date": "2026-04-16",
                "end_date": "2026-04-30",
                "score_based_state": "strong",
                "state": "strong",
            },
        ],
    )

    result = module.collect_review_top3_records(
        methods=["b1", "b2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        environment_state="weak",
    )

    assert result
    assert all(item["environment_state"] == "weak" for item in result)
    assert {item["method"] for item in result} == {"b1", "b2"}


def test_compare_artifact_dirs_reports_delta() -> None:
    module = _load_review_top3_stats_module()

    payload = module.compare_top3_metrics(
        baseline=[{"method": "b2", "avg_ret3_pct": 0.5}],
        candidate=[{"method": "b2", "avg_ret3_pct": 1.2}],
    )

    assert payload["rows"][0]["delta_ret3_pct"] == 0.7


def test_compare_artifact_dirs_does_not_apply_default_date_filter(tmp_path: Path) -> None:
    module = _load_review_top3_stats_module()

    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    baseline_dir.mkdir()
    candidate_dir.mkdir()
    for path, ret3 in [(baseline_dir, 0.5), (candidate_dir, 1.2)]:
        (path / "samples_with_env.csv").write_text(
            "\n".join(
                [
                    "method,pick_date,code,total_score,verdict,ret3_pct,ret5_pct,environment_state",
                    f"b2,2026-05-10,000001.SZ,4.2,PASS,{ret3},1.0,neutral",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    payload = module.compare_artifact_dirs(
        baseline_artifact_dir=baseline_dir,
        candidate_artifact_dir=candidate_dir,
        methods=[],
    )

    assert payload["comparison"]["rows"][0]["delta_ret3_pct"] == 0.7


def test_compare_artifact_dirs_with_empty_methods_uses_all_methods_in_artifact(tmp_path: Path) -> None:
    module = _load_review_top3_stats_module()

    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    baseline_dir.mkdir()
    candidate_dir.mkdir()
    baseline_lines = [
        "method,pick_date,code,total_score,verdict,ret3_pct,ret5_pct,environment_state",
        "b1,2026-05-10,000001.SZ,4.2,PASS,0.5,1.0,neutral",
        "b2,2026-05-10,000002.SZ,4.0,PASS,0.6,1.1,neutral",
    ]
    candidate_lines = [
        "method,pick_date,code,total_score,verdict,ret3_pct,ret5_pct,environment_state",
        "b1,2026-05-10,000001.SZ,4.2,PASS,1.5,1.0,neutral",
        "b2,2026-05-10,000002.SZ,4.0,PASS,1.6,1.1,neutral",
    ]
    (baseline_dir / "samples_with_env.csv").write_text("\n".join(baseline_lines) + "\n", encoding="utf-8")
    (candidate_dir / "samples_with_env.csv").write_text("\n".join(candidate_lines) + "\n", encoding="utf-8")

    payload = module.compare_artifact_dirs(
        baseline_artifact_dir=baseline_dir,
        candidate_artifact_dir=candidate_dir,
        methods=[],
    )

    assert {row["method"] for row in payload["comparison"]["rows"]} == {"b1", "b2"}


def test_collect_review_top3_records_fails_cleanly_when_environment_filter_requires_missing_labels(
    tmp_path: Path,
) -> None:
    module = _load_review_top3_stats_module()

    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "samples.csv").write_text(
        "\n".join(
            [
                "method,pick_date,code,total_score,verdict,ret3_pct,ret5_pct",
                "b2,2026-05-10,000001.SZ,4.2,PASS,0.5,1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        module.collect_review_top3_records(
            methods=[],
            start_date=None,
            end_date=None,
            environment_state="neutral",
            artifact_dir=artifact_dir,
        )

    assert "environment_state" in str(excinfo.value)


def test_collect_review_top3_records_fails_cleanly_when_artifact_files_are_missing(
    tmp_path: Path,
) -> None:
    module = _load_review_top3_stats_module()

    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()

    with pytest.raises(ValueError) as excinfo:
        module.collect_review_top3_records(
            methods=[],
            start_date=None,
            end_date=None,
            artifact_dir=artifact_dir,
        )

    assert "samples_with_env.csv" in str(excinfo.value)
