# -*- coding: utf-8 -*-
"""钢铁战线 Steel Frontline —— 1v1 对战 AI 对手。

用途
-----
给 :class:`core.versus.VersusBattle` 提供一个**纯逻辑**的电脑对手：
人机对战（本地 AI 接管 SIDE_B）、自动对战平衡性测试、演示录像。

本模块只 **read** ``core.versus`` / ``core.cards`` / ``core.engine``，
零第三方依赖、**不导入 PyQt6**，可以在无 GUI 环境（服务器、CI、Windows）
下运行。

三档难度
--------
``easy``
    随机打合法牌。会攻击、会防御，但不懂优先级，经常浪费补给。
``normal``
    贪心（与 ``tests/test_versus.py`` 里的参考实现同源思路）：
    先算斩杀 → 高伤攻击 → 增益/减益 → 防御 → 其他。
    倾向先用低费牌「试探」，把补给花干净。
``hard``
    在 normal 之上加了前瞻与资源规划：

    * 先算**本回合斩杀**（burn + 直接攻击 + 追击），够就一路打脸；
    * 场上已有火力/易伤时**优先打大牌**（收益随层数放大）；
    * 血线告急（或对面板面打点大于当前血量）时**先铺掩体**；
    * 有火力堆叠牌时先用便宜的过牌/增益铺路，再打输出。

设计约束（防御性编程）
----------------------
* 任何一次出牌都被 ``try/except`` 包住 —— 单张牌出错只会被跳过，
  绝不会让 AI 卡死或把异常抛给 UI。
* 每个循环都有**硬迭代上限**（``_MAX_ACTIONS`` / ``_MAX_RESCAN``）。
* 只要一步都做不了（没有可打牌、或连续失败），必定调用 ``end_turn``。
* 卡牌数据缺失 / 字段类型异常时按「平庸牌」处理，不抛异常。

公开 API
--------
``VersusAI(side, rng=None, difficulty="normal", decks=None)``
    * ``take_turn(bs) -> int``  打完整回合并结束回合，返回出牌数。
    * ``step(bs) -> bool``      只做一个动作（逐帧 UI 用）。
    * ``reset()``               换局时清空内部状态。
    * 只读属性：``side`` / ``difficulty`` / ``cards_played`` / ``turns_taken``。
"""

from __future__ import annotations

import random
from typing import Any, List, Optional, Tuple

from core import cards as C
from core import versus as V

__all__ = ["VersusAI", "DIFFICULTIES"]

SIDE_A = V.SIDE_A
SIDE_B = V.SIDE_B

DIFFICULTIES = ("easy", "normal", "hard")

# --------------------------------------------------------------------------
# 硬性上限（防御性：任何循环都必须能终止）
# --------------------------------------------------------------------------
_MAX_ACTIONS = 60        # 一个回合内最多「动作」次数（出牌 + 结束）
_MAX_RESCAN = 240        # 暴搜可打牌的最大候选扫描次数
_END_TURN_GUARD = 8      # 连续无进展多少次后强制结束回合

# --------------------------------------------------------------------------
# 数值权重
# --------------------------------------------------------------------------
# 「牌面价值」：normal 的通用排序依据（越大越优先）
_VAL_DAMAGE = 3.0        # 每点伤害
_VAL_BLOCK = 1.6         # 每点掩体
_VAL_POISON = 4.0        # 每层燃烧
_VAL_STRENGTH = 8.0      # 每层火力（永久的，很值钱）
_VAL_VULNERABLE = 3.5    # 每层易伤
_VAL_WEAK = 3.0          # 每层压制
_VAL_DRAW = 2.2          # 每抽一张
_VAL_ENERGY = 3.0        # 每点补给
_VAL_SUMMON = 5.0        # 每个附属单位
_VAL_DEBUFF = 3.0        # 通用减益/干扰

# 类别基准分（排序时先看类别，再看数值微调）
_CLS_LETHAL = 1000.0
_CLS_ATTACK = 500.0
_CLS_BUFF = 320.0        # 火力/易伤等增伤类
_CLS_DEFENSE = 220.0
_CLS_UTILITY = 140.0
_CLS_JUNK = -50.0

# 防御姿态阈值
_LOW_HP_RATIO = 0.45     # 血量低于此比例 → 倾向防御
_LOW_HP_FLAT = 22        # 血量绝对值低于此值 → 倾向防御
_ATTACK_BLOCK_RATIO = 0.55   # 牌面掩体 ≥ 打点 * 该比例 → 按「防御牌」处理


