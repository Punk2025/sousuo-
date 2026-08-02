#!/usr/bin/env bash
# 强制使用本机 Playwright 浏览器缓存（覆盖 Cursor 沙箱注入的路径）
set -euo pipefail
cd "$(dirname "$0")"
export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Caches/ms-playwright"
exec python3 server.py
