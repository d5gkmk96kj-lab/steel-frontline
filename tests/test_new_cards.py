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


# ==========================================================================
# 第三批：指挥点 / 干扰 / 范围 / 科研 / 单位
# ==========================================================================

BATCH3 = [
    "supply_drop", "logistics_chain", "all_hands_on_deck",
    "emergency_requisition", "winter_stockpile",
    "suppress_fire", "disarm", "jam_comms", "break_morale", "scatter",
    "rust_rounds", "carpet_bomb", "artillery_barrage", "scorched_earth",
    "shrapnel_storm", "research_basic", "research_advanced",
    "research_breakthrough", "prototype_weapon",
    "deploy_riflemen", "deploy_mg_nest", "deploy_tank", "deploy_artillery",
    "deploy_engineer", "deploy_command_tank",
]


class TestBatch3Exists(unittest.TestCase):

    def test_all_present(self):
        for cid in BATCH3:
            with self.subTest(card=cid):
                self.assertIn(cid, C.CARD_DB)

    def test_all_playable(self):
        for cid in BATCH3:
            with self.subTest(card=cid):
                b, _ = _battle(n_enemies=3)
                b.player.energy = 20
                b.player.hand.clear()
                b.add_card_to_hand(cid, n=1)
                self.assertTrue(b.play_card(b.player.hand[-1],
                                            first_enemy(b)),
                                "%s 打不出去" % cid)

    def test_in_reward_pool(self):
        for cid in BATCH3:
            d = C.CARD_DB[cid]
            with self.subTest(card=cid):
                self.assertNotEqual(d.rarity, "basic")
                self.assertNotIn(d.type, ("curse", "status"))


class TestCommandPoints(unittest.TestCase):
    """指挥点卡：必须真的回本或赚。"""

    def _energy_delta(self, cid: str) -> int:
        """打出这张牌之后的「能量变化」（含扣费）。

        注意要先给够能量，否则 1 费的牌根本打不出去（测试会误判成"没给能量"）。
        """
        b, _ = _battle()
        b.player.energy = 10
        start = b.player.energy
        b.player.hand.clear()
        b.add_card_to_hand(cid, n=1)
        cost = b.card_cost(b.player.hand[-1])
        if not b.play_card(b.player.hand[-1], first_enemy(b)):
            raise AssertionError("%s 打不出去" % cid)
        return b.player.energy - (start - cost)

    def test_all_gain_energy(self):
        for cid in ("supply_drop", "logistics_chain", "all_hands_on_deck",
                    "emergency_requisition", "winter_stockpile"):
            with self.subTest(card=cid):
                self.assertGreater(self._energy_delta(cid), 0,
                                   "%s 没有给指挥点" % cid)

    def test_zero_cost_ones_are_net_positive(self):
        """0 费的后勤链 / 空投补给必须净赚（否则没人带）。"""
        for cid in ("logistics_chain", "supply_drop"):
            with self.subTest(card=cid):
                b, _ = _battle()
                b.player.energy = 5
                b.player.hand.clear()
                b.add_card_to_hand(cid, n=1)
                cost = b.card_cost(b.player.hand[-1])
                self.assertEqual(cost, 0, "%s 不是 0 费" % cid)
                b.play_card(b.player.hand[-1], first_enemy(b))
                self.assertGreater(b.player.energy, 5,
                                   "%s 没有净赚指挥点" % cid)


class TestAreaDamage(unittest.TestCase):
    """范围攻击：必须打到所有敌人。"""

    def test_hits_all_enemies(self):
        for cid in ("carpet_bomb", "artillery_barrage", "shrapnel_storm",
                    "prototype_weapon"):
            with self.subTest(card=cid):
                b, es = _battle(n_enemies=3)
                b.player.energy = 20
                b.player.hand.clear()
                b.add_card_to_hand(cid, n=1)
                b.play_card(b.player.hand[-1], first_enemy(b))
                for i, e in enumerate(es):
                    self.assertLess(e.hp, e.max_hp,
                                    "%s 没打到第 %d 个敌人" % (cid, i))

    def test_scales_with_enemy_count(self):
        """3 个敌人的总伤害必须高于 1 个。"""
        def total(cid, n):
            b, es = _battle(n_enemies=n)
            b.player.energy = 20
            b.player.hand.clear()
            b.add_card_to_hand(cid, n=1)
            before = sum(e.hp for e in es)
            b.play_card(b.player.hand[-1], first_enemy(b))
            return before - sum(e.hp for e in es)

        for cid in ("carpet_bomb", "artillery_barrage", "prototype_weapon"):
            with self.subTest(card=cid):
                self.assertGreater(total(cid, 3), total(cid, 1))


