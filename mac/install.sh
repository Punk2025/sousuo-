#!/usr/bin/env bash
# macOS 一键安装：Homebrew → Python → 依赖 → Chromium → 创建启动器
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PIPELINE="$REPO/pipeline"
LAUNCHER="$REPO/启动SearchPipe.command"

# ── 工具 ──────────────────────────────────────────────

say()  { echo "$*"; }
step() { echo ""; echo "▶ $*"; }

brew_shellenv() {
  if [[ -x /opt/homebrew/bin/brew ]]; then
    # shellcheck source=/dev/null
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    # shellcheck source=/dev/null
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

python_ok() {
  local py="$1"
  [[ -x "$py" ]] && "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null
}

find_python() {
  brew_shellenv
  local c
  for c in \
    "${PYTHON:-}" \
    "$(command -v python3 2>/dev/null || true)" \
    /opt/homebrew/bin/python3 \
    /opt/homebrew/opt/python@3.12/bin/python3 \
    /opt/homebrew/opt/python@3.11/bin/python3 \
    /usr/local/bin/python3 \
    /usr/local/opt/python@3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3
  do
    [[ -n "$c" && -x "$c" ]] || continue
    if python_ok "$c"; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

ensure_brew() {
  brew_shellenv
  if command -v brew >/dev/null 2>&1; then
    return 0
  fi

  step "安装 Homebrew（Mac 包管理器，用于安装 Python）"
  say "  过程中可能要求输入 Mac 登录密码，属正常情况。"
  say ""
  read -r -p "  按回车开始安装 Homebrew，Ctrl+C 取消…" _

  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  brew_shellenv

  if ! command -v brew >/dev/null 2>&1; then
    say "❌ Homebrew 安装后仍未找到 brew 命令。"
    say "   请关闭本窗口，重新打开终端后再双击「Mac一键安装.command」。"
    exit 1
  fi
}

install_python() {
  ensure_brew
  step "通过 Homebrew 安装 Python 3.12（约 1～3 分钟）"
  brew install python@3.12 2>/dev/null || brew install python3
  brew_shellenv

  # 把 brew 的 python 链到 PATH 前面
  if [[ -d /opt/homebrew/opt/python@3.12/bin ]]; then
    export PATH="/opt/homebrew/opt/python@3.12/bin:$PATH"
  elif [[ -d /usr/local/opt/python@3.12/bin ]]; then
    export PATH="/usr/local/opt/python@3.12/bin:$PATH"
  fi
}

create_launcher() {
  cat > "$LAUNCHER" << 'LAUNCHER_EOF'
#!/bin/bash
# SearchPipe 日常启动（安装完成后用这个）
cd "$(dirname "$0")"
chmod +x pipeline/start.sh mac/install.sh 2>/dev/null || true

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

export PATH="/opt/homebrew/opt/python@3.12/bin:/usr/local/opt/python@3.12/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
exec ./pipeline/start.sh
LAUNCHER_EOF
  chmod +x "$LAUNCHER"

  # 桌面快捷方式
  local desk="$HOME/Desktop/SearchPipe.command"
  cp "$LAUNCHER" "$desk"
  chmod +x "$desk"
  say "  已创建桌面快捷方式：~/Desktop/SearchPipe.command"
}

# ── 主流程 ────────────────────────────────────────────

if [[ "$(uname -s)" != "Darwin" ]]; then
  say "❌ 此安装脚本仅适用于 macOS。"
  exit 1
fi

clear 2>/dev/null || true
say "╔══════════════════════════════════════╗"
say "║   SearchPipe · Mac 一键安装          ║"
say "╚══════════════════════════════════════╝"
say ""
say "  将自动安装：Python → 项目依赖 → Chromium 浏览器"
say "  首次约需 3～8 分钟（视网络而定）"
say ""

chmod +x "$PIPELINE/setup.sh" "$PIPELINE/start.sh" 2>/dev/null || true

step "检查 Python 3.9+"
PY="$(find_python || true)"

if [[ -z "${PY:-}" ]]; then
  say "  本机未找到合适版本的 Python，开始安装…"
  install_python
  PY="$(find_python || true)"
fi

if [[ -z "${PY:-}" ]]; then
  say "❌ Python 安装后仍未找到可用版本。"
  say "   请重启终端后重试，或手动安装：https://www.python.org/downloads/"
  exit 1
fi

export PYTHON="$PY"
export PATH="$(dirname "$PY"):$PATH"
say "  使用：$("$PY" --version 2>&1) → $PY"

step "安装项目依赖与 Playwright Chromium"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
PYTHON="$PY" "$PIPELINE/setup.sh"

step "创建启动快捷方式"
create_launcher
say "  项目内启动器：$LAUNCHER"

say ""
say "✅ 安装完成！"
say ""
read -r -p "是否现在启动控制面板？[Y/n] " ans
ans="${ans:-Y}"
if [[ "$ans" =~ ^[Yy]$ ]]; then
  exec "$LAUNCHER"
else
  say ""
  say "下次启动方式："
  say "  · 双击桌面「SearchPipe.command」"
  say "  · 或双击「启动SearchPipe.command」"
  say ""
  read -r -p "按回车关闭此窗口…" _
fi
