"""钢铁战线 Steel Frontline — 战斗引擎。

严格实现 ARCHITECTURE.md 第 6 节与附录 A。

设计要点
--------
* 所有随机走 ``self.rng``（``random.Random`` 实例），可复现。
* 公开方法**绝不抛异常**给 UI；非法操作返回 False 并写入 ``self.log``。
* ``snapshot()`` 输出纯数据字典，UI 不接触内部对象。
* 战斗节奏协议（附录 A.6）：``end_turn()`` 不执行敌人行动，
  UI 每 400ms 调 ``enemy_step()`` 逐个推进。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core import cards as C
from core import enemies as E
from core import relics as R

# --------------------------------------------------------------------------
# Buff / Power 键（与 cards.py 保持一致）
# --------------------------------------------------------------------------
BUFF_STRENGTH = C.BUFF_STRENGTH
BUFF_DEXTERITY = C.BUFF_DEXTERITY
BUFF_VULNERABLE = C.BUFF_VULNERABLE
BUFF_WEAK = C.BUFF_WEAK
BUFF_FRAIL = C.BUFF_FRAIL
BUFF_POISON = C.BUFF_POISON
BUFF_THORNS = C.BUFF_THORNS
BUFF_METALLICIZE = C.BUFF_METALLICIZE
BUFF_RITUAL = C.BUFF_RITUAL
BUFF_ARTIFACT = C.BUFF_ARTIFACT
BUFF_PLATED_ARMOR = C.BUFF_PLATED_ARMOR
BUFF_REGENERATE = C.BUFF_REGENERATE
BUFF_INTANGIBLE = C.BUFF_INTANGIBLE
BUFF_STRENGTH_DOWN = C.BUFF_STRENGTH_DOWN
BUFF_BARRIER = C.BUFF_BARRIER
BUFF_CHAIN = C.BUFF_CHAIN
BUFF_ENVENOM = C.BUFF_ENVENOM
BUFF_ACCURACY = C.BUFF_ACCURACY

POWER_SHELLGUARD = C.POWER_SHELLGUARD
POWER_TIDEPOOL = C.POWER_TIDEPOOL
POWER_DEEP_CURRENT = C.POWER_DEEP_CURRENT
POWER_TIDAL_RESERVE = C.POWER_TIDAL_RESERVE
POWER_BARNACLE = C.POWER_BARNACLE
POWER_VENOM_ECHO = C.POWER_VENOM_ECHO
POWER_DEADWATER = C.POWER_DEADWATER
POWER_CORAL = C.POWER_CORAL
POWER_ABYSSAL_GATE = C.POWER_ABYSSAL_GATE
POWER_WHALE_SONG = C.POWER_WHALE_SONG
POWER_DEEP_ECHO = C.POWER_DEEP_ECHO
POWER_RITUAL_CHORUS = C.POWER_RITUAL_CHORUS
POWER_NECROTIDE = C.POWER_NECROTIDE

# 回合末不清空的 buff（正面持续）
_PERSISTENT_BUFFS = {
    BUFF_STRENGTH, BUFF_DEXTERITY, BUFF_THORNS, BUFF_METALLICIZE, BUFF_RITUAL,
    BUFF_ARTIFACT, BUFF_PLATED_ARMOR, BUFF_REGENERATE, BUFF_BARRIER,
    BUFF_CHAIN, BUFF_ENVENOM, BUFF_ACCURACY, BUFF_STRENGTH_DOWN,
}
# 回合末 -1 的 debuff
_DECAY_BUFFS = {BUFF_VULNERABLE, BUFF_WEAK, BUFF_FRAIL, BUFF_INTANGIBLE}

HAND_LIMIT = 10
MAX_LOG = 40

BUFF_NAMES = {
    BUFF_STRENGTH: "火力", BUFF_DEXTERITY: "机动", BUFF_VULNERABLE: "破甲",
    BUFF_WEAK: "压制", BUFF_FRAIL: "混乱", BUFF_POISON: "燃烧",
    BUFF_THORNS: "铁丝网", BUFF_METALLICIZE: "工事", BUFF_RITUAL: "增援",
    BUFF_ARTIFACT: "干扰弹", BUFF_PLATED_ARMOR: "装甲板", BUFF_REGENERATE: "战地医疗",
    BUFF_INTANGIBLE: "烟幕", BUFF_STRENGTH_DOWN: "弹药短缺", BUFF_BARRIER: "坚守",
    BUFF_CHAIN: "连射", BUFF_ENVENOM: "燃烧弹", BUFF_ACCURACY: "瞄准",
    POWER_SHELLGUARD: "甲壳工事", POWER_TIDEPOOL: "补给线", POWER_DEEP_CURRENT: "侦察网",
    POWER_TIDAL_RESERVE: "弹药储备", POWER_BARNACLE: "纵火", POWER_VENOM_ECHO: "燃烧回响",
    POWER_DEADWATER: "焦土", POWER_CORAL: "工事加固", POWER_ABYSSAL_GATE: "总攻令",
    POWER_WHALE_SONG: "协同作战", POWER_DEEP_ECHO: "炮火覆盖", POWER_RITUAL_CHORUS: "增援梯队",
    POWER_NECROTIDE: "焦土战术",
}

BUFF_DESCS = {
    BUFF_STRENGTH: "每层使攻击伤害 +1。",
    BUFF_DEXTERITY: "每层使获得的掩体 +1。",
    BUFF_VULNERABLE: "受到的攻击伤害 +50%，回合末 -1。",
    BUFF_WEAK: "造成的攻击伤害 -25%，回合末 -1。",
    BUFF_FRAIL: "获得的掩体 -25%，回合末 -1。",
    BUFF_POISON: "回合开始损失等同层数的生命，然后 -1。",
    BUFF_THORNS: "受到攻击时反弹等同层数的伤害。",
    BUFF_METALLICIZE: "回合结束获得等同层数的掩体。",
    BUFF_RITUAL: "回合结束获得等同层数的火力。",
    BUFF_ARTIFACT: "抵挡下一次负面效果。",
    BUFF_PLATED_ARMOR: "回合结束获得等同层数的格挡（不衰减）。",
    BUFF_REGENERATE: "回合结束回复等同层数的生命。",
    BUFF_INTANGIBLE: "受到的伤害降为 1，回合末 -1。",
    BUFF_STRENGTH_DOWN: "每层使攻击伤害 -1。",
    BUFF_BARRIER: "回合结束时格挡不清空。",
    BUFF_CHAIN: "本回合每打出一张牌，下一张攻击牌 +1 伤害。",
    BUFF_ENVENOM: "攻击牌造成伤害时，附加等同层数的中毒。",
    BUFF_ACCURACY: "召唤物的攻击伤害 +等同层数。",
}


# --------------------------------------------------------------------------
# 运行时对象
# --------------------------------------------------------------------------

@dataclass
class Minion:
    name: str
    hp: int
    max_hp: int
    attack: int
    block: int = 0
    alive: bool = True


@dataclass
class Combatant:
    """玩家或敌人的战斗态。"""
    is_player: bool
    name: str
    hp: int
    max_hp: int
    block: int = 0
    energy: int = 0
    max_energy: int = 3
    buffs: Dict[str, int] = field(default_factory=dict)
    powers: Dict[str, int] = field(default_factory=dict)
    # 玩家专属
    hand: List[C.CardInstance] = field(default_factory=list)
    draw_pile: List[C.CardInstance] = field(default_factory=list)
    discard_pile: List[C.CardInstance] = field(default_factory=list)
    exhaust_pile: List[C.CardInstance] = field(default_factory=list)
    relics: List[str] = field(default_factory=list)
    minions: List[Minion] = field(default_factory=list)
    # 敌人专属
    def_id: str = ""
    tier: str = "normal"
    idx: int = 0
    move_history: List[str] = field(default_factory=list)
    intent: Optional[Any] = None          # MoveDef，敌方回合开始前公示
    phase_index: int = 0                  # BOSS 阶段

    def alive(self) -> bool:
        return self.hp > 0

    # -- buff 便捷方法 ----------------------------------------------------
    def get_buff(self, key: str) -> int:
        return int(self.buffs.get(key, 0))

    def add_buff(self, key: str, amount: int) -> None:
        if amount == 0:
            return
        cur = int(self.buffs.get(key, 0)) + int(amount)
        if cur <= 0:
            self.buffs.pop(key, None)
        else:
            self.buffs[key] = cur

    def get_power(self, key: str) -> int:
        return int(self.powers.get(key, 0))

    def add_power(self, key: str, amount: int) -> None:
        cur = int(self.powers.get(key, 0)) + int(amount)
        if cur <= 0:
            self.powers.pop(key, None)
        else:
            self.powers[key] = cur


# --------------------------------------------------------------------------
# 卡牌效果上下文
# --------------------------------------------------------------------------

class CardContext:
    """传给 ``CardDef.effect`` 的上下文。所有卡牌效果只能用这里的方法。"""

    def __init__(self, battle: "BattleState", source: Combatant,
                 target: Optional[Combatant], card: C.CardInstance):
        self.battle = battle
        self.source = source
        self.target = target
        self.card = card

    # -- 基础 ------------------------------------------------------------
    def rng(self) -> random.Random:
        return self.battle.rng

    def enemies(self) -> List[Combatant]:
        return list(self.battle.enemies)

    def alive_enemies(self) -> List[Combatant]:
        return [e for e in self.battle.enemies if e.alive()]

    def all_combatants(self) -> List[Combatant]:
        return [self.battle.player] + list(self.battle.enemies)

    def cards_played_this_turn(self) -> int:
        return self.battle.cards_played_this_turn

    def pick_enemy(self) -> Optional[Combatant]:
        """目标为空（已死亡）时，自动改选一个存活敌人。"""
        if self.target is not None and self.target.alive():
            return self.target
        alive = self.alive_enemies()
        return alive[0] if alive else None

    # -- 数值 ------------------------------------------------------------
    def card_value(self, base: int, magic: bool = False) -> int:
        """取卡牌数值（已应用升级覆盖）。"""
        d = self.card.defn
        v = d.magic if magic else base
        return int(v)

    # -- 效果 ------------------------------------------------------------
    def deal_damage(self, amount, target=None, hits: int = 1, kind: str = "attack") -> int:
        t = target if target is not None else self.pick_enemy()
        if t is None or not t.alive():
            return 0
        total = 0
        for _ in range(max(1, int(hits))):
            if not t.alive():
                break
            total += self.battle.deal_damage(self.source, t, int(amount), kind=kind)
        return total

    def deal_damage_all(self, amount, hits: int = 1, kind: str = "attack") -> int:
        total = 0
        for e in self.alive_enemies():
            total += self.deal_damage(amount, e, hits=hits, kind=kind)
        return total

    def gain_block(self, amount, target=None) -> int:
        t = target if target is not None else self.source
        return self.battle.gain_block(t, int(amount))

    def apply_buff(self, key, amount, target=None) -> None:
        t = target if target is not None else self.pick_enemy()
        if t is None:
            return
        self.battle.apply_buff(t, key, int(amount))

    def apply_buff_all(self, key, amount) -> None:
        for e in self.alive_enemies():
            self.battle.apply_buff(e, key, int(amount))

    def apply_buff_self(self, key, amount) -> None:
        self.battle.apply_buff(self.source, key, int(amount))

    def draw(self, n) -> None:
        self.battle.draw_cards(self.source, int(n))

    def gain_energy(self, n) -> None:
        self.source.energy += int(n)

    def add_card_to_hand(self, def_id, upgraded=0, n=1, temp=True) -> None:
        self.battle.add_card_to_hand(def_id, upgraded=upgraded, n=int(n))

    def add_card_to_draw(self, def_id, n=1, upgraded=0) -> None:
        self.battle.add_card_to_draw(def_id, n=int(n), upgraded=upgraded)

    def add_card_to_discard(self, def_id, n=1, upgraded=0) -> None:
        self.battle.add_card_to_discard(def_id, n=int(n), upgraded=upgraded)

    def heal(self, n) -> None:
        self.battle.heal(self.source, int(n))

    def gain_max_hp(self, n) -> None:
        """提高总部血量上限（并同步回血）。

        用户要求「可以叠总部血量上限」。上限提升时**同时回等量的血**，
        否则上限涨了但当前血量没动，玩家感觉不到收益。
        """
        fn = getattr(self.battle, "gain_max_hp", None)
        if fn is None:
            return
        try:
            fn(self.source, int(n))
        except Exception:
            pass

    def lose_hp(self, n) -> None:
        self.battle.lose_hp(self.source, int(n))

    def summon(self, name, hp, attack) -> None:
        self.battle.summon(self.source, name, int(hp), int(attack))

    def summon_count(self) -> int:
        return len([m for m in self.source.minions if m.alive])

    def exhaust_random(self, n) -> None:
        self.battle.exhaust_random_from_hand(int(n))

    def discard_random(self, n) -> None:
        self.battle.discard_random_from_hand(int(n))

    def upgrade_hand(self, n: int = 99) -> int:
        return self.battle.upgrade_random_in_hand(int(n))

    def gain_power(self, key, amount) -> None:
        self.source.add_power(key, int(amount))

    def add_relic(self, relic_id) -> None:
        self.battle.add_relic_mid_run(relic_id)

    def gain_gold(self, n) -> None:
        self.battle.gold_gain += int(n)

    def x_value(self) -> int:
        """X 费卡牌的 X 值。"""
        return int(self.battle.x_spent)

    # 兼容别名（不同卡可能用不同命名）
    def block(self, amount, target=None) -> int:
        return self.gain_block(amount, target)

    def buff(self, key, amount, target=None) -> None:
        self.apply_buff(key, amount, target)

    def damage(self, amount, target=None, hits=1) -> int:
        return self.deal_damage(amount, target, hits=hits)


# --------------------------------------------------------------------------
# 战斗状态
# --------------------------------------------------------------------------

class BattleState:
    """一场战斗。"""

    def __init__(self, run, enemies: List[Combatant], rng: random.Random,
                 encounter: Optional[dict] = None):
        self.run = run
        self.rng = rng
        self.encounter = encounter or {}
        self.kind = self.encounter.get("kind", "normal")
        self.enemies: List[Combatant] = list(enemies or [])
        self.turn = 0
        self.phase = "player"
        self.log: List[str] = []
        self.cards_played_this_turn = 0
        self.cards_played_total = 0
        self.x_spent = 0
        self.gold_gain = 0
        self._relic_counters: Dict[str, int] = {}
        self._enemy_queue: List[Combatant] = []
        self.player = self._build_player(run)

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------
    def _build_player(self, run) -> Combatant:
        p = Combatant(
            is_player=True,
            name="装甲指挥官",
            hp=getattr(run, "hp", 70),
            max_hp=getattr(run, "max_hp", 70),
        )
        p.max_energy = 3
        p.relics = list(getattr(run, "relics", []) or [])
        deck = list(getattr(run, "deck", []) or [])
        # 深拷贝牌组，避免战斗修改污染 run.deck
        p.draw_pile = [c.clone() for c in deck]
        if not p.draw_pile:
            p.draw_pile = [C.make_card("strike"), C.make_card("strike"),
                           C.make_card("defend"), C.make_card("defend")]
        p.draw_pile.sort(key=lambda c: (not c.defn.innate, self.rng.random()))
        return p

    def log_msg(self, msg: str) -> None:
        self.log.append(str(msg))
        if len(self.log) > MAX_LOG:
            del self.log[:-MAX_LOG]

    # ------------------------------------------------------------------
    # 战斗开始
    # ------------------------------------------------------------------
    def start_battle(self) -> None:
        self.turn = 0
        self.phase = "player"
        for r in self.player.relics:
            self.fire_relic(r, R.TRIGGER_BATTLE_START)
        self._roll_enemy_intents()
        self._start_player_turn(first=True)

    def _start_player_turn(self, first: bool = False) -> None:
        p = self.player
        self.turn += 1
        self.cards_played_this_turn = 0
        # 格挡清空（屏障除外）
        if p.get_buff(BUFF_BARRIER) <= 0:
            p.block = 0
        else:
            p.add_buff(BUFF_BARRIER, -1)
        # 能量
        p.energy = p.max_energy + p.get_power(POWER_TIDEPOOL) + p.get_power(POWER_ABYSSAL_GATE)
        # 抽牌
        n = 5 + p.get_power(POWER_DEEP_CURRENT) + p.get_power(POWER_ABYSSAL_GATE)
        self.draw_cards(p, n)
        # 中毒结算：玩家与所有敌人在各自回合开始都结算
        self._tick_poison(p)
        for _en in list(self.enemies):
            if _en.alive():
                self._tick_poison(_en)
        if not any(x.alive() for x in self.enemies):
            self._check_end()
            return
        # 再生
        if p.get_buff(BUFF_REGENERATE) > 0:
            self.heal(p, p.get_buff(BUFF_REGENERATE))
        # 遗物
        self.fire_relic_all(R.TRIGGER_TURN_START)
        if not self.player.alive():
            self._check_end()

    def _tick_poison(self, c: Combatant) -> None:
        n = c.get_buff(BUFF_POISON)
        if n > 0:
            self.lose_hp(c, n, source=None)
            c.add_buff(BUFF_POISON, -1)

    # ------------------------------------------------------------------
    # 伤害管线
    # ------------------------------------------------------------------
    def calc_attack(self, source: Combatant, target: Combatant, base: int,
                    kind: str = "attack") -> int:
        """计算最终伤害（含力量/虚弱/易伤/连锁）。"""
        dmg = float(base)
        if kind == "attack":
            dmg += source.get_buff(BUFF_STRENGTH)
            dmg -= source.get_buff(BUFF_STRENGTH_DOWN)
            if source.get_buff(BUFF_WEAK) > 0:
                dmg *= 0.75
            if source.get_buff(BUFF_CHAIN) > 0:
                dmg += source.get_buff(BUFF_CHAIN)
            if target.get_buff(BUFF_VULNERABLE) > 0:
                dmg *= 1.5
        return max(0, int(dmg))

    def deal_damage(self, source: Combatant, target: Combatant, amount: int,
                    kind: str = "attack") -> int:
        """造成一次伤害，返回实际扣血量。"""
        if target is None or not target.alive():
            return 0
        if amount <= 0 and kind == "attack":
            return 0
        dmg = self.calc_attack(source, target, amount, kind=kind) if kind == "attack" else int(amount)
        if dmg <= 0:
            return 0
        # 无实体
        if target.get_buff(BUFF_INTANGIBLE) > 0:
            dmg = min(dmg, 1)
        # 格挡
        absorbed = min(target.block, dmg)
        target.block -= absorbed
        hp_loss = dmg - absorbed
        if hp_loss > 0:
            target.hp -= hp_loss
        # 遗物：受伤
        if target.is_player and dmg > 0:
            self.fire_relic_all(R.TRIGGER_ON_DAMAGE_TAKEN, amount=dmg)
        # 荆棘反伤
        if kind == "attack" and source is not None and source is not target:
            th = target.get_buff(BUFF_THORNS)
            if th > 0:
                self.lose_hp(source, th, source=target)
        # 淬毒
        if kind == "attack" and source is not None and source.get_buff(BUFF_ENVENOM) > 0 \
                and target is not source and target.alive():
            self.apply_buff(target, BUFF_POISON, source.get_buff(BUFF_ENVENOM))
        # 藤壶：玩家攻击牌命中后叠毒
        if kind == "attack" and source is not None and source.is_player \
                and source.get_power(POWER_BARNACLE) > 0 and target.alive():
            self.apply_buff(target, BUFF_POISON, source.get_power(POWER_BARNACLE))
        # 死亡处理
        if not target.alive():
            self._on_death(target)
        self._check_end()
        return dmg

    def lose_hp(self, target: Combatant, n: int, source: Optional[Combatant] = None) -> None:
        """直接损失生命（无视格挡）。"""
        if target is None or not target.alive() or n <= 0:
            return
        target.hp -= int(n)
        if target.is_player:
            self.fire_relic_all(R.TRIGGER_ON_DAMAGE_TAKEN, amount=int(n))
        if not target.alive():
            self._on_death(target)
        self._check_end()

    def gain_max_hp(self, target: Combatant, n: int) -> None:
        """提高血量上限，并同时回复等量的血量。"""
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
        if target.is_player:
            amount += target.get_buff(BUFF_DEXTERITY)
            amount += target.get_power(POWER_CORAL)
            if target.get_buff(BUFF_FRAIL) > 0:
                amount *= 0.75
        amount = max(0, int(amount))
        target.block += amount
        return amount

    def _on_death(self, c: Combatant) -> None:
        if c.is_player:
            self.log_msg("你倒下了……")
            return
        self.log_msg(f"{c.name} 被击败！")
        # 亡潮：召唤物死亡时玩家获得牌
        p = self.player
        if p.get_power(POWER_NECROTIDE) > 0:
            for _ in range(p.get_power(POWER_NECROTIDE)):
                self.add_card_to_discard("strike", n=1)
        self.fire_relic_all(R.TRIGGER_ON_KILL)

    # ------------------------------------------------------------------
    # buff
    # ------------------------------------------------------------------
    def apply_buff(self, target: Combatant, key: str, amount: int) -> None:
        if target is None or amount == 0:
            return
        negative = key in (BUFF_VULNERABLE, BUFF_WEAK, BUFF_FRAIL, BUFF_POISON,
                           BUFF_STRENGTH_DOWN)
        if negative and amount > 0 and target.get_buff(BUFF_ARTIFACT) > 0:
            target.add_buff(BUFF_ARTIFACT, -1)
            self.log_msg(f"{target.name} 的神器抵挡了效果。")
            return
        target.add_buff(key, amount)

    # ------------------------------------------------------------------
    # 牌堆操作
    # ------------------------------------------------------------------
    def draw_cards(self, who: Combatant, n: int) -> None:
        if not who.is_player:
            return
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

    def _new_temp_card(self, def_id: str, upgraded: int = 0) -> Optional[C.CardInstance]:
        try:
            return C.make_card(def_id, upgraded=upgraded)
        except Exception:
            return None

    def add_card_to_hand(self, def_id: str, upgraded: int = 0, n: int = 1) -> None:
        for _ in range(max(0, int(n))):
            if len(self.player.hand) >= HAND_LIMIT:
                break
            ci = self._new_temp_card(def_id, upgraded)
            if ci is not None:
                self.player.hand.append(ci)

    def add_card_to_draw(self, def_id: str, n: int = 1, upgraded: int = 0) -> None:
        for _ in range(max(0, int(n))):
            ci = self._new_temp_card(def_id, upgraded)
            if ci is not None:
                self.player.draw_pile.insert(self.rng.randrange(len(self.player.draw_pile) + 1), ci)

    def add_card_to_discard(self, def_id: str, n: int = 1, upgraded: int = 0) -> None:
        for _ in range(max(0, int(n))):
            ci = self._new_temp_card(def_id, upgraded)
            if ci is not None:
                self.player.discard_pile.append(ci)

    def exhaust_random_from_hand(self, n: int) -> None:
        for _ in range(max(0, int(n))):
            hand = self.player.hand
            if not hand:
                break
            i = self.rng.randrange(len(hand))
            card = hand.pop(i)
            card.cost_override = None
            self.player.exhaust_pile.append(card)

    def discard_random_from_hand(self, n: int) -> None:
        for _ in range(max(0, int(n))):
            hand = self.player.hand
            if not hand:
                break
            i = self.rng.randrange(len(hand))
            self.player.discard_pile.append(hand.pop(i))

    def upgrade_random_in_hand(self, n: int) -> int:
        cands = [c for c in self.player.hand if c.upgraded < 1 and c.is_upgradable]
        self.rng.shuffle(cands)
        cnt = 0
        for c in cands[:max(0, int(n))]:
            c.upgraded = 1
            cnt += 1
        return cnt

    def summon(self, owner: Combatant, name: str, hp: int, attack: int) -> None:
        owner.minions.append(Minion(name=name, hp=max(1, hp), max_hp=max(1, hp),
                                    attack=max(0, attack)))
        self.log_msg(f"{name} 加入了战斗！")

    def add_relic_mid_run(self, relic_id: str) -> None:
        if relic_id and relic_id not in self.player.relics:
            self.player.relics.append(relic_id)

    # ------------------------------------------------------------------
    # 遗物
    # ------------------------------------------------------------------
    def fire_relic_all(self, trigger: str, **kw) -> None:
        for rid in list(self.player.relics):
            self.fire_relic(rid, trigger, **kw)

    def fire_relic(self, relic_id: str, trigger: str, **kw) -> None:
        rdef = R.RELIC_DB.get(relic_id)
        if rdef is None or getattr(rdef, "trigger", None) != trigger:
            return
        self._relic_counters[relic_id] = self._relic_counters.get(relic_id, 0) + 1
        try:
            self._apply_relic_effect(relic_id, trigger, kw)
        except Exception:
            pass

    def _apply_relic_effect(self, relic_id: str, trigger: str, kw: dict) -> None:
        """内置遗物效果分发（按 id 匹配常见遗物）。"""
        p = self.player
        amt = int(kw.get("amount", 0))
        table = {
            "battle_start": {
                "anchor_shard": lambda: self.gain_block(p, 5),
                "tide_charm": lambda: self.apply_buff(p, BUFF_STRENGTH, 1),
            },
            "turn_start": {
                "barnacle_shell": lambda: self.gain_block(p, 3),
                "deep_lantern": lambda: self.draw_cards(p, 1),
            },
            "on_damage_taken": {
                "spine_urchin": lambda: self._relic_thorns(amt),
            },
        }
        fn = table.get(trigger, {}).get(relic_id)
        if fn:
            fn()

    def _relic_thorns(self, amt: int) -> None:
        alive = [e for e in self.enemies if e.alive()]
        if alive:
            self.lose_hp(alive[0], 2, source=self.player)

    # ------------------------------------------------------------------
    # 出牌
    # ------------------------------------------------------------------
    def can_play(self, card) -> bool:
        if card is None or self.phase != "player":
            return False
        ci = self._resolve_card(card)
        if ci is None:
            return False
        if ci not in self.player.hand:
            return False
        cost = self.card_cost(ci)
        if cost > self.player.energy:
            return False
        d = ci.defn
        if d.target == "enemy" and not any(e.alive() for e in self.enemies):
            return False
        if d.type == "curse" and not getattr(d, "playable_curse", False):
            return d.id in ("writhe",)
        return True

    def _resolve_card(self, card) -> Optional[C.CardInstance]:
        if isinstance(card, C.CardInstance):
            return card
        if isinstance(card, int):
            for c in self.player.hand:
                if c.uid == card:
                    return c
        return None

    def card_cost(self, ci: C.CardInstance) -> int:
        if ci.cost_override is not None:
            return int(ci.cost_override)
        cost = int(ci.cost)
        if cost < 0:                      # X 费
            return self.player.energy
        return cost

    def play_card(self, card, target=None) -> bool:
        if self.phase != "player":
            self.log_msg("现在不是你的回合。")
            return False
        ci = self._resolve_card(card)
        if ci is None or ci not in self.player.hand:
            self.log_msg("这张牌不在手牌中。")
            return False
        cost = self.card_cost(ci)
        if cost > self.player.energy:
            self.log_msg("能量不足。")
            return False
        if isinstance(target, int):
            target = self.enemies[target] if 0 <= target < len(self.enemies) else None
        d = ci.defn
        if d.target == "enemy":
            if target is None or not target.alive():
                alive = [e for e in self.enemies if e.alive()]
                if not alive:
                    self.log_msg("没有可以攻击的目标。")
                    return False
                target = alive[0]
        # 扣费
        self.player.energy -= cost
        self.x_spent = cost if int(ci.cost) < 0 else 0
        # 移出手牌
        try:
            self.player.hand.remove(ci)
        except ValueError:
            pass
        self.cards_played_this_turn += 1
        self.cards_played_total += 1
        self.log_msg(f"你打出了 {ci.display_name}")
        # 效果
        ctx = CardContext(self, self.player, target, ci)
        try:
            if d.effect is not None:
                d.effect(ctx)
        except Exception as exc:                      # 卡牌效果绝不拖垮战斗
            self.log_msg(f"[效果异常] {d.id}: {exc}")
        # 连锁：打出攻击牌后清空
        if d.type == "attack" and self.player.get_buff(BUFF_CHAIN) > 0:
            pass
        # 死水：每次攻击牌让全体中毒
        if d.type == "attack" and self.player.get_power(POWER_DEADWATER) > 0:
            for e in self.enemies:
                if e.alive():
                    self.apply_buff(e, BUFF_POISON, self.player.get_power(POWER_DEADWATER))
        # 遗物：出牌
        self.fire_relic_all(R.TRIGGER_ON_CARD_PLAYED)
        # 去处
        if d.exhaust:
            self.player.exhaust_pile.append(ci)
        elif d.type == "power":
            self.player.exhaust_pile.append(ci)
        else:
            self.player.discard_pile.append(ci)
        self._check_end()
        return True

    # ------------------------------------------------------------------
    # 回合结束 / 敌人行动
    # ------------------------------------------------------------------
    def end_turn(self) -> None:
        """只做回合末结算并切到 enemy phase，**不执行**敌人行动。"""
        if self.phase != "player":
            return
        p = self.player
        # 能力：壳甲 / 金属化 / 镀甲（玩家）
        shell = p.get_power(POWER_SHELLGUARD) + p.get_buff(BUFF_METALLICIZE) \
            + p.get_buff(BUFF_PLATED_ARMOR)
        if shell > 0:
            self.gain_block(p, shell)
        # 敌人同样享受 金属化 / 镀甲（否则敌人的工事类招式是废招）
        for _en in self.enemies:
            if not _en.alive():
                continue
            _eshell = _en.get_buff(BUFF_METALLICIZE) + _en.get_buff(BUFF_PLATED_ARMOR)
            if _eshell > 0:
                _en.block += _eshell
        # 协同作战：每个附属单位提供掩体
        ws = p.get_power(POWER_WHALE_SONG)
        if ws > 0:
            cnt = len([m for m in p.minions if m.alive])
            if cnt:
                self.gain_block(p, ws * cnt)
        # 炮火覆盖
        de = p.get_power(POWER_DEEP_ECHO)
        if de > 0:
            for e in self.enemies:
                if e.alive():
                    self.deal_damage(p, e, de, kind="other")
        # 仪式合唱
        rc = p.get_power(POWER_RITUAL_CHORUS)
        if rc > 0:
            p.add_buff(BUFF_RITUAL, rc)
        # 毒回响：按敌人中毒总量回血
        ve = p.get_power(POWER_VENOM_ECHO)
        if ve > 0:
            total = sum(e.get_buff(BUFF_POISON) for e in self.enemies if e.alive())
            if total > 0:
                self.heal(p, ve * total)
        # 再生
        if p.get_buff(BUFF_REGENERATE) > 0:
            self.heal(p, p.get_buff(BUFF_REGENERATE))
        # 仪式：玩家与敌人都要在回合末叠力量（契约 §3 ARCH_SUMMON）
        if p.get_buff(BUFF_RITUAL) > 0:
            p.add_buff(BUFF_STRENGTH, p.get_buff(BUFF_RITUAL))
        for _en in self.enemies:
            if _en.alive() and _en.get_buff(BUFF_RITUAL) > 0:
                _en.add_buff(BUFF_STRENGTH, _en.get_buff(BUFF_RITUAL))
        # 召唤物行动
        self._minions_act()
        # 遗物
        self.fire_relic_all(R.TRIGGER_TURN_END)
        # 手牌处理
        retain = p.get_power(POWER_TIDAL_RESERVE) > 0
        keep, toss = [], []
        for c in p.hand:
            if c.defn.ethereal:
                p.exhaust_pile.append(c)
            elif retain or c.defn.retain:
                keep.append(c)
            else:
                toss.append(c)
        p.hand = keep
        for c in toss:
            p.discard_pile.append(c)
        self._check_end()
        if self.phase in ("won", "lost"):
            return
        self.phase = "enemy"
        self._enemy_queue = [e for e in self.enemies if e.alive()]

    def _minions_act(self) -> None:
        p = self.player
        acc = p.get_buff(BUFF_ACCURACY)
        for m in p.minions:
            if not m.alive:
                continue
            m.block = 0
            alive = [e for e in self.enemies if e.alive()]
            if alive:
                tgt = alive[0]
                self.deal_damage(p, tgt, max(0, m.attack + acc), kind="other")

    def enemy_step(self) -> bool:
        """执行下一个敌人行动。返回 True 表示还有敌人待行动。"""
        if self.phase != "enemy":
            return False
        if self._check_end():
            return False
        # 取下一个仍存活的敌人
        while self._enemy_queue and not self._enemy_queue[0].alive():
            self._enemy_queue.pop(0)
        if not self._enemy_queue:
            self._end_enemy_phase()
            return False
        enemy = self._enemy_queue.pop(0)
        try:
            self._enemy_act(enemy)
        except Exception as exc:
            self.log_msg(f"[敌人异常] {enemy.name}: {exc}")
        if self._check_end():
            return False
        # 还有敌人待行动？
        while self._enemy_queue and not self._enemy_queue[0].alive():
            self._enemy_queue.pop(0)
        if self._enemy_queue:
            return True
        self._end_enemy_phase()
        return False

    def _end_enemy_phase(self) -> None:
        if self.phase in ("won", "lost"):
            return
        # debuff 衰减
        for c in [self.player] + list(self.enemies):
            if not c.alive():
                continue
            for key in _DECAY_BUFFS:
                if c.get_buff(key) > 0:
                    c.add_buff(key, -1)
        # 敌人格挡清空
        for e in self.enemies:
            e.block = 0
        self._roll_enemy_intents()
        self.phase = "player"
        self._start_player_turn()

    def _roll_enemy_intents(self) -> None:
        for e in self.enemies:
            if not e.alive():
                e.intent = None
                continue
            e.intent = self._choose_move(e)

    def _choose_move(self, enemy: Combatant):
        edef = E.ENEMY_DB.get(enemy.def_id)
        if edef is None or not edef.moves:
            return None
        # 自定义 AI 优先
        if getattr(edef, "ai", None) is not None:
            try:
                mv = edef.ai(enemy, self, self.turn)
                if mv is not None:
                    return mv
            except Exception:
                pass
        moves = list(edef.moves)
        hist = enemy.move_history
        # 禁止连续三次同一招
        if len(hist) >= 2 and hist[-1] == hist[-2]:
            banned = hist[-1]
            filtered = [m for m in moves if m.id != banned]
            if filtered:
                moves = filtered
        # 读局势加权
        weights = []
        for m in moves:
            w = 1.0
            if m.intent in ("defend", "attack_defend") and enemy.hp < enemy.max_hp * 0.4:
                w *= 3.0
            if m.intent in ("buff", "debuff") and enemy.hp > enemy.max_hp * 0.7:
                w *= 1.4
            if m.intent == "attack" and self.player.block > 8:
                w *= 0.6
            if hist and hist[-1] == m.id:
                w *= 0.25
            weights.append(max(0.01, w))
        try:
            return self.rng.choices(moves, weights=weights, k=1)[0]
        except Exception:
            return moves[0]

    def _enemy_act(self, enemy: Combatant) -> None:
        mv = enemy.intent or self._choose_move(enemy)
        if mv is None:
            return
        enemy.move_history.append(mv.id)
        if len(enemy.move_history) > 6:
            del enemy.move_history[:-6]
        enemy.intent = mv
        self.log_msg(f"{enemy.name} 使用了 {mv.name}")
        # 伤害
        hits = max(1, int(getattr(mv, "hits", 1)))
        dmg = int(getattr(mv, "damage", 0))
        if dmg > 0:
            for _ in range(hits):
                if not self.player.alive():
                    break
                self.deal_damage(enemy, self.player, dmg, kind="attack")
        # 格挡
        blk = int(getattr(mv, "block", 0))
        if blk > 0:
            enemy.block += blk
        # 效果
        fn = getattr(mv, "effect", None)
        if fn is not None:
            ctx = CardContext(self, enemy, self.player, None)
            ctx.enemy = enemy
            try:
                fn(ctx)
            except Exception as exc:
                self.log_msg(f"[意图异常] {mv.id}: {exc}")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def current_enemy_intent(self, enemy):
        if enemy is None:
            return None
        return enemy.intent

    def alive(self) -> bool:
        return self.player.alive()

    def result(self) -> str:
        if not self.player.alive():
            return "lost"
        if not any(e.alive() for e in self.enemies):
            return "won"
        return "ongoing"

    def _check_end(self) -> bool:
        if self.phase in ("won", "lost"):
            return True
        r = self.result()
        if r == "won":
            self.phase = "won"
            self.log_msg("战斗胜利！")
        elif r == "lost":
            self.phase = "lost"
        return self.phase in ("won", "lost")

    # ------------------------------------------------------------------
    # 快照（附录 A.2）
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        p = self.player

        def combatant_dto(c: Combatant) -> dict:
            return {
                "name": c.name, "hp": c.hp, "max_hp": c.max_hp,
                "block": c.block,
                "energy": c.energy, "max_energy": c.max_energy,
                "buffs": dict(c.buffs),
                "minions": [{"name": m.name, "hp": m.hp, "max_hp": m.max_hp,
                             "attack": m.attack, "block": m.block}
                            for m in c.minions if m.alive],
                "powers": dict(c.powers),
            }

        enemies = []
        for i, e in enumerate(self.enemies):
            mv = e.intent
            intent = None
            if mv is not None:
                raw = int(getattr(mv, "damage", 0))
                shown = self.calc_attack(e, p, raw, kind="attack") if raw > 0 else 0
                intent = {
                    "id": mv.id, "name": mv.name, "intent": mv.intent,
                    "damage": shown, "hits": int(getattr(mv, "hits", 1)),
                    "block": int(getattr(mv, "block", 0)),
                    "text": getattr(mv, "text", "") or "",
                }
            dto = combatant_dto(e)
            dto.update({"idx": i, "alive": e.alive(), "intent": intent})
            enemies.append(dto)

        hand = []
        for ci in p.hand:
            d = ci.defn
            hand.append({
                "uid": ci.uid, "def_id": ci.def_id, "name": ci.display_name,
                "cost": self.card_cost(ci), "type": d.type, "rarity": d.rarity,
                "arch": d.arch, "text": C.resolve_text(ci), "upgraded": ci.upgraded,
                "playable": self.can_play(ci),
                # 附录 A.2：牌堆长度别名冗余挂在每个 hand 元素上
                "draw_pile_len": len(p.draw_pile),
                "discard_pile_len": len(p.discard_pile),
                "exhaust_pile_len": len(p.exhaust_pile),
            })

        relics = []
        for rid in p.relics:
            rd = R.RELIC_DB.get(rid)
            if rd is None:
                continue
            relics.append({"id": rid, "name": rd.name, "text": rd.text,
                           "rarity": rd.rarity,
                           "counter": self._relic_counters.get(rid, -1)})

        pdto = combatant_dto(p)
        snap = {
            "turn": self.turn, "phase": self.phase,
            "player": pdto, "enemies": enemies, "hand": hand,
            "draw_count": len(p.draw_pile), "discard_count": len(p.discard_pile),
            "exhaust_count": len(p.exhaust_pile),
            "relics": relics, "log": list(self.log[-MAX_LOG:]),
            "cards_played_this_turn": self.cards_played_this_turn,
            # 附录 A.2 别名兜底
            "draw_pile_len": len(p.draw_pile),
            "discard_pile_len": len(p.discard_pile),
            "exhaust_pile_len": len(p.exhaust_pile),
            "gold_gain": self.gold_gain,
        }
        return snap


# --------------------------------------------------------------------------
# 构造入口（附录 A.1）
# --------------------------------------------------------------------------

def make_enemy_combatant(def_id: str, rng: random.Random,
                         ascension: int = 0, act: int = 1) -> Combatant:
    edef = E.ENEMY_DB.get(def_id)
    if edef is None:
        edef = E.ENEMY_DB.get("deep_crab")
    if edef is None:
        return Combatant(is_player=False, name=def_id or "未知生物", hp=20, max_hp=20)
    hp = rng.randint(int(edef.hp_min), max(int(edef.hp_max), int(edef.hp_min)))
    # 飞升加成
    hp = int(hp * (1.0 + 0.02 * max(0, ascension)))
    if ascension >= 10:
        hp = int(hp * 1.05)
    c = Combatant(is_player=False, name=edef.name, hp=max(1, hp), max_hp=max(1, hp))
    c.def_id = def_id
    c.tier = getattr(edef, "tier", "normal")
    return c


def make_battle(run, encounter: dict) -> BattleState:
    """UI 唯一使用的战斗创建入口。"""
    encounter = encounter or {}
    kind = encounter.get("kind", "normal")
    ids = encounter.get("enemies") or []
    rng = getattr(run, "rng", None) or random.Random()
    asc = int(getattr(run, "ascension", 0) or 0)
    act = int(getattr(run, "act", 1) or 1)
    if not ids:
        pool = E.ENCOUNTERS.get(act, {}).get(kind) or []
        if pool:
            pick = pool[rng.randrange(len(pool))]
            ids = pick.get("enemies", []) if isinstance(pick, dict) else list(pick)
    if not ids:
        ids = ["deep_crab"]
    enemies = [make_enemy_combatant(i, rng, asc, act) for i in ids]
    b = BattleState(run, enemies, rng, {"kind": kind, "enemies": ids})
    b.start_battle()
    return b


# 兼容别名
Battle = BattleState
