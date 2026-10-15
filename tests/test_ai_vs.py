# -*- coding: utf-8 -*-
"""``core/ai.py``（1v1 对战 AI）的契约与收敛性测试。

覆盖：
* 构造签名 / 难度合法性 / 非法输入兜底
* ``take_turn`` 必定结束回合、``step`` 单步语义
* 三档难度都能正常打完一局（不抛异常）
* AI vs AI 自走收敛（含退化卡组的显式报告）
* 难度单调性：hard 对 easy 应该有优势（统计性，允许较大方差）
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load  # noqa: E402


def _make_battle(V, db, seed, size=24, arch=None):
    """构造一副对称卡组的对局。"""
    deck = db.random_deck(random.Random(seed), size, arch=arch)
    rng = random.Random(seed * 7 + 1)
    return V.VersusBattle(list(deck), list(deck), rng=rng, hp=75), rng


def _play_out(A, V, bs, ais, cap=400):
    """让对局跑到结束，返回 (result, steps)。"""
    g = 0
    while bs.result() == V.RESULT_ONGOING and g < cap:
        g += 1
        ais[bs.current_side()].take_turn(bs)
    return bs.result(), g


class TestAIContract(unittest.TestCase):

    def setUp(self):
        self.A, err = load("core.ai")
        if self.A is None:
            self.fail("core.ai 不可用：%s" % err)
        self.V, err2 = load("core.versus")
        if self.V is None:
            self.fail("core.versus 不可用：%s" % err2)
        self.db, err3 = load("core.deckbuild")
        if self.db is None:
            self.fail("core.deckbuild 不可用：%s" % err3)

    # -- 构造 ----------------------------------------------------------
    def test_constructor_signature(self):
        ai = self.A.VersusAI(1, random.Random(0), "hard")
        self.assertEqual(ai.side, 1)
        self.assertEqual(ai.difficulty, "hard")
        ai2 = self.A.VersusAI(side=0, difficulty="easy")
        self.assertEqual(ai2.side, 0)
        self.assertEqual(ai2.difficulty, "easy")

    def test_invalid_inputs_are_safe(self):
        """非法 side / difficulty 必须兜底，绝不抛异常。"""
        for bad_side in (None, "x", 5, -1, True, 2.5):
            ai = self.A.VersusAI(bad_side)
            self.assertIn(ai.side, (0, 1))
        ai = self.A.VersusAI(1, difficulty="impossible")
        self.assertIn(ai.difficulty, self.A.DIFFICULTIES)
        # rng 传非法值也要能自建
        ai2 = self.A.VersusAI(1, rng="not-a-rng")
        self.assertTrue(isinstance(ai2.rng, random.Random))

    def test_methods_exist(self):
        ai = self.A.VersusAI(1)
        self.assertTrue(callable(ai.take_turn))
        self.assertTrue(callable(ai.step))
        self.assertTrue(callable(ai.reset))

    # -- 对 None / 坏入参的鲁棒性 --------------------------------------
    def test_take_turn_none_is_safe(self):
        ai = self.A.VersusAI(1)
        self.assertEqual(ai.take_turn(None), 0)
        self.assertFalse(ai.step(None))

    def test_never_raises_on_garbage(self):
        """传入各种垃圾对象都不能抛异常。"""
        ai = self.A.VersusAI(1)
        for junk in (0, "", [], object(), {"x": 1}):
            try:
                ai.take_turn(junk)
                ai.step(junk)
            except Exception as exc:      # pragma: no cover
                self.fail("AI 对 %r 抛出了异常：%r" % (junk, exc))

    # -- 回合语义 ------------------------------------------------------
    def test_take_turn_ends_turn(self):
        """take_turn 结束后必须换手（除非对局已结束）。"""
        bs, _rng = _make_battle(self.V, self.db, 3)
        ai = self.A.VersusAI(bs.current_side(), difficulty="hard")
        before = bs.current_side()
        ai.take_turn(bs)
        if bs.result() == self.V.RESULT_ONGOING:
            self.assertNotEqual(bs.current_side(), before,
                                "take_turn 没有换手")

    def test_take_turn_returns_count(self):
        bs, _rng = _make_battle(self.V, self.db, 5)
        ai = self.A.VersusAI(bs.current_side(), difficulty="normal")
        n = ai.take_turn(bs)
        self.assertIsInstance(n, int)
        self.assertGreaterEqual(n, 0)

    def test_step_is_single_action(self):
        """step 每次最多做一件事；连续 step 最终会结束回合。"""
        bs, _rng = _make_battle(self.V, self.db, 8)
        side = bs.current_side()
        ai = self.A.VersusAI(side, difficulty="hard")
        guard = 0
        while bs.current_side() == side and \
                bs.result() == self.V.RESULT_ONGOING and guard < 100:
            guard += 1
            ai.step(bs)
        self.assertLess(guard, 100, "step 循环未能结束回合")
        if bs.result() == self.V.RESULT_ONGOING:
            self.assertNotEqual(bs.current_side(), side)

    def test_step_returns_false_when_not_my_turn(self):
        bs, _rng = _make_battle(self.V, self.db, 11)
        other = 1 - bs.current_side()
        ai = self.A.VersusAI(other)
        self.assertFalse(ai.step(bs), "不是自己回合时 step 应返回 False")

    # -- 难度行为 ------------------------------------------------------
    def test_all_difficulties_play(self):
        for diff in ("easy", "normal", "hard"):
            bs, _rng = _make_battle(self.V, self.db, 13)
            ai = self.A.VersusAI(bs.current_side(), difficulty=diff)
            ai.take_turn(bs)
            self.assertGreaterEqual(ai.cards_played, 0)

    def test_deterministic_with_seed(self):
        """同种子同难度应当完全可复现。"""
        results = []
        for _ in range(2):
            bs, rng = _make_battle(self.V, self.db, 21)
            ai = self.A.VersusAI(bs.current_side(), rng=random.Random(99),
                                 difficulty="hard")
            ai.take_turn(bs)
            results.append((ai.cards_played,
                            bs.side(0).combatant.hp, bs.side(1).combatant.hp))
        self.assertEqual(results[0], results[1], "同种子结果不一致")


class TestAIConvergence(unittest.TestCase):
    """AI vs AI 自走：必须能收敛（或明确报告退化卡组）。"""

    def setUp(self):
        self.A, err = load("core.ai")
        if self.A is None:
            self.fail("core.ai 不可用：%s" % err)
        self.V, _ = load("core.versus")
        self.db, _ = load("core.deckbuild")

    def test_100_games_converge(self):
        """100 局 hard vs hard，统计未收敛数量并 print 出来。"""
        nonconv = 0
        outcomes = {}
        for i in range(100):
            arch = (None, "attack", "block", "poison", "energy", "summon")[i % 6]
            deck = self.db.random_deck(random.Random(500 + i), 20 + (i % 21),
                                       arch=arch)
            rng = random.Random(i * 13 + 7)
            bs = self.V.VersusBattle(list(deck), list(deck), rng=rng, hp=75)
            ais = {0: self.A.VersusAI(0, rng=rng, difficulty="hard"),
                   1: self.A.VersusAI(1, rng=rng, difficulty="hard")}
            res, _steps = _play_out(self.A, self.V, bs, ais, cap=400)
            outcomes[res] = outcomes.get(res, 0) + 1
            if res == self.V.RESULT_ONGOING:
                nonconv += 1
        print("\n[core.ai] 100 局 hard vs hard：未收敛 %d 局；分布 %s"
              % (nonconv, outcomes))
        self.assertLessEqual(nonconv, 3,
                             "%d/100 局未收敛（AI 可能卡死循环）" % nonconv)

    def test_degenerate_deck_is_reported_not_hidden(self):
        """退化卡组（只有零伤害牌）必须**能结束**，而不是永久卡住。

        历史：这条测试原本断言 steps == cap（即"它本来就跑不完"），
        把引擎缺回合上限这件事当成了既定事实。后来发现这会让
        人机对战永久卡死（玩家只能强退），于是在 core/versus.py 里
        加了 MAX_TURNS 僵局判定。现在改为断言对局能正常收尾。

        riposte 基础伤害为 0（伤害等同铁丝网层数），单靠它赢不了，
        所以结果应该是 draw（或按血量判定的胜负），但绝不能是 ongoing。
        """
        from core import cards as C
        deck = ["riposte"] * 20
        self.assertEqual(C.CARD_DB["riposte"].damage, 0)
        rng = random.Random(1)
        bs = self.V.VersusBattle(list(deck), list(deck), rng=rng, hp=75)
        ais = {0: self.A.VersusAI(0, rng=rng, difficulty="hard"),
               1: self.A.VersusAI(1, rng=rng, difficulty="hard")}
        res, steps = _play_out(self.A, self.V, bs, ais, cap=120)
        print("\n[core.ai] 退化卡组（20x riposte）：result=%s steps=%d"
              % (res, steps))
        self.assertNotEqual(
            res, self.V.RESULT_ONGOING,
            "退化卡组跑了 %d 步仍是 ongoing —— 僵局判定没生效" % steps)
        self.assertLess(steps, 120,
                        "退化卡组不该跑满 %d 步（说明还在僵持）" % 120)

    def test_difficulty_ordering(self):
        """hard 对 easy 应当有优势（200 局统计）。"""
        wins = {"hard": 0, "easy": 0, "draw": 0}
        n = 200
        for i in range(n):
            deck = self.db.random_deck(random.Random(3000 + i), 24)
            rng = random.Random(i * 31 + 5)
            # 交替先后手，消除先后手偏差
            hard_side = i % 2
            bs = self.V.VersusBattle(list(deck), list(deck), rng=rng, hp=75)
            ais = {}
            for s in (0, 1):
                ais[s] = self.A.VersusAI(
                    s, rng=rng,
                    difficulty="hard" if s == hard_side else "easy")
            res, _ = _play_out(self.A, self.V, bs, ais, cap=400)
            if res == "draw" or res == self.V.RESULT_ONGOING:
                wins["draw"] += 1
            else:
                winner = 0 if res == self.V.RESULT_A_WINS else 1
                if winner == hard_side:
                    wins["hard"] += 1
                else:
                    wins["easy"] += 1
        print("\n[core.ai] 200 局 hard vs easy：hard 胜 %d (%.1f%%) | "
              "easy 胜 %d (%.1f%%) | 平/未收敛 %d"
              % (wins["hard"], wins["hard"] * 100.0 / n,
                 wins["easy"], wins["easy"] * 100.0 / n, wins["draw"]))
        self.assertGreater(wins["hard"], wins["easy"],
                           "hard 未能战胜 easy（hard=%d, easy=%d）"
                           % (wins["hard"], wins["easy"]))


class TestAIHelpers(unittest.TestCase):

    def setUp(self):
        self.A, err = load("core.ai")
        if self.A is None:
            self.fail("core.ai 不可用：%s" % err)
        self.V, _ = load("core.versus")
        self.db, _ = load("core.deckbuild")

    def test_play_ai_game(self):
        deck = self.db.random_deck(random.Random(4), 24)
        out = self.A.play_ai_game(deck, deck, "hard", "normal",
                                  rng=random.Random(2))
        for key in ("result", "winner_side", "turns", "cards_played",
                    "hp_a", "hp_b", "converged"):
            self.assertIn(key, out)
        self.assertIsInstance(out["converged"], bool)

    def test_play_ai_game_bad_deck_is_safe(self):
        """垃圾卡组不能让 play_ai_game 抛异常。"""
        out = self.A.play_ai_game([], [], "hard", "hard", rng=random.Random(1))
        self.assertIn("result", out)

    def test_auto_turn(self):
        deck = self.db.random_deck(random.Random(6), 24)
        rng = random.Random(3)
        bs = self.V.VersusBattle(list(deck), list(deck), rng=rng, hp=75)
        n = self.A.auto_turn(bs, difficulty="normal")
        self.assertIsInstance(n, int)

    def test_make_ai_seed(self):
        a = self.A.make_ai(1, "hard", seed=5)
        self.assertEqual(a.difficulty, "hard")
        self.assertEqual(a.side, 1)


if __name__ == "__main__":
    unittest.main()