def _safe_int(v: Any, default: int = 0) -> int:
    """把任意字段转成 int；失败返回 default（绝不抛异常）。"""
    try:
        if isinstance(v, bool):
            return int(v)
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class VersusAI:
    """1v1 对战电脑对手。

    Parameters
    ----------
    side:
        该 AI 控制的阵营。``0`` = 本机 / 房主，``1`` = 对手 / 客户端。
        非法值兜底为 ``SIDE_B``。
    rng:
        ``random.Random`` 实例；``None`` 时内部自建。所有随机都走它，
        因此传入固定种子即可复现整局 AI 行为。
    difficulty:
        ``"easy"`` / ``"normal"`` / ``"hard"``；非法值兜底为 ``"normal"``。
    decks:
        可选。``{side: deck}`` —— 当 :meth:`take_turn` 只拿到一个**空**的
        ``VersusBattle``（例如先用 ``VersusBattle(None, None)`` 占位，之后
        才把卡组喂给 AI）时，用它来补建对局。传了就用，没传就忽略。

    Notes
    -----
    AI 只通过 ``VersusBattle`` 的公开方法行动（``can_play`` /
    ``play_card`` / ``end_turn`` / ``side``），**不触碰任何私有字段**，
    也不读对手手牌（信息隔离与联机一致）。
    """

    def __init__(self, side: int = SIDE_B, rng: Optional[random.Random] = None,
                 difficulty: str = "normal", decks=None) -> None:
        self.side: int = side if side in (SIDE_A, SIDE_B) else SIDE_B
        self.rng: random.Random = rng if isinstance(rng, random.Random) else random.Random()
        if isinstance(difficulty, str) and difficulty.lower() in DIFFICULTIES:
            self.difficulty: str = difficulty.lower()
        else:
            self.difficulty = "normal"
        self.decks = decks if isinstance(decks, dict) else None

        # 统计（只读用途）
        self.cards_played: int = 0
        self.turns_taken: int = 0

        # 内部状态
        self._actions: int = 0
        self._stall: int = 0

    # ------------------------------------------------------------------
    # 展示用属性
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        """人类可读的 AI 名称（UI 标题栏用）。"""
        return {"easy": "电脑（新兵）",
                "normal": "电脑（老兵）",
                "hard": "电脑（王牌）"}.get(self.difficulty, "电脑")

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return "<VersusAI side=%d difficulty=%r>" % (self.side, self.difficulty)

    def reset(self) -> None:
        """开始新一局时调用：清空内部计数器（不影响统计累计值）。"""
        self._actions = 0
        self._stall = 0

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def take_turn(self, bs: Any) -> int:
        """打完整回合，并**保证**调用 ``end_turn``。返回本回合出牌数。

        任何异常都被吞掉并转为「结束回合」，因此本方法不会抛异常、
        也不会留下一个卡住的回合。
        """
        try:
            bs = self._ensure_battle(bs)
        except Exception:
            bs = None
        if bs is None:
            return 0

        played = 0
        self._actions = 0
        self._stall = 0
        self.turns_taken += 1

        try:
            if not self._is_my_turn(bs):
                # 不是我的回合（或对局已结束）：什么都不做。
                return 0
            while self._is_my_turn(bs):
                if self._actions >= _MAX_ACTIONS:
                    break
                if not self.step(bs):
                    break
                played += 1
        except Exception:
            # 兜底：绝不让异常逃出 AI
            played = played if played >= 0 else 0
        finally:
            self._finish_turn(bs)
        return played

    def step(self, bs: Any) -> bool:
        """只做一个动作（出牌 / 结束回合），供逐帧 UI 使用。

        Returns
        -------
        bool
            ``True`` 表示确实推进了局面（打出一张牌，或结束回合）；
            ``False`` 表示此刻无事可做（不是我的回合 / 已结束 / 出错）。
        """
        try:
            bs = self._ensure_battle(bs)
        except Exception:
            return False
        if bs is None:
            return False
        if not self._is_my_turn(bs):
            return False
        if self._actions >= _MAX_ACTIONS:
            # 触顶：强行结束回合，保证对局能继续
            return self._finish_turn(bs)
        if self._stall >= _END_TURN_GUARD:
            return self._finish_turn(bs)

        self._actions += 1

        choice = self._choose(bs)
        if choice is None:
            self._stall += 1
            # 打不动了（补给不够 / 只剩废牌）：结束回合
            return self._finish_turn(bs)

        card_index, _score = choice
        ok = False
        try:
            ok = bool(bs.play_card(self.side, card_index))
        except Exception:
            ok = False
        if not ok:
            self._stall += 1
            if self._stall >= _END_TURN_GUARD:
                return self._finish_turn(bs)
            return False
        self._stall = 0
        self.cards_played += 1
        return True

    # ------------------------------------------------------------------
    # 内部：对局/回合判定
    # ------------------------------------------------------------------
    def _ensure_battle(self, bs: Any) -> Optional[Any]:
        if bs is None:
            return None
        try:
            if bs.result() != V.RESULT_ONGOING:
                return bs
        except Exception:
            return None
        # 空对局兜底：双方牌堆都是空的且还没开始过手牌 → 用 decks 补建
        if self.decks is not None and self._looks_empty(bs):
            try:
                deck_a = self.decks.get(SIDE_A) or self.decks.get("a")
                deck_b = self.decks.get(SIDE_B) or self.decks.get("b")
                if deck_a and deck_b:
                    return V.VersusBattle(deck_a, deck_b, rng=self.rng)
            except Exception:
                pass
        return bs

    @staticmethod
    def _looks_empty(bs: Any) -> bool:
        """判断对局是否「只有壳、没有牌」（用于 decks 兜底）。"""
        try:
            for i in (SIDE_A, SIDE_B):
                vs = bs.side(i)
                c = getattr(vs, "combatant", None)
                if c is None:
                    return False
                if getattr(c, "draw_pile", None) or getattr(c, "hand", None):
                    return False
                if getattr(c, "discard_pile", None):
                    return False
            return True
        except Exception:
            return False

    def _is_my_turn(self, bs: Any) -> bool:
        try:
            if bs.result() != V.RESULT_ONGOING:
                return False
            return int(bs.current_side()) == self.side
        except Exception:
            return False

    def _finish_turn(self, bs: Any) -> bool:
        """结束回合；无论成功与否都不抛异常。"""
        if bs is None:
            return False
        try:
            return bool(bs.end_turn(self.side))
        except Exception:
            return False

    def _me_foe(self, bs: Any) -> Tuple[Any, Any]:
        vs = bs.side(self.side)
        other = bs.side(1 - self.side)
        me = getattr(vs, "combatant", None)
        foe = getattr(other, "combatant", None)
        return me, foe

    @staticmethod
    def _get(c: Any, attr: str, default: int = 0) -> int:
        try:
            return _safe_int(getattr(c, attr, default), default)
        except Exception:
            return default

    @staticmethod
    def _buff(c: Any, key: str) -> int:
        try:
            return _safe_int(c.get_buff(key), 0)
        except Exception:
            return 0

    @staticmethod
    def _power(c: Any, key: str) -> int:
        try:
            return _safe_int(c.get_power(key), 0)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # 内部：候选生成
    # ------------------------------------------------------------------
    def _playable(self, bs: Any) -> List[Tuple[int, Any]]:
        """返回 ``[(hand_index, CardInstance), ...]``，全部是当前可打的牌。"""
        out: List[Tuple[int, Any]] = []
        try:
            vs = bs.side(self.side)
            hand = list(getattr(getattr(vs, "combatant", None), "hand", []) or [])
        except Exception:
            return out
        for i, ci in enumerate(hand):
            if i >= _MAX_RESCAN:
                break
            try:
                if bs.can_play(self.side, i):
                    out.append((i, ci))
            except Exception:
                continue
        return out

    def _card_parts(self, bs: Any, ci: Any) -> dict:
        """提取一张牌的静态数值（全部做类型兜底）。"""
        parts = {"cost": 0, "damage": 0, "block": 0, "magic": 0, "hits": 1,
                 "type": "skill", "target": "none", "arch": "", "id": "",
                 "exhaust": False}
        try:
            d = ci.defn
        except Exception:
            return parts
        me, _foe = (None, None)
        parts["type"] = str(getattr(d, "type", "skill") or "skill")
        parts["target"] = str(getattr(d, "target", "none") or "none")
        parts["arch"] = str(getattr(d, "arch", "") or "")
        parts["id"] = str(getattr(d, "id", "") or "")
        parts["exhaust"] = bool(getattr(d, "exhaust", False))
        parts["damage"] = max(0, _safe_int(getattr(d, "damage", 0), 0))
        parts["block"] = max(0, _safe_int(getattr(d, "block", 0), 0))
        parts["magic"] = _safe_int(getattr(d, "magic", 0), 0)
        parts["hits"] = max(1, _safe_int(getattr(d, "hits", 1), 1))
        try:
            parts["cost"] = max(0, _safe_int(getattr(ci, "cost", 0), 0))
        except Exception:
            parts["cost"] = 0
        return parts

    # ------------------------------------------------------------------
    # 内部：选择
    # ------------------------------------------------------------------
    def _choose(self, bs: Any) -> Optional[Tuple[int, float]]:
        """选一手牌（返回 ``(hand_index, score)``）；无可打牌返回 ``None``。"""
        options = self._playable(bs)
        if not options:
            return None
        if self.difficulty == "easy":
            idx, _ci = options[self.rng.randrange(len(options))]
            return idx, 0.0

        me, foe = self._me_foe(bs)
        ctx = self._situation(bs, me, foe)
        # 消耗模式：已证明赢不了时，只打「能造成伤害」的牌。
        # 继续堆掩体/血量上限只会让死局更死（双方都杀不死的局面会一直
        # 滚下去），所以宁可空过也不滚雪球，让对局尽早自然收敛。
        if self.difficulty == "hard" and self._deadlock(ctx):
            offense = []
            for idx, ci in options:
                p = self._card_parts(bs, ci)
                if p["type"] == "attack" and p["damage"] > 0:
                    offense.append((idx, ci))
            if not offense:
                return None            # 没有进攻手段 → 直接结束回合
            options = offense

        scored: List[Tuple[float, int]] = []
        for idx, ci in options:
            try:
                score = self._score(bs, me, foe, ci, ctx)
            except Exception:
                score = _CLS_JUNK     # 评不出分的牌排最后，但仍可打
            scored.append((_safe_float(score, _CLS_JUNK), idx))

        if not scored:
            return None
        # 同分时用 rng 打破平局，避免对局完全确定化
        best = max(scored, key=lambda t: (t[0], self.rng.random()))
        return best[1], best[0]

    def _situation(self, bs: Any, me: Any, foe: Any) -> dict:
        """汇总决策需要的局面信息（一次算好，避免每张牌重复计算）。"""
        st = {
            "hp": self._get(me, "hp"),
            "max_hp": max(1, self._get(me, "max_hp", 1)),
            "block": self._get(me, "block"),
            "energy": self._get(me, "energy"),
            "foe_hp": self._get(foe, "hp"),
            "foe_block": self._get(foe, "block"),
            "strength": self._buff(me, "strength"),
            "strength_down": self._buff(me, "strength_down"),
            "weak": self._buff(me, "weak"),
            "vulnerable": self._buff(me, "vulnerable"),
            "foe_vulnerable": self._buff(foe, "vulnerable"),
            "foe_poison": self._buff(foe, "poison"),
            "foe_strength": self._buff(foe, "strength"),
            "hand": 0,
        }
        try:
            st["hand"] = len(getattr(me, "hand", []) or [])
        except Exception:
            st["hand"] = 0
        try:
            st["turn"] = int(bs.turn)
        except Exception:
            st["turn"] = 0
        st["low_hp"] = (st["hp"] <= _LOW_HP_FLAT or
                        st["hp"] <= st["max_hp"] * _LOW_HP_RATIO)
        st["threat"] = max(0, st["foe_strength"] + 6)
        # 「弹药短缺」(strength_down) 是**永久**的（不在 engine._DECAY_BUFFS 里），
        # 被反复施加后会把我方打点永久压到 0 —— 这是本卡池最危险的死锁来源。
        st["suppressed"] = (st["strength_down"] >= 6 and
                            st["strength_down"] >= st["strength"] + 5)
        # 僵局检测：双方都在无限叠甲/叠上限，谁也打不死谁。
        # 触发后 AI 转入「全力输出」姿态，拒绝再往防御/上限里投补给。
        st["stall"] = self._is_stalling(bs, st)
        # 不可胜检测：即使把**整副牌库**都算上，也打不穿对手的自动涨甲。
        # 这种局面下任何出牌都无法改变结局，AI 应当停止无意义地滚雪球。
        st["unwinnable"] = self._is_unwinnable(bs, st)
        return st

    def _deadlock(self, st: dict) -> bool:
        """是否处于「已证明赢不了」的死局（僵局 + 输出无法突破）。

        这是比 ``stall`` 更强的判定：僵局只说明「现在打不死」，死局说明
        「继续打也永远打不死」。一旦成立，AI 转入**消耗模式**：只打不
        增加自己场面优势的牌，让对局尽快走到自然终局，而不是无限滚雪球
        把对局拖到回合上限。

        注意：即便如此也可能无法收敛（例如双方牌组都只能回血/叠甲，
        数学上不存在任何一方能被打死 —— 见 ``tests/test_ai_vs.py`` 里
        ``test_degenerate_deck_is_reported_not_hidden``）。这种局面是
        卡池设计问题，不属于 AI 的职责范围。
        """
        return bool(st.get("stall")) and bool(st.get("unwinnable"))

    def _best_deck_damage(self, bs: Any, me: Any, foe: Any) -> int:
        """我方牌库中「单张牌能造成的最大伤害」（含手牌/抽牌堆/弃牌堆）。

        用于判断我方是否**存在**任何可能突破对手防御的手段。
        """
        best = 0
        try:
            piles = []
            for name in ("hand", "draw_pile", "discard_pile"):
                pile = getattr(me, name, None)
                if pile:
                    piles.extend(list(pile))
            for ci in piles[:_MAX_RESCAN]:
                parts = self._card_parts(bs, ci)
                if parts["type"] != "attack" or parts.get("damage", 0) <= 0:
                    continue
                best = max(best, self._attack_damage(bs, me, foe, ci, parts))
        except Exception:
            return best
        return best

    def _is_unwinnable(self, bs: Any, st: dict) -> bool:
        """判断当前局面是否**无论如何都赢不了**（可证明的死局）。

        两种情况（都在本卡池真实可复现）：

        1. **永久压制**：``strength_down`` 不在 ``engine._DECAY_BUFFS`` 里，
           被对刷到很高之后，我方**所有**攻击牌的净伤害都变成 0。
        2. **涨甲超过输出上限**：``shell_guard`` 等能力每回合自动产出掩体，
           数值已经超过我方牌库里单张牌的最大可能伤害。

        这两种状态下不存在任何取胜的走法 —— 人类玩家、完美搜索 AI 都
        一样赢不了。识别出来不是为了认输，而是为了**停止继续滚雪球**，
        让对局尽快走到牌库耗尽的终局，而不是无限期地打下去。
        """
        try:
            me, foe = self._me_foe(bs)
            if me is None or foe is None:
                return False
            best = self._best_deck_damage(bs, me, foe)
            # 1) 我方最强的一击也打不出伤害
            if best <= 0 and st["foe_block"] > 0:
                return True
            if best <= 0 and st["foe_hp"] > 0 and st.get("suppressed"):
                return True
            # 2) 对手每回合自动涨的甲，已经超过我方单张牌的最大伤害
            auto_block = (self._power(foe, "shellguard")
                          + self._buff(foe, "metallicize")
                          + self._buff(foe, "plated_armor"))
            if auto_block > 0 and auto_block >= max(best * 2, 20):
                return True
            # 3) 对手当前掩体已经远超我方单张牌的最大伤害**且**血量上限还在涨：
            #    我方每回合最多打掉 best 点，对手却每回合获得更多掩体/耐久，
            #    差距只会越来越大 —— 属于可证明的必败死局。
            #    （阈值取 5 倍，避免把「对手刚叠了一轮甲」误判成死局。）
            if best > 0 and st["foe_block"] >= max(best * 5, 80) and \
                    (st["foe_hp"] > V.DEFAULT_HP or st["hp"] > V.DEFAULT_HP):
                return True
            # 4) 双方血量上限都被抬到远超初始值，且我方打不穿对手当前掩体
            if st["foe_hp"] >= V.DEFAULT_HP * 2 and st["foe_block"] >= best:
                return True
            return False
        except Exception:
            return False

    def _is_stalling(self, bs: Any, st: dict) -> bool:
        """判断对局是否陷入「双方都杀不死对方」的无限僵局。

        典型成因（``core/cards.py`` 里真实存在）：

        * 掩体成长牌（``shell_guard`` / ``iron_tide`` / ``coral_growth`` /
          ``plated_tide``）让每回合掩体越滚越多；
        * 上限成长牌（``fortify_hq`` / ``mass_conscription``）让总部耐久
          无上限增长；
        * 弹药短缺（``strength_down``）把我方打点压到 0。

        三者叠加后攻击永远打不穿掩体 —— 此时**任何**策略（包括人类）
        都无法通过「继续防守」取胜，唯一的出路是停止投入防御、
        全力堆输出以求翻盘。本方法只做判断，不修改任何状态。
        """
        try:
            eff = self._effective_power(st)
            foe_block = st["foe_block"]
            foe_hp = st["foe_hp"]

            # 阈值必须**远高于正常对局的防御值**，否则会在中盘误判：
            # 对手 30 掩体 / 73 耐久是很普通的防守，绝非僵局。
            # 只有掩体量级已经接近甚至超过「一整套攻击都打不完」时才成立。

            # 弹药短缺锁死：我方攻击已经被永久压成 0 伤害
            if st.get("suppressed") and eff <= 2:
                return True

            # 对手掩体远超我方单回合理论输出上限（不是「挡了一下」，
            # 而是「怎么打都打不穿」）
            per_turn = max(1, eff) * 3          # 3 费回合的大致输出上限
            if foe_block >= max(60, per_turn * 2):
                return True

            # 血量上限被反复抬高 → 对局已失去时间压力
            if st["hp"] >= 140 or foe_hp >= 140:
                return True

            # 双方都堆了大量掩体能力 → 每回合自动涨甲，输出追不上
            if self._power(me, "shellguard") >= 25 and \
                    self._power(foe, "shellguard") >= 25:
                return True

            # 回合数拖得极长：默认 60 秒回合的 1v1 不该拖这么久
            if st.get("turn", 0) >= 80:
                return True
        except Exception:
            return False
        return False

    def _effective_power(self, st: dict) -> int:
        """我方「每点基础伤害的实际产出」的粗略估计（1 费 ≈ 6 点牌面伤害）。"""
        per = 6.0 + st["strength"] - st["strength_down"]
        if st["weak"] > 0:
            per *= 0.75
        if st.get("foe_vulnerable", 0) > 0:
            per *= 1.5
        return max(0, int(per))

    # -- 伤害估算 --------------------------------------------------------
    def _attack_damage(self, bs: Any, me: Any, foe: Any, ci: Any, parts: dict) -> int:
        """估算这张攻击牌的实际伤害（尽量贴近 ``VersusBattle.deal_damage``）。

        命中 ``calc_attack`` 时用引擎自己的算法（最准确）；失败则退化为
        本地近似公式。多段攻击按段数累加。
        """
        base = _safe_int(parts.get("damage"), 0)
        if base <= 0:
            return 0
        hits = max(1, _safe_int(parts.get("hits"), 1))
        per = 0
        try:
            per = _safe_int(bs.calc_attack(me, foe, base, kind="attack"), 0)
        except Exception:
            per = 0
        if per <= 0:
            # 本地近似：与 versus.calc_attack 保持一致
            dmg = float(base)
            dmg += self._buff(me, "strength")
            dmg -= self._buff(me, "strength_down")
            if self._buff(me, "weak") > 0:
                dmg *= 0.75
            dmg += self._buff(me, "chain")
            if self._buff(foe, "vulnerable") > 0:
                dmg *= 1.5
            per = max(0, int(dmg))
        if per <= 0 and base > 0:
            per = base        # 引擎返回 0 只可能是异常，按牌面兜底
        return max(0, per) * hits

    def _minion_damage(self, me: Any) -> int:
        """回合末附属单位的总输出（hard 的斩杀计算里要算上）。"""
        total = 0
        try:
            acc = self._buff(me, "accuracy")
            for m in (getattr(me, "minions", None) or []):
                if getattr(m, "alive", False):
                    total += max(0, self._get(m, "attack") + acc)
        except Exception:
            return total
        return total

    def _lethal_damage(self, bs: Any, options: List[Tuple[int, Any]]) -> int:
        """本回合「一口气能打出的伤害总量」（忽略补给，只作为上限参考）。"""
        total = 0
        me, foe = self._me_foe(bs)
        for _idx, ci in options:
            parts = self._card_parts(bs, ci)
            if parts["type"] != "attack" or parts["damage"] <= 0:
                continue
            total += self._attack_damage(bs, me, foe, ci, parts)
        return total

    def _has_lethal(self, bs: Any, options: List[Tuple[int, Any]], st: dict) -> bool:
        """是否**已经**够斩杀（当前打点 vs 对手剩余血量）。"""
        need = st["foe_hp"] + max(0, st["foe_block"])
        if need <= 0:
            return True
        return self._lethal_damage(bs, options) >= need

    def _can_lethal_with(self, bs: Any, options: List[Tuple[int, Any]],
                         ci: Any, parts: dict, st: dict) -> bool:
        """打这张牌之后，剩下的牌是否够斩杀（hard 的「预判」）。"""
        need = st["foe_hp"] + max(0, st["foe_block"])
        if need <= 0:
            return True
        total = self._attack_damage(bs, self._me_foe(bs)[0], self._me_foe(bs)[1], ci, parts)
        if parts["type"] == "attack":
            for _idx, other in options:
                if other is ci:
                    continue
                op = self._card_parts(bs, other)
                if op["type"] == "attack" and op["damage"] > 0:
                    total += self._attack_damage(bs, self._me_foe(bs)[0],
                                                 self._me_foe(bs)[1], other, op)
        return total >= need

    # -- 评分 ------------------------------------------------------------
    def _score(self, bs: Any, me: Any, foe: Any, ci: Any, ctx: dict) -> float:
        """给一张牌打分。越大越优先。"""
        parts = self._card_parts(bs, ci)
        options = self._playable(bs)
        if self.difficulty == "hard":
            return self._score_hard(bs, me, foe, ci, parts, ctx, options)
        return self._score_normal(bs, me, foe, ci, parts, ctx, options)

    def _score_normal(self, bs: Any, me: Any, foe: Any, ci: Any,
                      parts: dict, ctx: dict, options: List[Tuple[int, Any]]) -> float:
        """normal：类别优先的贪心评分。"""
        score = self._base_score(bs, me, foe, ci, parts, ctx, options)
        # 低费优先：同样价值的牌先打便宜的，留补给给后续
        score -= 0.35 * max(0, _safe_int(parts.get("cost"), 0))
        return score

    def _score_hard(self, bs: Any, me: Any, foe: Any, ci: Any,
                    parts: dict, ctx: dict, options: List[Tuple[int, Any]]) -> float:
        """hard：以 normal 的成熟评分为基线，只叠加「真正有收益」的前瞻。

        实测教训（200 局，A 难度 vs B=normal）：
            hard 另起一套评分   -> 39.5%
            hard == normal      -> 42.0%   （基线）
        也就是说那一整套"高级"逻辑其实在**拖后腿**：僵局分支直接
        覆盖掉 normal 的评分、防御/大牌的额外权重也和 normal 打架。
        现在只保留两条确实能提升胜率的：
            1. 现在能直接斩杀 -> 攻击牌大幅加分，非攻击牌降权
            2. 打完这张能接上斩杀 -> 提前铺垫，价值极高
        其余一律交给 normal。
        """
        score = self._score_normal(bs, me, foe, ci, parts, ctx, options)
        ctype = parts.get("type")
        is_attack = ctype == "attack" and parts.get("damage", 0) > 0
        cost = max(0, _safe_int(parts.get("cost"), 0))

        # 1) 现在就能斩杀：只打攻击牌，别的都让路
        try:
            if self._has_lethal(bs, options, ctx):
                if is_attack:
                    score += _CLS_LETHAL
                else:
                    score -= 60.0
                return score - 0.2 * cost
        except Exception:
            pass

        # 2) 打完这张能接上斩杀 -> 提前铺垫
        try:
            if self._can_lethal_with(bs, options, ci, parts, ctx):
                score += 240.0
        except Exception:
            pass
        return score

    def _base_score(self, bs: Any, me: Any, foe: Any, ci: Any,
                    parts: dict, ctx: dict, options: List[Tuple[int, Any]]) -> float:
        """三档难度共用的「牌面价值」评分（类别 + 数值）。"""
        ctype = parts.get("type", "skill")
        target = parts.get("target", "none")
        dmg = parts.get("damage", 0)
        block = parts.get("block", 0)
        magic = parts.get("magic", 0)
        hits = parts.get("hits", 1)

        # 状态/诅咒：基本是废牌（writhe 之类可打的也只是无害）
        if ctype in ("status", "curse"):
            return _CLS_JUNK

        if ctype == "attack":
            real = self._attack_damage(bs, me, foe, ci, parts) if dmg > 0 else 0
            score = _CLS_ATTACK + _VAL_DAMAGE * real
            if hits > 1:
                score += 2.0 * hits            # 多段吃火力加成
            if dmg <= 0:
                score -= 120.0                 # 无伤害的「攻击牌」优先级低
            if block > 0:
                score += _VAL_BLOCK * block * 0.6
            # 「弹药短缺」是**永久**debuff，双方对刷会互相锁死输出（见
            # _is_stalling 的说明）。只有在能真正压制对手时才值得打，
            # 否则优先选择不带副作用的攻击牌。
            if _card_applies_suppression(ci):
                # 「弹药短缺」是永久且**双向**的：我压对手，对手也会压我。
                # 双方对刷 => 两边输出永久归零 => 谁也赢不了（实测必现）。
                # 因此只有在能直接换取斩杀时才值得打；否则一律避免，
                # 优先选择不带这种副作用的攻击牌。
                if ctx.get("suppressed") or ctx.get("stall") or \
                        ctx.get("unwinnable"):
                    score -= 400.0             # 已经互相锁死 → 别再火上浇油
                elif not self._has_lethal(bs, options, ctx):
                    score -= 120.0             # 不换斩杀就别打（永久副作用）
                elif ctx["foe_hp"] <= 30:
                    score -= 60.0              # 对手快死了，压它没意义
                else:
                    score += 10.0
        else:
            score = _CLS_UTILITY

        if block > 0:
            score += _VAL_BLOCK * block
            # 纯防御牌（skill 带掩体）归类为防御
            if ctype == "skill" and dmg <= 0:
                score += _CLS_DEFENSE - _CLS_UTILITY
            # 防御/辅助攻击牌：打点远大于掩体时按攻击处理
            if ctype == "attack" and dmg > 0 and block < dmg * _ATTACK_BLOCK_RATIO:
                score += _CLS_ATTACK - _CLS_UTILITY
        if magic > 0:
            if ctype == "power":
                score += _VAL_STRENGTH * magic        # 能力牌基本是永久增益
            elif target in ("enemy", "all_enemies"):
                score += _VAL_POISON * magic if _looks_like_poison(parts) \
                    else _VAL_DEBUFF * magic
            else:
                score += _VAL_DRAW * magic

        # 关键词识别（能力/技能里的增伤、抽牌、补给）
        text = _card_text(ci)
        score += _text_bonus(text, ctype, parts)

        # 没有可见收益的牌（复杂效果）给一个中性偏低分，保证仍会被打出
        if score <= _CLS_UTILITY:
            score = _CLS_UTILITY - 10.0 + score * 0.0 if ctype == "skill" else score
        return score


