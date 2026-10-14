#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新检查与旧版清理测试。纯逻辑 + 文件系统，不联网、不建窗口。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import updater as U   # noqa: E402
from core import cleanup as C   # noqa: E402
from core import version as V   # noqa: E402


class TestVersionCompare(unittest.TestCase):
    """版本号必须按数字段比较，不能按字符串。"""

    def test_numeric_order(self):
        # 0.10 比 0.9 新（字符串比较会得出相反结论）
        self.assertTrue(U.is_newer("0.10", "0.9"))
        self.assertFalse(U.is_newer("0.9", "0.10"))

    def test_cases(self):
        cases = [
            ("0.9", "0.9", False), ("1.0", "0.9", True),
            ("0.9.1", "0.9", True), ("0.9", "0.9.1", False),
            ("0.10.2", "0.10", True), ("2.0", "1.99", True),
        ]
        for remote, local, want in cases:
            with self.subTest(remote=remote, local=local):
                self.assertEqual(U.is_newer(remote, local), want)

    def test_empty_remote_is_not_newer(self):
        self.assertFalse(U.is_newer("", "0.9"))
        self.assertFalse(U.is_newer(None, "0.9"))

    def test_parse_version(self):
        # 每段编成 (数值, 原始长度)，用来区分 0.9.01 与 0.9.1
        self.assertEqual(U.parse_version("0.10.2"), ((0, 1), (10, 2), (2, 1)))
        self.assertEqual(U.parse_version("v1.2"), ((1, 1), (2, 1)))
        self.assertEqual(U.parse_version("garbage"), ((0, 1),))
        self.assertEqual(U.parse_version(""), ((0, 1),))

    def test_patch_numbering_sequence(self):
        """0.9.01 起每次 +0.01 的整条序列必须严格递增。"""
        seq = ["0.9", "0.9.01", "0.9.02", "0.9.09", "0.9.10",
               "0.9.99", "0.10", "0.10.01", "1.0"]
        for a, b in zip(seq, seq[1:]):
            with self.subTest(a=a, b=b):
                self.assertTrue(U.is_newer(b, a), "%s 应该比 %s 新" % (b, a))
                self.assertFalse(U.is_newer(a, b), "%s 不该比 %s 新" % (a, b))

    def test_same_version_not_newer(self):
        for v in ("0.9", "0.9.01", "0.9.10", "1.0"):
            with self.subTest(v=v):
                self.assertFalse(U.is_newer(v, v))

    def test_leading_zero_distinguished(self):
        """0.9.01 与 0.9.1 不是同一个版本（补零编号要能区分）。"""
        self.assertTrue(U.is_newer("0.9.01", "0.9.1"))
        self.assertFalse(U.is_newer("0.9.1", "0.9.01"))


class TestAutoBump(unittest.TestCase):
    """发版脚本的自动 +0.01。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location(
            "bv", os.path.join(root, "packaging", "bump_version.py"))
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_sequence(self):
        cases = {"0.9": "0.9.01", "0.9.01": "0.9.02", "0.9.09": "0.9.10",
                 "0.9.99": "0.10", "0.10": "0.10.01", "0.10.01": "0.10.02"}
        for cur, want in cases.items():
            with self.subTest(cur=cur):
                self.assertEqual(self.m.auto_next(cur), want)

    def test_bumped_is_newer(self):
        for cur in ("0.9", "0.9.01", "0.9.98", "0.10"):
            with self.subTest(cur=cur):
                nxt = self.m.auto_next(cur)
                self.assertTrue(U.is_newer(nxt, cur),
                                "%s -> %s 应该更新" % (cur, nxt))


class TestManifest(unittest.TestCase):

    def test_parse_full(self):
        raw = json.dumps({
            "version": "0.10", "label": "0.10 测试版",
            "label_en": "0.10 Beta", "released": "2026-10-15",
            "url": "https://example.com/x.dmg",
            "notes": ["修复 A", "新增 B"], "notes_en": ["Fix A", "New B"],
        }, ensure_ascii=False)
        info = U.parse_manifest(raw)
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "0.10")
        self.assertEqual(len(info.notes), 2)
        self.assertTrue(U.is_newer(info.version))

    def test_parse_garbage_returns_none(self):
        for bad in ["", "{", "[]", "null", "123",
                    json.dumps({}), json.dumps({"version": 123}),
                    json.dumps({"version": ""})]:
            with self.subTest(bad=bad):
                self.assertIsNone(U.parse_manifest(bad))

    def test_notes_accept_single_string(self):
        info = U.parse_manifest(json.dumps(
            {"version": "1.0", "notes": "只有一条"}))
        self.assertEqual(info.notes, ["只有一条"])

    def test_offline_fetch_returns_none_not_raise(self):
        """离线/超时时必须返回 None，不能抛异常。"""
        old = U.MANIFEST_URL
        try:
            U.MANIFEST_URL = "http://127.0.0.1:9/definitely-not-listening"
            self.assertIsNone(U.fetch_manifest(timeout=1))
        finally:
            U.MANIFEST_URL = old

    def test_local_manifest_file_is_valid(self):
        """仓库里的 version.json 必须格式正确，且与 core/version.py 一致。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(root, "version.json")
        if not os.path.isfile(p):
            self.skipTest("version.json 不存在")
        with open(p, encoding="utf-8") as f:
            info = U.parse_manifest(json.load(f))
        self.assertIsNotNone(info, "version.json 格式不对")
        self.assertEqual(info.version, V.VERSION,
                         "version.json 与 core/version.py 版本号不一致")


