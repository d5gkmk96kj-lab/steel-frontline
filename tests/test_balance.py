"""蒙特卡洛平衡性测试（ARCHITECTURE.md §9）。

写一个**贪心 AI 自动出牌**，全自动跑完 ≥2000 场战斗，
输出各飞升档胜率表，并对异常区间报警。

异常判据（题目给定）：
- act1 普通战胜率 < 85%
- 通关率 0% 或 > 60%

本文件不在 unittest discover 中做 2000 场重负载（那样太慢）；
它在被单独调用时跑全量，在 discover 中跑缩减版 smoke。
全量方式：`python3 tests/test_balance.py --full`
"""

import os
import random
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import alive_enemies, ContractCase, load  # noqa: E402

ASCENSIONS = list(range(0, 21))


# ------------------------------------------------------------------ 引擎适配
class EngineAdapter:
    """把不同实现的引擎包装成统一驱动接口。"""

    def __init__(self):
        self.engine, e1 = load("core.engine")
        self.enemies, e2 = load("core.enemies")
        self.runmod, e3 = load("core.run")
        self.cards, e4 = load("core.cards")
        self.relics, e5 = load("core.relics")
        self.crashes = []
        for mod, err, name in ((self.engine, e1, "core.engine"),
                               (self.enemies, e2, "core.enemies"),
                               (self.runmod, e3, "core.run"),
                               (self.cards, e4, "core.cards")):
            if mod is None:
                raise AssertionError("%s 不可用：%s" % (name, err))

    # ---------------------------------------------------- 构造
    def new_run(self, seed, ascension):
        r = self.runmod.RunState()
        r.new_run(seed=seed, ascension=ascension)
        return r

    def encounter_for(self, act, kind, rng=None):
        """取一个真实的 encounter dict。

        真实结构（已实测）：ENCOUNTERS[act][kind] = [ {"kind":..,"enemies":[id,...]}, ... ]
        ⚠️ 注意：元素**本身就是** encounter dict，不是 id 列表。
        verifier 初版把元素当成 id 列表遍历，导致拿到 dict 的 key
        （'kind'/'enemies'）当敌人 id，战斗退化成必赢 —— 那一版 100% 通关率是假的。
        """
        enc = getattr(self.enemies, "ENCOUNTERS", {})
        entry = enc.get(act) or enc.get(str(act)) or {}
        pool = entry.get(kind) or []
        if pool:
            pick = rng.choice(pool) if rng is not None else pool[0]
            if isinstance(pick, dict) and "enemies" in pick:
                ids = list(pick["enemies"])
                return {"kind": pick.get("kind", kind), "enemies": ids}
            if isinstance(pick, str):
                return {"kind": kind, "enemies": [pick]}
            if isinstance(pick, (list, tuple)):
                # 兼容「元素是 id 列表」的写法
                flat = []
                for x in pick:
                    if isinstance(x, str):
                        flat.append(x)
                    elif isinstance(x, (list, tuple)):
                        flat.extend(y for y in x if isinstance(y, str))
                if flat:
                    return {"kind": kind, "enemies": flat}
        # 退化：从 ENEMY_DB 直接挑
        db = self.enemies.ENEMY_DB
        wanted = {"elite": "elite", "boss": "boss"}.get(kind, "normal")
        cands = [e.id for e in db.values()
                 if e.tier == wanted and e.act == act] or \
                [e.id for e in db.values() if e.tier == wanted]
        if not cands:
            cands = [next(iter(db))]
        return {"kind": kind, "enemies": [cands[0]]}

    def validate_encounters(self):
        """自检：所有 encounter 里的 enemy id 必须存在于 ENEMY_DB。"""
        bad = []
        db = self.enemies.ENEMY_DB
        for act, kinds in getattr(self.enemies, "ENCOUNTERS", {}).items():
            for kind, pool in kinds.items():
                for pick in pool:
                    if not isinstance(pick, dict):
                        bad.append("act%s/%s: 元素不是 dict: %r" % (act, kind, pick))
                        continue
                    for eid in pick.get("enemies", []):
                        if eid not in db:
                            bad.append("act%s/%s: 未知敌人 id %r" % (act, kind, eid))
        return bad

    def make_battle(self, run, encounter):
        return self.engine.make_battle(run, encounter)

    # ---------------------------------------------------- 驱动
    def player_turn(self, bs, rng, max_actions=200):
        """贪心 AI：优先能击杀的攻击牌 → 攻击牌 → 技能牌 → 能力牌。"""
        played = 0
        for _ in range(max_actions):
            options = []
            for c in list(getattr(bs.player, "hand", []) or []):
                try:
                    if not bs.can_play(c):
                        continue
                except Exception:
                    continue
                options.append(c)
            if not options:
                break
            target = None
            alive = alive_enemies(bs)
            if alive:
                target = min(alive, key=lambda e: e.hp)

            def score(c):
                t = getattr(c, "type", "")
                dmg = getattr(c, "damage", 0) or getattr(getattr(c, "defn", None), "damage", 0)
                blk = getattr(c, "block", 0) or getattr(getattr(c, "defn", None), "block", 0)
                s = 0
                if t == "attack":
                    s += 100 + dmg * 3
                    if target is not None and dmg >= target.hp:
                        s += 500  # 能击杀优先
                elif t == "power":
                    s += 60
                elif t == "skill":
                    s += 40 + blk * 2
                else:
                    s -= 1000
                if getattr(c, "cost", 0) == -2:
                    s -= 1000
                return s

            options.sort(key=score, reverse=True)
            progressed = False
            for c in options:
                tgt = target
                try:
                    ctype = getattr(c, "type", "")
                    defn = getattr(c, "defn", None)
                    ctarget = getattr(defn, "target", None)
                    if ctarget in ("self", "none"):
                        tgt = None
                except Exception:
                    pass
                try:
                    ok = bs.play_card(c, tgt)
                except Exception:
                    ok = False
                if ok:
                    played += 1
                    progressed = True
                    break
            if not progressed:
                break
        return played

    def battle(self, run, encounter, rng, max_turns=80):
        """跑完一整场战斗，返回 "won"/"lost"。"""
        bs = self.make_battle(run, encounter)
        for _ in range(max_turns):
            res = bs.result()
            if res != "ongoing":
                return res
            if bs.phase == "player":
                self.player_turn(bs, rng)
                if bs.result() != "ongoing":
                    return bs.result()
                try:
                    bs.end_turn()
                except Exception as exc:
                    # 引擎在 end_turn 抛异常 = 真实缺陷（契约 §2 禁止异常泄漏）。
                    # 记录下来继续跑，否则整个蒙特卡洛会被一处数据错误阻断，
                    # 拿不到任何平衡性数据。
                    self.crashes.append("%s: %s" % (type(exc).__name__, exc))
                    return "crash"
            else:
                guard = 0
                ret = True
                while ret and guard < 100:
                    ret = bs.enemy_step()
                    guard += 1
                if bs.result() != "ongoing":
                    return bs.result()
        return "timeout"


