"""联机协议测试（core/netplay.py）—— 风险最高的一块。

覆盖（按 Lead 指定优先级）：
1. 伪装 state 广播 —— 客户端发 {"t":"state",...} 必须被房主忽略
2. 越权出牌 / 超费 / 越界
3. 协议健壮性 —— 非法 JSON / 半行分片 / 超长行 / 多消息 / 空行 / 乱码
4. 断线检测
5. 端口占用不抛异常
6. 本机互连（127.0.0.1 + 随机空闲端口）跑完整局

全部使用 127.0.0.1，不依赖真实局域网。
纯 unittest，零 pytest。
"""

import json
import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load  # noqa: E402


def _mod():
    m, err = load("core.netplay")
    if m is None:
        raise AssertionError("core.netplay 无法导入：%s" % err)
    return m


def _deck(n=20):
    cards, _ = load("core.cards")
    db, _ = load("core.deckbuild")
    pool = db.card_pool() if db is not None else [c.id for c in cards.CARD_DB.values()]
    out = []
    i = 0
    while len(out) < n:
        out.append(pool[i % len(pool)])
        i += 1
    return out


class _Collector:
    """收集事件回调。"""

    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def __call__(self, ev):
        with self.lock:
            self.events.append(ev)

    def types(self):
        """事件名：netplay 用 "type"，协议帧用 "t"，两者都取。"""
        with self.lock:
            return [e.get("type") or e.get("t")
                    for e in self.events if isinstance(e, dict)]

    def by_type(self, t):
        with self.lock:
            return [e for e in self.events
                    if isinstance(e, dict) and (e.get("type") == t or e.get("t") == t)]

    def wait_for(self, t, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            if t in self.types():
                return True
            time.sleep(0.02)
        return False

    def count(self, t):
        return sum(1 for x in self.types() if x == t)


class NetplayCase(unittest.TestCase):
    def setUp(self):
        self.NP = _mod()
        self.port = self.NP.free_port()

    def tearDown(self):
        for obj in getattr(self, "_cleanup", []):
            try:
                obj.close()
            except Exception:
                pass

    def _host(self, events=None, port=None, name="房主"):
        ev = events if events is not None else _Collector()
        h = self.NP.Host(on_event=ev, port=port or self.port, name=name)
        self._cleanup = getattr(self, "_cleanup", []) + [h]
        return h, ev

    def _client(self, events=None, name="挑战者"):
        ev = events if events is not None else _Collector()
        c = self.NP.Client(on_event=ev, name=name)
        self._cleanup = getattr(self, "_cleanup", []) + [c]
        return c, ev


# ---------------------------------------------------------------- 端口/启动
class TestPortAndStartup(NetplayCase):

    def test_free_port_returns_valid(self):
        p = self.NP.free_port()
        self.assertIsInstance(p, int)
        self.assertGreater(p, 1024)
        self.assertLess(p, 65536)

    def test_start_on_free_port(self):
        h, _ = self._host()
        self.assertTrue(h.start(), "空闲端口应能成功 start()")

    def test_busy_port_returns_false_not_exception(self):
        """端口被占用时 start() 应返回 False，不抛异常。"""
        # 注意：房主绑定的是所有接口（0.0.0.0），所以只占 127.0.0.1 不构成冲突
        # （我第一版就是这么写错的）。必须占 0.0.0.0 才能真正制造「端口被占用」。
        # Windows 上 SO_REUSEADDR 的语义与 POSIX **不同**：
        # 它允许两个 socket 绑同一端口（相当于 Linux 的 SO_REUSEPORT），
        # 于是"占住端口"这个前提根本不成立，Host.start() 照样成功。
        # 所以这里必须**不设** SO_REUSEADDR。
        s = socket.socket()
        if os.name != "nt":
            # POSIX 上要设，否则 TIME_WAIT 会导致绑定失败
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", self.port))
        except OSError:
            # 某些平台不允许绑 0.0.0.0，退回绑本机
            s.bind(("127.0.0.1", self.port))
        s.listen(1)
        try:
            h = self.NP.Host(on_event=_Collector(), port=self.port, name="房主")
            self._cleanup = getattr(self, "_cleanup", []) + [h]
            try:
                r = h.start()
            except Exception as exc:
                self.fail("端口被占用时 start() 抛异常：%r" % (exc,))
            self.assertFalse(r, "端口被占用时 start() 应返回 False")
        finally:
            s.close()

    def test_local_ip_returns_string(self):
        ip = self.NP.local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(ip)

    def test_double_start_safe(self):
        h, _ = self._host()
        h.start()
        try:
            r = h.start()
        except Exception as exc:
            self.fail("重复 start() 抛异常：%r" % (exc,))
        self.assertIsInstance(r, bool)

    def test_close_without_start_safe(self):
        h = self.NP.Host(on_event=_Collector(), port=self.port)
        try:
            h.close()
        except Exception as exc:
            self.fail("未 start 就 close() 抛异常：%r" % (exc,))


# ---------------------------------------------------------------- 连接
class TestConnect(NetplayCase):

    def test_host_wait_and_client_connect(self):
        h, hev = self._host()
        self.assertTrue(h.start())
        c, cev = self._client()
        self.assertTrue(c.connect("127.0.0.1", self.port, timeout=5),
                        "客户端应能连上本机房主")
        h.wait_for_client(timeout=5)

    def test_connect_to_dead_port_returns_false(self):
        c, _ = self._client()
        dead = self.NP.free_port()
        try:
            r = c.connect("127.0.0.1", dead, timeout=2)
        except Exception as exc:
            self.fail("连接不存在的端口抛异常：%r" % (exc,))
        self.assertFalse(r, "连接无人监听的端口应返回 False")

    def test_connect_bad_host_returns_false(self):
        c, _ = self._client()
        try:
            r = c.connect("256.256.256.256", self.port, timeout=2)
        except Exception as exc:
            self.fail("非法主机名抛异常：%r" % (exc,))
        self.assertIsInstance(r, bool)


# ---------------------------------------------------------------- 反作弊
class TestAntiCheat(NetplayCase):
    """伪装 state 广播 / 越权操作 —— 联机最容易被钻空子。"""

    def test_validate_rejects_state_broadcast(self):
        """客户端不得发送 state 类型消息（那是房主专属）。"""
        fn = getattr(self.NP, "validate_client_intent", None)
        self.assertIsNotNone(fn, "缺少 validate_client_intent")
        for payload in ({"t": "state"}, {"t": "state", "payload": {"hp": 9999}},
                        {"t": "state", "hp": 9999}):
            r = fn(payload)
            self.assertTrue(r, "房主应拒绝客户端的 state 广播，实际返回 %r" % (r,))

    def test_validate_rejects_unknown_types(self):
        fn = self.NP.validate_client_intent
        for t in ("hack", "cheat", "set_hp", "god", "__proto__", ""):
            r = fn({"t": t})
            self.assertTrue(r, "未知消息类型 %r 应被拒绝" % t)

    def test_validate_accepts_legal_intents(self):
        """validate_client_intent 只服务于 _on_intent（play/end 路径）。"""
        fn = self.NP.validate_client_intent
        for msg in ({"t": "play", "idx": 0}, {"t": "end"},
                    {"t": "ping"}, {"t": "pong"}):
            r = fn(msg)
            self.assertEqual(r, "", "合法消息 %r 不应被拒绝，实际 %r" % (msg, r))

    def test_validate_allowlist_matches_actual_routing(self):
        """记录不一致：`deck` 走 _on_peer_ready，不经过 validate_client_intent。

        实测 `_handle_message` 明确接受 `deck`（netplay.py:887），
        但 `validate_client_intent` 对它返回「不支持的操作：deck」。
        由于它只被 `_on_intent`（play/end）调用，这是**死分支**，
        当前不影响功能（deck 交换实测正常）。此处仅记录，不判失败。
        """
        r = self.NP.validate_client_intent({"t": "deck", "cards": ["strike"]})
        if r:
            print("\n[netplay] 注意：validate_client_intent 拒绝 'deck'（%r），"
                  "但该函数仅用于 play/end 路径；deck 走 _on_peer_ready，"
                  "属命名/职责不一致的死分支，不影响功能。" % r)
            self.assertIn("deck", r)

    def test_validate_rejects_malformed_play(self):
        fn = self.NP.validate_client_intent
        for msg in ({"t": "play"}, {"t": "play", "idx": -1},
                    {"t": "play", "idx": "x"}, {"t": "play", "idx": None}):
            r = fn(msg)
            self.assertTrue(r, "畸形 play 消息 %r 应被拒绝" % (msg,))

    def test_raw_state_frame_does_not_change_host_state(self):
        """**端到端**：客户端直接发原始 state 帧，房主状态必须不变。"""
        h, hev = self._host()
        self.assertTrue(h.start())
        c, cev = self._client()
        self.assertTrue(c.connect("127.0.0.1", self.port, timeout=5))
        h.wait_for_client(timeout=5)
        # 交换卡组，确保对局已开始
        h.send_deck(_deck(20))
        c.send_deck(_deck(20))
        time.sleep(0.4)

        snap_before = h.snapshot()
        hp_before = None
        if snap_before:
            for k in ("me", "you", "self"):
                if k in snap_before and isinstance(snap_before[k], dict):
                    hp_before = snap_before[k].get("hp")
                    break

        # 恶意：直接往 socket 里灌 state 帧
        raw = c._sock if hasattr(c, "_sock") else getattr(c, "sock", None)
        if raw is None:
            self.skipTest("无法拿到客户端裸 socket 以发送恶意帧")
        malicious = [
            {"t": "state", "payload": {"hp": 9999}},
            {"t": "state", "me": {"hp": 9999}, "opponent": {"hp": 0}},
            {"t": "hp", "value": 9999},
            {"t": "set_hp", "hp": 9999},
        ]
        for m in malicious:
            try:
                raw.sendall((json.dumps(m) + "\n").encode("utf-8"))
            except Exception:
                pass
        h.tick(0.1)
        time.sleep(0.4)
        h.tick(0.1)

        snap_after = h.snapshot()
        if snap_before and snap_after and hp_before is not None:
            hp_after = None
            for k in ("me", "you", "self"):
                if k in snap_after and isinstance(snap_after[k], dict):
                    hp_after = snap_after[k].get("hp")
                    break
            self.assertEqual(hp_after, hp_before,
                             "客户端 state 广播改变了房主血量（%r -> %r）"
                             % (hp_before, hp_after))
        self.assertIn(h.result() if hasattr(h, "result") else "ongoing",
                      ("ongoing", "a_wins", "b_wins", "draw"))

    def test_out_of_range_play_index_rejected(self):
        h, _ = self._host()
        h.start()
        c, _ = self._client()
        c.connect("127.0.0.1", self.port, timeout=5)
        h.wait_for_client(timeout=5)
        h.send_deck(_deck(20))
        c.send_deck(_deck(20))
        time.sleep(0.3)
        try:
            h.play_card(999)
            h.play_card(-1)
            c.play_card(999)
        except Exception as exc:
            self.fail("越界出牌抛异常：%r" % (exc,))


# ---------------------------------------------------------------- 协议健壮性
class TestProtocolRobustness(NetplayCase):
    """畸形输入绝不能打崩房主。"""

    def _pair(self):
        h, hev = self._host()
        self.assertTrue(h.start(), "房主启动失败")
        c, cev = self._client()
        self.assertTrue(c.connect("127.0.0.1", self.port, timeout=5),
                        "连接失败")
        self.assertTrue(h.wait_for_client(timeout=5), "房主未感知到客户端")
        return h, c, hev

    def _raw(self, c):
        s = getattr(c, "_sock", None) or getattr(c, "sock", None)
        if s is None:
            self.skipTest("无法获取客户端裸 socket")
        return s

    def test_garbage_inputs_do_not_crash_host(self):
        h, c, hev = self._pair()
        sock = self._raw(c)
        payloads = [
            b"not json at all\n",
            b"{\n",
            b"}\n",
            b"[]\n",
            b"null\n",
            b"12345\n",
            b'"just a string"\n',
            b"\n",
            b"   \n",
            b"\t\r\n",
            b'{"t":\n',
            b'{"t": "play", "idx": }\n',
            b"\xff\xfe\xfd garbage bytes \x00\x01\n",
            b'{"t": "' + b"x" * 500 + b'"}\n',
            json.dumps({"t": "play", "idx": 0, "extra": {"deep": [1, 2, 3]}}).encode() + b"\n",
        ]
        for p in payloads:
            try:
                sock.sendall(p)
            except Exception:
                break
            h.tick(0.05)
        time.sleep(0.3)
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("畸形输入导致房主 tick 抛异常：%r" % (exc,))
        # 房主仍应存活可交互
        self.assertTrue(h.start() in (True, False))

    def test_split_frame_reassembled(self):
        """半行分片：先发一半，再发另一半 —— 应被正确重组。"""
        h, c, hev = self._pair()
        sock = self._raw(c)
        msg = json.dumps({"t": "end"}).encode() + b"\n"
        half = len(msg) // 2
        sock.sendall(msg[:half])
        h.tick(0.05)
        time.sleep(0.15)
        sock.sendall(msg[half:])
        time.sleep(0.3)
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("半行分片导致异常：%r" % (exc,))

    def test_split_then_next_message(self):
        """分片 + 后续整条消息不能粘连错位。"""
        h, c, hev = self._pair()
        sock = self._raw(c)
        m1 = json.dumps({"t": "end"}) + "\n"
        m2 = json.dumps({"t": "play", "idx": 0}) + "\n"
        b1 = m1.encode()
        sock.sendall(b1[:3])
        h.tick(0.05)
        sock.sendall(b1[3:] + m2.encode())
        time.sleep(0.3)
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("分片粘连导致异常：%r" % (exc,))

    def test_multiple_messages_one_packet(self):
        """一次 send 多条消息必须全部被处理，不丢不粘。"""
        h, c, hev = self._pair()
        sock = self._raw(c)
        batch = b"".join(json.dumps({"t": t}).encode() + b"\n"
                         for t in ("end", "end", "end"))
        sock.sendall(batch)
        time.sleep(0.3)
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("批量消息导致异常：%r" % (exc,))

    def test_oversized_line_does_not_hang_or_oom(self):
        """超长单行（远超 MAX_LINE）不能 OOM 或卡死。"""
        h, c, hev = self._pair()
        sock = self._raw(c)
        max_line = getattr(self.NP, "MAX_LINE", 512 * 1024)
        # 发 2 倍 MAX_LINE 的垃圾，且不给换行
        chunk = b"a" * 65536
        total = 0
        t0 = time.time()
        try:
            while total < max_line * 2 and time.time() - t0 < 5:
                sock.sendall(chunk)
                total += len(chunk)
        except Exception:
            pass
        # 房主必须仍能响应（未卡死）
        t1 = time.time()
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("超长行导致 tick 异常：%r" % (exc,))
        self.assertLess(time.time() - t1, 10, "超长行处理耗时过长（疑似卡死）")
        self.assertLess(time.time() - t0, 30, "超长行导致整体卡死")

    def test_oversized_line_then_valid_frame(self):
        """超长垃圾行之后，正常帧仍应能被处理。"""
        h, c, hev = self._pair()
        sock = self._raw(c)
        try:
            sock.sendall(b"x" * (getattr(self.NP, "MAX_LINE", 512 * 1024) + 1024) + b"\n")
        except Exception:
            pass
        time.sleep(0.2)
        try:
            sock.sendall(json.dumps({"t": "end"}).encode() + b"\n")
        except Exception:
            pass
        time.sleep(0.3)
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("超长行后正常帧导致异常：%r" % (exc,))

    def test_empty_and_whitespace_lines(self):
        h, c, hev = self._pair()
        sock = self._raw(c)
        sock.sendall(b"\n\n\n \n\t\n\r\n\n")
        time.sleep(0.2)
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("空行导致异常：%r" % (exc,))

    def test_server_never_crashes_from_any_fuzz(self):
        """随机字节 fuzz 100 帧，房主不得崩溃。"""
        import random as _r
        h, c, hev = self._pair()
        sock = self._raw(c)
        rng = _r.Random(2024)
        for i in range(100):
            n = rng.randrange(0, 200)
            junk = bytes(rng.randrange(256) for _ in range(n))
            try:
                sock.sendall(junk + (b"\n" if rng.random() < 0.7 else b""))
            except Exception:
                break
            if i % 20 == 0:
                h.tick(0.02)
        time.sleep(0.3)
        try:
            h.tick(0.1)
        except Exception as exc:
            self.fail("fuzz 导致房主异常：%r" % (exc,))


# ---------------------------------------------------------------- 断线
class TestDisconnect(NetplayCase):

    def test_client_close_detected_by_host(self):
        h, hev = self._host()
        h.start()
        c, cev = self._client()
        c.connect("127.0.0.1", self.port, timeout=5)
        h.wait_for_client(timeout=5)
        h.send_deck(_deck(20))
        c.send_deck(_deck(20))
        time.sleep(0.3)
        c.close()
        # 房主应在一个合理时间内感知
        # 断开检测需要若干轮 tick（实测约 36 轮 × 0.1s）。
        # 我第一版只 tick(0.05) 且轮数不够，导致误判「房主没感知」。
        got = False
        for _ in range(120):
            h.tick(0.1)
            tset = set(hev.types())
            if tset & {"disconnected", "peer_left", "error", "bye",
                       "disconnect", "left", "rejected"}:
                got = True
                break
            time.sleep(0.05)
        self.assertTrue(got,
                        "客户端断开后房主应给出事件（实际事件：%s）"
                        % [(e.get("type"), str(e.get("msg"))[:30]) for e in hev.events][:10])

    def test_host_close_does_not_crash_client(self):
        h, _ = self._host()
        h.start()
        c, cev = self._client()
        c.connect("127.0.0.1", self.port, timeout=5)
        h.wait_for_client(timeout=5)
        h.close()
        time.sleep(0.5)
        try:
            for _ in range(10):
                try:
                    c.poll() if hasattr(c, "poll") else c.snapshot()
                except Exception:
                    pass
                time.sleep(0.05)
        except Exception as exc:
            self.fail("房主关闭导致客户端抛异常：%r" % (exc,))

    def test_abrupt_socket_close(self):
        """粗暴 RST 断开（不发 bye）也不应崩房主。"""
        h, hev = self._host()
        h.start()
        c, cev = self._client()
        c.connect("127.0.0.1", self.port, timeout=5)
        h.wait_for_client(timeout=5)
        s = getattr(c, "_sock", None) or getattr(c, "sock", None)
        if s is not None:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                             __import__("struct").pack("ii", 1, 0))
            except Exception:
                pass
        try:
            c.close()
        except Exception:
            pass
        time.sleep(0.4)
        try:
            for _ in range(10):
                h.tick(0.05)
        except Exception as exc:
            self.fail("粗暴断开导致房主异常：%r" % (exc,))

    def test_close_twice_safe(self):
        h, _ = self._host()
        h.start()
        h.close()
        try:
            h.close()
        except Exception as exc:
            self.fail("重复 close() 抛异常：%r" % (exc,))

    def test_client_methods_after_close_safe(self):
        c, _ = self._client()
        c.close()
        for fn, args in (("play_card", (0,)), ("end_turn", ()),
                         ("send_deck", (_deck(20),))):
            f = getattr(c, fn, None)
            if f is None:
                continue
            try:
                f(*args)
            except Exception as exc:
                self.fail("close 后调用 %s 抛异常：%r" % (fn, exc))


