# -*- coding: utf-8 -*-
"""钢铁战线 — 局域网 1v1 联机（零第三方依赖）。

设计
----
* **纯标准库**：``socket`` / ``threading`` / ``queue`` / ``json``。
  不 import 任何第三方包，PyInstaller 打包后同学双击即用。
* **权威房主模型**：房主跑 ``core.versus.VersusBattle``，客户端**只发操作意图**
  （"我要出第 2 张牌"），房主校验合法性后才改状态并广播快照。
  客户端**无法**直接改血量 / 状态 / 出不属于自己的牌。
* **每人一份快照**：房主给客户端发 ``snapshot_for(1)``（自己视角），给自己用
  ``snapshot_for(0)``。对手手牌只以**数量**出现，内容永不出网。
* **后台线程 + 队列**：所有 ``recv`` 在 daemon 线程里做，解析成事件塞进
  ``queue.Queue``；UI 线程只调 ``poll()`` 取事件。**不做任何跨线程 Tk 调用**。
* **绝不抛异常到 UI**：一切错误（端口被占、连接失败、对方退出、心跳超时、
  协议坏帧）都变成 ``{"type": "error"/"bye", "msg": "中文提示"}`` 事件。
* **消息分片**：缓冲区按 ``\\n`` 切分，半行留到下次，一次多行逐行处理，
  所以 TCP 怎么切都不影响解析。

协议（JSON 行协议，UTF-8，每行一个 JSON 对象，``\\n`` 结尾）
------------------------------------------------------------
::

    C -> H   hello   {"t":"hello","ver":1,"name":"玩家名","hash":"...","did":"..."}
    H -> C   hello   {"t":"hello","ver":1,"name":"玩家名","side":1}
    C -> H   ready   {"t":"ready","cards":["strike",...]}   双方都 ready 才开局
    H -> C   start   {"t":"start","your_side":1,"names":[...]}
    H -> C   state   {"t":"state","payload":{...}}          每人一份快照
    C -> H   play    {"t":"play","idx":2,"target":0}        只是意图
    C -> H   end     {"t":"end"}
    H <-> C  ping    {"t":"ping","ts":...} / pong {"t":"pong","ts":...}
    both     chat    {"t":"chat","text":"..."}               对局内聊天
    both     profile {"t":"profile","name":"...","title":"...","display":"..."}
    both     error   {"t":"error","msg":"..."}
    both     bye     {"t":"bye","reason":"对方已断开"}

事件（``on_event`` 回调 / ``poll()`` 返回的 dict）
--------------------------------------------------
::

    {"type":"listening", "port":45671, "ip":"10.0.0.5"}
    {"type":"connecting","host":"10.0.0.7","port":45671}
    {"type":"connected"}
    {"type":"peer",    "name":"玩家名"}          # 收到对方 hello
    {"type":"ready",   "side":0}                 # 自己已就绪（本地回执）
    {"type":"peer_ready","name":"玩家名"}        # 对方已就绪
    {"type":"start",   "side":0,"names":[...],"snapshot":{...}|None}
    {"type":"state",   "payload":{...}}          # 对战快照（每人一份）
    {"type":"log",     "msg":"..."}              # 房主权威战报（战斗日志增量）
    {"type":"pong"} / {"type":"ping_timeout"} / {"type":"peer_pong"}
    {"type":"disconnected","msg":"对方已断开"}   # + bye 事件紧跟其后
    {"type":"bye",     "reason":"对方已断开"}
    {"type":"error",   "msg":"端口 45671 已被占用，请换个端口"}

线程安全
--------
* ``_send`` 由公开方法（UI 线程）直接调用 —— 一个 4KB 以内的小 JSON 帧走一次
  ``sendall``，CPython 下的 socket 写本身是线程安全的；这避免了"发送队列"
  在 ``close()`` 时丢掉最后一条 bye 的经典问题。
* 所有状态字段（``_peer_name`` / ``_connected`` / ``_started`` …）只在后台
  线程里读写，UI 线程通过事件而非共享状态感知变化。
"""

from __future__ import annotations

import errno
import json
import queue
import random
import socket
import threading
import time

from . import session as _sess
from typing import Any, Callable, List, Optional

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
DEFAULT_PORT = 45671
PROTOCOL_VERSION = 1

PING_INTERVAL = 5.0      # 每 5 秒 ping 一次
PONG_TIMEOUT = 15.0      # 15 秒没 pong 判定掉线
ACCEPT_TIMEOUT = 1.0     # accept 轮询间隔，保证 wait_for_client 能被 close 打断

MAX_LINE = 512 * 1024    # 单行上限（防止对端灌爆内存 / 卡死 recv）
MAX_CARDS = 300          # 卡组张数上限
MAX_NAME_LEN = 24
MAX_DECK_ID_LEN = 64     # 单个卡牌 id 长度上限

ERR_PORT_BUSY = "端口 {port} 已被占用，请换一个端口或关掉占用它的程序。"
ERR_CONNECT_FAIL = "连接失败：无法连接到 {host}:{port}（请确认对方已开房间、两台设备在同一个 WiFi 下）。"
ERR_TIMEOUT = "连接超时：{host}:{port} 没有响应（检查 IP 是否输对、防火墙是否拦截）。"
ERR_PEER_LEFT = "对方已断开连接。"
ERR_HEARTBEAT = "网络心跳超时，与对方失去联系（可能是 WiFi 断开或对方关掉了游戏）。"
ERR_BAD_FRAME = "收到无法解析的消息，已忽略。"
ERR_PROTOCOL = "对方使用了不兼容的游戏版本（协议 v{ver}，需要 v{need}）。"
ERR_NOT_CONNECTED = "还没连上对方，操作无效。"
ERR_DECK_EMPTY = "卡组是空的，请先构筑卡组。"
ERR_DECK_TOO_BIG = "卡组最多 {max} 张。"
ERR_DECK_BAD_CARD = "卡组里有未知的卡牌，已拒绝。"
ERR_CANNOT_PLAY = "这张牌现在打不出（手牌序号不存在，或还没轮到你）。"

_SIDE_NAMES = ("房主", "加入方")


def _now() -> float:
    return time.monotonic()


def _safe_int(v: Any, default: int = -1) -> int:
    """把任意东西安全转成 int；失败返回 default。绝不抛异常。"""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# 局域网 IP 探测
# --------------------------------------------------------------------------
def local_ip() -> str:
    """返回本机局域网 IP（如 ``10.16.64.27``），失败返回 ``127.0.0.1``。

    先用 UDP trick：connect 一个公网地址不会真的发包，但内核会按路由表选出
    本机出口网卡地址 —— 这是最准确的做法（多网卡 / VPN 下也比
    ``gethostbyname(gethostname())`` 靠谱）。失败再退回 hostname 解析。
    """
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))          # 不真正发包
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    except Exception:
        pass
    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip:
            return ip
    except OSError:
        pass
    except Exception:
        pass
    return "127.0.0.1"


def free_port() -> int:
    """要一个当前空闲的端口（自检用；有极小竞态，生产用 DEFAULT_PORT）。"""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        return int(s.getsockname()[1])
    except Exception:
        return DEFAULT_PORT
    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass


def _is_valid_card_id(cid: Any) -> bool:
    """卡牌 id 只允许短的 snake_case，防止超长字符串 / 注入怪东西进对战引擎。"""
    if not isinstance(cid, str):
        return False
    if not cid or len(cid) > MAX_DECK_ID_LEN:
        return False
    for ch in cid:
        if not (ch.isalnum() or ch == "_"):
            return False
    return True


def _sanitize_name(name: Any, fallback: str = "玩家") -> str:
    if not isinstance(name, str):
        return fallback
    name = name.strip().replace("\n", " ").replace("\r", " ")
    if not name:
        return fallback
    return name[:MAX_NAME_LEN]


# --------------------------------------------------------------------------
# versus 引擎的松散适配层
# --------------------------------------------------------------------------
# versus.py 由队友 versus-core 提供（task-8）。为了在它出现之前就能落地联机层，
# 这里做 duck-typing 适配：多签名依次尝试 + 明确的中文错误事件，绝不抛到 UI。
_VERSUS_MODULE = None
_VERSUS_IMPORT_ERROR = ""


def _load_versus():
    """惰性 import ``core.versus``；失败返回 None 并记下原因。"""
    global _VERSUS_MODULE, _VERSUS_IMPORT_ERROR
    if _VERSUS_MODULE is not None:
        return _VERSUS_MODULE
    try:
        from core import versus as _v  # type: ignore
        _VERSUS_MODULE = _v
    except Exception as exc:            # ImportError / 队友文件写坏了 都不许炸
        _VERSUS_IMPORT_ERROR = "%s: %s" % (type(exc).__name__, exc)
        return None
    return _VERSUS_MODULE


def engine_available() -> bool:
    """对战引擎是否可用（UI 可据此提前提示"对战模块缺失"）。"""
    return _load_versus() is not None


def engine_error() -> str:
    return _VERSUS_IMPORT_ERROR


def _has_method(obj: Any, name: str) -> bool:
    return callable(getattr(obj, name, None))


def _try_calls(fns) -> Any:
    """依次尝试若干调用形式，返回第一个不抛 TypeError 的结果。

    只吞 ``TypeError``（签名不匹配），其它异常照常冒泡给调用方兜住 ——
    免得把引擎的真实 bug 伪装成"签名不对"。
    """
    last = None
    for fn in fns:
        try:
            return fn()
        except TypeError as exc:
            last = exc
            continue
    if last is not None:
        raise last
    return None


