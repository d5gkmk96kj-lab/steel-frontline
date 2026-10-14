"""敌人 AI 测试（ARCHITECTURE.md §5/§6）。

覆盖：无三连同一招（500 回合枚举）、精英低血会格挡、BOSS 多阶段。
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import ContractCase, auto_play_turn, buff_key, load, make_combatant  # noqa: E402


class TestEnemyDatabase(ContractCase):
    required_module = "core.enemies"

    def test_enemy_count(self):
        db = getattr(self.enemies, "ENEMY_DB", {})
        self.assertGreaterEqual(len(db), 34, "ENEMY_DB 只有 %d 个（契约 ≥34）" % len(db))

    def test_boss_count_and_stages(self):
        db = getattr(self.enemies, "ENEMY_DB", {})
        bosses = [e for e in db.values() if e.tier == "boss"]
        self.assertGreaterEqual(len(bosses), 3, "BOSS 只有 %d 个（契约 ≥3）" % len(bosses))
        acts = sorted({b.act for b in bosses})
        self.assertIn(1, acts)
        # 每个 boss 必须有独特机制：多阶段 / 召唤 / 专属 debuff
        weak = []
        for b in bosses:
            blob = (b.desc or "") + " " + " ".join(m.text or "" for m in b.moves)
            has_stage = ("阶段" in blob) or (b.ai is not None) or len(b.moves) >= 4
            if not has_stage:
                weak.append(b.id)
        self.assertEqual(weak, [], "以下 BOSS 看不出多阶段/召唤/专属机制：%s" % weak)

    def test_encounters_cover_acts(self):
        enc = getattr(self.enemies, "ENCOUNTERS", {})
        self.assertTrue(enc, "ENCOUNTERS 缺失")
        for act in (1, 2, 3):
            self.assertIn(act, enc, "ENCOUNTERS 缺少 act %d" % act)
            entry = enc[act]
            for kind in ("normal", "elite", "boss"):
                self.assertIn(kind, entry, "act %d 缺少 %s 遭遇" % (act, kind))
                self.assertTrue(entry[kind], "act %d 的 %s 遭遇为空" % (act, kind))

    def test_moveset_valid(self):
        db = getattr(self.enemies, "ENEMY_DB", {})
        valid_intents = {"attack", "attack_debuff", "attack_defend", "defend",
                         "buff", "debuff", "unknown", "sleep"}
        problems = []
        for e in db.values():
            if not e.moves:
                problems.append("%s: 无招式" % e.id)
            if e.hp_min <= 0 or e.hp_max < e.hp_min:
                problems.append("%s: hp 范围非法 %d..%d" % (e.id, e.hp_min, e.hp_max))
            if e.tier not in ("normal", "elite", "boss"):
                problems.append("%s: tier=%r" % (e.id, e.tier))
            for m in e.moves:
                if m.intent not in valid_intents:
                    problems.append("%s/%s: intent=%r" % (e.id, m.id, m.intent))
                if m.hits < 1:
                    problems.append("%s/%s: hits<1" % (e.id, m.id))
                if m.damage < 0:
                    problems.append("%s/%s: damage<0" % (e.id, m.id))
        self.assertEqual(problems, [], "敌人数据问题：\n  " + "\n  ".join(problems[:30]))

    def test_enemy_ids_unique_and_keys_match(self):
        db = getattr(self.enemies, "ENEMY_DB", {})
        for key, e in db.items():
            self.assertEqual(key, e.id, "ENEMY_DB 键 %r != id %r" % (key, e.id))


class TestEnemyAI(ContractCase):
    required_module = "core.engine"

    def setUp(self):
        super().setUp()
        self.enemies, err = load("core.enemies")
        self.assertIsNotNone(self.enemies, "core.enemies 不可用：%s" % err)
        self.cards, err = load("core.cards")
        self.assertIsNotNone(self.cards, "core.cards 不可用：%s" % err)
        self.runmod, err = load("core.run")
        self.assertIsNotNone(self.runmod, "core.run 不可用：%s" % err)

    # ------------------------------------------------------------ 无三连
    def test_no_three_peat_for_all_enemies(self):
        """500 回合枚举：任何敌人不得连续 3 次使用同一招。"""
        offenders = {}
        db = self.enemies.ENEMY_DB
        for eid, ed in db.items():
            seq = self._move_sequence(ed, turns=500)
            run_len = 1
            for i in range(1, len(seq)):
                if seq[i] == seq[i - 1]:
                    run_len += 1
                    if run_len >= 3:
                        offenders.setdefault(eid, []).append((i, seq[i - 2:i + 1]))
                        break
                else:
                    run_len = 1
        self.assertEqual(offenders, {},
                         "以下敌人出现连续 3 次同一招：%s" % offenders)

    def _move_sequence(self, ed, turns=500):
        """尽量用真实战斗引擎跑 turns 个敌人回合，采集敌人出招序列。"""
        seq = []
        try:
            run = self.runmod.RunState()
            if hasattr(run, "new_run"):
                run.new_run(seed=4242, ascension=0)
        except Exception:
            run = object()
        rng = random.Random(4242)
        try:
            p = make_combatant(self.engine, True, "P", 99999)
            p.max_hp = 99999
            p.energy = 0
            enemy = make_combatant(self.engine, False, ed.name, 99999)
            for attr in ("def_id", "enemy_id"):
                if hasattr(enemy, attr):
                    setattr(enemy, attr, ed.id)
                    break
            if hasattr(enemy, "defn"):
                enemy.defn = ed
            bs = self.engine.BattleState(run, [enemy], rng)
            if hasattr(bs, "start_battle"):
                bs.start_battle()
        except Exception as exc:
            raise AssertionError("无法构造战斗以采样 AI：%r" % (exc,))

        last = None
        for _ in range(turns):
            bs.phase = "enemy"
            try:
                bs.enemy_step()
            except Exception as exc:
                raise AssertionError("%s 的 enemy_step 抛异常：%r" % (ed.id, exc))
            mv = getattr(enemy, "last_move", None) or getattr(enemy, "current_move", None)
            if mv is None:
                mv = bs.current_enemy_intent(enemy)
            mid = getattr(mv, "id", None)
            if mid is None:
                # 引擎未暴露；退化为检查意图
                break
            seq.append(mid)
            # 保持玩家存活，敌人不被打死
            bs.player.hp = bs.player.max_hp = 99999
            enemy.hp = enemy.max_hp = 99999
            bs.player.block = 0
            if hasattr(bs, "end_turn"):
                try:
                    bs.end_turn()
                except Exception:
                    pass
        if not seq:
            raise AssertionError(
                "%s: 无法采集出招序列（引擎未暴露敌人上一招 id）——"
                "无三连同一招无法验证" % ed.id)
        return seq

    def test_ai_uses_multiple_moves(self):
        ok = []
        for eid, ed in self.enemies.ENEMY_DB.items():
            if len(ed.moves) < 2:
                continue
            ok.append(eid)
        self.assertTrue(ok, "没有多招式的敌人，AI 无从谈起")

    # ------------------------------------------------------------ 精英低血格挡
    def test_elite_blocks_when_low_hp(self):
        """构造精英低血场景，AI 应该选择防御/治疗类招式而非纯攻击。"""
        elites = [e for e in self.enemies.ENEMY_DB.values()
                  if e.tier == "elite" and self._has_defensive(e)]
        self.assertTrue(elites, "没有具备防御招式的精英敌人，无法验证读局势 AI")
        results = {}
        for ed in elites:
            chosen = self._sample_elite_move(ed)
            results[ed.id] = chosen
        good = [eid for eid, mv in results.items() if mv in ("defend", "attack_defend", "buff")]
        self.assertTrue(good,
                        "精英低血时未选择任何防御/增益招：采样结果=%s" % results)

    def _has_defensive(self, ed):
        return any(m.intent in ("defend", "attack_defend") or m.block > 0
                   for m in ed.moves)

    def _sample_elite_move(self, ed, low_ratio=0.15):
        try:
            run = self.runmod.RunState()
            if hasattr(run, "new_run"):
                run.new_run(seed=1717, ascension=0)
        except Exception:
            run = object()
        p = make_combatant(self.engine, True, "P", 500)
        enemy = make_combatant(self.engine, False, ed.name, ed.hp_max)
        for attr in ("def_id", "enemy_id"):
            if hasattr(enemy, attr):
                setattr(enemy, attr, ed.id)
                break
        if hasattr(enemy, "defn"):
            enemy.defn = ed
        enemy.hp = max(1, int(ed.hp_max * low_ratio))
        enemy.max_hp = ed.hp_max
        bs = self.engine.BattleState(run, [enemy], random.Random(1717))
        if hasattr(bs, "start_battle"):
            bs.start_battle()
        enemy.hp = max(1, int(ed.hp_max * low_ratio))
        # 让敌人连续行动若干次，统计是否出现防御
        for _ in range(20):
            enemy.hp = max(1, int(ed.hp_max * low_ratio))
            bs.phase = "enemy"
            try:
                bs.enemy_step()
            except Exception:
                break
            mv = getattr(enemy, "last_move", None) or getattr(enemy, "current_move", None)
            mv = mv or bs.current_enemy_intent(enemy)
            if mv is not None and getattr(mv, "intent", None) in ("defend", "attack_defend"):
                return mv.intent
            p.hp = 500
            if hasattr(bs, "end_turn"):
                try:
                    bs.end_turn()
                except Exception:
                    pass
        return None

    # ------------------------------------------------------------ BOSS 多阶段
    def test_boss_multi_phase_behavior(self):
        bosses = [e for e in self.enemies.ENEMY_DB.values() if e.tier == "boss"]
        self.assertGreaterEqual(len(bosses), 3)
        checked = []
        for b in bosses:
            stages = self._detect_stages(b)
            checked.append((b.id, stages))
        self.assertTrue(any(s for _, s in checked),
                        "所有 BOSS 都检测不到阶段变化：%s" % checked)
        missing = [bid for bid, s in checked if not s]
        self.assertEqual(missing, [],
                         "以下 BOSS 没有可观测的多阶段行为：%s" % missing)

    def _detect_stages(self, b):
        """检测 BOSS 在血量跨过阈值后是否换招/获得 buff。"""
        try:
            run = self.runmod.RunState()
            if hasattr(run, "new_run"):
                run.new_run(seed=99, ascension=0)
        except Exception:
            run = object()
        p = make_combatant(self.engine, True, "P", 99999)
        p.max_hp = 99999
        enemy = make_combatant(self.engine, False, b.name, b.hp_max)
        for attr in ("def_id", "enemy_id"):
            if hasattr(enemy, attr):
                setattr(enemy, attr, b.id)
                break
        if hasattr(enemy, "defn"):
            enemy.defn = b
        bs = self.engine.BattleState(run, [enemy], random.Random(99))
        if hasattr(bs, "start_battle"):
            bs.start_battle()

        def snapshot_state():
            return (
                tuple(sorted((k, v) for k, v in (enemy.buffs or {}).items())),
                getattr(getattr(enemy, "last_move", None), "id", None),
                getattr(enemy, "phase_index", None),
                getattr(enemy, "stage", None),
            )

        high = []
        low = []
        for _ in range(30):
            enemy.hp = enemy.max_hp
            bs.phase = "enemy"
            try:
                bs.enemy_step()
            except Exception:
                break
            high.append(snapshot_state())
            p.hp = 99999
        for _ in range(30):
            enemy.hp = max(1, int(enemy.max_hp * 0.2))
            bs.phase = "enemy"
            try:
                bs.enemy_step()
            except Exception:
                break
            low.append(snapshot_state())
            p.hp = 99999
        # 阶段变化：buff 集合或显式 stage 字段在高/低血量下不同
        high_buffs = {s[0] for s in high}
        low_buffs = {s[0] for s in low}
        high_stage = {s[2] for s in high} | {s[3] for s in high}
        low_stage = {s[2] for s in low} | {s[3] for s in low}
        return (high_buffs != low_buffs) or (high_stage != low_stage)


if __name__ == "__main__":
    unittest.main(verbosity=2)
