#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账号界面：首启注册 / 登录 / 资料（名字 + 头衔）。

设计：
  * 首次进游戏 -> 引导注册（一台设备一个账号）
  * 之后打开自动进入（无密码时），不联网
  * 「我的资料」可以改名 / 换头衔 / 查看恢复码 / 迁移
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from core import account as A


def _title() -> QLabel:
    lb = QLabel("钢 铁 战 线")
    f = QFont()
    f.setPointSize(20)
    f.setBold(True)
    lb.setFont(f)
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lb


def _sub(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lb.setStyleSheet("color:#888;")
    return lb


class RegisterDialog(QDialog):
    """首次进入：取名 + 可选密码。"""

    done_ok = pyqtSignal(object)      # Account

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("创建账号")
        self.setMinimumWidth(420)
        self.account: Optional[A.Account] = None
        self.recovery_code = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_title())
        lay.addWidget(_sub("第一次进入 —— 给自己取个名字"))

        form = QFormLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("最多 16 个字符")
        self.ed_name.setMaxLength(16)
        form.addRow("名字", self.ed_name)
        self.ed_pwd = QLineEdit()
        self.ed_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_pwd.setPlaceholderText("可留空（留空则打开即进）")
        form.addRow("密码", self.ed_pwd)

        self.cb_title = QComboBox()
        self._fill_titles()
        form.addRow("头衔", self.cb_title)
        lay.addLayout(form)

        note = QLabel(
            "· 一台设备一个账号\n"
            "· 不联网也能玩（单机随时可玩）\n"
            "· 注册后会给你一个恢复码，换设备时用")
        note.setStyleSheet("color:#888;font-size:11px;")
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_ok = QPushButton("创 建")
        self.btn_ok.setObjectName("Primary")
        self.btn_ok.clicked.connect(self._do_register)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)

    def _fill_titles(self) -> None:
        self.cb_title.clear()
        for t in A.available_titles():
            label = A.title_label(t) or "（不设头衔）"
            self.cb_title.addItem(label, t)

    def _do_register(self) -> None:
        name = self.ed_name.text().strip()
        pwd = self.ed_pwd.text()
        title = self.cb_title.currentData() or ""
        ok, msg, acc = A.register(name, pwd, title)
        if not ok:
            QMessageBox.warning(self, "创建失败", msg)
            return
        self.account = acc
        self.recovery_code = msg          # register 成功时 msg 就是恢复码
        self.done_ok.emit(acc)
        self.accept()


class RecoveryDialog(QDialog):
    """展示恢复码（只显示一次）。"""

    def __init__(self, code: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("你的恢复码")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_title())
        lay.addWidget(_sub("请抄下来 —— 换设备时要用"))

        box = QTextEdit()
        box.setPlainText(code)
        box.setReadOnly(True)
        box.setFixedHeight(60)
        f = QFont("Menlo")
        f.setPointSize(16)
        f.setBold(True)
        box.setFont(f)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(box)

        tip = QLabel(
            "· 恢复码只显示这一次，之后只存哈希，找不回来\n"
            "· 换设备时：进入游戏 -> 用恢复码迁移\n"
            "· 泄露给别人 = 别人可以把你的账号迁走")
        tip.setStyleSheet("color:#c66;font-size:11px;")
        lay.addWidget(tip)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("我已抄下")
        btn.setObjectName("Primary")
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        lay.addLayout(row)


class LoginDialog(QDialog):
    """有密码的账号：进游戏时要求输入。"""

    done_ok = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录")
        self.setMinimumWidth(420)
        self.account: Optional[A.Account] = None

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_title())

        acc = A.load()
        who = acc.display() if acc else "?"
        lay.addWidget(_sub("欢迎回来，%s" % who))

        self.ed_pwd = QLineEdit()
        self.ed_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_pwd.setPlaceholderText("输入密码")
        self.ed_pwd.returnPressed.connect(self._do_login)
        lay.addWidget(self.ed_pwd)

        row = QHBoxLayout()
        self.btn_restore = QPushButton("用恢复码迁移账号")
        self.btn_restore.setObjectName("Ghost")
        self.btn_restore.clicked.connect(self._do_restore)
        row.addWidget(self.btn_restore)
        row.addStretch(1)
        self.btn_ok = QPushButton("登 录")
        self.btn_ok.setObjectName("Primary")
        self.btn_ok.clicked.connect(self._do_login)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)

    def _do_login(self) -> None:
        ok, msg, acc = A.login(self.ed_pwd.text())
        if not ok:
            QMessageBox.warning(self, "登录失败", msg)
            return
        self.account = acc
        self.done_ok.emit(acc)
        self.accept()

    def _do_restore(self) -> None:
        code, ok = _ask_text(self, "账号迁移",
                             "输入你的恢复码（形如 AAAA-BBBB-CCCC）")
        if not ok or not code.strip():
            return
        ok2, msg2, acc = A.restore_with_code(code)
        if not ok2:
            QMessageBox.warning(self, "迁移失败", msg2)
            return
        QMessageBox.information(self, "迁移成功",
                                "账号已迁到本机。\n新的恢复码：\n\n" + msg2)
        if acc is not None:
            self.account = acc
            self.done_ok.emit(acc)
            self.accept()


