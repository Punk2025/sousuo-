#!/usr/bin/env bash
# SearchPipe · 终端一键（清隔离 → 缺啥装啥 → 启动）
# 用法（在项目根目录）：
#   bash mac/终端一键.sh
# 或：
#   cd /你的/SearchPipe-便携包 && bash mac/终端一键.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

say()  { echo "$*"; }
step() { echo ""; echo "▶ $*"; }

say "╔══════════════════════════════════════╗"
say "║   SearchPipe · 终端一键              ║"
say "╚══════════════════════════════════════╝"
say "  目录：$REPO"
say ""

step "清除 macOS 隔离标记（Telegram/网盘传输后必需）"
xattr -cr "$REPO" 2>/dev/null || true
chmod +x \
  "$REPO/mac/"*.sh \
  "$REPO/pipeline/setup.sh" \
  "$REPO/pipeline/start.sh" \
  "$REPO/run.sh" \
  "$REPO/"*.command \
  2>/dev/null || true
say "  已处理。"

need_install=0
if [[ ! -x "$REPO/pipeline/.venv/bin/python" ]]; then
  need_install=1
fi
if [[ ! -f "$REPO/pipeline/.venv/bin/playwright" ]]; then
  # venv 在但依赖可能不全；有 python 就再跑一次 setup 也安全
  if [[ "$need_install" -eq 0 ]]; then
    if ! "$REPO/pipeline/.venv/bin/python" -c "import flask, playwright" 2>/dev/null; then
      need_install=1
    fi
  fi
fi

if [[ "$need_install" -eq 1 ]]; then
  step "检测到尚未安装完整，开始安装…"
  # 非交互：装完直接启动（避免卡在 read）
  export SEARCHPIPE_NONINTERACTIVE=1
  bash "$REPO/mac/install.sh"
else
  say ""
  say "  环境已就绪，跳过安装。"
fi

step "启动控制面板 → http://127.0.0.1:8878/admin/"
say "  停止：在本窗口按 Ctrl+C"
say ""

# Apple Silicon Playwright 路径修正（与 start.sh 一致）
if [[ "$(uname -m)" = "arm64" ]] && [[ -z "${PLAYWRIGHT_HOST_PLATFORM_OVERRIDE:-}" ]]; then
  export PLAYWRIGHT_HOST_PLATFORM_OVERRIDE="mac15-arm64"
fi
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"

exec "$REPO/pipeline/start.sh"
