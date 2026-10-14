"""测试公共工具。

verifier 拥有 tests/ 目录。核心原则：
- 只读 core/ 与 ui/，绝不修改被测代码。
- 模块尚未实现时，测试 **失败**（不是 skip），因为交付物是完整项目。
- 这里提供契约常量、宽松的构造助手（兼容多种实现签名）。
"""

import importlib
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def load(module_name):
    """导入 core.x / ui.x；不可用时返回 (None, 原因)。"""
    try:
        return importlib.import_module(module_name), None
    except Exception as exc:  # pragma: no cover - 诊断路径
        return None, "%s: %s" % (type(exc).__name__, exc)


class ContractCase(unittest.TestCase):
    """需要某个 core 模块的测试基类。缺失即失败（附明确原因）。"""

    required_module = None

    def setUp(self):
        super().setUp()
        if self.required_module:
            mod, err = load(self.required_module)
            if mod is None:
                self.fail(
                    "契约模块 %s 无法导入：%s\n"
                    "（ARCHITECTURE.md 要求该模块存在；这是实现缺失，不是测试问题）"
                    % (self.required_module, err)
                )
            setattr(self, self.required_module.split(".")[-1], mod)


# ---------------------------------------------------------------- 契约常量
ARCHS = ("attack", "block", "poison", "energy", "summon")
ARCH = {
    "attack": "attack",
    "block": "block",
    "poison": "poison",
    "energy": "energy",
    "summon": "summon",
}
RARITIES = ("basic", "common", "uncommon", "rare")

BUFF_NAMES = (
    "strength", "dexterity", "vulnerable", "weak", "frail", "poison",
    "thorns", "metallicize", "ritual", "artifact", "plated_armor",
    "regenerate", "intangible", "strength_down", "barrier", "chain",
    "envenom", "accuracy",
)

TRIGGER_NAMES = (
    "battle_start", "turn_start", "turn_end", "on_attack",
    "on_damage_taken", "on_card_played", "on_kill", "on_rest",
    "passive", "on_pickup", "on_shop",
)

SCREENS = (
    "menu", "map", "battle", "reward", "shop", "rest", "event",
    "deck", "gameover", "codex", "settings", "stats",
)

NODE_KINDS = (
    "battle", "elite", "event", "shop", "rest", "treasure", "boss",
)


# ---------------------------------------------------------------- 助手
def mod_attr(mod, *names, default=None):
    """返回 mod 上第一个存在的属性。"""
    for n in names:
        if hasattr(mod, n):
            return getattr(mod, n)
    return default


def buff_key(engine, name):
    """兼容 BUFF_X 常量与裸字符串两种实现。"""
    const = getattr(engine, "BUFF_" + name.upper(), None)
    return const if isinstance(const, str) else name


def make_card(cards_mod, def_id, upgraded=0):
    fn = getattr(cards_mod, "make_card", None)
    if fn is not None:
        return fn(def_id, upgraded)
    inst_cls = getattr(cards_mod, "CardInstance", None)
    if inst_cls is None:
        raise AssertionError("cards 模块既没有 make_card 也没有 CardInstance")
    try:
        return inst_cls(uid=0, def_id=def_id, upgraded=upgraded)
    except TypeError:
        return inst_cls(0, def_id, upgraded)


def dummy_run(run_mod, seed=1234, ascension=0, **kwargs):
    """构造一个 RunState 实例（不同实现签名可能略有差异）。"""
    cls = getattr(run_mod, "RunState", None)
    if cls is None:
        raise AssertionError("run 模块缺少 RunState")
    attempts = [
        lambda: cls.new_run(seed=seed, ascension=ascension, **kwargs),
        lambda: cls().new_run(seed=seed, ascension=ascension, **kwargs),
    ]
    last = None
    for a in attempts:
        try:
            obj = a()
            if obj is not None:
                return obj
        except Exception as exc:
            last = exc
    # 最后再试一次慢路径，便于报错信息有用
    try:
        obj = cls()
    except Exception as exc:
        raise AssertionError("无法构造 RunState：%s（此前错误 %s）" % (exc, last))
    for meth in ("new_run", "start_new_run", "begin"):
        f = getattr(obj, meth, None)
        if f is not None:
            try:
                f(seed=seed, ascension=ascension, **kwargs)
                return obj
            except Exception:
                try:
                    f(seed, ascension)
                    return obj
                except Exception as exc:
                    last = exc
    return obj


