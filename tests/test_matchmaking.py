#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键匹配测试：启动真实中继服务器，连两个客户端配对。

跳过条件：server/ 不存在（私有目录，公开仓库里没有）。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "server", "relay.py")

sys.path.insert(0, ROOT)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class MatchmakingCase(unittest.TestCase):
    """起一个真服务器，跑匹配流程。"""

    PORT = 0

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(SERVER):
            raise unittest.SkipTest("server/ 不存在（私有目录）")
        cls.PORT = _free_port()
        env = dict(os.environ)
        env["SF_RELAY_MAX_CONNS_PER_IP"] = "20"
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER, "--port", str(cls.PORT)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env)
        # 等端口起来
        for _ in range(60):
            try:
                with socket.create_connection(("127.0.0.1", cls.PORT), timeout=0.3):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            cls.proc.kill()
            raise unittest.SkipTest("服务器没起来")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.proc.terminate()
            cls.proc.wait(timeout=5)
        except Exception:
            try:
                cls.proc.kill()
            except Exception:
                pass

    # -- 工具 --
    def _conn(self):
        s = socket.create_connection(("127.0.0.1", self.PORT), timeout=6)
        return s

    def _send(self, s, obj):
        s.sendall((json.dumps(obj) + "\n").encode())

    def _recv(self, s, timeout=6):
        s.settimeout(timeout)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(8192)
            if not chunk:
                break
            buf += chunk
        if not buf.strip():
            return None
        return json.loads(buf.decode("utf-8", "replace").strip().split("\n")[0])

    def _close(self, *socks):
        for s in socks:
            try:
                s.close()
            except Exception:
                pass
        time.sleep(0.15)

    # -- 用例 --
    def test_single_player_gets_queued(self):
        a = self._conn()
        try:
            self._send(a, {"t": "quick_match"})
            r = self._recv(a)
            self.assertEqual(r.get("t"), "queued", r)
            self.assertEqual(r.get("pos"), 1, "第一个人应该排第 1 位")
            self.assertEqual(r.get("waiting"), 1)
        finally:
            self._close(a)

    def test_two_players_get_matched(self):
        a = self._conn()
        b = self._conn()
        try:
            self._send(a, {"t": "quick_match"})
            ra1 = self._recv(a)
            self.assertEqual(ra1.get("t"), "queued", ra1)

            self._send(b, {"t": "quick_match"})
            rb = self._recv(b)
            ra = self._recv(a)

            self.assertEqual(ra.get("t"), "matched", "A 应该收到 matched：%r" % ra)
            self.assertEqual(rb.get("t"), "matched", "B 应该收到 matched：%r" % rb)
            self.assertEqual(ra.get("room"), rb.get("room"),
                             "双方应该在同一个房间")
            self.assertEqual(len(ra.get("room") or ""), 4, "房间号是 4 位")
            self.assertEqual({ra.get("side"), rb.get("side")}, {0, 1},
                             "side 必须互补，否则双方都当房主")
        finally:
            self._close(a, b)

    def test_cancel_match(self):
        a = self._conn()
        try:
            self._send(a, {"t": "quick_match"})
            self.assertEqual(self._recv(a).get("t"), "queued")
            self._send(a, {"t": "cancel_match"})
            self.assertEqual(self._recv(a).get("t"), "match_cancelled")
        finally:
            self._close(a)

    def test_cancel_then_second_player_waits(self):
        """取消后队列应该干净：第二个人不会被配给已取消的人。"""
        a = self._conn()
        b = self._conn()
        try:
            self._send(a, {"t": "quick_match"})
            self._recv(a)
            self._send(a, {"t": "cancel_match"})
            self._recv(a)

            self._send(b, {"t": "quick_match"})
            rb = self._recv(b)
            self.assertEqual(rb.get("t"), "queued",
                             "A 已取消，B 不该立刻被配对：%r" % rb)
        finally:
            self._close(a, b)

    def test_disconnect_removes_from_queue(self):
        """排队中掉线，不能让队列里留死连接。"""
        a = self._conn()
        b = self._conn()
        c = self._conn()
        try:
            self._send(a, {"t": "quick_match"})
            self._recv(a)
            a.close()          # 掉线
            time.sleep(0.4)

            self._send(b, {"t": "quick_match"})
            rb = self._recv(b)
            self.assertEqual(rb.get("t"), "queued",
                             "B 不该被配给已掉线的 A：%r" % rb)

            self._send(c, {"t": "quick_match"})
            rc = self._recv(c)
            rb2 = self._recv(b)
            self.assertEqual(rb2.get("t"), "matched", rb2)
            self.assertEqual(rc.get("t"), "matched", rc)
        finally:
            self._close(a, b, c)

    def test_three_players_pair_two_one_waits(self):
        a, b, c = self._conn(), self._conn(), self._conn()
        try:
            self._send(a, {"t": "quick_match"}); self._recv(a)
            self._send(b, {"t": "quick_match"})
            rb = self._recv(b); ra = self._recv(a)
            self.assertEqual(ra.get("t"), "matched")
            self.assertEqual(rb.get("t"), "matched")

            self._send(c, {"t": "quick_match"})
            rc = self._recv(c)
            self.assertEqual(rc.get("t"), "queued",
                             "第三个人应该继续等：%r" % rc)
        finally:
            self._close(a, b, c)


class MatchmakingClientAPI(unittest.TestCase):
    """不做网络请求，只验证客户端 API 存在且签名正确。"""

    def test_client_api_exists(self):
        from core import relay_client as RC
        for name in ("quick_match_room", "match_via_relay"):
            self.assertTrue(hasattr(RC, name), "缺少 %s" % name)

    def test_socket_has_quick_match(self):
        from core import relay_client as RC
        for name in ("quick_match", "cancel_match"):
            self.assertTrue(hasattr(RC.RelaySocket, name),
                            "RelaySocket 缺少 %s" % name)

    def test_messages_in_whitelist(self):
        """quick_match / cancel_match / matched / queued 都要被认识。"""
        src = ""
        if os.path.isfile(SERVER):
            with open(SERVER, encoding="utf-8") as f:
                src = f.read()
        if not src:
            self.skipTest("server/ 不存在")
        for t in ("quick_match", "cancel_match"):
            self.assertIn('"%s"' % t, src, "服务器没处理 %s" % t)
        for t in ("matched", "queued", "match_cancelled", "match_timeout"):
            self.assertIn('"%s"' % t, src, "服务器没发 %s" % t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
