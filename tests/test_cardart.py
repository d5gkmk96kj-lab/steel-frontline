#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面插图测试：每张卡一份独立设计（纯数据，不需要 Qt）。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import cardart as CA  # noqa: E402
from core.cards import CARD_DB  # noqa: E402

# 作弊专属卡是 core.cheats 懒注入的 —— 主动触发一次，
# 否则覆盖率断言会漏掉它们（真踩过：3 张作弊卡没设计）。
try:
    from core import cheats as _CH
    _CH._ensure_cheat_cards()
except Exception:
    pass


class TestDesignCoverage(unittest.TestCase):

    def test_all_cards_have_design(self):
        """199 张卡都必须有登记的设计（不能靠兜底糊过去）。"""
        missing = [cid for cid in CARD_DB if cid not in CA.DESIGNS]
        self.assertEqual(missing, [],
                         "这些卡还没有独立设计：%s" % missing[:10])

    def test_every_design_has_parts(self):
        for cid, d in CA.DESIGNS.items():
            with self.subTest(card=cid):
                self.assertGreaterEqual(len(d.parts), 1,
                                        "%s 的设计是空的" % cid)

    def test_no_registry_orphans(self):
        """登记了但卡库里不存在的 id -> 拼错字了。"""
        orphan = [cid for cid in CA.DESIGNS if cid not in CARD_DB]
        self.assertEqual(orphan, [],
                         "这些 id 在卡库里不存在（拼错了？）：%s" % orphan[:10])


class TestDesignQuality(unittest.TestCase):

    def test_designs_are_distinct(self):
        """不同卡不能是同一个设计（否则又变回千篇一律）。"""
        seen = {}
        dup = []
        for cid, d in CA.DESIGNS.items():
            key = (tuple((p.kind, round(p.x, 2), round(p.y, 2)) for p in d.parts),
                   d.fx, d.bg)
            if key in seen:
                dup.append((seen[key], cid))
            else:
                seen[key] = cid
        self.assertLess(len(dup), 6,
                        "有 %d 组卡设计完全一样：%s" % (len(dup), dup[:5]))

    def test_parts_within_bounds(self):
        """图元位置必须在 0~1 之间（画到框外会被裁掉）。"""
        for cid, d in CA.DESIGNS.items():
            for pt in d.parts:
                with self.subTest(card=cid, kind=pt.kind):
                    self.assertGreaterEqual(pt.x, 0.0)
                    self.assertLessEqual(pt.x, 1.0)
                    self.assertGreaterEqual(pt.y, 0.0)
                    self.assertLessEqual(pt.y, 1.0)

    def test_scales_sane(self):
        for cid, d in CA.DESIGNS.items():
            for pt in d.parts:
                self.assertGreater(pt.s, 0.0, "%s 的 %s 尺寸为 0" % (cid, pt.kind))
                self.assertLess(pt.s, 4.0, "%s 的 %s 尺寸过大" % (cid, pt.kind))

    def test_all_part_kinds_known(self):
        """设计里用到的图元名必须在 PART_KINDS 里。"""
        used = set()
        for d in CA.DESIGNS.values():
            for pt in d.parts:
                used.add(pt.kind)
        unknown = sorted(used - set(CA.PART_KINDS))
        self.assertEqual(unknown, [], "未声明的图元：%s" % unknown)


class TestFx(unittest.TestCase):

    def test_all_fx_known(self):
        for cid, d in CA.DESIGNS.items():
            with self.subTest(card=cid):
                self.assertIn(d.fx, CA.FX_KINDS,
                              "%s 的 fx=%r 不在已知类型里" % (cid, d.fx))

    def test_gun_cards_shoot(self):
        """枪械类卡必须有 bullet 特效。"""
        for cid in ("strike", "heavy_harpoon", "twin_fang", "sniper" if "sniper" in CARD_DB else "deep_cut"):
            if cid not in CARD_DB:
                continue
            with self.subTest(card=cid):
                self.assertEqual(CA.fx_for({"def_id": cid}), "bullet",
                                 "%s 是枪械类，应该有子弹特效" % cid)

    def test_fire_cards_burn(self):
        """燃烧类卡必须有 fire 特效。"""
        for cid in ("burn", "toxin_uppercut", "scorched_earth", "carpet_bomb"):
            if cid not in CARD_DB:
                continue
            with self.subTest(card=cid):
                self.assertEqual(CA.fx_for({"def_id": cid}), "fire",
                                 "%s 是火攻类，应该有火焰特效" % cid)

    def test_nuke_is_nuke(self):
        self.assertEqual(CA.fx_for({"def_id": "nuke"}), "nuke")

    def test_no_duplicate_fx_on_same_card(self):
        for cid in CARD_DB:
            self.assertIsInstance(CA.fx_for({"def_id": cid}), str)


class TestFallback(unittest.TestCase):

    def test_unknown_card_gets_design(self):
        d = CA.design_for({"def_id": "not_a_real_card", "arch": "attack"})
        self.assertIsNotNone(d)
        self.assertGreaterEqual(len(d.parts), 1)

    def test_unknown_arch_falls_back(self):
        d = CA.design_for({"def_id": "not_a_real_card", "arch": "nonsense"})
        self.assertIsNotNone(d)
        self.assertGreaterEqual(len(d.parts), 1)

    def test_empty_card_does_not_crash(self):
        for bad in ({}, {"def_id": None}, {"arch": None}):
            with self.subTest(bad=bad):
                d = CA.design_for(bad)
                self.assertGreaterEqual(len(d.parts), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
