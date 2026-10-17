#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""辅助角色（指挥官）：每局开战前选一位，提供一层全局被动。

设计
----
* **纯数据 + 纯函数**：本模块不依赖 Qt，也不改引擎内部状态。
* 加成都通过 ``Modifiers`` 表达，引擎在结算时查询，方便测试与存档。
* 角色用的是**真实历史人物的名字**（姓名本身不构成著作权）；
  描述为游戏化改编，不代表对历史人物的评价。

加成维度（Modifiers）
---------------------
``supply``      每回合额外指挥点
``hp``          总部耐久上限
``damage``      伤害倍率（1.15 = +15%）
``block``       掩体倍率
``draw``        每回合额外抽牌
``hand``        开局手牌数
``burn``        燃烧/毒伤倍率
``nuke``        核弹额外增伤（固定值，只在核弹卡上生效）
``gold``        开局金币
``price``       商店价格倍率（0.85 = 便宜 15%）
``heal``        战后回复加成（固定值）
``energy_cap``  指挥点上限
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional


# --------------------------------------------------------------------------
# 加成
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Modifiers:
    """一位指挥官提供的全部加成。默认全是"不变"。"""

    supply: int = 0
    hp: int = 0
    damage: float = 1.0
    block: float = 1.0
    draw: int = 0
    hand: int = 0
    burn: float = 1.0
    nuke: int = 0
    gold: int = 0
    price: float = 1.0
    heal: int = 0
    energy_cap: int = 0

    def merge(self, other: "Modifiers") -> "Modifiers":
        """叠加两个加成（倍率相乘，数值相加）。"""
        return Modifiers(
            supply=self.supply + other.supply,
            hp=self.hp + other.hp,
            damage=self.damage * other.damage,
            block=self.block * other.block,
            draw=self.draw + other.draw,
            hand=self.hand + other.hand,
            burn=self.burn * other.burn,
            nuke=self.nuke + other.nuke,
            gold=self.gold + other.gold,
            price=self.price * other.price,
            heal=self.heal + other.heal,
            energy_cap=self.energy_cap + other.energy_cap,
        )

    def is_neutral(self) -> bool:
        return self == Modifiers()


NEUTRAL = Modifiers()


# --------------------------------------------------------------------------
# 角色定义
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Commander:
    """一位辅助角色。"""

    id: str
    name: str              # 显示名（中文）
    name_en: str           # 英文名
    era: str               # 阵营 / 时期的短标签
    title: str             # 一句称号
    text: str              # 效果说明（给人看的一行）
    mods: Modifiers
    #: 解锁条件：0 = 一开始就有
    unlock_runs: int = 0


def _c(cid, name, name_en, era, title, text, unlock=0, **kw) -> Commander:
    return Commander(cid, name, name_en, era, title, text,
                     Modifiers(**kw), unlock)


#: 全部角色。数值都做过克制：单条加成不会改变游戏难度层级。
COMMANDERS: Dict[str, Commander] = {}


def _reg(c: Commander) -> None:
    COMMANDERS[c.id] = c


# ---- 后勤 / 指挥 ----------------------------------------------------------
_reg(_c("guderian", "古德里安", "Guderian", "装甲",
        "闪击先锋",
        "每回合 +1 指挥点；开局手牌 +1。",
        supply=1, hand=1))

_reg(_c("rommel", "隆美尔", "Rommel", "装甲",
        "沙漠之狐",
        "每回合 +1 指挥点；伤害 ×1.08。",
        supply=1, damage=1.08))

_reg(_c("patton", "巴顿", "Patton", "装甲",
        "血胆将军",
        "伤害 ×1.15；总部耐久 −8。",
        damage=1.15, hp=-8))

_reg(_c("zhukov", "朱可夫", "Zhukov", "统帅",
        "钢铁元帅",
        "总部耐久 +15；战后回复 +6。",
        hp=15, heal=6))

_reg(_c("rokossovsky", "罗科索夫斯基", "Rokossovsky", "统帅",
        "双线统帅",
        "每回合 +1 指挥点；指挥点上限 +1。",
        supply=1, energy_cap=1))

_reg(_c("manstein", "曼施坦因", "Manstein", "统帅",
        "镰刀闪击",
        "伤害 ×1.10；开局手牌 −1。",
        damage=1.10, hand=-1))

_reg(_c("montgomery", "蒙哥马利", "Montgomery", "统帅",
        "谨慎的胜利",
        "掩体 ×1.20；战后回复 +4。",
        block=1.20, heal=4))

_reg(_c("eisenhower", "艾森豪威尔", "Eisenhower", "盟军",
        "联军统筹",
        "开局金币 +40；商店价格 ×0.90。",
        gold=40, price=0.90))

# ---- 科研 / 武器 ----------------------------------------------------------
_reg(_c("oppenheimer", "奥本海默", "Oppenheimer", "科学",
        "曼哈顿计划",
        "核弹额外 +12 伤害；每回合 +1 指挥点。",
        nuke=12, supply=1))

_reg(_c("turing", "图灵", "Turing", "科学",
        "破译者",
        "每回合额外抽 1 张牌。",
        draw=1))

