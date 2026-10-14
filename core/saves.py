#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 —— 存档槽管理（多存档 + 导入导出）。

设计
----
* 每个存档独立成一个文件，放在 ``data/saves/`` 下：

      data/saves/<存档 id>.json

* 同时维护一份 ``data/save.json`` 指向**最近使用**的存档，
  这样「继续上次战役」永远接得上，老逻辑无需改动。

* 存档文件自带元信息（名字、时间、进度摘要），可以**直接发给别人**：
  对方把这个 .json 放进自己的 ``data/saves/`` 即可，或者用界面里的
  「导入存档」选文件。

对外接口（都很简单，出错返回 False / 空列表，不抛异常）
    slots()                     -> [SlotInfo, ...]  按时间倒序
    save_new(run, name)         -> 存档 id 或 None
    save_to(slot_id, run)       -> bool
    load(slot_id)               -> RunState 或 None
    delete(slot_id)             -> bool
    rename(slot_id, name)       -> bool
    export_to(slot_id, path)    -> bool
    import_from(path)           -> 新存档 id 或 None
    latest_slot()               -> 存档 id 或 None
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from . import run as _run

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
SAVE_EXT = ".json"
SLOT_DIR_NAME = "saves"


def slots_dir() -> str:
    """存档目录。跟随 core.run.DATA_DIR（打包后由入口脚本改写）。"""
    try:
        base = getattr(_run, "DATA_DIR", None) or _run.DATA_DIR
    except Exception:
        base = "data"
    return os.path.join(base, SLOT_DIR_NAME)


def _ensure_dir() -> str:
    d = slots_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _safe_id(text: str) -> str:
    """把任意字符串变成安全的文件名片段。"""
    t = re.sub(r"[^0-9A-Za-z_\-]+", "_", str(text or ""))[:40]
    return t.strip("_") or "save"


def _new_id(name: str = "") -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return "%s-%s" % (stamp, uuid.uuid4().hex[:6])


# --------------------------------------------------------------------------
# 存档信息
# --------------------------------------------------------------------------
@dataclass
class SlotInfo:
    slot_id: str
    name: str = ""
    mtime: float = 0.0
    act: int = 0
    floor: int = 0
    hp: int = 0
    max_hp: int = 0
    ascension: int = 0
    deck_size: int = 0
    relics: int = 0
    character: str = ""
    broken: bool = False
    path: str = ""

    # -- 显示用 ---------------------------------------------------------
    def when(self) -> str:
        """人类可读的时间。"""
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.mtime))
        except Exception:
            return ""

    def title(self) -> str:
        return self.name or ("第 %d 幕 · 第 %d 层" % (self.act + 1, self.floor))

    def summary(self) -> str:
        if self.broken:
            return "（文件损坏，无法读取）"
        return "第 %d 幕 %d 层 · %d/%d 耐久 · 牌组 %d 张 · 勋章 %d · 难度 %d" % (
            self.act + 1, self.floor, self.hp, self.max_hp,
            self.deck_size, self.relics, self.ascension)

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id, "name": self.name, "mtime": self.mtime,
            "act": self.act, "floor": self.floor, "hp": self.hp,
            "max_hp": self.max_hp, "ascension": self.ascension,
            "deck_size": self.deck_size, "relics": self.relics,
            "character": self.character,
        }


# --------------------------------------------------------------------------
# 读写
# --------------------------------------------------------------------------
def _slot_path(slot_id: str) -> str:
    return os.path.join(slots_dir(), "%s%s" % (_safe_id(slot_id), SAVE_EXT))


