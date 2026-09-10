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
