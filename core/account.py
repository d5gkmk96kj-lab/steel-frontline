#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账号系统：设备锁定 + 恢复码 + 离线优先。

设计（按用户要求）
------------------
* **一台设备一个账号** —— 账号与设备指纹绑定，同一台机器不能重复注册
* **离线优先** —— 打开游戏自动进入账号，**不需要联网**。
  单机内容随时能玩。
* **恢复码** —— 换设备时用恢复码把账号迁过去
* **首次注册时同步哈希到服务器** —— 记录了"这个账号存在过"，
  服务器上线后可用于跨设备校验；没网也不影响注册

数据落盘
--------
``<data>/account.json`` —— 一行 JSON，包含：
``id`` / ``name`` / ``title`` / ``device`` / ``pwd_salt`` / ``pwd_hash``
``recovery_hash`` / ``created`` / ``synced`` / ``stats``

**密码永不落盘**（只存盐 + 哈希）。恢复码同样只存哈希。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
def data_dir() -> str:
    env = os.environ.get("SF_GAME_HOME")
    if env:
        return env
    try:
        from core import run as _run
        d = os.path.dirname(getattr(_run, "SAVE_PATH", "") or "")
        if d:
            return d
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents", "钢铁战线")


def account_path() -> str:
    return os.path.join(data_dir(), "account.json")


# --------------------------------------------------------------------------
# 头衔
# --------------------------------------------------------------------------
TITLE_AUTHOR = "author"       # 作者大帝 —— 仅作者设备可得
TITLE_TESTER = "tester"       # 测试玩家
TITLE_VETERAN = "veteran"     # 老玩家
TITLE_NONE = ""

#: 头衔表：id -> (中文名, 英文名, 是否仅作者)
TITLES: Dict[str, Tuple[str, str, bool]] = {
    TITLE_AUTHOR:  ("作者大帝", "Sovereign Author", True),
    TITLE_TESTER:  ("测试玩家", "Playtester", False),
    TITLE_VETERAN: ("老玩家", "Veteran", False),
    TITLE_NONE:    ("", "", False),
}

#: 老玩家的门槛：完成多少局（含战役与联机，不含 AI 1v1）
VETERAN_RUNS = 20

#: 作者设备指纹（在下面 _author_device() 里按需填）
#: 留空 = 还没锁定，此时任何设备都拿不到「作者大帝」，
#: 避免误发给别人。作者本机首次运行时会自动写入。
AUTHOR_DEVICE_FILE = "author_device.txt"


def _author_device_path() -> str:
    return os.path.join(data_dir(), AUTHOR_DEVICE_FILE)


def _known_author_devices() -> List[str]:
    """读取已登记的作者设备指纹。"""
    out: List[str] = []
    try:
        p = _author_device_path()
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        out.append(line)
    except Exception:
        pass
    # 也支持写死在环境变量里（打包时注入）
    env = os.environ.get("SF_AUTHOR_DEVICE", "").strip()
    if env:
        out.append(env)
    return out


def claim_author_device() -> Tuple[bool, str]:
    """把当前设备登记为作者设备。

    只在**首次**调用且文件不存在时写入 —— 防止别人在自己机器上
    调用一下就把自己变成作者。
    """
    try:
        p = _author_device_path()
        if os.path.isfile(p):
            return False, "作者设备已经登记过了"
        from core import integrity as I
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 作者设备指纹（本机）。删除本文件会失去「作者大帝」头衔。\n")
            f.write(I.device_id() + "\n")
        return True, "已登记本机为作者设备"
    except Exception as exc:
        return False, "登记失败：%r" % (exc,)


def is_author_device() -> bool:
    try:
        from core import integrity as I
        return I.device_id() in _known_author_devices()
    except Exception:
        return False


def title_label(title: str, en: bool = False) -> str:
    zh, t_en, _ = TITLES.get(title, ("", "", False))
    return (t_en if en else zh) or ""


def available_titles() -> List[str]:
    """当前设备可以选的头衔。"""
    out = [TITLE_NONE]
    if is_author_device():
        out.append(TITLE_AUTHOR)
    out.append(TITLE_TESTER)
    out.append(TITLE_VETERAN)
    return out


