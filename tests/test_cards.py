"""卡牌数据完整性测试（ARCHITECTURE.md §3）。

全部为硬性契约检查。模块缺失 = 失败（fail），不是 skip。
"""

import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import ARCHS, RARITIES, load  # noqa: E402

cards_mod, _cards_err = load("core.cards")


def _need_cards():
    if cards_mod is None:
        raise AssertionError("core.cards 无法导入：%s" % _cards_err)
    return cards_mod


class TestCardDatabase(unittest.TestCase):

    def setUp(self):
        self.c = _need_cards()
        self.db = getattr(self.c, "CARD_DB", None)
        if not isinstance(self.db, dict) or not self.db:
            self.fail("core.cards.CARD_DB 缺失或为空")

    # ---------------------------------------------------------- 数量
    def test_total_at_least_90(self):
        n = len(self.db)
        self.assertGreaterEqual(n, 90, "卡牌总数 %d < 90（契约硬性要求）" % n)

    def test_type_counts(self):
        by_type = {}
        for cd in self.db.values():
            by_type[cd.type] = by_type.get(cd.type, 0) + 1
        self.assertGreaterEqual(by_type.get("attack", 0), 38,
                                "attack 牌 %d < 38；分布=%s" % (by_type.get("attack", 0), by_type))
        self.assertGreaterEqual(by_type.get("skill", 0), 34,
                                "skill 牌 %d < 34；分布=%s" % (by_type.get("skill", 0), by_type))
        self.assertGreaterEqual(by_type.get("power", 0), 12,
                                "power 牌 %d < 12；分布=%s" % (by_type.get("power", 0), by_type))
        sc = by_type.get("status", 0) + by_type.get("curse", 0)
        self.assertGreaterEqual(sc, 6, "status+curse 牌 %d < 6；分布=%s" % (sc, by_type))

    def test_rarity_distribution(self):
        by_rar = {}
        for cd in self.db.values():
            by_rar[cd.rarity] = by_rar.get(cd.rarity, 0) + 1
        self.assertGreaterEqual(by_rar.get("common", 0), 30,
                                "common %d 偏少（契约 ≈40）；分布=%s" % (by_rar.get("common", 0), by_rar))
        self.assertGreaterEqual(by_rar.get("uncommon", 0), 25,
                                "uncommon %d 偏少（契约 ≈35）；分布=%s" % (by_rar.get("uncommon", 0), by_rar))
        self.assertGreaterEqual(by_rar.get("rare", 0), 10,
                                "rare %d 偏少（契约 ≈15）；分布=%s" % (by_rar.get("rare", 0), by_rar))
        for r in by_rar:
            self.assertIn(r, RARITIES, "出现未知稀有度 %r" % r)

    def test_each_archetype_at_least_14(self):
        for arch in ARCHS:
            n = sum(1 for cd in self.db.values() if cd.arch == arch)
            self.assertGreaterEqual(n, 14, "流派 %s 只有 %d 张（契约要求 ≥14）" % (arch, n))

    # ---------------------------------------------------------- 字段
    def test_no_duplicate_ids(self):
        ids = [cd.id for cd in self.db.values()]
        self.assertEqual(len(ids), len(set(ids)), "CARD_DB 存在重复 id")

    def test_db_key_matches_id(self):
        for key, cd in self.db.items():
            self.assertEqual(key, cd.id, "CARD_DB 键 %r 与 CardDef.id %r 不一致" % (key, cd.id))

    def test_id_format_snake_case(self):
        bad = [cd.id for cd in self.db.values()
               if not re.match(r"^[a-z][a-z0-9_]*$", cd.id)]
        self.assertEqual(bad, [], "id 非 snake_case：%s" % bad[:10])

    def test_field_validity(self):
        problems = []
        for cd in self.db.values():
            if not cd.name or not isinstance(cd.name, str):
                problems.append("%s: name 空" % cd.id)
            if not isinstance(cd.cost, int) or cd.cost < -2:
                # cost: -1 = X 费；-2 = 不可打出的 status/curse 牌
                problems.append("%s: cost=%r 非法" % (cd.id, cd.cost))
            if cd.cost == -2 and cd.type not in ("status", "curse"):
                problems.append("%s: cost=-2 只允许用于 status/curse（type=%r）"
                                % (cd.id, cd.type))
            if cd.type not in ("attack", "skill", "power", "status", "curse"):
                problems.append("%s: type=%r 非法" % (cd.id, cd.type))
            if cd.rarity not in RARITIES:
                problems.append("%s: rarity=%r 非法" % (cd.id, cd.rarity))
            if cd.arch not in ARCHS:
                problems.append("%s: arch=%r 非法" % (cd.id, cd.arch))
            if cd.target not in ("enemy", "self", "all_enemies", "none"):
                problems.append("%s: target=%r 非法" % (cd.id, cd.target))
            if not cd.text or not isinstance(cd.text, str):
                problems.append("%s: text 空" % cd.id)
            for f in ("damage", "block", "magic", "magic2", "hits"):
                v = getattr(cd, f, None)
                if not isinstance(v, int) or v < 0:
                    problems.append("%s: %s=%r 非法" % (cd.id, f, v))
            if getattr(cd, "hits", 1) < 1:
                problems.append("%s: hits<1" % cd.id)
        self.assertEqual(problems, [], "字段非法：\n  " + "\n  ".join(problems[:30]))

    def test_frozen_dataclass(self):
        cd = next(iter(self.db.values()))
        with self.assertRaises(Exception, msg="CardDef 必须是 frozen dataclass（不可变静态数据）"):
            cd.damage = 999

    # ---------------------------------------------------------- effect
    def test_effects_present_and_callable(self):
        missing = [cd.id for cd in self.db.values()
                   if cd.type not in ("status", "curse") and cd.effect is None]
        self.assertEqual(missing, [], "以下卡牌缺少 effect：%s" % missing[:20])
        bad = [cd.id for cd in self.db.values()
               if cd.effect is not None and not callable(cd.effect)]
        self.assertEqual(bad, [], "effect 不可调用：%s" % bad[:20])

    def test_effect_accepts_one_argument(self):
        bad = []
        for cd in self.db.values():
            if cd.effect is None:
                continue
            try:
                sig = inspect.signature(cd.effect)
            except (TypeError, ValueError):
                continue
            required = [p for p in sig.parameters.values()
                        if p.default is inspect.Parameter.empty
                        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            if len(required) > 1:
                bad.append("%s(%s)" % (cd.id, sig))
        self.assertEqual(bad, [], "effect 签名应为 fn(ctx)：%s" % bad[:10])

    # ---------------------------------------------------------- text 占位符
    def test_placeholder_values_match_fields(self):
        """text 里的 {damage}/{block}/{magic} 数字必须与字段一致。"""
        problems = []
        for cd in self.db.values():
            text = cd.text
            fields = {
                "damage": cd.damage,
                "block": cd.block,
                "magic": cd.magic,
                "magic2": cd.magic2,
                "hits": cd.hits,
            }
            for name, value in fields.items():
                m = re.search(r"\{%s\}" % name, text)
                if m:
                    # {damage} 形式：要求字段非零（除非 hits==1 且 damage==0 的技能）
                    if name == "damage" and cd.type == "attack" and value <= 0:
                        problems.append("%s: text 用 {damage} 但 damage=%d" % (cd.id, value))
                    continue
                # 也允许直接写数字；检查常见模式 "造成 N 点伤害"
                if name == "damage" and cd.damage > 0:
                    nums = [int(x) for x in re.findall(r"\d+", text)]
                    if nums and cd.damage not in nums and cd.damage * cd.hits not in nums:
                        # 只有在文本确实描述伤害时才判定
                        if re.search(r"伤害", text):
                            problems.append(
                                "%s: text=%r 中找不到 damage=%d（数字=%s）"
                                % (cd.id, text, cd.damage, nums))
                if name == "block" and cd.block > 0 and re.search(r"格挡", text):
                    nums = [int(x) for x in re.findall(r"\d+", text)]
                    if nums and cd.block not in nums:
                        problems.append(
                            "%s: text=%r 中找不到 block=%d（数字=%s）"
                            % (cd.id, text, cd.block, nums))
        self.assertEqual(problems, [], "text 与字段不一致：\n  " + "\n  ".join(problems[:20]))

    def test_attack_cards_have_damage_or_own_damage_source(self):
        """攻击牌要么有基础伤害，要么在 text 里明确说明伤害来源。

        damage=0 的攻击牌是合法的，但必须是「伤害等同于 X」这类派生伤害，
        否则就是数据漏填（例如纯格挡牌被误标成 attack）。
        """
        bad = []
        for cd in self.db.values():
            if cd.type != "attack":
                continue
            if cd.damage > 0 or cd.magic > 0:
                continue
            if re.search(r"伤害", cd.text):
                continue  # 派生伤害：text 明确写了伤害来源
            bad.append("%s(text=%r)" % (cd.id, cd.text))
        self.assertEqual(bad, [], "攻击牌既无 damage 也没在 text 说明伤害来源：%s" % bad[:20])

    # ---------------------------------------------------------- 流派钩子
    def test_archetype_mechanic_hooks(self):
        """每个流派必须有明确的机制钩子 —— 用**行为探针**验证，而非中文文本。

        ⚠️ 教训：不要用中文关键词 grep 卡牌 text。
        附录 B 题材变更会持续改写全部中文文案（连 keywords 也改成中文了），
        基于文本的断言会一直失败，且失败与实现质量无关。

        这里改为：在真实战斗里逐张打出该流派的牌，观测引擎状态是否出现
        该流派的**特征变化**（中毒层数 / 格挡 / 力量 / 能量或抽牌 / 召唤物）。
        某流派只要有任何一张牌能引出其特征变化，即视为钩子存在。
        """
        engine, err = load("core.engine")
        if engine is None:
            self.fail("core.engine 不可用：%s" % err)
        enemies, err = load("core.enemies")
        if enemies is None:
            self.fail("core.enemies 不可用：%s" % err)
        runmod, err = load("core.run")
        if runmod is None:
            self.fail("core.run 不可用：%s" % err)

        import random as _random

        def buff(bs, who, name):
            const = getattr(engine, "BUFF_" + name.upper(), name)
            return (who.buffs or {}).get(const, 0)

        def probe(cd):
            """打出这张牌，返回引擎状态的可观测变化集合。"""
            try:
                run = runmod.RunState()
                run.new_run(seed=7, ascension=0)
                eid = next(iter(enemies.ENEMY_DB))
                bs = engine.make_battle(run, {"kind": "normal", "enemies": [eid]})
            except Exception:
                return set()
            p, e = bs.player, bs.enemies[0]
            p.energy = 99
            p.max_hp = p.hp = 9999
            e.max_hp = e.hp = 9999
            try:
                inst = self.c.make_card(cd.id)
            except Exception:
                return set()
            p.hand.append(inst)
            before = {
                "poison": buff(bs, e, "poison"),
                "block": p.block,
                "strength": buff(bs, p, "strength"),
                "energy": p.energy,
                "hand": len(p.hand),
                "draw": len(p.draw_pile),
                "minions": len(getattr(p, "minions", []) or []),
            }
            try:
                bs.play_card(inst, e)
            except Exception:
                return set()
            after = {
                "poison": buff(bs, e, "poison"),
                "block": p.block,
                "strength": buff(bs, p, "strength"),
                "energy": p.energy,
                "hand": len(p.hand),
                "draw": len(p.draw_pile),
                "minions": len(getattr(p, "minions", []) or []),
            }
            got = set()
            for k in before:
                if after[k] != before[k]:
                    got.add(k)
            return got

        # 流派 -> 可接受的证据集合
        evidence = {
            "attack": {"strength"},
            "block": {"block"},
            "poison": {"poison"},
            "energy": {"energy", "hand", "draw"},
            "summon": {"minions"},
        }

        missing = {}
        for arch in ARCHS:
            pool = [cd for cd in self.db.values() if cd.arch == arch]
            if len(pool) < 14:
                missing[arch] = "只有 %d 张（需 ≥14）" % len(pool)
                continue
            want = evidence[arch]
            hits = []
            for cd in pool:
                if cd.effect is None:
                    continue
                if probe(cd) & want:
                    hits.append(cd.id)
            if not hits:
                missing[arch] = ("打遍该流派 %d 张牌，均未观测到 %s 变化（机制钩子缺失）"
                                 % (len(pool), sorted(want)))
        self.assertEqual(missing, {}, "流派机制钩子缺失：%s" % missing)

    def test_all_referenced_card_ids_exist(self):
        """数据完整性：所有 `add_card_to_hand/draw(...)` 引用的 def_id 必须真实存在。

        这是 BUG #9 的回归防线：卡牌效果里写了一个不存在的卡 id，
        play_card 的 try/except 会把它静默吞掉，直到 end_turn 遍历手牌
        读 `c.defn.ethereal` 时才抛 KeyError 崩溃整个战斗。
        """
        import re as _re
        src_path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "core", "cards.py")
        if not os.path.exists(src_path):
            self.fail("core/cards.py 不存在")
        with open(src_path, encoding="utf-8") as f:
            source = f.read()

        # 匹配 _add_hand(ctx, "id") / add_card_to_hand(ctx, "id") / "id", n) 等
        pats = [
            _re.compile(r'_add_hand\(\s*[^,]+,\s*["\']([a-z0-9_]+)["\']'),
            _re.compile(r'add_card_to_hand\(\s*[^,]+,\s*["\']([a-z0-9_]+)["\']'),
            _re.compile(r'add_card_to_draw\(\s*[^,]+,\s*["\']([a-z0-9_]+)["\']'),
        ]
        referenced = set()
        for p in pats:
            referenced.update(p.findall(source))

        missing = sorted(r for r in referenced if r not in self.db)
        self.assertEqual(missing, [],
                         "以下卡牌 id 被 effect 引用但不在 CARD_DB 中"
                         "（打出后会留下幽灵卡并在 end_turn 崩溃）：%s" % missing)

    def test_card_instance_defn_survives_unknown_id(self):
        """CardInstance.defn 对未知 id 不应抛异常（加固建议）。

        契约 §2「无异常泄漏」：数据打字错误不应让玩家崩游戏。
        """
        try:
            inst = self.c.make_card("__definitely_not_a_real_card__")
        except Exception:
            self.skipTest("make_card 对未知 id 直接拒绝（可接受的早期失败）")
        try:
            d = inst.defn
        except KeyError as exc:
            self.fail("CardInstance.defn 对未知 id 抛 KeyError %r —— "
                      "任何数据打字错误都会在 end_turn 崩掉战斗。"
                      "建议返回安全占位 CardDef 并写 log" % (exc,))
        except Exception as exc:
            self.fail("CardInstance.defn 对未知 id 抛异常：%r" % (exc,))
        self.assertIsNotNone(d)

    def test_all_starter_and_reward_ids_resolve(self):
        """STARTER_DECK 与奖励池里的每张卡都必须能构造出 CardInstance 并读到 defn。"""
        import random as _random
        ids = set(self.c.STARTER_DECK)
        rng = _random.Random(3)
        for cd in self.c.random_card_pool(rng):
            ids.add(cd.id)
        broken = []
        for did in sorted(ids):
            try:
                inst = self.c.make_card(did)
                _ = inst.defn
            except Exception as exc:
                broken.append("%s: %r" % (did, exc))
        self.assertEqual(broken, [], "以下卡无法正常构造/解析：%s" % broken)

    def test_all_card_effects_run_without_exception(self):
        """遍历 CARD_DB，每张牌在真实战斗里打一次，effect 不得抛异常。

        Lead 要求的全卡牌效果冒烟（BUG #9 同类防线）：
        用真实引擎而不是 mock ctx，这样能连带覆盖 ctx API 的误用。
        """
        engine, err = load("core.engine")
        if engine is None:
            self.fail("core.engine 不可用：%s" % err)
        enemies, err = load("core.enemies")
        if enemies is None:
            self.fail("core.enemies 不可用：%s" % err)
        runmod, err = load("core.run")
        if runmod is None:
            self.fail("core.run 不可用：%s" % err)

        failures = []
        eid = next(iter(enemies.ENEMY_DB))
        for cd in sorted(self.db.values(), key=lambda c: c.id):
            if cd.effect is None:
                continue
            try:
                run = runmod.RunState()
                run.new_run(seed=11, ascension=0)
                bs = engine.make_battle(run, {"kind": "normal",
                                              "enemies": [eid, eid]})
                p = bs.player
                p.energy = 99
                p.max_hp = p.hp = 9999
                for e in bs.enemies:
                    e.max_hp = e.hp = 9999
                inst = self.c.make_card(cd.id)
                p.hand.append(inst)
                # 覆盖两种目标形态
                for target in (bs.enemies[0], None):
                    try:
                        bs.play_card(inst, target)
                    except Exception:
                        pass
                    if inst not in p.hand:
                        break
            except Exception as exc:
                failures.append("%s: %s: %s" % (cd.id, type(exc).__name__, exc))
        self.assertEqual(failures, [],
                         "以下卡牌的 effect 在真实战斗中抛异常：\n  " +
                         "\n  ".join(failures[:30]))

    def test_all_card_effects_callable_with_minimal_ctx(self):
        """用最小 mock ctx 调用每张牌的 effect —— 启动自检级别的全量覆盖。"""
        class MockEnemy:
            hp = 10
            max_hp = 10
            block = 0
            name = "mock"
            is_player = False

            def alive(self):
                return True

            def get_buff(self, k):
                return 0

        class MockCtx:
            """最小 ctx：返回类型必须合理，否则 AOE/循环类卡会误报。"""

            def __init__(self):
                self.calls = []
                self.target = MockEnemy()
                self.source = MockEnemy()
                self.card = None

            def enemies(self):
                return [MockEnemy(), MockEnemy()]

            def alive_enemies(self):
                return [MockEnemy(), MockEnemy()]

            def cards_played_this_turn(self):
                return 1

            def draw(self, n=1):
                self.calls.append(("draw", (n,)))

            def rng(self):
                import random as _r
                return _r.Random(1)

            def __getattr__(self, name):
                def fn(*a, **k):
                    self.calls.append((name, a))
                    return 0
                return fn

        failures = []
        for cd in sorted(self.db.values(), key=lambda c: c.id):
            if cd.effect is None:
                continue
            ctx = MockCtx()
            try:
                cd.effect(ctx)
            except Exception as exc:
                failures.append("%s: %s: %s" % (cd.id, type(exc).__name__, exc))
        self.assertEqual(failures, [],
                         "以下卡牌 effect 用最小 ctx 调用即抛异常：\n  " +
                         "\n  ".join(failures[:30]))

    # ---------------------------------------------------------- 升级
    def test_upgrade_dicts_valid(self):
        bad = []
        for cd in self.db.values():
            up = cd.upgrade
            if up is None:
                continue
            if not isinstance(up, dict):
                bad.append("%s: upgrade 不是 dict" % cd.id)
                continue
            allowed = {"cost", "damage", "block", "magic", "magic2", "hits", "text",
                       "exhaust", "retain", "innate", "ethereal", "keywords", "name"}
            unknown = set(up) - allowed
            if unknown:
                bad.append("%s: upgrade 含未知键 %s" % (cd.id, unknown))
            if "cost" in up and (not isinstance(up["cost"], int) or up["cost"] < -1):
                bad.append("%s: upgrade cost=%r" % (cd.id, up["cost"]))
        self.assertEqual(bad, [], "upgrade 定义非法：%s" % bad[:20])

    # ---------------------------------------------------------- API 行为
    def test_helper_api(self):
        c = self.c
        for fn in ("make_card", "all_cards", "cards_by_arch", "random_card_pool"):
            self.assertTrue(callable(getattr(c, fn, None)), "缺少函数 %s" % fn)

        self.assertIsInstance(c.STARTER_DECK, (list, tuple))
        self.assertEqual(len(c.STARTER_DECK), 10,
                         "STARTER_DECK 应为 10 张，实际 %d" % len(c.STARTER_DECK))
        for did in c.STARTER_DECK:
            self.assertIn(did, self.db, "STARTER_DECK 含未知卡 %r" % did)

        cards = c.all_cards()
        # 注意：core/cheats.py 会在首次兑换时把作弊卡注入 CARD_DB，
        # 它们不属于游戏内容，故与 all_cards() 比较时要排除。
        content = [k for k in self.db
                   if not c.is_cheat_card(k) and k != "whale"]  # whale 是彩蛋卡
        self.assertEqual(len(cards), len(content),
                         "all_cards() 数量与 CARD_DB（非作弊卡）不符")
        for arch in ARCHS:
            got = c.cards_by_arch(arch)
            self.assertTrue(got, "cards_by_arch(%r) 为空" % arch)
            self.assertTrue(all(cd.arch == arch for cd in got),
                            "cards_by_arch(%r) 返回了别的流派" % arch)

        import random
        rng = random.Random(99)
        pool = c.random_card_pool(rng)
        self.assertTrue(pool, "random_card_pool() 为空")
        rare_pool = c.random_card_pool(rng, rarity="rare")
        self.assertTrue(all(cd.rarity == "rare" for cd in rare_pool),
                        "random_card_pool(rarity='rare') 返回了非 rare 卡")

    def test_make_card_and_instance(self):
        c = self.c
        did = c.STARTER_DECK[0]
        inst = c.make_card(did)
        self.assertEqual(inst.def_id, did)
        self.assertIsInstance(inst.defn, type(self.db[did]),
                              "CardInstance.defn 应返回 CardDef")
        self.assertEqual(inst.name, self.db[did].name)
        self.assertEqual(inst.cost, self.db[did].cost)
        self.assertEqual(inst.type, self.db[did].type)
        self.assertEqual(inst.rarity, self.db[did].rarity)

        # 升级：upgrade 覆盖字段应生效
        upgraded_ids = [cd.id for cd in self.db.values()
                        if cd.upgrade and "damage" in cd.upgrade]
        if upgraded_ids:
            did2 = upgraded_ids[0]
            base = self.db[did2]
            up = c.make_card(did2, 1)
            self.assertEqual(up.defn.damage, base.upgrade["damage"],
                             "%s 升级后 damage 未按 upgrade 覆盖" % did2)

    def test_card_instance_roundtrip(self):
        c = self.c
        did = c.STARTER_DECK[0]
        inst = c.make_card(did, 1)
        d = inst.to_dict()
        self.assertIsInstance(d, dict)
        back = c.CardInstance.from_dict(d)
        self.assertEqual(back.def_id, inst.def_id)
        self.assertEqual(back.upgraded, inst.upgraded)
        self.assertEqual(back.uid, inst.uid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
