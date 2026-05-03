from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_environment_tuning_diagnostics_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "environment_tuning_diagnostics.py"
    spec = importlib.util.spec_from_file_location("environment_tuning_diagnostics", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_defaults_to_required_research_window() -> None:
    module = _load_environment_tuning_diagnostics_module()

    args = module.parse_args([])

    assert args.env_start_date == "2025-11-01"
    assert args.env_end_date == "2026-04-30"
    assert args.methods == ["b1", "b2"]


def test_build_environment_layered_records_attaches_environment_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_environment_tuning_diagnostics_module()

    monkeypatch.setattr(
        module,
        "load_environment_history",
        lambda _runtime_root: [
            {
                "state": "weak",
                "start_date": "2026-04-01",
                "end_date": "2026-04-15",
                "evaluated_at": "2026-04-01",
                "source": "scheduled",
                "manual_override": False,
                "reason": "risk-off",
            }
        ],
    )
    monkeypatch.setattr(
        module,
        "collect_method_records",
        lambda **_kwargs: [
            {
                "method": "b1",
                "pick_date": "2026-04-10",
                "code": "000001.SZ",
                "total_score": 4.1,
                "ret3_pct": 1.2,
            }
        ],
    )

    records = module.build_environment_layered_records(runtime_root=tmp_path, methods=["b1"])

    assert records[0]["environment_state"] == "weak"
