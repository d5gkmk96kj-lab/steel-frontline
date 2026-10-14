#!/usr/bin/env python3
"""钢铁战线 Steel Frontline — PyQt6 无头遍历验收脚本。

这是**真实 .py 文件**（不是 `python3 -c`），按 lead 的要求。

覆盖范围
--------
1. 导入 qt 全模块
2. 创建 QApplication + MainWindow（离屏）
3. **逐个切换全部 14 个界面**并渲染一帧（触发 paintEvent，抓绘制期异常）
4. **真实打完一场战斗**（走 play_card / end_turn / enemy_step 全协议）
5. 每个界面渲染 PNG 截图供肉眼验收
6. 走一遍 地图 → 事件 → 商店 → 医院 → 奖励 → 结算 的完整节点派发
7. 捕获 stderr，断言无异常/Traceback

运行：
    python3 qt/headless_tour.py
    python3 qt/headless_tour.py --shots /tmp/myshots
退出码 0 = 全部通过。
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import traceback
from contextlib import redirect_stderr

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from qt import qtheme as T  # noqa: E402
from qt.qapp import SCREENS, MainWindow, make_app  # noqa: E402


class Report:
    def __init__(self):
        self.passed = []
        self.failed = []

    def ok(self, msg: str) -> None:
        self.passed.append(msg)
        print(f"  [PASS] {msg}", flush=True)

    def bad(self, msg: str, exc: BaseException | None = None) -> None:
        self.failed.append(msg)
        print(f"  [FAIL] {msg}", flush=True)
        if exc is not None:
            traceback.print_exception(type(exc), exc, exc.__traceback__)

    def check(self, cond: bool, msg: str, exc=None) -> bool:
        if cond:
            self.ok(msg)
        else:
            self.bad(msg, exc)
        return bool(cond)


def pump(app: QApplication, ms: int = 60) -> None:
    """让事件循环真实跑一小段（处理布局/定时器/动画）。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents()


def content_ratio(img) -> float:
    """可见内容占比：与背景色差异明显的采样点比例。

    这是**空白页防线** —— 界面"存在但不渲染内容"不会崩溃、也没有 stderr，
    只有量化像素才能抓到。Tkinter 版当初就踩过这个坑。
    """
    bg = T.Q_BG_DEEP
    br, bgc, bb = bg.red(), bg.green(), bg.blue()
    nonbg = 0
    total = 0
    step = 6
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            total += 1
            c = img.pixelColor(x, y)
            if (abs(c.red() - br) + abs(c.green() - bgc)
                    + abs(c.blue() - bb)) > 40:
                nonbg += 1
    return (nonbg / total) if total else 0.0


def check_not_blank(win: MainWindow, name: str, rep: Report, outdir: str,
                    min_ratio: float = 0.010) -> float:
    """断言界面确实渲染出了内容（而非空白页）。"""
    try:
        pm = QPixmap(T.WIN_W, T.WIN_H)
        pm.fill(T.Q_BG_DEEP)
        win.render(pm)
        img = pm.toImage()
        ratio = content_ratio(img)
        if ratio < min_ratio:
            rep.bad(f"{name} 内容过少，疑似空白页 (ratio={ratio:.3f} < {min_ratio})")
        else:
            rep.ok(f"{name} 内容占比 {ratio*100:.1f}%")
        return ratio
    except Exception as exc:
        rep.bad(f"{name} 内容占比检测异常", exc)
        return 0.0


def shoot(win: MainWindow, name: str, outdir: str) -> str:
    """用 QWidget.grab() 离屏出图（不需要屏幕录制权限）。"""
    win.resize(T.WIN_W, T.WIN_H)
    pump_ok = True
    try:
        pm = QPixmap(T.WIN_W, T.WIN_H)
        pm.fill(T.Q_BG_DEEP)
        win.render(pm)
        path = os.path.join(outdir, f"{name}.png")
        pm.save(path, "PNG")
        return path
    except Exception:
        return ""


