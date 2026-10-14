# -*- coding: utf-8 -*-
"""兑换码 / 作弊码系统测试。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import cheats as CH          # noqa: E402
from core import cards as C            # noqa: E402
from core import engine as E           # noqa: E402
from core import run as R              # noqa: E402


def fresh(seed=7):
    r = R.RunState()
    r.new_run(seed=seed, ascension=0)
    b = E.make_battle(r, r.roll_encounter("normal"))
    return r, b


class TestCheatLookup(unittest.TestCase):
    """兑换码查找：大小写/下划线/空格不敏感。"""

    def test_all_seven_codes_present(self):
        codes = {d.code for d in CH.all_codes()}
        for want in ("it", "research all", "ic", "debug_nuke",
                     "god_mode", "annex all", "manpower"):
            self.assertIn(want, codes, "缺少兑换码 %r" % want)

    def test_lookup_is_flexible(self):
        cases = {
            "it": "it",
            "IT": "it",
            "research all": "research all",
            "research_all": "research all",
            "ResearchAll": "research all",
            "debug_nuke": "debug_nuke",
            "debug nuke": "debug_nuke",
            "god_mode": "god_mode",
            "godmode": "god_mode",
            "annex all": "annex all",
            "manpower": "manpower",
        }
        for text, want in cases.items():
            d = CH.find(text)
            self.assertIsNotNone(d, "%r 应能解析" % text)
            self.assertEqual(d.code, want, "%r 应解析为 %r" % (text, want))

    def test_unknown_code_returns_none(self):
        self.assertIsNone(CH.find("definitely_not_a_code"))
        self.assertIsNone(CH.find(""))


class TestCheatRedeem(unittest.TestCase):
    """每个兑换码都要真实生效。"""

    def test_it_refills_supply_and_hand(self):
        r, b = fresh()
        b.player.energy = 0
        b.player.hand = b.player.hand[:2]
        ok, msg = CH.CheatRegistry().redeem("it", run=r, battle=b)
        self.assertTrue(ok, msg)
        self.assertEqual(b.player.energy, b.player.max_energy)
        self.assertGreaterEqual(len(b.player.hand), 2)

    def test_research_all_unlocks_everything(self):
        r, b = fresh()
        meta = R.MetaProgress()
        ok, msg = CH.CheatRegistry().redeem("research all", run=r, battle=b,
                                            meta=meta)
        self.assertTrue(ok, msg)
        # 牌组里应含几乎所有非 status/curse 卡
        want = {c.id for c in C.CARD_DB.values()
                if c.type not in ("status", "curse")
                and not c.id.startswith("cheat_")}
        have = {c.def_id for c in r.deck}
        missing = want - have
        self.assertEqual(missing, set(), "研究全解锁后仍缺卡：%r" % list(missing)[:5])
        # 图鉴应填满
        self.assertGreaterEqual(len(meta.seen_cards), len(C.CARD_DB))

    def test_ic_builds_defense_instantly(self):
        r, b = fresh()
        b.player.block = 0
        ok, msg = CH.CheatRegistry().redeem("ic", run=r, battle=b)
        self.assertTrue(ok, msg)
        self.assertGreater(b.player.block, 500)
        self.assertGreater(b.player.get_buff(E.BUFF_THORNS), 0)

    def test_debug_nuke_grants_kill_card(self):
        r, b = fresh()
        ok, msg = CH.CheatRegistry().redeem("debug_nuke", run=r, battle=b)
        self.assertTrue(ok, msg)
        ids = [c.def_id for c in b.player.hand]
        self.assertIn(CH.CHEAT_CARD_STRAT_BOMB, ids, "战略轰炸应进入手牌")

    def test_nuke_card_actually_kills_all(self):
        r, b = fresh()
        CH.CheatRegistry().redeem("debug_nuke", run=r, battle=b)
        card = [c for c in b.player.hand
                if c.def_id == CH.CHEAT_CARD_STRAT_BOMB][0]
        self.assertTrue(b.play_card(card, None), "战略轰炸应能打出")
        self.assertEqual(b.result(), "won", "打出后应立刻获胜")
        self.assertTrue(all(not e.alive() for e in b.enemies))

    def test_god_mode_blocks_damage(self):
        r, b = fresh()
        ok, msg = CH.CheatRegistry().redeem("god_mode", run=r, battle=b)
        self.assertTrue(ok, msg)
        hp0 = b.player.hp
        b.end_turn()
        guard = 0
        while b.enemy_step() and guard < 40:
            guard += 1
        self.assertGreaterEqual(b.player.hp, hp0,
                                "上帝模式期间不应掉血（%d -> %d）"
                                % (hp0, b.player.hp))

    def test_annex_all_wins_battle(self):
        r, b = fresh()
        ok, msg = CH.CheatRegistry().redeem("annex all", run=r, battle=b)
        self.assertTrue(ok, msg)
        self.assertEqual(b.result(), "won")
        self.assertTrue(all(not e.alive() for e in b.enemies))

    def test_manpower_adds_hp_and_capacity(self):
        r, b = fresh()
        max0, hp0 = r.max_hp, r.hp
        ok, msg = CH.CheatRegistry().redeem("manpower", run=r, battle=b)
        self.assertTrue(ok, msg)
        self.assertEqual(r.max_hp, max0 + 50, "总部耐久上限应 +50")
        self.assertEqual(r.hp, min(r.max_hp, hp0 + 50))
        self.assertGreaterEqual(len(b.player.minions), 1, "应召唤增援单位")

    def test_all_codes_redeem_without_exception(self):
        """遍历全部码，任何环境下都不得抛异常。"""
        for d in CH.all_codes():
            r, b = fresh()
            meta = R.MetaProgress()
            ok, msg = CH.CheatRegistry().redeem(d.code, run=r, battle=b,
                                                meta=meta)
            self.assertIsInstance(ok, bool)
            self.assertIsInstance(msg, str)
            self.assertTrue(msg, "%s 应给出提示文本" % d.code)


class TestCheatGuards(unittest.TestCase):
    """边界与防误用。"""

    def test_invalid_code_is_rejected(self):
        r, b = fresh()
        ok, msg = CH.CheatRegistry().redeem("nope_nope", run=r, battle=b)
        self.assertFalse(ok)
        self.assertIn("无效", msg)

    def test_battle_only_codes_rejected_outside_battle(self):
        r, _ = fresh()
        for code in ("god_mode", "annex all", "ic", "it"):
            ok, msg = CH.CheatRegistry().redeem(code, run=r, battle=None)
            self.assertFalse(ok, "%s 在无战斗时应被拒绝" % code)
            self.assertIn("战斗", msg)

    def test_once_codes_rejected_on_second_use(self):
        r, b = fresh()
        reg = CH.CheatRegistry()
        ok1, _ = reg.redeem("annex all", run=r, battle=b)
        self.assertTrue(ok1)
        r2, b2 = fresh()
        ok2, msg2 = reg.redeem("annex all", run=r2, battle=b2)
        self.assertFalse(ok2, "once 码第二次应被拒绝")
        self.assertIn("一次", msg2)

    def test_registry_records_history(self):
        r, b = fresh()
        reg = CH.CheatRegistry()
        reg.redeem("manpower", run=r, battle=b)
        self.assertTrue(reg.has_used("manpower"))
        self.assertGreater(len(reg.log), 0)

    def test_registry_roundtrip(self):
        reg = CH.CheatRegistry()
        reg.used["manpower"] = 3
        reg.log.append("x")
        d = reg.to_dict()
        reg2 = CH.CheatRegistry.from_dict(d)
        self.assertEqual(reg2.used.get("manpower"), 3)
        self.assertEqual(reg2.log, ["x"])

    def test_registry_survives_garbage_dict(self):
        reg = CH.CheatRegistry.from_dict({"used": "not a dict", "log": 5})
        self.assertIsInstance(reg.used, dict)

    def test_cheat_cards_are_real_carddefs(self):
        """注入的作弊卡必须是合法 CardDef，能被 snapshot/UI 正常读取。"""
        CH._ensure_cheat_cards()
        for cid in (CH.CHEAT_CARD_STRAT_BOMB, CH.CHEAT_CARD_GOD_SHIELD,
                    CH.CHEAT_CARD_MANPOWER):
            self.assertIn(cid, C.CARD_DB, "%s 应已注入 CARD_DB" % cid)
            cd = C.CARD_DB[cid]
            self.assertIsInstance(cd, C.CardDef)
            self.assertTrue(cd.name)
            self.assertIsNotNone(cd.effect)

    def test_cheat_cards_render_in_snapshot(self):
        r, b = fresh()
        CH.CheatRegistry().redeem("debug_nuke", run=r, battle=b)
        snap = b.snapshot()
        bomb = [c for c in snap["hand"]
                if c["def_id"] == CH.CHEAT_CARD_STRAT_BOMB]
        self.assertEqual(len(bomb), 1)
        self.assertIsInstance(bomb[0]["playable"], bool)

    def test_game_still_playable_after_cheats(self):
        """连续兑换后引擎仍能正常推进回合。"""
        r, b = fresh()
        reg = CH.CheatRegistry()
        for code in ("it", "debug_nuke", "manpower"):
            reg.redeem(code, run=r, battle=b)
        b.end_turn()
        guard = 0
        while b.enemy_step() and guard < 50:
            guard += 1
        self.assertIn(b.phase, ("player", "won", "lost"))

    def test_cheat_does_not_corrupt_deck_identity(self):
        """research all 不应产生重复 uid 冲突。"""
        r, b = fresh()
        CH.CheatRegistry().redeem("research all", run=r, battle=b)
        uids = [c.uid for c in r.deck]
        self.assertEqual(len(uids), len(set(uids)), "牌组 uid 必须唯一")


if __name__ == "__main__":
    unittest.main(verbosity=2)
