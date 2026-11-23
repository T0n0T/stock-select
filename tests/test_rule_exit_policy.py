from __future__ import annotations

import unittest

from ml.backtest.rule_exit import ExitBar, ExitPolicyConfig, ExitState


def bar(close=10.0, **kwargs):
    return ExitBar(open=kwargs.pop("open", close), close=close, high=kwargs.pop("high", close+.2),
                   volume=kwargs.pop("volume", 100), previous_close=kwargs.pop("previous_close", 10),
                   previous_volume_mean=kwargs.pop("previous_volume_mean", 100),
                   ma25=kwargs.pop("ma25", 9), tdx_sell=kwargs.pop("tdx_sell", False), **kwargs)


class RuleExitPolicyTest(unittest.TestCase):
    def test_day_count_config_rejects_fractional_or_boolean_values(self):
        for field in ["timeout_days", "volume_lookback"]:
            for value in [True, 1.5]:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    ExitPolicyConfig(**{field: value})

    def state(self):
        return ExitState(entry_date="2026-01-05", entry_session=0, entry_price=10)

    def test_ma25_stop_is_strict_and_buy_day_cannot_sell(self):
        state = self.state()
        self.assertIsNone(state.observe("2026-01-05", 0, bar(close=8), ExitPolicyConfig()))
        self.assertIsNone(state.observe("2026-01-06", 1, bar(close=9, ma25=9), ExitPolicyConfig()))
        exit = state.observe("2026-01-07", 2, bar(close=8.9), ExitPolicyConfig())
        self.assertEqual(exit.reasons, ("below_ma25",))

    def test_latest_volume_bull_body_midpoint_is_remembered(self):
        state = self.state()
        config = ExitPolicyConfig()
        self.assertIsNone(state.observe("2026-01-05", 0,
            bar(open=10, close=12, volume=150, previous_close=10), config))
        self.assertEqual(state.bull_midpoint, 11)
        self.assertIsNone(state.observe("2026-01-06", 1,
            bar(open=12, close=14, volume=200, previous_close=12), config))
        self.assertEqual(state.bull_midpoint, 13)
        exit = state.observe("2026-01-07", 2, bar(open=13, close=12.9, previous_close=14), config)
        self.assertEqual(exit.reasons, ("below_volume_bull_midpoint",))
        self.assertEqual(state.bull_date, "2026-01-06")

    def test_volume_uses_prior_mean_and_configurable_multiple(self):
        for volume, multiple, expected in [(149,1.5,None),(150,1.5,11),(150,2,None)]:
            with self.subTest(volume=volume, multiple=multiple):
                state = self.state()
                state.observe("2026-01-05",0,bar(open=10,close=12,volume=volume),ExitPolicyConfig(volume_multiple=multiple))
                self.assertEqual(state.bull_midpoint,expected)

    def test_t_plus_three_uses_that_close_even_if_earlier_gain_exceeded_three_percent(self):
        state = self.state()
        config = ExitPolicyConfig()
        for index, close in enumerate([10.6, 10.8, 10.5]):
            self.assertIsNone(state.observe(f"2026-01-0{5+index}",index,bar(close=close),config))
        exit = state.observe("2026-01-08",3,bar(close=10.2),config)
        self.assertEqual(exit.reasons,("t3_return_below_3pct",))

    def test_passing_t3_does_not_create_a_repeated_time_stop_afterwards(self):
        state = self.state()
        config = ExitPolicyConfig()
        self.assertIsNone(state.observe("2026-01-08",3,bar(close=10.3),config))
        self.assertIsNone(state.observe("2026-01-09",4,bar(close=10.1),config))

    def test_tdx_condition_can_exit_and_all_simultaneous_reasons_are_retained(self):
        exit = self.state().observe("2026-01-06",1,bar(close=8,tdx_sell=True),ExitPolicyConfig())
        self.assertEqual(exit.reasons,("below_ma25","tdx_kdj_slope"))


if __name__ == "__main__":
    unittest.main()
