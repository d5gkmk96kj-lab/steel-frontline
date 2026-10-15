# -*- coding: utf-8 -*-
"""钢铁战线 Steel Frontline —— 卡牌数据库。

严格遵循 ARCHITECTURE.md 第 3 节：

* ``CardDef`` / ``CardInstance`` 字段名与契约完全一致。
* 每个 ``effect`` 签名一律 ``fn(ctx)``，只调用 ARCHITECTURE.md 第 6 节
  ``CardContext`` 上列出的公开方法，绝不访问未定义属性。
* 所有随机走 ``ctx.rng()``。
* ``text`` 中的 ``{damage}`` / ``{block}`` / ``{magic}`` / ``{magic2}`` /
  ``{hits}`` 占位符由 :func:`resolve_text` 用实例上的真实数值替换，
  升级后的文案也会自动跟随。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

RARITY_BASIC, RARITY_COMMON, RARITY_UNCOMMON, RARITY_RARE = "basic", "common", "uncommon", "rare"

ARCH_ATTACK = "attack"    # 强攻：高伤、火力
ARCH_BLOCK = "block"      # 铁壁：护甲、铁丝网
ARCH_POISON = "poison"    # 蚀骨：燃烧、减益
ARCH_ENERGY = "energy"    # 后勤：补给、抽牌、连射
ARCH_SUMMON = "summon"    # 唤灵：附属单位、持续输出

ARCHS = (ARCH_ATTACK, ARCH_BLOCK, ARCH_POISON, ARCH_ENERGY, ARCH_SUMMON)

# Buff / power 字符串键（与 ARCHITECTURE.md 第 6 节 BUFF_* 完全一致）
BUFF_STRENGTH = "strength"
BUFF_DEXTERITY = "dexterity"
BUFF_VULNERABLE = "vulnerable"
BUFF_WEAK = "weak"
BUFF_FRAIL = "frail"
BUFF_POISON = "poison"
BUFF_THORNS = "thorns"
BUFF_METALLICIZE = "metallicize"
BUFF_RITUAL = "ritual"
BUFF_ARTIFACT = "artifact"
BUFF_PLATED_ARMOR = "plated_armor"
BUFF_REGENERATE = "regenerate"
BUFF_INTANGIBLE = "intangible"
BUFF_STRENGTH_DOWN = "strength_down"
BUFF_BARRIER = "barrier"
BUFF_CHAIN = "chain"
BUFF_ENVENOM = "envenom"
BUFF_ACCURACY = "accuracy"

# 纯「能力牌计数器」键（挂在 Combatant.powers 上，引擎按回合推送效果）
POWER_SHELLGUARD = "shellguard"          # 回合末获得掩体
POWER_TIDEPOOL = "tidepool"              # 每回合额外补给
POWER_DEEP_CURRENT = "deep_current"      # 每回合额外抽牌
POWER_TIDAL_RESERVE = "tidal_reserve"    # 回合末保留手牌
POWER_BARNACLE = "barnacle"              # 攻击牌命中后叠燃烧
POWER_VENOM_ECHO = "venom_echo"          # 回合末按敌人身上的燃烧回血
POWER_DEADWATER = "deadwater"            # 每次打出攻击牌，全体敌人燃烧
POWER_CORAL = "coral"                    # 每次获得掩体时额外 +N
POWER_ABYSSAL_GATE = "abyssal_gate"      # 每回合额外补给 + 抽牌
POWER_WHALE_SONG = "whale_song"          # 回合末每个附属单位为你提供掩体
POWER_DEEP_ECHO = "deep_echo"            # 每回合末对所有敌人造成固定伤害
POWER_RITUAL_CHORUS = "ritual_chorus"    # 每回合末获得增援
POWER_NECROTIDE = "necrotide"            # 附属单位死亡时向弃牌堆加入牌

# 附属单位名（纯粹用于 UI 显示）
MINION_WHALE_CALF = "步兵班"
MINION_GULL = "侦察机"
MINION_SQUID = "机枪组"
MINION_JELLY = "迫击炮组"
MINION_ANGLER = "反坦克组"
MINION_CRAB = "装甲车"
MINION_LEVIATHAN = "重型坦克"


# --------------------------------------------------------------------------
# 数据类
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CardDef:
    id: str                 # 唯一 snake_case
    name: str               # 中文名
    cost: int               # -1 表示 X 费
    type: str               # "attack" | "skill" | "power" | "status" | "curse"
    rarity: str
    arch: str               # ARCH_*
    text: str               # 描述，用 {damage} {block} 等占位
    target: str             # "enemy" | "self" | "all_enemies" | "none"
    # 效果：fn(ctx) -> None，ctx 为 CardContext
    effect: Optional[Callable[[Any], None]] = None
    exhaust: bool = False           # 移除
    ethereal: bool = False          # 不稳固：回合结束未打出则移除
    innate: bool = False            # 固有：起手必在手牌
    retain: bool = False            # 保留：回合结束不弃
    upgrade: Optional[dict] = None  # 升级后覆盖的字段，如 {"cost":0,"damage":12}
    damage: int = 0                 # 基础伤害（供 UI 与升级计算）
    block: int = 0
    magic: int = 0                  # 通用数值槽（燃烧层数等）
    magic2: int = 0
    hits: int = 1                   # 攻击段数
    keywords: tuple = ()            # 关键词，用于图鉴筛选


def make_card(def_id: str, upgraded: int = 0, uid: Optional[int] = None) -> "CardInstance":
    """构造一张实际持有的牌。uid 省略时用全局自增计数器。"""
    if uid is None:
        uid = _next_uid()
    return CardInstance(uid=uid, def_id=def_id, upgraded=1 if upgraded else 0)


_UID_COUNTER = [0]


def _next_uid() -> int:
    _UID_COUNTER[0] += 1
    return _UID_COUNTER[0]


_VALID_TYPES = ("attack", "skill", "power", "status", "curse")
_VALID_TARGETS = ("enemy", "self", "all_enemies", "none")


# 缺失 id 的安全占位卡（防止数据错误导致运行时崩溃）
def _placeholder_card(def_id: str) -> CardDef:
    """当 CARD_DB 缺失某个 id 时返回的占位卡：0 费、无效果、不可升级。"""
    try:
        return CardDef(
            id=str(def_id), name="失效指令", cost=0, type="skill",
            rarity=RARITY_COMMON, arch=ARCH_ENERGY,
            text="（数据缺失，此牌无效果）", target="none",
            effect=None, keywords=("占位",),
        )
    except Exception:
        # 极端兜底：连 CardDef 都构造失败时，用最小合法定义重试一次
        return CardDef(
            id="__placeholder__", name="失效指令", cost=0, type="skill",
            rarity=RARITY_COMMON, arch=ARCH_ENERGY,
            text="（数据缺失）", target="none", effect=None,
        )


class CardInstance:
    """一张实际持有的牌（可变：升级、本场临时改费）。"""

    __slots__ = ("uid", "def_id", "upgraded", "cost_override")

    def __init__(self, uid: int, def_id: str, upgraded: int = 0,
                 cost_override: Optional[int] = None) -> None:
        self.uid = uid
        self.def_id = def_id
        self.upgraded = 0 if not upgraded else 1
        self.cost_override = cost_override

    # ---- 便捷只读属性 -------------------------------------------------
    @property
    def defn(self) -> CardDef:
        """已应用升级覆盖的 CardDef。

        防御性设计：若 def_id 在 CARD_DB 中缺失（数据打字错误等），
        返回一张安全占位卡而不是抛 KeyError —— 任何数据错误都不应让玩家崩游戏。
        """
        base = CARD_DB.get(self.def_id)
        if base is None:
            base = _placeholder_card(self.def_id)
        if not self.upgraded or not base.upgrade:
            return base
        try:
            from dataclasses import replace as _dc_replace
            return _dc_replace(base, **base.upgrade)
        except Exception:
            return base

    @property
    def base_def(self) -> CardDef:
        """未升级的原始 CardDef（同样做缺失兜底）。"""
        return CARD_DB.get(self.def_id) or _placeholder_card(self.def_id)

    @property
    def name(self) -> str:
        return self.defn.name

    @property
    def cost(self) -> int:
        if self.cost_override is not None:
            return self.cost_override
        return self.defn.cost

    @property
    def text(self) -> str:
        return resolve_text(self.defn)

    @property
    def type(self) -> str:
        return self.defn.type

    @property
    def rarity(self) -> str:
        return self.defn.rarity

    @property
    def arch(self) -> str:
        return self.defn.arch

    @property
    def damage(self) -> int:
        return self.defn.damage

    @property
    def block(self) -> int:
        return self.defn.block

    @property
    def magic(self) -> int:
        return self.defn.magic

    @property
    def magic2(self) -> int:
        return self.defn.magic2

    @property
    def hits(self) -> int:
        return self.defn.hits

    @property
    def target(self) -> str:
        return self.defn.target

    @property
    def is_upgradable(self) -> bool:
        return bool(self.base_def.upgrade)

    @property
    def display_name(self) -> str:
        return self.name + "+" if self.upgraded else self.name

    # ---- 序列化 -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "def_id": self.def_id,
            "upgraded": self.upgraded,
            "cost_override": self.cost_override,
        }

    @staticmethod
    def from_dict(d: dict) -> "CardInstance":
        return CardInstance(
            uid=int(d.get("uid", _next_uid())),
            def_id=d["def_id"],
            upgraded=int(d.get("upgraded", 0)),
            cost_override=d.get("cost_override", None),
        )

    def clone(self, new_uid: bool = False) -> "CardInstance":
        return CardInstance(
            uid=_next_uid() if new_uid else self.uid,
            def_id=self.def_id,
            upgraded=self.upgraded,
            cost_override=self.cost_override,
        )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return "<CardInstance %s%s uid=%d>" % (self.def_id, "+" if self.upgraded else "", self.uid)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CardInstance):
            return NotImplemented
        return (self.uid, self.def_id, self.upgraded, self.cost_override) == (
            other.uid, other.def_id, other.upgraded, other.cost_override)

    def __hash__(self) -> int:
        return hash((self.uid, self.def_id, self.upgraded, self.cost_override))


def resolve_text(defn: CardDef, translate: bool = False) -> str:
    """把 text 里的 {damage}/{block}/{magic}/{magic2}/{hits} 换成真实数值。

    只用替换不用 str.format，避免中文描述里出现字面花括号时炸掉。

    ``translate=True`` 时会**先翻译模板再填数值** —— 顺序很重要：
    填完数值后字符串是「造成 6 点伤害。」这种具体文案，已经不在翻译表里了。
    """
    out = defn.text
    if translate:
        try:
            from core import i18n as _i18n
            out = _i18n.t(out)
        except Exception:
            pass
    mapping = {
        "{damage}": str(defn.damage),
        "{block}": str(defn.block),
        "{magic}": str(defn.magic),
        "{magic2}": str(defn.magic2),
        "{hits}": str(defn.hits),
    }
    for k, v in mapping.items():
        if k in out:
            out = out.replace(k, v)
    return out


# --------------------------------------------------------------------------
# effect 小工具：只使用 CardContext 公开方法，且对可选方法做防御性探测
# --------------------------------------------------------------------------

def _apply(ctx, key: str, amount: int, target=None) -> None:
    fn = getattr(ctx, "apply_buff", None)
    if fn is None:
        return
    fn(key, amount, target)


def _aoe(ctx, key: str, amount: int) -> None:
    for e in ctx.alive_enemies():
        _apply(ctx, key, amount, e)


def _hit(ctx, amount, target=None, hits: int = 1):
    return ctx.deal_damage(amount, target, hits)


def _block(ctx, amount, target=None) -> int:
    return ctx.gain_block(amount, target)


def _draw(ctx, n: int) -> None:
    fn = getattr(ctx, "draw", None)
    if fn is not None and n > 0:
        fn(n)


def _energy(ctx, n: int) -> None:
    fn = getattr(ctx, "gain_energy", None)
    if fn is not None and n:
        fn(n)


def _add_hand(ctx, def_id: str, n: int = 1, upgraded: int = 0) -> None:
    fn = getattr(ctx, "add_card_to_hand", None)
    if fn is None or n <= 0:
        return
    try:
        fn(def_id, upgraded=upgraded, n=n, temp=True)
    except TypeError:  # pragma: no cover - 兼容只有 fn(def_id, n) 的老签名
        fn(def_id, n)


def _add_draw(ctx, def_id: str, n: int = 1) -> None:
    fn = getattr(ctx, "add_card_to_draw", None)
    if fn is not None and n > 0:
        fn(def_id, n)


def _heal(ctx, n: int) -> None:
    fn = getattr(ctx, "heal", None)
    if fn is not None and n > 0:
        fn(n)


def _lose_hp(ctx, n: int) -> None:
    fn = getattr(ctx, "lose_hp", None)
    if fn is not None and n > 0:
        fn(n)


def _summon(ctx, name: str, hp: int, attack: int) -> None:
    fn = getattr(ctx, "summon", None)
    if fn is not None:
        fn(name, hp, attack)


def _exhaust_random(ctx, n: int) -> None:
    fn = getattr(ctx, "exhaust_random", None)
    if fn is not None and n > 0:
        fn(n)


def _rng(ctx) -> random.Random:
    return ctx.rng()


def _played(ctx) -> int:
    fn = getattr(ctx, "cards_played_this_turn", None)
    return int(fn()) if fn is not None else 0


def _power(ctx, key: str, amount: int) -> None:
    """给 source 挂一个纯计数器 power。"""
    p = getattr(ctx.source, "powers", None)
    if p is None:
        return
    p[key] = p.get(key, 0) + amount


def _has_power(ctx, key: str) -> bool:
    p = getattr(ctx.source, "powers", None)
    return bool(p) and p.get(key, 0) > 0


def _aoe_damage(ctx, amount) -> None:
    for e in ctx.alive_enemies():
        ctx.deal_damage(amount, e)


def _self_damage(ctx, amount) -> None:
    """自伤：走 lose_hp，无视掩体。"""
    _lose_hp(ctx, amount)


def _buff_amount(ctx, key: str, target=None) -> int:
    tgt = target if target is not None else ctx.source
    b = getattr(tgt, "buffs", None)
    return int(b.get(key, 0)) if b else 0


# --------------------------------------------------------------------------
# 效果函数
# --------------------------------------------------------------------------

def _x_cost(n_per: int = 1, cap: int = 99) -> Callable[[Any], None]:
    """X 费卡：按本回合剩余补给结算。"""
    def fx(ctx) -> None:
        eng = int(getattr(ctx.source, "energy", 0))
        n = max(0, min(eng, cap))
        if n <= 0:
            return
        ctx.deal_damage(n * n_per, ctx.target)
    return fx


def _x_block(n_per: int = 1, cap: int = 99) -> Callable[[Any], None]:
    def fx(ctx) -> None:
        eng = int(getattr(ctx.source, "energy", 0))
        n = max(0, min(eng, cap))
        if n <= 0:
            return
        ctx.gain_block(n * n_per, ctx.target)
    return fx


# ---- 强攻 / 火力 ---------------------------------------------------------

def fx_strike(ctx) -> None:
    ctx.deal_damage(6, ctx.target)


def fx_heavy_harpoon(ctx) -> None:
    ctx.deal_damage(14, ctx.target)


def fx_twin_fang(ctx) -> None:
    ctx.deal_damage(5, ctx.target, hits=2)


def fx_cleave(ctx) -> None:
    for e in ctx.alive_enemies():
        ctx.deal_damage(8, e)


def fx_ram_charge(ctx) -> None:
    ctx.deal_damage(10, ctx.target)
    ctx.gain_block(5)


def fx_rending_bite(ctx) -> None:
    ctx.deal_damage(7, ctx.target)
    _apply(ctx, BUFF_VULNERABLE, 2, ctx.target)


def fx_whale_charge(ctx) -> None:
    ctx.deal_damage(9, ctx.target)
    _apply(ctx, BUFF_STRENGTH, 2, ctx.source)


def fx_inflame(ctx) -> None:
    _apply(ctx, BUFF_STRENGTH, 2, ctx.source)
    ctx.gain_block(5)


def fx_limit_break(ctx) -> None:
    cur = _buff_amount(ctx, BUFF_STRENGTH)
    _apply(ctx, BUFF_STRENGTH, cur, ctx.source)


def fx_reaper_scythe(ctx) -> None:
    _aoe_damage(ctx, 4)
    _apply(ctx, BUFF_STRENGTH, 3, ctx.source)


def fx_frenzy(ctx) -> None:
    n = _played(ctx)
    ctx.deal_damage(8 + n * 3, ctx.target)


def fx_hold_the_line(ctx) -> None:
    ctx.deal_damage(7 + _buff_amount(ctx, BUFF_STRENGTH), ctx.target)


def fx_cross_slash(ctx) -> None:
    ctx.deal_damage(7 + _played(ctx) * 2, ctx.target)
    ctx.deal_damage(7 + _played(ctx) * 2, ctx.target)


def fx_recall(ctx) -> None:
    ctx.deal_damage(6, ctx.target)
    _add_hand(ctx, "tide_knot")


def fx_sweeping_blow(ctx) -> None:
    ctx.deal_damage(12, ctx.target)
    _apply(ctx, BUFF_STRENGTH_DOWN, 3, ctx.target)


def fx_whirlpool(ctx) -> None:
    for _ in range(3):
        for e in ctx.alive_enemies():
            ctx.deal_damage(5, e)


def fx_armor_piercer(ctx) -> None:
    ctx.deal_damage(9, ctx.target)
    b = getattr(ctx.target, "block", 0) if ctx.target is not None else 0
    for e in ctx.alive_enemies():
        e.block = 0
    if b:
        ctx.deal_damage(min(b, 8), ctx.target)


def fx_cold_current(ctx) -> None:
    for e in ctx.alive_enemies():
        ctx.deal_damage(6, e)
        _apply(ctx, BUFF_WEAK, 1, e)


def fx_double_strike(ctx) -> None:
    ctx.deal_damage(6, ctx.target, hits=2)


def fx_toxin_uppercut(ctx) -> None:
    ctx.deal_damage(8, ctx.target)
    _apply(ctx, BUFF_VULNERABLE, 3, ctx.target)


def fx_hammerhead(ctx) -> None:
    ctx.deal_damage(11, ctx.target)
    if getattr(ctx.target, "block", 0) > 0:
        ctx.deal_damage(5, ctx.target)


def fx_deep_cut(ctx) -> None:
    ctx.deal_damage(13, ctx.target)


def fx_earthshatter(ctx) -> None:
    ctx.deal_damage(22, ctx.target)
    ctx.gain_block(6)


def fx_bait_lunge(ctx) -> None:
    ctx.deal_damage(15, ctx.target)
    _apply(ctx, BUFF_VULNERABLE, 2, ctx.target)


def fx_drowning_hook(ctx) -> None:
    ctx.deal_damage(10, ctx.target, hits=2)


def fx_flensing(ctx) -> None:
    ctx.deal_damage(3, ctx.target)
    _lose_hp(ctx, 2)


def fx_backflip_lash(ctx) -> None:
    ctx.deal_damage(9, ctx.target)
    _draw(ctx, 1)


def fx_berserk_tide(ctx) -> None:
    _apply(ctx, BUFF_VULNERABLE, 2, ctx.source)
    _energy(ctx, 1)
    _apply(ctx, BUFF_STRENGTH, 2, ctx.source)


def fx_pressure_crush(ctx) -> None:
    ctx.deal_damage(15, ctx.target)
    _apply(ctx, BUFF_STRENGTH_DOWN, 1, ctx.target)


def fx_blood_in_water(ctx) -> None:
    ctx.deal_damage(10, ctx.target, hits=3)
    _lose_hp(ctx, 6)


def fx_x_flood(ctx) -> None:
    eng = int(getattr(ctx.source, "energy", 0))
    n = max(0, min(eng, 12))
    if n <= 0:
        return
    atk = ctx.target if ctx.target is not None else (ctx.alive_enemies() or [None])[0]
    if atk is None:
        return
    ctx.deal_damage(n * 2, atk)


def fx_whirlpool_extra(ctx) -> None:
    """地毯式轰炸：X 费，每点补给对全体造成 4 伤害。"""
    eng = int(getattr(ctx.source, "energy", 0))
    n = max(0, min(eng, 12))
    for _ in range(n):
        for e in ctx.alive_enemies():
            ctx.deal_damage(4, e)


# ---- 铁壁 / 掩体 ---------------------------------------------------------

def fx_defend(ctx) -> None:
    ctx.gain_block(5, ctx.source)


def fx_metal_hide(ctx) -> None:
    ctx.gain_block(9)


def fx_shell_guard(ctx) -> None:
    _power(ctx, POWER_SHELLGUARD, 4)


def fx_barnacle_armor(ctx) -> None:
    ctx.gain_block(13)
    _apply(ctx, BUFF_THORNS, 3, ctx.source)


def fx_spine_reflex(ctx) -> None:
    ctx.gain_block(7)
    _apply(ctx, BUFF_THORNS, 4, ctx.source)


def fx_iron_tide(ctx) -> None:
    _apply(ctx, BUFF_METALLICIZE, 3, ctx.source)


def fx_bulwark_dive(ctx) -> None:
    ctx.gain_block(15)
    ctx.deal_damage(4, ctx.target)


def fx_coral_growth(ctx) -> None:
    _power(ctx, POWER_CORAL, 1)


def fx_plated_tide(ctx) -> None:
    _apply(ctx, BUFF_PLATED_ARMOR, 4, ctx.source)


def fx_barrier_wall(ctx) -> None:
    ctx.gain_block(12)
    _apply(ctx, BUFF_BARRIER, 12, ctx.source)


def fx_rebound_wave(ctx) -> None:
    ctx.gain_block(6)


def fx_stone_skin(ctx) -> None:
    ctx.gain_block(8)
    _apply(ctx, BUFF_DEXTERITY, 1, ctx.source)


def fx_tide_guard(ctx) -> None:
    ctx.gain_block(10)


def fx_riposte(ctx) -> None:
    th = _buff_amount(ctx, BUFF_THORNS)
    ctx.gain_block(4)
    ctx.deal_damage(th, ctx.target)


def fx_fortress_tide(ctx) -> None:
    _energy(ctx, 1)
    ctx.gain_block(11)


def fx_whale_bone_screen(ctx) -> None:
    b = int(getattr(ctx.card, "block", 7) or 7)
    n = 1
    cnt = getattr(ctx, "summon_count", None)
    if callable(cnt):
        try:
            n += int(cnt())
        except Exception:
            pass
    else:
        n += len(getattr(ctx.source, "minions", None) or [])
    for _ in range(max(1, n)):
        ctx.gain_block(b, ctx.source)


def fx_second_wind(ctx) -> None:
    _exhaust_random(ctx, 2)
    ctx.gain_block(9)


def fx_levee(ctx) -> None:
    ctx.deal_damage(10, ctx.target)
    ctx.gain_block(8)


def fx_abyssal_shell(ctx) -> None:
    ctx.gain_block(16)
    _apply(ctx, BUFF_BARRIER, 6, ctx.source)


def fx_bulwark_stance(ctx) -> None:
    ctx.gain_block(5)
    _apply(ctx, BUFF_METALLICIZE, 2, ctx.source)
    _apply(ctx, BUFF_THORNS, 2, ctx.source)


def fx_last_bastion(ctx) -> None:
    ctx.gain_block(20)
    _apply(ctx, BUFF_FRAIL, 2, ctx.source)


def fx_mirror_pool(ctx) -> None:
    b = _buff_amount(ctx, BUFF_BARRIER)
    if b <= 0:
        b = 5
    ctx.gain_block(b)


def fx_undertow(ctx) -> None:
    for e in ctx.alive_enemies():
        _apply(ctx, BUFF_WEAK, 1, e)
    ctx.gain_block(9)


def fx_sonar_scan(ctx) -> None:
    _energy(ctx, 1)
    _draw(ctx, 1)
    ctx.gain_block(6)


def fx_tidewall_bastion(ctx) -> None:
    ctx.gain_block(14)


def _ally_of(ctx):
    """取一个「队友」目标；本作是单人，返回 None 表示只作用于自己。"""
    return None


# ---- 蚀骨 / 燃烧 / 减益 --------------------------------------------------

def fx_venom_dart(ctx) -> None:
    _apply(ctx, BUFF_POISON, 4, ctx.target)


def fx_corrode_bite(ctx) -> None:
    ctx.deal_damage(5, ctx.target)
    _apply(ctx, BUFF_POISON, 3, ctx.target)


def fx_toxic_cloud(ctx) -> None:
    _aoe(ctx, BUFF_POISON, 3)


def fx_miasma(ctx) -> None:
    _apply(ctx, BUFF_POISON, 6, ctx.target)
    _apply(ctx, BUFF_WEAK, 2, ctx.target)


def fx_plague_tide(ctx) -> None:
    _aoe(ctx, BUFF_POISON, 4)


def fx_envenom(ctx) -> None:
    _apply(ctx, BUFF_ENVENOM, 2, ctx.source)


def fx_barnacle_infest(ctx) -> None:
    _power(ctx, POWER_BARNACLE, 2)


def fx_deadwater(ctx) -> None:
    _power(ctx, POWER_DEADWATER, 1)


def fx_venom_echo(ctx) -> None:
    _power(ctx, POWER_VENOM_ECHO, 3)


def fx_numbing_brine(ctx) -> None:
    _apply(ctx, BUFF_WEAK, 3, ctx.target)


def fx_crippling_wave(ctx) -> None:
    _aoe(ctx, BUFF_WEAK, 2)


def fx_hook_and_barb(ctx) -> None:
    ctx.deal_damage(5, ctx.target)
    _apply(ctx, BUFF_VULNERABLE, 1, ctx.target)


def fx_catalyst_lance(ctx) -> None:
    cur = _buff_amount(ctx, BUFF_POISON, ctx.target)
    ctx.deal_damage(8, ctx.target)
    _apply(ctx, BUFF_POISON, max(cur, 4), ctx.target)


def fx_hemotoxin(ctx) -> None:
    cur = _buff_amount(ctx, BUFF_POISON, ctx.target)
    _apply(ctx, BUFF_POISON, max(1, cur * 2), ctx.target)


def fx_toxin_burst(ctx) -> None:
    ctx.deal_damage(_buff_amount(ctx, BUFF_POISON, ctx.target), ctx.target)


def fx_brine_spray(ctx) -> None:
    ctx.deal_damage(6, ctx.target, hits=3)
    _apply(ctx, BUFF_WEAK, 1, ctx.target)


def fx_bloodletting(ctx) -> None:
    _energize(ctx, 2)


def _energize(ctx, n: int) -> None:
    fn = getattr(ctx, "gain_energy", None)
    if fn is not None:
        fn(n)


def fx_deep_malaise(ctx) -> None:
    eng = int(getattr(ctx.source, "energy", 0))
    n = max(0, min(eng, 8))
    if n <= 0:
        return
    _apply(ctx, BUFF_WEAK, n, ctx.target)
    _apply(ctx, BUFF_POISON, n * 2, ctx.target)


def fx_necrotic_grasp(ctx) -> None:
    ctx.deal_damage(6, ctx.target)
    _heal(ctx, 4)


def fx_vile_surge(ctx) -> None:
    ctx.deal_damage(4, ctx.target)
    _aoe(ctx, BUFF_POISON, 3)


def fx_festering_hook(ctx) -> None:
    ctx.deal_damage(8, ctx.target)
    _apply(ctx, BUFF_WEAK, 2, ctx.target)


def fx_rot_barrage(ctx) -> None:
    ctx.deal_damage(9, ctx.target)
    _apply(ctx, BUFF_VULNERABLE, 2, ctx.target)
    _apply(ctx, BUFF_POISON, 2, ctx.target)


def fx_culling_tide(ctx) -> None:
    for e in ctx.alive_enemies():
        p = _buff_amount(ctx, BUFF_POISON, e)
        ctx.deal_damage(p, e)


def fx_frail_current(ctx) -> None:
    _apply(ctx, BUFF_FRAIL, 3, ctx.target)


def fx_withering_gaze(ctx) -> None:
    ctx.deal_damage(11, ctx.target)
    _apply(ctx, BUFF_STRENGTH_DOWN, 2, ctx.target)


def fx_defile_water(ctx) -> None:
    _add_hand(ctx, "plague_spore")


# ---- 后勤 / 补给 / 抽牌 / 连射 -------------------------------------------

def fx_tide_pool(ctx) -> None:
    _power(ctx, POWER_TIDEPOOL, 1)


def fx_deep_current(ctx) -> None:
    _power(ctx, POWER_DEEP_CURRENT, 1)


def fx_artifact_shell(ctx) -> None:
    _apply(ctx, BUFF_ARTIFACT, 1, ctx.source)


def fx_tidal_reserve(ctx) -> None:
    _power(ctx, POWER_TIDAL_RESERVE, 1)


def fx_abyssal_gate(ctx) -> None:
    _power(ctx, POWER_ABYSSAL_GATE, 1)


def fx_electrify(ctx) -> None:
    _draw(ctx, 2)
    _energy(ctx, 1)


def fx_tide_knot(ctx) -> None:
    ctx.deal_damage(3, ctx.target)


def fx_chain_lightning(ctx) -> None:
    ctx.deal_damage(4 + _played(ctx) * 2, ctx.target)


def fx_resonance(ctx) -> None:
    ctx.deal_damage(3 + _played(ctx) * 2, ctx.target)


def fx_surge_draw(ctx) -> None:
    _draw(ctx, 2)


def fx_current_ribbon(ctx) -> None:
    ctx.deal_damage(14, ctx.target)
    _draw(ctx, 1)


def fx_energy_well(ctx) -> None:
    _energize(ctx, 1)
    _draw(ctx, 1)


def fx_lightning_pool(ctx) -> None:
    _apply(ctx, BUFF_CHAIN, 4, ctx.source)


def fx_volt_lance(ctx) -> None:
    ctx.deal_damage(5, ctx.target)
    _energize(ctx, 1)


def fx_buoyancy(ctx) -> None:
    _energize(ctx, 2)
    _apply(ctx, BUFF_CHAIN, 1, ctx.source)


def fx_tidal_echo(ctx) -> None:
    ctx.deal_damage(8, ctx.target)
    _add_hand(ctx, "chain_vein")


def fx_sonar_pulse(ctx) -> None:
    _draw(ctx, 3)
    _energy(ctx, 1)
    _add_hand(ctx, "whale_bone_screen")


def fx_whirl_engine(ctx) -> None:
    ctx.deal_damage(10, ctx.target)
    _draw(ctx, 1)
    _energize(ctx, 1)


def fx_ebbing_blade(ctx) -> None:
    ctx.deal_damage(6, ctx.target, hits=2)
    _draw(ctx, 1)


def fx_surge_protector(ctx) -> None:
    ctx.gain_block(8)
    _apply(ctx, BUFF_CHAIN, 2, ctx.source)


def fx_chain_vein(ctx) -> None:
    ctx.deal_damage(5 + _played(ctx), ctx.target)


def fx_voltaic_shell(ctx) -> None:
    ctx.deal_damage(12, ctx.target, hits=2)


def fx_current_lash(ctx) -> None:
    ctx.deal_damage(6 + _played(ctx), ctx.target)
    _energize(ctx, 1)


# ---- 唤灵 / 征召 / 增援 --------------------------------------------------

def fx_summon_calf(ctx) -> None:
    _summon(ctx, MINION_WHALE_CALF, 8, 4)


def fx_summon_gull(ctx) -> None:
    _summon(ctx, MINION_GULL, 4, 2)


def fx_summon_squid(ctx) -> None:
    _summon(ctx, MINION_SQUID, 6, 3)


def fx_school_of_gulls(ctx) -> None:
    _summon(ctx, MINION_GULL, 3, 2)
    _summon(ctx, MINION_GULL, 3, 2)


def fx_jelly_pulse(ctx) -> None:
    _summon(ctx, MINION_JELLY, 5, 2)
    _apply(ctx, BUFF_WEAK, 1, ctx.target)


def fx_ritual_chant(ctx) -> None:
    _apply(ctx, BUFF_RITUAL, 1, ctx.source)


def fx_blood_ritual(ctx) -> None:
    _lose_hp(ctx, 5)
    _apply(ctx, BUFF_RITUAL, 2, ctx.source)


def fx_sacrificial_tide(ctx) -> None:
    ctx.deal_damage(18, ctx.target)
    _lose_hp(ctx, 8)


def fx_summon_angler(ctx) -> None:
    _summon(ctx, MINION_ANGLER, 10, 5)


def fx_summon_crab(ctx) -> None:
    _summon(ctx, MINION_CRAB, 14, 1)
    ctx.gain_block(6)


def fx_tide_leviathan(ctx) -> None:
    _summon(ctx, MINION_LEVIATHAN, 22, 8)


def fx_deep_echo(ctx) -> None:
    _power(ctx, POWER_DEEP_ECHO, 5)


def fx_ritual_chorus(ctx) -> None:
    _power(ctx, POWER_RITUAL_CHORUS, 1)


def fx_whale_song(ctx) -> None:
    _power(ctx, POWER_WHALE_SONG, 4)


def fx_necro_tide(ctx) -> None:
    _power(ctx, POWER_NECROTIDE, 1)


def fx_sacrifice(ctx) -> None:
    ms = getattr(ctx.source, "minions", None) or []
    if not ms:
        ctx.gain_block(4)
        return
    m = ms[0]
    hpm = int(getattr(m, "hp", 0))
    try:
        ms.remove(m)
    except ValueError:  # pragma: no cover
        pass
    ctx.gain_block(hpm)
    _apply(ctx, BUFF_STRENGTH, 2, ctx.source)


def fx_bone_chorus(ctx) -> None:
    ms = getattr(ctx.source, "minions", None) or []
    n = max(1, len(ms))
    for e in ctx.alive_enemies():
        ctx.deal_damage(n * 3, e)


def fx_feed_the_deep(ctx) -> None:
    _lose_hp(ctx, 4)
    _summon(ctx, MINION_SQUID, 6, 3)


def fx_kraken_grasp(ctx) -> None:
    ctx.deal_damage(4, ctx.target, hits=3)
    _apply(ctx, BUFF_WEAK, 2, ctx.target)


def fx_abyssal_legion(ctx) -> None:
    for _ in range(3):
        _summon(ctx, MINION_JELLY, 5, 2)


def fx_spawn_pod(ctx) -> None:
    _summon(ctx, MINION_WHALE_CALF, 6, 3)


def fx_tentacle_lash(ctx) -> None:
    ms = getattr(ctx.source, "minions", None) or []
    for m in ms:
        a = int(getattr(m, "attack", 0))
        if a:
            ctx.deal_damage(a, ctx.target)


# ---- 状态牌 / 诅咒 -------------------------------------------------------

def fx_wound(ctx) -> None:
    return None


def fx_dazed(ctx) -> None:
    return None


def fx_slimed(ctx) -> None:
    return None


def fx_burn(ctx) -> None:
    _lose_hp(ctx, 2)


def fx_decay(ctx) -> None:
    _lose_hp(ctx, 2)


def fx_doubt(ctx) -> None:
    _apply(ctx, BUFF_WEAK, 1, ctx.source)


def fx_shame(ctx) -> None:
    _apply(ctx, BUFF_FRAIL, 1, ctx.source)


def fx_regret(ctx) -> None:
    hand = getattr(ctx.source, "hand", None) or []
    _lose_hp(ctx, max(1, len(hand)))


def fx_pain(ctx) -> None:
    _lose_hp(ctx, 1)


def fx_curse_of_the_deep(ctx) -> None:
    _lose_hp(ctx, 3)


# --------------------------------------------------------------------------
# 卡表定义
# --------------------------------------------------------------------------

# ==== 新增：指挥点 / 干扰 / 科研 / 单位 ====
def fx_supply_drop(ctx) -> None:
    """空投补给：直接给指挥点 + 抽牌。"""
    ctx.gain_energy(2)
    ctx.draw(1)


def fx_logistics_chain(ctx) -> None:
    """后勤链：给指挥点，费用为 0，等于白赚。"""
    ctx.gain_energy(2)


def fx_all_hands_on_deck(ctx) -> None:
    """全员就位：给指挥点并抽牌，但抽到的牌本回合临时。"""
    ctx.gain_energy(3)
    ctx.draw(2)


def fx_emergency_requisition(ctx) -> None:
    """紧急征用：失去 4 点耐久换 3 点指挥点。"""
    ctx.gain_energy(3)
    try:
        ctx.source.hp = max(1, int(ctx.source.hp) - 4)
    except Exception:
        pass


def fx_winter_stockpile(ctx) -> None:
    """冬季储备：给指挥点，但本回合结束手牌不保留（副作用靠描述提示）。"""
    ctx.gain_energy(4)
    ctx.draw(1)


# --------------------------------------------------------------------------
# B 组 · 干扰（削弱敌人 / 打乱敌人）
# --------------------------------------------------------------------------
def fx_suppress_fire(ctx) -> None:
    """压制射击：给敌人「虚弱」（其攻击 -25%）。"""
    ctx.deal_damage(6, ctx.target)
    _apply(ctx, BUFF_WEAK, 3, ctx.target)


def fx_disarm(ctx) -> None:
    """缴械：给敌人虚弱 + 脆弱（无法强化自己）。"""
    _apply(ctx, BUFF_WEAK, 2, ctx.target)
    _apply(ctx, BUFF_FRAIL, 3, ctx.target)
    ctx.gain_block(6)


def fx_jam_comms(ctx) -> None:
    """干扰通讯：全体虚弱。"""
    ctx.apply_buff_all(BUFF_WEAK, 3)


def fx_break_morale(ctx) -> None:
    """瓦解士气：敌人失去火力（strength_down）。"""
    _apply(ctx, BUFF_STRENGTH_DOWN, 3, ctx.target)
    ctx.deal_damage(5, ctx.target)


def fx_scatter(ctx) -> None:
    """驱散队形：全体脆弱 + 抽牌。"""
    ctx.apply_buff_all(BUFF_FRAIL, 2)
    ctx.draw(1)


def fx_rust_rounds(ctx) -> None:
    """锈蚀弹药：给敌人叠燃烧（随时间掉血）。"""
    _apply(ctx, BUFF_POISON, 5, ctx.target)
    ctx.deal_damage(3, ctx.target)


# --------------------------------------------------------------------------
# C 组 · 范围攻击
# --------------------------------------------------------------------------
def fx_carpet_bomb(ctx) -> None:
    """地毯式轰炸：对全体造成伤害。"""
    ctx.deal_damage_all(10)


def fx_artillery_barrage(ctx) -> None:
    """炮火覆盖：全体伤害 + 全体破甲。"""
    ctx.deal_damage_all(7)
    ctx.apply_buff_all(BUFF_VULNERABLE, 2)


def fx_scorched_earth(ctx) -> None:
    """焦土政策：全体高伤，但自己也掉血。"""
    ctx.deal_damage_all(16)
    try:
        ctx.source.hp = max(1, int(ctx.source.hp) - 5)
    except Exception:
        pass


def fx_shrapnel_storm(ctx) -> None:
    """破片风暴：全体多次小伤害（配合火力极强）。"""
    ctx.deal_damage_all(4, hits=3)


# --------------------------------------------------------------------------
# D 组 · 科研（初级 → 高级 → 超模）
# --------------------------------------------------------------------------
def fx_research_basic(ctx) -> None:
    """初级科研：抽 2 张牌，获得 1 点火力（打基础）。"""
    ctx.draw(2)
    _apply(ctx, BUFF_STRENGTH, 1, ctx.source)


def fx_research_advanced(ctx) -> None:
    """高级科研：**手牌中的初级科研越多，收益越高**。"""
    n = 0
    try:
        for c in (ctx.source.hand or []):
            did = getattr(c, 'def_id', '')
            if did in ('research_basic', 'research_advanced'):
                n += 1
    except Exception:
        n = 0
    ctx.draw(2 + min(3, n))
    _apply(ctx, BUFF_STRENGTH, 2 + min(4, n), ctx.source)
    ctx.gain_energy(1)


def fx_research_breakthrough(ctx) -> None:
    """科研突破：**每打过一张科研牌**，火力 +2（成长型）。"""
    n = int(getattr(ctx.source, 'research_count', 0) or 0)
    _apply(ctx, BUFF_STRENGTH, 3 + min(8, n * 2), ctx.source)
    try:
        ctx.source.research_count = n + 1
    except Exception:
        pass
    ctx.draw(2)


def fx_prototype_weapon(ctx) -> None:
    """原型兵器：超模范围攻击 —— 对全体造成大量伤害，消耗。"""
    ctx.deal_damage_all(22)
    ctx.apply_buff_all(BUFF_VULNERABLE, 3)


# --------------------------------------------------------------------------
# E 组 · 单位（KARDS 风格：放置后每回合自动攻击）
# --------------------------------------------------------------------------
def fx_deploy_riflemen(ctx) -> None:
    """部署步兵班：每回合自动开火。"""
    ctx.summon("步兵班", 8, 4)


def fx_deploy_mg_nest(ctx) -> None:
    """部署机枪巢：血厚、输出稳定。"""
    ctx.summon("机枪巢", 14, 3)


def fx_deploy_tank(ctx) -> None:
    """部署中型坦克：高攻。"""
    ctx.summon("中型坦克", 12, 7)


def fx_deploy_artillery(ctx) -> None:
    """部署野战炮：攻击高但脆。"""
    ctx.summon("野战炮", 6, 10)


def fx_deploy_engineer(ctx) -> None:
    """部署工兵连：给掩体 + 单位（防御向）。"""
    ctx.gain_block(8)
    ctx.summon("工兵连", 10, 2)


def fx_deploy_command_tank(ctx) -> None:
    """部署指挥坦克：单位 + 全体火力。"""
    ctx.summon("指挥坦克", 15, 6)
    _apply(ctx, BUFF_STRENGTH, 2, ctx.source)




# ==== 新增：破甲增伤 + 条件牌（见文件末尾的 NEW_CARDS）====
def fx_armor_crack(ctx) -> None:
    """破甲弹：小伤害 + 易伤。"""
    ctx.deal_damage(5, ctx.target)
    _apply(ctx, BUFF_VULNERABLE, 3, ctx.target)


def fx_siege_shell(ctx) -> None:
    """攻坚弹：高伤 + 易伤，给自己一点副作用（疲惫）。"""
    ctx.deal_damage(14, ctx.target)
    _apply(ctx, BUFF_VULNERABLE, 2, ctx.target)
    ctx.gain_block(4)


def fx_mark_target(ctx) -> None:
    """标记目标：不造成伤害，但给大量易伤 + 抽牌。"""
    _apply(ctx, BUFF_VULNERABLE, 4, ctx.target)
    ctx.draw(1)


def fx_chain_breach(ctx) -> None:
    """连环破袭：全体易伤。"""
    ctx.apply_buff_all(BUFF_VULNERABLE, 2)


# --------------------------------------------------------------------------
# B 组 · 增伤（BUFF_STRENGTH = 火力，每点 +1 伤害）
# --------------------------------------------------------------------------
def fx_mass_mobilize(ctx) -> None:
    """全军动员：获得火力，本回合打出的攻击牌越多越强。"""
    n = 0
    fn = getattr(ctx, "cards_played_this_turn", None)
    if callable(fn):
        try:
            n = int(fn())
        except Exception:
            n = 0
    _apply(ctx, BUFF_STRENGTH, 2 + min(3, n), ctx.source)


def fx_last_stand(ctx) -> None:
    """背水一战：**血量越低，火力越高**（平常很蛆，残血时爆炸）。"""
    hp = int(getattr(ctx.source, "hp", 1) or 1)
    mx = max(1, int(getattr(ctx.source, "max_hp", 1) or 1))
    missing = max(0, mx - hp)
    gain = 1 + missing // 8          # 每缺 8 点血 +1 火力
    _apply(ctx, BUFF_STRENGTH, min(8, gain), ctx.source)
    ctx.gain_block(missing // 6)


def fx_arsenal_overload(ctx) -> None:
    """弹药过载：火力大提升，但立即失去少量耐久。"""
    _apply(ctx, BUFF_STRENGTH, 5, ctx.source)
    try:
        ctx.source.hp = max(1, int(ctx.source.hp) - 4)
    except Exception:
        pass


# --------------------------------------------------------------------------
# C 组 · 减防（BUFF_FRAIL = 脆弱，自己受到的伤害 +50%，这里用于「换攻」）
# --------------------------------------------------------------------------
def fx_all_in(ctx) -> None:
    """孤注一掷：本回合火力暴涨，但自己也变脆（高风险高回报）。"""
    _apply(ctx, BUFF_STRENGTH, 4, ctx.source)
    _apply(ctx, BUFF_FRAIL, 2, ctx.source)
    ctx.gain_energy(1)


def fx_reckless_assault(ctx) -> None:
    """蛮勇突击：高伤害，自身受 3 点伤害。"""
    ctx.deal_damage(16, ctx.target)
    try:
        ctx.source.hp = max(1, int(ctx.source.hp) - 3)
    except Exception:
        pass


# --------------------------------------------------------------------------
# D 组 · 「平常很蛆，特定情况能量巨大」
# --------------------------------------------------------------------------
def fx_scrap_heap(ctx) -> None:
    """废铁堆：伤害很低，但**手牌越多伤害越高**。"""
    n = 0
    try:
        n = len(getattr(ctx.source, "hand", []) or [])
    except Exception:
        n = 0
    ctx.deal_damage(2 + n * 2, ctx.target)


def fx_ambush(ctx) -> None:
    """伏击：本回合**还没出过牌**时伤害翻倍（第一张出它才强）。"""
    n = 0
    fn = getattr(ctx, "cards_played_this_turn", None)
    if callable(fn):
        try:
            n = int(fn())
        except Exception:
            n = 0
    dmg = 18 if n <= 1 else 5
    ctx.deal_damage(dmg, ctx.target)


def fx_overrun(ctx) -> None:
    """碾压：**敌人越多越强**（单体时很蛆）。"""
    n = 0
    fn = getattr(ctx, "alive_enemies", None)
    if callable(fn):
        try:
            n = len(fn())
        except Exception:
            n = 0
    ctx.deal_damage(4 + n * 7, ctx.target)


def fx_bullet_hail(ctx) -> None:
    """弹幕覆盖：对每个敌人各打一次（人少时很蛆）。"""
    n = 0
    fn = getattr(ctx, "alive_enemies", None)
    if callable(fn):
        try:
            n = len(fn())
        except Exception:
            n = 0
    for _ in range(max(1, n)):
        ctx.deal_damage(6, ctx.target)


def fx_desperate_gamble(ctx) -> None:
    """绝境豪赌：**血量低于 30% 时**给予巨额火力，否则几乎没有效果。"""
    hp = int(getattr(ctx.source, "hp", 1) or 1)
    mx = max(1, int(getattr(ctx.source, "max_hp", 1) or 1))
    if hp * 10 <= mx * 3:
        _apply(ctx, BUFF_STRENGTH, 6, ctx.source)
        ctx.gain_energy(2)
        ctx.draw(2)
    else:
        ctx.gain_block(3)


def fx_entrench(ctx) -> None:
    """掘壕固守：本回合不攻击的话，回合末获得大量掩体（很蛆但保命）。"""
    ctx.gain_block(6)


def fx_salvage(ctx) -> None:
    """回收残骸：**手牌越少抽越多**（平常抽 1，手牌空时抽 4）。"""
    n = 0
    try:
        n = len(getattr(ctx.source, "hand", []) or [])
    except Exception:
        n = 0
    ctx.draw(4 if n <= 1 else 1)


def fx_deadweight_shot(ctx) -> None:
    """负重射击：伤害等于**已打出牌数 × 3**（第一张很蛆）。"""
    n = 0
    fn = getattr(ctx, "cards_played_this_turn", None)
    if callable(fn):
        try:
            n = int(fn())
        except Exception:
            n = 0
    ctx.deal_damage(max(3, n * 3), ctx.target)


def fx_siege_momentum(ctx) -> None:
    """攻势蓄能：每次打出都叠火力，**越打越猛**（起手很蛆）。"""
    _apply(ctx, BUFF_STRENGTH, 1, ctx.source)
    ctx.draw(1)
    ctx.gain_energy(1)


def fx_veteran_instinct(ctx) -> None:
    """老兵直觉：**牌库越薄越强**（未升级的牌越多越弱）。"""
    n = 0
    try:
        n = len(getattr(ctx.source, "draw_pile", []) or [])
    except Exception:
        n = 0
    ctx.gain_block(4)
    if n <= 5:
        _apply(ctx, BUFF_STRENGTH, 3, ctx.source)


def fx_fortify_line(ctx) -> None:
    """死守防线：获得掩体，且**本回合每受一次击额外 +2 掩体**（被动）。"""
    ctx.gain_block(10)
    _apply(ctx, BUFF_PLATED_ARMOR, 2, ctx.source)


def fx_zero_hour(ctx) -> None:
    """零点攻势：**本回合第一次出牌时**全体易伤 + 抽满（后续出就是废牌）。"""
    n = 0
    fn = getattr(ctx, "cards_played_this_turn", None)
    if callable(fn):
        try:
            n = int(fn())
        except Exception:
            n = 0
    if n <= 1:
        ctx.apply_buff_all(BUFF_VULNERABLE, 3)
        ctx.draw(2)
    else:
        ctx.draw(1)




CARD_LIST: List[CardDef] = [

    # ================= 强攻 · 火力 (attack) — 24 张 =================
    CardDef("strike", "步枪齐射", 1, "attack", RARITY_BASIC, ARCH_ATTACK,
            "造成 {damage} 点伤害。", "enemy", fx_strike, upgrade={"damage": 9},
            damage=6, keywords=("基础", "火力")),
    CardDef("heavy_harpoon", "重型穿甲弹", 2, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害。", "enemy", fx_heavy_harpoon, upgrade={"damage": 18},
            damage=14, keywords=("火力", "单体重击")),
    CardDef("twin_fang", "双联机枪", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，共 {hits} 次。", "enemy", fx_twin_fang,
            upgrade={"damage": 7}, damage=5, hits=2, keywords=("火力", "连击")),
    CardDef("cleave", "扇形扫射", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "对全体敌人各造成 {damage} 点伤害。", "all_enemies", fx_cleave,
            upgrade={"damage": 11}, damage=8, keywords=("火力", "群体")),
    CardDef("ram_charge", "装甲冲锋", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，获得 {block} 点掩体。", "enemy", fx_ram_charge,
            upgrade={"damage": 13, "block": 7}, damage=10, block=5,
            keywords=("火力", "掩体")),
    CardDef("rending_bite", "破片手雷", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，施加 {magic} 层破甲。", "enemy", fx_rending_bite,
            upgrade={"damage": 9, "magic": 3}, damage=7, magic=2,
            keywords=("火力", "破甲")),
    CardDef("whale_charge", "重锤突击", 2, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，获得 {magic} 点火力。", "enemy", fx_whale_charge,
            upgrade={"damage": 12, "magic": 3}, damage=9, magic=2,
            keywords=("火力",)),
    CardDef("frenzy", "狂暴突刺", 1, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，本回合每打出一张牌额外 +3 伤害。", "enemy", fx_frenzy,
            upgrade={"cost": 0}, damage=8, keywords=("火力", "连射")),
    CardDef("inflame", "战意沸腾", 1, "power", RARITY_UNCOMMON, ARCH_ATTACK,
            "获得 {magic} 点火力与 {block} 点掩体。", "self", fx_inflame,
            upgrade={"magic": 3}, magic=2, block=5, keywords=("火力", "能力")),
    CardDef("limit_break", "火力全开", 1, "skill", RARITY_RARE, ARCH_ATTACK,
            "使自身火力翻倍。", "self", fx_limit_break, upgrade={"cost": 0},
            exhaust=True, keywords=("火力", "成长")),
    CardDef("reaper_scythe", "焦土轰炸", 3, "attack", RARITY_RARE, ARCH_ATTACK,
            "对全体敌人各造成 {damage} 点伤害，获得 {magic} 点火力。", "all_enemies",
            fx_reaper_scythe, upgrade={"damage": 6}, damage=4, magic=3, exhaust=True,
            keywords=("火力", "群体")),
    CardDef("hold_the_line", "据守射击", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成等同于 {damage} + 当前火力的伤害。", "enemy", fx_hold_the_line,
            upgrade={"damage": 9}, damage=7, keywords=("火力",)),
    CardDef("cross_slash", "交叉火力", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 2 次伤害，每次为本回合已出牌数 ×2 + {damage}。", "enemy", fx_cross_slash,
            upgrade={"damage": 9}, damage=7, hits=2, keywords=("火力", "连射")),
    CardDef("recall", "弹药补给", 1, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，将一张「弹药箱」加入手牌。", "enemy", fx_recall,
            upgrade={"damage": 9}, damage=6, keywords=("火力", "生成")),
    CardDef("sweeping_blow", "重炮轰击", 2, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，施加 {magic} 层弹药短缺。", "enemy", fx_sweeping_blow,
            upgrade={"damage": 15}, damage=12, magic=3, keywords=("火力", "减益")),
    CardDef("whirlpool", "轮番突击", 2, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "对全体敌人造成 3 次 {damage} 点伤害。", "all_enemies", fx_whirlpool,
            upgrade={"damage": 7}, damage=5, hits=3, keywords=("火力", "群体", "连击")),
    CardDef("armor_piercer", "穿甲弹幕", 2, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "清除所有敌人的掩体，造成 {damage} 点伤害并追加其掩体值伤害（至多 8）。",
            "enemy", fx_armor_piercer, upgrade={"damage": 12}, damage=9,
            keywords=("火力", "破甲")),
    CardDef("cold_current", "曳光扫射", 2, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "对全体敌人各造成 {damage} 点伤害并施加 {magic} 层压制。", "all_enemies",
            fx_cold_current, upgrade={"damage": 8}, damage=6, magic=1,
            keywords=("火力", "群体", "压制")),
    CardDef("double_strike", "双发点射", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，共 {hits} 次。", "enemy", fx_double_strike,
            upgrade={"damage": 8}, damage=6, hits=2, keywords=("火力", "连击")),
    CardDef("toxin_uppercut", "烈性燃烧弹", 2, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，施加 {magic} 层破甲。", "enemy", fx_toxin_uppercut,
            upgrade={"damage": 10}, damage=8, magic=3, keywords=("火力", "破甲")),
    CardDef("hammerhead", "破障锤击", 2, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害；若目标有掩体，再造成 5 点伤害。", "enemy", fx_hammerhead,
            upgrade={"damage": 14}, damage=11, keywords=("火力", "破甲")),
    CardDef("deep_cut", "纵深突入", 3, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害。", "enemy", fx_deep_cut, upgrade={"damage": 17},
            damage=13, keywords=("火力", "单体重击")),
    CardDef("earthshatter", "重炮碾压", 3, "attack", RARITY_RARE, ARCH_ATTACK,
            "造成 {damage} 点伤害，获得 {block} 点掩体。", "enemy", fx_earthshatter,
            upgrade={"damage": 28}, damage=22, block=6, keywords=("火力", "单体重击")),
    CardDef("bait_lunge", "诱敌突袭", 2, "attack", RARITY_RARE, ARCH_ATTACK,
            "造成 {damage} 点伤害，施加 {magic} 层破甲。", "enemy", fx_bait_lunge,
            upgrade={"damage": 20}, damage=15, magic=3, keywords=("火力", "破甲")),

    # ================= 铁壁 · 掩体 (block) — 24 张 =================
    CardDef("defend", "构筑掩体", 1, "skill", RARITY_BASIC, ARCH_BLOCK,
            "获得 {block} 点掩体。", "self", fx_defend, upgrade={"block": 8},
            block=5, keywords=("基础", "掩体")),
    CardDef("metal_hide", "装甲板加固", 2, "skill", RARITY_COMMON, ARCH_BLOCK,
            "获得 {block} 点掩体。", "self", fx_metal_hide, upgrade={"block": 13},
            block=9, keywords=("掩体",)),
    CardDef("shell_guard", "工事修筑", 1, "skill", RARITY_COMMON, ARCH_BLOCK,
            "获得能力：每回合结束时获得 {magic} 点掩体。", "self", fx_shell_guard,
            upgrade={"magic": 6}, magic=4, keywords=("掩体", "能力")),
    CardDef("barnacle_armor", "铁丝网防线", 2, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得 {block} 点掩体与 {magic} 点铁丝网。", "self", fx_barnacle_armor,
            upgrade={"block": 17}, block=13, magic=3, keywords=("掩体", "铁丝网")),
    CardDef("spine_reflex", "铁丝网反冲", 1, "skill", RARITY_COMMON, ARCH_BLOCK,
            "获得 {block} 点掩体与 {magic} 点铁丝网。", "self", fx_spine_reflex,
            upgrade={"block": 9, "magic": 6}, block=7, magic=4,
            keywords=("掩体", "铁丝网")),
    CardDef("iron_tide", "永备工事", 1, "power", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得 {magic} 点工事：每回合结束获得等量掩体。", "self", fx_iron_tide,
            upgrade={"magic": 5}, magic=3, keywords=("掩体", "工事", "能力")),
    CardDef("bulwark_dive", "掩体突击", 2, "attack", RARITY_COMMON, ARCH_BLOCK,
            "获得 {block} 点掩体，造成 {damage} 点伤害。", "enemy", fx_bulwark_dive,
            upgrade={"block": 20, "damage": 6}, damage=4, block=15,
            keywords=("掩体", "反击")),
    CardDef("coral_growth", "工兵强化", 1, "power", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得能力：每次获得掩体时额外 +{magic}。", "self", fx_coral_growth,
            upgrade={"magic": 2}, magic=1, keywords=("掩体", "能力")),
    CardDef("plated_tide", "装甲板铺设", 1, "power", RARITY_RARE, ARCH_BLOCK,
            "获得 {magic} 点装甲板：回合结束保留并叠加掩体。", "self", fx_plated_tide,
            upgrade={"magic": 6}, magic=4, keywords=("掩体", "装甲板", "能力")),
    CardDef("barrier_wall", "坚守阵地", 2, "skill", RARITY_RARE, ARCH_BLOCK,
            "获得 {block} 点掩体与 12 点坚守（回合末不清空）。", "self", fx_barrier_wall,
            upgrade={"block": 16}, block=12, magic=12, exhaust=True,
            keywords=("掩体", "坚守")),
    CardDef("rebound_wave", "快速掩体", 0, "skill", RARITY_COMMON, ARCH_BLOCK,
            "获得 {block} 点掩体。", "self", fx_rebound_wave, upgrade={"block": 9},
            block=6, keywords=("掩体",)),
    CardDef("stone_skin", "机动规避", 1, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得 {block} 点掩体与 {magic} 点机动。", "self", fx_stone_skin,
            upgrade={"block": 11}, block=8, magic=1, keywords=("掩体", "机动")),
    CardDef("tide_guard", "警戒哨位", 1, "skill", RARITY_COMMON, ARCH_BLOCK,
            "获得 {block} 点掩体。", "self", fx_tide_guard, upgrade={"block": 14},
            block=10, keywords=("掩体",)),
    CardDef("riposte", "铁丝网反击", 1, "attack", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得 {block} 点掩体，造成等同于当前铁丝网层数的伤害。", "enemy", fx_riposte,
            upgrade={"block": 6}, damage=0, block=4, keywords=("掩体", "铁丝网", "反击")),
    CardDef("fortress_tide", "要塞补给", 1, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得 {block} 点掩体与 1 点补给。", "self", fx_fortress_tide,
            upgrade={"block": 15}, block=11, keywords=("掩体", "补给")),
    CardDef("whale_bone_screen", "沙袋胸墙", 1, "skill", RARITY_COMMON, ARCH_BLOCK,
            "获得 {block} 点掩体；每拥有一个附属单位，额外获得一次。", "self",
            fx_whale_bone_screen,
            upgrade={"block": 10}, block=7, keywords=("掩体", "征召")),
    CardDef("second_wind", "战场整备", 1, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "随机移除 2 张手牌，获得 {block} 点掩体。", "self", fx_second_wind,
            upgrade={"block": 13}, block=9, keywords=("掩体", "移除")),
    CardDef("levee", "反坦克拒马", 2, "attack", RARITY_COMMON, ARCH_BLOCK,
            "造成 {damage} 点伤害并获得 {block} 点掩体。", "enemy", fx_levee,
            upgrade={"damage": 13, "block": 11}, damage=10, block=8,
            keywords=("掩体", "反击")),
    CardDef("abyssal_shell", "重型掩体", 3, "skill", RARITY_RARE, ARCH_BLOCK,
            "获得 {block} 点掩体与 6 点坚守。", "self", fx_abyssal_shell,
            upgrade={"block": 22}, block=16, magic=6, keywords=("掩体", "坚守")),
    CardDef("bulwark_stance", "筑垒架势", 2, "power", RARITY_RARE, ARCH_BLOCK,
            "获得 {block} 点掩体、{magic} 点工事与 {magic2} 点铁丝网。", "self",
            fx_bulwark_stance, upgrade={"magic": 3, "magic2": 3}, block=5, magic=2,
            magic2=2, keywords=("掩体", "工事", "铁丝网", "能力")),
    CardDef("last_bastion", "最后防线", 2, "skill", RARITY_RARE, ARCH_BLOCK,
            "获得 {block} 点掩体，自身获得 2 层压制。", "self", fx_last_bastion,
            upgrade={"block": 28}, block=20, keywords=("掩体", "风险")),
    CardDef("mirror_pool", "加固工事", 1, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得等同于当前坚守层数的掩体（无坚守时获得 5 点）。", "self", fx_mirror_pool,
            upgrade={"cost": 0}, block=5, magic=5, keywords=("掩体", "坚守")),
    CardDef("undertow", "压制射击", 1, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "对全体敌人施加 {magic} 层压制，获得 {block} 点掩体。", "self", fx_undertow,
            upgrade={"block": 13}, block=9, magic=1, keywords=("掩体", "压制")),
    CardDef("sonar_scan", "战场侦察", 0, "skill", RARITY_RARE, ARCH_BLOCK,
            "获得 1 点补给，抽 1 张牌，获得 {block} 点掩体。", "self", fx_sonar_scan,
            upgrade={"block": 9}, block=6, keywords=("掩体", "补给", "抽牌")),

    # ================= 蚀骨 · 燃烧 (poison) — 24 张 =================
    CardDef("venom_dart", "燃烧瓶", 1, "skill", RARITY_COMMON, ARCH_POISON,
            "施加 {magic} 层燃烧。", "enemy", fx_venom_dart, upgrade={"magic": 6},
            magic=4, keywords=("燃烧",)),
    CardDef("corrode_bite", "纵火射击", 1, "attack", RARITY_COMMON, ARCH_POISON,
            "造成 {damage} 点伤害，施加 {magic} 层燃烧。", "enemy", fx_corrode_bite,
            upgrade={"damage": 7, "magic": 4}, damage=5, magic=3,
            keywords=("燃烧", "攻击")),
    CardDef("toxic_cloud", "燃烧弹覆盖", 2, "skill", RARITY_COMMON, ARCH_POISON,
            "对全体敌人施加 {magic} 层燃烧。", "all_enemies", fx_toxic_cloud,
            upgrade={"magic": 5}, magic=3, keywords=("燃烧", "群体")),
    CardDef("miasma", "火海压制", 2, "skill", RARITY_UNCOMMON, ARCH_POISON,
            "施加 {magic} 层燃烧与 {magic2} 层压制。", "enemy", fx_miasma,
            upgrade={"magic": 9}, magic=6, magic2=2, keywords=("燃烧", "压制")),
    CardDef("plague_tide", "全面纵火", 2, "skill", RARITY_UNCOMMON, ARCH_POISON,
            "对全体敌人施加 {magic} 层燃烧。", "all_enemies", fx_plague_tide,
            upgrade={"magic": 6}, magic=4, keywords=("燃烧", "群体")),
    CardDef("envenom", "燃烧弹改装", 1, "power", RARITY_RARE, ARCH_POISON,
            "获得 {magic} 层燃烧弹：攻击牌造成伤害后施加等量燃烧。", "self", fx_envenom,
            upgrade={"magic": 3}, magic=2, keywords=("燃烧", "能力")),
    CardDef("barnacle_infest", "纵火教官", 1, "power", RARITY_UNCOMMON, ARCH_POISON,
            "获得能力：每次打出攻击牌，目标额外获得 {magic} 层燃烧。", "self",
            fx_barnacle_infest, upgrade={"magic": 3}, magic=2,
            keywords=("燃烧", "能力")),
    CardDef("deadwater", "焦土战术", 2, "power", RARITY_RARE, ARCH_POISON,
            "获得能力：每次打出攻击牌，全体敌人获得 1 层燃烧。", "self", fx_deadwater,
            upgrade={"cost": 1}, magic=1, keywords=("燃烧", "群体", "能力")),
    CardDef("venom_echo", "战地医疗", 2, "power", RARITY_RARE, ARCH_POISON,
            "获得能力：回合结束时按敌人燃烧总层数回复 {magic} 倍总部耐久。", "self",
            fx_venom_echo, upgrade={"magic": 4}, magic=3, keywords=("燃烧", "能力")),
    CardDef("numbing_brine", "压制射击", 1, "skill", RARITY_COMMON, ARCH_POISON,
            "施加 {magic} 层压制。", "enemy", fx_numbing_brine, upgrade={"magic": 5},
            magic=3, keywords=("压制",)),
    CardDef("crippling_wave", "弹幕压制", 2, "skill", RARITY_UNCOMMON, ARCH_POISON,
            "对全体敌人施加 {magic} 层压制。", "all_enemies", fx_crippling_wave,
            upgrade={"magic": 3}, magic=2, keywords=("压制", "群体")),
    CardDef("hook_and_barb", "近距破甲", 0, "attack", RARITY_COMMON, ARCH_POISON,
            "造成 {damage} 点伤害，施加 {magic} 层破甲。", "enemy", fx_hook_and_barb,
            upgrade={"damage": 7}, damage=5, magic=1, keywords=("破甲", "攻击")),
    CardDef("catalyst_lance", "燃烧增幅", 2, "attack", RARITY_RARE, ARCH_POISON,
            "造成 {damage} 点伤害，再施加等同于目标当前燃烧层数的燃烧。", "enemy",
            fx_catalyst_lance, upgrade={"damage": 12}, damage=8, magic=4,
            keywords=("燃烧", "爆发")),
    CardDef("hemotoxin", "火势蔓延", 2, "skill", RARITY_RARE, ARCH_POISON,
            "使目标的燃烧层数翻倍。", "enemy", fx_hemotoxin, upgrade={"cost": 1},
            magic=2, keywords=("燃烧", "翻倍")),
    CardDef("toxin_burst", "烈焰引爆", 1, "attack", RARITY_UNCOMMON, ARCH_POISON,
            "造成等同于目标燃烧层数的伤害。", "enemy", fx_toxin_burst,
            upgrade={"cost": 0}, damage=0, keywords=("燃烧", "爆发")),
    CardDef("brine_spray", "燃烧弹齐射", 2, "attack", RARITY_UNCOMMON, ARCH_POISON,
            "造成 {damage} 点伤害，共 {hits} 次，并施加 {magic} 层压制。", "enemy",
            fx_brine_spray, upgrade={"damage": 8}, damage=6, magic=1, hits=3,
            keywords=("燃烧", "压制", "连击")),
    CardDef("bloodletting", "强征补给", 0, "skill", RARITY_COMMON, ARCH_POISON,
            "获得 2 点补给，失去 3 点总部耐久。", "self", fx_bloodletting,
            upgrade={"cost": 0}, exhaust=True, keywords=("补给", "风险")),
    CardDef("deep_malaise", "补给切断", -1, "skill", RARITY_RARE, ARCH_POISON,
            "X 费：施加 X 层压制与 2X 层燃烧。", "enemy", fx_deep_malaise,
            upgrade={"cost": 0}, magic=1, keywords=("燃烧", "压制", "X费")),
    CardDef("necrotic_grasp", "焦土推进", 1, "attack", RARITY_UNCOMMON, ARCH_POISON,
            "造成 {damage} 点伤害，回复 4 点总部耐久。", "enemy", fx_necrotic_grasp,
            upgrade={"damage": 9}, damage=6, keywords=("燃烧", "回复")),
    CardDef("vile_surge", "火线突进", 1, "attack", RARITY_UNCOMMON, ARCH_POISON,
            "造成 {damage} 点伤害，对全体敌人施加 {magic} 层燃烧。", "enemy",
            fx_vile_surge, upgrade={"damage": 6}, damage=4, magic=3,
            keywords=("燃烧", "群体")),
    CardDef("festering_hook", "燃烧弹突袭", 1, "attack", RARITY_COMMON, ARCH_POISON,
            "造成 {damage} 点伤害，施加 {magic} 层压制。", "enemy", fx_festering_hook,
            upgrade={"damage": 10}, damage=8, magic=2, keywords=("压制", "攻击")),
    CardDef("rot_barrage", "燃烧弹幕", 2, "attack", RARITY_UNCOMMON, ARCH_POISON,
            "造成 {damage} 点伤害，施加 {magic} 层破甲与 {magic2} 层燃烧。", "enemy",
            fx_rot_barrage, upgrade={"damage": 12}, damage=9, magic=2, magic2=2,
            keywords=("燃烧", "破甲")),
    CardDef("culling_tide", "火海收割", 2, "attack", RARITY_RARE, ARCH_POISON,
            "对全体敌人造成等同于其燃烧层数的伤害。", "all_enemies", fx_culling_tide,
            upgrade={"cost": 1}, damage=0, keywords=("燃烧", "群体", "爆发")),
    CardDef("withering_gaze", "弹药摧毁", 2, "attack", RARITY_UNCOMMON, ARCH_POISON,
            "造成 {damage} 点伤害，施加 {magic} 层弹药短缺。", "enemy", fx_withering_gaze,
            upgrade={"damage": 14}, damage=11, magic=2, keywords=("减益", "攻击")),

    # ================= 后勤 · 补给 (energy) — 24 张 =================
    CardDef("tide_pool", "补给线", 1, "power", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得能力：每回合额外获得 {magic} 点补给。", "self", fx_tide_pool,
            upgrade={"magic": 2}, magic=1, keywords=("补给", "能力")),
    CardDef("deep_current", "参谋调度", 1, "power", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得能力：每回合额外抽 {magic} 张牌。", "self", fx_deep_current,
            upgrade={"magic": 2}, magic=1, keywords=("抽牌", "能力")),
    CardDef("artifact_shell", "干扰弹", 1, "skill", RARITY_RARE, ARCH_ENERGY,
            "获得 {magic} 层干扰弹，抵挡下一次负面效果。", "self", fx_artifact_shell,
            upgrade={"magic": 2}, magic=1, exhaust=True, keywords=("干扰弹",)),
    CardDef("tidal_reserve", "弹药储备", 1, "power", RARITY_RARE, ARCH_ENERGY,
            "获得能力：回合结束时保留手牌。", "self", fx_tidal_reserve,
            upgrade={"cost": 0}, magic=1, keywords=("保留", "能力")),
    CardDef("abyssal_gate", "总动员令", 3, "power", RARITY_RARE, ARCH_ENERGY,
            "获得能力：每回合额外获得 1 点补给并抽 1 张牌。", "self", fx_abyssal_gate,
            upgrade={"cost": 2}, magic=1, keywords=("补给", "抽牌", "能力")),
    CardDef("electrify", "紧急调令", 1, "skill", RARITY_COMMON, ARCH_ENERGY,
            "抽 2 张牌，获得 1 点补给。", "self", fx_electrify, upgrade={"cost": 0},
            keywords=("抽牌", "补给")),
    CardDef("tide_knot", "弹药箱", 0, "attack", RARITY_COMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害。", "enemy", fx_tide_knot, upgrade={"damage": 5},
            damage=3, exhaust=True, keywords=("生成", "连射")),
    CardDef("chain_lightning", "连射压制", 1, "attack", RARITY_UNCOMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，本回合每打出一张牌额外 +2 伤害。", "enemy",
            fx_chain_lightning, upgrade={"damage": 6}, damage=4,
            keywords=("连射", "攻击")),
    CardDef("resonance", "协同射击", 0, "attack", RARITY_COMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，本回合每打出一张牌额外 +2 伤害。", "enemy",
            fx_resonance, upgrade={"damage": 5}, damage=3, keywords=("连射", "攻击")),
    CardDef("surge_draw", "补给征调", 1, "skill", RARITY_COMMON, ARCH_ENERGY,
            "抽 2 张牌。", "self", fx_surge_draw, upgrade={"cost": 0},
            keywords=("抽牌",)),
    CardDef("current_ribbon", "通讯兵", 2, "attack", RARITY_UNCOMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，抽 1 张牌。", "enemy", fx_current_ribbon,
            upgrade={"damage": 18}, damage=14, keywords=("抽牌", "攻击")),
    CardDef("energy_well", "野战油库", 0, "skill", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得 1 点补给，抽 1 张牌。", "self", fx_energy_well,
            upgrade={"cost": 0}, exhaust=True, keywords=("补给", "抽牌")),
    CardDef("lightning_pool", "连射指令", 1, "power", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得 {magic} 层连射：本回合每打出一张牌，下张攻击牌 +N 伤害。", "self",
            fx_lightning_pool, upgrade={"magic": 6}, magic=4,
            keywords=("连射", "能力")),
    CardDef("volt_lance", "电压突击", 1, "attack", RARITY_COMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，获得 1 点补给。", "enemy", fx_volt_lance,
            upgrade={"damage": 8}, damage=5, keywords=("补给", "攻击")),
    CardDef("buoyancy", "紧急补给", 1, "skill", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得 2 点补给与 {magic} 层连射。", "self", fx_buoyancy,
            upgrade={"magic": 2}, magic=1, keywords=("补给", "连射")),
    CardDef("tidal_echo", "无线电呼叫", 1, "attack", RARITY_UNCOMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，将一张「弹链」加入手牌。", "enemy", fx_tidal_echo,
            upgrade={"damage": 11}, damage=8, keywords=("连射", "生成")),
    CardDef("sonar_pulse", "侦察机侦察", 2, "skill", RARITY_RARE, ARCH_ENERGY,
            "抽 3 张牌，获得 1 点补给，将一张「沙袋胸墙」加入手牌。", "self", fx_sonar_pulse,
            upgrade={"cost": 1}, exhaust=True, keywords=("抽牌", "生成")),
    CardDef("whirl_engine", "引擎增压", 2, "attack", RARITY_UNCOMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，抽 1 张牌，获得 1 点补给。", "enemy", fx_whirl_engine,
            upgrade={"damage": 13}, damage=10, keywords=("补给", "抽牌", "攻击")),
    CardDef("ebbing_blade", "退壳突击", 1, "attack", RARITY_COMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，共 {hits} 次，抽 1 张牌。", "enemy", fx_ebbing_blade,
            upgrade={"damage": 8}, damage=6, hits=2, keywords=("抽牌", "连击")),
    CardDef("surge_protector", "补给护罩", 1, "skill", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得 {block} 点掩体与 {magic} 层连射。", "self", fx_surge_protector,
            upgrade={"block": 11}, block=8, magic=2, keywords=("掩体", "连射")),
    CardDef("chain_vein", "弹链", 0, "attack", RARITY_COMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，本回合每打出一张牌额外 +1 伤害。", "enemy",
            fx_chain_vein, upgrade={"damage": 8}, damage=5, exhaust=True,
            keywords=("生成", "连射")),
    CardDef("voltaic_shell", "装甲突袭", 2, "attack", RARITY_UNCOMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，共 {hits} 次。", "enemy", fx_voltaic_shell,
            upgrade={"damage": 16}, damage=12, hits=2, keywords=("攻击", "连击")),
    CardDef("current_lash", "机动打击", 1, "attack", RARITY_COMMON, ARCH_ENERGY,
            "造成 {damage} 点伤害，本回合每打出一张牌额外 +1 伤害，获得 1 点补给。",
            "enemy", fx_current_lash, upgrade={"damage": 8}, damage=6,
            keywords=("补给", "连射")),
    CardDef("whirlpool_extra", "地毯式轰炸", -1, "attack", RARITY_RARE, ARCH_ENERGY,
            "X 费：对全体敌人造成 X 次 4 点伤害。", "all_enemies", fx_whirlpool_extra,
            upgrade={"cost": 0}, damage=4, keywords=("群体", "X费")),
    CardDef("whale_fall_engine", "后勤引擎", 2, "power", RARITY_RARE, ARCH_ENERGY,
            "获得能力：每回合开始时获得 1 点补给并抽 1 张牌。", "self", fx_abyssal_gate,
            upgrade={"cost": 1}, magic=1, keywords=("补给", "抽牌", "能力")),
    CardDef("echo_chamber", "通讯中枢", 2, "power", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得能力：每次打出攻击牌后抽 1 张牌。", "self", fx_deep_current,
            upgrade={"magic": 2}, magic=1, keywords=("抽牌", "连射", "能力")),

    # ================= 唤灵 · 征召 (summon) — 24 张 =================
    CardDef("summon_calf", "征召步兵班", 1, "skill", RARITY_COMMON, ARCH_SUMMON,
            "征召「步兵班」（{magic} 总部耐久，{magic2} 攻击）。", "self", fx_summon_calf,
            upgrade={"magic": 12, "magic2": 6}, magic=8, magic2=4,
            keywords=("征召", "附属单位")),
    CardDef("summon_gull", "呼叫侦察机", 0, "skill", RARITY_COMMON, ARCH_SUMMON,
            "征召「侦察机」（{magic} 总部耐久，{magic2} 攻击）。", "self", fx_summon_gull,
            upgrade={"magic": 6, "magic2": 3}, magic=4, magic2=2, exhaust=True,
            keywords=("征召", "附属单位")),
    CardDef("summon_squid", "征召机枪组", 1, "skill", RARITY_COMMON, ARCH_SUMMON,
            "征召「机枪组」（{magic} 总部耐久，{magic2} 攻击）。", "self", fx_summon_squid,
            upgrade={"magic": 9, "magic2": 4}, magic=6, magic2=3,
            keywords=("征召", "附属单位")),
    CardDef("school_of_gulls", "双机编队", 1, "skill", RARITY_UNCOMMON, ARCH_SUMMON,
            "征召 2 只「侦察机」（各 {magic} 总部耐久，{magic2} 攻击）。", "self",
            fx_school_of_gulls, upgrade={"magic": 5}, magic=3, magic2=2,
            keywords=("征召", "群召")),
    CardDef("jelly_pulse", "迫击炮支援", 1, "attack", RARITY_COMMON, ARCH_SUMMON,
            "造成 {damage} 点伤害，征召「迫击炮组」（{magic} 总部耐久，{magic2} 攻击）。",
            "enemy", fx_jelly_pulse, upgrade={"damage": 8}, damage=5, magic=5,
            magic2=2, keywords=("征召", "压制")),
    CardDef("ritual_chant", "增援命令", 1, "power", RARITY_UNCOMMON, ARCH_SUMMON,
            "获得 {magic} 层增援：每回合开始叠加等量火力。", "self", fx_ritual_chant,
            upgrade={"magic": 2}, magic=1, keywords=("增援", "能力")),
    CardDef("blood_ritual", "血战增援", 1, "power", RARITY_RARE, ARCH_SUMMON,
            "失去 5 点总部耐久，获得 {magic} 层增援。", "self", fx_blood_ritual,
            upgrade={"magic": 3}, magic=2, keywords=("增援", "风险", "能力")),
    CardDef("sacrificial_tide", "敢死突击", 2, "attack", RARITY_UNCOMMON, ARCH_SUMMON,
            "造成 {damage} 点伤害，失去 8 点总部耐久。", "enemy", fx_sacrificial_tide,
            upgrade={"damage": 24}, damage=18, keywords=("风险", "攻击")),
    CardDef("summon_angler", "征召反坦克组", 2, "skill", RARITY_UNCOMMON, ARCH_SUMMON,
            "征召「反坦克组」（{magic} 总部耐久，{magic2} 攻击）。", "self", fx_summon_angler,
            upgrade={"magic": 14, "magic2": 7}, magic=10, magic2=5,
            keywords=("征召", "附属单位")),
    CardDef("summon_crab", "征召装甲车", 2, "skill", RARITY_UNCOMMON, ARCH_SUMMON,
            "征召「装甲车」（{magic} 总部耐久，{magic2} 攻击），获得 {block} 点掩体。",
            "self", fx_summon_crab, upgrade={"magic": 18}, magic=14, magic2=1,
            block=6, keywords=("征召", "掩体")),
    CardDef("tide_leviathan", "重型坦克支援", 3, "skill", RARITY_RARE, ARCH_SUMMON,
            "征召「重型坦克」（{magic} 总部耐久，{magic2} 攻击）。", "self",
            fx_tide_leviathan, upgrade={"magic": 30, "magic2": 10}, magic=22,
            magic2=8, exhaust=True, keywords=("征召", "附属单位")),
    CardDef("deep_echo", "炮火支援", 2, "power", RARITY_UNCOMMON, ARCH_SUMMON,
            "获得能力：每回合结束时对全体敌人造成 {magic} 点伤害。", "self",
            fx_deep_echo, upgrade={"magic": 8}, magic=5, keywords=("持续输出", "能力")),
    CardDef("ritual_chorus", "持续增援", 2, "power", RARITY_RARE, ARCH_SUMMON,
            "获得能力：每回合结束时获得 1 层增援。", "self", fx_ritual_chorus,
            upgrade={"cost": 1}, magic=1, keywords=("增援", "能力")),
    CardDef("whale_song", "工兵构筑", 2, "power", RARITY_RARE, ARCH_SUMMON,
            "获得能力：每回合结束时，每个附属单位为你提供 {magic} 点掩体。", "self",
            fx_whale_song, upgrade={"magic": 6}, magic=4, keywords=("征召", "掩体", "能力")),
    CardDef("necro_tide", "残部收编", 1, "power", RARITY_RARE, ARCH_SUMMON,
            "获得能力：附属单位死亡时，将一张「弹药箱」加入弃牌堆。", "self",
            fx_necro_tide, upgrade={"cost": 0}, magic=1, keywords=("征召", "能力")),
    CardDef("sacrifice", "弃车保帅", 1, "skill", RARITY_UNCOMMON, ARCH_SUMMON,
            "牺牲一个附属单位，获得等同于其总部耐久值的掩体与 2 点火力。", "self",
            fx_sacrifice, upgrade={"cost": 0}, keywords=("征召", "祭品")),
    CardDef("bone_chorus", "附属单位突击", 1, "attack", RARITY_UNCOMMON, ARCH_SUMMON,
            "对全体敌人造成（附属单位数量，至少 1）×3 的伤害。", "all_enemies",
            fx_bone_chorus, upgrade={"cost": 0}, damage=3,
            keywords=("征召", "群体")),
    CardDef("feed_the_deep", "征召突击队", 0, "skill", RARITY_UNCOMMON, ARCH_SUMMON,
            "失去 4 点总部耐久，征召「机枪组」（{magic} 总部耐久，{magic2} 攻击）。", "self",
            fx_feed_the_deep, upgrade={"magic": 9}, magic=6, magic2=3,
            keywords=("征召", "风险")),
    CardDef("kraken_grasp", "重火力压制", 2, "attack", RARITY_UNCOMMON, ARCH_SUMMON,
            "造成 {damage} 点伤害，共 {hits} 次，施加 {magic} 层压制。", "enemy",
            fx_kraken_grasp, upgrade={"damage": 6}, damage=4, hits=3, magic=2,
            keywords=("征召", "压制", "连击")),
    CardDef("abyssal_legion", "装甲集群", 3, "skill", RARITY_RARE, ARCH_SUMMON,
            "征召 3 只「迫击炮组」（各 {magic} 总部耐久，{magic2} 攻击）。", "self",
            fx_abyssal_legion, upgrade={"magic": 7}, magic=5, magic2=2, exhaust=True,
            keywords=("征召", "群召")),
    CardDef("spawn_pod", "兵员补充", 1, "skill", RARITY_COMMON, ARCH_SUMMON,
            "征召「步兵班」（{magic} 总部耐久，{magic2} 攻击）。", "self", fx_spawn_pod,
            upgrade={"magic": 9, "magic2": 4}, magic=6, magic2=3,
            keywords=("征召", "附属单位")),
    CardDef("tentacle_lash", "附属单位齐射", 1, "attack", RARITY_UNCOMMON, ARCH_SUMMON,
            "每个附属单位各对目标造成一次等同于其攻击力的伤害。", "enemy",
            fx_tentacle_lash, upgrade={"cost": 0}, damage=0,
            keywords=("征召", "连击")),
    CardDef("tide_serpent", "机械化步兵", 2, "skill", RARITY_UNCOMMON, ARCH_SUMMON,
            "征召「机枪组」（{magic} 总部耐久，{magic2} 攻击）并抽 1 张牌。", "self",
            fx_summon_squid, upgrade={"magic": 9}, magic=6, magic2=3,
            keywords=("征召", "抽牌")),
    CardDef("leviathan_wake", "坦克洪流", 3, "attack", RARITY_RARE, ARCH_SUMMON,
            "对全体敌人造成（附属单位数量，至少 1）×5 的伤害并征召「步兵班」（{magic} 总部耐久）。",
            "all_enemies", fx_bone_chorus, upgrade={"magic": 9}, damage=5, magic=6,
            magic2=3, keywords=("征召", "群体")),

    # ================= 状态牌 / 诅咒 — 12 张 =================
    CardDef("wound", "伤口", -2, "status", RARITY_COMMON, ARCH_ATTACK,
            "无法打出。", "none", fx_wound, keywords=("状态", "不可打出")),
    CardDef("dazed", "恍惚", -2, "status", RARITY_COMMON, ARCH_ENERGY,
            "不稳固。无法打出。", "none", fx_dazed, ethereal=True,
            keywords=("状态", "不可打出", "不稳固")),
    CardDef("slimed", "油污", 1, "status", RARITY_COMMON, ARCH_POISON,
            "移除。", "self", fx_slimed, exhaust=True, keywords=("状态",)),
    CardDef("burn", "灼伤", -2, "status", RARITY_UNCOMMON, ARCH_ATTACK,
            "回合结束时受到 2 点伤害。", "none", fx_burn,
            keywords=("状态", "不可打出")),
    CardDef("decay", "锈蚀", -2, "status", RARITY_UNCOMMON, ARCH_POISON,
            "回合结束时受到 2 点伤害。", "none", fx_decay,
            keywords=("状态", "不可打出")),
    CardDef("plague_spore", "哑弹", -2, "status", RARITY_UNCOMMON, ARCH_POISON,
            "回合结束时受到 2 点伤害。", "none", fx_decay,
            keywords=("状态", "不可打出", "生成")),
    CardDef("doubt", "动摇", -2, "curse", RARITY_UNCOMMON, ARCH_POISON,
            "无法打出。回合结束时获得 1 层压制。", "self", fx_doubt, retain=True,
            keywords=("诅咒", "不可打出")),
    CardDef("shame", "耻辱", -2, "curse", RARITY_UNCOMMON, ARCH_BLOCK,
            "无法打出。回合结束时获得 1 层混乱。", "self", fx_shame, retain=True,
            keywords=("诅咒", "不可打出")),
    CardDef("regret", "悔恨", -2, "curse", RARITY_RARE, ARCH_ENERGY,
            "无法打出。回合结束时每有一张手牌便失去 1 点总部耐久。", "self", fx_regret,
            retain=True, keywords=("诅咒", "不可打出")),
    CardDef("pain", "痛楚", -2, "curse", RARITY_RARE, ARCH_ATTACK,
            "无法打出。回合结束时失去 1 点总部耐久。", "self", fx_pain, retain=True,
            keywords=("诅咒", "不可打出")),
    CardDef("curse_of_the_deep", "战争之咒", -2, "curse", RARITY_RARE, ARCH_SUMMON,
            "无法打出。回合结束时失去 3 点总部耐久。", "self", fx_curse_of_the_deep,
            keywords=("诅咒", "不可打出")),
    CardDef("barnacle_curse", "辎重拖累", -2, "curse", RARITY_UNCOMMON, ARCH_BLOCK,
            "无法打出。回合结束时获得 1 层混乱。", "self", fx_shame, ethereal=True,
            keywords=("诅咒", "不可打出", "不稳固")),

    # ---- A 组 · 破甲 ----
    CardDef("armor_crack", "破甲弹", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，施加 {magic} 层破甲（受到伤害 +50%）。",
            "enemy", fx_armor_crack,
            upgrade={"magic": 4, "damage": 7}, damage=5, magic=3,
            keywords=("破甲",)),
    CardDef("siege_shell", "攻坚弹", 2, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，施加 {magic} 层破甲，获得 4 点掩体。",
            "enemy", fx_siege_shell,
            upgrade={"damage": 18}, damage=14, magic=2,
            keywords=("破甲", "火力")),
    CardDef("mark_target", "标记目标", 0, "skill", RARITY_COMMON, ARCH_ATTACK,
            "施加 {magic} 层破甲，抽 1 张牌。", "enemy", fx_mark_target,
            upgrade={"magic": 5}, magic=4, keywords=("破甲", "抽牌")),
    CardDef("chain_breach", "连环破袭", 1, "skill", RARITY_UNCOMMON, ARCH_ATTACK,
            "对**全体**敌人各施加 {magic} 层破甲。", "none", fx_chain_breach,
            upgrade={"magic": 3, "cost": 0}, magic=2, keywords=("破甲", "群体")),

    # ---- B 组 · 增伤 ----
    CardDef("mass_mobilize", "全军动员", 2, "power", RARITY_UNCOMMON, ARCH_ATTACK,
            "获得火力：基础 2 点，本回合每已打出一张牌再 +1（最多 +3）。",
            "self", fx_mass_mobilize, upgrade={"cost": 1},
            magic=2, keywords=("火力", "成长")),
    CardDef("last_stand", "背水一战", 1, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "**每损失 8 点耐久**获得 1 点火力（最多 8），并获得掩体。",
            "self", fx_last_stand, upgrade={"cost": 0},
            keywords=("火力", "残血")),
    CardDef("arsenal_overload", "弹药过载", 1, "skill", RARITY_RARE, ARCH_ATTACK,
            "获得 {magic} 点火力，但立即失去 4 点耐久。", "self",
            fx_arsenal_overload, upgrade={"magic": 7}, magic=5, exhaust=True,
            keywords=("火力", "自伤")),

    # ---- C 组 · 换攻（自己变脆）----
    CardDef("all_in", "孤注一掷", 1, "skill", RARITY_UNCOMMON, ARCH_ATTACK,
            "获得 {magic} 点火力与 1 点补给，但自身获得 2 层脆弱。",
            "self", fx_all_in, upgrade={"magic": 6}, magic=4,
            keywords=("火力", "脆弱", "风险")),
    CardDef("reckless_assault", "蛮勇突击", 1, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 {damage} 点伤害，自身失去 3 点耐久。", "enemy",
            fx_reckless_assault, upgrade={"damage": 21}, damage=16,
            keywords=("火力", "自伤")),

    # ---- D 组 · 条件牌 ----
    CardDef("scrap_heap", "废铁堆", 0, "attack", RARITY_COMMON, ARCH_ATTACK,
            "造成 2 点伤害，**手牌每有 1 张再 +2**。", "enemy", fx_scrap_heap,
            upgrade={"cost": 0, "damage": 3}, damage=2,
            keywords=("条件", "手牌")),
    CardDef("ambush", "伏击", 1, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "**本回合第一张出牌**时造成 {damage} 点伤害，否则只有 5 点。",
            "enemy", fx_ambush, upgrade={"damage": 24}, damage=18,
            keywords=("条件", "先手")),
    CardDef("overrun", "碾压", 1, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成 4 点伤害，**每个存活敌人再 +7**（敌人越多越强）。",
            "enemy", fx_overrun, upgrade={"damage": 7}, damage=4,
            keywords=("条件", "群体")),
    CardDef("bullet_hail", "弹幕覆盖", 1, "attack", RARITY_RARE, ARCH_ATTACK,
            "对目标造成 6 点伤害，**每个存活敌人各打一次**。", "enemy",
            fx_bullet_hail, upgrade={"damage": 8}, damage=6,
            keywords=("条件", "多段")),
    CardDef("desperate_gamble", "绝境豪赌", 0, "skill", RARITY_RARE, ARCH_ATTACK,
            "**耐久低于 30%** 时：获得 6 火力、2 补给、抽 2 张；否则只获得 3 掩体。",
            "self", fx_desperate_gamble, upgrade={"cost": 0},
            keywords=("条件", "残血")),
    CardDef("salvage", "回收残骸", 0, "skill", RARITY_COMMON, ARCH_ENERGY,
            "抽 1 张牌；**手牌 ≤1 张时改为抽 4 张**。", "self", fx_salvage,
            upgrade={"cost": 0}, keywords=("条件", "抽牌")),
    CardDef("deadweight_shot", "负重射击", 0, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "造成**本回合已出牌数 × 3** 点伤害（至少 3）。", "enemy",
            fx_deadweight_shot, upgrade={"magic": 4}, magic=3,
            keywords=("条件", "连射")),
    CardDef("siege_momentum", "攻势蓄能", 0, "skill", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得 1 点火力，抽 1 张牌，获得 1 点补给。", "self",
            fx_siege_momentum, upgrade={"magic": 2}, magic=1,
            keywords=("成长", "循环")),
    CardDef("veteran_instinct", "老兵直觉", 1, "skill", RARITY_UNCOMMON, ARCH_BLOCK,
            "获得 4 点掩体；**抽牌堆 ≤5 张时**额外获得 3 点火力。", "self",
            fx_veteran_instinct, upgrade={"block": 7}, block=4,
            keywords=("条件", "掩体")),
    CardDef("fortify_line", "死守防线", 2, "power", RARITY_RARE, ARCH_BLOCK,
            "获得 {block} 点掩体与 {magic} 层装甲板（每次受击减伤）。",
            "self", fx_fortify_line, upgrade={"block": 14}, block=10, magic=2,
            keywords=("掩体", "能力")),
    CardDef("zero_hour", "零点攻势", 1, "skill", RARITY_RARE, ARCH_ATTACK,
            "**本回合第一张出牌**时：全体施加 3 层破甲并抽 2 张；否则只抽 1 张。",
            "none", fx_zero_hour, upgrade={"cost": 0},
            keywords=("条件", "破甲", "群体")),

    # ---- A 指挥点 ----
    CardDef("supply_drop", "空投补给", 0, "skill", RARITY_COMMON, ARCH_ENERGY,
            "获得 2 点指挥点，抽 1 张牌。", "self", fx_supply_drop,
            upgrade={"cost": 0}, keywords=("指挥点", "抽牌")),
    CardDef("logistics_chain", "后勤链", 0, "skill", RARITY_COMMON, ARCH_ENERGY,
            "获得 2 点指挥点。", "self", fx_logistics_chain,
            upgrade={"magic": 3}, magic=2, keywords=("指挥点",)),
    CardDef("all_hands_on_deck", "全员就位", 1, "skill", RARITY_UNCOMMON, ARCH_ENERGY,
            "获得 {magic} 点指挥点，抽 2 张牌。", "self", fx_all_hands_on_deck,
            upgrade={"magic": 4}, magic=3, keywords=("指挥点", "抽牌")),
    CardDef("emergency_requisition", "紧急征用", 0, "skill", RARITY_UNCOMMON,
            ARCH_ENERGY,
            "获得 {magic} 点指挥点，失去 4 点耐久。", "self",
            fx_emergency_requisition, upgrade={"magic": 4}, magic=3,
            keywords=("指挥点", "自伤")),
    CardDef("winter_stockpile", "冬季储备", 1, "skill", RARITY_RARE, ARCH_ENERGY,
            "获得 {magic} 点指挥点，抽 1 张牌。", "self", fx_winter_stockpile,
            upgrade={"magic": 5}, magic=4, exhaust=True,
            keywords=("指挥点", "爆发")),

    # ---- B 干扰 ----
    CardDef("suppress_fire", "压制射击", 1, "attack", RARITY_COMMON, ARCH_POISON,
            "造成 {damage} 点伤害，施加 {magic} 层虚弱（敌人攻击 -25%）。",
            "enemy", fx_suppress_fire, upgrade={"magic": 4}, damage=6, magic=3,
            keywords=("虚弱", "干扰")),
    CardDef("disarm", "缴械", 1, "skill", RARITY_UNCOMMON, ARCH_POISON,
            "施加 {magic} 层虚弱与 3 层脆弱，获得 6 点掩体。", "enemy",
            fx_disarm, upgrade={"cost": 0}, magic=2, block=6,
            keywords=("虚弱", "脆弱", "干扰")),
    CardDef("jam_comms", "干扰通讯", 1, "skill", RARITY_UNCOMMON, ARCH_POISON,
            "对**全体**敌人施加 {magic} 层虚弱。", "none", fx_jam_comms,
            upgrade={"magic": 4}, magic=3, keywords=("虚弱", "群体")),
    CardDef("break_morale", "瓦解士气", 1, "attack", RARITY_UNCOMMON, ARCH_POISON,
            "造成 {damage} 点伤害，并使其失去 {magic} 点火力。", "enemy",
            fx_break_morale, upgrade={"magic": 4}, damage=5, magic=3,
            keywords=("削弱", "干扰")),
    CardDef("scatter", "驱散队形", 1, "skill", RARITY_COMMON, ARCH_POISON,
            "对**全体**敌人施加 2 层脆弱，抽 1 张牌。", "none", fx_scatter,
            upgrade={"cost": 0}, keywords=("脆弱", "群体", "抽牌")),
    CardDef("rust_rounds", "锈蚀弹药", 1, "attack", RARITY_COMMON, ARCH_POISON,
            "造成 {damage} 点伤害，施加 {magic} 层燃烧。", "enemy",
            fx_rust_rounds, upgrade={"magic": 7}, damage=3, magic=5,
            keywords=("燃烧", "持续")),

    # ---- C 范围攻击 ----
    CardDef("carpet_bomb", "地毯式轰炸", 2, "attack", RARITY_UNCOMMON, ARCH_ATTACK,
            "对**全体**敌人各造成 {damage} 点伤害。", "all_enemies",
            fx_carpet_bomb, upgrade={"damage": 14}, damage=10,
            keywords=("群体", "火力")),
    CardDef("artillery_barrage", "炮火覆盖", 2, "attack", RARITY_UNCOMMON,
            ARCH_ATTACK,
            "对**全体**敌人造成 {damage} 点伤害并施加 2 层破甲。",
            "all_enemies", fx_artillery_barrage, upgrade={"damage": 10},
            damage=7, keywords=("群体", "破甲")),
    CardDef("scorched_earth", "焦土政策", 1, "attack", RARITY_RARE, ARCH_ATTACK,
            "对**全体**敌人造成 {damage} 点伤害，自身失去 5 点耐久。",
            "all_enemies", fx_scorched_earth, upgrade={"damage": 22},
            damage=16, keywords=("群体", "自伤")),
    CardDef("shrapnel_storm", "破片风暴", 2, "attack", RARITY_RARE, ARCH_ATTACK,
            "对**全体**敌人造成 3 次 {damage} 点伤害（火力加成 3 次）。",
            "all_enemies", fx_shrapnel_storm, upgrade={"damage": 6},
            damage=4, keywords=("群体", "多段")),

    # ---- D 科研 ----
    CardDef("research_basic", "初级科研", 1, "skill", RARITY_COMMON, ARCH_ENERGY,
            "抽 2 张牌，获得 1 点火力。（科研链的起点）", "self",
            fx_research_basic, upgrade={"cost": 0}, keywords=("科研", "成长")),
    CardDef("research_advanced", "高级科研", 1, "skill", RARITY_UNCOMMON,
            ARCH_ENERGY,
            "抽 2 张牌并获得 2 点火力；**手牌中每有一张科研牌再 +1**。",
            "self", fx_research_advanced, upgrade={"cost": 0},
            magic=2, keywords=("科研", "成长")),
    CardDef("research_breakthrough", "科研突破", 2, "power", RARITY_RARE,
            ARCH_ENERGY,
            "获得 3 点火力；**本局每打过一张科研牌再 +2**（最多 +8）。",
            "self", fx_research_breakthrough, upgrade={"cost": 1},
            keywords=("科研", "成长", "能力")),
    CardDef("prototype_weapon", "原型兵器", 3, "attack", RARITY_RARE, ARCH_ATTACK,
            "【超模】对**全体**敌人造成 {damage} 点伤害并施加 3 层破甲。",
            "all_enemies", fx_prototype_weapon, upgrade={"damage": 28},
            damage=22, exhaust=True, keywords=("科研", "群体", "超模")),

    # ---- E 单位 ----
    CardDef("deploy_riflemen", "部署步兵班", 1, "power", RARITY_COMMON,
            ARCH_SUMMON,
            "征召「步兵班」（{magic} 耐久 / {magic2} 攻击），每回合自动开火。",
            "self", fx_deploy_riflemen, upgrade={"magic": 11},
            magic=8, magic2=4, keywords=("单位", "持续")),
    CardDef("deploy_mg_nest", "部署机枪巢", 2, "power", RARITY_UNCOMMON,
            ARCH_SUMMON,
            "征召「机枪巢」（{magic} 耐久 / {magic2} 攻击）。", "self",
            fx_deploy_mg_nest, upgrade={"magic": 18}, magic=14, magic2=3,
            keywords=("单位", "耐打")),
    CardDef("deploy_tank", "部署中型坦克", 2, "power", RARITY_UNCOMMON,
            ARCH_SUMMON,
            "征召「中型坦克」（{magic} 耐久 / {magic2} 攻击）。", "self",
            fx_deploy_tank, upgrade={"magic2": 9}, magic=12, magic2=7,
            keywords=("单位", "火力")),
    CardDef("deploy_artillery", "部署野战炮", 2, "power", RARITY_UNCOMMON,
            ARCH_SUMMON,
            "征召「野战炮」（{magic} 耐久 / {magic2} 攻击，很脆）。", "self",
            fx_deploy_artillery, upgrade={"magic": 8}, magic=6, magic2=10,
            keywords=("单位", "高攻")),
    CardDef("deploy_engineer", "部署工兵连", 2, "power", RARITY_COMMON,
            ARCH_SUMMON,
            "获得 8 点掩体，并征召「工兵连」（{magic} 耐久 / {magic2} 攻击）。",
            "self", fx_deploy_engineer, upgrade={"block": 12}, magic=10, magic2=2,
            block=8, keywords=("单位", "掩体")),
    CardDef("deploy_command_tank", "部署指挥坦克", 3, "power", RARITY_RARE,
            ARCH_SUMMON,
            "征召「指挥坦克」（{magic} 耐久 / {magic2} 攻击），并获得 2 点火力。",
            "self", fx_deploy_command_tank, upgrade={"magic": 20},
            magic=15, magic2=6, keywords=("单位", "火力", "能力")),
]


CARD_DB: Dict[str, CardDef] = {c.id: c for c in CARD_LIST}


# --------------------------------------------------------------------------
# 初始卡组 / 查询接口
# --------------------------------------------------------------------------

STARTER_DECK: List[str] = (
    ["strike"] * 5 + ["defend"] * 4 + ["corrode_bite"]
)
"""初始卡组（10 张）：5 步枪齐射 + 4 构筑掩体 + 1 纵火射击。"""

STARTER_RELIC_ID = "broken_compass"


# 作弊/调试专属卡牌 id 前缀。它们由 core/cheats.py 在首次使用时注入
# ``CARD_DB``，**不属于**游戏内容集，因此 all_cards() 不返回它们
# （否则「CARD_DB 数量 == all_cards() 数量」这条不变式会被打破）。
CHEAT_CARD_PREFIX = "cheat_"


def is_cheat_card(card_id: str) -> bool:
    """是不是作弊/调试专属卡（不进图鉴、不算内容量）。"""
    return str(card_id).startswith(CHEAT_CARD_PREFIX)


def all_cards() -> List[CardDef]:
    """全部**游戏内容**卡牌（不含作弊卡）。"""
    return list(CARD_LIST)


def cards_by_arch(arch: str) -> List[CardDef]:
    return [c for c in CARD_LIST if c.arch == arch]


def cards_by_type(type_name: str) -> List[CardDef]:
    return [c for c in CARD_LIST if c.type == type_name]


def cards_by_rarity(rarity: str) -> List[CardDef]:
    return [c for c in CARD_LIST if c.rarity == rarity]


def get_card(def_id: str) -> Optional[CardDef]:
    return CARD_DB.get(def_id)


def playable_cards() -> List[CardDef]:
    """可进入奖励池的卡（排除初始牌与状态/诅咒）。"""
    return [c for c in CARD_LIST
            if c.rarity != RARITY_BASIC and c.type not in ("status", "curse")]


def random_card_pool(rng: random.Random, rarity: Optional[str] = None) -> List[CardDef]:
    """返回打乱后的候选卡池。rarity 为 None 时按 60/30/10 权重抽取三选一池。"""
    if rarity is not None:
        pool = [c for c in playable_cards() if c.rarity == rarity]
        if not pool:
            pool = playable_cards()
        out = list(pool)
        rng.shuffle(out)
        return out

    buckets = {
        RARITY_COMMON: [c for c in playable_cards() if c.rarity == RARITY_COMMON],
        RARITY_UNCOMMON: [c for c in playable_cards() if c.rarity == RARITY_UNCOMMON],
        RARITY_RARE: [c for c in playable_cards() if c.rarity == RARITY_RARE],
    }
    for b in buckets.values():
        rng.shuffle(b)
    out: List[CardDef] = []
    for _ in range(3):
        roll = rng.random()
        key = RARITY_COMMON if roll < 0.60 else (RARITY_UNCOMMON if roll < 0.90 else RARITY_RARE)
        if buckets[key]:
            out.append(buckets[key].pop())
        else:
            for alt in (RARITY_COMMON, RARITY_UNCOMMON, RARITY_RARE):
                if buckets[alt]:
                    out.append(buckets[alt].pop())
                    break
    return out


def status_cards() -> List[CardDef]:
    return [c for c in CARD_LIST if c.type == "status"]


def curse_cards() -> List[CardDef]:
    return [c for c in CARD_LIST if c.type == "curse"]


# --------------------------------------------------------------------------
# 静态引用审计（BUG #9 防线）
# --------------------------------------------------------------------------
# 背景：题材改写曾把 fx_sonar_pulse 里的 "whale_bone_screen" 误写成
# "whale_bone_guard"，导致玩家打出该牌后下一回合 end_turn() 抛 KeyError。
# 这类「幽灵 id」编译期无法发现（字符串字面量），因此在这里做静态扫描。
#
# 用法：
#     from core.cards import audit_card_references
#     problems = audit_card_references()      # 空列表 = 健康
#     audit_all_references()                  # 四库交叉引用一次全查

def _module_source(name: str) -> str:
    """读取同包内某模块的源码文本。"""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _literal_refs(src: str, funcs: List[str]) -> set:
    """抓取形如 func(ctx, "some_id") / func(run, "some_id") 的字面量 id 参数。"""
    import re
    found = set()
    for fn in funcs:
        # 第一个参数是 ctx/run 等，第二个参数是字符串字面量 id
        pat = re.compile(
            re.escape(fn) + r'\(\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']'
        )
        found |= set(pat.findall(src))
    return found


def audit_card_references() -> List[str]:
    """返回所有引用了不存在卡 id 的位置。空列表 = 健康。

    覆盖这些引用入口：
      * cards.py 内部   _add_hand / _add_draw / add_card_to_hand / add_card_to_draw
      * events.py       _add_card(run, "...") / run.add_card("...")
      * enemies.py      理论上不引用卡牌，一并扫描以防万一
    """
    problems: List[str] = []

    # --- cards.py 自身的卡牌引用 ---
    src = _module_source("cards")
    refs = _literal_refs(src, ["_add_hand", "_add_draw", "_add_discard",
                               "add_card_to_hand", "add_card_to_draw",
                               "add_card_to_discard"])
    for r in sorted(refs):
        if r not in CARD_DB:
            problems.append("cards.py 引用了不存在的卡 id: %r" % r)

    # --- events.py 的卡牌引用 ---
    esrc = _module_source("events")
    erefs = _literal_refs(esrc, ["_add_card", "add_card"])
    for r in sorted(erefs):
        if r not in CARD_DB:
            problems.append("events.py 引用了不存在的卡 id: %r" % r)

    # --- enemies.py（当前不引用卡牌；若将来引用会被这里抓住）---
    nsrc = _module_source("enemies")
    nrefs = _literal_refs(nsrc, ["_add_hand", "_add_draw", "_add_card", "add_card_to_hand"])
    for r in sorted(nrefs):
        if r not in CARD_DB:
            problems.append("enemies.py 引用了不存在的卡 id: %r" % r)

    return problems


def audit_all_references() -> List[str]:
    """四库（cards / relics / enemies / events）交叉引用一次性全查。

    检查项：
      1. cards.py 内部引用的卡 id 存在
      2. events.py 引用的卡 id / 遗物 id / 药水 id 存在
      3. relics.py 引用的卡 id 存在（若有）
      4. 各库自身 id 与 DB 键一致、无重复
      5. STARTER_DECK / STARTER_RELIC 指向真实存在的数据
    """
    problems: List[str] = []

    # 1) 卡牌引用
    problems.extend(audit_card_references())

    # 2) events.py 的遗物与药水引用
    esrc = _module_source("events")
    try:
        from core import relics as _R
        relic_ids = set(_R.RELIC_DB)
    except Exception:
        relic_ids = set()
    for r in sorted(_literal_refs(esrc, ["_add_relic", "add_relic"])):
        if r not in relic_ids:
            problems.append("events.py 引用了不存在的遗物 id: %r" % r)

    potion_ids = set(globals().get("_POTION_IDS_FOR_AUDIT", ()))
    try:
        from core import events as _EV
        potion_ids = set(getattr(_EV, "POTION_DB", {}))
    except Exception:
        pass
    for r in sorted(_literal_refs(esrc, ["_add_potion", "add_potion"])):
        if r not in potion_ids:
            problems.append("events.py 引用了不存在的药水 id: %r" % r)

    # 3) 各库内部一致性
    for cid, cd in CARD_DB.items():
        if cd.id != cid:
            problems.append("CARD_DB 键 %r != CardDef.id %r" % (cid, cd.id))
    if len(CARD_DB) != len(CARD_LIST):
        problems.append("CARD_DB 存在重复卡 id（%d vs %d）" % (len(CARD_DB), len(CARD_LIST)))
    for cid in STARTER_DECK:
        if cid not in CARD_DB:
            problems.append("STARTER_DECK 引用了不存在的卡 id: %r" % cid)
    if STARTER_RELIC_ID:
        try:
            from core import relics as _R2
            if STARTER_RELIC_ID not in _R2.RELIC_DB:
                problems.append("STARTER_RELIC_ID 指向不存在的遗物: %r" % STARTER_RELIC_ID)
        except Exception:
            pass

    # 4) 敌人招式 / 遭遇引用
    try:
        from core import enemies as _E
        for eid, ed in _E.ENEMY_DB.items():
            if ed.id != eid:
                problems.append("ENEMY_DB 键 %r != EnemyDef.id %r" % (eid, ed.id))
            if not ed.moves:
                problems.append("敌人 %r 没有招式" % eid)
        for act, table in _E.ENCOUNTERS.items():
            for kind, lst in table.items():
                for enc in lst:
                    for e in enc.get("enemies", ()):
                        if e not in _E.ENEMY_DB:
                            problems.append("遭遇 act%d/%s 引用不存在的敌人: %r" % (act, kind, e))
    except Exception as exc:  # pragma: no cover
        problems.append("敌人库审计异常: %r" % (exc,))

    # 5) 遗物库自身
    try:
        from core import relics as _R3
        for rid, rd in _R3.RELIC_DB.items():
            if rd.id != rid:
                problems.append("RELIC_DB 键 %r != RelicDef.id %r" % (rid, rd.id))
            if rd.trigger not in _R3.TRIGGERS:
                problems.append("遗物 %r 使用了未知 trigger: %r" % (rid, rd.trigger))
        if _R3.STARTER_RELIC not in _R3.RELIC_DB:
            problems.append("STARTER_RELIC 指向不存在的遗物: %r" % _R3.STARTER_RELIC)
    except Exception as exc:  # pragma: no cover
        problems.append("遗物库审计异常: %r" % (exc,))

    return problems


__all__ = [
    "RARITY_BASIC", "RARITY_COMMON", "RARITY_UNCOMMON", "RARITY_RARE",
    "ARCH_ATTACK", "ARCH_BLOCK", "ARCH_POISON", "ARCH_ENERGY", "ARCH_SUMMON", "ARCHS",
    "BUFF_STRENGTH", "BUFF_DEXTERITY", "BUFF_VULNERABLE", "BUFF_WEAK", "BUFF_FRAIL",
    "BUFF_POISON", "BUFF_THORNS", "BUFF_METALLICIZE", "BUFF_RITUAL", "BUFF_ARTIFACT",
    "BUFF_PLATED_ARMOR", "BUFF_REGENERATE", "BUFF_INTANGIBLE", "BUFF_STRENGTH_DOWN",
    "BUFF_BARRIER", "BUFF_CHAIN", "BUFF_ENVENOM", "BUFF_ACCURACY",
    "POWER_SHELLGUARD", "POWER_TIDEPOOL", "POWER_DEEP_CURRENT", "POWER_TIDAL_RESERVE",
    "POWER_BARNACLE", "POWER_VENOM_ECHO", "POWER_DEADWATER", "POWER_CORAL",
    "POWER_ABYSSAL_GATE", "POWER_WHALE_SONG", "POWER_DEEP_ECHO", "POWER_RITUAL_CHORUS",
    "POWER_NECROTIDE",
    "MINION_WHALE_CALF", "MINION_GULL", "MINION_SQUID", "MINION_JELLY",
    "MINION_ANGLER", "MINION_CRAB", "MINION_LEVIATHAN",
    "CardDef", "CardInstance", "CARD_DB", "CARD_LIST", "STARTER_DECK", "STARTER_RELIC_ID",
    "make_card", "all_cards", "cards_by_arch", "cards_by_type", "cards_by_rarity",
    "get_card", "playable_cards", "random_card_pool", "status_cards", "curse_cards",
    "resolve_text", "audit_card_references", "audit_all_references",
]
