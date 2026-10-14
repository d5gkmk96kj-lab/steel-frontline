# -*- coding: utf-8 -*-
"""钢铁战线 Steel Frontline —— 事件 / 商店 / 宝箱数据。

严格遵循 ARCHITECTURE.md 附录 A.4（冻结接口）：

    EventChoice(label, desc, effect, requires=None)
    EventDef(id, name, act, text, choices, art="")
    EVENT_DB: Dict[str, EventDef]          # >= 22
    random_event(rng, act, seen) -> EventDef
    SHOP_CARD_PRICE / SHOP_RELIC_PRICE / SHOP_POTION_PRICE / SHOP_REMOVE_PRICE_BASE
    build_shop_inventory(rng, act, ascension) -> dict
    TREASURE_TIERS
    roll_treasure(rng, act) -> dict

设计约束：
* 本模块 **import 时即可用**，不依赖 engine / run（避免循环 import）。
* 事件 effect 签名 ``fn(run) -> str``，只调用 lead 冻结的 RunState 公开方法：
  ``heal / add_gold / add_card / remove_card / upgrade_card / add_relic /
  add_potion / hp / max_hp / gold / deck / rng``，以及对可选方法的防御性探测。
* 所有随机走传入的 ``rng``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import cards as C
from core import relics as R


# --------------------------------------------------------------------------
# 冻结数据类
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EventChoice:
    label: str            # 按钮文字
    desc: str             # 结果预告
    effect: Callable[[Any], str]                      # fn(run) -> 结果叙述文本
    requires: Optional[Callable[[Any], bool]] = None  # 不满足则灰显


@dataclass(frozen=True)
class EventDef:
    id: str
    name: str
    act: int
    text: str
    choices: tuple        # tuple[EventChoice, ...]
    art: str = ""


# --------------------------------------------------------------------------
# 价格常量（附录 A.4 冻结值）
# --------------------------------------------------------------------------

SHOP_CARD_PRICE = {"common": 50, "uncommon": 75, "rare": 150}
SHOP_RELIC_PRICE = {"common": 150, "uncommon": 200, "rare": 280, "shop": 180}
SHOP_POTION_PRICE = 60
SHOP_REMOVE_PRICE_BASE = 75      # 每次删卡 +25

TREASURE_TIERS = ("gold", "relic", "potion", "curse_relic")

# 药水表（run.add_potion(pid) 使用；纯数据，不依赖 engine）
POTION_DB: Dict[str, dict] = {
    "potion_heal": {"name": "战地急救包", "text": "回复 20 点总部耐久。"},
    "potion_strength": {"name": "燃烧弹补给", "text": "获得 3 点火力。"},
    "potion_block": {"name": "沙袋补给", "text": "获得 15 点掩体。"},
    "potion_poison": {"name": "凝固汽油瓶", "text": "对目标施加 12 层燃烧。"},
    "potion_energy": {"name": "紧急补给令", "text": "获得 2 点补给。"},
    "potion_draw": {"name": "加密电文", "text": "抽 3 张卡。"},
    "potion_weak": {"name": "震爆弹", "text": "对全体敌人施加 3 层压制。"},
    "potion_fear": {"name": "破甲弹", "text": "对全体敌人施加 3 层破甲。"},
    "potion_artifact": {"name": "干扰弹碎片", "text": "获得 2 层干扰弹。"},
    "potion_bomb": {"name": "重型航空炸弹", "text": "对所有敌人造成 25 点伤害。"},
}

POTION_IDS: Tuple[str, ...] = tuple(POTION_DB.keys())


# --------------------------------------------------------------------------
# run 方法防御性封装（只调用冻结的公开面）
# --------------------------------------------------------------------------

def _heal(run, n: int) -> None:
    fn = getattr(run, "heal", None)
    if fn is not None:
        fn(n)


def _add_gold(run, n: int) -> int:
    fn = getattr(run, "add_gold", None)
    if fn is not None:
        return int(fn(n) or 0)
    run.gold = int(getattr(run, "gold", 0)) + int(n)
    return int(n)


def _add_card(run, def_id: str, upgraded: int = 0) -> None:
    fn = getattr(run, "add_card", None)
    if fn is not None:
        try:
            fn(def_id, upgraded=upgraded)
        except TypeError:  # pragma: no cover
            fn(def_id)


def _add_relic(run, relic_id: str) -> None:
    fn = getattr(run, "add_relic", None)
    if fn is not None:
        fn(relic_id)


def _add_potion(run, potion_id: str) -> None:
    fn = getattr(run, "add_potion", None)
    if fn is not None:
        fn(potion_id)


def _deck(run) -> list:
    return list(getattr(run, "deck", None) or [])


def _remove_random_card(run, rng) -> Optional[str]:
    """随机移除牌组里一张非初始必备牌，返回被移除的名字。"""
    deck = _deck(run)
    if not deck:
        return None
    idx = rng.randrange(len(deck))
    card = deck[idx]
    uid = getattr(card, "uid", None)
    fn = getattr(run, "remove_card", None)
    if fn is not None and uid is not None:
        if fn(uid):
            return str(getattr(card, "name", "一张牌"))
        return None
    try:
        deck.pop(idx)
    except (IndexError, ValueError):  # pragma: no cover
        return None
    run.deck = deck
    return str(getattr(card, "name", "一张牌"))


def _remove_curse_or_status(run, rng) -> Optional[str]:
    deck = _deck(run)
    cands = [c for c in deck if getattr(c, "type", "") in ("curse", "status")]
    if not cands:
        return None
    card = cands[rng.randrange(len(cands))]
    uid = getattr(card, "uid", None)
    fn = getattr(run, "remove_card", None)
    if fn is not None and uid is not None and fn(uid):
        return str(getattr(card, "name", "一张牌"))
    return None


def _upgrade_random_card(run, rng) -> Optional[str]:
    deck = _deck(run)
    cands = []
    for c in deck:
        if getattr(c, "upgraded", 0):
            continue
        base = C.CARD_DB.get(getattr(c, "def_id", ""))
        if base is not None and base.upgrade:
            cands.append(c)
    if not cands:
        return None
    card = cands[rng.randrange(len(cands))]
    uid = getattr(card, "uid", None)
    fn = getattr(run, "upgrade_card", None)
    if fn is not None and uid is not None and fn(uid):
        return str(getattr(card, "name", "一张牌"))
    return None


def _random_curse(rng) -> str:
    curses = C.curse_cards()
    return curses[rng.randrange(len(curses))].id


def _random_status(rng) -> str:
    st = C.status_cards()
    return st[rng.randrange(len(st))].id


def _random_card_of_rarity(rng, rarity: str) -> str:
    pool = C.cards_by_rarity(rarity)
    pool = [c for c in pool if c.type not in ("status", "curse")] or pool
    return pool[rng.randrange(len(pool))].id


def _random_relic(rng, rarity: Optional[str] = None, owned: Optional[set] = None) -> str:
    pool = R.random_relic_pool(rng, rarity, owned or set())
    if not pool:
        pool = R.random_relic_pool(rng, None, owned or set())
    if not pool:
        return R.STARTER_RELIC
    return pool[0].id


def _random_potion(rng) -> str:
    return POTION_IDS[rng.randrange(len(POTION_IDS))]


def _rng_of(run) -> Any:
    """取 run 的 rng；缺失时退回标准库 Random（仅为健壮性）。"""
    r = getattr(run, "rng", None)
    if r is not None:
        return r
    import random as _random
    return _random.Random(0)


def _owned_relics(run) -> set:
    return set(getattr(run, "relics", None) or [])


def _pct_hp(run) -> float:
    mx = max(1, int(getattr(run, "max_hp", 1)))
    return float(getattr(run, "hp", mx)) / mx


# --------------------------------------------------------------------------
# 事件 effect 实现
# --------------------------------------------------------------------------

# ---- 通用：三选一奖励 ----

def _gain_card_choice(run, rng, rarity: str, label: str) -> str:
    cid = _random_card_of_rarity(rng, rarity)
    _add_card(run, cid)
    return "你获得了「%s」（%s）。" % (C.CARD_DB[cid].name, label)


def _lose_hp(run, n: int) -> None:
    run.hp = max(0, int(getattr(run, "hp", 0)) - int(n))


# ---- 事件 ----

def ev_wrecked_ship_loot(run) -> str:
    rng = _rng_of(run)
    rid = _random_relic(rng, None, _owned_relics(run))
    _add_relic(run, rid)
    _lose_hp(run, 8)
    return "你从烧毁的车厢里拽出「%s」，代价是 8 点生命。" % R.RELIC_DB[rid].name


def ev_wrecked_ship_leave(run) -> str:
    _add_gold(run, 30)
    return "你退开几步，只捡了些散落的军饷（+30 金币）。"


def ev_whale_fall_feast(run) -> str:
    mx = int(getattr(run, "max_hp", 70))
    run.max_hp = mx + 8
    _heal(run, 8)
    return "缴获的物资滋养了你，最大总部耐久 +8 并回复等量总部耐久。"


def ev_whale_fall_harvest(run) -> str:
    rng = _rng_of(run)
    name = _remove_random_card(run, rng)
    if name is None:
        return "你想拆下什么，但牌库里已无可弃之物。"
    return "你割舍了「%s」，让它随残骸一起留在这片焦土上。" % name


def ev_bioluminescent_pool(run) -> str:
    _heal(run, 18)
    return "燃油的暖意渗入伤口，你回复了 18 点总部耐久。"


def ev_bioluminescent_pool_drink(run) -> str:
    _add_potion(run, "potion_heal")
    _add_potion(run, "potion_energy")
    _lose_hp(run, 5)
    return "你取用两罐燃油（获得 2 瓶补给品），喉咙灼痛，失去 5 点总部耐久。"


def ev_drowned_altar_pray(run) -> str:
    _add_relic(run, R.STARTER_RELIC)
    _heal(run, 5)
    return "教堂的钟声响起，缴获罗盘的指针微微转动。"


def ev_drowned_altar_desecrate(run) -> str:
    rng = _rng_of(run)
    _add_gold(run, 90)
    curse = _random_curse(rng)
    _add_card(run, curse)
    return "你撬开圣坛取走物资（+90 金币），但「%s」缠上了你的牌库。" % C.CARD_DB[curse].name


def ev_sunken_library_study(run) -> str:
    rng = _rng_of(run)
    name = _upgrade_random_card(run, rng)
    if name is None:
        return "文件早已烧毁，你什么也没学到。"
    return "你读懂了手册，「%s」被强化了。" % name


def ev_sunken_library_take(run) -> str:
    rng = _rng_of(run)
    return _gain_card_choice(run, rng, C.RARITY_RARE, "稀有")


def ev_sonar_echo_map(run) -> str:
    rng = _rng_of(run)
    _add_gold(run, 40)
    _add_potion(run, _random_potion(rng))
    return "截获的电文指向了军需库（+40 金币，并获得 1 瓶补给品）。"


def ev_ghost_crew_bargain(run) -> str:
    rng = _rng_of(run)
    _add_gold(run, 120)
    curse = _random_curse(rng)
    _add_card(run, curse)
    return "溃兵收下了你的承诺（+120 金币），代价是「%s」。" % C.CARD_DB[curse].name


def ev_ghost_crew_refuse(run) -> str:
    _lose_hp(run, 6)
    return "你拒绝了交易，冰冷的枪口抵住你的背（失去 6 点总部耐久）。"


def ev_coral_garden_tend(run) -> str:
    _heal(run, 12)
    run.hp = min(int(getattr(run, "max_hp", 70)), int(getattr(run, "hp", 0)) + 4)
    return "阵地在你手中成形，你回复了 12 点总部耐久并额外回复 4 点。"


def ev_coral_garden_prune(run) -> str:
    rng = _rng_of(run)
    rid = _random_relic(rng, "common", _owned_relics(run))
    _add_relic(run, rid)
    return "你拆下可用的工事材料，它凝成了「%s」。" % R.RELIC_DB[rid].name


def ev_barnacle_scrape_endure(run) -> str:
    rng = _rng_of(run)
    _lose_hp(run, 7)
    rid = _random_relic(rng, None, _owned_relics(run))
    _add_relic(run, rid)
    return "你强行清理履带（失去 7 点总部耐久），从中得到「%s」。" % R.RELIC_DB[rid].name


def ev_barnacle_scrape_pay(run) -> str:
    cost = 40
    if int(getattr(run, "gold", 0)) < cost:
        return "你掏不出 %d 金币，履带依旧卡死。" % cost
    _add_gold(run, -cost)
    _heal(run, 6)
    return "你请工兵处理（-%d 金币），回复 6 点总部耐久。" % cost


def ev_abyssal_whisper_listen(run) -> str:
    rng = _rng_of(run)
    _add_card(run, "curse_of_the_deep")
    _add_relic(run, _random_relic(rng, None, _owned_relics(run)))
    return "你听完了广播，也再忘不掉它（获得一件装备与「战争之咒」）。"


def ev_abyssal_whisper_close(run) -> str:
    _heal(run, 6)
    return "你砸掉收音机，心神稍定（回复 6 点总部耐久）。"


def ev_pressure_chamber_descend(run) -> str:
    rng = _rng_of(run)
    _add_gold(run, 70)
    _add_potion(run, _random_potion(rng))
    _lose_hp(run, 10)
    return "你继续加压（+70 金币，获得 1 瓶补给品），但耳膜破裂（失去 10 点总部耐久）。"


def ev_pressure_chamber_surface(run) -> str:
    _heal(run, 9)
    return "你选择泄压，在掩体后喘匀了气（回复 9 点总部耐久）。"


def ev_bone_merchant_deal(run) -> str:
    cost = 60
    if int(getattr(run, "gold", 0)) < cost:
        return "军火商看了看你空瘪的钱袋，转身走了。"
    _add_gold(run, -cost)
    rng = _rng_of(run)
    return _gain_card_choice(run, rng, C.RARITY_UNCOMMON, "罕见") + "（-%d 金币）" % cost


def ev_bone_merchant_sell(run) -> str:
    rng = _rng_of(run)
    name = _remove_random_card(run, rng)
    if name is None:
        return "你没有什么可以卖给他。"
    _add_gold(run, 55)
    return "你卖掉了「%s」（+55 金币）。" % name


def ev_tide_pool_meditate(run) -> str:
    rng = _rng_of(run)
    name = _upgrade_random_card(run, rng)
    _heal(run, 5)
    if name is None:
        return "你在掩体里静坐，回复了 5 点总部耐久。"
    return "整备中你摸清了门道，「%s」被强化，并回复 5 点总部耐久。" % name


def ev_tide_pool_swim(run) -> str:
    rng = _rng_of(run)
    _add_potion(run, _random_potion(rng))
    _lose_hp(run, 4)
    return "你冒险检修（获得 1 瓶补给品），机油刺骨（失去 4 点总部耐久）。"


def ev_lantern_fish_lure_follow(run) -> str:
    rng = _rng_of(run)
    _add_relic(run, _random_relic(rng, None, _owned_relics(run)))
    _add_card(run, _random_status(rng))
    return "你跟着照明弹走，捡到一件装备，却揣回了一张「%s」。" % "状态牌"


def ev_lantern_fish_lure_ignore(run) -> str:
    _add_gold(run, 25)
    return "你没有跟过去，只在原地捡到些许军饷（+25 金币）。"


def ev_drowned_king_court_bow(run) -> str:
    _heal(run, 10)
    _add_gold(run, 50)
    return "你向敌军指挥官行礼，他赏赐了你（+50 金币，回复 10 点总部耐久）。"


def ev_drowned_king_court_defy(run) -> str:
    rng = _rng_of(run)
    _add_card(run, _random_card_of_rarity(rng, C.RARITY_RARE))
    _lose_hp(run, 12)
    return "你拒绝行礼，指挥所里爆发出怒吼（获得一张传奇卡牌，失去 12 点总部耐久）。"


def ev_memory_well_drink(run) -> str:
    rng = _rng_of(run)
    _remove_curse_or_status(run, rng)
    _heal(run, 8)
    return "你接受了手术，一张负面牌从记忆中淡去，并回复 8 点总部耐久。"


def ev_memory_well_refuse(run) -> str:
    rng = _rng_of(run)
    return _gain_card_choice(run, rng, C.RARITY_UNCOMMON, "罕见")


def ev_kraken_offering_feed(run) -> str:
    rng = _rng_of(run)
    name = _remove_random_card(run, rng)
    _add_relic(run, _random_relic(rng, None, _owned_relics(run)))
    if name is None:
        return "你没有可献之物，敌军装甲悻悻退去。"
    return "你交出「%s」，敌军装甲留下一件装备。" % name


def ev_kraken_offering_fight(run) -> str:
    _lose_hp(run, 15)
    _add_gold(run, 100)
    return "你与装甲缠斗（失去 15 点总部耐久），从残骸里扒出 100 金币。"


def ev_void_rift_gaze(run) -> str:
    rng = _rng_of(run)
    _add_card(run, _random_card_of_rarity(rng, C.RARITY_RARE))
    _add_card(run, "curse_of_the_deep")
    return "你进入洞穴，换来一张传奇卡牌与「战争之咒」。"


def ev_void_rift_avert(run) -> str:
    _lose_hp(run, 9)
    return "你封锁坑口，黑暗仍在你视网膜上留了一道痕（失去 9 点总部耐久）。"


def ev_final_herald_accept(run) -> str:
    mx = int(getattr(run, "max_hp", 70))
    run.max_hp = mx + 12
    _heal(run, 12)
    rng = _rng_of(run)
    _add_card(run, _random_curse(rng))
    return "代表给了你更大的编制（最大总部耐久 +12），但你的名字被记下了。"


def ev_final_herald_defy(run) -> str:
    _add_gold(run, 150)
    _lose_hp(run, 10)
    return "你撕毁文件（+150 金币），代价是 10 点总部耐久。"


def ev_sunken_forge_temper(run) -> str:
    cost = 50
    if int(getattr(run, "gold", 0)) < cost:
        return "修理厂要价 50 金币，你付不起。"
    _add_gold(run, -cost)
    rng = _rng_of(run)
    name = _upgrade_random_card(run, rng)
    if name is None:
        return "你付了钱，却没有可改装的卡（-%d 金币）。" % cost
    return "修理厂改装了「%s」（-%d 金币）。" % (name, cost)


def ev_sunken_forge_scrap(run) -> str:
    rng = _rng_of(run)
    name = _remove_random_card(run, rng)
    _add_gold(run, 45)
    if name is None:
        return "你拆了些废铁卖掉（+45 金币）。"
    return "你拆解了「%s」换钱（+45 金币）。" % name


def ev_whale_graveyard_pay_respects(run) -> str:
    rng = _rng_of(run)
    _heal(run, 14)
    return _gain_card_choice(run, rng, C.RARITY_COMMON, "普通") + "（并回复 14 点总部耐久）"


def ev_whale_graveyard_rob(run) -> str:
    rng = _rng_of(run)
    _add_gold(run, 130)
    _add_relic(run, _random_relic(rng, None, _owned_relics(run)))
    _lose_hp(run, 14)
    return "你搜刮墓穴（+130 金币与一件装备），十字架在你背后倒下（失去 14 点总部耐久）。"


def ev_star_compass_read(run) -> str:
    rng = _rng_of(run)
    _add_potion(run, _random_potion(rng))
    _add_potion(run, _random_potion(rng))
    return "密码机为你指路，你收获 2 瓶补给品。"


def ev_star_compass_sell(run) -> str:
    _add_gold(run, 110)
    return "你把密码机卖了 110 金币。"


def ev_black_tide_wade(run) -> str:
    rng = _rng_of(run)
    _add_card(run, _random_card_of_rarity(rng, C.RARITY_RARE))
    _add_potion(run, _random_potion(rng))
    _lose_hp(run, 11)
    return "你穿越毒气（获得一张传奇卡牌与 1 瓶补给品），双腿失去知觉（失去 11 点总部耐久）。"


def ev_black_tide_wait(run) -> str:
    _heal(run, 7)
    _add_gold(run, 20)
    return "你等待风向转变（+20 金币，回复 7 点总部耐久）。"


def ev_leviathan_egg_warm(run) -> str:
    _add_relic(run, R.STARTER_RELIC)
    _heal(run, 6)
    return "航弹外壳的余温让你想起家乡。"


def ev_leviathan_egg_crack(run) -> str:
    rng = _rng_of(run)
    _add_gold(run, 80)
    _add_card(run, _random_status(rng))
    return "你引爆了航弹（+80 金币），冲击波震乱了你的牌库。"


def ev_silt_oracle_ask(run) -> str:
    rng = _rng_of(run)
    name = _upgrade_random_card(run, rng)
    _add_gold(run, 30)
    if name is None:
        return "参谋含糊地说了几句（+30 金币）。"
    return "参谋点出了你的破绽，「%s」被强化（+30 金币）。" % name


def ev_silt_oracle_silence(run) -> str:
    _heal(run, 10)
    return "你保持沉默，参谋也就不再言语（回复 10 点总部耐久）。"


def ev_deep_pressure_gift(run) -> str:
    rng = _rng_of(run)
    rid = _random_relic(rng, None, _owned_relics(run))
    _add_relic(run, rid)
    return "军旗上的徽记在你手中凝成「%s」。" % R.RELIC_DB[rid].name


def ev_echo_chamber_shout(run) -> str:
    rng = _rng_of(run)
    _add_card(run, _random_card_of_rarity(rng, C.RARITY_UNCOMMON))
    _add_card(run, _random_card_of_rarity(rng, C.RARITY_UNCOMMON))
    _lose_hp(run, 6)
    return "你的命令被放大（获得 2 张精锐卡牌），耳中嗡鸣不止（失去 6 点总部耐久）。"


def ev_echo_chamber_listen(run) -> str:
    _heal(run, 8)
    return "你听自己的回声慢慢散开（回复 8 点总部耐久）。"


def ev_ghost_ship_board(run) -> str:
    rng = _rng_of(run)
    _add_potion(run, _random_potion(rng))
    _add_gold(run, 60)
    _lose_hp(run, 8)
    return "你登上装甲列车（+60 金币与 1 瓶补给品），车厢里的寒气刺入骨髓（失去 8 点总部耐久）。"


def ev_ghost_ship_sink(run) -> str:
    rng = _rng_of(run)
    name = _remove_random_card(run, rng)
    if name is None:
        return "你炸毁了列车，却发现自己什么也没失去。"
    return "你炸毁了列车，「%s」也随之化为废铁。" % name


def ev_abyss_gate_enter(run) -> str:
    rng = _rng_of(run)
    _add_relic(run, _random_relic(rng, "rare", _owned_relics(run)))
    _add_card(run, _random_curse(rng))
    return "你强攻要塞大门，取得一件传奇装备，也带回了诅咒。"


def ev_abyss_gate_seal(run) -> str:
    _heal(run, 16)
    _add_gold(run, 40)
    return "你封锁了要塞（+40 金币），胸口一松（回复 16 点总部耐久）。"


def ev_moonlit_trench_rest(run) -> str:
    _heal(run, 22)
    return "月光下的无人区安静得让人安心（回复 22 点总部耐久）。"


def ev_moonlit_trench_dig(run) -> str:
    rng = _rng_of(run)
    _add_gold(run, 95)
    _add_card(run, _random_curse(rng))
    return "你挖出埋藏的军需箱（+95 金币），箱底的诅咒爬上了你。"


def ev_lost_expedition_join(run) -> str:
    rng = _rng_of(run)
    _add_card(run, _random_card_of_rarity(rng, C.RARITY_COMMON))
    _heal(run, 6)
    return "你收编了他们，分到一张卡牌，也分到一点暖意。"


def ev_lost_expedition_leave(run) -> str:
    _add_gold(run, 35)
    return "你独自前进，只带走他们给的一点军饷（+35 金币）。"


# --------------------------------------------------------------------------
# 事件表（>= 22）
# --------------------------------------------------------------------------

EVENT_LIST: List[EventDef] = [

    # ---------------- act 1 ----------------
    EventDef("wrecked_ship", "被击毁的补给车队", 1,
             "一支被击毁的补给车队横在路边，卡车残骸还在冒烟。车厢门虚掩，里面有东西在反光。",
             (
                 EventChoice("撬开车厢", "获得一件随机装备，失去 8 点总部耐久", ev_wrecked_ship_loot),
                 EventChoice("只捡散落物资", "获得 30 金币", ev_wrecked_ship_leave),
             ), art="event_wrecked_ship"),

    EventDef("whale_fall", "缴获的敌军物资", 1,
             "一整车敌军物资刚刚被放弃，罐头、弹药、燃油散落一地——也散落着陷阱。",
             (
                 EventChoice("就地补给", "最大总部耐久 +8 并回复 8 点", ev_whale_fall_feast),
                 EventChoice("拆取可用零件", "随机移除牌库中一张卡", ev_whale_fall_harvest),
             ), art="event_whale_fall"),

    EventDef("bioluminescent_pool", "燃烧的油槽", 1,
             "一个被击穿的油槽仍在燃烧，火光里似乎有能用上的东西在滚动。",
             (
                 EventChoice("靠近油槽", "回复 18 点总部耐久", ev_bioluminescent_pool),
                 EventChoice("取用燃油", "获得 2 瓶补给品，失去 5 点总部耐久", ev_bioluminescent_pool_drink),
             ), art="event_bioluminescent_pool"),

    EventDef("drowned_altar", "废弃的野战教堂", 1,
             "一座被炮火削去尖顶的教堂，圣坛上刻着部队的徽记，石缝间还有东西在闪。",
             (
                 EventChoice("就地祈祷", "获得缴获的军用罗盘并回复 5 点总部耐久", ev_drowned_altar_pray),
                 EventChoice("撬开圣坛", "获得 90 金币，牌库加入一张诅咒", ev_drowned_altar_desecrate),
             ), art="event_drowned_altar"),

    EventDef("sunken_library", "缴获的参谋部文件", 1,
             "一只烧了一半的文件箱，里面塞满了敌军的作战手册与地图。",
             (
                 EventChoice("研读手册", "随机升级牌库中的一张卡", ev_sunken_library_study),
                 EventChoice("取走核心文件", "获得一张传奇卡牌", ev_sunken_library_take),
             ), art="event_sunken_library"),

    EventDef("sonar_echo", "无线电截获", 1,
             "情报班截获了一段加密电文，解出来的坐标指向一处从未被标注的军需库。",
             (
                 EventChoice("循坐标搜索", "获得 40 金币与 1 瓶补给品", ev_sonar_echo_map),
             ), art="event_sonar_echo"),

    EventDef("ghost_crew", "迷路的溃兵", 1,
             "一群蓬头垢面的溃兵围着你，领头的手里举着一袋金币，另一只手摊开等你。",
             (
                 EventChoice("收编他们", "获得 120 金币，牌库加入一张诅咒", ev_ghost_crew_bargain),
                 EventChoice("让他们自去", "失去 6 点总部耐久", ev_ghost_crew_refuse),
             ), art="event_ghost_crew"),

    EventDef("coral_garden", "被放弃的阵地", 1,
             "一处修筑精良却空无一人的阵地，沙袋、铁丝网、掩体一应俱全。",
             (
                 EventChoice("加固阵地", "回复 12 点总部耐久", ev_coral_garden_tend),
                 EventChoice("拆走工事材料", "获得一件随机常规装备", ev_coral_garden_prune),
             ), art="event_coral_garden"),

    EventDef("barnacle_scrape", "清理履带", 1,
             "泥泞和铁丝网已经缠满你的履带，再不处理就要卡死传动。",
             (
                 EventChoice("强行清理", "失去 7 点总部耐久，获得一件随机装备", ev_barnacle_scrape_endure),
                 EventChoice("调工兵处理", "花费 40 金币，回复 6 点总部耐久", ev_barnacle_scrape_pay,
                            requires=lambda run: int(getattr(run, "gold", 0)) >= 40),
             ), art="event_barnacle_scrape"),

    # ---------------- act 2 ----------------
    EventDef("abyssal_whisper", "敌军的劝降广播", 2,
             "无线电突然变得极静，然后有人用你的母语念出你的名字。",
             (
                 EventChoice("继续监听", "获得一件装备与「战争之咒」", ev_abyssal_whisper_listen),
                 EventChoice("关闭无线电", "回复 6 点总部耐久", ev_abyssal_whisper_close),
             ), art="event_abyssal_whisper"),

    EventDef("pressure_chamber", "加压的油罐车", 2,
             "一辆仍在运转的加压油罐车，压力表上的指针指着一个不该存在的刻度。",
             (
                 EventChoice("继续加压", "获得 70 金币与 1 瓶补给品，失去 10 点总部耐久",
                             ev_pressure_chamber_descend),
                 EventChoice("立即泄压", "回复 9 点总部耐久", ev_pressure_chamber_surface),
             ), art="event_pressure_chamber"),

    EventDef("bone_merchant", "黑市军火商", 2,
             "一个穿着三件套的军火商坐在弹药箱上，指节敲着算盘，没有军衔却什么都有。",
             (
                 EventChoice("买一张卡", "花费 60 金币获得一张精锐卡牌", ev_bone_merchant_deal,
                            requires=lambda run: int(getattr(run, "gold", 0)) >= 60),
                 EventChoice("卖一张卡", "随机移除一张卡，获得 55 金币", ev_bone_merchant_sell),
             ), art="event_bone_merchant"),

    EventDef("tide_pool", "战地工事整备", 2,
             "炮火间歇，你有时间喘口气，也有时间检查装备。",
             (
                 EventChoice("就地整备", "随机升级一张卡并回复 5 点总部耐久", ev_tide_pool_meditate),
                 EventChoice("冒险检修", "获得 1 瓶补给品，失去 4 点总部耐久", ev_tide_pool_swim),
             ), art="event_tide_pool"),

    EventDef("lantern_fish_lure", "可疑的照明弹", 2,
             "黑暗里一串照明弹缓缓移动，光后面是很久没动过的巨大轮廓。",
             (
                 EventChoice("跟上去", "获得一件装备与一张状态牌", ev_lantern_fish_lure_follow),
                 EventChoice("无视它", "获得 25 金币", ev_lantern_fish_lure_ignore),
             ), art="event_lantern_fish_lure"),

    EventDef("drowned_king_court", "沦陷区指挥部", 2,
             "一张铺满地图的长桌后端坐着敌军指挥官，两侧站着数百名低头不语的参谋。",
             (
                 EventChoice("行礼", "获得 50 金币并回复 10 点总部耐久", ev_drowned_king_court_bow),
                 EventChoice("拒绝行礼", "获得一张传奇卡牌，失去 12 点总部耐久", ev_drowned_king_court_defy),
             ), art="event_drowned_king_court"),

    EventDef("memory_well", "战地医院的选择", 2,
             "军医摊开手：药品只够处理一样东西——伤，或者记忆。",
             (
                 EventChoice("处理记忆", "移除一张诅咒/状态牌并回复 8 点总部耐久", ev_memory_well_drink),
                 EventChoice("保留记忆", "获得一张精锐卡牌", ev_memory_well_refuse),
             ), art="event_memory_well"),

    EventDef("kraken_offering", "敌军的勒索", 2,
             "敌军装甲从四面围拢，但没有立刻开火——他们在等一件东西。",
             (
                 EventChoice("交出一张卡", "随机移除一张卡，获得一件装备", ev_kraken_offering_feed),
                 EventChoice("开火还击", "失去 15 点总部耐久，获得 100 金币", ev_kraken_offering_fight),
             ), art="event_kraken_offering"),

    EventDef("sunken_forge", "野战修理厂", 2,
             "一座还在作业的野战修理厂，车床和焊枪都还能用。",
             (
                 EventChoice("请求改装", "花费 50 金币随机升级一张卡", ev_sunken_forge_temper,
                            requires=lambda run: int(getattr(run, "gold", 0)) >= 50),
                 EventChoice("拆解废铁", "随机移除一张卡，获得 45 金币", ev_sunken_forge_scrap),
             ), art="event_sunken_forge"),

    # ---------------- act 3 ----------------
    EventDef("void_rift", "弹坑里的洞穴", 3,
             "一发重炮在阵地上炸出深坑，坑底露出一个不该存在的入口。",
             (
                 EventChoice("进入洞穴", "获得一张传奇卡牌与「战争之咒」", ev_void_rift_gaze),
                 EventChoice("封锁坑口", "失去 9 点总部耐久", ev_void_rift_avert),
             ), art="event_void_rift"),

    EventDef("final_herald", "停战谈判代表", 3,
             "一个披着大衣的代表站在路中央，手里握着一份尚未签字的文件。",
             (
                 EventChoice("接受条件", "最大总部耐久 +12 并回复 12 点，牌库加入诅咒",
                             ev_final_herald_accept),
                 EventChoice("撕毁文件", "获得 150 金币，失去 10 点总部耐久",
                             ev_final_herald_defy),
             ), art="event_final_herald"),

    EventDef("whale_graveyard", "阵亡者公墓", 3,
             "数以千计的白色十字架整齐排列，每一个下面都躺着一个人。",
             (
                 EventChoice("敬礼致哀", "获得一张常规卡牌并回复 14 点总部耐久",
                             ev_whale_graveyard_pay_respects),
                 EventChoice("搜刮墓穴", "获得 130 金币与一件装备，失去 14 点总部耐久",
                             ev_whale_graveyard_rob),
             ), art="event_whale_graveyard"),

    EventDef("star_compass_event", "缴获的密码机", 3,
             "一台缴获的密码机仍在运转，它的输出不指向任何已知坐标，而指向你尚未走过的一步。",
             (
                 EventChoice("按密码机行动", "获得 2 瓶补给品", ev_star_compass_read),
                 EventChoice("拆解变卖", "获得 110 金币", ev_star_compass_sell),
             ), art="event_star_compass"),

    EventDef("black_tide_event", "毒气地带", 3,
             "一股黄绿色的浓雾横在前路，雾里漂着不属于这个世界的东西。",
             (
                 EventChoice("穿越毒气", "获得一张传奇卡牌与 1 瓶补给品，失去 11 点总部耐久",
                             ev_black_tide_wade),
                 EventChoice("等待风向转变", "获得 20 金币并回复 7 点总部耐久", ev_black_tide_wait),
             ), art="event_black_tide"),

    EventDef("leviathan_egg", "未引爆的重型航弹", 3,
             "一枚半人高的重型航弹卡在废墟里，外壳温热，里面有心跳般的滴答声。",
             (
                 EventChoice("尝试拆弹", "获得缴获的军用罗盘并回复 6 点总部耐久", ev_leviathan_egg_warm),
                 EventChoice("引爆它", "获得 80 金币，牌库加入一张状态牌", ev_leviathan_egg_crack),
             ), art="event_leviathan_egg"),

    EventDef("silt_oracle", "被俘的敌军参谋", 3,
             "一个被俘的敌军参谋抬起头，嘴一张一合，说出的是你的作战计划。",
             (
                 EventChoice("审问", "随机升级一张卡并获得 30 金币", ev_silt_oracle_ask),
                 EventChoice("保持沉默", "回复 10 点总部耐久", ev_silt_oracle_silence),
             ), art="event_silt_oracle"),

    EventDef("deep_pressure_gift", "缴获的敌军军旗", 3,
             "你从废墟里扯下一面军旗，旗帜下的东西正在成形。",
             (
                 EventChoice("收下军旗", "获得一件随机装备", ev_deep_pressure_gift),
             ), art="event_deep_pressure_gift"),

    EventDef("echo_chamber_event", "地下掩体", 3,
             "一个钢筋混凝土的球形掩体，任何声音都会被放大成震耳欲聋的轰鸣。",
             (
                 EventChoice("大声下令", "获得 2 张精锐卡牌，失去 6 点总部耐久", ev_echo_chamber_shout),
                 EventChoice("安静倾听", "回复 8 点总部耐久", ev_echo_chamber_listen),
             ), art="event_echo_chamber"),

    EventDef("ghost_ship_event", "无人驾驶的装甲列车", 3,
             "一列装甲列车静静停在轨道上，炮塔完好，炉膛还是温的。",
             (
                 EventChoice("登车检查", "获得 60 金币与 1 瓶补给品，失去 8 点总部耐久", ev_ghost_ship_board),
                 EventChoice("炸毁列车", "随机移除一张卡", ev_ghost_ship_sink),
             ), art="event_ghost_ship"),

    EventDef("abyss_gate_event", "敌军要塞大门", 3,
             "两扇钢制大门半开着，门后传来引擎声，也传来锁链拖地的声音。",
             (
                 EventChoice("强攻大门", "获得一件传奇装备，牌库加入一张诅咒",
                             ev_abyss_gate_enter),
                 EventChoice("封锁要塞", "获得 40 金币并回复 16 点总部耐久", ev_abyss_gate_seal),
             ), art="event_abyss_gate"),

    EventDef("moonlit_trench", "月光下的无人区", 3,
             "月光穿透硝烟，把整片无人区照得如同白昼。",
             (
                 EventChoice("就地休整", "回复 22 点总部耐久", ev_moonlit_trench_rest),
                 EventChoice("挖掘阵地", "获得 95 金币，牌库加入一张诅咒", ev_moonlit_trench_dig),
             ), art="event_moonlit_trench"),

    EventDef("lost_expedition", "失联的友军残部", 3,
             "一支失联多日的友军残部还活着，正围着火堆分享仅剩的补给。",
             (
                 EventChoice("收编他们", "获得一张常规卡牌并回复 6 点总部耐久", ev_lost_expedition_join),
                 EventChoice("独自前进", "获得 35 金币", ev_lost_expedition_leave),
             ), art="event_lost_expedition"),
]


EVENT_DB: Dict[str, EventDef] = {e.id: e for e in EVENT_LIST}


# --------------------------------------------------------------------------
# 事件抽取
# --------------------------------------------------------------------------

def random_event(rng, act: int, seen: set) -> EventDef:
    """按 act 随机抽一个未见过的事件；全见过时退回该 act 的任意事件。

    保证**永不返回 None**（run.py 依赖此点）。
    """
    seen = set(seen or ())
    pool = [e for e in EVENT_LIST if e.act == act and e.id not in seen]
    if not pool:
        pool = [e for e in EVENT_LIST if e.id not in seen]
    if not pool:
        pool = [e for e in EVENT_LIST if e.act == act] or list(EVENT_LIST)
    return pool[rng.randrange(len(pool))]


def events_by_act(act: int) -> List[EventDef]:
    return [e for e in EVENT_LIST if e.act == act]


def get_event(event_id: str) -> Optional[EventDef]:
    return EVENT_DB.get(event_id)


# --------------------------------------------------------------------------
# 商店
# --------------------------------------------------------------------------

def _asc_price_mult(ascension: int) -> float:
    """飞升越高物价越贵：每 5 档 +10%。"""
    a = max(0, int(ascension))
    return 1.0 + 0.10 * (a // 5)


def card_price(rarity: str, ascension: int = 0) -> int:
    base = SHOP_CARD_PRICE.get(rarity, SHOP_CARD_PRICE["common"])
    return int(round(base * _asc_price_mult(ascension)))


def relic_price(rarity: str, ascension: int = 0) -> int:
    base = SHOP_RELIC_PRICE.get(rarity, SHOP_RELIC_PRICE["common"])
    return int(round(base * _asc_price_mult(ascension)))


def potion_price(ascension: int = 0) -> int:
    return int(round(SHOP_POTION_PRICE * _asc_price_mult(ascension)))


def remove_price(act: int = 1, ascension: int = 0, removes_done: int = 0) -> int:
    """删卡价格：基础 75，每次删卡 +25，act 与飞升各加成。"""
    base = SHOP_REMOVE_PRICE_BASE + 25 * max(0, int(removes_done))
    base += 25 * max(0, int(act) - 1)
    return int(round(base * _asc_price_mult(ascension)))


def build_shop_inventory(rng, act: int, ascension: int = 0) -> dict:
    """生成一次商店库存。

    返回 {"cards":[...], "relics":[...], "potions":[...], "remove_price":int,
          "card_prices":{id:price}, "relic_prices":{id:price}, "potion_price":int}
    cards 为 CardDef，relics 为 RelicDef，potions 为药水 id 字符串。
    """
    act = int(act or 1)
    asc = int(ascension or 0)

    # 卡牌：4 张（高飞升时更容易出高稀有度）
    cards = []
    used = set()
    for i in range(4):
        roll = rng.random()
        if roll < 0.62:
            rar = C.RARITY_COMMON
        elif roll < 0.90:
            rar = C.RARITY_UNCOMMON
        else:
            rar = C.RARITY_RARE
        pool = [c for c in C.playable_cards() if c.rarity == rar and c.id not in used]
        if not pool:
            pool = [c for c in C.playable_cards() if c.id not in used]
        if not pool:
            break
        pick = pool[rng.randrange(len(pool))]
        used.add(pick.id)
        cards.append(pick)

    # 遗物：2~3 件
    relics = []
    pool = R.random_relic_pool(rng, None, set())
    n_relic = 2 + (1 if (asc >= 10 or rng.random() < 0.35) else 0)
    for r in pool[:n_relic]:
        relics.append(r)

    # 药水：3 瓶
    potions = []
    for _ in range(3):
        potions.append(_random_potion(rng))

    return {
        "cards": cards,
        "relics": relics,
        "potions": potions,
        "remove_price": remove_price(act, asc, 0),
        "card_prices": {c.id: card_price(c.rarity, asc) for c in cards},
        "relic_prices": {r.id: relic_price(r.rarity, asc) for r in relics},
        "potion_price": potion_price(asc),
    }


# --------------------------------------------------------------------------
# 宝箱
# --------------------------------------------------------------------------

def roll_treasure(rng, act: int) -> dict:
    """掷一次宝箱。

    tier ∈ TREASURE_TIERS；返回 {"tier","gold","relic_id","potion_id","curse_id","text"}。
    未使用的字段为 None。
    """
    act = int(act or 1)
    roll = rng.random()
    # act 越深，好货越多，诅咒遗物也越多
    if roll < 0.34 - 0.05 * (act - 1):
        tier = "gold"
    elif roll < 0.74:
        tier = "relic"
    elif roll < 0.90:
        tier = "potion"
    else:
        tier = "curse_relic"

    out = {"tier": tier, "gold": 0, "relic_id": None,
           "potion_id": None, "curse_id": None, "text": ""}

    if tier == "gold":
        out["gold"] = int(rng.randrange(60, 100) + 35 * (act - 1))
        out["text"] = "宝箱里滚出 %d 枚金币。" % out["gold"]
    elif tier == "relic":
        rid = _random_relic(rng, None, set())
        out["relic_id"] = rid
        out["text"] = "宝箱里躺着一件遗物：「%s」。" % R.RELIC_DB[rid].name
    elif tier == "potion":
        pid = _random_potion(rng)
        out["potion_id"] = pid
        out["gold"] = int(rng.randrange(20, 45))
        out["text"] = "宝箱里是一瓶「%s」，箱底还有 %d 枚金币。" % (
            POTION_DB[pid]["name"], out["gold"])
    else:  # curse_relic
        rid = _random_relic(rng, None, set())
        cid = _random_curse(rng)
        out["relic_id"] = rid
        out["curse_id"] = cid
        out["text"] = "宝箱里有「%s」，但拿起来时「%s」也跟上了你。" % (
            R.RELIC_DB[rid].name, C.CARD_DB[cid].name)

    return out


def apply_treasure(run, treasure: dict) -> str:
    """把 roll_treasure 的结果应用到 run（供 run.py 可选调用）。"""
    if not treasure:
        return ""
    gold = int(treasure.get("gold") or 0)
    if gold:
        _add_gold(run, gold)
    rid = treasure.get("relic_id")
    if rid:
        _add_relic(run, rid)
    pid = treasure.get("potion_id")
    if pid:
        _add_potion(run, pid)
    cid = treasure.get("curse_id")
    if cid:
        _add_card(run, cid)
    return str(treasure.get("text") or "你打开了宝箱。")


__all__ = [
    "EventChoice", "EventDef", "EVENT_DB", "EVENT_LIST",
    "random_event", "events_by_act", "get_event",
    "SHOP_CARD_PRICE", "SHOP_RELIC_PRICE", "SHOP_POTION_PRICE", "SHOP_REMOVE_PRICE_BASE",
    "TREASURE_TIERS", "POTION_DB", "POTION_IDS",
    "build_shop_inventory", "roll_treasure", "apply_treasure",
    "card_price", "relic_price", "potion_price", "remove_price",
]
