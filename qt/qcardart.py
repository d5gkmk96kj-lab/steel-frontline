#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面插图渲染：把 ``core.cardart`` 的每张卡独立设计画出来。

设计要点
--------
* **纯矢量**：卡图区只有 ~150x76，位图缩下来必糊。
* **每张卡独立**：位置/尺寸/组合都来自 ``core.cardart.DESIGNS``。
* 所有尺寸乘 ``k``（卡片缩放系数），任何分辨率都锐利。
* 任何图元画挂了都只跳过它，不影响整张卡。
"""

from __future__ import annotations

import math
from typing import Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QLinearGradient, QPainterPath, QPen)

from core import cardart as CA

from . import qtheme as T


# ---------------------------------------------------------------- 调色板 --
def _ink(tcol: QColor, tint: int) -> QColor:
    """按 tint 取色：0=流派色 1=亮 2=暗 3=金 4=白。"""
    if tint == 1:
        return T.f(tcol, 1.35)
    if tint == 2:
        return T.f(tcol, 0.62)
    if tint == 3:
        return T.Q_GOLD
    if tint == 4:
        return T.qc("#E8E4DA")
    return tcol


_BG = {
    "dark": ("#171A1F", "#0D1013"),
    "olive": ("#1B2018", "#101310"),
    "steel": ("#1A1D22", "#0E1014"),
    "fire": ("#241512", "#120B09"),
}


# ---------------------------------------------------------------- 通用底 --
def _background(p, rect: QRectF, k: float, bg: str) -> None:
    top, bot = _BG.get(bg, _BG["dark"])
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, T.qc(top))
    g.setColorAt(1.0, T.qc(bot))
    T.fill_round(p, rect, 5 * k, QBrush(g))

    # 网格
    p.save()
    p.setPen(QPen(T.a(T.qc("#8A93A0"), 20), max(0.5, 0.6 * k)))
    step = rect.width() / 11.0
    x = rect.left() + step
    while x < rect.right() - 2:
        p.drawLine(QPointF(x, rect.top() + 2), QPointF(x, rect.bottom() - 2))
        x += step
    step = rect.height() / 4.0
    y = rect.top() + step
    while y < rect.bottom() - 2:
        p.drawLine(QPointF(rect.left() + 2, y), QPointF(rect.right() - 2, y))
        y += step
    # 扫描线
    p.setPen(QPen(T.a(T.qc("#FFFFFF"), 7), max(0.4, 0.5 * k)))
    y = rect.top() + 2
    while y < rect.bottom():
        p.drawLine(QPointF(rect.left() + 1, y), QPointF(rect.right() - 1, y))
        y += 3.0 * k
    p.restore()


def _frame(p, rect: QRectF, k: float, col: QColor) -> None:
    """取景框刻度 + 边框。"""
    p.save()
    p.setPen(QPen(T.a(col, 140), max(0.9, 1.0 * k)))
    L = min(rect.width(), rect.height()) * 0.15
    for cx, cy, dx, dy in (
            (rect.left(), rect.top(), 1, 1),
            (rect.right(), rect.top(), -1, 1),
            (rect.left(), rect.bottom(), 1, -1),
            (rect.right(), rect.bottom(), -1, -1)):
        ax, ay = cx + 3 * k, cy + 3 * k
        p.drawLine(QPointF(ax, ay), QPointF(ax + L * dx, ay))
        p.drawLine(QPointF(ax, ay), QPointF(ax, ay + L * dy))
    p.restore()
    T.stroke_round(p, rect, 5 * k, T.a(T.Q_BLACK, 95), max(0.8, 1.0 * k))


# =====================================================================
# 图元绘制
# =====================================================================
# 每个函数签名：(p, cx, cy, s, k, col)
#   cx, cy  中心（绝对坐标）
#   s       基准尺寸（约等于插图高度的一半）
#   k       卡片缩放

def _rifle(p, cx, cy, s, k, col):
    lw = max(1.4, 2.0 * k)
    p.setBrush(QBrush(T.a(col, 55)))
    # 枪托
    st = QPainterPath()
    st.moveTo(cx - s * 1.65, cy - s * 0.13)
    st.lineTo(cx - s * 0.85, cy - s * 0.10)
    st.lineTo(cx - s * 0.85, cy + s * 0.11)
    st.lineTo(cx - s * 1.55, cy + s * 0.19)
    st.closeSubpath()
    p.setPen(QPen(col, lw)); p.drawPath(st)
    # 机匣
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 85)))
    p.drawRoundedRect(QRectF(cx - s * 0.88, cy - s * 0.13, s * 0.80, s * 0.26),
                      s * 0.05, s * 0.05)
    # 护木
    p.setBrush(QBrush(T.a(col, 70)))
    p.drawRoundedRect(QRectF(cx + s * 0.0, cy - s * 0.09, s * 0.90, s * 0.18),
                      s * 0.04, s * 0.04)
    # 枪管
    p.setPen(QPen(col, max(1.8, 2.6 * k)))
    p.drawLine(QPointF(cx + s * 0.88, cy - s * 0.01), QPointF(cx + s * 1.70, cy - s * 0.01))
    # 弹匣
    mag = QPainterPath()
    mag.moveTo(cx - s * 0.30, cy + s * 0.12); mag.lineTo(cx + s * 0.04, cy + s * 0.12)
    mag.lineTo(cx - s * 0.06, cy + s * 0.45); mag.lineTo(cx - s * 0.44, cy + s * 0.42)
    mag.closeSubpath()
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 72))); p.drawPath(mag)
    # 准星
    p.setPen(QPen(col, max(1.0, 1.3 * k)))
    p.drawLine(QPointF(cx + s * 1.40, cy - s * 0.01), QPointF(cx + s * 1.40, cy - s * 0.18))
    p.drawLine(QPointF(cx + s * 1.30, cy - s * 0.18), QPointF(cx + s * 1.50, cy - s * 0.18))


def _smg(p, cx, cy, s, k, col):
    lw = max(1.3, 1.8 * k)
    p.setBrush(QBrush(T.a(col, 60)))
    p.setPen(QPen(col, lw))
    p.drawRoundedRect(QRectF(cx - s * 0.80, cy - s * 0.14, s * 1.30, s * 0.28),
                      s * 0.05, s * 0.05)
    p.drawLine(QPointF(cx + s * 0.50, cy - s * 0.01), QPointF(cx + s * 1.30, cy - s * 0.01))
    # 弹匣（长直）
    p.setBrush(QBrush(T.a(col, 75)))
    p.drawRoundedRect(QRectF(cx - s * 0.22, cy + s * 0.10, s * 0.22, s * 0.52),
                      s * 0.03, s * 0.03)
    # 散热孔
    p.setPen(QPen(T.a(col, 130), max(0.6, 0.8 * k)))
    for i in range(4):
        xx = cx + s * (0.60 + i * 0.16)
        p.drawLine(QPointF(xx, cy - s * 0.06), QPointF(xx, cy + s * 0.06))


def _cannon(p, cx, cy, s, k, col):
    lw = max(1.5, 2.1 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 65)))
    # 炮管
    bbl = QPainterPath()
    bbl.moveTo(cx - s * 0.20, cy - s * 0.20); bbl.lineTo(cx + s * 1.55, cy - s * 0.13)
    bbl.lineTo(cx + s * 1.55, cy + s * 0.13); bbl.lineTo(cx - s * 0.20, cy + s * 0.20)
    bbl.closeSubpath()
    p.drawPath(bbl)
    # 炮口
    p.setBrush(QBrush(T.a(col, 110)))
    p.drawEllipse(QRectF(cx + s * 1.42, cy - s * 0.19, s * 0.20, s * 0.38))
    # 炮架
    p.setBrush(QBrush(T.a(col, 80)))
    p.drawRoundedRect(QRectF(cx - s * 0.95, cy - s * 0.24, s * 0.80, s * 0.50),
                      s * 0.06, s * 0.06)
    # 轮
    p.setBrush(QBrush(T.a(col, 45)))
    p.drawEllipse(QPointF(cx - s * 0.55, cy + s * 0.40), s * 0.22, s * 0.22)


def _sniper(p, cx, cy, s, k, col):
    lw = max(1.4, 2.0 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 58)))
    # 枪身（长）
    p.drawLine(QPointF(cx - s * 1.55, cy), QPointF(cx + s * 1.60, cy - s * 0.02))
    p.setPen(QPen(col, max(2.6, 3.6 * k)))
    p.drawLine(QPointF(cx - s * 0.50, cy), QPointF(cx + s * 0.95, cy - s * 0.015))
    # 瞄准镜
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 90)))
    p.drawRoundedRect(QRectF(cx - s * 0.35, cy - s * 0.34, s * 0.75, s * 0.18),
                      s * 0.06, s * 0.06)
    p.drawLine(QPointF(cx - s * 0.20, cy - s * 0.16), QPointF(cx - s * 0.20, cy))
    p.drawLine(QPointF(cx + s * 0.25, cy - s * 0.16), QPointF(cx + s * 0.25, cy))
    # 枪托
    st = QPainterPath()
    st.moveTo(cx - s * 1.60, cy - s * 0.10); st.lineTo(cx - s * 1.00, cy - s * 0.08)
    st.lineTo(cx - s * 1.00, cy + s * 0.10); st.lineTo(cx - s * 1.50, cy + s * 0.20)
    st.closeSubpath()
    p.setBrush(QBrush(T.a(col, 70))); p.drawPath(st)


def _pistol(p, cx, cy, s, k, col):
    lw = max(1.3, 1.9 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 70)))
    # 套筒
    p.drawRoundedRect(QRectF(cx - s * 0.55, cy - s * 0.22, s * 1.20, s * 0.26),
                      s * 0.04, s * 0.04)
    # 握把
    gr = QPainterPath()
    gr.moveTo(cx - s * 0.42, cy + s * 0.04); gr.lineTo(cx - s * 0.08, cy + s * 0.04)
    gr.lineTo(cx + s * 0.04, cy + s * 0.60); gr.lineTo(cx - s * 0.34, cy + s * 0.62)
    gr.closeSubpath()
    p.drawPath(gr)
    # 扳机护圈
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(cx - s * 0.10, cy + s * 0.02, s * 0.30, s * 0.26), 190 * 16, 150 * 16)


def _turret(p, cx, cy, s, k, col):
    lw = max(1.4, 2.0 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 55)))
    # 车体
    body = QPainterPath()
    body.moveTo(cx - s * 1.05, cy + s * 0.30); body.lineTo(cx + s * 1.05, cy + s * 0.30)
    body.lineTo(cx + s * 0.88, cy - s * 0.05); body.lineTo(cx - s * 0.88, cy - s * 0.05)
    body.closeSubpath()
    p.drawPath(body)
    # 炮塔
    p.setBrush(QBrush(T.a(col, 85)))
    p.drawRoundedRect(QRectF(cx - s * 0.42, cy - s * 0.34, s * 0.84, s * 0.32),
                      s * 0.08, s * 0.08)
    # 炮管
    p.setPen(QPen(col, max(1.6, 2.3 * k)))
    p.drawLine(QPointF(cx + s * 0.42, cy - s * 0.18), QPointF(cx + s * 1.28, cy - s * 0.20))
    # 履带
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(T.a(col, 120)))
    p.drawRoundedRect(QRectF(cx - s * 1.02, cy + s * 0.30, s * 2.04, s * 0.18),
                      s * 0.08, s * 0.08)


def _bullet(p, cx, cy, s, k, col):
    p.setPen(Qt.PenStyle.NoPen)
    for i, (dx, al) in enumerate(((0.0, 230), (0.10, 160), (0.20, 90))):
        bx = cx - s * 0.42 + dx * s
        p.setBrush(QBrush(T.a(T.f(col, 1.3), al)))
        p.drawRoundedRect(QRectF(bx, cy - s * 0.055, s * 0.30, s * 0.11),
                          s * 0.05, s * 0.05)
    # 弹尖
    tip = QPainterPath()
    tip.moveTo(cx + s * 0.14, cy - s * 0.075); tip.lineTo(cx + s * 0.30, cy)
    tip.lineTo(cx + s * 0.14, cy + s * 0.075)
    tip.closeSubpath()
    p.setBrush(QBrush(T.a(T.f(col, 1.4), 230))); p.drawPath(tip)


def _shell(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 80)))
    body = QPainterPath()
    body.moveTo(cx - s * 0.18, cy - s * 0.14)
    body.lineTo(cx + s * 0.18, cy - s * 0.14)
    body.lineTo(cx + s * 0.18, cy + s * 0.18)
    body.lineTo(cx - s * 0.18, cy + s * 0.18)
    body.closeSubpath()
    p.drawPath(body)
    # 头锥
    head = QPainterPath()
    head.moveTo(cx - s * 0.18, cy - s * 0.14)
    head.lineTo(cx + s * 0.18, cy - s * 0.14)
    head.lineTo(cx, cy - s * 0.44)
    head.closeSubpath()
    p.setBrush(QBrush(T.a(col, 120))); p.drawPath(head)
    # 弹带
    p.setPen(QPen(T.a(col, 150), lw))
    p.drawLine(QPointF(cx - s * 0.20, cy + s * 0.02), QPointF(cx + s * 0.20, cy + s * 0.02))


def _mag(p, cx, cy, s, k, col):
    lw = max(1.2, 1.6 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 80)))
    p.drawRoundedRect(QRectF(cx - s * 0.16, cy - s * 0.42, s * 0.32, s * 0.84),
                      s * 0.05, s * 0.05)
    p.setPen(QPen(T.a(col, 140), max(0.7, 0.9 * k)))
    for i in range(4):
        yy = cy - s * 0.30 + i * s * 0.20
        p.drawLine(QPointF(cx - s * 0.11, yy), QPointF(cx + s * 0.11, yy))


def _crosshair(p, cx, cy, s, k, col):
    lw = max(1.0, 1.4 * k)
    p.setPen(QPen(col, lw)); p.setBrush(Qt.BrushStyle.NoBrush)
    r = s * 0.55
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.drawEllipse(QPointF(cx, cy), r * 0.30, r * 0.30)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        p.drawLine(QPointF(cx + dx * r * 0.42, cy + dy * r * 0.42),
                   QPointF(cx + dx * r * 1.25, cy + dy * r * 1.25))


def _scope(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 50)))
    p.drawEllipse(QPointF(cx, cy), s * 0.52, s * 0.52)
    p.setPen(QPen(T.a(col, 170), lw))
    p.drawLine(QPointF(cx - s * 0.52, cy), QPointF(cx + s * 0.52, cy))
    p.drawLine(QPointF(cx, cy - s * 0.52), QPointF(cx, cy + s * 0.52))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), s * 0.20, s * 0.20)


def _sandbags(p, cx, cy, s, k, col):
    lw = max(1.0, 1.3 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 45)))
    rows = ((0, 0.30, 3), (1, 0.02, 3), (2, -0.26, 2))
    for row, oy, n in rows:
        span = s * 1.50
        for i in range(n):
            x = cx - span / 2 + span * i / (n - 1) if n > 1 else cx
            r = QRectF(x - s * 0.26, cy + s * oy - s * 0.10, s * 0.52, s * 0.21)
            p.drawRoundedRect(r, s * 0.09, s * 0.09)


def _barbed_wire(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 175), max(0.9, 1.2 * k)))
    n = 7
    x0 = cx - s * 0.95
    step = s * 1.90 / n
    for row in (-1, 1):
        yy = cy + row * s * 0.16
        for i in range(n):
            x = x0 + step * i
            p.drawLine(QPointF(x, yy - s * 0.10), QPointF(x + step, yy + s * 0.10))
            p.drawLine(QPointF(x, yy + s * 0.10), QPointF(x + step, yy - s * 0.10))


def _bunker(p, cx, cy, s, k, col):
    lw = max(1.2, 1.6 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 60)))
    body = QPainterPath()
    body.moveTo(cx - s * 0.95, cy + s * 0.36)
    body.lineTo(cx + s * 0.95, cy + s * 0.36)
    body.lineTo(cx + s * 0.70, cy - s * 0.14)
    body.lineTo(cx - s * 0.70, cy - s * 0.14)
    body.closeSubpath()
    p.drawPath(body)
    # 射孔
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(T.a(T.Q_BLACK, 190)))
    p.drawRect(QRectF(cx - s * 0.45, cy - s * 0.04, s * 0.90, s * 0.13))


def _shield(p, cx, cy, s, k, col):
    lw = max(1.2, 1.7 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 55)))
    sp = QPainterPath()
    sp.moveTo(cx, cy - s * 0.52)
    sp.cubicTo(cx + s * 0.55, cy - s * 0.40, cx + s * 0.55, cy + s * 0.10,
               cx, cy + s * 0.54)
    sp.cubicTo(cx - s * 0.55, cy + s * 0.10, cx - s * 0.55, cy - s * 0.40,
               cx, cy - s * 0.52)
    p.drawPath(sp)
    p.setPen(QPen(T.a(col, 150), max(0.7, 0.9 * k)))
    p.drawLine(QPointF(cx, cy - s * 0.44), QPointF(cx, cy + s * 0.44))


def _plate(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 55)))
    p.drawRoundedRect(QRectF(cx - s * 0.62, cy - s * 0.42, s * 1.24, s * 0.84),
                      s * 0.08, s * 0.08)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(T.a(col, 140)))
    for dx, dy in ((-0.48, -0.28), (0.48, -0.28), (-0.48, 0.28), (0.48, 0.28)):
        p.drawEllipse(QPointF(cx + s * dx, cy + s * dy), s * 0.045, s * 0.045)


def _trench(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 165), max(1.0, 1.3 * k)))
    path = QPainterPath()
    path.moveTo(cx - s * 0.95, cy + s * 0.10)
    n = 8
    for i in range(n + 1):
        x = cx - s * 0.95 + s * 1.90 * i / n
        y = cy + s * 0.10 - (s * 0.16 if i % 2 else 0)
        path.lineTo(x, y)
    p.drawPath(path)
    p.setPen(QPen(T.a(col, 110), max(0.8, 1.0 * k)))
    p.drawLine(QPointF(cx - s * 0.95, cy + s * 0.40), QPointF(cx + s * 0.95, cy + s * 0.40))


def _wall(p, cx, cy, s, k, col):
    lw = max(1.0, 1.3 * k)
    p.setPen(QPen(col, lw)); p.setBrush(Qt.BrushStyle.NoBrush)
    for r in range(3):
        y = cy - s * 0.34 + r * s * 0.24
        off = (r % 2) * s * 0.22
        for c in range(4):
            x = cx - s * 0.72 + off + c * s * 0.44
            if x > cx + s * 0.72:
                continue
            p.drawRect(QRectF(x, y, s * 0.40, s * 0.21))


def _helmet(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 60)))
    path = QPainterPath()
    path.moveTo(cx - s * 0.52, cy + s * 0.10)
    path.cubicTo(cx - s * 0.52, cy - s * 0.48, cx + s * 0.52, cy - s * 0.48,
                 cx + s * 0.52, cy + s * 0.10)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(cx - s * 0.64, cy + s * 0.10), QPointF(cx + s * 0.64, cy + s * 0.10))


def _barricade(p, cx, cy, s, k, col):
    lw = max(1.0, 1.3 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 50)))
    p.drawRect(QRectF(cx - s * 0.75, cy - s * 0.28, s * 1.50, s * 0.20))
    p.drawRect(QRectF(cx - s * 0.75, cy + s * 0.06, s * 1.50, s * 0.20))
    p.setPen(QPen(T.a(col, 150), max(0.8, 1.0 * k)))
    for dx in (-0.52, 0.0, 0.52):
        p.drawLine(QPointF(cx + s * dx, cy - s * 0.40), QPointF(cx + s * dx, cy + s * 0.38))


def _flame(p, cx, cy, s, k, col):
    for scale, alpha in ((1.00, 70), (0.66, 130), (0.36, 210)):
        w = s * 0.44 * scale
        h = s * 0.72 * scale
        path = QPainterPath()
        path.moveTo(cx, cy - h)
        path.cubicTo(cx + w, cy - h * 0.30, cx + w * 0.72, cy + h * 0.58, cx, cy + h * 0.68)
        path.cubicTo(cx - w * 0.72, cy + h * 0.58, cx - w, cy - h * 0.30, cx, cy - h)
        p.setBrush(QBrush(T.a(T.f(col, 1.30), alpha)))
        p.setPen(QPen(T.a(col, min(255, alpha + 40)), max(0.6, 0.8 * k)))
        p.drawPath(path)


def _fireball(p, cx, cy, s, k, col):
    for r, al in ((s * 0.58, 50), (s * 0.40, 100), (s * 0.24, 180)):
        p.setPen(QPen(T.a(col, al + 40), max(0.7, 0.9 * k)))
        p.setBrush(QBrush(T.a(T.f(col, 1.35), al)))
        p.drawEllipse(QPointF(cx, cy), r, r)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(T.a(T.qc("#FFF0C0"), 200)))
    p.drawEllipse(QPointF(cx, cy), s * 0.11, s * 0.11)


def _explosion(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 190), max(0.8, 1.0 * k)))
    p.setBrush(QBrush(T.a(col, 55)))
    n = 9
    path = QPainterPath()
    for i in range(n * 2):
        ang = math.pi * 2 * i / (n * 2)
        r = s * (0.58 if i % 2 == 0 else 0.30)
        pt = QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r)
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _grenade(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 70)))
    p.drawEllipse(QPointF(cx, cy + s * 0.06), s * 0.34, s * 0.40)
    p.drawRect(QRectF(cx - s * 0.11, cy - s * 0.40, s * 0.22, s * 0.14))
    # 拉环
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx + s * 0.20, cy - s * 0.40), s * 0.12, s * 0.12)
    p.setPen(QPen(T.a(col, 140), max(0.7, 0.9 * k)))
    p.drawLine(QPointF(cx - s * 0.26, cy - s * 0.10), QPointF(cx + s * 0.26, cy - s * 0.10))
    p.drawLine(QPointF(cx - s * 0.26, cy + s * 0.20), QPointF(cx + s * 0.26, cy + s * 0.20))


def _molotov(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 65)))
    body = QPainterPath()
    body.moveTo(cx - s * 0.26, cy + s * 0.40)
    body.lineTo(cx + s * 0.26, cy + s * 0.40)
    body.lineTo(cx + s * 0.12, cy - s * 0.16)
    body.lineTo(cx - s * 0.12, cy - s * 0.16)
    body.closeSubpath()
    p.drawPath(body)
    p.drawLine(QPointF(cx - s * 0.10, cy - s * 0.16), QPointF(cx - s * 0.10, cy - s * 0.42))
    p.drawLine(QPointF(cx + s * 0.10, cy - s * 0.16), QPointF(cx + s * 0.10, cy - s * 0.42))
    # 火苗
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(T.a(T.Q_ORANGE, 220)))
    p.drawEllipse(QPointF(cx, cy - s * 0.50), s * 0.10, s * 0.16)


def _smoke(p, cx, cy, s, k, col):
    p.setPen(Qt.PenStyle.NoPen)
    for dx, dy, r, al in ((0, 0, 0.40, 42), (-0.28, 0.10, 0.26, 34),
                          (0.26, -0.08, 0.30, 30), (0.06, -0.24, 0.20, 26)):
        p.setBrush(QBrush(T.a(T.qc("#C3C8D0"), al)))
        p.drawEllipse(QPointF(cx + s * dx, cy + s * dy), s * r, s * r * 0.86)


def _ember(p, cx, cy, s, k, col):
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(4):
        ang = i * 1.9
        ex = cx + math.cos(ang) * s * 0.42
        ey = cy + math.sin(ang) * s * 0.34
        p.setBrush(QBrush(T.a(T.f(col, 1.4), 170)))
        p.drawEllipse(QPointF(ex, ey), s * 0.055, s * 0.055)


def _napalm(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 170), max(0.8, 1.0 * k)))
    p.setBrush(QBrush(T.a(col, 60)))
    path = QPainterPath()
    path.moveTo(cx - s * 0.80, cy + s * 0.30)
    path.cubicTo(cx - s * 0.40, cy - s * 0.46, cx + s * 0.40, cy - s * 0.46,
                 cx + s * 0.80, cy + s * 0.30)
    path.lineTo(cx + s * 0.80, cy + s * 0.44)
    path.lineTo(cx - s * 0.80, cy + s * 0.44)
    path.closeSubpath()
    p.drawPath(path)


def _ash(p, cx, cy, s, k, col):
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(7):
        ax = cx + (((i * 37) % 100) - 50) / 100.0 * s * 1.6
        ay = cy + (((i * 61) % 100) - 50) / 100.0 * s * 1.1
        p.setBrush(QBrush(T.a(T.qc("#9AA0AA"), 120)))
        p.drawEllipse(QPointF(ax, ay), s * 0.05, s * 0.05)


def _fuel_drum(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    w, h = s * 0.36, s * 0.62
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 55)))
    p.drawRoundedRect(QRectF(cx - w, cy - h, w * 2, h * 2), s * 0.07, s * 0.07)
    p.setPen(QPen(T.a(col, 185), max(0.7, 0.9 * k)))
    for fy in (0.32, 0.66):
        y = cy - h + h * 2 * fy
        p.drawLine(QPointF(cx - w + 1, y), QPointF(cx + w - 1, y))


def _crate(p, cx, cy, s, k, col):
    lw = max(1.0, 1.3 * k)
    w, h = s * 0.56, s * 0.44
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 50)))
    p.drawRect(QRectF(cx - w, cy - h, w * 2, h * 2))
    p.drawLine(QPointF(cx - w, cy - h), QPointF(cx + w, cy + h))
    p.drawLine(QPointF(cx + w, cy - h), QPointF(cx - w, cy + h))


def _gear(p, cx, cy, s, k, col):
    r = s * 0.36
    p.setPen(QPen(col, max(0.9, 1.2 * k))); p.setBrush(QBrush(T.a(col, 40)))
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setBrush(QBrush(T.a(col, 90)))
    for i in range(8):
        ang = i * math.pi / 4
        pt = QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r)
        p.drawEllipse(pt, s * 0.075, s * 0.075)


def _wrench(p, cx, cy, s, k, col):
    lw = max(1.6, 2.2 * k)
    p.setPen(QPen(col, lw)); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(cx - s * 0.44, cy + s * 0.46), QPointF(cx + s * 0.30, cy - s * 0.24))
    p.setBrush(QBrush(T.a(col, 70)))
    p.drawEllipse(QPointF(cx + s * 0.40, cy - s * 0.34), s * 0.20, s * 0.20)
    p.setBrush(QBrush(T.a(T.Q_BLACK, 200)))
    p.drawEllipse(QPointF(cx + s * 0.44, cy - s * 0.38), s * 0.10, s * 0.10)


def _jerrycan(p, cx, cy, s, k, col):
    lw = max(1.0, 1.3 * k)
    w, h = s * 0.34, s * 0.50
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 60)))
    p.drawRoundedRect(QRectF(cx - w, cy - h, w * 2, h * 2), s * 0.06, s * 0.06)
    p.drawRect(QRectF(cx - s * 0.10, cy - h - s * 0.12, s * 0.20, s * 0.12))
    p.setPen(QPen(T.a(col, 140), max(0.6, 0.8 * k)))
    p.drawLine(QPointF(cx - w * 0.5, cy - h * 0.5), QPointF(cx + w * 0.5, cy - h * 0.5))


def _pipe(p, cx, cy, s, k, col):
    lw = max(1.8, 2.6 * k)
    p.setPen(QPen(col, lw)); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(cx - s * 0.85, cy), QPointF(cx + s * 0.85, cy))
    p.setPen(QPen(T.a(col, 170), lw * 0.6))
    for dx in (-0.45, 0.0, 0.45):
        p.drawLine(QPointF(cx + s * dx, cy - s * 0.16), QPointF(cx + s * dx, cy + s * 0.16))


def _radio(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    w, h = s * 0.50, s * 0.34
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 60)))
    p.drawRoundedRect(QRectF(cx - w, cy - h, w * 2, h * 2), s * 0.06, s * 0.06)
    p.setBrush(QBrush(T.a(col, 130)))
    p.drawRect(QRectF(cx - w + s * 0.10, cy - h + s * 0.09, s * 0.34, s * 0.20))
    p.setBrush(QBrush(T.a(col, 95)))
    for i in range(2):
        p.drawEllipse(QPointF(cx + w * 0.55, cy - h * 0.42 + i * s * 0.26),
                      s * 0.065, s * 0.065)
    # 天线
    p.setPen(QPen(col, lw))
    p.drawLine(QPointF(cx - w * 0.7, cy - h), QPointF(cx - w * 0.95, cy - h * 2.3))


def _antenna(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 165), max(0.8, 1.0 * k)))
    top = QPointF(cx, cy - s * 0.55)
    p.drawLine(top, QPointF(cx - s * 0.30, cy + s * 0.50))
    p.drawLine(top, QPointF(cx + s * 0.30, cy + s * 0.50))
    for i in range(3):
        yy = cy - s * 0.55 + (s * 1.05) * (i + 1) / 4.0
        half = s * 0.30 * (i + 1) / 4.0
        p.drawLine(QPointF(cx - half, yy), QPointF(cx + half, yy))


def _binoculars(p, cx, cy, s, k, col):
    lw = max(1.1, 1.5 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 60)))
    for dx in (-0.24, 0.24):
        p.drawRoundedRect(QRectF(cx + s * dx - s * 0.16, cy - s * 0.34,
                                 s * 0.32, s * 0.68), s * 0.08, s * 0.08)
    p.drawRect(QRectF(cx - s * 0.10, cy - s * 0.08, s * 0.20, s * 0.16))


def _map(p, cx, cy, s, k, col):
    lw = max(1.0, 1.3 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 40)))
    path = QPainterPath()
    path.moveTo(cx - s * 0.60, cy - s * 0.40)
    path.lineTo(cx - s * 0.20, cy - s * 0.48)
    path.lineTo(cx + s * 0.20, cy - s * 0.40)
    path.lineTo(cx + s * 0.60, cy - s * 0.48)
    path.lineTo(cx + s * 0.60, cy + s * 0.40)
    path.lineTo(cx + s * 0.20, cy + s * 0.48)
    path.lineTo(cx - s * 0.20, cy + s * 0.40)
    path.lineTo(cx - s * 0.60, cy + s * 0.48)
    path.closeSubpath()
    p.drawPath(path)
    p.setPen(QPen(T.a(col, 130), max(0.6, 0.8 * k)))
    p.drawLine(QPointF(cx - s * 0.20, cy - s * 0.46), QPointF(cx - s * 0.20, cy + s * 0.42))
    p.drawLine(QPointF(cx + s * 0.20, cy - s * 0.42), QPointF(cx + s * 0.20, cy + s * 0.46))


def _flare(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 190), max(1.2, 1.6 * k)))
    p.drawLine(QPointF(cx, cy + s * 0.45), QPointF(cx, cy - s * 0.10))
    p.setPen(Qt.PenStyle.NoPen)
    for r, al in ((0.24, 60), (0.15, 120), (0.08, 220)):
        p.setBrush(QBrush(T.a(T.Q_GOLD, al)))
        p.drawEllipse(QPointF(cx, cy - s * 0.28), s * r, s * r)


def _signal(p, cx, cy, s, k, col):
    p.setPen(QPen(col, max(0.9, 1.2 * k))); p.setBrush(Qt.BrushStyle.NoBrush)
    for i, r in enumerate((0.22, 0.38, 0.54)):
        p.setPen(QPen(T.a(col, 190 - i * 45), max(0.9, 1.2 * k)))
        p.drawArc(QRectF(cx - s * r, cy - s * r, s * r * 2, s * r * 2), -50 * 16, 100 * 16)


def _troops(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 180), max(0.9, 1.2 * k)))
    for i in range(3):
        tx = cx - s * 0.42 + i * s * 0.42
        ty = cy + s * 0.40
        p.setBrush(QBrush(T.a(col, 80)))
        p.drawEllipse(QPointF(tx, ty - s * 0.42), s * 0.10, s * 0.10)
        p.drawLine(QPointF(tx, ty - s * 0.28), QPointF(tx, ty + s * 0.04))
        p.drawLine(QPointF(tx - s * 0.14, ty - s * 0.10), QPointF(tx + s * 0.14, ty - s * 0.10))


def _medic(p, cx, cy, s, k, col):
    lw = max(1.3, 1.8 * k)
    p.setPen(QPen(T.a(col, 210), lw)); p.setBrush(QBrush(T.a(col, 45)))
    p.drawRoundedRect(QRectF(cx - s * 0.46, cy - s * 0.46, s * 0.92, s * 0.92),
                      s * 0.10, s * 0.10)
    p.setBrush(QBrush(T.a(T.qc("#E8E4DA"), 200))); p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(QRectF(cx - s * 0.09, cy - s * 0.28, s * 0.18, s * 0.56))
    p.drawRect(QRectF(cx - s * 0.28, cy - s * 0.09, s * 0.56, s * 0.18))


def _flag(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 200), max(1.4, 2.0 * k)))
    p.drawLine(QPointF(cx - s * 0.52, cy - s * 0.52), QPointF(cx - s * 0.52, cy + s * 0.50))
    p.setPen(QPen(col, max(0.9, 1.2 * k))); p.setBrush(QBrush(T.a(col, 110)))
    fl = QPainterPath()
    fl.moveTo(cx - s * 0.52, cy - s * 0.50)
    fl.lineTo(cx + s * 0.50, cy - s * 0.36)
    fl.lineTo(cx + s * 0.16, cy - s * 0.02)
    fl.lineTo(cx + s * 0.50, cy + s * 0.16)
    fl.lineTo(cx - s * 0.52, cy + s * 0.02)
    fl.closeSubpath()
    p.drawPath(fl)


def _bullet_holes(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 110), max(0.6, 0.8 * k)))
    for i in range(4):
        hx = cx + ((i * 53 % 100) - 50) / 100.0 * s * 1.6
        hy = cy + ((i * 79 % 100) - 50) / 100.0 * s * 1.0
        p.setBrush(QBrush(T.a(T.Q_BLACK, 210)))
        p.drawEllipse(QPointF(hx, hy), s * 0.06, s * 0.06)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(hx, hy), s * 0.12, s * 0.12)


def _sight_ticks(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 140), max(0.6, 0.8 * k)))
    for i in range(4):
        yy = cy - s * 0.40 + i * s * 0.26
        ln = s * (0.26 if i % 2 == 0 else 0.14)
        p.drawLine(QPointF(cx + s * 0.55, yy), QPointF(cx + s * 0.55 - ln, yy))


def _rivets(p, cx, cy, s, k, col):
    p.setPen(Qt.PenStyle.NoPen)
    for dx, dy in ((-0.48, -0.30), (0.48, -0.30), (-0.48, 0.30), (0.48, 0.30)):
        p.setBrush(QBrush(T.a(col, 150)))
        p.drawEllipse(QPointF(cx + s * dx, cy + s * dy), s * 0.05, s * 0.05)


def _grid(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 70), max(0.5, 0.6 * k)))
    for i in range(4):
        xx = cx - s * 0.60 + i * s * 0.40
        p.drawLine(QPointF(xx, cy - s * 0.44), QPointF(xx, cy + s * 0.44))
    for i in range(3):
        yy = cy - s * 0.44 + i * s * 0.44
        p.drawLine(QPointF(cx - s * 0.60, yy), QPointF(cx + s * 0.60, yy))


def _scan(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 60), max(0.5, 0.6 * k)))
    yy = cy - s * 0.44
    while yy < cy + s * 0.44:
        p.drawLine(QPointF(cx - s * 0.62, yy), QPointF(cx + s * 0.62, yy))
        yy += s * 0.11


def _spark(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(T.f(col, 1.4), 220), max(1.0, 1.4 * k)))
    for ang in (0.0, 1.05, 2.09, 3.14, 4.19, 5.24):
        p.drawLine(QPointF(cx, cy),
                   QPointF(cx + math.cos(ang) * s * 0.42,
                           cy + math.sin(ang) * s * 0.42))


def _star(p, cx, cy, s, k, col):
    path = QPainterPath()
    n = 5
    for i in range(n * 2):
        ang = -math.pi / 2 + math.pi * i / n
        r = s * (0.44 if i % 2 == 0 else 0.19)
        pt = QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r)
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    p.setPen(QPen(col, max(0.8, 1.0 * k)))
    p.setBrush(QBrush(T.a(col, 90)))
    p.drawPath(path)


def _chevron_up(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 210), max(1.4, 2.0 * k)))
    p.drawLine(QPointF(cx - s * 0.40, cy + s * 0.16), QPointF(cx, cy - s * 0.22))
    p.drawLine(QPointF(cx, cy - s * 0.22), QPointF(cx + s * 0.40, cy + s * 0.16))


def _chevron_dn(p, cx, cy, s, k, col):
    p.setPen(QPen(T.a(col, 210), max(1.4, 2.0 * k)))
    p.drawLine(QPointF(cx - s * 0.40, cy - s * 0.16), QPointF(cx, cy + s * 0.22))
    p.drawLine(QPointF(cx, cy + s * 0.22), QPointF(cx + s * 0.40, cy - s * 0.16))


#: 图元分发表
_PART = {
    "rifle": _rifle, "smg": _smg, "cannon": _cannon, "sniper": _sniper,
    "pistol": _pistol, "turret": _turret,
    "bullet": _bullet, "shell": _shell, "mag": _mag,
    "crosshair": _crosshair, "scope": _scope,
    "sandbags": _sandbags, "barbed_wire": _barbed_wire, "bunker": _bunker,
    "shield": _shield, "plate": _plate, "trench": _trench, "wall": _wall,
    "helmet": _helmet, "barricade": _barricade,
    "flame": _flame, "explosion": _explosion, "grenade": _grenade,
    "molotov": _molotov, "smoke": _smoke, "ember": _ember,
    "napalm": _napalm, "fireball": _fireball, "ash": _ash,
    "fuel_drum": _fuel_drum, "crate": _crate, "gear": _gear,
    "wrench": _wrench, "jerrycan": _jerrycan, "pipe": _pipe,
    "radio": _radio, "antenna": _antenna, "binoculars": _binoculars,
    "map": _map, "flare": _flare, "signal": _signal,
    "troops": _troops, "medic": _medic, "flag": _flag,
    "bullet_holes": _bullet_holes, "sight_ticks": _sight_ticks,
    "rivets": _rivets, "grid": _grid, "scan": _scan,
    "spark": _spark, "star": _star,
    "chevron_up": _chevron_up, "chevron_dn": _chevron_dn,
}


# =====================================================================
# 入口
# =====================================================================
def paint(painter, rect: QRectF, card: dict, tcol: QColor, k: float) -> None:
    """把一张卡的插图完整画到 rect 里。"""
    d = CA.design_for(card)

    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
    _background(painter, rect, k, d.bg)

    # 图元：严格裁剪在插图区内（否则炮管会画到框外）
    painter.setClipRect(rect)
    base = min(rect.height() * 0.52, rect.width() * 0.30)
    tint_cols = {0: tcol, 1: T.f(tcol, 1.35), 2: T.f(tcol, 0.62),
                 3: T.Q_GOLD, 4: T.qc("#E8E4DA")}
    for part in d.parts:
        fn = _PART.get(part.kind)
        if fn is None:
            continue
        try:
            cx = rect.left() + rect.width() * part.x
            cy = rect.top() + rect.height() * part.y
            painter.save()
            painter.setOpacity(max(0.0, min(1.0, part.alpha / 255.0)))
            if abs(part.rot) > 0.01:
                painter.translate(cx, cy)
                painter.rotate(part.rot)
                painter.translate(-cx, -cy)
            fn(painter, cx, cy, base * part.s, k,
               tint_cols.get(part.tint, tcol))
            painter.restore()
        except Exception:
            try:
                painter.restore()
            except Exception:
                pass
    painter.restore()

    _frame(painter, rect, k, tcol)