# versus-core 冻结 API（task-8）：
#   VersusBattle(deck_a, deck_b, rng=None, hp=75, turn_seconds=60)
#   play_card(side, card_index, target_index=None) -> bool
#   end_turn(side) -> bool
#   tick(dt_seconds) -> None        # UI 每秒调一次，累计到 turn_seconds 自动换手
#   snapshot_for(side) -> dict      # side = 看谁的视角
#   result() -> "ongoing"|"a_wins"|"b_wins"|"draw"
#   current_side() -> 0|1
# 下面的调用一律按这个签名，不再靠多签名猜测；只保留极薄的防御，
# 保证队友文件若被改坏也只是"报错事件"而不是崩溃。
_VS_TIMEOUT_PHASES = ("a_wins", "b_wins", "draw")


def _make_battle(deck0: List[str], deck1: List[str], seed: Optional[int] = None):
    """构造对战实例。返回 ``(battle, error_msg)``，绝不抛异常。"""
    mod = _load_versus()
    if mod is None:
        return None, ("对战模块 core/versus.py 不可用（%s）。"
                      % (_VERSUS_IMPORT_ERROR or "文件缺失"))
    cls = getattr(mod, "VersusBattle", None)
    if cls is None:
        return None, "对战模块缺少 VersusBattle 类，无法开局。"
    rng = random.Random(seed if seed is not None else random.randrange(1 << 30))
    try:
        battle = cls(list(deck0), list(deck1), rng=rng)
    except Exception as exc:
        return None, "无法创建对战：%s" % exc
    if battle is None:
        return None, "无法创建对战：引擎返回了空对象。"
    return battle, ""


def _battle_play(battle, side: int, idx: int, target: Optional[int]) -> bool:
    """代房主发起一次出牌。引擎返回 False = 非法操作（反作弊靠它兜底）。"""
    fn = getattr(battle, "play_card", None)
    if not callable(fn):
        return False
    try:
        if target is None:
            r = fn(int(side), int(idx))
        else:
            r = fn(int(side), int(idx), int(target))
    except Exception:
        return False
    if r is None:
        return True
    return bool(r)


def _battle_end_turn(battle, side: int) -> bool:
    fn = getattr(battle, "end_turn", None)
    if not callable(fn):
        return False
    try:
        r = fn(int(side))
    except Exception:
        return False
    if r is None:
        return True
    return bool(r)


def _battle_snapshot(battle, side: int) -> Optional[dict]:
    """取"side 视角"的快照（``snapshot_for``）。取不到时回退 ``snapshot()``。"""
    fn = getattr(battle, "snapshot_for", None)
    if callable(fn):
        try:
            snap = fn(int(side))
            if isinstance(snap, dict):
                return snap
        except Exception:
            pass
    fn = getattr(battle, "snapshot", None)
    if callable(fn):
        try:
            snap = fn()
            if isinstance(snap, dict):
                return snap
        except Exception:
            return None
    return None


def _battle_over(battle) -> bool:
    """对局是否结束：``result() != "ongoing"``。"""
    fn = getattr(battle, "result", None)
    if callable(fn):
        try:
            return str(fn()) != "ongoing"
        except Exception:
            return False
    snap = getattr(battle, "phase", None)
    return isinstance(snap, str) and snap in _VS_TIMEOUT_PHASES


def _battle_winner(battle) -> Optional[int]:
    """获胜方 0/1，平局或进行中返回 None。"""
    fn = getattr(battle, "winner_side", None)
    if callable(fn):
        try:
            w = fn()
            return w if w in (0, 1) else None
        except Exception:
            return None
    fn = getattr(battle, "result", None)
    if callable(fn):
        try:
            r = str(fn())
        except Exception:
            return None
        if r == "a_wins":
            return 0
        if r == "b_wins":
            return 1
    return None


def _battle_current_side(battle) -> int:
    fn = getattr(battle, "current_side", None)
    if callable(fn):
        try:
            return 1 if int(fn()) == 1 else 0
        except Exception:
            pass
    return 0


def _battle_log_delta(battle, cursor: int) -> "tuple[List[str], int]":
    """取战斗日志增量（房主权威战报），返回 ``(新条目, 新游标)``。

    日志优先从快照里取（versus 把 log 放在快照里），拿不到再退回 battle.log。
    """
    log = None
    snap_fn = getattr(battle, "snapshot_for", None)
    if callable(snap_fn):
        try:
            snap = snap_fn(_battle_current_side(battle))
            if isinstance(snap, dict) and isinstance(snap.get("log"), list):
                log = snap["log"]
        except Exception:
            log = None
    if log is None:
        log = getattr(battle, "log", None)
    if not isinstance(log, list):
        return [], cursor
    if cursor > len(log):       # 引擎截断过日志，重新对齐
        cursor = 0
    return [str(x) for x in log[cursor:]], len(log)


def _battle_tick(battle, dt: float) -> None:
    """推进回合计时（``tick(dt)``）；没有 tick 的引擎直接忽略。"""
    fn = getattr(battle, "tick", None)
    if not callable(fn):
        return
    try:
        fn(float(dt))
    except Exception:
        pass


def _battle_time_left(battle) -> Optional[float]:
    """当前方剩余秒数；引擎不提供时返回 None。"""
    fn = getattr(battle, "time_left", None)
    if callable(fn):
        try:
            return float(fn())
        except Exception:
            return None
    snap = getattr(battle, "snapshot_for", None)
    if callable(snap):
        try:
            s = snap(_battle_current_side(battle))
            if isinstance(s, dict) and "time_left" in s:
                return float(s["time_left"])
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------
# C->H 操作意图的严格校验（反作弊关键路径）
# --------------------------------------------------------------------------
# 客户端**允许**发给房主的全部消息类型（已知协议白名单）。
# 其余一律拒绝：包括 `state`（那是房主专属广播，客户端发就是伪造）、
# `hp` / `win` / 任何未知类型（越权改状态）。
# --------------------------------------------------------------------------
# 代码完整性校验（联机时确认双方跑的是同一份代码）
# --------------------------------------------------------------------------
def _integrity_snapshot() -> dict:
    """取本机的完整性信息。失败时返回空 dict（不阻断游戏）。"""
    try:
        from core import integrity as _I
        ok, rep = _I.self_check()
        return {
            "hash": rep.get("build_hash", ""),
            "problems": rep.get("problems", []),
            "did": rep.get("device_id", ""),
            "clean": bool(ok),
        }
    except Exception:
        return {}


#: 校验结果类型
VER_OK = "ok"
VER_MISMATCH = "mismatch"      # 版本不一致（对局相关代码不同）—— 可以明确告诉玩家
VER_TAMPER = "tamper"          # 疑似篡改 —— 伪装超时，不告诉原因


#: 客户端请求速率上限（次/秒）。真人操作远达不到这个速度。
MAX_INTENT_PER_SEC = 12
#: 超过这个次数就判定为自动化/脚本
INTENT_BURST_LIMIT = 40

#: 对局中每隔多少秒重查一次本机完整性（运行中代码被改也要发现）
REVERIFY_INTERVAL = 20.0
#: 单人快照里这些字段的合理上限（超出即判定异常）
SANE_LIMITS = {
    "hp": 5000,
    "block": 5000,
    "energy": 99,
}


def _snapshot_sane(snap: dict) -> list:
    """检查一份快照的数值是否在合理范围内。

    返回问题列表。作弊者常改动血量/护甲/能量来速胜，
    这些值有明确上限，超了就说明被改过。
    """
    problems = []
    if not isinstance(snap, dict):
        return ["bad-snapshot"]
    for side_key in ("me", "opponent", "you", "foe"):
        d = snap.get(side_key)
        if not isinstance(d, dict):
            continue
        for field_name, cap in SANE_LIMITS.items():
            v = d.get(field_name)
            if v is None:
                continue
            try:
                if int(v) > int(cap) or int(v) < -1:
                    problems.append("%s.%s=%r" % (side_key, field_name, v))
            except (TypeError, ValueError):
                problems.append("%s.%s-bad-type" % (side_key, field_name))
    # 手牌数量也有上限
    hand = snap.get("my_hand") or snap.get("hand") or []
    if isinstance(hand, list) and len(hand) > 30:
        problems.append("hand=%d" % len(hand))
    return problems


def _check_peer_integrity(msg: dict, strict: bool = True):
    """校验对方 hello 里带的哈希。

    返回 ``(ok, kind, 说明)``，其中 ``kind`` 是：

      * ``VER_OK``       —— 通过
      * ``VER_MISMATCH`` —— **版本不一致**。
        双方的战斗 / 卡牌代码不同，联机必然出问题（同步错乱、崩溃）。
        这种情况**明确告诉玩家**「版本不一致，请更新」，因为对方多半
        只是没更新，不是恶意。
      * ``VER_TAMPER``   —— 疑似**篡改**。
        对方自报了调试器、注入之类的东西。这种**伪装成网络超时**，
        不告诉真实原因（免得被针对性绕过）。

    怎么区分「版本不同」和「被改过」：
      哈希只覆盖 engine / cards / versus / netplay 这些**对局相关**的模块。
      正常更新 -> 哈希变，但对方自检是干净的 -> 判成「版本不一致」。
      自己改代码 -> 通常还会带调试器 / 补丁痕迹 -> 判成「篡改」。
    """
    try:
        from core import integrity as _I
    except Exception:
        return True, VER_OK, ""
    expect = str(msg.get("hash") or "")
    mine = _I.build_hash()
    if not expect:
        # 老客户端没有这个字段 —— 放行（不能因为对方版本旧就连不上）
        return True, VER_OK, ""
    if not mine:
        return True, VER_OK, ""            # 本机算不出来就不拦

    # 对方自报的运行时问题（调试器 / 注入 / 补丁）
    probs = msg.get("problems") or []
    has_problems = isinstance(probs, list) and bool(probs)

    if expect != mine:
        if has_problems:
            return False, VER_TAMPER, "代码校验失败。"
        # 纯粹是版本不同
        theirs = str(msg.get("label") or "").strip()
        mine_label = ""
        try:
            from core import version as _V
            mine_label = _V.VERSION_LABEL
        except Exception:
            pass
        detail = ("对方的版本：%s\n你的版本：%s" % (theirs, mine_label)
                  if theirs else "")
        return False, VER_MISMATCH, detail

    if has_problems:
        return False, VER_TAMPER, "代码校验失败。"
    return True, VER_OK, ""


