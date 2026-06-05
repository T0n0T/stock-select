#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
用法:
  scripts/model_maintenance.sh status
  scripts/model_maintenance.sh archives
  scripts/model_maintenance.sh promote <candidate_dir> [extra args...]
  scripts/model_maintenance.sh dry-run-promote <candidate_dir> [extra args...]
  scripts/model_maintenance.sh switch <archive_version> [extra args...]
  scripts/model_maintenance.sh rollback <archive_version> [extra args...]

说明:
  status            查看当前激活模型摘要
  archives          列出归档模型
  promote           正式发布候选模型
  dry-run-promote   dry-run 发布候选模型
  switch/rollback   切换到归档版本
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command="$1"
shift

case "$command" in
  status)
    uv run scripts/ml/promote_lgbm_model.py --describe-current "$@"
    ;;
  archives)
    uv run scripts/ml/promote_lgbm_model.py --list-archives "$@"
    ;;
  promote)
    if [[ $# -lt 1 ]]; then
      echo "错误: promote 需要 candidate_dir" >&2
      usage
      exit 2
    fi
    candidate_dir="$1"
    shift
    uv run scripts/ml/promote_lgbm_model.py --candidate-dir "$candidate_dir" --require-report "$@"
    ;;
  dry-run-promote)
    if [[ $# -lt 1 ]]; then
      echo "错误: dry-run-promote 需要 candidate_dir" >&2
      usage
      exit 2
    fi
    candidate_dir="$1"
    shift
    uv run scripts/ml/promote_lgbm_model.py --candidate-dir "$candidate_dir" --dry-run --require-report "$@"
    ;;
  switch|rollback)
    if [[ $# -lt 1 ]]; then
      echo "错误: $command 需要 archive_version" >&2
      usage
      exit 2
    fi
    version="$1"
    shift
    uv run scripts/ml/promote_lgbm_model.py --rollback "$version" "$@"
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
