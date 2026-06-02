from __future__ import annotations

import unittest

from scripts import b2_review_layer_diagnostics as diag


class B2ReviewLayerDiagnosticsTest(unittest.TestCase):
    def test_ret3_bucket_boundaries_match_roadmap(self) -> None:
        cases = [
            (10.0, "A"),
            (5.0, "B"),
            (0.01, "C"),
            (0.0, "D"),
            (-4.99, "D"),
            (-5.0, "E"),
            (-10.0, "F"),
        ]

        for ret3, expected in cases:
            with self.subTest(ret3=ret3):
                self.assertEqual(diag.ret3_bucket(ret3), expected)

    def test_extract_feature_row_prefers_baseline_review_fields(self) -> None:
        review = {
            "code": "000001.SZ",
            "name": "Ping An",
            "verdict": "WATCH",
            "total_score": 3.7,
            "signal": "B2",
            "baseline_review": {
                "verdict": "PASS",
                "total_score": 4.21,
                "trend_structure": 4.0,
                "price_position": 3.0,
                "volume_behavior": 5.0,
                "previous_abnormal_move": 2.0,
                "macd_phase": 4.3,
                "signal": "B2",
                "signal_type": "trend_start",
                "daily_macd_wave_index": 0,
                "daily_macd_bottom_divergence": False,
                "weekly_macd_wave_index": 1,
                "weekly_macd_top_divergence": True,
            },
        }

        row = diag.extract_feature_row(
            pick_date="2026-05-25",
            code="000001.SZ",
            env="weak",
            review=review,
            forward={"ret3": 5.4, "ret5": -1.2},
        )

        self.assertEqual(row["current_verdict"], "WATCH")
        self.assertEqual(row["baseline_verdict"], "PASS")
        self.assertEqual(row["current_score"], 3.7)
        self.assertEqual(row["baseline_score"], 4.21)
        self.assertEqual(row["ret3_bucket"], "B")
        self.assertEqual(row["signal"], "B2")
        self.assertEqual(row["signal_type"], "trend_start")
        self.assertEqual(row["daily_macd_wave_index"], 0)
        self.assertEqual(row["daily_macd_bottom_divergence"], False)
        self.assertEqual(row["weekly_macd_wave_index"], 1)
        self.assertEqual(row["weekly_macd_top_divergence"], True)

    def test_segment_summary_counts_positive_and_negative_groups(self) -> None:
        rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "weak",
                "signal": "B2",
                "signal_type": "trend_start",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 1,
                "weekly_macd_wave_stage": "强势",
                "weekly_daily_combo_type": "rising:1|falling:2",
                "ret3": 6.0,
                "ret5": 7.0,
                "current_verdict": "WATCH",
            },
            {
                "date": "2026-05-26",
                "code": "000002.SZ",
                "env": "weak",
                "signal": "B2",
                "signal_type": "trend_start",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 1,
                "weekly_macd_wave_stage": "强势",
                "weekly_daily_combo_type": "rising:1|falling:2",
                "ret3": -1.0,
                "ret5": -2.0,
                "current_verdict": "PASS",
            },
        ]

        segments = diag.build_segments(rows)
        segment = segments["weak|B2|trend_start"]

        self.assertEqual(segment["sample_count"], 2)
        self.assertEqual(segment["ret3_ge_5_count"], 1)
        self.assertEqual(segment["ret3_le_0_count"], 1)
        self.assertEqual(segment["current_verdict_distribution"], {"PASS": 1, "WATCH": 1})

        macd_segments = diag.build_macd_segments(rows)
        macd_key = "weak|B2|trend_start|W:rising:1:强势|D:falling:2:修复|rising:1|falling:2"
        self.assertIn(macd_key, macd_segments)
        self.assertEqual(macd_segments[macd_key]["sample_count"], 2)

    def test_factor_segment_buckets_context_fields(self) -> None:
        row = {
            "env": "strong",
            "signal": "B2",
            "signal_type": "trend_start",
            "price_vs_90d_high": -4.0,
            "price_vs_90d_low": 85.0,
            "midline_state": "reclaim_volume",
            "support_stack_type": "bull_stack",
            "range_compression_20d": 0.35,
            "volume_ratio_5d": 1.4,
            "j_value": 105.0,
            "j_vs_d": 12.0,
            "ret3": 8.0,
            "ret5": 4.0,
            "current_verdict": "WATCH",
        }

        key = diag.factor_segment_key(row)
        self.assertEqual(
            key,
            "strong|B2|trend_start|price=near_high|midline=reclaim_volume|support=bull_stack|compression=tight|volume=expanding|kdj=overheat",
        )

        segments = diag.build_factor_segments([row])
        self.assertEqual(segments[key]["ret3_ge_5_count"], 1)

    def test_build_environment_comparisons_splits_positive_and_negative_groups(self) -> None:
        rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "weak",
                "signal": "B2",
                "signal_type": "trend_start",
                "ret3": 8.0,
                "ret5": 4.0,
                "ret3_bucket": "B",
                "current_verdict": "WATCH",
            },
            {
                "date": "2026-05-25",
                "code": "000002.SZ",
                "env": "weak",
                "signal": "B2",
                "signal_type": "trend_start",
                "ret3": -4.0,
                "ret5": -6.0,
                "ret3_bucket": "D",
                "current_verdict": "PASS",
            },
        ]

        comparisons = diag.build_environment_comparisons(rows)
        weak = comparisons["weak"]

        self.assertEqual(weak["sample_count"], 2)
        self.assertEqual(weak["positive_group"]["sample_count"], 1)
        self.assertEqual(weak["negative_group"]["sample_count"], 1)
        self.assertEqual(weak["watch_fail_high_ret3"][0]["code"], "000001.SZ")
        self.assertEqual(weak["pass_negative_ret3"][0]["code"], "000002.SZ")

    def test_build_stable_patterns_classifies_promising_and_risky_segments(self) -> None:
        segments = {
            "weak|good": {
                "sample_count": 12,
                "ret3_ge_5_count": 7,
                "ret3_le_0_count": 2,
                "ret3_mean": 4.2,
                "ret5_mean": 3.1,
                "typical_samples": [],
            },
            "weak|bad": {
                "sample_count": 12,
                "ret3_ge_5_count": 2,
                "ret3_le_0_count": 8,
                "ret3_mean": -2.5,
                "ret5_mean": -1.2,
                "typical_samples": [],
            },
            "weak|mixed": {
                "sample_count": 30,
                "ret3_ge_5_count": 8,
                "ret3_le_0_count": 10,
                "ret3_mean": 0.2,
                "ret5_mean": 0.1,
                "typical_samples": [],
            },
        }

        patterns = diag.build_stable_patterns(
            base_segments=segments,
            macd_segments={},
            factor_segments={},
            min_samples=10,
        )

        self.assertEqual(patterns["base"]["promising"][0]["segment"], "weak|good")
        self.assertEqual(patterns["base"]["risky"][0]["segment"], "weak|bad")
        self.assertEqual(patterns["base"]["mixed_high_sample"][0]["segment"], "weak|mixed")

    def test_build_macd_wave_rules_prefers_push_wave_stage_with_env_uplift(self) -> None:
        rows = []
        for index in range(6):
            rows.append(
                {
                    "date": "2026-05-25",
                    "code": f"00000{index}.SZ",
                    "env": "strong",
                    "signal": "B2",
                    "signal_type": "trend_start",
                    "weekly_macd_phase_type": "rising",
                    "weekly_macd_wave_index": 3,
                    "weekly_macd_wave_stage": "强势",
                    "daily_macd_phase_type": "falling",
                    "daily_macd_wave_index": 2,
                    "daily_macd_wave_stage": "修复",
                    "ret3": 6.0 if index < 4 else -1.0,
                    "ret5": 8.0 if index < 4 else -2.0,
                    "current_verdict": "WATCH",
                }
            )
        for index in range(4):
            rows.append(
                {
                    "date": "2026-05-25",
                    "code": f"10000{index}.SZ",
                    "env": "strong",
                    "signal": "B2",
                    "signal_type": "trend_start",
                    "weekly_macd_phase_type": "falling",
                    "weekly_macd_wave_index": 4,
                    "weekly_macd_wave_stage": "修复",
                    "daily_macd_phase_type": "falling",
                    "daily_macd_wave_index": 4,
                    "daily_macd_wave_stage": "修复",
                    "ret3": -2.0,
                    "ret5": -3.0,
                    "current_verdict": "WATCH",
                }
            )

        rules = diag.build_macd_wave_rules(rows, min_samples=5)
        top = rules["strong"]["positive_rules"][0]

        self.assertEqual(top["wave_rule"], "W:rising:3:强势|D:falling:2:修复")
        self.assertEqual(top["push_wave_side"], "weekly")
        self.assertAlmostEqual(top["positive_rate"], 0.667, places=3)
        self.assertGreater(top["positive_rate_uplift"], 0.2)

    def test_build_strong_pass_watch_ranking_report_compares_ranking_variants(self) -> None:
        def row(code: str, score: float, ret3: float, *, volume_ratio: float, kdj: float, verdict: str = "WATCH") -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": "strong",
                "current_verdict": verdict,
                "current_score": score,
                "signal": "B2",
                "signal_type": "trend_start",
                "price_vs_90d_high": -8.0,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": volume_ratio,
                "j_value": kdj,
                "j_vs_d": 0.0,
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "ret3": ret3,
                "ret5": ret3 + 1.0,
            }

        rows = [
            row("000001.SZ", 4.8, -2.0, volume_ratio=0.9, kdj=70.0, verdict="PASS"),
            row("000002.SZ", 4.7, -1.0, volume_ratio=0.9, kdj=70.0, verdict="PASS"),
            row("000003.SZ", 4.6, 1.0, volume_ratio=0.9, kdj=70.0, verdict="PASS"),
            row("000004.SZ", 4.0, 8.0, volume_ratio=1.5, kdj=45.0),
            row("000005.SZ", 3.9, 7.0, volume_ratio=1.5, kdj=45.0),
            row("000006.SZ", 3.8, 6.0, volume_ratio=1.5, kdj=45.0),
        ]

        report = diag.build_strong_pass_watch_ranking_report(rows)

        self.assertEqual(report["sample_count"], 6)
        self.assertEqual(report["candidate_count"], 6)
        self.assertEqual(report["family_stats"]["S-A"]["ret3_ge_5_count"], 3)
        self.assertIn("conservative_rank", report["top3_comparison"])
        self.assertIn("s_a_priority", report["top3_comparison"])
        self.assertIn("strong_v1_rank", report["top3_comparison"])
        self.assertEqual(report["daily_top3"][0]["s_a_priority"][0]["code"], "000004.SZ")

    def test_strong_v2_rank_penalizes_repeated_negative_groups(self) -> None:
        def row(
            code: str,
            score: float,
            ret3: float,
            *,
            signal: str = "B2",
            signal_type: str = "trend_start",
            price_high: float = -8.0,
            volume_ratio: float = 1.4,
            kdj: float = 45.0,
            j_vs_d: float = 0.0,
            hist_state: str = "red_expanding",
            price_turnover: str = "price_turnover_rise",
        ) -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": "strong",
                "current_verdict": "WATCH",
                "current_score": score,
                "signal": signal,
                "signal_type": signal_type,
                "price_vs_90d_high": price_high,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": volume_ratio,
                "j_value": kdj,
                "j_vs_d": j_vs_d,
                "daily_macd_hist_state": hist_state,
                "price_turnover_state": price_turnover,
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "ret3": ret3,
                "ret5": ret3 + 1.0,
            }

        rows = [
            row(
                "000001.SZ",
                4.95,
                -3.0,
                signal="B3",
                signal_type="rebound",
                hist_state="red_expanding",
                price_turnover="mixed",
                kdj=70.0,
                j_vs_d=5.0,
            ),
            row("000002.SZ", 4.65, 6.0, volume_ratio=0.9),
            row("000003.SZ", 4.55, 7.0, volume_ratio=0.9),
            row("000004.SZ", 4.5, 8.0, volume_ratio=0.9),
        ]

        report = diag.build_strong_pass_watch_ranking_report(rows)

        self.assertIn("strong_v2_rank", report["top3_comparison"])
        self.assertEqual(report["daily_top3"][0]["strong_v1_rank"][0]["code"], "000001.SZ")
        self.assertNotIn("000001.SZ", [sample["code"] for sample in report["daily_top3"][0]["strong_v2_rank"]])
        ranked = {sample["code"]: sample for sample in report["ranked_samples"]}
        self.assertIn("b3_rebound_mixed", ranked["000001.SZ"]["strong_v2_risk_flags"])

    def test_strong_v3_rank_penalizes_b2_near_high_red_expanding_losers(self) -> None:
        def row(code: str, score: float, ret3: float, *, hist_state: str = "red_expanding") -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": "strong",
                "current_verdict": "WATCH",
                "current_score": score,
                "signal": "B2",
                "signal_type": "trend_start",
                "price_vs_90d_high": -4.0,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.4,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "daily_macd_hist_state": hist_state,
                "price_turnover_state": "price_turnover_rise",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "ret3": ret3,
                "ret5": ret3 + 1.0,
            }

        rows = [
            row("000001.SZ", 4.95, -3.0),
            row("000002.SZ", 4.65, 6.0, hist_state="green_or_zero"),
            row("000003.SZ", 4.55, 7.0, hist_state="green_or_zero"),
            row("000004.SZ", 4.50, 8.0, hist_state="green_or_zero"),
        ]

        report = diag.build_strong_pass_watch_ranking_report(rows)

        self.assertEqual(report["daily_top3"][0]["strong_v1_rank"][0]["code"], "000001.SZ")
        self.assertNotIn("000001.SZ", [sample["code"] for sample in report["daily_top3"][0]["strong_v3_rank"]])
        ranked = {sample["code"]: sample for sample in report["ranked_samples"]}
        self.assertIn("b2_near_high_expanding_red_turnover_rise", ranked["000001.SZ"]["strong_v3_risk_flags"])

    def test_build_neutral_watch_ranking_report_boosts_positive_skeleton_and_penalizes_veto(self) -> None:
        def row(code: str, score: float, ret3: float, *, signal_type: str = "trend_start", price_high: float = -8.0, hist_state: str = "green_or_zero") -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": "neutral",
                "current_verdict": "WATCH",
                "current_score": score,
                "signal": "B2",
                "signal_type": signal_type,
                "price_vs_90d_high": price_high,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.0,
                "j_value": 60.0,
                "j_vs_d": -2.0,
                "daily_macd_hist_state": hist_state,
                "price_turnover_state": "price_turnover_rise",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 2,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "bbi_bias_state": "above_extended",
                "bias_bucket": "positive",
                "obv_state": "flat",
                "ret3": ret3,
                "ret5": ret3 + 1.0,
            }

        rows = [
            row("000001.SZ", 4.8, -3.0, signal_type="rebound", price_high=-25.0),
            row("000002.SZ", 4.2, 7.0),
            row("000003.SZ", 4.1, 8.0),
            row("000004.SZ", 4.0, 6.0),
        ]

        report = diag.build_neutral_watch_ranking_report(rows)

        self.assertEqual(report["daily_top3"][0]["current_score"][0]["code"], "000001.SZ")
        self.assertNotIn("000001.SZ", [sample["code"] for sample in report["daily_top3"][0]["neutral_v1_rank"]])
        ranked = {sample["code"]: sample for sample in report["ranked_samples"]}
        self.assertIn("neutral_b2_rebound_extended_no_red", ranked["000001.SZ"]["neutral_risk_flags"])
        self.assertGreater(ranked["000002.SZ"]["neutral_positive_score"], 0.0)

    def test_build_neutral_v1_stability_report_flags_daily_regressions_and_losses(self) -> None:
        def sample(
            date: str,
            code: str,
            current_score: float,
            neutral_score: float,
            ret3: float,
            *,
            flags: list[str] | None = None,
        ) -> dict:
            return {
                "date": date,
                "code": code,
                "verdict": "WATCH",
                "current_score": current_score,
                "neutral_v1_rank_score": neutral_score,
                "neutral_positive_score": max(0.0, neutral_score - current_score),
                "neutral_risk_penalty": 0.0,
                "neutral_risk_flags": flags or [],
                "ret3": ret3,
                "ret5": ret3 + 1.0,
                "signal": "B2",
                "signal_type": "trend_start",
                "factor_segment": "factor",
                "macd_wave_rule": "macd",
            }

        ranking_report = {
            "daily_top3": [
                {
                    "date": "2026-05-25",
                    "current_score": [
                        sample("2026-05-25", "000001.SZ", 5.0, 4.0, -2.0),
                        sample("2026-05-25", "000002.SZ", 4.9, 3.9, -1.0),
                        sample("2026-05-25", "000003.SZ", 4.8, 3.8, 1.0),
                    ],
                    "neutral_v1_rank": [
                        sample("2026-05-25", "000004.SZ", 4.0, 5.0, 8.0),
                        sample("2026-05-25", "000005.SZ", 3.9, 4.9, 7.0),
                        sample("2026-05-25", "000006.SZ", 3.8, 4.8, 6.0),
                    ],
                },
                {
                    "date": "2026-05-26",
                    "current_score": [
                        sample("2026-05-26", "000007.SZ", 5.0, 4.0, 5.0),
                        sample("2026-05-26", "000008.SZ", 4.9, 3.9, 4.0),
                        sample("2026-05-26", "000009.SZ", 4.8, 3.8, 3.0),
                    ],
                    "neutral_v1_rank": [
                        sample(
                            "2026-05-26",
                            "000010.SZ",
                            4.0,
                            5.0,
                            -6.0,
                            flags=["neutral_b2_near_high_expanding_macd_bad"],
                        ),
                        sample("2026-05-26", "000011.SZ", 3.9, 4.9, -2.0),
                        sample("2026-05-26", "000012.SZ", 3.8, 4.8, 2.0),
                    ],
                },
            ],
            "ranked_samples": [],
        }

        report = diag.build_neutral_v1_stability_report(ranking_report)

        self.assertEqual(report["daily_summary"]["improved_days"], 1)
        self.assertEqual(report["daily_summary"]["regressed_days"], 1)
        self.assertEqual(report["daily_deltas"][0]["ret3_ge_5_delta"], 3)
        self.assertEqual(report["daily_deltas"][1]["ret3_le_0_delta"], 2)
        self.assertEqual(report["regression_days"][0]["date"], "2026-05-26")
        self.assertEqual(report["top3_loss_summary"]["sample_count"], 2)
        self.assertIn("neutral_b2_near_high_expanding_macd_bad", report["top3_loss_risk_flags"])
        self.assertIn("B2|trend_start", report["top3_loss_signal_distribution"])

    def test_build_neutral_v2_veto_report_penalizes_loss_only_factor_groups(self) -> None:
        def sample(
            date: str,
            code: str,
            v1_score: float,
            ret3: float,
            factor: str,
            macd: str = "macd_ok",
        ) -> dict:
            return {
                "date": date,
                "code": code,
                "verdict": "WATCH",
                "current_score": v1_score - 0.2,
                "neutral_v1_rank_score": v1_score,
                "neutral_positive_score": 0.2,
                "neutral_risk_penalty": 0.0,
                "neutral_risk_flags": [],
                "ret3": ret3,
                "ret5": ret3 + 1.0,
                "signal": "B2",
                "signal_type": "trend_start",
                "factor_segment": factor,
                "macd_wave_rule": macd,
            }

        bad_factor = "neutral|B2|trend_start|price=upper|compression=normal|volume=expanding|kdj=rising"
        ok_factor = "neutral|B2|trend_start|price=upper|compression=tight|volume=normal|kdj=neutral"
        ranking_report = {
            "daily_top3": [
                {
                    "date": "2026-05-25",
                    "neutral_v1_rank": [
                        sample("2026-05-25", "000001.SZ", 5.0, -5.0, bad_factor),
                        sample("2026-05-25", "000002.SZ", 4.9, -3.0, bad_factor),
                        sample("2026-05-25", "000003.SZ", 4.8, 7.0, ok_factor),
                    ],
                    "current_score": [],
                }
            ],
            "ranked_samples": [
                sample("2026-05-25", "000001.SZ", 5.0, -5.0, bad_factor),
                sample("2026-05-25", "000002.SZ", 4.9, -3.0, bad_factor),
                sample("2026-05-25", "000003.SZ", 4.8, 7.0, ok_factor),
                sample("2026-05-25", "000004.SZ", 4.7, 8.0, ok_factor),
                sample("2026-05-25", "000005.SZ", 4.6, 9.0, ok_factor),
            ],
        }

        report = diag.build_neutral_v2_veto_report(ranking_report)

        self.assertIn(bad_factor, report["veto_candidates"]["factor"])
        self.assertEqual(report["top3_comparison"]["neutral_v1_rank"]["ret3_le_0_count"], 2)
        self.assertEqual(report["top3_comparison"]["neutral_v2_rank"]["ret3_le_0_count"], 0)
        penalized = {sample["code"]: sample for sample in report["penalized_samples"]}
        self.assertGreater(penalized["000001.SZ"]["neutral_v2_penalty"], 0.0)

    def test_build_pass_watch_high_ret3_group_report_finds_priority_groups(self) -> None:
        def sample(date: str, code: str, ret3: float, factor: str, score: float = 4.0) -> dict:
            return {
                "date": date,
                "code": code,
                "verdict": "WATCH",
                "current_score": score,
                "ret3": ret3,
                "ret5": ret3 + 1.0,
                "signal": "B2",
                "signal_type": "trend_start",
                "factor_segment": factor,
                "macd_wave_rule": "W:rising:3:背离|D:falling:4:修复",
            }

        factor = "strong|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral"
        other = "strong|B3|rebound|price=middle|midline=below_midline|support=close_above_ma60|compression=normal|volume=normal|kdj=low"
        report = diag.build_pass_watch_high_ret3_group_report(
            {
                "strong": {
                    "ranked_samples": [
                        sample("2026-05-25", "000001.SZ", 8.0, factor),
                        sample("2026-05-25", "000002.SZ", 2.0, other),
                        sample("2026-05-26", "000003.SZ", 7.0, factor),
                        sample("2026-05-26", "000004.SZ", 6.0, other),
                    ]
                }
            }
        )

        strong = report["environments"]["strong"]
        self.assertEqual(strong["high_ret3_count"], 3)
        self.assertEqual(strong["daily_best_summary"]["day_count"], 2)
        self.assertEqual(strong["daily_best_summary"]["best_ret3_gt_0_days"], 2)
        self.assertIn("B2|trend_start|price=upper_or_near_high|midline=above_hold|support=bull_stack", strong["daily_best_skeleton_distribution"])
        self.assertGreaterEqual(strong["priority_skeleton_groups"][0]["coverage"], 0.5)

    def test_build_env_skeleton_top1_report_uses_environment_specific_groups(self) -> None:
        def sample(date: str, code: str, score: float, ret3: float, factor: str) -> dict:
            return {
                "date": date,
                "code": code,
                "verdict": "WATCH",
                "current_score": score,
                "ret3": ret3,
                "ret5": ret3 + 1.0,
                "signal": "B2",
                "signal_type": "trend_start",
                "factor_segment": factor,
                "macd_wave_rule": "macd",
            }

        strong_group = "B2|trend_start|price=upper_or_near_high|midline=above_hold|support=bull_stack"
        weak_group = "B3|rebound|price=upper_or_near_high|midline=above_hold|support=bull_stack"
        strong_factor = "strong|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral"
        weak_factor = "weak|B3|rebound|price=near_high|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=rising"
        other_factor = "strong|B2|rebound|price=middle|midline=below_midline|support=close_above_ma60|compression=normal|volume=normal|kdj=low"
        high_report = {
            "environments": {
                "strong": {"priority_skeleton_groups": [{"group": strong_group, "coverage": 0.6}]},
                "weak": {"priority_skeleton_groups": [{"group": weak_group, "coverage": 0.5}]},
            }
        }
        ranking_reports = {
            "strong": {
                "ranked_samples": [
                    sample("2026-05-25", "000001.SZ", 4.0, -2.0, other_factor),
                    sample("2026-05-25", "000002.SZ", 3.8, 8.0, strong_factor),
                ]
            },
            "weak": {
                "ranked_samples": [
                    sample("2026-05-25", "000003.SZ", 4.0, -3.0, other_factor),
                    sample("2026-05-25", "000004.SZ", 3.8, 7.0, weak_factor),
                ]
            },
        }

        report = diag.build_env_skeleton_top1_report(high_report, ranking_reports)

        self.assertEqual(report["environments"]["strong"]["top1_comparison"]["skeleton_rank"]["ret3_gt_0_count"], 1)
        self.assertEqual(report["environments"]["weak"]["top1_comparison"]["skeleton_rank"]["ret3_gt_0_count"], 1)
        self.assertEqual(report["environments"]["strong"]["skeleton_top1_from_group_days"], 1)
        self.assertEqual(report["environments"]["weak"]["skeleton_top1_from_group_days"], 1)

    def test_build_weak_neutral_top3_followup_report_tracks_hit_rates_and_losses(self) -> None:
        def sample(date: str, code: str, ret3: float, score_key: str, score: float, factor: str, macd: str) -> dict:
            return {
                "date": date,
                "code": code,
                "verdict": "WATCH",
                score_key: score,
                "current_score": score - 0.1,
                "ret3": ret3,
                "ret5": ret3 + 1.0,
                "factor_segment": factor,
                "macd_wave_rule": macd,
                "weak_risk_flags": ["weak_bad"] if ret3 <= 0 else [],
                "weak_v3_risk_flags": [],
                "neutral_risk_flags": ["neutral_bad"] if ret3 <= 0 else [],
            }

        weak_report = {
            "daily_top3": [
                {
                    "date": "2026-05-25",
                    "weak_v3_rank": [
                        sample("2026-05-25", "000001.SZ", 8.0, "weak_v3_rank_score", 5.0, "weak_good", "macd_good"),
                        sample("2026-05-25", "000002.SZ", -2.0, "weak_v3_rank_score", 4.9, "weak_bad", "macd_bad"),
                    ],
                    "weak_v4_rank": [
                        sample("2026-05-25", "000003.SZ", 6.0, "weak_v4_rank_score", 5.1, "weak_good", "macd_good"),
                    ],
                },
                {
                    "date": "2026-05-26",
                    "weak_v3_rank": [
                        sample("2026-05-26", "000004.SZ", -1.0, "weak_v3_rank_score", 5.0, "weak_bad", "macd_bad"),
                    ],
                    "weak_v4_rank": [
                        sample("2026-05-26", "000005.SZ", -1.0, "weak_v4_rank_score", 5.0, "weak_bad", "macd_bad"),
                    ],
                },
            ]
        }
        neutral_report = {
            "daily_top3": [
                {
                    "date": "2026-05-25",
                    "neutral_v1_rank": [
                        sample("2026-05-25", "000006.SZ", 7.0, "neutral_v1_rank_score", 5.0, "neutral_good", "macd_good"),
                        sample("2026-05-25", "000007.SZ", -3.0, "neutral_v1_rank_score", 4.9, "neutral_bad", "macd_bad"),
                    ],
                }
            ]
        }

        report = diag.build_weak_neutral_top3_followup_report(weak_report, neutral_report)

        weak_v3 = report["environments"]["weak"]["variants"]["weak_v3_rank"]
        self.assertEqual(weak_v3["top3_summary"]["ret3_ge_5_count"], 1)
        self.assertEqual(weak_v3["daily_hit_summary"]["hit_days"], 1)
        self.assertEqual(weak_v3["daily_hit_summary"]["day_count"], 2)
        self.assertIn("weak_bad", weak_v3["loss_factor_distribution"])
        neutral_v1 = report["environments"]["neutral"]["variants"]["neutral_v1_rank"]
        self.assertEqual(neutral_v1["daily_hit_summary"]["hit_rate"], 1.0)
        self.assertIn("neutral_bad", neutral_v1["loss_factor_distribution"])

    def test_build_weak_final_tuning_report_selects_top3_penalty_candidate(self) -> None:
        target_factor = "weak|B2|trend_start|price=upper|midline=reclaim_volume|support=bull_stack|compression=tight|volume=expanding|kdj=rising"
        good_factor = "weak|B2|trend_start|price=upper|midline=above_hold|support=bull_stack|compression=tight|volume=normal|kdj=neutral"

        def sample(date: str, code: str, score: float, ret3: float, factor: str) -> dict:
            return {
                "date": date,
                "code": code,
                "verdict": "WATCH",
                "current_score": score,
                "weak_v3_rank_score": score,
                "weak_v4_rank_score": score,
                "ret3": ret3,
                "ret5": ret3 + 1.0,
                "factor_segment": factor,
                "weak_v3_risk_flags": [],
            }

        weak_report = {
            "ranked_samples": [
                sample("2026-05-25", "000001.SZ", 5.0, -2.0, target_factor),
                sample("2026-05-25", "000002.SZ", 4.9, 8.0, good_factor),
                sample("2026-05-25", "000008.SZ", 4.88, 7.0, good_factor),
                sample("2026-05-25", "000009.SZ", 4.86, 6.0, good_factor),
                sample("2026-05-26", "000003.SZ", 5.0, 9.0, good_factor),
                sample("2026-05-26", "000004.SZ", 4.9, -3.0, target_factor),
                sample("2026-05-26", "000010.SZ", 4.88, 8.0, good_factor),
                sample("2026-05-26", "000011.SZ", 4.86, 7.0, good_factor),
            ]
        }

        report = diag.build_weak_final_tuning_report(weak_report)

        final_top3 = report["scenarios"]["weak_v3_minus_reclaim"]["top3"]
        self.assertEqual(final_top3["ret3_ge_5_count"], 6)
        self.assertEqual(final_top3["ret3_le_0_count"], 0)
        self.assertEqual(report["recommended_top3_scenario"], "weak_v3_minus_reclaim")

    def test_build_weak_pass_watch_ranking_report_prefers_repair_groups(self) -> None:
        def row(
            code: str,
            score: float,
            ret3: float,
            *,
            signal: str = "B3",
            signal_type: str = "rebound",
            price_high: float = -4.0,
            volume_ratio: float = 1.0,
            kdj: float = 70.0,
            j_vs_d: float = 5.0,
            hist_state: str = "red_expanding",
            price_turnover: str = "price_up_turnover_not",
        ) -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": "weak",
                "current_verdict": "WATCH",
                "current_score": score,
                "signal": signal,
                "signal_type": signal_type,
                "price_vs_90d_high": price_high,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": volume_ratio,
                "j_value": kdj,
                "j_vs_d": j_vs_d,
                "daily_macd_hist_state": hist_state,
                "price_turnover_state": price_turnover,
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "背离",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "ret3": ret3,
                "ret5": ret3 + 1.0,
            }

        rows = [
            row(
                "000001.SZ",
                4.2,
                -3.0,
                signal="B3",
                signal_type="rebound",
                price_high=-20.0,
                kdj=35.0,
                hist_state="green_or_zero",
                price_turnover="mixed",
            ),
            row("000002.SZ", 4.0, 7.0),
            row("000003.SZ", 3.9, 8.0, signal="B3", signal_type="trend_start"),
            row("000004.SZ", 3.8, -1.0, signal="B2", signal_type="rebound"),
            row("000005.SZ", 3.78, 5.5, signal="B2", signal_type="trend_start", kdj=45.0, hist_state="green_or_zero"),
        ]

        report = diag.build_weak_pass_watch_ranking_report(rows)

        self.assertEqual(report["sample_count"], 5)
        self.assertIn("weak_v2_rank", report["top3_comparison"])
        self.assertNotIn("000001.SZ", [sample["code"] for sample in report["daily_top3"][0]["weak_v2_rank"]])
        ranked = {sample["code"]: sample for sample in report["ranked_samples"]}
        self.assertEqual(ranked["000002.SZ"]["family"], "W-A")
        self.assertIn("b3_rebound_extended_mixed", ranked["000001.SZ"]["weak_risk_flags"])

    def test_build_strong_pass_composition_report_summarizes_current_pass_basis(self) -> None:
        rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "strong",
                "current_verdict": "PASS",
                "current_score": 4.5,
                "signal": "B3",
                "signal_type": "trend_start",
                "price_vs_90d_high": -8.0,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 0.9,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "背离",
                "daily_macd_phase_type": "rising",
                "daily_macd_wave_index": 1,
                "daily_macd_wave_stage": "强势",
                "ret3": 6.0,
                "ret5": 7.0,
            },
            {
                "date": "2026-05-25",
                "code": "000002.SZ",
                "env": "strong",
                "current_verdict": "PASS",
                "current_score": 4.2,
                "signal": "B2",
                "signal_type": "trend_start",
                "price_vs_90d_high": -10.0,
                "price_vs_90d_low": 65.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.35,
                "volume_ratio_5d": 1.4,
                "j_value": 40.0,
                "j_vs_d": 0.0,
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "ret3": -1.0,
                "ret5": 2.0,
            },
            {
                "date": "2026-05-25",
                "code": "000003.SZ",
                "env": "strong",
                "current_verdict": "WATCH",
                "current_score": 4.0,
                "signal": "B2",
                "signal_type": "trend_start",
                "ret3": 8.0,
                "ret5": 9.0,
            },
        ]

        report = diag.build_strong_pass_composition_report(rows)

        self.assertEqual(report["sample_count"], 2)
        self.assertEqual(report["summary"]["ret3_ge_5_count"], 1)
        self.assertEqual(report["family_distribution"]["S-A"]["sample_count"], 1)
        self.assertEqual(report["signal_distribution"]["B3|trend_start"]["sample_count"], 1)
        self.assertGreater(report["indicator_hit_rates"]["bull_stack"], 0.9)

    def test_forward_returns_skips_future_rows_without_close(self) -> None:
        rows = [
            {"trade_date": "2026-05-25", "close": 10.0},
            {"trade_date": "2026-05-26", "close": None},
            {"trade_date": "2026-05-27", "close": 10.5},
            {"trade_date": "2026-05-28", "close": 11.0},
            {"trade_date": "2026-05-29", "close": 12.0},
            {"trade_date": "2026-06-01", "close": 13.0},
        ]

        forward = diag.forward_returns(rows, "2026-05-25")

        self.assertAlmostEqual(forward["ret3"], 20.0)
        self.assertEqual(forward["ret5"], None)

    def test_compute_context_features_from_price_history(self) -> None:
        rows = [
            {
                "trade_date": f"2026-05-{day:02d}",
                "open": 10.0 + day * 0.1,
                "high": 11.0 + day * 0.1,
                "low": 9.0 + day * 0.1,
                "close": 10.0 + day * 0.1,
                "vol": 100.0 + day,
            }
            for day in range(1, 31)
        ]

        features = diag.compute_context_features(rows, "2026-05-30")

        self.assertEqual(features["price_vs_90d_high"], -7.14)
        self.assertEqual(features["price_vs_90d_low"], 42.86)
        self.assertEqual(features["close_vs_ma25"], 10.17)
        self.assertEqual(features["close_vs_ma60"], None)
        self.assertEqual(features["midline_state"], "above_hold")
        self.assertEqual(features["support_stack_type"], "close_above_ma25")
        self.assertGreater(features["volume_ratio_5d"], 1.0)
        self.assertGreater(features["k_value"], 50.0)
        self.assertGreater(features["j_value"], features["d_value"])

    def test_compute_context_features_marks_red_macd_and_price_turnover_rise(self) -> None:
        rows = []
        close = 10.0
        for day in range(1, 45):
            close += 0.08 if day < 42 else 0.35
            rows.append(
                {
                    "trade_date": f"2026-05-{day:02d}",
                    "open": close - 0.2,
                    "high": close + 0.2,
                    "low": close - 0.3,
                    "close": close,
                    "vol": 100.0 + day,
                    "turnover_rate": 1.0 if day < 42 else 2.0 + day * 0.01,
                }
            )

        features = diag.compute_context_features(rows, "2026-05-44")

        self.assertEqual(features["daily_macd_hist_state"], "red_expanding")
        self.assertEqual(features["price_turnover_state"], "price_turnover_rise")
        self.assertEqual(features["price_up_1d"], True)
        self.assertEqual(features["turnover_up_1d"], True)

    def test_build_strong_b3_red_macd_report_splits_red_acceleration(self) -> None:
        rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "strong",
                "current_verdict": "WATCH",
                "signal": "B3",
                "signal_type": "trend_start",
                "daily_macd_hist_state": "red_expanding",
                "price_turnover_state": "price_turnover_rise",
                "ret3": 8.0,
                "ret5": 9.0,
            },
            {
                "date": "2026-05-25",
                "code": "000002.SZ",
                "env": "strong",
                "current_verdict": "WATCH",
                "signal": "B3",
                "signal_type": "trend_start",
                "daily_macd_hist_state": "green_or_zero",
                "price_turnover_state": "mixed",
                "ret3": -2.0,
                "ret5": -3.0,
            },
        ]

        report = diag.build_strong_b3_red_macd_report(rows)

        self.assertEqual(report["sample_count"], 2)
        self.assertIn("red_expanding|price_turnover_rise", report["condition_distribution"])
        self.assertEqual(report["condition_distribution"]["red_expanding|price_turnover_rise"]["ret3_ge_5_count"], 1)

    def test_build_strong_v1_negative_groups_report_traces_top_ranked_losers(self) -> None:
        def row(code: str, score: float, ret3: float, *, signal: str = "B2", signal_type: str = "trend_start") -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": "strong",
                "current_verdict": "WATCH",
                "current_score": score,
                "signal": signal,
                "signal_type": signal_type,
                "price_vs_90d_high": -4.0,
                "price_vs_90d_low": 80.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.4,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "daily_macd_hist_state": "red_expanding",
                "price_turnover_state": "mixed",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "rising",
                "daily_macd_wave_index": 1,
                "daily_macd_wave_stage": "背离",
                "ret3": ret3,
                "ret5": ret3 - 1.0,
            }

        report = diag.build_strong_v1_negative_groups_report(
            [
                row("000001.SZ", 4.8, -2.0, signal="B3", signal_type="rebound"),
                row("000002.SZ", 4.7, 8.0),
                row("000003.SZ", 4.6, -1.0),
                row("000004.SZ", 3.0, 6.0),
            ]
        )

        self.assertEqual(report["top3"]["sample_count"], 3)
        self.assertEqual(report["top3"]["negative_summary"]["sample_count"], 2)
        self.assertIn("other", report["top3"]["negative_family_distribution"])
        self.assertIn(
            "red_expanding|mixed|rebound|price=near_high|volume=expanding|kdj=rising",
            report["top3"]["negative_b3_condition_distribution"],
        )
        self.assertEqual(report["top3"]["worst_samples"][0]["code"], "000001.SZ")

    def test_build_weak_v2_negative_groups_report_traces_remaining_losers(self) -> None:
        def row(code: str, score: float, ret3: float, *, family_like: str = "other") -> dict:
            base = {
                "date": "2026-05-25",
                "code": code,
                "env": "weak",
                "current_verdict": "WATCH",
                "current_score": score,
                "signal": "B2",
                "signal_type": "trend_start",
                "price_vs_90d_high": -8.0,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.0,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "daily_macd_hist_state": "green_or_zero",
                "price_turnover_state": "price_turnover_rise",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 0,
                "weekly_macd_wave_stage": "背离",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 4,
                "daily_macd_wave_stage": "修复",
                "ret3": ret3,
                "ret5": ret3 - 1.0,
            }
            if family_like == "W-A":
                base.update(
                    {
                        "signal": "B3",
                        "signal_type": "rebound",
                        "price_vs_90d_high": -4.0,
                        "volume_ratio_5d": 1.0,
                        "daily_macd_hist_state": "red_expanding",
                        "price_turnover_state": "price_up_turnover_not",
                    }
                )
            return base

        report = diag.build_weak_v2_negative_groups_report(
            [
                row("000001.SZ", 4.2, -6.0, family_like="W-A"),
                row("000002.SZ", 4.1, 7.0, family_like="W-A"),
                row("000003.SZ", 4.0, -2.0),
                row("000004.SZ", 3.0, 6.0),
            ]
        )

        self.assertEqual(report["top3"]["sample_count"], 3)
        self.assertEqual(report["top3"]["negative_summary"]["sample_count"], 2)
        self.assertIn("W-A", report["top3"]["negative_family_distribution"])
        self.assertIn("B3|rebound|near_high|normal|rising|red_expanding|price_up_turnover_not", report["top3"]["negative_condition_distribution"])
        self.assertEqual(report["top3"]["worst_samples"][0]["code"], "000001.SZ")

    def test_build_weak_watch_positive_report_finds_upgrade_candidates_and_vetoes(self) -> None:
        def row(
            code: str,
            ret3: float,
            ret5: float,
            *,
            signal: str = "B3",
            signal_type: str = "rebound",
            price_high: float = -4.0,
            volume_ratio: float = 1.0,
            kdj: float = 70.0,
            j_vs_d: float = 5.0,
            hist_state: str = "red_expanding",
            price_turnover: str = "price_up_turnover_not",
            bbi_state: str = "above_extended",
            bias_bucket: str = "high_positive",
            obv_state: str = "rising",
            verdict: str = "WATCH",
            env: str = "weak",
        ) -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": env,
                "current_verdict": verdict,
                "current_score": 4.0,
                "signal": signal,
                "signal_type": signal_type,
                "price_vs_90d_high": price_high,
                "price_vs_90d_low": 70.0,
                "price_vs_90d_mid": 12.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": volume_ratio,
                "j_value": kdj,
                "j_vs_d": j_vs_d,
                "daily_macd_hist_state": hist_state,
                "price_turnover_state": price_turnover,
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "推升",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "bbi_bias_state": bbi_state,
                "bias_bucket": bias_bucket,
                "obv_state": obv_state,
                "ret3": ret3,
                "ret5": ret5,
            }

        rows = [
            row("000001.SZ", 6.0, 8.0),
            row("000002.SZ", 7.0, 9.0),
            row("000003.SZ", -2.0, -1.0),
            row("000004.SZ", -3.0, -2.0, price_high=-20.0, kdj=35.0, hist_state="green_or_zero", price_turnover="mixed"),
            row("000007.SZ", 0.0, 1.0, price_high=-20.0, kdj=35.0, hist_state="green_or_zero", price_turnover="mixed"),
            row("000005.SZ", 4.0, 6.0, verdict="PASS"),
            row("000006.SZ", 5.0, 6.0, env="neutral"),
        ]

        report = diag.build_weak_watch_positive_report(rows, min_samples=2)

        self.assertEqual(report["sample_count"], 5)
        self.assertEqual(report["return_groups"]["ret3_gt_0"]["sample_count"], 2)
        self.assertEqual(report["return_groups"]["ret5_gt_0"]["sample_count"], 3)
        self.assertEqual(report["return_groups"]["ret3_ge_5"]["sample_count"], 2)
        self.assertEqual(report["return_groups"]["ret3_le_0"]["sample_count"], 3)
        self.assertEqual(report["upgrade_candidates"][0]["condition"], "family_indicator")
        self.assertEqual(report["upgrade_candidates"][0]["key"], "W-A|bbi=above_extended|bias=high_positive|obv=rising")
        self.assertIn("b3_rebound_extended_mixed", report["veto_candidates"])
        self.assertEqual(report["veto_candidates"]["b3_rebound_extended_mixed"]["sample_count"], 2)

    def test_build_neutral_watch_positive_report_finds_candidates(self) -> None:
        def row(code: str, ret3: float, ret5: float, *, verdict: str = "WATCH", env: str = "neutral") -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": env,
                "current_verdict": verdict,
                "current_score": 4.0,
                "signal": "B3",
                "signal_type": "trend_start",
                "price_vs_90d_high": -8.0,
                "price_vs_90d_low": 70.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.35,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "daily_macd_hist_state": "red_expanding",
                "price_turnover_state": "price_turnover_rise",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 2,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "rising",
                "daily_macd_wave_index": 1,
                "daily_macd_wave_stage": "强势",
                "bbi_bias_state": "above",
                "bias_bucket": "positive",
                "obv_state": "rising",
                "ret3": ret3,
                "ret5": ret5,
            }

        report = diag.build_neutral_watch_positive_report(
            [
                row("000001.SZ", 6.0, 8.0),
                row("000002.SZ", 7.0, 9.0),
                row("000003.SZ", -2.0, -1.0),
                row("000004.SZ", 4.0, 6.0, verdict="PASS"),
                row("000005.SZ", 5.0, 6.0, env="weak"),
            ],
            min_samples=2,
        )

        self.assertEqual(report["sample_count"], 3)
        self.assertEqual(report["return_groups"]["ret3_ge_5"]["sample_count"], 2)
        self.assertEqual(report["return_groups"]["ret3_le_0"]["sample_count"], 1)
        self.assertEqual(report["upgrade_candidates"][0]["condition"], "condition")
        self.assertIn("B3|trend_start", report["upgrade_candidates"][0]["key"])

    def test_build_strong_neutral_risk_report_summarizes_veto_candidates(self) -> None:
        rows = [
            {
                "date": "2026-05-25",
                "code": "000001.SZ",
                "env": "strong",
                "current_verdict": "WATCH",
                "current_score": 4.8,
                "signal": "B3",
                "signal_type": "rebound",
                "price_vs_90d_high": -4.0,
                "price_vs_90d_low": 80.0,
                "midline_state": "above_hold",
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.4,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "daily_macd_hist_state": "red_expanding",
                "price_turnover_state": "mixed",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 3,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "rising",
                "daily_macd_wave_index": 1,
                "daily_macd_wave_stage": "背离",
                "ret3": -2.0,
                "ret5": -3.0,
            },
            {
                "date": "2026-05-25",
                "code": "000002.SZ",
                "env": "strong",
                "current_verdict": "WATCH",
                "current_score": 4.7,
                "signal": "B2",
                "signal_type": "trend_start",
                "ret3": 8.0,
                "ret5": 7.0,
            },
            {
                "date": "2026-05-25",
                "code": "000003.SZ",
                "env": "neutral",
                "current_verdict": "WATCH",
                "current_score": 4.0,
                "signal": "B2",
                "signal_type": "rebound",
                "price_vs_90d_high": -25.0,
                "price_vs_90d_low": 70.0,
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.0,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "daily_macd_hist_state": "green_or_zero",
                "price_turnover_state": "price_turnover_rise",
                "ret3": -3.0,
                "ret5": -4.0,
            },
            {
                "date": "2026-05-25",
                "code": "000004.SZ",
                "env": "neutral",
                "current_verdict": "WATCH",
                "current_score": 3.9,
                "signal": "B2",
                "signal_type": "rebound",
                "price_vs_90d_high": -25.0,
                "price_vs_90d_low": 70.0,
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.0,
                "j_value": 70.0,
                "j_vs_d": 5.0,
                "daily_macd_hist_state": "green_or_zero",
                "price_turnover_state": "price_turnover_rise",
                "ret3": 6.0,
                "ret5": 7.0,
            },
        ]

        report = diag.build_strong_neutral_risk_report(rows, min_samples=1)

        self.assertIn("strong", report)
        self.assertIn("neutral", report)
        self.assertIn("red_expanding|mixed|rebound|price=near_high|volume=expanding|kdj=rising", report["strong"]["risk_candidates"])
        self.assertIn("neutral_b2_rebound_extended_no_red", report["neutral"]["risk_candidates"])
        self.assertEqual(report["next_step"][0], "strong 先将高频 topN 负例组合做 rank_score 扣分实验，不直接改 verdict。")

    def test_build_neutral_factor_effect_report_marks_majority_positive_features(self) -> None:
        def row(code: str, ret3: float, *, midline: str = "above_hold", price_high: float = -8.0) -> dict:
            return {
                "date": "2026-05-25",
                "code": code,
                "env": "neutral",
                "current_verdict": "WATCH",
                "current_score": 4.0,
                "signal": "B2",
                "signal_type": "trend_start",
                "price_vs_90d_high": price_high,
                "price_vs_90d_low": 70.0,
                "midline_state": midline,
                "support_stack_type": "bull_stack",
                "range_compression_20d": 0.3,
                "volume_ratio_5d": 1.0,
                "j_value": 60.0,
                "j_vs_d": -2.0,
                "daily_macd_hist_state": "green_or_zero",
                "price_turnover_state": "price_turnover_rise",
                "weekly_macd_phase_type": "rising",
                "weekly_macd_wave_index": 2,
                "weekly_macd_wave_stage": "强势",
                "daily_macd_phase_type": "falling",
                "daily_macd_wave_index": 2,
                "daily_macd_wave_stage": "修复",
                "bbi_bias_state": "above_extended",
                "bias_bucket": "positive",
                "obv_state": "flat",
                "ret3": ret3,
                "ret5": ret3 + 1.0,
            }

        report = diag.build_neutral_factor_effect_report(
            [
                row("000001.SZ", 6.0),
                row("000002.SZ", 7.0),
                row("000003.SZ", -2.0, midline="below_midline", price_high=-20.0),
            ]
        )

        self.assertEqual(report["sample_count"], 3)
        self.assertEqual(report["ret3_gt_5_count"], 2)
        majority_keys = {item["key"] for item in report["majority_positive_features"]}
        self.assertIn("midline_state=above_hold", majority_keys)
        self.assertIn("price_bucket=upper", majority_keys)
        self.assertEqual(report["factor_effects"]["signal_type"]["trend_start"]["ret3_gt_5_share"], 1.0)

    def test_midline_state_marks_volume_breakout_and_pullback_confirm(self) -> None:
        breakout_rows = [
            {"trade_date": f"2026-05-{day:02d}", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "vol": 100.0}
            for day in range(1, 30)
        ]
        breakout_rows.append(
            {"trade_date": "2026-05-30", "open": 10.0, "high": 11.2, "low": 9.8, "close": 10.8, "vol": 160.0}
        )

        breakout = diag.compute_context_features(breakout_rows, "2026-05-30")

        self.assertEqual(breakout["midline_state"], "reclaim_volume")
        self.assertEqual(breakout["breakout_above_90d_mid_with_volume"], True)

        pullback_rows = [
            {"trade_date": f"2026-05-{day:02d}", "open": 10.0, "high": 12.0, "low": 8.0, "close": 10.8, "vol": 100.0}
            for day in range(1, 30)
        ]
        pullback_rows.append(
            {"trade_date": "2026-05-30", "open": 10.6, "high": 10.9, "low": 10.1, "close": 10.4, "vol": 95.0}
        )

        pullback = diag.compute_context_features(pullback_rows, "2026-05-30")

        self.assertEqual(pullback["midline_state"], "pullback_confirm")
        self.assertEqual(pullback["pullback_confirm_vs_90d_mid"], True)


if __name__ == "__main__":
    unittest.main()
