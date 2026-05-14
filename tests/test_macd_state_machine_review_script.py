from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "macd_state_machine_review.py"
    spec = importlib.util.spec_from_file_location("macd_state_machine_review", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_manual_review_notes_extracts_codes_and_pick_dates(tmp_path: Path) -> None:
    module = _load_module()
    notes = tmp_path / "macd_review_notes.md"
    notes.write_text(
        """
## 1. 301667.SZ · 纳百川

| 入选日期 | 2026-04-09（当日 B3, rebound） |

## 2. 000096.SZ · 广聚能源

| 入选日期 | 2026-02-24（当日 B2, rebound） |
""",
        encoding="utf-8",
    )

    samples = module.parse_manual_review_notes(notes)

    assert [(item.code, item.pick_date) for item in samples] == [
        ("301667.SZ", "2026-04-09"),
        ("000096.SZ", "2026-02-24"),
    ]


def test_parse_manual_review_notes_extracts_user_judgment_section(tmp_path: Path) -> None:
    module = _load_module()
    notes = tmp_path / "macd_review_notes.md"
    notes.write_text(
        """
## 1. 300166.SZ · 东方国信

| 入选日期 | 2026-02-09（当日 B2, trend_start） |

### 用户判断

> 日线MACD水上金叉，三浪启动第一天。
> 周线MACD重新增加，脱离底背离，是绝对的机会。

### CLI Baseline Review 原文

> baseline
""",
        encoding="utf-8",
    )

    samples = module.parse_manual_review_notes(notes)

    assert len(samples) == 1
    assert "三浪启动第一天" in samples[0].manual_note
    assert "脱离底背离" in samples[0].manual_note


def test_load_worst_negative_samples_reads_csv_rows(tmp_path: Path) -> None:
    module = _load_module()
    csv_path = tmp_path / "worst_negative_category_samples.csv"
    csv_path.write_text(
        "pick_date,code,signal,signal_type,verdict,total_score,ret5_pct,macd_category,comment,chart_path,review_path\n"
        "2026-04-09,301667.SZ,B3,rebound,FAIL,2.13,25.22,周待启动-日降,comment,/tmp/chart.png,/tmp/review.json\n",
        encoding="utf-8",
    )

    samples = module.load_worst_negative_samples(csv_path)

    assert len(samples) == 1
    assert samples[0].code == "301667.SZ"
    assert samples[0].pick_date == "2026-04-09"
    assert samples[0].source == "worst_negative_csv"


def test_infer_manual_expectation_extracts_daily_stage_and_rating() -> None:
    module = _load_module()

    assert module.infer_manual_expectation(
        module.ReviewSample(
            code="301667.SZ",
            pick_date="2026-04-09",
            source="manual_notes",
            manual_note="日MACD一浪后二浪回调末期，存在底背离。",
        )
    ).daily_stage == "wave2_end"
    assert module.infer_manual_expectation(
        module.ReviewSample(
            code="300166.SZ",
            pick_date="2026-02-09",
            source="manual_notes",
            manual_note="日线MACD水上金叉，三浪启动第一天。周线脱离底背离，是绝对的机会。",
        )
    ).daily_stage == "odd_start"
    assert module.infer_manual_expectation(
        module.ReviewSample(
            code="300152.SZ",
            pick_date="2026-03-09",
            source="manual_notes",
            manual_note="日MACD 2浪末，周MACD水下，且红MACD缩短，FAIL是没问题的。",
        )
    ).rating == "fail"
    assert module.infer_manual_expectation(
        module.ReviewSample(
            code="603175.SH",
            pick_date="2026-04-08",
            source="manual_notes",
            manual_note="日MACD二浪调整修复阶段，还未启动。周MACD一浪启动后正在强化。",
        )
    ).daily_stage == "wave2_repair"
    risk_watch = module.infer_manual_expectation(
        module.ReviewSample(
            code="301609.SZ",
            pick_date="2026-02-25",
            source="manual_notes",
            manual_note="日MACD二浪调整修复阶段，还未启动。周MACD属于未上水的强化阶段，属于风险股，应该给watch。",
        )
    )
    assert risk_watch.weekly_stage == "underwater_strengthening"
    assert risk_watch.rating == "watch"


def test_classify_observed_daily_stage_from_state_machine_result() -> None:
    module = _load_module()

    assert module.classify_observed_daily_stage(
        {
            "current_state": "even_wave_forming",
            "even_repair_started": True,
            "current_wave_index": 2,
        }
    ) == "wave2_repair"
    assert module.classify_observed_daily_stage(
        {
            "current_state": "even_wave_forming",
            "even_repair_started": False,
            "current_wave_index": 2,
        }
    ) == "wave2_adjusting"
    assert module.classify_observed_daily_stage(
        {
            "current_state": "even_wave_forming",
            "even_repair_started": True,
            "current_wave_index": 2,
            "golden_cross_imminent": True,
        }
    ) == "odd_start_imminent"
    assert module.classify_observed_daily_stage(
        {
            "current_state": "odd_wave_forming",
            "even_repair_started": False,
            "current_wave_index": 3,
        }
    ) == "odd_start"


def test_build_alignment_accepts_wave2_end_and_repair_as_same_family() -> None:
    module = _load_module()

    alignment = module.build_alignment(
        module.ReviewSample(
            code="301667.SZ",
            pick_date="2026-04-09",
            source="manual_notes",
            manual_note="日MACD一浪后二浪回调末期。",
        ),
        {
            "current_state": "even_wave_forming",
            "even_repair_started": True,
            "current_wave_index": 2,
        },
        {"current_state": "pre_wave1_pushing"},
    )

    assert alignment["observed_daily_stage"] == "wave2_repair"
    assert alignment["daily_alignment"] == "match"


def test_build_alignment_accepts_odd_start_imminent_as_same_family() -> None:
    module = _load_module()

    alignment = module.build_alignment(
        module.ReviewSample(
            code="300166.SZ",
            pick_date="2026-02-09",
            source="manual_notes",
            manual_note="日线MACD水上金叉，三浪启动第一天。",
        ),
        {
            "current_state": "even_wave_forming",
            "even_repair_started": True,
            "current_wave_index": 2,
            "golden_cross_imminent": True,
        },
        {"current_state": "pre_wave1_pushing"},
    )

    assert alignment["observed_daily_stage"] == "odd_start_imminent"
    assert alignment["daily_alignment"] == "match"


def test_build_alignment_accepts_odd_start_and_wave2_repair_as_same_family() -> None:
    module = _load_module()

    alignment = module.build_alignment(
        module.ReviewSample(
            code="301658.SZ",
            pick_date="2026-02-03",
            source="manual_notes",
            manual_note="日MACD不强，属于不严格的三浪启动。",
        ),
        {
            "current_state": "even_wave_forming",
            "even_repair_started": True,
            "current_wave_index": 2,
            "golden_cross_imminent": False,
        },
        {"current_state": "pre_wave1_pushing"},
    )

    assert alignment["observed_daily_stage"] == "wave2_repair"
    assert alignment["daily_alignment"] == "match"


def test_classify_observed_daily_stage_ignores_stale_imminent_event_without_current_flag() -> None:
    module = _load_module()

    observed = module.classify_observed_daily_stage(
        {
            "current_state": "even_wave_forming",
            "even_repair_started": True,
            "current_wave_index": 2,
            "events": ["golden_cross_imminent"],
            "golden_cross_imminent": False,
        }
    )

    assert observed == "wave2_repair"


def test_summarize_alignments_counts_manual_review_results() -> None:
    module = _load_module()

    summary = module.summarize_alignments(
        [
            {
                "code": "301667.SZ",
                "pick_date": "2026-04-09",
                "alignment": {"daily_alignment": "match"},
            },
            {
                "code": "000096.SZ",
                "pick_date": "2026-02-24",
                "alignment": {"daily_alignment": "mismatch"},
            },
            {
                "code": "603175.SH",
                "pick_date": "2026-04-08",
                "alignment": {"daily_alignment": "near"},
            },
        ]
    )

    assert summary["total"] == 3
    assert summary["match"] == 1
    assert summary["near"] == 1
    assert summary["mismatch"] == 1
    assert summary["mismatches"] == ["000096.SZ@2026-02-24"]