class TestDisrupt(unittest.TestCase):

    def test_weak_applied(self):
        b, es = _battle()
        _play(b, "suppress_fire")
        self.assertGreater(es[0].buffs.get("weak", 0), 0)

    def test_break_morale_strips_strength(self):
        """瓦解士气施加的是「弹药短缺」（strength_down），
        每层让敌人攻击 -1 —— 这是独立的 debuff 键，不是直接扣 strength。"""
        b, es = _battle()
        _play(b, "break_morale")
        self.assertGreater(es[0].buffs.get("strength_down", 0), 0,
                           "瓦解士气没有施加弹药短缺")

    def test_strength_down_reduces_enemy_damage(self):
        """弹药短缺必须真的降低敌人伤害。"""
        b1, e1 = _battle()
        b1.apply_buff(e1[0], "strength_down", 3)
        d_with = b1.deal_damage(e1[0], b1.player, 10)
        b2, e2 = _battle()
        d_without = b2.deal_damage(e2[0], b2.player, 10)
        self.assertLess(d_with, d_without,
                        "弹药短缺没有降低敌人伤害（%d vs %d）"
                        % (d_with, d_without))

    def test_jam_comms_hits_all(self):
        b, es = _battle(n_enemies=3)
        _play(b, "jam_comms")
        for i, e in enumerate(es):
            with self.subTest(enemy=i):
                self.assertGreater(e.buffs.get("weak", 0), 0)


class TestResearch(unittest.TestCase):
    """科研链：初级 -> 高级 -> 突破，收益递进。"""

    def test_basic_gives_strength(self):
        b, _ = _battle()
        _play(b, "research_basic")
        self.assertGreater(b.player.buffs.get("strength", 0), 0)

    def test_advanced_scales_with_research_in_hand(self):
        b1, _ = _battle()
        b1.player.hand.clear()
        b1.add_card_to_hand("research_advanced")
        b1.player.energy = 20
        b1.play_card(b1.player.hand[-1], first_enemy(b1))
        low = b1.player.buffs.get("strength", 0)

        b2, _ = _battle()
        b2.player.hand.clear()
        b2.add_card_to_hand("research_basic")
        b2.add_card_to_hand("research_basic")
        b2.add_card_to_hand("research_advanced")
        b2.player.energy = 20
        b2.play_card(b2.player.hand[-1], first_enemy(b2))
        high = b2.player.buffs.get("strength", 0)
        self.assertGreater(high, low, "高级科研没有随科研牌数量增长")

    def test_breakthrough_grows(self):
        """科研突破打多次应该越叠越高。"""
        b, _ = _battle()
        b.player.energy = 99
        gains = []
        for _ in range(3):
            b.player.hand.clear()
            b.add_card_to_hand("research_breakthrough")
            b.player.energy = 99
            before = b.player.buffs.get("strength", 0)
            b.play_card(b.player.hand[-1], first_enemy(b))
            gains.append(b.player.buffs.get("strength", 0) - before)
        self.assertGreater(gains[-1], gains[0],
                           "科研突破没有越打越强：%s" % gains)

    def test_prototype_is_overtuned(self):
        """超模范围卡：3 个敌人时总伤害应高于普通范围卡。"""
        def total(cid):
            b, es = _battle(n_enemies=3)
            b.player.energy = 20
            b.player.hand.clear()
            b.add_card_to_hand(cid, n=1)
            before = sum(e.hp for e in es)
            b.play_card(b.player.hand[-1], first_enemy(b))
            return before - sum(e.hp for e in es)

        self.assertGreater(total("prototype_weapon"), total("carpet_bomb"))


