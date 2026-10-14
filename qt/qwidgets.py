"""钢铁战线 Steel Frontline — Qt 可复用自绘控件 (qwidgets.py)
================================================================
全部基于 ``QPainter`` 抗锯齿绘制，配 ``QPropertyAnimation`` 做平滑动画。

控件清单
--------
* :class:`Battlefield`   —— 焦土战场背景（渐变 + 地平线废墟 + 硝烟粒子 + 曳光弹）
* :class:`HpBar`         —— 缓动血条（延迟残影）
* :class:`CoverBar`      —— 掩体条
* :class:`SupplyOrb`     —— 补给能量球（环形进度 + 脉冲）
* :class:`IntentBadge`   —— 敌人意图徽标
* :class:`BuffChip`      —— buff/debuff 小图标 + 层数
* :class:`CardView`      —— 卡牌（做旧纸张/铆接钢板 + 稀有度辉光 + 悬停上浮）
* :class:`RelicView`     —— 勋章 / 装备
* :class:`UnitArt`       —— 单位立绘剪影（坦克 / 碉堡 / 步兵 / 飞机 / 要塞 / 火炮 / 军官）
* :class:`FloatText`     —— 伤害飘字（QPropertyAnimation 上升淡出）
* :class:`ShakeWidget`   —— 屏幕震动混入
* :class:`IconButton`    —— 军事符号图标按钮
* :class:`UnitCanvas`    —— 可点击的单位面板（敌人可选中）
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from . import qtheme as T

# 装饰性动画的统一帧长。
# 说明：背景硝烟/粒子这类动画不需要 60fps；而**每个**自绘控件各起一个
# 定时器会让事件循环饱和（实测 10 个 16ms 定时器 → 主界面反而掉到 13fps）。
# 30fps 是观感与开销的平衡点；卡牌交互动画由 QPropertyAnimation 驱动，
# 不受此值限制，仍然保持顺滑。
_FRAME_MS = 16


# =====================================================================
# 通用工具
# =====================================================================


def _elide(painter: QPainter, s: str, fnt: QFont, width: float) -> str:
    fm = QFontMetricsF(fnt)
    if fm.horizontalAdvance(s) <= width:
        return s
    out = s
    while out and fm.horizontalAdvance(out + "…") > width:
        out = out[:-1]
    return out + "…" if out else ""


def wrap_text(painter: QPainter, s: str, fnt: QFont, width: float,
              max_lines: int = 99) -> List[str]:
    """按像素宽度手动折行（中文逐字，英文按词）—— 保证卡面排版精确可控。"""
    fm = QFontMetricsF(fnt)
    lines: List[str] = []
    for para in str(s).split("\n"):
        cur = ""
        i = 0
        while i < len(para):
            ch = para[i]
            # 英文单词整体处理
            if ch.isascii() and (ch.isalnum() or ch in "-_'"):
                j = i
                while j < len(para) and para[j].isascii() and (para[j].isalnum() or para[j] in "-_'"):
                    j += 1
                chunk = para[i:j]
                i = j
            else:
                chunk = ch
                i += 1
            if fm.horizontalAdvance(cur + chunk) > width and cur:
                lines.append(cur)
                cur = chunk
            else:
                cur += chunk
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = _elide(painter, lines[-1] + "…", fnt, width)
    return lines


def draw_text_block(painter: QPainter, rect: QRectF, s: str, fnt: QFont,
                    color: QColor, align=Qt.AlignmentFlag.AlignLeft,
                    max_lines: int = 99, line_gap: float = 2.0,
                    center_v: bool = False) -> float:
    """在矩形内绘制折行文本，返回占用高度。"""
    painter.setFont(fnt)
    fm = QFontMetricsF(fnt)
    lh = fm.height() + line_gap
    lines = wrap_text(painter, s, fnt, rect.width(), max_lines)
    total = len(lines) * lh
    y = rect.top()
    if center_v:
        y = rect.top() + max(0.0, (rect.height() - total) / 2)
    painter.setPen(QPen(color))
    for ln in lines:
        if y > rect.bottom() + lh:
            break
        lr = QRectF(rect.left(), y, rect.width(), lh)
        painter.drawText(lr, int(align) | int(Qt.AlignmentFlag.AlignVCenter),
                         T.tr(ln))
        y += lh
    return total


# =====================================================================
# 战场背景：焦土渐变 + 远景地平线废墟 + 硝烟粒子 + 曳光弹
# =====================================================================


class Battlefield(QWidget):
    """全屏战场背景。纯装饰，不吃鼠标事件。

    层序：焦土天空渐变 → 地平线余晖 → 远景废墟剪影 → 铁丝网 →
         地面 → 弹坑 → 硝烟粒子（漂移） → 曳光弹（偶发）
    """

    def __init__(self, parent: Optional[QWidget] = None, dust: int = 46,
                 seed: int = 20241, intensity: float = 1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._seed = seed
        self._intensity = intensity
        self._t = 0.0
        self._particles: List[List[float]] = []
        self._tracers: List[List[float]] = []
        self._ruins: List[Tuple[float, float, float, float]] = []
        self._craters: List[Tuple[float, float, float]] = []
        self._dust_n = dust
        self._build()

        self._cache_pm = None
        self._cache_key = None
        self._smoke_pm = None
        self._last_t = time.monotonic()

        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- 初始化 -----------------------------------------------------------
    def _build(self) -> None:
        import random as _r
        rng = _r.Random(self._seed)

        # 远景废墟：底部对齐地平线，高低错落的方块与塔
        self._ruins = []
        x = -40.0
        while x < 1.35:
            w = rng.uniform(0.018, 0.055)
            h = rng.uniform(0.03, 0.14)
            self._ruins.append((x, w, h, rng.uniform(0, 1)))
            x += w + rng.uniform(0.004, 0.022)

        # 弹坑
        self._craters = [(rng.uniform(0.03, 0.97), rng.uniform(0.0, 1.0),
                          rng.uniform(0.02, 0.07)) for _ in range(9)]

        # 硝烟粒子
        self._particles = [[rng.uniform(0, 1), rng.uniform(0, 1),
                            rng.uniform(0.25, 1.0), rng.uniform(0.0025, 0.010),
                            rng.uniform(0.010, 0.032)] for _ in range(self._dust_n)]

        # 曳光弹
        self._tracers = []

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)

    def _tick(self) -> None:
        # 用真实时间步进，保证动画速度与帧率无关（否则改定时器就会变速）
        now = time.monotonic()
        dt = now - getattr(self, "_last_t", now)
        self._last_t = now
        if dt <= 0.0 or dt > 0.25:      # 首帧 / 长时间挂起
            dt = 0.033
        k = dt / 0.033                  # 以 30fps 为基准的倍数
        self._t += 0.04 * k
        # 粒子漂移
        for pt in self._particles:
            pt[1] -= pt[3] * 0.055 * k          # 缓慢上升
            pt[0] += math.sin(self._t * 0.7 + pt[1] * 6.0) * 0.00055 * k
            if pt[1] < -0.08:
                pt[1] = 1.08
        # 曳光弹
        for tr in list(self._tracers):
            tr[0] += tr[3] * k
            tr[1] += tr[4] * k
            tr[5] -= 0.045 * k
            if tr[5] <= 0:
                self._tracers.remove(tr)
        if len(self._tracers) < 3 and self._intensity > 0.5:
            import random as _r
            if _r.random() < 0.05:
                y0 = _r.uniform(0.18, 0.52)
                self._tracers.append([_r.choice([-0.05, 1.05]), y0,
                                      _r.uniform(-0.06, 0.06),  # 弧度
                                      _r.choice([-1, 1]) * _r.uniform(0.010, 0.024),
                                      _r.uniform(-0.004, 0.002), 1.0])
        self.update()

    # -- 硝烟精灵（预渲染，避免每帧构造 QRadialGradient）------------------- #
    def _smoke_sprite(self):
        if getattr(self, "_smoke_pm", None) is not None:
            return self._smoke_pm
        size = 128
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        pp = QPainter(pm)
        T.aa(pp)
        g = QRadialGradient(QPointF(size / 2, size / 2), size / 2)
        g.setColorAt(0.0, T.a(T.Q_SMOKE, 150))
        g.setColorAt(0.55, T.a(T.Q_SMOKE, 63))
        g.setColorAt(1.0, T.a(T.Q_SMOKE, 0))
        pp.setPen(Qt.PenStyle.NoPen)
        pp.setBrush(QBrush(g))
        pp.drawEllipse(QRectF(0, 0, size, size))
        pp.end()
        self._smoke_pm = pm
        return pm

    # -- 静态背景缓存 ----------------------------------------------------- #
    def _static_pixmap(self):
        """把渐变/废墟/弹坑/铁丝网等**静态**图层缓存成一张 QPixmap。

        这些内容每帧重画非常昂贵（实测整屏 48ms/帧 → 21fps 上限），
        缓存后每帧只需 blit 一次 + 画少量动态粒子。
        """
        W, H = self.width(), self.height()
        key = (W, H)
        if getattr(self, "_cache_key", None) == key and self._cache_pm is not None:
            return self._cache_pm
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(Qt.GlobalColor.transparent)
        pp = QPainter(pm)
        T.aa(pp)
        self._paint_static(pp, float(W), float(H))
        pp.end()
        self._cache_pm = pm
        self._cache_key = key
        return pm

    # -- 绘制 -------------------------------------------------------------
    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        W, H = float(self.width()), float(self.height())
        horizon = H * 0.62
        # 静态层：直接贴缓存
        p.drawPixmap(0, 0, self._static_pixmap())
        self._paint_dynamic(p, W, H, horizon)

    def _paint_dynamic(self, p, W, H, horizon):
        # 硝烟粒子（预渲染精灵，避免每帧构造 QRadialGradient）
        sprite = self._smoke_sprite()
        if sprite is not None and not sprite.isNull():
            sw, sh = sprite.width(), sprite.height()
            for (px, py, pr, spd, rr) in self._particles:
                r = rr * W * 1.5
                x, y = px * W, py * H
                w = max(1, int(r * 2))
                h = max(1, int(r * 0.78 * 2))
                if w != sw or h != sh:
                    sprite = sprite.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                    sw, sh = w, h
                fade = 1.0 - abs(py - 0.45) * 1.3
                alpha = int(max(0, min(150, (48 + 66 * pr) * max(0.0, fade))))
                if alpha <= 2:
                    continue
                p.setOpacity(alpha / 150.0)
                p.drawPixmap(int(x - w / 2), int(y - h / 2), sprite)
            p.setOpacity(1.0)

        # 曳光弹
        for tr in self._tracers:
            x, y, lenv, vx, vy, life = tr
            x0, y0 = x * W, y * H
            x1, y1 = (x + lenv * (1 if vx >= 0 else 1)) * W, (y + lenv * 0.3) * H
            tg = QLinearGradient(QPointF(x0, y0), QPointF(x1, y1))
            tg.setColorAt(0.0, T.a(T.Q_GOLD, 0))

        # 1) 焦土天空
        sky = QLinearGradient(QPointF(0, 0), QPointF(0, horizon))
        sky.setColorAt(0.00, T.Q_SKY_TOP)
        sky.setColorAt(0.55, T.Q_SKY_MID)
        sky.setColorAt(1.00, T.Q_SKY_LOW)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(sky))
        p.drawRect(QRectF(0, 0, W, horizon))

    def _paint_static(self, p, W, H):
        """静态图层：渐变 / 余晖 / 废墟 / 焦土 / 弹坑 / 铁丝网。"""
        horizon = H * 0.62
        glow_c = QPointF(W * 0.5, horizon - H * 0.02)
        rg = QRadialGradient(glow_c, W * 0.62)
        rg.setColorAt(0.0, T.a(T.qc("#B5651D"), 96))
        rg.setColorAt(0.35, T.a(T.qc("#8B5A2B"), 42))
        rg.setColorAt(1.0, T.a(T.Q_BG_DEEP, 0))
        p.setBrush(QBrush(rg))
        p.drawRect(QRectF(0, 0, W, horizon + H * 0.10))

        # 3) 远景废墟剪影
        ruin_col = T.mix(T.Q_SMOKE, T.Q_BG_DEEP, 0.35)
        for (x, w, h, k) in self._ruins:
            rx = x * W
            rw = w * W
            rh = h * H
            col = T.mix(ruin_col, T.Q_SKY_LOW, 0.30 + 0.35 * k)
            p.setBrush(QBrush(T.a(col, 205)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(rx, horizon - rh, rw, rh))
            # 断口 / 塔尖
            if k > 0.68:
                p.drawRect(QRectF(rx + rw * 0.30, horizon - rh - rh * 0.30,
                                  rw * 0.34, rh * 0.34))
            # 残窗
            if rw > 22:
                p.setBrush(QBrush(T.a(T.qc("#B5651D"), int(22 + 34 * k))))
                for wy in range(2):
                    p.drawRect(QRectF(rx + rw * 0.28, horizon - rh + rh * (0.28 + wy * 0.34),
                                      rw * 0.16, rh * 0.16))

        # 4) 地面
        grd = QLinearGradient(QPointF(0, horizon), QPointF(0, H))
        grd.setColorAt(0.0, T.Q_GROUND_FAR)
        grd.setColorAt(0.35, T.Q_GROUND)
        grd.setColorAt(1.0, T.mix(T.Q_GROUND, T.Q_BLACK, 0.45))
        p.setBrush(QBrush(grd))
        p.drawRect(QRectF(0, horizon, W, H - horizon))

        # 5) 弹坑 + 焦痕
        for (cx, cy, cr) in self._craters:
            x = cx * W
            y = horizon + cy * (H - horizon) * 0.9
            r = cr * W
            p.setBrush(QBrush(T.a(T.Q_BLACK, 70)))
            p.drawEllipse(QPointF(x, y), r, r * 0.35)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(T.a(T.Q_RUST, 40), 1.2))
            p.drawEllipse(QPointF(x, y), r * 1.25, r * 0.44)

        # 6) 地平线铁丝网剪影
        self._wire(p, W, horizon)


    def _wire(self, p: QPainter, W: float, horizon: float) -> None:
        """地平线铁丝网（防御工事语汇）。"""
        p.setPen(QPen(T.a(T.Q_STEEL, 46), 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        x = 0.0
        amp = 5.5
        step = 16.0
        path = QPainterPath()
        first = True
        while x <= W:
            y = horizon + math.sin(x * 0.09) * amp + math.sin(x * 0.31) * 2.2
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)
            x += step
        p.drawPath(path)
        # 立柱
        p.setPen(QPen(T.a(T.Q_STEEL, 34), 1.4))
        for i in range(0, int(W), 118):
            p.drawLine(QPointF(i, horizon - 15), QPointF(i, horizon + 9))


# =====================================================================
# 血条 / 掩体条
# =====================================================================


class HpBar(QWidget):
    """缓动血条：底层延迟残影（ghost）+ 主条 + 分段刻度 + 数值。

    ``set_value(hp, max_hp)`` 后主条立即走，残影条用 QPropertyAnimation 追赶。
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None, width: int = T.HPBAR_W, height: int = T.HPBAR_H,
                 show_text: bool = True, compact: bool = False):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setMinimumWidth(int(width * 0.6))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._hp, self._max = 1, 1
        self._ghost = 1.0
        self._shown = 1.0
        self._anim_g = QPropertyAnimation(self, b"ghost", self)
        self._anim_g.setDuration(520)
        self._anim_g.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_s = QPropertyAnimation(self, b"shown", self)
        self._anim_s.setDuration(180)
        self._anim_s.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._show_text = show_text
        self._compact = compact
        self._danger_pulse = 0.0
        self._pt = QTimer(self)
        self._pt.setInterval(_FRAME_MS)
        self._pt.timeout.connect(self._pulse)
        self._pt.start()

    def _pulse(self) -> None:
        if self._max > 0 and self._hp / max(1, self._max) <= 0.30:
            self._danger_pulse = (self._danger_pulse + 0.09) % (math.pi * 2)
            self.update()

    # -- 动画属性 ---------------------------------------------------------
    def _get_ghost(self) -> float:
        return self._ghost

    def _set_ghost(self, v: float) -> None:
        self._ghost = float(v)
        self.update()

    ghost = pyqtProperty(float, fget=_get_ghost, fset=_set_ghost)

    def _get_shown(self) -> float:
        return self._shown

    def _set_shown(self, v: float) -> None:
        self._shown = float(v)
        self.update()

    shown = pyqtProperty(float, fget=_get_shown, fset=_set_shown)

    # -- 数据 -------------------------------------------------------------
    def set_value(self, hp: int, max_hp: int, animate: bool = True) -> None:
        hp = max(0, int(hp))
        max_hp = max(1, int(max_hp))
        old_ratio = self._shown
        new_ratio = hp / max_hp
        self._hp, self._max = hp, max_hp
        if not animate:
            self._ghost = self._shown = new_ratio
            self.update()
            return
        self._anim_s.stop()
        self._anim_s.setStartValue(old_ratio)
        self._anim_s.setEndValue(new_ratio)
        self._anim_s.start()
        if new_ratio < self._ghost:
            self._anim_g.stop()
            self._anim_g.setStartValue(self._ghost)
            self._anim_g.setEndValue(new_ratio)
            self._anim_g.start()
        else:
            self._ghost = new_ratio
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        r = QRectF(0, 0, self.width(), self.height())
        rad = r.height() / 2 if not self._compact else 3.0

        # 凹槽
        T.fill_round(p, r, rad, T.Q_PANEL_LO)
        inner = r.adjusted(1.5, 1.5, -1.5, -1.5)

        # 残影（延迟掉血）
        gw = inner.width() * max(0.0, min(1.0, self._ghost))
        if gw > 0.5:
            T.fill_round(p, QRectF(inner.left(), inner.top(), gw, inner.height()),
                         rad, T.a(T.Q_HP_GHOST, 150))

        # 主条
        w = inner.width() * max(0.0, min(1.0, self._shown))
        ratio = self._hp / max(1, self._max)
        if w > 0.5:
            bar = QRectF(inner.left(), inner.top(), w, inner.height())
            danger = ratio <= 0.30
            pulse = (0.78 + 0.22 * (0.5 + 0.5 * math.sin(self._danger_pulse))) if danger else 1.0
            base = T.mix(T.Q_HP, T.qc("#D14A40"), max(0.0, ratio) * 0.75)
            g = QLinearGradient(QPointF(bar.left(), bar.top()),
                                QPointF(bar.left(), bar.bottom()))
            g.setColorAt(0.0, T.f(base, 1.32 * pulse))
            g.setColorAt(0.42, base)
            g.setColorAt(1.0, T.f(base, 0.62 * pulse))
            T.fill_round(p, bar, rad, QBrush(g))
            # 顶部高光
            hl = QRectF(bar.left() + 2, bar.top() + 1.2, max(0.0, bar.width() - 4),
                        bar.height() * 0.30)
            if hl.width() > 2:
                T.fill_round(p, hl, hl.height() / 2, T.a(T.Q_WHITE, 46))

        # 分段刻度（每 25%）
        p.setPen(QPen(T.a(T.Q_BLACK, 110), 1.0))
        for i in range(1, 4):
            x = inner.left() + inner.width() * i / 4.0
            p.drawLine(QPointF(x, inner.top() + 1), QPointF(x, inner.bottom() - 1))

        # 描边
        T.stroke_round(p, r.adjusted(0.5, 0.5, -0.5, -0.5), rad,
                       T.a(T.BORDER_HI and T.Q_BORDER_HI, 220), 1.2)

        # 文本
        if self._show_text:
            fnt = T.font(T.FONT_TINY + 1, True)
            T.text_c(p, r.center().x(), r.center().y(),
                     f"{self._hp}/{self._max}", fnt, T.Q_TEXT, shadow=True)
        p.end()


