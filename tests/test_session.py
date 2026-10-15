#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联机票据（token / 签名 / 防重放）与重连测试。纯逻辑，不联网。"""

from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import session as S    # noqa: E402
from core import reconnect as R  # noqa: E402


class TestToken(unittest.TestCase):

    def test_token_uses_safe_alphabet(self):
        for _ in range(200):
            t = S.new_token()
            self.assertTrue(t)
            for c in t:
                self.assertIn(c, S.ALPHABET,
                              "房间码出现了易混字符 %r" % c)

    def test_tokens_unique(self):
        self.assertEqual(len({S.new_token() for _ in range(2000)}), 2000)

    def test_code_roundtrip(self):
        """展示码必须能还原回 token（否则念给同学就对不上）。"""
        for _ in range(500):
            t = S.new_token()
            code = S.room_code(t)
            self.assertEqual(S.normalize_code(code), t[:S.CODE_LEN])

    def test_code_matching(self):
        t = S.new_token()
        full = S.room_code(t)
        self.assertTrue(S.code_matches(t, full))
        self.assertTrue(S.code_matches(t, full.replace("-", "")))
        first_two = "-".join(full.split("-")[:2])                 # 前两组
        self.assertTrue(S.code_matches(t, first_two))
        self.assertTrue(S.code_matches(t, full.lower()))          # 小写也认
        self.assertFalse(S.code_matches(t, "ZZZZ-ZZZZ"))
        self.assertFalse(S.code_matches(t, ""))
        # 太短不接受：输一两个字符就进去等于没有保护
        self.assertFalse(S.code_matches(t, full.split("-")[0]))
        self.assertFalse(S.code_matches(t, "2345"))
        self.assertFalse(S.code_matches(t, t[:S.MIN_CODE_LEN - 1]))

    def test_min_length_boundary(self):
        t = S.new_token()
        self.assertTrue(S.code_matches(t, t[:S.MIN_CODE_LEN]))
        self.assertFalse(S.code_matches(t, t[:S.MIN_CODE_LEN - 1]))

    def test_room_code_format(self):
        code = S.room_code(S.new_token())
        parts = code.split("-")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertEqual(len(p), 4)


class TestSignature(unittest.TestCase):

    def setUp(self):
        self.t = S.new_token()
        self.tk = S.Ticket(token=self.t, require_code=True)
        self.msg = {"t": "play", "idx": 2, "target": 0}

    def test_valid_roundtrip(self):
        w = S.wrap(self.tk, self.msg, seq=1)
        ok, why = S.unwrap(self.tk, dict(w))
        self.assertTrue(ok, why)

    def test_unwrap_strips_meta(self):
        """校验后必须把 _s/_t/_g 去掉，业务层拿到干净消息。"""
        w = S.wrap(self.tk, self.msg, seq=1)
        S.unwrap(self.tk, w)
        for k in ("_s", "_t", "_g"):
            self.assertNotIn(k, w)

    def test_tamper_detected(self):
        w = S.wrap(self.tk, self.msg, seq=1)
        w["idx"] = 99
        ok, why = S.unwrap(self.tk, dict(w))
        self.assertFalse(ok, "改了内容竟然通过了校验")

    def test_replay_detected(self):
        w = S.wrap(self.tk, self.msg, seq=1)
        self.assertTrue(S.unwrap(self.tk, dict(w))[0])
        ok, why = S.unwrap(self.tk, dict(w))
        self.assertFalse(ok, "重放同一条消息竟然通过了")

    def test_wrong_token_rejected(self):
        w = S.wrap(self.tk, self.msg, seq=1)
        other = S.Ticket(token=S.new_token(), require_code=True)
        self.assertFalse(S.unwrap(other, dict(w))[0])

    def test_expired_signature_rejected(self):
        old = time.time() - (S.SIG_WINDOW + 60)
        sig = S.sign(self.t, self.msg, 5, old)
        self.assertFalse(S.verify(self.t, self.msg, 5, old, sig))

    def test_no_signature_rejected_when_required(self):
        tk = S.Ticket(token=self.t, require_code=True)
        ok, why = S.unwrap(tk, {"t": "play", "idx": 0})
        self.assertFalse(ok)

    def test_no_signature_allowed_when_not_required(self):
        """局域网默认模式：没开房间码时，老客户端还能连。"""
        tk = S.Ticket(token=self.t, require_code=False)
        ok, why = S.unwrap(tk, {"t": "play", "idx": 0})
        self.assertTrue(ok, why)

    def test_ticket_expiry(self):
        tk = S.Ticket(token=self.t, ttl=0.05)
        self.assertFalse(tk.expired())
        time.sleep(0.1)
        self.assertTrue(tk.expired())
        self.assertEqual(tk.remaining(), 0.0)

    def test_ticket_serialisation(self):
        tk = S.Ticket(token=self.t, host_name="房主", require_code=True)
        back = S.Ticket.from_dict(tk.to_dict())
        self.assertEqual(back.token, tk.token)
        self.assertEqual(back.require_code, tk.require_code)
        self.assertTrue(S.Ticket.from_dict({}).token == "")

    def test_expired_ticket_rejects_message(self):
        tk = S.Ticket(token=self.t, ttl=0.05, require_code=True)
        time.sleep(0.1)
        w = S.wrap(S.Ticket(token=self.t), self.msg, seq=1)  # 用新票据签
        ok, why = S.unwrap(tk, dict(w))
        self.assertFalse(ok)

    def test_signature_is_deterministic(self):
        a = S.sign(self.t, self.msg, 1, 1000)
        b = S.sign(self.t, self.msg, 1, 1000)
        self.assertEqual(a, b)

    def test_signature_changes_with_content(self):
        a = S.sign(self.t, {"x": 1}, 1, 1000)
        b = S.sign(self.t, {"x": 2}, 1, 1000)
        self.assertNotEqual(a, b)