def make_combatant(engine, is_player, name, hp, **kw):
    cc = getattr(engine, "Combatant", None)
    if cc is None:
        raise AssertionError("engine 模块缺少 Combatant")
    try:
        return cc(is_player=is_player, name=name, hp=hp, max_hp=hp, **kw)
    except TypeError:
        return cc(is_player, name, hp, hp, **kw)


def enemy_combatant(engine, enemies_mod, enemy_id, act=1, hp=None):
    """从 ENEMY_DB 造一个敌人 Combatant。"""
    db = getattr(enemies_mod, "ENEMY_DB", {})
    if enemy_id not in db:
        raise AssertionError("ENEMY_DB 里没有敌人 %r" % enemy_id)
    ed = db[enemy_id]
    use_hp = hp if hp is not None else ed.hp_max
    c = make_combatant(engine, False, ed.name, use_hp)
    for attr, val in (("def_id", enemy_id), ("enemy_id", enemy_id),
                      ("enemy_def", ed), ("defn", ed)):
        if hasattr(c, attr):
            try:
                setattr(c, attr, val)
            except Exception:
                pass
            break
    return c


def start_battle(engine, run, enemy_ids, enemies_mod, seed=7, rng=None):
    """构造并启动一场战斗，尽力兼容不同签名。"""
    rng = rng or random.Random(seed)
    combatants = [
        enemy_combatant(engine, enemies_mod, eid) if isinstance(eid, str) else eid
        for eid in enemy_ids
    ]
    bs_cls = getattr(engine, "BattleState", None)
    if bs_cls is None:
        raise AssertionError("engine 模块缺少 BattleState")
    try:
        bs = bs_cls(run, combatants, rng)
    except TypeError:
        bs = bs_cls(combatants, rng, run)
    start = getattr(bs, "start_battle", None)
    if start is not None:
        start()
    return bs


def alive_enemies(bs):
    """BattleState 上的存活敌人列表。

    契约把 alive_enemies() 定义在 CardContext 上，BattleState 上**没有**这个方法；
    因此这里做兼容解析，避免测试用错 API 而把测试自身的错误报成实现 bug。
    """
    fn = getattr(bs, "alive_enemies", None)
    if callable(fn):
        return list(fn())
    return [e for e in getattr(bs, "enemies", []) if getattr(e, "hp", 0) > 0]


def first_enemy(bs):
    got = alive_enemies(bs)
    return got[0] if got else None


def draw_cards(bs, n, who=None):
    """抽牌：BattleState.draw_cards(who, n) 或 Combatant.draw(n)。"""
    who = who if who is not None else getattr(bs, "player", None)
    fn = getattr(bs, "draw_cards", None)
    if callable(fn):
        try:
            return fn(who, n)
        except TypeError:
            try:
                return fn(n)
            except TypeError:
                pass
    if who is not None:
        fn = getattr(who, "draw", None)
        if callable(fn):
            return fn(n)
    raise AssertionError("找不到可用的抽牌方法（BattleState.draw_cards / Combatant.draw）")


def auto_play_turn(engine, bs, max_actions=200):
    """贪心自动出牌：能打就打（尽量打敌人），直到打不出。返回出牌数。"""
    played = 0
    for _ in range(max_actions):
        hand = list(getattr(bs.player, "hand", []) or [])
        if not hand:
            break
        progressed = False
        for card in hand:
            try:
                if not bs.can_play(card):
                    continue
            except Exception:
                continue
            target = first_enemy(bs)
            try:
                ok = bs.play_card(card, target)
            except Exception:
                ok = False
            if ok:
                played += 1
                progressed = True
                break
        if not progressed:
            break
    return played


def run_battle_to_end(engine, bs, max_turns=60):
    """贪心打完一整场，返回 bs.result()。"""
    for _ in range(max_turns):
        if bs.result() != "ongoing":
            break
        if bs.phase == "player":
            auto_play_turn(engine, bs)
            bs.end_turn()
        else:
            guard = 0
            while bs.phase == "enemy" and guard < 40:
                more = bs.enemy_step()
                guard += 1
                if not more:
                    break
    return bs.result()
