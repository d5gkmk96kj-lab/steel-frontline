#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 — 主线剧情与小人物事件。

设计原则
--------
* **纯数据 + 纯函数**：不依赖 Qt、不改引擎内部状态，只通过 ``run`` 的
  公开方法加一点点数值影响。
* **反战基调**：这里没有英雄史诗。写的都是被卷进去的普通人 ——
  面包师、护士、学生、邮差、敌方的士兵。战争的残酷体现在细节里，
  而不是口号里。
* **主线和爬塔分开**：
    - 主线（story）走三幕，打完第三幕要塞 = 主线结束，给一个结局。
    - 无尽（endless）在主线通关后解锁，才是原来自在刷的那种模式。

剧情触发点
----------
``run_start``    新开一局
``act_start``    进入新一幕
``before_boss``  要塞战之前
``after_boss``   要塞战之后
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import i18n as _I18N


def _t(s: str) -> str:
    """翻译（剧情正文在 UI 层也会走一次 T.tr，这里主要给效果文本用）。"""
    try:
        return _I18N.t(s)
    except Exception:
        return s


def _f(tpl: str, **kw) -> str:
    """带占位符的翻译，便于英文版正确插值。"""
    try:
        return _I18N.fmt(tpl, **kw)
    except Exception:
        try:
            return tpl.format(**kw)
        except Exception:
            return tpl


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class StoryChoice:
    """剧情里的一个选择。"""

    label: str
    desc: str
    effect: Optional[Callable[[Any], str]] = None


@dataclass(frozen=True)
class StoryBeat:
    """一段剧情。``lines`` 逐行显示，``choices`` 为空则只有「继续」。"""

    id: str
    act: int
    trigger: str
    title: str
    lines: Tuple[str, ...]
    choices: Tuple[StoryChoice, ...] = ()
    #: True = 主线关键节点（会写进存档的进度里）
    key: bool = False


# --------------------------------------------------------------------------
# 数值效果（都很轻，剧情不是主要成长来源）
# --------------------------------------------------------------------------
def _heal(n):
    def fn(run):
        try:
            run.heal(n)
        except Exception:
            pass
        return _f("总部耐久回复 {n}。", n=n)
    return fn


def _gold(n):
    def fn(run):
        try:
            run.add_gold(n)
        except Exception:
            pass
        return _f("获得 {n} 金币。", n=n)
    return fn


def _nothing(msg):
    def fn(run):
        return msg
    return fn


def _max_hp(n):
    def fn(run):
        try:
            run.max_hp = int(run.max_hp) + n
            run.hp = int(run.hp) + n
        except Exception:
            pass
        return _f("总部耐久上限 +{n}。", n=n)
    return fn


# --------------------------------------------------------------------------
# 主线剧情
# --------------------------------------------------------------------------
#: 全文基调：战争不是荣耀，是一层层剥掉人的过程。
MAIN_STORY: Dict[str, List[StoryBeat]] = {}



# --------------------------------------------------------------------------
# 主线剧情
# --------------------------------------------------------------------------
#: 全文基调：战争不是荣耀，是一层层剥掉人的过程。
#:
#: 每一幕有 9 段：「开场」→「途中三条」→「要塞前」→「要塞后」→「间章」。
#: 全部是第一人称视角 —— 你是一个连长，从动员令贴出来那天开始，
#: 一直走到战争结束。
MAIN_STORY: Dict[str, List[StoryBeat]] = {}

# ========================= 第一幕 =========================
MAIN_STORY["run_start"] = [
    StoryBeat(
        id="prologue", act=1, trigger="run_start", key=True,
        title="第一幕 · 钢铁洪流",
        lines=(
            "动员令是在一个下雨的早晨贴出来的。",
            "纸上写着：这场战争会在圣诞节前结束。",
            "",
            "站台上挤满了人。有人在笑，有人在往车窗里塞面包。",
            "一个老太太拉着你的袖子问：我儿子什么时候回来？",
            "你说：很快就回来。",
            "",
            "你说了谎。你当时还不知道。",
        ),
        choices=(StoryChoice("登车", "开赴前线。", _nothing(_t("列车启动了。"))),),
    ),
]

