# -*- coding: utf-8 -*-
"""BGM 播放系统测试。

不依赖真实音频文件（用临时生成的 wav），也不依赖音频硬件 ——
即使后端不可用，也必须保证「静默降级、不崩、不抛异常」。
"""

import math
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# 无头环境（CI / 无显示器的机器）必须用 offscreen，
# 否则 Qt 创建 QApplication 会失败 —— Windows CI 上就是这样挂的。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SF_ALLOW_HEADLESS_QT", "1")

from core import audio  # noqa: E402


def _write_wav(path, freq=440.0, dur=0.6, sr=22050):
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        n = int(sr * dur)
        for i in range(n):
            frames += struct.pack("<h", int(9000 * math.sin(2 * math.pi * freq * i / sr)))
        w.writeframes(bytes(frames))


class TestSceneMapping(unittest.TestCase):
    """界面 → 场景映射。"""

    def test_known_screens(self):
        cases = {
            "menu": "menu", "battle": "battle", "map": "map",
            "shop": "shop", "event": "event", "rest": "rest",
            "reward": "reward", "gameover": "gameover",
        }
        for screen, want in cases.items():
            self.assertEqual(audio.scene_for_screen(screen), want)

    def test_unknown_screen_falls_back_to_ambient(self):
        self.assertEqual(audio.scene_for_screen("nonsense"), "ambient")
        self.assertEqual(audio.scene_for_screen(""), "ambient")

    def test_every_scene_has_a_file_chain(self):
        for scene in ("menu", "battle", "map", "shop", "event", "rest",
                      "reward", "victory", "defeat", "gameover"):
            self.assertIn(scene, audio.SCENE_FILES)
            self.assertIn("ambient", audio.SCENE_FILES[scene],
                          "%s 应以 ambient 兜底" % scene)


