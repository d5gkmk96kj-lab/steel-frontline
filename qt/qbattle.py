"""钢铁战线 Steel Frontline — 战斗界面 (qbattle.py)
================================================================
最核心的界面。严格按附录 A.6 的战斗节奏协议与引擎交互：

* 所有渲染数据来自 ``BattleState.snapshot()``（纯 dict，UI 只读）
* 玩家出牌 → ``battle.play_card(uid, target)``
* 结束回合 → ``battle.end_turn()``（**不执行**敌人行动，只切 phase）
* 之后 QTimer 每 400ms 调一次 ``battle.enemy_step()``：
  True = 还有敌人待行动（继续调度）；False = 敌方回合结束并已自动开新玩家回合

动画（全部 QPropertyAnimation，不阻塞主线程）：
* 手牌悬停上浮放大（CardView 内建）
* 伤害飘字（FloatText）
* 屏幕震动（ShakeMixin）
* 卡牌飞向目标（攻击牌 fly-out）与飞入（抽牌）
* 血条缓动（HpBar 内建）
* 敌人死亡淡出 + 立绘变灰
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve, QPoint, QPointF, QPropertyAnimation, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from . import qtheme as T
from . import qfx as FX
from . import qwidgets as W


# =====================================================================
# 覆盖在战场上的浮层（飘字 / 飞牌 / 震屏）
# =====================================================================


class Overlay(QWidget):
    """战斗场景的绝对定位浮层：所有特效都往这里丢。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def float_text(self, x: float, y: float, text: str, color: QColor,
                   size: int = 30, rise: int = 60) -> W.FloatText:
        ft = W.FloatText(self, text, color, font_size=size, rise=rise)
        ft.popup(x, y)
        return ft

    def fly_card(self, from_pt: QPointF, to_pt: QPointF, card: dict,
                on_done=None) -> None:
        """打出的卡飞向目标：缩小 + 淡出。"""
        w = int(T.CARD_W * 0.55)
        h = int(T.CARD_H * 0.55)
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        # 用 CardView 渲染一张小卡做精灵
        cv = W.CardView(card, scale=0.55, interactive=False)
        cv.resize(w, h)
        cv.render(pm)
        cv.deleteLater()
        sprite = QLabel(self)
        sprite.setPixmap(pm)
        sprite.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        sprite.resize(w, h)
        sprite.move(int(from_pt.x() - w / 2), int(from_pt.y() - h / 2))
        sprite.show()
        sprite.raise_()

        a1 = QPropertyAnimation(sprite, b"pos", sprite)
        a1.setDuration(240)
        a1.setStartValue(QPoint(int(from_pt.x() - w / 2), int(from_pt.y() - h / 2)))
        a1.setEndValue(QPoint(int(to_pt.x() - w / 2), int(to_pt.y() - h / 2)))
        a1.setEasingCurve(QEasingCurve.Type.InCubic)
        a2 = QPropertyAnimation(sprite, b"windowOpacity", sprite)
        a2.setDuration(240)
        a2.setStartValue(1.0)
        a2.setKeyValueAt(0.6, 0.9)
        a2.setEndValue(0.0)
        a1.finished.connect(lambda: (sprite.deleteLater(),
                                     on_done() if on_done else None))
        a1.start()
        a2.start()

    def fly_in(self, to_pt: QPointF, card: dict) -> None:
        """抽牌飞入：从牌库位置飞到目标。"""
        w = int(T.CARD_W * 0.5)
        h = int(T.CARD_H * 0.5)
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        cv = W.CardView(card, scale=0.5, interactive=False)
        cv.resize(w, h)
        cv.render(pm)
        cv.deleteLater()
        sprite = QLabel(self)
        sprite.setPixmap(pm)
        sprite.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        sprite.resize(w, h)
        sprite.move(int(to_pt.x() - w / 2), int(to_pt.y() - h / 2))
        sprite.show()
        a1 = QPropertyAnimation(sprite, b"pos", sprite)
        a1.setDuration(320)
        a1.setStartValue(QPoint(int(self.width() - 90), int(self.height() - 60)))
        a1.setEndValue(QPoint(int(to_pt.x() - w / 2), int(to_pt.y() - h / 2)))
        a1.setEasingCurve(QEasingCurve.Type.OutCubic)
        a2 = QPropertyAnimation(sprite, b"windowOpacity", sprite)
        a2.setDuration(320)
        a2.setStartValue(0.0)
        a2.setEndValue(1.0)
        a1.finished.connect(sprite.deleteLater)
        a1.start()
        a2.start()


# =====================================================================
# 手牌区
# =====================================================================