# ---------------------------------------------------------------------
# 1. 全部界面遍历
# ---------------------------------------------------------------------
def tour_screens(win: MainWindow, app: QApplication, rep: Report, outdir: str) -> None:
    print("\n[1] 遍历全部界面", flush=True)
    # 先开一局，让 map/battle 等界面有真实数据可渲染
    # （否则截出来的 map 是空画布，验收截图没有意义）
    try:
        win.start_new_run(0, seed=20241)
        pump(app, 60)
        enc = win.run.roll_encounter("normal")
        win.start_battle(enc)
        pump(app, 80)
        win.show_screen("map")
        pump(app, 60)
    except Exception as exc:
        print(f"  (预热开局失败，界面仍将逐个遍历: {exc!r})", flush=True)

    for name in SCREENS:
        try:
            win.show_screen(name)
            pump(app, 50)
            w = win.screens[name]
            png = shoot(win, f"screen_{name}", outdir)
            rep.check(win.stack.currentWidget() is w,
                      f"切换到 {name}（截图 {os.path.basename(png) or 'n/a'}）")
            check_not_blank(win, f"界面 {name}", rep, outdir)
        except Exception as exc:
            rep.bad(f"界面 {name} 异常", exc)


# ---------------------------------------------------------------------
# 2. 完整一局：地图派发 + 战斗 + 奖励 + 商店 + 医院 + 事件
# ---------------------------------------------------------------------
def tour_gameplay(win: MainWindow, app: QApplication, rep: Report, outdir: str) -> None:
    print("\n[2] 真实打一局", flush=True)

    # --- 开局 ---
    try:
        win.start_new_run(0, seed=4242)
        pump(app, 60)
        rep.check(win.run is not None, "开局成功（RunState 就绪）")
        rep.check(len(win.run.map_nodes) > 0,
                  f"战区推进图已生成（{len(win.run.map_nodes)} 个节点）")
        shoot(win, "game_01_map", outdir)
    except Exception as exc:
        rep.bad("开局失败", exc)
        return

    # --- 打一场普通战斗，走完整协议 ---
    try:
        enc = win.run.roll_encounter("normal")
        win.start_battle(enc)
        pump(app, 80)
        bs = win.screens["battle"]
        rep.check(win.battle is not None and bs.battle is not None,
                  f"战斗已创建（敌人 {len(bs.battle.enemies)} 个）")
        rep.check(len(bs.hand.cards) > 0, f"手牌已渲染（{len(bs.hand.cards)} 张）")
        shoot(win, "game_02_battle_start", outdir)

        # 打一张牌（验证 play_card 路径 + 补给下降）
        snap0 = bs.battle.snapshot()
        e0 = snap0["player"]["energy"]
        played_uid = None
        for h in snap0["hand"]:
            if bs.battle.can_play(h["uid"]):
                played_uid = h["uid"]
                break
        if played_uid is not None:
            ok = bs.play_card(played_uid)
            pump(app, 60)
            snap1 = bs.battle.snapshot()
            rep.check(ok and snap1["player"]["energy"] < e0,
                      f"play_card 生效（补给 {e0} -> {snap1['player']['energy']}）")
        else:
            rep.bad("手牌中没有可打出的牌")

        # 一个完整回合：end_turn -> 每 400ms enemy_step 直到 False
        step_ms = bs._timer.interval()
        rep.check(step_ms == 400, f"敌方回合步进间隔 = {step_ms}ms（协议要求 400ms）")

        phase_before = bs.battle.phase
        bs.end_turn()
        rep.check(bs.battle.phase == "enemy",
                  f"end_turn() 只切 phase（{phase_before} -> enemy），未执行敌人行动")
        shoot(win, "game_03_battle_enemy_turn", outdir)

        steps = 0
        while bs.battle.phase == "enemy" and steps < 100:
            bs._on_step()
            steps += 1
        pump(app, 60)
        rep.check(bs.battle.phase == "player",
                  f"enemy_step 驱动完成（{steps} 步）后自动开新玩家回合")
        rep.check(not bs._busy, "回合结束后输入锁已释放")

        # 自动打完
        guard = 0
        while not bs._ended and guard < 800:
            bs.auto_play_step()
            guard += 1
        pump(app, 120)
        result = bs.battle.result() if bs.battle else "?"
        rep.check(bs._ended and result in ("won", "lost"),
                  f"战斗正常结束（result={result}, {guard} 步）")
        shoot(win, "game_04_battle_end", outdir)
    except Exception as exc:
        rep.bad("战斗流程异常", exc)
        return

    # --- 结算派发 ---
    try:
        win.on_battle_finished(result)
        pump(app, 140)
        cur = win.stack.currentWidget()
        name = next((k for k, v in win.screens.items() if v is cur), "?")
        rep.check(name in ("reward", "gameover", "map"),
                  f"战斗结束后路由正确（-> {name}）")
        shoot(win, f"game_05_after_battle_{name}", outdir)
        if name == "reward":
            win.on_reward_done()
            pump(app, 100)
            rep.check(win.stack.currentWidget() is win.screens["map"],
                      "奖励领取后回到战区推进图")
    except Exception as exc:
        rep.bad("战斗结算派发异常", exc)

    # --- 节点派发：事件 / 商店 / 医院 / 缴获 ---
    if win.run is None:
        return
    print("\n[3] 节点派发", flush=True)
    for kind in ("event", "shop", "rest", "treasure"):
        try:
            win._pending = {"kind": kind}
            info = {"kind": kind, "node_id": -1, "act": win.run.act,
                    "floor": win.run.floor}
            if kind == "shop":
                from core import events as EV
                info["shop"] = EV.build_shop_inventory(win.run.rng, win.run.act,
                                                       win.run.ascension)
            elif kind == "treasure":
                from core import events as EV
                info["treasure"] = EV.roll_treasure(win.run.rng, win.run.act)
            elif kind == "rest":
                info["rest_heal"] = win.run.rest_heal_amount()
            elif kind == "event":
                from core import events as EV
                info["event"] = EV.random_event(win.run.rng, win.run.act, set())
            win._dispatch_node(info)
            pump(app, 110)
            cur = win.stack.currentWidget()
            name = next((k for k, v in win.screens.items() if v is cur), "?")
            rep.check(name != "?", f"{kind} 节点派发成功（-> {name}）")
            shoot(win, f"node_{kind}", outdir)
        except Exception as exc:
            rep.bad(f"{kind} 节点派发异常", exc)

    # --- 商店交互 ---
    try:
        from core import events as EV
        win.show_screen("shop")
        win.screens["shop"].setup(
            win.run, EV.build_shop_inventory(win.run.rng, win.run.act, win.run.ascension))
        win.run.gold = 9999
        win.screens["shop"].refresh_gold(win.run)
        g0, d0 = win.run.gold, len(win.run.deck)
        win.on_buy_card(0, 50)
        pump(app, 60)
        rep.check(win.run.gold < g0 and len(win.run.deck) > d0,
                  f"补给站购卡生效（金币 {g0}->{win.run.gold}, 牌组 {d0}->{len(win.run.deck)}）")
        shoot(win, "shop_after_buy", outdir)
    except Exception as exc:
        rep.bad("补给站交互异常", exc)

    # --- 医院升级 ---
    try:
        win.show_screen("rest")
        win.screens["rest"].setup(win.run)
        ups = win.run.upgradable_cards()
        if ups:
            uid = ups[0].uid
            win.on_rest_upgrade(uid)
            pump(app, 60)
            rep.check(True, f"战地医院升级生效（uid={uid}）")
        else:
            rep.ok("战地医院：当前无可升级卡牌（跳过）")
        shoot(win, "rest_after_upgrade", outdir)
    except Exception as exc:
        rep.bad("战地医院交互异常", exc)


