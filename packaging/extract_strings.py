#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描源码，抽取**面向玩家**的中文字符串，生成 locales/zh.json。

只收玩家看得见的文案，排除：
  * docstring（开发者文档）
  * 注释
  * 源码里拼出来的短碎片（如 " 张，同名卡上限为 "）
  * 调试/断言信息（含 %d %s 等格式化占位且不在 UI 上下文）

判定原则：**宁可少收，不可错收** —— 收到开发者文本会让翻译量虚高，
而且翻出来的东西永远不会显示给玩家。
"""
import ast
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CJK = re.compile(r'[\u4e00-\u9fff]')
SCAN_DIRS = ("core", "ui", "qt")
SKIP_FILES = {"i18n.py"}

# 明确排除的文件（纯测试/调试工具，玩家看不到）
SKIP_NAMES = {"headless_tour.py", "selftest.py"}

# 调试/开发文案的特征
DEBUG_HINTS = (
    "assert", "debug", "DEBUG", "traceback", "Traceback",
    "内部", "开发者", "TODO", "FIXME", "XXX",
)


def _is_docstring(node, parents):
    """判断一个字符串节点是不是 docstring。

    注意：docstring 在 AST 里是 ``Expr(Constant(...))`` —— Constant 被一层
    Expr 包着。所以要比的是**父节点**是不是那个 Expr，而不是 Constant 本身
    （早期版本这里写错，导致所有 docstring 都被当成玩家文案收了进来）。
    """
    if not parents:
        return False
    parent = parents[-1]
    grand = parents[-2] if len(parents) >= 2 else None
    if not isinstance(parent, ast.Expr):
        return False
    if grand is None:
        return False
    if not isinstance(grand, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)):
        return False
    body = getattr(grand, "body", None)
    return bool(body) and body[0] is parent


class Visitor(ast.NodeVisitor):
    def __init__(self):
        self.stack = []
        self.strings = set()

    def visit(self, node):
        self.stack.append(node)
        try:
            super().visit(node)
        finally:
            self.stack.pop()

    def visit_Constant(self, node):
        if isinstance(node.value, str) and node.value:
            if not _is_docstring(node, self.stack[:-1]):
                self.strings.add(("const", node.value))

    def visit_JoinedStr(self, node):
        """f-string：把 {expr} 换成 {0} {1} 形式的规范占位符。"""
        parts = []
        idx = 0
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("\x00%d\x00" % idx)
                idx += 1
        self.strings.add(("fstr", "".join(parts)))


def _looks_like_ui(s: str) -> bool:
    """粗略判断这条字符串是否面向玩家。"""
    if not s or not CJK.search(s):
        return False
    # 纯空白/纯符号
    if not s.strip():
        return False
    # 调试/开发特征
    for h in DEBUG_HINTS:
        if h in s:
            return False
    # 含 % 格式符的（多为日志/异常/断言）
    if re.search(r'%[sdrfx]', s):
        return False
    # 明显的代码痕迹
    if any(t in s for t in ("==", "!=", "self.", "None", "def ", "()")):
        return False
    # 超长（>120 字）多半是文档
    if len(s) > 120:
        return False
    return True


def strings_from_source(path):
    out = set()
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
    except Exception:
        return out
    v = Visitor()
    v.visit(tree)
    for kind, s in v.strings:
        if not _looks_like_ui(s):
            continue
        # 归一化：把 \x00N\x00 还原成 {0} {1}，便于人读与翻译
        if kind == "fstr":
            s = re.sub(r'\x00(\d+)\x00', lambda m: "{%s}" % m.group(1), s)
            if not s.strip() or not CJK.search(s):
                continue
        out.add(s)
    return out


def main():
    found = {}
    for d in SCAN_DIRS:
        full = os.path.join(ROOT, d)
        if not os.path.isdir(full):
            continue
        for fn in sorted(os.listdir(full)):
            if not fn.endswith(".py") or fn in SKIP_FILES or fn in SKIP_NAMES:
                continue
            for s in strings_from_source(os.path.join(full, fn)):
                found.setdefault(s, []).append("%s/%s" % (d, fn))

    loc = os.path.join(ROOT, "locales")
    os.makedirs(loc, exist_ok=True)
    zh = {k: k for k in sorted(found)}
    with open(os.path.join(loc, "zh.json"), "w", encoding="utf-8") as f:
        json.dump(zh, f, ensure_ascii=False, indent=1, sort_keys=True)

    print("抽取到 %d 条面向玩家的中文文案" % len(zh))
    from collections import Counter
    c = Counter()
    for k, files in found.items():
        for x in files:
            c[x] += 1
    print("\n分布（前 15）:")
    for name, n in c.most_common(15):
        print("  %-24s %5d" % (name, n))


if __name__ == "__main__":
    main()
