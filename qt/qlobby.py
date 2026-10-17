"""钢铁战线 Steel Frontline — 联机大厅 (qlobby.py)
================================================================

局域网 1v1 的房间界面。两个模式：

* **创建房间**（房主，side 0）：显示本机 IP（大字号，方便念给同学）+ 端口，
  以及「等待对方连接…」状态。
* **加入房间**（加入方，side 1）：输入对方 IP + 连接按钮 + 连接中/失败提示。

设计要点
--------
* 网络全部走 :mod:`core.netplay`：所有 ``recv`` 在它自己的 daemon 线程里，
  界面只通过 ``QTimer`` 轮询 ``poll()``。**绝不** ``time.sleep`` 阻塞 UI。
* 连接成功后 → 进入卡组构筑（``connected`` 信号带 side 与 net 对象）。
* 任何错误（端口占用 / IP 打错 / 对方退出）都以中文提示显示在界面上，
  不弹异常、不白屏。
* 面向玩家文案遵守附录 B.1（能量→补给、格挡→掩体、遗物→勋章）。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget,
)

from . import qtheme as T
from . import qwidgets as W
from .qscreens import TitleBar


def _hex(c) -> str:
    """把任意颜色值安全地转成 QSS 可用的 `#RRGGBB`。

    ``qtheme`` 里颜色常量有**两套命名**：无前缀的是 ``str``（如
    ``BORDER_HI``/``GOLD``/``GREEN``），``Q_`` 前缀的才是 ``QColor``。
    字符串上调用 ``.name()`` 会直接 AttributeError 崩掉整个界面，
    因此所有进入 QSS 的颜色都必须过这里。
    """
    try:
        if isinstance(c, QColor):
            return c.name()
        if isinstance(c, str):
            return c
        name = getattr(c, "name", None)
        if callable(name):
            return str(name())
        return str(c)
    except Exception:
        return "#000000"


# =====================================================================
# netplay 兜底
# =====================================================================

DEFAULT_PORT = 45671


def _netplay():
    """拿到 core.netplay 模块；不可用时返回 None（界面仍要能显示）。"""
    try:
        from core import netplay as np        # type: ignore
        return np
    except Exception:
        return None


def local_ip() -> str:
    """本机局域网 IP（大字号显示给同学念）。"""
    np = _netplay()
    if np is not None and hasattr(np, "local_ip"):
        try:
            ip = str(np.local_ip() or "")
            if ip:
                return ip
        except Exception:
            pass
    # 标准库兜底：连一个不存在的公网地址只为问出本机出口 IP
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return str(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def free_port() -> int:
    np = _netplay()
    if np is not None and hasattr(np, "free_port"):
        try:
            return int(np.free_port())
        except Exception:
            pass
    return DEFAULT_PORT


def engine_available() -> bool:
    np = _netplay()
    if np is not None and hasattr(np, "engine_available"):
        try:
            return bool(np.engine_available())
        except Exception:
            return True
    return False


# =====================================================================
# 大字号 IP 显示
# =====================================================================


class BigIP(QWidget):
    """大字号 IP + 端口：黑底绿字「电台显示」质感，方便念给同学。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(116)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ip = "—"
        self._port = DEFAULT_PORT

    def set_addr(self, ip: str, port: int) -> None:
        self._ip = str(ip or "—")
        try:
            self._port = int(port)
        except (TypeError, ValueError):
            self._port = DEFAULT_PORT
        self.update()

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        T.aa(p)
        rr = QRectF(0, 0, self.width(), self.height())

        # 外壳
        T.steel_plate(p, rr, T.Q_PANEL, T.RADIUS_M, rivets=True)
        inner = rr.adjusted(9, 9, -9, -9)
        # 荧光屏底
        g = QLinearGradient(QPointF(inner.left(), inner.top()),
                            QPointF(inner.left(), inner.bottom()))
        g.setColorAt(0.0, T.qc("#0B120A"))
        g.setColorAt(0.5, T.qc("#0E1A0C"))
        g.setColorAt(1.0, T.qc("#070C06"))
        T.fill_round(p, inner, T.RADIUS_S, QBrush(g))
        T.stroke_round(p, inner, T.RADIUS_S, T.a(T.Q_BORDER_HI, 220), 1.4)

        # 扫描线
        p.save()
        p.setClipPath(T.round_path(inner, T.RADIUS_S))
        p.setPen(QPen(T.a(T.qc("#6B7F3A"), 26), 1.0))
        y = inner.top()
        while y < inner.bottom():
            p.drawLine(QPointF(inner.left(), y), QPointF(inner.right(), y))
            y += 3.0
        p.restore()

        # 小标签
        T.text(p, QRectF(inner.left() + 12, inner.top() + 6,
                         inner.width() - 24, 16),
               "本机地址 · 念给同学听", T.font(max(9, T.FONT_TINY - 1), True),
               T.a(T.qc("#8FA86A"), 230))

        # 大字号 IP
        f = T.mono(max(24, int(self.height() * 0.30)), True)
        T.text_c(p, inner.center().x(), inner.center().y() + 4,
                 self._ip, f, T.qc("#B9E06A"), shadow=True)

        # 端口（右下）
        T.text(p, QRectF(inner.right() - 190, inner.bottom() - 22, 178, 18),
               "端口 %d" % self._port, T.font(T.FONT_TINY, True),
               T.a(T.qc("#8FA86A"), 220),
               align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # 呼吸光标
        import math as _m
        ph = (self._phase if hasattr(self, "_phase") else 0.0)
        if getattr(self, "_live", False):
            k = 0.4 + 0.6 * (0.5 + 0.5 * _m.sin(ph))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(T.a(T.qc("#B9E06A"), int(220 * k))))
            p.drawEllipse(QPointF(inner.left() + 14, inner.bottom() - 13), 3.4, 3.4)
        p.end()


# =====================================================================
# 大厅
# =====================================================================


