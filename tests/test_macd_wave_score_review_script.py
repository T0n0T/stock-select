from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from stock_select.analysis.macd_wave_score import MacdScoreBreakdown


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "macd_wave_score_review.py"
    spec = importlib.util.spec_from_file_location("macd_wave_score_review", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_args_defaults_to_research_output_dir() -> None:
    module = _load_module()

    args = module.parse_args([])

    assert "macd_wave_score" in str(args.output_dir)


def test_score_sample_writes_macd_only_fields(monkeypatch, tmp_path: Path) -> None:
    module = _load_module()

    def fake_fetch_symbol_history(*_args, **_kwargs):
        return pd.DataFrame(
            {
                "trade_date": pd.date_range("2026-03-01", periods=12, freq="B"),
                "close": [10.0, 10.2, 10.1, 10.4, 10.6, 10.5, 10.8, 10.9, 11.0, 11.1, 11.0, 11.2],
            }
        )

    monkeypatch.setattr("stock_select.db_access.fetch_symbol_history", fake_fetch_symbol_history)
    monkeypatch.setattr(
        module,
        "compute_weekly_and_daily_stages",
        lambda _history: ("weekly-stage", "daily-stage"),
    )
    monkeypatch.setattr(
        module,
        "score_macd_state_machine_combo",
        lambda **_kwargs: MacdScoreBreakdown(
            score_1_to_5=4.82,
            raw_score=95.5,
            weekly_score=29.0,
            daily_score=34.0,
            combo_score=20.0,
            risk_adjustment=8.0,
            method_bias=4.5,
            setup_tag="pre_wave3_imminent",
            risk_flags=("bottom_divergence_valid",),
            reason="test reason",
            review_context={"weekly_wave_context": "周线", "daily_wave_context": "日线", "wave_combo_context": "组合"},
        ),
    )

    result = module.score_sample(
        object(),
        module.ReviewSample(code="000001.SZ", pick_date="2026-04-10", source="test"),
        method="b2",
        lookback_days=420,
    )

    assert result["code"] == "000001.SZ"
    assert result["pick_date"] == "2026-04-10"
    assert "macd_score" in result
    assert "review_context" in result
    assert "baseline_review" not in result


def test_write_artifacts_writes_research_outputs_only(tmp_path: Path) -> None:
    module = _load_module()
    output_dir = tmp_path / "runtime" / "research" / "macd_wave_score" / "smoke"
    results = [
        {
            "code": "000001.SZ",
            "pick_date": "2026-04-10",
            "macd_score": 4.82,
            "setup_tag": "pre_wave3_imminent",
            "review_context": {"weekly_wave_context": "周线", "daily_wave_context": "日线", "wave_combo_context": "组合"},
        }
    ]
    summary = {
        "total": 1,
        "score_buckets": {"4.7-5.0": 1},
        "setup_tag_counts": {"pre_wave3_imminent": 1},
        "top_samples": [{"code": "000001.SZ", "pick_date": "2026-04-10", "macd_score": 4.82}],
    }

    module.write_artifacts(output_dir=output_dir, results=results, summary=summary)

    assert (output_dir / "macd_score_samples.jsonl").exists()
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "summary.md").exists()
    assert not (tmp_path / "runtime" / "reviews").exists()


def test_summarize_scores_includes_buckets_setup_counts_and_top_samples() -> None:
    module = _load_module()

    summary = module.summarize_scores(
        [
            {"code": "000001.SZ", "pick_date": "2026-04-10", "macd_score": 4.82, "setup_tag": "pre_wave3_imminent"},
            {"code": "000002.SZ", "pick_date": "2026-04-11", "macd_score": 4.45, "setup_tag": "even_repairing"},
            {"code": "000003.SZ", "pick_date": "2026-04-12", "macd_score": 3.80, "setup_tag": "even_repairing"},
            {"code": "000004.SZ", "pick_date": "2026-04-13", "macd_score": 2.90, "setup_tag": "cycle_ended"},
            {"code": "000005.SZ", "pick_date": "2026-04-14", "macd_score": 2.10, "setup_tag": "cycle_ended"},
        ]
    )

    assert summary["score_buckets"] == {
        "1.0-2.4": 1,
        "2.5-3.3": 1,
        "3.4-4.1": 1,
        "4.2-4.6": 1,
        "4.7-5.0": 1,
    }
    assert summary["setup_tag_counts"] == {
        "pre_wave3_imminent": 1,
        "even_repairing": 2,
        "cycle_ended": 2,
    }
    assert summary["top_samples"][0]["code"] == "000001.SZ"
    assert summary["top_samples"][0]["pick_date"] == "2026-04-10"


def test_render_summary_markdown_includes_distribution_and_top_examples() -> None:
    module = _load_module()
    summary = {
        "total": 2,
        "score_buckets": {"4.7-5.0": 1, "4.2-4.6": 1},
        "setup_tag_counts": {"pre_wave3_imminent": 1, "even_repairing": 1},
        "top_samples": [
            {"code": "000001.SZ", "pick_date": "2026-04-10", "macd_score": 4.82},
            {"code": "000002.SZ", "pick_date": "2026-04-11", "macd_score": 4.45},
        ],
    }

    markdown = module.render_summary_markdown(summary)

    assert "score_buckets" in markdown
    assert "setup_tag_counts" in markdown
    assert "000001.SZ @ 2026-04-10" in markdown
    assert "pre_wave3_imminent" in markdown
