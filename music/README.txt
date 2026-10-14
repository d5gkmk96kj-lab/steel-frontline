音乐目录 / Music folder
================================================================

本仓库不包含任何音频文件（版权原因）/ This repo ships no audio files (copyright).

--------------------------------------------------------------------------------
中文
--------------------------------------------------------------------------------

想加背景音乐：

  1. 把 mp3 / ogg / m4a / wav / aac / aiff / flac 放进这个目录
  2. 命名成 music1、music2、music3……（带扩展名）
  3. 重启游戏

游戏从 music1 开始播，放完自动随机下一首，一直循环。

支持的格式：mp3 / ogg / m4a / wav / aac / aiff / flac（可混用）
排序规则：按数字排，所以 music10 在 music2 后面

按场景命名（进阶，可选）：
  menu.*  battle.*  map.*  shop.*  event.*  rest.*
  reward.*  victory.*  defeat.*  ambient.*
有场景曲子时优先用场景曲子，没有则回落到 music1/2/3… 电台模式。

完整教程见项目根目录 README.md 的「音乐 / BGM」一节。

--------------------------------------------------------------------------------
English
--------------------------------------------------------------------------------

To add background music:

  1. Put mp3 / ogg / m4a / wav / aac / aiff / flac files in this folder
  2. Name them music1, music2, music3... (keep the extension)
  3. Restart the game

Playback always starts with music1, then picks a random next track, forever.

Supported formats: mp3 / ogg / m4a / wav / aac / aiff / flac (mixable)
Sort order: numeric, so music10 sorts after music2

Scene-based naming (advanced, optional):
  menu.*  battle.*  map.*  shop.*  event.*  rest.*
  reward.*  victory.*  defeat.*  ambient.*
Scene tracks win when present; otherwise it falls back to the music1/2/3... radio.

Full tutorial: see the "Music / BGM" section of README.md in the project root.
