"""RunState 长期进度测试（ARCHITECTURE.md §7）。

覆盖：同种子可复现、存档往返、20 档飞升单调递增且合法、地图连通性。
"""

import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import ContractCase, load, NODE_KINDS  # noqa: E402


def new_run(runmod, seed, ascension=0):
    r = runmod.RunState()
    r.new_run(seed=seed, ascension=ascension)
    return r


class TestRunReproducibility(ContractCase):
    required_module = "core.run"

    def test_same_seed_same_map(self):
        a = new_run(self.run, 42)
        b = new_run(self.run, 42)
        self.assertEqual(len(a.map_nodes), len(b.map_nodes), "同种子地图节点数不同")
        sig = lambda r: [(n.id, n.row, n.col, n.kind, tuple(n.edges)) for n in r.map_nodes]
        self.assertEqual(sig(a), sig(b), "同种子应生成完全相同的地图")

    def test_same_seed_same_initial_state(self):
        a = new_run(self.run, 7)
        b = new_run(self.run, 7)
        self.assertEqual(a.hp, b.hp)
        self.assertEqual(a.max_hp, b.max_hp)
        self.assertEqual(a.gold, b.gold)
        self.assertEqual([c.def_id for c in a.deck], [c.def_id for c in b.deck])
        self.assertEqual([r for r in a.relics], [r for r in b.relics])

    def test_different_seed_differs(self):
        a = new_run(self.run, 42)
        b = new_run(self.run, 43)
        sig = lambda r: [(n.id, n.kind, tuple(n.edges)) for n in r.map_nodes]
        self.assertNotEqual(sig(a), sig(b), "不同种子生成了相同地图")

    def test_rng_is_seeded_instance(self):
        r = new_run(self.run, 5)
        self.assertIsInstance(r.rng, random.Random, "run.rng 必须是 random.Random 实例")

    def test_starter_deck_size(self):
        r = new_run(self.run, 5)
        self.assertEqual(len(r.deck), 10, "初始卡组应为 10 张，实际 %d" % len(r.deck))


class TestMapConnectivity(ContractCase):
    required_module = "core.run"

    def test_every_node_reaches_boss(self):
        """地图连通性：每个节点都必须能到达 boss。"""
        for seed in (1, 2, 3, 42, 777, 20240607):
            r = new_run(self.run, seed)
            nodes = {n.id: n for n in r.map_nodes}
            bosses = [n for n in r.map_nodes if n.kind == "boss"]
            self.assertTrue(bosses, "种子 %d 的地图没有 boss 节点" % seed)
            boss_ids = {b.id for b in bosses}

            # 反向可达：从 boss 反向 BFS
            rev = {nid: [] for nid in nodes}
            for n in r.map_nodes:
                for e in n.edges:
                    self.assertIn(e, nodes, "种子 %d: 节点 %d 的边指向不存在的 %d"
                                  % (seed, n.id, e))
                    rev[e].append(n.id)
            reachable = set(boss_ids)
            stack = list(boss_ids)
            while stack:
                cur = stack.pop()
                for prev in rev[cur]:
                    if prev not in reachable:
                        reachable.add(prev)
                        stack.append(prev)
            unreachable = sorted(set(nodes) - reachable)
            self.assertEqual(unreachable, [],
                             "种子 %d: 以下节点无法到达 boss：%s" % (seed, unreachable[:10]))

    def test_edges_go_forward(self):
        for seed in (1, 99):
            r = new_run(self.run, seed)
            nodes = {n.id: n for n in r.map_nodes}
            for n in r.map_nodes:
                for e in n.edges:
                    self.assertGreater(nodes[e].row, n.row,
                                       "种子 %d: 边 %d(row=%d) -> %d(row=%d) 没有前进"
                                       % (seed, n.id, n.row, e, nodes[e].row))

    def test_node_kinds_valid(self):
        for seed in (1, 5, 42):
            r = new_run(self.run, seed)
            for n in r.map_nodes:
                self.assertIn(n.kind, NODE_KINDS,
                              "种子 %d: 节点 %d kind=%r 非法" % (seed, n.id, n.kind))

    def test_reachable_nodes_from_start(self):
        r = new_run(self.run, 42)
        start = None
        for n in r.map_nodes:
            if n.row == min(x.row for x in r.map_nodes) and (start is None or n.id < start.id):
                start = n
        got = r.reachable_nodes()
        self.assertIsInstance(got, list)
        self.assertTrue(got, "开局没有可选节点")
        # 可达节点必须与当前节点有边相连（或位于首行）
        cur = getattr(r, "current_node", None)
        if cur is None:
            ids = {n.id for n in got}
            first_row = {n.id for n in r.map_nodes if n.row == min(x.row for x in r.map_nodes)}
            self.assertTrue(ids <= first_row,
                            "未开始跑图时 reachable_nodes 应只返回首行节点")

    def test_move_to_is_consistent(self):
        r = new_run(self.run, 42)
        for _ in range(30):
            nxt = r.reachable_nodes()
            if not nxt:
                break
            node = nxt[0]
            d = r.move_to(node.id)
            self.assertIsInstance(d, dict)
            self.assertEqual(r.current_node, node.id)
            if node.kind == "boss":
                break


