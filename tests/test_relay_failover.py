#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中继多地址故障转移测试（不需要真服务器）。"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import relay_client as RC  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class FailoverCase(unittest.TestCase):

    def setUp(self):
        self._old = os.environ.get("SF_RELAY_HOSTS")
        self._srv = None

    def _all_clear(self):
        """把所有配置来源都清干净（环境变量 + 模块变量）。

        别的测试可能设置过 SF_RELAY_HOSTS / DEFAULT_RELAY_HOST，
        不一起清掉就测不出"真的没配置"。
        """
        os.environ.pop("SF_RELAY_HOSTS", None)
        os.environ.pop("SF_RELAY_HOST", None)
        old_mod = RC.DEFAULT_RELAY_HOST
        old_list = list(RC.RELAY_HOSTS)
        RC.DEFAULT_RELAY_HOST = ""
        RC.RELAY_HOSTS[:] = []

        def restore():
            RC.DEFAULT_RELAY_HOST = old_mod
            RC.RELAY_HOSTS[:] = old_list
        return restore

    def tearDown(self):
        if self._old is None:
            os.environ.pop("SF_RELAY_HOSTS", None)
        else:
            os.environ["SF_RELAY_HOSTS"] = self._old
        self._stop()

    def _start(self, port: int):
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(4)
        self._srv = srv

        def loop():
            try:
                while True:
                    c, _ = srv.accept()
                    try:
                        c.close()
                    except Exception:
                        pass
            except Exception:
                pass

        threading.Thread(target=loop, daemon=True).start()
        time.sleep(0.15)

    def _stop(self):
        if self._srv is not None:
            try:
                self._srv.close()
            except Exception:
                pass
            self._srv = None


class TestParsing(FailoverCase):

    def test_empty_config(self):
        restore = self._all_clear()
        try:
            self.assertEqual(RC.relay_endpoints(), [])
            self.assertFalse(RC.relay_configured())
            self.assertEqual(RC.relay_address(), "")
        finally:
            restore()

    def test_single_host_with_port(self):
        os.environ["SF_RELAY_HOSTS"] = "1.2.3.4:9000"
        self.assertEqual(RC.relay_endpoints(), [("1.2.3.4", 9000)])

    def test_host_without_port_uses_default(self):
        os.environ["SF_RELAY_HOSTS"] = "example.com"
        eps = RC.relay_endpoints()
        self.assertEqual(eps, [("example.com", RC.DEFAULT_RELAY_PORT)])

    def test_multiple_hosts_order_preserved(self):
        os.environ["SF_RELAY_HOSTS"] = "hk.test:9000,us.test:9001"
        self.assertEqual(RC.relay_endpoints(),
                         [("hk.test", 9000), ("us.test", 9001)])

    def test_bad_entries_skipped(self):
        os.environ["SF_RELAY_HOSTS"] = " , ,a.test:9000, ,"
        eps = RC.relay_endpoints()
        self.assertEqual(eps, [("a.test", 9000)])

    def test_address_shows_backup_count(self):
        os.environ["SF_RELAY_HOSTS"] = "a.test:1,b.test:2,c.test:3"
        text = RC.relay_address()
        self.assertIn("a.test", text)
        self.assertIn("+2", text, "应显示还有 2 台备用")


class TestFailover(FailoverCase):

    def test_connects_to_first_when_alive(self):
        p1 = _free_port()
        self._start(p1)
        os.environ["SF_RELAY_HOSTS"] = "127.0.0.1:%d,127.0.0.1:%d" % (p1, _free_port())
        rs = RC.connect_any()
        try:
            self.assertEqual(rs.port, p1, "第一台活着就该连第一台")
        finally:
            rs.close()

    def test_falls_back_to_second(self):
        """第一台挂了 -> 自动连第二台。"""
        p1 = _free_port()          # 不起服务
        p2 = _free_port()
        self._start(p2)
        os.environ["SF_RELAY_HOSTS"] = "127.0.0.1:%d,127.0.0.1:%d" % (p1, p2)
        rs = RC.connect_any()
        try:
            self.assertEqual(rs.port, p2, "第一台挂了应该自动切到第二台")
        finally:
            rs.close()

    def test_all_down_raises_with_reasons(self):
        p1, p2 = _free_port(), _free_port()
        os.environ["SF_RELAY_HOSTS"] = "127.0.0.1:%d,127.0.0.1:%d" % (p1, p2)
        with self.assertRaises(RC.RelayError) as ctx:
            RC.connect_any()
        msg = str(ctx.exception)
        self.assertIn("都连不上", msg)
        self.assertIn(str(p1), msg, "错误信息应包含每台的地址")
        self.assertIn(str(p2), msg)

    def test_not_configured_raises(self):
        restore = self._all_clear()
        try:
            with self.assertRaises(RC.RelayError):
                RC.connect_any()
        finally:
            restore()

    def test_explicit_host_bypasses_list(self):
        """显式给地址时只连那一台，不走列表。"""
        p1, p2 = _free_port(), _free_port()
        self._start(p2)
        os.environ["SF_RELAY_HOSTS"] = "127.0.0.1:%d" % p1   # p1 是死的
        rs = RC._connect_with_failover("127.0.0.1", p2)
        try:
            self.assertEqual(rs.port, p2)
        finally:
            rs.close()


class TestDefaults(unittest.TestCase):

    def test_relay_hosts_is_list(self):
        self.assertIsInstance(RC.RELAY_HOSTS, list)

    def test_public_api(self):
        for name in ("relay_endpoints", "connect_any", "relay_configured",
                     "relay_address"):
            self.assertTrue(hasattr(RC, name), "缺少 %s" % name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
