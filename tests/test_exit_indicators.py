from __future__ import annotations

import importlib.util
import unittest

HAS_PANDAS = importlib.util.find_spec("pandas") is not None
if HAS_PANDAS:
    import pandas as pd

from ml.backtest.exit_indicators import exit_indicators, tdx_sell_condition


@unittest.skipUnless(HAS_PANDAS, "install backtest extra")
class ExitIndicatorsTest(unittest.TestCase):
    def test_kdj_uses_5_2_3_and_tdx_recursive_sma(self):
        frame = pd.DataFrame({"close": [6.0, 8.0, 9.0], "high": [10.0]*3, "low": [0.0]*3})
        actual = exit_indicators(frame)
        self.assertEqual(actual["exit_kdj_k"].tolist(), [60.0, 70.0, 80.0])
        for found, expected in zip(actual["exit_kdj_d"], [60.0, 190/3, 620/9]):
            self.assertAlmostEqual(found, expected)

    def test_ma_slope_requires_full_windows_and_matches_formula(self):
        closes = list(range(1, 29))
        frame = pd.DataFrame({"close": closes, "high": [p+1 for p in closes], "low": [p-1 for p in closes]})
        actual = exit_indicators(frame)
        self.assertTrue(pd.isna(actual.loc[23, "exit_ma25"]))
        self.assertEqual(actual.loc[24, "exit_ma25"], 13.0)
        self.assertTrue(pd.isna(actual.loc[19, "exit_j1"]))
        self.assertAlmostEqual(actual.loc[20, "exit_j1"], (11.5/10.5-1)*100)
        expected = sum((numerator/denominator-1)*100 for numerator, denominator in [(11.5,10.5),(12.5,11.5),(13.5,12.5)])/3
        self.assertAlmostEqual(actual.loc[22, "exit_mj1"], expected)

    def test_sell_formula_requires_cross_and_all_three_other_conditions(self):
        frame = pd.DataFrame({"exit_kdj_k": [60., 70., 70.], "exit_kdj_d": [62., 68., 71.],
                              "exit_j1": [1.2, .8, .6], "exit_mj1": [1.3, 1., .9]})
        self.assertEqual(tdx_sell_condition(frame).tolist(), [False, False, True])
        for column, values in [
            ("exit_kdj_k", [60., 67., 70.]),  # already above yesterday: no new cross
            ("exit_kdj_d", [62., 64., 65.]),  # D must be strictly above 65
            ("exit_j1", [.8, .7, .6]),       # COUNT(J1>1,3) is zero
            ("exit_mj1", [1.3, 1., .5]),     # current slope is not below its mean
        ]:
            with self.subTest(column=column):
                changed = frame.copy()
                changed[column] = values
                self.assertFalse(bool(tdx_sell_condition(changed).iloc[-1]))

    def test_future_bars_do_not_change_past_indicators(self):
        closes = [10+i*.12+(i%3)*.05 for i in range(40)]
        frame = pd.DataFrame({"close": closes, "high": [p+.3 for p in closes], "low": [p-.3 for p in closes]})
        prefix = exit_indicators(frame.iloc[:30])
        actual = exit_indicators(frame)
        pd.testing.assert_frame_equal(prefix, actual.iloc[:30])


if __name__ == "__main__":
    unittest.main()
