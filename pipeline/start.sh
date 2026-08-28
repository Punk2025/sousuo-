#!/usr/bin/env bash
# 一键启动：自动 setup → 开后台 → 打开浏览器
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

case "$(uname -s)" in
  Darwin)
    export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
    ;;
  *)
    export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
    ;;
esac

chmod +x "$ROOT/setup.sh" 2>/dev/null || true
"$ROOT/setup.sh"

# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"

ADMIN_URL="http://127.0.0.1:8878/admin/"

echo ""
echo "▶ 启动控制面板 → $ADMIN_URL"
echo "  按 Ctrl+C 停止服务"
echo ""

# 等服务起来后再打开浏览器
(
  sleep 1.5
  case "$(uname -s)" in
    Darwin) open "$ADMIN_URL" 2>/dev/null || true ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$ADMIN_URL" 2>/dev/null || true
      fi
      ;;
  esac
) &

exec python server.py
