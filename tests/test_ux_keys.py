#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体验优化回归测试：快捷键 / 新手提示 / 字号缩放。"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SF_NO_UPDATE_CHECK"] = "1"

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import Qt, QEvent, QEventLoop, QTimer
    HAS_QT = True
except Exception:                                    # pragma: no cover
    HAS_QT = False


def _pump(ms=120):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestKeyboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def _win(self):
        from qt.qapp import MainWindow
        w = MainWindow()
        w.resize(1280, 800)
        w.show()
        _pump(260)
        return w

    @staticmethod
    def _press(widget, key, mods=Qt.KeyboardModifier.NoModifier):
        widget.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, key, mods))
        _pump(260)

    def test_f11_toggles_fullscreen(self):
        w = self._win()
        try:
            before = w.isFullScreen()
            self._press(w, Qt.Key.Key_F11)
            self.assertNotEqual(w.isFullScreen(), before, "F11 没切换全屏")
            self._press(w, Qt.Key.Key_F11)
            self.assertEqual(w.isFullScreen(), before, "再按 F11 没切回来")
        finally:
            w.close()

    def test_esc_returns_from_readonly_screen(self):
        w = self._win()
        try:
            w.show_screen("codex"); _pump(300)
            self.assertEqual(w.stack.currentWidget().__class__.__name__,
                             "CodexScreen")
            self._press(w, Qt.Key.Key_Escape)
            self.assertNotEqual(w.stack.currentWidget().__class__.__name__,
                                "CodexScreen", "Esc 没返回")
        finally:
            w.close()

    def test_menu_number_keys(self):
        w = self._win()
        try:
            m = w.screens["menu"]
            self._press(m, Qt.Key.Key_3)
            self.assertEqual(w.stack.currentWidget().__class__.__name__,
                             "SaveScreen", "主菜单按 3 没进存档管理")
        finally:
            w.close()

    def test_battle_space_ends_turn(self):
        w = self._win()
        try:
            w.start_run_direct(0, 42, "guderian", "story")
            _pump(400)
            # 跳过剧情
            scr = w.screens["story"]
            for _ in range(40):
                if scr.btn_next.isVisible():
                    scr.btn_next.click(); _pump(25)
                else:
                    break
            btns = scr._choice_buttons()
            if btns:
                btns[0].click(); _pump(350)
            w.start_battle(
                {"kind": "normal", "enemies": ["infantry_squad"], "name": "t"})
            _pump(500)
            bs = w.screens["battle"]
            self.assertIsNotNone(bs.battle)
            turn0 = bs.battle.turn
            bs.hide_tips()
            # 结束回合是异步的（敌人行动由 QTimer 逐个推进），
            # 按下去之后 phase 应该立刻变成 enemy
            self._press(bs, Qt.Key.Key_Space)
            phase = bs.battle.phase
            if phase == "player":
                # 也可能 400ms 内已经走完敌人回合、回到我方
                _pump(1200)
                self.assertGreater(bs.battle.turn, turn0, "空格没结束回合")
            else:
                self.assertEqual(phase, "enemy", "空格后相位不对")
        finally:
            w.close()

    def test_battle_number_plays_card(self):
        w = self._win()
        try:
            w.start_run_direct(0, 7, "guderian", "story")
            _pump(400)
            scr = w.screens["story"]
            for _ in range(40):
                if scr.btn_next.isVisible():
                    scr.btn_next.click(); _pump(25)
                else:
                    break
            btns = scr._choice_buttons()
            if btns:
                btns[0].click(); _pump(350)
            w.start_battle(
                {"kind": "normal", "enemies": ["infantry_squad"], "name": "t"})
            _pump(500)
            bs = w.screens["battle"]
            bs.hide_tips()
            hand0 = len((bs._snap or {}).get("hand") or [])
            if hand0 == 0:
                self.skipTest("没有手牌")
            self._press(bs, Qt.Key.Key_1)
            hand1 = len((bs._snap or {}).get("hand") or [])
            self.assertLess(hand1, hand0, "按 1 没出牌")
        finally:
            w.close()


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestFirstBattleTips(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def test_tips_show_once(self):
        from qt.qapp import MainWindow
        w = MainWindow(); w.resize(1280, 800); w.show(); _pump(260)
        try:
            w.meta.seen_battle_tips = False
            w.start_run_direct(0, 42, "guderian", "story"); _pump(400)
            scr = w.screens["story"]
            for _ in range(40):
                if scr.btn_next.isVisible():
                    scr.btn_next.click(); _pump(25)
                else:
                    break
            btns = scr._choice_buttons()
            if btns:
                btns[0].click(); _pump(350)
            w.start_battle(
                {"kind": "normal", "enemies": ["infantry_squad"], "name": "t"})
            _pump(700)
            bs = w.screens["battle"]
            self.assertTrue(bs.tips.isVisible(), "第一次进战斗没弹提示")
            # 提示层必须铺满（否则会挤在左上角）
            self.assertGreaterEqual(bs.tips.width(), bs.width() - 10,
                                    "提示层没铺满界面")
            self.assertTrue(w.meta.seen_battle_tips)
            bs.hide_tips(); _pump(100)
            w.start_battle(
                {"kind": "normal", "enemies": ["infantry_squad"], "name": "t"})
            _pump(600)
            self.assertFalse(bs.tips.isVisible(), "第二次不该再弹提示")
        finally:
            w.close()


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestFontScale(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def tearDown(self):
        from qt import qtheme as T
        T.set_ui_scale(1.0)

    def test_set_ui_scale_changes_sizes(self):
        from qt import qtheme as T
        T.set_ui_scale(1.0)
        base = T.FONT_BODY
        T.set_ui_scale(1.3)
        self.assertGreater(T.FONT_BODY, base, "放大后字号没变")
        T.set_ui_scale(1.0)
        self.assertEqual(T.FONT_BODY, base)

    def test_scale_clamped(self):
        from qt import qtheme as T
        self.assertAlmostEqual(T.set_ui_scale(99), 1.5, places=2)
        self.assertAlmostEqual(T.set_ui_scale(-5), 0.8, places=2)
        T.set_ui_scale(1.0)

    def test_font_uses_scale(self):
        from qt import qtheme as T
        T.set_ui_scale(1.0)
        base = T.font(15).pixelSize()
        T.set_ui_scale(1.2)
        self.assertGreater(T.font(15).pixelSize(), base)


if __name__ == "__main__":
    unittest.main(verbosity=2)
