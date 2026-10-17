#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面插图：**每张卡一份独立设计**。

用户要求
--------
「每个都单独画，工作量很大但这是必要的。」

所以这里不是「按流派套模板」，而是给 199 张卡各自登记一份
独立的画面描述（``Design``）。每份描述可以自由组合：

* ``parts``  —— 若干图元，每个图元有位置、缩放、旋转、颜色权重
* ``fx``     —— 这张卡的**动效类型**（子弹 / 火焰 / 冲击 / 毒雾 …）

图元（``Part``）由 ``qt.qcardart`` 里的绘制函数实现，
本文件只描述「画什么、画在哪、多大」——纯数据，不需要 Qt。

未登记的卡会走 ``_fallback()``，按流派生成一份（不至于空白）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------- 数据模型 --
@dataclass(frozen=True)
class Part:
    """一个图元。

    kind   绘制函数名（见 qt.qcardart._PART）
    x, y   相对插图区的归一化中心（0~1）
    s      相对尺寸（1.0 = 基准）
    rot    旋转角度
    alpha  不透明度 0~255
    tint   0=流派色 1=亮色 2=暗色 3=金 4=白
    """

    kind: str
    x: float = 0.5
    y: float = 0.5
    s: float = 1.0
    rot: float = 0.0
    alpha: int = 255
    tint: int = 0


@dataclass(frozen=True)
class Design:
    """一张卡的画面设计。"""

    parts: Tuple[Part, ...] = ()
    fx: str = ""              # 动效："" 表示无
    bg: str = "dark"          # 底色风格
    accents: int = 0          # 额外装饰点数


# ---------------------------------------------------------------- 图元注册 --
#: 全部可用图元（渲染器必须实现同名函数）
PART_KINDS = (
    # —— 枪械 / 弹药
    "rifle", "smg", "cannon", "sniper", "pistol", "turret",
    "bullet", "shell", "mag", "crosshair", "scope",
    # —— 防护 / 工事
    "sandbags", "barbed_wire", "bunker", "shield", "plate",
    "trench", "wall", "helmet", "barricade",
    # —— 燃烧 / 爆炸
    "flame", "explosion", "grenade", "molotov", "smoke", "ember",
    "napalm", "fireball", "ash",
    # —— 后勤 / 机械
    "fuel_drum", "crate", "gear", "wrench", "jerrycan", "pipe",
    # —— 支援 / 通讯
    "radio", "antenna", "binoculars", "map", "flare", "signal",
    "troops", "medic", "flag",
    # —— 通用装饰
    "bullet_holes", "sight_ticks", "rivets", "grid", "scan",
    "spark", "star", "chevron_up", "chevron_dn",
)

#: 动效类型
FX_KINDS = ("", "bullet", "fire", "impact", "gas", "spark", "nuke")


# ---------------------------------------------------------------- 分派表 --
def _p(kind: str, x=0.5, y=0.5, s=1.0, rot=0.0, alpha=255, tint=0) -> Part:
    return Part(kind, x, y, s, rot, alpha, tint)


#: 每张卡的独立设计。key = 卡牌 def_id
DESIGNS: Dict[str, Design] = {}


def _reg(card_id: str, parts, fx: str = "", bg: str = "dark",
         accents: int = 0) -> None:
    DESIGNS[card_id] = Design(tuple(parts), fx, bg, accents)


# =====================================================================
# 突击（54 张）—— 枪械、弹药、爆炸
# =====================================================================
_reg("strike", [
    _p("rifle", 0.52, 0.50, 1.05),
    _p("bullet", 0.80, 0.42, 0.7, -8),
    _p("bullet_holes", 0.22, 0.30, 0.8),
    _p("sight_ticks", 0.92, 0.55, 0.9),
], fx="bullet")

_reg("heavy_harpoon", [
    _p("sniper", 0.50, 0.48, 1.10),
    _p("shell", 0.80, 0.55, 0.9, 12),
    _p("crosshair", 0.82, 0.34, 0.6),
], fx="bullet")

_reg("twin_fang", [
    _p("smg", 0.36, 0.46, 0.86),
    _p("smg", 0.66, 0.54, 0.86, 6),
    _p("bullet", 0.88, 0.36, 0.6),
    _p("bullet", 0.88, 0.62, 0.6),
], fx="bullet")

_reg("cleave", [
    _p("rifle", 0.40, 0.50, 0.95, -14),
    _p("smoke", 0.72, 0.58, 1.0),
    _p("spark", 0.78, 0.40, 0.9),
    _p("sight_ticks", 0.92, 0.50, 0.8),
], fx="bullet")

_reg("ram_charge", [
    _p("turret", 0.44, 0.52, 1.05),
    _p("chevron_up", 0.76, 0.48, 0.9),
    _p("smoke", 0.24, 0.66, 0.8),
], fx="impact")

_reg("rending_bite", [
    _p("grenade", 0.48, 0.48, 1.05),
    _p("explosion", 0.72, 0.56, 0.85),
    _p("spark", 0.30, 0.32, 0.7),
], fx="impact")

_reg("whale_charge", [
    _p("cannon", 0.46, 0.50, 1.05),
    _p("impact" if False else "smoke", 0.78, 0.60, 1.0),
    _p("rivets", 0.20, 0.40, 0.8),
], fx="impact")

_reg("frenzy", [
    _p("pistol", 0.34, 0.46, 0.9),
    _p("pistol", 0.62, 0.54, 0.9, 10),
    _p("spark", 0.80, 0.40, 0.8),
    _p("spark", 0.84, 0.62, 0.7),
], fx="bullet")

_reg("inflame", [
    _p("flame", 0.50, 0.52, 1.05),
    _p("ember", 0.24, 0.34, 0.8),
    _p("ember", 0.76, 0.30, 0.9),
], fx="fire")

_reg("limit_break", [
    _p("flame", 0.40, 0.52, 1.0),
    _p("cannon", 0.66, 0.52, 0.95),
    _p("spark", 0.84, 0.36, 0.9),
], fx="fire")

_reg("reaper_scythe", [
    _p("explosion", 0.44, 0.52, 1.10),
    _p("ash", 0.74, 0.34, 0.9),
    _p("smoke", 0.72, 0.64, 1.0),
], fx="fire")

_reg("hold_the_line", [
    _p("sandbags", 0.46, 0.60, 1.05),
    _p("rifle", 0.58, 0.38, 0.82),
    _p("sight_ticks", 0.90, 0.44, 0.8),
], fx="bullet")

_reg("cross_slash", [
    _p("rifle", 0.32, 0.44, 0.85, -22),
    _p("rifle", 0.44, 0.56, 0.85, 22),
    _p("flame", 0.76, 0.50, 0.85),
], fx="bullet")

