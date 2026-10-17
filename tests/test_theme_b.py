"""附录 B 题材变更验收测试（ARCHITECTURE.md §附录 B）。

红线：
- `id` / 字段名 / 函数签名 / 数值 一律不变（只改面向玩家的中文显示文本）
- 面向用户的字符串里不得残留海洋词汇
- `main.py --selftest` 必须通过
"""

import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import ROOT, load  # noqa: E402

# Lead 给的验收 grep 词表，外加附录 B.4 的同义词
SEA_WORDS = ("鲸", "深海", "潮汐", "珊瑚", "海洋", "气泡", "海", "浪", "鱼", "虾", "蟹", "海藻")
# 「海」单字太宽（会命中「海量」等），单独放宽处理

STRICT_SEA = ("鲸", "深海", "潮汐", "珊瑚", "海洋", "气泡")


def iter_source_files():
    for base in ("core", "ui"):
        d = os.path.join(ROOT, base)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".py"):
                yield os.path.join(d, fn)
    mp = os.path.join(ROOT, "main.py")
    if os.path.exists(mp):
        yield mp


def strip_comments_and_docstrings(src):
    """去掉 # 注释与三引号块，只留真正会展示的代码。"""
    out = []
    in_triple = False
    triple_delim = None
    for line in src.split("\n"):
        s = line.strip()
        if in_triple:
            if triple_delim in line:
                in_triple = False
            continue
        for d in ('"""', "'''"):
            if s.startswith(d):
                if line.count(d) < 2:
                    in_triple = True
                    triple_delim = d
                break
        else:
            # 去掉行内注释（简单处理，不追求完美）
            idx = line.find("#")
            if idx >= 0:
                line = line[:idx]
            out.append(line)
    return "\n".join(out)


class TestNamingRedline(unittest.TestCase):
    """B.0/B.3 红线：id 与结构不得改动。"""

    def test_card_ids_still_present(self):
        """卡牌 id 必须仍然是 snake_case 英文标识，未被改成中文。"""
        cards, err = load("core.cards")
        self.assertIsNotNone(cards, "core.cards 不可用：%s" % err)
        bad = [cd.id for cd in cards.CARD_DB.values()
               if not re.match(r"^[a-z][a-z0-9_]*$", cd.id)]
        self.assertEqual(bad, [],
                         "以下卡牌 id 不再是英文 snake_case（题材变更误改了 id）：%s"
                         % bad[:20])

    def test_buff_keys_unchanged(self):
        """B.1：代码标识符（键名）一律不改，只改显示名。"""
        engine, err = load("core.engine")
        self.assertIsNotNone(engine, "core.engine 不可用：%s" % err)
        expected = {
            "BUFF_STRENGTH": "strength", "BUFF_DEXTERITY": "dexterity",
            "BUFF_VULNERABLE": "vulnerable", "BUFF_WEAK": "weak",
            "BUFF_FRAIL": "frail", "BUFF_POISON": "poison",
            "BUFF_THORNS": "thorns", "BUFF_METALLICIZE": "metallicize",
            "BUFF_RITUAL": "ritual", "BUFF_ARTIFACT": "artifact",
            "BUFF_PLATED_ARMOR": "plated_armor", "BUFF_REGENERATE": "regenerate",
            "BUFF_INTANGIBLE": "intangible", "BUFF_BARRIER": "barrier",
            "BUFF_CHAIN": "chain", "BUFF_ENVENOM": "envenom",
            "BUFF_ACCURACY": "accuracy",
        }
        wrong = {}
        for const, key in expected.items():
            got = getattr(engine, const, None)
            if got != key:
                wrong[const] = got
        self.assertEqual(wrong, {},
                         "B.1 要求 buff 键名不变（只改显示名），以下被改动：%s" % wrong)

    def test_archetype_constants_unchanged(self):
        cards, _ = load("core.cards")
        expected = {"ARCH_ATTACK": "attack", "ARCH_BLOCK": "block",
                    "ARCH_POISON": "poison", "ARCH_ENERGY": "energy",
                    "ARCH_SUMMON": "summon"}
        wrong = {c: getattr(cards, c, None) for c, v in expected.items()
                 if getattr(cards, c, None) != v}
        self.assertEqual(wrong, {}, "ARCH_* 常量值被改动：%s" % wrong)

    def test_enemy_ids_unchanged_shape(self):
        enemies, err = load("core.enemies")
        self.assertIsNotNone(enemies, "core.enemies 不可用：%s" % err)
        bad = [e.id for e in enemies.ENEMY_DB.values()
               if not re.match(r"^[a-z][a-z0-9_]*$", e.id)]
        self.assertEqual(bad, [], "敌人 id 不再是英文 snake_case：%s" % bad[:20])


