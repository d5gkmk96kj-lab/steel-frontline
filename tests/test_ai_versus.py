#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1v1 人机对战的 AI 测试。

这里的测试都在跑真实对局，所以刻意控制局数（每局约 7 步），
避免拖慢整个测试套件。
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

from core import ai as AI        # noqa: E402
from core import deckbuild as DB  # noqa: E402
from core import versus as V      # noqa: E402


def play_game(diff_a: str, diff_b: str, seed: int, max_steps: int = 600):
    """跑一整局，返回 (result, steps)。"""
    deck = DB.random_deck(random.Random(seed % 7 + 1), 20)
    bs = V.VersusBattle(list(deck), list(deck),
                        rng=random.Random(seed), hp=75)
    ais = {
        V.SIDE_A: AI.VersusAI(V.SIDE_A, rng=random.Random(seed * 3 + 1),
                              difficulty=diff_a),
        V.SIDE_B: AI.VersusAI(V.SIDE_B, rng=random.Random(seed * 3 + 2),
                              difficulty=diff_b),
    }
    g = 0
    while bs.result() == "ongoing" and g < max_steps:
        g += 1
        s = bs.current_side()
        for _ in range(40):
            try:
                if not ais[s].step(bs):
                    break
            except Exception:
                break
        try:
            bs.end_turn(s)
        except Exception:
            break
        bs.tick(0.05)
    return bs.result(), g


class TestAiBasics(unittest.TestCase):

    def test_module_imports(self):
        self.assertTrue(hasattr(AI, "VersusAI"))

    def test_three_difficulties(self):
        self.assertEqual(set(AI.DIFFICULTIES), {"easy", "normal", "hard"})

    def test_constructor_accepts_all_difficulties(self):
        for d in AI.DIFFICULTIES:
            with self.subTest(difficulty=d):
                ai = AI.VersusAI(V.SIDE_B, rng=random.Random(1), difficulty=d)
                self.assertIsNotNone(ai)

    def test_invalid_difficulty_falls_back(self):
        """非法难度不能抛异常（UI 传错值时也要能用）。"""
        ai = AI.VersusAI(V.SIDE_B, rng=random.Random(1), difficulty="nonsense")
        self.assertIsNotNone(ai)

    def test_has_step_and_take_turn(self):
        ai = AI.VersusAI(V.SIDE_B, rng=random.Random(1))
        self.assertTrue(callable(getattr(ai, "step", None)))
        self.assertTrue(callable(getattr(ai, "take_turn", None)))

    def test_no_pyqt_dependency(self):
        """core/ai.py 必须是纯逻辑模块，不能真的 import PyQt6。

        只检查 import 语句：文档里提到「本模块不依赖 PyQt6」是允许的。
        """
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "core", "ai.py"),
                   encoding="utf-8").read()
        imports = re.findall(r"^\s*(?:from|import)\s+([\w\.]+)", src, re.M)
        bad = [m for m in imports if m.startswith("PyQt")]
        self.assertEqual(bad, [],
                         "core/ai.py 真的 import 了 Qt：%s" % bad)


class TestAiConvergence(unittest.TestCase):

    def test_games_converge(self):
        """AI 必须能把对局打完，不能死循环。"""
        stuck = 0
        for i in range(30):
            r, g = play_game(("easy", "normal", "hard")[i % 3], "normal", i)
            if r == "ongoing":
                stuck += 1
        self.assertEqual(stuck, 0,
                         "有 %d/30 局未收敛（AI 可能死循环）" % stuck)

    def test_mirror_match_terminates(self):
        for d in AI.DIFFICULTIES:
            with self.subTest(difficulty=d):
                r, g = play_game(d, d, 7)
                self.assertNotEqual(r, "ongoing",
                                    "%s 镜像对局未收敛" % d)

    def test_step_returns_bool(self):
        """step() 必须返回 True/False，UI 靠它判断是否还要继续。"""
        deck = DB.random_deck(random.Random(1), 20)
        bs = V.VersusBattle(list(deck), list(deck), rng=random.Random(1), hp=75)
        ai = AI.VersusAI(V.SIDE_A, rng=random.Random(1), difficulty="normal")
        s = bs.current_side()
        if s == V.SIDE_A:
            got = ai.step(bs)
            self.assertIsInstance(got, bool)


