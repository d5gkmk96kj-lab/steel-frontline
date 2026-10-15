#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""特效与过渡测试：必须能渲染、能自毁、能关掉，且绝不阻塞或抛异常。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _qt_ok() -> bool:
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_qt_ok(), "PyQt6 不可用")
class TestFx(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        import qt.qtheme as T
        T.install_i18n_patch()

    def setUp(self):
        from qt import qfx
        qfx.set_enabled(True)

    def tearDown(self):
        from qt import qfx
        qfx.set_enabled(True)

    def _pump(self, ms=150):
        from PyQt6.QtCore import QEventLoop, QTimer
        l = QEventLoop()
        QTimer.singleShot(ms, l.quit)
        l.exec()

    def _host(self):
        from PyQt6.QtWidgets import QWidget
        h = QWidget()
        h.resize(500, 360)
        h.show()
        self._pump(80)
        return h

    def _fx_children(self, host):
        from PyQt6.QtWidgets import QWidget
        return [c for c in host.children()
                if isinstance(c, QWidget) and type(c).__name__ in
                ("SparkBurst", "ImpactRing", "SlashArc", "_Fader")]

    def test_hit_effect_creates_and_selfdestructs(self):
        from qt import qfx
        host = self._host()
        qfx.hit_effect(host, 250, 180, power=1.4)
        self.assertTrue(self._fx_children(host), "没有生成任何特效控件")
        self._pump(1400)          # 等动画跑完
        self.assertEqual(self._fx_children(host), [],
                         "动画结束后特效没有自毁（会泄漏）")
        host.close()

    def test_block_effect(self):
        from qt import qfx
        host = self._host()
        qfx.block_effect(host, 200, 150)
        self.assertTrue(self._fx_children(host))
        self._pump(900)
        host.close()

    def test_disabled_produces_nothing(self):
        """关掉特效后不能生成任何东西。"""
        from qt import qfx
        host = self._host()
        qfx.set_enabled(False)
        qfx.hit_effect(host, 250, 180)
        qfx.block_effect(host, 250, 180)
        self.assertEqual(self._fx_children(host), [])
        host.close()

    def test_extreme_power_does_not_crash(self):
        """伤害换算出的 power 再离谱也不能崩。"""
        from qt import qfx
        host = self._host()
        for p in (-5, 0, 0.001, 1, 99, 1e9, None):
            qfx.hit_effect(host, 250, 180, power=p)
        self._pump(400)
        host.close()

    def test_fade_switch_calls_through(self):
        """过渡最终必须真的执行切换（不能吞掉）。"""
        from qt import qfx
        host = self._host()
        called = []
        qfx.fade_switch(host, lambda: called.append(1), duration=80)
        self._pump(600)
        self.assertEqual(called, [1], "fade_switch 没有执行切换")
        host.close()

    def test_fade_switch_runs_even_if_disabled(self):
        from qt import qfx
        host = self._host()
        called = []
        qfx.set_enabled(False)
        qfx.fade_switch(host, lambda: called.append(1))
        self.assertEqual(called, [1], "关掉特效后切换也必须发生")
        host.close()

    def test_fade_switch_survives_bad_callback(self):
        from qt import qfx
        host = self._host()
        # 回调抛异常也不能把程序带崩
        qfx.fade_switch(host, lambda: (_ for _ in ()).throw(RuntimeError("x")),
                        duration=60)
        self._pump(400)
        host.close()

    def test_enabled_default_true(self):
        from qt import qfx
        qfx.set_enabled(True)
        self.assertTrue(qfx.enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