# ------------------------------------------------------------------ 模拟器
def simulate_one(adapter, seed, ascension, floors=15):
    """模拟一局：连续打 floors 场战斗（含精英/BOSS），返回终局结果。

    用真实 RunState 的 hp/gold/deck 延续状态，近似真实跑图。
    """
    rng = random.Random(seed)
    try:
        run = adapter.new_run(seed, ascension)
    except Exception:
        return {"result": "error", "error": "new_run failed"}

    act = 1
    for floor in range(1, floors + 1):
        if floor % 5 == 0:
            kind = "boss"
        elif floor % 4 == 0:
            kind = "elite"
        else:
            kind = "normal"
        if floor > 10:
            act = min(3, act + 1) if floor == 11 else act
        enc = adapter.encounter_for(act, kind, rng)
        res = adapter.battle(run, enc, rng)
        if res == "timeout":
            return {"result": "timeout", "floor": floor, "kind": kind}
        if res == "crash":
            return {"result": "crash", "floor": floor, "kind": kind}
        if res == "lost":
            return {"result": "lost", "floor": floor, "kind": kind}

        # 战后：回血 + 成长（简化，但用真实 RunState 接口）
        try:
            if hasattr(run, "heal"):
                run.heal(max(1, int(run.max_hp * 0.10)))
            if hasattr(run, "add_card"):
                pool = adapter.cards.random_card_pool(rng)
                if pool:
                    run.add_card(rng.choice(pool).id)
            if hasattr(run, "add_relic"):
                pool = list(getattr(adapter.relics, "RELIC_DB", {}) or {})
                if pool:
                    run.add_relic(rng.choice(pool))
        except Exception:
            pass
    return {"result": "won", "floor": floors}