_reg("recall", [
    _p("crate", 0.44, 0.54, 1.05),
    _p("mag", 0.68, 0.44, 0.9),
    _p("bullet", 0.82, 0.62, 0.7),
], fx="")

_reg("sweeping_blow", [
    _p("cannon", 0.44, 0.52, 1.15),
    _p("shell", 0.74, 0.38, 0.9),
    _p("smoke", 0.80, 0.64, 0.9),
], fx="impact")

_reg("whirlpool", [
    _p("turret", 0.40, 0.52, 1.0),
    _p("bullet", 0.70, 0.36, 0.7),
    _p("bullet", 0.78, 0.50, 0.7),
    _p("bullet", 0.70, 0.64, 0.7),
], fx="bullet")

_reg("armor_piercer", [
    _p("sniper", 0.46, 0.50, 1.10),
    _p("shell", 0.76, 0.50, 1.0, 90),
    _p("crosshair", 0.22, 0.40, 0.7),
], fx="bullet")

_reg("cold_current", [
    _p("smg", 0.42, 0.48, 0.95),
    _p("bullet", 0.74, 0.34, 0.65),
    _p("bullet", 0.80, 0.48, 0.65),
    _p("bullet", 0.74, 0.62, 0.65),
], fx="bullet")

_reg("double_strike", [
    _p("rifle", 0.40, 0.44, 0.95),
    _p("rifle", 0.56, 0.58, 0.95),
    _p("bullet", 0.82, 0.40, 0.7),
], fx="bullet")

_reg("toxin_uppercut", [
    _p("molotov", 0.38, 0.54, 1.0),
    _p("flame", 0.62, 0.52, 1.0),
    _p("smoke", 0.80, 0.36, 0.8),
], fx="fire")

_reg("hammerhead", [
    _p("wrench", 0.42, 0.52, 1.05, -20),
    _p("impact" if False else "spark", 0.70, 0.46, 0.9),
    _p("rivets", 0.20, 0.60, 0.8),
], fx="impact")

_reg("deep_cut", [
    _p("sniper", 0.48, 0.50, 1.12),
    _p("bullet", 0.78, 0.44, 0.8),
    _p("scope", 0.22, 0.34, 0.7),
], fx="bullet")

_reg("earthshatter", [
    _p("cannon", 0.42, 0.50, 1.15),
    _p("explosion", 0.72, 0.58, 1.0),
    _p("smoke", 0.30, 0.66, 0.9),
], fx="impact")

_reg("bait_lunge", [
    _p("rifle", 0.46, 0.46, 0.95, -10),
    _p("chevron_up", 0.72, 0.56, 0.9),
    _p("smoke", 0.24, 0.60, 0.7),
], fx="bullet")

_reg("wound", [
    _p("bullet_holes", 0.34, 0.42, 1.4),
    _p("bullet", 0.62, 0.56, 0.8),
    _p("spark", 0.78, 0.36, 0.7),
], fx="impact")

_reg("burn", [
    _p("flame", 0.44, 0.54, 1.05),
    _p("ember", 0.66, 0.32, 0.9),
    _p("ash", 0.30, 0.40, 0.8),
], fx="fire")

_reg("pain", [
    _p("spark", 0.40, 0.44, 1.2),
    _p("bullet_holes", 0.62, 0.54, 1.2),
    _p("sight_ticks", 0.86, 0.50, 0.8),
], fx="impact")

_reg("armor_crack", [
    _p("shell", 0.40, 0.50, 1.15),
    _p("plate", 0.68, 0.50, 1.0),
    _p("spark", 0.84, 0.38, 0.8),
], fx="impact")

_reg("siege_shell", [
    _p("cannon", 0.40, 0.52, 1.15),
    _p("shell", 0.68, 0.46, 1.0),
    _p("explosion", 0.82, 0.62, 0.8),
], fx="impact")

_reg("mark_target", [
    _p("crosshair", 0.50, 0.50, 1.25),
    _p("sight_ticks", 0.86, 0.50, 0.9),
    _p("scope", 0.18, 0.36, 0.7),
], fx="")

_reg("chain_breach", [
    _p("rifle", 0.32, 0.46, 0.85),
    _p("explosion", 0.56, 0.56, 0.9),
    _p("grenade", 0.80, 0.42, 0.8),
], fx="impact")

_reg("mass_mobilize", [
    _p("troops", 0.42, 0.56, 1.05),
    _p("flag", 0.70, 0.42, 0.9),
    _p("chevron_up", 0.84, 0.60, 0.8),
], fx="")

_reg("arsenal_overload", [
    _p("crate", 0.38, 0.54, 1.0),
    _p("shell", 0.60, 0.44, 0.85),
    _p("mag", 0.78, 0.56, 0.8),
], fx="")

_reg("all_in", [
    _p("explosion", 0.46, 0.52, 1.1),
    _p("flame", 0.72, 0.56, 0.9),
    _p("spark", 0.26, 0.34, 0.8),
], fx="fire")

_reg("reckless_assault", [
    _p("rifle", 0.40, 0.48, 1.0, -8),
    _p("bullet", 0.70, 0.38, 0.7),
    _p("bullet", 0.78, 0.56, 0.7),
], fx="bullet")

_reg("scrap_heap", [
    _p("wrench", 0.38, 0.54, 1.0, 18),
    _p("rivets", 0.62, 0.46, 1.1),
    _p("gear", 0.80, 0.60, 0.8),
], fx="")

_reg("ambush", [
    _p("sniper", 0.44, 0.54, 1.05, -6),
    _p("scope", 0.74, 0.40, 0.8),
    _p("smoke", 0.26, 0.64, 0.7),
], fx="bullet")

_reg("overrun", [
    _p("turret", 0.40, 0.50, 1.1),
    _p("chevron_up", 0.70, 0.50, 0.95),
    _p("smoke", 0.86, 0.64, 0.7),
], fx="impact")

_reg("bullet_hail", [
    _p("smg", 0.34, 0.48, 0.9),
    _p("bullet", 0.60, 0.36, 0.6),
    _p("bullet", 0.68, 0.50, 0.6),
    _p("bullet", 0.60, 0.64, 0.6),
    _p("bullet", 0.82, 0.44, 0.55),
], fx="bullet")

_reg("desperate_gamble", [
    _p("shell", 0.40, 0.50, 0.9),
    _p("shell", 0.56, 0.44, 0.9),
    _p("bullet", 0.74, 0.54, 0.8),
    _p("spark", 0.84, 0.34, 0.7),
], fx="bullet")

