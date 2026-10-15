#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Windows 发布包里的 README-FIRST.txt。

由 .github/workflows/build-windows.yml 调用。
用 Python 而不是 shell 写，是因为内容里有中文、反斜杠和引号 ——
在 YAML + PowerShell 里转义这些极易出错（真踩过）。

环境变量：
    NAME  可执行文件名（不含 .exe）
    VER   版本号
    OUT   输出目录
"""

from __future__ import annotations

import os

NAME = os.environ.get("NAME", "SteelFrontlineWindowsRework")
VER = os.environ.get("VER", "dev")
OUT = os.environ.get("OUT", "release")

LINES = [
    "=" * 62,
    " 钢铁战线 Steel Frontline - Windows Rework",
    " Version: " + VER,
    "=" * 62,
    "",
    "How to run:",
    "  1. Double-click " + NAME + ".exe",
    "  2. If Windows SmartScreen appears, click 'More info', then",
    "     'Run anyway'. This is normal - the app has no paid Microsoft",
    "     code-signing certificate. The full source is on GitHub if you",
    "     want to verify it yourself.",
    "  3. First launch may take 5-10 seconds.",
    "",
    "Saves:  %APPDATA%\\钢铁战线\\data\\",
    "Music:  drop audio files into music\\ and name them",
    "        music1.mp3, music2.ogg, music3.wav, ...",
    "",
    "-" * 62,
    " 怎么玩：",
    "   1. 双击 " + NAME + ".exe",
    "   2. 如果弹出「Windows 已保护你的电脑」：",
    "      点「更多信息」→「仍要运行」",
    "      （本软件没有购买微软的代码签名证书，这是正常现象）",
    "   3. 首次启动可能要等 5-10 秒",
    "   4. 存档位置：%APPDATA%\\钢铁战线\\data\\",
    "   5. 加音乐：把音频文件放进 music\\，命名 music1.mp3 / music2.ogg ...",
    "",
    "-" * 62,
    " ⚠️ 本游戏全部由 AI（DeepSeek-V4.1-Flash）生成 ⚠️",
    " This game is entirely AI-generated.",
    "=" * 62,
    "",
]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "README-FIRST.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
