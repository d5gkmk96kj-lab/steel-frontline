#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新增卡组测试：破甲增伤流派 + 条件牌。

重点验证「设计意图真的成立」，而不只是"能打出去"：
  * 破甲（易伤）确实放大伤害
  * 火力确实增伤
  * 条件牌在满足条件时确实更强
"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TESTS = os.path.dirname(os.path.abspath(__file__))
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

from core import cards as C      # noqa: E402
from core import enemies as E    # noqa: E402
from core import engine as EN    # noqa: E402
from core import run as RM       # noqa: E402
from _util import enemy_combatant, first_enemy  # noqa: E402

NEW_IDS = [
    "armor_crack", "siege_shell", "mark_target", "chain_breach",
    "mass_mobilize", "last_stand", "arsenal_overload", "all_in",
    "reckless_assault", "scrap_heap", "ambush", "overrun", "bullet_hail",
    "desperate_gamble", "salvage", "deadweight_shot", "siege_momentum",
    "veteran_instinct", "fortify_line", "zero_hour",
]


def _battle(n_enemies: int = 1, hp: int = 400):
    r = RM.RunState()
    r.new_run(seed=7)
    es = [enemy_combatant(EN, E, "spine_minnow") for _ in range(n_enemies)]
    for e in es:
        e.hp = hp
        e.max_hp = hp
    b = EN.BattleState(r, es, random.Random(5))
    if hasattr(b, "start_battle"):
        b.start_battle()
    return b, es


def _play(b, cid: str, energy: int = 9):
    b.player.hand.clear()
    b.add_card_to_hand(cid, n=1)
    b.player.energy = energy
    return b.play_card(b.player.hand[-1], first_enemy(b))


def _damage(b, es, cid: str, prep=None) -> int:
    if prep:
        prep(b, es)
    b.player.hand.clear()
    b.add_card_to_hand(cid, n=1)
    b.player.energy = 9
    before = sum(e.hp for e in es)
    b.play_card(b.player.hand[-1], first_enemy(b))
    return before - sum(e.hp for e in es)


class TestCardsExist(unittest.TestCase):

    def test_all_present(self):
        for cid in NEW_IDS:
            with self.subTest(card=cid):
                self.assertIn(cid, C.CARD_DB, "卡 %s 没进 CARD_DB" % cid)

    def test_no_duplicate_ids(self):
        from collections import Counter
        cnt = Counter(c.id for c in C.CARD_LIST)
        dups = {k: v for k, v in cnt.items() if v > 1}
        self.assertEqual(dups, {}, "有重复的卡 id：%s" % dups)

    def test_no_duplicate_effect_names(self):
        """effect 函数不能重名 —— 重名会静默覆盖（真踩过）。"""
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "core", "cards.py"),
                   encoding="utf-8").read()
        from collections import Counter
        defs = re.findall(r"^def (\w+)\(", src, re.M)
        dups = {k: v for k, v in Counter(defs).items() if v > 1}
        self.assertEqual(dups, {}, "effect 函数重名：%s" % dups)

    def test_all_playable(self):
        for cid in NEW_IDS:
            with self.subTest(card=cid):
                b, _ = _battle()
                self.assertTrue(_play(b, cid), "%s 打不出去" % cid)

    def test_in_reward_pool(self):
        """新卡必须能作为奖励出现，否则等于没加。"""
        for cid in NEW_IDS:
            d = C.CARD_DB[cid]
            with self.subTest(card=cid):
                self.assertNotEqual(d.rarity, "basic")
                self.assertNotIn(d.type, ("curse", "status"))


class TestArmorBreak(unittest.TestCase):
    """破甲：施加易伤，并真的放大伤害。"""

    def test_applies_vulnerable(self):
        b, es = _battle()
        _play(b, "armor_crack")
        self.assertGreater(es[0].buffs.get("vulnerable", 0), 0,
                           "破甲弹没有施加易伤")

    def test_vulnerable_amplifies_damage(self):
        b1, e1 = _battle()
        _play(b1, "armor_crack")
        b2, e2 = _battle()
        d_with = b1.deal_damage(b1.player, e1[0], 10)
        d_without = b2.deal_damage(b2.player, e2[0], 10)
        self.assertGreater(d_with, d_without,
                           "易伤没有放大伤害（%d vs %d）" % (d_with, d_without))

    def test_mass_vulnerable(self):
        """连环破袭必须给所有敌人上破甲。"""
        b, es = _battle(n_enemies=3)
        _play(b, "chain_breach")
        for i, e in enumerate(es):
            with self.subTest(enemy=i):
                self.assertGreater(e.buffs.get("vulnerable", 0), 0)

    def test_zero_hour_also_breaks_armor(self):
        b, es = _battle(n_enemies=2)
        _play(b, "zero_hour")
        self.assertGreater(es[0].buffs.get("vulnerable", 0), 0)


class TestStrength(unittest.TestCase):
    """增伤：获得火力，并真的提高伤害。"""

    def test_strength_amplifies(self):
        b, es = _battle()
        base = b.deal_damage(b.player, es[0], 10)
        _play(b, "arsenal_overload")
        after = b.deal_damage(b.player, es[0], 10)
        self.assertGreater(after, base, "火力没有增伤")

    def test_mass_mobilize_scales_with_cards_played(self):
        """全军动员：本回合已出牌越多，火力越高。"""
        b1, _ = _battle()
        _play(b1, "mass_mobilize")
        low = b1.player.buffs.get("strength", 0)

        b2, _ = _battle()
        for _ in range(3):
            b2.player.hand.clear()
            b2.add_card_to_hand("strike")
            b2.player.energy = 9
            b2.play_card(b2.player.hand[-1], first_enemy(b2))
        _play(b2, "mass_mobilize")
        high = b2.player.buffs.get("strength", 0)
        self.assertGreater(high, low, "全军动员没有随出牌数增长")


