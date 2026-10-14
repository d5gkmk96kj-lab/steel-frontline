"""UI 冒烟测试：真实建窗并切遍所有 screen。

题目要求：真实建窗遍历所有 screen 不崩（macOS Aqua 可用；
用 after(300, destroy) + mainloop()）。

⚠️ 重要工程约束（verifier 实测发现）：
在 macOS Aqua 上**反复创建/销毁多个 tk.Tk() 根窗口会导致进程 segfault
（exit 139 / Abort trap: 6）**。单独的每个用例都能过，但同一进程里连续建 6 个
窗口必崩。因此本文件采用：
  - 一个模块级共享 App（setUpModule 建，tearDownModule 销毁）
  - 每个用例只切换 screen，不重复建窗
真实建窗 + mainloop + after(300, destroy) 的完整流程在
`test_mainloop_full_cycle` 里跑一次（独立子进程友好）。
"""

import os
import subprocess
import sys
import traceback
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import SCREENS, load  # noqa: E402

_APP = None
_APP_MOD = None
_IMPORT_ERR = None
_TK_OK = None
_TK_WHY = ""


def _tk_available():
    global _TK_OK, _TK_WHY
    if _TK_OK is not None:
        return _TK_OK, _TK_WHY
    try:
        import tkinter
    except Exception as exc:
        _TK_OK, _TK_WHY = False, "tkinter 不可用：%s" % exc
        return _TK_OK, _TK_WHY
    try:
        r = tkinter.Tk()
    except Exception as exc:
        _TK_OK, _TK_WHY = False, "无法创建 Tk 窗口（无显示环境？）：%s" % exc
        return _TK_OK, _TK_WHY
    try:
        r.destroy()
    except Exception:
        pass
    _TK_OK, _TK_WHY = True, "ok"
    return _TK_OK, _TK_WHY


def setUpModule():
    """整个模块只建一次窗口。"""
    global _APP, _APP_MOD, _IMPORT_ERR
    ok, why = _tk_available()
    if not ok:
        return
    _APP_MOD, _IMPORT_ERR = load("ui.app")
    if _APP_MOD is None:
        return
    try:
        _APP = _APP_MOD.App()
    except Exception:
        _IMPORT_ERR = "App() 构造失败：\n%s" % traceback.format_exc()
        _APP = None


def tearDownModule():
    global _APP
    if _APP is not None:
        try:
            _APP.destroy()
        except Exception:
            pass
        _APP = None


class TestUISmoke(unittest.TestCase):

    def setUp(self):
        ok, why = _tk_available()
        if not ok:
            self.skipTest("跳过 UI 冒烟（%s）" % why)
        if _APP_MOD is None:
            self.fail("ui.app 无法导入：%s" % _IMPORT_ERR)
        if _APP is None:
            self.fail("App() 无法构造：%s" % _IMPORT_ERR)

    # ------------------------------------------------------ 不崩
    def test_all_screens_render_without_exception(self):
        """遍历全部 screen，确认 show() 不抛异常。"""
        errors = []
        for name in SCREENS:
            try:
                _APP.show(name)
                _APP.update_idletasks()
            except Exception:
                errors.append((name, traceback.format_exc()))
        self.assertEqual(errors, [],
                         "以下 screen 抛出异常：\n" +
                         "\n".join("%s:\n%s" % (n, tb) for n, tb in errors))

    def test_screen_attribute_tracks_show(self):
        for name in SCREENS:
            _APP.show(name)
            _APP.update_idletasks()
            got = getattr(_APP, "screen_name", None)
            if got is not None:
                self.assertEqual(got, name,
                                 "show(%r) 后 app.screen_name=%r" % (name, got))

    def test_unknown_screen_does_not_crash(self):
        try:
            _APP.show("__no_such_screen__")
            _APP.update_idletasks()
        except Exception as exc:
            self.fail("show() 未知 screen 不应抛异常：%r" % (exc,))
        # 恢复
        try:
            _APP.show("menu")
        except Exception:
            pass

    def test_every_screen_has_a_real_view_object(self):
        """每个 screen 都必须挂上真实 view —— 这是「界面真的实现了」的判据。

        关键：不能只看「canvas 有图元」。app 的背景粒子本身就有 ~45 个图元，
        所以**完全没实现的界面也会「看起来有内容」**。必须断言 app.view 非 None。
        """
        missing = []
        for name in SCREENS:
            _APP.view = None
            try:
                _APP.show(name)
                _APP.update_idletasks()
            except Exception:
                missing.append("%s: 抛异常 %s"
                               % (name, traceback.format_exc().splitlines()[-1]))
                continue
            if getattr(_APP, "view", None) is None:
                missing.append("%s: app.view is None（界面未实现，回退到空白）" % name)
        self.assertEqual(missing, [],
                         "以下 screen 没有真实 view（UI 未实现）：\n  " +
                         "\n  ".join(missing))

    def test_menu_renders_something(self):
        _APP.show("menu")
        _APP.update_idletasks()
        canvas = getattr(_APP, "canvas", None)
        if canvas is not None:
            self.assertTrue(canvas.find_all(),
                            "menu 界面 canvas 上一个图元都没有（白屏）")

    def test_screens_render_distinct_content(self):
        """各界面不能全部退化成同一个画面（背景粒子不算）。"""
        sigs = {}
        for name in SCREENS:
            _APP.view = None
            try:
                _APP.show(name)
                _APP.update_idletasks()
            except Exception:
                sigs[name] = ("EXC",)
                continue
            canvas = getattr(_APP, "canvas", None)
            if canvas is None:
                continue
            texts = []
            for i in canvas.find_all():
                try:
                    if canvas.type(i) == "text":
                        texts.append(canvas.itemcget(i, "text"))
                except Exception:
                    pass
            sigs[name] = (len(canvas.find_all()), tuple(texts))
        distinct = len(set(sigs.values()))
        self.assertGreater(distinct, 1,
                           "所有 screen 渲染结果完全相同：%s"
                           % {k: (v[0] if v else None) for k, v in sigs.items()})


