"""钢铁战线 Steel Frontline — PyQt6 版入口。

用法：
    python3 qt/main_qt.py                # 正常启动
    python3 qt/main_qt.py --seed 42      # 指定种子直接开局
    python3 qt/main_qt.py --selftest     # 无头自检后退出（不打开窗口）
    python3 qt/main_qt.py --fullscreen

与 Tkinter 版（main.py）并存，共享同一套 core/ 引擎。
"""

from __future__ import annotations

import os
import sys

# 允许 `python3 qt/main_qt.py` 直接运行：把项目根加入 sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = [a for a in argv[1:]]

    # 无头模式必须在导入 QtWidgets 之前设置
    headless = "--selftest" in args or "--headless" in args
    if headless and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from qt.qapp import make_app, MainWindow

    app = make_app([argv[0]])

    seed = None
    if "--seed" in args:
        try:
            seed = int(args[args.index("--seed") + 1])
        except (IndexError, ValueError):
            seed = None
    asc = 0
    if "--ascension" in args:
        try:
            asc = int(args[args.index("--ascension") + 1])
        except (IndexError, ValueError):
            asc = 0

    win = MainWindow()
    win.setWindowTitle("钢铁战线 Steel Frontline")

    if headless or "--selftest" in args:
        # 自检：切遍所有界面 + 打完一场战斗，全部无异常
        ok = _selftest(win, app)
        return 0 if ok else 1

    win.show()
    if seed is not None or "--new" in args:
        win.start_new_run(asc, seed)

    return app.exec()


def _selftest(win, app) -> bool:
    """无窗口自检：所有界面可切换、战斗可打完。"""
    from qt.qapp import SCREENS

    print("== 钢铁战线 PyQt6 自检 ==", flush=True)
    fails = []

    # 1) 全部界面可切换
    for name in SCREENS:
        try:
            win.show_screen(name)
            app.processEvents()
        except Exception as exc:
            fails.append(f"screen {name}: {exc!r}")
    print(f"界面切换: {len(SCREENS)} 个", flush=True)

    # 2) 开局 + 打完一场战斗
    try:
        win.start_new_run(0, 42)
        app.processEvents()
        assert win.run is not None, "run is None"
        enc = win.run.roll_encounter("normal")
        win.start_battle(enc)
        app.processEvents()
        bs = win.screens["battle"]
        guard = 0
        while win.battle is not None and not bs._ended and guard < 600:
            bs.auto_play_step()
            guard += 1
        app.processEvents()
        res = bs.battle.result() if bs.battle else "?"
        print(f"战斗结束: result={res} steps={guard} turn={bs.battle.turn}", flush=True)
    except Exception as exc:
        import traceback
        fails.append(f"battle: {exc!r}")
        traceback.print_exc()

    # 3) 界面仍可切换（战斗后）
    for name in ("menu", "map", "codex", "achievements", "settings", "stats"):
        try:
            win.show_screen(name)
            app.processEvents()
        except Exception as exc:
            fails.append(f"post screen {name}: {exc!r}")

    if fails:
        print("\n自检失败:", flush=True)
        for f in fails:
            print("  -", f, flush=True)
        return False
    print("自检通过：全部界面正常，战斗可完成。", flush=True)
    return True


if __name__ == "__main__":
    sys.exit(main())
