#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""程序化生成音效（不依赖任何外部素材，零版权问题）。

为什么合成而不是找素材
--------------------
* 项目要能公开分发，音频素材的版权是最容易踩雷的地方；
* 合成出来的小 WAV 只有几 KB，打包体积几乎不增加；
* 程序化生成可以保证**同一份代码在任何机器上生成同样的音效**。

音效设计思路
------------
游戏是二战装甲题材，所以全部走「金属 / 爆响 / 机械」的质感：

* ``card``    出牌：短促的纸牌摩擦 + 金属轻响
* ``hit``     命中：低频闷响 + 噪声冲击
* ``block``   格挡：金属敲击（高频衰减振铃）
* ``crit``    重击：更猛的低频 + 更长的尾音
* ``kill``    击毁：爆响 + 碎片噪声
* ``victory`` 胜利：上行三音（弹壳金）
* ``defeat``  失败：下行三音（低沉）
* ``click``   UI 点击：极短的干脆声
* ``potion``  药水：气泡上升
* ``turn``    回合切换：轻微军事哨音
"""

from __future__ import annotations

import math
import os
import struct
import wave
from typing import List, Optional, Tuple

SAMPLE_RATE = 22050


# --------------------------------------------------------------------------
# 基础合成工具
# --------------------------------------------------------------------------
def _silence(n: int) -> List[float]:
    return [0.0] * int(n)


def _env(t: float, dur: float, attack: float = 0.002,
         decay: float = 1.0) -> float:
    """简单包络：线性起音 + 指数衰减。"""
    if t < attack:
        return t / attack if attack > 0 else 1.0
    x = (t - attack) / max(1e-6, dur - attack)
    return math.exp(-decay * 5.0 * x)


def _sine(freq: float, t: float) -> float:
    return math.sin(2.0 * math.pi * freq * t)


def _noise(seed: int = 1) -> float:
    """确定性伪噪声（不用 random，保证多次生成结果一致）。"""
    x = math.sin(seed * 12.9898 + 78.233) * 43758.5453
    return (x - math.floor(x)) * 2.0 - 1.0


def _mix(parts: List[List[float]], gains: Optional[List[float]] = None) -> List[float]:
    """把若干路等长/不等长音频叠加。"""
    n = max((len(p) for p in parts), default=0)
    out = [0.0] * n
    for i, p in enumerate(parts):
        g = gains[i] if gains and i < len(gains) else 1.0
        for j, v in enumerate(p):
            out[j] += v * g
    return out


def _scale(buf: List[float], peak: float = 0.72) -> List[float]:
    """归一化到指定峰值，避免削波。"""
    m = max((abs(v) for v in buf), default=0.0)
    if m <= 1e-9:
        return buf
    k = peak / m
    return [v * k for v in buf]


def _fade_out(buf: List[float], ms: int = 12) -> List[float]:
    n = min(len(buf), int(SAMPLE_RATE * ms / 1000))
    for i in range(n):
        buf[len(buf) - n + i] *= (n - i) / n
    return buf


# --------------------------------------------------------------------------
# 各个音效
# --------------------------------------------------------------------------
def _sfx_card() -> List[float]:
    """出牌：纸牌摩擦 + 金属轻响。"""
    dur = 0.13
    n = int(SAMPLE_RATE * dur)
    body = []
    for i in range(n):
        t = i / SAMPLE_RATE
        e = _env(t, dur, attack=0.001, decay=2.6)
        # 摩擦：高通感的噪声
        nz = _noise(i * 3 + 1) * 0.55 + _noise(i * 7 + 5) * 0.25
        # 金属：两个不和谐高频
        ring = _sine(1750, t) * 0.30 + _sine(2630, t) * 0.18
        body.append((nz + ring) * e)
    return _fade_out(_scale(body, 0.5), 8)


def _sfx_hit() -> List[float]:
    """命中：低频闷响 + 噪声冲击。"""
    dur = 0.20
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        e = _env(t, dur, attack=0.001, decay=3.4)
        # 低频下扫：120Hz -> 55Hz
        f = 120.0 - 65.0 * (t / dur)
        low = _sine(f, t) * 0.85
        nz = _noise(i * 5 + 11) * 0.42
        out.append((low + nz) * e)
    return _fade_out(_scale(out, 0.62), 10)


def _sfx_block() -> List[float]:
    """格挡：金属敲击（高频振铃）。"""
    dur = 0.24
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        e = _env(t, dur, attack=0.001, decay=2.2)
        ring = (_sine(1180, t) * 0.34 + _sine(1810, t) * 0.26
                + _sine(2470, t) * 0.16)
        nz = _noise(i * 13 + 3) * 0.14
        out.append((ring + nz) * e)
    return _fade_out(_scale(out, 0.5), 12)


def _sfx_crit() -> List[float]:
    """重击：更猛的低频 + 更长尾音。"""
    dur = 0.34
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        e = _env(t, dur, attack=0.001, decay=2.8)
        f = 165.0 - 120.0 * (t / dur)
        low = _sine(f, t) * 1.0
        nz = _noise(i * 9 + 21) * 0.60
        # 叠加一层余响
        tail = _sine(88.0, t) * 0.30 * math.exp(-4.5 * t)
        out.append((low + nz) * e + tail)
    return _fade_out(_scale(out, 0.78), 16)


def _sfx_kill() -> List[float]:
    """击毁：爆响 + 碎片噪声。"""
    dur = 0.46
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        e = _env(t, dur, attack=0.001, decay=2.0)
        f = 95.0 - 70.0 * (t / dur)
        low = _sine(f, t) * 0.9
        nz = _noise(i * 17 + 7) * 0.75 * math.exp(-6.0 * t)
        out.append((low + nz) * e)
    return _fade_out(_scale(out, 0.80), 20)


def _tone_seq(freqs: List[Tuple[float, float]], wave_kind: str = "tri") -> List[float]:
    """一串音符（频率, 时长秒）。"""
    out: List[float] = []
    for idx, (f, d) in enumerate(freqs):
        n = int(SAMPLE_RATE * d)
        for i in range(n):
            t = i / SAMPLE_RATE
            phase = 2.0 * math.pi * f * t
            if wave_kind == "tri":
                v = (2.0 / math.pi) * math.asin(math.sin(phase))
            elif wave_kind == "sq":
                v = 1.0 if math.sin(phase) >= 0 else -1.0
            else:
                v = math.sin(phase)
            e = _env(t, d, attack=0.004, decay=1.8)
            out.append(v * e * 0.55)
    return out


def _sfx_victory() -> List[float]:
    """胜利：上行三音。"""
    bufs = _tone_seq([(392.0, 0.13), (523.25, 0.13), (659.25, 0.30)])
    return _fade_out(_scale(bufs, 0.55), 40)


def _sfx_defeat() -> List[float]:
    """失败：下行三音。"""
    bufs = _tone_seq([(311.1, 0.16), (261.6, 0.16), (196.0, 0.42)], "sine")
    return _fade_out(_scale(bufs, 0.5), 50)


def _sfx_click() -> List[float]:
    """UI 点击：极短干脆声。"""
    dur = 0.055
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        e = _env(t, dur, attack=0.0005, decay=6.0)
        v = _sine(880, t) * 0.5 + _noise(i * 3 + 2) * 0.35
        out.append(v * e)
    return _fade_out(_scale(out, 0.34), 4)


def _sfx_potion() -> List[float]:
    """药水：气泡上升。"""
    dur = 0.30
    n = int(SAMPLE_RATE * dur)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # 频率随气泡上升
        f = 420.0 + 520.0 * (t / dur)
        e = _env(t, dur, attack=0.004, decay=2.4)
        wob = _sine(f, t) * (0.6 + 0.4 * _sine(11.0, t))
        out.append(wob * e * 0.6)
    return _fade_out(_scale(out, 0.45), 12)


def _sfx_turn() -> List[float]:
    """回合切换：轻微军事哨音。"""
    return _fade_out(_scale(
        _tone_seq([(660.0, 0.06), (880.0, 0.09)], "sine"), 0.38), 10)


#: 名称 -> 生成函数
GENERATORS = {
    "card": _sfx_card,
    "hit": _sfx_hit,
    "block": _sfx_block,
    "crit": _sfx_crit,
    "kill": _sfx_kill,
    "victory": _sfx_victory,
    "defeat": _sfx_defeat,
    "click": _sfx_click,
    "potion": _sfx_potion,
    "turn": _sfx_turn,
}


def write_wav(path: str, samples: List[float]) -> bool:
    """把浮点样本写成 16bit 单声道 WAV。"""
    try:
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            frames = bytearray()
            for v in samples:
                iv = int(max(-1.0, min(1.0, float(v))) * 32767)
                frames += struct.pack("<h", iv)
            w.writeframes(bytes(frames))
        return True
    except Exception:
        return False


def generate_all(out_dir: str, names: Optional[List[str]] = None) -> dict:
    """生成全部音效到 ``out_dir``，返回 {name: path}。"""
    got: dict = {}
    for name in (names or list(GENERATORS)):
        fn = GENERATORS.get(name)
        if fn is None:
            continue
        path = os.path.join(out_dir, "%s.wav" % name)
        if not os.path.isfile(path):
            if not write_wav(path, fn()):
                continue
        got[name] = path
    return got


def ensure_sfx_files(data_dir: str) -> dict:
    """确保音效文件存在（首次运行时生成）。"""
    return generate_all(os.path.join(data_dir, "sfx"))
