#!/usr/bin/env bash
# 从 GitHub 克隆/更新仓库，并执行 Mac 一键安装
# 用法（终端一条命令）：
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Punk2025/sousuo-/main/mac/bootstrap.sh)"
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Punk2025/sousuo-.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/SearchPipe}"

say()  { echo "$*"; }
step() { echo ""; echo "▶ $*"; }

if [[ "$(uname -s)" != "Darwin" ]]; then
  say "❌ 此脚本仅适用于 macOS。"
  exit 1
fi

clear 2>/dev/null || true
say "╔══════════════════════════════════════╗"
say "║   SearchPipe · 云端下载并安装        ║"
say "╚══════════════════════════════════════╝"
say ""
say "  仓库：$REPO_URL"
say "  目录：$INSTALL_DIR"
say ""

ensure_git() {
  if command -v git >/dev/null 2>&1; then
    return 0
  fi
  step "未检测到 git，尝试安装 Xcode 命令行工具"
  say "  若弹出系统对话框，请点击「安装」；装完后再运行本命令。"
  xcode-select --install 2>/dev/null || true
  say ""
  say "❌ 请先安装 git（Xcode 命令行工具），然后重新运行本命令。"
  say "   或手动执行：xcode-select --install"
  exit 1
}

clone_or_update() {
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    step "目录已存在，拉取最新代码…"
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH" || true
  elif [[ -e "$INSTALL_DIR" ]]; then
    say "❌ 目标路径已存在但不是 git 仓库：$INSTALL_DIR"
    say "   请删除/改名该文件夹，或指定其它目录："
    say "   INSTALL_DIR=~/Desktop/搜索网 /bin/bash -c \"\$(curl -fsSL .../bootstrap.sh)\""
    exit 1
  else
    step "从 GitHub 克隆项目…"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  fi
}

ensure_git
clone_or_update

step "进入项目并执行安装"
chmod +x "$INSTALL_DIR/mac/install.sh" \
  "$INSTALL_DIR/Mac一键安装.command" \
  "$INSTALL_DIR/一键运行.command" \
  "$INSTALL_DIR/run.sh" \
  "$INSTALL_DIR/pipeline/setup.sh" \
  "$INSTALL_DIR/pipeline/start.sh" 2>/dev/null || true

cd "$INSTALL_DIR"
exec ./mac/install.sh