class TestMusicResolution(unittest.TestCase):
    """曲库扫描与回退链。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_music_")
        self._orig = audio.music_dir
        audio.music_dir = lambda: self.tmp
        self.p = audio.MusicPlayer(volume=50, enabled=True)

    def tearDown(self):
        try:
            self.p.stop()
        except Exception:
            pass
        audio.music_dir = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_dir_resolves_nothing(self):
        self.assertIsNone(self.p.resolve("menu"))
        self.assertEqual(self.p.available_tracks(), {})

    def test_exact_scene_match(self):
        _write_wav(os.path.join(self.tmp, "menu.wav"))
        got = self.p.resolve("menu")
        self.assertIsNotNone(got)
        self.assertTrue(got.endswith("menu.wav"))

    def test_ambient_fallback(self):
        _write_wav(os.path.join(self.tmp, "ambient.wav"))
        for scene in ("menu", "battle", "shop", "event"):
            got = self.p.resolve(scene)
            self.assertIsNotNone(got, "%s 应回退到 ambient" % scene)
            self.assertTrue(got.endswith("ambient.wav"))

    def test_scene_specific_beats_ambient(self):
        _write_wav(os.path.join(self.tmp, "ambient.wav"))
        _write_wav(os.path.join(self.tmp, "battle.wav"), freq=660)
        self.assertTrue(self.p.resolve("battle").endswith("battle.wav"))
        self.assertTrue(self.p.resolve("menu").endswith("ambient.wav"))

    def test_various_extensions_supported(self):
        for ext in (".mp3", ".m4a", ".wav", ".aac", ".aiff", ".ogg"):
            for f in os.listdir(self.tmp):
                os.remove(os.path.join(self.tmp, f))
            _write_wav(os.path.join(self.tmp, "menu" + ext))
            self.assertIsNotNone(self.p.resolve("menu"),
                                 "%s 应被识别" % ext)

    def test_uppercase_and_hidden_files(self):
        _write_wav(os.path.join(self.tmp, "MENU.WAV"))
        self.assertIsNotNone(self.p.resolve("menu"), "大写扩展名应识别")
        _write_wav(os.path.join(self.tmp, "._hidden.wav"))
        # 隐藏文件不应成为 menu 的曲目
        self.assertNotIn("_hidden", (self.p.resolve("menu") or ""))

    def test_alias_names(self):
        _write_wav(os.path.join(self.tmp, "mainmenu.wav"))
        self.assertIsNotNone(self.p.resolve("menu"), "mainmenu 应作为 menu 别名")


class TestMusicPlayer(unittest.TestCase):
    """播放器行为：开关、音量、状态、稳健性。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_music_")
        self._orig = audio.music_dir
        audio.music_dir = lambda: self.tmp
        _write_wav(os.path.join(self.tmp, "menu.wav"))
        _write_wav(os.path.join(self.tmp, "battle.wav"), freq=660)
        self.p = audio.MusicPlayer(volume=50, enabled=True)

    def tearDown(self):
        try:
            self.p.stop()
        except Exception:
            pass
        audio.music_dir = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backend_is_detected(self):
        self.assertIn(self.p.backend_name, ("afplay", "qt", "none"))

    def test_play_sets_scene_and_track(self):
        self.p.play("menu")
        self.assertEqual(self.p.scene, "menu")
        self.assertTrue(self.p.track.endswith("menu.wav"))

    def test_switching_scene_changes_track(self):
        self.p.play("menu")
        self.p.play("battle")
        self.assertEqual(self.p.scene, "battle")
        self.assertTrue(self.p.track.endswith("battle.wav"))

    def test_same_scene_does_not_restart(self):
        self.p.play("menu")
        first = self.p.track
        self.p.play("menu")
        self.assertIs(self.p.track, first, "同场景不应重头播")

    def test_missing_scene_does_not_interrupt_current(self):
        self.p.play("menu")
        self.p.play("settings")      # 无 settings.wav -> 不应打断 menu
        self.assertEqual(self.p.scene, "menu")

    def test_volume_clamped(self):
        for v in (-50, 0, 50, 100, 999):
            self.p.set_volume(v)
            self.assertGreaterEqual(self.p._volume, 0.0)
            self.assertLessEqual(self.p._volume, 1.0)

    def test_disable_stops_and_reenable_resumes(self):
        self.p.play("battle")
        self.p.set_enabled(False)
        self.assertIsNone(self.p.scene, "关闭后应停止")
        self.p.set_enabled(True)
        self.assertEqual(self.p.scene, "battle", "重新开启应恢复原场景")

    def test_disabled_player_does_not_play(self):
        self.p.set_enabled(False)
        self.p.play("menu")
        self.assertIsNone(self.p.scene)

    def test_stop_clears_state(self):
        self.p.play("menu")
        self.p.stop()
        self.assertIsNone(self.p.scene)
        self.assertIsNone(self.p.track)

    def test_status_shape(self):
        self.p.play("menu")
        st = self.p.status()
        for k in ("backend", "enabled", "volume", "scene", "track",
                  "music_dir", "tracks"):
            self.assertIn(k, st)
        self.assertIn("menu", st["tracks"])

    def test_no_exception_on_garbage_scene(self):
        for s in ("", None, 123, "!!!", "a" * 500):
            try:
                self.p.play(s)
            except Exception as exc:
                self.fail("play(%r) 抛异常：%r" % (s, exc))

    def test_on_screen_never_raises(self):
        for s in ("menu", "battle", "bogus", "", None):
            try:
                audio.on_screen(s, volume=50, enabled=True)
            except Exception as exc:
                self.fail("on_screen(%r) 抛异常：%r" % (s, exc))

    def test_shutdown_is_safe(self):
        audio.player(volume=50)
        try:
            audio.shutdown()
            audio.shutdown()      # 二次调用也要安全
        except Exception as exc:
            self.fail("shutdown 抛异常：%r" % exc)


