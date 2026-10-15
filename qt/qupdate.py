#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新提示对话框：显示新版本号、更新内容，并跳转下载页。

只做三件事：
  1. 告诉用户有新版本
  2. 列出修复了什么 / 新增了什么
  3. 打开浏览器到下载页（**不自动下载安装**）

还有一个「下载后怎么替换」的说明，以及「删除旧版本但保留存档」的提示。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QTextBrowser, QVBoxLayout, QWidget,
)

from . import qtheme as T

try:
    from core import updater as _up
    from core import version as _V
except Exception:                                     # pragma: no cover
    _up = None
    _V = None


class UpdateDialog(QDialog):
    """「发现新版本」对话框。"""

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("发现新版本")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(
            f"QDialog{{background:{T.BG_DEEP};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(11)

        # --- 标题 ---
        title = QLabel("🔔  发现新版本", self)
        title.setStyleSheet(
            f"color:{T.GOLD};font-size:{T.FONT_H1}px;font-weight:800;"
            f"background:transparent;")
        root.addWidget(title)

        # --- 版本对比 ---
        # 两边都要带 v 前缀，否则显示成 "v0.9.06 → 0.10" 很不整齐
        cur = _V.short() if _V else "?"
        if not cur.startswith("v"):
            cur = "v" + cur
        new = (info.display_label() if hasattr(info, "display_label")
               else info.version)
        if new and not new.startswith("v"):
            new = "v" + new
        cmp_lbl = QLabel("当前版本：%s　→　最新版本：%s" % (cur, new), self)
        cmp_lbl.setStyleSheet(
            f"color:{T.TEXT};font-size:{T.FONT_BODY}px;background:transparent;")
        root.addWidget(cmp_lbl)

        if getattr(info, "released", ""):
            rel = QLabel("发布日期：%s" % info.released, self)
            rel.setStyleSheet(
                f"color:{T.TEXT_DIM};font-size:{T.FONT_TINY}px;"
                f"background:transparent;")
            root.addWidget(rel)

        # --- 更新内容 ---
        notes = info.display_notes() if hasattr(info, "display_notes") else []
        head = QLabel("本次更新内容", self)
        head.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"font-weight:700;background:transparent;")
        root.addWidget(head)

        box = QTextBrowser(self)
        box.setOpenExternalLinks(True)
        box.setMinimumHeight(180)
        box.setStyleSheet(
            f"QTextBrowser{{background:{T.PANEL};color:{T.TEXT};"
            f"border:1px solid {T.BORDER_HI};"
            f"border-radius:{T.RADIUS_M}px;padding:10px;"
            f"font-size:{T.FONT_BODY}px;}}")
        if notes:
            html = "<ul style='margin:0;padding-left:18px;line-height:170%'>"
            for n in notes:
                html += "<li>%s</li>" % str(n)
            html += "</ul>"
        else:
            html = "<p>（本次没有提供更新说明）</p>"
        box.setHtml(html)
        root.addWidget(box, 1)

        # --- 下载后怎么装 ---
        tips = QLabel(
            "下载后怎么更新：\n"
            "  1. 点下面的「前往下载」，在浏览器里下载新的 .dmg\n"
            "  2. 打开 dmg，把新的 App 拖进「应用程序」（覆盖旧的即可）\n"
            "  3. 新版本会自动沿用你的存档 —— 存档在\n"
            "     ~/Documents/钢铁战线/data/，不在 App 里面，不会被覆盖",
            self)
        tips.setWordWrap(True)
        tips.setStyleSheet(
            f"color:{T.TEXT_MUTED};font-size:{T.FONT_TINY}px;"
            f"background:{T.PANEL_LO};border:1px solid {T.BORDER};"
            f"border-radius:6px;padding:9px;")
        root.addWidget(tips)

        # --- 按钮 ---
        bar = QHBoxLayout()
        bar.addStretch(1)
        later = QPushButton("以后再说", self)
        later.setObjectName("Ghost")
        later.setFixedWidth(120)
        later.clicked.connect(self.reject)
        bar.addWidget(later)

        go = QPushButton("前 往 下 载", self)
        go.setObjectName("Primary")
        go.setFixedWidth(160)
        go.clicked.connect(self._open_and_close)
        bar.addWidget(go)
        root.addLayout(bar)

    def _open_and_close(self) -> None:
        try:
            if _up is not None:
                _up.open_download_page(getattr(self.info, "url", "") or "")
        except Exception:
            pass
        # 下载页打开了 —— 顺便问一句要不要清掉旧版本
        self._offer_cleanup()
        self.accept()

    def _offer_cleanup(self) -> None:
        """下载完新版本后，提示可以清理旧版（不动存档）。"""
        try:
            from . import qcleanup
            if not qcleanup.has_junk():
                return
            r = QMessageBox.question(
                self, "要清理旧版本吗？",
                "新版本下载安装完成后，可以顺手删掉旧的 App 和旧的安装包，"
                "释放一些空间。\n\n"
                "**你的存档不会被删除**（存档在 ~/Documents/钢铁战线/data/，"
                "不在这些文件里）。\n\n现在去看看有哪些可以清理吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                qcleanup.show_cleanup_dialog(self)
        except Exception:
            pass


def show_update_dialog(info, parent=None) -> bool:
    """弹出更新提示。返回是否点了「前往下载」。"""
    try:
        dlg = UpdateDialog(info, parent)
        r = dlg.exec()
        return r == int(QDialog.DialogCode.Accepted)
    except Exception:
        return False