class LobbyScreen(QWidget):
    """联机大厅：创建房间 / 加入房间。

    信号
    ----
    * ``connected(int, object)``  已连上对手 → (my_side, net_object)
    * ``closed()``                返回主菜单
    """

    connected = pyqtSignal(int, object)
    closed = pyqtSignal()

    # -- 一键匹配 --
    #: 排队位置更新（pos, waiting）
    queue_update = pyqtSignal(int, int)
    #: 匹配成功（net 对象, 房间号, 是否是房主）
    match_found = pyqtSignal(object, str, bool)
    #: 匹配成功且已准备好进入对战
    match_ready = pyqtSignal(object, str, bool)
    #: 匹配失败（原因）
    match_failed = pyqtSignal(str)

    POLL_MS = 120

    def __init__(self, parent=None, player_name: str = "指挥官"):
        super().__init__(parent)
        self.host = None
        self.client = None
        self.my_side = 0
        self._mode = "host"
        self._peer_ready = False
        self._player_name = str(player_name or "指挥官")
        self._port = DEFAULT_PORT

        self._poll = QTimer(self)
        self._poll.setInterval(self.POLL_MS)
        self._poll.timeout.connect(self.poll_net)

        self._build()

    # =================================================================
    # 构建
    # =================================================================
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 16, 26, 16)
        root.setSpacing(10)

        self.tb = TitleBar("联 机 对 战", "局域网 1v1 · 双方各带一套卡组", self)
        root.addWidget(self.tb)

        # --- 模式切换 ---
        tabrow = QHBoxLayout()
        tabrow.setSpacing(0)
        self.btn_host = QPushButton("创 建 房 间", self)
        self.btn_host.setObjectName("Tab")
        self.btn_host.setCheckable(True)
        self.btn_host.setChecked(True)
        self.btn_host.setMinimumWidth(200)
        self.btn_host.setMinimumHeight(42)
        self.btn_host.clicked.connect(lambda: self.set_mode("host"))
        tabrow.addWidget(self.btn_host)

        self.btn_join = QPushButton("加 入 房 间", self)
        self.btn_join.setObjectName("Tab")
        self.btn_join.setCheckable(True)
        self.btn_join.setMinimumWidth(200)
        self.btn_join.setMinimumHeight(42)
        self.btn_join.clicked.connect(lambda: self.set_mode("join"))
        tabrow.addWidget(self.btn_join)

        # -- 一键匹配（最好用，放最前面）--
        self.btn_match = QPushButton("⚡ 一 键 匹 配", self)
        self.btn_match.setObjectName("Tab")
        self.btn_match.setCheckable(True)
        self.btn_match.setMinimumWidth(190)
        self.btn_match.setMinimumHeight(42)
        self.btn_match.setToolTip("自动找对手，不用交换房间号")
        self.btn_match.clicked.connect(lambda: self.set_mode("match"))
        tabrow.addWidget(self.btn_match)

        # -- 公网（中继）两个模式 --
        self.btn_net_host = QPushButton("公 网 建 房", self)
        self.btn_net_host.setObjectName("Tab")
        self.btn_net_host.setCheckable(True)
        self.btn_net_host.setMinimumWidth(170)
        self.btn_net_host.setMinimumHeight(42)
        self.btn_net_host.clicked.connect(lambda: self.set_mode("net_host"))
        tabrow.addWidget(self.btn_net_host)

        self.btn_net_join = QPushButton("公 网 加 入", self)
        self.btn_net_join.setObjectName("Tab")
        self.btn_net_join.setCheckable(True)
        self.btn_net_join.setMinimumWidth(170)
        self.btn_net_join.setMinimumHeight(42)
        self.btn_net_join.clicked.connect(lambda: self.set_mode("net_join"))
        tabrow.addWidget(self.btn_net_join)

        tabrow.addStretch(1)
        root.addLayout(tabrow)

        # --- 主体 ---
        mid = QHBoxLayout()
        mid.setSpacing(12)

        # 左：模式面板
        self.panel = QFrame(self)
        self.panel.setObjectName("Panel")
        self.panel.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(18, 16, 18, 16)
        pv.setSpacing(12)

        # -- 一键匹配区 --
        self.match_box = QWidget(self.panel)
        self.match_box.setObjectName("LobbyPane")
        self.match_box.setStyleSheet("QWidget#LobbyPane{background:transparent;}")
        mv = QVBoxLayout(self.match_box)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(14)

        self.lbl_match_title = QLabel("快速匹配", self.match_box)
        self.lbl_match_title.setStyleSheet(
            f"color:{T.GOLD};font-size:{T.FONT_H1}px;font-weight:800;"
            f"background:transparent;")
        mv.addWidget(self.lbl_match_title)

        self.lbl_match_hint = QLabel(
            "点下面的按钮，服务器会**自动帮你找一个对手**。\n"
            "不用交换房间号，不用知道对方 IP。", self.match_box)
        self.lbl_match_hint.setWordWrap(True)
        self.lbl_match_hint.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        mv.addWidget(self.lbl_match_hint)

        # 搜索中的动画文字
        self.lbl_match_state = QLabel("", self.match_box)
        self.lbl_match_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_match_state.setMinimumHeight(64)
        self.lbl_match_state.setStyleSheet(
            f"color:{T.TEXT};font-size:{T.FONT_H1}px;font-weight:700;"
            f"background:{T.PANEL_LO};border:1px solid {T.BORDER};"
            f"border-radius:8px;")
        self.lbl_match_state.hide()
        mv.addWidget(self.lbl_match_state)

        # 服务器地址（可手动改，存到本地 server.txt）
        srv_row = QHBoxLayout()
        srv_row.setSpacing(8)
        lbl_srv = QLabel("服务器：", self.match_box)
        lbl_srv.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        srv_row.addWidget(lbl_srv)
        self.ed_srv = QLineEdit(self.match_box)
        self.ed_srv.setPlaceholderText("例如 45.123.45.67:9000")
        self.ed_srv.setClearButtonEnabled(True)
        srv_row.addWidget(self.ed_srv, 1)
        self.btn_srv_save = QPushButton("保存", self.match_box)
        self.btn_srv_save.setObjectName("Ghost")
        self.btn_srv_save.setFixedWidth(76)
        self.btn_srv_save.clicked.connect(self.save_server_address)
        srv_row.addWidget(self.btn_srv_save)
        mv.addLayout(srv_row)

        self.btn_match_go = QPushButton("开 始 匹 配", self.match_box)
        self.btn_match_go.setObjectName("Primary")
        self.btn_match_go.setMinimumHeight(52)
        self.btn_match_go.clicked.connect(self.start_match)
        mv.addWidget(self.btn_match_go)

        self.btn_match_cancel = QPushButton("取 消 匹 配", self.match_box)
        self.btn_match_cancel.setObjectName("Ghost")
        self.btn_match_cancel.setMinimumHeight(42)
        self.btn_match_cancel.clicked.connect(self.cancel_match)
        self.btn_match_cancel.hide()
        mv.addWidget(self.btn_match_cancel)

        mv.addStretch(1)
        self.match_box.hide()

        # 匹配信号连接（后台线程 -> UI 线程）
        self.queue_update.connect(self.on_queue_update)
        self.match_found.connect(self.on_match_found)
        self.match_failed.connect(self.on_match_failed)

        # -- 房主区 --
        self.host_box = QWidget(self.panel)
        self.host_box.setObjectName("LobbyPane")
        self.host_box.setStyleSheet("QWidget#LobbyPane{background:transparent;}")
        hv = QVBoxLayout(self.host_box)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(10)

        h1 = QLabel("① 把这串地址念给同学", self.host_box)
        h1.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2}px; font-weight:800;"
            f"background:transparent;")
        hv.addWidget(h1)

        self.big_ip = BigIP(self.host_box)
        hv.addWidget(self.big_ip)

        h2 = QLabel("② 让同学在他那边的「加入房间」里输入上面的 IP",
                    self.host_box)
        h2.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        h2.setWordWrap(True)
        hv.addWidget(h2)

        portrow = QHBoxLayout()
        portrow.setSpacing(8)
        lbl_p = QLabel("端口", self.host_box)
        lbl_p.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        portrow.addWidget(lbl_p)
        self.sp_port = QSpinBox(self.host_box)
        self.sp_port.setRange(1024, 65535)
        self.sp_port.setValue(DEFAULT_PORT)
        self.sp_port.setFixedWidth(120)
        self.sp_port.valueChanged.connect(self._on_port_changed)
        portrow.addWidget(self.sp_port)
        self.btn_free_port = QPushButton("换个空闲端口", self.host_box)
        self.btn_free_port.setObjectName("Ghost")
        self.btn_free_port.clicked.connect(self._pick_free_port)
        portrow.addWidget(self.btn_free_port)
        portrow.addStretch(1)
        hv.addLayout(portrow)

        # 需要房间码（更安全，但对方必须知道码）
        self.cb_code = QCheckBox("需要房间码（更安全）", self.host_box)
        self.cb_code.setChecked(False)
        self.cb_code.setToolTip(
            "开启后，对方必须输入正确的房间码才能进入，\n"
            "防止同一个网络里的陌生人乱入。")
        hv.addWidget(self.cb_code)

        self.lbl_code = QLabel("", self.host_box)
        self.lbl_code.setStyleSheet(
            f"color:{T.GOLD};font-size:{T.FONT_H2}px;font-weight:800;"
            f"background:transparent;letter-spacing:2px;")
        self.lbl_code.hide()
        hv.addWidget(self.lbl_code)

        self.btn_open = QPushButton("开 始 等 待 对 手", self.host_box)
        self.btn_open.setObjectName("Primary")
        self.btn_open.setMinimumHeight(48)
        self.btn_open.clicked.connect(self.start_host)
        hv.addWidget(self.btn_open)
        hv.addStretch(1)
        # -- 公网面板（中继：房间号匹配，跨网络可用） --
        self.net_box = QWidget(self.panel)
        self.net_box.setObjectName("LobbyPane")
        self.net_box.setStyleSheet("QWidget#LobbyPane{background:transparent;}")
        nv = QVBoxLayout(self.net_box)
        nv.setContentsMargins(4, 4, 4, 4)
        nv.setSpacing(12)

        self.lbl_net_title = QLabel("公网联机（自动匹配）", self.net_box)
        self.lbl_net_title.setStyleSheet(
            f"color:{T.GOLD};font-size:{T.FONT_H2}px;font-weight:800;"
            f"background:transparent;")
        nv.addWidget(self.lbl_net_title)

        self.lbl_net_hint = QLabel("", self.net_box)
        self.lbl_net_hint.setWordWrap(True)
        self.lbl_net_hint.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        nv.addWidget(self.lbl_net_hint)

        # 房间号大字显示（房主）
        self.lbl_room = QLabel("", self.net_box)
        self.lbl_room.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_room.setStyleSheet(
            f"color:{T.GOLD};font-size:64px;font-weight:900;"
            f"background:transparent;letter-spacing:14px;")
        self.lbl_room.hide()
        nv.addWidget(self.lbl_room)

        # 房间号输入（加入方）
        row_room = QHBoxLayout()
        row_room.addWidget(QLabel("房间号", self.net_box))
        self.ed_room = QLineEdit(self.net_box)
        self.ed_room.setPlaceholderText("4 位数字，例如 4821")
        self.ed_room.setMaxLength(4)
        self.ed_room.setFixedWidth(180)
        self.ed_room.setStyleSheet(
            f"QLineEdit{{background:{T.PANEL_LO};border:1px solid {T.BORDER};"
            f"border-radius:6px;padding:8px 12px;color:{T.TEXT};"
            f"font-size:28px;font-weight:800;letter-spacing:6px;}}"
            f"QLineEdit:focus{{border:1px solid {T.GOLD};}}")
        row_room.addWidget(self.ed_room)
        row_room.addStretch(1)
        self.net_room_row = QWidget(self.net_box)
        rl = QHBoxLayout(self.net_room_row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(row_room)
        nv.addWidget(self.net_room_row)

        self.btn_net_go = QPushButton("创 建 房 间", self.net_box)
        self.btn_net_go.setObjectName("Primary")
        self.btn_net_go.setMinimumHeight(48)
        self.btn_net_go.clicked.connect(self.start_net)
        nv.addWidget(self.btn_net_go)

        # 固定写出开放时间（不管开没开都显示，玩家一眼知道什么时候能玩）
        self.lbl_net_hours = QLabel(
            "🕐 开放时间：每天 12:00 ～ 24:00", self.net_box)
        self.lbl_net_hours.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_SMALL}px;"
            f"background:transparent;font-weight:600;")
        nv.addWidget(self.lbl_net_hours)

        self.lbl_net_srv = QLabel("", self.net_box)
        self.lbl_net_srv.setStyleSheet(
            f"color:{T.TEXT_MUTED};font-size:{T.FONT_TINY}px;"
            f"background:transparent;")
        nv.addWidget(self.lbl_net_srv)

        nv.addStretch(1)
        self.net_box.hide()
        pv.addWidget(self.net_box, 1)

        pv.addWidget(self.match_box, 1)
        pv.addWidget(self.host_box, 1)

        # -- 加入区 --
        self.join_box = QWidget(self.panel)
        self.join_box.setObjectName("LobbyPane")
        self.join_box.setStyleSheet("QWidget#LobbyPane{background:transparent;}")
        jv = QVBoxLayout(self.join_box)
        jv.setContentsMargins(0, 0, 0, 0)
        jv.setSpacing(10)

        j1 = QLabel("① 输入房主念给你的 IP", self.join_box)
        j1.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_H2}px; font-weight:800;"
            f"background:transparent;")
        jv.addWidget(j1)

        self.ed_ip = QLineEdit(self.join_box)
        self.ed_ip.setPlaceholderText(T.tr("例如 192.168.1.42"))
        self.ed_ip.setMinimumHeight(52)
        self.ed_ip.setStyleSheet(
            f"QLineEdit{{background:{T.PANEL_LO}; border:1px solid {T.BORDER};"
            f"border-radius:{T.RADIUS_S}px; padding:8px 14px;"
            f"font-size:{T.FONT_H1}px; font-family:'{T.MONO_FAMILY}';"
            f"color:{T.TEXT}; letter-spacing:2px;}}"
            f"QLineEdit:focus{{border:1px solid {T.GOLD};}}")
        self.ed_ip.returnPressed.connect(self.start_join)
        jv.addWidget(self.ed_ip)

        jrow = QHBoxLayout()
        jrow.setSpacing(8)
        lbl_jp = QLabel("端口", self.join_box)
        lbl_jp.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        jrow.addWidget(lbl_jp)
        self.sp_jport = QSpinBox(self.join_box)
        self.sp_jport.setRange(1024, 65535)
        self.sp_jport.setValue(DEFAULT_PORT)
        self.sp_jport.setFixedWidth(120)
        jrow.addWidget(self.sp_jport)
        jrow.addStretch(1)
        jv.addLayout(jrow)

        self.btn_join_now = QPushButton("连 接 房 主", self.join_box)
        self.btn_join_now.setObjectName("Primary")
        self.btn_join_now.setMinimumHeight(48)
        self.btn_join_now.clicked.connect(self.start_join)
        jv.addWidget(self.btn_join_now)

        # 房间码（房主开了「需要房间码」时必须填）
        code_row = QHBoxLayout()
        code_row.addWidget(QLabel("房间码（房主开了才要填）", self.join_box))
        self.ed_code = QLineEdit(self.join_box)
        self.ed_code.setPlaceholderText("ABCD-2345-EFGH")
        self.ed_code.setMaxLength(24)
        self.ed_code.setStyleSheet(
            f"QLineEdit{{background:{T.PANEL_LO}; border:1px solid {T.BORDER};"
            f"border-radius:6px; padding:6px 10px; color:{T.TEXT};"
            f"font-size:{T.FONT_BODY}px;}}"
            f"QLineEdit:focus{{border:1px solid {T.GOLD};}}")
        code_row.addWidget(self.ed_code, 1)
        jv.addLayout(code_row)

        self.lbl_mine = QLabel(
            T.tr("（本机地址：%s —— 方便对方反过来告诉你他的 IP）") % local_ip(),
            self.join_box)
        self.lbl_mine.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;"
            f"background:transparent;")
        self.lbl_mine.setWordWrap(True)
        jv.addWidget(self.lbl_mine)
        jv.addStretch(1)
        pv.addWidget(self.join_box, 1)
        self.join_box.hide()

        # 状态条
        self.status = QLabel("", self.panel)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(46)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_BODY}px; background:transparent;")
        pv.addWidget(self.status)
        mid.addWidget(self.panel, 1)

        # 右：说明 / 连接动画
        side = QWidget(self)
        side.setFixedWidth(252)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(9)

        info = QFrame(side)
        info.setObjectName("PanelLo")
        iv = QVBoxLayout(info)
        iv.setContentsMargins(12, 12, 12, 12)
        iv.setSpacing(7)
        ttl = QLabel("怎 么 玩", info)
        ttl.setStyleSheet(
            f"color:{T.GOLD}; font-size:{T.FONT_BODY}px; font-weight:800;"
            f"background:transparent;")
        iv.addWidget(ttl)
        _tips_zh = (
            "1. 两台设备连**同一个 WiFi**。\n"
            "2. 房主点「开始等待对手」，把大字号 IP 念给同学。\n"
            "3. 加入方输入 IP → 「连接房主」。\n"
            "4. 连上后各自构筑卡组（20–40 张）。\n"
            "5. 双方都确认后自动开战。\n\n"
            "· 出牌只发「我要出第几张」的意图，\n"
            "  一切判定由房主执行，改血量改不动。\n"
            "· 对手手牌永远是背面，看不到内容。"
        )
        tips = QLabel(T.tr(_tips_zh), info)
        tips.setWordWrap(True)
        tips.setStyleSheet(
            f"color:{T.TEXT_DIM}; font-size:{T.FONT_TINY}px;"
            f"background:transparent;")
        iv.addWidget(tips)
        sv.addWidget(info, 0)

        self.radar = RadarWidget(side)
        sv.addWidget(self.radar, 0, Qt.AlignmentFlag.AlignHCenter)
        sv.addStretch(1)
        mid.addWidget(side, 0)

        root.addLayout(mid, 1)

        # --- 底部 ---
        foot = QHBoxLayout()
        self.lbl_engine = QLabel("", self)
        self.lbl_engine.setStyleSheet(
            f"color:{T.TEXT_MUTED}; font-size:{T.FONT_TINY}px;"
            f"background:transparent;")
        foot.addWidget(self.lbl_engine, 1)
        self.btn_back = QPushButton("返 回 主 菜 单", self)
        self.btn_back.setObjectName("Ghost")
        self.btn_back.clicked.connect(self._on_back)
        foot.addWidget(self.btn_back)
        root.addLayout(foot)

        self._refresh_engine_note()
        self.big_ip.set_addr(local_ip(), self._port)
        self.set_mode("host")

    def _refresh_engine_note(self) -> None:
        if engine_available():
            self.lbl_engine.setText("对战引擎：就绪")
        else:
            self.lbl_engine.setText("⚠ 对战引擎不可用（core/versus.py 缺失）")

    # =================================================================
    # 模式
    # =================================================================
    def set_mode(self, mode: str) -> None:
        mode = str(mode)
        if mode not in ("host", "join", "net_host", "net_join", "match"):
            mode = "host"
        if mode != self._mode:
            self.stop_all()
        self._mode = mode
        self.btn_host.setChecked(mode == "host")
        self.btn_join.setChecked(mode == "join")
        self.btn_net_host.setChecked(mode == "net_host")
        self.btn_net_join.setChecked(mode == "net_join")
        self.btn_match.setChecked(mode == "match")
        self.host_box.setVisible(mode == "host")
        self.join_box.setVisible(mode == "join")
        self.match_box.setVisible(mode == "match")
        # match 走自己的面板，不显示旧的房间号面板
        # （两个都显示会挤在一起，而且房间号匹配对玩家没意义）
        is_net = mode in ("net_host", "net_join", "match")
        self.net_box.setVisible(mode in ("net_host", "net_join"))
        self.radar.set_live(False)
        # 副标题跟着模式走，避免"局域网"字样出现在公网模式里
        try:
            if mode == "match":
                self.tb.set_subtitle("一键匹配 · 自动找对手 · 跨网络可用")
            elif is_net:
                self.tb.set_subtitle("公网联机 · 用房间号匹配 · 跨网络可用")
            else:
                self.tb.set_subtitle("局域网 1v1 · 双方各带一套卡组")
        except Exception:
            pass

        if mode == "match":
            self._prepare_match()
            return
        if is_net:
            self._prepare_net(mode)
            return
        self.lbl_room.hide()
        if mode == "host":
            self._status("点「开始等待对手」后，把这台设备的地址念给同学。",
                         T.TEXT_DIM)
        else:
            self._status("输入房主的 IP，然后点「连接房主」。", T.TEXT_DIM)

    def save_server_address(self) -> None:
        """保存玩家手填的服务器地址（存到本地 server.txt）。"""
        try:
            from core import relay_client as _rc
        except Exception as exc:
            self._status("缺少联机模块：%s" % exc, T.Q_RED)
            return
        ok, msg = _rc.save_endpoints(self.ed_srv.text())
        if not ok:
            self._status("保存失败：%s" % msg, T.Q_RED)
            return
        self._status(msg + " 可以开始匹配了。", T.GREEN)
        self._prepare_match()          # 刷新按钮可用状态

    def _load_server_address(self) -> None:
        """把当前配置的地址填进输入框。"""
        try:
            from core import relay_client as _rc
            eps = _rc.relay_endpoints()
            if eps:
                self.ed_srv.setText(",".join(
                    "%s:%d" % (h, p) for h, p in eps))
        except Exception:
            pass

    def _prepare_match(self) -> None:
        """切到匹配模式：按服务器是否开放来决定按钮可用性。"""
        try:
            self._load_server_address()
        except Exception:
            pass
        try:
            from core import relay_client as _rc
            configured = bool(_rc.relay_configured())
            srv = (_rc.relay_address() if configured else "")
        except Exception:
            configured = False
            srv = ""
        self.btn_match_go.setEnabled(configured)
        if configured:
            self._status("点「开始匹配」自动找对手（服务器：%s）" % srv,
                         T.TEXT_DIM)
        else:
            self._status("服务器未开放，请等待 12:00～24:00 开放服务器",
                         T.Q_ORANGE)

    # ------------------------------------------------------------------
    # 一键匹配
    # ------------------------------------------------------------------
    def start_match(self) -> None:
        """点「开始匹配」：进服务器队列找对手。"""
        try:
            from core import relay_client as _rc
        except Exception as exc:
            self._status("缺少联机模块：%s" % exc, T.Q_RED)
            return
        if not _rc.relay_configured():
            self._status("服务器未开放，请等待 12:00～24:00 开放服务器",
                         T.Q_ORANGE)
            return
        if getattr(self, "_matching", False):
            return
        self._matching = True
        self._match_cancel = False
        self.btn_match_go.setEnabled(False)
        self.btn_match_cancel.show()
        self.lbl_match_state.show()
        self.lbl_match_state.setText("正在搜索对手…")
        self.lbl_match_state.setStyleSheet(
            f"color:{T.GOLD};font-size:{T.FONT_H1}px;font-weight:700;"
            f"background:{T.PANEL_LO};border:1px solid {T.BORDER};"
            f"border-radius:8px;")
        self._status("已进入匹配队列，正在寻找对手…", T.GOLD)

        # 后台线程匹配（不能卡 UI）
        import threading

        def _worker():
            try:
                obj, room, is_host = _rc.match_via_relay(
                    on_queue=self._on_queue_update, timeout=90.0)
            except Exception as exc:
                self.match_failed.emit(str(exc))
                return
            self.match_found.emit(obj, room, bool(is_host))

        t = threading.Thread(target=_worker, name="sf-match", daemon=True)
        t.start()

    def _on_queue_update(self, pos: int, waiting: int) -> None:
        """排队位置回调（可能来自后台线程 -> 用信号转回 UI 线程）。"""
        self.queue_update.emit(int(pos), int(waiting))

    def on_queue_update(self, pos: int, waiting: int) -> None:
        """UI 线程里更新「搜索中…（第 N 位）」。"""
        if not getattr(self, "_matching", False):
            return
        dots = "." * ((pos + waiting) % 4)
        if waiting <= 1:
            self.lbl_match_state.setText("正在搜索对手" + dots)
        else:
            self.lbl_match_state.setText(
                "正在搜索对手" + dots + "\n前面还有 %d 人" % max(0, waiting - 1))

    def on_match_found(self, obj, room, is_host: bool) -> None:
        """匹配成功：直接进对战。"""
        self._matching = False
        self.btn_match_go.setEnabled(True)
        self.btn_match_cancel.hide()
        self.lbl_match_state.setText("已找到对手！")
        self.lbl_match_state.setStyleSheet(
            f"color:{T.GREEN};font-size:{T.FONT_H1}px;font-weight:700;"
            f"background:{T.PANEL_LO};border:1px solid {T.GREEN};"
            f"border-radius:8px;")
        self._status("匹配成功，房间 %s" % room, T.GREEN)
        self.match_ready.emit(obj, str(room), bool(is_host))

    def on_match_failed(self, msg: str) -> None:
        self._matching = False
        self.btn_match_go.setEnabled(True)
        self.btn_match_cancel.hide()
        self.lbl_match_state.hide()
        self._status("匹配失败：%s" % msg, T.Q_RED)

    def cancel_match(self) -> None:
        """取消匹配。"""
        if not getattr(self, "_matching", False):
            return
        self._matching = False
        self._match_cancel = True
        self.btn_match_go.setEnabled(True)
        self.btn_match_cancel.hide()
        self.lbl_match_state.hide()
        self._status("已取消匹配。", T.TEXT_DIM)

    # ------------------------------------------------------------------
    # 公网（中继）
    # ------------------------------------------------------------------
    def _prepare_net(self, mode: str) -> None:
        """切到公网模式：配置输入框与按钮。"""
        try:
            from core import relay_client as _rc
        except Exception:
            _rc = None

        configured = bool(_rc is not None and _rc.relay_configured())
        if configured:
            self.lbl_net_srv.setText("服务器：%s" % _rc.relay_address())
        else:
            # 服务器还没开 —— 给一句明确、不吓人的提示。
            # 每天 12:00~24:00 开放。
            self.lbl_net_srv.setText(
                "服务器未开放，请等待 12:00～24:00 开放服务器")

        if mode == "net_host":
            self.lbl_net_title.setText("公网建房")
            self.lbl_net_hint.setText(
                "点下面的按钮创建房间，会得到一个 4 位房间号。\n"
                "把房间号发给对方（微信、QQ、游戏群里都行），"
                "他在「公网加入」里输入就能进来。\n"
                "不需要在同一个 WiFi，也不需要知道对方 IP。")
            self.btn_net_go.setText("创 建 房 间")
            self.net_room_row.hide()
            self.lbl_room.hide()
        else:
            self.lbl_net_title.setText("公网加入")
            self.lbl_net_hint.setText(
                "输入对方给你的 4 位房间号，点下面的按钮进入。\n"
                "不需要在同一个 WiFi。")
            self.btn_net_go.setText("加 入 房 间")
            self.net_room_row.show()
            self.lbl_room.hide()
        self.btn_net_go.setEnabled(configured)
        self._status("跨网络联机 —— 用房间号匹配。" if configured
                     else "服务器未开放，请等待服务器开放",
                     T.TEXT_DIM if configured else T.Q_ORANGE)

    def start_net(self) -> None:
        """公网建房 / 加入。"""
        try:
            from core import relay_client as _rc
        except Exception as exc:
            self._status("⚠ 缺少联机模块：%s" % exc, T.Q_RED)
            return
        if not _rc.relay_configured():
            self._status("⚠ 还没有配置联机服务器。", T.Q_RED)
            return

        is_host = self._mode == "net_host"
        self.btn_net_go.setEnabled(False)

        if is_host:
            self._status("正在创建房间…", T.Q_GOLD)
        else:
            room = (self.ed_room.text() or "").strip()
            if len(room) != 4 or not room.isdigit():
                self._status("⚠ 房间号是 4 位数字。", T.Q_ORANGE)
                self.btn_net_go.setEnabled(True)
                self.ed_room.setFocus()
                return
            self._status("正在加入房间 %s …" % room, T.Q_GOLD)
        QApplication_process()

        try:
            if is_host:
                net, code = _rc.host_via_relay()
                self.host_net = net
                self.lbl_room.setText(code)
                self.lbl_room.show()
                self._status(
                    "房间已创建！把房间号 %s 发给对方。" % code, T.Q_GREEN)
                self._poll.start()      # 开始轮询，等对方进来
                # 配对成功后由 poll 收到 connected，走正常流程
                self._net_waiting_host = True
            else:
                net, rs = _rc.join_via_relay(room)
                self.client_net = net
                self._poll.start()
                self._status("已加入房间，正在进入卡组构筑…", T.Q_GREEN)
                self.my_side = 1
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(300, lambda n=net: self.connected.emit(1, n))
        except Exception as exc:
            self._status("⚠ %s" % exc, T.Q_RED)
            self.btn_net_go.setEnabled(True)

    def _on_port_changed(self, v: int) -> None:
        self._port = int(v)
        self.big_ip.set_addr(local_ip(), self._port)
        if self._mode == "join":
            self.sp_jport.setValue(self._port)

    def _pick_free_port(self) -> None:
        self.sp_port.setValue(free_port())

    def _status(self, msg: str, color=None) -> None:
        self.status.setText(msg)
        self.status.setStyleSheet(
            f"color:{_hex(color or T.Q_TEXT_DIM)}; font-size:{T.FONT_BODY}px;"
            f"font-weight:600; background:transparent;")

    # =================================================================
    # 房主
    # =================================================================
    def start_host(self) -> None:
        np = _netplay()
        if np is None:
            self._status("⚠ 联机模块不可用（core/netplay.py 缺失）。", T.Q_RED)
            return
        if self.host is not None:
            self._status("房间已经开着了，正在等同学连接…", T.Q_GOLD)
            return
        port = int(self.sp_port.value())
        self._status("正在开房间（端口 %d）…" % port, T.Q_GOLD)
        QApplication_process()
        # netplay 的契约：端口在构造时传入，start() 不接受参数。
        try:
            require_code = bool(getattr(self, "cb_code", None)
                                and self.cb_code.isChecked())
            self.host = np.Host(on_event=None, port=port,
                                name=self._player_name,
                                require_code=require_code)
            try:
                code = getattr(getattr(self.host, "_ticket", None),
                               "display", lambda: "")()
                if code:
                    self.lbl_code.setText(
                        ("房间码：%s" % code) if require_code
                        else ("本房房间码：%s（对方可不填）" % code))
                    self.lbl_code.show()
            except Exception:
                pass
        except TypeError:
            # 兼容更早的 Host(on_event, name) 签名
            try:
                self.host = np.Host(on_event=None, name=self._player_name)
            except Exception as exc:
                self._status("⚠ 创建房间失败：%s" % exc, T.Q_RED)
                self.host = None
                return
        except Exception as exc:
            self._status("⚠ 创建房间失败：%s" % exc, T.Q_RED)
            self.host = None
            return
        try:
            ok = bool(self.host.start())
        except Exception as exc:
            self._status("⚠ 开房失败：%s" % exc, T.Q_RED)
            self.host = None
            return
        if not ok:
            # start() 失败的具体原因（端口占用）由 error 事件给出，
            # 这里轮询一次立刻显示出来。
            self.poll_net()
            if not self.status.text().startswith("⚠"):
                self._status("⚠ 端口 %d 可能被占用，换个端口再试。" % port, T.Q_RED)
            try:
                self.host.close()
            except Exception:
                pass
            self.host = None
            return
        self.my_side = 0
        self._peer_ready = False
        self._port = port
        self.big_ip.set_addr(local_ip(), port)
        self.radar.set_live(True)
        self._poll.start()
        self.btn_open.setText("等 待 对 手 连 接 …")
        self.btn_open.setEnabled(False)
        self._status("等待对方连接…（本机 %s:%d）" % (local_ip(), port), T.Q_GOLD)

    @staticmethod
    def _host_start_takes_port() -> bool:
        """netplay.Host.start 是否接受端口参数（按签名自适应）。"""
        np = _netplay()
        if np is None:
            return False
        try:
            import inspect
            sig = inspect.signature(np.Host.start)
            return len(sig.parameters) > 1
        except Exception:
            return False

    # =================================================================
    # 加入方
    # =================================================================
    def start_join(self) -> None:
        np = _netplay()
        if np is None:
            self._status("⚠ 联机模块不可用（core/netplay.py 缺失）。", T.Q_RED)
            return
        host_ip = (self.ed_ip.text() or "").strip()
        if not host_ip:
            self._status("⚠ 请先输入房主的 IP 地址。", T.Q_ORANGE)
            self.ed_ip.setFocus()
            return
        if self.client is not None:
            self._status("已经连上了，正在等房主开始。", T.Q_GOLD)
            return
        port = int(self.sp_jport.value())
        self._status("正在连接 %s:%d …（最多等 8 秒）" % (host_ip, port), T.Q_GOLD)
        self.btn_join_now.setEnabled(False)
        self.radar.set_live(True)
        QApplication_process()
        try:
            code = ""
            try:
                code = (self.ed_code.text() or "").strip()
            except Exception:
                code = ""
            try:
                if code:
                    self.client = np.Client(on_event=None,
                                            name=self._player_name,
                                            token=code)
                else:
                    self.client = np.Client(on_event=None,
                                            name=self._player_name)
            except TypeError:
                self.client = np.Client(on_event=None, name=self._player_name)
        except Exception as exc:
            self._status("⚠ 创建连接失败：%s" % exc, T.Q_RED)
            self.client = None
            self.btn_join_now.setEnabled(True)
            return
        try:
            ok = bool(self.client.connect(host_ip, port))
        except Exception as exc:
            self._status("⚠ 连接出错：%s" % exc, T.Q_RED)
            self.client = None
            self.btn_join_now.setEnabled(True)
            self.radar.set_live(False)
            return
        self.my_side = 1
        if not ok:
            # connect() 的失败原因已变成 error 事件；轮询出来显示
            self._poll.start()
            self.poll_net()
            self._poll.stop()
            if self.status.text().startswith("正在连接"):
                self._status("⚠ 连接失败：请确认对方已开房间、IP 与端口正确、"
                             "两台设备在同一个 WiFi 下。", T.Q_RED)
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
            self.btn_join_now.setEnabled(True)
            self.radar.set_live(False)
            return
        self._poll.start()
        self._status("已连接，等待房主确认…", T.Q_GOLD)

    # =================================================================
    # 事件轮询
    # =================================================================
    def poll_net(self) -> None:
        # 公网（中继）的连接对象存在 host_net / client_net，也要一起轮询，
        # 否则联网后永远收不到 connected / peer 事件（界面卡在等待）。
        objs = (self.host, self.client,
                getattr(self, "host_net", None),
                getattr(self, "client_net", None))
        for obj in objs:
            if obj is None:
                continue
            try:
                events = obj.poll() or []
            except Exception as exc:
                print(f"[qt.lobby] poll failed: {exc!r}", flush=True)
                continue
            for ev in events:
                try:
                    self._on_event(ev)
                except Exception as exc:
                    print(f"[qt.lobby] event failed: {exc!r}", flush=True)

    def _on_event(self, ev: Dict) -> None:
        t = str((ev or {}).get("type", ""))
        if t == "listening":
            self.radar.set_live(True)
            self._status("等待对方连接…（本机 %s:%d）"
                         % (ev.get("ip", local_ip()), int(ev.get("port", self._port))),
                         T.Q_GOLD)
        elif t == "connecting":
            self._status("正在连接 %s:%d …" % (ev.get("host", "?"),
                                              int(ev.get("port", self._port))),
                         T.Q_GOLD)
        elif t == "connected":
            # 连上后**必须立刻进入卡组构筑**，否则死锁：
            # connected.emit 原本只在收到 start 时才发，而 start 需要
            # 双方都 send_deck —— 可玩家根本没机会去编卡组，于是画面
            # 永远停在「正在交换卡组…」，看着就是卡死（用户实际遇到）。
            self.radar.set_live(True)
            self._status("已连上，正在进入卡组构筑…", T.Q_GREEN)
            # 判断自己是房主还是加入方，并取出对应的连接对象。
            # 四条路径都要覆盖：局域网房主/加入、公网房主/加入。
            host_obj = self.host or getattr(self, "host_net", None)
            client_obj = self.client or getattr(self, "client_net", None)
            is_host = host_obj is not None
            side = 0 if is_host else 1
            self.my_side = side
            # 别停轮询：后面还要等对手的 peer_ready
            net = host_obj if is_host else client_obj
            if net is not None:
                # 稍等一下让状态文字先画出来，再切界面
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(350,
                                  lambda n=net, sd=side: self.connected.emit(sd, n))
        elif t == "peer":
            self._status("对方「%s」已进入房间，等待确认卡组…"
                         % ev.get("name", "同学"), T.Q_GREEN)
        elif t == "ready":
            self._status("我的卡组已就绪，等对方…", T.Q_GOLD)
        elif t == "peer_ready":
            self._peer_ready = True
            self._status("对方「%s」卡组已就绪！" % ev.get("name", "同学"), T.Q_GREEN)
        elif t == "start":
            side = int(ev.get("side", self.my_side))
            self.my_side = side
            self._status("开战！正在进入对战…", T.Q_GREEN)
            self.radar.set_live(False)
            self._poll.stop()
            net = self.host if side == 0 else self.client
            self.connected.emit(side, net)
        elif t == "error":
            self._status("⚠ " + str(ev.get("msg", "未知错误")), T.Q_RED)
            self.radar.set_live(False)
            # 连接失败/开房失败：允许重试
            self.btn_join_now.setEnabled(True)
            self.btn_open.setText("开 始 等 待 对 手")
            self.btn_open.setEnabled(True if self.host is None else False)
        elif t in ("disconnected", "bye"):
            msg = str(ev.get("reason") or ev.get("msg") or "对方已断开连接。")
            self._status("⚠ " + msg + " 可以重新等待/连接。", T.Q_ORANGE)
            self.stop_all()
            self.btn_join_now.setEnabled(True)
            self.btn_open.setText("开 始 等 待 对 手")
            self.btn_open.setEnabled(True)
            self.radar.set_live(False)

    # =================================================================
    # 收尾
    # =================================================================
    def stop_all(self) -> None:
        self._poll.stop()
        for attr in ("host", "client", "host_net", "client_net"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)
        self.radar.set_live(False)
        self.btn_open.setText("开 始 等 待 对 手")
        self.btn_open.setEnabled(True)
        self.btn_join_now.setEnabled(True)

    def _on_back(self) -> None:
        self.stop_all()
        self.closed.emit()

    def refresh(self) -> None:
        self.big_ip.set_addr(local_ip(), self._port)
        self.lbl_mine.setText(
            "（本机地址：%s —— 方便对方反过来告诉你他的 IP）" % local_ip())
        self._refresh_engine_note()

    # =================================================================
    # 自检辅助
    # =================================================================
    def status_text(self) -> str:
        return self.status.text()

    def mode(self) -> str:
        return self._mode