MAIN_STORY["act1_mid"] = [
    StoryBeat(
        id="a1_train", act=1, trigger="act1_mid",
        title="闷罐车",
        lines=(
            "车厢是运牲口用的。四十八个人挤在一起，没有窗。",
            "有人在车厢壁上刻字，记天数。",
            "第三天的时候，那个刻字的人不刻了 —— 他说反正也数不清了。",
            "",
            "闷罐车停停走走，走了七天。",
            "中间有一次停了很久，外面有哭声。",
            "没人敢开门看。",
        ),
        choices=(
            StoryChoice("拉开车门", "看一眼。", _heal(-3)),
            StoryChoice("坐在原地", "不该看的东西就别看。", _nothing(_t("哭声持续了一个小时，然后没了。"))),
        ),
    ),
    StoryBeat(
        id="a1_first_letter", act=1, trigger="act1_mid",
        title="第一封信",
        lines=(
            "你在前线收到了第一封家信。",
            "",
            "信里说家里一切都好，邻居家的女儿订婚了，",
            "老屋后面那棵树今年结果特别多。",
            "",
            "最后一行是：",
            "「你什么时候能回来？我们都在等你。」",
            "",
            "你写回信，写了三个小时，最后只写了六个字：",
            "「我很好，勿念。」",
        ),
        choices=(
            StoryChoice("把信收进衣袋", "贴身放着。", _max_hp(2)),
            StoryChoice("原样退回", "不知道该说什么。", _nothing(_t("你把信折好，塞回了信封。"))),
        ),
    ),
    StoryBeat(
        id="a1_river", act=1, trigger="act1_mid",
        title="渡河",
        lines=(
            "渡河是在半夜进行的。",
            "",
            "工兵搭好了浮桥，部队一个接一个过去。",
            "有人掉进水里，没人敢喊 —— 会暴露位置。",
            "",
            "你听见水里有人扑腾的声音，然后是 silence。",
            "",
            "天亮后，你数的数少了三个人。",
            "名册上他们被记成「渡河失踪」。",
        ),
        choices=(
            StoryChoice("记下名字", "你记住了三个名字。", _max_hp(2)),
            StoryChoice("按流程上报", "该走的程序走。", _nothing(_t("报表递上去了。"))),
        ),
    ),
]

MAIN_STORY["before_boss"] = [
    StoryBeat(
        id="a1_boss", act=1, trigger="before_boss", key=True,
        title="要塞之前",
        lines=(
            "要塞在河对岸。天还没亮，你听到那边有人在唱歌。",
            "是敌人的歌。你听不懂词，但调子和你们的一样。",
            "",
            "副官问：要开炮吗？",
            "你说：等一等。",
            "",
            "歌声停了。然后你听到有人在哭。",
            "你没让副官开炮。你也没让他停手。",
            "",
            "—— 半小时后，炮击开始了。",
        ),
        choices=(StoryChoice("下令进攻", "要塞必须拿下。", _nothing(_t("你举起了手。"))),),
    ),
]

MAIN_STORY["after_boss"] = [
    StoryBeat(
        id="a1_after", act=1, trigger="after_boss", key=True,
        title="阵地上没有胜利者",
        lines=(
            "要塞拿下来了。旗子换了一面。",
            "",
            "你走过战壕，看到两个士兵并排躺着 —— 一个你们的，一个他们的。",
            "两个人的手都伸向同一个方向。",
            "你想知道那里有什么。你走过去，发现是一只掉落的水壶。",
            "",
            "水壶是空的。",
            "",
            "副官过来报告伤亡数字。你听不清。",
            "你只记得动员令上那句话：圣诞节前就能回家。",
            "离圣诞节还有八个月。",
        ),
        choices=(StoryChoice("继续前进", "战争还没结束。", _nothing(_t("你站了起来。"))),),
    ),
]

MAIN_STORY["act1_end"] = [
    StoryBeat(
        id="a1_rest", act=1, trigger="act1_end",
        title="休整",
        lines=(
            "部队在要塞后面的村子里休整三天。",
            "",
            "村民们回来了。他们看你们的眼神很奇怪，",
            "不像是看救星，也不像是看敌人。",
            "像是看一场没完的灾。",
            "",
            "有个老汉给了你一壶酒。你问多少钱。",
            "他摆摆手说：不要钱。你们还要去打下一个地方吧？",
            "",
            "你说：是。",
            "他说：那下下个呢？",
            "",
            "你没回答。",
        ),
        choices=(
            StoryChoice("喝了这壶酒", "很多天没喝过酒了。", _heal(8)),
            StoryChoice("收下但不喝", "留着。", _max_hp(3)),
        ),
    ),
]

# ========================= 第二幕 =========================
MAIN_STORY["act_start@2"] = [
    StoryBeat(
        id="a2_start", act=2, trigger="act_start", key=True,
        title="第二幕 · 焦土",
        lines=(
            "你们进入一座城市。",
            "地图上有它的名字，路牌已经没有了。",
            "",
            "街角有一家面包店，橱窗碎了，里面还剩十几个面包。",
            "面包已经硬得咬不动。但没有人拿。",
            "",
            "有人在墙上用粉笔写了一个日期，和一句话：",
            "「我们在这里，直到最后。」",
            "",
            "日期是三个月前。",
        ),
        choices=(StoryChoice("继续推进", "城市还要往前打。", _nothing(_t("你穿过了空无一人的街道。"))),),
    ),
]

