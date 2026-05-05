from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

from stock_select import cli
from stock_select.research.review_tuning import collect_review_samples


def _load_review_tuning_collect_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_collect.py"
    spec = importlib.util.spec_from_file_location("review_tuning_collect", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_collect_review_samples_extracts_scores_and_forward_returns(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "method": "b2",
                        "total_score": 4.2,
                        "trend_structure": 4.0,
                        "price_position": 5.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 5.0,
                        "macd_phase": 4.5,
                        "verdict": "PASS",
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-15.feather",
        prepared_root / "2026-04-15.meta.json",
        method="b2",
        pick_date="2026-04-15",
        start_date="2026-04-01",
        end_date="2026-04-15",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.5},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.6},
            ]
        ),
    )

    rows = collect_review_samples(
        methods=["b2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        runtime_root=runtime_root,
        prepared_root=prepared_root,
    )

    assert rows[0]["code"] == "000001.SZ"
    assert rows[0]["total_score"] == 4.2
    assert rows[0]["ret3_pct"] == 4.0
    assert rows[0]["ret5_pct"] == 6.0


def test_collect_review_samples_reads_subscores_from_baseline_review(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "total_score": 4.2,
                        "verdict": "PASS",
                        "signal_type": "trend_start",
                        "comment": "runtime-shaped payload",
                        "baseline_review": {
                            "total_score": 4.0,
                            "trend_structure": 3.5,
                            "price_position": 4.5,
                            "volume_behavior": 2.5,
                            "previous_abnormal_move": 5.0,
                            "macd_phase": 4.0,
                            "verdict": "WATCH",
                        },
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-15.feather",
        prepared_root / "2026-04-15.meta.json",
        method="b2",
        pick_date="2026-04-15",
        start_date="2026-04-01",
        end_date="2026-04-15",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.5},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.6},
            ]
        ),
    )

    rows = collect_review_samples(
        methods=["b2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        runtime_root=runtime_root,
        prepared_root=prepared_root,
    )

    assert rows[0]["total_score"] == 4.2
    assert rows[0]["trend_structure"] == 3.5
    assert rows[0]["price_position"] == 4.5
    assert rows[0]["volume_behavior"] == 2.5
    assert rows[0]["previous_abnormal_move"] == 5.0
    assert rows[0]["macd_phase"] == 4.0
    assert rows[0]["verdict"] == "PASS"


def test_collect_review_samples_picks_latest_prepared_snapshot_on_or_before_end_date(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "method": "b2",
                        "total_score": 4.2,
                        "trend_structure": 4.0,
                        "price_position": 5.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 5.0,
                        "macd_phase": 4.5,
                        "verdict": "PASS",
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-12.feather",
        prepared_root / "2026-04-12.meta.json",
        method="b2",
        pick_date="2026-04-12",
        start_date="2026-04-01",
        end_date="2026-04-12",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
            ]
        ),
    )
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-15.feather",
        prepared_root / "2026-04-15.meta.json",
        method="b2",
        pick_date="2026-04-15",
        start_date="2026-04-01",
        end_date="2026-04-15",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.5},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.6},
            ]
        ),
    )
    cli._write_prepared_cache_v2(
        prepared_root / "2026-05-01.feather",
        prepared_root / "2026-05-01.meta.json",
        method="b2",
        pick_date="2026-05-01",
        start_date="2026-04-01",
        end_date="2026-05-01",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.1},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.5},
            ]
        ),
    )

    rows = collect_review_samples(
        methods=["b2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        runtime_root=runtime_root,
        prepared_root=prepared_root,
    )

    assert rows[0]["ret3_pct"] == 4.0
    assert rows[0]["ret5_pct"] == 6.0


def test_collect_review_samples_ignores_intraday_prepared_cache_for_shared_method(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "method": "b2",
                        "total_score": 4.2,
                        "trend_structure": 4.0,
                        "price_position": 5.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 5.0,
                        "macd_phase": 4.5,
                        "verdict": "PASS",
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-15.feather",
        prepared_root / "2026-04-15.meta.json",
        method="b2",
        pick_date="2026-04-15",
        start_date="2026-04-01",
        end_date="2026-04-15",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.5},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.6},
            ]
        ),
    )
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-29.intraday.feather",
        prepared_root / "2026-04-29.intraday.meta.json",
        method="b2",
        pick_date="2026-04-29",
        start_date="2026-04-01",
        end_date="2026-04-29",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.1},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.5},
            ]
        ),
    )

    rows = collect_review_samples(
        methods=["b2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        runtime_root=runtime_root,
        prepared_root=prepared_root,
    )

    assert rows[0]["ret3_pct"] == 4.0
    assert rows[0]["ret5_pct"] == 6.0


def test_collect_review_samples_normalizes_method_name_for_review_lookup(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "method": "b2",
                        "total_score": 4.2,
                        "trend_structure": 4.0,
                        "price_position": 5.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 5.0,
                        "macd_phase": 4.5,
                        "verdict": "PASS",
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-15.feather",
        prepared_root / "2026-04-15.meta.json",
        method="b2",
        pick_date="2026-04-15",
        start_date="2026-04-01",
        end_date="2026-04-15",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.5},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.6},
            ]
        ),
    )

    rows = collect_review_samples(
        methods=["B2"],
        start_date="2026-04-01",
        end_date="2026-04-30",
        runtime_root=runtime_root,
        prepared_root=prepared_root,
    )

    assert len(rows) == 1
    assert rows[0]["method"] == "b2"