class TestAscension(ContractCase):
    required_module = "core.run"

    def test_20_tiers_constructible(self):
        for a in range(0, 21):
            try:
                r = new_run(self.run, 3, ascension=a)
            except Exception as exc:
                self.fail("ascension=%d 无法构造 RunState：%r" % (a, exc))
            self.assertEqual(r.ascension, a)

    def test_ascension_out_of_range_clamped_or_rejected(self):
        for bad in (-1, 21, 999):
            try:
                r = new_run(self.run, 3, ascension=bad)
            except Exception:
                continue  # 抛异常也算合法处理
            self.assertGreaterEqual(r.ascension, 0,
                                    "ascension=%d 应被夹到合法区间" % bad)
            self.assertLessEqual(r.ascension, 20,
                                 "ascension=%d 应被夹到合法区间" % bad)

    def test_monotonic_difficulty(self):
        """飞升参数必须单调递增且合法。"""
        params = []
        for a in range(0, 21):
            r = new_run(self.run, 3, ascension=a)
            # 找到 ascension 参数表（不同实现命名不同）
            table = None
            for name in ("ASCENSION_MODS", "ASCENSION_TABLE", "ASCENSION"):
                cand = getattr(self.run, name, None)
                if cand is not None:
                    table = cand
                    break
            params.append((a, r, table))

        # 1) 起始 HP 必须非递增（越难血越少或持平）
        hps = [r.max_hp for _, r, _ in params]
        for i in range(1, len(hps)):
            self.assertLessEqual(hps[i], hps[i - 1],
                                 "起始 max_hp 未随飞升单调下降：%s" % hps)

        # 2) 敌人血量/伤害必须非递减
        enemies, err = load("core.enemies")
        engine, err2 = load("core.engine")
        if enemies is not None and engine is not None and hasattr(engine, "make_enemy_combatant"):
            eid = None
            for e in enemies.ENEMY_DB.values():
                if e.tier == "normal":
                    eid = e.id
                    break
            if eid:
                hpmax = []
                for a in range(0, 21):
                    vals = [engine.make_enemy_combatant(eid, random.Random(i), a, 1).max_hp
                            for i in range(8)]
                    hpmax.append(max(vals))
                for i in range(1, len(hpmax)):
                    self.assertGreaterEqual(hpmax[i], hpmax[i - 1],
                                            "敌人血量未随飞升单调递增：%s" % hpmax)
                self.assertGreater(hpmax[-1], hpmax[0],
                                   "飞升 20 应比飞升 0 更难（敌人血量无变化）")

        # 3) 参数表若存在，逐档检查
        table = params[0][2]
        if isinstance(table, dict):
            keys = sorted(k for k in table if isinstance(k, int))
            if keys:
                self.assertEqual(keys, list(range(min(keys), max(keys) + 1)),
                                 "飞升表档位不连续：%s" % keys)
                self.assertLessEqual(max(keys), 20, "飞升表档位超过 20")

    def test_ascension_affects_something(self):
        """飞升 0 与飞升 20 必须有可观测差异。"""
        lo = new_run(self.run, 3, ascension=0)
        hi = new_run(self.run, 3, ascension=20)
        diffs = []
        if lo.max_hp != hi.max_hp:
            diffs.append("max_hp %s vs %s" % (lo.max_hp, hi.max_hp))
        if lo.gold != hi.gold:
            diffs.append("gold %s vs %s" % (lo.gold, hi.gold))
        if len(lo.deck) != len(hi.deck):
            diffs.append("deck %s vs %s" % (len(lo.deck), len(hi.deck)))
        self.assertTrue(diffs, "飞升 0 与飞升 20 的初始状态完全相同，难度没有差异")


