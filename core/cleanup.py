#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""旧版本清理：删除旧的 .app 和下载的旧安装包，**绝不碰存档**。

安全原则
--------
1. 只删**明确认定为我们自己的**文件（名字匹配 + 是 .app 目录 / .dmg 文件）
2. 只扫固定几个位置（/Applications、~/Applications、~/Downloads、桌面）
3. **永不删除** data/ 与 Documents 下的存档目录
4. 删除前逐项列出，让用户看过再动手
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List

# 我们自己 App 的名字（当前版本 + 公开版）
APP_NAMES = ("钢铁战线.app", "钢铁战线公开版.app", "SteelFrontline.app",
             "Steel Frontline.app",
             # Windows
             "钢铁战线", "钢铁战线.exe", "SteelFrontline.exe",
             "Steel Frontline.exe",
             # Windows Rework 版
             "钢铁战线WindowsRework", "钢铁战线WindowsRework.exe",
             "SteelFrontlineWindowsRework.exe")

# 安装包文件名特征
DMG_PATTERNS = (
    re.compile(r"^钢铁战线.*\.dmg$"),
    re.compile(r"^SteelFrontline.*\.dmg$", re.I),
    # Windows 安装包 / 压缩包
    re.compile(r"^钢铁战线.*\.(exe|zip|7z)$", re.I),
    re.compile(r"^SteelFrontline.*\.(exe|zip|7z)$", re.I),
)

# **绝对不碰**的路径片段（存档、音乐、用户数据）
PROTECTED = ("/Documents/", "/data/", "/music/", "/.git/")


@dataclass
class Junk:
    path: str
    kind: str          # "app" | "dmg"
    size: int = 0

    def size_text(self) -> str:
        n = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
            n /= 1024.0
        return "%.1f GB" % n


def _dir_size(path: str) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
    except Exception:
        pass
    return total


def _is_protected(path: str) -> bool:
    """这条路径是否属于「绝对不能删」的范围（存档 / 音乐 / 仓库）。

    注意：PROTECTED 里存的是 **POSIX 风格** 的片段（"/Documents/" 等）。
    Windows 上 os.path.abspath 会给出反斜杠路径，直接比字符串必然不匹配
    （真踩过：测试里 /Users/x/Documents/... 被判成"不受保护"）。
    所以这里先把路径统一成正斜杠再比较。
    """
    try:
        p = os.path.abspath(path).replace("\\", "/")
    except Exception:
        p = str(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return any(seg in p for seg in PROTECTED)


def _is_current(path: str) -> bool:
    """是不是**当前这个版本**自己的文件。

    桌面上的新 DMG 是用户刚下载要用的，不是垃圾。判断依据：
    文件名里带有当前版本号（或没有版本号说明是当前版）。
    """
    import re as _re
    try:
        from . import version as _V
        cur = _V.VERSION
    except Exception:
        return False
    base = os.path.basename(path)
    # 文件名里出现 x.y 这样的版本号
    found = _re.findall(r"\d+(?:\.\d+)+", base)
    if not found:
        return False                  # 没版本号的文件无法判断，不当作垃圾
    return any(_re.sub(r"^v", "", f) == cur for f in found)


def default_dirs() -> List[str]:
    """默认扫描位置（按平台）。

    macOS：/Applications + 用户目录
    Windows：安装目录 + 下载 + 桌面 + 本地程序目录
    Linux：/opt + 用户目录（尽力而为）
    """
    import sys
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        dirs = [os.path.join(os.environ.get("LOCALAPPDATA", home),
                             "Programs"),
                os.path.expanduser("~/Downloads"),
                os.path.expanduser("~/Desktop")]
        pf = os.environ.get("ProgramFiles")
        if pf:
            dirs.insert(0, pf)
        return [d for d in dirs if d]
    if sys.platform == "darwin":
        return ["/Applications", os.path.join(home, "Applications"),
                os.path.join(home, "Downloads"), os.path.join(home, "Desktop")]
    return ["/opt", "/usr/local/bin", os.path.join(home, "Downloads"),
            os.path.join(home, "Desktop")]


def scan(extra_dirs: List[str] = None, only: List[str] = None) -> List[Junk]:
    """扫描可清理的旧版本。只读，不删任何东西。

    **不包含当前版本的文件** —— 桌面上的新 DMG 是要用的，不是垃圾。

    ``only``：只扫这些目录（测试用，避免碰到真实系统目录）。
    ``extra_dirs``：在默认目录之外追加。
    """
    out: List[Junk] = []
    seen = set()

    dirs = list(only) if only else default_dirs()
    if extra_dirs:
        dirs = list(extra_dirs) + dirs

    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except Exception:
            continue
        for name in names:
            full = os.path.join(d, name)
            if full in seen or _is_protected(full):
                continue
            # .app 目录
            if name in APP_NAMES and os.path.isdir(full):
                seen.add(full)
                out.append(Junk(full, "app", _dir_size(full)))
                continue
            # .dmg 安装包
            if any(p.match(name) for p in DMG_PATTERNS) and os.path.isfile(full):
                if _is_current(full):
                    continue          # 当前版本的安装包，别当成垃圾
                seen.add(full)
                try:
                    sz = os.path.getsize(full)
                except Exception:
                    sz = 0
                out.append(Junk(full, "dmg", sz))
    out.sort(key=lambda j: -j.size)
    return out


def total_size(items: List[Junk]) -> int:
    return sum(j.size for j in items)


def remove(items: List[Junk]) -> tuple:
    """删除给定的条目。返回 (成功数, 失败列表)。"""
    ok = 0
    failed = []
    for j in items:
        if _is_protected(j.path):          # 双保险
            failed.append(j.path)
            continue
        try:
            import shutil
            if os.path.isdir(j.path):
                shutil.rmtree(j.path)
            elif os.path.isfile(j.path):
                os.remove(j.path)
            else:
                continue
            ok += 1
        except Exception:
            failed.append(j.path)
    return ok, failed


__all__ = ["Junk", "scan", "remove", "total_size", "default_dirs",
           "APP_NAMES", "PROTECTED"]
