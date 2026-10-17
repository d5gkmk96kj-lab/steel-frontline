#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 —— 公网中继客户端。

作用
----
把「经过中继的连接」伪装成一条普通的 TCP 连接，从而**完全复用**
现有的 ``core.netplay.Host`` / ``core.netplay.Client`` 逻辑。

这是本方案最省事的地方：游戏规则、协议、防作弊、房间码签名……
一行都不用改，只要让它们以为自己在跟对方直连。

实现方式
--------
``RelaySocket`` 提供和 ``socket.socket`` 一样的 ``sendall`` / ``recv`` /
``close`` 接口：

    sendall(data)   -> 按行切开，逐行包成 {"d":..., "p":...} 发给中继
    recv(n)         -> 从中继收到的帧里取出 "p"，还原成原始字节
    close()         -> 关闭

上层 netplay 代码完全感知不到中间隔了一台服务器。

连接流程
--------
房主：

    {"t":"host"}                    -> {"t":"room","room":"4821"}
    之后 sendall 的内容被转发给对方

玩家：

    {"t":"join","room":"4821"}      -> {"t":"joined","room":"4821"}

配对成功后双方收到的 ``{"d":"a"|"b","p":"<原始行>"}``，
``RelaySocket`` 把 ``p`` 还原出来交给上层。
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
from typing import Any, Dict, Optional

# 中继服务器地址。**部署后改这里**（或设环境变量覆盖，方便测试）。
# 建议用域名而不是 IP：以后换服务器只要改 DNS，老客户端自动跟着走。
DEFAULT_RELAY_HOST = os.environ.get("SF_RELAY_HOST", "")
DEFAULT_RELAY_PORT = int(os.environ.get("SF_RELAY_PORT", "9000"))

# 连中继的超时
CONNECT_TIMEOUT = 10.0
# 等待房间创建/加入结果的超时
HANDSHAKE_TIMEOUT = 12.0


def relay_configured() -> bool:
    """有没有配置中继服务器（没配就隐藏「公网」入口）。"""
    return bool(DEFAULT_RELAY_HOST.strip())


def relay_address() -> str:
    """给界面显示的服务器地址。"""
    h = DEFAULT_RELAY_HOST.strip()
    if not h:
        return ""
    return h if ":" in h else ("%s:%d" % (h, DEFAULT_RELAY_PORT))


class RelayError(Exception):
    """中继相关的错误（连不上 / 房间不存在 / 已满……）。"""