# =====================================================================
# 雷达（等待/连接动画）
# =====================================================================


class RadarWidget(QWidget):
    """雷达扫描：等待对方连接时的动态反馈，避免界面像卡死。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 雷达必须保持正方形，否则同心圆会被拉成椭圆。
        self.setFixedSize(252, 252)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._live = False
        self._sweep = 0.0
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def set_live(self, on: bool) -> None:
        self._live = bool(on)
        self.update()

    def _tick(self) -> None:
        if self._live:
            self._sweep = (self._sweep + 0.045) % 1.0
            self.update()

    def paintEvent(self, ev):  # noqa: N802
        import math as _m
        p = QPainter(self)
        T.aa(p)
        r = QRectF(0, 0, self.width(), self.height())
        T.steel_plate(p, r, T.Q_PANEL, T.RADIUS_M, rivets=False)

        c = r.center()
        R = max(20.0, min(r.width(), r.height()) / 2 - 26)

        # 同心圆
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, k in enumerate((0.34, 0.62, 1.0)):
            p.setPen(QPen(T.a(T.Q_GREEN, 150 if i == 2 else 80),
                          1.3 if i == 2 else 1.0))
            p.drawEllipse(c, R * k, R * k)
        # 十字
        p.setPen(QPen(T.a(T.Q_GREEN, 70), 1.0))
        p.drawLine(QPointF(c.x() - R, c.y()), QPointF(c.x() + R, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - R), QPointF(c.x(), c.y() + R))

        col = T.Q_GREEN if self._live else T.Q_TEXT_FAINT
        # 扫描扇形
        if self._live:
            p.save()
            p.setClipPath(T.round_path(QRectF(c.x() - R, c.y() - R, R * 2, R * 2), R))
            for i in range(26):
                k = i / 26.0
                a0 = self._sweep * 360.0 - k * 42.0
                p.setPen(QPen(T.a(T.Q_GREEN, int(120 * (1.0 - k))), 2.4))
                p.drawLine(c, QPointF(
                    c.x() + _m.cos(_m.radians(a0)) * R,
                    c.y() - _m.sin(_m.radians(a0)) * R))
            p.restore()
            p.setPen(QPen(T.a(T.Q_GREEN, 220), 2.0))
            p.drawLine(c, QPointF(
                c.x() + _m.cos(_m.radians(self._sweep * 360.0)) * R,
                c.y() - _m.sin(_m.radians(self._sweep * 360.0)) * R))

        # 中心点
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(T.a(col, 220)))
        p.drawEllipse(c, 3.4, 3.4)

        T.text_c(p, c.x(), min(r.bottom() - 11, c.y() + R + 17),
                 "正在等待对手…" if self._live else "未开始",
                 T.font(T.FONT_SMALL, True),
                 col if self._live else T.Q_TEXT_FAINT)
        p.end()


def QApplication_process():
    """让「连接中…」这一帧先画出来（连接本身是阻塞的 socket 调用）。"""
    try:
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
    except Exception:
        pass