class TestAiStrength(unittest.TestCase):
    """难度必须真的递进：easy 明显弱于 normal。"""

    def _winrate(self, diff: str, n: int = 60) -> float:
        w = 0
        dec = 0
        for i in range(n):
            r, _ = play_game(diff, "normal", i)
            if r == "a_wins":
                w += 1
                dec += 1
            elif r == "b_wins":
                dec += 1
        return w / float(dec or 1) * 100.0

    def test_easy_is_weaker_than_normal(self):
        easy = self._winrate("easy")
        normal = self._winrate("normal")
        self.assertLess(easy, normal,
                        "easy(%.1f%%) 应该明显弱于 normal(%.1f%%)"
                        % (easy, normal))

    def test_hard_is_not_weaker_than_normal(self):
        """hard 曾经因为"另起一套评分"反而比 normal 弱（39.5% vs 42.0%）。

        现在 hard 以 normal 为基线，必须至少不弱于 normal。
        容忍 6 个百分点（随机波动）。
        """
        normal = self._winrate("normal")
        hard = self._winrate("hard")
        self.assertGreaterEqual(
            hard + 6.0, normal,
            "hard(%.1f%%) 明显弱于 normal(%.1f%%) —— "
            "hard 的额外逻辑可能在拖后腿" % (hard, normal))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAiUiWiring(unittest.TestCase):
    """UI 接线：菜单按钮、难度下拉框、信号链路。

    这些测试曾经抓到一个真 bug：信号定义了但按钮没加上，
    __init__ 里 connect 直接 AttributeError，整个程序起不来。
    """

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("SF_ALLOW_HEADLESS_QT", "1")
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception:
            raise unittest.SkipTest("没有 PyQt6")
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        """建一个主窗口。

        注意：MainWindow.__init__ 会调用 _music_for() 去切换**全局** BGM
        状态（core.audio 是模块级单例）。不还原的话会污染同一个进程里
        后面跑的 test_audio（实测：单独跑 audio 全过，跑完这个文件再跑
        就挂）。所以这里登记到 addCleanup 里恢复。
        """
        # 先记下全局 BGM 播放器的状态，测完还原。
        # MainWindow._music_for() 会调 audio.on_screen()，那是**模块级单例**，
        # 会污染同进程后续的 test_audio。
        def _restore():
            try:
                from core import audio as _audio
                p = _audio.player()
                _audio.shutdown()
                # 停掉并恢复默认音量/开关，避免残留后台进程
                try:
                    p.set_enabled(False)
                except Exception:
                    pass
            except Exception:
                pass

        self.addCleanup(_restore)

        try:
            from qt.qapp import MainWindow
        except Exception as exc:
            self.skipTest("无法导入 MainWindow：%r" % (exc,))
        return MainWindow()

    def test_menu_has_ai_button(self):
        w = self._window()
        m = w.screens["menu"]
        self.assertTrue(hasattr(m, "open_ai_versus"),
                        "MenuScreen 缺少 open_ai_versus 信号")
        self.assertTrue(hasattr(m, "btn_ai"), "菜单上没有人机对战按钮")
        self.assertTrue(hasattr(m, "cb_ai"), "菜单上没有难度下拉框")

    def test_difficulty_options(self):
        w = self._window()
        cb = w.screens["menu"].cb_ai
        keys = [cb.itemData(i) for i in range(cb.count())]
        self.assertEqual(keys, ["easy", "normal", "hard"])

    def test_open_ai_versus_routes_to_deckbuild(self):
        w = self._window()
        w.open_ai_versus("hard")
        self.assertEqual(w._history[-1], "deckbuild",
                         "人机对战没有进入选卡界面")

    def test_confirming_deck_creates_ai(self):
        w = self._window()
        w.open_ai_versus("normal")
        db = w.screens["deckbuild"]
        ids = list(db.picked)
        self.assertTrue(ids, "选卡界面没有默认卡组")
        db.ai_confirmed.emit(ids, "normal")
        vs = w.screens["versus"]
        self.assertIsNotNone(getattr(vs, "_ai", None),
                             "确认卡组后没有创建 AI")

    def test_ai_actually_plays_a_turn(self):
        """AI 必须在真实对局里出牌并把回合交回来。"""
        w = self._window()
        w.open_ai_versus("normal")
        db = w.screens["deckbuild"]
        db.ai_confirmed.emit(list(db.picked), "normal")
        vs = w.screens["versus"]
        b = vs.battle
        self.assertIsNotNone(b, "没有创建对局")
        b.end_turn(0)                      # 我方结束，交给电脑
        self.assertEqual(b.current_side(), 1)
        hp0 = b.side(0).combatant.hp
        for _ in range(400):
            vs._step_ai()
            if b.current_side() == 0:
                break
        self.assertEqual(b.current_side(), 0,
                         "电脑没有把回合交回来")
        self.assertLess(b.side(0).combatant.hp, hp0,
                        "电脑一个回合一点伤害都没打出来")

    def test_net_mode_has_no_ai(self):
        """联机模式绝不能跑本地 AI（否则会抢对手的操作）。"""
        w = self._window()
        vs = w.screens["versus"]
        vs.start_net(object(), 0)
        self.assertIsNone(getattr(vs, "_ai", None),
                          "联机模式不该有本地 AI")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestStalemate(unittest.TestCase):
    """僵局判定：双方都打不死对方时不能永久卡住。

    真实场景：20 张「铁丝网反击」（riposte，基础伤害 0）互相对挠，
    双方 75/75 一动不动。修之前实测跑 150 回合仍是 ongoing，
    人机对战会永久卡死、玩家只能强退。
    """

    def test_max_turns_constant_exists(self):
        self.assertTrue(hasattr(V, "MAX_TURNS"), "缺少 MAX_TURNS 常量")
        self.assertGreater(V.MAX_TURNS, 10)
        self.assertLessEqual(V.MAX_TURNS, 200, "上限太高，玩家会干等")

    def test_degenerate_deck_terminates(self):
        """纯防御卡组必须能结束（判平局或按血量定胜负）。"""
        deck = ["riposte"] * 20
        bs = V.VersusBattle(list(deck), list(deck),
                            rng=random.Random(0), hp=75)
        g = 0
        while bs.result() == "ongoing" and g < 2000:
            g += 1
            s = bs.current_side()
            played = False
            for k in range(15):
                try:
                    if bs.can_play(s, k) and bs.play_card(s, k):
                        played = True
                        break
                except Exception:
                    break
            if not played:
                try:
                    if not bs.end_turn(s):
                        break
                except Exception:
                    break
            bs.tick(0.05)
        self.assertNotEqual(bs.result(), "ongoing",
                            "退化卡组跑 %d 步仍未结束（会卡死玩家）" % g)

    def test_turn_limit_is_draw_when_hp_equal(self):
        """双方血量相同时打满回合数应判平局。"""
        deck = ["riposte"] * 20
        bs = V.VersusBattle(list(deck), list(deck),
                            rng=random.Random(0), hp=75)
        bs.turn = int(V.MAX_TURNS)
        self.assertEqual(bs.result(), "draw",
                         "血量相同且打满回合数应判平局")

    def test_turn_limit_favors_higher_hp(self):
        deck = ["riposte"] * 20
        bs = V.VersusBattle(list(deck), list(deck),
                            rng=random.Random(0), hp=75)
        bs.turn = int(V.MAX_TURNS)
        bs.side(0).combatant.hp = 50
        bs.side(1).combatant.hp = 20
        self.assertEqual(bs.result(), "a_wins",
                         "打满回合数时血量高的一方应获胜")

    def test_normal_games_finish_well_before_limit(self):
        """正常卡组不该被回合上限误伤。"""
        for i in range(12):
            r, _ = play_game("normal", "normal", i)
            self.assertNotEqual(r, "ongoing")
            self.assertIn(r, ("a_wins", "b_wins", "draw"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
