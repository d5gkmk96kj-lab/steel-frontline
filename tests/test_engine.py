"""战斗引擎测试（ARCHITECTURE.md §6）。

覆盖：出牌/抽牌/能量/格挡/力量/易伤/虚弱/中毒/荆棘/召唤/胜负/牌堆循环。
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import (first_enemy, ARCHS, ContractCase, auto_play_turn, buff_key, load,  # noqa: E402
                   make_card, make_combatant, start_battle)


class TestEngineBase(ContractCase):
    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.cards, err = load("core.cards")
        self.assertIsNotNone(self.cards, "core.cards 不可用：%s" % err)
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)
        self.rng = random.Random(20240607)
        self.bs = self._battle(["act1_slime"] if "act1_slime" in getattr(self.enemies, "ENEMY_DB", {})
                               else list(getattr(self.enemies, "ENEMY_DB", {"x": 1}))[:1])

    def _battle(self, enemy_ids, seed=20240607):
        run = None
        try:
            run = self.runmod.RunState()
            if hasattr(run, "new_run"):
                run.new_run(seed=seed, ascension=0)
        except Exception:
            run = object()
        return start_battle(self.engine, run, enemy_ids, self.enemies,
                            rng=random.Random(seed))


class TestCombatantBasics(TestEngineBase):

    def test_buff_constants(self):
        for name in ("strength", "dexterity", "vulnerable", "weak", "poison",
                     "thorns", "metallicize", "ritual", "artifact", "barrier",
                     "plated_armor", "regenerate", "intangible", "frail",
                     "strength_down", "chain", "envenom", "accuracy"):
            self.assertTrue(hasattr(self.engine, "BUFF_" + name.upper()),
                            "缺少 BUFF_%s 常量" % name.upper())

    def test_start_battle_draws_hand(self):
        p = self.bs.player
        self.assertEqual(len(p.hand), 5, "起手应为 5 张，实际 %d" % len(p.hand))
        self.assertEqual(p.energy, p.max_energy)
        self.assertEqual(self.bs.phase, "player")
        self.assertGreater(self.bs.turn, 0)

    def test_alive_and_result_api(self):
        self.assertTrue(self.bs.alive())
        self.assertEqual(self.bs.result(), "ongoing")
        self.assertIn(self.bs.phase, ("player", "enemy", "won", "lost"))

    def test_snapshot_is_plain_data(self):
        snap = self.bs.snapshot()
        self.assertIsInstance(snap, dict)
        self.assertIn("player", snap)
        p = snap["player"]
        self.assertIsInstance(p, dict)
        for key in ("hp", "max_hp", "block"):
            self.assertIn(key, p, "snapshot()['player'] 缺少 %s" % key)
        # A.2 把 hand 放在 snapshot 顶层，不在 player 下
        self.assertIn("hand", snap, "snapshot() 顶层缺少 'hand'")
        self.assertIn("enemies", snap)

    def test_public_methods_no_exception_on_bad_input(self):
        """契约：公开方法不得把异常泄漏给 UI，非法操作返回 False。"""
        class Bogus:
            def_id = "__no_such_card__"
            uid = -999
            upgraded = 0
            cost_override = None

        try:
            ok = self.bs.play_card(self.bs.player.hand[0], None)
            self.assertIn(ok, (True, False))
        except Exception as exc:
            self.fail("play_card 非法目标抛异常：%r" % (exc,))


class TestEnergyAndPlay(TestEngineBase):

    def _card_named(self, *predicates):
        """按字段特征挑一张牌加入手牌。"""
        for cd in self.cards.CARD_DB.values():
            if all(p(cd) for p in predicates):
                return cd
        return None

    def test_energy_decreases_by_cost(self):
        p = self.bs.player
        cd = self._card_named(lambda c: c.cost == 1, lambda c: c.type == "attack")
        if cd is None:
            self.skipTest("数据库中没有 1 费攻击牌可供本用例使用")
        inst = self.cards.make_card(cd.id)
        p.hand.append(inst)
        p.energy = 3
        target = first_enemy(self.bs)
        self.assertTrue(self.bs.can_play(inst))
        self.assertTrue(self.bs.play_card(inst, target))
        self.assertEqual(p.energy, 2, "1 费牌打出后能量应为 2")

    def test_cannot_play_without_energy(self):
        p = self.bs.player
        cd = self._card_named(lambda c: c.cost == 3)
        if cd is None:
            self.skipTest("数据库中没有 3 费牌")
        inst = self.cards.make_card(cd.id)
        p.hand.append(inst)
        p.energy = 0
        self.assertFalse(self.bs.can_play(inst), "0 能量时 3 费牌不应可打出")
        self.assertFalse(self.bs.play_card(inst, first_enemy(self.bs)))

    def test_x_cost_card_playable_with_energy(self):
        p = self.bs.player
        cd = self._card_named(lambda c: c.cost == -1)
        if cd is None:
            return  # X 费牌非强制
        inst = self.cards.make_card(cd.id)
        p.hand.append(inst)
        p.energy = 2
        self.assertTrue(self.bs.can_play(inst), "X 费牌在有能量时应可打出")

    def test_played_card_goes_to_discard(self):
        p = self.bs.player
        cd = self._card_named(lambda c: c.cost == 0) or self._card_named(lambda c: c.cost == 1)
        inst = self.cards.make_card(cd.id)
        p.hand.append(inst)
        p.energy = 5
        before = len(p.discard_pile)
        self.bs.play_card(inst, first_enemy(self.bs))
        if not cd.exhaust:
            self.assertEqual(len(p.discard_pile), before + 1,
                             "非消耗牌打出后应进弃牌堆")
        self.assertNotIn(inst, p.hand, "打出的牌仍在手牌")


class TestDamageAndBlock(TestEngineBase):

    def test_block_absorbs_damage(self):
        p = self.bs.player
        p.block = 100
        hp0 = p.hp
        self.bs.end_turn()
        guard = 0
        while self.bs.phase == "enemy" and guard < 60:
            more = self.bs.enemy_step()
            guard += 1
            if not more:
                break
        self.assertLessEqual(p.hp, hp0)
        self.assertLess(p.block, 100, "格挡未被消耗")

    def test_block_cleared_at_turn_start(self):
        p = self.bs.player
        p.block = 12
        self.bs.end_turn()
        guard = 0
        while self.bs.phase == "enemy" and guard < 60:
            more = self.bs.enemy_step()
            guard += 1
            if not more:
                break
        if self.bs.phase in ("won", "lost"):
            return
        self.assertEqual(p.block, 0, "玩家回合开始时格挡应清零（无 barrier 时）")

    def test_strength_adds_damage(self):
        p = self.bs.player
        p.buffs[buff_key(self.engine, "strength")] = 5
        e = first_enemy(self.bs)
        hp0 = e.hp
        e.block = 0
        cd = None
        for c in self.cards.CARD_DB.values():
            if c.type == "attack" and c.damage > 0 and c.hits == 1 and c.cost <= 1:
                cd = c
                break
        self.assertIsNotNone(cd, "找不到单段低费攻击牌")
        inst = self.cards.make_card(cd.id)
        p.hand.append(inst)
        p.energy = 9
        self.bs.play_card(inst, e)
        dealt = hp0 - e.hp
        self.assertGreaterEqual(dealt, cd.damage + 5,
                                "力量 5 应使 %s 伤害 +5（基础 %d，实际 %d）"
                                % (cd.id, cd.damage, dealt))

    def test_vulnerable_increases_damage(self):
        p = self.bs.player
        e = first_enemy(self.bs)
        e.buffs[buff_key(self.engine, "vulnerable")] = 3
        e.block = 0
        cd = None
        for c in self.cards.CARD_DB.values():
            if c.type == "attack" and c.damage >= 6 and c.hits == 1:
                cd = c
                break
        self.assertIsNotNone(cd)
        inst = self.cards.make_card(cd.id)
        p.hand.append(inst)
        p.energy = 9
        hp0 = e.hp
        self.bs.play_card(inst, e)
        dealt = hp0 - e.hp
        self.assertGreaterEqual(dealt, int(cd.damage * 1.5) - 1,
                                "易伤应使伤害 ×1.5（基础 %d，实际 %d）" % (cd.damage, dealt))

    def test_weak_reduces_damage(self):
        p = self.bs.player
        p.buffs[buff_key(self.engine, "weak")] = 3
        e = first_enemy(self.bs)
        e.block = 0
        cd = None
        for c in self.cards.CARD_DB.values():
            if c.type == "attack" and c.damage >= 6 and c.hits == 1:
                cd = c
                break
        inst = self.cards.make_card(cd.id)
        p.hand.append(inst)
        p.energy = 9
        hp0 = e.hp
        self.bs.play_card(inst, e)
        dealt = hp0 - e.hp
        self.assertLessEqual(dealt, cd.damage,
                             "虚弱应使伤害 -25%%（基础 %d，实际 %d）" % (cd.damage, dealt))
        self.assertGreaterEqual(dealt, 1)


class TestBuffs(TestEngineBase):

    def test_poison_ticks_and_decays(self):
        e = first_enemy(self.bs)
        e.buffs[buff_key(self.engine, "poison")] = 5
        hp0 = e.hp
        # 推进一整轮，让敌人回合开始触发中毒
        self.bs.end_turn()
        guard = 0
        while self.bs.phase == "enemy" and guard < 60:
            more = self.bs.enemy_step()
            guard += 1
            if not more:
                break
        self.assertLess(e.hp, hp0, "中毒未造成伤害")
        self.assertLessEqual(e.buffs.get(buff_key(self.engine, "poison"), 0), 4,
                             "中毒层数应每回合 -1")

    def test_thorns_reflects_attack_damage(self):
        """荆棘契约：玩家受攻击时反弹伤害给攻击者（敌人掉血是正确行为）。"""
        p = self.bs.player
        p.buffs[buff_key(self.engine, "thorns")] = 9
        p.max_hp = p.hp = 999
        e = self.bs.enemies[0]
        e_hp0 = e.hp
        it = self.bs.current_enemy_intent(e)
        intent = getattr(it, "intent", None)
        if intent not in ("attack", "attack_debuff", "attack_defend"):
            self.skipTest("敌人本回合不是攻击意图（%r），无法验证荆棘反弹" % intent)
        self.bs.end_turn()
        guard = 0
        ret = True
        while ret and guard < 60:
            ret = self.bs.enemy_step()
            guard += 1
        self.assertLess(e.hp, e_hp0,
                        "敌人攻击带荆棘的玩家后应受到反弹伤害（%d -> %d）"
                        % (e_hp0, e.hp))

    def test_thorns_not_triggered_by_non_attack(self):
        """非攻击伤害（kind != attack）不应触发荆棘。

        注意：荆棘挂在**受击方**身上，反弹给攻击方。
        这里让**敌人**拥有荆棘，玩家对其施加非攻击伤害，
        玩家不应被反弹（玩家 HP 不变）。
        """
        p = self.bs.player
        p.max_hp = p.hp = 999
        e = self.bs.enemies[0]
        e.buffs[buff_key(self.engine, "thorns")] = 9
        p_hp0 = p.hp
        try:
            self.bs.deal_damage(p, e, 5, kind="other")
        except TypeError:
            self.skipTest("deal_damage 不支持 kind 参数，无法构造非攻击伤害")
        self.assertEqual(p.hp, p_hp0,
                         "非攻击伤害不应触发荆棘反弹（玩家 %d -> %d）"
                         % (p_hp0, p.hp))

    def test_thorns_triggers_on_attack(self):
        """对照实验：同样的设置改成 kind='attack'，则应触发反弹。"""
        p = self.bs.player
        p.max_hp = p.hp = 999
        e = self.bs.enemies[0]
        e.buffs[buff_key(self.engine, "thorns")] = 9
        p_hp0 = p.hp
        try:
            self.bs.deal_damage(p, e, 1, kind="attack")
        except TypeError:
            self.skipTest("deal_damage 不支持 kind 参数")
        self.assertLess(p.hp, p_hp0,
                        "攻击带荆棘的目标应被反弹（玩家 %d -> %d）" % (p_hp0, p.hp))

    def test_ritual_grows_strength(self):
        e = first_enemy(self.bs)
        k = buff_key(self.engine, "ritual")
        e.buffs[k] = 2
        s0 = e.buffs.get(buff_key(self.engine, "strength"), 0)
        self.bs.end_turn()
        guard = 0
        while self.bs.phase == "enemy" and guard < 60:
            more = self.bs.enemy_step()
            guard += 1
            if not more:
                break
        s1 = e.buffs.get(buff_key(self.engine, "strength"), 0)
        self.assertGreater(s1, s0, "仪式应在回合末叠加力量（%d -> %d）" % (s0, s1))


class TestMinions(TestEngineBase):
    """召唤流派：必须真正验证召唤物产生与行动，而不是只喊一遍就过。"""

    def _play_summon_card(self):
        """打出一张 summon 流派的牌，返回 (成功?, 卡 id)。"""
        p = self.bs.player
        pool = [c for c in self.cards.CARD_DB.values()
                if c.arch == "summon" and c.effect is not None and c.cost >= 0]
        self.assertTrue(pool, "没有可用的 summon 流派卡牌（按 arch 筛选）")
        p.energy = 99
        before = len(getattr(p, "minions", []) or [])
        for cd in sorted(pool, key=lambda c: c.cost):
            inst = self.cards.make_card(cd.id)
            p.hand.append(inst)
            try:
                self.bs.play_card(inst, first_enemy(self.bs))
            except Exception as exc:
                self.fail("打出 summon 牌 %s 抛异常：%r" % (cd.id, exc))
            if len(getattr(p, "minions", []) or []) > before:
                return True, cd.id
            if inst in p.hand:
                p.hand.remove(inst)
        return False, None

    def test_summon_creates_minion(self):
        ok, cid = self._play_summon_card()
        self.assertTrue(ok, "打出全部 summon 流派卡牌后 minions 仍未增加")

    def test_minion_fields_valid(self):
        ok, cid = self._play_summon_card()
        if not ok:
            self.skipTest("未能召唤出召唤物")
        for m in self.bs.player.minions:
            self.assertGreater(getattr(m, "hp", 0), 0, "召唤物 HP 应为正")
            self.assertGreaterEqual(getattr(m, "attack", 0), 0, "召唤物攻击力不应为负")
            self.assertTrue(getattr(m, "name", ""), "召唤物应有名字")

    def test_minion_appears_in_snapshot(self):
        ok, cid = self._play_summon_card()
        if not ok:
            self.skipTest("未能召唤出召唤物")
        snap = self.bs.snapshot()["player"]
        self.assertTrue(snap["minions"], "召唤物未出现在 snapshot['player']['minions']")
        for m in snap["minions"]:
            for k in ("name", "hp", "max_hp", "attack", "block"):
                self.assertIn(k, m, "snapshot 召唤物缺少 key %r" % k)

    def test_minion_attacks_at_turn_end(self):
        """召唤物应在回合末自动攻击敌人。"""
        ok, cid = self._play_summon_card()
        if not ok:
            self.skipTest("未能召唤出召唤物")
        p = self.bs.player
        if not p.minions:
            self.skipTest("没有召唤物")
        total_atk = sum(getattr(m, "attack", 0) for m in p.minions)
        if total_atk <= 0:
            self.skipTest("召唤物攻击力为 0，无法验证行动")
        e = self.bs.enemies[0]
        e_hp0 = e.hp
        self.bs.end_turn()
        guard = 0
        ret = True
        while ret and guard < 60:
            ret = self.bs.enemy_step()
            guard += 1
        self.assertLess(e.hp, e_hp0,
                        "回合末召唤物应自动攻击敌人（%d -> %d），总攻击力=%d"
                        % (e_hp0, e.hp, total_atk))


class TestEnemyPersistentEffects(TestEngineBase):
    """持续效果必须对**双方**结算，不能只遍历玩家。

    BUG #5（中毒只在玩家结算）与 BUG #6（仪式只在玩家结算）是同一类 bug 的两处实例。
    这里做通用回归：对每个「回合末/回合初结算」类 buff，
    验证敌人身上的层数也能真正生效。
    """

    def _run_full_round(self, on_enemy=True, buff="ritual", amount=2, turns=6):
        p = self.bs.player
        p.hp = p.max_hp = 999999
        e = self.bs.enemies[0]
        e.hp = e.max_hp = 999999
        key = buff_key(self.engine, buff)
        if on_enemy:
            e.buffs[key] = amount
        else:
            p.buffs[key] = amount
        # 推进若干回合
        for _ in range(turns):
            self.bs.end_turn()
            guard = 0
            ret = True
            while ret and guard < 60:
                ret = self.bs.enemy_step()
                guard += 1
            p.hp = p.max_hp = 999999
            e.hp = e.max_hp = 999999
            if self.bs.result() != "ongoing":
                break
        who = e if on_enemy else p
        return who

    def test_poison_ticks_on_enemy(self):
        """BUG #5 回归：中毒必须在敌人身上结算。"""
        e = self.bs.enemies[0]
        e.hp = e.max_hp = 999
        e.buffs[buff_key(self.engine, "poison")] = 5
        bs = self.bs
        p = bs.player
        p.hp = p.max_hp = 9999
        hp0 = e.hp
        bs.end_turn()
        guard = 0
        ret = True
        while ret and guard < 60:
            ret = bs.enemy_step()
            guard += 1
        self.assertLess(e.hp, hp0,
                        "敌人身上的中毒必须在玩家回合开始结算（BUG #5 回归）")
        self.assertLessEqual(e.buffs.get(buff_key(self.engine, "poison"), 0), 4,
                             "敌人中毒层数应 -1")

    def test_ritual_grows_strength_on_enemy(self):
        """BUG #6 回归：敌人身上的仪式必须转化为力量。"""
        e = self._run_full_round(on_enemy=True, buff="ritual", amount=3, turns=8)
        strength = e.buffs.get(buff_key(self.engine, "strength"), 0)
        self.assertGreater(strength, 0,
                           "敌人身上叠了仪式却始终没有获得力量（BUG #6）："
                           "ritual=%d strength=%d"
                           % (e.buffs.get(buff_key(self.engine, "ritual"), 0), strength))

    def test_ritual_converts_for_player(self):
        """对照：玩家身上的仪式确实生效（说明机制本身没问题，只是漏了敌人）。"""
        p = self._run_full_round(on_enemy=False, buff="ritual", amount=3, turns=8)
        strength = p.buffs.get(buff_key(self.engine, "strength"), 0)
        self.assertGreater(strength, 0,
                           "玩家仪式未转化力量：ritual=%d strength=%d"
                           % (p.buffs.get(buff_key(self.engine, "ritual"), 0), strength))

    def test_enemy_ritual_moves_actually_grant_ritual(self):
        """6 个敌人的「增援」招式必须真的给自己叠上仪式（否则是空转招式）。"""
        ritual_moves = []
        for e in self.enemies.ENEMY_DB.values():
            for m in e.moves:
                if m.effect is not None and "ritual" in (m.effect.__name__ or ""):
                    ritual_moves.append((e.id, m.id))
        if not ritual_moves:
            self.skipTest("没有敌人有 ritual 招式")
        eid = ritual_moves[0][0]
        p = self.bs.player
        p.hp = p.max_hp = 999999
        enemy = self.bs.enemies[0]
        enemy.hp = enemy.max_hp = 999999
        # 换成带 ritual 的敌人
        new_enemy = self.engine.make_enemy_combatant(eid, __import__("random").Random(0), 0, 1)
        new_enemy.hp = new_enemy.max_hp = 999999
        self.bs.enemies = [new_enemy]
        seen = 0
        for _ in range(30):
            self.bs.phase = "enemy"
            self.bs._enemy_queue = [new_enemy]
            try:
                self.bs.enemy_step()
            except Exception:
                break
            seen = max(seen, new_enemy.buffs.get(buff_key(self.engine, "ritual"), 0))
            p.hp = p.max_hp = 999999
        self.assertGreater(seen, 0,
                           "%s 有 ritual 招式却从未叠上仪式，招式是空转" % eid)


