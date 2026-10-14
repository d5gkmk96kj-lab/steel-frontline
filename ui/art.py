"""钢铁战线 —— 程序化军事美术库（纯 tkinter Canvas 绘制，零贴图）。

本模块只给 ``ui/`` 内部使用，集中放置**所有**战场题材的矢量绘制原语，
避免同一辆坦克在战斗界面和地图界面各画一遍。

约定
----
* 所有函数接受一个 ``tk.Canvas`` 与一组几何参数，返回创建的 item id 列表。
* 所有绘制都打上调用方给的 ``tags``，方便整体删除。
* 调色板来自 ``ui/theme.py``；缺失时回退到本模块内置的战场配色。
* 不依赖 ``widgets`` / ``core``，可独立 import 与单测。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk

from . import theme as T

# --------------------------------------------------------------------------- #
# 战场调色板（theme.py 常量名不变，仅取值；缺失时用这里的回退）
# --------------------------------------------------------------------------- #
BG_DEEP = getattr(T, "BG_DEEP", "#12100D")
BG = getattr(T, "BG", "#1A1712")
PANEL = getattr(T, "PANEL", "#24201A")
PANEL_HI = getattr(T, "PANEL_HI", "#322C24")
PANEL_LO = getattr(T, "PANEL_LO", "#181510")
BORDER = getattr(T, "BORDER", "#3A3428")
BORDER_HI = getattr(T, "BORDER_HI", "#5A5140")
GOLD = getattr(T, "GOLD", "#C9A227")
CYAN = getattr(T, "CYAN", "#6B7F3A")
BLOOD = getattr(T, "BLOOD", "#A8322D")
TEXT = getattr(T, "TEXT", "#E8E2D4")
TEXT_DIM = getattr(T, "TEXT_DIM", "#9C9280")
TEXT_FAINT = getattr(T, "TEXT_FAINT", "#6B6355")
STEEL = getattr(T, "STEEL", "#5A6470")
SMOKE = getattr(T, "SMOKE", "#3A3630")
RUST = getattr(T, "RUST", "#8B5A2B")
OLIVE = CYAN

FONT_TINY = getattr(T, "FONT_TINY", ("Helvetica", 10))
FONT_SMALL = getattr(T, "FONT_SMALL", ("Helvetica", 12))
FONT_BODY = getattr(T, "FONT_BODY", ("Helvetica", 14))
FONT_H2 = getattr(T, "FONT_H2", ("Helvetica", 18, "bold"))
FONT_NUM = getattr(T, "FONT_NUM", ("Helvetica", 15, "bold"))


def _hex(c: str) -> Tuple[int, int, int]:
    try:
        return T.hex_to_rgb(c)
    except Exception:
        c = (c or "#000000").lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
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


def lerp(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    r1, g1, b1 = _hex(c1)
    r2, g2, b2 = _hex(c2)
    return _to_hex((r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t))


def alpha_on(bg: str, fg: str, a: float) -> str:
    try:
        return str(T.with_alpha_on(bg, fg, a))
    except Exception:
        return lerp(bg, fg, a)


def shade(c: str, amt: float) -> str:
    try:
        return str(T.shade(c, amt))
    except Exception:
        return lerp(c, "#ffffff" if amt > 0 else "#000000", abs(amt))


def rounded(c: tk.Canvas, x1, y1, x2, y2, r=8, **kw):
    """圆角矩形；优先 theme.round_rect，否则回退多边形。"""
    fn = getattr(T, "round_rect", None)
    if callable(fn):
        try:
            return fn(c, x1, y1, x2, y2, r, **kw)
        except Exception:
            pass
    pts: List[float] = []
    r = max(0.0, min(r, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0))
    for cx, cy, a0, a1 in ((x2 - r, y1 + r, -90, 0), (x2 - r, y2 - r, 0, 90),
                           (x1 + r, y2 - r, 90, 180), (x1 + r, y1 + r, 180, 270)):
        for i in range(5):
            a = math.radians(a0 + (a1 - a0) * i / 4.0)
            pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))
    return c.create_polygon(pts, **kw)


def rect(c: tk.Canvas, x1, y1, x2, y2, **kw):
    return c.create_rectangle(x1, y1, x2, y2, **kw)


def poly(c: tk.Canvas, pts, **kw):
    return c.create_polygon(list(pts), **kw)


# --------------------------------------------------------------------------- #
# 1. 战场背景
# --------------------------------------------------------------------------- #
def battlefield(c: tk.Canvas, w: float, h: float, tag: str = "bg",
                horizon: float = 0.56, smoke_layer: bool = True) -> None:
    """焦土战场背景：天空渐变 + 地平线 + 焦土 + 远景废墟。"""
    hy = h * horizon
    # 天空：硝烟黄褐 -> 灰
    steps = 40
    for i in range(steps):
        t = i / float(steps - 1)
        col = lerp("#3B3226", "#191612", t)
        c.create_rectangle(0, (hy) * i / steps, w, hy * (i + 1) / steps + 1,
                           fill=col, outline="", tags=tag)
    # 远景地平线光带
    c.create_rectangle(0, hy - 3, w, hy + 2, fill="#5A4A32", outline="",
                       tags=tag)
    # 地面
    gsteps = 26
    for i in range(gsteps):
        t = i / float(gsteps - 1)
        col = lerp("#2A231A", "#0D0B08", t)
        yy = hy + (h - hy) * i / gsteps
        c.create_rectangle(0, yy, w, hy + (h - hy) * (i + 1) / gsteps + 1,
                           fill=col, outline="", tags=tag)
    # 远景废墟剪影
    ruins(c, w, hy, tag)
    if smoke_layer:
        smoke_band(c, w, h, tag)


def ruins(c: tk.Canvas, w: float, hy: float, tag: str) -> None:
    """地平线上的残破建筑轮廓。"""
    col = "#14110D"
    xs = 0.0
    seed = 7
    while xs < w:
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        bw = 40 + (seed % 70)
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        bh = 20 + (seed % 60)
        x2 = min(w, xs + bw)
        # 锯齿屋顶
        pts = [xs, hy, xs, hy - bh]
        segs = 4
        for i in range(segs):
            sx = xs + (x2 - xs) * i / segs
            ex = xs + (x2 - xs) * (i + 1) / segs
            top = hy - bh + ((seed >> (i * 3)) % 16)
            pts.extend((sx, top, ex, top))
        pts.extend((x2, hy))
        c.create_polygon(pts, fill=col, outline="", tags=tag)
        # 窗口
        for k in range(3):
            wx = xs + (x2 - xs) * (k + 0.5) / 3
            if wx + 4 < x2:
                c.create_rectangle(wx - 4, hy - bh * 0.6, wx + 4, hy - bh * 0.4,
                                   fill="#0A0906", outline="", tags=tag)
        xs = x2 + 6


def smoke_band(c: tk.Canvas, w: float, h: float, tag: str) -> None:
    """低空硝烟带（静态底衬，动态粒子由 particles 负责）。"""
    for i in range(5):
        y = h * (0.12 + 0.09 * i)
        col = alpha_on(BG_DEEP, "#6B5F4A", 0.05 + 0.02 * (4 - i))
        c.create_rectangle(0, y, w, y + h * 0.07, fill=col, outline="",
                           tags=tag)


def horizon_glow(c: tk.Canvas, w: float, h: float, tag: str,
                 t: float = 0.0) -> None:
    """地平线火光（远处炮击的间歇闪光）。"""
    pulse = 0.5 + 0.5 * math.sin(t * 0.9)
    hy = h * 0.56
    col = alpha_on(BG_DEEP, "#FF8A3C", 0.05 + 0.05 * pulse)
    c.create_oval(-w * 0.2, hy - 60, w * 0.5, hy + 40, fill=col, outline="",
                  tags=tag)
    c.create_oval(w * 0.55, hy - 50, w * 1.2, hy + 30, fill=col, outline="",
                  tags=tag)


# --------------------------------------------------------------------------- #
# 2. 粒子：硝烟 + 曳光弹
# --------------------------------------------------------------------------- #
def make_smoke_sprites(w: float, h: float, n: int = 60, seed: int = 20241) -> List[dict]:
    """生成硝烟粒子（确定性伪随机，不污染游戏随机序列）。"""
    out: List[dict] = []
    for _ in range(n):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = seed % max(1, int(w))
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = seed % max(1, int(h))
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        spd = 0.18 + (seed % 100) / 260.0
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        r = 2.0 + (seed % 100) / 9.0
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        phase = seed % 360
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        drift = ((seed % 40) - 16) / 22.0
        out.append({"x": float(x), "y": float(y), "spd": spd, "r": r,
                    "phase": phase, "drift": drift})
    return out


def draw_smoke_cloud(c: tk.Canvas, x: float, y: float, r: float, col: str,
                     tag: str) -> None:
    """一朵硝烟：三层同心圆，越外越淡。"""
    for i in range(3):
        rr = r * (1.0 - i * 0.26)
        a = 0.30 - i * 0.09
        if rr <= 0.5:
            continue
        c.create_oval(x - rr, y - rr * 0.8, x + rr, y + rr * 0.8,
                      fill=alpha_on(BG_DEEP, col, a), outline="", tags=tag)


def tracer(c: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
           col: str = "#FFD27A", tag: str = "fx") -> None:
    """曳光弹轨迹：一条亮线 + 拖尾。"""
    c.create_line(x1, y1, x2, y2, fill=alpha_on(BG_DEEP, col, 0.30), width=4,
                  tags=tag)
    c.create_line(x1, y1, x2, y2, fill=col, width=1, tags=tag)


# --------------------------------------------------------------------------- #
# 3. 玩家单位：坦克 / 总部
# --------------------------------------------------------------------------- #
def tank(c: tk.Canvas, cx: float, cy: float, s: float = 1.0,
         col: Optional[str] = None, facing: int = 1, tag: str = "unit",
         turret_angle: float = 0.0, tread_phase: float = 0.0) -> None:
    """玩家/敌方坦克剪影（俯视偏 3/4）。

    车体 + 炮塔 + 炮管 + 履带 + 负重轮 + 舱盖 + 天线。
    ``facing`` 1 朝右，-1 朝左。
    """
    col = col or OLIVE
    dark = shade(col, -0.45)
    mid = shade(col, -0.18)
    light = shade(col, 0.25)
    body_w, body_h = 132 * s, 62 * s
    x1, x2 = cx - body_w / 2, cx + body_w / 2
    y1, y2 = cy - body_h / 2, cy + body_h / 2

    # --- 履带
    tr_h = 17 * s
    for side, ty in ((-1, y1 - tr_h * 0.5), (1, y2 + tr_h * 0.5)):
        rounded(c, x1 - 8 * s, ty - tr_h / 2, x2 + 8 * s, ty + tr_h / 2,
                tr_h / 2, fill=dark, outline=shade(dark, -0.3), width=2,
                tags=tag)
        # 履带齿
        n = 12
        for i in range(n):
            px = (x1 - 6 * s) + (body_w + 12 * s) * i / (n - 1)
            off = math.sin(tread_phase + i * 0.7) * 1.2 * s
            c.create_line(px, ty - tr_h * 0.42 + off, px, ty + tr_h * 0.42 + off,
                          fill=shade(dark, 0.18), width=1, tags=tag)
    # 负重轮
    for side, ty in ((-1, y1 - tr_h * 0.5), (1, y2 + tr_h * 0.5)):
        for i in range(5):
            wx = x1 + 16 * s + (body_w - 32 * s) * i / 4.0
            c.create_oval(wx - 6 * s, ty - 6 * s, wx + 6 * s, ty + 6 * s,
                          fill=shade(dark, 0.12), outline=shade(dark, -0.25),
                          width=1, tags=tag)

    # --- 车体（前部倾斜装甲）
    nose = 18 * s * facing
    poly(c, [x1, y1 + 6 * s, x2 - (0 if facing > 0 else nose), y1,
             x2 + nose, cy - 4 * s, x2 + nose, cy + 4 * s,
             x2 - (0 if facing > 0 else nose), y2, x1, y2 - 6 * s],
         fill=col, outline=dark, width=2, tags=tag)
    # 车体高光
    rect(c, x1 + 6 * s, y1 + 6 * s, x2 - 6 * s, y1 + 14 * s, fill=light,
         outline="", tags=tag)
    # 挡泥板 / 侧裙
    rect(c, x1 + 4 * s, y2 - 12 * s, x2 - 4 * s, y2 - 2 * s,
         fill=mid, outline="", tags=tag)
    # 车体铆钉
    for i in range(6):
        rx = x1 + 14 * s + (body_w - 28 * s) * i / 5.0
        c.create_oval(rx - 1.6 * s, cy - 1.6 * s, rx + 1.6 * s, cy + 1.6 * s,
                      fill=shade(col, 0.35), outline="", tags=tag)

    # --- 炮塔
    tw, th = 66 * s, 46 * s
    tx, ty = cx + 4 * s * facing, cy - 4 * s
    poly(c, [tx - tw / 2, ty + th / 2, tx - tw / 2 + 8 * s, ty - th / 2,
             tx + tw / 2 - 8 * s, ty - th / 2, tx + tw / 2, ty + th / 2],
         fill=mid, outline=dark, width=2, tags=tag)
    # 炮管
    a = math.radians(turret_angle)
    bl = 74 * s
    bx1 = tx + math.cos(a) * 20 * s * facing
    by1 = ty + math.sin(a) * 20 * s
    bx2 = tx + math.cos(a) * bl * facing
    by2 = ty + math.sin(a) * bl
    c.create_line(bx1, by1, bx2, by2, fill=dark, width=int(9 * s),
                  capstyle="round", tags=tag)
    c.create_line(bx1, by1, bx2, by2, fill=shade(col, 0.1),
                  width=int(5 * s), capstyle="round", tags=tag)
    # 炮口制退器
    c.create_oval(bx2 - 6 * s, by2 - 6 * s, bx2 + 6 * s, by2 + 6 * s,
                  fill=dark, outline="", tags=tag)
    # 舱盖
    c.create_oval(tx - 13 * s, ty - 16 * s, tx + 13 * s, ty + 10 * s,
                  fill=shade(mid, 0.18), outline=dark, width=1, tags=tag)
    # 天线
    c.create_line(tx - 22 * s, ty - th / 2, tx - 34 * s, ty - th / 2 - 40 * s,
                  fill=dark, width=max(1, int(2 * s)), tags=tag)
    # 星徽
    star(c, cx - 26 * s * facing, cy + 10 * s, 9 * s, TEXT_DIM, tag,
         points=5)


def hq(c: tk.Canvas, cx: float, cy: float, s: float = 1.0,
       col: Optional[str] = None, tag: str = "hq", hp_ratio: float = 1.0,
       flag_phase: float = 0.0) -> None:
    """总部碉堡：混凝土工事 + 沙袋 + 旗杆（玩家阵地）。"""
    col = col or "#6E6A5E"
    dark = shade(col, -0.42)
    light = shade(col, 0.2)
    w, h = 190 * s, 92 * s
    x1, x2 = cx - w / 2, cx + w / 2
    y1, y2 = cy - h / 2, cy + h / 2

    # 沙袋基座
    for i in range(9):
        bx = x1 - 16 * s + (w + 32 * s) * i / 8.0
        by = y2 + 12 * s
        rounded(c, bx - 15 * s, by - 11 * s, bx + 15 * s, by + 11 * s, 9 * s,
                fill=shade("#7A6A46", -0.08 if i % 2 else 0.0),
                outline=shade("#7A6A46", -0.4), width=1, tags=tag)
    # 主堡体（梯形，上窄下宽）
    poly(c, [x1 + 14 * s, y1, x2 - 14 * s, y1, x2, y2, x1, y2],
         fill=col, outline=dark, width=2, tags=tag)
    # 顶部
    rect(c, x1 + 10 * s, y1 - 10 * s, x2 - 10 * s, y1 + 2 * s, fill=light,
         outline=dark, tags=tag)
    # 射击孔
    for i in range(4):
        sx = x1 + 34 * s + (w - 68 * s) * i / 3.0
        rect(c, sx - 11 * s, cy - 6 * s, sx + 11 * s, cy + 6 * s,
             fill="#0B0906", outline=dark, tags=tag)
    # 混凝土纹理
    for i in range(5):
        ly = y1 + (y2 - y1) * (i + 1) / 6.0
        c.create_line(x1 + 4 * s, ly, x2 - 4 * s, ly, fill=shade(col, -0.22),
                      width=1, tags=tag)
    # 沙袋掩体（前方）
    for i in range(4):
        bx = x1 + 20 * s + (w - 40 * s) * i / 3.0
        rounded(c, bx - 17 * s, y2 + 24 * s, bx + 17 * s, y2 + 46 * s, 12 * s,
                fill="#7A6A46", outline=shade("#7A6A46", -0.4), width=1,
                tags=tag)
    # 旗杆 + 旗帜
    px = x2 - 26 * s
    c.create_line(px, y1 - 10 * s, px, y1 - 96 * s, fill="#3A3428",
                  width=max(2, int(3 * s)), tags=tag)
    fw = 52 * s
    wob = math.sin(flag_phase) * 4 * s
    flag_col = OLIVE if hp_ratio > 0.35 else BLOOD
    poly(c, [px, y1 - 94 * s, px + fw, y1 - 86 * s + wob,
             px + fw * 0.6, y1 - 74 * s + wob * 0.5, px + fw,
             y1 - 60 * s + wob, px, y1 - 54 * s],
         fill=flag_col, outline=shade(flag_col, -0.35), width=1, tags=tag)
    star(c, px + fw * 0.42, y1 - 75 * s, 10 * s, "#D8CFAF", tag)


def star(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
         tag: str = "unit", points: int = 5) -> None:
    pts: List[float] = []
    for i in range(points * 2):
        a = -math.pi / 2 + math.pi * i / points
        rr = r if i % 2 == 0 else r * 0.45
        pts.extend((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    c.create_polygon(pts, fill=col, outline="", tags=tag)


# --------------------------------------------------------------------------- #
# 4. 敌方单位：坦克 / 步兵 / 飞机 / 要塞 / 火炮
# --------------------------------------------------------------------------- #
def enemy_tank(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
               tag: str) -> None:
    """敌方坦克（朝左，配色偏敌方灰蓝/铁锈）。"""
    tank(c, cx, cy, s=r / 66.0, col=col, facing=-1, tag=tag,
         turret_angle=8.0, tread_phase=1.4)


def enemy_infantry(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                   tag: str) -> None:
    """步兵：头盔 + 肩线 + 步枪剪影。"""
    dark = shade(col, -0.4)
    # 头盔
    c.create_arc(cx - r * 0.62, cy - r * 0.95, cx + r * 0.62, cy + r * 0.35,
                 start=0, extent=180, fill=col, outline=dark, width=2, tags=tag)
    c.create_rectangle(cx - r * 0.68, cy - r * 0.34, cx + r * 0.68, cy - r * 0.2,
                       fill=shade(col, 0.18), outline=dark, tags=tag)
    # 面部阴影
    c.create_oval(cx - r * 0.36, cy - r * 0.36, cx + r * 0.36, cy + r * 0.1,
                  fill="#120F0B", outline="", tags=tag)
    # 躯干
    poly(c, [cx - r * 0.7, cy + r * 0.15, cx + r * 0.7, cy + r * 0.15,
             cx + r * 0.5, cy + r * 1.15, cx - r * 0.5, cy + r * 1.15],
         fill=shade(col, -0.15), outline=dark, width=2, tags=tag)
    # 步枪
    c.create_line(cx - r * 0.95, cy + r * 0.95, cx + r * 0.85, cy + r * 0.1,
                  fill="#2B2318", width=max(2, int(r * 0.16)), tags=tag)
    # 弹带
    c.create_line(cx - r * 0.5, cy + r * 0.3, cx + r * 0.45, cy + r * 0.75,
                  fill=RUST, width=max(1, int(r * 0.1)), tags=tag)


def enemy_plane(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                tag: str) -> None:
    """螺旋桨飞机（俯视）：机身 + 机翼 + 尾翼 + 旋转桨盘。"""
    dark = shade(col, -0.42)
    # 机翼
    poly(c, [cx - r * 1.5, cy - r * 0.1, cx + r * 1.5, cy - r * 0.1,
             cx + r * 1.25, cy + r * 0.2, cx - r * 1.25, cy + r * 0.2],
         fill=shade(col, -0.12), outline=dark, width=2, tags=tag)
    # 机身
    poly(c, [cx + r * 1.35, cy, cx + r * 0.6, cy - r * 0.34,
             cx - r * 1.0, cy - r * 0.26, cx - r * 1.0, cy + r * 0.26,
             cx + r * 0.6, cy + r * 0.34],
         fill=col, outline=dark, width=2, tags=tag)
    # 尾翼
    poly(c, [cx - r * 1.0, cy - r * 0.55, cx - r * 0.5, cy - r * 0.5,
             cx - r * 0.6, cy + r * 0.5, cx - r * 1.0, cy + r * 0.55],
         fill=shade(col, -0.2), outline=dark, width=2, tags=tag)
    # 座舱
    c.create_oval(cx + r * 0.3, cy - r * 0.22, cx + r * 0.75, cy + r * 0.22,
                  fill="#8FA6B0", outline=dark, width=2, tags=tag)
    # 桨盘
    c.create_oval(cx + r * 1.3, cy - r * 0.62, cx + r * 1.55, cy + r * 0.62,
                  fill="", outline=alpha_on(BG_DEEP, TEXT_DIM, 0.5), width=2,
                  tags=tag)


def enemy_fortress(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                   tag: str) -> None:
    """要塞：多层棱堡 + 炮塔 + 探照灯。"""
    dark = shade(col, -0.45)
    # 基座棱堡
    poly(c, [cx - r * 1.25, cy + r * 0.9, cx - r * 1.05, cy - r * 0.25,
             cx - r * 0.45, cy - r * 0.55, cx + r * 0.45, cy - r * 0.55,
             cx + r * 1.05, cy - r * 0.25, cx + r * 1.25, cy + r * 0.9],
         fill=shade(col, -0.18), outline=dark, width=3, tags=tag)
    # 垛口
    for i in range(7):
        bx = cx - r * 1.0 + r * 2.0 * i / 6.0
        rect(c, bx - r * 0.09, cy - r * 0.78, bx + r * 0.09, cy - r * 0.5,
             fill=shade(col, 0.08), outline=dark, tags=tag)
    # 主炮塔
    poly(c, [cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy - r * 0.5,
             cx + r * 0.62, cy - r * 0.05, cx - r * 0.62, cy - r * 0.05],
         fill=shade(col, 0.16), outline=dark, width=2, tags=tag)
    c.create_line(cx, cy - r * 0.3, cx - r * 1.3, cy - r * 0.75,
                  fill=dark, width=max(3, int(r * 0.12)), tags=tag)
    c.create_line(cx, cy - r * 0.3, cx + r * 1.3, cy - r * 0.75,
                  fill=dark, width=max(3, int(r * 0.12)), tags=tag)
    # 射击孔
    for i in range(4):
        sx = cx - r * 0.75 + r * 1.5 * i / 3.0
        rect(c, sx - r * 0.08, cy + r * 0.3, sx + r * 0.08, cy + r * 0.5,
             fill="#0B0906", outline=dark, tags=tag)
    # 探照灯
    c.create_oval(cx + r * 0.85, cy - r * 1.05, cx + r * 1.15, cy - r * 0.75,
                  fill=alpha_on(BG_DEEP, "#FFE7A8", 0.85), outline=dark,
                  width=1, tags=tag)


def enemy_artillery(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                    tag: str) -> None:
    """牵引火炮：炮盾 + 长炮管 + 大轮。"""
    dark = shade(col, -0.42)
    for side in (-1, 1):
        wx = cx + side * r * 0.45
        c.create_oval(wx - r * 0.42, cy + r * 0.05, wx + r * 0.42, cy + r * 0.9,
                      fill="#241E16", outline=dark, width=3, tags=tag)
        for i in range(6):
            a = math.pi * 2 * i / 6.0
            c.create_line(wx, cy + r * 0.48,
                          wx + math.cos(a) * r * 0.36,
                          cy + r * 0.48 + math.sin(a) * r * 0.36,
                          fill=shade(col, 0.1), width=2, tags=tag)
    poly(c, [cx - r * 0.6, cy - r * 0.15, cx + r * 0.6, cy - r * 0.15,
             cx + r * 0.5, cy + r * 0.4, cx - r * 0.5, cy + r * 0.4],
         fill=col, outline=dark, width=2, tags=tag)
    c.create_line(cx, cy - r * 0.1, cx + r * 0.2, cy - r * 1.25,
                  fill=dark, width=max(3, int(r * 0.14)), tags=tag)
    c.create_line(cx - r * 0.4, cy + r * 0.35, cx - r * 1.0, cy + r * 1.0,
                  fill=dark, width=max(2, int(r * 0.1)), tags=tag)


def enemy_soldier_elite(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                        tag: str) -> None:
    """精锐部队：军官剪影 + 大檐帽 + 望远镜。"""
    enemy_infantry(c, cx, cy, r, col, tag)
    dark = shade(col, -0.5)
    # 大檐帽替换头盔
    c.create_oval(cx - r * 0.7, cy - r * 1.05, cx + r * 0.7, cy - r * 0.55,
                  fill=shade(col, 0.05), outline=dark, width=2, tags=tag)
    rect(c, cx - r * 0.85, cy - r * 0.68, cx + r * 0.85, cy - r * 0.5,
         fill=shade(col, -0.3), outline=dark, tags=tag)
    # 肩章
    for side in (-1, 1):
        rect(c, cx + side * r * 0.5 - r * 0.14, cy + r * 0.18,
             cx + side * r * 0.5 + r * 0.14, cy + r * 0.34, fill=GOLD,
             outline="", tags=tag)


def enemy_generic(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                  tag: str) -> None:
    """兜底：装甲运兵车剪影。"""
    dark = shade(col, -0.44)
    for side in (-1, 1):
        wy = cy + side * r * 0.5
        rounded(c, cx - r * 1.0, wy - r * 0.22, cx + r * 1.0, wy + r * 0.22,
                r * 0.2, fill="#241E16", outline=dark, width=2, tags=tag)
    poly(c, [cx - r * 1.05, cy - r * 0.42, cx + r * 0.5, cy - r * 0.55,
             cx + r * 1.05, cy - r * 0.1, cx + r * 1.05, cy + r * 0.42,
             cx - r * 1.05, cy + r * 0.42],
         fill=col, outline=dark, width=2, tags=tag)
    rect(c, cx - r * 0.75, cy - r * 0.36, cx + r * 0.2, cy - r * 0.15,
         fill=shade(col, 0.2), outline="", tags=tag)


#: 敌人美术 key -> 绘制函数
ENEMY_ART: Dict[str, Any] = {
    "tank": enemy_tank,
    "infantry": enemy_infantry,
    "plane": enemy_plane,
    "fortress": enemy_fortress,
    "artillery": enemy_artillery,
    "elite": enemy_soldier_elite,
    "generic": enemy_generic,
}


def draw_enemy_unit(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                    art: str, tag: str = "enemy") -> None:
    """按 art key 画敌人立绘；未知 key 用哨兵/运兵车兜底。"""
    fn = ENEMY_ART.get(str(art or "").lower(), enemy_generic)
    try:
        fn(c, cx, cy, r, col, tag)
    except Exception:
        enemy_generic(c, cx, cy, r, col, tag)


def unit_art_for(name: str = "", eid: str = "", fallback_index: int = 0) -> str:
    """把敌人名字/id 映射到美术 key（题材无关的启发式）。"""
    key = (str(name) + " " + str(eid)).lower()
    table = (
        (("要塞", "堡垒", "fortress", "citadel", "bunker"), "fortress"),
        (("飞机", "轰炸", "航空", "plane", "bomber", "air", "wing"), "plane"),
        (("炮", "artillery", "howitzer", "gun", "mortar"), "artillery"),
        (("精锐", "军官", "指挥", "elite", "officer", "commander"), "elite"),
        (("步兵", "士兵", "infantry", "rifle", "trooper", "squad"), "infantry"),
        (("坦克", "装甲", "tank", "panzer", "armor", "armour"), "tank"),
    )
    for words, art in table:
        for w in words:
            if w in key:
                return art
    return ("tank", "infantry", "artillery", "plane", "generic")[
        fallback_index % 5]


# --------------------------------------------------------------------------- #
# 5. 战场装饰：沙袋 / 铁丝网 / 弹坑 / 路障 / 地图桌
# --------------------------------------------------------------------------- #
def sandbags(c: tk.Canvas, cx: float, cy: float, n: int = 4, s: float = 1.0,
             tag: str = "deco") -> None:
    for i in range(n):
        bx = cx + (i - (n - 1) / 2.0) * 34 * s
        rounded(c, bx - 17 * s, cy - 11 * s, bx + 17 * s, cy + 11 * s, 9 * s,
                fill="#7A6A46" if i % 2 else "#6E5F3E",
                outline="#4A3F28", width=1, tags=tag)


def barbed_wire(c: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                tag: str = "deco", posts: int = 4) -> None:
    """铁丝网：立柱 + 交叉钢丝 + 倒刺。"""
    col = "#4A453A"
    for i in range(posts):
        t = i / float(max(1, posts - 1))
        px = x1 + (x2 - x1) * t
        py = y1 + (y2 - y1) * t
        c.create_line(px, py - 22, px, py + 10, fill=col, width=2, tags=tag)
    for k in (-6, 0, 6):
        c.create_line(x1, y1 + k, x2, y2 + k, fill=col, width=1, tags=tag)
    for i in range(posts * 3):
        t = i / float(max(1, posts * 3 - 1))
        px = x1 + (x2 - x1) * t
        py = y1 + (y2 - y1) * t
        c.create_line(px - 4, py - 4, px + 4, py + 4, fill=col, width=1,
                      tags=tag)
        c.create_line(px - 4, py + 4, px + 4, py - 4, fill=col, width=1,
                      tags=tag)


def crater(c: tk.Canvas, cx: float, cy: float, r: float,
           tag: str = "deco") -> None:
    c.create_oval(cx - r, cy - r * 0.45, cx + r, cy + r * 0.45,
                  fill="#171310", outline=shade("#171310", 0.25), width=1,
                  tags=tag)
    c.create_oval(cx - r * 0.7, cy - r * 0.3, cx + r * 0.7, cy + r * 0.3,
                  fill="#0E0B09", outline="", tags=tag)


def hedgehog(c: tk.Canvas, cx: float, cy: float, s: float = 1.0,
             tag: str = "deco") -> None:
    """反坦克拒马。"""
    col = "#3A3428"
    for a in (90, 210, 330):
        rad = math.radians(a)
        c.create_line(cx - math.cos(rad) * 26 * s, cy + math.sin(rad) * 26 * s,
                      cx + math.cos(rad) * 26 * s, cy - math.sin(rad) * 26 * s,
                      fill=col, width=max(2, int(4 * s)), tags=tag)


def map_table(c: tk.Canvas, cx: float, cy: float, w: float, h: float,
              tag: str = "deco") -> None:
    """地图桌：一张摊开的地图 + 图钉 + 尺规。"""
    rounded(c, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, 6,
            fill="#6E5F3E", outline="#3A3122", width=3, tags=tag)
    for i in range(5):
        y = cy - h / 2 + h * (i + 1) / 6.0
        c.create_line(cx - w / 2 + 8, y, cx + w / 2 - 8, y,
                      fill=alpha_on("#6E5F3E", "#3A3122", 0.4), width=1,
                      tags=tag)
    for i in range(4):
        x = cx - w / 2 + w * (i + 1) / 5.0
        c.create_line(x, cy - h / 2 + 8, x, cy + h / 2 - 8,
                      fill=alpha_on("#6E5F3E", "#3A3122", 0.4), width=1,
                      tags=tag)
    for i in range(3):
        px = cx - w * 0.3 + w * 0.3 * i
        py = cy - h * 0.2 + h * 0.35 * (i % 2)
        c.create_oval(px - 5, py - 5, px + 5, py + 5, fill=BLOOD, outline="",
                      tags=tag)


# --------------------------------------------------------------------------- #
# 6. 战术图标（掩体 / 攻击 / 指令 / 补给）
# --------------------------------------------------------------------------- #
def icon_shield(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                tag: str = "ico") -> None:
    """掩体（盾）。"""
    poly(c, [cx, cy - r, cx + r * 0.85, cy - r * 0.55, cx + r * 0.85,
             cy + r * 0.25, cx, cy + r, cx - r * 0.85, cy + r * 0.25,
             cx - r * 0.85, cy - r * 0.55],
         fill=col, outline="", tags=tag)
    c.create_line(cx, cy - r * 0.6, cx, cy + r * 0.6, fill="#FFFFFF", width=2,
                  tags=tag)


def icon_burst(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
               tag: str = "ico") -> None:
    """攻击（爆裂）。"""
    pts: List[float] = []
    for i in range(16):
        a = math.pi * 2 * i / 16.0
        rr = r if i % 2 == 0 else r * 0.48
        pts.extend((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    c.create_polygon(pts, fill=col, outline="", tags=tag)


def icon_gear(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
              tag: str = "ico") -> None:
    """指令（齿轮）。"""
    teeth = 8
    pts: List[float] = []
    for i in range(teeth * 2):
        a = math.pi * 2 * i / (teeth * 2)
        rr = r if i % 2 == 0 else r * 0.72
        pts.extend((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    c.create_polygon(pts, fill=col, outline="", tags=tag)
    c.create_oval(cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3,
                  fill=BG_DEEP, outline="", tags=tag)


def icon_supply(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
                tag: str = "ico") -> None:
    """补给（弹药箱）。"""
    rounded(c, cx - r, cy - r * 0.75, cx + r, cy + r * 0.75, r * 0.18,
            fill=col, outline="", tags=tag)
    c.create_line(cx - r, cy - r * 0.2, cx + r, cy - r * 0.2,
                  fill=shade(col, -0.4), width=2, tags=tag)
    c.create_line(cx, cy - r * 0.75, cx, cy + r * 0.75,
                  fill=shade(col, -0.4), width=2, tags=tag)


def icon_wire(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
              tag: str = "ico") -> None:
    """铁丝网（荆棘 / 反伤）。"""
    for k in (-1, 0, 1):
        c.create_line(cx - r, cy + k * r * 0.45, cx + r, cy + k * r * 0.45,
                      fill=col, width=2, tags=tag)
    for i in range(4):
        px = cx - r + 2 * r * i / 3.0
        c.create_line(px - r * 0.15, cy - r * 0.6, px + r * 0.15, cy + r * 0.6,
                      fill=col, width=1, tags=tag)


# --------------------------------------------------------------------------- #
# 7. 地图 / 界面装饰
# --------------------------------------------------------------------------- #
def arrow_head(c: tk.Canvas, x: float, y: float, angle: float, size: float,
               col: str, tag: str = "deco") -> None:
    a = math.radians(angle)
    pts = []
    for da, rr in ((0, size), (2.5, size * 0.75), (-2.5, size * 0.75)):
        pts.extend((x + math.cos(a + da) * rr, y + math.sin(a + da) * rr))
    c.create_polygon(pts, fill=col, outline="", tags=tag)


def ribbon(c: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
           col: str, tag: str = "deco") -> None:
    """丝带横幅（标题底衬）。"""
    h = (y2 - y1) / 2.0
    poly(c, [x1, y1, x2, y1, x2 - h * 0.6, (y1 + y2) / 2, x2, y2, x1, y2,
             x1 + h * 0.6, (y1 + y2) / 2], fill=col, outline="", tags=tag)


def medal(c: tk.Canvas, cx: float, cy: float, r: float, col: str,
          tag: str = "deco") -> None:
    """勋章：绶带 + 圆章 + 星。"""
    poly(c, [cx - r * 0.5, cy - r * 1.5, cx + r * 0.5, cy - r * 1.5,
             cx + r * 0.3, cy - r * 0.4, cx - r * 0.3, cy - r * 0.4],
         fill=shade(col, -0.3), outline="", tags=tag)
    c.create_oval(cx - r, cy - r * 0.55, cx + r, cy + r * 1.05, fill=col,
                  outline=shade(col, -0.45), width=2, tags=tag)
    star(c, cx, cy + r * 0.25, r * 0.52, TEXT, tag)


__all__ = [
    "battlefield", "ruins", "smoke_band", "horizon_glow",
    "make_smoke_sprites", "draw_smoke_cloud", "tracer",
    "tank", "hq", "star",
    "enemy_tank", "enemy_infantry", "enemy_plane", "enemy_fortress",
    "enemy_artillery", "enemy_soldier_elite", "enemy_generic",
    "ENEMY_ART", "draw_enemy_unit", "unit_art_for",
    "sandbags", "barbed_wire", "crater", "hedgehog", "map_table",
    "icon_shield", "icon_burst", "icon_gear", "icon_supply", "icon_wire",
    "arrow_head", "ribbon", "medal",
    "lerp", "alpha_on", "shade", "rounded",
]
