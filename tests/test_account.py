#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账号系统测试：设备锁定 / 恢复码 / 离线优先 / 头衔 / 战绩。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import account as A  # noqa: E402


class AccountCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_acct_")
        self._old = os.environ.get("SF_GAME_HOME")
        os.environ["SF_GAME_HOME"] = self.tmp

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SF_GAME_HOME", None)
        else:
            os.environ["SF_GAME_HOME"] = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_device(self, dev: str) -> None:
        """把存档里的设备改成别的（模拟换机器）。"""
        d = json.load(open(A.account_path(), encoding="utf-8"))
        d["device"] = dev
        with open(A.account_path(), "w", encoding="utf-8") as f:
            json.dump(d, f)


class TestRegister(AccountCase):

    def test_first_register_ok(self):
        ok, code, acc = A.register("凯文")
        self.assertTrue(ok, code)
        self.assertIsNotNone(acc)
        self.assertEqual(acc.name, "凯文")
        self.assertRegex(code, r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

    def test_one_account_per_device(self):
        A.register("第一个")
        ok, msg, _ = A.register("第二个")
        self.assertFalse(ok, "同一设备竟然能注册两个账号")
        self.assertIn("已经注册", msg)

    def test_name_validation(self):
        for bad in ("", "   ", "x" * 20, "a\nb"):
            with self.subTest(name=bad):
                ok, msg, _ = A.register(bad)
                self.assertFalse(ok, "非法名字被接受了：%r" % bad)

    def test_password_is_hashed_not_stored(self):
        A.register("有密码", "hunter2")
        raw = open(A.account_path(), encoding="utf-8").read()
        self.assertNotIn("hunter2", raw, "密码明文落盘了！")
        self.assertIn("pwd_hash", raw)

    def test_recovery_code_not_stored_plain(self):
        ok, code, _ = A.register("x")
        raw = open(A.account_path(), encoding="utf-8").read()
        self.assertNotIn(code, raw, "恢复码明文落盘了！")


class TestLogin(AccountCase):

    def test_auto_login_without_password(self):
        A.register("无密码")
        self.assertIsNotNone(A.auto_login(), "无密码时应该自动进入")

    def test_auto_login_blocked_by_password(self):
        A.register("有密码", "pw")
        self.assertIsNone(A.auto_login(), "有密码时不该自动进入")

    def test_login_wrong_password(self):
        A.register("有密码", "pw")
        ok, msg, _ = A.login("wrong")
        self.assertFalse(ok)

    def test_login_correct(self):
        A.register("有密码", "pw")
        ok, msg, acc = A.login("pw")
        self.assertTrue(ok, msg)
        self.assertEqual(acc.name, "有密码")

    def test_device_mismatch_rejected(self):
        A.register("我的账号", "pw")
        self._fake_device("some-other-device")
        ok, msg, _ = A.login("pw")
        self.assertFalse(ok)
        self.assertIn("恢复码", msg, "应该提示用恢复码迁移")


class TestRecovery(AccountCase):

    def test_restore_moves_account(self):
        ok, code, _ = A.register("要迁移的", "pw")
        self.assertTrue(ok)
        self._fake_device("new-machine-9999")
        # 换设备后登录被拒
        self.assertFalse(A.login("pw")[0])
        # 用恢复码迁移
        ok2, newcode, acc = A.restore_with_code(code, "pw")
        self.assertTrue(ok2, newcode)
        self.assertEqual(A.load().device, A.current_device())
        self.assertTrue(A.login("pw")[0], "迁移后应该能登录")

    def test_old_code_invalidated(self):
        ok, code, _ = A.register("x")
        ok2, newcode, _ = A.restore_with_code(code)
        self.assertTrue(ok2)
        self.assertNotEqual(code, newcode)
        self.assertFalse(A.load().check_recovery(code),
                         "旧恢复码应该作废")
        self.assertTrue(A.load().check_recovery(newcode))

    def test_wrong_recovery_rejected(self):
        A.register("x")
        ok, msg, _ = A.restore_with_code("AAAA-BBBB-CCCC")
        self.assertFalse(ok)

    def test_recovery_normalization(self):
        a = A.normalize_recovery("abcd-efgh")
        b = A.normalize_recovery("ABCDEFGH")
        self.assertEqual(a, b, "大小写/横线应该等价")


class TestStats(AccountCase):

    def test_ai_versus_not_counted(self):
        """用户明确要求：AI 1v1 不计入战绩。"""
        A.register("x")
        before = dict(A.load().stats)
        ok, msg = A.record_result("ai_versus", True)
        self.assertFalse(ok)
        self.assertEqual(A.load().stats, before, "AI 对战竟然计入战绩了")

    def test_campaign_counted(self):
        A.register("x")
        A.record_result("campaign", True, score=500)
        st = A.load().stats
        self.assertEqual(st["runs"], 1)
        self.assertEqual(st["wins"], 1)
        self.assertEqual(st["best_score"], 500)

    def test_versus_counted_separately(self):
        A.register("x")
        A.record_result("versus", True)
        A.record_result("versus", False)
        st = A.load().stats
        self.assertEqual(st["versus"], 2)
        self.assertEqual(st["versus_wins"], 1)
        self.assertEqual(st["runs"], 0, "联机不该算进战役局数")


class TestTitles(AccountCase):

    def test_author_title_requires_author_device(self):
        A.register("普通人")
        ok, msg = A.set_title(A.TITLE_AUTHOR)
        self.assertFalse(ok, "非作者设备竟然拿到了「作者大帝」")
        self.assertIn("作者", msg)

    def test_tester_available(self):
        A.register("x")
        ok, msg = A.set_title(A.TITLE_TESTER)
        self.assertTrue(ok, msg)
        self.assertEqual(A.load().display(), "测试玩家 x")

    def test_veteran_needs_runs(self):
        A.register("x")
        ok, msg = A.set_title(A.TITLE_VETERAN)
        self.assertFalse(ok, "局数不够竟然拿到了「老玩家」")
        for _ in range(A.VETERAN_RUNS):
            A.record_result("campaign", False)
        ok2, msg2 = A.set_title(A.TITLE_VETERAN)
        self.assertTrue(ok2, msg2)

    def test_author_device_claim_is_one_shot(self):
        A.register("x")
        ok, msg = A.claim_author_device()
        # 第一次可能成功（本机还没登记过），第二次必须失败
        ok2, msg2 = A.claim_author_device()
        self.assertFalse(ok2, "作者设备竟然能被登记两次")

    def test_available_titles_shape(self):
        A.register("x")
        ts = A.available_titles()
        self.assertIn(A.TITLE_NONE, ts)
        self.assertIn(A.TITLE_TESTER, ts)
        self.assertIn(A.TITLE_VETERAN, ts)

    def test_display_with_title(self):
        A.register("凯文")
        A.set_title(A.TITLE_TESTER)
        self.assertEqual(A.load().display(), "测试玩家 凯文")


class TestSync(AccountCase):

    def test_payload_has_no_secrets(self):
        """上报给服务器的内容不能包含密码或恢复码。"""
        ok, code, _ = A.register("x", "supersecret")
        A.set_title(A.TITLE_TESTER)
        p = A.sync_payload()
        self.assertIsNotNone(p)
        blob = json.dumps(p, ensure_ascii=False)
        self.assertNotIn("supersecret", blob)
        self.assertNotIn(code, blob)
        self.assertNotIn("pwd_hash", blob)
        self.assertIn("hash", p)
        self.assertIn("device", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
