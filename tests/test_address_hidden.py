#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器地址不能暴露给玩家。

地址写死在界面 / 更新说明里 = 给所有人一个攻击目标：
扫端口、找漏洞、DDOS 都有明确靶子。所以：
  * 界面只显示「在线 / 离线」
  * 源码里不以明文出现
"""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import relay_client as RC  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IP_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestNoPlainIP(unittest.TestCase):

    def test_ui_files_have_no_ip(self):
        """qt/*.py 里不能出现 IP 字面量。"""
        bad = []
        qt_dir = os.path.join(ROOT, "qt")
        for fn in os.listdir(qt_dir):
            if not fn.endswith(".py"):
                continue
            for m in IP_RE.finditer(_read(os.path.join("qt", fn))):
                ip = m.group(0)
                if ip.startswith(("127.", "0.0.0.0", "255.", "192.168")):
                    continue
                # 这些是输入框的**占位示例**（局域网教学用），不是真实服务器
                if ip in ("45.123.45.67", "10.255.255.255", "255.255.255.255"):
                    continue
                bad.append("%s: %s" % (fn, ip))
        self.assertEqual(bad, [], "界面代码里出现 IP：%s" % bad[:5])

    def test_relay_client_has_no_plain_ip(self):
        src = _read("core/relay_client.py")
        bad = [m.group(0) for m in IP_RE.finditer(src)
               if not m.group(0).startswith(("127.", "0.0.0.0"))]
        self.assertEqual(bad, [], "relay_client 里有明文 IP：%s" % bad[:5])

    def test_version_json_has_no_ip(self):
        src = _read("version.json")
        self.assertIsNone(IP_RE.search(src), "更新说明里不该出现服务器 IP")


class TestHostResolution(unittest.TestCase):

    def test_builtin_host_still_resolves(self):
        """混淆存储不影响解析 —— 内置地址必须能解出来。"""
        eps = RC.relay_endpoints()
        self.assertTrue(eps, "内置服务器地址解析失败")
        host, port = eps[0]
        self.assertTrue(host, "主机名为空（混淆 key 错了吧）")
        self.assertIsInstance(port, int)

    def test_builtin_host_is_configured(self):
        self.assertTrue(RC.relay_configured())

    def test_builtin_is_not_user_configured(self):
        """内置地址不算「玩家自己配的」—— 所以界面不回填。"""
        os.environ.pop("SF_RELAY_HOSTS", None)
        self.assertFalse(RC.is_user_configured())


class TestUIShowsStatusOnly(unittest.TestCase):

    def test_lobby_source_uses_status_text(self):
        src = _read("qt/qlobby.py")
        # 不该再把 relay_address() 塞进 setText
        self.assertNotIn('"服务器：%s" % _rc.relay_address()', src,
                         "公网页不该显示服务器地址")
        self.assertNotIn("% srv", src.replace("，", ","),
                         "状态栏不该拼服务器地址")

    def test_address_helper_not_printed(self):
        """relay_address() 只该给调试用，不该出现在界面字符串里。"""
        src = _read("qt/qlobby.py")
        for m in re.finditer(r"relay_address\(\)", src):
            line_start = src.rfind("\n", 0, m.start()) + 1
            line_end = src.find("\n", m.end())
            line = src[line_start:line_end if line_end != -1 else len(src)]
            self.assertNotIn("setText", line,
                             "relay_address() 被塞进了界面：" + line.strip()[:60])


if __name__ == "__main__":
    unittest.main(verbosity=2)
