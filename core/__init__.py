"""钢铁战线 Steel Frontline —— core 包。

只依赖 Python 3.9 标准库。
本包内的静态数据库模块（cards / relics / enemies / events）彼此零耦合，
engine.py 通过 import 汇聚它们。
"""

# 请用 `from core import cards, relics, enemies, events` 显式导入。
# 这里不做 eager import：让 engine 自由组合，也让单模块自检更快。

__all__ = ["cards", "relics", "enemies", "events"]
