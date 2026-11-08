"""Scene intent ordering and actual source-time presentation, independent of display FPS."""

import copy
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import numpy as np
import pygame

from renderer.asset_catalog import load_catalog
from renderer.scene_director import SceneDirector
from renderer.video import BufferedVideoPlayer, FrameDecoder, VideoFrame
from renderer.timing import FrameClock

MANIFEST = Path(__file__).resolve().parents[1] / "wilhelm_asset_manifest.json"


class FakePlayer:
    def __init__(self):
        self.sequences = {}
        self.played = []
        self.callback = None
        self.last_error = None

    def register_video(self, spec):
        self.sequences[spec["id"]] = spec

    def has_sequence(self, name):
        return name in self.sequences

    def prepare(self, name):
        return self.has_sequence(name)

    def play(self, name, on_complete):
        if self.callback:
            return False
        self.played.append(name)
        self.callback = on_complete
        return True

    def finish(self, error=None):
        callback, self.callback = self.callback, None
        self.last_error = error
        callback()

    def close(self):
        pass


class TestSceneDirector(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(MANIFEST)
        self.player = FakePlayer()
        self.now = 0
        self.director = SceneDirector(self.catalog, self.player, clock=lambda: self.now)

    def test_arrival_finishes_page_then_looks_up_and_retains_readiness(self):
        d = self.director
        d.request_action("page_flip")
        d.update(idle=True)
        d.request_engagement()
        d.request_engagement()
        d.update()
        self.assertEqual(self.player.played, ["page_flip"])
        self.assertFalse(d.ready_for_speech)
        self.player.finish()
        d.update()
        self.assertEqual(self.player.played, ["page_flip", "look_up"])
        self.assertEqual(d.scene, "reading")
        self.player.finish()
        self.assertFalse(d.ready_for_speech)  # Commit only in the main-thread tick.
        d.update()
        self.assertTrue(d.ready_for_speech)
        self.assertEqual(d.scene, "engaged_book")
        d.request_return()
        d.update()
        self.assertEqual(self.player.played[-1], "return_to_book")
        self.assertFalse(d.settled)
        self.player.finish()
        d.update()
        self.assertTrue(d.settled)
        self.assertEqual(d.scene, "reading")

    def test_arrival_during_return_waits_for_return_then_reengages(self):
        d = self.director
        d.request_engagement()
        d.update()
        self.player.finish()
        d.update()
        d.request_return()
        d.update()
        d.request_engagement()
        d.update()
        self.assertEqual(self.player.played, ["look_up", "return_to_book"])
        self.player.finish()
        d.update()
        self.assertEqual(self.player.played[-1], "look_up")
        self.assertFalse(d.ready_for_speech)

    def test_cancelled_greeting_completes_committed_look_before_return(self):
        d = self.director
        d.request_engagement()
        d.update()
        d.request_return()
        d.update()
        self.assertEqual(self.player.played, ["look_up"])
        self.player.finish()
        d.update()
        self.assertEqual(self.player.played[-1], "return_to_book")

    def test_tinkering_is_runtime_enabled_and_engages_via_tinker_look_up(self):
        d = self.director
        self.assertTrue(d.request_action("get_out_tinker_box"))
        d.update()
        self.assertEqual(d.player.played, ["put_away_book"])
        d.player.finish()
        d.update()
        self.assertEqual(d.player.played, ["put_away_book", "get_out_tinker_box"])
        d.player.finish()
        d.update()
        self.assertEqual(d.scene, "tinkering")
        d.request_engagement()
        d.update()
        self.assertEqual(d.player.played[-1], "look_up_from_tinker_box")
        d.player.finish()
        d.update()
        self.assertEqual(d.scene, "engaged_tinker")
        self.assertTrue(d.ready_for_speech)
        d.request_return()
        d.update()
        self.assertEqual(d.player.played[-1], "return_to_tinker")
        d.player.finish()
        d.update()
        self.assertEqual(d.scene, "tinkering")
        self.assertFalse(d.ready_for_speech)

    def test_away_and_return_cycle_with_engagement_while_away(self):
        d = self.director
        # From reading, request walk_away -> puts away book, then walks away
        self.assertTrue(d.request_action("walk_away"))
        d.update()
        self.assertEqual(d.player.played, ["put_away_book"])
        d.player.finish()
        d.update()
        self.assertEqual(d.player.played, ["put_away_book", "walk_away"])
        d.player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertFalse(d.ready_for_speech)

        # Visitor asks for Wilhelm while away -> walks in to neutral desk
        d.request_engagement()
        d.update()
        self.assertEqual(d.player.played[-1], "walk_in")
        d.player.finish()
        d.update()
        self.assertEqual(d.scene, "neutral")
        self.assertTrue(d.ready_for_speech)

        # End of conversation -> return to away
        d.request_return()
        d.update()
        self.assertEqual(d.player.played[-1], "walk_away")
        d.player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertFalse(d.ready_for_speech)

    def test_decode_failure_cannot_commit_an_unseen_prop_change(self):
        d = self.director
        d.request_engagement()
        d.update()
        self.player.finish("truncated video")
        d.update()
        self.assertEqual(d.scene, "unresolved")
        self.assertFalse(d.ready_for_speech)
        self.assertIn("look_up", d.disabled)

    def test_idle_timer_restarts_after_conversation_instead_of_firing_immediately(self):
        d = self.director
        d.update(idle=False)
        self.now = 1000
        d.update(idle=True)
        self.assertEqual(self.player.played, [])
        self.now = d.next_idle + 1
        d.update(idle=True)
        self.assertEqual(self.player.played, ["page_flip"])

    def test_autonomous_activity_change_routes_between_reading_and_tinkering(self):
        d = self.director
        d.next_activity = -1
        d.update(idle=True)
        self.assertEqual(d.target, "tinkering")
        d.update(idle=True)
        self.assertEqual(d.player.played, ["put_away_book"])

    def test_activity_without_engagement_routes_is_rejected_by_scheduler(self):
        d = self.director
        d.clips["look_up_from_tinker_box"]["runtime_enabled"] = False
        d.next_activity = -1
        d.update(idle=True)
        self.assertIsNone(d.target)

class MemoryDecoder:
    def __init__(self, spec, memory_bytes, max_width):
        self.spec = spec
        self.fps = spec["source_fps"]
        self.count = spec.get("test_count", 240)
        self.size = (8, 4)
        self.frames = queue.Queue()
        self.error = None
        self.done = threading.Event()
        self.thread = Mock()
        self.thread.is_alive.return_value = False
        for index in range(self.count):
            self.frames.put(VideoFrame(index, np.full((4, 8, 3), index % 256, dtype=np.uint8)))
        self.done.set()

    def close(self):
        pass


class TestBufferedVideoPlayer(unittest.TestCase):
    def player(self, count=240, factory=MemoryDecoder):
        self.now = 0
        player = BufferedVideoPlayer(clock=lambda: self.now, decoder_factory=factory)
        player.register_video({"id": "clip", "source_fps": 24, "test_count": count, "crossfade_ms": 0})
        return player

    def test_24fps_source_takes_ten_seconds_at_30_and_60_display_fps(self):
        for fps in (30, 60):
            player = self.player()
            completed = []
            player.play("clip", on_complete=lambda: completed.append(self.now))
            for tick in range(fps * 10 + 1):
                self.now = tick / fps
                player.update((16, 8))
            self.assertEqual(player.current_frame_index, 239)
            self.assertEqual(completed, [10])
            self.assertEqual(player.last_playback["presentation_seconds"], 10)
            self.assertEqual(player.last_playback["preparation_seconds"], 0)
            self.assertEqual(player.last_surface.get_at((0, 0))[:3], (239, 239, 239))

    def test_loading_does_not_consume_action_time_and_underflow_does_not_skip(self):
        player = self.player(3)
        player.play("clip")
        decoder = player._active
        frames = [decoder.frames.get_nowait() for _ in range(3)]
        decoder.done.clear()
        self.now = 5
        self.assertIsNone(player.update())
        decoder.frames.put(frames[0])
        player.update()
        self.assertEqual(player.current_frame_index, 0)
        self.now = 200
        player.update()
        self.assertEqual(player.current_frame_index, 0)
        decoder.frames.put(frames[1])
        player.update()
        self.assertEqual(player.current_frame_index, 1)
        decoder.frames.put(frames[2])
        decoder.done.set()
        player.update()
        self.assertEqual(player.current_frame_index, 1)
        self.now += 1 / 24
        player.update()
        self.assertEqual(player.current_frame_index, 2)
        self.assertTrue(player.is_playing)
        self.now += 1 / 24
        player.update()
        self.assertFalse(player.is_playing)

    def test_preparation_timeout_fails_without_advancing_the_pose(self):
        player = self.player(3)
        callback = Mock()
        player.play("clip", on_complete=callback)
        while not player._active.frames.empty():
            player._active.frames.get_nowait()
        player._active.done.clear()
        self.now = 20
        self.assertIsNone(player.update())
        self.assertEqual(player.current_frame_index, -1)
        self.assertIn("timed out", player.last_error)
        callback.assert_called_once()

    def test_requests_cannot_restart_active_clip_and_callback_fires_once(self):
        player = self.player(1)
        callback = Mock()
        player.play("clip", on_complete=callback)
        self.assertFalse(player.play("clip", restart=True))
        player.update()
        self.now = 1
        last = player.update()
        self.assertIs(player.update(), last)
        callback.assert_called_once_with()

    def test_decode_error_reports_failure_without_success_endpoint(self):
        player = self.player(3)
        callback = Mock()
        player.play("clip", on_complete=callback)
        player.update()
        first = player.last_surface
        player._active.error = "broken video"
        player.update()
        self.assertIs(player.last_surface, first)
        self.assertEqual(player.last_error, "broken video")
        self.assertFalse(player.is_playing)
        callback.assert_called_once()

    def test_real_decoder_cancels_bounded_queue_and_releases_video(self):
        spec = load_catalog(MANIFEST)["clips"][0]
        decoder = FrameDecoder(spec, 2 * 1024 * 1024, max_width=320)
        self.assertTrue(decoder.ready.wait(3))
        time.sleep(0.05)
        self.assertLessEqual(decoder.queue_bytes, decoder.memory_bytes)
        self.assertLessEqual(decoder.frames.qsize(), decoder.frames.maxsize)
        self.assertLessEqual(decoder.size[0], 320)
        decoder.close()
        decoder.thread.join(timeout=2)
        self.assertFalse(decoder.thread.is_alive())

    def test_missing_media_fails_without_leaving_a_decoder_thread(self):
        decoder = FrameDecoder({"id": "missing", "source_fps": 24, "path": "missing/never.mp4"}, 1024 * 1024)
        self.assertTrue(decoder.done.wait(2))
        decoder.thread.join(timeout=1)
        self.assertIn("Cannot open", decoder.error)
        self.assertFalse(decoder.thread.is_alive())


class TestFrameClock(unittest.TestCase):
    def test_clock_accounts_for_render_work_and_recovers_without_catchup_burst(self):
        now = [0.0]
        def sleep(seconds):
            now[0] += seconds
        clock = FrameClock(now=lambda: now[0], sleep=sleep)
        clock.tick(30)
        first = now[0]
        now[0] += 0.01
        clock.tick(30)
        self.assertAlmostEqual(now[0] - first, 1 / 30)
        now[0] += 1
        clock.tick(30)
        self.assertGreater(clock.deadline, now[0])


if __name__ == "__main__":
    unittest.main()
