#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反外挂加强层测试：快照校验 / 速率检测 / 持续校验。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import integrity as I  # noqa: E402
from core import netplay as N  # noqa: E402


class TestSnapshotSanity(unittest.TestCase):
    """快照里的血量/护甲/能量必须在合理范围内。"""

    def test_normal_snapshot_clean(self):
        snap = {"me": {"hp": 75, "block": 12, "energy": 3},
                "opponent": {"hp": 60, "block": 0}}
        self.assertEqual(N._snapshot_sane(snap), [])

    def test_absurd_hp_flagged(self):
        bad = N._snapshot_sane({"me": {"hp": 99999}})
        self.assertTrue(bad, "超大血量应该被标记")

    def test_absurd_block_flagged(self):
        bad = N._snapshot_sane({"opponent": {"block": 9999}})
        self.assertTrue(bad, "超大掩体应该被标记")

    def test_absurd_energy_flagged(self):
        bad = N._snapshot_sane({"me": {"energy": 999}})
        self.assertTrue(bad, "超大补给应该被标记")

    def test_negative_hp_flagged(self):
        bad = N._snapshot_sane({"me": {"hp": -99}})
        self.assertTrue(bad, "负血量应该被标记")

    def test_huge_hand_flagged(self):
        bad = N._snapshot_sane({"my_hand": [{}] * 50})
        self.assertTrue(bad, "手牌超过 30 张应该被标记")

    def test_bad_type_flagged(self):
        bad = N._snapshot_sane({"me": {"hp": "lots"}})
        self.assertTrue(bad, "血量类型不对应该被标记")

    def test_garbage_input_safe(self):
        for bad_in in (None, [], "x", 42):
            with self.subTest(v=bad_in):
                out = N._snapshot_sane(bad_in)
                self.assertIsInstance(out, list)

    def test_missing_fields_ok(self):
        self.assertEqual(N._snapshot_sane({}), [])
        self.assertEqual(N._snapshot_sane({"me": {}}), [])


class TestRuntimeChecks(unittest.TestCase):

    def test_clean_env_passes(self):
        probs = I.check_runtime()
        self.assertIsInstance(probs, list)

    def test_trace_hook_detected(self):
        old = sys.gettrace()
        try:
            sys.settrace(lambda *a: None)
            probs = I.check_runtime()
            self.assertTrue(any("trace" in p for p in probs),
                            "装了 trace 钩子应该被发现：%s" % probs)
        finally:
            sys.settrace(old)

    def test_profile_hook_detected(self):
        old = sys.getprofile()
        try:
            sys.setprofile(lambda *a: None)
            probs = I.check_runtime()
            self.assertTrue(any("profile" in p for p in probs),
                            "装了 profile 钩子应该被发现：%s" % probs)
        finally:
            sys.setprofile(old)

    def test_excepthook_detected(self):
        old = sys.excepthook
        try:
            sys.excepthook = lambda *a: None
            probs = I.check_runtime()
            self.assertTrue(any("excepthook" in p for p in probs))
        finally:
            sys.excepthook = old

    def test_benign_modules_not_flagged(self):
        """ctypes 这类正常依赖不能误判。"""
        self.assertIn("ctypes", I._BENIGN_MODULES)

    def test_suspicious_list_expanded(self):
        for name in ("frida", "cheatengine", "pydevd", "debugpy"):
            self.assertIn(name, I.SUSPICIOUS_MODULES,
                          "%s 应该在可疑列表里" % name)


class TestRateLimit(unittest.TestCase):

    def test_normal_rate_ok(self):
        c = N._Conn()
        for _ in range(5):
            self.assertTrue(c._rate_ok())

    def test_burst_rejected(self):
        c = N._Conn()
        results = [c._rate_ok() for _ in range(30)]
        self.assertFalse(all(results), "连续 30 次请求应该被拦下来")
        self.assertIn(False, results)

    def test_rate_window_resets(self):
        """每秒窗口应该自动重置（不能永久封死）。"""
        import time
        c = N._Conn()
        for _ in range(20):
            c._rate_ok()
        time.sleep(1.1)
        self.assertTrue(c._rate_ok(), "过了 1 秒应该恢复正常")


class TestConstants(unittest.TestCase):

    def test_limits_reasonable(self):
        self.assertGreater(N.MAX_INTENT_PER_SEC, 5)
        self.assertLess(N.MAX_INTENT_PER_SEC, 100)
        self.assertGreater(N.REVERIFY_INTERVAL, 0)

    def test_sane_caps(self):
        self.assertGreater(N.SANE_LIMITS["hp"], 75)
        self.assertLess(N.SANE_LIMITS["hp"], 100000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
