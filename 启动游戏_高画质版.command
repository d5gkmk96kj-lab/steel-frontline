#!/bin/bash
# 钢铁战线 Steel Frontline —— PyQt6 高画质版启动器（macOS 双击）
#
# 需要先安装 PyQt6（一次性）：
#     python3 -m pip install --user PyQt6
#
# 如果没装，本脚本会自动尝试安装。

cd "$(dirname "$0")" || exit 1

echo "==========================================="
echo "  钢铁战线 · Steel Frontline  (PyQt6 高画质版)"
echo "==========================================="
echo

PY=""
for cand in python3 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done

if [ -z "$PY" ]; then
    echo "错误：找不到 python3。"
    read -n 1 -s -r -p "按任意键退出..."
    exit 1
fi

if ! "$PY" -c "import PyQt6" >/dev/null 2>&1; then
    echo "未检测到 PyQt6，正在安装（约 60MB，只需一次）..."
    echo
    "$PY" -m pip install --user PyQt6 || {
        echo
        echo "安装失败。你可以改用无依赖的 Tkinter 版：双击 启动游戏.command"
        read -n 1 -s -r -p "按任意键退出..."
        exit 1
    }
    echo
fi

echo "使用: $PY"
echo "启动中..."
echo

"$PY" qt/main_qt.py "$@" 2>/dev/null
CODE=$?

if [ $CODE -ne 0 ]; then
    echo
    echo "游戏异常退出（代码 $CODE）。"
    echo "提示：如果 PyQt6 有问题，可改用 Tkinter 版：双击 启动游戏.command"
    read -n 1 -s -r -p "按任意键关闭..."
fi
