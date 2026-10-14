# -*- coding: utf-8 -*-
"""钢铁战线 — BGM 播放系统（零第三方依赖）。

设计
----
* **不打包任何音频**。音乐文件由用户放进 ``music/`` 目录。
* 播放后端按可用性自动选择：
    1. macOS ``afplay``（系统自带，支持音量/速率，无第三方依赖）
    2. ``QtMultimedia``（PyQt6 版通常可用）
    3. 无后端 → 静默降级，游戏照常运行
* ``afplay`` 不支持循环，因此这里用**进程重启**实现无缝循环，并留一点
  提前量在曲子结束前重启，避免听感上有空档。

音乐文件命名约定（放 ``music/`` 目录，按场景自动匹配）
----------------------------------------------------
    menu.*        主菜单
    battle.*      战斗
    map.*         战区推进图
    shop.*        补给站 / 商店
    event.*       事件
    victory.*     胜利结算
    defeat.*      失败结算
    gameover.*    gameover 通用（victory/defeat 缺失时的兜底）
    ambient.*     通用兜底（任何场景缺曲子时用它）

支持扩展名：mp3 / m4a / wav / aac / aiff / ogg
找不到对应曲子时自动回退到 ``ambient.*``，再找不到就静音。

音量
----
由设置里的 ``volume``（0–100）控制，与音效共用。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional

# --------------------------------------------------------------------------
# 场景 → 文件名（按优先级）
# --------------------------------------------------------------------------
SCENE_FILES: Dict[str, List[str]] = {
    "menu":       ["menu", "mainmenu", "title", "ambient"],
    "battle":     ["battle", "combat", "fight", "ambient"],
    "map":        ["map", "worldmap", "campaign", "ambient"],
    "shop":       ["shop", "supply", "ambient"],
    "event":      ["event", "encounter", "ambient"],
    "rest":       ["rest", "hospital", "ambient"],
    "reward":     ["reward", "ambient"],
    "codex":      ["codex", "ambient"],
    "settings":   ["settings", "ambient"],
    "stats":      ["stats", "ambient"],
    "deck":       ["deck", "ambient"],
    "pile":       ["ambient"],
    "victory":    ["victory", "win", "gameover", "ambient"],
    "defeat":     ["defeat", "lose", "gameover", "ambient"],
    "gameover":   ["gameover", "victory", "defeat", "ambient"],
}

EXTS = (".mp3", ".m4a", ".wav", ".aac", ".aiff", ".aif", ".ogg")


def _natural_key(name: str):
    """自然排序键：让 music2 排在 music10 前面（而不是字典序）。

    把文件名按「数字段 / 非数字段」切开，数字段按数值比较。
    这样 ``music1, music2, ..., music10`` 是人类预期的顺序。
    """
    import re as _re
    parts = _re.split(r"(\d+)", str(name).lower())
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            try:
                out.append((0, int(part), ""))
                continue
            except ValueError:
                pass
        out.append((1, 0, part))
    return out

# 提前多久重启（秒），避免循环接缝处的空档
LOOP_LEAD = 0.35


def music_dir() -> str:
    """music/ 目录（位于项目根）。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "music")


