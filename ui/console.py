# -*- coding: utf-8 -*-
"""全局控制台（F1 呼出）—— Tkinter 版。

像真正的 PC 游戏那样：任意界面按 **F1** 呼出下拉式控制台，
输入指令后回车执行，**Esc 或 F1 关闭**。

支持两类输入：
  1. 兑换码：``manpower``、``god_mode``、``research all`` …
  2. 控制指令：``help`` / ``list`` / ``give <card_id>`` / ``heal`` /
     ``gold 999`` / ``hp 999`` / ``energy 99`` / ``kill`` / ``clear`` /
     ``close``

设计要点
--------
* 控制台状态存在 ``App`` 上（``app.console``），与界面无关，跨界面保持。
* 绘制由 App 在主画布**最后**叠加，所以永远在最上层。
* 输入走 ``App._on_key`` 的统一分发，优先级高于当前 view。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ui import theme as T
from core import cheats as CH


class Console:
    """下拉式控制台状态机 + 绘制。"""

    HEIGHT = 210          # 控制台面板高度
    MAX_LINES = 7         # 历史区显示行数
    MAX_BUF = 40          # 输入缓冲上限

    def __init__(self, app) -> None:
        self.app = app
        self.open = False
        self.buf = ""
        self.lines: List[Tuple[str, str]] = []   # (text, color_key)
        self.scroll = 0
        self._blink = 0.0
        self._say_hint()

    # ------------------------------------------------------------------ #
    # 状态
    # ------------------------------------------------------------------ #
    def _say_hint(self) -> None:
        self.lines = [
            ("钢铁战线 控制台 — 输入 help 查看指令，Esc 关闭", "dim"),
            ("提示：可直接输入兑换码，如 manpower / god_mode / research all", "dim"),
        ]

    def toggle(self) -> None:
        self.open = not self.open
        if self.open:
            self._blink = 0.0
            # 打开时补一条当前状态，方便确认生效
            self._say("已打开控制台（当前：%s）" % self._where(), "gold")
        self.app.redraw()

    def close(self) -> None:
        if self.open:
            self.open = False
            self.app.redraw()

    def _where(self) -> str:
        a = self.app
        if a.battle is not None:
            try:
                s = a.battle.snapshot()
                return "战斗中 回合%d 总部%d/%d 补给%d" % (
                    s["turn"], s["player"]["hp"], s["player"]["max_hp"],
                    s["player"]["energy"])
            except Exception:
                return "战斗中"
        if a.run is not None:
            return "战役 第%d幕 总部%d/%d 金币%d" % (
                a.run.act, a.run.hp, a.run.max_hp, a.run.gold)
        return "主菜单"

    # ------------------------------------------------------------------ #
    # 输出
    # ------------------------------------------------------------------ #
    _COLORS = {"ok": "#7BC950", "err": "#A8322D", "gold": "#C9A227",
               "dim": "#9AB0C6", "text": "#E8E2D4"}

    def _notify_battle_over(self) -> None:
        """让战斗界面走正常的结束流程（含结算跳转）。"""
        try:
            view = getattr(self.app, "view", None)
            fn = getattr(view, "_check_end", None)
            if callable(fn):
                fn()
                return
            # 退路：直接推进结算
            run = getattr(self.app, "run", None)
            if run is not None:
                self.app.show("reward")
        except Exception:
            pass

    def _say(self, text: str, kind: str = "text") -> None:
        self.lines.append((str(text), kind))
        if len(self.lines) > 120:
            del self.lines[:-120]

    def _color(self, kind: str) -> str:
        return self._COLORS.get(kind, self._COLORS["text"])

    # ------------------------------------------------------------------ #
    # 键盘
    # ------------------------------------------------------------------ #
    def on_key(self, event) -> bool:
        """返回 True 表示已消费该按键。"""
        if not self.open:
            return False
        k = getattr(event, "keysym", "")
        ch = getattr(event, "char", "")
        if k in ("Escape", "F1"):
            self.close()
            return True
        if k in ("Return", "KP_Enter"):
            self.submit()
            return True
        if k == "BackSpace":
            self.buf = self.buf[:-1]
        elif k == "Up":
            self._history(-1)
        elif k == "Down":
            self._history(1)
        elif k == "Tab":
            self._complete()
        elif ch and ch.isprintable() and len(self.buf) < self.MAX_BUF:
            self.buf += ch
        else:
            return True
        self.app.redraw()
        return True

    def _history(self, direction: int) -> None:
        """↑/↓ 翻历史指令。"""
        hist = [t for t, _ in self.lines if t.startswith("> ")]
        if not hist:
            return
        idx = getattr(self, "_hist_idx", len(hist))
        idx = max(0, min(len(hist), idx + (1 if direction < 0 else -1)))
        self._hist_idx = idx
        self.buf = hist[idx][2:] if idx < len(hist) else ""
        self.app.redraw()

    def _complete(self) -> None:
        """Tab 补全兑换码。"""
        pref = CH._normalize(self.buf)
        if not pref:
            return
        for d in CH.all_codes():
            if CH._normalize(d.code).startswith(pref):
                self.buf = d.code
                break
        self.app.redraw()

    # ------------------------------------------------------------------ #
    # 执行
    # ------------------------------------------------------------------ #
    def submit(self) -> None:
        raw = (self.buf or "").strip()
        self._hist_idx = 10 ** 6
        if not raw:
            self.close()
            return
        self.buf = ""
        self._say("> " + raw, "dim")
        try:
            self._run(raw)
        except Exception as exc:                 # 控制台绝不拖垮游戏
            self._say("执行出错：%s" % exc, "err")
        self.app.redraw()

    def _run(self, raw: str) -> None:
        parts = raw.split()
        cmd = parts[0].lower() if parts else ""
        args = parts[1:]

        # -- 内建控制指令 --
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
                "gold <n>         增加金币",
                "energy <n>       设置补给（战斗中）",
                "block <n>        设置掩体（战斗中）",
                "kill             肃清当前战斗敌人",
                "win              直接通过当前战斗",
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
            return

        if cmd in ("close", "exit", "quit"):
            self.close()
            return

        if cmd == "status":
            self._say(self._where(), "ok")
            return

        if cmd == "seed":
            self._say("种子：%s" % (getattr(self.app.run, "seed", "无战役")), "ok")
            return

        if cmd in ("music", "bgm"):
            # 支持 "music on" / "music off"
            sub = (args[0].lower() if args else "")
            if sub in ("on", "1", "true"):
                self.app.settings["music"] = True
                self.app.restart_music()
                self._say("背景音乐已开启。", "ok")
                return
            if sub in ("off", "0", "false"):
                self.app.settings["music"] = False
                self.app.restart_music()
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


        # -- 直接数值操作 --
        if cmd == "heal":
            n = self._int(args, 999)
            ok, msg = self._heal(n)
            self._say(msg, "ok" if ok else "err")
            return

        if cmd in ("hp", "maxhp", "gold", "energy", "block"):
            n = self._int(args, None)
            if n is None:
                self._say("用法：%s <数字>" % cmd, "err")
                return
            ok, msg = self._set_num(cmd, n)
            self._say(msg, "ok" if ok else "err")
            return

        if cmd in ("kill", "win"):
            b = self.app.battle
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
            # 必须通知**界面**战斗结束了。只调引擎的 _check_end()，
            # BattleView.finished 仍是 False，画面会卡在战斗里按不动。
            self._notify_battle_over()
            self._say("已肃清全部敌人。", "ok")
            return

        if cmd == "give":
            if not args:
                self._say("用法：give <卡牌id>", "err")
                return
            b = self.app.battle
            if b is None:
                self._say("只有战斗中才能直接给牌。", "err")
                return
            cid = args[0]
            from core import cards as C
            if cid not in C.CARD_DB:
                self._say("没有这张卡：%s" % cid, "err")
                return
            b.add_card_to_hand(cid)
            self._say("已加入手牌：%s" % C.CARD_DB[cid].name, "ok")
            return

        # -- 否则当作兑换码 --
        reg = getattr(self.app, "cheat_reg", None)
        if reg is None:
            reg = CH.CheatRegistry()
            self.app.cheat_reg = reg
        ok, msg = reg.redeem(raw, run=self.app.run, battle=self.app.battle,
                             meta=getattr(self.app, "meta", None))
        self._say(msg, "ok" if ok else "err")
        if ok:
            self.app.flash(T.GOLD if hasattr(T, "GOLD") else "#C9A227", 120)

    @staticmethod
    def _int(args, default: Optional[int]) -> Optional[int]:
        if not args:
            return default
        try:
            return int(args[0])
        except Exception:
            return default

    def _heal(self, n: int) -> Tuple[bool, str]:
        a = self.app
        if a.battle is not None:
            a.battle.heal(a.battle.player, n)
            return True, "战斗中总部已回复 %d（当前 %d/%d）" % (
                n, a.battle.player.hp, a.battle.player.max_hp)
        if a.run is not None:
            a.run.heal(n)
            return True, "总部已回复 %d（当前 %d/%d）" % (n, a.run.hp, a.run.max_hp)
        return False, "还没有开始战役。"

    def _set_num(self, cmd: str, n: int) -> Tuple[bool, str]:
        a = self.app
        if cmd == "gold":
            if a.run is None:
                return False, "还没有开始战役。"
            a.run.gold = max(0, n)
            return True, "金币已设为 %d" % a.run.gold
        if cmd in ("hp", "maxhp"):
            tgt = a.battle.player if a.battle is not None else a.run
            if tgt is None:
                return False, "还没有开始战役。"
            if cmd == "maxhp":
                tgt.max_hp = max(1, n)
                if tgt.hp > tgt.max_hp:
                    tgt.hp = tgt.max_hp
                return True, "耐久上限已设为 %d" % tgt.max_hp
            tgt.hp = max(1, min(n, tgt.max_hp))
            return True, "当前耐久已设为 %d/%d" % (tgt.hp, tgt.max_hp)
        if cmd in ("energy", "block"):
            if a.battle is None:
                return False, "只有战斗中才能设置。"
            p = a.battle.player
            if cmd == "energy":
                p.energy = max(0, n)
                return True, "补给已设为 %d" % p.energy
            p.block = max(0, n)
            return True, "掩体已设为 %d" % p.block
        return False, "未知指令。"

    # ------------------------------------------------------------------ #
    # 绘制（由 App 在主画布最后调用）
    # ------------------------------------------------------------------ #
    def draw(self, canvas, w: float, h: float) -> None:
        if not self.open:
            return
        from ui.theme import (round_rect, vgradient)  # 局部导入避免循环

        ph = self.HEIGHT
        top = h - ph
        # 背板
        vgradient(canvas, 0, top, w, h, "#0B0906", "#141109", steps=28)
        canvas.create_rectangle(0, top, w, top + 3, fill=T.GOLD, outline="")
        # 标题栏
        canvas.create_text(20, top + 22, text="控 制 台",
                           font=T.FONT_H1, fill=T.GOLD, anchor="w")
        canvas.create_text(140, top + 24,
                           text="F1/Esc 关闭 · Enter 执行 · Tab 补全 · ↑↓ 历史",
                           font=T.FONT_SMALL, fill=T.TEXT_FAINT, anchor="w")

        # 历史区
        y = top + 52
        shown = self.lines[-self.MAX_LINES:]
        for text, kind in shown:
            canvas.create_text(20, y, text=text[:96], font=T.FONT_SMALL,
                               fill=self._color(kind), anchor="w")
            y += 19

        # 输入行
        iy = h - 34
        canvas.create_line(16, iy - 14, w - 16, iy - 14,
                           fill=T.BORDER, width=1)
        canvas.create_text(20, iy, text="›", font=T.FONT_H2,
                           fill=T.GOLD, anchor="w")
        canvas.create_text(42, iy, text=self.buf or "",
                           font=T.FONT_H2, fill=T.TEXT, anchor="w")
        # 光标
        if (self._blink % 60) < 32:
            cx = 42 + len(self.buf) * 10.2
            canvas.create_line(cx, iy - 12, cx, iy + 12, fill=T.GOLD, width=2)

    def tick(self) -> None:
        if self.open:
            self._blink = (self._blink + 1) % 120