MAIN_STORY["act2_mid"] = [
    StoryBeat(
        id="a2_well", act=2, trigger="act2_mid",
        title="水井",
        lines=(
            "城里唯一的干净水源是一口井。",
            "",
            "井边围了很多人 —— 有我们的人，也有被留下的人。",
            "谁也不说话，排成一列，一个一个地打水。",
            "",
            "轮到一个老婆婆的时候，她的桶掉进井里了。",
            "有个士兵二话不说，把自己的水倒进了她的桶。",
            "",
            "然后他重新排队，排到队尾。",
            "没有人插队，没有人说谢谢。",
            "",
            "那天下午的水很凉。",
        ),
        choices=(
            StoryChoice("也去排队", "你也渴了。", _heal(6)),
            StoryChoice("留在原地", "看着就好。", _nothing(_t("你看着他们一个一个地打完水。"))),
        ),
    ),
    StoryBeat(
        id="a2_piano", act=2, trigger="act2_mid",
        title="钢琴",
        lines=(
            "一栋被炸塌的房子里，露出一架钢琴。",
            "",
            "琴键还在。有点跑调。",
            "",
            "有个兵坐下去弹了一首。你听不出是什么曲子，",
            "但所有人都安静下来了。",
            "",
            "弹到一半，他停住了。",
            "他说：剩下的我忘了。",
            "",
            "有人喊：那你就重新弹。",
            "他真的重新弹了一遍，还是弹到一半停下。",
            "",
            "后来炮击开始了，大家散了。",
        ),
        choices=(
            StoryChoice("留下来听", "再听一遍。", _heal(7)),
            StoryChoice("去指挥所", "还有正事。", _nothing(_t("你转身走了。琴声还在响。"))),
        ),
    ),
    StoryBeat(
        id="a2_food", act=2, trigger="act2_mid",
        title="分粮",
        lines=(
            "补给终于到了。比预计晚了十一天。",
            "",
            "粮食不够分。参谋说按人头分，每人一份。",
            "你说：先给伤员。",
            "",
            "有人说这样不公。",
            "你说：公平是指每个人都能活下去，不是每人一块饼。",
            "",
            "最后每个人都分到了，只是伤员多一点。",
            "你那份，你给了旁边一个冻得发抖的小兵。",
        ),
        choices=(
            StoryChoice("照这样办", "不公平，但公道。", _max_hp(4)),
            StoryChoice("按人数均分", "遵守规则。", _nothing(_t("每个人都拿到了同样的份量。")))
        ),
    ),
]

MAIN_STORY["before_boss@2"] = [
    StoryBeat(
        id="a2_boss", act=2, trigger="before_boss", key=True,
        title="巷战之前",
        lines=(
            "下一个要塞在市区中心。侦察兵说里面还有平民。",
            "",
            "参谋摊开地图，用红笔圈出覆盖范围：",
            "「按标准程序，这里、这里、还有这里，都要炮火覆盖。」",
            "",
            "你看着那片红色。红色的边界里有一所学校和一间医院。",
            "你知道医院的位置 —— 上一场战斗里，你的伤员就是在那里救的。",
            "",
            "参谋问：标准程序？",
            "你没有立刻回答。",
        ),
        choices=(
            StoryChoice("按标准程序", "这是战争。", _nothing(_t("你点了头。"))),
            StoryChoice("绕开医院", "多打两天，但医院不动。", _max_hp(5)),
        ),
    ),
]

MAIN_STORY["after_boss@2"] = [
    StoryBeat(
        id="a2_after", act=2, trigger="after_boss", key=True,
        title="清理",
        lines=(
            "城里安静下来了。",
            "",
            "清理队在做他们的事 —— 一具一具抬，一个一个登记。",
            "有人在登记本上写：无名，男，约二十岁。",
            "同一个人，写了很多页。",
            "",
            "你在一间被掀掉屋顶的房子里，看到黑板上还留着算术题。",
            "「3 + 5 = __」",
            "",
            "下面有铅笔写的小字：我知道了，是 8。",
            "字迹很用力，笔尖把黑板划出了白痕。",
        ),
        choices=(StoryChoice("合上门", "继续。", _nothing(_t("你把门轻轻带上了。"))),),
    ),
]

MAIN_STORY["act2_end"] = [
    StoryBeat(
        id="a2_burial", act=2, trigger="act2_end",
        title="埋葬",
        lines=(
            "阵亡的人要埋。",
            "",
            "挖坑的时候遇到石头，进度很慢。",
            "有个兵挖着挖着停下来，说：这个坑太浅了。",
            "排长说：够深了，够了。",
            "",
            "那个兵还是又挖了半个小时。",
            "",
            "填土的时候，大家都往里面扔东西 —— 一枚子弹壳、",
            "半块巧克力、一张照片、一个烟盒。",
            "",
            "你不知道这个土坑里躺着的是谁。",
            "你只知道他们昨天还站着。",
        ),
        choices=(
            StoryChoice("也扔一样东西", "扔进你的军牌。", _max_hp(5)),
            StoryChoice("站着看完", "不扔什么。", _nothing(_t("最后一把土盖上去了。"))),
        ),
    ),
]

