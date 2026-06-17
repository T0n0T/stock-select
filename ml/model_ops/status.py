from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .promote import DEFAULT_METHOD, RUNTIME_ROOT_ENV
from .runtime import runtime_root_for_status


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def count_list(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def artifact_summary(model_dir: Path) -> str:
    manifest = routing_manifest(model_dir)
    if manifest:
        missing = []
        for model_key, relative_dir in sorted((manifest.get("models") or {}).items()):
            if not isinstance(relative_dir, str):
                missing.append(f"{model_key}/model_dir")
                continue
            child_dir = routed_child_dir(model_dir, relative_dir)
            for name in ["model.txt", "model_metadata.json"]:
                if not (child_dir / name).exists():
                    missing.append(f"{model_key}/{name}")
        return "OK" if not missing else "缺失 " + ", ".join(missing)
    missing = [name for name in ["model.txt", "model_metadata.json"] if not (model_dir / name).exists()]
    return "OK" if not missing else "缺失 " + ", ".join(missing)


def feature_summary(model_dir: Path, card: dict[str, Any]) -> str:
    metadata = summary_metadata(model_dir)
    numeric_count = coalesce(card.get("numeric_feature_count"), count_list(metadata.get("numeric_columns")), 0)
    categorical_count = coalesce(card.get("categorical_feature_count"), count_list(metadata.get("categorical_columns")), 0)
    feature_count = coalesce(
        card.get("feature_count"),
        count_list(metadata.get("feature_names")),
        numeric_count + categorical_count,
    )
    label = coalesce(card.get("label_column"), metadata.get("label_column"), "?")
    return f"{feature_count} 个特征 (数值 {numeric_count}, 分类 {categorical_count}), label={label}"


def resolve_model_dir(root: Path, model_dir_text: str) -> Path:
    model_dir = Path(model_dir_text)
    if model_dir.is_absolute():
        return model_dir
    try:
        model_dir.relative_to(root)
        return model_dir
    except ValueError:
        return root / model_dir


def routing_manifest(model_dir: Path) -> dict[str, Any]:
    manifest = read_json(model_dir / "model_routing.json")
    models = manifest.get("models")
    return manifest if isinstance(models, dict) and models else {}


def routed_child_dir(model_dir: Path, relative_dir: str) -> Path:
    child = Path(relative_dir)
    return child if child.is_absolute() else model_dir / child


def default_routed_model_dir(model_dir: Path, manifest: dict[str, Any]) -> Path | None:
    models = manifest.get("models")
    if not isinstance(models, dict) or not models:
        return None
    default_model = manifest.get("default_model")
    relative_dir = models.get(default_model) if isinstance(default_model, str) else None
    if not isinstance(relative_dir, str):
        first_key = sorted(models)[0]
        relative_dir = models.get(first_key)
    return routed_child_dir(model_dir, relative_dir) if isinstance(relative_dir, str) else None


def summary_metadata(model_dir: Path) -> dict[str, Any]:
    metadata = read_json(model_dir / "model_metadata.json")
    if metadata:
        return metadata
    manifest = routing_manifest(model_dir)
    default_dir = default_routed_model_dir(model_dir, manifest)
    return read_json(default_dir / "model_metadata.json") if default_dir is not None else {}


def routed_summary(model_dir: Path) -> str | None:
    manifest = routing_manifest(model_dir)
    if not manifest:
        return None
    models = manifest.get("models") or {}
    default_model = manifest.get("default_model") or "未记录"
    return f"default={default_model}, 子模型 {len(models)} 个"


def route_items(root: Path, state: dict[str, Any], default_model_dir_text: str) -> list[tuple[str, dict[str, Any]]]:
    if not state:
        item = {"status": "ready", "model_dir": default_model_dir_text}
        default_dir = resolve_model_dir(root, default_model_dir_text)
        if not (default_dir / "model_routing.json").exists():
            item["reason"] = "未找到 model_state.json；按默认日终模型目录展示"
        return [("eod", item)]
    output = []
    for mode in ("eod", "intraday"):
        item = state.get(mode)
        if isinstance(item, dict):
            output.append((mode, item))
    for mode in sorted(state):
        if mode in {"eod", "intraday"}:
            continue
        item = state.get(mode)
        if isinstance(item, dict):
            output.append((mode, item))
    return output


def status_summary(status: str) -> str:
    labels = {"ready": "可用", "disabled": "停用", "missing": "缺失", "not_ready": "未就绪"}
    return f"{status} ({labels.get(status, '未知')})"


def route_title(mode: str) -> str:
    return {"eod": "日终模型", "intraday": "盘中模型"}.get(mode, mode)


def metric_section(card: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    for name in ("test_metrics", "rolling_summary"):
        section = card.get(name)
        if isinstance(section, dict) and section:
            return name, section
    return None, None


def metric_source_label(section_name: str, card: dict[str, Any]) -> str:
    if section_name == "test_metrics":
        return "test_metrics (模型卡测试集)"
    if section_name == "rolling_summary":
        fold_count = card.get("rolling_fold_count")
        return f"rolling_summary ({fold_count} 折滚动验证)" if fold_count else "rolling_summary (滚动验证)"
    return f"{section_name} (未知口径)"


def format_percent(metrics: dict[str, Any], key: str) -> str:
    if key not in metrics:
        return "指标缺失"
    try:
        return f"{float(metrics[key]):.2f}%"
    except (TypeError, ValueError):
        return str(metrics[key])


def format_rank_ic(metrics: dict[str, Any], key: str) -> str:
    if key not in metrics:
        return "指标缺失"
    try:
        return f"{float(metrics[key]):.4f}"
    except (TypeError, ValueError):
        return str(metrics[key])


def print_metric_line(metrics: dict[str, Any], days: int) -> None:
    prefix = f"top3_ret{days}"
    print(
        f"  Top3 {days}日表现: "
        f"正收益 {format_percent(metrics, f'{prefix}_positive_rate')} | "
        f"涨幅>=5% {format_percent(metrics, f'{prefix}_ge_5_rate')} | "
        f"非正收益 {format_percent(metrics, f'{prefix}_le_0_rate')} | "
        f">=5%捕获 {format_percent(metrics, f'{prefix}_ge_5_capture_rate')} | "
        f"RankIC {format_rank_ic(metrics, f'rank_ic_ret{days}') }"
    )


def print_route(root: Path, method: str, mode: str, item: dict[str, Any]) -> None:
    status = str(item.get("status") or "ready")
    model_dir_text = str(item.get("model_dir") or f"models/{method}")
    model_dir = resolve_model_dir(root, model_dir_text)
    card = read_json(model_dir / "model_card.json")
    print()
    print(f"{route_title(mode)} ({mode})")
    print(f"  状态: {status_summary(status)}")
    print(f"  模型目录: {model_dir}")
    print(f"  产物检查: {artifact_summary(model_dir)}")
    route_summary = routed_summary(model_dir)
    if route_summary:
        print(f"  路由模型: {route_summary}")
    print(f"  发布版本: {coalesce(card.get('model_version'), '未记录')}")
    print(f"  训练窗口: {coalesce(card.get('train_window'), '未记录')}")
    print(f"  打分窗口: {coalesce(card.get('score_window'), '未记录')}")
    print(f"  特征/标签: {feature_summary(model_dir, card)}")
    section_name, metrics = metric_section(card)
    if section_name and metrics:
        print(f"  指标口径: {metric_source_label(section_name, card)}")
        print_metric_line(metrics, 3)
        print_metric_line(metrics, 5)
    else:
        print("  指标口径: 未找到 test_metrics/rolling_summary")
    reason = item.get("reason")
    if reason:
        print(f"  备注: {reason}")


def print_status(*, method: str, runtime_root: Path, target_dir: Path | None = None) -> None:
    root = runtime_root
    default_model_dir = target_dir or root / "models" / method
    default_model_dir_text = str(target_dir) if target_dir is not None else f"models/{method}"
    state = read_json(default_model_dir / "model_state.json")
    print("=" * 60)
    print(f"模型状态: {method}")
    print("=" * 60)
    print()
    print(f"生产路由总览: {method}")
    print("-" * 60)
    print(f"运行目录: {root}")
    print("说明: eod=日终收盘后模型；intraday=盘中实时可计算模型")
    for mode, item in route_items(root, state, default_model_dir_text):
        print_route(root, method, mode, item)


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("status", description="查看当前激活模型摘要和路由状态")
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--target-dir", type=Path)
    parser.set_defaults(handler=main_from_args)
    return parser


def main_from_args(args: argparse.Namespace) -> int:
    try:
        root = runtime_root_for_status(method=args.method, runtime_root=args.runtime_root, target_dir=args.target_dir)
        print_status(method=args.method, runtime_root=root, target_dir=args.target_dir)
        return 0
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
