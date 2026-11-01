#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解锁系统：把 203 张卡和 52 枚勋章分批开放。

设计原则
--------
* **不能一开局就把 200 张卡全摆出来** —— 那样既没有成长感，第一次玩的
  人也会被选择淹没。
* **但也不能太吝啬**：目标大约玩 10–15 局就能解锁绝大部分内容，
  每局都要能摸到新东西。
* **老存档必须兼容**：已经有进度的人不能因为这次更新突然丢卡。

分层
----
=================  ==========================  ==========================
稀有度             初始状态                     解锁方式
=================  ==========================  ==========================
基础 / 普通         全部解锁                      —
稀有 (uncommon)    0 张                         每局结束 +3，通关 +6
史诗 (rare)        0 张                         通关 +2，每通关一次再多 +1
=================  ==========================  ==========================

勋章同理，但节奏更慢（勋章总数少）。
"""

from __future__ import annotations

from typing import Iterable, List, Set, Tuple

from core import cards as C
from core import relics as R


#: 全新存档一开始就送几张 uncommon（否则前几局奖励清一色普通卡，太单调）
STARTER_UNCOMMON = 14
#: 每局结束（无论胜负）解锁几张 uncommon
UNCOMMON_PER_RUN = 3
#: 每局结束额外解锁几张（赢了才给）
UNCOMMON_PER_WIN = 6
#: 通关解锁几张 rare
RARE_PER_WIN = 2
#: 每局结束解锁几枚勋章
RELIC_PER_RUN = 1
#: 通关额外解锁几枚勋章
RELIC_PER_WIN = 2


def _card_ids_by_rarity(rarity: str) -> List[str]:
    out: List[str] = []
    for cd in C.CARD_LIST:
        if getattr(cd, "rarity", "") != rarity:
            continue
        # 状态牌 / 诅咒牌永远不该进奖励池，自然也不算解锁
        if getattr(cd, "type", "") in ("status", "curse"):
            continue
        out.append(cd.id)
    return sorted(out)


def starter_cards() -> Set[str]:
    """开局就有的卡：普通 + 基础。"""
    got = set(_card_ids_by_rarity(C.RARITY_COMMON))
    got |= set(_card_ids_by_rarity(C.RARITY_BASIC)) \
        if hasattr(C, "RARITY_BASIC") else set()
    # 起始卡组里的牌一定要有
    try:
        got |= {str(c) for c in C.STARTER_DECK}
    except Exception:
        pass
    return got


def starter_relics() -> Set[str]:
    """开局就有的勋章：普通稀有度。"""
    out: Set[str] = set()
    for rd in R.RELIC_LIST:
        if getattr(rd, "rarity", "") in (R.RARITY_COMMON,):
            out.add(rd.id)
    # 起始勋章必须有
    try:
        if R.STARTER_RELIC:
            out.add(str(R.STARTER_RELIC))
    except Exception:
        pass
    return out


def _pool(meta) -> Tuple[List[str], List[str], List[str]]:
    """返回（已解锁, 待解锁 uncommon, 待解锁 rare）三种卡 id。"""
    have: Set[str] = set(getattr(meta, "unlocked_cards", set()) or set())
    all_uncommon = _card_ids_by_rarity(C.RARITY_UNCOMMON)
    all_rare = _card_ids_by_rarity(C.RARITY_RARE)
    u = [i for i in all_uncommon if i not in have]
    r = [i for i in all_rare if i not in have]
    return sorted(have), u, r


def _relic_pool(meta) -> List[str]:
    have: Set[str] = set(getattr(meta, "unlocked_relics", set()) or set())
    out: List[str] = []
    for rd in R.RELIC_LIST:
        if getattr(rd, "rarity", "") == R.RARITY_COMMON:
            continue           # 普通勋章一开始就有
        if rd.id in have:
            continue
        out.append(rd.id)
    return sorted(out)


def migrate(meta) -> bool:
    """老存档兼容：已经有进度但解锁集合是空的 -> 补一大截。

    没有这一步的话，更新后老玩家会突然发现商店和奖励池只剩普通卡，
    看起来像"东西变少了"（真踩过的坑）。返回是否改动。
    """
    try:
        played = (int(getattr(meta, "total_runs", 0) or 0) > 0
                  or bool(getattr(meta, "story_done", False))
                  or int(getattr(meta, "wins", 0) or 0) > 0)
    except Exception:
        played = False
    if not played:
        return False
    changed = False
    try:
        cur = set(getattr(meta, "unlocked_cards", set()) or set())
        if not cur:
            base = starter_cards()
            # 按进度给：通关过主线的人基本全给
            uncommon = _card_ids_by_rarity(C.RARITY_UNCOMMON)
            rare = _card_ids_by_rarity(C.RARITY_RARE)
            if getattr(meta, "story_done", False):
                # 通关过：全部解锁（他们本来就都见过了）
                cur = base | set(uncommon) | set(rare)
            else:
                # 没通关但玩过：给七成 uncommon / 三成 rare
                n_u = int(len(uncommon) * 0.7)
                n_r = int(len(rare) * 0.3)
                cur = base | set(uncommon[:n_u]) | set(rare[:n_r])
            meta.unlocked_cards = cur
            changed = True
        rel = set(getattr(meta, "unlocked_relics", set()) or set())
        if not rel:
            base_r = starter_relics()
            others = _relic_pool(meta)
            if getattr(meta, "story_done", False):
                rel = base_r | set(others)
            else:
                rel = base_r | set(others[:int(len(others) * 0.5)])
            meta.unlocked_relics = rel
            changed = True
    except Exception:
        pass
    return changed


def ensure_starter(meta) -> bool:
    """保证基础内容和已解锁内容一直在集合里。返回是否改动。"""
    changed = False
    try:
        cur = set(getattr(meta, "unlocked_cards", set()) or set())
        base = starter_cards()
        # 全新存档：额外送一批 uncommon，保证开局就有稀有度变化
        if not cur:
            import random as _random
            pool = _card_ids_by_rarity(C.RARITY_UNCOMMON)
            rng = _random.Random(20251101)
            rng.shuffle(pool)
            base |= set(pool[:STARTER_UNCOMMON])
        if not base <= cur:
            meta.unlocked_cards = cur | base
            changed = True
        cur_r = set(getattr(meta, "unlocked_relics", set()) or set())
        base_r = starter_relics()
        if not base_r <= cur_r:
            meta.unlocked_relics = cur_r | base_r
            changed = True
    except Exception:
        pass
    return changed


def grant_after_run(meta, won: bool) -> List[str]:
    """一局结束后按规则解锁，返回**这次新解锁**的名字列表。"""
    newly: List[str] = []
    try:
        rng = _rng_for(meta)
        cur = set(getattr(meta, "unlocked_cards", set()) or set())
        _, unc, rare = _pool(meta)
        # uncommon
        n_u = UNCOMMON_PER_RUN + (UNCOMMON_PER_WIN if won else 0)
        for cid in _take(unc, n_u, rng):
            cur.add(cid)
            newly.append(_card_name(cid))
        # rare
        if won:
            n_r = RARE_PER_WIN + int(getattr(meta, "wins", 0) or 0) // 3
            for cid in _take(rare, min(n_r, 4), rng):
                cur.add(cid)
                newly.append(_card_name(cid))
        meta.unlocked_cards = cur

        # 勋章
        cur_r = set(getattr(meta, "unlocked_relics", set()) or set())
        pool = _relic_pool(meta)
        n_rel = RELIC_PER_RUN + (RELIC_PER_WIN if won else 0)
        for rid in _take(pool, n_rel, rng):
            cur_r.add(rid)
            newly.append(_relic_name(rid))
        meta.unlocked_relics = cur_r
    except Exception:
        pass
    return newly


def _rng_for(meta):
    """用一个稳定的伪随机（不污染游戏内 rng）。"""
    import random
    try:
        seed = (int(getattr(meta, "total_runs", 0) or 0) * 7919
                + int(getattr(meta, "wins", 0) or 0) * 104729
                + len(getattr(meta, "unlocked_cards", set()) or set()))
    except Exception:
        seed = 13
    return random.Random(seed)


def _take(pool: List[str], n: int, rng) -> List[str]:
    if n <= 0 or not pool:
        return []
    p = list(pool)
    rng.shuffle(p)
    return p[:min(n, len(p))]


def _card_name(cid: str) -> str:
    try:
        return C.CARD_DB[cid].name
    except Exception:
        return str(cid)


def _relic_name(rid: str) -> str:
    try:
        return R.RELIC_DB[rid].name
    except Exception:
        return str(rid)


def is_card_unlocked(meta, cid: str) -> bool:
    """这张卡现在能不能出现在奖励/商店里。"""
    try:
        cur = set(getattr(meta, "unlocked_cards", set()) or set())
        if not cur:
            return True        # 还没初始化：全开（不要让老存档丢内容）
        return str(cid) in cur
    except Exception:
        return True


def is_relic_unlocked(meta, rid: str) -> bool:
    try:
        cur = set(getattr(meta, "unlocked_relics", set()) or set())
        if not cur:
            return True
        return str(rid) in cur
    except Exception:
        return True


def progress(meta) -> dict:
    """解锁进度（给界面显示）。"""
    try:
        cur = set(getattr(meta, "unlocked_cards", set()) or set())
        u_total = len(_card_ids_by_rarity(C.RARITY_UNCOMMON))
        r_total = len(_card_ids_by_rarity(C.RARITY_RARE))
        all_card = set(_card_ids_by_rarity(C.RARITY_UNCOMMON)) | \
            set(_card_ids_by_rarity(C.RARITY_RARE))
        got = len(cur & all_card)
        total = u_total + r_total
        cur_r = set(getattr(meta, "unlocked_relics", set()) or set())
        all_relic = {rd.id for rd in R.RELIC_LIST}
        return {
            "cards_unlocked": got,
            "cards_total": total,
            "cards_pct": (100.0 * got / total) if total else 100.0,
            "relics_unlocked": len(cur_r & all_relic),
            "relics_total": len(all_relic),
        }
    except Exception:
        return {"cards_unlocked": 0, "cards_total": 0, "cards_pct": 100.0,
                "relics_unlocked": 0, "relics_total": 0}