def _read_file(path: str) -> Optional[dict]:
    """读一个存档文件。兼容两种格式：
      1) 新格式：{"meta": {...}, "run": {...}}
      2) 老格式：直接就是 RunState 的 dict
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    if isinstance(d.get("run"), dict):
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        return {"meta": meta, "run": d["run"]}
    # 老格式：整份就是 run
    return {"meta": {}, "run": d}


def _build_info(path: str) -> SlotInfo:
    sid = os.path.splitext(os.path.basename(path))[0]
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        mtime = 0.0
    data = _read_file(path)
    if data is None:
        return SlotInfo(slot_id=sid, mtime=mtime, broken=True, path=path)
    run = data.get("run") or {}
    meta = data.get("meta") or {}
    deck = run.get("deck") or []
    relics = run.get("relics") or []
    return SlotInfo(
        slot_id=sid,
        name=str(meta.get("name") or ""),
        mtime=float(meta.get("mtime") or mtime),
        act=int(run.get("act", 0) or 0),
        floor=int(run.get("floor", 0) or 0),
        hp=int(run.get("hp", 0) or 0),
        max_hp=int(run.get("max_hp", 0) or 0),
        ascension=int(run.get("ascension", 0) or 0),
        deck_size=len(deck) if isinstance(deck, list) else 0,
        relics=len(relics) if isinstance(relics, list) else 0,
        character=str(run.get("character") or ""),
        path=path,
    )


def _write(path: str, run, name: str, mtime: Optional[float] = None) -> bool:
    payload = {
        "meta": {
            "name": str(name or ""),
            "mtime": float(mtime if mtime is not None else time.time()),
            "game": "steel-frontline",
            "version": 1,
        },
        "run": run.to_dict() if hasattr(run, "to_dict") else dict(run or {}),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)          # 原子替换，避免写一半崩掉
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def slots() -> List[SlotInfo]:
    """全部存档，按修改时间倒序。目录不存在时返回空列表。"""
    d = slots_dir()
    out: List[SlotInfo] = []
    try:
        for fn in os.listdir(d):
            if not fn.endswith(SAVE_EXT) or fn.endswith(".tmp"):
                continue
            out.append(_build_info(os.path.join(d, fn)))
    except Exception:
        return []
    out.sort(key=lambda s: -s.mtime)
    return out


def get(slot_id: str) -> Optional[SlotInfo]:
    p = _slot_path(slot_id)
    if not os.path.isfile(p):
        return None
    return _build_info(p)


def save_new(run, name: str = "") -> Optional[str]:
    """新建一个存档。返回 slot_id。"""
    if run is None:
        return None
    _ensure_dir()
    sid = _new_id(name)
    if not _write(_slot_path(sid), run, name):
        return None
    _point_latest(sid)
    return sid


def save_to(slot_id: str, run, name: Optional[str] = None) -> bool:
    """覆盖保存到已有存档（保留原名字与创建时间）。"""
    if run is None or not slot_id:
        return False
    p = _slot_path(slot_id)
    old = _read_file(p) if os.path.isfile(p) else None
    old_meta = (old or {}).get("meta") or {}
    use_name = name if name is not None else str(old_meta.get("name") or "")
    ok = _write(p, run, use_name)
    if ok:
        _point_latest(slot_id)
    return ok


def load(slot_id: str):
    """读存档并返回 RunState。失败返回 None。"""
    data = _read_file(_slot_path(slot_id))
    if data is None:
        return None
    try:
        r = _run.RunState.from_dict(data["run"])
        _point_latest(slot_id)
        return r
    except Exception:
        return None


def delete(slot_id: str) -> bool:
    p = _slot_path(slot_id)
    try:
        if os.path.isfile(p):
            os.remove(p)
        # 删掉的正好是"最近存档"就清掉指针
        if latest_slot() == slot_id:
            try:
                if os.path.exists(_run.SAVE_PATH):
                    os.remove(_run.SAVE_PATH)
            except Exception:
                pass
        return True
    except Exception:
        return False


def rename(slot_id: str, name: str) -> bool:
    """改名。保留存档内容与时间。"""
    p = _slot_path(slot_id)
    data = _read_file(p)
    if data is None:
        return False
    data.setdefault("meta", {})
    data["meta"]["name"] = str(name or "")
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def export_to(slot_id: str, dst_path: str) -> bool:
    """把存档导出到任意路径（用于发给别人）。"""
    p = _slot_path(slot_id)
    if not os.path.isfile(p):
        return False
    try:
        data = _read_file(p)
        if data is None:
            return False
        data.setdefault("meta", {})
        data["meta"]["exported_at"] = time.time()
        with open(dst_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def import_from(src_path: str, name: str = "") -> Optional[str]:
    """从文件导入一个存档，返回新 slot_id。

    会做基本校验：必须是能解析的存档格式，且能构造出 RunState。
    """
    data = _read_file(src_path)
    if data is None:
        return None
    # 校验 1：必须像个存档（含有 run 的关键字段），不能是随便一个 dict
    raw = data.get("run") or {}
    required = ("seed", "hp", "max_hp", "deck")
    if not isinstance(raw, dict) or not all(k in raw for k in required):
        return None
    # 校验 2：类型要对得上，避免反序列化出半残对象
    try:
        if not isinstance(raw.get("deck"), (list, tuple)):
            return None
        int(raw.get("seed"))
        int(raw.get("hp"))
        int(raw.get("max_hp"))
    except Exception:
        return None
    # 校验 3：真的能构造出 RunState
    try:
        obj = _run.RunState.from_dict(raw)
        if obj is None:
            return None
    except Exception:
        return None
    _ensure_dir()
    sid = _new_id(name)
    meta = data.get("meta") or {}
    use_name = name or str(meta.get("name") or "")
    if not use_name:
        base = os.path.splitext(os.path.basename(src_path))[0]
        use_name = base[:24]
    if not _write(_slot_path(sid), data["run"],
                  use_name, mtime=time.time()):
        return None
    return sid


# --------------------------------------------------------------------------
# 「最近存档」指针：让老的「继续上次战役」继续可用
# --------------------------------------------------------------------------
def _point_latest(slot_id: str) -> None:
    """把某个存档的内容同步到 data/save.json（老路径）。"""
    try:
        data = _read_file(_slot_path(slot_id))
        if data is None:
            return
        with open(_run.SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(data["run"], f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def latest_slot() -> Optional[str]:
    """最近一次使用的存档 id。"""
    try:
        with open(_run.SAVE_PATH, "r", encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        return None
    # 用 seed + 楼层 + 血量做一次粗匹配，找到对应槽位
    for s in slots():
        d = _read_file(s.path)
        if d is None:
            continue
        r = d.get("run") or {}
        if (r.get("seed") == cur.get("seed")
                and r.get("floor") == cur.get("floor")
                and r.get("hp") == cur.get("hp")):
            return s.slot_id
    return None


def count() -> int:
    return len(slots())


def migrate_legacy() -> Optional[str]:
    """把老的单文件存档收进存档槽（首次运行时调用一次）。

    返回新 slot_id（没有老存档则返回 None）。
    """
    try:
        if not os.path.isfile(_run.SAVE_PATH):
            return None
        if slots():                     # 已经有槽位了，不重复迁移
            return None
        data = _read_file(_run.SAVE_PATH)
        if data is None:
            return None
        _ensure_dir()
        sid = _new_id("legacy")
        r = data["run"]
        ok = _write(_slot_path(sid), r,
                    str((data.get("meta") or {}).get("name") or "旧存档"))
        return sid if ok else None
    except Exception:
        return None


__all__ = [
    "SlotInfo", "slots_dir", "slots", "get", "save_new", "save_to", "load",
    "delete", "rename", "export_to", "import_from", "latest_slot",
    "count", "migrate_legacy",
]
