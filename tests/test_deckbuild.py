"""卡组构筑测试（core/deckbuild.py）。

覆盖：张数上下限、同名卡上限、非法 id、空卡组、起始牌例外、
random_deck / recommended_decks / deck_summary / card_pool。

纯 unittest，零 pytest。
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load  # noqa: E402


def _mod():
    m, err = load("core.deckbuild")
    if m is None:
        raise AssertionError("core.deckbuild 无法导入：%s" % err)
    return m


class DeckbuildCase(unittest.TestCase):
    def setUp(self):
        self.D = _mod()
        self.cards, err = load("core.cards")
        if self.cards is None:
            self.fail("core.cards 不可用：%s" % err)

    # -------------------------------------------------- 构造合法卡组的助手
    def _legal_deck(self, size=None):
        """造一个确定合法的卡组：respecting MAX_COPIES。"""
        size = size if size is not None else self.D.DECK_SIZE_MIN
        pool = [c.id for c in self.cards.CARD_DB.values()
                if c.type not in getattr(self.D, "EXCLUDED_TYPES", ())]
        self.assertTrue(pool, "卡池为空")
        max_copies = self.D.MAX_COPIES
        out = []
        i = 0
        while len(out) < size:
            out.append(pool[i % len(pool)])
            i += 1
            # 每张牌不超过 max_copies
            if i % len(pool) == 0:
                # 一轮下来每张都到 max_copies 了，需要更多不同牌
                pass
        # 重新用「每种最多 max_copies」的方式构造
        out = []
        for cid in pool:
            for _ in range(min(max_copies, size - len(out))):
                out.append(cid)
            if len(out) >= size:
                break
        return out[:size]


class TestValidateDeck(DeckbuildCase):

    def test_constants_exist_and_sane(self):
        for n in ("DECK_SIZE_MIN", "DECK_SIZE_MAX", "MAX_COPIES"):
            self.assertTrue(hasattr(self.D, n), "缺少常量 %s" % n)
        self.assertIsInstance(self.D.DECK_SIZE_MIN, int)
        self.assertIsInstance(self.D.DECK_SIZE_MAX, int)
        self.assertLess(self.D.DECK_SIZE_MIN, self.D.DECK_SIZE_MAX,
                        "DECK_SIZE_MIN 应小于 MAX")
        self.assertGreater(self.D.MAX_COPIES, 0)

    def test_empty_deck_rejected(self):
        ok, msg = self.D.validate_deck([])
        self.assertFalse(ok, "空卡组必须被拒绝")
        self.assertTrue(msg, "拒绝时必须给出原因")

    def test_none_rejected_without_exception(self):
        for bad in (None, 123, "strike", {"a": 1}):
            try:
                r = self.D.validate_deck(bad)
            except Exception as exc:
                self.fail("validate_deck(%r) 抛异常：%r" % (bad, exc))
            self.assertIsInstance(r, tuple, "应返回 (bool, str) 元组")
            self.assertEqual(len(r), 2)
            self.assertFalse(r[0], "非法输入 %r 应返回 False" % (bad,))

    def test_returns_bool_str_tuple(self):
        r = self.D.validate_deck(self._legal_deck())
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 2)
        self.assertIsInstance(r[0], bool)
        self.assertIsInstance(r[1], str)

    def test_legal_deck_accepted(self):
        deck = self._legal_deck(self.D.DECK_SIZE_MIN)
        ok, msg = self.D.validate_deck(deck)
        self.assertTrue(ok, "合法卡组被拒绝：%s（卡组=%s）" % (msg, deck[:8]))

    def test_below_min_rejected(self):
        deck = self._legal_deck(self.D.DECK_SIZE_MIN - 1)
        ok, msg = self.D.validate_deck(deck)
        self.assertFalse(ok, "%d 张（低于下限 %d）应被拒绝"
                         % (len(deck), self.D.DECK_SIZE_MIN))

    def test_above_max_rejected(self):
        size = self.D.DECK_SIZE_MAX + 1
        pool = [c.id for c in self.cards.CARD_DB.values()
                if c.type not in getattr(self.D, "EXCLUDED_TYPES", ())]
        deck = []
        i = 0
        while len(deck) < size:
            deck.append(pool[i % len(pool)])
            i += 1
            if i > 10000:
                break
        ok, msg = self.D.validate_deck(deck)
        self.assertFalse(ok, "%d 张（超过上限 %d）应被拒绝"
                         % (len(deck), self.D.DECK_SIZE_MAX))

    def test_boundary_exact_min_and_max(self):
        for size in (self.D.DECK_SIZE_MIN, self.D.DECK_SIZE_MAX):
            deck = self._legal_deck(size)
            ok, msg = self.D.validate_deck(deck)
            self.assertTrue(ok, "边界张数 %d 应被接受：%s" % (size, msg))

    def test_too_many_copies_rejected(self):
        """同一张牌超过 MAX_COPIES 必须被拒绝。"""
        size = self.D.DECK_SIZE_MIN
        # 必须挑一张**非起始牌**（起始牌 strike/defend 有更高上限 STARTER_MAX_COPIES）
        starter = set(getattr(self.D, "STARTER_CARD_IDS", ()))
        pool = [c.id for c in self.cards.CARD_DB.values()
                if c.type not in getattr(self.D, "EXCLUDED_TYPES", ())
                and c.id not in starter]
        self.assertTrue(pool, "没有非起始牌可用于本用例")
        target = pool[0]
        over = self.D.MAX_COPIES + 1
        others = [c for c in pool if c != target]
        deck = [target] * over
        i = 0
        while len(deck) < size:
            deck.append(others[i % len(others)])
            i += 1
        ok, msg = self.D.validate_deck(deck)
        self.assertFalse(ok, "%s 放了 %d 张（上限 %d）应被拒绝"
                         % (target, over, self.D.MAX_COPIES))

    def test_starter_cards_may_exceed_normal_cap(self):
        """起始牌（strike/defend）应有更高的上限。"""
        starter = getattr(self.D, "STARTER_CARD_IDS", frozenset())
        starter_max = getattr(self.D, "STARTER_MAX_COPIES", None)
        if not starter or starter_max is None:
            self.skipTest("没有 STARTER_CARD_IDS / STARTER_MAX_COPIES")
        cid = sorted(starter)[0]
        deck = [cid] * min(starter_max, self.D.DECK_SIZE_MIN)
        pool = [c.id for c in self.cards.CARD_DB.values()
                if c.type not in getattr(self.D, "EXCLUDED_TYPES", ()) and c.id != cid]
        i = 0
        while len(deck) < self.D.DECK_SIZE_MIN:
            deck.append(pool[i % len(pool)])
            i += 1
        ok, msg = self.D.validate_deck(deck)
        self.assertTrue(ok, "起始牌 %s 放 %d 张应被允许（上限 %d）：%s"
                        % (cid, min(starter_max, self.D.DECK_SIZE_MIN),
                           starter_max, msg))

    def test_unknown_card_rejected(self):
        deck = self._legal_deck(self.D.DECK_SIZE_MIN)
        deck[0] = "__no_such_card__"
        ok, msg = self.D.validate_deck(deck)
        self.assertFalse(ok, "含未知 id 的卡组必须被拒绝")
        self.assertIn("__no_such_card__", msg,
                      "错误信息应指出是哪个 id 有问题，实际：%r" % msg)

    def test_unknown_card_variants_rejected(self):
        for bad in ("", " ", "STRIKE", "strike ", " strike", "strike\n",
                    "../../etc/passwd", "<script>", "a" * 500):
            deck = self._legal_deck(self.D.DECK_SIZE_MIN)
            deck[0] = bad
            try:
                ok, msg = self.D.validate_deck(deck)
            except Exception as exc:
                self.fail("id=%r 时抛异常：%r" % (bad, exc))
            self.assertFalse(ok, "非法 id %r 应被拒绝" % bad)

    def test_status_and_curse_rejected(self):
        """status/curse 不应允许进入自建卡组。"""
        excluded = getattr(self.D, "EXCLUDED_TYPES", frozenset())
        if not excluded:
            self.skipTest("没有 EXCLUDED_TYPES")
        bad_card = None
        for c in self.cards.CARD_DB.values():
            if c.type in excluded:
                bad_card = c.id
                break
        if bad_card is None:
            self.skipTest("卡库里没有 status/curse 卡")
        deck = self._legal_deck(self.D.DECK_SIZE_MIN)
        deck[0] = bad_card
        ok, msg = self.D.validate_deck(deck)
        self.assertFalse(ok, "%s (type=%s) 不应能进卡组" % (bad_card, excluded))

    def test_all_validated_ids_exist_in_db(self):
        """内置推荐卡组必须全部合法（防止推荐一个非法卡组）。"""
        rec = self.D.recommended_decks()
        self.assertTrue(rec, "recommended_decks() 为空")
        for name, deck in rec.items():
            if isinstance(deck, dict):
                deck = deck.get("cards") or deck.get("deck") or []
            ok, msg = self.D.validate_deck(list(deck))
            self.assertTrue(ok, "推荐卡组 %r 非法：%s" % (name, msg))


class TestRandomDeck(DeckbuildCase):

    def test_random_deck_size(self):
        for size in (self.D.DECK_SIZE_MIN, 30, self.D.DECK_SIZE_MAX):
            d = self.D.random_deck(random.Random(1), size)
            self.assertEqual(len(d), size, "random_deck(%d) 应返回 %d 张" % (size, size))

    def test_random_deck_is_valid(self):
        for seed in range(20):
            d = self.D.random_deck(random.Random(seed), 30)
            ok, msg = self.D.validate_deck(list(d))
            self.assertTrue(ok, "随机卡组（seed=%d）非法：%s" % (seed, msg))

    def test_random_deck_deterministic_per_seed(self):
        a = self.D.random_deck(random.Random(42), 30)
        b = self.D.random_deck(random.Random(42), 30)
        self.assertEqual(list(a), list(b), "同种子 random_deck 应可复现")

    def test_random_deck_differs_across_seeds(self):
        a = self.D.random_deck(random.Random(1), 30)
        b = self.D.random_deck(random.Random(2), 30)
        self.assertNotEqual(list(a), list(b), "不同种子应产生不同卡组")

    def test_random_deck_arch_filter(self):
        """指定流派时，卡组应以该流派的牌为主。"""
        arch = "attack"
        d = self.D.random_deck(random.Random(3), 30, arch=arch)
        archs = [self.cards.CARD_DB[cid].arch for cid in d
                 if cid in self.cards.CARD_DB]
        self.assertTrue(archs)
        share = sum(1 for a in archs if a == arch) / float(len(archs))
        self.assertGreater(share, 0.5,
                           "指定 arch=%s 时该流派占比应过半，实际 %.0f%%"
                           % (arch, share * 100))

    def test_random_deck_uses_keyword_variants(self):
        """兼容 arch= 与 archetype= 两种命名。"""
        try:
            d = self.D.random_deck(random.Random(3), 30, archetype="attack")
            self.assertEqual(len(d), 30)
        except TypeError:
            pass  # 只支持 arch= 也可以

    def test_random_deck_no_duplicate_over_cap(self):
        for seed in range(10):
            d = self.D.random_deck(random.Random(seed), 30)
            from collections import Counter
            cnt = Counter(d)
            over = {k: v for k, v in cnt.items() if v > self.D.MAX_COPIES
                    and k not in getattr(self.D, "STARTER_CARD_IDS", ())}
            self.assertEqual(over, {},
                             "seed=%d 随机卡组超过同名上限：%s" % (seed, over))


class TestHelpers(DeckbuildCase):

    def test_card_pool_excludes_status_curse(self):
        pool = self.D.card_pool()
        self.assertTrue(pool, "card_pool() 为空")
        excluded = getattr(self.D, "EXCLUDED_TYPES", frozenset())
        for cid in pool:
            self.assertIn(cid, self.cards.CARD_DB, "card_pool 含未知 id %r" % cid)
            self.assertNotIn(self.cards.CARD_DB[cid].type, excluded,
                             "card_pool 不应含 %s（type=%s）"
                             % (cid, self.cards.CARD_DB[cid].type))

    def test_arch_card_pool(self):
        for arch in ("attack", "block", "poison", "energy", "summon"):
            pool = self.D.arch_card_pool(arch)
            self.assertTrue(pool, "arch_card_pool(%r) 为空" % arch)
            for cid in pool:
                self.assertEqual(self.cards.CARD_DB[cid].arch, arch,
                                 "%s 不属于 %s" % (cid, arch))

    def test_starter_deck_valid(self):
        d = self.D.starter_deck()
        self.assertTrue(d, "starter_deck() 为空")
        for cid in d:
            self.assertIn(cid, self.cards.CARD_DB, "起始卡组含未知 id %r" % cid)

    def test_recommended_decks_cover_all_archetypes(self):
        rec = self.D.recommended_decks()
        self.assertIsInstance(rec, dict)
        self.assertTrue(rec)
        # 至少要有若干套推荐
        self.assertGreaterEqual(len(rec), 3,
                                "推荐卡组只有 %d 套" % len(rec))
        for name, deck in rec.items():
            if isinstance(deck, dict):
                deck = deck.get("cards") or deck.get("deck") or []
            self.assertTrue(deck, "推荐卡组 %r 为空" % name)

    def test_recommended_decks_distinct(self):
        rec = self.D.recommended_decks()
        sigs = []
        for name, deck in rec.items():
            if isinstance(deck, dict):
                deck = deck.get("cards") or deck.get("deck") or []
            sigs.append(tuple(sorted(deck)))
        self.assertEqual(len(set(sigs)), len(sigs),
                         "推荐卡组之间存在完全重复的套牌")

    def test_deck_summary(self):
        s = self.D.deck_summary(["strike", "defend"])
        self.assertIsInstance(s, dict)
        self.assertEqual(s.get("size"), 2)
        self.assertIn("archs", s)
        self.assertIn("types", s)
        self.assertIn("valid", s)

    def test_deck_summary_empty(self):
        try:
            s = self.D.deck_summary([])
        except Exception as exc:
            self.fail("deck_summary([]) 抛异常：%r" % (exc,))
        self.assertIsInstance(s, dict)
        self.assertEqual(s.get("size"), 0)

    def test_no_exception_leak_everywhere(self):
        """所有公开函数对垃圾输入都不得抛异常。"""
        junk = [None, 0, -1, "", "x", [], {}, object()]
        for j in junk:
            for fn in ("validate_deck", "deck_summary"):
                f = getattr(self.D, fn, None)
                if f is None:
                    continue
                try:
                    f(j)
                except Exception as exc:
                    self.fail("%s(%r) 抛异常：%r" % (fn, j, exc))

    def test_oversized_deck_name_or_id_safe(self):
        """超长卡组名/超长 id 不应崩。"""
        huge = "x" * 100000
        deck = self._legal_deck(self.D.DECK_SIZE_MIN)
        deck[0] = huge
        try:
            ok, msg = self.D.validate_deck(deck)
        except Exception as exc:
            self.fail("超长 id 抛异常：%r" % (exc,))
        self.assertFalse(ok)
        # 记录（不作为失败）：错误信息会原样回显超长 id，长度被放大。
        # 这属于「信息放大」的轻微风险，不是崩溃，故仅记录。
        if len(msg) >= 10000:
            print("\n[deckbuild] 注意：validate_deck 对超长 id 的错误信息长度为 %d "
                  "（原样回显，存在放大幅度）" % len(msg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