_reg("deadweight_shot", [
    _p("cannon", 0.44, 0.52, 1.1),
    _p("shell", 0.72, 0.44, 0.85, 20),
    _p("smoke", 0.24, 0.62, 0.8),
], fx="impact")

_reg("zero_hour", [
    _p("sniper", 0.46, 0.48, 1.1),
    _p("crosshair", 0.74, 0.46, 0.9),
    _p("spark", 0.28, 0.60, 0.7),
], fx="bullet")

_reg("carpet_bomb", [
    _p("explosion", 0.34, 0.56, 0.85),
    _p("explosion", 0.54, 0.46, 0.85),
    _p("explosion", 0.74, 0.58, 0.85),
], fx="fire")

_reg("artillery_barrage", [
    _p("cannon", 0.34, 0.44, 0.95),
    _p("shell", 0.58, 0.36, 0.75),
    _p("explosion", 0.78, 0.60, 0.9),
], fx="impact")

_reg("scorched_earth", [
    _p("flame", 0.36, 0.54, 0.95),
    _p("flame", 0.58, 0.48, 0.85),
    _p("ash", 0.80, 0.40, 1.0),
    _p("smoke", 0.30, 0.68, 0.8),
], fx="fire")

_reg("shrapnel_storm", [
    _p("grenade", 0.40, 0.46, 0.9),
    _p("spark", 0.62, 0.36, 0.85),
    _p("spark", 0.70, 0.56, 0.85),
    _p("spark", 0.52, 0.64, 0.75),
], fx="impact")

_reg("prototype_weapon", [
    _p("turret", 0.46, 0.50, 1.15),
    _p("gear", 0.74, 0.40, 0.85),
    _p("spark", 0.28, 0.58, 0.75),
], fx="bullet")

_reg("steady_advance", [
    _p("troops", 0.40, 0.56, 0.95),
    _p("rifle", 0.60, 0.42, 0.85),
    _p("chevron_up", 0.82, 0.54, 0.75),
], fx="")

_reg("bunker_buster", [
    _p("cannon", 0.38, 0.50, 1.1),
    _p("bunker", 0.72, 0.54, 0.95),
    _p("explosion", 0.70, 0.62, 0.75),
], fx="impact")

_reg("decisive_strike", [
    _p("sniper", 0.46, 0.48, 1.15),
    _p("crosshair", 0.76, 0.52, 0.95),
    _p("bullet", 0.26, 0.58, 0.7),
], fx="bullet")

_reg("annihilation", [
    _p("explosion", 0.40, 0.50, 1.05),
    _p("explosion", 0.66, 0.58, 0.95),
    _p("ash", 0.84, 0.36, 0.85),
], fx="fire")

_reg("final_offensive", [
    _p("flag", 0.38, 0.46, 1.0),
    _p("troops", 0.58, 0.60, 0.9),
    _p("chevron_up", 0.80, 0.44, 0.85),
], fx="")

_reg("nuke", [
    _p("fireball", 0.46, 0.48, 1.2),
    _p("smoke", 0.72, 0.62, 1.0),
    _p("ash", 0.24, 0.34, 0.9),
], fx="nuke")

_reg("second_strike", [
    _p("rifle", 0.36, 0.46, 0.9),
    _p("bullet", 0.58, 0.38, 0.7),
    _p("bullet", 0.72, 0.56, 0.7),
    _p("shell", 0.84, 0.44, 0.7),
], fx="bullet")


# =====================================================================
# 防御（39 张）—— 工事、掩体、装甲
# =====================================================================
_reg("defend", [
    _p("sandbags", 0.50, 0.58, 1.05),
    _p("helmet", 0.24, 0.36, 0.65),
    _p("trench", 0.50, 0.82, 1.0),
], bg="olive")

_reg("metal_hide", [
    _p("plate", 0.48, 0.50, 1.10),
    _p("rivets", 0.28, 0.42, 1.0),
    _p("shield", 0.74, 0.54, 0.75),
], bg="steel")

_reg("shell_guard", [
    _p("bunker", 0.46, 0.54, 1.05),
    _p("sandbags", 0.72, 0.66, 0.7),
    _p("wrench", 0.22, 0.38, 0.6),
], bg="olive")

_reg("barnacle_armor", [
    _p("barbed_wire", 0.44, 0.52, 1.15),
    _p("barbed_wire", 0.44, 0.66, 1.05, 6),
    _p("wall", 0.76, 0.56, 0.70),
], bg="olive")

_reg("spine_reflex", [
    _p("barbed_wire", 0.42, 0.54, 1.10),
    _p("spark", 0.72, 0.40, 0.85),
    _p("chevron_dn", 0.24, 0.36, 0.7),
], bg="olive")

_reg("iron_tide", [
    _p("bunker", 0.38, 0.52, 0.95),
    _p("plate", 0.66, 0.52, 0.92),
    _p("rivets", 0.52, 0.34, 0.9),
], bg="steel")

_reg("bulwark_dive", [
    _p("barricade", 0.44, 0.56, 1.05),
    _p("rifle", 0.70, 0.42, 0.72),
    _p("smoke", 0.24, 0.66, 0.65),
], bg="olive")

_reg("coral_growth", [
    _p("wrench", 0.38, 0.50, 0.95, 22),
    _p("gear", 0.62, 0.56, 0.85),
    _p("wall", 0.80, 0.44, 0.70),
], bg="olive")

_reg("plated_tide", [
    _p("plate", 0.34, 0.48, 0.95),
    _p("plate", 0.58, 0.56, 0.95),
    _p("rivets", 0.80, 0.42, 0.85),
], bg="steel")

_reg("barrier_wall", [
    _p("wall", 0.48, 0.52, 1.15),
    _p("sandbags", 0.26, 0.70, 0.70),
    _p("flag", 0.78, 0.34, 0.65),
], bg="olive")

_reg("rebound_wave", [
    _p("shield", 0.44, 0.50, 1.00),
    _p("chevron_up", 0.70, 0.50, 0.85),
    _p("spark", 0.24, 0.62, 0.7),
], bg="steel")

_reg("stone_skin", [
    _p("helmet", 0.42, 0.50, 0.95),
    _p("plate", 0.66, 0.54, 0.85),
    _p("sight_ticks", 0.86, 0.48, 0.7),
], bg="steel")

_reg("tide_guard", [
    _p("binoculars", 0.40, 0.50, 0.95),
    _p("flag", 0.66, 0.40, 0.8),
    _p("bunker", 0.82, 0.62, 0.65),
], bg="olive")

_reg("riposte", [
    _p("barbed_wire", 0.40, 0.54, 1.05),
    _p("rifle", 0.68, 0.44, 0.80, -12),
    _p("spark", 0.84, 0.60, 0.7),
], bg="olive")

