#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作弊提示文案的「风格开关」测试。

公开版必须用温和文案（不含人身攻击），完整版保留原话。
两者逻辑相同，只有提示语不同。
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 公开版不该出现的词（人身攻击 / 家人诅咒）
HARSH_WORDS = ("火葬场", "burn in hell", "全家")


class TestFlavorSwitch(unittest.TestCase):

    def setUp(self):
        self._old = os.environ.get("SF_CHEAT_FLAVOR")
        import core.netplay as N
        self.N = N

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SF_CHEAT_FLAVOR", None)
        else:
            os.environ["SF_CHEAT_FLAVOR"] = self._old

    def _flavor(self, name):
        os.environ["SF_CHEAT_FLAVOR"] = name
        return self.N.cheat_flavor()

    def test_mild_flavor_text(self):
        self._flavor("mild")
        self.assertEqual(self.N.cheat_text("shame"), "作弊是可耻的")
        self.assertEqual(self.N.cheat_text("label"), "作弊者")

    def test_spicy_flavor_text(self):
        self._flavor("spicy")
        self.assertEqual(self.N.cheat_text("shame"), "挂狗全家火葬场")
        self.assertEqual(self.N.cheat_text("label"), "挂狗")

    def test_default_is_mild(self):
        """不设环境变量时必须走温和版（公开版默认）。"""
        os.environ.pop("SF_CHEAT_FLAVOR", None)
        self.assertEqual(self.N.cheat_flavor(), "mild")
        self.assertEqual(self.N.DEFAULT_FLAVOR, "mild")

    def test_unknown_flavor_falls_back_to_mild(self):
        self._flavor("nonsense")
        self.assertEqual(self.N.cheat_flavor(), "mild")

    def test_mild_text_has_no_personal_attack(self):
        """温和版不能出现咒骂家人的字眼。"""
        self._flavor("mild")
        for key in ("shame", "label", "log"):
            txt = self.N.cheat_text(key)
            for w in HARSH_WORDS:
                self.assertNotIn(w, txt,
                                 "温和文案 %r 里出现了 %r" % (txt, w))

    def test_mild_log_formats_safely(self):
        self._flavor("mild")
        out = self.N.cheat_text("log") % "伪造消息"
        self.assertIn("伪造消息", out)


class TestNoHarshTextInPublicFiles(unittest.TestCase):
    """公开分发物里不能残留咒骂文案。"""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _read(self, rel):
        try:
            return open(os.path.join(self.ROOT, rel), encoding="utf-8").read()
        except Exception:
            return ""

    def test_readme_is_clean(self):
        src = self._read("README.md")
        self.assertTrue(src)
        # README 是公开文档，不能出现原话（只允许在说明里提到"完整版保留更直白措辞"）
        self.assertNotIn("挂狗全家火葬场", src,
                         "README 仍含原话，公开场合不合适")
        self.assertNotIn("burn in hell", src.lower())

    def test_locale_tables_are_clean(self):
        import json
        for f in ("zh.json", "en.json", "en_ui.json", "en_data.json"):
            p = os.path.join(self.ROOT, "locales", f)
            try:
                d = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            for k, v in d.items():
                for w in HARSH_WORDS:
                    self.assertNotIn(w, str(k) + str(v),
                                     "%s 的 %r 含 %r" % (f, k, w))

    def test_public_protocol_messages_are_neutral(self):
        """发给玩家的协议拒绝文案不能是指责口吻。"""
        src = self._read("core/netplay.py")
        self.assertTrue(src)
        # 这几种旧措辞不该再出现
        for old in ("客户端不能发送对战状态",
                    "客户端不能宣告对局结束"):
            self.assertNotIn(old, src,
                             "协议文案仍是旧版指责口吻：%s" % old)


if __name__ == "__main__":
    unittest.main(verbosity=2)
