"""钢铁战线 Steel Frontline — QApplication 主窗口与界面路由 (qapp.py)
================================================================
把 12 个界面接成一局完整的游戏：

    menu ──new_run──> map ──move_to(kind)──┬─> battle ──won──> reward ──> map
                                           ├─> event  ──────────────> map
                                           ├─> shop   ──────────────> map
                                           ├─> rest   ──────────────> map
                                           └─> treasure ────────────> map
    battle ──lost──> gameover ──> menu
    boss 击败 ──> 进入下一幕（advance_act）

设计要点
--------
* 界面用 :class:`QStackedWidget` 路由，不重建窗口。
* 战斗节奏严格走附录 A.6；``QTimer`` 间隔由设置里的 ``battle_step_ms`` 控制。
* 存档：每次从地图/战斗返回时调用 ``run_mod.save_run``。
* 元进度：结算时 ``MetaProgress.record_run`` 并落盘。
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QSizePolicy, QStackedWidget, QVBoxLayout,
    QWidget,
)

# 允许 `python3 qt/main_qt.py` 直接运行（把项目根加入 sys.path）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core import engine              # noqa: E402
from core import events as EV        # noqa: E402
from core import relics as R         # noqa: E402
from core import run as run_mod      # noqa: E402

from . import qtheme as T            # noqa: E402
from . import qbattle, qmap, qscreens  # noqa: E402
from . import qdeckbuild, qfx, qlobby, qsave, qupdate, qversus  # noqa: E402
from .qconsole import ConsoleOverlay  # noqa: E402


# =====================================================================
# 路由常量
# =====================================================================

SCREENS = ("menu", "map", "battle", "reward", "shop", "rest", "event",
           "deck", "gameover", "codex", "achievements", "settings",
           "stats", "pile", "lobby", "deckbuild", "versus", "saves")

DEFAULT_CFG: Dict = {
    "fullscreen": False,
    "animation": True,
    "screen_shake": True,
    "confirm_end_turn": False,
    "battle_step_ms": 400,
}


class GameWindow(QMainWindow):
    """主窗口 + 界面路由。"""

    # 后台线程检查更新完成后，用信号把结果送回 UI 线程。
    # 注意：**不能**在后台线程里直接 QTimer.singleShot —— Qt 的定时器
    # 必须由拥有事件循环的那个线程创建，否则回调会被静默丢弃
    # （这就是「点检查更新没反应」的真正原因）。
    update_checked = pyqtSignal(object, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("钢铁战线 Steel Frontline")
        self.setMinimumSize(T.MIN_WIN_W, T.MIN_WIN_H)
        self.resize(T.WIN_W, T.WIN_H)

        # --- 运行时状态 ---
        self.run = None               # RunState
        self.battle = None            # BattleState
        self.meta = run_mod.MetaProgress.load()
        self.cfg: Dict = dict(DEFAULT_CFG)
        self._ready = False
        self._load_cfg()
        # 特效开关跟随配置（默认开）
        try:
            qfx.set_enabled(bool(self.cfg.get("animation", True)))
        except Exception:
            pass
        self._pending: Dict = {}      # move_to 返回的遭遇描述
        self._gold_gain = 0
        self._history: List[str] = ["menu"]

        # --- 联机 1v1 状态 ---
        self._net = None              # core.netplay.Host / Client
        self._net_side = 0
        self._vs_deck: List[str] = []

        # --- 中央堆栈 ---
        central = QWidget(self)
        central.setSizePolicy(QSizePolicy.Policy.Expanding,
                              QSizePolicy.Policy.Expanding)
        central.setMinimumSize(T.MIN_WIN_W - 40, T.MIN_WIN_H - 60)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.stack = QStackedWidget(central)
        # QStackedWidget 必须显式 Expanding，否则会塌缩到 sizeHint(100x30)，
        # 导致所有页面的内部布局都在一个被压扁的容器里计算 —— 手牌被裁切、
        # 按钮错位等一系列问题的真正根因。
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        self.stack.setMinimumSize(T.MIN_WIN_W - 40, T.MIN_WIN_H - 60)
        lay.addWidget(self.stack)
        self.setCentralWidget(central)

        # --- 实例化全部界面 ---
        self.screens: Dict[str, QWidget] = {}
        self._build_all_screens()

        # --- 全局控制台（F1 呼出）---
        self._build_console()

        # 信号接线（必须在界面建好之后）
        self._wire()
        self._install_cheat_hook()
        self._connect_update_signal()
        self.show_screen("menu")
        self._ready = True
        self._start_update_check()

    # ------------------------------------------------------- 更新检查 -- #
    def _start_update_check(self) -> None:
        """启动后延迟几秒在后台检查更新（不阻塞、离线静默失败）。"""
        try:
            from PyQt6.QtCore import QTimer
            # 等界面稳定再查，避免和启动动画抢资源
            QTimer.singleShot(2500, self.check_updates)
        except Exception:
            pass

    def check_updates(self, silent: bool = True) -> None:
        """检查新版本。silent=True 时没有更新就不打扰用户。"""
        if getattr(self, "_update_checking", False):
            return
        self._update_checking = True
        try:
            from core import updater as _up
        except Exception:
            self._update_checking = False
            return

        def on_result(info, err):
            # 用**信号**跨线程投递：Qt 会自动排队到 UI 线程执行。
            # （早期版本这里用 QTimer.singleShot，但那是从后台线程调用的，
            #   Qt 不接受，回调被静默丢弃 —— 表现为"点检查更新没反应"。）
            try:
                self.update_checked.emit(info, str(err or ""), bool(silent))
            except Exception as exc:
                print(f"[qt.app] emit update_checked failed: {exc!r}",
                      flush=True)

        try:
            _up.check_async(on_result)
        except Exception:
            self._update_checking = False

    def _on_update_checked(self, info, err, silent: bool) -> None:
        self._update_checking = False
        if info is None:
            if not silent:
                try:
                    from core import version as _V
                    label = _V.short()
                except Exception:
                    label = "?"
                # _V.short() 已经带 "v" 前缀，这里不要再加一个
                QMessageBox.information(
                    self, "检查更新",
                    "当前已是最新版本（%s）。\n\n"
                    "（如果刚发布不久，可能还没同步到，稍后再试。）" % label)
            return
        try:
            qupdate.show_update_dialog(info, self)
        except Exception as exc:
            print(f"[qt.app] update dialog failed: {exc!r}", flush=True)

    def _connect_update_signal(self) -> None:
        """把更新检查结果接到 UI（跨线程安全）。"""
        try:
            self.update_checked.connect(self._on_update_checked)
        except Exception:
            pass

    def _install_cheat_hook(self) -> None:
        """让兑换码结束战斗后能通知界面（否则画面会卡在战斗里）。"""
        try:
            from core import cheats as _ch

            def _on_over(result: str) -> None:
                try:
                    bs = self.screens.get("battle")
                    if bs is not None and callable(getattr(bs, "_check_end", None)):
                        bs._check_end()          # 走正常结束流程
                    else:
                        self.on_battle_finished(str(result))
                except Exception:
                    pass

            _ch.set_battle_over_hook(_on_over)
        except Exception:
            pass

    def _build_console(self) -> None:
        """构造/重建全局控制台（F1）。"""
        old = getattr(self, "console", None)
        if old is not None:
            try:
                old.setParent(None)
                old.deleteLater()
            except Exception:
                pass
        self.console = ConsoleOverlay(self)
        self.console.setGeometry(0, self.height() - ConsoleOverlay.HEIGHT,
                                 self.width(), ConsoleOverlay.HEIGHT)
        self.console.raise_()
        try:
            from PyQt6.QtGui import QShortcut, QKeySequence
            sc = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(self.toggle_console)
            self._f1 = sc
        except Exception:
            self._f1 = None

    def _build_all_screens(self) -> None:
        """构造/重建全部界面。

        语言切换时整个界面都要换文案 —— 与其给上千个控件逐个改文字，
        不如**重建**（Qt 构造这些界面很快，实测 <100ms）。
        """
        if self.screens:
            for w in list(self.screens.values()):
                try:
                    self.stack.removeWidget(w)
                    w.setParent(None)
                    w.deleteLater()
                except Exception:
                    pass
            self.screens.clear()
        self.screens["menu"] = qscreens.MenuScreen(self, self.meta)
        self.screens["map"] = qmap.MapScreen(self)
        self.screens["battle"] = qbattle.BattleScreen(self)
        self.screens["reward"] = qscreens.RewardScreen(self)
        self.screens["shop"] = qscreens.ShopScreen(self)
        self.screens["rest"] = qscreens.RestScreen(self)
        self.screens["event"] = qscreens.EventScreen(self)
        self.screens["deck"] = qscreens.DeckScreen(self)
        self.screens["gameover"] = qscreens.GameOverScreen(self)
        self.screens["codex"] = qscreens.CodexScreen(self)
        self.screens["achievements"] = qscreens.AchievementScreen(self)
        self.screens["settings"] = qscreens.SettingsScreen(self, self.cfg)
        self.screens["stats"] = qscreens.StatsScreen(self)
        self.screens["saves"] = qsave.SaveScreen(self)
        self.screens["pile"] = qscreens.PileScreen(self)
        # --- 联机 1v1：大厅 → 卡组构筑 → 对战 ---
        self.screens["lobby"] = qlobby.LobbyScreen(self)
        self.screens["deckbuild"] = qdeckbuild.DeckBuildScreen(self)
        self.screens["versus"] = qversus.VersusScreen(self)

        for name in SCREENS:
            w = self.screens.get(name)
            if w is None:
                continue
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.stack.addWidget(w)

    def rebuild_screens(self) -> None:
        """语言切换后重建全部界面，并停在当前页。"""
        cur = "menu"
        try:
            w = self.stack.currentWidget()
            for name, widget in self.screens.items():
                if widget is w:
                    cur = name
                    break
        except Exception:
            pass
        try:
            self._build_all_screens()
            self._build_console()
            # 关键：新建的界面是**全新的对象**，旧对象上的信号连接已随
            # 其销毁而失效。必须在重建后重新接线，否则所有按钮都会失灵
            # （用户实际遇到：改完语言后点「开始战役」没反应）。
            self._wire()
            self._install_cheat_hook()
            self.show_screen(cur if cur in self.screens else "menu")
        except Exception:
            try:
                self.show_screen("menu")
            except Exception:
                pass

    # =================================================================
    # BGM（music/ 目录由用户放置）
    # =================================================================
    def _save_cfg(self) -> None:
        """把界面设置写进 prefs.json（下次启动沿用）。"""
        try:
            import json as _json
            import os as _os
            d = getattr(run_mod, "DATA_DIR", None) or "."
            p = _os.path.join(d, "prefs.json")
            cur = {}
            try:
                cur = _json.load(open(p, encoding="utf-8"))
                if not isinstance(cur, dict):
                    cur = {}
            except Exception:
                cur = {}
            cur["cfg"] = dict(self.cfg)
            _os.makedirs(_os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                _json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _load_cfg(self) -> None:
        """启动时恢复界面设置。"""
        try:
            import json as _json
            import os as _os
            d = getattr(run_mod, "DATA_DIR", None) or "."
            p = _os.path.join(d, "prefs.json")
            cur = _json.load(open(p, encoding="utf-8"))
            saved = cur.get("cfg") if isinstance(cur, dict) else None
            if isinstance(saved, dict):
                self.cfg.update({k: v for k, v in saved.items()
                                 if k in DEFAULT_CFG})
        except Exception:
            pass

    def _music_for(self, screen: str) -> None:
        try:
            from core import audio
            vol = int(self.cfg.get("volume", 70))
            on = bool(self.cfg.get("music", True))
            audio.on_screen(screen, volume=vol, enabled=on)
        except Exception:
            pass

    def restart_music(self) -> None:
        try:
            self._music_for(self._current_name())
        except Exception:
            pass

    # =================================================================
    # 全局控制台
    # =================================================================
    def toggle_console(self) -> None:
        con = getattr(self, "console", None)
        if con is None:
            return
        con.setGeometry(0, max(0, self.height() - ConsoleOverlay.HEIGHT),
                        self.width(), ConsoleOverlay.HEIGHT)
        con.toggle()
        con.raise_()

    def keyPressEvent(self, ev):  # noqa: N802
        """Esc 关闭控制台；F1 切换。"""
        con = getattr(self, "console", None)
        if con is not None and con.isVisible():
            if ev.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F1):
                con.hide_console()
                return
        if ev.key() == Qt.Key.Key_F1:
            self.toggle_console()
            return
        super().keyPressEvent(ev)

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        con = getattr(self, "console", None)
        if con is not None:
            con.setGeometry(0, max(0, self.height() - ConsoleOverlay.HEIGHT),
                            self.width(), ConsoleOverlay.HEIGHT)

    def refresh_current(self) -> None:
        """刷新当前界面（兑换码/控制台改动了状态后调用）。"""
        try:
            name = self._current_name()
            w = self.screens.get(name)
            if w is not None and hasattr(w, "refresh"):
                w.refresh()
        except Exception:
            pass

    def _current_name(self) -> str:
        cur = self.stack.currentWidget()
        for k, v in self.screens.items():
            if v is cur:
                return k
        return "menu"

    # =================================================================
    # 信号接线
    # =================================================================
    def _wire(self) -> None:
        m = self.screens["menu"]
        m.new_run.connect(self.start_new_run)
        m.continue_run.connect(self.continue_run)
        m.open_codex.connect(lambda: self.show_screen("codex"))
        m.open_achievements.connect(lambda: self.show_screen("achievements"))
        m.open_settings.connect(lambda: self.show_screen("settings"))
        m.open_stats.connect(lambda: self.show_screen("stats"))
        m.open_versus.connect(self.open_lobby)
        m.open_saves.connect(self.open_saves)

        # --- 联机 1v1 链路 ---
        lb = self.screens["lobby"]
        lb.connected.connect(self.on_lobby_connected)
        lb.closed.connect(self.on_lobby_closed)

        db = self.screens["deckbuild"]
        db.deck_confirmed.connect(self.on_deck_confirmed)
        db.closed.connect(self.on_deckbuild_closed)

        vs = self.screens["versus"]
        vs.battle_over.connect(self.on_versus_over)
        vs.left_match.connect(self.on_versus_left)

        mp = self.screens["map"]
        mp.node_selected.connect(self.on_node_selected)
        mp.open_deck.connect(lambda: self._open_deck("牌 组", None))
        mp.open_codex.connect(lambda: self.show_screen("codex"))
        mp.save_and_quit.connect(self.save_and_quit)

        bt = self.screens["battle"]
        bt.battle_finished.connect(self.on_battle_finished)
        bt.request_piles.connect(self._open_piles)

        self.screens["reward"].done.connect(self.on_reward_done)

        sh = self.screens["shop"]
        sh.done.connect(self.on_shop_done)
        sh.buy_card.connect(self.on_buy_card)
        sh.buy_relic.connect(self.on_buy_relic)
        sh.buy_potion.connect(self.on_buy_potion)
        sh.remove_card.connect(self.on_shop_remove)

        rs = self.screens["rest"]
        rs.done.connect(self.on_rest_done)
        rs.choose_rest.connect(self.on_rest_heal)
        rs.choose_upgrade.connect(self.on_rest_upgrade)

        self.screens["event"].done.connect(self.on_event_done)

        self.screens["deck"].closed.connect(self._on_deck_closed)
        self.screens["pile"].closed.connect(self._on_pile_closed)

        self.screens["codex"].closed.connect(self._back_to)
        self.screens["achievements"].closed.connect(self._back_to)
        self.screens["stats"].closed.connect(self._back_to)
        self.screens["saves"].closed.connect(self._back_to)
        self.screens["saves"].load_run.connect(self._load_slot)
        self.screens["settings"].closed.connect(self.on_settings_closed)
        self.screens["settings"].wipe_meta.connect(self.on_wipe_meta)
        self.screens["settings"].wipe_save.connect(self.on_wipe_save)
        self.screens["gameover"].finished.connect(lambda: self.show_screen("menu"))

    # =================================================================
    # 路由
    # =================================================================
    def show_screen(self, name: str) -> None:
        if name not in self.screens:
            print(f"[qt.app] unknown screen: {name}", flush=True)
            return
        w = self.screens[name]
        # 离开对战界面时停掉它的计时器，避免后台空转与残留网络轮询
        if name != "versus":
            try:
                self.screens["versus"].stop()
            except Exception:
                pass
        # 界面过渡：淡入淡出（可在设置里关掉）
        cur = self.stack.currentWidget()
        if cur is not None and cur is not w and getattr(self, "_ready", False):
            qfx.fade_switch(self, lambda: self.stack.setCurrentWidget(w))
        else:
            self.stack.setCurrentWidget(w)
        self._music_for(name)
        if name not in ("menu",) and (not self._history or self._history[-1] != name):
            self._history.append(name)
        # 进入界面时按需补齐内容，保证任何入口都不会看到空白页
        try:
            if name == "map" and self.run is not None:
                w.set_run(self.run)
            elif name == "codex":
                w.setup(self.meta)
            elif name == "achievements":
                w.setup(self.meta)
            elif name == "stats":
                w.setup(self.meta)
            elif name == "shop" and self.run is not None and not w._inv:
                # 直接进入补给站（而非经地图派发）时补一份货架
                w.setup(self.run)
            elif name == "rest" and self.run is not None and not w._upgradable:
                w.setup(self.run)
            elif name == "deck" and self.run is not None and not w._cards:
                w.setup(self.run)
            elif name == "pile" and self.battle is not None:
                w.setup(self.battle)
            elif name == "reward" and self.run is not None and not w._cards:
                w.setup(self.run)
            elif name == "deckbuild":
                # 未选卡组时先给一套推荐，避免界面看起来是空的
                if not w.picked:
                    from core import deckbuild as _DB
                    w.set_deck(_DB.random_deck(__import__("random").Random(),
                                               _DB.DECK_SIZE_MIN))
        except Exception as exc:
            print(f"[qt.app] refresh {name} failed: {exc!r}", flush=True)
        w.setFocus()

    def _back_to(self) -> None:
        """从只读界面（图鉴/成就/战绩）返回上一个界面。"""
        prev = "menu"
        for name in reversed(self._history[:-1]):
            if name not in ("codex", "achievements", "stats", "deck", "pile", "settings"):
                prev = name
                break
        self.show_screen(prev)

    def _open_deck(self, title: str, cards) -> None:
        if self.run is None and cards is None:
            return
        try:
            d = self.screens["deck"]
            d.setup(self.run, title, cards)
            self._deck_from = self.stack.currentWidget()
            self.show_screen("deck")
        except Exception as exc:
            print(f"[qt.app] open deck failed: {exc!r}", flush=True)

    def _on_deck_closed(self) -> None:
        target = getattr(self, "_deck_from", None)
        if target is not None:
            self.stack.setCurrentWidget(target)
        else:
            self._back_to()

    def _open_piles(self) -> None:
        try:
            self.screens["pile"].setup(self.battle)
            self._pile_from = self.stack.currentWidget()
            self.show_screen("pile")
        except Exception as exc:
            print(f"[qt.app] open piles failed: {exc!r}", flush=True)

    def _on_pile_closed(self) -> None:
        target = getattr(self, "_pile_from", None)
        if target is not None:
            self.stack.setCurrentWidget(target)
        else:
            self._back_to()

    # =================================================================
    # 联机 1v1 路由：大厅 → 卡组构筑 → 对战
    # =================================================================
    def open_lobby(self) -> None:
        """从主菜单进入联机大厅。"""
        self._net = None            # Host / Client
        self._net_side = 0
        self._vs_deck = []
        try:
            self.screens["lobby"].refresh()
        except Exception:
            pass
        self.show_screen("lobby")

    def on_lobby_connected(self, side: int, net) -> None:
        """大厅连上对手 → 进入卡组构筑。"""
        self._net = net
        self._net_side = int(side)
        db = self.screens["deckbuild"]
        who = "房主" if self._net_side == 0 else "加入方"
        try:
            db.set_context("net", "联机对战 · 你是%s" % who)
        except Exception:
            pass
        self.show_screen("deckbuild")

    def on_lobby_closed(self) -> None:
        self._cleanup_net()
        self.show_screen("menu")

    def on_deckbuild_closed(self) -> None:
        """卡组界面返回：联机时回大厅，否则回主菜单。"""
        if self._net is not None:
            self._cleanup_net()
            self.open_lobby()
        else:
            self.show_screen("menu")

    def on_deck_confirmed(self, card_ids) -> None:
        """卡组确认 → 联机则发给对手；全部就绪后由 netplay 发 start 开局。"""
        ids = list(card_ids or [])
        self._vs_deck = ids
        if self._net is None:
            # 单机试玩：本地开一局
            self._start_local_versus(ids)
            return
        try:
            self._net.send_deck(ids)
        except Exception as exc:
            print(f"[qt.app] send_deck failed: {exc!r}", flush=True)
            return
        vs = self.screens["versus"]
        try:
            vs.start_net(self._net, self._net_side,
                         names=["房主", "加入方"])
        except Exception as exc:
            print(f"[qt.app] start_net failed: {exc!r}", flush=True)
        self.show_screen("versus")

    def _start_local_versus(self, ids) -> None:
        """单机试玩：用对手随机卡组本地开一局（不需要网络）。"""
        try:
            import random as _r
            from core import deckbuild as _DB
            from core.versus import VersusBattle
            rng = _r.Random()
            foe = _DB.random_deck(_r.Random(), len(ids) or 30)
            battle = VersusBattle(list(ids), list(foe), rng=rng)
            vs = self.screens["versus"]
            vs.start_local(battle, my_side=0, names=["我方", "对手"])
            self.show_screen("versus")
        except Exception as exc:
            print(f"[qt.app] local versus failed: {exc!r}", flush=True)

    def on_versus_over(self, result: str) -> None:
        """对战结束：不自动退出，让玩家看到结算横幅。"""
        print(f"[qt.app] versus over: {result}", flush=True)

    def on_versus_left(self, reason: str) -> None:
        self._cleanup_net()
        self.show_screen("menu")

    def _cleanup_net(self) -> None:
        net = getattr(self, "_net", None)
        if net is not None:
            try:
                net.close()
            except Exception:
                pass
        self._net = None

    # =================================================================
    # 开局 / 续玩
    # =================================================================
    def start_new_run(self, ascension: int = 0, seed=None) -> None:
        self._slot_id = None          # 新开局：下次保存时建新槽位
        self.run = run_mod.RunState()
        try:
            self.run.new_run(seed=seed, ascension=int(ascension))
        except Exception as exc:
            print(f"[qt.app] new_run failed: {exc!r}", flush=True)
            QMessageBox.warning(self, "无法开始战役", f"引擎拒绝了这次开局：\n{exc}")
            return
        self.battle = None
        self._pending = {}
        run_mod.save_run(self.run)
        self.show_screen("map")

    def continue_run(self) -> None:
        r = run_mod.load_run()
        if r is None:
            QMessageBox.information(self, "没有存档", "当前没有可继续的战役。")
            return
        self.run = r
        self.battle = None
        self._pending = {}
        self.show_screen("map")

    def save_and_quit(self) -> None:
        self._persist_run()
        self.show_screen("menu")

    def _persist_run(self) -> None:
        """把当前战役写进**存档槽**（同时保持老路径可用）。

        存档列表读的是 data/saves/，所以这里必须往槽里写，否则
        「保存并退出」后在存档管理里看不到（用户实际遇到）。
        """
        if self.run is None:
            return
        try:
            from core import saves as _sv
            sid = getattr(self, "_slot_id", None)
            if sid and _sv.get(sid) is not None:
                _sv.save_to(sid, self.run)
            else:
                # 新的一局：第一次保存时创建槽位
                name = "第 %d 幕 · 第 %d 层" % (
                    int(getattr(self.run, "act", 0) or 0) + 1,
                    int(getattr(self.run, "floor", 0) or 0))
                self._slot_id = _sv.save_new(self.run, name)
            # 老路径也写一份，保证「继续上次战役」照常可用
            run_mod.save_run(self.run)
        except Exception as exc:
            print(f"[qt.app] save failed: {exc!r}", flush=True)
            try:
                run_mod.save_run(self.run)
            except Exception:
                pass

    # =================================================================
    # 地图推进
    # =================================================================
    def on_node_selected(self, node_id: int) -> None:
        if self.run is None:
            return
        try:
            info = self.run.move_to(node_id)
        except Exception as exc:
            print(f"[qt.app] move_to failed: {exc!r}", flush=True)
            return
        kind = str(info.get("kind", "none"))
        if kind == "none":
            return
        self._pending = info
        run_mod.save_run(self.run)
        self._dispatch_node(info)

    def _dispatch_node(self, info: Dict) -> None:
        """按 move_to() 返回的 kind 派发到对应界面。"""
        kind = str(info.get("kind", "none"))
        if kind in ("battle", "elite", "boss"):
            enc = info.get("encounter") or self.run.roll_encounter(
                "normal" if kind == "battle" else kind)
            self.start_battle(enc)
        elif kind == "event":
            ev = info.get("event")
            if ev is None:
                # 契约保证 event 一定存在；防御性兜底 —— 转成一场遭遇战，
                # 并把该事件标记为已见，避免死循环。
                try:
                    ev = EV.random_event(self.run.rng, self.run.act,
                                         set(self.run.seen_events))
                except Exception:
                    ev = None
            if ev is None:
                self.start_battle(self.run.roll_encounter("normal"))
                return
            try:
                if ev.id not in self.run.seen_events:
                    self.run.seen_events.append(ev.id)
            except Exception:
                pass
            self.screens["event"].setup(self.run, ev)
            self.show_screen("event")
        elif kind == "shop":
            self.screens["shop"].setup(self.run, info.get("shop"))
            self.show_screen("shop")
        elif kind == "rest":
            self._rest_used = False       # 每个休息节点只能用一次
            self.screens["rest"].setup(self.run)
            self.show_screen("rest")
        elif kind == "treasure":
            self._handle_treasure(info.get("treasure") or {})
        else:
            # 未知节点类型：回地图，避免卡死
            self.show_screen("map")

    def _handle_treasure(self, tr: Dict) -> None:
        """缴获：直接结算，然后用奖励界面展示结果。"""
        gold = int(tr.get("gold", 0) or 0)
        rid = tr.get("relic_id")
        potion = tr.get("potion_id")
        msgs = []
        if gold:
            try:
                self.run.add_gold(gold)
            except Exception:
                pass
            msgs.append(f"缴获 {gold} 金币")
        if rid:
            try:
                self.run.add_relic(rid)
                rd = R.RELIC_DB.get(rid)
                msgs.append(f"获得勋章：{rd.name if rd else rid}")
                self.meta.see_relic(rid)
            except Exception:
                pass
        if potion:
            try:
                self.run.add_potion(potion)
                msgs.append("获得补给品")
            except Exception:
                pass
        if tr.get("curse_id"):
            try:
                self.run.add_card(tr["curse_id"])
                msgs.append("获得一张诅咒牌")
            except Exception:
                pass
        text = tr.get("text") or "、".join(msgs) or "空空如也。"
        self._show_reward(gold=0, cards=[], relic_id=rid, banner=str(text),
                          relic_already_given=True)

    # =================================================================
    # 战斗
    # =================================================================
    def start_battle(self, encounter: Optional[Dict] = None) -> None:
        """创建并进入一场战斗。``encounter`` 省略时自动 roll 一场普通遭遇。"""
        if self.run is None:
            return
        if encounter is None:
            try:
                encounter = self.run.roll_encounter("normal")
            except Exception:
                encounter = {"kind": "normal", "enemies": []}
        try:
            self.battle = engine.make_battle(self.run, encounter)
        except Exception as exc:
            print(f"[qt.app] make_battle failed: {exc!r}", flush=True)
            self.show_screen("map")
            return
        bs = self.screens["battle"]
        bs.STEP_MS = int(self.cfg.get("battle_step_ms", 400))
        try:
            bs._timer.setInterval(bs.STEP_MS)
        except Exception:
            pass
        bs.start(self.run, self.battle)
        self.show_screen("battle")

    def on_battle_finished(self, result: str) -> None:
        """战斗结束：结算金币/掉落，然后进奖励或结算界面。"""
        if self.run is None or self.battle is None:
            return
        won = (result == "won")
        gold_before = self.run.gold
        try:
            self.run.finish_battle(result, self.battle)
        except Exception as exc:
            print(f"[qt.app] finish_battle failed: {exc!r}", flush=True)
        gold_gain = max(0, int(self.run.gold) - int(gold_before))
        self._gold_gain = gold_gain

        # 记录图鉴
        try:
            for e in self.battle.enemies:
                self.meta.see_enemy(getattr(e, "def_id", ""))
        except Exception:
            pass

        if not won:
            self._finish_game(won=False)
            return

        # 胜利：精英/Boss 额外勋章
        relic_id = None
        try:
            kind = str((self._pending or {}).get("kind", "battle"))
            if kind in ("elite", "boss"):
                ids = self.run.offer_relic_rewards(1)
                if ids:
                    relic_id = ids[0]
                    self.run.add_relic(relic_id)
                    self.meta.see_relic(relic_id)
        except Exception as exc:
            print(f"[qt.app] relic reward failed: {exc!r}", flush=True)

        # Boss 击败 → 进入下一幕
        is_boss = False
        try:
            is_boss = bool((self._pending or {}).get("kind") == "boss")
        except Exception:
            is_boss = False

        cards = []
        try:
            cards = list(self.run.offer_card_rewards(3))
        except Exception as exc:
            print(f"[qt.app] card rewards failed: {exc!r}", flush=True)

        if is_boss:
            self._advance_act()
            return

        self._show_reward(gold=gold_gain, cards=cards, relic_id=relic_id)

    def _advance_act(self) -> None:
        try:
            self.run.advance_act()
        except Exception as exc:
            print(f"[qt.app] advance_act failed: {exc!r}", flush=True)
        self.battle = None
        run_mod.save_run(self.run)
        # 通关（第三幕后）
        if int(getattr(self.run, "act", 1)) > 3:
            self._finish_game(won=True)
        else:
            self.show_screen("map")

    def _show_reward(self, gold: int = 0, cards: Optional[List] = None,
                     relic_id: Optional[str] = None, banner: str = "",
                     relic_already_given: bool = False) -> None:
        try:
            rs = self.screens["reward"]
            rs.setup(self.run, gold=gold, cards=cards,
                     relic_id=None if relic_already_given else relic_id)
            if banner:
                rs.tb.subtitle = banner
            self._relic_from_reward = relic_id
            self.show_screen("reward")
        except Exception as exc:
            print(f"[qt.app] reward screen failed: {exc!r}", flush=True)
            self.show_screen("map")

    def on_reward_done(self) -> None:
        """奖励界面结束：加入卡牌，然后回地图。"""
        rs = self.screens["reward"]
        card = getattr(rs, "picked_card", None)
        if card is not None and self.run is not None:
            try:
                self.run.add_card(getattr(card, "id", None) or card)
                try:
                    self.meta.see_card(getattr(card, "id", ""))
                except Exception:
                    pass
            except Exception as exc:
                print(f"[qt.app] add_card failed: {exc!r}", flush=True)
        rid = getattr(self, "_relic_from_reward", None)
        if rid:
            try:
                self.run.add_relic(rid)
                self.meta.see_relic(rid)
            except Exception:
                pass
            self._relic_from_reward = None
        self.battle = None
        run_mod.save_run(self.run)
        self.show_screen("map")

    # =================================================================
    # 结算
    # =================================================================
    def _finish_game(self, won: bool) -> None:
        self.battle = None
        new_ach: List[str] = []
        score = 0
        try:
            new_ach = list(self.meta.record_run(self.run, won) or [])
        except Exception as exc:
            print(f"[qt.app] record_run failed: {exc!r}", flush=True)
        try:
            score = int(self.run.final_score())
        except Exception:
            score = int(getattr(self.run, "score", 0) or 0)
        try:
            self.meta.save()
        except Exception as exc:
            print(f"[qt.app] meta save failed: {exc!r}", flush=True)
        try:
            run_mod.save_run(None)     # 清掉局内存档
        except Exception:
            pass
        try:
            self.screens["gameover"].setup(self.run, won, new_ach, score)
        except Exception as exc:
            print(f"[qt.app] gameover setup failed: {exc!r}", flush=True)
        self.show_screen("gameover")

    # =================================================================
    # 事件 / 商店 / 医院
    # =================================================================
    def on_event_done(self) -> None:
        self._persist_run()
        self.show_screen("map")

    def on_shop_done(self) -> None:
        self._persist_run()
        self.show_screen("map")

    def on_buy_card(self, idx: int, price: int) -> None:
        if self.run is None or self.run.gold < price:
            return
        inv = getattr(self.screens["shop"], "_inv", {}) or {}
        cards = inv.get("cards", [])
        if idx < 0 or idx >= len(cards):
            return
        cd = cards[idx]
        if cd.id in self.run.deck_ids() if hasattr(self.run, "deck_ids") else False:
            return
        try:
            self.run.add_card(cd.id)
            self.run.gold -= int(price)
            self.meta.see_card(cd.id)
        except Exception as exc:
            print(f"[qt.app] buy card failed: {exc!r}", flush=True)
            return
        # 从货架移除
        try:
            inv["cards"].pop(idx)
            inv.setdefault("card_prices", {}).pop(cd.id, None)
        except Exception:
            pass
        self.screens["shop"].setup(self.run, inv)

    def on_buy_relic(self, relic_id: str, price: int) -> None:
        if self.run is None or self.run.gold < price:
            return
        try:
            self.run.add_relic(relic_id)
            self.run.gold -= int(price)
            self.meta.see_relic(relic_id)
        except Exception as exc:
            print(f"[qt.app] buy relic failed: {exc!r}", flush=True)
            return
        inv = getattr(self.screens["shop"], "_inv", {}) or {}
        try:
            inv["relics"] = [r for r in inv.get("relics", []) if r.id != relic_id]
            inv.setdefault("relic_prices", {}).pop(relic_id, None)
        except Exception:
            pass
        self.screens["shop"].setup(self.run, inv)

    def on_buy_potion(self, pid: str, price: int) -> None:
        if self.run is None or self.run.gold < price:
            return
        try:
            self.run.add_potion(pid)
            self.run.gold -= int(price)
        except Exception as exc:
            print(f"[qt.app] buy potion failed: {exc!r}", flush=True)
            return
        inv = getattr(self.screens["shop"], "_inv", {}) or {}
        try:
            inv["potions"] = [p for p in inv.get("potions", []) if p != pid]
        except Exception:
            pass
        self.screens["shop"].setup(self.run, inv)

    def on_shop_remove(self) -> None:
        """商店删卡：打开牌组进入选择模式。"""
        if self.run is None:
            return
        inv = getattr(self.screens["shop"], "_inv", {}) or {}
        price = int(inv.get("remove_price", 75))
        if self.run.gold < price:
            return
        d = self.screens["deck"]
        d.select_mode = True
        d.setup(self.run, "选 择 要 移 除 的 卡 牌", list(self.run.deck))
        self._deck_from = self.screens["shop"]
        self._remove_price = price
        try:
            d.remove_requested.disconnect()
        except Exception:
            pass
        d.remove_requested.connect(self._do_remove_card)
        self.show_screen("deck")

    def _do_remove_card(self, uid: int) -> None:
        if self.run is None:
            return
        price = int(getattr(self, "_remove_price", 75))
        try:
            ok = bool(self.run.remove_card(uid))
        except Exception as exc:
            print(f"[qt.app] remove_card failed: {exc!r}", flush=True)
            ok = False
        d = self.screens["deck"]
        d.select_mode = False
        try:
            d.remove_requested.disconnect()
        except Exception:
            pass
        if not ok:
            self._on_deck_closed()
            return
        try:
            self.run.gold -= price
            self.run.remove_count = int(getattr(self.run, "remove_count", 0)) + 1
        except Exception:
            pass
        inv = getattr(self.screens["shop"], "_inv", {}) or {}
        new_price = int(inv.get("remove_price", 75)) + 25
        inv["remove_price"] = new_price
        self.screens["shop"].setup(self.run, inv)
        self.show_screen("shop")

    def open_saves(self) -> None:
        """打开存档管理。"""
        try:
            self.screens["saves"].refresh()
        except Exception as exc:
            print(f"[qt.app] saves refresh failed: {exc!r}", flush=True)
        self.show_screen("saves")

    def _load_slot(self, slot_id: str) -> None:
        """从存档管理里读一个存档并进入游戏。"""
        try:
            from core import saves as _sv
            r = _sv.load(slot_id)
        except Exception as exc:
            print(f"[qt.app] load slot failed: {exc!r}", flush=True)
            r = None
        if r is None:
            try:
                self.screens["saves"]._say("读取失败：存档已损坏或被删除。")
            except Exception:
                pass
            return
        self.run = r
        self.battle = None
        self._pending = {}
        self._slot_id = slot_id        # 之后保存会写回这个槽
        self.show_screen("map")

    def on_rest_done(self) -> None:
        self._persist_run()
        self.show_screen("map")

    def on_rest_heal(self) -> None:
        """休整：回血**并立即结束本节点**。

        旧实现只回血、不结束节点，导致可以无限点「进行休整」刷满耐久
        （用户实际遇到）。休整是一次性的营地行为，用过就离开。
        """
        if self.run is None:
            return
        if getattr(self, "_rest_used", False):
            return
        self._rest_used = True
        try:
            self.run.heal(self.run.rest_heal_amount())
        except Exception as exc:
            print(f"[qt.app] heal failed: {exc!r}", flush=True)
        try:
            run_mod.save_run(self.run)
        except Exception:
            pass
        self.show_screen("map")          # 用完即走，不能反复点

    def on_rest_upgrade(self, uid: int) -> None:
        """锻造：升级一张牌后同样结束节点。"""
        if self.run is None:
            return
        if getattr(self, "_rest_used", False):
            return
        self._rest_used = True
        try:
            self.run.upgrade_card(uid)
        except Exception as exc:
            print(f"[qt.app] upgrade failed: {exc!r}", flush=True)
        try:
            run_mod.save_run(self.run)
        except Exception:
            pass
        self.show_screen("map")

    # =================================================================
    # 设置 / 数据
    # =================================================================
    def on_settings_closed(self) -> None:
        try:
            self.cfg.update(self.screens["settings"].values())
        except Exception:
            pass
        # 用户点的是「保存并关闭」—— 必须**真的保存当前战役**。
        # 旧实现只存了界面设置，战役进度被丢掉（用户实际遇到）。
        if self.run is not None:
            self._persist_run()
        self._save_cfg()
        if self.cfg.get("fullscreen"):
            self.showFullScreen()
        else:
            self.showNormal()
        try:
            bs = self.screens["battle"]
            bs.STEP_MS = int(self.cfg.get("battle_step_ms", 400))
            bs._timer.setInterval(bs.STEP_MS)
        except Exception:
            pass
        self._back_to()

    def on_wipe_meta(self) -> None:
        ans = QMessageBox.question(
            self, "确认清空", "确实要清空全部元进度（成就/图鉴/排行）吗？此操作不可撤销。")
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            self.meta = run_mod.MetaProgress()
            self.meta.save()
            self.screens["menu"].meta = self.meta
        except Exception as exc:
            print(f"[qt.app] wipe meta failed: {exc!r}", flush=True)

    def on_wipe_save(self) -> None:
        ans = QMessageBox.question(
            self, "确认删除", "确实要删除当前战役存档吗？")
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            run_mod.save_run(None)
            self.run = None
            self.battle = None
        except Exception as exc:
            print(f"[qt.app] wipe save failed: {exc!r}", flush=True)

    # =================================================================
    # 无头验收辅助
    # =================================================================
    def headless_step(self, n: int = 1) -> None:
        """无头遍历用：推进 n 步当前战斗。"""
        bs = self.screens["battle"]
        for _ in range(max(1, n)):
            if self.battle is None or bs._ended:
                break
            bs.auto_play_step()

    def closeEvent(self, ev):  # noqa: N802
        try:
            self.screens["battle"].stop()
        except Exception:
            pass
        try:
            if self.run is not None and self.battle is None:
                run_mod.save_run(self.run)
            self.meta.save()
        except Exception:
            pass
        super().closeEvent(ev)


# =====================================================================
# 兼容别名（ARCHITECTURE §8 的 App.show 语义）
# =====================================================================


class MainWindow(GameWindow):
    """ARCHITECTURE §8 的 ``App`` 等价物。

    注意：**不要**重写 ``show()`` 来做界面路由。``QWidget.show()`` 被 Qt 内部
    大量调用，重写它会破坏布局激活流程（表现为所有页面塌缩在 100x30，
    手牌被裁切、按钮错位）。因此这里用独立方法名 :meth:`go`。
    """

    def go(self, screen_name: str = "menu", **kwargs) -> None:
        """ARCHITECTURE §8 ``App.show(name)`` 语义的等价入口。"""
        GameWindow.show_screen(self, screen_name)


def make_app(argv: Optional[List[str]] = None) -> QApplication:
    """创建 QApplication 并完成字体/样式初始化（可重复调用，已存在则复用）。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    try:
        from core import version as _V
        app.setApplicationName(_V.NAME_EN)
        app.setApplicationVersion(_V.VERSION)
        app.setApplicationDisplayName(T.tr(_V.title()))
    except Exception:
        app.setApplicationName("Steel Frontline")
    # i18n：给 QLabel/QPushButton 等的 setText 打翻译补丁。
    # 必须在任何界面构造**之前**安装，否则先建好的控件不会被翻译。
    try:
        T.install_i18n_patch()
    except Exception:
        pass
    T.init_fonts()
    app.setStyleSheet(T.stylesheet())
    return app
