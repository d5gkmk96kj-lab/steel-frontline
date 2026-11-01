#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新手教程：一场被打过招呼的简单战斗。

设计
----
* **纯数据 + 纯状态机**：不依赖 Qt，单测可以直接跑。
* 教程就是一场真实战斗 —— 不是幻灯片。玩家从第一秒就在用真正的界面，
  只是旁边有一条提示带告诉他要做什么。
* 步骤按「玩家做了什么」推进，不按时间推进：点了牌才进下一步，
  所以手快的玩家不会被卡，手慢的也不会被催。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


#: 教程专用卡组：全是基础牌，没有花里胡哨的效果
TUTORIAL_DECK = [
    "strike", "strike", "strike",
    "defend", "defend", "defend",
    "strike", "defend",
]

#: 教程敌人：固定一个很弱的，保证新手打得过
TUTORIAL_ENCOUNTER = {
    "kind": "normal",
    "enemies": ["deep_crab"],
    "name": "训练靶标",
    "tutorial": True,
}


@dataclass
class Step:
    """教程的一步。"""

    id: str
    text: str
    #: 触发下一步的事件类型：play_attack / play_skill / end_turn /
    #: enemy_acted / battle_end
    wait_for: str
    #: 完成这一步后显示的一句反馈（空 = 不显示）
    done_text: str = ""


#: 教程步骤表。顺序就是教学顺序。
STEPS: List[Step] = [
    Step(
        "welcome",
        "欢迎来到钢铁战线。这一局是你的训练场，不会真的失败。\n"
        "先点一张「攻击」牌 —— 就是下面带红边的那些。",
        "play_attack",
        "很好。出牌会消耗左边的补给，每回合会重新回满。",
    ),
    Step(
        "defend",
        "再打一张「防御」牌（绿边），它会给总部加上掩体。\n"
        "掩体可以挡住伤害，每回合开始会清空。",
        "play_skill",
        "掩体挡住了伤害。注意：它不累积，下回合会清掉。",
    ),
    Step(
        "end_turn",
        "牌打得差不多了，按 空格（或点右下角「结束回合」）结束你的回合。",
        "end_turn",
        "现在轮到对面了。看它头顶的图标 —— 那是它下回合要用的招。",
    ),
    Step(
        "intent",
        "敌人头顶的数字就是它下回合要打你的伤害。\n"
        "看到大数字就要提前堆掩体，或者先把输出打出去。",
        "enemy_acted",
        "",
    ),
    Step(
        "finish",
        "打掉它就能完成教程。之后主线的三幕战役在等你。\n"
        "（随时可以按 Esc 离开。）",
        "battle_end",
        "",
    ),
]


class Coach:
    """教程推进器：记录当前步骤，按事件前进。"""

    def __init__(self, steps: Optional[List[Step]] = None):
        self.steps: List[Step] = list(steps if steps is not None else STEPS)
        self.index = 0
        self.done = False
        self._feedback = ""

    # -- 查询 -----------------------------------------------------------
    @property
    def current(self) -> Optional[Step]:
        if self.done or self.index >= len(self.steps):
            return None
        return self.steps[self.index]

    @property
    def text(self) -> str:
        s = self.current
        if s is None:
            return ""
        if self._feedback:
            return self._feedback + "\n\n" + s.text
        return s.text

    @property
    def progress(self) -> str:
        """「第 2 / 5 步」这种。"""
        if self.done:
            return "教程完成"
        return "第 %d / %d 步" % (min(self.index + 1, len(self.steps)),
                                 len(self.steps))

    # -- 推进 -----------------------------------------------------------
    def notify(self, event: str) -> bool:
        """告诉教程「玩家做了 event」。返回 True 表示步骤确实前进了。"""
        s = self.current
        if s is None:
            return False
        if s.wait_for != event:
            return False
        self._feedback = s.done_text or ""
        self.index += 1
        if self.index >= len(self.steps):
            self.done = True
        return True

    def advance(self) -> None:
        """手动跳过一步（给「我知道了」按钮用）。"""
        if self.current is not None:
            self._feedback = ""
            self.index += 1
            if self.index >= len(self.steps):
                self.done = True

    def reset(self) -> None:
        self.index = 0
        self.done = False
        self._feedback = ""


def classify_card(card_type: str) -> str:
    """把卡牌类型映射成教程关心的事件名。"""
    t = str(card_type or "").lower()
    if t == "attack":
        return "play_attack"
    if t in ("skill", "power"):
        return "play_skill"
    return "play_other"