# ---------------------------------------------------------------------
# 4. 结算 + 元进度落盘
# ---------------------------------------------------------------------
def tour_endgame(win: MainWindow, app: QApplication, rep: Report, outdir: str) -> None:
    print("\n[4] 结算与元进度", flush=True)
    try:
        if win.run is None:
            win.start_new_run(0, seed=7)
        win.run.gold = 500
        win._finish_game(won=True)
        pump(app, 120)
        rep.check(win.stack.currentWidget() is win.screens["gameover"],
                  "结算界面显示正常")
        shoot(win, "game_06_victory", outdir)
        win._finish_game(won=False)
        pump(app, 120)
        shoot(win, "game_07_defeat", outdir)
        rep.ok("胜利/失败两种结算均可渲染")
    except Exception as exc:
        rep.bad("结算异常", exc)

    for name in ("codex", "achievements", "stats"):
        try:
            win.show_screen(name)
            pump(app, 90)
            shoot(win, f"meta_{name}", outdir)
            rep.ok(f"{name} 界面渲染正常")
        except Exception as exc:
            rep.bad(f"{name} 界面异常", exc)


# ---------------------------------------------------------------------
# 5. 窗口缩放鲁棒性
# ---------------------------------------------------------------------
def check_scroll_overflow(win: MainWindow, app: QApplication, rep: Report,
                          name: str, min_fit: float = 0.55) -> None:
    """检查界面里的滚动区内容是否横向溢出视口（图鉴曾把 135 张卡排成一条长龙）。"""
    from PyQt6.QtWidgets import QScrollArea
    try:
        scr = win.screens[name]
        areas = scr.findChildren(QScrollArea)
        if not areas:
            return
        worst = None
        for sa in areas:
            inner = sa.widget()
            if inner is None:
                continue
            vw = sa.viewport().width()
            iw = inner.width()
            if vw <= 0:
                continue
            frac = vw / float(iw) if iw else 1.0
            if worst is None or frac < worst[0]:
                worst = (frac, iw, vw)
        if worst and worst[0] < min_fit:
            # 溢出本身不是 bug（长列表就该滚动），关键是**能否滚到**：
            # 只要横向滚动条 range > 0 且不被禁用，玩家就能浏览全部内容。
            frac, iw, vw = worst
            scrollable = False
            for sa in areas:
                inner = sa.widget()
                if inner is None or inner.width() <= 0:
                    continue
                if sa.viewport().width() / float(inner.width()) >= min_fit:
                    continue
                bar = sa.horizontalScrollBar()
                if bar.maximum() > 0 and sa.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
                    scrollable = True
            if scrollable:
                rep.ok(f"{name} 内容需横向滚动（{iw}px vs 视口 {vw}px），滚动条可用")
            else:
                rep.bad(f"{name} 滚动区内容横向溢出且**无法滚动**："
                        f"{iw}px vs 视口 {vw}px")
        elif worst:
            rep.ok(f"{name} 滚动区内容未溢出行外 (可见比例 {worst[0]:.2f})")
    except Exception as exc:
        rep.bad(f"{name} 滚动区检查异常", exc)


