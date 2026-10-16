#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡组预设：玩家可以先配好几套卡组，开局时一键选用。

用户需求
--------
「玩家可以自己在一个页面预设好卡组，然后到时候直接选」

设计
----
* 存成 ``<data>/presets.json``（一个 JSON 数组）
* 每套预设：名字 + 卡牌 id 列表 + 创建时间
* 支持：新建 / 重命名 / 删除 / 复制
* 开局时（卡组构筑界面）可以直接套用
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional, Tuple


def data_dir() -> str:
    env = os.environ.get("SF_GAME_HOME")
    if env:
        return env
    try:
        from core import run as _run
        d = os.path.dirname(getattr(_run, "SAVE_PATH", "") or "")
        if d:
            return d
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents", "钢铁战线")


def presets_path() -> str:
    return os.path.join(data_dir(), "presets.json")


MAX_PRESETS = 30
MAX_NAME_LEN = 20


def load_all() -> List[Dict]:
    """读全部预设。坏数据一律跳过，不抛异常。"""
    try:
        with open(presets_path(), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return []
    if not isinstance(d, list):
        return []
    out = []
    for item in d:
        if not isinstance(item, dict):
            continue
        cards = item.get("cards")
        if not isinstance(cards, list) or not cards:
            continue
        clean = [str(x) for x in cards if isinstance(x, str) and x]
        if not clean:
            continue
        out.append({
            "name": str(item.get("name") or "未命名")[:MAX_NAME_LEN],
            "cards": clean,
            "created": float(item.get("created") or 0),
        })
    return out[:MAX_PRESETS]


def save_all(items: List[Dict]) -> bool:
    try:
        p = presets_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items[:MAX_PRESETS], f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def add(name: str, cards: List[str]) -> Tuple[bool, str]:
    """新建一套预设。"""
    name = (name or "").strip()[:MAX_NAME_LEN]
    if not name:
        return False, "请填名字。"
    cards = [str(c) for c in (cards or []) if c]
    if not cards:
        return False, "卡组是空的。"
    items = load_all()
    if len(items) >= MAX_PRESETS:
        return False, "预设数量已达上限（%d 套）。" % MAX_PRESETS
    if any(x["name"] == name for x in items):
        return False, "已经有同名的预设了。"
    items.append({"name": name, "cards": cards, "created": time.time()})
    if not save_all(items):
        return False, "写入失败。"
    return True, "已保存。"


def rename(old: str, new: str) -> Tuple[bool, str]:
    new = (new or "").strip()[:MAX_NAME_LEN]
    if not new:
        return False, "名字不能为空。"
    items = load_all()
    hit = False
    for x in items:
        if x["name"] == old:
            if any(y["name"] == new and y is not x for y in items):
                return False, "已经有同名的预设了。"
            x["name"] = new
            hit = True
            break
    if not hit:
        return False, "找不到这套预设。"
    return (True, "已重命名。") if save_all(items) else (False, "写入失败。")


def delete(name: str) -> Tuple[bool, str]:
    items = load_all()
    left = [x for x in items if x["name"] != name]
    if len(left) == len(items):
        return False, "找不到这套预设。"
    return (True, "已删除。") if save_all(left) else (False, "写入失败。")


def get(name: str) -> Optional[Dict]:
    for x in load_all():
        if x["name"] == name:
            return x
    return None


def overwrite(name: str, cards: List[str]) -> Tuple[bool, str]:
    """用新卡组覆盖已有预设。"""
    cards = [str(c) for c in (cards or []) if c]
    if not cards:
        return False, "卡组是空的。"
    items = load_all()
    for x in items:
        if x["name"] == name:
            x["cards"] = cards
            x["created"] = time.time()
            return (True, "已更新。") if save_all(items) else (False, "写入失败。")
    return False, "找不到这套预设。"


def duplicate(name: str) -> Tuple[bool, str]:
    src = get(name)
    if src is None:
        return False, "找不到这套预设。"
    new_name = (name + " 副本")[:MAX_NAME_LEN]
    i = 2
    while get(new_name) is not None:
        new_name = ("%s 副本%d" % (name, i))[:MAX_NAME_LEN]
        i += 1
    return add(new_name, src["cards"])
