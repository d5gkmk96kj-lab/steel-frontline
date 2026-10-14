"""钢铁战线 Steel Frontline — Qt 主题层 (qtheme.py)
================================================================
对标 ui/theme.py 的军事调色板，但按 **Qt / QPainter / QSS** 的方式重写：

* 所有颜色以 ``QColor`` 导出（``Q_*`` 前缀），同时对 Tkinter 版风格的名字
  提供 ``str`` 常量别名，方便两个轨道互相对照。
* 提供 QSS 样式表生成器 :func:`stylesheet()`。
* 提供 QPainter 绘制工具：抗锯齿、圆角路径、线性/径向渐变、阴影、钢板纹理、
  做旧纸张、铆钉、磨损边、稀有度辉光。
* 术语一律使用附录 B：补给 / 掩体 / 牌库 / 移除区 / 勋章 / 战区推进图 /
  补给站 / 战地医院 / 精锐部队 / 战役难度 / 攻击·战术·指令 / 制式·常规·精锐·传奇。

坐标系：Qt 的 y 轴向下，与 Tk 一致；但所有控件都用 QLayout 布局，
不再手工算像素坐标。
================================================================
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QLinearGradient, QPainter,
    QPainterPath, QPen, QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget

# =====================================================================
# 0. 数值工具
# =====================================================================


def css(c) -> str:
    """把 ``QColor`` / ``"#RRGGBB"`` / ``None`` 统一成可嵌入 QSS 的 hex 字符串。

    任何 ``f"color:{x};"`` 形式的样式表插值都必须用它，否则插入 QColor
    对象会生成 Qt 无法解析的样式表（静默失败，只在 stderr 打警告）。
    """
    if c is None:
        return "transparent"
    if isinstance(c, str):
        return c
    try:
        return QColor(c).name()
    except Exception:
        return "transparent"


def _as_color(c) -> QColor:
    """容忍 ``QColor`` / ``"#RRGGBB"`` / ``None`` 三种输入，统一成 QColor。

    UI 层大量颜色来自常量表（str），而绘制函数内部按 QColor 使用。
    所有颜色入口都必须先过这里，否则会在运行时才炸 —— 这是本模块最易踩的坑。
    """
    if isinstance(c, QColor):
        return c
    if c is None:
        return QColor(Qt.GlobalColor.transparent)
    return qc(str(c))


def qc(hexstr: str, alpha: int = 255) -> QColor:
    """``"#RRGGBB"`` -> ``QColor``（可带 alpha 0..255）。非法输入回退为洋红以便定位。"""
    c = QColor(hexstr) if hexstr else QColor("#FF00FF")
    if not c.isValid():
        c = QColor("#FF00FF")
    if alpha != 255:
        c.setAlpha(max(0, min(255, int(alpha))))
    return c


def a(color: QColor, alpha: int) -> QColor:
    """返回带 alpha 的颜色副本（0..255）。"""
    c = QColor(_as_color(color))
    c.setAlpha(max(0, min(255, int(alpha))))
    return c


def f(color: QColor, factor: float) -> QColor:
    """亮度缩放：factor<1 变暗，>1 变亮（保留 alpha）。"""
    color = _as_color(color)
    h, s, v, al = color.getHsvF()
    if h < 0:
        h = 0.0
    v = max(0.0, min(1.0, v * factor))
    s = max(0.0, min(1.0, s * (1.0 if factor <= 1.0 else 0.92)))
    return QColor.fromHsvF(h, s, v, al)


def mix(c1: QColor, c2: QColor, t: float, alpha: int = 255) -> QColor:
    """线性插值两个颜色，t=0 -> c1。"""
    c1 = _as_color(c1); c2 = _as_color(c2)
    t = max(0.0, min(1.0, float(t)))
    r = int(c1.red() + (c2.red() - c1.red()) * t)
    g = int(c1.green() + (c2.green() - c1.green()) * t)
    b = int(c1.blue() + (c2.blue() - c1.blue()) * t)
    return QColor(r, g, b, alpha)


def lerp_hex(c1: str, c2: str, t: float) -> str:
    """hex -> hex 插值，返回 ``"#RRGGBB"``。"""
    m = mix(c1, c2, t)
    return m.name()


def ease_out(t: float) -> float:
    """三次缓出，用于动画曲线。"""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t * t * t


# =====================================================================
# 1. 调色板（附录 B.2）
# =====================================================================

Q_BG_DEEP = qc("#12100D")     # 硝烟黑褐：最底层
Q_BG = qc("#1A1712")          # 常规背景
Q_PANEL = qc("#24201A")       # 沙盘 / 钢板
Q_PANEL_HI = qc("#322C23")    # 面板高光 / 悬停
Q_PANEL_LO = qc("#141210")    # 凹陷 / 输入框
Q_BORDER = qc("#3E372C")
Q_BORDER_HI = qc("#5A5040")

Q_STEEL = qc("#5A6470")       # 钢灰：装甲、金属件
Q_SMOKE = qc("#3A3630")       # 硝烟灰
Q_RUST = qc("#8B5A2B")        # 锈迹

Q_GREEN = qc("#6B7F3A")       # 军绿强调（原 CYAN）
Q_GREEN_DIM = qc("#4E5D2A")
Q_GREEN_DARK = qc("#232B14")
Q_GOLD = qc("#C9A227")        # 弹壳金
Q_GOLD_DIM = qc("#8A6F1A")
Q_RED = qc("#A8322D")         # 战损红
Q_RED_DIM = qc("#6E211E")
Q_ORANGE = qc("#B5651D")      # 燃烧橙
Q_ORANGE_DIM = qc("#7A4413")

Q_TEXT = qc("#E8E2D4")        # 泛黄纸白
Q_TEXT_DIM = qc("#A89E8A")
Q_TEXT_FAINT = qc("#6E6656")
Q_WHITE = qc("#FFFFFF")
Q_BLACK = qc("#000000")

Q_BLOCK = qc("#7C8B99")       # 掩体：钢灰蓝
Q_BLOCK_DIM = qc("#4C5866")
Q_SUPPLY = qc("#D8C071")      # 补给
Q_HP = qc("#8E2B26")
Q_HP_GHOST = qc("#E8E2D4")

#: 焦土战场（战斗背景）三段渐变
Q_SKY_TOP = qc("#171410")
Q_SKY_MID = qc("#2A2118")
Q_SKY_LOW = qc("#3A2A1A")
Q_GROUND = qc("#241E17")
Q_GROUND_FAR = qc("#2E2619")

# ---------------------------------------------------------------------
# 字符串别名（与 ui/theme.py 同名，方便对照 / 混用）
# ---------------------------------------------------------------------
BG_DEEP, BG_DARK, BG = "#12100D", "#1A1712", "#1A1712"
PANEL, PANEL_LIGHT, PANEL_LO = "#24201A", "#322C23", "#141210"
BORDER, BORDER_HI = "#3E372C", "#5A5040"
TEXT, TEXT_DIM, TEXT_MUTED = "#E8E2D4", "#A89E8A", "#6E6656"
GOLD, CYAN, GREEN, RED, PURPLE, ORANGE = (
    "#C9A227", "#6B7F3A", "#6B7F3A", "#A8322D", "#B5651D", "#B5651D",
)
STEEL, SMOKE, RUST = "#5A6470", "#3A3630", "#8B5A2B"
BLOOD = "#A8322D"
GOLD_DIM = "#8A6F1A"
WHITE, BLACK = "#FFFFFF", "#000000"

COLORS: Dict[str, str] = {
    "bg_deep": BG_DEEP, "bg_dark": BG_DARK, "bg": BG,
    "panel": PANEL, "panel_light": PANEL_LIGHT, "panel_lo": PANEL_LO,
    "border": BORDER, "border_hi": BORDER_HI,
    "gold": GOLD, "cyan": CYAN, "green": GREEN, "red": RED,
    "purple": PURPLE, "orange": ORANGE,
    "steel": STEEL, "smoke": SMOKE, "rust": RUST, "text": TEXT,
}

# ---------------------------------------------------------------------
# 稀有度（制式 / 常规 / 精锐 / 传奇）— key 保持 core 的英文 id
# ---------------------------------------------------------------------
RARITY_COLORS: Dict[str, str] = {
    "basic": "#7A7A72",
    "common": "#A8B0A0",
    "uncommon": "#6B7F3A",
    "rare": "#C9A227",
    "special": "#B5651D",
    "starter": "#7A7A72",
    "boss": "#B5651D",
    "shop": "#6B7F3A",
}

RARITY_NAMES: Dict[str, str] = {
    "basic": "制式", "common": "常规", "uncommon": "精锐", "rare": "传奇",
    "special": "特殊", "starter": "制式", "boss": "王牌", "shop": "补给",
}

TYPE_COLORS: Dict[str, str] = {
    "attack": "#A8322D",   # 攻击
    "skill": "#6B7F3A",    # 战术
    "power": "#C9A227",    # 指令
    "status": "#7A7A72",   # 状态
    "curse": "#6E3B36",    # 诅咒
}

TYPE_NAMES: Dict[str, str] = {
    "attack": "攻击", "skill": "战术", "power": "指令",
    "status": "状态", "curse": "诅咒",
}

ARCH_COLORS: Dict[str, str] = {
    "attack": "#A8322D",   # 突击
    "block": "#7C8B99",    # 防御
    "poison": "#B5651D",   # 燃烧弹
    "energy": "#6B7F3A",   # 后勤
    "summon": "#8B5A2B",   # 支援
}

ARCH_NAMES: Dict[str, str] = {
    "attack": "突击", "block": "防御", "poison": "燃烧弹",
    "energy": "后勤", "summon": "支援",
}

# ---------------------------------------------------------------------------
# 名称表的 i18n 包装
# ---------------------------------------------------------------------------
# RARITY_NAMES / TYPE_NAMES / ARCH_NAMES 是「键 -> 中文显示名」的字典，
# 界面直接下标取值（T.RARITY_NAMES["common"]），因此不能在读的时候调 tr()。
# 用一个会在 __getitem__ 时翻译的 dict 子类包住，既有调用点无需改动。
class _TrDict(dict):
    def __getitem__(self, k):
        return _i18n.t(dict.__getitem__(self, k))

    def get(self, k, default=None):
        try:
            return _i18n.t(dict.__getitem__(self, k))
        except KeyError:
            return default


RARITY_NAMES = _TrDict(RARITY_NAMES)
TYPE_NAMES = _TrDict(TYPE_NAMES)
ARCH_NAMES = _TrDict(ARCH_NAMES)

INTENT_COLORS: Dict[str, str] = {
    "attack": "#A8322D",
    "attack_debuff": "#A8322D",
    "attack_defend": "#8B5A2B",
    "defend": "#7C8B99",
    "buff": "#C9A227",
    "debuff": "#B5651D",
    "sleep": "#7A7A72",
    "unknown": "#A89E8A",
}

INTENT_NAMES: Dict[str, str] = {
    "attack": "进攻", "attack_debuff": "进攻+压制", "attack_defend": "进攻+构筑",
    "defend": "构筑掩体", "buff": "强化", "debuff": "压制",
    "sleep": "待命", "unknown": "未知",
}

#: Buff 显示名。**单一事实来源是 core.engine.BUFF_NAMES**（附录 B.1 已在源头
#: 完成术语替换），这里只在 core 不可用时回退到内置副本，避免两份表漂移。
_FALLBACK_BUFF_NAMES: Dict[str, str] = {
    "strength": "火力", "strength_down": "弹药短缺", "dexterity": "机动",
    "vulnerable": "破甲", "weak": "压制",
    "frail": "混乱", "poison": "燃烧", "thorns": "铁丝网",
    "metallicize": "工事", "ritual": "增援", "artifact": "干扰弹",
    "plated_armor": "装甲板", "regenerate": "战地医疗", "intangible": "烟幕",
    "barrier": "坚守", "chain": "连射", "envenom": "燃烧弹", "accuracy": "瞄准",
}


def _load_buff_names() -> Dict[str, str]:
    try:
        from core import engine as _engine
        names = dict(getattr(_engine, "BUFF_NAMES", {}) or {})
        if names:
            return names
    except Exception:
        pass
    return dict(_FALLBACK_BUFF_NAMES)


def _load_buff_descs() -> Dict[str, str]:
    try:
        from core import engine as _engine
        return dict(getattr(_engine, "BUFF_DESCS", {}) or {})
    except Exception:
        return {}


#: 键名 -> 中文显示名（源自 core，附录 B.1 术语）
BUFF_NAMES: Dict[str, str] = _load_buff_names()
#: 键名 -> 说明文字（源自 core）
BUFF_DESCS: Dict[str, str] = _load_buff_descs()


def buff_name(key: str) -> str:
    """取 buff 显示名；未知键回退到键名本身，绝不抛异常。"""
    return BUFF_NAMES.get(key) or _FALLBACK_BUFF_NAMES.get(key) or str(key)

BUFF_COLORS: Dict[str, str] = {
    "strength": "#A8322D", "strength_down": "#6E211E", "dexterity": "#6B7F3A",
    "vulnerable": "#C9A227", "weak": "#8B5A2B", "frail": "#7A7A72",
    "poison": "#B5651D", "thorns": "#5A6470", "metallicize": "#7C8B99",
    "ritual": "#C9A227", "artifact": "#8FA05A", "plated_armor": "#8A94A0",
    "regenerate": "#5E8C4A", "intangible": "#B8B0A0", "barrier": "#5A7C99",
    "chain": "#C9A227", "envenom": "#B5651D", "accuracy": "#D8C071",
    # core 扩展 buff（键名保留 core 的 id，颜色按语义配军事色）
    "shellguard": "#8A94A0",      # 甲壳工事 -> 装甲板灰
    "tidepool": "#C9A227",        # 补给线 -> 弹壳金
    "deep_current": "#6B7F3A",    # 侦察网 -> 军绿
    "tidal_reserve": "#D8C071",   # 弹药储备 -> 补给黄
    "barnacle": "#B5651D",        # 纵火 -> 燃烧橙
    "venom_echo": "#C97A2B",      # 燃烧回响 -> 亮橙
    "deadwater": "#8B5A2B",       # 焦土 -> 锈褐
    "coral": "#7C8B99",           # 工事加固 -> 钢灰蓝
    "abyssal_gate": "#8E2B26",    # 总攻令 -> 战损红
    "whale_song": "#6B7F3A",      # 协同作战 -> 军绿
    "deep_echo": "#A8322D",       # 炮火覆盖 -> 战损红
    "ritual_chorus": "#C9A227",   # 增援梯队 -> 弹壳金
    "necrotide": "#7A4413",       # 焦土战术 -> 暗燃烧橙
}


def buff_color_for(key: str) -> QColor:
    """取 buff 颜色；未知键按 key 稳定分配一个军事色，避免出现异常色。"""
    c = BUFF_COLORS.get(key)
    if c:
        return qc(c)
    pool = ("#8FA05A", "#7C8B99", "#B5651D", "#C9A227", "#8B5A2B",
            "#6B7F3A", "#A8322D", "#D8C071")
    return qc(pool[sum(ord(ch) for ch in str(key)) % len(pool)])

NODE_COLORS: Dict[str, str] = {
    "battle": "#A8322D", "elite": "#8B5A2B", "event": "#B5651D",
    "shop": "#C9A227", "rest": "#6B7F3A", "treasure": "#C9A227",
    "boss": "#8E2B26",
}

NODE_NAMES: Dict[str, str] = {
    "battle": "遭遇战", "elite": "精锐部队", "event": "战场事件",
    "shop": "补给站", "rest": "战地医院", "treasure": "缴获物资",
    "boss": "要塞",
}

NODE_GLYPHS: Dict[str, str] = {
    "battle": "⚔", "elite": "☠", "event": "?", "shop": "⛭",
    "rest": "✚", "treasure": "★", "boss": "✠",
}


def rarity_color(r: str) -> QColor:
    return qc(RARITY_COLORS.get(r, "#A8B0A0"))


def type_color(t: str) -> QColor:
    return qc(TYPE_COLORS.get(t, "#A8B0A0"))


def arch_color(k: str) -> QColor:
    return qc(ARCH_COLORS.get(k, "#A8B0A0"))


def intent_color(i: str) -> QColor:
    return qc(INTENT_COLORS.get(i, "#A89E8A"))


def buff_color(k: str) -> QColor:
    return buff_color_for(k)


def node_color(k: str) -> QColor:
    return qc(NODE_COLORS.get(k, "#A89E8A"))


# =====================================================================
# 2. 字体 —— 优先 PingFang SC（macOS 实测 247 个字体族中可用）
# =====================================================================

_FONT_PREFS = [
    "PingFang SC", "PingFang HK", "Hiragino Sans GB", "Heiti SC",
    "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei",
    "WenQuanYi Micro Hei", "Arial Unicode MS", "Helvetica Neue", "Arial",
]
_MONO_PREFS = ["SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "Courier New"]

FONT_FAMILY: str = "Helvetica"      # 由 init_fonts() 覆盖
MONO_FAMILY: str = "Menlo"


def init_fonts() -> str:
    """探测可用字体族。必须在 QApplication 创建之后调用。"""
    global FONT_FAMILY, MONO_FAMILY
    try:
        fams = set(QFontDatabase.families())
    except Exception:
        fams = set()
    for name in _FONT_PREFS:
        if name in fams:
            FONT_FAMILY = name
            break
    for name in _MONO_PREFS:
        if name in fams:
            MONO_FAMILY = name
            break
    return FONT_FAMILY


def font(size: int = 14, bold: bool = False, family: Optional[str] = None,
         italic: bool = False) -> QFont:
    """构造 QFont。优先 :family:，否则用探测到的中文字体。"""
    fnt = QFont(family or FONT_FAMILY)
    fnt.setPixelSize(max(6, int(size)))
    fnt.setBold(bool(bold))
    fnt.setItalic(bool(italic))
    fnt.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return fnt


def mono(size: int = 12, bold: bool = False) -> QFont:
    return font(size, bold, family=MONO_FAMILY)


# 尺寸阶梯（px）
FONT_TITLE = 40
FONT_H1 = 26
FONT_H2 = 19
FONT_BODY = 15
FONT_SMALL = 13
FONT_TINY = 11
FONT_NUM = 16
FONT_NUM_BIG = 28

# =====================================================================
# 3. 尺寸常量
# =====================================================================

WIN_W, WIN_H = 1440, 900
MIN_WIN_W, MIN_WIN_H = 1280, 800

CARD_W, CARD_H, CARD_RADIUS = 168, 236, 12
CARD_GAP = 8
PAD, PAD_S, PAD_L = 12, 6, 24
RADIUS_S, RADIUS_M, RADIUS_L = 6, 10, 16
RELIC_SIZE = 44
BUFF_SIZE = 30
HPBAR_W, HPBAR_H = 260, 22


# =====================================================================
# 4. QSS 样式表
# =====================================================================


def stylesheet() -> str:
    """全局 QSS。所有面板/按钮/滚动条都走这里，不再手工画像素。"""
    return f"""
