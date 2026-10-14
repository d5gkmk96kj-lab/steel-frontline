#!/bin/bash
# 钢铁战线 Steel Frontline —— macOS 双击启动
# 直接双击本文件即可开始游戏（无需联网、无需安装任何东西）

cd "$(dirname "$0")" || exit 1

echo "==========================================="
echo "  钢铁战线 · Steel Frontline"
echo "==========================================="
echo

# 找一个可用的 python3
PY=""
for cand in python3 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import tkinter" >/dev/null 2>&1; then
            PY="$cand"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "错误：找不到带 tkinter 的 Python 3。"
    echo "请安装 Python 3（python.org 版本自带 tkinter）。"
    echo
    read -n 1 -s -r -p "按任意键退出..."
    exit 1
fi

echo "使用: $PY"
echo "启动中..."
echo

"$PY" main.py 2>/dev/null
CODE=$?

if [ $CODE -ne 0 ]; then
    echo
    echo "游戏异常退出（代码 $CODE）。"
    read -n 1 -s -r -p "按任意键关闭..."
fi
