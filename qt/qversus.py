"""钢铁战线 Steel Frontline — 1v1 对战界面 (qversus.py)
================================================================

局域网 1v1 的战斗界面。**既服务于单机试玩，也服务于联机对战**，
两者用同一个渲染管线，靠 ``snap`` 的来源区分：

* 联机：房主/客户端各自拿到**自己视角**的 ``snapshot_for(side)``
* 单机：直接持有 :class:`core.versus.VersusBattle`

关键安全约束
------------
对手手牌**必须只显示背面 + 数量**。``snapshot_for(side)`` 的 ``foe`` 里
根本没有 ``hand`` 键，本界面也**只读 ``hand_count``**；任何情况下都不会
去访问 ``foe["hand"]``，因此即使引擎将来出错也不会泄露。

布局（顶部两侧对称的总部耐久条）::

    ┌──────────────────────────────────────────────────────────────┐
    │ [我方 总部耐久 ▓▓▓▓░░ 62/75]  ⟳ 你的回合 0:47  [敌方 ▓▓▓░ 48/75] │
    ├───────────────────────────────────────────┬──────────────────┤
    │           对手战区                          │                  │
    │      [对方手牌背面 ×5]  [对方掩体/buff]      │   战  报          │
    │  ─────────── 地平线 ───────────             │   （滚动）        │
    │      [我方掩体/buff]                        │                  │
    ├───────────────────────────────────────────┴──────────────────┤
    │ [补给 3/3]   手牌扇形（可点击出牌）        [结束回合] [投降]     │
    └──────────────────────────────────────────────────────────────┘

面向玩家文案严格遵守附录 B.1：
格挡→**掩体**、能量→**补给**、中毒→**燃烧**、力量→**火力**、
易伤→**破甲**、虚弱→**压制**。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import math

from PyQt6.QtCore import (
    QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer,
    pyqtProperty, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import qchat  # noqa: E402
from . import qtheme as T
from core import netplay as _np
from . import qwidgets as W


def _hex(c) -> str:
    """把任意颜色值安全地转成 QSS 可用的 `#RRGGBB`。

    ``qtheme`` 里颜色常量有**两套命名**：无前缀的是 ``str``（如
    ``BORDER_HI``/``GOLD``/``GREEN``），``Q_`` 前缀的才是 ``QColor``。
    字符串上调用 ``.name()`` 会直接 AttributeError 崩掉整个界面，
    因此所有进入 QSS 的颜色都必须过这里。
    """
    try:
        if isinstance(c, QColor):
            return c.name()
        if isinstance(c, str):
            return c
        name = getattr(c, "name", None)
        if callable(name):
            return str(name())
        return str(c)
    except Exception:
        return "#000000"


# =====================================================================
# 对手手牌背面
# =====================================================================


class CardBack(QWidget):
    """一张牌背：铆接钢板 + 军徽 + 斜向警戒纹，**绝不显示牌面内容**。"""

    def __init__(self, parent=None, w: int = 46, h: int = 64, seed: int = 0):
        super().__init__(parent)
        self.setFixedSize(w, h)
        self._seed = int(seed)
        self.setToolTip("对方手牌（内容不可见）")

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        rad = max(3.0, min(r.width(), r.height()) * 0.12)

        # 投影
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 160)))
        p.drawPath(T.round_path(r.translated(0, 3), rad))

        T.steel_plate(p, r, T.mix(T.Q_PANEL, T.Q_RED, 0.16), rad, rivets=True)
        T.stroke_round(p, r, rad, T.a(T.Q_GOLD_DIM, 220), 1.4)

        # 斜向警戒纹（裁剪到圆角内）
        p.save()
        p.setClipPath(T.round_path(r, rad))
        p.setPen(QPen(T.a(T.Q_GOLD, 34), 3.0))
        step = 9.0
        x = r.left() - r.height()
        while x < r.right() + r.height():
            p.drawLine(QPointF(x, r.bottom()), QPointF(x + r.height(), r.top()))
            x += step
        p.restore()

        # 中央军徽（盾 + 星）
        c = r.center()
        s = min(r.width(), r.height()) * 0.26
        W.CoverBar._cover_icon(p, c, s * 0.92, T.a(T.Q_GOLD, 205))
        T.star(p, c.x(), c.y() + s * 0.12, s * 0.40, T.a(T.Q_BG_DEEP, 225))

        # 边缘内阴影
        T.stroke_round(p, r.adjusted(1.5, 1.5, -1.5, -1.5), rad,
                       T.a(T.Q_BLACK, 90), 1.0)
        p.end()


class CardBackRow(QWidget):
    """对手手牌：一排背面 + 「×N」数量标签。"""

    MAX_SHOWN = 7

    def __init__(self, parent=None, cw: int = 46, ch: int = 64):
        super().__init__(parent)
        self._cw, self._ch = cw, ch
        self._n = 0
        self._backs: List[CardBack] = []
        self.setFixedHeight(ch + 24)
        self.setMinimumWidth(70)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 2, 0, 0)
        self._lay.setSpacing(-int(cw * 0.42))     # 负间距 = 叠放
        self._lay.addStretch(1)
        self._lbl = QLabel("", self)
        self._lbl.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px; font-weight:700;"
            f"background:transparent;")
        self._lay.addWidget(self._lbl, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_count(self, n: int) -> None:
        n = max(0, int(n or 0))
        self._n = n
        shown = min(n, self.MAX_SHOWN)
        self._lbl.setText("  ×%d" % n if n else "")

        # 数量变化：最常见的路径，尽量原地更新
        if len(self._backs) == shown and shown > 0:
            return
        for b in self._backs:
            self._lay.removeWidget(b)
            b.setParent(None)
            b.deleteLater()
        self._backs = []
        if shown == 0:
            self._lbl.setText("  无手牌")
            return
        # 手牌多时缩小
        cw = self._cw if shown <= 5 else int(self._cw * 0.82)
        ch = int(cw * self._ch / max(1, self._cw))
        for i in range(shown):
            b = CardBack(self, cw, ch, seed=i * 7 + 3)
            self._lay.insertWidget(self._lay.count() - 2, b)
            self._backs.append(b)


# =====================================================================
# 顶部总部耐久条
# =====================================================================


class HQBar(QWidget):
    """总部耐久：大号数值 + 缓动条 + 指挥官名。

    ``mirror=True`` 时整体镜像（对手在右侧，条形从右往左生长），
    形成用户要求的「顶部两侧对称布局」。
    """

    def __init__(self, parent=None, mirror: bool = False, color: Optional[QColor] = None):
        super().__init__(parent)
        self.mirror = bool(mirror)
        self.color = color or (T.Q_GREEN if not mirror else T.Q_RED)
        self._hp, self._max = 1, 1
        self._shown = 1.0
        self._ghost = 1.0
        self._pulse = 0.0
        self._name = "—"
        self._sub = ""
        self._active = False

        self.setFixedHeight(62)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._ag = QPropertyAnimation(self, b"ghost", self)
        self._ag.setDuration(600)
        self._ag.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._as = QPropertyAnimation(self, b"shown", self)
        self._as.setDuration(200)
        self._as.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self._tick)
        self._t.start()

    # -- 动画属性 ---------------------------------------------------------
    def _get_shown(self) -> float:
        return self._shown

    def _set_shown(self, v: float) -> None:
        self._shown = float(v)
        self.update()

    shown = pyqtProperty(float, fget=_get_shown, fset=_set_shown)

    def _get_ghost(self) -> float:
        return self._ghost

    def _set_ghost(self, v: float) -> None:
        self._ghost = float(v)
        self.update()

    ghost = pyqtProperty(float, fget=_get_ghost, fset=_set_ghost)

    def _tick(self) -> None:
        ratio = self._hp / max(1, self._max)
        if ratio <= 0.30 or self._active:
            self._pulse = (self._pulse + 0.06) % (3.14159 * 2)
            self.update()

    # -- 数据 -------------------------------------------------------------
    def set_hq(self, name: str, hp: int, max_hp: int, sub: str = "",
               active: bool = False, animate: bool = True) -> None:
        hp = max(0, int(hp or 0))
        max_hp = max(1, int(max_hp or 1))
        self._name = str(name or "—")
        self._sub = str(sub or "")
        self._active = bool(active)
        new = hp / max_hp
        old = self._shown
        self._hp, self._max = hp, max_hp
        if not animate:
            self._shown = self._ghost = new
            self.update()
            return
        self._as.stop()
        self._as.setStartValue(old)
        self._as.setEndValue(new)
        self._as.start()
        if new < self._ghost:
            self._ag.stop()
            self._ag.setStartValue(self._ghost)
            self._ag.setEndValue(new)
            self._ag.start()
        else:
            self._ghost = new
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        r = QRectF(0, 0, self.width(), self.height())

        # 底板（铆接钢板）
        T.steel_plate(p, r, T.Q_PANEL, T.RADIUS_M, rivets=True)

        # 当前行动方：金边呼吸辉光
        if self._active:
            k = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._pulse))
            T.glow(p, r, T.Q_GOLD, T.RADIUS_M, strength=int(150 * k),
                   spread=7, t=self._pulse / 6.28)

        num_w = 92.0
        pad = 8.0
        # 名字 / 副标题 / 数值 的位置按镜像翻转
        if self.mirror:
            info = QRectF(r.right() - num_w - pad, r.top() + 4, num_w, r.height() - 8)
            bar_area = QRectF(r.left() + pad, r.top() + 8,
                              max(20.0, r.width() - num_w - pad * 3), r.height() - 16)
        else:
            info = QRectF(r.left() + pad, r.top() + 4, num_w, r.height() - 8)
            bar_area = QRectF(r.left() + num_w + pad * 2, r.top() + 8,
                              max(20.0, r.width() - num_w - pad * 3), r.height() - 16)

        ratio = max(0.0, min(1.0, self._hp / max(1, self._max)))
        scale_k = max(1.0, r.height() / 62.0)
        bar_h = min(bar_area.height() - 6, 20.0 * scale_k)
        bar = QRectF(bar_area.left(), bar_area.top(), bar_area.width(), bar_h)

        # 凹槽
        T.fill_round(p, bar, bar_h / 2, T.Q_PANEL_LO)
        inner = bar.adjusted(1.6, 1.6, -1.6, -1.6)

        # 残影
        gw = inner.width() * max(0.0, min(1.0, self._ghost))
        if gw > 0.5:
            gr = QRectF(inner.right() - gw if self.mirror else inner.left(),
                        inner.top(), gw, inner.height())
            T.fill_round(p, gr, inner.height() / 2, T.a(T.Q_HP_GHOST, 140))

        # 主条
        w = inner.width() * max(0.0, min(1.0, self._shown))
        if w > 0.5:
            danger = ratio <= 0.30
            pulse = (0.76 + 0.24 * (0.5 + 0.5 * math.sin(self._pulse))
                     ) if danger else 1.0
            base = T.mix(self.color, T.qc("#D14A40"), ratio * 0.55)
            br = QRectF(inner.right() - w if self.mirror else inner.left(),
                        inner.top(), w, inner.height())
            g = QLinearGradient(QPointF(br.left(), br.top()),
                                QPointF(br.left(), br.bottom()))
            g.setColorAt(0.0, T.f(base, 1.34 * pulse))
            g.setColorAt(0.45, base)
            g.setColorAt(1.0, T.f(base, 0.60 * pulse))
            T.fill_round(p, br, inner.height() / 2, QBrush(g))
            hl = QRectF(br.left() + 2, br.top() + 1.2, max(0.0, br.width() - 4),
                        br.height() * 0.30)
            if hl.width() > 2:
                T.fill_round(p, hl, hl.height() / 2, T.a(T.Q_WHITE, 52))

        # 分段刻度
        p.setPen(QPen(T.a(T.Q_BLACK, 120), 1.0))
        for i in range(1, 4):
            x = inner.left() + inner.width() * i / 4.0
            p.drawLine(QPointF(x, inner.top() + 1), QPointF(x, inner.bottom() - 1))

        T.stroke_round(p, bar, bar_h / 2, T.a(T.Q_BORDER_HI, 220), 1.2)

        # 条内文字：总部耐久
        T.text_c(p, bar.center().x(), bar.center().y(),
                 "总部耐久", T.font(max(9, T.FONT_TINY - 1), True),
                 T.a(T.Q_TEXT, 205), shadow=True)

        # 数值（大字号）
        T.text_c(p, info.center().x(), info.top() + info.height() * 0.42,
                 "%d/%d" % (self._hp, self._max),
                 T.font(max(13, T.FONT_H1 - 2), True), T.Q_TEXT, shadow=True)
        # 名字 / 副标题
        T.text_c(p, info.center().x(), info.bottom() - 10,
                 self._name if not self._sub else "%s · %s" % (self._name, self._sub),
                 T.font(max(9, T.FONT_TINY)), T.Q_TEXT_DIM)
        p.end()


# =====================================================================
# 战场一方（掩体 + buff + 手牌数）
# =====================================================================


class SidePanel(QFrame):
    """一方在战场上的状态：掩体条 + buff 芯片行 + 手牌/牌库统计。"""

    def __init__(self, parent=None, title: str = "我方", accent: Optional[QColor] = None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.accent = accent or T.Q_GREEN
        self._buffs: List[W.BuffChip] = []
        self._minions: List[QLabel] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 8)
        v.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.lbl = QLabel(title, self)
        self.lbl.setStyleSheet(
            f"color:{_hex(self.accent)}; font-size:{T.FONT_SMALL+1}px;"
            f"font-weight:800; background:transparent;")
        top.addWidget(self.lbl)
        top.addStretch(1)
        self.lbl_hand = QLabel("手牌 0", self)
        self.lbl_hand.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_TINY}px; background:transparent;")
        top.addWidget(self.lbl_hand)
        v.addLayout(top)

        # 掩体条（复用 CoverBar，显示名「掩体」）
        crow = QHBoxLayout()
        crow.setSpacing(5)
        self.lbl_cover = QLabel("掩体 0", self)
        self.lbl_cover.setFixedWidth(58)
        self.lbl_cover.setStyleSheet(
            f"color:{T.Q_BLOCK.name()}; font-size:{T.FONT_TINY}px; font-weight:700;"
            f"background:transparent;")
        crow.addWidget(self.lbl_cover)
        self.cover = W.CoverBar(self, height=14)
        crow.addWidget(self.cover, 1)
        v.addLayout(crow)

        # buff 行
        self.buff_row = QWidget(self)
        self.buff_row.setStyleSheet("background:transparent;")
        self.bl = QHBoxLayout(self.buff_row)
        self.bl.setContentsMargins(0, 0, 0, 0)
        self.bl.setSpacing(4)
        self.bl.addStretch(1)
        self._empty_buff = QLabel("暂无状态", self.buff_row)
        self._empty_buff.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px; background:transparent;")
        self.bl.insertWidget(0, self._empty_buff)
        v.addWidget(self.buff_row)

        # 附属单位（如果有）
        self.minion_row = QWidget(self)
        self.minion_row.setStyleSheet("background:transparent;")
        self.ml = QHBoxLayout(self.minion_row)
        self.ml.setContentsMargins(0, 0, 0, 0)
        self.ml.setSpacing(4)
        self.ml.addStretch(1)
        v.addWidget(self.minion_row)

        self.lbl_piles = QLabel("牌库 0 · 弃牌 0 · 移除 0", self)
        self.lbl_piles.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px; background:transparent;")
        v.addWidget(self.lbl_piles)

    def set_side(self, d: Dict, animate: bool = True,
                 show_hand_count: bool = True) -> None:
        d = d or {}
        cover = int(d.get("block", 0) or 0)
        self.lbl_cover.setText("掩体 %d" % cover)
        self.cover.set_value(cover, animate=animate)
        if show_hand_count:
            self.lbl_hand.setText("手牌 %d" % int(d.get("hand_count", 0) or 0))
        else:
            self.lbl_hand.setText("")

        # buff / 火力（powers 合并进来，与 W.UnitPanel 的取法一致）
        want: Dict[str, int] = {}
        for src in (d.get("buffs") or {}, d.get("powers") or {}):
            for k, v in src.items():
                if v:
                    want[k] = int(v)
        keys = list(want.keys())
        if keys != [b.key for b in self._buffs]:
            for b in self._buffs:
                self.bl.removeWidget(b)
                b.deleteLater()
            self._buffs = []
            for k in keys:
                chip = W.BuffChip(k, want[k], self.buff_row)
                self.bl.insertWidget(self.bl.count() - 1, chip)
                self._buffs.append(chip)
        else:
            for b in self._buffs:
                v = want.get(b.key, 0)
                if v != b.amount:
                    b.amount = v
                    b.setToolTip("%s %d" % (T.buff_name(b.key), v))
                    b.update()
        self._empty_buff.setVisible(not keys)

        # 附属单位
        mins = list(d.get("minions") or [])
        if len(mins) != len(self._minions):
            for m in self._minions:
                self.ml.removeWidget(m)
                m.deleteLater()
            self._minions = []
            for mo in mins:
                if isinstance(mo, dict):
                    txt = str(mo.get("name", "附属单位"))
                    hp = mo.get("hp")
                    if hp is not None:
                        txt += " %s" % hp
                else:
                    txt = str(mo)
                lbl = QLabel(txt, self.minion_row)
                lbl.setStyleSheet(
                    f"color:{T.GOLD}; font-size:{T.FONT_TINY}px;"
                    f"background:transparent;")
                self.ml.insertWidget(self.ml.count() - 1, lbl)
                self._minions.append(lbl)
        else:
            for lbl, mo in zip(self._minions, mins):
                if isinstance(mo, dict):
                    lbl.setText(str(mo.get("name", "附属单位")))

        self.lbl_piles.setText(
            "牌库 %d · 弃牌 %d · 移除 %d" % (
                int(d.get("draw_count", 0) or 0),
                int(d.get("discard_count", 0) or 0),
                int(d.get("exhaust_count", 0) or 0)))


# =====================================================================
# 倒计时
# =====================================================================


class TurnClock(QWidget):
    """回合倒计时：环形进度 + 秒数。最后 10 秒变红并脉冲。"""

    def __init__(self, parent=None, size: int = 68):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._total = 60.0
        self._left = 60.0
        self._pulse = 0.0
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def _tick(self) -> None:
        if self._left <= 10.5:
            self._pulse = (self._pulse + 0.09) % 6.28
            self.update()

    def set_time(self, left: float, total: float) -> None:
        try:
            self._left = max(0.0, float(left))
        except (TypeError, ValueError):
            self._left = 0.0
        try:
            self._total = max(1.0, float(total))
        except (TypeError, ValueError):
            self._total = 60.0
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = min(self.width(), self.height()) / 2 - 4
        ratio = max(0.0, min(1.0, self._left / self._total))
        danger = self._left <= 10.5

        # 底盘
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 130)))
        p.drawEllipse(c + QPointF(0, 2), R, R)
        g = QRadialGradient(c + QPointF(-R * 0.3, -R * 0.35), R * 2.0)
        g.setColorAt(0.0, T.f(T.Q_PANEL_HI, 1.30))
        g.setColorAt(0.65, T.Q_PANEL)
        g.setColorAt(1.0, T.f(T.Q_PANEL_LO, 0.92))
        p.setBrush(QBrush(g))
        p.drawEllipse(c, R, R)
        # 铆钉
        for i in range(6):
            ang = i * math.pi / 3
            pt = QPointF(c.x() + math.cos(ang) * (R - 4), c.y() + math.sin(ang) * (R - 4))
            p.setBrush(QBrush(T.a(T.Q_BLACK, 120)))
            p.drawEllipse(pt, 1.8, 1.8)

        col = T.Q_RED if danger else (T.Q_GOLD if ratio < 0.5 else T.Q_GREEN)
        if danger:
            col = T.mix(col, T.qc("#FF6B5A"), 0.5 + 0.5 * math.sin(self._pulse))
        T.wedge(p, c.x(), c.y(), R - 8, 1.0, 90.0,
                bg=T.a(T.Q_BLACK, 170), fill=T.a(T.Q_BLACK, 170), thickness=5)
        T.wedge(p, c.x(), c.y(), R - 8, ratio, 90.0,
                bg=T.a(col, 0), fill=col, thickness=5)

        if danger:
            gg = QRadialGradient(c, R * 1.2)
            gg.setColorAt(0.6, T.a(col, 0))
            gg.setColorAt(1.0, T.a(col, int(70 * (0.5 + 0.5 * math.sin(self._pulse)))))
            p.setBrush(QBrush(gg))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, R * 1.2, R * 1.2)

        secs = int(self._left + 0.999)
        T.text_c(p, c.x(), c.y() - 2, str(secs),
                 T.font(T.FONT_H2, True), T.Q_TEXT if not danger else T.qc("#FFD9D3"),
                 shadow=True)
        T.text_c(p, c.x(), c.y() + R * 0.52, "秒",
                 T.font(max(8, T.FONT_TINY - 2)), T.Q_TEXT_DIM)
        p.end()


# =====================================================================
# 战报面板
# =====================================================================


class VersusLog(QFrame):
    """对战战报（最新在上）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PanelLo")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 6, 8)
        lay.setSpacing(4)
        head = QLabel("战  报", self)
        head.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_SMALL+2}px; font-weight:700;"
            f"background:transparent;")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(head)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(
            f"QScrollArea{{background:{T.PANEL_LO};border:none;}}"
            f"QScrollArea>QWidget>QWidget{{background:{T.PANEL_LO};}}")
        self.scroll.viewport().setStyleSheet(f"background:{T.PANEL_LO};")
        self.inner = QWidget()
        self.inner.setStyleSheet(f"background:{T.PANEL_LO};")
        self.v = QVBoxLayout(self.inner)
        self.v.setContentsMargins(2, 2, 2, 2)
        self.v.setSpacing(3)
        self.v.addStretch(1)
        self.scroll.setWidget(self.inner)
        lay.addWidget(self.scroll, 1)

        self._n = -1
        self._empty = QLabel("等待开战…\n\n出牌与对方行动会实时写入此处。", self.inner)
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;"
            f"background:transparent;padding:14px;")
        self.v.insertWidget(0, self._empty)

    def set_log(self, lines: List[str]) -> None:
        lines = list(lines or [])
        if len(lines) == self._n:
            return
        self._n = len(lines)
        while self.v.count() > 2:
            it = self.v.takeAt(0)
            w = it.widget()
            if w is not None and w is not self._empty:
                w.setParent(None)
                w.deleteLater()
        for ln in reversed(lines[-60:]):
            lbl = QLabel(ln, self.inner)
            lbl.setWordWrap(True)
            # 注意：颜色常量有的是 str 有的是 QColor，必须统一为 hex 字符串，
            # 否则 f-string 会把 QColor 插成 "<QColor object ...>" 让 QSS 失效。
            col = T.TEXT_DIM
            if "伤害" in ln or "失去" in ln or "燃烧" in ln:
                col = "#D98A82"
            elif "掩体" in ln or "获得" in ln:
                col = "#9FB0C0"
            elif "胜利" in ln or "击败" in ln or "陷落" in ln or "摧毁" in ln:
                col = T.GOLD
            elif "回合" in ln:
                col = "#B9C98A"
            lbl.setStyleSheet(
                f"color:{col}; font-size:{T.FONT_TINY}px; background:transparent;")
            self.v.insertWidget(self.v.count() - 1, lbl)
        self._empty.setVisible(not lines)
        self.scroll.verticalScrollBar().setValue(0)

    def append(self, msg: str) -> None:
        """网络模式下的增量战报（房主权威 log 事件）。"""
        if not msg:
            return
        lbl = QLabel(str(msg), self.inner)
        lbl.setWordWrap(True)
        col = T.GOLD if ("胜利" in msg or "陷落" in msg) else T.TEXT_DIM
        lbl.setStyleSheet(
            f"color:{col}; font-size:{T.FONT_TINY}px; background:transparent;")
        self.v.insertWidget(self.v.count() - 1, lbl)
        self._empty.hide()
        self._n = -1
        self.scroll.verticalScrollBar().setValue(0)


