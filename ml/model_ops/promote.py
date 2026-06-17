from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .runtime import RUNTIME_ROOT_ENV, resolve_default_target_dir, resolve_runtime_root

DEFAULT_METHOD = "b2"
REQUIRED_METADATA_KEYS = {
    "feature_names",
    "numeric_columns",
    "categorical_columns",
    "categorical_levels",
    "label_column",
    "train_start",
    "train_end",
    "score_start",
    "score_end",
    "model_params",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"无法解析 JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 必须是对象: {path}")
    return payload


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def validate_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(key for key in REQUIRED_METADATA_KEYS if key not in metadata)
    if missing:
        raise ValueError(f"model_metadata.json 缺少关键字段: {', '.join(missing)}")

    feature_names = metadata.get("feature_names")
    numeric_columns = metadata.get("numeric_columns")
    categorical_columns = metadata.get("categorical_columns")
    categorical_levels = metadata.get("categorical_levels")
    categorical_encoding = str(metadata.get("categorical_encoding") or "one_hot")
    categorical_code_maps = metadata.get("categorical_code_maps") or {}
    model_params = metadata.get("model_params")
    label_column = metadata.get("label_column")

    if not isinstance(feature_names, list) or not all(isinstance(value, str) for value in feature_names) or not feature_names:
        raise ValueError("model_metadata.json feature_names 必须是非空字符串数组")
    if not isinstance(numeric_columns, list) or not all(isinstance(value, str) for value in numeric_columns):
        raise ValueError("model_metadata.json numeric_columns 必须是字符串数组")
    if not isinstance(categorical_columns, list) or not all(isinstance(value, str) for value in categorical_columns):
        raise ValueError("model_metadata.json categorical_columns 必须是字符串数组")
    if not isinstance(categorical_levels, dict):
        raise ValueError("model_metadata.json categorical_levels 必须是对象")
    if categorical_encoding not in {"one_hot", "native"}:
        raise ValueError("model_metadata.json categorical_encoding 必须是 one_hot 或 native")
    for column in categorical_columns:
        levels = categorical_levels.get(column)
        if not isinstance(levels, list) or not all(isinstance(value, str) for value in levels):
            raise ValueError(f"model_metadata.json categorical_levels.{column} 必须是字符串数组")
    if categorical_encoding == "native":
        if not isinstance(categorical_code_maps, dict):
            raise ValueError("model_metadata.json categorical_code_maps 必须是对象")
        expected_feature_names = list(numeric_columns) + list(categorical_columns)
        if feature_names != expected_feature_names:
            raise ValueError("native categorical 模型 feature_names 必须等于 numeric_columns + categorical_columns")
        for column in categorical_columns:
            code_map = categorical_code_maps.get(column)
            levels = categorical_levels.get(column) or []
            if not isinstance(code_map, dict):
                raise ValueError(f"model_metadata.json categorical_code_maps.{column} 必须是对象")
            expected_map = {str(level): index for index, level in enumerate(levels)}
            if code_map != expected_map:
                raise ValueError(f"model_metadata.json categorical_code_maps.{column} 必须覆盖 categorical_levels 且从 0 连续编码")
    if not isinstance(label_column, str) or not label_column:
        raise ValueError("model_metadata.json label_column 必须是非空字符串")
    if not isinstance(model_params, dict) or not model_params:
        raise ValueError("model_metadata.json model_params 必须是非空对象")

    return {
        "feature_count": len(feature_names),
        "numeric_count": len(numeric_columns),
        "categorical_count": len(categorical_columns),
        "categorical_encoding": categorical_encoding,
        "label_column": label_column,
        "train_window": f"{metadata.get('train_start')}..{metadata.get('train_end')}",
        "score_window": f"{metadata.get('score_start')}..{metadata.get('score_end')}",
        "model_params": model_params,
    }


def find_report(candidate_dir: Path, explicit_report: Path | None = None) -> Path | None:
    if explicit_report is not None:
        return explicit_report
    names = [
        "lgbm_rank_report_raw_numeric.json",
        "lgbm_rank_report.json",
        "lgbm_rank_report_all.json",
    ]
    for name in names:
        path = candidate_dir / name
        if path.exists():
            return path
    matches = sorted(candidate_dir.glob("lgbm_rank_report*.json"))
    return matches[0] if matches else None


