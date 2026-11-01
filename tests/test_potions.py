#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""药水系统回归测试。

背景：药水这一整套东西（10 种、商店能买、背包能存）之前**完全没实现使用入口** ——
玩家花钱买了永远用不掉。这组测试锁住「真的能用、真的生效、真的消耗」。
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import engine as EN          # noqa: E402
from core import events as EV          # noqa: E402
from core import run as R              # noqa: E402


def _battle(seed=1, potions=()):
    r = R.RunState()
    r.new_run(seed=seed)
    for p in potions:
        r.add_potion(p)
    b = EN.make_battle(r, {"kind": "normal", "enemies": ["deep_crab"]})
    return r, b


class TestPotionEffects(unittest.TestCase):

    def test_every_potion_has_effect(self):
        """10 种药水必须全都能用，且真的改变战斗状态。"""
        for pid in EV.POTION_DB:
            with self.subTest(pid=pid):
                r, b = _battle(potions=[pid])
                # 把状态调成「任何效果都会产生可见变化」
                b.player.hp = b.player.max_hp - 25
                b.player.energy = 0
                b.player.hand.clear()
                before = (
                    b.player.hp, b.player.block, b.player.energy,
                    len(b.player.hand),
                    b.enemies[0].hp,
                    b.enemies[0].get_buff("poison"),
                    b.enemies[0].get_buff("weak"),
                    b.enemies[0].get_buff("vulnerable"),
                    b.player.get_buff("strength"),
                    b.player.get_buff("artifact"),
                )
                self.assertTrue(b.use_potion(pid), "%s 应该能用" % pid)
                self.assertNotIn(pid, r.potions, "%s 用完应该从背包扣掉" % pid)
                after = (
                    b.player.hp, b.player.block, b.player.energy,
                    len(b.player.hand),
                    b.enemies[0].hp,
                    b.enemies[0].get_buff("poison"),
                    b.enemies[0].get_buff("weak"),
                    b.enemies[0].get_buff("vulnerable"),
                    b.player.get_buff("strength"),
                    b.player.get_buff("artifact"),
                )
                self.assertNotEqual(before, after, "%s 用了没有任何效果" % pid)

    def test_cannot_use_without_potion(self):
        _, b = _battle()
        self.assertFalse(b.use_potion("potion_heal"))

    def test_cannot_use_twice(self):
        r, b = _battle(potions=["potion_heal"])
        self.assertTrue(b.use_potion("potion_heal"))
        self.assertFalse(b.use_potion("potion_heal"), "同一瓶不能用两次")

    def test_cannot_use_on_enemy_turn(self):
        r, b = _battle(potions=["potion_block"])
        b.phase = "enemy"
        self.assertFalse(b.use_potion("potion_block"), "敌方回合不该能用")

    def test_unknown_potion_rejected(self):
        _, b = _battle(potions=["not_a_potion"])
        self.assertFalse(b.use_potion("not_a_potion"))

    def test_usable_potions_lists_inventory(self):
        r, b = _battle(potions=["potion_heal", "potion_bomb"])
        self.assertEqual(set(b.usable_potions()), {"potion_heal", "potion_bomb"})

    def test_potion_bomb_hits_all_enemies(self):
        r = R.RunState()
        r.new_run(seed=2)
        r.add_potion("potion_bomb")
        b = EN.make_battle(r, {"kind": "normal",
                               "enemies": ["deep_crab", "deep_crab"]})
        hps = [e.hp for e in b.enemies]
        b.use_potion("potion_bomb")
        for e, before in zip(b.enemies, hps):
            self.assertLess(e.hp, before, "炸弹应该打全体")

    def test_potion_poison_applies_burn(self):
        r, b = _battle(potions=["potion_poison"])
        b.use_potion("potion_poison")
        self.assertGreater(b.enemies[0].get_buff("poison"), 0)

    def test_inventory_cap_is_three(self):
        r = R.RunState()
        r.new_run(seed=3)
        for pid in list(EV.POTION_IDS)[:5]:
            r.add_potion(pid)
        self.assertLessEqual(len(r.potions), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