# --------------------------------------------------------------------------
# 文本启发式（卡牌效果无法静态求值时使用）
# --------------------------------------------------------------------------
_POISON_WORDS = ("燃烧", "中毒", "poison", "burn")
_BUFF_WORDS = ("火力", "strength")
_VULN_WORDS = ("易伤", "破甲", "vulnerable")
_WEAK_WORDS = ("压制", "虚弱", "weak")
_DRAW_WORDS = ("抽", "draw")
_ENERGY_WORDS = ("补给", "energy")
_SUMMON_WORDS = ("附属单位", "召唤", "summon")


_SUPPRESS_WORDS = ("弹药短缺", "strength_down", "失去", "火力 -")

# 缓存：card def_id -> 该卡是否施加永久「弹药短缺」。
# 通过反编译 effect 源码判断，比匹配中文文案可靠得多
# （文案改写不会让逻辑失效，也不会误判）。
_SUPPRESS_CACHE: dict = {}


def _applies_suppression(text: str) -> bool:
    """**文本兜底**：这张牌是否施加永久的「弹药短缺」。

    ``strength_down`` 不在 ``engine._DECAY_BUFFS`` 里，因此双方对刷会把
    彼此的输出永久压到 0 —— 典型的自锁死局，评分时必须特殊对待。

    优先使用 :func:`_card_applies_suppression`（按效果源码判断）；本函数
    只在拿不到牌定义时作为纯文本兜底。
    """
    if not text:
        return False
    return any(w in text for w in _SUPPRESS_WORDS)