CLIENT_ALLOWED_TYPES = ("hello", "ready", "deck", "play", "end",
                        "chat", "profile",
                        "ping", "pong", "bye", "error")
# 其中真正携带"操作"、需要逐字段校验的：
INTENT_TYPES = ("play", "end")

# 明确点名的高危类型 -> 专用中文文案（比"不支持的操作"更能提示作弊）
_PRIVILEGED_TYPES = {
    "state": "对战状态只能由房主裁决，该消息已忽略。",
    "snapshot": "对战状态只能由房主裁决，该消息已忽略。",
    "start": "开局指令只能由房主发出，该消息已忽略。",
    "over": "对局结果只能由房主裁定，该消息已忽略。",
}


def validate_client_intent(msg: dict) -> str:
    """校验客户端发来的消息。返回 "" 表示合法，否则返回中文拒绝原因。

    绝不信任客户端传来的任何数值：类型、范围、字段齐全性全部重查。
    真正的合法性（是不是你的回合、有没有这张牌、费用够不够）由房主上的
    ``versus`` 引擎在 ``play_card`` 里最终裁决 —— 这里只拦明显的畸形/越权输入。

    规则
    ----
    * ``play``：``idx`` 必须是非 bool 的 int 且 0 <= idx < MAX_CARDS；
      ``target`` 若存在必须是非 bool 的 int 且在 -1..15。
    * ``end`` / ``ping`` / ``pong`` / ``hello`` / ``ready`` / ``deck`` /
      ``bye`` / ``error``：协议内的合法类型，放行（细分校验在 ``_handle``）。
    * ``state`` / ``snapshot`` / ``start`` / ``over``：房主专属，客户端发送一律拒绝。
    * 其它任何类型：拒绝。
    """
    if not isinstance(msg, dict):
        return "消息格式错误。"
    t = msg.get("t")
    if t in _PRIVILEGED_TYPES:
        return _PRIVILEGED_TYPES[t]
    if t == "play":
        idx = msg.get("idx")
        # bool 是 int 的子类，必须单独挡掉（True 会被当成 1 号手牌）
        if not isinstance(idx, int) or isinstance(idx, bool):
            return "出牌请求的卡牌序号非法。"
        if idx < 0 or idx >= MAX_CARDS:
            return "出牌请求的卡牌序号非法。"
        tgt = msg.get("target")
        if tgt is not None and (not isinstance(tgt, int) or isinstance(tgt, bool)):
            return "出牌目标非法。"
        if isinstance(tgt, int) and (tgt < -1 or tgt >= 16):
            return "出牌目标非法。"
        return ""
    if t in CLIENT_ALLOWED_TYPES:
        return ""
    return "不支持的操作：%s" % str(t)[:24]


# --------------------------------------------------------------------------
# 作弊判定（彩蛋）
# --------------------------------------------------------------------------
# 两套文案。用哪一套由 ``SF_CHEAT_FLAVOR`` 环境变量决定，打包脚本会设置：
#   "spicy"  = 完整版（自用），保留原话
#   "mild"   = 公开版（分发），文明措辞 —— 默认值
# 之所以做成运行时切换而不是两份代码：逻辑完全一样，只有文案不同。
FLAVOR_ENV = "SF_CHEAT_FLAVOR"

_FLAVORS = {
    "spicy": {
        "shame": "挂狗全家火葬场",
        "label": "挂狗",
        "log": "检测到对手作弊（%s）—— 已标记。",
    },
    "mild": {
        "shame": "作弊是可耻的",
        "label": "作弊者",
        "log": "对手试图作弊（%s），已拒绝并标记。",
    },
}
DEFAULT_FLAVOR = "mild"


def _bundled_flavor() -> str:
    """读随包分发的风格文件（打包时写入，优先级低于环境变量）。

    为什么需要它：环境变量只在**打包时**存在，用户双击 .app 时没有。
    所以风格必须落盘，否则完整版会被静默降级成温和文案。
    """
    import os as _os
    import sys as _sys
    cands = []
    base = getattr(_sys, "_MEIPASS", None)
    if base:
        cands.append(_os.path.join(base, "cheat_flavor.txt"))
    here = _os.path.dirname(_os.path.abspath(__file__))
    cands.append(_os.path.join(_os.path.dirname(here), "cheat_flavor.txt"))
    cands.append(_os.path.join(here, "cheat_flavor.txt"))
    for c in cands:
        try:
            with open(c, "r", encoding="utf-8") as f:
                v = f.read().strip().lower()
            if v in _FLAVORS:
                return v
        except Exception:
            continue
    return ""


def cheat_flavor() -> str:
    """当前生效的文案风格。

    优先级：环境变量 > 随包风格文件 > 默认（温和）。
    """
    import os as _os
    v = str(_os.environ.get(FLAVOR_ENV, "") or "").strip().lower()
    if v in _FLAVORS:
        return v
    v2 = _bundled_flavor()
    if v2:
        return v2
    return DEFAULT_FLAVOR


def cheat_text(key: str) -> str:
    """取指定风格的文案（key: shame / label / log）。"""
    tbl = _FLAVORS.get(cheat_flavor(), _FLAVORS[DEFAULT_FLAVOR])
    return tbl.get(key, _FLAVORS[DEFAULT_FLAVOR].get(key, ""))


def _sync_cheat_texts() -> None:
    """把当前风格的文案同步到模块级常量（兼容旧调用点）。"""
    global CHEAT_SHAME_TEXT, CHEAT_LABEL, CHEAT_LOG_TEXT
    CHEAT_SHAME_TEXT = cheat_text("shame")
    CHEAT_LABEL = cheat_text("label")
    CHEAT_LOG_TEXT = cheat_text("log")


# 模块级常量：导入时按当前风格定一次；测试/打包可调 _sync_cheat_texts() 刷新
CHEAT_SHAME_TEXT = ""
CHEAT_LABEL = ""
CHEAT_LOG_TEXT = ""
_sync_cheat_texts()


def classify_cheat(msg) -> str:
    """判断一条客户端消息是否属于**恶意作弊**。返回原因，合法则返回 ""。

    区分「手滑/选错了」与「蓄意作弊」：
      * 伪造房主专属消息（state/snapshot/start/over）—— 蓄意，客户端
        根本没有发送这些的接口，只能是手搓的包。
      * 冒充作弊类消息（cheat/redeem/god_mode/...）—— 蓄意。
      * 出牌索引越界或负数 —— 蓄意（正常 UI 只会点手上存在的牌）。
      * 未知消息类型 —— 蓄意（正常客户端不会发明协议）。
    以下**不算**作弊（是真·操作失误，只走普通 rejected）：
      * 不是自己的回合出牌
      * 补给不足
      * 出牌目标字段格式不对
    """
    if not isinstance(msg, dict):
        return ""                                  # 垃圾包不算作弊
    t = msg.get("t")
    if t in _PRIVILEGED_TYPES:
        return "伪造房主专属消息（%s）" % str(t)
    if t in CLIENT_CHEAT_TYPES:
        return "冒充作弊指令（%s）" % str(t)
    if t == "play":
        idx = msg.get("idx")
        if not isinstance(idx, int) or isinstance(idx, bool):
            return "构造非法出牌序号"
        if idx < 0 or idx >= MAX_CARDS:
            return "出牌序号越界（%d）" % idx
        return ""
    if t in CLIENT_ALLOWED_TYPES or t in INTENT_TYPES:
        return ""
    return "发送未知协议消息（%s）" % str(t)[:24]


# 客户端冒充作弊指令的类型（命中即判定作弊）
CLIENT_CHEAT_TYPES = ("cheat", "redeem", "cheats", "god_mode", "godmode",
                      "give", "hp", "win", "annex", "manpower", "nuke")