class CoverBar(QWidget):
    """掩体条：钢灰蓝，带盾形图标位。"""

    def __init__(self, parent=None, height: int = 14):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._val = 0
        self._shown = 0.0
        self._anim = QPropertyAnimation(self, b"shown", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_shown(self) -> float:
        return self._shown

    def _set_shown(self, v: float) -> None:
        self._shown = float(v)
        self.update()

    shown = pyqtProperty(float, fget=_get_shown, fset=_set_shown)

    def set_value(self, cover: int, animate: bool = True) -> None:
        cover = max(0, int(cover))
        old = self._shown
        self._val = cover
        if not animate:
            self._shown = float(cover)
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(old)
        self._anim.setEndValue(float(cover))
        self._anim.start()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        r = QRectF(0, 0, self.width(), self.height())
        rad = r.height() / 2
        if self._val <= 0 and self._shown < 0.5:
            # 只画一条虚线占位，避免布局跳动
            p.setPen(QPen(T.a(T.Q_BORDER, 130), 1.0, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(T.round_path(r.adjusted(0.5, 0.5, -0.5, -0.5), rad))
            p.end()
            return

        T.fill_round(p, r, rad, T.Q_PANEL_LO)
        inner = r.adjusted(1.5, 1.5, -1.5, -1.5)
        # 掩体条按“当前值 / 参考上限”显示；用非线性映射让大数字也可见
        ref = max(12.0, float(self._val) * 1.35)
        ratio = max(0.0, min(1.0, self._shown / ref))
        w = inner.width() * ratio
        if w > 0.5:
            bar = QRectF(inner.left(), inner.top(), w, inner.height())
            g = QLinearGradient(QPointF(bar.left(), bar.top()),
                                QPointF(bar.left(), bar.bottom()))
            g.setColorAt(0.0, T.f(T.Q_BLOCK, 1.45))
            g.setColorAt(0.5, T.Q_BLOCK)
            g.setColorAt(1.0, T.Q_BLOCK_DIM)
            T.fill_round(p, bar, rad, QBrush(g))
            hl = QRectF(bar.left() + 2, bar.top() + 1, max(0.0, bar.width() - 4),
                        bar.height() * 0.32)
            if hl.width() > 2:
                T.fill_round(p, hl, hl.height() / 2, T.a(T.Q_WHITE, 54))
        T.stroke_round(p, r.adjusted(0.5, 0.5, -0.5, -0.5), rad,
                       T.a(T.Q_BORDER_HI, 200), 1.0)

        # 盾形图标 + 数字
        icon_cx = r.left() + rad + 1
        self._cover_icon(p, QPointF(icon_cx, r.center().y()), r.height() * 0.30,
                         T.Q_TEXT if self._val > 0 else T.Q_TEXT_FAINT)
        fnt = T.font(T.FONT_TINY + 1, True)
        T.text_c(p, icon_cx + r.height() * 0.72 + 12, r.center().y(),
                 str(int(self._shown)), fnt, T.Q_TEXT, shadow=True)
        p.end()

    @staticmethod
    def _cover_icon(p: QPainter, c: QPointF, s: float, col: QColor) -> None:
        path = QPainterPath()
        path.moveTo(c.x() - s, c.y() - s * 1.05)
        path.lineTo(c.x() + s, c.y() - s * 1.05)
        path.lineTo(c.x() + s, c.y() + s * 0.20)
        path.quadTo(c.x() + s * 0.85, c.y() + s * 1.35, c.x(), c.y() + s * 1.65)
        path.quadTo(c.x() - s * 0.85, c.y() + s * 1.35, c.x() - s, c.y() + s * 0.20)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawPath(path)


# =====================================================================
# 补给能量球
# =====================================================================


class SupplyOrb(QWidget):
    """补给（能量）：环形进度 + 中心数字 + 呼吸辉光。"""

    def __init__(self, parent=None, size: int = 96):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._cur, self._max = 3, 3
        self._shown = 3.0
        self._anim = QPropertyAnimation(self, b"shown", self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._phase = 0.0
        self._t = QTimer(self)
        self._t.setInterval(_FRAME_MS)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def _tick(self) -> None:
        self._phase += 0.055
        self.update()

    def _get_shown(self) -> float:
        return self._shown

    def _set_shown(self, v: float) -> None:
        self._shown = float(v)
        self.update()

    shown = pyqtProperty(float, fget=_get_shown, fset=_set_shown)

    def set_value(self, cur: int, mx: int, animate: bool = True) -> None:
        cur, mx = int(cur), max(1, int(mx))
        old = self._shown
        self._cur, self._max = cur, mx
        if not animate:
            self._shown = float(cur)
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(old)
        self._anim.setEndValue(float(cur))
        self._anim.start()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = min(self.width(), self.height()) / 2 - 6

        # 外壳（钢板圆盘 + 阴影）
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 120)))
        p.drawEllipse(c + QPointF(0, 3), R, R)
        shell = QRadialGradient(c + QPointF(-R * 0.3, -R * 0.35), R * 1.9)
        shell.setColorAt(0.0, T.f(T.Q_PANEL_HI, 1.35))
        shell.setColorAt(0.6, T.Q_PANEL)
        shell.setColorAt(1.0, T.f(T.Q_PANEL_LO, 0.9))
        p.setBrush(QBrush(shell))
        p.drawEllipse(c, R, R)
        # 铆钉环
        for i in range(8):
            ang = i * math.pi / 4 + self._phase * 0.15
            pt = QPointF(c.x() + math.cos(ang) * (R - 4.5),
                         c.y() + math.sin(ang) * (R - 4.5))
            p.setBrush(QBrush(T.a(T.Q_BLACK, 130)))
            p.drawEllipse(pt, 2.0, 2.0)
            p.setBrush(QBrush(T.mix(T.Q_STEEL, T.Q_WHITE, 0.4)))
            p.drawEllipse(pt, 1.35, 1.35)

        # 环形进度
        ratio = max(0.0, min(1.0, self._shown / max(1, self._max)))
        pulse = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(self._phase))
        empty = ratio < 0.999
        T.wedge(p, c.x(), c.y(), R - 9, 1.0, 90.0,
                bg=T.a(T.Q_BLACK, 165), fill=T.a(T.Q_BLACK, 165), thickness=6)
        gcol = T.qc("#D8C071") if self._cur > 0 else T.Q_TEXT_FAINT
        if self._cur > 0:
            T.wedge(p, c.x(), c.y(), R - 9, ratio, 90.0,
                    bg=T.a(gcol, 0), fill=T.a(gcol, int(200 + 55 * pulse)), thickness=6)
        else:
            T.wedge(p, c.x(), c.y(), R - 9, 0.0, 90.0,
                    bg=T.a(T.Q_BORDER, 200), fill=T.a(T.Q_BORDER, 200), thickness=6)

        # 呼吸辉光
        if self._cur > 0:
            g = QRadialGradient(c, R * 1.25)
            g.setColorAt(0.55, T.a(gcol, 0))
            g.setColorAt(0.85, T.a(gcol, int(30 * pulse)))
            g.setColorAt(1.0, T.a(gcol, 0))
            p.setBrush(QBrush(g))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, R * 1.25, R * 1.25)

        # 数字
        T.text_c(p, c.x(), c.y() + 1, f"{self._cur}/{self._max}",
                 T.font(T.FONT_H2, True), T.Q_TEXT, shadow=True)
        p.end()



