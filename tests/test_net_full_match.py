#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联机对战「完整一局」端到端测试。

之前只测到「开局成功」，没人验证过一局真的能打完并正确判定胜负。
这个测试用真实 Host + Client 跑完整局。
"""

from __future__ import annotations

import os
import socket
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import cards as C          # noqa: E402
from core import deckbuild as DB     # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _legal_deck(n: int = 20):
    """造一个协议层认可的卡组（同名最多 2 张）。"""
    deck = []
    for cd in C.CARD_LIST:
        if cd.type not in ("attack", "skill"):
            continue
        deck += [cd.id] * min(2, n - len(deck))
        if len(deck) >= n:
            break
    ok, why = DB.validate_deck(deck)
    assert ok, why
    return deck


try:
    from core import netplay as N
    HAS_NET = True
except Exception:                        # pragma: no cover
    HAS_NET = False


@unittest.skipUnless(HAS_NET, "netplay 不可用")
class TestFullOnlineMatch(unittest.TestCase):

    def test_full_match_reaches_result(self):
        """两个真实客户端能打完一整局并收到 over。"""
        deck = _legal_deck()
        port = _free_port()
        hev, cev = [], []
        h = N.Host(on_event=lambda e: hev.append(dict(e)), port=port)
        h.start()
        c = N.Client(on_event=lambda e: cev.append(dict(e)),
                     name="挑战者", require_code=False)
        try:
            self.assertTrue(c.connect("127.0.0.1", port, timeout=8),
                            "客户端连不上房主")
            h.wait_for_client(timeout=8)
            time.sleep(0.3)
            h.send_deck(deck)
            c.send_deck(deck)
            time.sleep(0.8)

            t0 = time.time()
            over = None
            while time.time() - t0 < 40:
                h.poll()
                c.poll()
                over = (next((e for e in cev if e.get("type") == "over"), None)
                        or next((e for e in hev if e.get("type") == "over"), None))
                if over:
                    break
                if c.my_turn():
                    if not c.play_card(0):
                        c.end_turn()
                else:
                    try:
                        if not h.play_card(0):
                            h.end_turn()
                    except Exception:
                        try:
                            h.end_turn()
                        except Exception:
                            pass
                time.sleep(0.06)

            self.assertIsNotNone(over, "整局没能打完（没收到 over）")
            self.assertIn(over.get("winner"), (0, 1),
                          "胜负判定异常：%r" % (over,))
        finally:
            try:
                c.close()
            except Exception:
                pass
            try:
                h.close()
            except Exception:
                pass

    def test_client_rejects_out_of_turn_play(self):
        """不是自己回合时，出牌意图必须被本地拦下。"""
        deck = _legal_deck()
        port = _free_port()
        hev, cev = [], []
        h = N.Host(on_event=lambda e: hev.append(dict(e)), port=port)
        h.start()
        c = N.Client(on_event=lambda e: cev.append(dict(e)),
                     name="挑战者", require_code=False)
        try:
            c.connect("127.0.0.1", port, timeout=8)
            h.wait_for_client(timeout=8)
            time.sleep(0.3)
            h.send_deck(deck)
            c.send_deck(deck)
            time.sleep(0.8)
            # 房主先手：客户端本地就该拦下（不把无效请求打到房主）
            self.assertFalse(c.my_turn(), "开局不该是客户端回合")
            self.assertFalse(c.play_card(0), "非本方回合时本地应该拒绝出牌")
        finally:
            try:
                c.close()
            except Exception:
                pass
            try:
                h.close()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
