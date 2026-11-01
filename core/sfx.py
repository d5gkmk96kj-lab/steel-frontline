#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音效播放层。

* 用 ``QSoundEffect``（低延迟，专门为音效设计），没有就静默降级。
* 所有音效由 :mod:`core.sfx_gen` 在首次运行时**程序化生成**到
  ``<数据目录>/sfx/``，不依赖任何外部素材（零版权问题）。
* 任何一步失败都不抛异常 —— 音效是锦上添花，绝不能因为它让游戏崩。
"""

from __future__ import annotations

import os
import threading
from typing import Dict, Optional

_LOCK = threading.Lock()
_EFFECTS: Dict[str, object] = {}
_PATHS: Dict[str, str] = {}
_INITED = False
_ENABLED = True
_VOLUME = 0.55


def _data_dir() -> str:
    try:
        from core import run as _run
        return getattr(_run, "DATA_DIR", None) or "data"
    except Exception:
        return "data"


def _init() -> None:
    """首次调用时生成并加载音效。之后是空操作。"""
    global _INITED
    if _INITED:
        return
    with _LOCK:
        if _INITED:
            return
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is None:
                # 还没有 QApplication（应用启动早期 / 纯测试环境）。
                # 这里**不能**把 _INITED 置为 True —— 否则以后永远不再尝试，
                # 音效就永久哑了。等有 QApplication 时再初始化。
                return
        except Exception:
            _INITED = True          # 没装 PyQt6：永久放弃，别反复 import
            return
        try:
            from PyQt6.QtMultimedia import QSoundEffect
            from PyQt6.QtCore import QUrl
        except Exception:
            _INITED = True          # 没装 QtMultimedia：永久放弃
            return
        _INITED = True              # 到这里才算初始化完成
        try:
            from core import sfx_gen as _gen
            base = os.path.join(_data_dir(), "sfx")
            paths = _gen.generate_all(base)
        except Exception:
            return
        for name, path in paths.items():
            try:
                eff = QSoundEffect()
                eff.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
                eff.setVolume(_VOLUME)
                _EFFECTS[name] = eff
                _PATHS[name] = path
            except Exception:
                continue


def set_enabled(on: bool) -> None:
    """总开关（设置里的「启用音效」）。"""
    global _ENABLED
    _ENABLED = bool(on)


def is_enabled() -> bool:
    return bool(_ENABLED)


def set_volume(v: float) -> None:
    """0.0 – 1.0。"""
    global _VOLUME
    try:
        _VOLUME = max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return
    for eff in list(_EFFECTS.values()):
        try:
            eff.setVolume(_VOLUME)
        except Exception:
            pass


def play(name: str) -> bool:
    """播一个音效。没加载成功就静默返回 False。"""
    if not _ENABLED:
        return False
    if not _INITED:
        _init()
    eff = _EFFECTS.get(str(name))
    if eff is None:
        return False
    try:
        # 连续触发时先停再放，避免叠成噪音
        if eff.isPlaying():
            eff.stop()
        eff.setVolume(_VOLUME)
        eff.play()
        return True
    except Exception:
        return False


def names() -> list:
    """可用音效名（调试用）。"""
    if not _INITED:
        _init()
    return sorted(_EFFECTS.keys())


def shutdown() -> None:
    """释放音效对象（退出时调）。"""
    global _INITED
    with _LOCK:
        for eff in list(_EFFECTS.values()):
            try:
                eff.stop()
                eff.deleteLater()
            except Exception:
                pass
        _EFFECTS.clear()
        _INITED = False
