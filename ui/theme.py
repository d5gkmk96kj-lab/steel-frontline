"""
钢铁战线 — UI 主题层 (theme.py)
================================================================
军事题材（二战装甲战争）：硝烟褐 / 军绿 / 钢灰 + 弹壳金，
做旧纸张与铆接钢板质感。字体 / 尺寸 / 以及全部基于 tk.Canvas 的手绘工具。

设计约束
--------
* 纯标准库：只用 ``tkinter``，**零第三方依赖**。
* 本模块 **不阻塞主线程**，不做任何动画调度（动画在 widgets.py 用 ``after``）。
* 本模块可以脱离项目其它模块单独 import。
* Tk 的 Canvas 没有 alpha 通道，所有"半透明"效果用 :func:`with_alpha_on`
  手工混色模拟。

坐标系：屏幕像素，原点左上，y 轴向下。
================================================================
"""

from __future__ import annotations

import math
import random
import sys
import tkinter as tk
from tkinter import font as tkfont

__all__ = [
    # 调色板
    "BG_DEEP", "BG", "PANEL", "PANEL_HI", "PANEL_LO", "BORDER", "BORDER_HI",
    "CYAN", "CYAN_DIM", "CYAN_DARK", "GOLD", "GOLD_DIM", "BLOOD", "BLOOD_DIM",
    "POISON", "POISON_DIM", "TEXT", "TEXT_DIM", "TEXT_FAINT", "WHITE", "BLACK",
    "BLOCK_BLUE", "BLOCK_BLUE_DIM", "ENERGY_YELLOW", "HP_RED", "HP_GHOST",
    "RARITY_COLORS", "TYPE_COLORS", "ARCH_COLORS", "INTENT_COLORS",
    "BUFF_COLORS", "NODE_COLORS",
    # 字体
    "FONT_FAMILY", "MONO_FAMILY", "pick_font_family",
    "FONT_TITLE", "FONT_H1", "FONT_H2", "FONT_BODY", "FONT_SMALL",
    "FONT_TINY", "FONT_NUM", "FONT_NUM_BIG", "FONT_CARD_NAME", "FONT_CARD_TEXT",
    "FONT_BUTTON", "FONT_MONO",
    # 尺寸
    "WIN_W", "WIN_H", "MIN_WIN_W", "MIN_WIN_H",
    "CARD_W", "CARD_H", "CARD_RADIUS", "CARD_ARC", "CARD_GAP",
    "HAND_Y", "HAND_ARC_HEIGHT", "HAND_MAX_ROT", "HAND_HOVER_LIFT",
    "ENERGY_ORB_R", "ENERGY_ORB_POS", "END_TURN_BTN", "DRAW_PILE_POS",
    "DISCARD_PILE_POS", "EXHAUST_PILE_POS", "PLAYER_POS", "ENEMY_ROW_Y",
    "HPBAR_W", "HPBAR_H", "RELIC_SIZE", "BUFF_SIZE", "PAD", "PAD_S", "PAD_L",
    "RADIUS_S", "RADIUS_M", "RADIUS_L", "SHADOW_SPREAD",
    # 工具函数
    "hex_to_rgb", "rgb_to_hex", "lerp_color", "with_alpha_on", "shade",
    "rarity_color", "type_color", "arch_color", "intent_color", "buff_color",
    "node_color", "hp_color",
    # Canvas 绘制
    "round_rect", "round_rect_points", "vgradient", "hgradient", "shadow",
    "glow_ring", "draw_arc_text", "text_size", "wrap_text_cjk",
    "slice_text_cjk", "star_polygon", "crystal_polygon", "init_fonts",
    "make_font",
]


# =====================================================================
# 1. 调色板
# =====================================================================

# --- 背景 / 面板（附录 B.2：硝烟黑褐 / 沙盘钢板）---------------------
BG_DEEP = "#12100D"     # 最底层背景：硝烟黑褐
BG = "#1A1712"          # 常规背景
PANEL = "#24201A"       # 面板底：沙盘 / 钢板
PANEL_HI = "#322C23"    # 面板高光 / 悬停态
PANEL_LO = "#141210"    # 面板凹陷 / 输入框
BORDER = "#3E372C"      # 常规描边
BORDER_HI = "#5A5040"   # 高亮描边

# --- 军事质感新增色（附录 B.2）---------------------------------------
STEEL = "#5A6470"       # 钢灰：装甲、金属件
SMOKE = "#3A3630"       # 硝烟灰
RUST = "#8B5A2B"        # 锈迹

# --- 强调色 -----------------------------------------------------------
CYAN = "#6B7F3A"        # 军绿强调（原青色；变量名保留，值改为军绿）
CYAN_DIM = "#4E5D2A"    # 军绿暗部
CYAN_DARK = "#232B14"   # 军绿极暗（用于填充底）
GOLD = "#C9A227"        # 弹壳金：稀有、金币、能量球
GOLD_DIM = "#8A6F1A"
BLOOD = "#A8322D"       # 战损红：伤害、敌人、危险
BLOOD_DIM = "#6E211E"
POISON = "#B5651D"      # 燃烧橙（原毒绿；语义不变）
POISON_DIM = "#7A4413"

# --- 文本（泛黄纸白）--------------------------------------------------
TEXT = "#E8E2D4"        # 主文本
TEXT_DIM = "#A89E8A"    # 次要文本
TEXT_FAINT = "#6E6656"  # 极弱文本 / 禁用
WHITE = "#FFFFFF"
BLACK = "#000000"

# --- A.5 冻结别名（附录 A.5 按这些名字冻结；两套拼写都保留）---------
BG_DARK = "#1A1712"         # A.5: BG_DARK
PANEL_LIGHT = PANEL_HI      # A.5: PANEL_LIGHT
TEXT_MUTED = TEXT_FAINT     # A.5: TEXT_MUTED

GREEN = "#6B7F3A"           # A.5: GREEN（军绿）
RED = "#A8322D"             # A.5: RED（战损红）
ORANGE = "#B5651D"          # A.5: ORANGE（燃烧橙）

