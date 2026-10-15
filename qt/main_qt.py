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


def _force_utf8_stdout() -> None:
    """把 stdout/stderr 切到 UTF-8。

    Windows 上 Python 默认用 cp1252 输出，一 print 中文就抛
    UnicodeEncodeError（打包成 exe 后自检直接崩，且看不到任何输出）。
    这里显式 reconfigure，不依赖外部环境变量。
    """
    for name in ("stdout", "stderr"):
        st = getattr(sys, name, None)
        if st is None:
            continue
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8_stdout()


def _title() -> str:
    """窗口标题（Windows 版自动带 Windows Rework 后缀）。"""
    try:
        from core import version as _V
        return _V.title()
    except Exception:
        return "钢铁战线 Steel Frontline"



def _print_missing_pyqt6() -> None:
    """没装 PyQt6 时的友好提示（中英双语，含各平台命令）。"""
    import sys as _s
    line = "=" * 62
    print(line)
    print("  钢铁战线 · 缺少 PyQt6  /  Steel Frontline — PyQt6 missing")
    print(line)
    print()
    print("  这个版本需要 PyQt6 才能运行。")
    print("  This edition requires PyQt6 to run.")
    print()
    print("  请安装 / Please install:")
    print()
    print("      python -m pip install PyQt6")
    print()
    if _s.platform.startswith("win"):
        print("  Windows 提示 / Windows note:")
        print("      如果提示找不到 python，试试 py -m pip install PyQt6")
        print("      If 'python' is not found, try: py -m pip install PyQt6")
        print()
        print("      也可以直接下载打包版（自带 Python + Qt）：")
        print("      Or just download the packaged build (bundles Python + Qt):")
        print("      https://github.com/d5gkmk96kj-lab/steel-frontline/releases")
    elif _s.platform == "darwin":
        print("  macOS 提示 / macOS note:")
        print("      如果提示权限不足，加 --user：")
        print("      If you get a permission error, add --user:")
        print("          python3 -m pip install --user PyQt6")
    else:
        print("  Linux 提示 / Linux note:")
        print("      可能需要先装系统依赖：")
        print("      You may need system packages first:")
        print("          sudo apt install python3-pyqt6")
    print()
    print("  不想装？用零依赖的经典版 / No install? Use the classic build:")
    print("      python main.py")
    print()
    print(line)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = [a for a in argv[1:]]

    # 无头模式必须在导入 QtWidgets 之前设置
    headless = "--selftest" in args or "--headless" in args
    if headless and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    # PyQt6 缺失时给一条**看得懂**的提示（中英双语）。
    # 不能让它直接抛 ModuleNotFoundError，玩家会一脸懵。
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        _print_missing_pyqt6()
        return 2

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
    win.setWindowTitle(_title())

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
