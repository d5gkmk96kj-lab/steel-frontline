#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面插图的「构图数据」—— 纯数据，不含任何 Qt 依赖。

为什么单独成文件：
  199 张卡如果全长一样，卡组看起来就是一堆重复方块。
  这里按 **流派 × 稀有度 × 数值** 生成一套确定的构图参数，
  让每张卡在视觉上都能分辨出来，同时保持统一的军事蚀刻风格。

  纯数据的好处是可以在没有 Qt 的环境里单测（CI 跑得快）。

设计
----
每张卡得到一份 ``Composition``：

* ``motif``      主图案（步枪 / 沙袋 / 油桶 / 火焰 / 电台 …）
* ``motifs``     次要装饰（弹孔 / 铆钉 / 烟 / 电缆 …）
* ``count``      主图案数量（由数值决定，1~4）
* ``density``    装饰密度 0~1
* ``angle``      整体倾角（让每张卡有微妙差异）
* ``band``       底部色带（稀有度）
* ``seed``       用于确定性随机（同一张卡永远同一个样子）
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------- 数据模型 --
@dataclass(frozen=True)
class Composition:
    """一张卡的插图构图。"""

    motif: str = "rifle"
    motifs: Tuple[str, ...] = ()
    count: int = 1
    density: float = 0.5
    angle: float = 0.0
    band: str = "common"
    seed: int = 0
    accent: float = 1.0          # 主色亮度系数


# ------------------------------------------------------------------ 流派 --
#: 五个流派的视觉母题（每个流派的卡都共享这套语汇）
ARCH_MOTIFS = {
    "attack": ("rifle", ("bullet_holes", "sight_ticks", "smoke")),
    "block": ("sandbags", ("wire", "rivets", "trench")),
    "energy": ("fuel_drum", ("gears", "cables", "crate")),
    "poison": ("flame", ("gas_cloud", "radiation", "embers")),
    "summon": ("radio", ("antenna", "troops", "signal")),
}

#: type 兜底（有些卡 arch 缺失）
TYPE_TO_ARCH = {
    "attack": "attack",
    "power": "summon",
    "skill": "block",
    "status": "poison",
    "curse": "poison",
}

#: 稀有度 -> 底部色带 + 装饰密度
RARITY_BAND = {
    "common": ("steel", 0.35),
    "uncommon": ("bronze", 0.50),
    "rare": ("gold", 0.68),
    "legendary": ("crimson", 0.85),
}


def _seed_of(card_id: str) -> int:
    h = hashlib.sha256((card_id or "x").encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _pick(rng: int, items) -> str:
    if not items:
        return ""
    return items[rng % len(items)]


def compose(card: dict) -> Composition:
    """由一张卡的数据算出插图构图。

    card 至少需要 ``def_id`` / ``type`` / ``arch``，
    可选 ``damage`` / ``block`` / ``cost`` / ``rarity``。
    """
    cid = str(card.get("def_id") or card.get("id") or "x")
    seed = _seed_of(cid)

    arch = str(card.get("arch") or "")
    if arch not in ARCH_MOTIFS:
        arch = TYPE_TO_ARCH.get(str(card.get("type") or "skill"), "block")
    motif, extras = ARCH_MOTIFS[arch]

    # 数量：伤害/格挡数值越大，主图案越多（1~4）
    num = 0
    for key in ("damage", "block"):
        try:
            num = max(num, int(card.get(key) or 0))
        except (TypeError, ValueError):
            pass
    if num <= 0:
        try:
            num = int(card.get("cost") or 1)
        except (TypeError, ValueError):
            num = 1
    count = 1 if num <= 2 else 2 if num <= 5 else 3 if num <= 9 else 4

    rar = str(card.get("rarity") or "common")
    band, dens = RARITY_BAND.get(rar, RARITY_BAND["common"])

    # 装饰：从该流派的装饰里挑 2~3 个（确定性）
    n_extra = 2 + (seed % 2)
    picked: List[str] = []
    for i in range(n_extra):
        m = extras[(seed >> (i * 3)) % len(extras)]
        if m not in picked:
            picked.append(m)

    # 倾角：轻微差异，避免每张卡死板
    angle = ((seed >> 5) % 7) - 3.0

    # 主色亮度：稀有度越高越亮
    accent = {"common": 0.95, "uncommon": 1.05,
              "rare": 1.18, "legendary": 1.35}.get(rar, 1.0)

    return Composition(
        motif=motif,
        motifs=tuple(picked),
        count=count,
        density=max(0.0, min(1.0, dens)),
        angle=float(angle),
        band=band,
        seed=seed,
        accent=float(accent),
    )


#: 供 UI 用的母题清单（测试里断言完整性）
ALL_MOTIFS = tuple(sorted({m for m, _ in ARCH_MOTIFS.values()} |
                          {x for _, e in ARCH_MOTIFS.values() for x in e}))