QWidget {{
    color: {TEXT};
    font-family: "{FONT_FAMILY}";
    font-size: {FONT_BODY}px;
}}
QMainWindow, QDialog {{ background: {BG_DEEP}; }}

/* ---------- 面板 ---------- */
QFrame#Panel, QWidget#Panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_M}px;
}}
QFrame#PanelLo {{
    background: {PANEL_LO};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_S}px;
}}
QLabel#Title    {{ font-size: {FONT_TITLE}px; font-weight: 700; color: {GOLD}; }}
QLabel#H1       {{ font-size: {FONT_H1}px;  font-weight: 700; color: {TEXT}; }}
QLabel#H2       {{ font-size: {FONT_H2}px;  font-weight: 700; color: {TEXT}; }}
QLabel#Dim      {{ color: {TEXT_DIM}; }}
QLabel#Faint    {{ color: {TEXT_MUTED}; font-size: {FONT_SMALL}px; }}
QLabel#Gold     {{ color: {GOLD}; font-weight: 700; }}
QLabel#Danger   {{ color: {RED}; font-weight: 700; }}
QLabel#Good     {{ color: {GREEN}; font-weight: 700; }}

/* ---------- 按钮 ---------- */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {PANEL_LIGHT}, stop:1 {PANEL});
    border: 1px solid {BORDER_HI};
    border-radius: {RADIUS_S}px;
    padding: 9px 20px;
    color: {TEXT};
    font-size: {FONT_BODY}px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4A4132, stop:1 {PANEL_LIGHT});
    border: 1px solid {GOLD};
    color: {WHITE};
}}
QPushButton:pressed {{ background: {PANEL_LO}; border: 1px solid {GOLD_DIM}; }}
QPushButton:disabled {{
    color: {TEXT_MUTED}; border: 1px solid {BORDER}; background: {PANEL_LO};
}}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #8A6F1A, stop:1 #6B5413);
    border: 1px solid {GOLD}; color: #FFF6DC; font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {GOLD}, stop:1 #8A6F1A);
}}
QPushButton#Primary:disabled {{
    background: {PANEL_LO}; color: {TEXT_MUTED}; border: 1px solid {BORDER};
}}
QPushButton#Danger {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #8E2B26, stop:1 #5E1C19);
    border: 1px solid {RED}; color: {TEXT};
}}
QPushButton#Danger:hover {{ background: {RED}; }}
QPushButton#Ghost {{
    background: transparent; border: 1px solid {BORDER};
    color: {TEXT_DIM}; font-weight: 500;
}}
QPushButton#Ghost:hover {{ border: 1px solid {GOLD}; color: {TEXT}; }}
QPushButton#Tab {{
    background: {PANEL_LO}; border: 1px solid {BORDER};
    border-radius: 0px; padding: 8px 16px; color: {TEXT_DIM};
}}
QPushButton#Tab:checked {{
    background: {PANEL_LIGHT}; border-bottom: 2px solid {GOLD}; color: {GOLD};
}}

