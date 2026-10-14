"""钢铁战线 —— 全部非战斗界面。

包含：主菜单 / 牌组查看 / 卡牌奖励 / 商店 / 休息 / 事件 / 宝箱 /
结算 / 图鉴 / 成就 / 统计 / 设置，以及一个通用占位界面。

设计约定
--------
* 每个界面是一个 ``View`` 类：``__init__(app)`` / ``build(kwargs)`` / ``draw()``
  / 可选 ``on_resize(w,h)`` / ``on_destroy()``。
* 界面内部**只读 run 的公开属性**，只调 run 的公开方法。
* 全部动效走 ``app.after()``；本文件不含 ``time.sleep``。
* 数据为空（无牌组 / 无遗物 / core 缺失）时必须正常渲染。
"""

from __future__ import annotations

import math
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import art as A
from . import theme as T

try:  # widgets 由 ui-theme 提供；缺失时全部走内置绘制
    from . import widgets as W
except Exception:  # pragma: no cover
    W = None

BG_DEEP = getattr(T, "BG_DEEP", "#0A1420")
BG = getattr(T, "BG", "#0D1A28")
PANEL = getattr(T, "PANEL", "#12233A")
PANEL_HI = getattr(T, "PANEL_HI", "#1B3554")
PANEL_LO = getattr(T, "PANEL_LO", "#0B1725")
BORDER = getattr(T, "BORDER", "#1E3A5F")
BORDER_HI = getattr(T, "BORDER_HI", "#2E5580")
CYAN = getattr(T, "CYAN", "#3FD8D0")
GOLD = getattr(T, "GOLD", "#F2C14E")
BLOOD = getattr(T, "BLOOD", "#A8322D")
TEXT = getattr(T, "TEXT", "#E6EEF6")
TEXT_DIM = getattr(T, "TEXT_DIM", "#9AB0C6")
TEXT_FAINT = getattr(T, "TEXT_FAINT", "#5D7691")
POISON = getattr(T, "POISON", "#7BC950")
RUST = getattr(T, "RUST", "#8B5A2B")
SMOKE = getattr(T, "SMOKE", "#3A3630")
OLIVE = getattr(T, "OLIVE", getattr(T, "CYAN", "#6B7F3A"))
BLOCK_BLUE = getattr(T, "BLOCK_BLUE", "#7FB4E8")
RED = getattr(T, "RED", BLOOD)
GREEN = getattr(T, "GREEN", POISON)

ACHIEVEMENTS: Dict[str, dict] = {}
try:
    from core.run import ACHIEVEMENTS as _ACH  # type: ignore
    ACHIEVEMENTS = _ACH
except Exception:
    ACHIEVEMENTS = {}


def _hex(c: str) -> Tuple[int, int, int]:
    try:
        return T.hex_to_rgb(c)
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


def _rarity_color(r: str) -> str:
    try:
        return str(T.rarity_color(r))
    except Exception:
        return "#C7D6E4"


def _g(obj, name, default=None):
    try:
        v = getattr(obj, name)
    except Exception:
        return default
    return default if v is None else v