_reg("fortress_tide", [
    _p("bunker", 0.40, 0.52, 1.00),
    _p("crate", 0.66, 0.56, 0.80),
    _p("flag", 0.84, 0.36, 0.70),
], bg="steel")

_reg("whale_bone_screen", [
    _p("sandbags", 0.40, 0.56, 1.00),
    _p("sandbags", 0.68, 0.48, 0.90),
    _p("trench", 0.50, 0.84, 1.0),
], bg="olive")

_reg("second_wind", [
    _p("medic", 0.40, 0.50, 1.00),
    _p("crate", 0.66, 0.54, 0.80),
    _p("chevron_up", 0.84, 0.38, 0.75),
], bg="olive")

_reg("levee", [
    _p("barricade", 0.44, 0.54, 1.10),
    _p("barbed_wire", 0.44, 0.72, 0.95),
    _p("plate", 0.76, 0.44, 0.65),
], bg="steel")

_reg("abyssal_shell", [
    _p("bunker", 0.36, 0.52, 0.95),
    _p("plate", 0.60, 0.52, 0.92),
    _p("wall", 0.80, 0.56, 0.72),
], bg="steel")

_reg("bulwark_stance", [
    _p("shield", 0.42, 0.50, 1.05),
    _p("helmet", 0.68, 0.44, 0.75),
    _p("spark", 0.84, 0.62, 0.65),
], bg="steel")

_reg("last_bastion", [
    _p("wall", 0.36, 0.52, 0.95),
    _p("bunker", 0.58, 0.54, 0.90),
    _p("flag", 0.80, 0.40, 0.85),
], bg="steel")

_reg("mirror_pool", [
    _p("plate", 0.42, 0.50, 0.95),
    _p("grid", 0.66, 0.52, 1.0),
    _p("rivets", 0.84, 0.44, 0.75),
], bg="steel")

_reg("undertow", [
    _p("sandbags", 0.36, 0.60, 0.90),
    _p("rifle", 0.58, 0.40, 0.80),
    _p("bullet", 0.82, 0.46, 0.65),
], bg="olive")

_reg("sonar_scan", [
    _p("radio", 0.38, 0.52, 0.95),
    _p("signal", 0.70, 0.42, 1.0),
    _p("grid", 0.50, 0.66, 0.9),
], bg="dark")

_reg("shame", [
    _p("helmet", 0.44, 0.54, 0.95),
    _p("chevron_dn", 0.68, 0.50, 0.8),
    _p("smoke", 0.30, 0.66, 0.65),
], bg="dark")


_reg("dig_in", [
    _p("trench", 0.50, 0.60, 1.15),
    _p("sandbags", 0.32, 0.48, 0.75),
    _p("helmet", 0.70, 0.42, 0.65),
], bg="olive")



_reg("fortify_line", [
    _p("barbed_wire", 0.36, 0.52, 1.05),
    _p("sandbags", 0.58, 0.60, 0.90),
    _p("bunker", 0.80, 0.44, 0.70),
], bg="olive")








# =====================================================================
# 燃烧弹（34 张）—— 火焰、爆燃、毒气
# =====================================================================
_reg("venom_dart", [
    _p("molotov", 0.42, 0.52, 1.00),
    _p("flame", 0.68, 0.44, 0.85),
    _p("ember", 0.84, 0.62, 0.65),
], fx="fire", bg="fire")

_reg("corrode_bite", [
    _p("rifle", 0.40, 0.48, 0.90),
    _p("flame", 0.68, 0.54, 0.90),
    _p("smoke", 0.84, 0.36, 0.65),
], fx="fire", bg="fire")

_reg("toxic_cloud", [
    _p("grenade", 0.38, 0.48, 0.95),
    _p("gas_cloud" if False else "smoke", 0.64, 0.54, 1.0),
    _p("napalm", 0.82, 0.42, 0.75),
], fx="gas", bg="fire")

_reg("miasma", [
    _p("flame", 0.34, 0.54, 0.95),
    _p("flame", 0.56, 0.50, 0.90),
    _p("smoke", 0.78, 0.42, 0.85),
], fx="fire", bg="fire")

_reg("plague_tide", [
    _p("flame", 0.30, 0.56, 0.85),
    _p("flame", 0.50, 0.50, 0.90),
    _p("flame", 0.70, 0.56, 0.85),
    _p("ash", 0.86, 0.36, 0.70),
], fx="fire", bg="fire")

_reg("envenom", [
    _p("molotov", 0.36, 0.50, 0.90),
    _p("pipe", 0.60, 0.54, 0.85, 24),
    _p("flame", 0.80, 0.42, 0.80),
], fx="fire", bg="fire")

_reg("barnacle_infest", [
    _p("flame", 0.36, 0.54, 0.95),
    _p("troops", 0.62, 0.58, 0.80),
    _p("ember", 0.84, 0.36, 0.70),
], fx="fire", bg="fire")

_reg("deadwater", [
    _p("crate", 0.38, 0.54, 0.90),
    _p("flame", 0.62, 0.50, 0.90),
    _p("ash", 0.82, 0.40, 0.80),
], fx="fire", bg="fire")

_reg("venom_echo", [
    _p("medic", 0.38, 0.50, 0.95),
    _p("flame", 0.64, 0.54, 0.80),
    _p("spark", 0.84, 0.40, 0.70),
], fx="", bg="fire")

_reg("numbing_brine", [
    _p("rifle", 0.38, 0.50, 0.90),
    _p("smoke", 0.64, 0.54, 0.95),
    _p("spark", 0.84, 0.44, 0.70),
], fx="bullet", bg="dark")

_reg("crippling_wave", [
    _p("smg", 0.34, 0.50, 0.85),
    _p("bullet", 0.58, 0.40, 0.65),
    _p("bullet", 0.66, 0.56, 0.65),
    _p("smoke", 0.84, 0.62, 0.70),
], fx="bullet", bg="dark")

_reg("hook_and_barb", [
    _p("shell", 0.40, 0.50, 1.05),
    _p("pliest" if False else "plate", 0.66, 0.52, 0.90),
    _p("spark", 0.84, 0.38, 0.75),
], fx="impact", bg="dark")

_reg("catalyst_lance", [
    _p("flame", 0.36, 0.52, 1.00),
    _p("shell", 0.62, 0.48, 0.90, 45),
    _p("ember", 0.84, 0.62, 0.70),
], fx="fire", bg="fire")

