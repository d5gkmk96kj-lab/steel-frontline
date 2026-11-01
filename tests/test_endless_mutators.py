#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无尽模式的「战场态势」测试。

之前无尽模式只是难度 +18%/轮，玩法完全一样；现在每轮叠一条规则。
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import engine as EN    # noqa: E402
from core import run as R        # noqa: E402


class TestMutatorTable(unittest.TestCase):

    def test_loop_zero_has_none(self):
        self.assertEqual(R.mutators_for_loop(0), [])

    def test_every_loop_has_mutators(self):
        for n in range(1, 8):
            self.assertTrue(R.mutators_for_loop(n), "第 %d 轮没有态势" % n)

    def test_max_three_stacked(self):
        for n in range(1, 10):
            self.assertLessEqual(len(R.mutators_for_loop(n)), 3)

    def test_no_duplicates_within_loop(self):
        for n in range(1, 10):
            ids = [m["id"] for m in R.mutators_for_loop(n)]
            self.assertEqual(len(ids), len(set(ids)), "第 %d 轮态势重复" % n)

    def test_each_mutator_has_text(self):
        for m in R.LOOP_MUTATORS:
            self.assertTrue(m.get("id"))
            self.assertTrue(str(m.get("name", "")).strip())
            self.assertTrue(str(m.get("text", "")).strip())


class TestMutatorEffects(unittest.TestCase):

    def test_story_mode_unaffected(self):
        r = R.RunState(); r.new_run(seed=1, mode="story")
        self.assertEqual(r.loop_mutators(), [])
        self.assertAlmostEqual(r.difficulty_scale(), 1.0)

    def test_endless_scales_difficulty(self):
        r = R.RunState(); r.new_run(seed=1, mode="endless")
        base = r.difficulty_scale()
        r.loop = 3
        self.assertGreater(r.difficulty_scale(), base)

    def test_burning_ground_damages_at_start(self):
        """「焦土」：开局扣 8 血。"""
        r = R.RunState(); r.new_run(seed=5, mode="endless")
        r.loop = 2
        names = [m["id"] for m in r.loop_mutators()]
        self.assertIn("burning_ground", names)
        b = EN.make_battle(r, {"kind": "normal", "enemies": ["deep_crab"]})
        self.assertEqual(b.player.hp, b.player.max_hp - 8)

    def test_swarm_spawns_extra_enemy(self):
        r = R.RunState(); r.new_run(seed=5, mode="endless")
        r.loop = 3
        names = [m["id"] for m in r.loop_mutators()]
        self.assertIn("swarm", names)
        b = EN.make_battle(r, {"kind": "normal", "enemies": ["deep_crab"]})
        self.assertEqual(len(b.enemies), 2, "增援不断应该多一个敌人")

    def test_supply_short_and_swarm_net_out(self):
        """弹药 -1 与增援 +1 叠加后补给不变。"""
        r = R.RunState(); r.new_run(seed=5, mode="endless")
        r.loop = 3
        b = EN.make_battle(r, {"kind": "normal", "enemies": ["deep_crab"]})
        self.assertEqual(b.player.energy, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