# --------------------------------------------------------------------------- #
# 视图基类
# --------------------------------------------------------------------------- #
class View:
    """所有界面的基类：提供背景、按钮、tooltip、飘字等通用能力。"""

    wants_bg = True

    def __init__(self, app) -> None:
        self.app = app
        self.c = app.canvas
        self.w, self.h = app.W, app.H
        self.kwargs: Dict[str, Any] = {}
        self.shake = (0.0, 0.0)
        self.anim = 0.0
        self.hover: Optional[str] = None
        self._btns: List[dict] = []
        self._bind()

    # -- 生命周期 --------------------------------------------------------- #
    def build(self, kwargs: Dict[str, Any]) -> None:
        self.kwargs = dict(kwargs or {})
        self.w, self.h = self.app.W, self.app.H
        self.on_build()
        self.app.every("view_anim", 40, self._tick)

    def on_build(self) -> None:
        pass

    def on_destroy(self) -> None:
        self.app.cancel("view_anim")
        self.app.cancel("view_tip")
        self.app._hide_tooltip()

    def on_resize(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.layout()

    def layout(self) -> None:
        pass

    def _tick(self) -> None:
        self.anim += 0.05
        self.app.redraw()

    def set_shake(self, dx: float, dy: float) -> None:
        self.shake = (dx, dy)

    # -- 输入 ------------------------------------------------------------- #
    def _bind(self) -> None:
        self.c.bind("<Motion>", self.on_motion)
        self.c.bind("<Button-1>", self.on_click)
        self.c.bind("<Leave>", lambda e: self.clear_hover())

    def clear_hover(self) -> None:
        self.hover = None
        self.app._hide_tooltip()

    def on_motion(self, event) -> None:
        x, y = event.x - self.shake[0], event.y - self.shake[1]
        prev = self.hover
        self.hover = None
        for b in self._btns:
            x1, y1, x2, y2 = b["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.hover = b["key"]
                break
        if self.hover != prev:
            self.app._hide_tooltip()
        if self.hover:
            b = self.btn(self.hover)
            if b and b.get("tip"):
                key = self.hover
                self.app.cancel("view_tip")
                self.app._jobs["view_tip"] = self.app.after(
                    250, lambda k=key: self._tip_for(k))
        else:
            self.on_motion_extra(x, y, prev)

    def on_motion_extra(self, x: float, y: float, prev) -> None:
        pass

    def _tip_for(self, key: str) -> None:
        b = self.btn(key)
        if not b:
            return
        x1, y1, x2, y2 = b["rect"]
        self.app.show_tooltip(b["tip"], x1 - 40, y2,
                              title=b.get("tip_title", ""),
                              color=b.get("color", CYAN), width=290)

    def on_click(self, event) -> None:
        x, y = event.x - self.shake[0], event.y - self.shake[1]
        for b in self._btns:
            x1, y1, x2, y2 = b["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                if b.get("enabled", True):
                    self.app.flash(_alpha_on(BG_DEEP, b.get("color", CYAN), 0.08),
                                   90)
                    try:
                        b["cmd"]()
                    except Exception:
                        import traceback
                        traceback.print_exc()
                else:
                    self.app.pop_text((x1 + x2) / 2, y1 - 16, "不可用",
                                      color=TEXT_FAINT, size=16)
                return
        self.on_click_extra(x, y)

    def on_click_extra(self, x: float, y: float) -> None:
        pass

    # -- 小工具 ----------------------------------------------------------- #
    def btn(self, key: str) -> Optional[dict]:
        for b in self._btns:
            if b["key"] == key:
                return b
        return None

    def add_btn(self, key: str, rect, label: str, cmd: Callable,
                color: str = CYAN, enabled: bool = True, tip: str = "",
                tip_title: str = "", font=None, radius: int = 12,
                style: str = "solid", sub: str = "") -> None:
        self._btns.append({
            "key": key, "rect": tuple(rect), "label": label, "cmd": cmd,
            "color": color, "enabled": enabled, "tip": tip,
            "tip_title": tip_title, "font": font, "radius": radius,
            "style": style, "sub": sub,
        })

    def set_btn(self, key: str, **kw) -> None:
        b = self.btn(key)
        if b:
            b.update(kw)

    def draw_buttons(self) -> None:
        sx, sy = self.shake
        for b in self._btns:
            if b.get("hidden"):
                continue
            x1, y1, x2, y2 = b["rect"]
            x1, y1, x2, y2 = x1 + sx, y1 + sy, x2 + sx, y2 + sy
            hot = (self.hover == b["key"]) and b.get("enabled", True)
            col = b.get("color", CYAN)
            if not b.get("enabled", True):
                col = _alpha_on(BG_DEEP, TEXT_FAINT, 0.6)
                fill = _alpha_on(BG_DEEP, PANEL, 0.55)
            elif b.get("style") == "ghost":
                fill = _alpha_on(BG_DEEP, PANEL, 0.95 if hot else 0.6)
            else:
                fill = _alpha_on(BG_DEEP, _shade(col, -0.72),
                                 0.97 if hot else 0.85)
            if hot:
                self.app.round_rect(x1 - 3, y1 - 3, x2 + 3, y2 + 3,
                                    b.get("radius", 12) + 3, fill="",
                                    outline=_alpha_on(BG_DEEP, col, 0.45),
                                    width=2)
            self.app.round_rect(x1, y1, x2, y2, b.get("radius", 12), fill=fill,
                                outline=col, width=2)
            if b.get("enabled", True) and b.get("style") != "ghost":
                self.app.round_rect(x1 + 3, y1 + 3, x2 - 3, y1 + 7, 3,
                                    fill=_alpha_on(fill, col, 0.35), outline="")
            cy = (y1 + y2) / 2 - (8 if b.get("sub") else 0)
            self.app.text_shadow((x1 + x2) / 2, cy, b["label"],
                                 font=b.get("font") or T.FONT_BUTTON, fill=col)
            if b.get("sub"):
                self.app.text_shadow((x1 + x2) / 2, cy + 22, b["sub"],
                                     font=T.FONT_TINY, fill=TEXT_DIM)

    def draw_bg(self, top: str = "#3B3226", bottom: str = BG_DEEP) -> None:
        """默认背板：焦土战场 + 硝烟粒子。"""
        self.app.vgradient(0, 0, self.w, self.h, top, bottom, steps=44)
        t = self.app._tick
        for s in self.app._bg_sprites:
            wob = math.sin(math.radians((t * 2 + s["phase"]) % 360))
            bx, by, r = s["x"] + wob * 4, s["y"], s["r"] * 1.3
            col = _lerp(SMOKE, "#8A7F6B", 0.28)
            A.draw_smoke_cloud(self.c, bx, by, r, col, "bg")

    def title(self, text: str, y: float = 60, sub: str = "",
              color: str = GOLD) -> None:
        self.app.text_shadow(self.w / 2, y, text, font=T.FONT_TITLE,
                             fill=color)
        if sub:
            self.app.text_shadow(self.w / 2, y + 36, sub, font=T.FONT_BODY,
                                 fill=TEXT_DIM)
        self.c.create_line(self.w / 2 - 200, y + 52, self.w / 2 + 200, y + 52,
                           fill=_alpha_on(BG_DEEP, color, 0.4), width=2)

    def draw(self) -> None:
        self.c.delete("all")
        self.draw_bg()
        self.layout()
        self._btns = []
        self.body()
        self.draw_buttons()
        self.app.draw_damage_numbers("dmg")

    def body(self) -> None:
        pass

    # -- 数据 ------------------------------------------------------------- #
    @property
    def run(self):
        return self.app.run

    def deck(self) -> list:
        return list(_g(self.run, "deck", []) or [])

    def relics(self) -> list:
        return list(_g(self.run, "relics", []) or [])

    def back_to_map(self) -> None:
        self.app.show("map" if self.app.run is not None else "menu")

    def top_bar(self, show_back: bool = True, back_key: str = "back") -> None:
        """通用顶部栏：标题由子类画，这里只放返回按钮和资源。"""
        run = self.run
        y = 26
        if run is not None:
            hp = int(_g(run, "hp", 0))
            mx = max(1, int(_g(run, "max_hp", 1)))
            gold = int(_g(run, "gold", 0))
            txt = "❤ %d/%d    ¥ %d" % (hp, mx, gold)
            self.app.text_shadow(self.w - 30, y + 14, txt, font=T.FONT_H2,
                                 fill=TEXT, anchor="e")
        if show_back:
            self.add_btn(back_key, (24, y, 150, y + 44), "◀ 返回",
                         self.back_to_map, color=TEXT_DIM, style="ghost")


def placeholder_view(app, name: str):
    """任何界面渲染失败时的兜底界面。"""

    class _Placeholder(View):
        def body(self) -> None:
            self.draw_bg()
            self.app.text_shadow(self.w / 2, self.h / 2 - 30,
                                 "「%s」界面暂不可用" % name,
                                 font=T.FONT_TITLE, fill=TEXT_DIM)
            self.app.text_shadow(self.w / 2, self.h / 2 + 24,
                                 "该界面依赖的数据尚未就绪",
                                 font=T.FONT_BODY, fill=TEXT_FAINT)
            self.add_btn("menu", (self.w / 2 - 90, self.h / 2 + 70,
                                  self.w / 2 + 90, self.h / 2 + 122),
                         "返回主菜单", lambda: self.app.show("menu"))

    return _Placeholder(app)


# --------------------------------------------------------------------------- #
# 主菜单
# --------------------------------------------------------------------------- #
class MenuView(View):
    """大标题 + 动画坦克 + 开始战役/继续/图鉴/统计/设置。"""

    def on_build(self) -> None:
        self.unit_t = 0.0
        self.glow = 0.0

    def _tick(self) -> None:
        self.unit_t += 0.05
        self.glow += 0.03
        self.anim += 0.05
        self.app.redraw()

    def layout(self) -> None:
        self._btns_layout = True

    def body(self) -> None:
        w, h = self.w, self.h
        t = self.anim          # 帧计数器（原为未定义的裸 t）
        cx = w * 0.5           # 主菜单水平中心（原为未定义的裸 cx）
        # 背景：焦土战场 + 硝烟 + 探照灯
        A.battlefield(self.c, w, h, "menubg", horizon=0.62)
        A.horizon_glow(self.c, w, h, "menubg", t * 0.02)
        for i in range(3):
            x0 = w * (0.18 + 0.3 * i) + math.sin(math.radians(t * 0.5 + i * 70)) * 40
            col = _alpha_on(BG_DEEP, "#FFE7A8", 0.030)
            sway = math.sin(math.radians(t * 0.7 + i * 120)) * 110
            self.c.create_polygon(x0, h * 0.62, x0 + 14, h * 0.62,
                                  x0 + sway + 80, -10, x0 + sway - 80, -10,
                                  fill=col, outline="")
        for sp in self.app._bg_sprites:
            wob = math.sin(math.radians((t * 2 + sp["phase"]) % 360))
            bx, by, r = sp["x"] + wob * 6, sp["y"], sp["r"] * 1.7
            col = A.lerp(SMOKE, "#8A7F6B", 0.3)
            A.draw_smoke_cloud(self.c, bx, by, r, col, "menubg")
        A.barbed_wire(self.c, -20, h - 30, w * 0.28, h - 20, "menubg", posts=4)
        A.barbed_wire(self.c, w * 0.72, h - 20, w + 20, h - 30, "menubg", posts=4)

        # 动画主战坦克
        self._tank(w * 0.5, h * 0.50, t)

        # 底部版权
        _ver = ""
        try:
            from core import version as _V
            _ver = "  ·  v%s" % _V.VERSION_LABEL
        except Exception:
            pass
        self.app.text_shadow(cx, h - 22,
                             "纯 Python + Tkinter · 零依赖 · 🤖 全部由 AI 生成" + _ver,
                             font=T.FONT_TINY, fill=TEXT_FAINT)

        # 按钮
        bw, bh, gap = 260, 54, 14
        x1 = cx - bw / 2
        y = h * 0.665
        has_save = self._has_save()
        self.add_btn("new", (x1, y, x1 + bw, y + bh), "开始战役",
                     self._new_game, color=GOLD,
                     tip="开始一场新的装甲战役。\n战区推进图随机生成，通关后解锁更高战役难度。",
                     tip_title="新战役")
        asc = self._ascension()
        asc_name = self._asc_name(asc)
        self.add_btn("asc", (x1 + bw + 18, y, x1 + bw + 118, y + bh), "▲",
                     lambda: self._cycle_asc(1), color=CYAN,
                     tip="调高战役难度（Campaign Level）。\n最高档「神人模式」无法使用作弊。\n"
                         "也可以用键盘数字键 0-9 直接跳档。",
                     tip_title="战役难度 %d · %s" % (asc, asc_name))
        self.add_btn("asc_lbl", (x1 - 190, y, x1 - 118, y + bh),
                     "战役难度 %d" % asc, lambda: None, color=TEXT_DIM,
                     style="ghost", enabled=False)
        self.add_btn("asc_name", (x1 - 118, y, x1 - 18, y + bh),
                     asc_name, lambda: self._cycle_asc(1),
                     color=(BLOOD if asc >= self._asc_max() else TEXT_DIM),
                     style="ghost",
                     tip="点击可切换难度。\n当前：%s" % asc_name)
        self.add_btn("asc_dn", (x1 - 18, y, x1 + 22, y + bh), "▼",
                     lambda: self._cycle_asc(-1), color=CYAN,
                     tip="调低战役难度。")
        y += bh + gap
        self.add_btn("cont", (x1, y, x1 + bw, y + bh), "继续战役",
                     self._continue, color=CYAN, enabled=has_save,
                     tip="读取上一次的中断存档继续作战。" if has_save
                     else "没有可继续的存档。",
                     tip_title="继续")
        y += bh + gap
        half = (bw - 12) / 2
        self.add_btn("codex", (x1, y, x1 + half, y + bh), "图鉴",
                     lambda: self.app.show("codex"), color=CYAN)
        self.add_btn("stats", (x1 + half + 12, y, x1 + bw, y + bh), "统计",
                     lambda: self.app.show("stats"), color=POISON)
        y += bh + gap
        self.add_btn("ach", (x1, y, x1 + half, y + bh), "成就",
                     lambda: self.app.show("achievements"), color=GOLD)
        self.add_btn("set", (x1 + half + 12, y, x1 + bw, y + bh), "设置",
                     lambda: self.app.show("settings"), color=TEXT_DIM)
        y += bh + gap + 4
        self.add_btn("quit", (cx - 70, y, cx + 70, y + 40), "退出",
                     self.app.quit_game, color=BLOOD, style="ghost")

    def _tank(self, cx: float, cy: float, t: float) -> None:
        """主菜单的动画主战坦克（缓慢转向 + 履带滚动 + 炮口余烟）。"""
        s = min(self.w / 1440.0, self.h / 900.0) * 1.25
        cy += math.sin(self.unit_t) * 8
        # 阵地光晕
        halo = _alpha_on(BG_DEEP, OLIVE, 0.06)
        self.c.create_oval(cx - 260 * s, cy + 40 * s, cx + 260 * s,
                           cy + 180 * s, fill=halo, outline="")
        # 地面工事
        A.sandbags(self.c, cx - 40 * s, cy + 118 * s, 6, 1.1 * s, "mtank")
        A.hedgehog(self.c, cx - 250 * s, cy + 96 * s, 1.0 * s, "mtank")
        A.hedgehog(self.c, cx + 250 * s, cy + 96 * s, 1.0 * s, "mtank")
        # 坦克
        A.tank(self.c, cx, cy, 1.5 * s, col=OLIVE, facing=1, tag="mtank",
               turret_angle=math.sin(t * 0.02) * 10.0,
               tread_phase=self.unit_t * 1.6)
        # 旗
        px, py = cx + 118 * s, cy - 60 * s
        self.c.create_line(px, py, px, py - 70 * s, fill="#3A3428",
                           width=max(2, int(3 * s)), tags="mtank")
        wob = math.sin(self.unit_t * 1.6) * 5 * s
        self.c.create_polygon(px, py - 68 * s, px + 46 * s, py - 60 * s + wob,
                              px + 28 * s, py - 50 * s + wob * 0.5, px + 46 * s,
                              py - 40 * s + wob, px, py - 34 * s,
                              fill=BLOOD, outline="", tags="mtank")
        A.star(self.c, px + 20 * s, py - 52 * s, 9 * s, "#D8CFAF", "mtank")
        # 炮口余烟
        A.draw_smoke_cloud(self.c, cx + 150 * s, cy - 26 * s, 26 * s,
                           "#8A7F6B", "mtank")

    def _has_save(self) -> bool:
        try:
            from core.run import has_save  # type: ignore
            return bool(has_save())
        except Exception:
            return False

    def _ascension(self) -> int:
        if not hasattr(self, "_asc"):
            self._asc = 0
        return int(self._asc)

    def _asc_max(self) -> int:
        """可选的最大难度档位。

        旧版用 ``meta.ascension_unlocked`` 当上限，新档为 0 —— 于是 ▲ 永远
        算出 0，玩家根本调不了难度（也与此前「只有通关才能解锁」的设定不符，
        但用户明确要求能自由调）。现在**全部 20 档直接可选**。
        """
        try:
            from core.run import ASCENSION_TABLE  # type: ignore
            return max(0, len(ASCENSION_TABLE) - 1)
        except Exception:
            return 19

    def _asc_name(self, v: int) -> str:
        """难度档的显示名。最高档显示为「神人模式」。"""
        if v >= self._asc_max():
            return "神人模式"
        try:
            from core.run import ASCENSION_TABLE  # type: ignore
            row = ASCENSION_TABLE[v]
            if isinstance(row, dict):
                return str(row.get("name") or ("难度 %d" % v))
            return str(row)
        except Exception:
            return "难度 %d" % v

    def _is_god_mode(self) -> bool:
        """当前是否选中「神人模式」（最高难度，禁用一切作弊）。"""
        return self._ascension() >= self._asc_max()

    def _set_asc(self, v: int) -> None:
        self._asc = max(0, min(self._asc_max(), int(v)))
        self.app.redraw()

    def _cycle_asc(self, delta: int = 1) -> None:
        """按 delta 增减难度并**循环**（到顶回 0、到底回顶）。"""
        top = self._asc_max()
        self._set_asc((self._ascension() + delta) % (top + 1))

    def _asc_key(self, ch: str) -> bool:
        """键盘输入数字调难度：0-9 直接跳档。返回是否消费了该按键。"""
        if len(ch) == 1 and ch.isdigit():
            self._set_asc(int(ch))
            return True
        return False

    def on_key(self, event) -> None:
        """主菜单键盘操作：数字键跳难度、上下键微调。"""
        try:
            k = str(getattr(event, "keysym", "") or "")
            ch = str(getattr(event, "char", "") or "")
        except Exception:
            return
        if self._asc_key(ch):
            return
        if k in ("Up", "plus", "equal"):
            self._cycle_asc(1)
        elif k in ("Down", "minus"):
            self._cycle_asc(-1)

    def _new_game(self) -> None:
        daily = bool(self.kwargs.get("daily"))
        seed = None
        if daily:
            try:
                from core.run import daily_seed  # type: ignore
                seed = daily_seed()
            except Exception:
                seed = None
        ok = self.app.start_new_run(seed=seed, ascension=self._ascension())
        meta = self.app.meta_progress()
        if meta is not None and not daily:
            try:
                meta.total_runs = int(_g(meta, "total_runs", 0)) + 1
            except Exception:
                pass
        self.app.show("map")
        if not ok:
            self.app.pop_text(self.w / 2, self.h * 0.30,
                              "核心引擎尚未就绪，显示空地图",
                              color=BLOOD, size=20)

    def _continue(self) -> None:
        try:
            from core.run import load_run  # type: ignore
            run = load_run()
        except Exception:
            run = None
        if run is None:
            self.app.pop_text(self.w / 2, self.h * 0.86, "没有可用存档",
                              color=TEXT_FAINT, size=18)
            return
        self.app.run = run
        self.app.show("map")


# --------------------------------------------------------------------------- #
# 牌组查看
# --------------------------------------------------------------------------- #
class DeckView(View):
    """手令网格 + 排序；也可切到勋章 / 补给品分页。"""

    PAGES = ("cards", "relics", "potions")
    SORTS = (("type", "按类型"), ("cost", "按费用"), ("rarity", "按稀有度"),
             ("name", "按名称"), ("arch", "按流派"))

    def on_build(self) -> None:
        self.page = str(self.kwargs.get("tab") or "cards")
        if self.page not in self.PAGES:
            self.page = "cards"
        self.sort = "type"
        self.scroll = 0
        self.hover_card = None
        self.selected_uid = None
        self.cols = 8
        self.ro = self.kwargs.get("readonly", False)

    def layout(self) -> None:
        w, h = self.w, self.h
        grid_top = 150
        grid_bottom = h - 70
        rows = max(1, int((grid_bottom - grid_top) // (T.CARD_H * 0.52 + 18)))
        self.rows = rows
        self.grid_top, self.grid_bottom = grid_top, grid_bottom

    def body(self) -> None:
        self.title("作战手令", 52, "共 %d 张" % len(self.deck()))
        self.top_bar(back_key="back")
        # 分页
        x = 190
        for p, label in zip(self.PAGES, ("手令", "勋章", "补给品")):
            n = {"cards": len(self.deck()), "relics": len(self.relics()),
                 "potions": len(_g(self.run, "potions", []) or [])}[p]
            active = (self.page == p)
            self.add_btn("tab_" + p, (x, 26, x + 110, 70),
                         "%s %d" % (label, n), (lambda pp=p: self._set_page(pp)),
                         color=CYAN if active else TEXT_DIM,
                         style="solid" if active else "ghost")
            x += 120
        if self.page == "cards":
            sx = self.w - 620
            for key, label in self.SORTS:
                active = (self.sort == key)
                self.add_btn("sort_" + key, (sx, 26, sx + 108, 70), label,
                             (lambda k=key: self._set_sort(k)),
                             color=GOLD if active else TEXT_DIM,
                             style="solid" if active else "ghost",
                             font=T.FONT_SMALL)
                sx += 114
        if self.page == "cards":
            self._draw_cards()
        elif self.page == "relics":
            self._draw_relics()
        else:
            self._draw_potions()

    def _set_page(self, p: str) -> None:
        self.page = p
        self.scroll = 0
        self.app.redraw()

    def _set_sort(self, k: str) -> None:
        self.sort = k
        self.app.redraw()

    def _sorted(self) -> list:
        deck = self.deck()
        keyfn = {
            "type": lambda c: (str(_g(_g(c, "defn", None), "type", "")),
                               int(_g(_g(c, "defn", None), "cost", 0)),
                               str(_g(c, "name", ""))),
            "cost": lambda c: (int(_g(_g(c, "defn", None), "cost", 0)),
                               str(_g(c, "name", ""))),
            "rarity": lambda c: (str(_g(_g(c, "defn", None), "rarity", "")),
                                 str(_g(c, "name", ""))),
            "name": lambda c: str(_g(c, "name", "")),
            "arch": lambda c: (str(_g(_g(c, "defn", None), "arch", "")),
                               str(_g(c, "name", ""))),
        }[self.sort]
        try:
            return sorted(deck, key=keyfn)
        except Exception:
            return deck

    def _draw_cards(self) -> None:
        cards = self._sorted()
        if not cards:
            self.app.text_shadow(self.w / 2, self.h / 2, "手令库是空的",
                                 font=T.FONT_H1, fill=TEXT_FAINT)
            return
        cw, ch = T.CARD_W * 0.52, T.CARD_H * 0.52
        gap = 14
        cols = max(1, int((self.w - 140) // (cw + gap)))
        self.cols = cols
        start_y = self.grid_top
        for i, card in enumerate(cards):
            r, col = divmod(i, cols)
            x = 70 + col * (cw + gap)
            y = start_y + r * (ch + gap) - self.scroll * (ch + gap)
            if y + ch < self.grid_top - 40 or y > self.grid_bottom + 40:
                continue
            self._mini_card(card, x, y, cw, ch)
        total_rows = (len(cards) + cols - 1) // cols
        max_scroll = max(0, total_rows - max(1, int((self.grid_bottom -
                                                     self.grid_top) //
                                                    (ch + gap))))
        self._max_scroll = max_scroll

    def _mini_card(self, card, x: float, y: float, cw: float, ch: float) -> None:
        d = _g(card, "defn", None)
        rar = str(_g(d, "rarity", "common"))
        typ = str(_g(d, "type", "skill"))
        rcol = _rarity_color(rar)
        tcol = getattr(T, "TYPE_COLORS", {}).get(typ, TEXT_DIM) \
            if isinstance(getattr(T, "TYPE_COLORS", None), dict) else TEXT_DIM
        drawer = self._card_drawer()
        if drawer is not None and card is not None:
            try:
                drawer(self.c, x + cw / 2, y + ch / 2, card,
                       scale=cw / float(T.CARD_W), angle=0.0,
                       playable=True, hover=False, selected=False,
                       tags="mini", glow=False)
                return
            except Exception:
                pass
        self.app.round_rect(x, y, x + cw, y + ch, 8,
                            fill=_alpha_on(BG_DEEP, PANEL, 0.95), outline=rcol,
                            width=2)
        self.app.round_rect(x + 3, y + 3, x + cw - 3, y + 20, 5, fill=tcol,
                            outline="")
        self.app.text_shadow(x + cw / 2, y + 12,
                             self._fit(_g(card, "display_name", _g(card, "name", "?")),
                                       cw - 12, T.FONT_TINY),
                             font=T.FONT_TINY, fill="#0B1620")
        cost = _g(d, "cost", 0)
        self.c.create_oval(x + 4, y + 26, x + 26, y + 48,
                           fill=_alpha_on(BG_DEEP, GOLD, 0.95), outline="")
        self.app.text_shadow(x + 15, y + 37, "X" if cost == -1 else str(cost),
                             font=T.FONT_TINY, fill="#3A2600")
        txt = str(_g(d, "text", ""))
        lines = self.app.wrap_text(txt, int(cw - 16), T.FONT_TINY, max_lines=3)
        ty = y + 54
        for ln in lines:
            self.app.text_shadow(x + 8, ty, ln, font=T.FONT_TINY, fill=TEXT,
                                 anchor="w")
            ty += 13

    def _card_drawer(self):
        if W is None:
            return None
        cv = getattr(W, "CardView", None)
        return getattr(cv, "draw_on", None) if cv else None

    def _fit(self, text: str, maxw: float, font) -> str:
        try:
            fn = getattr(T, "slice_text_cjk", None)
            if callable(fn):
                return str(fn(str(text), maxw, font))
        except Exception:
            pass
        return str(text)

    def _draw_relics(self) -> None:
        relics = self.relics()
        if not relics:
            self.app.text_shadow(self.w / 2, self.h / 2, "还没有获得任何勋章",
                                 font=T.FONT_H1, fill=TEXT_FAINT)
            return
        db = {}
        try:
            from core.relics import RELIC_DB  # type: ignore
            db = RELIC_DB
        except Exception:
            pass
        size = 64
        gap = 26
        cols = max(1, int((self.w - 140) // (size + gap + 160)))
        for i, rid in enumerate(relics):
            r, col = divmod(i, cols)
            x = 90 + col * (size + gap + 170)
            y = 160 + r * (size + 40)
            d = db.get(rid) if isinstance(db, dict) else None
            col_hex = _rarity_color(str(_g(d, "rarity", "common")))
            self.c.create_oval(x, y, x + size, y + size,
                               fill=_alpha_on(BG_DEEP, PANEL, 0.9),
                               outline=col_hex, width=2)
            self._relic_glyph(x + size / 2, y + size / 2, size * 0.32,
                              str(rid), col_hex)
            self.app.text_shadow(x + size + 12, y + 20,
                                 str(_g(d, "name", rid)), font=T.FONT_BODY,
                                 fill=TEXT, anchor="w")
            txt = str(_g(d, "text", ""))
            for j, ln in enumerate(self.app.wrap_text(txt, 150, T.FONT_TINY,
                                                      max_lines=3)):
                self.app.text_shadow(x + size + 12, y + 44 + j * 14, ln,
                                     font=T.FONT_TINY, fill=TEXT_DIM,
                                     anchor="w")

    def _relic_glyph(self, cx: float, cy: float, r: float, rid: str,
                     col: str) -> None:
        shapes = ("crystal", "star", "droplet", "eye", "rune", "gear", "shell",
                  "shard")
        idx = sum((i + 1) * ord(ch) for i, ch in enumerate(rid)) % len(shapes)
        shape = shapes[idx]
        if shape == "star":
            pts = []
            for i in range(10):
                a = -math.pi / 2 + math.pi * i / 5.0
                rr = r * (1.0 if i % 2 == 0 else 0.45)
                pts.extend((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
            self.c.create_polygon(pts, fill=col, outline="")
        elif shape in ("droplet", "shell"):
            self.c.create_oval(cx - r * 0.7, cy - r * 0.7, cx + r * 0.7,
                               cy + r, fill=col, outline="")
            self.c.create_polygon(cx, cy - r * 1.15, cx + r * 0.62, cy - r * 0.2,
                                  cx - r * 0.62, cy - r * 0.2, fill=col,
                                  outline="")
        elif shape == "eye":
            self.c.create_oval(cx - r, cy - r * 0.55, cx + r, cy + r * 0.55,
                               fill=col, outline="")
            self.c.create_oval(cx - r * 0.3, cy - r * 0.3, cx + r * 0.3,
                               cy + r * 0.3, fill=BG_DEEP, outline="")
        else:
            pts = []
            for i in range(6):
                a = -math.pi / 2 + math.pi * 2 * i / 6.0
                pts.extend((cx + math.cos(a) * r, cy + math.sin(a) * r))
            self.c.create_polygon(pts, fill=col, outline="")

    def _draw_potions(self) -> None:
        potions = list(_g(self.run, "potions", []) or [])
        if not potions:
            self.app.text_shadow(self.w / 2, self.h / 2, "没有补给品",
                                 font=T.FONT_H1, fill=TEXT_FAINT)
            return
        for i, pid in enumerate(potions):
            x = self.w / 2 - 200 + i * 200
            y = 220
            self.c.create_oval(x, y, x + 90, y + 120,
                               fill=_alpha_on(BG_DEEP, POISON, 0.5),
                               outline=POISON, width=3)
            self.app.text_shadow(x + 45, y + 60, str(pid)[:4], font=T.FONT_TINY,
                                 fill=TEXT)
            self.app.text_shadow(x + 45, y + 140, str(pid), font=T.FONT_SMALL,
                                 fill=TEXT_DIM)

    def on_click_extra(self, x: float, y: float) -> None:
        if self.page == "cards" and not self.ro:
            uid = self._card_at(x, y)
            if uid is not None:
                self._card_menu(uid)

    def _card_at(self, x: float, y: float):
        cards = self._sorted()
        cw, ch = T.CARD_W * 0.52, T.CARD_H * 0.52
        gap = 14
        cols = max(1, self.cols)
        for i, card in enumerate(cards):
            r, col = divmod(i, cols)
            bx = 70 + col * (cw + gap)
            by = self.grid_top + r * (ch + gap) - self.scroll * (ch + gap)
            if bx <= x <= bx + cw and by <= y <= by + ch:
                return card
        return None

    def _card_menu(self, card) -> None:
        """点击卡牌：升级（若可）或显示详情。"""
        run = self.run
        if run is None:
            return
        uid = _g(card, "uid", None)
        up = getattr(run, "upgrade_card", None)
        if callable(up) and uid is not None:
            ok = False
            try:
                ok = bool(up(uid))
            except Exception:
                ok = False
            if ok:
                self.app.pop_text(self.w / 2, 120, "升级成功！", color=POISON,
                                  size=24)
                self.app.redraw()
                return
        d = _g(card, "defn", None)
        self.app.show_tooltip(str(_g(d, "text", "")), self.w / 2 - 150,
                              self.h / 2,
                              title=str(_g(card, "display_name",
                                           _g(card, "name", "卡牌"))),
                              color=_rarity_color(str(_g(d, "rarity", "common"))),
                              width=320)

    def on_motion_extra(self, x, y, prev) -> None:
        card = self._card_at(x, y)
        key = str(_g(card, "uid", "")) if card is not None else None
        self.hover_card = key
        if card is not None:
            d = _g(card, "defn", None)
            self.app.cancel("view_tip")
            self.app._jobs["view_tip"] = self.app.after(
                250, lambda cd=card: self._show_card_tip(cd))
        return

    def _show_card_tip(self, card) -> None:
        d = _g(card, "defn", None)
        self.app.show_tooltip(str(_g(d, "text", "")), self.w / 2 - 150,
                              self.h - 260,
                              title=str(_g(card, "display_name",
                                           _g(card, "name", "卡牌"))),
                              color=_rarity_color(str(_g(d, "rarity", "common"))),
                              width=320)


# --------------------------------------------------------------------------- #
# 卡牌奖励
# --------------------------------------------------------------------------- #
class RewardView(View):
    """3 选 1 + 跳过。"""

    def on_build(self) -> None:
        self.cards: List[Any] = list(self.kwargs.get("cards") or [])
        if not self.cards:
            self.cards = self._roll()
        self.relic_reward = self.kwargs.get("relic")
        self.taken: Optional[int] = None
        self.hover_card: Optional[int] = None   # BUG #7：原先未初始化
        self.card_rects: List[Tuple[float, float, float, float]] = []
        self.anim = 0.0

    def _roll(self) -> List[Any]:
        run = self.run
        fn = getattr(run, "offer_card_rewards", None) if run else None
        if callable(fn):
            try:
                return list(fn(3) or [])
            except Exception:
                return []
        return []

    def layout(self) -> None:
        pass

    def body(self) -> None:
        self.draw_bg("#3B3226", BG_DEEP)
        self.title("战 利 品", 66, "选择一张手令加入作战牌组")
        cw, ch = T.CARD_W, T.CARD_H
        n = max(1, len(self.cards))
        gap = 40
        total = n * cw + (n - 1) * gap
        x0 = self.w / 2 - total / 2
        y = self.h / 2 - ch / 2 + 10
        self.card_rects = []
        drawer = None
        if W is not None:
            drawer = getattr(getattr(W, "CardView", None), "draw_on", None)
        hovered = self.hover_card if isinstance(self.hover_card, int) else None
        for i, card in enumerate(self.cards):
            x = x0 + i * (cw + gap)
            hot = (hovered == i)
            scale = 1.08 if hot else 1.0
            self.card_rects.append((x, y, x + cw, y + ch))
            if drawer is not None and card is not None:
                try:
                    drawer(self.c, x + cw / 2, y + ch / 2 - (18 if hot else 0),
                           card, scale=scale, angle=0.0, playable=True,
                           hover=hot, selected=False, tags="reward")
                    continue
                except Exception:
                    pass
            self.app.round_rect(x, y, x + cw, y + ch, 12,
                                fill=_alpha_on(BG_DEEP, PANEL, 0.95),
                                outline=GOLD, width=2)
            self.app.text_shadow(x + cw / 2, y + ch / 2,
                                 str(_g(card, "name", "?")), font=T.FONT_H2,
                                 fill=TEXT)
        # 遗物奖励
        y2 = y + ch + 34
        rel = self.relic_reward
        if not rel:
            rel = self._roll_relic()
        if rel:
            txt = "勋章奖励：%s" % self._relic_name(rel)
            self.app.text_shadow(self.w / 2, y2 + 18, txt, font=T.FONT_H2,
                                 fill=GOLD)
            self.add_btn("relic", (self.w / 2 - 140, y2 + 44, self.w / 2 + 140,
                                   y2 + 92), "领取勋章",
                         (lambda r=rel: self._take_relic(r)), color=GOLD)
        self.add_btn("skip", (self.w / 2 - 110, self.h - 96, self.w / 2 + 110,
                              self.h - 44), "跳过奖励",
                     self._skip, color=TEXT_DIM, style="ghost")
        self.add_btn("deck", (self.w - 220, self.h - 96, self.w - 24,
                              self.h - 44), "查看手令",
                     lambda: self.app.show("deck", context="reward"),
                     color=CYAN, style="ghost")

    def _roll_relic(self):
        run = self.run
        fn = getattr(run, "offer_relic_rewards", None) if run else None
        if callable(fn) and str(self.kwargs.get("kind", "")) in ("elite", "boss"):
            try:
                got = list(fn(1) or [])
                return got[0] if got else None
            except Exception:
                return None
        return None

    def _relic_name(self, rid) -> str:
        try:
            from core.relics import relic_name  # type: ignore
            return str(relic_name(rid))
        except Exception:
            return str(rid)

    def _take_relic(self, rid) -> None:
        run = self.run
        fn = getattr(run, "add_relic", None) if run else None
        if callable(fn):
            try:
                fn(rid)
            except Exception:
                pass
        self.relic_reward = None
        self.app.pop_text(self.w / 2, self.h * 0.32, "获得勋章：%s" %
                          self._relic_name(rid), color=GOLD, size=22)
        self.app.redraw()

    def _take(self, i: int) -> None:
        if not (0 <= i < len(self.cards)):
            return
        card = self.cards[i]
        run = self.run
        did = _g(_g(card, "defn", card), "id", None) or _g(card, "id", None)
        fn = getattr(run, "add_card", None) if run else None
        if callable(fn) and did:
            try:
                fn(did)
            except Exception:
                pass
        self.taken = i
        self.app.pop_text(self.w / 2, self.h * 0.30, "已编入牌组",
                          color=POISON, size=22)
        self.app.once(320, self._leave)

    def _skip(self) -> None:
        self.app.pop_text(self.w / 2, self.h * 0.30, "跳过", color=TEXT_DIM,
                          size=20)
        self.app.once(200, self._leave)

    def _leave(self) -> None:
        run = self.run
        if run is None:
            self.app.show("menu")
            return
        if bool(_g(run, "pending_node", None)) is False and \
                str(self.kwargs.get("next", "")) == "gameover":
            self.app.show("gameover", result="won")
            return
        self.app.show("map")

    def on_click_extra(self, x: float, y: float) -> None:
        for i, (x1, y1, x2, y2) in enumerate(self.card_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._take(i)
                return

    def on_motion_extra(self, x, y, prev) -> None:
        hot = None
        for i, (x1, y1, x2, y2) in enumerate(self.card_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                hot = i
                break
        if hot != prev and hot is not None:
            self.app.cancel("view_tip")
            self.app._jobs["view_tip"] = self.app.after(
                250, lambda i=hot: self._tip(i))
        self.hover_card = hot

    def _tip(self, i: int) -> None:
        if not (0 <= i < len(self.cards)):
            return
        x1, y1, x2, y2 = self.card_rects[i]
        d = _g(self.cards[i], "defn", self.cards[i])
        self.app.show_tooltip(str(_g(d, "text", "")), x2 + 8, y1,
                              title=str(_g(self.cards[i], "name", "卡牌")),
                              color=_rarity_color(str(_g(d, "rarity", "common"))),
                              width=300)


# --------------------------------------------------------------------------- #
# 商店
# --------------------------------------------------------------------------- #
class ShopView(View):
    """补给站：买手令 / 勋章 / 补给品 / 精简牌组。"""

    def on_build(self) -> None:
        self.inv = self.kwargs.get("inventory") or self._build_inv()
        self.cards = list((self.inv or {}).get("cards") or [])
        self.relics = list((self.inv or {}).get("relics") or [])
        self.potions = list((self.inv or {}).get("potions") or [])
        self.remove_price = int((self.inv or {}).get("remove_price", 75) or 75)
        self.sold_cards: set = set()
        self.sold_relics: set = set()
        self.sold_potions: set = set()
        self.message = ""
        self.msg_life = 0.0
        self.remove_mode = False
        self.hover_item = None

    def _build_inv(self):
        run = self.run
        if run is None:
            return {}
        try:
            from core import events as EV  # type: ignore
            fn = getattr(EV, "build_shop_inventory", None)
            if callable(fn):
                return fn(run.rng, int(_g(run, "act", 1)), int(_g(run, "ascension", 0)))
        except Exception:
            pass
        return {}

    def _tick(self) -> None:
        if self.msg_life > 0:
            self.msg_life -= 40
        self.anim += 0.05
        self.app.redraw()

    def _price(self, rarity: str, kind: str) -> int:
        try:
            from core import events as EV  # type: ignore
            if kind == "card":
                return int(getattr(EV, "SHOP_CARD_PRICE", {}).get(rarity, 50))
            if kind == "relic":
                return int(getattr(EV, "SHOP_RELIC_PRICE", {}).get(rarity, 150))
            return int(getattr(EV, "SHOP_POTION_PRICE", 60))
        except Exception:
            return {"card": 50, "relic": 150, "potion": 60}.get(kind, 50)

    def body(self) -> None:
        self.draw_bg("#33291C", BG_DEEP)
        run = self.run
        gold = int(_g(run, "gold", 0)) if run else 0
        self.title("补 给 站", 56, "军费：%d" % gold, color=GOLD)
        self.top_bar()

        if self.remove_mode:
            self._draw_remove_mode()
            return

        y = 132
        # --- 卡牌 ---
        self.app.text_shadow(70, y, "卡牌", font=T.FONT_H1, fill=CYAN,
                             anchor="w")
        x = 150
        drawer = None
        if W is not None:
            drawer = getattr(getattr(W, "CardView", None), "draw_on", None)
        for i, card in enumerate(self.cards):
            if i in self.sold_cards:
                continue
            cw, ch = T.CARD_W * 0.62, T.CARD_H * 0.62
            if x + cw > self.w - 60:
                break
            price = self._price(str(_g(card, "rarity", "common")), "card")
            if drawer is not None:
                try:
                    drawer(self.c, x + cw / 2, y + 42 + ch / 2, card,
                           scale=cw / float(T.CARD_W), tags="shop")
                except Exception:
                    pass
            afford = gold >= price
            col = GOLD if afford else TEXT_FAINT
            self.add_btn("buy_c_%d" % i,
                         (x, y + 48 + ch, x + cw, y + 88 + ch),
                         "¥ %d" % price, (lambda k=i: self._buy_card(k)),
                         color=col, enabled=afford, font=T.FONT_BODY)
            self.add_btn("tipc_%d" % i, (x, y, x + cw, y + 42 + ch), "",
                         (lambda: None), color=BG_DEEP, style="ghost",
                         tip=str(_g(card, "text", "")),
                         tip_title=str(_g(card, "name", "卡牌")))
            self.set_btn("tipc_%d" % i, hidden=True)
            self._tips["card_%d" % i] = (x, y + 42 + ch,
                                         str(_g(card, "name", "卡牌")),
                                         str(_g(card, "text", "")),
                                         _rarity_color(str(_g(card, "rarity",
                                                               "common"))))
            x += cw + 24

        # --- 遗物 ---
        y = 132 + T.CARD_H * 0.62 + 130
        self.app.text_shadow(70, y, "勋章", font=T.FONT_H1, fill=GOLD,
                             anchor="w")
        x = 150
        for i, rid in enumerate(self.relics):
            if i in self.sold_relics:
                continue
            rar = str(_g(rid, "rarity", "common"))
            price = self._price(rar, "relic")
            afford = gold >= price
            self.c.create_oval(x, y + 30, x + 56, y + 86,
                               fill=_alpha_on(BG_DEEP, PANEL, 0.95),
                               outline=_rarity_color(rar), width=2)
            self._glyph(x + 28, y + 58, 18, str(_g(rid, "id", rid)),
                        _rarity_color(rar))
            self.app.text_shadow(x + 28, y + 96, str(_g(rid, "name", rid))[:8],
                                 font=T.FONT_TINY, fill=TEXT)
            self.add_btn("buy_r_%d" % i, (x, y + 108, x + 56, y + 144),
                         "¥%d" % price, (lambda k=i: self._buy_relic(k)),
                         color=GOLD if afford else TEXT_FAINT, enabled=afford,
                         font=T.FONT_TINY, radius=8)
            self._tips["relic_%d" % i] = (x, y + 86,
                                          str(_g(rid, "name", rid)),
                                          str(_g(rid, "text", "")),
                                          _rarity_color(rar))
            x += 90

        # --- 药水 ---
        y += 180
        self.app.text_shadow(70, y, "补给品", font=T.FONT_H1, fill=POISON,
                             anchor="w")
        x = 150
        for i, pid in enumerate(self.potions):
            if i in self.sold_potions:
                continue
            price = self._price("", "potion")
            afford = gold >= price
            self.c.create_oval(x, y + 26, x + 40, y + 80,
                               fill=_alpha_on(BG_DEEP, POISON, 0.6),
                               outline=POISON, width=2)
            self.app.text_shadow(x + 20, y + 53, str(pid)[:3],
                                 font=T.FONT_TINY, fill=TEXT)
            self.add_btn("buy_p_%d" % i, (x, y + 88, x + 40, y + 120),
                         "¥%d" % price, (lambda k=i: self._buy_potion(k)),
                         color=POISON if afford else TEXT_FAINT,
                         enabled=afford, font=T.FONT_TINY, radius=8)
            x += 70

        # --- 删卡服务 ---
        bxx = self.w - 400
        byy = y - 30
        self.app.round_rect(bxx, byy, bxx + 340, byy + 190, 14,
                            fill=_alpha_on(BG_DEEP, PANEL, 0.9),
                            outline=BORDER_HI, width=2)
        self.app.text_shadow(bxx + 170, byy + 34, "卡牌移除服务",
                             font=T.FONT_H2, fill=CYAN)
        self.app.text_shadow(bxx + 170, byy + 68,
                             "费用：%d 军费" % self.remove_price,
                             font=T.FONT_BODY, fill=TEXT)
        self.app.text_shadow(bxx + 170, byy + 94,
                             "（每使用一次，下次更贵）",
                             font=T.FONT_TINY, fill=TEXT_DIM)
        afford = gold >= self.remove_price and len(self.deck()) > 0
        self.add_btn("remove", (bxx + 70, byy + 122, bxx + 270, byy + 174),
                     "移除一张牌", self._enter_remove, color=GOLD,
                     enabled=afford,
                     tip="从牌组中永久移除一张手令，让牌组更精炼。",
                     tip_title="删卡")
        if self.message:
            self.app.text_shadow(self.w / 2, self.h - 96, self.message,
                                 font=T.FONT_H2, fill=GOLD)

    _tips: Dict[str, tuple] = {}

    def _glyph(self, cx, cy, r, rid, col) -> None:
        shapes = ("crystal", "star", "droplet", "eye", "rune", "gear")
        idx = sum((i + 1) * ord(ch) for i, ch in enumerate(rid)) % len(shapes)
        if shapes[idx] == "star":
            pts = []
            for i in range(10):
                a = -math.pi / 2 + math.pi * i / 5.0
                rr = r * (1.0 if i % 2 == 0 else 0.45)
                pts.extend((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
            self.c.create_polygon(pts, fill=col, outline="")
        else:
            pts = []
            for i in range(6):
                a = -math.pi / 2 + math.pi * 2 * i / 6.0
                pts.extend((cx + math.cos(a) * r, cy + math.sin(a) * r))
            self.c.create_polygon(pts, fill=col, outline="")

    def _draw_remove_mode(self) -> None:
        self.app.text_shadow(self.w / 2, 106,
                             "选择要移除的牌（再次点击确认）",
                             font=T.FONT_H2, fill=GOLD)
        cards = self.deck()
        if not cards:
            self.app.text_shadow(self.w / 2, self.h / 2, "手令库是空的",
                                 font=T.FONT_H1, fill=TEXT_FAINT)
            return
        cw, ch = T.CARD_W * 0.5, T.CARD_H * 0.5
        gap = 12
        cols = max(1, int((self.w - 140) // (cw + gap)))
        for i, card in enumerate(cards):
            r, col = divmod(i, cols)
            x = 70 + col * (cw + gap)
            y = 150 + r * (ch + gap) - self.scroll * (ch + gap)
            if y > self.h - 60:
                continue
            d = _g(card, "defn", None)
            self.app.round_rect(x, y, x + cw, y + ch, 10,
                                fill=_alpha_on(BG_DEEP, PANEL, 0.95),
                                outline=_rarity_color(str(_g(d, "rarity",
                                                             "common"))),
                                width=2)
            self.app.text_shadow(x + cw / 2, y + 26,
                                 str(_g(card, "display_name",
                                        _g(card, "name", "?"))),
                                 font=T.FONT_BODY, fill=TEXT)
            for j, ln in enumerate(self.app.wrap_text(str(_g(d, "text", "")),
                                                      int(cw - 20),
                                                      T.FONT_TINY, 3)):
                self.app.text_shadow(x + cw / 2, y + 54 + j * 14, ln,
                                     font=T.FONT_TINY, fill=TEXT_DIM)
            w = self.add_btn_widget = None
        self.add_btn("cancel", (self.w - 220, self.h - 74, self.w - 24,
                                self.h - 26), "取消", self._exit_remove,
                     color=TEXT_DIM, style="ghost")

    def _enter_remove(self) -> None:
        self.remove_mode = True
        self.scroll = 0
        self.app.redraw()

    def _exit_remove(self) -> None:
        self.remove_mode = False
        self.app.redraw()

    def on_click_extra(self, x: float, y: float) -> None:
        if self.remove_mode:
            card = self._remove_at(x, y)
            if card is not None:
                self._do_remove(card)
            return
        for key, (bx, by, name, text, col) in list(self._tips.items()):
            if bx <= x <= bx + 130 and by - 60 <= y <= by + 8:
                self.app.show_tooltip(text, bx, by, title=name, color=col,
                                      width=280)
                return

    def _remove_at(self, x, y):
        cards = self.deck()
        cw, ch = T.CARD_W * 0.5, T.CARD_H * 0.5
        gap = 12
        cols = max(1, int((self.w - 140) // (cw + gap)))
        for i, card in enumerate(cards):
            r, col = divmod(i, cols)
            bx = 70 + col * (cw + gap)
            by = 150 + r * (ch + gap) - self.scroll * (ch + gap)
            if bx <= x <= bx + cw and by <= y <= by + ch:
                return card
        return None

    def _do_remove(self, card) -> None:
        run = self.run
        gold = int(_g(run, "gold", 0)) if run else 0
        if gold < self.remove_price:
            self._say("军费不足", BLOOD)
            return
        fn = getattr(run, "remove_card", None) if run else None
        ok = False
        if callable(fn):
            try:
                ok = bool(fn(_g(card, "uid", None)))
            except Exception:
                ok = False
        if ok:
            try:
                run.gold -= self.remove_price
                run.remove_count = int(_g(run, "remove_count", 0)) + 1
            except Exception:
                pass
            self.remove_price += 25
            self._say("已移除 %s" % _g(card, "name", "卡牌"), POISON)
            self.remove_mode = False
        else:
            self._say("无法移除这张牌", BLOOD)

    def _say(self, text: str, color: str) -> None:
        self.message = text
        self.app.pop_text(self.w / 2, self.h - 130, text, color=color, size=20)
        self.app.redraw()

    def _spend(self, price: int) -> bool:
        run = self.run
        if run is None:
            return False
        if int(_g(run, "gold", 0)) < price:
            self._say("军费不足", BLOOD)
            return False
        try:
            run.gold -= price
        except Exception:
            return False
        return True

    def _buy_card(self, i: int) -> None:
        if not (0 <= i < len(self.cards)):
            return
        card = self.cards[i]
        price = self._price(str(_g(card, "rarity", "common")), "card")
        if not self._spend(price):
            return
        run = self.run
        fn = getattr(run, "add_card", None) if run else None
        did = _g(card, "id", None)
        if callable(fn) and did:
            try:
                fn(did)
            except Exception:
                pass
        self.sold_cards.add(i)
        self._say("购买：%s" % _g(card, "name", "卡牌"), CYAN)

    def _buy_relic(self, i: int) -> None:
        if not (0 <= i < len(self.relics)):
            return
        rid = self.relics[i]
        price = self._price(str(_g(rid, "rarity", "common")), "relic")
        if not self._spend(price):
            return
        run = self.run
        fn = getattr(run, "add_relic", None) if run else None
        if callable(fn):
            try:
                fn(_g(rid, "id", rid))
            except Exception:
                pass
        self.sold_relics.add(i)
        self._say("购入勋章：%s" % _g(rid, "name", rid), GOLD)

    def _buy_potion(self, i: int) -> None:
        if not (0 <= i < len(self.potions)):
            return
        pid = self.potions[i]
        if not self._spend(self._price("", "potion")):
            return
        run = self.run
        fn = getattr(run, "add_potion", None) if run else None
        if callable(fn):
            try:
                fn(pid)
            except Exception:
                pass
        self.sold_potions.add(i)
        self._say("购入补给品", POISON)


# --------------------------------------------------------------------------- #
# 休息（营火）
# --------------------------------------------------------------------------- #
class RestView(View):
    """回血 / 升级。"""

    def on_build(self) -> None:
        self.mode = "choose"
        self.upgrade_cards: List[Any] = []
        self.chosen = None
        run = self.run
        fn = getattr(run, "upgradable_cards", None) if run else None
        if callable(fn):
            try:
                self.upgrade_cards = list(fn() or [])
            except Exception:
                self.upgrade_cards = []
        self.heal_amount = 0
        hf = getattr(run, "rest_heal_amount", None) if run else None
        if callable(hf):
            try:
                self.heal_amount = int(hf())
            except Exception:
                self.heal_amount = 0
        if not self.heal_amount:
            self.heal_amount = max(1, int(_g(run, "max_hp", 75) * 0.3)) if run else 1
        self.anim = 0.0

    def body(self) -> None:
        run = self.run
        self.draw_bg("#2E2418", "#0B0906")
        hp = int(_g(run, "hp", 0)) if run else 0
        mx = max(1, int(_g(run, "max_hp", 1))) if run else 1
        self.title("战 地 医 院", 56, "总部 HP：%d / %d" % (hp, mx), color="#FF9B4A")
        self.top_bar()
        # 火焰
        self._fire(self.w / 2, self.h * 0.62, min(self.w, self.h) / 900.0)

        if self.mode == "choose":
            self.add_btn("heal", (self.w / 2 - 420, self.h * 0.34,
                                  self.w / 2 - 40, self.h * 0.34 + 96),
                         "抢 修", self._do_heal, color=POISON,
                         tip="修复 %d 点总部 HP。" % self.heal_amount,
                         tip_title="战地医院", sub="+%d HP" % self.heal_amount)
            can_up = bool(self.upgrade_cards)
            self.add_btn("smith", (self.w / 2 + 40, self.h * 0.34,
                                   self.w / 2 + 420, self.h * 0.34 + 96),
                         "改 装", self._to_upgrade, color=GOLD,
                         enabled=can_up,
                         tip="升级一张手令（永久）。" if can_up
                         else "没有可升级的卡牌。",
                         tip_title="改装", sub="升级一张手令")
        elif self.mode == "upgrade":
            self._draw_upgrade_grid()
            self.add_btn("back", (24, 26, 150, 70), "◀ 返回",
                         lambda: self._set_mode("choose"), color=TEXT_DIM,
                         style="ghost")

    def _set_mode(self, m: str) -> None:
        self.mode = m
        self.app.redraw()

    def _fire(self, cx: float, cy: float, s: float) -> None:
        t = self.app._tick
        for i in range(3):
            w = (150 - i * 34) * s
            h = (260 - i * 40) * s * (1 + 0.05 * math.sin(t * 0.2 + i))
            col = ["#8C3A12", "#D9661F", "#FFC24D"][i]
            wob = math.sin(t * 0.25 + i) * 10 * s
            self.c.create_polygon(cx - w / 2, cy + h * 0.45,
                                  cx - w * 0.28 + wob, cy - h * 0.2,
                                  cx + wob * 0.5, cy - h * 0.5,
                                  cx + w * 0.28 + wob, cy - h * 0.1,
                                  cx + w / 2, cy + h * 0.45,
                                  fill=col, outline="", smooth=True)
        # 火星
        for i in range(14):
            ph = (t * 3 + i * 37) % 200
            tt = ph / 200.0
            px = cx + math.sin(i * 2.1 + t * 0.1) * (30 + 60 * tt) * s
            py = cy - 60 * s - 200 * tt * s
            r = max(1, (3 - 2 * tt)) * s
            col = _alpha_on("#050C14", "#FFD27A", max(0.0, 1 - tt))
            self.c.create_oval(px - r, py - r, px + r, py + r, fill=col,
                               outline="")
        # 木柴
        for i in (-1, 1):
            self.c.create_line(cx - 70 * s + i * 10, cy + 66 * s,
                               cx + 70 * s + i * 10, cy + 46 * s,
                               fill="#3A2415", width=int(16 * s))

    def _draw_upgrade_grid(self) -> None:
        if not self.upgrade_cards:
            self.app.text_shadow(self.w / 2, self.h / 2, "没有可升级的手令",
                                 font=T.FONT_H1, fill=TEXT_FAINT)
            return
        cw, ch = T.CARD_W * 0.56, T.CARD_H * 0.56
        gap = 16
        cols = max(1, int((self.w - 160) // (cw + gap)))
        drawer = None
        if W is not None:
            drawer = getattr(getattr(W, "CardView", None), "draw_on", None)
        for i, card in enumerate(self.upgrade_cards):
            r, col = divmod(i, cols)
            x = 90 + col * (cw + gap)
            y = 150 + r * (ch + gap)
            if y > self.h - 120:
                continue
            if drawer is not None:
                try:
                    drawer(self.c, x + cw / 2, y + ch / 2, card,
                           scale=cw / float(T.CARD_W), tags="up")
                    continue
                except Exception:
                    pass
            d = _g(card, "defn", None)
            self.app.round_rect(x, y, x + cw, y + ch, 10,
                                fill=_alpha_on(BG_DEEP, PANEL, 0.95),
                                outline=GOLD, width=2)
            self.app.text_shadow(x + cw / 2, y + ch / 2,
                                 str(_g(card, "name", "?")), font=T.FONT_H2,
                                 fill=TEXT)

    def on_click_extra(self, x: float, y: float) -> None:
        if self.mode != "upgrade":
            return
        cw, ch = T.CARD_W * 0.56, T.CARD_H * 0.56
        gap = 16
        cols = max(1, int((self.w - 160) // (cw + gap)))
        for i, card in enumerate(self.upgrade_cards):
            r, col = divmod(i, cols)
            bx = 90 + col * (cw + gap)
            by = 150 + r * (ch + gap)
            if bx <= x <= bx + cw and by <= y <= by + ch:
                self._upgrade(card)
                return

    def _upgrade(self, card) -> None:
        run = self.run
        fn = getattr(run, "upgrade_card", None) if run else None
        ok = False
        if callable(fn):
            try:
                ok = bool(fn(_g(card, "uid", None)))
            except Exception:
                ok = False
        if ok:
            self.app.pop_text(self.w / 2, self.h * 0.3, "改装完成！",
                              color=GOLD, size=26)
            self.app.once(400, self.back_to_map)
        else:
            self.app.pop_text(self.w / 2, self.h * 0.3, "升级失败",
                              color=BLOOD, size=20)

    def _do_heal(self) -> None:
        run = self.run
        fn = getattr(run, "heal", None) if run else None
        if callable(fn):
            try:
                fn(self.heal_amount)
            except Exception:
                pass
        self.app.pop_text(self.w / 2, self.h * 0.3,
                          "修复 %d 点总部 HP" % self.heal_amount, color=POISON,
                          size=26)
        self.app.once(420, self.back_to_map)

    def _to_upgrade(self) -> None:
        self._set_mode("upgrade")


# --------------------------------------------------------------------------- #
# 事件
# --------------------------------------------------------------------------- #
class EventView(View):
    """多选项叙事事件。"""

    def on_build(self) -> None:
        self.event = self.kwargs.get("event")
        if self.event is None:
            self.event = self._roll()
        self.result_text = ""
        self.done = False
        self.choices = list(_g(self.event, "choices", ()) or ())
        self.anim = 0.0

    def _roll(self):
        run = self.run
        if run is None:
            return None
        try:
            from core import events as EV  # type: ignore
            fn = getattr(EV, "random_event", None)
            if callable(fn):
                return fn(run.rng, int(_g(run, "act", 1)),
                          set(_g(run, "seen_events", []) or []))
        except Exception:
            pass
        return None

    def body(self) -> None:
        self.draw_bg("#2C2A20", BG_DEEP)
        ev = self.event
        name = str(_g(ev, "name", "未知战场事件"))
        text = str(_g(ev, "text", "什么都没有发生。"))
        self.title(name, 56, "", color="#B07BE8")
        self.top_bar()

        # 事件立绘（程序化）
        self._art(self.w * 0.22, self.h * 0.52, min(self.w, self.h) / 900.0,
                  str(_g(ev, "art", "")) or name)

        # 正文面板
        px, py = self.w * 0.42, self.h * 0.24
        pw, ph = self.w * 0.52, self.h * 0.46
        self.app.round_rect(px, py, px + pw, py + ph, 16,
                            fill=_alpha_on(BG_DEEP, PANEL, 0.92),
                            outline=BORDER_HI, width=2)
        lines = self.app.wrap_text(text, int(pw - 56), T.FONT_BODY)
        ty = py + 40
        for ln in lines[:12]:
            self.app.text_shadow(px + 28, ty, ln, font=T.FONT_BODY, fill=TEXT,
                                 anchor="w")
            ty += 28

        if self.result_text:
            self.app.round_rect(px, py + ph + 16, px + pw, py + ph + 116, 14,
                                fill=_alpha_on(BG_DEEP, PANEL_LO, 0.95),
                                outline=GOLD, width=2)
            for i, ln in enumerate(self.app.wrap_text(self.result_text,
                                                      int(pw - 56),
                                                      T.FONT_BODY)[:3]):
                self.app.text_shadow(px + 28, py + ph + 46 + i * 26, ln,
                                     font=T.FONT_BODY, fill=GOLD, anchor="w")
            self.add_btn("leave", (self.w / 2 - 130, self.h - 90,
                                   self.w / 2 + 130, self.h - 36),
                         "继续前进", self.back_to_map, color=GOLD)
            return

        # 选项
        cy = py + ph + 20
        for i, ch in enumerate(self.choices):
            label = str(_g(ch, "label", "选项 %d" % (i + 1)))
            desc = str(_g(ch, "desc", ""))
            ok = self._available(ch)
            rect = (px, cy, px + pw, cy + 68)
            self.add_btn("ch_%d" % i, rect, label,
                         (lambda k=i: self._pick(k)), color=CYAN if ok
                         else TEXT_FAINT, enabled=ok,
                         tip=desc, tip_title=label, font=T.FONT_H2)
            cy += 80
            if cy > self.h - 90:
                break

    def _available(self, ch) -> bool:
        req = _g(ch, "requires", None)
        if req is None:
            return True
        run = self.run
        if run is None:
            return False
        try:
            return bool(req(run))
        except Exception:
            return False

    def _art(self, cx: float, cy: float, s: float, key: str) -> None:
        t = self.app._tick
        seed = sum(ord(c) for c in key) if key else 11
        col = ["#7B4AB4", "#4A7FB4", "#4AB48A", "#B4824A", "#B44A9A"][seed % 5]
        # 神秘漩涡
        for i in range(9, 0, -1):
            r = (30 + i * 16) * s
            a = 0.06 + 0.04 * (9 - i)
            self.c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="",
                               outline=_alpha_on(BG_DEEP, col, a), width=2)
        for i in range(26):
            a = math.radians(i * 13.8 + t * 0.6)
            rr = (14 + i * 5.2) * s
            px = cx + math.cos(a) * rr
            py = cy + math.sin(a) * rr * 0.65
            r = max(1.0, (4 - i / 8.0)) * s
            self.c.create_oval(px - r, py - r, px + r, py + r,
                               fill=_alpha_on(BG_DEEP, col, 0.75 - i * 0.02),
                               outline="")
        self.c.create_oval(cx - 34 * s, cy - 34 * s, cx + 34 * s, cy + 34 * s,
                           fill=_alpha_on(BG_DEEP, "#0B1620", 0.9),
                           outline=_shade(col, 0.2), width=2)
        self.app.text_shadow(cx, cy, "?", font=(T.FONT_FAMILY or "Helvetica",
                                                52, "bold"), fill=col)

    def _pick(self, i: int) -> None:
        if not (0 <= i < len(self.choices)):
            return
        ch = self.choices[i]
        fn = _g(ch, "effect", None)
        run = self.run
        out = ""
        if callable(fn) and run is not None:
            try:
                out = str(fn(run) or "")
            except Exception as exc:
                out = "（事件效果执行失败：%s）" % exc
        self.result_text = out or "什么都没有发生。"
        self.choices = []
        self.app.pop_text(self.w / 2, self.h * 0.6, "已选择", color=GOLD,
                          size=20)
        self.app.redraw()


# --------------------------------------------------------------------------- #
# 宝箱
# --------------------------------------------------------------------------- #
class TreasureView(View):
    """开启宝箱。"""

    def on_build(self) -> None:
        self.reward = self.kwargs.get("treasure") or self._roll()
        self.opened = False
        self.loot_lines: List[str] = []
        self.anim = 0.0

    def _roll(self):
        run = self.run
        if run is None:
            return {}
        try:
            from core import events as EV  # type: ignore
            fn = getattr(EV, "roll_treasure", None)
            if callable(fn):
                return fn(run.rng, int(_g(run, "act", 1))) or {}
        except Exception:
            pass
        return {}

    def body(self) -> None:
        self.draw_bg("#33301F", BG_DEEP)
        self.title("宝 箱", 56, "", color=CYAN)
        self.top_bar()
        cx, cy = self.w / 2, self.h * 0.52
        s = min(self.w, self.h) / 900.0 * 1.4
        self._chest(cx, cy, s, self.opened)
        if self.opened:
            for i, ln in enumerate(self.loot_lines):
                self.app.text_shadow(cx, cy + 200 * s + i * 32, ln,
                                     font=T.FONT_H2, fill=GOLD)
            self.add_btn("leave", (cx - 130, self.h - 96, cx + 130,
                                   self.h - 42), "带走战利品", self.back_to_map,
                         color=GOLD)
        else:
            self.add_btn("open", (cx - 150, self.h - 116, cx + 150,
                                  self.h - 56), "打 开", self._open,
                         color=GOLD,
                         sub="%s" % self._tier_name())

    def _tier_name(self) -> str:
        tier = str(_g(self.reward, "tier", "")) if isinstance(self.reward, dict) \
            else ""
        return {"gold": "军费入库", "relic": "勋章箱", "potion": "补给品",
                "curse_relic": "诡异的低语"}.get(tier, "未知")

    def _chest(self, cx: float, cy: float, s: float, opened: bool) -> None:
        w, h = 300 * s, 200 * s
        body_col = "#7A5A2A" if not opened else "#5C4420"
        self.app.round_rect(cx - w / 2, cy - h * 0.1, cx + w / 2, cy + h * 0.7,
                            10, fill=body_col, outline=_shade(body_col, -0.4),
                            width=4)
        if opened:
            # 掀开的盖子
            self.c.create_polygon(cx - w / 2, cy - h * 0.1,
                                  cx - w / 2 + 20 * s, cy - h * 0.8,
                                  cx + w / 2 - 20 * s, cy - h * 0.95,
                                  cx + w / 2, cy - h * 0.1,
                                  fill=_shade(body_col, 0.2), outline="")
            t = self.app._tick
            for i in range(24):
                a = math.radians(i * 15 + t * 2)
                rr = (40 + i * 6) * s
                px = cx + math.cos(a) * rr
                py = cy - h * 0.2 + math.sin(a) * rr * 0.4
                col = ["#F2C14E", "#3FD8D0", "#FFD27A"][i % 3]
                r = max(1.5, (5 - i / 6.0)) * s
                self.c.create_oval(px - r, py - r, px + r, py + r, fill=col,
                                   outline="")
        else:
            self.app.round_rect(cx - w / 2 - 6, cy - h * 0.46, cx + w / 2 + 6,
                                cy - h * 0.04, 12,
                                fill=_shade(body_col, 0.16),
                                outline=_shade(body_col, -0.4), width=4)
            self.app.round_rect(cx - 22 * s, cy - h * 0.22, cx + 22 * s,
                                cy + h * 0.2, 8, fill=GOLD,
                                outline=_shade(GOLD, -0.4), width=3)
            self.c.create_oval(cx - 10 * s, cy - 4 * s, cx + 10 * s,
                               cy + 16 * s, fill="#3A2600", outline="")
        # 底座
        self.app.round_rect(cx - w / 2 - 14, cy + h * 0.7, cx + w / 2 + 14,
                            cy + h * 0.82, 8, fill="#2A1D10", outline="")

    def _open(self) -> None:
        run = self.run
        r = self.reward if isinstance(self.reward, dict) else {}
        lines: List[str] = []
        gold = int(r.get("gold", 0) or 0)
        if gold:
            fn = getattr(run, "add_gold", None) if run else None
            if callable(fn):
                try:
                    fn(gold)
                except Exception:
                    pass
            lines.append("军费 +%d" % gold)
        rid = r.get("relic_id") or r.get("relic")
        if rid:
            fn = getattr(run, "add_relic", None) if run else None
            if callable(fn):
                try:
                    fn(rid)
                except Exception:
                    pass
            try:
                from core.relics import relic_name  # type: ignore
                rid = relic_name(rid)
            except Exception:
                pass
            lines.append("勋章：%s" % rid)
        pid = r.get("potion_id") or r.get("potion")
        if pid:
            fn = getattr(run, "add_potion", None) if run else None
            if callable(fn):
                try:
                    fn(pid)
                except Exception:
                    pass
            lines.append("补给品：%s" % pid)
        cid = r.get("curse_id") or r.get("curse")
        if cid:
            fn = getattr(run, "add_card", None) if run else None
            if callable(fn):
                try:
                    fn(cid)
                except Exception:
                    pass
            lines.append("诅咒：%s" % cid)
        if not lines:
            lines.append("空空如也……")
        self.loot_lines = lines
        self.opened = True
        self.app.flash(_alpha_on(BG_DEEP, GOLD, 0.25), 180)
        self.app.pop_text(self.w / 2, self.h * 0.32, "宝物到手！", color=GOLD,
                          size=28)
        self.app.redraw()


# --------------------------------------------------------------------------- #
# 结算
# --------------------------------------------------------------------------- #
class GameOverView(View):
    """胜负结算：分数 / 统计 / 解锁。"""

    def on_build(self) -> None:
        self.result = str(self.kwargs.get("result") or "lost")
        self.won = (self.result == "won")
        self.score = self._compute_score()
        self.new_unlocks: List[str] = []
        if not self.kwargs.get("_recorded"):
            self._record()
        self.anim = 0.0
        self.reveal = 0.0

    def _tick(self) -> None:
        self.anim += 0.05
        self.reveal = min(1.0, self.reveal + 0.06)
        self.app.redraw()

    def _compute_score(self) -> int:
        run = self.run
        fn = getattr(run, "final_score", None) if run else None
        if callable(fn):
            try:
                return int(fn())
            except Exception:
                pass
        return int(_g(run, "score", 0))

    def _record(self) -> None:
        meta = self.app.meta_progress()
        run = self.run
        if meta is None or run is None:
            return
        fn = getattr(meta, "record_run", None)
        if callable(fn):
            try:
                self.new_unlocks = list(fn(run, self.won) or [])
            except Exception:
                self.new_unlocks = []
        if self.won:
            try:
                meta.wins = int(_g(meta, "wins", 0)) + 1
                meta.unlock("first_win")
            except Exception:
                pass
        self.app.save_meta()

    def body(self) -> None:
        top = "#1A4A2E" if self.won else "#3A1420"
        self.draw_bg(top, "#050C14")
        w, h = self.w, self.h
        t = self.reveal
        color = GOLD if self.won else BLOOD
        title = "通 关 ！" if self.won else "潜 航 结 束"
        self.app.text_shadow(w / 2, h * 0.16, title,
                             font=(T.FONT_FAMILY or "Helvetica", 60, "bold"),
                             fill=_lerp(BG_DEEP, color, min(1.0, t * 1.4)))
        sub = "你攻陷了敌军最高要塞" if self.won else "你的指挥部被敌军摧毁"
        self.app.text_shadow(w / 2, h * 0.16 + 56, sub, font=T.FONT_H2,
                             fill=_lerp(BG_DEEP, TEXT_DIM, t))
        # 分数
        self.app.text_shadow(w / 2, h * 0.28, "最终得分",
                             font=T.FONT_H1, fill=TEXT_DIM)
        self.app.text_shadow(w / 2, h * 0.35, str(int(self.score * t)),
                             font=(T.FONT_FAMILY or "Helvetica", 52, "bold"),
                             fill=GOLD)

        # 统计表
        run = self.run
        stats = [
            ("推进层数", int(_g(run, "floor", 0))),
            ("军费", int(_g(run, "gold", 0))),
            ("生命", "%d/%d" % (int(_g(run, "hp", 0)),
                                int(_g(run, "max_hp", 1)))),
            ("手令", "%d 张" % len(self.deck())),
            ("勋章", "%d 枚" % len(self.relics())),
            ("战役难度", int(_g(run, "ascension", 0))),
        ]
        sx = w / 2 - 380
        sy = h * 0.46
        for i, (k, v) in enumerate(stats):
            col, row = divmod(i, 3)
            x = sx + col * 260
            y = sy + row * 46
            self.app.text_shadow(x, y, str(k), font=T.FONT_BODY,
                                 fill=TEXT_DIM, anchor="w")
            self.app.text_shadow(x + 150, y, str(v), font=T.FONT_H2,
                                 fill=TEXT, anchor="e")

        # 解锁
        if self.new_unlocks:
            self.app.text_shadow(w / 2, sy + 130, "新成就解锁！",
                                 font=T.FONT_H2, fill=GOLD)
            for i, key in enumerate(self.new_unlocks[:4]):
                info = ACHIEVEMENTS.get(key, {})
                self.app.text_shadow(
                    w / 2, sy + 164 + i * 26,
                    "★ %s — %s" % (info.get("name", key),
                                   info.get("desc", "")),
                    font=T.FONT_BODY, fill=POISON)

        self.add_btn("again", (w / 2 - 320, h - 104, w / 2 - 40, h - 48),
                     "再来一局", self._again, color=GOLD)
        self.add_btn("menu", (w / 2 + 40, h - 104, w / 2 + 320, h - 48),
                     "返回主菜单", lambda: self.app.show("menu"),
                     color=TEXT_DIM, style="ghost")

    def _again(self) -> None:
        self.app.start_new_run()
        self.app.show("map")


# --------------------------------------------------------------------------- #
# 图鉴
# --------------------------------------------------------------------------- #
class CodexView(View):
    """手令 / 勋章 / 敌军 分页图鉴。"""

    PAGES = ("cards", "relics", "enemies")

    def on_build(self) -> None:
        self.page = str(self.kwargs.get("tab") or "cards")
        if self.page not in self.PAGES:
            self.page = "cards"
        self.filter = "all"
        self.scroll = 0
        self.selected = None
        self.hover_entry = None
        self.anim = 0.0

    def body(self) -> None:
        self.draw_bg("#2A2820", BG_DEEP)
        meta = self.app.meta_progress()
        total = self._total()
        seen = self._seen_count(meta)
        self.title("情 报 档 案", 50, "收集进度：%d / %d" % (seen, total), color=CYAN)
        self.add_btn("back", (24, 26, 150, 70), "◀ 返回",
                     lambda: self.app.show("menu"), color=TEXT_DIM,
                     style="ghost")
        x = 190
        for p, label in zip(self.PAGES, ("手令", "勋章", "敌军")):
            active = (self.page == p)
            self.add_btn("tab_" + p, (x, 26, x + 110, 70), label,
                         (lambda pp=p: self._set_page(pp)),
                         color=CYAN if active else TEXT_DIM,
                         style="solid" if active else "ghost")
            x += 120
        if self.page == "cards":
            self._card_filters(x)
        self._draw_grid(meta)
        self._draw_detail()

    def _card_filters(self, x0: float) -> None:
        filters = [("all", "全部"), ("attack", "攻击"), ("skill", "技能"),
                   ("power", "能力"), ("attack_arch", "突击"),
                   ("block", "防御"), ("poison", "燃烧弹"), ("energy", "后勤"),
                   ("summon", "支援")]
        x = x0 + 10
        for key, label in filters:
            active = (self.filter == key)
            if x + 82 > self.w - 20:
                break
            self.add_btn("flt_" + key, (x, 78, x + 78, 112), label,
                         (lambda k=key: self._set_filter(k)),
                         color=GOLD if active else TEXT_DIM,
                         style="solid" if active else "ghost",
                         font=T.FONT_TINY, radius=8)
            x += 84

    def _set_page(self, p: str) -> None:
        self.page = p
        self.scroll = 0
        self.selected = None
        self.app.redraw()

    def _set_filter(self, k: str) -> None:
        self.filter = k
        self.app.redraw()

    def _total(self) -> int:
        try:
            if self.page == "cards":
                from core.cards import CARD_DB  # type: ignore
                return len(CARD_DB)
            if self.page == "relics":
                from core.relics import RELIC_DB  # type: ignore
                return len(RELIC_DB)
            from core.enemies import ENEMY_DB  # type: ignore
            return len(ENEMY_DB)
        except Exception:
            return 0

    def _seen_count(self, meta) -> int:
        if meta is None:
            return 0
        return {"cards": len(_g(meta, "seen_cards", set()) or set()),
                "relics": len(_g(meta, "seen_relics", set()) or set()),
                "enemies": len(_g(meta, "seen_enemies", set()) or set())}[self.page]

    def _entries(self) -> List[Any]:
        try:
            if self.page == "cards":
                from core.cards import all_cards  # type: ignore
                items = list(all_cards())
                if self.filter == "all":
                    return items
                if self.filter in ("attack", "skill", "power"):
                    return [c for c in items if getattr(c, "type", "") == self.filter]
                return [c for c in items if getattr(c, "arch", "") == self.filter]
            if self.page == "relics":
                from core.relics import all_relics  # type: ignore
                return list(all_relics())
            from core.enemies import ENEMY_DB  # type: ignore
            return [ENEMY_DB[k] for k in sorted(ENEMY_DB)]
        except Exception:
            return []

    def _draw_grid(self, meta) -> None:
        items = self._entries()
        if not items:
            self.app.text_shadow(self.w / 2, self.h / 2,
                                 "图鉴数据尚未加载", font=T.FONT_H1,
                                 fill=TEXT_FAINT)
            return
        seen_set = set()
        if meta is not None:
            seen_set = set(_g(meta, "seen_cards" if self.page == "cards" else
                              ("seen_relics" if self.page == "relics"
                               else "seen_enemies"), set()) or set())
        self._seen_set = seen_set
        top = 128
        cw, ch, gap = 150, 62, 12
        cols = max(1, int((self.w - 460) // (cw + gap)))
        self._cols = cols
        for i, item in enumerate(items):
            r, col = divmod(i, cols)
            x = 40 + col * (cw + gap)
            y = top + r * (ch + gap) - self.scroll * (ch + gap)
            if y + ch < top - 10 or y > self.h - 40:
                continue
            iid = str(_g(item, "id", ""))
            known = (not seen_set) or (iid in seen_set)
            name = str(_g(item, "name", iid))
            hue = _rarity_color(str(_g(item, "rarity", "common")))
            hot = (self.hover_entry == i)
            self.app.round_rect(x, y, x + cw, y + ch, 8,
                                fill=_alpha_on(BG_DEEP, PANEL_HI if hot else PANEL,
                                               0.95),
                                outline=hue if known else BORDER,
                                width=2 if hot else 1)
            self.app.text_shadow(x + 10, y + 22,
                                 name if known else "？？？",
                                 font=T.FONT_BODY, fill=TEXT if known else
                                 TEXT_FAINT, anchor="w")
            sub = self._sub_label(item)
            self.app.text_shadow(x + 10, y + 44, sub if known else "未发现",
                                 font=T.FONT_TINY,
                                 fill=TEXT_DIM if known else TEXT_FAINT,
                                 anchor="w")
            if hot and known:
                self.selected = item
                self._detail_rect = (self.w - 400, top, self.w - 30,
                                     self.h - 40)

    def _sub_label(self, item) -> str:
        if self.page == "cards":
            cost = getattr(item, "cost", 0)
            return "%s费 · %s · %s" % ("X" if cost == -1 else cost,
                                       getattr(item, "type", ""),
                                       getattr(item, "rarity", ""))
        if self.page == "relics":
            return str(getattr(item, "rarity", ""))
        return "%s · HP %s-%s" % (getattr(item, "tier", ""),
                                  getattr(item, "hp_min", "?"),
                                  getattr(item, "hp_max", "?"))

    def _draw_detail(self) -> None:
        if self.page == "enemies":
            self._draw_enemy_detail()
            return
        item = self.selected
        x1, y1, x2, y2 = getattr(self, "_detail_rect",
                                 (self.w - 400, 128, self.w - 30, self.h - 40))
        self.app.round_rect(x1, y1, x2, y2, 14,
                            fill=_alpha_on(BG_DEEP, PANEL_LO, 0.95),
                            outline=BORDER_HI, width=2)
        if item is None:
            self.app.text_shadow((x1 + x2) / 2, (y1 + y2) / 2,
                                 "悬停查看详情", font=T.FONT_BODY,
                                 fill=TEXT_FAINT)
            return
        hue = _rarity_color(str(_g(item, "rarity", "common")))
        self.app.text_shadow(x1 + 20, y1 + 36, str(_g(item, "name", "")),
                             font=T.FONT_H1, fill=hue, anchor="w")
        ty = y1 + 74
        if self.page == "cards":
            drawer = None
            if W is not None:
                drawer = getattr(getattr(W, "CardView", None), "draw_on", None)
            if drawer is not None:
                try:
                    from core.cards import make_card  # type: ignore
                    drawer(self.c, x1 + 110, ty + 120, make_card(
                        str(_g(item, "id", ""))), scale=1.0, tags="codex")
                except Exception:
                    pass
            tx = x1 + 240
        else:
            tx = x1 + 20
        txt = str(_g(item, "text", "") or _g(item, "desc", ""))
        for i, ln in enumerate(self.app.wrap_text(txt, int(x2 - tx - 20),
                                                  T.FONT_BODY, max_lines=10)):
            self.app.text_shadow(tx, ty + i * 24, ln, font=T.FONT_BODY,
                                 fill=TEXT, anchor="w")

    def _draw_enemy_detail(self) -> None:
        item = self.selected
        x1, y1, x2, y2 = getattr(self, "_detail_rect",
                                 (self.w - 400, 128, self.w - 30, self.h - 40))
        self.app.round_rect(x1, y1, x2, y2, 14,
                            fill=_alpha_on(BG_DEEP, PANEL_LO, 0.95),
                            outline=BORDER_HI, width=2)
        if item is None:
            self.app.text_shadow((x1 + x2) / 2, (y1 + y2) / 2,
                                 "悬停查看敌人", font=T.FONT_BODY,
                                 fill=TEXT_FAINT)
            return
        self.app.text_shadow(x1 + 20, y1 + 36, str(_g(item, "name", "")),
                             font=T.FONT_H1, fill=BLOOD, anchor="w")
        info = "HP %s-%s · %s · 第 %s 幕" % (
            _g(item, "hp_min", "?"), _g(item, "hp_max", "?"),
            _g(item, "tier", "?"), _g(item, "act", "?"))
        self.app.text_shadow(x1 + 20, y1 + 70, info, font=T.FONT_BODY,
                             fill=TEXT_DIM, anchor="w")
        y = y1 + 104
        for ln in self.app.wrap_text(str(_g(item, "desc", "")),
                                     int(x2 - x1 - 40), T.FONT_BODY,
                                     max_lines=6):
            self.app.text_shadow(x1 + 20, y, ln, font=T.FONT_BODY, fill=TEXT,
                                 anchor="w")
            y += 24
        y += 10
        self.app.text_shadow(x1 + 20, y, "招式", font=T.FONT_H2, fill=CYAN,
                             anchor="w")
        y += 30
        for mv in list(_g(item, "moves", ()) or ())[:8]:
            self.app.text_shadow(x1 + 24, y,
                                 "%s（%s）" % (_g(mv, "name", "?"),
                                               _g(mv, "intent", "?")),
                                 font=T.FONT_BODY, fill=TEXT, anchor="w")
            self.app.text_shadow(x2 - 24, y,
                                 "伤害 %s × %s" % (_g(mv, "damage", 0),
                                                   _g(mv, "hits", 1)),
                                 font=T.FONT_TINY, fill=TEXT_DIM, anchor="e")
            y += 26
            if y > y2 - 30:
                break

    def on_motion_extra(self, x, y, prev) -> None:
        idxs = self._entry_at(x, y)
        if idxs != prev:
            self.app.redraw()
        self.hover_entry = idxs

    def _entry_at(self, x, y):
        cw, ch, gap = 150, 62, 12
        cols = max(1, getattr(self, "_cols", 6))
        if y < 128:
            return None
        col = int((x - 40) // (cw + gap))
        row = int((y - 128 + self.scroll * (ch + gap)) // (ch + gap))
        if col < 0 or col >= cols or row < 0:
            return None
        idx = row * cols + col
        items = self._entries()
        if idx < len(items):
            return idx
        return None

    def on_click_extra(self, x, y) -> None:
        idx = self._entry_at(x, y)
        if idx is not None:
            items = self._entries()
            if 0 <= idx < len(items):
                self.selected = items[idx]
                self.app.redraw()


# --------------------------------------------------------------------------- #
# 成就
# --------------------------------------------------------------------------- #
class AchievementsView(View):
    """成就墙。"""

    def on_build(self) -> None:
        self.scroll = 0
        self.anim = 0.0

    def body(self) -> None:
        self.draw_bg("#2A2418", BG_DEEP)
        meta = self.app.meta_progress()
        got = _g(meta, "achievements", {}) or {}
        total = len(ACHIEVEMENTS)
        unlocked = sum(1 for k in ACHIEVEMENTS if got.get(k))
        pct = (unlocked / total * 100) if total else 0.0
        self.title("勋 章 墙", 50, "%d / %d  （%.1f%%）" % (unlocked, total, pct),
                   color=GOLD)
        self.add_btn("back", (24, 26, 150, 70), "◀ 返回",
                     lambda: self.app.show("menu"), color=TEXT_DIM,
                     style="ghost")
        # 进度条
        bx, by, bw, bh = self.w / 2 - 260, 118, 520, 14
        self.app.round_rect(bx, by, bx + bw, by + bh, 7, fill="#150E22",
                            outline=BORDER, width=1)
        if pct > 0:
            self.app.round_rect(bx + 1, by + 1, bx + 1 + (bw - 2) * pct / 100.0,
                                by + bh - 1, 6, fill=GOLD, outline="")
        items = sorted(ACHIEVEMENTS.items(),
                       key=lambda kv: (not got.get(kv[0]), kv[0]))
        cols = 2
        cw = (self.w - 160) / cols
        for i, (key, info) in enumerate(items):
            r, col = divmod(i, cols)
            x = 60 + col * (cw + 20)
            y = 160 + r * 76
            if y > self.h - 60:
                continue
            ok = bool(got.get(key))
            col_hex = GOLD if ok else TEXT_FAINT
            self.app.round_rect(x, y, x + cw, y + 66, 10,
                                fill=_alpha_on(BG_DEEP, PANEL, 0.9 if ok else 0.5),
                                outline=col_hex, width=2 if ok else 1)
            self.c.create_oval(x + 14, y + 16, x + 48, y + 50,
                               fill=_alpha_on(BG_DEEP, col_hex, 0.25 if ok
                                              else 0.12),
                               outline=col_hex, width=2)
            self.app.text_shadow(x + 31, y + 33, "★" if ok else "☆",
                                 font=T.FONT_H2, fill=col_hex)
            self.app.text_shadow(x + 60, y + 26, str(info.get("name", key)),
                                 font=T.FONT_H2,
                                 fill=TEXT if ok else TEXT_FAINT, anchor="w")
            self.app.text_shadow(x + 60, y + 50, str(info.get("desc", "")),
                                 font=T.FONT_TINY,
                                 fill=TEXT_DIM if ok else TEXT_FAINT,
                                 anchor="w")


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
class StatsView(View):
    """生涯统计 + 排行榜。"""

    def on_build(self) -> None:
        self.anim = 0.0

    def body(self) -> None:
        self.draw_bg("#2C2820", BG_DEEP)
        meta = self.app.meta_progress()
        run = self.run
        self.title("战 报", 50, "你的作战记录", color=POISON)
        self.add_btn("back", (24, 26, 150, 70), "◀ 返回",
                     lambda: self.app.show("menu"), color=TEXT_DIM,
                     style="ghost")

        rows = [
            ("总战役数", int(_g(meta, "total_runs", 0) if meta else 0)),
            ("通关次数", int(_g(meta, "wins", 0) if meta else 0)),
            ("最高分", int(_g(meta, "best_score", 0) if meta else 0)),
            ("最高连胜", int(_g(meta, "best_streak", 0) if meta else 0)),
            ("已解锁战役难度", int(_g(meta, "ascension_unlocked", 0) if meta else 0)),
            ("已见手令", len(_g(meta, "seen_cards", set()) or set()) if meta else 0),
            ("已见勋章", len(_g(meta, "seen_relics", set()) or set()) if meta else 0),
            ("已见敌军", len(_g(meta, "seen_enemies", set()) or set()) if meta else 0),
        ]
        x0 = 80
        y0 = 150
        for i, (k, v) in enumerate(rows):
            r, col = divmod(i, 2)
            x = x0 + col * (self.w / 2 - 80)
            y = y0 + r * 62
            self.app.round_rect(x, y, x + 340, y + 50, 10,
                                fill=_alpha_on(BG_DEEP, PANEL, 0.85),
                                outline=BORDER, width=1)
            self.app.text_shadow(x + 18, y + 25, str(k), font=T.FONT_BODY,
                                 fill=TEXT_DIM, anchor="w")
            self.app.text_shadow(x + 322, y + 25, str(v), font=T.FONT_H2,
                                 fill=CYAN, anchor="e")

        # 当前局
        if run is not None:
            self.app.text_shadow(80, y0 + 4 * 62 + 20, "当前这一局",
                                 font=T.FONT_H1, fill=GOLD, anchor="w")
            cur = [("推进层数", _g(run, "floor", 0)), ("军费", _g(run, "gold", 0)),
                   ("手令", len(self.deck())), ("勋章", len(self.relics())),
                   ("种子", _g(run, "seed", 0)),
                   ("战役难度", _g(run, "ascension", 0))]
            for i, (k, v) in enumerate(cur):
                x = 80 + (i % 3) * 250
                y = y0 + 4 * 62 + 60 + (i // 3) * 30
                self.app.text_shadow(x, y, "%s：%s" % (k, v),
                                     font=T.FONT_BODY, fill=TEXT, anchor="w")

        # 排行榜
        board = list(_g(meta, "leaderboard", []) or []) if meta else []
        bx = self.w / 2 + 40
        by = 150
        self.app.round_rect(bx, by, self.w - 60, self.h - 60, 14,
                            fill=_alpha_on(BG_DEEP, PANEL_LO, 0.9),
                            outline=BORDER_HI, width=2)
        self.app.text_shadow(bx + 24, by + 34, "本地排行榜 Top 10",
                             font=T.FONT_H1, fill=GOLD, anchor="w")
        if not board:
            self.app.text_shadow(bx + 24, by + 90, "还没有记录，快去出征吧！",
                                 font=T.FONT_BODY, fill=TEXT_FAINT, anchor="w")
        for i, entry in enumerate(board[:10]):
            y = by + 80 + i * 40
            score = entry.get("score", 0) if isinstance(entry, dict) else entry
            who = entry.get("ascension", "") if isinstance(entry, dict) else ""
            won = entry.get("won", False) if isinstance(entry, dict) else False
            col = GOLD if i == 0 else (TEXT if i < 3 else TEXT_DIM)
            self.app.text_shadow(bx + 24, y, "%2d." % (i + 1),
                                 font=T.FONT_H2, fill=col, anchor="w")
            self.app.text_shadow(bx + 80, y, str(score), font=T.FONT_H2,
                                 fill=col, anchor="w")
            tag = "通关" if won else "阵亡"
            if who != "":
                tag += " · 战役难度 %s" % who
            self.app.text_shadow(self.w - 84, y, tag, font=T.FONT_TINY,
                                 fill=TEXT_DIM, anchor="e")


# --------------------------------------------------------------------------- #
# 设置
# --------------------------------------------------------------------------- #
class SettingsView(View):
    """音量 / 动画速度 / 难度显示 / 飘字开关 / 兑换码。"""

    def on_build(self) -> None:
        self.anim = 0.0
        self.dragging = None
        self.cheat_buf = ""            # 兑换码输入缓冲
        self.cheat_msg = ""            # 最近一次兑换结果
        self.cheat_ok = True
        self.cheat_focus = False

    def _s(self, key: str, default):
        return self.app.settings.get(key, default)

    def _set(self, key: str, value) -> None:
        self.app.settings[key] = value
        if key in ("volume", "music"):
            try:
                self.app.restart_music()
            except Exception:
                pass
        self.app.redraw()

    def body(self) -> None:
        self.draw_bg("#2E2A20", BG_DEEP)
        self.title("设 置", 54, "本地保存，立即生效", color=CYAN)
        self.add_btn("back", (24, 26, 150, 70), "◀ 返回",
                     lambda: self.app.show("menu"), color=TEXT_DIM,
                     style="ghost")

        x = self.w / 2 - 340
        y = 160
        bw = 680
        # 音量
        self._slider(x, y, bw, "音量", "volume", 0, 100,
                     "%d%%" % int(self._s("volume", 70)))
        y += 90
        # 动画速度
        self._slider(x, y, bw, "动画速度", "anim_speed", 0.5, 3.0,
                     "%.1fx" % float(self._s("anim_speed", 1.0)),
                     integer=False)
        y += 90
        # 飘字
        self._toggle(x, y, bw, "伤害飘字", "damage_numbers")
        y += 74
        # 难度显示
        self._toggle(x, y, bw, "显示战役难度", "show_difficulty")
        y += 74
        # 全屏
        self._toggle(x, y, bw, "全屏", "fullscreen")
        y += 74
        # 语言切换（中 / English）
        self._lang_row(x, y, bw)
        y += 74
        # 背景音乐
        self._toggle(x, y, bw, "背景音乐", "music")
        y += 62

        # ---- 曲目选择 ----
        self._music_section(x, y, bw)
        y += 118

        # ---- 兑换码 ----
        self._redeem_section(x, y, bw)
        y += 132

        # 关于
        self.app.round_rect(x, y, x + bw, y + 150, 14,
                            fill=_alpha_on(BG_DEEP, PANEL_LO, 0.9),
                            outline=BORDER, width=1)
        info = [
            "钢铁战线  Steel Frontline",
            "纯 Python 3 + Tkinter 8.5 · 零第三方依赖 · 零网络",
            "窗口 %dx%d（最小 %dx%d，可自由缩放）"
            % (self.app.WIDTH, self.app.HEIGHT, self.app.MIN_W, self.app.MIN_H),
            "全部美术（坦克/步兵/飞机/要塞/工事）均为程序化几何绘制",
        ]
        for i, ln in enumerate(info):
            self.app.text_shadow(x + 24, y + 34 + i * 28, ln,
                                 font=T.FONT_BODY if i == 0 else T.FONT_SMALL,
                                 fill=TEXT if i == 0 else TEXT_DIM, anchor="w")

        self.add_btn("reset", (self.w / 2 - 130, self.h - 74,
                               self.w / 2 + 130, self.h - 26),
                     "恢复默认设置", self._reset, color=TEXT_DIM,
                     style="ghost")

    # ---- 曲目选择 ---------------------------------------------------- #
    def _music_section(self, x: float, y: float, bw: float) -> None:
        """游戏内切歌：列出 music/ 里的全部曲目，点击即播。"""
        from core import audio
        try:
            tracks = audio.all_tracks()
        except Exception:
            tracks = []
        cur = getattr(self, "_music_sel", None)
        if cur is None:
            try:
                cur = audio.player().track
            except Exception:
                cur = None

        self.app.text_shadow(x, y + 12, "选择音乐", font=T.FONT_H1,
                             fill=GOLD, anchor="w")
        self.app.text_shadow(x + bw, y + 14,
                             "music/ 共 %d 首" % len(tracks),
                             font=T.FONT_SMALL, fill=TEXT_DIM, anchor="e")

        if not tracks:
            self.app.text_shadow(x, y + 46,
                                 "music/ 目录为空 —— 放入 mp3 后点此刷新",
                                 font=T.FONT_SMALL, fill=TEXT_FAINT,
                                 anchor="w")
            self.add_btn("mus_refresh", (x + bw - 150, y + 32,
                                         x + bw - 80, y + 64),
                         "刷新", self._music_open_dir, color=TEXT_DIM,
                         style="ghost", font=T.FONT_SMALL)
            self.add_btn("mus_dir", (x + bw - 74, y + 32,
                                     x + bw, y + 64),
                         "打开目录", self._music_reveal_dir,
                         color=CYAN, style="ghost", font=T.FONT_SMALL)
            return

        # 曲目按钮：每行 3 个
        per_row = 3
        bwid = (bw - 16) / per_row
        for i, t in enumerate(tracks[:6]):
            r, c = divmod(i, per_row)
            bx = x + c * (bwid + 8)
            by = y + 34 + r * 38
            is_cur = (cur == t["path"])
            label = t["file"][:16]
            self.add_btn("mus_%d" % i,
                         (bx, by, bx + bwid, by + 32),
                         ("♪ " if is_cur else "") + label,
                         (lambda pp=t["path"]: self._music_play(pp)),
                         color=GOLD if is_cur else TEXT_DIM,
                         style="solid" if is_cur else "ghost",
                         font=T.FONT_SMALL,
                         tip="点击播放并循环")

        # 上一首 / 下一首 / 打开目录
        cy = y + 34 + ((min(len(tracks), 6) - 1) // per_row + 1) * 38
        self.add_btn("mus_prev", (x, cy, x + 96, cy + 30), "◀ 上一首",
                     lambda: self._music_step(-1), color=TEXT_DIM,
                     style="ghost", font=T.FONT_SMALL)
        self.add_btn("mus_next", (x + 102, cy, x + 198, cy + 30), "下一首 ▶",
                     lambda: self._music_step(1), color=TEXT_DIM,
                     style="ghost", font=T.FONT_SMALL)
        self.add_btn("mus_dir", (x + bw - 110, cy, x + bw, cy + 30),
                     "打开目录", self._music_reveal_dir, color=CYAN,
                     style="ghost", font=T.FONT_SMALL)

    def _music_play(self, path: str) -> None:
        from core import audio
        ok = audio.play_file(path)
        self._music_sel = path
        self.app.pop_text(self.w / 2, 120,
                          ("正在播放：%s" % os.path.basename(path)) if ok
                          else "播放失败：文件不可读",
                          color=GOLD if ok else BLOOD, size=16)
        self.app.redraw()

    def _music_step(self, step: int) -> None:
        from core import audio
        cur = getattr(self, "_music_sel", None)
        if cur is None:
            try:
                cur = audio.player().track
            except Exception:
                cur = None
        nxt = audio.next_track(cur, step)
        if nxt:
            self._music_play(nxt)

    def _music_reveal_dir(self) -> None:
        """在访达里打开 music/ 目录（方便拖文件进去）。"""
        from core import audio
        d = audio.music_dir()
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        try:
            if sys.platform == "darwin":
                os.system('open "%s"' % d)
            elif os.name == "nt":
                os.startfile(d)  # type: ignore[attr-defined]
            else:
                os.system('xdg-open "%s" >/dev/null 2>&1 &' % d)
        except Exception:
            pass
        self.app.redraw()

    # 空目录时的「刷新」= 重新扫描并打开目录
    def _music_open_dir(self) -> None:
        self._music_sel = None
        self._music_reveal_dir()

    # ---- 兑换码 ------------------------------------------------------ #
    def _redeem_section(self, x: float, y: float, bw: float) -> None:
        """兑换码输入区。纯 Canvas 绘制，支持键盘输入。

        神人模式下禁用：这里直接显示红色提示并**不画输入框**，
        免得玩家输了半天以为是码不对。
        """
        from core import cheats as CH

        god = False
        try:
            god = bool(CH.CheatRegistry.is_god_mode(run=self.app.run))
        except Exception:
            god = False

        self.app.text_shadow(x, y + 14, "兑换码", font=T.FONT_H1,
                             fill=(TEXT_DIM if god else GOLD), anchor="w")
        if god:
            self.app.round_rect(x, y + 34, x + bw, y + 88, 10,
                                fill=_alpha_on(BG_DEEP, BLOOD, 0.18),
                                outline=BLOOD, width=1)
            self.app.text_shadow(
                x + bw / 2, y + 52, "神人模式 —— 作弊已禁用",
                font=T.FONT_BODY, fill=BLOOD)
            self.app.text_shadow(
                x + bw / 2, y + 74, "这是最高难度的荣誉挑战，兑换码与调试指令全部失效。",
                font=T.FONT_TINY, fill=TEXT_DIM)
            return
        self.app.text_shadow(x + bw, y + 14,
                             "已用 %d 次" % sum(
                                 (self._cheat_reg().used or {}).values()),
                             font=T.FONT_SMALL, fill=TEXT_DIM, anchor="e")

        iy = y + 34
        ih = 46
        # 输入框
        self.app.round_rect(x, iy, x + bw - 130, iy + ih, 10,
                            fill=_alpha_on(BG_DEEP, PANEL_LO, 0.95),
                            outline=CYAN if self.cheat_focus else BORDER,
                            width=2 if self.cheat_focus else 1)
        shown = self.cheat_buf if self.cheat_buf else ""
        if shown:
            self.app.text_shadow(x + 16, iy + ih / 2, shown,
                                 font=T.FONT_H2, fill=TEXT, anchor="w")
        else:
            self.app.text_shadow(x + 16, iy + ih / 2,
                                 "输入兑换码，例如 manpower",
                                 font=T.FONT_BODY, fill=TEXT_FAINT,
                                 anchor="w")
        # 光标
        if self.cheat_focus and (self.anim * 2) % 2 < 1:
            tw = len(shown) * 11 + 18
            self.c.create_line(x + tw, iy + 12, x + tw, iy + ih - 12,
                               fill=CYAN, width=2)

        self.add_btn("cheat_go", (x + bw - 118, iy, x + bw, iy + ih),
                     "兑换", self._redeem_submit, color=CYAN,
                     style="solid" if self.cheat_buf else "ghost")
        self.add_btn("cheat_clear", (x + bw - 118 - 82, iy + ih + 8,
                                     x + bw - 118 - 8, iy + ih + 42),
                     "清空", self._redeem_clear, color=TEXT_DIM,
                     style="ghost", font=T.FONT_SMALL)

        # 结果提示
        if self.cheat_msg:
            self.app.text_shadow(x, iy + ih + 26, self.cheat_msg,
                                 font=T.FONT_SMALL,
                                 fill=GREEN if self.cheat_ok else RED,
                                 anchor="w")
        else:
            self.app.text_shadow(x, iy + ih + 26,
                                 "在设置里兑换特殊指令（部分码每局限一次）",
                                 font=T.FONT_SMALL, fill=TEXT_FAINT,
                                 anchor="w")

    def _cheat_reg(self):
        """取得（或懒创建）兑换码注册表。"""
        reg = getattr(self.app, "cheat_reg", None)
        if reg is None:
            from core import cheats as CH
            reg = CH.CheatRegistry()
            self.app.cheat_reg = reg
        return reg

    def _redeem_submit(self) -> None:
        code = (self.cheat_buf or "").strip()
        if not code:
            self.cheat_msg = "请输入兑换码。"
            self.cheat_ok = False
            self.app.redraw()
            return
        reg = self._cheat_reg()
        ok, msg = reg.redeem(code, run=self.app.run,
                             battle=self.app.battle,
                             meta=getattr(self.app, "meta", None))
        self.cheat_ok = ok
        self.cheat_msg = msg
        self.cheat_buf = ""
        if ok:
            self.app.pop_text(self.w / 2, self.h / 2 - 120, msg,
                              color=GOLD, size=20)
        self.app.redraw()

    def _redeem_clear(self) -> None:
        self.cheat_buf = ""
        self.cheat_msg = ""
        self.app.redraw()

    def _cheat_key(self, event) -> None:
        """键盘输入处理（仅在设置界面且输入框聚焦时生效）。"""
        if not self.cheat_focus:
            return
        k = getattr(event, "keysym", "")
        ch = getattr(event, "char", "")
        if k == "BackSpace":
            self.cheat_buf = self.cheat_buf[:-1]
        elif k == "Return" or k == "KP_Enter":
            self._redeem_submit()
            return
        elif k == "Escape":
            self.cheat_focus = False
        elif ch and ch.isprintable() and len(self.cheat_buf) < 24:
            self.cheat_buf += ch
        else:
            return
        self.app.redraw()

    def on_click_extra(self, x: float, y: float) -> None:
        """点击输入框区域时聚焦。"""
        bw = 680
        bx = self.w / 2 - 340
        iy = 160 + 74 + 74 + 74 + 74 + 34      # 与 body() 的 y 累加一致
        hit = (bx <= x <= bx + bw - 130 and iy <= y <= iy + 46)
        if hit != self.cheat_focus:
            self.cheat_focus = hit
            self.app.redraw()

    def _slider(self, x, y, bw, label, key, lo, hi, shown, integer=True):
        self.app.text_shadow(x, y, label, font=T.FONT_H1, fill=TEXT,
                             anchor="w")
        self.app.text_shadow(x + bw, y, shown, font=T.FONT_H1, fill=GOLD,
                             anchor="e")
        ty = y + 32
        self.app.round_rect(x, ty, x + bw, ty + 14, 7, fill="#0A1620",
                            outline=BORDER, width=1)
        val = float(self._s(key, lo))
        frac = 0.0 if hi == lo else max(0.0, min(1.0, (val - lo) / (hi - lo)))
        if frac > 0:
            self.app.round_rect(x + 1, ty + 1, x + 1 + (bw - 2) * frac,
                                ty + 13, 6, fill=CYAN, outline="")
        hx = x + frac * bw
        self.c.create_oval(hx - 13, ty + 7 - 13, hx + 13, ty + 7 + 13,
                           fill=_alpha_on(BG_DEEP, PANEL_HI, 1.0),
                           outline=CYAN, width=2)
        self.add_btn("sl_" + key, (x, ty - 12, x + bw, ty + 26), "", 
                     (lambda k=key, a=lo, b=hi, i=integer:
                      self._nudge(k, a, b, i, 0.05)),
                     color=BG_DEEP, style="ghost")
        self._track = getattr(self, "_track", {})
        self._track[key] = (x, ty + 7, bw, lo, hi, integer)

    def _nudge(self, key, lo, hi, integer, step) -> None:
        """点击滑轨：按点击位置设置；这里用中点近似 + 微调。"""
        cur = float(self._s(key, lo))
        span = hi - lo
        nxt = cur + span * 0.1
        if nxt > hi + 1e-6:
            nxt = lo
        self._set(key, int(round(nxt)) if integer else round(nxt, 2))

    def _lang_row(self, x, y, bw) -> None:
        """语言切换行：点一下在中/英之间切换。"""
        try:
            from core import i18n as _i
            cur = _i.lang()
            name = _i.LANG_NAMES.get(cur, cur)
        except Exception:
            cur, name = "zh", "中文"
        self.app.text_shadow(x, y + 14, "语言 / Language", font=T.FONT_H1,
                             fill=TEXT, anchor="w")
        tx = x + bw - 150
        self.app.round_rect(tx, y, tx + 150, y + 40, 20,
                            fill=_alpha_on(BG_DEEP, GOLD, 0.9),
                            outline=GOLD, width=2)
        self.app.text_shadow(tx + 75, y + 20, "%s ▸" % name,
                             font=T.FONT_BODY, fill=BG_DEEP)
        self.add_btn("tg_lang", (tx, y, tx + 150, y + 40), "",
                     self._cycle_lang,
                     tip="切换界面语言：中文 / English。\n立即生效。",
                     tip_title="语言")

    def _cycle_lang(self) -> None:
        """切换语言并立即重绘（所有界面文字都会跟着变）。"""
        try:
            from core import i18n as _i
            new = _i.toggle_lang()
        except Exception:
            return
        # 记住选择，下次启动沿用
        try:
            from ui.app import _save_pref
            _save_pref("lang", new)
        except Exception:
            pass
        # 语言变了要刷新字体（英文用不同字号更协调）
        try:
            self.app.refresh_fonts()
        except Exception:
            pass
        self.app.redraw()

    def _toggle(self, x, y, bw, label, key) -> None:
        on = bool(self._s(key, False))
        self.app.text_shadow(x, y + 14, label, font=T.FONT_H1, fill=TEXT,
                             anchor="w")
        tx = x + bw - 90
        self.app.round_rect(tx, y, tx + 90, y + 40, 20,
                            fill=_alpha_on(BG_DEEP, CYAN if on else PANEL, 0.9),
                            outline=CYAN if on else BORDER, width=2)
        kx = tx + 66 if on else tx + 24
        self.c.create_oval(kx - 16, y + 4, kx + 16, y + 36,
                           fill=BG_DEEP if on else TEXT_DIM, outline="")
        self.app.text_shadow(tx + 45, y + 20, "开" if on else "关",
                             font=T.FONT_TINY, fill=TEXT if on else TEXT_DIM)
        self.add_btn("tg_" + key, (tx, y, tx + 90, y + 40), "",
                     (lambda k=key: self._set(k, not bool(self._s(k, False)))),
                     color=BG_DEEP, style="ghost")

    def _reset(self) -> None:
        self.app.settings.update({
            "volume": 70, "music": True, "anim_speed": 1.0, "show_difficulty": True,
            "fullscreen": False, "damage_numbers": True})
        self.app.pop_text(self.w / 2, self.h - 110, "已恢复默认",
                          color=POISON, size=20)
        self.app.redraw()

    def on_click_extra(self, x, y) -> None:
        # 直接点击滑轨定位
        for key, (tx, ty, bw, lo, hi, integer) in getattr(self, "_track",
                                                          {}).items():
            if tx <= x <= tx + bw and ty - 16 <= y <= ty + 16:
                frac = max(0.0, min(1.0, (x - tx) / bw))
                val = lo + frac * (hi - lo)
                self._set(key, int(round(val)) if integer else round(val, 2))
                return


# --------------------------------------------------------------------------- #
# 注册表
# --------------------------------------------------------------------------- #
SCREEN_CLASSES: Dict[str, Callable] = {
    "menu": MenuView,
    "reward": RewardView,
    "shop": ShopView,
    "rest": RestView,
    "event": EventView,
    "treasure": TreasureView,
    "deck": DeckView,
    "gameover": GameOverView,
    "codex": CodexView,
    "stats": StatsView,
    "settings": SettingsView,
    "achievements": AchievementsView,
}
