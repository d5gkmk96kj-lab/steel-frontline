#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码完整性校验 / 反篡改 / 反调试。

用途
-----
联机对局时确认双方跑的是**同一份未被改动的代码**。

三层设计
--------
1. **构建哈希（build hash）**
   把核心模块的源码按固定顺序拼起来算 SHA-256。
   这是「你是谁」的指纹 —— 改一个字节就变。

2. **运行时自检（tamper check）**
   检测调试器、注入、猴子补丁等常见的「边跑边改」手段。

3. **设备指纹（device id）**
   同一台机器的稳定标识，用于把违规记录关联起来。
   注意：**不采集任何隐私信息**，只用系统层面的公开标识做哈希。

安全边界（重要）
----------------
这些手段挡不住**真正有心的人** —— Python 反编译门槛很低。
目标不是「绝对防住」，而是：
  * 让**随手改代码**的人立刻连不上
  * 让**改代码的人**留下可追溯的记录
  * 让**玩家举报**有据可查

不做什么：不联网、不上传、不记录玩家隐私。
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------
# 1. 构建哈希
# --------------------------------------------------------------------------
#: 参与哈希的模块。顺序固定 —— 顺序变了哈希也会变（这是有意的）。
HASHED_MODULES = (
    "core/engine.py",
    "core/cards.py",
    "core/versus.py",
    "core/netplay.py",
    "core/session.py",
    "core/run.py",
    "core/deckbuild.py",
    "core/integrity.py",
)

#: 额外参与哈希的文件（非源码）
HASHED_FILES = (
    "version.json",
)


