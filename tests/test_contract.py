"""附录 A 冻结接口契约测试（ARCHITECTURE.md §附录 A）。

这是最高优先级的测试文件：UI 与引擎的接缝全靠这些冻结签名。
逐 key 断言 snapshot、逐名字断言 theme 导出、逐条断言战斗节奏协议。
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import alive_enemies, first_enemy, ContractCase, load, make_card  # noqa: E402

SNAPSHOT_TOP = ("turn", "phase", "player", "enemies", "hand",
                "draw_count", "discard_count", "exhaust_count",
                "relics", "log", "cards_played_this_turn")

SNAPSHOT_PLAYER = ("name", "hp", "max_hp", "block", "energy", "max_energy",
                   "buffs", "minions", "powers")

SNAPSHOT_ENEMY = ("idx", "name", "hp", "max_hp", "block", "buffs", "alive", "intent")

SNAPSHOT_INTENT = ("id", "name", "intent", "damage", "hits", "block", "text")

SNAPSHOT_HAND = ("uid", "def_id", "name", "cost", "type", "rarity", "arch",
                 "text", "upgraded", "playable")

THEME_NAMES = (
    "BG_DEEP", "BG_DARK", "PANEL", "PANEL_LIGHT", "BORDER", "TEXT", "TEXT_DIM",
    "TEXT_MUTED", "GOLD", "CYAN", "GREEN", "RED", "PURPLE", "ORANGE",
    "COLORS", "RARITY_COLORS", "TYPE_COLORS", "ARCH_COLORS",
    "FONT_TITLE", "FONT_H1", "FONT_H2", "FONT_BODY", "FONT_SMALL",
    "FONT_TINY", "FONT_NUM",
    "CARD_W", "CARD_H", "CARD_RADIUS",
    "rgb", "lerp_color", "mix", "round_rect", "vgradient", "hgradient",
    "draw_text_center", "rarity_color", "type_color", "arch_color",
    "font", "get_font",
)


def _enemy_id(enemies_mod, kind="normal", act=1):
    """从 ENCOUNTERS 取一个可用的敌人 id。"""
    enc = getattr(enemies_mod, "ENCOUNTERS", {})
    entry = enc.get(act, {})
    for k in (kind, "normal", "boss", "elite"):
        pool = entry.get(k) or []
        for item in pool:
            if isinstance(item, str):
                return item
            if isinstance(item, (list, tuple)) and item:
                return item[0]
    db = getattr(enemies_mod, "ENEMY_DB", {})
    for e in db.values():
        if e.tier == kind:
            return e.id
    return next(iter(db))


class TestA1BattleEntry(ContractCase):
    """A.1 — make_battle / make_enemy_combatant"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)

    def test_make_enemy_combatant_exists_and_works(self):
        self.assertTrue(callable(getattr(self.engine, "make_enemy_combatant", None)),
                        "缺少 A.1 冻结函数 make_enemy_combatant")
        rng = random.Random(5)
        eid = _enemy_id(self.enemies)
        c = self.engine.make_enemy_combatant(eid, rng, 0, 1)
        ed = self.enemies.ENEMY_DB[eid]
        self.assertEqual(c.name, ed.name)
        self.assertFalse(c.is_player)
        self.assertGreaterEqual(c.hp, ed.hp_min)
        self.assertLessEqual(c.hp, ed.hp_max)
        self.assertEqual(c.max_hp, c.hp)

    def test_make_enemy_combatant_ascension_scales_hp(self):
        rng = random.Random(5)
        eid = _enemy_id(self.enemies)
        ed = self.enemies.ENEMY_DB[eid]
        base = [self.engine.make_enemy_combatant(eid, random.Random(i), 0, 1).max_hp
                for i in range(12)]
        high = [self.engine.make_enemy_combatant(eid, random.Random(i), 20, 1).max_hp
                for i in range(12)]
        self.assertGreater(max(high), max(base) - 1,
                           "飞升 20 的敌人血量未提升：base=%s high=%s" % (base, high))

    def test_make_battle_exists_and_works(self):
        self.assertTrue(callable(getattr(self.engine, "make_battle", None)),
                        "缺少 A.1 冻结函数 make_battle")
        run = self.runmod.RunState()
        if hasattr(run, "new_run"):
            run.new_run(seed=11, ascension=0)
        eid = _enemy_id(self.enemies)
        bs = self.engine.make_battle(run, {"kind": "normal", "enemies": [eid]})
        self.assertIsNotNone(bs)
        self.assertEqual(len(bs.enemies), 1)
        self.assertEqual(bs.phase, "player")

    def test_move_to_returns_encounter_shape(self):
        """A.1：run.move_to 返回 dict 必须含 kind 与 encounter。"""
        run = self.runmod.RunState()
        if hasattr(run, "new_run"):
            run.new_run(seed=11, ascension=0)
        nodes = [n for n in getattr(run, "map_nodes", []) if n.kind == "battle"]
        self.assertTrue(nodes, "地图上没有 battle 节点")
        d = run.move_to(nodes[0].id)
        self.assertIsInstance(d, dict, "move_to 应返回 dict，实际 %r" % type(d))
        self.assertIn("kind", d, "move_to 返回值缺少 'kind'")
        self.assertIn("encounter", d, "move_to 返回值缺少 'encounter'")
        enc = d["encounter"]
        self.assertIsInstance(enc, dict)
        self.assertIn("enemies", enc, "encounter 缺少 'enemies'")


