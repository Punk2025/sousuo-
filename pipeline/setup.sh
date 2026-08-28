#!/usr/bin/env bash
# 首次或更新后：创建 venv、安装依赖、安装 Playwright Chromium
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 本机浏览器缓存（避免 IDE 沙箱注入错误路径）
case "$(uname -s)" in
  Darwin)
    export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
    ;;
  *)
    export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
    ;;
esac

echo "▶ SearchPipe 环境检查…"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "❌ 未找到 Python：$PY"
  echo "   macOS 请双击根目录「Mac一键安装.command」自动安装"
  exit 1
fi

if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "❌ 需要 Python 3.9 及以上，当前：$("$PY" --version 2>&1)"
  exit 1
fi

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  echo "▶ 创建虚拟环境 .venv …"
  "$PY" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

echo "▶ 安装 Python 依赖…"
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo "▶ 检查 Playwright Chromium（首次约需 1 分钟，已安装则跳过）…"
python -m playwright install chromium

mkdir -p data data/history

echo "✅ 环境就绪"
