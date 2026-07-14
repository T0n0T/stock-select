import argparse
import unittest
from pathlib import Path
from unittest import mock

from ml.tuning import optuna_search


class OptunaTuningTest(unittest.TestCase):
    def test_forwards_fixed_feature_manifest_to_every_trial(self):
        class Trial:
            number = 0

            def suggest_categorical(self, _name, choices):
                return choices[0]

            def suggest_float(self, _name, low, _high, **_kwargs):
                return low

            def set_user_attr(self, _key, _value):
                pass

        class Study:
            trials = []
            best_trial = Trial()
            best_value = 1.0
            best_params = {}
            study_name = "fixture"

            def optimize(self, objective, n_trials):
                self.trials = [Trial()]
                objective(self.trials[0])

        optuna = mock.Mock()
        optuna.__version__ = "fixture"
        optuna.samplers.TPESampler.return_value = object()
        optuna.create_study.return_value = Study()
        args = argparse.Namespace(
            objective="default",
            output_root=Path("out"),
            method="lsh",
            dataset=Path("dataset.csv"),
            feature_manifest=Path("static.json"),
            seed=17,
            num_threads=14,
            test_ratio=0.2,
            rolling_folds=5,
            rolling_train_dates=240,
            rolling_test_dates=40,
            skip_rf_diagnostics=True,
            max_trials=1,
            allow_native_categorical=False,
            visualize=False,
        )
        report = {
            "rolling_summary": {"test_avg": {"top3_ret3_le_0_rate": 40.0}},
            "metrics": {"test": {}},
            "model_params": {},
        }

        with mock.patch.object(optuna_search.train_lgbm_rank, "train_and_report", return_value=report) as train:
            optuna_search.run_optuna_study(args, optuna)

        self.assertEqual(train.call_args.kwargs["feature_manifest"], Path("static.json"))


if __name__ == "__main__":
    unittest.main()
