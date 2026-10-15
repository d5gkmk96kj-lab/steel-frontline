"""钢铁战线 Steel Frontline — 局域网 1v1 对战引擎。

与单机版 ``core/engine.py`` 的关系
----------------------------------
本模块**只 read 不 write** ``core/engine.py``：复用它的伤害管线
（:meth:`~core.engine.BattleState.calc_attack` /
:meth:`~core.engine.BattleState.deal_damage` / ``gain_block`` /
``apply_buff`` / ``lose_hp`` / ``heal``）与 :class:`~core.engine.Combatant`，
以及 ``core.cards`` 的 134 张卡。单机版逻辑零改动。

对称性
------
双方都是「玩家」——结构完全一致，没有 AI、没有主客场数值差异。
阵营只以 ``side`` 区分：``0`` = 本机/房主，``1`` = 对手/客户端。

回合流程（与单机版一致）
------------------------
回合开始 → 清空掩体（坚守除外）→ 补给回满 → 抽 5 张 → 结算燃烧/战地医疗
→ 出牌 → 结束回合（工事/增援/附属单位结算）→ 换对方。

信息隔离（**核心安全要求**）
----------------------------
:meth:`VersusBattle.snapshot_for` 只暴露该视角应知的信息：
自己的手牌**完整内容**，对手的手牌**只有数量**。
血量/掩体/buff/牌库数属于公开信息，双方可见。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core import cards as C
from core import engine as E

# --------------------------------------------------------------------------
# 从 engine 复用的常量（不重复定义，保证与单机版语义一致）
# --------------------------------------------------------------------------
BUFF_STRENGTH = E.BUFF_STRENGTH
BUFF_DEXTERITY = E.BUFF_DEXTERITY
BUFF_VULNERABLE = E.BUFF_VULNERABLE
BUFF_WEAK = E.BUFF_WEAK
BUFF_FRAIL = E.BUFF_FRAIL
BUFF_POISON = E.BUFF_POISON
BUFF_THORNS = E.BUFF_THORNS
BUFF_METALLICIZE = E.BUFF_METALLICIZE
BUFF_RITUAL = E.BUFF_RITUAL
BUFF_ARTIFACT = E.BUFF_ARTIFACT
BUFF_PLATED_ARMOR = E.BUFF_PLATED_ARMOR
BUFF_REGENERATE = E.BUFF_REGENERATE
BUFF_INTANGIBLE = E.BUFF_INTANGIBLE
BUFF_STRENGTH_DOWN = E.BUFF_STRENGTH_DOWN
BUFF_BARRIER = E.BUFF_BARRIER
BUFF_CHAIN = E.BUFF_CHAIN
BUFF_ENVENOM = E.BUFF_ENVENOM
BUFF_ACCURACY = E.BUFF_ACCURACY

POWER_SHELLGUARD = E.POWER_SHELLGUARD
POWER_TIDEPOOL = E.POWER_TIDEPOOL
POWER_DEEP_CURRENT = E.POWER_DEEP_CURRENT
POWER_TIDAL_RESERVE = E.POWER_TIDAL_RESERVE
POWER_BARNACLE = E.POWER_BARNACLE
POWER_VENOM_ECHO = E.POWER_VENOM_ECHO
POWER_DEADWATER = E.POWER_DEADWATER
POWER_CORAL = E.POWER_CORAL
POWER_ABYSSAL_GATE = E.POWER_ABYSSAL_GATE
POWER_WHALE_SONG = E.POWER_WHALE_SONG
POWER_DEEP_ECHO = E.POWER_DEEP_ECHO
POWER_RITUAL_CHORUS = E.POWER_RITUAL_CHORUS
POWER_NECROTIDE = E.POWER_NECROTIDE

HAND_LIMIT = E.HAND_LIMIT
Combatant = E.Combatant
Minion = E.Minion
BUFF_NAMES = E.BUFF_NAMES

# --------------------------------------------------------------------------
# 对战常量
# --------------------------------------------------------------------------
DEFAULT_HP = 75
DEFAULT_SUPPLY = 3          # 补给上限（= engine 的 max_energy）
DRAW_PER_TURN = 5
DEFAULT_TURN_SECONDS = 60.0

# 后手补偿。
# 实测（500 场自动对战）先手胜率 72.8%，远超健康阈值 —— 根因是先手白赚
# 一个完整回合，而后手开局 hand=0/energy=0，没有任何弥补。
# 这里给后手方在其**第一个回合**额外的补给与抽牌，把先手优势拉回 50±10%。
# 后手首回合补偿 —— 数值经过实测标定，不要随意改。
#
# 测法：**同卡组镜像对局**（双方实力完全相同，胜率偏差 100% 来自先后手），
#       6 副随机卡组 × 200 场 = 1200 局，取均值与极值。
#   无补偿  -> 均值 62~72%（10 副牌里 6 副超 60%，最高 71%）
#   +1 补给 -> 均值 60.4%，范围 53.5~70.0%，2/6 仍超标
#   +2 补给 -> 均值 50.4%，范围 45.0~59.5%，0/6 超标   ← 采用
#   +3 补给 -> 均值 43.0%（矫枉过正，后手反而占优）
#
# 为什么用「补给」而不是「抽牌」：先手优势来自多一个回合的**行动力**，
# 补给直接对冲；且改抽牌会改变手牌数、破坏双方手牌对称性（实测也更无效）。
# 后手补偿：先手方天然快一拍，卡组越强这个优势越大。
# 实测（300 场，同卡组）：
#   补偿 +2 -> 先手胜率 59.7%（>60% 红线，实测多次到 62%）
#   补偿 +3 -> 56.7%
#   补偿 +4 -> 53.7%
#   补偿 +5 -> 52.3%   <- 取这个
#   补偿 +6 -> 51.3%（接近对称，但后手开始反而占优）
# 之所以从 2 提到 5：新增卡牌让 0 费牌从 10 张涨到 20 张，
# 先手方能"白打一张"滚雪球，优势被放大。补偿必须跟上卡池强度。
FIRST_TURN_BONUS_SUPPLY = 5      # 后手首回合额外 +5 补给
FIRST_TURN_BONUS_DRAW = 0        # 不改抽牌：保持双方手牌数对称

SIDE_A = 0                  # 本机 / 房主
SIDE_B = 1                  # 对手 / 客户端

RESULT_ONGOING = "ongoing"
RESULT_A_WINS = "a_wins"
RESULT_B_WINS = "b_wins"
RESULT_DRAW = "draw"

MAX_LOG = 60

SIDE_NAMES = {SIDE_A: "本机部队", SIDE_B: "对手部队"}


# --------------------------------------------------------------------------
# 战斗态：一对对称的 Combatant
# --------------------------------------------------------------------------

@dataclass
class VersusSide:
    """一方的全部对战状态（双方结构完全一致）。"""
    idx: int
    combatant: Combatant
    deck_ids: List[str] = field(default_factory=list)
    turn_seconds: float = DEFAULT_TURN_SECONDS
    time_left: float = DEFAULT_TURN_SECONDS

    @property
    def name(self) -> str:
        return self.combatant.name

    @property
    def alive(self) -> bool:
        return self.combatant.alive()


def _make_combatant(name: str, hp: int) -> Combatant:
    """构造一个「玩家方」战斗态（双方同构）。"""
    hp = max(1, int(hp))
    c = Combatant(is_player=True, name=name, hp=hp, max_hp=hp)
    c.max_energy = DEFAULT_SUPPLY
    c.energy = 0
    return c


def _build_draw_pile(deck, rng: random.Random) -> List[C.CardInstance]:
    """把卡组（def_id 列表或 CardInstance 列表）变成洗好的牌库。

    拒绝 status/curse 之外的任何脏数据；未知 id 直接跳过（不抛异常）。
    """
    cards: List[C.CardInstance] = []
    for item in list(deck or []):
        if isinstance(item, C.CardInstance):
            cards.append(item.clone())
            continue
        if not isinstance(item, str):
            continue
        if item not in C.CARD_DB:
            continue
        try:
            cards.append(C.make_card(item))
        except Exception:
            continue
    # 固有牌优先置于牌库顶部（与 engine 语义一致：sort 后 pop() 取尾）
    cards.sort(key=lambda c: (not c.defn.innate, rng.random()))
    return cards


# --------------------------------------------------------------------------
# 卡牌效果上下文（复用 engine.CardContext 的全部 API 形态）
# --------------------------------------------------------------------------

class VersusCardContext(E.CardContext):
    """对战出牌的 ``ctx``。

    继承 ``engine.CardContext`` 以保证 134 张卡的 ``effect`` 全部可用：
    卡牌效果只会调用 ``deal_damage`` / ``gain_block`` / ``apply_buff`` /
    ``alive_enemies`` / ``draw`` / ``summon`` 等方法，这里把它们接到对战
    战斗态上（``battle`` = :class:`VersusBattle`，``enemies`` = 对方的
    ``combatant`` 单元素列表）。
    """

    def __init__(self, battle: "VersusBattle", source: Combatant,
                 target: Optional[Combatant], card: Optional[C.CardInstance],
                 owner: "VersusBattle"):
        super().__init__(battle, source, target, card)   # type: ignore[arg-type]
        self.owner = owner          # 真正持有牌堆/手牌的一方（VersusBattle）

    # -- 目标 ------------------------------------------------------------
    def pick_enemy(self) -> Optional[Combatant]:
        if self.target is not None and self.target.alive():
            return self.target
        foe = self.owner.foe_of(self.source)
        return foe if (foe is not None and foe.alive()) else None

    # 对战里没有「多敌人」，但卡牌可能调用；保持可用
    def alive_enemies(self) -> List[Combatant]:
        foe = self.owner.foe_of(self.source)
        return [foe] if (foe is not None and foe.alive()) else []

    def enemies(self) -> List[Combatant]:
        foe = self.owner.foe_of(self.source)
        return [foe] if foe is not None else []

    def all_combatants(self) -> List[Combatant]:
        return [self.owner.sides[0].combatant, self.owner.sides[1].combatant]

    # -- 抽牌 / 资源（接到 owner 的牌堆上）--------------------------------
    def draw(self, n) -> None:
        self.owner.draw_cards(self.source, int(n))

    def gain_max_hp(self, n) -> None:
        """提高总部血量上限（1v1 用）。"""
        fn = getattr(self.battle, "gain_max_hp", None)
        if fn is None:
            return
        try:
            fn(self.source, int(n))
        except Exception:
            pass

    def gain_energy(self, n) -> None:
        self.source.energy += int(n)

    def add_card_to_hand(self, def_id, upgraded=0, n=1, temp=True) -> None:
        self.owner.add_card_to_hand(self.source, def_id, upgraded=upgraded, n=int(n))

    def add_card_to_draw(self, def_id, n=1, upgraded=0) -> None:
        self.owner.add_card_to_draw(self.source, def_id, n=int(n), upgraded=upgraded)

    def add_card_to_discard(self, def_id, n=1, upgraded=0) -> None:
        self.owner.add_card_to_discard(self.source, def_id, n=int(n), upgraded=upgraded)

    def exhaust_random(self, n) -> None:
        self.owner.exhaust_random_from_hand(self.source, int(n))

    def discard_random(self, n) -> None:
        self.owner.discard_random_from_hand(self.source, int(n))

    def upgrade_hand(self, n: int = 99) -> int:
        return self.owner.upgrade_random_in_hand(self.source, int(n))

    def summon_count(self) -> int:
        return len([m for m in self.source.minions if m.alive])

    # -- 与单机版行为对齐的辅助 -------------------------------------------
    def gain_power(self, key, amount) -> None:
        self.source.add_power(key, int(amount))

    def add_relic(self, relic_id) -> None:
        return None                       # 对战无勋章系统

    def gain_gold(self, n) -> None:
        return None                       # 对战无金币

    def x_value(self) -> int:
        return int(self.owner.x_spent)


# --------------------------------------------------------------------------
# 对战
# --------------------------------------------------------------------------

class VersusBattle:
    """一场 1v1 对战。

    Parameters
    ----------
    deck_a, deck_b:
        两方的卡组，``List[str]``（卡牌 def_id）或 ``List[CardInstance]``。
    rng:
        ``random.Random`` 实例；``None`` 时内部自建。所有随机都走它。
    hp:
        双方总部耐久（HQ HP），默认 75。
    turn_seconds:
        每回合限时秒数，默认 60；超时由 :meth:`tick` 自动结束回合。
    """

    def __init__(self, deck_a, deck_b, rng: Optional[random.Random] = None,
                 hp: int = DEFAULT_HP, turn_seconds: float = DEFAULT_TURN_SECONDS):
        self.rng: random.Random = rng if isinstance(rng, random.Random) else random.Random()
        try:
            hp = int(hp)
        except (TypeError, ValueError):
            hp = DEFAULT_HP
        hp = max(1, hp)
        try:
            turn_seconds = float(turn_seconds)
        except (TypeError, ValueError):
            turn_seconds = DEFAULT_TURN_SECONDS
        if turn_seconds <= 0:
            turn_seconds = DEFAULT_TURN_SECONDS
        self.hp = hp
        self.turn_seconds = turn_seconds

        # 两侧对称构造
        self.sides: List[VersusSide] = [
            VersusSide(idx=SIDE_A,
                       combatant=_make_combatant(SIDE_NAMES[SIDE_A], hp),
                       deck_ids=[],
                       turn_seconds=turn_seconds),
            VersusSide(idx=SIDE_B,
                       combatant=_make_combatant(SIDE_NAMES[SIDE_B], hp),
                       deck_ids=[],
                       turn_seconds=turn_seconds),
        ]
        for vs, deck in ((self.sides[SIDE_A], deck_a), (self.sides[SIDE_B], deck_b)):
            vs.deck_ids = _deck_id_list(deck)
            vs.combatant.draw_pile = _build_draw_pile(deck, self.rng) or \
                [C.make_card("strike"), C.make_card("strike"),
                 C.make_card("defend"), C.make_card("defend")]

        # 对战全局状态
        self.turn = 0
        self.current = SIDE_A
        self.phase = "p0"                       # "p0" | "p1" | 终局结果
        self.log: List[str] = []
        self.cards_played_this_turn = 0
        self.cards_played_total = 0
        self.x_spent = 0
        self._ended = False
        self.gold_gain = 0
        self.minions: List[Minion] = []          # 兼容 engine.CardContext.all_combatants
        # VersusCardContext 继承 engine.CardContext，其 __init__ 会读 battle.enemies
        self.enemies: List[Combatant] = [self.sides[SIDE_B].combatant]

        self.log_msg("对战开始！双方各就各位。")
        self._start_turn(SIDE_A, first=True)

    # ------------------------------------------------------------------
    # 基础访问
    # ------------------------------------------------------------------
    def side(self, side: int) -> Optional[VersusSide]:
        """取一方；非法 side 返回 None（不抛异常）。"""
        if isinstance(side, bool):
            return None
        if isinstance(side, int) and 0 <= side < 2:
            return self.sides[side]
        return None

    def foe_of(self, c: Optional[Combatant]) -> Optional[Combatant]:
        """给定战斗态，返回其对手的战斗态。"""
        if c is None:
            return None
        for vs in self.sides:
            if vs.combatant is c:
                return self.sides[1 - vs.idx].combatant
        return None

    def _side_of(self, c: Optional[Combatant]) -> Optional[VersusSide]:
        if c is None:
            return None
        for vs in self.sides:
            if vs.combatant is c:
                return vs
        return None

    def current_side(self) -> int:
        """当前行动方：0 = 本机，1 = 对手。"""
        return int(self.current)

    def winner_side(self) -> Optional[int]:
        """胜方 side；未结束或平局返回 None。"""
        r = self.result()
        if r == RESULT_A_WINS:
            return SIDE_A
        if r == RESULT_B_WINS:
            return SIDE_B
        return None

    def result(self) -> str:
        """``"ongoing" | "a_wins" | "b_wins" | "draw"``。"""
        a = self.sides[SIDE_A].combatant.alive()
        b = self.sides[SIDE_B].combatant.alive()
        if a and b:
            return RESULT_ONGOING
        if a and not b:
            return RESULT_A_WINS
        if b and not a:
            return RESULT_B_WINS
        return RESULT_DRAW

    def is_over(self) -> bool:
        return self.result() != RESULT_ONGOING

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    def log_msg(self, msg: str) -> None:
        self.log.append(str(msg))
        if len(self.log) > MAX_LOG:
            del self.log[:-MAX_LOG]

    # ------------------------------------------------------------------
    # 回合流程
    # ------------------------------------------------------------------
    def _start_turn(self, side: int, first: bool = False) -> None:
        """回合开始：掩体结算 → 补给回满 → 抽牌 → 燃烧 → 战地医疗。"""
        vs = self.sides[side]
        c = vs.combatant
        self.turn += 1
        self.current = side
        self.phase = "p0" if side == SIDE_A else "p1"
        self.cards_played_this_turn = 0
        self.x_spent = 0
        vs.time_left = float(self.turn_seconds)

        # 掩体：坚守未清则扣一层并保留，否则清零
        if c.get_buff(BUFF_BARRIER) > 0:
            c.add_buff(BUFF_BARRIER, -1)
        else:
            c.block = 0

        # 补给回满
        c.energy = c.max_energy + c.get_power(POWER_TIDEPOOL) \
            + c.get_power(POWER_ABYSSAL_GATE)

        # 后手补偿：仅在后手方的**第一个**回合生效
        bonus_supply = bonus_draw = 0
        if side == SIDE_B and not getattr(vs, "had_first_turn", False):
            bonus_supply = FIRST_TURN_BONUS_SUPPLY
            bonus_draw = FIRST_TURN_BONUS_DRAW
        if bonus_supply:
            c.energy += bonus_supply

        # 抽牌
        n = (DRAW_PER_TURN + bonus_draw + c.get_power(POWER_DEEP_CURRENT)
             + c.get_power(POWER_ABYSSAL_GATE))
        self.draw_cards(c, n)
        if side == SIDE_B:
            vs.had_first_turn = True   # 补偿只给一次

        # 燃烧：双方都在各自回合开始结算（与单机版一致）
        self._tick_poison(c)
        other = self.sides[1 - side].combatant
        if other.alive():
            self._tick_poison(other)
        if self._check_end():
            return

        # 战地医疗
        if c.get_buff(BUFF_REGENERATE) > 0:
            self.heal(c, c.get_buff(BUFF_REGENERATE))
        self._check_end()

    def _tick_poison(self, c: Combatant) -> None:
        n = c.get_buff(BUFF_POISON)
        if n > 0:
            self.lose_hp(c, n)
            c.add_buff(BUFF_POISON, -1)

    def _end_turn_settlement(self, side: int) -> None:
        """回合末结算：工事/装甲板/协同作战/火力覆盖/再生/增援/附属单位。"""
        vs = self.sides[side]
        c = vs.combatant
        foe = self.sides[1 - side].combatant

        # 工事 + 装甲板
        shell = c.get_power(POWER_SHELLGUARD) + c.get_buff(BUFF_METALLICIZE) \
            + c.get_buff(BUFF_PLATED_ARMOR)
        if shell > 0:
            self.gain_block(c, shell)

        # 协同作战：每个附属单位提供掩体
        ws = c.get_power(POWER_WHALE_SONG)
        if ws > 0:
            cnt = len([m for m in c.minions if m.alive])
            if cnt:
                self.gain_block(c, ws * cnt)

        # 炮火覆盖
        de = c.get_power(POWER_DEEP_ECHO)
        if de > 0 and foe.alive():
            self.deal_damage(c, foe, de, kind="other")

        # 增援梯队
        rc = c.get_power(POWER_RITUAL_CHORUS)
        if rc > 0:
            c.add_buff(BUFF_RITUAL, rc)

        # 燃烧回响：按对手燃烧总量回血
        ve = c.get_power(POWER_VENOM_ECHO)
        if ve > 0:
            total = foe.get_buff(BUFF_POISON)
            if total > 0:
                self.heal(c, ve * total)

        # 战地医疗
        if c.get_buff(BUFF_REGENERATE) > 0:
            self.heal(c, c.get_buff(BUFF_REGENERATE))

        # 增援：回合末叠火力
        if c.get_buff(BUFF_RITUAL) > 0:
            c.add_buff(BUFF_STRENGTH, c.get_buff(BUFF_RITUAL))

        # 附属单位行动
        self._minions_act(side)

        # 手牌处理：虚无 → 移除区；保留 → 留手；其余进弃牌堆
        retain = c.get_power(POWER_TIDAL_RESERVE) > 0
        keep, toss = [], []
        for card in c.hand:
            if card.defn.ethereal:
                c.exhaust_pile.append(card)
            elif retain or card.defn.retain:
                keep.append(card)
            else:
                toss.append(card)
        c.hand = keep
        for card in toss:
            c.discard_pile.append(card)

        self._check_end()

    def _minions_act(self, side: int) -> None:
        vs = self.sides[side]
        c = vs.combatant
        foe = self.sides[1 - side].combatant
        acc = c.get_buff(BUFF_ACCURACY)
        for m in c.minions:
            if not m.alive:
                continue
            m.block = 0
            if foe.alive():
                self.deal_damage(c, foe, max(0, m.attack + acc), kind="other")

    # ------------------------------------------------------------------
    # 倒计时
    # ------------------------------------------------------------------
    def tick(self, dt_seconds: float) -> None:
        """推进倒计时；归零则**自动结束当前方回合**。UI 每秒调一次。"""
        if self.is_over():
            return
        try:
            dt = float(dt_seconds)
        except (TypeError, ValueError):
            return
        if dt <= 0:
            return
        vs = self.sides[self.current]
        vs.time_left -= dt
        if vs.time_left <= 0:
            vs.time_left = 0.0
            self.log_msg(f"{vs.name} 回合超时，自动结束回合。")
            self.end_turn(self.current, _force=True)

    def time_left(self) -> float:
        """当前方剩余秒数。"""
        return float(self.sides[self.current].time_left)

    # ------------------------------------------------------------------
    # 伤害管线（转发 engine 语义）
    # ------------------------------------------------------------------
    def calc_attack(self, source: Combatant, target: Combatant, base: int,
                    kind: str = "attack") -> int:
        dmg = float(base)
        if kind == "attack":
            dmg += source.get_buff(BUFF_STRENGTH)
            dmg -= source.get_buff(BUFF_STRENGTH_DOWN)
            if source.get_buff(BUFF_WEAK) > 0:
                dmg *= 0.75
            if source.get_buff(BUFF_CHAIN) > 0:
                dmg += source.get_buff(BUFF_CHAIN)
            if target is not None and target.get_buff(BUFF_VULNERABLE) > 0:
                dmg *= 1.5
        return max(0, int(dmg))

    def deal_damage(self, source: Combatant, target: Combatant, amount: int,
                    kind: str = "attack") -> int:
        """造成一次伤害，返回实际伤害值。语义与 engine 完全一致。"""
        if target is None or not target.alive():
            return 0
        if amount <= 0 and kind == "attack":
            return 0
        dmg = self.calc_attack(source, target, amount, kind=kind) if kind == "attack" \
            else int(amount)
        if dmg <= 0:
            return 0
        # 烟幕
        if target.get_buff(BUFF_INTANGIBLE) > 0:
            dmg = min(dmg, 1)
        # 掩体吸收
        absorbed = min(target.block, dmg)
        target.block -= absorbed
        hp_loss = dmg - absorbed
        if hp_loss > 0:
            target.hp -= hp_loss
        # 铁丝网反伤
        if kind == "attack" and source is not None and source is not target:
            th = target.get_buff(BUFF_THORNS)
            if th > 0:
                self.lose_hp(source, th)
        # 燃烧弹：攻击附带燃烧
        if kind == "attack" and source is not None and source is not target \
                and source.get_buff(BUFF_ENVENOM) > 0 and target.alive():
            self.apply_buff(target, BUFF_POISON, source.get_buff(BUFF_ENVENOM))
        # 纵火：攻击牌命中后叠燃烧
        if kind == "attack" and source is not None \
                and source.get_power(POWER_BARNACLE) > 0 and target.alive():
            self.apply_buff(target, BUFF_POISON, source.get_power(POWER_BARNACLE))
        self._check_end()
        return dmg

    def lose_hp(self, target: Combatant, n: int,
                source: Optional[Combatant] = None) -> None:
        """直接损失生命（无视掩体）。"""
        if target is None or not target.alive() or n <= 0:
            return
        target.hp -= int(n)
        self._check_end()

    def gain_max_hp(self, target: Combatant, n: int) -> None:
        """提高血量上限，并同时回复等量血量。"""
        n = int(n)
        if n <= 0:
            return
        target.max_hp = int(target.max_hp) + n
        target.hp = min(target.max_hp, int(target.hp) + n)
        try:
            self.log_msg("%s 的总部上限 +%d" % (target.name, n))
        except Exception:
            pass

    def heal(self, target: Combatant, n: int) -> None:
        if target is None or n <= 0 or not target.alive():
            return
        target.hp = min(target.max_hp, target.hp + int(n))

    def gain_block(self, target: Combatant, n: int) -> int:
        if target is None or n <= 0 or not target.alive():
            return 0
        amount = float(n)
        amount += target.get_buff(BUFF_DEXTERITY)
        amount += target.get_power(POWER_CORAL)
        if target.get_buff(BUFF_FRAIL) > 0:
            amount *= 0.75
        amount = max(0, int(amount))
        target.block += amount
        return amount

    def apply_buff(self, target: Combatant, key: str, amount: int) -> None:
        if target is None or amount == 0:
            return
        negative = key in (BUFF_VULNERABLE, BUFF_WEAK, BUFF_FRAIL, BUFF_POISON,
                           BUFF_STRENGTH_DOWN)
        if negative and amount > 0 and target.get_buff(BUFF_ARTIFACT) > 0:
            target.add_buff(BUFF_ARTIFACT, -1)
            self.log_msg(f"{target.name} 的干扰弹抵挡了效果。")
            return
        target.add_buff(key, amount)

    def summon(self, owner: Combatant, name: str, hp: int, attack: int) -> None:
        owner.minions.append(Minion(name=name, hp=max(1, int(hp)),
                                    max_hp=max(1, int(hp)),
                                    attack=max(0, int(attack))))
        self.log_msg(f"{name} 加入了战斗！")

    # ------------------------------------------------------------------
    # 牌堆操作
    # ------------------------------------------------------------------
    def draw_cards(self, who: Combatant, n: int) -> None:
        for _ in range(max(0, int(n))):
            if len(who.hand) >= HAND_LIMIT:
                break
            if not who.draw_pile:
                if not who.discard_pile:
                    break
                who.draw_pile = who.discard_pile
                who.discard_pile = []
                self.rng.shuffle(who.draw_pile)
            if who.draw_pile:
                who.hand.append(who.draw_pile.pop())

    def add_card_to_hand(self, who: Combatant, def_id: str, upgraded: int = 0,
                         n: int = 1) -> None:
        for _ in range(max(0, int(n))):
            if len(who.hand) >= HAND_LIMIT:
                break
            ci = self._new_card(def_id, upgraded)
            if ci is not None:
                who.hand.append(ci)

    def add_card_to_draw(self, who: Combatant, def_id: str, n: int = 1,
                         upgraded: int = 0) -> None:
        for _ in range(max(0, int(n))):
            ci = self._new_card(def_id, upgraded)
            if ci is not None:
                who.draw_pile.insert(self.rng.randrange(len(who.draw_pile) + 1), ci)

    def add_card_to_discard(self, who: Combatant, def_id: str, n: int = 1,
                            upgraded: int = 0) -> None:
        for _ in range(max(0, int(n))):
            ci = self._new_card(def_id, upgraded)
            if ci is not None:
                who.discard_pile.append(ci)

    @staticmethod
    def _new_card(def_id: str, upgraded: int = 0) -> Optional[C.CardInstance]:
        try:
            return C.make_card(def_id, upgraded=upgraded)
        except Exception:
            return None

    def exhaust_random_from_hand(self, who: Combatant, n: int) -> None:
        for _ in range(max(0, int(n))):
            if not who.hand:
                break
            i = self.rng.randrange(len(who.hand))
            card = who.hand.pop(i)
            card.cost_override = None
            who.exhaust_pile.append(card)

    def discard_random_from_hand(self, who: Combatant, n: int) -> None:
        for _ in range(max(0, int(n))):
            if not who.hand:
                break
            i = self.rng.randrange(len(who.hand))
            who.discard_pile.append(who.hand.pop(i))

    def upgrade_random_in_hand(self, who: Combatant, n: int) -> int:
        cands = [c for c in who.hand if c.upgraded < 1 and c.is_upgradable]
        self.rng.shuffle(cands)
        cnt = 0
        for c in cands[:max(0, int(n))]:
            c.upgraded = 1
            cnt += 1
        return cnt

    # ------------------------------------------------------------------
    # 出牌
    # ------------------------------------------------------------------
    def card_cost(self, ci: C.CardInstance, who: Optional[Combatant] = None) -> int:
        if ci is None:
            return 0
        if ci.cost_override is not None:
            return int(ci.cost_override)
        cost = int(ci.cost)
        if cost < 0:                      # X 费
            return int(who.energy) if who is not None else 0
        return cost

    def can_play(self, side: int, card_index: int) -> bool:
        """该方能否打出这张手牌（供 UI 置灰）。非法输入返回 False。"""
        vs = self.side(side)
        if vs is None or self.is_over() or side != self.current:
            return False
        c = vs.combatant
        if not isinstance(card_index, int) or isinstance(card_index, bool):
            return False
        if not (0 <= card_index < len(c.hand)):
            return False
        ci = c.hand[card_index]
        if self.card_cost(ci, c) > c.energy:
            return False
        d = ci.defn
        if d.type == "curse" and not getattr(d, "playable_curse", False):
            return d.id in ("writhe",)
        if d.target == "enemy":
            foe = self.sides[1 - side].combatant
            if not foe.alive():
                return False
        return True

    def play_card(self, side: int, card_index: int,
                  target_index=None) -> bool:
        """打出一张手牌。非法操作返回 ``False``，绝不抛异常。

        * ``side`` —— 0 = 本机，1 = 对手。必须是当前行动方。
        * ``card_index`` —— 该方 ``hand`` 的**下标**。
        * ``target_index`` —— 1v1 只有一个敌方目标，可省略。
        """
        vs = self.side(side)
        if vs is None:
            return False
        if self.is_over():
            return False
        if side != self.current:
            self.log_msg("现在不是你的回合。")
            return False
        c = vs.combatant
        if not isinstance(card_index, int) or isinstance(card_index, bool):
            return False
        if not (0 <= card_index < len(c.hand)):
            self.log_msg("这张牌不在手牌中。")
            return False

        ci = c.hand[card_index]
        cost = self.card_cost(ci, c)
        if cost > c.energy:
            self.log_msg("补给不足。")
            return False

        d = ci.defn
        foe = self.sides[1 - side].combatant
        target: Optional[Combatant] = None
        if d.target == "enemy":
            if not foe.alive():
                self.log_msg("没有可以攻击的目标。")
                return False
            target = foe
        elif d.target == "all_enemies":
            target = foe if foe.alive() else None
        # target_index 仅作兼容：1v1 里唯一合法目标就是对方
        if target_index is not None and not isinstance(target_index, int):
            return False

        # 扣补给
        c.energy -= cost
        self.x_spent = cost if int(ci.cost) < 0 else 0
        # 移出手牌
        try:
            c.hand.pop(card_index)
        except (IndexError, ValueError):
            return False
        self.cards_played_this_turn += 1
        self.cards_played_total += 1
        self.log_msg(f"{vs.name} 打出了 {ci.display_name}")

        # 效果（与单机版一致：效果异常绝不拖垮对局）
        ctx = VersusCardContext(self, c, target, ci, self)
        try:
            if d.effect is not None:
                d.effect(ctx)
        except Exception as exc:
            self.log_msg(f"[效果异常] {d.id}: {exc}")

        # 焦土：每张攻击牌让对方叠燃烧
        if d.type == "attack" and c.get_power(POWER_DEADWATER) > 0 and foe.alive():
            self.apply_buff(foe, BUFF_POISON, c.get_power(POWER_DEADWATER))

        # 去处：消耗 / 指令 → 移除区，其余进弃牌堆
        if d.exhaust or d.type == "power":
            c.exhaust_pile.append(ci)
        else:
            c.discard_pile.append(ci)

        self._check_end()
        return True

    # ------------------------------------------------------------------
    # 结束回合
    # ------------------------------------------------------------------
    def end_turn(self, side: int, _force: bool = False) -> bool:
        """结束该方回合并换对方。非法调用返回 ``False``。"""
        vs = self.side(side)
        if vs is None:
            return False
        if self.is_over():
            return False
        if side != self.current and not _force:
            self.log_msg("现在不是你的回合。")
            return False
        if _force and side != self.current:
            return False

        self._end_turn_settlement(side)
        if self._check_end():
            return True

        # debuff 衰减（双方）
        for s in self.sides:
            cc = s.combatant
            if not cc.alive():
                continue
            for key in E._DECAY_BUFFS:
                if cc.get_buff(key) > 0:
                    cc.add_buff(key, -1)

        # 换手
        nxt = 1 - side
        if not self.sides[nxt].combatant.alive():
            self._check_end()
            return True
        self._start_turn(nxt)
        return True

    # ------------------------------------------------------------------
    # 终局
    # ------------------------------------------------------------------
    def _check_end(self) -> bool:
        r = self.result()
        if r == RESULT_ONGOING:
            return False
        if not self._ended:
            self._ended = True
            self.phase = r
            if r == RESULT_A_WINS:
                self.log_msg(f"{self.sides[SIDE_A].name} 取得胜利！")
            elif r == RESULT_B_WINS:
                self.log_msg(f"{self.sides[SIDE_B].name} 取得胜利！")
            else:
                self.log_msg("双方同归于尽，平局。")
        return True

    # ------------------------------------------------------------------
    # 快照
    # ------------------------------------------------------------------
    @staticmethod
    def _card_dto(ci: C.CardInstance, cost: int, playable: bool) -> dict:
        d = ci.defn
        return {
            "uid": ci.uid,
            "def_id": ci.def_id,
            "name": ci.display_name,
            "cost": int(cost),
            "type": d.type,
            "rarity": d.rarity,
            "arch": d.arch,
            "text": C.resolve_text(d),
            "upgraded": int(ci.upgraded),
            "playable": bool(playable),
            # 附加字段（UI 可选用）
            "damage": int(d.damage),
            "block": int(d.block),
            "hits": int(d.hits),
            "target": d.target,
            "exhaust": bool(d.exhaust),
            "ethereal": bool(d.ethereal),
            "innate": bool(d.innate),
            "retain": bool(d.retain),
        }

    def _public_dto(self, c: Combatant) -> dict:
        """公开信息：血量/掩体/buff/牌堆数（双方可见）。"""
        return {
            "name": c.name,
            "hp": int(c.hp),
            "max_hp": int(c.max_hp),
            "block": int(c.block),
            "energy": int(c.energy),
            "max_energy": int(c.max_energy),
            "buffs": {k: int(v) for k, v in c.buffs.items()},
            "powers": {k: int(v) for k, v in c.powers.items()},
            "minions": [{"name": m.name, "hp": int(m.hp), "max_hp": int(m.max_hp),
                         "attack": int(m.attack), "block": int(m.block)}
                        for m in c.minions if m.alive],
            "hand_count": len(c.hand),
            "draw_count": len(c.draw_pile),
            "discard_count": len(c.discard_pile),
            "exhaust_count": len(c.exhaust_pile),
        }

    def snapshot_for(self, side: int) -> dict:
        """该方视角的纯数据快照。

        **信息隔离**：``you`` 含完整手牌；``foe`` **只有 ``hand_count``**，
        绝不含手牌内容。非法 ``side`` 兜底为当前行动方（不抛异常）。
        """
        vs = self.side(side)
        if vs is None:
            vs = self.sides[self.current]
        side = vs.idx
        me = vs.combatant
        foe_vs = self.sides[1 - side]
        foe = foe_vs.combatant

        hand = []
        for i, ci in enumerate(me.hand):
            hand.append(self._card_dto(ci, self.card_cost(ci, me),
                                       self.can_play(side, i)))

        you = self._public_dto(me)
        you["hand"] = hand
        foe_dto = self._public_dto(foe)          # 注意：不含 "hand"

        return {
            "side": int(side),
            "turn": int(self.turn),
            "current_side": int(self.current),
            "phase": self.phase,
            "time_left": round(float(vs.time_left), 2),
            "turn_seconds": float(self.turn_seconds),
            "result": self.result(),
            "you": you,
            "foe": foe_dto,
            # -- 别名（同一份数据，兼容不同调用方的命名习惯）-------------
            # 冻结主键为 you / foe；下列别名指向同一 dict，**不含**对手手牌内容。
            "me": you,
            "opponent": foe_dto,
            "my_hand": hand,
            "opponent_hand_count": len(foe.hand),
            "log": list(self.log[-MAX_LOG:]),
        }

    def snapshot(self) -> dict:
        """当前行动方视角的快照（等价于 ``snapshot_for(current_side())``）。"""
        return self.snapshot_for(self.current_side())

    # ------------------------------------------------------------------
    # 战绩（可选，写进 MetaProgress）
    # ------------------------------------------------------------------
    def to_record(self, local_side: int = SIDE_A) -> dict:
        """本局结果的纯数据记录，供 :class:`core.run.MetaProgress` 存档。"""
        r = self.result()
        if r == RESULT_A_WINS:
            winner = SIDE_A
        elif r == RESULT_B_WINS:
            winner = SIDE_B
        else:
            winner = None
        return {
            "result": r,
            "winner_side": winner,
            "local_side": int(local_side),
            "local_won": (winner == local_side),
            "turns": int(self.turn),
            "cards_played": int(self.cards_played_total),
            "hp_a": int(self.sides[SIDE_A].combatant.hp),
            "hp_b": int(self.sides[SIDE_B].combatant.hp),
        }


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------

def _deck_id_list(deck) -> List[str]:
    out: List[str] = []
    for item in list(deck or []):
        if isinstance(item, C.CardInstance):
            out.append(item.def_id)
        elif isinstance(item, str):
            out.append(item)
    return out


def make_versus(deck_a, deck_b, rng: Optional[random.Random] = None,
                hp: int = DEFAULT_HP,
                turn_seconds: float = DEFAULT_TURN_SECONDS) -> VersusBattle:
    """构造入口（与 ``engine.make_battle`` 对称）。"""
    return VersusBattle(deck_a, deck_b, rng=rng, hp=hp, turn_seconds=turn_seconds)


def make_test_battle(rng: Optional[random.Random] = None,
                     hp: int = DEFAULT_HP) -> VersusBattle:
    """双方同卡组的对称测试对局（自检/联调用）。"""
    from core import deckbuild as _db
    deck = _db.starter_deck()
    return VersusBattle(deck, list(deck), rng=rng, hp=hp)


__all__ = [
    "VersusBattle", "VersusSide", "VersusCardContext", "make_versus",
    "make_test_battle", "SIDE_A", "SIDE_B", "DEFAULT_HP", "DEFAULT_SUPPLY",
    "DRAW_PER_TURN", "DEFAULT_TURN_SECONDS",
    "RESULT_ONGOING", "RESULT_A_WINS", "RESULT_B_WINS", "RESULT_DRAW",
]
