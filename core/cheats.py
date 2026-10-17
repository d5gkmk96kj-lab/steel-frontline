"""钢铁战线 Steel Frontline — 作弊码 / 兑换码系统。

设计原则
--------
* **零 UI 依赖**：本模块只操作 ``core`` 的公开接口，Tkinter 版与 PyQt6 版共用。
* **不破坏正常流程**：作弊码只走已有公开方法（``play_card`` / ``heal`` / ``add_card`` …），
  不直接改内部字段，因此不会让引擎进入不一致状态。
* **可重复兑换**：每个码都有冷却/幂等处理（见 ``CHEAT_DEFS`` 的 ``once`` 字段）。
* **可审计**：``CheatRegistry`` 记录使用历史，方便写进结算界面或存档。

用法
----
    from core import cheats
    reg = cheats.CheatRegistry()
    ok, msg = reg.redeem("manpower", run=run, battle=battle)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import cards as C
from core import enemies as E
from core import engine as EN
from core import relics as R
from core import run as RUN


# --------------------------------------------------------------------------
# 特殊作弊卡牌 id（延迟注册，避免 import 顺序问题）
# --------------------------------------------------------------------------
CHEAT_CARD_STRAT_BOMB = "cheat_strategic_bomb"
CHEAT_CARD_GOD_SHIELD = "cheat_god_shield"
CHEAT_CARD_MANPOWER = "cheat_manpower_drop"
#: 彩蛋卡：致敬这个项目最开始想做「鲸鱼卡牌」的那个计划
CHEAT_CARD_WHALE = "whale"

_CHEAT_CARDS_READY = False


def _ensure_cheat_cards() -> None:
    """把作弊专属卡牌注入 CARD_DB（幂等）。

    注入的是**真实的 CardDef**，所以它们能正常被打出、被 snapshot 读取、
    被 UI 渲染，完全走正常管线。
    """
    global _CHEAT_CARDS_READY
    if _CHEAT_CARDS_READY:
        return

    def fx_strategic_bomb(ctx):
        """战略轰炸：对敌方全体造成 9999 伤害。"""
        ctx.deal_damage_all(9999)

    def fx_god_shield(ctx):
        """钢铁意志：本回合受到的伤害归零（无实体 + 巨额掩体）。"""
        ctx.apply_buff_self(EN.BUFF_INTANGIBLE, 1)
        ctx.gain_block(9999)

    def fx_manpower_drop(ctx):
        """兵力空投：立即回复 50 点总部耐久并召唤一个附属单位。"""
        ctx.heal(50)
        ctx.summon("空降兵班", 30, 8)

    def fx_whale(ctx):
        """鲸鱼：让对手跳过下一回合。

        * 1v1（VersusBattle）：把行动权交给对手再立刻结束它的回合，
          净效果 = 对手这一轮什么都不做，直接轮到我方。
        * 战役（BattleState，单人）：没有"对手回合"这个概念，
          效果落成「立刻再获得一回合」—— 也就是把本回合的
          已用补给还回来、敌人这轮不行动。用眩晕代替最稳妥。
        """
        b = ctx.battle
        try:
            # --- 1v1 ---
            if hasattr(b, "current") and hasattr(b, "end_turn"):
                enemy_side = 1 - int(getattr(ctx.source, "side", 0))
                cur = int(getattr(b, "current", 0))
                if cur != enemy_side:
                    b.end_turn(cur, _force=True)
                b.end_turn(enemy_side, _force=True)
                return
            # --- 战役（单人）：没有"对手回合"，
            #     效果落成「敌人这一轮全体不行动」。
            #     引擎靠 _enemy_queue 逐个执行敌人行动，清空它就是跳过整轮。
            try:
                b._enemy_queue = []          # 本轮没人行动
                b._whale_skip = True         # 记账，给 UI 显示用
            except Exception:
                pass
            try:
                b.log_msg("巨大的影子掠过战场。所有敌人这一轮都没有行动。")
            except Exception:
                pass
        except Exception:
            pass

    specs = [
        # ---- 彩蛋：致敬最初的「鲸鱼卡牌」企划 ----
        dict(id=CHEAT_CARD_WHALE, name="鲸鱼吉祥物", cost=0, type="skill",
             rarity=C.RARITY_RARE, arch=C.ARCH_SUMMON, target="self",
             text="战火之前，我梦见深海巨兽。\n"
                  "三个名字用下划线缝起：\n"
                  "鲸鱼・纸牌・对抗\n"
                  "唤醒它的门是 F1。",
             effect=fx_whale, keywords=("彩蛋",)),
        dict(id=CHEAT_CARD_STRAT_BOMB, name="战略轰炸", cost=0, type="attack",
             rarity=C.RARITY_RARE, arch=C.ARCH_ATTACK, target="all_enemies",
             text="对敌方全体造成 9999 点伤害。", effect=fx_strategic_bomb,
             damage=9999, keywords=("作弊", "战略")),
        dict(id=CHEAT_CARD_GOD_SHIELD, name="钢铁意志", cost=0, type="skill",
             rarity=C.RARITY_RARE, arch=C.ARCH_BLOCK, target="self",
             text="本回合受到的伤害降为 1，并获得 9999 点掩体。",
             effect=fx_god_shield, keywords=("作弊", "防御")),
        dict(id=CHEAT_CARD_MANPOWER, name="兵力空投", cost=0, type="skill",
             rarity=C.RARITY_RARE, arch=C.ARCH_SUMMON, target="self",
             text="回复 50 点总部耐久，并召唤一个空降兵班。",
             effect=fx_manpower_drop, keywords=("作弊", "支援")),
    ]
    for s in specs:
        if s["id"] in C.CARD_DB:
            continue
        cd = C.CardDef(**s)
        try:
            C.CARD_DB[s["id"]] = cd          # type: ignore[index]
        except Exception:
            pass
    _CHEAT_CARDS_READY = True


# --------------------------------------------------------------------------
# 兑换码实现
# --------------------------------------------------------------------------

def _need_battle(battle) -> Optional[str]:
    return None if battle is not None else "此兑换码只能在战斗中使用。"


def _need_run(run) -> Optional[str]:
    return None if run is not None else "还没有开始战役。"


def code_blitz(run, battle, state) -> Tuple[bool, str]:
    """it — 立即完成当前回合的所有部署动作，跳过等待。

    效果：本回合已打出的牌全部返还补给，手牌补满，
    并**立刻结束玩家回合**（敌方行动由 UI 按正常节奏推进，不阻塞）。
    """
    if battle is None:
        return False, _need_battle(battle)
    p = battle.player
    # 返还本回合消耗的补给
    p.energy = p.max_energy
    # 手牌补满到 7 张，方便继续部署
    have = len(p.hand)
    if have < 7:
        battle.draw_cards(p, 7 - have)
    battle.log_msg("【兑换码】闪电部署：补给已回满，手牌已补充。")
    return True, "闪电部署已生效：补给回满、手牌补至 7 张。"


def code_research_all(run, battle, state) -> Tuple[bool, str]:
    """research all — 立刻解锁游戏内所有卡牌、遗物、支援装备，并填满图鉴。

    对战模式下没有「战役牌组」这个概念，改为把全部卡牌塞进手牌 ——
    效果等价于「科技全解锁」，房主能随意取用。
    """
    if run is None:
        if battle is not None and hasattr(battle, "sides"):
            try:
                _b = getattr(battle, "_b", battle)
                me = _b.sides[0].combatant
                n = 0
                for cd in C.CARD_DB.values():
                    if cd.type in ("status", "curse"):
                        continue
                    try:
                        me.hand.append(C.make_card(cd.id))
                        n += 1
                    except Exception:
                        continue
                    if n >= 10:          # 手牌上限：给 10 张足够多了
                        break
                try:
                    _b.log.append("【兑换码】科技全解锁：全部卡牌已进入手牌。")
                except Exception:
                    pass
                return True, "科技全解锁：%d 张卡牌已加入手牌。" % n
            except Exception as exc:
                return False, "对战模式下解锁失败：%s" % exc
        return False, _need_run(run)
    meta = state.get("meta")
    added_cards = added_relics = 0
    # 把所有非 status/curse 卡牌加入牌组（各一张，避免重复膨胀）
    owned = {c.def_id for c in run.deck}
    for cd in C.CARD_DB.values():
        if cd.type in ("status", "curse"):
            continue
        if cd.id.startswith("cheat_"):
            continue
        if cd.id in owned:
            continue
        run.add_card(cd.id)
        added_cards += 1
    # 解锁全部遗物
    for rd in R.RELIC_DB.values():
        if rd.rarity == "starter":
            continue
        if rd.id in run.relics:
            continue
        run.add_relic(rd.id)
        added_relics += 1
    # 填满图鉴
    if meta is not None:
        for cid in C.CARD_DB:
            try:
                meta.see_card(cid)
            except Exception:
                pass
        for rid in R.RELIC_DB:
            try:
                meta.see_relic(rid)
            except Exception:
                pass
        for eid in E.ENEMY_DB:
            try:
                meta.see_enemy(eid)
            except Exception:
                pass
    # 给点补给品
    for pid in getattr(RUN, "POTION_POOL", []) or []:
        try:
            run.add_potion(pid)
        except Exception:
            pass
    return True, ("研究全解锁：新增 %d 张卡牌、%d 件勋章，图鉴已填满。"
                  % (added_cards, added_relics))


def code_defense(run, battle, state) -> Tuple[bool, str]:
    """ic — 秒建防线：立刻瞬间完成全部工事建造。"""
    if battle is None:
        return False, _need_battle(battle)
    p = battle.player
    p.block = 0
    gained = battle.gain_block(p, 999)
    # 顺带给一层铁丝网，体现「防线建成」
    battle.apply_buff(p, EN.BUFF_THORNS, 10)
    battle.log_msg("【兑换码】秒建防线：工事已瞬间完工。")
    return True, "防线已秒建完成：获得 %d 点掩体 + 10 层铁丝网。" % gained


def code_debug_nuke(run, battle, state) -> Tuple[bool, str]:
    """debug_nuke — 获得一张「战略轰炸」卡牌。"""
    _ensure_cheat_cards()
    if battle is not None:
        battle.add_card_to_hand(CHEAT_CARD_STRAT_BOMB)
        battle.log_msg("【兑换码】战略轰炸已投递到手牌。")
        return True, "「战略轰炸」已加入手牌（对敌方全体 9999 伤害）。"
    if run is not None:
        run.add_card(CHEAT_CARD_STRAT_BOMB)
        return True, "「战略轰炸」已加入牌组（下次战斗可抽到）。"
    return False, _need_run(run)


def code_god_mode(run, battle, state) -> Tuple[bool, str]:
    """god_mode — 我方本回合受到的伤害强制为 0。"""
    if battle is None:
        return False, _need_battle(battle)
    p = battle.player
    # 无实体把伤害压到 1；再叠 9999 掩体等效于「本回合 0 伤害」
    battle.apply_buff(p, EN.BUFF_INTANGIBLE, 1)
    battle.gain_block(p, 9999)
    battle.log_msg("【兑换码】上帝模式：本回合伤害免疫。")
    return True, "上帝模式已启用：本回合受到的伤害被强制抵消。"


# --------------------------------------------------------------------------
# 战斗结束通知
# --------------------------------------------------------------------------
# 兑换码直接改引擎状态后，**界面层并不知情** —— 于是画面卡在战斗里
# 什么键都按不动（用户实际遇到）。core 不能 import UI，所以由 UI 注册
# 一个回调，兑换码结束战斗时调用它。
_battle_over_hook = None


def set_battle_over_hook(fn) -> None:
    """UI 注册：战斗被兑换码结束时如何通知界面。fn(result:str) -> None"""
    global _battle_over_hook
    _battle_over_hook = fn if callable(fn) else None


def _notify_battle_over(battle) -> None:
    """如果战斗已经结束，通知界面。"""
    try:
        res = str(battle.result()) if battle is not None else "ongoing"
    except Exception:
        res = "ongoing"
    if res not in ("won", "lost"):
        try:
            ph = str(getattr(battle, "phase", "ongoing"))
            if ph in ("won", "lost"):
                res = ph
        except Exception:
            pass
    if res not in ("won", "lost"):
        return
    try:
        if callable(_battle_over_hook):
            _battle_over_hook(res)
    except Exception:
        pass


def code_annex_all(run, battle, state) -> Tuple[bool, str]:
    """annex all — 直接秒杀当前战斗所有敌人，瞬间结算。"""
    if battle is None:
        return False, _need_battle(battle)
    killed = 0
    for e in list(battle.enemies):
        if e.alive():
            e.hp = 0
            killed += 1
    battle.log_msg("【兑换码】全面吞并：敌方部队被瞬间肃清。")
    try:
        battle._check_end()
    except Exception:
        pass
    _notify_battle_over(battle)
    return True, "已肃清 %d 个敌方单位，战斗立即结算。" % killed


def code_manpower(run, battle, state) -> Tuple[bool, str]:
    """manpower — 总部 +50 耐久上限与当前耐久，并 +50 兵力（召唤/补给）。"""
    msgs = []
    if run is not None:
        run.max_hp += 50
        run.hp = min(run.max_hp, run.hp + 50)
        msgs.append("总部耐久 +50（当前 %d/%d）" % (run.hp, run.max_hp))
    if battle is not None:
        p = battle.player
        p.max_hp += 50
        p.hp = min(p.max_hp, p.hp + 50)
        battle.gain_block(p, 50)
        battle.summon(battle.player, "增援营", 50, 10)
        msgs.append("战场 +50 掩体并召唤增援营")
    if not msgs:
        return False, _need_run(run)
    return True, "兵力补充完成：" + "；".join(msgs) + "。"


# --------------------------------------------------------------------------
# 对战模式（core/versus.py）适配
# --------------------------------------------------------------------------
def _is_versus(battle) -> bool:
    """判断这是不是 1v1 对战引擎（而不是单机 engine）。"""
    return battle is not None and hasattr(battle, "sides") \
        and not hasattr(battle, "player")


class _VersusAdapter:
    """把 ``VersusBattle`` 适配成单机 engine 的接口，让既有兑换码直接可用。

    只实现兑换码真正用到的那几个方法，尽量简单 —— 不追求完整对齐。
    """

    def __init__(self, battle, side: int = 0) -> None:
        self._b = battle
        self._side = int(side)

    # -- 单机接口映射 ---------------------------------------------------
    @property
    def player(self):
        side = self._b.sides[self._side]
        c = side.combatant
        # 兑换码会写 p.hp / p.max_hp，这里直接返回真身（Combatant）
        return c

    @property
    def enemies(self):
        return [self._b.sides[1 - self._side].combatant]

    def apply_buff(self, target, buff, n=1):
        try:
            return target.add_buff(buff, n)
        except Exception:
            return None

    def gain_block(self, target, n):
        """返回**实际增加**的掩体数（兑换码会把它拼进提示文本）。"""
        try:
            before = int(getattr(target, "block", 0))
            target.block = before + int(n)
            return int(target.block) - before
        except Exception:
            return 0

    def summon(self, *_a, **_k):
        return None                       # 对战里没有召唤位，静默跳过

    def log_msg(self, msg: str):
        try:
            self._b.log.append(str(msg))
        except Exception:
            pass

    def _check_end(self):
        try:
            return self._b._check_end()
        except Exception:
            return None

    # -- 让「秒杀」类兑换码在对战里变成「直接获胜」----------------------
    def __getattr__(self, name):
        # 未实现的方法返回空操作，避免 AttributeError 打断兑换流程
        def _noop(*_a, **_k):
            return None
        return _noop


def _wrap_battle(battle):
    """兑换码入口统一走这里：对战引擎自动适配，单机引擎原样返回。"""
    if _is_versus(battle):
        return _VersusAdapter(battle)
    return battle


# --------------------------------------------------------------------------
# 兑换码表
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CheatDef:
    code: str               # 兑换码（小写，输入时忽略大小写与空格）
    name: str               # 显示名
    desc: str               # 效果说明
    fn: Callable            # fn(run, battle, state) -> (ok, msg)
    once: bool = False      # True = 每局只能兑换一次
    aliases: tuple = ()     # 别名


CHEAT_DEFS: List[CheatDef] = [
    CheatDef("it", "闪电部署",
             "立即完成本回合所有部署动作：补给回满、手牌补至 7 张，跳过等待。",
             code_blitz, aliases=("blitz",)),
    CheatDef("research all", "研究全解锁",
             "解锁全部卡牌、勋章与支援装备，并填满图鉴。",
             code_research_all, once=True, aliases=("research_all", "researchall")),
    CheatDef("ic", "秒建防线",
             "立刻瞬间完成全部工事建造：获得 999 点掩体 + 10 层铁丝网。",
             code_defense, aliases=("instant_build",)),
    CheatDef("debug_nuke", "战略轰炸",
             "获得一张「战略轰炸」卡牌，打出后对敌方全体造成 9999 伤害。",
             code_debug_nuke, aliases=("nuke", "debug nuke")),
    CheatDef("god_mode", "上帝模式",
             "本回合我方受到的伤害强制归零。",
             code_god_mode, aliases=("godmode", "god")),
    CheatDef("annex all", "全面吞并",
             "直接肃清当前战斗全部敌人，瞬间结算通关。",
             code_annex_all, once=True, aliases=("annex_all", "annexall")),
    CheatDef("manpower", "兵力补充",
             "总部 +50 耐久上限与当前耐久，并 +50 可用兵力。",
             code_manpower, aliases=("mp",)),
]

def _normalize(s: str) -> str:
    """统一大小写与分隔符：'Research All' / 'research_all' -> 'researchall'。"""
    return "".join(str(s).lower().replace("_", " ").replace("-", " ").split())


_CHEAT_INDEX: Dict[str, CheatDef] = {}
for _d in CHEAT_DEFS:
    _CHEAT_INDEX[_normalize(_d.code)] = _d
    for _a in _d.aliases:
        _CHEAT_INDEX[_normalize(_a)] = _d


def find(code: str) -> Optional[CheatDef]:
    """按兑换码查找（大小写/下划线/空格不敏感）。"""
    return _CHEAT_INDEX.get(_normalize(code))


def all_codes() -> List[CheatDef]:
    return list(CHEAT_DEFS)


# --------------------------------------------------------------------------
# 注册表（记录已用过的码，支持 once 语义）
# --------------------------------------------------------------------------

class CheatRegistry:
    """跟踪兑换历史。可随存档持久化。"""

    def __init__(self) -> None:
        self.used: Dict[str, int] = {}          # code -> 使用次数
        self.log: List[str] = []

    # -- 查询 -----------------------------------------------------------
    def has_used(self, code: str) -> bool:
        d = find(code)
        key = d.code if d else _normalize(code)
        return self.used.get(key, 0) > 0

    def can_redeem(self, code: str) -> Tuple[bool, str]:
        d = find(code)
        if d is None:
            return False, "无效的兑换码。"
        if d.once and self.has_used(d.code):
            return False, "「%s」每局只能兑换一次。" % d.name
        return True, d.name

    # -- 兑换 -----------------------------------------------------------
    @staticmethod
    def is_god_mode(run=None, meta=None) -> bool:
        """当前是否处于「神人模式」（最高难度档）—— 该模式禁用一切作弊。"""
        try:
            if run is not None:
                asc = int(getattr(run, "ascension", 0) or 0)
            elif meta is not None:
                asc = int(getattr(meta, "ascension_unlocked", 0) or 0)
            else:
                return False
            from core.run import ASCENSION_TABLE  # type: ignore
            return asc >= len(ASCENSION_TABLE) - 1
        except Exception:
            return False

    def redeem(self, code: str, run=None, battle=None, meta=None
               ) -> Tuple[bool, str]:
        """兑换一个码。返回 (成功, 提示文本)。绝不抛异常。"""
        # 神人模式：最高难度的荣誉挑战，禁用一切作弊。
        # 放在最前面，保证控制台 / 设置界面 / 快捷键三条路径全被拦住。
        if self.is_god_mode(run, meta):
            return False, "神人模式下无法使用兑换码 —— 这是最高难度的荣誉挑战。"
        d = find(code)
        if d is None:
            return False, "无效的兑换码：「%s」" % str(code).strip()
        if d.once and self.has_used(d.code):
            return False, "「%s」每局只能兑换一次。" % d.name
        try:
            ok, msg = d.fn(run, _wrap_battle(battle),
                           {"meta": meta, "registry": self})
        except Exception as exc:                      # 兑换码绝不能拖垮游戏
            return False, "兑换失败（%s）：%s" % (d.name, exc)
        if not ok:
            return False, msg
        self.used[d.code] = self.used.get(d.code, 0) + 1
        self.log.append("[%s] %s — %s" % (d.code, d.name, msg))
        if len(self.log) > 50:
            del self.log[:-50]
        return True, msg

    # -- 存档 -----------------------------------------------------------
    def to_dict(self) -> dict:
        return {"used": dict(self.used), "log": list(self.log[-20:])}

    @staticmethod
    def from_dict(d: Optional[dict]) -> "CheatRegistry":
        reg = CheatRegistry()
        if isinstance(d, dict):
            try:
                reg.used = {str(k): int(v) for k, v in (d.get("used") or {}).items()}
                reg.log = [str(x) for x in (d.get("log") or [])]
            except Exception:
                pass
        return reg

    def reset(self) -> None:
        self.used.clear()
        self.log.clear()


# 便捷：一次性兑换（不关心历史）
def redeem_once(code: str, run=None, battle=None, meta=None) -> Tuple[bool, str]:
    return CheatRegistry().redeem(code, run=run, battle=battle, meta=meta)
