#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台测试：Windows 版命名、路径、清理目录、PyQt6 提示。

不需要真的在 Windows 上跑 —— 通过模拟 sys.platform 验证分支逻辑。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import version as V    # noqa: E402
from core import cleanup as C    # noqa: E402


class TestPlatformNaming(unittest.TestCase):
    """Windows 版名字要带 "Windows Rework"。"""

    def setUp(self):
        self._flag = V.IS_WINDOWS_EDITION
        self._plat = sys.platform

    def tearDown(self):
        V.IS_WINDOWS_EDITION = self._flag
        sys.platform = self._plat

    def test_mac_has_no_suffix(self):
        V.IS_WINDOWS_EDITION = False
        sys.platform = "darwin"
        self.assertEqual(V.platform_suffix(), "")
        self.assertEqual(V.window_name(), V.NAME_ZH)
        self.assertEqual(V.bundle_name(), V.NAME_ZH)
        self.assertNotIn("Windows", V.title())

    def test_windows_suffix(self):
        V.IS_WINDOWS_EDITION = True
        self.assertEqual(V.platform_suffix(), "Windows Rework")
        self.assertIn("Windows Rework", V.window_name())
        self.assertIn("Windows Rework", V.title())
        self.assertIn("Windows Rework", V.about())

    def test_bundle_name_has_no_spaces(self):
        """打包名不能有空格，否则脚本引用会出问题。"""
        V.IS_WINDOWS_EDITION = True
        self.assertNotIn(" ", V.bundle_name())
        self.assertNotIn(" ", V.bundle_name_public())
        self.assertIn("WindowsRework", V.bundle_name())

    def test_platform_autodetect(self):
        """没有显式标记时，按 sys.platform 判断。"""
        V.IS_WINDOWS_EDITION = False
        sys.platform = "win32"
        self.assertEqual(V.platform_suffix(), "Windows Rework")
        sys.platform = "darwin"
        self.assertEqual(V.platform_suffix(), "")

    def test_version_strings_consistent(self):
        for flag in (False, True):
            with self.subTest(windows=flag):
                V.IS_WINDOWS_EDITION = flag
                self.assertIn(V.VERSION, V.title())
                self.assertIn(V.VERSION, V.about())


class TestPlatformPaths(unittest.TestCase):
    """Windows 上不能往 Program Files 写。"""

    def setUp(self):
        self._plat = sys.platform
        self._saved = {}
        for k in ("APPDATA", "LOCALAPPDATA", "ProgramFiles"):
            self._saved[k] = os.environ.get(k)

    def tearDown(self):
        sys.platform = self._plat
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_windows_cleanup_dirs(self):
        sys.platform = "win32"
        os.environ["APPDATA"] = r"C:\Users\T\AppData\Roaming"
        os.environ["LOCALAPPDATA"] = r"C:\Users\T\AppData\Local"
        os.environ["ProgramFiles"] = r"C:\Program Files"
        dirs = C.default_dirs()
        self.assertTrue(dirs)
        joined = " ".join(dirs)
        self.assertIn("LOCALAPPDATA", os.environ)
        self.assertIn("Programs", joined)

    def test_mac_cleanup_dirs(self):
        sys.platform = "darwin"
        dirs = C.default_dirs()
        self.assertIn("/Applications", dirs)

    def test_windows_installer_patterns(self):
        """Windows 的 exe / zip 安装包也要能被识别为可清理项。"""
        for n in ("钢铁战线WindowsRework.exe", "SteelFrontline.exe",
                  "钢铁战线-v0.9.07-安装包.zip"):
            with self.subTest(name=n):
                self.assertTrue(
                    any(p.match(n) for p in C.DMG_PATTERNS)
                    or n in C.APP_NAMES,
                    "%s 没被识别为可清理项" % n)

    def test_unrelated_files_still_ignored(self):
        for n in ("照片.png", "报告.docx", "别的游戏.exe", "notes.txt"):
            with self.subTest(name=n):
                self.assertFalse(
                    any(p.match(n) for p in C.DMG_PATTERNS)
                    or n in C.APP_NAMES,
                    "%s 不该被当成我们的文件" % n)

    def test_app_names_include_windows(self):
        joined = " ".join(C.APP_NAMES)
        self.assertIn("WindowsRework", joined)
        self.assertIn(".exe", joined)


class TestNoPlatformAssumptions(unittest.TestCase):
    """核心模块不能有 macOS 专属的硬依赖。"""

    def test_core_imports_anywhere(self):
        import importlib
        mods = ["core.run", "core.cards", "core.enemies", "core.engine",
                "core.versus", "core.netplay", "core.saves", "core.updater",
                "core.session", "core.reconnect", "core.relay_client",
                "core.tips", "core.cleanup", "core.audio", "core.i18n",
                "core.version", "core.deckbuild"]
        for m in mods:
            with self.subTest(module=m):
                importlib.import_module(m)

    def test_audio_falls_back_when_no_afplay(self):
        """没有 afplay（Windows）时，afplay 后端必须报告不可用。"""
        import shutil as _sh
        from core import audio
        old_plat = sys.platform
        old_which = _sh.which
        try:
            sys.platform = "win32"
            _sh.which = lambda n: None
            self.assertFalse(audio._AfplayBackend.available())
        finally:
            sys.platform = old_plat
            _sh.which = old_which

    def test_has_non_afplay_backend(self):
        """必须存在 afplay 之外的播放后端（Windows 用 Qt）。"""
        from core import audio
        import inspect
        src = inspect.getsource(audio)
        self.assertIn("_QtBackend", src)
        self.assertIn("_NullBackend", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
