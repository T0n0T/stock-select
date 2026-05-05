from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

DEFAULT_RUNTIME_ROOT = Path.home() / ".agents" / "skills" / "stock-select" / "runtime"
DEFAULT_OUTPUT_DIR = DEFAULT_RUNTIME_ROOT / "research" / "review_tuning"


def _parser_error(args: argparse.Namespace, message: str) -> "Never":
    parser = getattr(args, "_parser", None)
    if parser is not None:
        parser.error(message)
    raise SystemExit(message)


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir is not None:
        return args.output_dir
    if args.artifact_dir is not None:
        return args.artifact_dir
    return DEFAULT_OUTPUT_DIR


def _load_artifact_dir(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "files": sorted(item.name for item in path.iterdir()) if path.exists() else [],
    }


def _load_review_top3_stats_module():
    script_path = Path(__file__).resolve().with_name("review_top3_stats.py")
    spec = importlib.util.spec_from_file_location("review_top3_stats", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a minimal review tuning verification shell")
    parser.add_argument("--methods", nargs="+", default=[])
    parser.add_argument("--environment-state")
    parser.add_argument("--baseline-artifact-dir", type=Path, required=True)
    parser.add_argument("--candidate-artifact-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    setattr(args, "_parser", parser)
    return args


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()

    invalid_inputs = [
        str(path)
        for path in (args.baseline_artifact_dir, args.candidate_artifact_dir)
        if not path.is_dir()
    ]
    if invalid_inputs:
        joined = ", ".join(invalid_inputs)
        _parser_error(args, f"baseline and candidate artifact dirs must exist and be directories: {joined}")

    review_top3_stats = _load_review_top3_stats_module()
    try:
        comparison_payload = review_top3_stats.compare_artifact_dirs(
            baseline_artifact_dir=args.baseline_artifact_dir,
            candidate_artifact_dir=args.candidate_artifact_dir,
            methods=args.methods,
            environment_state=args.environment_state,
        )
    except ValueError as exc:
        _parser_error(args, str(exc))

    payload = {
        "methods": comparison_payload["methods"],
        "environment_state": args.environment_state,
        "baseline": _load_artifact_dir(args.baseline_artifact_dir),
        "candidate": _load_artifact_dir(args.candidate_artifact_dir),
        "comparison": comparison_payload["comparison"],
    }

    output_dir = _resolve_output_dir(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "verification.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_lines = [
        "# Verification",
        "",
        f"- baseline: {args.baseline_artifact_dir}",
        f"- candidate: {args.candidate_artifact_dir}",
    ]
    if comparison_payload["methods"]:
        summary_lines.append(f"- methods: {', '.join(comparison_payload['methods'])}")
    if args.environment_state:
        summary_lines.append(f"- environment_state: {args.environment_state}")
    for row in comparison_payload["comparison"]["rows"]:
        summary_lines.append(
            "- "
            f"method={row['method']} "
            f"environment_state={row.get('environment_state') or 'all'} "
            f"delta_ret3_pct={row.get('delta_ret3_pct')} "
            f"delta_ret5_pct={row.get('delta_ret5_pct')}"
        )
    (output_dir / "verification.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
