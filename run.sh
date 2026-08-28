#!/usr/bin/env bash
# 从仓库根目录一键启动 pipeline
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/pipeline/start.sh"
