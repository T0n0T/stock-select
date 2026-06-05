#!/usr/bin/env bash
#
# install.sh — stock-select 安装脚本
#
# 功能：
#   1. cargo install 构建并安装二进制 stock-select-rs
#   2. 将 .agents/skills 下的技能同步到 ~/.agents/skills
#   3. 将项目 .env 复制到 runtime/ 目录供生产使用
#
set -euo pipefail

# 定位项目根目录：优先 git 根目录，否则退回到脚本所在目录的父目录
if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    CDPATH="" cd "$git_root"
else
    CDPATH="" cd "$(cd "$(dirname "$0")" && pwd -P)/.."
fi

PROJECT_ROOT="$PWD"
SKILLS_SRC="$PROJECT_ROOT/.agents/skills"
SKILLS_DST="$HOME/.agents/skills"

# ── 1. cargo install ──────────────────────────────────────────────────────────
echo "==> 安装二进制 stock-select-rs …"
cargo install --path "$PROJECT_ROOT" 2>&1 | sed 's/^/    /'
echo "    完成。二进制位于 $(which stock-select-rs 2>/dev/null || echo "$HOME/.cargo/bin/stock-select-rs")"

# ── 2. 安装技能到 ~/.agents/skills ────────────────────────────────────────────
if [ -d "$SKILLS_SRC" ]; then
    echo "==> 安装技能到 $SKILLS_DST …"
    mkdir -p "$SKILLS_DST"
    for skill_dir in "$SKILLS_SRC"/*/; do
        skill_name="$(basename "$skill_dir")"
        if [ -d "$SKILLS_DST/$skill_name" ]; then
            echo "    - 更新技能: $skill_name"
            cp -r "$skill_dir"/* "$SKILLS_DST/$skill_name/"
        else
            echo "    - 安装技能: $skill_name"
            cp -r "$skill_dir" "$SKILLS_DST/"
        fi
    done
    echo "    完成。技能列表:"
    for skill_dir in "$SKILLS_DST"/*/; do
        echo "      - $(basename "$skill_dir")"
    done
else
    echo "==> 跳过技能安装（未找到 $SKILLS_SRC）"
fi

echo ""
echo "安装完成。"
echo ""
echo "使用方法:"
echo "  stock-select-rs run --method b2 --pick-date <YYYY-MM-DD>"
echo "  stock-select-rs screen --method b2 --pick-date <YYYY-MM-DD>"


