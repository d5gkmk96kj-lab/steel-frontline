#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt6 主窗口信号接线测试。

防止「按钮全失灵」这类问题回归 —— 曾经因为 __init__ 的收尾逻辑被
误并入 rebuild_screens()，导致 _wire() 从未被调用，菜单上所有按钮失效。

需要离屏 Qt；没有 Qt 时整组跳过。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 允许在无头环境创建 QApplication（与 test_smoke_ui 同一开关）
os.environ.setdefault("SF_ALLOW_HEADLESS_QT", "1")


def _qt_ok():
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_qt_ok(), "PyQt6 不可用")
class TestMainWindowWiring(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import qt.qtheme as T
        T.install_i18n_patch()

    def _make(self):
        from qt.qapp import MainWindow
        import qt.qtheme as T
        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        return w

    def _pump(self, ms=250):
        from PyQt6.QtCore import QEventLoop, QTimer
        l = QEventLoop()
        QTimer.singleShot(ms, l.quit)
        l.exec()

    def test_wire_is_called_on_init(self):
        """__init__ 必须调用 _wire()，否则所有按钮都是死的。"""
        import qt.qapp as Q
        calls = []
        orig = Q.MainWindow._wire

        def traced(self):
            calls.append(1)
            return orig(self)

        Q.MainWindow._wire = traced
        try:
            w = self._make()
        finally:
            Q.MainWindow._wire = orig
        self.assertTrue(calls, "MainWindow 初始化时没有调用 _wire()")
        w.close()

    def test_console_and_f1_exist(self):
        """控制台与 F1 快捷键必须在初始化时建好。"""
        w = self._make()
        self.assertIsNotNone(getattr(w, "console", None),
                             "控制台没有创建")
        self.assertIsNotNone(getattr(w, "_f1", None),
                             "F1 快捷键没有绑定")
        w.close()

    def test_start_button_enters_map(self):
        """点「开始新战役」应离开菜单（核心回归点）。"""
        w = self._make()
        self._pump(400)
        m = w.screens["menu"]
        m.btn_new.click()
        self._pump(500)
        cur = w.stack.currentWidget().__class__.__name__
        self.assertNotEqual(cur, "MenuScreen",
                            "点了开始战役仍停在菜单 —— 信号没接上")
        w.close()

    def test_difficulty_then_start(self):
        """改难度后仍能开始（用户实际报告的场景）。"""
        w = self._make()
        self._pump(400)
        m = w.screens["menu"]
        m.spin_asc.setValue(5)
        self._pump(200)
        m.btn_new.click()
        self._pump(500)
        self.assertNotEqual(w.stack.currentWidget().__class__.__name__,
                            "MenuScreen")
        self.assertIsNotNone(w.run)
        w.close()

    def test_rebuild_screens_rewires(self):
        """语言切换重建界面后，按钮必须仍然可用。"""
        w = self._make()
        self._pump(400)
        w.rebuild_screens()
        self._pump(500)
        m = w.screens["menu"]
        m.btn_new.click()
        self._pump(500)
        self.assertNotEqual(w.stack.currentWidget().__class__.__name__,
                            "MenuScreen",
                            "重建界面后按钮失灵 —— _wire() 没重新调用")
        w.close()

    def test_rebuild_keeps_console(self):
        w = self._make()
        self._pump(300)
        w.rebuild_screens()
        self._pump(400)
        self.assertIsNotNone(getattr(w, "console", None))
        w.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)


@unittest.skipUnless(_qt_ok(), "PyQt6 不可用")
class TestSaveScreenWiring(unittest.TestCase):
    """存档界面接线：卡片按钮必须真的能触发。"""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import qt.qtheme as T
        T.install_i18n_patch()

    def setUp(self):
        import tempfile
        import shutil
        from core import run as run_mod
        self.tmp = tempfile.mkdtemp(prefix="sf_qsave_")
        self._old = (run_mod.DATA_DIR, run_mod.SAVE_PATH)
        run_mod.DATA_DIR = self.tmp
        run_mod.SAVE_PATH = os.path.join(self.tmp, "save.json")

    def tearDown(self):
        import shutil
        from core import run as run_mod
        run_mod.DATA_DIR, run_mod.SAVE_PATH = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pump(self, ms=200):
        from PyQt6.QtCore import QEventLoop, QTimer
        l = QEventLoop()
        QTimer.singleShot(ms, l.quit)
        l.exec()

    def test_screen_exists_and_lists_saves(self):
        from core import run as run_mod, saves as sv
        from qt.qapp import MainWindow
        import qt.qtheme as T
        r = run_mod.RunState()
        r.new_run(seed=5)
        r.hp = 42
        sv.save_new(r, "测试存档")

        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        self._pump(300)
        w.show_screen("saves")
        w.screens["saves"].refresh()
        self._pump(300)
        cards = [c for c in w.screens["saves"]._cards
                 if hasattr(c, "slot_id")]
        self.assertEqual(len(cards), 1)
        w.close()

    def test_load_button_enters_game(self):
        """点卡片上的「读取」应进入地图（回归：曾把信号当函数调用）。"""
        from PyQt6.QtWidgets import QPushButton
        from core import run as run_mod, saves as sv
        from qt.qapp import MainWindow
        import qt.qtheme as T
        r = run_mod.RunState()
        r.new_run(seed=6)
        r.hp = 39
        sv.save_new(r, "要读的")

        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        self._pump(300)
        w.show_screen("saves")
        w.screens["saves"].refresh()
        self._pump(300)
        card = [c for c in w.screens["saves"]._cards
                if hasattr(c, "slot_id")][0]
        for b in card.findChildren(QPushButton):
            if b.text() == "读取":
                b.click()
                break
        self._pump(500)
        self.assertNotEqual(w.stack.currentWidget().__class__.__name__,
                            "SaveScreen", "点读取后没有离开存档界面")
        self.assertIsNotNone(w.run)
        self.assertEqual(w.run.hp, 39)
        w.close()

    def test_settings_save_persists_run(self):
        """「保存并关闭」必须真的保存战役（用户报告的 bug）。"""
        import json
        from PyQt6.QtWidgets import QPushButton
        from core import run as run_mod
        from qt.qapp import MainWindow
        import qt.qtheme as T
        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        self._pump(300)
        w.start_new_run(0, None)
        self._pump(300)
        w.run.hp = 77
        w.show_screen("settings")
        self._pump(300)
        for b in w.screens["settings"].findChildren(QPushButton):
            if "保存并关闭" in b.text().replace(" ", ""):
                b.click()
                break
        self._pump(500)
        with open(run_mod.SAVE_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved.get("hp"), 77,
                         "设置界面没有保存战役进度")
        w.close()