# =====================================================================
# 意图徽标 / Buff 芯片
# =====================================================================


class IntentBadge(QWidget):
    """敌人意图：图标 + 伤害数字。intent 数据来自 snapshot()["enemies"][i]["intent"]。"""

    def __init__(self, parent=None, size: int = 54):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._intent: Optional[dict] = None
        self.setToolTip("")

    def set_intent(self, intent: Optional[dict]) -> None:
        self._intent = intent
        if intent:
            bits = [f"{T.INTENT_NAMES.get(intent.get('intent',''), '行动')}"]
            if intent.get("damage"):
                d = f"伤害 {intent['damage']}"
                if int(intent.get("hits", 1)) > 1:
                    d += f" × {intent['hits']}"
                bits.append(d)
            if intent.get("block"):
                bits.append(f"{T.tr('掩体')} {intent['block']}")
            tip = f"【{T.tr(intent.get('name',''))}】\n" + "  ".join(bits)
            if intent.get("text"):
                tip += "\n" + T.tr(intent["text"])
            self.setToolTip(tip)
        else:
            self.setToolTip("")
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        if not self._intent:
            return
        p = QPainter(self)
        T.aa(p)
        it = self._intent
        kind = str(it.get("intent", "unknown"))
        col = T.intent_color(kind)
        c = QPointF(self.width() / 2, self.height() / 2)

        # 背板
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 120)))
        p.drawEllipse(c + QPointF(0, 2), 20, 20)
        g = QRadialGradient(c + QPointF(-5, -6), 30)
        g.setColorAt(0.0, T.f(T.Q_PANEL_HI, 1.3))
        g.setColorAt(1.0, T.Q_PANEL_LO)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, 20, 20)
        T.stroke_round(p, QRectF(c.x() - 20, c.y() - 20, 40, 40), 20,
                       T.a(col, 210), 1.6)

        # 图标
        self._icon(p, c, kind, col)

        # 伤害数字
        if it.get("damage"):
            txt = str(it["damage"])
            if int(it.get("hits", 1)) > 1:
                txt = f"{it['damage']}×{it['hits']}"
            fnt = T.font(T.FONT_SMALL, True)
            fm = QFontMetricsF(fnt)
            w = fm.horizontalAdvance(txt) + 12
            box = QRectF(c.x() - w / 2, c.y() + 14, w, 17)
            T.fill_round(p, box, 8, T.a(T.Q_RED_DIM, 235))
            T.stroke_round(p, box, 8, T.a(T.Q_RED, 235), 1.0)
            T.text_c(p, box.center().x(), box.center().y() + 0.5, txt, fnt, T.Q_TEXT)
        elif it.get("block"):
            fnt = T.font(T.FONT_TINY + 1, True)
            T.text_c(p, c.x(), c.y() + 22, f"▣{it['block']}", fnt, T.Q_BLOCK)
        p.end()

    @staticmethod
    def _icon(p: QPainter, c: QPointF, kind: str, col: QColor) -> None:
        """军事符号语汇：爆裂=攻击 / 盾=掩体 / 齿轮=指令 / 向下箭头=压制。"""
        s = 9.0
        if kind.startswith("attack"):
            # 爆裂星
            path = QPainterPath()
            for i in range(12):
                rad = s if i % 2 == 0 else s * 0.44
                ang = -math.pi / 2 + i * math.pi / 6
                pt = QPointF(c.x() + math.cos(ang) * rad, c.y() - 2 + math.sin(ang) * rad)
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawPath(path)
        elif kind == "defend":
            CoverBar._cover_icon(p, QPointF(c.x(), c.y() - 2), s * 0.85, col)
        elif kind == "buff":
            T.chevron(p, c.x(), c.y() - 2, s * 0.9, col, up=True, width=2.4)
        elif kind == "debuff":
            T.chevron(p, c.x(), c.y() - 2, s * 0.9, col, up=False, width=2.4)
            p.setPen(QPen(col, 2.0))
            p.drawLine(QPointF(c.x() - s, c.y() - 2 - s * 0.8),
                       QPointF(c.x() + s, c.y() - 2 + s * 0.55))
        elif kind == "sleep":
            p.setPen(QPen(col, 1.8, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(c.x(), c.y() - 2), s * 0.8, s * 0.8)
        else:
            # 齿轮 = 指令
            p.setPen(QPen(col, 2.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(c.x(), c.y() - 2), s * 0.55, s * 0.55)
            for i in range(6):
                ang = i * math.pi / 3
                p.drawLine(
                    QPointF(c.x() + math.cos(ang) * s * 0.62, c.y() - 2 + math.sin(ang) * s * 0.62),
                    QPointF(c.x() + math.cos(ang) * s * 0.95, c.y() - 2 + math.sin(ang) * s * 0.95))


class BuffChip(QWidget):
    """单个 buff/debuff：小圆盾 + 层数角标。"""

    def __init__(self, key: str, amount: int, parent=None, size: int = T.BUFF_SIZE):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.key = key
        self.amount = int(amount)
        name = T.buff_name(key)
        self.setToolTip(f"{name} {amount}")
        self._pulse = 0.0

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        k = self.key
        col = T.buff_color(k)
        c = QPointF(self.width() / 2, self.height() / 2 - 1)
        R = min(self.width(), self.height()) / 2 - 5

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 130)))
        p.drawEllipse(c + QPointF(0, 1.8), R, R)
        g = QRadialGradient(c + QPointF(-R * 0.35, -R * 0.4), R * 2.1)
        g.setColorAt(0.0, T.f(col, 0.95))
        g.setColorAt(0.7, T.f(col, 0.55))
        g.setColorAt(1.0, T.f(col, 0.32))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, R, R)
        T.stroke_round(p, QRectF(c.x() - R, c.y() - R, R * 2, R * 2), R,
                       T.a(T.f(col, 1.6), 235), 1.4)

        self._glyph(p, c, k, R)

        # 层数角标
        fnt = T.font(max(9, T.FONT_TINY - 1), True)
        T.text_c(p, c.x(), c.y() + R * 1.02, str(self.amount), fnt, T.Q_TEXT, shadow=True)
        p.end()

    @staticmethod
    def _glyph(p: QPainter, c: QPointF, k: str, R: float) -> None:
        """用几何符号表示 buff 语义（军事语汇）。"""
        dark = T.a(T.Q_BLACK, 190)
        s = R * 0.52
        if k in ("strength", "strength_down"):
            # 火力：向上/向下的弹丸
            up = k == "strength"
            for i in range(3):
                x = c.x() + (i - 1) * s * 0.72
                path = QPainterPath()
                if up:
                    path.moveTo(x, c.y() - s * 0.85)
                    path.lineTo(x + s * 0.42, c.y() + s * 0.45)
                    path.lineTo(x - s * 0.42, c.y() + s * 0.45)
                else:
                    path.moveTo(x, c.y() + s * 0.85)
                    path.lineTo(x + s * 0.42, c.y() - s * 0.45)
                    path.lineTo(x - s * 0.42, c.y() - s * 0.45)
                path.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(dark))
                p.drawPath(path)
        elif k in ("vulnerable",):
            # 破甲：盾上裂纹
            CoverBar._cover_icon(p, c, s * 0.95, dark)
            p.setPen(QPen(T.a(T.qc("#FFE9A8"), 230), 1.5))
            p.drawLine(QPointF(c.x() - s * 0.3, c.y() - s * 0.7),
                       QPointF(c.x() + s * 0.1, c.y() + s * 0.1))
            p.drawLine(QPointF(c.x() + s * 0.1, c.y() + s * 0.1),
                       QPointF(c.x() - s * 0.2, c.y() + s * 0.8))
        elif k == "weak":
            # 压制：向下箭头
            T.chevron(p, c.x(), c.y() - s * 0.15, s * 0.85, dark, up=False, width=2.2)
        elif k == "frail":
            p.setPen(QPen(dark, 1.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, s * 0.72, s * 0.72)
            p.drawLine(QPointF(c.x() - s, c.y() - s), QPointF(c.x() + s, c.y() + s))
        elif k == "poison":
            # 燃烧：火焰
            path = QPainterPath()
            path.moveTo(c.x(), c.y() - s)
            path.quadTo(c.x() + s * 0.95, c.y() + s * 0.15, c.x(), c.y() + s * 0.9)
            path.quadTo(c.x() - s * 0.95, c.y() + s * 0.15, c.x(), c.y() - s)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(dark))
            p.drawPath(path)
        elif k == "thorns":
            # 铁丝网
            p.setPen(QPen(dark, 1.5))
            for j in range(2):
                y = c.y() - s * 0.45 + j * s * 0.9
                p.drawLine(QPointF(c.x() - s, y), QPointF(c.x() + s, y))
            p.drawLine(QPointF(c.x(), c.y() - s * 0.9), QPointF(c.x(), c.y() + s * 0.9))
        elif k in ("metallicize", "plated_armor", "barrier"):
            # 工事 / 装甲板：叠层矩形
            for i in range(3):
                rr = QRectF(c.x() - s * (1.0 - i * 0.22), c.y() - s * 0.75 + i * s * 0.5,
                            s * 2 * (1.0 - i * 0.22), s * 0.42)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(dark))
                p.drawRect(rr)
        elif k in ("ritual", "regenerate"):
            # 增援 / 战地医疗：十字
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(dark))
            p.drawRect(QRectF(c.x() - s * 0.28, c.y() - s, s * 0.56, s * 2))
            p.drawRect(QRectF(c.x() - s, c.y() - s * 0.28, s * 2, s * 0.56))
        elif k in ("artifact", "intangible"):
            # 干扰弹 / 烟幕：六边形
            path = QPainterPath()
            for i in range(6):
                ang = -math.pi / 2 + i * math.pi / 3
                pt = QPointF(c.x() + math.cos(ang) * s, c.y() + math.sin(ang) * s)
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            path.closeSubpath()
            p.setPen(QPen(dark, 1.7))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        elif k in ("chain", "accuracy", "envenom"):
            # 连射 / 瞄准：准星
            p.setPen(QPen(dark, 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, s * 0.62, s * 0.62)
            for ang in (0, math.pi / 2, math.pi, math.pi * 1.5):
                p.drawLine(QPointF(c.x() + math.cos(ang) * s * 0.72, c.y() + math.sin(ang) * s * 0.72),
                           QPointF(c.x() + math.cos(ang) * s * 1.05, c.y() + math.sin(ang) * s * 1.05))
        else:
            T.star(p, c.x(), c.y(), s * 0.9, dark)


# =====================================================================
# 单位立绘：QPainterPath 剪影
# =====================================================================


def draw_player_tank(p: QPainter, cx: float, cy: float, s: float,
                     col: QColor, hp_ratio: float = 1.0) -> None:
    """玩家坦克（军绿，正面/侧面剪影 + 履带 + 炮塔 + 炮管）。"""
    body = col
    dark = T.f(col, 0.55)
    light = T.f(col, 1.42)
    # 履带
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(dark))
    p.drawRoundedRect(QRectF(cx - s * 1.05, cy + s * 0.30, s * 2.10, s * 0.46),
                      s * 0.20, s * 0.20)
    for i in range(7):
        x = cx - s * 1.00 + i * s * 0.335
        p.setBrush(QBrush(T.a(T.Q_BLACK, 120)))
        p.drawEllipse(QPointF(x, cy + s * 0.53), s * 0.085, s * 0.085)
    # 车体
    hull = QPolygonF([QPointF(cx - s * 0.95, cy + s * 0.32),
                      QPointF(cx - s * 0.80, cy - s * 0.06),
                      QPointF(cx + s * 0.80, cy - s * 0.06),
                      QPointF(cx + s * 0.95, cy + s * 0.32)])
    g = QLinearGradient(QPointF(cx, cy - s * 0.1), QPointF(cx, cy + s * 0.35))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    p.drawPolygon(hull)
    # 炮塔
    p.setBrush(QBrush(T.mix(body, T.Q_WHITE, 0.12)))
    p.drawRoundedRect(QRectF(cx - s * 0.44, cy - s * 0.44, s * 0.88, s * 0.42),
                      s * 0.10, s * 0.10)
    # 炮管
    p.setBrush(QBrush(dark))
    p.drawRect(QRectF(cx + s * 0.30, cy - s * 0.36, s * 0.92, s * 0.13))
    p.drawRect(QRectF(cx + s * 1.16, cy - s * 0.41, s * 0.14, s * 0.23))  # 炮口制退器
    # 车长塔
    p.setBrush(QBrush(light))
    p.drawRoundedRect(QRectF(cx - s * 0.30, cy - s * 0.60, s * 0.30, s * 0.20),
                      s * 0.05, s * 0.05)
    # 星徽
    T.star(p, cx - s * 0.58, cy + s * 0.13, s * 0.13, T.qc("#E8E2D4"))
    # 战损：血少时冒烟
    if hp_ratio < 0.55:
        n = 3 if hp_ratio < 0.3 else 2
        for i in range(n):
            r = s * (0.12 + i * 0.09)
            y = cy - s * 0.85 - i * s * 0.30
            gg = QRadialGradient(QPointF(cx + s * 0.1 + i * s * 0.12, y), r * 2.4)
            gg.setColorAt(0.0, T.a(T.Q_SMOKE, 120 - i * 28))
            gg.setColorAt(1.0, T.a(T.Q_SMOKE, 0))
            p.setBrush(QBrush(gg))
            p.drawEllipse(QPointF(cx + s * 0.1 + i * s * 0.12, y), r * 2.0, r * 1.7)


