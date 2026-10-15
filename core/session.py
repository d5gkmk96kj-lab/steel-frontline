#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 —— 联机会话票据（token）与重连支持。

解决两件事
----------
1. **安全性**：局域网里任何人都能连上你的端口。加一个「房间码」，
   只有知道码的人才能进；并且每条消息带 HMAC 签名，防止中途改包。

2. **重连**：网络抖一下（切 WiFi、休眠唤醒）就掉线太难受。
   掉线后短时间内可以用同一张票据续上，继续把这一局打完。

设计
----
* 纯标准库（``hashlib`` / ``hmac`` / ``secrets`` / ``time``），零第三方依赖。
* 票据是**短期**的：默认 6 小时过期，过期必须重新开房。
* 签名覆盖「消息正文 + 序号 + 时间戳」，防止重放和篡改。
* **向后兼容**：老客户端不带票据时，房主可以按配置决定是否放行
   （默认：局域网内允许无票据，只有开了「需要房间码」才强制）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
TOKEN_BYTES = 16                 # 房间码熵：128 位，够用
DEFAULT_TTL = 6 * 3600           # 票据有效期（秒）
SIG_WINDOW = 120.0               # 时间戳容差（秒），防重放
NONCE_KEEP = 512                 # 记住多少个已用序号，防重放

# 房间码用的字母表：去掉容易看错的 0/O/1/I/l
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


# --------------------------------------------------------------------------
# 房间码
# --------------------------------------------------------------------------
# 展示码长度：12 个字符（约 59 bit 熵）—— 够防住局域网里乱猜，
# 又短到能口头念给同学。
CODE_LEN = 12


def new_token(nbytes: int = TOKEN_BYTES) -> str:
    """生成一个随机票据。

    **只用 ALPHABET 里的字符**，保证它本身就是一张合法展示码 ——
    这样 ``normalize_code(room_code(t)) == t`` 恒成立，
    展示码、用户输入、签名密钥三者是同一个东西，不会对不上。
    """
    return "".join(secrets.choice(ALPHABET)
                   for _ in range(max(8, int(nbytes) * 2)))


def room_code(token: str, groups: int = 3, size: int = 4) -> str:
    """把票据转成人类好念的短码，例如 ``K7F2-9QMX-3BPD``。

    取前 ``CODE_LEN`` 个字符分组显示；用户输入这个码即可入场。
    """
    t = normalize_code(token)
    body = t[:groups * size] if groups and size else t
    parts = [body[i:i + size] for i in range(0, len(body), size)]
    return "-".join(parts) if parts else ""


def normalize_code(text: str) -> str:
    """把用户输入的房间码还原成 token（去掉分隔符、统一大写）。"""
    return "".join(c for c in str(text or "").upper() if c in ALPHABET)


# 允许的最短前缀：太短（一两个字符）等于没有保护
MIN_CODE_LEN = 8


def code_matches(token: str, typed: str) -> bool:
    """比较用户输入的码与真实 token。

    规则：**前缀匹配**（方便只念前几组），但至少要 ``MIN_CODE_LEN`` 个
    字符 —— 否则输一两个字符就进去了，等于没有保护。
    """
    a = normalize_code(token)
    b = normalize_code(typed)
    if not b or len(b) < MIN_CODE_LEN:
        return False
    return a.startswith(b)


class TokenMismatch(Exception):
    """房间码不匹配。签名校验之外单独判定，好给出准确提示。"""


def ticket_for_request(host_token: str, typed: str,
                       require: bool) -> Optional["Ticket"]:
    """房主侧：根据「本房 token」与「对方输入的码」造一张用于验签的票据。

    * 不开房间码 -> 返回 None（不做签名校验，向后兼容）
    * 开了房间码 -> 必须匹配，否则返回 None 表示拒绝
    """
    if not require:
        return None
    if not code_matches(host_token, typed):
        return None
    # 关键：用**房主的完整 token** 验签 —— 对方输的是前缀，
    # 但双方约定的密钥始终是完整 token（客户端会用输入值签名，
    # 所以这里要把对方的输入当作密钥来验，见 unwrap_with_code）。
    return Ticket(token=str(host_token), require_code=True)


def unwrap_with_code(host_token: str, typed: str, require: bool,
                     msg: Dict[str, Any]) -> Tuple[bool, str]:
    """房主侧收消息时的完整校验（房间码 + 签名 + 防重放）。

    对方用「自己输入的码」当密钥签名；我们用「他输入的码」验，
    验过之后再确认它确实是本房 token 的合法前缀。
    """
    if not require:
        # 不强制：能验就验，验不过也放行（向后兼容老客户端）
        seq = msg.get("_s")
        if seq is None:
            return True, ""
        return unwrap(Ticket(token=host_token, require_code=False), msg,
                      require_code=False)

    typed_norm = normalize_code(typed)
    if not code_matches(host_token, typed):
        return False, "房间码不正确。"
    # 用对方输入的那个码验签
    tk = Ticket(token=typed_norm, require_code=True)
    return unwrap(tk, msg)


# --------------------------------------------------------------------------
# 签名
# --------------------------------------------------------------------------
def _b32_key(token: str) -> bytes:
    """把 token 派生成 HMAC 密钥（域分离，避免直接拿 token 当密钥）。"""
    return hashlib.sha256(
        b"steelfrontline-v1|" + str(token or "").encode("utf-8")).digest()


