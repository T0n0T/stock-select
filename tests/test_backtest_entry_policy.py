from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ml.backtest.entry_policy import EntryPolicy, EntryRule, load_daily_environments, load_entry_policy


class EntryPolicyTest(unittest.TestCase):
    def test_environment_rules_control_entry_and_daily_equity_budget(self):
        policy = EntryPolicy(name="environment", by_environment={
            "weak": EntryRule(allow_new_positions=False),
            "neutral": EntryRule(daily_equity_fraction=0.15),
            "strong": EntryRule(),
        })

        weak = policy.decide("2026-01-05", "weak", default_fraction=0.3)
        neutral = policy.decide("2026-01-06", "neutral", default_fraction=0.3)
        strong = policy.decide("2026-01-07", "strong", default_fraction=0.3)

        self.assertFalse(weak.allow_new_positions)
        self.assertEqual(weak.daily_equity_fraction, 0)
        self.assertEqual(neutral.daily_equity_fraction, 0.15)
        self.assertTrue(neutral.allow_new_positions)
        self.assertEqual(strong.daily_equity_fraction, 0.3)
        self.assertEqual(strong.environment, "strong")
        self.assertFalse(EntryPolicy(default=EntryRule(daily_equity_fraction=0)).decide(
            "2026-01-05", None, default_fraction=0.3,
        ).allow_new_positions)

    def test_environment_policy_rejects_missing_or_unconfigured_environment(self):
        policy = EntryPolicy(by_environment={"weak": EntryRule(allow_new_positions=False)})
        for environment in (None, "unexpected"):
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(ValueError, "2026-01-05.*environment"):
                    policy.decide("2026-01-05", environment, default_fraction=0.3)

    def test_policy_config_and_daily_candidate_context_are_loaded_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy_file = root / "policy.json"
            policy_file.write_text(json.dumps({
                "name": "fixed-budget",
                "default": {"daily_equity_fraction": 0.1},
            }), encoding="utf-8")
            context = root / "dataset.csv"
            context.write_text("date,code,env\n2026-01-05,A,weak\n2026-01-05,B,weak\n2026-01-06,C,strong\n", encoding="utf-8")

            policy = load_entry_policy(policy_file)
            environments = load_daily_environments(context)

            self.assertEqual(policy.name, "fixed-budget")
            self.assertEqual(policy.decide("2026-01-05", None, default_fraction=0.3).daily_equity_fraction, 0.1)
            self.assertEqual(environments, {"2026-01-05": "weak", "2026-01-06": "strong"})
            context.write_text("date,env\n2026-01-05,weak\n2026-01-05,strong\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicting.*2026-01-05"):
                load_daily_environments(context)

    def test_invalid_rule_and_typo_are_rejected(self):
        for fraction in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(fraction=fraction):
                with self.assertRaises(ValueError):
                    EntryRule(daily_equity_fraction=fraction)
        with self.assertRaises(ValueError):
            EntryRule(allow_new_positions="false")
        with tempfile.TemporaryDirectory() as temporary:
            policy_file = Path(temporary) / "policy.json"
            policy_file.write_text('{"default": {"daily_budget_fracion": 0.1}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "daily_budget_fracion"):
                load_entry_policy(policy_file)


if __name__ == "__main__":
    unittest.main()