def draw_hq(p: QPainter, cx: float, cy: float, s: float, col: QColor,
            hp_ratio: float = 1.0) -> None:
    """总部碉堡：沙袋 + 混凝土掩体 + 旗杆（旗色随 HP 变化）。"""
    dark = T.f(col, 0.5)
    light = T.f(col, 1.35)
    # 沙袋底座
    p.setPen(Qt.PenStyle.NoPen)
    for row in range(2):
        n = 7 - row
        for i in range(n):
            x = cx - s * 0.95 + i * s * 0.30 + row * s * 0.15
            y = cy + s * 0.55 - row * s * 0.22
            p.setBrush(QBrush(T.f(T.Q_RUST, 0.55 + row * 0.10)))
            p.drawRoundedRect(QRectF(x - s * 0.15, y - s * 0.11, s * 0.30, s * 0.22),
                              s * 0.09, s * 0.09)
    # 主堡体
    body = QPolygonF([QPointF(cx - s * 0.78, cy + s * 0.48),
                      QPointF(cx - s * 0.66, cy - s * 0.20),
                      QPointF(cx + s * 0.66, cy - s * 0.20),
                      QPointF(cx + s * 0.78, cy + s * 0.48)])
    g = QLinearGradient(QPointF(cx, cy - s * 0.2), QPointF(cx, cy + s * 0.48))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    p.drawPolygon(body)
    # 射击孔
    p.setBrush(QBrush(T.a(T.Q_BLACK, 210)))
    p.drawRect(QRectF(cx - s * 0.44, cy - s * 0.10, s * 0.88, s * 0.15))
    # 顶盖
    p.setBrush(QBrush(T.f(col, 0.72)))
    p.drawRect(QRectF(cx - s * 0.72, cy - s * 0.30, s * 1.44, s * 0.12))
    # 旗杆 + 旗帜（颜色随 HP）
    pole_x = cx + s * 0.52
    p.setBrush(QBrush(T.f(T.Q_STEEL, 0.8)))
    p.drawRect(QRectF(pole_x, cy - s * 1.55, s * 0.075, s * 1.30))
    flag_col = (T.qc("#6B7F3A") if hp_ratio > 0.6 else
                (T.qc("#C9A227") if hp_ratio > 0.3 else T.qc("#A8322D")))
    wave = QPainterPath()
    h = s * 0.34
    wave.moveTo(pole_x + s * 0.075, cy - s * 1.52)
    wave.lineTo(pole_x + s * 0.90, cy - s * 1.46)
    wave.lineTo(pole_x + s * 0.90, cy - s * 1.52 + h)
    wave.lineTo(pole_x + s * 0.075, cy - s * 1.52 + h)
    wave.closeSubpath()
    fg = QLinearGradient(QPointF(pole_x, cy - s * 1.5),
                         QPointF(pole_x + s, cy - s * 1.2))
    fg.setColorAt(0.0, T.f(flag_col, 1.2))
    fg.setColorAt(1.0, T.f(flag_col, 0.7))
    p.setBrush(QBrush(fg))
    p.drawPath(wave)
    T.star(p, pole_x + s * 0.50, cy - s * 1.52 + h / 2, s * 0.11, T.a(T.Q_TEXT, 220))


def draw_enemy_tank(p: QPainter, cx: float, cy: float, s: float, col: QColor) -> None:
    """敌方坦克（钢灰，楔形倾斜装甲，朝左）。"""
    dark = T.f(col, 0.5)
    light = T.f(col, 1.45)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(dark))
    p.drawRoundedRect(QRectF(cx - s * 1.02, cy + s * 0.28, s * 2.04, s * 0.44),
                      s * 0.18, s * 0.18)
    for i in range(7):
        x = cx - s * 0.96 + i * s * 0.325
        p.setBrush(QBrush(T.a(T.Q_BLACK, 130)))
        p.drawEllipse(QPointF(x, cy + s * 0.50), s * 0.08, s * 0.08)
    hull = QPolygonF([QPointF(cx - s * 0.95, cy + s * 0.30),
                      QPointF(cx - s * 0.62, cy - s * 0.14),
                      QPointF(cx + s * 0.70, cy - s * 0.14),
                      QPointF(cx + s * 0.98, cy + s * 0.30)])
    g = QLinearGradient(QPointF(cx, cy - s * 0.15), QPointF(cx, cy + s * 0.32))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    p.drawPolygon(hull)
    p.setBrush(QBrush(T.mix(col, T.Q_BLACK, 0.22)))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.58, cy - s * 0.14),
                             QPointF(cx - s * 0.34, cy - s * 0.52),
                             QPointF(cx + s * 0.30, cy - s * 0.52),
                             QPointF(cx + s * 0.52, cy - s * 0.14)]))
    p.setBrush(QBrush(dark))
    p.drawRect(QRectF(cx - s * 1.24, cy - s * 0.44, s * 0.94, s * 0.12))  # 炮管朝左
    p.setBrush(QBrush(T.a(T.Q_BLACK, 190)))
    for i in range(4):  # 侧裙观察窗
        p.drawRect(QRectF(cx - s * 0.20 + i * s * 0.26, cy - s * 0.02, s * 0.16, s * 0.09))


def draw_enemy_infantry(p: QPainter, cx: float, cy: float, s: float, col: QColor) -> None:
    """敌方步兵：钢盔 + 肩线 + 步枪。"""
    dark = T.f(col, 0.48)
    light = T.f(col, 1.40)
    p.setPen(Qt.PenStyle.NoPen)
    # 钢盔
    helm = QPainterPath()
    helm.moveTo(cx - s * 0.50, cy - s * 0.12)
    helm.quadTo(cx - s * 0.52, cy - s * 0.72, cx, cy - s * 0.76)
    helm.quadTo(cx + s * 0.52, cy - s * 0.72, cx + s * 0.50, cy - s * 0.12)
    helm.closeSubpath()
    g = QLinearGradient(QPointF(cx, cy - s * 0.78), QPointF(cx, cy - s * 0.10))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    p.drawPath(helm)
    # 盔檐
    p.setBrush(QBrush(T.f(col, 0.7)))
    p.drawRoundedRect(QRectF(cx - s * 0.62, cy - s * 0.18, s * 1.24, s * 0.13),
                      s * 0.06, s * 0.06)
    # 面部阴影
    p.setBrush(QBrush(T.a(T.Q_BLACK, 180)))
    p.drawEllipse(QPointF(cx, cy + s * 0.02), s * 0.32, s * 0.20)
    # 躯干
    torso = QPolygonF([QPointF(cx - s * 0.34, cy + s * 0.66),
                       QPointF(cx - s * 0.30, cy + s * 0.12),
                       QPointF(cx + s * 0.30, cy + s * 0.12),
                       QPointF(cx + s * 0.34, cy + s * 0.66)])
    g2 = QLinearGradient(QPointF(cx, cy + s * 0.1), QPointF(cx, cy + s * 0.66))
    g2.setColorAt(0.0, light)
    g2.setColorAt(1.0, dark)
    p.setBrush(QBrush(g2))
    p.drawPolygon(torso)
    # 步枪（斜跨）
    p.setBrush(QBrush(T.mix(T.Q_RUST, T.Q_BLACK, 0.35)))
    rp = QPainterPath()
    rp.moveTo(cx - s * 0.86, cy + s * 0.70)
    rp.lineTo(cx + s * 0.62, cy - s * 0.02)
    rp.lineTo(cx + s * 0.62, cy + s * 0.10)
    rp.lineTo(cx - s * 0.86, cy + s * 0.82)
    rp.closeSubpath()
    p.drawPath(rp)
    # 弹匣
    p.drawRect(QRectF(cx - s * 0.16, cy + s * 0.34, s * 0.14, s * 0.26))