# --- 功能色 -----------------------------------------------------------
BLOCK_BLUE = "#7C8B99"      # 掩体：钢灰蓝
BLOCK_BLUE_DIM = "#4C5866"
ENERGY_YELLOW = "#D8C071"   # 补给
HP_RED = "#8E2B26"          # 血条实色
HP_GHOST = "#E8E2D4"        # 延迟掉血残影（泛黄纸白）

# --- 稀有度（制式 / 常规 / 精锐 / 传奇）------------------------------
RARITY_BASIC = "#7A7A72"    # 制式：灰钢
RARITY_COMMON = "#A8B0A0"   # 常规
RARITY_UNCOMMON = "#6B7F3A"  # 精锐：军绿
RARITY_RARE = "#C9A227"     # 传奇：弹壳金
RARITY_SPECIAL = "#B5651D"  # 特殊：燃烧橙

#: A.5: PURPLE（须定义在 RARITY_SPECIAL 之后）
PURPLE = RARITY_SPECIAL

RARITY_NAMES = {
    "basic": "制式",
    "common": "常规",
    "uncommon": "精锐",
    "rare": "传奇",
    "special": "特殊",
    "starter": "制式",
    "boss": "王牌",
    "shop": "补给",
}

RARITY_COLORS = {
    "basic": RARITY_BASIC,
    "common": RARITY_COMMON,
    "uncommon": RARITY_UNCOMMON,
    "rare": RARITY_RARE,
    "special": RARITY_SPECIAL,
    "starter": RARITY_BASIC,
    "boss": RARITY_SPECIAL,
    "shop": RARITY_UNCOMMON,
}

# --- 卡牌类型（攻击 / 战术 / 指令）-----------------------------------
TYPE_COLORS = {
    "attack": "#A8322D",     # 攻击：战损红
    "skill": "#6B7F3A",      # 战术：军绿
    "power": "#C9A227",      # 指令：弹壳金
    "status": "#7A7A72",     # 状态：灰钢
    "curse": "#6E3B36",      # 诅咒：暗锈红
}

TYPE_NAMES = {
    "attack": "攻击",
    "skill": "战术",
    "power": "指令",
    "status": "状态",
    "curse": "诅咒",
}

# --- 流派（突击 / 防御 / 燃烧弹 / 后勤 / 支援）-----------------------
ARCH_COLORS = {
    "attack": "#A8322D",     # 突击：战损红
    "block": "#7C8B99",      # 防御：钢灰
    "poison": "#B5651D",     # 燃烧弹：燃烧橙
    "energy": "#6B7F3A",     # 后勤：军绿
    "summon": "#8B5A2B",     # 支援：锈褐
}

ARCH_NAMES = {
    "attack": "突击",
    "block": "防御",
    "poison": "燃烧弹",
    "energy": "后勤",
    "summon": "支援",
}

# --- 敌人意图 ---------------------------------------------------------
INTENT_COLORS = {
    "attack": "#A8322D",
    "attack_debuff": "#A8322D",
    "attack_defend": "#8B5A2B",
    "defend": "#7C8B99",
    "buff": "#C9A227",
    "debuff": "#B5651D",
    "sleep": "#7A7A72",
    "unknown": "#A89E8A",
}

# --- Buff -------------------------------------------------------------
BUFF_COLORS = {
    "strength": "#A8322D",      # 火力
    "strength_down": "#6E211E",  # 弹药短缺
    "dexterity": "#6B7F3A",     # 机动
    "vulnerable": "#C9A227",    # 破甲
    "weak": "#8B5A2B",          # 压制
    "frail": "#7A7A72",         # 混乱
    "poison": "#B5651D",        # 燃烧
    "thorns": "#5A6470",        # 铁丝网
    "metallicize": "#7C8B99",   # 工事
    "ritual": "#C9A227",        # 增援
    "artifact": "#8FA05A",      # 干扰弹
    "plated_armor": "#8A94A0",  # 装甲板
    "regenerate": "#5E8C4A",    # 战地医疗
    "intangible": "#B8B0A0",    # 烟幕
    "barrier": "#5A7C99",       # 坚守
    "chain": "#C9A227",         # 连射
    "envenom": "#B5651D",       # 燃烧弹
    "accuracy": "#D8C071",      # 瞄准
}

# --- 地图节点（战区推进图）-------------------------------------------
NODE_COLORS = {
    "battle": "#A8322D",     # 遭遇战
    "elite": "#8B5A2B",      # 精锐部队
    "event": "#B5651D",      # 战场事件
    "shop": "#C9A227",       # 补给站
    "rest": "#6B7F3A",       # 战地医院
    "treasure": "#C9A227",   # 缴获
    "boss": "#8E2B26",       # 要塞 / 王牌
}

# --- A.5 冻结：name -> hex 总表 ---------------------------------------
# 允许用 `theme.COLORS["cyan"]` 或 `theme.color("cyan")` 按名取色。
COLORS = {
    "bg_deep": BG_DEEP,
    "bg_dark": BG_DARK,
    "bg": BG,
    "panel": PANEL,
    "panel_hi": PANEL_HI,
    "panel_light": PANEL_LIGHT,
    "panel_lo": PANEL_LO,
    "border": BORDER,
    "border_hi": BORDER_HI,
    "cyan": CYAN,
    "cyan_dim": CYAN_DIM,
    "cyan_dark": CYAN_DARK,
    "gold": GOLD,
    "gold_dim": GOLD_DIM,
    "blood": BLOOD,
    "red": RED,
    "poison": POISON,
    "green": GREEN,
    "purple": PURPLE,
    "orange": ORANGE,
    "block": BLOCK_BLUE,
    "energy": ENERGY_YELLOW,
    "hp": HP_RED,
    "hp_ghost": HP_GHOST,
    "text": TEXT,
    "text_dim": TEXT_DIM,
    "text_faint": TEXT_FAINT,
    "text_muted": TEXT_MUTED,
    "white": WHITE,
    "black": BLACK,
    # 军事质感（附录 B.2）
    "steel": STEEL,
    "smoke": SMOKE,
    "rust": RUST,
    "khaki": "#8A8259",
    "canvas": "#6E6A52",
}
# 语义别名补全：app.py 会按这些名字取色，缺失时会兜底成 TEXT(浅色)，
# 曾导致淡入遮罩变成整屏白（用户可见的「黑屏」实为白屏）。
COLORS.setdefault("bg_abyss", COLORS.get("panel_lo", BG_DEEP))
COLORS.setdefault("bg_mid", COLORS.get("panel", PANEL))
COLORS.setdefault("ground_top", COLORS.get("border_hi", BORDER_HI))
COLORS.setdefault("ground_bottom", COLORS.get("bg_deep", BG_DEEP))
COLORS.setdefault("panel_dark", COLORS.get("panel_lo", PANEL_LO))
COLORS.setdefault("text_mute", COLORS.get("text_faint", TEXT_FAINT))
COLORS.setdefault("gold_dark", COLORS.get("gold_dim", GOLD_DIM))
COLORS.setdefault("energy_dark", COLORS.get("gold_dim", GOLD_DIM))
COLORS.setdefault("hp_dark", COLORS.get("blood", BLOOD))
COLORS.setdefault("border_light", COLORS.get("cyan", CYAN))
COLORS.setdefault("glow", COLORS.get("cyan", CYAN))
COLORS.setdefault("good", COLORS.get("poison", POISON))
COLORS.setdefault("bad", COLORS.get("blood", BLOOD))
COLORS.setdefault("danger", COLORS.get("blood", BLOOD))
COLORS.setdefault("buff", COLORS.get("gold", GOLD))
COLORS.setdefault("debuff", COLORS.get("purple", "#B07BE8"))



