# -*- coding: utf-8 -*-
"""core-data 自检脚本：全量 effect 冒烟 + 数据契约校验。

不依赖 engine.py：用轻量 mock ctx 独立调用每一个 effect。
用法： python3 tools_selfcheck_coredata.py
"""

import random
import sys
from collections import Counter

sys.path.insert(0, ".")

from core import cards as C
from core import enemies as E
from core import relics as R


# ---------------------------------------------------------------- mock ctx
class MockMinion:
    def __init__(self, name, hp, attack):
        self.name = name
        self.hp = hp
        self.max_hp = hp
        self.attack = attack
        self.block = 0


class MockCombatant:
    def __init__(self, name="测试者", hp=70, is_player=False):
        self.is_player = is_player
        self.name = name
        self.hp = hp
        self.max_hp = hp
        self.block = 0
        self.energy = 3
        self.max_energy = 3
        self.buffs = {}
        self.powers = {}
        self.hand = []
        self.draw_pile = []
        self.discard_pile = []
        self.exhaust_pile = []
        self.minions = []


class MockBattle:
    def __init__(self):
        self.player = MockCombatant("玩家", is_player=True)
        self.enemies = [MockCombatant("敌人甲", 40), MockCombatant("敌人乙", 30)]
        self.turn = 3
        self.phase = "player"
        self.log = []
        self._played = 2
        self.rng_obj = random.Random(1234)
        self._last_move_id = ""


class MockCard:
    """模拟 CardInstance：提供 block/damage/magic 等已被升级覆盖的取值。"""

    def __init__(self, defn):
        self.defn = defn
        self.uid = 1
        self.upgraded = 0
        self.block = defn.block
        self.damage = defn.damage
        self.magic = defn.magic
        self.magic2 = defn.magic2
        self.hits = defn.hits

    @property
    def cost(self):
        return self.defn.cost


class MockCtx:
    """实现 ARCHITECTURE.md 第 6 节 CardContext 的全部公开方法。"""

    def __init__(self, battle, source, target, card, enemy=None):
        self.battle = battle
        self.source = source
        self.target = target
        self.card = card
        self.enemy = enemy if enemy is not None else source
        self._used = set()
        self.calls = []

    # --- 第 6 节列出的方法 ---
    def deal_damage(self, amount, target=None, hits=1, kind="attack"):
        tgt = target if target is not None else self.target
        if tgt is None:
            alive = self.alive_enemies()
            tgt = alive[0] if alive else None
        if tgt is not None:
            tgt.hp -= max(0, int(amount)) * max(1, int(hits))
        self._used.add("deal_damage")
        self.calls.append(("deal_damage", amount, hits))
        return int(amount) * max(1, int(hits))

    def gain_block(self, amount, target=None):
        tgt = target if target is not None else self.source
        if tgt is not None:
            tgt.block += max(0, int(amount))
        self._used.add("gain_block")
        return int(amount)

    def apply_buff(self, key, amount, target=None):
        tgt = target if target is not None else self.source
        if tgt is not None:
            tgt.buffs[key] = tgt.buffs.get(key, 0) + int(amount)
        self._used.add("apply_buff")

    def draw(self, n):
        self._used.add("draw")
        for _ in range(int(n)):
            self.source.hand.append("虚拟牌")

    def gain_energy(self, n):
        self.source.energy += int(n)
        self._used.add("gain_energy")

    def add_card_to_hand(self, def_id, upgraded=0, n=1, temp=True):
        self._used.add("add_card_to_hand")

    def add_card_to_draw(self, def_id, n=1):
        self._used.add("add_card_to_draw")

    def heal(self, n):
        self.source.hp = min(self.source.max_hp, self.source.hp + int(n))
        self._used.add("heal")

    def lose_hp(self, n):
        self.source.hp -= int(n)
        self._used.add("lose_hp")

    def summon(self, name, hp, attack):
        self.source.minions.append(MockMinion(name, hp, attack))
        self._used.add("summon")

    def exhaust_random(self, n):
        self._used.add("exhaust_random")

    def rng(self):
        return self.battle.rng_obj

    def enemies(self):
        return list(self.battle.enemies)

    def alive_enemies(self):
        return [e for e in self.battle.enemies if e.hp > 0]

    def cards_played_this_turn(self):
        return self.battle._played

    # --- 附录 A：engine 已确认提供的扩展方法 ---
    def summon_count(self):
        return len(self.source.minions)