_reg(_c("von_neumann", "冯·诺依曼", "von Neumann", "科学",
        "计算之父",
        "每回合额外抽 1 张牌；总部耐久 −5。",
        draw=1, hp=-5))

_reg(_c("einstein", "爱因斯坦", "Einstein", "科学",
        "质能方程",
        "核弹额外 +18 伤害；伤害 ×0.95。",
        nuke=18, damage=0.95))

_reg(_c("fermi", "费米", "Fermi", "科学",
        "链式反应",
        "燃烧伤害 ×1.25。",
        burn=1.25))

_reg(_c("heisenberg", "海森堡", "Heisenberg", "科学",
        "不确定原理",
        "燃烧伤害 ×1.20；开局手牌 +1。",
        burn=1.20, hand=1))

_reg(_c("teller", "泰勒", "Teller", "科学",
        "氢弹之父",
        "核弹额外 +22 伤害；总部耐久 −10。",
        nuke=22, hp=-10))

_reg(_c("sikorsky", "西科斯基", "Sikorsky", "科学",
        "旋翼先驱",
        "每回合 +1 指挥点；掩体 ×0.92。",
        supply=1, block=0.92))

# ---- 空军 / 海军 ----------------------------------------------------------
_reg(_c("harris", "哈里斯", "Harris", "空军",
        "轰炸机司令",
        "燃烧伤害 ×1.30；掩体 ×0.90。",
        burn=1.30, block=0.90))

_reg(_c("doolittle", "杜立特", "Doolittle", "空军",
        "空袭东京",
        "伤害 ×1.12；每回合 +1 指挥点。",
        damage=1.12, supply=1))

_reg(_c("yamamoto", "山本五十六", "Yamamoto", "海军",
        "联合舰队",
        "每回合额外抽 1 张牌；伤害 ×1.05。",
        draw=1, damage=1.05))

_reg(_c("nimitz", "尼米兹", "Nimitz", "海军",
        "太平洋统帅",
        "总部耐久 +10；每回合 +1 指挥点。",
        hp=10, supply=1))

_reg(_c("cunningham", "坎宁安", "Cunningham", "海军",
        "地中海之锚",
        "掩体 ×1.15；战后回复 +5。",
        block=1.15, heal=5))

# ---- 后勤 / 工业 ----------------------------------------------------------
_reg(_c("speer", "施佩尔", "Speer", "工业",
        "军备部长",
        "开局金币 +60；商店价格 ×0.85。",
        gold=60, price=0.85))

_reg(_c("ford", "亨利·福特", "Henry Ford", "工业",
        "流水线",
        "开局金币 +30；每回合 +1 指挥点。",
        gold=30, supply=1))

_reg(_c("kaiser", "凯泽", "Kaiser", "工业",
        "自由轮",
        "总部耐久 +12；掩体 ×1.05。",
        hp=12, block=1.05))

_reg(_c("marshall", "马歇尔", "Marshall", "后勤",
        "胜利的基石",
        "战后回复 +8；开局金币 +20。",
        heal=8, gold=20))

_reg(_c("somervell", "萨默维尔", "Somervell", "后勤",
        "补给大动脉",
        "每回合 +1 指挥点；开局手牌 +1。",
        supply=1, hand=1))

# ---- 医疗 / 士气 ----------------------------------------------------------
_reg(_c("nightingale", "南丁格尔", "Nightingale", "医疗",
        "提灯女神",
        "战后回复 +10；总部耐久 +5。",
        heal=10, hp=5))

_reg(_c("bethune", "白求恩", "Bethune", "医疗",
        "前线医者",
        "战后回复 +12。",
        heal=12))

_reg(_c("zhang_zhizhong", "张自忠", "Zhang Zizhong", "抗战",
        "抗战军魂",
        "伤害 ×1.12；总部耐久 +8。",
        damage=1.12, hp=8))

_reg(_c("dowding", "道丁", "Dowding", "空军",
        "不列颠之盾",
        "掩体 ×1.25；每回合抽牌 −0（无副作用）。",
        block=1.25))


# --------------------------------------------------------------------------
# 查询
# --------------------------------------------------------------------------
def get(cid: str) -> Optional[Commander]:
    return COMMANDERS.get(str(cid or ""))


def all_commanders() -> List[Commander]:
    return list(COMMANDERS.values())


def starters() -> List[Commander]:
    """一开始就能用的角色。"""
    return [c for c in COMMANDERS.values() if c.unlock_runs <= 0]


def available(total_runs: int = 0) -> List[Commander]:
    """按累计局数解锁后还能用的角色。"""
    n = max(0, int(total_runs or 0))
    return [c for c in COMMANDERS.values() if c.unlock_runs <= n]


def mods_of(cid: Optional[str]) -> Modifiers:
    """取某位指挥官的加成（不存在返回中性）。"""
    c = get(cid) if cid else None
    return c.mods if c is not None else NEUTRAL


def registry():
    """给界面用的 {id: Commander}（和 COMMANDERS 同源，便于以后热改）。"""
    return dict(COMMANDERS)
