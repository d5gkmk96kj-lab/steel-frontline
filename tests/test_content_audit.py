#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内容审计：防止这次全面检查发现的问题再次出现。"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import i18n as I  # noqa: E402
from core.cards import CARD_DB  # noqa: E402

try:
    from core import cheats as _CH
    _CH._ensure_cheat_cards()
except Exception:
    pass

LOCALES = os.path.join(ROOT, "locales")


def _load(name):
    with open(os.path.join(LOCALES, name), encoding="utf-8") as f:
        return json.load(f)


class TestTranslations(unittest.TestCase):
    """翻译表完整性。"""

    def test_key_counts_match(self):
        zh, en = _load("zh.json"), _load("en.json")
        self.assertEqual(set(zh), set(en),
                         "zh/en 键不一致：多 %d 少 %d"
                         % (len(set(zh) - set(en)), len(set(en) - set(zh))))

    def test_ui_data_no_overlap(self):
        ui, data = _load("en_ui.json"), _load("en_data.json")
        overlap = set(ui) & set(data)
        self.assertEqual(overlap, set(),
                         "en_ui 和 en_data 有重复键：%s" % list(overlap)[:3])

    def test_no_untranslated(self):
        zh, en = _load("zh.json"), _load("en.json")
        bad = [k for k in zh
               if en.get(k) == zh[k] and re.search(r"[\u4e00-\u9fff]", str(k))]
        self.assertEqual(bad, [], "未翻译：%s" % bad[:5])

    def test_no_chinese_in_english(self):
        en = _load("en.json")
        bad = [k for k, v in en.items()
               if isinstance(v, str) and re.search(r"[\u4e00-\u9fff]", v)]
        self.assertEqual(bad, [], "英文里残留中文：%s" % bad[:5])

    def test_placeholders_consistent(self):
        zh, en = _load("zh.json"), _load("en.json")
        bad = []
        for k in zh:
            zp = set(re.findall(r"\{[a-z0-9_]+\}", str(zh[k])))
            ep = set(re.findall(r"\{[a-z0-9_]+\}", str(en.get(k) or "")))
            if zp != ep:
                bad.append(k)
        self.assertEqual(bad, [], "占位符不一致：%s" % bad[:5])


class TestMarkdownStripping(unittest.TestCase):
    """卡牌描述用 ** 强调，但 Qt 不认 markdown —— 必须剥掉。"""

    def test_t_strips_asterisks(self):
        self.assertEqual(I.t("对**全体**敌人"), "对全体敌人")

    def test_t_keeps_normal_text(self):
        self.assertEqual(I.t("普通文本"), "普通文本")

    def test_all_cards_text_clean_after_t(self):
        for c in CARD_DB.values():
            got = I.t(c.text or "")
            self.assertNotIn("**", str(got), "%s 的描述还带 **" % c.id)


class TestCardNames(unittest.TestCase):

    def test_no_duplicate_names(self):
        """重名卡牌会让玩家困惑（宝塔/作弊卡除外）。"""
        by = collections.defaultdict(list)
        for c in CARD_DB.values():
            if str(c.id).startswith("cheat_"):
                continue
            by[c.name].append(c.id)
        dup = {k: v for k, v in by.items() if len(v) > 1}
        self.assertEqual(dup, {}, "重名卡牌：%s" % dup)


class TestNoOceanLeftovers(unittest.TestCase):
    """主题是装甲战争，不该残留鲸鱼/海洋词汇。"""

    WORDS = ("鲸", "鲨", "触手", "深海", "珊瑚", "藤壶", "牡蛎", "海妖",
             "鱿", "乌贼", "水母")

    def test_source_clean(self):
        bad = []
        for fn in os.listdir(os.path.join(ROOT, "core")):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(ROOT, "core", fn)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for w in self.WORDS:
                for m in re.finditer(re.escape(w), src):
                    ctx = src[max(0, m.start() - 30):m.end() + 30]
                    if "whale" in ctx.lower():
                        continue        # 代码标识符（如 whale_charge）不算
                    bad.append((fn, w))
        self.assertEqual(bad, [], "海洋词残留：%s" % bad[:5])

    def test_locales_clean(self):
        if not os.path.isdir(LOCALES):
            self.skipTest("没有 locales")
        bad = []
        for fn in ("zh.json", "en.json", "en_ui.json", "en_data.json"):
            p = os.path.join(LOCALES, fn)
            if not os.path.isfile(p):
                continue
            with open(p, encoding="utf-8") as f:
                txt = f.read()
            for w in self.WORDS:
                if w in txt:
                    bad.append((fn, w))
        self.assertEqual(bad, [], "翻译表里还有海洋词：%s" % bad[:5])


class TestCardData(unittest.TestCase):

    def test_all_cards_have_text(self):
        for c in CARD_DB.values():
            self.assertTrue((c.text or "").strip(), "%s 没有描述" % c.id)

    def test_all_cards_have_name(self):
        for c in CARD_DB.values():
            self.assertTrue((c.name or "").strip(), "%s 没有名字" % c.id)

    def test_cost_in_range(self):
        """费用必须是 -2 到 5（负数 = 不可打出/X 费）。"""
        for c in CARD_DB.values():
            self.assertIsInstance(c.cost, int, "%s 费用不是整数" % c.id)
            self.assertGreaterEqual(c.cost, -2, "%s 费用过低" % c.id)
            self.assertLessEqual(c.cost, 5, "%s 费用过高" % c.id)

    def test_known_placeholders_only(self):
        ok = {"damage", "block", "magic", "magic2", "hits"}
        for c in CARD_DB.values():
            for ph in re.findall(r"\{([a-z0-9_]+)\}", c.text or ""):
                self.assertIn(ph, ok, "%s 有未知占位符 {%s}" % (c.id, ph))


if __name__ == "__main__":
    unittest.main(verbosity=2)
