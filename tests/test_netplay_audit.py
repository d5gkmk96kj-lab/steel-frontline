#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联机逻辑审计：锁定这轮全面检查发现的问题。"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import netplay as N  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _HostCase(unittest.TestCase):
    """起一个真 Host + 一条裸 socket 当"恶意客户端"。"""

    def setUp(self):
        self.port = _free_port()
        self.ev = []
        self.h = N.Host(on_event=lambda e: self.ev.append(e), port=self.port)
        ok = self.h.start()
        if not ok:
            self.skipTest("Host 起不来（端口被占？）")
        self.raw = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.assertTrue(self.h.wait_for_client(timeout=5))
        time.sleep(0.25)
        self.h.poll()
        self.ev.clear()

    def tearDown(self):
        for closer in (getattr(self, "raw", None), getattr(self, "h", None)):
            try:
                closer.close()
            except Exception:
                pass

    def send(self, obj):
        self.raw.sendall((json.dumps(obj) + "\n").encode())

    def send_raw(self, data: bytes):
        self.raw.sendall(data)

    def hello(self, ver=1, name="测试"):
        self.send({"t": "hello", "ver": ver, "name": name})
        time.sleep(0.3)
        self.h.poll()

    def events(self, kind=None):
        self.h.poll()
        if kind is None:
            return list(self.ev)
        return [e for e in self.ev if e.get("type") == kind]


class TestDeepNesting(_HostCase):
    """深层嵌套的 JSON 不能让接收线程崩掉。"""

    def test_deep_nesting_does_not_kill_reader(self):
        depth = 5000
        self.send_raw(b'{"t":' + b'{"a":' * depth + b'1' + b'}' * depth + b'}\n')
        time.sleep(0.8)
        self.h.poll()
        # 接收线程必须还活着
        self.assertIsNotNone(self.h._reader)
        self.assertTrue(self.h._reader.is_alive(),
                        "深层嵌套把接收线程搞崩了")
        # 而且还能正常收消息
        self.hello()
        self.assertTrue(self.events("peer"), "崩完之后收不到正常消息")

    def test_moderate_nesting_ok(self):
        depth = 50
        self.send_raw(b'{"t":' + b'{"a":' * depth + b'1' + b'}' * depth + b'}\n')
        time.sleep(0.4)
        self.h.poll()
        self.assertTrue(self.h._reader.is_alive())


class TestDeckRejection(_HostCase):
    """卡组合法性：拒绝时必须**同时**通知本地界面。"""

    def test_too_many_cards_notifies_host(self):
        self.hello()
        self.ev.clear()
        self.send({"t": "ready", "cards": ["strike"] * (N.MAX_CARDS + 1)})
        time.sleep(0.5)
        errs = self.events("error")
        self.assertTrue(errs, "房主界面收不到「卡组太大」的提示")
        self.assertIn("最多", str(errs[0].get("msg")))
        self.assertFalse(self.h._peer_ready, "非法卡组不该被接受")

    def test_unknown_card_rejected(self):
        self.hello()
        self.ev.clear()
        self.send({"t": "ready", "cards": ["fake_card"] * 5})
        time.sleep(0.5)
        errs = self.events("error")
        self.assertTrue(errs, "未知卡牌必须被拒绝且通知房主")
        self.assertFalse(self.h._peer_ready)

    def test_valid_deck_accepted(self):
        self.hello()
        self.ev.clear()
        self.send({"t": "ready", "cards": ["strike"] * 20})
        time.sleep(0.5)
        self.assertTrue(self.h._peer_ready, "正常卡组应该被接受")
        self.assertEqual(len(self.h._peer_deck), 20)


class TestCardIdValidation(unittest.TestCase):
    """卡牌 id 必须真实存在 —— 光校验格式不够。"""

    def test_real_cards_ok(self):
        for cid in ("strike", "defend", "cleave"):
            self.assertTrue(N._is_valid_card_id(cid), cid)

    def test_nonexistent_card_rejected(self):
        self.assertFalse(N._is_valid_card_id("fake_card"))
        self.assertFalse(N._is_valid_card_id("assault"))
        self.assertFalse(N._is_valid_card_id("brace"))

    def test_garbage_rejected(self):
        for bad in ("", None, 123, True, "a" * 200,
                    "strike; rm -rf /", "strike\n", "strike\x00"):
            self.assertFalse(N._is_valid_card_id(bad), repr(bad))


class TestNameSanitization(unittest.TestCase):
    """玩家名要过滤控制字符和 ANSI 转义。"""

    def test_normal(self):
        self.assertEqual(N._sanitize_name("正常名字"), "正常名字")
        self.assertEqual(N._sanitize_name("Player1"), "Player1")

    def test_null_byte_removed(self):
        out = N._sanitize_name("name\x00null")
        self.assertNotIn("\x00", out)
        self.assertEqual(out, "name null")

    def test_ansi_escape_removed(self):
        out = N._sanitize_name("\x1b[31m红色\x1b[0m")
        self.assertNotIn("\x1b", out)
        self.assertEqual(out, "红色")

    def test_osc_sequence_removed(self):
        out = N._sanitize_name("\x1b]0;title\x07x")
        self.assertNotIn("\x1b", out)

    def test_newlines_flattened(self):
        out = N._sanitize_name("A\nB\rC")
        self.assertNotIn("\n", out)
        self.assertNotIn("\r", out)

    def test_length_capped(self):
        self.assertEqual(len(N._sanitize_name("A" * 1000)), N.MAX_NAME_LEN)

    def test_empty_fallback(self):
        for bad in ("", "   ", None, 123, []):
            self.assertEqual(N._sanitize_name(bad), "玩家")

    def test_emoji_kept(self):
        self.assertIn("🎮", N._sanitize_name("🎮玩家"))


class TestProtocolMismatch(_HostCase):
    """版本不一致要明确告知本地界面。"""

    def test_wrong_version_notifies(self):
        self.ev.clear()
        self.send({"t": "hello", "ver": 999, "name": "T"})
        time.sleep(0.5)
        kinds = [e.get("type") for e in self.events()]
        self.assertIn("protocol_mismatch", kinds,
                      "协议版本不匹配必须通知本地：%s" % kinds)

    def test_correct_version_ok(self):
        self.hello(ver=N.PROTOCOL_VERSION)
        self.assertTrue(self.events("peer"))


class TestMalformedInputs(_HostCase):
    """各种畸形输入，服务器都不能崩。"""

    def test_garbage_batch(self):
        payloads = [
            b"x" * (N.MAX_LINE + 1024) + b"\n",
            b"not json\n",
            b"\n",
            b"[1,2,3]\n",
            b"null\n",
            b'"str"\n',
            b"{}\n",
            b'{"t":"play","idx":999999999999999999999}\n',
            b'{"t":"play","idx":-1}\n',
            b'{"t":"play","idx":true}\n',
            b'{"t":"play","idx":1.5}\n',
            b'{"t":null}\n',
            b'{"t":"unknown_type_xyz"}\n',
        ]
        for p in payloads:
            try:
                self.send_raw(p)
            except Exception:
                break
            time.sleep(0.08)
            self.h.poll()
        time.sleep(0.3)
        self.h.poll()
        self.assertTrue(self.h._reader.is_alive(), "畸形输入把接收线程搞崩了")


if __name__ == "__main__":
    unittest.main(verbosity=2)