def color(name, default=None):
    """按名字取色（A.5 冻结）。未知名字返回 ``default``（默认 ``TEXT``）。

    带 ``#`` 前缀的字符串会被原样返回，便于混用常量与字面量。
    """
    if name is None:
        return default if default is not None else TEXT
    if isinstance(name, str) and name.startswith("#"):
        return name
    key = str(name).strip().lower()
    v = COLORS.get(key)
    if isinstance(v, str) and v.startswith("#"):
        return v
    if default is not None:
        return default
    # 未知名字兜底成深色背景，而不是文字色 —— 否则会把整个画面刷白
    return COLORS.get("bg_deep", BG_DEEP)


# 目录里最后注册一次（须在 COLORS 定义之后），把 dict 也挂上去
__all__.extend([
    "COLORS", "color", "BG_DEEP", "BG_DARK", "PANEL", "PANEL_LIGHT", "BORDER",
    "TEXT", "TEXT_DIM", "TEXT_MUTED", "GOLD", "CYAN", "GREEN", "RED", "PURPLE",
    "ORANGE", "rgb", "mix", "font", "get_font", "draw_text_center", "make_font",
    "FONT_H2", "ARCH_NAMES", "round_rect_points", "hgradient", "star_polygon",
    "crystal_polygon", "glow_ring", "slice_text_cjk", "shade", "intent_color",
    "buff_color", "node_color", "hp_color", "MONO_FAMILY", "FONT_FAMILY",
    "init_fonts", "text_size", "wrap_text_cjk", "CARD_ARC", "CARD_GAP",
    "HAND_Y", "HAND_ARC_HEIGHT", "HAND_MAX_ROT", "HAND_HOVER_LIFT",
    "HAND_HOVER_SCALE", "HAND_FAN_MAX", "ENERGY_ORB_R", "ENERGY_ORB_POS",
    "END_TURN_BTN", "DRAW_PILE_POS", "DISCARD_PILE_POS", "EXHAUST_PILE_POS",
    "PLAYER_POS", "ENEMY_ROW_Y", "ENEMY_SLOT_X", "HPBAR_W", "HPBAR_H",
    "RELIC_SIZE", "BUFF_SIZE", "PAD", "PAD_S", "PAD_L", "RADIUS_S",
    "RADIUS_M", "RADIUS_L", "SHADOW_SPREAD", "WIN_W", "WIN_H", "MIN_WIN_W",
    "MIN_WIN_H", "BLOCK_BLUE", "ENERGY_YELLOW", "HP_RED", "HP_GHOST",
    "RARITY_BASIC", "RARITY_COMMON", "RARITY_UNCOMMON", "RARITY_RARE",
    "RARITY_SPECIAL", "BUFF_COLORS", "INTENT_COLORS", "NODE_COLORS",
    "FONT_NUM_BIG", "FONT_CARD_NAME", "FONT_CARD_TEXT", "FONT_BUTTON",
    "FONT_MONO", "shadow", "draw_arc_text", "_is_wide", "hex_to_rgb",
    "rgb_to_hex",
    # 附录 B 军事质感
    "STEEL", "SMOKE", "RUST", "rivet", "wear_edge", "paper_texture",
    "stencil_text", "steel_panel", "tape_corner", "RARITY_NAMES", "TYPE_NAMES",
])


# =====================================================================
# 2. 字体
# =====================================================================

_FONT_PREFS = [
    "PingFang SC",          # macOS 中文首选
    "Hiragino Sans GB",     # macOS 中文回退
    "Heiti SC",
    "Helvetica Neue",       # 拉丁回退
    "Helvetica",
    "Arial Unicode MS",
    "Microsoft YaHei",      # Windows
    "Noto Sans CJK SC",     # Linux
    "DejaVu Sans",
    "TkDefaultFont",
]

_MONO_PREFS = ["Menlo", "SF Mono", "Monaco", "Consolas", "DejaVu Sans Mono", "Courier"]

_font_cache = {}
FONT_FAMILY = None      # 由 init_fonts() / 模块加载时确定
MONO_FAMILY = None


def pick_font_family(prefs=None, root=None):
    """从候选列表里挑第一个系统真正拥有的字体族。

    **绝不自行创建 Tk root。** 早期实现在 import 时临时 ``tk.Tk()`` 再
    ``destroy()``，在 macOS + Python 3.9 + Tk 8.5 上会让**之后**新建的 root
    在 ``mainloop()`` 里直接段错误（SIGSEGV）——整个程序无法启动。
    因此这里只在「已经有 root」时查询字体；没有 root 就返回候选表首项，
    之后由 :func:`init_fonts` 在 App 建好 root 后再精确解析。
    """
    prefs = list(prefs or _FONT_PREFS)
    try:
        if root is None:
            root = tk._default_root  # noqa: SLF001
        if root is None:
            return prefs[0]          # 无 root：不建 root，安全退化
        available = set(tkfont.families(root))
        for fam in prefs:
            if fam in available:
                return fam
    except Exception:
        pass
    return prefs[0]


