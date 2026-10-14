运行时数据目录 / Runtime data folder
================================================================

本目录存放游戏运行时生成的文件，**不进版本库**（见 .gitignore）。
Files here are generated at runtime and are **not tracked** by git.

--------------------------------------------------------------------------------
中文
--------------------------------------------------------------------------------

  save.json    当前战役存档（删掉 = 重开一局）
  meta.json    元进度（成就 / 图鉴 / 排行榜 / 难度解锁）
  prefs.json   界面偏好（语言等）
  crash.log    启动失败时的错误日志（正常不会有）

删掉 save.json 只重置当前这局；删掉 meta.json 会清空全部元进度。

--------------------------------------------------------------------------------
English
--------------------------------------------------------------------------------

  save.json    current run save (delete to restart the run)
  meta.json    meta progress (achievements / codex / leaderboard / unlocks)
  prefs.json   UI preferences (language, etc.)
  crash.log    startup error log (should not normally exist)

Deleting save.json only resets the current run. Deleting meta.json wipes all
meta progress.