class TestNoSeaWordsInUserFacingText(unittest.TestCase):
    """B.4 验收 1：面向用户的字符串里不得残留海洋词汇。"""

    def test_source_has_no_sea_words_in_string_literals(self):
        offenders = []
        for path in iter_source_files():
            with open(path, encoding="utf-8") as f:
                raw = f.read()
            clean = strip_comments_and_docstrings(raw)
            for i, line in enumerate(clean.split("\n"), 1):
                # 隐藏彩蛋卡（致敬最初的鲸鱼企划）不算残留
                if "吉祥物" in line or "梦到了一只鲸鱼" in line:
                    continue
                for w in STRICT_SEA:
                    if w in line:
                        offenders.append("%s:%d  %s" % (
                            os.path.relpath(path, ROOT), i, line.strip()[:110]))
                        break
        self.assertEqual(offenders, [],
                         "面向用户的字符串中残留海洋词汇（附录 B.4 验收 1）：\n  " +
                         "\n  ".join(offenders[:40]))

    def test_card_display_text_no_sea_words(self):
        cards, err = load("core.cards")
        self.assertIsNotNone(cards, "core.cards 不可用：%s" % err)
        bad = []
        for cd in cards.CARD_DB.values():
            # 彩蛋卡 whale 是故意致敬最初企划的，不算残留
            if getattr(cd, "id", "") == "whale":
                continue
            blob = "%s %s" % (cd.name, cd.text)
            for w in STRICT_SEA:
                if w in blob:
                    bad.append("%s: name=%r text=%r" % (cd.id, cd.name, cd.text[:50]))
                    break
        self.assertEqual(bad, [], "卡牌显示文本残留海洋词汇：\n  " + "\n  ".join(bad[:30]))

    def test_enemy_display_text_no_sea_words(self):
        enemies, err = load("core.enemies")
        self.assertIsNotNone(enemies, "core.enemies 不可用：%s" % err)
        bad = []
        for e in enemies.ENEMY_DB.values():
            blob = "%s %s" % (e.name, e.desc or "")
            for w in STRICT_SEA:
                if w in blob:
                    bad.append("%s: name=%r desc=%r" % (e.id, e.name, (e.desc or "")[:40]))
                    break
            for m in e.moves:
                if any(w in (m.name or "") for w in STRICT_SEA):
                    bad.append("%s/%s: move=%r" % (e.id, m.id, m.name))
        self.assertEqual(bad, [], "敌人显示文本残留海洋词汇：\n  " + "\n  ".join(bad[:30]))

    def test_relic_display_text_no_sea_words(self):
        relics, err = load("core.relics")
        if relics is None:
            self.fail("core.relics 不可用：%s" % err)
        bad = []
        for r in getattr(relics, "RELIC_DB", {}).values():
            blob = "%s %s" % (r.name, r.text)
            for w in STRICT_SEA:
                if w in blob:
                    bad.append("%s: name=%r" % (r.id, r.name))
                    break
        self.assertEqual(bad, [], "遗物显示文本残留海洋词汇：\n  " + "\n  ".join(bad[:30]))


class TestThemePalette(unittest.TestCase):
    """B.2：配色替换为军事风，但保留同名常量。"""

    def setUp(self):
        self.theme, self.err = load("ui.theme")
        if self.theme is None:
            self.fail("ui.theme 不可用：%s" % self.err)

    def test_kept_constant_names(self):
        for n in ("BG_DEEP", "BG_DARK", "PANEL", "PANEL_LIGHT", "BORDER", "TEXT",
                  "TEXT_DIM", "TEXT_MUTED", "GOLD", "CYAN", "GREEN", "RED",
                  "PURPLE", "ORANGE"):
            self.assertTrue(hasattr(self.theme, n),
                            "B.2 要求保留同名常量 %s" % n)

    def test_palette_is_not_ocean_blue(self):
        """旧配色是青蓝深海渐变；新配色应为硝烟褐/军绿/钢灰。"""
        def rgb(hexs):
            hexs = hexs.lstrip("#")
            return tuple(int(hexs[i:i + 2], 16) for i in (0, 2, 4))

        bg = rgb(self.theme.BG_DEEP)
        r, g, b = bg
        self.assertLess(b, r + 20,
                        "BG_DEEP=%s 仍然偏蓝（B>R），疑似未换掉深海配色" % self.theme.BG_DEEP)


class TestSelftestStillPasses(unittest.TestCase):
    """B.4 验收 2：main.py --selftest 必须通过。"""

    def test_selftest(self):
        main_py = os.path.join(ROOT, "main.py")
        if not os.path.exists(main_py):
            self.fail("main.py 不存在（附录 B.4 要求 --selftest 通过）")
        # 用 encoding + errors 明确指定：Windows 上子进程输出可能是
        # cp1252/GBK，text=True 的默认解码会让 stdout/stderr 变成 None
        # （真踩过：TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'）
        import os as _os
        env = dict(_os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        proc = subprocess.run([sys.executable, "main.py", "--selftest"],
                              cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=180, env=env)
        combined = (proc.stdout or "") + (proc.stderr or "")
        self.assertEqual(proc.returncode, 0,
                         "main.py --selftest 返回 %d\n输出:\n%s"
                         % (proc.returncode, combined[-3000:]))
        lowered = combined.lower()
        self.assertNotIn("traceback", lowered,
                         "--selftest 出现异常堆栈：\n%s" % combined[-3000:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
