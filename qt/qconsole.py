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

    def _notify_battle_over(self, app) -> None:
        """让对战界面走正常的结束流程（含横幅与结算跳转）。

        控制台直接改引擎状态后，界面层并不知情；这里补上这一步。
        """
        try:
            bs = None
            screens = getattr(app, "screens", None)
            if isinstance(screens, dict):
                bs = screens.get("battle")
            if bs is None:
                bs = getattr(app, "battle_view", None)
            if bs is None:
                return
            # 优先用界面自己的 _check_end（它会播横幅并 emit battle_finished）
            fn = getattr(bs, "_check_end", None)
            if callable(fn):
                fn()
                return
            # 退路：直接发信号
            sig = getattr(bs, "battle_finished", None)
            if sig is not None:
                res = "ongoing"
                try:
                    res = str(app.battle.result())
                except Exception:
                    res = "won"
                if res not in ("won", "lost"):
                    res = "won"
                sig.emit(res)
        except Exception as exc:
            print("[qconsole] notify battle over failed: %r" % (exc,),
                  flush=True)

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
                "integrity        代码完整性自检（哈希/设备号/异常）",
                "reports          查看违规设备记录（IP + 设备号）",
                "clearlog         清空违禁记录",
                "report           举报当前对手（加强检测）",
            ):
                self._say("  " + ln, "dim")
            self._say("也可直接输入兑换码（见 list）", "gold")
            return

        if cmd in ("list", "codes"):
            self._say("可用兑换码：", "gold")
            for d in CH.all_codes():
                self._say("  %-14s %s" % (d.code, d.name), "dim")
            return

        # ---- 完整性 / 反作弊相关 ----------------------------------
        if cmd in ("integrity", "hash", "verify"):
            try:
                from core import integrity as I
                ok, rep = I.self_check()
                self._say("代码完整性自检：%s" % ("通过" if ok else "异常"),
                          "text" if ok else "bad")
                self._say("  构建哈希：%s" % rep.get("short_hash", "?"), "dim")
                self._say("  完整哈希：%s" % (rep.get("build_hash", "")[:32] or "?"),
                          "dim")
                self._say("  设备号：  %s" % rep.get("short_device", "?"), "dim")
                self._say("  打包运行：%s" % rep.get("frozen"), "dim")
                probs = rep.get("problems") or []
                if probs:
                    self._say("  ⚠ 检测到 %d 项异常：" % len(probs), "bad")
                    for x in probs[:8]:
                        self._say("     " + str(x), "bad")
                else:
                    self._say("  ✓ 未检测到调试器 / 注入 / 补丁", "dim")
            except Exception as exc:
                self._say("自检失败：%r" % (exc,), "bad")
            return

        if cmd in ("reports", "violations", "suspects"):
            try:
                from core import integrity as I
                vs = I.violations(limit=40)
                if not vs:
                    self._say("暂无违规记录。", "dim")
                    return
                self._say("违规记录（最近 %d 条）：" % len(vs), "bad")
                for v in vs[:20]:
                    ts = v.get("ts") or 0
                    try:
                        import time as _t
                        when = _t.strftime("%m-%d %H:%M", _t.localtime(ts))
                    except Exception:
                        when = "?"
                    self._say("  [%s] 设备 %s  IP %s"
                              % (when,
                                 str(v.get("peer_device") or "?")[:16],
                                 str(v.get("peer_ip") or "局域网/未知")[:15]),
                              "bad")
                    self._say("        原因：%s  哈希：%s"
                              % (str(v.get("reason") or "?")[:24],
                                 str(v.get("peer_hash") or "?")[:12]), "dim")
                self._say("提示：clearlog 可清空记录", "dim")
            except Exception as exc:
                self._say("读取失败：%r" % (exc,), "bad")
            return

        if cmd in ("clearlog", "clearreports"):
            try:
                from core import integrity as I
                I.clear_violations()
                self._say("违规记录已清空。", "gold")
            except Exception as exc:
                self._say("清空失败：%r" % (exc,), "bad")
            return

        if cmd in ("report", "举报"):
            try:
                a = self._app()
                fn = getattr(a, "report_peer", None)
                if callable(fn):
                    fn()
                    self._say("已提交举报，正在加强检测…", "gold")
                else:
                    self._say("当前不在对局中，无法举报。", "dim")
            except Exception as exc:
                self._say("举报失败：%r" % (exc,), "bad")
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
            # 关键：必须通知**界面**战斗已结束。
            # 只调引擎的 _check_end() 会让 BattleScreen._ended 仍为 False，
            # 于是画面卡在战斗里、什么键都按不动（用户实际遇到）。
            self._notify_battle_over(a)
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

        # ---- 彩蛋（不写进 help / list，别在任何地方提）--------------
        if self._maybe_easter_egg(raw, a):
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

    # 彩蛋口令：大小写不敏感、允许末尾任意字符
    _EGG_KEY = "whale_card_battle"

    def _maybe_easter_egg(self, raw: str, a) -> bool:
        """识别隐藏口令。返回 True 表示已处理（调用方应直接 return）。

        注意：**不要**在 help / list / 任何提示里出现这个口令，
        也别说"口令不对"——失败的输入要和普通未知命令完全一样，
        否则玩家一试就试出来了。
        """
        import re as _re
        text = str(raw or "").strip()
        # 允许 "Whale_card_battle_" 以及后面还有别的东西
        # 注意：不能写 \b —— 后面跟下划线时 \b 不成立（下划线算单词字符）
        m = _re.match(r"(?i)^\s*whale_card_battle", text)
        if not m:
            return False
        try:
            from core import cheats as _CH
            from core.cards import CARD_DB as _DB
            _CH._ensure_cheat_cards()
            # 先找战役战斗，找不到再找 1v1 对战（联机/人机）
            b = getattr(a, "battle", None)
            if b is None:
                vs = (getattr(a, "screens", {}) or {}).get("versus")
                b = getattr(vs, "battle", None) if vs is not None else None
            if b is None:
                # 不在战斗里也收下：给个不点破的提示
                self._say("……海面很平静。", "dim")
                return True
            if _CH.CHEAT_CARD_WHALE not in _DB:
                return False
            # 手牌满时 add_card_to_hand 会被 HAND_LIMIT 挡掉 ——
            # 彩蛋得真的给到手里，所以满了就先塞进抽牌堆。
            added = False
            # 1v1（VersusBattle）没有 add_card_to_hand，走它自己的接口
            try:
                if hasattr(b, "add_card_to_hand"):
                    from core import engine as _EN
                    if len(getattr(b.player, "hand", []) or []) < _EN.HAND_LIMIT:
                        b.add_card_to_hand(_CH.CHEAT_CARD_WHALE)
                        added = True
            except Exception:
                pass
            if not added:
                # 1v1：直接造一个 CardInstance 塞进我方手牌
                try:
                    from core import cards as _C
                    side = b.side(0) if hasattr(b, "side") else None
                    cc = getattr(side, "combatant", None) if side else None
                    if cc is not None and _CH.CHEAT_CARD_WHALE in _DB:
                        n = int(getattr(side, "_uid_seq", 9000) or 9000) + 1
                        try:
                            side._uid_seq = n
                        except Exception:
                            pass
                        ci = _C.CardInstance(uid=n, def_id=_CH.CHEAT_CARD_WHALE)
                        cc.hand.append(ci)
                        added = True
                except Exception as exc:
                    print("[egg] versus add failed: %r" % (exc,), flush=True)
            if not added:
                try:
                    b.add_card_to_draw(_CH.CHEAT_CARD_WHALE)
                    added = True
                except Exception:
                    pass
            if added:
                self._say("有什么东西浮上来了。", "gold")
            return True
        except Exception:
            return False

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
