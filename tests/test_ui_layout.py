#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""界面布局回归测试。

锁住几个「肉眼才看得出来」的布局 bug：
* TitleBar 没副标题时高度为 0 → 标题整个看不见（影响 10 个界面）
* 图鉴里未解锁的卡仍然印出真实效果（剪影失去意义）
* 事件插画高度写死 → 中间一条细带、下方大片空白
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SF_NO_UPDATE_CHECK"] = "1"

try:
    from PyQt6.QtCore import QEventLoop, QTimer
    HAS_QT = True
except Exception:                       # pragma: no cover
    HAS_QT = False


def _pump(ms=150):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestTitleBarHeight(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def test_height_without_subtitle(self):
        from qt.qscreens import TitleBar
        tb = TitleBar("战 场 事 件")
        self.assertGreater(tb.height(), 20,
                           "没有副标题时 TitleBar 高度不能是 0（标题会消失）")
        self.assertGreaterEqual(tb.minimumHeight(), 20)

    def test_height_with_subtitle(self):
        from qt.qscreens import TitleBar
        tb = TitleBar("图 鉴", "副标题")
        self.assertGreater(tb.height(), 20)


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestCodexSilhouette(unittest.TestCase):
    """图鉴里未见过的卡必须只显示占位文案，不能泄露真实效果。"""

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def test_placeholder_not_replaced(self):
        from qt.qwidgets import _card_text
        from core import cards as C
        cd = C.CARD_LIST[0]
        placeholder = "尚未在战场上缴获过这张卡牌。"
        text = _card_text({"def_id": cd.id, "text": placeholder})
        self.assertEqual(text, placeholder,
                         "剪影卡泄露了真实效果：%r" % text)

    def test_real_text_still_resolved(self):
        from qt.qwidgets import _card_text
        from core import cards as C
        cd = next(c for c in C.CARD_LIST if "{damage}" in c.text)
        text = _card_text({"def_id": cd.id, "text": C.resolve_text(cd)})
        self.assertNotIn("{damage}", text)
        self.assertTrue(text.strip())


@unittest.skipUnless(HAS_QT, "需要 PyQt6")
class TestEventLayout(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from qt.qapp import make_app
        cls.app = make_app([])

    def test_event_art_has_reasonable_height(self):
        from qt.qscreens import EventArt
        art = EventArt()
        self.assertGreaterEqual(art.height(), 150, "事件插画太扁")
        self.assertLessEqual(art.height(), 400, "事件插画过高（会挤掉文字）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