def init_fonts(root=None, force=False):
    """确定字体族。**App 建好 root 之后**调用一次即可；重复调用是幂等的。

    这是字体得以精确解析（真正命中 "PingFang SC"）的唯一时机。
    """
    global FONT_FAMILY, MONO_FAMILY, FONT_TITLE, FONT_H1, FONT_H2, FONT_BODY
    global FONT_SMALL, FONT_TINY, FONT_NUM, FONT_NUM_BIG, FONT_CARD_NAME
    global FONT_CARD_TEXT, FONT_BUTTON, FONT_MONO
    if root is None:
        root = tk._default_root  # noqa: SLF001
    if FONT_FAMILY is None or force:
        FONT_FAMILY = pick_font_family(_FONT_PREFS, root)
    if MONO_FAMILY is None or force:
        MONO_FAMILY = pick_font_family(_MONO_PREFS, root)
    # 重建所有字体元组，使其采用解析后的字体族
    FONT_TITLE = make_font(34, "bold")
    FONT_H1 = make_font(24, "bold")
    FONT_H2 = make_font(18, "bold")
    FONT_BODY = make_font(14)
    FONT_SMALL = make_font(12)
    FONT_TINY = make_font(10)
    FONT_NUM = make_font(15, "bold")
    FONT_NUM_BIG = make_font(26, "bold")
    FONT_CARD_NAME = make_font(14, "bold")
    FONT_CARD_TEXT = make_font(11)
    FONT_BUTTON = make_font(15, "bold")
    FONT_MONO = (MONO_FAMILY, 12)
    return FONT_FAMILY


# 模块加载时**不创建任何 Tk root**（见 pick_font_family 的说明）。
# 先用首选名占位；App 启动后调 init_fonts(root) 精确解析系统字体。
FONT_FAMILY = _FONT_PREFS[0]
MONO_FAMILY = _MONO_PREFS[0]


def make_font(size=14, weight="normal", slant="roman", family=None, underline=False):
    """返回 Tk 字体元组 ``(family, size, style...)``。

    元组形式比 ``tkfont.Font`` 对象轻量、可跨 Tk 实例复用，且中文正常。
    """
    fam = family or FONT_FAMILY or _FONT_PREFS[0]
    style = []
    if weight and weight != "normal":
        style.append(weight)
    if slant and slant != "roman":
        style.append(slant)
    if underline:
        style.append("underline")
    return (fam, size) + tuple(style) if style else (fam, size)


def font(size=14, bold=False, family=None, slant="roman"):
    """A.5 冻结的字体工厂：``font(16, bold=True)`` -> ``("PingFang SC", 16, "bold")``。

    返回值可直接给 ``canvas.create_text(font=...)``。
    """
    return make_font(size, "bold" if bold else "normal", slant, family=family)


def get_font(spec):
    """规范化字体规格（A.5 冻结）。

    接受：``None`` / ``int``（字号）/ ``(family, size[, style...])`` 元组 /
    已构造的 :class:`tkinter.font.Font` 对象。返回一个可直接传给 Tk 的字体元组。
    """
    if spec is None:
        return FONT_BODY
    if isinstance(spec, tuple):
        return spec
    if isinstance(spec, int):
        return font(spec)
    if isinstance(spec, str):
        return (spec, FONT_BODY[1]) + tuple(FONT_BODY[2:])
    try:                                   # tkfont.Font 实例 -> (family, size, style)
        fam = spec.actual("family")
        size = spec.actual("size")
        style = []
        if spec.actual("weight") == "bold":
            style.append("bold")
        if spec.actual("slant") == "italic":
            style.append("italic")
        return (fam, size) + tuple(style)
    except Exception:
        return FONT_BODY


# 具体字号常量（元组，可直接传给 canvas 的 font= 参数）
FONT_TITLE = make_font(34, "bold")
FONT_H1 = make_font(24, "bold")
FONT_H2 = make_font(18, "bold")
FONT_BODY = make_font(14)
FONT_SMALL = make_font(12)
FONT_TINY = make_font(10)
FONT_NUM = make_font(15, "bold")
FONT_NUM_BIG = make_font(26, "bold")
FONT_CARD_NAME = make_font(14, "bold")
FONT_CARD_TEXT = make_font(11)
FONT_BUTTON = make_font(15, "bold")
FONT_MONO = (MONO_FAMILY, 12)


# =====================================================================
# 3. 尺寸 / 布局常量
# =====================================================================

WIN_W, WIN_H = 1440, 900
MIN_WIN_W, MIN_WIN_H = 1280, 800

# --- 卡牌 ---
CARD_W = 168
CARD_H = 236
CARD_RADIUS = 12
CARD_ARC = 10           # 圆角矩形的平滑程度
CARD_GAP = 8            # 卡与卡的水平间隙

# --- 手牌区（战斗界面主 Canvas 上的弧线布局） ---
HAND_Y = 742            # 手牌中心的 y（未悬停）
HAND_ARC_HEIGHT = 46    # 弧线两端相对中心的下沉量
HAND_MAX_ROT = 8.0      # 弧线两端的最大旋转角（度）
HAND_HOVER_LIFT = 34    # 悬停时上浮像素
HAND_HOVER_SCALE = 1.18  # 悬停时放大倍率
HAND_FAN_MAX = 10       # 超过这个张数就压缩间距

# --- 能量球 ---
ENERGY_ORB_R = 42
ENERGY_ORB_POS = (128, 700)

# --- 结束回合按钮 ---
END_TURN_BTN = (1230, 690, 1400, 760)   # x1,y1,x2,y2

# --- 牌堆 ---
DRAW_PILE_POS = (112, 812)
DISCARD_PILE_POS = (1328, 812)
EXHAUST_PILE_POS = (1120, 812)

# --- 角色站位 ---
PLAYER_POS = (300, 470)
ENEMY_ROW_Y = 360
ENEMY_SLOT_X = (760, 980, 1200)

# --- 血条 ---
HPBAR_W = 220
HPBAR_H = 22

