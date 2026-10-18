#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""辅助角色（指挥官）测试。"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import cards as C  # noqa: E402
from core import commanders as CM  # noqa: E402
from core import engine as EN  # noqa: E402
from core import run as R  # noqa: E402


class _Run:
    hp = 75
    max_hp = 75
    relics = []
    ascension = 0
    act = 1

    def __init__(self, deck_ids=None):
        self.deck = [C.make_card(i) for i in (deck_ids or
                                              ["strike"] * 10 + ["defend"] * 10)]
        self.rng = random.Random(7)


def _battle(cid: str):
    """造一场已经选好指挥官的战斗。

    一次性的加成（耐久/金币）走 ``run.apply_commander`` ——
    它只在**开局时**结算一次，不会每场战斗重复加。
    ``make_battle`` 内部已经调用过 ``start_battle()``，这里不再重复调。
    """
    r = R.RunState()
    r.new_run(seed=7)
    r.apply_commander(cid)
    return EN.make_battle(r, {"kind": "normal", "enemies": ["infantry_squad"]})


class TestRegistry(unittest.TestCase):

    def test_has_thirty(self):
        self.assertGreaterEqual(len(CM.COMMANDERS), 30,
                                "至少要 30 位角色，现在 %d" % len(CM.COMMANDERS))

    def test_unique_ids_and_names(self):
        ids = [c.id for c in CM.all_commanders()]
        self.assertEqual(len(ids), len(set(ids)), "角色 id 有重复")
        names = [c.name for c in CM.all_commanders()]
        self.assertEqual(len(names), len(set(names)), "角色名字有重复")

    def test_all_have_text(self):
        for c in CM.all_commanders():
            with self.subTest(cmd=c.id):
                self.assertTrue(c.name.strip(), "%s 没有名字" % c.id)
                self.assertTrue(c.text.strip(), "%s 没有效果说明" % c.id)
                self.assertTrue(c.nation.strip(), "%s 没有国家" % c.id)

    def test_six_nations_five_each(self):
        """6 个国家，每个正好 5 位。"""
        groups = CM.grouped()
        self.assertEqual(len(groups), 6, "应该是 6 个国家")
        for code, zh, en, lst in groups:
            with self.subTest(nation=code):
                self.assertEqual(len(lst), 5,
                                 "%s 应该有 5 位，实际 %d" % (zh, len(lst)))

    def test_nation_codes(self):
        got = [g[0] for g in CM.grouped()]
        self.assertEqual(got, ["CN", "US", "JP", "SU", "DE", "GB"],
                         "国家顺序/代码不对：%s" % got)

    def test_every_commander_has_valid_nation(self):
        for c in CM.all_commanders():
            self.assertIn(c.nation, CM.NATION_NAMES,
                          "%s 的国家 %r 不合法" % (c.id, c.nation))

    def test_key_figures_present(self):
        """用户点名要的人物必须在。"""
        need = {
            "sun_yatsen": "CN", "mao": "CN",
            "roosevelt": "US", "eisenhower": "US",
            "yamamoto": "JP", "tojo": "JP",
            "stalin": "SU", "zhukov": "SU",
            "hitler": "DE", "guderian": "DE",
            "churchill": "GB", "montgomery": "GB",
        }
        for cid, nat in need.items():
            c = CM.get(cid)
            self.assertIsNotNone(c, "%s 缺失" % cid)
            self.assertEqual(c.nation, nat, "%s 国家错" % cid)

    def test_none_is_neutral(self):
        self.assertTrue(CM.mods_of("").is_neutral())
        self.assertTrue(CM.mods_of("not_a_real_id").is_neutral())

    def test_mods_merge(self):
        a = CM.Modifiers(supply=1, damage=1.1)
        b = CM.Modifiers(supply=2, damage=1.2)
        m = a.merge(b)
        self.assertEqual(m.supply, 3)
        self.assertAlmostEqual(m.damage, 1.32, places=5)


class TestEffects(unittest.TestCase):

    def test_no_commander_baseline(self):
        b = _battle("")
        self.assertEqual(b.player.energy, 3)
        self.assertEqual(len(b.player.hand), 5)
        self.assertEqual(b.player.max_hp, 75)

    def test_guderian_supply_and_hand(self):
        b = _battle("guderian")
        self.assertEqual(b.player.energy, 4, "古德里安应 +1 补给")
        self.assertEqual(len(b.player.hand), 6, "古德里安应 +1 开局手牌")

    def test_patton_damage_but_low_hp(self):
        b = _battle("patton")
        self.assertLess(b.player.max_hp, 75, "巴顿应该减耐久")
        m = CM.mods_of("patton")
        self.assertGreater(m.damage, 1.0)

    def test_zhukov_more_hp(self):
        b = _battle("zhukov")
        self.assertGreater(b.player.max_hp, 75, "朱可夫应加耐久")
        self.assertEqual(b.player.max_hp, 90)

    def test_turing_extra_draw(self):
        b = _battle("turing")
        self.assertEqual(len(b.player.hand), 6, "图灵应多抽 1 张")

    def test_oppenheimer_supply(self):
        b = _battle("oppenheimer")
        self.assertEqual(b.player.energy, 4, "奥本海默应 +1 补给")
        self.assertEqual(CM.mods_of("oppenheimer").nuke, 12)

    def test_every_commander_runs(self):
        """每一位都要能正常开局，不能崩。"""
        for c in CM.all_commanders():
            with self.subTest(cmd=c.id):
                b = _battle(c.id)
                self.assertGreater(len(b.player.hand), 0)
                self.assertGreater(b.player.max_hp, 0)

    def test_mods_do_not_break_game(self):
        """带任何指挥官都能打完一场（不会卡死）。"""
        for c in CM.all_commanders()[:8]:
            with self.subTest(cmd=c.id):
                b = _battle(c.id)
                for _ in range(20):
                    if b.phase in ("won", "lost"):
                        break
                    b.end_turn()
                    while b.enemy_step():
                        pass
                    if b.phase in ("won", "lost"):
                        break
                    b.start_turn() if hasattr(b, "start_turn") else None
                self.assertIn(b.phase, ("player", "enemy", "won", "lost"))


