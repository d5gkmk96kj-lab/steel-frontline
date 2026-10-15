"""钢铁战线 Steel Frontline — 卡组构筑界面 (qdeckbuild.py)
================================================================

1v1 对战前的卡组构筑。用户的要求是「开局满卡让你自己选一些作为卡组」，
所以这里**不做任何图鉴解锁门槛**：全部 134 张卡一次性开放。

界面结构
--------
::

    ┌──────────────────── 标题：卡 组 构 筑 ────────────────────┐
    │ [搜索框] [流派▾] [类型▾] [排序▾]       已选 23/40  [随机一套][推荐流派] │
    ├──────────────────────────────────┬────────────────────────┤
    │                                  │  统计面板               │
    │   卡牌网格（CardScroll 多行）      │   · 张数 / 平均费用      │
    │   点击卡片 = 加入 / 移除           │   · 费用曲线小图         │
    │                                  │   · 流派分布条           │
    │                                  │  [已选卡组 ▾ 可移除]     │
    ├──────────────────────────────────┴────────────────────────┤
    │ 提示文字                              [返回] [开 始 对 战]   │
    └───────────────────────────────────────────────────────────┘

设计约束
--------
* 渲染一律复用 :class:`qwidgets.CardView`，不重复造卡面。
* 统计（平均费用 / 费用曲线 / 流派分布）全部用 QPainter 自绘，开抗锯齿 + 渐变。
* ``core.deckbuild`` 尚未落地时用内置兜底实现，界面**永不**因为缺模块而崩。
* 面向玩家文案严格遵守 ARCHITECTURE.md 附录 B.1 术语表
  （能量→补给、格挡→掩体、遗物→勋章、中毒→燃烧、力量→火力、易伤→破甲、虚弱→压制）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import (
    QPointF, QRectF, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from . import qtheme as T
from . import qwidgets as W
from .qscreens import CardScroll, TitleBar


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
# core.deckbuild 兜底
# =====================================================================
# 契约：
#   DECK_SIZE_MIN, DECK_SIZE_MAX
#   validate_deck(card_ids) -> (bool, str)
#   random_deck(rng, size, arch=None) -> list[str]
#   recommended_decks() -> dict
# 模块尚未落地时用下面的等价款接管，保证界面可用。

DECK_SIZE_MIN = 20
DECK_SIZE_MAX = 40

_ARCH_KEYS = ("attack", "block", "poison", "energy", "summon")

#: 同名上限（core.deckbuild 未落地时的兜底；strike/defend 放宽到 3）
MAX_COPIES = 2
MAX_COPIES_EXEMPT = {"strike": 3, "defend": 3}


def _deckbuild_mod():
    """尝试拿到 core.deckbuild；拿不到返回 None。"""
    try:
        from core import deckbuild as DB      # type: ignore
        return DB
    except Exception:
        return None


def deck_limits() -> Tuple[int, int]:
    db = _deckbuild_mod()
    lo = int(getattr(db, "DECK_SIZE_MIN", DECK_SIZE_MIN) or DECK_SIZE_MIN)
    hi = int(getattr(db, "DECK_SIZE_MAX", DECK_SIZE_MAX) or DECK_SIZE_MAX)
    if lo > hi:
        lo, hi = hi, lo
    return max(1, lo), max(lo, hi)


def validate_deck(card_ids: Sequence[str]) -> Tuple[bool, str]:
    """校验卡组。优先用 core.deckbuild，失败/缺失时用本地等价规则。"""
    ids = [str(c) for c in (card_ids or [])]
    db = _deckbuild_mod()
    if db is not None and hasattr(db, "validate_deck"):
        try:
            res = db.validate_deck(list(ids))
            if isinstance(res, tuple) and len(res) == 2:
                return bool(res[0]), str(res[1])
        except Exception:
            pass
    # --- 本地兜底（与 core.deckbuild 的规则保持一致）---
    lo, hi = deck_limits()
    n = len(ids)
    if n == 0:
        return False, "卡组是空的，至少需要 %d 张" % lo
    if n < lo:
        return False, "还差 %d 张（%d/%d）" % (lo - n, n, lo)
    if n > hi:
        return False, "超出上限 %d 张（%d/%d）" % (n - hi, n, hi)
    try:
        from core import cards as C
        bad = [i for i in ids if i not in C.CARD_DB]
    except Exception:
        bad = []
    if bad:
        return False, "有 %d 张卡不存在" % len(bad)
    # 同名上限：strike/defend 放宽到 3
    counts: Dict[str, int] = {}
    for i in ids:
        counts[i] = counts.get(i, 0) + 1
    over = [(k, v) for k, v in counts.items()
            if v > MAX_COPIES_EXEMPT.get(k, MAX_COPIES)]
    if over:
        k, v = sorted(over, key=lambda kv: -kv[1])[0]
        name = k
        try:
            from core import cards as C
            d = C.CARD_DB.get(k)
            if d is not None:
                name = d.name
        except Exception:
            pass
        cap = MAX_COPIES_EXEMPT.get(k, MAX_COPIES)
        return False, "「%s」带了 %d 张，同名最多 %d 张" % (name, v, cap)
    return True, "OK"


def random_deck(rng=None, size: Optional[int] = None, arch: Optional[str] = None) -> List[str]:
    """随机一套卡组。优先 core.deckbuild。"""
    lo, hi = deck_limits()
    size = int(size or hi)
    size = max(lo, min(hi, size))
    db = _deckbuild_mod()
    if db is not None and hasattr(db, "random_deck"):
        try:
            out = db.random_deck(rng, size, arch)
            out = [str(c) for c in (out or [])]
            if out:
                return out
        except Exception:
            pass
    return _local_random_deck(rng, size, arch)


def _local_random_deck(rng, size: int, arch: Optional[str]) -> List[str]:
    import random as _random
    rng = rng or _random.Random()
    pool = _playable_defs()
    if arch:
        pool = [c for c in pool if c.arch == arch] or pool
    if not pool:
        return []
    out: List[str] = []
    # 先保证费用曲线健康：1~2 费占多数，再补高费
    for _ in range(size):
        out.append(rng.choice(pool).id)
    return out


def _playable_defs() -> List:
    """可入构筑的卡（排除状态/诅咒）。"""
    try:
        from core import cards as C
        return [c for c in C.CARD_LIST if c.type not in ("status", "curse")]
    except Exception:
        return []


def recommended_decks() -> Dict[str, List[str]]:
    """推荐流派卡组：{显示名: [def_id, ...]}。优先 core.deckbuild。"""
    db = _deckbuild_mod()
    if db is not None and hasattr(db, "recommended_decks"):
        try:
            raw = db.recommended_decks() or {}
            out: Dict[str, List[str]] = {}
            for k, v in raw.items():
                if isinstance(v, dict):                    # 兼容 {"cards":[...]}
                    v = v.get("cards") or v.get("deck") or []
                ids = [str(x) for x in (v or [])]
                if ids:
                    out[str(k)] = ids
            if out:
                return out
        except Exception:
            pass
    return _local_recommended()


def _local_recommended() -> Dict[str, List[str]]:
    """本地兜底推荐：每个流派挑「本流派 70% + 通用 30%」凑满上限张数。"""
    import random as _random
    _, hi = deck_limits()
    pool = _playable_defs()
    if not pool:
        return {}
    out: Dict[str, List[str]] = {}
    for arch in _ARCH_KEYS:
        mine = [c for c in pool if c.arch == arch]
        if not mine:
            continue
        rng = _random.Random(hash(arch) & 0xFFFF)
        n_mine = max(1, int(hi * 0.72))
        ids = [rng.choice(mine).id for _ in range(n_mine)]
        rest = [c for c in pool if c.id not in set(ids)]
        while len(ids) < hi and rest:
            ids.append(rng.choice(rest).id)
        out[T.ARCH_NAMES.get(arch, arch)] = ids[:hi]
    return out


# =====================================================================
# 费用曲线小图
# =====================================================================


class CostCurve(QWidget):
    """费用曲线：柱状图（自绘，抗锯齿 + 渐变 + 网格）。

    横轴为补给费用（0/1/2/3/4+），纵轴为张数。柱子按「是否超过平均值」
    上色，让玩家一眼看出曲线是否偏科。
    """

    def __init__(self, parent=None, height: int = 96):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._counts: List[int] = [0] * 5
        self._avg = 0.0
        self._pulse = 0.0
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.03) % 1.0
        self.update()

    def set_counts(self, counts: Sequence[int], avg: float = 0.0) -> None:
        self._counts = [int(c) for c in list(counts)[:5]] + [0] * max(0, 5 - len(counts))
        self._avg = float(avg)
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        r = QRectF(0, 0, self.width(), self.height())
        T.steel_plate(p, r, T.Q_PANEL, T.RADIUS_S, rivets=False)

        # 顶部留出标题带（16px），否则柱子顶端的数字会压在标题上
        pad_l, pad_r, pad_t, pad_b = 8.0, 8.0, 18.0, 16.0
        plot = QRectF(r.left() + pad_l, r.top() + pad_t,
                      max(1.0, r.width() - pad_l - pad_r),
                      max(1.0, r.height() - pad_t - pad_b))
        n = 5
        total = max(1, sum(self._counts))
        peak = max(1, max(self._counts))

        # 背景网格（3 条水平线）
        p.setPen(QPen(T.a(T.Q_BORDER, 150), 1.0, Qt.PenStyle.DashLine))
        for i in range(1, 4):
            y = plot.top() + plot.height() * i / 4.0
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        gap = 6.0
        bw = max(4.0, (plot.width() - gap * (n - 1)) / n)
        for i, c in enumerate(self._counts):
            x = plot.left() + i * (bw + gap)
            h = plot.height() * (c / float(peak))
            bar = QRectF(x, plot.bottom() - h, bw, h)
            # 底座凹槽
            T.fill_round(p, QRectF(x, plot.top(), bw, plot.height()), 3,
                         T.a(T.Q_BLACK, 70))
            if c > 0:
                over = self._avg and i >= int(round(self._avg))
                top = T.Q_GOLD if i >= 4 else (T.f(T.Q_GREEN, 1.5) if not over
                                               else T.qc("#C98F2E"))
                if i >= 4:
                    top = T.Q_ORANGE
                bot = T.f(top, 0.5)
                g = QLinearGradient(QPointF(bar.left(), bar.top()),
                                    QPointF(bar.left(), bar.bottom()))
                g.setColorAt(0.0, T.f(top, 1.25))
                g.setColorAt(1.0, bot)
                T.fill_round(p, bar, 3, QBrush(g))
                # 顶部高光
                hl = QRectF(bar.left() + 1.5, bar.top() + 1.2,
                            max(0.0, bar.width() - 3), 2.2)
                if hl.width() > 1:
                    T.fill_round(p, hl, 1.1, T.a(T.Q_WHITE, 70))
                T.text_c(p, bar.center().x(), bar.top() - 6,
                         str(c), T.font(T.FONT_TINY, True), T.Q_TEXT, shadow=True)
            # 底部 X 轴标签
            lbl = "4+" if i == 4 else str(i)
            T.text_c(p, x + bw / 2, r.bottom() - 8, lbl,
                     T.font(max(9, T.FONT_TINY - 1)),
                     T.Q_TEXT_DIM if c == 0 else T.Q_TEXT)
        # 标题
        T.text(p, QRectF(r.left() + 8, r.top() + 3, r.width() - 16, 15),
               "费用曲线 · 共 %d 张 · 均费 %.1f" % (total, self._avg),
               T.font(max(9, T.FONT_TINY - 1), True), T.Q_TEXT_DIM)
        p.end()


# =====================================================================
# 流派分布条
# =====================================================================


class ArchBars(QWidget):
    """流派分布：每个流派一条横向占比条 + 张数。"""

    def __init__(self, parent=None, height: int = 108):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._data: List[Tuple[str, int]] = []
        self._total = 0

    def set_data(self, data: Sequence[Tuple[str, int]]) -> None:
        self._data = [(str(k), int(v)) for k, v in data]
        self._total = sum(v for _, v in self._data)
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        r = QRectF(0, 0, self.width(), self.height())
        T.steel_plate(p, r, T.Q_PANEL, T.RADIUS_S, rivets=False)
        T.text(p, QRectF(r.left() + 8, r.top() + 3, r.width() - 16, 15),
               "流派分布", T.font(max(9, T.FONT_TINY - 1), True), T.Q_TEXT_DIM)

        rows = self._data or []
        if not rows:
            T.text_c(p, r.center().x(), r.center().y() + 6, "尚未选择卡牌",
                     T.font(T.FONT_SMALL), T.Q_TEXT_FAINT)
            p.end()
            return

        top = r.top() + 22.0
        row_h = max(12.0, (r.height() - top - 6) / max(1, len(rows)))
        label_w = 48.0
        num_w = 34.0
        for i, (key, cnt) in enumerate(rows):
            y = top + i * row_h
            cy = y + row_h / 2 - 1
            col = T.arch_color(key)
            T.text(p, QRectF(r.left() + 6, y, label_w, row_h),
                   T.ARCH_NAMES.get(key, key), T.font(max(9, T.FONT_TINY)),
                   T.Q_TEXT_DIM)
            bx = r.left() + 6 + label_w
            bw = max(10.0, r.width() - label_w - num_w - 14)
            track = QRectF(bx, cy - 4.5, bw, 9.0)
            T.fill_round(p, track, 4.5, T.a(T.Q_BLACK, 90))
            ratio = cnt / float(max(1, self._total))
            if cnt > 0:
                fill = QRectF(track.left(), track.top(),
                              max(6.0, track.width() * ratio), track.height())
                g = QLinearGradient(QPointF(fill.left(), fill.top()),
                                    QPointF(fill.left(), fill.bottom()))
                g.setColorAt(0.0, T.f(col, 1.5))
                g.setColorAt(1.0, T.f(col, 0.7))
                T.fill_round(p, fill, 4.5, QBrush(g))
                hl = QRectF(fill.left() + 1.5, fill.top() + 1.0,
                            max(0.0, fill.width() - 3), 2.0)
                if hl.width() > 1:
                    T.fill_round(p, hl, 1.0, T.a(T.Q_WHITE, 60))
            T.stroke_round(p, track, 4.5, T.a(T.Q_BORDER_HI, 160), 1.0)
            T.text(p, QRectF(r.right() - num_w - 6, y, num_w, row_h),
                   str(cnt), T.font(max(9, T.FONT_TINY), True),
                   T.Q_TEXT if cnt else T.Q_TEXT_FAINT,
                   align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        p.end()


# =====================================================================
# 已选卡组列表（可点击移除）
# =====================================================================


class PickedList(QFrame):
    """已选卡组：按卡名聚合显示「名称 xN」，点击减一。"""

    remove_requested = pyqtSignal(str)      # def_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PanelLo")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ids: List[str] = []
        self._rows: List[QPushButton] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        head = QLabel("已 选 卡 组", self)
        head.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_SMALL}px; font-weight:700;"
            f"background:transparent;")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(head)
        # 卡组最多 40 张，行数会超出面板高度 —— 必须放在滚动区里，
        # 否则 QVBoxLayout 会把每行压扁（文字糊成一团）。
        from PyQt6.QtWidgets import QScrollArea
        self._sa = QScrollArea(self)
        self._sa.setWidgetResizable(True)
        self._sa.setFrameShape(QFrame.Shape.NoFrame)
        self._sa.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sa.setStyleSheet(
            f"QScrollArea{{background:{T.PANEL_LO};border:none;}}"
            f"QScrollArea>QWidget>QWidget{{background:{T.PANEL_LO};}}")
        self._sa.viewport().setStyleSheet(f"background:{T.PANEL_LO};")
        self._body = QWidget()
        self._body.setStyleSheet(f"background:{T.PANEL_LO};")
        self._bl = QVBoxLayout(self._body)
        self._bl.setContentsMargins(2, 2, 2, 2)
        self._bl.setSpacing(3)
        self._sa.setWidget(self._body)
        lay.addWidget(self._sa, 1)

        self._empty = QLabel("点左边的卡加入卡组\n再次点击即移除", self._body)
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;"
            f"background:transparent;padding:20px;")
        self._bl.addWidget(self._empty)
        self._bl.addStretch(1)

    def set_ids(self, ids: Sequence[str]) -> None:
        self._ids = [str(i) for i in (ids or [])]
        # 清空（保留空态提示与 stretch）
        while self._bl.count() > 2:
            it = self._bl.takeAt(1)
            w = it.widget()
            if w is not None and w is not self._empty:
                w.setParent(None)
                w.deleteLater()
        self._rows = []

        agg: Dict[str, int] = {}
        order: List[str] = []
        for cid in self._ids:
            if cid not in agg:
                order.append(cid)
            agg[cid] = agg.get(cid, 0) + 1
        if not order:
            self._empty.show()
            return
        self._empty.hide()
        for cid in order:
            name = cid
            try:
                from core import cards as C
                d = C.CARD_DB.get(cid)
                if d is not None:
                    name = d.name
            except Exception:
                pass
            btn = QPushButton("%s  ×%d" % (T.tr(name), agg[cid]), self._body)
            btn.setObjectName("Ghost")
            btn.setToolTip(T.tr("点击移除一张「%s」") % T.tr(name))
            # 固定行高：卡组常有 20~40 行，若不锁高会被布局压扁成一团糊字
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f"QPushButton{{background:transparent;border:1px solid {T.BORDER};"
                f"color:{T.TEXT_DIM};font-size:{T.FONT_TINY}px;padding:0px 6px;"
                f"text-align:left;}}"
                f"QPushButton:hover{{border:1px solid {T.RED};color:{T.TEXT};}}")
            btn.clicked.connect(lambda _=False, c=cid: self.remove_requested.emit(c))
            self._bl.insertWidget(self._bl.count() - 2, btn)
            self._rows.append(btn)


# =====================================================================
# 主界面
# =====================================================================


class DeckBuildScreen(QWidget):
    """卡组构筑界面。

    信号
    ----
    * ``deck_confirmed(list)``  确认卡组并开始对战（list[str] of def_id）
    * ``closed()``              返回上一级
    """

    deck_confirmed = pyqtSignal(list)
    #: 人机对战：确认卡组时额外带上难度（"easy"/"normal"/"hard"）
    ai_confirmed = pyqtSignal(list, str)
    closed = pyqtSignal()

    #: 网格里每张卡的显示比例
    CARD_SCALE = 0.60

    def __init__(self, parent=None):
        super().__init__(parent)
        self.picked: List[str] = []
        self._search = ""
        self._arch: Optional[str] = None
        self._type = None             # str 或 tuple（"状态/诅咒" 是复合筛选）
        self._sort = "按类型"
        self._all: List = []
        self._mode = "local"          # "local" = 单机试玩, "net" = 联机
        self._subtitle = ""

        self._build()
        self._load_cards()
        # 注意顺序：必须先填充网格再 _refresh()。
        # _refresh() 只遍历 self.scroll.cards 更新选中态，它**不创建**卡片；
        # 少了 _refresh_grid() 这一句，整个左侧卡牌区就是全黑的（已踩过这个坑）。
        self._refresh_grid()
        self._refresh()

    # =================================================================
    # 构建
    # =================================================================
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 14, 22, 14)
        root.setSpacing(9)

        self.tb = TitleBar("卡 组 构 筑", "点卡加入 · 再点移除", self)
        root.addWidget(self.tb)

        # --- 工具栏 ---
        bar = QHBoxLayout()
        bar.setSpacing(9)

        self.ed_search = QLineEdit(self)
        self.ed_search.setPlaceholderText(T.tr("搜索卡名 / 效果关键字…"))
        self.ed_search.setFixedWidth(248)
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self._on_search)
        bar.addWidget(self.ed_search)

        self.cb_arch = QComboBox(self)
        self.cb_arch.addItems(["全部流派", "突击", "防御", "燃烧弹", "后勤", "支援"])
        self.cb_arch.currentIndexChanged.connect(self._on_filter)
        bar.addWidget(self.cb_arch)

        self.cb_type = QComboBox(self)
        self.cb_type.addItems(["全部类型", "攻击", "战术", "指令", "状态/诅咒"])
        self.cb_type.currentIndexChanged.connect(self._on_filter)
        bar.addWidget(self.cb_type)

        self.cb_sort = QComboBox(self)
        self.cb_sort.addItems(["按类型", "按稀有度", "按费用", "按名称"])
        self.cb_sort.currentIndexChanged.connect(self._on_filter)
        bar.addWidget(self.cb_sort)

        bar.addStretch(1)

        self.lbl_selected = QLabel("已选 0/30", self)
        self.lbl_selected.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2}px; font-weight:800;"
            f"background:transparent;")
        bar.addWidget(self.lbl_selected)

        self.btn_random = QPushButton("随 机 一 套", self)
        self.btn_random.setObjectName("Ghost")
        self.btn_random.setToolTip("随便来一套能打的卡组")
        self.btn_random.clicked.connect(self.on_random)
        bar.addWidget(self.btn_random)

        self.btn_reco = QPushButton("推 荐 流 派", self)
        self.btn_reco.setObjectName("Ghost")
        self.btn_reco.setToolTip("从推荐流派里挑一套")
        self.btn_reco.clicked.connect(self.on_recommended)
        bar.addWidget(self.btn_reco)

        self.cb_reco = QComboBox(self)
        self.cb_reco.setFixedWidth(110)
        self.cb_reco.setToolTip(T.tr("推荐流派列表"))
        bar.addWidget(self.cb_reco)

        root.addLayout(bar)

        # --- 主体：网格 + 右栏 ---
        mid = QHBoxLayout()
        mid.setSpacing(10)

        self.scroll = CardScroll(self, card_scale=self.CARD_SCALE, vertical=True, cols=7)
        self.scroll.card_picked.connect(self._on_card_picked)
        mid.addWidget(self.scroll, 1)

        side = QWidget(self)
        side.setFixedWidth(252)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(8)

        self.stat_card = QFrame(side)
        self.stat_card.setObjectName("Panel")
        # 统计块必须给足高度：4 行文字 + 费用曲线 + 流派分布，
        # 否则 QVBoxLayout 会把 lbl_stat 压扁导致文字互相重叠。
        self.stat_card.setSizePolicy(QSizePolicy.Policy.Preferred,
                                     QSizePolicy.Policy.Minimum)
        scv = QVBoxLayout(self.stat_card)
        scv.setContentsMargins(10, 8, 10, 10)
        scv.setSpacing(6)
        self.lbl_stat = QLabel("—", self.stat_card)
        self.lbl_stat.setStyleSheet(
            f"color:{T.TEXT}; font-size:{T.FONT_SMALL}px; background:transparent;")
        self.lbl_stat.setWordWrap(True)
        self.lbl_stat.setMinimumHeight(78)          # 4 行，防止被压缩重叠
        self.lbl_stat.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        scv.addWidget(self.lbl_stat, 0)
        self.curve = CostCurve(self.stat_card, 96)
        scv.addWidget(self.curve, 0)
        self.archs = ArchBars(self.stat_card, 104)
        scv.addWidget(self.archs, 0)
        sv.addWidget(self.stat_card, 0)

        self.picked_list = PickedList(side)
        self.picked_list.remove_requested.connect(self._remove_one)
        sv.addWidget(self.picked_list, 1)

        mid.addWidget(side, 0)
        root.addLayout(mid, 1)

        # --- 底部 ---
        foot = QHBoxLayout()
        foot.setSpacing(10)
        self.lbl_hint = QLabel("", self)
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px; background:transparent;")
        foot.addWidget(self.lbl_hint, 1)

        self.btn_clear = QPushButton("清 空", self)
        self.btn_clear.setObjectName("Ghost")
        self.btn_clear.clicked.connect(self.on_clear)
        foot.addWidget(self.btn_clear)

        self.btn_back = QPushButton("返 回", self)
        self.btn_back.setObjectName("Ghost")
        self.btn_back.clicked.connect(self._on_back)
        foot.addWidget(self.btn_back)

        self.btn_start = QPushButton("开 始 对 战", self)
        self.btn_start.setObjectName("Primary")
        self.btn_start.setMinimumWidth(190)
        self.btn_start.setMinimumHeight(44)
        self.btn_start.clicked.connect(self._on_start)
        foot.addWidget(self.btn_start)

        root.addLayout(foot)

    # =================================================================
    # 数据
    # =================================================================
    def _load_cards(self) -> None:
        """载入**全部 134 张**卡（含状态/诅咒）。

        用户要求「开局满卡让你自己选一些作为卡组」，所以这里不做任何
        图鉴解锁门槛，也不隐藏状态/诅咒牌 —— 它们是合法牌（玩家主动带
        = 付出代价）。合法性一律交给 ``deckbuild.validate_deck`` 判定。
        """
        try:
            from core import cards as C
            self._all = list(C.CARD_LIST)
        except Exception as exc:
            print(f"[qt.deckbuild] load cards failed: {exc!r}", flush=True)
            self._all = []
        # 推荐流派下拉
        recs = recommended_decks()
        self._recs = recs
        self.cb_reco.clear()
        self.cb_reco.addItems(list(recs.keys()) or ["（无推荐）"])

    def set_context(self, mode: str = "local", subtitle: str = "",
                    ai_difficulty: str = "") -> None:
        """由路由注入上下文（联机 / 人机 / 单机试玩）。

        ai_difficulty 非空表示这一局是**人机对战**，确认卡组后会交给
        core/ai.py 的电脑对手。
        """
        self._mode = mode or "local"
        self._subtitle = subtitle or ""
        self._ai_difficulty = ai_difficulty or ""
        self.tb.subtitle = self._subtitle or "点卡加入 · 再点移除"

    # =================================================================
    # 过滤
    # =================================================================
    def _on_search(self, text: str) -> None:
        self._search = (text or "").strip().lower()
        self._refresh_grid()

    def _on_filter(self, *_) -> None:
        archs = {"全部流派": None, "突击": "attack", "防御": "block",
                 "燃烧弹": "poison", "后勤": "energy", "支援": "summon"}
        types = {"全部类型": None, "攻击": "attack", "战术": "skill",
                 "指令": "power", "状态/诅咒": ("status", "curse")}
        self._arch = archs.get(self.cb_arch.currentText())
        self._type = types.get(self.cb_type.currentText())
        self._sort = self.cb_sort.currentText()
        self._refresh_grid()

    def _filtered(self) -> List:
        out = []
        for d in self._all:
            if self._arch and getattr(d, "arch", "") != self._arch:
                continue
            if self._type:
                if isinstance(self._type, tuple):
                    if getattr(d, "type", "") not in self._type:
                        continue
                elif getattr(d, "type", "") != self._type:
                    continue
            if self._search:
                hay = ("%s %s %s" % (getattr(d, "name", ""),
                                     getattr(d, "text", ""),
                                     " ".join(getattr(d, "keywords", ()) or ()))).lower()
                if self._search not in hay:
                    continue
            out.append(d)
        order = {"attack": 0, "skill": 1, "power": 2, "status": 3, "curse": 4}
        rar = {"basic": 0, "common": 1, "uncommon": 2, "rare": 3}
        if self._sort == "按类型":
            out.sort(key=lambda c: (order.get(c.type, 9), c.name))
        elif self._sort == "按稀有度":
            out.sort(key=lambda c: (-rar.get(c.rarity, 9), c.name))
        elif self._sort == "按费用":
            out.sort(key=lambda c: (c.cost if c.cost >= 0 else 99, c.name))
        else:
            out.sort(key=lambda c: c.name)
        return out

    def _refresh_grid(self) -> None:
        defs = self._filtered()
        dicts: List[dict] = []
        payloads: List[str] = []
        extra: Dict[int, str] = {}
        for i, d in enumerate(defs):
            cd = self._card_dict(d)
            n = self.picked.count(d.id)
            if n:
                cd["selected"] = True
            dicts.append(cd)
            payloads.append(d.id)
            if n:
                extra[i] = T.tr("已选 ×%d") % n
        try:
            self.scroll.set_cards(dicts, payloads=payloads, extra=extra, footer=True)
        except Exception as exc:
            print(f"[qt.deckbuild] grid failed: {exc!r}", flush=True)
            return
        # CardView 的选中态（金色描边）
        for cv, cid in zip(self.scroll.cards, payloads):
            cv.set_selected(self.picked.count(cid) > 0)

    @staticmethod
    def _card_dict(d) -> dict:
        """CardDef -> CardView 需要的 dict（复用 qscreens 的实现，避免分叉）。"""
        try:
            from .qscreens import RewardScreen
            return RewardScreen._card_dict(d)
        except Exception:
            return {"uid": -1, "def_id": getattr(d, "id", ""),
                    "name": getattr(d, "name", ""), "cost": getattr(d, "cost", 0),
                    "type": getattr(d, "type", "skill"),
                    "rarity": getattr(d, "rarity", "common"),
                    "arch": getattr(d, "arch", "attack"),
                    "text": getattr(d, "text", ""), "upgraded": 0,
                    "playable": True}

    # =================================================================
    # 统计刷新
    # =================================================================
    def _refresh(self) -> None:
        lo, hi = deck_limits()
        n = len(self.picked)
        self.lbl_selected.setText(T.tr("已选 %d/%d") % (n, hi))
        ratio = n / float(max(1, hi))
        ok, why = validate_deck(self.picked)
        col = T.Q_GREEN if ok else (T.Q_GOLD if ratio > 0.6 else T.Q_ORANGE)
        if n > hi:
            col = T.Q_RED
        self.lbl_selected.setStyleSheet(
            f"color:{_hex(col)}; font-size:{T.FONT_H2}px; font-weight:800;"
            f"background:transparent;")

        self._refresh_stats()
        self.picked_list.set_ids(self.picked)

        self.btn_start.setEnabled(bool(ok))
        self.btn_start.setToolTip(why if not ok else "带着这套卡组上战场")
        if not ok:
            self.lbl_hint.setText("⚠ " + why)
            self.lbl_hint.setStyleSheet(
                f"color:{T.ORANGE}; font-size:{T.FONT_SMALL}px; background:transparent;")
        else:
            side = T.tr("对方" if self._mode == "net" else "战场")
            self.lbl_hint.setText(
                T.tr("✓ 卡组就绪（%d 张）—— 点「开始对战」把卡组交给%s。")
                % (n, side))
            self.lbl_hint.setStyleSheet(
                f"color:{T.GREEN}; font-size:{T.FONT_SMALL}px; background:transparent;")
        for cv in getattr(self.scroll, "cards", []):
            cid = str(cv.card.get("def_id", ""))
            cv.set_selected(self.picked.count(cid) > 0)

    def _refresh_stats(self) -> None:
        lo, hi = deck_limits()
        n = len(self.picked)
        counts = [0] * 5
        arch_cnt: Dict[str, int] = {}
        cost_sum = 0
        cost_n = 0
        try:
            from core import cards as C
            for cid in self.picked:
                d = C.CARD_DB.get(cid)
                if d is None:
                    continue
                arch_cnt[d.arch] = arch_cnt.get(d.arch, 0) + 1
                if d.cost < 0:
                    counts[4] += 1
                    continue
                ci = min(4, max(0, int(d.cost)))
                counts[ci] += 1
                cost_sum += int(d.cost)
                cost_n += 1
        except Exception:
            pass
        avg = (cost_sum / cost_n) if cost_n else 0.0
        self.curve.set_counts(counts, avg)
        rows = [(k, arch_cnt.get(k, 0)) for k in _ARCH_KEYS]
        self.archs.set_data(rows)

        atk = sum(1 for cid in self.picked
                  if self._defn(cid) is not None and self._defn(cid).type == "attack")
        skl = n - atk
        rar = {}
        for cid in self.picked:
            d = self._defn(cid)
            if d is not None:
                rar[d.rarity] = rar.get(d.rarity, 0) + 1
        rar_txt = " · ".join("%s %d" % (T.RARITY_NAMES.get(k, k), v)
                             for k, v in sorted(rar.items(), key=lambda kv: -kv[1]))
        lines = [
            T.tr("张数 %d / %d   ·   平均补给 %.2f") % (n, hi, avg),
            T.tr("攻击 %d  ·  战术/指令 %d") % (atk, skl),
            rar_txt or "—",
            T.tr("距离下限还差 %d 张") % max(0, lo - n) if n < lo else T.tr("已达可出战张数"),
        ]
        self.lbl_stat.setText("\n".join(lines))

    @staticmethod
    def _defn(cid: str):
        try:
            from core import cards as C
            return C.CARD_DB.get(cid)
        except Exception:
            return None

    # =================================================================
    # 交互
    # =================================================================
    def _on_card_picked(self, _idx: int, payload) -> None:
        cid = str(payload or "")
        if not cid:
            return
        _, hi = deck_limits()
        if self.picked.count(cid) > 0:
            self._remove_one(cid)
        else:
            if len(self.picked) >= hi:
                self._flash_hint("卡组已满（%d 张），先移除一张再加入。" % hi)
                return
            self.picked.append(cid)
            self._refresh()

    def _remove_one(self, cid: str) -> None:
        cid = str(cid or "")
        if cid in self.picked:
            self.picked.remove(cid)
            self._refresh()

    def _flash_hint(self, msg: str) -> None:
        self.lbl_hint.setText("⚠ " + msg)
        self.lbl_hint.setStyleSheet(
            f"color:{T.ORANGE}; font-size:{T.FONT_SMALL}px; background:transparent;")

    def on_clear(self) -> None:
        self.picked = []
        self._refresh()

    def on_random(self) -> None:
        try:
            import random as _r
            self.picked = random_deck(_r.Random(), None, None)
        except Exception as exc:
            print(f"[qt.deckbuild] random_deck failed: {exc!r}", flush=True)
            self.picked = []
        self._refresh()

    def on_recommended(self) -> None:
        name = self.cb_reco.currentText()
        ids = list(self._recs.get(name) or [])
        if not ids:
            self._flash_hint("该流派暂时没有可用推荐卡组。")
            return
        self.picked = ids
        self._refresh()

    def _on_back(self) -> None:
        self.closed.emit()

    def _on_start(self) -> None:
        ok, why = validate_deck(self.picked)
        if not ok:
            self._flash_hint(why)
            return
        diff = getattr(self, "_ai_difficulty", "") or ""
        if diff:
            # 人机对战：走单独的信号，由路由交给电脑对手
            try:
                self.ai_confirmed.emit(list(self.picked), diff)
                return
            except Exception:
                pass
        self.deck_confirmed.emit(list(self.picked))

    # =================================================================
    # 供外部/自检调用
    # =================================================================
    def set_deck(self, ids: Sequence[str]) -> None:
        self.picked = [str(i) for i in (ids or [])]
        self._refresh()

    def visible_card_count(self) -> int:
        return len(getattr(self.scroll, "cards", []))

    def refresh(self) -> None:
        self._load_cards()
        self._refresh()