def validate_report(report_path: Path, *, expected_method: str | None = None) -> dict[str, Any]:
    report = read_json(report_path)
    method = report.get("method")
    if expected_method is not None and method is not None and method != expected_method:
        raise ValueError(f"训练报告 method={method} 与目标 method={expected_method} 不一致: {report_path}")
    rolling_summary = report.get("rolling_summary")
    if not isinstance(rolling_summary, dict):
        raise ValueError(f"训练报告缺少 rolling_summary: {report_path}")
    model_avg = rolling_summary.get("test_avg")
    if not isinstance(model_avg, dict) or not model_avg:
        raise ValueError(f"训练报告缺少 rolling_summary.test_avg: {report_path}")

    return {
        "report_path": str(report_path),
        "method": method,
        "dataset": report.get("dataset"),
        "feature_manifest": report.get("feature_manifest"),
        "model_params": report.get("model_params"),
        "rolling_summary": model_avg,
        "rolling_fold_count": len(report.get("rolling_folds") or []),
        "decision": "allow",
    }


def validate_model_routing_manifest(candidate_dir: Path) -> dict[str, Any]:
    routing_path = candidate_dir / "model_routing.json"
    routing = read_json(routing_path)
    default_model = routing.get("default_model")
    models = routing.get("models")
    routes = routing.get("routes") or []
    if not isinstance(default_model, str) or not default_model:
        raise ValueError("model_routing.json default_model 必须是非空字符串")
    if not isinstance(models, dict) or not models:
        raise ValueError("model_routing.json models 必须是非空对象")
    if default_model not in models:
        raise ValueError(f"model_routing.json default_model 未在 models 中定义: {default_model}")
    if not isinstance(routes, list):
        raise ValueError("model_routing.json routes 必须是数组")
    for route in routes:
        if not isinstance(route, dict):
            raise ValueError("model_routing.json routes 每项必须是对象")
        model = route.get("model")
        if model not in models:
            raise ValueError(f"model_routing.json route 引用未知模型: {model}")
        when = route.get("when", {})
        if not isinstance(when, dict):
            raise ValueError("model_routing.json route.when 必须是对象")
    for model_key, relative_dir in models.items():
        if not isinstance(model_key, str) or not model_key:
            raise ValueError("model_routing.json models key 必须是非空字符串")
        if not isinstance(relative_dir, str) or not relative_dir:
            raise ValueError(f"model_routing.json models.{model_key} 必须是非空字符串路径")
        if Path(relative_dir).is_absolute() or ".." in Path(relative_dir).parts:
            raise ValueError(f"model_routing.json models.{model_key} 必须是候选目录内相对路径")
    return {
        "routing_path": str(routing_path),
        "default_model": default_model,
        "models": dict(sorted(models.items())),
        "routes": routes,
    }


def validate_routed_model_artifacts(
    candidate_dir: Path,
    *,
    report_path: Path | None = None,
    require_report: bool = False,
    expected_method: str | None = None,
) -> dict[str, Any]:
    routing = validate_model_routing_manifest(candidate_dir)
    child_validations: dict[str, dict[str, Any]] = {}
    for model_key, relative_dir in routing["models"].items():
        child_dir = candidate_dir / str(relative_dir)
        child_validations[model_key] = validate_model_artifacts(
            child_dir,
            require_report=False,
            expected_method=expected_method,
        )

    resolved_report = find_report(candidate_dir, report_path)
    report_summary = None
    if resolved_report is None and require_report:
        raise ValueError("发布前要求训练报告，但候选目录未找到 lgbm_rank_report*.json")
    if resolved_report is not None:
        report_summary = validate_report(resolved_report, expected_method=expected_method)

    default_validation = child_validations[str(routing["default_model"])]
    decision = "allow"
    if report_summary is not None:
        decision = str(report_summary.get("decision") or "allow")
    return {
        "artifact_type": "routed",
        "candidate_dir": str(candidate_dir),
        "routing": {
            "routing_path": routing["routing_path"],
            "default_model": routing["default_model"],
            "models": sorted(routing["models"].keys()),
            "model_count": len(routing["models"]),
            "route_count": len(routing["routes"]),
        },
        "child_models": child_validations,
        "feature_count": default_validation.get("feature_count"),
        "numeric_count": default_validation.get("numeric_count"),
        "categorical_count": default_validation.get("categorical_count"),
        "categorical_encoding": default_validation.get("categorical_encoding"),
        "label_column": default_validation.get("label_column"),
        "train_window": default_validation.get("train_window"),
        "score_window": default_validation.get("score_window"),
        "model_params": default_validation.get("model_params"),
        "model_sha256": None,
        "metadata_sha256": None,
        "report": report_summary,
        "decision": decision,
    }


