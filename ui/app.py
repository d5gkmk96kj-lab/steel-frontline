"""钢铁战线 —— App 主循环、界面路由、动画调度、core 适配层。

设计要点
--------
1. ``App(tk.Tk)`` 只有一个真正的 Canvas 子控件（``self.canvas``）。所有界面都在它上面
   重绘，切换界面 = 换 ``self._screen`` 渲染器 + 重绘。
2. **全部动画走 ``self.after()``**；本文件（以及整个 ui/）不含任何 ``time.sleep``。
3. 界面切换带 200ms 淡入（``FADE_MS``）。
4. 对 ``core`` 的依赖全部收敛在 ``_Core`` 适配器与各渲染器的 ``safe(fn, *a, default=)``
   调用里：core 尚未就绪、方法缺失、抛异常，都只会退化为"空数据界面"，绝不崩。
5. 渲染数据一律来自 ``battle.snapshot()`` / run 的公开属性，不触碰 core 私有字段。
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

import tkinter as tk
from tkinter import font as tkfont

# 允许 `python3 ui/app.py` 直接运行。
if __package__ in (None, ""):  # pragma: no cover - 直接运行脚本时
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --------------------------------------------------------------------------- #
# 主题（容错导入：ui/theme.py 由队友 ui-theme 提供；缺失时用内置回退表）
# --------------------------------------------------------------------------- #
try:  # pragma: no cover
    from . import theme as _theme_mod
except Exception:  # pragma: no cover
    try:
        import theme as _theme_mod  # type: ignore
    except Exception:
        _theme_mod = None

# --------------------------------------------------------------------------- #
# 轻量偏好存储：只存极少数全局设置（目前是语言）。
# 放 data/ 下，与存档分开，损坏也不影响玩游戏。
# --------------------------------------------------------------------------- #
def _prefs_path() -> str:
    try:
        from core import run as _run
        d = getattr(_run, "DATA_DIR", None)
        if d:
            return os.path.join(d, "prefs.json")
    except Exception:
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "prefs.json")


def _load_pref(key: str, default=None):
    try:
        with open(_prefs_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and key in d:
            return d[key]
    except Exception:
        pass
    return default


def _save_pref(key: str, value) -> None:
    p = _prefs_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        d = {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                cur = json.load(f)
            if isinstance(cur, dict):
                d = cur
        except Exception:
            pass
        d[key] = value
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# i18n（中英切换）。容错导入：拿不到就退化成恒等函数。
try:  # pragma: no cover
    from core import i18n as _i18n
except Exception:  # pragma: no cover
    class _Ident:
        @staticmethod
        def t(x):
            return x
    _i18n = _Ident()  # type: ignore

# 全局控制台（F1 呼出）
try:  # pragma: no cover
    from .console import Console as _Console
except Exception:  # pragma: no cover
    try:
        from console import Console as _Console  # type: ignore
    except Exception:
        _Console = None


# 战场配色（硝烟褐 / 军绿 / 钢灰 / 弹壳金）：所有渲染器的最后一道回退。
FALLBACK_COLORS: Dict[str, str] = {
    "bg_deep": "#12100D",
    "bg_abyss": "#0B0906",
    "bg_mid": "#2A2418",
    "ground_top": "#3B3226",
    "ground_bottom": "#12100D",
    "panel": "#24201A",
    "panel_light": "#322C24",
    "panel_dark": "#181510",
    "border": "#3A3428",
    "border_light": "#5A5140",
    "gold": "#C9A227",
    "gold_dark": "#8A6E1A",
    "text": "#E8E2D4",
    "text_dim": "#9C9280",
    "text_mute": "#6B6355",
    "hp_red": "#A8322D",
    "hp_dark": "#5a1714",
    "block_blue": "#7FB4E8",
    "energy": "#D8B23A",
    "energy_dark": "#b07d12",
    "poison": "#7ed957",
    "buff": "#ffd45e",
    "debuff": "#c86bff",
    "danger": "#ff5f56",
    "good": "#5fd68a",
    "common": "#c9d4dd",
    "uncommon": "#5fc4e8",
    "rare": "#f2c14e",
    "basic": "#9aa7b2",
    "curse": "#8b4a9c",
    "status": "#6f7f8c",
    "attack": "#A8322D",
    "skill": "#6B7F3A",
    "power": "#C9A227",
    "glow": "#C9A227",
    "black": "#000000",
    "white": "#ffffff",
}

FONT_STACK = ("PingFang SC", "Hiragino Sans GB", "Heiti SC", "Microsoft YaHei",
              "Noto Sans CJK SC", "Arial Unicode MS", "Helvetica")

FADE_MS = 200
FRAME_MS = 33           # 背景粒子 ~30fps
TOOLTIP_DELAY_MS = 250  # 悬浮 250ms 显示提示


def _fgfont(size: int = 14, bold: bool = False) -> tuple:
    return (FONT_STACK[0], size, "bold") if bold else (FONT_STACK[0], size)


def _safe_font(root: tk.Misc, size: int, bold: bool = False) -> tuple:
    """选一个系统里真实存在的字体，避免中文变方块。"""
    try:
        available = set(tkfont.families(root))
    except Exception:
        available = set()
    for fam in FONT_STACK:
        if fam in available:
            return (fam, size, "bold") if bold else (fam, size)
    return _fgfont(size, bold)


def _hex_to_rgb(c: str):
    c = (c or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except Exception:
        return 0, 0, 0


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#%02x%02x%02x" % (max(0, min(255, int(r))),
                              max(0, min(255, int(g))),
                              max(0, min(255, int(b))))


def mix(c1: str, c2: str, t: float) -> str:
    """两色线性插值；t=0 取 c1，t=1 取 c2。"""
    t = max(0.0, min(1.0, float(t)))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)


def lighten(c: str, t: float = 0.3) -> str:
    return mix(c, "#ffffff", t)


def darken(c: str, t: float = 0.3) -> str:
    return mix(c, "#000000", t)


def with_alpha(c: str, bg: str, alpha: float) -> str:
    """Tkinter Canvas 不支持 alpha，用与背景混色模拟半透明。"""
    return mix(bg, c, alpha)


# --------------------------------------------------------------------------- #
# core 适配层
# --------------------------------------------------------------------------- #
MISSING = object()
_UNSET = object()


class _Core:
    """对 ``core`` 包的**唯一**访问点。

    所有属性都可能在 core 尚未完成时为 None，所有调用都带异常隔离。
    """

    _SUB = ("cards", "relics", "enemies", "events", "engine", "run")

    def __init__(self) -> None:
        self.error: Optional[str] = None
        self.cards = self.relics = self.enemies = self.events = None
        self.engine = self.run = None
        self._load()
        if any(m is None for m in (self.cards, self.relics, self.enemies,
                                   self.events, self.engine, self.run)):
            retry = _Core._load_now()
            for name in self._SUB:
                if getattr(self, name) is None:
                    setattr(self, name, getattr(retry, name, None))

    @staticmethod
    def _load_now() -> "_Core":
        obj = _Core.__new__(_Core)
        obj.error = None
        for name in _Core._SUB:
            setattr(obj, name, None)
        for name in _Core._SUB:
            try:
                mod = __import__("core." + name, fromlist=[name])
                setattr(obj, name, mod)
            except Exception:
                pass
        return obj

    def _load(self) -> None:
        for name in self._SUB:
            try:
                setattr(self, name, __import__("core." + name, fromlist=[name]))
            except Exception:
                pass

    # -- 便捷取值 ---------------------------------------------------------- #
    def attr(self, module: str, name: str, default=None):
        """取 core 子模块上的常量/数据库，缺失或异常时返回 default。"""
        mod = getattr(self, module, None)
        if mod is None:
            return default
        return getattr(mod, name, default)

    def missing(self) -> List[str]:
        return [n for n in self._SUB if getattr(self, n, None) is None]


def _call(obj: Any, *names: str) -> Optional[Callable]:
    """返回 obj 上第一个可调用的候选方法。"""
    for n in names:
        fn = getattr(obj, n, None)
        if callable(fn):
            return fn
    return None


def _try(fn: Optional[Callable], *args, default=MISSING, **kwargs):
    if fn is None:
        return None if default is MISSING else default
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None if default is MISSING else default


def _attr(obj: Any, *names: str, default=None):
    for n in names:
        if obj is None:
            return default
        try:
            v = getattr(obj, n)
        except Exception:
            continue
        if v is not None:
            return v
    return default


def _num(v, default=0):
    try:
        if isinstance(v, bool):
            return int(v)
        return float(v)
    except Exception:
        return default


# --------------------------------------------------------------------------- #
# 屏幕定义
# --------------------------------------------------------------------------- #
SCREENS = ("menu", "map", "battle", "reward", "shop", "rest", "event",
           "treasure", "deck", "gameover", "codex", "stats", "settings",
           "achievements")

_VIEW_CACHE: Dict[str, Callable] = {}


def _make_view(name: str):
    """惰性构造各界面渲染器。

    降级策略是**有噪音的**：任何 import/取属性的失败都会打印完整堆栈到
    stderr（BUG #4：静默 except 会让界面空白却查不到原因），然后才回退到
    占位界面。占位界面自身若也不可用，则返回一个最小可用的兜底工厂。
    """
    if name in _VIEW_CACHE:
        return _VIEW_CACHE[name]
    factory: Optional[Callable] = None
    load_error: Optional[str] = None
    try:
        if name == "battle":
            from . import battle_view as m
            factory = getattr(m, "BattleView")
        elif name == "map":
            from . import map_view as m
            factory = getattr(m, "MapView")
        else:
            from . import screens as m
            factory = getattr(m, "SCREEN_CLASSES", {}).get(name)
            if factory is None:
                ph = getattr(m, "placeholder_view", None)
                if ph is not None:
                    factory = (lambda n, _ph=ph: (lambda app: _ph(app, n)))(name)
                else:
                    load_error = ("screens.SCREEN_CLASSES 缺少 %r，"
                                  "且没有 placeholder_view" % name)
    except Exception:
        # 绝不静默：把真实原因暴露到 stderr，便于定位"界面空白"类问题。
        traceback.print_exc()
        print("[ui.app] 加载界面 %r 的渲染器失败，将回退到占位界面。"
              % name, file=sys.stderr, flush=True)
        load_error = "import/属性访问异常（详见上方堆栈）"
        factory = None
    if factory is None:
        if load_error:
            print("[ui.app] 界面 %r 降级原因：%s" % (name, load_error),
                  file=sys.stderr, flush=True)

        def factory(app, _n=name):  # type: ignore
            try:
                from . import screens as m
                return m.placeholder_view(app, _n)
            except Exception:
                traceback.print_exc()
                print("[ui.app] 连占位界面都不可用，使用内置兜底界面 %r"
                      % _n, file=sys.stderr, flush=True)
                return _FallbackView(app, _n)
    _VIEW_CACHE[name] = factory
    return factory



class _FallbackView:
    """终极兜底界面：不依赖 ui.screens，只在画布上写一段提示。"""

    wants_bg = False

    def __init__(self, app, name: str) -> None:
        self.app = app
        self.name = name
        self.kwargs: Dict[str, Any] = {}

    def build(self, kwargs: Dict[str, Any]) -> None:
        self.kwargs = dict(kwargs or {})

    def draw(self) -> None:
        app = self.app
        app.canvas.delete("all")
        w, h = app.W, app.H
        app.canvas.create_rectangle(0, 0, w, h, fill="#12100D", outline="")
        app.text_shadow(w / 2, h / 2 - 20,
                        "界面 %r 无法渲染" % self.name, font=app.font_h1,
                        fill="#A8322D")
        app.text_shadow(w / 2, h / 2 + 30,
                        "请查看终端 stderr 中的堆栈信息（按 Esc 返回）",
                        font=app.font_body, fill="#9C9280")

    def on_resize(self, w: int, h: int) -> None:
        pass



# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    """游戏主窗口。"""

    WIDTH, HEIGHT = 1440, 900
    MIN_W, MIN_H = 1280, 800

    def __init__(self) -> None:
        super().__init__()
        self.core = _Core()

        try:
            from core import version as _V
            self.title(_V.title())
        except Exception:
            self.title("钢铁战线 · Steel Frontline")
        self.geometry("%dx%d" % (self.WIDTH, self.HEIGHT))
        self.minsize(self.MIN_W, self.MIN_H)

        # 字体解析：必须在 root 建好之后调用一次（theme.py 自己绝不建 Tk，
        # 否则 macOS + Tk8.5 下会在 mainloop 里 SIGSEGV）。
        init_fonts = getattr(_theme_mod, "init_fonts", None) if _theme_mod else None
        if callable(init_fonts):
            try:
                init_fonts(self)
            except Exception:
                traceback.print_exc()
                print("[ui.app] theme.init_fonts() 失败，使用回退字体。",
                      file=sys.stderr, flush=True)
        # theme 的字体常量在 init_fonts 之后才精确；重新读取一遍。
        self._refresh_theme_fonts()
        self.configure(bg=self.color("bg_deep"))

        # 字体
        self.font_title = _safe_font(self, 46, True)
        self.font_h1 = _safe_font(self, 28, True)
        self.font_h2 = _safe_font(self, 20, True)
        self.font_body = _safe_font(self, 15)
        self.font_small = _safe_font(self, 13)
        self.font_tiny = _safe_font(self, 11)
        self.font_num = _safe_font(self, 18, True)

        # 唯一画布
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=self.color("bg_deep"))
        self.canvas.pack(fill="both", expand=True)

        # 运行时状态
        self.run = None
        self.battle = None
        self.meta = None
        self.screen_name = "menu"
        self.view = None

        # 动画/调度
        self._jobs: Dict[str, str] = {}
        self._tick = 0
        self._fade_job: Optional[str] = None
        self._fade_done: Optional[Callable] = None
        self._shake: List[float] = [0.0, 0.0, 0.0]   # [剩余, 幅度, 相位]
        self._overlay_flash: List[Any] = [None, 0.0]
        self._damage_numbers: List[dict] = []
        self._dn_cls = _UNSET
        self._last_wh: tuple = (self.WIDTH, self.HEIGHT)
        self._bg_sprites: List[dict] = []
        self._init_bg_sprites()

        # 设置（由设置界面读写）
        self.settings: Dict[str, Any] = {
            "volume": 70,
            "anim_speed": 1.0,
            "show_difficulty": True,
            "fullscreen": False,
            "damage_numbers": True,
        }

        # 语言偏好：从磁盘恢复（上次选过英文就还用英文）
        try:
            _i18n.set_lang(_load_pref("lang", _i18n.lang()))
        except Exception:
            pass

        self._install_cheat_hook()
        self.canvas.bind("<Configure>", self._on_configure)
        self.bind("<Escape>", self._on_escape)
        # 全局控制台（F1 呼出）
        if _Console is not None:
            self.console = _Console(self)
            try:
                self.bind("<F1>", self._on_f1)
            except Exception:
                pass
        # 通用键盘转发：交给控制台 / 当前 view
        self.bind("<Key>", self._on_key)

        # 全局帧循环：背景粒子 + 伤害飘字 + 震屏
        self._frame_job: Optional[str] = None
        self._schedule_frame()

        self._show_direct("menu")


    def _refresh_theme_fonts(self) -> None:
        """把 theme.init_fonts() 解析后的字体对象取回本模块（若提供）。"""
        for name, attr in (("FONT_TITLE", "font_title"), ("FONT_H1", "font_h1"),
                           ("FONT_H2", "font_h2"), ("FONT_BODY", "font_body"),
                           ("FONT_SMALL", "font_small"), ("FONT_TINY", "font_tiny"),
                           ("FONT_NUM", "font_num")):
            v = getattr(_theme_mod, name, None) if _theme_mod else None
            if isinstance(v, tuple) and len(v) >= 2:
                setattr(self, attr, v)

    # ---------------------------------------------------------------- 工具 -- #
    # theme.py 常量名 → 本项目内部的语义色名
    _THEME_ALIASES: Dict[str, tuple] = {
        "bg_deep": ("BG_DEEP", "BG", "PANEL_LO"),
        "bg_abyss": ("PANEL_LO", "BG_DEEP"),
        "bg_mid": ("PANEL", "BG"),
        "ground_top": ("BORDER_HI", "CYAN_DARK"),
        "ground_bottom": ("BG_DEEP", "BG"),
        "panel": ("PANEL", "PANEL_HI"),
        "panel_light": ("PANEL_HI", "PANEL"),
        "panel_dark": ("PANEL_LO", "BG_DEEP"),
        "border": ("BORDER", "BORDER_HI"),
        "border_light": ("BORDER_HI", "CYAN"),
        "gold": ("GOLD", "GOLD_DIM"),
        "gold_dark": ("GOLD_DIM", "GOLD"),
        "text": ("TEXT", "WHITE"),
        "text_dim": ("TEXT_DIM", "TEXT"),
        "text_mute": ("TEXT_FAINT", "TEXT_DIM"),
        "hp_red": ("HP_RED", "BLOOD"),
        "hp_dark": ("BLOOD_DIM", "HP_RED"),
        "block_blue": ("BLOCK_BLUE", "BLOCK_BLUE_DIM"),
        "energy": ("ENERGY_YELLOW", "GOLD"),
        "energy_dark": ("GOLD_DIM", "GOLD"),
        "poison": ("POISON", "POISON_DIM"),
        "buff": ("GOLD", "ENERGY_YELLOW"),
        "debuff": ("RARITY_SPECIAL", "POISON"),
        "danger": ("BLOOD", "HP_RED"),
        "good": ("POISON", "CYAN"),
        "glow": ("CYAN", "BORDER_HI"),
        "black": ("BLACK",),
        "white": ("WHITE",),
        "common": ("RARITY_COMMON",),
        "uncommon": ("RARITY_UNCOMMON",),
        "rare": ("RARITY_RARE",),
        "basic": ("RARITY_BASIC",),
        "curse": ("RARITY_SPECIAL",),
        "status": ("RARITY_BASIC",),
        "attack": ("RARITY_RARE",),
        "skill": ("CYAN",),
        "power": ("RARITY_SPECIAL",),
    }

    def color(self, name: str, default: Optional[str] = None) -> str:
        """取主题色。优先 ui/theme.py，其次内置回退表。"""
        mod = _theme_mod
        if mod is not None:
            # 1) theme.color("name") 若队友提供了函数
            fn = getattr(mod, "color", None)
            if callable(fn):
                try:
                    v = fn(name)
                    if v:
                        return str(v)
                except Exception:
                    pass
            # 2) 按别名表取 theme 顶层常量
            for cand in self._THEME_ALIASES.get(name, ()):
                v = getattr(mod, cand, None)
                if isinstance(v, str) and v.startswith("#"):
                    return v
            # 3) 字典表
            for dict_name in ("COLORS", "C", "PALETTE"):
                d = getattr(mod, dict_name, None)
                if isinstance(d, dict):
                    for key in (name, name.upper(), name.lower()):
                        if key in d:
                            return str(d[key])
            # 4) 同名 / 大写的顶层常量
            for cand in (name, name.upper()):
                v = getattr(mod, cand, None)
                if isinstance(v, str) and v.startswith("#"):
                    return v
        if default:
            return default
        return FALLBACK_COLORS.get(name, FALLBACK_COLORS["text"])

    def semi(self, fg: str, alpha: float, bg: Optional[str] = None) -> str:
        """Tk 画布无 alpha：用与背景混色模拟半透明（优先 theme.with_alpha_on）。"""
        mod = _theme_mod
        base = bg or self.color("bg_deep")
        fn = getattr(mod, "with_alpha_on", None) if mod is not None else None
        if callable(fn):
            try:
                return str(fn(base, fg, alpha))
            except Exception:
                pass
        return with_alpha(fg, base, alpha)

    def shade(self, c: str, amount: float) -> str:
        """amount>0 变亮，<0 变暗（优先 theme.shade）。"""
        mod = _theme_mod
        fn = getattr(mod, "shade", None) if mod is not None else None
        if callable(fn):
            try:
                return str(fn(c, amount))
            except Exception:
                pass
        return lighten(c, amount) if amount >= 0 else darken(c, -amount)

    def lerp(self, c1: str, c2: str, t: float) -> str:
        mod = _theme_mod
        fn = getattr(mod, "lerp_color", None) if mod is not None else None
        if callable(fn):
            try:
                return str(fn(c1, c2, t))
            except Exception:
                pass
        return mix(c1, c2, t)

    def wrap_text(self, text: str, px: int, font=None, max_lines=None) -> List[str]:
        """中文友好折行：优先 theme.wrap_text_cjk。"""
        mod = _theme_mod
        fn = getattr(mod, "wrap_text_cjk", None) if mod is not None else None
        if callable(fn):
            try:
                return list(fn(text, px, font=font, max_lines=max_lines))
            except Exception:
                pass
        lines = self._wrap(text, px, font or self.font_small)
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1][:-1] + "…"
        return lines

    def intent_color(self, intent: str) -> str:
        mod = _theme_mod
        fn = getattr(mod, "intent_color", None) if mod is not None else None
        if callable(fn):
            try:
                return str(fn(intent))
            except Exception:
                pass
        d = getattr(mod, "INTENT_COLORS", {}) if mod is not None else {}
        if isinstance(d, dict) and intent in d:
            return str(d[intent])
        return FALLBACK_COLORS.get("danger" if "attack" in str(intent)
                                   else "text_dim")

    def buff_color(self, key: str) -> str:
        mod = _theme_mod
        fn = getattr(mod, "buff_color", None) if mod is not None else None
        if callable(fn):
            try:
                return str(fn(key))
            except Exception:
                pass
        d = getattr(mod, "BUFF_COLORS", {}) if mod is not None else {}
        if isinstance(d, dict) and key in d:
            return str(d[key])
        return self.color("text_dim")

    def node_color(self, kind: str) -> str:
        mod = _theme_mod
        fn = getattr(mod, "node_color", None) if mod is not None else None
        if callable(fn):
            try:
                return str(fn(kind))
            except Exception:
                pass
        d = getattr(mod, "NODE_COLORS", {}) if mod is not None else {}
        if isinstance(d, dict) and kind in d:
            return str(d[kind])
        return self.color("border_light")

    def glow_ring(self, x1, y1, x2, y2, r, color, **kw):
        mod = _theme_mod
        fn = getattr(mod, "glow_ring", None) if mod is not None else None
        if callable(fn):
            try:
                return fn(self.canvas, x1, y1, x2, y2, r, color, **kw)
            except Exception:
                pass
        for i in range(3):
            a = 0.10 + 0.08 * i
            self.round_rect(x1 - i * 2, y1 - i * 2, x2 + i * 2, y2 + i * 2,
                            r + i * 2, fill="",
                            outline=self.semi(color, a), width=2)

    def rarity_color(self, rarity: str) -> str:
        mod = _theme_mod
        if mod is not None:
            d = getattr(mod, "RARITY_COLORS", None)
            if isinstance(d, dict) and rarity in d:
                return str(d[rarity])
            rfn = getattr(mod, "rarity_color", None)
            if callable(rfn):
                try:
                    v = rfn(rarity)
                    if v:
                        return str(v)
                except Exception:
                    pass
        return FALLBACK_COLORS.get(rarity, FALLBACK_COLORS["common"])

    def type_color(self, ctype: str) -> str:
        mod = _theme_mod
        if mod is not None:
            for dn in ("TYPE_COLORS", "CARD_TYPE_COLORS"):
                d = getattr(mod, dn, None)
                if isinstance(d, dict) and ctype in d:
                    return str(d[ctype])
        return FALLBACK_COLORS.get(ctype, FALLBACK_COLORS["common"])

    # ------------------------------------------------------------ 主题绘制 -- #
    def round_rect(self, x1, y1, x2, y2, r=12, **kw):
        """圆角矩形：优先 theme.round_rect，否则自带多边形回退。"""
        mod = _theme_mod
        fn = getattr(mod, "round_rect", None) if mod is not None else None
        if callable(fn):
            try:
                return fn(self.canvas, x1, y1, x2, y2, r, **kw)
            except TypeError:
                try:
                    return fn(self.canvas, x1, y1, x2, y2, r, kw)
                except Exception:
                    pass
            except Exception:
                pass
        pts: List[float] = []
        r = max(0, min(r, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0))
        steps = 6
        import math as _m
        corners = ((x2 - r, y1 + r, -90, 0), (x2 - r, y2 - r, 0, 90),
                   (x1 + r, y2 - r, 90, 180), (x1 + r, y1 + r, 180, 270))
        for cx, cy, a0, a1 in corners:
            for i in range(steps + 1):
                a = _m.radians(a0 + (a1 - a0) * i / steps)
                pts.extend((cx + r * _m.cos(a), cy + r * _m.sin(a)))
        return self.canvas.create_polygon(pts, smooth=False, **kw)

    def vgradient(self, x1, y1, x2, y2, c1, c2, steps=48, tags=None):
        """垂直线性渐变（用一堆细矩形拼）。"""
        mod = _theme_mod
        fn = getattr(mod, "vgradient", None) if mod is not None else None
        if callable(fn):
            try:
                return fn(self.canvas, x1, y1, x2, y2, c1, c2, steps=steps)
            except TypeError:
                try:
                    return fn(self.canvas, x1, y1, x2, y2, c1, c2, steps)
                except Exception:
                    pass
            except Exception:
                pass
        h = (y2 - y1) / float(max(1, steps))
        ids = []
        for i in range(steps):
            c = mix(c1, c2, i / float(max(1, steps - 1)))
            kw = {"fill": c, "outline": ""}
            if tags:
                kw["tags"] = tags
            ids.append(self.canvas.create_rectangle(x1, y1 + i * h, x2,
                                                    y1 + (i + 1) * h + 1, **kw))
        return ids

    def draw_arc_text(self, x, y, text, font=None, fill=None, anchor="center",
                      angle=0.0, tags=None):
        """带旋转的文字（手牌弧线用）。优先 theme.draw_arc_text。"""
        mod = _theme_mod
        fn = getattr(mod, "draw_arc_text", None) if mod is not None else None
        if callable(fn):
            try:
                return fn(self.canvas, x, y, text, font=font,
                          fill=fill or self.color("text"), anchor=anchor,
                          angle=angle, tags=tags)
            except Exception:
                pass
        kw = {"text": text, "font": font or self.font_body,
              "fill": fill or self.color("text"), "anchor": anchor}
        if tags:
            kw["tags"] = tags
        return [self.canvas.create_text(x, y, **kw)]

    def text_width(self, text: str, font=None) -> int:
        mod = _theme_mod
        fn = getattr(mod, "text_size", None) if mod is not None else None
        if callable(fn):
            try:
                return int(fn(text, font=font, root=self)[0])
            except Exception:
                pass
        try:
            return self.font_measure(text, font or self.font_small)
        except Exception:
            return len(str(text)) * 8

    def font_measure(self, text: str, font) -> int:
        f = tkfont.Font(root=self, font=font)
        return f.measure(text)

    def text_center(self, x, y, text, font=None, fill=None, tags=None):
        kw = {"text": text, "font": font or self.font_body,
              "fill": fill or self.color("text"), "anchor": "center"}
        if tags:
            kw["tags"] = tags
        return self.canvas.create_text(x, y, **kw)

    def refresh_fonts(self) -> None:
        """重新解析字体（语言切换后调用；字体缺失时静默跳过）。"""
        try:
            if _theme_mod is not None and hasattr(_theme_mod, "init_fonts"):
                _theme_mod.init_fonts()
                self._reload_fonts()
        except Exception:
            pass

    def text_shadow(self, x, y, text, font=None, fill=None, anchor="center",
                    shadow="#000000", off=2, tags=None):
        # i18n：所有 Tk 界面文字都经过这里，因此在这一处做统一翻译，
        # 不必去改几千个调用点。中文时 t() 是恒等函数，零开销。
        text = _i18n.t(text)
        kw = dict(font=font or self.font_body, fill=shadow, anchor=anchor)
        if tags:
            kw["tags"] = tags
        self.canvas.create_text(x + off, y + off, text=text, **kw)
        kw["fill"] = fill or self.color("text")
        return self.canvas.create_text(x, y, text=text, **kw)

    # --------------------------------------------------------------- 调度 -- #
    def _schedule_frame(self) -> None:
        try:
            self._frame_job = self.after(FRAME_MS, self._frame)
        except Exception:
            self._frame_job = None

    def _frame(self) -> None:
        self._tick += 1
        try:
            if self._bg_step():
                self.redraw()
            self._step_damage_numbers()
            if self._step_shake():
                self.redraw()
            self._step_flash()
            _c = getattr(self, "console", None)
            if _c is not None and _c.open:
                _c.tick()
                self.redraw()
        except Exception:
            traceback.print_exc()
        self._schedule_frame()

    def every(self, key: str, ms: int, fn: Callable, run_now: bool = False) -> str:
        """带 key 的 after 循环，重复调用会取消旧的，避免重复任务堆积。"""
        self.cancel(key)
        if run_now:
            try:
                fn()
            except Exception:
                traceback.print_exc()

        def loop():
            try:
                fn()
            except Exception:
                traceback.print_exc()
            if key in self._jobs:
                self._jobs[key] = self.after(ms, loop)

        self._jobs[key] = self.after(ms, loop)
        return self._jobs[key]

    def once(self, ms: int, fn: Callable) -> str:
        return self.after(ms, fn)

    def cancel(self, key: str) -> None:
        job = self._jobs.pop(key, None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def cancel_all(self) -> None:
        for key in list(self._jobs):
            self.cancel(key)

    def scaled(self, ms: float) -> int:
        """按用户设置的动画速度缩放时长。"""
        speed = _num(self.settings.get("anim_speed", 1.0), 1.0) or 1.0
        if speed <= 0:
            return 0
        return max(0, int(ms / speed))

    # -------------------------------------------------------------- 界面 -- #
    def show(self, screen_name: str, **kwargs) -> None:
        """路由到指定界面，带 200ms 淡入。"""
        if screen_name not in SCREENS:
            screen_name = "menu"
        self._show_direct(screen_name, fade=True, **kwargs)

    def _show_direct(self, screen_name: str, fade: bool = False, **kwargs) -> None:
        self.cancel_all()
        self._hide_tooltip()
        self._damage_numbers.clear()
        self._shake[0] = 0.0
        self.screen_name = screen_name
        self._music_for(screen_name)
        try:
            old = self.view
            if old is not None:
                close = getattr(old, "on_destroy", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        traceback.print_exc()
            self.canvas.delete("all")
            factory = _make_view(screen_name)
            self.view = factory(self)
            self.view.kwargs = kwargs
            self.view.build(kwargs)
            self.redraw()
            if fade:
                self.fade_in()
        except Exception:
            traceback.print_exc()
            self._error_screen(screen_name)

    def reload(self) -> None:
        """用当前 kwargs 重建当前界面（数据变化后刷新）。"""
        self._show_direct(self.screen_name,
                          **getattr(self.view, "kwargs", {}))

    def _error_screen(self, name: str) -> None:
        self.canvas.delete("all")
        c = self.canvas
        w, h = self.winfo_width() or self.WIDTH, self.winfo_height() or self.HEIGHT
        c.create_rectangle(0, 0, w, h, fill=self.color("bg_deep"), outline="")
        self.vgradient(0, 0, w, h, self.color("bg_mid"), self.color("bg_abyss"), 40)
        self.text_shadow(w / 2, h / 2 - 20, "界面渲染失败：%s" % name,
                         font=self.font_h1, fill=self.color("danger"))
        self.text_shadow(w / 2, h / 2 + 30, "按 Esc 返回主菜单",
                         font=self.font_body, fill=self.color("text_dim"))
        self.view = None

    def _music_for(self, screen_name: str) -> None:
        """按界面切换 BGM（music/ 目录由用户放置）。"""
        try:
            # Tkinter 版没有 QApplication；允许音频层自建一个无窗口的 Qt 应用，
            # 这样可以用 QtMultimedia 播放（本机 afplay 无法播放 ogg）。
            import os as _os
            _os.environ.setdefault("SF_ALLOW_HEADLESS_QT", "1")
            from core import audio
            vol = int(self.settings.get("volume", 70))
            on = bool(self.settings.get("music", True))
            audio.on_screen(screen_name, volume=vol, enabled=on)
        except Exception:
            pass

    def restart_music(self) -> None:
        """音量/开关变化后重新应用。"""
        self._music_for(self.screen_name)

    def redraw(self) -> None:
        if self.view is None:
            return
        try:
            self.view.draw()
        except Exception:
            traceback.print_exc()
        # 控制台永远画在最上层
        con = getattr(self, "console", None)
        if con is not None and con.open:
            try:
                con.draw(self.canvas, self.W, self.H)
            except Exception:
                traceback.print_exc()

    def _install_cheat_hook(self) -> None:
        """兑换码结束战斗后通知界面（否则画面卡在战斗里）。"""
        try:
            from core import cheats as _ch

            def _on_over(_result: str) -> None:
                try:
                    view = getattr(self, "view", None)
                    fn = getattr(view, "_check_end", None)
                    if callable(fn):
                        fn()
                except Exception:
                    pass

            _ch.set_battle_over_hook(_on_over)
        except Exception:
            pass

    def _on_configure(self, event) -> None:
        if abs(event.width - self._last_wh[0]) < 2 and \
           abs(event.height - self._last_wh[1]) < 2:
            return
        self._last_wh = (event.width, event.height)
        self._init_bg_sprites()
        rebuild = getattr(self.view, "on_resize", None)
        if callable(rebuild):
            try:
                rebuild(event.width, event.height)
            except Exception:
                traceback.print_exc()
        self.redraw()

    def _on_f1(self, _event=None) -> str:
        con = getattr(self, "console", None)
        if con is not None:
            con.toggle()
        return "break"

    def _on_key(self, event) -> None:
        """按键分发：控制台优先，其次当前 view。"""
        con = getattr(self, "console", None)
        if con is not None and con.open:
            try:
                if con.on_key(event):
                    return
            except Exception:
                pass
        view = self.view
        for name in ("on_key", "_cheat_key"):
            fn = getattr(view, name, None)
            if callable(fn):
                try:
                    fn(event)
                except Exception:
                    pass
                return

    def _on_escape(self, _event=None) -> None:
        con = getattr(self, "console", None)
        if con is not None and con.open:
            con.close()
            return
        if self.screen_name in ("battle",):
            return  # 战斗中不允许直接退出，避免误触
        if self.screen_name != "menu":
            if self.run is not None and self.screen_name in ("deck", "codex",
                                                             "stats", "settings",
                                                             "achievements"):
                self.show("map" if self.run is not None else "menu")
            else:
                self.show("menu")
        else:
            self.quit()

    # ---------------------------------------------------------------- 尺寸 -- #
    @property
    def W(self) -> int:
        """当前视口宽度。

        ``winfo_width()`` 在窗口尚未映射时会返回 1（而不是 0），直接使用会让
        所有界面按 1x1 布局并把内容挤到左上角，因此这里显式过滤掉 <=1 的
        占位值，退回窗口请求尺寸。
        """
        try:
            v = int(self.winfo_width())
        except Exception:
            v = 0
        return v if v > 1 else self.WIDTH

    @property
    def H(self) -> int:
        """当前视口高度（同样过滤未映射时的占位值 1）。"""
        try:
            v = int(self.winfo_height())
        except Exception:
            v = 0
        return v if v > 1 else self.HEIGHT

    # ------------------------------------------------------------ 背景粒子 -- #
    def _init_bg_sprites(self) -> None:
        """初始化硝烟粒子（确定性伪随机，不污染 run.rng）。"""
        self._bg_sprites = []
        w, h = self.W, self.H
        # 确定性伪随机（避免裸 random.*，也不用 run.rng 污染战斗随机序列）
        seed = 20241013
        for i in range(90):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            x = (seed % max(1, w))
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            y0 = (seed % max(1, h))
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            speed = 0.25 + (seed % 100) / 140.0
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            radius = 1.0 + (seed % 100) / 34.0
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            phase = (seed % 360)
            self._bg_sprites.append({
                "x": float(x), "y": float(y0), "spd": speed,
                "r": radius, "phase": phase,
                "drift": ((seed % 40) - 20) / 60.0,
            })

    def _bg_step(self) -> bool:
        """推进硝烟粒子；返回 True 表示需要整体重绘。"""
        if getattr(self.view, "wants_bg", False) is False and self.screen_name not in (
                "battle", "map", "menu"):
            return False
        moved = False
        w, h = self.W, self.H
        for s in self._bg_sprites:
            s["y"] -= s["spd"] * 1.6
            s["x"] += s["drift"] * 0.4
            if s["y"] < -10:
                s["y"] = h + 8
            if s["x"] < -10:
                s["x"] = w + 8
            elif s["x"] > w + 10:
                s["x"] = -8
            moved = True
        return moved

    def draw_smoke(self, tag: str = "bg") -> None:
        """把硝烟粒子画到当前画布。"""
        import math as _m
        c = self.canvas
        for s in self._bg_sprites:
            wob = _m.sin(_m.radians((self._tick * 2 + s["phase"]) % 360))
            x = s["x"] + wob * 5
            y = s["y"]
            r = s["r"]
            t = max(0.05, min(1.0, 1.0 - (y / float(max(1, self.H)))))
            col = mix(self.color("bg_mid"), "#bfeaff", 0.25 + 0.5 * t)
            c.create_oval(x - r, y - r, x + r, y + r, outline=col, width=1,
                          tags=tag)
            if r > 2.0:
                c.create_oval(x - r * 0.45, y - r * 0.45, x + r * 0.1,
                              y + r * 0.1, outline=mix(col, "#ffffff", 0.5),
                              width=1, tags=tag)

    # ------------------------------------------------------------- 淡入 -- #
    def fade_in(self, on_done: Optional[Callable] = None) -> None:
        """200ms 淡入：在画布上叠一层由深到透明的遮罩。"""
        self._fade_done = on_done
        if self._fade_job:
            try:
                self.after_cancel(self._fade_job)
            except Exception:
                pass
            self._fade_job = None
        w, h = self.W, self.H
        steps = 8
        base = self.color("bg_abyss")

        def step(i: int) -> None:
            try:
                self.canvas.delete("fade")
                if i >= steps:
                    self._fade_job = None
                    cb, self._fade_done = self._fade_done, None
                    if callable(cb):
                        cb()
                    return
                a = 1.0 - i / float(steps)
                if a > 0.01:
                    self.canvas.create_rectangle(
                        0, 0, w, h, fill=with_alpha(base, base, a),
                        outline="", tags="fade")
                self.canvas.tag_raise("fade")
                self._fade_job = self.after(max(10, FADE_MS // steps),
                                            lambda: step(i + 1))
            except Exception:
                self._fade_job = None

        step(0)

    # --------------------------------------------------------- 震屏 / 闪白 -- #
    def shake(self, strength: float = 10.0, ms: int = 260) -> None:
        self._shake[0] = max(self._shake[0], float(ms))
        self._shake[1] = max(self._shake[1], float(strength))
        self._shake[2] = 0.0

    def _step_shake(self) -> bool:
        import math as _m
        if self._shake[0] <= 0:
            if self._shake[1] != 0.0:
                self._shake[1] = 0.0
                # 复位兜底（视图自带 set_shake 时本就不需要它）
                self.canvas.move("all", 0, 0)
            return False
        self._shake[0] -= FRAME_MS
        self._shake[2] += 0.9
        amp = self._shake[1] * max(0.0, self._shake[0] / 260.0)
        dx = _m.sin(self._shake[2]) * amp
        dy = _m.cos(self._shake[2] * 1.7) * amp * 0.6
        if hasattr(self.view, "set_shake"):
            try:
                self.view.set_shake(dx, dy)
            except Exception:
                pass
        else:
            self.canvas.move("all", int(dx), int(dy))
        return True

    def flash(self, color: Optional[str] = None, ms: int = 160) -> None:
        self._overlay_flash[0] = color or "#ffffff"
        self._overlay_flash[1] = float(ms)

    def _step_flash(self) -> None:
        if self._overlay_flash[0] is None:
            return
        self._overlay_flash[1] -= FRAME_MS
        col, left = self._overlay_flash
        try:
            self.canvas.delete("flashover")
            if left <= 0:
                self._overlay_flash[0] = None
                return
            base = self.color("bg_deep")
            a = min(0.55, left / 200.0)
            self.canvas.create_rectangle(0, 0, self.W, self.H, fill=with_alpha(
                col, base, a), outline="", tags="flashover")
            self.canvas.tag_raise("flashover")
        except Exception:
            self._overlay_flash[0] = None

    # -------------------------------------------------------- 伤害飘字 -- #
    def _damage_number_cls(self):
        """widgets.DamageNumber（若队友提供）；结果缓存于 _dn_cls。"""
        if self._dn_cls is _UNSET:
            cls = None
            try:
                from .widgets import DamageNumber
                if callable(getattr(DamageNumber, "spawn", None)):
                    cls = DamageNumber
            except Exception:
                cls = None
            self._dn_cls = cls
        return self._dn_cls

    def pop_number(self, x: float, y: float, text: str, color: str = "#ffffff",
                   size: int = 26, life: int = 850, drift: float = -2.2) -> None:
        if not self.settings.get("damage_numbers", True):
            return
        cls = self._damage_number_cls()
        if cls is not None:
            try:
                cls.spawn(self.canvas, x, y, str(text), color=color, size=size)
                return
            except Exception:
                self._dn_cls = None
        self._damage_numbers.append({
            "x": float(x), "y": float(y), "text": str(text), "color": color,
            "size": size, "life": float(life), "max": float(life),
            "vy": drift, "kind": "num",
        })

    def pop_text(self, x: float, y: float, text: str, color: str = "#ffffff",
                 size: int = 20, life: int = 900, drift: float = -1.4) -> None:
        self._damage_numbers.append({
            "x": float(x), "y": float(y), "text": str(text), "color": color,
            "size": size, "life": float(life), "max": float(life),
            "vy": drift, "kind": "text",
        })
        # 文字提示也交给 widgets 叠一层（视觉更统一）
        cls = self._damage_number_cls()
        if cls is not None:
            try:
                cls.spawn(self.canvas, x, y, str(text), color=color, size=size)
                self._damage_numbers.pop()
            except Exception:
                self._dn_cls = None

    def _step_damage_numbers(self) -> None:
        if not self._damage_numbers:
            return
        alive = []
        for d in self._damage_numbers:
            d["life"] -= FRAME_MS
            d["y"] += d["vy"]
            d["vy"] *= 0.985
            if d["life"] > 0:
                alive.append(d)
        self._damage_numbers = alive

    def draw_damage_numbers(self, tag: str = "dmg") -> None:
        c = self.canvas
        for d in self._damage_numbers:
            t = d["life"] / d["max"]
            size = int(d["size"] * (0.85 + 0.35 * min(1.0, (1.0 - t) * 4)))
            col = mix(self.color("bg_deep"), d["color"], max(0.12, min(1.0, t * 1.6)))
            f = _safe_font(self, max(8, size), True)
            c.create_text(d["x"] + 2, d["y"] + 2, text=d["text"], font=f,
                          fill="#000000", anchor="center", tags=tag)
            c.create_text(d["x"], d["y"], text=d["text"], font=f, fill=col,
                          anchor="center", tags=tag)

    # ------------------------------------------------------------ tooltip -- #
    def show_tooltip(self, text: str, x: float, y: float,
                     title: str = "", color: Optional[str] = None,
                     width: int = 300) -> None:
        self.canvas.delete("tooltip")
        if not text:
            return
        pad = 10
        lines = self._wrap(text, width - pad * 2, self.font_small)
        th = 22 * len(lines) + pad * 2 + (24 if title else 0)
        tw = width
        # 避免出屏
        x = max(8, min(self.W - tw - 8, x))
        if y + th + 14 > self.H:
            y = y - th - 18
        y = max(8, y + 14)
        c = self.canvas
        self.round_rect(x, y, x + tw, y + th, 10,
                        fill=with_alpha(self.color("panel_dark"),
                                        self.color("bg_deep"), 0.94),
                        outline=color or self.color("border_light"), width=2,
                        tags="tooltip")
        ty = y + pad
        if title:
            c.create_text(x + pad, ty + 4, text=title, font=self.font_h2,
                          fill=color or self.color("gold"), anchor="w",
                          tags="tooltip")
            ty += 24
        for ln in lines:
            c.create_text(x + pad, ty + 4, text=ln, font=self.font_small,
                          fill=self.color("text"), anchor="w", tags="tooltip")
            ty += 22
        c.tag_raise("tooltip")

    def _hide_tooltip(self, _e=None) -> None:
        try:
            self.canvas.delete("tooltip")
        except Exception:
            pass

    def _wrap(self, text: str, px: int, font) -> List[str]:
        """按像素宽度粗略折行（中文按整字，英文按词）。"""
        try:
            f = tkfont.Font(font=font)
            measure = f.measure
        except Exception:
            measure = lambda s: len(s) * 8  # noqa: E731
        out: List[str] = []
        for para in str(text).split("\n"):
            cur = ""
            for ch in para:
                if measure(cur + ch) > px and cur:
                    out.append(cur)
                    cur = ch
                else:
                    cur += ch
            out.append(cur)
        return out or [""]

    # ------------------------------------------------------------- 运行态 -- #
    def start_new_run(self, seed: Optional[int] = None,
                      ascension: int = 0, character: str = "commander") -> bool:
        mod = self.core.run
        cls = getattr(mod, "RunState", None) if mod else None
        if cls is None:
            self.run = None
            return False
        try:
            run = cls()
        except Exception:
            try:
                run = cls(rng=None)  # type: ignore
            except Exception:
                traceback.print_exc()
                self.run = None
                return False
        self.run = run
        fn = _call(run, "new_run")
        ok = _try(fn, seed=seed, ascension=ascension, character=character,
                  default=False)
        if ok is False:
            _try(fn, seed, ascension, character, default=None)
        self.battle = None
        return True

    def start_battle(self, encounter: Any = None) -> bool:
        """用 run + 遭遇创建 BattleState（附录 A.1：``make_battle(run, encounter)``）。"""
        eng = self.core.engine
        if eng is None or self.run is None:
            self.battle = None
            return False
        enc = encounter
        if isinstance(enc, dict) and "encounter" in enc and \
                isinstance(enc.get("encounter"), dict):
            enc = enc["encounter"]
        if enc is None:
            enc = {"kind": "normal",
                   "enemies": _attr(self.run, "encounter_enemies", default=None)
                   or ["squid_scout"]}
        battle = None
        fn = getattr(eng, "make_battle", None)
        if callable(fn):
            battle = _try(fn, self.run, enc, default=None)
            if battle is None:
                battle = _try(fn, self.run, enc, default=None)
        if battle is None:
            # 退化路径：自行拼 Combatant（core 未就绪时不至于崩）
            cls = getattr(eng, "BattleState", None)
            if cls is not None:
                enemies = self.make_enemies(enc)
                rng = _attr(self.run, "rng", default=None)
                for args in ((self.run, enemies, rng), (self.run, enemies),
                             (enemies, rng)):
                    battle = _try(cls, *args, default=None)
                    if battle is not None:
                        break
        self.battle = battle
        if battle is not None:
            _try(_call(battle, "start_battle"))
        return battle is not None

    def make_enemies(self, encounter: Any) -> List[Any]:
        """把 encounter 描述转换成 Combatant 列表。

        附录 A.1 冻结入口：``core.engine.make_enemy_combatant(def_id, rng, ascension, act)``。
        """
        eng = self.core.engine
        if eng is None:
            return []
        fn = getattr(eng, "make_enemy_combatant", None)
        if not callable(fn):
            return self._make_enemies_fallback(encounter)
        rng = _attr(self.run, "rng", default=None)
        asc = int(_num(_attr(self.run, "ascension", default=0), 0))
        act = int(_num(_attr(self.run, "act", default=1), 1)) or 1
        out = []
        for eid in self.encounter_ids(encounter):
            c = None
            for args, kwargs in (
                    ((eid, rng, asc, act), {}),
                    ((eid, rng), {"ascension": asc, "act": act}),
                    ((eid,), {"rng": rng, "ascension": asc, "act": act}),
                    ((eid,), {}),
            ):
                c = _try(fn, *args, default=None, **kwargs)
                if c is not None:
                    break
            if c is not None:
                out.append(c)
        return out

    def encounter_ids(self, encounter: Any) -> List[str]:
        """从 encounter（dict / list / str / run.move_to 返回值）中取出敌人 id 列表。"""
        if encounter is None:
            return []
        if isinstance(encounter, str):
            return [encounter]
        if isinstance(encounter, (list, tuple)):
            return [x if isinstance(x, str) else _attr(x, "id", "name", default=str(x))
                    for x in encounter]
        if isinstance(encounter, dict):
            enc = encounter.get("encounter", encounter)
            if isinstance(enc, dict):
                for key in ("enemies", "ids", "list", "encounter"):
                    v = enc.get(key)
                    if isinstance(v, (list, tuple)) and v:
                        return [x if isinstance(x, str) else
                                _attr(x, "id", "name", default=str(x)) for x in v]
                    if isinstance(v, str) and v:
                        return [v]
            for key in ("enemies", "ids", "list"):
                v = encounter.get(key)
                if isinstance(v, (list, tuple)) and v:
                    return [x if isinstance(x, str) else
                            _attr(x, "id", "name", default=str(x)) for x in v]
                if isinstance(v, str) and v:
                    return [v]
        return []

    def _make_enemies_fallback(self, encounter: Any) -> List[Any]:
        eng = self.core.engine
        cls = getattr(eng, "Combatant", None)
        out = []
        for eid in (self.encounter_ids(encounter) or ["squid_scout"]):
            c = None
            if cls is not None:
                c = _try(cls, eid, default=None)
                if c is None:
                    c = _try(cls, eid, 20, default=None)
            if c is not None:
                out.append(c)
        return out
    def meta_progress(self):
        if self.meta is None:
            mod = self.core.run
            cls = getattr(mod, "MetaProgress", None) if mod else None
            if cls is not None:
                self.meta = _try(_call(cls, "load"), default=None)
                if self.meta is None:
                    self.meta = _try(cls, default=None)
        return self.meta

    def save_meta(self) -> None:
        m = self.meta_progress()
        if m is not None:
            _try(_call(m, "save"))

    def quit_game(self) -> None:
        try:
            self.save_meta()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


__all__ = ["App", "SCREENS", "FADE_MS", "mix", "lighten", "darken",
           "with_alpha", "MISSING"]
