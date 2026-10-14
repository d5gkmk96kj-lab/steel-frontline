#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存档槽系统测试：多存档 / 导入导出 / 坏文件防护。

不建窗口，纯文件 IO，可安全与其它测试同进程运行。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import run as run_mod  # noqa: E402
from core import saves as sv     # noqa: E402


class SaveCase(unittest.TestCase):
    """每个用例用独立的临时 data 目录，互不干扰。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_save_")
        self._old_dir = run_mod.DATA_DIR
        self._old_path = run_mod.SAVE_PATH
        run_mod.DATA_DIR = self.tmp
        run_mod.SAVE_PATH = os.path.join(self.tmp, "save.json")

    def tearDown(self):
        run_mod.DATA_DIR = self._old_dir
        run_mod.SAVE_PATH = self._old_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, seed=1, hp=50, floor=3):
        r = run_mod.RunState()
        r.new_run(seed=seed)
        r.hp = hp
        r.floor = floor
        return r


class TestSlotCRUD(SaveCase):

    def test_save_and_list(self):
        sv.save_new(self._run(hp=60), "甲")
        sv.save_new(self._run(seed=2, hp=40), "乙")
        got = sv.slots()
        self.assertEqual(len(got), 2)
        names = {s.name for s in got}
        self.assertEqual(names, {"甲", "乙"})

    def test_load_roundtrip(self):
        sid = sv.save_new(self._run(hp=63, floor=9), "测试")
        r = sv.load(sid)
        self.assertIsNotNone(r)
        self.assertEqual(r.hp, 63)
        self.assertEqual(r.floor, 9)

    def test_save_to_updates_same_slot(self):
        sid = sv.save_new(self._run(hp=10), "存档")
        sv.save_to(sid, self._run(hp=70))
        self.assertEqual(sv.count(), 1, "覆盖保存不该新增槽位")
        self.assertEqual(sv.load(sid).hp, 70)

    def test_delete(self):
        sid = sv.save_new(self._run(), "待删")
        self.assertEqual(sv.count(), 1)
        self.assertTrue(sv.delete(sid))
        self.assertEqual(sv.count(), 0)
        self.assertIsNone(sv.load(sid))

    def test_rename(self):
        sid = sv.save_new(self._run(), "原名")
        self.assertTrue(sv.rename(sid, "新名"))
        self.assertEqual(sv.get(sid).name, "新名")

    def test_empty_dir_returns_empty_list(self):
        self.assertEqual(sv.slots(), [])
        self.assertEqual(sv.count(), 0)

    def test_latest_slot_tracking(self):
        a = sv.save_new(self._run(seed=11, hp=55, floor=4), "A")
        self.assertEqual(sv.latest_slot(), a)

    def test_info_has_display_fields(self):
        sid = sv.save_new(self._run(hp=44, floor=6), "显示")
        info = sv.get(sid)
        self.assertTrue(info.title())
        self.assertIn("44", info.summary())
        self.assertTrue(info.when())


class TestExportImport(SaveCase):

    def test_export_then_import(self):
        sid = sv.save_new(self._run(hp=58, floor=8), "要分享的")
        out = os.path.join(self.tmp, "share.json")
        self.assertTrue(sv.export_to(sid, out))
        self.assertTrue(os.path.isfile(out))

        # 模拟对方：清空存档目录后再导入
        shutil.rmtree(sv.slots_dir(), ignore_errors=True)
        self.assertEqual(sv.count(), 0)
        new_id = sv.import_from(out, "朋友给的")
        self.assertIsNotNone(new_id)
        self.assertEqual(sv.load(new_id).hp, 58)
        self.assertEqual(sv.get(new_id).name, "朋友给的")

    def test_import_rejects_garbage(self):
        cases = {
            "not_json": "这不是 json {{{",
            "empty_dict": "{}",
            "wrong_shape": json.dumps({"hello": "world"}),
            "missing_deck": json.dumps(
                {"run": {"seed": 1, "hp": 1, "max_hp": 1}}),
            "bad_types": json.dumps(
                {"run": {"seed": "x", "hp": "y", "max_hp": 1, "deck": []}}),
        }
        for name, content in cases.items():
            p = os.path.join(self.tmp, "%s.json" % name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            with self.subTest(case=name):
                self.assertIsNone(sv.import_from(p),
                                  "%s 不该被当成有效存档" % name)

    def test_import_missing_file(self):
        self.assertIsNone(sv.import_from("/definitely/not/here.json"))

    def test_export_missing_slot(self):
        self.assertFalse(sv.export_to("nope", os.path.join(self.tmp, "x.json")))


class TestLegacyCompat(SaveCase):

    def test_reads_old_flat_format(self):
        """老存档是「直接一份 RunState dict」，必须还能读。"""
        r = self._run(hp=37)
        p = os.path.join(sv.slots_dir(), "old.json")
        os.makedirs(sv.slots_dir(), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(r.to_dict(), f, ensure_ascii=False)
        self.assertTrue(sv.load("old"))
        self.assertEqual(sv.load("old").hp, 37)
        self.assertEqual(sv.get("old").name, "")   # 老格式没名字

    def test_broken_file_marked_not_crash(self):
        os.makedirs(sv.slots_dir(), exist_ok=True)
        p = os.path.join(sv.slots_dir(), "broken.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{ 坏掉的")
        infos = sv.slots()
        self.assertEqual(len(infos), 1)
        self.assertTrue(infos[0].broken)
        self.assertIn("损坏", infos[0].summary())

    def test_migrate_legacy(self):
        """首次运行把老的单文件存档收进槽位。"""
        r = self._run(hp=48)
        run_mod.save_run(r)
        sid = sv.migrate_legacy()
        self.assertIsNotNone(sid)
        self.assertEqual(sv.count(), 1)


class TestSafety(SaveCase):

    def test_weird_names_are_safe(self):
        """存档名可以随便写，但不能影响文件名。"""
        for bad in ("../../etc/passwd", "a/b\\c", "名字 带空格", "x" * 200):
            sid = sv.save_new(self._run(), bad)
            self.assertIsNotNone(sid)
            self.assertNotIn("/", sid)
            self.assertNotIn("..", sid)
        self.assertEqual(sv.count(), 4)

    def test_delete_missing_is_ok(self):
        self.assertTrue(sv.delete("no-such-slot"))

    def test_rename_missing_fails_cleanly(self):
        self.assertFalse(sv.rename("no-such-slot", "x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