def draw_enemy_plane(p: QPainter, cx: float, cy: float, s: float, col: QColor) -> None:
    """敌机：俯视轰炸机剪影 + 尾迹。"""
    dark = T.f(col, 0.55)
    light = T.f(col, 1.35)
    p.setPen(Qt.PenStyle.NoPen)
    # 机身
    g = QLinearGradient(QPointF(cx, cy - s * 0.9), QPointF(cx, cy + s * 0.9))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    fuse = QPainterPath()
    fuse.moveTo(cx, cy - s * 0.92)
    fuse.quadTo(cx + s * 0.20, cy - s * 0.30, cx + s * 0.17, cy + s * 0.62)
    fuse.quadTo(cx, cy + s * 0.92, cx - s * 0.17, cy + s * 0.62)
    fuse.quadTo(cx - s * 0.20, cy - s * 0.30, cx, cy - s * 0.92)
    p.drawPath(fuse)
    # 主翼
    p.setBrush(QBrush(T.mix(col, T.Q_BLACK, 0.18)))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 1.05, cy + s * 0.10),
                             QPointF(cx - s * 0.14, cy - s * 0.28),
                             QPointF(cx + s * 0.14, cy - s * 0.28),
                             QPointF(cx + s * 1.05, cy + s * 0.10),
                             QPointF(cx + s * 1.05, cy + s * 0.26),
                             QPointF(cx - s * 1.05, cy + s * 0.26)]))
    # 尾翼
    p.setBrush(QBrush(dark))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.40, cy + s * 0.66),
                             QPointF(cx + s * 0.40, cy + s * 0.66),
                             QPointF(cx + s * 0.34, cy + s * 0.86),
                             QPointF(cx - s * 0.34, cy + s * 0.86)]))
    # 座舱
    p.setBrush(QBrush(T.a(T.qc("#9FC6D8"), 230)))
    p.drawEllipse(QPointF(cx, cy - s * 0.42), s * 0.13, s * 0.24)
    # 尾迹
    for i in range(3):
        y = cy + s * (1.00 + i * 0.30)
        p.setBrush(QBrush(T.a(T.Q_SMOKE, 110 - i * 30)))
        p.drawEllipse(QPointF(cx, y), s * 0.16 * (1 + i * 0.35), s * 0.08 * (1 + i * 0.3))


def draw_enemy_fortress(p: QPainter, cx: float, cy: float, s: float, col: QColor) -> None:
    """要塞：多面体混凝土 + 炮塔 + 探照灯。"""
    dark = T.f(col, 0.45)
    light = T.f(col, 1.30)
    p.setPen(Qt.PenStyle.NoPen)
    g = QLinearGradient(QPointF(cx, cy - s * 0.9), QPointF(cx, cy + s * 0.85))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 1.00, cy + s * 0.85),
                             QPointF(cx - s * 0.85, cy - s * 0.10),
                             QPointF(cx - s * 0.40, cy - s * 0.50),
                             QPointF(cx + s * 0.40, cy - s * 0.50),
                             QPointF(cx + s * 0.85, cy - s * 0.10),
                             QPointF(cx + s * 1.00, cy + s * 0.85)]))
    # 射击孔排
    p.setBrush(QBrush(T.a(T.Q_BLACK, 215)))
    for i in range(5):
        p.drawRect(QRectF(cx - s * 0.60 + i * s * 0.28, cy - s * 0.06, s * 0.16, s * 0.12))
    # 中央炮塔
    p.setBrush(QBrush(T.mix(col, T.Q_BLACK, 0.30)))
    p.drawRoundedRect(QRectF(cx - s * 0.30, cy - s * 0.78, s * 0.60, s * 0.30),
                      s * 0.06, s * 0.06)
    p.setBrush(QBrush(T.f(dark, 0.9)))
    p.drawRect(QRectF(cx + s * 0.24, cy - s * 0.72, s * 0.86, s * 0.11))
    # 探照灯
    p.setBrush(QBrush(T.a(T.qc("#FFE9A8"), 200)))
    p.drawEllipse(QPointF(cx - s * 0.68, cy - s * 0.62), s * 0.11, s * 0.11)
    cone = QPolygonF([QPointF(cx - s * 0.68, cy - s * 0.62),
                      QPointF(cx - s * 2.4, cy - s * 1.5),
                      QPointF(cx - s * 1.9, cy - s * 0.30)])
    cg = QLinearGradient(QPointF(cx - s * 0.68, cy - s * 0.62),
                         QPointF(cx - s * 2.2, cy - s * 0.9))
    cg.setColorAt(0.0, T.a(T.qc("#FFE9A8"), 70))
    cg.setColorAt(1.0, T.a(T.qc("#FFE9A8"), 0))
    p.setBrush(QBrush(cg))
    p.drawPolygon(cone)
    # 铁丝网
    p.setPen(QPen(T.a(T.Q_STEEL, 170), 1.3))
    for j in range(2):
        y = cy + s * (0.62 + j * 0.16)
        p.drawLine(QPointF(cx - s * 1.15, y), QPointF(cx + s * 1.15, y))
        for k in range(7):
            x = cx - s * 1.05 + k * s * 0.35
            p.drawLine(QPointF(x, y - s * 0.07), QPointF(x + s * 0.18, y + s * 0.07))


def draw_enemy_artillery(p: QPainter, cx: float, cy: float, s: float, col: QColor) -> None:
    """火炮 / 反坦克炮：轮 + 炮盾 + 长身管。"""
    dark = T.f(col, 0.5)
    light = T.f(col, 1.35)
    p.setPen(Qt.PenStyle.NoPen)
    # 大架
    p.setBrush(QBrush(T.mix(T.Q_RUST, T.Q_BLACK, 0.42)))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.20, cy + s * 0.22),
                             QPointF(cx + s * 1.05, cy + s * 0.72),
                             QPointF(cx + s * 1.05, cy + s * 0.86),
                             QPointF(cx - s * 0.30, cy + s * 0.42)]))
    # 轮
    for wx in (cx - s * 0.30, cx + s * 0.30):
        p.setBrush(QBrush(T.f(T.Q_SMOKE, 0.9)))
        p.drawEllipse(QPointF(wx, cy + s * 0.50), s * 0.34, s * 0.34)
        p.setBrush(QBrush(T.mix(T.Q_STEEL, T.Q_BLACK, 0.45)))
        p.drawEllipse(QPointF(wx, cy + s * 0.50), s * 0.16, s * 0.16)
        p.setPen(QPen(T.a(T.Q_STEEL, 190), 1.3))
        for i in range(4):
            ang = i * math.pi / 4
            p.drawLine(QPointF(wx - math.cos(ang) * s * 0.30, cy + s * 0.50 - math.sin(ang) * s * 0.30),
                       QPointF(wx + math.cos(ang) * s * 0.30, cy + s * 0.50 + math.sin(ang) * s * 0.30))
        p.setPen(Qt.PenStyle.NoPen)
    # 炮盾
    g = QLinearGradient(QPointF(cx, cy - s * 0.45), QPointF(cx, cy + s * 0.32))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.62, cy + s * 0.28),
                             QPointF(cx - s * 0.44, cy - s * 0.44),
                             QPointF(cx + s * 0.44, cy - s * 0.44),
                             QPointF(cx + s * 0.62, cy + s * 0.28)]))
    # 身管
    p.setBrush(QBrush(T.mix(dark, T.Q_BLACK, 0.25)))
    p.drawRect(QRectF(cx - s * 1.55, cy - s * 0.36, s * 1.35, s * 0.15))
    p.drawRect(QRectF(cx - s * 1.70, cy - s * 0.42, s * 0.17, s * 0.27))  # 制退器
    # 炮口焰
    p.setBrush(QBrush(T.a(T.qc("#FFD98A"), 150)))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 1.72, cy - s * 0.30),
                             QPointF(cx - s * 2.15, cy - s * 0.52),
                             QPointF(cx - s * 2.05, cy - s * 0.28),
                             QPointF(cx - s * 2.15, cy - s * 0.04),
                             QPointF(cx - s * 1.72, cy - s * 0.28)]))


def draw_enemy_officer(p: QPainter, cx: float, cy: float, s: float, col: QColor) -> None:
    """军官 / 指挥官：大衣 + 大檐帽 + 望远镜。"""
    dark = T.f(col, 0.48)
    light = T.f(col, 1.38)
    p.setPen(Qt.PenStyle.NoPen)
    # 大衣
    g = QLinearGradient(QPointF(cx, cy - s * 0.5), QPointF(cx, cy + s * 0.9))
    g.setColorAt(0.0, light)
    g.setColorAt(1.0, dark)
    p.setBrush(QBrush(g))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.52, cy + s * 0.92),
                             QPointF(cx - s * 0.36, cy - s * 0.20),
                             QPointF(cx + s * 0.36, cy - s * 0.20),
                             QPointF(cx + s * 0.52, cy + s * 0.92)]))
    # 大檐帽
    p.setBrush(QBrush(T.mix(col, T.Q_BLACK, 0.30)))
    hat = QPainterPath()
    hat.moveTo(cx - s * 0.46, cy - s * 0.40)
    hat.quadTo(cx, cy - s * 0.95, cx + s * 0.46, cy - s * 0.40)
    hat.closeSubpath()
    p.drawPath(hat)
    p.setBrush(QBrush(T.f(col, 0.62)))
    p.drawRoundedRect(QRectF(cx - s * 0.58, cy - s * 0.46, s * 1.16, s * 0.13),
                      s * 0.06, s * 0.06)
    # 帽徽
    T.star(p, cx, cy - s * 0.60, s * 0.09, T.qc("#C9A227"))
    # 面部阴影
    p.setBrush(QBrush(T.a(T.Q_BLACK, 170)))
    p.drawEllipse(QPointF(cx, cy - s * 0.22), s * 0.28, s * 0.16)
    # 望远镜
    p.setBrush(QBrush(T.a(T.Q_BLACK, 220)))
    p.drawRect(QRectF(cx - s * 0.30, cy - s * 0.30, s * 0.24, s * 0.15))
    p.drawRect(QRectF(cx + s * 0.06, cy - s * 0.30, s * 0.24, s * 0.15))
    # 肩章
    p.setBrush(QBrush(T.qc("#C9A227")))
    p.drawRect(QRectF(cx - s * 0.50, cy - s * 0.16, s * 0.16, s * 0.10))
    p.drawRect(QRectF(cx + s * 0.34, cy - s * 0.16, s * 0.16, s * 0.10))


def draw_enemy_generic(p: QPainter, cx: float, cy: float, s: float, col: QColor) -> None:
    """通用敌方剪影（认不出的单位）：钢盔 + 沙袋。"""
    dark = T.f(col, 0.5)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(dark))
    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.80, cy + s * 0.72),
                             QPointF(cx - s * 0.62, cy - s * 0.10),
                             QPointF(cx + s * 0.62, cy - s * 0.10),
                             QPointF(cx + s * 0.80, cy + s * 0.72)]))
    p.setBrush(QBrush(T.f(col, 1.25)))
    helm = QPainterPath()
    helm.moveTo(cx - s * 0.40, cy - s * 0.16)
    helm.quadTo(cx - s * 0.42, cy - s * 0.70, cx, cy - s * 0.72)
    helm.quadTo(cx + s * 0.42, cy - s * 0.70, cx + s * 0.40, cy - s * 0.16)
    helm.closeSubpath()
    p.drawPath(helm)
    p.setBrush(QBrush(T.a(T.Q_BLACK, 200)))
    p.drawRect(QRectF(cx - s * 0.36, cy - s * 0.02, s * 0.72, s * 0.12))


#: 单位 key -> 绘制函数
UNIT_PAINTERS = {
    "tank": draw_enemy_tank,
    "infantry": draw_enemy_infantry,
    "plane": draw_enemy_plane,
    "fortress": draw_enemy_fortress,
    "artillery": draw_enemy_artillery,
    "officer": draw_enemy_officer,
    "generic": draw_enemy_generic,
}


def unit_kind_for(name: str = "", eid: str = "", art: str = "") -> str:
    """按 名称 / id / art key 推断立绘类型（纯关键词匹配，不依赖 core 常量）。"""
    hay = f"{name} {eid} {art}".lower()
    rules = [
        ("plane", ("飞机", "轰炸", "侦察机", "空袭", "俯冲", "机编队", "飞艇", "飞")),
        ("artillery", ("炮", "火箭", "榴弹", "臼炮", "迫击", "artillery", "gun", "cannon", "mortar")),
        ("fortress", ("要塞", "碉堡", "堡垒", "工事", "永备", "阵地", "掩体", "据点",
                      "fortress", "bunker", "bastion", "golem")),
        ("tank", ("坦克", "装甲", "战车", "虎式", "突击炮", "列车", "tank", "panzer", "leviathan")),
        ("officer", ("军官", "指挥官", "指挥所", "总督", "参谋", "将领", "军团长",
                     "officer", "commander", "lord", "king", "watcher")),
        ("infantry", ("步兵", "士兵", "军犬", "巡逻", "狙击", "游击队", "掷弹", "老兵",
                      "突击队", "师", "连", "班", "infantry", "soldier", "hound")),
    ]
    for kind, keys in rules:
        if any(k in hay for k in keys):
            return kind
    return "generic"


