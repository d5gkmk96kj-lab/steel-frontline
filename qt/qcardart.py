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
from PyQt6.QtGui import (QBrush, QColor, QLinearGradient, QPainterPath,
                       QPen, QRadialGradient)

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


#: 场景配色：(天空顶, 天空底/地平线, 地面)
_BG_SCENE = {
    "dark":  ("#1E2733", "#3A4350", "#0B0D11"),   # 阴沉天空
    "olive": ("#26301F", "#414A32", "#0C0F0A"),   # 战场绿
    "steel": ("#202A36", "#3C4756", "#0A0C10"),   # 冷钢色
    "fire":  ("#3A1E14", "#6B3418", "#120805"),   # 火红天空
}


# ---------------------------------------------------------------- 通用底 --
def _background(p, rect: QRectF, k: float, bg: str) -> None:
    """场景化背景：天空渐变 + 地平线 + 地面 + 暗角。

    之前只有一个暗色渐变 + 网格 —— 看起来像"技术图纸"，太抽象。
    现在做成有纵深感的场景：上面是天空，中间是地平线，
    下面是地面，四周压暗（暗角）把视线聚到中间。
    """
    pal = _BG_SCENE.get(bg, _BG_SCENE["dark"])
    sky_top, sky_bot, ground = pal

    # 天空渐变
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, T.qc(sky_top))
    g.setColorAt(0.58, T.qc(sky_bot))
    g.setColorAt(1.0, T.qc(ground))
    T.fill_round(p, rect, 5 * k, QBrush(g))

    horizon = rect.top() + rect.height() * 0.60

    # 地平线：一条亮线（逆光感）
    p.save()
    p.setPen(QPen(T.a(T.qc("#6E7885"), 70), max(0.6, 0.9 * k)))
    p.drawLine(QPointF(rect.left() + 2, horizon), QPointF(rect.right() - 2, horizon))
    p.restore()

    # 远山/建筑剪影：地平线上几座三角，增加纵深
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    sil = T.a(T.qc("#0A0C10"), 150)
    p.setBrush(QBrush(sil))
    hills = QPainterPath()
    hills.moveTo(rect.left(), horizon + 1)
    n = 5
    for i in range(n + 1):
        x = rect.left() + rect.width() * i / n
        h = rect.height() * (0.045 + ((i * 37) % 40) / 400.0)
        hills.lineTo(x, horizon + 1 - h)
        if i < n:
            nx = rect.left() + rect.width() * (i + 0.5) / n
            hills.lineTo(nx, horizon + 1)
    hills.lineTo(rect.right(), horizon + 1)
    hills.closeSubpath()
    p.drawPath(hills)
    p.restore()

    # 地面：暗色 + 稀疏纹理
    p.save()
    p.setClipRect(QRectF(rect.left(), horizon, rect.width(),
                         rect.bottom() - horizon))
    gg = QLinearGradient(QPointF(0, horizon), QPointF(0, rect.bottom()))
    gg.setColorAt(0.0, T.a(T.qc("#12151A"), 90))
    gg.setColorAt(1.0, T.a(T.qc("#05070A"), 210))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gg))
    p.drawRect(QRectF(rect.left(), horizon, rect.width(),
                      rect.bottom() - horizon))
    # 透视网格（向远处收缩）
    p.setPen(QPen(T.a(T.qc("#7A8391"), 22), max(0.4, 0.6 * k)))
    for i in range(5):
        yy = horizon + (rect.bottom() - horizon) * (i / 5.0) ** 1.5
        p.drawLine(QPointF(rect.left() + 2, yy), QPointF(rect.right() - 2, yy))
    p.restore()

    # 暗角：四周压暗，视线聚到中间
    p.save()
    vig = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.72)
    vig.setColorAt(0.0, T.a(T.Q_BLACK, 0))
    vig.setColorAt(0.62, T.a(T.Q_BLACK, 25))
    vig.setColorAt(1.0, T.a(T.Q_BLACK, 165))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(vig))
    p.drawRoundedRect(rect, 5 * k, 5 * k)
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
# 明暗工具：让物体有体积感（这是"具象"的关键）
# =====================================================================

def _shade(rect: QRectF, base: QColor, light=1.0, dark=0.45):
    """纵向渐变填充：上亮下暗，模拟顶光。"""
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, T.f(base, light))
    g.setColorAt(0.55, base)
    g.setColorAt(1.0, T.f(base, dark))
    return QBrush(g)


def _metal(cx, cy, w, h, base, radius=0.0):
    """金属块：斜向高光 + 渐变 + 暗底。返回 (brush, rect)。"""
    r = QRectF(cx - w, cy - h, w * 2, h * 2)
    g = QLinearGradient(QPointF(r.left(), r.top()), QPointF(r.right(), r.bottom()))
    g.setColorAt(0.0, T.f(base, 1.55))
    g.setColorAt(0.28, T.f(base, 1.15))
    g.setColorAt(0.62, base)
    g.setColorAt(1.0, T.f(base, 0.42))
    return g, r


