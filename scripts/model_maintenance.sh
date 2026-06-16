#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
用法:
  scripts/model_maintenance.sh [--method <method>] status
  scripts/model_maintenance.sh [--method <method>] archives
  scripts/model_maintenance.sh [--method <method>] promote <candidate_dir> [extra args...]
  scripts/model_maintenance.sh [--method <method>] dry-run-promote <candidate_dir> [extra args...]
  scripts/model_maintenance.sh [--method <method>] switch <archive_version> [extra args...]
  scripts/model_maintenance.sh [--method <method>] rollback <archive_version> [extra args...]

说明:
  --method <method> 维护目标，默认 b2；例如 --method b3
  status            查看当前激活模型摘要和 eod/intraday 路由状态
  archives          列出归档模型
  promote           正式发布候选模型
  dry-run-promote   dry-run 发布候选模型
  switch/rollback   切换到归档版本
EOF
}

print_status_header() {
  local method="$1"
  printf '%s\n' '============================================================'
  printf '模型状态: %s\n' "$method"
  printf '%s\n' '============================================================'
  printf '\n'
}

print_model_routing_status() {
  local method="$1"
  shift
  python3 - "$method" "$@" <<'PY'
import argparse
import json
import os
import sys
from pathlib import Path


def load_dotenv_runtime_root() -> str | None:
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "STOCK_SELECT_RUNTIME_ROOT":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        print(f"  {path}: JSON 解析失败: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--target-dir", type=Path)
    args, unknown = parser.parse_known_args(sys.argv[2:])
    if unknown:
        print(f"错误: status 不支持参数: {' '.join(unknown)}", file=sys.stderr)
        raise SystemExit(2)
    return args


def runtime_root(cli_runtime_root: Path | None = None) -> Path:
    if cli_runtime_root is not None:
        return cli_runtime_root
    value = os.environ.get("STOCK_SELECT_RUNTIME_ROOT") or load_dotenv_runtime_root() or "runtime"
    return Path(value)


def count_list(value) -> int | None:
    return len(value) if isinstance(value, list) else None


def coalesce(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def feature_summary(model_dir: Path, card: dict) -> str:
    metadata = summary_metadata(model_dir)
    numeric_count = coalesce(card.get("numeric_feature_count"), count_list(metadata.get("numeric_columns")), 0)
    categorical_count = coalesce(
        card.get("categorical_feature_count"),
        count_list(metadata.get("categorical_columns")),
        0,
    )
    feature_count = coalesce(
        card.get("feature_count"),
        count_list(metadata.get("feature_names")),
        numeric_count + categorical_count if isinstance(numeric_count, int) and isinstance(categorical_count, int) else None,
        "?",
    )
    label = coalesce(card.get("label_column"), metadata.get("label_column"), "?")
    return f"{feature_count} 个特征 (数值 {numeric_count}, 分类 {categorical_count}), label={label}"


def routing_manifest(model_dir: Path) -> dict:
    manifest = read_json(model_dir / "model_routing.json")
    models = manifest.get("models")
    if not isinstance(models, dict) or not models:
        return {}
    return manifest


def routed_child_dir(model_dir: Path, relative_dir: str) -> Path:
    child = Path(relative_dir)
    return child if child.is_absolute() else model_dir / child


def default_routed_model_dir(model_dir: Path, manifest: dict) -> Path | None:
    models = manifest.get("models")
    if not isinstance(models, dict) or not models:
        return None
    default_model = manifest.get("default_model")
    relative_dir = models.get(default_model) if isinstance(default_model, str) else None
    if not isinstance(relative_dir, str):
        first_key = sorted(models)[0]
        relative_dir = models.get(first_key)
    if not isinstance(relative_dir, str):
        return None
    return routed_child_dir(model_dir, relative_dir)


def summary_metadata(model_dir: Path) -> dict:
    metadata = read_json(model_dir / "model_metadata.json")
    if metadata:
        return metadata
    manifest = routing_manifest(model_dir)
    default_dir = default_routed_model_dir(model_dir, manifest)
    if default_dir is None:
        return {}
    return read_json(default_dir / "model_metadata.json")


def artifact_summary(model_dir: Path) -> str:
    manifest = routing_manifest(model_dir)
    if manifest:
        missing = []
        models = manifest.get("models") or {}
        for model_key, relative_dir in sorted(models.items()):
            if not isinstance(relative_dir, str):
                missing.append(f"{model_key}/model_dir")
                continue
            child_dir = routed_child_dir(model_dir, relative_dir)
            for name in ["model.txt", "model_metadata.json"]:
                if not (child_dir / name).exists():
                    missing.append(f"{model_key}/{name}")
        if not missing:
            return "OK"
        return "缺失 " + ", ".join(missing)

    required = ["model.txt", "model_metadata.json"]
    missing = [name for name in required if not (model_dir / name).exists()]
    if not missing:
        return "OK"
    return "缺失 " + ", ".join(missing)


def routed_summary(model_dir: Path) -> str | None:
    manifest = routing_manifest(model_dir)
    if not manifest:
        return None
    models = manifest.get("models") or {}
    default_model = manifest.get("default_model") or "未记录"
    return f"default={default_model}, 子模型 {len(models)} 个"


def status_summary(status: str) -> str:
    labels = {
        "ready": "可用",
        "disabled": "停用",
        "missing": "缺失",
        "not_ready": "未就绪",
    }
    return f"{status} ({labels.get(status, '未知')})"


def metric_section(card: dict) -> tuple[str, dict] | tuple[None, None]:
    for name in ("test_metrics", "rolling_summary"):
        section = card.get(name)
        if isinstance(section, dict) and section:
            return name, section
    return None, None


def metric_source_label(section_name: str, card: dict) -> str:
    if section_name == "test_metrics":
        return "test_metrics (模型卡测试集)"
    if section_name == "rolling_summary":
        fold_count = card.get("rolling_fold_count")
        if fold_count:
            return f"rolling_summary ({fold_count} 折滚动验证)"
        return "rolling_summary (滚动验证)"
    return f"{section_name} (未知口径)"


def format_percent(metrics: dict, key: str) -> str:
    if key not in metrics:
        return "指标缺失"
    try:
        return f"{float(metrics[key]):.2f}%"
    except (TypeError, ValueError):
        return str(metrics[key])


def format_rank_ic(metrics: dict, key: str) -> str:
    if key not in metrics:
        return "指标缺失"
    try:
        return f"{float(metrics[key]):.4f}"
    except (TypeError, ValueError):
        return str(metrics[key])


def print_metric_line(metrics: dict, days: int) -> None:
    prefix = f"top3_ret{days}"
    print(
        f"  Top3 {days}日表现: "
        f"正收益 {format_percent(metrics, f'{prefix}_positive_rate')} | "
        f"涨幅>=5% {format_percent(metrics, f'{prefix}_ge_5_rate')} | "
        f"非正收益 {format_percent(metrics, f'{prefix}_le_0_rate')} | "
        f">=5%捕获 {format_percent(metrics, f'{prefix}_ge_5_capture_rate')} | "
        f"RankIC {format_rank_ic(metrics, f'rank_ic_ret{days}')}"
    )


def route_title(mode: str) -> str:
    return {
        "eod": "日终模型",
        "intraday": "盘中模型",
    }.get(mode, mode)


def route_items(root: Path, state: dict, default_model_dir_text: str) -> list[tuple[str, dict]]:
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


def resolve_model_dir(root: Path, model_dir_text: str) -> Path:
    model_dir = Path(model_dir_text)
    if model_dir.is_absolute():
        return model_dir
    try:
        model_dir.relative_to(root)
        return model_dir
    except ValueError:
        return root / model_dir


def print_route(root: Path, method: str, mode: str, item: dict) -> None:
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


method = sys.argv[1]
args = parse_args()
if args.runtime_root is not None:
    root = args.runtime_root
elif args.target_dir is not None and args.target_dir.parent.name == "models":
    root = args.target_dir.parent.parent
else:
    root = runtime_root()
default_model_dir = args.target_dir or root / "models" / method
default_model_dir_text = str(args.target_dir) if args.target_dir is not None else f"models/{method}"
state_path = default_model_dir / "model_state.json"

print(f"生产路由总览: {method}")
print("-" * 60)
print(f"运行目录: {root}")
print("说明: eod=日终收盘后模型；intraday=盘中实时可计算模型")

state = read_json(state_path) if state_path.exists() else {}
for mode, item in route_items(root, state, default_model_dir_text):
    print_route(root, method, mode, item)
PY
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

method="${MODEL_METHOD:-b2}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --method)
      if [[ $# -lt 2 ]]; then
        echo "错误: --method 需要参数" >&2
        usage
        exit 2
      fi
      method="$2"
      shift 2
      ;;
    --method=*)
      method="${1#--method=}"
      shift
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command="$1"
shift

case "$command" in
  status)
    print_status_header "$method"
    print_model_routing_status "$method" "$@"
    ;;
  archives)
    uv run scripts/ml/promote_lgbm_model.py --method "$method" --list-archives "$@"
    ;;
  promote)
    if [[ $# -lt 1 ]]; then
      echo "错误: promote 需要 candidate_dir" >&2
      usage
      exit 2
    fi
    candidate_dir="$1"
    shift
    uv run scripts/ml/promote_lgbm_model.py --method "$method" --candidate-dir "$candidate_dir" --require-report "$@"
    ;;
  dry-run-promote)
    if [[ $# -lt 1 ]]; then
      echo "错误: dry-run-promote 需要 candidate_dir" >&2
      usage
      exit 2
    fi
    candidate_dir="$1"
    shift
    uv run scripts/ml/promote_lgbm_model.py --method "$method" --candidate-dir "$candidate_dir" --dry-run --require-report "$@"
    ;;
  switch|rollback)
    if [[ $# -lt 1 ]]; then
      echo "错误: $command 需要 archive_version" >&2
      usage
      exit 2
    fi
    version="$1"
    shift
    uv run scripts/ml/promote_lgbm_model.py --method "$method" --rollback "$version" "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "错误: 未知命令 $command" >&2
    usage
    exit 2
    ;;
esac
