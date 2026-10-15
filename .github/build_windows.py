#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 Windows 上调用 PyInstaller 打包。

由 .github/workflows/build-windows.yml 调用。

为什么单独写成一个脚本，而不是把参数塞进 YAML：
  1. YAML 里拼 90 个参数容易出错（空格、引号、分号）
  2. Windows 的 --add-data 用 ';' 分隔，从 bash 传参时 ';' 会被
     当成命令分隔符，很难转义
  3. 出了错能看到完整命令

**关键：所有路径一律用绝对路径，且不传 --specpath。**
原因：--specpath 会让 --add-data / --icon 的相对路径
基于 spec 目录去解析，于是打包时报
    Icon input file ...\build_win\packaging\icon.ico not found
（这是实际踩过的坑，浪费了两轮 CI）
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

# 项目根 = 本文件所在目录的上一级（.github/ -> 项目根）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NAME = "SteelFrontlineWindowsRework"
DIST = os.path.join(ROOT, "dist_win")
WORK = os.path.join(ROOT, "build_win")

# 需要显式声明的模块（PyInstaller 的静态分析可能漏掉动态导入）
HIDDEN = [
    "core", "core.run", "core.cards", "core.enemies", "core.engine",
    "core.versus", "core.netplay", "core.saves", "core.session",
    "core.reconnect", "core.relay_client", "core.updater",
    "core.cleanup", "core.tips", "core.audio", "core.i18n",
    "core.version", "core.cheats", "core.deckbuild",
    "qt", "qt.qapp", "qt.qscreens", "qt.qbattle", "qt.qversus",
    "qt.qlobby", "qt.qdeckbuild", "qt.qsave", "qt.qupdate",
    "qt.qcleanup", "qt.qconsole", "qt.qfx", "qt.qmap",
    "qt.qtheme", "qt.qwidgets",
]


def main() -> int:
    icon = os.path.join(ROOT, "packaging", "icon.ico")
    locales = os.path.join(ROOT, "locales")
    tips = os.path.join(ROOT, "tips.txt")
    entry = os.path.join(ROOT, "packaging", "app_entry.py")

    # 先检查必需文件都在
    missing = [p for p in (icon, locales, tips, entry) if not os.path.exists(p)]
    if missing:
        for p in missing:
            print("::error::缺少必需文件: %s" % p)
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", NAME,
        "--distpath", DIST,
        "--workpath", WORK,
        # 注意：这里**故意不传 --specpath**
        "--paths", ROOT,
        # --add-data 的源路径必须是绝对路径
        "--add-data", "%s%slocales" % (locales, os.pathsep),
        "--add-data", "%s%s." % (tips, os.pathsep),
        "--icon", icon,
    ]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    cmd.append(entry)

    print("=" * 62)
    print(" PyInstaller 打包")
    print("=" * 62)
    print("  ROOT :", ROOT)
    print("  icon :", icon)
    print("  参数个数:", len(cmd))
    print()

    # 清理旧产物，避免用到上次的缓存
    for d in (DIST, WORK):
        shutil.rmtree(d, ignore_errors=True)

    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("::error::PyInstaller 失败，退出码 %d" % r.returncode)
        return r.returncode

    exe = os.path.join(DIST, NAME, NAME + ".exe")
    if not os.path.isfile(exe):
        print("::error::没找到产物: %s" % exe)
        for root, _dirs, files in os.walk(DIST):
            for f in files[:5]:
                print("   ", os.path.join(root, f))
        return 1

    print()
    print("=" * 62)
    print(" 打包成功")
    print("  exe:", exe)
    print("  大小: %.1f MB" % (os.path.getsize(exe) / 1048576.0))
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
