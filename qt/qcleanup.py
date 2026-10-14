#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""旧版本清理对话框。

用途：更新到新版本后，把**旧的 .app 和旧的安装包**删掉，释放空间。
**绝不碰存档** —— 存档在 ~/Documents/钢铁战线/data/，不在这里列出的任何位置。
"""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from . import qtheme as T

try:
    from core import cleanup as _clean
except Exception:                                     # pragma: no cover
    _clean = None


class CleanupDialog(QDialog):
    """列出可清理的旧版本，勾选后删除。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("清理旧版本")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setStyleSheet(f"QDialog{{background:{T.BG_DEEP};}}")

        self._checks: List[tuple] = []       # (QCheckBox, Junk)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(11)

        title = QLabel("🧹  清理旧版本", self)
        title.setStyleSheet(
            f"color:{T.GOLD};font-size:{T.FONT_H1}px;font-weight:800;"
            f"background:transparent;")
        root.addWidget(title)

        self.lb_sub = QLabel("", self)
        self.lb_sub.setWordWrap(True)
        self.lb_sub.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        root.addWidget(self.lb_sub)

        # --- 列表 ---
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(220)
        inner = QWidget()
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)
        self.scroll.setWidget(inner)
        root.addWidget(self.scroll, 1)

        # --- 存档安全说明 ---
        safe = QLabel(
            "✅ 存档不会被删除\n"
            "你的存档在 ~/Documents/钢铁战线/data/，不在 App 内部。\n"
            "删掉旧 App 和旧安装包，进度、音乐、成就全都不受影响。",
            self)
        safe.setWordWrap(True)
        safe.setStyleSheet(
            f"color:{T.GREEN};font-size:{T.FONT_TINY}px;"
            f"background:{T.PANEL_LO};border:1px solid {T.BORDER};"
            f"border-radius:6px;padding:9px;")
        root.addWidget(safe)

        # --- 按钮 ---
        bar = QHBoxLayout()
        self.cb_all = QCheckBox("全选", self)
        self.cb_all.setChecked(True)
        self.cb_all.toggled.connect(self._toggle_all)
        bar.addWidget(self.cb_all)
        bar.addStretch(1)

        self.btn_del = QPushButton("删 除 选 中 项", self)
        self.btn_del.setObjectName("Primary")
        self.btn_del.setFixedWidth(160)
        self.btn_del.clicked.connect(self._do_delete)
        bar.addWidget(self.btn_del)

        close = QPushButton("关闭", self)
        close.setObjectName("Ghost")
        close.setFixedWidth(100)
        close.clicked.connect(self.reject)
        bar.addWidget(close)
        root.addLayout(bar)

        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        for cb, _j in self._checks:
            try:
                self._lay.removeWidget(cb)
                cb.setParent(None)
                cb.deleteLater()
            except Exception:
                pass
        self._checks = []

        items = _clean.scan() if _clean else []
        if not items:
            lbl = QLabel("没有发现可以清理的旧版本。", self)
            lbl.setStyleSheet(
                f"color:{T.TEXT_MUTED};font-size:{T.FONT_BODY}px;"
                f"background:transparent;padding:20px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._lay.insertWidget(0, lbl)
            self.lb_sub.setText("你的安装很干净。")
            self.btn_del.setEnabled(False)
            self.cb_all.setEnabled(False)
            return

        total = _clean.total_size(items)
        self.lb_sub.setText(
            "发现 %d 项可以清理，共约 %.0f MB。"
            "勾选后点删除 —— **不会**影响存档。" % (len(items), total / 1048576.0))
        self.btn_del.setEnabled(True)
        self.cb_all.setEnabled(True)

        for i, j in enumerate(items):
            kind = "旧版 App" if j.kind == "app" else "旧安装包"
            cb = QCheckBox("%s　·　%s　·　%s" % (kind, j.size_text(), j.path),
                           self)
            cb.setChecked(True)
            cb.setStyleSheet(
                f"color:{T.TEXT};font-size:{T.FONT_SMALL}px;"
                f"background:transparent;")
            self._checks.append((cb, j))
            self._lay.insertWidget(i, cb)

    def _toggle_all(self, on: bool) -> None:
        for cb, _ in self._checks:
            cb.setChecked(bool(on))

    def _selected(self) -> list:
        return [j for cb, j in self._checks if cb.isChecked()]

    def _do_delete(self) -> None:
        picked = self._selected()
        if not picked:
            QMessageBox.information(self, "没有选择", "请先勾选要删除的项目。")
            return
        total = sum(j.size for j in picked)
        r = QMessageBox.question(
            self, "确认删除",
            "将删除 %d 项，释放约 %.0f MB。\n\n"
            "存档不会被删除 —— 确定继续吗？"
            % (len(picked), total / 1048576.0),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return

        ok, failed = _clean.remove(picked) if _clean else (0, [])
        msg = "已删除 %d 项，释放约 %.0f MB。" % (ok, total / 1048576.0)
        if failed:
            msg += "\n\n有 %d 项没删掉（可能没有权限，试试用管理员身份）：\n%s" % (
                len(failed), "\n".join(failed[:3]))
        QMessageBox.information(self, "清理完成", msg)
        self.reload()


def show_cleanup_dialog(parent=None) -> None:
    try:
        CleanupDialog(parent).exec()
    except Exception:
        pass


def has_junk() -> bool:
    """有没有可清理的东西（用来决定要不要显示入口）。"""
    try:
        return bool(_clean.scan()) if _clean else False
    except Exception:
        return False