class TestSaveLoad(ContractCase):
    required_module = "core.run"

    def test_to_dict_roundtrip(self):
        r = new_run(self.run, 123)
        d = r.to_dict()
        self.assertIsInstance(d, dict)
        try:
            json.dumps(d)
        except TypeError as exc:
            self.fail("to_dict() 必须可 JSON 序列化：%s" % exc)
        back = self.run.RunState.from_dict(d)
        self.assertEqual(back.hp, r.hp)
        self.assertEqual(back.max_hp, r.max_hp)
        self.assertEqual(back.gold, r.gold)
        self.assertEqual(back.act, r.act)
        self.assertEqual(back.floor, r.floor)
        self.assertEqual(back.ascension, r.ascension)
        self.assertEqual(back.seed, r.seed)
        self.assertEqual([c.def_id for c in back.deck], [c.def_id for c in r.deck])
        self.assertEqual(sorted(back.relics), sorted(r.relics))
        self.assertEqual(len(back.map_nodes), len(r.map_nodes))

    def test_roundtrip_is_stable(self):
        r = new_run(self.run, 321)
        d1 = r.to_dict()
        d2 = self.run.RunState.from_dict(d1).to_dict()
        self.assertEqual(d1, d2, "to_dict/from_dict 往返不稳定（二次序列化不同）")

    def test_roundtrip_preserves_rewards_and_midrun_state(self):
        r = new_run(self.run, 55)
        r.gold = 314
        r.hp = max(1, r.max_hp - 13)
        r.add_card(self.run_card_id(), upgraded=1)
        from core import cards as c
        r.add_relic(next(iter(self.relic_db_ids())))
        d = r.to_dict()
        back = self.run.RunState.from_dict(d)
        self.assertEqual(back.gold, 314)
        self.assertEqual(back.hp, r.hp)
        self.assertEqual(len(back.deck), len(r.deck))
        up = [x for x in back.deck if getattr(x, "upgraded", 0) == 1]
        self.assertEqual(len(up), len([x for x in r.deck if getattr(x, "upgraded", 0) == 1]),
                         "升级状态未在存档中保留")

    def test_roundtrip_after_moving(self):
        r = new_run(self.run, 88)
        nodes = r.reachable_nodes()
        self.assertTrue(nodes)
        r.move_to(nodes[0].id)
        r.floor = 3
        back = self.run.RunState.from_dict(r.to_dict())
        self.assertEqual(back.current_node, r.current_node)
        self.assertEqual(back.floor, r.floor)
        self.assertEqual(sum(1 for n in back.map_nodes if n.visited),
                         sum(1 for n in r.map_nodes if n.visited),
                         "visited 状态未在存档中保留")

    def run_card_id(self):
        from core import cards as c
        return c.STARTER_DECK[0]

    def relic_db_ids(self):
        relics, _ = load("core.relics")
        if relics is None:
            return {"broken_compass"}
        return set(getattr(relics, "RELIC_DB", {}).keys())


