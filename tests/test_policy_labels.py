from __future__ import annotations

import importlib.util
import unittest

HAS_PANDAS = importlib.util.find_spec("pandas") is not None
if HAS_PANDAS:
    import pandas as pd

from ml.backtest.rule_exit import ExitMarket, ExitPolicyConfig
from ml.training.policy_labels import align_exit_labels, exit_quartile_labels, policy_training_rows_before


def market_fixture(closes=None):
    dates = pd.bdate_range("2026-01-05", periods=35)
    closes = closes or [10.]*25+[10.5,10.6,10.8,10.2]+[10.2]*6
    frame = pd.DataFrame({"datetime":dates,"open":[10.]*35,"close":closes,
                          "high":[max(10,c)+.1 for c in closes],"low":[9.9]*35,"volume":[1000]*35})
    return dates, {"A":frame}


@unittest.skipUnless(HAS_PANDAS, "install backtest extra")
class PolicyLabelsTest(unittest.TestCase):
    def test_policy_label_uses_actual_exit_and_proportional_costs(self):
        dates,market = market_fixture()
        day=str(dates[24].date())
        prepared=ExitMarket(market,ExitPolicyConfig())
        rows,ends=align_exit_labels([{"date":day,"code":"A"}],prepared)
        self.assertEqual(rows[0]["exit_date"],str(dates[28].date()))
        self.assertEqual(rows[0]["exit_reason"],"t3_return_below_3pct")
        self.assertAlmostEqual(rows[0]["exit_return"],2.)
        self.assertAlmostEqual(rows[0]["exit_net_return"],(10.2*(1-.0003-.0005-.00001)/(10*(1+.0003+.00001))-1)*100)
        self.assertEqual(ends[(day,"A")],str(dates[28].date()))

    def test_no_forced_exit_or_zero_return_for_censored_and_warmup_samples(self):
        dates,market=market_fixture([10.]*25+[10.4]*10)
        prepared=ExitMarket(market,ExitPolicyConfig())
        rows,_=align_exit_labels([{"date":str(dates[i].date()),"code":"A"} for i in [0,24]],prepared)
        self.assertEqual([row["exit_label_status"] for row in rows],["missing_warmup","right_censored"])
        self.assertTrue(all(row["rank_label_exit"]=="" and row["exit_net_return"]=="" for row in rows))

    def test_new_quartiles_are_balanced_and_ties_have_same_label(self):
        labels=exit_quartile_labels({str(i):float(i) for i in range(20)})
        self.assertEqual([list(labels.values()).count(i) for i in range(4)],[5,5,5,5])
        tied=exit_quartile_labels({"A":-1.,"B":-1.,"C":5.,"D":8.})
        self.assertEqual(tied["A"],tied["B"])

    def test_training_purges_actual_exit_and_rebuilds_ranks_without_future_peers(self):
        rows=[{"date":"2026-02-05","code":code,"exit_date":end,"exit_net_return":ret,"rank_label_exit":3}
              for code,end,ret in [("A","2026-02-06",1.),("B","2026-03-10",100.),("C","2026-02-09",2.)]]
        safe=policy_training_rows_before(rows,{"2026-02-05"},"2026-02-10")
        self.assertEqual([row["code"] for row in safe],["A","C"])
        self.assertEqual(safe[0]["rank_label_exit"],0)
        self.assertEqual(rows[0]["rank_label_exit"],3)
        rows[2]["exit_date"]="2026-02-10"
        self.assertEqual(len(policy_training_rows_before(rows,{"2026-02-05"},"2026-02-10")),1)


if __name__=="__main__":
    unittest.main()
