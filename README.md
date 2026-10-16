<div align="center">

# 钢铁战线 Steel Frontline

**二战装甲卡牌 Roguelike** · 当前版本 **v0.9.31 测试版**

---
---

# ⬇️ 点下面直接下载 ⬇️

<h2>

[🖥️ macOS 版（38 MB）](https://github.com/d5gkmk96kj-lab/steel-frontline/releases/download/v0.9.27/SteelFrontline-Public-v0.9.27-beta.dmg)

[🪟 Windows 版（52 MB）](https://github.com/d5gkmk96kj-lab/steel-frontline/releases/download/v0.9.27/SteelFrontline-WindowsRework-0.9.28.zip)

</h2>

**打包版自带 Python 与 Qt，不需要装任何东西** —— 下载、双击、开玩。

---

</div>

## 📖 下载之前，请先看一眼这个

**不看就玩，大概率会卡在这几个地方：**

| 你可能会遇到 | 原因 | 怎么解决 |
|---|---|---|
| macOS 打不开，说「无法验证开发者」 | 没买苹果签名 | [看这里](#macos-首次打开) |
| Windows 弹「已保护你的电脑」 | 没买微软签名 | [看这里](#windows-首次打开) |
| 联机按钮点不动 | 服务器每天只开 12 小时 | [看这里](#联机服务器开放时间) |
| 没声音 | 音乐不附带（版权原因） | [看这里](#音乐--bgm) |
| 不知道干嘛 | 这是卡牌 Roguelike | [看这里](#这是什么游戏) |

<div align="center">

**[📦 全部版本 / 更新日志（Releases 页面）](https://github.com/d5gkmk96kj-lab/steel-frontline/releases)**

</div>

---

### 联机服务器开放时间

> **每天 12:00 ～ 24:00** 开放（其余时间服务器关闭）。
>
> 服务器关闭时，「联机对战」按钮会置灰并提示。
> 单机内容任何时间都能玩，不受影响。

### macOS 首次打开

下载的是 `.dmg`，双击打开后把 App 拖进「应用程序」。第一次打开如果提示
「无法验证开发者」：**右键点 App → 打开 → 再点「打开」**，之后就不会再问了。

（这是因为没有买苹果的开发者证书 —— 本游戏完全由 AI 生成，没有预算买证书。）

### Windows 首次打开

解压后双击 `SteelFrontlineWindowsRework.exe`。如果弹出
「Windows 已保护你的电脑」：**点「更多信息」→「仍要运行」**，
之后就不会再问了。首次启动可能要等 5～10 秒。

> ### 🐛 发现 Bug？请到 Wiki 提交
>
> **遇到问题、崩溃、数值不合理，或者想提建议，欢迎到 [Wiki](https://github.com/d5gkmk96kj-lab/steel-frontline/wiki) 提交。**
>
> 提交时麻烦带上这几样，能快很多：
>
> | 要写的 | 从哪来 |
> |---|---|
> | **版本号** | 主菜单副标题，例如 `v0.9.31 测试版` |
> | **怎么复现** | 你点了什么、期望发生什么、实际发生了什么 |
> | **截图** | 有的话最好 |
> | **`~/Documents/钢铁战线/data/crash.log`** | 如果是崩溃，把这个文件内容贴上 |
>
> 已知问题见 [Wiki 的 Known Issues 页](https://github.com/d5gkmk96kj-lab/steel-frontline/wiki)；已修复的 bug 会记在更新日志里。

> | 版本 | 文件名 | 大小 | 音乐 | 用途 |
> |---|---|---|---|---|
> | **0.9.31 测试版 · 公开版** | `SteelFrontline-Public-v0.9.28-beta.dmg` | 38 MB | 无 | 发同学 / GitHub 下载 |
> | 0.9.31 测试版 · 完整版 | `钢铁战线-v0.9.31 测试版-安装包.dmg` | 185 MB | 29 首 | 自己玩（含音乐，不公开分发） |


一款**卡牌构筑 Roguelike**（Slay the Spire 式），二战装甲战争题材，回合制。

- **单人战役**：与 AI 敌军交战，爬塔、组卡、解锁成就
- **局域网 1v1**：和朋友同一 WiFi 直接对战（[见教程](#局域网联机对战1v1)）

> **完全离线**（联机也只在局域网内，不经过任何服务器）。有两个版本：
>
> | 版本 | 依赖 | 画风 | 启动 |
> |---|---|---|---|
> | **高画质版（推荐）** | 需要 PyQt6 | Qt 抗锯齿 / 真渐变 / 平滑动画 | 双击 `启动游戏_高画质版.command` |
> | 经典版 | 零依赖（自带 Tkinter） | Tkinter 手绘 | 双击 `启动游戏.command` |
>
> 两个版本共享同一套 `core/` 引擎与同一份存档。

---


# ⚠️ 此游戏全部由 AI 生成 ⚠️

<h2>🤖 <span style="color:#D32F2F">本项目 100% 由 AI（DeepSeek-V4.1-Flash）生成</span> 🤖</h2>

**代码、卡牌、数值、美术、文案、翻译、测试、打包脚本 —— 一行一行，全部来自 AI。**

人类只做了三件事：**提需求、点运行、报 Bug。**

</div>

---

> ## 🔴 请注意
> - **readme也是AI写的 除了这句话 有问题还是那句话：wiki
> - **这是 AI 作品。** 它没有经过专业团队打磨，平衡性、代码质量、文案水准都可能有明显问题。
> - **很可能存在尚未发现的 Bug。** 遇到问题欢迎到 [Wiki](https://github.com/d5gkmk96kj-lab/steel-frontline/wiki) 提交。
> - **素材版权**：美术全部由**代码程序化生成**（没有一张图片文件），音乐**不附带**（避免版权问题，请自行添加）。
> - **没有苹果签名**，macOS 首次打开会被拦一次，[点这里看怎么放行](#macos-首次运行通过审核隐私与安全性)。
> - **不接受"AI 做的东西也配叫游戏"这类争论** —— 这本来就是个实验：看看现在 AI 能独立做出什么。

---

## 下载哪个版本

| 平台 | 版本 | 怎么用 |
|---|---|---|
| **macOS** | 高画质版 / 经典版 | 见下面的[下载区](#-下载--download) |
| **Windows** | **Windows Rework** | 解压后双击 `.exe` |

### Windows Rework 版

- 名字里带 **Windows Rework** 的就是 Windows 版
- 解压 zip → 双击 `钢铁战线WindowsRework.exe`
- **自带 Python 和 Qt**，不用装任何东西
- 首次打开如果弹出「Windows 已保护你的电脑」：
  点「**更多信息**」→「**仍要运行**」
  （因为没买微软的数字签名证书，这是正常现象）

> **存档位置**（Windows）：`%APPDATA%\钢铁战线\data\`

---

## 快速开始

### 高画质版（PyQt6，推荐）

```bash
cd whale-card-battle
python3 -m pip install --user PyQt6   # 只需一次，约 60MB
python3 qt/main_qt.py
```

macOS 可直接双击 **`启动游戏_高画质版.command`**（会自动检测并安装 PyQt6）。

### 经典版（Tkinter，零依赖）

```bash
cd whale-card-battle
python3 main.py
```

macOS 可直接双击 **`启动游戏.command`**。

### 命令行参数（两版通用）

```bash
python3 qt/main_qt.py --seed 42        # 指定种子
python3 qt/main_qt.py --ascension 5    # 指定战役难度
python3 qt/main_qt.py --fullscreen     # 全屏
python3 qt/main_qt.py --selftest       # 无头自检
```

其它启动方式：

```bash
python3 main.py --seed 12345   # 指定种子（同种子可复现同一局）
python3 main.py --asc 5        # 指定战役难度（0–20）
python3 main.py --daily        # 每日挑战（全球同种子，按日期确定）
python3 main.py --selftest     # 无窗口自检：数据层 + 引擎冒烟
```

macOS 用户也可以直接双击 **`启动游戏.command`**。

---

## 这是什么游戏

你是**装甲指挥官**，率领部队向敌方纵深推进。每局从 10 张制式卡开始，
沿途收集**攻击 / 战术 / 指令**三类卡牌与**勋章**，一步步构筑出属于你的战斗体系。

- **目标**：通过 3 幕战区，击败最终要塞
- **单局时长**：30–60 分钟
- **失败**：总部 HP 归零（当局结束，但元进度永久保留）

### 五大战术流派

| 流派 | 核心机制 | 打法 |
|---|---|---|
| **突击** | 火力（每层 +1 伤害）、破甲（受伤 +50%） | 堆火力一回合爆发 |
| **防御** | 掩体、铁丝网反伤、工事 | 叠甲反打，越打越硬 |
| **燃烧弹** | 燃烧（每回合掉血后递减）、压制（敌人伤害 -25%） | 挂持续伤害，慢慢磨死 |
| **后勤** | 额外补给、抽牌、连射、弹药储备 | 一回合打出十几张牌 |
| **支援** | 附属单位（独立行动）、增援（每回合叠火力） | 铺场滚雪球 |

---

## 为什么能玩很久

这是设计时最优先考虑的目标，共 7 层长期动力：

1. **20 档战役难度**（`--asc 0..20`）——每档叠加真实难度：敌人血量/伤害递增、
   开局携带诅咒、精英翻倍、Boss 额外阶段。通关一档解锁下一档。
2. **元进度永久解锁**——即使这局失败，图鉴、成就、难度解锁全部保留。
3. **30 个成就**——从「初次下潜」到「钢铁终焉」，覆盖各种极限玩法
   （15 张以下薄牌组通关、20 分钟速通、5 点生命翻盘、纯防御流通关…）。
4. **完整图鉴**——134 张卡 / 52 个勋章 / 53 种敌军全部可收集查阅。
5. **每日挑战**——全球同种子，每天一张新地图。
6. **自定义种子**——想复盘某个局面就输入同一个种子。
7. **本地排行榜 + 存档**——Top 10 分数记录，随时中断续玩。

### 内容量

| 内容 | 数量 |
|---|---|
| 卡牌 | **134** 张（攻击 54 / 战术 46 / 指令 22 / 状态 6 / 诅咒 6） |
| 勋章（遗物） | **52** 个，覆盖 11 类触发时机 |
| 敌军 | **53** 种（含 3 个 multi-phase 要塞 Boss） |
| 事件 | **31** 个战场抉择 |
| 战役难度 | **20** 档 |
| 成就 | **30** 个 |

---

## 操作

| 操作 | 说明 |
|---|---|
| 鼠标悬停卡牌 | 放大 + 显示详细说明 |
| 左键点击卡牌 | 选中（需要目标的牌再点敌人） |
| 结束回合 | 敌方行动（逐个播放动画） |
| `Esc` | 返回 / 关闭 |
| 拖拽窗口边缘 | 窗口可缩放（最小 1280×800） |

---

## 局域网联机对战（1v1）

**不需要联网，不需要服务器。** 两台电脑连同一个 WiFi（或同一路由器），一台开房间、一台加入即可。

> 只有**高画质版（PyQt6）**有联机。经典版是纯单机。

### 完整教程：开房间 + 加入

#### 第一步：两台电脑在同一个局域网

确认两台机器连的是**同一个 WiFi**（或同一台路由器的网口）。
手机热点也行 —— 两台电脑都连你的热点即可。

#### 第二步：房主开房间

1. 打开游戏 → 主菜单点「**联 机 对 战**」
2. 选「**创 建 房 间**」（默认就选中了）
3. 界面会显示你的**本机 IP**，长得像 `192.168.1.7` 或 `10.42.100.2`
4. 记下这个 IP，**念给对面的人**（或截图发给他）
5. 点「**开 始 等 待**」，状态变成「等待对方连接…」

> 端口默认 `45671`。如果提示「端口已被占用」，说明别的程序占了这个口，
> 换一个端口再试（界面可改）。

#### 第三步：另一台电脑加入

1. 打开游戏 → 主菜单点「**联 机 对 战**」
2. 选「**加 入 房 间**」
3. 在输入框里填房主念给你的那个 IP
4. 点「**连 接**」

连上后两边都会进入**卡组构筑**界面。

#### 第四步：各自组卡

- 开局 **134 张卡全部解锁**，随便挑
- 卡组需要 **20–40 张**
- 同名卡最多 **2 张**（`步枪齐射`/`构筑掩体` 这类制式牌可以放 3 张）
- 懒得组就点「**随机一套**」或选一套「**推荐流派**」：

| 流派 | 打法 |
|---|---|
| **突击流** | 高伤害快攻，靠连射和火力压制抢节奏 |
| **铁壁流** | 堆掩体反击，铁丝网反伤，越拖越强 |
| **蚀骨流** | 上燃烧和破甲，让对手每回合流血 |
| **后勤流** | 疯狂抽牌与补给，用牌差和信息优势碾压 |
| **唤灵流** | 大量附属单位铺场，人海战术 |

#### 第五步：开打

- 双方各 **75 点总部耐久**，每回合 **3 点补给**，抽 5 张牌
- 回合限时 **60 秒**，超时自动结束回合
- 谁先被打到 0 谁输

**先后手公平性**：后手第一回合多给 **2 点补给**作为补偿。
（实测 1200 局镜像对战，先手胜率 50.4%，基本五五开。）

### 联机的已知限制

诚实说明，避免你踩坑：

| 限制 | 说明 |
|---|---|
| **只支持 1v1** | 不支持 3 人以上 |
| **不支持中途重连** | 一方掉线即对局结束，不能续玩 |
| **只有局域网** | 同一 WiFi / 同一路由器。跨网络需要自己做端口转发 |
| **明文传输、无密码** | 同一网段的人理论上能连进你的房间（谁先连上算谁的） |
| **房主是权威端** | 房主自己作弊无法被防（但客户端作弊**一定会被抓**） |
| **macOS 防火墙** | 首次开房间若对方连不上，去「系统设置 → 网络 → 防火墙」放行 |

### 连不上时的排查顺序

1. **确认在同一个 WiFi** —— 最常见的原因。手机热点测试最可靠
2. **IP 填对了吗** —— 房主界面显示的那个，不是 `127.0.0.1`
3. **防火墙** —— macOS 首次会弹「是否允许接受传入连接」，点「允许」
4. **换端口** —— 45671 被占用时换一个
5. **VPN 关掉** —— 部分 VPN 会把局域网流量劫走，导致同网段也连不上

---

## 联机方式

游戏支持两种联机：

| 方式 | 适用场景 | 怎么做 |
|---|---|---|
| **局域网** | 同一个 WiFi（家里、宿舍、教室） | 房主开房 → 把 IP 念给同学 → 对方输入 |
| **公网** | 不在同一个网络，相隔两地 | 房主开房 → 得到 **4 位房间号** → 发给对方 → 对方输入 |

### 公网联机（推荐）

```
房主：联机 → 公网建房 → 屏幕显示「4821」
      把 4821 发给对方（微信 / QQ / 游戏群都行）

对方：联机 → 公网加入 → 输入 4821 → 开打
```

**不需要在同一个 WiFi，不需要知道对方 IP，不需要任何网络配置。**

> 公网联机需要中继服务器。如果暂时连不上，
> 用局域网方式，或开手机热点让两台设备处在同一网络。

---

## 联机安全性

局域网里任何人都能连上你的端口，所以加了**房间码**：

### 怎么用

1. 房主勾选 **「需要房间码（更安全）」**，开房后会显示一串码，例如：

   ```
   房间码：K7F2-9QMX-3BPD
   ```

2. 把这串码告诉同学（念前几组也行，最少 8 个字符）
3. 同学在「加入房间」页填进去 → 连上

**不勾选**就还是原来的行为（谁都能连），适合自己家里玩。

### 安全措施

| 措施 | 作用 |
|---|---|
| **房间码** | 不知道码就进不来，防止同网段陌生人乱入 |
| **消息签名（HMAC）** | 每条消息都签名，中间改了内容会被发现并丢弃 |
| **防重放** | 同一条消息重复发送会被拒绝 |
| **连续异常断开** | 连续 5 次校验失败直接断开，不给爆破机会 |
| **码最短 8 位** | 太短的输入不接受，避免"输两个字符就进去" |

> 房间码是**短期**的（默认 6 小时），过期后需要重新开房。

---

## 掉线重连

网络抖一下（切 WiFi、合盖唤醒）不至于整局作废：

- 掉线后进入**重连窗口**（默认 60 秒），房主不会立刻销毁对局
- 客户端自动重试，间隔逐步拉长：`0.8s → 1.6s → 2.5s → 4s → 6s → 8s`
- 窗口内连回来就能继续打，超过窗口才真正结束

---

## 公平游戏

> **请公平地玩。**

**单人模式**：这是你自己的游戏体验，怎么玩都行。

**神人模式**（战役难度拉满到第 20 档）：全部辅助功能失效。
这是最高难度的荣誉挑战，想证明自己就老老实实打。

**联机模式**：对局以房主为准，客户端无法单方面改动结果。
任何试图伪造网络消息的行为都会被拦截并记录。

---

## 音乐 / BGM

### 怎么加自己的音乐（完整教程）

游戏本身**不带音乐**（版权原因）。加歌只要三步：

**第 1 步：找到音乐目录**

游戏第一次运行时会自动创建音乐目录：

```
~/Documents/钢铁战线/music/
```

> **在 Finder 里怎么过去**：菜单栏「前往」→「个人」→ 进 `Documents` → 进 `钢铁战线` → `music`
> 或者按 `Cmd+Shift+G`，粘贴 `~/Documents/钢铁战线/music/` 回车。

**第 2 步：把歌拷进去，按顺序命名**

文件名必须是 `music1`、`music2`、`music3`……（**后面跟扩展名**）：

```
music1.ogg
music2.ogg
music3.ogg
...
```

支持的格式：**`mp3` / `ogg` / `m4a` / `wav` / `aac` / `aiff` / `flac`**

> **格式随便混**，`music1.mp3` 和 `music2.ogg` 可以共存，游戏内部按数字排序。
> 注意 **`music10` 排在 `music2` 后面**（按数字排，不是按字母），放心加到 99 首。

**第 3 步：重启游戏**

就这么简单，不用任何设置。

### 播放规则

1. **开局固定放 `music1`**（每次打开游戏都是第一首）
2. 一首放完 → **随机**挑下一首
3. 再放完 → 再随机 → **永不停止**
4. 随机时会避开刚放过的几首，不会短时间内反复听同一首

### 常见问题

| 问题 | 原因 / 解决 |
|---|---|
| **放进去了但没声音** | ① 文件名是不是 `music1.mp3` 这种格式；② 有没有重启游戏；③ 检查设置里「启用背景音乐」是否开着 |
| **想换掉某一首** | 直接删掉旧的、放新的、名字保持不变即可 |
| **想全部重来** | 把 `music/` 里清空，重新放 |
| **顺序不对** | 检查文件名数字。游戏按**数字**排序：1, 2, 3 … 10, 11 |
| **找不到 music 文件夹** | 先启动一次游戏，它会自动创建；或者手动建 `~/Documents/钢铁战线/music/` |
| **音量太小 / 太大** | 设置界面有音量滑条；也可以用系统音量 |

### 想按场景放不同的曲子（进阶）

除了 `music1`/`music2` 这种电台模式，还可以按**场景**命名，游戏会优先用场景曲子：

```
menu.*        主菜单
battle.*      战斗
map.*         战区推进图
shop.*        补给站 / 商店
event.*       事件
rest.*        战地医院
reward.*      战利品结算
victory.*     胜利
defeat.*      失败
ambient.*     通用兜底（任何场景缺曲子时用它）
```

例子：
- 只想一首曲子全程循环 → 放一个 `ambient.mp3` 就够了
- 主菜单和战斗要不同曲子 → `menu.mp3` + `battle.mp3`

> 两种模式可以混用：有场景曲子时用场景曲子，没有就回落到 `music1/2/3…` 电台。

### 电台模式（默认）

**最省事的用法**：把歌丢进 `music/`，命名成 `music1.ogg`、`music2.ogg`、`music3.ogg`…
然后**什么都不用设置**，游戏会自动：

1. 启动时从 **`music1`** 开始播
2. 一首放完 → **随机**挑下一首继续
3. 再放完 → 再随机 → **永不停止**

随机时会避开刚放过的几首，不会短时间内反复听同一首。

设置界面里点「◀ 上一首 / 下一首 ▶」或双击列表可以随时手动切歌；
关掉「启用背景音乐」再打开，会**从刚才那首继续**，不会跳回第一首。

### 场景命名（可选，想精细控制时用）

> 如果你的文件按下面这些**场景名**命名，游戏会用它们做「进战斗换战斗曲」这类自动切换，
> 而不是电台随机。两种方式可以共存 —— 有场景命名的优先，其余走电台。

### 场景对照表

| 文件名 | 场景 |
|---|---|
| `menu.*` | 主菜单 |
| `battle.*` | 战斗 |
| `map.*` | 战区推进图 |
| `shop.*` | 补给站 / 商店 |
| `event.*` | 战场事件 |
| `rest.*` | 战地医院 |
| `reward.*` | 战利品结算 |
| `victory.*` / `defeat.*` | 胜负结算 |
| `ambient.*` | **通用兜底**（缺曲子时用它） |

支持 `mp3 / m4a / wav / aac / aiff / ogg`。

某个场景没放对应曲子会自动回退到 `ambient.*`；如果**一个场景名都没匹配上**
（比如你的文件叫 `music1.ogg`），就自动进入上面的电台模式。

### 设置界面里的音乐控制

进入 **设置** 界面，有三块：

| 控件 | 作用 |
|---|---|
| **音乐音量** | 0–100，实时生效，不用重启 |
| **启用背景音乐** | 勾选框。取消勾选立刻静音；重新勾上会**接着原来的曲子**播，不会重头开始 |
| **选 择 音 乐** | 列出 `music/` 里**全部**曲目，双击（或选中后点「播 放」）即切歌 |

「选择音乐」面板还带：

- `◀ 上一首` / `下一首 ▶` —— 在全部曲目里循环切换
- `刷新列表` —— 刚往 `music/` 拖进新歌，点一下就能看到
- `打开 music/ 目录` —— 直接在访达里打开，方便拖文件
- 正在播的那首前面有 `♪` 标记，下方显示「当前：xxx.mp3」

> 注意：手动选歌会**覆盖场景自动切换**，之后一直播你选的这首，直到你切换界面或再选别的。

### 播放机制

- **零第三方依赖**：macOS 用系统自带的 `afplay`；PyQt6 版也可走 `QtMultimedia`
- **自动循环**：`afplay` 本身不支持循环，游戏会在曲子结束前 0.35 秒无缝重启，听不出接缝
- **后台播放**：不占用游戏帧率
- 退出时自动停止，不留残余进程

### 在游戏内查看

设置界面可以看到当前音乐后端、音量与识别到的曲库。

---

## 更新软件

### 需要联网

**游戏本身完全离线**，只有**检查更新**这一步需要联网（几 KB 的请求）。

- 启动游戏后会自动在后台检查一次（不阻塞、不影响玩）
- 也可以手动检查：**设置 → 检查更新**
- 离线时检查会静默失败，不影响任何功能

如果发现新版本，会弹出提示，列出这次**修复了什么 Bug、新增了什么功能**，
点「前往下载」会打开浏览器到 GitHub 下载页。

### 怎么更新（三步）

1. 下载新的 `.dmg`
2. 打开它，把新的 App **拖进「应用程序」文件夹**（提示覆盖时选「替换」）
3. 完成 —— **存档、音乐、成就全部保留**

> **存档不会被覆盖**：存档在 `~/Documents/钢铁战线/data/`，
> 不在 App 内部。换 App 不影响进度。

### 清理旧版本

更新完成后，可以在 **设置 → 清理旧版本** 里删掉旧的 App 和旧的安装包。

- 会**逐项列出**要删什么、多大
- **存档绝不会被删除**（代码里有硬性保护）
- 当前正在用的版本也会自动跳过

---

## macOS 首次运行：通过审核（隐私与安全性）

这个包**没有苹果开发者签名**（签名要 $99/年），所以 macOS 第一次会拦一下。
按下面做一次即可，之后双击就能正常打开。

### 方法一：右键打开（最快）

1. 打开「应用程序」文件夹
2. **右键**（或按住 Control 点）「钢铁战线」
3. 选「**打开**」
4. 弹窗里再点一次「**打开**」

### 方法二：隐私与安全性里放行

如果右键打开也看不到「打开」按钮：

1. 双击 App，会弹出「无法打开，因为 Apple 无法检查其是否包含恶意软件」
2. 点「**完成**」（或「好」）
3. 打开 **系统设置** → **隐私与安全性**
4. 往下拉到「**安全性**」区域
5. 会看到一行：
   > **"钢铁战线" 已被阻止，因为它来自身份不明的开发者**
6. 点旁边的「**仍要打开**」
7. 输入你的开机密码 / 用 Touch ID 确认
8. 再双击 App，弹窗里点「**打开**」

> **看不到「仍要打开」按钮？**
>
> 那说明你下载的是**旧版本**（v0.9.28 之前的包签名是坏的）。
> 旧包的签名有缺陷，macOS 无法识别它，所以**不提供放行按钮** ——
> 这种情况只能用下面的命令行方法。
>
> **现在的新包已经修好了签名**，正常会出现「仍要打开」。
> 请重新下载最新的 DMG。

### 方法三：命令行（前两种都不行时）

```bash
xattr -dr com.apple.quarantine /Applications/钢铁战线.app
```

执行后再双击即可。

> **为什么会有这个提示？**
> 苹果要求所有 App 都购买开发者证书（$99/年）并做公证，否则一律拦截。
> 这是开源小项目的普遍情况，**不代表软件有问题** —— 全部源码都在这个仓库里，
> 你可以自己审阅、自己打包。

---

## 自定义提示语（Tips）

游戏会在**主菜单、加载、战役胜利、战役失败**时随机显示一条提示。

**所有提示都写在项目根的 `tips.txt` 里，你可以随便改。**

### 怎么写

一行一条，想加多少加多少。**想同时支持中英文，就用 `|` 分开**：

```
薄牌组通常比厚牌组强 —— 商店可以删卡。 | Thin decks usually beat fat decks.
遇到打不过的精英，绕开也是一种战术。 | Skipping an unbeatable elite is valid.
只有中文也行，英文界面会回落显示这句。
```

- `|` 前面是中文，后面是英文
- 只写中文也可以 —— 英文界面会回落显示中文那条（不会空白）
- 空行会被忽略
- `#` 开头的行是注释，不会显示
- 不用加引号、不用编号
- **改完重启游戏生效**，不用重新打包

### 想让不同场景显示不同的话

用标记分节：

```
[菜单]
只有主菜单会显示这句

[加载]
只有加载时会显示这句

[胜利]
通关时才显示

[失败]
战败时才显示
```

**没有归入任何分节的提示 = 通用提示**。

出现概率是这么分的：

| | 概率 |
|---|---|
| 通用提示 | **50%** |
| 该场景专属提示 | **50%**（多条则平分） |

只写了其中一类时，100% 都给那一类，不会出现空白。

### 文件在哪

| 情况 | 位置 |
|---|---|
| 源码运行 | 项目根目录的 `tips.txt` |
| 装了 DMG | DMG 里的 `tips.txt`（拖到桌面改也行），或放到 App 旁边 |
| 想用自己的一份 | 放进 `~/Documents/钢铁战线/data/tips.txt`（优先级最高） |

> 如果 `tips.txt` 是空的（或者全被注释掉了），游戏会显示内置的几条兜底提示，
> 保证不会出现空白。

---

## 画面特效

### 有什么

| 特效 | 出现时机 |
|---|---|
| **火花爆发** | 卡牌命中敌人时（伤害越高火花越大） |
| **冲击环** | 命中瞬间扩散的圆环 |
| **斩击弧** | 高伤害 / 击毁敌人时追加 |
| **格挡特效** | 获得掩体时（冷色，和攻击区分） |
| **总部挨打** | 自己掉血时红色火花 + 震屏 |
| **界面过渡** | 主菜单 ↔ 地图 ↔ 战斗 之间淡入淡出 |

### 性能

- 全部基于 `QPropertyAnimation`，**不阻塞主线程**（不会卡帧）
- 播完自动销毁，不占内存
- 低配机器可以在 **设置 → 战斗特效与界面过渡动画** 里**一键关掉**

> 关掉后功能完全不受影响，只是没有特效。

---

## 存档管理

主菜单 → **存档管理**。可以同时保留多个存档，每个都是独立文件。

| 操作 | 说明 |
|---|---|
| **读取** | 载入这个存档继续玩 |
| **改名** | 给存档起个名字（默认是「第 N 幕 · 第 M 层」） |
| **导出** | 存成 `.json` 文件，**可以发给别人** |
| **删除** | 删掉（会二次确认） |
| **导入存档** | 选一个别人给你的 `.json` 文件加进来 |
| **打开存档目录** | 在 Finder 里打开，方便手动管理 |

存档位置：

```
~/Documents/钢铁战线/data/saves/
```

每局战役在**首次保存时**自动创建一个存档槽，之后保存会更新同一个槽
（不会越存越多）。战斗、商店、事件、休息、设置里点保存都会写入。

### 把存档发给别人

1. 你这边：存档管理 → 找到那个存档 → 点**导出** → 存到桌面
2. 发给对方（微信/QQ/邮件都行，文件很小，约 18 KB）
3. 对方：存档管理 → 点**导入存档** → 选中这个文件

导入时会校验文件格式，损坏或不是存档的文件会被拒绝，不会污染对方的存档列表。

---

## 版本号规则

`钢铁战线` 用这样的版本号：

```
0.9  →  0.9.29  →  0.9.29  →  ...  →  0.9.29  →  0.10  →  1.0
```

- **每次推送 +0.01**（小更新）
- 补零编号 `0.9.29 < 0.9.29 < ...`，到 `0.9.29` 自动进位成 `0.10`
- **要上大版本就手动跳**，比如直接 `1.0` 或 `1.0.0.0`
- 发版脚本：

```bash
# 小更新：自动 +0.01
python3 packaging/bump_version.py --auto "修复了 xxx"

# 大版本：手动指定
python3 packaging/bump_version.py --set 1.0.0.0 "正式版发布"
```

游戏内的**检查更新**读的是仓库根目录的 `version.json`，所以发版时
`core/version.py` 与 `version.json` 必须一致（发版脚本会自动同步）。

---

## 项目结构

```
whale-card-battle/
├── main.py              # 启动器
├── 启动游戏.command      # macOS 双击启动
├── ARCHITECTURE.md      # 架构契约（冻结接口 / 附录 A / 附录 B）
├── README.md
├── core/                # 游戏逻辑（零 UI 依赖，可独立测试）
│   ├── cards.py         # 134 张卡 + 效果函数 + 引用审计
│   ├── relics.py        # 52 个勋章
│   ├── enemies.py       # 53 种敌军 + 意图 AI
│   ├── events.py        # 31 个事件 + 商店 + 宝箱
│   ├── engine.py        # 战斗引擎（伤害管线 / buff / 召唤 / 胜负）
│   └── run.py           # 地图 / 元进度 / 20 档难度 / 存档
├── ui/                  # Tkinter 界面
│   ├── theme.py         # 配色 / 字体 / 绘制工具
│   ├── widgets.py       # 卡牌 / 血条 / 能量 / 按钮 等控件
│   ├── art.py           # 程序化军事美术（坦克/碉堡/飞机/铁丝网…）
│   ├── battle_view.py   # 战斗界面
│   ├── map_view.py      # 战区推进图
│   ├── screens.py       # 菜单 / 商店 / 图鉴 / 结算 等
│   └── app.py           # 主窗口与界面路由
├── qt/                  # PyQt6 高画质版（与 ui/ 并存，共享 core/）
│   ├── main_qt.py       # 入口
│   ├── qtheme.py        # Qt 配色 / QSS / QPainter 工具
│   ├── qwidgets.py      # 卡牌 / 血条 / 单位立绘 等控件
│   ├── qbattle.py       # 战斗界面（含动画）
│   ├── qmap.py          # 战区推进图
│   ├── qscreens.py      # 菜单 / 商店 / 图鉴 / 结算 等
│   ├── qapp.py          # 主窗口与路由
│   └── headless_tour.py # 无头遍历验收脚本
├── tests/               # 175 个单元测试（纯 unittest）
├── data/                # 存档（自动生成）
└── selfcheck_coredata.py# 数据层完整性审计
```

---

## 开发 / 验证

```bash
# 运行全部测试（516 个用例）
python3 -m unittest discover -s tests -v

# 引擎与数据层冒烟
python3 main.py --selftest

# 数据完整性审计（幽灵 id / 交叉引用 / 数值自洽）
python3 selfcheck_coredata.py

# 平衡性蒙特卡洛（2000 场自动对战）
python3 tests/test_balance.py --full
```

### 当前状态

- **175 / 175 测试通过**（2 个 skip）
- 端到端：开局 → 战斗 → 存档读档 → 12 个界面切换，全部正常
- 蒙特卡洛 2000 场：`act1 普通战胜率 100%`，通关率随难度单调下降
  （难度 0 → 43%，难度 20 → 5%），0 超时 0 崩溃

---

---

## 关于素材

本项目**不含任何外部素材文件**：

- 所有美术均为**程序化绘制**（Tkinter Canvas / QPainter 代码生成）——坦克、碉堡、
  飞机、铁丝网、勋章、卡面质感等全部由代码绘制，无图片文件依赖
- 无音频文件
- 因此**没有任何版权问题**，也不会因为缺少素材文件而无法运行

---

## 常见问题

**Q: 提示 `No module named tkinter`？**
macOS 自带 Python 3 已包含 tkinter。若使用自定义 Python，请安装带 tk 支持的版本。

**Q: 窗口显示异常 / 卡住？**
本机 Python 3.9 自带 Tk 8.5 在 macOS 上较旧。若遇到渲染问题，可尝试
`qt/` 目录下的 PyQt6 版本（需先 `pip install PyQt6`）。

**Q: 存档在哪？**
`~/Documents/钢铁战线/data/saves/`（多个存档，每个一个文件）。
成就等永久进度在 `data/meta.json`。改了 `data/` 之外的位置都不影响存档。

**Q: 遇到 Bug 怎么办？**
到 [Wiki](https://github.com/d5gkmk96kj-lab/steel-frontline/wiki) 提交，
带上版本号、复现步骤和截图。详细要求见 [下载区上方的说明](#-下载--download)。

**Q: 怎么玩得更好？**
薄牌组通常强于厚牌组 —— 商店可以删卡。专注一个流派比什么都拿更强。

---

<a id="english"></a>
# English

<div align="center">

## ⚠️ This game is entirely AI-generated ⚠️

### 🤖 100% built by AI (DeepSeek-V4.1-Flash) 🤖

**Code, cards, balance numbers, art, text, translations, tests, build scripts —
every single line came from AI.**

The human did exactly three things: **asked for it, ran it, reported bugs.**

</div>

> ### 🔴 Please note
>
> - **This is an AI project.** It has not been polished by a professional team;
>   balance, code quality and writing may all have rough edges.
> - **There are probably bugs I have not found.** Report them on the
>   [Wiki](https://github.com/d5gkmk96kj-lab/steel-frontline/wiki) and it will be
>   the AI fix them.
> - **Assets**: all art is **procedurally generated in code** (not a single image
>   file), and **no music is bundled** (to avoid copyright issues — add your own).
> - **No Apple signature**, so macOS blocks the first launch once.
>   [Here is how to allow it](#option-1-right-click-to-open-fastest).
> - **Arguments of the form "AI-made things are not real games" are not welcome
>   here.** This is an experiment: let us see what AI can build on its own today.

**Current version: 0.9.29 Beta**

> Bilingual document. Chinese is above; English starts here.
> [Back to top / 回到顶部](#钢铁战线-steel-frontline)

**Steel Frontline** is a **deck-building roguelike** (Slay-the-Spire style) set in
a WWII armored-warfare theme, turn-based.

- **Solo campaign** — fight AI forces, climb the map, build decks, unlock achievements
- **LAN 1v1** — battle a friend directly over the same WiFi ([tutorial](#lan-1v1-versus))

> **Fully offline** (even multiplayer stays on your LAN — no servers involved).
> Two editions:
>
> | Edition | Dependency | Look | Launch |
> |---|---|---|---|
> | **Hi-Fi (recommended)** | needs PyQt6 | Qt anti-aliasing / real gradients / smooth animation | double-click `启动游戏_高画质版.command` |
> | Classic | zero dependencies (bundled Tkinter) | hand-drawn Tkinter | double-click `启动游戏.command` |
>
> Both share the same `core/` engine and the same save file.

## Which Build to Download

| Platform | Build | How |
|---|---|---|
| **macOS** | Hi-Fi / Classic | see the [download section](#-下载--download) |
| **Windows** | **Windows Rework** | unzip and double-click the `.exe` |

### Windows Rework

- The Windows build is the one with **Windows Rework** in the name
- Unzip, then double-click `SteelFrontlineWindowsRework.exe`
- **Bundles Python and Qt** — nothing to install
- If SmartScreen appears on first launch, click **More info** → **Run anyway**
  (there is no paid Microsoft code-signing certificate; this is normal)

> **Save location (Windows):** `%APPDATA%\钢铁战线\data\`

---

## Quick Start

### Hi-Fi edition (PyQt6, recommended)

```bash
cd whale-card-battle
python3 -m pip install --user PyQt6   # once, ~60 MB
python3 qt/main_qt.py
```

On macOS you can just double-click **`启动游戏_高画质版.command`** (it detects and
installs PyQt6 for you).

### Classic edition (Tkinter, zero dependencies)

```bash
cd whale-card-battle
python3 main.py
```

On macOS you can just double-click **`启动游戏.command`**.

### Command-line flags (both editions)

```bash
python3 qt/main_qt.py --seed 42        # fixed seed
python3 qt/main_qt.py --ascension 5    # campaign level
python3 qt/main_qt.py --fullscreen     # fullscreen
python3 qt/main_qt.py --selftest       # headless self-test
```

Other launch options:

```bash
python3 main.py --seed 12345   # same seed reproduces the same run
python3 main.py --asc 5        # campaign level (0-20)
python3 main.py --daily        # daily challenge (same seed for everyone, by date)
python3 main.py --selftest     # no-window self-test: data layer + engine smoke
```

## What Kind of Game Is This

You are an **armored commander** pushing into enemy territory. Each run starts with
10 standard cards; along the way you collect **Attack / Tactics / Orders** cards and
**Medals**, gradually building your own combat engine.

- **Goal** — clear 3 acts and defeat the final fortress
- **Run length** — 30-60 minutes
- **Failure** — HQ HP hits zero (the run ends, meta progress is permanent)

### The five archetypes

| Archetype | Core mechanic | How it plays |
|---|---|---|
| **Assault** | Strength (+1 damage per stack), Vulnerable (+50% damage taken) | Stack Strength, burst one turn |
| **Defense** | Block, Barbed Wire retaliation, Fortifications | Out-armor them and hit back |
| **Incendiary** | Burn (damage over turns, decays), Weak (enemy damage -25%) | Apply damage-over-time, grind them down |
| **Logistics** | Extra Energy, card draw, multi-hit, ammo stockpiles | Play a dozen cards per turn |
| **Support** | Minions (act independently), Reinforce (Strength each turn) | Flood the board, snowball |

## Why It Lasts

Long-term replayability was the top design priority — 7 layers of it:

1. **20 campaign levels** (`--asc 0..20`) — each stacks real difficulty: enemy
   HP/damage up, starting curses, doubled elites, extra boss phases. Clearing one
   unlocks the next.
2. **Permanent meta progression** — even a failed run keeps your codex,
   achievements, and level unlocks.
3. **30 achievements** — from "First Descent" to "Steel Finale", covering extreme
   playstyles (win with under 15 cards, speedrun in 20 minutes, win at 5 HP, win
   with a pure Defense deck...).
4. **Full codex** — all 134 cards / 52 medals / 53 enemies browsable.
5. **Daily challenge** — one seed worldwide, a new map every day.
6. **Custom seeds** — replay any situation by entering the same seed.
7. **Local leaderboard + saves** — top-10 scores, quit and resume anytime.

### Content

| Content | Count |
|---|---|
| Cards | **134** (Attack 54 / Skill 46 / Power 22 / Status 6 / Curse 6) |
| Medals (relics) | **52**, covering 11 trigger timings |
| Enemies | **53** (including 3 multi-phase fortress bosses) |
| Events | **31** battlefield choices |
| Campaign levels | **20** |
| Achievements | **30** |

## Controls

| Action | Effect |
|---|---|
| Hover a card | Enlarge + show full description |
| Left-click a card | Select (targeted cards need a second click on an enemy) |
| End Turn | Enemies act (animated one by one) |
| `Esc` | Back / close |
| Drag window edge | Resizable (minimum 1280x800) |

## LAN 1v1 Versus

**No internet, no server required.** Two computers on the same WiFi (or router):
one hosts, the other joins.

> Only the **Hi-Fi (PyQt6)** edition has multiplayer. The Classic edition is solo-only.

### Full tutorial: hosting and joining

#### Step 1 — Put both computers on the same LAN

Make sure both are on the **same WiFi** (or the same router's ports).
A phone hotspot works too — connect both laptops to your hotspot.

#### Step 2 — The host opens a room

1. Launch the game -> main menu -> **LAN VERSUS**
2. Pick **Create Room** (selected by default)
3. The screen shows your **local IP**, something like `192.168.1.7` or `10.42.100.2`
4. Note it down and **read it aloud** to the other player (or screenshot it)
5. Click **Start Waiting**; status becomes "Waiting for opponent..."

> Default port is `45671`. If you see "port already in use", another program has
> it — pick a different port in the UI.

#### Step 3 — The other computer joins

1. Launch the game -> main menu -> **LAN VERSUS**
2. Pick **Join Room**
3. Type the IP the host read out
4. Click **Connect**

Both sides then go to deck building.

#### Step 4 — Build decks

- **All 134 cards are unlocked** from the start
- A deck needs **20-40 cards**
- Max **2 copies** of the same card (`Rifle Volley` / `Build Cover` get 3)
- In a hurry? Click **Random Deck** or pick a **Recommended Archetype**:

| Archetype | Playstyle |
|---|---|
| **Assault** | High damage, fast, seizes tempo with multi-hits |
| **Defense** | Stack Block and retaliate with Barbed Wire |
| **Incendiary** | Burn and Vulnerable, make them bleed every turn |
| **Logistics** | Draw and Energy engines, win on card advantage |
| **Support** | Flood the board with minions |

#### Step 5 — Fight

- Both sides start at **75 HQ Integrity**, **3 Energy** per turn, draw 5 cards
- Each turn has a **60-second** limit; it auto-ends on timeout
- First HQ reduced to 0 loses

**Turn-order fairness**: the second player gets **+2 Energy** on their first turn.
(Measured over 1200 mirrored games, first-player win rate is 50.4% — essentially even.)

### Known limitations

Honest list, so you do not get surprised:

| Limitation | Detail |
|---|---|
| **1v1 only** | No 3+ player support |
| **No reconnect** | If one side drops, the match ends |
| **LAN only** | Same WiFi/router. Cross-network needs manual port forwarding |
| **Plaintext, no password** | Anyone on the same subnet could theoretically join (first come, first served) |
| **Host is authoritative** | A cheating host cannot be stopped — but a cheating client **always gets caught** |
| **macOS firewall** | If the other side cannot connect, allow incoming connections in System Settings -> Network -> Firewall |

### Troubleshooting order

1. **Same WiFi?** — the most common cause. A phone hotspot is the most reliable test
2. **Right IP?** — the one shown on the host screen, not `127.0.0.1`
3. **Firewall** — macOS asks "allow incoming connections?" on first host; click Allow
4. **Different port** — try another if 45671 is taken
5. **Turn off VPN** — some VPNs hijack LAN traffic, breaking same-subnet connections

## Multiplayer Modes

| Mode | When to use | How |
|---|---|---|
| **LAN** | Same Wi-Fi (home, dorm, classroom) | Host opens a room, reads out the IP, friend types it |
| **Online** | Different networks, different cities | Host opens a room, gets a **4-digit code**, sends it over, friend types it |

### Online (recommended)

```
Host:   Multiplayer -> Create Online Room -> screen shows "4821"
        Send 4821 to your friend (any chat app)

Friend: Multiplayer -> Join Online Room -> type 4821 -> play
```

**No shared Wi-Fi, no IP addresses, no network configuration.**

> Online play needs a relay server (provided by the author). If it is
> unreachable, use LAN mode, or turn on a phone hotspot so both devices share
> one network.

---

## Online Security

Anyone on your LAN can reach your port, so there is a **room code**:

### How to use it

1. The host ticks **"Require room code (more secure)"**; a code appears:

   ```
   Room code: K7F2-9QMX-3BPD
   ```

2. Tell your friend the code (reading just the first groups works — 8 chars min)
3. They type it into the Join tab and connect

Leave it unticked and behaviour is unchanged (anyone can join) — fine at home.

### Protections

| Measure | Effect |
|---|---|
| **Room code** | No code, no entry — blocks strangers on the same network |
| **HMAC signing** | Every message is signed; tampering is detected and dropped |
| **Replay protection** | Re-sending the same message is rejected |
| **Auto-disconnect** | 5 failed checks in a row drops the connection |
| **8-char minimum** | Very short codes are refused, so two characters can't get in |

> Codes are **short-lived** (6 hours by default); re-host after they expire.

---

## Reconnection

A brief network hiccup (switching Wi-Fi, closing the lid) no longer kills the match:

- After a drop the host keeps the match alive for a **grace window** (60s default)
- The client retries with growing delays: `0.8s → 1.6s → 2.5s → 4s → 6s → 8s`
- Reconnect inside the window and play on; past it the match really ends

---

## Fair Play

> **Please play fair.**

**Single player**: it is your own game, play however you like.

**Ascension 20**: all assists are disabled. A pure honor challenge.

**Online**: the host is authoritative; a client cannot unilaterally change
the outcome. Any attempt to forge network messages is blocked and logged.

---

## Music / BGM

### How to add your own music (full tutorial)

The game ships **without music** (copyright). Adding songs takes three steps:

**Step 1 — Find the music folder**

The game creates it automatically on first launch:

```
~/Documents/钢铁战线/music/          (Chinese edition folder)
~/Documents/钢铁战线公开版/music/     (public edition folder)
```

> **In Finder**: menu bar "Go" -> "Home" -> `Documents` -> the game folder -> `music`
> Or press `Cmd+Shift+G` and paste the full path.

**Step 2 — Copy songs in, numbered**

Filenames must be `music1`, `music2`, `music3`... (**with an extension**):

```
music1.ogg
music2.ogg
music3.ogg
...
```

Supported formats: **`mp3` / `ogg` / `m4a` / `wav` / `aac` / `aiff` / `flac`**

> **You can mix formats** — `music1.mp3` and `music2.ogg` coexist fine.
> Note **`music10` sorts after `music2`** (numeric, not alphabetical), so up to 99 tracks are safe.

**Step 3 — Restart the game**

That is it. No configuration needed.

### Playback rules

1. **Always starts with `music1`** (every launch)
2. When a track ends -> **random** next track
3. When that ends -> random again -> **never stops**
4. Recently played tracks are avoided, so you will not hear the same song twice in a row

### FAQ

| Problem | Cause / Fix |
|---|---|
| **No sound after adding files** | 1) Is the filename exactly `music1.mp3`? 2) Did you restart? 3) Is "Enable background music" on in Settings? |
| **Replace one track** | Delete the old file, drop in the new one, keep the same name |
| **Start over** | Empty the `music/` folder and re-add |
| **Wrong order** | Check the numbers. Sorting is **numeric**: 1, 2, 3 ... 10, 11 |
| **Cannot find the music folder** | Launch the game once (it creates it), or make it manually |
| **Too loud / quiet** | Volume slider in Settings, or the system volume |

### Scene-based naming (advanced)

Besides the `music1`/`music2` radio mode, you can name by **scene** and the game
prefers those:

```
menu.*        main menu
battle.*      battle
map.*         campaign map
shop.*        supply depot / shop
event.*       events
rest.*        field hospital
reward.*      rewards
victory.*     victory
defeat.*      defeat
ambient.*     universal fallback (used when a scene has no track)
```

Examples:
- One song looping forever -> a single `ambient.mp3` is enough
- Different menu and battle music -> `menu.mp3` + `battle.mp3`

> Both modes mix: scene tracks win when present, otherwise it falls back to the
> `music1/2/3...` radio.

### Radio mode (default)

**The easiest way**: drop songs into `music/` named `music1.ogg`, `music2.ogg`...
and change nothing.

Use "◀ Previous / Next ▶" in Settings (or double-click a list entry) to skip
tracks. Toggling background music off and on **resumes the same track**, it does
not jump back to the first.

## Updating the Game

### It needs internet — but only for this

**The game itself is fully offline.** The only network request is the update
check (a few KB).

- The game checks once in the background after launch (non-blocking)
- Or check manually: **Settings -> Check for Updates**
- Offline? The check silently fails and nothing breaks

When a newer version exists, a dialog shows what was **fixed** and what was
**added**, with a button that opens the GitHub download page in your browser.

### How to update (three steps)

1. Download the new `.dmg`
2. Open it and drag the new app into **Applications** (choose Replace)
3. Done — **saves, music and achievements are all kept**

> **Your saves are not touched**: they live in `~/Documents/钢铁战线/data/`,
> outside the app bundle. Swapping the app does not affect progress.

### Cleaning up old versions

After updating, use **Settings -> Clean Up Old Versions** to remove the old app
and old installers.

- It **lists every item** with its size before deleting
- **Saves can never be deleted** (hard-coded protection)
- The version you are currently running is skipped automatically

---

## macOS First Launch: Getting Past Gatekeeper

This package is **not signed with an Apple developer certificate** (that costs
$99/year), so macOS blocks it once. Do this once and double-click works forever
after.

### Option 1: Right-click to open (fastest)

1. Open your Applications folder
2. **Right-click** (or Control-click) the app
3. Choose **Open**
4. Click **Open** again in the dialog

### Option 2: Allow it in Privacy & Security

If right-clicking does not offer Open:

1. Double-click the app. You will see "Apple could not verify ... is free of malware"
2. Click **Done**
3. Open **System Settings** -> **Privacy & Security**
4. Scroll down to the **Security** section
5. You will see a line like:
   > **"钢铁战线" was blocked because it is from an unidentified developer**
6. Click **Open Anyway** next to it
7. Enter your password / confirm with Touch ID
8. Double-click the app again and click **Open** in the dialog

### Option 3: Command line (if the above fail)

```bash
xattr -dr com.apple.quarantine /Applications/钢铁战线.app
```

Then double-click as usual.

> **No "Open Anyway" button?**
>
> That means you downloaded an **older build** (before v0.9's signing fix).
> The old bundle had a broken signature, so macOS could not identify it and
> therefore **offered no allow button at all** — the command-line method below
> is the only way for those.
>
> **Current builds have a valid signature**, so "Open Anyway" does appear.
> Please download the latest DMG.

> **Why does this happen?**
> Apple requires every app to be signed with a paid developer certificate
> ($99/year) and notarised; unsigned apps are blocked by default. This is normal
> for small open-source projects and **does not mean anything is wrong** — the
> full source is in this repository, so you can read it and build it yourself.

---

## Custom Tips

The game shows a random tip on the **main menu, while loading, on victory and on
defeat**.

**All tips live in `tips.txt` at the project root — edit it however you like.**

### Format

One tip per line. **To support both languages, separate them with `|`**:

```
Thin decks usually beat fat decks. | 薄牌组通常比厚牌组强。
Skipping an elite is a valid tactic. | 绕开打不过的精英也是战术。
```

- Chinese first, then `|`, then English
- Chinese-only is fine: the English UI falls back to the Chinese line
- Blank lines are ignored
- Lines starting with `#` are comments
- No quotes, no numbering needed
- **Restart the game to apply** — no rebuild required

### Different tips for different screens

Use section markers:

```
[菜单]   (or [menu])
main menu only

[加载]   (or [load])
loading only

[胜利]   (or [win])
victory only

[失败]   (or [lose])
defeat only
```

Tips outside any section are **general**.

Probability:

| | Chance |
|---|---|
| General tip | **50%** |
| The scene's own tips | **50%** (split evenly) |

If you only write one kind, it gets 100% — never blank.

### Where the file lives

| Situation | Location |
|---|---|
| Running from source | `tips.txt` in the project root |
| Installed from the DMG | `tips.txt` in the DMG (or next to the app) |
| Your own override | `~/Documents/钢铁战线/data/tips.txt` (highest priority) |

> If `tips.txt` is empty (or entirely commented out), a few built-in fallback
> tips are shown, so the UI is never blank.

---

## Visual Effects

| Effect | When |
|---|---|
| **Spark burst** | Card hits an enemy (bigger hit = bigger burst) |
| **Impact ring** | Expanding ring at the moment of impact |
| **Slash arc** | Extra flourish on heavy hits and kills |
| **Block effect** | Gaining cover (cool colour, distinct from damage) |
| **HQ hit** | Red sparks + screen shake when you take damage |
| **Screen fade** | Transitions between menu / map / battle |

### Performance

- All driven by `QPropertyAnimation` — **never blocks the main thread**
- Self-destructs when finished; no leaks
- Turn it all off in **Settings → battle effects & transitions**

> Disabling it changes nothing functionally — you just lose the eye candy.

---

## Save Management

Main menu -> **Save Management**. Keep as many saves as you like; each is a
separate file.

| Action | Effect |
|---|---|
| **Load** | Continue that save |
| **Rename** | Give it a name (defaults to "Act N · Floor M") |
| **Export** | Write it to a `.json` file — **you can send this to a friend** |
| **Delete** | Remove it (with confirmation) |
| **Import Save** | Pick a `.json` someone sent you |
| **Open Save Folder** | Reveal the folder in Finder |

Saves live in:

```
~/Documents/钢铁战线/data/saves/
```

A run creates its slot on **first save**; later saves update the same slot
(no endless duplicates). Saving from the map, shop, events, rest or settings all
write through.

### Sending a save to someone

1. You: Save Management -> **Export** -> save it to your Desktop
2. Send the file (it is tiny, about 18 KB)
3. They: Save Management -> **Import Save** -> pick the file

Imports are validated: corrupt files or non-save JSON are rejected, so a bad
file cannot pollute your save list.

---

## Versioning

```
0.9  →  0.9.29  →  0.9.29  →  ...  →  0.9.29  →  0.10  →  1.0
```

- **Every push bumps +0.01**
- Zero-padded numbers sort correctly (`0.9.29 < 0.9.29`), and `0.9.29`
  carries over to `0.10`
- **Major versions are manual** — jump straight to `1.0` or `1.0.0.0`
- Release script:

```bash
# small update: auto +0.01
python3 packaging/bump_version.py --auto "fixed xxx"

# major version: explicit
python3 packaging/bump_version.py --set 1.0.0.0 "official release"
```

The in-game update checker reads `version.json` at the repo root, so
`core/version.py` and `version.json` must match (the script syncs them).

---

## Project Structure

```
whale-card-battle/
├── core/            engine + data (no UI dependency)
│   ├── engine.py      battle engine
│   ├── cards.py       134 cards
│   ├── enemies.py     53 enemies
│   ├── events.py      31 events
│   ├── relics.py      52 medals
│   ├── run.py         run state, meta progress, saves
│   ├── saves.py       multi-slot save manager + import/export
│   ├── versus.py      1v1 engine
│   ├── deckbuild.py   deck builder
│   ├── netplay.py     LAN networking (stdlib sockets only)
│   ├── cheats.py      cheat codes
│   ├── audio.py       music (radio mode)
│   └── i18n.py        Chinese/English switching
├── ui/              Classic edition (Tkinter)
├── qt/              Hi-Fi edition (PyQt6)
├── locales/         translation tables
├── tests/           426 tests
├── packaging/       build scripts for .app / .dmg
└── releases/        prebuilt downloads
```

## Development / Verification

```bash
# all tests (516 cases)
python3 -m unittest discover -s tests

# engine + data smoke test
python3 main.py --selftest

# data integrity audit (phantom ids / cross-references / value sanity)
python3 selfcheck_coredata.py

# balance Monte Carlo (2000 auto-battles)
python3 -m unittest tests.test_balance -v
```

### Current status

| Item | Result |
|---|---|
| Tests | **426 passed** (3 skipped) |
| Card reference audit | 0 phantom ids |
| Headless UI tour | 17 screens, no stderr |
| Balance | Act-1 normal win rate ~100% (greedy AI) |
| Versus fairness | first player 50.6% over 500 mirrored games |
| i18n coverage | **100%** (2000 / 2000 strings) |

## About Assets

- **All art is procedural** — no image files. Every tank, soldier, icon and
  background is drawn with code (shapes, gradients, noise).
- **No audio is bundled** — for copyright reasons. See the music section above.
- **No third-party dependencies** for the Classic edition. The Hi-Fi edition
  needs only PyQt6.

## FAQ

**Does it need internet?**
No. Fully offline, including LAN multiplayer (which never leaves your network).

**Does it need Python or Qt installed?**
Not for the packaged `.dmg` — it bundles Python and Qt. Running from source needs
Python 3.9+ (PyQt6 optional, for the Hi-Fi edition).

**Where are my saves?**
`~/Documents/钢铁战线/data/` (or the `data/` folder inside the project when
running from source). Delete `save.json` to reset the current run, `meta.json`
to wipe meta progress.

**Why is the first launch blocked by Gatekeeper?**
The package is unsigned (an Apple certificate costs $99/year). Right-click the
app -> Open -> Open. Once only.

**Can I add cards / change numbers?**
Yes — everything is plain Python. Card data lives in `core/cards.py`, enemies in
`core/enemies.py`. No build step.

**I found a bug — where do I report it?**
Please file it on the [Wiki](https://github.com/d5gkmk96kj-lab/steel-frontline/wiki).
Include the version string (shown under the main menu title, e.g. `0.9.29 Beta`),
the exact steps to reproduce, and a screenshot if you have one. If the game
crashed, paste the contents of `~/Documents/钢铁战线/data/crash.log`.

**Is there a mobile version?**
No. Desktop only (macOS tested; the code is portable Python and should run on
Linux/Windows with a Python 3.9+ interpreter, though that is untested).
