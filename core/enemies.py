# -*- coding: utf-8 -*-
"""钢铁战线 Steel Frontline —— 敌人 / 意图(AI)数据库。

严格遵循 ARCHITECTURE.md 第 5 节：

* ``MoveDef`` / ``EnemyDef`` 字段名与契约完全一致。
* ``MoveDef.effect`` 签名 ``fn(ctx)``；ctx 额外提供 ``ctx.enemy``（行动者），
  其余方法与 :class:`core.engine.CardContext` 一致。effect 内部只使用同一套
  公开方法，并对可选方法做防御性探测，因此可被独立调用而不崩。
* ``EnemyDef.ai`` 签名 ``fn(self_state, battle, turn) -> MoveDef``（可选，优先级高于权重）。
* 所有随机走 ``ctx.rng()``。
* 所有 buff 键均来自 ARCHITECTURE.md 第 6 节 BUFF_*。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Buff 键（与 ARCHITECTURE.md 第 6 节一致）
# --------------------------------------------------------------------------

BUFF_STRENGTH = "strength"
BUFF_DEXTERITY = "dexterity"
BUFF_VULNERABLE = "vulnerable"
BUFF_WEAK = "weak"
BUFF_FRAIL = "frail"
BUFF_POISON = "poison"
BUFF_THORNS = "thorns"
BUFF_METALLICIZE = "metallicize"
BUFF_RITUAL = "ritual"
BUFF_ARTIFACT = "artifact"
BUFF_PLATED_ARMOR = "plated_armor"
BUFF_REGENERATE = "regenerate"
BUFF_INTANGIBLE = "intangible"
BUFF_STRENGTH_DOWN = "strength_down"
BUFF_BARRIER = "barrier"

# 敌人专属 debuff（BOSS 机制）——仍是第 6 节已登记的键
BUFF_ABYSS_MARK = "abyss_mark"          # 湮灭印记：回合结束按层数对玩家造成伤害
BUFF_ENTANGLE = "entangle"              # 缠绕藤壶：玩家本回合无法获得格挡加成（引擎可只做数值削弱）
BUFF_HUNTED = "hunted"                  # 猎杀标记：敌人对你的伤害 +25%
BUFF_MEMORY_LOSS = "memory_loss"        # 记忆流失：每层使玩家下回合少抽 1 张（下限 1）

# 意图
INTENT_ATTACK = "attack"
INTENT_ATTACK_DEBUFF = "attack_debuff"
INTENT_ATTACK_DEFEND = "attack_defend"
INTENT_DEFEND = "defend"
INTENT_BUFF = "buff"
INTENT_DEBUFF = "debuff"
INTENT_UNKNOWN = "unknown"
INTENT_SLEEP = "sleep"

_INTENTS = (INTENT_ATTACK, INTENT_ATTACK_DEBUFF, INTENT_ATTACK_DEFEND, INTENT_DEFEND,
            INTENT_BUFF, INTENT_DEBUFF, INTENT_UNKNOWN, INTENT_SLEEP)

# 附属单位名
MINION_SHARK = "侦察班"
MINION_CRAB = "支援车"
MINION_LANTERN = "反坦克组"
MINION_ECHO = "烟幕分队"
MINION_WHALE_SHADE = "烟幕分队"
MINION_LEECH = "工兵班"

# 各 act 敌人 art key 前缀（供 ui-render 程序化贴图）
ART_ACT_PREFIX = {1: "shallow_", 2: "trench_", 3: "abyss_"}


# --------------------------------------------------------------------------
# 数据类
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MoveDef:
    id: str
    name: str                 # 显示名，如 "撕咬"
    intent: str               # "attack"|"attack_debuff"|"attack_defend"|"defend"|"buff"|"debuff"|"unknown"|"sleep"
    damage: int = 0           # 每段基础伤害（未修正；力量/虚弱/易伤由引擎结算）
    hits: int = 1
    block: int = 0
    effect: Optional[Callable] = None   # fn(ctx) 施加 buff/debuff
    text: str = ""            # 意图提示补充


@dataclass(frozen=True)
class EnemyDef:
    id: str
    name: str
    hp_min: int
    hp_max: int
    tier: str                 # "normal"|"elite"|"boss"
    act: int                  # 1 | 2 | 3
    # AI：按权重选招，禁止连续同一招
    moves: tuple              # tuple[MoveDef]
    # fn(self_state, battle, turn) -> MoveDef  自定义 AI（可选，优先级高于权重）
    ai: Optional[Callable] = None
    art: str = ""             # 程序化贴图 key
    desc: str = ""


# --------------------------------------------------------------------------
# effect 辅助（只用 CardContext 公开方法；ctx.enemy 为行动者）
# --------------------------------------------------------------------------

def _apply(ctx, key: str, amount: int, target=None) -> None:
    fn = getattr(ctx, "apply_buff", None)
    if fn is not None:
        fn(key, amount, target)


def _on_player(ctx) -> None:
    """把 debuff 挂到玩家身上。"""
    p = getattr(ctx, "source", None) or getattr(ctx, "player", None)
    return p


def _hurt_player(ctx, key: str, amount: int) -> None:
    _apply(ctx, key, amount, None)


def _self_buff(ctx, key: str, amount: int) -> None:
    e = getattr(ctx, "enemy", None)
    _apply(ctx, key, amount, e)


def _summon(ctx, name: str, hp: int, attack: int) -> None:
    fn = getattr(ctx, "summon", None)
    if fn is not None:
        fn(name, hp, attack)


def _block(ctx, amount, target=None) -> None:
    fn = getattr(ctx, "gain_block", None)
    if fn is not None:
        fn(amount, target)


def _heal(ctx, n: int) -> None:
    fn = getattr(ctx, "heal", None)
    if fn is not None and n > 0:
        fn(n)


def _draw_player(ctx, n: int) -> None:
    fn = getattr(ctx, "draw", None)
    if fn is not None and n > 0:
        fn(n)


# --------------------------------------------------------------------------
# 通用 effect
# --------------------------------------------------------------------------

def eff_weaken(ctx) -> None:
    """施加 1 层虚弱。"""
    _hurt_player(ctx, BUFF_WEAK, 1)


def eff_weaken2(ctx) -> None:
    """施加 2 层虚弱。"""
    _hurt_player(ctx, BUFF_WEAK, 2)



def eff_vulnerable(ctx) -> None:
    _hurt_player(ctx, BUFF_VULNERABLE, 2)


def eff_vulnerable3(ctx) -> None:
    _hurt_player(ctx, BUFF_VULNERABLE, 3)


def eff_frail(ctx) -> None:
    _hurt_player(ctx, BUFF_FRAIL, 2)


def eff_poison(ctx) -> None:
    _hurt_player(ctx, BUFF_POISON, 3)


def eff_poison_heavy(ctx) -> None:
    _hurt_player(ctx, BUFF_POISON, 6)


def eff_poison_aoe(ctx) -> None:
    """向玩家施加中毒（本作为单体玩家，等价于 poison）。"""
    _hurt_player(ctx, BUFF_POISON, 4)


def eff_strength_up(ctx) -> None:
    _self_buff(ctx, BUFF_STRENGTH, 2)


def eff_strength_up3(ctx) -> None:
    _self_buff(ctx, BUFF_STRENGTH, 3)


def eff_ritual(ctx) -> None:
    _self_buff(ctx, BUFF_RITUAL, 1)


def eff_ritual2(ctx) -> None:
    _self_buff(ctx, BUFF_RITUAL, 2)


def eff_thorns(ctx) -> None:
    _self_buff(ctx, BUFF_THORNS, 3)


def eff_metallicize(ctx) -> None:
    _self_buff(ctx, BUFF_METALLICIZE, 3)


def eff_plated(ctx) -> None:
    _self_buff(ctx, BUFF_PLATED_ARMOR, 5)


def eff_dexterity(ctx) -> None:
    _self_buff(ctx, BUFF_DEXTERITY, 2)


def eff_regenerate(ctx) -> None:
    _self_buff(ctx, BUFF_REGENERATE, 3)


def eff_intangible(ctx) -> None:
    _self_buff(ctx, BUFF_INTANGIBLE, 1)


def eff_artifact(ctx) -> None:
    _self_buff(ctx, BUFF_ARTIFACT, 1)


def eff_abyss_mark(ctx) -> None:
    _hurt_player(ctx, BUFF_ABYSS_MARK, 2)


def eff_abyss_mark3(ctx) -> None:
    _hurt_player(ctx, BUFF_ABYSS_MARK, 3)


def eff_hunted(ctx) -> None:
    _hurt_player(ctx, BUFF_HUNTED, 2)


def eff_memory_loss(ctx) -> None:
    _hurt_player(ctx, BUFF_MEMORY_LOSS, 1)


def eff_memory_loss2(ctx) -> None:
    _hurt_player(ctx, BUFF_MEMORY_LOSS, 2)


def eff_memory_loss3(ctx) -> None:
    _hurt_player(ctx, BUFF_MEMORY_LOSS, 3)


def eff_entangle(ctx) -> None:
    _hurt_player(ctx, BUFF_ENTANGLE, 1)


def eff_heal8(ctx) -> None:
    _heal(ctx, 8)


def eff_heal15(ctx) -> None:
    _heal(ctx, 15)


def eff_heal_self_block(ctx) -> None:
    _heal(ctx, 10)
    _block(ctx, 8, getattr(ctx, "enemy", None))


def eff_strength_down(ctx) -> None:
    _hurt_player(ctx, BUFF_STRENGTH_DOWN, 2)


def eff_summon_shark(ctx) -> None:
    _summon(ctx, MINION_SHARK, 12, 5)


def eff_summon_crab(ctx) -> None:
    _summon(ctx, MINION_CRAB, 18, 3)


def eff_summon_lantern(ctx) -> None:
    _summon(ctx, MINION_LANTERN, 10, 6)


def eff_summon_echo(ctx) -> None:
    _summon(ctx, MINION_ECHO, 8, 4)


def eff_summon_leech(ctx) -> None:
    _summon(ctx, MINION_LEECH, 9, 3)


def eff_summon_shade(ctx) -> None:
    _summon(ctx, MINION_WHALE_SHADE, 20, 7)


def eff_summon_two(ctx) -> None:
    _summon(ctx, MINION_ECHO, 7, 3)
    _summon(ctx, MINION_ECHO, 7, 3)


def eff_player_discard_pressure(ctx) -> None:
    """压力：让玩家失去能量感知（用虚弱表示），并抽牌作为补偿提示。"""
    _hurt_player(ctx, BUFF_WEAK, 1)
    _draw_player(ctx, 1)


def eff_nothing(ctx) -> None:
    return None


def eff_double_strength(ctx) -> None:
    e = getattr(ctx, "enemy", None)
    b = getattr(e, "buffs", None)
    cur = int(b.get(BUFF_STRENGTH, 0)) if b else 0
    _self_buff(ctx, BUFF_STRENGTH, max(1, cur))


def eff_gain_block_12(ctx) -> None:
    _block(ctx, 12, getattr(ctx, "enemy", None))


def eff_self_heal_missing(ctx) -> None:
    """吞噬：回复已损失生命的一半（最多 12）。"""
    e = getattr(ctx, "enemy", None)
    if e is None:
        return
    missing = int(getattr(e, "max_hp", 0)) - int(getattr(e, "hp", 0))
    _heal(ctx, min(12, max(0, missing // 2)))


def eff_poison_from_missing(ctx) -> None:
    """潮毒：按自身已损失生命向玩家施加中毒。"""
    e = getattr(ctx, "enemy", None)
    if e is None:
        return
    missing = int(getattr(e, "max_hp", 0)) - int(getattr(e, "hp", 0))
    _hurt_player(ctx, BUFF_POISON, min(10, max(2, missing // 4)))


# --------------------------------------------------------------------------
# 自定义 AI（fn(self_state, battle, turn) -> MoveDef）
# 读取局势：低血格挡/回血、玩家格挡高改 debuff、有召唤位先召唤、满足条件进狂暴。
# --------------------------------------------------------------------------

def _find(enemy: "EnemyDef", move_id: str) -> MoveDef:
    for m in enemy.moves:
        if m.id == move_id:
            return m
    return enemy.moves[0]


def _player_block(battle) -> int:
    p = getattr(battle, "player", None)
    return int(getattr(p, "block", 0)) if p is not None else 0


def _hp_ratio(state) -> float:
    mx = max(1, int(getattr(state, "max_hp", 1)))
    return float(getattr(state, "hp", mx)) / mx


def _minion_count(state) -> int:
    return len(getattr(state, "minions", None) or [])


def _history(state) -> list:
    """取该敌人最近的出招 id 历史（engine.Combatant.move_history）。"""
    h = getattr(state, "move_history", None)
    if h is None:
        h = getattr(state, "history", None)
    return list(h) if h else []


def _last_move_id(state) -> str:
    h = _history(state)
    return str(h[-1]) if h else ""


def _pick(enemy, preferred: List[str], state=None) -> MoveDef:
    """按优先级挑招，并强制满足「禁止连续 3 次同一招」。

    这是引擎侧过滤的补充：带 ai 钩子的敌人会绕过引擎的权重过滤，
    因此钩子必须自己保证不三连。
    """
    hist = _history(state) if state is not None else []
    banned = ""
    if len(hist) >= 2 and hist[-1] == hist[-2]:
        banned = str(hist[-1])
    last = str(hist[-1]) if hist else ""

    for mid in preferred:
        if mid == banned:
            continue
        return _find(enemy, mid)
    # 首选全被禁 → 找任何不是 banned 的招
    for m in enemy.moves:
        if m.id != banned:
            return m
    # 极端兜底：全部同招，仍返回首选（数据层面不会发生）
    _ = last
    return _find(enemy, preferred[0])


def _mark_stage(state, stage: int) -> None:
    """把 BOSS 阶段写到 Combatant，供引擎/UI/测试观测（多阶段可检测）。"""
    try:
        state.phase_index = int(stage)
    except Exception:
        pass


def ai_tide_hunter(state, battle, turn) -> MoveDef:
    """反坦克猎手：低血先回血，玩家掩体高改用破甲。"""
    enemy = _enemy_of(state)
    if _hp_ratio(state) < 0.4:
        return _pick(enemy, ["regroup", "harpoon", "spike"], state)
    if _player_block(battle) >= 8:
        return _pick(enemy, ["mark", "harpoon", "regroup"], state)
    return _pick(enemy, ["harpoon", "mark", "regroup"], state)


def ai_shell_crab(state, battle, turn) -> MoveDef:
    """铁壳蟹：低血缩壳，其余以钳击与尖刺轮换。"""
    enemy = _enemy_of(state)
    if _hp_ratio(state) < 0.5:
        return _pick(enemy, ["harden", "claw", "spike"], state)
    return _pick(enemy, ["claw", "spike", "harden"], state)


def ai_barnacle_hulk(state, battle, turn) -> MoveDef:
    """藤壶重装者：低血以钙化壁垒自保，否则附着猛击与碾壳轮换。"""
    enemy = _enemy_of(state)
    if _hp_ratio(state) < 0.5:
        return _pick(enemy, ["calcify", "crush_shell", "encrust_slam"], state)
    return _pick(enemy, ["encrust_slam", "crush_shell", "calcify"], state)


def ai_chorus(state, battle, turn) -> MoveDef:
    """宣传连：广播压制与不谐音干扰交替，杜绝三连同一招。"""
    enemy = _enemy_of(state)
    if _hp_ratio(state) < 0.5:
        return _pick(enemy, ["dirge", "requiem", "dissonance"], state)
    return _pick(enemy, ["dissonance", "dirge", "requiem"], state)


def ai_venom_eel(state, battle, turn) -> MoveDef:
    """毒鳗：玩家格挡越高越倾向用中毒绕过格挡。"""
    enemy = _enemy_of(state)
    if _player_block(battle) >= 10:
        return _pick(enemy, ["venom_spit", "burrow", "coil"], state)
    return _pick(enemy, ["coil", "venom_spit", "burrow"], state)


def ai_deep_oracle(state, battle, turn) -> MoveDef:
    """重炮祭司：先召唤，召唤满则叠加仪式。"""
    enemy = _enemy_of(state)
    if _minion_count(state) < 2:
        return _pick(enemy, ["summon_echoes", "rite", "mind_lash", "prophecy"], state)
    return _pick(enemy, ["rite", "mind_lash", "prophecy", "summon_echoes"], state)


def ai_trench_stalker(state, battle, turn) -> MoveDef:
    """战壕潜行者：血量低进入狂暴（叠力量），玩家格挡高时用猎杀标记。"""
    enemy = _enemy_of(state)
    if _hp_ratio(state) < 0.35:
        return _pick(enemy, ["frenzy", "vanish", "lunge", "hunt"], state)
    if _player_block(battle) >= 12:
        return _pick(enemy, ["hunt", "vanish", "lunge"], state)
    return _pick(enemy, ["lunge", "hunt", "frenzy", "vanish"], state)


def ai_abyss_watcher(state, battle, turn) -> MoveDef:
    """要塞监视所（BOSS1）：多阶段。

    阶段 1（>50%）：凝视 → 湮灭刻印 → 碾压轮转。
    阶段 2（<=50%）：进入狂暴，先以「湮灭刻印」叠易伤，再转三段撕裂。
    """
    enemy = _enemy_of(state)
    r = _hp_ratio(state)
    if r <= 0.50:
        _mark_stage(state, 2)
        return _pick(enemy, ["abyss_rend", "mark_of_abyss", "crush", "gaze"], state)
    _mark_stage(state, 1)
    if turn <= 1:
        return _pick(enemy, ["gaze", "crush", "mark_of_abyss"], state)
    return _pick(enemy, ["crush", "mark_of_abyss", "gaze"], state)


def ai_leviathan_rex(state, battle, turn) -> MoveDef:
    """利维坦之王（BOSS2）：三阶段。

    >60%：呼叫装甲集群 + 重炮压制；
    <=60%：狂暴（力量翻倍）；
    <=30%：终末阶段，三段潮怒。
    """
    enemy = _enemy_of(state)
    r = _hp_ratio(state)
    if r <= 0.30:
        _mark_stage(state, 3)
        return _pick(enemy, ["tidal_wrath", "devour", "frenzy_roar", "roar"], state)
    if r <= 0.60:
        _mark_stage(state, 2)
        return _pick(enemy, ["frenzy_roar", "devour", "summon_shoal", "roar"], state)
    _mark_stage(state, 1)
    if _minion_count(state) < 2:
        return _pick(enemy, ["summon_shoal", "crushing_pressure", "roar", "devour"], state)
    return _pick(enemy, ["crushing_pressure", "roar", "devour", "summon_shoal"], state)


def ai_hollow_whale(state, battle, turn) -> MoveDef:
    """最高统帅部（BOSS3）：多阶段 + 周期性烟幕。

    >50%：灵魂汲取 → 湮灭烙印 → 湮灭回响；
    <=50%：改为帷幕与烙印交替，并持续汲取。
    每 3 回合优先张开「虚空帷幕」获得无形（不与上一招重复）。
    """
    enemy = _enemy_of(state)
    r = _hp_ratio(state)
    if r <= 0.50:
        _mark_stage(state, 2)
        if turn % 3 == 0:
            return _pick(enemy, ["void_veil", "mark_of_abyss", "soul_drain"], state)
        return _pick(enemy, ["mark_of_abyss", "soul_drain", "echo_of_oblivion", "void_veil"], state)
    _mark_stage(state, 1)
    if turn % 3 == 0:
        return _pick(enemy, ["void_veil", "soul_drain", "mark_of_abyss"], state)
    return _pick(enemy, ["soul_drain", "mark_of_abyss", "echo_of_oblivion"], state)


def _enemy_of(state) -> EnemyDef:
    """从 self_state 里取 EnemyDef：优先 state.defn / state.enemy_def，否则当作 EnemyDef。"""
    for attr in ("defn", "enemy_def", "enemydef"):
        d = getattr(state, attr, None)
        if isinstance(d, EnemyDef):
            return d
    if isinstance(state, EnemyDef):
        return state
    # 兜底：按 id 反查
    did = getattr(state, "def_id", None) or getattr(state, "id", None)
    if did and did in ENEMY_DB:
        return ENEMY_DB[did]
    raise KeyError("无法从 self_state 解析 EnemyDef")


# --------------------------------------------------------------------------
# 敌人表
# --------------------------------------------------------------------------
# 设计约束：任何敌人的 moves 数量 >= 3（BOSS1/2/3 亦满足），
# 因此「权重随机 + 禁止连续同一招」的引擎规则天然不会出现三连同一招。

ENEMY_LIST: List[EnemyDef] = [

    # ================= ACT 1 · 浅海 (normal 12 / elite 3 / boss 1) =================
    EnemyDef("spine_minnow", "侦察步兵班", 9, 14, "normal", 1, (
        MoveDef("nip", "步枪射击", INTENT_ATTACK, damage=4, text="轻咬一口"),
        MoveDef("swarm_dash", "班组冲锋", INTENT_ATTACK, damage=3, hits=2, text="连续冲刺"),
        MoveDef("flutter", "就地卧倒", INTENT_DEFEND, block=4, text="摆动防御"),
    ), art="shallow_spine_minnow", desc="最前沿的散兵，数量多、装备差，负责试探我军火力。"),

    EnemyDef("deep_crab", "掩体机枪巢", 14, 20, "normal", 1, (
        MoveDef("pincer", "机枪点射", INTENT_ATTACK, damage=6, text="铁钳夹击"),
        MoveDef("shell_up", "加固掩体", INTENT_DEFEND, block=6,
                effect=eff_gain_block_12, text="硬化外壳"),
        MoveDef("sand_spray", "掷弹压制", INTENT_ATTACK_DEBUFF, damage=3,
                effect=eff_weaken, text="沙粒迷眼，施加虚弱"),
    ), art="shallow_deep_crab", desc="标准配置的机枪巢，压制一切试图接近的步兵。"),

    EnemyDef("tide_crab", "混凝土碉堡", 14, 20, "normal", 1, (
        MoveDef("pincer", "机枪点射", INTENT_ATTACK, damage=6, text="铁钳夹击"),
        MoveDef("shell_up", "加固掩体", INTENT_DEFEND, block=6,
                effect=eff_gain_block_12, text="硬化外壳"),
        MoveDef("sand_spray", "掷弹压制", INTENT_ATTACK_DEBUFF, damage=3,
                effect=eff_weaken, text="沙粒迷眼，施加虚弱"),
    ), art="shallow_tide_crab", desc="浇铸成型的碉堡，正面硬得像石头。"),

    EnemyDef("gull_flock", "俯冲轰炸机编队", 12, 17, "normal", 1, (
        MoveDef("dive_bomb", "俯冲投弹", INTENT_ATTACK, damage=5, hits=2, text="轮番俯冲"),
        MoveDef("screech", "警报尖啸", INTENT_DEBUFF, effect=eff_frail, text="刺耳鸣叫，施加脆弱"),
        MoveDef("peck", "机炮扫射", INTENT_ATTACK, damage=7, text="尖锐啄击"),
    ), art="shallow_gull_flock", desc="从云层里扎下来的黑点，警报永远慢半拍。"),

    EnemyDef("lantern_jelly", "照明弹哨戒", 16, 22, "normal", 1, (
        MoveDef("sting", "照明弹压制", INTENT_ATTACK_DEBUFF, damage=5,
                effect=eff_poison, text="毒刺，施加中毒"),
        MoveDef("luminesce", "信号弹校准", INTENT_BUFF, effect=eff_strength_up, text="发亮蓄力，获得力量"),
        MoveDef("drift", "转移阵地", INTENT_DEFEND, block=8, text="随流漂移"),
    ), art="shallow_lantern_jelly", desc="悬在半空的冷白光，把整片阵地照得无处藏身。"),

    EnemyDef("harpoon_drifter", "反坦克炮组", 18, 24, "normal", 1, (
        MoveDef("throw_harpoon", "反坦克炮击", INTENT_ATTACK, damage=9, text="掷出锈叉"),
        MoveDef("reel_in", "标定射击", INTENT_ATTACK_DEBUFF, damage=4,
                effect=eff_vulnerable, text="钩住皮肤，施加易伤"),
        MoveDef("brace", "架炮还击", INTENT_ATTACK_DEFEND, damage=3, block=6, text="攻守兼备"),
    ), art="shallow_harpoon_drifter", desc="架在废墟里的反坦克炮，炮管还在冒烟。", ),

    EnemyDef("barnacle_swarm", "铁丝网集群", 20, 26, "normal", 1, (
        MoveDef("encrust", "布设铁丝网", INTENT_ATTACK_DEBUFF, damage=4,
                effect=eff_frail, text="爬上关节，施加脆弱"),
        MoveDef("squeeze", "火力挤压", INTENT_ATTACK, damage=8, text="石灰质的挤压"),
        MoveDef("harden", "混凝土浇筑", INTENT_DEFEND, block=9, effect=eff_thorns, text="硬化并长刺"),
    ), art="shallow_barnacle_swarm", desc="层层叠叠的障碍带，越挣扎缠得越紧。"),

    EnemyDef("salt_hound", "军犬巡逻队", 15, 21, "normal", 1, (
        MoveDef("bite", "军犬撕咬", INTENT_ATTACK, damage=7, text="犬齿撕咬"),
        MoveDef("howl", "集结号", INTENT_BUFF, effect=eff_strength_up, text="嗥叫助威"),
        MoveDef("pounce", "突袭扑击", INTENT_ATTACK_DEBUFF, damage=5,
                effect=eff_weaken, text="扑倒并施加虚弱"),
    ), art="shallow_salt_hound", desc="牵着犬的巡逻兵，鼻子比探照灯更早发现你。"),

    EnemyDef("drowned_sailor", "老兵残部", 22, 28, "normal", 1, (
        MoveDef("barnacled_fist", "近身格斗", INTENT_ATTACK, damage=9, text="沉重一拳"),
        MoveDef("sea_curse", "心理战广播", INTENT_DEBUFF, effect=eff_weaken, text="低语诅咒，施加虚弱"),
        MoveDef("wail", "哀号广播", INTENT_BUFF, effect=eff_ritual, text="悲鸣不止，获得仪式"),
    ), art="shallow_drowned_sailor", desc="打了四年仗还没死的老兵，动作慢但枪枪致命。"),

    EnemyDef("reef_stalker", "狙击手", 17, 23, "normal", 1, (
        MoveDef("ambush", "狙击伏击", INTENT_ATTACK, damage=10, text="从暗处暴起"),
        MoveDef("shadow_step", "转移阵位", INTENT_DEFEND, block=7, text="融入礁影"),
        MoveDef("drain_bite", "战场搜刮", INTENT_ATTACK, damage=6,
                effect=eff_self_heal_missing, text="吸血回复"),
    ), art="shallow_reef_stalker", desc="你以为那是断墙，其实他一直在等你抬头。"),

    EnemyDef("ink_squid", "烟幕掷弹兵", 19, 25, "normal", 1, (
        MoveDef("ink_veil", "烟幕弹", INTENT_DEBUFF, effect=eff_memory_loss, text="墨雾遮蔽，记忆流失"),
        MoveDef("tentacle", "霰弹扫射", INTENT_ATTACK, damage=4, hits=3, text="三连抽击"),
        MoveDef("retreat", "退回掩体", INTENT_DEFEND, block=10, text="缩回洞穴"),
    ), art="shallow_ink_squid", desc="一通烟幕弹，让你的联络和判断全部失效。"),

    EnemyDef("shoal_serpent", "装甲侦察车", 21, 27, "normal", 1, (
        MoveDef("serpent_strike", "车载机枪", INTENT_ATTACK, damage=6, hits=2, text="双段啃咬"),
        MoveDef("coil", "履带碾压", INTENT_ATTACK_DEBUFF, damage=3,
                effect=eff_entangle, text="缠住你，藤壶封甲"),
        MoveDef("shed_skin", "更换装甲板", INTENT_BUFF, effect=eff_dexterity, text="蜕皮，获得灵巧"),
    ), art="shallow_shoal_serpent", desc="轮式装甲车贴着废墟高速穿插，专挑侧翼。"),

    EnemyDef("bone_picker", "战利品回收队", 20, 26, "normal", 1, (
        MoveDef("bone_knife", "战壕刀", INTENT_ATTACK, damage=8, text="骨刃劈砍"),
        MoveDef("strip", "剥甲射击", INTENT_ATTACK_DEBUFF, damage=4,
                effect=eff_vulnerable, text="剥开护甲，施加易伤"),
        MoveDef("gnaw", "啃食补给", INTENT_ATTACK_DEFEND, damage=5, block=5,
                effect=eff_self_heal_missing, text="边吃边长"),
    ), art="shallow_bone_picker", desc="跟在战线后面捡装备的人，筐里装的都是同僚的东西。"),

    # ---- ACT 1 精英 3 ----
    EnemyDef("elite_tide_hunter", "精锐·反坦克猎手", 42, 52, "elite", 1, (
        MoveDef("harpoon", "穿甲弹射击", INTENT_ATTACK, damage=11, text="蓄力刺击"),
        MoveDef("mark", "标记目标", INTENT_ATTACK_DEBUFF, damage=6,
                effect=eff_hunted, text="标记你，受伤 +25%"),
        MoveDef("regroup", "重整队形", INTENT_DEFEND, block=12,
                effect=eff_gain_block_12, text="后撤整备并回血"),
    ), ai=ai_tide_hunter, art="shallow_elite_tide_hunter",
        desc="精锐：标记目标后集火，专打装甲薄弱的侧面。"),

    EnemyDef("elite_shell_crab", "精锐·重装突击炮", 48, 58, "elite", 1, (
        MoveDef("claw", "重炮直击", INTENT_ATTACK, damage=12, text="巨钳砸落"),
        MoveDef("harden", "混凝土浇筑", INTENT_DEFEND, block=16,
                effect=eff_thorns, text="缩壳并获得荆棘"),
        MoveDef("spike", "尖刺拒马突刺", INTENT_ATTACK_DEFEND, damage=7, block=8, text="攻守一体"),
    ), ai=ai_shell_crab, art="shallow_elite_shell_crab",
        desc="精锐：正面装甲极厚，硬啃只会崩掉自己的牙。"),

    EnemyDef("elite_venom_eel", "精锐·喷火兵", 40, 50, "elite", 1, (
        MoveDef("coil", "履带碾压", INTENT_ATTACK, damage=5, hits=2, text="缠住身体撕扯"),
        MoveDef("venom_spit", "火焰喷射", INTENT_ATTACK_DEBUFF, damage=4,
                effect=eff_poison_heavy, text="喷吐剧毒，施加大量中毒"),
        MoveDef("burrow", "进入掩体", INTENT_DEFEND, block=10,
                effect=eff_regenerate, text="钻入沙中并再生"),
    ), ai=ai_venom_eel, art="shallow_elite_venom_eel",
        desc="精锐：火焰喷射器把整条战壕变成烤箱。"),

    EnemyDef("elite_barnacle_hulk", "精锐·永备工事", 46, 56, "elite", 1, (
        MoveDef("encrust_slam", "铁丝网猛击", INTENT_ATTACK_DEBUFF, damage=10,
                effect=eff_frail, text="重击并施加脆弱"),
        MoveDef("calcify", "浇筑混凝土", INTENT_DEFEND, block=15,
                effect=eff_thorns, text="钙化并获得荆棘"),
        MoveDef("crush_shell", "碾压掩体", INTENT_ATTACK_DEFEND, damage=8, block=9,
                effect=eff_plated, text="攻守兼备，获得甲壳"),
    ), ai=ai_barnacle_hulk, art="shallow_elite_barnacle_hulk",
        desc="精锐：钢筋混凝土浇筑的巨型工事，越打越硬。"),

    # ---- ACT 1 BOSS ----
    EnemyDef("abyss_watcher", "要塞·观测所", 96, 106, "boss", 1, (
        MoveDef("gaze", "战场标定", INTENT_DEBUFF, effect=eff_abyss_mark,
                text="湮灭印记：回合结束按层数灼伤你"),
        MoveDef("crush", "重炮碾压", INTENT_ATTACK, damage=14, text="碾压而下"),
        MoveDef("mark_of_abyss", "标定印记", INTENT_ATTACK_DEBUFF, damage=8,
                effect=eff_abyss_mark3, text="刻印加深，并施加易伤"),
        MoveDef("abyss_rend", "三段覆盖射击", INTENT_ATTACK, damage=9, hits=3,
                text="狂暴阶段：三段撕裂"),
    ), ai=ai_abyss_watcher, art="abyss_abyss_watcher",
        desc="【BOSS·多阶段】高地上的观测所，用标定射击把整片区域变成死亡区。耐久过半后转为三段覆盖射击，并持续标定你的位置。"
             "并以「湮灭印记」在回合末持续灼伤你。"),

    # ================= ACT 2 · 战壕 (normal 12 / elite 4 / boss 1) =================
    EnemyDef("trench_lurker", "堑壕突击队", 30, 38, "normal", 2, (
        MoveDef("lunge", "装甲突击", INTENT_ATTACK, damage=12, text="猛然扑出"),
        MoveDef("hunt", "猎杀标定", INTENT_ATTACK_DEBUFF, damage=6,
                effect=eff_hunted, text="标记，受伤 +25%"),
        MoveDef("frenzy", "狂暴冲锋", INTENT_BUFF, effect=eff_strength_up3, text="狂暴，力量 +3"),
    ), art="trench_trench_lurker", desc="精锐：从堑壕里突然跃出，贴脸解决战斗。"),

    EnemyDef("bone_kraken_spawn", "多管火箭炮", 26, 34, "normal", 2, (
        MoveDef("tentacle", "霰弹扫射", INTENT_ATTACK, damage=5, hits=3, text="三连触击"),
        MoveDef("spawn", "呼叫增援", INTENT_BUFF, effect=eff_summon_two, text="分裂出两个回声体"),
        MoveDef("ink_cloud", "烟幕覆盖", INTENT_DEBUFF, effect=eff_memory_loss, text="墨雾，记忆流失"),
    ), art="trench_bone_kraken_spawn", desc="精锐：六根发射管轮流倾泻，覆盖面积惊人。"),

    EnemyDef("pressure_wraith", "重炮观测机", 28, 36, "normal", 2, (
        MoveDef("crush_pressure", "重炮压制", INTENT_ATTACK, damage=13, text="压强骤增"),
        MoveDef("decompress", "转移阵地", INTENT_DEFEND, block=14, text="排空腔体"),
        MoveDef("the_bends", "震爆弹", INTENT_DEBUFF, effect=eff_frail, text="血液沸腾，施加脆弱"),
    ), art="trench_pressure_wraith", desc="悬在头顶的观测机，它看见你，炮弹就会落下。"),

    EnemyDef("lantern_priest", "战地广播站", 32, 40, "normal", 2, (
        MoveDef("rite", "战场仪式", INTENT_BUFF, effect=eff_ritual, text="每回合叠加力量"),
        MoveDef("mind_lash", "通讯干扰", INTENT_ATTACK, damage=10, text="精神冲击"),
        MoveDef("bless", "分发干扰弹", INTENT_DEFEND, block=12, effect=eff_artifact, text="获得神器"),
    ), art="trench_lantern_priest", desc="精锐：用广播瓦解士气，每回合都在给你的部队施压。"),

    EnemyDef("coral_golem", "混凝土要塞", 44, 52, "normal", 2, (
        MoveDef("stone_fist", "混凝土重拳", INTENT_ATTACK, damage=15, text="混凝土重拳"),
        MoveDef("fortify", "构筑工事", INTENT_DEFEND, block=18, effect=eff_metallicize, text="钙化并金属化"),
        MoveDef("shard_volley", "破片弹幕", INTENT_ATTACK_DEBUFF, damage=5,
                effect=eff_vulnerable, text="碎屑四射，施加易伤"),
    ), art="trench_coral_golem", desc="精锐：整座碉堡站了起来，拳头是浇筑出来的。"),

    EnemyDef("sonar_bat", "夜间侦察机", 22, 28, "normal", 2, (
        MoveDef("echo_shriek", "声呐尖啸", INTENT_ATTACK_DEBUFF, damage=6,
                effect=eff_weaken, text="尖啸，施加虚弱"),
        MoveDef("dive", "俯冲扫射", INTENT_ATTACK, damage=8, hits=2, text="两段俯冲"),
        MoveDef("cloak", "匿声潜行", INTENT_DEFEND, block=11, text="隐匿于噪声"),
    ), art="trench_sonar_bat", desc="精锐：夜里用探照灯和机枪反复骚扰，让你无法休整。"),

    EnemyDef("drowned_chorus", "propaganda 宣传连", 36, 44, "normal", 2, (
        MoveDef("dirge", "挽歌广播", INTENT_DEBUFF, effect=eff_weaken2, text="挽歌，施加 2 层虚弱"),
        MoveDef("dissonance", "不谐音干扰", INTENT_ATTACK, damage=6, hits=2, text="音波撕扯"),
        MoveDef("requiem", "安魂广播", INTENT_BUFF, effect=eff_ritual2, text="安魂曲，获得 2 层仪式"),
    ), ai=ai_chorus, art="trench_drowned_chorus",
        desc="精锐：高音喇叭里的声音没有一个是活人的音高。"),

    EnemyDef("anglerfish_lure", "诱饵阵地", 34, 42, "normal", 2, (
        MoveDef("lure", "诱饵照明", INTENT_DEBUFF, effect=eff_vulnerable3, text="诱光，施加 3 层易伤"),
        MoveDef("devour", "抵近射击", INTENT_ATTACK, damage=16, text="血盆大口"),
        MoveDef("swallow", "战场吞噬", INTENT_ATTACK_DEFEND, damage=8, block=10,
                effect=eff_self_heal_missing, text="吞下碎块并回复"),
    ), art="trench_anglerfish_lure", desc="精锐：那盏亮着的灯，是故意留给你的。"),

    EnemyDef("silt_horror", "泥泞沼泽阵地", 38, 46, "normal", 2, (
        MoveDef("engulf", "泥泞吞没", INTENT_ATTACK_DEBUFF, damage=9,
                effect=eff_entangle, text="淤泥灌入关节"),
        MoveDef("slam", "重击", INTENT_ATTACK, damage=14, text="沉重拍击"),
        MoveDef("ooze", "渗出补给", INTENT_DEFEND, block=13, effect=eff_regenerate, text="渗流再生"),
    ), art="trench_silt_horror", desc="精锐：把整片地面变成泥潭，装甲和意志一起下沉。"),

    EnemyDef("abyss_hermit", "临时装甲掩体", 30, 38, "normal", 2, (
        MoveDef("shell_bash", "装甲撞击", INTENT_ATTACK_DEFEND, damage=9, block=9, text="以壳为盾为锤"),
        MoveDef("scavenge", "拾荒加固", INTENT_BUFF, effect=eff_plated, text="捡拾残骸，获得甲壳"),
        MoveDef("spite_bite", "怨恨射击", INTENT_ATTACK, damage=12,
                effect=eff_poison, text="带毒的撕咬"),
    ), art="trench_abyss_hermit", desc="精锐：用别人的装甲板拼出来的掩体，能挡也能砸。"),

    EnemyDef("cold_vent_worm", "火焰喷射阵地", 40, 48, "normal", 2, (
        MoveDef("vent_blast", "火焰喷射", INTENT_ATTACK, damage=7, hits=2, text="滚烫喷流"),
        MoveDef("scald", "烫伤喷射", INTENT_ATTACK_DEBUFF, damage=5,
                effect=eff_frail, text="烫伤，施加脆弱"),
        MoveDef("retract", "缩回工事", INTENT_DEFEND, block=15, text="缩回管内"),
    ), art="trench_cold_vent_worm", desc="精锐：在冰与火之间来回扫射的喷射口。"),

    EnemyDef("ghost_net", "反坦克拒网", 26, 34, "normal", 2, (
        MoveDef("entangle_net", "反坦克拒网", INTENT_ATTACK_DEBUFF, damage=4,
                effect=eff_entangle, text="拖网缠身"),
        MoveDef("drag", "拖拽绞杀", INTENT_ATTACK, damage=6, hits=3, text="拖向深处"),
        MoveDef("mend", "修补工事", INTENT_DEFEND, block=12, text="灵体补网"),
    ), art="trench_ghost_net", desc="精锐：看似空无一物的区域，布满了缠住履带的钢索网。"),

    # ---- ACT 2 精英 4 ----
    EnemyDef("elite_deep_oracle", "精锐·战地指挥所", 66, 78, "elite", 2, (
        MoveDef("summon_echoes", "呼叫增援", INTENT_BUFF, effect=eff_summon_two, text="召出两个回声体"),
        MoveDef("rite", "战场仪式", INTENT_BUFF, effect=eff_ritual2, text="获得 2 层仪式"),
        MoveDef("mind_lash", "通讯干扰", INTENT_ATTACK, damage=13, text="精神撕裂"),
        MoveDef("prophecy", "战场预言", INTENT_DEBUFF, effect=eff_abyss_mark3, text="湮灭印记 +3"),
    ), ai=ai_deep_oracle, art="trench_elite_deep_oracle",
        desc="精锐：优先呼叫增援直到场上两个支援单位，然后持续提升火力。"),

    EnemyDef("elite_trench_stalker", "精锐·装甲猎兵", 70, 82, "elite", 2, (
        MoveDef("lunge", "装甲突击", INTENT_ATTACK, damage=15, text="高速穿刺"),
        MoveDef("hunt", "猎杀标定", INTENT_ATTACK_DEBUFF, damage=8,
                effect=eff_hunted, text="标记，受伤 +25%"),
        MoveDef("frenzy", "狂暴冲锋", INTENT_BUFF, effect=eff_strength_up3, text="力量 +3"),
        MoveDef("vanish", "隐入硝烟", INTENT_DEFEND, block=18, text="隐入硝烟"),
    ), ai=ai_trench_stalker, art="trench_elite_trench_stalker",
        desc="精锐：耐久低于 35% 进入狂暴；我军掩体厚时改用猎杀标记。"),

    EnemyDef("elite_iron_leviathan_calf", "精锐·虎式重坦", 84, 96, "elite", 2, (
        MoveDef("body_slam", "装甲撞击", INTENT_ATTACK, damage=17, text="庞大身躯撞来"),
        MoveDef("plating", "加挂装甲板", INTENT_DEFEND, block=20, effect=eff_plated, text="甲壳增厚"),
        MoveDef("bellow", "怒吼", INTENT_BUFF, effect=eff_strength_up3, text="怒吼，力量 +3"),
        MoveDef("tail_sweep", "尾部扫射", INTENT_ATTACK_DEFEND, damage=9, block=12, text="尾扫兼防"),
    ), art="trench_elite_iron_leviathan_calf",
        desc="精锐：高耐久高装甲，靠装甲板和怒吼滚雪球。"),

    EnemyDef("elite_siren_choir", "精锐· propaganda 广播连", 62, 74, "elite", 2, (
        MoveDef("song_of_deep", "心理战广播", INTENT_DEBUFF, effect=eff_weaken2,
                text="歌声使你虚弱"),
        MoveDef("dissonant_wave", "干扰波", INTENT_ATTACK_DEBUFF, damage=11,
                effect=eff_frail, text="音波撕扯并施加脆弱"),
        MoveDef("lament", "悲叹广播", INTENT_ATTACK, damage=8, hits=2, text="双段悲叹"),
        MoveDef("chorus", "联合广播", INTENT_BUFF, effect=eff_summon_echo, text="召出回声体"),
    ), art="trench_elite_siren_choir",
        desc="精锐：持续压制并呼叫支援单位，越拖越难打。"),

    # ---- ACT 2 BOSS ----
    EnemyDef("leviathan_rex", "要塞·装甲军团长", 168, 182, "boss", 2, (
        MoveDef("summon_shoal", "呼叫装甲集群", INTENT_BUFF, effect=eff_summon_two,
                text="召出两个回声体助战"),
        MoveDef("crushing_pressure", "深压碾碎", INTENT_ATTACK, damage=18, text="水压碾碎"),
        MoveDef("roar", "军团长咆哮", INTENT_BUFF, effect=eff_strength_up3, text="咆哮，力量 +3"),
        MoveDef("devour", "抵近射击", INTENT_ATTACK_DEFEND, damage=12, block=14,
                effect=eff_self_heal_missing, text="撕咬并回复"),
        MoveDef("frenzy_roar", "狂暴咆哮", INTENT_BUFF, effect=eff_double_strength,
                text="力量翻倍（狂暴阶段）"),
        MoveDef("tidal_wrath", "终末轰击", INTENT_ATTACK, damage=11, hits=3,
                text="终末阶段：三段潮怒"),
    ), ai=ai_leviathan_rex, art="abyss_leviathan_rex",
        desc="【BOSS·三阶段】耐久 >60% 时呼叫装甲集群并以重炮压制；≤60% 进入狂暴，火力翻倍；≤30% 转终末阶段，改为三段覆盖轰击。"
             "力量翻倍；≤30% 转终末阶段，改为三段潮怒。"),

    # ================= ACT 3 · 湮灭 (normal 12 / elite 5 / boss 1) =================
    EnemyDef("void_shade", "游击队伏兵", 44, 54, "normal", 3, (
        MoveDef("void_touch", "游击袭扰", INTENT_ATTACK, damage=16, text="抽走体温"),
        MoveDef("fade", "隐入硝烟", INTENT_DEFEND, block=16, effect=eff_intangible, text="获得无形"),
        MoveDef("despair", "绝望广播", INTENT_DEBUFF, effect=eff_weaken2, text="低语，2 层虚弱"),
    ), art="abyss_void_shade", desc="精锐：没有轮廓，只有缺失——你永远不知道他们从哪来。"),

    EnemyDef("abyss_serpent", "重型装甲列车", 50, 60, "normal", 3, (
        MoveDef("constrict", "绞紧封锁", INTENT_ATTACK_DEBUFF, damage=8,
                effect=eff_entangle, text="绞紧并封甲"),
        MoveDef("swallow_whole", "整口吞没", INTENT_ATTACK, damage=19, text="整口吞下"),
        MoveDef("shed", "更换装甲", INTENT_DEFEND, block=17, effect=eff_dexterity, text="蜕鳞增益"),
    ), art="abyss_abyss_serpent", desc="精锐：装甲板上的弹痕是无数支部队的遗言。"),

    EnemyDef("whale_ghost", "幽灵装甲师", 56, 66, "normal", 3, (
        MoveDef("ghost_song", "幽灵电台", INTENT_DEBUFF, effect=eff_memory_loss3, text="记忆流失加剧"),
        MoveDef("phantom_ram", "幻影冲撞", INTENT_ATTACK, damage=17, text="灵魂撞击"),
        MoveDef("mist_form", "化作烟幕", INTENT_DEFEND, block=18, text="化作水雾"),
    ), art="abyss_whale_ghost", desc="精锐：一支早已被歼灭的部队，仍在按原定计划推进。"),

    EnemyDef("bone_coral_hydra", "多炮塔重型坦克", 60, 70, "normal", 3, (
        MoveDef("three_bites", "三炮塔齐射", INTENT_ATTACK, damage=7, hits=3, text="三个头同时咬"),
        MoveDef("regrow", "修复炮塔", INTENT_BUFF, effect=eff_regenerate, text="再生"),
        MoveDef("coral_spit", "破片喷射", INTENT_ATTACK_DEBUFF, damage=6,
                effect=eff_vulnerable, text="骨刺喷射，施加易伤"),
    ), art="abyss_bone_coral_hydra", desc="精锐：打掉一个炮塔，还有两个在转。"),

    EnemyDef("drowned_king", "沦陷区总督", 54, 64, "normal", 3, (
        MoveDef("royal_decree", "总督令", INTENT_DEBUFF, effect=eff_frail, text="王令：脆弱"),
        MoveDef("scepter_smash", "权杖重击", INTENT_ATTACK, damage=18, text="权杖落下"),
        MoveDef("crown_guard", "总督卫队", INTENT_DEFEND, block=20, effect=eff_artifact, text="获得神器"),
    ), art="abyss_drowned_king", desc="精锐：他在废墟里加冕，王座下压着整座城市。"),

    EnemyDef("echo_of_oblivion", "无线电干扰站", 40, 50, "normal", 3, (
        MoveDef("oblivion_wave", "湮灭波", INTENT_ATTACK_DEBUFF, damage=12,
                effect=eff_abyss_mark, text="印记 +2"),
        MoveDef("repeat", "重复干扰", INTENT_ATTACK, damage=6, hits=3, text="三重回响"),
        MoveDef("nullify", "信号归零", INTENT_DEFEND, block=15, effect=eff_intangible, text="获得无形"),
    ), art="abyss_echo_of_oblivion", desc="精锐：你说过的话，被它一遍遍原样播回来。"),

    EnemyDef("nightmare_crab", "夜间重炮阵地", 66, 76, "normal", 3, (
        MoveDef("claw_crush", "重炮粉碎", INTENT_ATTACK, damage=20, text="双钳合拢"),
        MoveDef("nightmare_shell", "夜战装甲", INTENT_DEFEND, block=22,
                effect=eff_thorns, text="甲壳与荆棘"),
        MoveDef("terror_look", "恐惧凝视", INTENT_DEBUFF, effect=eff_weaken2, text="恐惧，2 层虚弱"),
    ), art="abyss_nightmare_crab", desc="精锐：整夜不停的炮击，闭上眼也躲不掉。"),

    EnemyDef("sunken_titan", "超级重型臼炮", 90, 104, "normal", 3, (
        MoveDef("titan_fist", "臼炮重击", INTENT_ATTACK, damage=22, text="巨拳轰落"),
        MoveDef("titan_guard", "要塞壁垒", INTENT_DEFEND, block=24,
                effect=eff_metallicize, text="金属化壁垒"),
        MoveDef("quake", "震爆轰击", INTENT_ATTACK_DEBUFF, damage=8, hits=2,
                effect=eff_frail, text="震击，施加脆弱"),
    ), art="abyss_sunken_titan", desc="精锐：一整座要塞级的臼炮，一炮就是一个足球场。"),

    EnemyDef("soul_harvester", "战地宪兵队", 46, 56, "normal", 3, (
        MoveDef("reap", "战场收割", INTENT_ATTACK, damage=15,
                effect=eff_self_heal_missing, text="收割并回血"),
        MoveDef("soul_chain", "锁链封锁", INTENT_ATTACK_DEBUFF, damage=7,
                effect=eff_entangle, text="锁链缠身"),
        MoveDef("harvest_moon", "月夜集结", INTENT_BUFF, effect=eff_strength_up3, text="月下蓄力"),
    ), art="abyss_soul_harvester", desc="精锐：他们清点的是没走完的路和没送回的信。"),

    EnemyDef("void_whale_calf", "新型重坦原型车", 58, 68, "normal", 3, (
        MoveDef("void_ram", "原型车冲撞", INTENT_ATTACK, damage=17, text="原型车冲撞"),
        MoveDef("devour_light", "吞光", INTENT_ATTACK_DEBUFF, damage=9,
                effect=eff_memory_loss, text="吞掉光线，记忆流失"),
        MoveDef("bubble_shield", "烟幕护盾", INTENT_DEFEND, block=19, text="烟幕护盾"),
    ), art="abyss_void_whale_calf", desc="精锐：它还只是原型，但装甲已经挡下了一切。"),

    EnemyDef("final_herald", "停战谈判代表", 52, 62, "normal", 3, (
        MoveDef("herald_horn", "谈判号角", INTENT_BUFF, effect=eff_ritual2, text="号角，2 层仪式"),
        MoveDef("judgment", "最终裁决", INTENT_ATTACK, damage=16, text="光刃裁决"),
        MoveDef("seal", "封锁令", INTENT_DEBUFF, effect=eff_weaken2, text="封印，2 层虚弱"),
    ), art="abyss_final_herald", desc="精锐：他吹响的号角，是给所有人的。"),

    EnemyDef("drowned_ship", "装甲列车炮组", 72, 84, "normal", 3, (
        MoveDef("cannon_broadside", "列车炮齐射", INTENT_ATTACK, damage=9, hits=2, text="舷炮齐射"),
        MoveDef("ghost_crew", "亡灵车组", INTENT_BUFF, effect=eff_summon_leech, text="召出吸血蛭"),
        MoveDef("hull_repair", "抢修车体", INTENT_DEFEND, block=21, effect=eff_regenerate, text="修补并再生"),
    ), art="abyss_drowned_ship", desc="精锐：列车还在轨道上行驶，只是车厢里的人都成了灰。"),

    # ---- ACT 3 精英 5 ----
    EnemyDef("elite_bone_leviathan", "精锐·超重型坦克", 120, 136, "elite", 3, (
        MoveDef("bone_crush", "重装碾压", INTENT_ATTACK, damage=21, text="白骨巨颚"),
        MoveDef("marrow_guard", "装甲壁垒", INTENT_DEFEND, block=26, effect=eff_plated, text="覆甲增厚"),
        MoveDef("death_roll", "死亡翻滚", INTENT_ATTACK, damage=12, hits=2, text="两段翻滚"),
        MoveDef("call_shoal", "呼叫烟幕掩护", INTENT_BUFF, effect=eff_summon_shade, text="召出烟幕分队"),
    ), art="abyss_elite_bone_leviathan", desc="精锐：高耐久高装甲，会在中段释放烟幕掩护。"),

    EnemyDef("elite_whale_priest", "精锐·集团军参谋部", 100, 116, "elite", 3, (
        MoveDef("sacrament", "战地圣礼", INTENT_BUFF, effect=eff_ritual2, text="2 层仪式"),
        MoveDef("bone_spike", "穿甲穿刺", INTENT_ATTACK, damage=18, text="骨刺穿体"),
        MoveDef("curse_of_abyss", "标定诅咒", INTENT_DEBUFF, effect=eff_abyss_mark3, text="印记 +3"),
        MoveDef("reliquary", "圣物箱", INTENT_DEFEND, block=22, effect=eff_heal15, text="回血并防御"),
    ), art="abyss_elite_whale_priest", desc="精锐：增援叠加 + 标定灼烧，越拖越致命。"),

    EnemyDef("elite_abyss_watcher_echo", "精锐·观测所前哨", 108, 124, "elite", 3, (
        MoveDef("echo_gaze", "前哨标定", INTENT_DEBUFF, effect=eff_abyss_mark3, text="印记 +3"),
        MoveDef("echo_rend", "前哨覆盖", INTENT_ATTACK, damage=9, hits=3, text="三段撕裂"),
        MoveDef("echo_veil", "前哨烟幕", INTENT_DEFEND, block=20, effect=eff_intangible, text="获得无形"),
        MoveDef("echo_scream", "前哨警报", INTENT_ATTACK_DEBUFF, damage=10, effect=eff_weaken2, text="尖啸并虚弱"),
    ), art="abyss_elite_abyss_watcher_echo", desc="精锐：BOSS 的前哨，机制更狠但耐久更低。"),

    EnemyDef("elite_kraken", "精锐·多管火箭炮营", 132, 148, "elite", 3, (
        MoveDef("eight_arms", "八管齐射", INTENT_ATTACK, damage=6, hits=4, text="四段触手连击"),
        MoveDef("drag_down", "拖入火网", INTENT_ATTACK_DEBUFF, damage=13,
                effect=eff_entangle, text="缠绕并封甲"),
        MoveDef("ink_ocean", "全频段干扰", INTENT_DEBUFF, effect=eff_memory_loss2, text="记忆大量流失"),
        MoveDef("regenerate_arms", "补充弹药", INTENT_BUFF, effect=eff_regenerate, text="再生"),
    ), art="abyss_elite_kraken", desc="精锐：四段覆盖射击 + 通讯压制，考验续航。"),

    EnemyDef("elite_coral_tyrant", "精锐·要塞炮台", 116, 130, "elite", 3, (
        MoveDef("tyrant_smash", "炮台重击", INTENT_ATTACK, damage=23, text="炮台重击"),
        MoveDef("reef_wall", "要塞胸墙", INTENT_DEFEND, block=28, effect=eff_thorns, text="礁墙与荆棘"),
        MoveDef("summon_polyp", "召出支援车", INTENT_BUFF, effect=eff_summon_crab, text="召出支援车"),
        MoveDef("bleach", "白化伪装", INTENT_DEBUFF, effect=eff_frail, text="白化，施加脆弱"),
    ), art="abyss_elite_coral_tyrant", desc="精锐：极厚掩体 + 征召支援，需要穿甲或燃烧。"),

    # ---- ACT 3 BOSS ----
    EnemyDef("hollow_whale", "要塞·最高统帅部", 210, 230, "boss", 3, (
        MoveDef("void_veil", "升起烟幕", INTENT_DEFEND, block=24,
                effect=eff_intangible, text="获得无形，几乎免疫伤害"),
        MoveDef("soul_drain", "灵魂汲取", INTENT_ATTACK, damage=20,
                effect=eff_self_heal_missing, text="汲取生命并回复"),
        MoveDef("mark_of_abyss", "标定印记", INTENT_DEBUFF, effect=eff_abyss_mark3,
                text="湮灭印记 +3"),
        MoveDef("echo_of_oblivion", "湮灭回响", INTENT_ATTACK_DEBUFF, damage=9, hits=2,
                effect=eff_memory_loss, text="记忆流失 + 双段"),
    ), ai=ai_hollow_whale, art="abyss_hollow_whale",
        desc="【BOSS·独特机制】每 3 回合升起「烟幕」获得无形，几乎免疫伤害；用「标定印记」在回合结束时持续灼烧我军；耐久过半后改为灵魂汲取 + 湮灭回响。"
             "以「湮灭印记」在回合末持续灼伤玩家；血量过半后改为灵魂汲取 + 湮灭回响。"),
]


# 修正未定义引用的 effect（保持表内声明整洁）
ENEMY_DB: Dict[str, EnemyDef] = {e.id: e for e in ENEMY_LIST}


# --------------------------------------------------------------------------
# 遭遇组合：ENCOUNTERS[act] = {"normal":[...], "elite":[...], "boss":[...]}
# --------------------------------------------------------------------------

def _enc(kind: str, *ids: str) -> dict:
    return {"kind": kind, "enemies": list(ids)}


ENCOUNTERS: Dict[int, dict] = {
    1: {
        "normal": [
            _enc("normal", "spine_minnow", "spine_minnow", "spine_minnow"),
            _enc("normal", "spine_minnow", "tide_crab"),
            _enc("normal", "tide_crab", "gull_flock"),
            _enc("normal", "gull_flock", "gull_flock"),
            _enc("normal", "lantern_jelly", "spine_minnow"),
            _enc("normal", "harpoon_drifter"),
            _enc("normal", "harpoon_drifter", "spine_minnow"),
            _enc("normal", "barnacle_swarm"),
            _enc("normal", "barnacle_swarm", "tide_crab"),
            _enc("normal", "salt_hound", "salt_hound"),
            _enc("normal", "drowned_sailor"),
            _enc("normal", "drowned_sailor", "lantern_jelly"),
            _enc("normal", "reef_stalker", "gull_flock"),
            _enc("normal", "ink_squid", "spine_minnow"),
            _enc("normal", "shoal_serpent"),
            _enc("normal", "shoal_serpent", "tide_crab"),
            _enc("normal", "bone_picker", "bone_picker"),
            _enc("normal", "bone_picker", "drowned_sailor"),
        ],
        "elite": [
            _enc("elite", "elite_tide_hunter"),
            _enc("elite", "elite_shell_crab"),
            _enc("elite", "elite_venom_eel"),
            _enc("elite", "elite_tide_hunter", "spine_minnow"),
            _enc("elite", "elite_shell_crab", "tide_crab"),
            _enc("elite", "elite_barnacle_hulk"),
            _enc("elite", "elite_barnacle_hulk", "barnacle_swarm"),
        ],
        "boss": [
            _enc("boss", "abyss_watcher"),
        ],
    },
    2: {
        "normal": [
            _enc("normal", "trench_lurker"),
            _enc("normal", "trench_lurker", "sonar_bat"),
            _enc("normal", "bone_kraken_spawn", "bone_kraken_spawn"),
            _enc("normal", "pressure_wraith", "sonar_bat"),
            _enc("normal", "lantern_priest", "trench_lurker"),
            _enc("normal", "coral_golem"),
            _enc("normal", "sonar_bat", "sonar_bat", "sonar_bat"),
            _enc("normal", "drowned_chorus"),
            _enc("normal", "anglerfish_lure", "bone_kraken_spawn"),
            _enc("normal", "silt_horror", "pressure_wraith"),
            _enc("normal", "abyss_hermit", "abyss_hermit"),
            _enc("normal", "cold_vent_worm", "sonar_bat"),
            _enc("normal", "ghost_net", "bone_kraken_spawn"),
            _enc("normal", "coral_golem", "abyss_hermit"),
            _enc("normal", "lantern_priest", "drowned_chorus"),
        ],
        "elite": [
            _enc("elite", "elite_deep_oracle"),
            _enc("elite", "elite_trench_stalker"),
            _enc("elite", "elite_iron_leviathan_calf"),
            _enc("elite", "elite_siren_choir"),
            _enc("elite", "elite_deep_oracle", "sonar_bat"),
        ],
        "boss": [
            _enc("boss", "leviathan_rex"),
        ],
    },
    3: {
        "normal": [
            _enc("normal", "void_shade", "void_shade"),
            _enc("normal", "abyss_serpent"),
            _enc("normal", "whale_ghost", "echo_of_oblivion"),
            _enc("normal", "bone_coral_hydra"),
            _enc("normal", "drowned_king", "void_shade"),
            _enc("normal", "echo_of_oblivion", "echo_of_oblivion"),
            _enc("normal", "nightmare_crab"),
            _enc("normal", "sunken_titan"),
            _enc("normal", "soul_harvester", "whale_ghost"),
            _enc("normal", "void_whale_calf", "void_shade"),
            _enc("normal", "final_herald", "echo_of_oblivion"),
            _enc("normal", "drowned_ship", "soul_harvester"),
            _enc("normal", "abyss_serpent", "nightmare_crab"),
            _enc("normal", "bone_coral_hydra", "whale_ghost"),
            _enc("normal", "sunken_titan", "void_whale_calf"),
        ],
        "elite": [
            _enc("elite", "elite_bone_leviathan"),
            _enc("elite", "elite_whale_priest"),
            _enc("elite", "elite_abyss_watcher_echo"),
            _enc("elite", "elite_kraken"),
            _enc("elite", "elite_coral_tyrant"),
            _enc("elite", "elite_kraken", "echo_of_oblivion"),
        ],
        "boss": [
            _enc("boss", "hollow_whale"),
        ],
    },
}


# --------------------------------------------------------------------------
# 查询接口
# --------------------------------------------------------------------------

def all_enemies() -> List[EnemyDef]:
    return list(ENEMY_LIST)


def get_enemy(enemy_id: str) -> EnemyDef:
    return ENEMY_DB[enemy_id]


def enemies_by_act(act: int, tier: Optional[str] = None) -> List[EnemyDef]:
    return [e for e in ENEMY_LIST
            if e.act == act and (tier is None or e.tier == tier)]


def bosses() -> List[EnemyDef]:
    return [e for e in ENEMY_LIST if e.tier == "boss"]


def random_encounter(rng, act: int, kind: str) -> dict:
    """按 act + kind 随机抽一个遭遇组合（深拷贝，避免被引擎改动）。"""
    table = ENCOUNTERS.get(act) or ENCOUNTERS[1]
    pool = table.get(kind) or table["normal"]
    enc = pool[rng.randrange(len(pool))]
    return {"kind": enc["kind"], "enemies": list(enc["enemies"])}


def encounter_of(act: int, kind: str, index: int = 0) -> dict:
    table = ENCOUNTERS.get(act) or ENCOUNTERS[1]
    pool = table.get(kind) or table["normal"]
    enc = pool[index % len(pool)]
    return {"kind": enc["kind"], "enemies": list(enc["enemies"])}


def expected_ai_signature() -> str:
    """文档用：返回 AI 钩子的约定签名文本。"""
    return "fn(self_state, battle, turn) -> MoveDef"


__all__ = [
    "BUFF_STRENGTH", "BUFF_DEXTERITY", "BUFF_VULNERABLE", "BUFF_WEAK", "BUFF_FRAIL",
    "BUFF_POISON", "BUFF_THORNS", "BUFF_METALLICIZE", "BUFF_RITUAL", "BUFF_ARTIFACT",
    "BUFF_PLATED_ARMOR", "BUFF_REGENERATE", "BUFF_INTANGIBLE", "BUFF_STRENGTH_DOWN",
    "BUFF_BARRIER", "BUFF_ABYSS_MARK", "BUFF_ENTANGLE", "BUFF_HUNTED", "BUFF_MEMORY_LOSS",
    "INTENT_ATTACK", "INTENT_ATTACK_DEBUFF", "INTENT_ATTACK_DEFEND", "INTENT_DEFEND",
    "INTENT_BUFF", "INTENT_DEBUFF", "INTENT_UNKNOWN", "INTENT_SLEEP",
    "MINION_SHARK", "MINION_CRAB", "MINION_LANTERN", "MINION_ECHO",
    "MINION_WHALE_SHADE", "MINION_LEECH", "ART_ACT_PREFIX",
    "MoveDef", "EnemyDef", "ENEMY_DB", "ENEMY_LIST", "ENCOUNTERS",
    "all_enemies", "get_enemy", "enemies_by_act", "bosses",
    "random_encounter", "encounter_of", "expected_ai_signature",
]
