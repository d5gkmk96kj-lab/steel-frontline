"""钢铁战线 Steel Frontline — 对战卡组构筑器。

供 1v1 对战使用：玩家在开局时从**全部卡池**中自选牌组成一副对战卡组。

设计要点
--------
* 「开局满卡」= 解锁全部 134 张卡供挑选，**不看图鉴/解锁进度**。
* 所有随机走传入的 ``rng``（``random.Random`` 实例），可复现，禁止裸 ``random``。
* 所有公开函数**不抛异常**：非法输入返回 ``(False, 原因)`` 或空/兜底结果。
* 复用 ``core.cards`` 的数据库，不新增卡牌类型、不改动既有文件。
* 术语遵守 ARCHITECTURE.md 附录 B.1（补给 / 掩体 / 牌库 / 火力 / 燃烧 …）。
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from core import cards as C

# --------------------------------------------------------------------------
# 构筑规则常量
# --------------------------------------------------------------------------
DECK_SIZE_MIN = 20
DECK_SIZE_MAX = 40
MAX_COPIES = 2

#: 同名卡上限的一个例外：这两张是**初始制式牌**（1 费，数值最弱），
#: 放宽到 3 张，保证新手在 20 张下限时仍能组出「步枪+掩体」的稳定底子。
STARTER_CARD_IDS = frozenset({"strike", "defend"})
STARTER_MAX_COPIES = 3

#: 默认初始牌 id —— 构筑器给出的保底底牌。
DEFAULT_STRIKE = "strike"
DEFAULT_DEFEND = "defend"
DEFAULT_FILLER = "strike"

#: 构筑器默认排除的卡牌类型（除非玩家主动添加，作为代价牌）。
EXCLUDED_TYPES = frozenset({"status", "curse"})


# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------

def _norm_ids(card_ids) -> Optional[List[str]]:
    """把入参规整成 ``List[str]``；无法识别返回 None。"""
    if card_ids is None:
        return None
    if isinstance(card_ids, (str, bytes)):
        return None
    try:
        items = list(card_ids)
    except TypeError:
        return None
    out: List[str] = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, C.CardInstance):
            out.append(it.def_id)
        else:
            # 未知元素（None / 数字）保留为特殊标记，便于报错
            out.append(None)  # type: ignore[arg-type]
    return out


def _max_copies(def_id: str) -> int:
    """该卡的同名上限。初始制式牌放宽到 3。"""
    if def_id in STARTER_CARD_IDS:
        return STARTER_MAX_COPIES
    return MAX_COPIES


def card_pool(include_status: bool = False) -> List[str]:
    """可供挑选的卡牌 id 列表（**全部 134 张**，不看解锁进度）。

    ``include_status=False``（默认）时排除 status/curse 类。
    排序稳定（按 CARD_DB 原顺序），便于 UI 展示。
    """
    out: List[str] = []
    for cid, d in C.CARD_DB.items():
        if not include_status and d.type in EXCLUDED_TYPES:
            continue
        out.append(cid)
    return out


def arch_card_pool(arch: str, include_status: bool = False) -> List[str]:
    """某个流派（ARCH_*）的可选卡牌 id。"""
    return [cid for cid in card_pool(include_status)
            if C.CARD_DB[cid].arch == arch]


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------

def validate_deck(card_ids: list) -> Tuple[bool, str]:
    """校验一副对战卡组。

    返回 ``(是否合法, 原因)``；合法时原因为简短说明，非法时为具体原因。
    绝不抛异常。
    """
    ids = _norm_ids(card_ids)
    if ids is None:
        return False, "卡组格式不正确：需要一个卡牌 id 列表。"
    if not ids:
        return False, f"卡组不能为空，需要 {DECK_SIZE_MIN}–{DECK_SIZE_MAX} 张。"
    if len(ids) < DECK_SIZE_MIN:
        return False, (f"卡组只有 {len(ids)} 张，至少需要 {DECK_SIZE_MIN} 张。")
    if len(ids) > DECK_SIZE_MAX:
        return False, (f"卡组有 {len(ids)} 张，最多只能 {DECK_SIZE_MAX} 张。")

    counts: Dict[str, int] = {}
    for cid in ids:
        if not isinstance(cid, str):
            return False, "卡组里有无法识别的条目（应为卡牌 id 字符串）。"
        d = C.CARD_DB.get(cid)
        if d is None:
            return False, f"未知卡牌 id：{cid}。"
        # 规则必须与 card_pool() 一致：状态/诅咒牌不能**主动**进卡组。
        # 否则可构造出 20 张 cost=-2 的废牌卡组 —— 双方整局无牌可出，
        # 对战被软锁（联机时是恶意拖延手段）。
        if d.type in EXCLUDED_TYPES:
            return False, (f"「{d.name}」是无法主动使用的"
                           f"{'诅咒' if d.type == 'curse' else '状态'}牌，"
                           f"不能放入卡组。")
        counts[cid] = counts.get(cid, 0) + 1

    for cid, n in counts.items():
        limit = _max_copies(cid)
        if n > limit:
            d = C.CARD_DB[cid]
            return False, (f"「{d.name}」有 {n} 张，同名卡上限为 {limit} 张。")
    return True, f"合法卡组：{len(ids)} 张，共 {len(counts)} 种。"


def deck_summary(card_ids: list) -> dict:
    """给 UI 用的卡组概要（张数 / 种类 / 流派分布 / 平均费用）。纯数据。"""
    ids = _norm_ids(card_ids) or []
    ids = [c for c in ids if isinstance(c, str) and c in C.CARD_DB]
    archs: Dict[str, int] = {}
    types: Dict[str, int] = {}
    total_cost = 0
    for cid in ids:
        d = C.CARD_DB[cid]
        archs[d.arch] = archs.get(d.arch, 0) + 1
        types[d.type] = types.get(d.type, 0) + 1
        total_cost += max(0, int(d.cost))          # X 费按 0 计入均价
    return {
        "size": len(ids),
        "unique": len(set(ids)),
        "archs": archs,
        "types": types,
        "avg_cost": round(total_cost / len(ids), 2) if ids else 0.0,
        "valid": validate_deck(ids)[0] if ids else False,
    }


# --------------------------------------------------------------------------
# 随机 / 推荐卡组
# --------------------------------------------------------------------------

def _pick(rng: random.Random, pool: List[str], counts: Dict[str, int],
          n: int) -> List[str]:
    """从 pool 中按同名上限抽 n 张（可重复，受上限约束）。"""
    out: List[str] = []
    guard = 0
    candidates = list(pool)
    while len(out) < n and guard < n * 40:
        guard += 1
        if not candidates:
            break
        cid = candidates[rng.randrange(len(candidates))]
        if counts.get(cid, 0) >= _max_copies(cid):
            continue
        counts[cid] = counts.get(cid, 0) + 1
        out.append(cid)
    return out


def random_deck(rng: random.Random, size: int = 30,
                arch: Optional[str] = None) -> List[str]:
    """随机生成一副合法对战卡组。

    * ``arch`` 指定流派时，约 70% 的牌来自该流派，其余从全卡池补足。
    * ``size`` 会被夹到 ``[DECK_SIZE_MIN, DECK_SIZE_MAX]``。
    * 结果保证通过 :func:`validate_deck`。
    """
    if not isinstance(rng, random.Random):
        rng = random.Random()
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 30
    size = max(DECK_SIZE_MIN, min(DECK_SIZE_MAX, size))

    full = card_pool(include_status=False)
    if not full:                                   # pragma: no cover - 数据兜底
        return [DEFAULT_FILLER] * size

    counts: Dict[str, int] = {}
    deck: List[str] = []

    if arch in (C.ARCH_ATTACK, C.ARCH_BLOCK, C.ARCH_POISON,
                C.ARCH_ENERGY, C.ARCH_SUMMON):
        primary = arch_card_pool(arch)
        n_main = int(size * 0.7)
        deck += _pick(rng, primary, counts, n_main)
        deck += _pick(rng, full, counts, size - len(deck))
    else:
        deck += _pick(rng, full, counts, size)

    # 补足（理论上不会触发，防御性）
    guard = 0
    while len(deck) < size and guard < size * 40:
        guard += 1
        cid = full[rng.randrange(len(full))]
        if counts.get(cid, 0) >= _max_copies(cid):
            continue
        counts[cid] = counts.get(cid, 0) + 1
        deck.append(cid)

    rng.shuffle(deck)
    return deck


def _build_from_core(arch: str, core_ids: List[str], extras: List[str],
                     size: int = 30) -> List[str]:
    """组装一套推荐卡组：核心牌优先 → 制式牌打底 → 流派池补足到 ``size``。

    纯确定性（不抽随机、**与日期无关**），保证每次调用返回同一副卡组。
    每张牌都受 ``_max_copies`` 约束，因此返回值必定通过 :func:`validate_deck`。
    """
    counts: Dict[str, int] = {}
    deck: List[str] = []

    def push(cid: str) -> None:
        if cid not in C.CARD_DB or C.CARD_DB[cid].type in EXCLUDED_TYPES:
            return
        if counts.get(cid, 0) >= _max_copies(cid):
            return
        counts[cid] = counts.get(cid, 0) + 1
        deck.append(cid)

    for cid in core_ids:
        push(cid)
    for cid in extras:
        push(cid)
    # 先用制式牌（上限 3）填底，再上流派牌
    for _ in range(6):
        push(DEFAULT_STRIKE)
        push(DEFAULT_DEFEND)
    pool = arch_card_pool(arch) or card_pool()
    guard = 0
    while len(deck) < size and guard < size * 40:
        guard += 1
        push(pool[guard % len(pool)])
    return deck[:size]


def recommended_decks() -> dict:
    """五个流派各一套推荐卡组：``{"突击流": [...], ...}``。

    返回的是**卡牌 id 列表**，全部通过 :func:`validate_deck`。
    只使用 ``CARD_DB`` 中真实存在的 id；缺失的辅助牌会自动跳过。
    """
    decks: Dict[str, List[str]] = {
        "突击流": _build_from_core(
            C.ARCH_ATTACK,
            ["strike", "defend", "heavy_harpoon", "double_strike", "hold_the_line",
             "inflame", "cleave", "limit_break", "armor_piercer", "frenzy"],
            ["ram_charge", "rending_bite", "bait_lunge", "cross_slash"],
        ),
        "铁壁流": _build_from_core(
            C.ARCH_BLOCK,
            ["strike", "defend", "shrug_it_off", "iron_wave", "entrench",
             "barricade", "metallicize", "thorn_hide", "hold_the_line"],
            ["body_slam", "juggernaut", "armaments"],
        ),
        "蚀骨流": _build_from_core(
            C.ARCH_POISON,
            ["strike", "defend", "deadly_poison", "toxic_stab", "noxious_fumes",
             "catalyst", "corrode_bite", "bane"],
            ["poison_dart", "venom_strike", "toxin_uppercut"],
        ),
        "后勤流": _build_from_core(
            C.ARCH_ENERGY,
            ["strike", "defend", "tide_knot", "deep_current", "tidepool",
             "supply_drop", "recall", "chain_lightning"],
            ["cold_current", "whirlpool", "sweeping_blow"],
        ),
        "唤灵流": _build_from_core(
            C.ARCH_SUMMON,
            ["strike", "defend", "summon_guard", "rally", "whale_song",
             "deep_echo", "reinforce"],
            ["call_the_fleet", "war_hound"],
        ),
    }
    return decks


def starter_deck() -> List[str]:
    """一副最小可用的合法卡组（给「快速开始」用）。

    固定 30 张：制式牌打底 + 各流派各取若干张，保证新手每一局都有
    直伤、掩体、火力、燃烧、抽牌五类手段。**保证通过校验**。
    """
    counts: Dict[str, int] = {}
    deck: List[str] = []

    def push(cid: str) -> bool:
        if cid not in C.CARD_DB:
            return False
        if C.CARD_DB[cid].type in EXCLUDED_TYPES:
            return False
        if counts.get(cid, 0) >= _max_copies(cid):
            return False
        counts[cid] = counts.get(cid, 0) + 1
        deck.append(cid)
        return True

    # 1) 制式牌打底（上限 3 张）
    for _ in range(STARTER_MAX_COPIES):
        push(DEFAULT_STRIKE)
        push(DEFAULT_DEFEND)
    # 2) 五个流派各取 4 张，按默认顺序稳定挑选
    for arch in (C.ARCH_ATTACK, C.ARCH_BLOCK, C.ARCH_POISON,
                 C.ARCH_ENERGY, C.ARCH_SUMMON):
        took = 0
        for cid in arch_card_pool(arch):
            if took >= 4:
                break
            if push(cid):
                took += 1
    # 3) 补足到 30 张（从全卡池，受同名上限约束）
    pool = card_pool()
    guard = 0
    while len(deck) < 30 and guard < 400:
        guard += 1
        push(pool[guard % len(pool)])
    return deck


__all__ = [
    "DECK_SIZE_MIN", "DECK_SIZE_MAX", "MAX_COPIES",
    "STARTER_CARD_IDS", "STARTER_MAX_COPIES", "EXCLUDED_TYPES",
    "card_pool", "arch_card_pool", "validate_deck", "deck_summary",
    "random_deck", "recommended_decks", "starter_deck",
]
