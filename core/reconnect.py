#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 —— 掉线重连。

为什么需要
----------
局域网也会掉：切 WiFi、笔记本合盖唤醒、路由器抽风、同学手滑关掉窗口。
现在的行为是一掉线就整局作废，体验很差。

策略
----
* 房主**不立刻**销毁对局，而是进入「等待重连」窗口（默认 60 秒）。
* 客户端在这个窗口内用**同一张票据**重连，房主核对票据后把
  当前对局快照重新发过去，继续打。
* 超过窗口就真的结束（发 ``bye``）。

纯标准库，不引入任何依赖。所有操作幂等、不抛异常。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# 默认重连窗口（秒）—— 太短没用，太长又像卡死
DEFAULT_GRACE = 60.0
# 客户端重试节奏（秒）
RETRY_DELAYS = (0.8, 1.6, 2.5, 4.0, 6.0, 8.0)


@dataclass
class ReconnectState:
    """一次掉线事件的状态。

    房主持有一个；客户端也持有一个（记录自己的重试进度）。
    """

    active: bool = False
    deadline: float = 0.0
    attempts: int = 0
    last_reason: str = ""
    resumed: bool = False
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    # -- 房主侧 ---------------------------------------------------------
    def open(self, grace: float = DEFAULT_GRACE, reason: str = "") -> None:
        """对端掉线，打开重连窗口。"""
        with self._lock:
            self.active = True
            self.deadline = time.time() + max(0.0, float(grace))
            self.last_reason = str(reason or "")[:120]
            self.resumed = False
            self.attempts = 0

    def close(self, resumed: bool = False) -> None:
        with self._lock:
            self.active = False
            self.resumed = bool(resumed)

    def is_open(self) -> bool:
        with self._lock:
            if not self.active:
                return False
            if time.time() > self.deadline:
                self.active = False
                return False
            return True

    def left(self) -> float:
        with self._lock:
            if not self.active:
                return 0.0
            return max(0.0, self.deadline - time.time())

    def note_attempt(self) -> int:
        with self._lock:
            self.attempts += 1
            return self.attempts


def retry_delay(attempt: int) -> float:
    """第 N 次重连前等多久（指数退避，封顶 8 秒）。"""
    try:
        i = max(0, int(attempt))
    except Exception:
        i = 0
    if i < len(RETRY_DELAYS):
        return RETRY_DELAYS[i]
    return RETRY_DELAYS[-1]


class Reconnector:
    """客户端侧的重连驱动器（跑在后台线程，不阻塞界面）。

    ``attempt_fn()`` 由调用方提供：返回 True 表示这次重连成功。
    成功或超时都会通过 ``on_done(ok, msg)`` 回调通知。
    """

    def __init__(self, attempt_fn, on_done=None,
                 budget: float = DEFAULT_GRACE):
        self._attempt = attempt_fn
        self._on_done = on_done
        self._budget = float(budget)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.state = ReconnectState(active=True,
                                    deadline=time.time() + self._budget)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop,
                                        name="netplay-reconnect",
                                        daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._stop.set()

    def _finish(self, ok: bool, msg: str) -> None:
        self.state.close(resumed=ok)
        try:
            if callable(self._on_done):
                self._on_done(ok, msg)
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            if time.time() > self.state.deadline:
                self._finish(False, "重连超时，这一局结束了。")
                return
            n = self.state.note_attempt()
            ok = False
            try:
                ok = bool(self._attempt())
            except Exception:
                ok = False
            if ok:
                self._finish(True, "已重新连上，继续对战。")
                return
            # 等一会儿再试（可被 cancel 打断）
            self._stop.wait(retry_delay(n))
        self._finish(False, "已取消重连。")


__all__ = ["DEFAULT_GRACE", "RETRY_DELAYS", "ReconnectState",
           "retry_delay", "Reconnector"]