# =====================================================================
# 手牌扇形（复用 qbattle.HandArea 的排布思路）
# =====================================================================


class VersusHand(QWidget):
    """我方手牌：弧形扇面 + 悬停上浮，点击出牌。

    与 ``qbattle.HandArea`` 同样的取舍：重叠量有上限，保证每张牌的
    费用与卡名始终可见；手牌过多时整体缩小而不是硬叠。
    """

    card_clicked = pyqtSignal(int)          # hand index

    MAX_OVERLAP = 0.28

    def __init__(self, parent=None):
        super().__init__(parent)
        # 必须容纳一张**全尺寸**卡（CARD_H）再加上扇面弧高与悬停上浮量，
        # 否则卡片底部会被裁掉（卡面文字被切一半）。参考 qbattle.HandArea。
        self.setMinimumHeight(T.CARD_H + 46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cards: List[W.CardView] = []
        self._hand: List[dict] = []

    def clear(self) -> None:
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []

    def set_hand(self, hand: List[dict], animate_in: bool = False) -> None:
        self._hand = list(hand or [])
        self.clear()
        for i, h in enumerate(self._hand):
            cv = W.CardView(h, self, scale=1.0, interactive=True)
            # 用下标出牌（play_card 的 card_index 是手牌下标，不是 uid）
            cv.clicked.connect(lambda _uid, k=i: self.card_clicked.emit(k))
            cv.hovered.connect(self.hover_raise)
            self.cards.append(cv)
        self._relayout()
        for c in self.cards:
            c.show()
            c.raise_()
        if animate_in and self.cards:
            for i, c in enumerate(self.cards):
                c.setWindowOpacity(0.0)
                a = QPropertyAnimation(c, b"windowOpacity", c)
                a.setDuration(200)
                a.setStartValue(0.0)
                a.setEndValue(1.0)
                a.setEasingCurve(QEasingCurve.Type.OutCubic)
                QTimer.singleShot(i * 28, a.start)

    def _relayout(self) -> None:
        n = len(self.cards)
        if n == 0:
            return
        W_, H_ = self.width(), self.height()
        cw, ch = T.CARD_W, T.CARD_H
        if W_ < 10 or H_ < 10:
            return
        scale = 1.0
        avail = W_ - 20.0
        need = cw * (1.0 - self.MAX_OVERLAP) * (n - 1) + cw
        if need > avail and n > 1:
            scale = max(0.58, avail / need)
        # 还要受高度约束：控件被压矮时必须等比缩小，否则卡底被裁。
        # 预留 12px 给扇面弧高 + 悬停上浮。
        h_fit = (H_ - 12.0) / float(ch)
        if h_fit < scale:
            scale = max(0.48, h_fit)
        cw_s, ch_s = cw * scale, ch * scale
        if n == 1:
            step = 0.0
        else:
            ideal = (avail - cw_s) / (n - 1)
            step = max(cw_s * (1.0 - self.MAX_OVERLAP),
                       min(cw_s + T.CARD_GAP, ideal))
        total = cw_s + step * (n - 1)
        x0 = max(4.0, (W_ - total) / 2.0)
        arc_h = min(16.0, max(4.0, 150.0 / max(1, n)))
        max_rot = min(4.0, 22.0 / max(1, n))
        base_y = max(0.0, H_ - ch_s - 4)
        for i, c in enumerate(self.cards):
            x = x0 + i * step
            t = 0.0 if n == 1 else (i - (n - 1) / 2.0) / ((n - 1) / 2.0)
            y = min(base_y + (t * t) * arc_h, max(0.0, H_ - ch_s))
            c.set_scale(scale)
            c.move(int(x), int(y))
            c._arc_rot = t * max_rot if n > 1 else 0.0
            c._arc_base = (int(x), int(y))

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        self._relayout()

    def hover_raise(self, uid: int) -> None:
        for c in self.cards:
            if int(c.card.get("uid", -1)) == int(uid):
                c.raise_()
            else:
                c.lower()

    def set_interactive(self, on: bool) -> None:
        for c in self.cards:
            c._interactive = bool(on)
            c.setCursor(Qt.CursorShape.PointingHandCursor if on
                        else Qt.CursorShape.ArrowCursor)
            if not on:
                c._set_lift(0.0)


# =====================================================================
# 主对战界面
# =====================================================================


class VersusScreen(QWidget):
    """1v1 对战界面。

    信号
    ----
    * ``battle_over(str)``   对局结束，参数为结果文本（"win"/"lose"/"draw"/"peer_lost"）
    * ``left_match()``      用户主动退出对战
    """

    battle_over = pyqtSignal(str)
    left_match = pyqtSignal(str)
    #: 收到一条完整性/安全事件（字典）—— App 记录并回传管理台
    integrity_event = pyqtSignal(dict)

    TICK_MS = 250          # 倒计时刷新间隔（不阻塞 UI）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.battle = None            # core.versus.VersusBattle（本地）
        self.net = None               # core.netplay.Host / Client（联机）
        self.my_side = 0
        self._snap: Dict = {}
        self._ended = False
        self._busy = False
        self._hand_sig: Tuple = ()
        self._log_len = -1
        self._last_tick = 0.0
        self._peer_lost = False
        self._mode = "local"
        self._names = ["我方", "对手"]

        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._on_tick)

        self._build()

    # =================================================================
    # 构建
    # =================================================================
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 舞台（背景） ----------
        self.stage = W.Battlefield(self, dust=36, intensity=1.0)
        self.stage.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        self.stage.setMinimumHeight(300)
        stage_lay = QVBoxLayout(self.stage)
        stage_lay.setContentsMargins(14, 8, 14, 8)
        stage_lay.setSpacing(6)

        # ---------- 顶部：双方总部耐久（对称） ----------
        self.hq_bar_frame = QFrame(self.stage)
        self.hq_bar_frame.setObjectName("Panel")
        hb = QHBoxLayout(self.hq_bar_frame)
        hb.setContentsMargins(8, 6, 8, 6)
        hb.setSpacing(10)

        self.hq_me = HQBar(self.hq_bar_frame, mirror=False, color=T.Q_GREEN)
        hb.addWidget(self.hq_me, 1)

        # 中央：回合指示 + 倒计时
        mid_col = QWidget(self.hq_bar_frame)
        mid_col.setStyleSheet("background:transparent;")
        mv = QVBoxLayout(mid_col)
        mv.setContentsMargins(4, 0, 4, 0)
        mv.setSpacing(2)
        self.lbl_turn = QLabel("回合 1", mid_col)
        self.lbl_turn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_turn.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_SMALL}px; font-weight:800;"
            f"background:transparent;")
        mv.addWidget(self.lbl_turn)
        self.clock = TurnClock(mid_col, 68)
        mv.addWidget(self.clock, 0, Qt.AlignmentFlag.AlignHCenter)
        hb.addWidget(mid_col, 0)

        self.hq_foe = HQBar(self.hq_bar_frame, mirror=True, color=T.Q_RED)
        hb.addWidget(self.hq_foe, 1)

        stage_lay.addWidget(self.hq_bar_frame, 0)

        # 当前行动方横幅
        self.lbl_phase = QLabel("我方行动", self.stage)
        self.lbl_phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_phase.setStyleSheet(
            f"color:{T.GREEN}; font-size:{T.FONT_H2}px; font-weight:800;"
            f"background:transparent;")
        stage_lay.addWidget(self.lbl_phase, 0)

        # ---------- 中段：对手区 / 我方区 + 战报 ----------
        mid = QWidget(self.stage)
        mid.setStyleSheet("background:transparent;")
        mid_lay = QHBoxLayout(mid)
        mid_lay.setContentsMargins(0, 0, 0, 0)
        mid_lay.setSpacing(10)

        col = QWidget(mid)
        col.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(col)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(7)

        # 对手区
        self.foe_box = QFrame(col)
        self.foe_box.setObjectName("Panel")
        fv = QVBoxLayout(self.foe_box)
        fv.setContentsMargins(10, 7, 10, 8)
        fv.setSpacing(5)
        frow = QHBoxLayout()
        frow.setSpacing(10)
        self.foe_panel = SidePanel(self.foe_box, "敌方指挥官", T.Q_RED)
        frow.addWidget(self.foe_panel, 1)
        backs_col = QVBoxLayout()
        backs_col.setSpacing(2)
        backs_lbl = QLabel("对方手牌（不可见）", self.foe_box)
        backs_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        backs_lbl.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;"
            f"background:transparent;")
        backs_col.addWidget(backs_lbl)
        self.foe_backs = CardBackRow(self.foe_box)
        backs_col.addWidget(self.foe_backs, 0, Qt.AlignmentFlag.AlignHCenter)
        frow.addLayout(backs_col, 0)
        fv.addLayout(frow)
        cv.addWidget(self.foe_box, 0)

        # 地平线分隔
        self.horizon = QFrame(col)
        self.horizon.setFixedHeight(2)
        self.horizon.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 transparent, stop:0.5 {_hex(T.BORDER_HI)}, stop:1 transparent);"
            f"border:none;")
        cv.addWidget(self.horizon, 0)

        # 我方区
        self.me_panel = SidePanel(col, "我方指挥部", T.Q_GREEN)
        cv.addWidget(self.me_panel, 0)
        cv.addStretch(1)
        mid_lay.addWidget(col, 1)

        self.log_panel = VersusLog(mid)
        self.log_panel.setFixedWidth(262)
        mid_lay.addWidget(self.log_panel, 0)
        stage_lay.addWidget(mid, 1)

        root.addWidget(self.stage, 1)

        # ---------- 底部：补给 + 手牌 + 按钮 ----------
        self.bottom = QFrame(self)
        self.bottom.setObjectName("Panel")
        # 底栏 = 全尺寸手牌(含扇面/上浮余量) + 上下留白，否则手牌被裁
        self.bottom.setFixedHeight(T.CARD_H + 46 + 14)
        bl = QHBoxLayout(self.bottom)
        bl.setContentsMargins(10, 4, 12, 6)
        bl.setSpacing(10)

        left = QWidget(self.bottom)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)
        self.orb = W.SupplyOrb(left, 88)
        lv.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.lbl_supply = QLabel("补给", left)
        self.lbl_supply.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_supply.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_TINY}px; background:transparent;")
        lv.addWidget(self.lbl_supply)
        bl.addWidget(left, 0)

        self.hand = VersusHand(self.bottom)
        self.hand.card_clicked.connect(self._on_card_clicked)
        bl.addWidget(self.hand, 1)

        right = QWidget(self.bottom)
        # 右侧栏改成「主按钮独占一行 + 其余两列网格」：
        # 之前 6 个按钮挤在一列、间距 6px，小的像作弊/举报按钮
        # 很难点中（用户反馈）。
        right.setMinimumWidth(240)
        right.setMaximumWidth(260)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 14, 10, 10)
        rv.setSpacing(10)

        self.btn_end = QPushButton("结 束 回 合", right)
        self.btn_end.setObjectName("Primary")
        self.btn_end.setMinimumHeight(50)
        self.btn_end.clicked.connect(self.end_turn)
        rv.addWidget(self.btn_end)

        # 次要按钮：两列
        grid_w = QWidget(right)
        self._right_grid = QGridLayout(grid_w)
        self._right_grid.setContentsMargins(0, 0, 0, 0)
        self._right_grid.setHorizontalSpacing(8)
        self._right_grid.setVerticalSpacing(8)
        rv.addWidget(grid_w)

        self.btn_leave = QPushButton("离 开 对 战", right)
        self.btn_leave.setObjectName("Ghost")
        self.btn_leave.setMinimumHeight(38)
        self.btn_leave.clicked.connect(lambda: self._leave("left"))
        self._right_grid.addWidget(self.btn_leave, 0, 0)

        # 聊天面板：**放进右侧栏布局**，跟着按钮列一起排。
        # 之前 parent=self 又没 addWidget，结果是个悬在右上角
        # 320x240 的小方块，玩家完全不知道那是什么（用户反馈）。
        try:
            self.chat = qchat.ChatPanel(right)
            self.chat.send_requested.connect(self._on_chat_send)
            self.chat.setVisible(False)
        except Exception as exc:
            print(f"[qversus] 聊天面板创建失败：{exc!r}", flush=True)
            self.chat = None

        # 聊天按钮：只在对**真人**时才显示。
        # 人机对局没有对手可聊，显示出来只会让人困惑（用户反馈）。
        self.btn_chat = QPushButton("💬 聊天", right)
        self.btn_chat.setObjectName("Ghost")
        self.btn_chat.setMinimumHeight(38)
        self.btn_chat.clicked.connect(self._toggle_chat)
        self.btn_chat.hide()
        self._right_grid.addWidget(self.btn_chat, 0, 1)

        self.btn_report = QPushButton("🚩 举报对手", right)
        self.btn_report.setObjectName("Ghost")
        self.btn_report.setMinimumHeight(38)
        self.btn_report.setToolTip(
            "遇到疑似改代码 / 作弊的对手，点这里举报。\n"
            "举报后会对他启用更严格的检测。")
        self.btn_report.clicked.connect(self._do_report)
        self.btn_report.hide()          # 默认不显示，开了真人局才显示
        self._right_grid.addWidget(self.btn_report, 1, 0)

        # 聊天面板放在按钮下面，占满剩余高度（右侧栏里的一块）
        if getattr(self, "chat", None) is not None:
            rv.addWidget(self.chat, 1)

        # ---- 房主作弊开关（仅房主可见；客户端永远没有这个面板）----
        self.cheat_box = QWidget(right)
        cb = QVBoxLayout(self.cheat_box)
        cb.setContentsMargins(0, 4, 0, 0)
        cb.setSpacing(4)
        self.btn_cheat = QPushButton("房主作弊：关", self.cheat_box)
        self.btn_cheat.setObjectName("Ghost")
        self.btn_cheat.setMinimumHeight(34)
        self.btn_cheat.setCheckable(True)
        self.btn_cheat.clicked.connect(self._toggle_host_cheats)
        cb.addWidget(self.btn_cheat)
        self.cheat_input = QLineEdit(self.cheat_box)
        self.cheat_input.setMinimumHeight(30)
        self.cheat_input.setPlaceholderText(T.tr("作弊码，回车"))
        self.cheat_input.returnPressed.connect(self._submit_cheat)
        cb.addWidget(self.cheat_input)
        self.cheat_msg = QLabel("", self.cheat_box)

        self.cheat_msg.setWordWrap(True)
        self.cheat_msg.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px; background:transparent;")
        cb.addWidget(self.cheat_msg)
        self.cheat_box.setVisible(False)      # 联机且我是房主时才显示
        rv.addWidget(self.cheat_box)

        self.hint = QLabel("点手牌出牌", right)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px; background:transparent;")
        rv.addWidget(self.hint)
        bl.addWidget(right, 0)

        root.addWidget(self.bottom, 0)

        # ---------- 结算横幅 + 遮罩 ----------
        self.banner = QLabel("", self)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet(
            f"background:{_hex(T.a(T.Q_BG_DEEP, 235))}; color:{T.GOLD};"
            f"font-size:{T.FONT_TITLE}px; font-weight:800;"
            f"border:2px solid {T.GOLD}; border-radius:12px; padding:14px 36px;")
        self.banner.hide()

        self.banner_sub = QLabel("", self)
        self.banner_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner_sub.setStyleSheet(
            f"background:transparent; color:{T.TEXT};"
            f"font-size:{T.FONT_BODY}px; font-weight:600;")
        self.banner_sub.hide()

    # =================================================================
    # 生命周期
    # =================================================================
    def start_local(self, battle, my_side: int = 0,
                    names: Optional[List[str]] = None, rng=None,
                    ai_difficulty: Optional[str] = None) -> None:
        """单机试玩 / 本地热座 / **人机对战**：直接持有 VersusBattle。

        ai_difficulty 不为 None 时启用电脑对手（接管非 my_side 的一方）。
        取值 "easy" / "normal" / "hard"，见 core/ai.py。
        """
        self.mode = "local"
        self._mode = "local"
        self.battle = battle
        self.net = None
        self.my_side = int(my_side)
        self._names = list(names or ["我方", "对手"])
        self._ai = None
        self._ai_difficulty = ai_difficulty
        if ai_difficulty and battle is not None:
            try:
                from core.ai import VersusAI
                foe_side = 1 - int(my_side)
                self._ai = VersusAI(foe_side, difficulty=ai_difficulty)
            except Exception as exc:
                print(f"[qversus] AI 初始化失败：{exc!r}", flush=True)
                self._ai = None
        self._reset()
        if self.battle is not None:
            try:
                self.battle.start_battle()
            except Exception:
                pass
        # 人机对局不显示聊天 —— 没有真人可聊
        self._set_chat_available(not bool(ai_difficulty))
        self._timer.start()
        self._sync(animate=False)

    def start_net(self, net, my_side: int, names: Optional[List[str]] = None) -> None:
        """联机对战：net 为 Host 或 Client，快照从它所处的事件里取。"""
        self.mode = "net"
        self._mode = "net"
        self._ai = None            # 联机绝不跑本地 AI
        self.net = net
        self.battle = None
        self.my_side = int(my_side)
        self._names = list(names or (["房主", "加入者"] if my_side == 0
                                     else ["房主", "加入者"]))
        self._reset()
        self._set_chat_available(True)      # 联机 -> 有真人对手
        self._timer.start()
        # 立刻拉一次快照，避免空白
        try:
            snap = net.snapshot() if hasattr(net, "snapshot") else None
            if snap:
                self.apply_snapshot(snap)
        except Exception:
            pass
        self._sync_cheat_ui()          # 房主才显示作弊面板
        self._sync(animate=False)

    #: 「准备中」最多等多久（秒）。对方一直不交卡组就提示可以重开。
    READY_TIMEOUT = 20.0
    #: 超时后每隔多久再提醒一次
    READY_WARN_EVERY = 20.0

    def _reset(self) -> None:
        self._ended = False
        self._ready_since = 0.0
        self._ready_warned = 0
        self._busy = False
        self._peer_lost = False
        self._hand_sig = ()
        self._log_len = -1
        self._snap = {}
        self.banner.hide()
        self.banner_sub.hide()
        self.log_panel.set_log([])
        self.hand.clear()
        self.foe_backs.set_count(0)
        self.lbl_phase.setText("准备中…")
        # 开始计时：对方可能永远不交卡组（掉线 / 挂机 / 根本没在）
        import time as _t
        self._ready_since = _t.time()
        self._ready_warned = 0

    def stop(self) -> None:
        self._timer.stop()

    # =================================================================
    # 网络事件
    # =================================================================
    def poll_net(self) -> None:
        """由路由的 QTimer 调用；也允许外部直接调用。"""
        if self.net is None:
            return
        try:
            events = self.net.poll() or []
        except Exception as exc:
            print(f"[qt.versus] poll failed: {exc!r}", flush=True)
            return
        for ev in events:
            try:
                self._on_net_event(ev)
            except Exception as exc:
                print(f"[qt.versus] event {ev.get('type')!r} failed: {exc!r}",
                      flush=True)
        self._drain_security_events()

    def _on_net_event(self, ev: Dict) -> None:
        t = str((ev or {}).get("type", ""))
        if t == "state":
            payload = ev.get("payload")
            if isinstance(payload, dict):
                self.apply_snapshot(payload)
        elif t == "log":
            self.log_panel.append(str(ev.get("msg", "")))
        elif t == "start":
            self._names = list(ev.get("names") or self._names)
            snap = ev.get("snapshot")
            if isinstance(snap, dict):
                self.apply_snapshot(snap)
            else:
                self._sync(animate=False)
        elif t in ("disconnected", "bye"):
            msg = str(ev.get("reason") or ev.get("msg") or "对方已断开连接。")
            self._on_peer_lost(msg)
        elif t == "cheater":
            # 房主视角：对手被判定作弊 —— 在他头顶挂「挂狗」红标签
            self._set_cheater_label(str(ev.get("label") or _np.cheat_text("label")),
                                    side=int(ev.get("side", 1)),
                                    reason=str(ev.get("reason") or ""))
        elif t == "shame":
            # 作弊者本人视角：整屏巨大红字
            self._show_shame(str(ev.get("text") or _np.cheat_text("shame")))
        elif t == "error":
            self.log_panel.append("⚠ " + str(ev.get("msg", "")))
            self.hint.setText(str(ev.get("msg", ""))[:40])

    # -------------------------------------------------- 作弊彩蛋（UI）-- #
    def _set_cheater_label(self, label: str, side: int = 1,
                           reason: str = "") -> None:
        """在作弊者头顶悬挂巨大的红色「挂狗」标签（真正的浮层控件）。"""
        try:
            self._cheater_side = int(side)
            self._cheater_label = str(label)
            self._cheater_reason = str(reason)
            lbl = getattr(self, "_cheater_tag", None)
            if lbl is None:
                lbl = QLabel(self)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                                 True)
                lbl.setStyleSheet(
                    "background:rgba(150,10,10,235);"
                    "color:#FFEDED;"
                    "border:3px solid #FF2A2A;"
                    "border-radius:8px;"
                    "font-size:30px;"
                    "font-weight:900;"
                    "letter-spacing:6px;"
                    "padding:6px 10px;")
                self._cheater_tag = lbl
            lbl.setText(str(label))
            lbl.adjustSize()
            self._place_cheater_tag()
            lbl.raise_()
            lbl.show()
            if reason:
                try:
                    self.log_panel.append("🚫 " + (_np.cheat_text("log")
                                                   % str(reason)))
                except Exception:
                    self.log_panel.append("🚫 " + str(reason))
        except Exception:
            pass

    def _place_cheater_tag(self) -> None:
        """把标签放到作弊者那一侧的顶部中间。"""
        lbl = getattr(self, "_cheater_tag", None)
        if lbl is None:
            return
        side = int(getattr(self, "_cheater_side", 1))
        w = self.width()
        bw, bh = lbl.width(), lbl.height()
        # 挂在作弊者那一侧的名牌上方，避开中央的回合/倒计时
        # （对手在上半区，自己在下方）
        if side == 1:
            x, y = 24, 10
        else:
            x, y = 24, max(10, int(self.height() * 0.45) + 4)
        lbl.setGeometry(x, y, bw, bh)

    def _show_shame(self, text: str) -> None:
        """作弊者本人：整屏巨大红字（不遮住操作，只压在最上层）。"""
        try:
            self._shame_text = str(text)
            self._shame_t = 0.0
            self._shame_on = True
            lbl = getattr(self, "_shame_overlay", None)
            if lbl is None:
                lbl = QLabel(self)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                                 True)
                lbl.setStyleSheet(
                    "background:transparent;"
                    "color:#FF2A2A;"
                    "font-size:96px;"
                    "font-weight:900;"
                    "letter-spacing:8px;")
                lbl.raise_()
                self._shame_overlay = lbl
            lbl.setText(str(text))
            lbl.setGeometry(0, 0, self.width(), self.height())
            lbl.raise_()
            lbl.show()
            if not getattr(self, "_shame_timer", None):
                from PyQt6.QtCore import QTimer as _QT
                tm = _QT(self)
                tm.timeout.connect(self._pulse_shame)
                tm.start(60)
                self._shame_timer = tm
        except Exception:
            pass

    def _pulse_shame(self) -> None:
        """红字闪烁 + 轻微缩放，让它足够显眼。"""
        if not getattr(self, "_shame_on", False):
            return
        try:
            self._shame_t += 0.06
            import math
            a = 0.55 + 0.45 * abs(math.sin(self._shame_t))
            size = int(88 + 14 * abs(math.sin(self._shame_t)))
            lbl = self._shame_overlay
            lbl.setGeometry(0, 0, self.width(), self.height())
            lbl.setStyleSheet(
                "background:transparent;"
                f"color:rgba(255,42,42,{a:.2f});"
                f"font-size:{size}px;font-weight:900;letter-spacing:8px;")
        except Exception:
            pass

    def resizeEvent(self, ev) -> None:
        try:
            super().resizeEvent(ev)
        except Exception:
            pass
        lbl = getattr(self, "_shame_overlay", None)
        if lbl is not None:
            lbl.setGeometry(0, 0, self.width(), self.height())
        self._place_cheater_tag()

    def _on_peer_lost(self, msg: str) -> None:
        """对方掉线：必须有明确提示，不能静默卡住。"""
        if self._ended:
            return
        self._peer_lost = True
        self._ended = True
        self.log_panel.append("⚠ " + msg)
        self.lbl_phase.setText("对方已断开")
        self.lbl_phase.setStyleSheet(
            f"color:{T.ORANGE}; font-size:{T.FONT_H2}px; font-weight:800;"
            f"background:transparent;")
        self._show_banner("对 方 掉 线", "本局无胜负 —— %s" % msg)
        self.hand.set_interactive(False)
        self.btn_end.setEnabled(False)
        self.battle_over.emit("peer_lost")

    # =================================================================
    # 快照
    # =================================================================
    def apply_snapshot(self, snap: Dict) -> None:
        """由网络层或本地引擎喂入一份**自己视角**的快照。"""
        if not isinstance(snap, dict) or not snap:
            return
        self._snap = snap
        self._sync(animate=True)

    def _local_snapshot(self) -> Dict:
        if self.battle is None:
            return {}
        # 优先用「我方视角」的接口
        for meth in ("snapshot_for",):
            fn = getattr(self.battle, meth, None)
            if callable(fn):
                try:
                    s = fn(self.my_side)
                    if isinstance(s, dict) and s:
                        return s
                except Exception:
                    pass
        for meth in ("snapshot",):
            fn = getattr(self.battle, meth, None)
            if callable(fn):
                try:
                    s = fn()
                    if isinstance(s, dict) and s:
                        return s
                except Exception:
                    pass
        return {}

    def _check_ready_timeout(self) -> None:
        """对方迟迟不交卡组时，给玩家明确的说明和退路。"""
        if getattr(self, "_ended", False) or getattr(self, "_peer_lost", False):
            return
        import time as _t
        since = getattr(self, "_ready_since", 0.0)
        if not since:
            return
        waited = _t.time() - since
        if waited < self.READY_TIMEOUT:
            return
        warned = getattr(self, "_ready_warned", 0)
        rounds = int((waited - self.READY_TIMEOUT) // self.READY_WARN_EVERY) + 1
        if rounds <= warned:
            return
        self._ready_warned = rounds
        mins = int(waited // 60)
        secs = int(waited % 60)
        self.lbl_phase.setText(
            "对方还没准备好（已等 %d:%02d）" % (mins, secs)
            if mins else "对方还没准备好（已等 %d 秒）" % secs)
        self.lbl_phase.setStyleSheet(
            f"color:{T.ORANGE}; font-size:{T.FONT_H2}px;"
            f"font-weight:800; background:transparent;")
        try:
            self.banner_sub.setText(
                "对方可能掉线或挂机了。可以点「离开对战」重开一局。")
            self.banner_sub.show()
        except Exception:
            pass

    def _sync(self, animate: bool = True) -> None:
        snap = self._snap if self._mode == "net" else self._local_snapshot()
        if not snap:
            # 还没有第一份快照 = 对方还没交卡组。
            # 之前这里直接 return，界面上就永远停在「准备中…」，
            # 玩家完全不知道发生了什么（真 bug：很多人以为游戏卡死）。
            self._check_ready_timeout()
            return
        self._snap = snap

        me = dict(snap.get("you") or {})
        foe = dict(snap.get("foe") or {})
        side = int(snap.get("side", self.my_side) or 0)
        cur = int(snap.get("current_side", 0) or 0)
        turn = int(snap.get("turn", 1) or 1)
        result = str(snap.get("result", "ongoing"))

        # --- 总部耐久（顶部两侧对称）---
        self.hq_me.set_hq(self._names[0] if self._names else "我方",
                          int(me.get("hp", 0) or 0), int(me.get("max_hp", 1) or 1),
                          sub="补给 %d/%d" % (int(me.get("energy", 0) or 0),
                                             int(me.get("max_energy", 3) or 3)),
                          active=(cur == side), animate=animate)
        self.hq_foe.set_hq(self._names[1] if len(self._names) > 1 else "对手",
                           int(foe.get("hp", 0) or 0), int(foe.get("max_hp", 1) or 1),
                           sub="手牌 %d" % int(foe.get("hand_count", 0) or 0),
                           active=(cur != side), animate=animate)

        # --- 回合 / 倒计时 ---
        self.lbl_turn.setText("回合 %d" % turn)
        self.clock.set_time(float(snap.get("time_left", 0) or 0),
                            float(snap.get("turn_seconds", 60) or 60))

        # --- 行动指示 ---
        my_turn = (cur == side) and result == "ongoing"
        if result == "ongoing":
            if my_turn:
                self.lbl_phase.setText("★ 我 方 行 动")
                self.lbl_phase.setStyleSheet(
                    f"color:{T.GREEN}; font-size:{T.FONT_H2}px;"
                    f"font-weight:800; background:transparent;")
            else:
                self.lbl_phase.setText("… 等 待 对 方 行 动")
                self.lbl_phase.setStyleSheet(
                    f"color:{T.ORANGE}; font-size:{T.FONT_H2}px;"
                    f"font-weight:800; background:transparent;")

        # --- 双方场上状态 ---
        self.me_panel.set_side(me, animate=animate, show_hand_count=True)
        self.foe_panel.set_side(foe, animate=animate, show_hand_count=False)
        self.foe_backs.set_count(int(foe.get("hand_count", 0) or 0))

        # --- 补给 ---
        self.orb.set_value(int(me.get("energy", 0) or 0),
                           int(me.get("max_energy", 3) or 3), animate=animate)
        self.lbl_supply.setText("补给 %d/%d" % (int(me.get("energy", 0) or 0),
                                               int(me.get("max_energy", 3) or 3)))

        # --- 手牌 ---
        hand = list(me.get("hand") or [])
        sig = tuple((h.get("uid"), h.get("cost"), h.get("playable")) for h in hand)
        if sig != self._hand_sig:
            grew = len(hand) > len(self._hand_sig)
            self._hand_sig = sig
            self.hand.set_hand(hand, animate_in=grew and animate)
        else:
            for cv, h in zip(self.hand.cards, hand):
                cv.set_card(h)

        # --- 战报 ---
        log = list(snap.get("log") or [])
        if self._mode != "net":
            self.log_panel.set_log(log)

        # --- 输入开关 ---
        can_act = my_turn and not self._ended and not self._busy
        self.btn_end.setEnabled(can_act)
        self.btn_end.setText("结 束 回 合")
        self.hand.set_interactive(can_act)
        # 逐张标记可打出（playable 已由引擎算好：够补给 + 非诅咒 + 轮到你）
        for cv in self.hand.cards:
            if not cv.card.get("playable", True):
                cv.update()
        if can_act:
            self.hint.setText("点手牌出牌 · 倒计时结束自动过回合")
        elif result == "ongoing":
            self.hint.setText("等待对方行动…")
        else:
            self.hint.setText("对局已结束")

        # --- 结算 ---
        if result != "ongoing":
            self._finish(result)
        self._place_banner()

    # =================================================================
    # 结算
    # =================================================================
    def _finish(self, result: str) -> None:
        if self._ended and not self._peer_lost:
            return
        self._ended = True
        self._timer.stop()
        self.hand.set_interactive(False)
        self.btn_end.setEnabled(False)
        side = int(self._snap.get("side", self.my_side) or 0)
        if result == "draw":
            title, sub, code = "平 局", "双方总部同时被摧毁。", "draw"
        else:
            win = (result == "a_wins" and side == 0) or (result == "b_wins" and side == 1)
            if win:
                title, sub, code = "胜 利", "对方总部已被摧毁。", "win"
            else:
                title, sub, code = "败 北", "我方总部已陷落。", "lose"
        self.lbl_phase.setText(title)
        self.lbl_phase.setStyleSheet(
            f"color:{T.GOLD if code == 'win' else T.RED};"
            f"font-size:{T.FONT_H2}px; font-weight:800; background:transparent;")
        self._show_banner(title, sub)
        self.battle_over.emit(code)

    def _show_banner(self, title: str, sub: str = "") -> None:
        self.banner.setText(title)
        self.banner_sub.setText(sub)
        self.banner.show()
        self.banner_sub.show()
        self.banner.raise_()
        self.banner_sub.raise_()
        self._place_banner()

    def _place_banner(self) -> None:
        if not self.banner.isVisible():
            return
        self.banner.adjustSize()
        self.banner_sub.adjustSize()
        w = max(self.banner.width(), self.banner_sub.width())
        x = (self.width() - self.banner.width()) // 2
        y = int(self.height() * 0.28)
        self.banner.move(x, y)
        self.banner_sub.move((self.width() - self.banner_sub.width()) // 2,
                             y + self.banner.height() + 10)

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        self._place_banner()

    # =================================================================
    # 计时 / 输入
    # =================================================================
    def _on_tick(self) -> None:
        """QTimer 驱动：推进本地引擎的限时；联机由房主权威推进。

        **绝不**用 time.sleep —— 一切节奏走 QTimer。
        """
        if self._ended:
            return
        dt = self.TICK_MS / 1000.0
        if self._mode == "local" and self.battle is not None:
            try:
                self.battle.tick(dt)
            except Exception:
                pass
            self._step_ai()
            self._sync(animate=True)
        else:
            # 联机：先推进回合计时，再轮询网络事件。
            # ⚠ 房主必须调用 net.tick() —— 回合超时是**房主权威**判定的，
            # 之前这里只 poll_net()，导致联机时倒计时永远不走、
            # 对方挂机也能无限卡住（真 bug）。
            net = self.net
            tick_fn = getattr(net, "tick", None) if net is not None else None
            # 只有房主（Host）有 tick —— 回合超时由房主权威判定
            if callable(tick_fn):
                try:
                    if tick_fn(dt):
                        # 发生了自动换手：立刻刷新界面（房主会广播 state）
                        self._sync(animate=True)
                except Exception:
                    pass
            self.poll_net()

    def _step_ai(self) -> None:
        """人机对战：轮到电脑时，每个 tick 让它走一小步。

        刻意**不**在一个 tick 里让 AI 打完整个回合 —— 那样界面会突然跳变。
        每个 tick 只走一步（出牌或结束回合），节奏交给 QTimer。
        """
        ai = getattr(self, "_ai", None)
        if ai is None or self.battle is None or self._ended:
            return
        try:
            if self.battle.result() != "ongoing":
                return
            side = int(self.battle.current_side())
            if side == int(self.my_side):
                return                    # 轮到我，别抢
            # 冷却：给动画留时间（约每 0.45 秒一步）
            self._ai_cool = getattr(self, "_ai_cool", 0) + 1
            every = max(1, int(0.45 / (self.TICK_MS / 1000.0)))
            if self._ai_cool < every:
                return
            self._ai_cool = 0
            ai.step(self.battle)
        except Exception as exc:
            print(f"[qversus] AI 出错（已忽略）：{exc!r}", flush=True)
            try:
                self._ai = None       # 出错就停掉 AI，别卡住界面
            except Exception:
                pass

    def _on_card_clicked(self, idx: int) -> None:
        if self._ended or self._busy:
            return
        snap = self._snap
        cur = int(snap.get("current_side", -1))
        if cur != int(snap.get("side", self.my_side)):
            self.hint.setText("还没轮到你行动。")
            return
        self.play_card(int(idx))

    def play_card(self, card_index: int) -> bool:
        """出牌（手牌下标）。UI 与自检脚本共用。"""
        if self._ended or self._busy:
            return False
        if not isinstance(self._snap, dict) or not self._snap:
            return False
        side = int(self._snap.get("side", self.my_side) or 0)
        hand = list((self._snap.get("you") or {}).get("hand") or [])
        if not (0 <= int(card_index) < len(hand)):
            return False
        card = hand[int(card_index)]

        # 出牌动画（卡飞向对手）
        try:
            cv = self.hand.cards[int(card_index)] if int(card_index) < len(self.hand.cards) else None
            if cv is not None:
                cv.flash()
        except Exception:
            pass

        if self._mode == "net":
            if self.net is None:
                return False
            try:
                # 客户端 → 发意图；房主 → 直接进权威引擎
                self.net.play_card(int(card_index), None)
            except Exception as exc:
                print(f"[qt.versus] net play failed: {exc!r}", flush=True)
                return False
            self.hand.set_interactive(False)   # 等权威快照回来再解锁
            self.btn_end.setEnabled(False)
            return True

        if self.battle is None:
            return False
        fn = getattr(self.battle, "play_card", None)
        if not callable(fn):
            return False
        try:
            ok = bool(fn(side, int(card_index), None))
        except Exception as exc:
            print(f"[qt.versus] play_card failed: {exc!r}", flush=True)
            return False
        if not ok:
            self._deny(card)
            return False
        self._sync(animate=True)
        return True

    def _deny(self, card: Dict) -> None:
        cost = int(card.get("cost", 0) or 0)
        self.hint.setText("补给不足（需要 %d）—— 先结束回合。" % cost
                          if cost > 0 else "这张牌现在不能打出。")
        try:
            for cv in self.hand.cards:
                if int(cv.card.get("uid", -1)) == int(card.get("uid", -2)):
                    cv._flash = 1.0
                    cv.update()
        except Exception:
            pass

    # ---------------------------------------------------- 房主作弊开关 -- #
    def _is_host(self) -> bool:
        """我是不是房主（只有房主能作弊）。"""
        return (self._mode == "net" and self.net is not None
                and getattr(self.net, "side", -1) == 0)

    def _sync_cheat_ui(self) -> None:
        """按角色显示/隐藏作弊面板。客户端永远看不到。"""
        box = getattr(self, "cheat_box", None)
        if box is None:
            return
        box.setVisible(bool(self._is_host()))
        if self._is_host():
            btn = getattr(self, "btn_cheat", None)
            if btn is not None:
                on = False
                try:
                    on = bool(self.net.cheats_enabled())
                except Exception:
                    pass
                btn.setChecked(on)
                btn.setText("房主作弊：开" if on else "房主作弊：关")

    def _toggle_host_cheats(self) -> None:
        """切换房主作弊。

        不用按钮的 isChecked() —— 它由 clicked 信号驱动，与真实状态容易不同步
        （实测开过一次后按钮与 Host 状态相反）。直接**翻转权威状态**再回写按钮。
        """
        if not self._is_host():
            return
        try:
            want = not bool(self.net.cheats_enabled())
            self.net.set_cheats(want)
        except Exception as exc:
            self._set_cheat_msg("设置失败：%s" % exc)
            return
        # 回读权威状态，保证按钮显示的就是真实开关
        try:
            real = bool(self.net.cheats_enabled())
        except Exception:
            real = want
        btn = getattr(self, "btn_cheat", None)
        if btn is not None:
            btn.setChecked(real)
            btn.setText("房主作弊：开" if real else "房主作弊：关")
        self._set_cheat_msg("作弊已开启，可输入作弊码。" if real
                            else "作弊已关闭。")

    def _set_cheat_msg(self, text: str) -> None:
        lbl = getattr(self, "cheat_msg", None)
        if lbl is not None:
            lbl.setText(str(text))

    def _submit_cheat(self) -> None:
        """提交作弊码（只有房主 + 开关打开 + 非神人模式才生效）。"""
        if not self._is_host():
            return
        box = getattr(self, "cheat_input", None)
        code = (box.text() if box is not None else "").strip()
        if not code:
            return
        try:
            ok, msg = self.net.redeem(code)
        except Exception as exc:
            ok, msg = False, "兑换失败：%s" % exc
        self._set_cheat_msg(msg)
        if ok and box is not None:
            box.clear()

    def end_turn(self) -> bool:
        if self._ended or self._busy:
            return False
        snap = self._snap or {}
        if int(snap.get("current_side", -1)) != int(snap.get("side", self.my_side)):
            self.hint.setText("现在不是你的回合。")
            return False
        if self._mode == "net":
            if self.net is None:
                return False
            try:
                self.net.end_turn()
            except Exception as exc:
                print(f"[qt.versus] net end_turn failed: {exc!r}", flush=True)
                return False
            self.btn_end.setEnabled(False)
            self.hand.set_interactive(False)
            return True
        if self.battle is None:
            return False
        fn = getattr(self.battle, "end_turn", None)
        if not callable(fn):
            return False
        try:
            ok = bool(fn(int(snap.get("side", self.my_side) or 0)))
        except Exception as exc:
            print(f"[qt.versus] end_turn failed: {exc!r}", flush=True)
            return False
        if ok:
            self._sync(animate=True)
        else:
            self.hint.setText("现在不能结束回合。")
        return ok

    def _drain_security_events(self) -> None:
        """把 netplay 抛出的安全/完整性事件转成 Qt 信号。"""
        net = getattr(self, "net", None)
        if net is None:
            return
        try:
            q = getattr(net, "_events", None)
            if q is None:
                return
            import queue as _q
            for _ in range(20):
                try:
                    ev = q.get_nowait()
                except _q.Empty:
                    break
                except Exception:
                    break
                if not isinstance(ev, dict):
                    continue
                et = ev.get("type")
                if et == "chat":
                    self._on_chat_event(ev)
                    continue
                if et == "profile":
                    self._on_profile_event(ev)
                    continue
                if et == "version_mismatch":
                    # 版本不一致：弹一个明确提示，告诉双方去更新
                    try:
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(
                            self, "版本不一致",
                            ev.get("msg") or "版本不一致，请更新到最新版。")
                    except Exception:
                        pass
                    try:
                        self.hint.setText("版本不一致，无法联机。")
                    except Exception:
                        pass
                    continue
                if et in ("integrity", "security", "timeout"):
                    info = {
                        "device": ev.get("peer_device", ""),
                        "hash": ev.get("peer_hash", ""),
                        "ip": ev.get("peer_ip", ""),
                        "name": ev.get("peer_name", ""),
                    }
                    self._last_peer_info = info
                    try:
                        self.integrity_event.emit(ev)
                    except Exception:
                        pass
        except Exception:
            pass

    def _send_my_profile(self) -> None:
        """把自己的名字 + 头衔告诉对方（联机时）。"""
        net = getattr(self, "net", None)
        if net is None or not hasattr(net, "send_profile"):
            return
        try:
            from core import account as _A
            acc = _A.load()
            if acc is None:
                return
            net.send_profile(acc.name, acc.title, acc.display())
        except Exception:
            pass

    def _toggle_chat(self) -> None:
        if getattr(self, "chat", None) is None:
            return
        c = self.chat
        if c.isVisible():
            c.hide_panel()
        else:
            c.show_panel()      # 已经在右侧栏布局里，不需要手动定位

    def _set_chat_available(self, on: bool) -> None:
        """开关「只有真人对手才有意义」的功能。

        人机对局没有对手可聊、也没人可举报 —— 这两个按钮都该隐藏。
        （用户反馈：人机对战里冒出举报和聊天，很莫名其妙。）
        """
        try:
            if on:
                self.btn_chat.show()
                self.btn_report.show()
            else:
                self.btn_chat.hide()
                self.btn_report.hide()
                c = getattr(self, "chat", None)
                if c is not None:
                    c.hide_panel()
        except Exception:
            pass

    def _on_chat_send(self, text: str) -> None:
        """把聊天发出去（联机时走 netplay）。"""
        net = getattr(self, "net", None)
        if net is None or not hasattr(net, "send_chat"):
            if getattr(self, "chat", None) is not None:
                self.chat.system("当前不是联机对局，无法发送。")
            return
        try:
            if net.send_chat(text):
                if getattr(self, "chat", None) is not None:
                    self.chat.add("我", text, mine=True)
            else:
                if getattr(self, "chat", None) is not None:
                    self.chat.system("发送失败（可能已达条数上限）。")
        except Exception as exc:
            if getattr(self, "chat", None) is not None:
                self.chat.system("发送出错：%r" % (exc,))

    def _on_chat_event(self, entry: dict) -> None:
        """收到对方的聊天。"""
        if getattr(self, "chat", None) is None:
            return
        self.chat.add(entry.get("name") or "对手",
                      entry.get("text") or "", mine=False)

    def _on_profile_event(self, entry: dict) -> None:
        """收到对方的档案（名字 / 头衔）。"""
        try:
            disp = entry.get("display") or entry.get("name") or ""
            if disp:
                self._names = list(getattr(self, "_names", ["我方", "对手"]))
                # 对手恒为 side 1
                if len(self._names) > 1:
                    self._names[1] = disp
                self._peer_display = disp
                # 刷新标题栏
                try:
                    self.tb.set_subtitle("对手：%s" % disp)
                except Exception:
                    pass
        except Exception:
            pass

    def _do_report(self) -> None:
        """举报当前对手。

        举报后：
          1. 本地记一条举报（尽量带上对方设备号 / 哈希）
          2. 通知 App 打开「严检模式」—— 之后对这名对手逐条额外校验
        """
        try:
            from PyQt6.QtWidgets import QMessageBox
            r = QMessageBox.question(
                self, "举报对手",
                "确定要举报这名对手吗？\n\n"
                "举报后系统会对他启用更严格的检测。\n"
                "恶意举报同样会被记录。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
        except Exception:
            pass

        try:
            import time as _t
            from core import integrity as I
            info = getattr(self, "_last_peer_info", {}) or {}
            I.record_violation({
                "type": "report",
                "reason": "玩家举报",
                "peer_device": info.get("device", ""),
                "peer_hash": info.get("hash", ""),
                "peer_ip": info.get("ip", ""),
                "peer_name": info.get("name", ""),
                "ts": _t.time(),
            })
        except Exception:
            pass

        try:
            self.strict_watch = True
        except Exception:
            pass
        try:
            app = self.window()
            fn = getattr(app, "on_peer_reported", None)
            if callable(fn):
                fn()
        except Exception:
            pass
        try:
            self.hint.setText("已提交举报，正在对这名对手加强检测…")
        except Exception:
            pass

    def _close_room_after_match(self) -> None:
        """对局结束后释放房间（不退出界面，只断连接）。

        为什么要做：打完之后连接一直挂着，服务器那边房间也一直占着。
        """
        net = getattr(self, "net", None)
        if net is None:
            return
        try:
            # 通知服务器我要走了
            if hasattr(net, "send_bye"):
                net.send_bye("对局结束")
            elif hasattr(net, "close"):
                net.close()
        except Exception:
            pass
        try:
            self.net = None
        except Exception:
            pass
        try:
            self.hint.setText("对局已结束，房间已关闭。")
        except Exception:
            pass
        print("[qversus] 房间已自动关闭", flush=True)

    def _leave(self, code: str) -> None:
        self._timer.stop()
        if self.net is not None:
            try:
                self.net.close()
            except Exception:
                pass
        self.left_match.emit(code)

    # =================================================================
    # 自检辅助
    # =================================================================
    def foe_hand_contents_visible(self) -> bool:
        """自检断言用：对手手牌内容永不进入渲染路径。

        返回 True 表示**存在泄露**（正常情况下恒为 False）。
        """
        snap = self._snap or {}
        foe = snap.get("foe") or {}
        if "hand" in foe:
            # 即便引擎给了 hand，本界面也从不读取；这里只报告事实
            return True
        return False