def draw_unit(p: QPainter, kind: str, cx: float, cy: float, s: float,
              col: QColor) -> None:
    fn = UNIT_PAINTERS.get(kind, draw_enemy_generic)
    fn(p, cx, cy, s, col)


class UnitArt(QWidget):
    """单位立绘容器（含落地阴影 + 呼吸浮动）。"""

    def __init__(self, parent=None, kind: str = "generic", size: int = 150,
                 color: Optional[QColor] = None, animate: bool = True):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.kind = kind
        self.color = color or T.Q_STEEL
        self._phase = 0.0
        self._dead = False
        if animate:
            self._t = QTimer(self)
            self._t.setInterval(_FRAME_MS)
            self._t.timeout.connect(self._tick)
            self._t.start()

    def _tick(self) -> None:
        self._phase += 0.07
        self.update()

    def set_dead(self, dead: bool) -> None:
        self._dead = dead
        self.update()

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        W, H = self.width(), self.height()
        cx = W / 2
        cy = H / 2 + math.sin(self._phase) * 1.6
        s = min(W, H) / 3.0
        alpha = 110 if self._dead else 255
        col = T.a(self.color, alpha)
        # 落地阴影
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 70 if not self._dead else 34)))
        p.drawEllipse(QPointF(cx, H - 10), s * 1.15, s * 0.26)
        p.save()
        if self._dead:
            p.setOpacity(0.35)
        draw_unit(p, self.kind, cx, cy, s, col)
        p.restore()
        p.end()


# =====================================================================
# 卡牌
# =====================================================================


class CardView(QWidget):
    """卡牌控件：做旧纸张 / 铆接钢板 + 稀有度发光 + 悬停上浮放大。

    数据来自 ``snapshot()["hand"][i]``（纯 dict），也可用于牌组/图鉴展示。
    悬停上浮用 QPropertyAnimation 驱动 ``lift`` / ``scale`` 属性。
    """

    clicked = pyqtSignal(int)          # uid
    right_clicked = pyqtSignal(int)
    hovered = pyqtSignal(int)

    BASE_W, BASE_H = T.CARD_W, T.CARD_H

    def __init__(self, card: dict, parent=None, scale: float = 1.0,
                 compact: bool = False, interactive: bool = True):
        super().__init__(parent)
        self.card = dict(card or {})
        self._scale = float(scale)
        self._compact = compact
        self._interactive = interactive
        self.setFixedSize(int(self.BASE_W * scale), int(self.BASE_H * scale))
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._fixed = True
        self.setCursor(Qt.CursorShape.PointingHandCursor if interactive
                       else Qt.CursorShape.ArrowCursor)
        self._lift = 0.0
        self._glow_t = 0.0
        self._selected = False
        self._flash = 0.0
        self._anim_hover = QPropertyAnimation(self, b"lift", self)
        self._anim_hover.setDuration(170)
        self._anim_hover.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._gt = QTimer(self)
        self._gt.setInterval(_FRAME_MS)
        self._gt.timeout.connect(self._tick)
        if interactive:
            self._gt.start()
        self._refresh_tooltip()

    # -- 动画属性 ---------------------------------------------------------
    def _get_lift(self) -> float:
        return self._lift

    def _set_lift(self, v: float) -> None:
        self._lift = float(v)
        # 悬停时基于弧线基准位上浮（扇形布局写入 _arc_base）
        base = getattr(self, "_arc_base", None)
        if base is not None:
            self.move(base[0], base[1] - int(self._lift * 26))
        m = self.parent()
        self.update()
        if m is not None:
            m.update()

    lift = pyqtProperty(float, fget=_get_lift, fset=_set_lift)

    def _tick(self) -> None:
        self._glow_t = (self._glow_t + 0.022) % 1.0
        rar = self.card.get("rarity", "common")
        if rar in ("rare", "uncommon", "boss", "special") or self._selected:
            self.update()
        if self._flash > 0:
            self._flash = max(0.0, self._flash - 0.09)
            self.update()

    def set_card(self, card: dict) -> None:
        self.card = dict(card or {})
        self._refresh_tooltip()
        self.update()

    def set_card(self, card: dict) -> None:
        """更新卡牌数据（会失效渲染缓存）。"""
        self.card = dict(card or {})
        self._cp_tok = None
        self.update()

    def resizeEvent(self, ev):  # noqa: N802
        self._cp_tok = None
        super().resizeEvent(ev)

    def set_scale(self, scale: float) -> None:
        """改变卡牌显示比例（手牌区按张数等比缩小用）。

        ``__init__`` 用了 ``setFixedSize`` 锁死尺寸，直接 ``resize()`` 无效，
        因此必须在这里显式解除固定并设置新的最小/最大尺寸。
        """
        scale = max(0.5, min(1.6, float(scale)))
        self._scale = scale
        w = max(60, int(self.BASE_W * scale))
        h = max(84, int(self.BASE_H * scale))
        self.setMinimumSize(w, h)
        self.setMaximumSize(w, h)
        self.resize(w, h)
        self.update()

    def set_selected(self, on: bool) -> None:
        self._selected = bool(on)
        self.update()

    def flash(self) -> None:
        self._flash = 1.0
        self.update()

    def _refresh_tooltip(self) -> None:
        c = self.card
        if not c:
            return
        name = c.get("name", "")
        if c.get("upgraded"):
            name += "+"
        lines = [
            f"【{name}】  {T.TYPE_NAMES.get(c.get('type',''), c.get('type',''))}"
            f" · {T.RARITY_NAMES.get(c.get('rarity',''), '')}"
            f" · {T.ARCH_NAMES.get(c.get('arch',''), '')}",
            f"{T.tr('补给消耗')}：{c.get('cost', 0)}",
            T.tr(str(c.get("text", ""))),
        ]
        self.setToolTip("\n".join(lines))

    # -- 交互 -------------------------------------------------------------
    def enterEvent(self, ev):  # noqa: N802
        if not self._interactive:
            return
        self._anim_hover.stop()
        self._anim_hover.setStartValue(self._lift)
        self._anim_hover.setEndValue(1.0)
        self._anim_hover.start()
        self.hovered.emit(int(self.card.get("uid", -1)))

    def leaveEvent(self, ev):  # noqa: N802
        if not self._interactive:
            return
        self._anim_hover.stop()
        self._anim_hover.setStartValue(self._lift)
        self._anim_hover.setEndValue(0.0)
        self._anim_hover.start()

    def mousePressEvent(self, ev):  # noqa: N802
        if not self._interactive:
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(int(self.card.get("uid", -1)))
        elif ev.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(int(self.card.get("uid", -1)))

    # -- 绘制 -------------------------------------------------------------
    # -- 渲染缓存 --------------------------------------------------------- #
    def _cache_token(self):
        """决定卡面是否需要重绘的状态指纹。"""
        c = self.card
        return (self.width(), self.height(), round(self._scale, 3),
                bool(self._selected), bool(c.get("playable", True)),
                c.get("name"), c.get("text"), c.get("cost"),
                c.get("upgraded"), c.get("rarity"), c.get("type"))

    def _card_pixmap(self):
        """把**不含悬停动画**的卡面缓存成 QPixmap。

        卡面绘制（做旧纸张/钢板/铆钉/文字排版）单张约 1.7ms，10 张手牌
        每帧重绘就是 17ms —— 这是战斗界面掉帧的主因。卡面内容在血量/费用
        变化之外基本静态，因此缓存收益极大；悬停的上浮/缩放仍由实时绘制完成。
        """
        tok = self._cache_token()
        if getattr(self, "_cp_tok", None) == tok and getattr(self, "_cp_pm", None) is not None:
            return self._cp_pm
        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        pp = QPainter(pm)
        T.aa(pp)
        try:
            self._paint_card(pp, w, h)
        except Exception:
            pass
        pp.end()
        self._cp_pm = pm
        self._cp_tok = tok
        return pm

    def paintEvent(self, ev):  # noqa: N802
        c = self.card
        if not c:
            return
        p = QPainter(self)
        T.aa(p)
        k = self._scale
        # 悬停：整体上浮 + 轻微放大
        off = -self._lift * 26 * k
        zoom = 1.0 + self._lift * 0.06
        p.translate(self.width() / 2, self.height() / 2 + off)
        p.scale(zoom, zoom)
        rot = float(getattr(self, "_arc_rot", 0.0))
        if rot:
            p.rotate(rot)
        p.translate(-self.width() / 2, -self.height() / 2)

        # 未悬停且无发光时直接贴缓存（绝大多数帧走这条路）
        if self._lift < 0.004 and self._flash < 0.004 and not self._selected:
            p.drawPixmap(0, 0, self._card_pixmap())
            return
        # 悬停/选中/闪光：缓存打底 + 实时叠加高光
        p.drawPixmap(0, 0, self._card_pixmap())
        if self._selected or self._lift > 0.004:
            rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
            rcol = T.rarity_color(c.get("rarity", "common"))
            pen = QPen(T.a(rcol, int(120 + 110 * max(self._lift, 1.0 if self._selected else 0))),
                       2.2 + 1.4 * self._lift)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(T.round_path(rect, T.CARD_RADIUS * k))
        return

    def _paint_card(self, p, _w, _h):  # noqa: N802
        """真正的卡面绘制（静态部分，不含悬停位移/缩放）。"""
        c = self.card
        k = self._scale
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        rar = c.get("rarity", "common")
        rcol = T.rarity_color(rar)
        tcol = T.type_color(c.get("type", "skill"))
        playable = bool(c.get("playable", True))

        # 投影
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 170)))
        p.drawPath(T.round_path(rect.translated(0, 5), T.CARD_RADIUS * k))

        # 卡面底：战术/指令用做旧纸张，攻击用铆接钢板
        if rar in ("rare",):
            base = T.qc("#3A3226")
            T.steel_plate(p, rect, base, T.CARD_RADIUS * k, rivets=True)
        elif c.get("type") in ("attack", "power"):
            T.steel_plate(p, rect, T.mix(T.Q_PANEL, tcol, 0.10),
                          T.CARD_RADIUS * k, rivets=True)
        else:
            T.aged_paper(p, rect, T.qc("#D9CDAE"), T.CARD_RADIUS * k,
                         seed=abs(hash(c.get("def_id", "x"))) % 997)

        # 顶部类型色带
        band = QRectF(rect.left(), rect.top(), rect.width(), 30 * k)
        bg = QLinearGradient(band.topLeft(), band.bottomLeft())
        bg.setColorAt(0.0, T.a(T.f(tcol, 1.15), 235))
        bg.setColorAt(1.0, T.a(T.f(tcol, 0.62), 235))
        p.save()
        p.setClipPath(T.round_path(rect, T.CARD_RADIUS * k))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRect(band)
        # 纸张卡的类型带下缘要压一道暗线
        p.setBrush(QBrush(T.a(T.Q_BLACK, 90)))
        p.drawRect(QRectF(band.left(), band.bottom() - 2, band.width(), 2))
        p.restore()

        # 稀有度辉光描边
        if rar in ("rare", "boss", "special"):
            T.glow(p, rect, rcol, T.CARD_RADIUS * k, strength=150,
                   spread=8 * k, t=self._glow_t, pulse=True)
        elif rar == "uncommon":
            T.glow(p, rect, rcol, T.CARD_RADIUS * k, strength=80,
                   spread=5 * k, t=self._glow_t)
        T.stroke_round(p, rect, T.CARD_RADIUS * k,
                       T.a(T.f(rcol, 1.3), 220) if not playable else T.a(rcol, 200),
                       1.6)

        # 卡名
        name = str(c.get("name", ""))
        if c.get("upgraded"):
            name += "+"
        nf = T.font(max(11, int(15 * k)), True)
        nmrect = QRectF(rect.left() + 8 * k, band.top() + 3 * k,
                        rect.width() - 16 * k, band.height() - 4 * k)
        T.text_c(p, nmrect.center().x(), nmrect.center().y(),
                 _elide(p, name, nf, nmrect.width()), nf, T.Q_TEXT, shadow=True)

        # 补给消耗徽标（左上角圆形）
        cost = c.get("cost", 0)
        cc = QPointF(rect.left() + 15 * k, rect.top() + 15 * k)
        rad = 13 * k
        cost_ok = playable
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 150)))
        p.drawEllipse(cc + QPointF(0, 2 * k), rad, rad)
        cg = QRadialGradient(cc + QPointF(-rad * 0.3, -rad * 0.35), rad * 2.2)
        if cost_ok:
            cg.setColorAt(0.0, T.qc("#F2E3A8"))
            cg.setColorAt(0.55, T.Q_SUPPLY)
            cg.setColorAt(1.0, T.Q_GOLD_DIM)
        else:
            cg.setColorAt(0.0, T.Q_TEXT_FAINT)
            cg.setColorAt(1.0, T.mix(T.Q_TEXT_FAINT, T.Q_BLACK, 0.5))
        p.setBrush(QBrush(cg))
        p.drawEllipse(cc, rad, rad)
        T.stroke_round(p, QRectF(cc.x() - rad, cc.y() - rad, rad * 2, rad * 2),
                       rad, T.a(T.Q_BLACK, 170), 1.2)
        cost_txt = "X" if int(cost) < 0 else str(int(cost))
        T.text_c(p, cc.x(), cc.y() + 0.5, cost_txt,
                 T.font(max(10, int(14 * k)), True),
                 T.Q_BLACK if cost_ok else T.Q_TEXT, shadow=False)

        # 插图区
        art = QRectF(rect.left() + 9 * k, band.bottom() + 7 * k,
                     rect.width() - 18 * k, 62 * k)
        self._art(p, art, c, tcol, k)

        # 描述文字
        body = QRectF(rect.left() + 10 * k, art.bottom() + 6 * k,
                      rect.width() - 20 * k, rect.bottom() - art.bottom() - 30 * k)
        dark_card = rar in ("rare",) or c.get("type") in ("attack", "power")
        txt_col = T.Q_TEXT if dark_card else T.qc("#2A2419")
        draw_text_block(p, body, T.tr(str(c.get("text", ""))),
                        T.font(max(9, int(11.5 * k))), txt_col,
                        align=Qt.AlignmentFlag.AlignHCenter,
                        max_lines=6, center_v=True)

        # 底部类型 / 流派条
        foot = QRectF(rect.left() + 6 * k, rect.bottom() - 22 * k,
                      rect.width() - 12 * k, 17 * k)
        T.fill_round(p, foot, 5 * k, T.a(T.f(tcol, 0.55), 200) if dark_card
                     else T.a(tcol, 190))
        label = f"{T.TYPE_NAMES.get(c.get('type',''), '')} · {T.ARCH_NAMES.get(c.get('arch',''), '')}"
        if c.get("exhaust"):
            label += " · 移除"
        if c.get("ethereal"):
            label += " · 虚无"
        if c.get("innate"):
            label += " · 固有"
        if c.get("retain"):
            label += " · 保留"
        T.text_c(p, foot.center().x(), foot.center().y(), label,
                 T.font(max(8, int(9.5 * k)), True), T.Q_TEXT)

        # 稀有度角标
        if rar in ("rare", "boss"):
            T.star(p, rect.right() - 15 * k, rect.bottom() - 38 * k, 6.5 * k, rcol)

        # 不可打出：整卡压暗 + 对角提示
        if not playable:
            p.save()
            p.setClipPath(T.round_path(rect, T.CARD_RADIUS * k))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(T.a(T.Q_BG_DEEP, 128)))
            p.drawRect(rect)
            p.restore()

        # 选中高亮
        if self._selected:
            T.stroke_round(p, rect.adjusted(-2, -2, 2, 2), T.CARD_RADIUS * k + 2,
                           T.a(T.qc("#FFE9A8"), 230), 2.4)

        # 出牌闪光
        if self._flash > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(T.a(T.qc("#FFE9A8"), int(150 * self._flash))))
            p.drawPath(T.round_path(rect, T.CARD_RADIUS * k))

    def _art(self, p: QPainter, rect: QRectF, c: dict, tcol: QColor, k: float) -> None:
        """卡面插图：按类型画对应军事符号。"""
        # 插图底
        T.fill_round(p, rect, 5 * k, T.a(T.Q_BLACK, 60))
        t = c.get("type", "skill")
        # 类型图标
        cx, cy = rect.center().x(), rect.center().y()
        s = min(rect.width(), rect.height()) * 0.30
        col = T.f(tcol, 1.25)
        if t == "attack":
            IntentBadge._icon(p, QPointF(cx, cy), "attack", col)
            for i in (-1, 1):
                p.setPen(QPen(T.a(col, 150), 2.0 * k))
                p.drawLine(QPointF(cx + i * s * 1.25, cy - s * 1.5),
                           QPointF(cx + i * s * 2.0, cy + s * 1.5))
        elif t == "power":
            IntentBadge._icon(p, QPointF(cx, cy), "buff", col)
            T.chevron(p, cx, cy + s * 1.5, s * 0.9, T.a(col, 170), up=True, width=2.2 * k)
        else:
            CoverBar._cover_icon(p, QPointF(cx, cy), s * 1.05, col)
            p.setPen(QPen(T.a(col, 130), 1.6 * k))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), s * 1.7, s * 1.7)
        # 铆钉点缀
        for (dx, dy) in ((6, 6), (-6, 6), (6, -6), (-6, -6)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(T.a(T.Q_BLACK, 70)))
            p.drawEllipse(QPointF(rect.center().x() + dx * k, rect.center().y() + dy * k),
                          1.6 * k, 1.6 * k)
        T.stroke_round(p, rect, 5 * k, T.a(T.Q_BLACK, 80), 1.0)


