#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 i18n —— 中英文切换。

设计目标：**不重写既有代码**。
游戏里几乎所有面向玩家的文案本来就是中文字面量，所以这里用
「查表翻译」而不是「改写每一处」：

    from core import i18n
    i18n.t("开始战役")          # -> "Start Campaign" (英文) / "开始战役" (中文)

翻译表放在 ``locales/zh.json`` 与 ``locales/en.json``。
``zh.json`` 是**原文索引**（中文 -> 中文），用于：
  * 统一收集所有需要翻译的文案
  * 英文表缺失时自动回落，不会出现空白

切换语言：
    i18n.set_lang("en")        # 全局立即生效，下次重绘即英文
    i18n.set_lang("zh")

对 f-string 的支持：
    既有代码大量使用 ``f"{name} 打出了 {card}"``。要翻译这种句子，
    把中文**模板**登记进表里，用 ``fmt()``：

    i18n.fmt("{name} 打出了 {card}", name="A", card="B")

两种写法都能用；``t()`` 用于完整短句，``fmt()`` 用于带占位符的。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

_LOCK = threading.RLock()

# 当前语言（"zh" / "en"）
_lang: str = "zh"

# 翻译表缓存：lang -> {原文: 译文}
_tables: Dict[str, Dict[str, str]] = {}

# 语言显示名（设置界面用）
LANG_NAMES = {
    "zh": "中文",
    "en": "English",
}
LANG_ORDER = ("zh", "en")

_LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "locales")


def locales_dir() -> str:
    """locales 目录（打包后位于 PyInstaller 的 _MEIPASS 资源里）。"""
    import sys as _sys
    cands = []
    # 1) 冻结环境：--add-data locales:locales 会落在 _MEIPASS/locales
    if getattr(_sys, "frozen", False):
        base = getattr(_sys, "_MEIPASS", None)
        if base:
            cands.append(os.path.join(base, "locales"))
    # 2) 源码环境
    cands.append(os.path.normpath(_LOCALES_DIR))
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(os.path.dirname(here), "locales"))
    cands.append(os.path.join(here, "locales"))
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return os.path.normpath(_LOCALES_DIR)


def _load(lang: str) -> Dict[str, str]:
    """读一个语言的翻译表（带缓存）。缺失/损坏时返回空表，绝不抛异常。"""
    with _LOCK:
        if lang in _tables:
            return _tables[lang]
        table: Dict[str, str] = {}
        # 先读主表，再叠加分片（en_ui.json / en_data.json …）。
        # 分片是为了让多个译者并行工作、各写各的文件，互不冲突。
        paths = [os.path.join(locales_dir(), "%s.json" % lang)]
        try:
            import glob as _glob
            paths += sorted(_glob.glob(
                os.path.join(locales_dir(), "%s_*.json" % lang)))
        except Exception:
            pass
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(k, str) and isinstance(v, str) and v:
                            # 先到先得：en.json（合并后的权威表）优先，
                            # 分片只补空缺，避免同名 key 互相覆盖。
                            table.setdefault(k, v)
            except Exception:
                continue
        _tables[lang] = table
        return table


def reload_tables() -> None:
    """清缓存（改完 json 不想重启时用）。"""
    with _LOCK:
        _tables.clear()


def lang() -> str:
    return _lang


def set_lang(code: str) -> str:
    """切换语言。返回实际生效的语言码。"""
    global _lang
    c = str(code or "").strip().lower()
    if c not in LANG_NAMES:
        c = "zh"
    with _LOCK:
        _lang = c
    return _lang


def toggle_lang() -> str:
    """在可用语言间循环切换。"""
    try:
        i = LANG_ORDER.index(_lang)
    except ValueError:
        i = 0
    return set_lang(LANG_ORDER[(i + 1) % len(LANG_ORDER)])


def is_english() -> bool:
    return _lang == "en"


def t(text: Any):
    """翻译一个完整句子。查不到就**原样返回中文**（不会变空白）。

    非字符串原样返回，方便直接包住任意变量。
    """
    if not isinstance(text, str) or not text:
        return text
    # 去掉 markdown 风格的 **加粗** 星号。
    # 卡牌数据用 ** 强调关键字，但 Qt 的 drawText 不认 markdown，
    # 之前星号会原样印在卡面上（37 张卡都有，真 bug）。
    text = text.replace("**", "")
    if _lang == "zh":
        return text
    tbl = _load(_lang)
    hit = tbl.get(text)
    if isinstance(hit, str) and hit:
        return hit
    # 英文表没有 -> 回落中文表（保证不是空白）
    zh = _load("zh").get(text)
    return zh if isinstance(zh, str) and zh else text


def fmt(template: str, **kw) -> str:
    """翻译带占位符的模板并填充。

        fmt("{name} 打出了 {card}", name="A", card="B")
    """
    tpl = t(template)
    if not isinstance(tpl, str):
        return str(template)
    try:
        return tpl.format(**kw)
    except Exception:
        # 占位符对不上时退回原模板，避免崩溃
        try:
            return str(template).format(**kw)
        except Exception:
            return str(template)


def has(text: str) -> bool:
    """当前语言是否有这条翻译（自检/覆盖率统计用）。"""
    if not isinstance(text, str):
        return False
    if _lang == "zh":
        return True
    return text in _load(_lang)


def stats() -> Dict[str, int]:
    """翻译覆盖率统计。"""
    zh = _load("zh")
    en = _load("en")
    total = len(zh)
    done = sum(1 for k in zh if k in en)
    return {"zh": total, "en": len(en), "covered": done,
            "missing": max(0, total - done)}


def coverage() -> float:
    """英文覆盖率 0..1。"""
    s = stats()
    if s["zh"] <= 0:
        return 1.0
    return s["covered"] / float(s["zh"])
