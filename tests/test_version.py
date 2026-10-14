#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本与名称的一致性测试。

版本号只允许在 ``core/version.py`` 定义一处；界面标题、打包 Info.plist、
文档都必须从这里取。这些测试防止有人又把它写死到别处。
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import version as V  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestVersionModule(unittest.TestCase):

    def test_version_is_semver_like(self):
        """VERSION 必须是纯数字点分（macOS 的 Info.plist 不接受别的）。"""
        self.assertRegex(V.VERSION, r"^\d+(\.\d+)*$",
                         "VERSION 必须是 0.9 / 1.2.3 这种纯数字点分")

    def test_macos_strings_are_numeric(self):
        self.assertRegex(V.macos_version_string(), r"^\d+(\.\d+)*$")
        self.assertRegex(V.macos_build_string(), r"^\d+(\.\d+)*$")

    def test_names_present(self):
        self.assertTrue(V.NAME_ZH)
        self.assertTrue(V.NAME_EN)
        self.assertIn(V.NAME_ZH, V.FULL_NAME)
        self.assertIn(V.NAME_EN, V.FULL_NAME)

    def test_bundle_ids_valid(self):
        pat = re.compile(r"^[A-Za-z0-9.\-]+$")
        self.assertRegex(V.BUNDLE_ID, pat)
        self.assertRegex(V.BUNDLE_ID_PUBLIC, pat)
        self.assertNotEqual(V.BUNDLE_ID, V.BUNDLE_ID_PUBLIC,
                            "公开版需要独立的 bundle id")

    def test_helpers_include_version(self):
        for s in (V.title(), V.short(), V.about()):
            self.assertIn(V.VERSION_LABEL, s)

    def test_stage_consistent_with_label(self):
        """阶段是 beta 时，标签里应能看出是测试版。"""
        if V.STAGE == "beta":
            self.assertTrue(
                "测试" in V.VERSION_LABEL or "Beta" in V.VERSION_LABEL
                or "beta" in V.VERSION_LABEL,
                "beta 阶段的 VERSION_LABEL 应标明测试版")


class TestVersionIsSingleSourced(unittest.TestCase):
    """版本号不能散落在别处写死。"""

    def _read(self, rel):
        p = os.path.join(ROOT, rel)
        try:
            return open(p, encoding="utf-8").read()
        except Exception:
            return ""

    def test_ui_reads_from_version_module(self):
        for rel in ("qt/qapp.py", "ui/app.py"):
            src = self._read(rel)
            if not src:
                continue
            self.assertIn("version", src,
                          "%s 应从 core.version 取版本" % rel)

    def test_build_scripts_read_version(self):
        for rel in ("packaging/build_app.sh",
                    "packaging/build_app_public.sh"):
            src = self._read(rel)
            if not src:
                continue
            self.assertIn("core import version", src,
                          "%s 应从 core/version.py 读版本" % rel)

    def test_docs_mention_current_version(self):
        """README 顶部应写当前版本。"""
        src = self._read("README.md")
        if not src:
            self.skipTest("README 不存在")
        self.assertIn(V.VERSION_LABEL, src,
                      "README 没有写当前版本 %s" % V.VERSION_LABEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestVersionLabelLanguage(unittest.TestCase):
    """版本标签必须跟随语言（0.9.01 测试版 / 0.9.01 Beta）。"""

    def setUp(self):
        from core import i18n
        self._old = i18n.lang()

    def tearDown(self):
        from core import i18n
        i18n.set_lang(self._old)

    def test_chinese(self):
        from core import version as V, i18n
        i18n.set_lang("zh")
        self.assertIn("测试版", V.title())
        self.assertIn("测试版", V.short())
        self.assertIn("测试版", V.about())

    def test_english(self):
        from core import version as V, i18n
        i18n.set_lang("en")
        self.assertIn("Beta", V.title())
        self.assertIn("Beta", V.short())
        self.assertIn("Beta", V.about())
        self.assertNotIn("测试版", V.short(),
                         "英文界面不该出现中文版本标签")

    def test_version_number_consistent(self):
        """core/version.py 与 version.json 必须一致。"""
        import json
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(root, "version.json")
        if not os.path.isfile(p):
            self.skipTest("version.json 不存在")
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        from core import version as V
        self.assertEqual(d["version"], V.VERSION)
        self.assertEqual(d["label"], V.VERSION_LABEL)
        self.assertEqual(d["label_en"], V.VERSION_LABEL_EN)