def _root() -> str:
    """项目根目录（打包后在 _MEIPASS 里）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def compute_build_hash() -> str:
    """算出当前代码的构建哈希（64 位十六进制）。

    打包后源码被塞进 PYZ，读不到 .py —— 这时退回用**已加载模块的
    code object** 算哈希，效果等价（代码变了字节码就变）。
    """
    h = hashlib.sha256()
    h.update(b"steel-frontline-v1|")

    got_any = False
    root = _root()
    for rel in HASHED_MODULES:
        data = _read_bytes(os.path.join(root, rel))
        if data is not None:
            h.update(rel.encode())
            h.update(b"\x00")
            h.update(data)
            h.update(b"\x1e")
            got_any = True

    for rel in HASHED_FILES:
        data = _read_bytes(os.path.join(root, rel))
        if data is not None:
            h.update(rel.encode())
            h.update(b"\x00")
            h.update(data)
            h.update(b"\x1e")
            got_any = True

    if not got_any:
        # 打包环境：用字节码摘要
        for name in ("core.engine", "core.cards", "core.versus",
                     "core.netplay", "core.session", "core.integrity"):
            mod = sys.modules.get(name)
            if mod is None:
                continue
            try:
                co = getattr(mod, "__loader__", None)
                spec = getattr(mod, "__spec__", None)
                origin = getattr(spec, "origin", "") or ""
                h.update(name.encode())
                h.update(origin.encode())
                # 模块里所有函数的字节码摘要
                for attr in sorted(dir(mod)):
                    obj = getattr(mod, attr, None)
                    cb = getattr(obj, "__code__", None)
                    if cb is not None:
                        h.update(cb.co_code)
                        h.update(repr(cb.co_consts).encode("utf-8", "replace"))
                h.update(b"\x1e")
                got_any = True
            except Exception:
                continue

    if not got_any:
        return ""
    return h.hexdigest()


#: 进程内缓存（哈希只算一次）
_CACHE: Dict[str, str] = {}


def build_hash(refresh: bool = False) -> str:
    if refresh or "h" not in _CACHE:
        _CACHE["h"] = compute_build_hash()
    return _CACHE["h"]


def short_hash() -> str:
    """前 12 位，给控制台显示用。"""
    h = build_hash()
    return h[:12] if h else "--------"


def verify_against(expected: str) -> bool:
    """和对方给的哈希比对（常数时间，防时序侧信道）。"""
    mine = build_hash()
    if not mine or not expected:
        return False
    try:
        import hmac
        return hmac.compare_digest(mine, str(expected))
    except Exception:
        return mine == str(expected)


# --------------------------------------------------------------------------
# 2. 运行时自检
# --------------------------------------------------------------------------
#: 被保护的关键函数。这些一旦被替换（猴子补丁）就判定为篡改。
# 写成 "模块.类.方法" 的完整路径（_resolve 按这个格式解析）。
# 早先写成 (模块, 属性) 的二元组，_resolve 收到 tuple 直接抛
# AttributeError —— 被外层 except 吞掉，导致篡改检测**静默失效**。
GUARDED_CALLABLES = (
    "core.engine.BattleState.deal_damage",
    "core.engine.CardContext.deal_damage",
    "core.versus.VersusBattle.deal_damage",
    "core.versus.VersusBattle.play_card",
    "core.session.sign",
    "core.session.verify",
    "core.integrity.build_hash",
)

#: 可疑的模块名（常见的内存修改/注入工具）
SUSPICIOUS_MODULES = (
    "pydevd",            # PyCharm 调试器
    "pdb",               # 标准调试器
    "frida",             # 注入框架
    "cheatengine",
    "pymem",
    "memory_profiler",
)


def _resolve(dotted: str):
    """把 "core.versus.VersusBattle.deal_damage" 解析成实际的函数对象。

    注意：不能简单用 partition(".") 拆 —— 那会把 "core.versus..."
    拆成 mod="core"、attr="versus.VersusBattle..."，而 core 包里
    并没有 versus 这个属性（真踩过，导致篡改检测整个失效）。

    正确做法：从最长的模块前缀开始试，剩下的当属性路径走。
    """
    parts = dotted.split(".")
    # 从长到短试模块名
    for i in range(len(parts) - 1, 0, -1):
        mod_name = ".".join(parts[:i])
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        obj = mod
        ok = True
        for part in parts[i:]:
            obj = getattr(obj, part, None)
            if obj is None:
                ok = False
                break
        if ok:
            return obj
    return None


def check_runtime() -> List[str]:
    """运行时自检。返回「问题列表」（空 = 干净）。"""
    problems: List[str] = []

    # a) 调试器 / 注入工具
    for name in SUSPICIOUS_MODULES:
        if name in sys.modules:
            problems.append("debugger:%s" % name)

    try:
        if sys.gettrace() is not None:
            problems.append("trace-hook")
    except Exception:
        pass

    # b) 关键函数被替换
    try:
        import inspect
        for dotted in GUARDED_CALLABLES:
            fn = _resolve(dotted)
            if fn is None:
                continue
            try:
                src_file = inspect.getsourcefile(fn) or ""
            except Exception:
                continue
            # 关键函数必须来自 core/ 下的文件
            if src_file and "core" not in src_file.replace("\\", "/"):
                problems.append("patched:%s" % dotted)
        # 关键函数是否变成了「非 Python」对象（ctypes 替换）
        for dotted in GUARDED_CALLABLES:
            fn = _resolve(dotted)
            if fn is not None and not callable(fn):
                problems.append("not-callable:%s" % dotted)
    except Exception as exc:
        # 不能静默吞：自检本身出错也要暴露出来（否则等于没有保护）
        problems.append("check-failed:%r" % (exc,))

    # c) 环境变量注入（常见于调试/自动化）
    for var in ("PYTHONINSPECT", "PYTHONBREAKPOINT", "PYTHONSTARTUP"):
        v = os.environ.get(var)
        if v and var == "PYTHONBREAKPOINT" and v.strip() in ("0", ""):
            continue
        if v:
            problems.append("env:%s" % var)

    return problems


# --------------------------------------------------------------------------
# 3. 设备指纹
# --------------------------------------------------------------------------
def device_id() -> str:
    """稳定的设备标识（16 位十六进制）。

    **只**用系统层面的公开标识做哈希：
      * 主机名
      * 平台 / 版本
      * 网卡 MAC（本地哈希，不外传）
    不含用户名、路径等隐私信息。不可逆。
    """
    parts = []
    try:
        import platform
        parts.append(platform.node() or "")
        parts.append(platform.system() or "")
        parts.append(platform.machine() or "")
    except Exception:
        pass
    try:
        import uuid
        parts.append(str(uuid.getnode()))
    except Exception:
        pass
    parts.append(os.environ.get("SF_DEVICE_SALT", "sf-default-salt"))
    h = hashlib.sha256("|".join(parts).encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def short_device() -> str:
    d = device_id()
    return "%s-%s" % (d[:8], d[8:12]) if len(d) >= 12 else d


# --------------------------------------------------------------------------
# 4. 汇总
# --------------------------------------------------------------------------
def self_check() -> Tuple[bool, Dict]:
    """完整自检。返回 (是否可信, 报告)。"""
    rep = {
        "build_hash": build_hash(),
        "short_hash": short_hash(),
        "device_id": device_id(),
        "short_device": short_device(),
        "problems": [],
        "frozen": bool(getattr(sys, "frozen", False)),
        "platform": sys.platform,
    }
    try:
        rep["problems"] = check_runtime()
    except Exception as exc:
        rep["problems"] = ["check-error:%r" % (exc,)]
    rep["clean"] = not rep["problems"]
    return rep["clean"], rep


# --------------------------------------------------------------------------
# 5. 违规记录（给控制台 / 管理台读）
# --------------------------------------------------------------------------
#: 落盘位置（和游戏数据放一起）
def _violation_path() -> str:
    try:
        from core import run as _run
        base = os.path.dirname(getattr(_run, "SAVE_PATH", "") or "")
        if base:
            return os.path.join(base, "integrity_log.jsonl")
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), ".steel_frontline",
                        "integrity_log.jsonl")


#: 内存缓冲（进程内可随时读，不必等落盘）
_MEM: List[Dict] = []
_MEM_LOCK = None


def _lock():
    global _MEM_LOCK
    if _MEM_LOCK is None:
        import threading
        _MEM_LOCK = threading.Lock()
    return _MEM_LOCK


def record_violation(entry: Dict) -> None:
    """记一条违规。落盘用 JSONL（追加写，损坏也不影响已有记录）。"""
    try:
        with _lock():
            _MEM.append(dict(entry))
            if len(_MEM) > 200:
                del _MEM[:-200]
    except Exception:
        pass
    try:
        path = _violation_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        import json as _j
        with open(path, "a", encoding="utf-8") as f:
            f.write(_j.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def violations(limit: int = 100) -> List[Dict]:
    """读最近的违规记录（内存优先，读不到再读文件）。"""
    out: List[Dict] = []
    try:
        with _lock():
            out = list(_MEM)
    except Exception:
        out = []
    if len(out) < limit:
        try:
            import json as _j
            path = _violation_path()
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            out.append(_j.loads(line))
                        except Exception:
                            continue
        except Exception:
            pass
    # 去重（内存和文件可能有重复）+ 按时间倒序
    seen = set()
    uniq = []
    for e in out:
        key = (e.get("ts"), e.get("peer_hash"), e.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    uniq.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return uniq[:limit]


def clear_violations() -> None:
    """清空违规记录（控制台用）。"""
    try:
        with _lock():
            _MEM.clear()
    except Exception:
        pass
    try:
        path = _violation_path()
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
