#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钢铁战线 Steel Frontline — 启动器。

单人卡牌构筑 Roguelike。纯本地运行，不需要联网，不需要安装任何第三方库。

用法:
    python3 main.py              # 正常启动
    python3 main.py --seed 12345 # 指定种子
    python3 main.py --asc 5      # 指定飞升难度
    python3 main.py --daily      # 每日挑战
    python3 main.py --selftest   # 无窗口自检（不开 UI，跑引擎冒烟）
"""

from __future__ import annotations

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)


def _selftest() -> int:
    """无窗口自检：确认数据层与引擎可用。"""
    ok = True
    try:
        from core import cards, relics, enemies, events
        print(f"[OK] 卡牌 {len(cards.CARD_DB)} 张")
        print(f"[OK] 遗物 {len(relics.RELIC_DB)} 个")
        print(f"[OK] 敌人 {len(enemies.ENEMY_DB)} 个")
        print(f"[OK] 事件 {len(getattr(events, 'EVENT_DB', {}))} 个")
    except Exception as exc:
        print(f"[FAIL] 数据层: {exc}")
        ok = False
    try:
        from core import run as run_mod
        from core import engine
        r = run_mod.RunState()
        r.new_run(seed=42, ascension=0)
        enc = r.roll_encounter("normal")
        b = engine.make_battle(r, enc)
        snap = b.snapshot()
        print(f"[OK] 引擎: 回合 {snap['turn']}, 手牌 {len(snap['hand'])}, "
              f"敌人 {len(snap['enemies'])}, 能量 {snap['player']['energy']}")
        # 打一张牌试试
        for c in snap["hand"]:
            try:
                if b.play_card(c["uid"]):
                    print(f"[OK] 成功打出 {c['name']}")
                    break
            except Exception as exc:
                print(f"[FAIL] 出牌 {c['name']}: {exc}")
                ok = False
                break
        # 跑完整个敌方回合
        b.end_turn()
        guard = 0
        while b.enemy_step() and guard < 50:
            guard += 1
        print(f"[OK] 敌方回合推进完成，当前 phase={b.phase}")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"[FAIL] 引擎: {exc}")
        ok = False
    print("\n自检结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return _selftest()

    seed = None
    ascension = 0
    daily = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--seed" and i + 1 < len(argv):
            try:
                seed = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        if a == "--asc" and i + 1 < len(argv):
            try:
                ascension = max(0, min(20, int(argv[i + 1])))
            except ValueError:
                pass
            i += 2
            continue
        if a == "--daily":
            daily = True
        i += 1

    try:
        import tkinter  # noqa: F401
    except Exception:
        print("错误：未找到 tkinter。请安装带 tk 支持的 Python 3。")
        return 2

    try:
        from ui.app import App
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"\n启动失败：无法加载 UI 模块（{exc}）")
        return 3

    app = App()
    if daily:
        try:
            from core import run as run_mod
            app.start_daily()
        except Exception:
            pass
    elif seed is not None or ascension:
        try:
            app.start_new_run(seed=seed, ascension=ascension)
        except Exception:
            pass
    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