class TestUnits(unittest.TestCase):
    """单位：部署后真的会被召唤，并且每回合自动攻击。"""

    UNIT_CARDS = {
        "deploy_riflemen": "步兵班",
        "deploy_mg_nest": "机枪巢",
        "deploy_tank": "中型坦克",
        "deploy_artillery": "野战炮",
        "deploy_engineer": "工兵连",
        "deploy_command_tank": "指挥坦克",
    }

    def test_summons_a_unit(self):
        for cid, name in self.UNIT_CARDS.items():
            with self.subTest(card=cid):
                b, _ = _battle()
                _play(b, cid)
                names = [m.name for m in b.player.minions]
                self.assertIn(name, names,
                              "%s 没有召唤出「%s」（当前 %s）"
                              % (cid, name, names))

    def test_units_have_stats(self):
        for cid in self.UNIT_CARDS:
            with self.subTest(card=cid):
                b, _ = _battle()
                _play(b, cid)
                m = b.player.minions[-1]
                self.assertGreater(m.hp, 0, "%s 单位血量为 0" % cid)
                self.assertGreater(m.attack, 0, "%s 单位攻击为 0" % cid)

    def test_units_attack_each_turn(self):
        """单位必须在回合结束时对敌人造成伤害。"""
        b, es = _battle()
        b.player.energy = 20
        _play(b, "deploy_tank")
        self.assertTrue(b.player.minions, "没召唤出单位")
        before = es[0].hp
        # 跑完玩家回合 + 敌人回合并回到玩家回合（单位在此期间开火）
        if hasattr(b, "end_turn"):
            b.end_turn()
        for _ in range(30):
            if not hasattr(b, "enemy_step") or not b.enemy_step():
                break
        self.assertLess(es[0].hp, before, "单位没有自动攻击")


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ==========================================================================
# 第四批：核爆终结技（用户反馈"打核爆最爽"）
# ==========================================================================

NUKE_CARDS = [
    "dig_in", "steady_advance", "prepare_offensive",
    "bunker_buster", "decisive_strike", "annihilation", "final_offensive",
    "nuke", "second_strike",
]


class TestNukeCards(unittest.TestCase):

    def test_all_present(self):
        for cid in NUKE_CARDS:
            with self.subTest(card=cid):
                self.assertIn(cid, C.CARD_DB)

    def test_all_playable(self):
        for cid in NUKE_CARDS:
            with self.subTest(card=cid):
                b, _ = _battle(n_enemies=3)
                b.player.energy = 30
                b.player.hand.clear()
                b.add_card_to_hand(cid, n=1)
                self.assertTrue(b.play_card(b.player.hand[-1],
                                            first_enemy(b)))

    def test_nuke_scales_with_strength(self):
        """核弹必须吃火力加成。"""
        def nuke_damage(prep_strength: int) -> int:
            b, es = _battle(n_enemies=3)
            if prep_strength:
                b.apply_buff(b.player, "strength", prep_strength)
            b.player.energy = 30
            b.player.hand.clear()
            b.add_card_to_hand("nuke", n=1)
            before = sum(e.hp for e in es)
            b.play_card(b.player.hand[-1], first_enemy(b))
            return before - sum(e.hp for e in es)

        self.assertGreater(nuke_damage(20), nuke_damage(0),
                           "核弹没有吃火力加成")

    def test_nuke_is_exhaust(self):
        """核弹是一次性的（消耗）。"""
        self.assertTrue(C.CARD_DB["nuke"].exhaust, "核弹不是消耗牌")

    def test_bunker_buster_scales_with_armor_break(self):
        def dmg(vuln: int) -> int:
            b, es = _battle()
            if vuln:
                b.apply_buff(es[0], "vulnerable", vuln)
            b.player.energy = 30
            b.player.hand.clear()
            b.add_card_to_hand("bunker_buster", n=1)
            before = es[0].hp
            b.play_card(b.player.hand[-1], es[0])
            return before - es[0].hp

        self.assertGreater(dmg(6), dmg(0), "要塞破坏者没有吃破甲加成")

    def test_decisive_strike_scales_with_strength(self):
        def dmg(s: int) -> int:
            b, es = _battle()
            if s:
                b.apply_buff(b.player, "strength", s)
            b.player.energy = 30
            b.player.hand.clear()
            b.add_card_to_hand("decisive_strike", n=1)
            before = es[0].hp
            b.play_card(b.player.hand[-1], es[0])
            return before - es[0].hp

        self.assertGreater(dmg(15), dmg(0), "决定性一击没有吃火力加成")

    def test_final_offensive_is_area(self):
        b, es = _battle(n_enemies=3)
        b.apply_buff(b.player, "strength", 10)
        b.player.energy = 30
        b.player.hand.clear()
        b.add_card_to_hand("final_offensive", n=1)
        b.play_card(b.player.hand[-1], first_enemy(b))
        for i, e in enumerate(es):
            with self.subTest(enemy=i):
                self.assertLess(e.hp, e.max_hp, "最后总攻漏了第 %d 个" % i)


