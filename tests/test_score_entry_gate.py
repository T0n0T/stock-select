from __future__ import annotations

import math
import importlib.util
import unittest

from ml.backtest.score_gate import ScoreEntryGate, filter_score_signals, validate_bound_score_policy
from ml.backtest.signal_bundle import SignalBundle, SignalRow


class ScoreEntryGateTest(unittest.TestCase):
    def gate(self, **kwargs):
        return ScoreEntryGate(open_min_score=0., discard_below_score=-.2, top_n=2, **kwargs)

    def test_three_actions_include_exact_thresholds_and_original_rank_cap(self):
        gate = self.gate()
        self.assertEqual(gate.decide(-.21, 1, "strong").action, "discard")
        self.assertEqual(gate.decide(-.2, 1, "strong").action, "observe")
        self.assertEqual(gate.decide(0., 2, "strong").action, "open")
        self.assertEqual(gate.decide(.3, 3, "strong").action, "observe")

    def test_missing_score_rank_and_environment_never_open(self):
        gate = self.gate()
        for value in [None, math.nan, math.inf, -math.inf]:
            self.assertEqual(gate.decide(value, 1, "strong").action, "observe")
        for rank in [None, 0, -1]:
            self.assertEqual(gate.decide(.3, rank, "strong").action, "observe")
        for env in [None, "unknown", ""]:
            self.assertEqual(gate.decide(.3, 1, env).action, "observe")

    def test_environment_filter_and_invalid_configuration(self):
        gate = self.gate(blocked_environments=("weak",))
        self.assertEqual(gate.decide(.3, 1, "weak").action, "observe")
        self.assertEqual(gate.decide(.3, 1, "neutral").action, "open")
        for kwargs in [dict(open_min_score=-.3, discard_below_score=-.2, top_n=2),
                       dict(open_min_score=math.nan, discard_below_score=-.2, top_n=2),
                       dict(open_min_score=0., discard_below_score=-.2, top_n=0)]:
            with self.assertRaises(ValueError):
                ScoreEntryGate(**kwargs)

    def test_filter_keeps_empty_signal_days_and_does_not_promote_lower_ranks(self):
        day = "2026-06-01"
        signals = SignalBundle({day: (SignalRow(day, "A", -.3, 1),
                                     SignalRow(day, "B", .3, 3)),
                                "2026-06-02": (SignalRow("2026-06-02", "C", .2, 1),)})
        result = filter_score_signals(signals, self.gate(), {day: "strong", "2026-06-02": "neutral"})
        self.assertEqual(result.dates, signals.dates)
        self.assertEqual(result.rows_for_date(day), ())
        self.assertEqual([row.code for row in result.rows_for_date("2026-06-02")], ["C"])

    def test_serialization_is_strict_and_portable(self):
        gate = self.gate(blocked_environments=("weak",))
        self.assertEqual(ScoreEntryGate.from_dict(gate.to_dict()), gate)
        with self.assertRaises(ValueError):
            ScoreEntryGate.from_dict({**gate.to_dict(), "typo": 1})

    def test_bound_policy_rejects_wrong_model_method_and_invalid_date(self):
        raw = {"schema_version": 1, "method": "scm", "model_sha256": "a" * 64,
               "calibration_end_date": "2026-11-16", "status": "research", "gate": self.gate().to_dict()}
        self.assertEqual(validate_bound_score_policy(raw, "a" * 64, "scm"), raw)
        for value, digest, method in [(raw, "b" * 64, "scm"), (raw, "a" * 64, "b2"),
                                      ({**raw, "calibration_end_date": "bad"}, "a" * 64, "scm")]:
            with self.assertRaises(ValueError):
                validate_bound_score_policy(value, digest, method)

    @unittest.skipUnless(importlib.util.find_spec("akquant"), "install backtest extra")
    def test_backtest_filters_entries_preserves_cash_slots_and_exits_existing_positions(self):
        from ml.backtest.akquant_gateway import BacktestConfig, run_akquant_backtest
        from ml.backtest.report import build_report
        from ml.backtest.rule_exit import ExitPolicyConfig
        from tests.test_policy_labels import market_fixture
        dates, market = market_fixture()
        market["B"] = market["A"].copy()
        first, second = (str(dates[i].date()) for i in [24, 25])
        signals = SignalBundle({first: (SignalRow(first, "A", .2, 1), SignalRow(first, "B", -.1, 2)),
                                second: (SignalRow(second, "B", .3, 1),)})
        gate = self.gate(blocked_environments=("weak",))
        result = run_akquant_backtest(market, signals, BacktestConfig(top_n=2, capital_allocation=.9),
                                     exit_policy=ExitPolicyConfig(), score_gate=gate,
                                     environments={first: "strong", second: "weak"},
                                     entry_policy=None)
        report = build_report(result)
        self.assertEqual(report["actions"][0]["enter"], ["A"])
        self.assertEqual(report["actions"][1]["enter"], [])
        # 只通过一个名额时留下一半现金，不把过滤掉的名额转给另一只。
        self.assertLess(report["daily_budgets"][0]["submitted_notional_at_close"], 160_000.)
        self.assertTrue(any(event["code"] == "A" for event in report["exit_events"]))
        self.assertEqual(report["strategy_config"]["score_entry_gate"], gate.to_dict())


if __name__ == "__main__":
    unittest.main()
