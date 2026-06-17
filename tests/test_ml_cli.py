import contextlib
import io
import unittest

from ml.cli import main


class MlCliTest(unittest.TestCase):
    def test_main_prints_usage_for_no_args(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main([])
        self.assertEqual(rc, 2)
        self.assertIn("stock-select-ml", stderr.getvalue())

    def test_main_routes_version(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = main(["--version"])
        self.assertEqual(rc, 0)
        self.assertIn("stock-select-ml", stdout.getvalue())

    def test_dataset_build_help_is_registered(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["dataset", "build", "--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("rank dataset", stdout.getvalue())

    def test_train_lgbm_rank_help_is_registered(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["train", "lgbm-rank", "--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("LightGBM ranker", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