def _shadow(p, cx, cy, w, h, alpha=110):
    """地面投影：椭圆 + 径向渐变。"""
    g = QRadialGradient(QPointF(cx, cy), max(w, h))
    g.setColorAt(0.0, T.a(T.Q_BLACK, alpha))
    g.setColorAt(0.65, T.a(T.Q_BLACK, alpha // 2))
    g.setColorAt(1.0, T.a(T.Q_BLACK, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), w, h)


def _rim(p, path_or_rect, col: QColor, width=1.2, alpha=170):
    """轮廓高光：亮的细边，让物体从背景里跳出来。"""
    p.setPen(QPen(T.a(col, alpha), width))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if isinstance(path_or_rect, QRectF):
        p.drawRoundedRect(path_or_rect, 2, 2)
    else:
        p.drawPath(path_or_rect)


def _spec(p, cx, cy, r, alpha=150):
    """高光点：物体表面的反光。"""
    g = QRadialGradient(QPointF(cx, cy), r)
    g.setColorAt(0.0, T.a(T.qc("#FFFFFF"), alpha))
    g.setColorAt(0.55, T.a(T.qc("#FFFFFF"), alpha // 3))
    g.setColorAt(1.0, T.a(T.qc("#FFFFFF"), 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)


# =====================================================================
# 图元绘制
# =====================================================================
# 每个函数签名：(p, cx, cy, s, k, col)
#   cx, cy  中心（绝对坐标）
#   s       基准尺寸（约等于插图高度的一半）
#   k       卡片缩放

def _rifle(p, cx, cy, s, k, col):
    """步枪：木托 + 钢制机匣 + 枪管，带明暗和投影。"""
    lw = max(1.2, 1.8 * k)
    wood = T.qc("#8A5A32")       # 木质
    steel = T.qc("#5F6874")      # 钢
    _shadow(p, cx, cy + s * 0.34, s * 1.45, s * 0.16, 120)

    # —— 枪托（木，带渐变）
    st = QPainterPath()
    st.moveTo(cx - s * 1.62, cy - s * 0.15)
    st.lineTo(cx - s * 0.82, cy - s * 0.12)
    st.lineTo(cx - s * 0.82, cy + s * 0.15)
    st.lineTo(cx - s * 1.50, cy + s * 0.25)
    st.closeSubpath()
    gg, _ = _metal(cx - s * 1.2, cy, s * 0.45, s * 0.20, wood)
    p.setPen(QPen(T.f(wood, 0.45), lw))
    p.setBrush(QBrush(gg))
    p.drawPath(st)
    _rim(p, st, T.f(wood, 1.6), lw * 0.8, 120)

    # —— 机匣（钢）
    r = QRectF(cx - s * 0.86, cy - s * 0.16, s * 0.78, s * 0.32)
    gg2, _ = _metal(cx - s * 0.47, cy, s * 0.39, s * 0.16, steel)
    p.setPen(QPen(T.f(steel, 0.40), lw))
    p.setBrush(QBrush(gg2))
    p.drawRoundedRect(r, s * 0.05, s * 0.05)
    _spec(p, r.left() + r.width() * 0.28, r.top() + r.height() * 0.22,
          s * 0.10, 120)

    # —— 护木（木）
    w2 = QRectF(cx - s * 0.02, cy - s * 0.11, s * 0.92, s * 0.22)
    gg3, _ = _metal(cx + s * 0.44, cy, s * 0.46, s * 0.11, wood)
    p.setPen(QPen(T.f(wood, 0.45), lw))
    p.setBrush(QBrush(gg3))
    p.drawRoundedRect(w2, s * 0.04, s * 0.04)
    # 护木散热槽
    p.setPen(QPen(T.a(T.Q_BLACK, 130), max(0.5, 0.7 * k)))
    for i in range(3):
        xx = cx + s * (0.14 + i * 0.24)
        p.drawLine(QPointF(xx, cy - s * 0.07), QPointF(xx, cy + s * 0.07))

    # —— 枪管（钢，圆柱感）
    bbl = QRectF(cx + s * 0.88, cy - s * 0.045, s * 0.80, s * 0.09)
    gb = QLinearGradient(bbl.topLeft(), bbl.bottomLeft())
    gb.setColorAt(0.0, T.f(steel, 1.5))
    gb.setColorAt(0.5, steel)
    gb.setColorAt(1.0, T.f(steel, 0.35))
    p.setPen(QPen(T.f(steel, 0.40), max(0.6, 0.9 * k)))
    p.setBrush(QBrush(gb))
    p.drawRect(bbl)
    # 枪口
    p.setBrush(QBrush(T.qc("#1A1D22")))
    p.drawEllipse(QPointF(cx + s * 1.68, cy), s * 0.045, s * 0.055)

    # —— 弹匣（下挂弧形，钢）
    mag = QPainterPath()
    mag.moveTo(cx - s * 0.30, cy + s * 0.14)
    mag.lineTo(cx + s * 0.05, cy + s * 0.14)
    mag.lineTo(cx - s * 0.05, cy + s * 0.52)
    mag.lineTo(cx - s * 0.44, cy + s * 0.48)
    mag.closeSubpath()
    gg4, _ = _metal(cx - s * 0.18, cy + s * 0.32, s * 0.20, s * 0.20, steel)
    p.setPen(QPen(T.f(steel, 0.40), lw))
    p.setBrush(QBrush(gg4))
    p.drawPath(mag)

    # —— 准星
    p.setPen(QPen(T.f(steel, 1.3), max(0.9, 1.2 * k)))
    p.drawLine(QPointF(cx + s * 1.36, cy - s * 0.04), QPointF(cx + s * 1.36, cy - s * 0.22))
    p.drawLine(QPointF(cx + s * 1.26, cy - s * 0.22), QPointF(cx + s * 1.46, cy - s * 0.22))


def _smg(p, cx, cy, s, k, col):
    """冲锋枪：机匣 + 长弹匣 + 散热孔，带明暗。"""
    lw = max(0.9, 1.3 * k)
    steel = T.qc("#545B64")
    _shadow(p, cx, cy + s * 0.60, s * 0.80, s * 0.14, 115)
    body = QRectF(cx - s * 0.82, cy - s * 0.16, s * 1.32, s * 0.32)
    gg, _ = _metal(cx, cy, s * 0.66, s * 0.16, steel)
    p.setPen(QPen(T.f(steel, 0.32), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(body, s * 0.05, s * 0.05)
    # 枪管
    bbl = QRectF(cx + s * 0.50, cy - s * 0.055, s * 0.82, s * 0.11)
    gb = QLinearGradient(bbl.topLeft(), bbl.bottomLeft())
    gb.setColorAt(0.0, T.f(steel, 1.5))
    gb.setColorAt(0.55, steel)
    gb.setColorAt(1.0, T.f(steel, 0.34))
    p.setBrush(QBrush(gb))
    p.drawRect(bbl)
    # 长弹匣
    mg = QRectF(cx - s * 0.24, cy + s * 0.12, s * 0.24, s * 0.56)
    gm = QLinearGradient(mg.topLeft(), mg.rightTop())
    gm.setColorAt(0.0, T.f(steel, 1.35))
    gm.setColorAt(0.55, steel)
    gm.setColorAt(1.0, T.f(steel, 0.36))
    p.setBrush(QBrush(gm))
    p.drawRoundedRect(mg, s * 0.03, s * 0.03)
    # 散热孔
    p.setPen(QPen(T.a(T.qc("#08090C"), 190), max(0.7, 1.0 * k)))
    for i in range(4):
        xx = cx + s * (0.60 + i * 0.17)
        p.drawEllipse(QPointF(xx, cy), s * 0.028, s * 0.028)
    _spec(p, body.left() + s * 0.30, body.top() + s * 0.06, s * 0.10, 110)

def _cannon(p, cx, cy, s, k, col):
    """野战炮：粗炮管 + 炮盾 + 轮子 + 高光。"""
    lw = max(0.9, 1.3 * k)
    steel = T.qc("#5A6570")
    _shadow(p, cx, cy + s * 0.46, s * 1.30, s * 0.16, 130)

    # 炮管（粗细渐变）
    bbl = QRectF(cx - s * 0.16, cy - s * 0.20, s * 1.72, s * 0.34)
    gb = QLinearGradient(bbl.topLeft(), bbl.bottomLeft())
    gb.setColorAt(0.0, T.f(steel, 1.60))
    gb.setColorAt(0.30, T.f(steel, 1.10))
    gb.setColorAt(0.68, steel)
    gb.setColorAt(1.0, T.f(steel, 0.35))
    p.setPen(QPen(T.f(steel, 0.32), lw))
    p.setBrush(QBrush(gb))
    p.drawRoundedRect(bbl, s * 0.06, s * 0.06)

    # 炮口制退器
    mz = QRectF(cx + s * 1.48, cy - s * 0.25, s * 0.18, s * 0.44)
    p.setBrush(QBrush(T.f(steel, 0.75)))
    p.drawRoundedRect(mz, s * 0.04, s * 0.04)
    p.setBrush(QBrush(T.qc("#0E1014")))
    p.drawEllipse(QPointF(cx + s * 1.62, cy - s * 0.03), s * 0.05, s * 0.09)

    # 炮盾
    sh = QRectF(cx - s * 0.94, cy - s * 0.30, s * 0.78, s * 0.56)
    gs, _ = _metal(cx - s * 0.55, cy, s * 0.39, s * 0.28, steel)
    p.setPen(QPen(T.f(steel, 0.32), lw))
    p.setBrush(QBrush(gs))
    p.drawRoundedRect(sh, s * 0.06, s * 0.06)
    _spec(p, sh.left() + s * 0.18, sh.top() + s * 0.12, s * 0.10, 100)

    # 轮子
    for wx in (cx - s * 0.52, cx + s * 0.05):
        wr = s * 0.24
        p.setPen(QPen(T.qc("#2A2E24"), max(1.0, 1.4 * k)))
        gg = QLinearGradient(QPointF(wx - wr, cy + s * 0.18),
                             QPointF(wx + wr, cy + s * 0.62))
        gg.setColorAt(0.0, T.qc("#4A5040"))
        gg.setColorAt(1.0, T.qc("#14170F"))
        p.setBrush(QBrush(gg))
        p.drawEllipse(QPointF(wx, cy + s * 0.40), wr, wr)
        # 轮辐
        p.setPen(QPen(T.a(T.qc("#8A9278"), 150), max(0.5, 0.7 * k)))
        for ang in (0, 1.05, 2.09):
            p.drawLine(QPointF(wx - math.cos(ang) * wr * 0.7,
                               cy + s * 0.40 - math.sin(ang) * wr * 0.7),
                       QPointF(wx + math.cos(ang) * wr * 0.7,
                               cy + s * 0.40 + math.sin(ang) * wr * 0.7))
        p.setBrush(QBrush(T.f(steel, 1.2)))
        p.drawEllipse(QPointF(wx, cy + s * 0.40), wr * 0.28, wr * 0.28)

def _sniper(p, cx, cy, s, k, col):
    """狙击枪：长枪身 + 瞄准镜 + 枪托，带明暗。"""
    lw = max(0.9, 1.3 * k)
    steel = T.qc("#5C636D")
    wood = T.qc("#7A4E2A")
    _shadow(p, cx, cy + s * 0.26, s * 1.50, s * 0.13, 115)
    # 枪身
    p.setPen(QPen(T.f(steel, 0.32), max(1.6, 2.4 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(cx - s * 1.55, cy + s * 0.02), QPointF(cx + s * 1.60, cy - s * 0.02))
    bbl = QRectF(cx + s * 0.95, cy - s * 0.05, s * 0.70, s * 0.09)
    gb = QLinearGradient(bbl.topLeft(), bbl.bottomLeft())
    gb.setColorAt(0.0, T.f(steel, 1.45))
    gb.setColorAt(1.0, T.f(steel, 0.34))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gb))
    p.drawRect(bbl)
    # 护木
    wd = QRectF(cx - s * 0.50, cy - s * 0.09, s * 1.42, s * 0.18)
    gw, _ = _metal(cx + s * 0.21, cy, s * 0.71, s * 0.09, wood)
    p.setPen(QPen(T.f(wood, 0.36), lw))
    p.setBrush(QBrush(gw))
    p.drawRoundedRect(wd, s * 0.04, s * 0.04)
    # 枪托
    st = QPainterPath()
    st.moveTo(cx - s * 1.58, cy - s * 0.12)
    st.lineTo(cx - s * 0.98, cy - s * 0.09)
    st.lineTo(cx - s * 0.98, cy + s * 0.11)
    st.lineTo(cx - s * 1.48, cy + s * 0.24)
    st.closeSubpath()
    gst, _ = _metal(cx - s * 1.28, cy, s * 0.30, s * 0.14, wood)
    p.setBrush(QBrush(gst))
    p.drawPath(st)
    # 瞄准镜（圆柱）
    sc = QRectF(cx - s * 0.36, cy - s * 0.38, s * 0.78, s * 0.20)
    gsc = QLinearGradient(sc.topLeft(), sc.bottomLeft())
    gsc.setColorAt(0.0, T.f(steel, 1.55))
    gsc.setColorAt(0.45, steel)
    gsc.setColorAt(1.0, T.f(steel, 0.30))
    p.setPen(QPen(T.f(steel, 0.30), lw))
    p.setBrush(QBrush(gsc))
    p.drawRoundedRect(sc, s * 0.08, s * 0.08)
    # 镜片
    p.setBrush(QBrush(T.a(T.qc("#6FA8D0"), 220)))
    p.drawEllipse(QPointF(cx + s * 0.42, cy - s * 0.28), s * 0.05, s * 0.075)
    # 镜架
    p.setPen(QPen(T.f(steel, 0.8), max(0.6, 0.9 * k)))
    p.drawLine(QPointF(cx - s * 0.18, cy - s * 0.18), QPointF(cx - s * 0.18, cy - s * 0.02))
    p.drawLine(QPointF(cx + s * 0.26, cy - s * 0.18), QPointF(cx + s * 0.26, cy - s * 0.02))

def _pistol(p, cx, cy, s, k, col):
    """手枪：套筒 + 握把，带明暗和投影。"""
    lw = max(0.9, 1.3 * k)
    steel = T.qc("#5A616B")
    grip_c = T.qc("#3A2E22")
    _shadow(p, cx, cy + s * 0.62, s * 0.60, s * 0.10, 110)
    # 套筒
    sl = QRectF(cx - s * 0.56, cy - s * 0.24, s * 1.22, s * 0.28)
    gg, _ = _metal(cx, cy - s * 0.10, s * 0.61, s * 0.14, steel)
    p.setPen(QPen(T.f(steel, 0.32), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(sl, s * 0.04, s * 0.04)
    # 握把（木/聚合物）
    gr = QPainterPath()
    gr.moveTo(cx - s * 0.42, cy + s * 0.04)
    gr.lineTo(cx - s * 0.06, cy + s * 0.04)
    gr.lineTo(cx + s * 0.06, cy + s * 0.60)
    gr.lineTo(cx - s * 0.34, cy + s * 0.62)
    gr.closeSubpath()
    ggr, _ = _metal(cx - s * 0.20, cy + s * 0.32, s * 0.20, s * 0.28, grip_c)
    p.setBrush(QBrush(ggr))
    p.drawPath(gr)
    # 握把纹
    p.setPen(QPen(T.a(T.qc("#0A0C10"), 140), max(0.4, 0.6 * k)))
    for i in range(3):
        p.drawLine(QPointF(cx - s * 0.30, cy + s * (0.16 + i * 0.14)),
                   QPointF(cx - s * 0.10, cy + s * (0.14 + i * 0.14)))
    # 扳机护圈
    p.setPen(QPen(T.f(steel, 0.9), max(0.8, 1.1 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(cx - s * 0.10, cy + s * 0.02, s * 0.32, s * 0.28), 190 * 16, 150 * 16)
    _spec(p, sl.left() + s * 0.25, sl.top() + s * 0.06, s * 0.09, 120)

def _turret(p, cx, cy, s, k, col):
    """坦克：车体 + 炮塔 + 炮管 + 履带，带明暗。"""
    lw = max(0.9, 1.3 * k)
    base = T.qc("#5A6348")
    _shadow(p, cx, cy + s * 0.48, s * 1.20, s * 0.18, 130)

    # 车体
    body = QPainterPath()
    body.moveTo(cx - s * 1.05, cy + s * 0.30)
    body.lineTo(cx + s * 1.05, cy + s * 0.30)
    body.lineTo(cx + s * 0.90, cy - s * 0.06)
    body.lineTo(cx - s * 0.90, cy - s * 0.06)
    body.closeSubpath()
    gg, _ = _metal(cx, cy + s * 0.12, s * 1.0, s * 0.18, base)
    p.setPen(QPen(T.f(base, 0.35), lw))
    p.setBrush(QBrush(gg))
    p.drawPath(body)

    # 履带
    tr = QRectF(cx - s * 1.04, cy + s * 0.30, s * 2.08, s * 0.20)
    gt = QLinearGradient(tr.topLeft(), tr.bottomLeft())
    gt.setColorAt(0.0, T.qc("#3A3F36"))
    gt.setColorAt(1.0, T.qc("#14170F"))
    p.setPen(QPen(T.qc("#22261C"), max(0.6, 0.9 * k)))
    p.setBrush(QBrush(gt))
    p.drawRoundedRect(tr, s * 0.07, s * 0.07)
    # 履带齿
    p.setPen(QPen(T.a(T.qc("#6E7660"), 150), max(0.5, 0.7 * k)))
    for i in range(7):
        xx = tr.left() + tr.width() * (i + 0.5) / 7.0
        p.drawLine(QPointF(xx, tr.top() + 1), QPointF(xx, tr.bottom() - 1))

    # 炮塔
    tp = QRectF(cx - s * 0.44, cy - s * 0.36, s * 0.88, s * 0.34)
    gg2, _ = _metal(cx, cy - s * 0.19, s * 0.44, s * 0.17, base, )
    p.setPen(QPen(T.f(base, 0.35), lw))
    p.setBrush(QBrush(gg2))
    p.drawRoundedRect(tp, s * 0.10, s * 0.10)
    _spec(p, tp.left() + s * 0.22, tp.top() + s * 0.08, s * 0.10, 90)

    # 炮管
    bbl = QRectF(cx + s * 0.40, cy - s * 0.22, s * 0.92, s * 0.10)
    gb = QLinearGradient(bbl.topLeft(), bbl.bottomLeft())
    gb.setColorAt(0.0, T.f(base, 1.45))
    gb.setColorAt(0.55, base)
    gb.setColorAt(1.0, T.f(base, 0.35))
    p.setPen(QPen(T.f(base, 0.35), max(0.6, 0.9 * k)))
    p.setBrush(QBrush(gb))
    p.drawRect(bbl)
    # 炮口
    p.setBrush(QBrush(T.qc("#14170F")))
    p.drawEllipse(QPointF(cx + s * 1.30, cy - s * 0.17), s * 0.04, s * 0.055)

def _bullet(p, cx, cy, s, k, col):
    """子弹：黄铜弹壳 + 铜弹头 + 高光。"""
    brass = T.qc("#C89A38")
    _shadow(p, cx, cy + s * 0.14, s * 0.44, s * 0.05, 90)
    # 弹壳
    cs = QRectF(cx - s * 0.44, cy - s * 0.062, s * 0.46, s * 0.124)
    gc = QLinearGradient(cs.topLeft(), cs.bottomLeft())
    gc.setColorAt(0.0, T.f(brass, 1.60))
    gc.setColorAt(0.45, brass)
    gc.setColorAt(1.0, T.f(brass, 0.32))
    p.setPen(QPen(T.f(brass, 0.34), max(0.6, 0.9 * k)))
    p.setBrush(QBrush(gc))
    p.drawRoundedRect(cs, s * 0.03, s * 0.03)
    # 底缘
    p.setBrush(QBrush(T.f(brass, 1.15)))
    p.drawRect(QRectF(cs.left() - s * 0.03, cs.top() - s * 0.012,
                      s * 0.05, cs.height() + s * 0.024))
    # 弹头
    tip = QPainterPath()
    tip.moveTo(cx + s * 0.02, cy - s * 0.075)
    tip.lineTo(cx + s * 0.14, cy - s * 0.070)
    tip.lineTo(cx + s * 0.34, cy)
    tip.lineTo(cx + s * 0.14, cy + s * 0.070)
    tip.lineTo(cx + s * 0.02, cy + s * 0.075)
    tip.closeSubpath()
    gt = QLinearGradient(QPointF(cx, cy - s * 0.075), QPointF(cx, cy + s * 0.075))
    gt.setColorAt(0.0, T.qc("#E8C479"))
    gt.setColorAt(0.45, T.qc("#B87830"))
    gt.setColorAt(1.0, T.qc("#704018"))
    p.setBrush(QBrush(gt))
    p.drawPath(tip)
    _spec(p, cx - s * 0.20, cy - s * 0.030, s * 0.07, 170)

def _shell(p, cx, cy, s, k, col):
    """炮弹：黄铜壳 + 尖弹头 + 高光。"""
    lw = max(0.8, 1.1 * k)
    brass = T.qc("#B98A2E")
    lead = T.qc("#8C8F96")
    _shadow(p, cx, cy + s * 0.26, s * 0.36, s * 0.08, 100)

    # 壳体
    body = QRectF(cx - s * 0.17, cy - s * 0.10, s * 0.34, s * 0.34)
    gb = QLinearGradient(body.topLeft(), body.rightTop())
    gb.setColorAt(0.0, T.f(brass, 0.40))
    gb.setColorAt(0.35, T.f(brass, 1.55))
    gb.setColorAt(0.7, brass)
    gb.setColorAt(1.0, T.f(brass, 0.32))
    p.setPen(QPen(T.f(brass, 0.35), lw))
    p.setBrush(QBrush(gb))
    p.drawRoundedRect(body, s * 0.02, s * 0.02)
    # 底缘
    p.setBrush(QBrush(T.f(brass, 1.2)))
    p.drawRect(QRectF(body.left() - s * 0.02, body.bottom() - s * 0.055,
                      body.width() + s * 0.04, s * 0.055))

    # 弹头
    head = QPainterPath()
    head.moveTo(cx - s * 0.17, cy - s * 0.10)
    head.lineTo(cx + s * 0.17, cy - s * 0.10)
    head.lineTo(cx, cy - s * 0.44)
    head.closeSubpath()
    gh, _ = _metal(cx, cy - s * 0.24, s * 0.17, s * 0.17, lead)
    p.setPen(QPen(T.f(lead, 0.35), lw))
    p.setBrush(QBrush(gh))
    p.drawPath(head)
    _spec(p, cx - s * 0.05, cy - s * 0.24, s * 0.055, 150)

def _mag(p, cx, cy, s, k, col):
    """弹匣：钢壳 + 子弹头露出 + 高光。"""
    lw = max(0.8, 1.1 * k)
    steel = T.qc("#5E656E")
    brass = T.qc("#C09030")
    _shadow(p, cx, cy + s * 0.46, s * 0.26, s * 0.07, 100)
    r = QRectF(cx - s * 0.17, cy - s * 0.42, s * 0.34, s * 0.86)
    gg = QLinearGradient(r.leftTop(), r.rightBottom())
    gg.setColorAt(0.0, T.f(steel, 1.5))
    gg.setColorAt(0.45, steel)
    gg.setColorAt(1.0, T.f(steel, 0.34))
    p.setPen(QPen(T.f(steel, 0.32), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(r, s * 0.05, s * 0.05)
    # 顶部露出的子弹
    for i in range(3):
        bx = r.left() + r.width() * (0.25 + i * 0.25)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.f(brass, 1.25)))
        p.drawRoundedRect(QRectF(bx - s * 0.035, r.top() - s * 0.09,
                                 s * 0.07, s * 0.12), s * 0.03, s * 0.03)
    # 侧肋
    p.setPen(QPen(T.a(T.qc("#FFFFFF"), 40), max(0.8, 1.2 * k)))
    p.drawLine(QPointF(r.left() + r.width() * 0.28, r.top() + s * 0.14),
               QPointF(r.left() + r.width() * 0.28, r.bottom() - s * 0.10))

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
    """沙袋工事：三层错缝堆叠，每个袋子有明暗。"""
    lw = max(0.8, 1.1 * k)
    base = T.qc("#8C7A4A")
    _shadow(p, cx, cy + s * 0.42, s * 1.30, s * 0.16, 120)
    rows = ((0, 0.30, 3), (1, 0.02, 3), (2, -0.26, 2))
    for row, oy, n in rows:
        span = s * 1.50
        for i in range(n):
            x = cx - span / 2 + span * i / (n - 1) if n > 1 else cx
            r = QRectF(x - s * 0.26, cy + s * oy - s * 0.11, s * 0.52, s * 0.23)
            gg, _ = _metal(x, cy + s * oy, s * 0.26, s * 0.115, base)
            p.setPen(QPen(T.f(base, 0.42), lw))
            p.setBrush(QBrush(gg))
            p.drawRoundedRect(r, s * 0.10, s * 0.10)
            # 缝线
            p.setPen(QPen(T.a(T.f(base, 0.5), 140), max(0.4, 0.6 * k)))
            p.drawLine(QPointF(x - s * 0.16, cy + s * oy),
                       QPointF(x + s * 0.16, cy + s * oy))
            _spec(p, x - s * 0.10, cy + s * oy - s * 0.05, s * 0.08, 80)

def _barbed_wire(p, cx, cy, s, k, col):
    """铁丝网：金属丝 + 倒刺 + 支撑柱。"""
    lw = max(0.7, 1.0 * k)
    wire = T.qc("#9AA3AD")
    # 后层（暗）
    for row, yy, al in ((0, -s * 0.20, 110), (1, s * 0.14, 175)):
        p.setPen(QPen(T.a(wire, al), max(0.8, 1.1 * k)))
        n = 8
        x0 = cx - s * 0.92
        step = s * 1.84 / n
        for i in range(n):
            x = x0 + step * i
            p.drawLine(QPointF(x, cy + yy - s * 0.09),
                       QPointF(x + step, cy + yy + s * 0.09))
            p.drawLine(QPointF(x, cy + yy + s * 0.09),
                       QPointF(x + step, cy + yy - s * 0.09))
        # 倒刺：每个交点画小叉
        p.setPen(QPen(T.a(T.qc("#D8DEE6"), al), max(0.6, 0.9 * k)))
        for i in range(n + 1):
            x = x0 + step * i
            p.drawLine(QPointF(x - s * 0.03, cy + yy - s * 0.03),
                       QPointF(x + s * 0.03, cy + yy + s * 0.03))
            p.drawLine(QPointF(x - s * 0.03, cy + yy + s * 0.03),
                       QPointF(x + s * 0.03, cy + yy - s * 0.03))

    # 支撑柱
    for px_ in (cx - s * 0.88, cx + s * 0.88):
        col_r = QRectF(px_ - s * 0.035, cy - s * 0.42, s * 0.07, s * 0.86)
        gp = QLinearGradient(col_r.topLeft(), col_r.rightTop())
        gp.setColorAt(0.0, T.qc("#6A5240"))
        gp.setColorAt(0.4, T.qc("#9A7A5A"))
        gp.setColorAt(1.0, T.qc("#4A3828"))
        p.setPen(QPen(T.qc("#2A2018"), max(0.5, 0.8 * k)))
        p.setBrush(QBrush(gp))
        p.drawRoundedRect(col_r, s * 0.02, s * 0.02)
        _shadow(p, px_, cy + s * 0.46, s * 0.14, s * 0.05, 90)

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
    """装甲板：斜向金属高光 + 四角铆钉 + 边缘磨损。"""
    lw = max(0.9, 1.3 * k)
    base = T.qc("#5C6672")
    _shadow(p, cx, cy + s * 0.46, s * 0.75, s * 0.14, 110)
    r = QRectF(cx - s * 0.64, cy - s * 0.44, s * 1.28, s * 0.88)
    gg, _ = _metal(cx, cy, s * 0.64, s * 0.44, base)
    p.setPen(QPen(T.f(base, 0.38), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(r, s * 0.08, s * 0.08)
    # 斜高光带
    p.setPen(QPen(T.a(T.qc("#FFFFFF"), 55), max(2.0, 3.2 * k)))
    p.drawLine(QPointF(r.left() + r.width() * 0.16, r.bottom() - r.height() * 0.10),
               QPointF(r.left() + r.width() * 0.52, r.top() + r.height() * 0.10))
    # 铆钉
    for dx, dy in ((-0.52, -0.34), (0.52, -0.34), (-0.52, 0.34), (0.52, 0.34)):
        px_, py_ = cx + s * dx, cy + s * dy
        p.setPen(QPen(T.f(base, 0.35), max(0.5, 0.7 * k)))
        p.setBrush(QBrush(T.f(base, 1.5)))
        p.drawEllipse(QPointF(px_, py_), s * 0.052, s * 0.052)
        _spec(p, px_ - s * 0.016, py_ - s * 0.018, s * 0.030, 170)

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
    """钢盔：顶部高光 + 底部暗部 + 帽檐。"""
    lw = max(0.9, 1.2 * k)
    base = T.qc("#4E5A46")
    _shadow(p, cx, cy + s * 0.26, s * 0.62, s * 0.11, 110)
    path = QPainterPath()
    path.moveTo(cx - s * 0.54, cy + s * 0.10)
    path.cubicTo(cx - s * 0.54, cy - s * 0.52, cx + s * 0.54, cy - s * 0.52,
                 cx + s * 0.54, cy + s * 0.10)
    path.closeSubpath()
    gg = QLinearGradient(QPointF(cx, cy - s * 0.50), QPointF(cx, cy + s * 0.10))
    gg.setColorAt(0.0, T.f(base, 1.65))
    gg.setColorAt(0.45, T.f(base, 1.05))
    gg.setColorAt(1.0, T.f(base, 0.38))
    p.setPen(QPen(T.f(base, 0.32), lw))
    p.setBrush(QBrush(gg))
    p.drawPath(path)
    # 帽檐
    rim = QRectF(cx - s * 0.66, cy + s * 0.06, s * 1.32, s * 0.14)
    gr = QLinearGradient(rim.topLeft(), rim.bottomLeft())
    gr.setColorAt(0.0, T.f(base, 1.20))
    gr.setColorAt(1.0, T.f(base, 0.34))
    p.setBrush(QBrush(gr))
    p.drawRoundedRect(rim, s * 0.07, s * 0.07)
    _spec(p, cx - s * 0.16, cy - s * 0.30, s * 0.14, 130)

def _barricade(p, cx, cy, s, k, col):
    lw = max(1.0, 1.3 * k)
    p.setPen(QPen(col, lw)); p.setBrush(QBrush(T.a(col, 50)))
    p.drawRect(QRectF(cx - s * 0.75, cy - s * 0.28, s * 1.50, s * 0.20))
    p.drawRect(QRectF(cx - s * 0.75, cy + s * 0.06, s * 1.50, s * 0.20))
    p.setPen(QPen(T.a(col, 150), max(0.8, 1.0 * k)))
    for dx in (-0.52, 0.0, 0.52):
        p.drawLine(QPointF(cx + s * dx, cy - s * 0.40), QPointF(cx + s * dx, cy + s * 0.38))


def _flame(p, cx, cy, s, k, col):
    """火焰：三层色阶（暗红 -> 橙 -> 黄白）+ 外发光。"""
    # 外发光
    gl = QRadialGradient(QPointF(cx, cy + s * 0.10), s * 0.95)
    gl.setColorAt(0.0, T.a(T.qc("#FF8A3C"), 120))
    gl.setColorAt(0.55, T.a(T.qc("#E8501E"), 55))
    gl.setColorAt(1.0, T.a(T.qc("#E8501E"), 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gl))
    p.drawEllipse(QPointF(cx, cy + s * 0.10), s * 0.95, s * 1.05)

    # 三层火舌：从外到内，颜色越来越亮
    layers = ((1.00, "#B02A08", 235), (0.68, "#F07018", 245),
              (0.38, "#FFD24A", 255))
    for scale, hexcol, alpha in layers:
        w = s * 0.50 * scale
        h = s * 0.78 * scale
        path = QPainterPath()
        path.moveTo(cx, cy - h)
        path.cubicTo(cx + w * 1.05, cy - h * 0.34,
                     cx + w * 0.80, cy + h * 0.62, cx, cy + h * 0.72)
        path.cubicTo(cx - w * 0.80, cy + h * 0.62,
                     cx - w * 1.05, cy - h * 0.34, cx, cy - h)
        # 每层加纵向渐变（下亮上暗）
        gg = QLinearGradient(QPointF(cx, cy - h), QPointF(cx, cy + h * 0.7))
        base = T.qc(hexcol)
        gg.setColorAt(0.0, T.a(T.f(base, 1.25), alpha))
        gg.setColorAt(0.55, T.a(base, alpha))
        gg.setColorAt(1.0, T.a(T.f(base, 1.35), alpha))
        p.setBrush(QBrush(gg))
        p.setPen(QPen(T.a(T.f(base, 0.6), 120), max(0.5, 0.7 * k)))
        p.drawPath(path)

    # 核心亮点
    _spec(p, cx, cy + s * 0.28, s * 0.16, 200)
    # 余烬
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(5):
        ang = i * 1.7 + 0.4
        ex = cx + math.cos(ang) * s * 0.62
        ey = cy - s * 0.30 + math.sin(ang) * s * 0.45
        p.setBrush(QBrush(T.a(T.qc("#FFC24A"), 190)))
        p.drawEllipse(QPointF(ex, ey), s * 0.035, s * 0.035)


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
    """手雷：菠萝纹弹体 + 保险杆，带明暗。"""
    lw = max(0.8, 1.1 * k)
    base = T.qc("#4A5238")
    _shadow(p, cx, cy + s * 0.50, s * 0.40, s * 0.09, 110)
    # 弹体（球）
    gg = QRadialGradient(QPointF(cx - s * 0.12, cy - s * 0.10), s * 0.62)
    gg.setColorAt(0.0, T.f(base, 1.75))
    gg.setColorAt(0.45, T.f(base, 1.05))
    gg.setColorAt(1.0, T.f(base, 0.34))
    p.setPen(QPen(T.f(base, 0.30), lw))
    p.setBrush(QBrush(gg))
    p.drawEllipse(QPointF(cx, cy + s * 0.06), s * 0.34, s * 0.40)
    # 菠萝纹（横竖格）
    p.setPen(QPen(T.a(T.f(base, 0.45), 140), max(0.4, 0.6 * k)))
    for i in range(-2, 3):
        yy = cy + s * 0.06 + i * s * 0.11
        p.drawLine(QPointF(cx - s * 0.30, yy), QPointF(cx + s * 0.30, yy))
    for i in range(-2, 3):
        xx = cx + i * s * 0.11
        p.drawLine(QPointF(xx, cy - s * 0.26), QPointF(xx, cy + s * 0.40))
    # 引信座
    neck = QRectF(cx - s * 0.11, cy - s * 0.44, s * 0.22, s * 0.16)
    gn, _ = _metal(cx, cy - s * 0.36, s * 0.11, s * 0.08, T.qc("#6A6F78"))
    p.setPen(QPen(T.qc("#2A2E24"), lw))
    p.setBrush(QBrush(gn))
    p.drawRoundedRect(neck, s * 0.03, s * 0.03)
    # 保险杆
    p.setPen(QPen(T.qc("#9AA3AD"), max(1.2, 1.8 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(cx - s * 0.30, cy - s * 0.44, s * 0.60, s * 0.52), 20 * 16, 140 * 16)
    # 拉环
    p.setPen(QPen(T.qc("#B9C0C9"), max(0.9, 1.3 * k)))
    p.drawEllipse(QPointF(cx + s * 0.30, cy - s * 0.40), s * 0.11, s * 0.11)
    _spec(p, cx - s * 0.14, cy - s * 0.14, s * 0.12, 150)

def _molotov(p, cx, cy, s, k, col):
    """燃烧瓶：玻璃瓶 + 液体 + 布条火焰，带透明感。"""
    lw = max(0.8, 1.1 * k)
    # 火焰（顶部）
    _shadow(p, cx, cy + s * 0.48, s * 0.34, s * 0.08, 110)
    # 瓶身
    body = QPainterPath()
    body.moveTo(cx - s * 0.28, cy + s * 0.42)
    body.cubicTo(cx - s * 0.30, cy + s * 0.10, cx - s * 0.14, cy - s * 0.06,
                 cx - s * 0.13, cy - s * 0.18)
    body.lineTo(cx + s * 0.13, cy - s * 0.18)
    body.cubicTo(cx + s * 0.14, cy - s * 0.06, cx + s * 0.30, cy + s * 0.10,
                 cx + s * 0.28, cy + s * 0.42)
    body.closeSubpath()
    gb = QLinearGradient(QPointF(cx - s * 0.28, 0), QPointF(cx + s * 0.28, 0))
    gb.setColorAt(0.0, T.qc("#2E4A2A"))
    gb.setColorAt(0.30, T.qc("#7AA05A"))
    gb.setColorAt(0.55, T.qc("#4A6E38"))
    gb.setColorAt(1.0, T.qc("#1E3018"))
    p.setPen(QPen(T.a(T.qc("#C8E0A8"), 140), lw))
    p.setBrush(QBrush(gb))
    p.drawPath(body)
    # 液体
    liq = QRectF(cx - s * 0.25, cy + s * 0.10, s * 0.50, s * 0.30)
    gl = QLinearGradient(liq.topLeft(), liq.bottomLeft())
    gl.setColorAt(0.0, T.a(T.qc("#E8A020"), 150))
    gl.setColorAt(1.0, T.a(T.qc("#8C4A10"), 190))
    p.setBrush(QBrush(gl))
    p.drawEllipse(liq)
    # 瓶颈
    p.setPen(QPen(T.a(T.qc("#C8E0A8"), 130), max(0.7, 1.0 * k)))
    p.setBrush(QBrush(T.a(T.qc("#7AA05A"), 120)))
    p.drawRect(QRectF(cx - s * 0.12, cy - s * 0.30, s * 0.24, s * 0.14))
    # 布条 + 火苗
    p.setPen(QPen(T.qc("#D8D0B8"), max(1.0, 1.4 * k)))
    p.drawLine(QPointF(cx, cy - s * 0.30), QPointF(cx + s * 0.04, cy - s * 0.44))
    p.setPen(Qt.PenStyle.NoPen)
    for r, a, c in ((s * 0.15, 90, "#F07018"), (s * 0.095, 170, "#FFB03A"),
                    (s * 0.05, 230, "#FFE48A")):
        p.setBrush(QBrush(T.a(T.qc(c), a)))
        p.drawEllipse(QPointF(cx + s * 0.04, cy - s * 0.50), r * 0.8, r * 1.15)
    _spec(p, cx - s * 0.12, cy + s * 0.02, s * 0.09, 130)

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
    """油桶：圆柱感（横向渐变）+ 顶盖 + 双箍 + 高光。"""
    lw = max(0.9, 1.3 * k)
    w, h = s * 0.38, s * 0.60
    base = T.qc("#7A5A2E")
    _shadow(p, cx, cy + h * 1.05, w * 1.25, h * 0.22, 120)

    body = QRectF(cx - w, cy - h, w * 2, h * 2)
    # 横向渐变 = 圆柱
    gg = QLinearGradient(QPointF(body.left(), 0), QPointF(body.right(), 0))
    gg.setColorAt(0.0, T.f(base, 0.35))
    gg.setColorAt(0.22, T.f(base, 1.30))
    gg.setColorAt(0.48, T.f(base, 1.55))
    gg.setColorAt(0.72, base)
    gg.setColorAt(1.0, T.f(base, 0.28))
    p.setPen(QPen(T.f(base, 0.35), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(body, s * 0.07, s * 0.07)

    # 顶盖椭圆
    cap = QRectF(cx - w, cy - h - h * 0.13, w * 2, h * 0.26)
    gc = QLinearGradient(QPointF(cap.left(), 0), QPointF(cap.right(), 0))
    gc.setColorAt(0.0, T.f(base, 0.40))
    gc.setColorAt(0.45, T.f(base, 1.65))
    gc.setColorAt(1.0, T.f(base, 0.35))
    p.setBrush(QBrush(gc))
    p.drawEllipse(cap)

    # 两道箍
    p.setPen(QPen(T.a(T.f(base, 0.30), 200), max(0.8, 1.1 * k)))
    for fy in (0.30, 0.66):
        y = body.top() + body.height() * fy
        p.drawLine(QPointF(body.left() + 1, y), QPointF(body.right() - 1, y))

    # 竖向高光
    p.setPen(QPen(T.a(T.qc("#FFFFFF"), 70), max(1.2, 1.8 * k)))
    p.drawLine(QPointF(cx - w * 0.30, body.top() + h * 0.18),
               QPointF(cx - w * 0.30, body.bottom() - h * 0.18))


def _crate(p, cx, cy, s, k, col):
    """补给箱：木箱 + 铁边 + 斜木条。"""
    lw = max(0.8, 1.1 * k)
    base = T.qc("#8A6A3E")
    w, h = s * 0.56, s * 0.44
    _shadow(p, cx, cy + h * 1.20, w * 1.15, h * 0.26, 115)
    r = QRectF(cx - w, cy - h, w * 2, h * 2)
    gg, _ = _metal(cx, cy, w, h, base)
    p.setPen(QPen(T.f(base, 0.38), lw))
    p.setBrush(QBrush(gg))
    p.drawRect(r)
    # 木板横纹
    p.setPen(QPen(T.a(T.f(base, 0.52), 150), max(0.5, 0.7 * k)))
    for i in range(1, 3):
        y = r.top() + r.height() * i / 3.0
        p.drawLine(QPointF(r.left() + 1, y), QPointF(r.right() - 1, y))
    # 铁边
    p.setPen(QPen(T.qc("#6E7682"), max(1.2, 1.7 * k)))
    p.drawRect(r)
    # 斜撑
    p.setPen(QPen(T.a(T.f(base, 0.6), 170), max(1.0, 1.4 * k)))
    p.drawLine(QPointF(cx - w, cy - h), QPointF(cx + w, cy + h))
    p.drawLine(QPointF(cx + w, cy - h), QPointF(cx - w, cy + h))

def _gear(p, cx, cy, s, k, col):
    """齿轮：金属齿 + 中心孔 + 高光。"""
    lw = max(0.8, 1.1 * k)
    base = T.qc("#7A6A52")
    r = s * 0.34
    _shadow(p, cx, cy + r * 1.2, r * 1.3, r * 0.28, 100)
    # 齿
    p.setPen(QPen(T.f(base, 0.35), lw))
    gg, _ = _metal(cx, cy, r, r, base)
    p.setBrush(QBrush(gg))
    for i in range(8):
        ang = i * math.pi / 4
        px_ = cx + math.cos(ang) * r * 0.86
        py_ = cy + math.sin(ang) * r * 0.86
        p.drawEllipse(QPointF(px_, py_), s * 0.085, s * 0.085)
    # 主体
    p.drawEllipse(QPointF(cx, cy), r, r)
    # 中心孔
    p.setPen(QPen(T.f(base, 0.30), lw))
    p.setBrush(QBrush(T.qc("#15181C")))
    p.drawEllipse(QPointF(cx, cy), r * 0.38, r * 0.38)
    _spec(p, cx - r * 0.30, cy - r * 0.34, r * 0.32, 110)

def _wrench(p, cx, cy, s, k, col):
    """扳手：镀铬钢柄 + 开口头，带高光。"""
    steel = T.qc("#8A939E")
    deg = -0.9
    _shadow(p, cx + s * 0.10, cy + s * 0.52, s * 0.50, s * 0.08, 100)
    p.save()
    p.translate(cx, cy)
    p.rotate(math.degrees(deg))
    # 柄
    hd = QRectF(-s * 0.52, -s * 0.075, s * 1.02, s * 0.15)
    gh = QLinearGradient(hd.topLeft(), hd.bottomLeft())
    gh.setColorAt(0.0, T.f(steel, 1.70))
    gh.setColorAt(0.40, T.f(steel, 1.10))
    gh.setColorAt(1.0, T.f(steel, 0.30))
    p.setPen(QPen(T.f(steel, 0.28), max(0.7, 1.0 * k)))
    p.setBrush(QBrush(gh))
    p.drawRoundedRect(hd, s * 0.07, s * 0.07)
    # 开口头
    head = QPainterPath()
    head.moveTo(s * 0.46, -s * 0.26)
    head.lineTo(s * 0.72, -s * 0.30)
    head.lineTo(s * 0.66, -s * 0.06)
    head.lineTo(s * 0.72, s * 0.30)
    head.lineTo(s * 0.46, s * 0.26)
    head.lineTo(s * 0.56, s * 0.06)
    head.lineTo(s * 0.30, 0)
    head.lineTo(s * 0.56, -s * 0.06)
    head.closeSubpath()
    ghd, _ = _metal(s * 0.55, 0, s * 0.20, s * 0.28, steel)
    p.setBrush(QBrush(ghd))
    p.drawPath(head)
    # 高光
    p.setPen(QPen(T.a(T.qc("#FFFFFF"), 95), max(0.8, 1.2 * k)))
    p.drawLine(QPointF(-s * 0.44, -s * 0.035), QPointF(s * 0.38, -s * 0.035))
    p.restore()

def _jerrycan(p, cx, cy, s, k, col):
    """油桶：平板钢桶 + 提手 + X 压纹，带明暗。"""
    lw = max(0.8, 1.1 * k)
    base = T.qc("#4E5A38")
    w, h = s * 0.34, s * 0.50
    _shadow(p, cx, cy + h * 1.16, w * 1.1, h * 0.20, 110)
    r = QRectF(cx - w, cy - h, w * 2, h * 2)
    gg, _ = _metal(cx, cy, w, h, base)
    p.setPen(QPen(T.f(base, 0.32), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(r, s * 0.06, s * 0.06)
    # X 压纹
    p.setPen(QPen(T.a(T.f(base, 1.5), 90), max(1.0, 1.4 * k)))
    p.drawLine(QPointF(r.left() + r.width() * 0.18, r.top() + r.height() * 0.22),
               QPointF(r.right() - r.width() * 0.18, r.bottom() - r.height() * 0.22))
    p.drawLine(QPointF(r.right() - r.width() * 0.18, r.top() + r.height() * 0.22),
               QPointF(r.left() + r.width() * 0.18, r.bottom() - r.height() * 0.22))
    # 提手
    p.setPen(QPen(T.f(base, 1.3), max(1.0, 1.4 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(cx - s * 0.12, cy - h - s * 0.14, s * 0.24, s * 0.20),
              0, 180 * 16)
    # 加油口
    cap = QRectF(cx + w * 0.34, cy - h - s * 0.05, s * 0.16, s * 0.09)
    p.setPen(QPen(T.f(base, 0.35), max(0.5, 0.8 * k)))
    p.setBrush(QBrush(T.f(base, 1.35)))
    p.drawRoundedRect(cap, s * 0.02, s * 0.02)
    _spec(p, r.left() + w * 0.55, r.top() + h * 0.30, s * 0.10, 110)

def _pipe(p, cx, cy, s, k, col):
    """钢管：圆柱感 + 法兰盘 + 锈迹。"""
    steel = T.qc("#6E7680")
    rust = T.qc("#8A5030")
    _shadow(p, cx, cy + s * 0.22, s * 0.90, s * 0.07, 100)
    # 管身（纵向渐变 = 圆柱）
    body = QRectF(cx - s * 0.88, cy - s * 0.14, s * 1.76, s * 0.28)
    gg = QLinearGradient(body.topLeft(), body.bottomLeft())
    gg.setColorAt(0.0, T.f(steel, 1.55))
    gg.setColorAt(0.28, T.f(steel, 1.30))
    gg.setColorAt(0.62, steel)
    gg.setColorAt(1.0, T.f(steel, 0.30))
    p.setPen(QPen(T.f(steel, 0.26), max(0.7, 1.0 * k)))
    p.setBrush(QBrush(gg))
    p.drawRect(body)
    # 法兰
    for dx in (-0.60, 0.0, 0.60):
        fl = QRectF(cx + s * dx - s * 0.055, cy - s * 0.20, s * 0.11, s * 0.40)
        gf = QLinearGradient(fl.topLeft(), fl.bottomLeft())
        gf.setColorAt(0.0, T.f(steel, 1.60))
        gf.setColorAt(0.55, T.f(steel, 0.95))
        gf.setColorAt(1.0, T.f(steel, 0.28))
        p.setPen(QPen(T.f(steel, 0.26), max(0.5, 0.8 * k)))
        p.setBrush(QBrush(gf))
        p.drawRoundedRect(fl, s * 0.02, s * 0.02)
    # 锈斑
    p.setPen(Qt.PenStyle.NoPen)
    for i, (rx, rr) in enumerate(((-0.36, 0.055), (0.26, 0.042), (0.46, 0.030))):
        p.setBrush(QBrush(T.a(rust, 120)))
        p.drawEllipse(QPointF(cx + s * rx, cy + s * 0.03), s * rr, s * rr * 0.7)

def _radio(p, cx, cy, s, k, col):
    """野战电台：金属机身 + 发光屏幕 + 旋钮。"""
    lw = max(0.9, 1.3 * k)
    base = T.qc("#4E5A48")
    w, h = s * 0.52, s * 0.34
    _shadow(p, cx, cy + h * 1.25, w * 1.1, h * 0.25, 110)
    r = QRectF(cx - w, cy - h, w * 2, h * 2)
    gg, _ = _metal(cx, cy, w, h, base)
    p.setPen(QPen(T.f(base, 0.38), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(r, s * 0.06, s * 0.06)
    # 屏幕（发光）
    scr = QRectF(cx - w + s * 0.10, cy - h + s * 0.10, s * 0.38, s * 0.22)
    gs = QLinearGradient(scr.topLeft(), scr.bottomLeft())
    gs.setColorAt(0.0, T.qc("#8FE8B0"))
    gs.setColorAt(1.0, T.qc("#2E8C58"))
    p.setPen(QPen(T.qc("#0E1F16"), max(0.5, 0.7 * k)))
    p.setBrush(QBrush(gs))
    p.drawRect(scr)
    # 屏幕光晕
    glow = QRadialGradient(scr.center(), s * 0.34)
    glow.setColorAt(0.0, T.a(T.qc("#8FE8B0"), 70))
    glow.setColorAt(1.0, T.a(T.qc("#8FE8B0"), 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(scr.center(), s * 0.34, s * 0.34)
    # 旋钮
    for i in range(2):
        kx = cx + w * 0.58
        ky = cy - h * 0.40 + i * s * 0.28
        p.setPen(QPen(T.f(base, 0.35), max(0.5, 0.7 * k)))
        p.setBrush(QBrush(T.f(base, 1.35)))
        p.drawEllipse(QPointF(kx, ky), s * 0.065, s * 0.065)
        _spec(p, kx - s * 0.02, ky - s * 0.022, s * 0.035, 160)
    # 天线
    p.setPen(QPen(T.qc("#B9C0C9"), max(0.9, 1.2 * k)))
    p.drawLine(QPointF(cx - w * 0.70, cy - h), QPointF(cx - w * 0.95, cy - h * 2.25))

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
    """望远镜：两个圆筒 + 镜片反光 + 连接桥。"""
    lw = max(0.8, 1.2 * k)
    base = T.qc("#3E4448")
    _shadow(p, cx, cy + s * 0.46, s * 0.60, s * 0.09, 105)
    for dx in (-0.25, 0.25):
        r = QRectF(cx + s * dx - s * 0.17, cy - s * 0.36, s * 0.34, s * 0.72)
        gg = QLinearGradient(r.leftTop(), r.rightBottom())
        gg.setColorAt(0.0, T.f(base, 1.75))
        gg.setColorAt(0.42, T.f(base, 1.05))
        gg.setColorAt(1.0, T.f(base, 0.28))
        p.setPen(QPen(T.f(base, 0.28), lw))
        p.setBrush(QBrush(gg))
        p.drawRoundedRect(r, s * 0.10, s * 0.10)
        # 镜片
        lens = QRectF(r.left() + s * 0.04, r.top() + s * 0.05, r.width() - s * 0.08, s * 0.16)
        gl = QLinearGradient(lens.topLeft(), lens.bottomLeft())
        gl.setColorAt(0.0, T.qc("#A8D8F0"))
        gl.setColorAt(0.55, T.qc("#3A6E90"))
        gl.setColorAt(1.0, T.qc("#12202A"))
        p.setPen(QPen(T.qc("#0E1014"), max(0.5, 0.8 * k)))
        p.setBrush(QBrush(gl))
        p.drawEllipse(lens)
        _spec(p, lens.center().x() - s * 0.04, lens.center().y() - s * 0.02,
               s * 0.055, 180)
    # 连接桥
    br = QRectF(cx - s * 0.10, cy - s * 0.08, s * 0.20, s * 0.17)
    gb, _ = _metal(cx, cy, s * 0.10, s * 0.085, base)
    p.setPen(QPen(T.f(base, 0.28), max(0.5, 0.8 * k)))
    p.setBrush(QBrush(gb))
    p.drawRoundedRect(br, s * 0.03, s * 0.03)

def _map(p, cx, cy, s, k, col):
    """作战地图：做旧纸 + 折痕 + 红线标注。"""
    paper = T.qc("#C8B88A")
    _shadow(p, cx, cy + s * 0.46, s * 0.66, s * 0.09, 105)
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
    gg = QLinearGradient(QPointF(cx - s * 0.6, cy - s * 0.5),
                         QPointF(cx + s * 0.6, cy + s * 0.5))
    gg.setColorAt(0.0, T.f(paper, 1.18))
    gg.setColorAt(0.48, paper)
    gg.setColorAt(1.0, T.f(paper, 0.62))
    p.setPen(QPen(T.qc("#6A5A3A"), max(0.7, 1.0 * k)))
    p.setBrush(QBrush(gg))
    p.drawPath(path)
    # 折痕
    p.setPen(QPen(T.a(T.qc("#6A5A3A"), 130), max(0.5, 0.8 * k)))
    p.drawLine(QPointF(cx - s * 0.20, cy - s * 0.46), QPointF(cx - s * 0.20, cy + s * 0.42))
    p.drawLine(QPointF(cx + s * 0.20, cy - s * 0.42), QPointF(cx + s * 0.20, cy + s * 0.46))
    # 红线标注（进攻箭头）
    p.setPen(QPen(T.a(T.qc("#C03020"), 200), max(0.9, 1.3 * k)))
    p.drawLine(QPointF(cx - s * 0.34, cy + s * 0.18), QPointF(cx + s * 0.30, cy - s * 0.12))
    p.drawLine(QPointF(cx + s * 0.30, cy - s * 0.12), QPointF(cx + s * 0.16, cy - s * 0.14))
    p.drawLine(QPointF(cx + s * 0.30, cy - s * 0.12), QPointF(cx + s * 0.24, cy + s * 0.02))

def _flare(p, cx, cy, s, k, col):
    """信号弹：弹体 + 强光 + 拖尾烟。"""
    # 光晕
    gl = QRadialGradient(QPointF(cx, cy - s * 0.24), s * 0.72)
    gl.setColorAt(0.0, T.a(T.qc("#FFF0B0"), 220))
    gl.setColorAt(0.35, T.a(T.qc("#FFB020"), 110))
    gl.setColorAt(1.0, T.a(T.qc("#FF8A00"), 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(gl))
    p.drawEllipse(QPointF(cx, cy - s * 0.24), s * 0.72, s * 0.72)
    # 弹体
    bd = QRectF(cx - s * 0.075, cy - s * 0.10, s * 0.15, s * 0.56)
    gb = QLinearGradient(bd.topLeft(), bd.rightTop())
    gb.setColorAt(0.0, T.qc("#8C2E1E"))
    gb.setColorAt(0.40, T.qc("#D85030"))
    gb.setColorAt(1.0, T.qc("#5A1A10"))
    p.setPen(QPen(T.qc("#2A0E08"), max(0.5, 0.8 * k)))
    p.setBrush(QBrush(gb))
    p.drawRoundedRect(bd, s * 0.03, s * 0.03)
    # 弹头火光
    p.setBrush(QBrush(T.qc("#FFF6D0")))
    p.drawEllipse(QPointF(cx, cy - s * 0.22), s * 0.09, s * 0.11)
    # 拖尾烟
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(4):
        yy = cy + s * (0.12 + i * 0.14)
        rr = s * (0.07 - i * 0.012)
        p.setBrush(QBrush(T.a(T.qc("#9AA0AA"), 90 - i * 18)))
        p.drawEllipse(QPointF(cx + (i % 2) * s * 0.03, yy), rr, rr)

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
    """医疗箱：白漆金属箱 + 红十字 + 提手 + 明暗。"""
    lw = max(0.8, 1.2 * k)
    base = T.qc("#D8D4C8")
    _shadow(p, cx, cy + s * 0.50, s * 0.56, s * 0.09, 115)
    r = QRectF(cx - s * 0.48, cy - s * 0.40, s * 0.96, s * 0.86)
    gg, _ = _metal(cx, cy, s * 0.48, s * 0.43, base)
    p.setPen(QPen(T.qc("#6A6458"), lw))
    p.setBrush(QBrush(gg))
    p.drawRoundedRect(r, s * 0.08, s * 0.08)
    # 提手
    p.setPen(QPen(T.qc("#4E4A42"), max(1.2, 1.7 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(cx - s * 0.18, r.top() - s * 0.16, s * 0.36, s * 0.26),
              0, 180 * 16)
    # 红十字
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(T.qc("#C02820")))
    p.drawRect(QRectF(cx - s * 0.085, cy - s * 0.26, s * 0.17, s * 0.56))
    p.drawRect(QRectF(cx - s * 0.27, cy - s * 0.075, s * 0.54, s * 0.17))
    _spec(p, r.left() + s * 0.14, r.top() + s * 0.12, s * 0.10, 120)

def _flag(p, cx, cy, s, k, col):
    """军旗：旗杆 + 飘动旗面（有褶皱明暗）。"""
    lw = max(0.9, 1.3 * k)
    # 旗杆
    pole = QRectF(cx - s * 0.56, cy - s * 0.56, s * 0.075, s * 1.10)
    gp = QLinearGradient(pole.topLeft(), pole.rightTop())
    gp.setColorAt(0.0, T.qc("#5A5048"))
    gp.setColorAt(0.42, T.qc("#B0A090"))
    gp.setColorAt(1.0, T.qc("#3A342C"))
    p.setPen(QPen(T.qc("#2A241E"), max(0.5, 0.8 * k)))
    p.setBrush(QBrush(gp))
    p.drawRect(pole)
    # 旗杆顶
    p.setBrush(QBrush(T.qc("#C0A050")))
    p.drawEllipse(QPointF(cx - s * 0.52, cy - s * 0.60), s * 0.055, s * 0.055)
    # 旗面（波浪）
    fl = QPainterPath()
    fl.moveTo(cx - s * 0.49, cy - s * 0.52)
    fl.cubicTo(cx - s * 0.10, cy - s * 0.60, cx + s * 0.14, cy - s * 0.36,
               cx + s * 0.52, cy - s * 0.40)
    fl.lineTo(cx + s * 0.34, cy - s * 0.10)
    fl.lineTo(cx + s * 0.52, cy + s * 0.18)
    fl.cubicTo(cx + s * 0.14, cy + s * 0.14, cx - s * 0.10, cy + s * 0.02,
               cx - s * 0.49, cy + s * 0.04)
    fl.closeSubpath()
    gf = QLinearGradient(QPointF(cx - s * 0.5, cy - s * 0.5),
                         QPointF(cx + s * 0.5, cy + s * 0.2))
    gf.setColorAt(0.0, T.f(col, 1.25))
    gf.setColorAt(0.45, col)
    gf.setColorAt(1.0, T.f(col, 0.45))
    p.setPen(QPen(T.f(col, 0.45), max(0.7, 1.0 * k)))
    p.setBrush(QBrush(gf))
    p.drawPath(fl)
    # 褶皱
    p.setPen(QPen(T.a(T.f(col, 0.40), 130), max(0.6, 0.9 * k)))
    p.drawLine(QPointF(cx - s * 0.20, cy - s * 0.50), QPointF(cx - s * 0.14, cy - s * 0.04))
    p.drawLine(QPointF(cx + s * 0.12, cy - s * 0.42), QPointF(cx + s * 0.20, cy + s * 0.04))

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
