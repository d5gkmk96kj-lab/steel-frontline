"""
钢铁战线 — 可复用控件层 (widgets.py)
================================================================
全部基于 ``tk.Canvas`` **程序化手绘**，不依赖任何图片文件、不依赖第三方库。

依赖：仅标准库 ``tkinter`` + 本包 :mod:`ui.theme`。
本模块可脱离项目其它模块单独 import；无 Tk root 时 import 也不抛异常。

动画纪律
--------
* **绝不用** ``time.sleep`` 阻塞主线程；一律 ``widget.after(ms, cb)``。
* 每个会自跑的控件都提供 ``destroy()`` 重写，销毁时取消挂起的 after 回调。

控件清单
--------
``Tooltip``      延迟悬浮提示（跟随鼠标、自动避让屏幕边界）
``CardView``     卡牌渲染（可画在任意 Canvas 的任意位置/缩放）
``RelicView``    勋章/装备图标（按 id hash 程序化生成几何图形）
``BuffBadge``    Buff 图标 + 层数（带 tooltip）
``HPBar``        血条（含延迟掉血白色残影动画）
``EnergyOrb``    补给球（能量 cur/max + 呼吸光晕）
``FancyButton``  圆角按钮（悬停变色 + 按下凹陷）
``ScrollFrame``  可滚动容器（Canvas + Scrollbar + 滚轮，兼容 macOS）
``DamageNumber`` 飘字动画对象
``IntentBadge``  敌人意图图标（附加，供战斗界面使用）
``BlockShield``  掩体盾徽（附加）
``PileButton``   牌库/弃牌堆计数器按钮（附加）
``set_tooltip``  给任意 widget 挂 tooltip 的便捷函数
================================================================
"""

from __future__ import annotations

import math
import random
import tkinter as tk
from tkinter import ttk

from . import theme as T

__all__ = [
    "Tooltip", "set_tooltip",
    "CardView", "RelicView", "BuffBadge", "HPBar", "EnergyOrb",
    "FancyButton", "ScrollFrame", "DamageNumber",
    "IntentBadge", "BlockShield", "PileButton", "PipBar",
]


# =====================================================================
# 常量
# =====================================================================

TOOLTIP_DELAY = 250         # ms，契约规定
TOOLTIP_PAD = 10
TOOLTIP_OFFSET = (16, 22)   # 相对鼠标的偏移
TOOLTIP_MAX_W = 300

_DEFAULT_ROOT_TAG = "_steel_tooltip_mgr"


# =====================================================================
# 0. 小工具
# =====================================================================

def _cancel(widget, attr):
    """取消 widget 上挂起的 after 回调（安全，可重复调用）。"""
    aid = getattr(widget, attr, None)
    if aid:
        try:
            widget.after_cancel(aid)
        except Exception:
            pass
        try:
            setattr(widget, attr, None)
        except Exception:
            pass


def _alive(widget):
    try:
        return bool(widget.winfo_exists())
    except Exception:
        return False


def _defn_of(card):
    """从 CardInstance 或 CardDef 里取出 CardDef；失败返回 None。"""
    for attr in ("defn", "definition"):
        try:
            d = getattr(card, attr)
        except Exception:
            continue
        if d is not None and not callable(d):
            return d
    return card


def _field(obj, name, default=None):
    if obj is None:
        return default
    try:
        v = getattr(obj, name)
    except Exception:
        return default
    return default if v is None else v


# =====================================================================
# 1. Tooltip
# =====================================================================

