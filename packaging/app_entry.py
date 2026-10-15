#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 Steel Frontline —— 打包版入口（自带 Python + Qt，零依赖）。

打包方式：PyInstaller ``--paths`` 让 core/ui/qt 作为**真正的模块**编入 PYZ。
因此这里**不能**再往 sys.path 里塞源码目录 —— 那些模块已可导入，
额外的路径操作反而会干扰导入器（曾导致 ``No module named '__future__'``）。

只有两样需要放到包外（可写）：
  * ``music/`` —— 用户自己加歌
  * ``data/``  —— 存档
"""

from __future__ import annotations


def _writable_home() -> str:
    """找一个可写目录放 music/ 与 data/。"""
    import os
    import sys

    env = os.environ.get("SF_GAME_HOME")
    if env:
        try:
            os.makedirs(env, exist_ok=True)
            return env
        except Exception:
            pass

    if getattr(sys, "frozen", False):
        exe = os.path.realpath(sys.executable)
        p = exe
        for _ in range(3):
            p = os.path.dirname(p)
        if p.endswith(".app"):
            p = os.path.dirname(p)

        if sys.platform.startswith("win"):
            # Windows：**不要**往 Program Files 里写 —— 普通用户没权限，
            # 会直接失败。用 %APPDATA%\钢铁战线（用户目录，一定可写）。
            appdata = (os.environ.get("APPDATA")
                       or os.path.expanduser("~"))
            cands = [os.path.join(appdata, "钢铁战线"),
                     os.path.join(os.path.expanduser("~"),
                                  "Documents", "钢铁战线"),
                     p]
        else:
            cands = [p, os.path.join(os.path.expanduser("~"),
                                     "Documents", "钢铁战线")]
        for cand in cands:
            try:
                os.makedirs(cand, exist_ok=True)
                probe = os.path.join(cand, ".wtest")
                with open(probe, "w") as f:
                    f.write("1")
                os.remove(probe)
                return cand
            except Exception:
                continue
    return os.getcwd()


def main() -> int:
    import os
    import sys
    import traceback

    home = _writable_home()

    # 音乐解析：
    #   1) 包外目录（用户可加歌）
    #   2) 包内自带（随包分发的默认 BGM）
    #   3) 两者合并：包外的优先，包内的补齐
    # 注意 .app 的 music/ 在 bundle 内是只读的，所以用户歌必须能覆盖。
    def _has_ogg(d: str) -> bool:
        try:
            return any(f.lower().endswith((".ogg", ".mp3", ".m4a", ".wav",
                                           ".aac", ".aiff", ".flac"))
                       for f in os.listdir(d))
        except Exception:
            return False

    outer = os.path.join(home, "music")
    try:
        os.makedirs(outer, exist_ok=True)
    except Exception:
        pass

    inner = None
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        cand = os.path.join(base, "music")
        if os.path.isdir(cand):
            inner = cand

    # 首次运行：把包内自带的歌复制到包外，用户就能直接增删
    if inner and _has_ogg(inner) and not _has_ogg(outer):
        try:
            import shutil
            for f in os.listdir(inner):
                low = f.lower()
                if low.endswith((".ogg", ".mp3", ".m4a", ".wav", ".aac",
                                 ".aiff", ".flac", ".txt")):
                    src = os.path.join(inner, f)
                    dst = os.path.join(outer, f)
                    if os.path.isfile(src) and not os.path.exists(dst):
                        shutil.copy2(src, dst)
        except Exception:
            pass

    if _has_ogg(outer):
        music = outer
    elif inner and os.path.isdir(inner):
        music = inner
    else:
        music = outer

    data = os.path.join(home, "data")
    try:
        os.makedirs(data, exist_ok=True)
    except Exception:
        data = home

    # 让引擎去外面读写
    try:
        import core.audio as _audio
        _audio.music_dir = lambda: music
    except Exception:
        pass
    try:
        import core.run as _run
        _run.DATA_DIR = data
        _run.SAVE_PATH = os.path.join(data, "save.json")
        _run.META_PATH = os.path.join(data, "meta.json")
    except Exception:
        pass

    def _report(text: str) -> None:
        """打包后无终端：出错要弹窗 + 落盘。"""
        try:
            with open(os.path.join(data, "crash.log"), "a",
                      encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass
        try:
            import subprocess
            safe = text.replace('"', "'").replace("\\", "/")[-600:]
            subprocess.run(
                ["osascript", "-e",
                 'display alert "钢铁战线 启动失败" message "%s" as critical'
                 % safe], timeout=12)
        except Exception:
            pass

    # --selftest：无窗口自检。
    # Windows 上用 --windowed 打包的 exe **没有控制台**，
    # 此时 sys.stdout 是 None —— print() 会直接抛异常，
    # 自检看起来"跑了一秒就退出"。所以这里分两步：
    #   1. 把结果写进文件（一定能拿到）
    #   2. 尽量往控制台打一份（有就用，没有就跳过）
    if "--selftest" in sys.argv:
        return _run_selftest()

    # 高画质版（PyQt6 已打进包内）
    try:
        from qt.main_qt import main as qt_main
        return int(qt_main([sys.argv[0]] + sys.argv[1:]) or 0)
    except Exception:
        _report("Qt 版启动失败：\n" + traceback.format_exc())

    # 兜底：Tkinter
    try:
        import main as tk_main
        return int(tk_main.main() or 0)
    except Exception:
        _report("Tkinter 版启动失败：\n" + traceback.format_exc())
    return 1


def _run_selftest() -> int:
    """跑 --selftest，并把结果同时写进文件与控制台。

    为什么需要这个函数：
      PyInstaller 的 --windowed 在 Windows 上不分配控制台，
      sys.stdout 可能是 None。直接 print 会抛
      "AttributeError: 'NoneType' object has no attribute 'write'"
      或 OSError，进程立刻以非 0 退出 —— CI 里就表现为
      "Run the exe selftest" 跑 1 秒就失败，且没有任何输出。

    所以：
      * 结果统一收集到 buf
      * 写进 <data>/selftest.log（一定成功）
      * 再尽力往 stdout 打（没有就忽略）
    """
    import io
    import os
    import sys
    import traceback

    buf = io.StringIO()

    def out(text: str = "") -> None:
        buf.write(text + "\n")

    code = 1
    try:
        out("== 钢铁战线 自检 ==")
        out("python: %s" % sys.version.split()[0])
        out("frozen: %s" % getattr(sys, "frozen", False))
        out("argv: %r" % (sys.argv,))
        out("stdout is None: %s" % (sys.stdout is None))

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from qt.main_qt import main as qt_main
        code = int(qt_main([sys.argv[0], "--selftest"]) or 0)
        out("qt_main 返回: %d" % code)
    except BaseException:
        out("自检抛异常：")
        out(traceback.format_exc())
        code = 1

    text = buf.getvalue()

    # 1) 写文件（最可靠）
    try:
        d = os.environ.get("SF_GAME_HOME")
        if not d:
            base = os.path.dirname(os.path.abspath(sys.executable))
            d = os.path.join(base, "data")
        os.makedirs(d, exist_ok=True)
        lp = os.path.join(d, "selftest.log")
        with open(lp, "w", encoding="utf-8") as f:
            f.write(text)
        print_path = lp
    except Exception:
        print_path = "(写日志失败)"

    # 2) 尽力打到控制台
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.write(text)
            stream.write("\n[selftest] exit code = %d\n" % code)
            stream.flush()
        except Exception:
            pass

    # 3) 完全没有控制台时，把日志路径也追加到文件末尾
    if print_path != "(写日志失败)":
        try:
            with open(print_path, "a", encoding="utf-8") as f:
                f.write("\n[selftest] exit code = %d\n" % code)
        except Exception:
            pass

    return code


if __name__ == "__main__":
    import sys
    sys.exit(main())
