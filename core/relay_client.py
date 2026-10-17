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

# --------------------------------------------------------------------
# 中继服务器地址 —— **支持多个，自动故障转移**
# --------------------------------------------------------------------
# 主服务器挂了就自动试下一个，玩家完全无感。
#
# 配置方式（优先级从高到低）：
#   1. 环境变量 SF_RELAY_HOSTS="ip1:9000,ip2:9000"
#   2. 下面的 RELAY_HOSTS 列表（**部署后改这里**）
#   3. 老的单地址环境变量 SF_RELAY_HOST
#
# 建议用域名而不是 IP：以后换服务器只要改 DNS，老客户端自动跟着走。
def _decode_host(parts) -> str:
    """把混淆过的地址片段还原成主机名。

    公开版里服务器地址**不以明文出现** —— 直接写 IP 的话，
    任何人反编译一下就能拿到，等于发给所有人一个攻击目标。
    这里只做最基本的混淆（挡住随手 grep / strings），
    不指望挡住有心人（客户端必然知道要连哪）。
    """
    try:
        return "".join(chr(int(x, 16) ^ 0x5A) for x in parts)
    except Exception:
        return ""


#: 内置服务器（混淆存储，运行时还原）
_RELAY_HOST_PARTS = ("63", "6c", "74", "6b", "68", "6c", "74",
                     "6b", "6d", "63", "74", "6c", "6e")
_RELAY_PORT = 9000

RELAY_HOSTS = [
    # (主机, 端口) —— 第一个是主力，后面的是备用（连不上自动换）
    (_decode_host(_RELAY_HOST_PARTS), _RELAY_PORT),
]

DEFAULT_RELAY_PORT = int(os.environ.get("SF_RELAY_PORT", "9000"))

#: 兼容旧代码：第一台服务器
DEFAULT_RELAY_HOST = ""


def _config_file() -> str:
    """本地服务器配置文件的路径（优先于代码里的 RELAY_HOSTS）。"""
    env = os.environ.get("SF_GAME_HOME")
    if env:
        return os.path.join(env, "server.txt")
    return os.path.join(os.path.expanduser("~"), "Documents", "钢铁战线",
                        "server.txt")


def _read_config_file() -> str:
    """读 server.txt：每行一个 host 或 host:port，# 开头是注释。"""
    try:
        with open(_config_file(), encoding="utf-8") as f:
            lines = []
            for ln in f:
                ln = ln.split("#", 1)[0].strip()
                if ln:
                    lines.append(ln)
            return ",".join(lines)
    except Exception:
        return ""


def save_endpoints(text: str) -> tuple:
    """把玩家填的地址写进 server.txt。返回 (是否成功, 说明)。

    text 支持：
      * 一个或多个地址，用逗号 / 空格 / 换行分隔
      * 自动去掉协议前缀和路径
      * 没写端口就用默认端口
    """
    raw = str(text or "").replace("\n", ",").replace(" ", ",")
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    clean = []
    for p in parts:
        p = p.strip()
        for pre in ("https://", "http://"):
            if p.startswith(pre):
                p = p[len(pre):]
        p = p.split("/", 1)[0]
        if p:
            clean.append(p)
    if not clean:
        return False, "请填服务器地址。"
    path = _config_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 钢铁战线 联机服务器地址（每行一个，第一行是主服务器）\n")
            for c in clean:
                f.write(c + "\n")
    except Exception as exc:
        return False, "写入失败：%s" % exc
    return True, "已保存 %d 个地址。" % len(clean)