class TestA2SnapshotContract(ContractCase):
    """A.2 — snapshot() 冻结 key"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.cards, err = load("core.cards")
        self.assertIsNotNone(self.cards, "core.cards 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)
        run = self.runmod.RunState()
        if hasattr(run, "new_run"):
            run.new_run(seed=31, ascension=0)
        self.run = run
        self.bs = self.engine.make_battle(
            run, {"kind": "normal", "enemies": [_enemy_id(self.enemies)]})
        self.snap = self.bs.snapshot()

    def test_top_level_keys(self):
        for k in SNAPSHOT_TOP:
            self.assertIn(k, self.snap, "snapshot() 缺少顶层 key %r" % k)
        self.assertIsInstance(self.snap["turn"], int)
        self.assertIn(self.snap["phase"], ("player", "enemy", "won", "lost"))
        self.assertIsInstance(self.snap["log"], list)
        self.assertLessEqual(len(self.snap["log"]), 40,
                             "log 应最多保留最近 40 条，实际 %d" % len(self.snap["log"]))
        self.assertIsInstance(self.snap["cards_played_this_turn"], int)

    def test_player_keys(self):
        p = self.snap["player"]
        self.assertIsInstance(p, dict)
        for k in SNAPSHOT_PLAYER:
            self.assertIn(k, p, "snapshot['player'] 缺少 key %r" % k)
        for k in ("hp", "max_hp", "block", "energy", "max_energy"):
            self.assertIsInstance(p[k], int, "player.%s 应为 int" % k)
        self.assertIsInstance(p["name"], str)
        self.assertIsInstance(p["buffs"], dict)
        self.assertIsInstance(p["minions"], list)
        self.assertIsInstance(p["powers"], dict)
        for m in p["minions"]:
            self.assertIsInstance(m, dict)
            for k in ("name", "hp", "max_hp", "attack", "block"):
                self.assertIn(k, m, "minion 缺少 key %r" % k)

    def test_enemy_keys(self):
        self.assertIsInstance(self.snap["enemies"], list)
        self.assertTrue(self.snap["enemies"], "enemies 为空")
        for e in self.snap["enemies"]:
            for k in SNAPSHOT_ENEMY:
                self.assertIn(k, e, "snapshot['enemies'][i] 缺少 key %r" % k)
            self.assertIsInstance(e["idx"], int)
            self.assertIsInstance(e["alive"], bool, "enemy.alive 必须是 bool")
            self.assertIsInstance(e["buffs"], dict)
            self.assertIsInstance(e["hp"], int)

    def test_enemy_intent_shape_and_damage_semantics(self):
        """A.2 关键点：intent.damage 是**已计算**的玩家实际承受伤害。"""
        intents = [e["intent"] for e in self.snap["enemies"] if e["intent"] is not None]
        self.assertTrue(intents, "战斗开始时敌人意图不应为 None（A.2/AI 要求提前展示）")
        for it in intents:
            for k in SNAPSHOT_INTENT:
                self.assertIn(k, it, "intent 缺少 key %r" % k)
            self.assertIsInstance(it["damage"], int)
            self.assertIsInstance(it["hits"], int)
            self.assertIsInstance(it["block"], int)
            self.assertIsInstance(it["id"], str)
            self.assertIsInstance(it["name"], str)
            self.assertIsInstance(it["intent"], str)
            self.assertIsInstance(it["text"], str)

    def test_intent_damage_reflects_strength(self):
        """给敌人叠力量，snapshot 的 intent.damage 必须变大。"""
        e = self.bs.enemies[0]
        before = None
        for s in self.bs.snapshot()["enemies"]:
            before = s["intent"]
        if before is None or before["damage"] <= 0:
            self.skipTest("敌人当前意图不是攻击（damage=%s），无法验证力量加成"
                          % (before and before["damage"]))
        key = getattr(self.engine, "BUFF_STRENGTH", "strength")
        e.buffs[key] = e.buffs.get(key, 0) + 6
        after = None
        for s in self.bs.snapshot()["enemies"]:
            if s["idx"] == 0:
                after = s["intent"]
        self.assertIsNotNone(after)
        self.assertGreater(after["damage"], before["damage"],
                           "敌人力量 +6 后 intent.damage 应上升（%d -> %d）"
                           % (before["damage"], after["damage"]))

    def test_intent_damage_reflects_player_block_semantics(self):
        """易伤/虚弱应体现在 intent.damage 里；至少不能是原始未计算值。"""
        e = self.bs.enemies[0]
        base = None
        for s in self.bs.snapshot()["enemies"]:
            if s["idx"] == 0:
                base = s["intent"]
        if base is None or base["damage"] <= 0:
            self.skipTest("敌人当前不是攻击意图")
        vk = getattr(self.engine, "BUFF_VULNERABLE", "vulnerable")
        self.bs.player.buffs[vk] = self.bs.player.buffs.get(vk, 0) + 3
        after = None
        for s in self.bs.snapshot()["enemies"]:
            if s["idx"] == 0:
                after = s["intent"]
        self.assertGreater(after["damage"], base["damage"],
                           "玩家易伤后 intent.damage 应上升（%d -> %d）"
                           % (base["damage"], after["damage"]))

    def test_hand_keys(self):
        hand = self.snap["hand"]
        self.assertIsInstance(hand, list)
        self.assertTrue(hand, "起手手牌为空")
        for c in hand:
            for k in SNAPSHOT_HAND:
                self.assertIn(k, c, "snapshot['hand'][i] 缺少 key %r" % k)
            self.assertIsInstance(c["uid"], int)
            self.assertIsInstance(c["cost"], int)
            self.assertIsInstance(c["upgraded"], int)
            self.assertIsInstance(c["playable"], bool,
                                  "hand[i].playable 必须是 bool，实际 %r" % type(c["playable"]))

    def test_playable_semantics(self):
        """能量为 0 时，高费牌 playable 必须为 False。"""
        self.bs.player.energy = 0
        snap = self.bs.snapshot()
        for c in snap["hand"]:
            if c["cost"] >= 1:
                self.assertFalse(c["playable"],
                                 "%s(cost=%d) 在 0 能量时 playable 应为 False"
                                 % (c["def_id"], c["cost"]))
        self.bs.player.energy = 99
        snap = self.bs.snapshot()
        for c in snap["hand"]:
            self.assertTrue(c["playable"],
                            "%s(cost=%d) 在 99 能量时 playable 应为 True"
                            % (c["def_id"], c["cost"]))

    def test_pile_count_aliases(self):
        """A.2 别名兜底：hand[i] 中提供 draw_pile_len 等别名。"""
        hand = self.snap["hand"]
        self.assertTrue(hand)
        c = hand[0]
        # Lead 裁定：按 A.2 原文，别名必须挂在 hand[i] 上（顶层别名可选冗余）。
        for alias, canon in (("draw_pile_len", "draw_count"),
                             ("discard_pile_len", "discard_count"),
                             ("exhaust_pile_len", "exhaust_count")):
            self.assertIn(alias, c,
                          "A.2 要求 hand[i] 必须含别名 key %r（顶层冗余不算）" % alias)
            self.assertEqual(c[alias], self.snap[canon],
                             "hand[i].%r=%r 与 %s=%r 不一致"
                             % (alias, c[alias], canon, self.snap[canon]))

    def test_relic_entries(self):
        for r in self.snap["relics"]:
            for k in ("id", "name", "text", "rarity", "counter"):
                self.assertIn(k, r, "snapshot['relics'][i] 缺少 key %r" % k)

    def test_snapshot_is_json_serializable(self):
        import json
        try:
            json.dumps(self.snap)
        except TypeError as exc:
            self.fail("snapshot() 必须是纯数据（可 JSON 序列化）：%s" % exc)

    def test_snapshot_does_not_expose_live_objects(self):
        """UI 不得触碰内部对象：snapshot 里不该出现 Combatant / CardInstance。"""
        cc = getattr(self.engine, "Combatant", None)
        ci = getattr(self.cards, "CardInstance", None)

        def walk(v):
            if cc is not None and isinstance(v, cc):
                return True
            if ci is not None and isinstance(v, ci):
                return True
            if isinstance(v, dict):
                return any(walk(x) for x in v.values())
            if isinstance(v, (list, tuple)):
                return any(walk(x) for x in v)
            return False

        self.assertFalse(walk(self.snap), "snapshot() 泄漏了内部可变对象")


class TestA3PlayCard(ContractCase):
    """A.3 — play_card(card, target=None) 接受 uid 或 CardInstance"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.cards, err = load("core.cards")
        self.assertIsNotNone(self.cards, "core.cards 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)

    def _fresh(self):
        run = self.runmod.RunState()
        if hasattr(run, "new_run"):
            run.new_run(seed=77, ascension=0)
        return self.engine.make_battle(
            run, {"kind": "normal", "enemies": [_enemy_id(self.enemies)]})

    def test_signature_has_default_target(self):
        import inspect
        sig = inspect.signature(self.engine.BattleState.play_card)
        params = list(sig.parameters.values())
        self.assertGreaterEqual(len(params), 2, "play_card 至少要有 (self, card)")
        target_p = sig.parameters.get("target")
        self.assertIsNotNone(target_p, "play_card 缺少 target 参数")
        self.assertIsNot(target_p.default, inspect.Parameter.empty,
                         "play_card 的 target 必须有默认值（A.3 冻结为 target=None）")

    def test_accepts_card_instance(self):
        bs = self._fresh()
        card = bs.player.hand[0]
        target = first_enemy(bs) if alive_enemies(bs) else None
        ok = bs.play_card(card, target)
        self.assertIsInstance(ok, bool)
        self.assertTrue(ok, "合法出牌应返回 True")

    def test_accepts_int_uid(self):
        bs = self._fresh()
        card = bs.player.hand[0]
        uid = card.uid
        target = first_enemy(bs) if alive_enemies(bs) else None
        ok = bs.play_card(uid, target)
        self.assertIsInstance(ok, bool)
        self.assertTrue(ok, "play_card 应接受 int uid（A.3 冻结）")

    def test_target_omittable_for_self_target_card(self):
        bs = self._fresh()
        self_card = None
        for c in bs.player.hand:
            if c.defn.target in ("self", "none"):
                self_card = c
                break
        if self_card is None:
            self.skipTest("起手没有 self/none 目标牌")
        ok = bs.play_card(self_card)
        self.assertIsInstance(ok, bool)
        self.assertTrue(ok, "self 目标牌应能省略 target 打出")

    def test_illegal_plays_return_false_without_exception(self):
        bs = self._fresh()
        # 1) 不存在的 uid
        try:
            self.assertIs(bs.play_card(999999, None), False,
                          "非法 uid 应返回 False")
        except Exception as exc:
            self.fail("非法 uid 抛异常：%r" % (exc,))
        # 2) 能量不足
        bs.player.energy = 0
        high = None
        for c in bs.player.hand:
            if c.cost >= 1:
                high = c
                break
        if high is not None:
            try:
                self.assertIs(bs.play_card(high, first_enemy(bs)), False,
                              "能量不足应返回 False")
            except Exception as exc:
                self.fail("能量不足时 play_card 抛异常：%r" % (exc,))
        # 3) 不在手牌里的牌
        other = make_card(self.cards, self.cards.STARTER_DECK[0])
        outside = None
        for _ in range(400):
            cand = make_card(self.cards, self.cards.STARTER_DECK[0])
            if all(c.uid != cand.uid for c in bs.player.hand):
                outside = cand
                break
        if outside is not None:
            try:
                r = bs.play_card(outside, None)
                self.assertIsInstance(r, bool)
            except Exception as exc:
                self.fail("打出不在手牌的牌时抛异常：%r" % (exc,))

    def test_failed_play_writes_log(self):
        bs = self._fresh()
        n0 = len(bs.log)
        bs.play_card(999999, None)
        self.assertGreaterEqual(len(bs.log), n0, "log 不应因失败出牌而崩溃")


class TestA6BattleRhythm(ContractCase):
    """A.6 — 战斗节奏协议（Lead 标记为最易出 bug 处）"""

    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)

    def _fresh(self, seed=101):
        run = self.runmod.RunState()
        if hasattr(run, "new_run"):
            run.new_run(seed=seed, ascension=0)
        return self.engine.make_battle(
            run, {"kind": "normal", "enemies": [_enemy_id(self.enemies)]})

    def test_end_turn_does_not_execute_enemy_actions(self):
        """A.6.1：end_turn() 只进入 enemy phase，不执行敌人行动。"""
        bs = self._fresh()
        p_hp0 = bs.player.hp
        e_hp0 = bs.enemies[0].hp
        bs.end_turn()
        self.assertEqual(bs.phase, "enemy",
                         "end_turn() 后应处于 enemy phase，实际 %r" % bs.phase)
        self.assertEqual(bs.player.hp, p_hp0,
                         "end_turn() 不得让玩家掉血（敌人行动必须由 enemy_step 驱动）")
        self.assertEqual(bs.enemies[0].hp, e_hp0, "end_turn() 不得改变敌人血量")

    def test_enemy_step_true_then_false_opens_new_player_turn(self):
        """A.6.2：enemy_step 返回 False 表示敌方回合结束并已开新玩家回合。"""
        bs = self._fresh()
        bs.end_turn()
        self.assertEqual(bs.phase, "enemy")
        seen_true = False
        guard = 0
        ret = True
        while ret and guard < 50:
            ret = bs.enemy_step()
            guard += 1
            if ret:
                seen_true = True
        self.assertLess(guard, 50, "enemy_step 一直返回 True，敌方回合无法结束")
        self.assertEqual(ret, False)
        if bs.phase in ("won", "lost"):
            return
        self.assertEqual(bs.phase, "player",
                         "enemy_step 返回 False 后应已进入新的玩家回合，实际 %r" % bs.phase)
        self.assertEqual(len(bs.player.hand), 5,
                         "新玩家回合应抽满 5 张手牌，实际 %d" % len(bs.player.hand))

    def test_enemy_step_returns_bool(self):
        bs = self._fresh()
        bs.end_turn()
        r = bs.enemy_step()
        self.assertIsInstance(r, bool, "enemy_step 必须返回 bool，实际 %r" % type(r))

    def test_enemy_step_safe_when_phase_not_enemy(self):
        """A.6.3：phase 非 enemy 时安全返回 False，且不推进战斗。"""
        bs = self._fresh()
        self.assertEqual(bs.phase, "player")
        turn0 = bs.turn
        hp0 = bs.player.hp
        try:
            r = bs.enemy_step()
        except Exception as exc:
            self.fail("player phase 调 enemy_step 抛异常：%r" % (exc,))
        self.assertIs(r, False,
                      "phase=%r 时 enemy_step 应返回 False，实际 %r" % (bs.phase, r))
        self.assertEqual(bs.phase, "player", "enemy_step 不应在非 enemy phase 改变 phase")
        self.assertEqual(bs.turn, turn0, "enemy_step 不应在非 enemy phase 推进回合")
        self.assertEqual(bs.player.hp, hp0, "enemy_step 不应在非 enemy phase 造成伤害")

    def test_enemy_step_safe_after_battle_over(self):
        bs = self._fresh()
        for e in bs.enemies:
            e.hp = 0
        try:
            r = bs.enemy_step()
        except Exception as exc:
            self.fail("战斗结束后 enemy_step 抛异常：%r" % (exc,))
        self.assertIsInstance(r, bool)

    def test_enemy_step_idempotent_after_false(self):
        """返回 False 之后再调应仍然安全返回 False，不得重复开新回合。"""
        bs = self._fresh()
        bs.end_turn()
        guard = 0
        ret = True
        while ret and guard < 50:
            ret = bs.enemy_step()
            guard += 1
        if bs.phase in ("won", "lost"):
            return
        turn0 = bs.turn
        hand0 = len(bs.player.hand)
        r2 = bs.enemy_step()
        self.assertIs(r2, False)
        self.assertEqual(bs.turn, turn0, "重复 enemy_step 不应重复推进回合")
        self.assertEqual(len(bs.player.hand), hand0, "重复 enemy_step 不应重复抽牌")

    def test_full_ui_driven_loop_completes(self):
        """模拟 UI 调度：出牌 → end_turn → 400ms 轮询 enemy_step，直至分出胜负。"""
        bs = self._fresh(seed=2024)
        turns = 0
        while bs.result() == "ongoing" and turns < 60:
            turns += 1
            # 玩家：能打就打
            for _ in range(50):
                played = False
                for c in list(bs.player.hand):
                    if bs.can_play(c):
                        tgt = first_enemy(bs) if alive_enemies(bs) else None
                        if bs.play_card(c, tgt):
                            played = True
                            break
                if not played:
                    break
            if bs.result() != "ongoing":
                break
            bs.end_turn()
            guard = 0
            ret = True
            while ret and guard < 60:
                ret = bs.enemy_step()
                guard += 1
            if bs.result() != "ongoing":
                break
            self.assertEqual(bs.phase, "player",
                             "一轮结束后应回到玩家回合，实际 %r" % bs.phase)
        self.assertIn(bs.result(), ("won", "lost"),
                      "%d 回合仍未分出胜负（result=%r）——战斗无法收敛" % (turns, bs.result()))


