"""钢铁战线 Steel Frontline — 其余界面 (qscreens.py)
================================================================
主菜单 / 卡牌奖励 / 补给站 / 战地医院 / 事件 / 牌组 / 结算(胜负) /
图鉴 / 成就 / 设置 / 牌堆查看。

设计约定
--------
* 一律 QLayout + QSS 布局；只有卡牌、勋章、地图这类需要自绘的控件用 QPainter。
* 所有数据来自 core 的公开接口；不触碰内部字段。
* 每个界面都是独立 QWidget，由 qapp.MainWindow 做路由。
"""

from __future__ import annotations

import os
import sys

from typing import Dict, List, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import qtheme as T
try:
    from core import i18n as _i18n
except Exception:
    class _I:
        LANG_ORDER = ("zh",)
        LANG_NAMES = {"zh": "中文"}
        @staticmethod
        def lang(): return "zh"
        @staticmethod
        def set_lang(c): return c
    _i18n = _I()

# 统一动画帧长（60fps）。所有装饰性动画共用它，避免不同 timer 周期
# 互相拖慢导致「锁帧」观感（用户实测：40~60ms 会把整机压到 20~25fps）。
_FRAME_MS = 16

from . import qwidgets as W


# =====================================================================
# 共用小件
# =====================================================================