def _parse_hosts() -> list:
    """把配置解析成 [(host, port), ...]，按优先级排好。"""
    out = []
    # 优先级：环境变量 > 本地配置文件 > 代码里的 RELAY_HOSTS
    raw = os.environ.get("SF_RELAY_HOSTS", "").strip() or _read_config_file()
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                h, _, p = part.rpartition(":")
                try:
                    out.append((h.strip(), int(p)))
                except ValueError:
                    out.append((part, DEFAULT_RELAY_PORT))
            else:
                out.append((part, DEFAULT_RELAY_PORT))
        return out
    for item in RELAY_HOSTS:
        try:
            h, p = item
        except (TypeError, ValueError):
            continue
        h = str(h or "").strip()
        if h:
            try:
                out.append((h, int(p)))
            except (TypeError, ValueError):
                out.append((h, DEFAULT_RELAY_PORT))
    if out:
        return out
    # 老的单地址
    one = os.environ.get("SF_RELAY_HOST", "").strip()
    if one:
        if ":" in one:
            h, _, p = one.rpartition(":")
            try:
                return [(h.strip(), int(p))]
            except ValueError:
                return [(one, DEFAULT_RELAY_PORT)]
        return [(one, DEFAULT_RELAY_PORT)]
    # 最后回落到模块级变量（测试里会直接改它）
    mod = str(globals().get("DEFAULT_RELAY_HOST") or "").strip()
    if mod:
        if ":" in mod:
            h, _, p = mod.rpartition(":")
            try:
                return [(h.strip(), int(p))]
            except ValueError:
                return [(mod, DEFAULT_RELAY_PORT)]
        return [(mod, DEFAULT_RELAY_PORT)]
    return []


def relay_endpoints() -> list:
    """当前配置的全部服务器地址（按优先级）。"""
    return _parse_hosts()


def is_user_configured() -> bool:
    """玩家是否**自己**配了服务器地址（环境变量 / 本地 server.txt）。

    公开版内置的地址不算 —— 界面上不该显示给别人看。
    """
    try:
        if os.environ.get("SF_RELAY_HOSTS", "").strip():
            return True
        if _read_config_file():
            return True
    except Exception:
        pass
    return False


def relay_configured() -> bool:
    """有没有配置中继服务器（没配就隐藏「公网」入口）。"""
    return bool(_parse_hosts())


def relay_address() -> str:
    """给界面显示的服务器地址（只显示主服务器）。"""
    eps = _parse_hosts()
    if not eps:
        return ""
    h, p = eps[0]
    text = h if ":" in h else ("%s:%d" % (h, p))
    if len(eps) > 1:
        text += "（+%d 备用）" % (len(eps) - 1)
    return text


def connect_any(timeout: float = 0.0):
    """依次尝试配置里的每一台服务器，返回第一个连上的 RelaySocket。

    全连不上就抛 RelayError，里面带上每一台的失败原因 ——
    玩家能看出是"服务器没开"还是"自己网络问题"。
    """
    eps = _parse_hosts()
    if not eps:
        raise RelayError("没有配置联机服务器地址。")
    errors = []
    for h, p in eps:
        rs = RelaySocket(h, p)
        try:
            rs.connect()
            return rs
        except Exception as exc:
            errors.append("%s:%d -> %s" % (h, p, exc))
            try:
                rs.close()
            except Exception:
                pass
    raise RelayError("所有服务器都连不上。\n" + "\n".join(errors))


# 连中继的超时
CONNECT_TIMEOUT = 10.0
# 等待房间创建/加入结果的超时
HANDSHAKE_TIMEOUT = 12.0


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
        #: 快速匹配分到的一边（0/1）
        self.matched_side = 0
        self._queue_cb = None
        self._queue_cancelled = False
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

    # -- 快速匹配 -------------------------------------------------------
    def quick_match(self, on_queue=None, timeout: float = 60.0) -> str:
        """一键匹配：进队列等配对，配上了返回房间号。

        ``on_queue`` 是一个回调（排队位置, 队列人数），用于 UI 显示
        「正在搜索对手…（第 N 位）」。可以不传。

        返回房间号；拿 ``side`` 用 :attr:`matched_side`。
        """
        self._queue_cb = on_queue
        self._send_msg({"t": "quick_match"})
        deadline = time.time() + max(5.0, float(timeout))
        while time.time() < deadline:
            if self.room:
                return self.room
            if self._handshake_error:
                raise RelayError(self._handshake_error)
            time.sleep(0.12)
        # 超时 -> 主动取消，别把服务器队列占着
        try:
            self.cancel_match()
        except Exception:
            pass
        raise RelayError("没有找到对手，请稍后再试。")

    def cancel_match(self) -> None:
        """退出匹配队列。"""
        try:
            self._send_msg({"t": "cancel_match"})
        except Exception:
            pass

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
        if t == "matched":
            # 快速匹配成功：room + side 一起给
            self.room = str(msg.get("room") or "")
            try:
                self.matched_side = int(msg.get("side") or 0)
            except (TypeError, ValueError):
                self.matched_side = 0
            self._handshake_done.set()
            return
        if t == "queued":
            # 排队中：回调给 UI 显示「第 N 位」
            cb = getattr(self, "_queue_cb", None)
            if cb is not None:
                try:
                    cb(int(msg.get("pos") or 0), int(msg.get("waiting") or 0))
                except Exception:
                    pass
            return
        if t == "match_cancelled":
            self._queue_cancelled = True
            self._handshake_error = "已取消匹配。"
            self._handshake_done.set()
            return
        if t == "match_timeout":
            self._handshake_error = "等待超时，请重新匹配。"
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
def _connect_with_failover(host: str = "", port: int = 0) -> RelaySocket:
    """连服务器：显式指定地址就直连，否则按配置依次试（故障转移）。"""
    h = (host or "").strip()
    if h:
        rs = RelaySocket(h, port or DEFAULT_RELAY_PORT)
        rs.connect()
        return rs
    return connect_any()