/* ---------- 输入 ---------- */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {PANEL_LO}; border: 1px solid {BORDER};
    border-radius: {RADIUS_S}px; padding: 6px 10px; color: {TEXT};
    selection-background-color: {GOLD_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {GOLD}; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER_HI};
    selection-background-color: {GOLD_DIM}; color: {TEXT};
}}
QCheckBox {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1px solid {BORDER_HI};
    border-radius: 3px; background: {PANEL_LO};
}}
QCheckBox::indicator:checked {{ background: {GOLD}; border: 1px solid {GOLD}; }}

/* ---------- 列表 / 滚动区 ---------- */
QListWidget, QScrollArea, QTableWidget {{
    background: {PANEL_LO}; border: 1px solid {BORDER};
    border-radius: {RADIUS_S}px; color: {TEXT};
}}
QListWidget::item {{ padding: 7px 10px; border-bottom: 1px solid {BORDER}; }}
QListWidget::item:selected {{ background: {GOLD_DIM}; color: {WHITE}; }}
QListWidget::item:hover {{ background: {PANEL_LIGHT}; }}
QScrollBar:vertical {{
    background: {PANEL_LO}; width: 11px; margin: 0px; border: none;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_HI}; min-height: 28px; border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{ background: {GOLD_DIM}; }}
