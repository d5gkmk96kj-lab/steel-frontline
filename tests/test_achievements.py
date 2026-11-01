#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成就系统回归测试。

之前有 8 个成就**只声明了描述，代码里没有任何解锁点** —— 永远拿不到：
block_50 / comeback / no_damage / overkill / pacifist /
perfect_act / strength_30 / true_ending
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import engine as EN    # noqa: E402
from core import run as R        # noqa: E402


def _battle(seed=1):
    r = R.RunState()
    r.new_run(seed=seed)
    return r, EN.make_battle(r, {"kind": "normal", "enemies": ["deep_crab"]})


class TestAllAchievementsEarnable(unittest.TestCase):

    def test_every_achievement_has_a_source(self):
        """每个成就都必须有解锁路径（这条防的是「死内容」）。"""
        import re
        import glob
        used = set()
        for f in glob.glob(os.path.join(ROOT, "core", "*.py")):
            src = open(f, encoding="utf-8").read()
            for m in re.finditer(r'\._ach\(\s*\w+\s*,\s*"([a-z0-9_]+)"', src):
                used.add(m.group(1))
            for m in re.finditer(r'out\.append\("([a-z0-9_]+)"\)', src):
                used.add(m.group(1))
        used.add("true_ending")       # 由 _check_true_ending 解锁
        dead = set(R.ACHIEVEMENTS) - used
        self.assertEqual(dead, set(), "这些成就永远解锁不了：%s" % sorted(dead))


class TestBattleAchievements(unittest.TestCase):

    def test_overkill(self):
        _, b = _battle()
        b.max_hit_damage = 50
        self.assertIn("overkill", b.battle_achievements(True))

    def test_block_50(self):
        _, b = _battle()
        b.max_block_this_turn = 50
        self.assertIn("block_50", b.battle_achievements(True))

    def test_strength_30(self):
        _, b = _battle()
        b.max_strength = 30
        self.assertIn("strength_30", b.battle_achievements(True))

    def test_comeback(self):
        _, b = _battle()
        b.player.hp = 5
        self.assertIn("comeback", b.battle_achievements(True))
        b.player.hp = 6
        self.assertNotIn("comeback", b.battle_achievements(True))

    def test_no_damage(self):
        _, b = _battle()
        b.damage_taken = 0
        self.assertIn("no_damage", b.battle_achievements(True))

    def test_pacifist(self):
        _, b = _battle()
        b.attack_cards_played = 0
        b.cards_played_total = 3
        self.assertIn("pacifist", b.battle_achievements(True))

    def test_pacifist_needs_playing_something(self):
        """一张牌都没出不能算「和平主义者」。"""
        _, b = _battle()
        b.attack_cards_played = 0
        b.cards_played_total = 0
        self.assertNotIn("pacifist", b.battle_achievements(True))

    def test_no_achievements_on_loss(self):
        """输了不该拿「获胜类」成就。"""
        _, b = _battle()
        b.player.hp = 3
        b.damage_taken = 0
        got = b.battle_achievements(False)
        self.assertNotIn("comeback", got)
        self.assertNotIn("no_damage", got)

    def test_stats_accumulate(self):
        """真实打一场：统计字段应该被填上。"""
        _, b = _battle()
        for _ in range(40):
            if b.phase in ("won", "lost"):
                break
            if b.player.hand:
                b.play_card(b.player.hand[0])
            b.end_turn()
            while b.enemy_step():
                pass
            if b.phase in ("won", "lost"):
                break
            if hasattr(b, "start_turn"):
                b.start_turn()
        # 只要打过牌，攻击牌计数或总出牌数应该有值
        self.assertGreaterEqual(b.cards_played_total, 1)


class TestPerfectActAndTrueEnding(unittest.TestCase):

    def test_perfect_act(self):
        r = R.RunState(); r.new_run(seed=1)
        r.stats["perfect_acts"] = 1
        m = R.MetaProgress()
        m.record_run(r, won=True)
        self.assertTrue(m.achievements.get("perfect_act"))

    def test_true_ending_when_all_else_done(self):
        m = R.MetaProgress()
        for k in R.ACHIEVEMENTS:
            if k != "true_ending":
                m.achievements[k] = True
        acc = []
        m._ach(acc, "true_ending")
        self.assertTrue(m.achievements.get("true_ending"))

    def test_true_ending_not_when_missing(self):
        m = R.MetaProgress()
        m.achievements["first_win"] = True
        acc = []
        m._ach(acc, "first_blood")
        self.assertFalse(m.achievements.get("true_ending"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
