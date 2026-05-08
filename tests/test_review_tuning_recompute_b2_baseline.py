from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


def _load_recompute_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_recompute_b2_baseline.py"
    spec = importlib.util.spec_from_file_location("review_tuning_recompute_b2_baseline", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_recompute_b2_baseline_main_rewrites_summary_and_collects_candidate_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_recompute_module()

    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b2",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "pick_date": "2026-04-10",
                        "chart_path": "/tmp/000001.SZ_day.png",
                        "baseline_review": {
                            "code": "000001.SZ",
                            "pick_date": "2026-04-10",
                            "chart_path": "/tmp/000001.SZ_day.png",
                            "review_type": "baseline",
                            "trend_structure": 3.0,
                            "price_position": 3.0,
                            "volume_behavior": 3.0,
                            "previous_abnormal_move": 3.0,
                            "macd_phase": 3.0,
                            "total_score": 3.2,
                            "signal": "B2",
                            "signal_type": "trend_start",
                            "verdict": "WATCH",
                            "comment": "old",
                        },
                        "total_score": 3.2,
                        "signal_type": "trend_start",
                        "verdict": "WATCH",
                        "comment": "old",
                    }
                ],
                "excluded": [],
                "failures": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    artifact_dir = tmp_path / "candidate"
    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()

    monkeypatch.setattr(
        module,
        "_load_prepared_for_pick_date",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2026-04-10",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.9,
                    "close": 10.2,
                    "vol": 1000.0,
                    "zxdq": 9.8,
                    "zxdkx": 9.7,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        module,
        "_resolve_profile_for_pick_date",
        lambda **_kwargs: type("Profile", (), {"state": "weak"})(),
    )
    monkeypatch.setattr(
        module,
        "review_b2_symbol_history",
        lambda **kwargs: {
            "code": kwargs["code"],
            "pick_date": kwargs["pick_date"],
            "chart_path": kwargs["chart_path"],
            "review_type": "baseline",
            "trend_structure": 4.0,
            "price_position": 5.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 5.0,
            "macd_phase": 4.2,
            "total_score": 4.02,
            "signal": "B2",
            "signal_type": "trend_start",
            "verdict": "PASS",
            "elastic_watch": False,
            "elastic_watch_reason": None,
            "watch_score": None,
            "watch_tier": None,
            "comment": "new baseline",
        },
    )
    monkeypatch.setattr(
        module,
        "collect_review_samples",
        lambda **_kwargs: [
            {
                "method": "b2",
                "pick_date": "2026-04-10",
                "code": "000001.SZ",
                "total_score": 4.02,
                "trend_structure": 4.0,
                "price_position": 5.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 4.2,
                "verdict": "PASS",
                "ret3_pct": 1.5,
                "ret5_pct": 2.5,
            }
        ],
    )

    args = module.parse_args(
        [
            "--start-date",
            "2026-04-10",
            "--end-date",
            "2026-04-10",
            "--source-runtime-root",
            str(runtime_root),
            "--prepared-root",
            str(prepared_root),
            "--artifact-dir",
            str(artifact_dir),
        ]
    )

    assert module.main(args) == 0

    rewritten = json.loads((artifact_dir / "reviews" / "2026-04-10.b2" / "summary.json").read_text(encoding="utf-8"))
    item = rewritten["recommendations"][0]
    assert item["baseline_review"]["total_score"] == 4.02
    assert item["baseline_review"]["verdict"] == "PASS"
    assert item["total_score"] == 4.02
    assert item["verdict"] == "PASS"
    frame = pd.read_csv(artifact_dir / "samples.csv")
    assert frame.loc[0, "total_score"] == 4.02
    assert frame.loc[0, "verdict"] == "PASS"


