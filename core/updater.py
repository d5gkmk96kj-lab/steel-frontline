#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 —— 版本更新检查。

设计原则
--------
* **完全离线可用**：不联网时所有功能照常，检查失败只是静默跳过。
* **只在需要时联网**：读一个几 KB 的版本清单，不做任何别的请求。
* **绝不阻塞界面**：检查跑在后台线程，结果通过回调交给 UI。
* **绝不自动改文件**：只提示 + 打开浏览器，下载安装由用户自己决定。

版本清单来自仓库根目录的 ``version.json``：

    {
      "version": "0.10",
      "label": "0.10 测试版",
      "label_en": "0.10 Beta",
      "released": "2026-10-15",
      "url": "https://github.com/.../releases/SteelFrontline-Public-v0.10-beta.dmg",
      "notes": ["修复：控制台 kill 后卡死", "新增：存档管理界面"]
    }

比较规则是**数字逐段比较**（``0.9 < 0.10``），不是字符串比较。
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import version as V

# 版本清单的地址（仓库根目录，raw 直链）
MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "d5gkmk96kj-lab/steel-frontline/main/version.json"
)

# 下载页（提示用户时打开）
DOWNLOAD_PAGE = "https://github.com/d5gkmk96kj-lab/steel-frontline/releases"

# 超时（秒）—— 网络不好时不能把用户卡住
TIMEOUT = 6


# --------------------------------------------------------------------------
# 版本号比较
# --------------------------------------------------------------------------
def parse_version(text: str) -> tuple:
    """把 "0.10.2" 解析成 (0, 10, 2)。非数字段丢弃。

    这样 ``0.10`` 才会正确地大于 ``0.9``（字符串比较会反过来）。
    """
    parts = re.findall(r"\d+", str(text or ""))
    return tuple(int(p) for p in parts) if parts else (0,)


def is_newer(remote: str, local: str = "") -> bool:
    """远端版本是否比本地新。"""
    if not remote:
        return False
    try:
        return parse_version(remote) > parse_version(local or V.VERSION)
    except Exception:
        return False


# --------------------------------------------------------------------------
# 清单数据结构
# --------------------------------------------------------------------------
@dataclass
class UpdateInfo:
    version: str = ""
    label: str = ""
    label_en: str = ""
    released: str = ""
    url: str = ""
    notes: List[str] = field(default_factory=list)
    notes_en: List[str] = field(default_factory=list)
    mandatory: bool = False

    def display_label(self) -> str:
        """当前语言下的版本名。"""
        try:
            from . import i18n
            if i18n.is_english():
                return self.label_en or self.label or self.version
        except Exception:
            pass
        return self.label or self.version

    def display_notes(self) -> List[str]:
        try:
            from . import i18n
            if i18n.is_english() and self.notes_en:
                return list(self.notes_en)
        except Exception:
            pass
        return list(self.notes)

    def to_dict(self) -> dict:
        return {
            "version": self.version, "label": self.label,
            "label_en": self.label_en, "released": self.released,
            "url": self.url, "notes": list(self.notes),
            "notes_en": list(self.notes_en), "mandatory": self.mandatory,
        }


def parse_manifest(data) -> Optional[UpdateInfo]:
    """解析版本清单。格式不对返回 None，绝不抛异常。"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    ver = data.get("version")
    if not isinstance(ver, str) or not ver.strip():
        return None

    def _strs(key):
        v = data.get(key)
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    return UpdateInfo(
        version=ver.strip(),
        label=str(data.get("label") or ver).strip(),
        label_en=str(data.get("label_en") or "").strip(),
        released=str(data.get("released") or "").strip(),
        url=str(data.get("url") or "").strip(),
        notes=_strs("notes"),
        notes_en=_strs("notes_en"),
        mandatory=bool(data.get("mandatory", False)),
    )


# --------------------------------------------------------------------------
# 检查
# --------------------------------------------------------------------------
def fetch_manifest(timeout: int = TIMEOUT) -> Optional[UpdateInfo]:
    """同步拉取版本清单。失败返回 None（离线/超时/格式错都算）。"""
    try:
        import urllib.request
        req = urllib.request.Request(
            MANIFEST_URL,
            headers={"User-Agent": "SteelFrontline/%s" % V.VERSION,
                     "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(256 * 1024)          # 最多 256KB，够用
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = raw.decode("utf-8", "ignore")
        return parse_manifest(text)
    except Exception:
        return None


def check_for_update(timeout: int = TIMEOUT) -> Optional[UpdateInfo]:
    """检查是否有新版本。有新版本返回 UpdateInfo，否则 None。"""
    info = fetch_manifest(timeout)
    if info is None:
        return None
    if is_newer(info.version, V.VERSION):
        return info
    return None


def check_async(on_result: Callable[[Optional[UpdateInfo], str], None],
                timeout: int = TIMEOUT) -> threading.Thread:
    """后台线程检查，避免卡住界面。

    ``on_result(info, err)``：info 为 UpdateInfo 或 None；
    err 为空字符串表示检查成功（哪怕没有新版本）。
    """
    def worker():
        try:
            info = check_for_update(timeout)
            on_result(info, "")
        except Exception as exc:
            on_result(None, str(exc))

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


# --------------------------------------------------------------------------
# 打开下载页
# --------------------------------------------------------------------------
def open_download_page(url: str = "") -> bool:
    """用系统浏览器打开下载页。"""
    target = url or DOWNLOAD_PAGE
    try:
        import subprocess
        import sys
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["start", "", target], shell=True)
        else:
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception:
        return False


__all__ = [
    "MANIFEST_URL", "DOWNLOAD_PAGE", "UpdateInfo",
    "parse_version", "is_newer", "parse_manifest", "fetch_manifest",
    "check_for_update", "check_async", "open_download_page",
]