class CardRow(QWidget):
    """卡牌行：负责悬停时把当前卡抬到最上层（Qt 的 z-order）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: List[CardView] = []


# =====================================================================
# 勋章 / 装备
# =====================================================================


class RelicView(QWidget):
    """勋章 / 装备：金属圆章 + 绶带 + 稀有度描边。"""

    clicked = pyqtSignal(str)

    def __init__(self, relic: dict, parent=None, size: int = T.RELIC_SIZE):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.relic = dict(relic or {})
        self._size = size
        self._hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"【{self.relic.get('name','')}】"
            f"  {T.RARITY_NAMES.get(self.relic.get('rarity',''), '')}\n"
            f"{T.tr(self.relic.get('text',''))}"
        )

    def enterEvent(self, ev):  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, ev):  # noqa: N802
        self._hover = False
        self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(str(self.relic.get("id", "")))

    def paintEvent(self, ev):  # noqa: N802
        r = self.relic
        if not r:
            return
        p = QPainter(self)
        T.aa(p)
        S = self._size
        c = QPointF(S / 2, S / 2)
        rad = S / 2 - 4
        rcol = T.rarity_color(r.get("rarity", "common"))

        # 绶带
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_RED_DIM, 200)))
        p.drawPolygon(QPolygonF([
            QPointF(c.x() - rad * 0.70, c.y() - rad * 1.02),
            QPointF(c.x() + rad * 0.70, c.y() - rad * 1.02),
            QPointF(c.x() + rad * 0.45, c.y() - rad * 0.52),
            QPointF(c.x() - rad * 0.45, c.y() - rad * 0.52)]))
        # 圆章
        p.setBrush(QBrush(T.a(T.Q_BLACK, 140)))
        p.drawEllipse(c + QPointF(0, 2.2), rad, rad)
        g = QRadialGradient(c + QPointF(-rad * 0.35, -rad * 0.40), rad * 2.1)
        g.setColorAt(0.0, T.f(T.mix(T.Q_STEEL, rcol, 0.45), 1.25))
        g.setColorAt(0.6, T.mix(T.Q_STEEL, rcol, 0.30))
        g.setColorAt(1.0, T.f(T.Q_PANEL_LO, 1.15))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, rad, rad)
        # 齿边
        p.setPen(QPen(T.a(T.f(rcol, 1.4), 200), 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, rad - 2.2, rad - 2.2)
        for i in range(18):
            ang = i * math.pi / 9
            p.setPen(QPen(T.a(T.f(rcol, 1.5), 150), 1.1))
            p.drawLine(QPointF(c.x() + math.cos(ang) * (rad - 2.0),
                               c.y() + math.sin(ang) * (rad - 2.0)),
                       QPointF(c.x() + math.cos(ang) * (rad - 5.0),
                               c.y() + math.sin(ang) * (rad - 5.0)))
        # 中心符号
        if r.get("rarity") == "boss":
            T.star(p, c.x(), c.y(), rad * 0.52, T.qc("#FFE9A8"))
        elif r.get("rarity") == "rare":
            T.star(p, c.x(), c.y(), rad * 0.48, T.a(T.qc("#FFF3C8"), 240))
        else:
            CoverBar._cover_icon(p, QPointF(c.x(), c.y()), rad * 0.42,
                                 T.a(T.qc("#F0E6C8"), 235))
        # 计数角标
        cnt = int(r.get("counter", -1))
        if cnt >= 0:
            fnt = T.font(T.FONT_TINY, True)
            box = QRectF(S - 17, S - 17, 15, 15)
            T.fill_round(p, box, 7.5, T.a(T.Q_BG_DEEP, 235))
            T.stroke_round(p, box, 7.5, T.a(T.Q_GOLD, 220), 1.0)
            T.text_c(p, box.center().x(), box.center().y(), str(cnt), fnt, T.Q_TEXT)
        if self._hover:
            T.glow(p, QRectF(c.x() - rad, c.y() - rad, rad * 2, rad * 2), rcol,
                   rad, strength=120, spread=5)
        p.end()


# =====================================================================
# 飘字 / 屏幕震动
# =====================================================================


class FloatText(QWidget):
    """伤害飘字：QPropertyAnimation 上升 + 淡出，自毁。"""

    def __init__(self, parent: QWidget, text: str, color: QColor,
                 font_size: int = 30, rise: int = 58, duration: int = 900,
                 outline: Optional[QColor] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._text = str(text)
        self._color = color
        self._outline = outline or T.a(T.Q_BLACK, 230)
        self._fnt = T.font(font_size, True)
        w = max(60, int(QFontMetricsF(self._fnt).horizontalAdvance(self._text) + 28))
        h = int(font_size * 1.8)
        self.resize(w, h)
        self._dy = 0.0
        self._op = 1.0
        self._a1 = QPropertyAnimation(self, b"dy", self)
        self._a1.setDuration(duration)
        self._a1.setStartValue(0.0)
        self._a1.setEndValue(-float(rise))
        self._a1.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a2 = QPropertyAnimation(self, b"op", self)
        self._a2.setDuration(duration)
        self._a2.setStartValue(1.0)
        self._a2.setKeyValueAt(0.55, 1.0)
        self._a2.setEndValue(0.0)

    def _get_dy(self) -> float:
        return self._dy

    def _set_dy(self, v: float) -> None:
        self._dy = float(v)
        self.move(self._x0, int(self._y0 + self._dy))

    dy = pyqtProperty(float, fget=_get_dy, fset=_set_dy)

    def _get_op(self) -> float:
        return self._op

    def _set_op(self, v: float) -> None:
        self._op = float(v)
        self.setWindowOpacity(1.0)
        self.update()

    op = pyqtProperty(float, fget=_get_op, fset=_set_op)

    def popup(self, x: float, y: float) -> None:
        self._x0 = int(x - self.width() / 2)
        self._y0 = int(y - self.height() / 2)
        self.move(self._x0, self._y0)
        self.show()
        self.raise_()
        self._a1.start()
        self._a2.start()
        QTimer.singleShot(self._a1.duration() + 60, self.deleteLater)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        p.setOpacity(max(0.0, min(1.0, self._op)))
        r = QRectF(0, 0, self.width(), self.height())
        T.outline_text(p, r, self._text, self._fnt, self._color, self._outline,
                       width=3.4)
        p.end()


class ShakeMixin:
    """屏幕震动：对目标 widget 的 pos 做衰减随机偏移。

    用法：``self.shake(10)``。目标必须是 QWidget 子类，且其父布局能容忍位移
    （本实现直接 move 目标自身，配合 QPropertyAnimation 结束后归位）。
    """

    def init_shake(self, target: QWidget, base_pos: Optional[QPoint] = None) -> None:
        self._shake_target = target
        self._shake_base = base_pos or target.pos()
        self._shake_anim = QPropertyAnimation(target, b"pos", target)
        self._shake_anim.setDuration(320)
        self._shake_anim.setEasingCurve(QEasingCurve.Type.OutElastic)

    def shake(self, amount: int = 10) -> None:
        tgt = getattr(self, "_shake_target", None)
        if tgt is None:
            return
        import random as _r
        base = self._shake_base
        path_pts = []
        for i in range(6):
            amp = amount * (1.0 - i / 6.0)
            path_pts.append(QPoint(int(base.x() + _r.uniform(-amp, amp)),
                                   int(base.y() + _r.uniform(-amp, amp))))
        anim = QPropertyAnimation(tgt, b"pos", tgt)
        anim.setDuration(280)
        anim.setStartValue(tgt.pos())
        anim.setEndValue(base)
        for i, pt in enumerate(path_pts):
            anim.setKeyValueAt((i + 1) / (len(path_pts) + 1.0), pt)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._shake_anim = anim


# =====================================================================
# 图标按钮
# =====================================================================


class IconButton(QWidget):
    """军事符号图标按钮（盾 / 爆裂 / 齿轮 / 十字 / 星）。"""

    clicked = pyqtSignal()

    KINDS = ("cover", "attack", "order", "medic", "star", "gear", "flag", "skull")

    def __init__(self, kind: str = "cover", parent=None, size: int = 46,
                 color: Optional[QColor] = None, tooltip: str = "",
                 label: str = ""):
        super().__init__(parent)
        self.setFixedSize(size, size if not label else size + 16)
        self.kind = kind
        self.color = color or T.Q_GOLD
        self.label = label
        self._hover = False
        self._down = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self._size = size

    def enterEvent(self, ev):  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, ev):  # noqa: N802
        self._hover = False
        self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        self._down = True
        self.update()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        if self._down and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()
        self._down = False
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        S = self._size
        r = QRectF(0, 0, S, S)
        lift = -2.0 if (self._hover and not self._down) else (1.0 if self._down else 0.0)
        r = r.translated(0, lift)
        col = T.f(self.color, 1.25 if self._hover else 1.0)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 120)))
        p.drawPath(T.round_path(r.translated(0, 3), 9))
        T.steel_plate(p, r, T.mix(T.Q_PANEL, col, 0.10 if self._hover else 0.04), 9,
                      rivets=False)
        T.stroke_round(p, r, 9, T.a(col, 235 if self._hover else 175), 1.4)

        c = r.center()
        s = S * 0.24
        if self.kind == "cover":
            CoverBar._cover_icon(p, c, s * 0.95, col)
        elif self.kind == "attack":
            IntentBadge._icon(p, c, "attack", col)
        elif self.kind == "order":
            IntentBadge._icon(p, c, "unknown", col)
        elif self.kind == "medic":
            BuffChip._glyph(p, c, "regenerate", s * 1.15)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawRect(QRectF(c.x() - s * 0.30, c.y() - s * 1.05, s * 0.60, s * 2.1))
            p.drawRect(QRectF(c.x() - s * 1.05, c.y() - s * 0.30, s * 2.1, s * 0.60))
        elif self.kind == "star":
            T.star(p, c.x(), c.y(), s * 1.05, col)
        elif self.kind == "gear":
            IntentBadge._icon(p, c, "unknown", col)
        elif self.kind == "skull":
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(c.x(), c.y() - s * 0.25), s * 0.85, s * 0.85)
            p.drawRect(QRectF(c.x() - s * 0.45, c.y() + s * 0.25, s * 0.90, s * 0.55))
            p.setBrush(QBrush(T.a(T.Q_BLACK, 230)))
            p.drawEllipse(QPointF(c.x() - s * 0.32, c.y() - s * 0.30), s * 0.24, s * 0.24)
            p.drawEllipse(QPointF(c.x() + s * 0.32, c.y() - s * 0.30), s * 0.24, s * 0.24)
        elif self.kind == "flag":
            p.setBrush(QBrush(col))
            p.drawRect(QRectF(c.x() - s * 0.95, c.y() - s * 1.15, s * 0.22, s * 2.3))
            p.drawPolygon(QPolygonF([QPointF(c.x() - s * 0.73, c.y() - s * 1.10),
                                     QPointF(c.x() + s * 1.10, c.y() - s * 0.72),
                                     QPointF(c.x() - s * 0.73, c.y() - s * 0.30)]))
        if self.label:
            T.text_c(p, S / 2, S + 8, self.label, T.font(T.FONT_TINY), T.Q_TEXT_DIM)
        p.end()


# =====================================================================
# 单位面板（可点击的敌人 / 玩家）
# =====================================================================


class UnitPanel(QWidget):
    """一个战斗单位：立绘 + 名字 + 血条 + 掩体条 + buff 行 + 意图。

    数据全部来自 ``snapshot()`` 的 dict；不触碰 core 的内部对象。
    """

    clicked = pyqtSignal(int)          # idx（敌人）/ -1（玩家）

    def __init__(self, parent=None, is_player: bool = False, idx: int = -1,
                 unit_size: int = 140):
        super().__init__(parent)
        self.is_player = is_player
        self.idx = idx
        self._dead = False
        self._hit = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor if not is_player
                       else Qt.CursorShape.ArrowCursor)
        self._unit_size = unit_size
        self.setMinimumWidth(190)
        # 立绘 + 名字 + 血条 + 掩体条 + buff 行，必须留够高度，否则血条被裁掉
        self.setMinimumHeight(unit_size + 104)

        from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(6, 2, 6, 2)
        self.v.setSpacing(2)

        self.intent = IntentBadge(self, 52)
        irow = QHBoxLayout()
        irow.setContentsMargins(0, 0, 0, 0)
        irow.addStretch(1)
        irow.addWidget(self.intent)
        irow.addStretch(1)
        self.v.addLayout(irow)

        self.art = UnitArt(self, "tank" if is_player else "generic", unit_size)
        arow = QHBoxLayout()
        arow.setContentsMargins(0, 0, 0, 0)
        arow.addStretch(1)
        arow.addWidget(self.art)
        arow.addStretch(1)
        self.v.addLayout(arow)

        self.name_lbl = QLabel("—", self)
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setObjectName("H2" if is_player else "Dim")
        self.name_lbl.setStyleSheet(
            f"font-size:{T.FONT_SMALL + 1}px; font-weight:700; color:{T.TEXT};"
            f"background:transparent;")
        self.v.addWidget(self.name_lbl)

        self.hp = HpBar(self, height=T.HPBAR_H)
        self.v.addWidget(self.hp)
        self.cover = CoverBar(self, height=15)
        self.v.addWidget(self.cover)

        self.buffs = QWidget(self)
        self.bl = QHBoxLayout(self.buffs)
        self.bl.setContentsMargins(0, 0, 0, 0)
        self.bl.setSpacing(3)
        self.bl.addStretch(1)
        self.v.addWidget(self.buffs)
        self.v.addStretch(0)

        self._buff_widgets: List[BuffChip] = []
        self._anim_hit = QPropertyAnimation(self, b"hit", self)
        self._anim_hit.setDuration(220)

    def _get_hit(self) -> float:
        return self._hit

    def _set_hit(self, v: float) -> None:
        self._hit = float(v)
        self.update()

    hit = pyqtProperty(float, fget=_get_hit, fset=_set_hit)

    # -- 内容 -------------------------------------------------------------
    def set_unit(self, d: dict, animate: bool = True) -> None:
        """d 为 snapshot 里的 player 或 enemies[i] dict。"""
        name = str(d.get("name", "—"))
        self.name_lbl.setText(name)
        self.hp.set_value(d.get("hp", 0), d.get("max_hp", 1), animate=animate)
        self.cover.set_value(d.get("block", 0), animate=animate)
        self.art.set_dead(not d.get("alive", True))
        self._dead = not d.get("alive", True)
        # buff 行
        want: Dict[str, int] = dict(d.get("buffs") or {})
        for k, v in (d.get("powers") or {}).items():
            want.setdefault(k, v)
        keys = [k for k, v in want.items() if v]
        if keys != [w.key for w in self._buff_widgets]:
            for w in self._buff_widgets:
                self.bl.removeWidget(w)
                w.deleteLater()
            self._buff_widgets = []
            for k in keys:
                chip = BuffChip(k, want[k], self)
                self.bl.insertWidget(self.bl.count() - 1, chip)
                self._buff_widgets.append(chip)
        else:
            for w in self._buff_widgets:
                v = want.get(w.key, 0)
                if v != w.amount:
                    w.amount = v
                    w.setToolTip(f"{T.buff_name(w.key)} {v}")
                    w.update()
        if not self.is_player:
            self.intent.set_intent(d.get("intent"))
            self.intent.setVisible(bool(d.get("alive", True)))

    def set_player_kind(self, kind: str, color: QColor) -> None:
        self.art.kind = kind
        self.art.color = color
        self.art.update()

    def flinch(self) -> None:
        """受击抖动：短暂左右位移。

        QPropertyAnimation 必须显式给 start/end value，否则 Qt 会打印
        "starting an animation without end value" 警告。
        """
        try:
            base = self.pos()
            anim = QPropertyAnimation(self, b"pos", self)
            anim.setDuration(170)
            anim.setStartValue(base)
            anim.setEndValue(base)
            for i, dx in enumerate((-6, 6, -4, 3)):
                anim.setKeyValueAt((i + 1) / 5.0, QPoint(base.x() + dx, base.y()))
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        except Exception:
            pass

    def enterEvent(self, ev):  # noqa: N802
        if not self.is_player and not self._dead:
            self.update()

    def leaveEvent(self, ev):  # noqa: N802
        self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        if not self.is_player and not self._dead and ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.idx)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        is_sel = bool(self.property("selected"))
        base = T.Q_PANEL if not self.is_player else T.mix(T.Q_PANEL, T.Q_GREEN, 0.08)
        T.fill_round(p, r, T.RADIUS_M, T.a(base, 205 if not self._dead else 130))
        T.stroke_round(p, r, T.RADIUS_M,
                       T.a(T.Q_GOLD, 235) if is_sel else T.a(T.Q_BORDER, 200),
                       2.0 if is_sel else 1.2)
        if is_sel:
            T.glow(p, r, T.Q_GOLD, T.RADIUS_M, strength=90, spread=5, t=0.7)
        p.end()


# =====================================================================
# 布局辅助
# =====================================================================


class Spacer(QWidget):
    def __init__(self, w: int = 0, h: int = 0, parent=None):
        super().__init__(parent)
        if w:
            self.setFixedWidth(w)
        if h:
            self.setFixedHeight(h)


def hline(parent=None, color: Optional[QColor] = None, height: int = 1) -> QWidget:
    w = QWidget(parent)
    w.setFixedHeight(height)
    w.setStyleSheet(f"background:{T.a(color or T.Q_BORDER, 200).name()};")
    return w


class SectionTitle(QWidget):
    """带军衔人字纹与横线的分区标题。"""

    def __init__(self, title: str, parent=None, color: Optional[QColor] = None):
        super().__init__(parent)
        self.title = title
        self.color = color or T.Q_GOLD
        self.setFixedHeight(30)
        # 光有高度没有宽度时，放进 QHBoxLayout 会被压成 0 宽 → 什么都画不出来。
        # 给一个基于文字长度的最小宽度，保证标题总是可见。
        try:
            fm = QFontMetricsF(T.font(T.FONT_H1, True))
            self.setMinimumWidth(int(fm.horizontalAdvance(str(title))) + 46)
        except Exception:
            self.setMinimumWidth(max(160, len(str(title)) * 22))

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        col = self.color
        T.chevron(p, 12, self.height() / 2, 7, col, up=True, width=1.7)
        fnt = T.font(T.FONT_H2 - 3, True)
        fm = QFontMetricsF(fnt)
        w = fm.horizontalAdvance(self.title)
        p.setFont(fnt)
        p.setPen(QPen(col))
        p.drawText(QRectF(26, 0, w + 8, self.height()),
                   int(Qt.AlignmentFlag.AlignLeft) | int(Qt.AlignmentFlag.AlignVCenter),
                   T.tr(self.title))
        x0 = 26 + w + 12
        if self.width() > x0 + 8:
            g = QLinearGradient(QPointF(x0, 0), QPointF(self.width(), 0))
            g.setColorAt(0.0, T.a(col, 130))
            g.setColorAt(1.0, T.a(col, 0))
            p.setPen(QPen(QBrush(g), 1.4))
            p.drawLine(QPointF(x0, self.height() / 2),
                       QPointF(self.width() - 2, self.height() / 2))
        p.end()
