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
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
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

        self.btn_open = QPushButton("开 始 等 待 对 手", self.host_box)
        self.btn_open.setObjectName("Primary")
        self.btn_open.setMinimumHeight(48)
        self.btn_open.clicked.connect(self.start_host)
        hv.addWidget(self.btn_open)
        hv.addStretch(1)
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
        self.ed_ip.setPlaceholderText("例如 192.168.1.42")
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
        mode = "join" if str(mode) == "join" else "host"
        if mode != self._mode:
            self.stop_all()
        self._mode = mode
        self.btn_host.setChecked(mode == "host")
        self.btn_join.setChecked(mode == "join")
        self.host_box.setVisible(mode == "host")
        self.join_box.setVisible(mode == "join")
        self.radar.set_live(False)
        if mode == "host":
            self._status("点「开始等待对手」后，把这台设备的地址念给同学。", T.TEXT_DIM)
        else:
            self._status("输入房主的 IP，然后点「连接房主」。", T.TEXT_DIM)

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
            self.host = np.Host(on_event=None, port=port, name=self._player_name)
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
        for obj in (self.host, self.client):
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
            self.radar.set_live(True)
            self._status("已连上，正在交换卡组…", T.Q_GREEN)
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
        for attr in ("host", "client"):
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
