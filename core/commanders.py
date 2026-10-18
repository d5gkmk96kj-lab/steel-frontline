#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""辅助角色（指挥官）：6 个国家，每国 5 位，共 30 位。

设计
----
* **纯数据 + 纯函数**：本模块不依赖 Qt，也不改引擎内部状态。
* 加成都通过 ``Modifiers`` 表达，引擎在结算时查询，方便测试与存档。
* 用的是**真实历史人物的名字**（姓名本身不构成著作权）；
  效果为游戏化改编，不代表对历史人物的评价。

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

from dataclasses import dataclass
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
# 国家
# --------------------------------------------------------------------------
NATION_CN = "CN"          # 中国 / China
NATION_US = "US"          # 美国 / USA
NATION_JP = "JP"          # 日本 / Japan
NATION_SU = "SU"          # 苏联 / USSR
NATION_DE = "DE"          # 德国 / Germany
NATION_GB = "GB"          # 英国 / Britain

#: 国家代码 -> 中文名
NATION_NAMES: Dict[str, str] = {
    "CN": "中国",
    "US": "美国",
    "JP": "日本",
    "SU": "苏联",
    "DE": "德国",
    "GB": "英国",
}

#: 国家代码 -> 英文名
NATION_NAMES_EN: Dict[str, str] = {
    "CN": "China",
    "US": "USA",
    "JP": "Japan",
    "SU": "USSR",
    "DE": "Germany",
    "GB": "Britain",
}

#: 界面里的显示顺序
NATION_ORDER: List[str] = [
    "CN",
    "US",
    "JP",
    "SU",
    "DE",
    "GB",
]


# --------------------------------------------------------------------------
# 角色
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Commander:
    """一位辅助角色。"""

    id: str
    name: str          # 中文名
    name_en: str       # 英文名
    nation: str        # 国家代码
    title: str         # 一句称号
    text: str          # 效果说明
    mods: Modifiers
    unlock_runs: int = 0

    @property
    def era(self) -> str:
        """兼容旧字段：返回国家中文名。"""
        return NATION_NAMES.get(self.nation, self.nation)


#: 全部角色（按国家分组定义，扁平存进这个 dict）
COMMANDERS: Dict[str, Commander] = {}


def _reg(c: Commander) -> None:
    COMMANDERS[c.id] = c


# ---- 中国 / China ----------------------------------------------------
_reg(Commander("sun_yatsen", "孙中山", "Sun Yat-sen", "CN",
                 "民族先驱", "总部耐久 +12；开局金币 +25。", Modifiers(hp=12, gold=25)))
_reg(Commander("mao", "毛泽东", "Mao Zedong", "CN",
                 "持久战", "每回合 +1 指挥点；战后回复 +6。", Modifiers(supply=1, heal=6)))
_reg(Commander("zhu_de", "朱德", "Zhu De", "CN",
                 "总司令", "伤害 ×1.10；总部耐久 +6。", Modifiers(damage=1.10, hp=6)))
_reg(Commander("peng", "彭德怀", "Peng Dehuai", "CN",
                 "百团大战", "伤害 ×1.15；掩体 ×0.94。", Modifiers(damage=1.15, block=0.94)))
_reg(Commander("xue_yue", "薛岳", "Xue Yue", "CN",
                 "天炉战法", "掩体 ×1.25；每回合 +1 指挥点。", Modifiers(block=1.25, supply=1)))

# ---- 美国 / USA ----------------------------------------------------
_reg(Commander("roosevelt", "罗斯福", "Roosevelt", "US",
                 "新政", "开局金币 +50；商店价格 ×0.88。", Modifiers(gold=50, price=0.88)))
_reg(Commander("eisenhower", "艾森豪威尔", "Eisenhower", "US",
                 "联军统筹", "每回合额外抽 1 张牌；掩体 ×1.08。", Modifiers(draw=1, block=1.08)))
_reg(Commander("patton", "巴顿", "Patton", "US",
                 "血胆将军", "伤害 ×1.15；总部耐久 −8。", Modifiers(damage=1.15, hp=-8)))
_reg(Commander("nimitz", "尼米兹", "Nimitz", "US",
                 "太平洋统帅", "总部耐久 +10；每回合 +1 指挥点。", Modifiers(hp=10, supply=1)))
_reg(Commander("oppenheimer", "奥本海默", "Oppenheimer", "US",
                 "曼哈顿计划", "核弹额外 +12 伤害；每回合 +1 指挥点。", Modifiers(nuke=12, supply=1)))

# ---- 日本 / Japan ----------------------------------------------------
_reg(Commander("hirohito", "裕仁", "Hirohito", "JP",
                 "御前会议", "每回合 +1 指挥点；开局手牌 +1。", Modifiers(supply=1, hand=1)))
_reg(Commander("tojo", "东条英机", "Tojo Hideki", "JP",
                 "战时内阁", "伤害 ×1.12；掩体 ×0.92。", Modifiers(damage=1.12, block=0.92)))
_reg(Commander("yamamoto", "山本五十六", "Yamamoto Isoroku", "JP",
                 "联合舰队", "每回合额外抽 1 张牌；伤害 ×1.05。", Modifiers(draw=1, damage=1.05)))