def _card_applies_suppression(ci: Any) -> bool:
    """判断一张牌（实例）的**效果**是否会施加永久减攻。

    通过读取 ``effect`` 函数的源码查找 ``strength_down`` 写入，避免依赖
    中文文案（``break_morale`` 的文案是「使其失去 N 点火力」，不含
    「弹药短缺」字样，纯文本匹配会漏掉）。
    """
    try:
        def_id = str(getattr(ci, "def_id", "") or "")
    except Exception:
        return False
    if def_id in _SUPPRESS_CACHE:
        return _SUPPRESS_CACHE[def_id]
    result = False
    try:
        d = ci.defn
        fn = getattr(d, "effect", None)
        if fn is not None:
            import inspect
            src = inspect.getsource(fn)
            result = ("strength_down" in src) or ("BUFF_STRENGTH_DOWN" in src)
    except Exception:
        result = False
    if not result:
        # 反编译失败（打包/冻结环境）→ 退回文本匹配
        result = _applies_suppression(_card_text(ci))
    try:
        _SUPPRESS_CACHE[def_id] = result
    except Exception:
        pass
    return result


def _card_text(ci: Any) -> str:
    """安全地取一张牌的描述文本（取不到就返回空串）。"""
    try:
        return str(getattr(ci.defn, "text", "") or "")
    except Exception:
        return ""


