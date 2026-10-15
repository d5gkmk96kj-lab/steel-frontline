#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""房间码端到端：正确码能进、错误码被挡、无码模式向后兼容。

回归背景：原本「connected」在 TCP accept 的瞬间就发了，
所以输错房间码的人虽然会被踢，本地却已经切到卡组界面 ——
界面与实际状态不一致。现在改为**鉴权通过后才宣告连上**。
"""

from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import netplay as N  # noqa: E402


def _deck(n=20):
    import itertools
    return list(itertools.islice(
        itertools.cycle(["strike", "defend", "assault", "brace"]), n))


class TokenCase(unittest.TestCase):

    def setUp(self):
        self._cleanup = []

    def tearDown(self):
        for o in self._cleanup:
            try:
                o.close()
            except Exception:
                pass

    def _pair(self, host_token=None, require=False, client_token=None):
        hev, cev = [], []
        h = N.Host(on_event=hev.append, port=0, name="房主",
                   token=host_token, require_code=require)
        self._cleanup.append(h)
        self.assertTrue(h.start())
        c = N.Client(on_event=cev.append, name="挑战者",
                     token=client_token)
        self._cleanup.append(c)
        c.connect("127.0.0.1", h.port)
        return h, c, hev, cev


class TestRoomCode(TokenCase):

    def test_correct_code_connects_both_sides(self):
        h, c, hev, cev = self._pair("ABCD2345EFGH", True, "ABCD2345EFGH")
        time.sleep(1.0)
        self.assertIn("connected", [e.get("type") for e in hev])
        self.assertIn("connected", [e.get("type") for e in cev])

    def test_wrong_code_rejected_both_sides(self):
        h, c, hev, cev = self._pair("ABCD2345EFGH", True, "WRONGWRONG12")
        time.sleep(1.8)
        htypes = [e.get("type") for e in hev]
        ctypes = [e.get("type") for e in cev]
        self.assertNotIn("connected", htypes,
                         "房主不该把错误码的人当成连上")
        self.assertNotIn("connected", ctypes,
                         "客户端不该以为连上了（界面会切错）")
        self.assertIn("security", htypes)
        self.assertIn("disconnected", htypes)

    def test_correct_code_can_start_match(self):
        h, c, hev, cev = self._pair("ABCD2345EFGH", True, "ABCD2345EFGH")
        time.sleep(0.8)
        h.send_deck(_deck())
        c.send_deck(_deck())
        time.sleep(1.2)
        self.assertTrue(any(e.get("type") == "start" for e in hev))
        self.assertTrue(any(e.get("type") == "start" for e in cev))

    def test_wrong_code_cannot_start_match(self):
        h, c, hev, cev = self._pair("ABCD2345EFGH", True, "NOPE1234NOPE")
        time.sleep(1.5)
        h.send_deck(_deck())
        c.send_deck(_deck())
        time.sleep(1.5)
        self.assertFalse(any(e.get("type") == "start" for e in hev),
                         "错误码竟然开局了")

    def test_lan_default_without_code_still_works(self):
        """局域网默认模式：不开房间码时，不带码的老客户端照样能连。"""
        h, c, hev, cev = self._pair(None, False, None)
        time.sleep(0.8)
        self.assertIn("connected", [e.get("type") for e in hev])
        self.assertIn("connected", [e.get("type") for e in cev])
        h.send_deck(_deck())
        c.send_deck(_deck())
        time.sleep(1.2)
        self.assertTrue(any(e.get("type") == "start" for e in hev))

    def test_partial_code_accepted(self):
        """只念前几组也应该能进（房主展示的是短码）。"""
        h, c, hev, cev = self._pair("ABCD2345EFGH", True, "ABCD-2345")
        time.sleep(1.0)
        self.assertIn("connected", [e.get("type") for e in hev])
        self.assertIn("connected", [e.get("type") for e in cev])

    def test_host_exposes_display_code(self):
        h = N.Host(on_event=[].append, port=0, name="房主",
                   token="ABCD2345EFGH", require_code=True)
        self._cleanup.append(h)
        self.assertEqual(h._ticket.display(), "ABCD-2345-EFGH")

    def test_host_autogenerates_code_when_absent(self):
        h = N.Host(on_event=[].append, port=0, name="房主")
        self._cleanup.append(h)
        self.assertTrue(h._ticket is not None)
        self.assertTrue(h._ticket.token)
        self.assertTrue(h._ticket.display())


if __name__ == "__main__":
    unittest.main(verbosity=2)