def allowed_title(title: str, stats: Optional[Dict] = None) -> bool:
    """这个头衔当前设备能不能用。"""
    if title in ("", TITLE_NONE):
        return True
    if title == TITLE_AUTHOR:
        return is_author_device()
    if title == TITLE_TESTER:
        return True
    if title == TITLE_VETERAN:
        stats = stats or {}
        return int(stats.get("runs", 0) or 0) >= VETERAN_RUNS
    return False


# --------------------------------------------------------------------------
# 口令哈希
# --------------------------------------------------------------------------
def _hash_secret(secret: str, salt: str) -> str:
    """PBKDF2-HMAC-SHA256。标准库实现，无需第三方。"""
    try:
        dk = hashlib.pbkdf2_hmac("sha256", str(secret).encode("utf-8"),
                                 str(salt).encode("utf-8"), 120000)
        return dk.hex()
    except Exception:
        return hashlib.sha256(("%s|%s" % (salt, secret)).encode()).hexdigest()


def _new_salt() -> str:
    return secrets.token_hex(16)


def make_recovery_code() -> str:
    """生成恢复码：XXXX-XXXX-XXXX（去掉容易看混的字符）。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    groups = []
    for _ in range(3):
        groups.append("".join(secrets.choice(alphabet) for _ in range(4)))
    return "-".join(groups)


def normalize_recovery(code: str) -> str:
    """去掉分隔符与易混字符，统一大写。"""
    s = "".join(ch for ch in str(code or "").upper()
                if ch.isalnum())
    return s.replace("O", "0").replace("I", "1").replace("L", "1")


# --------------------------------------------------------------------------
# 账号
# --------------------------------------------------------------------------
class Account:
    """一个本地账号。"""

    def __init__(self, data: Optional[Dict] = None):
        d = dict(data or {})
        self.id: str = str(d.get("id") or "")
        self.name: str = str(d.get("name") or "")
        self.title: str = str(d.get("title") or "")
        self.device: str = str(d.get("device") or "")
        self.pwd_salt: str = str(d.get("pwd_salt") or "")
        self.pwd_hash: str = str(d.get("pwd_hash") or "")
        self.recovery_hash: str = str(d.get("recovery_hash") or "")
        self.created: float = float(d.get("created") or 0)
        self.synced: bool = bool(d.get("synced"))
        self.stats: Dict = dict(d.get("stats") or {})
        self._raw = d

    # -- 序列化 -------------------------------------------------------
    def to_dict(self) -> Dict:
        d = dict(self._raw)
        d.update({
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "device": self.device,
            "pwd_salt": self.pwd_salt,
            "pwd_hash": self.pwd_hash,
            "recovery_hash": self.recovery_hash,
            "created": self.created,
            "synced": self.synced,
            "stats": self.stats,
        })
        return d

    # -- 展示 ---------------------------------------------------------
    def display(self) -> str:
        """给界面/对手看的名字：「[头衔] 名字」。"""
        t = title_label(self.title)
        if t and self.name:
            return "%s %s" % (t, self.name)
        return self.name or "无名指挥官"

    def public(self) -> Dict:
        """可以发给对手的最小信息（不含任何凭据）。"""
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "display": self.display(),
        }

    # -- 密码 ---------------------------------------------------------
    def check_password(self, pwd: str) -> bool:
        if not self.pwd_hash:
            return True                 # 没设密码
        got = _hash_secret(pwd, self.pwd_salt)
        try:
            return hmac.compare_digest(got, self.pwd_hash)
        except Exception:
            return got == self.pwd_hash

    def set_password(self, pwd: str) -> None:
        self.pwd_salt = _new_salt()
        self.pwd_hash = _hash_secret(pwd, self.pwd_salt)

    def check_recovery(self, code: str) -> bool:
        """校验恢复码。

        盐用**账号 id**，不能用设备指纹 ——
        恢复码的用途就是「换设备」，用设备做盐是逻辑矛盾：
        换了机器 self.device 变了，哈希永远对不上（真踩过）。
        """
        if not self.recovery_hash:
            return False
        got = _hash_secret(normalize_recovery(code), self.id or "sf")
        try:
            return hmac.compare_digest(got, self.recovery_hash)
        except Exception:
            return got == self.recovery_hash

    def sync_hash(self) -> str:
        """给服务器上报的「账号哈希」。

        只包含 id/name/title + 设备，**不含密码或恢复码**。
        """
        base = "|".join([self.id, self.name, self.title, self.device])
        return hashlib.sha256(base.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 读写
# --------------------------------------------------------------------------
def exists() -> bool:
    return os.path.isfile(account_path())


def load() -> Optional[Account]:
    try:
        with open(account_path(), encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or not d.get("id"):
            return None
        return Account(d)
    except Exception:
        return None


def save(acc: Account) -> bool:
    try:
        p = account_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(acc.to_dict(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 注册 / 登录 / 迁移
# --------------------------------------------------------------------------
def current_device() -> str:
    try:
        from core import integrity as I
        return I.device_id()
    except Exception:
        return "unknown-device"


def register(name: str, password: str = "",
             title: str = "") -> Tuple[bool, str, Optional[Account]]:
    """注册。返回 (成功, 提示, 账号)。

    规则：
      * **一台设备只能有一个账号**（已存在就拒绝）
      * 名字 1-16 字符，非空
      * 头衔必须是本机可用的
    """
    if exists():
        return False, "这台设备已经注册过账号了。", None

    name = (name or "").strip()
    if not name:
        return False, "请填写名字。", None
    if len(name) > 16:
        return False, "名字最多 16 个字符。", None
    if any(ord(c) < 32 for c in name):
        return False, "名字里有非法字符。", None

    dev = current_device()
    stats = {"runs": 0, "wins": 0, "versus": 0, "versus_wins": 0}
    if not allowed_title(title, stats):
        title = TITLE_NONE

    acc = Account({
        "id": secrets.token_hex(8),
        "name": name,
        "title": title,
        "device": dev,
        "created": time.time(),
        "synced": False,
        "stats": stats,
    })
    if password:
        acc.set_password(password)

    code = make_recovery_code()
    acc.recovery_hash = _hash_secret(normalize_recovery(code), acc.id)

    if not save(acc):
        return False, "写入失败，检查磁盘权限。", None

    # 把恢复码明文返回一次（只此一次，之后只存哈希）
    return True, code, acc


def login(password: str = "") -> Tuple[bool, str, Optional[Account]]:
    """登录本机账号。

    **离线也能登** —— 只校验本机文件 + 可选密码。
    设备不匹配时给出明确提示（提示用恢复码迁移）。
    """
    acc = load()
    if acc is None:
        return False, "这台设备还没有账号，请先注册。", None

    dev = current_device()
    if acc.device and dev and acc.device != dev:
        # 设备变了：不是这台机器的账号
        return False, ("这个账号属于另一台设备。\n"
                       "请用「恢复码」把账号迁移过来。"), None

    if acc.pwd_hash:
        if not password:
            return False, "请输入密码。", None
        if not acc.check_password(password):
            return False, "密码不对。", None

    return True, "登录成功。", acc


def auto_login() -> Optional[Account]:
    """打开游戏时自动进入账号（无密码时直接用）。"""
    acc = load()
    if acc is None:
        return None
    dev = current_device()
    if acc.device and dev and acc.device != dev:
        return None                     # 需要恢复码
    if acc.pwd_hash:
        return None                     # 需要密码，走登录界面
    return acc


def restore_with_code(code: str, new_password: str = "",
                      keep_name: bool = True,
                      new_name: str = "") -> Tuple[bool, str, Optional[Account]]:
    """用恢复码把账号迁移到本机。

    迁移后：
      * 账号绑定到**本机**设备指纹
      * 换一个新的恢复码（旧的作废）
      * 名字可以保留或改
    """
    acc = load()
    if acc is None:
        return False, "本机没有可迁移的账号记录。", None
    if not acc.recovery_hash:
        return False, "这个账号没有设置恢复码。", None
    if not acc.check_recovery(code):
        return False, "恢复码不对。", None

    dev = current_device()
    acc.device = dev
    if not keep_name and (new_name or "").strip():
        acc.name = new_name.strip()[:16]
    if new_password:
        acc.set_password(new_password)

    new_code = make_recovery_code()
    acc.recovery_hash = _hash_secret(normalize_recovery(new_code), acc.id)
    if not save(acc):
        return False, "写入失败。", None
    return True, new_code, acc


def regenerate_recovery() -> Tuple[bool, str]:
    """重新生成恢复码（旧的作废）。"""
    acc = load()
    if acc is None:
        return False, "没有账号。"
    code = make_recovery_code()
    acc.recovery_hash = _hash_secret(normalize_recovery(code),
                                     acc.id or "sf")
    if not save(acc):
        return False, "写入失败。"
    return True, code


# --------------------------------------------------------------------------
# 战绩（AI 1v1 不计入）
# --------------------------------------------------------------------------
def record_result(kind: str, won: bool, score: int = 0,
                  note: str = "") -> Tuple[bool, str]:
    """记一局战绩。

    ``kind`` 取值：
      * ``"campaign"``  战役（计入）
      * ``"versus"``    联机 1v1（计入）
      * ``"ai_versus"`` **AI 1v1 —— 不计入**
    """
    if kind == "ai_versus":
        return False, "AI 对战不计入战绩。"

    acc = load()
    if acc is None:
        return False, "没有账号。"

    st = dict(acc.stats or {})
    if kind == "campaign":
        st["runs"] = int(st.get("runs", 0)) + 1
        if won:
            st["wins"] = int(st.get("wins", 0)) + 1
        st["best_score"] = max(int(st.get("best_score", 0)), int(score or 0))
    elif kind == "versus":
        st["versus"] = int(st.get("versus", 0)) + 1
        if won:
            st["versus_wins"] = int(st.get("versus_wins", 0)) + 1
    else:
        return False, "未知的对局类型：%s" % kind

    st["last_played"] = time.time()
    acc.stats = st

    # 达标就解锁老玩家（不覆盖已有头衔）
    if not acc.title and int(st.get("runs", 0)) >= VETERAN_RUNS:
        acc.title = TITLE_VETERAN

    save(acc)
    return True, "已记录。"


def set_title(title: str) -> Tuple[bool, str]:
    acc = load()
    if acc is None:
        return False, "没有账号。"
    if not allowed_title(title, acc.stats):
        if title == TITLE_AUTHOR:
            return False, "「作者大帝」只属于作者本人的设备。"
        if title == TITLE_VETERAN:
            n = int((acc.stats or {}).get("runs", 0) or 0)
            return False, "「老玩家」需要完成 %d 局（当前 %d 局）。" % (
                VETERAN_RUNS, n)
        return False, "这个头衔不能用。"
    acc.title = title
    save(acc)
    return True, "头衔已更新。"


def set_name(name: str) -> Tuple[bool, str]:
    acc = load()
    if acc is None:
        return False, "没有账号。"
    name = (name or "").strip()
    if not name or len(name) > 16:
        return False, "名字需要 1-16 个字符。"
    if any(ord(c) < 32 for c in name):
        return False, "名字里有非法字符。"
    acc.name = name
    save(acc)
    return True, "名字已更新。"


# --------------------------------------------------------------------------
# 服务器同步（离线优先：失败也不影响玩）
# --------------------------------------------------------------------------
def sync_payload() -> Optional[Dict]:
    """准备上报给服务器的内容（**不含密码 / 恢复码**）。"""
    acc = load()
    if acc is None:
        return None
    return {
        "id": acc.id,
        "name": acc.name,
        "title": acc.title,
        "device": acc.device,
        "hash": acc.sync_hash(),
        "created": acc.created,
        "stats": {
            "runs": int((acc.stats or {}).get("runs", 0)),
            "wins": int((acc.stats or {}).get("wins", 0)),
            "versus": int((acc.stats or {}).get("versus", 0)),
        },
    }


def mark_synced(ok: bool = True) -> None:
    acc = load()
    if acc is None:
        return
    acc.synced = bool(ok)
    save(acc)