def test_recompute_b2_baseline_resolves_environment_profile_per_pick_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_recompute_module()

    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b2",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "pick_date": "2026-04-10",
                        "chart_path": "/tmp/000001.SZ_day.png",
                        "baseline_review": {"signal": "B2"},
                        "total_score": 3.2,
                        "verdict": "WATCH",
                    }
                ],
                "excluded": [],
                "failures": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    artifact_dir = tmp_path / "candidate"

    monkeypatch.setattr(
        module,
        "_load_prepared_for_pick_date",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2026-04-10",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.9,
                    "close": 10.2,
                    "vol": 1000.0,
                    "zxdq": 9.8,
                    "zxdkx": 9.7,
                }
            ]
        ),
    )

    captured: dict[str, object] = {}

    def fake_resolve_profile_for_pick_date(**kwargs):
        captured["pick_date"] = kwargs["pick_date"]
        return type("Profile", (), {"state": "strong"})()

    monkeypatch.setattr(module, "_resolve_profile_for_pick_date", fake_resolve_profile_for_pick_date)
    monkeypatch.setattr(
        module,
        "review_b2_symbol_history",
        lambda **kwargs: {
            "code": kwargs["code"],
            "pick_date": kwargs["pick_date"],
            "chart_path": kwargs["chart_path"],
            "review_type": "baseline",
            "trend_structure": 4.0,
            "price_position": 5.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 5.0,
            "macd_phase": 4.2,
            "total_score": 4.02,
            "signal": "B2",
            "signal_type": "trend_start",
            "verdict": kwargs["profile"].state.upper(),
            "elastic_watch": False,
            "elastic_watch_reason": None,
            "watch_score": None,
            "watch_tier": None,
            "comment": "new baseline",
        },
    )
    monkeypatch.setattr(module, "collect_review_samples", lambda **_kwargs: [])

    args = module.parse_args(
        [
            "--start-date",
            "2026-04-10",
            "--end-date",
            "2026-04-10",
            "--source-runtime-root",
            str(runtime_root),
            "--prepared-root",
            str(prepared_root),
            "--artifact-dir",
            str(artifact_dir),
        ]
    )

    assert module.main(args) == 0
    assert captured["pick_date"] == "2026-04-10"
    rewritten = json.loads((artifact_dir / "reviews" / "2026-04-10.b2" / "summary.json").read_text(encoding="utf-8"))
    assert rewritten["recommendations"][0]["baseline_review"]["verdict"] == "STRONG"


def test_recompute_b2_baseline_reads_environment_profile_from_artifact_env_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_recompute_module()

    runtime_root = tmp_path / "runtime"
    review_dir = runtime_root / "reviews" / "2026-04-10.b2"
    review_dir.mkdir(parents=True)
    (review_dir / "summary.json").write_text(
        json.dumps(
            {
                "pick_date": "2026-04-10",
                "method": "b2",
                "recommendations": [
                    {
                        "code": "000001.SZ",
                        "pick_date": "2026-04-10",
                        "chart_path": "/tmp/000001.SZ_day.png",
                        "baseline_review": {"signal": "B2"},
                        "total_score": 3.2,
                        "verdict": "WATCH",
                    }
                ],
                "excluded": [],
                "failures": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    prepared_root = tmp_path / "prepared"
    prepared_root.mkdir()
    artifact_dir = tmp_path / "candidate"
    env_runtime = artifact_dir / "env-runtime"
    env_runtime.mkdir(parents=True)

    monkeypatch.setattr(
        module,
        "_load_prepared_for_pick_date",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2026-04-10",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.9,
                    "close": 10.2,
                    "vol": 1000.0,
                    "zxdq": 9.8,
                    "zxdkx": 9.7,
                }
            ]
        ),
    )

    captured: dict[str, object] = {}

    def fake_resolve_profile_for_pick_date(**kwargs):
        captured["runtime_root"] = kwargs["runtime_root"]
        return type("Profile", (), {"state": "strong"})()

    monkeypatch.setattr(module, "_resolve_profile_for_pick_date", fake_resolve_profile_for_pick_date)
    monkeypatch.setattr(
        module,
        "review_b2_symbol_history",
        lambda **kwargs: {
            "code": kwargs["code"],
            "pick_date": kwargs["pick_date"],
            "chart_path": kwargs["chart_path"],
            "review_type": "baseline",
            "trend_structure": 4.0,
            "price_position": 5.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 5.0,
            "macd_phase": 4.2,
            "total_score": 4.02,
            "signal": "B2",
            "signal_type": "trend_start",
            "verdict": "PASS",
            "elastic_watch": False,
            "elastic_watch_reason": None,
            "watch_score": None,
            "watch_tier": None,
            "comment": "new baseline",
        },
    )
    monkeypatch.setattr(module, "collect_review_samples", lambda **_kwargs: [])

    args = module.parse_args(
        [
            "--start-date",
            "2026-04-10",
            "--end-date",
            "2026-04-10",
            "--source-runtime-root",
            str(runtime_root),
            "--prepared-root",
            str(prepared_root),
            "--artifact-dir",
            str(artifact_dir),
        ]
    )

    assert module.main(args) == 0
    assert captured["runtime_root"] == env_runtime