@unittest.skipUnless(_qt_ok(), "PyQt6 不可用")
class TestConsoleKillWin(unittest.TestCase):
    """控制台 kill / win 必须真的结束战斗。

    回归：过去只调引擎的 _check_end()，界面层不知情，
    画面卡在战斗里什么键都按不动（用户实际报告）。
    """

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import qt.qtheme as T
        T.install_i18n_patch()

    def _pump(self, ms=200):
        from PyQt6.QtCore import QEventLoop, QTimer
        l = QEventLoop()
        QTimer.singleShot(ms, l.quit)
        l.exec()

    def _battle_window(self):
        from qt.qapp import MainWindow
        import qt.qtheme as T
        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        self._pump(300)
        w.start_new_run(0, None)
        self._pump(250)
        w.start_battle({"kind": "normal",
                        "enemies": ["infantry_squad"], "name": "t"})
        self._pump(500)
        return w

    def _run_cmd(self, w, cmd):
        w.console._run(cmd)
        self._pump(1600)

    def test_kill_leaves_battle(self):
        w = self._battle_window()
        self.assertEqual(w.stack.currentWidget().__class__.__name__,
                         "BattleScreen", "没能进入战斗，测试前提不成立")
        self._run_cmd(w, "kill")
        cur = w.stack.currentWidget().__class__.__name__
        self.assertNotEqual(cur, "BattleScreen",
                            "kill 之后仍卡在战斗界面")
        self.assertTrue(all(e.hp <= 0 for e in (w.battle.enemies or []))
                        if w.battle else True)
        w.close()

    def test_win_leaves_battle(self):
        w = self._battle_window()
        self._run_cmd(w, "win")
        cur = w.stack.currentWidget().__class__.__name__
        self.assertNotEqual(cur, "BattleScreen",
                            "win 之后仍卡在战斗界面")
        w.close()

    def test_kill_outside_battle_says_so(self):
        """不在战斗中时只提示，不崩。"""
        from qt.qapp import MainWindow
        import qt.qtheme as T
        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        self._pump(300)
        w.console._run("kill")      # 不应抛异常
        self._pump(200)
        w.close()


@unittest.skipUnless(_qt_ok(), "PyQt6 不可用")
class TestCheatEndsBattleUi(unittest.TestCase):
    """兑换码结束战斗后，界面也必须跟着走（与 kill/win 同一类 bug）。"""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import qt.qtheme as T
        T.install_i18n_patch()

    def _pump(self, ms=200):
        from PyQt6.QtCore import QEventLoop, QTimer
        l = QEventLoop()
        QTimer.singleShot(ms, l.quit)
        l.exec()

    def test_annex_all_leaves_battle(self):
        from qt.qapp import MainWindow
        from core import cheats as CH
        import qt.qtheme as T
        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        self._pump(300)
        w.start_new_run(0, None)
        self._pump(250)
        w.start_battle({"kind": "normal",
                        "enemies": ["infantry_squad"], "name": "t"})
        self._pump(500)
        self.assertEqual(w.stack.currentWidget().__class__.__name__,
                         "BattleScreen")
        CH.CheatRegistry().redeem("annex all", battle=w.battle)
        self._pump(1800)
        cur = w.stack.currentWidget().__class__.__name__
        self.assertNotEqual(cur, "BattleScreen",
                            "annex all 之后界面卡在战斗里")
        w.close()

    def test_hook_registered(self):
        """主窗口初始化时应注册战斗结束钩子。"""
        from qt.qapp import MainWindow
        from core import cheats as CH
        import qt.qtheme as T
        w = MainWindow()
        w.resize(T.WIN_W, T.WIN_H)
        self._pump(250)
        self.assertTrue(callable(CH._battle_over_hook),
                        "没有注册战斗结束钩子，兑换码会导致卡死")
        w.close()
