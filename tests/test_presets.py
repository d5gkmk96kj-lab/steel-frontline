#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡组预设测试。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import presets as P  # noqa: E402


class PresetCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_preset_")
        self._old = os.environ.get("SF_GAME_HOME")
        os.environ["SF_GAME_HOME"] = self.tmp

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SF_GAME_HOME", None)
        else:
            os.environ["SF_GAME_HOME"] = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPresetBasics(PresetCase):

    def test_empty_at_first(self):
        self.assertEqual(P.load_all(), [])

    def test_add_and_load(self):
        ok, msg = P.add("火力流", ["strike", "inflame"])
        self.assertTrue(ok, msg)
        items = P.load_all()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "火力流")
        self.assertEqual(items[0]["cards"], ["strike", "inflame"])

    def test_duplicate_name_rejected(self):
        P.add("A", ["strike"])
        ok, msg = P.add("A", ["defend"])
        self.assertFalse(ok, "重名竟然被接受了")
        self.assertIn("同名", msg)

    def test_empty_name_rejected(self):
        ok, msg = P.add("", ["strike"])
        self.assertFalse(ok)

    def test_empty_cards_rejected(self):
        ok, msg = P.add("空卡组", [])
        self.assertFalse(ok)

    def test_name_truncated(self):
        P.add("x" * 50, ["strike"])
        self.assertLessEqual(len(P.load_all()[0]["name"]), P.MAX_NAME_LEN)


class TestPresetOps(PresetCase):

    def setUp(self):
        super().setUp()
        P.add("原始", ["strike", "defend"])

    def test_rename(self):
        ok, msg = P.rename("原始", "改名后")
        self.assertTrue(ok, msg)
        self.assertIsNone(P.get("原始"))
        self.assertIsNotNone(P.get("改名后"))

    def test_rename_to_existing_rejected(self):
        P.add("另一套", ["inflame"])
        ok, msg = P.rename("原始", "另一套")
        self.assertFalse(ok)

    def test_delete(self):
        ok, msg = P.delete("原始")
        self.assertTrue(ok, msg)
        self.assertEqual(P.load_all(), [])

    def test_delete_missing(self):
        ok, msg = P.delete("不存在")
        self.assertFalse(ok)

    def test_overwrite(self):
        ok, msg = P.overwrite("原始", ["nuke"])
        self.assertTrue(ok, msg)
        self.assertEqual(P.get("原始")["cards"], ["nuke"])

    def test_duplicate(self):
        ok, msg = P.duplicate("原始")
        self.assertTrue(ok, msg)
        self.assertEqual(len(P.load_all()), 2)
        names = [x["name"] for x in P.load_all()]
        self.assertIn("原始", names)
        self.assertTrue(any("副本" in n for n in names))


class TestPresetRobustness(PresetCase):

    def test_bad_json_does_not_crash(self):
        """坏数据不能让界面崩。"""
        with open(P.presets_path(), "w", encoding="utf-8") as f:
            f.write("{ not json at all")
        self.assertEqual(P.load_all(), [])

    def test_wrong_shape_ignored(self):
        with open(P.presets_path(), "w", encoding="utf-8") as f:
            f.write('{"not": "a list"}')
        self.assertEqual(P.load_all(), [])

    def test_bad_entries_skipped(self):
        import json
        with open(P.presets_path(), "w", encoding="utf-8") as f:
            json.dump([
                {"name": "好的", "cards": ["strike"]},
                {"name": "没卡", "cards": []},
                "not a dict",
                {"name": "非字符串卡", "cards": [1, 2, None]},
            ], f)
        items = P.load_all()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "好的")

    def test_max_presets(self):
        for i in range(P.MAX_PRESETS + 5):
            P.add("P%d" % i, ["strike"])
        self.assertLessEqual(len(P.load_all()), P.MAX_PRESETS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
