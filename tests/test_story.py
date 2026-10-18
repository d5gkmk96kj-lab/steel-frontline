#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主线剧情与无尽模式测试。"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import engine as EN  # noqa: E402
from core import run as R  # noqa: E402
from core import story as S  # noqa: E402


class TestStoryData(unittest.TestCase):

    def test_has_main_beats(self):
        self.assertGreaterEqual(S.total_beats(), 8,
                                "主线至少要有 8 段剧情")

    def test_has_vignettes(self):
        self.assertGreaterEqual(len(S.VIGNETTES), 10,
                                "小人物特写至少 10 段")

    def test_all_beats_have_content(self):
        for beats in S.MAIN_STORY.values():
            for b in beats:
                with self.subTest(beat=b.id):
                    self.assertTrue(b.title.strip(), "%s 没标题" % b.id)
                    self.assertTrue(b.lines, "%s 没正文" % b.id)
                    self.assertTrue(any(x.strip() for x in b.lines),
                                    "%s 正文是空的" % b.id)

    def test_vignettes_have_choices(self):
        for v in S.VIGNETTES:
            with self.subTest(vg=v.id):
                self.assertTrue(v.lines, "%s 没正文" % v.id)
                self.assertGreaterEqual(len(v.choices), 2,
                                        "%s 应该有两个选择" % v.id)

    def test_ids_unique(self):
        ids = []
        for beats in S.MAIN_STORY.values():
            ids += [b.id for b in beats]
        ids += [v.id for v in S.VIGNETTES]
        self.assertEqual(len(ids), len(set(ids)), "剧情 id 有重复")

    def test_every_act_has_beats(self):
        for act in (1, 2, 3):
            got = (S.beats_for("before_boss", act)
                   or S.beats_for("after_boss", act))
            self.assertTrue(got, "第 %d 幕没有任何剧情" % act)

    def test_ending_exists(self):
        e = S.ending_beat()
        self.assertIsNotNone(e, "没有结局")
        self.assertEqual(e.trigger, "after_boss")

    def test_beats_not_repeat_after_seen(self):
        seen = set()
        b1 = S.next_beat("before_boss", 1, seen)
        self.assertIsNotNone(b1)
        seen.add(b1.id)
        b2 = S.next_beat("before_boss", 1, seen)
        self.assertIsNone(b2, "看过的不该再给")

    def test_vignette_random_unique(self):
        rng = random.Random(1)
        seen = set()
        for _ in range(len(S.VIGNETTES)):
            v = S.random_vignette(rng, seen)
            self.assertIsNotNone(v)
            seen.add(v.id)
        self.assertIsNone(S.random_vignette(rng, seen),
                          "全部看过后应该返回 None")

    def test_tone_is_anti_war(self):
        """基调检查：不该出现「荣耀」「胜利万岁」这类美化战争的词。"""
        blob = []
        for beats in S.MAIN_STORY.values():
            for b in beats:
                blob.append(b.title)
                blob += list(b.lines)
        for v in S.VIGNETTES:
            blob.append(v.title)
            blob += list(v.lines)
        text = "\n".join(blob)
        for bad in ("荣耀", "万岁", "光荣牺牲", "为祖国献身"):
            self.assertNotIn(bad, text, "剧情基调不该用「%s」" % bad)