_reg("hemotoxin", [
    _p("flame", 0.34, 0.56, 0.90),
    _p("flame", 0.54, 0.48, 0.85),
    _p("ash", 0.76, 0.40, 0.85),
], fx="fire", bg="fire")

_reg("toxin_burst", [
    _p("explosion", 0.44, 0.50, 1.10),
    _p("flame", 0.70, 0.56, 0.85),
    _p("smoke", 0.24, 0.36, 0.75),
], fx="fire", bg="fire")

_reg("brine_spray", [
    _p("molotov", 0.34, 0.52, 0.90),
    _p("molotov", 0.58, 0.46, 0.85),
    _p("flame", 0.80, 0.56, 0.80),
], fx="fire", bg="fire")

_reg("bloodletting", [
    _p("crate", 0.38, 0.52, 0.95),
    _p("medic", 0.64, 0.50, 0.85),
    _p("chevron_up", 0.84, 0.38, 0.70),
], fx="", bg="dark")

_reg("deep_malaise", [
    _p("pipe", 0.36, 0.52, 0.95, -20),
    _p("crate", 0.62, 0.54, 0.85),
    _p("smoke", 0.84, 0.42, 0.70),
], fx="gas", bg="dark")

_reg("necrotic_grasp", [
    _p("flame", 0.36, 0.54, 0.95),
    _p("troops", 0.64, 0.56, 0.85),
    _p("ember", 0.84, 0.36, 0.70),
], fx="fire", bg="fire")

_reg("vile_surge", [
    _p("rifle", 0.36, 0.48, 0.85),
    _p("flame", 0.62, 0.54, 0.95),
    _p("chevron_up", 0.84, 0.40, 0.75),
], fx="fire", bg="fire")

_reg("festering_hook", [
    _p("molotov", 0.38, 0.50, 0.95),
    _p("smoke", 0.64, 0.56, 0.90),
    _p("spark", 0.84, 0.42, 0.70),
], fx="fire", bg="fire")

_reg("rot_barrage", [
    _p("cannon", 0.32, 0.48, 0.85),
    _p("flame", 0.56, 0.54, 0.90),
    _p("flame", 0.78, 0.46, 0.85),
], fx="fire", bg="fire")

_reg("culling_tide", [
    _p("flame", 0.28, 0.56, 0.85),
    _p("flame", 0.48, 0.48, 0.90),
    _p("flame", 0.68, 0.54, 0.85),
    _p("ash", 0.88, 0.38, 0.70),
], fx="fire", bg="fire")

_reg("withering_gaze", [
    _p("scope", 0.40, 0.50, 1.00),
    _p("crate", 0.66, 0.54, 0.80),
    _p("smoke", 0.84, 0.40, 0.65),
], fx="", bg="dark")












# =====================================================================
# 后勤（41 张）—— 补给、油料、指挥
# =====================================================================
_reg("tide_pool", [
    _p("fuel_drum", 0.40, 0.52, 1.00),
    _p("jerrycan", 0.68, 0.56, 0.80),
    _p("gear", 0.84, 0.38, 0.65),
], bg="dark")

_reg("deep_current", [
    _p("map", 0.40, 0.50, 1.00),
    _p("binoculars", 0.66, 0.54, 0.75),
    _p("flag", 0.84, 0.38, 0.65),
], bg="dark")

_reg("artifact_shell", [
    _p("shell", 0.38, 0.50, 1.00),
    _p("gear", 0.64, 0.54, 0.85),
    _p("spark", 0.84, 0.40, 0.70),
], bg="dark")

_reg("tidal_reserve", [
    _p("crate", 0.38, 0.54, 1.00),
    _p("mag", 0.64, 0.44, 0.85),
    _p("shell", 0.82, 0.58, 0.75),
], bg="dark")

_reg("abyssal_gate", [
    _p("flag", 0.38, 0.48, 1.00),
    _p("troops", 0.62, 0.58, 0.90),
    _p("chevron_up", 0.84, 0.36, 0.75),
], bg="dark")

_reg("electrify", [
    _p("radio", 0.40, 0.52, 0.95),
    _p("spark", 0.68, 0.44, 0.85),
    _p("signal", 0.84, 0.60, 0.75),
], bg="dark")

_reg("tide_knot", [
    _p("crate", 0.42, 0.54, 1.05),
    _p("pipe", 0.70, 0.48, 0.75, 20),
    _p("rivets", 0.24, 0.38, 0.65),
], bg="dark")

_reg("chain_lightning", [
    _p("turret", 0.36, 0.50, 0.90),
    _p("spark", 0.60, 0.44, 0.85),
    _p("spark", 0.76, 0.58, 0.80),
], fx="spark", bg="dark")

_reg("resonance", [
    _p("radio", 0.36, 0.52, 0.90),
    _p("signal", 0.62, 0.44, 0.90),
    _p("cannon", 0.82, 0.56, 0.70),
], bg="dark")

_reg("surge_draw", [
    _p("jerrycan", 0.38, 0.52, 1.00),
    _p("fuel_drum", 0.66, 0.56, 0.80),
    _p("chevron_up", 0.84, 0.36, 0.70),
], bg="dark")

_reg("current_ribbon", [
    _p("radio", 0.40, 0.50, 0.95),
    _p("antenna", 0.70, 0.48, 0.85),
    _p("signal", 0.84, 0.62, 0.70),
], bg="dark")

_reg("energy_well", [
    _p("fuel_drum", 0.36, 0.54, 0.95),
    _p("fuel_drum", 0.60, 0.48, 0.90),
    _p("jerrycan", 0.82, 0.58, 0.75),
], bg="dark")

_reg("lightning_pool", [
    _p("turret", 0.36, 0.52, 0.90),
    _p("spark", 0.62, 0.46, 0.90),
    _p("bullet", 0.84, 0.40, 0.65),
], fx="spark", bg="dark")

_reg("volt_lance", [
    _p("spark", 0.42, 0.50, 1.10),
    _p("rifle", 0.66, 0.54, 0.80),
    _p("shell", 0.24, 0.38, 0.65),
], fx="spark", bg="dark")

_reg("buoyancy", [
    _p("crate", 0.40, 0.54, 0.95),
    _p("medic", 0.66, 0.48, 0.80),
    _p("chevron_up", 0.84, 0.38, 0.70),
], bg="dark")

_reg("tidal_echo", [
    _p("antenna", 0.38, 0.50, 0.95),
    _p("radio", 0.62, 0.56, 0.85),
    _p("signal", 0.84, 0.40, 0.75),
], bg="dark")

_reg("supply_drop", [
    _p("crate", 0.38, 0.54, 1.00),
    _p("flare", 0.64, 0.44, 0.85),
    _p("chevron_dn", 0.84, 0.58, 0.70),
], bg="dark")