# --------------------------------------------------------------------------
# 连接基类（收发线程 + 心跳 + 事件队列）
# --------------------------------------------------------------------------
class _Conn:
    """房主/客户端共用的 TCP 收发骨架。子类只需实现 ``_handle(msg)``。"""

    def __init__(self, on_event: Optional[Callable[[dict], None]] = None,
                 name: str = "玩家",
                 ticket=None) -> None:
        self._on_event = on_event if callable(on_event) else None
        self.name = _sanitize_name(name, "玩家")
        # 会话票据：不为 None 时，收发消息都带 HMAC 签名（房间码安全）
        self._ticket = ticket
        self._send_seq = 0
        self._sec_fails = 0
        self._events: "queue.Queue[dict]" = queue.Queue()
        self._sock: Optional[socket.socket] = None
        self._reader: Optional[threading.Thread] = None
        self._heart: Optional[threading.Thread] = None
        self._closing = threading.Event()      # 我方主动关闭
        self._finished = threading.Event()     # 连接已结束（只发一次 bye）
        self._peer = None                      # 对端 socket（房主用）
        self._connected = False
        self._started = False
        self._peer_name = ""
        self._peer_ready = False
        self._last_pong = _now()
        self._sent_ping_at = 0.0
        self._buf = b""
        self._lock = threading.RLock()
        self.side = 0                          # 0=房主, 1=加入方

    # ---------------- 事件 ----------------
    def _emit(self, ev: dict) -> None:
        """投递事件：队列给 poll()，同时（可选）调回调。异常一律吞掉。"""
        if not isinstance(ev, dict):
            return
        try:
            self._events.put(ev)
        except Exception:
            pass
        cb = self._on_event
        if cb is not None:
            try:
                cb(ev)
            except Exception:
                pass

    def _error(self, msg: str) -> None:
        self._emit({"type": "error", "msg": str(msg)})

    def poll(self) -> List[dict]:
        """UI 线程调用：取出当前所有待处理事件（非阻塞）。"""
        out: List[dict] = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                break
            except Exception:
                break
        return out

    # ---------------- 发送 ----------------
    def _send(self, msg: dict) -> bool:
        """把一条消息编码成一行 JSON 发出去。失败返回 False，不抛异常。

        如果本次会话带了票据（房间码），会自动附上序号与 HMAC 签名；
        没带票据时按原样发送（局域网默认模式，向后兼容）。

        **密钥一致性**：房主开的码可能比对方输入的长（对方只念了前几组）。
        签名必须用双方**实际约定的那一串**（即对方输入的值），
        否则两边算出的 HMAC 不同，消息会被对方判为篡改。
        """
        sock = self._sock
        if sock is None:
            return False
        try:
            tk = getattr(self, "_ticket", None)
            peer_code = getattr(self, "_peer_code", None)
            if peer_code:
                # 已有约定的共享密钥（房主侧，对方输入的那个码）
                tk = _sess.Ticket(token=peer_code, require_code=True)
            if tk is not None:
                self._send_seq = int(getattr(self, "_send_seq", 0)) + 1
                msg = _sess.wrap(tk, msg, self._send_seq)
            line = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            return False
        data = (line + "\n").encode("utf-8")
        try:
            with self._lock:
                sock.sendall(data)
            return True
        except OSError:
            self._drop_peer("发送失败，对方连接已中断")
            return False
        except Exception:
            return False

    def _send_bye(self, reason: str) -> None:
        """只发一次 bye（用 _finished 去重）。"""
        if self._finished.is_set():
            return
        self._finished.set()
        self._send({"t": "bye", "reason": str(reason)})

    # ---------------- 接收 ----------------
    def _reader_loop(self, sock: socket.socket) -> None:
        """后台线程：recv -> 按 \\n 切分 -> 逐行 json -> _handle(msg)。

        这是"消息分片"的落点：半行留在 ``self._buf``，一次多行全部处理。
        """
        self._buf = b""
        try:
            sock.settimeout(1.0)
        except OSError:
            return
        while not self._closing.is_set():
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._closing.is_set() or getattr(exc, "errno", None) in (
                        errno.EBADF, errno.ENOTCONN, errno.ECONNRESET):
                    break
                if not self._connected:
                    break
                self._drop_peer(ERR_PEER_LEFT)
                break
            except Exception:
                break
            if not chunk:
                # 对端正常关闭
                if not self._closing.is_set():
                    self._drop_peer(ERR_PEER_LEFT)
                break
            self._buf += chunk
            if len(self._buf) > MAX_LINE:
                self._error(ERR_BAD_FRAME)
                self._buf = b""
                continue
            while b"\n" in self._buf:
                raw, self._buf = self._buf.split(b"\n", 1)
                self._handle_raw(raw)
        self._finished.set()

    # -- 完整性违规：记录 + 伪装超时 --------------------------------
    # -- 聊天 / 档案 --------------------------------------------------
    #: 单条聊天最大长度（防刷屏 / 防塞大段文本）
    CHAT_MAX_LEN = 120
    #: 每局最多发多少条（防轰炸）
    CHAT_MAX_TOTAL = 60

    def _on_peer_chat(self, msg: dict) -> None:
        """收到对方的聊天。做长度/频率限制后抛给 UI。"""
        try:
            text = str(msg.get("text") or "").strip()
        except Exception:
            return
        if not text:
            return
        if len(text) > self.CHAT_MAX_LEN:
            text = text[:self.CHAT_MAX_LEN]
        # 去掉控制字符（防终端转义 / 换行注入）
        text = "".join(ch for ch in text if ord(ch) >= 32 or ch == " ")
        try:
            n = int(getattr(self, "_chat_count", 0))
        except Exception:
            n = 0
        if n >= self.CHAT_MAX_TOTAL:
            return
        self._chat_count = n + 1
        try:
            self._emit({"type": "chat", "text": text,
                        "name": self._peer_name or "对手",
                        "title": getattr(self, "_peer_title", ""),
                        "from": "peer"})
        except Exception:
            pass

    def _on_peer_profile(self, msg: dict) -> None:
        """收到对方的名字 / 头衔。"""
        try:
            name = _sanitize_name(msg.get("name"), "")
            title = str(msg.get("title") or "")[:16]
            disp = str(msg.get("display") or "")[:32]
        except Exception:
            return
        if name:
            self._peer_name = name
        self._peer_title = title
        try:
            self._emit({"type": "profile", "name": self._peer_name,
                        "title": title, "display": disp or self._peer_name})
        except Exception:
            pass

    def send_chat(self, text: str) -> bool:
        """发一条聊天给对方。"""
        text = str(text or "").strip()[:self.CHAT_MAX_LEN]
        if not text:
            return False
        text = "".join(ch for ch in text if ord(ch) >= 32 or ch == " ")
        try:
            n = int(getattr(self, "_chat_count", 0))
        except Exception:
            n = 0
        if n >= self.CHAT_MAX_TOTAL:
            return False
        self._chat_count = n + 1
        try:
            self._send({"t": "chat", "text": text})
            self._emit({"type": "chat", "text": text, "from": "me",
                        "name": self.name})
            return True
        except Exception:
            return False

    def send_profile(self, name: str, title: str = "",
                     display: str = "") -> bool:
        """把自己的名字/头衔告诉对方。"""
        try:
            self._send({"t": "profile", "name": str(name or "")[:16],
                        "title": str(title or "")[:16],
                        "display": str(display or "")[:32]})
            return True
        except Exception:
            return False

    def _record_integrity_violation(self, msg: dict, why: str) -> None:
        """把一次「代码校验失败」记录下来。

        记录内容：对方自报的设备号、哈希、原因、时间。
        通过 security 事件抛给上层（大厅/控制台会存下来并回传管理台）。
        """
        try:
            from core import integrity as _I
            # 尽量取到对方的 IP（局域网直连时从 socket 拿）
            peer_ip = ""
            try:
                sk = getattr(self, "_sock", None) or getattr(self, "sock", None)
                pa = sk.getpeername() if sk is not None else None
                if isinstance(pa, (tuple, list)) and pa:
                    peer_ip = str(pa[0])
            except Exception:
                peer_ip = ""
            entry = {
                "type": "integrity",
                "peer_ip": peer_ip,
                "reason": str(why),
                "peer_hash": str(msg.get("hash") or "")[:64],
                "peer_device": str(msg.get("did") or "")[:32],
                "peer_problems": list(msg.get("problems") or [])[:8],
                "my_hash": _I.short_hash(),
                "my_device": _I.short_device(),
                "ts": time.time(),
                "peer_name": _sanitize_name(msg.get("name"), "对手"),
            }
            self._emit(entry)
            # 累计一份，供举报/管理台读取
            try:
                from core import integrity as _I2
                _I2.record_violation(entry)
            except Exception:
                pass
        except Exception:
            pass

    def _reject_version_mismatch(self, detail: str = "") -> None:
        """版本不一致：明确告诉双方原因（不是篡改，只是没更新）。

        对局相关代码（战斗/卡牌）不同的话，联机必然出同步问题，
        所以直接拒绝 —— 但要说清原因，让对方知道去更新。
        """
        msg = "版本不一致，无法联机。\n请双方都更新到最新版后再试。"
        if detail:
            msg += "\n\n" + detail
        try:
            self._emit({"type": "version_mismatch", "msg": msg})
        except Exception:
            pass
        try:
            self._send({"t": "error", "msg": msg})
        except Exception:
            pass
        try:
            self._send_bye("版本不一致，请更新后再试。")
        except Exception:
            pass
        try:
            self._teardown(notify=False)
        except Exception:
            pass

    def _fake_timeout(self) -> None:
        """对违规方伪装成「网络超时」。

        为什么要伪装：直接告诉对方"你被检测到改代码了"，
        等于告诉他哪一层被发现了，方便针对性绕过。
        对外一律表现为连不上/掉线。
        """
        try:
            self._emit({"type": "timeout",
                        "msg": "连接超时，请检查网络后重试。"})
        except Exception:
            pass
        try:
            self._send_bye("连接超时。")
        except Exception:
            pass
        try:
            self._teardown(notify=False)
        except Exception:
            pass

    def _security_reject(self, why: str) -> None:
        """票据/签名校验失败：记一次并拒绝。

        不直接断线 —— 可能只是网络把包弄坏了，丢这一条继续。
        但如果连续多次失败，就说明对方在乱来，直接断开。
        """
        try:
            self._sec_fails = int(getattr(self, "_sec_fails", 0)) + 1
        except Exception:
            self._sec_fails = 1
        try:
            self._emit({"type": "security", "msg": str(why),
                        "count": self._sec_fails})
        except Exception:
            pass
        if self._sec_fails >= 5:
            self._drop_peer("对方连续发送未通过校验的消息，已断开。")

    def _handle_raw(self, raw: bytes) -> None:
        raw = raw.strip()
        if not raw:
            return
        try:
            msg = json.loads(raw.decode("utf-8", "replace"))
        except (ValueError, UnicodeDecodeError):
            self._error(ERR_BAD_FRAME)
            return
        if not isinstance(msg, dict):
            self._error(ERR_BAD_FRAME)
            return

        # 票据校验：带了房间码时必须签名有效，否则整条丢弃。
        # 校验通过后 _s/_t/_g 会被摘掉，下面拿到的就是干净的业务消息。
        tk = getattr(self, "_recv_ticket", None) or getattr(self, "_ticket", None)
        if tk is not None and getattr(tk, "require_code", False) \
                and getattr(self, "_peer_code", None) is None \
                and getattr(self, "side", 1) == 0:
            # 房主开了房间码，但还不知道对方输的是什么码 ——
            # hello 里会带；在那之前不收任何业务消息。
            if msg.get("t") != "hello":
                self._security_reject("请先发送带房间码的 hello。")
                return
            typed = str(msg.get("code") or "")
            if not _sess.code_matches(tk.token, typed):
                self._security_reject("房间码不正确。")
                try:
                    self._send({"t": "bye", "reason": "房间码不正确，已拒绝。"})
                except Exception:
                    pass
                self._drop_peer("对方房间码不正确，已断开。")
                return
            # 记下对方的码：以后所有消息都用它验签
            self._peer_code = _sess.normalize_code(typed)
            self._auth_pending = False
            self._announce_connected()
            # 用对方的码验这条 hello 的签名
            ok, why = _sess.unwrap(
                _sess.Ticket(token=self._peer_code, require_code=True), msg)
            if not ok:
                self._security_reject(why)
                return
            try:
                self._handle(msg)
            except Exception as exc:
                self._error("处理对方消息时出错：%s" % exc)
            return

        if tk is not None:
            # 房主侧已记录对方用的码 -> 用它验签；否则用本房 token
            peer_code = getattr(self, "_peer_code", None)
            verify_tk = (_sess.Ticket(token=peer_code, require_code=True)
                         if peer_code else tk)
            ok, why = _sess.unwrap(verify_tk, msg)
            if not ok:
                # ---- 校验失败 ----
                self._security_reject(why)
                if getattr(self, "_auth_pending", False):
                    # 房主侧：还没鉴权成功对方就发不合法消息 -> 踢掉
                    try:
                        self._send({"t": "bye",
                                    "reason": "房间码不正确，已拒绝。"})
                    except Exception:
                        pass
                    self._drop_peer("对方房间码不正确，已断开。")
                elif getattr(self, "_awaiting_auth", False):
                    # 客户端侧：房主没回签名正确的消息 -> 说明码不对
                    self._awaiting_auth = False
                    self._emit({"type": "error",
                                "msg": "房间码不正确，或房主没有开启房间码。"})
                    self._drop_peer("房间码校验未通过。")
                return
            # ---- 校验通过 ----
            if getattr(self, "_auth_pending", False):
                # 房主侧：鉴权通过，现在才算真正连上
                self._auth_pending = False
                self._announce_connected()
            elif getattr(self, "_awaiting_auth", False):
                # 客户端侧：房主回话了且签名正确 -> 码是对的
                self._awaiting_auth = False
                self._emit({"type": "connected",
                            "host": getattr(self, "_host_ip", ""),
                            "port": getattr(self, "_host_port", 0)})

        t = msg.get("t")
        now = _now()
        # 心跳在基类统一处理
        if t == "ping":
            self._send({"t": "pong", "ts": msg.get("ts")})
            self._emit({"type": "ping"})
            return
        if t == "pong":
            self._last_pong = now
            self._emit({"type": "peer_pong"})
            return
        if t == "bye":
            reason = msg.get("reason") or ERR_PEER_LEFT
            self._emit({"type": "disconnected", "msg": str(reason)[:120]})
            self._emit({"type": "bye", "reason": str(reason)[:120]})
            self._finished.set()
            self._connected = False
            self._teardown(notify=False)
            return
        if t == "error":
            self._error(str(msg.get("msg") or "对方报错。")[:160])
            return
        try:
            self._handle(msg)
        except Exception as exc:        # 任何解析/引擎异常都不许杀线程
            self._error("处理对方消息时出错：%s" % exc)

    def _handle(self, msg: dict) -> None:       # pragma: no cover - 子类实现
        pass

    # ---------------- 心跳 ----------------
    def _heartbeat_loop(self) -> None:
        last_verify = 0.0
        while not self._closing.is_set():
            if self._closing.wait(PING_INTERVAL):
                return
            if self._closing.is_set():
                return
            if self._last_pong and (_now() - self._last_pong) > PONG_TIMEOUT:
                self._emit({"type": "ping_timeout", "msg": ERR_HEARTBEAT})
                self._drop_peer(ERR_HEARTBEAT)
                return
            # 对局中持续校验本机完整性（不只在握手时查一次）
            try:
                if (_now() - last_verify) >= REVERIFY_INTERVAL:
                    last_verify = _now()
                    self._reverify_self()
            except Exception:
                pass
            self._sent_ping_at = _now()
            if not self._send({"t": "ping", "ts": int(time.time())}):
                return

    def _rate_ok(self) -> bool:
        """检查客户端请求速率是否正常（防脚本连发）。

        记录最近 1 秒内的请求时间戳；超过上限判定为异常。
        """
        try:
            now = _now()
            stamps = getattr(self, "_intent_stamps", None)
            if stamps is None:
                stamps = []
                self._intent_stamps = stamps
            # 只保留最近 1 秒
            stamps[:] = [t for t in stamps if now - t < 1.0]
            stamps.append(now)
            if len(stamps) > MAX_INTENT_PER_SEC:
                return False
            total = int(getattr(self, "_intent_total", 0)) + 1
            self._intent_total = total
            if total > INTENT_BURST_LIMIT and len(stamps) > MAX_INTENT_PER_SEC * 0.8:
                return False
            return True
        except Exception:
            return True

    def _reverify_self(self) -> None:
        """对局中重查本机完整性：运行中代码被改也要能发现。

        发现异常时**不主动断开**（免得误伤），但会：
          * 记录一条违规
          * 在下次发出去的 ping 里带上 problems
          * 房主侧收到后按既有逻辑标记对方
        """
        try:
            from core import integrity as _I
            probs = _I.check_runtime()
            h = _I.build_hash(refresh=True)   # 强制重算，防缓存掩盖改动
        except Exception:
            return
        if h:
            self._live_hash = h
        if probs:
            try:
                self._self_problems = list(probs)[:8]
            except Exception:
                pass

    def _start_heartbeat(self) -> None:
        if self._heart is not None and self._heart.is_alive():
            return
        self._last_pong = _now()
        self._heart = threading.Thread(
            target=self._heartbeat_loop, name="netplay-heartbeat", daemon=True)
        self._heart.start()

    # ---------------- 生命周期 ----------------
    def _reset_peer_auth(self) -> None:
        """清掉与"上一个对手"有关的鉴权状态。

        不清的话，房主重新开始等待后，新连入的人会被当成
        「已经鉴权过的同一人」而直接放行（或反之被拒）。
        """
        try:
            self._peer_code = None
            self._announced = False
            self._auth_pending = False
            self._peer_name = ""
            self._peer_ready = False
            self._i_ready = False
        except Exception:
            pass

    def _drop_peer(self, reason: str) -> None:
        """判定对端掉线：通知一次，然后优雅收摊。"""
        if self._finished.is_set():
            return
        self._finished.set()
        self._reset_peer_auth()
        self._emit({"type": "disconnected", "msg": str(reason)})
        self._emit({"type": "bye", "reason": str(reason)})
        self._teardown(notify=False)

    def _teardown(self, notify: bool = False) -> None:
        """关闭 socket，停掉线程。幂等，绝不抛异常。"""
        if notify:
            self._send_bye(ERR_PEER_LEFT)
        self._closing.set()
        self._connected = False
        for attr in ("_sock", "_peer"):
            sock = getattr(self, attr, None)
            if sock is None:
                continue
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass
            try:
                setattr(self, attr, None)
            except Exception:
                pass

    def close(self) -> None:
        """UI 调用：主动关闭连接。幂等，可重复调用。"""
        if not self._closing.is_set():
            self._send_bye("我方结束了联机")
        self._teardown(notify=False)

    # ---------------- 公共操作 ----------------
    # 返回 bool 是契约（None）的兼容超集：True = 意图已发出。
    # 注意：客户端是**非权威端**，返回 True 只代表"请求已送出"，
    # 不代表房主接受了 —— 一切以随后收到的 state 快照为准。
    #
    # 但"明显不可能"的意图会在本地就被拦下（手牌空 / 不是自己回合 / 费用不够），
    # 这样即使 UI 有 bug 反复点，也不会变成洪水打到房主。
    def play_card(self, card_index, target_index=None) -> bool:
        """发送出牌意图（只是意图，房主校验后才生效）。"""
        if not self._connected:
            self._error(ERR_NOT_CONNECTED)
            return False
        if not self.can_act_locally(card_index):
            return False
        msg = {"t": "play", "idx": _safe_int(card_index, -1)}
        if target_index is not None:
            msg["target"] = _safe_int(target_index, -1)
        return self._send(msg)

    def end_turn(self) -> bool:
        """发送结束回合意图。"""
        if not self._connected:
            self._error(ERR_NOT_CONNECTED)
            return False
        return self._send({"t": "end"})

    # ---------------- 本地预检（非权威，只是省流量/防误点） ----------------
    def my_turn(self) -> bool:
        """按最近一次快照判断：现在是不是自己的回合。"""
        snap = self._last_snap
        if not isinstance(snap, dict):
            return True                     # 还没收到快照就不拦
        return _safe_int(snap.get("current_side"), 1) == 1

    def can_act_locally(self, card_index=None) -> bool:
        """强烈建议 UI 在点牌前调用。True = 这个动作看起来是合法的。

        只依据**权威房主发来的最新快照**做判断，本身不做任何状态修改。
        房主仍然是唯一裁判 —— 返回 True 不代表一定成功。
        """
        snap = self._last_snap
        if not isinstance(snap, dict):
            return True
        if not self.my_turn():
            return False
        me = snap.get("me") or {}
        hand = me.get("hand") or []
        if not isinstance(hand, list) or not hand:
            return False
        if card_index is None:
            return True
        idx = _safe_int(card_index, -1)
        if idx < 0 or idx >= len(hand):
            return False
        card = hand[idx] if isinstance(hand[idx], dict) else {}
        if card.get("playable") is False:
            return False
        energy = _safe_int(me.get("energy"), 0)
        cost = _safe_int(card.get("cost"), 0)
        if cost >= 0 and cost > energy:
            return False
        return True

    def hand_size(self) -> int:
        """自己手牌张数（来自最新快照）。"""
        snap = self._last_snap
        if not isinstance(snap, dict):
            return 0
        return len(((snap.get("me") or {}).get("hand")) or [])

    def is_connected(self) -> bool:
        return bool(self._connected)