class TestNoAudioAssetsBundled(unittest.TestCase):
    """**源码目录**不应包含音频；音乐一律由用户放进 music/。

    注意：``music/`` 目录本身就是给用户放歌的，里面的音频文件是**预期**的，
    因此这里只扫描 core/ ui/ qt/ tests/ 与根目录下的源码，不扫描 music/。
    """

    SCAN_DIRS = ("core", "ui", "qt", "tests")
    EXTS = (".mp3", ".m4a", ".wav", ".aac", ".aiff", ".ogg", ".flac")

    def test_no_audio_files_in_source_tree(self):
        offenders = []
        for sub in self.SCAN_DIRS:
            root_dir = os.path.join(BASE, sub)
            if not os.path.isdir(root_dir):
                continue
            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fn in files:
                    if fn.lower().endswith(self.EXTS):
                        offenders.append(os.path.join(root, fn))
        self.assertEqual(offenders, [],
                         "源码目录不应包含音频文件：%r" % offenders[:5])

    def test_no_audio_files_in_project_root(self):
        for fn in os.listdir(BASE):
            path = os.path.join(BASE, fn)
            if os.path.isfile(path) and fn.lower().endswith(self.EXTS):
                self.fail("项目根目录不应有音频文件：%s" % fn)

    def test_music_dir_exists_with_readme(self):
        d = audio.music_dir()
        self.assertTrue(os.path.isdir(d), "music/ 目录应存在")
        self.assertTrue(os.path.isfile(os.path.join(d, "README.txt")),
                        "music/README.txt 应说明命名规则")

    def test_music_dir_is_the_only_audio_location(self):
        """music/ 里允许有音频，且引擎应能列出它们。"""
        d = audio.music_dir()
        found = []
        for fn in os.listdir(d):
            if fn.lower().endswith(self.EXTS):
                found.append(fn)
        tracks = audio.all_tracks()
        self.assertEqual(len(tracks), len(found),
                         "all_tracks() 应列出 music/ 里全部音频文件")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTrackSelection(unittest.TestCase):
    """游戏内切歌：列出全部曲目 / 循环切换 / 直接播放。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_tracks_")
        self._orig = audio.music_dir
        audio.music_dir = lambda: self.tmp
        for i, name in enumerate(("alpha", "beta", "gamma")):
            _write_wav(os.path.join(self.tmp, name + ".wav"), freq=400 + i * 60)
        self.p = audio.MusicPlayer(volume=40, enabled=True)

    def tearDown(self):
        try:
            self.p.stop()
        except Exception:
            pass
        audio.music_dir = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_tracks_lists_every_file(self):
        tracks = audio.all_tracks()
        names = [t["file"] for t in tracks]
        self.assertEqual(names, ["alpha.wav", "beta.wav", "gamma.wav"])

    def test_all_tracks_shape(self):
        for t in audio.all_tracks():
            for k in ("file", "path", "stem", "scene", "size"):
                self.assertIn(k, t)
            self.assertGreater(t["size"], 0)

    def test_all_tracks_empty_dir(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        self.assertEqual(audio.all_tracks(), [])

    def test_all_tracks_ignores_non_audio(self):
        open(os.path.join(self.tmp, "notes.txt"), "w").close()
        names = [t["file"] for t in audio.all_tracks()]
        self.assertNotIn("notes.txt", names)

    def test_next_track_cycles_forward(self):
        paths = [t["path"] for t in audio.all_tracks()]
        self.assertEqual(audio.next_track(paths[0], 1), paths[1])
        self.assertEqual(audio.next_track(paths[2], 1), paths[0], "应回环")

    def test_next_track_cycles_backward(self):
        paths = [t["path"] for t in audio.all_tracks()]
        self.assertEqual(audio.next_track(paths[0], -1), paths[2], "应回环")
        self.assertEqual(audio.next_track(paths[1], -1), paths[0])

    def test_next_track_from_unknown(self):
        paths = [t["path"] for t in audio.all_tracks()]
        self.assertEqual(audio.next_track("/nope/x.wav", 1), paths[0])
        self.assertEqual(audio.next_track(None, 1), paths[0])

    def test_next_track_empty_dir(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        self.assertIsNone(audio.next_track(None, 1))

    def test_play_file_switches_track(self):
        paths = [t["path"] for t in audio.all_tracks()]
        audio._INSTANCE = self.p
        try:
            self.assertTrue(audio.play_file(paths[1]))
            self.assertEqual(self.p.track, paths[1])
            self.assertEqual(self.p.scene, "__manual__")
        finally:
            audio._INSTANCE = None

    def test_play_file_rejects_missing(self):
        audio._INSTANCE = self.p
        try:
            self.assertFalse(audio.play_file("/does/not/exist.wav"))
        finally:
            audio._INSTANCE = None

    def test_play_file_never_raises(self):
        audio._INSTANCE = self.p
        try:
            for bad in ("", None, 123, "!!!"):
                try:
                    audio.play_file(bad)
                except Exception as exc:
                    self.fail("play_file(%r) 抛异常：%r" % (bad, exc))
        finally:
            audio._INSTANCE = None


class TestRadioMode(unittest.TestCase):
    """电台模式：music1 开场 -> 放完随机下一首 -> 永不停止。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_radio_")
        self._orig = audio.music_dir
        audio.music_dir = lambda: self.tmp
        # music1..music10（刻意 >9 首，用来验证自然排序）
        for i in range(1, 11):
            _write_wav(os.path.join(self.tmp, "music%d.wav" % i),
                       freq=300 + i * 40, dur=0.5)
        self.p = audio.MusicPlayer(volume=30, enabled=True)

    def tearDown(self):
        try:
            self.p.stop()
        except Exception:
            pass
        audio.music_dir = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_radio_on_by_default(self):
        self.assertTrue(self.p.radio, "默认应为电台模式")

    def test_library_is_naturally_sorted(self):
        lib = [os.path.basename(x) for x in self.p.library()]
        self.assertEqual(lib[0], "music1.wav")
        self.assertEqual(lib[1], "music2.wav", "music2 应排 music10 前面")
        self.assertEqual(lib[-1], "music10.wav")

    def test_default_track_is_music1(self):
        self.assertTrue(self.p.default_track().endswith("music1.wav"))

    def test_default_track_falls_back_to_first(self):
        os.remove(os.path.join(self.tmp, "music1.wav"))
        d = self.p.default_track()
        self.assertIsNotNone(d, "没有 music1 时应退回曲库第一首")
        self.assertTrue(d.endswith("music2.wav"))

    def test_default_track_none_when_empty(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        self.assertIsNone(self.p.default_track())

    def test_random_track_avoids_current(self):
        self.p.track = self.p.library()[0]
        for _ in range(40):
            nxt = self.p.random_track()
            self.assertNotEqual(nxt, self.p.track,
                                "随机结果不应等于当前曲目")

    def test_random_track_single_file_degenerates(self):
        for f in os.listdir(self.tmp)[1:]:
            os.remove(os.path.join(self.tmp, f))
        only = self.p.library()[0]
        self.p.track = only
        self.assertEqual(self.p.random_track(), only)

    def test_random_track_empty_library(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        self.assertIsNone(self.p.random_track())

    def test_random_track_returns_library_member(self):
        lib = set(self.p.library())
        for _ in range(20):
            self.assertIn(self.p.random_track(), lib)

    def test_start_radio_begins_with_music1(self):
        audio._INSTANCE = self.p
        try:
            self.p.start_radio()
            self.assertEqual(os.path.basename(self.p.track), "music1.wav")
            self.assertEqual(self.p.scene, "__manual__")
        finally:
            audio._INSTANCE = None

    def test_remember_keeps_recent_list_bounded(self):
        for _ in range(200):
            self.p._remember(self.p.library()[0])
        self.assertLessEqual(len(self.p._played_recent), 60,
                             "近期播放记录不应无限增长")

    def test_recent_history_prevents_immediate_repeat(self):
        """连续取 5 次随机，不应出现同一首连着两次。"""
        picks = []
        for _ in range(5):
            nxt = self.p.random_track()
            picks.append(nxt)
            self.p.track = nxt
        for a, b in zip(picks, picks[1:]):
            self.assertNotEqual(a, b)


class TestRadioResume(unittest.TestCase):
    """关闭音乐后再打开，应从那首继续，而不是回到第一首。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_resume_")
        self._orig = audio.music_dir
        audio.music_dir = lambda: self.tmp
        for i in range(1, 5):
            _write_wav(os.path.join(self.tmp, "music%d.wav" % i), dur=0.5)
        self.p = audio.MusicPlayer(volume=30, enabled=True)
        audio._INSTANCE = self.p

    def tearDown(self):
        audio._INSTANCE = None
        try:
            self.p.stop()
        except Exception:
            pass
        audio.music_dir = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resume_returns_to_same_track(self):
        self.p.start_radio()
        third = self.p.library()[2]
        audio.play_file(third)
        self.assertEqual(self.p.track, third)

        self.p.set_enabled(False)
        self.assertIsNone(self.p.scene)
        self.p.set_enabled(True)
        self.assertEqual(self.p.track, third,
                         "重新打开应回到关闭前那首")

    def test_resume_survives_advanced_track(self):
        """模拟电台已推进到别的曲子后再关/开。"""
        self.p.start_radio()
        target = self.p.library()[3]
        self.p.track = target
        self.p.set_enabled(False)
        self.p.set_enabled(True)
        self.assertEqual(self.p.track, target)

    def test_disabled_then_enabled_with_empty_library_is_safe(self):
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        try:
            self.p.set_enabled(False)
            self.p.set_enabled(True)
        except Exception as exc:
            self.fail("空曲库下开关音乐抛异常：%r" % exc)


class TestBackendSelection(unittest.TestCase):
    """后端选择必须选一个**真的能出声**的，而不只是「存在」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sf_be_")
        self._orig = audio.music_dir
        audio.music_dir = lambda: self.tmp
        _write_wav(os.path.join(self.tmp, "music1.wav"), dur=0.5)

    def tearDown(self):
        audio.music_dir = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backend_is_never_none(self):
        p = audio.MusicPlayer(volume=20)
        try:
            self.assertIn(p.backend_name, ("afplay", "qt", "none"))
        finally:
            p.stop()

    def test_probe_exists_and_is_callable(self):
        p = audio.MusicPlayer(volume=20)
        try:
            self.assertTrue(callable(getattr(p, "_probe", None)),
                            "应有真实播放探测")
        finally:
            p.stop()

    def test_qt_backend_requires_qapplication(self):
        """没有 QApplication 时 Qt 后端必须报不可用（否则会崩）。"""
        from PyQt6.QtWidgets import QApplication
        has_app = QApplication.instance() is not None
        avail = audio._QtBackend.available()
        if not has_app:
            self.assertFalse(avail, "无 QApplication 时不应声称可用")

    def test_env_override_forces_afplay(self):
        """强制 afplay 时：macOS 上必须用它；其它平台 afplay 根本不存在，
        应当回落到别的后端（Qt）或 none —— 但绝不能崩。"""
        old = os.environ.get("SF_AUDIO_BACKEND")
        os.environ["SF_AUDIO_BACKEND"] = "afplay"
        try:
            p = audio.MusicPlayer(volume=20)
            try:
                if sys.platform == "darwin":
                    self.assertIn(p.backend_name, ("afplay", "none"))
                else:
                    # Windows / Linux：afplay 不存在
                    self.assertIn(p.backend_name, ("qt", "none", "afplay"))
                    self.assertNotEqual(p.backend_name, "",
                                        "后端名不能是空串")
            finally:
                p.stop()
        finally:
            if old is None:
                os.environ.pop("SF_AUDIO_BACKEND", None)
            else:
                os.environ["SF_AUDIO_BACKEND"] = old

    def test_probe_returns_bool(self):
        p = audio.MusicPlayer(volume=20)
        try:
            for cls in (audio._AfplayBackend, audio._NullBackend):
                if cls.available():
                    got = p._probe(cls())
                    self.assertIsInstance(got, bool)
        finally:
            p.stop()


class TestQtBackendContract(unittest.TestCase):
    """Qt 后端必须提供电台所需的接口（信号驱动推进）。"""

    def test_qt_backend_has_required_api(self):
        for name in ("play", "stop", "duration", "set_volume",
                     "current_position", "is_playing"):
            self.assertTrue(hasattr(audio._QtBackend, name),
                            "Qt 后端缺少 %s" % name)

    def test_music_player_has_finish_handler(self):
        p = audio.MusicPlayer(volume=20)
        try:
            self.assertTrue(callable(getattr(p, "_on_track_finished", None)),
                            "应有曲末推进回调（Qt 信号驱动）")
        finally:
            p.stop()

    def test_qt_loops_once_not_infinite(self):
        """Qt 后端不能用 Infinite 循环，否则电台永远播同一首。"""
        import inspect
        src = inspect.getsource(audio._QtBackend.__init__)
        self.assertIn("Once", src,
                      "Qt 后端应设 Loops.Once，由电台逻辑推进下一首")
        self.assertNotIn("Infinite", src,
                         "不应使用 Infinite（会卡住电台）")
