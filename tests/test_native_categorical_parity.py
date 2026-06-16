import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.ml.train_rank_lgbm import build_feature_matrix


FIXTURE_DIR = Path("tests/fixtures/native_categorical_model")


class NativeCategoricalParityFixtureTest(unittest.TestCase):
    def test_generate_native_categorical_fixture(self):
        try:
            import lightgbm as lgb
            import numpy as np
        except ModuleNotFoundError as exc:
            self.skipTest(f"native categorical fixture generation requires {exc.name}")

        rows = [
            {"x": "0.1", "env": "weak", "label": 0},
            {"x": "0.2", "env": "weak", "label": 0},
            {"x": "0.8", "env": "strong", "label": 1},
            {"x": "0.9", "env": "strong", "label": 1},
            {"x": "0.4", "env": "neutral", "label": 0},
            {"x": "0.6", "env": "neutral", "label": 1},
        ]
        levels = {"env": ["weak", "neutral", "strong"]}
        matrix, feature_names, code_maps = build_feature_matrix(
            rows,
            numeric_columns=["x"],
            categorical_columns=["env"],
            levels=levels,
            categorical_encoding="native",
        )
        labels = [row["label"] for row in rows]
        dataset = lgb.Dataset(
            np.array(matrix, dtype=float),
            label=np.array(labels, dtype=int),
            feature_name=feature_names,
            categorical_feature=["env"],
            free_raw_data=False,
        )
        model = lgb.train(
            {
                "objective": "binary",
                "metric": "binary_logloss",
                "learning_rate": 0.3,
                "num_leaves": 3,
                "min_data_in_leaf": 1,
                "seed": 17,
                "verbosity": -1,
                "num_threads": 1,
            },
            dataset,
            num_boost_round=4,
        )

        sample_rows = [
            {"code": "a", "x": "0.15", "env": "weak"},
            {"code": "b", "x": "0.85", "env": "strong"},
            {"code": "c", "x": "0.50", "env": "unknown"},
        ]
        sample_matrix, _sample_names, _sample_maps = build_feature_matrix(
            sample_rows,
            numeric_columns=["x"],
            categorical_columns=["env"],
            levels=levels,
            categorical_encoding="native",
        )
        predictions = [float(value) for value in model.predict(np.array(sample_matrix, dtype=float))]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_path = root / "model.txt"
            model.save_model(str(model_path))
            self.assertGreater(model_path.stat().st_size, 0)

        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        model.save_model(str(FIXTURE_DIR / "model.txt"))
        metadata = {
            "numeric_columns": ["x"],
            "categorical_columns": ["env"],
            "categorical_levels": levels,
            "categorical_encoding": "native",
            "categorical_code_maps": code_maps,
            "feature_names": ["x", "env"],
            "lightgbm_feature_names": ["x", "env"],
            "label_column": "label",
            "train_start": "fixture",
            "train_end": "fixture",
            "score_start": "fixture",
            "score_end": "fixture",
            "model_params": {"objective": "binary", "num_boost_round": 4},
        }
        (FIXTURE_DIR / "model_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with (FIXTURE_DIR / "predictions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["code", "x", "env", "prediction"])
            writer.writeheader()
            for row, prediction in zip(sample_rows, predictions):
                writer.writerow({**row, "prediction": f"{prediction:.12f}"})

        self.assertEqual(metadata["categorical_code_maps"], {"env": {"weak": 0, "neutral": 1, "strong": 2}})
        self.assertEqual(len(predictions), 3)


if __name__ == "__main__":
    unittest.main()
