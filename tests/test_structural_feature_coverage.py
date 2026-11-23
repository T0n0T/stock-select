import unittest

from ml.training.features import validate_selected_feature_coverage


PREFIX = "market_index_chinext_calc_daily_czsc_structure_monthly_"
COLUMNS = [PREFIX + "latest_zs_" + field for field in (
    "bi_count", "duration_calendar_days", "end_age_calendar_days",
    "start_age_calendar_days", "zd_to_close_pct", "zg_to_close_pct", "zz_to_close_pct",
)]


class StructuralFeatureCoverageTest(unittest.TestCase):
    def row(self, **changes):
        row = dict.fromkeys(COLUMNS, "")
        row.update({"core": "3", "market_index_chinext_member_flag": "1",
                    PREFIX + "source_bar_valid": "1", PREFIX + "status_code": "2"})
        row.update(changes)
        return row

    def validate(self, rows, columns=None):
        return validate_selected_feature_coverage(
            rows, numeric_columns=columns or ["core"] + COLUMNS, categorical_columns=[])

    def test_retains_verified_unformed_structure_columns(self):
        report = self.validate([self.row()])
        self.assertEqual(report["feature_count"], 8)
        self.assertEqual(set(report["structurally_unavailable_features"]), set(COLUMNS))
        self.assertEqual(report["zero_coverage_features"], [])
        self.assertTrue(all(report["features"][column]["non_empty_count"] == 0 for column in COLUMNS))

    def test_membership_mask_is_valid_but_unknown_membership_is_not(self):
        row = self.row(market_index_chinext_member_flag="0")
        row[PREFIX + "source_bar_valid"] = "0"
        self.validate([row])
        row["market_index_chinext_member_flag"] = ""
        with self.assertRaisesRegex(ValueError, "zero coverage"):
            self.validate([row])

    def test_missing_source_or_existing_structure_still_fails(self):
        for field, value in (("source_bar_valid", "0"), ("status_code", "4"), ("status_code", "")):
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, "zero coverage"):
                    self.validate([self.row(**{PREFIX + field: value})])
        with self.assertRaisesRegex(ValueError, "core"):
            self.validate([self.row(core="")])
        with self.assertRaisesRegex(ValueError, "zero coverage"):
            self.validate([self.row()], COLUMNS + [PREFIX + "latest_bi_move_pct"])

    def test_any_known_index_mask_retains_empty_context_without_inventing_values(self):
        column = "market_index_bse50_idx_ma_bfq_250_to_close_pct"
        row = {column: "", "market_index_bse50_member_flag": "0"}
        report = self.validate([row], [column])
        self.assertEqual(report["structurally_unavailable_features"], [column])
        self.assertEqual(row[column], "")
        for membership in ["1", ""]:
            with self.subTest(membership=membership), self.assertRaises(ValueError):
                self.validate([{**row, "market_index_bse50_member_flag": membership}], [column])

    def test_other_index_unformed_zs_requires_valid_source_and_explicit_status(self):
        prefix = "market_index_csi_dividend_calc_daily_czsc_structure_monthly_"
        column = prefix + "latest_zs_zd_to_close_pct"
        row = {column: "", "market_index_csi_dividend_member_flag": "1",
               prefix + "source_bar_valid": "1", prefix + "status_code": "2"}
        self.validate([row], [column])
        row[prefix + "source_bar_valid"] = "0"
        with self.assertRaises(ValueError):
            self.validate([row], [column])


if __name__ == "__main__":
    unittest.main()
