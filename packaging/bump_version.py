#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发新版本时用这个脚本：升版本号 + 写更新说明。

用法：
    python3 packaging/bump_version.py 0.10 "修复：控制台卡死" "新增：存档管理"

它会同时更新：
  * core/version.py   （唯一版本来源）
  * version.json      （GitHub 上的版本清单，供游戏内检查更新）
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def _write(p, s):
    with open(os.path.join(ROOT, p), "w", encoding="utf-8") as f:
        f.write(s)


def set_version_file(new_ver):
    """改 core/version.py 里的 VERSION 与 VERSION_LABEL。"""
    p = "core/version.py"
    s = _read(p)
    s = re.sub(r'^VERSION = "[^"]*"', 'VERSION = "%s"' % new_ver, s, flags=re.M)
    label = "%s 测试版" % new_ver
    label_en = "%s Beta" % new_ver
    s = re.sub(r'^VERSION_LABEL = "[^"]*"',
               'VERSION_LABEL = "%s"' % label, s, flags=re.M)
    s = re.sub(r'^VERSION_LABEL_EN = "[^"]*"',
               'VERSION_LABEL_EN = "%s"' % label_en, s, flags=re.M)
    _write(p, s)
    return label, label_en


def set_manifest(new_ver, notes, label, label_en):
    p = "version.json"
    d = {}
    if os.path.isfile(os.path.join(ROOT, p)):
        try:
            d = json.loads(_read(p))
        except Exception:
            d = {}
    d["version"] = new_ver
    d["label"] = label
    d["label_en"] = label_en
    d["released"] = time.strftime("%Y-%m-%d")
    d["notes"] = list(notes)
    d["notes_en"] = list(notes)
    d.setdefault("url",
                 "https://github.com/d5gkmk96kj-lab/steel-frontline/releases")
    d.setdefault("mandatory", False)
    _write(p, json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def auto_next(cur: str) -> str:
    """按「每发一次加 0.01」推进末段。

        0.9     -> 0.9.01
        0.9.01  -> 0.9.02
        0.9.09  -> 0.9.10
        0.9.99  -> 0.10        (进位)
        0.10    -> 0.10.01
    """
    cur = str(cur or "").strip().lstrip("vV")
    parts = cur.split(".")
    if len(parts) < 3:
        # 只有 X.Y -> 补一个 .01
        return ".".join(parts[:2]) + ".01"
    try:
        last = int(re.sub(r"\D", "", parts[-1]) or "0")
    except Exception:
        last = 0
    last += 1
    width = max(2, len(re.sub(r"\D", "", parts[-1])))
    if last >= 10 ** width:            # 99 -> 100，进位到上一段
        head = parts[:-1]
        try:
            head[-1] = str(int(head[-1]) + 1)   # 0.9.99 -> 0.10
        except Exception:
            head.append("1")
        return ".".join(head)
    parts[-1] = str(last).zfill(2)
    return ".".join(parts)


def main():
    argv = sys.argv[1:]
    auto_mode = False
    # --auto：自动在当前版本上 +0.01
    if argv and argv[0] in ("--auto", "-a", "auto"):
        auto_mode = True
        cur = None
        # 直接读 core/version.py，避免依赖 import 路径
        try:
            import re as _re
            src = _read("core/version.py")
            m = _re.search(r'^VERSION\s*=\s*"([^"]+)"', src, _re.M)
            if m:
                cur = m.group(1)
        except Exception:
            cur = None
        if not cur:
            try:
                sys.path.insert(0, ROOT)
                from core import version as _V
                cur = _V.VERSION
            except Exception:
                cur = None
        if not cur:
            print("读不到当前版本，请手动指定")
            return 1
        ver = auto_next(cur)
        argv = argv[1:]
        print("自动递增 -> %s" % ver)
    else:
        print(__doc__)
        print("\n也可以用： python3 packaging/bump_version.py --auto \"改了什么\"")
        return 1
    if not re.match(r"^\d+(\.\d+)+$", ver):
        print("版本号必须是数字点分，例如 0.9.02 或 1.0")
        return 1
    # --auto 时 argv 里只有备注（版本号自动算）；手动指定时 argv[0] 是版本号。
    notes = ([a for a in argv if a.strip()] if auto_mode
             else [a for a in argv[1:] if a.strip()])
    label, label_en = set_version_file(ver)
    set_manifest(ver, notes, label, label_en)
    print("已升级到 %s" % label)
    for n in notes:
        print("  · %s" % n)
    print()
    print("下一步：")
    print("  1. bash packaging/build_app.sh && bash packaging/build_dmg.sh")
    print("  2. bash packaging/build_app_public.sh && bash packaging/build_dmg_public.sh")
    print("  3. 把新的公开版 DMG 放进 releases/ 并改名")
    print("  4. git add -A && git commit && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