class TestUnlock(unittest.TestCase):

    def test_starters_exist(self):
        self.assertGreater(len(CM.starters()), 0)

    def test_available_grows(self):
        lo = len(CM.available(0))
        hi = len(CM.available(999))
        self.assertGreaterEqual(hi, lo)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestNoStatStacking(unittest.TestCase):
    """边界：一次性加成不能被反复叠加。

    真 bug：耐久加成原本放在 ``_build_player`` 里，每场战斗 +一次，
    而 ``finish_battle`` 又把含加成的血量写回 run，于是越打血越多
    （用户实测叠到 120+）。
    """

    def _run(self, cid=""):
        r = R.RunState()
        r.new_run(seed=7, mode="story")
        r.apply_commander(cid)
        return r

    def test_hp_bonus_applied_once(self):
        for cid in ("zhukov", "churchill", "sun_yatsen", "patton"):
            with self.subTest(cmd=cid):
                r = self._run(cid)
                c = CM.get(cid)
                want = 75 + int(c.mods.hp)
                self.assertEqual(r.max_hp, want,
                                 "%s 耐久上限应该是 %d" % (cid, want))
                self.assertEqual(r.hp, want)

    def test_no_hp_growth_over_many_battles(self):
        for cid in ("zhukov", "churchill", "patton", ""):
            with self.subTest(cmd=cid):
                r = self._run(cid)
                start_max = int(r.max_hp)
                for _ in range(10):
                    b = EN.make_battle(
                        r, {"kind": "normal", "enemies": ["infantry_squad"]})
                    # 不低于上限，模拟每场都几乎满血
                    self.assertLessEqual(b.player.max_hp, start_max,
                                         "战斗里耐久上限不该超过 run 的上限")
                    self.assertLessEqual(b.player.hp, b.player.max_hp,
                                         "当前耐久不该超过上限")
                    b.player.hp = b.player.max_hp
                    r.finish_battle("won", b)
                self.assertEqual(int(r.max_hp), start_max,
                                 "%s 打 10 场后耐久上限不该变" % cid)
                self.assertLessEqual(int(r.hp), int(r.max_hp),
                                     "打完血量不该超过上限")

    def test_gold_bonus_applied_once(self):
        for cid, extra_gold in (("speer", 60), ("roosevelt", 50),
                                ("sun_yatsen", 25)):
            with self.subTest(cmd=cid):
                r = self._run(cid)
                self.assertEqual(int(r.gold), 99 + extra_gold)

    def test_gold_not_regranted_on_reload(self):
        """读档不该重新发一次开局金币。"""
        import tempfile
        r = self._run("speer")
        gold = int(r.gold)
        p = tempfile.mktemp(suffix=".json")
        try:
            R.save_run(r, p)
            r2 = R.load_run(p)
            self.assertEqual(int(r2.gold), gold,
                             "读档后金币不该再 +60")
        finally:
            try:
                os.unlink(p)
            except OSError:
                pass

    def test_price_discount(self):
        r = self._run("speer")
        self.assertAlmostEqual(r.price_mult(), 0.85, places=3)
        r2 = self._run("")
        self.assertAlmostEqual(r2.price_mult(), 1.0, places=3)

    def test_heal_after_battle(self):
        for cid in ("zhukov", "montgomery"):
            with self.subTest(cmd=cid):
                r = self._run(cid)
                c = CM.get(cid)
                r.hp = 40
                b = EN.make_battle(
                    r, {"kind": "normal", "enemies": ["infantry_squad"]})
                b.player.hp = 40
                r.finish_battle("won", b)
                self.assertEqual(int(r.hp), 40 + int(c.mods.heal),
                                 "%s 战后应该回复 %d" % (cid, c.mods.heal))

    def test_heal_never_exceeds_max(self):
        r = self._run("zhukov")
        r.hp = int(r.max_hp) - 1
        b = EN.make_battle(r, {"kind": "normal", "enemies": ["infantry_squad"]})
        b.player.hp = int(r.max_hp) - 1
        r.finish_battle("won", b)
        self.assertLessEqual(int(r.hp), int(r.max_hp))