def validate_model_artifacts(
    candidate_dir: Path,
    *,
    report_path: Path | None = None,
    require_report: bool = False,
    expected_method: str | None = None,
) -> dict[str, Any]:
    if (candidate_dir / "model_routing.json").exists():
        return validate_routed_model_artifacts(
            candidate_dir,
            report_path=report_path,
            require_report=require_report,
            expected_method=expected_method,
        )

    model_path = candidate_dir / "model.txt"
    metadata_path = candidate_dir / "model_metadata.json"
    if not model_path.exists():
        raise ValueError(f"候选模型缺少 model.txt: {model_path}")
    if not metadata_path.exists():
        raise ValueError(f"候选模型缺少 model_metadata.json: {metadata_path}")
    metadata = read_json(metadata_path)
    metadata_summary = validate_metadata(metadata)

    resolved_report = find_report(candidate_dir, report_path)
    report_summary = None
    if resolved_report is None and require_report:
        raise ValueError("发布前要求训练报告，但候选目录未找到 lgbm_rank_report*.json")
    if resolved_report is not None:
        report_summary = validate_report(resolved_report, expected_method=expected_method)

    decision = "allow"
    if report_summary is not None:
        decision = str(report_summary.get("decision") or "allow")
    return {
        "artifact_type": "single",
        **metadata_summary,
        "candidate_dir": str(candidate_dir),
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "model_sha256": file_hash(model_path),
        "metadata_sha256": file_hash(metadata_path),
        "report": report_summary,
        "decision": decision,
    }


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def replace_target_from_source(source_dir: Path, target_dir: Path, temp_dir: Path) -> None:
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    shutil.copytree(source_dir, temp_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    temp_dir.rename(target_dir)


def build_model_card(summary: dict[str, Any]) -> dict[str, Any]:
    validation = summary.get("validation") or {}
    report = validation.get("report") or {}
    return {
        "model_version": summary.get("version") or summary.get("rollback_version"),
        "mode": summary.get("mode"),
        "source": summary.get("source"),
        "target": summary.get("target"),
        "method": summary.get("method"),
        "archive_path": summary.get("archive_path") or summary.get("current_archive_path"),
        "artifact_type": validation.get("artifact_type"),
        "routing": validation.get("routing"),
        "promotion_decision": validation.get("decision"),
        "feature_count": validation.get("feature_count"),
        "label_column": validation.get("label_column"),
        "train_window": validation.get("train_window"),
        "score_window": validation.get("score_window"),
        "model_params": validation.get("model_params"),
        "model_sha256": validation.get("model_sha256"),
        "metadata_sha256": validation.get("metadata_sha256"),
        "dataset": report.get("dataset"),
        "feature_manifest": report.get("feature_manifest"),
        "rolling_summary": report.get("rolling_summary") or {},
        "rolling_fold_count": report.get("rolling_fold_count"),
    }


def write_model_card(target_dir: Path, summary: dict[str, Any]) -> None:
    card_path = target_dir / "model_card.json"
    card_path.write_text(json.dumps(build_model_card(summary), ensure_ascii=False, indent=2), encoding="utf-8")


def describe_current_model(target_dir: Path | None = None) -> dict[str, Any]:
    target_dir = target_dir or resolve_default_target_dir()
    validation = validate_model_artifacts(target_dir, expected_method=target_dir.name)
    return {
        "mode": "describe-current",
        "source": str(target_dir),
        "target": str(target_dir),
        "validation": validation,
    }


def method_archive_root(target_dir: Path) -> Path:
    return target_dir.parent / "archive" / target_dir.name


def archive_matches_target(path: Path, target_dir: Path) -> bool:
    card_path = path / "model_card.json"
    if not card_path.exists():
        return False
    try:
        card = read_json(card_path)
    except ValueError:
        return False
    target = card.get("target")
    return bool(target) and Path(str(target)).name == target_dir.name


def archive_source_for_version(target_dir: Path, version: str) -> Path:
    scoped = method_archive_root(target_dir) / version
    if scoped.exists():
        return scoped
    legacy = target_dir.parent / "archive" / version
    if legacy.exists() and archive_matches_target(legacy, target_dir):
        return legacy
    return scoped


def archive_dirs_for_target(target_dir: Path) -> list[Path]:
    archive_parent = target_dir.parent / "archive"
    scoped_root = method_archive_root(target_dir)
    dirs: list[Path] = []
    if scoped_root.exists():
        dirs.extend(item for item in scoped_root.iterdir() if item.is_dir())
    if archive_parent.exists():
        for item in archive_parent.iterdir():
            if item == scoped_root or not item.is_dir():
                continue
            if archive_matches_target(item, target_dir):
                dirs.append(item)
    return sorted(dirs, key=lambda item: item.name, reverse=True)


def list_archived_models(target_dir: Path | None = None, *, expected_method: str | None = None) -> list[dict[str, Any]]:
    target_dir = target_dir or resolve_default_target_dir()
    method = expected_method or target_dir.name
    rows: list[dict[str, Any]] = []
    for path in archive_dirs_for_target(target_dir):
        rows.append(
            {
                "mode": "list-archives",
                "version": path.name,
                "source": str(path),
                "target": str(target_dir),
                "validation": validate_model_artifacts(path, expected_method=method),
            }
        )
    return rows


def promote_model(
    candidate_dir: Path,
    target_dir: Path | None = None,
    *,
    report_path: Path | None = None,
    dry_run: bool = False,
    require_report: bool = False,
    expected_method: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    target_dir = target_dir or resolve_default_target_dir()
    method = expected_method or target_dir.name
    timestamp = now or utc_timestamp()
    validation = validate_model_artifacts(
        candidate_dir,
        report_path=report_path,
        require_report=require_report,
        expected_method=method,
    )
    archive_root = method_archive_root(target_dir)
    archive_path = archive_root / timestamp
    temp_target = target_dir.parent / f".{target_dir.name}.tmp-{timestamp}"

    summary = {
        "mode": "dry-run" if dry_run else "promote",
        "method": method,
        "source": str(candidate_dir),
        "target": str(target_dir),
        "archive_path": str(archive_path) if target_dir.exists() else None,
        "version": timestamp,
        "validation": validation,
    }
    if dry_run:
        return summary

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        archive_root.mkdir(parents=True, exist_ok=True)
        if archive_path.exists():
            raise ValueError(f"归档版本已存在: {archive_path}")
        shutil.move(str(target_dir), str(archive_path))
    replace_target_from_source(candidate_dir, target_dir, temp_target)
    write_model_card(target_dir, summary)
    return summary


def rollback_model(
    target_dir: Path | None = None,
    version: str | None = None,
    *,
    dry_run: bool = False,
    expected_method: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    target_dir = target_dir or resolve_default_target_dir()
    method = expected_method or target_dir.name
    if not version:
        raise ValueError("rollback 必须指定 archive version")
    timestamp = now or utc_timestamp()
    archive_root = method_archive_root(target_dir)
    source = archive_source_for_version(target_dir, version)
    if not source.exists():
        raise ValueError(f"找不到回滚版本: {source}")
    validation = validate_model_artifacts(source, expected_method=method)
    current_archive = archive_root / f"rollback-current-{timestamp}"
    temp_target = target_dir.parent / f".{target_dir.name}.rollback-tmp-{timestamp}"
    summary = {
        "mode": "dry-run" if dry_run else "rollback",
        "method": method,
        "rollback_version": version,
        "source": str(source),
        "target": str(target_dir),
        "current_archive_path": str(current_archive) if target_dir.exists() else None,
        "version": timestamp,
        "validation": validation,
    }
    if dry_run:
        return summary

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        if current_archive.exists():
            raise ValueError(f"当前模型归档版本已存在: {current_archive}")
        shutil.move(str(target_dir), str(current_archive))
    replace_target_from_source(source, target_dir, temp_target)
    write_model_card(target_dir, summary)
    return summary


def print_chinese_summary(summary: dict[str, Any]) -> None:
    validation = summary.get("validation") or {}
    report = validation.get("report") or {}
    print("LightGBM 模型维护摘要")
    print(f"模式: {summary.get('mode')}")
    print(f"来源: {summary.get('source')}")
    print(f"目标: {summary.get('target')}")
    if summary.get("archive_path"):
        print(f"旧模型归档: {summary.get('archive_path')}")
    if summary.get("current_archive_path"):
        print(f"当前模型归档: {summary.get('current_archive_path')}")
    print(f"特征数: {validation.get('feature_count')}")
    print(f"label: {validation.get('label_column')}")
    print(f"训练窗口: {validation.get('train_window')}")
    print(f"打分窗口: {validation.get('score_window')}")
    print(f"model_sha256: {validation.get('model_sha256')}")
    print(f"metadata_sha256: {validation.get('metadata_sha256')}")
    if report:
        print(f"训练报告: {report.get('report_path')}")
        print(f"rolling 折数: {report.get('rolling_fold_count')}")
        rolling_summary = report.get("rolling_summary") or {}
        for key in sorted(rolling_summary):
            print(f"rolling: {key}={rolling_summary[key]}")


def print_archive_list(rows: Sequence[dict[str, Any]]) -> None:
    print("LightGBM 归档模型列表")
    if not rows:
        print("无归档模型")
        return
    for row in rows:
        validation = row.get("validation") or {}
        print(f"version: {row.get('version')}")
        print(f"source: {row.get('source')}")
        print(f"label: {validation.get('label_column')}")
        print(f"feature_count: {validation.get('feature_count')}")
        print(f"train_window: {validation.get('train_window')}")
        print(f"score_window: {validation.get('score_window')}")
        print(f"decision: {validation.get('decision')}")
        print("")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote or rollback LightGBM model artifacts for the Rust default runtime.")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--candidate-dir", type=Path, help="候选模型目录，包含 model.txt 和 model_metadata.json")
    parser.add_argument("--runtime-root", type=Path, help="runtime root；未传时按 shell 环境变量再当前目录 .env 解析")
    parser.add_argument("--target-dir", type=Path, help="runtime 当前模型目录；未传时使用 <runtime-root>/models/<method>")
    parser.add_argument("--report", type=Path, help="训练/rolling report JSON；未传时从候选目录自动查找")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-report", action="store_true", help="要求发布前必须有 rolling report")
    parser.add_argument("--describe-current", action="store_true", help="打印当前激活模型摘要")
    parser.add_argument("--list-archives", action="store_true", help="列出可切换的归档模型")
    parser.add_argument("--rollback", help="回滚到 runtime archive 下的指定版本")
    return parser.parse_args(argv)


def add_dry_run_promote_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("dry-run-promote", description="dry-run 发布候选模型")
    add_promote_parser_arguments(parser)
    parser.set_defaults(handler=main_from_dry_run_promote_args)
    return parser


def add_promote_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("promote", description="正式发布候选模型")
    add_promote_parser_arguments(parser)
    parser.set_defaults(handler=main_from_promote_args)
    return parser


def add_rollback_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("rollback", description="回滚到归档版本")
    parser.add_argument("archive_version")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(handler=main_from_rollback_args)
    return parser


def add_promote_parser_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--require-report", action="store_true")


def main_from_dry_run_promote_args(args: argparse.Namespace) -> int:
    args.dry_run = True
    return main_from_promote_args(args)


def main_from_promote_args(args: argparse.Namespace) -> int:
    try:
        target_dir = args.target_dir or resolve_default_target_dir(args.runtime_root, method=args.method)
        summary = promote_model(
            args.candidate_dir,
            target_dir,
            report_path=args.report,
            dry_run=bool(getattr(args, "dry_run", False)),
            require_report=args.require_report,
            expected_method=args.method,
        )
        print_chinese_summary(summary)
        return 0
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


def main_from_rollback_args(args: argparse.Namespace) -> int:
    try:
        target_dir = args.target_dir or resolve_default_target_dir(args.runtime_root, method=args.method)
        summary = rollback_model(target_dir, args.archive_version, dry_run=args.dry_run, expected_method=args.method)
        print_chinese_summary(summary)
        return 0
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        target_dir = args.target_dir or resolve_default_target_dir(args.runtime_root, method=args.method)
        actions = int(bool(args.describe_current)) + int(bool(args.list_archives)) + int(bool(args.rollback)) + int(bool(args.candidate_dir))
        if actions != 1:
            raise ValueError("必须且只能选择一种动作：--describe-current、--list-archives、--rollback 或 --candidate-dir")
        if args.describe_current:
            summary = describe_current_model(target_dir)
            print_chinese_summary(summary)
        elif args.list_archives:
            rows = list_archived_models(target_dir, expected_method=args.method)
            print_archive_list(rows)
        elif args.rollback:
            summary = rollback_model(target_dir, args.rollback, dry_run=args.dry_run, expected_method=args.method)
            print_chinese_summary(summary)
        else:
            summary = promote_model(
                args.candidate_dir,
                target_dir,
                report_path=args.report,
                dry_run=args.dry_run,
                require_report=args.require_report,
                expected_method=args.method,
            )
            print_chinese_summary(summary)
        return 0
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
