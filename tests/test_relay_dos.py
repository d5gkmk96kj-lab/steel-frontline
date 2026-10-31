#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中继服务器抗 DoS 测试。

覆盖两件真踩过的事：

1. **连接洪水把玩家挡在门外**：容量满了以后如果直接拒绝新连接，
   攻击者只要占满 MAX_CONNS，服务器看起来活着但谁也进不来。
   正确做法是踢掉最老的**空闲**连接（不在房间、不在队列）。
2. **匹配限速误伤**：原先 5 次/分钟，对同一 WiFi 下共用出口 IP
   的几个人来说太紧。
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY = os.path.join(ROOT, "server", "relay.py")


def _load_relay():
    spec = importlib.util.spec_from_file_location("relay_dos_test", RELAY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipUnless(os.path.isfile(RELAY), "relay.py 不存在")
class TestRelayDOS(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 这些环境变量必须在 import relay 之前设好
        os.environ["SF_RELAY_MAX_CONNS"] = "40"          # 方便测满
        os.environ["SF_RELAY_MAX_CONNS_PER_IP"] = "5000"
        os.environ["SF_RELAY_MAX_MATCH_PER_MIN"] = "1000"
        os.environ["SF_RELAY_LOG"] = ""
        cls.RM = _load_relay()
        cls.port = _free_port()
        cls.relay = cls.RM.Relay(cls.port)
        cls.thread = threading.Thread(
            target=cls.relay.serve_forever, daemon=True)
        cls.thread.start()
        for _ in range(80):
            try:
                s = socket.create_connection(("127.0.0.1", cls.port), 0.2)
                s.close()
                return
            except OSError:
                time.sleep(0.05)
        raise unittest.SkipTest("中继没起来")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.relay.stop()
        except Exception:
            pass

    def _probe(self) -> bool:
        """用 quick_match 探测服务是否可用（不受 host 限速影响）。"""
        try:
            s = socket.create_connection(("127.0.0.1", self.port), 3)
            s.settimeout(3)
            s.sendall(b'{"t":"quick_match"}\n')
            d = s.recv(300)
            s.sendall(b'{"t":"cancel_match"}\n')
            s.close()
            return b"queued" in d or b"error" in d
        except Exception:
            return False

    def test_fill_to_capacity_then_new_player_still_served(self):
        """占满容量后，正常玩家仍然能被服务（靠驱逐空闲连接）。"""
        maxc = self.RM.MAX_CONNS
        socks = []
        try:
            for _ in range(maxc + 20):
                try:
                    socks.append(
                        socket.create_connection(("127.0.0.1", self.port), 2))
                except OSError:
                    break
            self.assertGreaterEqual(len(socks), maxc,
                                    "应能建立至少 MAX_CONNS 个连接")
            time.sleep(0.5)
            self.assertTrue(self._probe(),
                            "连接被占满后正常玩家被挡住了（DoS 漏洞）")
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
            time.sleep(1.0)

    def test_recovers_after_flood(self):
        """洪水释放后要能恢复。"""
        socks = []
        try:
            for _ in range(self.RM.MAX_CONNS + 20):
                try:
                    socks.append(
                        socket.create_connection(("127.0.0.1", self.port), 2))
                except OSError:
                    break
            time.sleep(0.4)
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
        deadline = time.time() + 8
        while time.time() < deadline:
            if self._probe():
                return
            time.sleep(0.4)
        self.fail("洪水释放后服务器没有恢复")

    def test_evict_never_kills_room_or_queue(self):
        """驱逐只能动空闲连接，不能动房间里的 / 排队中的。"""
        # 造一个排队中的连接
        q = socket.create_connection(("127.0.0.1", self.port), 3)
        try:
            q.sendall(b'{"t":"quick_match"}\n')
            q.settimeout(3)
            self.assertIn(b"queued", q.recv(300))
            # 触发驱逐：先塞满
            socks = []
            for _ in range(self.RM.MAX_CONNS + 5):
                try:
                    socks.append(
                        socket.create_connection(("127.0.0.1", self.port), 2))
                except OSError:
                    break
            time.sleep(0.6)
            # 队列里的连接必须还活着：cancel 应该能得到响应
            q.sendall(b'{"t":"cancel_match"}\n')
            q.settimeout(3)
            d = q.recv(300)
            self.assertTrue(d, "排队中的连接被驱逐误杀了")
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
        finally:
            try:
                q.close()
            except OSError:
                pass
            time.sleep(1.0)


class TestRateLimits(unittest.TestCase):

    def test_match_limit_is_not_too_tight(self):
        """5 次/分钟对共用出口 IP 的小团体太紧，至少放宽到 10。"""
        os.environ.pop("SF_RELAY_MAX_MATCH_PER_MIN", None)
        if not os.path.isfile(RELAY):
            self.skipTest("relay.py 不存在")
        RM = _load_relay()
        self.assertGreaterEqual(
            RM.MAX_MATCH_PER_MIN, 10,
            "每分钟匹配上限太低，同一 WiFi 下几个人会被误伤")

    def test_conn_limit_reasonable(self):
        if not os.path.isfile(RELAY):
            self.skipTest("relay.py 不存在")
        RM = _load_relay()
        self.assertGreaterEqual(RM.MAX_CONNS, 100, "全局连接上限太小")
        self.assertLessEqual(RM.MAX_CONNS, 5000, "全局连接上限太大")


if __name__ == "__main__":
    unittest.main(verbosity=2)
