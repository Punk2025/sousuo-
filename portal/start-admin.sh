#!/usr/bin/env bash
# 启动心屿内容站 + 后台（默认端口 8767）
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x ../pipeline/.venv/bin/python ]]; then
  PY=../pipeline/.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "未找到 python3"
  exit 1
fi

"$PY" -c "import flask" 2>/dev/null || "$PY" -m pip install -q flask

exec "$PY" server.py