def test_review_tuning_collect_main_writes_samples_csv(tmp_path: Path) -> None:
    module = _load_review_tuning_collect_module()

    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "method": "b2",
                        "total_score": 4.2,
                        "trend_structure": 4.0,
                        "price_position": 5.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 5.0,
                        "macd_phase": 4.5,
                        "verdict": "PASS",
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-15.feather",
        prepared_root / "2026-04-15.meta.json",
        method="b2",
        pick_date="2026-04-15",
        start_date="2026-04-01",
        end_date="2026-04-15",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.5},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.6},
            ]
        ),
    )

    output_dir = tmp_path / "output"
    args = module.parse_args(
        [
            "--methods",
            "b2",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-04-30",
            "--runtime-root",
            str(runtime_root),
            "--prepared-root",
            str(prepared_root),
            "--output-dir",
            str(output_dir),
        ]
    )

    module.main(args)

    csv_path = output_dir / "samples.csv"
    assert csv_path.exists()
    frame = pd.read_csv(csv_path)
    assert frame.loc[0, "code"] == "000001.SZ"
    assert frame.loc[0, "ret3_pct"] == 4.0


def test_review_tuning_collect_main_uses_artifact_dir_for_output(tmp_path: Path) -> None:
    module = _load_review_tuning_collect_module()

    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "method": "b2",
                        "total_score": 4.2,
                        "trend_structure": 4.0,
                        "price_position": 5.0,
                        "volume_behavior": 3.0,
                        "previous_abnormal_move": 5.0,
                        "macd_phase": 4.5,
                        "verdict": "PASS",
                    }
                ],
                "excluded": [],
            }
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    cli._write_prepared_cache_v2(
        prepared_root / "2026-04-15.feather",
        prepared_root / "2026-04-15.meta.json",
        method="b2",
        pick_date="2026-04-15",
        start_date="2026-04-01",
        end_date="2026-04-15",
        prepared_table=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2026-04-10", "open": 10.0, "close": 10.0},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-11", "open": 10.1, "close": 10.2},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-12", "open": 10.2, "close": 10.3},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-13", "open": 10.3, "close": 10.4},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-14", "open": 10.4, "close": 10.5},
                {"ts_code": "000001.SZ", "trade_date": "2026-04-15", "open": 10.5, "close": 10.6},
            ]
        ),
    )

    artifact_dir = tmp_path / "artifacts" / "review-tuning" / "smoke"
    args = module.parse_args(
        [
            "--methods",
            "b2",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-04-30",
            "--runtime-root",
            str(runtime_root),
            "--prepared-root",
            str(prepared_root),
            "--artifact-dir",
            str(artifact_dir),
        ]
    )

    assert module.main(args) == 0
    frame = pd.read_csv(artifact_dir / "samples.csv")
    assert frame.loc[0, "code"] == "000001.SZ"
