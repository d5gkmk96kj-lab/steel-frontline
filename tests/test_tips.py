#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tips 系统测试：解析、分节、兜底、容错。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import tips   # noqa: E402


class TestParse(unittest.TestCase):

    def test_basic_lines(self):
        d = tips._parse("第一条\n第二条\n\n第三条\n")
        self.assertEqual(d["general"],
                         [("第一条", ""), ("第二条", ""), ("第三条", "")])

    def test_comments_and_blanks_ignored(self):
        d = tips._parse("# 注释\n\n真的提示\n   \n# 又一条注释\n")
        self.assertEqual(d["general"], [("真的提示", "")])

    def test_sections(self):
        text = "通用一\n[菜单]\n菜单一\n菜单二\n[胜利]\n胜利一\n"
        d = tips._parse(text)
        self.assertEqual(d["general"], [("通用一", "")])
        self.assertEqual(d["menu"], [("菜单一", ""), ("菜单二", "")])
        self.assertEqual(d["win"], [("胜利一", "")])

    def test_english_section_markers(self):
        d = tips._parse("[menu]\nA\n[load]\nB\n[win]\nC\n[lose]\nD\n")
        self.assertEqual(d["menu"], [("A", "")])
        self.assertEqual(d["load"], [("B", "")])
        self.assertEqual(d["win"], [("C", "")])
        self.assertEqual(d["lose"], [("D", "")])

    def test_whitespace_trimmed(self):
        d = tips._parse("   前后有空格   \n")
        self.assertEqual(d["general"], [("前后有空格", "")])

    def test_empty_text(self):
        d = tips._parse("")
        self.assertEqual(d.get("general"), [])


class TestRandomTip(unittest.TestCase):

    def setUp(self):
        tips.reload()

    def tearDown(self):
        tips.reload()

    def test_never_returns_empty(self):
        """无论文件怎样，random_tip 都不能返回空串。"""
        for scene in ("menu", "load", "win", "lose", "general", ""):
            with self.subTest(scene=scene):
                self.assertTrue(tips.random_tip(scene).strip())

    def test_unknown_scene_falls_back(self):
        t = tips.random_tip("不存在的场景")
        self.assertTrue(t.strip())

    def test_deterministic_with_rng(self):
        import random
        a = tips.random_tip("general", random.Random(1))
        b = tips.random_tip("general", random.Random(1))
        self.assertEqual(a, b)

    def test_builtin_fallback_present(self):
        self.assertTrue(tips.DEFAULT_TIPS)
        self.assertTrue(tips.random_tip("general").strip())


class TestFileHandling(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_tips_")
        tips.reload()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        tips.reload()

    def _write(self, text):
        p = os.path.join(self.tmp, "tips.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_source_builtin_when_empty(self):
        p = self._write("# 全是注释\n[菜单]\n")
        old = tips._candidate_paths
        try:
            tips._candidate_paths = lambda: [p]
            tips.reload()
            self.assertTrue(tips.file_is_empty())
            self.assertEqual(tips.source(), "builtin")
        finally:
            tips._candidate_paths = old

    def test_source_file_when_filled(self):
        p = self._write("真提示一\n真提示二\n")
        old = tips._candidate_paths
        try:
            tips._candidate_paths = lambda: [p]
            tips.reload()
            self.assertFalse(tips.file_is_empty())
            self.assertEqual(tips.source(), "file")
            self.assertIn(tips.random_tip("general"), ["真提示一", "真提示二"])
        finally:
            tips._candidate_paths = old

    def test_missing_file_uses_builtin(self):
        old = tips._candidate_paths
        try:
            tips._candidate_paths = lambda: [
                os.path.join(self.tmp, "nope.txt")]
            tips.reload()
            self.assertTrue(tips.random_tip("menu").strip())
            self.assertEqual(tips.source(), "builtin")
        finally:
            tips._candidate_paths = old

    def test_repo_tips_file_is_parseable(self):
        """仓库里的 tips.txt 必须能被解析（哪怕现在还是空的）。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(root, "tips.txt")
        if not os.path.isfile(p):
            self.skipTest("tips.txt 不存在")
        with open(p, encoding="utf-8") as f:
            d = tips._parse(f.read())
        for v in d.values():
            self.assertIsInstance(v, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestBilingual(unittest.TestCase):
    """中文 | 英文 一行两条。"""

    def test_split(self):
        self.assertEqual(tips.split_bilingual("中文A | English B"),
                         ("中文A", "English B"))
        self.assertEqual(tips.split_bilingual("中文A｜English B"),
                         ("中文A", "English B"))
        self.assertEqual(tips.split_bilingual("只有中文"), ("只有中文", ""))

    def test_parse_keeps_pairs(self):
        d = tips._parse("甲 | Alpha\n乙\n")
        self.assertEqual(d["general"], [("甲", "Alpha"), ("乙", "")])

    def test_language_picks_right_half(self):
        from core import i18n
        s = open('tips.txt', encoding='utf-8').read() if os.path.isfile('tips.txt') else ''
        p = os.path.join(tempfile.mkdtemp(prefix="sf_bi_"), "tips.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("中文甲 | EnglishA\n中文乙 | EnglishB\n")
        old = tips._candidate_paths
        old_lang = i18n.lang()
        try:
            tips._candidate_paths = lambda: [p]
            tips.reload()
            i18n.set_lang("en")
            got = {tips.random_tip("general") for _ in range(20)}
            self.assertEqual(got, {"EnglishA", "EnglishB"})
            i18n.set_lang("zh")
            got = {tips.random_tip("general") for _ in range(20)}
            self.assertEqual(got, {"中文甲", "中文乙"})
        finally:
            i18n.set_lang(old_lang)
            tips._candidate_paths = old
            tips.reload()

    def test_english_falls_back_to_chinese(self):
        """只写了中文时，英文界面也要有内容（回落中文）。"""
        from core import i18n
        p = os.path.join(tempfile.mkdtemp(prefix="sf_bi2_"), "tips.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("只有中文\n")
        old = tips._candidate_paths
        old_lang = i18n.lang()
        try:
            tips._candidate_paths = lambda: [p]
            tips.reload()
            i18n.set_lang("en")
            self.assertEqual(tips.random_tip("general"), "只有中文")
        finally:
            i18n.set_lang(old_lang)
            tips._candidate_paths = old
            tips.reload()