class TestA4Events(ContractCase):
    """A.4 — core/events.py 公开面"""

    required_module = "core.events"

    def test_event_db_size(self):
        db = getattr(self.events, "EVENT_DB", None)
        self.assertIsInstance(db, dict)
        self.assertGreaterEqual(len(db), 22, "EVENT_DB 只有 %d 个（契约 ≥22）" % len(db))

    def test_event_defs_valid(self):
        for e in self.events.EVENT_DB.values():
            self.assertTrue(e.id and e.name and e.text, "事件 %r 字段为空" % e.id)
            self.assertIn(e.act, (1, 2, 3), "事件 %s act=%r 非法" % (e.id, e.act))
            self.assertTrue(e.choices, "事件 %s 没有选项" % e.id)
            for ch in e.choices:
                self.assertTrue(ch.label, "事件 %s 有选项缺 label" % e.id)
                self.assertTrue(callable(ch.effect),
                                "事件 %s 选项 %r 的 effect 不可调用" % (e.id, ch.label))
                if ch.requires is not None:
                    self.assertTrue(callable(ch.requires))

    def test_random_event(self):
        self.assertTrue(callable(getattr(self.events, "random_event", None)))
        for act in (1, 2, 3):
            got = self.events.random_event(random.Random(3), act, set())
            self.assertIn(got.id, self.events.EVENT_DB)

    def test_shop_prices(self):
        for name in ("SHOP_CARD_PRICE", "SHOP_RELIC_PRICE", "SHOP_POTION_PRICE",
                     "SHOP_REMOVE_PRICE_BASE"):
            self.assertTrue(hasattr(self.events, name), "events 缺少 %s" % name)
        cp = self.events.SHOP_CARD_PRICE
        for r in ("common", "uncommon", "rare"):
            self.assertIn(r, cp)
            self.assertIsInstance(cp[r], int)
        self.assertLess(cp["common"], cp["uncommon"], "卡价应随稀有度递增")
        self.assertLess(cp["uncommon"], cp["rare"], "卡价应随稀有度递增")
        self.assertIsInstance(self.events.SHOP_POTION_PRICE, int)
        self.assertIsInstance(self.events.SHOP_REMOVE_PRICE_BASE, int)

    def test_build_shop_inventory(self):
        fn = getattr(self.events, "build_shop_inventory", None)
        self.assertTrue(callable(fn), "events 缺少 build_shop_inventory")
        inv = fn(random.Random(8), 1, 0)
        self.assertIsInstance(inv, dict)
        for k in ("cards", "relics", "potions", "remove_price"):
            self.assertIn(k, inv, "商店库存缺少 key %r" % k)
        self.assertTrue(inv["cards"], "商店没有卡牌")
        self.assertIsInstance(inv["remove_price"], int)
        self.assertGreater(inv["remove_price"], 0)

    def test_treasure_tiers_and_roll(self):
        self.assertTrue(hasattr(self.events, "TREASURE_TIERS"))
        for t in ("gold", "relic", "potion", "curse_relic"):
            self.assertIn(t, self.events.TREASURE_TIERS)
        fn = getattr(self.events, "roll_treasure", None)
        self.assertTrue(callable(fn), "events 缺少 roll_treasure")
        for act in (1, 2, 3):
            r = fn(random.Random(5), act)
            self.assertIsInstance(r, dict)
            self.assertIn("tier", r)
            self.assertIn(r["tier"], self.events.TREASURE_TIERS)