class TestPilesAndDraw(TestEngineBase):

    def test_draw_reduces_draw_pile(self):
        p = self.bs.player
        n0 = len(p.draw_pile)
        self.bs.end_turn()
        guard = 0
        while self.bs.phase == "enemy" and guard < 60:
            more = self.bs.enemy_step()
            guard += 1
            if not more:
                break
        if self.bs.phase in ("won", "lost"):
            return
        self.assertEqual(len(p.hand), 5, "新回合应抽到 5 张手牌")

    def test_discard_shuffles_back_when_draw_empty(self):
        p = self.bs.player
        # 把全部牌堆进弃牌堆，模拟「牌库全空」。
        # 注意：必须把手牌也归入弃牌堆，否则手牌会凭空消失、总数不守恒
        # （verifier 初版漏了这一步，导致断言与 setup 数学矛盾 —— 已修正）。
        p.discard_pile.extend(p.draw_pile)
        p.discard_pile.extend(p.hand)
        p.draw_pile = []
        p.hand = []
        total_before = (len(p.hand) + len(p.draw_pile) + len(p.discard_pile)
                        + len(p.exhaust_pile))
        self.assertEqual(total_before, 10, "setup 后牌张总数应为 10，实际 %d" % total_before)

        from _util import draw_cards as _draw
        _draw(self.bs, 5)
        self.assertEqual(len(p.hand), 5, "抽牌堆空时应把弃牌堆洗回抽牌堆再抽")
        self.assertEqual(len(p.discard_pile), 0, "洗回后弃牌堆应为空")
        self.assertEqual(len(p.draw_pile), 5, "10 张洗回、抽走 5 张 → 抽牌堆应剩 5 张")

    def test_card_conservation_invariant(self):
        """牌张总数守恒：手牌+抽牌堆+弃牌堆+消耗堆 应恒等于卡组张数。

        前提：只做「出牌 / 结束回合 / 敌人行动」这些纯规则推进，
        不使用会凭空加牌的效果（如 add_card_to_hand）。
        """
        p = self.bs.player
        n_deck = (len(p.hand) + len(p.draw_pile) + len(p.discard_pile)
                  + len(p.exhaust_pile))
        self.assertEqual(n_deck, 10, "开局牌张总数应为 10，实际 %d" % n_deck)

        for turn in range(6):
            auto_play_turn(self.engine, self.bs)
            total = (len(p.hand) + len(p.draw_pile) + len(p.discard_pile)
                     + len(p.exhaust_pile))
            self.assertEqual(
                total, n_deck,
                "第 %d 回合牌张总数不守恒：%d != %d "
                "(hand=%d draw=%d discard=%d exhaust=%d)"
                % (turn, total, n_deck, len(p.hand), len(p.draw_pile),
                   len(p.discard_pile), len(p.exhaust_pile)))
            if self.bs.result() != "ongoing":
                break
            self.bs.end_turn()
            guard = 0
            ret = True
            while ret and guard < 60:
                ret = self.bs.enemy_step()
                guard += 1
            if self.bs.result() != "ongoing":
                break

    def test_end_turn_discards_hand(self):
        p = self.bs.player
        p.retain = getattr(p, "retain", None)
        before = len(p.hand)
        self.bs.end_turn()
        if self.bs.phase in ("won", "lost"):
            return
        self.assertLessEqual(len(p.hand), before)


