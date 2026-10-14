"""钢铁战线 —— 战斗界面（全屏 Canvas 手绘）。

视觉结构（自下而上）
--------------------
1. 战场背景：焦土渐变 + 地平线火光 + 硝烟粒子 + 曳光弹 + 铁丝网剪影
2. 战斗台：玩家坦克 / 总部碉堡立绘（程序化几何绘制）、敌方装甲单位（按 ``EnemyDef.art`` 映射）
3. 单位信息：总部 HP / 掩体 / 状态徽章 / 附属单位行动条 / 敌人头顶意图图标
4. HUD：补给桶、牌库 / 弃牌堆 / 移除区计数、勋章栏、回合数
5. 手牌（作战手令）：**弧形排列**，悬停上浮放大 1.35 倍并显示 tooltip，点击选中
6. 特效层：伤害飘字、屏幕震动（整层偏移重绘）、受击闪白、击毁烟尘

工程约束
--------
* 全部动画走 ``self.app.after()``；本文件**不含 time.sleep**。
* 渲染数据全部来自 ``battle.snapshot()``；UI 不读 core 内部字段。
* snapshot 缺字段 / 数据为空 / core 未就绪，一律降级渲染，不崩。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk

from . import art as A
from . import theme as T

# 主题常量容错（theme.py 由 ui-theme 维护）
BG_DEEP = getattr(T, "BG_DEEP", "#0A1420")
PANEL = getattr(T, "PANEL", "#12233A")
PANEL_HI = getattr(T, "PANEL_HI", "#1B3554")
BORDER = getattr(T, "BORDER", "#1E3A5F")
BORDER_HI = getattr(T, "BORDER_HI", "#2E5580")
CYAN = getattr(T, "CYAN", "#3FD8D0")
GOLD = getattr(T, "GOLD", "#F2C14E")
BLOOD = getattr(T, "BLOOD", "#E5484D")
TEXT = getattr(T, "TEXT", "#E6EEF6")
TEXT_DIM = getattr(T, "TEXT_DIM", "#9AB0C6")
TEXT_FAINT = getattr(T, "TEXT_FAINT", "#5D7691")
POISON = getattr(T, "POISON", "#7BC950")
SMOKE = getattr(T, "SMOKE", "#3A3630")
OLIVE = getattr(T, "OLIVE", getattr(T, "CYAN", "#6B7F3A"))
STEEL = getattr(T, "STEEL", "#5A6470")
RUST = getattr(T, "RUST", "#8B5A2B")
BLOCK_BLUE = getattr(T, "BLOCK_BLUE", "#7FB4E8")
ENERGY_YELLOW = getattr(T, "ENERGY_YELLOW", "#FFD966")
HP_RED = getattr(T, "HP_RED", "#C93B41")
RARITY_COLORS = getattr(T, "RARITY_COLORS", {"common": "#C7D6E4",
                                             "uncommon": "#3FD8D0",
                                             "rare": "#F2C14E"})
TYPE_COLORS = getattr(T, "TYPE_COLORS", {"attack": "#E5484D",
                                         "skill": "#3FD8D0",
                                         "power": "#F2C14E"})
INTENT_COLORS = getattr(T, "INTENT_COLORS", {"attack": "#E5484D",
                                             "defend": "#7FB4E8",
                                             "buff": "#F2C14E",
                                             "debuff": "#B07BE8"})
BUFF_COLORS = getattr(T, "BUFF_COLORS", {})

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

BUFF_NAMES = {
    "strength": "火力", "strength_down": "弹药短缺", "dexterity": "机动",
    "vulnerable": "破甲", "weak": "压制", "frail": "混乱", "poison": "燃烧",
    "thorns": "铁丝网", "metallicize": "工事", "ritual": "增援",
    "artifact": "干扰弹", "plated_armor": "装甲板", "regenerate": "战地医疗",
    "intangible": "烟幕", "barrier": "坚守", "chain": "连射",
    "envenom": "燃烧弹", "accuracy": "瞄准",
}
BUFF_DESC = {
    "strength": "每层使攻击牌伤害 +1。",
    "strength_down": "每层使攻击牌伤害 -1。",
    "dexterity": "每层使获得的掩体 +1。",
    "vulnerable": "受到的攻击伤害 +50%（每回合 -1 层）。",
    "weak": "造成的攻击伤害 -25%（每回合 -1 层）。",
    "frail": "获得的掩体 -25%（每回合 -1 层）。",
    "poison": "回合开始时按层数受到伤害，然后 -1 层。",
    "thorns": "被近战攻击时反弹等量伤害。",
    "metallicize": "回合结束时获得等量掩体。",
    "ritual": "每回合结束获得等量火力。",
    "artifact": "每层抵挡一次负面状态。",
    "plated_armor": "回合结束时获得等量掩体。",
    "regenerate": "回合结束时修复等量总部 HP。",
    "intangible": "受到的伤害降为 1。",
    "barrier": "回合末不清空的掩体。",
    "chain": "本回合每打出一张牌，下一张攻击 +1 伤害。",
    "envenom": "攻击造成伤害时施加等量中毒。",
    "accuracy": "每层使小刀类伤害 +1。",
}

CARD_W = int(getattr(T, "CARD_W", 168))
_UNSET = object()
CARD_H = int(getattr(T, "CARD_H", 236))
HAND_SCALE_HOVER = 1.35      # 需求：悬停放大 1.35 倍
HAND_ARC_H = 46.0            # 弧线两端相对中心的下沉量
HAND_MAX_ROT = 8.0
HAND_BASE_Y_OFF = 46         # 手牌中心相对底边的上移量
ENEMY_STEP_MS = 400          # 敌方回合节奏（附录 A.6）

DIFF_NAMES = ["普通", "进阶 I", "进阶 II", "进阶 III", "进阶 IV", "进阶 V"]


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


# --------------------------------------------------------------------------- #
# 战斗界面
# --------------------------------------------------------------------------- #
class BattleView:
    """战斗界面渲染器（由 ``App`` 实例化，接口：build / draw / on_resize）。"""

    wants_bg = False

    def __init__(self, app) -> None:
        self.app = app
        self.c = app.canvas
        self.w = app.W
        self.h = app.H
        self.snap: Dict[str, Any] = {}
        self.kwargs: Dict[str, Any] = {}

        # 交互状态
        self.hover_card: Optional[int] = None      # 手牌索引
        self.selected: Optional[int] = None        # 手牌索引
        self.hover_enemy: Optional[int] = None
        self.hover_relic: Optional[int] = None
        self.hover_end: bool = False
        self.hover_pile: Optional[str] = None
        self._layout: Dict[str, Any] = {}
        self._intent_hit: List[Tuple[float, float, float, dict]] = []

        # 动画状态
        self.shake = (0.0, 0.0)
        self.enemy_offsets: List[float] = []       # 每个敌人的抬升偏移
        self.hit_flash: Dict[int, float] = {}      # 敌人 idx -> 闪白剩余 ms
        self.dead_alpha: Dict[int, float] = {}     # 敌人 idx -> 淡出剩余 ms
        self.dying: set = set()
        self.float_hp: Dict[int, float] = {}       # 敌人 idx -> 血条残影值
        self.float_hp_player: Optional[float] = None
        self.unit_anim = 0.0
        self._recoil = 0.0
        self.enemy_anim = 0.0
        self.pending = False                       # 正在播放敌人回合
        self.card_pop: Dict[int, float] = {}       # 手牌 uid -> 打出动画剩余
        self.turn_banner = 0.0
        self.energy_flash = 0.0
        self.log_fade: List[Tuple[str, float]] = []
        self.busy_lock = False
        self.finished = False
        self._real = None          # core.cards 模块缓存（用于还原 CardInstance）
        self._drawer = _UNSET      # widgets.CardView.draw_on 缓存
        self._relic_draw = _UNSET  # 程序化勋章图标绘制器缓存

        self._bind()

    # ------------------------------------------------------------------ 生命周期
    def build(self, kwargs: Dict[str, Any]) -> None:
        self.kwargs = dict(kwargs or {})
        self.snap = self._fetch()
        self.w, self.h = self.app.W, self.app.H
        self._compute_layout()
        self._sync_pools()
        self.turn_banner = 1400.0
        self._start_loops()

    def on_destroy(self) -> None:
        self.app.cancel("battle_anim")
        self.app.cancel("enemy_turn")
        self.app.cancel("battle_check")
        try:
            self.c.delete("tooltip")
        except Exception:
            pass

    def on_resize(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self._compute_layout()

    def _start_loops(self) -> None:
        self.app.every("battle_anim", 33, self._anim_step)

    # ------------------------------------------------------------------ 数据
    def _fetch(self) -> Dict[str, Any]:
        b = self.app.battle
        if b is None:
            return {}
        fn = getattr(b, "snapshot", None)
        if not callable(fn):
            return {}
        try:
            snap = fn()
            return snap if isinstance(snap, dict) else {}
        except Exception:
            return {}

    def _sync_pools(self) -> None:
        """把 snapshot 的血量同步到血条残影，避免每帧抖动。"""
        p = self.snap.get("player") or {}
        hp = float(p.get("hp", 0) or 0)
        if self.float_hp_player is None:
            self.float_hp_player = hp
        for e in (self.snap.get("enemies") or []):
            idx = int(e.get("idx", 0) or 0)
            if idx not in self.float_hp:
                self.float_hp[idx] = float(e.get("hp", 0) or 0)

    # ------------------------------------------------------------------ 布局
    def _compute_layout(self) -> None:
        w, h = self.w, self.h
        # 玩家阵地（坦克 + 总部）
        self.unit_cx = w * 0.235
        self.unit_cy = h * 0.60
        self.unit_scale = min(w / 1440.0, h / 900.0) * 1.0
        # 敌人一排
        self.enemy_y = h * 0.40
        n = max(1, len(self.snap.get("enemies") or []))
        span = w * 0.50
        x0 = w * 0.40
        self.enemy_xs = [x0 + span * (i + 0.5) / n for i in range(n)]
        self.enemy_scale = min(w / 1440.0, h / 900.0)
        # 手牌
        self.hand_cx = w / 2.0 + 40
        self.hand_cy = h - HAND_BASE_Y_OFF - CARD_H / 2.0
        # 补给桶 / 牌堆 / 勋章 / 结束回合
        self.orb = (w * 0.085, h * 0.775)
        self.orb_r = 40
        self.end_btn = (w - 190, h - 152, w - 20, h - 84)
        self.piles = {
            "draw": (w * 0.075, h - 56),
            "discard": (w - 76, h - 56),
            "exhaust": (w - 268, h - 56),
        }
        self.relic_xy = (w * 0.055, h * 0.045)
        self._compute_hand_positions()

    def _hand_slots(self) -> List[dict]:
        return self._layout.get("hand", [])

    def _compute_hand_positions(self) -> None:
        hand = self.snap.get("hand") or []
        n = len(hand)
        slots: List[dict] = []
        if n == 0:
            self._layout["hand"] = slots
            return
        avail = self.w - 200.0
        gap = min(CARD_W + 8.0, avail / n)
        gap = max(46.0, gap)
        total = gap * (n - 1)
        over = self.hover_card
        for i in range(n):
            t = (i - (n - 1) / 2.0) / max(1.0, (n - 1) / 2.0) if n > 1 else 0.0
            x = self.hand_cx - total / 2.0 + gap * i
            y = self.hand_cy + (t * t) * HAND_ARC_H
            rot = t * HAND_MAX_ROT
            scale = 1.0
            lift = 0.0
            if over is not None and i == over:
                scale = HAND_SCALE_HOVER
                lift = 26.0
            elif over is not None:
                d = abs(i - over)
                if d == 1:
                    y += 8
                elif d == 2:
                    y += 4
            slots.append({"i": i, "x": x, "y": y - lift, "rot": rot,
                          "scale": scale, "w": CARD_W * scale,
                          "h": CARD_H * scale, "t": t})
        self._layout["hand"] = slots

    # ------------------------------------------------------------------ 输入
    def _bind(self) -> None:
        c = self.c
        c.bind("<Motion>", self._on_motion)
        c.bind("<Button-1>", self._on_click)
        c.bind("<Button-3>", self._on_right)
        c.bind("<Leave>", lambda e: self._clear_hover())
        c.bind("<MouseWheel>", self._on_wheel)

    def _clear_hover(self) -> None:
        self.hover_card = None
        self.hover_enemy = None
        self.hover_relic = None
        self.hover_end = False
        self.hover_pile = None
        self.app._hide_tooltip()
        self._compute_hand_positions()

    def _on_wheel(self, event) -> None:
        if (self.snap.get("phase") or "") == "player" and not self.pending:
            self.app.redraw()

    def _card_at(self, x: float, y: float) -> Optional[int]:
        """命中测试：从后往前（上层优先）。"""
        for s in reversed(self._hand_slots()):
            hw, hh = s["w"] / 2.0, s["h"] / 2.0
            if abs(x - s["x"]) <= hw and abs(y - s["y"]) <= hh:
                return int(s["i"])
        return None

    def _enemy_at(self, x: float, y: float) -> Optional[int]:
        for (cx, cy, r, e) in self._intent_hit:
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                return int(e.get("idx", 0) or 0)
        # 兜底：用粗略身体范围
        for i, e in enumerate(self.snap.get("enemies") or []):
            cx = self.enemy_xs[i] if i < len(self.enemy_xs) else self.w * 0.6
            cy = self.enemy_y
            if abs(x - cx) < 110 * self.enemy_scale and \
               abs(y - cy) < 130 * self.enemy_scale:
                return int(e.get("idx", i) or i)
        return None

    def _on_motion(self, event) -> None:
        x, y = event.x - self.shake[0], event.y - self.shake[1]
        prev_card, prev_enemy = self.hover_card, self.hover_enemy
        prev_relic, prev_end = self.hover_relic, self.hover_end

        self.hover_card = self._card_at(x, y)
        self.hover_enemy = self._enemy_at(x, y)
        bx1, by1, bx2, by2 = self.end_btn
        self.hover_end = bx1 <= x <= bx2 and by1 <= y <= by2
        self.hover_relic = None
        rx, ry = self.relic_xy
        if abs(y - ry) < 24:
            idx = int((x - rx) // 44)
            relics = self.snap.get("relics") or []
            if 0 <= idx < len(relics):
                self.hover_relic = idx
        self.hover_pile = None
        if (self.snap.get("phase") or "") == "player" and not self.pending:
            for name, (px, py) in self.piles.items():
                if (x - px) ** 2 + (y - py) ** 2 < 46 ** 2:
                    self.hover_pile = name

        if self.hover_card != prev_card:
            self._compute_hand_positions()
            self.app._hide_tooltip()
        if (self.hover_enemy != prev_enemy or self.hover_relic != prev_relic or
                self.hover_end != prev_end):
            self.app._hide_tooltip()

        # tooltip 延时 250ms
        if self.hover_card is not None:
            self.app.cancel("battle_tip")
            idx = self.hover_card
            self.app._jobs["battle_tip"] = self.app.after(
                250, lambda i=idx: self._tip_card(i))
        elif self.hover_relic is not None:
            self.app.cancel("battle_tip")
            idx = self.hover_relic
            self.app._jobs["battle_tip"] = self.app.after(
                250, lambda i=idx: self._tip_relic(i))
        elif self.hover_pile:
            name = self.hover_pile
            self.app.cancel("battle_tip")
            self.app._jobs["battle_tip"] = self.app.after(
                150, lambda n=name: self._tip_pile(n))

    def _tip_card(self, i: int) -> None:
        hand = self.snap.get("hand") or []
        if not (0 <= i < len(hand)):
            return
        cd = hand[i]
        slots = self._hand_slots()
        s = slots[i] if i < len(slots) else None
        col = self._rarity_color(cd.get("rarity", "common"))
        body = str(cd.get("text", "") or "")
        if cd.get("cost", 0) == -1:
            body = "X 费：消耗全部补给。\n" + body
        self.app.show_tooltip(
            body, (s["x"] if s else self.w / 2) - 150,
            (s["y"] - s["h"] / 2 - 10) if s else self.h / 2,
            title="%s%s   [%s]" % (cd.get("name", "?"),
                                   " +" if cd.get("upgraded") else "",
                                   self._cost_text(cd.get("cost", 0))),
            color=col, width=320)

    def _tip_relic(self, i: int) -> None:
        relics = self.snap.get("relics") or []
        if not (0 <= i < len(relics)):
            return
        r = relics[i]
        rx, ry = self.relic_xy
        reg = T.rarity_color(r.get("rarity", "common")) if hasattr(
            T, "rarity_color") else RARITY_COLORS.get(r.get("rarity"), GOLD)
        self.app.show_tooltip(str(r.get("text", "")), rx + i * 44 - 40, ry + 10,
                              title=str(r.get("name", "勋章")), color=reg,
                              width=300)

    def _tip_pile(self, name: str) -> None:
        n = {"draw": self._count("draw"), "discard": self._count("discard"),
             "exhaust": self._count("exhaust")}.get(name, 0)
        label = {"draw": "牌库", "discard": "弃牌堆",
                 "exhaust": "移除区"}.get(name, name)
        x, y = self.piles.get(name, (self.w / 2, self.h - 60))
        tip = {"draw": "回合开始时从牌库抽取 5 张手令。",
               "discard": "回合结束时手牌进入这里。",
               "exhaust": "被移除的牌（本场战斗不再出现）。"}.get(name, "")
        self.app.show_tooltip(tip, x - 120, y - 80,
                              title="%s · %d 张" % (label, n),
                              color=CYAN, width=260)

    def _on_right(self, event) -> None:
        if self.selected is not None:
            self.selected = None
            self.app.redraw()

    def _on_click(self, event) -> None:
        x, y = event.x - self.shake[0], event.y - self.shake[1]
        if (self.snap.get("phase") or "") != "player" or self.pending:
            return
        # 1) 结束回合
        bx1, by1, bx2, by2 = self.end_btn
        if bx1 <= x <= bx2 and by1 <= y <= by2:
            self._end_turn()
            return
        # 2) 手牌
        idx = self._card_at(x, y)
        if idx is not None:
            self._click_card(idx)
            return
        # 3) 点击敌人 = 对选中牌指定目标
        eidx = self._enemy_at(x, y)
        if eidx is not None and self.selected is not None:
            self._play(self.selected, eidx)
            return
        # 4) 牌堆 tooltip 已由 hover 处理；点空白取消选择
        if self.selected is not None:
            self.selected = None
            self.app.redraw()

    def _click_card(self, idx: int) -> None:
        hand = self.snap.get("hand") or []
        if not (0 <= idx < len(hand)):
            return
        cd = hand[idx]
        if not cd.get("playable", True):
            self.app.pop_text(self.hand_cx, self.h - 120, "无法打出",
                              color=BLOOD, size=18)
            self.app.flash(_alpha_on(BG_DEEP, BLOOD, 0.10), 90)
            return
        target_kind = self._target_kind(cd)
        if target_kind == "self" or target_kind == "none":
            self._play(idx, None)
            return
        # 需要目标
        if self.selected == idx:
            alive = [e for e in (self.snap.get("enemies") or [])
                     if e.get("alive", True)]
            if len(alive) == 1:
                self._play(idx, int(alive[0].get("idx", 0) or 0))
            else:
                self.selected = None
                self.app.redraw()
            return
        self.selected = idx
        self.app.redraw()

    def _play(self, idx: int, target: Optional[int]) -> None:
        hand = self.snap.get("hand") or []
        if not (0 <= idx < len(hand)):
            return
        cd = hand[idx]
        uid = cd.get("uid", idx)
        battle = self.app.battle
        ok = False
        fn = getattr(battle, "play_card", None)
        if callable(fn):
            tgt = None
            if target is not None:
                enemies = getattr(battle, "enemies", None) or []
                for e in enemies:
                    if int(getattr(e, "idx", -1) if hasattr(e, "idx") else -1) == int(target):
                        tgt = e
                        break
                if tgt is None:
                    # 用 idx 直接取
                    try:
                        tgt = (getattr(battle, "enemies", []) or [])[int(target)]
                    except Exception:
                        tgt = None
            try:
                ok = bool(fn(uid, tgt))
            except Exception:
                ok = False
        if not ok:
            self.app.pop_text(self.hand_cx, self.h - 120, "补给不足 / 目标非法",
                              color=BLOOD, size=17)
            self.app.flash(_alpha_on(BG_DEEP, BLOOD, 0.08), 90)
            self.selected = None
            self.app.redraw()
            return
        # 出牌成功：即时反馈
        self.selected = None
        self.card_pop[uid] = 240.0
        self.snap = self._fetch()
        self._compute_hand_positions()
        self._detect_events(prev_hand_len=len(hand))
        self.app.redraw()
        self.app.once(60, self._after_play)

    def _after_play(self) -> None:
        self.snap = self._fetch()
        self._compute_hand_positions()
        self._detect_events()
        self._check_end()
        self.app.redraw()

    def _end_turn(self) -> None:
        if self.pending or (self.snap.get("phase") or "") != "player":
            return
        battle = self.app.battle
        fn = getattr(battle, "end_turn", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
        self.selected = None
        self.pending = True
        self.snap = self._fetch()
        self._compute_hand_positions()
        self.app.redraw()
        self._schedule_enemy_step()

    # ------------------------------------------------------- 敌方回合（400ms）
    def _schedule_enemy_step(self) -> None:
        self.app.every("enemy_turn", self.app.scaled(ENEMY_STEP_MS),
                       self._enemy_step, run_now=False)

    def _enemy_step(self) -> None:
        if self.finished:
            return
        battle = self.app.battle
        fn = getattr(battle, "enemy_step", None)
        more = False
        if callable(fn):
            try:
                more = bool(fn())
            except Exception:
                more = False
        else:
            more = False
        self.snap = self._fetch()
        self._detect_events(animate=True)
        self.app.redraw()
        if not more:
            self.app.cancel("enemy_turn")
            self.pending = False
            self.snap = self._fetch()
            self._compute_hand_positions()
            self._sync_pools()
            self.turn_banner = 900.0
            self.app.redraw()
            self._check_end()

    # ------------------------------------------------------------ 事件检测
    def _detect_events(self, prev_hand_len: Optional[int] = None,
                       animate: bool = True) -> None:
        """对比 snapshot 变化，触发飘字 / 震屏 / 闪白 / 死亡淡出。"""
        # 玩家掉血
        p = self.snap.get("player") or {}
        php = float(p.get("hp", 0) or 0)
        if self.float_hp_player is None:
            self.float_hp_player = php
        if php < self.float_hp_player - 0.01:
            dmg = self.float_hp_player - php
            self.app.pop_number(self.unit_cx + 40, self.unit_cy - 90,
                                "-%d" % int(round(dmg)), color=BLOOD, size=30)
            self.app.shake(13 if animate else 6, 280)
            self.app.flash(_alpha_on(BG_DEEP, "#FFFFFF", 0.22), 140)
        elif php > self.float_hp_player + 0.01:
            heal = php - self.float_hp_player
            self.app.pop_number(self.unit_cx + 40, self.unit_cy - 90,
                                "+%d" % int(round(heal)), color="#5FD07A", size=26)
        self.float_hp_player = php

        for i, e in enumerate(self.snap.get("enemies") or []):
            idx = int(e.get("idx", i) or i)
            hp = float(e.get("hp", 0) or 0)
            prev = self.float_hp.get(idx)
            alive = bool(e.get("alive", True))
            cx = self.enemy_xs[i] if i < len(self.enemy_xs) else self.w * 0.6
            cy = self.enemy_y
            if prev is None:
                self.float_hp[idx] = hp
            else:
                if hp < prev - 0.01 and animate:
                    dmg = prev - hp
                    self.app.pop_number(cx + 14, cy - 70, "-%d" % int(round(dmg)),
                                        color=GOLD if dmg < 10 else "#FF9B4A",
                                        size=30)
                    self.hit_flash[idx] = 180.0
                    self.app.shake(8, 200)
                elif hp > prev + 0.01 and animate:
                    self.app.pop_number(cx + 14, cy - 70,
                                        "+%d" % int(round(hp - prev)),
                                        color="#5FD07A", size=24)
                self.float_hp[idx] = hp
            if not alive and idx not in self.dying:
                self.dying.add(idx)
                self.dead_alpha[idx] = 520.0
                if animate:
                    self.app.pop_text(cx, cy - 10, "击破！", color=CYAN, size=26)
                    self.app.shake(10, 260)

        if prev_hand_len is not None and len(self.snap.get("hand") or []) > prev_hand_len:
            self.app.pop_text(self.hand_cx, self.hand_cy - 120, "补给手令",
                              color=CYAN, size=16, life=600)

    def set_shake(self, dx: float, dy: float) -> None:
        self.shake = (dx, dy)

    # ------------------------------------------------------------------ 动画
    def _anim_step(self) -> None:
        dt = 33.0
        self.unit_anim += 0.055
        if self._recoil > 0:
            self._recoil = max(0.0, self._recoil - 0.06)
        self.enemy_anim += 0.04
        if self.turn_banner > 0:
            self.turn_banner -= dt
        if self.energy_flash > 0:
            self.energy_flash -= dt
        for k in list(self.hit_flash):
            self.hit_flash[k] -= dt
            if self.hit_flash[k] <= 0:
                del self.hit_flash[k]
        for k in list(self.dead_alpha):
            self.dead_alpha[k] -= dt
        for k in list(self.card_pop):
            self.card_pop[k] -= dt
            if self.card_pop[k] <= 0:
                del self.card_pop[k]
        # 血条残影缓动
        for i, e in enumerate(self.snap.get("enemies") or []):
            idx = int(e.get("idx", i) or i)
            hp = float(e.get("hp", 0) or 0)
            prev = self.float_hp.get(idx, hp)
            if prev > hp:
                self.float_hp[idx] = max(hp, prev - max(0.6, prev * 0.06))
        p = self.snap.get("player") or {}
        if self.float_hp_player is not None:
            php = float(p.get("hp", 0) or 0)
            if self.float_hp_player > php:
                self.float_hp_player = max(php, self.float_hp_player -
                                           max(0.6, self.float_hp_player * 0.05))
        # 日志淡出
        self.log_fade = [(t, l - dt) for (t, l) in self.log_fade if l - dt > 0]
        if self.pending:
            self.app.redraw()
        elif self.turn_banner > 0 or self.card_pop or self.hit_flash:
            self.app.redraw()

    def _check_end(self) -> None:
        if self.finished:
            return
        battle = self.app.battle
        res = "ongoing"
        fn = getattr(battle, "result", None)
        if callable(fn):
            try:
                res = str(fn())
            except Exception:
                res = "ongoing"
        if res == "ongoing":
            res = str(self.snap.get("phase") or "ongoing")
        if res in ("won", "lost"):
            self.finished = True
            self.app.cancel("enemy_turn")
            self.app.cancel("battle_anim")
            self.app.once(700, lambda r=res: self._finish(r))

    def _finish(self, result: str) -> None:
        run = self.app.run
        fn = getattr(run, "finish_battle", None) if run else None
        if callable(fn):
            try:
                fn(result, self.app.battle)
            except Exception:
                pass
        if result == "won":
            self.app.show("reward")
        else:
            self.app.show("gameover", result="lost")

    # ================================================================== 绘制
    def draw(self) -> None:
        c = self.c
        c.delete("all")
        if not self.snap:
            self.snap = self._fetch()
        sx, sy = self.shake
        tag = "shake"
        self._draw_background(tag)
        self._draw_light_rays(tag)
        self._draw_seabed(tag)
        self._draw_player_forces(sx, sy)
        self._draw_enemies(sx, sy)
        self._draw_player_status(sx, sy)
        self._draw_relics(sx, sy)
        self._draw_energy(sx, sy)
        self._draw_piles(sx, sy)
        self._draw_end_turn(sx, sy)
        self._draw_turn_banner()
        self._draw_log()
        self._draw_hand(sx, sy)
        self.app.draw_damage_numbers("dmg")
        self._draw_selection_hint(sx, sy)

    # ---------------------------------------------------------------- 背景
    def _draw_background(self, tag: str) -> None:
        """焦土战场：地平线渐变 + 远景废墟 + 硝烟粒子 + 曳光弹 + 铁丝网剪影。"""
        w, h = self.w, self.h
        A.battlefield(self.c, w, h, tag, horizon=0.56)
        A.horizon_glow(self.c, w, h, tag, self.app._tick * 0.03)
        # 硝烟粒子
        t = self.app._tick
        for s in self.app._bg_sprites:
            wob = math.sin(math.radians((t * 2 + s["phase"]) % 360))
            bx = s["x"] + wob * 6
            by = s["y"]
            r = s["r"] * 1.5
            tt = max(0.05, min(1.0, 1.0 - (by / float(max(1, h)))))
            col = A.lerp(SMOKE, "#8A7F6B", 0.25 + 0.5 * tt)
            A.draw_smoke_cloud(self.c, bx, by, r, col, tag)
        # 曳光弹（间歇扫过）
        for i in range(3):
            ph = (t * 2.2 + i * 67) % 180
            if ph > 46:
                continue
            k = ph / 46.0
            x1 = w * (0.12 + 0.3 * i) + k * w * 0.6
            y1 = h * 0.62
            A.tracer(self.c, x1, y1, x1 + 90, y1 - 34, "#FFD27A", tag)
        # 前景工事
        A.barbed_wire(self.c, -20, h - 34, w * 0.34, h - 22, tag, posts=5)
        A.barbed_wire(self.c, w * 0.66, h - 22, w + 20, h - 34, tag, posts=5)
        A.crater(self.c, w * 0.16, h * 0.82, 46 * self.unit_scale, tag)
        A.crater(self.c, w * 0.86, h * 0.88, 34 * self.unit_scale, tag)
        A.hedgehog(self.c, w * 0.47, h * 0.86, 0.9 * self.unit_scale, tag)

    def _draw_light_rays(self, tag: str) -> None:
        """远处炮击火光 + 探照灯光柱（原海底光柱）。"""
        w, h = self.w, self.h
        t = self.app._tick * 0.3
        for i in range(3):
            x0 = w * (0.24 + 0.26 * i) + math.sin(math.radians(t + i * 61)) * 40
            spread = 46 + i * 18
            hot = 0.5 + 0.5 * math.sin(math.radians(t * 1.7 + i * 120))
            col = A.alpha_on(BG_DEEP, "#FF9B4A", 0.020 + 0.022 * hot)
            self.c.create_polygon(x0 - 10, h * 0.56, x0 + 10, h * 0.56,
                                  x0 + spread, -10, x0 - spread, -10,
                                  fill=col, outline="", tags=tag)
        for i in range(2):
            x0 = w * (0.18 + 0.62 * i)
            sway = math.sin(math.radians(t * 0.8 + i * 140)) * 90
            col = A.alpha_on(BG_DEEP, "#FFE7A8", 0.030)
            self.c.create_polygon(x0, h * 0.56, x0 + 14, h * 0.56,
                                  x0 + sway + 70, -10, x0 + sway - 70, -10,
                                  fill=col, outline="", tags=tag)

    def _draw_seabed(self, tag: str) -> None:
        """战壕线与沙袋工事（原海床剪影）。"""
        w, h = self.w, self.h
        base = h - 74
        pts: List[float] = []
        for i in range(0, 41):
            x = w * i / 40.0
            y = base + math.sin(i * 0.55) * 9 + math.sin(i * 0.21 + 1.2) * 6
            pts.extend((x, y))
        pts.extend((w, h, 0, h))
        self.c.create_polygon(pts, fill="#0D0B08", outline="", tags=tag)
        for kx in (0.08, 0.30, 0.62, 0.86):
            A.sandbags(self.c, w * kx, base + 8, 3, 0.9 * self.unit_scale, tag)
        for kx in (0.18, 0.44, 0.74, 0.94):
            cx = w * kx
            self.c.create_line(cx, base + 4, cx + 4, base - 30,
                               fill="#2E2519", width=4, tags=tag)

    def _fish_silhouette(self, x: float, y: float, size: float, col: str,
                         tag: str) -> None:
        """远景飞机剪影（原鱼群）。"""
        A.enemy_plane(self.c, x, y, size * 0.42, col, tag)

    # ------------------------------------------------------- 玩家装甲单位
    def _draw_player_forces(self, sx: float, sy: float) -> None:
        """玩家阵地：主战坦克 + 总部碉堡。"""
        c = self.c
        cx = self.unit_cx + sx
        cy = self.unit_cy + sy + math.sin(self.unit_anim) * 5
        s = self.unit_scale
        tag = "unit"

        p = self.snap.get("player") or {}
        hp = float(p.get("hp", 1) or 1)
        maxhp = max(1.0, float(p.get("max_hp", 1) or 1))
        ratio = max(0.0, min(1.0, hp / maxhp))

        halo = A.alpha_on(BG_DEEP, CYAN,
                          0.05 + 0.04 * math.sin(self.unit_anim * 0.8))
        c.create_oval(cx - 210 * s, cy + 60 * s, cx + 210 * s, cy + 170 * s,
                      fill=halo, outline="", tags=tag)

        col = OLIVE if ratio > 0.3 else A.lerp(OLIVE, BLOOD, 0.4)
        A.hq(c, cx - 118 * s, cy - 6 * s, s * 0.82,
             col="#6E6A5E" if ratio > 0.25 else A.lerp("#6E6A5E", BLOOD, 0.3),
             tag=tag, hp_ratio=ratio, flag_phase=self.unit_anim * 1.5)
        recoil = getattr(self, "_recoil", 0.0)
        A.tank(c, cx + 62 * s - recoil * 6 * s, cy + 44 * s, s * 0.95, col=col,
               facing=1, tag=tag, turret_angle=-6.0,
               tread_phase=self.unit_anim * 2.0)
        if recoil > 0.02:
            mx = cx + 62 * s + 74 * 0.95 * s
            my = cy + 44 * s - 6 * s
            A.draw_smoke_cloud(self.c, mx, my, 16 * s * (1 + recoil),
                               "#8A7F6B", tag)

        name = str(p.get("name") or "总部")
        self.app.text_shadow(cx, cy + 148 * s, name, font=T.FONT_H2,
                             fill=TEXT, tags=tag)

    # -------------------------------------------------------- 敌方装甲单位
    def _draw_enemies(self, sx: float, sy: float) -> None:
        self._intent_hit = []
        for i, e in enumerate(self.snap.get("enemies") or []):
            self._draw_enemy(i, e, sx, sy)

    def _draw_enemy(self, i: int, e: dict, sx: float, sy: float) -> None:
        c = self.c
        idx = int(e.get("idx", i) or i)
        alive = bool(e.get("alive", True))
        cx = (self.enemy_xs[i] if i < len(self.enemy_xs) else self.w * 0.6) + sx
        cy = self.enemy_y + sy
        s = self.enemy_scale
        if not alive:
            fade = self.dead_alpha.get(idx, 0.0)
            if idx in self.dying and fade <= 0:
                self._draw_wreck(cx, cy, s)
            elif fade > 0.02 or idx not in self.dying:
                self._draw_wreck(cx, cy, s, fade=min(1.0, fade / 520.0)
                                 if idx in self.dying else 0.6)
            return

        col = self._enemy_color(e)
        cy += math.sin(self.enemy_anim + i * 1.1) * 4 * s
        if self.hover_enemy == idx:
            glow = A.alpha_on(BG_DEEP,
                              BLOOD if idx == self.selected else CYAN, 0.20)
            c.create_oval(cx - 116 * s, cy - 116 * s, cx + 116 * s,
                          cy + 116 * s, fill=glow, outline="", tags="enemy")
        art = str(e.get("art") or "") or A.unit_art_for(
            str(e.get("name", "")), str(e.get("id", "")), i)
        A.draw_enemy_unit(c, cx, cy, 78 * s, col, art, "enemy")
        fl = self.hit_flash.get(idx, 0.0)
        if fl > 0:
            a = min(0.75, fl / 180.0)
            c.create_oval(cx - 92 * s, cy - 92 * s, cx + 92 * s, cy + 92 * s,
                          fill=A.alpha_on(BG_DEEP, "#FFFFFF", a * 0.35),
                          outline="", tags="enemy")
        self.app.text_shadow(cx, cy - 118 * s, str(e.get("name", "?")),
                             font=T.FONT_BODY, fill=TEXT, tags="enemy")
        self._draw_intent(cx, cy - 152 * s, e, s)
        self._draw_enemy_hp(cx, cy + 104 * s, e, s)
        self._draw_buffs(cx, cy + 134 * s, e.get("buffs") or {}, s, "enemy")

    def _draw_wreck(self, cx: float, cy: float, s: float,
                    fade: float = 1.0) -> None:
        """被击毁的敌方载具残骸 + 余烬黑烟。"""
        c = self.c
        a = max(0.15, min(1.0, fade))
        c.create_oval(cx - 84 * s, cy - 34 * s, cx + 84 * s, cy + 40 * s,
                      fill=A.alpha_on(BG_DEEP, "#171310", 0.85 * a),
                      outline="", tags="enemy")
        c.create_line(cx - 70 * s, cy - 30 * s, cx + 70 * s, cy + 26 * s,
                      fill=A.alpha_on(BG_DEEP, "#3A3428", 0.9 * a), width=5,
                      tags="enemy")
        c.create_line(cx - 60 * s, cy + 22 * s, cx + 66 * s, cy - 24 * s,
                      fill=A.alpha_on(BG_DEEP, "#3A3428", 0.9 * a), width=4,
                      tags="enemy")
        t = self.app._tick
        for k in range(5):
            tt = ((t * 1.4 + k * 43) % 140) / 140.0
            rr = (3 + 7 * tt) * s
            px = cx + math.sin(k * 2.1 + t * 0.1) * (16 + 30 * tt) * s
            py = cy - 10 * s - 60 * tt * s
            col = A.lerp("#FF9B4A", "#3A3428", tt)
            c.create_oval(px - rr, py - rr, px + rr, py + rr,
                          fill=A.alpha_on(BG_DEEP, col,
                                          max(0.0, 0.7 * (1 - tt) * a)),
                          outline="", tags="enemy")
        A.draw_smoke_cloud(c, cx, cy - 20 * s, 42 * s, "#4A4238", "enemy")

    def _guess_art(self, i: int, e: dict) -> str:
        return A.unit_art_for(str(e.get("name", "")), str(e.get("id", "")), i)

    def _enemy_color(self, e: dict) -> str:
        """敌方配色：钢灰 / 铁锈 / 深军绿（按名字稳定取色）。"""
        n = str(e.get("name", ""))
        seed = sum(ord(ch) for ch in n) if n else 7
        palettes = ["#5A6470", "#6B5540", "#4F5A42", "#6E5A4A", "#59606B",
                    "#7A6448", "#4A5A55", "#6A5A5E"]
        return palettes[seed % len(palettes)]

    def _draw_intent(self, cx: float, cy: float, e: dict, s: float) -> None:
        intent = e.get("intent") or {}
        if not intent:
            return
        c = self.c
        kind = str(intent.get("intent", "unknown"))
        col = INTENT_COLORS.get(kind, TEXT_DIM) if isinstance(INTENT_COLORS, dict) \
            else TEXT_DIM
        pulse = 1.0 + 0.06 * math.sin(self.app._tick * 0.12)
        r = 25 * s * pulse
        # 牌底
        self.c.create_oval(cx - r, cy - r, cx + r, cy + r,
                           fill=_alpha_on(BG_DEEP, PANEL, 0.92),
                           outline=col, width=2, tags="enemy")
        self._intent_icon(cx, cy, r * 0.62, kind, col)
        # 伤害数字
        dmg = int(intent.get("damage", 0) or 0)
        hits = int(intent.get("hits", 1) or 1)
        blk = int(intent.get("block", 0) or 0)
        label = ""
        if dmg > 0 and hits > 1:
            label = "%d×%d" % (dmg, hits)
        elif dmg > 0:
            label = str(dmg)
        elif blk > 0:
            label = str(blk)
        if label:
            self.app.text_shadow(cx, cy + r + 14 * s, label, font=T.FONT_NUM,
                                 fill=col, tags="enemy")
        # 命中范围（用于点击选中目标）
        self._intent_hit.append((cx, cy, max(r, 40 * s), e))
        # 悬停时显示招式名
        if self.hover_enemy == int(e.get("idx", -1) or -1):
            nm = str(intent.get("name") or "")
            txt = str(intent.get("text") or "")
            body = nm + ("\n" + txt if txt else "")
            self.app.show_tooltip(body, cx - 130, cy - r - 6,
                                  title=self._intent_title(kind), color=col,
                                  width=270)

    def _intent_title(self, kind: str) -> str:
        return {"attack": "攻击意图", "attack_debuff": "攻击 + 减益",
                "attack_defend": "攻击 + 防御", "defend": "防御意图",
                "buff": "强化意图", "debuff": "削弱意图",
                "sleep": "沉睡", "unknown": "未知意图"}.get(kind, "意图")

    def _intent_icon(self, cx: float, cy: float, r: float, kind: str,
                     col: str) -> None:
        c = self.c
        if kind.startswith("attack"):
            # 剑 / 爪
            c.create_polygon(cx, cy - r, cx + r * 0.22, cy - r * 0.2,
                             cx + r * 0.9, cy + r * 0.7, cx + r * 0.35,
                             cy + r * 0.9, cx - r * 0.2, cy - r * 0.1,
                             fill=col, outline="", tags="enemy")
            c.create_line(cx - r * 0.9, cy + r * 0.2, cx - r * 0.1, cy + r * 0.98,
                          fill=_shade(col, -0.25), width=4, tags="enemy")
            if kind == "attack_debuff":
                c.create_oval(cx - r * 1.35, cy - r * 1.3, cx - r * 0.6,
                              cy - r * 0.55, fill="#B07BE8", outline="", tags="enemy")
            elif kind == "attack_defend":
                c.create_polygon(cx + r * 0.55, cy - r * 1.3, cx + r * 1.35,
                                 cy - r * 0.95, cx + r * 0.95, cy - r * 0.4,
                                 cx + r * 0.55, cy - r * 0.75, fill=BLOCK_BLUE,
                                 outline="", tags="enemy")
        elif kind == "defend":
            c.create_polygon(cx, cy - r * 1.1, cx + r * 0.95, cy - r * 0.6,
                             cx + r * 0.95, cy + r * 0.35, cx, cy + r * 1.1,
                             cx - r * 0.95, cy + r * 0.35, cx - r * 0.95,
                             cy - r * 0.6, fill=col, outline="",
                             smooth=False, tags="enemy")
            c.create_line(cx, cy - r * 0.7, cx, cy + r * 0.7, fill="#FFFFFF",
                          width=2, tags="enemy")
        elif kind == "buff":
            for i in range(6):
                a = math.pi * 2 * i / 6.0
                c.create_line(cx, cy, cx + math.cos(a) * r * 1.05,
                              cy + math.sin(a) * r * 1.05, fill=col, width=4,
                              tags="enemy")
            c.create_oval(cx - r * 0.34, cy - r * 0.34, cx + r * 0.34,
                          cy + r * 0.34, fill=col, outline="", tags="enemy")
        elif kind == "debuff":
            c.create_polygon(cx, cy - r * 1.05, cx + r * 1.05, cy,
                             cx, cy + r * 1.05, cx - r * 1.05, cy,
                             fill=col, outline="", tags="enemy")
            c.create_line(cx - r * 0.5, cy + r * 0.5, cx + r * 0.5,
                          cy - r * 0.5, fill="#FFFFFF", width=3, tags="enemy")
        elif kind == "sleep":
            fc = T.FONT_NUM
            c.create_text(cx, cy, text="Z", font=fc, fill=col, tags="enemy")
        else:
            c.create_text(cx, cy, text="?", font=T.FONT_NUM, fill=col,
                          tags="enemy")

    def _draw_enemy_hp(self, cx: float, cy: float, e: dict, s: float) -> None:
        c = self.c
        w = int(200 * s)
        h = int(18 * s)
        x1, y1 = cx - w / 2, cy
        x2, y2 = cx + w / 2, cy + h
        self.app.round_rect(x1 - 2, y1 - 2, x2 + 2, y2 + 2, h / 2 + 2,
                            fill="#071019", outline=BORDER, width=1, tags="enemy")
        hp = max(0.0, float(e.get("hp", 0) or 0))
        maxhp = max(1.0, float(e.get("max_hp", 1) or 1))
        ratio = max(0.0, min(1.0, hp / maxhp))
        ghost = max(ratio, min(1.0, self.float_hp.get(
            int(e.get("idx", 0) or 0), hp) / maxhp))
        if ghost > ratio:
            self.app.round_rect(x1, y1, x1 + w * ghost, y2, h / 2,
                                fill="#F2F4F7", outline="", tags="enemy")
        col = HP_RED if ratio > 0.5 else (GOLD if ratio > 0.25 else BLOOD)
        if ratio > 0:
            self.app.round_rect(x1, y1, x1 + w * ratio, y2, h / 2, fill=col,
                                outline="", tags="enemy")
        self.app.round_rect(x1, y1, x2, y2, h / 2, fill="", outline=BORDER_HI,
                            width=1, tags="enemy")
        self.app.text_shadow(cx, cy + h / 2, "%d/%d" % (int(hp), int(maxhp)),
                             font=T.FONT_TINY, fill="#FFFFFF", tags="enemy")
        blk = int(e.get("block", 0) or 0)
        if blk > 0:
            by = cy - 26 * s
            c.create_oval(cx - 24 * s - 12, by - 12, cx - 24 * s + 12, by + 12,
                          fill=_alpha_on(BG_DEEP, BLOCK_BLUE, 0.9), outline="",
                          tags="enemy")
            self.app.text_shadow(cx - 24 * s, by, str(blk), font=T.FONT_TINY,
                                 fill="#08222E", tags="enemy")

    def _draw_buffs(self, cx: float, cy: float, buffs: dict, s: float,
                    tag: str) -> None:
        if not buffs:
            return
        items = [(k, v) for k, v in buffs.items() if v]
        if not items:
            return
        size = max(18, int(24 * s))
        gap = size + 6
        total = gap * len(items)
        x = cx - total / 2 + gap / 2
        for k, v in items[:10]:
            col = BUFF_COLORS.get(k, TEXT_DIM) if isinstance(BUFF_COLORS, dict) \
                else TEXT_DIM
            self.c.create_oval(x - size / 2, cy - size / 2, x + size / 2,
                               cy + size / 2,
                               fill=_alpha_on(BG_DEEP, col, 0.85), outline="",
                               tags=tag)
            self.app.text_shadow(x, cy, str(v), font=T.FONT_TINY,
                                 fill="#0A1620", tags=tag)
            x += gap

    # ------------------------------------------------------- 玩家状态 / HUD
    def _draw_player_status(self, sx: float, sy: float) -> None:
        p = self.snap.get("player") or {}
        cx = self.unit_cx + sx
        cy = self.unit_cy + sy + 168 * self.unit_scale
        w = int(260 * self.unit_scale)
        h = int(22 * self.unit_scale)
        x1, y1 = cx - w / 2, cy
        x2, y2 = cx + w / 2, cy + h
        self.app.round_rect(x1 - 3, y1 - 3, x2 + 3, y2 + 3, h / 2 + 3,
                            fill="#071019", outline=BORDER, width=1)
        hp = max(0.0, float(p.get("hp", 0) or 0))
        maxhp = max(1.0, float(p.get("max_hp", 1) or 1))
        ratio = max(0.0, min(1.0, hp / maxhp))
        ghost = max(ratio, min(1.0, (self.float_hp_player or hp) / maxhp))
        if ghost > ratio:
            self.app.round_rect(x1, y1, x1 + w * ghost, y2, h / 2,
                                fill="#F2F4F7", outline="")
        col = HP_RED if ratio > 0.5 else (GOLD if ratio > 0.25 else BLOOD)
        if ratio > 0:
            self.app.round_rect(x1, y1, x1 + w * ratio, y2, h / 2, fill=col,
                                outline="")
        for i in range(1, 5):
            gx = x1 + w * i / 5.0
            self.c.create_line(gx, y1 + 2, gx, y2 - 2,
                               fill=_alpha_on(col, "#000000", 0.35))
        self.app.round_rect(x1, y1, x2, y2, h / 2, fill="", outline=BORDER_HI,
                            width=1)
        self.app.text_shadow(cx, cy + h / 2, "%d / %d" % (int(hp), int(maxhp)),
                             font=T.FONT_NUM, fill="#FFFFFF")
        blk = int(p.get("block", 0) or 0)
        if blk > 0:
            self._shield(cx - w / 2 - 26, cy + h / 2, str(blk))
        self._draw_buffs(cx, cy + h + 22, p.get("buffs") or {},
                         self.unit_scale, "player")
        self._draw_minions(cx, cy + h + 54, p.get("minions") or [],
                           self.unit_scale)

    def _shield(self, cx: float, cy: float, text: str) -> None:
        """掩体值：钢制盾牌徽记。"""
        c = self.c
        A.icon_shield(c, cx, cy, 19, _alpha_on(BG_DEEP, BLOCK_BLUE, 0.95),
                      "unit")
        c.create_polygon(cx, cy - 18, cx + 16, cy - 10, cx + 16, cy + 6, cx,
                         cy + 18, cx - 16, cy + 6, cx - 16, cy - 10,
                         fill="", outline=_shade(BLOCK_BLUE, -0.3), width=2,
                         tags="unit")
        self.app.text_shadow(cx, cy, text, font=T.FONT_TINY, fill="#0E1418")

    def _draw_minions(self, cx: float, cy: float, minions: List[dict],
                      s: float) -> None:
        if not minions:
            return
        gap = 118 * s
        x = cx - gap * (len(minions) - 1) / 2
        for m in minions:
            hp = max(0.0, float(m.get("hp", 0) or 0))
            maxhp = max(1.0, float(m.get("max_hp", 1) or 1))
            ratio = max(0.0, min(1.0, hp / maxhp))
            self.app.round_rect(x - 44 * s, cy - 22 * s, x + 44 * s,
                                cy + 4 * s, 10,
                                fill=_alpha_on(BG_DEEP, PANEL, 0.85),
                                outline=BORDER_HI, width=1)
            self.app.round_rect(x - 42 * s, cy - 8 * s, x + 42 * s, cy,
                                6, fill="#071019", outline="")
            if ratio > 0:
                self.app.round_rect(x - 42 * s, cy - 8 * s,
                                    x - 42 * s + 84 * s * ratio, cy, 6,
                                    fill=CYAN, outline="")
            self.app.text_shadow(x, cy - 14 * s, str(m.get("name", "附属单位")),
                                 font=T.FONT_TINY, fill=TEXT)
            self.app.text_shadow(x + 58 * s, cy - 4 * s,
                                 "⚔%d" % int(m.get("attack", 0) or 0),
                                 font=T.FONT_TINY, fill=GOLD)
            x += gap

    def _relic_drawer(self):
        """取 widgets 里程序化勋章图标的绘制函数（若有）。"""
        if self._relic_draw is _UNSET:
            fn = None
            try:
                from .widgets import RelicView
                for name in ("draw_on", "draw_icon", "paint"):
                    cand = getattr(RelicView, name, None)
                    if callable(cand):
                        fn = cand
                        break
            except Exception:
                fn = None
            self._relic_draw = fn
        return self._relic_draw

    def _draw_relics(self, sx: float, sy: float) -> None:
        relics = self.snap.get("relics") or []
        rx, ry = self.relic_xy
        rx += sx
        ry += sy
        size = 34
        self.app.round_rect(rx - 14, ry - 22,
                            rx + max(1, len(relics)) * 44 + 6, ry + 22, 10,
                            fill=_alpha_on(BG_DEEP, PANEL, 0.55), outline=BORDER,
                            width=1)
        drawer = self._relic_drawer()
        for i, r in enumerate(relics):
            x = rx + i * 44 + 8
            hot = (self.hover_relic == i)
            col = GOLD if not hot else _shade(GOLD, 0.3)
            drawn = False
            if drawer is not None:
                # 优先用 RelicView 的形状引擎，保证与其它界面视觉一致
                defn = self._relic_def(r)
                if defn is not None:
                    for args, kwargs in (((self.c, x, ry, size), {}),
                                         ((self.c, x, ry, defn), {})):
                        try:
                            drawer(*args, **kwargs)
                            drawn = True
                            break
                        except Exception:
                            continue
            if not drawn:
                self.c.create_oval(x - size / 2, ry - size / 2, x + size / 2,
                                   ry + size / 2,
                                   fill=_alpha_on(BG_DEEP, col,
                                                  0.9 if hot else 0.65),
                                   outline=_shade(col, -0.3), width=2)
                self.c.create_oval(x - size / 2 + 5, ry - size / 2 + 5,
                                   x + size / 2 - 5, ry + size / 2 - 5,
                                   fill="", outline=_shade(col, 0.4), width=1)
            cnt = int(r.get("counter", -1) or -1)
            if cnt >= 0:
                self.app.text_shadow(x + 11, ry + 11, str(cnt),
                                     font=T.FONT_TINY, fill=TEXT)

    def _relic_def(self, r: dict):
        """snapshot 里的勋章 dict -> core 的 RelicDef（供 widgets 使用）。"""
        if not isinstance(r, dict):
            return None
        if self._real is None:
            try:
                from core import cards as C
                self._real = C
            except Exception:
                self._real = False
        try:
            from core import relics as R
        except Exception:
            return None
        db = getattr(R, "RELIC_DB", None)
        if isinstance(db, dict):
            return db.get(r.get("id"))
        return None

    def _draw_energy(self, sx: float, sy: float) -> None:
        """补给桶：弹药箱造型 + 剩余补给刻度。"""
        p = self.snap.get("player") or {}
        cx, cy = self.orb
        cx += sx
        cy += sy
        r = self.orb_r
        cur = int(p.get("energy", 0) or 0)
        mx = max(1, int(p.get("max_energy", 3) or 3))
        ratio = max(0.0, min(1.0, cur / float(mx)))
        # 外圈刻度
        for i in range(mx):
            a0 = -90 + 360.0 * i / mx + 4
            a1 = -90 + 360.0 * (i + 1) / mx - 4
            col = ENERGY_YELLOW if i < cur else "#2A3A46"
            self.c.create_arc(cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10,
                              start=a0, extent=a1 - a0, style="arc", outline=col,
                              width=5)
        # 球体
        self.c.create_oval(cx - r, cy - r, cx + r, cy + r,
                           fill=_alpha_on(BG_DEEP, "#123044", 0.95),
                           outline=BORDER_HI, width=2)
        if ratio > 0:
            rr = r * (0.35 + 0.6 * ratio)
            for i in range(9):
                t = i / 8.0
                self.c.create_oval(cx - rr + rr * 0.35 * t, cy - rr + rr * 0.9 * t,
                                   cx + rr - rr * 0.35 * t, cy + rr - rr * 0.1 * t,
                                   fill=_lerp(_shade(ENERGY_YELLOW, -0.35),
                                              "#FFF6C4", t), outline="")
        # 高光
        self.c.create_oval(cx - r * 0.55, cy - r * 0.68, cx - r * 0.05,
                           cy - r * 0.28, fill=_alpha_on(BG_DEEP, "#FFFFFF", 0.35),
                           outline="")
        self.app.text_shadow(cx, cy, "%d/%d" % (cur, mx), font=T.FONT_NUM_BIG,
                             fill="#3A2A00" if ratio > 0.4 else TEXT)
        self.app.text_shadow(cx, cy + r + 26, "补给", font=T.FONT_TINY,
                             fill=TEXT_DIM)

    def _count(self, which: str) -> int:
        key = {"draw": "draw_count", "discard": "discard_count",
               "exhaust": "exhaust_count"}[which]
        v = self.snap.get(key)
        if v is None:
            v = self.snap.get(key.replace("_count", "_pile_len"))
        try:
            return int(v or 0)
        except Exception:
            return 0

    def _draw_piles(self, sx: float, sy: float) -> None:
        info = (("draw", "牌库", CYAN), ("exhaust", "移除区", RUST),
                ("discard", "弃牌堆", GOLD))
        for which, label, col in info:
            px, py = self.piles[which]
            px += sx
            py += sy
            n = self._count(which)
            hot = (self.hover_pile == which)
            # 牌堆叠层
            for k in (3, 2, 1):
                self.app.round_rect(px - 34 + k * 2, py - 44 - k * 3,
                                    px + 34 + k * 2, py + 14 - k * 3, 7,
                                    fill=_alpha_on(BG_DEEP, PANEL, 0.75),
                                    outline=_alpha_on(BG_DEEP, col, 0.35),
                                    width=1)
            self.app.round_rect(px - 34, py - 44, px + 34, py + 14, 7,
                                fill=_alpha_on(BG_DEEP, PANEL, 0.96),
                                outline=_shade(col, 0.15 if hot else -0.2),
                                width=2)
            self.app.text_shadow(px, py - 15, str(n), font=T.FONT_NUM_BIG,
                                 fill=col)
            self.app.text_shadow(px, py + 30, label, font=T.FONT_TINY,
                                 fill=TEXT if hot else TEXT_DIM)

    def _draw_end_turn(self, sx: float, sy: float) -> None:
        x1, y1, x2, y2 = self.end_btn
        x1 += sx
        x2 += sx
        y1 += sy
        y2 += sy
        phase = str(self.snap.get("phase") or "player")
        enabled = (phase == "player") and not self.pending
        if not enabled:
            col = _alpha_on(BG_DEEP, TEXT_FAINT, 0.5)
            fill = _alpha_on(BG_DEEP, PANEL, 0.6)
            label = "敌军行动…" if self.pending else "–"
        else:
            col = GOLD
            fill = _alpha_on(BG_DEEP, PANEL, 0.95)
            label = "结束回合"
        if self.hover_end and enabled:
            fill = _alpha_on(BG_DEEP, PANEL_HI, 1.0)
            col = _shade(col, 0.2)
        self.app.round_rect(x1, y1, x2, y2, 12, fill=fill, outline=col,
                            width=2)
        if enabled:
            self.app.round_rect(x1 + 3, y1 + 3, x2 - 3, y1 + 7, 4,
                                fill=_alpha_on(fill, col, 0.30), outline="")
        self.app.text_shadow((x1 + x2) / 2, (y1 + y2) / 2, label,
                             font=T.FONT_BUTTON, fill=col)
        self.app.text_shadow((x1 + x2) / 2, y2 + 18,
                             "回合 %d" % int(self.snap.get("turn", 1) or 1),
                             font=T.FONT_TINY, fill=TEXT_DIM)

    def _draw_turn_banner(self) -> None:
        if self.turn_banner <= 0:
            return
        t = self.turn_banner / 1400.0
        a = min(1.0, t * 2.2)
        phase = "player" if not self.pending else "enemy"
        text = "我方行动阶段" if phase == "player" else "敌军行动阶段"
        col = CYAN if phase == "player" else BLOOD
        y = self.h * 0.30
        self.c.create_rectangle(0, y - 34, self.w, y + 34,
                                fill=_alpha_on(BG_DEEP, "#000000", 0.35 * a),
                                outline="")
        self.app.text_shadow(self.w / 2, y, text, font=T.FONT_TITLE,
                             fill=_alpha_on(BG_DEEP, col, a))

    def _draw_log(self) -> None:
        log = self.snap.get("log") or []
        if not log:
            return
        x = self.w * 0.30
        y = self.h * 0.045
        for i, line in enumerate(log[-4:]):
            self.app.text_shadow(x, y + i * 20, str(line)[:46],
                                 font=T.FONT_TINY,
                                 fill=_alpha_on(BG_DEEP, TEXT_DIM,
                                                0.85 - i * 0.16),
                                 anchor="w")

    def _draw_selection_hint(self, sx: float, sy: float) -> None:
        if self.selected is None:
            return
        hand = self.snap.get("hand") or []
        if not (0 <= self.selected < len(hand)):
            return
        cd = hand[self.selected]
        kind = self._target_kind(cd)
        if kind in ("self", "none"):
            return
        alive = [e for e in (self.snap.get("enemies") or []) if e.get("alive", True)]
        if len(alive) <= 1:
            return
        self.app.text_shadow(self.w / 2, self.h * 0.20,
                             "选择一个目标 ▶", font=T.FONT_H2, fill=GOLD)

    def _target_kind(self, cd: dict) -> str:
        t = str(cd.get("target") or "")
        if t:
            return t
        typ = str(cd.get("type") or "")
        return "enemy" if typ == "attack" else "self"

    def _cost_text(self, cost) -> str:
        try:
            c = int(cost)
        except Exception:
            return "?"
        return "X" if c < 0 else str(c)

    # ---------------------------------------------------------------- 手牌
    def _draw_hand(self, sx: float, sy: float) -> None:
        slots = self._hand_slots()
        if not slots:
            self.app.text_shadow(self.w / 2, self.h - 96, "手牌为空",
                                 font=T.FONT_BODY, fill=TEXT_FAINT)
            return
        hand = self.snap.get("hand") or []
        hover_slot = None
        for s in slots:
            if s["i"] == self.hover_card:
                hover_slot = s
            else:
                self._draw_card(s["i"], s["x"] + sx, s["y"] + sy, s, False)
        if hover_slot is not None:
            self._draw_card(hover_slot["i"], hover_slot["x"] + sx,
                            hover_slot["y"] + sy, hover_slot, True)
        # 选中指示
        if self.selected is not None:
            for s in slots:
                if s["i"] == self.selected:
                    self.app.round_rect(s["x"] - s["w"] / 2 - 6 + sx,
                                        s["y"] - s["h"] / 2 - 6 + sy,
                                        s["x"] + s["w"] / 2 + 6 + sx,
                                        s["y"] + s["h"] / 2 + 30 + sy,
                                        16, fill="", outline=GOLD, width=3)
                    self.app.text_shadow(s["x"] + sx, s["y"] - s["h"] / 2 - 22 + sy,
                                         "已选中", font=T.FONT_TINY, fill=GOLD)

    def _real_card(self, cd: dict):
        """把 snapshot 的手牌 dict 还原成 core 的 CardInstance（交给 widgets 画）。"""
        if not isinstance(cd, dict):
            return cd
        if self._real is None:
            try:
                from core import cards as C
                self._real = C
            except Exception:
                self._real = False
        if not self._real:
            return None
        fn = getattr(self._real, "make_card", None)
        did = cd.get("def_id") or cd.get("id") or ""
        if not callable(fn) or not did:
            return None
        try:
            return fn(did, int(cd.get("upgraded", 0) or 0),
                      cd.get("uid") if isinstance(cd.get("uid"), int) else None)
        except TypeError:
            try:
                return fn(did, int(cd.get("upgraded", 0) or 0))
            except Exception:
                return None
        except Exception:
            return None

    def _draw_card(self, i: int, cx: float, cy: float, slot: dict,
                   hover: bool) -> None:
        """手牌：优先用 widgets.CardView.draw_on（与 ui-theme 视觉统一）。"""
        hand = self.snap.get("hand") or []
        if not (0 <= i < len(hand)):
            return
        cd = hand[i]
        s = slot["scale"]
        playable = bool(cd.get("playable", True))
        selected = (self.selected == i)
        drawer = self._card_drawer()
        if drawer is not None:
            obj = self._real_card(cd)
            if obj is not None:
                try:
                    drawer(self.c, cx, cy, obj, scale=s, angle=slot["rot"],
                           playable=playable, hover=hover, selected=selected,
                           disabled=not playable, tags="card", glow=hover)
                    return
                except Exception:
                    pass
        self._draw_card_builtin(i, cx, cy, slot, hover)

    def _card_drawer(self):
        if self._drawer is _UNSET:
            fn = None
            try:
                from .widgets import CardView
                fn = getattr(CardView, "draw_on", None)
            except Exception:
                try:
                    from widgets import CardView  # type: ignore
                    fn = getattr(CardView, "draw_on", None)
                except Exception:
                    fn = None
            self._drawer = fn if callable(fn) else None
        return self._drawer

    def _draw_card_builtin(self, i: int, cx: float, cy: float, slot: dict,
                           hover: bool) -> None:
        hand = self.snap.get("hand") or []
        if not (0 <= i < len(hand)):
            return
        cd = hand[i]
        c = self.c
        s = slot["scale"]
        w, h = CARD_W * s, CARD_H * s
        x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        rarity = str(cd.get("rarity", "common"))
        rcol = self._rarity_color(rarity)
        tcol = TYPE_COLORS.get(str(cd.get("type")), TEXT_DIM) \
            if isinstance(TYPE_COLORS, dict) else TEXT_DIM
        playable = bool(cd.get("playable", True))
        selected = (self.selected == i)

        # 阴影
        if hover:
            self.app.round_rect(x1 - 4, y1 - 4, x2 + 10, y2 + 14, 14,
                                fill=_alpha_on(BG_DEEP, "#000000", 0.35),
                                outline="")
        else:
            self.app.round_rect(x1 - 2, y1 - 2, x2 + 5, y2 + 8, 12,
                                fill=_alpha_on(BG_DEEP, "#000000", 0.28),
                                outline="")
        body_dark = "#0E1B28"
        body_light = "#1B2F45"
        self.app.vgradient(x1, y1, x2, y2, body_light, body_dark, steps=18)
        self.app.round_rect(x1, y1, x2, y2, 12, fill="", outline=rcol,
                            width=3 if (hover or selected) else 2)
        self.app.round_rect(x1 + 5, y1 + 5, x2 - 5, y1 + 30 * s, 8, fill=tcol,
                            outline="")
        name = str(cd.get("name", "?"))
        up = " +" if cd.get("upgraded") else ""
        self._fit_text(cx, y1 + 18 * s, name + up, w - 46 * s,
                       T.FONT_CARD_NAME, "#0B1620")

        orb_r = 17 * s
        ox, oy = x1 + 6 * s, y1 + 6 * s
        c.create_oval(ox - orb_r, oy - orb_r, ox + orb_r, oy + orb_r,
                      fill=_alpha_on(BG_DEEP, GOLD, 0.95),
                      outline=_shade(GOLD, -0.35), width=2)
        self.app.text_shadow(ox, oy, self._cost_text(cd.get("cost", 0)),
                             font=T.FONT_NUM, fill="#3A2600")

        art_y1 = y1 + 32 * s
        art_y2 = y1 + 118 * s
        self.app.round_rect(x1 + 8, art_y1, x2 - 8, art_y2, 8,
                            fill=_alpha_on(BG_DEEP, _shade(tcol, -0.55), 0.85),
                            outline=_alpha_on(BG_DEEP, tcol, 0.5), width=1)
        self._card_art(cx, (art_y1 + art_y2) / 2, (art_y2 - art_y1) * 0.42,
                       cd, tcol, s)

        desc = self._fill_placeholders(str(cd.get("text", "") or ""), cd)
        lines = self.app.wrap_text(desc, int(w - 22 * s), T.FONT_CARD_TEXT,
                                   max_lines=4)
        ty = art_y2 + 16 * s
        for ln in lines:
            self.app.text_shadow(cx, ty, ln, font=T.FONT_CARD_TEXT, fill=TEXT,
                                 tags="card")
            ty += 16 * s

        if cd.get("upgraded"):
            c.create_oval(x2 - 20 * s, y2 - 20 * s, x2 - 4 * s, y2 - 4 * s,
                          fill="#5FD07A", outline="", tags="card")
        if not playable:
            self.app.round_rect(x1, y1, x2, y2, 12,
                                fill=_alpha_on(BG_DEEP, "#000000", 0.5),
                                outline="")
            self.app.text_shadow(cx, cy, "不可打出", font=T.FONT_SMALL,
                                 fill=BLOOD)

    def _card_art(self, cx: float, cy: float, r: float, cd: dict, tcol: str,
                  s: float) -> None:
        """卡面小插画：按 type/arch 画不同符号。"""
        c = self.c
        typ = str(cd.get("type", "skill"))
        arch = str(cd.get("arch", ""))
        col = _shade(tcol, 0.25)
        t = self.app._tick
        if typ == "attack":
            c.create_polygon(cx, cy - r, cx + r * 0.22, cy - r * 0.1,
                             cx + r * 0.85, cy + r * 0.8, cx + r * 0.3,
                             cy + r * 0.95, cx - r * 0.25, cy + 0.0,
                             fill=col, outline="", tags="card")
            c.create_line(cx - r * 0.9, cy + r * 0.1, cx - r * 0.1, cy + r,
                          fill=_shade(col, -0.2), width=max(2, int(4 * s)),
                          tags="card")
        elif typ == "power":
            for i in range(8):
                a = math.pi * 2 * i / 8.0 + t * 0.01
                c.create_line(cx + math.cos(a) * r * 0.35, cy + math.sin(a) * r * 0.35,
                              cx + math.cos(a) * r, cy + math.sin(a) * r,
                              fill=col, width=max(2, int(3 * s)), tags="card")
            c.create_oval(cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3,
                          fill=GOLD, outline="", tags="card")
        elif typ == "curse":
            c.create_oval(cx - r * 0.8, cy - r * 0.8, cx + r * 0.8, cy + r * 0.8,
                          fill="#3A1C4A", outline=col, width=2, tags="card")
            c.create_line(cx - r * 0.5, cy + r * 0.5, cx + r * 0.5, cy - r * 0.5,
                          fill=col, width=max(2, int(3 * s)), tags="card")
        elif typ == "status":
            c.create_rectangle(cx - r * 0.8, cy - r * 0.8, cx + r * 0.8,
                               cy + r * 0.8, fill="#26333E", outline=col,
                               width=2, tags="card")
            c.create_line(cx - r * 0.5, cy, cx + r * 0.5, cy, fill=col,
                          width=max(2, int(3 * s)), tags="card")
        else:  # skill：按流派
            if arch == "block":
                c.create_polygon(cx, cy - r, cx + r * 0.85, cy - r * 0.5,
                                 cx + r * 0.85, cy + r * 0.3, cx, cy + r,
                                 cx - r * 0.85, cy + r * 0.3, cx - r * 0.85,
                                 cy - r * 0.5, fill=col, outline="", tags="card")
            elif arch == "poison":
                c.create_oval(cx - r * 0.75, cy - r * 0.75, cx + r * 0.35,
                              cy + r * 0.35, fill=col, outline="", tags="card")
                c.create_oval(cx - r * 0.05, cy - r * 0.05, cx + r * 0.85,
                              cy + r * 0.85, fill=_shade(col, -0.25),
                              outline="", tags="card")
            elif arch == "energy":
                c.create_polygon(cx - r * 0.35, cy - r, cx + r * 0.55,
                                 cy - r * 0.15, cx + r * 0.05, cy - r * 0.05,
                                 cx + r * 0.55, cy + r, cx - r * 0.6,
                                 cy - r * 0.1, cx - r * 0.05, cy - r * 0.2,
                                 fill=col, outline="", tags="card")
            elif arch == "summon":
                for j in range(3):
                    rr = r * (0.85 - j * 0.22)
                    c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                  fill="", outline=col, width=2, tags="card")
            else:
                c.create_oval(cx - r * 0.85, cy - r * 0.85, cx + r * 0.85,
                              cy + r * 0.85, fill=col, outline="", tags="card")

    def _fill_placeholders(self, text: str, cd: dict) -> str:
        dmg = int(cd.get("damage", 0) or 0)
        blk = int(cd.get("block", 0) or 0)
        hits = int(cd.get("hits", 1) or 1)
        try:
            return text.format(damage=dmg, block=blk, hits=hits,
                               magic=int(cd.get("magic", 0) or 0),
                               magic2=int(cd.get("magic2", 0) or 0))
        except Exception:
            return text

    def _fit_text(self, cx: float, cy: float, text: str, maxw: float, font,
                  fill: str) -> None:
        try:
            fn = getattr(T, "slice_text_cjk", None)
            if callable(fn):
                text = fn(text, maxw, font)
        except Exception:
            pass
        self.app.text_shadow(cx, cy, text, font=font, fill=fill)

    def _rarity_color(self, rarity: str) -> str:
        fn = getattr(T, "rarity_color", None)
        if callable(fn):
            try:
                return str(fn(rarity))
            except Exception:
                pass
        if isinstance(RARITY_COLORS, dict):
            return RARITY_COLORS.get(rarity, "#C7D6E4")
        return GOLD
