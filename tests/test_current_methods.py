import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ml.cli import build_parser
from ml.dataset.rank_dataset import compute_forward_labels, dataset_columns_for_method, load_candidate_rows
from ml.model_ops.promote import archive_dirs_for_target, archive_source_for_version, validate_metadata
from ml.training.matrices import build_feature_matrix_from_metadata


class CurrentMethodsTest(unittest.TestCase):
    def test_dataset_rejects_retired_methods(self):
        for method in ("b1", "b3", "lsh", "qianlong", "dribull"):
            with self.subTest(method=method), self.assertRaises(ValueError):
                dataset_columns_for_method(method)

    def test_cli_rejects_retired_methods(self):
        parser = build_parser()
        for args in (
            ["backfill", "candidates", "--start-date", "2026-01-01", "--end-date", "2026-01-02"],
            ["dataset", "build"],
            ["train", "lgbm-rank"],
            ["model", "status"],
        ):
            for method in ("b1", "b3", "lsh", "qianlong", "dribull"):
                with self.subTest(args=args, method=method):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                        parser.parse_args([*args, "--method", method])
                    self.assertIn(f"invalid choice: '{method}'", stderr.getvalue())

    def test_model_readers_require_explicit_encoding(self):
        with self.assertRaisesRegex(ValueError, "categorical_encoding"):
            validate_metadata({})
        with self.assertRaisesRegex(ValueError, "categorical_encoding"):
            build_feature_matrix_from_metadata([], {"numeric_columns": [], "categorical_columns": []})

    def test_forward_labels_require_explicit_qfq_prices(self):
        for basis in (None, "raw"):
            row = {"trade_date": "2026-06-05", "close": 10.0, "adj_factor": 2.0}
            if basis:
                row["price_basis"] = basis
            with self.subTest(basis=basis), self.assertRaisesRegex(ValueError, "price basis"):
                compute_forward_labels([row], "2026-06-05")

    def test_candidate_reader_rejects_legacy_shape_and_mismatched_headers(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "candidates" / "2026-06-05.b2.json"
            path.parent.mkdir()
            for payload in (
                {"rows": []},
                {"candidates": []},
                {"method": "b3", "pick_date": "2026-06-05", "candidates": []},
                {"method": "scm", "pick_date": "2026-06-05", "candidates": []},
                {"method": "b2", "pick_date": "2026-06-04", "candidates": []},
            ):
                path.write_text(json.dumps(payload))
                with self.subTest(payload=payload):
                    rows, warnings = load_candidate_rows(root, method="b2", start_date="2026-06-05", end_date="2026-06-05")
                    self.assertEqual(rows, [])
                    self.assertTrue(warnings)

    def test_scm_pbm_export_current_ma25_factors(self):
        for method in ("scm", "pbm"):
            columns = dataset_columns_for_method(method)
            self.assertIn("ma25_daily_macd_wave_index", columns)
            self.assertFalse(any("b3" in c or "lsh" in c for c in columns))

    def test_deleted_strategy_bar_fields_are_not_registered(self):
        for method in ("b2", "scm", "pbm"):
            columns = dataset_columns_for_method(method)
            for field in ("bar_lower_shadow_pct", "bar_amplitude_pct", "bar_body_pct"):
                self.assertNotIn(field, columns)

    def test_flat_model_archives_are_neither_listed_nor_used_for_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "models" / "b2"
            old = target.parent / "archive" / "old"
            old.mkdir(parents=True)
            (old / "model_card.json").write_text('{"target": "models/b2"}')
            self.assertEqual(archive_dirs_for_target(target), [])
            self.assertEqual(archive_source_for_version(target, "old"), target.parent / "archive" / "b2" / "old")