def run_effect(fn, defn, label, problems):
    battle = MockBattle()
    source = battle.player
    target = battle.enemies[0]
    card = MockCard(defn) if defn is not None else None
    ctx = MockCtx(battle, source, target, card, enemy=target)
    try:
        fn(ctx)
    except Exception as exc:  # noqa: BLE001
        problems.append("%s: %s: %s" % (label, type(exc).__name__, exc))
        return None
    return ctx


# ---------------------------------------------------------------- 卡牌自检
def check_cards(problems):
    print("=" * 64)
    print("卡牌 CARD_DB:", len(C.CARD_DB))
    print("  type  ", dict(Counter(x.type for x in C.CARD_LIST)))
    print("  rarity", dict(Counter(x.rarity for x in C.CARD_LIST)))
    print("  arch  ", dict(Counter(x.arch for x in C.CARD_LIST)))

    # effect 全量调用
    for cd in C.CARD_LIST:
        if cd.effect is None:
            if cd.type not in ("status", "curse"):
                problems.append("卡牌 %s effect=None 但 type=%s 会进奖励池" % (cd.id, cd.type))
            continue
        run_effect(cd.effect, cd, "card:" + cd.id, problems)

    # 占位符与数值一致
    for cd in C.CARD_LIST:
        txt = C.resolve_text(cd)
        if "{" in txt or "}" in txt:
            problems.append("卡牌 %s 文本残留占位符: %s" % (cd.id, txt))
        if "{damage}" in cd.text and cd.damage <= 0:
            problems.append("卡牌 %s 文本含 {damage} 但 damage=0" % cd.id)
        if "{block}" in cd.text and cd.block <= 0:
            problems.append("卡牌 %s 文本含 {block} 但 block=0" % cd.id)
        if "{magic}" in cd.text and cd.magic <= 0:
            problems.append("卡牌 %s 文本含 {magic} 但 magic=0" % cd.id)
        if "{magic2}" in cd.text and cd.magic2 <= 0:
            problems.append("卡牌 %s 文本含 {magic2} 但 magic2=0" % cd.id)

    # 升级覆盖字段合法
    valid_fields = set(C.CardDef.__dataclass_fields__.keys())
    for cd in C.CARD_LIST:
        if cd.upgrade:
            for k in cd.upgrade:
                if k not in valid_fields:
                    problems.append("卡牌 %s upgrade 含非法字段 %s" % (cd.id, k))

    # 硬性指标
    checks = [
        (len(C.CARD_LIST) >= 90, "卡牌总数 >=90: %d" % len(C.CARD_LIST)),
        (len(C.cards_by_type("attack")) >= 38, "attack >=38: %d" % len(C.cards_by_type("attack"))),
        (len(C.cards_by_type("skill")) >= 34, "skill >=34: %d" % len(C.cards_by_type("skill"))),
        (len(C.cards_by_type("power")) >= 12, "power >=12: %d" % len(C.cards_by_type("power"))),
        (len(C.status_cards()) + len(C.curse_cards()) >= 6,
         "status+curse >=6: %d" % (len(C.status_cards()) + len(C.curse_cards()))),
    ]
    for arch in C.ARCHS:
        n = len(C.cards_by_arch(arch))
        checks.append((n >= 14, "流派 %s >=14: %d" % (arch, n)))
    for ok, msg in checks:
        print(("  [OK]   " if ok else "  [FAIL] ") + msg)
        if not ok:
            problems.append(msg)

    # 卡牌 id 唯一 / target 合法 / type 合法
    if len(C.CARD_DB) != len(C.CARD_LIST):
        problems.append("CARD_DB 存在重复 id")
    for cd in C.CARD_LIST:
        if cd.type not in ("attack", "skill", "power", "status", "curse"):
            problems.append("卡牌 %s 非法 type=%s" % (cd.id, cd.type))
        if cd.target not in ("enemy", "self", "all_enemies", "none"):
            problems.append("卡牌 %s 非法 target=%s" % (cd.id, cd.target))

    # CardInstance 往返 + 升级
    ci = C.make_card("strike", 1, uid=99)
    if ci.damage != 9:
        problems.append("strike+ 升级后 damage 应为 9，实际 %d" % ci.damage)
    if C.CardInstance.from_dict(ci.to_dict()).to_dict() != ci.to_dict():
        problems.append("CardInstance 存档往返不一致")
    print("  strike+ damage =", ci.damage, "| text =", ci.text)
    print("  STARTER_DECK =", len(C.STARTER_DECK), "张")