# ========================= 第三幕 =========================
MAIN_STORY["act_start@3"] = [
    StoryBeat(
        id="a3_start", act=3, trigger="act_start", key=True,
        title="第三幕 · 最后一冬",
        lines=(
            "第三个冬天。",
            "",
            "新兵越来越年轻，老兵越来越少。",
            "补给车已经两个月没有准时到过。",
            "",
            "有人开始把家信叠成小方块，缝进衣领 —— 说是这样炮弹就打不中。",
            "你知道这不灵。你没说。",
            "",
            "夜里有人冻死了。早上点名的时候，排长会多喊一遍那个名字。",
            "然后沉默一会儿，喊下一个。",
        ),
        choices=(StoryChoice("继续行军", "还有下一个要塞。", _nothing(_t("雪一直在下。"))),),
    ),
]

MAIN_STORY["act3_mid"] = [
    StoryBeat(
        id="a3_boots", act=3, trigger="act3_mid",
        title="一双鞋",
        lines=(
            "你的靴子破了。第三次。",
            "",
            "补给里没有新靴子。你只好用布条绑住。",
            "",
            "某个早晨，一个兵把自己的一双鞋放在你帐篷门口。",
            "你问他为什么。",
            "",
            "他说：长官，我可能用不上了。",
            "",
            "你问他什么意思。他笑了笑说没事。",
            "",
            "三天后，他的名字出现在名单上。",
            "那双鞋你一直没穿。",
        ),
        choices=(
            StoryChoice("穿上那双鞋", "他会希望这样。", _max_hp(4)),
            StoryChoice("收进行囊", "留着。", _heal(3)),
        ),
    ),
    StoryBeat(
        id="a3_hospital", act=3, trigger="act3_mid",
        title="最后一个护士",
        lines=(
            "野战医院只剩下两个护士了。",
            "",
            "其中一个是从第二幕开始就在的。她的名字你已经听过很多次 ——",
            "伤员们都在传：那个瘦瘦的、讲话很轻的女的。",
            "",
            "她还在换绷带。她的动作还是那么稳。",
            "只是她现在说话越来越少了。",
            "",
            "你问她需要什么。",
            "她说：止痛药。然后又说：不是给他们的，是给我自己的。",
            "",
            "你什么也没说，把自己那瓶给了她。",
        ),
        choices=(
            StoryChoice("把止痛药给她", "她也需要。", _heal(8)),
            StoryChoice("留着给伤员", "她还能撑。", _nothing(_t("她把药推了回来。"))),
        ),
    ),
    StoryBeat(
        id="a3_letters", act=3, trigger="act3_mid",
        title="遗书",
        lines=(
            "每个人都要写遗书。这是规定。",
            "",
            "大部分人不写。或者写了塞在兜里，从不交上来。",
            "",
            "你收到一封信 —— 是一个昨天刚阵亡的兵的家属寄来的。",
            "信里问：他最近怎么样？",
            "",
            "你拿起笔，写：他很好，一切平安。",
            "然后你停了很久。",
            "",
            "最后你把这张纸撕了，重新写：",
            "「他走的时候没有痛苦。我们都在他身边。」",
            "",
            "这句话有一半是真的。",
        ),
        choices=(
            StoryChoice("把信寄出去", "至少让他家人好过一点。", _max_hp(3)),
            StoryChoice("按实际情况写", "真相比安慰更重要。", _nothing(_t("你写了三页纸。"))),
        ),
    ),
]

MAIN_STORY["before_boss@3"] = [
    StoryBeat(
        id="a3_boss", act=3, trigger="before_boss", key=True,
        title="最后的防线",
        lines=(
            "这是最后一个要塞。",
            "",
            "对面也是这么想的 —— 他们把所有的东西都堆在了这里。",
            "情报说，那里的守军已经换过四批，最后一批连名字都没登记。",
            "",
            "你的副官 —— 从开战第一天就跟着你的那个 —— 昨天没回来。",
            "他的位置现在站着一个十九岁的通讯兵。",
            "",
            "通讯兵问：长官，打完这一仗是不是就结束了？",
            "",
            "这一次，你想了想，没有骗他。",
        ),
        choices=(StoryChoice("准备进攻", "最后一次。", _nothing(_t("雪停了。"))),),
    ),
]

MAIN_STORY["after_boss@3"] = [
    StoryBeat(
        id="ending", act=3, trigger="after_boss", key=True,
        title="结束",
        lines=(
            "要塞陷落了。",
            "",
            "没有欢呼。没有号角。",
            "活着的人只是坐在废墟上，谁也没有说话。",
            "",
            "有人开始抽烟。有人开始翻口袋找家信。",
            "有个兵忽然哭了起来，没人问为什么，也没人劝他。",
            "",
            "你走进要塞的指挥室。桌上摊着一张地图，",
            "和我们的一模一样。",
            "上面也画满了红色的圈，圈里也有学校、医院、还有墓地。",
            "",
            "两边的人，做的是同一件事。",
            "",
            "—— 战争结束了。",
            "但没有人是赢家。",
            "",
            "后来你才知道，动员令上的那句话，",
            "两边都写过。",
            "",
            "「圣诞节前就能回家。」",
        ),
        choices=(StoryChoice("离开指挥室", "无尽模式已解锁。", _nothing(_t("你走出去了。"))),),
    ),
]