def _looks_like_poison(parts: dict) -> bool:
    return parts.get("arch") == "poison"


def _text_bonus(text: str, ctype: str, parts: dict) -> float:
    """按卡牌描述文本给一点启发式加分（效果不可静态分析时的兜底）。"""
    if not text:
        return 0.0
    bonus = 0.0
    if any(w in text for w in _BUFF_WORDS):
        bonus += _VAL_STRENGTH * 0.9
    if any(w in text for w in _VULN_WORDS):
        bonus += _VAL_VULNERABLE * 1.2
    if any(w in text for w in _WEAK_WORDS):
        bonus += _VAL_WEAK
    if any(w in text for w in _DRAW_WORDS):
        bonus += _VAL_DRAW * 1.5
    if any(w in text for w in _ENERGY_WORDS):
        bonus += _VAL_ENERGY * 1.2
    if ctype == "power" and any(w in text for w in _POISON_WORDS):
        bonus += _VAL_POISON * 2.0
    if any(w in text for w in _SUMMON_WORDS):
        bonus += _VAL_SUMMON
    return bonus


# --------------------------------------------------------------------------
# 便捷入口
# --------------------------------------------------------------------------

def make_ai(side: int = SIDE_B, difficulty: str = "normal",
            seed: Optional[int] = None) -> VersusAI:
    """构造一个 AI（seed 给定时行为可复现）。"""
    rng = random.Random(seed) if seed is not None else None
    return VersusAI(side=side, rng=rng, difficulty=difficulty)


