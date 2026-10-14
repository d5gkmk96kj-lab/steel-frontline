# 钢铁战线 · Steel Frontline — 架构契约 v1

> 本文件是**唯一**的模块接口契约。所有实现必须严格遵守。
> 纯 Python 3.9 + Tkinter 8.5 / PyQt6（可选），**零第三方依赖**，**零网络**。
>
> [English summary ↓](#english-summary) — 本文档正文为中文（内部契约），
> 英文只提供简明概览，供外部贡献者快速上手。

---

<a id="english-summary"></a>
## English Summary (for contributors)

This is the internal architecture contract. The full text below is in Chinese;
here is the short version.

**What it is** — a turn-based deck-building roguelike (Slay-the-Spire style),
solo vs. AI plus LAN 1v1. Python 3.9+, zero third-party dependencies for the
core and the Classic (Tkinter) UI; PyQt6 is optional for the Hi-Fi UI.

**Layering rule** — `core/` must never import `ui/` or `qt/`. All game logic
lives in `core/` and is UI-agnostic; both UIs drive the same engine and share
the same save file.

| Module | Responsibility |
|---|---|
| `core/cards.py` | 134 card definitions + upgrade rules |
| `core/relics.py` | 52 medals (relics) |
| `core/enemies.py` | 53 enemies + intent (AI) definitions |
| `core/events.py` | events, shops, treasure data |
| `core/engine.py` | `BattleState`: rules engine + enemy AI |
| `core/run.py` | `RunState`: map, floors, shops, scoring, saves |
| `core/versus.py` | 1v1 PvP engine (symmetric, no AI) |
| `core/deckbuild.py` | deck construction + validation |
| `core/netplay.py` | LAN transport (stdlib sockets only, JSON-line protocol) |
| `core/i18n.py` | Chinese/English string lookup |
| `core/cheats.py` | cheat-code registry |
| `core/audio.py` | music player (radio mode, pluggable backend) |
| `ui/` | Classic edition (Tkinter) |
| `qt/` | Hi-Fi edition (PyQt6) |

**Hard rules**

1. `core/` never imports UI code; UI never contains game rules.
2. No third-party runtime dependencies (PyQt6 is the single optional extra).
3. No network calls except `core/netplay.py`'s LAN sockets.
4. Public functions never raise on bad input — return `False`/a neutral value.
5. Randomness always goes through an injected `random.Random` instance, never
   the global `random` module (keeps runs reproducible by seed).
6. Player-facing strings must be translatable — add them to `locales/`.

**Where things are documented** — see the Chinese sections below for the exact
frozen interfaces, the theme/terminology directive, and the acceptance criteria.

---

## 0. 定位

单人卡牌构筑 Roguelike（Slay the Spire 式），回合制，本地 AI 人机对战。
一局 30–60 分钟，通关后解锁更高难度，可长期反复游玩。

## 1. 目录结构 / 写入范围（严禁越界）

```
whale-card-battle/
├── main.py                # [lead] 启动器 + 路由
├── core/                  # [core-sim]
│   ├── __init__.py
│   ├── cards.py           # 卡牌数据库 + 升级定义
│   ├── relics.py          # 遗物数据库
│   ├── enemies.py         # 敌人 + 意图(AI)定义
│   ├── events.py          # 事件/商店/宝箱数据
│   ├── engine.py          # BattleState + 规则引擎 + AI 出牌
│   └── run.py             # RunState：地图、层、商店、结算
├── ui/                    # [ui-render]
│   ├── __init__.py
│   ├── theme.py           # 配色、字体、圆角绘制工具
│   ├── widgets.py         # 可复用控件：CardView, Button, Bar
│   ├── battle_view.py     # 战斗界面
│   ├── map_view.py        # 地图界面
│   ├── screens.py         # 主菜单/牌组/遗物/结算/图鉴/设置
│   └── app.py             # App 主循环、界面路由、动画调度
├── data/                  # [lead] 运行时生成
│   ├── save.json
│   └── meta.json
├── tests/                 # [verifier]
├── assets/                # [ui-render] 生成的图标/贴图（纯程序生成 PNG，无版权）
└── README.md              # [lead]
```

**写入范围是排他的。** 只写自己名下的文件。

## 2. 全局约定

- **坐标系**：卡牌一律横屏。窗口 `1440x900`，最小 `1280x800`，可缩放。
- **随机**：所有随机必须走 `engine.rng` / `run.rng`（`random.Random` 实例）。禁止裸 `random.*`。
- **不可变数据**：`CardDef` / `RelicDef` / `EnemyDef` 用 `@dataclass(frozen=True)`，实例上只放静态数据。
  运行时状态（费用、格挡、buff）放在 `CardInstance` / `Combatant` 上。
- **无异常泄漏**：引擎任何公开方法不得抛异常给 UI。非法操作返回 `False` 或 `ActionResult(ok=False, reason=...)`。
- **UI 绝不直接改引擎内部字段**：只能调用引擎公开方法。

## 3. `core/cards.py`

```python
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Dict, Any

# 稀有度
RARITY_BASIC, RARITY_COMMON, RARITY_UNCOMMON, RARITY_RARE = "basic","common","uncommon","rare"

# 职业/流派标签（用于构建 build）
ARCH_ATTACK  = "attack"    # 强攻：高伤、力量
ARCH_BLOCK   = "block"     # 铁壁：护甲、荆棘
ARCH_POISON  = "poison"    # 蚀骨：中毒、减益
ARCH_ENERGY  = "energy"    # 潮汐：能量、抽牌、连锁
ARCH_SUMMON  = "summon"    # 唤灵：召唤物、持续输出

@dataclass(frozen=True)
class CardDef:
    id: str                 # 唯一 snake_case
    name: str               # 中文名
    cost: int               # -1 表示 X 费
    type: str               # "attack" | "skill" | "power" | "status" | "curse"
    rarity: str
    arch: str               # ARCH_*
    text: str               # 描述，用 {damage} {block} 等占位
    target: str             # "enemy" | "self" | "all_enemies" | "none"
    # 效果：fn(ctx) -> None，ctx 为 CardContext
    effect: Optional[Callable[[Any], None]] = None
    exhaust: bool = False           # 消耗
    ethereal: bool = False          # 虚无：回合结束未打出则消耗
    innate: bool = False            # 固有：起手必在手牌
    retain: bool = False            # 保留：回合结束不弃
    upgrade: Optional[dict] = None  # 升级后覆盖的字段，如 {"cost":0,"damage":12}
    damage: int = 0                 # 基础伤害（供 UI 与升级计算）
    block: int = 0
    magic: int = 0                  # 通用数值槽（中毒层数等）
    magic2: int = 0
    hits: int = 1                   # 攻击段数
    keywords: tuple = ()            # 关键词，用于图鉴筛选

@dataclass
class CardInstance:
    """一张实际持有的牌。"""
    uid: int
    def_id: str
    upgraded: int = 0               # 0 或 1（1=升级）
    cost_override: Optional[int] = None   # 本场战斗内的临时改费（如被施加的减费）
    # 便捷只读属性：
    #   .defn -> CardDef        (从 CARD_DB 取，已应用升级覆盖)
    #   .name, .cost, .text, .type, .rarity  -> 转发到 .defn
    def to_dict(self) -> dict: ...
    @staticmethod
    def from_dict(d: dict) -> "CardInstance": ...

CARD_DB: Dict[str, CardDef]                 # 全部卡牌
STARTER_DECK: List[str]                     # 初始卡组 id 列表（10 张）
def make_card(def_id: str, upgraded: int = 0, uid: Optional[int] = None) -> CardInstance
def all_cards() -> List[CardDef]
def cards_by_arch(arch: str) -> List[CardDef]
def random_card_pool(rng: random.Random, rarity: Optional[str] = None) -> List[CardDef]
```

### 卡牌数量要求（硬性）
- 总数 **≥ 90 张**：attack ≥ 38，skill ≥ 34，power ≥ 12，status/curse ≥ 6
- 稀有度分布：common ≈ 40，uncommon ≈ 35，rare ≈ 15（basic 为初始牌）
- 每个 `ARCH_*` 至少 14 张，且各流派有 **明确的机制钩子**（见下）

### 流派机制钩子（必须实现，写在 `text` 与 `effect` 里）
- `ARCH_ATTACK` — **力量(strength)**：每层使攻击 +1 伤害；`易伤(vulnerable)` 目标受伤 +50%
- `ARCH_BLOCK` — **格挡(block)** / **荆棘(thorns)**：受击反弹；`金属化(metallicize)` 回合末获得格挡
- `ARCH_POISON` — **中毒(poison)**：回合开始按层数掉血后 -1；`虚弱(weak)` 目标造成伤害 -25%
- `ARCH_ENERGY` — **能量**：额外费用、抽牌、`连锁`（本回合每打出一张牌，下张 +N 伤害）；`神器(artifact)`
- `ARCH_SUMMON` — **召唤物(minion)**：独立行动条，回合末自动攻击/格挡；`仪式(ritual)` 每回合叠力量

## 4. `core/relics.py`

```python
@dataclass(frozen=True)
class RelicDef:
    id: str
    name: str
    rarity: str            # "starter"|"common"|"uncommon"|"rare"|"boss"|"shop"
    text: str
    trigger: str           # 见下
    counter: int = -1      # -1 表示不计数显示
    # 触发钩子在 engine 中通过 trigger 字符串分发
TRIGGER_BATTLE_START   = "battle_start"
TRIGGER_TURN_START     = "turn_start"
TRIGGER_TURN_END       = "turn_end"
TRIGGER_ON_ATTACK      = "on_attack"      # 攻击牌造成伤害后
TRIGGER_ON_DAMAGE_TAKEN= "on_damage_taken"
TRIGGER_ON_CARD_PLAYED = "on_card_played"
TRIGGER_ON_KILL        = "on_kill"
TRIGGER_ON_REST        = "on_rest"
TRIGGER_PASSIVE        = "passive"        # 持续生效，engine 主动查询
TRIGGER_ON_PICKUP      = "on_pickup"      # 拾取瞬间
TRIGGER_ON_SHOP        = "on_shop"

RELIC_DB: Dict[str, RelicDef]     # ≥ 45 个
STARTER_RELIC: str                # "broken_compass" 之类
```

## 5. `core/enemies.py`

```python
@dataclass(frozen=True)
class MoveDef:
    id: str
    name: str                 # 显示名，如 "撕咬"
    intent: str               # "attack"|"attack_debuff"|"attack_defend"|"defend"|"buff"|"debuff"|"unknown"|"sleep"
    damage: int = 0           # 每段基础伤害
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

ENEMY_DB: Dict[str, EnemyDef]   # ≥ 34 个：act1 普通12 精英3 boss1；act2/act3 类推
ENCOUNTERS: Dict[int, dict]     # {act: {"normal":[...组合...], "elite":[...], "boss":[...]}}
```

**BOSS 必须 ≥ 3 个**，各 act 一个，且有独特机制（多阶段 / 召唤 / 专属 debuff）。

## 6. `core/engine.py` — 战斗引擎（最关键）

```python
@dataclass
class Combatant:
    """玩家或敌人的战斗态。"""
    is_player: bool
    name: str
    hp: int
    max_hp: int
    block: int = 0
    energy: int = 0
    max_energy: int = 3
    buffs: Dict[str, int] = field(default_factory=dict)  # 见 BUFF_*
    # 玩家专属
    hand: List[CardInstance] = ...
    draw_pile: List[CardInstance] = ...
    discard_pile: List[CardInstance] = ...
    exhaust_pile: List[CardInstance] = ...
    relics: List[str] = ...
    powers: Dict[str, int] = ...     # 能力牌持续效果
    minions: List["Minion"] = ...
    def alive(self) -> bool: ...

@dataclass
class Minion:
    name: str; hp: int; max_hp: int; attack: int; block: int

# Buff 常量（统一用这些字符串键）
BUFF_STRENGTH="strength"; BUFF_DEXTERITY="dexterity"; BUFF_VULNERABLE="vulnerable"
BUFF_WEAK="weak"; BUFF_FRAIL="frail"; BUFF_POISON="poison"; BUFF_THORNS="thorns"
BUFF_METALLICIZE="metallicize"; BUFF_RITUAL="ritual"; BUFF_ARTIFACT="artifact"
BUFF_PLATED_ARMOR="plated_armor"; BUFF_REGENERATE="regenerate"; BUFF_INTANGIBLE="intangible"
BUFF_STRENGTH_DOWN="strength_down"; BUFF_BARRIER="barrier"   # barrier=回合末不清空的格挡
BUFF_CHAIN="chain"; BUFF_ENVENOM="envenom"; BUFF_ACCURACY="accuracy"

@dataclass
class CardContext:
    """传给 CardDef.effect 的上下文。"""
    battle: "BattleState"
    source: Combatant          # 打出者
    target: Optional[Combatant]
    card: CardInstance
    def deal_damage(self, amount, target=None, hits=1, kind="attack") -> int
    def gain_block(self, amount, target=None) -> int
    def apply_buff(self, key, amount, target=None) -> None
    def draw(self, n) -> None
    def gain_energy(self, n) -> None
    def add_card_to_hand(self, def_id, upgraded=0, n=1, temp=True) -> None
    def add_card_to_draw(self, def_id, n=1) -> None
    def heal(self, n) -> None
    def lose_hp(self, n) -> None
    def summon(self, name, hp, attack) -> None
    def exhaust_random(self, n) -> None
    def rng(self) -> random.Random
    def enemies(self) -> List[Combatant]
    def alive_enemies(self) -> List[Combatant]
    def cards_played_this_turn(self) -> int

class BattleState:
    def __init__(self, run, enemies: List[Combatant], rng: random.Random): ...
    player: Combatant
    enemies: List[Combatant]
    turn: int
    phase: str     # "player"|"enemy"|"won"|"lost"
    log: List[str]

    def start_battle(self) -> None
    def play_card(self, card: CardInstance, target: Optional[Combatant]) -> bool
    def can_play(self, card: CardInstance) -> bool
    def end_turn(self) -> None
    def enemy_step(self) -> bool
        """执行**下一个**敌人行动，返回 True 表示还有敌人待行动。
        UI 每 400ms 调一次以播放动画。"""
    def current_enemy_intent(self, enemy) -> Optional[MoveDef]
    def alive(self) -> bool
    def result(self) -> str     # "ongoing"|"won"|"lost"
    def snapshot(self) -> dict  # 供 UI 渲染的纯数据快照（避免 UI 触碰内部对象）
```

**AI 行为要求**（`enemy_step` 内）：
1. 意图在**上一回合结束时**就已确定并展示（`current_enemy_intent` 可查）。
2. 精英/BOSS 的 AI 要**读局势**：低血时优先格挡/回血、玩家格挡高时改用 debuff、
   有召唤位时先召唤、满足条件时进入狂暴阶段。绝不是纯随机。
3. 禁止同一招连续使用 3 次。

## 7. `core/run.py` — 长期进度

```python
@dataclass
class MapNode:
    id: int; row: int; col: int; kind: str
    # kind: "battle"|"elite"|"event"|"shop"|"rest"|"treasure"|"boss"
    edges: List[int]
    visited: bool = False

@dataclass
class RunState:
    rng: random.Random
    act: int                    # 1..3
    floor: int
    gold: int
    hp: int; max_hp: int
    deck: List[CardInstance]
    relics: List[str]
    map_nodes: List[MapNode]
    current_node: Optional[int]
    potions: List[str]
    ascension: int              # 0..20 难度等级
    score: int
    seed: int
    # 方法
    def new_run(self, seed=None, ascension=0, character="whale") -> None
    def reachable_nodes(self) -> List[MapNode]
    def move_to(self, node_id) -> dict      # 返回该节点要触发的遭遇描述
    def add_card(self, def_id, upgraded=0) -> None
    def remove_card(self, uid) -> bool
    def upgrade_card(self, uid) -> bool
    def heal(self, n) -> None
    def add_relic(self, relic_id) -> None
    def offer_card_rewards(self, n=3, rng=None) -> List[CardDef]
    def finish_battle(self, result: str, battle) -> None
    def to_dict(self) / from_dict(cls, d)   # 存档

# 元进度（跨局永久解锁）
class MetaProgress:
    def load(cls) / save(self)
    def unlock(self, key) -> None
    ascension_unlocked: int
    total_runs: int; wins: int; best_score: int
    seen_cards: set; seen_relics: set; seen_enemies: set
    achievements: Dict[str, bool]
```

**「玩很久」的保证（硬性要求）**：
1. **20 档飞升(Ascension)**：每档叠加真实难度（敌人血/伤、起始诅咒、精英加强、Boss 强化…）
2. **元进度解锁**：新卡牌/新遗物/新角色随游玩解锁
3. **成就系统 ≥ 25 个**
4. **图鉴**：卡牌/遗物/敌人全收集
5. **每日种子 & 自定义种子**
6. **计分与排行**（本地 Top 10）
7. **存档**：可中断续玩

## 8. UI 层契约

```python
# ui/app.py
class App(tk.Tk):
    def __init__(self): ...
    def show(self, screen_name: str, **kwargs) -> None
    # screen_name: "menu"|"map"|"battle"|"reward"|"shop"|"rest"|"event"|"deck"|"gameover"|"codex"|"settings"|"stats"
    run: Optional[RunState]
    battle: Optional[BattleState]
```

- **动画**：统一用 `self.after(ms, ...)` 调度，不得使用 `time.sleep` 阻塞主线程。
- **战斗动画序列**：出牌 → 伤害数字飘字 → 屏幕震动 → 敌人死亡淡出，全部异步。
- **悬浮提示**：卡牌/遗物/buff 悬停 250ms 显示 tooltip。
- 所有渲染基于 `BattleState.snapshot()`，UI 不得直接读 `Combatant` 对象做逻辑判断。

## 9. 测试要求 `tests/`
- `test_cards.py` — 卡牌数据完整性（数量、稀有度分布、每条 effect 可调用、占位符与数值一致）
- `test_engine.py` — 出牌/抽牌/能量/格挡/中毒/召唤/胜负判定
- `test_ai.py` — AI 不连续三连招；精英低血会格挡；BOSS 多阶段
- `test_run.py` — 随机种子可复现、存档往返、20 档飞升参数合法
- `test_balance.py` — **蒙特卡洛**：模拟 ≥ 2000 场自动对战，胜率落在合理区间
- `test_smoke_ui.py` — 无头创建 App 并切遍所有界面不崩溃
- 运行方式：`python3 -m unittest discover -s tests -v`（**不得依赖 pytest**）

---

# 附录 A — 冻结接口（Lead 裁定，所有模块必须遵守）

> ui-render 提出的接口歧义已在此裁定。**此附录优先级高于正文任何含糊之处。**

## A.1 战斗构造入口（core/engine.py 必须提供）

```python
def make_enemy_combatant(def_id: str, rng, ascension: int = 0, act: int = 1) -> Combatant
    """按 EnemyDef 生成敌人战斗态，血量在 hp_min..hp_max 间随机（飞升加成）。"""

def make_battle(run, encounter: dict) -> BattleState
    """encounter 形如 {"kind":"normal"|"elite"|"boss", "enemies":["enemy_id", ...]}
    UI 只调用这一个入口创建战斗。BattleState.__init__ 签名保持不变，但 UI 不直接用。"""
```

UI 只需调用 `core.engine.make_battle(run, encounter)`。
`run.move_to(node_id)` 返回的 dict 必须含 `{"kind": ..., "encounter": {...}}`，UI 直接把它喂给 `make_battle`。

## A.2 `BattleState.snapshot()` 精确 key（冻结）

```python
{
  "turn": int, "phase": "player"|"enemy"|"won"|"lost",
  "player": {
      "name":str, "hp":int, "max_hp":int, "block":int,
      "energy":int, "max_energy":int,
      "buffs": {buff_key: int},
      "minions": [{"name":str,"hp":int,"max_hp":int,"attack":int,"block":int}],
      "powers": {power_key: int},
  },
  "enemies": [{
      "idx":int, "name":str, "hp":int, "max_hp":int, "block":int,
      "buffs": {buff_key:int}, "alive":bool,
      "intent": {"id":str,"name":str,"intent":str,"damage":int,
                 "hits":int,"block":int,"text":str} | None,
      # damage 为**已计算好玩家实际会承受的伤害**（含力量/虚弱/易伤），UI 直接显示
  }],
  "hand": [{"uid":int,"def_id":str,"name":str,"cost":int,"type":str,
            "rarity":str,"arch":str,"text":str,"upgraded":int,"playable":bool}],
  "draw_count": int, "discard_count": int, "exhaust_count": int,
  "relics": [{"id":str,"name":str,"text":str,"rarity":str,"counter":int}],
  "log": [str],           # 最近 40 条
  "cards_played_this_turn": int,
}
```

**别名兜底**：`snapshot()["hand"]` 里额外冗余提供 `draw_pile_len`/`discard_pile_len`/`exhaust_pile_len`，
值与 draw_count/discard_count/exhaust_count 相同（兼容 ui-render 的别名映射）。

## A.3 `play_card` 参数（冻结）

```python
def play_card(self, card, target=None) -> bool
```
`card` 可以是 `CardInstance` **或 int uid**（引擎内部自行解析，UI 传哪个都行）。
非法操作返回 False 并写入 `self.log`，不抛异常。

## A.4 `core/events.py` 公开面（冻结）

```python
@dataclass(frozen=True)
class EventChoice:
    label: str            # 按钮文字
    desc: str             # 结果预告
    effect: Callable[[Any], str]   # fn(run) -> 结果叙述文本
    requires: Optional[Callable[[Any], bool]] = None   # 不满足则灰显

@dataclass(frozen=True)
class EventDef:
    id: str; name: str; act: int; text: str
    choices: tuple        # tuple[EventChoice, ...]
    art: str = ""

EVENT_DB: Dict[str, EventDef]           # ≥ 22 个
def random_event(rng, act: int, seen: set) -> EventDef

# 商店
SHOP_CARD_PRICE = {"common": 50, "uncommon": 75, "rare": 150}
SHOP_RELIC_PRICE = {"common": 150, "uncommon": 200, "rare": 280, "shop": 180}
SHOP_POTION_PRICE = 60
SHOP_REMOVE_PRICE_BASE = 75      # 每次删卡 +25
def build_shop_inventory(rng, act: int, ascension: int) -> dict
    # -> {"cards":[CardDef,...], "relics":[RelicDef,...], "potions":[str,...], "remove_price":int}

# 宝箱
TREASURE_TIERS = ("gold", "relic", "potion", "curse_relic")
def roll_treasure(rng, act: int) -> dict   # -> {"tier":str,"gold":int,"relic_id":str|None,...}
```

## A.5 `ui/theme.py` 必须导出的名字（冻结）

颜色/尺寸常量：`BG_DEEP, BG_DARK, PANEL, PANEL_LIGHT, BORDER, TEXT, TEXT_DIM, TEXT_MUTED,
GOLD, CYAN, GREEN, RED, PURPLE, ORANGE` + dict `COLORS`（name→hex）+
`RARITY_COLORS`（"basic"/"common"/"uncommon"/"rare"→hex）+ `TYPE_COLORS` + `ARCH_COLORS`
字体：`FONT_TITLE, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL, FONT_TINY, FONT_NUM`
尺寸：`CARD_W=168, CARD_H=236, CARD_RADIUS=12`
函数：`rgb(hex)->tuple`、`lerp_color(c1,c2,t)->hex`、`mix(bg,fg,alpha)->hex`、
`round_rect(canvas,x1,y1,x2,y2,r,**kw)`、`vgradient(canvas,x1,y1,x2,y2,c1,c2,steps=40)`、
`hgradient(...)`、`draw_text_center(canvas,x,y,text,**kw)`、`rarity_color(r)`、`type_color(t)`、`arch_color(a)`、
`font(size, bold=False)`、`get_font(family_size_bold_tuple)->tuple`

## A.6 战斗节奏协议（UI ↔ 引擎，冻结）

1. 玩家出牌/结束回合 → `engine.end_turn()` 内部只做「结算回合末 + 进入 enemy phase」，
   **不执行任何敌人行动**。
2. UI 之后每 400ms 调一次 `battle.enemy_step()`：
   - 返回 `True` 表示还有敌人待行动 → UI 继续调度
   - 返回 `False` 表示敌方回合结束、已自动开新玩家回合 → UI 停止调度并刷新
3. `battle.enemy_step()` 必须幂等安全：phase 不是 "enemy" 时直接返回 False。

---

# 附录 B — 题材变更令（Lead 裁定，最高优先级）

> **用户明确要求：保留玩法内核，彻底更换题材与美术风格。**
> 「不要鲸鱼之类的画风和主题」「卡牌和世界观换成战争的」「AI 对战内核可以」「总部血量也可以」

## B.0 立项变更

| 项 | 旧 | 新 |
|---|---|---|
| 游戏名 | 鲸牌战记 Whale Card Battle | **钢铁战线** Steel Frontline |
| 题材 | 深海 / 鲸鱼 / 海洋生物 | **二战装甲战争**（架空 1940s 欧洲战场） |
| 玩家身份 | 深海行者（鲸鱼） | **装甲军指挥官** |
| 敌人 | 深海生物 | **敌方装甲部队 / 步兵 / 空军 / 要塞** |
| 主基地 | 玩家自身血量 | **总部 HP（HQ）**，保持现有 hp 字段语义不变 |
| 视觉 | 青蓝深海渐变 + 气泡 | **硝烟褐 / 军绿 / 钢灰 + 弹壳金**，纸张磨损质感 |

**玩法内核（引擎、抽卡、能量、AI、遗物、地图、飞升、成就）全部保留，不改架构。**

## B.1 术语映射表（强制统一，所有模块遵守）

| 旧术语 | 新术语 |
|---|---|
| 能量 energy | **补给 Supply** |
| 格挡 block | **掩体 Cover** |
| 抽牌堆 / 弃牌堆 / 消耗堆 | **牌库 / 弃牌堆 / 移除区** |
| 力量 strength | **火力 Firepower** |
| 敏捷 dexterity | **机动 Mobility** |
| 易伤 vulnerable | **破甲 Exposed** |
| 虚弱 weak | **压制 Suppressed** |
| 脆弱 frail | **混乱 Disrupted** |
| 中毒 poison | **燃烧 Burning**（语义不变：回合开始掉血后 -1） |
| 荆棘 thorns | **铁丝网 Barbed Wire** |
| 金属化 metallicize | **工事 Fortify** |
| 镀甲 plated_armor | **装甲板 Armor Plate** |
| 神器 artifact | **干扰弹 Countermeasure** |
| 无实体 intangible | **烟幕 Smoke Screen** |
| 仪式 ritual | **增援 Reinforce** |
| 再生 regenerate | **战地医疗 Field Medic** |
| 屏障 barrier | **坚守 Hold Fast** |
| 连锁 chain | **连射 Burst** |
| 淬毒 envenom | **燃烧弹 Incendiary** |
| 精准 accuracy | **瞄准 Optics** |
| 召唤物 minion | **附属单位 Support Unit** |
| 力竭 strength_down | **弹药短缺 Ammo Shortage** |
| 卡牌类型 attack/skill/power | **攻击 / 战术 / 指令** |
| 稀有度 basic/common/uncommon/rare | **制式 / 常规 / 精锐 / 传奇** |
| 飞升 ascension | **战役难度 Campaign Level** |
| 遗物 relic | **勋章 / 装备 Decoration** |
| 地图 map | **战区推进图** |
| 商店 shop | **补给站** |
| 休息 rest | **战地医院** |
| 精英 elite | **精锐部队** |
| Boss | **要塞 / 王牌指挥官** |

> **重要**：**代码标识符（变量名/键名/函数名）一律不改**，只改**面向玩家的显示文本**。
> 即 `BUFF_POISON = "poison"` 这个**键名保留**，但 `BUFF_NAMES["poison"]` 的**显示名**改成「燃烧」。
> 引擎逻辑零改动，风险最低。

## B.2 美术方向（ui-theme 主导，ui-render 承接）

**配色（替换 theme.py 调色板，保留同名常量以免破坏调用方）**
- `BG_DEEP`  #12100D 硝烟黑褐
- `BG_DARK`  #1A1712
- `PANEL`     #24201A 沙盘/钢板
- `GOLD`      #C9A227 弹壳金（强调色，保留变量名）
- `CYAN`      #7A8B4A → 改为 **军绿强调** `#6B7F3A`
- `BLOOD/RED` #A8322D 战损红
- `TEXT`      #E8E2D4 泛黄纸白
- 新增：`STEEL=#5A6470`、`SMOKE=#3A3630`、`RUST=#8B5A2B`

**质感要求**
- 卡面：做旧纸张 / 铆接钢板，边缘磨损，四角螺丝或折角
- 背景：硝烟粒子（替换气泡）、远景地平线、铁丝网剪影、偶尔的曳光弹
- **删除所有鲸鱼/海洋元素**：鲸鱼立绘、气泡、波浪、海洋生物图标
- 新立绘方向：坦克剪影、士兵头盔、飞机、沙袋、地图桌
- 图标：程序化几何图形即可，但要用军事符号语汇（盾=掩体、爆裂=攻击、齿轮=指令）

**程序化绘制替换清单（ui/battle_view.py）**
| 旧 | 新 |
|---|---|
| `draw_whale()` 鲸鱼立绘 | `draw_tank()` 玩家坦克 / `draw_hq()` 总部碉堡 |
| `draw_bubbles()` 气泡粒子 | `draw_smoke()` 硝烟粒子 + `draw_tracer()` 曳光弹 |
| 海洋背景渐变 | 战场地平线 + 焦土渐变 |
| 海洋生物敌人立绘 | 敌方坦克/步兵/飞机/要塞剪影 |

## B.3 内容改写要求（core-data）

- `core/cards.py`：134 张卡的 `name` 与 `text` 全改为军事术语；**`id`、字段结构、数值、effect 逻辑一律不变**
- `core/enemies.py`：53 个敌人的 `name`/`desc`/`MoveDef.name` 改为军事单位；**id/moves/hp/ai 逻辑不变**
- `core/relics.py`：52 个遗物改名（勋章/装备）+ 文案
- `core/events.py`：31 个事件改为战场事件（遭遇战/补给抉择/俘虏/空袭）
- 流派名 `ARCH_*` 的**显示名**：attack=**突击**、block=**防御**、poison=**燃烧弹**、energy=**后勤**、summon=**支援**

**红线：不得改动任何数值、id、字段名、函数签名。只改中文字符串。**

## B.4 验收

1. 全代码库 `grep -i "鲸\|深海\|潮汐\|珊瑚\|气泡\|海洋"` 在**面向用户字符串中**应为 0 处
2. `python3 main.py --selftest` 仍全部通过（引擎不受题材影响）
3. 所有界面截图中无海洋元素
4. 测试套件保持全绿

---

# 附录 C — 验收口径澄清（Lead 裁定）

## C.1 海洋词残留的判据修正

**背景**：附录 B.4 写「全代码库 grep 海洋词应为 0 处」，这条**表述不准确**，已导致误报。

**正确判据**：只约束**面向玩家的显示字符串**，即：

| 必须为 0 | 允许保留 |
|---|---|
| `BUFF_NAMES` / `BUFF_DESCS` 的 **value** | dict **键名**（如 `"whale_song"`） |
| 卡牌 `name` / `text` | 变量名 / 常量名 / 类名 / 函数名 |
| 敌人 `name` / `MoveDef.name` / `MoveDef.text` | 参数名 |
| 遗物 `name` / `text` | — |
| 事件 `name` / `text` / `choice.label` | — |
| 难度档位名 / 成就名 / 称号 | — |
| 所有 UI label / 按钮文字 / tooltip | — |

理由：B.1 明确规定「**代码标识符一律不改，只改面向玩家的显示文本**」。
`whale_song`、`tidepool`、`abyssal_gate` 等 key **保留是正确的**，不算违规 —— 改动它们会破坏存档兼容性、测试断言与 UI 调用方。

## C.2 注释与 docstring

**注释、docstring、代码内 TODO** 中的海洋词汇**必须清除**。
理由：不影响玩家，但会误导后续维护者误以为项目是海洋题材。已全量清理。

## C.3 配色验收的客观判据

不依赖主观肉眼，用**可度量**的方式：

1. `ui/theme.py` 的 `BG_DEEP` 必须为暖色（`R >= B`），B.2 指定 `#12100D`
2. **实际渲染场景**中，暖色图元（`R >= B`）占比应 **> 90%**
   - 实测 `battle` 场景：1015 个着色图元中 **1004 个暖色 = 98.9%**
3. 复核命令：
```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from ui.app import App
from collections import Counter
app=App()
def go():
    app.start_new_run(seed=3); app.start_battle(); app.show('battle'); app.update_idletasks()
    c=app.canvas; fills=Counter()
    for it in c.find_all():
        try:
            f=c.itemcget(it,'fill')
            if f: fills[f.lower()]+=1
        except Exception: pass
    warm=sum(n for col,n in fills.items() if len(col)==7 and int(col[1:3],16)>=int(col[5:7],16))
    cool=sum(n for col,n in fills.items() if len(col)==7 and int(col[1:3],16)<int(col[5:7],16))
    print('warm %.1f%%' % (100*warm/max(1,warm+cool)))
    app.quit()
app.after(700,go); app.after(9000,app.quit); app.mainloop()
"
```

## C.4 视觉正确性必须由人眼确认

**任何自动化测试都不能证明「画风是军事风且好看」。** 测试只能证明：
- 界面不崩、`view` 非 None、图元数合理、无异常输出

因此交付前必须有**人工视觉确认**环节。已完成的确认方式：
- 从 Tk canvas 导出 PostScript 并栅格化 → 肉眼看到**绿色玩家坦克 + 红星旗 + 城市废墟天际线 + 探照灯光柱 + 铁丝网 + 拒马** ✅
- 直接读取 canvas 的 `text` 图元 → 确认文案为 `总部 / 补给 / 牌库 / 移除区 / 弃牌堆 / 结束回合` ✅
- 配色暖色占比度量 98.9% ✅