_reg("rally_point", [
    _p("flag", 0.38, 0.46, 1.00),
    _p("troops", 0.62, 0.58, 0.85),
    _p("chevron_up", 0.84, 0.36, 0.75),
], bg="dark")




_reg("field_hospital", [
    _p("medic", 0.40, 0.50, 1.00),
    _p("crate", 0.66, 0.54, 0.80),
    _p("chevron_up", 0.84, 0.38, 0.70),
], bg="dark")
















# =====================================================================
# 支援（31 张）—— 通讯、侦察、部队
# =====================================================================
































# =====================================================================
# 其余（75 张）—— 包括附属单位、研究、诅咒、状态
# =====================================================================
_reg("sonar_pulse", [_p("radio", 0.38, 0.52, 0.95), _p("signal", 0.64, 0.44, 0.90), _p("scope", 0.84, 0.58, 0.70)], bg="dark")
_reg("whirl_engine", [_p("gear", 0.36, 0.52, 0.95), _p("gear", 0.60, 0.48, 0.85), _p("spark", 0.82, 0.58, 0.70)], bg="dark")
_reg("ebbing_blade", [_p("shell", 0.38, 0.50, 0.95), _p("rifle", 0.62, 0.54, 0.85), _p("spark", 0.84, 0.38, 0.70)], fx="bullet", bg="dark")
_reg("surge_protector", [_p("shield", 0.40, 0.52, 1.00), _p("crate", 0.66, 0.54, 0.80), _p("chevron_up", 0.86, 0.38, 0.68)], bg="dark")
_reg("chain_vein", [_p("mag", 0.36, 0.50, 0.90), _p("bullet", 0.58, 0.44, 0.75), _p("bullet", 0.74, 0.56, 0.75), _p("shell", 0.86, 0.40, 0.65)], fx="bullet", bg="dark")
_reg("voltaic_shell", [_p("turret", 0.40, 0.52, 0.95), _p("plate", 0.66, 0.54, 0.85), _p("spark", 0.86, 0.38, 0.70)], bg="steel")
_reg("current_lash", [_p("rifle", 0.36, 0.48, 0.85), _p("chevron_up", 0.62, 0.54, 0.85), _p("spark", 0.84, 0.40, 0.70)], bg="dark")
_reg("whirlpool_extra", [_p("explosion", 0.34, 0.54, 0.85), _p("explosion", 0.56, 0.46, 0.85), _p("explosion", 0.78, 0.58, 0.85)], fx="fire", bg="fire")
_reg("whale_fall_engine", [_p("gear", 0.36, 0.52, 0.90), _p("fuel_drum", 0.60, 0.54, 0.85), _p("wrench", 0.84, 0.44, 0.70, 18)], bg="dark")
_reg("echo_chamber", [_p("radio", 0.38, 0.52, 0.95), _p("antenna", 0.62, 0.44, 0.90), _p("signal", 0.84, 0.58, 0.75)], bg="dark")

_reg("summon_calf", [_p("troops", 0.38, 0.54, 0.95), _p("rifle", 0.62, 0.46, 0.85), _p("flag", 0.86, 0.60, 0.68)], bg="dark")
_reg("summon_gull", [_p("binoculars", 0.38, 0.50, 0.95), _p("signal", 0.62, 0.46, 0.85), _p("map", 0.84, 0.58, 0.70)], bg="dark")
_reg("summon_squid", [_p("troops", 0.36, 0.54, 0.88), _p("turret", 0.60, 0.48, 0.85), _p("sandbags", 0.82, 0.62, 0.70)], bg="dark")
_reg("school_of_gulls", [_p("troops", 0.34, 0.54, 0.85), _p("troops", 0.58, 0.48, 0.85), _p("chevron_up", 0.82, 0.40, 0.72)], bg="dark")
_reg("jelly_pulse", [_p("cannon", 0.36, 0.50, 0.90), _p("shell", 0.60, 0.44, 0.80), _p("explosion", 0.82, 0.58, 0.78)], fx="impact", bg="dark")
_reg("ritual_chant", [_p("flag", 0.38, 0.48, 0.95), _p("troops", 0.62, 0.56, 0.85), _p("chevron_up", 0.86, 0.38, 0.70)], bg="dark")
_reg("blood_ritual", [_p("medic", 0.38, 0.52, 0.95), _p("troops", 0.62, 0.48, 0.85), _p("spark", 0.84, 0.60, 0.70)], bg="dark")
_reg("sacrificial_tide", [_p("troops", 0.36, 0.54, 0.90), _p("flame", 0.60, 0.46, 0.85), _p("chevron_up", 0.84, 0.60, 0.70)], fx="fire", bg="fire")
_reg("summon_angler", [_p("cannon", 0.38, 0.52, 0.95), _p("shell", 0.62, 0.44, 0.85), _p("plate", 0.84, 0.58, 0.70)], bg="dark")
_reg("summon_crab", [_p("turret", 0.40, 0.52, 0.95), _p("plate", 0.64, 0.56, 0.85), _p("gear", 0.86, 0.40, 0.68)], bg="steel")
_reg("tide_leviathan", [_p("turret", 0.38, 0.50, 1.00), _p("plate", 0.60, 0.70, 0.90), _p("shell", 0.86, 0.40, 0.70)], bg="steel")
_reg("deep_echo", [_p("cannon", 0.36, 0.50, 0.90), _p("radio", 0.60, 0.54, 0.85), _p("explosion", 0.84, 0.42, 0.78)], fx="impact", bg="dark")
_reg("ritual_chorus", [_p("troops", 0.34, 0.54, 0.85), _p("troops", 0.56, 0.46, 0.85), _p("flag", 0.80, 0.58, 0.75)], bg="dark")
_reg("whale_song", [_p("wrench", 0.38, 0.52, 0.90, -18), _p("gear", 0.62, 0.54, 0.85), _p("bunker", 0.84, 0.42, 0.68)], bg="dark")
_reg("necro_tide", [_p("troops", 0.36, 0.54, 0.88), _p("flag", 0.60, 0.46, 0.85), _p("chevron_up", 0.84, 0.60, 0.70)], bg="dark")
_reg("sacrifice", [_p("crate", 0.38, 0.52, 0.90), _p("shell", 0.62, 0.48, 0.85), _p("chevron_up", 0.84, 0.40, 0.70)], bg="dark")
_reg("bone_chorus", [_p("troops", 0.36, 0.54, 0.88), _p("rifle", 0.60, 0.46, 0.85), _p("spark", 0.84, 0.62, 0.68)], fx="bullet", bg="dark")
_reg("feed_the_deep", [_p("troops", 0.38, 0.54, 0.90), _p("crate", 0.62, 0.48, 0.85), _p("chevron_up", 0.86, 0.40, 0.70)], bg="dark")
_reg("kraken_grasp", [_p("turret", 0.36, 0.50, 0.95), _p("cannon", 0.60, 0.54, 0.85), _p("flame", 0.84, 0.40, 0.75)], fx="fire", bg="dark")
_reg("abyssal_legion", [_p("turret", 0.34, 0.52, 0.85), _p("turret", 0.58, 0.48, 0.85), _p("plate", 0.82, 0.58, 0.75)], bg="steel")
_reg("spawn_pod", [_p("crate", 0.40, 0.54, 0.95), _p("troops", 0.66, 0.48, 0.80), _p("chevron_up", 0.86, 0.38, 0.68)], bg="dark")
_reg("tentacle_lash", [_p("turret", 0.36, 0.50, 0.88), _p("bullet", 0.58, 0.44, 0.72), _p("bullet", 0.72, 0.58, 0.72), _p("spark", 0.86, 0.40, 0.65)], fx="bullet", bg="dark")
_reg("tide_serpent", [_p("turret", 0.38, 0.52, 0.92), _p("gear", 0.62, 0.54, 0.85), _p("plate", 0.84, 0.42, 0.70)], bg="steel")
_reg("leviathan_wake", [_p("turret", 0.32, 0.52, 0.82), _p("turret", 0.54, 0.48, 0.82), _p("turret", 0.76, 0.54, 0.82)], bg="steel")