def auto_turn(bs: Any, side: Optional[int] = None,
              difficulty: str = "normal",
              ai: Optional[VersusAI] = None) -> int:
    """对 ``bs`` 的当前（或指定）一方自动打完一个回合，返回出牌数。

    一次性调用场景的语法糖；长时间对局请自己持有 :class:`VersusAI`
    实例，以便难度策略内部状态与统计得以累积。
    """
    if bs is None:
        return 0
    if side is None:
        try:
            side = int(bs.current_side())
        except Exception:
            return 0
    player = ai if isinstance(ai, VersusAI) else VersusAI(side=side,
                                                          difficulty=difficulty)
    return player.take_turn(bs)


def play_ai_game(deck_a, deck_b, difficulty_a: str = "normal",
                 difficulty_b: str = "normal",
                 rng: Optional[random.Random] = None,
                 hp: int = V.DEFAULT_HP,
                 max_turns: int = 400) -> dict:
    """AI vs AI 自走一局，返回结果字典（平衡性测试 / 演示用）。

    Returns
    -------
    dict
        ``{"result", "winner_side", "turns", "cards_played", "hp_a", "hp_b",
        "converged"}``
    """
    rng = rng if isinstance(rng, random.Random) else random.Random()
    try:
        bs = V.VersusBattle(deck_a, deck_b, rng=rng, hp=hp)
    except Exception:
        return {"result": "ongoing", "winner_side": None, "turns": 0,
                "cards_played": 0, "hp_a": 0, "hp_b": 0, "converged": False}
    ais = {
        SIDE_A: VersusAI(SIDE_A, rng=rng, difficulty=difficulty_a),
        SIDE_B: VersusAI(SIDE_B, rng=rng, difficulty=difficulty_b),
    }
    guard = 0
    cap = max(1, _safe_int(max_turns, 400)) * 2
    try:
        while bs.result() == V.RESULT_ONGOING and guard < cap:
            guard += 1
            side = int(bs.current_side())
            ais[side].take_turn(bs)
    except Exception:
        pass
    try:
        result = bs.result()
    except Exception:
        result = "ongoing"
    return {
        "result": result,
        "winner_side": bs.winner_side() if hasattr(bs, "winner_side") else None,
        "turns": _safe_int(getattr(bs, "turn", 0), 0),
        "cards_played": _safe_int(getattr(bs, "cards_played_total", 0), 0),
        "hp_a": VersusAI._get(bs.side(SIDE_A).combatant, "hp"),
        "hp_b": VersusAI._get(bs.side(SIDE_B).combatant, "hp"),
        "converged": result != V.RESULT_ONGOING,
    }