# --- 遗物 / buff ---
RELIC_SIZE = 34
BUFF_SIZE = 26

# --- 通用间距 ---
PAD = 12
PAD_S = 6
PAD_L = 24
RADIUS_S = 6
RADIUS_M = 10
RADIUS_L = 16
SHADOW_SPREAD = 6


# =====================================================================
# 4. 颜色工具
# =====================================================================

def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def hex_to_rgb(color):
    """``"#RRGGBB"`` / ``"#RGB"`` / 颜色名 -> ``(r, g, b)``，0..255。"""
    if isinstance(color, (tuple, list)):
        r, g, b = color[0], color[1], color[2]
        return (int(r), int(g), int(b))
    s = str(color).strip()
    if not s.startswith("#"):
        # 交给 Tk 解释颜色名
        try:
            root = tk._default_root  # noqa: SLF001
            name = root.winfo_rgb(s) if root is not None else None
            if name:
                return (name[0] >> 8, name[1] >> 8, name[2] >> 8)
        except Exception:
            pass
        return (255, 255, 255)
    s = s[1:]
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 8:     # #RRGGBBAA —— 忽略 alpha，仅取 RGB
        s = s[:6]
    if len(s) != 6:
        return (255, 255, 255)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (255, 255, 255)


def rgb_to_hex(rgb):
    """``(r, g, b)`` -> ``"#rrggbb"``，输入会被截断并夹紧到 0..255。"""
    r, g, b = (int(_clamp(round(c), 0, 255)) for c in rgb[:3])
    return "#%02x%02x%02x" % (r, g, b)


def lerp_color(c1, c2, t):
    """在两色之间线性插值；``t=0`` 返回 c1，``t=1`` 返回 c2。"""
    t = _clamp(float(t))
    a = hex_to_rgb(c1)
    b = hex_to_rgb(c2)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def with_alpha_on(bg, fg, alpha):
    """把 ``fg`` 以 ``alpha``(0..1) 的透明度叠在 ``bg`` 上，返回不透明 hex。

    Tk 8.5 没有 alpha 通道，这里手工做 source-over 混色来**模拟**半透明。
    """
    a = _clamp(float(alpha))
    b = hex_to_rgb(bg)
    f = hex_to_rgb(fg)
    return rgb_to_hex(tuple(b[i] + (f[i] - b[i]) * a for i in range(3)))


def shade(color, amount):
    """变亮(``amount>0``)或变暗(``amount<0``)；amount 取 -1..1。"""
    amount = _clamp(float(amount), -1.0, 1.0)
    target = "#FFFFFF" if amount > 0 else "#000000"
    return lerp_color(color, target, abs(amount))


# --- A.5 冻结别名 -----------------------------------------------------
#: A.5: ``rgb(hex) -> (r, g, b)``
rgb = hex_to_rgb
#: A.5: ``mix(bg, fg, alpha) -> hex``，Tk 无 alpha 通道时的半透明模拟
mix = with_alpha_on


def _lookup(table, key, default):
    if key is None:
        return default
    if key in table:
        return table[key]
    k = str(key).lower().strip()
    if k in table:
        return table[k]
    return default


def rarity_color(rarity):
    """稀有度 -> hex。未知值回退到 common 的灰色。"""
    return _lookup(RARITY_COLORS, rarity, RARITY_COMMON)


def type_color(ctype):
    """卡牌类型 -> hex。attack/skill/power/status/curse。"""
    return _lookup(TYPE_COLORS, ctype, TEXT_DIM)


def arch_color(arch):
    """流派 -> hex。attack/block/poison/energy/summon。"""
    return _lookup(ARCH_COLORS, arch, CYAN)


def intent_color(intent):
    """敌人意图 -> hex。"""
    return _lookup(INTENT_COLORS, intent, TEXT_DIM)


def buff_color(key):
    """buff key -> hex。未知 buff 返回青色。"""
    return _lookup(BUFF_COLORS, key, CYAN)


def node_color(kind):
    """地图节点类型 -> hex。"""
    return _lookup(NODE_COLORS, kind, TEXT_DIM)


def hp_color(ratio):
    """血条按血量比例取色：>0.5 绿, >0.25 金, 否则血红。"""
    r = _clamp(float(ratio))
    if r > 0.5:
        return "#5FD07A"
    if r > 0.25:
        return GOLD
    return BLOOD


# =====================================================================
# 5. Canvas 手绘工具
# =====================================================================