class TestConditionalCards(unittest.TestCase):
    """条件牌：满足条件时明显更强。"""

    def test_last_stand_scales_with_missing_hp(self):
        b_full, _ = _battle()
        _play(b_full, "last_stand")
        full = b_full.player.buffs.get("strength", 0)

        b_low, _ = _battle()
        b_low.player.hp = max(1, b_low.player.max_hp // 6)
        _play(b_low, "last_stand")
        low = b_low.player.buffs.get("strength", 0)
        self.assertGreater(low, full, "背水一战在残血时没有更强")

    def test_ambush_stronger_as_first_card(self):
        first = _damage(*_battle(), "ambush")

        def _prep(b, es):
            b.player.hand.clear()
            b.add_card_to_hand("strike")
            b.player.energy = 9
            b.play_card(b.player.hand[-1], first_enemy(b))

        b, es = _battle()
        later = _damage(b, es, "ambush", prep=_prep)
        self.assertGreater(first, later, "伏击第一张打出时没有更强")

    def test_overrun_scales_with_enemy_count(self):
        one = _damage(*_battle(n_enemies=1), "overrun")
        three = _damage(*_battle(n_enemies=3), "overrun")
        self.assertGreater(three, one, "碾压没有随敌人数量增长")

    def test_bullet_hail_hits_every_enemy(self):
        one = _damage(*_battle(n_enemies=1), "bullet_hail")
        three = _damage(*_battle(n_enemies=3), "bullet_hail")
        self.assertGreater(three, one, "弹幕覆盖没有随敌人数量增长")

    def test_deadweight_shot_scales_with_cards_played(self):
        first = _damage(*_battle(), "deadweight_shot")

        def _prep(b, es):
            for _ in range(3):
                b.player.hand.clear()
                b.add_card_to_hand("strike")
                b.player.energy = 9
                b.play_card(b.player.hand[-1], first_enemy(b))

        b, es = _battle()
        later = _damage(b, es, "deadweight_shot", prep=_prep)
        self.assertGreater(later, first, "负重射击没有随出牌数增长")

    def test_desperate_gamble_needs_low_hp(self):
        b_hi, _ = _battle()
        _play(b_hi, "desperate_gamble")
        hi = b_hi.player.buffs.get("strength", 0)

        b_lo, _ = _battle()
        b_lo.player.hp = max(1, b_lo.player.max_hp // 10)
        _play(b_lo, "desperate_gamble")
        lo = b_lo.player.buffs.get("strength", 0)
        self.assertGreater(lo, hi, "绝境豪赌在残血时没有更强")

    def test_scrap_heap_scales_with_hand_size(self):
        """注意：效果读的是「生效瞬间的手牌」——打出时这张牌本身已离开手牌。
        所以对比的是「手上留几张其它牌」。"""
        def _hit(n_extra: int) -> int:
            b, es = _battle()
            b.player.hand.clear()
            for _ in range(n_extra):
                b.add_card_to_hand("strike")
            b.add_card_to_hand("scrap_heap")
            b.player.energy = 9
            before = es[0].hp
            b.play_card(b.player.hand[-1], es[0])
            return before - es[0].hp

        low = _hit(1)
        high = _hit(6)
        self.assertGreater(high, low,
                           "废铁堆没有随手牌数增长（%d vs %d）" % (high, low))

    def test_salvage_draws_more_when_hand_empty(self):
        """手牌少时抽 4 张；手牌多时只抽 1 张。"""
        def _left(n_extra: int) -> int:
            b, es = _battle()
            b.player.hand.clear()
            for _ in range(n_extra):
                b.add_card_to_hand("strike")
            b.add_card_to_hand("salvage")
            b.player.energy = 9
            b.play_card(b.player.hand[-1], first_enemy(b))
            return len(b.player.hand)

        empty = _left(0)      # 打出前只有 salvage 自己
        many = _left(4)       # 打出前手上有 5 张
        self.assertGreater(empty, 1, "手牌空时没有多抽")
        self.assertLess(many, empty + 4,
                        "手牌多时抽太多了")


class TestRiskyCards(unittest.TestCase):

    def test_all_in_applies_frail_to_self(self):
        b, _ = _battle()
        _play(b, "all_in")
        self.assertGreater(b.player.buffs.get("frail", 0), 0,
                           "孤注一掷没有给自己脆弱")
        self.assertGreater(b.player.buffs.get("strength", 0), 0)

    def test_arsenal_overload_costs_hp(self):
        b, _ = _battle()
        before = b.player.hp
        _play(b, "arsenal_overload")
        self.assertLess(b.player.hp, before, "弹药过载没有扣血")

    def test_reckless_assault_costs_hp(self):
        b, _ = _battle()
        before = b.player.hp
        _play(b, "reckless_assault")
        self.assertLess(b.player.hp, before, "蛮勇突击没有扣血")

    def test_self_damage_never_kills(self):
        """自伤不能把玩家打死（至少留 1 点）。"""
        for cid in ("arsenal_overload", "reckless_assault"):
            with self.subTest(card=cid):
                b, _ = _battle()
                b.player.hp = 1
                _play(b, cid)
                self.assertGreaterEqual(b.player.hp, 1,
                                        "%s 把玩家打死了" % cid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