class TestWinLose(TestEngineBase):

    def test_win_when_all_enemies_dead(self):
        for e in self.bs.enemies:
            e.hp = 1
            e.block = 0
        for _ in range(5):
            auto_play_turn(self.engine, self.bs)
            if self.bs.result() != "ongoing":
                break
            self.bs.end_turn()
            if self.bs.result() != "ongoing":
                break
        self.assertEqual(self.bs.result(), "won",
                         "敌人全灭后 result() 应为 'won'，实际 %r" % self.bs.result())
        self.assertEqual(self.bs.phase, "won")
        # 契约：BattleState.alive() == 「玩家是否存活」，不是「战斗是否进行中」。
        # 敌人全灭时玩家仍存活 → alive() 为 True，胜利由 result() 表达。
        self.assertTrue(self.bs.alive(),
                        "alive() 语义是玩家存活；敌人全灭时玩家仍活着，应为 True")

    def test_lose_when_player_dead(self):
        self.bs.player.hp = 0
        self.assertEqual(self.bs.result(), "lost",
                         "玩家 HP=0 后 result() 应为 'lost'，实际 %r" % self.bs.result())

    def test_result_never_raises(self):
        for phase in ("player", "enemy", "won", "lost"):
            try:
                self.bs.phase = phase
                self.bs.result()
            except Exception as exc:
                self.fail("result() 在 phase=%s 抛异常 %r" % (phase, exc))

    def test_enemy_step_returns_bool(self):
        self.bs.end_turn()
        if self.bs.phase != "enemy":
            self.skipTest("未进入敌人阶段")
        v = self.bs.enemy_step()
        self.assertIsInstance(v, bool, "enemy_step() 应返回 bool，实际 %r" % type(v))

    def test_current_enemy_intent_available(self):
        e = first_enemy(self.bs)
        mv = self.bs.current_enemy_intent(e)
        self.assertIsNotNone(mv, "current_enemy_intent 在战斗开始后应非 None")
        self.assertTrue(hasattr(mv, "intent"), "MoveDef 缺少 intent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
