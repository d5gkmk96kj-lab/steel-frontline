#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面插图渲染：把 core.cardart 的构图画成军事蚀刻风插图。

风格取向
--------
* **矢量线稿**，不用位图 —— 卡图区只有 150x62，位图缩下来必糊。
* 深色底 + 冷灰线 + 主色点缀，像老式技术手册里的剖面图。
* 每个母题都是参数化的，尺寸随卡片缩放，任何分辨率都锐利。

所有函数都接受 ``k``（卡片缩放系数），内部一切尺寸都乘 k。
"""

from __future__ import annotations

import math
from typing import Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QLinearGradient, QPainterPath, QPen,
                         QRadialGradient)

from core import cardart as CA

from . import qtheme as T


# ---------------------------------------------------------------- 调色板 --
def _ink(tcol: QColor, comp: CA.Composition) -> QColor:
    """线稿主色：流派色压暗一点，稀有度越高越亮。"""
    return T.f(tcol, 0.85 * comp.accent)


def _paper(rect: QRectF, comp: CA.Composition) -> Tuple[QColor, QColor]:
    """插图底：由上到下的暗色渐变。"""
    top = T.qc("#171A1F")
    bot = T.mix(T.qc("#0C0E11"), T.qc("#241A14"), 0.35)
    if comp.band == "gold":
        top = T.qc("#1E1A12")
    elif comp.band == "crimson":
        top = T.qc("#20120F")
    elif comp.band == "bronze":
        top = T.qc("#181610")
    return top, bot


# ---------------------------------------------------------------- 通用件 --
def _grid(p, rect: QRectF, k: float, col: QColor) -> None:
    """细网格：技术图纸的底纹。"""
    p.save()
    p.setPen(QPen(T.a(col, 26), max(0.6, 0.7 * k)))
    step = rect.width() / 12.0
    x = rect.left() + step
    while x < rect.right() - 2:
        p.drawLine(QPointF(x, rect.top() + 2), QPointF(x, rect.bottom() - 2))
        x += step
    step = rect.height() / 5.0
    y = rect.top() + step
    while y < rect.bottom() - 2:
        p.drawLine(QPointF(rect.left() + 2, y), QPointF(rect.right() - 2, y))
        y += step
    p.restore()


def _corner_ticks(p, rect: QRectF, k: float, col: QColor) -> None:
    """四角刻度：像瞄具/相机取景框。"""
    p.save()
    p.setPen(QPen(T.a(col, 150), max(1.0, 1.1 * k)))
    L = min(rect.width(), rect.height()) * 0.16
    for cx, cy, dx, dy in (
            (rect.left(), rect.top(), 1, 1),
            (rect.right(), rect.top(), -1, 1),
            (rect.left(), rect.bottom(), 1, -1),
            (rect.right(), rect.bottom(), -1, -1)):
        p.drawLine(QPointF(cx + 3 * k, cy + 3 * k),
                   QPointF(cx + 3 * k + L * dx, cy + 3 * k))
        p.drawLine(QPointF(cx + 3 * k, cy + 3 * k),
                   QPointF(cx + 3 * k, cy + 3 * k + L * dy))
    p.restore()


def _scanlines(p, rect: QRectF, k: float, col: QColor) -> None:
    """极淡的横向扫描线，增加"印刷品"质感。"""
    p.save()
    p.setPen(QPen(T.a(col, 12), max(0.5, 0.6 * k)))
    y = rect.top() + 2 * k
    while y < rect.bottom():
        p.drawLine(QPointF(rect.left() + 1, y), QPointF(rect.right() - 1, y))
        y += 3.2 * k
    p.restore()


# ---------------------------------------------------------------- 主图案 --
def _rifle(p, cx: float, cy: float, s: float, k: float, col: QColor,
           rng: int) -> None:
    """步枪侧视剖面：枪托 + 机匣 + 护木 + 枪管 + 弹匣 + 准星。

    画粗一点（之前线太细，缩到卡面尺寸后看着像一把梳子）。
    """
    lw = max(1.6, 2.4 * k)
    p.setBrush(QBrush(T.a(col, 60)))

    # —— 枪托（左侧梯形）
    stock = QPainterPath()
    stock.moveTo(cx - s * 1.62, cy - s * 0.30)
    stock.lineTo(cx - s * 0.80, cy - s * 0.22)
    stock.lineTo(cx - s * 0.80, cy + s * 0.26)
    stock.lineTo(cx - s * 1.50, cy + s * 0.42)
    stock.closeSubpath()
    p.setPen(QPen(col, lw))
    p.drawPath(stock)

    # —— 机匣（中段矩形）
    rec = QRectF(cx - s * 0.84, cy - s * 0.26, s * 0.78, s * 0.50)
    p.setBrush(QBrush(T.a(col, 85)))
    p.drawRoundedRect(rec, s * 0.08, s * 0.08)

    # —— 护木 + 枪管
    p.setBrush(QBrush(T.a(col, 70)))
    wood = QRectF(cx + s * 0.02, cy - s * 0.17, s * 0.86, s * 0.34)
    p.drawRoundedRect(wood, s * 0.07, s * 0.07)
    p.setPen(QPen(col, max(2.0, 3.0 * k)))
    p.drawLine(QPointF(cx + s * 0.86, cy - s * 0.02),
               QPointF(cx + s * 1.62, cy - s * 0.02))

    # —— 弹匣（下挂弧形）
    mag = QPainterPath()
    mag.moveTo(cx - s * 0.28, cy + s * 0.22)
    mag.lineTo(cx + s * 0.06, cy + s * 0.22)
    mag.lineTo(cx - s * 0.04, cy + s * 0.86)
    mag.lineTo(cx - s * 0.42, cy + s * 0.80)
    mag.closeSubpath()
    p.setPen(QPen(col, lw))
    p.setBrush(QBrush(T.a(col, 75)))
    p.drawPath(mag)

    # —— 握把
    grip = QPainterPath()
    grip.moveTo(cx - s * 0.62, cy + s * 0.22)
    grip.lineTo(cx - s * 0.40, cy + s * 0.22)
    grip.lineTo(cx - s * 0.52, cy + s * 0.72)
    grip.lineTo(cx - s * 0.76, cy + s * 0.66)
    grip.closeSubpath()
    p.drawPath(grip)

    # —— 准星（枪口上方）
    p.setPen(QPen(col, max(1.2, 1.7 * k)))
    p.drawLine(QPointF(cx + s * 1.34, cy - s * 0.02),
               QPointF(cx + s * 1.34, cy - s * 0.34))
    p.drawLine(QPointF(cx + s * 1.18, cy - s * 0.34),
               QPointF(cx + s * 1.50, cy - s * 0.34))

    # —— 细节：机匣上的散热孔
    p.setPen(QPen(T.a(col, 140), max(0.7, 0.9 * k)))
    for i in range(3):
        yy = cy - s * 0.10 + i * s * 0.14
        p.drawLine(QPointF(cx - s * 0.72, yy), QPointF(cx - s * 0.12, yy))


def _sandbags(p, cx: float, cy: float, s: float, k: float, col: QColor,
              rng: int) -> None:
    """沙袋工事：三层错缝堆叠 + 铁丝网。"""
    p.setBrush(QBrush(T.a(col, 40)))
    p.setPen(QPen(col, max(0.9, 1.1 * k)))
    rows = ((0, 1.06), (1, 0.88), (2, 0.70))
    for row, w in rows:
        n = 3 if row < 2 else 2
        y = cy + s * (0.34 - row * 0.30)
        span = s * w * 1.9
        for i in range(n):
            x = cx - span / 2 + (span / (n - 1)) * i if n > 1 else cx
            r = QRectF(x - s * 0.34, y - s * 0.14, s * 0.68, s * 0.30)
            p.drawRoundedRect(r, s * 0.12, s * 0.12)
    # 铁丝网
    p.setPen(QPen(T.a(col, 130), max(0.6, 0.8 * k)))
    for i in range(4):
        x = cx - s * 0.9 + i * s * 0.6
        p.drawLine(QPointF(x, cy - s * 0.52), QPointF(x, cy + s * 0.10))


def _fuel_drum(p, cx: float, cy: float, s: float, k: float, col: QColor,
               rng: int) -> None:
    """油桶：桶身 + 两道箍 + 顶盖椭圆。"""
    w, h = s * 0.62, s * 1.02
    r = QRectF(cx - w, cy - h / 2, w * 2, h)
    p.setBrush(QBrush(T.a(col, 45)))
    p.setPen(QPen(col, max(1.0, 1.3 * k)))
    p.drawRoundedRect(r, s * 0.10, s * 0.10)
    # 箍
    p.setPen(QPen(T.a(col, 190), max(0.8, 1.0 * k)))
    for fy in (0.30, 0.68):
        y = r.top() + h * fy
        p.drawLine(QPointF(r.left() + 1, y), QPointF(r.right() - 1, y))
    # 顶盖
    p.setBrush(QBrush(T.a(col, 80)))
    p.drawEllipse(QRectF(r.left(), r.top() - h * 0.10, w * 2, h * 0.20))
    # 斜向高光
    p.setPen(QPen(T.a(col, 90), max(0.7, 0.9 * k)))
    p.drawLine(QPointF(cx - w * 0.4, r.bottom() - h * 0.12),
               QPointF(cx + w * 0.2, r.top() + h * 0.14))


def _flame(p, cx: float, cy: float, s: float, k: float, col: QColor,
           rng: int) -> None:
    """火焰：三层嵌套火舌 + 余烬点。"""
    layers = ((1.00, 60), (0.68, 110), (0.38, 190))
    for scale, alpha in layers:
        w = s * 0.92 * scale
        h = s * 1.32 * scale
        path = QPainterPath()
        path.moveTo(cx, cy - h * 0.95)
        path.cubicTo(cx + w * 0.95, cy - h * 0.30,
                     cx + w * 0.70, cy + h * 0.55,
                     cx, cy + h * 0.62)
        path.cubicTo(cx - w * 0.70, cy + h * 0.55,
                     cx - w * 0.95, cy - h * 0.30,
                     cx, cy - h * 0.95)
        p.setBrush(QBrush(T.a(T.f(col, 1.30), alpha)))
        p.setPen(QPen(T.a(col, min(255, alpha + 50)), max(0.7, 0.9 * k)))
        p.drawPath(path)
    # 余烬
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(5):
        ex = cx + ((rng >> (i * 2)) % 100 - 50) / 100.0 * s * 1.5
        ey = cy - s * (0.9 + ((rng >> (i * 3)) % 60) / 100.0 * 0.7)
        p.setBrush(QBrush(T.a(T.f(col, 1.4), 150)))
        p.drawEllipse(QPointF(ex, ey), 1.1 * k, 1.1 * k)


def _radio(p, cx: float, cy: float, s: float, k: float, col: QColor,
           rng: int) -> None:
    """野战电台：机身 + 天线 + 频率刻度 + 声波。"""
    w, h = s * 0.86, s * 0.62
    r = QRectF(cx - w, cy - h * 0.1, w * 2, h)
    p.setBrush(QBrush(T.a(col, 45)))
    p.setPen(QPen(col, max(1.0, 1.3 * k)))
    p.drawRoundedRect(r, s * 0.08, s * 0.08)
    # 屏幕
    p.setBrush(QBrush(T.a(col, 120)))
    p.drawRect(QRectF(r.left() + w * 0.12, r.top() + h * 0.14,
                      w * 0.42, h * 0.30))
    # 旋钮
    p.setBrush(QBrush(T.a(col, 90)))
    for i in range(2):
        p.drawEllipse(QPointF(r.left() + w * 0.75,
                              r.top() + h * (0.28 + i * 0.42)),
                      s * 0.11, s * 0.11)
    # 天线
    p.setPen(QPen(col, max(1.0, 1.3 * k)))
    p.drawLine(QPointF(r.left() + w * 0.3, r.top()),
               QPointF(r.left() + w * 0.06, r.top() - h * 1.55))
    # 声波
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(T.a(col, 140), max(0.7, 0.9 * k)))
    for i, rad in enumerate((0.42, 0.66, 0.90)):
        p.drawArc(QRectF(cx + s * 0.30 - s * rad, cy - s * rad,
                         s * rad * 2, s * rad * 2), -55 * 16, 110 * 16)


# ---------------------------------------------------------------- 装饰件 --
def _bullet_holes(p, rect: QRectF, k: float, col: QColor, n: int,
                  rng: int) -> None:
    """弹孔：暗心 + 亮边 + 放射裂纹。"""
    p.setPen(QPen(T.a(col, 90), max(0.6, 0.7 * k)))
    for i in range(n):
        hx = rect.left() + rect.width() * (0.12 + ((rng >> (i * 4)) % 76) / 100.0)
        hy = rect.top() + rect.height() * (0.15 + ((rng >> (i * 5)) % 70) / 100.0)
        rr = (1.3 + ((rng >> (i * 6)) % 10) / 10.0) * k
        p.setBrush(QBrush(T.a(T.Q_BLACK, 200)))
        p.drawEllipse(QPointF(hx, hy), rr, rr)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(hx, hy), rr * 1.9, rr * 1.9)


def _sight_ticks(p, rect: QRectF, k: float, col: QColor, n: int,
                 rng: int) -> None:
    """瞄具刻度：右侧竖排短刻度。"""
    p.setPen(QPen(T.a(col, 120), max(0.6, 0.8 * k)))
    x = rect.right() - 7 * k
    for i in range(n):
        y = rect.top() + rect.height() * (0.18 + i * 0.16)
        ln = (5.0 if i % 2 == 0 else 3.0) * k
        p.drawLine(QPointF(x, y), QPointF(x - ln, y))


def _smoke(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """烟：几团半透明圆 + 淡边。"""
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(n):
        sx = rect.left() + rect.width() * (0.55 + ((rng >> (i * 3)) % 40) / 100.0)
        sy = rect.bottom() - rect.height() * (0.10 + ((rng >> (i * 4)) % 45) / 100.0)
        rr = (4.0 + ((rng >> (i * 5)) % 40) / 10.0) * k
        p.setBrush(QBrush(T.a(T.qc("#B9BDC4"), 26)))
        p.drawEllipse(QPointF(sx, sy), rr, rr * 0.85)


def _wire(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """铁丝网：交叉锯齿线。"""
    p.setPen(QPen(T.a(col, 110), max(0.55, 0.7 * k)))
    y0 = rect.bottom() - 9 * k
    x = rect.left() + 4 * k
    up = True
    while x < rect.right() - 4 * k:
        nx = x + 5.0 * k
        p.drawLine(QPointF(x, y0 + (2.4 * k if up else 0)),
                   QPointF(nx, y0 + (0 if up else 2.4 * k)))
        up = not up
        x = nx


def _rivets(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """铆钉：沿左右边一列小圆。"""
    p.setPen(Qt.PenStyle.NoPen)
    for side in (0, 1):
        x = rect.left() + 4.5 * k if side == 0 else rect.right() - 4.5 * k
        for i in range(min(n, 3)):
            y = rect.top() + rect.height() * (0.25 + i * 0.26)
            p.setBrush(QBrush(T.a(col, 130)))
            p.drawEllipse(QPointF(x, y), 1.25 * k, 1.25 * k)
            p.setBrush(QBrush(T.a(T.Q_BLACK, 110)))
            p.drawEllipse(QPointF(x + 0.4 * k, y + 0.4 * k), 0.5 * k, 0.5 * k)


def _trench(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """战壕线：底部起伏折线。"""
    p.setPen(QPen(T.a(col, 100), max(0.7, 0.9 * k)))
    path = QPainterPath()
    path.moveTo(rect.left() + 2, rect.bottom() - 3 * k)
    steps = 8
    for i in range(steps + 1):
        x = rect.left() + 2 + (rect.width() - 4) * i / steps
        y = rect.bottom() - 3 * k - (3.0 if i % 2 else 0) * k
        path.lineTo(x, y)
    p.drawPath(path)


def _gears(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """齿轮：小圆 + 齿。"""
    for i in range(n):
        gx = rect.left() + rect.width() * (0.16 + ((rng >> (i * 3)) % 30) / 100.0)
        gy = rect.top() + rect.height() * (0.22 + ((rng >> (i * 4)) % 55) / 100.0)
        rr = (3.0 + ((rng >> (i * 5)) % 20) / 10.0) * k
        p.setPen(QPen(T.a(col, 120), max(0.55, 0.7 * k)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(gx, gy), rr, rr)
        for t in range(6):
            ang = t * math.pi / 3
            p.drawLine(QPointF(gx + math.cos(ang) * rr, gy + math.sin(ang) * rr),
                       QPointF(gx + math.cos(ang) * rr * 1.45,
                               gy + math.sin(ang) * rr * 1.45))


def _cables(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """电缆：两条下垂曲线。"""
    p.setPen(QPen(T.a(col, 105), max(0.6, 0.8 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(min(n, 2)):
        y = rect.top() + rect.height() * (0.18 + i * 0.12)
        path = QPainterPath()
        path.moveTo(rect.left() + 3, y)
        path.cubicTo(rect.left() + rect.width() * 0.35, y + 7 * k,
                     rect.left() + rect.width() * 0.65, y + 7 * k,
                     rect.right() - 3, y)
        p.drawPath(path)


def _crate(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """补给箱：方框 + 交叉木条。"""
    for i in range(min(n, 1)):
        bx = rect.left() + rect.width() * 0.10
        by = rect.top() + rect.height() * 0.52
        bw, bh = 16 * k, 12 * k
        p.setPen(QPen(T.a(col, 115), max(0.6, 0.8 * k)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(bx, by, bw, bh))
        p.drawLine(QPointF(bx, by), QPointF(bx + bw, by + bh))
        p.drawLine(QPointF(bx + bw, by), QPointF(bx, by + bh))


def _gas_cloud(p, rect: QRectF, k: float, col: QColor, n: int,
               rng: int) -> None:
    """毒气云：绿色团块。"""
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(n):
        gx = rect.left() + rect.width() * (0.20 + ((rng >> (i * 3)) % 60) / 100.0)
        gy = rect.top() + rect.height() * (0.25 + ((rng >> (i * 4)) % 45) / 100.0)
        rr = (3.5 + ((rng >> (i * 5)) % 30) / 10.0) * k
        p.setBrush(QBrush(T.a(T.qc("#7FBF6A"), 34)))
        p.drawEllipse(QPointF(gx, gy), rr, rr * 0.8)


def _radiation(p, rect: QRectF, k: float, col: QColor, n: int,
               rng: int) -> None:
    """辐射标：三叶。"""
    cx = rect.right() - 9 * k
    cy = rect.top() + 9 * k
    rr = 5.0 * k
    p.setPen(QPen(T.a(T.qc("#C9E06A"), 170), max(0.6, 0.8 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), rr * 0.30, rr * 0.30)
    for t in range(3):
        base = t * 120 - 90
        p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2),
                  int(base * 16), int(45 * 16))


def _embers(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """余烬点。"""
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(n * 2):
        ex = rect.left() + rect.width() * ((rng >> (i * 3)) % 100) / 100.0
        ey = rect.top() + rect.height() * ((rng >> (i * 5)) % 100) / 100.0
        p.setBrush(QBrush(T.a(T.f(col, 1.35), 120)))
        p.drawEllipse(QPointF(ex, ey), 0.9 * k, 0.9 * k)


def _antenna(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """天线塔：三角桁架。"""
    p.setPen(QPen(T.a(col, 110), max(0.55, 0.7 * k)))
    ax = rect.right() - 10 * k
    ay = rect.top() + 3 * k
    p.drawLine(QPointF(ax, ay), QPointF(ax - 5 * k, rect.bottom() - 4 * k))
    p.drawLine(QPointF(ax, ay), QPointF(ax + 5 * k, rect.bottom() - 4 * k))
    for i in range(3):
        yy = ay + (rect.bottom() - 4 * k - ay) * (i + 1) / 4.0
        half = 5 * k * (i + 1) / 4.0
        p.drawLine(QPointF(ax - half, yy), QPointF(ax + half, yy))


def _troops(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """部队剪影：几个小人形。"""
    p.setPen(QPen(T.a(col, 105), max(0.55, 0.75 * k)))
    for i in range(min(n, 3)):
        tx = rect.left() + 8 * k + i * 7 * k
        ty = rect.bottom() - 8 * k
        p.drawEllipse(QPointF(tx, ty - 6 * k), 1.7 * k, 1.7 * k)
        p.drawLine(QPointF(tx, ty - 4.2 * k), QPointF(tx, ty))
        p.drawLine(QPointF(tx - 2.4 * k, ty - 1.2 * k), QPointF(tx + 2.4 * k, ty - 1.2 * k))


def _signal(p, rect: QRectF, k: float, col: QColor, n: int, rng: int) -> None:
    """信号波：几道渐弱弧线。"""
    p.setPen(QPen(T.a(col, 120), max(0.55, 0.7 * k)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    cx = rect.left() + 9 * k
    cy = rect.top() + 9 * k
    for i, rr in enumerate((4.0, 6.5, 9.0)):
        p.drawArc(QRectF(cx - rr * k, cy - rr * k, rr * 2 * k, rr * 2 * k),
                  -40 * 16, 80 * 16)


#: 装饰件分发表
_DECOR = {
    "bullet_holes": _bullet_holes,
    "sight_ticks": _sight_ticks,
    "smoke": _smoke,
    "wire": _wire,
    "rivets": _rivets,
    "trench": _trench,
    "gears": _gears,
    "cables": _cables,
    "crate": _crate,
    "gas_cloud": _gas_cloud,
    "radiation": _radiation,
    "embers": _embers,
    "antenna": _antenna,
    "troops": _troops,
    "signal": _signal,
}

_MOTIF = {
    "rifle": _rifle,
    "sandbags": _sandbags,
    "fuel_drum": _fuel_drum,
    "flame": _flame,
    "radio": _radio,
}


# ---------------------------------------------------------------- 入口 --
def paint(painter, rect: QRectF, card: dict, tcol: QColor, k: float) -> None:
    """把一张卡的插图完整画到 rect 里。"""
    comp = CA.compose(card)
    col = _ink(tcol, comp)

    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, True)

    # 底：渐变 + 网格 + 扫描线
    top, bot = _paper(rect, comp)
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, top)
    g.setColorAt(1.0, bot)
    T.fill_round(painter, rect, 5 * k, QBrush(g))
    _grid(painter, rect, k, col)
    _scanlines(painter, rect, k, col)

    # 主图案：限制在插图区内（否则步枪/弹匣会画到框外）
    painter.save()
    painter.setClipRect(rect)

    # 主图案只画**一个**（不再是并排复制 —— 复制出来像一排梳子）。
    # count 改为表达"数量感"：在图案周围加弹着点 / 重复刻痕。
    comp_n = max(1, int(comp.count))
    cx0 = rect.center().x()
    cy0 = rect.center().y() - rect.height() * 0.04
    s = min(rect.height() * 0.42, rect.width() * 0.26)
    fn = _MOTIF.get(comp.motif, _rifle)
    painter.save()
    painter.translate(cx0, cy0)
    painter.rotate(comp.angle)
    painter.translate(-cx0, -cy0)
    try:
        fn(painter, cx0, cy0, s, k, col, comp.seed)
    except Exception:
        pass
    painter.restore()

    # 数量感：在主图案左右两侧加"重复计数"刻痕
    if comp_n > 1:
        pcol = T.a(col, 165)
        painter.setPen(QPen(pcol, max(0.8, 1.0 * k)))
        for i in range(comp_n - 1):
            xx = rect.left() + rect.width() * (0.08 + i * 0.045)
            painter.drawLine(QPointF(xx, rect.top() + rect.height() * 0.30),
                             QPointF(xx, rect.bottom() - rect.height() * 0.30))
        # 右侧对称
        for i in range(comp_n - 1):
            xx = rect.right() - rect.width() * (0.08 + i * 0.045)
            painter.drawLine(QPointF(xx, rect.top() + rect.height() * 0.30),
                             QPointF(xx, rect.bottom() - rect.height() * 0.30))

    painter.restore()      # 解除主图案的裁剪

    # 装饰：密度越高画越多
    dn = 1 + int(round(comp.density * 4))
    for j, m in enumerate(comp.motifs):
        dfn = _DECOR.get(m)
        if dfn is None:
            continue
        try:
            dfn(painter, rect, k, col, max(1, dn - j), comp.seed >> (j * 4 + 3))
        except Exception:
            pass

    # 取景框 + 边框
    _corner_ticks(painter, rect, k, col)
    T.stroke_round(painter, rect, 5 * k, T.a(T.Q_BLACK, 90), max(0.8, 1.0 * k))
    painter.restore()