# --------------------------------------------------------------------------
# 房主（权威端）
# --------------------------------------------------------------------------
class Host(_Conn):
    """开房间的一方。跑 ``versus.VersusBattle``，广播每人一份快照。

    用法::

        h = Host(on_event)
        if not h.start():        # 端口被占
            ...                  # 事件里已有中文 error
        print(h.local_ip())      # 显示给玩家：让对方输这个 IP
        h.wait_for_client(60)    # 或轮询 h.poll()
        h.send_deck(cards)       # 我准备好啦
        h.wait_for_client_ready()
        h.play_card(2)           # 出第 2 张
        h.end_turn()
    """

    def __init__(self, on_event: Optional[Callable[[dict], None]] = None,
                 port: int = DEFAULT_PORT, name: str = "房主",
                 time_limit: Optional[float] = None,
                 token: Optional[str] = None,
                 require_code: bool = False) -> None:
        # 房主默认**生成**一张票据；require_code=False 时只在日志里展示房间码，
        # 不强制对方输入（局域网默认行为，向后兼容）。
        tk = None
        if token is None:
            token = _sess.new_token()
        try:
            tk = _sess.Ticket(token=str(token), host_name=name,
                              require_code=bool(require_code))
        except Exception:
            tk = None
        super().__init__(on_event, name, ticket=tk)
        self.port = _safe_int(port, DEFAULT_PORT)
        self.side = 0
        self._server: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._listening = False
        self._my_deck: List[str] = []
        self._peer_deck: List[str] = []
        self._i_ready = False
        self._battle = None
        self._log_cursor = 0
        self._time_limit = time_limit
        self._last_snap0: Optional[dict] = None      # 房主自己的最新快照
        self._last_tick = _now()
        self._over_sent = False
        # 房主作弊开关：默认**关闭**。开启后房主可用兑换码（客户端永远不能）。
        self._cheats_enabled = False
        # 对手作弊标记（彩蛋）：一旦判定，对方头顶显示「挂狗」。
        self._cheater_flagged = False
        self._cheater_reason = ""
        # 注意：这里**不能**预设 _peer_name。
        # `_handle` 里用 `if not self._peer_name:` 判断"是否已收到对方 hello"，
        # 预设值会让房主永远不回 hello，客户端便一直等鉴权、连不上。
        # 真正的名字在收到 hello 时写入（_sanitize_name 有兜底）。

    # ---------------- 房主作弊开关 ----------------
    def set_cheats(self, on: bool) -> None:
        """开启/关闭房主作弊。只影响房主自己，客户端无论如何都不能作弊。"""
        self._cheats_enabled = bool(on)
        self._emit({"type": "cheats", "enabled": self._cheats_enabled,
                    "msg": ("房主已开启作弊" if self._cheats_enabled
                            else "房主已关闭作弊")})
        try:
            self.log("房主%s了作弊开关。" % ("开启" if self._cheats_enabled else "关闭"))
        except Exception:
            pass

    def cheats_enabled(self) -> bool:
        return bool(self._cheats_enabled)

    def redeem(self, code: str) -> Tuple[bool, str]:
        """房主使用兑换码。返回 (成功, 提示)。

        * 开关没开 -> 拒绝
        * 对局没开始 -> 拒绝
        * 神人模式（最高难度）-> 拒绝（荣誉挑战）
        客户端**没有**对应接口，只能发意图，房主一律拒绝作弊类消息。
        """
        if not self._cheats_enabled:
            return False, "房主作弊开关未开启。"
        if self._battle is None:
            return False, "对战还没开始。"
        try:
            from core import cheats as _ch
            reg = getattr(self, "_cheat_reg", None)
            if reg is None:
                reg = self._cheat_reg = _ch.CheatRegistry()
            ok, msg = reg.redeem(code, battle=self._battle)
        except Exception as exc:
            return False, "兑换失败：%s" % exc
        if ok:
            self._broadcast()
            self._emit({"type": "cheat", "code": str(code), "msg": msg})
        else:
            self._error(msg)
        return ok, msg

    # ---------------- 监听 ----------------
    def start(self) -> bool:
        """开始监听。返回 False 表示端口被占用（已发中文 error 事件）。"""
        if self._listening:
            return True
        if self._server is not None:
            return False
        srv = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                srv.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            srv.bind(("", self.port))
            srv.listen(2)
            srv.settimeout(ACCEPT_TIMEOUT)
        except OSError as exc:
            try:
                if srv is not None:
                    srv.close()
            except Exception:
                pass
            if getattr(exc, "errno", None) in (errno.EADDRINUSE, errno.EACCES):
                self._error(ERR_PORT_BUSY.format(port=self.port))
            else:
                self._error("无法在端口 %d 上开房间：%s" % (self.port, exc))
            return False
        except Exception as exc:
            self._error("无法在端口 %d 上开房间：%s" % (self.port, exc))
            return False

        self._server = srv
        self._listening = True
        # bind 到 0 端口时把真实端口读回来，方便显示
        try:
            self.port = int(srv.getsockname()[1])
        except Exception:
            pass
        self._emit({"type": "listening", "port": self.port, "ip": local_ip()})
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="netplay-accept", daemon=True)
        self._accept_thread.start()
        return True

    def local_ip(self) -> str:
        """本机局域网 IP，显示给玩家（如 ``10.16.64.27``）。"""
        return local_ip()

    def _announce_connected(self, addr=None) -> None:
        """确认（或无需）鉴权后，对外声明"连上了"。只发一次。"""
        if getattr(self, "_announced", False):
            return
        self._announced = True
        self._emit({"type": "connected",
                    "host": (addr[0] if addr else ""),
                    "port": (addr[1] if addr else 0)})

    def _accept_loop(self) -> None:
        srv = self._server
        if srv is None:
            return
        while not self._closing.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                break
            if self._closing.is_set():
                try:
                    conn.close()
                except Exception:
                    pass
                break
            if self._peer is not None:
                # 已经有对手了，礼貌拒绝第二个连接
                try:
                    conn.sendall((json.dumps(
                        {"t": "bye", "reason": "房间已满（已有对手在线）。"},
                        ensure_ascii=False) + "\n").encode("utf-8"))
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
                continue
            self._attach(conn, addr)

    def _attach(self, conn: socket.socket, addr) -> None:
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._peer = conn
        self._sock = conn
        self._connected = True
        # 注意：这里**先不发 connected**。
        # 如果本房要求房间码，对方的第一条消息必须带正确签名，
        # 校验通过后才算真正连上（否则「连上」的瞬间 UI 就切界面了，
        # 输错码的人照样能进来 —— 这正是之前的漏洞）。
        self._auth_pending = bool(
            getattr(getattr(self, "_ticket", None), "require_code", False))
        if not self._auth_pending:
            self._announce_connected(addr)
        self._reader = threading.Thread(
            target=self._reader_loop, args=(conn,),
            name="netplay-host-recv", daemon=True)
        self._reader.start()
        self._start_heartbeat()

    def wait_for_client(self, timeout: Optional[float] = None) -> bool:
        """阻塞等待客户端连接（窗口期发消息用）。返回是否连上。"""
        deadline = None if timeout is None else _now() + max(0.0, float(timeout))
        while True:
            if self._connected and self._peer is not None:
                return True
            if self._closing.is_set() or self._finished.is_set():
                return False
            if deadline is not None and _now() >= deadline:
                return False
            time.sleep(0.02)

    # ---------------- 握手 ----------------
    def _handle(self, msg: dict) -> None:
        t = msg.get("t")
        if t == "hello":
            if not self._peer_name:
                ver = _safe_int(msg.get("ver"), 0)
                if ver != PROTOCOL_VERSION:
                    self._send({"t": "error",
                                "msg": ERR_PROTOCOL.format(ver=ver,
                                                           need=PROTOCOL_VERSION)})
                    self._send_bye("协议版本不兼容")
                    self._teardown(notify=False)
                    return
                # 代码完整性校验：双方必须跑同一份未改动的代码。
                # 不匹配就**伪装成网络超时**（不告诉对方真实原因，
                # 免得被针对性绕过）。
                try:
                    _ok, _kind, _why = _check_peer_integrity(msg)
                except Exception:
                    _ok, _kind, _why = True, VER_OK, ""
                if not _ok:
                    self._record_integrity_violation(msg, _why or _kind)
                    if _kind == VER_MISMATCH:
                        # 版本不一致 -> 明确告诉玩家去更新
                        self._reject_version_mismatch(_why)
                    else:
                        # 疑似篡改 -> 伪装超时
                        self._fake_timeout()
                    return

                self._peer_name = _sanitize_name(msg.get("name"), "对手")
                self._send({"t": "hello", "ver": PROTOCOL_VERSION,
                            "name": self.name, "side": 1})
                self._emit({"type": "peer", "name": self._peer_name, "side": 1})
            return
        if t == "chat":
            self._on_peer_chat(msg)
            return
        if t == "profile":
            self._on_peer_profile(msg)
            return
        if t in ("ready", "deck"):
            self._on_peer_ready(msg)
            return
        if t in ("play", "end"):
            self._on_intent(msg)
            return
        if t in ("pong", "ping", "bye", "error"):
            return                       # 心跳/收尾由基类处理
        if t == "state":
            # 客户端没有资格给房主发快照 —— 这一定是伪造/篡改尝试。
            cheat = classify_cheat(msg)
            if cheat:
                self._flag_cheater(cheat)
            # 复用统一文案表，避免同一句话在两处各自维护
            self._send({"t": "error",
                        "msg": _PRIVILEGED_TYPES.get(
                            t, "对战状态只能由房主裁决，该消息已忽略。")})
            return
        # 走到这里的都是协议外的消息 —— 正常客户端不会发明协议，判定作弊。
        cheat = classify_cheat(msg)
        if cheat:
            self._flag_cheater(cheat)
        self._send({"t": "error", "msg": "不支持的消息类型：%s" % str(t)[:24]})

    def _on_peer_ready(self, msg: dict) -> None:
        cards = msg.get("cards")
        if self._peer_ready:
            # 已经上报过卡组：重复上报（想中途换牌 / 绕过 ready）一律拒绝，
            # 绝不能静默忽略 —— 那会让作弊者以为得手了。
            self._send({"t": "error",
                        "msg": "卡组已经提交过了，对局中不能更换卡组。"})
            return
        if not isinstance(cards, list) or not cards:
            self._send({"t": "error", "msg": ERR_DECK_EMPTY})
            return
        if len(cards) > MAX_CARDS:
            self._send({"t": "error", "msg": ERR_DECK_TOO_BIG.format(max=MAX_CARDS)})
            return
        clean: List[str] = []
        for cid in cards:
            if not _is_valid_card_id(cid):
                self._send({"t": "error", "msg": ERR_DECK_BAD_CARD})
                return
            clean.append(cid)
        self._peer_deck = clean
        self._peer_ready = True
        self._emit({"type": "peer_ready", "name": self._peer_name})
        self._maybe_start()

    def _flag_cheater(self, why: str) -> None:
        """判定对手作弊：给他挂标签，并通知双方。

        房主用 ``cheater`` 事件通知**自己**的界面（对方头顶挂「挂狗」），
        同时给作弊者本人发 ``shame`` —— 他屏幕上会弹那行巨大的红字。
        """
        if self._cheater_flagged:
            return
        self._cheater_flagged = True
        self._cheater_reason = str(why)
        # 1) 给作弊者本人弹红字
        try:
            self._send({"t": "shame", "text": cheat_text("shame"),
                        "label": cheat_text("label"), "reason": str(why)})
        except Exception:
            pass
        # 2) 通知房主界面：对方是挂狗
        self._emit({"type": "cheater", "side": 1, "name": self._peer_name,
                    "label": CHEAT_LABEL, "reason": str(why)})
        try:
            self.log(CHEAT_LOG_TEXT % str(why))
        except Exception:
            pass

    def _on_intent(self, msg: dict) -> None:
        """核心反作弊路径：客户端只能发"意图"，房主校验后裁决。"""
        t = msg.get("t")
        # 先做作弊判定 —— 蓄意发包直接挂标签（彩蛋），再照常拒绝执行。
        cheat = classify_cheat(msg)
        if cheat:
            self._flag_cheater(cheat)
        # 只有 play/end 才是"操作意图"。其它类型即使通过了通用白名单，
        # 也绝不能在这个入口被当成操作执行（防越权改状态）。
        if t not in INTENT_TYPES:
            reason = "无效的操作指令：%s" % str(t)[:24]
            self._send({"t": "error", "msg": reason})
            self._emit({"type": "rejected", "msg": reason})
            return
        reason = validate_client_intent(msg)
        if reason:
            self._send({"t": "error", "msg": reason})
            self._emit({"type": "rejected", "msg": reason})
            return
        if self._battle is None:
            self._send({"t": "error", "msg": "对战还没开始。"})
            return
        # 速率检测：机器人/脚本会在极短时间内狂发请求
        try:
            if not self._rate_ok():
                self._flag_cheater("请求速率异常（疑似脚本）")
                self._send({"t": "error", "msg": "操作太频繁。"})
                return
        except Exception:
            pass
        if t == "play":
            idx = int(msg.get("idx"))
            tgt = msg.get("target")
            if tgt is not None:
                tgt = int(tgt)
            if not _battle_play(self._battle, 1, idx, tgt):
                self._send({"t": "error", "msg": ERR_CANNOT_PLAY})
                self._emit({"type": "rejected", "msg": ERR_CANNOT_PLAY})
                return
        else:   # "end"
            if not _battle_end_turn(self._battle, 1):
                self._send({"t": "error", "msg": "现在不能结束回合。"})
                return
        self._broadcast()

    # ---------------- 开局 ----------------
    def send_deck(self, card_ids: list) -> None:
        """上报本方卡组并标记 ready。卡组非法则只报错、不发 ready。"""
        cards = list(card_ids or [])
        if not cards:
            self._error(ERR_DECK_EMPTY)
            return
        if len(cards) > MAX_CARDS:
            self._error(ERR_DECK_TOO_BIG.format(max=MAX_CARDS))
            return
        clean: List[str] = []
        for cid in cards:
            if not _is_valid_card_id(cid):
                self._error(ERR_DECK_BAD_CARD)
                return
            clean.append(cid)
        self._my_deck = clean
        self._i_ready = True
        if self._connected:
            self._send({"t": "ready", "cards": clean})
        self._emit({"type": "ready", "side": 0})
        self._maybe_start()

    def _maybe_start(self) -> None:
        if self._started or not self._i_ready or not self._peer_ready:
            return
        if not self._connected:
            return
        self._started = True
        battle, err = _make_battle(self._my_deck, self._peer_deck)
        if battle is None:
            self._started = False
            self._send({"t": "error", "msg": err})
            self._error(err)
            return
        self._battle = battle
        self._log_cursor = 0
        self._last_tick = _now()
        try:
            snap0 = _battle_snapshot(battle, 0)
            snap1 = _battle_snapshot(battle, 1)
        except Exception as exc:
            self._started = False
            msg = "开局失败：%s" % exc
            self._send({"t": "error", "msg": msg})
            self._error(msg)
            return
        self._last_snap0 = snap0
        names = [self.name, self._peer_name or "对手"]
        self._send({"t": "start", "your_side": 1, "names": names,
                    "snapshot": snap1})
        self._emit({"type": "start", "side": 0, "names": names,
                    "snapshot": snap0})
        self._flush_log()

    # ---------------- 广播 ----------------
    def _flush_log(self) -> None:
        """把引擎新增的战斗日志作为 log 事件发给双方（数据包很小，值得）。"""
        if self._battle is None:
            return
        try:
            lines, cursor = _battle_log_delta(self._battle, self._log_cursor)
        except Exception:
            return
        self._log_cursor = cursor
        if not lines:
            return
        self._emit({"type": "log", "msg": "\n".join(lines)})
        if self._connected:
            self._send({"t": "log", "msg": "\n".join(lines)})

    def _broadcast(self) -> None:
        """对局推进后：给客户端发它的快照，给自己留自己的快照。

        **每人一份**：客户端拿 ``snapshot_for(1)``（自己手牌全、对手只有数量），
        房主拿 ``snapshot_for(0)``。对手手牌内容永不出网。
        """
        if self._battle is None:
            return
        snap1 = _battle_snapshot(self._battle, 1)     # 客户端视角
        if snap1 is not None and self._connected:
            self._send({"t": "state", "payload": snap1})
        snap0 = _battle_snapshot(self._battle, 0)     # 房主视角
        self._last_snap0 = snap0
        if snap0 is not None:
            self._emit({"type": "state", "payload": snap0})
        self._flush_log()
        if not self._over_sent and _battle_over(self._battle):
            self._over_sent = True
            self._emit({"type": "over", "winner": _battle_winner(self._battle),
                        "names": [self.name, self._peer_name or "对手"]})
            if self._connected:
                self._send({"t": "over", "winner": _battle_winner(self._battle)})

    # ---------------- 回合限时 ----------------
    def tick(self, dt: Optional[float] = None) -> None:
        """UI 调用：推进回合计时。返回 True 表示本次发生了自动换手（需刷新界面）。

        ``versus.VersusBattle.tick(dt)`` 累计到 ``turn_seconds`` 会自动结束
        当前方回合。UI 每秒调一次最省事；不给 ``dt`` 时按距上次调用的真实
        间隔计算，所以多调几次也不会把计时器跑快。
        """
        if self._battle is None:
            return False
        now = _now()
        if dt is None:
            dt = now - self._last_tick
        self._last_tick = now
        if dt < 0:
            dt = 0.0
        side_before = _battle_current_side(self._battle)
        _battle_tick(self._battle, dt)
        if _battle_current_side(self._battle) != side_before or _battle_over(self._battle):
            self._broadcast()
            return True
        return False

    def time_left(self) -> Optional[float]:
        """当前方剩余秒数（显示倒计时用）。"""
        if self._battle is None:
            return None
        return _battle_time_left(self._battle)

    # ---------------- 房主自己的操作 ----------------
    # 说明：契约里这两个方法返回 None。这里**额外**返回 bool（True=操作被接受），
    # 属于兼容超集 —— 忽略返回值的调用方行为完全不变，UI 却能立刻知道
    # 「这张牌出不了（费用不够/不是你的回合）」，不必去轮询 error 事件。
    def play_card(self, card_index, target_index=None) -> bool:
        """房主出牌：直接进本地权威引擎，不等网络。返回是否被接受。"""
        if self._battle is None:
            self._error("对战还没开始。")
            return False
        idx = _safe_int(card_index, -1)
        if idx < 0:
            self._error(ERR_CANNOT_PLAY)
            return False
        tgt = None if target_index is None else _safe_int(target_index, -1)
        if not _battle_play(self._battle, 0, idx, tgt):
            self._error(ERR_CANNOT_PLAY)
            return False
        self._broadcast()
        return True

    def end_turn(self) -> bool:
        if self._battle is None:
            self._error("对战还没开始。")
            return False
        if not _battle_end_turn(self._battle, 0):
            self._error("现在不能结束回合。")
            return False
        self._broadcast()
        return True

    def my_turn(self) -> bool:
        """现在是不是房主（side 0）的回合。UI 用来决定按钮可用性。"""
        if self._battle is None:
            return False
        return _battle_current_side(self._battle) == 0

    def snapshot(self) -> Optional[dict]:
        """房主视角的最新快照（UI 也可以只用 poll() 的 state 事件）。"""
        return self._last_snap0

    # ---------------- 关闭 ----------------
    def _drop_peer(self, reason: str) -> None:
        super()._drop_peer(reason)
        self._connected = False

    def close(self) -> None:
        """关闭房间：先给对手发 bye，再收摊。可重复调用。"""
        if self._connected and not self._closing.is_set():
            self._send_bye("房主关闭了房间。")
        self._closing.set()
        srv = self._server
        self._server = None
        if srv is not None:
            try:
                srv.close()
            except Exception:
                pass
        self._listening = False
        self._teardown(notify=False)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# --------------------------------------------------------------------------