# --------------------------------------------------------------------------
# 后端
# --------------------------------------------------------------------------
class _AfplayBackend:
    """macOS 系统自带 afplay。支持音量，循环靠重启进程。"""

    name = "afplay"

    def __init__(self) -> None:
        self._path = shutil.which("afplay") or "/usr/bin/afplay"

    @staticmethod
    def available() -> bool:
        return sys.platform == "darwin" and (
            shutil.which("afplay") is not None
            or os.path.exists("/usr/bin/afplay"))

    def duration(self, path: str) -> float:
        """用 afinfo 取时长；失败返回 0（表示不知道，按整曲播放）。"""
        try:
            out = subprocess.run(["afinfo", path], capture_output=True,
                                 text=True, timeout=5).stdout
            for line in out.splitlines():
                if "estimated duration" in line.lower():
                    return float(line.split(":")[1].strip().split()[0])
        except Exception:
            pass
        return 0.0

    def play(self, path: str, volume: float):
        vol = max(0.0, min(1.0, float(volume)))
        return subprocess.Popen(
            [self._path, "-v", "%.3f" % vol, path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _quiet_qt_logs() -> None:
    """压制 QtMultimedia/FFmpeg 的日志（会直接写到进程 stderr，刷屏）。

    Qt 的 ffmpeg 后端在 QApplication 构造前读这些环境变量，所以必须尽早设置。
    """
    os.environ.setdefault("QT_LOGGING_RULES", "*=false")
    os.environ.setdefault("AV_LOG_FORCE_NOCOLOR", "1")
    os.environ.setdefault("AV_LOG_LEVEL", "-8")          # FFmpeg: quiet
    os.environ.setdefault("QT_FFMPEG_LOG_LEVEL", "quiet")
    os.environ.setdefault("QT_DEBUG_PLUGINS", "0")


def _ensure_qt_app():
    """确保存在一个 QApplication（Tkinter 版没有）。

    QtMultimedia 必须有 QApplication 才能工作。Tkinter 版不依赖 Qt GUI，
    但我们可以**只起一个无窗口的 QApplication 专用于音频** —— 实测在
    纯 Tk 程序里这样能让音频正常播放（position 稳定推进）。

    返回 True 表示 Qt 音频可用。

    仅当**确实需要**时才创建 QApplication：
      * 已有实例 -> 直接用（PyQt6 版天然满足）
      * 没有实例 -> 只有在允许时才新建（Tkinter 版需要，测试环境不需要）
    新建 Qt 应用会与 Tk 抢占主循环，在测试进程里同时跑会 Abort，
    因此用 ``SF_ALLOW_HEADLESS_QT`` 环境变量兜住。
    """
    global _QT_APP
    _quiet_qt_logs()
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return False
    try:
        inst = QApplication.instance()
        if inst is not None:
            _QT_APP = inst
            return True
        # 没实例：默认不擅自创建（避免与 Tk/测试冲突）
        if os.environ.get("SF_ALLOW_HEADLESS_QT") != "1":
            return False
        app = QApplication([])
        _QT_APP = app
        return True
    except Exception:
        return False


class _QtBackend:
    """QtMultimedia 后端。

    与 afplay 不同，Qt 的播放器是**长生命周期对象**：换曲只需 ``setSource``，
    不用起新进程。因此这里不交给 ``_loop_worker`` 轮询，而是用播放器自身的
    ``mediaStatusChanged`` 信号在曲末推进下一首（更精确、无空档）。
    """

    name = "qt"

    def __init__(self) -> None:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
        self._player = QMediaPlayer()
        self._out = QAudioOutput()
        self._player.setAudioOutput(self._out)
        self._player.setLoops(QMediaPlayer.Loops.Once)
        self._QUrl = QUrl
        self._path = ""
        self.on_finished = None        # 由 MusicPlayer 注入：曲末回调
        try:
            self._player.mediaStatusChanged.connect(self._on_status)
        except Exception:
            pass

    def _on_status(self, status) -> None:
        """曲目播完时通知外部推进（电台随机下一首）。"""
        try:
            from PyQt6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                cb = self.on_finished
                if callable(cb):
                    cb()
        except Exception:
            pass

    def current_position(self) -> int:
        try:
            return int(self._player.position())
        except Exception:
            return 0

    def is_playing(self) -> bool:
        try:
            from PyQt6.QtMultimedia import QMediaPlayer
            return self._player.playbackState() == \
                QMediaPlayer.PlaybackState.PlayingState
        except Exception:
            return False

    @staticmethod
    def available() -> bool:
        """Qt 多媒体需要 QApplication；没有就地起一个无窗口的。"""
        try:
            from PyQt6.QtMultimedia import QMediaPlayer  # noqa: F401
        except Exception:
            return False
        return _ensure_qt_app()

    def duration(self, path: str) -> float:
        """Qt 是异步解析的，先返回已解析值（0 表示还没好）。"""
        try:
            ms = int(self._player.duration())
            return ms / 1000.0 if ms > 0 else 0.0
        except Exception:
            return 0.0

    def play(self, path: str, volume: float):
        self._path = path
        try:
            self._out.setVolume(max(0.0, min(1.0, float(volume))))
            self._player.setSource(self._QUrl.fromLocalFile(path))
            self._player.play()
        except Exception:
            pass
        return None

    def set_volume(self, volume: float) -> None:
        self._out.setVolume(max(0.0, min(1.0, float(volume))))

    def stop(self) -> None:
        self._player.stop()


class _NullBackend:
    name = "none"

    @staticmethod
    def available() -> bool:
        return True

    def duration(self, path: str) -> float:
        return 0.0

    def play(self, path: str, volume: float):
        return None


# --------------------------------------------------------------------------
# 管理器
# --------------------------------------------------------------------------
class MusicPlayer:
    """按场景切换 BGM。线程安全，绝不抛异常到调用方。"""

    def __init__(self, volume: int = 70, enabled: bool = True) -> None:
        _quiet_qt_logs()
        self.enabled = bool(enabled)
        self._volume = max(0, min(100, int(volume))) / 100.0
        self.scene: Optional[str] = None
        self.track: Optional[str] = None
        self._lock = threading.RLock()
        self._proc = None
        self._backend = None
        self._volume_backend = None
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._missing_logged = set()
        # 电台模式：每首放完 -> 随机下一首（而不是单曲循环）
        self.radio = True
        self._played_recent: List[str] = []   # 最近放过的，避免短期重复
        self._first_track_index = 0           # 第一首（music1 优先）
        self._choose_backend()

    # -- 后端选择 ------------------------------------------------------- #
    def _choose_backend(self) -> None:
        """选一个**真的能出声**的后端。

        注意：``afplay`` 存在 ≠ 能用。实测某些 macOS 环境下 ``afplay`` 会在
        0.9 秒内直接退出（rc=0、无报错），而 CoreAudio 本身是好的 ——
        这种情况下 QtMultimedia 反而正常。所以这里对候选后端做一次
        **真实播放探测**，谁能跑通就用谁。
        """
        env = (os.environ.get("SF_AUDIO_BACKEND") or "").strip().lower()
        order = [_QtBackend, _AfplayBackend]
        if env == "afplay":
            order = [_AfplayBackend, _QtBackend]
        elif env == "qt":
            order = [_QtBackend, _AfplayBackend]

        for cls in order + [_NullBackend]:
            try:
                if not cls.available():
                    continue
                inst = cls()
                if cls is _NullBackend:
                    self._backend = inst
                    return
                if self._probe(inst):
                    self._backend = inst
                    if cls is _QtBackend:
                        self._volume_backend = inst
                        # Qt 走信号驱动：曲末自动推进（电台）
                        try:
                            inst.on_finished = self._on_track_finished
                        except Exception:
                            pass
                    return
                # 探测失败 -> 释放并试下一个
                try:
                    if hasattr(inst, "stop"):
                        inst.stop()
                except Exception:
                    pass
            except Exception:
                continue
        self._backend = _NullBackend()

    def _probe(self, backend) -> bool:
        """真实播放一个短音，验证后端可用。

        用一个临时 wav（几乎所有后端都支持），播放 ~0.35 秒，
        若进程在极短时间内就退出则判定该后端不可用。
        """
        if backend.name == "qt":
            return self._probe_qt(backend)
        tmp = None
        try:
            import tempfile
            import wave
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            with wave.open(tmp, "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(b"\x00\x00" * 22050)   # 1 秒静音
            proc = backend.play(tmp, 0.0)
            if proc is None:
                return backend.name == "qt"
            time.sleep(0.45)
            alive = proc.poll() is None
            # 一定要收干净：terminate + wait + kill 兜底，
            # 否则会留下僵尸 afplay 进程（测试套件里会表现为挂起）
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass
            return bool(alive)
        except Exception:
            return False
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    def _probe_qt(self, backend) -> bool:
        """Qt 后端探测 —— **不做真实播放、不泵事件循环**。

        历史教训（两位验证者独立报道）：
          * 在 Tkinter 已初始化的进程里跑 ``QEventLoop`` → 死锁/段错误
          * 改用 ``QApplication.processEvents()`` 规避 → 在部分机器上**同样** SIGSEGV
        根因是 Qt 事件系统与 Tk 主循环同进程共存时的不确定性，
        属于原生层冲突，Python 侧 try/except **抓不住**。

        因此这里只做**纯静态检查**：
          1. QApplication 是否已存在（Tkinter 版由 _ensure_qt_app 建）
          2. PyQt6.QtMultimedia 能否 import
          3. 播放器/output 对象能否实例化
        不播放、不泵事件 —— 冲突面降到零。
        真实可用性由「首次播放时若失败则自动降级」兜底（见 play()）。
        """
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is None:
                return False
            # 播放器与音频输出对象是否就绪（构造时不触发任何事件循环）
            player = getattr(backend, "_player", None)
            out = getattr(backend, "_out", None)
            if player is None or out is None:
                return False
            # 能否拿到设备（纯查询，不播放）
            try:
                from PyQt6.QtMultimedia import QMediaDevices
                if not QMediaDevices.audioOutputs():
                    return False
            except Exception:
                pass
            return True
        except Exception:
            return False

    @property
    def backend_name(self) -> str:
        return getattr(self._backend, "name", "none")

    # -- 曲库 ----------------------------------------------------------- #
    def available_tracks(self) -> Dict[str, str]:
        """扫描 music/ 目录，返回 {场景: 文件绝对路径}。"""
        d = music_dir()
        found: Dict[str, str] = {}
        if not os.path.isdir(d):
            return found
        # 建立 basename(小写,无扩展) -> 路径 的索引
        index: Dict[str, str] = {}
        for fn in sorted(os.listdir(d), key=_natural_key):
            low = fn.lower()
            if not low.endswith(EXTS):
                continue
            if low.startswith("."):
                continue
            stem = os.path.splitext(low)[0]
            index.setdefault(stem, os.path.join(d, fn))
        for scene, names in SCENE_FILES.items():
            for nm in names:
                if nm in index:
                    found[scene] = index[nm]
                    break
        return found

    def library(self) -> List[str]:
        """全部曲目的绝对路径（自然排序：music1, music2, ... music10）。"""
        return [t["path"] for t in all_tracks()]

    def default_track(self) -> Optional[str]:
        """默认第一首：优先 music1，否则曲库第一个。"""
        lib = self.library()
        if not lib:
            return None
        for p in lib:
            if os.path.basename(p).lower().startswith("music1."):
                return p
        return lib[0]

    def random_track(self, avoid_current: bool = True) -> Optional[str]:
        """随机挑一首。短期内不重复，曲库只有一首时退化为它本身。"""
        import random as _r
        lib = self.library()
        if not lib:
            return None
        if len(lib) == 1:
            return lib[0]
        pool = [p for p in lib if p != self.track] if avoid_current else list(lib)
        # 尽量避开刚放过的几首
        recent = set(self._played_recent[-max(1, len(lib) // 3):])
        fresh = [p for p in pool if p not in recent]
        if fresh:
            pool = fresh
        return _r.choice(pool)

    def _remember(self, path: str) -> None:
        self._played_recent.append(path)
        keep = max(4, len(self.library()) // 2)
        if len(self._played_recent) > keep:
            del self._played_recent[:-keep]

    def start_radio(self, first: Optional[str] = None) -> None:
        """开始电台：**固定用第一首（music1）开场**，之后每首放完随机下一首。

        开场曲是确定的 —— 每次打开游戏都从 music1 开始；
        只有「下一首」才随机。需要开场也随机时显式传入 ``first``。
        """
        self.radio = True
        lib = self.library()
        if not lib:
            return
        start = first or self.default_track() or lib[0]
        # 直接在本实例上启动（模块级 play_file 走单例，这里要保证作用于自己）
        global _INSTANCE
        prev = _INSTANCE
        _INSTANCE = self
        try:
            play_file(start)
        finally:
            if prev is not None and prev is not self:
                _INSTANCE = prev

    def resolve(self, scene: str) -> Optional[str]:
        d = music_dir()
        index: Dict[str, str] = {}
        try:
            for fn in sorted(os.listdir(d), key=_natural_key):
                low = fn.lower()
                if low.endswith(EXTS) and not low.startswith("."):
                    index.setdefault(os.path.splitext(low)[0],
                                     os.path.join(d, fn))
        except Exception:
            return None
        for nm in SCENE_FILES.get(scene, [scene, "ambient"]):
            if nm in index:
                return index[nm]
        return None

    # -- 音量 ----------------------------------------------------------- #
    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume))) / 100.0
        vb = self._volume_backend
        if vb is not None:
            try:
                vb.set_volume(self._volume)
            except Exception:
                pass

    def set_enabled(self, on: bool) -> None:
        """开关音乐。

        关闭时记住**当前正在播的那首**；重新打开会从那首继续，
        而不是回到曲库第一首。
        """
        on = bool(on)
        if on == self.enabled:
            return
        self.enabled = on
        if not on:
            self._resume_scene = self.scene
            self._resume_track = self.track
            self.stop()
        else:
            s = getattr(self, "_resume_scene", None)
            t = getattr(self, "_resume_track", None)
            self._resume_scene = None
            self._resume_track = None
            self.scene = None
            self.track = None
            # 从上次那首继续
            if t and os.path.isfile(t):
                if play_file(t):
                    return
            # 退回到按场景/电台恢复
            if s and s != "__manual__":
                self.play(s)
            elif self.library():
                self.start_radio()

    # -- 播放 ----------------------------------------------------------- #
    def play(self, scene: str, restart: bool = False) -> None:
        """切到某场景的 BGM。同一场景重复调用不会重头播。"""
        try:
            self._play(scene, restart)
        except Exception:
            pass

    def _play(self, scene: str, restart: bool) -> None:
        if not self.enabled:
            return
        path = self.resolve(scene)
        with self._lock:
            if path is None:
                if scene not in self._missing_logged:
                    self._missing_logged.add(scene)
                # 没有对应曲子时不要打断当前播放
                return
            if not restart and self.scene == scene and self.track == path:
                return
            self._stop_locked()
            self.scene = scene
            self.track = path
            self._stop_flag.clear()
            proc = self._backend.play(path, self._volume)
            if proc is None:
                self._proc = None
                return
            self._proc = proc
            dur = 0.0
            try:
                dur = self._backend.duration(path)
            except Exception:
                dur = 0.0
            if dur > 0:
                self._thread = threading.Thread(
                    target=self._loop_worker, args=(path, dur),
                    daemon=True)
                self._thread.start()

    def _on_track_finished(self) -> None:
        """Qt 后端曲目播完时调用：推进到下一首（电台随机 / 否则重播）。"""
        try:
            if self._stop_flag.is_set() or not self.enabled:
                return
            if self.radio:
                nxt = self.random_track()
                if not nxt:
                    return
                self._remember(self.track or "")
                b = self._backend
                self.track = nxt
                b.play(nxt, self._volume)
            else:
                b = self._backend
                if self.track:
                    b.play(self.track, self._volume)
        except Exception:
            pass

    def _loop_worker(self, path: str, dur: float) -> None:
        """曲目推进线程。

        * **电台模式**（``radio=True``，默认）：这首放完 -> 随机挑下一首继续，
          无限循环，永不重复播放同一首直到全部轮过。
        * **单曲循环**（``radio=False``）：放完原曲重播（旧行为）。

        ``afplay`` 只支持播放单曲、进程结束即停，所以这里用线程在曲子结束前
        一点接管并启动下一首。
        """
        while not self._stop_flag.is_set():
            wait = max(1.0, dur - LOOP_LEAD)
            if self._stop_flag.wait(wait):
                return
            with self._lock:
                if self._stop_flag.is_set():
                    return
                # 用户已手动切歌 -> 让新线程接管
                if self.track != path:
                    return
                try:
                    if self._proc is not None:
                        try:
                            self._proc.terminate()
                        except Exception:
                            pass
                    if self.radio:
                        nxt = self.random_track()
                        if not nxt:
                            return
                        # 曲库只有一首时就是原曲重播
                        self._remember(path)
                        self.track = nxt
                        self._proc = self._backend.play(nxt, self._volume)
                        path = nxt
                        try:
                            dur = self._backend.duration(nxt)
                        except Exception:
                            dur = 0.0
                        if dur <= 0:
                            return      # 拿不到时长就无法接管下一首
                    else:
                        self._proc = self._backend.play(path, self._volume)
                except Exception:
                    return

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
            self.scene = None
            self.track = None

    def _stop_locked(self) -> None:
        self._stop_flag.set()
        try:
            if self._proc is not None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1.5)
                except Exception:
                    self._proc.kill()
            self._proc = None
        except Exception:
            self._proc = None
        vb = self._volume_backend
        if vb is not None and hasattr(vb, "stop"):
            try:
                vb.stop()
            except Exception:
                pass
        self._thread = None

    # -- 状态 ----------------------------------------------------------- #
    def status(self) -> dict:
        return {
            "backend": self.backend_name,
            "enabled": self.enabled,
            "volume": int(self._volume * 100),
            "scene": self.scene,
            "track": os.path.basename(self.track) if self.track else None,
            "music_dir": music_dir(),
            "tracks": {k: os.path.basename(v)
                       for k, v in self.available_tracks().items()},
        }


# --------------------------------------------------------------------------
# 单例
# --------------------------------------------------------------------------
_INSTANCE: Optional[MusicPlayer] = None
_QT_APP = None


def player(volume: int = 70, enabled: bool = True) -> MusicPlayer:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MusicPlayer(volume=volume, enabled=enabled)
    return _INSTANCE


def play_scene(scene: str) -> None:
    p = _INSTANCE
    if p is not None:
        p.play(scene)


def shutdown() -> None:
    global _INSTANCE
    if _INSTANCE is not None:
        try:
            _INSTANCE.stop()
        except Exception:
            pass
        _INSTANCE = None


# --------------------------------------------------------------------------
# 界面名 → 音乐场景
# --------------------------------------------------------------------------
SCREEN_TO_SCENE: Dict[str, str] = {
    "menu": "menu",
    "battle": "battle",
    "map": "map",
    "shop": "shop",
    "event": "event",
    "rest": "rest",
    "reward": "reward",
    "treasure": "reward",
    "deck": "deck",
    "codex": "codex",
    "settings": "settings",
    "stats": "stats",
    "achievements": "stats",
    "pile": "pile",
    "gameover": "gameover",
}


def scene_for_screen(screen: str) -> str:
    return SCREEN_TO_SCENE.get(str(screen), "ambient")


def on_screen(screen: str, volume: int = 70, enabled: bool = True) -> None:
    """界面切换时调用：切到对应 BGM（同场景不会重头播）。"""
    try:
        p = player(volume=volume, enabled=enabled)
        p.set_volume(volume)
        p.set_enabled(enabled)
        if enabled:
            p.play(scene_for_screen(screen))
            # 若没有任何场景命名的曲子（用户用的是 music1/2/3...），
            # 则退回「电台模式」：随机开场，之后随机轮播。
            if p.scene is None and not p.track:
                if p.library():
                    p.start_radio()
    except Exception:
        pass


# --------------------------------------------------------------------------
# 曲目选择（游戏内切歌）
# --------------------------------------------------------------------------
def all_tracks() -> List[dict]:
    """列出 music/ 目录里的**全部**音频文件。

    返回 ``[{"file": 文件名, "path": 绝对路径, "stem": 主名,
              "scene": 匹配到的场景或 None, "size": 字节}]``
    按文件名排序，便于 UI 直接渲染列表。
    """
    d = music_dir()
    out: List[dict] = []
    try:
        for fn in sorted(os.listdir(d), key=_natural_key):
            low = fn.lower()
            if low.startswith(".") or not low.endswith(EXTS):
                continue
            path = os.path.join(d, fn)
            stem = os.path.splitext(low)[0]
            scene = None
            for sc, names in SCENE_FILES.items():
                if stem in names:
                    scene = sc
                    break
            try:
                size = os.path.getsize(path)
            except Exception:
                size = 0
            out.append({"file": fn, "path": path, "stem": stem,
                        "scene": scene, "size": size})
    except Exception:
        pass
    return out


def play_file(path: str) -> bool:
    """直接播放指定文件（忽略场景匹配），并循环。"""
    p = _INSTANCE
    if p is None:
        return False
    try:
        if not os.path.isfile(path):
            return False
        with p._lock:
            p._stop_locked()
            p.scene = "__manual__"
            p.track = path
            p._remember(path)
            p._stop_flag.clear()
            proc = p._backend.play(path, p._volume)
            if proc is None:
                p._proc = None
                return True
            p._proc = proc
            try:
                dur = p._backend.duration(path)
            except Exception:
                dur = 0.0
            if dur > 0:
                p._thread = threading.Thread(
                    target=p._loop_worker, args=(path, dur), daemon=True)
                p._thread.start()
        return True
    except Exception:
        return False


def next_track(current: Optional[str] = None, step: int = 1) -> Optional[str]:
    """在全部曲目中循环切换，返回新文件路径。"""
    tracks = all_tracks()
    if not tracks:
        return None
    paths = [t["path"] for t in tracks]
    if current in paths:
        i = (paths.index(current) + step) % len(paths)
    else:
        i = 0 if step >= 0 else len(paths) - 1
    return paths[i]