def _ask_text(parent, title: str, label: str):
    """小工具：弹一个输入框。返回 (文本, 是否确定)。"""
    from PyQt6.QtWidgets import QInputDialog
    text, ok = QInputDialog.getText(parent, title, label)
    return text, ok


class ProfileDialog(QDialog):
    """我的资料：改名 / 换头衔 / 恢复码 / 战绩。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("我的资料")
        self.setMinimumWidth(460)
        self.changed = False

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self.lbl_head = QLabel()
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        self.lbl_head.setFont(f)
        lay.addWidget(self.lbl_head)

        form = QFormLayout()
        self.ed_name = QLineEdit()
        self.ed_name.setMaxLength(16)
        form.addRow("名字", self.ed_name)

        self.cb_title = QComboBox()
        self._fill_titles()
        form.addRow("头衔", self.cb_title)
        lay.addLayout(form)

        self.lbl_stats = QLabel()
        self.lbl_stats.setStyleSheet("color:#aaa;font-size:12px;")
        lay.addWidget(self.lbl_stats)

        row = QHBoxLayout()
        b1 = QPushButton("保存修改")
        b1.setObjectName("Primary")
        b1.clicked.connect(self._save)
        b2 = QPushButton("重设恢复码")
        b2.setObjectName("Ghost")
        b2.clicked.connect(self._regen)
        b3 = QPushButton("关闭")
        b3.setObjectName("Ghost")
        b3.clicked.connect(self.accept)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        row.addWidget(b3)
        lay.addLayout(row)

        self._reload()

    def _fill_titles(self) -> None:
        self.cb_title.clear()
        avail = A.available_titles()
        acc = A.load()
        cur = (acc.title if acc else "")
        for t in avail:
            self.cb_title.addItem(A.title_label(t) or "（不设头衔）", t)
        # 当前头衔可能不在可用列表里（例如局数掉了），补进去免得被清掉
        if cur and cur not in avail:
            self.cb_title.addItem(A.title_label(cur) or cur, cur)
        idx = self.cb_title.findData(cur)
        if idx >= 0:
            self.cb_title.setCurrentIndex(idx)

    def _reload(self) -> None:
        acc = A.load()
        if acc is None:
            self.lbl_head.setText("没有账号")
            return
        self.lbl_head.setText(acc.display())
        self.ed_name.setText(acc.name)
        st = acc.stats or {}
        self.lbl_stats.setText(
            "战役 %d 局 / 胜 %d 局 ｜ 联机 %d 局 / 胜 %d 局\n"
            "最佳分数 %s ｜ AI 对战不计入战绩"
            % (int(st.get("runs", 0)), int(st.get("wins", 0)),
               int(st.get("versus", 0)), int(st.get("versus_wins", 0)),
               st.get("best_score", 0)))
        self._fill_titles()

    def _save(self) -> None:
        name = self.ed_name.text().strip()
        title = self.cb_title.currentData() or ""
        ok1, msg1 = A.set_name(name)
        if not ok1:
            QMessageBox.warning(self, "保存失败", msg1)
            return
        ok2, msg2 = A.set_title(title)
        if not ok2:
            QMessageBox.warning(self, "头衔没保存", msg2)
        else:
            self.changed = True
        self._reload()
        QMessageBox.information(self, "已保存", "资料已更新。")

    def _regen(self) -> None:
        r = QMessageBox.question(
            self, "重设恢复码",
            "会生成一个新的恢复码，**旧的立刻作废**。\n继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        ok, code = A.regenerate_recovery()
        if not ok:
            QMessageBox.warning(self, "失败", code)
            return
        RecoveryDialog(code, self).exec()
        self.changed = True