def run_matrix(adapter, n_per_ascension, ascensions=ASCENSIONS, progress=None):
    """跑胜率矩阵：{ascension: {"wins":int,"losses":int,"rate":float,...}}"""
    table = {}
    for a in ascensions:
        wins = losses = timeouts = crashes = 0
        act1_win = act1_total = 0
        for i in range(n_per_ascension):
            out = simulate_one(adapter, seed=100000 + i * 7 + a, ascension=a)
            if out["result"] == "won":
                wins += 1
            elif out["result"] == "lost":
                losses += 1
            elif out["result"] == "crash":
                crashes += 1
            else:
                timeouts += 1
            if out.get("floor", 99) >= 1:
                act1_total += 1
                if out["result"] == "won" or out.get("floor", 0) > 1:
                    act1_win += 1
        total = wins + losses + timeouts + crashes
        table[a] = {
            "n": total, "wins": wins, "losses": losses, "timeouts": timeouts,
            "crashes": crashes,
            "rate": (wins / total) if total else 0.0,
            "act1_rate": (act1_win / act1_total) if act1_total else 0.0,
        }
        if progress:
            progress(a, table[a])
    return table


def act1_normal_winrate(adapter, n=300, ascension=0):
    """单独测 act1 普通战胜率（判据 <85% 报警）。"""
    rng = random.Random(1)
    wins = 0
    for i in range(n):
        run = adapter.new_run(seed=5000 + i, ascension=ascension)
        enc = adapter.encounter_for(1, "normal")
        r = adapter.battle(run, enc, rng)
        if r == "won":
            wins += 1
    return wins / float(n), n


def format_table(table):
    lines = ["飞升 |   场次 |   胜 |   负 | 超时 | 崩溃 |  通关率 | act1率",
             "-----+--------+------+------+------+------+---------+-------"]
    for a in sorted(table):
        t = table[a]
        lines.append("%4d | %6d | %4d | %4d | %4d | %4d | %6.1f%% | %5.1f%%"
                     % (a, t["n"], t["wins"], t["losses"], t["timeouts"],
                        t.get("crashes", 0),
                        t["rate"] * 100, t["act1_rate"] * 100))
    return "\n".join(lines)


class TestBalanceSmoke(ContractCase):
    """discover 下的轻量版：验证平衡测试基础设施可跑通 + act1 胜率。"""

    required_module = "core.engine"

    def test_adapter_constructs(self):
        ad = EngineAdapter()
        run = ad.new_run(1, 0)
        self.assertIsNotNone(run)
        enc = ad.encounter_for(1, "normal")
        self.assertIn("enemies", enc)
        self.assertTrue(enc["enemies"])
        bs = ad.make_battle(run, enc)
        self.assertIsNotNone(bs)

    def test_encounter_ids_are_valid(self):
        """所有 ENCOUNTERS 里的敌人 id 必须真实存在（否则战斗退化/崩溃）。"""
        ad = EngineAdapter()
        bad = ad.validate_encounters()
        self.assertEqual(bad, [], "ENCOUNTERS 数据非法：%s" % bad[:20])

    def test_encounter_is_real_composition(self):
        """encounter 必须真的是敌人 id 列表，而不是 dict 的 key。"""
        ad = EngineAdapter()
        for act in (1, 2, 3):
            for kind in ("normal", "elite", "boss"):
                enc = ad.encounter_for(act, kind)
                self.assertIsInstance(enc, dict)
                ids = enc["enemies"]
                self.assertTrue(ids, "act%d/%s encounter 为空" % (act, kind))
                for eid in ids:
                    self.assertIsInstance(eid, str,
                                          "act%d/%s 的敌人项不是 str: %r" % (act, kind, eid))
                    self.assertIn(eid, ad.enemies.ENEMY_DB,
                                  "act%d/%s 引用了未知敌人 %r" % (act, kind, eid))

    def test_single_simulation_completes(self):
        ad = EngineAdapter()
        out = simulate_one(ad, seed=1, ascension=0, floors=3)
        self.assertIn(out["result"], ("won", "lost", "timeout"),
                      "单局模拟结果非法：%r" % out)
        self.assertNotEqual(out["result"], "error", "单局模拟报错：%r" % out)

    def test_act1_normal_winrate_smoke(self):
        """小样本 act1 普通战胜率（全量在 test_balance.py --full）。"""
        ad = EngineAdapter()
        rate, n = act1_normal_winrate(ad, n=60)
        print("\n[balance] act1 普通战胜率 = %.1f%% (%d 场)" % (rate * 100, n))
        self.assertGreaterEqual(
            rate, 0.85,
            "act1 普通战胜率 %.1f%% < 85%%（%d 场）—— 前期过难" % (rate * 100, n))

    def test_greedy_ai_can_actually_win(self):
        """贪心 AI 至少要能赢下一场普通战，否则说明引擎/数据有硬伤。"""
        ad = EngineAdapter()
        rng = random.Random(2)
        wins = 0
        for i in range(20):
            run = ad.new_run(seed=900 + i, ascension=0)
            enc = ad.encounter_for(1, "normal")
            if ad.battle(run, enc, rng) == "won":
                wins += 1
        self.assertGreater(wins, 0,
                           "贪心 AI 20 场 act1 普通战一场没赢——战斗系统可能不可通关")


