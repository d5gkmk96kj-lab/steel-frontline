#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解锁系统回归测试。

之前 ``unlocked_cards`` / ``unlocked_relics`` 是**空壳**：字段有、存档有，
但从来没被填充，也没人用它过滤卡池 —— 203 张卡从第一局就全开放。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import cards as C       # noqa: E402
from core import run as R         # noqa: E402
from core import unlock as U      # noqa: E402


class TestUnlockBasics(unittest.TestCase):

    def test_starter_cards_nonempty(self):
        self.assertGreater(len(U.starter_cards()), 20)

    def test_starter_relics_nonempty(self):
        self.assertGreater(len(U.starter_relics()), 0)

    def test_ensure_starter_fills_meta(self):
        m = R.MetaProgress()
        self.assertTrue(U.ensure_starter(m))
        self.assertTrue(U.starter_cards() <= m.unlocked_cards)
        # 二次调用不应该再改动
        self.assertFalse(U.ensure_starter(m))

    def test_empty_set_means_all_unlocked(self):
        """空集合必须**全部放行** —— 否则老存档会突然少东西。"""
        m = R.MetaProgress()
        any_card = next(iter(C.CARD_DB))
        self.assertTrue(U.is_card_unlocked(m, any_card))

    def test_progress_shape(self):
        m = R.MetaProgress()
        U.ensure_starter(m)
        p = U.progress(m)
        for k in ("cards_unlocked", "cards_total", "cards_pct"):
            self.assertIn(k, p)
        self.assertGreater(p["cards_total"], 0)


class TestUnlockGrant(unittest.TestCase):

    def test_run_grants_cards(self):
        m = R.MetaProgress()
        U.ensure_starter(m)
        before = len(m.unlocked_cards)
        m.total_runs = 1
        new = U.grant_after_run(m, won=False)
        self.assertGreater(len(m.unlocked_cards), before, "打完一局应该解锁新卡")
        self.assertTrue(new, "应该返回新解锁的名字")

    def test_win_grants_more_than_loss(self):
        a = R.MetaProgress(); U.ensure_starter(a); a.total_runs = 1
        U.grant_after_run(a, won=False)
        b = R.MetaProgress(); U.ensure_starter(b); b.total_runs = 1
        U.grant_after_run(b, won=True)
        self.assertGreaterEqual(len(b.unlocked_cards), len(a.unlocked_cards))

    def test_no_duplicate_unlocks(self):
        m = R.MetaProgress(); U.ensure_starter(m)
        for i in range(8):
            m.total_runs = i + 1
            U.grant_after_run(m, won=(i % 2 == 0))
        self.assertEqual(len(m.unlocked_cards), len(set(m.unlocked_cards)))

    def test_all_contents_unlockable(self):
        """一直解锁下去，最终应该能解锁全部 uncommon / rare。"""
        m = R.MetaProgress(); U.ensure_starter(m)
        for i in range(120):
            m.total_runs = i + 1
            m.wins = i // 2
            U.grant_after_run(m, won=True)
        p = U.progress(m)
        self.assertGreaterEqual(p["cards_pct"], 95.0,
                                "解锁太慢：跑了 120 局才 %.0f%%" % p["cards_pct"])


class TestUnlockFilters(unittest.TestCase):

    def test_locked_card_never_offered(self):
        r = R.RunState(); r.new_run(seed=1)
        # 只放行一张卡
        unlock_all = set(C.CARD_DB)
        one = "strike"
        r.unlocked_cards = {one}
        for _ in range(40):
            for cd in r.offer_card_rewards(3):
                self.assertEqual(cd.id, one, "奖励池出了未解锁的卡")

    def test_locked_relic_never_offered(self):
        r = R.RunState(); r.new_run(seed=1)
        r.unlocked_relics = set()
        # 空集合 = 全开；这里给一个非空但很小的集合
        r.unlocked_relics = {"relic_compass"}
        for _ in range(20):
            for rid in r.offer_relic_rewards(1):
                self.assertIn(rid, {"relic_compass"}, "勋章池出了未解锁的")


class TestUnlockMigration(unittest.TestCase):

    def test_veteran_keeps_most_content(self):
        """老存档（玩过但没解锁字段）不能因为更新丢内容。"""
        m = R.MetaProgress()
        m.total_runs = 12
        m.story_done = True
        self.assertTrue(U.migrate(m))
        p = U.progress(m)
        self.assertGreaterEqual(p["cards_pct"], 99.0,
                                "通关过的老存档应该几乎全解锁")

    def test_fresh_meta_not_migrated(self):
        m = R.MetaProgress()
        self.assertFalse(U.migrate(m), "全新存档不该触发迁移")

    def test_meta_roundtrip_preserves_unlocks(self):
        m = R.MetaProgress(); U.ensure_starter(m)
        m.total_runs = 1
        U.grant_after_run(m, won=True)
        p = tempfile.mktemp(suffix=".json")
        try:
            m.save(p)
            m2 = R.MetaProgress.load(p)
            self.assertEqual(set(m.unlocked_cards), set(m2.unlocked_cards))
            self.assertEqual(set(m.unlocked_relics), set(m2.unlocked_relics))
        finally:
            try:
                os.unlink(p)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