class TestCleanupSafety(unittest.TestCase):
    """清理功能：只删自己的文件，绝不碰存档。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_clean_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_protected_paths(self):
        for p in ("/Users/x/Documents/钢铁战线/data/save.json",
                  "/Users/x/Documents/钢铁战线/music/a.ogg",
                  "/repo/.git/config"):
            with self.subTest(path=p):
                self.assertTrue(C._is_protected(p),
                                "%s 应受保护" % p)

    def test_scan_finds_app_and_old_dmg(self):
        apps = os.path.join(self.tmp, "Applications")
        os.makedirs(apps)
        os.makedirs(os.path.join(apps, "钢铁战线.app"))
        with open(os.path.join(apps, "钢铁战线.app", "x"), "w") as f:
            f.write("data")
        with open(os.path.join(apps, "钢铁战线-v0.1-安装包.dmg"), "w") as f:
            f.write("x")
        found = C.scan(only=[apps])
        kinds = {j.kind for j in found}
        self.assertIn("app", kinds)
        self.assertIn("dmg", kinds)

    def test_scan_skips_current_version_dmg(self):
        """当前版本的安装包不是垃圾（用户正要用的）。"""
        d = os.path.join(self.tmp, "Desktop")
        os.makedirs(d)
        cur = " SteelFrontline-v%s-beta.dmg" % V.VERSION
        with open(os.path.join(d, cur.strip()), "w") as f:
            f.write("x")
        found = C.scan(only=[d])
        self.assertEqual([j for j in found if j.kind == "dmg"], [],
                         "当前版本的 DMG 被误判为旧版")

    def test_scan_ignores_unrelated_files(self):
        d = os.path.join(self.tmp, "Desktop")
        os.makedirs(d)
        for n in ("照片.png", "报告.pdf", "别的游戏.dmg", "notes.txt"):
            with open(os.path.join(d, n), "w") as f:
                f.write("x")
        self.assertEqual(C.scan(only=[d]), [])

    def test_remove_works_and_refuses_protected(self):
        d = os.path.join(self.tmp, "Desktop")
        os.makedirs(d)
        victim = os.path.join(d, "钢铁战线-v0.1-安装包.dmg")
        with open(victim, "w") as f:
            f.write("x")
        junk = C.Junk(victim, "dmg", 1)
        protected = C.Junk("/Users/x/Documents/钢铁战线/data/save.json",
                           "dmg", 1)
        ok, failed = C.remove([junk, protected])
        self.assertEqual(ok, 1)
        self.assertFalse(os.path.exists(victim))
        self.assertIn(protected.path, failed,
                      "受保护的路径必须拒绝删除")

    def test_total_size(self):
        items = [C.Junk("a", "dmg", 100), C.Junk("b", "app", 200)]
        self.assertEqual(C.total_size(items), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