def _main():
    full = "--full" in sys.argv
    quick = "--quick" in sys.argv
    adapter = EngineAdapter()

    if full:
        per = 100  # 20 档 × 100 = 2000 场
        print("=== 蒙特卡洛全量：20 档 × %d 场 = %d 场 ===" % (per, per * 20))
    elif quick:
        per = 5
        print("=== 蒙特卡洛快测：20 档 × %d 场 = %d 场 ===" % (per, per * 20))
    else:
        per = 25
        print("=== 蒙特卡洛：20 档 × %d 场 = %d 场 ===" % (per, per * 20))

    t0 = time.time()
    last = [0.0]

    def progress(a, t):
        now = time.time()
        if now - last[0] > 2.0:
            last[0] = now
            print("  ...飞升 %2d 完成，通关率 %.1f%%" % (a, t["rate"] * 100))

    table = run_matrix(adapter, per, progress=progress)
    print(format_table(table))
    print("\n总耗时 %.1fs" % (time.time() - t0))

    n_act1 = 300 if full else 60
    rate, n = act1_normal_winrate(adapter, n=n_act1)
    print("\nact1 普通战胜率 = %.1f%% (%d 场)" % (rate * 100, n))

    print("\n=== 异常判据 ===")
    problems = []
    if rate < 0.85:
        problems.append("act1 普通战胜率 %.1f%% < 85%%（前期过难）" % (rate * 100))
    a0 = table.get(0, {})
    if a0.get("rate", 0) == 0.0:
        problems.append("飞升 0 通关率 0%（无人能通关）")
    if a0.get("rate", 0) > 0.60:
        problems.append("飞升 0 通关率 %.1f%% > 60%%（过于简单）" % (a0.get("rate", 0) * 100))
    to = sum(t["timeouts"] for t in table.values())
    if to:
        problems.append("%d 场战斗超时未收敛（可能死循环）" % to)
    cr = sum(t.get("crashes", 0) for t in table.values())
    if cr:
        uniq = sorted(set(adapter.crashes))
        problems.append("%d 场战斗因引擎抛异常而中断（违反契约 §2 无异常泄漏）：%s"
                        % (cr, uniq[:5]))

    # 单调性：难度应随飞升升高，通关率应大致非递增
    rates = [table[a]["rate"] for a in sorted(table)]
    inversions = [(a, rates[a], rates[a + 1])
                  for a in range(len(rates) - 1) if rates[a + 1] > rates[a] + 0.15]
    if inversions:
        problems.append("通关率随飞升非单调（逆序 %d 处，容差 15%%）：%s"
                        % (len(inversions), inversions[:5]))

    if problems:
        print("发现问题：")
        for p in problems:
            print("  ✗ " + p)
        return 1
    print("  ✓ 未发现异常")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