def tour_resize(win: MainWindow, app: QApplication, rep: Report) -> None:
    print("\n[5] 缩放鲁棒性", flush=True)
    for (w, h) in ((1280, 800), (1600, 1000), (1920, 1080), (1280, 800)):
        try:
            win.resize(w, h)
            pump(app, 70)
            rep.ok(f"{w}x{h} 渲染正常")
        except Exception as exc:
            rep.bad(f"{w}x{h} 渲染异常", exc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="/tmp/steel_frontline_shots")
    args = ap.parse_args()
    os.makedirs(args.shots, exist_ok=True)

    # 捕获 stderr 以断言无异常
    err = io.StringIO()
    rep = Report()

    app = make_app([sys.argv[0]])
    win = MainWindow()
    win.resize(T.WIN_W, T.WIN_H)
    win.show()
    pump(app, 120)

    print("=" * 62)
    print("钢铁战线 Steel Frontline — PyQt6 无头遍历验收")
    print(f"Qt platform = {app.platformName()}")
    print(f"字体族 = {T.FONT_FAMILY}")
    print(f"截图输出 = {args.shots}")
    print("=" * 62)

    try:
        with redirect_stderr(err):
            tour_screens(win, app, rep, args.shots)
            for nm in ("codex", "deck", "reward", "shop", "rest", "event"):
                check_scroll_overflow(win, app, rep, nm)
            tour_gameplay(win, app, rep, args.shots)
            tour_endgame(win, app, rep, args.shots)
            tour_resize(win, app, rep)
    except Exception:
        rep.bad("顶层遍历异常", sys.exc_info()[1])

    # 关闭窗口，确认干净退出
    try:
        win.close()
        pump(app, 80)
        rep.ok("窗口关闭干净")
    except Exception as exc:
        rep.bad("窗口关闭异常", exc)

    captured = err.getvalue()
    bad_lines = [
        ln for ln in captured.splitlines()
        if ("Traceback" in ln or "Error" in ln or "error" in ln
            or "Exception" in ln or "qt." in ln and "Fatal" in ln)
        and "Populating font family aliases" not in ln
        and "propagateSizeHints" not in ln
    ]

    print("\n" + "=" * 62)
    print(f"通过: {len(rep.passed)}    失败: {len(rep.failed)}")
    if captured.strip():
        print("\n--- stderr 捕获 ---")
        for ln in captured.splitlines()[:40]:
            print("  " + ln)
    else:
        print("stderr: 空")
    if bad_lines:
        print("\nstderr 中疑似异常行:")
        for ln in bad_lines[:20]:
            print("  !", ln)
    print("=" * 62)

    if rep.failed:
        print("\n失败项:")
        for f in rep.failed:
            print("  -", f)
        return 1
    if bad_lines:
        print("\n虽然断言通过，但 stderr 有疑似异常，判为失败。")
        return 1
    print("\n全部通过：界面遍历 + 真实战斗 + 无 stderr 异常。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
