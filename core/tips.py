#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""游戏提示（Tips）：主菜单 / 加载 / 战役胜利 / 战役失败 时随机显示一条。

**你只需要编辑 tips.txt**（项目根目录），一行一条，空行和 # 开头的行会被忽略。
改完不用重新打包 —— 游戏每次启动都会重新读。

文件位置（按优先级）：
  1. 包外的 tips.txt（同学自己加的，放在 App 旁边或 data/ 目录）
  2. 程序目录的 tips.txt（随包分发的默认内容）

如果文件不存在或全是注释，会回落到内置的几条默认提示（保证不空白）。
"""

from __future__ import annotations

import os
import random
from typing import List, Optional

# 内置兜底（tips.txt 为空时用）
DEFAULT_TIPS = [
    "薄牌组通常比厚牌组强 —— 商店可以删卡。",
    "囤资源不如早出力，早打赢少挨打。",
    "勋章能叠加出意想不到的组合，别只看单张效果。",
    "遇到打不过的精英，绕开也是一种战术。",
]

# 英文模式的兜底（tips.txt 由用户自己写，中英随他；
# 但如果文件是空的，英文界面不该蹦出中文）
DEFAULT_TIPS_EN = [
    "Thin decks usually beat fat decks — the shop lets you remove cards.",
    "Spending resources early beats hoarding them: win sooner, bleed less.",
    "Medals combine in ways you will not expect; do not judge them alone.",
    "Skipping an elite you cannot beat is a legitimate tactic.",
]

# 按场景分节的文件标记
SECTION_MARKERS = {
    "menu": ("[菜单]", "[menu]", "[主菜单]"),
    "load": ("[加载]", "[load]", "[loading]"),
    "win": ("[胜利]", "[win]", "[通关]"),
    "lose": ("[失败]", "[lose]", "[战败]"),
}

_cache: dict = {}


def _candidate_paths() -> List[str]:
    """tips.txt 的查找顺序。"""
    out = []
    try:
        import sys
        # 打包后：App 旁边（用户可改）
        if getattr(sys, "frozen", False):
            exe = os.path.realpath(sys.executable)
            p = exe
            for _ in range(3):
                p = os.path.dirname(p)
            if p.endswith(".app"):
                p = os.path.dirname(p)
            out.append(os.path.join(p, "tips.txt"))
            base = getattr(sys, "_MEIPASS", None)
            if base:
                out.append(os.path.join(base, "tips.txt"))
        # 源码环境：项目根
        here = os.path.dirname(os.path.abspath(__file__))
        out.append(os.path.join(os.path.dirname(here), "tips.txt"))
    except Exception:
        pass
    # data/ 目录（用户自己放）
    try:
        from . import run as _run
        d = getattr(_run, "DATA_DIR", None)
        if d:
            out.insert(0, os.path.join(d, "tips.txt"))
    except Exception:
        pass
    return out


def split_bilingual(line: str) -> tuple:
    """把「中文 | 英文」拆成两半。

    支持的分隔符：主用 ``|``，也兼容全角 ``｜``。
    没写英文时返回 (中文, "")，英文界面就回落到中文那条。

        薄牌组通常比厚牌组强。 | Thin decks usually beat fat decks.

    ->  ("薄牌组通常比厚牌组强。", "Thin decks usually beat fat decks.")
    """
    for sep in ("|", "｜"):
        if sep in line:
            zh, _, en = line.partition(sep)
            return zh.strip(), en.strip()
    return line.strip(), ""


def _parse(text: str) -> dict:
    """解析 tips.txt，支持 [菜单] / [胜利] 这类分节标记。

    返回值里每条都是 ``(中文, 英文)`` 二元组；英文为空表示只写了中文。
    """
    sections: dict = {"general": []}
    cur = "general"
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        matched = None
        for key, marks in SECTION_MARKERS.items():
            if any(low == m.lower() for m in marks):
                matched = key
                break
        if matched:
            cur = matched
            sections.setdefault(cur, [])
            continue
        sections.setdefault(cur, []).append(split_bilingual(line))
    return sections


def load(force: bool = False) -> dict:
    """读取并缓存 tips。返回 {section: [tip, ...]}。"""
    global _cache
    if _cache and not force:
        return _cache
    for p in _candidate_paths():
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = _parse(f.read())
                if any(data.values()):
                    _cache = data
                    return _cache
        except Exception:
            continue
    _cache = {"general": list(DEFAULT_TIPS)}
    return _cache


def reload() -> None:
    """清缓存（改完 tips.txt 想立即生效时调用）。"""
    global _cache
    _cache = {}


def tips_path() -> str:
    """当前实际使用的 tips.txt 路径（可能不存在）。"""
    for p in _candidate_paths():
        if os.path.isfile(p):
            return p
    # 都没有就返回第一个候选，方便 UI 提示"该放哪儿"
    c = _candidate_paths()
    return c[0] if c else "tips.txt"


def random_tip(scene: str = "general", rng: Optional[random.Random] = None) -> str:
    """随机取一条提示。

    scene: menu / load / win / lose / general
    找不到对应场景就用 general，再没有就用内置兜底。绝不返回空串。
    """
    # 判断内容到底来自用户的 tips.txt，还是 load() 的兜底 ——
    # load() 已经做过兜底，不能只看它的返回值。
    raw = _raw_file_sections()
    from_file = any(raw.values())
    data = raw if from_file else {}
    entries = list(data.get(scene) or []) or list(data.get("general") or [])

    try:
        from . import i18n as _i18n
        want_en = _i18n.is_english()
    except Exception:
        want_en = False

    if entries:
        # 每条是 (zh, en)。英文界面优先取英文；没写英文就回落中文，
        # 保证英文界面也不会空白。
        pool = []
        for item in entries:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                zh, en = item[0], item[1]
            else:
                zh, en = str(item), ""
            pick = (en or zh) if want_en else (zh or en)
            if pick:
                pool.append(pick)
    else:
        # 文件里没内容 -> 内置兜底
        pool = list(DEFAULT_TIPS_EN) if want_en else list(DEFAULT_TIPS)

    r = rng or random
    try:
        return str(r.choice(pool))
    except Exception:
        return pool[0] if pool else ""


def _raw_file_sections() -> dict:
    """只读文件、**不做兜底**的解析结果（判断文件是否为空要用它）。"""
    for _p in _candidate_paths():
        try:
            if os.path.isfile(_p):
                with open(_p, "r", encoding="utf-8") as f:
                    return _parse(f.read())
        except Exception:
            continue
    return {}


def file_is_empty() -> bool:
    """tips.txt 存在但没有任何有效内容（作者还没写）。"""
    try:
        return not any(_raw_file_sections().values())
    except Exception:
        return True


def source() -> str:
    """提示来自哪里：'file'（文件里有内容）或 'builtin'（内置兜底）。"""
    try:
        return "file" if any(_raw_file_sections().values()) else "builtin"
    except Exception:
        return "builtin"



def count(scene: Optional[str] = None) -> int:
    """提示条数（自检/调试用）。"""
    data = load()
    if scene:
        return len(data.get(scene) or [])
    return sum(len(v) for v in data.values())


__all__ = ["DEFAULT_TIPS", "DEFAULT_TIPS_EN", "load", "reload", "tips_path", "random_tip",
           "count", "SECTION_MARKERS", "file_is_empty", "source"]