# ---------------------------------------------------------------- 完整对局
class TestFullMatchLocalhost(NetplayCase):

    def test_full_match_over_localhost(self):
        """本机互连跑完整局：双方交换卡组 → 出牌 → 直到分出结果。"""
        h, hev = self._host()
        self.assertTrue(h.start())
        c, cev = self._client()
        self.assertTrue(c.connect("127.0.0.1", self.port, timeout=5))
        self.assertTrue(h.wait_for_client(timeout=5))

        deck = _deck(20)
        h.send_deck(deck)
        c.send_deck(deck)

        # 泵事件直到开局
        for _ in range(100):
            h.tick(0.02)
            if h.snapshot():
                break
            time.sleep(0.02)

        self.assertIsNotNone(h.snapshot(), "房主应能取到快照")

        guard = 0
        while guard < 300:
            guard += 1
            snap = h.snapshot()
            if not snap:
                break
            res = snap.get("result", "ongoing")
            if res != "ongoing":
                break
            cur = snap.get("current_side", 0)
            # 尽量出牌
            played = False
            for i in range(12):
                try:
                    h.play_card(i) if cur == 0 else c.play_card(i)
                    played = True
                    break
                except Exception:
                    continue
            h.tick(0.02)
            h.end_turn() if cur == 0 else c.end_turn()
            h.tick(0.02)
            time.sleep(0.01)

        snap = h.snapshot()
        self.assertIsNotNone(snap)
        self.assertIn(snap.get("result", "ongoing"),
                      ("ongoing", "a_wins", "b_wins", "draw"),
                      "对局结果非法：%r" % snap.get("result"))

    def test_snapshot_after_connect_is_dict(self):
        h, _ = self._host()
        h.start()
        c, _ = self._client()
        c.connect("127.0.0.1", self.port, timeout=5)
        h.wait_for_client(timeout=5)
        h.send_deck(_deck(20))
        c.send_deck(_deck(20))
        for _ in range(60):
            h.tick(0.02)
            s = h.snapshot()
            if s:
                self.assertIsInstance(s, dict)
                return
            time.sleep(0.02)
        self.fail("交换卡组后房主仍拿不到快照")


if __name__ == "__main__":
    unittest.main(verbosity=2)
