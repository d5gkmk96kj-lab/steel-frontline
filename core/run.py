"""钢铁战线 Steel Frontline — 局内流程与元进度。

严格实现 ARCHITECTURE.md 第 7 节。

「玩很久」的七项保证（第 7 节硬性要求）都实现在这里：
1. 20 档飞升   2. 元进度解锁   3. 成就 ≥25   4. 图鉴
5. 每日种子    6. 本地排行榜   7. 存档续玩
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core import cards as C
from core import story as STORY
from core import enemies as E
from core import events as EV
from core import relics as R

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_BASE, "data")
SAVE_PATH = os.path.join(DATA_DIR, "save.json")
META_PATH = os.path.join(DATA_DIR, "meta.json")

ACTS = (1, 2, 3)
MAP_ROWS = 15
NODE_KINDS = ("battle", "elite", "event", "shop", "rest", "treasure", "boss")

# --------------------------------------------------------------------------
# 20 档飞升参数表：每档叠加真实难度
# --------------------------------------------------------------------------
ASCENSION_TABLE: List[dict] = [
    {"lv": 0,  "name": "初次登陆",    "hp_mult": 1.00, "dmg_mult": 1.00, "elite_hp": 1.00, "start_curse": 0, "rest_heal": 0.30, "desc": "标准难度。"},
    {"lv": 1,  "name": "初现锋芒",    "hp_mult": 1.10, "dmg_mult": 1.00, "elite_hp": 1.05, "start_curse": 0, "rest_heal": 0.30, "desc": "敌人生命 +10%。"},
    {"lv": 2,  "name": "风沙侵蚀",    "hp_mult": 1.15, "dmg_mult": 1.08, "elite_hp": 1.10, "start_curse": 0, "rest_heal": 0.28, "desc": "敌人生命 +15%、伤害 +8%。"},
    {"lv": 3,  "name": "锈甲之重",    "hp_mult": 1.20, "dmg_mult": 1.12, "elite_hp": 1.15, "start_curse": 0, "rest_heal": 0.26, "desc": "精英更加强壮。"},
    {"lv": 4,  "name": "低语回廊",    "hp_mult": 1.25, "dmg_mult": 1.15, "elite_hp": 1.20, "start_curse": 1, "rest_heal": 0.25, "desc": "开局携带 1 张诅咒。"},
    {"lv": 5,  "name": "寒流降临",    "hp_mult": 1.32, "dmg_mult": 1.20, "elite_hp": 1.25, "start_curse": 1, "rest_heal": 0.24, "desc": "敌人全面强化。"},
    {"lv": 6,  "name": "雷区迷航",    "hp_mult": 1.38, "dmg_mult": 1.25, "elite_hp": 1.30, "start_curse": 1, "rest_heal": 0.22, "desc": "商店价格上浮。"},
    {"lv": 7,  "name": "钢铁凝视",    "hp_mult": 1.45, "dmg_mult": 1.30, "elite_hp": 1.35, "start_curse": 1, "rest_heal": 0.21, "desc": "Boss 拥有额外阶段。"},
    {"lv": 8,  "name": "血色黎明",    "hp_mult": 1.52, "dmg_mult": 1.35, "elite_hp": 1.40, "start_curse": 2, "rest_heal": 0.20, "desc": "开局携带 2 张诅咒。"},
    {"lv": 9,  "name": "万骸焦原",    "hp_mult": 1.60, "dmg_mult": 1.42, "elite_hp": 1.48, "start_curse": 2, "rest_heal": 0.19, "desc": "敌人伤害大幅提升。"},
    {"lv": 10, "name": "无光之境",    "hp_mult": 1.70, "dmg_mult": 1.50, "elite_hp": 1.58, "start_curse": 2, "rest_heal": 0.18, "desc": "敌人生命额外 +5%。"},
    {"lv": 11, "name": "焦土焦原",    "hp_mult": 1.80, "dmg_mult": 1.58, "elite_hp": 1.68, "start_curse": 2, "rest_heal": 0.17, "desc": "起始金币减少。"},
    {"lv": 12, "name": "永夜攻势",    "hp_mult": 1.92, "dmg_mult": 1.66, "elite_hp": 1.80, "start_curse": 3, "rest_heal": 0.16, "desc": "开局携带 3 张诅咒。"},
    {"lv": 13, "name": "腐化圣殿",    "hp_mult": 2.05, "dmg_mult": 1.75, "elite_hp": 1.92, "start_curse": 3, "rest_heal": 0.15, "desc": "休息回复量下降。"},
    {"lv": 14, "name": "绞杀战壕",    "hp_mult": 2.20, "dmg_mult": 1.85, "elite_hp": 2.05, "start_curse": 3, "rest_heal": 0.14, "desc": "精英血量翻倍。", "elite_double": True},
    {"lv": 15, "name": "湮灭回响",    "hp_mult": 2.35, "dmg_mult": 1.95, "elite_hp": 2.20, "start_curse": 3, "rest_heal": 0.13, "desc": "普通敌人也拥有能力。"},
    {"lv": 16, "name": "终末使徒",    "hp_mult": 2.55, "dmg_mult": 2.05, "elite_hp": 2.40, "start_curse": 4, "rest_heal": 0.12, "desc": "Boss 血量大幅提升。"},
    {"lv": 17, "name": "寂灭焦土",    "hp_mult": 2.75, "dmg_mult": 2.20, "elite_hp": 2.60, "start_curse": 4, "rest_heal": 0.11, "desc": "所有敌人伤害 +15%。"},
    {"lv": 18, "name": "万古长夜",    "hp_mult": 3.00, "dmg_mult": 2.35, "elite_hp": 2.85, "start_curse": 4, "rest_heal": 0.10, "desc": "商店删卡价格翻倍。"},
    {"lv": 19, "name": "敌国腹地",    "hp_mult": 3.30, "dmg_mult": 2.55, "elite_hp": 3.10, "start_curse": 5, "rest_heal": 0.09, "desc": "敌人全面强化，起始 5 诅咒。"},
    {"lv": 20, "name": "钢铁终焉",    "hp_mult": 3.70, "dmg_mult": 2.80, "elite_hp": 3.40, "start_curse": 5, "rest_heal": 0.08, "desc": "最高难度。愿钢铁与意志与你同在。"},
]


def ascension_params(level: int) -> dict:
    lv = max(0, min(20, int(level)))
    return ASCENSION_TABLE[lv]


# --------------------------------------------------------------------------
# 成就
# --------------------------------------------------------------------------
ACHIEVEMENTS: Dict[str, dict] = {
    "first_blood":    {"name": "初次下潜",   "desc": "打赢第一场战斗。"},
    "first_win":      {"name": "破浪而出",   "desc": "第一次通关。"},
    "act2":           {"name": "深入敌后",   "desc": "抵达第二幕。"},
    "act3":           {"name": "兵临城下",   "desc": "抵达第三幕。"},
    "asc5":           {"name": "自讨苦吃",   "desc": "在飞升 5 或以上通关。"},
    "asc10":          {"name": "受虐狂潮",   "desc": "在飞升 10 或以上通关。"},
    "asc20":          {"name": "钢铁之王",   "desc": "在飞升 20 通关。"},
    "deck_thin":      {"name": "断舍离",     "desc": "以 15 张以下的牌组通关。"},
    "deck_fat":       {"name": "收藏家",     "desc": "牌组达到 40 张。"},
    "rich":           {"name": "富甲一方",   "desc": "单局持有 999 金币。"},
    "relic10":        {"name": "遗物猎人",   "desc": "单局收集 10 件遗物。"},
    "relic20":        {"name": "博物馆长",   "desc": "单局收集 20 件遗物。"},
    "elite_hunter":   {"name": "精英杀手",   "desc": "单局击败 5 个精英。"},
    "boss_slayer":    {"name": "弑君者",     "desc": "击败任意 Boss。"},
    "overkill":       {"name": "过量击杀",   "desc": "单次造成 50 点以上伤害。"},
    "no_damage":      {"name": "毫发无伤",   "desc": "在一场战斗中不受任何伤害获胜。"},
    "poison_master":  {"name": "蚀骨之毒",   "desc": "一局中累计施加 100 层中毒。"},
    "summoner":       {"name": "唤灵者",     "desc": "单场战斗召唤 5 个召唤物。"},
    "strength_30":    {"name": "力拔山兮",   "desc": "力量达到 30。"},
    "block_50":       {"name": "铜墙铁壁",   "desc": "单回合获得 50 点格挡。"},
    "speedrun":       {"name": "疾风骤雨",   "desc": "在 20 分钟内通关。"},
    "pacifist":       {"name": "和平主义者","desc": "赢下一场不使用攻击牌的战斗。"},
    "curse_bearer":   {"name": "诅咒缠身",   "desc": "牌组中同时拥有 5 张诅咒。"},
    "exhaust_all":    {"name": "空空如也",   "desc": "在一场战斗中消耗 20 张牌。"},
    "daily":          {"name": "每日出击",   "desc": "完成一次每日挑战。"},
    "collector":      {"name": "图鉴完成",   "desc": "认识全部卡牌。"},
    "streak3":        {"name": "三连捷",     "desc": "连续通关 3 次。"},
    "comeback":       {"name": "绝地反击",   "desc": "在 5 点生命以下赢下一场战斗。"},
    "perfect_act":    {"name": "完美一幕",   "desc": "以满血状态通过一幕。"},
    "true_ending":    {"name": "钢铁终焉",   "desc": "解锁全部其它成就。"},
}


# --------------------------------------------------------------------------
# 地图
# --------------------------------------------------------------------------
@dataclass
class MapNode:
    id: int
    row: int
    col: int
    kind: str
    edges: List[int] = field(default_factory=list)
    visited: bool = False


class MapGenerator:
    """生成爬塔式分支地图：15 行，第 0 行起点，第 14 行 Boss。"""

    def __init__(self, rng: random.Random, act: int = 1):
        self.rng = rng
        self.act = act

    def generate(self) -> List[MapNode]:
        rng = self.rng
        nodes: List[MapNode] = []
        next_id = 0
        # 每行的列数（中间宽、两端窄）
        widths = []
        for r in range(MAP_ROWS):
            if r == 0 or r == MAP_ROWS - 1:
                widths.append(1)
            elif r in (1, MAP_ROWS - 2):
                widths.append(3)
            else:
                widths.append(4)
        rows: List[List[int]] = []
        for r, w in enumerate(widths):
            ids = []
            for c in range(w):
                nodes.append(MapNode(id=next_id, row=r, col=c, kind="battle"))
                ids.append(next_id)
                next_id += 1
            rows.append(ids)
        # 连线：每个节点连到下一行中列号接近的 1~2 个节点，保证全连通
        for r in range(len(rows) - 1):
            cur, nxt = rows[r], rows[r + 1]
            for i, nid in enumerate(cur):
                # 按比例映射到下一行的位置，保证单调覆盖
                ratio = i / max(1, len(cur) - 1) if len(cur) > 1 else 0.5
                center = ratio * (len(nxt) - 1)
                targets = {int(round(center))}
                targets.add(max(0, min(len(nxt) - 1, int(center) - 1)))
                targets.add(max(0, min(len(nxt) - 1, int(center) + 1)))
                n_targets = 1 if len(nxt) == 1 else rng.choice([1, 2, 2])
                chosen = sorted(rng.sample(sorted(targets), min(n_targets, len(targets))))
                nodes[nid].edges = [nxt[j] for j in chosen]
        # 保证下一行每个节点都被指到（否则会成为孤岛）
        for r in range(len(rows) - 2, -1, -1):
            cur, nxt = rows[r], rows[r + 1]
            incoming = {e for nid in cur for e in nodes[nid].edges}
            for j, tid in enumerate(nxt):
                if tid not in incoming:
                    src = cur[min(len(cur) - 1, int(j / max(1, len(nxt) - 1) * max(0, len(cur) - 1)))]
                    nodes[src].edges = sorted(set(nodes[src].edges + [tid]))
        # 分配节点类型
        boss_ids = rows[-1]
        for nid in boss_ids:
            nodes[nid].kind = "boss"
        for nid in rows[0]:
            nodes[nid].kind = "battle"
        # 休息节点：Boss 前一行必有
        for nid in rows[MAP_ROWS - 2]:
            nodes[nid].kind = "rest"
        # 其它行按权重分配
        for r in range(1, MAP_ROWS - 2):
            for nid in rows[r]:
                nodes[nid].kind = self._roll_kind(r)
        # 兜底：每行至少有一个非战斗节点（除第一行）
        for r in range(1, MAP_ROWS - 2):
            if all(nodes[nid].kind == "battle" for nid in rows[r]):
                nodes[rng.choice(rows[r])].kind = rng.choice(["event", "rest", "shop"])
        return nodes

    def _roll_kind(self, row: int) -> str:
        r = self.rng.random()
        # 精英在前期更少
        elite_p = 0.06 if row < 4 else 0.16
        if r < 0.50:
            return "battle"
        if r < 0.50 + elite_p:
            return "elite"
        if r < 0.68 + elite_p:
            return "event"
        if r < 0.78 + elite_p:
            return "rest"
        if r < 0.88 + elite_p:
            return "shop"
        return "treasure"


# --------------------------------------------------------------------------
# 局内状态
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# RNG 序列化辅助（保证存档往返后随机序列完全一致）
# --------------------------------------------------------------------------
def _serialize_rng(rng: random.Random):
    """把 Random 的完整状态序列化为可 JSON 化的结构。"""
    try:
        state = rng.getstate()
        return {"version": state[0], "keys": list(state[1]), "gauss": state[2]}
    except Exception:
        return None


def _restore_rng(rng: random.Random, data) -> None:
    """从 _serialize_rng 的结果恢复状态。失败则保持原样（不抛异常）。"""
    if not data:
        return
    try:
        g = data.get("gauss")
        rng.setstate((int(data["version"]),
                      tuple(int(x) for x in data["keys"]),
                      None if g is None else float(g)))
    except Exception:
        pass


class RunState:
    def __init__(self):
        self.rng = random.Random()
        self.act = 1
        self.floor = 0
        self.gold = 99
        self.hp = 75
        self.max_hp = 75
        self.deck: List[C.CardInstance] = []
        self.relics: List[str] = []
        self.potions: List[str] = []
        self.map_nodes: List[MapNode] = []
        self.current_node: Optional[int] = None
        self.ascension = 0
        #: 本局选择的辅助角色（指挥官）id
        self.commander = ""
        self.score = 0
        self.seed = 0
        self.run_start_time = 0.0
        self.stats: Dict[str, Any] = {}
        self.seen_events: List[str] = []
        self.remove_count = 0
        self.pending_node: Optional[int] = None
        self.daily = False
        #: "story" = 主线（三幕，打完给结局）；"endless" = 无尽爬塔
        self.mode = "story"
        #: 已播放过的剧情 id（主线段落 + 小人物特写）
        self.story_seen: set = set()
        #: 无尽模式已经循环了几轮（第一轮 = 0）
        self.loop = 0
        #: 待播放的剧情（UI 取走后清空）
        self.pending_story: Optional[dict] = None
        #: 主线是否已通关（本局）
        self.story_cleared = False

    # -- 初始化 -----------------------------------------------------------
    def new_run(self, seed=None, ascension=0, character="whale", daily=False,
                mode: str = "story") -> None:
        if seed is None:
            seed = random.randrange(1, 2 ** 31 - 1)
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.ascension = max(0, min(20, int(ascension)))
        par = ascension_params(self.ascension)
        self.act = 1
        self.floor = 0
        self.gold = max(0, int(99 - 8 * max(0, self.ascension - 10)))
        self.max_hp = 75
        self.hp = 75
        self.deck = [C.make_card(cid) for cid in C.STARTER_DECK]
        for _ in range(int(par.get("start_curse", 0))):
            curses = C.curse_cards()
            if curses:
                self.deck.append(C.make_card(self.rng.choice(curses).id))
        self.relics = [R.STARTER_RELIC]
        self.potions = []
        self.current_node = None
        self.score = 0
        self.pending_node = None
        self.seen_events = []
        self.remove_count = 0
        self.daily = bool(daily)
        self.mode = "endless" if str(mode) == "endless" else "story"
        self.story_seen = set()
        self.loop = 0
        self.pending_story = None
        self.story_cleared = False
        self.run_start_time = time.time()
        self.stats = {
            "elites_killed": 0, "bosses_killed": 0, "damage_dealt": 0,
            "poison_applied": 0, "minions_summoned": 0, "cards_exhausted": 0,
            "cards_played": 0, "turns": 0, "floors": 0, "kills": 0,
        }
        self.map_nodes = MapGenerator(self.rng, self.act).generate()

    # -- 地图 -------------------------------------------------------------
    def reachable_nodes(self) -> List[MapNode]:
        if self.current_node is None:
            return [n for n in self.map_nodes if n.row == 0]
        cur = self.map_nodes[self.current_node]
        out = []
        for e in cur.edges:
            if 0 <= e < len(self.map_nodes) and not self.map_nodes[e].visited:
                out.append(self.map_nodes[e])
        return out

    def node_by_id(self, nid: int) -> Optional[MapNode]:
        if 0 <= nid < len(self.map_nodes):
            return self.map_nodes[nid]
        return None

    def move_to(self, node_id) -> dict:
        """移动到节点，返回该节点要触发的遭遇描述。

        契约：绝不抛异常给调用方；非法输入返回 {"kind": "none"}。
        """
        try:
            nid = int(node_id)
        except (TypeError, ValueError):
            return {"kind": "none"}
        node = self.node_by_id(nid)
        if node is None:
            return {"kind": "none"}
        allowed = {n.id for n in self.reachable_nodes()}
        if node.id not in allowed:
            return {"kind": "none"}
        node.visited = True
        self.current_node = node.id
        self.floor += 1
        self.stats["floors"] = self.floor
        kind = node.kind
        info: Dict[str, Any] = {"kind": kind, "node_id": node.id, "act": self.act,
                                "floor": self.floor}
        if kind in ("battle", "elite", "boss"):
            info["encounter"] = self.roll_encounter(kind)
        elif kind == "event":
            ev = EV.random_event(self.rng, self.act, set(self.seen_events))
            if ev is not None:
                self.seen_events.append(ev.id)
                info["event"] = ev
        elif kind == "shop":
            info["shop"] = EV.build_shop_inventory(self.rng, self.act, self.ascension)
        elif kind == "treasure":
            info["treasure"] = EV.roll_treasure(self.rng, self.act)
        elif kind == "rest":
            info["rest_heal"] = self.rest_heal_amount()
        return info

    # -- 幕 / 模式 -------------------------------------------------------
    def act_pool(self) -> int:
        """当前该用哪一幕的敌人池。

        主线：就是 act。
        无尽：act 一直往上加，但敌人池在 1..3 循环。
        """
        if self.mode != "endless":
            return max(1, min(3, int(self.act)))
        return ((max(1, int(self.act)) - 1) % 3) + 1

    def difficulty_scale(self) -> float:
        """额外的难度倍率（无尽模式每轮 +18%）。"""
        if self.mode != "endless":
            return 1.0
        return 1.0 + 0.18 * max(0, int(self.loop))

    def max_act(self) -> int:
        """主线只有 3 幕；无尽没有上限。"""
        return 3 if self.mode != "endless" else 999

    # -- 剧情 -------------------------------------------------------------
    def take_story(self, trigger: str) -> Optional[dict]:
        """取一条该触发点的剧情（没看过才给）。返回给 UI 的 dict。"""
        try:
            b = STORY.next_beat(trigger, int(self.act), self.story_seen)
        except Exception:
            return None
        if b is None:
            return None
        self.story_seen.add(b.id)
        self.pending_story = {
            "id": b.id, "title": b.title,
            "lines": list(b.lines),
            "choices": [{"label": c.label, "desc": c.desc} for c in b.choices],
            "act": b.act, "key": b.key,
        }
        return self.pending_story

    def take_vignette(self) -> Optional[dict]:
        """取一段没看过的小人物特写（无尽/主线都有）。"""
        try:
            v = STORY.random_vignette(self.rng, self.story_seen)
        except Exception:
            return None
        if v is None:
            return None
        self.story_seen.add(v.id)
        self.pending_story = {
            "id": v.id, "title": v.title,
            "lines": list(v.lines),
            "choices": [{"label": c.label, "desc": c.desc} for c in v.choices],
            "act": v.act, "key": False,
        }
        return self.pending_story

    def apply_story_choice(self, index: int) -> str:
        """执行剧情的第 index 个选择，返回结果文本。"""
        p = self.pending_story or {}
        self.pending_story = None
        try:
            b = None
            for beats in STORY.MAIN_STORY.values():
                for x in beats:
                    if x.id == p.get("id"):
                        b = x; break
                if b: break
            if b is None:
                for x in STORY.VIGNETTES:
                    if x.id == p.get("id"):
                        b = x; break
            if b is None:
                return ""
            i = max(0, min(len(b.choices) - 1, int(index)))
            if not b.choices:
                return ""
            ch = b.choices[i]
            if ch.effect is None:
                return ""
            return str(ch.effect(self) or "")
        except Exception:
            return ""

    def roll_encounter(self, kind: str) -> dict:
        pool = E.ENCOUNTERS.get(self.act_pool(), {}).get(kind) or []
        if not pool:
            pool = E.ENCOUNTERS.get(1, {}).get("normal") or []
        if not pool:
            return {"kind": kind, "enemies": ["deep_crab"]}
        pick = self.rng.choice(pool)
        ids = pick.get("enemies", []) if isinstance(pick, dict) else list(pick)
        return {"kind": kind, "enemies": list(ids)}

    def is_boss_node(self) -> bool:
        n = self.node_by_id(self.current_node) if self.current_node is not None else None
        return bool(n and n.kind == "boss")

    # -- 资源 -------------------------------------------------------------
    def rest_heal_amount(self) -> int:
        par = ascension_params(self.ascension)
        return max(1, int(self.max_hp * float(par.get("rest_heal", 0.3))))

    def heal(self, n: int) -> None:
        self.hp = min(self.max_hp, self.hp + max(0, int(n)))

    def add_gold(self, n: int) -> None:
        self.gold = max(0, self.gold + int(n))

    # -- 牌组 -------------------------------------------------------------
    def add_card(self, def_id, upgraded: int = 0) -> None:
        try:
            self.deck.append(C.make_card(def_id, upgraded=upgraded))
        except Exception:
            pass

    def remove_card(self, uid) -> bool:
        for i, c in enumerate(self.deck):
            if c.uid == uid:
                del self.deck[i]
                self.remove_count += 1
                return True
        return False

    def upgrade_card(self, uid) -> bool:
        for c in self.deck:
            if c.uid == uid and c.upgraded < 1 and c.is_upgradable:
                c.upgraded = 1
                return True
        return False

    def add_relic(self, relic_id) -> None:
        if relic_id and relic_id not in self.relics:
            self.relics.append(relic_id)

    def add_potion(self, pid) -> None:
        if pid and len(self.potions) < 3:
            self.potions.append(pid)

    def upgradable_cards(self) -> List[C.CardInstance]:
        return [c for c in self.deck if c.is_upgradable and c.upgraded < 1]

    def offer_card_rewards(self, n=3, rng=None, rarity_boost: float = 0.0) -> List[C.CardDef]:
        rng = rng or self.rng
        out: List[C.CardDef] = []
        seen = set()
        for _ in range(max(0, int(n))):
            for _try in range(24):
                r = rng.random() - rarity_boost
                if r < 0.58:
                    rarity = C.RARITY_COMMON
                elif r < 0.90:
                    rarity = C.RARITY_UNCOMMON
                else:
                    rarity = C.RARITY_RARE
                pool = C.cards_by_rarity(rarity)
                pool = [c for c in pool if c.id not in seen
                        and c.type not in ("status", "curse")]
                if pool:
                    pick = rng.choice(pool)
                    seen.add(pick.id)
                    out.append(pick)
                    break
        return out

    def offer_relic_rewards(self, n=1, rng=None) -> List[str]:
        rng = rng or self.rng
        owned = set(self.relics)
        pool = [r for r in R.RELIC_DB.values()
                if r.id not in owned and r.rarity not in ("starter", "boss")]
        rng.shuffle(pool)
        return [r.id for r in pool[:max(0, int(n))]]

    # -- 战斗结算 ---------------------------------------------------------
    def finish_battle(self, result: str, battle=None) -> None:
        if battle is not None:
            st = self.stats
            st["cards_played"] = st.get("cards_played", 0) + getattr(battle, "cards_played_total", 0)
            st["turns"] = st.get("turns", 0) + getattr(battle, "turn", 0)
            if battle.player is not None:
                self.hp = max(0, int(battle.player.hp))
            self.add_gold(max(0, int(getattr(battle, "gold_gain", 0))))
            n = self.node_by_id(self.current_node) if self.current_node is not None else None
            if result == "won":
                if n and n.kind == "elite":
                    st["elites_killed"] = st.get("elites_killed", 0) + 1
                if n and n.kind == "boss":
                    st["bosses_killed"] = st.get("bosses_killed", 0) + 1
                st["kills"] = st.get("kills", 0) + 1
        if result == "won":
            self.score += 10 + self.floor * 2
        else:
            self.score += self.floor * 2
        # 进入下一幕
        if result == "won" and self.is_boss_node():
            self.advance_act()

    def advance_act(self) -> None:
        """打完一幕的要塞后推进。

        主线：1 -> 2 -> 3 -> 4（4 = 主线通关，UI 走结局流程）
        无尽：1 -> 2 -> 3 -> 1 -> 2 -> ...，每循环一轮 ``loop + 1`` 加难度
        """
        if self.mode == "endless":
            nxt = int(self.act) + 1
            if nxt > 3:
                nxt = 1
                self.loop = int(self.loop) + 1
                self.score += 1000 + self.max_hp * 5
            self.act = nxt
            self.floor = 0
            self.current_node = None
            self.map_nodes = MapGenerator(self.rng, self.act).generate()
            return
        if self.act < 3:
            self.act += 1
            self.floor = 0
            self.current_node = None
            self.map_nodes = MapGenerator(self.rng, self.act).generate()
        else:
            # 主线三幕全部打完 —— 标记通关（结局由 UI 播放）
            self.act = 4
            self.story_cleared = True
            self.score += 2000 + self.max_hp * 5

    def final_score(self) -> int:
        s = self.score + self.gold // 2 + self.hp * 3 + len(self.relics) * 15
        s += self.ascension * 100
        return int(s)

    # -- 存档 -------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "seed": self.seed,
            "act": self.act, "floor": self.floor, "gold": self.gold,
            "hp": self.hp, "max_hp": self.max_hp,
            "deck": [c.to_dict() for c in self.deck],
            "relics": list(self.relics), "potions": list(self.potions),
            "current_node": self.current_node,
            "ascension": self.ascension, "score": self.score,
            "commander": str(getattr(self, "commander", "") or ""),
            "mode": str(getattr(self, "mode", "story") or "story"),
            "story_seen": sorted(getattr(self, "story_seen", set()) or set()),
            "loop": int(getattr(self, "loop", 0) or 0),
            "story_cleared": bool(getattr(self, "story_cleared", False)),
            "run_start_time": self.run_start_time,
            "stats": dict(self.stats), "seen_events": list(self.seen_events),
            "remove_count": self.remove_count, "daily": self.daily,
            "map_nodes": [{"id": n.id, "row": n.row, "col": n.col, "kind": n.kind,
                           "edges": list(n.edges), "visited": n.visited}
                          for n in self.map_nodes],
            # rng 状态以便续玩时保持随机序列（完整 625 元组 + 位置索引）
            "rng_state": _serialize_rng(self.rng),
        }

    @staticmethod
    def from_dict(d: dict) -> "RunState":
        r = RunState()
        r.seed = int(d.get("seed", 0))
        r.rng = random.Random(r.seed)
        _restore_rng(r.rng, d.get("rng_state"))
        r.act = int(d.get("act", 1))
        r.floor = int(d.get("floor", 0))
        r.gold = int(d.get("gold", 0))
        r.hp = int(d.get("hp", 75))
        r.max_hp = int(d.get("max_hp", 75))
        r.deck = [C.CardInstance.from_dict(x) for x in d.get("deck", [])]
        r.relics = list(d.get("relics", []))
        r.potions = list(d.get("potions", []))
        r.current_node = d.get("current_node")
        r.ascension = int(d.get("ascension", 0))
        r.commander = str(d.get("commander", "") or "")
        r.mode = "endless" if d.get("mode") == "endless" else "story"
        r.story_seen = set(d.get("story_seen", []) or [])
        r.loop = int(d.get("loop", 0) or 0)
        r.story_cleared = bool(d.get("story_cleared", False))
        r.pending_story = None
        r.score = int(d.get("score", 0))
        r.run_start_time = float(d.get("run_start_time", time.time()))
        r.stats = dict(d.get("stats", {}))
        r.seen_events = list(d.get("seen_events", []))
        r.remove_count = int(d.get("remove_count", 0))
        r.daily = bool(d.get("daily", False))
        nodes = []
        for nd in d.get("map_nodes", []):
            nodes.append(MapNode(id=int(nd["id"]), row=int(nd["row"]),
                                 col=int(nd["col"]), kind=nd["kind"],
                                 edges=list(nd.get("edges", [])),
                                 visited=bool(nd.get("visited", False))))
        r.map_nodes = nodes
        return r


# --------------------------------------------------------------------------
# 元进度
# --------------------------------------------------------------------------
class MetaProgress:
    def __init__(self):
        self.ascension_unlocked = 0
        self.total_runs = 0
        self.wins = 0
        self.best_score = 0
        self.best_ascension_win = -1
        self.streak = 0
        self.best_streak = 0
        self.seen_cards: set = set()
        self.seen_relics: set = set()
        self.seen_enemies: set = set()
        self.achievements: Dict[str, bool] = {}
        self.leaderboard: List[dict] = []
        self.unlocked_cards: set = set()
        self.unlocked_relics: set = set()
        self.total_playtime = 0.0
        self.daily_done: List[str] = []
        #: 主线是否通关过（通关后解锁无尽模式）
        self.story_done = False
        #: 主线通关次数
        self.story_wins = 0
        #: 跨局记住的小人物特写（不重复播）
        self.seen_vignettes: set = set()
        #: 跨局记住的主线剧情 id
        self.seen_story: set = set()

    # -- 读写 -------------------------------------------------------------
    @classmethod
    def load(cls, path: str = META_PATH) -> "MetaProgress":
        m = cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return m
        try:
            m.ascension_unlocked = int(d.get("ascension_unlocked", 0))
            m.total_runs = int(d.get("total_runs", 0))
            m.wins = int(d.get("wins", 0))
            m.best_score = int(d.get("best_score", 0))
            m.best_ascension_win = int(d.get("best_ascension_win", -1))
            m.streak = int(d.get("streak", 0))
            m.best_streak = int(d.get("best_streak", 0))
            m.seen_cards = set(d.get("seen_cards", []))
            m.seen_relics = set(d.get("seen_relics", []))
            m.seen_enemies = set(d.get("seen_enemies", []))
            m.achievements = dict(d.get("achievements", {}))
            m.leaderboard = list(d.get("leaderboard", []))
            m.unlocked_cards = set(d.get("unlocked_cards", []))
            m.unlocked_relics = set(d.get("unlocked_relics", []))
            m.total_playtime = float(d.get("total_playtime", 0.0))
            m.daily_done = list(d.get("daily_done", []))
            m.story_done = bool(d.get("story_done", False))
            m.story_wins = int(d.get("story_wins", 0))
            m.seen_vignettes = set(d.get("seen_vignettes", []))
            m.seen_story = set(d.get("seen_story", []))
        except Exception:
            pass
        return m

    def save(self, path: str = META_PATH) -> bool:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
            return True
        except Exception:
            return False

    def to_dict(self) -> dict:
        return {
            "ascension_unlocked": self.ascension_unlocked,
            "total_runs": self.total_runs, "wins": self.wins,
            "best_score": self.best_score,
            "best_ascension_win": self.best_ascension_win,
            "streak": self.streak, "best_streak": self.best_streak,
            "seen_cards": sorted(self.seen_cards),
            "seen_relics": sorted(self.seen_relics),
            "seen_enemies": sorted(self.seen_enemies),
            "achievements": dict(self.achievements),
            "leaderboard": list(self.leaderboard)[:10],
            "unlocked_cards": sorted(self.unlocked_cards),
            "unlocked_relics": sorted(self.unlocked_relics),
            "total_playtime": self.total_playtime,
            "daily_done": list(self.daily_done),
            "story_done": bool(self.story_done),
            "story_wins": int(self.story_wins),
            "seen_vignettes": sorted(self.seen_vignettes),
            "seen_story": sorted(self.seen_story),
        }

    # -- 解锁 -------------------------------------------------------------
    def unlock(self, key: str) -> bool:
        """解锁成就，返回是否是首次解锁。"""
        if key not in ACHIEVEMENTS:
            return False
        if self.achievements.get(key):
            return False
        self.achievements[key] = True
        # 全成就解锁 true_ending
        others = [k for k in ACHIEVEMENTS if k != "true_ending"]
        if key != "true_ending" and all(self.achievements.get(k) for k in others):
            self.achievements["true_ending"] = True
        return True

    def see_card(self, cid: str) -> None:
        if cid:
            self.seen_cards.add(cid)

    def see_relic(self, rid: str) -> None:
        if rid:
            self.seen_relics.add(rid)

    def see_enemy(self, eid: str) -> None:
        if eid:
            self.seen_enemies.add(eid)

    # -- 结算 -------------------------------------------------------------
    def record_run(self, run: RunState, won: bool) -> List[str]:
        """记录一局结束，返回本次新解锁的成就 key 列表。"""
        newly: List[str] = []
        self.total_runs += 1
        elapsed = max(0.0, time.time() - (run.run_start_time or time.time()))
        self.total_playtime += elapsed
        score = run.final_score()
        if score > self.best_score:
            self.best_score = score
        st = run.stats or {}
        if st.get("kills"):
            self._ach(newly, "first_blood")
        if st.get("bosses_killed"):
            self._ach(newly, "boss_slayer")
        if run.act >= 2:
            self._ach(newly, "act2")
        if run.act >= 3:
            self._ach(newly, "act3")
        if len(run.deck) >= 40:
            self._ach(newly, "deck_fat")
        if run.gold >= 999:
            self._ach(newly, "rich")
        if len(run.relics) >= 10:
            self._ach(newly, "relic10")
        if len(run.relics) >= 20:
            self._ach(newly, "relic20")
        if st.get("elites_killed", 0) >= 5:
            self._ach(newly, "elite_hunter")
        if st.get("poison_applied", 0) >= 100:
            self._ach(newly, "poison_master")
        if st.get("minions_summoned", 0) >= 5:
            self._ach(newly, "summoner")
        if st.get("cards_exhausted", 0) >= 20:
            self._ach(newly, "exhaust_all")
        if len([c for c in run.deck if c.type == "curse"]) >= 5:
            self._ach(newly, "curse_bearer")
        if run.daily:
            self._ach(newly, "daily")
        if len(self.seen_cards) >= len(C.CARD_DB):
            self._ach(newly, "collector")
        if won:
            self.wins += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self._ach(newly, "first_win")
            if self.streak >= 3:
                self._ach(newly, "streak3")
            if len(run.deck) <= 15:
                self._ach(newly, "deck_thin")
            if elapsed <= 20 * 60:
                self._ach(newly, "speedrun")
            if run.ascension >= 5:
                self._ach(newly, "asc5")
            if run.ascension >= 10:
                self._ach(newly, "asc10")
            if run.ascension >= 20:
                self._ach(newly, "asc20")
            self.best_ascension_win = max(self.best_ascension_win, run.ascension)
            # 解锁下一档飞升
            if run.ascension >= self.ascension_unlocked and self.ascension_unlocked < 20:
                self.ascension_unlocked = min(20, run.ascension + 1)
        else:
            self.streak = 0
        self.leaderboard.append({
            "score": score, "act": run.act, "ascension": run.ascension,
            "win": bool(won), "deck": len(run.deck), "relics": len(run.relics),
            "date": time.strftime("%Y-%m-%d %H:%M"),
        })
        self.leaderboard.sort(key=lambda x: -x["score"])
        self.leaderboard = self.leaderboard[:10]
        if run.daily:
            key = time.strftime("%Y-%m-%d")
            if key not in self.daily_done:
                self.daily_done.append(key)
        return newly

    def _ach(self, acc: List[str], key: str) -> None:
        if self.unlock(key):
            acc.append(key)

    def progress_pct(self) -> float:
        total = len(ACHIEVEMENTS)
        got = sum(1 for k in ACHIEVEMENTS if self.achievements.get(k))
        return got / total if total else 0.0


# --------------------------------------------------------------------------
# 存档辅助
# --------------------------------------------------------------------------
def save_run(run: Optional[RunState], path: Optional[str] = None) -> bool:
    # 注意：path 不能写成默认参数 SAVE_PATH —— 那会在 import 时定死，
    # 之后改 run.SAVE_PATH（测试/打包会改）就失效了。
    if path is None:
        path = SAVE_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if run is None:
            if os.path.exists(path):
                os.remove(path)
            return True
        with open(path, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def load_run(path: Optional[str] = None) -> Optional[RunState]:
    if path is None:
        path = SAVE_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return RunState.from_dict(d)
    except Exception:
        return None


def has_save(path: Optional[str] = None) -> bool:
    if path is None:
        path = SAVE_PATH
    return os.path.exists(path)


def daily_seed(date_str: Optional[str] = None) -> int:
    """每日挑战的确定性种子。"""
    if date_str is None:
        date_str = time.strftime("%Y-%m-%d")
    h = 2166136261
    for ch in ("whale-" + date_str):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h % (2 ** 31 - 1)