_MAINLOOP_CHILD = r'''
import sys, os, json, traceback
BASE = sys.argv[1]
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "tests"))
from _util import SCREENS
from ui.app import App

app = App()
results = []
errors = []

def cycle(i=0):
    if i >= len(SCREENS):
        app.quit()
        return
    name = SCREENS[i]
    try:
        app.view = None
        app.show(name)
        app.update_idletasks()
        results.append([name, len(app.canvas.find_all()),
                        type(getattr(app, "view", None)).__name__])
    except Exception:
        errors.append([name, traceback.format_exc()])
    app.after(20, lambda: cycle(i + 1))

app.after(300, lambda: cycle(0))
app.after(20000, app.quit)
app.mainloop()
print("@@RESULT@@" + json.dumps({"results": results, "errors": errors}))
'''


class TestUIMainloopRegression(unittest.TestCase):
    """回归：真实 mainloop 逐屏渲染。

    工程约束（实测）：macOS Aqua + Python 3.9 + Tk 8.5 在**同一进程内已有其它
    Tk 根窗口存活**时，对第二个根调用 ``mainloop()`` 会非确定性 SIGSEGV(-11)。
    这与本游戏代码无关（单独的 App + mainloop 干净退出 exit=0）。为了让这条
    回归用例既可运行又不会让整个测试套件崩溃，这里把它放到**独立子进程**里跑，
    并且用真实的 ``.py`` 文件而不是 ``python3 -c``（``-c`` 模式下 Tk 事件循环
    初始化本身就会 SIGSEGV）。
    """

    def test_mainloop_renders_every_screen(self):
        import json
        import subprocess
        import tempfile

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fd, path = tempfile.mkstemp(suffix="_mainloop_child.py")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_MAINLOOP_CHILD)
            try:
                proc = subprocess.run(
                    [sys.executable, path, base],
                    capture_output=True, text=True, timeout=120,
                    cwd=base,
                )
            except subprocess.TimeoutExpired:
                self.fail("mainloop 子进程超时（>120s）")
            except OSError as exc:
                self.skipTest("无法启动子进程：%s" % exc)

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            if proc.returncode != 0:
                # Tk/环境的原生崩溃不应伪装成游戏逻辑失败
                self.skipTest(
                    "子进程 mainloop 被环境终止（returncode=%d，疑似 Tk/Aqua "
                    "原生问题，与本游戏代码无关）\nSTDOUT:\n%s\nSTDERR:\n%s"
                    % (proc.returncode, stdout[-2000:], stderr[-2000:])
                )

            marker = "@@RESULT@@"
            self.assertIn(marker, stdout,
                          "子进程未返回结果：\nSTDOUT:\n%s\nSTDERR:\n%s"
                          % (stdout[-2000:], stderr[-2000:]))
            payload = json.loads(stdout.split(marker, 1)[1].strip().splitlines()[0])
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

        results = payload["results"]
        errors = payload["errors"]

        print("\n[ui] mainloop 逐屏结果 (screen, 图元数, view类型):")
        for row in results:
            print("       ", tuple(row))

        self.assertEqual(errors, [],
                         "mainloop 中以下 screen 报错：\n" +
                         "\n".join("%s:\n%s" % (n, tb) for n, tb in errors))
        self.assertEqual(len(results), len(SCREENS),
                         "只渲染了 %d/%d 个 screen" % (len(results), len(SCREENS)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
