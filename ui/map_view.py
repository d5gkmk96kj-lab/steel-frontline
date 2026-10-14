"""钢铁战线 —— 战区推进图（爬塔式分支地图）。

* 分层（row）× 分列（col）的节点图，连线用**三次贝塞尔**平滑曲线。
* 节点按 ``kind`` 程序化绘制不同图标：战斗 / 精英 / 事件 / 商店 / 休息 / 宝箱 / BOSS。
* **可达节点发光脉冲**，已走路径高亮，不可达节点灰暗。
* 悬停节点 250ms 显示 tooltip（名称 + 说明 + 可达性）。
* 顶部 HUD：战线层数、军费、总部 HP、勋章、补给品、战役难度。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from . import art as A
from . import theme as T

BG_DEEP = getattr(T, "BG_DEEP", "#0A1420")
PANEL = getattr(T, "PANEL", "#12233A")
BORDER = getattr(T, "BORDER", "#1E3A5F")
BORDER_HI = getattr(T, "BORDER_HI", "#2E5580")
CYAN = getattr(T, "CYAN", "#6B7F3A")
RUST = getattr(T, "RUST", "#8B5A2B")
GOLD = getattr(T, "GOLD", "#F2C14E")
BLOOD = getattr(T, "BLOOD", "#E5484D")
TEXT = getattr(T, "TEXT", "#E6EEF6")
TEXT_DIM = getattr(T, "TEXT_DIM", "#9AB0C6")
TEXT_FAINT = getattr(T, "TEXT_FAINT", "#5D7691")
POISON = getattr(T, "POISON", "#7BC950")
BLOCK_BLUE = getattr(T, "BLOCK_BLUE", "#7FB4E8")
NODE_COLORS = getattr(T, "NODE_COLORS", {
    "battle": "#E5484D", "elite": "#E58A4D", "event": "#B07BE8",
    "shop": "#F2C14E", "rest": "#7BC950", "treasure": "#3FD8D0",
    "boss": "#E5484D"})

KIND_NAMES = {
    "battle": "遭遇战", "elite": "精锐部队", "event": "战场事件",
    "shop": "补给站", "rest": "战地医院", "treasure": "缴获物资",
    "boss": "要塞", "start": "起点",
}
KIND_DESC = {
    "battle": "与敌方巡逻队交战，胜利后获得军费与手令奖励。",
    "elite": "精锐部队：装备精良、火力凶猛，必掉勋章。",
    "event": "战场事件：可能是机遇，也可能是陷阱。",
    "shop": "补给站：购买手令、勋章、补给品，也可花军费精简牌组。",
    "rest": "战地医院：修复总部 HP，或升级一张手令。",
    "treasure": "缴获物资：免费的战利品。",
    "boss": "敌军要塞：攻陷后推进到下一战区。",
    "start": "你的出发阵地。",
}


def _hex(c: str) -> Tuple[int, int, int]:
    try:
        return T.hex_to_rgb(c)
    except Exception:
        c = (c or "#000000").lstrip("#")
        try:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        except Exception:
            return (0, 0, 0)


def _to_hex(rgb) -> str:
    try:
        return T.rgb_to_hex(rgb)
    except Exception:
        r, g, b = rgb
        return "#%02x%02x%02x" % (max(0, min(255, int(r))),
                                  max(0, min(255, int(g))),
                                  max(0, min(255, int(b))))


def _lerp(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    r1, g1, b1 = _hex(c1)
    r2, g2, b2 = _hex(c2)
    return _to_hex((r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t))


def _alpha_on(bg: str, fg: str, a: float) -> str:
    try:
        return T.with_alpha_on(bg, fg, a)
    except Exception:
        return _lerp(bg, fg, a)


def _shade(c: str, amt: float) -> str:
    try:
        return T.shade(c, amt)
    except Exception:
        return _lerp(c, "#ffffff" if amt > 0 else "#000000", abs(amt))


def bezier(p0, p1, p2, p3, steps=18) -> List[float]:
    """三次贝塞尔采样，返回扁平坐标列表（供 create_line smooth 使用）。"""
    pts: List[float] = []
    for i in range(steps + 1):
        t = i / float(steps)
        mt = 1 - t
        x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + \
            3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + \
            3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        pts.extend((x, y))
    return pts


class MapView:
    """地图界面渲染器。"""

    wants_bg = False

    def __init__(self, app) -> None:
        self.app = app
        self.c = app.canvas
        self.w, self.h = app.W, app.H
        self.kwargs: Dict[str, Any] = {}
        self.nodes: List[Any] = []
        self.pos: Dict[Any, Tuple[float, float]] = {}
        self.reachable: set = set()
        self.hover_id: Optional[Any] = None
        self.hover_btn: Optional[str] = None
        self.shake = (0.0, 0.0)
        self.anim = 0.0
        self._btns: Dict[str, Tuple[float, float, float, float]] = {}
        self._enter_page = 0.0
        self._bind()
        self._load()

    # ------------------------------------------------------------------ 数据
    def _load(self) -> None:
        run = self.app.run
        nodes = list(getattr(run, "map_nodes", None) or []) if run else []
        self.nodes = nodes
        reach_fn = getattr(run, "reachable_nodes", None) if run else None
        rs = []
        if callable(reach_fn):
            try:
                rs = list(reach_fn() or [])
            except Exception:
                rs = []
        self.reachable = set()
        for n in rs:
            self.reachable.add(_nid(n))
        if not self.reachable and nodes:
            # 退化：没有 current_node 时，把第一层当作可达
            cur = getattr(run, "current_node", None) if run else None
            if cur is None:
                first_row = min((int(getattr(n, "row", 0) or 0) for n in nodes),
                                default=0)
                for n in nodes:
                    if int(getattr(n, "row", 0) or 0) == first_row:
                        self.reachable.add(_nid(n))

    def _reload(self) -> None:
        self._load()
        self._compute_layout()

    # ------------------------------------------------------------------ 生命周期
    def build(self, kwargs: Dict[str, Any]) -> None:
        self.kwargs = dict(kwargs or {})
        self.w, self.h = self.app.W, self.app.H
        self._reload()
        self._enter_page = 0.0
        self.app.every("map_anim", 40, self._anim_step)

    def on_destroy(self) -> None:
        self.app.cancel("map_anim")
        self.app.cancel("map_tip")
        self.app._hide_tooltip()

    def on_resize(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self._compute_layout()

    def set_shake(self, dx: float, dy: float) -> None:
        self.shake = (dx, dy)

    def _anim_step(self) -> None:
        self.anim += 0.05
        if self._enter_page < 1.0:
            self._enter_page = min(1.0, self._enter_page + 0.05)
        self.app.redraw()

    # ------------------------------------------------------------------ 布局
    def _compute_layout(self) -> None:
        self.pos = {}
        if not self.nodes:
            return
        top, bottom = self.h * 0.13, self.h * 0.93
        rows = [int(getattr(n, "row", 0) or 0) for n in self.nodes]
        minr, maxr = min(rows), max(rows)
        span = max(1, maxr - minr)
        # 节点在图上的显示顺序：row 大 = 更靠上（爬塔向上）
        by_row: Dict[int, List[Any]] = {}
        for n in self.nodes:
            by_row.setdefault(int(getattr(n, "row", 0) or 0), []).append(n)
        for r, group in by_row.items():
            group.sort(key=lambda n: int(getattr(n, "col", 0) or 0))
            y = bottom - (bottom - top) * ((r - minr) / float(span))
            n_cols = max(1, len(group))
            x0 = self.w * 0.16
            x1 = self.w * 0.84
            for i, n in enumerate(group):
                x = (x0 + x1) / 2 if n_cols == 1 else x0 + (x1 - x0) * i / (n_cols - 1)
                # 轻微错位，避免过于对齐
                x += math.sin(r * 1.7 + i * 2.3) * 10
                self.pos[_nid(n)] = (x, y)

    # ------------------------------------------------------------------ 输入
    def _bind(self) -> None:
        c = self.c
        c.bind("<Motion>", self._on_motion)
        c.bind("<Button-1>", self._on_click)
        c.bind("<Leave>", lambda e: self._clear())

    def _clear(self) -> None:
        self.hover_id = None
        self.hover_btn = None
        self.app._hide_tooltip()

    def _node_at(self, x: float, y: float):
        for n in reversed(self.nodes):
            p = self.pos.get(_nid(n))
            if not p:
                continue
            r = self._node_r(n)
            if (x - p[0]) ** 2 + (y - p[1]) ** 2 <= r * r:
                return n
        return None

    def _node_r(self, n) -> float:
        return 28.0 if str(getattr(n, "kind", "")) != "boss" else 38.0

    def _on_motion(self, event) -> None:
        x, y = event.x - self.shake[0], event.y - self.shake[1]
        prev = self.hover_id
        prev_btn = self.hover_btn
        self.hover_id = self._node_at(x, y)
        self.hover_btn = None
        for k, (x1, y1, x2, y2) in self._btns.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.hover_btn = k
                break
        if prev != self.hover_id or prev_btn != self.hover_btn:
            self.app._hide_tooltip()
        if self.hover_id is not None:
            n = self.hover_id
            self.app.cancel("map_tip")
            self.app._jobs["map_tip"] = self.app.after(
                250, lambda nd=n: self._tip_node(nd))
        elif self.hover_btn:
            k = self.hover_btn
            self.app.cancel("map_tip")
            self.app._jobs["map_tip"] = self.app.after(
                150, lambda kk=k: self._tip_btn(kk))

    def _tip_btn(self, key: str) -> None:
        info = self._btn_info(key)
        if not info:
            return
        x1, y1, x2, y2 = self._btns[key]
        self.app.show_tooltip(info[2], x1 - 60, y2, title=info[0],
                              color=info[1], width=280)

    def _btn_info(self, key: str):
        run = self.app.run
        deck = list(getattr(run, "deck", None) or []) if run else []
        relics = list(getattr(run, "relics", None) or []) if run else []
        if key == "deck":
            return ("手令 %d 张" % len(deck), CYAN, "查看并整理你的作战手令。")
        if key == "relics":
            return ("勋章 %d 枚" % len(relics), GOLD, "查看已获得的勋章与装备。")
        if key == "menu":
            return ("主菜单", TEXT_DIM, "返回主菜单（当前战役进度已保存）。")
        return None

    def _tip_node(self, n) -> None:
        kind = str(getattr(n, "kind", "battle"))
        nid = _nid(n)
        p = self.pos.get(nid)
        if not p:
            return
        col = NODE_COLORS.get(kind, TEXT_DIM) if isinstance(NODE_COLORS, dict) \
            else TEXT_DIM
        state = "可推进 · 点击进入" if nid in self.reachable else (
            "已通过" if getattr(n, "visited", False) else "不可达")
        body = "%s\n状态：%s" % (KIND_DESC.get(kind, ""), state)
        self.app.show_tooltip(body, p[0] - 140, p[1],
                              title="%s（第 %s 层）" % (
                                  KIND_NAMES.get(kind, kind),
                                  int(getattr(n, "row", 0) or 0) + 1),
                              color=col, width=290)

    def _on_click(self, event) -> None:
        x, y = event.x - self.shake[0], event.y - self.shake[1]
        for k, (x1, y1, x2, y2) in self._btns.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._click_btn(k)
                return
        n = self._node_at(x, y)
        if n is None:
            return
        if _nid(n) not in self.reachable:
            self.app.pop_text(x, y - 30, "不可达", color=TEXT_FAINT, size=18)
            self.app.shake(5, 160)
            return
        self._enter(n)

    def _click_btn(self, key: str) -> None:
        if key == "deck":
            self.app.show("deck", context="map")
        elif key == "relics":
            self.app.show("deck", tab="relics", context="map")
        elif key == "menu":
            self.app.show("menu")

    def _enter(self, n) -> None:
        run = self.app.run
        if run is None:
            return
        info = {}
        fn = getattr(run, "move_to", None)
        if callable(fn):
            try:
                info = fn(_nid(n)) or {}
            except Exception:
                info = {}
        self.app.cancel("map_anim")
        kind = str(info.get("kind") or getattr(n, "kind", "battle"))

        def go():
            if kind in ("battle", "elite", "boss"):
                enc = info.get("encounter") or {"kind": kind,
                                                "enemies": ["squid_scout"]}
                ok = self.app.start_battle(enc)
                self.app.show("battle")
                if not ok:
                    self.app.pop_text(self.w / 2, self.h / 2, "战斗引擎未就绪",
                                      color=BLOOD, size=24)
            elif kind == "shop":
                self.app.show("shop")
            elif kind == "rest":
                self.app.show("rest")
            elif kind == "treasure":
                self.app.show("treasure")
            elif kind == "event":
                self.app.show("event")
            else:
                self.app.show("battle")

        go()

    # ------------------------------------------------------------------ 绘制
    def draw(self) -> None:
        c = self.c
        c.delete("all")
        sx, sy = self.shake
        self._draw_bg()
        if not self.nodes:
            self._empty()
            self._draw_hud(sx, sy)
            return
        self._draw_edges(sx, sy)
        self._draw_nodes(sx, sy)
        self._draw_hud(sx, sy)
        self.app.draw_damage_numbers("dmg")

    def _draw_bg(self) -> None:
        """战区地图桌面：泛黄作战地图 + 硝烟 + 远景废墟 + 探照灯。"""
        w, h = self.w, self.h
        A.battlefield(self.c, w, h, "mapbg", horizon=0.34, smoke_layer=False)
        # 作战地图底衬（军绿羊皮纸质感）
        self.app.round_rect(28, 96, w - 28, h - 46, 10,
                            fill=_alpha_on(BG_DEEP, "#2C2A20", 0.55),
                            outline=_alpha_on(BG_DEEP, RUST, 0.45), width=2)
        # 经纬网格
        for i in range(1, 10):
            gx = 28 + (w - 56) * i / 10.0
            self.c.create_line(gx, 96, gx, h - 46,
                               fill=_alpha_on(BG_DEEP, TEXT_FAINT, 0.10))
        for i in range(1, 9):
            gy = 96 + (h - 142) * i / 9.0
            self.c.create_line(28, gy, w - 28, gy,
                               fill=_alpha_on(BG_DEEP, TEXT_FAINT, 0.10))
        # 硝烟粒子
        t = self.app._tick
        for sp in self.app._bg_sprites:
            wob = math.sin(math.radians((t * 2 + sp["phase"]) % 360))
            bx, by, r = sp["x"] + wob * 4, sp["y"], sp["r"] * 1.2
            A.draw_smoke_cloud(self.c, bx, by, r, "#4A4238", "mapbg")
        # 前景工事剪影
        A.barbed_wire(self.c, -20, h - 30, w * 0.3, h - 20, "mapbg", posts=4)
        A.barbed_wire(self.c, w * 0.7, h - 20, w + 20, h - 30, "mapbg", posts=4)

    def _empty(self) -> None:
        self.app.text_shadow(self.w / 2, self.h / 2 - 20, "暂无战区数据",
                             font=T.FONT_TITLE, fill=TEXT_DIM)
        self.app.text_shadow(self.w / 2, self.h / 2 + 30,
                             "请从主菜单「开始战役」创建新的作战",
                             font=T.FONT_BODY, fill=TEXT_FAINT)

    # ---------------------------------------------------------------- 连线
    def _draw_edges(self, sx: float, sy: float) -> None:
        for n in self.nodes:
            a = self.pos.get(_nid(n))
            if not a:
                continue
            for eid in (getattr(n, "edges", None) or []):
                b = self.pos.get(eid)
                if not b:
                    continue
                target = self._by_id(eid)
                passed = bool(getattr(n, "visited", False)) and \
                    bool(getattr(target, "visited", False)) if target else False
                on_path = passed
                glow = (_nid(n) in self.reachable) and (
                    eid in self.reachable)
                reach_edge = _nid(n) in self.reachable
                if on_path:
                    col = GOLD
                    width = 4
                elif reach_edge:
                    col = CYAN
                    width = 3
                else:
                    col = "#1B2E3E"
                    width = 2
                ax, ay = a[0] + sx, a[1] + sy
                bx, by = b[0] + sx, b[1] + sy
                mid = (ay + by) / 2.0
                pts = bezier((ax, ay), (ax, mid), (bx, mid), (bx, by), 16)
                self.c.create_line(pts, fill=col, width=width, smooth=True,
                                   capstyle="round")
                if reach_edge:
                    dash = _alpha_on(BG_DEEP, CYAN, 0.55)
                    self.c.create_line(pts, fill=dash, width=1, smooth=True,
                                       dash=(6, 8))
                if on_path:
                    # 路径上的流动光点
                    ph = (self.app._tick * 0.02) % 1.0
                    i = int(ph * (len(pts) - 2) / 2) * 2
                    self.c.create_oval(pts[i] - 4, pts[i + 1] - 4,
                                       pts[i] + 4, pts[i + 1] + 4,
                                       fill=GOLD, outline="")

    def _by_id(self, nid):
        for n in self.nodes:
            if _nid(n) == nid:
                return n
        return None

    # ---------------------------------------------------------------- 节点
    def _draw_nodes(self, sx: float, sy: float) -> None:
        for n in self.nodes:
            p = self.pos.get(_nid(n))
            if not p:
                continue
            self._draw_node(n, p[0] + sx, p[1] + sy)

    def _draw_node(self, n, x: float, y: float) -> None:
        c = self.c
        kind = str(getattr(n, "kind", "battle"))
        nid = _nid(n)
        visited = bool(getattr(n, "visited", False))
        reachable = nid in self.reachable
        hover = (self.hover_id is not None and _nid(self.hover_id) == nid)
        base = NODE_COLORS.get(kind, TEXT_DIM) if isinstance(NODE_COLORS, dict) \
            else TEXT_DIM
        r = self._node_r(n)

        if reachable:
            col = base
        elif visited:
            col = _alpha_on(BG_DEEP, GOLD, 0.85)
        else:
            col = _alpha_on(BG_DEEP, base, 0.28)

        # 可达发光脉冲
        if reachable:
            pulse = 0.5 + 0.5 * math.sin(self.anim * 2.2 + x * 0.01)
            for i in range(3):
                rr = r + 8 + i * 9 + pulse * 8
                a = 0.20 * (1 - i / 3.0) * (0.6 + 0.4 * pulse)
                c.create_oval(x - rr, y - rr, x + rr, y + rr, fill="",
                              outline=_alpha_on(BG_DEEP, base, a), width=2)
        # 底盘
        c.create_oval(x - r, y - r, x + r, y + r,
                      fill=_alpha_on(BG_DEEP, PANEL, 0.94),
                      outline=col, width=3 if (reachable or hover) else 2)
        if visited and not reachable:
            c.create_oval(x - r + 5, y - r + 5, x + r - 5, y + r - 5,
                          fill="", outline=_alpha_on(BG_DEEP, GOLD, 0.5),
                          width=1)
        # 图标
        self._node_icon(x, y, r * 0.58, kind, col)
        # BOSS 皇冠
        if kind == "boss":
            # 铁十字标识
            for a in (0, 90):
                rad = math.radians(a)
                c.create_line(x - math.cos(rad) * 13, y - r - 16 +
                              math.sin(rad) * 13,
                              x + math.cos(rad) * 13, y - r - 16 -
                              math.sin(rad) * 13, fill=GOLD, width=5,
                              capstyle="round")
        # 悬停高亮
        if hover:
            c.create_oval(x - r - 6, y - r - 6, x + r + 6, y + r + 6, fill="",
                          outline=TEXT, width=2)
        # 已完成打勾
        if visited:
            c.create_line(x + r * 0.45, y + r * 0.45, x + r * 0.7, y + r * 0.75,
                          x + r * 1.1, y - r * 0.1, fill="#5FD07A", width=4,
                          capstyle="round", smooth=True)

    def _node_icon(self, x: float, y: float, r: float, kind: str, col: str) -> None:
        """北约军标风格的战术符号。"""
        c = self.c
        if kind == "battle":
            # 交叉刺刀（遭遇战）
            c.create_line(x - r, y + r, x + r, y - r, fill=col, width=5,
                          capstyle="round")
            c.create_line(x - r * 0.6, y - r * 0.7, x + r * 0.2, y + r * 0.1,
                          fill=col, width=8, capstyle="round")
            c.create_line(x - r, y - r * 0.9, x - r * 0.35, y - r * 0.3,
                          fill=col, width=4, capstyle="round")
        elif kind == "elite":
            # 双剑 + 星
            for sgn in (-1, 1):
                c.create_line(x + sgn * r * 0.85, y - r, x - sgn * r * 0.35,
                              y + r, fill=col, width=5, capstyle="round")
            A.star(c, x, y, r * 0.34, BG_DEEP, "mapn")
        elif kind == "event":
            c.create_text(x, y, text="!", font=T.FONT_H1, fill=col)
        elif kind == "shop":
            # 补给箱
            A.icon_supply(c, x, y, r * 0.85, col, "mapn")
        elif kind == "rest":
            # 医疗十字
            c.create_rectangle(x - r * 0.28, y - r, x + r * 0.28, y + r,
                               fill=col, outline="")
            c.create_rectangle(x - r, y - r * 0.28, x + r, y + r * 0.28,
                               fill=col, outline="")
        elif kind == "treasure":
            # 弹药箱 / 缴获物资
            A.icon_supply(c, x, y, r * 0.95, col, "mapn")
            c.create_line(x - r * 0.95, y - r * 0.72, x + r * 0.95,
                          y - r * 0.72, fill=GOLD, width=2)
        elif kind == "boss":
            # 要塞棱堡
            A.enemy_fortress(c, x, y, r * 0.95, col, "mapn")
        else:
            c.create_oval(x - r * 0.7, y - r * 0.7, x + r * 0.7, y + r * 0.7,
                          fill=col, outline="")

    # ---------------------------------------------------------------- HUD
    def _draw_hud(self, sx: float, sy: float) -> None:
        run = self.app.run
        w, h = self.w, self.h
        # 顶部条
        self.app.round_rect(16, 14, w - 16, 76, 14,
                            fill=_alpha_on(BG_DEEP, PANEL, 0.72),
                            outline=BORDER, width=1)
        act = int(getattr(run, "act", 1) or 1) if run else 1
        floor = int(getattr(run, "floor", 0) or 0) if run else 0
        self.app.text_shadow(40, 45, "第 %d 战区" % act, font=T.FONT_H1, fill=GOLD,
                             anchor="w")
        self.app.text_shadow(140, 48, "第 %d 日" % (floor + 1),
                             font=T.FONT_BODY, fill=TEXT_DIM, anchor="w")
        # 血量
        hp = int(getattr(run, "hp", 0) or 0) if run else 0
        maxhp = max(1, int(getattr(run, "max_hp", 1) or 1)) if run else 1
        ratio = max(0.0, min(1.0, hp / float(maxhp)))
        bx, by = 260, 34
        bw, bh = 200, 20
        self.app.round_rect(bx, by, bx + bw, by + bh, bh / 2, fill="#071019",
                            outline=BORDER, width=1)
        if ratio > 0:
            col = BLOOD if ratio > 0.3 else "#FF7A45"
            self.app.round_rect(bx + 1, by + 1, bx + 1 + (bw - 2) * ratio,
                                by + bh - 1, (bh - 2) / 2, fill=col, outline="")
        self.app.text_shadow(bx + bw / 2, by + bh / 2, "%d/%d" % (hp, maxhp),
                             font=T.FONT_TINY, fill="#FFFFFF")
        # 金币
        gold = int(getattr(run, "gold", 0) or 0) if run else 0
        self.c.create_oval(490, 34, 518, 62, fill=GOLD, outline=_shade(GOLD, -0.35),
                           width=2)
        self.app.text_shadow(504, 48, "¥", font=T.FONT_SMALL, fill="#3A2600")
        self.app.text_shadow(526, 48, str(gold), font=T.FONT_H2, fill=GOLD,
                             anchor="w")
        # 药水
        potions = list(getattr(run, "potions", None) or []) if run else []
        px = 600
        for i in range(3):
            x = px + i * 34
            filled = i < len(potions)
            self.c.create_oval(x, 34, x + 26, 62,
                               fill=_alpha_on(BG_DEEP, POISON, 0.8) if filled
                               else _alpha_on(BG_DEEP, PANEL, 0.8),
                               outline=BORDER_HI if filled else BORDER, width=2)
            if filled:
                self.c.create_rectangle(x + 10, 26, x + 16, 36,
                                        fill=BORDER_HI, outline="")
        # 难度
        asc = int(getattr(run, "ascension", 0) or 0) if run else 0
        show_diff = self.app.settings.get("show_difficulty", True)
        if show_diff:
            self.app.text_shadow(w - 300, 46, "战役难度 %d" % asc, font=T.FONT_H2,
                                 fill=_shade(GOLD, -0.1) if asc else TEXT_DIM,
                                 anchor="w")
        # 按钮
        self._btns = {}
        self._button(w - 264, 28, 132, 34, "手令", "deck", CYAN, sx, sy)
        self._button(w - 124, 28, 46, 34, "勋章", "relics", GOLD, sx, sy)
        self._button(w - 70, 28, 54, 34, "菜单", "menu", TEXT_DIM, sx, sy)
        # 底部提示
        self.app.text_shadow(w / 2, h - 26,
                             "点击发光的可推进节点前进 · 悬停查看详情",
                             font=T.FONT_SMALL, fill=TEXT_FAINT)

    def _button(self, x: float, y: float, bw: float, bh: float, label: str,
                key: str, col: str, sx: float, sy: float) -> None:
        x1, y1 = x + sx, y + sy
        x2, y2 = x1 + bw, y1 + bh
        hot = (self.hover_btn == key)
        self.app.round_rect(x1, y1, x2, y2, 9,
                            fill=_alpha_on(BG_DEEP, PANEL,
                                           0.95 if hot else 0.7),
                            outline=_shade(col, 0.12 if hot else -0.25),
                            width=2 if hot else 1)
        self.app.text_shadow((x1 + x2) / 2, (y1 + y2) / 2, label,
                             font=T.FONT_BUTTON if False else T.FONT_BODY,
                             fill=TEXT if hot else col)
        self._btns[key] = (x1, y1, x2, y2)


def _nid(n) -> Any:
    v = getattr(n, "id", None)
    if v is None:
        v = getattr(n, "uid", None)
    if v is None:
        v = id(n)
    try:
        return int(v)
    except Exception:
        return v
