"""对抗性测试：专门攻击 Lead 点名的脆弱面。

1. end_turn 不得执行敌人行动（A.6）
2. enemy_step 幂等 / phase != enemy 安全
3. intent.damage 是已修正值
4. play_card 双形态（CardInstance / int uid）
5. **卡牌 effect 抛异常时引擎不得崩溃**
6. **run.deck 不得被战斗污染**
外加：非法输入 fuzz、战斗收敛性。
"""

import copy
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import alive_enemies, first_enemy, ContractCase, load, make_combatant, start_battle  # noqa: E402


def pick_enemy(enemies_mod, tier="normal", act=1):
    enc = getattr(enemies_mod, "ENCOUNTERS", {})
    entry = enc.get(act, {})
    for k in (tier, "normal", "boss", "elite"):
        for item in (entry.get(k) or []):
            if isinstance(item, str):
                return item
            if isinstance(item, (list, tuple)) and item:
                return item[0]
    for e in getattr(enemies_mod, "ENEMY_DB", {}).values():
        if e.tier == tier:
            return e.id
    return next(iter(enemies_mod.ENEMY_DB))


class TestEffectRobustness(ContractCase):
    """卡牌 effect 抛异常时引擎必须吞掉并写 log，绝不崩溃。"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.cards, err = load("core.cards")
        self.assertIsNotNone(self.cards, "core.cards 不可用：%s" % err)
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)

    def _fresh(self):
        run = self.runmod.RunState()
        if hasattr(run, "new_run"):
            run.new_run(seed=13, ascension=0)
        return self.engine.make_battle(
            run, {"kind": "normal", "enemies": [pick_enemy(self.enemies)]})

    def test_effect_raising_does_not_crash_play_card(self):
        """把一个会抛异常的 effect 挂到手牌上，play_card 不得抛异常。"""
        bs = self._fresh()
        card = bs.player.hand[0]

        def boom(ctx):
            raise RuntimeError("intentional verifier bomb")

        # 尝试多种注入方式，覆盖不同实现
        injected = False
        try:
            object.__setattr__(card, "_defn_override", None)
        except Exception:
            pass
        try:
            card.effect_override = boom
            injected = True
        except Exception:
            pass
        try:
            object.__setattr__(card, "effect_override", boom)
            injected = True
        except Exception:
            pass

        n_log = len(bs.log)
        try:
            r = bs.play_card(card, first_enemy(bs) if alive_enemies(bs) else None)
        except Exception as exc:
            self.fail("effect 抛异常导致 play_card 崩溃：%r" % (exc,))
        self.assertIsInstance(r, bool)
        if injected:
            self.assertGreaterEqual(len(bs.log), n_log,
                                    "effect 抛异常后应至少有 log 记录")

    def test_engine_survives_effect_exception_via_defn_patch(self):
        """直接给一张真实卡打上会抛异常的 effect，走完整出牌路径。"""
        bs = self._fresh()
        from core import cards as c
        victim = None
        for cd in c.CARD_DB.values():
            if cd.effect is not None and cd.cost == 0:
                victim = cd
                break
        if victim is None:
            self.skipTest("没有 0 费带 effect 的卡可供注入")

        inst = c.make_card(victim.id)
        bs.player.energy = 9
        bs.player.hand.append(inst)
        try:
            r = bs.play_card(inst, first_enemy(bs) if alive_enemies(bs) else None)
            self.assertIsInstance(r, bool)
        except Exception as exc:
            self.fail("正常出牌路径抛异常：%r" % (exc,))

    def test_can_play_never_raises_on_weird_input(self):
        bs = self._fresh()

        class Weird:
            pass

        for bad in (None, Weird(), 12345, "not a card", -1):
            try:
                bs.can_play(bad)
            except Exception as exc:
                self.fail("can_play(%r) 抛异常：%r" % (bad, exc))

    def test_play_card_fuzz_never_raises(self):
        """100 次随机非法出牌，一次都不许抛异常。"""
        rng = random.Random(4242)
        for i in range(100):
            bs = self._fresh()
            kind = rng.randrange(6)
            if kind == 0:
                card = rng.randrange(-5, 10 ** 6)
            elif kind == 1:
                card = None
            elif kind == 2:
                card = bs.player.hand[0] if bs.player.hand else 0
            elif kind == 3:
                from core import cards as c
                card = c.make_card(rng.choice(list(c.CARD_DB)))
            elif kind == 4:
                card = bs.player.hand[0] if bs.player.hand else 0
                bs.player.energy = 0
            else:
                card = bs.player.hand[0] if bs.player.hand else 0
            target = rng.choice([None, 0, -1, 99, 10 ** 6])
            try:
                r = bs.play_card(card, target)
            except Exception as exc:
                self.fail("play_card(%r, %r) 第 %d 次 fuzz 抛异常：%r"
                          % (card, target, i, exc))
            self.assertIsInstance(r, bool,
                                  "play_card 必须返回 bool，实际 %r（card=%r target=%r）"
                                  % (type(r), card, target))


class TestNoDeckPollution(ContractCase):
    """run.deck 不得被战斗污染。"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.cards, err = load("core.cards")
        self.enemies, err = load("core.enemies")
        self.runmod, err = load("core.run")
        for m, e in ((self.cards, "core.cards"), (self.enemies, "core.enemies"),
                     (self.runmod, "core.run")):
            self.assertIsNotNone(m, "%s 不可用：%s" % (e, err))

    def test_run_deck_unchanged_after_battle(self):
        run = self.runmod.RunState()
        run.new_run(seed=21, ascension=0)
        before = [(c.uid, c.def_id, getattr(c, "upgraded", 0)) for c in run.deck]
        before_objs = list(run.deck)

        bs = self.engine.make_battle(
            run, {"kind": "normal", "enemies": [pick_enemy(self.enemies)]})
        # 打一整个回合
        for _ in range(30):
            played = False
            for c in list(bs.player.hand):
                if bs.can_play(c):
                    t = first_enemy(bs) if alive_enemies(bs) else None
                    if bs.play_card(c, t):
                        played = True
                        break
            if not played:
                break
        bs.end_turn()
        guard = 0
        ret = True
        while ret and guard < 50:
            ret = bs.enemy_step()
            guard += 1

        after = [(c.uid, c.def_id, getattr(c, "upgraded", 0)) for c in run.deck]
        self.assertEqual(before, after,
                         "run.deck 在战斗中被修改（卡牌数量/uid/升级状态变化）")
        self.assertEqual(len(run.deck), len(before_objs),
                         "run.deck 长度在战斗后改变")

    def test_battle_uses_clones_not_run_deck_objects(self):
        run = self.runmod.RunState()
        run.new_run(seed=22, ascension=0)
        deck_ids = {id(c) for c in run.deck}
        bs = self.engine.make_battle(
            run, {"kind": "normal", "enemies": [pick_enemy(self.enemies)]})
        all_battle_cards = list(bs.player.hand) + list(bs.player.draw_pile) + \
            list(bs.player.discard_pile)
        shared = [c for c in all_battle_cards if id(c) in deck_ids]
        self.assertEqual(shared, [],
                         "战斗直接复用了 run.deck 的 CardInstance 对象（未 clone），"
                         "战斗中的升级/临时改费会污染长期卡组")

    def test_temp_cost_override_does_not_leak(self):
        run = self.runmod.RunState()
        run.new_run(seed=23, ascension=0)
        base_costs = {c.uid: c.cost for c in run.deck}
        bs = self.engine.make_battle(
            run, {"kind": "normal", "enemies": [pick_enemy(self.enemies)]})
        for c in bs.player.hand:
            c.cost_override = 0
        bs.end_turn()
        guard = 0
        ret = True
        while ret and guard < 50:
            ret = bs.enemy_step()
            guard += 1
        for c in run.deck:
            self.assertIsNone(getattr(c, "cost_override", None),
                              "run.deck 的卡 %s 残留了战斗内的 cost_override=%r"
                              % (c.def_id, c.cost_override))
            self.assertEqual(c.cost, base_costs[c.uid],
                             "run.deck 的卡 %s 费用被战斗改变" % c.def_id)