class TestReconnect(unittest.TestCase):

    def test_backoff_grows_and_caps(self):
        d = [R.retry_delay(i) for i in range(10)]
        self.assertTrue(all(x > 0 for x in d))
        self.assertLessEqual(max(d), 8.0)
        self.assertLessEqual(d[0], d[-1])

    def test_window_open_and_expire(self):
        st = R.ReconnectState()
        self.assertFalse(st.is_open())
        st.open(grace=0.2, reason="x")
        self.assertTrue(st.is_open())
        time.sleep(0.3)
        self.assertFalse(st.is_open())

    def test_resume_success(self):
        tries = {"n": 0}
        done = {}

        def attempt():
            tries["n"] += 1
            return tries["n"] >= 2

        rc = R.Reconnector(attempt,
                           lambda ok, m: done.update(ok=ok, msg=m),
                           budget=5)
        rc.start()
        for _ in range(80):
            if done:
                break
            time.sleep(0.05)
        self.assertTrue(done.get("ok"))
        self.assertGreaterEqual(tries["n"], 2)

    def test_timeout(self):
        done = {}
        rc = R.Reconnector(lambda: False,
                           lambda ok, m: done.update(ok=ok, msg=m),
                           budget=1.0)
        rc.start()
        for _ in range(80):
            if done:
                break
            time.sleep(0.05)
        self.assertIn("ok", done)
        self.assertFalse(done["ok"])

    def test_cancel(self):
        done = {}
        rc = R.Reconnector(lambda: False,
                           lambda ok, m: done.update(ok=ok),
                           budget=30)
        rc.start()
        time.sleep(0.2)
        rc.cancel()
        for _ in range(40):
            if done:
                break
            time.sleep(0.05)
        self.assertIn("ok", done)
        self.assertFalse(done["ok"])

    def test_attempt_exception_does_not_crash(self):
        """attempt 抛异常时应该继续重试，而不是把线程搞崩。"""
        done = {}

        def boom():
            raise RuntimeError("网络炸了")

        rc = R.Reconnector(boom, lambda ok, m: done.update(ok=ok), budget=1.0)
        rc.start()
        for _ in range(80):
            if done:
                break
            time.sleep(0.05)
        self.assertIn("ok", done)
        self.assertFalse(done["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
