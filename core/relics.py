# -*- coding: utf-8 -*-
"""钢铁战线 Steel Frontline —— 遗物数据库。

严格遵循 ARCHITECTURE.md 第 4 节：

* ``RelicDef`` 字段名与契约完全一致（id / name / rarity / text / trigger / counter）。
* 全部 ``TRIGGER_*`` 钩子均有遗物覆盖，引擎按 ``trigger`` 字符串分发即可。
* 遗物只声明数据，不含运行时状态；计数由 ``engine`` 在 ``RunState.relic_counters``
  或 ``Combatant`` 上维护（``counter`` 为显示用的初始值，-1 表示不显示）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

# --------------------------------------------------------------------------
# 稀有度
# --------------------------------------------------------------------------

RARITY_STARTER = "starter"
RARITY_COMMON = "common"
RARITY_UNCOMMON = "uncommon"
RARITY_RARE = "rare"
RARITY_BOSS = "boss"
RARITY_SHOP = "shop"

# --------------------------------------------------------------------------
# 触发钩子（与 ARCHITECTURE.md 第 4 节逐字一致）
# --------------------------------------------------------------------------

TRIGGER_BATTLE_START = "battle_start"
TRIGGER_TURN_START = "turn_start"
TRIGGER_TURN_END = "turn_end"
TRIGGER_ON_ATTACK = "on_attack"              # 攻击牌造成伤害后
TRIGGER_ON_DAMAGE_TAKEN = "on_damage_taken"
TRIGGER_ON_CARD_PLAYED = "on_card_played"
TRIGGER_ON_KILL = "on_kill"
TRIGGER_ON_REST = "on_rest"
TRIGGER_PASSIVE = "passive"                  # 持续生效，engine 主动查询
TRIGGER_ON_PICKUP = "on_pickup"              # 拾取瞬间
TRIGGER_ON_SHOP = "on_shop"

TRIGGERS = (
    TRIGGER_BATTLE_START, TRIGGER_TURN_START, TRIGGER_TURN_END,
    TRIGGER_ON_ATTACK, TRIGGER_ON_DAMAGE_TAKEN, TRIGGER_ON_CARD_PLAYED,
    TRIGGER_ON_KILL, TRIGGER_ON_REST, TRIGGER_PASSIVE,
    TRIGGER_ON_PICKUP, TRIGGER_ON_SHOP,
)


@dataclass(frozen=True)
class RelicDef:
    id: str
    name: str
    rarity: str            # "starter"|"common"|"uncommon"|"rare"|"boss"|"shop"
    text: str
    trigger: str           # 见下
    counter: int = -1      # -1 表示不计数显示


# --------------------------------------------------------------------------
# 遗物表
# --------------------------------------------------------------------------

RELIC_LIST: List[RelicDef] = [

    # ---------------- starter (1) ----------------
    RelicDef("broken_compass", "缴获的军用罗盘", RARITY_STARTER,
             "战斗开始时，获得 1 点火力。",
             TRIGGER_BATTLE_START, counter=-1),

    # ---------------- battle_start (5) ----------------
    RelicDef("whale_tooth", "狗牌护符", RARITY_COMMON,
             "战斗开始时，获得 6 点掩体。",
             TRIGGER_BATTLE_START),
    RelicDef("anchor_chain", "断裂的履带板", RARITY_COMMON,
             "战斗开始时，获得 2 层铁丝网。",
             TRIGGER_BATTLE_START),
    RelicDef("brine_vial", "凝固汽油瓶", RARITY_UNCOMMON,
             "战斗开始时，对所有敌人施加 2 层燃烧。",
             TRIGGER_BATTLE_START),
    RelicDef("sonar_buoy", "前沿观察哨", RARITY_UNCOMMON,
             "战斗开始时，抽 2 张卡。",
             TRIGGER_BATTLE_START),
    RelicDef("leviathan_scale", "虎式装甲板", RARITY_BOSS,
             "战斗开始时，获得 2 点火力与 2 点机动。",
             TRIGGER_BATTLE_START),

    # ---------------- turn_start (5) ----------------
    RelicDef("tide_clock", "军用计时器", RARITY_COMMON,
             "每 3 个回合开始时，获得 1 点补给。",
             TRIGGER_TURN_START, counter=0),
    RelicDef("coral_ring", "工兵铲", RARITY_COMMON,
             "每回合开始时，获得 3 点掩体。",
             TRIGGER_TURN_START),
    RelicDef("abyss_lantern", "战地探照灯", RARITY_UNCOMMON,
             "每回合开始时，抽 1 张卡。",
             TRIGGER_TURN_START),
    RelicDef("tideglass", "缴获的沙盘钟", RARITY_RARE,
             "每回合开始时，获得 1 点补给，但抽卡数 -1。",
             TRIGGER_TURN_START),
    RelicDef("ritual_mask", "集团军肩章", RARITY_BOSS,
             "每回合开始时，获得 1 层增援（每回合叠加火力）。",
             TRIGGER_TURN_START),

    # ---------------- turn_end (5) ----------------
    RelicDef("shell_amulet", "钢盔护符", RARITY_COMMON,
             "回合结束时，若本回合未受到伤害，获得 4 点掩体。",
             TRIGGER_TURN_END),
    RelicDef("barnacle_charm", "弹药携行具", RARITY_COMMON,
             "回合结束时，若手牌为空，抽 1 张卡。",
             TRIGGER_TURN_END),
    RelicDef("ice_core", "白磷弹核心", RARITY_UNCOMMON,
             "回合结束时，对所有敌人造成 3 点伤害。",
             TRIGGER_TURN_END),
    RelicDef("deep_altar", "战地祭坛", RARITY_UNCOMMON,
             "回合结束时，若本回合未打出攻击牌，回复 3 点总部耐久。",
             TRIGGER_TURN_END),
    RelicDef("whale_fall_bell", "焦土警钟", RARITY_RARE,
             "回合结束时，按本回合已打出卡数每 3 张造成 2 点全体伤害。",
             TRIGGER_TURN_END, counter=0),

    # ---------------- on_attack (5) ----------------
    RelicDef("harpoon_head", "穿甲弹头", RARITY_COMMON,
             "每回合首次攻击牌额外造成 3 点伤害。",
             TRIGGER_ON_ATTACK, counter=0),
    RelicDef("venom_gland", "燃烧弹引信", RARITY_COMMON,
             "攻击牌命中后，施加 1 层燃烧。",
             TRIGGER_ON_ATTACK),
    RelicDef("barbed_hook", "破甲弹芯", RARITY_UNCOMMON,
             "攻击牌命中后，施加 1 层破甲。",
             TRIGGER_ON_ATTACK),
    RelicDef("pressure_gauge", "膛压计", RARITY_UNCOMMON,
             "每打出第 3 张攻击牌时，抽 1 张卡。",
             TRIGGER_ON_ATTACK, counter=0),
    RelicDef("leviathan_jaw", "重型炮闩", RARITY_RARE,
             "攻击牌造成伤害后，若目标耐久低于 25%，伤害 +5。",
             TRIGGER_ON_ATTACK),

    # ---------------- on_damage_taken (4) ----------------
    RelicDef("thorn_mail", "反应装甲", RARITY_COMMON,
             "受到伤害时，对攻击者造成 3 点伤害。",
             TRIGGER_ON_DAMAGE_TAKEN),
    RelicDef("brine_blood", "老兵的血", RARITY_COMMON,
             "受到伤害时，获得 1 点火力（每回合最多 1 次）。",
             TRIGGER_ON_DAMAGE_TAKEN, counter=0),
    RelicDef("regenerative_gel", "战地医疗包", RARITY_UNCOMMON,
             "受到伤害时，获得 2 层战地医疗。",
             TRIGGER_ON_DAMAGE_TAKEN),
    RelicDef("abyss_pact", "血战军令", RARITY_RARE,
             "受到伤害时，对所有敌人造成等量伤害的一半（向下取整）。",
             TRIGGER_ON_DAMAGE_TAKEN),

    # ---------------- on_card_played (5) ----------------
    RelicDef("tide_bracelet", "参谋腕表", RARITY_COMMON,
             "每打出 4 张卡，获得 1 点补给。",
             TRIGGER_ON_CARD_PLAYED, counter=0),
    RelicDef("ink_sac", "战术地图筒", RARITY_COMMON,
             "打出战术牌后，获得 2 点掩体。",
             TRIGGER_ON_CARD_PLAYED),
    RelicDef("driftwood_idol", "铁十字勋章", RARITY_UNCOMMON,
             "每打出 3 张攻击牌，获得 1 点火力。",
             TRIGGER_ON_CARD_PLAYED, counter=0),
    RelicDef("echo_conch", "野战电话", RARITY_UNCOMMON,
             "每回合首次打出指令牌时，抽 2 张卡。",
             TRIGGER_ON_CARD_PLAYED, counter=0),
    RelicDef("chain_rosary", "弹链挂饰", RARITY_RARE,
             "每打出一张卡，本回合下一张攻击牌 +1 伤害（可叠加至 +8）。",
             TRIGGER_ON_CARD_PLAYED),

    # ---------------- on_kill (4) ----------------
    RelicDef("feeding_fang", "战功勋章", RARITY_COMMON,
             "击杀敌人时，回复 3 点总部耐久。",
             TRIGGER_ON_KILL),
    RelicDef("golden_scale", "缴获的军饷", RARITY_COMMON,
             "击杀敌人时，获得 12 金币。",
             TRIGGER_ON_KILL),
    RelicDef("soul_lure", "敌军军旗", RARITY_UNCOMMON,
             "击杀敌人时，获得 1 点火力。",
             TRIGGER_ON_KILL),
    RelicDef("reaper_pearl", "铁十字骑士章", RARITY_RARE,
             "击杀敌人时，获得 1 点补给并抽 1 张卡。",
             TRIGGER_ON_KILL),

    # ---------------- on_rest (4) ----------------
    RelicDef("driftwood_bed", "行军床", RARITY_COMMON,
             "休整时，额外回复 6 点总部耐久。",
             TRIGGER_ON_REST),
    RelicDef("dream_coral", "参谋部地图", RARITY_UNCOMMON,
             "休整时，可以额外升级一张卡。",
             TRIGGER_ON_REST),
    RelicDef("tide_prayer_beads", "后勤优先令", RARITY_UNCOMMON,
             "休整时，获得 1 点最大补给（本局永久）。",
             TRIGGER_ON_REST),
    RelicDef("whale_lullaby", "战地家书", RARITY_RARE,
             "休整时，移除牌库中一张诅咒或状态牌。",
             TRIGGER_ON_REST),

    # ---------------- passive (6) ----------------
    RelicDef("current_gauntlet", "射手手套", RARITY_COMMON,
             "攻击牌造成的伤害 +1。",
             TRIGGER_PASSIVE),
    RelicDef("iron_lung", "铁肺呼吸器", RARITY_COMMON,
             "最大总部耐久 +10。",
             TRIGGER_PASSIVE),
    RelicDef("poison_sac", "凝固汽油囊", RARITY_UNCOMMON,
             "敌人身上的燃烧每回合额外 -1 时多造成一次伤害。",
             TRIGGER_PASSIVE),
    RelicDef("artifact_prism", "干扰弹发射器", RARITY_RARE,
             "战斗开始时获得 1 层干扰弹（持续生效，见 battle_start 亦可）。",
             TRIGGER_PASSIVE),
    RelicDef("heavy_anchor", "重型装甲裙板", RARITY_SHOP,
             "你的掩体不会被「穿甲」类效果清空。",
             TRIGGER_PASSIVE),
    RelicDef("whale_eye", "炮兵观测镜", RARITY_SHOP,
             "战斗开始时查看敌人意图（信息类，永久生效）。",
             TRIGGER_PASSIVE),

    # ---------------- on_pickup (4) ----------------
    RelicDef("dried_kelp", "压缩干粮", RARITY_COMMON,
             "拾取时，回复 8 点总部耐久。",
             TRIGGER_ON_PICKUP),
    RelicDef("map_scroll", "战区地图", RARITY_COMMON,
             "拾取时，获得 25 金币。",
             TRIGGER_ON_PICKUP),
    RelicDef("inkstone", "工兵工具箱", RARITY_UNCOMMON,
             "拾取时，随机升级牌库中的一张卡。",
             TRIGGER_ON_PICKUP),
    RelicDef("deep_idol", "元帅权杖", RARITY_RARE,
             "拾取时，获得一张传奇卡牌。",
             TRIGGER_ON_PICKUP),

    # ---------------- on_shop (4) ----------------
    RelicDef("coupon_shell", "军用配给券", RARITY_COMMON,
             "补给站中所有商品价格 -20%。",
             TRIGGER_ON_SHOP),
    RelicDef("merchant_seal", "后勤部印章", RARITY_UNCOMMON,
             "进入补给站时，获得 1 次免费删卡。",
             TRIGGER_ON_SHOP),
    RelicDef("smugglers_hold", "走私车厢", RARITY_UNCOMMON,
             "补给站额外多上架 1 张卡牌与 1 件装备。",
             TRIGGER_ON_SHOP),
    RelicDef("black_market_tide", "黑市渠道", RARITY_SHOP,
             "补给站中必定出现一件传奇装备。",
             TRIGGER_ON_SHOP),
]


RELIC_DB: Dict[str, RelicDef] = {r.id: r for r in RELIC_LIST}

STARTER_RELIC = "broken_compass"


# --------------------------------------------------------------------------
# 查询接口
# --------------------------------------------------------------------------

def all_relics() -> List[RelicDef]:
    return list(RELIC_LIST)


def get_relic(relic_id: str) -> RelicDef:
    return RELIC_DB[relic_id]


def relics_by_trigger(trigger: str) -> List[RelicDef]:
    return [r for r in RELIC_LIST if r.trigger == trigger]


def relics_by_rarity(rarity: str) -> List[RelicDef]:
    return [r for r in RELIC_LIST if r.rarity == rarity]


def random_relic_pool(rng, rarity: str | None = None,
                      exclude: set | None = None) -> List[RelicDef]:
    """返回打乱后的遗物候选池。exclude 为已持有的遗物 id 集合。"""
    ex = exclude or set()
    pool = [r for r in RELIC_LIST if r.id not in ex and r.rarity != RARITY_STARTER]
    if rarity is not None:
        pool = [r for r in pool if r.rarity == rarity]
    out = list(pool)
    rng.shuffle(out)
    return out


def relic_name(relic_id: str) -> str:
    r = RELIC_DB.get(relic_id)
    return r.name if r else relic_id


__all__ = [
    "RARITY_STARTER", "RARITY_COMMON", "RARITY_UNCOMMON", "RARITY_RARE",
    "RARITY_BOSS", "RARITY_SHOP",
    "TRIGGER_BATTLE_START", "TRIGGER_TURN_START", "TRIGGER_TURN_END",
    "TRIGGER_ON_ATTACK", "TRIGGER_ON_DAMAGE_TAKEN", "TRIGGER_ON_CARD_PLAYED",
    "TRIGGER_ON_KILL", "TRIGGER_ON_REST", "TRIGGER_PASSIVE",
    "TRIGGER_ON_PICKUP", "TRIGGER_ON_SHOP", "TRIGGERS",
    "RelicDef", "RELIC_DB", "RELIC_LIST", "STARTER_RELIC",
    "all_relics", "get_relic", "relics_by_trigger", "relics_by_rarity",
    "random_relic_pool", "relic_name",
]