MAIN_STORY["act3_end"] = [
    StoryBeat(
        id="a3_after_war", act=3, trigger="act3_end",
        title="战后",
        lines=(
            "战争结束的消息是下午到的。",
            "",
            "广播里念了一份名单 —— 阵亡者名单。念了两个小时。",
            "所有人站着听。没有人坐下。",
            "",
            "念完之后，有人问：这就完了？",
            "",
            "没有人回答。",
            "",
            "后来你去领退伍文件。办事员问你：",
            "「战争期间你做过什么？」",
            "",
            "你张了张嘴，发现自己什么也说不出来。",
            "",
            "最后你说：我活下来了。",
            "",
            "办事员点点头，盖了个章。",
        ),
        choices=(
            StoryChoice("走出大楼", "外面在下雨。", _nothing(_t("雨和开战那天一样大。"))),
        ),
    ),
]


# --------------------------------------------------------------------------
# 小人物特写（TFR 式事件）
# --------------------------------------------------------------------------
#: 这些是**可选**的插入事件，出现在普通的事件节点上。
#: 每一段都是一个普通人的一小块人生，没有英雄，只有战争碾过去的样子。
VIGNETTES: List[StoryBeat] = [
    StoryBeat(
        id="vg_bakery", act=1, trigger="event",
        title="面包店",
        lines=(
            "部队征用了一家面包店做临时指挥所。",
            "老板站在门口，看着士兵把炉子拆掉搬走。他没有说话。",
            "",
            "后来你才知道，那炉子是他爷爷传下来的，",
            "用了六十年，烤过三代人的面包。",
            "",
            "他最后问了一句：炉子以后还能还给我吗？",
            "没人回答他。",
        ),
        choices=(
            StoryChoice("给他一张征用凭据", "至少有个凭证。", _gold(-20)),
            StoryChoice("什么也不说", "战争不需要解释。", _nothing(_t("他没有再问。"))),
        ),
    ),
    StoryBeat(
        id="vg_nurse", act=1, trigger="event",
        title="战地医院",
        lines=(
            "你在野战医院待了一夜。",
            "",
            "有个护士一直在换绷带，从傍晚换到天亮。",
            "她说她已经三天没睡了。",
            "",
            "早上，一个伤员停止了呼吸。她按流程记录，盖上白布，",
            "然后走到下一个床边。",
            "",
            "你问她：你记得住每一个人的脸吗？",
            "她说：记得住。所以才睡不着。",
        ),
        choices=(
            StoryChoice("留下来帮她", "你也会包扎。", _heal(8)),
            StoryChoice("返回指挥所", "你还有别的仗要打。", _nothing(_t("你走了。她还在换绷带。"))),
        ),
    ),
    StoryBeat(
        id="vg_student", act=1, trigger="event",
        title="十八岁",
        lines=(
            "补充兵到了。有个孩子背着枪，比枪还矮一点。",
            "",
            "登记的时候，他说自己十九岁。",
            "手在抖，把出生年份写错了两次。",
            "",
            "你认出他是镇上中学的学生 —— 你见过他在车站卖报纸。",
            "那时候他十五岁。",
            "",
            "你什么也没说，在登记表上签了字。",
        ),
        choices=(
            StoryChoice("把他调去后勤", "至少不用上前线。", _max_hp(-3)),
            StoryChoice("按编制分配", "每个人都一样。", _nothing(_t("他去了前线。"))),
        ),
    ),
    StoryBeat(
        id="vg_refugee", act=2, trigger="event",
        title="逃难的人",
        lines=(
            "路上遇到一队逃难的人。",
            "",
            "一个母亲抱着孩子，孩子的鞋掉了一只。",
            "她问：前面还有军队吗？",
            "",
            "你说有。",
            "她又问：那后面呢？",
            "",
            "你不知道怎么回答。",
            "",
            "她抱着孩子继续往前走了。孩子的另一只鞋在泥里，",
            "没有人捡。",
        ),
        choices=(
            StoryChoice("给她一些口粮", "能撑几天。", _gold(-15)),
            StoryChoice("让开道路", "你们继续前进。", _nothing(_t("你们朝相反的方向走了。"))),
        ),
    ),
    StoryBeat(
        id="vg_enemy_pocket", act=2, trigger="event",
        title="敌人的口袋",
        lines=(
            "清理战场的时候，有人翻出了一个敌人的钱包。",
            "",
            "里面没有钱。",
            "有一张照片：一个女人，两个孩子，背景是一间木头房子。",
            "背面写着一行字，是他们的文字。",
            "",
            "翻译说：",
            "「等我回来，我们去河边。」",
            "",
            "照片上的人笑得很开心。",
            "",
            "有人问钱包怎么处理。",
            "你说：寄回去。",
            "问题是，没有人知道该寄到哪里。",
        ),
        choices=(
            StoryChoice("把照片收进衣袋", "你带走了它。", _max_hp(3)),
            StoryChoice("放回原处", "留在原地。", _nothing(_t("你把它放了回去。"))),
        ),
    ),
    StoryBeat(
        id="vg_postman", act=2, trigger="event",
        title="邮差",
        lines=(
            "前线来了一批邮件。",
            "",
            "大部分是家里寄来的 —— 毛衣、糖、还有晒干的烟叶。",
            "邮差说，也有往家里寄的，但是寄不出去。",
            "",
            "他把一叠信封放在桌上：这都是之前阵亡的战友写的。",
            "地址都还清楚。",
            "",
            "他问：要不要帮忙送？",
            "",
            "按规定，不送。",
            "但他已经送了 —— 他说他每个月都自己掏钱买邮票。",
        ),
        choices=(
            StoryChoice("给他一些钱买邮票", "至少这个能帮。", _gold(-10)),
            StoryChoice("按规定办", "规定就是规定。", _nothing(_t("他把信收了回去。"))),
        ),
    ),
    StoryBeat(
        id="vg_cat", act=2, trigger="event",
        title="战壕里的猫",
        lines=(
            "战壕里住着一只猫。",
            "",
            "没人知道它是从哪来的。可能是从城里跑出来的。",
            "士兵们把自己那份罐头分一点给它。它不挑。",
            "",
            "它只在炮击的时候躲进洞里，其他时候就蹲在沙袋上晒太阳。",
            "",
            "有个兵说：它比我们命大。",
            "另一个说：不，它只是不在乎。",
            "",
            "后来有一天，炮击之后，猫没回来。",
            "有人在战壕外面找了很久。",
            "没有人说话。",
        ),
        choices=(
            StoryChoice("继续找", "浪费时间，但你还是去了。", _heal(5)),
            StoryChoice("当没这回事", "战争里死掉的东西太多了。", _nothing(_t("你转身回去了。"))),
        ),
    ),
    StoryBeat(
        id="vg_blackboard", act=2, trigger="event",
        title="黑板",
        lines=(
            "一间被炸掉半边的教室。",
            "",
            "黑板还挂在墙上。上面写着：",
            "「今天作业：写一篇作文，题目是《我的理想》」",
            "",
            "下面的课桌上，散着一叠作文本。",
            "最上面那本，翻开着。上面只写了两行：",
            "",
            "「我的理想是当老师。因为老师可以教别人。」",
            "「可是老师说，今年可能没有暑假了。」",
            "",
            "后面的字迹被雨水泡烂了。",
        ),
        choices=(
            StoryChoice("把作文本收好", "带走了一本。", _max_hp(2)),
            StoryChoice("原样放回去", "不该打扰。", _nothing(_t("你轻轻退了出去。"))),
        ),
    ),
    StoryBeat(
        id="vg_truce", act=3, trigger="event",
        title="停火的十分钟",
        lines=(
            "那一夜，对面的枪声停了。",
            "",
            "战壕里的人都醒了。有人以为要进攻，端起了枪。",
            "",
            "然后对面传来声音 —— 有人在唱歌。",
            "过了一会儿，居然有人跟着哼起来，然后是笑。",
            "",
            "两边的战壕里都有人在笑。笑得很累，但确实在笑。",
            "",
            "二十分钟后，双方都恢复了原状。",
            "第二天早上，炮击照旧。",
            "",
            "但你记得那二十分钟。",
            "那时候没有人是敌人。",
        ),
        choices=(
            StoryChoice("把这件事写进战报", "没人会信。", _nothing(_t("你还是写了。"))),
            StoryChoice("什么都不写", "有些事不该进档案。", _max_hp(4)),
        ),
    ),
    StoryBeat(
        id="vg_dogtags", act=3, trigger="event",
        title="狗牌",
        lines=(
            "你收到一个任务：把阵亡者的身份牌收集起来。",
            "",
            "有个新兵跟着你做。他做得很快，一直到某一块牌子。",
            "他停下来，蹲在原地很久。",
            "",
            "你走过去看。牌子上是他哥哥的名字。",
            "",
            "他早就知道哥哥阵亡了 —— 家里写过信。",
            "他说：我以为已经有人捡过了。",
            "",
            "两个人都没有动。风很大。",
        ),
        choices=(
            StoryChoice("陪他站一会儿", "不差这二十分钟。", _heal(6)),
            StoryChoice("让他单独待着", "这种时候，多半想一个人。", _nothing(_t("你走开了，回头看见他还蹲着。"))),
        ),
    ),
    StoryBeat(
        id="vg_soup", act=3, trigger="event",
        title="最后一罐汤",
        lines=(
            "补给已经三天没到。",
            "",
            "炊事班找到一罐罐头，煮了一锅汤。",
            "每人一勺，正好分完。",
            "",
            "最后轮到一个人，锅里没了。",
            "炊事兵愣了一下，把自己那碗递过去。",
            "对方摇头，说：你比我大。",
            "",
            "两个人推来推去。最后谁也没喝，把碗放在了中间。",
            "",
            "第二天，两个人都没醒来。",
            "汤还在那里，冻住了。",
        ),
        choices=(
            StoryChoice("给他们登记", "写上名字。", _heal(4)),
            StoryChoice("继续赶路", "还有下一个要塞。", _nothing(_t("雪把碗埋了。"))),
        ),
    ),
    StoryBeat(
        id="vg_scarecrow", act=3, trigger="event",
        title="稻草人",
        lines=(
            "田野里立着一个稻草人。",
            "",
            "它的衣服是军装的旧布，帽子是士兵的帽子。",
            "显然是有人把自己的东西给了一个稻草人。",
            "",
            "不知道为什么，没有一棵庄稼。",
            "",
            "也许是因为种地的人都不在了。",
            "也许是因为，给稻草人穿衣服的人，只是想证明",
            "这里曾经有人生活过。",
        ),
        choices=(
            StoryChoice("给稻草人敬个礼", "你也说不清为什么。", _max_hp(3)),
            StoryChoice("走过去", "只是路过。", _nothing(_t("你没有回头。"))),
        ),
    ),
    # ---- 新增 8 段 ----
    StoryBeat(
        id="vg_clock", act=1, trigger="event",
        title="钟表匠",
        lines=(
            "部队路过一间钟表店。店门开着，里面没有人。",
            "",
            "柜台上摆着几十只钟，全都停在同一个时间。",
            "不是被炸停的 —— 是主人走之前，把每一只都停在了同一刻。",
            "",
            "柜台后面有一张字条，用两种语言写着：",
            "「请勿拨动。谢谢。」",
            "",
            "有个兵想拿一只走。你把他的手按住了。",
            "",
            "那一天后来被记进了战报：在钟表店附近遭遇敌军。",
            "时间：下午三点十七分。",
        ),
        choices=(
            StoryChoice("把钟都留着", "不拨动。", _max_hp(2)),
            StoryChoice("让士兵自己决定", "你管不了这么多。", _nothing(_t("最后少了两只。"))),
        ),
    ),
    StoryBeat(
        id="vg_wedding", act=2, trigger="event",
        title="婚礼",
        lines=(
            "部队进城的时候，正好赶上一场婚礼。",
            "",
            "新娘穿着借来的白裙子，裙摆上有一块是灰色的布。",
            "新郎不是军人，是个木匠 —— 他的手很粗糙，拿戒指的时候在抖。",
            "",
            "神父没有来。有个人拿了一本书代念。",
            "",
            "他们交换戒指的时候，远处传来炮声。",
            "所有人都停了一下。",
            "",
            "然后新郎说：继续。",
            "",
            "婚礼继续了。没有人哭。",
        ),
        choices=(
            StoryChoice("站在外面看完", "不打扰。", _heal(6)),
            StoryChoice("让人送一束花", "院子里的花还开着。", _gold(-10)),
        ),
    ),
    StoryBeat(
        id="vg_well_child", act=1, trigger="event",
        title="井边的孩子",
        lines=(
            "你在一个村子里看到一口井，井边坐着一个孩子。",
            "",
            "孩子大概六七岁，抱着膝盖，一动不动。",
            "你走过去问：你在等谁？",
            "",
            "他说：等我妈。",
            "你问：她去哪了？",
            "他说：她说去买菜。",
            "",
            "这个村子已经三天没有商店了。",
            "",
            "你在旁边坐了一会儿，然后走了。",
            "你没有告诉他什么。",
        ),
        choices=(
            StoryChoice("给他留点吃的", "留下你的干粮。", _gold(-8)),
            StoryChoice("什么都不说", "你也没有答案。", _nothing(_t("你的脚步声很响。"))),
        ),
    ),
    StoryBeat(
        id="vg_letters_never_sent", act=3, trigger="event",
        title="没寄出的信",
        lines=(
            "清理一间掩体的时候，你发现一叠信。",
            "",
            "都是写给同一个人的，同一个地址。",
            "一封都没寄出去。",
            "",
            "第一封写着：「我很好，别担心。」",
            "第五封写着：「这里很冷。」",
            "第九封只写了三个字：「我想回家。」",
            "",
            "日期从去年的三月一直排到上个月。",
            "",
            "最后一封没有写完。",
            "停在一句话的中间 ——「等这一切结束，我们就……」",
        ),
        choices=(
            StoryChoice("把信收起来", "你带走了它们。", _max_hp(3)),
            StoryChoice("留在原处", "这里已经是结尾了。", _nothing(_t("你把信放回了原来的位置。"))),
        ),
    ),
    StoryBeat(
        id="vg_river_boys", act=2, trigger="event",
        title="河边的男孩",
        lines=(
            "休整的时候，你在河边看到几个男孩在游泳。",
            "",
            "他们笑得很响。其中一个跳到水里，溅起很高的水花。",
            "",
            "你不自觉地笑了。这是这个月第一次。",
            "",
            "然后你注意到——河的对面，也有男孩在游泳。",
            "",
            "他们也在笑。",
            "",
            "两边隔着一条不到五十米的河。",
            "没有任何人往对面看。",
        ),
        choices=(
            StoryChoice("继续看", "难得。", _heal(9)),
            StoryChoice("转身走了", "不该看。", _nothing(_t("你听见笑声一直在身后。"))),
        ),
    ),
    StoryBeat(
        id="vg_stove", act=1, trigger="event",
        title="炉子",
        lines=(
            "冬天到了，所有人都围着同一只炉子。",
            "",
            "炉子是从一户人家搬来的。搬走的时候女主人一直在哭，",
            "但没有人问为什么。",
            "",
            "有天晚上，一个兵说：这炉子真好用。",
            "另一个说：这炉子烤面包的。",
            "",
            "沉默了很久。",
            "",
            "然后有个人说：那以后我们用它烤面包吧。",
            "",
            "没有人笑。也没有人说话。",
            "后来那个炉子一直烧到战争结束。",
        ),
        choices=(
            StoryChoice("把炉子还回去", "找到那户人家。", _gold(-12)),
            StoryChoice("留下来取暖", "这个冬天太冷了。", _heal(7)),
        ),
    ),
    StoryBeat(
        id="vg_photograph", act=2, trigger="event",
        title="合影",
        lines=(
            "有人提议拍一张合影。",
            "",
            "摄影师是从城里找来的。他说他没有胶卷了。",
            "后来从一个阵亡的敌军通讯员身上找到一卷。",
            "",
            "所有人站好。排长说：笑一笑。",
            "",
            "没有人笑得出来。",
            "",
            "最后照片洗出来，二十三个人，二十二个在笑。",
            "只有一个没笑 —— 他在看镜头外的地方。",
            "",
            "那个人是你。",
        ),
        choices=(
            StoryChoice("留下这张照片", "塞进衣袋。", _max_hp(4)),
            StoryChoice("烧掉它", "有些脸不想记住。", _nothing(_t("火苗很小，但够了。"))),
        ),
    ),
    StoryBeat(
        id="vg_end_house", act=3, trigger="event",
        title="最后一户人家",
        lines=(
            "这片区域只剩下最后一户人家还亮着灯。",
            "",
            "你敲门。开门的是一个老头，他说他哪儿也不去。",
            "",
            "你问他为什么不走。",
            "他说：我在这里住了一辈子。树是我种的，房子是我盖的。",
            "",
            "你告诉他明天这里要打起来。",
            "",
            "他说：那你们打吧。打完我再修房子。",
            "",
            "第二天，那片地方被炮火覆盖了。",
            "第三天，你路过，看到他真的在修。",
        ),
        choices=(
            StoryChoice("帮他捡砖头", "你还有一小时。", _heal(10)),
            StoryChoice("继续前进", "修不好的。", _nothing(_t("你回头看了一眼。"))),
        ),
    ),
]


