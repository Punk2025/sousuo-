#!/bin/bash
cd "$(dirname "$0")"
echo "正在清除隔离标记…"
xattr -cr \
  "启动SearchPipe.command" \
  "一键运行.command" \
  "Mac一键安装.command" \
  "解除拦截.command" \
  "启动 SearchPipe.app" \
  pipeline/start.sh \
  pipeline/setup.sh \
  mac/install.sh \
  2>/dev/null || true
chmod +x \
  "启动SearchPipe.command" \
  "一键运行.command" \
  "Mac一键安装.command" \
  "解除拦截.command" \
  "启动 SearchPipe.app/Contents/MacOS/launcher" \
  pipeline/start.sh \
  pipeline/setup.sh \
  mac/install.sh \
  2>/dev/null || true

echo ""
echo "✅ 已处理完毕。"
echo ""
echo "接下来请："
echo "  1) 对「启动 SearchPipe.app」按住 Control 点击（或右键）→ 打开"
echo "  2) 弹出提示时再点「打开」"
echo "  以后就可以直接双击了。"
echo ""
read -r -p "按回车尝试打开启动器…" _
open "启动 SearchPipe.app"