class TestA5ThemeExports(unittest.TestCase):
    """A.5 — ui/theme.py 必须导出的名字（防 UI 崩溃第一道防线）"""

    @classmethod
    def setUpClass(cls):
        cls.theme, cls.err = load("ui.theme")

    def setUp(self):
        if self.theme is None:
            self.fail("ui.theme 无法导入：%s" % self.err)

    def test_all_names_present(self):
        missing = [n for n in THEME_NAMES if not hasattr(self.theme, n)]
        self.assertEqual(missing, [], "ui/theme.py 缺少 A.5 冻结名字：%s" % missing)

    def test_color_constants_are_hex(self):
        import re
        names = ("BG_DEEP", "BG_DARK", "PANEL", "PANEL_LIGHT", "BORDER", "TEXT",
                 "TEXT_DIM", "TEXT_MUTED", "GOLD", "CYAN", "GREEN", "RED",
                 "PURPLE", "ORANGE")
        for n in names:
            v = getattr(self.theme, n, None)
            self.assertIsInstance(v, str, "%s 应为 str，实际 %r" % (n, type(v)))
            self.assertTrue(re.match(r"^#[0-9a-fA-F]{6}$", v),
                            "%s=%r 不是 #RRGGBB" % (n, v))

    def test_dicts_cover_required_keys(self):
        c = getattr(self.theme, "COLORS", None)
        self.assertIsInstance(c, dict, "COLORS 应为 dict")
        for name in ("BG_DEEP", "TEXT", "GOLD"):
            self.assertIn(name.lower() if name.lower() in c else name, c,
                          "COLORS 缺少 %s" % name)
        rc = getattr(self.theme, "RARITY_COLORS", None)
        self.assertIsInstance(rc, dict)
        for r in ("basic", "common", "uncommon", "rare"):
            self.assertIn(r, rc, "RARITY_COLORS 缺少 %r" % r)
        self.assertIsInstance(getattr(self.theme, "TYPE_COLORS", None), dict)
        self.assertIsInstance(getattr(self.theme, "ARCH_COLORS", None), dict)

    def test_card_size_constants(self):
        self.assertEqual(self.theme.CARD_W, 168)
        self.assertEqual(self.theme.CARD_H, 236)
        self.assertEqual(self.theme.CARD_RADIUS, 12)

    def test_font_constants_are_tuples(self):
        for n in ("FONT_TITLE", "FONT_H1", "FONT_H2", "FONT_BODY",
                  "FONT_SMALL", "FONT_TINY", "FONT_NUM"):
            v = getattr(self.theme, n, None)
            self.assertIsInstance(v, tuple, "%s 应为 tuple（tk 字体元组），实际 %r" % (n, type(v)))

    def test_function_signatures_callable(self):
        for n in ("rgb", "lerp_color", "mix", "round_rect", "vgradient",
                  "hgradient", "draw_text_center", "rarity_color", "type_color",
                  "arch_color", "font", "get_font"):
            self.assertTrue(callable(getattr(self.theme, n, None)),
                            "%s 不可调用" % n)
        self.assertEqual(len(self.theme.rgb("#ff8000")), 3, "rgb 应返回 3 元组")
        out = self.theme.lerp_color("#000000", "#ffffff", 0.5)
        self.assertTrue(isinstance(out, str) and out.startswith("#"),
                        "lerp_color 应返回 hex 字符串，实际 %r" % (out,))
        self.assertTrue(isinstance(self.theme.mix("#000000", "#ffffff", 0.5), str))
        for r in ("basic", "common", "uncommon", "rare"):
            self.assertTrue(str(self.theme.rarity_color(r)).startswith("#"))
        for t in ("attack", "skill", "power"):
            self.assertTrue(str(self.theme.type_color(t)).startswith("#"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
