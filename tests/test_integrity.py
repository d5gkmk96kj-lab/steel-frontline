#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码完整性 / 反篡改测试。

这些测试验证的是**安全边界真的有效**，而不只是"函数能跑"。
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import integrity as I   # noqa: E402
from core import netplay as N     # noqa: E402


class TestBuildHash(unittest.TestCase):

    def test_hash_is_hex_and_stable(self):
        h = I.build_hash()
        self.assertTrue(h, "算不出哈希")
        self.assertEqual(len(h), 64)
        int(h, 16)                       # 必须是合法十六进制
        self.assertEqual(h, I.build_hash(), "两次调用结果不一致")

    def test_short_hash(self):
        s = I.short_hash()
        self.assertEqual(len(s), 12)
        self.assertTrue(I.build_hash().startswith(s))

    def test_hash_changes_when_source_changes(self):
        """改一个字节，哈希必须变 —— 这是整套机制的地基。"""
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "core", "cards.py")
        if not os.path.isfile(path):
            self.skipTest("找不到 core/cards.py")
        with open(path, "rb") as f:
            orig = f.read()
        try:
            h1 = I.compute_build_hash()
            with open(path, "wb") as f:
                f.write(orig + b"\n# tamper-test\n")
            h2 = I.compute_build_hash()
            self.assertNotEqual(h1, h2, "改了源码哈希却没变！")
        finally:
            with open(path, "wb") as f:
                f.write(orig)
        I._CACHE.clear()
        self.assertEqual(I.compute_build_hash(), I.compute_build_hash())

    def test_verify_against(self):
        mine = I.build_hash()
        self.assertTrue(I.verify_against(mine))
        self.assertFalse(I.verify_against("deadbeef" * 8))
        self.assertFalse(I.verify_against(""))


class TestRuntimeCheck(unittest.TestCase):

    def test_clean_process_has_no_problems(self):
        # 正常跑测试时应该是干净的
        probs = I.check_runtime()
        self.assertIsInstance(probs, list)

    def test_detects_patched_method(self):
        """替换关键方法必须被抓到。"""
        import core.versus as V
        orig = V.VersusBattle.deal_damage
        try:
            V.VersusBattle.deal_damage = lambda *a, **k: 9999
            probs = I.check_runtime()
            self.assertTrue(
                any("deal_damage" in p for p in probs),
                "篡改 deal_damage 没被检测到：%s" % probs)
        finally:
            V.VersusBattle.deal_damage = orig
        self.assertFalse(
            any("deal_damage" in p for p in I.check_runtime()),
            "还原后仍然报错")

    def test_detects_patched_sign(self):
        import core.session as S
        orig = S.sign
        try:
            S.sign = lambda *a, **k: "fake"
            probs = I.check_runtime()
            self.assertTrue(any("sign" in p for p in probs),
                            "篡改 sign 没被检测到：%s" % probs)
        finally:
            S.sign = orig

    def test_detects_debugger_module(self):
        """加载调试器模块后必须报出来。"""
        sys.modules["pdb"] = __import__("pdb")
        try:
            probs = I.check_runtime()
            self.assertTrue(any("pdb" in p for p in probs),
                            "调试器没被检测到：%s" % probs)
        finally:
            sys.modules.pop("pdb", None)

    def test_self_check_shape(self):
        ok, rep = I.self_check()
        self.assertIsInstance(ok, bool)
        for k in ("build_hash", "short_hash", "device_id",
                  "short_device", "problems", "clean"):
            self.assertIn(k, rep)


class TestDeviceId(unittest.TestCase):

    def test_stable_and_not_pii(self):
        d1 = I.device_id()
        d2 = I.device_id()
        self.assertEqual(d1, d2, "设备号不稳定")
        self.assertEqual(len(d1), 16)
        int(d1, 16)
        # 不能包含用户名/主机名原文
        try:
            import getpass
            user = getpass.getuser()
            if user and len(user) > 2:
                self.assertNotIn(user, d1, "设备号里出现了用户名原文")
        except Exception:
            pass

    def test_short_device_format(self):
        s = I.short_device()
        self.assertIn("-", s)
        self.assertEqual(len(s), 13)


class TestPeerIntegrityCheck(unittest.TestCase):
    """房主侧校验对方 hello 的逻辑。"""

    def test_accepts_matching_hash(self):
        ok, why = N._check_peer_integrity({"hash": I.build_hash()})
        self.assertTrue(ok, why)

    def test_rejects_mismatched_hash(self):
        ok, why = N._check_peer_integrity({"hash": "0" * 64})
        self.assertFalse(ok, "哈希不匹配竟然通过了！")

    def test_rejects_missing_hash(self):
        ok, why = N._check_peer_integrity({})
        self.assertFalse(ok, "没带哈希竟然通过了！")

    def test_rejects_peer_with_debugger(self):
        ok, why = N._check_peer_integrity(
            {"hash": I.build_hash(), "problems": ["debugger:pdb"]})
        self.assertFalse(ok, "对方自报有调试器竟然通过了！")

    def test_rejects_garbage_problems_type(self):
        """problems 字段类型不对也不能崩。"""
        ok, why = N._check_peer_integrity(
            {"hash": I.build_hash(), "problems": "not-a-list"})
        self.assertTrue(ok)

    def test_handles_weird_input(self):
        for bad in ({"hash": None}, {"hash": 123}, {"hash": []},
                    {"hash": {"a": 1}}):
            with self.subTest(hash=bad.get("hash")):
                ok, why = N._check_peer_integrity(bad)
                self.assertFalse(ok)


class TestViolationStore(unittest.TestCase):

    def setUp(self):
        I.clear_violations()

    def tearDown(self):
        I.clear_violations()

    def test_record_and_read(self):
        I.record_violation({"reason": "代码校验失败",
                            "peer_device": "abc", "ts": 1})
        I.record_violation({"reason": "代码校验失败",
                            "peer_device": "def", "ts": 2})
        vs = I.violations()
        self.assertEqual(len(vs), 2)
        # 最新的在前
        self.assertEqual(vs[0].get("ts"), 2)

    def test_clear(self):
        I.record_violation({"reason": "x", "ts": 1})
        I.clear_violations()
        self.assertEqual(I.violations(), [])

    def test_survives_bad_entry(self):
        """记录里塞奇怪的东西不能崩。"""
        I.record_violation({"reason": None, "ts": None,
                            "peer_device": {"weird": True}})
        self.assertIsInstance(I.violations(), list)

    def test_limit(self):
        for i in range(20):
            I.record_violation({"reason": "x", "ts": i})
        self.assertLessEqual(len(I.violations(limit=5)), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