# ---------------------------------------------------------------- 遗物自检
def check_relics(problems):
    print("=" * 64)
    print("遗物 RELIC_DB:", len(R.RELIC_DB))
    print("  trigger", dict(Counter(x.trigger for x in R.RELIC_LIST)))
    print("  rarity ", dict(Counter(x.rarity for x in R.RELIC_LIST)))
    missing = [t for t in R.TRIGGERS if not R.relics_by_trigger(t)]
    if missing:
        problems.append("未覆盖的 trigger: %s" % missing)
    print(("  [OK]   " if not missing else "  [FAIL] ") + "全部 11 个 TRIGGER_* 均有遗物覆盖")
    if len(R.RELIC_LIST) < 45:
        problems.append("遗物 <45: %d" % len(R.RELIC_LIST))
    else:
        print("  [OK]   遗物 >=45: %d" % len(R.RELIC_LIST))
    if len(R.RELIC_DB) != len(R.RELIC_LIST):
        problems.append("RELIC_DB 存在重复 id")
    if R.STARTER_RELIC not in R.RELIC_DB:
        problems.append("STARTER_RELIC %s 不在 RELIC_DB 中" % R.STARTER_RELIC)
    else:
        print("  [OK]   STARTER_RELIC =", R.STARTER_RELIC)