def round_rect_points(x1, y1, x2, y2, r, samples=None):
    """返回圆角矩形的多边形点序列（配合 ``create_polygon(..., smooth=True)``）。

    用密集采样而非稀疏四角点，保证 Tk 的样条渲染出来就是圆角矩形而不是"馒头"。
    """
    x1, x2 = (x1, x2) if x1 <= x2 else (x2, x1)
    y1, y2 = (y1, y2) if y1 <= y2 else (y2, y1)
    r = max(0.0, min(float(r), (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    if r <= 0.5:
        return [x1, y1, x2, y1, x2, y2, x1, y2]
    if samples is None:
        samples = max(3, int(r / 2) + 2)
    pts = []
    # 四个圆心与起始角（顺时针，屏幕坐标 y 向下）
    corners = (
        (x2 - r, y1 + r, -90.0),   # 右上
        (x2 - r, y2 - r, 0.0),     # 右下
        (x1 + r, y2 - r, 90.0),    # 左下
        (x1 + r, y1 + r, 180.0),   # 左上
    )
    for cx, cy, start in corners:
        for i in range(samples + 1):
            ang = math.radians(start + 90.0 * i / samples)
            pts.extend((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def round_rect(canvas, x1, y1, x2, y2, r=RADIUS_M, **kw):
    """在 canvas 上画一个**圆角矩形**，返回 canvas item id。

    与 ``create_rectangle`` 的参数风格一致，额外支持：
    ``fill`` / ``outline`` / ``width`` / ``dash`` / ``stipple`` / ``tags`` 等。
    实现方式为 ``create_polygon(smooth=True)``，因此也被 Canvas 原生缩放影响。

    传 ``nofill=True`` 可只描边（避免 Tk 对小 r 的填充溢出）。
    """
    nofill = kw.pop("nofill", False)
    if nofill:
        kw.setdefault("fill", "")
    pts = round_rect_points(x1, y1, x2, y2, r)
    kw.setdefault("smooth", True)
    kw.setdefault("splinesteps", 12)
    return canvas.create_polygon(pts, **kw)


def draw_text_center(canvas, x, y, text, font=None, fill=TEXT, **kw):
    """A.5 冻结：在 ``(x, y)`` 居中画一行文字，返回 item id。

    多余关键字参数原样透传给 ``canvas.create_text``（如 ``tags`` / ``width``）。
    """
    kw.setdefault("anchor", "center")
    return canvas.create_text(x, y, text=text, font=font or FONT_BODY,
                              fill=fill, **kw)


def vgradient(canvas, x1, y1, x2, y2, c1, c2, steps=40, tags=None, stipple=None):
    """**垂直线性渐变**：从上往下画 ``steps`` 条水平细线，颜色 c1 -> c2。

    零依赖实现。返回创建的 item id 列表。
    线条会首尾重叠 1px 以避免缩放时出现缝隙。
    """
    steps = max(2, int(steps))
    x1, x2 = (x1, x2) if x1 <= x2 else (x2, x1)
    y1, y2 = (y1, y2) if y1 <= y2 else (y2, y1)
    h = float(y2 - y1)
    band = h / steps
    items = []
    for i in range(steps):
        t = i / float(steps - 1) if steps > 1 else 0.0
        col = lerp_color(c1, c2, t)
        yy1 = y1 + band * i
        yy2 = y1 + band * (i + 1)
        if i < steps - 1:
            yy2 += 1.0        # 重叠，防缝
        opts = {"fill": col, "outline": "", "width": 0}
        if tags:
            opts["tags"] = tags
        if stipple:
            opts["stipple"] = stipple
        items.append(canvas.create_rectangle(x1, yy1, x2, yy2, **opts))
    return items


def hgradient(canvas, x1, y1, x2, y2, c1, c2, steps=40, tags=None, stipple=None):
    """**水平线性渐变**：从左往右画竖线。返回 item id 列表。"""
    steps = max(2, int(steps))
    x1, x2 = (x1, x2) if x1 <= x2 else (x2, x1)
    y1, y2 = (y1, y2) if y1 <= y2 else (y2, y1)
    w = float(x2 - x1)
    band = w / steps
    items = []
    for i in range(steps):
        t = i / float(steps - 1) if steps > 1 else 0.0
        col = lerp_color(c1, c2, t)
        xx1 = x1 + band * i
        xx2 = x1 + band * (i + 1)
        if i < steps - 1:
            xx2 += 1.0
        opts = {"fill": col, "outline": "", "width": 0}
        if tags:
            opts["tags"] = tags
        if stipple:
            opts["stipple"] = stipple
        items.append(canvas.create_rectangle(xx1, y1, xx2, y2, **opts))
    return items


def shadow(canvas, x1, y1, x2, y2, r=RADIUS_M, spread=SHADOW_SPREAD, base=BG_DEEP,
           layers=4, tags=None, strength=0.55):
    """伪阴影：在形状下方叠若干层逐渐淡出的圆角矩形（向下偏移）。

    Tk 无 alpha，用 :func:`with_alpha_on` 与背景色混色模拟。
    必须在绘制主体**之前**调用。返回 item id 列表。
    """
    spread = max(1, int(spread))
    layers = max(1, int(layers))
    items = []
    for i in range(layers, 0, -1):
        f = i / float(layers)                 # 1 -> 最外层
        off = spread * f
        alpha = strength * (1.0 - f) ** 1.6 + 0.06
        col = with_alpha_on(base, "#000000", min(0.9, alpha))
        kw = {"fill": col, "outline": ""}
        if tags:
            kw["tags"] = tags
        items.append(round_rect(canvas, x1 - off * 0.5, y1 + off * 0.55,
                                x2 + off * 0.5, y2 + off * 0.85,
                                r + off * 0.5, **kw))
    return items


def glow_ring(canvas, x1, y1, x2, y2, r, color, width=2, spread=4, layers=3,
              base=PANEL, tags=None):
    """在形状外围画一圈**发光描边**（逐层变淡、变粗）。

    用于稀有度描边 / 悬停高亮。返回 item id 列表（由外到内）。
    """
    items = []
    for i in range(layers, 0, -1):
        f = i / float(layers)
        col = with_alpha_on(base, color, 0.10 + 0.28 * (1.0 - f))
        kw = {"outline": col, "width": max(1, int(width + spread * f)),
              "nofill": True, "smooth": True}
        if tags:
            kw["tags"] = tags
        items.append(round_rect(canvas, x1 - spread * f * 0.5, y1 - spread * f * 0.5,
                                x2 + spread * f * 0.5, y2 + spread * f * 0.5,
                                r + spread * f * 0.5, **kw))
    return items


def rivet(canvas, x, y, r=4, color=None, base=None, tags=None):
    """**铆钉**：军事钢板的标志性细节。

    画一个带高光与暗边的实心圆，视觉上像半圆头铆钉。返回 item id 列表。
    """
    color = color or STEEL
    base = base or PANEL
    r = max(1.0, float(r))
    items = []
    opts = {"tags": tags} if tags else {}
    # 外圈阴影
    items.append(canvas.create_oval(x - r, y - r * 0.85, x + r, y + r * 1.15,
                                    fill=with_alpha_on(base, "#000000", 0.45),
                                    outline="", **opts))
    # 钉体
    items.append(canvas.create_oval(x - r, y - r, x + r, y + r,
                                    fill=color, outline=shade(color, -0.45),
                                    width=1, **opts))
    # 左上高光
    items.append(canvas.create_oval(x - r * 0.55, y - r * 0.6,
                                    x + r * 0.15, y - r * 0.05,
                                    fill=with_alpha_on(color, WHITE, 0.45),
                                    outline="", **opts))
    return items


def wear_edge(canvas, x1, y1, x2, y2, r=RADIUS_M, color=None, base=None,
              n=14, rng=None, tags=None, wobble=0.30):
    """**磨损边缘**：沿圆角矩形轮廓画一圈不规则的短划痕/缺口。

    用少量随机短线叠加描边，营造"用旧的钢板/纸张"质感。返回 item id 列表。
    传入固定的 ``rng``（``random.Random``）可得到稳定可复现的磨损图案。
    """
    color = color or RUST
    base = base or PANEL
    rng = rng or random.Random(7)
    d = max(0.0, float(wobble))
    items = []
    opts = {"tags": tags} if tags else {}
    x1, x2 = (x1, x2) if x1 <= x2 else (x2, x1)
    y1, y2 = (y1, y2) if y1 <= y2 else (y2, y1)
    pts = round_rect_points(x1, y1, x2, y2, r)
    total = len(pts) // 2
    if total < 3:
        return items
    for _ in range(max(1, int(n))):
        i = rng.randrange(total)
        px, py = pts[i * 2], pts[i * 2 + 1]
        nx = px + rng.uniform(-2.0, 2.0) * (1.0 + d)
        ny = py + rng.uniform(-2.0, 2.0) * (1.0 + d)
        L = rng.uniform(2.0, 7.0)
        ang = rng.uniform(0, math.tau)
        col = with_alpha_on(base, color, rng.uniform(0.20, 0.55))
        items.append(canvas.create_line(nx, ny,
                                        nx + L * math.cos(ang),
                                        ny + L * math.sin(ang),
                                        fill=col, width=1, **opts))
    return items


def paper_texture(canvas, x1, y1, x2, y2, r=0, rng=None, base=None,
                  color=None, n=90, tags=None, dots=True):
    """**做旧纸张斑点**：在矩形内散布细小斑点，模拟泛黄、霉点与纸纹。

    会用 ``stipple`` 做半透明近似。传入固定 ``rng`` 保证可复现。
    返回 item id 列表。
    """
    rng = rng or random.Random(1943)
    base = base or PANEL
    color = color or RUST
    items = []
    opts = {"tags": tags} if tags else {}
    x1, x2 = (x1, x2) if x1 <= x2 else (x2, x1)
    y1, y2 = (y1, y2) if y1 <= y2 else (y2, y1)
    if dots:
        for _ in range(max(0, int(n))):
            px = rng.uniform(x1, x2)
            py = rng.uniform(y1, y2)
            rr = rng.uniform(0.6, 2.4)
            a = rng.uniform(0.10, 0.40)
            items.append(canvas.create_oval(px - rr, py - rr, px + rr, py + rr,
                                            fill=with_alpha_on(base, color, a),
                                            outline="", **opts))
    # 几条淡淡的横向纤维纹
    for _ in range(max(1, int(n) // 30)):
        py = rng.uniform(y1, y2)
        items.append(canvas.create_line(x1, py, x2, py + rng.uniform(-1, 1),
                                        fill=with_alpha_on(base, color, 0.10),
                                        width=1, **opts))
    return items


def stencil_text(canvas, x, y, text, size=16, fill=None, anchor="center",
                 spacing=2, tags=None, bold=True):
    """**军用模板字（stencil）风格**：等宽字体 + 加大字间距。

    通过逐字符定位实现字间距（Tk 无 letter-spacing）。返回 item id 列表。
    """
    fill = fill or TEXT
    font = (MONO_FAMILY or "Courier", size, "bold") if bold else \
           (MONO_FAMILY or "Courier", size)
    text = "" if text is None else str(text)
    if not text:
        return []
    widths = [text_size(ch, font)[0] + spacing for ch in text]
    total = sum(widths) - spacing
    if anchor == "center":
        cx = x - total / 2.0
    elif anchor in ("w", "nw", "sw"):
        cx = x
    elif anchor in ("e", "ne", "se"):
        cx = x - total
    else:
        cx = x - total / 2.0
    items = []
    for ch, w in zip(text, widths):
        kw = {"text": ch, "font": font, "fill": fill, "anchor": "center"}
        if tags:
            kw["tags"] = tags
        items.append(canvas.create_text(cx + w / 2.0, y, **kw))
        cx += w
    return items


def steel_panel(canvas, x1, y1, x2, y2, r=RADIUS_M, base=None, rivet_r=3.5,
                rivet_inset=7, texture=True, rng=None, tags=None, **kw):
    """**铆接钢板**：渐变底板 + 四角铆钉 + 磨损边缘，一次成型。

    这是卡面 / 面板最常用的军事化底材。返回 item id 列表。
    """
    base = base or PANEL
    rng = rng or random.Random(1943)
    items = []
    opts = {"tags": tags} if tags else {}
    items.extend(vgradient(canvas, x1, y1, x2, y2,
                           shade(base, 0.14), shade(base, -0.20),
                           steps=14, tags=tags))
    if texture:
        items.extend(paper_texture(canvas, x1, y1, x2, y2, rng=rng, base=base,
                                   color=SMOKE, n=26, tags=tags))
    items.extend(wear_edge(canvas, x1, y1, x2, y2, r, color=RUST, base=base,
                           n=10, rng=rng, tags=tags))
    if rivet_r:
        for (rx, ry) in ((x1 + rivet_inset, y1 + rivet_inset),
                         (x2 - rivet_inset, y1 + rivet_inset),
                         (x1 + rivet_inset, y2 - rivet_inset),
                         (x2 - rivet_inset, y2 - rivet_inset)):
            items.extend(rivet(canvas, rx, ry, rivet_r, color=STEEL,
                               base=base, tags=tags))
    return items


def tape_corner(canvas, x, y, size=16, color=None, base=None, mode="tl", tags=None):
    """**折角胶带**：卡面四角的做旧折角/胶带，增强纸质与档案感。"""
    color = color or "#9C8C5A"
    base = base or PANEL
    s = float(size)
    if mode in ("tl", "nw"):
        pts = [x, y, x + s, y, x, y + s]
    elif mode in ("tr", "ne"):
        pts = [x, y, x - s, y, x, y + s]
    elif mode in ("bl", "sw"):
        pts = [x, y, x + s, y, x, y - s]
    else:
        pts = [x, y, x - s, y, x, y - s]
    kw = {"tags": tags} if tags else {}
    return [canvas.create_polygon(pts,
                                  fill=with_alpha_on(base, color, 0.55),
                                  outline=with_alpha_on(base, shade(color, -0.3), 0.7),
                                  width=1, **kw)]


def star_polygon(cx, cy, r_out, r_in=None, points=6, rotation=-90.0):
    """星形多边形点序列（用于勋章/图标）。"""
    r_in = r_out * 0.45 if r_in is None else r_in
    pts = []
    n = max(3, int(points)) * 2
    for i in range(n):
        rad = r_out if i % 2 == 0 else r_in
        ang = math.radians(rotation + 360.0 * i / n)
        pts.extend((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def crystal_polygon(cx, cy, r, sides=6, rotation=-90.0, squash=1.0):
    """正多边形/晶体点序列。``squash`` 压缩 y 轴。"""
    pts = []
    for i in range(max(3, int(sides))):
        ang = math.radians(rotation + 360.0 * i / sides)
        pts.extend((cx + r * math.cos(ang), cy + r * math.sin(ang) * squash))
    return pts


# =====================================================================
# 6. 中文文本工具
# =====================================================================

def _is_wide(ch):
    """粗略判断是否为"宽字符"（CJK / 全角），用于换行与宽度估算。"""
    o = ord(ch)
    return (
        0x1100 <= o <= 0x115F or
        0x2E80 <= o <= 0xA4CF or
        0xAC00 <= o <= 0xD7A3 or
        0xF900 <= o <= 0xFAFF or
        0xFE30 <= o <= 0xFE6F or
        0xFF00 <= o <= 0xFF60 or
        0xFFE0 <= o <= 0xFFE6 or
        0x20000 <= o <= 0x3FFFD
    )


def text_size(text, font=None, root=None):
    """估算文本像素尺寸，返回 ``(w, h)``。

    优先使用真实 ``tkfont.Font.measure``；在没有 Tk root 或字体不可用时，
    退化为"每字符宽度估算"，保证任何环境下都不抛异常。
    """
    font = font or FONT_BODY
    text = "" if text is None else str(text)
    if not text:
        return (0, 0)
    fam, size = font[0], font[1]
    try:
        if root is None:
            root = tk._default_root  # noqa: SLF001
        if root is not None:
            key = (fam, size, tuple(font[2:]))
            f = _font_cache.get(key)
            if f is None:
                f = tkfont.Font(root=root, family=fam, size=size,
                                weight="bold" if "bold" in font[2:] else "normal")
                _font_cache[key] = f
            return (f.measure(text), f.metrics("linespace"))
    except Exception:
        pass
    # 估算：宽字符 ≈ 1.0em，窄字符 ≈ 0.55em；行高 ≈ 1.35em
    w = 0.0
    for ch in text:
        w += size * (1.0 if _is_wide(ch) else 0.55)
    return (int(round(w)), int(round(size * 1.35)))


def wrap_text_cjk(text, max_width, font=None, root=None, max_lines=None):
    """**中英混排自动换行**：中文按字符断行，英文/数字按单词断行。

    返回行字符串列表。超过 ``max_lines`` 时最后一行以省略号结尾。
    """
    text = "" if text is None else str(text)
    if not text:
        return []
    max_width = max(8, int(max_width))
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        # 先切成"块"：连续的 ASCII 字母数字算一个词，其余单字符成块
        tokens = []
        buf = ""
        for ch in para:
            if ch.isascii() and (ch.isalnum() or ch in "_-'+#%./:"):
                buf += ch
            else:
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(ch)
        if buf:
            tokens.append(buf)

        for tok in tokens:
            cand = cur + tok
            if cur and text_size(cand, font, root)[0] > max_width:
                lines.append(cur)
                cur = tok if not tok.isspace() else ""
            else:
                cur = cand
        lines.append(cur)

    # 收尾：去掉纯空尾行，处理省略号
    while lines and lines[-1] == "":
        lines.pop()
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and text_size(last + "…", font, root)[0] > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def slice_text_cjk(text, max_width, font=None, root=None):
    """把文本截断到 ``max_width`` 以内，超出部分用 ``…`` 结尾。"""
    text = "" if text is None else str(text)
    if not text:
        return ""
    if text_size(text, font, root)[0] <= max_width:
        return text
    out = ""
    for ch in text:
        if text_size(out + ch + "…", font, root)[0] > max_width:
            break
        out += ch
    return (out + "…") if out else "…"


def draw_arc_text(canvas, x, y, text, font=None, fill=TEXT, anchor="center",
                  angle=0.0, tags=None):
    """在 ``(x, y)`` 画一段带旋转的文字（角度制，逆时针为正）。

    Tk 的 ``create_text`` 只支持 0/90/180/270 的整数 ``angle``，因此小角度
    旋转通过给每个字符单独定位来近似实现（用于手牌弧线扇形的微旋转）。
    返回 item id 列表。
    """
    font = font or FONT_BODY
    text = "" if text is None else str(text)
    angle = float(angle) % 360.0
    if angle == 0.0:
        kw = {"text": text, "font": font, "fill": fill, "anchor": anchor}
        if tags:
            kw["tags"] = tags
        return [canvas.create_text(x, y, **kw)]

    # 仅取最近的 90 度倍数交给 Tk 原生 angle（精度最好）
    near = round(angle / 90.0) * 90.0
    if abs(angle - near) < 0.5:
        kw = {"text": text, "font": font, "fill": fill,
              "anchor": anchor, "angle": int(near) % 360}
        if tags:
            kw["tags"] = tags
        return [canvas.create_text(x, y, **kw)]

    # 逐字符旋转布局
    rad = math.radians(angle)
    ca, sa = math.cos(rad), math.sin(rad)
    widths = [text_size(ch, font)[0] for ch in text]
    total = sum(widths)
    if anchor == "center":
        cx = -total / 2.0
    elif anchor in ("w", "nw", "sw"):
        cx = 0.0
    elif anchor in ("e", "ne", "se"):
        cx = -total
    else:
        cx = -total / 2.0
    items = []
    for ch, w in zip(text, widths):
        px = cx + w / 2.0
        gx = x + px * ca
        gy = y + px * sa
        kw = {"text": ch, "font": font, "fill": fill, "anchor": "center",
              "angle": int(round(angle)) % 360}
        if tags:
            kw["tags"] = tags
        items.append(canvas.create_text(gx, gy, **kw))
        cx += w
    return items