class HandArea(QWidget):
    """手牌容器：弧形扇面排布 + 悬停上浮放大。

    这是唯一需要精确控制的区域（卡牌必须重叠才能形成扇面），因此用
    ``resizeEvent`` 计算位置并 ``move()`` 每张卡；其余界面一律走 QLayout。

    可读性优先：重叠量有上限，保证每张卡**左侧的数值与卡名区域**始终可见。
    悬停时该卡会 ``raise_()`` 到最上层并放大，从而完整显示卡面。
    """

    card_clicked = pyqtSignal(int)

    #: 单卡最多被遮挡的比例。0.28 = 至少露出 72% 卡面宽度，
    #: 保证卡名的「造成 6 点伤害」这类核心数值不被邻卡压住。
    MAX_OVERLAP = 0.28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(int(T.CARD_H * 0.72) + 46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cards: List[W.CardView] = []

    def clear(self) -> None:
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []

    def set_hand(self, hand: List[dict], animate_in: bool = False) -> None:
        self.clear()
        for h in hand:
            cv = W.CardView(h, self, scale=1.0, interactive=True)
            cv.clicked.connect(self.card_clicked.emit)
            cv.hovered.connect(self.hover_raise)
            self.cards.append(cv)
        self._relayout()
        for c in self.cards:
            c.show()
            c.raise_()
        if animate_in and hand:
            for i, c in enumerate(self.cards):
                c.setWindowOpacity(0.0)
                a = QPropertyAnimation(c, b"windowOpacity", c)
                a.setDuration(200)
                a.setStartValue(0.0)
                a.setEndValue(1.0)
                a.setEasingCurve(QEasingCurve.Type.OutCubic)
                QTimer.singleShot(i * 30, a.start)

    def _relayout(self) -> None:
        """弧形扇面：中段位于弧顶，两侧下沉微旋；重叠量有上限以保证可读。"""
        n = len(self.cards)
        if n == 0:
            return
        W_, H_ = self.width(), self.height()
        cw, ch = T.CARD_W, T.CARD_H
        if W_ < 10 or H_ < 10:
            return

        # 手牌多时按可用宽度等比缩窄卡牌（而不是硬重叠），
        # 这样每张牌都能完整显示内容，玩家才读得到效果。
        scale = 1.0
        avail0 = W_ - 20.0
        need = cw * (1.0 - self.MAX_OVERLAP) * (n - 1) + cw
        if need > avail0 and n > 1:
            scale = max(0.62, avail0 / need)
        self._card_scale = scale
        cw_s = cw * scale
        ch_s = ch * scale

        if n == 1:
            step = 0.0
        else:
            ideal = (avail0 - cw_s) / (n - 1)
            step = max(cw_s * (1.0 - self.MAX_OVERLAP),
                       min(cw_s + T.CARD_GAP, ideal))

        total = cw_s + step * (n - 1)
        x0 = (W_ - total) / 2.0

        arc_h = min(18.0, max(5.0, 170.0 / max(1, n)))
        max_rot = min(4.5, 26.0 / max(1, n))
        base_y = max(0.0, H_ - ch_s - 4)

        for i, c in enumerate(self.cards):
            x = x0 + i * step
            t = 0.0 if n == 1 else (i - (n - 1) / 2.0) / ((n - 1) / 2.0)
            y = base_y + (t * t) * arc_h
            y = min(y, max(0.0, H_ - ch_s))
            c.set_scale(scale)
            c.move(int(x), int(y))
            c._arc_rot = t * max_rot if n > 1 else 0.0
            c._arc_base = (int(x), int(y))

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        self._relayout()

    def hover_raise(self, uid: int) -> None:
        for c in self.cards:
            if int(c.card.get("uid", -1)) == uid:
                c.raise_()
            else:
                c.lower()


# =====================================================================
# 战斗日志
# =====================================================================


class BattleLog(QFrame):
    """战斗日志面板（滚动，倒序最新在上）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PanelLo")
        self.setFixedWidth(268)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 6, 8)
        lay.setSpacing(4)
        head = QLabel("战 报", self)
        head.setStyleSheet(f"color:{T.GOLD}; font-size:{T.FONT_SMALL+2}px; font-weight:700;")
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
        self._n = 0
        self._empty = QLabel(
            "等待战斗记录…\n\n（出牌与敌方行动会实时写入此处）", self.inner)
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;"
            f"background:transparent;padding:14px;")
        self.v.insertWidget(0, self._empty)

    def set_log(self, lines: List[str]) -> None:
        if len(lines) == self._n:
            return
        self._n = len(lines)
        # 清空（保留末尾的 stretch 与空态提示）
        while self.v.count() > 2:
            it = self.v.takeAt(0)
            w = it.widget()
            if w and w is not self._empty:
                w.deleteLater()
        for ln in reversed(lines[-40:]):
            lbl = QLabel(ln, self.inner)
            lbl.setWordWrap(True)
            # 注意：颜色常量有的是 str 有的是 QColor，必须统一成 hex 字符串，
            # 否则 f-string 会把 QColor 插成 "<QColor object ...>" 让 QSS 解析失败。
            col = T.TEXT_DIM
            if "伤害" in ln or "失去" in ln:
                col = "#D98A82"
            elif "掩体" in ln or "获得" in ln:
                col = "#9FB0C0"
            elif "击毁" in ln or "击败" in ln or "胜利" in ln:
                col = T.GOLD
            elif "燃烧" in ln:
                col = "#D9A05B"
            lbl.setStyleSheet(f"color:{col}; font-size:{T.FONT_TINY}px;")
            self.v.insertWidget(self.v.count() - 1, lbl)
        if lines:
            self._empty.hide()
        else:
            self._empty.show()
        self.scroll.verticalScrollBar().setValue(0)


# =====================================================================
# 主战斗界面
# =====================================================================


class BattleScreen(QWidget):
    """战斗界面。

    信号
    ----
    * ``battle_finished(str)``  战斗结束（"won"/"lost"）
    * ``request_piles()``       请求打开牌库/弃牌堆/移除区查看
    """

    battle_finished = pyqtSignal(str)
    request_piles = pyqtSignal()

    STEP_MS = 400        # 附录 A.6：每 400ms 调一次 enemy_step()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.battle = None
        self.run = None
        self._snap: Dict = {}
        self._sel_enemy: int = 0
        self._busy = False                # 动画/敌方回合中，锁输入
        self._stepping = False
        self._ended = False
        self._log_len = -1
        self._hand_sig: Tuple = ()
        self._enemy_widgets: List[W.UnitPanel] = []
        self._overlay: Optional[Overlay] = None
        self._shake_off = QPoint(0, 0)

        self._timer = QTimer(self)
        self._timer.setInterval(self.STEP_MS)
        self._timer.timeout.connect(self._on_step)
        self._end_anim_timer = QTimer(self)
        self._end_anim_timer.setSingleShot(True)

        self._build()
        self._refresh_static()

    # =================================================================
    # 构建
    # =================================================================
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- 战场舞台（背景 + 单位 + 浮层）---
        self.stage = W.Battlefield(self, dust=42, intensity=1.0)
        self.stage.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 舞台上的内容用 QGridLayout 定位（不使用手工像素）
        self.stage_lay = QGridLayout(self.stage)
        self.stage_lay.setContentsMargins(16, 10, 16, 10)
        self.stage_lay.setHorizontalSpacing(10)
        self.stage_lay.setVerticalSpacing(4)

        # 顶栏：回合 / 牌库 / 弃牌 / 移除 / 勋章
        self.topbar = self._make_topbar(self.stage)
        self.stage_lay.addWidget(self.topbar, 0, 0, 1, 3)

        # 敌人行
        self.enemy_row = QWidget(self.stage)
        self.enemy_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.enemy_lay = QHBoxLayout(self.enemy_row)
        self.enemy_lay.setContentsMargins(0, 0, 0, 0)
        self.enemy_lay.setSpacing(18)
        self.enemy_lay.addStretch(1)
        # 敌人行需要完整高度（立绘+名字+血条+掩体条+buff），否则血条被裁掉
        self.enemy_row.setFixedHeight(292)
        self.enemy_row.setSizePolicy(QSizePolicy.Policy.Preferred,
                                     QSizePolicy.Policy.Minimum)
        # 敌人要"站在焦土地上"：整行下移贴住地平线，而不是浮在天空里
        self.stage_lay.addWidget(self.enemy_row, 1, 0, 1, 3,
                                 Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

        # 中段：玩家（左） + 日志（右）
        mid = QWidget(self.stage)
        mid.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        mid_lay = QHBoxLayout(mid)
        mid_lay.setContentsMargins(0, 0, 0, 0)
        mid_lay.setSpacing(10)

        self.player_panel = W.UnitPanel(mid, is_player=True, unit_size=118)
        self.player_panel.setFixedWidth(232)
        self.player_panel.set_player_kind("tank", T.Q_GREEN)
        mid_lay.addWidget(self.player_panel, 0, Qt.AlignmentFlag.AlignBottom)

        # 总部碉堡立绘（旗帜随 HP 变色）—— 画在玩家面板右侧
        self.hq = W.UnitArt(mid, "generic", 132, T.Q_STEEL)
        self.hq.setFixedSize(132, 132)
        mid_lay.addWidget(self.hq, 0, Qt.AlignmentFlag.AlignBottom)

        mid_lay.addStretch(1)
        self.log_panel = BattleLog(mid)
        self.log_panel.setFixedHeight(210)
        mid_lay.addWidget(self.log_panel, 0, Qt.AlignmentFlag.AlignTop)
        self.stage_lay.addWidget(mid, 2, 0, 1, 3)
        self.stage_lay.setRowStretch(0, 0)
        self.stage_lay.setRowStretch(1, 0)
        self.stage_lay.setRowStretch(2, 1)

        # 结束回合按钮浮在舞台右上（用布局放在顶栏右侧扩展位）
        root.addWidget(self.stage, 1)
        self.stage.setMinimumHeight(496)

        # --- 底部操作栏 ---
        self.bottom = QFrame(self)
        self.bottom.setObjectName("Panel")
        self.bottom.setFixedHeight(T.CARD_H + 64)
        bl = QHBoxLayout(self.bottom)
        bl.setContentsMargins(10, 4, 12, 6)
        bl.setSpacing(10)

        # 左：补给球 + 牌库信息
        left = QWidget(self.bottom)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(3)
        self.orb = W.SupplyOrb(left, 96)
        lv.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        self.pile_lbl = QLabel("牌库 0 · 弃牌 0 · 移除 0", left)
        self.pile_lbl.setStyleSheet(f"color:{T.TEXT_DIM}; font-size:{T.FONT_TINY}px;")
        self.pile_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lv.addWidget(self.pile_lbl)
        bl.addWidget(left, 0)

        # 中：手牌
        self.hand = HandArea(self.bottom)
        self.hand.card_clicked.connect(self._on_card_clicked)
        bl.addWidget(self.hand, 1)

        # 右：按钮列
        right = QWidget(self.bottom)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 26, 0, 0)
        rv.setSpacing(7)
        self.btn_end = QPushButton("结 束 回 合", right)
        self.btn_end.setObjectName("Primary")
        self.btn_end.setFixedWidth(150)
        self.btn_end.setMinimumHeight(46)
        self.btn_end.clicked.connect(self.end_turn)
        rv.addWidget(self.btn_end)
        self.btn_piles = QPushButton("查看牌库 / 移除区", right)
        self.btn_piles.setObjectName("Ghost")
        self.btn_piles.setFixedWidth(150)
        self.btn_piles.clicked.connect(self.request_piles.emit)
        rv.addWidget(self.btn_piles)
        self.hint = QLabel("点击敌方单位切换目标", right)
        self.hint.setStyleSheet(f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setFixedWidth(150)
        rv.addWidget(self.hint)
        bl.addWidget(right, 0)

        root.addWidget(self.bottom, 0)

        # 战斗结束横幅
        self.banner = QLabel("", self)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet(
            f"background:{T.a(T.Q_BG_DEEP, 230).name()}; color:{T.GOLD};"
            f"font-size:{T.FONT_TITLE}px; font-weight:800;"
            f"border:2px solid {T.GOLD}; border-radius:12px; padding:14px 36px;")
        self.banner.hide()

    def _make_topbar(self, parent) -> QWidget:
        bar = QFrame(parent)
        bar.setObjectName("Panel")
        bar.setMinimumHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(14)

        self.lbl_turn = QLabel("回合 1", bar)
        self.lbl_turn.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2}px; font-weight:700;")
        lay.addWidget(self.lbl_turn)

        self.lbl_phase = QLabel("我方行动", bar)
        self.lbl_phase.setStyleSheet(f"color:{T.GREEN}; font-size:{T.FONT_BODY}px;")
        lay.addWidget(self.lbl_phase)

        lay.addStretch(1)
        self.relic_row = QWidget(bar)
        self.relic_row.setSizePolicy(QSizePolicy.Policy.Preferred,
                                     QSizePolicy.Policy.Fixed)
        self.relic_lay = QHBoxLayout(self.relic_row)
        self.relic_lay.setContentsMargins(0, 0, 0, 0)
        self.relic_lay.setSpacing(5)
        lay.addWidget(self.relic_row)

        self.lbl_finish = QLabel("", bar)
        self.lbl_finish.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_BODY}px; font-weight:700;")
        lay.addWidget(self.lbl_finish)
        return bar

    def _refresh_static(self) -> None:
        self.hq.kind = "generic"
        self.hq.update()

    # =================================================================
    # 生命周期
    # =================================================================
    def start(self, run, battle) -> None:
        """开始一场战斗。"""
        self.run = run
        self.battle = battle
        self._ended = False
        self._busy = False
        self._stepping = False
        self._sel_enemy = 0
        self._log_len = -1
        self._hand_sig = ()
        self.banner.hide()
        self._clear_enemies()
        try:
            self.battle.start_battle()
        except Exception as exc:      # 引擎契约：不应抛异常；兜底防白屏
            print(f"[qt.battle] start_battle failed: {exc!r}", flush=True)
        self._build_enemies()
        self._sync(animate=False)
        self._ensure_overlay()
        self.setFocus()

    def _ensure_overlay(self) -> None:
        if self._overlay is None or self._overlay.parent() is not self.stage:
            self._overlay = Overlay(self.stage)
        self._overlay.setGeometry(self.stage.rect())
        self._overlay.raise_()

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        if self._overlay:
            self._overlay.setGeometry(self.stage.rect())
        self._place_banner()

    def _place_banner(self) -> None:
        self.banner.adjustSize()
        self.banner.move((self.width() - self.banner.width()) // 2,
                         int(self.height() * 0.30))

    def _clear_enemies(self) -> None:
        for w in self._enemy_widgets:
            self.enemy_lay.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._enemy_widgets = []

    def _build_enemies(self) -> None:
        self._clear_enemies()
        snap = self._snapshot()
        enemies = snap.get("enemies", [])
        # 敌人多时缩小立绘
        n = max(1, len(enemies))
        usize = 150 if n <= 2 else (128 if n == 3 else 108)
        for i, e in enumerate(enemies):
            up = W.UnitPanel(self.enemy_row, is_player=False, idx=i, unit_size=usize)
            kind = W.unit_kind_for(name=str(e.get("name", "")),
                                   eid=str(e.get("def_id", "")),
                                   art=str(e.get("art", "")))
            up.set_player_kind(kind, T.Q_STEEL)
            up.hp.clicked.connect(lambda i=i: self._select_enemy(i))
            up.clicked.connect(self._select_enemy)
            up.set_unit(e, animate=False)
            self.enemy_lay.insertWidget(self.enemy_lay.count() - 1, up)
            self._enemy_widgets.append(up)
        if enemies:
            self._select_enemy(min(self._sel_enemy, len(enemies) - 1))

    # =================================================================
    # 快照同步
    # =================================================================
    def _snapshot(self) -> Dict:
        if self.battle is None:
            return {}
        try:
            return self.battle.snapshot() or {}
        except Exception as exc:
            print(f"[qt.battle] snapshot failed: {exc!r}", flush=True)
            return {}

    def _sync(self, animate: bool = True) -> None:
        snap = self._snapshot()
        if not snap:
            return
        self._snap = snap

        # 顶栏
        self.lbl_turn.setText(f"回合 {int(snap.get('turn', 1))}")
        phase = str(snap.get("phase", "player"))
        ptext = {"player": "我方行动", "enemy": "敌方行动",
                 "won": "战斗胜利", "lost": "总部陷落"}.get(phase, phase)
        self.lbl_phase.setText(ptext)
        self.lbl_phase.setStyleSheet(
            f"color:{T.GREEN if phase == 'player' else T.RED};"
            f"font-size:{T.FONT_BODY}px; font-weight:600;")
        gold = int(snap.get("gold_gain", 0) or 0)
        self.lbl_finish.setText(f"缴获 {gold} 金币" if gold else "")

        # 勋章
        self._sync_relics(snap.get("relics", []))

        # 玩家
        pl = snap.get("player", {})
        self.player_panel.set_unit(pl, animate=animate)
        hp_ratio = float(pl.get("hp", 0)) / max(1, float(pl.get("max_hp", 1)))
        self.player_panel.art.color = T.Q_GREEN
        self.player_panel.art.update()

        # 总部碉堡：用 QPainter 单独画，旗帜随 HP 变色
        self.hq.set_kind("__hq__")
        self.hq.color = T.Q_STEEL
        self.hq._hq_ratio = hp_ratio

        # 敌人
        enemies = snap.get("enemies", [])
        if len(enemies) != len(self._enemy_widgets):
            self._build_enemies()
        for i, e in enumerate(enemies):
            if i < len(self._enemy_widgets):
                self._enemy_widgets[i].set_unit(e, animate=animate)
                if e.get("alive", True):
                    kind = W.unit_kind_for(name=str(e.get("name", "")),
                                           eid=str(e.get("def_id", "")),
                                           art=str(e.get("art", "")))
                    self._enemy_widgets[i].set_player_kind(kind, T.Q_STEEL)

        # 补给 / 牌堆
        self.orb.set_value(pl.get("energy", 0), pl.get("max_energy", 3),
                           animate=animate)
        self.pile_lbl.setText(
            f"牌库 {int(snap.get('draw_count', 0))} · "
            f"弃牌 {int(snap.get('discard_count', 0))} · "
            f"移除 {int(snap.get('exhaust_count', 0))}")

        # 手牌（只在 uid/cost/playable 变化时重建，避免打断悬停动画）
        hand = snap.get("hand", [])
        sig = tuple((h.get("uid"), h.get("cost"), h.get("playable")) for h in hand)
        if sig != self._hand_sig:
            grew = len(hand) > len(self._hand_sig)
            self._hand_sig = sig
            self.hand.set_hand(hand, animate_in=grew and animate)
        else:
            for cv, h in zip(self.hand.cards, hand):
                cv.set_card(h)

        # 日志
        self.log_panel.set_log(list(snap.get("log", [])))

        # 按钮状态（战斗结束 / 已被击杀时一律锁死输入）
        if self._ended:
            phase = "done"
        phase_ok = phase == "player" and not self._busy and not self._ended
        self.btn_end.setEnabled(phase_ok)
        self.btn_end.setText("结 束 回 合")
        for cv in self.hand.cards:
            cv._interactive = phase_ok
            cv.setCursor(Qt.CursorShape.PointingHandCursor if phase_ok
                         else Qt.CursorShape.ArrowCursor)
            if not phase_ok:
                cv._set_lift(0.0)

        self._place_banner()

    def _sync_relics(self, relics: List[dict]) -> None:
        cur = len(self.relic_lay)
        if cur == len(relics) and cur > 0:
            for i, r in enumerate(relics):
                it = self.relic_lay.itemAt(i)
                if it and it.widget():
                    it.widget().relic = dict(r)
                    it.widget().setToolTip(
                        f"【{r.get('name','')}】"
                        f"  {T.RARITY_NAMES.get(r.get('rarity',''), '')}\n{r.get('text','')}")
            return
        while self.relic_lay.count():
            it = self.relic_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        # 勋章太多时缩小
        n = len(relics)
        size = T.RELIC_SIZE if n <= 12 else (36 if n <= 18 else 30)
        for r in relics:
            rv = W.RelicView(r, self.relic_row, size=size)
            self.relic_lay.addWidget(rv)

    # =================================================================
    # 交互
    # =================================================================
    def _select_enemy(self, idx: int) -> None:
        self._sel_enemy = int(idx)
        for i, w in enumerate(self._enemy_widgets):
            w.setProperty("selected", i == self._sel_enemy)
            w.style().unpolish(w)
            w.update()

    def _target(self):
        """当前选中的敌人 Combatant 对象（play_card 接受对象或 uid）。"""
        if self.battle is None:
            return None
        alive = [e for e in self.battle.enemies if e.alive()]
        if not alive:
            return None
        if 0 <= self._sel_enemy < len(self.battle.enemies):
            e = self.battle.enemies[self._sel_enemy]
            if e.alive():
                return e
        return alive[0]

    def _on_card_clicked(self, uid: int) -> None:
        if self.battle is None or self._busy or self._ended:
            return
        if self.battle.phase != "player":
            return
        self.play_card(uid)

    def play_card(self, uid: int) -> bool:
        """打出一张牌（会被无头遍历脚本直接调用）。"""
        if self.battle is None or self._ended or self._busy:
            return False
        snap = self._snap or self._snapshot()
        card = None
        for h in snap.get("hand", []):
            if int(h.get("uid", -1)) == int(uid):
                card = h
                break
        if card is None:
            return False
        if not self.battle.can_play(uid):
            self._deny_feedback(card)
            return False

        pre = dict(snap.get("player", {}))
        tgt = self._target()
        card_widget = next((c for c in self.hand.cards
                            if int(c.card.get("uid", -1)) == int(uid)), None)

        ok = False
        try:
            ok = bool(self.battle.play_card(uid, tgt))
        except Exception as exc:
            print(f"[qt.battle] play_card failed: {exc!r}", flush=True)
            ok = False
        if not ok:
            self._deny_feedback(card)
            return False

        # 出牌动画：卡飞向目标 + 闪光
        if card_widget is not None and self._overlay is not None:
            fp = self._to_stage(card_widget, QPoint(card_widget.width() // 2,
                                                    card_widget.height() // 2))
            from_pt = fp if fp is not None else QPoint(0, 0)
            to_pt = None
            if tgt is not None:
                try:
                    ei = self.battle.enemies.index(tgt)
                    if 0 <= ei < len(self._enemy_widgets):
                        tw = self._enemy_widgets[ei]
                        tp = self._to_stage(tw, QPoint(tw.width() // 2, tw.height() // 2))
                        if tp is not None:
                            to_pt = tp
                except ValueError:
                    to_pt = None
            if to_pt is None:
                to_pt = QPointF(self.stage.width() / 2, self.stage.height() * 0.7)
            self._overlay.fly_card(QPointF(from_pt), QPointF(to_pt), card)

        self._after_action(pre)
        # 关键：玩家这一击可能已把最后一个敌人打死，引擎内部会把 phase 设成 "won"。
        # 不检查的话 UI 会永远停在玩家回合，无法进入结算。
        self._check_end()

        # 敌人受击反馈
        if tgt is not None:
            try:
                ei = self.battle.enemies.index(tgt)
                if 0 <= ei < len(self._enemy_widgets):
                    self._enemy_widgets[ei].flinch()
            except ValueError:
                pass
        return True

    def _deny_feedback(self, card: dict) -> None:
        reason = "补给不足" if not card.get("playable", True) else "无法打出"
        self.lbl_phase.setText(f"{reason}")
        QTimer.singleShot(700, lambda: self._sync(animate=False))

    def _after_action(self, pre_player: dict) -> None:
        """出牌后：飘字 + 震屏 + 刷新。"""
        snap = self._snapshot()
        pl = snap.get("player", {})
        dmg_to_player = max(0, int(pre_player.get("hp", 0)) - int(pl.get("hp", 0)))
        heal = max(0, int(pl.get("hp", 0)) - int(pre_player.get("hp", 0)))
        block_gain = max(0, int(pl.get("block", 0)) - int(pre_player.get("block", 0)))
        self._sync(animate=True)
        if self._overlay is None:
            return
        cx = self._to_stage(self.player_panel,
                            QPoint(self.player_panel.width() // 2, 40))
        if cx is None:
            return
        if block_gain:
            self._overlay.float_text(cx.x(), cx.y(), f"掩体 +{block_gain}",
                                     T.Q_BLOCK, size=22, rise=42)
            FX.block_effect(self._overlay, cx.x(), cx.y() - 10)
        if dmg_to_player:
            self._overlay.float_text(cx.x(), cx.y() - 16, f"-{dmg_to_player}",
                                     T.RED, size=30, rise=58)
            self._screen_shake(9)
            # 总部挨打：红色火花 + 震屏
            FX.hit_effect(self._overlay, cx.x(), cx.y() - 4, T.RED,
                          power=min(1.8, 0.6 + dmg_to_player / 18.0))
        if heal:
            self._overlay.float_text(cx.x(), cx.y() - 16, f"+{heal}",
                                     T.GREEN, size=26, rise=50)
        # 敌人掉血飘字
        for i, e in enumerate(snap.get("enemies", [])):
            if i >= len(self._enemy_widgets):
                break
            w = self._enemy_widgets[i]
            pt = self._to_stage(w, QPoint(w.width() // 2, int(w.height() * 0.35)))
            if pt is None:
                continue
            if not e.get("alive", True) and w.property("hit") != -1:
                self._overlay.float_text(pt.x(), pt.y(), "击 毁", T.GOLD,
                                         size=26, rise=52)
                # 击毁：来一发大的
                FX.hit_effect(self._overlay, pt.x(), pt.y() - 6,
                              T.Q_GOLD, power=1.7)
                w.setProperty("hit", -1)
            elif e.get("hp") is not None and getattr(w, "_last_hp", None) is not None:
                d = int(w._last_hp) - int(e.get("hp", 0))
                if d > 0:
                    self._overlay.float_text(pt.x(), pt.y(), f"-{d}", T.RED,
                                             size=28, rise=54)
                    # 伤害越高火花越大：0.6 小 / 1.0 中 / 1.6+ 大
                    FX.hit_effect(self._overlay, pt.x(), pt.y() + 4,
                                  T.Q_GOLD if d < 20 else T.RED,
                                  power=min(2.0, 0.55 + d / 22.0))
        for i, e in enumerate(snap.get("enemies", [])):
            if i < len(self._enemy_widgets):
                self._enemy_widgets[i]._last_hp = int(e.get("hp", 0))

    def _to_stage(self, w: QWidget, pt: QPoint) -> Optional[QPoint]:
        """把控件坐标安全地映射到舞台坐标系。

        Qt 的 ``mapTo`` 要求目标必须是祖先；布局调整期间父子链可能临时变化，
        直接调用会打印 "parent must be in parent hierarchy" 警告。
        这里统一做一次祖先检查 + 兜底为控件中心。
        """
        try:
            if self._is_ancestor(self.stage, w):
                return w.mapTo(self.stage, pt)
        except Exception:
            pass
        try:
            if self._is_ancestor(self.stage, w):
                return w.mapTo(self.stage, QPoint(w.width() // 2, w.height() // 2))
        except Exception:
            pass
        return None

    @staticmethod
    def _is_ancestor(anc: QWidget, w: QWidget) -> bool:
        p = w
        while p is not None:
            if p is anc:
                return True
            p = p.parentWidget()
        return False

    def _screen_shake(self, amount: int) -> None:
        if self._overlay is None:
            return
        import random as _r
        base = self.stage.pos()
        anim = QPropertyAnimation(self.stage, b"pos", self.stage)
        anim.setDuration(300)
        anim.setStartValue(base)
        anim.setEndValue(base)
        n = 6
        for i in range(n):
            amp = amount * (1.0 - i / float(n))
            anim.setKeyValueAt((i + 1) / (n + 1.0),
                               QPoint(int(base.x() + _r.uniform(-amp, amp)),
                                      int(base.y() + _r.uniform(-amp, amp))))
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    # =================================================================
    # 回合流转（附录 A.6）
    # =================================================================
    def end_turn(self) -> None:
        if self.battle is None or self._ended or self._busy:
            return
        if self.battle.phase != "player":
            return
        self._busy = True
        self.btn_end.setEnabled(False)
        try:
            self.battle.end_turn()      # 只切 phase，不执行敌人行动
        except Exception as exc:
            print(f"[qt.battle] end_turn failed: {exc!r}", flush=True)
        self._sync(animate=True)
        # 敌方回合开始：每 400ms 驱动一个敌人行动
        if self.battle.phase == "enemy":
            self.lbl_phase.setText("敌方行动")
            self._stepping = True
            self._timer.start()
        else:
            self._busy = False
            self._check_end()

    def _on_step(self) -> None:
        """每 400ms 推进一步敌人行动。"""
        if self.battle is None:
            self._timer.stop()
            return
        pre = dict(self._snapshot().get("player", {}))
        more = False
        try:
            more = bool(self.battle.enemy_step())
        except Exception as exc:
            print(f"[qt.battle] enemy_step failed: {exc!r}", flush=True)
            more = False
        snap = self._snapshot()
        # 敌人打玩家的飘字 / 震屏
        pl = snap.get("player", {})
        dmg = max(0, int(pre.get("hp", 0)) - int(pl.get("hp", 0)))
        blk = max(0, int(pre.get("block", 0)) - int(pl.get("block", 0)))
        self._sync(animate=True)
        if self._overlay is not None:
            cx = self._to_stage(self.player_panel,
                                QPoint(self.player_panel.width() // 2, 36))
            if cx is None:
                cx = QPoint(self.stage.width() // 4, int(self.stage.height() * 0.6))
            if dmg:
                self._overlay.float_text(cx.x(), cx.y(), f"-{dmg}", T.RED,
                                         size=32, rise=60)
                self._screen_shake(11)
            elif blk:
                self._overlay.float_text(cx.x(), cx.y(), f"掩体 -{blk}", T.Q_BLOCK,
                                         size=20, rise=40)
        if not more:
            self._timer.stop()
            self._stepping = False
            self._busy = False
            self._sync(animate=True)
            self._check_end()

    def _check_end(self) -> None:
        if self.battle is None or self._ended:
            return
        res = "ongoing"
        try:
            res = self.battle.result()
        except Exception:
            res = "ongoing"
        # 引擎在击杀瞬间就把 phase 置为 won/lost；以 phase 为准更及时。
        if res == "ongoing":
            ph = str(getattr(self.battle, "phase", "player"))
            if ph in ("won", "lost"):
                res = ph
        if res in ("won", "lost"):
            self._ended = True
            self._timer.stop()
            self._busy = False
            self.banner.setText("战 斗 胜 利" if res == "won" else "总 部 陷 落")
            self.banner.setStyleSheet(
                f"background:{T.a(T.Q_BG_DEEP, 235).name()};"
                f"color:{T.GOLD if res == 'won' else T.RED};"
                f"font-size:{T.FONT_TITLE}px; font-weight:800;"
                f"border:2px solid {T.GOLD if res == 'won' else T.RED};"
                f"border-radius:12px; padding:14px 36px;")
            self.banner.show()
            self.banner.raise_()
            self._place_banner()
            self._busy = False
            self._stepping = False
            self._sync(animate=True)
            QTimer.singleShot(1150, lambda: self.battle_finished.emit(res))

    def auto_play_step(self) -> bool:
        """无头验收用：打一张能打的牌，否则结束回合。返回是否战斗仍在进行。"""
        if self.battle is None:
            return False
        if self._ended:
            return False
        snap = self._snapshot()
        if snap.get("phase") == "player":
            for h in snap.get("hand", []):
                if self.battle.can_play(h["uid"]):
                    self.play_card(h["uid"])
                    break
            else:
                self.end_turn()
                # 无头：直接把敌方回合跑完
                guard = 0
                while self.battle.phase == "enemy" and guard < 200:
                    if not self.battle.enemy_step():
                        break
                    guard += 1
                self._busy = False
                self._sync(animate=False)
                self._check_end()
        return not self._ended

    def stop(self) -> None:
        self._timer.stop()
        self._stepping = False


# ---------------------------------------------------------------------
# 让 UnitArt 支持总部碉堡（在 UnitArt.paintEvent 里按 kind 分派）
# 这里用补丁方式注入，避免 qwidgets 反向依赖 qbattle。
# ---------------------------------------------------------------------
_orig_paint = W.UnitArt.paintEvent


def _unitart_paint(self, ev):  # noqa: N802
    if getattr(self, "kind", "") == "__hq__":
        p = QPainter(self)
        T.aa(p)
        W_, H_ = self.width(), self.height()
        cx, cy = W_ / 2, H_ / 2
        s = min(W_, H_) / 3.1
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 70)))
        p.drawEllipse(QPointF(cx, H_ - 10), s * 1.15, s * 0.26)
        W.draw_hq(p, cx, cy, s, self.color, float(getattr(self, "_hq_ratio", 1.0)))
        p.end()
        return
    _orig_paint(self, ev)


W.UnitArt.paintEvent = _unitart_paint