# ---------------------------------------------------------------- 敌人自检
def check_enemies(problems):
    print("=" * 64)
    print("敌人 ENEMY_DB:", len(E.ENEMY_DB))
    print("  tier ", dict(Counter(x.tier for x in E.ENEMY_LIST)))
    for a in (1, 2, 3):
        c = Counter(x.tier for x in E.ENEMY_LIST if x.act == a)
        print("  act%d " % a, dict(c))

    if len(E.ENEMY_LIST) < 34:
        problems.append("敌人 <34: %d" % len(E.ENEMY_LIST))
    else:
        print("  [OK]   敌人 >=34: %d" % len(E.ENEMY_LIST))
    bs = E.bosses()
    if len(bs) < 3:
        problems.append("BOSS <3: %s" % [b.id for b in bs])
    else:
        print("  [OK]   BOSS >=3:", [b.id for b in bs])
    for a in (1, 2, 3):
        tb = E.ENCOUNTERS.get(a)
        if not tb:
            problems.append("ENCOUNTERS 缺 act %d" % a)
            continue
        for kind in ("normal", "elite", "boss"):
            if not tb.get(kind):
                problems.append("act%d 缺 %s 遭遇" % (a, kind))
        if not any(e.tier == "boss" and e.act == a for e in E.ENEMY_LIST):
            problems.append("act%d 没有 BOSS" % a)

    # every encounter references existing enemies
    for a, tb in E.ENCOUNTERS.items():
        for kind, lst in tb.items():
            for enc in lst:
                for eid in enc["enemies"]:
                    if eid not in E.ENEMY_DB:
                        problems.append("遭遇引用未知敌人 %s (act%d/%s)" % (eid, a, kind))

    # effect 全量调用 + AI 可调用性
    for ed in E.ENEMY_LIST:
        for mv in ed.moves:
            if mv.effect is not None:
                run_effect(mv.effect, None, "move:%s.%s" % (ed.id, mv.id), problems)
            if mv.intent not in E._INTENTS:
                problems.append("敌人 %s 招式 %s 非法 intent=%s" % (ed.id, mv.id, mv.intent))
        if ed.hp_min > ed.hp_max:
            problems.append("敌人 %s hp_min>hp_max" % ed.id)
        if len(ed.moves) < 3:
            problems.append("敌人 %s moves<3（无法保证不三连招）: %d" % (ed.id, len(ed.moves)))
        if not ed.art:
            problems.append("敌人 %s 缺 art key" % ed.id)

    # AI 钩子：fixture 状态可调用且返回本题敌人自己的招式
    for ed in E.ENEMY_LIST:
        if ed.ai is None:
            continue
        for turn in (1, 2, 5):
            for ratio, blocker in ((1.0, 0), (0.5, 20), (0.25, 5)):
                st = MockCombatant(ed.name, hp=max(1, int(ed.hp_max * ratio)))
                st.max_hp = ed.hp_max
                st.defn = ed
                bt = MockBattle()
                bt.player.block = blocker
                bt.turn = turn
                bt._last_move_id = ""
                try:
                    mv = ed.ai(st, bt, turn)
                except Exception as exc:  # noqa: BLE001
                    problems.append("AI %s 调用失败: %s: %s" % (ed.id, type(exc).__name__, exc))
                    continue
                if mv is None or mv.id not in [m.id for m in ed.moves]:
                    problems.append("AI %s 返回了非法 MoveDef: %r" % (ed.id, mv))

    print("  deep_crab 兜底 id 存在:", "deep_crab" in E.ENEMY_DB)
    if "deep_crab" not in E.ENEMY_DB:
        problems.append("engine 兜底 id deep_crab 不存在")
    print("  act1 普通敌示例:", [x.id for x in E.ENEMY_LIST if x.act == 1 and x.tier == "normal"][:5])


# ---------------------------------------------------------------- 随机接口
def check_rng(problems):
    print("=" * 64)
    rng = random.Random(20240501)
    pool = C.random_card_pool(rng)
    print("random_card_pool ->", [c.name for c in pool])
    if len(pool) != 3:
        problems.append("random_card_pool 未返回 3 张")
    for i in range(200):
        enc = E.random_encounter(rng, (i % 3) + 1, ("normal", "elite", "boss")[i % 3])
        if not enc.get("enemies"):
            problems.append("random_encounter 空遭遇")
            break

    # 可复现性
    a = [c.id for c in C.random_card_pool(random.Random(7))]
    b = [c.id for c in C.random_card_pool(random.Random(7))]
    if a != b:
        problems.append("random_card_pool 同种子不可复现")
    else:
        print("  [OK]   同种子可复现")


def main():
    problems = []
    check_cards(problems)
    check_relics(problems)
    check_enemies(problems)
    check_rng(problems)

    print("=" * 64)
    print("静态引用审计（幽灵 id 防线 / BUG #9）")
    refs = C.audit_card_references()
    allrefs = C.audit_all_references()
    print("  audit_card_references() ->", refs if refs else "[] 健康")
    print("  audit_all_references()  ->", allrefs if allrefs else "[] 健康")
    problems.extend(refs)
    problems.extend(allrefs)

    print("=" * 64)
    if problems:
        print("发现 %d 个问题：" % len(problems))
        for p in problems:
            print("  -", p)
        return 1
    print("全部自检通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
