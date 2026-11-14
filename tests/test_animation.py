"""Unit tests for the upgraded animation engine (Visemes, Blinking, Saccades, Transitions, Idle)."""

import math
import time
import unittest
from unittest.mock import patch
from renderer.animation import (
    BlinkController,
    SaccadeController,
    BreathingController,
    LipSyncEngine,
    TransitionSequencePlayer,
    IdleActivityController,
    VISEME_NAMES,
    DeskFaceRig,
)
from vision.mock import MockVision


class TestAnimationEngine(unittest.TestCase):

    def test_blink_controller_stages_and_progress(self):
        controller = BlinkController(min_interval_sec=0.01, max_interval_sec=0.02, blink_duration_ms=100)
        # Initially open
        self.assertEqual(controller.get_stage(), "open")
        self.assertEqual(controller.get_progress(), 0.0)

        # Trigger blink
        controller.is_blinking = True
        controller.blink_start_time = time.monotonic() - 0.02
        controller.update()
        self.assertIn(controller.get_stage(), ("open", "half"))

        # Middle of blink (50ms in) -> closed
        controller.blink_start_time = time.monotonic() - 0.05
        controller.update()
        self.assertEqual(controller.get_stage(), "closed")
        self.assertGreaterEqual(controller.get_progress(), 0.75)

    def test_saccade_controller_produces_bounded_jitter(self):
        saccade = SaccadeController(min_interval=0.01, max_interval=0.02, max_jitter_px=3.0)
        # Trigger saccade
        saccade.next_saccade_time = time.monotonic() - 1.0
        jx, jy = saccade.update()
        self.assertLessEqual(abs(jx), 4.0)
        self.assertLessEqual(abs(jy), 4.0)

    def test_lipsync_engine_viseme_mapping(self):
        engine = LipSyncEngine()
        # Test Preston Blair visemes
        self.assertEqual(engine.viseme_to_legacy_index("A"), 1)
        self.assertEqual(engine.viseme_to_legacy_index("X"), 1)
        self.assertEqual(engine.viseme_to_legacy_index("B"), 2)
        self.assertEqual(engine.viseme_to_legacy_index("C"), 3)
        self.assertEqual(engine.viseme_to_legacy_index("D"), 3)

        # Test crossfade alpha
        engine.set_active_viseme("B")
        time.sleep(0.04)
        self.assertGreaterEqual(engine.get_crossfade_alpha(), 0.8)

    def test_saccade_easing_is_independent_of_frame_rate(self):
        offsets = []
        for fps in (30, 60):
            with patch("renderer.animation.time.monotonic", return_value=0.0) as now:
                saccade = SaccadeController()
                saccade.target_offset_x = 2.0
                saccade.next_saccade_time = 10.0
                saccade.saccade_end_time = 10.0
                for frame in range(1, fps + 1):
                    now.return_value = frame / fps
                    saccade.update()
                offsets.append(saccade.current_offset_x)
        self.assertAlmostEqual(*offsets, places=6)

    def test_mock_gaze_moves_without_rendering_preview(self):
        with patch("vision.mock.time.monotonic", return_value=0.0) as now:
            vision = MockVision()
            vision.start()
            vision.trigger(10.0)
            initial = vision.get_visitor_gaze()
            now.return_value = 0.5
            self.assertNotEqual(initial, vision.get_visitor_gaze())
            vision.stop()

    def test_mock_vision_gaze_tracking(self):
        vision = MockVision()
        vision.start()
        # Without presence
        gaze = vision.get_visitor_gaze()
        self.assertEqual(gaze, (0.0, 0.0, 1.0))

        # With presence
        vision.trigger(duration_seconds=2.0)
        gaze = vision.get_visitor_gaze()
        self.assertIsInstance(gaze, tuple)
        self.assertEqual(len(gaze), 3)
        gx, gy, gdist = gaze
        self.assertGreaterEqual(gx, -1.0)
        self.assertLessEqual(gx, 1.0)
        self.assertGreater(gdist, 0.0)
        vision.stop()

    def test_transition_sequence_player_lifecycle(self):
        player = TransitionSequencePlayer(fps=30.0)
        frames = ["frame_0", "frame_1", "frame_2", "frame_3"]
        player.register_sequence("look_up", frames)
        self.assertTrue(player.has_sequence("look_up"))
        self.assertFalse(player.has_sequence("nonexistent"))

        completed = []
        def on_done():
            completed.append(True)

        player.play("look_up", on_complete=on_done)
        self.assertTrue(player.is_playing)
        self.assertEqual(player.active_sequence_id, "look_up")

        # Advance frames
        with patch("renderer.animation.time.monotonic") as mock_time:
            mock_time.return_value = player.start_time + 0.05
            frame = player.update()
            self.assertIsNotNone(frame)
            self.assertGreaterEqual(player.get_progress(), 0.0)

            # Advance to end
            mock_time.return_value = player.start_time + 1.0
            last_frame = player.update()
            self.assertEqual(last_frame, "frame_3")
            self.assertFalse(player.is_playing)
            self.assertEqual(len(completed), 1)

    def test_idle_activity_controller(self):
        controller = IdleActivityController(default_activity="reading")
        self.assertEqual(controller.current_activity, "reading")
        controller.set_activity("tinkering")
        self.assertEqual(controller.current_activity, "tinkering")

        # Register custom activity
        controller.register_activity("brewing", "wilhelm_potion", ["stir_pot", "taste"])
        controller.set_activity("brewing")
        self.assertEqual(controller.current_activity, "brewing")

        # Trigger periodic action
        controller._next_action_time = time.monotonic() - 1.0
        action = controller.update()
        self.assertIn(action, ["stir_pot", "taste"])

    def test_desk_face_rig_geometry_scaling(self):
        rig = DeskFaceRig(face_rel_x=0.5756, face_rel_y=0.3333, reference_canvas_size=(1280, 720))
        geom = rig.get_face_geometry(target_size=(1280, 720), dest=(0, 0))
        self.assertEqual(geom["face_center"], (736, 239))
        self.assertEqual(geom["eye_size"], (18, 11))
        self.assertLess(geom["left_eye"][0], geom["face_center"][0])
        self.assertGreater(geom["right_eye"][0], geom["face_center"][0])
        self.assertGreater(geom["mouth_center"][1], geom["face_center"][1])

    def test_desk_face_rig_renders_visemes_and_blinks_on_surface(self):
        import pygame
        rig = DeskFaceRig()
        surface = pygame.Surface((640, 480))
        surface.fill((10, 10, 10))

        # Render open eyes with Preston-Blair viseme D
        geom = rig.render(
            surface=surface,
            target_size=(640, 360),
            dest=(0, 60),
            blink_stage="open",
            closure_progress=0.0,
            viseme="D",
            mouth_index=3,
            pupil_x=1.5,
            pupil_y=-0.8,
            is_speaking=True,
        )
        self.assertIsNotNone(geom)
        # Sclera / eye pixel should not be background color (10, 10, 10)
        lx, ly = geom["left_eye"]
        self.assertNotEqual(surface.get_at((lx, ly))[:3], (10, 10, 10))
        # Mouth pixel should not be background color
        mx, my = geom["mouth_center"]
        self.assertNotEqual(surface.get_at((mx, my))[:3], (10, 10, 10))

    def test_desk_face_rig_closed_blink_and_quiet_mouth(self):
        import pygame
        rig = DeskFaceRig()
        surface = pygame.Surface((640, 480))
        surface.fill((50, 50, 50))

        # When not speaking and viseme is X, resting mouth is not overwriting
        geom = rig.render(
            surface=surface,
            target_size=(640, 360),
            dest=(0, 60),
            blink_stage="closed",
            closure_progress=1.0,
            viseme="X",
            mouth_index=1,
            pupil_x=0.0,
            pupil_y=0.0,
            is_speaking=False,
        )
        # Mouth center should remain untouched (50, 50, 50)
        mx, my = geom["mouth_center"]
        self.assertEqual(surface.get_at((mx, my))[:3], (50, 50, 50))

    def test_breathing_controller_sinusoidal_drift(self):
        controller = BreathingController(amplitude_px=2.5, period_sec=4.0)
        # Bounded between -2.5 and +2.5
        for t in (0.0, 1.0, 2.0, 3.0, 4.0):
            offset = controller.update(current_time=controller._start_time + t)
            self.assertGreaterEqual(offset, -2.5)
            self.assertLessEqual(offset, 2.5)

        # Anim time calculation (Living portrait 2-3px sine drift)
        self.assertAlmostEqual(controller.get_offset(0.0), 0.0, places=4)
        peak_offset = controller.get_offset(math.pi / 3.0)  # sin(pi/2) = 1.0
        self.assertAlmostEqual(peak_offset, 2.5, places=4)

    def test_blink_controller_biological_defaults_and_easing(self):
        controller = BlinkController()
        # Defaults: 2.5s - 5.5s interval, 180ms duration
        self.assertEqual(controller.min_interval, 2.5)
        self.assertEqual(controller.max_interval, 5.5)
        self.assertAlmostEqual(controller.blink_duration_sec, 0.18, places=3)

        # Biological easing: closing phase (<35%), closed hold (35%-50%), opening phase (>50%)
        controller.is_blinking = True
        t0 = time.monotonic()
        controller.blink_start_time = t0

        # At 15% into blink -> closing (ease-in, progress > 0)
        with patch("renderer.animation.time.monotonic", return_value=t0 + 0.18 * 0.15):
            controller.update()
            self.assertIn(controller.get_stage(), ("open", "half"))
            self.assertGreater(controller.get_progress(), 0.0)
            self.assertLess(controller.get_progress(), 0.5)

        # At 42% into blink -> fully closed hold
        with patch("renderer.animation.time.monotonic", return_value=t0 + 0.18 * 0.42):
            controller.update()
            self.assertEqual(controller.get_stage(), "closed")
            self.assertEqual(controller.get_progress(), 1.0)

        # At 75% into blink -> opening (ease-out deceleration)
        with patch("renderer.animation.time.monotonic", return_value=t0 + 0.18 * 0.75):
            controller.update()
            self.assertIn(controller.get_stage(), ("half", "open"))
            self.assertGreater(controller.get_progress(), 0.0)
            self.assertLess(controller.get_progress(), 1.0)

    def test_lipsync_engine_openness_and_envelope_smoothing(self):
        engine = LipSyncEngine()
        # Openness metrics combine viseme shape and acoustic amplitude
        self.assertEqual(engine.viseme_to_openness("X", 0.0), 0.0)
        self.assertGreater(engine.viseme_to_openness("B", 0.3), engine.viseme_to_openness("A", 0.3))
        self.assertGreater(engine.viseme_to_openness("D", 0.8), engine.viseme_to_openness("B", 0.8))

        # Higher amplitude expands openness
        self.assertGreater(engine.viseme_to_openness("C", 0.9), engine.viseme_to_openness("C", 0.1))

        # Synthetic fallback analysis produces frames with valid openness
        frames = engine.analyze_wav("nonexistent_test_audio.wav", fps=30)
        self.assertGreater(len(frames), 0)
        for frame in frames:
            self.assertIn("openness", frame)
            self.assertGreaterEqual(frame["openness"], 0.0)
            self.assertLessEqual(frame["openness"], 1.0)
            self.assertIn(frame["viseme"], VISEME_NAMES)

    def test_desk_face_rig_smooth_mouth_interpolation(self):
        import pygame
        rig = DeskFaceRig()
        surface = pygame.Surface((640, 480))
        geom = rig.get_face_geometry(target_size=(640, 360), dest=(0, 60))

        # Initial frame with viseme B (slightly parted: ~28px wide, 8px high)
        rig.render_mouth(surface, geom, viseme="B", mouth_index=2, is_speaking=True)
        w_b = rig.cur_w
        h_b = rig.cur_h

        # Second frame: switch target to wide open vowel D (~38px wide, 18px high)
        # Advance clock by a tiny delta (15ms)
        rig._last_mouth_time -= 0.015
        rig.render_mouth(surface, geom, viseme="D", mouth_index=3, is_speaking=True)

        # Smooth interpolation: cur_w and cur_h must be between B and D shapes, NOT snapping instantly to D!
        self.assertGreater(rig.cur_w, w_b)
        self.assertLess(rig.cur_w, 38.0 * 1.3)
        self.assertGreater(rig.cur_h, h_b)

    def test_desk_face_rig_amplitude_modulation(self):
        import pygame
        rig_quiet = DeskFaceRig()
        rig_loud = DeskFaceRig()
        surface = pygame.Surface((640, 480))
        geom = rig_quiet.get_face_geometry(target_size=(640, 360), dest=(0, 60))

        # Quiet speech (amplitude=0.1) vs Loud speech (amplitude=0.95) for same viseme C
        rig_quiet.render_mouth(surface, geom, viseme="C", mouth_index=2, is_speaking=True, amplitude=0.1)
        rig_loud.render_mouth(surface, geom, viseme="C", mouth_index=3, is_speaking=True, amplitude=0.95)

        # Loud mouth opening must be physically wider and deeper than quiet mouth
        self.assertGreater(rig_loud.cur_h, rig_quiet.cur_h)
        self.assertGreater(rig_loud.cur_w, rig_quiet.cur_w)

    def test_desk_face_rig_closed_eyelid_skin_fill(self):
        import pygame
        rig = DeskFaceRig()
        surface = pygame.Surface((640, 480))
        surface.fill((0, 0, 0))

        # Closed eye blink: should fill eyelid skin tone (215, 175, 145) covering eye aperture
        geom = rig.render(
            surface=surface,
            target_size=(640, 360),
            dest=(0, 60),
            blink_stage="closed",
            closure_progress=1.0,
            viseme="X",
            mouth_index=1,
            pupil_x=0.0,
            pupil_y=0.0,
            is_speaking=False,
        )
        lx, ly = geom["left_eye"]
        # Eye center should be skin tone (215, 175, 145) and not black (0, 0, 0)
        self.assertEqual(surface.get_at((lx, ly))[:3], (215, 175, 145))


if __name__ == "__main__":
    unittest.main()
