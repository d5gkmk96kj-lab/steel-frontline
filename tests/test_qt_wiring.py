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
