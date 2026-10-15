#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI 用的测试运行器：把失败原因明确打出来。

unittest discover 的输出会被各测试的 print 淹没，
在 GitHub Actions 里很难看出到底哪个失败了。这里：
  1. 把所有输出收集起来
  2. 最后单独打印「失败清单」并加 ::error:: 标记
  3. 失败时以非 0 退出
"""

from __future__ import annotations

import io
import os
import sys
import traceback
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SF_ALLOW_HEADLESS_QT", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def main() -> int:
    loader = unittest.TestLoader()
    try:
        suite = loader.discover("tests")
    except Exception:
        print("::error::测试发现阶段就崩了")
        traceback.print_exc()
        return 1

    total = suite.countTestCases()
    print("=" * 62)
    print(" 发现 %d 个测试" % total)
    print("=" * 62, flush=True)

    buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=buf, verbosity=2)
    result = runner.run(suite)

    # 把详细输出整段打出来（方便看哪个用例挂了）
    print(buf.getvalue(), flush=True)

    print()
    print("=" * 62)
    print(" 测试结果")
    print("=" * 62)
    print("  运行: %d" % result.testsRun)
    print("  失败: %d" % len(result.failures))
    print("  错误: %d" % len(result.errors))
    print("  跳过: %d" % len(result.skipped))

    bad = list(result.failures) + list(result.errors)
    if bad:
        print()
        print("!! 有 %d 个用例没通过：" % len(bad))
        for case, tb in bad:
            print()
            print("::error::%s" % case)
            # 只打最后几行（真正的断言信息）
            lines = [l for l in tb.strip().split("\n") if l.strip()]
            for l in lines[-6:]:
                print("    " + l)
        print()
        print("=" * 62)
        return 1

    print()
    print(" ✅ 全部通过")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
