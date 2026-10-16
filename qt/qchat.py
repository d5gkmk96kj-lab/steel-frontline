#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对局内聊天框。

设计要点：
  * 默认收起，不挡战斗界面；点「💬」展开
  * 只在对局中可用
  * 消息有长度与条数上限（防刷屏）—— 上限在 core/netplay 里
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)


class ChatPanel(QWidget):
    """一条迷你聊天栏。"""

    #: 用户想发一条消息
    send_requested = pyqtSignal(str)

    MAX_LINES = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#ChatPanel{background:rgba(14,16,20,0.92);"
            "border:1px solid #333;border-radius:8px;}")
        self.setFixedWidth(320)
        self.setMaximumHeight(240)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        self.lbl_title = QLabel("聊 天")
        f = QFont()
        f.setBold(True)
        self.lbl_title.setFont(f)
        head.addWidget(self.lbl_title)
        head.addStretch(1)
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setObjectName("Ghost")
        self.btn_close.clicked.connect(self.hide_panel)
        head.addWidget(self.btn_close)
        lay.addLayout(head)

        self.log = QListWidget()
        self.log.setObjectName("ChatLog")
        self.log.setFont(QFont("PingFang SC", 11))
        self.log.setStyleSheet(
            "QListWidget{background:transparent;border:none;}")
        self.log.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(self.log, 1)

        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("说点什么…（回车发送）")
        self.edit.setMaxLength(120)
        self.edit.returnPressed.connect(self._on_send)
        row.addWidget(self.edit, 1)
        self.btn_send = QPushButton("发送")
        self.btn_send.setObjectName("Primary")
        self.btn_send.setFixedWidth(56)
        self.btn_send.clicked.connect(self._on_send)
        row.addWidget(self.btn_send)
        lay.addLayout(row)

        self.hide()

    # -- 收发 ---------------------------------------------------------
    def _on_send(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        ok, why = self._can_send()
        if not ok:
            self.system(why)
            return
        if self._is_duplicate(text):
            self.system("刚发过一样的话")
            return
        import time as _t
        self._last_send = _t.time()
        # 连续相同的消息折叠（防刷屏）
        n = self.log.count()
        if n >= self.MAX_REPEAT:
            last = [self.log.item(i).text() for i in range(n - self.MAX_REPEAT, n)]
            if len(set(last)) == 1 and text in last[0]:
                self.system("（消息已折叠）")
                self.edit.clear()
                return
        self.edit.clear()
        self.send_requested.emit(text)

    #: 两条消息之间最短间隔（秒）—— 防连点刷屏
    MIN_INTERVAL = 1.2
    #: 完全相同的消息在这么多秒内不重复显示
    DEDUP_WINDOW = 8.0
    #: 连续消息最多显示多少条相同前缀（超过就折叠）
    MAX_REPEAT = 3

    def _can_send(self) -> tuple:
        """冷却检查。返回 (能否发送, 提示)。"""
        import time as _t
        now = _t.time()
        last = getattr(self, "_last_send", 0.0)
        if now - last < self.MIN_INTERVAL:
            left = self.MIN_INTERVAL - (now - last)
            return False, "发太快了，等 %.1f 秒" % left
        return True, ""

    def _is_duplicate(self, text: str) -> bool:
        """短时间内重复发同一句 -> 抑制。"""
        import time as _t
        now = _t.time()
        rec = getattr(self, "_recent", None)
        if rec is None:
            self._recent = rec = {}
        # 清理过期
        for k in [k for k, t in rec.items() if now - t > self.DEDUP_WINDOW]:
            rec.pop(k, None)
        if text in rec:
            return True
        rec[text] = now
        return False

    def add(self, name: str, text: str, mine: bool = False) -> None:
        """加一条消息。"""
        prefix = "我" if mine else (name or "对手")
        item = QListWidgetItem("%s：%s" % (prefix, text))
        if mine:
            item.setForeground(Qt.GlobalColor.lightGray)
        self.log.addItem(item)
        while self.log.count() > self.MAX_LINES:
            self.log.takeItem(0)
        self.log.scrollToBottom()

    def system(self, text: str) -> None:
        """系统提示（灰字）。"""
        item = QListWidgetItem("· " + text)
        item.setForeground(Qt.GlobalColor.darkGray)
        self.log.addItem(item)
        self.log.scrollToBottom()

    # -- 显隐 ---------------------------------------------------------
    def show_panel(self) -> None:
        self.show()
        self.raise_()
        try:
            self.edit.setFocus()
        except Exception:
            pass

    def hide_panel(self) -> None:
        self.hide()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide_panel()
        else:
            self.show_panel()

    def set_enabled(self, on: bool, why: str = "") -> None:
        """非对局状态时禁用输入。"""
        self.edit.setEnabled(bool(on))
        self.btn_send.setEnabled(bool(on))
        if why:
            self.system(why)
