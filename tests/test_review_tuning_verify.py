from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_review_tuning_verify_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "review_tuning_verify.py"
    spec = importlib.util.spec_from_file_location("review_tuning_verify", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_review_tuning_verify_parse_args_accepts_required_paths(tmp_path: Path) -> None:
    module = _load_review_tuning_verify_module()

    args = module.parse_args(
        [
            "--baseline-artifact-dir",
            str(tmp_path / "baseline"),
            "--candidate-artifact-dir",
            str(tmp_path / "candidate"),
        ]
    )

    assert args.baseline_artifact_dir == tmp_path / "baseline"
    assert args.candidate_artifact_dir == tmp_path / "candidate"


def test_review_tuning_verify_main_writes_shell_outputs(tmp_path: Path) -> None:
    module = _load_review_tuning_verify_module()

    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    baseline_dir.mkdir()
    candidate_dir.mkdir()
    for path, ret3 in [(baseline_dir, 0.5), (candidate_dir, 1.2)]:
        (path / "samples_with_env.csv").write_text(
            "\n".join(
                [
                    "method,pick_date,code,total_score,verdict,ret3_pct,ret5_pct,environment_state",
                    f"b2,2026-04-10,000001.SZ,4.2,PASS,{ret3},1.0,neutral",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    artifact_dir = tmp_path / "artifacts" / "review-tuning" / "verify"
    args = module.parse_args(
        [
            "--methods",
            "b1",
            "b2",
            "--environment-state",
            "neutral",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--artifact-dir",
            str(artifact_dir),
        ]
    )

    assert module.main(args) == 0

    payload = json.loads((artifact_dir / "verification.json").read_text(encoding="utf-8"))
    summary = (artifact_dir / "verification.md").read_text(encoding="utf-8")
    assert payload["methods"] == ["b1", "b2"]
    assert payload["environment_state"] == "neutral"
    assert payload["baseline"]["exists"] is True
    assert payload["candidate"]["exists"] is True
    assert payload["comparison"]["rows"][0]["delta_ret3_pct"] == 0.7
    assert "delta_ret3_pct" in summary


def test_review_tuning_verify_main_fails_for_missing_artifact_dirs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = _load_review_tuning_verify_module()

    artifact_dir = tmp_path / "artifacts" / "review-tuning" / "verify"
    args = module.parse_args(
        [
            "--baseline-artifact-dir",
            str(tmp_path / "baseline"),
            "--candidate-artifact-dir",
            str(tmp_path / "candidate"),
            "--artifact-dir",
            str(artifact_dir),
        ]
    )

    with pytest.raises(SystemExit) as excinfo:
        module.main(args)

    assert excinfo.value.code == 2
    assert "must exist and be directories" in capsys.readouterr().err
    assert not (artifact_dir / "verification.json").exists()
