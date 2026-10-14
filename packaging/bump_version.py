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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    ver = sys.argv[1].strip()
    if not re.match(r"^\d+(\.\d+)*$", ver):
        print("版本号必须是纯数字点分，例如 0.10 或 1.0")
        return 1
    notes = [a for a in sys.argv[2:] if a.strip()]
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
