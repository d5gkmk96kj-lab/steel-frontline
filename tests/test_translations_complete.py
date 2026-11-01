#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""翻译完整性回归测试。

这条测试是「英文化」的守门员：任何新增的卡牌 / 勋章 / 敌人 / 药水 /
成就 / 事件 / 剧情 / 教程文案，只要没进翻译表就会在这里失败。
"""

from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import i18n as I          # noqa: E402
from core import cards as C         # noqa: E402
from core import enemies as E       # noqa: E402
from core import events as EV       # noqa: E402
from core import relics as R        # noqa: E402
from core import run as RUN         # noqa: E402
from core import story as S         # noqa: E402
from core import tutorial as TU     # noqa: E402

LOCALES = os.path.join(ROOT, "locales")


def _cjk(s) -> bool:
    return isinstance(s, str) and any("\u4e00" <= ch <= "\u9fff" for ch in s)


class TestTranslationCoverage(unittest.TestCase):

    def setUp(self):
        I.set_lang("en")

    def tearDown(self):
        I.set_lang("zh")

    def _miss(self, cat, s, out):
        if _cjk(s) and _cjk(I.t(s)):
            out.append((cat, s[:60]))

    def test_cards_translated(self):
        miss = []
        for cd in C.CARD_LIST:
            self._miss("卡名", cd.name, miss)
            self._miss("卡文", cd.text, miss)
        self.assertEqual(miss, [], "有卡牌没翻译：%s" % miss[:3])

    def test_relics_translated(self):
        miss = []
        for rd in R.RELIC_LIST:
            self._miss("勋章名", rd.name, miss)
            self._miss("勋章文", rd.text, miss)
        self.assertEqual(miss, [], "有勋章没翻译：%s" % miss[:3])

    def test_enemies_translated(self):
        miss = []
        for ed in E.ENEMY_DB.values():
            self._miss("敌人名", ed.name, miss)
            for mv in getattr(ed, "moves", []) or []:
                self._miss("意图名", getattr(mv, "name", ""), miss)
                self._miss("意图文", getattr(mv, "text", ""), miss)
        self.assertEqual(miss, [], "有敌人没翻译：%s" % miss[:3])

    def test_potions_translated(self):
        miss = []
        for d in EV.POTION_DB.values():
            self._miss("药水名", d.get("name"), miss)
            self._miss("药水文", d.get("text"), miss)
        self.assertEqual(miss, [], "有药水没翻译：%s" % miss[:3])

    def test_achievements_translated(self):
        miss = []
        for a in RUN.ACHIEVEMENTS.values():
            self._miss("成就名", a.get("name"), miss)
        self.assertEqual(miss, [], "有成就没翻译：%s" % miss[:3])

    def test_events_translated(self):
        miss = []
        for ev in EV.EVENT_LIST:
            self._miss("事件名", ev.name, miss)
            self._miss("事件文", ev.text, miss)
            for ch in getattr(ev, "choices", ()) or ():
                self._miss("选项", ch.label, miss)
                self._miss("选项文", ch.desc, miss)
        self.assertEqual(miss, [], "有事件没翻译：%s" % miss[:3])

    def test_story_translated(self):
        miss = []
        for beats in S.MAIN_STORY.values():
            for b in beats:
                self._miss("剧情标题", b.title, miss)
                for line in b.lines:
                    self._miss("剧情", line, miss)
                for ch in b.choices:
                    self._miss("剧情选项", ch.label, miss)
                    self._miss("剧情选项", ch.desc, miss)
        for v in S.VIGNETTES:
            self._miss("特写标题", v.title, miss)
            for line in v.lines:
                self._miss("特写", line, miss)
            for ch in v.choices:
                self._miss("特写选项", ch.label, miss)
                self._miss("特写选项", ch.desc, miss)
        self.assertEqual(miss, [], "有剧情没翻译：%s" % miss[:3])

    def test_tutorial_translated(self):
        miss = []
        for st in TU.STEPS:
            self._miss("教程", st.text, miss)
            self._miss("教程", st.done_text, miss)
        self.assertEqual(miss, [], "有教程文案没翻译：%s" % miss[:3])

    def test_endless_mutators_translated(self):
        miss = []
        for m in RUN.LOOP_MUTATORS:
            self._miss("态势名", m.get("name"), miss)
            self._miss("态势文", m.get("text"), miss)
        self.assertEqual(miss, [], "有无尽态势没翻译：%s" % miss[:3])


class TestLocaleFiles(unittest.TestCase):

    def _load(self, fn):
        p = os.path.join(LOCALES, fn)
        if not os.path.isfile(p):
            self.skipTest("没有 " + fn)
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def test_zh_en_keys_in_sync(self):
        zh = self._load("zh.json")
        en = self._load("en.json")
        self.assertEqual(set(zh), set(en), "中英 key 不一致")

    def test_no_chinese_in_english(self):
        en = self._load("en.json")
        bad = [k for k, v in en.items() if _cjk(v)]
        self.assertEqual(bad, [], "英文表里有中文：%s" % [b[:24] for b in bad[:3]])

    def test_no_empty_values(self):
        en = self._load("en.json")
        bad = [k for k, v in en.items()
               if not (isinstance(v, str) and v.strip())]
        self.assertEqual(bad, [], "有空翻译：%s" % [b[:24] for b in bad[:3]])

    def test_shards_do_not_overlap(self):
        ui = self._load("en_ui.json")
        data = self._load("en_data.json")
        dup = set(ui) & set(data)
        self.assertEqual(dup, set(),
                         "两个分片不能有相同 key：%s" % list(dup)[:3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