class TestNukeCombo(unittest.TestCase):
    """完整核爆连招：攒 buff -> 一发入魂。"""

    def test_full_combo_deals_massive_damage(self):
        b, es = _battle(n_enemies=3, hp=9999)
        b.player.energy = 60
        combo = ["dig_in", "dig_in", "steady_advance", "steady_advance",
                 "prepare_offensive", "all_in", "arsenal_overload",
                 "mass_mobilize", "annihilation", "nuke"]
        total = 0
        for cid in combo:
            b.player.hand.clear()
            b.add_card_to_hand(cid, n=1)
            ci = b.player.hand[-1]
            if b.can_play(ci):
                before = sum(e.hp for e in es)
                b.play_card(ci, first_enemy(b))
                total += before - sum(e.hp for e in es)
        self.assertGreater(total, 300,
                           "整套核爆连招只打出 %d 伤害（预期 >300）" % total)


class TestVersusSymmetry(unittest.TestCase):
    """1v1 后手补偿：必须把先手优势压在 60% 以下。

    背景：新增卡牌把 0 费牌从 10 张涨到 20 张，先手方"白打一张"
    滚雪球更早，先手胜率一度冲到 62%。补偿从 +2 提到 +5 才压回来。
    """

    def test_first_player_advantage_is_bounded(self):
        """跑 450 场（3 组种子 x 150）汇总，压住抽样波动。

        单独用 200 场时波动能到 ±5 个百分点：单跑能过、全量跑偶发
        失败（真踩过 60.5%）。多组种子汇总才稳。
        """
        from core import deckbuild as DB
        from core import versus as V
        import random as _r

        def _play(deck, seed):
            bs = V.VersusBattle(list(deck), list(deck),
                                rng=_r.Random(seed), hp=75)
            g = 0
            while bs.result() == "ongoing" and g < 400:
                g += 1
                sd = bs.current_side()
                played = False
                for k in range(15):
                    try:
                        if bs.can_play(sd, k) and bs.play_card(sd, k):
                            played = True
                            break
                    except Exception:
                        break
                if not played:
                    if not bs.end_turn(sd):
                        break
                bs.tick(0.1)
            return bs.result()

        a = b = d = o = 0
        for seed in (1, 2, 3):
            deck = DB.random_deck(_r.Random(seed), 20)
            for i in range(150):
                r = _play(deck, i * 7 + seed)
                if r == "a_wins":
                    a += 1
                elif r == "b_wins":
                    b += 1
                elif r == "draw":
                    d += 1
                else:
                    o += 1

        rate = a / float(max(1, a + b + d))
        self.assertLessEqual(
            rate, 0.60,
            "先手胜率 %.1f%% 超过 60%%（后手补偿 FIRST_TURN_BONUS_SUPPLY "
            "可能需要调高）" % (rate * 100))
        self.assertEqual(o, 0, "有 %d 场未收敛" % o)

    def test_bonus_is_not_absurd(self):
        """补偿不能高到反过来压死后手 —— 保持个位数。"""
        from core import versus as V
        self.assertGreaterEqual(V.FIRST_TURN_BONUS_SUPPLY, 0)
        self.assertLessEqual(V.FIRST_TURN_BONUS_SUPPLY, 10)