_reg(Commander("okamura", "冈村宁次", "Okamura Yasuji", "JP",
                 "华北方面军", "燃烧伤害 ×1.20；伤害 ×1.06。", Modifiers(burn=1.20, damage=1.06)))
_reg(Commander("nagumo", "南云忠一", "Nagumo Chuichi", "JP",
                 "机动部队", "伤害 ×1.18；总部耐久 −6。", Modifiers(damage=1.18, hp=-6)))

# ---- 苏联 / USSR ----------------------------------------------------
_reg(Commander("stalin", "斯大林", "Stalin", "SU",
                 "最高统帅", "伤害 ×1.10；总部耐久 −5。", Modifiers(damage=1.10, hp=-5)))
_reg(Commander("zhukov", "朱可夫", "Zhukov", "SU",
                 "钢铁元帅", "总部耐久 +15；战后回复 +6。", Modifiers(hp=15, heal=6)))
_reg(Commander("rokossovsky", "罗科索夫斯基", "Rokossovsky", "SU",
                 "双线统帅", "每回合 +1 指挥点；指挥点上限 +1。", Modifiers(supply=1, energy_cap=1)))
_reg(Commander("konev", "科涅夫", "Konev", "SU",
                 "乌克兰方面军", "伤害 ×1.12；掩体 ×1.05。", Modifiers(damage=1.12, block=1.05)))
_reg(Commander("vasilevsky", "华西列夫斯基", "Vasilevsky", "SU",
                 "远东闪击", "伤害 ×1.16；开局手牌 −1。", Modifiers(damage=1.16, hand=-1)))

# ---- 德国 / Germany ----------------------------------------------------
_reg(Commander("hitler", "希特勒", "Hitler", "DE",
                 "元首", "伤害 ×1.15；总部耐久 −10。", Modifiers(damage=1.15, hp=-10)))
_reg(Commander("guderian", "古德里安", "Guderian", "DE",
                 "闪击先锋", "每回合 +1 指挥点；开局手牌 +1。", Modifiers(supply=1, hand=1)))
_reg(Commander("manstein", "曼施坦因", "Manstein", "DE",
                 "镰刀闪击", "伤害 ×1.10；开局手牌 −1。", Modifiers(damage=1.10, hand=-1)))
_reg(Commander("rommel", "隆美尔", "Rommel", "DE",
                 "沙漠之狐", "每回合 +1 指挥点；伤害 ×1.08。", Modifiers(supply=1, damage=1.08)))
_reg(Commander("speer", "施佩尔", "Speer", "DE",
                 "军备部长", "开局金币 +60；商店价格 ×0.85。", Modifiers(gold=60, price=0.85)))

# ---- 英国 / Britain ----------------------------------------------------
_reg(Commander("churchill", "丘吉尔", "Churchill", "GB",
                 "我们决不投降", "总部耐久 +18；伤害 ×1.05。", Modifiers(hp=18, damage=1.05)))
_reg(Commander("montgomery", "蒙哥马利", "Montgomery", "GB",
                 "谨慎的胜利", "掩体 ×1.20；战后回复 +4。", Modifiers(block=1.20, heal=4)))
_reg(Commander("harris", "哈里斯", "Harris", "GB",
                 "轰炸机司令", "燃烧伤害 ×1.30；掩体 ×0.90。", Modifiers(burn=1.30, block=0.90)))
_reg(Commander("dowding", "道丁", "Dowding", "GB",
                 "不列颠之盾", "掩体 ×1.25。", Modifiers(block=1.25)))
_reg(Commander("turing", "图灵", "Turing", "GB",
                 "破译者", "每回合额外抽 1 张牌。", Modifiers(draw=1)))



# --------------------------------------------------------------------------
# 查询
# --------------------------------------------------------------------------
def get(cid: str) -> Optional[Commander]:
    return COMMANDERS.get(str(cid or ""))


def all_commanders() -> List[Commander]:
    return list(COMMANDERS.values())


def by_nation(code: str) -> List[Commander]:
    """某国的全部角色（按定义顺序）。"""
    return [c for c in COMMANDERS.values() if c.nation == str(code or "")]


def grouped() -> List[tuple]:
    """按国家分组：[(国家代码, 中文名, 英文名, [角色...]), ...]"""
    out = []
    for code in NATION_ORDER:
        out.append((code, NATION_NAMES.get(code, code),
                    NATION_NAMES_EN.get(code, code), by_nation(code)))
    return out


def starters() -> List[Commander]:
    return [c for c in COMMANDERS.values() if c.unlock_runs <= 0]


def available(total_runs: int = 0) -> List[Commander]:
    n = max(0, int(total_runs or 0))
    return [c for c in COMMANDERS.values() if c.unlock_runs <= n]


def mods_of(cid: Optional[str]) -> Modifiers:
    """取某位指挥官的加成（不存在返回中性）。"""
    c = get(cid) if cid else None
    return c.mods if c is not None else NEUTRAL


def registry():
    return dict(COMMANDERS)