# 客户端（加入方）
# --------------------------------------------------------------------------
class Client(_Conn):
    """加入方。只发意图，一切状态以房主广播的快照为准。"""

    def __init__(self, on_event: Optional[Callable[[dict], None]] = None,
                 name: str = "挑战者",
                 token: Optional[str] = None,
                 require_code: bool = True) -> None:
        tk = None
        # 规范化：去掉分隔符、统一大写 —— 用户可能输入 "abcd-2345"，
        # 而房主那边是 normalize 过的；两边密钥必须逐字节一致，
        # 否则 HMAC 对不上（前缀码就会连不上）。
        norm = _sess.normalize_code(token) if token else ""
        if norm:
            try:
                tk = _sess.Ticket(token=norm, require_code=bool(require_code))
            except Exception:
                tk = None
        super().__init__(on_event, name, ticket=tk)
        # 收发分离：发送用 _ticket（带自己的发送序号），
        # 收件另用一张，避免两边序号空间混在一起导致误判"重放"。
        self._recv_ticket = None
        if tk is not None:
            try:
                self._recv_ticket = _sess.Ticket(
                    token=tk.token, require_code=True)
            except Exception:
                self._recv_ticket = None
        self.token = str(token or "")
        self.side = 1
        self._my_deck: List[str] = []
        self._i_ready = False
        self._last_snap: Optional[dict] = None
        self._connected_once = False

    # ---------------- 连接 ----------------
    def connect(self, host: str, port: int = DEFAULT_PORT, timeout: float = 8) -> bool:
        """连接房主。返回 False 表示失败（已发中文 error 事件），不抛异常。"""
        host = (host or "").strip()
        port = _safe_int(port, DEFAULT_PORT)
        if not host:
            self._error("请输入房主的 IP 地址。")
            return False
        if self._connected:
            return True
        if self._sock is not None:
            self._error("已经连接过了，请先断开。")
            return False
        try:
            timeout = max(0.5, float(timeout))
        except (TypeError, ValueError):
            timeout = 8.0
        self._emit({"type": "connecting", "host": host, "port": port})
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.settimeout(1.0)
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
        except socket.timeout:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
            self._error(ERR_TIMEOUT.format(host=host, port=port))
            return False
        except OSError as exc:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
            if getattr(exc, "errno", None) == errno.ECONNREFUSED:
                self._error("连接被拒绝：%s:%d 上没有房间在等待（确认对方点了"
                            "「开房间」）。" % (host, port))
            else:
                self._error(ERR_CONNECT_FAIL.format(host=host, port=port))
            return False
        except Exception as exc:
            self._error("连接失败：%s" % exc)
            return False

        self._sock = sock
        self._connected = True
        self._connected_once = True
        self._buf = b""
        self._closing.clear()
        # 带了房间码时，要等房主回一条验签通过的消息才宣告连上，
        # 否则输错码的人本地已经切到卡组界面了（界面与实际不符）。
        self._awaiting_auth = bool(
            getattr(getattr(self, "_ticket", None),
                    "require_code", False))
        self._host_ip = host
        self._host_port = port
        if not self._awaiting_auth:
            self._emit({"type": "connected", "host": host,
                        "port": port})
        self._reader = threading.Thread(
            target=self._reader_loop, args=(sock,),
            name="netplay-client-recv", daemon=True)
        self._reader.start()
        self._start_heartbeat()
        # 自报家门（附带代码完整性信息，房主会校验）
        hello = {"t": "hello", "ver": PROTOCOL_VERSION, "name": self.name}
        try:
            _info = _integrity_snapshot()
            if _info.get("hash"):
                hello["hash"] = _info["hash"]
                hello["did"] = _info.get("did", "")
                hello["problems"] = _info.get("problems", [])
            # 带上版本标签：版本不一致时能让对方看到「对方的版本：xxx」
            try:
                from core import version as _V
                hello["label"] = _V.VERSION_LABEL
            except Exception:
                pass
        except Exception:
            pass
        # 把「我输入的码」告诉房主 —— 房主用它验签（前缀匹配也行）
        try:
            tk = getattr(self, "_ticket", None)
            if tk is not None and tk.token:
                hello["code"] = tk.token
        except Exception:
            pass
        self._send(hello)
        return True

    # ---------------- 消息 ----------------
    def _handle(self, msg: dict) -> None:
        t = msg.get("t")
        if t == "hello":
            ver = _safe_int(msg.get("ver"), 0)
            if ver != PROTOCOL_VERSION:
                self._error(ERR_PROTOCOL.format(ver=ver, need=PROTOCOL_VERSION))
                self._send_bye("协议版本不兼容")
                self._teardown(notify=False)
                return
            self._peer_name = _sanitize_name(msg.get("name"), "房主")
            self._emit({"type": "peer", "name": self._peer_name, "side": 0})
            return
        if t == "start":
            self._started = True
            snap = msg.get("snapshot")
            if isinstance(snap, dict):
                self._last_snap = snap
            self._emit({"type": "start",
                        "side": 1,
                        "names": list(msg.get("names") or []),
                        "snapshot": snap if isinstance(snap, dict) else None})
            if isinstance(snap, dict):
                self._emit({"type": "state", "payload": snap})
            return
        if t == "state":
            snap = msg.get("payload")
            if isinstance(snap, dict):
                # 快照可信度：房主报来的数值超出合理范围 -> 标记异常
                try:
                    bad = _snapshot_sane(snap)
                    if bad:
                        self._self_snapshot_flags = bad[:8]
                except Exception:
                    pass
                self._last_snap = snap
                self._emit({"type": "state", "payload": snap})
            return
        if t == "log":
            self._emit({"type": "log", "msg": str(msg.get("msg") or "")})
            return
        if t == "over":
            w = msg.get("winner")
            self._emit({"type": "over", "winner": w if w in (0, 1) else None})
            return
        if t == "shame":
            # 房主判定本客户端作弊：弹巨大红字。
            self._emit({"type": "shame",
                        "text": str(msg.get("text") or CHEAT_SHAME_TEXT),
                        "label": str(msg.get("label") or CHEAT_LABEL),
                        "reason": str(msg.get("reason") or "")})
            return
        if t == "chat":
            # 房主发来的聊天 —— 合法，交给上层显示
            self._on_peer_chat(msg)
            return
        if t == "profile":
            self._on_peer_profile(msg)
            return
        if t in ("ready", "deck"):
            self._emit({"type": "peer_ready", "name": self._peer_name})
            return
        if t in ("play", "end"):
            # 客户端是权威模型的"只读端"：绝不接受房主以外的操作指令
            self._error("收到无效的下行指令，已忽略。")
            return
        self._error("不支持的消息类型：%s" % str(t)[:24])

    # ---------------- 握手 ----------------
    def send_deck(self, card_ids: list) -> None:
        """上报卡组并 ready。未连接时只报错。"""
        cards = list(card_ids or [])
        if not cards:
            self._error(ERR_DECK_EMPTY)
            return
        if len(cards) > MAX_CARDS:
            self._error(ERR_DECK_TOO_BIG.format(max=MAX_CARDS))
            return
        clean: List[str] = []
        for cid in cards:
            if not _is_valid_card_id(cid):
                self._error(ERR_DECK_BAD_CARD)
                return
            clean.append(cid)
        self._my_deck = clean
        self._i_ready = True
        if not self._connected:
            self._error(ERR_NOT_CONNECTED)
            return
        self._send({"t": "ready", "cards": clean})
        self._emit({"type": "ready", "side": 1})

    def snapshot(self) -> Optional[dict]:
        """最近一次收到的快照（本方视角）。"""
        return self._last_snap

    def close(self) -> None:
        if self._connected and not self._closing.is_set():
            self._send_bye("我方离开了房间")
        self._teardown(notify=False)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# --------------------------------------------------------------------------
# 便捷函数（给 UI 一行起步）
# --------------------------------------------------------------------------
def start_host(on_event=None, port: int = DEFAULT_PORT,
               name: str = "房主") -> Optional[Host]:
    """开房间；失败（端口占用等）返回 None，错误走事件。"""
    h = Host(on_event, port=port, name=name)
    if not h.start():
        return None
    return h


def join_game(host: str, port: int = DEFAULT_PORT, on_event=None,
              name: str = "挑战者", timeout: float = 8) -> Optional[Client]:
    """加入房间；失败返回 None，错误走事件。"""
    c = Client(on_event, name=name)
    if not c.connect(host, port=port, timeout=timeout):
        c.close()
        return None
    return c


__all__ = [
    "DEFAULT_PORT", "PROTOCOL_VERSION", "PING_INTERVAL", "PONG_TIMEOUT",
    "Host", "Client", "local_ip", "free_port", "engine_available",
    "engine_error", "validate_client_intent", "start_host", "join_game",
    "ERR_PORT_BUSY", "ERR_CONNECT_FAIL", "ERR_TIMEOUT", "ERR_PEER_LEFT",
    "ERR_HEARTBEAT",
]