class TestRunOperations(ContractCase):
    required_module = "core.run"

    def test_add_remove_upgrade_card(self):
        r = new_run(self.run, 9)
        n0 = len(r.deck)
        from core import cards as c
        r.add_card(c.STARTER_DECK[0])
        self.assertEqual(len(r.deck), n0 + 1)
        new_uid = r.deck[-1].uid
        self.assertFalse(r.upgrade_card(999999), "升级不存在的 uid 应返回 False")
        self.assertTrue(r.upgrade_card(new_uid), "升级存在的卡应返回 True")
        self.assertFalse(r.upgrade_card(new_uid), "重复升级同一张卡应返回 False")
        self.assertTrue(r.remove_card(new_uid), "删除存在的卡应返回 True")
        self.assertEqual(len(r.deck), n0)
        self.assertFalse(r.remove_card(new_uid), "删除已删除的卡应返回 False")

    def test_heal_clamps_to_max(self):
        r = new_run(self.run, 9)
        r.hp = 1
        r.heal(99999)
        self.assertLessEqual(r.hp, r.max_hp, "治疗不应超过 max_hp")
        self.assertGreater(r.hp, 1)

    def test_offer_card_rewards(self):
        r = new_run(self.run, 9)
        got = r.offer_card_rewards(3)
        self.assertEqual(len(got), 3, "应提供 3 张卡，实际 %d" % len(got))
        for cd in got:
            self.assertTrue(cd.id)
        # 不应重复
        self.assertEqual(len({cd.id for cd in got}), len(got), "奖励卡出现重复")

    def test_finish_battle_updates_state(self):
        r = new_run(self.run, 9)
        gold0, floor0 = r.gold, r.floor
        try:
            r.finish_battle("won", None)
        except Exception as exc:
            self.fail("finish_battle 抛异常：%r" % (exc,))
        self.assertGreaterEqual(r.gold, gold0, "胜利后金币不应减少")

    def test_no_exception_leak(self):
        r = new_run(self.run, 9)
        for bad in (999999, -1, "nope"):
            for fn in ("move_to", "remove_card", "upgrade_card"):
                f = getattr(r, fn, None)
                if f is None:
                    continue
                try:
                    f(bad)
                except Exception as exc:
                    self.fail("%s(%r) 抛异常给调用方：%r" % (fn, bad, exc))


class TestMetaProgress(ContractCase):
    """元进度：契约 §7 要求成就 ≥25 个、解锁持久化。"""

    required_module = "core.run"

    def _meta(self):
        cls = getattr(self.run, "MetaProgress", None)
        self.assertIsNotNone(cls, "缺少 MetaProgress 类")
        return cls()

    def test_meta_api_surface(self):
        m = self._meta()
        for attr in ("ascension_unlocked", "total_runs", "wins", "best_score",
                     "seen_cards", "seen_relics", "seen_enemies", "achievements"):
            self.assertTrue(hasattr(m, attr), "MetaProgress 缺少 %s" % attr)
        # achievements 是「已解锁成就」的字典（初始为空）；成就**目录**是 ACHIEVEMENTS
        self.assertIsInstance(m.achievements, dict,
                              "achievements 应为已解锁成就的 dict")
        self.assertIsInstance(m.seen_cards, set)

    def test_achievement_catalog_has_at_least_25(self):
        """契约 ≥25 个成就 —— 目录在 ACHIEVEMENTS（不是实例的 achievements）。"""
        cat = getattr(self.run, "ACHIEVEMENTS", None)
        self.assertIsNotNone(cat, "缺少 ACHIEVEMENTS 成就目录")
        self.assertGreaterEqual(len(cat), 25,
                                "成就目录只有 %d 个（契约 ≥25）" % len(cat))
        for k, v in cat.items():
            self.assertTrue(k, "成就 key 为空")
            self.assertTrue(v, "成就 %r 缺少描述" % k)

    def test_unlock_accepts_real_key(self):
        """unlock() 只接受目录里已定义的 key（防止拼写错误写入垃圾成就）。"""
        cat = getattr(self.run, "ACHIEVEMENTS", {})
        self.assertTrue(cat, "没有成就目录可测")
        key = next(iter(cat))
        m = self._meta()
        self.assertTrue(m.unlock(key), "unlock(%r) 对合法成就 key 应返回 True" % key)
        self.assertIn(key, m.achievements,
                      "unlock(%r) 后 achievements 应记录该成就" % key)

    def test_unlock_rejects_unknown_key(self):
        m = self._meta()
        self.assertFalse(m.unlock("__not_a_real_achievement__"),
                         "unlock() 应拒绝未定义的成就 key")

    def test_meta_save_load_roundtrip(self):
        m = self._meta()
        cat = getattr(self.run, "ACHIEVEMENTS", {})
        if cat:
            m.unlock(next(iter(cat)))
        d = None
        for name in ("to_dict", "as_dict"):
            f = getattr(m, name, None)
            if callable(f):
                d = f()
                break
        if d is None:
            self.skipTest("MetaProgress 没有 to_dict/as_dict，跳过序列化检查")
        self.assertIsInstance(d, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