# --------------------------------------------------------------------------
# 伪 socket
# --------------------------------------------------------------------------
class RelaySocket:
    """像 socket 一样用的中继通道。

    故意不继承 ``socket.socket`` —— 那会带来一堆我们不想要的行为
    （缓冲区大小、超时语义、地址族……）。鸭子类型足够了。
    """

    def __init__(self, host: str, port: int, timeout: float = CONNECT_TIMEOUT):
        self.host = str(host)
        self.port = int(port)
        self._sock: Optional[socket.socket] = None
        self._buf = b""                       # 还没被上层取走的原始字节
        self._recv_q: "queue.Queue[bytes]" = queue.Queue()
        self._closed = False
        self._lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None
        self.room = ""
        self.peer_left = False
        self._handshake_done = threading.Event()
        self._handshake_error = ""
        self._rx_buf = b""
        self._timeout = None

    # -- 连接 -----------------------------------------------------------
    def connect(self) -> None:
        try:
            s = socket.create_connection((self.host, self.port),
                                         timeout=CONNECT_TIMEOUT)
        except OSError as exc:
            raise RelayError(
                "连不上联机服务器（%s:%d）。\n"
                "请检查网络是否正常，或稍后再试。\n（%s）"
                % (self.host, self.port, exc))
        s.settimeout(None)
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._sock = s
        self._reader = threading.Thread(target=self._read_loop,
                                        name="relay-recv", daemon=True)
        self._reader.start()

    # -- 握手 -----------------------------------------------------------
    def _send_msg(self, obj: Dict[str, Any]) -> None:
        if self._sock is None:
            raise RelayError("还没连接。")
        data = (json.dumps(obj, ensure_ascii=False,
                           separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            try:
                self._sock.sendall(data)
            except OSError as exc:
                raise RelayError("发送失败，连接可能已断开。（%s）" % exc)

    def host_room(self) -> str:
        """建房，返回 4 位房间号。"""
        self._send_msg({"t": "host"})
        return self._await_handshake()

    def join_room(self, room: str) -> str:
        """加入房间，返回房间号。"""
        rid = "".join(ch for ch in str(room or "") if ch.isdigit())
        if len(rid) != 4:
            raise RelayError("房间号是 4 位数字。")
        self._send_msg({"t": "join", "room": rid})
        return self._await_handshake()

    def _await_handshake(self) -> str:
        if not self._handshake_done.wait(HANDSHAKE_TIMEOUT):
            raise RelayError("服务器没有响应，请稍后再试。")
        if self._handshake_error:
            raise RelayError(self._handshake_error)
        return self.room

    # -- 读 -------------------------------------------------------------
    def _read_loop(self) -> None:
        s = self._sock
        if s is None:
            return
        buf = b""
        while not self._closed:
            try:
                chunk = s.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                self._on_frame(line)
        # 连接断了
        self._closed = True
        if not self._handshake_done.is_set():
            self._handshake_error = "与联机服务器的连接中断。"
            self._handshake_done.set()
        try:
            self._recv_q.put_nowait(b"")
        except Exception:
            pass

    def _on_frame(self, raw: bytes) -> None:
        try:
            msg = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        # 先处理「转发数据」——凡带 "p" 的都是对方发来的原始行，
        # 必须优先还原，不能因为它的 t 恰好是 ping/pong 就被当成控制消息。
        if "p" in msg:
            payload = msg.get("p")
            if isinstance(payload, str):
                try:
                    self._recv_q.put_nowait(payload.encode("utf-8") + b"\n")
                except Exception:
                    pass
            return

        t = str(msg.get("t") or "")

        # -- 握手结果 --
        if t == "room":
            self.room = str(msg.get("room") or "")
            self._handshake_done.set()
            return
        if t == "joined":
            self.room = str(msg.get("room") or self.room)
            self._handshake_done.set()
            return
        if t == "error":
            self._handshake_error = str(msg.get("msg") or "服务器返回错误。")
            self._handshake_done.set()
            return
        # 注意：只有**服务器自己发的**控制消息才拦。
        # 游戏心跳也用 {"t":"pong"} —— 那种是转发的（外层带 "p"），
        # 必须原样交给上层，否则 netplay 会判定心跳超时并断开（真踩过）。
        if t == "pong" and "p" not in msg:
            return
        if t in ("peer_left", "peer_gone"):
            self.peer_left = True
            try:
                self._recv_q.put_nowait(b"")
            except Exception:
                pass
            return


    # -- socket 兼容接口 -------------------------------------------------
    def sendall(self, data: bytes) -> None:
        """上层给的是一行行 JSON，逐行包成转发帧。

        注意：这里必须走 ``_send_line()``（裸发送），不能用 ``_send_msg()`` ——
        后者是给握手控制消息用的，会再包一层，导致对方收到
        ``{"p":"{\"p\":...}"}`` 这种双层嵌套（真踩过）。
        """
        if self._closed or self._sock is None:
            raise OSError("relay closed")
        try:
            text = data.decode("utf-8", "replace")
        except Exception:
            return
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 直接发**原始行**：服务端负责加方向标记（{"d":..,"p":..}），
            # 客户端这边不能再包一层，否则对方收到的是双层嵌套。
            self._send_raw_line(line)

    def _send_raw_line(self, line: str) -> None:
        """把一行原始 JSON 直接发给中继（服务端会加方向标记转发）。"""
        if self._sock is None:
            raise OSError("relay closed")
        data = (line + "\n").encode("utf-8")
        with self._lock:
            try:
                self._sock.sendall(data)
            except OSError as exc:
                raise OSError("relay send failed: %s" % exc)

    def recv(self, n: int = 65536) -> bytes:
        """返回上层的原始字节（一次一行）。

        **必须阻塞**，不能在空闲时返回 b"" —— 上层（netplay 的读线程）
        把空 bytes 理解成「对端正常关闭」，会立刻判定掉线。
        （socket 超时抛 socket.timeout，而 b"" 是关闭语义，两者不能混。）

        这里循环等待，直到真的有数据或真的断开为止；同时留一个
        ``_timeout`` 出口，方便上层用 settimeout 做非阻塞轮询。
        """
        if self._buf:
            out, self._buf = self._buf, b""
            return out
        while True:
            if self._closed:
                return b""
            try:
                return self._recv_q.get(timeout=0.5)
            except queue.Empty:
                if self._timeout is not None:
                    # 上层显式设置了超时 -> 按 socket 语义抛异常
                    raise socket.timeout("relay recv timeout")
                continue

    def settimeout(self, t) -> None:
        """记录超时值。None = 一直阻塞（默认）。"""
        self._timeout = t

    def getsockopt(self, *a, **kw):
        return 0

    def setsockopt(self, *a, **kw) -> None:
        pass

    def fileno(self) -> int:
        return self._sock.fileno() if self._sock is not None else -1

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._sock is not None:
                self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            if self._sock is not None:
                self._sock.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# 便捷入口：建一个「已经在房里」的 RelaySocket
# --------------------------------------------------------------------------
def make_room(host: str = "", port: int = 0) -> RelaySocket:
    """建房并返回已连接的 socket（房主用）。"""
    h = (host or DEFAULT_RELAY_HOST).strip()
    if not h:
        raise RelayError("没有配置联机服务器地址。")
    rs = RelaySocket(h, port or DEFAULT_RELAY_PORT)
    rs.connect()
    rs.host_room()
    return rs


def join(room: str, host: str = "", port: int = 0) -> RelaySocket:
    """加入房间并返回已连接的 socket（玩家用）。"""
    h = (host or DEFAULT_RELAY_HOST).strip()
    if not h:
        raise RelayError("没有配置联机服务器地址。")
    rs = RelaySocket(h, port or DEFAULT_RELAY_PORT)
    rs.connect()
    rs.join_room(room)
    return rs


__all__ = [
    "DEFAULT_RELAY_HOST", "DEFAULT_RELAY_PORT", "RelayError", "RelaySocket",
    "relay_configured", "relay_address", "make_room", "join",
]


# --------------------------------------------------------------------------
# 给 netplay 用的适配器
# --------------------------------------------------------------------------
def host_via_relay(host: str = "", port: int = 0):
    """建房并把 netplay.Host 接到中继上。

    返回 ``(host_obj, room_code)``。调用方拿到 room_code 后展示给玩家，
    对方用 ``join_via_relay(room_code)`` 进来。

    失败抛 RelayError（带中文原因），调用方直接显示给用户即可。
    """
    from . import netplay as _np

    rs = make_room(host, port)
    h = _np.Host(name="房主")
    # 关键：让 Host 以为这是一条直连 socket
    h._sock = rs
    h._peer = rs
    h._connected = True
    h._ticket = None          # 公网模式先不做房间码签名（中继本身隔离了房间）
    h._reader = threading.Thread(target=h._reader_loop, args=(rs,),
                                 name="relay-host-recv", daemon=True)
    h._reader.start()
    # 让 Host 对外声明「有人连上了」
    h._announce_connected()
    h._start_heartbeat()
    return h, rs.room


def join_via_relay(room_code: str, host: str = "", port: int = 0):
    """加入房间并把 netplay.Client 接到中继上。

    返回 ``(client_obj, relay_socket)``。
    """
    from . import netplay as _np

    rs = join(room_code, host, port)
    c = _np.Client(name="挑战者")
    c._sock = rs
    c._connected = True
    c._connected_once = True
    c._ticket = None
    c._reader = threading.Thread(target=c._reader_loop, args=(rs,),
                                 name="relay-client-recv", daemon=True)
    c._reader.start()
    c._start_heartbeat()
    # 客户端没有 _announce_connected（那是房主的方法），直接发事件
    try:
        c._emit({"type": "connected", "host": rs.host, "port": rs.port})
    except Exception:
        pass
    # 注意：走中继的 hello 也要带代码完整性信息，否则房主会
    # 判成"对方未提供校验信息"并伪装超时（真踩过：
    # 这里自己拼了一个 hello，漏了 hash/did/problems，
    # 导致所有中继对局全部连不上）。
    _hello = {"t": "hello", "ver": _np.PROTOCOL_VERSION, "name": c.name}
    try:
        _snap = _np._integrity_snapshot()
        if _snap.get("hash"):
            _hello["hash"] = _snap["hash"]
            _hello["did"] = _snap.get("did", "")
            _hello["problems"] = _snap.get("problems", [])
        # 版本标签：版本不一致时对方能看到具体版本
        try:
            from core import version as _V
            _hello["label"] = _V.VERSION_LABEL
        except Exception:
            pass
    except Exception:
        pass
    c._send(_hello)
    return c, rs


def sync_account(host: str = "", port: int = 0,
                 timeout: float = 8.0) -> tuple:
    """把本机账号哈希上报给服务器（注册时调用一次）。

    **离线优先**：连不上就直接返回失败，调用方忽略即可 —— 
    绝不能因为同步失败就挡住玩家进游戏。

    返回 (是否成功, 说明)。
    """
    import json as _j
    import socket as _s
    try:
        from core import account as _A
    except Exception:
        return False, "账号模块不可用"

    payload = _A.sync_payload()
    if not payload:
        return False, "本机还没有账号"

    h = host or DEFAULT_RELAY_HOST
    p = int(port or DEFAULT_RELAY_PORT)
    if not h:
        return False, "还没有配置服务器"

    try:
        sock = _s.create_connection((h, p), timeout=timeout)
    except Exception as exc:
        return False, "连不上服务器：%r" % (exc,)
    try:
        sock.settimeout(timeout)
        line = _j.dumps({"t": "account", "data": payload},
                        ensure_ascii=False) + "\n"
        sock.sendall(line.encode("utf-8"))
        raw = sock.recv(4096).decode("utf-8", "replace").strip()
        if not raw:
            return False, "服务器没有响应"
        try:
            msg = _j.loads(raw.split("\n")[0])
        except Exception:
            return False, "服务器返回无法解析"
        if msg.get("t") == "account_ok":
            try:
                _A.mark_synced(True)
            except Exception:
                pass
            return True, "已同步"
        return False, str(msg.get("msg") or "服务器拒绝")
    except Exception as exc:
        return False, "同步出错：%r" % (exc,)
    finally:
        try:
            sock.close()
        except Exception:
            pass