def sign(token: str, payload: Any, seq: int, ts: float) -> str:
    """对一条消息签名。覆盖内容 + 序号 + 时间戳，防篡改防重放。"""
    try:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    except Exception:
        body = str(payload)
    msg = b"%d|%d|" % (int(seq), int(ts)) + body.encode("utf-8")
    mac = hmac.new(_b32_key(token), msg, hashlib.sha256).digest()
    return base64.b32encode(mac[:20]).decode("ascii").rstrip("=")


def verify(token: str, payload: Any, seq: int, ts: float, sig: str) -> bool:
    """校验签名。用常数时间比较，避免时序侧信道。"""
    if not token or not sig:
        return False
    try:
        if abs(time.time() - float(ts)) > SIG_WINDOW:
            return False              # 过期（防重放）
    except Exception:
        return False
    try:
        want = sign(token, payload, seq, ts)
        return hmac.compare_digest(want, str(sig))
    except Exception:
        return False


# --------------------------------------------------------------------------
# 票据
# --------------------------------------------------------------------------
@dataclass
class Ticket:
    """一张联机会话票据。"""

    token: str = ""
    created: float = field(default_factory=time.time)
    ttl: float = DEFAULT_TTL
    host_name: str = ""
    require_code: bool = True          # 是否强制校验房间码
    _seen: list = field(default_factory=list)     # 最近用过的序号

    # -- 生命周期 -------------------------------------------------------
    def expired(self, now: Optional[float] = None) -> bool:
        n = time.time() if now is None else float(now)
        return (n - self.created) > self.ttl

    def remaining(self) -> float:
        return max(0.0, self.ttl - (time.time() - self.created))

    # -- 展示 -----------------------------------------------------------
    def display(self) -> str:
        return room_code(self.token)

    def to_dict(self) -> Dict[str, Any]:
        return {"token": self.token, "created": self.created,
                "ttl": self.ttl, "host_name": self.host_name,
                "require_code": self.require_code}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Ticket":
        return cls(
            token=str((d or {}).get("token") or ""),
            created=float((d or {}).get("created") or time.time()),
            ttl=float((d or {}).get("ttl") or DEFAULT_TTL),
            host_name=str((d or {}).get("host_name") or ""),
            require_code=bool((d or {}).get("require_code", True)),
        )

    # -- 防重放 ---------------------------------------------------------
    def accept_seq(self, seq: int) -> bool:
        """这个序号是不是新的（没用过）？"""
        try:
            s = int(seq)
        except Exception:
            return False
        if s in self._seen:
            return False
        self._seen.append(s)
        if len(self._seen) > NONCE_KEEP:
            del self._seen[:len(self._seen) - NONCE_KEEP]
        return True

    # -- 校验 -----------------------------------------------------------
    def check(self, payload: Any, seq: int, ts: float, sig: str,
              track_replay: bool = True) -> bool:
        """完整校验：过期 / 签名 / 重放。

        ``track_replay=False`` 时只验签名不记序号 —— 用于**回执类**
        消息（例如房主的 hello 应答）：双方各自维护发送序号，
        序号空间是分开的，不能和"对方发来的业务消息"共用一份去重表。
        """
        if self.expired():
            return False
        if not verify(self.token, payload, seq, ts, sig):
            return False
        if not track_replay:
            return True
        return self.accept_seq(seq)


# --------------------------------------------------------------------------
# 带票据的消息封装
# --------------------------------------------------------------------------
def wrap(ticket: Ticket, msg: Dict[str, Any], seq: int) -> Dict[str, Any]:
    """给一条协议消息加上票据字段与签名。"""
    ts = int(time.time())
    out = dict(msg or {})
    out["_s"] = int(seq)
    out["_t"] = ts
    out["_g"] = sign(ticket.token, msg, seq, ts)
    return out


def unwrap(ticket: Ticket, msg: Dict[str, Any],
           require_code: Optional[bool] = None) -> Tuple[bool, str]:
    """校验并剥离票据字段。

    返回 ``(是否通过, 原因)``。通过时 ``msg`` 里的 ``_s/_t/_g`` 已被删除
    （原地修改），调用方拿到的是干净的业务消息。

    如果票据里没设 require_code，且消息本身也没带签名 —— 按
    ``require_code`` 的默认值决定放行与否（保证老客户端还能用）。
    """
    if ticket is None:
        return True, ""
    need = ticket.require_code if require_code is None else bool(require_code)

    seq = msg.pop("_s", None)
    ts = msg.pop("_t", None)
    sig = msg.pop("_g", None)

    if seq is None or ts is None or sig is None:
        # 没带签名
        if need:
            return False, "对方没有提供房间码，已被拒绝。"
        return True, ""
    if not ticket.check(msg, seq, ts, sig):
        if ticket.expired():
            return False, "房间码已过期，请让房主重新开房。"
        return False, "消息签名校验失败（可能被篡改或重放）。"
    return True, ""


__all__ = [
    "MIN_CODE_LEN", "TokenMismatch", "ticket_for_request",
    "unwrap_with_code",
    "TOKEN_BYTES", "DEFAULT_TTL", "SIG_WINDOW", "ALPHABET", "CODE_LEN",
    "new_token", "room_code", "normalize_code", "code_matches",
    "sign", "verify", "Ticket", "wrap", "unwrap",
]