_reg("dazed", [_p("helmet", 0.42, 0.50, 0.95), _p("smoke", 0.68, 0.54, 0.85), _p("chevron_dn", 0.86, 0.38, 0.68)], bg="dark")
_reg("slimed", [_p("pipe", 0.38, 0.52, 0.92, 22), _p("smoke", 0.62, 0.48, 0.88), _p("spark", 0.84, 0.60, 0.68)], fx="gas", bg="dark")
_reg("decay", [_p("plate", 0.40, 0.52, 0.92), _p("smoke", 0.64, 0.48, 0.85), _p("spark", 0.84, 0.60, 0.68)], fx="gas", bg="dark")
_reg("plague_spore", [_p("shell", 0.38, 0.50, 0.90), _p("smoke", 0.62, 0.54, 0.88), _p("ember", 0.84, 0.40, 0.68)], fx="gas", bg="dark")
_reg("doubt", [_p("helmet", 0.40, 0.52, 0.92), _p("chevron_dn", 0.64, 0.48, 0.85), _p("smoke", 0.84, 0.60, 0.68)], bg="dark")
_reg("regret", [_p("flag", 0.40, 0.50, 0.92), _p("chevron_dn", 0.64, 0.46, 0.85), _p("smoke", 0.84, 0.60, 0.68)], bg="dark")
_reg("curse_of_the_deep", [_p("troops", 0.38, 0.54, 0.88), _p("smoke", 0.62, 0.46, 0.90), _p("ash", 0.84, 0.60, 0.72)], bg="dark")
_reg("barnacle_curse", [_p("crate", 0.38, 0.54, 0.90), _p("smoke", 0.62, 0.48, 0.85), _p("chevron_dn", 0.84, 0.40, 0.68)], bg="dark")

_reg("last_stand", [_p("sandbags", 0.36, 0.60, 0.88), _p("flag", 0.58, 0.44, 0.90), _p("spark", 0.82, 0.56, 0.72)], bg="olive")
_reg("salvage", [_p("crate", 0.38, 0.52, 0.92), _p("wrench", 0.62, 0.48, 0.85, 20), _p("gear", 0.84, 0.60, 0.70)], bg="dark")
_reg("siege_momentum", [_p("cannon", 0.36, 0.50, 0.90), _p("chevron_up", 0.60, 0.46, 0.85), _p("shell", 0.84, 0.58, 0.70)], fx="impact", bg="dark")
_reg("veteran_instinct", [_p("helmet", 0.38, 0.50, 0.95), _p("star", 0.62, 0.46, 0.85), _p("shield", 0.84, 0.58, 0.70)], bg="steel")
_reg("logistics_chain", [_p("crate", 0.34, 0.54, 0.85), _p("pipe", 0.56, 0.48, 0.85, 8), _p("crate", 0.80, 0.56, 0.85)], bg="dark")
_reg("all_hands_on_deck", [_p("troops", 0.34, 0.54, 0.85), _p("troops", 0.58, 0.48, 0.85), _p("chevron_up", 0.82, 0.62, 0.72)], bg="dark")
_reg("emergency_requisition", [_p("crate", 0.38, 0.54, 0.92), _p("flare", 0.62, 0.46, 0.88), _p("chevron_up", 0.86, 0.60, 0.68)], bg="dark")
_reg("winter_stockpile", [_p("crate", 0.36, 0.54, 0.90), _p("fuel_drum", 0.60, 0.48, 0.88), _p("jerrycan", 0.84, 0.60, 0.70)], bg="dark")
_reg("suppress_fire", [_p("rifle", 0.36, 0.50, 0.88), _p("bullet", 0.58, 0.44, 0.70), _p("smoke", 0.84, 0.58, 0.72)], fx="bullet", bg="dark")
_reg("disarm", [_p("grenade", 0.38, 0.50, 0.92), _p("wrench", 0.62, 0.54, 0.85, 15), _p("spark", 0.84, 0.40, 0.68)], bg="dark")
_reg("jam_comms", [_p("antenna", 0.38, 0.50, 0.92), _p("spark", 0.62, 0.46, 0.85), _p("chevron_dn", 0.84, 0.60, 0.68)], fx="spark", bg="dark")
_reg("break_morale", [_p("flag", 0.38, 0.48, 0.92), _p("chevron_dn", 0.62, 0.54, 0.85), _p("smoke", 0.84, 0.40, 0.68)], bg="dark")
_reg("scatter", [_p("troops", 0.36, 0.54, 0.85), _p("bullet", 0.58, 0.44, 0.70), _p("bullet", 0.74, 0.58, 0.70), _p("bullet", 0.86, 0.42, 0.62)], fx="bullet", bg="dark")
_reg("rust_rounds", [_p("mag", 0.38, 0.50, 0.92), _p("smoke", 0.62, 0.54, 0.85), _p("shell", 0.84, 0.42, 0.70)], fx="gas", bg="dark")

