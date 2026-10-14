# -*- coding: utf-8 -*-
"""全局控制台（F1 呼出）—— PyQt6 版。

像真正的 PC 游戏那样：任意界面按 **F1** 呼出底部下拉式控制台，
输入指令回车执行，**Esc 或 F1 关闭**。

与 Tkinter 版（``ui/console.py``）行为一致，共用 ``core.cheats``。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

import qt.qtheme as T
from core import cheats as CH


class ConsoleOverlay(QWidget):
    """底部下拉式控制台。覆盖在主界面之上，F1 切换。"""

    HEIGHT = 250

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConsoleOverlay")
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#ConsoleOverlay { background: rgba(11,9,6,0.97);"
            " border-top: 2px solid %s; }" % T.Q_GOLD.name())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 10, 18, 12)
        root.setSpacing(6)

        head = QHBoxLayout()
        t = QLabel("控 制 台", self)
        t.setStyleSheet(
            "color:%s; font-size:%dpx; font-weight:bold; background:transparent;"
            % (T.Q_GOLD.name(), T.FONT_H2))
        head.addWidget(t)
        hint = QLabel("F1/Esc 关闭 · Enter 执行 · Tab 补全 · ↑↓ 历史", self)
        hint.setStyleSheet(
            "color:%s; font-size:%dpx; background:transparent;"
            % (T.Q_TEXT_FAINT.name(), T.FONT_TINY))
        head.addWidget(hint)
        head.addStretch(1)
        root.addLayout(head)

        self.out = QLabel(self)
        self.out.setObjectName("ConsoleOut")
        self.out.setTextFormat(Qt.TextFormat.RichText)
        self.out.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.out.setWordWrap(False)
        self.out.setStyleSheet(
            "background:transparent; font-family:'Menlo','Monaco',monospace;"
            " font-size:%dpx;" % T.FONT_SMALL)
        root.addWidget(self.out, 1)

        row = QHBoxLayout()
        prom = QLabel("›", self)
        prom.setStyleSheet(
            "color:%s; font-size:%dpx; font-weight:bold; background:transparent;"
            % (T.Q_GOLD.name(), T.FONT_H2))
        row.addWidget(prom)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("输入指令或兑换码，例如 manpower / help")
        self.edit.returnPressed.connect(self.submit)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit, 1)
        self.btn = QPushButton("执 行", self)
        self.btn.setObjectName("Primary")
        self.btn.clicked.connect(self.submit)
        row.addWidget(self.btn)
        root.addLayout(row)

        self.lines: List[Tuple[str, str]] = []
        self._hist: List[str] = []
        self._hist_idx = 0
        self._say("钢铁战线 控制台 — 输入 help 查看指令，Esc 关闭", "dim")
        self._say("提示：可直接输入兑换码，如 manpower / god_mode / research all",
                  "dim")

    # ------------------------------------------------------------------ #
    def _app(self):
        return self.window()

    def show_console(self) -> None:
        self.setVisible(True)
        self._say("已打开控制台（当前：%s）" % self._where(), "gold")
        self._render()
        self.edit.setFocus()

    def hide_console(self) -> None:
        self.setVisible(False)

    def toggle(self) -> None:
        if self.isVisible():
            self.hide_console()
        else:
            self.show_console()

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(0, max(0, p.height() - self.HEIGHT),
                             p.width(), self.HEIGHT)

    # ------------------------------------------------------------------ #
    def _where(self) -> str:
        a = self._app()
        b = getattr(a, "battle", None)
        if b is not None:
            try:
                s = b.snapshot()
                return "战斗中 回合%d 总部%d/%d 补给%d" % (
                    s["turn"], s["player"]["hp"], s["player"]["max_hp"],
                    s["player"]["energy"])
            except Exception:
                return "战斗中"
        r = getattr(a, "run", None)
        if r is not None:
            return "战役 第%d幕 总部%d/%d 金币%d" % (r.act, r.hp, r.max_hp, r.gold)
        return "主菜单"

    _COLORS = {"ok": T.Q_GREEN.name(), "err": T.Q_RED.name(),
               "gold": T.Q_GOLD.name(), "dim": T.Q_TEXT_DIM.name(),
               "text": T.Q_TEXT.name()}

    def _say(self, text: str, kind: str = "text") -> None:
        self.lines.append((str(text), kind))
        if len(self.lines) > 200:
            del self.lines[:-200]

    def _render(self) -> None:
        html = []
        for text, kind in self.lines[-9:]:
            col = self._COLORS.get(kind, self._COLORS["text"])
            safe = (text.replace("&", "&amp;").replace("<", "&lt;")
                        .replace(">", "&gt;"))
            html.append('<div style="color:%s">%s</div>' % (col, safe))
        self.out.setText("".join(html))

    # ------------------------------------------------------------------ #
    def eventFilter(self, obj, ev):  # noqa: N802
        """把 ↑/↓/Esc 从输入框里截出来。"""
        if obj is self.edit and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if k == Qt.Key.Key_Escape:
                self.hide_console()
                return True
            if k == Qt.Key.Key_F1:
                self.toggle()
                return True
            if k == Qt.Key.Key_Up:
                self._nav(-1)
                return True
            if k == Qt.Key.Key_Down:
                self._nav(1)
                return True
            if k == Qt.Key.Key_Tab:
                self._complete()
                return True
        return super().eventFilter(obj, ev)

    def _nav(self, d: int) -> None:
        if not self._hist:
            return
        self._hist_idx = max(0, min(len(self._hist), self._hist_idx + d))
        self.edit.setText(self._hist[self._hist_idx]
                          if self._hist_idx < len(self._hist) else "")

    def _complete(self) -> None:
        pref = CH._normalize(self.edit.text())
        if not pref:
            return
        for d in CH.all_codes():
            if CH._normalize(d.code).startswith(pref):
                self.edit.setText(d.code)
                return

    # ------------------------------------------------------------------ #
    def submit(self) -> None:
        raw = (self.edit.text() or "").strip()
        if not raw:
            self.hide_console()
            return
        self.edit.clear()
        self._hist.append(raw)
        self._hist_idx = len(self._hist)
        self._say("› " + raw, "dim")
        try:
            self._run(raw)
        except Exception as exc:
            self._say("执行出错：%s" % exc, "err")
        self._render()

    def _run(self, raw: str) -> None:
        parts = raw.split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:]
        a = self._app()

        if cmd in ("help", "?"):
            for ln in (
                "help             显示本帮助",
                "list             列出全部兑换码",
                "clear            清空控制台输出",
                "close / exit     关闭控制台",
                "give <卡牌id>    把某张卡加入手牌（战斗中）",
                "heal [n]         回复总部耐久（默认 999）",
                "hp <n>           设置总部当前耐久",
                "maxhp <n>        设置总部耐久上限",
                "gold <n>         设置金币",
                "energy <n>       设置补给（战斗中）",
                "block <n>        设置掩体（战斗中）",
                "kill / win       肃清当前战斗敌人",
                "seed             显示当前种子",
                "music            显示 BGM 状态与曲库",
                "music on/off     开关背景音乐",
                "status           显示当前战役状态",
            ):
                self._say("  " + ln, "dim")
            self._say("也可直接输入兑换码（见 list）", "gold")
            return

        if cmd in ("list", "codes"):
            self._say("可用兑换码：", "gold")
            for d in CH.all_codes():
                self._say("  %-14s %s" % (d.code, d.name), "dim")
            return

        if cmd == "clear":
            self.lines = []
            self._render()
            return

        if cmd in ("close", "exit", "quit"):
            self.hide_console()
            return

        if cmd == "status":
            self._say(self._where(), "ok")
            return

        if cmd == "seed":
            self._say("种子：%s" % (getattr(getattr(a, "run", None), "seed", "无战役")), "ok")
            return

        if cmd in ("music", "bgm"):
            sub = (args[0].lower() if args else "")
            if sub in ("on", "1", "true"):
                a.cfg["music"] = True
                if hasattr(a, "restart_music"):
                    a.restart_music()
                self._say("背景音乐已开启。", "ok")
                return
            if sub in ("off", "0", "false"):
                a.cfg["music"] = False
                if hasattr(a, "restart_music"):
                    a.restart_music()
                self._say("背景音乐已关闭。", "ok")
                return
            try:
                from core import audio
                st = audio.player().status()
                self._say("后端: %s | 音量: %d%% | 当前: %s"
                          % (st["backend"], st["volume"],
                             st["track"] or "（未播放）"), "ok")
                if st["tracks"]:
                    self._say("music/ 识别到: %s"
                              % ", ".join("%s=%s" % (k, v)
                                          for k, v in sorted(st["tracks"].items())),
                              "dim")
                else:
                    self._say("music/ 目录里没有音频文件（放 menu.mp3 / ambient.mp3 等）",
                              "dim")
            except Exception as exc:
                self._say("音乐系统不可用：%s" % exc, "err")
            return


        def as_int(default=None):
            if not args:
                return default
            try:
                return int(args[0])
            except Exception:
                return default

        if cmd == "heal":
            n = as_int(999)
            b = getattr(a, "battle", None)
            if b is not None:
                b.heal(b.player, n)
                self._say("战斗中总部已回复 %d（当前 %d/%d）"
                          % (n, b.player.hp, b.player.max_hp), "ok")
            elif getattr(a, "run", None) is not None:
                a.run.heal(n)
                self._say("总部已回复 %d（当前 %d/%d）"
                          % (n, a.run.hp, a.run.max_hp), "ok")
            else:
                self._say("还没有开始战役。", "err")
            return

        if cmd in ("hp", "maxhp", "gold", "energy", "block"):
            n = as_int(None)
            if n is None:
                self._say("用法：%s <数字>" % cmd, "err")
                return
            self._say(*self._set_num(a, cmd, n))
            return

        if cmd in ("kill", "win"):
            b = getattr(a, "battle", None)
            if b is None:
                self._say("当前不在战斗中。", "err")
                return
            for e in b.enemies:
                if e.alive():
                    e.hp = 0
            try:
                b._check_end()
            except Exception:
                pass
            self._say("已肃清全部敌人。", "ok")
            return

        if cmd == "give":
            if not args:
                self._say("用法：give <卡牌id>", "err")
                return
            b = getattr(a, "battle", None)
            if b is None:
                self._say("只有战斗中才能直接给牌。", "err")
                return
            from core import cards as C
            if args[0] not in C.CARD_DB:
                self._say("没有这张卡：%s" % args[0], "err")
                return
            b.add_card_to_hand(args[0])
            self._say("已加入手牌：%s" % C.CARD_DB[args[0]].name, "ok")
            return

        reg = getattr(a, "cheat_reg", None)
        if reg is None:
            reg = CH.CheatRegistry()
            a.cheat_reg = reg
        ok, msg = reg.redeem(raw, run=getattr(a, "run", None),
                             battle=getattr(a, "battle", None),
                             meta=getattr(a, "meta", None))
        self._say(msg, "ok" if ok else "err")
        if ok:
            for name in ("refresh_current",):
                fn = getattr(a, name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass

    @staticmethod
    def _set_num(a, cmd: str, n: int) -> Tuple[str, str]:
        b = getattr(a, "battle", None)
        r = getattr(a, "run", None)
        if cmd == "gold":
            if r is None:
                return "还没有开始战役。", "err"
            r.gold = max(0, n)
            return "金币已设为 %d" % r.gold, "ok"
        if cmd in ("hp", "maxhp"):
            tgt = b.player if b is not None else r
            if tgt is None:
                return "还没有开始战役。", "err"
            if cmd == "maxhp":
                tgt.max_hp = max(1, n)
                if tgt.hp > tgt.max_hp:
                    tgt.hp = tgt.max_hp
                return "耐久上限已设为 %d" % tgt.max_hp, "ok"
            tgt.hp = max(1, min(n, tgt.max_hp))
            return "当前耐久已设为 %d/%d" % (tgt.hp, tgt.max_hp), "ok"
        if cmd in ("energy", "block"):
            if b is None:
                return "只有战斗中才能设置。", "err"
            if cmd == "energy":
                b.player.energy = max(0, n)
                return "补给已设为 %d" % b.player.energy, "ok"
            b.player.block = max(0, n)
            return "掩体已设为 %d" % b.player.block, "ok"
        return "未知指令。", "err"