QScrollBar:horizontal {{ background: {PANEL_LO}; height: 11px; border: none; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_HI}; min-width: 28px; border-radius: 5px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; width: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- 进度条 ---------- */
QProgressBar {{
    background: {PANEL_LO}; border: 1px solid {BORDER};
    border-radius: {RADIUS_S}px; text-align: center; color: {TEXT};
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #8E2B26, stop:1 {RED});
    border-radius: 4px;
}}

/* ---------- 提示 ---------- */
QToolTip {{
    background: {PANEL}; color: {TEXT}; border: 1px solid {GOLD_DIM};
    padding: 6px 9px; border-radius: 4px;
}}
QSplitter::handle {{ background: {BORDER}; }}
QMenu {{
    background: {PANEL}; border: 1px solid {BORDER_HI}; padding: 4px;
}}
QMenu::item:selected {{ background: {GOLD_DIM}; }}
"""


# =====================================================================
# 5. QPainter 绘制工具
# =====================================================================


def aa(painter: QPainter) -> QPainter:
    """开启抗锯齿 + 平滑像素图变换（所有自绘控件的第一行）。"""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return painter


def no_pen(painter: QPainter) -> None:
    painter.setPen(Qt.PenStyle.NoPen)


def round_path(rect: QRectF, r: float) -> QPainterPath:
    """圆角矩形 QPainterPath（自动钳制半径）。"""
    r = max(0.0, min(float(r), min(rect.width(), rect.height()) / 2.0))
    p = QPainterPath()
    p.addRoundedRect(rect, r, r)
    return p


def fill_round(painter: QPainter, rect: QRectF, r: float, brush) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    if isinstance(brush, QBrush):
        painter.setBrush(brush)
    elif isinstance(brush, (QColor, str)):
        painter.setBrush(QBrush(_as_color(brush)))
    else:
        painter.setBrush(brush)
    painter.drawPath(round_path(rect, r))


def stroke_round(painter: QPainter, rect: QRectF, r: float, color: QColor,
                 width: float = 1.0) -> None:
    color = _as_color(color)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, width))
    painter.drawPath(round_path(rect, r))


def vgrad(rect: QRectF, top: QColor, bottom: QColor,
          stops: Optional[Sequence[Tuple[float, QColor]]] = None) -> QLinearGradient:
    """垂直线性渐变（y 轴向下：top -> bottom）。"""
    g = QLinearGradient(QPointF(rect.left(), rect.top()),
                        QPointF(rect.left(), rect.bottom()))
    if stops:
        for pos, col in stops:
            g.setColorAt(max(0.0, min(1.0, pos)), col)
    else:
        g.setColorAt(0.0, top)
        g.setColorAt(1.0, bottom)
    return g


def hgrad(rect: QRectF, left: QColor, right: QColor) -> QLinearGradient:
    g = QLinearGradient(QPointF(rect.left(), rect.top()),
                        QPointF(rect.right(), rect.top()))
    g.setColorAt(0.0, left)
    g.setColorAt(1.0, right)
    return g


def radial(center: QPointF, radius: float, inner: QColor, outer: QColor) -> QRadialGradient:
    g = QRadialGradient(center, max(0.1, radius))
    g.setColorAt(0.0, inner)
    g.setColorAt(1.0, outer)
    return g


def steel_plate(painter: QPainter, rect: QRectF, base: QColor,
                radius: float = RADIUS_M, rivets: bool = True,
                top_hl: float = 0.30) -> None:
    """铆接钢板质感：竖向渐变 + 顶部高光带 + 底部暗边 + 四角铆钉。"""
    base = _as_color(base)
    g = QLinearGradient(QPointF(rect.left(), rect.top()),
                        QPointF(rect.left(), rect.bottom()))
    g.setColorAt(0.0, f(base, 1.35))
    g.setColorAt(0.10, f(base, 1.14))
    g.setColorAt(0.55, base)
    g.setColorAt(1.0, f(base, 0.68))
    fill_round(painter, rect, radius, QBrush(g))

    # 顶部高光细线
    hl = QRectF(rect.left() + 2, rect.top() + 1.5, rect.width() - 4, max(1.0, rect.height() * 0.03))
    fill_round(painter, hl, hl.height() / 2, a(f(base, 1.9), int(90 * top_hl * 3.3)))

    # 底部内阴影（裁到圆角内，避免溢出）
    if rect.height() > 10:
        sh = QRectF(rect.left(), rect.bottom() - rect.height() * 0.28,
                    rect.width(), rect.height() * 0.28)
        gg = QLinearGradient(QPointF(sh.left(), sh.top()), QPointF(sh.left(), sh.bottom()))
        gg.setColorAt(0.0, a(Q_BLACK, 0))
        gg.setColorAt(1.0, a(Q_BLACK, 90))
        painter.save()
        painter.setClipPath(round_path(rect, radius))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gg))
        painter.drawRect(sh)
        painter.restore()

    if rivets:
        _rivets(painter, rect, radius)


def _rivets(painter: QPainter, rect: QRectF, radius: float,
            inset: float = 6.0, r: float = 2.1) -> None:
    """四角铆钉（带高光点）。"""
    pts = [
        QPointF(rect.left() + inset, rect.top() + inset),
        QPointF(rect.right() - inset, rect.top() + inset),
        QPointF(rect.left() + inset, rect.bottom() - inset),
        QPointF(rect.right() - inset, rect.bottom() - inset),
    ]
    for p in pts:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(a(Q_BLACK, 110)))
        painter.drawEllipse(p, r + 0.9, r + 0.9)
        painter.setBrush(QBrush(mix(Q_STEEL, Q_WHITE, 0.35)))
        painter.drawEllipse(p, r, r)
        painter.setBrush(QBrush(a(Q_WHITE, 120)))
        painter.drawEllipse(QPointF(p.x() - r * 0.3, p.y() - r * 0.35), r * 0.32, r * 0.32)


def aged_paper(painter: QPainter, rect: QRectF, base: QColor,
               radius: float = RADIUS_M, seed: int = 0) -> None:
    """做旧纸张：暖色渐变 + 边缘暗角 + 随机污渍 + 磨损边。"""
    base = _as_color(base)
    g = QLinearGradient(QPointF(rect.left(), rect.top()),
                        QPointF(rect.right(), rect.bottom()))
    g.setColorAt(0.0, f(base, 1.06))
    g.setColorAt(0.5, base)
    g.setColorAt(1.0, f(base, 0.86))
    fill_round(painter, rect, radius, QBrush(g))

    painter.save()
    painter.setClipPath(round_path(rect, radius))
    # 污渍（用确定性伪随机，避免每帧闪烁）
    st = (seed * 2654435761) & 0x7FFFFFFF
    for i in range(7):
        st = (st * 1103515245 + 12345) & 0x7FFFFFFF
        cx = rect.left() + (st % 10000) / 10000.0 * rect.width()
        st = (st * 1103515245 + 12345) & 0x7FFFFFFF
        cy = rect.top() + (st % 10000) / 10000.0 * rect.height()
        st = (st * 1103515245 + 12345) & 0x7FFFFFFF
        rr = rect.width() * (0.06 + (st % 1000) / 1000.0 * 0.16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(radial(QPointF(cx, cy), rr,
                                      a(f(base, 0.72), 46), a(base, 0))))
        painter.drawEllipse(QPointF(cx, cy), rr, rr * 0.75)
    # 暗角
    vg = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.72)
    vg.setColorAt(0.55, a(Q_BLACK, 0))
    vg.setColorAt(1.0, a(Q_BLACK, 96))
    painter.setBrush(QBrush(vg))
    painter.drawRect(rect)
    painter.restore()

    # 磨损边（不规则虚线描边）
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(a(f(base, 0.55), 200), 1.4))
    painter.drawPath(round_path(rect.adjusted(1, 1, -1, -1), radius))


def glow(painter: QPainter, rect: QRectF, color: QColor, radius: float = RADIUS_M,
         strength: int = 110, spread: float = 7.0, t: float = 1.0,
         pulse: bool = False) -> None:
    """稀有度发光描边：多层外扩半透明圆角描边（模拟辉光）。"""
    color = _as_color(color)
    layers = 5
    for i in range(layers, 0, -1):
        k = i / layers
        alpha = int(strength * (1.0 - k) * (0.85 + 0.3 * t))
        if pulse:
            alpha = int(alpha * (0.72 + 0.28 * math.sin(t * math.pi * 2)))
        if alpha <= 2:
            continue
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(a(color, alpha), 1.6))
        painter.drawPath(round_path(
            rect.adjusted(-k * spread, -k * spread, k * spread, k * spread), radius + k * spread))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(a(color, min(255, int(200 * (0.6 + 0.4 * t)))), 1.8))
    painter.drawPath(round_path(rect, radius))


def shadow_effect(widget: QWidget, blur: int = 22, dy: int = 6,
                  color: QColor = QColor(0, 0, 0, 190)) -> QGraphicsDropShadowEffect:
    """给任意 QWidget 加投影（Qt 的 QGraphicsDropShadowEffect）。"""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(color)
    widget.setGraphicsEffect(eff)
    return eff


def text(painter: QPainter, rect: QRectF, s: str, fnt: QFont, color: QColor,
         align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
         wrap: bool = False) -> QRectF:
    """在矩形内绘制文字，返回实际绘制区域。

    这里是 QPainter 绘字的统一入口，i18n 在这一层翻译即可覆盖
    所有自绘界面文字（菜单按钮、标题、卡面……）。
    """
    s = tr(s)
    painter.setFont(fnt)
    painter.setPen(QPen(_as_color(color)))
    flags = int(align)
    if wrap:
        flags |= int(Qt.TextFlag.TextWordWrap)
    painter.drawText(rect, flags, s)
    return rect


def text_c(painter: QPainter, cx: float, cy: float, s: str, fnt: QFont,
           color: QColor, shadow: bool = False) -> None:
    """以 (cx,cy) 为中心绘制单行文字（可选投影）。"""
    s = tr(s)
    color = _as_color(color)
    painter.setFont(fnt)
    fm = QFontMetricsF(fnt)
    w = fm.horizontalAdvance(s)
    h = fm.height()
    r = QRectF(cx - w / 2, cy - h / 2, w, h)
    if shadow:
        painter.setPen(QPen(a(Q_BLACK, 170)))
        painter.drawText(r.translated(1.4, 1.4),
                         int(Qt.AlignmentFlag.AlignCenter), s)
    painter.setPen(QPen(color))
    painter.drawText(r, int(Qt.AlignmentFlag.AlignCenter), s)


def outline_text(painter: QPainter, rect: QRectF, s: str, fnt: QFont,
                 color: QColor, outline: QColor, width: float = 2.4,
                 align=Qt.AlignmentFlag.AlignCenter) -> None:
    """描边文字（伤害飘字用，保证在任何背景上都清晰）。"""
    color = _as_color(color)
    outline = _as_color(outline)
    painter.setFont(fnt)
    path = QPainterPath()
    fm = QFontMetricsF(fnt)
    tw = fm.horizontalAdvance(s)
    th = fm.ascent()
    x = rect.left() + (rect.width() - tw) / 2
    y = rect.top() + (rect.height() - fm.height()) / 2 + th
    path.addText(QPointF(x, y), fnt, s)
    painter.setPen(QPen(outline, width, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPath(path)


def chevron(painter: QPainter, cx: float, cy: float, size: float,
            color: QColor, up: bool = True, width: float = 2.2) -> None:
    """军衔人字纹（地图/结算装饰）。"""
    color = _as_color(color)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    d = -1 if up else 1
    for i in range(2):
        y = cy + d * (i * size * 0.5)
        p = QPainterPath()
        p.moveTo(cx - size, y)
        p.lineTo(cx, y + d * size * 0.42)
        p.lineTo(cx + size, y)
        painter.drawPath(p)


def star(painter: QPainter, cx: float, cy: float, r: float, color: QColor,
         points: int = 5, inner: float = 0.42, rotation: float = -math.pi / 2) -> None:
    """星形（军功章 / 稀有度标记）。"""
    color = _as_color(color)
    path = QPainterPath()
    for i in range(points * 2):
        rad = r if i % 2 == 0 else r * inner
        ang = rotation + i * math.pi / points
        pt = QPointF(cx + math.cos(ang) * rad, cy + math.sin(ang) * rad)
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPath(path)


def wedge(painter: QPainter, cx: float, cy: float, r: float, ratio: float,
          start_deg: float = 90.0, bg: QColor = QColor(0, 0, 0, 150),
          fill: QColor = QColor("#6B7F3A"), thickness: float = 4.0,
          rounded: bool = True) -> None:
    """环形进度（能量球 / 血条 / 冷却）。ratio 0..1。"""
    bg = _as_color(bg); fill = _as_color(fill)
    rect = QRectF(cx - r, cy - r, r * 2, r * 2)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(bg, thickness, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap if rounded else Qt.PenCapStyle.FlatCap))
    painter.drawArc(rect, int(start_deg * 16), int(-360 * 16))
    if ratio > 0.001:
        painter.setPen(QPen(fill, thickness, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap if rounded else Qt.PenCapStyle.FlatCap))
        painter.drawArc(rect, int(start_deg * 16), int(-360 * 16 * max(0.0, min(1.0, ratio))))


def polygon(points: Sequence[Tuple[float, float]]) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def scratch_marks(painter: QPainter, rect: QRectF, color: QColor,
                  n: int = 4, seed: int = 7) -> None:
    """战损刮痕（钢板卡面的磨损细节）。"""
    color = _as_color(color)
    st = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    painter.setPen(QPen(a(color, 70), 1.0, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap))
    for _ in range(n):
        st = (st * 1103515245 + 12345) & 0x7FFFFFFF
        x1 = rect.left() + (st % 1000) / 1000.0 * rect.width()
        st = (st * 1103515245 + 12345) & 0x7FFFFFFF
        y1 = rect.top() + (st % 1000) / 1000.0 * rect.height()
        st = (st * 1103515245 + 12345) & 0x7FFFFFFF
        ln = 8 + (st % 1000) / 1000.0 * 26
        ang = ((st >> 3) % 1000) / 1000.0 * math.pi
        painter.drawLine(QPointF(x1, y1),
                         QPointF(x1 + math.cos(ang) * ln, y1 + math.sin(ang) * ln))


def icon_glyph(kind: str) -> str:
    """军事符号语汇的图标字形（备用；主图标一律用 QPainterPath 绘制）。"""
    return {
        "cover": "▣", "attack": "✸", "supply": "◆", "order": "⚙",
        "tactic": "▲", "hp": "✚", "gold": "◉", "skull": "☠",
        "star": "★", "sword": "⚔", "flag": "⚑", "gear": "⛭",
    }.get(kind, "◆")


__all__ = [
    # 颜色对象
    "Q_BG_DEEP", "Q_BG", "Q_PANEL", "Q_PANEL_HI", "Q_PANEL_LO", "Q_BORDER",
    "Q_BORDER_HI", "Q_STEEL", "Q_SMOKE", "Q_RUST", "Q_GREEN", "Q_GREEN_DIM",
    "Q_GREEN_DARK", "Q_GOLD", "Q_GOLD_DIM", "Q_RED", "Q_RED_DIM", "Q_ORANGE",
    "Q_ORANGE_DIM", "Q_TEXT", "Q_TEXT_DIM", "Q_TEXT_FAINT", "Q_WHITE", "Q_BLACK",
    "Q_BLOCK", "Q_BLOCK_DIM", "Q_SUPPLY", "Q_HP", "Q_HP_GHOST",
    "Q_SKY_TOP", "Q_SKY_MID", "Q_SKY_LOW", "Q_GROUND", "Q_GROUND_FAR",
    # 字符串别名 + 表
    "BG_DEEP", "BG_DARK", "BG", "PANEL", "PANEL_LIGHT", "PANEL_LO", "BORDER",
    "BORDER_HI", "TEXT", "TEXT_DIM", "TEXT_MUTED", "GOLD", "CYAN", "GREEN",
    "RED", "PURPLE", "ORANGE", "STEEL", "SMOKE", "RUST", "BLOOD", "COLORS",
    "RARITY_COLORS", "RARITY_NAMES", "TYPE_COLORS", "TYPE_NAMES", "ARCH_COLORS",
    "ARCH_NAMES", "INTENT_COLORS", "INTENT_NAMES", "BUFF_NAMES", "BUFF_DESCS", "buff_name", "BUFF_COLORS",
    "NODE_COLORS", "NODE_NAMES", "NODE_GLYPHS",
    # 取色函数
    "qc", "a", "f", "mix", "lerp_hex", "ease_out", "ease_in_out",
    "rarity_color", "type_color", "arch_color", "intent_color", "buff_color",
    "buff_color_for",
    "node_color",
    # 字体
    "FONT_FAMILY", "MONO_FAMILY", "init_fonts", "font", "mono",
    "FONT_TITLE", "FONT_H1", "FONT_H2", "FONT_BODY", "FONT_SMALL", "FONT_TINY",
    "FONT_NUM", "FONT_NUM_BIG",
    # 尺寸
    "WIN_W", "WIN_H", "MIN_WIN_W", "MIN_WIN_H", "CARD_W", "CARD_H",
    "CARD_RADIUS", "CARD_GAP", "PAD", "PAD_S", "PAD_L", "RADIUS_S",
    "RADIUS_M", "RADIUS_L", "RELIC_SIZE", "BUFF_SIZE", "HPBAR_W", "HPBAR_H",
    # QSS
    "stylesheet",
    # 绘制工具
    "aa", "no_pen", "round_path", "fill_round", "stroke_round", "vgrad", "hgrad",
    "_as_color", "css",
    "radial", "steel_plate", "aged_paper", "glow", "shadow_effect", "text",
    "text_c", "outline_text", "chevron", "star", "wedge", "polygon",
    "scratch_marks", "icon_glyph",
]


# ---------------------------------------------------------------------------
# i18n：PyQt6 侧的统一文本处理
# ---------------------------------------------------------------------------
# Qt 没有像 Tk 那样的单一绘制入口（190+ 处 setText/QLabel），所以在
# qapp 启动时给 QLabel.setTitle/setText 打一个**一次性补丁**，
# 让所有既有调用点自动走翻译，无需改动任何一个界面文件。
try:  # pragma: no cover
    from core import i18n as _i18n
except Exception:  # pragma: no cover
    class _Ident:
        @staticmethod
        def t(x):
            return x
    _i18n = _Ident()  # type: ignore


def tr(s):
    """翻译（供界面代码显式调用；绝大多数情况用不到，补丁已自动处理）。"""
    return _i18n.t(s)


_I18N_PATCHED = False


def install_i18n_patch() -> None:
    """给 QLabel/QPushButton/QGroupBox 等的 setText 打翻译补丁（幂等）。"""
    global _I18N_PATCHED
    if _I18N_PATCHED:
        return
    # 注意：PyQt6 里 QAction 在 QtGui，不在 QtWidgets（写错会静默失败）。
    try:
        from PyQt6.QtWidgets import (QLabel, QPushButton, QCheckBox,
                                     QRadioButton, QGroupBox)
    except Exception:
        return
    try:
        from PyQt6.QtGui import QAction
    except Exception:
        QAction = None

    def _wrap_ctor(cls):
        """包装 __init__，把第一个字符串参数翻掉（构造传参路径）。"""
        orig_init = getattr(cls, "__init__", None)
        if orig_init is None or getattr(orig_init, "_i18n_ctor", False):
            return
        def patched_init(self, *args, **kw):
            try:
                if args and isinstance(args[0], str):
                    args = (_i18n.t(args[0]),) + tuple(args[1:])
                if isinstance(kw.get("text"), str):
                    kw = dict(kw)
                    kw["text"] = _i18n.t(kw["text"])
            except Exception:
                pass
            return orig_init(self, *args, **kw)
        patched_init._i18n_ctor = True
        try:
            cls.__init__ = patched_init
        except Exception:
            pass

    def _wrap(cls, name):
        orig = getattr(cls, name, None)
        if orig is None or getattr(orig, "_i18n_wrapped", False):
            return
        def patched(self, text, *a, **kw):
            try:
                text = _i18n.t(text)
            except Exception:
                pass
            return orig(self, text, *a, **kw)
        patched._i18n_wrapped = True
        try:
            setattr(cls, name, patched)
        except Exception:
            pass

    # QTabWidget.addTab / insertTab 的标题也是玩家可见文案，一并翻译。
    try:
        from PyQt6.QtWidgets import QTabWidget

        def _wrap_tab(name):
            orig = getattr(QTabWidget, name, None)
            if orig is None or getattr(orig, "_i18n_wrapped", False):
                return
            def patched(self, *a, **kw):
                try:
                    a = list(a)
                    if len(a) >= 2 and isinstance(a[1], str):
                        a[1] = _i18n.t(a[1])
                    elif isinstance(kw.get("label"), str):
                        kw = dict(kw)
                        kw["label"] = _i18n.t(kw["label"])
                except Exception:
                    pass
                return orig(self, *a, **kw)
            patched._i18n_wrapped = True
            try:
                setattr(QTabWidget, name, patched)
            except Exception:
                pass

        _wrap_tab("addTab")
        _wrap_tab("insertTab")
    except Exception:
        pass

    # QComboBox 的下拉项也是玩家可见文案，一并翻译。
    try:
        from PyQt6.QtWidgets import QComboBox

        def _wrap_combo(name):
            orig = getattr(QComboBox, name, None)
            if orig is None or getattr(orig, "_i18n_wrapped", False):
                return

            def patched(self, *a, **kw):
                try:
                    if name == "addItems" and a and isinstance(a[0], (list, tuple)):
                        a = ([_i18n.t(x) for x in a[0]],) + tuple(a[1:])
                    elif name in ("addItem", "setItemText") and len(a) >= 1:
                        idx = 0 if name == "addItem" else 1
                        if len(a) > idx and isinstance(a[idx], str):
                            a = list(a)
                            a[idx] = _i18n.t(a[idx])
                            a = tuple(a)
                except Exception:
                    pass
                return orig(self, *a, **kw)

            patched._i18n_wrapped = True
            try:
                setattr(QComboBox, name, patched)
            except Exception:
                pass

        for _n in ("addItem", "addItems", "setItemText"):
            _wrap_combo(_n)
    except Exception:
        pass

    classes = [QLabel, QPushButton, QCheckBox, QRadioButton, QGroupBox]
    if QAction is not None:
        classes.append(QAction)
    for cls in classes:
        _wrap(cls, "setText")
        _wrap(cls, "setTitle")
        _wrap(cls, "setToolTip")
        _wrap(cls, "setWindowTitle")
        _wrap(cls, "setPlaceholderText")
        # 关键：`QPushButton("中文")` 这种**构造传参**不会走 Python 层的
        # setText（Qt 在 C++ 里直接设置），所以必须同时包 __init__。
        _wrap_ctor(cls)
    _I18N_PATCHED = True
    try:
        import os as _os
        if _os.environ.get("SF_I18N_DEBUG"):
            print("[i18n] patch installed")
    except Exception:
        pass