_reg("research_basic", [_p("gear", 0.36, 0.52, 0.90), _p("wrench", 0.58, 0.48, 0.88, 18), _p("spark", 0.82, 0.58, 0.72)], bg="dark")
_reg("research_advanced", [_p("gear", 0.34, 0.52, 0.88), _p("gear", 0.56, 0.46, 0.85), _p("radio", 0.80, 0.58, 0.72)], bg="dark")
_reg("research_breakthrough", [_p("gear", 0.34, 0.54, 0.85), _p("spark", 0.56, 0.46, 0.90), _p("shell", 0.80, 0.58, 0.75)], bg="dark")

_reg("deploy_riflemen", [_p("troops", 0.38, 0.54, 0.92), _p("rifle", 0.62, 0.46, 0.85), _p("flag", 0.86, 0.60, 0.68)], bg="dark")
_reg("deploy_mg_nest", [_p("sandbags", 0.36, 0.60, 0.88), _p("turret", 0.58, 0.44, 0.85), _p("bullet", 0.84, 0.54, 0.68)], fx="bullet", bg="olive")
_reg("deploy_tank", [_p("turret", 0.40, 0.52, 1.00), _p("plate", 0.40, 0.72, 0.90), _p("gear", 0.86, 0.42, 0.68)], bg="steel")
_reg("deploy_artillery", [_p("cannon", 0.38, 0.50, 0.95), _p("shell", 0.62, 0.44, 0.85), _p("explosion", 0.84, 0.60, 0.75)], fx="impact", bg="dark")
_reg("deploy_engineer", [_p("wrench", 0.38, 0.52, 0.92, -16), _p("gear", 0.62, 0.54, 0.85), _p("plate", 0.84, 0.42, 0.68)], bg="dark")
_reg("deploy_command_tank", [_p("turret", 0.36, 0.50, 0.95), _p("flag", 0.60, 0.44, 0.88), _p("plate", 0.82, 0.60, 0.72)], bg="steel")
_reg("prepare_offensive", [_p("map", 0.38, 0.50, 0.92), _p("flag", 0.62, 0.46, 0.85), _p("chevron_up", 0.84, 0.60, 0.70)], bg="dark")
_reg("fortify_hq", [_p("bunker", 0.38, 0.52, 0.95), _p("sandbags", 0.64, 0.60, 0.82), _p("flag", 0.86, 0.40, 0.68)], bg="olive")
_reg("mass_conscription", [_p("troops", 0.32, 0.54, 0.85), _p("troops", 0.56, 0.48, 0.85), _p("troops", 0.80, 0.54, 0.85)], bg="dark")
_reg("war_economy", [_p("crate", 0.34, 0.54, 0.88), _p("fuel_drum", 0.58, 0.48, 0.85), _p("gear", 0.82, 0.58, 0.72)], bg="dark")
_reg("iron_will", [_p("shield", 0.38, 0.50, 0.95), _p("star", 0.62, 0.46, 0.85), _p("chevron_up", 0.84, 0.60, 0.70)], bg="steel")
_reg("emergency_repair", [_p("wrench", 0.38, 0.52, 0.92, -14), _p("plate", 0.62, 0.54, 0.85), _p("spark", 0.84, 0.40, 0.68)], bg="dark")
_reg("supply_lines", [_p("crate", 0.32, 0.54, 0.85), _p("pipe", 0.54, 0.48, 0.85, 6), _p("crate", 0.78, 0.56, 0.85)], bg="dark")
_reg("medical_corps", [_p("medic", 0.38, 0.52, 0.95), _p("troops", 0.62, 0.48, 0.85), _p("chevron_up", 0.84, 0.60, 0.68)], bg="dark")
_reg("triage", [_p("medic", 0.36, 0.52, 0.92), _p("crate", 0.60, 0.46, 0.88), _p("map", 0.84, 0.58, 0.70)], bg="dark")
_reg("fortified_medic", [_p("medic", 0.36, 0.52, 0.90), _p("shield", 0.60, 0.48, 0.88), _p("flag", 0.84, 0.60, 0.70)], bg="steel")


# =====================================================================
# 作弊专属卡（core/cheats.py 动态注入的）
# =====================================================================
_reg("cheat_strategic_bomb", [
    _p("fireball", 0.38, 0.48, 1.05),
    _p("explosion", 0.64, 0.56, 0.95),
    _p("smoke", 0.84, 0.36, 0.80),
    _p("star", 0.20, 0.34, 0.70, tint=3),
], fx="nuke", bg="fire")

_reg("cheat_god_shield", [
    _p("shield", 0.44, 0.50, 1.10),
    _p("plate", 0.68, 0.52, 0.85),
    _p("star", 0.84, 0.36, 0.75, tint=3),
    _p("spark", 0.22, 0.60, 0.70, tint=1),
], bg="steel")

_reg("cheat_manpower_drop", [
    _p("troops", 0.38, 0.54, 0.95),
    _p("flare", 0.62, 0.44, 0.90),
    _p("chevron_dn", 0.84, 0.62, 0.70),
    _p("star", 0.20, 0.32, 0.65, tint=3),
], bg="dark")


# =====================================================================
# 兜底：没登记的卡按流派自动生成
# =====================================================================
_ARCH_PARTS = {
    "attack": (("rifle", 0.50, 0.50, 1.0), ("bullet_holes", 0.24, 0.34, 0.8)),
    "block": (("sandbags", 0.50, 0.56, 1.0), ("barbed_wire", 0.50, 0.74, 0.9)),
    "energy": (("fuel_drum", 0.44, 0.52, 1.0), ("gear", 0.72, 0.50, 0.8)),
    "poison": (("flame", 0.50, 0.52, 1.0), ("ember", 0.74, 0.36, 0.8)),
    "summon": (("radio", 0.50, 0.52, 1.0), ("signal", 0.76, 0.44, 0.85)),
}

_ARCH_FX = {"attack": "bullet", "poison": "fire", "summon": "", "block": "", "energy": ""}


def _fallback(card_id: str, arch: str) -> Design:
    """没登记的卡：按流派拼一个像样的画面。"""
    a = arch if arch in _ARCH_PARTS else "block"
    parts = [_p(k, x, y, s) for (k, x, y, s) in _ARCH_PARTS[a]]
    parts.append(_p("rivets", 0.16, 0.26, 0.8))
    return Design(tuple(parts), _ARCH_FX.get(a, ""), "dark", 1)


def design_for(card: dict) -> Design:
    """取一张卡的设计（有登记用登记，没有用兜底）。"""
    cid = str(card.get("def_id") or card.get("id") or "")
    d = DESIGNS.get(cid)
    if d is not None:
        return d
    return _fallback(cid, str(card.get("arch") or "block"))


def fx_for(card: dict) -> str:
    """这张卡打出去时该播什么特效。"""
    return design_for(card).fx