def make_room(host: str = "", port: int = 0) -> RelaySocket:
    """建房并返回已连接的 socket（房主用）。"""
    rs = _connect_with_failover(host, port)
    rs.host_room()
    return rs


def join(room: str, host: str = "", port: int = 0) -> RelaySocket:
    """加入房间并返回已连接的 socket（玩家用）。"""
    rs = _connect_with_failover(host, port)
    rs.join_room(room)
    return rs


def match_via_relay(host: str = "", port: int = 0,
                    on_queue=None, timeout: float = 60.0):
    """一键匹配，并**自动**决定自己是房主还是挑战者。

    返回 ``(net_object, room, is_host)``：

      * 分到 side=0 -> 当房主（netplay.Host）
      * 分到 side=1 -> 当挑战者（netplay.Client）

    两边都主动连上服务器并配对，之后行为与普通建房/加入完全一致
    （因为中继只是透传，房间里的两个连接是对等的）。
    """
    from . import netplay as _np

    rs, room, side = quick_match_room(host, port, on_queue=on_queue,
                                      timeout=timeout)
    is_host = (side == 0)
    if is_host:
        obj = _np.Host(name="房主")
        obj._sock = rs
        obj._peer = rs
        obj._connected = True
        obj._ticket = None
        obj._reader = threading.Thread(
            target=obj._reader_loop, args=(rs,),
            name="relay-match-host", daemon=True)
        obj._reader.start()
        obj._announce_connected()
        obj._start_heartbeat()
        return obj, room, True

    obj = _np.Client(name="挑战者")
    obj._sock = rs
    obj._connected = True
    obj._connected_once = True
    obj._ticket = None
    obj._reader = threading.Thread(
        target=obj._reader_loop, args=(rs,),
        name="relay-match-client", daemon=True)
    obj._reader.start()
    obj._start_heartbeat()
    hello = {"t": "hello", "ver": _np.PROTOCOL_VERSION, "name": obj.name}
    try:
        snap = _np._integrity_snapshot()
        if snap.get("hash"):
            hello["hash"] = snap["hash"]
            hello["did"] = snap.get("did", "")
            hello["problems"] = snap.get("problems", [])
        try:
            from core import version as _V
            hello["label"] = _V.VERSION_LABEL
        except Exception:
            pass
    except Exception:
        pass
    try:
        obj._send(hello)
    except Exception:
        pass
    return obj, room, False


def quick_match_room(host: str = "", port: int = 0,
                     on_queue=None, timeout: float = 60.0):
    """一键匹配：返回 ``(socket, room, side)``。

    进服务器匹配队列，配上就返回房间号和分到的一边（0=房主位 / 1=挑战者位）。
    配不上抛 RelayError。
    """
    rs = _connect_with_failover(host, port)
    room = rs.quick_match(on_queue=on_queue, timeout=timeout)
    return rs, room, int(getattr(rs, "matched_side", 0) or 0)


__all__ = [
    "DEFAULT_RELAY_HOST", "DEFAULT_RELAY_PORT", "RelayError", "RelaySocket",
    "relay_configured", "relay_address", "make_room", "join",
    "quick_match_room", "match_via_relay",
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
