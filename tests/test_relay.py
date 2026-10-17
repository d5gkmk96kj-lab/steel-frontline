#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公网中继测试：起一个真实服务端，跑真实握手与对局。

覆盖踩过的四个坑：
  1. 客户端多包一层 -> 对方收到双层嵌套
  2. recv 空闲返回 b"" -> 被上层当成「对端断开」
  3. {"t":"pong"} 被当成中继控制消息吞掉 -> 心跳超时掉线
  4. 转发帧里 t 恰好是 ping/pong -> 同样被误吞
"""

from __future__ import annotations

import itertools
import os
import socket
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY = os.path.join(ROOT, "server", "relay.py")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class RelayCase(unittest.TestCase):
    """每个用例起一个独立的中继服务端。"""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RELAY):
            raise unittest.SkipTest("relay.py 不存在")

    def setUp(self):
        self.port = _free_port()
        env = dict(os.environ)
        env["SF_RELAY_LOG"] = ""
        self.proc = subprocess.Popen(
            [sys.executable, RELAY, "--port", str(self.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        # 等服务端起来
        for _ in range(60):
            try:
                s = socket.create_connection(("127.0.0.1", self.port), 0.2)
                s.close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            self.proc.terminate()
            self.skipTest("中继服务端没起来")
        self._old = None

    def tearDown(self):
        # 还原被改过的中继配置（否则会污染后面的测试）
        try:
            from core import relay_client as RC
            RC.DEFAULT_RELAY_HOST = ""
            RC.RELAY_HOSTS[:] = []
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _rc(self):
        from core import relay_client as RC
        self._old = (RC.DEFAULT_RELAY_HOST, RC.DEFAULT_RELAY_PORT)
        RC.DEFAULT_RELAY_HOST = "127.0.0.1"
        RC.DEFAULT_RELAY_PORT = self.port
        return RC


class TestRelayBasics(RelayCase):

    def test_config_helpers(self):
        RC = self._rc()
        self.assertTrue(RC.relay_configured())
        # relay_address() 可能带「（+N 备用）」后缀（多地址故障转移）
        self.assertIn("127.0.0.1:%d" % self.port, RC.relay_address())

    def test_create_and_join_room(self):
        RC = self._rc()
        a = RC.make_room()
        self.assertEqual(len(a.room), 4)
        self.assertTrue(a.room.isdigit())
        b = RC.join(a.room)
        self.assertEqual(b.room, a.room)
        a.close()
        b.close()

    def test_wrong_room_rejected(self):
        RC = self._rc()
        with self.assertRaises(RC.RelayError):
            RC.join("0000")

    def test_bad_room_format_rejected(self):
        RC = self._rc()
        a = RC.make_room()
        for bad in ("abc", "12", "123456", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(RC.RelayError):
                    RC.join(bad)
        a.close()

    def test_raw_passthrough(self):
        """原始行必须原样到达（不能多包一层）。"""
        RC = self._rc()
        a = RC.make_room()
        b = RC.join(a.room)
        a.sendall(b'{"t":"hello"}\n')
        time.sleep(0.6)
        got = b.recv()
        self.assertEqual(got, b'{"t":"hello"}\n',
                         "收到了被二次包装的内容：%r" % got)
        a.close()
        b.close()

    def test_pong_is_not_swallowed(self):
        """游戏心跳的 {"t":"pong"} 必须透传（之前被中继吞掉了）。"""
        RC = self._rc()
        a = RC.make_room()
        b = RC.join(a.room)
        a.sendall(b'{"t":"ping"}\n')
        time.sleep(0.5)
        self.assertEqual(b.recv(), b'{"t":"ping"}\n')
        b.sendall(b'{"t":"pong"}\n')
        time.sleep(0.5)
        self.assertEqual(a.recv(), b'{"t":"pong"}\n',
                         "pong 被中继当成控制消息吞了")
        a.close()
        b.close()


class TestNetplayOverRelay(RelayCase):

    def _deck(self, n=20):
        return list(itertools.islice(
            itertools.cycle(["strike", "defend"]), n))

    def test_full_match_over_relay(self):
        RC = self._rc()
        h, room = RC.host_via_relay()
        c, rs = RC.join_via_relay(room)
        time.sleep(1.2)
        hp = [e.get("type") for e in (h.poll() or [])]
        cp = [e.get("type") for e in (c.poll() or [])]
        self.assertIn("connected", hp)
        self.assertIn("peer", hp)
        self.assertIn("peer", cp)

        h.send_deck(self._deck())
        c.send_deck(self._deck())
        time.sleep(1.5)
        hp += [e.get("type") for e in (h.poll() or [])]
        cp += [e.get("type") for e in (c.poll() or [])]
        self.assertIn("start", hp, "房主没开局")
        self.assertIn("start", cp, "玩家没开局")
        rs.close()

    def test_idle_does_not_disconnect(self):
        """空闲时不能被判定掉线（recv 返回 b"" 的老问题）。"""
        RC = self._rc()
        h, room = RC.host_via_relay()
        c, rs = RC.join_via_relay(room)
        time.sleep(1.0)
        h.poll()
        c.poll()
        time.sleep(7.0)          # 覆盖至少一个心跳周期
        hp = [e.get("type") for e in (h.poll() or [])]
        self.assertNotIn("disconnected", hp,
                         "空闲时掉线了：%r" % hp)
        self.assertNotIn("ping_timeout", hp)
        rs.close()

    def test_peer_leave_notifies_other(self):
        RC = self._rc()
        h, room = RC.host_via_relay()
        c, rs = RC.join_via_relay(room)
        time.sleep(1.0)
        h.poll()
        rs.close()               # 玩家掉线
        time.sleep(1.5)
        hp = [e.get("type") for e in (h.poll() or [])]
        self.assertTrue(
            any(t in ("disconnected", "bye", "ping_timeout") for t in hp),
            "对方离开后房主没收到通知：%r" % hp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