class Tooltip:
    """延迟 250ms 显示的浮动提示。

    特性
    ----
    * **延迟**：悬停满 ``delay`` 毫秒才出现（默认 250ms，符合架构契约）。
    * **跟随鼠标**：``<Motion>`` 时实时移动。
    * **自动避让屏幕边界**：先按理想位置放置，再 ``winfo_screenwidth/height``
      夹紧，必要时翻到鼠标另一侧。
    * 使用 ``overrideredirect(True)`` 无边框 ``Toplevel``，可跨 widget 复用。

    用法::

        tp = Tooltip(anchor_widget, "对目标造成 6 点伤害。")
        tp.set_text("新的说明")      # 动态改文本
        tp.configure(wraplength=240)

    也支持动态文本回调：``Tooltip(w, lambda: card.defn.text)``。
    """

    _instances = []

    def __init__(self, widget, text="", delay=TOOLTIP_DELAY, wraplength=TOOLTIP_MAX_W,
                 font=None, bg=None, fg=None, follow=True, offset=TOOLTIP_OFFSET,
                 max_lines=None, padding=TOOLTIP_PAD):
        self.widget = widget
        self._text = text
        self.delay = int(delay)
        self.wraplength = int(wraplength)
        self.font = font or T.FONT_SMALL
        self.bg = bg or T.PANEL_LO
        self.fg = fg or T.TEXT
        self.follow = bool(follow)
        self.offset = offset
        self.max_lines = max_lines
        self.padding = int(padding)

        self._after_id = None
        self._tip = None
        self._tip_canvas = None
        self._tip_text_id = None
        self._visible = False
        self._last_xy = (0, 0)

        self._bind(widget)
        Tooltip._instances.append(self)

    # -- 文案 ----------------------------------------------------------
    def get_text(self):
        t = self._text
        if callable(t):
            try:
                t = t()
            except Exception:
                t = ""
        return "" if t is None else str(t)

    def set_text(self, text):
        """更新提示文本；若正在显示则立即重绘。"""
        self._text = text
        if self._visible:
            self._render()
        return self

    # 兼容别名
    text = property(get_text, set_text)

    def configure(self, **kw):
        for k, v in kw.items():
            if k == "text":
                self._text = v
            elif hasattr(self, k):
                setattr(self, k, v)
        if self._visible:
            self._render()
        return self

    config = configure

    # -- 事件 ----------------------------------------------------------
    def _bind(self, w):
        w.bind("<Enter>", self._on_enter, add="+")
        w.bind("<Leave>", self._on_leave, add="+")
        w.bind("<Motion>", self._on_motion, add="+")
        w.bind("<ButtonPress>", self._on_leave, add="+")
        w.bind("<Destroy>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._schedule()

    def _on_motion(self, event=None):
        if event is not None:
            self._last_xy = (event.x_root, event.y_root)
        if self._visible and self.follow:
            self._place()
        elif not self._visible and self._after_id is None:
            self._schedule()

    def _on_leave(self, event=None):
        self.hide()

    def _schedule(self):
        self._cancel()
        if not self.get_text():
            return
        try:
            self._after_id = self.widget.after(self.delay, self._show)
        except Exception:
            self._after_id = None

    def _cancel(self):
        _cancel(self, "_after_id")

    # -- 显示/隐藏 -----------------------------------------------------
    def _show(self):
        self._after_id = None
        if not _alive(self.widget):
            return
        txt = self.get_text()
        if not txt:
            return
        try:
            self._last_xy = (self.widget.winfo_pointerx(), self.widget.winfo_pointery())
        except Exception:
            pass
        if self._tip is None or not _alive(self._tip):
            self._build()
        self._render()
        self._visible = True
        try:
            self._tip.deiconify()
            self._tip.lift()
        except Exception:
            pass
        self._place()

    def hide(self):
        self._cancel()
        self._visible = False
        if self._tip is not None:
            try:
                self._tip.withdraw()
            except Exception:
                pass

    # -- 绘制 ----------------------------------------------------------
    def _build(self):
        top = tk.Toplevel(self.widget)
        top.withdraw()
        top.overrideredirect(True)
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        try:
            top.configure(bg=T.CYAN_DIM)
        except Exception:
            pass
        cv = tk.Canvas(top, bg=self.bg, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True, padx=1, pady=1)
        self._tip = top
        self._tip_canvas = cv
        self._tip_text_id = None

    def _render(self):
        cv = self._tip_canvas
        if cv is None:
            return
        txt = self.get_text()
        avail = max(40, self.wraplength - self.padding * 2)
        lines = T.wrap_text_cjk(txt, avail, self.font, max_lines=self.max_lines)
        if not lines:
            lines = [""]
        lh = int(self.font[1] * 1.45) + 2
        w = max(T.text_size(ln, self.font)[0] for ln in lines) + self.padding * 2
        w = min(max(w, 60), self.wraplength)
        h = lh * len(lines) + self.padding * 2
        cv.configure(width=w, height=h)
        cv.delete("all")
        # 一条青色顶边，作为视觉标识
        cv.create_rectangle(0, 0, w, 2, fill=T.CYAN, outline="")
        for i, ln in enumerate(lines):
            cv.create_text(self.padding, self.padding + lh * i,
                           text=ln, font=self.font, fill=self.fg, anchor="nw")
        try:
            self._tip.update_idletasks()
        except Exception:
            pass
        self._tip_w = w
        self._tip_h = h

    def _place(self):
        if self._tip is None:
            return
        mx, my = self._last_xy
        w = getattr(self, "_tip_w", 200)
        h = getattr(self, "_tip_h", 40)
        x = mx + self.offset[0]
        y = my + self.offset[1]
        try:
            sw = self._tip.winfo_screenwidth()
            sh = self._tip.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        # 自动避让屏幕边界
        if x + w > sw - 4:
            x = mx - w - self.offset[0]
        if y + h > sh - 4:
            y = my - h - self.offset[1] // 2
        x = max(4, min(x, max(4, sw - w - 4)))
        y = max(4, min(y, max(4, sh - h - 4)))
        try:
            self._tip.geometry("+%d+%d" % (int(x), int(y)))
        except Exception:
            pass

    def destroy(self):
        self.hide()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
        try:
            Tooltip._instances.remove(self)
        except ValueError:
            pass


#: 供外部类型检查/清理用
Tooltip.TYPE = Tooltip


def set_tooltip(widget, text, **kw):
    """给任意 widget 挂一个 Tooltip，返回该 Tooltip。"""
    return Tooltip(widget, text, **kw)


# =====================================================================
# 2. CardView
# =====================================================================

class CardView(tk.Canvas):
    """卡牌控件。

    两种用法
    --------
    1. **独立控件**（牌组界面/奖励界面）::

           cv = CardView(parent, card, width=CARD_W, height=CARD_H)
           cv.pack()
           cv.set_hover(True)      # 悬停放大上浮
           cv.set_disabled(True)   # 灰显（费用不足）

    2. **画到别人的 Canvas 上**（战斗界面手牌弧线动画）::

           items = CardView.draw_on(main_canvas, x, y, card_obj,
                                    scale=1.05, angle=-6.0, tags="hand")

       ``draw_on`` 是 **classmethod**，不需要先创建控件，也不要求目标
       Canvas 是 CardView。所有图形都在 ``(x, y)`` 指定的**中心点**周围绘制，
       并以 ``scale`` 缩放、以 ``angle`` 度旋转（Tk < 8.6 时用坐标旋转近似）。

    参数
    ----
    card : CardInstance | CardDef | None
        传 ``None`` 时显示一张占位空卡（用于动画/动画占位）。
    playable / disabled : bool
        不可打出时整体灰显 + 名称变暗。
    show_tooltip : bool
        独立控件模式下悬停是否弹 tooltip。
    """

    # 卡面内部布局（以卡牌中心为原点，未缩放的设计单位）
    _PAD = 9

    def __init__(self, parent, card=None, width=None, height=None, scale=1.0,
                 show_tooltip=True, playable=True, disabled=False,
                 command=None, bg=None, highlightthickness=0, **kw):
        w = int(width if width is not None else T.CARD_W * scale)
        h = int(height if height is not None else T.CARD_H * scale)
        try:
            super().__init__(parent, width=w, height=h, bg=bg or T.BG,
                             highlightthickness=highlightthickness, bd=0, **kw)
        except tk.TclError:      # pragma: no cover
            super().__init__(parent, width=w, height=h)
        self._card = card
        self._scale = float(scale)
        self._base_w = T.CARD_W * self._scale
        self._base_h = T.CARD_H * self._scale
        self._hover = False
        self._disabled = bool(disabled)
        self._playable = bool(playable)
        self._selected = False
        self._lift = 0.0
        self._anim_id = None
        self._command = command
        self._tooltip = None
        self._tags_own = "cardview_%d" % id(self)

        self.bind("<Configure>", self._on_configure)
        if command is not None:
            self.bind("<Button-1>", self._on_click)
            self.bind("<Enter>", lambda e: self.configure(cursor="hand2"), add="+")
            self.bind("<Leave>", lambda e: self.configure(cursor=""), add="+")
        if show_tooltip:
            self._tooltip = Tooltip(self, self._tooltip_text,
                                    wraplength=int(T.CARD_W * 1.55),
                                    max_lines=9)

    # ---------------------------------------------------------------- data
    @property
    def card(self):
        return self._card

    def set_card(self, card):
        self._card = card
        self.redraw()
        return self

    def _tooltip_text(self):
        d = _defn_of(self._card)
        if d is None:
            return ""
        name = _field(d, "name", "?")
        ctype = _field(d, "type", "")
        arch = _field(d, "arch", "")
        rarity = _field(d, "rarity", "")
        text = _field(d, "text", "")
        tname = T.TYPE_NAMES.get(ctype, ctype)
        aname = T.ARCH_NAMES.get(arch, arch)
        rname = T.RARITY_NAMES.get(rarity, rarity)
        return "%s\n%s · %s · %s\n%s" % (name, tname, aname, rname, text)

    # ---------------------------------------------------------------- state
    def set_hover(self, on):
        """悬停：放大并上浮。``on=True/False``。"""
        on = bool(on)
        if on == self._hover:
            return self
        self._hover = on
        self._animate_lift(T.HAND_HOVER_LIFT if on else 0.0)
        return self

    def set_disabled(self, on):
        """灰显（如费用不足）。"""
        on = bool(on)
        if on != self._disabled:
            self._disabled = on
            self.redraw()
        return self

    def set_playable(self, on):
        return self.set_disabled(not bool(on))

    def set_selected(self, on):
        self._selected = bool(on)
        self.redraw()
        return self

    def set_command(self, fn):
        self._command = fn
        return self

    def _on_click(self, event=None):
        if self._disabled:
            return
        if self._command:
            try:
                self._command(self)
            except Exception:
                pass

    def _on_configure(self, event=None):
        self.redraw()

    # ------------------------------------------------------------ animation
    def _animate_lift(self, target, step=5.0):
        """用 after() 平滑逼近目标上浮量，不阻塞主线程。"""
        _cancel(self, "_anim_id")
        self._anim_id = None

        def tick():
            self._anim_id = None
            d = target - self._lift
            if abs(d) <= step:
                self._lift = target
            else:
                self._lift += step if d > 0 else -step
            self.redraw()
            if abs(target - self._lift) > 0.01:
                try:
                    self._anim_id = self.after(16, tick)
                except Exception:
                    self._anim_id = None
        tick()

    # ---------------------------------------------------------------- draw
    def redraw(self):
        """重绘整个控件（独立控件模式）。"""
        if not _alive(self):
            return
        self.delete("all")
        try:
            w = self.winfo_width()
            h = self.winfo_height()
        except Exception:
            w = h = 0
        if w <= 1 or h <= 1:
            w, h = int(self._base_w), int(self._base_h)
        # 留出上浮空间：内容整体向下偏移，hover 时向上
        cx = w / 2.0
        cy = h / 2.0 + self._lift * 0.0 + 0.0
        s = self._base_w / float(T.CARD_W)
        if self._hover:
            s *= T.HAND_HOVER_SCALE
        y = h / 2.0 - self._lift + (T.CARD_H * s - h) / 2.0 * 0 - 0
        self.draw_on(self, cx, y, self._card, scale=s,
                     playable=self._playable and not self._disabled,
                     hover=self._hover, selected=self._selected,
                     disabled=self._disabled, tags=self._tags_own)

    # 兼容名字
    draw = redraw

    # ------------------------------------------------------- static painter
    @classmethod
    def draw_on(cls, canvas, cx, cy, card=None, scale=1.0, angle=0.0,
                playable=True, hover=False, selected=False, disabled=False,
                tags=None, base_bg=None, glow=True):
        """把一张卡画在**任意 Canvas** 上的 ``(cx, cy)`` 中心，返回 item id 列表。

        参数
        ----
        canvas : tk.Canvas            目标画布
        cx, cy : float                卡牌中心坐标
        card   : CardInstance|CardDef|None
        scale  : float                缩放（1.0 = 168x236）
        angle  : float                旋转角（度，正=逆时针）
        playable / disabled : bool    灰显控制
        selected / hover : bool       发光强调
        tags   : str|tuple            给所有 item 打 tag，方便整组删除/移动
        glow   : bool                 是否画稀有度外发光（大量卡时可关掉省性能）

        说明：Tk 8.5 的 ``create_polygon`` 不支持 ``angle``，因此画到**外部**
        Canvas 时一律用 ``_rotate`` 坐标变换近似旋转；只有画在自身控件里且
        角度为 0 时才最精确。
        """
        items = []
        s = float(scale)
        W = T.CARD_W * s
        H = T.CARD_H * s
        x1, y1, x2, y2 = cx - W / 2.0, cy - H / 2.0, cx + W / 2.0, cy + H / 2.0
        rad = math.radians(angle)

        def P(px, py):
            """设计坐标（相对卡牌中心、未缩放）-> 画布坐标。"""
            sx, sy = px * s, py * s
            if angle:
                ca, sa = math.cos(rad), math.sin(rad)
                sx, sy = sx * ca - sy * sa, sx * sa + sy * ca
            return cx + sx, cy + sy

        def rot_pts(flat):
            """一串画布坐标点整体绕中心旋转。"""
            if not angle:
                return list(flat)
            ca, sa = math.cos(rad), math.sin(rad)
            out = []
            for i in range(0, len(flat), 2):
                dx, dy = flat[i] - cx, flat[i + 1] - cy
                out.extend((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
            return out

        def add(item):
            items.append(item)
            if tags:
                try:
                    canvas.addtag_withtag(tags, item)
                except Exception:
                    pass
            return item

        d = _defn_of(card)
        rar = (_field(d, "rarity", "common") or "common")
        rcol = T.rarity_color(rar)
        ctype = _field(d, "type", "skill") or "skill"
        tcol = T.type_color(ctype)
        arch = _field(d, "arch", None)
        acol = T.arch_color(arch) if arch else tcol
        gray = (not playable) or disabled

        def C(color):
            """灰显时把所有颜色降饱和度（朝灰蓝混合）。"""
            if not gray:
                return color
            return T.lerp_color(color, "#55606B", 0.62)

        R = T.CARD_RADIUS * s
        bg_base = base_bg or T.BG

        # --- 阴影 ------------------------------------------------------
        if glow:
            for i in range(3, 0, -1):
                off = (T.SHADOW_SPREAD * s) * (i / 3.0) * 0.6
                col = T.with_alpha_on(bg_base, "#000000", 0.30 / i + 0.10)
                add(canvas.create_polygon(
                    rot_pts(T.round_rect_points(x1 - off * .4, y1 + off * .5,
                                                x2 + off * .4, y2 + off * .9,
                                                R + off * .5)),
                    fill=col, outline="", smooth=True, splinesteps=8))

        # --- 稀有度外发光 ----------------------------------------------
        if glow and rar not in ("basic", "common"):
            for i in range(3, 0, -1):
                f = i / 3.0
                gcol = T.with_alpha_on(bg_base, rcol, 0.12 + 0.20 * (1 - f))
                add(canvas.create_polygon(
                    rot_pts(T.round_rect_points(x1 - 5 * s * f, y1 - 5 * s * f,
                                                x2 + 5 * s * f, y2 + 5 * s * f,
                                                R + 5 * s * f)),
                    fill="", outline=gcol, width=max(1, int(3 * s * (1 - f) + 1)),
                    smooth=True, splinesteps=8))

        # --- 卡面底色（垂直渐变：上亮下暗） ----------------------------
        # 渐变用若干条水平线裁在圆角内近似
        add(canvas.create_polygon(rot_pts(T.round_rect_points(x1, y1, x2, y2, R)),
                                  fill=T.lerp_color(T.PANEL, T.BG_DEEP, 0.35),
                                  outline="", smooth=True, splinesteps=10))
        steps = max(6, int(14 * s))
        band = H / steps
        for i in range(steps):
            t = i / float(steps - 1)
            col = T.lerp_color(T.PANEL_HI, T.PANEL_LO, t)
            if gray:
                col = T.lerp_color(col, "#2A3138", 0.55)
            yy1 = y1 + band * i
            yy2 = y1 + band * (i + 1) + (1 if i < steps - 1 else 0)
            inset = R * (1 - min(1.0, abs((yy1 + yy2) / 2 - cy) / (H / 2)) ** 2) * 0.35
            add(canvas.create_rectangle(x1 + inset, yy1, x2 - inset, yy2,
                                        fill=col, outline=""))

        # 左侧流派粗色条
        bar_w = 7 * s
        add(canvas.create_polygon(
            rot_pts(T.round_rect_points(x1, y1, x1 + bar_w, y2, R * 0.9)),
            fill=C(acol), outline="", smooth=True, splinesteps=8))

        # --- 军事质感：四角铆钉 + 磨损边缘（附录 B.2）------------------
        if glow:
            rng = random.Random(abs(hash(str(_field(d, "id", "?")))) & 0xFFFF
                                if card is not None else 7)
            for (rx, ry) in ((x1 + 7 * s, y1 + 7 * s), (x2 - 7 * s, y1 + 7 * s),
                             (x1 + 7 * s, y2 - 7 * s)):
                add(canvas.create_oval(rx - 2.2 * s, ry - 2.2 * s,
                                       rx + 2.2 * s, ry + 2.2 * s,
                                       fill=C(T.STEEL),
                                       outline=C(T.shade(T.STEEL, -0.45)), width=1))
                add(canvas.create_oval(rx - 1.0 * s, ry - 1.2 * s,
                                       rx + 0.2 * s, ry, fill=C(T.with_alpha_on(
                                           T.STEEL, T.WHITE, 0.45)), outline=""))
            for _ in range(5):
                ex = rng.uniform(x1 + 4 * s, x2 - 4 * s)
                ey = rng.choice([y1 + 2.0 * s, y2 - 2.0 * s])
                add(canvas.create_line(ex, ey, ex + rng.uniform(3, 9) * s, ey,
                                       fill=C(T.with_alpha_on(T.PANEL, T.RUST, 0.5)),
                                       width=1))

        # --- 外描边 ----------------------------------------------------
        border_col = C(T.lerp_color(rcol, T.WHITE, 0.15))
        if hover or selected:
            border_col = C(T.WHITE)
        add(canvas.create_polygon(rot_pts(T.round_rect_points(x1, y1, x2, y2, R)),
                                  fill="", outline=border_col,
                                  width=max(1, int((2.6 if (hover or selected) else 1.6) * s)),
                                  smooth=True, splinesteps=10))

        # --- 卡图区（程序化军事装饰：焦土天空 + 地平线 + 掩体剪影）------
        art_top = 30 * s
        art_bot = 96 * s
        art_x1, art_x2 = x1 + bar_w + 5 * s, x2 - 6 * s
        add(canvas.create_polygon(
            rot_pts(T.round_rect_points(art_x1, y1 + art_top, art_x2, y1 + art_bot,
                                        5 * s)),
            fill=C(T.lerp_color(acol, T.BG_DEEP, 0.68)), outline="", smooth=True,
            splinesteps=8))
        art_cy = y1 + (art_top + art_bot) / 2.0
        horizon_y = y1 + art_bot - (art_bot - art_top) * 0.32
        # 地平线
        add(canvas.create_line(rot_pts([art_x1 + 2 * s, horizon_y,
                                        art_x2 - 2 * s, horizon_y]),
                               fill=C(T.with_alpha_on(T.BG_DEEP, T.TEXT, 0.22)),
                               width=max(1, int(1.2 * s))))
        # 掩体/坦克剪影：沿地平线的低矮锯齿
        sil = []
        n_sil = 9
        for i in range(n_sil + 1):
            fx = art_x1 + 3 * s + (art_x2 - art_x1 - 6 * s) * i / n_sil
            hh = (0.0 if i % 2 else (3.0 + (i % 3) * 2.0)) * s
            sil.extend((fx, horizon_y))
            sil.extend((fx, horizon_y - hh))
        add(canvas.create_line(rot_pts(sil),
                               fill=C(T.with_alpha_on(T.BG_DEEP, T.BLACK, 0.45)),
                               width=max(1, int(2.2 * s))))
        # 硝烟团
        srng = random.Random(abs(hash(str(_field(d, "id", "?")))) & 0xFFFF
                             if card is not None else 11)
        for _ in range(3):
            sx = srng.uniform(art_x1 + 8 * s, art_x2 - 8 * s)
            sy = srng.uniform(art_cy - 14 * s, horizon_y - 3 * s)
            sr = srng.uniform(4.0, 9.0) * s
            add(canvas.create_oval(sx - sr, sy - sr * 0.7, sx + sr, sy + sr * 0.7,
                                   fill=C(T.with_alpha_on(
                                       T.lerp_color(acol, T.BG_DEEP, 0.68),
                                       T.SMOKE, 0.42)),
                                   outline=""))
        # 一条曳光弹
        tx0 = srng.uniform(art_x1 + 6 * s, art_x2 - 30 * s)
        ty0 = horizon_y - srng.uniform(2, 8) * s
        add(canvas.create_line(rot_pts([tx0, ty0, tx0 + 26 * s, ty0 - 5 * s]),
                               fill=C(T.with_alpha_on(T.BG_DEEP, T.GOLD, 0.55)),
                               width=max(1, int(1.2 * s))))

        # --- 费用宝石 --------------------------------------------------
        cr = 15 * s
        gx, gy = x1 + cr * 0.78, y1 + cr * 0.78
        add(canvas.create_oval(gx - cr, gy - cr, gx + cr, gy + cr,
                               fill=C(T.lerp_color(T.CYAN_DARK, T.BG_DEEP, 0.3)),
                               outline=C(T.CYAN), width=max(1, int(1.8 * s))))
        add(canvas.create_oval(gx - cr * 0.62, gy - cr * 0.62,
                               gx + cr * 0.62, gy + cr * 0.62,
                               fill="", outline=C(T.with_alpha_on(T.BG_DEEP, T.CYAN, .45)),
                               width=1))
        cost = _field(d, "cost", 0)
        if cost is None:
            cost = 0
        cost_txt = "X" if cost == -1 else str(cost)
        if card is not None and _field(card, "cost_override", None) is not None:
            cost_txt = str(_field(card, "cost_override"))
        add(canvas.create_text(gx, gy, text=cost_txt,
                               font=T.make_font(max(9, int(15 * s)), "bold"),
                               fill=C(T.CYAN)))

        # --- 升级标识 "+" ---------------------------------------------
        if card is not None and _field(card, "upgraded", 0):
            px_, py_ = x2 - 12 * s, y1 + 12 * s
            add(canvas.create_oval(px_ - 9 * s, py_ - 9 * s, px_ + 9 * s, py_ + 9 * s,
                                   fill=C(T.GOLD), outline=C(T.shade(T.GOLD, -0.4)),
                                   width=1))
            add(canvas.create_text(px_, py_, text="+",
                                   font=T.make_font(max(9, int(14 * s)), "bold"),
                                   fill="#2A1F05"))

        # --- 名称 ------------------------------------------------------
        name = str(_field(d, "name", "——"))
        cname_font = T.make_font(max(8, int(14 * s)), "bold")
        name_w = T.CARD_W - 30
        name = T.slice_text_cjk(name, name_w * s, cname_font)
        add(canvas.create_text(cx, y1 + 112 * s, text=name, font=cname_font,
                               fill=C(T.TEXT if not gray else T.TEXT_FAINT),
                               anchor="center"))

        # --- 类型条 ----------------------------------------------------
        ty1, ty2 = y1 + 124 * s, y1 + 140 * s
        add(canvas.create_polygon(
            rot_pts(T.round_rect_points(x1 + 10 * s, ty1, x2 - 10 * s, ty2, 4 * s)),
            fill=C(T.with_alpha_on(T.PANEL_LO, tcol, 0.42)), outline="",
            smooth=True, splinesteps=6))
        add(canvas.create_text(cx, (ty1 + ty2) / 2.0,
                               text=" ".join(T.TYPE_NAMES.get(ctype,
                                                              ctype.upper())),
                               font=T.make_font(max(7, int(10 * s)), "bold"),
                               fill=C(tcol)))

        # --- 描述文本（中英混排自动换行） ------------------------------
        desc = str(_field(d, "text", ""))
        # 占位符替换：{damage} -> 实际数值（若 defn 上有对应字段）
        for ph, attr in (("{damage}", "damage"), ("{block}", "block"),
                         ("{magic}", "magic"), ("{magic2}", "magic2"),
                         ("{hits}", "hits")):
            if ph in desc:
                v = _field(d, attr.lstrip("{}"), None)
                if v is not None:
                    desc = desc.replace(ph, str(v))
        dcap = 96 * s
        dfont = T.make_font(max(7, int(11 * s)))
        lines = T.wrap_text_cjk(desc, (T.CARD_W - 30) * s, dfont, max_lines=6)
        dy = y1 + 148 * s
        lh = max(9, int(15 * s))
        for ln in lines:
            add(canvas.create_text(cx, dy, text=ln, font=dfont,
                                   fill=C(T.TEXT_DIM), anchor="n"))
            dy += lh

        # --- 底部指示：移除 / 易失 / 保留 -----------------------------
        flags = []
        if _field(d, "exhaust", False):
            flags.append(("移除", T.BLOOD))
        if _field(d, "ethereal", False):
            flags.append(("易失", T.RUST))
        if _field(d, "retain", False):
            flags.append(("保留", T.CYAN))
        if _field(d, "innate", False):
            flags.append(("先手", T.GOLD))
        if flags:
            fx = x1 + 12 * s
            for label, col in flags[:3]:
                wpx = T.text_size(label, T.make_font(max(7, int(9 * s))))[0] + 8 * s
                add(canvas.create_polygon(
                    rot_pts(T.round_rect_points(fx, y2 - 20 * s, fx + wpx,
                                                y2 - 8 * s, 4 * s)),
                    fill=C(T.with_alpha_on(T.PANEL_LO, col, .5)), outline="",
                    smooth=True, splinesteps=6))
                add(canvas.create_text(fx + wpx / 2.0, y2 - 14 * s, text=label,
                                       font=T.make_font(max(7, int(9 * s))),
                                       fill=C(col)))
                fx += wpx + 4 * s

        # --- 不可打出时的灰色蒙版 --------------------------------------
        if gray:
            add(canvas.create_polygon(rot_pts(T.round_rect_points(x1, y1, x2, y2, R)),
                                      fill=T.with_alpha_on(T.BG_DEEP, "#8899AA", 0.30),
                                      outline="", smooth=True, splinesteps=8,
                                      stipple="gray50"))
        return items

    # ---------------------------------------------------------------- misc
    def destroy(self):
        _cancel(self, "_anim_id")
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        try:
            super().destroy()
        except Exception:
            pass


# =====================================================================
# 3. RelicView
# =====================================================================

class RelicView(tk.Canvas):
    """勋章/装备图标：**按 id 的 hash 程序化生成**形状与配色，无需任何贴图。

    支持传入 ``RelicDef`` 对象或裸 ``id`` 字符串::

        RelicView(parent, relic_def).pack()
        RelicView(parent, "broken_compass", size=28)

    ``on_click`` 回调收到 ``(relic_id)``。
    """

    _SHAPES = ("crystal", "star", "helmet", "eye", "rune", "gear", "dogtag", "shard")

    def __init__(self, parent, relic=None, size=None, bg=None, show_tooltip=True,
                 on_click=None, **kw):
        s = int(size or T.RELIC_SIZE)
        super().__init__(parent, width=s, height=s, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        self._size = s
        self._relic = relic
        self._hover = False
        self._on_click = on_click
        self._tooltip = None
        self._shape_seed = 0
        self._color = T.CYAN
        self._refresh_seed()
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        if on_click:
            self.bind("<Button-1>", self._click)
            self.bind("<Enter>", lambda e: self.configure(cursor="hand2"), add="+")
            self.bind("<Leave>", lambda e: self.configure(cursor=""), add="+")
        if show_tooltip:
            self._tooltip = Tooltip(self, self._tip_text,
                                    wraplength=260, max_lines=6)
        self.bind("<Configure>", lambda e: self.redraw())
        self.redraw()

    # -- data -----------------------------------------------------------
    @property
    def relic_id(self):
        r = self._relic
        if r is None:
            return ""
        if isinstance(r, str):
            return r
        return str(_field(r, "id", ""))

    def set_relic(self, relic):
        self._relic = relic
        self._refresh_seed()
        self.redraw()
        return self

    def _refresh_seed(self):
        rid = self.relic_id
        # 稳定的 hash：不用内置 hash()（受 PYTHONHASHSEED 影响）
        acc = 0
        for i, ch in enumerate(rid or "?"):
            acc = (acc * 131 + ord(ch) + i * 7) & 0xFFFFFFFF
        self._shape_seed = acc
        rar = _field(self._relic, "rarity", None) if not isinstance(self._relic, str) else None
        self._color = T.rarity_color(rar) if rar else T.CYAN
        if self._color in (T.RARITY_COMMON, T.RARITY_BASIC):
            self._color = T.CYAN

    def _tip_text(self):
        r = self._relic
        if r is None:
            return ""
        if isinstance(r, str):
            return r
        return "%s\n%s" % (_field(r, "name", r), _field(r, "text", ""))

    # -- events ---------------------------------------------------------
    def _on_enter(self, event=None):
        self._hover = True
        self.redraw()

    def _on_leave(self, event=None):
        self._hover = False
        self.redraw()

    def _click(self, event=None):
        if self._on_click:
            try:
                self._on_click(self.relic_id)
            except Exception:
                pass

    # -- draw -----------------------------------------------------------
    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        s = self._size
        col = self._color
        if self._hover:
            col = T.lerp_color(col, T.WHITE, 0.25)
        c = s / 2.0
        r = s * 0.40
        base = self.cget("bg") if not self._hover else T.PANEL
        try:
            self.configure(bg=base)
        except Exception:
            pass
        # 底板
        self.create_oval(1, 1, s - 1, s - 1, fill=T.PANEL_LO,
                         outline=T.with_alpha_on(T.PANEL_LO, col, 0.75),
                         width=max(1, int(s * 0.055)))
        if self._hover:
            self.create_oval(0, 0, s, s, fill="",
                             outline=T.with_alpha_on(T.PANEL_LO, col, 0.45), width=1)

        shape = self._SHAPES[self._shape_seed % len(self._SHAPES)]
        rot = (self._shape_seed >> 3) % 360
        pts = []
        if shape == "crystal":
            pts = T.crystal_polygon(c, c, r, 6, rot, 1.0)
        elif shape == "star":
            pts = T.star_polygon(c, c, r, r * 0.44, 5, rot)
        elif shape == "helmet":
            # 钢盔剪影：半圆顶 + 外扩帽檐
            n = 14
            pts = [c - r, c + r * 0.30]
            for i in range(n + 1):
                a = math.radians(180.0 + 180.0 * i / n)
                pts.extend((c + r * math.cos(a) * 1.02, c + r * 0.30
                            + r * 0.95 * math.sin(a)))
            pts.extend([c + r * 1.22, c + r * 0.52, c - r * 1.22, c + r * 0.52])
        elif shape == "eye":
            pts = T.crystal_polygon(c, c, r, 4, 45, 0.62)
        elif shape == "rune":
            pts = T.crystal_polygon(c, c, r, 3, rot, 1.0)
        elif shape == "gear":
            n = 10
            for i in range(n * 2):
                a = math.radians(rot + 360.0 * i / (n * 2))
                rr = r if i % 2 == 0 else r * 0.7
                pts.extend((c + rr * math.cos(a), c + rr * math.sin(a)))
        elif shape == "dogtag":
            pts = T.crystal_polygon(c, c, r, 4, rot + 15, 1.25)
        else:  # shard
            pts = T.crystal_polygon(c, c, r, 5, rot + 20, 1.1)

        self.create_polygon(pts, fill=T.with_alpha_on(T.PANEL_LO, col, 0.55),
                            outline=col, width=max(1, int(s * 0.05)), smooth=True,
                            splinesteps=8)
        # 高光
        self.create_polygon(T.crystal_polygon(c - r * 0.25, c - r * 0.28, r * 0.35,
                                              4, rot, 0.8),
                            fill=T.with_alpha_on(T.PANEL_LO, T.WHITE, 0.30),
                            outline="", smooth=True)
        # 稀有度环（rare/boss 加一圈金环）
        if self._color == T.GOLD or self._color == T.RARITY_SPECIAL:
            self.create_oval(2, 2, s - 2, s - 2, fill="",
                             outline=T.with_alpha_on(T.PANEL_LO, self._color, 0.5),
                             width=1, dash=(3, 3))

    def destroy(self):
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        try:
            super().destroy()
        except Exception:
            pass


# =====================================================================
# 4. BuffBadge
# =====================================================================

BUFF_NAMES = {
    "strength": "火力", "strength_down": "弹药短缺", "dexterity": "机动",
    "vulnerable": "破甲", "weak": "压制", "frail": "混乱", "poison": "燃烧",
    "thorns": "铁丝网", "metallicize": "工事", "ritual": "增援",
    "artifact": "干扰弹", "plated_armor": "装甲板", "regenerate": "战地医疗",
    "intangible": "烟幕", "barrier": "坚守", "chain": "连射",
    "envenom": "燃烧弹", "accuracy": "瞄准",
}

BUFF_DESC = {
    "strength": "每层使攻击伤害 +1。",
    "strength_down": "每层使攻击伤害 -1。",
    "dexterity": "每层使获得的掩体 +1。",
    "vulnerable": "受到的攻击伤害 +50%，回合结束 -1 层。",
    "weak": "造成的攻击伤害 -25%，回合结束 -1 层。",
    "frail": "获得的掩体 -25%，回合结束 -1 层。",
    "poison": "回合开始按层数失去生命，然后 -1 层。",
    "thorns": "被近战攻击时反弹等量伤害。",
    "metallicize": "回合结束时获得等量掩体。",
    "ritual": "每回合开始时获得等量火力。",
    "artifact": "每层抵消一次负面效果。",
    "plated_armor": "回合结束时获得等量掩体（不随回合清空）。",
    "regenerate": "回合结束时回复等量生命。",
    "intangible": "受到的伤害降为 1。",
    "barrier": "掩体在回合结束时不清空。",
    "chain": "本回合每打出一张牌，下一张攻击牌 +N 伤害。",
    "envenom": "攻击造成伤害时施加等量燃烧。",
    "accuracy": "小刀类攻击 +N 伤害。",
}


class BuffBadge(tk.Canvas):
    """Buff 图标 + 层数数字，鼠标悬停显示说明 tooltip。

    ``BuffBadge(parent, "strength", 3).pack()``

    图标形状按 buff key 分类（增益=向上尖角、减益=向下尖角、DoT=叶片等），
    颜色取自 :data:`theme.BUFF_COLORS`。
    """

    _DEBUFFS = {"vulnerable", "weak", "frail", "poison", "strength_down"}
    _DOTS = {"poison", "regenerate", "envenom", "ritual"}

    def __init__(self, parent, key="strength", amount=0, size=None, bg=None,
                 show_tooltip=True, on_click=None, **kw):
        s = int(size or T.BUFF_SIZE)
        super().__init__(parent, width=s, height=s, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        self._size = s
        self._key = key
        self._amount = amount
        self._hover = False
        self._on_click = on_click
        self._tooltip = None
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        if on_click:
            self.bind("<Button-1>", lambda e: on_click(self._key))
        if show_tooltip:
            self._tooltip = Tooltip(self, self._tip_text, wraplength=250, max_lines=5)
        self.bind("<Configure>", lambda e: self.redraw())
        self.redraw()

    # -- data -----------------------------------------------------------
    @property
    def key(self):
        return self._key

    @property
    def amount(self):
        return self._amount

    def set_buff(self, key, amount):
        if key != self._key:
            self._key = key
        self._amount = amount
        self.redraw()
        return self

    set_amount = set_buff

    def _name(self):
        return BUFF_NAMES.get(self._key, self._key)

    def _tip_text(self):
        return "%s %s\n%s" % (self._name(), self._amount,
                              BUFF_DESC.get(self._key, ""))

    # -- events ---------------------------------------------------------
    def _enter(self, e=None):
        self._hover = True
        self.redraw()

    def _leave(self, e=None):
        self._hover = False
        self.redraw()

    # -- draw -----------------------------------------------------------
    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        s = self._size
        c = s / 2.0
        col = T.buff_color(self._key)
        if self._hover:
            col = T.lerp_color(col, T.WHITE, 0.28)
        r = s * 0.40

        # 底板
        self.create_oval(1, 1, s - 1, s - 1, fill=T.PANEL_LO,
                         outline=T.with_alpha_on(T.PANEL_LO, col, 0.8),
                         width=max(1, int(s * 0.06)))

        # 图标形状
        if self._key in self._DEBUFFS:
            pts = [c - r, c - r * 0.7, c, c + r, c + r, c - r * 0.7]   # 向下尖角
        elif self._key in self._DOTS:
            pts = T.crystal_polygon(c, c, r, 6, -90, 1.0)              # 六角
        else:
            pts = [c - r, c + r * 0.7, c, c - r, c + r, c + r * 0.7]   # 向上尖角
        self.create_polygon(pts, fill=T.with_alpha_on(T.PANEL_LO, col, 0.72),
                            outline=col, width=max(1, int(s * 0.045)), smooth=False)

        # 层数数字（右下角，带描边保证可读）
        if self._amount:
            f = T.make_font(max(8, int(s * 0.46)), "bold")
            tx, ty = s - 3, s - 2
            self.create_text(tx + 1, ty + 1, text=str(self._amount), font=f,
                             fill=T.BG_DEEP, anchor="se")
            self.create_text(tx, ty, text=str(self._amount), font=f,
                             fill=T.WHITE, anchor="se")

    def destroy(self):
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        try:
            super().destroy()
        except Exception:
            pass


# =====================================================================
# 5. HPBar
# =====================================================================

class HPBar(tk.Canvas):
    """血条：圆角底槽 + 渐变实血 + **延迟掉血白色残影** + ``hp/max`` 数字。

    用法::

        bar = HPBar(parent, width=220, height=22)
        bar.pack()
        bar.set(42, 80)        # 42/80，掉血时自动播放白色残影收缩动画

    内部用 ``after()`` 做缓动，不阻塞主线程。``bar.destroy()`` 会取消动画。
    """

    def __init__(self, parent, width=None, height=None, hp=1, max_hp=1, bg=None,
                 show_text=True, ghost=True, font=None, block_hint=None, **kw):
        w = int(width or T.HPBAR_W)
        h = int(height or T.HPBAR_H)
        super().__init__(parent, width=w, height=h, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        self._bar_w = w
        self._bar_h = h
        self._max = max(1, int(max_hp))
        self._hp = max(0, int(hp))
        self._shown = float(self._hp)      # 实际绘制用的血（缓动）
        self._ghost = float(self._hp)      # 白色残影值（延迟跟随）
        self._show_text = show_text
        self._ghost_on = ghost
        self._font = font or T.FONT_SMALL
        self._block = int(block_hint) if block_hint else 0
        self._anim_id = None
        self._block_txt = ""
        self.bind("<Configure>", self._on_configure)
        self.redraw()
        self._start()

    # -- api ------------------------------------------------------------
    def set(self, hp, max_hp=None, block=None):
        """设置当前生命（可同时更新上限与掩体）。掉血会触发残影动画。"""
        if max_hp is not None:
            self._max = max(1, int(max_hp))
        if block is not None:
            self._block = int(block)
        new_hp = max(0, min(int(hp), self._max))
        self._hp = new_hp
        if self._shown > new_hp:          # 掉血：残影停在旧值
            self._ghost = max(self._ghost, self._shown)
        else:                             # 回血：残影立刻跟上
            self._ghost = new_hp
        self.redraw()
        return self

    def set_hp(self, hp, max_hp=None):
        return self.set(hp, max_hp)

    def set_max(self, max_hp, hp=None):
        self._max = max(1, int(max_hp))
        if hp is not None:
            self._hp = max(0, min(int(hp), self._max))
        self.redraw()
        return self

    def set_block(self, block):
        self._block = int(block)
        self.redraw()
        return self

    @property
    def hp(self):
        return self._hp

    @property
    def max_hp(self):
        return self._max

    # -- animation ------------------------------------------------------
    def _start(self):
        if self._anim_id is None:
            self._anim_id = self.after(16, self._tick)

    def _tick(self):
        self._anim_id = None
        changed = False
        # 白色残影：延迟收缩（先停顿再快速掉）
        if self._ghost > self._hp + 0.05:
            d = self._ghost - self._hp
            self._ghost -= max(0.28, d * 0.16)
            if self._ghost < self._hp:
                self._ghost = float(self._hp)
            changed = True
        # 实血缓动追赶
        if abs(self._shown - self._hp) > 0.05:
            self._shown += (self._hp - self._shown) * 0.30
            if abs(self._shown - self._hp) <= 0.05:
                self._shown = float(self._hp)
            changed = True
        if changed:
            self.redraw()
        if _alive(self) and (self._ghost > self._hp + 0.05
                             or abs(self._shown - self._hp) > 0.05):
            self._anim_id = self.after(16, self._tick)
        else:
            self._start()      # 保持心跳，便于后续 set() 后继续动画

    def _on_configure(self, e=None):
        try:
            self._bar_w = max(20, self.winfo_width())
            self._bar_h = max(6, self.winfo_height())
        except Exception:
            pass
        self.redraw()

    # -- draw -----------------------------------------------------------
    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        w, h = self._bar_w, self._bar_h
        r = min(h / 2.0, 8.0)
        ratio = self._hp / float(self._max)
        shown_r = max(0.0, min(1.0, self._shown / float(self._max)))
        ghost_r = max(0.0, min(1.0, self._ghost / float(self._max)))
        text_w = 0
        if self._show_text:
            txt = "%d/%d" % (self._hp, self._max)
            text_w = T.text_size(txt, self._font)[0] + 8
        bar_w = max(10, w - text_w)

        # 底槽
        T.round_rect(self, 0, 1, bar_w - 1, h - 1, r, fill=T.PANEL_LO,
                     outline=T.BORDER, width=1)
        # 白色残影（延迟掉血）
        if self._ghost_on and ghost_r > shown_r + 0.001:
            T.round_rect(self, 1, 2, max(2, 1 + (bar_w - 2) * ghost_r), h - 2, r,
                         fill=T.HP_GHOST, outline="")
        # 实血（渐变）
        if shown_r > 0.001:
            x2 = max(2.0, 1 + (bar_w - 2) * shown_r)
            col = T.hp_color(ratio)
            T.vgradient(self, 1, 2, x2, h - 2,
                        T.lerp_color(col, T.WHITE, 0.30),
                        T.lerp_color(col, "#000000", 0.30),
                        steps=max(4, int(h) // 2))
            # 顶部高光
            self.create_line(3, 3, max(4, x2 - 2), 3,
                             fill=T.with_alpha_on(col, T.WHITE, 0.30), width=1)
        # 描边（画在血条之上，保持轮廓清晰）
        T.round_rect(self, 0, 1, bar_w - 1, h - 1, r, fill="", outline=T.BORDER_HI,
                     width=1)
        # 数字
        if self._show_text:
            self.create_text(w - 2, h / 2.0, text="%d/%d" % (self._hp, self._max),
                             font=self._font, fill=T.TEXT, anchor="e")
        # 掩体提示（可选）
        if self._block:
            self.create_text(bar_w / 2.0, h / 2.0, text="⛨ %d" % self._block,
                             font=self._font, fill=T.BLOCK_BLUE, anchor="center")

    def destroy(self):
        _cancel(self, "_anim_id")
        try:
            super().destroy()
        except Exception:
            pass


# =====================================================================
# 6. EnergyOrb
# =====================================================================

class EnergyOrb(tk.Canvas):
    """补给球（能量）：显示 ``cur/max``，带**呼吸光晕**（after 循环，可开关）。

    用法::

        orb = EnergyOrb(parent, size=96); orb.pack()
        orb.set(3, 3)

    呼吸动画默认 40ms 一帧，只重绘光晕层，开销很小。
    """

    def __init__(self, parent, size=None, cur=3, max_energy=3, bg=None,
                 animate=True, on_click=None, **kw):
        s = int(size or (T.ENERGY_ORB_R * 2 + 16))
        super().__init__(parent, width=s, height=s, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        self._size = s
        self._cur = int(cur)
        self._max = max(0, int(max_energy))
        self._phase = 0.0
        self._anim_id = None
        self._animate = bool(animate)
        self._hover = False
        if on_click:
            self.bind("<Button-1>", lambda e: on_click())
            self.bind("<Enter>", lambda e: self.configure(cursor="hand2"), add="+")
            self.bind("<Leave>", lambda e: self.configure(cursor=""), add="+")
        self.bind("<Configure>", lambda e: self.redraw())
        self.redraw()
        if self._animate:
            self._tick()

    # -- api ------------------------------------------------------------
    def set(self, cur, max_energy=None):
        if max_energy is not None:
            self._max = max(0, int(max_energy))
        self._cur = int(cur)
        self.redraw()
        return self

    def set_energy(self, cur, max_energy=None):
        return self.set(cur, max_energy)

    def set_animate(self, on):
        self._animate = bool(on)
        if on and self._anim_id is None:
            self._tick()
        elif not on:
            _cancel(self, "_anim_id")
        return self

    # -- animation ------------------------------------------------------
    def _tick(self):
        self._anim_id = None
        self._phase = (self._phase + 0.09) % (math.pi * 2)
        self.redraw()
        if _alive(self) and self._animate:
            self._anim_id = self.after(40, self._tick)

    # -- draw -----------------------------------------------------------
    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        s = self._size
        c = s / 2.0
        r = s * 0.40
        pulse = (math.sin(self._phase) + 1.0) / 2.0        # 0..1
        full = self._max > 0 and self._cur >= self._max

        # 外层呼吸光晕
        for i in range(3, 0, -1):
            f = i / 3.0
            rr = r + (2.2 + 4.0 * pulse) * f
            col = T.with_alpha_on(T.BG, T.CYAN, (0.10 + 0.16 * pulse) * (1 - f) + 0.04)
            self.create_oval(c - rr, c - rr, c + rr, c + rr, fill="", outline=col,
                             width=max(1, int(3 * (1 - f) + 1)))

        # 球体：径向近似 —— 多层同心椭圆由暗到亮
        for i in range(6, 0, -1):
            f = i / 6.0
            rr = r * f
            col = T.lerp_color(T.CYAN_DARK if not full else T.GOLD_DIM,
                               T.CYAN if not full else T.GOLD, 1.0 - f)
            self.create_oval(c - rr, c - rr * 0.98, c + rr, c + rr * 0.98,
                             fill="", outline=col, width=max(1, int(r / 3.0)))
        self.create_oval(c - r, c - r, c + r, c + r,
                         fill=T.with_alpha_on(T.BG_DEEP, T.CYAN_DARK, 0.55),
                         outline=T.CYAN if not full else T.GOLD,
                         width=max(2, int(s * 0.030)))
        # 内高光
        self.create_oval(c - r * 0.72, c - r * 0.78, c - r * 0.10, c - r * 0.30,
                         fill=T.with_alpha_on(T.CYAN_DARK, T.WHITE, 0.25),
                         outline="")
        # 数字
        big = T.make_font(max(10, int(s * 0.30)), "bold")
        self.create_text(c, c + 1, text="%d" % self._cur, font=big, fill=T.TEXT)
        small = T.make_font(max(8, int(s * 0.125)))
        self.create_text(c, c + r * 0.62, text="/ %d" % self._max, font=small,
                         fill=T.TEXT_DIM)
        self.create_text(c, c - r * 0.72, text="补给", font=small,
                         fill=T.with_alpha_on(T.BG_DEEP, T.CYAN, 0.85))

    def destroy(self):
        _cancel(self, "_anim_id")
        try:
            super().destroy()
        except Exception:
            pass


# =====================================================================
# 7. FancyButton
# =====================================================================

class FancyButton(tk.Canvas):
    """圆角按钮：悬停变色 + 按下凹陷。

    用法::

        b = FancyButton(parent, "结束回合", command=do_end_turn)
        b.pack()
        b.set_text("敌人回合")
        b.set_enabled(False)

    也支持 ``pack``/``grid`` 用外部尺寸：默认宽度按文本自动测量。
    """

    # 预设配色
    STYLES = {
        "primary": (T.CYAN, T.BG_DEEP),
        "gold": (T.GOLD, "#2A1F05"),
        "danger": (T.BLOOD, T.WHITE),
        "ghost": (T.PANEL_HI, T.TEXT),
        "plain": (T.PANEL, T.TEXT),
    }

    def __init__(self, parent, text="", command=None, width=None, height=None,
                 style="primary", color=None, bg=None, font=None, radius=None,
                 padx=22, pady=10, tooltip=None, enabled=True, **kw):
        self._text = str(text)
        self._font = font or T.FONT_BUTTON
        self._padx, self._pady = int(padx), int(pady)
        tw, th = T.text_size(self._text, self._font)
        w = int(width if width is not None else max(90, tw + self._padx * 2))
        h = int(height if height is not None else max(36, th + self._pady * 2))
        super().__init__(parent, width=w, height=h, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        self._style = style
        self._color = color or self.STYLES.get(style, self.STYLES["primary"])[0]
        self._fg = self.STYLES.get(style, self.STYLES["primary"])[1]
        self._radius = T.RADIUS_M if radius is None else radius
        self._command = command
        self._hover = False
        self._pressed = False
        self._enabled = bool(enabled)
        self._tooltip = Tooltip(self, tooltip) if tooltip else None

        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Configure>", lambda e: self.redraw())
        self.redraw()

    # -- api ------------------------------------------------------------
    @property
    def text(self):
        return self._text

    def set_text(self, text):
        self._text = str(text)
        self.redraw()
        return self

    def set_enabled(self, on):
        self._enabled = bool(on)
        self._hover = False if not on else self._hover
        self._pressed = False
        self.redraw()
        return self

    def set_command(self, fn):
        self._command = fn
        return self

    def set_color(self, color, fg=None):
        self._color = color
        if fg:
            self._fg = fg
        self.redraw()
        return self

    def invoke(self):
        if self._enabled and self._command:
            try:
                self._command()
            except Exception:
                pass

    # -- events ---------------------------------------------------------
    def _on_enter(self, e=None):
        self._hover = True
        if self._enabled:
            self.configure(cursor="hand2")
        self.redraw()

    def _on_leave(self, e=None):
        self._hover = False
        self._pressed = False
        self.configure(cursor="")
        self.redraw()

    def _on_press(self, e=None):
        if not self._enabled:
            return
        self._pressed = True
        self.redraw()

    def _on_release(self, e=None):
        was = self._pressed
        self._pressed = False
        self.redraw()
        if was and self._enabled and self._hover:
            self.invoke()

    # -- draw -----------------------------------------------------------
    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        try:
            w = max(20, self.winfo_width())
            h = max(12, self.winfo_height())
        except Exception:
            w = int(self["width"]) or 100
            h = int(self["height"]) or 36
        if w <= 1:
            w = int(self["width"]) or 100
        if h <= 1:
            h = int(self["height"]) or 36

        base = self.bg if hasattr(self, "bg") else T.BG
        try:
            base = self.cget("bg")
        except Exception:
            base = T.BG

        if not self._enabled:
            fill = T.lerp_color(base, T.PANEL, 0.75)
            outline = T.BORDER
            fg = T.TEXT_FAINT
        else:
            fill = self._color
            if self._pressed:
                fill = T.shade(self._color, -0.30)
            elif self._hover:
                fill = T.shade(self._color, 0.18)
            outline = T.shade(self._color, -0.35)
            fg = self._fg

        # 凹陷偏移：按下时整体下移 2px 并去掉阴影
        dy = 2 if self._pressed else 0
        x1, y1, x2, y2 = 1, 1 + dy, w - 1, h - 1 + dy
        if not self._pressed:
            T.shadow(self, x1, y1, x2, y2, self._radius, spread=5, base=base,
                     strength=0.5)
        T.round_rect(self, x1, y1, x2, y2, self._radius,
                     fill=T.with_alpha_on(base, fill, 0.86 if self._enabled else 0.5),
                     outline=outline, width=2 if self._hover and self._enabled else 1)
        # 顶部高光
        T.round_rect(self, x1 + 3, y1 + 2, x2 - 3, y2 - (y2 - y1) * 0.55,
                     max(2, self._radius - 2), fill="",
                     outline=T.with_alpha_on(fill, T.WHITE, 0.18 if self._enabled else 0.05),
                     width=1)
        self.create_text((x1 + x2) / 2.0, (y1 + y2) / 2.0 - 1, text=self._text,
                         font=self._font, fill=fg)

    def destroy(self):
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        try:
            super().destroy()
        except Exception:
            pass


# =====================================================================
# 8. ScrollFrame
# =====================================================================

class ScrollFrame(tk.Frame):
    """可滚动容器：``Canvas`` + ``Scrollbar`` + 鼠标滚轮（**兼容 macOS**）。

    用法::

        sf = ScrollFrame(parent, bg=theme.BG)
        sf.pack(fill="both", expand=True)
        for c in cards:
            CardView(sf.inner, c).pack(side="left")
        sf.update_scrollregion()

    内部结构：``self.canvas`` 是滚动视口，``self.inner`` 是真正放内容的 Frame。
    macOS 上 ``<MouseWheel>`` 的 ``event.delta`` 是"行数"而非 Windows 的 120 倍数，
    这里做了归一化；同时绑定 ``<Button-4>/<Button-5>`` 以兼容 X11。

    支持横向滚动（``orient="horizontal"``）与双向（``"both"``）。
    """

    def __init__(self, parent, bg=None, orient="vertical", width=None, height=None,
                 scrollbar=True, autohide=True, pad=0, **kw):
        self._bg = bg or T.BG
        super().__init__(parent, bg=self._bg, highlightthickness=0, bd=0)
        self._orient = orient
        self._autohide = autohide

        ckw = {"bg": self._bg, "highlightthickness": 0, "bd": 0}
        if width:
            ckw["width"] = int(width)
        if height:
            ckw["height"] = int(height)
        self.canvas = tk.Canvas(self, **ckw)
        self.inner = tk.Frame(self.canvas, bg=self._bg)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview) \
            if (scrollbar and orient in ("vertical", "both")) else None
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview) \
            if (scrollbar and orient in ("horizontal", "both")) else None
        self.vsb, self.hsb = vsb, hsb

        if orient in ("vertical", "both"):
            self.canvas.configure(yscrollcommand=(vsb.set if vsb else None))
        if orient in ("horizontal", "both"):
            self.canvas.configure(xscrollcommand=(hsb.set if hsb else None))

        self.canvas.grid(row=0, column=0, sticky="nsew")
        if vsb is not None:
            vsb.grid(row=0, column=1, sticky="ns")
        if hsb is not None:
            hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._win = self.canvas.create_window(pad, pad, window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_wheel(self)

    # -- wheel ----------------------------------------------------------
    def _bind_wheel(self, widget):
        """递归给所有子控件绑定滚轮（Tk 的事件不会冒泡到父控件）。"""
        widget.bind("<MouseWheel>", self._on_wheel, add="+")        # Win / macOS
        widget.bind("<Button-4>", self._on_wheel, add="+")          # X11 上滚
        widget.bind("<Button-5>", self._on_wheel, add="+")          # X11 下滚
        widget.bind("<Shift-MouseWheel>", self._on_wheel_shift, add="+")
        widget.bind("<Shift-Button-4>", self._on_wheel_shift, add="+")
        widget.bind("<Shift-Button-5>", self._on_wheel_shift, add="+")

    def bind_wheel_to(self, *widgets):
        """把滚轮事件也绑到外部新建的子控件上（内容很多时建议对每个子控件调用）。"""
        for w in widgets:
            self._bind_wheel(w)
        return self

    @staticmethod
    def _wheel_units(event):
        """把不同平台的 delta 归一化成"行"。macOS 的 delta 很小（±1..±10）。"""
        d = getattr(event, "delta", 0) or 0
        num = getattr(event, "num", None)
        if num == 4:
            return -3
        if num == 5:
            return 3
        if abs(d) >= 120:
            return -int(d / 120) * 3
        if d != 0:
            return -d                      # macOS：delta 已经是行数
        return 0

    def _on_wheel(self, event):
        units = self._wheel_units(event)
        if not units:
            return None
        if self._orient in ("vertical", "both"):
            self.canvas.yview_scroll(int(units), "units")
        elif self._orient == "horizontal":
            self.canvas.xview_scroll(int(units), "units")
        return "break"

    def _on_wheel_shift(self, event):
        units = self._wheel_units(event)
        if not units:
            return None
        self.canvas.xview_scroll(int(units), "units")
        return "break"

    # -- geometry -------------------------------------------------------
    def _on_inner_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None):
        # 内容宽度至少撑满视口（竖直滚动时），避免内容窄于窗口
        if self._orient in ("vertical", "both"):
            try:
                self.canvas.itemconfigure(self._win,
                                          width=max(event.width - 2,
                                                    self.inner.winfo_reqwidth()))
            except Exception:
                pass
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def update_scrollregion(self):
        """内容变化后调用（或让 inner 的 <Configure> 自动处理）。"""
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass
        return self

    # -- api ------------------------------------------------------------
    def yview_moveto(self, frac):
        self.canvas.yview_moveto(frac)

    def to_top(self):
        self.canvas.yview_moveto(0.0)

    def to_bottom(self):
        self.canvas.yview_moveto(1.0)

    def content_height(self):
        try:
            return self.inner.winfo_reqheight()
        except Exception:
            return 0

    def destroy(self):
        try:
            super().destroy()
        except Exception:
            pass


# =====================================================================
# 9. DamageNumber
# =====================================================================

class DamageNumber:
    """飘字动画对象：``spawn`` 后在**任意 Canvas** 上自动上浮淡出。

    用法::

        DamageNumber.spawn(canvas, 700, 320, "-12", theme.BLOOD, size=30)
        DamageNumber.spawn(canvas, 700, 300, "掩体 8", theme.BLOCK_BLUE,
                           rise=-30, life=700)

    特性
    ----
    * 纯 ``after()`` 驱动，不阻塞主线程。
    * 支持暴击/大数字的**弹跳缩放**（``pop=True``）。
    * 淡出用 :func:`theme.with_alpha_on` 与背景色混色模拟（Tk 无 alpha）。
    * ``spawn`` 返回对象；``.cancel()`` 可提前终止。

    类属性 ``active`` 记录所有在飞的飘字，``DamageNumber.clear_all(canvas)``
    可一次性清空（例如切场景时）。
    """

    active = []

    __slots__ = ("canvas", "items", "x", "y", "dy", "dx", "text", "color", "size",
                 "life", "elapsed", "bg", "aid", "pop", "font", "scale", "_done",
                 "shadow", "outline")

    def __init__(self, canvas, x, y, text, color=T.BLOOD, size=26, rise=-60,
                 drift=0.0, life=850, bg=None, pop=True, shadow=True,
                 outline=None, font=None):
        self.canvas = canvas
        self.x, self.y = float(x), float(y)
        self.dx = float(drift) / max(1.0, life)
        self.dy = float(rise) / max(1.0, life)
        self.text = str(text)
        self.color = color
        self.size = int(size)
        self.life = max(60, int(life))
        self.elapsed = 0
        self.bg = bg
        self.aid = None
        self.pop = bool(pop)
        self.shadow = bool(shadow)
        self.outline = outline
        self.font = font or T.make_font(self.size, "bold")
        self.scale = 1.0
        self._done = False
        self.items = []
        self._render()
        self._tick()

    # -- spawn ----------------------------------------------------------
    @classmethod
    def spawn(cls, canvas, x, y, text, color=T.BLOOD, size=26, **kw):
        """创建并启动一个飘字，返回 :class:`DamageNumber` 实例。"""
        obj = cls(canvas, x, y, text, color=color, size=size, **kw)
        cls.active.append(obj)
        return obj

    @classmethod
    def clear_all(cls, canvas=None):
        """终止（可选：仅限某个 canvas 上的）所有飘字。"""
        for d in list(cls.active):
            if canvas is None or d.canvas is canvas:
                d.cancel()

    # -- internals ------------------------------------------------------
    def _bg(self):
        if self.bg:
            return self.bg
        try:
            return self.canvas.cget("bg")
        except Exception:
            return T.BG_DEEP

    def _render(self):
        cv = self.canvas
        if self._done:
            return
        try:
            if not cv.winfo_exists():
                return
        except Exception:
            return
        for it in self.items:
            try:
                cv.delete(it)
            except Exception:
                pass
        self.items = []
        t = self.elapsed / float(self.life)
        # 透明度：前 60% 全不透明，之后线性淡出
        alpha = 1.0 if t < 0.60 else max(0.0, 1.0 - (t - 0.60) / 0.40)
        bg = self._bg()
        col = T.with_alpha_on(bg, self.color, alpha)
        # 弹跳：出现时从 1.6 倍缩到 1.0
        if self.pop:
            k = min(1.0, self.elapsed / 130.0)
            self.scale = 1.0 + 0.6 * (1.0 - k) ** 2
        else:
            self.scale = 1.0
        f = T.make_font(max(8, int(self.size * self.scale)), "bold")
        cx, cy = self.x, self.y
        if self.shadow:
            scol = T.with_alpha_on(bg, "#000000", 0.35 * alpha)
            self.items.append(cv.create_text(cx + 2, cy + 2, text=self.text,
                                             font=f, fill=scol, anchor="center"))
        if self.outline:
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ocol = T.with_alpha_on(bg, self.outline, 0.7 * alpha)
                self.items.append(cv.create_text(cx + ox, cy + oy, text=self.text,
                                                 font=f, fill=ocol, anchor="center"))
        self.items.append(cv.create_text(cx, cy, text=self.text, font=f, fill=col,
                                         anchor="center"))

    def _tick(self):
        self.aid = None
        if self._done:
            return
        step = 16
        self.elapsed += step
        self.x += self.dx * step
        self.y += self.dy * step
        if self.elapsed >= self.life:
            self.finish()
            return
        self._render()
        try:
            self.aid = self.canvas.after(step, self._tick)
        except Exception:
            self.aid = None

    def finish(self):
        """结束并清理图形。"""
        if self._done:
            return
        self._done = True
        for it in self.items:
            try:
                self.canvas.delete(it)
            except Exception:
                pass
        self.items = []
        try:
            DamageNumber.active.remove(self)
        except ValueError:
            pass

    cancel = finish

    def __repr__(self):
        return "<DamageNumber %r at (%.0f,%.0f)>" % (self.text, self.x, self.y)


# =====================================================================
# 10. 附加控件（战斗界面用得上，接口稳定）
# =====================================================================

class IntentBadge(tk.Canvas):
    """敌人意图图标：攻击/防御/增益/减益，攻击带伤害数字。

    ``IntentBadge(parent, "attack", damage=12, hits=2)``
    """

    def __init__(self, parent, intent="unknown", damage=0, hits=1, size=34,
                 bg=None, text="", show_tooltip=True, **kw):
        super().__init__(parent, width=size, height=size, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        self._size = int(size)
        self.intent = intent
        self.damage = int(damage or 0)
        self.hits = max(1, int(hits or 1))
        self.desc = text
        if show_tooltip:
            Tooltip(self, lambda: self.desc or self._default_desc(),
                    wraplength=220, max_lines=4)
        self.redraw()

    def _default_desc(self):
        d = {"attack": "将进行攻击", "attack_debuff": "攻击并施加负面效果",
             "attack_defend": "攻击并获得掩体", "defend": "将获得掩体",
             "buff": "将强化自身", "debuff": "将施加负面效果",
             "sleep": "正在沉睡", "unknown": "意图不明"}
        return d.get(self.intent, "意图不明")

    def set(self, intent, damage=0, hits=1, text=""):
        self.intent = intent
        self.damage = int(damage or 0)
        self.hits = max(1, int(hits or 1))
        if text:
            self.desc = text
        self.redraw()
        return self

    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        s = self._size
        c = s / 2.0
        col = T.intent_color(self.intent)
        r = s * 0.36
        self.create_oval(1, 1, s - 1, s - 1, fill=T.PANEL_LO,
                         outline=T.with_alpha_on(T.PANEL_LO, col, 0.85), width=2)
        it = self.intent
        if it.startswith("attack"):
            # 剑：三角+柄
            self.create_polygon(c, c - r, c + r * 0.42, c + r * 0.35,
                                c, c + r * 0.05, c - r * 0.42, c + r * 0.35,
                                fill=col, outline=T.shade(col, -0.3))
        elif it == "defend":
            self.create_polygon(c, c - r, c + r * 0.8, c - r * 0.45,
                                c + r * 0.6, c + r * 0.75, c, c + r,
                                c - r * 0.6, c + r * 0.75, c - r * 0.8, c - r * 0.45,
                                fill=col, outline=T.shade(col, -0.3))
        elif it in ("buff", "debuff"):
            for i in range(3):
                yy = c - r * 0.6 + i * r * 0.6
                self.create_line(c - r * 0.7, yy, c + r * 0.7, yy, fill=col,
                                 width=max(1, int(s * 0.06)))
            sign = "+" if it == "buff" else "−"
            self.create_text(c, c, text=sign, font=T.make_font(int(s * 0.42), "bold"),
                             fill=col)
        elif it == "sleep":
            self.create_text(c, c, text="z", font=T.make_font(int(s * 0.5), "bold"),
                             fill=col)
        else:
            self.create_text(c, c, text="?", font=T.make_font(int(s * 0.5), "bold"),
                             fill=col)
        if self.damage > 0:
            txt = str(self.damage) + ("×%d" % self.hits if self.hits > 1 else "")
            f = T.make_font(max(9, int(s * 0.36)), "bold")
            self.create_text(s - 1, s - 1, text=txt, font=f, fill=T.WHITE,
                             anchor="se")
            self.create_text(s - 2, s - 2, text=txt, font=f, fill=T.BG_DEEP,
                             anchor="se")
            self.create_text(s - 1, s - 1, text=txt, font=f, fill=T.WHITE,
                             anchor="se")


class BlockShield(tk.Canvas):
    """掩体盾徽：显示掩体值，``set(value)`` 更新。"""

    def __init__(self, parent, value=0, size=40, bg=None, **kw):
        super().__init__(parent, width=size, height=size, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        self._size = int(size)
        self._value = int(value)
        self.redraw()

    def set(self, value):
        self._value = max(0, int(value))
        self.redraw()
        return self

    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        s = self._size
        c = s / 2.0
        r = s * 0.40
        pts = [c, c - r, c + r * 0.9, c - r * 0.5, c + r * 0.72, c + r * 0.8,
               c, c + r, c - r * 0.72, c + r * 0.8, c - r * 0.9, c - r * 0.5]
        self.create_polygon(pts, fill=T.with_alpha_on(T.BG_DEEP, T.BLOCK_BLUE, 0.35),
                            outline=T.BLOCK_BLUE, width=2, smooth=True)
        self.create_text(c, c + 1, text=str(self._value),
                         font=T.make_font(max(10, int(s * 0.40)), "bold"),
                         fill=T.TEXT)


class PileButton(tk.Canvas):
    """牌库 / 弃牌堆 计数器按钮（圆角 + 数字 + tooltip + 点击回调）。

    注意：尺寸参数命名为 ``width``/``height``，**不能**用 ``w``/``h``——
    那会遮蔽 Tk 内部 ``Misc.__init__`` 的 widget 路径参数并抛 TclError。
    """

    def __init__(self, parent, label="牌库", count=0, width=86, height=52,
                 bg=None, color=T.CYAN, command=None, **kw):
        super().__init__(parent, width=width, height=height, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        # 注意：绝不能用 self._w —— Tkinter 内部用 _w 存 widget 路径，
        # 覆盖它会让 str(widget) 返回 int，pack()/grid() 直接抛 TclError。
        self._bw, self._bh = int(width), int(height)
        self.label = label
        self.count = int(count)
        self.color = color
        self.command = command
        self._hover = False
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        if command:
            self.bind("<Button-1>", lambda e: command())
            self.bind("<Enter>", lambda e: self.configure(cursor="hand2"), add="+")
        self.redraw()

    def set(self, count, label=None):
        self.count = int(count)
        if label:
            self.label = label
        self.redraw()
        return self

    def _enter(self, e=None):
        self._hover = True
        self.redraw()

    def _leave(self, e=None):
        self._hover = False
        self.redraw()

    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        w, h = self._bw, self._bh
        base = T.PANEL_HI if self._hover else T.PANEL
        T.round_rect(self, 1, 1, w - 1, h - 1, T.RADIUS_S, fill=base,
                     outline=T.with_alpha_on(base, self.color, 0.8), width=1)
        self.create_text(w / 2.0, h * 0.34, text=self.label,
                         font=T.FONT_TINY, fill=T.TEXT_DIM)
        self.create_text(w / 2.0, h * 0.68, text=str(self.count),
                         font=T.make_font(18, "bold"), fill=self.color)


class PipBar(tk.Canvas):
    """通用分段进度条（战区进度 / 击杀计数 / 成就进度都用得上）。

    同样避免 ``w``/``h`` 参数名（见 :class:`PileButton` 的说明）。
    """

    def __init__(self, parent, total=10, value=0, width=None, height=10, bg=None,
                 color=T.CYAN, **kw):
        width = int(width or (total * 14))
        super().__init__(parent, width=width, height=height, bg=bg or T.BG,
                         highlightthickness=0, bd=0, **kw)
        # 同上：不能用 self._w / self._h（Tkinter 保留属性）
        self._bw, self._bh = width, int(height)
        self.total = max(1, int(total))
        self.value = max(0, min(int(value), self.total))
        self.color = color
        self.redraw()

    def set(self, value, total=None):
        if total is not None:
            self.total = max(1, int(total))
        self.value = max(0, min(int(value), self.total))
        self.redraw()
        return self

    def redraw(self):
        if not _alive(self):
            return
        self.delete("all")
        gap = 3
        cw = (self._bw - gap * (self.total - 1)) / float(self.total)
        for i in range(self.total):
            x1 = i * (cw + gap)
            on = i < self.value
            col = self.color if on else T.PANEL_LO
            T.round_rect(self, x1, 1, x1 + cw, self._bh - 1, 3, fill=col,
                         outline="" if on else T.BORDER, width=1)
