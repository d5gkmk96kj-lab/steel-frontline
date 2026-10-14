"""钢铁战线 Steel Frontline — 战区推进图 (qmap.py)
================================================================
把 ``RunState.map_nodes`` / ``reachable_nodes()`` / ``move_to()`` 画成一张
作战沙盘：

* 沙盘底图（焦土做旧纸张 + 等高线 + 罗盘 + 比例尺）
* 节点用军事符号（遭遇战=爆裂、精锐=骷髅、事件=?、补给站=齿轮、
  战地医院=十字、缴获=星、要塞=铁十字）
* 可达节点脉冲发光（QPropertyAnimation），已访问节点打勾变暗
* 节点之间画虚线行军路径，当前节点插旗帜
* 顶部显示 战役难度 / 幕 / 层 / 总部 HP / 金币 / 勋章

全部用 QPainter 绘制在**单个 canvas** 上（地图需要连线，属于自绘场景），
但外层 HUD 与按钮一律走 QLayout + QSS。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from . import qtheme as T

# 统一动画帧长（60fps）。所有装饰性动画共用它，避免不同 timer 周期
# 互相拖慢导致「锁帧」观感（用户实测：40~60ms 会把整机压到 20~25fps）。
_FRAME_MS = 16

from . import qwidgets as W


# =====================================================================
# 节点符号
# =====================================================================


def draw_node_symbol(p: QPainter, kind: str, cx: float, cy: float, s: float,
                     col: QColor) -> None:
    """按节点类型画军事符号（s 为半径）。"""
    if kind == "battle":
        W.IntentBadge._icon(p, QPointF(cx, cy), "attack", col)
    elif kind == "elite":
        # 骷髅
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(QPointF(cx, cy - s * 0.22), s * 0.72, s * 0.72)
        p.drawRect(QRectF(cx - s * 0.38, cy + s * 0.30, s * 0.76, s * 0.46))
        p.setBrush(QBrush(T.a(T.Q_BLACK, 235)))
        p.drawEllipse(QPointF(cx - s * 0.28, cy - s * 0.26), s * 0.21, s * 0.21)
        p.drawEllipse(QPointF(cx + s * 0.28, cy - s * 0.26), s * 0.21, s * 0.21)
        p.setPen(QPen(T.a(T.Q_BLACK, 235), max(1.0, s * 0.11)))
        p.drawLine(QPointF(cx - s * 0.20, cy + s * 0.58),
                   QPointF(cx - s * 0.20, cy + s * 0.76))
        p.drawLine(QPointF(cx + s * 0.20, cy + s * 0.58),
                   QPointF(cx + s * 0.20, cy + s * 0.76))
    elif kind == "event":
        T.text_c(p, cx, cy, "?", T.font(int(s * 1.9), True), col)
    elif kind == "shop":
        p.setPen(QPen(col, max(1.4, s * 0.20)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), s * 0.44, s * 0.44)
        for i in range(8):
            ang = i * math.pi / 4
            p.drawLine(QPointF(cx + math.cos(ang) * s * 0.52, cy + math.sin(ang) * s * 0.52),
                       QPointF(cx + math.cos(ang) * s * 0.92, cy + math.sin(ang) * s * 0.92))
    elif kind == "rest":
        # 战地医院：十字
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawRect(QRectF(cx - s * 0.24, cy - s * 0.92, s * 0.48, s * 1.84))
        p.drawRect(QRectF(cx - s * 0.92, cy - s * 0.24, s * 1.84, s * 0.48))
    elif kind == "treasure":
        T.star(p, cx, cy, s * 0.95, col)
    elif kind == "boss":
        # 铁十字
        p.setPen(QPen(col, max(1.6, s * 0.24)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = s * 0.92
        p.drawLine(QPointF(cx - r, cy - r), QPointF(cx + r, cy + r))
        p.drawLine(QPointF(cx + r, cy - r), QPointF(cx - r, cy + r))
        p.drawLine(QPointF(cx, cy - r * 1.05), QPointF(cx, cy + r * 1.05))
        p.drawLine(QPointF(cx - r * 1.05, cy), QPointF(cx + r * 1.05, cy))
    else:
        T.star(p, cx, cy, s * 0.9, col)


# =====================================================================
# 沙盘画布
# =====================================================================


class MapCanvas(QWidget):
    """战区推进图主画布。可达节点可点击。"""

    node_chosen = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.run = None
        self.setMinimumSize(900, 620)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._nodes: List[dict] = []          # {id,row,col,kind,visited,x,y,r}
        self._edges: List[Tuple[int, int]] = []
        self._reachable: set = set()
        self._hover_id: Optional[int] = None
        self._phase = 0.0
        # 入场淡入是装饰性的：默认 1.0（完全可见），动画只是把它从 0 拉回来。
        # 若默认 0，任何不跑动画的环境（离屏渲染/无头遍历）都会整张图空白。
        self._enter = 1.0
        self._anim_enter = QPropertyAnimation(self, b"enterT", self)
        self._anim_enter.setDuration(460)
        self._anim_enter.setStartValue(0.0)
        self._anim_enter.setEndValue(1.0)
        self._anim_enter.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._t = QTimer(self)
        self._t.setInterval(_FRAME_MS)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.035) % (math.pi * 2)
        self.update()

    def _get_enter(self) -> float:
        return self._enter

    def _set_enter(self, v: float) -> None:
        self._enter = float(v)
        self.update()

    enterT = pyqtProperty(float, fget=_get_enter, fset=_set_enter)

    # -- 数据 -------------------------------------------------------------
    def set_run(self, run) -> None:
        self.run = run
        self._last_size = (0.0, 0.0)   # 强制下一次 paint 重新布局
        self._recompute()
        # 入场动画只是锦上添花，**绝不能**让它决定节点是否可见：
        # 离屏/无头环境下动画定时器不推进，若以 enterT 作为可见性开关，
        # 整张地图会永久空白。因此 _enter 恒为 1.0，动画仅做一次轻微缩放提示。
        self._enter = 1.0
        self._anim_enter.stop()

    def refresh(self) -> None:
        self._recompute()
        self.update()

    def _recompute(self) -> None:
        self._nodes = []
        self._edges = []
        self._reachable = set()
        if self.run is None:
            return
        nodes = list(getattr(self.run, "map_nodes", []) or [])
        if not nodes:
            return
        try:
            self._reachable = {n.id for n in self.run.reachable_nodes()}
        except Exception:
            self._reachable = set()
        rows = max(1, max(int(n.row) for n in nodes) + 1)
        W_, H_ = max(200, self.width()), max(200, self.height())
        pad_x, pad_y = 74.0, 46.0
        row_h = (H_ - pad_y * 2) / max(1, rows - 1) if rows > 1 else 0.0

        # 每行的列数
        by_row: Dict[int, List] = {}
        for n in nodes:
            by_row.setdefault(int(n.row), []).append(n)

        # 关键：col 是「行内局部索引」（每行都从 0 开始），不是全局泳道。
        # 必须放进**固定列数的网格**里定位，否则每行各自铺满全宽，
        # 15 行叠起来会形成几根竖直长柱而不是爬塔形状。
        grid_cols = max(1, max((len(g) for g in by_row.values()), default=1))
        usable_w = W_ - pad_x * 2
        slot_w = usable_w / grid_cols

        for r, group in by_row.items():
            group_sorted = sorted(group, key=lambda n: int(n.col))
            k = len(group_sorted)
            offset = (grid_cols - k) / 2.0        # 行内整体居中
            for i, n in enumerate(group_sorted):
                slot = offset + i                 # 0..grid_cols-1 的浮点槽位
                x = pad_x + (slot + 0.5) * slot_w
                # 确定性抖动（用 node.id 做种子，绝不用随机数，否则重绘会跳）
                x += ((int(n.id) * 37) % 11 - 5) * 1.5
                y = H_ - pad_y - r * row_h        # row 0 在底部（起点），Boss 在顶部
                self._nodes.append({
                    "id": int(n.id), "row": int(n.row), "col": int(n.col),
                    "kind": str(n.kind), "visited": bool(n.visited),
                    "x": x, "y": y,
                    "r": 28.0 if str(n.kind) == "boss" else 18.0,
                })
        # 边（去重，避免同一连线画两遍）
        seen = set()
        for n in nodes:
            for e in (getattr(n, "edges", []) or []):
                a, b = int(n.id), int(e)
                key = (min(a, b), max(a, b))
                if key in seen:
                    continue
                seen.add(key)
                self._edges.append(key)

    def _node_at(self, pos: QPoint) -> Optional[int]:
        x, y = float(pos.x()), float(pos.y())
        for nd in self._nodes:
            dx, dy = x - nd["x"], y - nd["y"]
            if dx * dx + dy * dy <= (nd["r"] + 8) ** 2:
                return nd["id"]
        return None

    # -- 交互 -------------------------------------------------------------
    def mouseMoveEvent(self, ev):  # noqa: N802
        nid = self._node_at(ev.position().toPoint())
        if nid != self._hover_id:
            self._hover_id = nid
            can = nid is not None and nid in self._reachable
            self.setCursor(Qt.CursorShape.PointingHandCursor if can
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, ev):  # noqa: N802
        self._hover_id = None
        self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        nid = self._node_at(ev.position().toPoint())
        if nid is not None and nid in self._reachable:
            self.node_chosen.emit(int(nid))

    # -- 绘制 -------------------------------------------------------------
    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        W_, H_ = float(self.width()), float(self.height())
        self._sand_table(p, W_, H_)

        # 自动重算：尺寸变化、或还没算出节点时都要重算。
        # （旧逻辑要求 self._nodes 非空才重算，导致"先设 run 后有尺寸"时永久空白。）
        if self.run is not None and (self._last_size != (W_, H_) or not self._nodes):
            self._recompute()
        self._last_size = (W_, H_)

        if not self._nodes:
            T.text_c(p, W_ / 2, H_ / 2, "战区推进图尚未生成",
                     T.font(T.FONT_H2, True), T.Q_TEXT_DIM)
            p.end()
            return

        pos = {nd["id"]: (nd["x"], nd["y"]) for nd in self._nodes}
        # 1) 行军路径（虚线）
        for (a, b) in self._edges:
            if a not in pos or b not in pos or a >= b:
                continue
            x1, y1 = pos[a]
            x2, y2 = pos[b]
            na = next(n for n in self._nodes if n["id"] == a)
            live = (a in self._reachable) or (b in self._reachable)
            cur = self.run.current_node if self.run else None
            if cur is not None and cur in (a, b):
                col = T.a(T.GOLD, 200)
                width = 2.4
            elif live:
                col = T.a(T.Q_GREEN, 175)
                width = 2.0
            else:
                col = T.a(T.Q_BORDER_HI, 120)
                width = 1.2
            pen = QPen(col, width, Qt.PenStyle.DashLine)
            pen.setDashPattern([5, 5])
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 2) 节点
        for nd in self._nodes:
            self._draw_node(p, nd)

        # 3) 当前节点旗帜 + 提示
        cur = getattr(self.run, "current_node", None)
        if cur is not None:
            for nd in self._nodes:
                if nd["id"] == cur:
                    self._flag(p, nd["x"], nd["y"] - nd["r"] - 6)
        # 4) 可达节点闪烁提示
        if not self._reachable and cur is None:
            T.text_c(p, W_ / 2, H_ - 30, "选择起点开始推进",
                     T.font(T.FONT_BODY, True), T.Q_GOLD)
        p.end()

    _last_size: Tuple[float, float] = (0.0, 0.0)

    def _sand_table(self, p: QPainter, W_: float, H_: float) -> None:
        """沙盘底：焦土纸张 + 等高线 + 网格 + 罗盘 + 比例尺 + 暗角。"""
        base = T.qc("#2A2419")
        g = QLinearGradient(QPointF(0, 0), QPointF(W_ * 0.35, H_))
        g.setColorAt(0.0, T.mix(base, T.Q_GOLD, 0.05))
        g.setColorAt(0.55, base)
        g.setColorAt(1.0, T.mix(base, T.Q_BLACK, 0.42))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(0, 0, W_, H_))

        # 等高线（同心不规则环）
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(9):
            rr = (i + 1) * max(W_, H_) * 0.075
            p.setPen(QPen(T.a(T.Q_RUST, 26), 1.0))
            path = QPainterPath()
            cx, cy = W_ * 0.34, H_ * 0.62
            first = True
            for k in range(73):
                ang = k * math.pi / 36
                rad = rr * (1.0 + 0.075 * math.sin(ang * 3.0 + i) + 0.045 * math.cos(ang * 5.0 - i))
                pt = QPointF(cx + math.cos(ang) * rad * 1.25,
                             cy + math.sin(ang) * rad * 0.85)
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
            p.drawPath(path)

        # 网格
        p.setPen(QPen(T.a(T.Q_TEXT_FAINT, 22), 1.0))
        step = 62
        for x in range(0, int(W_), step):
            p.drawLine(QPointF(x, 0), QPointF(x, H_))
        for y in range(0, int(H_), step):
            p.drawLine(QPointF(0, y), QPointF(W_, y))

        # 暗角
        vg = QRadialGradient(QPointF(W_ * 0.5, H_ * 0.5), max(W_, H_) * 0.72)
        vg.setColorAt(0.5, T.a(T.Q_BLACK, 0))
        vg.setColorAt(1.0, T.a(T.Q_BLACK, 130))
        p.setBrush(QBrush(vg))
        p.drawRect(QRectF(0, 0, W_, H_))

        # 罗盘（右下）
        self._compass(p, W_ - 74, H_ - 74, 34)
        # 比例尺（左下）
        p.setPen(QPen(T.a(T.Q_TEXT_DIM, 150), 1.4))
        y0 = H_ - 26
        p.drawLine(QPointF(26, y0), QPointF(150, y0))
        for xx in (26, 88, 150):
            p.drawLine(QPointF(xx, y0 - 5), QPointF(xx, y0 + 5))
        p.setFont(T.font(T.FONT_TINY))
        p.setPen(QPen(T.a(T.Q_TEXT_DIM, 170)))
        p.drawText(QRectF(26, y0 - 24, 130, 16),
                   int(Qt.AlignmentFlag.AlignCenter), "0        50        100 km")

    def _compass(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        p.setPen(QPen(T.a(T.Q_GOLD, 150), 1.4))
        p.setBrush(QBrush(T.a(T.Q_BLACK, 70)))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(T.a(T.Q_GOLD, 110), 1.0))
        p.drawEllipse(QPointF(cx, cy), r * 0.74, r * 0.74)
        # 四向
        for i, lbl in enumerate(("N", "E", "S", "W")):
            ang = -math.pi / 2 + i * math.pi / 2
            tx, ty = cx + math.cos(ang) * (r - 10), cy + math.sin(ang) * (r - 10)
            T.text_c(p, tx, ty, lbl, T.font(T.FONT_TINY, True),
                     T.GOLD if i == 0 else T.a(T.Q_TEXT_DIM, 200))
        # 指针
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.Q_RED))
        p.drawPolygon(QPolygonF([QPointF(cx, cy - r * 0.66),
                                 QPointF(cx - r * 0.15, cy),
                                 QPointF(cx + r * 0.15, cy)]))
        p.setBrush(QBrush(T.Q_STEEL))
        p.drawPolygon(QPolygonF([QPointF(cx, cy + r * 0.66),
                                 QPointF(cx - r * 0.15, cy),
                                 QPointF(cx + r * 0.15, cy)]))

    def _draw_node(self, p: QPainter, nd: dict) -> None:
        x, y, r = nd["x"], nd["y"], nd["r"]
        kind = nd["kind"]
        col = T.node_color(kind)
        reachable = nd["id"] in self._reachable
        visited = nd["visited"]
        hovered = nd["id"] == self._hover_id
        cur = getattr(self.run, "current_node", None) == nd["id"]
        # 逐行错落的入场；enter>=1 时 appear 恒为 1（完全可见）
        stagger = min(0.42, nd["row"] * 0.03)
        appear = max(0.0, min(1.0, (self._enter - stagger) / max(0.01, 1.0 - stagger)))
        scale = 0.72 + 0.28 * appear
        alpha = int(255 * appear)

        p.save()
        p.translate(x, y)
        p.scale(scale, scale)
        pulse = 0.5 + 0.5 * math.sin(self._phase + nd["row"] * 0.6)

        # 可达：外圈脉冲光晕
        if reachable and not visited:
            for i in range(3):
                k = (i + (pulse % 1.0)) / 3.0
                glow_r = r + 6 + k * 20
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(T.a(col, int(110 * (1.0 - k))), 2.0))
                p.drawEllipse(QPointF(0, 0), glow_r, glow_r)

        # 底盘
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, int(150 * appear))))
        p.drawEllipse(QPointF(0, 3), r + 3, r + 3)
        g = QRadialGradient(QPointF(-r * 0.3, -r * 0.38), r * 2.3)
        base = T.mix(T.Q_PANEL, col, 0.26 if not visited else 0.10)
        g.setColorAt(0.0, T.a(T.f(base, 1.40), alpha))
        g.setColorAt(0.62, T.a(base, alpha))
        g.setColorAt(1.0, T.a(T.f(base, 0.62), alpha))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), r, r)

        # 描边
        ring = col if not visited else T.Q_TEXT_FAINT
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(T.a(ring, min(255, int((230 if reachable else 165) * appear))),
                      2.4 if (reachable or cur) else 1.5))
        p.drawEllipse(QPointF(0, 0), r, r)
        # 内环
        p.setPen(QPen(T.a(ring, int(70 * appear)), 1.0))
        p.drawEllipse(QPointF(0, 0), r - 4.5, r - 4.5)

        # 符号
        sym_col = T.a(T.f(col, 1.35) if not visited else T.Q_TEXT_FAINT, alpha)
        draw_node_symbol(p, kind, 0.0, 0.0, r * 0.46, sym_col)

        # 已访问：打勾 + 压暗
        if visited:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(T.a(T.Q_BG_DEEP, 120)))
            p.drawEllipse(QPointF(0, 0), r, r)
            p.setPen(QPen(T.a(T.Q_GREEN, 230), 2.6, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(-r * 0.38, 0),
                                      QPointF(-r * 0.08, r * 0.30),
                                      QPointF(r * 0.42, -r * 0.32)]))

        # 悬停放大提示
        if hovered and reachable:
            p.setPen(QPen(T.a(T.qc("#FFE9A8"), 235), 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), r + 5, r + 5)

        # 类型名（仅在悬停 / 可达 / 当前节点 / Boss 时显示，避免 15 行标签互相压叠）
        if hovered or reachable or cur or kind in ("boss", "elite"):
            fnt = T.font(T.FONT_TINY, True)
            label = T.NODE_NAMES.get(kind, kind)
            box = QRectF(-46, r + 3, 92, 15)
            T.fill_round(p, box, 5, T.a(T.Q_BG_DEEP, 195))
            T.text_c(p, 0, r + 10.5, label, fnt,
                     T.a(T.Q_TEXT if not visited else T.Q_TEXT_FAINT, alpha))
        p.restore()

    def _flag(self, p: QPainter, x: float, y: float) -> None:
        """当前节点插旗。"""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(T.Q_BLACK, 110)))
        p.drawEllipse(QPointF(x, y + 24), 12, 4)
        p.setBrush(QBrush(T.f(T.Q_STEEL, 0.9)))
        p.drawRect(QRectF(x - 1.6, y - 26, 3.2, 50))
        g = QLinearGradient(QPointF(x, y - 26), QPointF(x + 26, y - 6))
        g.setColorAt(0.0, T.f(T.Q_GOLD, 1.2))
        g.setColorAt(1.0, T.f(T.Q_GOLD, 0.72))
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([QPointF(x + 1.6, y - 26),
                                 QPointF(x + 28, y - 19),
                                 QPointF(x + 1.6, y - 8)]))
        T.star(p, x + 10, y - 17, 4.2, T.a(T.Q_TEXT, 225))


# =====================================================================
# HUD
# =====================================================================


class MapHUD(QFrame):
    """顶部作战态势栏。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 7, 14, 7)
        lay.setSpacing(16)

        self.lbl_act = QLabel("第一幕", self)
        self.lbl_act.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2}px; font-weight:700;")
        lay.addWidget(self.lbl_act)

        self.lbl_diff = QLabel("", self)
        self.lbl_diff.setStyleSheet(f"color:{T.qc('#B5651D').name()};"
                                    f"font-size:{T.FONT_SMALL}px; font-weight:600;")
        lay.addWidget(self.lbl_diff)

        self.lbl_seed = QLabel("", self)
        self.lbl_seed.setStyleSheet(f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;")
        lay.addWidget(self.lbl_seed)

        lay.addStretch(1)

        self.lbl_floor = self._stat(lay, "推进", "0 层")
        self.lbl_hp = self._stat(lay, "总部", "75/75")
        self.lbl_gold = self._stat(lay, "金币", "99")
        self.lbl_relic = self._stat(lay, "勋章", "1")

    def _stat(self, lay: QHBoxLayout, title: str, val: str) -> QLabel:
        box = QWidget(self)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        t = QLabel(title, box)
        t.setStyleSheet(f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl = QLabel(val, box)
        val_lbl.setStyleSheet(f"color:{T.TEXT}; font-size:{T.FONT_BODY}px;"
                              f"font-weight:700;")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        v.addWidget(val_lbl)
        lay.addWidget(box)
        return val_lbl

    def update_run(self, run) -> None:
        if run is None:
            return
        act_names = {1: "第一幕 · 边境突破", 2: "第二幕 · 纵深推进", 3: "第三幕 · 敌国腹地"}
        self.lbl_act.setText(act_names.get(int(run.act), f"第 {run.act} 幕"))
        try:
            from core import run as run_mod
            par = run_mod.ascension_params(int(run.ascension))
            self.lbl_diff.setText(f"战役难度 {run.ascension} · {par.get('name','')}")
        except Exception:
            self.lbl_diff.setText(f"战役难度 {run.ascension}")
        seed = getattr(run, "seed", 0)
        daily = " · 每日种子" if getattr(run, "daily", False) else ""
        self.lbl_seed.setText(f"种子 {seed}{daily}")
        self.lbl_floor.setText(f"{run.floor} 层")
        hp_ratio = float(run.hp) / max(1, float(run.max_hp))
        self.lbl_hp.setText(f"{run.hp}/{run.max_hp}")
        self.lbl_hp.setStyleSheet(
            f"color:{T.RED if hp_ratio < 0.3 else (T.GOLD if hp_ratio < 0.6 else T.TEXT)};"
            f"font-size:{T.FONT_BODY}px; font-weight:700;")
        self.lbl_gold.setText(str(run.gold))
        self.lbl_relic.setText(str(len(run.relics)))


# =====================================================================
# 地图界面
# =====================================================================


class MapScreen(QWidget):
    """战区推进图界面。"""

    node_selected = pyqtSignal(int)      # node_id
    open_deck = pyqtSignal()
    open_codex = pyqtSignal()
    save_and_quit = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.run = None
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(9)

        self.hud = MapHUD(self)
        root.addWidget(self.hud, 0)

        self.canvas = MapCanvas(self)
        self.canvas.node_chosen.connect(self._on_node)

        holder = QFrame(self)
        holder.setObjectName("Panel")
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.canvas)
        root.addWidget(holder, 1)

        bar = QHBoxLayout()
        bar.setSpacing(9)
        self.hint = QLabel("点击发光的节点推进战线", self)
        self.hint.setStyleSheet(f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;")
        bar.addWidget(self.hint)
        bar.addStretch(1)
        self.btn_deck = QPushButton("牌组", self)
        self.btn_deck.clicked.connect(self.open_deck.emit)
        bar.addWidget(self.btn_deck)
        self.btn_codex = QPushButton("图鉴", self)
        self.btn_codex.clicked.connect(self.open_codex.emit)
        bar.addWidget(self.btn_codex)
        self.btn_quit = QPushButton("保存并退出", self)
        self.btn_quit.setObjectName("Ghost")
        self.btn_quit.clicked.connect(self.save_and_quit.emit)
        bar.addWidget(self.btn_quit)
        root.addLayout(bar)

    def set_run(self, run) -> None:
        self.run = run
        self.hud.update_run(run)
        self.canvas.set_run(run)

    def refresh(self) -> None:
        if self.run:
            self.hud.update_run(self.run)
        self.canvas.refresh()

    def _on_node(self, nid: int) -> None:
        self.node_selected.emit(int(nid))