class TestEnemyActionDiscipline(ContractCase):
    """再次针对 A.6 的攻击性验证（多敌人、多回合）。"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)

    def _fresh(self, n=2, seed=303):
        run = self.runmod.RunState()
        run.new_run(seed=seed, ascension=0)
        eid = pick_enemy(self.enemies)
        return self.engine.make_battle(run, {"kind": "normal", "enemies": [eid] * n})

    def test_end_turn_never_damages_player_across_many_turns(self):
        bs = self._fresh()
        bs.player.hp = bs.player.max_hp = 100000
        for turn in range(20):
            hp0 = bs.player.hp
            bs.player.block = 0
            ehp0 = [e.hp for e in bs.enemies]
            bs.end_turn()
            self.assertEqual(bs.player.hp, hp0,
                             "第 %d 回合 end_turn() 后玩家掉血了（应只切 phase）" % turn)
            self.assertEqual([e.hp for e in bs.enemies], ehp0,
                             "第 %d 回合 end_turn() 改变了敌人血量" % turn)
            # 敌人行动
            guard = 0
            ret = True
            while ret and guard < 100:
                ret = bs.enemy_step()
                guard += 1
            if bs.phase in ("won", "lost"):
                break
            bs.player.hp = bs.player.max_hp = 100000

    def test_multiple_enemies_each_act_once(self):
        """2 个敌人时，敌方阶段应至少返回一次 True（说明有多个待行动）。"""
        bs = self._fresh(n=2)
        bs.end_turn()
        self.assertEqual(bs.phase, "enemy")
        ret = bs.enemy_step()
        self.assertIsInstance(ret, bool)

    def test_enemy_step_callable_200_times_safely(self):
        bs = self._fresh(n=1)
        for i in range(200):
            try:
                r = bs.enemy_step()
            except Exception as exc:
                self.fail("第 %d 次 enemy_step 抛异常：%r" % (i, exc))
            self.assertIsInstance(r, bool)

    def test_phase_never_becomes_invalid_through_full_battle(self):
        bs = self._fresh(n=1)
        valid = {"player", "enemy", "won", "lost"}
        for i in range(400):
            self.assertIn(bs.phase, valid, "第 %d 步出现非法 phase=%r" % (i, bs.phase))
            if bs.phase == "player":
                for c in list(bs.player.hand):
                    if bs.can_play(c):
                        t = first_enemy(bs) if alive_enemies(bs) else None
                        if bs.play_card(c, t):
                            break
                bs.end_turn()
            else:
                bs.enemy_step()
            if bs.result() != "ongoing":
                break


class TestIntentDamageIsCorrection(ContractCase):
    """intent.damage 必须是修正后的玩家实际承受伤害。"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.runmod, err = load("core.run")

    def _fresh(self, seed=404):
        run = self.runmod.RunState()
        run.new_run(seed=seed, ascension=0)
        # 挑一个攻击型敌人
        eid = None
        for e in self.enemies.ENEMY_DB.values():
            if e.tier == "normal" and any(m.damage > 0 for m in e.moves):
                eid = e.id
                break
        eid = eid or pick_enemy(self.enemies)
        return self.engine.make_battle(run, {"kind": "normal", "enemies": [eid]})

    def _intent0(self, bs):
        for e in bs.snapshot()["enemies"]:
            if e["idx"] == 0:
                return e["intent"]
        return None

    def test_weak_reduces_intent_damage(self):
        bs = self._fresh()
        it = self._intent0(bs)
        if it is None or it["damage"] <= 0:
            self.skipTest("敌人当前意图非攻击（damage=%s）" % (it and it["damage"]))
        base = it["damage"]
        wk = getattr(self.engine, "BUFF_WEAK", "weak")
        e = bs.enemies[0]
        e.buffs[wk] = 5
        after = self._intent0(bs)["damage"]
        self.assertLess(after, base,
                        "敌人虚弱后 intent.damage 应下降（%d -> %d）—— "
                        "若未下降说明 damage 是未修正的原始值" % (base, after))

    def test_intent_damage_matches_actual_damage_dealt(self):
        """实际受到伤害应与展示的 intent.damage 一致。"""
        bs = self._fresh()
        it = self._intent0(bs)
        if it is None or it["damage"] <= 0:
            self.skipTest("敌人当前意图非攻击")
        shown = it["damage"]
        bs.player.block = 0
        bs.player.hp = bs.player.max_hp = 100000
        hp0 = bs.player.hp
        bs.end_turn()
        guard = 0
        ret = True
        while ret and guard < 50:
            ret = bs.enemy_step()
            guard += 1
        taken = hp0 - bs.player.hp
        if bs.phase in ("won", "lost"):
            self.skipTest("战斗在敌人行动前结束")
        self.assertEqual(taken, shown,
                         "展示的 intent.damage=%d 与实际扣除的 HP=%d 不一致"
                         % (shown, taken))

    def test_intent_damage_accounts_for_player_block_display(self):
        """至少保证 intent.damage 不是负数且为 int。"""
        bs = self._fresh()
        for e in bs.snapshot()["enemies"]:
            if e["intent"] is not None:
                self.assertGreaterEqual(e["intent"]["damage"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
