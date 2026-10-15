#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI 用的测试运行器。

设计要点（都是踩坑换来的）：
  1. **边跑边输出**，不缓冲。
     早先版本把 unittest 输出收进 StringIO、最后一次性打印。
     结果 CI 上进程 exit 127 崩溃时，缓冲区里的内容全部丢失 ——
     只知道"失败了"，完全不知道挂在哪个测试上。
  2. **每个测试文件单独报告进度**。
     崩溃时最后一行就是真凶。
  3. 最后仍打一份"失败清单"（加 ::error:: 前缀，GitHub 会高亮）。
"""

from __future__ import annotations

import faulthandler
import os
import sys
import unittest

# 原生崩溃（exit 127 / 段错误）时把 C 层调用栈 dump 到 stderr。
# 没有这个的话，Windows 上进程直接消失，日志里什么都看不到 ——
# 这正是之前"只知道 exit 127、不知道挂在哪"的原因。
try:
    faulthandler.enable(file=sys.stderr, all_threads=True)
except Exception:
    pass

# 测试跑太久就 dump 一次栈（防止彻底卡死时无从下手）
try:
    faulthandler.dump_traceback_later(600, exit=True)
except Exception:
    pass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SF_ALLOW_HEADLESS_QT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


class _StreamingResult(unittest.TextTestResult):
    """把每个用例的结果实时打出来（不缓冲）。"""

    def startTest(self, test):
        super().startTest(test)
        # 不用 end='' 打点：崩溃时至少能看到"当前正在跑哪个"
        sys.stdout.write("  -> %s\n" % test)
        sys.stdout.flush()

    def addSuccess(self, test):
        super().addSuccess(test)

    def addError(self, test, err):
        super().addError(test, err)
        print("     !! ERROR")
        sys.stdout.flush()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        print("     !! FAIL")
        sys.stdout.flush()

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        print("     (skip: %s)" % reason)
        sys.stdout.flush()


def main() -> int:
    print("=" * 62)
    print(" 开始跑测试（逐条打印，崩溃时最后一行就是真凶）")
    print("=" * 62, flush=True)

    loader = unittest.TestLoader()
    try:
        suite = loader.discover("tests")
    except Exception:
        import traceback
        print("::error::测试发现阶段就崩了")
        traceback.print_exc()
        return 1

    total = suite.countTestCases()
    print(" 共 %d 个测试\n" % total, flush=True)

    runner = unittest.TextTestRunner(
        stream=sys.stdout, verbosity=0, resultclass=_StreamingResult)

    try:
        result = runner.run(suite)
    except BaseException:
        import traceback
        print("\n::error::测试过程中抛出未捕获异常（进程可能即将崩溃）")
        traceback.print_exc()
        return 1

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
