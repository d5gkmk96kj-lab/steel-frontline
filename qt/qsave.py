#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存档管理界面：列表 / 读取 / 删除 / 改名 / 导出 / 导入。

界面很简单：左边一列存档卡片，右边一排操作按钮。
所有 IO 都走 core.saves，出错只提示不崩。
"""

from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import qtheme as T
from . import qwidgets as W

try:
    from core import saves as _saves
except Exception:                                     # pragma: no cover
    _saves = None


class SaveSlotCard(QFrame):
    """一个存档的卡片。"""

    picked = pyqtSignal(str)          # slot_id
    load_it = pyqtSignal(str)
    del_it = pyqtSignal(str)
    rename_it = pyqtSignal(str)
    export_it = pyqtSignal(str)

    def __init__(self, info, parent=None, is_latest: bool = False):
        super().__init__(parent)
        self.slot_id = info.slot_id
        self.setObjectName("SlotCard")
        border = T.BLOOD if info.broken else (
            T.GOLD if is_latest else T.BORDER_HI)
        self.setStyleSheet(
            f"QFrame#SlotCard{{background:{T.PANEL};"
            f"border:1px solid {border};border-radius:{T.RADIUS_M}px;}}")
        self.setMinimumHeight(92)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)

        # --- 左：文字信息 ---
        col = QVBoxLayout()
        col.setSpacing(3)

        title = QLabel(info.title())
        title.setStyleSheet(
            f"color:{T.GOLD if is_latest else T.TEXT};"
            f"font-size:{T.FONT_H2}px;font-weight:800;background:transparent;")
        col.addWidget(title)

        sub = QLabel(info.summary())
        sub.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        col.addWidget(sub)

        meta = QLabel(info.when() + ("　·　最近使用" if is_latest else ""))
        meta.setStyleSheet(
            f"color:{T.TEXT_MUTED};font-size:{T.FONT_TINY}px;"
            f"background:transparent;")
        col.addWidget(meta)

        row.addLayout(col, 1)

        # --- 右：按钮 ---
        btns = QHBoxLayout()
        btns.setSpacing(6)

        def mk(text, sig, primary=False, enabled=True):
            b = QPushButton(text, self)
            b.setObjectName("Primary" if primary else "Ghost")
            b.setFixedWidth(76)
            b.setEnabled(enabled)
            # 注意：sig 是绑定的 pyqtSignal，要 .emit() 才是可调用的
            b.clicked.connect(lambda _=False, s=sig: s.emit(self.slot_id))
            btns.addWidget(b)
            return b

        mk("读取", self.load_it, primary=True, enabled=not info.broken)
        mk("改名", self.rename_it, enabled=not info.broken)
        mk("导出", self.export_it, enabled=not info.broken)
        mk("删除", self.del_it)
        row.addLayout(btns)


class SaveScreen(QWidget):
    """存档管理。"""

    closed = pyqtSignal()
    load_run = pyqtSignal(str)        # slot_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[SaveSlotCard] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)

        # --- 标题 ---
        head = QHBoxLayout()
        head.addWidget(W.SectionTitle("存 档 管 理", self))
        head.addStretch(1)
        self.lb_count = QLabel("", self)
        self.lb_count.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        head.addWidget(self.lb_count)
        root.addLayout(head)

        # --- 说明 ---
        tip = QLabel(
            "每个存档都是一个独立文件，可以**发给别人**："
            "点「导出」存成 .json 发出去，对方点「导入存档」选中即可。\n"
            "存档目录：data/saves/", self)
        tip.setWordWrap(True)
        tip.setStyleSheet(
            f"color:{T.TEXT_MUTED};font-size:{T.FONT_TINY}px;"
            f"background:{T.PANEL_LO};border:1px solid {T.BORDER};"
            f"border-radius:6px;padding:8px;")
        root.addWidget(tip)

        # --- 列表 ---
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self._lay = QVBoxLayout(self.inner)
        self._lay.setContentsMargins(0, 0, 8, 0)
        self._lay.setSpacing(10)
        self._lay.addStretch(1)
        self.scroll.setWidget(self.inner)
        root.addWidget(self.scroll, 1)

        # --- 底部操作 ---
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_import = QPushButton("导 入 存 档", self)
        self.btn_import.setObjectName("Primary")
        self.btn_import.setFixedWidth(150)
        self.btn_import.clicked.connect(self._do_import)
        bar.addWidget(self.btn_import)

        self.btn_dir = QPushButton("打开存档目录", self)
        self.btn_dir.setObjectName("Ghost")
        self.btn_dir.setFixedWidth(150)
        self.btn_dir.clicked.connect(self._open_dir)
        bar.addWidget(self.btn_dir)

        bar.addStretch(1)
        self.lb_msg = QLabel("", self)
        self.lb_msg.setStyleSheet(
            f"color:{T.TEXT_DIM};font-size:{T.FONT_SMALL}px;"
            f"background:transparent;")
        bar.addWidget(self.lb_msg)

        bar.addStretch(1)
        b = QPushButton("返 回", self)
        b.setObjectName("Ghost")
        b.setFixedWidth(120)
        b.clicked.connect(self.closed.emit)
        bar.addWidget(b)
        root.addLayout(bar)

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        # 清空旧卡片
        for c in self._cards:
            try:
                self._lay.removeWidget(c)
                c.setParent(None)
                c.deleteLater()
            except Exception:
                pass
        self._cards = []

        if _saves is None:
            self.lb_count.setText("存档模块不可用")
            return

        infos = _saves.slots()
        latest = _saves.latest_slot()
        self.lb_count.setText("共 %d 个存档" % len(infos))

        if not infos:
            empty = QLabel("还没有存档。\n开始一局战役后会自动出现在这里。",
                           self.inner)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color:{T.TEXT_MUTED};font-size:{T.FONT_BODY}px;"
                f"background:transparent;padding:40px;")
            self._lay.insertWidget(0, empty)
            self._cards.append(empty)          # 复用清理逻辑
            return

        for i, info in enumerate(infos):
            card = SaveSlotCard(info, self.inner, is_latest=(info.slot_id == latest))
            card.load_it.connect(self._do_load)
            card.del_it.connect(self._do_delete)
            card.rename_it.connect(self._do_rename)
            card.export_it.connect(self._do_export)
            self._lay.insertWidget(i, card)
            self._cards.append(card)

    def _say(self, msg: str) -> None:
        self.lb_msg.setText(str(msg))

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------
    def _do_load(self, slot_id: str) -> None:
        self.load_run.emit(slot_id)

    def _do_delete(self, slot_id: str) -> None:
        info = _saves.get(slot_id) if _saves else None
        name = info.title() if info else slot_id
        r = QMessageBox.question(
            self, "删除存档",
            "确定删除「%s」吗？\n\n删除后无法恢复。" % name,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        ok = _saves.delete(slot_id) if _saves else False
        self._say("已删除。" if ok else "删除失败。")
        self.refresh()

    def _do_rename(self, slot_id: str) -> None:
        info = _saves.get(slot_id) if _saves else None
        cur = info.name if info else ""
        text, ok = QInputDialog.getText(self, "重命名存档", "新名字：",
                                        text=cur)
        if not ok:
            return
        done = _saves.rename(slot_id, text.strip()) if _saves else False
        self._say("已改名。" if done else "改名失败。")
        self.refresh()

    def _do_export(self, slot_id: str) -> None:
        info = _saves.get(slot_id) if _saves else None
        default = (info.title() if info else "存档") + ".json"
        default = "".join(ch for ch in default if ch not in '/\\:*?"<>|')
        path, _ = QFileDialog.getSaveFileName(
            self, "导出存档（可以发给别人）",
            os.path.join(os.path.expanduser("~"), "Desktop", default),
            "存档文件 (*.json)")
        if not path:
            return
        ok = _saves.export_to(slot_id, path) if _saves else False
        self._say("已导出到 %s" % os.path.basename(path) if ok
                  else "导出失败。")

    def _do_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要导入的存档", os.path.expanduser("~"),
            "存档文件 (*.json);;所有文件 (*)")
        if not path:
            return
        sid = _saves.import_from(path) if _saves else None
        if sid:
            self._say("导入成功：%s" % os.path.basename(path))
        else:
            self._say("导入失败：这不是有效的存档文件。")
        self.refresh()

    def _open_dir(self) -> None:
        """在 Finder 里打开存档目录。"""
        try:
            d = _saves.slots_dir() if _saves else "data"
            os.makedirs(d, exist_ok=True)
            import subprocess
            subprocess.Popen(["open", d])
            self._say("已打开存档目录。")
        except Exception:
            self._say("打不开目录，路径：%s" % (_saves.slots_dir()
                                              if _saves else "data"))