class TestStoryMode(unittest.TestCase):

    def _run(self, mode="story"):
        r = R.RunState()
        r.new_run(seed=11, mode=mode)
        return r

    def test_default_is_story(self):
        r = R.RunState()
        r.new_run(seed=1)
        self.assertEqual(r.mode, "story")
        self.assertFalse(r.story_cleared)

    def test_story_common_three_acts(self):
        r = self._run("story")
        self.assertEqual(r.max_act(), 3)
        r.advance_act(); self.assertEqual(r.act, 2)
        r.advance_act(); self.assertEqual(r.act, 3)
        r.advance_act()
        self.assertEqual(r.act, 4, "第三幕打完 act 应该变 4")
        self.assertTrue(r.story_cleared, "应该标记主线通关")

    def test_endless_cycles(self):
        r = self._run("endless")
        self.assertEqual(r.max_act(), 999)
        seq = []
        for _ in range(7):
            r.advance_act()
            seq.append(r.act)
        self.assertEqual(seq, [2, 3, 1, 2, 3, 1, 2], "无尽应该 1-2-3 循环")

    def test_endless_difficulty_grows(self):
        r = self._run("endless")
        self.assertAlmostEqual(r.difficulty_scale(), 1.0)
        for _ in range(3):
            r.advance_act()          # 走完一轮
        self.assertGreater(r.loop, 0, "应该记了循环数")
        self.assertGreater(r.difficulty_scale(), 1.0, "难度应该上升")

    def test_endless_enemy_scaling(self):
        r = self._run("endless")
        b1 = EN.make_battle(r, {"kind": "normal", "enemies": ["infantry_squad"]})
        hp1 = b1.enemies[0].max_hp
        r.loop = 5
        b2 = EN.make_battle(r, {"kind": "normal", "enemies": ["infantry_squad"]})
        self.assertGreater(b2.enemies[0].max_hp, hp1, "高循环敌人应该更硬")

    def test_act_pool_cycles(self):
        r = self._run("endless")
        r.act = 4
        self.assertIn(r.act_pool(), (1, 2, 3), "敌人池要回到 1..3")
        r2 = self._run("story")
        r2.act = 2
        self.assertEqual(r2.act_pool(), 2)


class TestStoryProgress(unittest.TestCase):

    def test_take_story_marks_seen(self):
        r = R.RunState(); r.new_run(seed=3)
        b = r.take_story("run_start")
        self.assertIsNotNone(b, "应该有开场剧情")
        self.assertIn(b["id"], r.story_seen)

    def test_take_story_once(self):
        r = R.RunState(); r.new_run(seed=3)
        b1 = r.take_story("run_start")
        self.assertIsNotNone(b1)
        b2 = r.take_story("run_start")
        self.assertIsNone(b2, "同一段剧情不该播两次")

    def test_take_vignette(self):
        r = R.RunState(); r.new_run(seed=3)
        v = r.take_vignette()
        self.assertIsNotNone(v)
        self.assertIn("lines", v)

    def test_apply_choice_returns_text(self):
        r = R.RunState(); r.new_run(seed=3)
        r.take_story("run_start")
        txt = r.apply_story_choice(0)
        self.assertIsInstance(txt, str)
        self.assertIsNone(r.pending_story, "选完应该清空 pending")

    def test_story_persists_in_save(self):
        import tempfile
        r = R.RunState(); r.new_run(seed=3, mode="endless")
        r.story_seen = {"prologue", "a1_boss"}
        r.loop = 2
        p = tempfile.mktemp(suffix=".json")
        try:
            R.save_run(r, p)
            r2 = R.load_run(p)
            self.assertEqual(r2.mode, "endless")
            self.assertEqual(r2.loop, 2)
            self.assertEqual(set(r2.story_seen), {"prologue", "a1_boss"})
        finally:
            try:
                os.unlink(p)
            except OSError:
                pass


class TestMetaStory(unittest.TestCase):

    def test_default_locked(self):
        m = R.MetaProgress()
        self.assertFalse(m.story_done, "默认应该锁着无尽模式")

    def test_unlock_persists(self):
        import tempfile
        m = R.MetaProgress()
        m.story_done = True
        m.story_wins = 1
        p = tempfile.mktemp(suffix=".json")
        try:
            m.save(p)
            m2 = R.MetaProgress.load(p)
            self.assertTrue(m2.story_done)
            self.assertEqual(m2.story_wins, 1)
        finally:
            try:
                os.unlink(p)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