class TitleBar(QWidget):
    """页面标题：军衔人字纹 + 大标题 + 副标题 + 底部金线。"""

    def __init__(self, title: str, subtitle: str = "", parent=None,
                 color: Optional[QColor] = None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.color = color or T.Q_GOLD
        self.setFixedHeight(64)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        W_, H_ = self.width(), self.height()
        T.chevron(p, 16, H_ / 2 - 3, 11, self.color, up=True, width=2.6)
        T.chevron(p, 16, H_ / 2 + 12, 11, T.a(self.color, 150), up=True, width=2.0)
        fnt = T.font(T.FONT_H1, True)
        p.setFont(fnt)
        p.setPen(QPen(self.color))
        fm = QFontMetricsF(fnt)
        p.drawText(QRectF(40, 2, W_ - 50, 34),
                   int(Qt.AlignmentFlag.AlignLeft) | int(Qt.AlignmentFlag.AlignVCenter),
                   T.tr(self.title))
        if self.subtitle:
            p.setFont(T.font(T.FONT_SMALL))
            p.setPen(QPen(T.Q_TEXT_DIM))
            p.drawText(QRectF(42, 34, W_ - 52, 20),
                       int(Qt.AlignmentFlag.AlignLeft) | int(Qt.AlignmentFlag.AlignVCenter),
                       T.tr(self.subtitle))
        g = QLinearGradient(QPointF(0, H_ - 3), QPointF(W_, H_ - 3))
        g.setColorAt(0.0, T.a(self.color, 210))
        g.setColorAt(0.65, T.a(self.color, 60))
        g.setColorAt(1.0, T.a(self.color, 0))
        p.setPen(QPen(QBrush(g), 2.0))
        p.drawLine(QPointF(4, H_ - 2), QPointF(W_ - 4, H_ - 2))
        p.end()


class CardScroll(QScrollArea):
    """卡牌滚动区，支持**横向单行**与**纵向多行网格**两种模式。

    ``vertical=False``：奖励 / 商店这类少量卡牌，单行横排（默认）。
    ``vertical=True`` ：牌组 / 图鉴这类几十上百张卡，**必须**用多行网格，
    否则 135 张卡会被排成一条上万像素的横线，屏幕上什么都看不到。
    """

    card_picked = pyqtSignal(int, object)     # index, payload

    def __init__(self, parent=None, card_scale: float = 1.0, vertical: bool = False,
                 cols: int = 8):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QScrollArea{{background:transparent;border:none;}}"
            f"QScrollArea>QWidget>QWidget{{background:transparent;}}")
        self.viewport().setStyleSheet("background:transparent;")
        self._scale = card_scale
        self._vertical = bool(vertical)
        self._cols = max(1, int(cols))
        self._inner = QWidget()
        self._inner.setStyleSheet("background:transparent;")
        if self._vertical:
            self._lay = QGridLayout(self._inner)
        else:
            self._lay = QHBoxLayout(self._inner)
        self._lay.setContentsMargins(10, 10, 10, 10)
        self._lay.setSpacing(14)
        if not self._vertical:
            self._lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self._inner)
        if self._vertical:
            # 多行网格需要"内容高于视口 -> 纵向滚动"。
            # setWidgetResizable(True) 会把 inner 压成视口高度，必须让 inner
            # 有自己的最小高度，否则 134 张卡会被压缩到看不见。
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards: List[W.CardView] = []
        self._entries: List[Tuple[QWidget, dict, object, str]] = []

    def set_cards(self, cards: List[dict], payloads: Optional[List] = None,
                  extra: Optional[Dict[int, str]] = None,
                  footer: bool = True) -> None:
        """extra: index -> 底部标注文字（价格 / 状态）。"""
        while self._lay.count():
            it = self._lay.takeAt(0)
            wd = it.widget()
            if wd:
                wd.setParent(None)
                wd.deleteLater()
        self.cards = []
        self._entries = []

        if not cards:
            empty = QLabel("（暂无内容）", self._inner)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color:{T.TEXT_MUTED}; font-size:{T.FONT_BODY}px;"
                f"background:transparent;padding:40px;")
            if self._vertical:
                self._lay.addWidget(empty, 0, 0, 1, self._cols)
            else:
                self._lay.addWidget(empty)
            return

        for i, cd in enumerate(cards):
            holder = QWidget(self._inner)
            holder.setStyleSheet("background:transparent;")
            hv = QVBoxLayout(holder)
            hv.setContentsMargins(0, 0, 0, 0)
            hv.setSpacing(5)
            cv = W.CardView(cd, holder, scale=self._scale, interactive=True)
            idx = i
            cv.clicked.connect(lambda _uid, k=idx: self._pick(k, payloads))
            hv.addWidget(cv, 0, Qt.AlignmentFlag.AlignHCenter)
            if footer and extra and idx in extra:
                lbl = QLabel(str(extra[idx]), holder)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet(
                    f"color:{T.GOLD}; font-size:{T.FONT_SMALL}px; font-weight:700;"
                    f"background:transparent;")
                hv.addWidget(lbl)
            if self._vertical:
                self._lay.addWidget(holder, i // self._cols, i % self._cols,
                                    Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
                self._lay.setRowStretch(i // self._cols + 1, 0)
            else:
                self._lay.addWidget(holder)
            self.cards.append(cv)
            self._entries.append((holder, cd, payloads[i] if payloads and i < len(payloads) else None,
                                  (extra or {}).get(i, "")))

        self._apply_inner_height()

    def _apply_inner_height(self) -> None:
        """设定 inner 的最小尺寸，避免被 setWidgetResizable 压扁。"""
        n = len(self.cards)
        if n == 0:
            return
        if not self._vertical:
            cw = max(1, int(T.CARD_W * self._scale))
            ch = max(1, int(T.CARD_H * self._scale))
            need_w = n * (cw + 14) + 24
            need_h = ch + 44
            self._inner.setMinimumSize(need_w, need_h)
            self._inner.resize(need_w, need_h)
            return
        rows = (n + self._cols - 1) // self._cols
        cw = max(1, int(T.CARD_W * self._scale))
        ch = max(1, int(T.CARD_H * self._scale))
        vw = max(1, self.viewport().width())
        cols = max(1, min(self._cols, max(1, (vw - 24) // (cw + 14))))
        rows = (n + cols - 1) // cols
        # 行高：卡牌 + 底部标注 + 间距
        row_h = ch + 30 + self._lay.spacing()
        need_h = rows * row_h + 24
        need_w = max(vw, cols * (cw + 14) + 24)
        self._inner.setMinimumSize(need_w, need_h)
        self._inner.resize(need_w, need_h)

    def set_cols(self, cols: int) -> None:
        """重排为指定列数（自适应宽度用）。"""
        cols = max(1, int(cols))
        if cols == self._cols or not self._vertical:
            return
        self._cols = cols
        cards = [e[1] for e in self._entries]
        payloads = [e[2] for e in self._entries]
        extra = {i: e[3] for i, e in enumerate(self._entries) if e[3]}
        if cards:
            self.set_cards(cards, payloads=payloads, extra=extra)

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        if not self._vertical or not self.cards:
            return
        # 按视口宽度自适应列数，保证内容始终落在可视区内
        card_w = max(1, int(T.CARD_W * self._scale))
        vw = max(1, self.viewport().width())
        cols = max(1, min(12, (vw - 24) // (card_w + 14)))
        if cols != self._cols:
            self.set_cols(cols)
        else:
            self._apply_inner_height()

    def _pick(self, idx: int, payloads) -> None:
        payload = payloads[idx] if payloads and idx < len(payloads) else None
        self.card_picked.emit(idx, payload)


class RewardPick(QWidget):
    """通用的"选一张"卡牌选择面板（奖励 / 事件 / 商店）。"""


# =====================================================================
# 1. 主菜单
# =====================================================================


class MenuScreen(QWidget):
    """主菜单：钢铁战线标题 + 战役入口 + 图鉴/成就/设置。"""

    new_run = pyqtSignal(int, object)      # ascension, seed(None=随机)
    continue_run = pyqtSignal()
    open_codex = pyqtSignal()
    open_achievements = pyqtSignal()
    open_settings = pyqtSignal()
    open_stats = pyqtSignal()
    open_saves = pyqtSignal()
    open_versus = pyqtSignal()          # 联机对战（局域网 1v1）

    def __init__(self, parent=None, meta=None):
        super().__init__(parent)
        self.meta = meta
        self._phase = 0.0
        self._t = QTimer(self)
        self._t.setInterval(_FRAME_MS)
        self._t.timeout.connect(self._tick)
        self._t.start()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- 左：标题与按钮 ---
        left = QWidget(self)
        left.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(70, 60, 30, 60)
        lv.setSpacing(14)
        lv.addStretch(2)

        self.lbl_title = BigTitle(left)
        # 必须容纳「中文大标题(58px) + 英文副标题(15px) + 分隔线」三行
        self.lbl_title.setFixedHeight(132)
        lv.addWidget(self.lbl_title)

        _ver = ""
        try:
            import core.version as _V
            import core.i18n as _i18n_m
            # 版本标签按语言显示：0.9.01 测试版 / 0.9.01 Beta
            _lbl = (_V.VERSION_LABEL_EN if _i18n_m.is_english()
                    else _V.VERSION_LABEL)
            _ver = "  ·  v%s" % _lbl
        except Exception:
            pass
        self.lbl_sub = QLabel(
            T.tr("STEEL FRONTLINE  ·  装甲战争 · 卡牌构筑  ·  🤖 全部由 AI 生成") + _ver,
            left)
        self.lbl_sub.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_H2-3}px; "
            f"background:transparent;")
        lv.addWidget(self.lbl_sub)

        # 提示行（内容来自项目根的 tips.txt，每次进菜单随机一条）
        self.lbl_tip = QLabel("", left)
        self.lbl_tip.setWordWrap(True)
        self.lbl_tip.setStyleSheet(
            f"color:{T.TEXT_MUTED};font-size:{T.FONT_TINY}px;"
            f"background:transparent;")
        lv.addWidget(self.lbl_tip)
        self._refresh_tip()

        lv.addSpacing(26)
        self.btn_new = QPushButton("开 始 新 战 役", left)
        self.btn_new.setObjectName("Primary")
        self.btn_new.setMinimumHeight(52)
        self.btn_new.setFixedWidth(340)
        self.btn_new.clicked.connect(self._emit_new)
        lv.addWidget(self.btn_new)

        self.btn_cont = QPushButton("继 续 上 次 战 役", left)
        self.btn_cont.setMinimumHeight(46)
        self.btn_cont.setFixedWidth(340)
        self.btn_cont.clicked.connect(self.continue_run.emit)
        lv.addWidget(self.btn_cont)

        # 联机对战入口：放在主按钮正下方，比次级网格更显眼
        self.btn_versus = QPushButton("联 机 对 战  (局域网 1v1)", left)
        self.btn_versus.setObjectName("Primary")
        self.btn_versus.setMinimumHeight(46)
        self.btn_versus.setFixedWidth(340)
        self.btn_versus.setToolTip("与同一个 WiFi 下的同学 1v1 对战")
        self.btn_versus.clicked.connect(self.open_versus.emit)
        lv.addWidget(self.btn_versus)

        # 次级入口：2x3 等宽网格，左对齐标题，避免流式换行导致的散乱
        grid = QGridLayout()
        grid.setSpacing(9)
        grid.setContentsMargins(0, 0, 0, 0)
        entries = (("每日挑战", self._emit_daily, "Ghost"),
                   ("图鉴", self.open_codex.emit, "Ghost"),
                   ("成就", self.open_achievements.emit, "Ghost"),
                   ("战绩档案", self.open_stats.emit, "Ghost"),
                   ("存档管理", self.open_saves.emit, "Ghost"),
                   ("设置", self.open_settings.emit, "Ghost"))
        for i, (text, sig, obj) in enumerate(entries):
            b = QPushButton(text, left)
            b.setObjectName(obj)
            b.setMinimumHeight(42)
            b.setMinimumWidth(160)
            b.clicked.connect(sig)
            if i == len(entries) - 1 and len(entries) % 2 == 1:
                # 奇数个时，最后一个按钮横跨两列，避免出现孤立的半行
                grid.addWidget(b, i // 2, 0, 1, 2)
            else:
                grid.addWidget(b, i // 2, i % 2)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnMinimumWidth(0, 165)
        grid.setColumnMinimumWidth(1, 165)
        holder = QWidget(left)
        holder.setStyleSheet("background:transparent;")
        holder.setLayout(grid)
        holder.setFixedWidth(350)
        lv.addWidget(holder)

        self.lbl_meta = QLabel("", left)
        self.lbl_meta.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;background:transparent;")
        lv.addWidget(self.lbl_meta)
        lv.addStretch(3)
        root.addWidget(left, 0)

        # --- 右：难度选择 + 种子 ---
        right = QFrame(self)
        right.setObjectName("Panel")
        right.setFixedWidth(410)
        # 暖色钢板底 + 圆角 + 描边：与左侧战场暖色调统一，
        # 并留出上下右边距，避免"焊死"在窗口边缘。
        right.setStyleSheet(
            f"QFrame#Panel{{background:{T.PANEL};"
            f"border:1px solid {T.BORDER_HI};border-radius:{T.RADIUS_L}px;}}")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(22, 22, 22, 22)
        rv.setSpacing(11)

        rv.addWidget(W.SectionTitle("战 役 设 定", right))
        rv.addWidget(QLabel("战役难度", right))
        self.spin_asc = QSpinBox(right)
        self.spin_asc.setRange(0, 20)
        self.spin_asc.setValue(0)
        self.spin_asc.valueChanged.connect(self._update_diff)
        rv.addWidget(self.spin_asc)

        self.lbl_diff = QLabel("", right)
        self.lbl_diff.setWordWrap(True)
        self.lbl_diff.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;"
            f"background:{T.PANEL_LO}; border:1px solid {T.BORDER};"
            f"border-radius:6px; padding:9px;")
        self.lbl_diff.setMinimumHeight(112)
        rv.addWidget(self.lbl_diff)

        rv.addWidget(W.SectionTitle("自 定 义 种 子", right))
        seed_row = QHBoxLayout()
        self.edit_seed = QLineEdit(right)
        self.edit_seed.setPlaceholderText(T.tr("留空 = 随机种子"))
        seed_row.addWidget(self.edit_seed, 1)
        btn_dice = QPushButton("随机", right)
        btn_dice.setFixedWidth(70)
        btn_dice.clicked.connect(self._roll_seed)
        seed_row.addWidget(btn_dice)
        rv.addLayout(seed_row)

        rv.addStretch(1)
        self.lbl_hint = QLabel(
            "提示：战役难度每提升一档，敌人生命与伤害都会真实增加。", right)
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;background:transparent;")
        rv.addWidget(self.lbl_hint)
        # 面板留出边距（不再贴死窗口右/下边缘）
        wrap = QWidget(self)
        wrap.setStyleSheet("background:transparent;")
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 22, 22, 22)
        wl.setSpacing(0)
        wl.addStretch(1)
        wl.addWidget(right, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addStretch(1)
        root.addWidget(wrap, 0)

        self._art = None
        self._update_diff()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.02) % 1.0
        self.lbl_title.update()
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        """整页背景：焦土渐变 + 战损坦克剪影 + 硝烟。"""
        p = QPainter(self)
        T.aa(p)
        W_, H_ = float(self.width()), float(self.height())
        g = QLinearGradient(QPointF(0, 0), QPointF(W_ * 0.6, H_))
        g.setColorAt(0.0, T.mix(T.Q_BG_DEEP, T.Q_RUST, 0.05))
        g.setColorAt(0.55, T.Q_BG_DEEP)
        g.setColorAt(1.0, T.qc("#0C0A08"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(0, 0, W_, H_))

        # 远景地平线 + 废墟
        horizon = H_ * 0.72
        rg = QRadialGradient(QPointF(W_ * 0.42, horizon), W_ * 0.5)
        rg.setColorAt(0.0, T.a(T.Q_ORANGE, 62))
        rg.setColorAt(0.5, T.a(T.Q_RUST, 24))
        rg.setColorAt(1.0, T.a(T.Q_BG_DEEP, 0))
        p.setBrush(QBrush(rg))
        p.drawRect(QRectF(0, 0, W_, horizon + 40))

        p.setBrush(QBrush(T.a(T.mix(T.Q_SMOKE, T.Q_BG_DEEP, 0.4), 190)))
        import random as _r
        rng = _r.Random(7)
        x = -30.0
        while x < W_:
            bw = rng.uniform(20, 62)
            bh = rng.uniform(18, 96)
            p.drawRect(QRectF(x, horizon - bh, bw, bh))
            if rng.random() > 0.7:
                p.drawRect(QRectF(x + bw * 0.3, horizon - bh - 20, bw * 0.3, 22))
            x += bw + rng.uniform(6, 30)

        # 前景：两辆战损坦克剪影
        # 前景剪影：中心抬高并缩小，确保整体（含履带）完整落在画面内
        W.draw_enemy_tank(p, W_ * 0.84, H_ * 0.80, 44, T.f(T.Q_SMOKE, 0.85))
        W.draw_player_tank(p, W_ * 0.70, H_ * 0.83, 38, T.f(T.Q_GREEN, 0.55), 0.35)

        # 硝烟
        for i in range(14):
            t = (self._phase + i / 14.0) % 1.0
            cx = W_ * (0.15 + 0.7 * ((i * 37) % 100) / 100.0)
            cy = H_ * (0.85 - 0.5 * t)
            rr = 40 + t * 90
            gg = QRadialGradient(QPointF(cx, cy), rr)
            gg.setColorAt(0.0, T.a(T.Q_SMOKE, int(38 * (1 - t))))
            gg.setColorAt(1.0, T.a(T.Q_SMOKE, 0))
            p.setBrush(QBrush(gg))
            p.drawEllipse(QPointF(cx, cy), rr, rr * 0.6)

        # 暗角
        vg = QRadialGradient(QPointF(W_ * 0.5, H_ * 0.5), max(W_, H_) * 0.75)
        vg.setColorAt(0.55, T.a(T.Q_BLACK, 0))
        vg.setColorAt(1.0, T.a(T.Q_BLACK, 165))
        p.setBrush(QBrush(vg))
        p.drawRect(QRectF(0, 0, W_, H_))
        p.end()

    def showEvent(self, ev):  # noqa: N802
        super().showEvent(ev)
        self._refresh_meta()

    def _refresh_meta(self) -> None:
        m = self.meta
        if m is None:
            try:
                from core import run as run_mod
                m = run_mod.MetaProgress.load()
                self.meta = m
            except Exception:
                return
        try:
            from core import run as run_mod
            # 全部 20 档直接可选（旧版用 ascension_unlocked 当上限，
            # 新档为 0 会导致难度**根本调不动** —— 用户实际遇到的 bug）。
            try:
                max_asc = max(0, len(run_mod.ASCENSION_TABLE) - 1)
            except Exception:
                max_asc = 20
            self.spin_asc.setMaximum(max_asc)
            self.spin_asc.setSpecialValueText("")
            done = sum(1 for v in (getattr(m, "achievements", {}) or {}).values() if v)
            total = len(run_mod.ACHIEVEMENTS)
            self.lbl_meta.setText(
                f"{T.tr('总局数')} {m.total_runs} · {T.tr('通关')} {m.wins} · "
                f"{T.tr('最高分')} {m.best_score} · "
                f"{T.tr('成就')} {done}/{total} · "
                f"{T.tr('已解锁难度')} {max_asc}")
            has = run_mod.has_save()
            self.btn_cont.setEnabled(bool(has))
            self.btn_cont.setText("继 续 上 次 战 役" if has else "无 存 档")
        except Exception as exc:
            print(f"[qt.menu] meta refresh failed: {exc!r}", flush=True)

    def _update_diff(self) -> None:
        try:
            from core import run as run_mod
            par = run_mod.ascension_params(int(self.spin_asc.value()))
            # 这段是运行时拼出来的 HTML，整体查表查不到，所以逐片段翻译。
            self.lbl_diff.setText(
                f"<b style='color:{T.GOLD}'>{T.tr(par.get('name',''))}</b><br>"
                f"{T.tr(par.get('desc',''))}<br><br>"
                f"{T.tr('敌人生命')} ×{par.get('hp_mult',1):.2f}　"
                f"{T.tr('伤害')} ×{par.get('dmg_mult',1):.2f}<br>"
                f"{T.tr('精锐生命')} ×{par.get('elite_hp',1):.2f}　"
                f"{T.tr('起始诅咒')} {par.get('start_curse',0)} {T.tr('张')}<br>"
                f"{T.tr('战地医院回复')} "
                f"{float(par.get('rest_heal',0.3))*100:.0f}%")
        except Exception:
            self.lbl_diff.setText("")
        # 最高档 = 神人模式：显著提示作弊被禁用
        try:
            if int(self.spin_asc.value()) >= int(self.spin_asc.maximum()):
                self.lbl_diff.setText(
                    self.lbl_diff.text()
                    + f"<br><br><b style='color:{T.BLOOD}'>"
                    + T.tr("神人模式") + "</b>"
                    + f"<span style='color:{T.TEXT_DIM}'> —— "
                    + T.tr("最高难度，兑换码与调试指令全部失效。")
                    + "</span>")
        except Exception:
            pass

    def _roll_seed(self) -> None:
        import random as _r
        self.edit_seed.setText(str(_r.randrange(1, 2 ** 31 - 1)))

    def _seed_or_none(self):
        s = self.edit_seed.text().strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return abs(hash(s)) % (2 ** 31 - 1)

    def _emit_new(self) -> None:
        self.new_run.emit(int(self.spin_asc.value()), self._seed_or_none())

    def _emit_daily(self) -> None:
        try:
            from core import run as run_mod
            self.new_run.emit(int(self.spin_asc.value()), int(run_mod.daily_seed()))
        except Exception:
            self.new_run.emit(0, None)


# =====================================================================
# 2. 卡牌奖励
# =====================================================================



    def _refresh_tip(self, scene: str = "menu") -> None:
        """刷新提示行。tips.txt 改了内容后重启即可生效。"""
        try:
            from core import tips as _tips
            self.lbl_tip.setText("💡 " + _tips.random_tip(scene))
        except Exception:
            pass

class RewardScreen(QWidget):
    """战后奖励：金币 + 卡牌三选一 + 勋章。"""

    done = pyqtSignal()
    skip = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._picked = False
        self._cards: List = []
        self._gold = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(10)

        self.tb = TitleBar("战 利 品", "", self)
        root.addWidget(self.tb)

        self.lbl_gold = QLabel("", self)
        self.lbl_gold.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2}px; font-weight:700;")
        self.lbl_gold.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_gold)

        self.relic_box = QFrame(self)
        self.relic_box.setObjectName("Panel")
        self.rl = QHBoxLayout(self.relic_box)
        self.rl.setContentsMargins(14, 10, 14, 10)
        self.rl.setSpacing(12)
        self.relic_lbl = QLabel("", self.relic_box)
        self.relic_lbl.setStyleSheet(
            f"color:{T.TEXT}; font-size:{T.FONT_BODY}px;background:transparent;")
        self.rl.addWidget(self.relic_lbl)
        root.addWidget(self.relic_box)
        self.relic_box.hide()

        root.addWidget(W.SectionTitle("挑 选 一 张 卡 牌 加 入 牌 组", self))

        self.scroll = CardScroll(self, card_scale=1.05)
        self.scroll.card_picked.connect(self._on_pick)
        root.addWidget(self.scroll, 1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        self.btn_skip = QPushButton("放 弃 奖 励", self)
        self.btn_skip.setObjectName("Ghost")
        self.btn_skip.clicked.connect(self._on_skip)
        bar.addWidget(self.btn_skip)
        root.addLayout(bar)

    def setup(self, run, gold: int = 0, cards: Optional[List] = None,
              relic_id: Optional[str] = None) -> None:
        self._picked = False
        self._gold = int(gold)
        self.tb.subtitle = f"第 {run.act} 幕 · 已推进 {run.floor} 层"
        self.lbl_gold.setText(T.tr("缴获 %d 金币") % gold if gold else "")
        self.btn_skip.setEnabled(True)
        self.btn_skip.setText("放 弃 奖 励")

        if relic_id:
            try:
                from core import relics as R
                rd = R.RELIC_DB.get(relic_id)
                if rd:
                    self.relic_lbl.setText(f"获得勋章：【{rd.name}】　{rd.text}")
                    self.relic_box.show()
                else:
                    self.relic_box.hide()
            except Exception:
                self.relic_box.hide()
        else:
            self.relic_box.hide()

        if cards is None:
            cards = run.offer_card_rewards(3) if run else []
        self._cards = list(cards)
        dicts = [self._card_dict(c) for c in cards]
        self.scroll.set_cards(dicts, payloads=list(range(len(cards))), footer=False)

    @staticmethod
    def _card_dict(cd) -> dict:
        """把 CardDef 转成 CardView 需要的 dict 结构。

        描述文本必须走 ``core.cards.resolve_text``，把 ``{damage}``/``{block}``
        等占位符换成真实数值，否则卡面上会直接显示花括号。
        """
        text = getattr(cd, "text", "")
        try:
            from core import cards as _C
            # 先翻译**模板**再填数值：resolve_text 会把 {damage} 换成具体数字，
            # 换完之后字符串就不在翻译表里了（这正是卡面描述漏翻的原因）。
            text = _C.resolve_text(cd, translate=True)
        except Exception:
            try:
                from core import cards as _C
                text = _C.resolve_text(cd)
            except Exception:
                pass
        return {
            "uid": -1, "def_id": getattr(cd, "id", ""),
            "name": T.tr(getattr(cd, "name", "")),
            "cost": getattr(cd, "cost", 0),
            "type": getattr(cd, "type", "skill"),
            "rarity": getattr(cd, "rarity", "common"),
            "arch": getattr(cd, "arch", "attack"),
            "text": text, "upgraded": 0, "playable": True,
            "exhaust": bool(getattr(cd, "exhaust", False)),
            "ethereal": bool(getattr(cd, "ethereal", False)),
            "innate": bool(getattr(cd, "innate", False)),
            "retain": bool(getattr(cd, "retain", False)),
        }

    def _on_pick(self, idx: int, payload) -> None:
        if self._picked:
            return
        self._picked = True
        self.btn_skip.setEnabled(False)
        self.btn_skip.setText("已 选 择")
        self.picked_index = idx
        self.picked_card = self._cards[idx] if idx < len(self._cards) else None
        QTimer.singleShot(220, self.done.emit)

    def _on_skip(self) -> None:
        if self._picked:
            return
        self._picked = True
        self.picked_index = -1
        self.picked_card = None
        self.skip.emit()
        QTimer.singleShot(120, self.done.emit)

    picked_index: int = -1
    picked_card = None


# =====================================================================
# 3. 补给站（商店）
# =====================================================================


class ShopScreen(QWidget):
    """补给站：买卡 / 买勋章 / 买补给品 / 删卡。"""

    done = pyqtSignal()
    buy_card = pyqtSignal(int, int)          # index, price
    buy_relic = pyqtSignal(str, int)
    buy_potion = pyqtSignal(str, int)
    remove_card = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inv: Dict = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(9)

        self.tb = TitleBar("补 给 站", "", self)
        root.addWidget(self.tb)

        top = QHBoxLayout()
        self.lbl_gold = QLabel("", self)
        self.lbl_gold.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2}px; font-weight:700;")
        top.addWidget(self.lbl_gold)
        top.addStretch(1)
        self.btn_leave = QPushButton("离 开 补 给 站", self)
        self.btn_leave.setObjectName("Primary")
        self.btn_leave.clicked.connect(self.done.emit)
        top.addWidget(self.btn_leave)
        root.addLayout(top)

        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {T.BORDER};border-radius:6px;"
            f"background:{T.PANEL_LO};}}"
            f"QTabBar::tab{{background:{T.PANEL};color:{T.TEXT_DIM};"
            f"padding:8px 20px;border:1px solid {T.BORDER};}}"
            f"QTabBar::tab:selected{{background:{T.PANEL_LIGHT};color:{T.GOLD};"
            f"border-bottom:2px solid {T.GOLD};}}")
        root.addWidget(self.tabs, 1)

        # 卡牌页
        self.card_page = CardScroll(self, card_scale=0.95)
        self.card_page.card_picked.connect(self._on_card)
        self.tabs.addTab(self._wrap(self.card_page), "卡 牌")

        # 勋章页
        self.relic_page = QWidget()
        self.relic_lay = QHBoxLayout(self.relic_page)
        self.relic_lay.setContentsMargins(14, 14, 14, 14)
        self.relic_lay.setSpacing(16)
        self.relic_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabs.addTab(self._wrap(self.relic_page), "勋 章")

        # 补给品页
        self.potion_page = QWidget()
        self.potion_lay = QHBoxLayout(self.potion_page)
        self.potion_lay.setContentsMargins(14, 14, 14, 14)
        self.potion_lay.setSpacing(16)
        self.potion_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabs.addTab(self._wrap(self.potion_page), "补 给 品")

        # 服务页
        svc = QWidget()
        sv = QVBoxLayout(svc)
        sv.setContentsMargins(20, 20, 20, 20)
        sv.setSpacing(12)
        self.lbl_remove = QLabel("", svc)
        self.lbl_remove.setWordWrap(True)
        self.lbl_remove.setStyleSheet(
            f"color:{T.TEXT}; font-size:{T.FONT_BODY}px;background:transparent;")
        sv.addWidget(self.lbl_remove)
        self.btn_remove = QPushButton("移 除 一 张 卡 牌", svc)
        self.btn_remove.setFixedWidth(240)
        self.btn_remove.clicked.connect(self.remove_card.emit)
        sv.addWidget(self.btn_remove)
        sv.addStretch(1)
        self.tabs.addTab(self._wrap(svc), "服 务")

    @staticmethod
    def _wrap(w: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        w.setStyleSheet("background:transparent;")
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        il = QHBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(w)
        sa.setWidget(inner)
        return sa

    def setup(self, run, inv: Optional[Dict] = None) -> None:
        self.tb.subtitle = f"第 {run.act} 幕 · 战役难度 {run.ascension}"
        self.lbl_gold.setText(T.tr("金币 %d") % run.gold)
        if inv is None:
            try:
                from core import events as EV
                inv = EV.build_shop_inventory(run.rng, run.act, run.ascension)
            except Exception:
                inv = {"cards": [], "relics": [], "potions": [],
                       "remove_price": 75, "card_prices": {},
                       "relic_prices": {}, "potion_price": 60}
        self._inv = dict(inv)
        self.btn_remove.setEnabled(run.gold >= int(inv.get("remove_price", 75)))

        # 卡牌
        prices = inv.get("card_prices", {}) or {}
        dicts, extra = [], {}
        for i, cd in enumerate(inv.get("cards", [])):
            dicts.append(RewardScreen._card_dict(cd))
            extra[i] = T.tr("%s 金币") % prices.get(cd.id, '?')
        self.card_page.set_cards(dicts, payloads=[c.id for c in inv.get("cards", [])],
                                 extra=extra)

        # 勋章
        while self.relic_lay.count():
            it = self.relic_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        rprices = inv.get("relic_prices", {}) or {}
        for rd in inv.get("relics", []):
            box = QWidget(self.relic_page)
            box.setStyleSheet("background:transparent;")
            bv = QVBoxLayout(box)
            bv.setContentsMargins(0, 0, 0, 0)
            bv.setSpacing(7)
            rv = W.RelicView({"id": rd.id, "name": rd.name, "text": rd.text,
                              "rarity": rd.rarity, "counter": -1}, box, size=64)
            bv.addWidget(rv, 0, Qt.AlignmentFlag.AlignHCenter)
            price = int(rprices.get(rd.id, 0))
            lbl = QLabel(T.tr("%s\n%d 金币") % (T.tr(rd.name), price), box)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setFixedWidth(170)
            afford = run.gold >= price
            lbl.setStyleSheet(
                f"color:{T.GOLD if afford else T.TEXT_MUTED};"
                f"font-size:{T.FONT_SMALL}px;background:transparent;")
            bv.addWidget(lbl)
            b = QPushButton("购 买", box)
            b.setFixedWidth(110)
            b.setEnabled(afford)
            b.clicked.connect(lambda _c=False, rid=rd.id, p=price:
                              self.buy_relic.emit(rid, p))
            bv.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
            self.relic_lay.addWidget(box)

        # 补给品
        while self.potion_lay.count():
            it = self.potion_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        try:
            from core import events as EV
            pnames = getattr(EV, "POTION_NAMES", {}) or {}
        except Exception:
            pnames = {}
        pprice = int(inv.get("potion_price", 60))
        for pid in inv.get("potions", []):
            box = QWidget(self.potion_page)
            box.setStyleSheet("background:transparent;")
            bv = QVBoxLayout(box)
            bv.setSpacing(7)
            art = W.IconButton("medic", box, 62, T.Q_GREEN,
                               tooltip=pnames.get(pid, pid))
            bv.addWidget(art, 0, Qt.AlignmentFlag.AlignHCenter)
            nm = pnames.get(pid, str(pid))
            lbl = QLabel(T.tr("%s\n%d 金币") % (T.tr(nm), pprice), box)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setFixedWidth(160)
            afford = run.gold >= pprice
            lbl.setStyleSheet(
                f"color:{T.GOLD if afford else T.TEXT_MUTED};"
                f"font-size:{T.FONT_SMALL}px;background:transparent;")
            bv.addWidget(lbl)
            b = QPushButton("购 买", box)
            b.setFixedWidth(110)
            b.setEnabled(afford)
            b.clicked.connect(lambda _c=False, p=pid, pr=pprice:
                              self.buy_potion.emit(p, pr))
            bv.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
            self.potion_lay.addWidget(box)

        self.lbl_remove.setText(
            T.tr("战地工兵可以帮你从牌组中移除一张卡牌。\n"
                 "当前价格：%d 金币（每次移除后价格会上涨）")
            % int(inv.get('remove_price', 75)))

    def _on_card(self, idx: int, payload) -> None:
        prices = self._inv.get("card_prices", {}) or {}
        self.buy_card.emit(idx, int(prices.get(payload, 0)))

    def refresh_gold(self, run) -> None:
        self.lbl_gold.setText(f"金币 {run.gold}")

    def set_remove_price(self, price: int) -> None:
        self.lbl_remove.setText(
            f"战地工兵可以帮你从牌组中移除一张卡牌。\n"
            f"当前价格：{int(price)} 金币（每次移除后价格会上涨）")


# =====================================================================
# 4. 战地医院（休息）
# =====================================================================


class RestScreen(QWidget):
    """战地医院：休整回血 / 升级卡牌。"""

    done = pyqtSignal()
    choose_rest = pyqtSignal()
    choose_upgrade = pyqtSignal(int)          # uid

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(11)

        self.tb = TitleBar("战 地 医 院", "", self)
        root.addWidget(self.tb)

        self.lbl_hp = QLabel("", self)
        self.lbl_hp.setStyleSheet(
            f"color:{T.TEXT}; font-size:{T.FONT_H2}px; font-weight:700;")
        self.lbl_hp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_hp)

        picks = QHBoxLayout()
        picks.setSpacing(18)

        # 左：休整
        left = QFrame(self)
        left.setObjectName("Panel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(20, 20, 20, 20)
        lv.setSpacing(11)
        lv.addWidget(W.SectionTitle("休 整", left))
        self.lbl_heal = QLabel("", left)
        self.lbl_heal.setWordWrap(True)
        self.lbl_heal.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_BODY}px;background:transparent;")
        lv.addWidget(self.lbl_heal)
        lv.addStretch(1)
        self.btn_rest = QPushButton("进 行 休 整", left)
        self.btn_rest.setObjectName("Primary")
        self.btn_rest.setMinimumHeight(48)
        self.btn_rest.clicked.connect(self.choose_rest.emit)
        lv.addWidget(self.btn_rest)
        art = W.IconButton("medic", left, 70, T.Q_GREEN, label="")
        lv.insertWidget(1, art, 0, Qt.AlignmentFlag.AlignHCenter)
        picks.addWidget(left, 1)

        # 右：升级
        right = QFrame(self)
        right.setObjectName("Panel")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(14, 14, 14, 14)
        rv.setSpacing(9)
        rv.addWidget(W.SectionTitle("锻 造 · 升 级 卡 牌", right))
        self.up_scroll = CardScroll(right, card_scale=0.58)
        self.up_scroll.card_picked.connect(self._on_upgrade)
        rv.addWidget(self.up_scroll, 1)
        picks.addWidget(right, 2)

        root.addLayout(picks, 1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        self.btn_skip = QPushButton("直 接 出 发", self)
        self.btn_skip.setObjectName("Ghost")
        self.btn_skip.clicked.connect(self.done.emit)
        bar.addWidget(self.btn_skip)
        root.addLayout(bar)

        self._upgradable: List = []

    def setup(self, run) -> None:
        self.tb.subtitle = f"第 {run.act} 幕 · 第 {run.floor} 层"
        heal = run.rest_heal_amount() if hasattr(run, "rest_heal_amount") else 20
        self.lbl_hp.setText(T.tr("总部耐久 %d / %d") % (run.hp, run.max_hp))
        # Qt 的 QLabel 只在字符串**以标签开头**时按富文本渲染。旧代码把
        # <b> 放在中间，于是标签被当成纯文本显示出来（用户看到的
        # 「回复 <b style='color:#6B7F3A'>22</b> 点…」）。
        # 这里统一用 <div> 包住整段，保证被识别为富文本；换行用 <br>。
        self.lbl_heal.setText(
            "<div style='line-height:150%'>"
            + T.tr("就地休整，修复装甲并补充弹药。")
            + "<br><br>"
            + T.tr("回复 {n} 点总部耐久（受战役难度影响）。").replace(
                "{n}", f"<b style='color:{T.GREEN}'>{heal}</b>")
            + ("<br><br><b>" + T.tr("总部已满耐久，休整无效果。") + "</b>"
               if run.hp >= run.max_hp else "")
            + "</div>")
        self.lbl_heal.setTextFormat(Qt.TextFormat.RichText)
        # 用过一次就不能再点（与 on_rest_heal 的单次限制一致）
        used = bool(getattr(self, "_used", False))
        self.btn_rest.setEnabled((run.hp < run.max_hp) and not used)

        self._upgradable = list(run.upgradable_cards())
        dicts = []
        for ci in self._upgradable:
            d = RewardScreen._card_dict(ci.defn)
            d["uid"] = ci.uid
            dicts.append(d)
        self.up_scroll.set_cards(dicts, payloads=[c.uid for c in self._upgradable],
                                 footer=False)

    def _on_upgrade(self, idx: int, payload) -> None:
        if payload is None:
            return
        self.choose_upgrade.emit(int(payload))


# =====================================================================
# 5. 事件
# =====================================================================


class EventScreen(QWidget):
    """战场事件：叙述文本 + 带后果预告的选项。"""

    resolved = pyqtSignal(str)         # 结果叙述文本

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(11)

        self.tb = TitleBar("战 场 事 件", "", self)
        root.addWidget(self.tb)

        body = QFrame(self)
        body.setObjectName("Panel")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(24, 20, 24, 20)
        bv.setSpacing(13)

        self.lbl_text = QLabel("", body)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet(
            f"color:{T.TEXT}; font-size:{T.FONT_H2-3}px; background:transparent;"
            f"")
        self.lbl_text.setMinimumHeight(150)
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        bv.addWidget(self.lbl_text)

        # 事件插画（程序化）
        self.art = EventArt(body)
        bv.addWidget(self.art)
        bv.addStretch(1)
        root.addWidget(body, 1)

        self.choices_box = QFrame(self)
        self.choices_box.setObjectName("Panel")
        self.cl = QVBoxLayout(self.choices_box)
        self.cl.setContentsMargins(16, 14, 16, 14)
        self.cl.setSpacing(9)
        root.addWidget(self.choices_box)

        self.result_box = QFrame(self)
        self.result_box.setObjectName("Panel")
        rl = QVBoxLayout(self.result_box)
        rl.setContentsMargins(20, 16, 20, 16)
        self.lbl_result = QLabel("", self.result_box)
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2-2}px;background:transparent;")
        rl.addWidget(self.lbl_result)
        self.btn_result = QPushButton("继 续", self.result_box)
        self.btn_result.setObjectName("Primary")
        self.btn_result.setFixedWidth(180)
        self.btn_result.clicked.connect(self.done.emit)
        rl.addWidget(self.btn_result, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self.result_box)
        self.result_box.hide()

        self._event = None
        self._run = None
        self._buttons: List[QPushButton] = []

    def setup(self, run, event) -> None:
        self._run = run
        self._event = event
        self.result_box.hide()
        self.choices_box.show()
        self.tb.title = f"战 场 事 件 · {getattr(event, 'name', '')}"
        self.tb.subtitle = f"第 {run.act} 幕 · 第 {run.floor} 层"
        self.lbl_text.setText(str(getattr(event, "text", "")))
        self.art.set_art(str(getattr(event, "art", "")), str(getattr(event, "id", "")))

        for b in self._buttons:
            self.cl.removeWidget(b)
            b.deleteLater()
        self._buttons = []

        for ch in getattr(event, "choices", ()) or ():
            ok = True
            try:
                ok = bool(ch.requires(run)) if ch.requires else True
            except Exception:
                ok = False
            box = QWidget(self.choices_box)
            box.setStyleSheet("background:transparent;")
            bh = QHBoxLayout(box)
            bh.setContentsMargins(0, 0, 0, 0)
            bh.setSpacing(12)
            btn = QPushButton(str(ch.label), box)
            btn.setMinimumHeight(46)
            btn.setMinimumWidth(260)
            btn.setEnabled(ok)
            btn.clicked.connect(lambda _c=False, c=ch: self._choose(c))
            bh.addWidget(btn, 0)
            d = QLabel(str(ch.desc), box)
            d.setWordWrap(True)
            d.setStyleSheet(
                f"color:{T.TEXT_DIM if ok else T.TEXT_MUTED};"
                f"font-size:{T.FONT_SMALL}px;background:transparent;")
            bh.addWidget(d, 1)
            self.cl.addWidget(box)
            self._buttons.append(btn)

    def _choose(self, choice) -> None:
        if self._run is None:
            return
        text = ""
        try:
            text = str(choice.effect(self._run))
        except Exception as exc:
            print(f"[qt.event] choice effect failed: {exc!r}", flush=True)
            text = "……什么也没有发生。"
        self.choices_box.hide()
        self.lbl_result.setText(text)
        self.result_box.show()
        self.resolved.emit(text)

    done = pyqtSignal()


class EventArt(QWidget):
    """事件插画：按 art / id 关键词画一幅程序化场景剪影。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._key = ""
        self._phase = 0.0
        self._t = QTimer(self)
        self._t.setInterval(_FRAME_MS)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.03) % 1.0
        self.update()

    def set_art(self, art: str, eid: str = "") -> None:
        self._key = f"{art} {eid}".lower()
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        W_, H_ = float(self.width()), float(self.height())
        horizon = H_ * 0.66

        g = QLinearGradient(QPointF(0, 0), QPointF(0, H_))
        g.setColorAt(0.0, T.Q_SKY_TOP)
        g.setColorAt(0.6, T.Q_SKY_MID)
        g.setColorAt(1.0, T.Q_GROUND)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(0, 0, W_, H_))

        rg = QRadialGradient(QPointF(W_ * 0.5, horizon), W_ * 0.42)
        rg.setColorAt(0.0, T.a(T.Q_ORANGE, 70))
        rg.setColorAt(1.0, T.a(T.Q_BG_DEEP, 0))
        p.setBrush(QBrush(rg))
        p.drawRect(QRectF(0, 0, W_, horizon + 30))

        k = self._key
        cx = W_ * 0.5
        if any(w in k for w in ("tank", "trench", "armor", "panzer", "leviathan")):
            W.draw_enemy_tank(p, cx, horizon + 26, 44, T.Q_STEEL)
        elif any(w in k for w in ("plane", "gull", "air", "sonar", "propaganda")):
            W.draw_enemy_plane(p, cx, horizon - 6, 42, T.Q_STEEL)
        elif any(w in k for w in ("fort", "bunker", "coral", "golem", "bastion", "wall")):
            W.draw_enemy_fortress(p, cx, horizon + 22, 48, T.Q_STEEL)
        elif any(w in k for w in ("gun", "artillery", "cannon", "harpoon", "vent", "fire")):
            W.draw_enemy_artillery(p, cx, horizon + 22, 44, T.Q_STEEL)
        elif any(w in k for w in ("priest", "oracle", "officer", "king", "lord", "commander",
                                  "chorus", "watcher", "siren")):
            W.draw_enemy_officer(p, cx, horizon + 28, 44, T.Q_STEEL)
        else:
            W.draw_enemy_infantry(p, cx, horizon + 26, 44, T.Q_STEEL)

        # 地面
        p.setBrush(QBrush(T.a(T.Q_BLACK, 90)))
        p.drawRect(QRectF(0, horizon + 46, W_, H_ - horizon - 46))

        # 硝烟
        for i in range(6):
            t = (self._phase + i / 6.0) % 1.0
            x = W_ * (0.12 + 0.76 * ((i * 53) % 100) / 100.0)
            y = horizon + 40 - t * 70
            rr = 26 + t * 46
            gg = QRadialGradient(QPointF(x, y), rr)
            gg.setColorAt(0.0, T.a(T.Q_SMOKE, int(46 * (1 - t))))
            gg.setColorAt(1.0, T.a(T.Q_SMOKE, 0))
            p.setBrush(QBrush(gg))
            p.drawEllipse(QPointF(x, y), rr, rr * 0.62)

        # 铁丝网前景
        p.setPen(QPen(T.a(T.Q_STEEL, 90), 1.2))
        for j in range(2):
            y = horizon + 56 + j * 12
            p.drawLine(QPointF(0, y), QPointF(W_, y))
        p.setPen(QPen(T.a(T.Q_BLACK, 120), 1.0))
        p.drawRect(QRectF(0, 0, W_, H_))
        p.end()


# =====================================================================
# 6. 牌组 / 牌堆查看
# =====================================================================


class DeckScreen(QWidget):
    """牌组查看：按类型筛选 + 升序/稀有度排序。"""

    closed = pyqtSignal()
    remove_requested = pyqtSignal(int)      # uid（仅查看牌堆时用于商店删卡）

    def __init__(self, parent=None, select_mode: bool = False):
        super().__init__(parent)
        self.select_mode = select_mode
        self._cards: List = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(9)

        self.tb = TitleBar("牌 组", "", self)
        root.addWidget(self.tb)

        bar = QHBoxLayout()
        bar.setSpacing(9)
        self.cb_type = QComboBox(self)
        self.cb_type.addItems(["全部类型", "攻击", "战术", "指令", "状态/诅咒"])
        self.cb_type.currentIndexChanged.connect(self._apply_filter)
        bar.addWidget(self.cb_type)
        self.cb_arch = QComboBox(self)
        self.cb_arch.addItems(["全部流派", "突击", "防御", "燃烧弹", "后勤", "支援"])
        self.cb_arch.currentIndexChanged.connect(self._apply_filter)
        bar.addWidget(self.cb_arch)
        self.cb_sort = QComboBox(self)
        self.cb_sort.addItems(["按类型", "按稀有度", "按费用", "按名称"])
        self.cb_sort.currentIndexChanged.connect(self._apply_filter)
        bar.addWidget(self.cb_sort)
        bar.addStretch(1)
        self.lbl_count = QLabel("", self)
        self.lbl_count.setStyleSheet(f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;")
        bar.addWidget(self.lbl_count)
        self.btn_close = QPushButton("关 闭", self)
        self.btn_close.clicked.connect(self.closed.emit)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)

        self.scroll = CardScroll(self, card_scale=0.62)
        self.scroll.card_picked.connect(self._on_pick)
        root.addWidget(self.scroll, 1)

    def setup(self, run, title: str = "牌 组", cards: Optional[List] = None) -> None:
        self.tb.title = title
        self.tb.subtitle = f"第 {run.act} 幕 · 共 {len(cards) if cards is not None else len(run.deck)} 张"
        self._cards = list(cards if cards is not None else run.deck)
        self._apply_filter()

    def _apply_filter(self) -> None:
        types = {"全部类型": None, "攻击": "attack", "战术": "skill",
                 "指令": "power", "状态/诅咒": ("status", "curse")}
        archs = {"全部流派": None, "突击": "attack", "防御": "block",
                 "燃烧弹": "poison", "后勤": "energy", "支援": "summon"}
        tsel = types.get(self.cb_type.currentText())
        asel = archs.get(self.cb_arch.currentText())
        out = []
        for ci in self._cards:
            try:
                d = ci.defn
            except Exception:
                continue
            if tsel:
                if isinstance(tsel, tuple):
                    if d.type not in tsel:
                        continue
                elif d.type != tsel:
                    continue
            if asel and d.arch != asel:
                continue
            out.append(ci)
        sort_key = self.cb_sort.currentText()
        order = {"attack": 0, "skill": 1, "power": 2, "status": 3, "curse": 4}
        rar = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}
        if sort_key == "按类型":
            out.sort(key=lambda c: (order.get(c.defn.type, 9), c.defn.name))
        elif sort_key == "按稀有度":
            out.sort(key=lambda c: (-rar.get(c.defn.rarity, 9), c.defn.name))
        elif sort_key == "按费用":
            out.sort(key=lambda c: (c.cost if c.cost >= 0 else 99, c.defn.name))
        else:
            out.sort(key=lambda c: c.defn.name)
        dicts = []
        for ci in out:
            d = RewardScreen._card_dict(ci.defn)
            d["uid"] = ci.uid
            d["upgraded"] = int(getattr(ci, "upgraded", 0) or 0)
            dicts.append(d)
        self.scroll.set_cards(dicts, payloads=[c.uid for c in out], footer=False)
        self.lbl_count.setText(T.tr("显示 %d / %d 张") % (len(out), len(self._cards)))

    def _on_pick(self, idx: int, payload) -> None:
        if self.select_mode and payload is not None:
            self.remove_requested.emit(int(payload))


# =====================================================================
# 7. 结算
# =====================================================================


class GameOverScreen(QWidget):
    """结算：胜利 / 失败。"""

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._t = QTimer(self)
        self._t.setInterval(_FRAME_MS)
        self._t.timeout.connect(self._tick)
        self._t.start()

        root = QVBoxLayout(self)
        root.setContentsMargins(80, 50, 80, 50)
        root.setSpacing(13)
        root.addStretch(1)

        self.lbl_big = QLabel("", self)
        self.lbl_big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_big.setStyleSheet("background:transparent;")
        root.addWidget(self.lbl_big)

        self.lbl_sub = QLabel("", self)
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sub.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_H2-2}px;background:transparent;")
        root.addWidget(self.lbl_sub)

        self.panel = QFrame(self)
        self.panel.setObjectName("Panel")
        self.panel.setFixedWidth(620)
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(26, 20, 26, 20)
        pv.setSpacing(8)
        pv.addWidget(W.SectionTitle("战 报 汇 总", self.panel))
        self.stats_lbl = QLabel("", self.panel)
        self.stats_lbl.setWordWrap(True)
        self.stats_lbl.setStyleSheet(
            f"color:{T.TEXT}; font-size:{T.FONT_BODY}px;background:transparent;"
            f"")
        pv.addWidget(self.stats_lbl)
        root.addWidget(self.panel, 0, Qt.AlignmentFlag.AlignHCenter)

        self.ach_box = QFrame(self)
        self.ach_box.setObjectName("Panel")
        self.ach_box.setFixedWidth(620)
        av = QVBoxLayout(self.ach_box)
        av.setContentsMargins(26, 16, 26, 16)
        av.setSpacing(6)
        av.addWidget(W.SectionTitle("新 解 锁 成 就", self.ach_box, T.Q_GREEN))
        self.ach_lbl = QLabel("", self.ach_box)
        self.ach_lbl.setWordWrap(True)
        self.ach_lbl.setStyleSheet(
            f"color:{T.GREEN}; font-size:{T.FONT_BODY}px;background:transparent;")
        av.addWidget(self.ach_lbl)
        root.addWidget(self.ach_box, 0, Qt.AlignmentFlag.AlignHCenter)
        self.ach_box.hide()

        # 提示行（内容来自项目根的 tips.txt，胜负各看各的）
        self.lbl_tip = QLabel("", self)
        self.lbl_tip.setWordWrap(True)
        self.lbl_tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_tip.setMaximumWidth(780)
        self.lbl_tip.setStyleSheet(
            f"color:{T.TEXT_MUTED};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        # 给提示行留够高度，否则会被上下挤压成重叠的一团
        self.lbl_tip.setMinimumHeight(34)
        root.addSpacing(6)
        root.addWidget(self.lbl_tip, 0, Qt.AlignmentFlag.AlignHCenter)

        root.addStretch(1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        self.btn_again = QPushButton("再 战 一 局", self)
        self.btn_again.setObjectName("Primary")
        self.btn_again.setMinimumHeight(48)
        self.btn_again.setFixedWidth(220)
        self.btn_again.clicked.connect(self.finished.emit)
        bar.addWidget(self.btn_again)
        bar.addStretch(1)
        root.addLayout(bar)
        root.addStretch(2)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.03) % 1.0
        self.lbl_big.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        W_, H_ = float(self.width()), float(self.height())
        won = getattr(self, "_won", False)
        accent = T.Q_GOLD if won else T.Q_RED
        g = QLinearGradient(QPointF(0, 0), QPointF(0, H_))
        g.setColorAt(0.0, T.mix(T.Q_BG_DEEP, accent, 0.10))
        g.setColorAt(0.5, T.Q_BG_DEEP)
        g.setColorAt(1.0, T.qc("#0A0908"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(0, 0, W_, H_))
        rg = QRadialGradient(QPointF(W_ * 0.5, H_ * 0.28), W_ * 0.55)
        rg.setColorAt(0.0, T.a(accent, 52))
        rg.setColorAt(1.0, T.a(T.Q_BG_DEEP, 0))
        p.setBrush(QBrush(rg))
        p.drawRect(QRectF(0, 0, W_, H_))

        # 放射状光芒
        p.save()
        p.translate(W_ * 0.5, H_ * 0.24)
        p.setBrush(QBrush(T.a(accent, 20)))
        for i in range(16):
            p.save()
            p.rotate(i * 22.5 + self._phase * 10)
            p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(-26, -H_ * 0.7),
                                     QPointF(26, -H_ * 0.7)]))
            p.restore()
        p.restore()

        # 地面 + 剪影
        W.draw_player_tank(p, W_ * 0.22, H_ * 0.88, 46,
                           T.Q_GREEN if won else T.f(T.Q_GREEN, 0.5), 1.0 if won else 0.3)
        W.draw_enemy_tank(p, W_ * 0.80, H_ * 0.88, 46,
                          T.Q_STEEL if not won else T.f(T.Q_STEEL, 0.5))
        p.end()

    def setup(self, run, won: bool, new_achievements: Optional[List[str]] = None,
              score: int = 0) -> None:
        self._won = bool(won)
        accent = T.GOLD if won else T.RED
        self.lbl_big.setText("战 役 胜 利" if won else "总 部 陷 落")
        self.lbl_big.setStyleSheet(
            f"color:{accent}; font-size:{T.FONT_TITLE + 16}px; font-weight:800;"
            f"background:transparent; ")
        if won:
            diff = int(getattr(run, "ascension", 0) or 0)
            self.lbl_sub.setText(
                "钢铁与意志的胜利。敌要塞陷落，全线突破。"
                + ("（战役难度 %d）" % diff if diff else ""))
        else:
            self.lbl_sub.setText("总部被摧毁了……但钢铁的意志不会熄灭。")
        st = getattr(run, "stats", {}) or {}
        # 通关时 advance_act() 会把 act 变成 4，显示「第 4 幕」很怪。
        act_txt = ("全 3 幕 · 已通关" if won
                   else "第 %d 幕" % max(1, int(getattr(run, "act", 1) or 1)))
        rows = [
            ("最终得分", str(score), T.GOLD),
            ("抵达幕次", act_txt, T.GOLD if won else T.TEXT),
            ("推进层数", f"{run.floor} 层", T.TEXT),
            ("总部耐久", f"{run.hp} / {run.max_hp}", T.TEXT),
            ("战役难度", str(run.ascension), T.TEXT),
            ("牌组张数", str(len(run.deck)), T.TEXT),
            ("勋章数量", str(len(run.relics)), T.TEXT),
            ("击杀总数", str(st.get("kills", 0)), T.TEXT),
            ("精锐击杀", str(st.get("elites_killed", 0)), T.TEXT),
            ("要塞击破", str(st.get("bosses_killed", 0)), T.TEXT),
            ("出牌张数", str(st.get("cards_played", 0)), T.TEXT),
            ("总回合数", str(st.get("turns", 0)), T.TEXT),
        ]
        html = []
        for i in range(0, len(rows), 2):
            cells = []
            for k, v, col in rows[i:i + 2]:
                cells.append(
                    f"<td style='padding:5px 20px 5px 0;color:{T.TEXT_DIM}'>{k}</td>"
                    f"<td style='padding:5px 30px 5px 0;color:{col};font-weight:700'>{v}</td>")
            html.append(f"<tr>{''.join(cells)}</tr>")
        self.stats_lbl.setText(f"<table>{''.join(html)}</table>")

        new = list(new_achievements or [])
        if new:
            try:
                from core import run as run_mod
                names = [f"【{run_mod.ACHIEVEMENTS[k]['name']}】"
                         for k in new if k in run_mod.ACHIEVEMENTS]
            except Exception:
                names = [f"【{k}】" for k in new]
            self.ach_lbl.setText("  ".join(names))
            self.ach_box.show()
        else:
            self.ach_box.hide()

        # 胜负各显示对应场景的提示
        try:
            from core import tips as _tips
            self.lbl_tip.setText(
                "💡 " + _tips.random_tip("win" if won else "lose"))
        except Exception:
            pass


# =====================================================================
# 8. 图鉴 / 9. 成就 / 10. 战绩
# =====================================================================


class CodexScreen(QWidget):
    """图鉴：卡牌 / 勋章 / 敌人 全收集。"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(9)

        self.tb = TitleBar("图 鉴", "已认识的全部单位与装备", self)
        root.addWidget(self.tb)

        bar = QHBoxLayout()
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {T.BORDER};border-radius:6px;"
            f"background:{T.PANEL_LO};}}"
            f"QTabBar::tab{{background:{T.PANEL};color:{T.TEXT_DIM};"
            f"padding:8px 20px;border:1px solid {T.BORDER};}}"
            f"QTabBar::tab:selected{{background:{T.PANEL_LIGHT};color:{T.GOLD};"
            f"border-bottom:2px solid {T.GOLD};}}")
        root.addWidget(self.tabs, 1)

        # 卡牌
        # 图鉴 134 张卡：横向滚动浏览（scale 调小，保证一屏能看到多张）
        self.card_scroll = CardScroll(self, card_scale=0.52)
        self.tabs.addTab(self.card_scroll, "卡 牌")
        # 勋章
        self.relic_list = QListWidget(self)
        self.relic_list.setStyleSheet(
            f"QListWidget{{background:{T.PANEL_LO};border:none;font-size:{T.FONT_BODY}px;}}")
        self.tabs.addTab(self.relic_list, "勋 章")
        # 敌人
        self.enemy_list = QListWidget(self)
        self.tabs.addTab(self.enemy_list, "敌 军")

        bot = QHBoxLayout()
        self.lbl_prog = QLabel("", self)
        self.lbl_prog.setStyleSheet(f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;")
        bot.addWidget(self.lbl_prog)
        bot.addStretch(1)
        b = QPushButton("关 闭", self)
        b.clicked.connect(self.closed.emit)
        bot.addWidget(b)
        root.addLayout(bot)

    def setup(self, meta=None) -> None:
        try:
            from core import cards as C, relics as R, enemies as E
        except Exception:
            return
        seen_c = set(getattr(meta, "seen_cards", set()) or set())
        seen_r = set(getattr(meta, "seen_relics", set()) or set())
        seen_e = set(getattr(meta, "seen_enemies", set()) or set())

        # 卡牌（未见过显示为剪影）
        dicts = []
        for cd in C.all_cards():
            d = RewardScreen._card_dict(cd)
            if cd.id not in seen_c:
                d["name"] = "？？？"
                d["text"] = "尚未在战场上缴获过这张卡牌。"
                d["playable"] = False
            dicts.append(d)
        self.card_scroll.set_cards(dicts, footer=False)

        # 勋章
        self.relic_list.clear()
        for rid, rd in R.RELIC_DB.items():
            got = rid in seen_r
            name = rd.name if got else "？？？"
            text = rd.text if got else "尚未获得。"
            rar = T.RARITY_NAMES.get(rd.rarity, rd.rarity)
            item = QListWidgetItem(f"{name}   〔{rar}〕\n    {text}")
            item.setForeground(T.qc(T.GOLD if got else T.TEXT_MUTED))
            self.relic_list.addItem(item)

        # 敌人
        self.enemy_list.clear()
        for eid, ed in E.ENEMY_DB.items():
            got = eid in seen_e
            name = ed.name if got else "？？？"
            desc = ed.desc if got else "尚未遭遇。"
            tier = {"normal": "常规", "elite": "精锐", "boss": "要塞"}.get(ed.tier, ed.tier)
            item = QListWidgetItem(
                f"{name}   〔{tier} · 第{ed.act}幕 · {ed.hp_min}-{ed.hp_max}耐久〕\n    {desc}")
            item.setForeground(T.qc(T.TEXT if got else T.TEXT_MUTED))
            self.enemy_list.addItem(item)

        self.lbl_prog.setText(
            f"{T.tr('卡牌')} {len(seen_c & set(C.CARD_DB))}/{len(C.CARD_DB)} · "
            f"{T.tr('勋章')} {len(seen_r & set(R.RELIC_DB))}/{len(R.RELIC_DB)} · "
            f"{T.tr('敌军')} {len(seen_e & set(E.ENEMY_DB))}/{len(E.ENEMY_DB)}")


class AchievementScreen(QWidget):
    """成就：军功章墙。"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(9)
        self.tb = TitleBar("成 就 · 军 功 章", "", self)
        root.addWidget(self.tb)
        bar = QHBoxLayout()
        self.lbl_prog = QLabel("", self)
        self.lbl_prog.setStyleSheet(f"color:{T.GOLD};font-size:{T.FONT_H2-3}px;")
        bar.addWidget(self.lbl_prog)
        bar.addStretch(1)
        b = QPushButton("关 闭", self)
        b.clicked.connect(self.closed.emit)
        bar.addWidget(b)
        root.addLayout(bar)
        self.grid_host = QScrollArea(self)
        self.grid_host.setWidgetResizable(True)
        self.grid_host.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_host.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.inner = QWidget()
        self.inner.setStyleSheet("background:transparent;")
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(10)
        self.grid_host.setWidget(self.inner)
        root.addWidget(self.grid_host, 1)

    def setup(self, meta=None) -> None:
        try:
            from core import run as run_mod
        except Exception:
            return
        ach = getattr(meta, "achievements", {}) or {}
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        keys = list(run_mod.ACHIEVEMENTS.keys())
        done = 0
        for i, k in enumerate(keys):
            info = run_mod.ACHIEVEMENTS[k]
            got = bool(ach.get(k))
            done += 1 if got else 0
            card = QFrame(self.inner)
            card.setObjectName("Panel")
            card.setMinimumHeight(84)
            cv = QHBoxLayout(card)
            cv.setContentsMargins(12, 10, 12, 10)
            cv.setSpacing(12)
            col = T.GOLD if got else T.TEXT_MUTED
            rv = W.IconButton("star" if got else "gear", card, 46, col, label="")
            cv.addWidget(rv)
            tv = QVBoxLayout()
            tv.setSpacing(2)
            nm = QLabel(info.get("name", k), card)
            nm.setStyleSheet(
                f"color:{col}; font-size:{T.FONT_H2-4}px; font-weight:700;"
                f"background:transparent;")
            tv.addWidget(nm)
            ds = QLabel(info.get("desc", ""), card)
            ds.setWordWrap(True)
            ds.setStyleSheet(
                f"color:{T.TEXT_DIM if got else T.TEXT_MUTED};"
                f"font-size:{T.FONT_SMALL}px;background:transparent;")
            tv.addWidget(ds)
            cv.addLayout(tv, 1)
            self.grid.addWidget(card, i // 3, i % 3)
        self.lbl_prog.setText(f"{T.tr('已解锁')} {done} / {len(keys)}")
        self.tb.subtitle = f"共 {len(keys)} 项军功章"


class StatsScreen(QWidget):
    """战绩档案：总局数 / 排行 / 游玩时长。"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(9)
        self.tb = TitleBar("战 绩 档 案", "", self)
        root.addWidget(self.tb)
        body = QHBoxLayout()
        body.setSpacing(14)

        left = QFrame(self)
        left.setObjectName("Panel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(20, 16, 20, 16)
        lv.setSpacing(7)
        lv.addWidget(W.SectionTitle("总 览", left))
        self.lbl_sum = QLabel("", left)
        self.lbl_sum.setWordWrap(True)
        self.lbl_sum.setStyleSheet(
            f"color:{T.TEXT}; font-size:{T.FONT_BODY}px;background:transparent;"
            f"")
        lv.addWidget(self.lbl_sum)
        lv.addStretch(1)
        body.addWidget(left, 1)

        right = QFrame(self)
        right.setObjectName("Panel")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(20, 16, 20, 16)
        rv.setSpacing(7)
        rv.addWidget(W.SectionTitle("本 地 排 行 榜 Top 10", right, T.Q_GREEN))
        self.lb = QListWidget(right)
        rv.addWidget(self.lb, 1)
        body.addWidget(right, 1)
        root.addLayout(body, 1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        b = QPushButton("关 闭", self)
        b.clicked.connect(self.closed.emit)
        bar.addWidget(b)
        root.addLayout(bar)

    def setup(self, meta=None) -> None:
        m = meta
        hours = float(getattr(m, "total_playtime", 0.0)) / 3600.0
        self.lbl_sum.setText(
            f"{T.tr('总局数')}: <b>{getattr(m,'total_runs',0)}</b><br>"
            f"{T.tr('通关次数')}: <b style='color:{T.GOLD}'>{getattr(m,'wins',0)}</b><br>"
            f"{T.tr('最高得分')}: <b style='color:{T.GOLD}'>{getattr(m,'best_score',0)}</b><br>"
            f"{T.tr('最高通关难度')}: <b>{getattr(m,'best_ascension_win',-1)}</b><br>"
            f"{T.tr('当前连胜')}: <b>{getattr(m,'streak',0)}</b>　"
            f"{T.tr('最长连胜')}: <b>{getattr(m,'best_streak',0)}</b><br>"
            f"{T.tr('累计游玩')}: <b>{hours:.1f}</b> {T.tr('小时')}")
        self.lb.clear()
        for i, row in enumerate(getattr(m, "leaderboard", []) or []):
            self.lb.addItem(
                f"{i+1:>2}.  {row.get('score',0):>6} {T.tr('分')}   "
                f"难度 {row.get('ascension',0)}   "
                f"{row.get('won_text','')}   {row.get('date','')}")


# =====================================================================
# 11. 设置
# =====================================================================


class SettingsScreen(QWidget):
    """设置：显示 / 音量占位 / 数据管理。"""

    closed = pyqtSignal()
    wipe_meta = pyqtSignal()
    wipe_save = pyqtSignal()

    def showEvent(self, ev):  # noqa: N802
        """每次进入设置界面时刷新曲库（可能刚往 music/ 里放了新歌）。"""
        super().showEvent(ev)
        try:
            self._music_refresh()
        except Exception:
            pass

    # ---- 音乐 -------------------------------------------------------- #
    def _lang_changed(self, idx: int) -> None:
        """切换语言：立即重建整个界面（所有文案都要换）。"""
        try:
            code = self.cb_lang.itemData(int(idx)) or "zh"
            _i18n.set_lang(str(code))
            # 记住选择
            try:
                import json as _json
                import os as _os
                from core import run as _run
                d = getattr(_run, "DATA_DIR", None) or "."
                p = _os.path.join(d, "prefs.json")
                cur = {}
                try:
                    cur = _json.load(open(p, encoding="utf-8"))
                except Exception:
                    cur = {}
                cur["lang"] = str(code)
                _os.makedirs(_os.path.dirname(p), exist_ok=True)
                _json.dump(cur, open(p, "w", encoding="utf-8"),
                           ensure_ascii=False)
            except Exception:
                pass
            # 重建主窗口的界面（文案全变）
            win = self.window()
            rebuild = getattr(win, "rebuild_screens", None)
            if callable(rebuild):
                rebuild()
        except Exception:
            pass

    def _vol_changed(self, v: int) -> None:
        self.cfg["volume"] = int(v)
        try:
            from core import audio
            audio.player(volume=int(v)).set_volume(int(v))
        except Exception:
            pass

    def _music_toggled(self, on: bool) -> None:
        self.cfg["music"] = bool(on)
        try:
            w = self.window()
            if hasattr(w, "restart_music"):
                w.restart_music()
        except Exception:
            pass

    # ---- 兑换码 ------------------------------------------------------ #
    def _cheat_reg(self):
        reg = getattr(self, "_creg", None)
        if reg is None:
            try:
                from core import cheats as CH
                reg = CH.CheatRegistry()
            except Exception:
                reg = None
            self._creg = reg
        return reg

    def _redeem(self) -> None:
        reg = self._cheat_reg()
        code = (self.ed_code.text() or "").strip()
        if reg is None:
            self._say("兑换码系统不可用。", ok=False)
            return
        if not code:
            self._say("请输入兑换码。", ok=False)
            return
        w = self.window()
        ok, msg = reg.redeem(code,
                             run=getattr(w, "run", None),
                             battle=getattr(w, "battle", None),
                             meta=getattr(w, "meta", None))
        self._say(msg, ok=ok)
        if ok:
            self.ed_code.clear()
            # 让地图/战斗界面刷新（兑换可能改了牌组/遗物）
            try:
                w = self.window()
                if hasattr(w, "refresh_current"):
                    w.refresh_current()
            except Exception:
                pass

    def _clear_code(self) -> None:
        try:
            self.ed_code.clear()
        except Exception:
            pass
        self._say("", ok=True)

    # ---- 曲目选择 ---------------------------------------------------- #
    def _music_refresh(self) -> None:
        try:
            from core import audio
            tracks = audio.all_tracks()
        except Exception:
            tracks = []
        self._tracks = tracks
        self.lst_tracks.clear()
        self.lb_tracks.setText(
            T.tr("music/ 共 %d 首 —— 双击播放") % len(tracks) if tracks
            else "music/ 目录为空，放入 mp3 后点「刷新列表」")
        for t in tracks:
            tag = t["file"]
            if t.get("scene"):
                tag += "   ［%s］" % t["scene"]
            self.lst_tracks.addItem(tag)
        self._mark_now()

    def _mark_now(self) -> None:
        try:
            from core import audio
            p = audio.player()
            cur = p.track
            self.lb_now.setText(
                T.tr("当前：%s") % os.path.basename(cur) if cur else T.tr("当前：未播放"))
            for i, t in enumerate(getattr(self, "_tracks", [])):
                it = self.lst_tracks.item(i)
                if it is None:
                    continue
                base = t["file"] + ("    ［%s］" % t["scene"] if t.get("scene") else "")
                it.setText(("♪ " if cur == t["path"] else "   ") + base)
        except Exception:
            pass

    def _music_play_selected(self) -> None:
        row = self.lst_tracks.currentRow()
        tracks = getattr(self, "_tracks", [])
        if row < 0 or row >= len(tracks):
            return
        try:
            from core import audio
            ok = audio.play_file(tracks[row]["path"])
            self.lb_now.setText(
                ("正在播放：%s" % tracks[row]["file"]) if ok
                else "播放失败：文件不可读")
            self._mark_now()
        except Exception:
            pass

    def _music_step(self, step: int) -> None:
        try:
            from core import audio
            cur = audio.player().track
            nxt = audio.next_track(cur, step)
            if nxt:
                audio.play_file(nxt)
                self.lb_now.setText("正在播放：%s" % os.path.basename(nxt))
                self._mark_now()
        except Exception:
            pass

    def _music_reveal(self) -> None:
        try:
            from core import audio
            d = audio.music_dir()
            os.makedirs(d, exist_ok=True)
            if sys.platform == "darwin":
                os.system('open "%s"' % d)
            elif os.name == "nt":
                os.startfile(d)  # type: ignore[attr-defined]
            else:
                os.system('xdg-open "%s" >/dev/null 2>&1 &' % d)
        except Exception:
            pass

    def _say(self, msg: str, ok: bool = True) -> None:
        try:
            col = T.Q_GREEN if ok else T.Q_RED
            self.lb_msg.setStyleSheet(
                f"color:{col.name()}; font-size:{T.FONT_SMALL}px;background:transparent;")
            self.lb_msg.setText(msg or "")
        except Exception:
            pass

    def __init__(self, parent=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg if cfg is not None else {}
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(9)
        self.tb = TitleBar("设 置", "", self)
        root.addWidget(self.tb)

        body = QHBoxLayout()
        body.setSpacing(14)

        # ---- 兑换码面板 ----
        cheat = QFrame(self)
        cheat.setObjectName("Panel")
        cv = QVBoxLayout(cheat)
        cv.setContentsMargins(20, 16, 20, 16)
        cv.setSpacing(9)
        cv.addWidget(W.SectionTitle("兑 换 码", cheat, T.Q_GOLD))
        hint = QLabel("输入特殊指令。部分码每局只能兑换一次。", cheat)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;background:transparent;")
        cv.addWidget(hint)
        self.ed_code = QLineEdit(cheat)
        self.ed_code.setPlaceholderText(T.tr("例如 manpower"))
        self.ed_code.setMaxLength(24)
        self.ed_code.returnPressed.connect(self._redeem)
        cv.addWidget(self.ed_code)
        brow = QHBoxLayout()
        self.btn_go = QPushButton("兑 换", cheat)
        self.btn_go.setObjectName("Primary")
        self.btn_go.clicked.connect(self._redeem)
        brow.addWidget(self.btn_go, 1)
        self.btn_clr = QPushButton("清空", cheat)
        self.btn_clr.clicked.connect(self._clear_code)
        brow.addWidget(self.btn_clr)
        cv.addLayout(brow)
        self.lb_msg = QLabel("", cheat)
        self.lb_msg.setWordWrap(True)
        self.lb_msg.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;background:transparent;")
        cv.addWidget(self.lb_msg)
        cv.addStretch(1)
        body.addWidget(cheat, 1)

        disp = QFrame(self)
        disp.setObjectName("Panel")
        dv = QVBoxLayout(disp)
        dv.setContentsMargins(20, 16, 20, 16)
        dv.setSpacing(10)
        dv.addWidget(W.SectionTitle("显 示", disp))
        # 语言切换（中 / English）—— 放在最上面，一进设置就能看到
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("语言 / Language", disp))
        lang_row.addStretch(1)
        self.cb_lang = QComboBox(disp)
        self.cb_lang.setFixedWidth(150)
        for code in _i18n.LANG_ORDER:
            self.cb_lang.addItem(_i18n.LANG_NAMES.get(code, code), code)
        try:
            _idx = _i18n.LANG_ORDER.index(_i18n.lang())
            self.cb_lang.setCurrentIndex(_idx)
        except Exception:
            pass
        self.cb_lang.currentIndexChanged.connect(self._lang_changed)
        lang_row.addWidget(self.cb_lang)
        dv.addLayout(lang_row)
        self.cb_full = QCheckBox("启动时全屏", disp)
        self.cb_full.setChecked(bool(self.cfg.get("fullscreen", False)))
        dv.addWidget(self.cb_full)
        self.cb_anim = QCheckBox("启用动画效果", disp)
        self.cb_anim.setChecked(bool(self.cfg.get("animation", True)))
        dv.addWidget(self.cb_anim)
        self.cb_shake = QCheckBox("启用屏幕震动", disp)
        self.cb_shake.setChecked(bool(self.cfg.get("screen_shake", True)))
        dv.addWidget(self.cb_shake)
        self.cb_confirm = QCheckBox("结束回合前需要确认", disp)
        self.cb_confirm.setChecked(bool(self.cfg.get("confirm_end_turn", False)))
        dv.addWidget(self.cb_confirm)
        dv.addSpacing(6)
        dv.addWidget(QLabel("音乐音量", disp))
        self.sl_vol = QSpinBox(disp)
        self.sl_vol.setRange(0, 100)
        self.sl_vol.setSingleStep(5)
        self.sl_vol.setValue(int(self.cfg.get("volume", 70)))
        self.sl_vol.valueChanged.connect(self._vol_changed)
        dv.addWidget(self.sl_vol)
        self.cb_music = QCheckBox("启用背景音乐", disp)
        self.cb_music.setChecked(bool(self.cfg.get("music", True)))
        self.cb_music.toggled.connect(self._music_toggled)
        dv.addWidget(self.cb_music)
        dv.addSpacing(6)
        dv.addWidget(QLabel("战斗动画速度（每步毫秒）", disp))
        self.spin_speed = QSpinBox(disp)
        self.spin_speed.setRange(120, 1200)
        self.spin_speed.setSingleStep(40)
        self.spin_speed.setValue(int(self.cfg.get("battle_step_ms", 400)))
        dv.addWidget(self.spin_speed)
        dv.addStretch(1)
        body.addWidget(disp, 1)

        # ---- 曲目选择 ----
        mus = QFrame(self)
        mus.setObjectName("Panel")
        mv = QVBoxLayout(mus)
        mv.setContentsMargins(20, 16, 20, 16)
        mv.setSpacing(8)
        mv.addWidget(W.SectionTitle("选 择 音 乐", mus, T.Q_GOLD))
        self.lb_tracks = QLabel("", mus)
        self.lb_tracks.setWordWrap(True)
        self.lb_tracks.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;background:transparent;")
        mv.addWidget(self.lb_tracks)
        self.lst_tracks = QListWidget(mus)
        self.lst_tracks.setMaximumHeight(170)
        self.lst_tracks.itemDoubleClicked.connect(
            lambda _it: self._music_play_selected())
        mv.addWidget(self.lst_tracks)
        brow2 = QHBoxLayout()
        self.btn_prev = QPushButton("◀ 上一首", mus)
        self.btn_prev.clicked.connect(lambda: self._music_step(-1))
        brow2.addWidget(self.btn_prev)
        self.btn_next = QPushButton("下一首 ▶", mus)
        self.btn_next.clicked.connect(lambda: self._music_step(1))
        brow2.addWidget(self.btn_next)
        self.btn_play = QPushButton("播 放", mus)
        self.btn_play.setObjectName("Primary")
        self.btn_play.clicked.connect(self._music_play_selected)
        brow2.addWidget(self.btn_play)
        mv.addLayout(brow2)
        brow3 = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新列表", mus)
        self.btn_refresh.clicked.connect(self._music_refresh)
        brow3.addWidget(self.btn_refresh)
        self.btn_open = QPushButton("打开 music/ 目录", mus)
        self.btn_open.clicked.connect(self._music_reveal)
        brow3.addWidget(self.btn_open)
        mv.addLayout(brow3)
        self.lb_now = QLabel("", mus)
        self.lb_now.setWordWrap(True)
        self.lb_now.setStyleSheet(
            f"color:{T.Q_GOLD.name()}; font-size:{T.FONT_SMALL}px;background:transparent;")
        mv.addWidget(self.lb_now)
        mv.addStretch(1)
        body.addWidget(mus, 1)

        data = QFrame(self)
        data.setObjectName("Panel")
        dav = QVBoxLayout(data)
        dav.setContentsMargins(20, 16, 20, 16)
        dav.setSpacing(10)
        dav.addWidget(W.SectionTitle("数 据 管 理", data, T.Q_RED))
        warn = QLabel(
            "以下操作不可撤销。存档与元进度位于 data/ 目录。", data)
        warn.setWordWrap(True)
        warn.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;background:transparent;")
        dav.addWidget(warn)
        b1 = QPushButton("删除当前战役存档", data)
        b1.setObjectName("Danger")
        b1.clicked.connect(self.wipe_save.emit)
        dav.addWidget(b1)
        b2 = QPushButton("清空元进度（成就 / 图鉴 / 排行）", data)
        b2.setObjectName("Danger")
        b2.clicked.connect(self.wipe_meta.emit)
        dav.addWidget(b2)
        dav.addStretch(1)

        info = QLabel(
            T.tr("钢铁战线 Steel Frontline") + "<br>"
            f"PyQt6 {self._qt_version()} · {T.tr('Qt 图形界面版')}<br>"
            + T.tr("与 Tkinter 版并存，共享同一套 core/ 引擎。"), data)
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;background:transparent;")
        dav.addWidget(info)
        body.addWidget(data, 1)
        root.addLayout(body, 1)

        bar = QHBoxLayout()
        # 手动检查更新（启动时也会自动查一次）
        self.btn_update = QPushButton("检 查 更 新", self)
        self.btn_update.setObjectName("Ghost")
        self.btn_update.setFixedWidth(150)
        self.btn_update.clicked.connect(self._check_update)
        bar.addWidget(self.btn_update)

        # 清理旧版本（不动存档）
        self.btn_clean = QPushButton("清理旧版本", self)
        self.btn_clean.setObjectName("Ghost")
        self.btn_clean.setFixedWidth(130)
        self.btn_clean.clicked.connect(self._cleanup_old)
        bar.addWidget(self.btn_clean)

        try:
            from core import version as _V
            # 注意：不要在这里 `from core import i18n as _i18n` ——
            # 那会让 _i18n 变成整个方法的局部变量，遮蔽模块级导入，
            # 导致上面语言下拉的 _i18n.LANG_ORDER 报 UnboundLocalError。
            import core.i18n as _i18n_mod
            ver = QLabel(("v" + _V.VERSION_LABEL_EN)
                         if _i18n_mod.is_english()
                         else ("v" + _V.VERSION_LABEL), self)
            ver.setStyleSheet(
                f"color:{T.TEXT_MUTED};font-size:{T.FONT_TINY}px;"
                f"background:transparent;padding-left:6px;")
            bar.addWidget(ver)
        except Exception:
            pass

        bar.addStretch(1)
        b = QPushButton("保 存 并 关 闭", self)
        b.setObjectName("Primary")
        b.setFixedWidth(200)
        b.clicked.connect(self._save_close)
        bar.addWidget(b)
        root.addLayout(bar)

    @staticmethod
    def _qt_version() -> str:
        try:
            from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
            return f"{PYQT_VERSION_STR} / Qt {QT_VERSION_STR}"
        except Exception:
            return "6.x"

    def values(self) -> dict:
        return {
            "fullscreen": self.cb_full.isChecked(),
            "animation": self.cb_anim.isChecked(),
            "screen_shake": self.cb_shake.isChecked(),
            "confirm_end_turn": self.cb_confirm.isChecked(),
            "battle_step_ms": int(self.spin_speed.value()),
        }

    def _cleanup_old(self) -> None:
        """打开「清理旧版本」对话框（不会删除存档）。"""
        try:
            from . import qcleanup
            qcleanup.show_cleanup_dialog(self)
        except Exception:
            pass

    def _check_update(self) -> None:
        """手动检查更新（会给出「已是最新」的反馈）。"""
        try:
            win = self.window()
            fn = getattr(win, "check_updates", None)
            if callable(fn):
                fn(silent=False)
                self.btn_update.setText("检查中…")
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(4000,
                                  lambda: self.btn_update.setText("检 查 更 新"))
        except Exception:
            pass

    def _save_close(self) -> None:
        self.cfg.update(self.values())
        self.closed.emit()


# =====================================================================
# 12. 牌堆查看（抽牌堆 / 弃牌堆 / 移除区）
# =====================================================================


class PileScreen(QWidget):
    """查看 牌库 / 弃牌堆 / 移除区。"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(9)
        self.tb = TitleBar("牌 堆 详 情", "", self)
        root.addWidget(self.tb)
        bar = QHBoxLayout()
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {T.BORDER};border-radius:6px;"
            f"background:{T.PANEL_LO};}}"
            f"QTabBar::tab{{background:{T.PANEL};color:{T.TEXT_DIM};"
            f"padding:8px 20px;border:1px solid {T.BORDER};}}"
            f"QTabBar::tab:selected{{background:{T.PANEL_LIGHT};color:{T.GOLD};"
            f"border-bottom:2px solid {T.GOLD};}}")
        self.piles: Dict[str, CardScroll] = {}
        for key, label in (("draw", "牌 库"), ("discard", "弃 牌 堆"),
                           ("exhaust", "移 除 区")):
            cs = CardScroll(self, card_scale=0.52)
            self.piles[key] = cs
            self.tabs.addTab(cs, label)
        root.addWidget(self.tabs, 1)
        bot = QHBoxLayout()
        bot.addStretch(1)
        b = QPushButton("关 闭", self)
        b.clicked.connect(self.closed.emit)
        bot.addWidget(b)
        root.addLayout(bot)

    def setup(self, battle) -> None:
        """从 BattleState 读取真实牌堆（core 公开属性）。"""
        if battle is None:
            # 不在战斗中：给出明确的空态说明，而不是一块空白
            for key, cs in self.piles.items():
                cs.set_cards([], footer=False)
            self.tb.subtitle = "当前不在战斗中 —— 牌库 / 弃牌堆 / 移除区 仅在战斗中有内容"
            return
        sets = {
            "draw": list(getattr(battle.player, "draw_pile", []) or []),
            "discard": list(getattr(battle.player, "discard_pile", []) or []),
            "exhaust": list(getattr(battle.player, "exhaust_pile", []) or []),
        }
        for key, cards in sets.items():
            cards = sorted(cards, key=lambda c: (c.defn.type, c.defn.name))
            dicts = []
            for ci in cards:
                d = RewardScreen._card_dict(ci.defn)
                d["uid"] = ci.uid
                d["upgraded"] = int(getattr(ci, "upgraded", 0) or 0)
                dicts.append(d)
            self.piles[key].set_cards(dicts, footer=False)
            idx = self.tabs.indexOf(self.piles[key])
            names = {"draw": "牌 库", "discard": "弃 牌 堆", "exhaust": "移 除 区"}
            self.tabs.setTabText(idx, f"{names[key]} ({len(cards)})")


class BigTitle(QWidget):
    """主菜单大标题：描边 + 金属渐变填充 + 军衔人字纹。

    QLabel 无法做渐变文字与描边，主标题必须自绘。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        W_, H_ = float(self.width()), float(self.height())
        fnt = T.font(52, True)
        fm = QFontMetricsF(fnt)
        texts = ["钢 铁 战 线", "STEEL FRONTLINE"]
        y = 4.0
        # 中文大标题
        path = QPainterPath()
        tw = fm.horizontalAdvance(texts[0])
        path.addText(QPointF(4, y + fm.ascent()), fnt, texts[0])
        p.setPen(QPen(T.a(T.Q_BLACK, 220), 5.0, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        g = QLinearGradient(QPointF(0, y), QPointF(0, y + fm.height()))
        g.setColorAt(0.0, T.qc("#F5E6A8"))
        g.setColorAt(0.45, T.Q_GOLD)
        g.setColorAt(0.55, T.qc("#8A6F1A"))
        g.setColorAt(1.0, T.qc("#D8C071"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawPath(path)
        # 英文副标题（放在中文标题正下方，不与分隔线重叠）
        fnt2 = T.font(15, True)
        fm2 = QFontMetricsF(fnt2)
        sub_y = y + fm.height() + 2.0
        p.setFont(fnt2)
        p.setPen(QPen(T.a(T.Q_TEXT_DIM, 220)))
        p.drawText(QRectF(8, sub_y, W_, fm2.height() + 4),
                   int(Qt.AlignmentFlag.AlignLeft) | int(Qt.AlignmentFlag.AlignVCenter),
                   "S T E E L   F R O N T L I N E")
        # 军衔人字纹装饰
        T.chevron(p, tw + 30, y + fm.height() * 0.36, 13, T.a(T.Q_GOLD, 190),
                  up=True, width=2.6)
        T.chevron(p, tw + 30, y + fm.height() * 0.36 + 17, 13,
                  T.a(T.Q_GOLD, 120), up=True, width=2.0)
        # 底部金线
        # 分隔线画在英文副标题**下方**（副标题底部再留 6px 间距）
        line_y = min(H_ - 3.0, sub_y + fm2.height() + 6.0)
        gg = QLinearGradient(QPointF(4, 0), QPointF(W_, 0))
        gg.setColorAt(0.0, T.a(T.Q_GOLD, 200))
        gg.setColorAt(0.7, T.a(T.Q_GOLD, 0))
        p.setPen(QPen(QBrush(gg), 2.0))
        p.drawLine(QPointF(4, line_y), QPointF(W_ - 4, line_y))
        p.end()
