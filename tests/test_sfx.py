#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音效系统回归测试（音效是程序化生成的，不依赖任何外部素材）。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import sfx_gen as G   # noqa: E402


class TestSfxGeneration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_sfx_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_expected_sounds_exist(self):
        need = {"card", "hit", "block", "crit", "kill",
                "victory", "defeat", "click", "potion", "turn"}
        self.assertTrue(need <= set(G.GENERATORS))

    def test_generates_valid_wav(self):
        got = G.generate_all(self.tmp)
        self.assertGreaterEqual(len(got), 8, "音效数量太少")
        for name, path in got.items():
            with self.subTest(name=name):
                self.assertTrue(os.path.isfile(path))
                with wave.open(path, "rb") as w:
                    self.assertEqual(w.getnchannels(), 1)
                    self.assertEqual(w.getsampwidth(), 2)
                    self.assertGreater(w.getnframes(), 100,
                                       "%s 太短了" % name)

    def test_deterministic(self):
        """同样的代码必须生成同样的字节（便于复现 / 打包稳定）。"""
        a = G.generate_all(os.path.join(self.tmp, "a"))
        b = G.generate_all(os.path.join(self.tmp, "b"))
        for name in a:
            with self.subTest(name=name):
                da = open(a[name], "rb").read()
                db = open(b[name], "rb").read()
                self.assertEqual(da, db, "%s 两次生成不一致" % name)

    def test_samples_not_silent(self):
        for name, fn in G.GENERATORS.items():
            with self.subTest(name=name):
                buf = fn()
                self.assertGreater(len(buf), 100)
                peak = max(abs(v) for v in buf)
                self.assertGreater(peak, 0.05, "%s 几乎没声音" % name)
                self.assertLessEqual(peak, 1.0, "%s 会削波" % name)

    def test_small_files(self):
        """合成的音效要足够小，不能把安装包撑大。"""
        got = G.generate_all(self.tmp)
        total = sum(os.path.getsize(p) for p in got.values())
        self.assertLess(total, 1024 * 1024, "音效总大小超过 1MB")

    def test_ensure_sfx_files(self):
        got = G.ensure_sfx_files(self.tmp)
        self.assertTrue(got)
        # 二次调用不重复生成
        self.assertEqual(got, G.ensure_sfx_files(self.tmp))


class TestSfxPlayback(unittest.TestCase):

    def test_play_is_safe_without_backend(self):
        """没有 Qt/音频设备时 play() 必须静默失败，绝不抛异常。"""
        from core import sfx
        try:
            sfx.play("definitely_not_a_sound")
        except Exception as exc:      # pragma: no cover
            self.fail("play() 不该抛异常: %r" % exc)

    def test_toggle_enabled(self):
        from core import sfx
        sfx.set_enabled(False)
        self.assertFalse(sfx.is_enabled())
        self.assertFalse(sfx.play("hit"), "关掉后不该播")
        sfx.set_enabled(True)
        self.assertTrue(sfx.is_enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
