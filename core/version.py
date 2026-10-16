#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 —— 版本与名称的**唯一**定义处。

改版本号只需要改这里，界面标题、关于页、打包的 Info.plist 全部跟着变。
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 版本
# --------------------------------------------------------------------------
VERSION = "0.9.25"
VERSION_LABEL = "0.9.25 测试版"
VERSION_LABEL_EN = "0.9.25 Beta"

# 版本阶段：alpha / beta / rc / stable
STAGE = "beta"

# 构建号（同版本多次出包时递增；打包脚本会读它）
BUILD = 1

# --------------------------------------------------------------------------
# 名称
# --------------------------------------------------------------------------
NAME_ZH = "钢铁战线"
NAME_EN = "Steel Frontline"

# Windows 版后缀（用户要求：加 "Windows Rework"）
PLATFORM_SUFFIX = "Windows Rework"

# 当前是不是 Windows 版（打包时由构建脚本写死，运行时也认平台）
# 用于决定窗口标题、关于页、安装包名字是否带 "Windows Rework"。
IS_WINDOWS_EDITION = False


def platform_suffix() -> str:
    """Windows 版返回 "Windows Rework"，其它平台返回空串。"""
    if IS_WINDOWS_EDITION:
        return PLATFORM_SUFFIX
    try:
        import sys
        if sys.platform.startswith("win"):
            return PLATFORM_SUFFIX
    except Exception:
        pass
    return ""


def window_name() -> str:
    """窗口/标题里显示的名字（Windows 版会自动带后缀）。"""
    sfx = platform_suffix()
    return ("%s %s" % (NAME_ZH, sfx)) if sfx else NAME_ZH


def bundle_name() -> str:
    """打包用的名字（不含空格，Windows 版带后缀）。"""
    sfx = platform_suffix()
    return (NAME_ZH + sfx.replace(" ", "")) if sfx else NAME_ZH


def bundle_name_public() -> str:
    """公开版的打包名。"""
    return bundle_name() + "公开版"

# 界面上用的完整名（中英并排）
FULL_NAME = "%s %s" % (NAME_ZH, NAME_EN)

# 用于 .app 的 bundle 名（不要有空格，避免脚本引用出问题）
BUNDLE_NAME = NAME_ZH
BUNDLE_NAME_PUBLIC = NAME_ZH + "公开版"

BUNDLE_ID = "local.steelfrontline.game"
BUNDLE_ID_PUBLIC = "local.steelfrontline.game.public"

# --------------------------------------------------------------------------
# 拼接好的显示串
# --------------------------------------------------------------------------
def _is_en() -> bool:
    """当前界面语言是不是英文。取不到就当中文。"""
    try:
        from . import i18n
        return bool(i18n.is_english())
    except Exception:
        return False


def _label() -> str:
    """当前语言下的版本标签（0.9.02 测试版 / 0.9.02 Beta）。"""
    return VERSION_LABEL_EN if _is_en() else VERSION_LABEL


def title() -> str:
    """窗口标题：钢铁战线 Steel Frontline · v0.9.02 测试版

    Windows 版会在名字后加 "Windows Rework"。
    """
    sfx = platform_suffix()
    base = ("%s %s %s" % (NAME_ZH, NAME_EN, sfx)) if sfx else FULL_NAME
    return "%s · v%s" % (base, _label())


def short() -> str:
    """短版本：v0.9.02 测试版 / v0.9.02 Beta"""
    return "v" + _label()


def about() -> str:
    """关于页用的一行。"""
    sfx = platform_suffix()
    base = ("%s %s %s" % (NAME_ZH, NAME_EN, sfx)) if sfx else FULL_NAME
    return "%s v%s" % (base, _label())


def macos_version_string() -> str:
    """Info.plist 的 CFBundleShortVersionString（必须是纯数字点分）。"""
    return VERSION


def macos_build_string() -> str:
    """Info.plist 的 CFBundleVersion（纯数字点分）。"""
    return "%s.%d" % (VERSION, BUILD)


__all__ = [
    "VERSION", "VERSION_LABEL", "VERSION_LABEL_EN", "STAGE", "BUILD",
    "NAME_ZH", "NAME_EN", "FULL_NAME", "BUNDLE_NAME", "BUNDLE_NAME_PUBLIC",
    "PLATFORM_SUFFIX", "IS_WINDOWS_EDITION", "platform_suffix",
    "window_name", "bundle_name", "bundle_name_public",
    "BUNDLE_ID", "BUNDLE_ID_PUBLIC",
    "title", "short", "about", "macos_version_string", "macos_build_string",
]
