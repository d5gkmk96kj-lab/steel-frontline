#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新手教程 + 结算界面动画回归测试。"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import tutorial as TU  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SF_NO_UPDATE_CHECK"] = "1"

try:
    from PyQt6.QtCore import Qt, QEvent, QEventLoop, QTimer
    from PyQt6.QtGui import QKeyEvent
    HAS_QT = True
except Exception:                                    # pragma: no cover
    HAS_QT = False


def _pump(ms=150):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _wait_for(widget, cls_name, timeout_ms=4000):
    """等界面真的切过去（淡入动画在慢机器上要走更久）。"""
    step = 50
    waited = 0
    while waited < timeout_ms:
        try:
            if widget.stack.currentWidget().__class__.__name__ == cls_name:
                return True
        except Exception:
            pass
        _pump(step)
        waited += step
    return False


class TestTutorialCoach(unittest.TestCase):
    """教程推进器（纯逻辑）。"""

    def test_steps_exist(self):
        self.assertGreaterEqual(len(TU.STEPS), 4, "教程步骤太少")

    def test_all_steps_have_text(self):
        for s in TU.STEPS:
            self.assertTrue(s.text.strip(), "%s 没有提示文字" % s.id)
            self.assertTrue(s.wait_for, "%s 没有触发事件" % s.id)

    def test_advances_in_order(self):
        c = TU.Coach()
        self.assertEqual(c.progress, "第 1 / 5 步")
        self.assertTrue(c.notify("play_attack"))
        self.assertEqual(c.index, 1)
        self.assertTrue(c.notify("play_skill"))
        self.assertTrue(c.notify("end_turn"))
        self.assertTrue(c.notify("enemy_acted"))
        self.assertTrue(c.notify("battle_end"))
        self.assertTrue(c.done)

    def test_wrong_event_does_not_advance(self):
        c = TU.Coach()
        self.assertFalse(c.notify("end_turn"), "错误事件不该推进")
        self.assertEqual(c.index, 0)

    def test_feedback_shows(self):
        c = TU.Coach()
        c.notify("play_attack")
        self.assertIn("补给", c.text, "完成后应该显示反馈")

    def test_advance_skips(self):
        c = TU.Coach()
        c.advance()
        self.assertEqual(c.index, 1)

    def test_reset(self):
        c = TU.Coach()
        c.notify("play_attack")
        c.reset()
        self.assertEqual(c.index, 0)
        self.assertFalse(c.done)

    def test_classify_card(self):
        self.assertEqual(TU.classify_card("attack"), "play_attack")
        self.assertEqual(TU.classify_card("skill"), "play_skill")
        self.assertEqual(TU.classify_card("power"), "play_skill")
        self.assertEqual(TU.classify_card(""), "play_other")

    def test_tutorial_scenario_sane(self):
        self.assertTrue(TU.TUTORIAL_DECK, "教程卡组不能为空")
        self.assertTrue(TU.TUTORIAL_ENCOUNTER.get("enemies"), "教程敌人不能为空")


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestGameOverAnimation(unittest.TestCase):
    """结算界面的旋转光芒必须真的在转（老 bug：只 update 标签不 update 背景）。"""

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def test_sun_rotates(self):
        from qt.qapp import MainWindow
        w = MainWindow(); w.resize(1100, 760); w.show(); _pump(300)
        try:
            go = w.screens["gameover"]
            paints = {"n": 0}
            orig = go.paintEvent

            def counting(ev):
                paints["n"] += 1
                return orig(ev)

            go.paintEvent = counting
            w.show_screen("gameover")
            self.assertTrue(_wait_for(w, "GameOverScreen"),
                            "界面没切到结算")
            _pump(400)
            self.assertTrue(go._t.isActive(), "结算界面的计时器没起来")
            p0, n0 = go._phase, paints["n"]
            _pump(900)
            self.assertNotEqual(go._phase, p0,
                                "旋转相位不动（太阳卡住了）")
            self.assertGreater(paints["n"] - n0, 5,
                               "背景没有重绘（只 update 了标签）")
        finally:
            w.close()

    def test_timer_stops_when_hidden(self):
        from qt.qapp import MainWindow
        w = MainWindow(); w.resize(1100, 760); w.show(); _pump(300)
        try:
            go = w.screens["gameover"]
            w.show_screen("gameover")
            self.assertTrue(_wait_for(w, "GameOverScreen"))
            _pump(300)
            self.assertTrue(go._t.isActive())
            w.show_screen("menu"); _pump(400)
            self.assertFalse(go._t.isActive(), "切走后应该停掉计时器")
        finally:
            w.close()


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestTutorialUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def test_tutorial_runs(self):
        from qt.qapp import MainWindow
        w = MainWindow(); w.resize(1280, 820); w.show(); _pump(300)
        try:
            w.start_tutorial()
            self.assertTrue(_wait_for(w, "BattleScreen"),
                            "教程没进到战斗界面")
            _pump(400)
            bs = w.screens["battle"]
            self.assertIsNotNone(bs._coach, "教程推进器没挂上")
            self.assertTrue(bs.coach_bar.isVisible(), "提示带没显示")
            self.assertGreaterEqual(bs.coach_bar.width(), 300,
                                    "提示带被压扁了")

            # 出攻击牌 -> 推进
            before = bs._coach.index
            for c in ((bs._snap or {}).get("hand") or []):
                if c.get("type") == "attack":
                    bs.play_card(c.get("uid"))
                    _pump(400)
                    break
            self.assertGreater(bs._coach.index, before, "出攻击牌没推进教程")
        finally:
            w.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