# --------------------------------------------------------------------------
# 查询
# --------------------------------------------------------------------------
#: 主线只有这三幕
STORY_MAX_ACT = 3


def beats_for(trigger: str, act: int) -> List[StoryBeat]:
    """取某个触发点、某一幕要播的剧情（按定义顺序）。"""
    out: List[StoryBeat] = []
    # 通用触发（不限幕）
    for b in MAIN_STORY.get(trigger, ()):
        if b.act == act:
            out.append(b)
    # 幕专属触发（"act_start@2" 这种）
    for b in MAIN_STORY.get("%s@%d" % (trigger, act), ()):
        out.append(b)
    return out


def next_beat_from_key(key: str,
                       seen: Optional[set] = None) -> Optional[StoryBeat]:
    """从 ``act1_mid`` / ``act3_end`` 这种键里取第一条没看过的。"""
    seen = seen or set()
    for b in MAIN_STORY.get(str(key), ()):
        if b.id not in seen:
            return b
    return None


def next_beat(trigger: str, act: int,
              seen: Optional[set] = None) -> Optional[StoryBeat]:
    """取第一条**还没看过**的剧情；没有就返回 None。"""
    seen = seen or set()
    for b in beats_for(trigger, act):
        if b.id not in seen:
            return b
    return None


def ending_beat() -> Optional[StoryBeat]:
    for b in MAIN_STORY.get("after_boss@3", ()):
        if b.id == "ending":
            return b
    return None


def all_vignettes() -> List[StoryBeat]:
    return list(VIGNETTES)


def random_vignette(rng, seen: Optional[set] = None) -> Optional[StoryBeat]:
    """随机挑一段没看过的小人物特写。"""
    seen = seen or set()
    pool = [v for v in VIGNETTES if v.id not in seen]
    if not pool:
        return None
    try:
        return rng.choice(pool)
    except Exception:
        return pool[0]


def total_beats() -> int:
    n = sum(len(v) for v in MAIN_STORY.values())
    return n


def story_progress(seen: Optional[set] = None) -> Tuple[int, int]:
    """返回 (已看主线数量, 总数)。"""
    seen = seen or set()
    ids = [b.id for beats in MAIN_STORY.values() for b in beats]
    got = sum(1 for i in ids if i in seen)
    return got, len(ids)
