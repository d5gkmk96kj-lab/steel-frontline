#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：用户实际遇到的三个界面 bug。

1. 休息节点可以无限点「进行休整」刷满耐久
2. 休息界面把 HTML 标签当纯文本显示出来
3. 补给站页签名字不翻译

这些都不建窗口（用假对象），保证可安全与其它测试同进程运行。
"""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRestSingleUse(unittest.TestCase):
    """休息节点只能用一次（不能无限回血）。"""

    def _fake_run(self, hp=40, mx=75):
        class R:
            def __init__(self):
                self.hp = hp
                self.max_hp = mx
                self.ascension = 0
            def rest_heal_amount(self):
                return int(self.max_hp * 0.30)
            def heal(self, n):
                self.hp = min(self.max_hp, self.hp + int(n))
            def upgradable_cards(self):
                return []
        return R()

    def test_source_guards_double_use(self):
        """源码里必须有「用过就不能再用」的守卫（防止回归）。"""
        src = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "qt", "qapp.py"), encoding="utf-8").read()
        for fn in ("on_rest_heal", "on_rest_upgrade"):
            i = src.find("def %s" % fn)
            self.assertGreater(i, 0, "找不到 %s" % fn)
            body = src[i:i + 900]
            self.assertIn("_rest_used", body,
                          "%s 缺少单次使用守卫" % fn)
            self.assertIn('show_screen("map")', body,
                          "%s 用完后必须离开休息界面" % fn)

    def test_heal_is_clamped_to_max(self):
        """回血不能超过上限。"""
        r = self._fake_run(hp=70, mx=75)
        r.heal(r.rest_heal_amount())
        self.assertLessEqual(r.hp, r.max_hp)


class TestNoRawHtmlInLabels(unittest.TestCase):
    """界面文字不能把 HTML 标签当纯文本显示。"""

    def test_rest_heal_text_is_rich(self):
        src = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "qt", "qscreens.py"), encoding="utf-8").read()
        i = src.find("def setup(self, run)")
        # 找到休息界面的 setup（含 lbl_heal 的那个）
        j = src.find("lbl_heal.setText", i)
        self.assertGreater(j, 0, "找不到 lbl_heal.setText")
        block = src[j:j + 800]
        # 必须显式声明富文本，或让字符串以标签开头
        self.assertTrue(
            "setTextFormat" in block or block.lstrip().startswith('"<'),
            "休息文案没有声明富文本格式，HTML 标签会外露")

    def test_no_html_tag_in_translation_values_mismatch(self):
        """译文里若出现 <b>，原文也必须有对应标签（否则渲染会错位）。"""
        import json
        loc = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "locales")
        try:
            zh = json.load(open(os.path.join(loc, "zh.json"), encoding="utf-8"))
            en = json.load(open(os.path.join(loc, "en.json"), encoding="utf-8"))
        except Exception as e:
            self.skipTest("locales 不可读：%s" % e)
        bad = []
        for k, v in en.items():
            if not v:
                continue
            for tag in ("<b>", "</b>", "<br>", "<div", "<span"):
                if (tag in v) != (tag in k):
                    bad.append((k[:40], v[:40], tag))
                    break
        self.assertEqual(bad, [],
                         "%d 条译文与原文的 HTML 标签不一致：%s"
                         % (len(bad), bad[:3]))


class TestShopTabsTranslated(unittest.TestCase):
    """补给站页签（QTabWidget.addTab）也要翻译。"""

    def test_tab_titles_are_in_locale(self):
        import json
        loc = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "locales")
        try:
            en = json.load(open(os.path.join(loc, "en.json"), encoding="utf-8"))
        except Exception as e:
            self.skipTest("locales 不可读：%s" % e)
        # 源码里 addTab 用到的中文标题
        src = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "qt", "qscreens.py"), encoding="utf-8").read()
        titles = re.findall(r'addTab\([^,]+,\s*"([^"]*[\u4e00-\u9fff][^"]*)"',
                            src)
        self.assertTrue(titles, "没有找到任何中文页签标题")
        missing = [t for t in titles if not en.get(t)]
        self.assertEqual(missing, [],
                         "这些页签没有英文翻译：%s" % missing)

    def test_qtabwidget_is_patched(self):
        """qtheme 必须给 QTabWidget.addTab 打补丁。"""
        src = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "qt", "qtheme.py"), encoding="utf-8").read()
        self.assertIn("QTabWidget", src,
                      "qtheme 没有处理 QTabWidget，页签不会翻译")


class TestDifficultySelectable(unittest.TestCase):
    """战役难度必须可选（曾经新档锁死在 0）。"""

    def test_full_range_available(self):
        from core import run as run_mod
        top = len(run_mod.ASCENSION_TABLE) - 1
        self.assertGreaterEqual(top, 19, "难度档位太少")

    def test_source_does_not_gate_on_unlocked(self):
        """不能再用 ascension_unlocked 当上限（那会让新档只能选 0）。"""
        src = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "qt", "qscreens.py"), encoding="utf-8").read()
        i = src.find("spin_asc.setMaximum")
        self.assertGreater(i, 0)
        near = src[max(0, i - 400):i + 100]
        self.assertNotIn("setMaximum(min(20, max_asc))", near,
                         "难度上限又被 ascension_unlocked 限制了")


if __name__ == "__main__":
    unittest.main(verbosity=2)
