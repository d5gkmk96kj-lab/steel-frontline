#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面插图构图测试（纯数据，不需要 Qt）。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import cardart as CA  # noqa: E402
from core.cards import CARD_DB  # noqa: E402


class TestCompose(unittest.TestCase):

    def test_all_cards_compose(self):
        """199 张卡都必须能算出构图，不能抛异常。"""
        for cid, cd in CARD_DB.items():
            with self.subTest(card=cid):
                comp = CA.compose({"def_id": cid})
                self.assertIsNotNone(comp)
                self.assertIn(comp.motif, CA.ALL_MOTIFS)
                self.assertGreaterEqual(comp.count, 1)
                self.assertLessEqual(comp.count, 4)

    def test_deterministic(self):
        """同一张卡必须永远得到同样的构图（不能随机抖）。"""
        a = CA.compose({"def_id": "strike", "arch": "attack"})
        b = CA.compose({"def_id": "strike", "arch": "attack"})
        self.assertEqual(a, b, "构图不稳定 —— 卡面会每次都不一样")

    def test_different_cards_differ(self):
        """不同卡应该有区别（否则又变回"全长一样"）。"""
        seen = set()
        for cid in list(CARD_DB)[:60]:
            cd = CARD_DB[cid]
            comp = CA.compose({"def_id": cid, "arch": cd.arch,
                               "rarity": cd.rarity, "damage": cd.damage,
                               "block": cd.block, "cost": cd.cost})
            seen.add((comp.motif, comp.count, comp.motifs, comp.band))
        self.assertGreater(len(seen), 8,
                           "只有 %d 种构图，太单调了" % len(seen))

    def test_arch_drives_motif(self):
        """流派决定主图案。"""
        for arch, (motif, _) in CA.ARCH_MOTIFS.items():
            comp = CA.compose({"def_id": "x-%s" % arch, "arch": arch})
            self.assertEqual(comp.motif, motif, "流派 %s 的主图案不对" % arch)

    def test_unknown_arch_falls_back(self):
        comp = CA.compose({"def_id": "x", "arch": "nonsense",
                           "type": "attack"})
        self.assertEqual(comp.motif, "rifle")

    def test_rarity_drives_band_and_density(self):
        lo = CA.compose({"def_id": "a", "arch": "attack", "rarity": "common"})
        hi = CA.compose({"def_id": "b", "arch": "attack", "rarity": "legendary"})
        self.assertEqual(lo.band, "steel")
        self.assertEqual(hi.band, "crimson")
        self.assertGreater(hi.density, lo.density)

    def test_count_scales_with_numbers(self):
        weak = CA.compose({"def_id": "a", "arch": "attack", "damage": 2})
        strong = CA.compose({"def_id": "b", "arch": "attack", "damage": 12})
        self.assertEqual(weak.count, 1)
        self.assertEqual(strong.count, 4)

    def test_bad_numbers_do_not_crash(self):
        for bad in ({"damage": "lots"}, {"block": None}, {"cost": []}):
            d = {"def_id": "x", "arch": "attack"}
            d.update(bad)
            with self.subTest(bad=bad):
                comp = CA.compose(d)
                self.assertGreaterEqual(comp.count, 1)

    def test_all_motifs_registered(self):
        """每个母题都要在 ALL_MOTIFS 里（渲染器找不到会静默跳过）。"""
        for arch, (motif, extras) in CA.ARCH_MOTIFS.items():
            self.assertIn(motif, CA.ALL_MOTIFS)
            for e in extras:
                self.assertIn(e, CA.ALL_MOTIFS)

    def test_seed_stable(self):
        self.assertEqual(CA._seed_of("strike"), CA._seed_of("strike"))
        self.assertNotEqual(CA._seed_of("strike"), CA._seed_of("defend"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
