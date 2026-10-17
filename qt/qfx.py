#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 —— 特效与过渡动画。

这个模块只做两件事，都基于 QPainter + QPropertyAnimation，不阻塞主线程：

1. **打击特效**（:class:`SparkBurst` / :class:`ImpactRing` / :class:`SlashArc`）
   卡牌命中敌人时的火花、冲击环、斩击弧。

2. **界面过渡**（:func:`fade_switch`）
   主菜单 → 地图 → 战斗 之间切换时的淡入淡出 + 轻微位移，
   而不是硬切。

设计约束
--------
* **绝不阻塞**：全部靠 QTimer/QPropertyAnimation 驱动，主线程立即返回。
* **可失败**：特效只是锦上添花，任何异常都必须静默吞掉，
  宁可没有特效也不能让游戏崩。
* **能关**：设置里可以关掉特效（低配机器 / 不喜欢花哨）。
* **离屏安全**：自检和无头遍历时不会因为画特效而卡住。
"""

from __future__ import annotations

import math
import random
from typing import List, Optional

from PyQt6.QtCore import (
    QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer,
    pyqtProperty,
)
from PyQt6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                       QRadialGradient)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

from . import qtheme as T

# --------------------------------------------------------------------------
# 全局开关（设置里可关）
# --------------------------------------------------------------------------
_FX_ENABLED = True


def set_enabled(on: bool) -> None:
    global _FX_ENABLED
    _FX_ENABLED = bool(on)


def enabled() -> bool:
    return _FX_ENABLED


# --------------------------------------------------------------------------
# 打击特效
# --------------------------------------------------------------------------
class SparkBurst(QWidget):
    """火花爆发：粒子从中心向外飞散，逐渐变淡。

    用于卡牌命中敌人的瞬间。粒子是预先生成的随机速度/角度，
    重绘时按 ``progress`` 推进，所以只要跑一个 0→1 的动画即可。
    """

    def __init__(self, parent: QWidget, x: float, y: float,
                 color: QColor = None, count: int = 18,
                 spread: float = 46.0, life_ms: int = 520):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.color = QColor(color) if color else QColor(T.GOLD)
        self.count = max(4, int(count))
        self.spread = float(spread)
        self._p = 0.0
        # 每个粒子：角度、初速、长度、粗细
        rnd = random.Random()
        self._parts = []
        for _ in range(self.count):
            ang = rnd.uniform(0, math.tau)
            spd = rnd.uniform(0.55, 1.35)
            self._parts.append((ang, spd,
                                rnd.uniform(3.0, 9.0),
                                rnd.uniform(1.0, 2.6),
                                rnd.uniform(-0.6, 0.6)))
        pad = int(self.spread * 1.9) + 20
        self.setGeometry(int(x) - pad, int(y) - pad, pad * 2, pad * 2)
        self._cx = pad
        self._cy = pad
        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(int(life_ms))
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self.deleteLater)
        self.show()
        self.raise_()

    def _get_p(self) -> float:
        return self._p

    def _set_p(self, v: float) -> None:
        self._p = float(v)
        self.update()

    progress = pyqtProperty(float, fget=_get_p, fset=_set_p)

    def start(self) -> None:
        self._anim.start()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = self._p
        if p >= 1.0:
            return
        pt = QPainter(self)
        T.aa(pt)
        fade = (1.0 - p) ** 1.6            # 越到后面越淡
        dist = self.spread * (p ** 0.6)    # 前快后慢
        for ang, spd, length, width, curve in self._parts:
            r = dist * spd
            a = ang + curve * p * 1.1      # 轻微弯曲
            x1 = self._cx + math.cos(a) * r
            y1 = self._cy + math.sin(a) * r * 0.85
            x2 = self._cx + math.cos(a) * (r + length)
            y2 = self._cy + math.sin(a) * (r + length) * 0.85
            col = QColor(self.color)
            col.setAlphaF(max(0.0, min(1.0, fade)))
            pen = QPen(col, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pt.setPen(pen)
            pt.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        # 中心一亮
        if p < 0.55:
            g = QRadialGradient(QPointF(self._cx, self._cy),
                                self.spread * 0.55)
            c0 = QColor(255, 255, 255, int(210 * (1 - p / 0.55)))
            c1 = QColor(self.color)
            c1.setAlpha(0)
            g.setColorAt(0.0, c0)
            g.setColorAt(1.0, c1)
            pt.setBrush(g)
            pt.setPen(Qt.PenStyle.NoPen)
            rad = self.spread * 0.5 * (1 - p / 0.55)
            pt.drawEllipse(QPointF(self._cx, self._cy), rad, rad * 0.85)


class ImpactRing(QWidget):
    """冲击环：一圈快速扩散的圆环，命中敌人时叠在火花上。"""

    def __init__(self, parent: QWidget, x: float, y: float,
                 color: QColor = None, max_r: float = 42.0,
                 life_ms: int = 380, width: float = 3.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.color = QColor(color) if color else QColor(T.GOLD)
        self.max_r = float(max_r)
        self.width = float(width)
        self._p = 0.0
        pad = int(self.max_r) + 12
        self.setGeometry(int(x) - pad, int(y) - pad, pad * 2, pad * 2)
        self._cx = pad
        self._cy = pad
        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(int(life_ms))
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        self._anim.finished.connect(self.deleteLater)
        self.show()
        self.raise_()

    def _get_p(self) -> float:
        return self._p

    def _set_p(self, v: float) -> None:
        self._p = float(v)
        self.update()

    progress = pyqtProperty(float, fget=_get_p, fset=_set_p)

    def start(self) -> None:
        self._anim.start()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = self._p
        if p >= 1.0:
            return
        pt = QPainter(self)
        T.aa(pt)
        r = self.max_r * p
        alpha = int(190 * (1.0 - p) ** 1.4)
        if alpha <= 2:
            return
        col = QColor(self.color)
        col.setAlpha(alpha)
        pen = QPen(col, self.width * (1.0 - p * 0.55))
        pt.setPen(pen)
        pt.setBrush(Qt.BrushStyle.NoBrush)
        pt.drawEllipse(QPointF(self._cx, self._cy), r, r * 0.82)


class SlashArc(QWidget):
    """斩击弧：一道快速划过的弧线，用于高伤害攻击。"""

    def __init__(self, parent: QWidget, x: float, y: float,
                 color: QColor = None, radius: float = 46.0,
                 life_ms: int = 300, angle0: float = -2.5,
                 sweep: float = 2.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.color = QColor(color) if color else QColor(255, 240, 200)
        self.radius = float(radius)
        self.angle0 = float(angle0)
        self.sweep = float(sweep)
        self._p = 0.0
        pad = int(self.radius) + 14
        self.setGeometry(int(x) - pad, int(y) - pad, pad * 2, pad * 2)
        self._cx = pad
        self._cy = pad
        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(int(life_ms))
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim.finished.connect(self.deleteLater)
        self.show()
        self.raise_()

    def _get_p(self) -> float:
        return self._p

    def _set_p(self, v: float) -> None:
        self._p = float(v)
        self.update()

    progress = pyqtProperty(float, fget=_get_p, fset=_set_p)

    def start(self) -> None:
        self._anim.start()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = self._p
        if p >= 1.0:
            return
        pt = QPainter(self)
        T.aa(pt)
        alpha = int(235 * (1.0 - p) ** 1.2)
        if alpha <= 2:
            return
        # 一条逐渐变长的弧
        span = self.sweep * min(1.0, p * 1.8)
        a0 = self.angle0
        rect = QRectF(self._cx - self.radius, self._cy - self.radius * 0.9,
                      self.radius * 2, self.radius * 1.8)
        col = QColor(self.color)
        col.setAlpha(alpha)
        pen = QPen(col, max(1.6, 5.0 * (1.0 - p)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pt.setPen(pen)
        pt.setBrush(Qt.BrushStyle.NoBrush)
        # Qt 的角度单位是 1/16 度
        pt.drawArc(rect, int(a0 * 16), int(span * 16))


# =====================================================================
# 攻击特效：子弹 / 火焰 / 冲击 / 毒气
# =====================================================================

class _BulletTrail(QWidget):
    """一发子弹：从起点飞向终点，带拖尾和枪口闪光。"""

    def __init__(self, parent, sx, sy, ex, ey, color, life_ms=190):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self._sx, self._sy = float(sx), float(sy)
        self._ex, self._ey = float(ex), float(ey)
        self._col = QColor(color)
        self._life = max(60, int(life_ms))
        self._t = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self):
        self._t += 16
        if self._t >= self._life:
            self._timer.stop()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        try:
            k = min(1.0, self._t / float(self._life))
            # 缓出：前半段快、后半段慢
            ease = 1.0 - (1.0 - k) ** 2.4
            x = self._sx + (self._ex - self._sx) * ease
            y = self._sy + (self._ey - self._sy) * ease
            p = QPainter(self)
            T.aa(p)
            # 拖尾
            for i in range(4):
                back = (i + 1) * 0.055
                kk = max(0.0, ease - back)
                tx = self._sx + (self._ex - self._sx) * kk
                ty = self._sy + (self._ey - self._sy) * kk
                alpha = int(150 * (1.0 - i / 4.5) * (1.0 - k * 0.5))
                p.setPen(QPen(T.a(T.f(self._col, 1.35), max(0, alpha)),
                              max(1.0, 3.2 - i * 0.7)))
                p.drawLine(QPointF(tx, ty), QPointF(x, y))
            # 弹头
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(T.a(T.qc("#FFF3C8"), 240)))
            p.drawEllipse(QPointF(x, y), 2.6, 2.6)
            # 枪口闪光（只在最开始）
            if k < 0.25:
                a2 = int(200 * (1.0 - k / 0.25))
                p.setBrush(QBrush(T.a(T.qc("#FFE9A8"), a2)))
                p.drawEllipse(QPointF(self._sx, self._sy),
                              5.0 + 7.0 * (1 - k / 0.25), 5.0 + 7.0 * (1 - k / 0.25))
        except Exception:
            pass


class _FireBurst(QWidget):
    """火焰爆开：几团火苗向外扩散 + 余烬上升。"""

    def __init__(self, parent, x, y, life_ms=520, power=1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self._x, self._y = float(x), float(y)
        self._life = max(120, int(life_ms))
        self._t = 0
        self._power = max(0.5, min(2.0, float(power)))
        import random as _r
        rng = _r.Random(int(x * 7 + y * 13))
        self._flames = []
        for i in range(int(7 + 5 * self._power)):
            self._flames.append([
                rng.uniform(-0.45, 0.45),      # dx 方向
                rng.uniform(-0.30, 0.30),      # dy
                rng.uniform(0.55, 1.5),        # 速度
                rng.uniform(0.6, 1.35),        # 大小
                rng.uniform(0.0, 0.35),        # 延迟
            ])
        self._embers = [[rng.uniform(-1, 1), rng.uniform(-1, 1),
                         rng.uniform(0.4, 1.0)] for _ in range(14)]
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self):
        self._t += 16
        if self._t >= self._life:
            self._timer.stop()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        try:
            k = min(1.0, self._t / float(self._life))
            p = QPainter(self)
            T.aa(p)
            R = 34.0 * self._power
            # 中心光晕
            if k < 0.4:
                a0 = int(120 * (1 - k / 0.4))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(T.a(T.qc("#FFB24A"), a0)))
                p.drawEllipse(QPointF(self._x, self._y),
                              R * (0.5 + k * 1.6), R * (0.5 + k * 1.6))
            # 火苗
            for (dx, dy, spd, sz, delay) in self._flames:
                kk = (k - delay) / max(0.05, 1.0 - delay)
                if kk <= 0 or kk >= 1:
                    continue
                ex = self._x + dx * R * 2.4 * kk
                ey = self._y + dy * R * 2.0 * kk - R * 0.9 * kk * kk
                rr = R * sz * (0.30 + 0.55 * kk) * (1.0 - kk * 0.35)
                alpha = int(210 * (1.0 - kk))
                # 外焰
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(T.a(T.qc("#E8622A"), alpha // 2)))
                p.drawEllipse(QPointF(ex, ey), rr, rr * 1.25)
                # 内焰
                p.setBrush(QBrush(T.a(T.qc("#FFD166"), int(alpha * 0.85))))
                p.drawEllipse(QPointF(ex, ey), rr * 0.55, rr * 0.72)
            # 余烬上升
            for (ex0, ey0, sz) in self._embers:
                ex = self._x + ex0 * R * 1.8 * (0.4 + k)
                ey = self._y + ey0 * R * 1.2 - R * 2.0 * k
                a1 = int(200 * (1.0 - k))
                if a1 <= 0:
                    continue
                p.setBrush(QBrush(T.a(T.qc("#FFC85C"), a1)))
                p.drawEllipse(QPointF(ex, ey), 1.5 * sz, 1.5 * sz)
        except Exception:
            pass


class _ImpactShock(QWidget):
    """冲击波：白色快闪 + 扩散环 + 碎屑。"""

    def __init__(self, parent, x, y, color, life_ms=340, power=1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self._x, self._y = float(x), float(y)
        self._col = QColor(color)
        self._life = max(100, int(life_ms))
        self._power = max(0.5, min(2.0, float(power)))
        self._t = 0
        import random as _r
        rng = _r.Random(int(x * 3 + y * 17))
        self._debris = [[rng.uniform(0, 6.283), rng.uniform(0.5, 1.6),
                         rng.uniform(1.2, 3.0)] for _ in range(10)]
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self):
        self._t += 16
        if self._t >= self._life:
            self._timer.stop()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        try:
            k = min(1.0, self._t / float(self._life))
            p = QPainter(self)
            T.aa(p)
            R = 42.0 * self._power
            # 白闪
            if k < 0.22:
                a = int(230 * (1 - k / 0.22))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(T.a(T.qc("#FFFFFF"), a)))
                p.drawEllipse(QPointF(self._x, self._y), R * 0.7, R * 0.7)
            # 扩散环
            for i, (wf, af) in enumerate(((1.0, 190), (0.7, 120))):
                rr = R * (0.2 + k * (1.5 + i * 0.5))
                a = int(af * (1.0 - k))
                if a <= 0:
                    continue
                p.setPen(QPen(T.a(T.f(self._col, 1.4), a), max(1.0, 3.2 - i)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(self._x, self._y), rr, rr)
            # 碎屑
            p.setPen(Qt.PenStyle.NoPen)
            for (ang, spd, sz) in self._debris:
                import math as _m
                import random as _r
                d = R * 1.5 * k * spd
                ex = self._x + _m.cos(ang) * d
                ey = self._y + _m.sin(ang) * d + R * 0.5 * k * k
                a = int(200 * (1.0 - k))
                if a <= 0:
                    continue
                p.setBrush(QBrush(T.a(self._col, a)))
                p.drawEllipse(QPointF(ex, ey), sz, sz)
        except Exception:
            pass


class _GasCloud(QWidget):
    """毒气/燃烧蔓延：几团半透明雾向外飘。"""

    def __init__(self, parent, x, y, color, life_ms=620, power=1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(parent.rect())
        self._x, self._y = float(x), float(y)
        self._col = QColor(color)
        self._life = max(150, int(life_ms))
        self._power = max(0.5, min(2.0, float(power)))
        self._t = 0
        import random as _r
        rng = _r.Random(int(x * 11 + y * 5))
        self._puffs = [[rng.uniform(-0.5, 0.5), rng.uniform(-0.4, 0.4),
                        rng.uniform(0.6, 1.4), rng.uniform(0.0, 0.4)]
                       for _ in range(int(8 + 4 * power))]
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self):
        self._t += 16
        if self._t >= self._life:
            self._timer.stop()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        try:
            k = min(1.0, self._t / float(self._life))
            p = QPainter(self)
            T.aa(p)
            R = 30.0 * self._power
            p.setPen(Qt.PenStyle.NoPen)
            for (dx, dy, sz, delay) in self._puffs:
                kk = (k - delay) / max(0.05, 1.0 - delay)
                if kk <= 0 or kk >= 1:
                    continue
                ex = self._x + dx * R * 2.2 * kk
                ey = self._y + dy * R * 1.6 * kk - R * 0.35 * kk
                rr = R * sz * (0.4 + 0.9 * kk)
                a = int(95 * (1.0 - kk))
                p.setBrush(QBrush(T.a(self._col, a)))
                p.drawEllipse(QPointF(ex, ey), rr, rr * 0.82)
        except Exception:
            pass


def card_fx(parent: QWidget, kind: str, x: float, y: float,
            color: QColor = None, power: float = 1.0,
            from_x: float = None, from_y: float = None) -> None:
    """按卡牌类型播对应特效。

    kind:
      ``bullet`` 子弹飞向目标（from_x/from_y 是枪口位置；没给就默认从左侧）
      ``fire``   火焰爆开
      ``impact`` 冲击波
      ``gas``    毒气扩散
      ``spark``  电火花
      ``nuke``   核爆（大范围）
      其他       普通命中
    """
    if not _FX_ENABLED:
        return
    try:
        power = max(0.4, min(2.0, float(power or 1.0)))
        col = QColor(color) if color else QColor(T.GOLD)
        k = (kind or "").strip()
        if k == "bullet":
            sx = from_x if from_x is not None else x - 190.0
            sy = from_y if from_y is not None else y - 26.0
            _BulletTrail(parent, sx, sy, x, y, T.qc("#FFD98A"),
                         life_ms=int(150 + 40 * power))
            hit_effect(parent, x, y, col, power * 0.8)
        elif k == "fire":
            _FireBurst(parent, x, y, life_ms=int(420 + 160 * power),
                       power=power)
            ImpactRing(parent, x, y, QColor(T.Q_ORANGE),
                       max_r=22.0 + 16.0 * power,
                       life_ms=int(260 + 100 * power)).start()
        elif k == "impact":
            _ImpactShock(parent, x, y, col,
                         life_ms=int(280 + 90 * power), power=power)
        elif k == "gas":
            _GasCloud(parent, x, y, QColor("#7FBF6A"),
                      life_ms=int(520 + 160 * power), power=power)
        elif k == "nuke":
            _FireBurst(parent, x, y, life_ms=900, power=2.0)
            _ImpactShock(parent, x, y, QColor("#FFFFFF"),
                         life_ms=520, power=2.0)
            ImpactRing(parent, x, y, QColor(T.Q_ORANGE),
                       max_r=120.0, life_ms=560).start()
        elif k == "spark":
            SparkBurst(parent, x, y, QColor("#9AD8FF"),
                       count=22, spread=52.0, life_ms=460).start()
            ImpactRing(parent, x, y, QColor("#9AD8FF"),
                       max_r=30.0, life_ms=300).start()
        else:
            hit_effect(parent, x, y, col, power)
    except Exception:
        pass


def hit_effect(parent: QWidget, x: float, y: float,
               color: QColor = None, power: float = 1.0) -> None:
    """命中特效用这一个函数就够了（火花 + 冲击环，高伤害再加斩击）。

    ``power``：0.6 普通 / 1.0 强化 / 1.6 重击，用伤害大小换算。
    任何异常都吞掉 —— 没有特效也要能正常玩。
    """
    if not _FX_ENABLED:
        return
    try:
        col = QColor(color) if color else QColor(T.GOLD)
        power = max(0.4, min(2.0, float(power or 1.0)))
        SparkBurst(parent, x, y, col,
                   count=int(12 + 12 * power),
                   spread=34.0 + 22.0 * power,
                   life_ms=int(420 + 160 * power)).start()
        ImpactRing(parent, x, y, col,
                   max_r=26.0 + 20.0 * power,
                   life_ms=int(300 + 120 * power)).start()
        if power >= 1.25:
            SlashArc(parent, x, y, QColor(255, 244, 214),
                     radius=38.0 + 14.0 * power,
                     life_ms=280).start()
    except Exception:
        pass


def block_effect(parent: QWidget, x: float, y: float) -> None:
    """格挡特效：偏冷色的环 + 少量火花（和攻击区分开）。"""
    if not _FX_ENABLED:
        return
    try:
        ImpactRing(parent, x, y, QColor(T.Q_BLOCK),
                   max_r=30.0, life_ms=340, width=2.4).start()
        SparkBurst(parent, x, y, QColor(T.Q_BLOCK),
                   count=9, spread=28.0, life_ms=400).start()
    except Exception:
        pass


# --------------------------------------------------------------------------
# 界面过渡
# --------------------------------------------------------------------------
class _Fader(QWidget):
    """盖在整个窗口上的一层，用来做淡入淡出。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._alpha = 0.0
        self._slide = 0.0
        self.setGeometry(parent.rect())
        self.hide()

    def _get_a(self) -> float:
        return self._alpha

    def _set_a(self, v: float) -> None:
        self._alpha = float(v)
        self.update()

    def _get_s(self) -> float:
        return self._slide

    def _set_s(self, v: float) -> None:
        self._slide = float(v)
        self.update()

    alpha = pyqtProperty(float, fget=_get_a, fset=_set_a)
    slide = pyqtProperty(float, fget=_get_s, fset=_set_s)

    def paintEvent(self, ev) -> None:  # noqa: N802
        if self._alpha <= 0.001:
            return
        pt = QPainter(self)
        T.aa(pt)
        w, h = self.width(), self.height()
        col = QColor(T.Q_BG_DEEP)
        col.setAlphaF(max(0.0, min(1.0, self._alpha)))
        # 纯色幕布 + 一条斜向亮带，做出「推镜」的感觉
        pt.fillRect(self.rect(), col)
        band = QColor(T.Q_GOLD)
        band.setAlphaF(max(0.0, min(1.0, self._alpha * 0.10)))
        off = (1.0 - self._slide) * (w + h)
        path = QPainterPath()
        path.moveTo(off - h * 0.5, 0)
        path.lineTo(off + 90 - h * 0.5, 0)
        path.lineTo(off + 90, h)
        path.lineTo(off, h)
        path.closeSubpath()
        pt.setPen(Qt.PenStyle.NoPen)
        pt.setBrush(band)
        pt.drawPath(path)


