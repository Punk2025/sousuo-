#!/bin/bash
# 已安装后快速启动；首次使用请双击「Mac一键安装.command」
cd "$(dirname "$0")"

if [[ -x "./启动SearchPipe.command" ]]; then
  exec ./启动SearchPipe.command
fi

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi
export PATH="/opt/homebrew/opt/python@3.12/bin:/usr/local/opt/python@3.12/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

chmod +x pipeline/start.sh mac/install.sh 2>/dev/null || true
exec ./pipeline/start.sh
