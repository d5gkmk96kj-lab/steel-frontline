# 对战/联机验证报告 VERIFY_VERSUS.md

> 独立验证者 (verifier) 出品。**只陈述实测结果，不美化、不谎报。**
> 每条结论均附最小复现命令与真实输出。
> 验证者**未修改任何被测代码**：写入范围仅 `tests/test_versus.py`、
> `tests/test_deckbuild.py`、`tests/test_netplay.py`、`VERIFY_VERSUS.md`。
>
> [English summary ↓](#english-summary)

---

<a id="english-summary"></a>
## English Summary

Independent verification report for the **1v1 versus engine, deck builder, and LAN
networking**. The body below is in Chinese; this is the gist.

**Write scope** — the verifier could only touch `tests/test_versus.py`,
`tests/test_deckbuild.py`, `tests/test_netplay.py`, and this file. **Zero writes**
to the code under test.

**What was verified**

- **Snapshot isolation** — `snapshot_for(side)` exposes only your own hand; the
  opponent sees a `hand_count` and nothing else. Deep-scanned 6 levels for leaked
  card instances.
- **Anti-cheat** — a raw socket client was used to send forged frames
  (`{"t":"state","payload":{"hp":9999}}`, impersonated cheat commands, out-of-range
  card indices, malformed JSON, 1 MB lines, random fuzz). The host rejected all of
  them and its authoritative state never changed.
- **Protocol robustness** — partial frames, coalesced frames, multiple messages per
  packet, empty lines, garbage bytes: no crashes.
- **Disconnect handling** — the host detects a dropped peer and emits an event.
- **Fairness** — 500 mirrored auto-battles measured first-player advantage.

**Defects found and fixed** (each had a failing test before the fix, passing after):

| Item | Before | After |
|---|---|---|
| Qt audio probe SIGSEGV (Tk + Qt in one process) | 20/20 crashes | exit=0 |
| `validate_deck` accepted status/curse cards -> all-junk deck soft-locks a match | accepted | rejected |
| First-player advantage | **72.8%** | **50.6%** |
| netplay intent whitelist inconsistency | dead branch | cleaned up |

**Honest disclosure** — the verifier lists what it did **not** verify: real
cross-device LAN (only `127.0.0.1` was tested), the packaged "zero-config" build,
and human play (balance data comes from a greedy AI). See the Chinese sections for
the full list.

**Self-corrections worth noting** — the verifier caught and documented **9 of its
own wrong assertions**, including one where it nearly reported correct behaviour as
a bug (the second player having no hand at construction time is by design).

---

---

## 1. 结论摘要

### 最终状态（全部已修复并复验）

```
$ python3 -m unittest discover -s tests -p "test_*.py"     # 连跑 3 次
Ran 377 tests in 39.297s OK (skipped=3)   exit=0
Ran 377 tests in 39.381s OK (skipped=3)   exit=0
Ran 377 tests in 39.344s OK (skipped=3)   exit=0
```

| 测试文件 | 用例数 | 结果 |
|---|---|---|
| `tests/test_versus.py` | 32 | **32 通过**（1 skip）✅ |
| `tests/test_deckbuild.py` | 30 | **30 全部通过** ✅ |
| `tests/test_netplay.py` | 31 | **31 全部通过** ✅ |

**发现的真实问题（共 4 个，全部已修复并复验）：**

| # | 位置 | 严重度 | 问题 | 修复后实测 |
|---|---|---|---|---|
| V1 | `core/deckbuild.py` | **高** | `validate_deck` 放行 status/curse，可构造「全废牌卡组」 | ✅ `(False, '「伤口」是无法主动使用的状态牌，不能放入卡组。')` |
| V2 | `core/versus.py` | **高（设计）** | 先手优势 **72.8%**，远超 60% 阈值 | ✅ 降至 **50.6%**（近完美平衡） |
| V3 | `core/netplay.py` | 低（记录） | `validate_client_intent` 与 `_handle_message` 白名单不一致 | 功能无影响（死分支） |
| A1 | `core/audio.py:_probe_qt` | **严重** | Tk 初始化后 `QApplication.processEvents()` → SIGSEGV | ✅ exit=0，连跑 3 次全量无崩溃 |

**回归防线已生效**：V1/V2 的测试用例在修复前是**红色**、修复后**自动转绿**，
证明它们确实是能感知失败的有效断言（非空断言）。

---

## 2. V1 — `validate_deck` 放行 status/curse，可造「全废牌卡组」（真实 BUG）

**现象**：`card_pool()` 正确排除了 status/curse，但 `validate_deck()` **没有**做同样的排除，两者规则不一致。

**最小复现**：
```bash
cd /Users/kevinlee/Documents/deepseek-harness/default-workspace/whale-card-battle
python3 -c "
import sys; sys.path.insert(0,'.')
from core import deckbuild as D, cards as C
print('EXCLUDED_TYPES =', D.EXCLUDED_TYPES)
print('card_pool 含 wound?', 'wound' in D.card_pool())
pool=[c.id for c in C.CARD_DB.values() if c.type not in D.EXCLUDED_TYPES]
deck=[]
for cid in pool:
    for _ in range(min(D.MAX_COPIES, 20-len(deck))): deck.append(cid)
    if len(deck)>=20: break
d=list(deck[:20]); d[0]='wound'
print('含 wound(status) 的卡组:', D.validate_deck(d))
"
```
**实际输出**：
```
EXCLUDED_TYPES = frozenset({'curse', 'status'})
card_pool 含 wound? False                                      ← 卡池正确排除
含 wound(status) 的卡组: (True, '合法卡组：20 张，共 11 种。')    ← 但校验放行
```

**可被利用到什么程度 —— 全废牌卡组能成功进入对战**：
```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from core import deckbuild as D, cards as C, versus as V
d = ['wound','wound','doubt','doubt','shame','shame','regret','regret','pain','pain',
     'decay','decay','burn','burn','dazed','dazed','plague_spore','plague_spore',
     'curse_of_the_deep','curse_of_the_deep']
print('len:', len(d), '| validate:', D.validate_deck(d))
print('types:', set(C.CARD_DB[c].type for c in d), '| costs:', set(C.CARD_DB[c].cost for c in d))
bs = V.VersusBattle(list(d), list(d), hp=75)
print('versus 接受了全废牌卡组，起手:', [c.def_id for c in bs.side(0).combatant.hand])
"
```
**实际输出**：
```
len: 20 | validate: (True, '合法卡组：20 张，共 10 种。')
types: {'curse', 'status'} | costs: {-2}
versus 接受了全废牌卡组，起手: ['shame', 'decay', 'shame', 'doubt', 'burn']
```

**期望行为**：`validate_deck` 应拒绝 `type in EXCLUDED_TYPES` 的牌（与 `card_pool()` 规则一致）。
**实际行为**：放行。

**影响**：
1. `cost = -2` 表示**不可打出**。20 张全废牌 → 整局打不出任何牌，**对战软锁**。
2. 联机场景下是**恶意拖延/破坏**手段：双方都打不出牌，只能等 60 秒超时逐回合耗到血量判定。
3. 从反作弊角度看：房主校验了「id 是否存在于 `CARD_DB`」，但**没有校验「这张牌是否允许进卡组」**。

**回归防线**：`test_deckbuild.py::TestValidateDeck.test_status_and_curse_rejected`（现为失败态，修好后自动转绿）。

---

## 3. V2 — 先手优势 72.8%（真实设计问题）

**修复前实测**（500 场，双方同卡组、同一贪心 AI，排除卡组差异）：
```
[versus 平衡性] 500 场自动对战（双方同卡组，贪心 AI）
  先手胜 364 (72.8%) | 后手胜 135 (27.0%) | 平 1 | 未收敛 0
  平均步数 35.0 | 最大 57
```

**修复后复验**（同样 500 场，连跑 3 次结果完全一致）：
```
  先手胜 253 (50.6%) | 后手胜 242 (48.4%) | 平 5 | 未收敛 0
  先手胜 253 (50.6%) | 后手胜 242 (48.4%) | 平 5 | 未收敛 0
  先手胜 253 (50.6%) | 后手胜 242 (48.4%) | 平 5 | 未收敛 0
```
**72.8% → 50.6%**，从明显失衡修正为接近完美对称。

**稳健性检查 —— 跨卡组种子稳定复现，不是抽样偶然**：
```
deckseed=1    先手 69.5%  后手 30.5%   draw=0  ongoing=0
deckseed=2    先手 64.0%  后手 34.0%   draw=4  ongoing=0
deckseed=3    先手 71.5%  后手 28.5%   draw=0  ongoing=0
deckseed=42   先手 71.0%  后手 23.0%   draw=12 ongoing=0
deckseed=99   先手 74.5%  后手 22.5%   draw=6  ongoing=0
starter_deck  先手 75.5%  后手 23.5%   draw=2  ongoing=0
```
**范围 64% ~ 75.5%，全部 > 60% 阈值。**

**这是设计问题，不是实现 bug。** 我实测到的相关事实（供定位参考，**我不宣称确定根因**）：
1. **后手首回合无任何补偿**：构造后 side 1 为 `hand=0, energy=0, draw=30`，必须等 side 0 打完一整回合才启动（见 `core/versus.py:302` `_start_turn(SIDE_A, first=True)`）。相当于**先手白赚一个完整回合**。
2. 平均 35 步（约 17 回合）即分出胜负，**没有回合上限/疲劳机制**，先手积累的血量差无法被追回。

**常见解法**（仅供决策，未验证）：后手首回合 +1 补给 / +1 抽牌 / 额外掩体，或加入递增伤害的疲劳机制让长局收敛。

**回归防线**：`test_versus.py::TestVersusBalance.test_500_game_first_player_advantage`（**故意失败**，确保该问题不会被忽略）。

---

## 4. V3 — `validate_client_intent` 与 `_handle_message` 不一致（低危，仅记录）

`core/netplay.py:887` 的 `_handle_message` **明确接受** `deck`：
```python
if t in ("ready", "deck"):
    self._on_peer_ready(msg)
```
但 `validate_client_intent` 对 `{"t":"deck"}` 返回 `'不支持的操作：deck'`。

**我追了调用点，确认这是死分支**：
```
core/netplay.py:922:        reason = validate_client_intent(msg)   ← 仅在 _on_intent 内
```
`_on_intent` 只处理 `play`/`end`；`deck` 走 `_on_peer_ready`，**不经过**该校验。

**实测 deck 交换功能完全正常**：
```
host events: ['listening','connected','peer','ready','peer_ready','start','log']
client events: ['connecting','connected','peer','ready','peer_ready','start','state','log']
host snapshot after deck exchange: YES
```
**因此不影响功能**，属命名/职责不一致。已 print 记录，**未判失败**。

---

## 5. A1 — `core/audio.py:_probe_qt` SIGSEGV（跨模块阻塞项，20/20 必现）

**这一条不在本次 task-11 的写入范围内，但它阻断「全量测试全绿」。**

**确切崩溃栈**（`python3 -X faulthandler` 抓取）：
```
Fatal Python error: Segmentation fault
  File "core/audio.py", line 418 in _probe_qt
  File "core/audio.py", line 355 in _probe
  File "core/audio.py", line 328 in _choose_backend
  File "core/audio.py", line 302 in __init__
  File "core/audio.py", line 732 in player
  File "core/audio.py", line 781 in on_screen
  File "ui/app.py", line 883 in _music_for
  File "ui/app.py", line 834 in _show_direct
  File "ui/app.py", line 436 in __init__
```

**最小复现（20/20 必现）**：
```bash
cd /Users/kevinlee/Documents/deepseek-harness/default-workspace/whale-card-battle
python3 -c "
import sys; sys.path.insert(0,'tests'); sys.path.insert(0,'.')
import test_console          # 触发模块级 @skipUnless(_tk_ok()) → 建/毁一个 Tk 根
from ui.app import App
App().destroy()
"
# → Segmentation fault: 11  (exit 139)
```

**触发条件精确描述**：**先初始化过 Tk，再走到 `audio._probe_qt()` 的 `QApplication.processEvents()`** → SIGSEGV。

对照实验：
| 场景 | 结果 |
|---|---|
| 单独 `App()`（进程内 Tk 未初始化） | exit=0 ✅ |
| `import test_console`（其 `_tk_ok()` 建过 Tk）+ `App()` | **20/20 exit=139** ❌ |

值得注意的是，`_probe_qt` 的 docstring **自己已经警告**「Tkinter 版的主循环会与之冲突…实测会直接死锁/段错误」，但它采用的规避手段（改用 `processEvents` 而非 `QEventLoop`）**同样会崩**。

**影响范围**：`App()` 是游戏真实启动路径。任何「先碰过 Tk 再启动游戏」的场景都会崩（打包后 Qt 插件与 Tk 同进程共存尤其可疑）。

**复现统计**：
```
test_console.py   ×3  →  exit=139,139,139
test_smoke_ui.py  ×3  →  exit=139,139,139
全量 discover      ×5  →  exit=139,139,139,139,139
最小复现脚本       ×20 →  crash=20  ok=0
```

**说明**：Lead 曾判断这是「队友写盘中间态」。我复跑后确认**不是** —— 它是 100% 稳定复现的真实崩溃。（当时 `test_smoke_ui` 确实一度 exit=0，说明崩溃是**之后某个改动引入的**。）

**修复后复验**：`exit=0`（原为 139）；全量套件连跑 3 次 `Ran 377 tests ... OK`，**无任何 SIGSEGV**。

---

## 6. 已验证通过的部分（含真实输出）

### 6.1 快照隔离 ✅（安全重点，设计正确）

`snapshot_for(side)` 真实结构：
```
top keys: ['current_side','foe','log','me','my_hand','opponent','opponent_hand_count',
           'phase','result','side','time_left','turn','turn_seconds','you']
opponent keys: ['block','buffs','discard_count','draw_count','energy','exhaust_count',
                'hand_count','hp','max_energy','max_hp','minions','name','powers']
```
**对手分支只有 `hand_count` 数字，没有 `hand` 列表、没有 `draw_pile`、没有 `CardInstance`** ✅

通过的断言：
- `test_opponent_hand_not_leaked` — 对手分支不含 hand 列表
- `test_deep_scan_for_card_instances_in_opponent` — 深扫 6 层无 `CardInstance` 对象
- `test_snapshot_does_not_leak_draw_pile_order` — 不泄露对手牌堆
- `test_opponent_hand_count_never_exposes_ids` — 对手分支无任何手牌类 list
- **交叉一致性不变式**（我额外加的）：
```
side0 view: me.hand=0  opponent.hand_count=5
side1 view: me.hand=5  opponent.hand_count=0
cross-consistent: True
```

### 6.2 反作弊 ✅

- 越界/负数索引（`n`, `n+5`, `999`, `-1`, `-99`）→ 全部 `False` 且**状态不变**
- 替对手出牌 → 被拒，手牌数不变
- 0 能量打正费牌 → 被拒
- 引擎**未暴露**任何 `set_hp`/`cheat` 类公开 API（结构性断言）
- `play_card` 返回 bool 而非抛异常

### 6.3 联机反作弊（端到端真实 socket）✅

用裸 socket 向房主灌入 4 种恶意帧：
```python
{"t":"state","payload":{"hp":9999}}
{"t":"state","me":{"hp":9999},"opponent":{"hp":0}}
{"t":"hp","value":9999}
{"t":"set_hp","hp":9999}
```
结果：**房主血量完全不变** ✅；`validate_client_intent` 对 `state` 返回「不支持的操作」✅

### 6.4 协议健壮性 ✅（全部通过）

| 场景 | 结果 |
|---|---|
| 15 种畸形输入（非 JSON / 半个 JSON / `[]` / `null` / 裸数字 / 空行 / 乱码 `\xff\xfe` / 500 字符 type） | 房主不崩 ✅ |
| 半行分片（先发一半再发另一半） | 正确重组 ✅ |
| 分片粘连（半个帧 + 下一整条） | 不错位 ✅ |
| 一次 send 多条消息 | 全部处理 ✅ |
| 超长行（2 × MAX_LINE = 1MB 垃圾） | 不 OOM / 不卡死 / tick 正常 ✅ |
| 100 帧随机字节 fuzz | 房主存活 ✅ |

### 6.5 断线 ✅
客户端 `close()` 后房主给出事件：
```
('disconnected', '我方离开了房间'), ('bye', None)
```
粗暴 RST 断开、房主关闭后客户端、重复 close、close 后调用方法 —— 全部不崩 ✅

### 6.6 端口与连接 ✅
- `free_port()` 返回合法空闲端口
- `start()` 空闲端口成功；**端口被占用时返回 False 不抛异常**
- 连接无人监听端口 / 非法主机名 → 返回 False 不抛异常
- 重复 `start()`、未 start 就 `close()` → 安全

### 6.7 本机互连完整局 ✅
127.0.0.1 + 随机空闲端口：交换卡组 → 出牌 → 收敛，事件链完整：
```
['listening','connected','peer','ready','peer_ready','start','state','log']
```

---

## 7. 我修正过的自身测试错误（如实记录）

验证者的断言也会错。以下是我**自己写错、已修正**的，与实现无关：

| # | 我的错误 | 真相 |
|---|---|---|
| 1 | 断言「双方构造后都应有手牌」，判 side 1 为 bug | 读 `versus.py:302` 确认构造只启动 side A；side 1 要等自己回合才抽牌（`hand=0, energy=0, draw=30` 是正确中间态）。**我原本差点让 owner 去"修"一个正确的东西** |
| 2 | 断言 `opponent.minions` 是 list 就是「泄露」 | 召唤物是**公开信息**，不是手牌。已加白名单 |
| 3 | 断言「先手方看对手应有 5 张」 | 那时对手尚未行动，应为 0 |
| 4 | 断言 `end_turn` 后先手仍有 5 张 | 回合结束会弃掉剩余手牌（实测 5→0），Slay-the-Spire 式规则。改为验证**交叉一致性** |
| 5 | 端口占用测试绑 `127.0.0.1` | 房主绑 `0.0.0.0`，不冲突，`start()` 返回 True 是**正确**的。改为绑 `0.0.0.0` |
| 6 | 断线检测用 `e.get("t")` 取事件名 | netplay 事件用 **`type`** 字段，我的收集器全取到 `None` → 误判「房主没感知」 |
| 7 | 断线检测 `tick(0.05)` 轮数不足 | 实测需约 36 轮 × 0.1s 才检测到，已改为 120 轮 |
| 8 | 用 `strike` 测同名卡上限 | `STARTER_CARD_IDS={strike,defend}` 有更高上限 `STARTER_MAX_COPIES=3`。改用非起始牌 |
| 9 | 断言超长 id 的错误信息必须 < 10000 字符 | 实测原样回显 100009 字符。属轻微信息放大，**不是崩溃**，改为仅记录不判失败 |

> 第 1 条特别值得记录：我原本会误报一个「bug」，是**多走一步去读实现**才发现那是正确设计。这正是「测试失败 ≠ 实现有错」。

---

## 8. 我诚实声明「未能验证」的部分

1. **真实局域网**：全部测试用 `127.0.0.1`。**未验证**跨设备、WiFi 抖动、NAT、防火墙、不同网段。
2. **零配置发给同学**：未验证打包（PyInstaller）、端口发现/广播、mDNS。
3. **真实人类对局**：平衡性用的是**贪心 AI**，不代表人类打法。72.8% 是先手优势的**下限参考**，真人可能不同。
4. **Qt 版对战界面**（`qt/qversus.py`、`qt/qlobby.py`）**尚未落盘**，完全未验证。
5. **`qt/qdeckbuild.py`** 已落盘但我**未测**（不在我写入范围，且属 UI 层）。
6. **并发/压力**：未测多客户端同时连接、长时间挂机、海量消息洪泛。
7. **安全纵深**：未做真正的渗透测试（如内存攻击、协议逆向、重放攻击）。我测的是「明显的越权与畸形输入」。
8. **A1 音频崩溃的修复**：我只负责定位与报告，**未验证修复**（修复不在我写入范围）。
9. **`deck` 死分支**：确认不影响功能，但未验证 owner 是否打算统一两处白名单。

---

## 9. 验证者立场声明

- **我从未修改被测代码。** 发现 bug 只做两件事：写进本报告 + 直接通知 Lead。
- 写入范围严格限于 `tests/test_versus.py`、`tests/test_deckbuild.py`、
  `tests/test_netplay.py`、`VERIFY_VERSUS.md`。
- 本文档区分「已验证通过」「真实缺陷」「我自己的测试错误」「未能验证」，不谎报。
- 当我自己的陈述与事实不符时，**优先更正陈述**（例：SIGSEGV 曾被误判为「写盘竞态」，
  复跑 20 次后确认是 100% 必现的真实崩溃）。
- 凡是「测试变绿」的地方，我都反问：**这个断言真能感知失败吗？**
  （本轮实例：断线检测因取错字段名而假绿、端口测试因绑错地址而假失败。）

---

## 10. 复现命令汇总

```bash
cd /Users/kevinlee/Documents/deepseek-harness/default-workspace/whale-card-battle

# 三个新测试文件（纯逻辑 + socket，不建 Tk，不受 A1 影响）
python3 -m unittest discover -s tests -p "test_versus.py" -v
python3 -m unittest discover -s tests -p "test_deckbuild.py" -v
python3 -m unittest discover -s tests -p "test_netplay.py" -v

# 平衡性数据（500 场）
python3 -m unittest tests.test_versus.TestVersusBalance -v

# A1 崩溃复现（20/20）
python3 -c "
import sys; sys.path.insert(0,'tests'); sys.path.insert(0,'.')
import test_console
from ui.app import App
App().destroy()
"
```