def fade_switch(host: QWidget, do_switch, duration: int = 190) -> None:
    """带过渡地切换界面。

    用法::

        fade_switch(self, lambda: self.stack.setCurrentWidget(target))

    流程：盖一层幕布淡入 → 执行切换 → 淡出。
    ``do_switch`` 在幕布最不透明时调用，所以切换过程看不见。
    任何异常都会直接执行切换，保证功能不受影响。
    """
    if not _FX_ENABLED or duration <= 0:
        do_switch()
        return
    try:
        fader = _Fader(host)
        fader.setGeometry(host.rect())
        fader.show()
        fader.raise_()

        done = {"n": 0}

        def _phase2() -> None:
            # 幕布最黑 -> 切换 -> 淡出
            try:
                do_switch()
            except Exception:
                pass
            a2 = QPropertyAnimation(fader, b"alpha", fader)
            a2.setDuration(int(duration))
            a2.setStartValue(1.0)
            a2.setEndValue(0.0)
            a2.setEasingCurve(QEasingCurve.Type.OutCubic)
            a2.finished.connect(fader.deleteLater)
            fader._out = a2            # 保住引用，别被 GC
            a2.start()

        a1 = QPropertyAnimation(fader, b"alpha", fader)
        a1.setDuration(int(duration))
        a1.setStartValue(0.0)
        a1.setEndValue(1.0)
        a1.setEasingCurve(QEasingCurve.Type.InCubic)
        a1.finished.connect(_phase2)
        fader._in = a1
        a1.start()
    except Exception:
        try:
            do_switch()
        except Exception:
            pass


__all__ = [
    "set_enabled", "enabled",
    "SparkBurst", "ImpactRing", "SlashArc",
    "hit_effect", "block_effect", "fade_switch", "card_fx",
]
