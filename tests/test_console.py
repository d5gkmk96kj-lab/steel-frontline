# -*- coding: utf-8 -*-
"""全局控制台（F1）测试。

覆盖两版共用的行为契约：
* F1 打开/关闭、Esc 关闭
* 内建指令（help/list/status/heal/gold/hp/energy/block/kill/give/clear/close）
* 兑换码在控制台里可用
* 非法输入不崩
"""

import io
import os
import contextlib
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "tests"))


def _tk_ok():
    try:
        import tkinter
        r = tkinter.Tk()
        r.destroy()
        return True
    except Exception:
        return False


class _FakeEvent:
    def __init__(self, keysym="", char=""):
        self.keysym = keysym
        self.char = char


@unittest.skipUnless(_tk_ok(), "无 Tk 显示环境")
class TestConsoleTk(unittest.TestCase):
    """Tkinter 版控制台。"""

    @classmethod
    def setUpClass(cls):
        import ui.app as A
        cls.A = A
        cls.app = A.App()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def setUp(self):
        # 重新开始一局，隔离用例
        self.app.start_new_run(seed=13)
        self.con = self.app.console
        self.con.close()
        self.con.lines = []

    def tearDown(self):
        self.con.close()

    # -- 开关 ---------------------------------------------------------- #
    def test_console_exists_and_starts_closed(self):
        self.assertTrue(hasattr(self.app, "console"))
        self.assertFalse(self.con.open)

    def test_f1_toggles_open_and_closed(self):
        self.app._on_f1()
        self.assertTrue(self.con.open, "F1 应打开控制台")
        self.app._on_f1()
        self.assertFalse(self.con.open, "再按 F1 应关闭")

    def test_escape_closes_console(self):
        self.app._on_f1()
        self.assertTrue(self.con.open)
        self.con.on_key(_FakeEvent("Escape"))
        self.assertFalse(self.con.open, "Esc 应关闭控制台")

    def test_escape_closes_console_before_leaving_screen(self):
        """控制台打开时 Esc 只关控制台，不应切界面。"""
        self.app.show("settings")
        self.app._on_f1()
        before = self.app.screen_name
        self.app._on_escape()
        self.assertFalse(self.con.open)
        self.assertEqual(self.app.screen_name, before, "不应同时切换界面")

    # -- 输入 ---------------------------------------------------------- #
    def test_typing_accumulates_and_backspace(self):
        self.app._on_f1()
        for ch in "gold":
            self.con.on_key(_FakeEvent("", ch))
        self.assertEqual(self.con.buf, "gold")
        self.con.on_key(_FakeEvent("BackSpace"))
        self.assertEqual(self.con.buf, "gol")

    def test_enter_submits_and_clears_buffer(self):
        self.app._on_f1()
        self.con.buf = "status"
        self.con.on_key(_FakeEvent("Return"))
        self.assertEqual(self.con.buf, "", "提交后输入应清空")
        self.assertTrue(self.con.open, "执行后控制台应保持打开")

    # -- 内建指令 ------------------------------------------------------ #
    def _run(self, cmd):
        self.con.buf = cmd
        self.con.submit()
        return self.con.lines[-1][0] if self.con.lines else ""

    def test_help_lists_commands(self):
        self._run("help")
        joined = " ".join(t for t, _ in self.con.lines)
        for cmd in ("help", "list", "give", "heal", "gold", "status"):
            self.assertIn(cmd, joined, "help 应列出 %s" % cmd)

    def test_list_shows_codes(self):
        self._run("list")
        joined = " ".join(t for t, _ in self.con.lines)
        self.assertIn("manpower", joined)
        self.assertIn("god_mode", joined)

    def test_status_reports_state(self):
        out = self._run("status")
        self.assertTrue("战役" in out or "战斗" in out or "菜单" in out)

    def test_seed_command(self):
        out = self._run("seed")
        self.assertIn("13", out)

    def test_gold_command(self):
        self._run("gold 777")
        self.assertEqual(self.app.run.gold, 777)

    def test_heal_command(self):
        self.app.run.hp = 10
        self._run("heal 30")
        self.assertEqual(self.app.run.hp, 40)

    def test_hp_and_maxhp_commands(self):
        self._run("maxhp 200")
        self.assertEqual(self.app.run.max_hp, 200)
        self._run("hp 150")
        self.assertEqual(self.app.run.hp, 150)

    def test_hp_clamped_to_max(self):
        self._run("maxhp 100")
        self._run("hp 9999")
        self.assertLessEqual(self.app.run.hp, self.app.run.max_hp)

    def test_clear_empties_output(self):
        self._run("status")
        self.assertTrue(self.con.lines)
        self._run("clear")
        self.assertEqual(self.con.lines, [])

    def test_close_command_closes(self):
        self.app._on_f1()
        self._run("close")
        self.assertFalse(self.con.open)

    def test_give_requires_battle(self):
        self.assertIsNone(self.app.battle)
        out = self._run("give strike")
        self.assertIn("战斗", out)

    def test_kill_requires_battle(self):
        self.assertIsNone(self.app.battle)
        out = self._run("kill")
        self.assertIn("战斗", out)

    # -- 兑换码 -------------------------------------------------------- #
    def test_redeem_code_via_console(self):
        self._run("manpower")
        self.assertEqual(self.app.run.max_hp, 75 + 50)

    def test_redeem_is_flexible(self):
        self._run("Research All")
        self.assertGreater(len(self.app.run.deck), 10)

    def test_invalid_code_reports_error(self):
        out = self._run("qqqq_not_real")
        self.assertIn("无效", out)

    def test_empty_input_closes_console(self):
        self.app._on_f1()
        self.con.buf = ""
        self.con.submit()
        self.assertFalse(self.con.open, "空输入回车应关闭控制台")

    # -- 稳健性 -------------------------------------------------------- #
    def test_console_survives_many_commands(self):
        for cmd in ("status", "help", "list", "gold 1", "heal 1", "hp 50",
                    "bogus", "", "  ", "kill"):
            self._run(cmd)
        self.assertIsNotNone(self.con.lines)

    def test_console_draw_does_not_raise(self):
        self.app._on_f1()
        for name in ("menu", "map", "settings", "codex"):
            self.app.show(name)
            try:
                self.con.draw(self.app.canvas, self.app.W, self.app.H)
            except Exception as exc:
                self.fail("控制台在 %s 绘制失败：%r" % (name, exc))

    def test_console_does_not_break_game_flow(self):
        """开控制台执行指令后，界面仍能正常切换。"""
        self.app._on_f1()
        self._run("gold 100")
        self.app._on_f1()          # close
        for name in ("menu", "settings", "codex"):
            self.app.show(name)
        self.assertTrue(True)


@unittest.skipUnless(_tk_ok(), "无 Tk 显示环境")
class TestConsoleOnTop(unittest.TestCase):
    """控制台必须画在最上层。"""

    def test_console_items_drawn_last(self):
        import ui.app as A
        app = A.App()
        try:
            app.show("menu")
            app._on_f1()
            app.update_idletasks()
            items = app.canvas.find_all()
            titles = [app.canvas.itemcget(i, "text") for i in items[-40:]
                      if app.canvas.type(i) == "text"]
            self.assertTrue(any("控 制 台" in t for t in titles),
                            "控制台标题应在最后绘制（最上层）")
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
