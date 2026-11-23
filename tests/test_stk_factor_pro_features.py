import json
import tempfile
import unittest
from pathlib import Path

from ml.dataset import rank_dataset
from ml.dataset.intraday_proxy import classify_intraday_factor
from ml.training.features import select_feature_columns

NEW_FACTORS = [
    "asi_qfq",
    "asit_qfq",
    "bias2_qfq",
    "bias3_qfq",
    "brar_ar_qfq",
    "brar_br_qfq",
    "cci_qfq",
    "cr_qfq",
    "emv_qfq",
    "maemv_qfq",
    "mass_qfq",
    "ma_mass_qfq",
    "mfi_qfq",
    "psyma_qfq",
    "maroc_qfq",
    "trma_qfq",
    "wr1_qfq",
    "updays",
    "downdays",
    "lowdays",
    "topdays",
    "dv_ttm",
    "turnover_rate",
    "volume_ratio",
    "float_share",
    "close_to_bbi_qfq_pct",
    "close_to_ma_qfq_5_pct",
    "close_to_ma_qfq_10_pct",
    "close_to_ma_qfq_20_pct",
    "close_to_ma_qfq_30_pct",
    "close_to_ma_qfq_60_pct",
    "close_to_ma_qfq_90_pct",
    "close_to_ma_qfq_250_pct",
    "close_to_ema_qfq_5_pct",
    "close_to_ema_qfq_10_pct",
    "close_to_ema_qfq_20_pct",
    "close_to_ema_qfq_30_pct",
    "close_to_ema_qfq_60_pct",
    "close_to_ema_qfq_90_pct",
    "close_to_ema_qfq_250_pct",
    "close_to_expma_12_qfq_pct",
    "close_to_expma_50_qfq_pct",
    "close_to_boll_upper_qfq_pct",
    "close_to_boll_mid_qfq_pct",
    "close_to_boll_lower_qfq_pct",
    "close_to_ktn_upper_qfq_pct",
    "close_to_ktn_mid_qfq_pct",
    "close_to_ktn_down_qfq_pct",
    "close_to_taq_up_qfq_pct",
    "close_to_taq_mid_qfq_pct",
    "close_to_taq_down_qfq_pct",
    "close_to_xsii_td1_qfq_pct",
    "close_to_xsii_td2_qfq_pct",
    "close_to_xsii_td3_qfq_pct",
    "close_to_xsii_td4_qfq_pct",
    "atr_qfq_to_close_pct",
    "dfma_dif_qfq_to_close_pct",
    "dfma_difma_qfq_to_close_pct",
    "dpo_qfq_to_close_pct",
    "madpo_qfq_to_close_pct",
    "mtmma_qfq_to_close_pct",
    "boll_position_pct",
    "boll_width_to_close_pct",
    "ktn_position_pct",
    "ktn_width_to_close_pct",
    "taq_position_pct",
    "taq_width_to_close_pct",
    "xsii_short_position_pct",
    "xsii_short_width_to_close_pct",
    "xsii_long_position_pct",
    "xsii_long_width_to_close_pct",
    "free_to_float_share_pct"
]

class StkFactorProFeatureTest(unittest.TestCase):
    def test_scm_and_pbm_can_train_on_every_new_indicator_and_derived_form(self):
        for method in ("scm", "pbm"):
            with self.subTest(method=method):
                columns = rank_dataset.dataset_columns_for_method(method)
                self.assertTrue(set(NEW_FACTORS).issubset(columns))
                numeric, categorical = select_feature_columns(NEW_FACTORS + ["vr_qfq"], method=method)
                self.assertEqual(numeric, NEW_FACTORS + ["vr_qfq"])
                self.assertEqual(categorical, [])
                raw_prices, _ = select_feature_columns(
                    ["bbi_qfq", "ema_qfq_250", "xsii_td3_qfq", "atr_qfq"], method=method
                )
                self.assertEqual(raw_prices, [])

    def test_new_eod_indicators_are_not_claimed_to_be_available_intraday(self):
        for factor in NEW_FACTORS + ["vr_qfq"]:
            with self.subTest(factor=factor):
                self.assertEqual(classify_intraday_factor(factor), "unavailable_intraday")

    def test_rust_factor_artifact_values_reach_training_selection_without_null_to_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            artifact = runtime / "factors" / "2026-11-20.scm"
            artifact.mkdir(parents=True)
            payload = {
                "artifact_version": rank_dataset.EXPECTED_FACTOR_ARTIFACT_VERSION,
                "factor_library_version": rank_dataset.EXPECTED_FACTOR_LIBRARY_VERSION,
                "rows": [{
                    "code": "000001.SZ",
                    "factors": {
                        "mfi_qfq": 62.5, "atr_qfq_to_close_pct": 5.0,
                        "xsii_long_position_pct": 125.0, "psyma_qfq": None,
                        "dv_ttm": 0.0, "_stk_close_qfq": 20.0,
                    },
                }],
            }
            (artifact / "factors.json").write_text(json.dumps(payload))
            rows, warnings = rank_dataset.load_factor_artifact_rows(
                runtime, method="scm", artifact_key="2026-11-20"
            )
        self.assertEqual(warnings, [])
        row = rows["000001.SZ"]
        numeric, _ = select_feature_columns(list(row), method="scm")
        self.assertEqual(
            numeric, ["mfi_qfq", "atr_qfq_to_close_pct", "xsii_long_position_pct", "psyma_qfq", "dv_ttm"]
        )
        self.assertEqual(row["xsii_long_position_pct"], 125.0)
        self.assertEqual(row["psyma_qfq"], "")
        self.assertEqual(row["dv_ttm"], 0.0)
