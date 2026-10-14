#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""i18n 测试：翻译表完整性、切换、占位符、回落安全。

不建窗口，纯逻辑，可安全与其它测试同进程运行。
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import i18n  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = os.path.join(ROOT, "locales")
CJK = re.compile(r"[\u4e00-\u9fff]")


def _load(name):
    try:
        with open(os.path.join(LOCALES, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class TestBasicAPI(unittest.TestCase):

    def setUp(self):
        i18n.set_lang("zh")

    def tearDown(self):
        i18n.set_lang("zh")

    def test_default_is_chinese(self):
        self.assertEqual(i18n.lang(), "zh")

    def test_switch_lang(self):
        self.assertEqual(i18n.set_lang("en"), "en")
        self.assertEqual(i18n.lang(), "en")
        self.assertEqual(i18n.set_lang("zh"), "zh")

    def test_invalid_lang_falls_back(self):
        self.assertEqual(i18n.set_lang("klingon"), "zh")
        self.assertEqual(i18n.set_lang(""), "zh")
        self.assertEqual(i18n.set_lang(None), "zh")

    def test_toggle_cycles(self):
        i18n.set_lang("zh")
        a = i18n.toggle_lang()
        b = i18n.toggle_lang()
        self.assertNotEqual(a, b)
        self.assertEqual(b, "zh")

    def test_is_english(self):
        i18n.set_lang("en")
        self.assertTrue(i18n.is_english())
        i18n.set_lang("zh")
        self.assertFalse(i18n.is_english())


class TestTranslate(unittest.TestCase):

    def setUp(self):
        i18n._tables.clear()

    def tearDown(self):
        i18n.set_lang("zh")

    def test_chinese_mode_is_identity(self):
        i18n.set_lang("zh")
        self.assertEqual(i18n.t("开始战役"), "开始战役")
        self.assertEqual(i18n.t("随便什么"), "随便什么")

    def test_unknown_string_falls_back_to_chinese(self):
        """查不到翻译必须原样返回中文，不能变空白。"""
        i18n.set_lang("en")
        out = i18n.t("这肯定没有翻译__xyz__")
        self.assertEqual(out, "这肯定没有翻译__xyz__")
        self.assertNotEqual(out, "")

    def test_non_string_passthrough(self):
        i18n.set_lang("en")
        for v in (None, 42, 3.14, [], {}, True):
            self.assertEqual(i18n.t(v), v)

    def test_empty_string(self):
        self.assertEqual(i18n.t(""), "")

    def test_fmt_fills_placeholders(self):
        i18n.set_lang("zh")
        self.assertEqual(
            i18n.fmt("{name} 打出了 {card}", name="A", card="B"),
            "A 打出了 B")

    def test_fmt_missing_key_does_not_crash(self):
        i18n.set_lang("zh")
        # 少给参数不能抛异常
        out = i18n.fmt("{a} 和 {b}", a="X")
        self.assertIsInstance(out, str)

    def test_has(self):
        i18n.set_lang("zh")
        self.assertTrue(i18n.has("开始战役"))     # 中文模式恒为 True


class TestShardFiles(unittest.TestCase):
    """分片文件必须格式正确、无重复冲突。"""

    def test_zh_index_exists(self):
        zh = _load("zh.json")
        self.assertGreater(len(zh), 500, "zh.json 太小，抽取可能失败")

    def test_shards_are_valid_json_dicts(self):
        for name in ("en_ui.json", "en_data.json"):
            d = _load(name)
            self.assertIsInstance(d, dict, "%s 应为 dict" % name)
            self.assertGreater(len(d), 0, "%s 为空" % name)

    def test_shards_do_not_overlap(self):
        """两个分片不能有相同的 key（否则合并顺序会决定结果）。"""
        a = set(_load("en_ui.json"))
        b = set(_load("en_data.json"))
        dup = a & b
        self.assertEqual(dup, set(),
                         "分片有 %d 个重复 key：%s" % (len(dup), list(dup)[:5]))

    def test_all_keys_come_from_zh_index(self):
        """译文 key 必须都在中文索引里（防止翻译了不存在的原文）。"""
        zh = set(_load("zh.json"))
        for name in ("en_ui.json", "en_data.json"):
            extra = set(_load(name)) - zh
            self.assertEqual(extra, set(),
                             "%s 有 %d 个不在 zh.json 的 key" % (name, len(extra)))


class TestPlaceholderIntegrity(unittest.TestCase):
    """占位符与 HTML 标签必须一一对应，否则 format() 会崩或显示错乱。"""

    def _pairs(self):
        out = []
        for name in ("en_ui.json", "en_data.json"):
            for k, v in _load(name).items():
                if v:
                    out.append((k, v))
        return out

    def test_placeholders_match(self):
        bad = []
        for k, v in self._pairs():
            if set(re.findall(r"\{[^}]+\}", k)) != set(re.findall(r"\{[^}]+\}", v)):
                bad.append((k, v))
        self.assertEqual(bad, [],
                         "%d 条占位符不一致：%s" % (len(bad), bad[:3]))

    def test_percent_placeholders_match(self):
        """printf 风格的 %d/%s 数量也要一致，否则运行时会 TypeError。

        这条是补的 —— 曾有一条译文漏了 %s，导致组卡界面刷新报错。
        """
        bad = []
        for k, v in self._pairs():
            nk = len(re.findall(r"%[sdrf]", k))
            nv = len(re.findall(r"%[sdrf]", v))
            if nk != nv:
                bad.append((k, v, nk, nv))
        self.assertEqual(bad, [],
                         "%d 条 %% 占位符数量不一致：%s" % (len(bad), bad[:3]))

    def test_br_tags_match(self):
        bad = [k for k, v in self._pairs() if k.count("<br>") != v.count("<br>")]
        self.assertEqual(bad, [], "%d 条 <br> 不一致" % len(bad))

    def test_no_chinese_left_in_translations(self):
        left = [k for k, v in self._pairs() if CJK.search(v)]
        self.assertEqual(left, [],
                         "%d 条译文里还有中文：%s" % (len(left), left[:5]))


class TestCoverage(unittest.TestCase):
    """覆盖率门槛（防止有人把翻译表清空）。"""

    def test_coverage_above_threshold(self):
        i18n._tables.clear()
        c = i18n.coverage()
        self.assertGreater(c, 0.5,
                           "英文覆盖率只有 %.1f%%，太低" % (c * 100))

    def test_stats_shape(self):
        st = i18n.stats()
        for k in ("zh", "en", "covered", "missing"):
            self.assertIn(k, st)
        self.assertGreaterEqual(st["zh"], st["covered"])


class TestPersistence(unittest.TestCase):
    """语言选择要能记住（prefs.json）。"""

    def test_prefs_roundtrip(self):
        try:
            from ui.app import _load_pref, _save_pref
        except Exception as e:
            self.skipTest("ui.app 不可用：%s" % e)
        _save_pref("lang", "en")
        self.assertEqual(_load_pref("lang", "zh"), "en")
        _save_pref("lang", "zh")
        self.assertEqual(_load_pref("lang", "zh"), "zh")


if __name__ == "__main__":
    unittest.main(verbosity=2)
