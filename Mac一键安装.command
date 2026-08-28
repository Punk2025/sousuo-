#!/bin/bash
# macOS 双击安装：Python + 依赖 + Chromium + 桌面快捷方式
cd "$(dirname "$0")"
chmod +x mac/install.sh pipeline/setup.sh pipeline/start.sh 2>/dev/null || true
exec ./mac/install.sh
