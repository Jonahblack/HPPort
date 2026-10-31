"""Headless rendering regressions using real SDL surfaces and fonts."""

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from renderer.renderer import PortraitRenderer
from state_machine import PortraitState


class TestPortraitRenderer(unittest.TestCase):
    def setUp(self):
        with patch.object(PortraitRenderer, "_load_sprites"), patch.object(PortraitRenderer, "_load_transitions"):
            self.renderer = PortraitRenderer({"renderer": {
                "width": 640, "height": 480, "asset_mode": "full_frames",
                "ambient_motes": False, "camera_motion": False,
            }})
        self.renderer.clock = MagicMock()

    def tearDown(self):
        self.renderer.cleanup()

    def test_transition_trigger_on_state_change(self):
        frame = pygame.Surface((64, 64))
        frame.fill((100, 150, 200))
        self.renderer.transition_player.register_sequence("look_up", [frame])
        self.renderer.transition_player.register_sequence("return_to_book", [frame])

        # Greeting triggers look_up transition
        self.renderer.set_state(PortraitState.GREETING)
        self.assertTrue(self.renderer.transition_player.is_playing)
        self.assertEqual(self.renderer.transition_player.active_sequence_id, "look_up")

        # Cooldown triggers return_to_book transition
        self.renderer.set_state(PortraitState.COOLDOWN)
        self.assertTrue(self.renderer.transition_player.is_playing)
        self.assertEqual(self.renderer.transition_player.active_sequence_id, "return_to_book")

    def test_gaze_target_clamping_and_updating(self):
        self.renderer.set_gaze_target(0.75, -0.5, distance=1.4)
        self.assertEqual(self.renderer.target_gaze_x, 0.75)
        self.assertEqual(self.renderer.target_gaze_y, -0.5)
        self.assertEqual(self.renderer.target_distance, 1.4)
        self.renderer.set_gaze_target(2.5, -3.0)
        self.assertEqual(self.renderer.target_gaze_x, 1.0)
        self.assertEqual(self.renderer.target_gaze_y, -1.0)

    def test_viseme_updating_and_legacy_fallback(self):
        for viseme, mouth in (("D", 3), ("B", 2), ("X", 1), ("INVALID", 1)):
            self.renderer.set_viseme(viseme, amplitude=0.85)
            self.assertEqual(self.renderer.current_mouth_index, mouth)
        self.assertEqual(self.renderer.current_viseme, "X")

    def test_quiet_audio_closes_previous_open_mouth(self):
        self.renderer.set_audio_amplitude(0.8)
        self.renderer.set_audio_amplitude(0.1)
        self.assertEqual(self.renderer.current_mouth_index, 1)
        self.assertEqual(self.renderer.current_viseme, "X")

    def test_two_visemes_sharing_legacy_index_keep_distinct_paintings(self):
        self.renderer.asset_mode = "layered"
        base = pygame.Surface((64, 64))
        mouth_b = pygame.Surface((64, 64))
        mouth_b.fill((220, 20, 20))
        mouth_g = pygame.Surface((64, 64))
        mouth_g.fill((20, 20, 220))
        self.renderer.sprites.update(base=base, viseme_B=mouth_b, viseme_G=mouth_g)
        self.renderer.set_viseme("B")
        self.renderer.render()
        self.assertEqual(self.renderer.screen.get_at((320, 240))[:3], (220, 20, 20))
        self.renderer.set_viseme("G")
        self.renderer.render()
        self.assertEqual(self.renderer.screen.get_at((320, 240))[:3], (20, 20, 220))

    def test_subtitles_wrap_and_reuse_surface_until_text_or_width_changes(self):
        self.renderer.set_subtitle("Welcome, traveller. Tell me what brings you to this enchanted portrait today.")
        first = self.renderer._get_subtitle_surface(280, 180)
        self.assertLessEqual(first.get_width(), 280)
        self.assertGreater(first.get_height(), self.renderer.font.get_linesize() + 20)
        self.assertIs(first, self.renderer._get_subtitle_surface(280, 180))
        resized = self.renderer._get_subtitle_surface(200, 180)
        self.assertIsNot(first, resized)
        self.assertLessEqual(resized.get_width(), 200)
        self.renderer.set_subtitle("x" * 180)
        self.assertLessEqual(self.renderer._get_subtitle_surface(200, 180).get_width(), 200)

    def test_repeated_text_is_rendered_once_and_cache_is_bounded(self):
        font = MagicMock(wraps=self.renderer.hud_font)
        first = self.renderer._text(font, "Listening", (255, 255, 255))
        self.assertIs(first, self.renderer._text(font, "Listening", (255, 255, 255)))
        self.assertEqual(font.render.call_count, 1)
        for i in range(160):
            self.renderer._text(font, str(i), (255, 255, 255))
        self.assertLessEqual(len(self.renderer._text_cache), 128)

    def test_resize_releases_previous_scaled_paintings(self):
        self.renderer.sprites["base"] = pygame.Surface((64, 64))
        self.renderer.render()
        previous_surfaces = list(self.renderer._scaled_sprite_cache.values())
        self.assertTrue(previous_surfaces)
        self.renderer.screen = pygame.Surface((800, 600))
        self.renderer.render()
        self.assertTrue(all(surface not in previous_surfaces for surface in self.renderer._scaled_sprite_cache.values()))

    def test_unchanged_preview_is_scaled_only_once(self):
        self.renderer.show_camera_pip = True
        self.renderer.update_camera_frame(pygame.Surface((320, 240)))
        with patch("pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as scale:
            self.renderer.render()
            self.renderer.render()
        self.assertEqual(scale.call_count, 1)

    def test_mote_glows_reuse_small_surfaces(self):
        self.renderer.ambient_motes = True
        with patch("pygame.Surface", wraps=pygame.Surface) as surface:
            self.renderer._draw_magic_motes(pygame.Rect(0, 0, 640, 480))
            initial_count = surface.call_count
            self.renderer._draw_magic_motes(pygame.Rect(0, 0, 640, 480))
        self.assertEqual(surface.call_count, initial_count)
        self.assertTrue(all(max(call.args[0]) < 20 for call in surface.call_args_list))

    def test_gaze_animation_is_independent_of_frame_rate(self):
        final_positions = []
        for fps in (30, 60):
            self.renderer.current_gaze_x = 0.0
            self.renderer.current_distance = 1.0
            self.renderer.target_gaze_x = 1.0
            self.renderer._last_render_time = 0.0
            with patch("renderer.renderer.time.monotonic") as now:
                for frame in range(1, fps + 1):
                    now.return_value = frame / fps
                    self.renderer.render()
            final_positions.append(self.renderer.current_gaze_x)
        self.assertAlmostEqual(*final_positions, places=6)

    def test_cooldown_state_selects_reading_idle_base(self):
        reading_surf = pygame.Surface((64, 64))
        reading_surf.fill((10, 20, 30))
        speaking_surf = pygame.Surface((64, 64))
        speaking_surf.fill((40, 50, 60))
        self.renderer.sprites["wilhelm_reading"] = reading_surf
        self.renderer.sprites["speaking_base"] = speaking_surf
        self.renderer.sprites["base"] = reading_surf

        # In COOLDOWN, state_base must remain on reading idle, NOT speaking base
        self.renderer.set_state(PortraitState.COOLDOWN)
        self.renderer.transition_player.is_playing = False  # after transition finishes
        with patch.object(self.renderer, "_scaled_sprite", wraps=self.renderer._scaled_sprite) as mock_scale:
            self.renderer.render()
            called_sprites = [call[0][1] for call in mock_scale.call_args_list]
            self.assertIn(reading_surf, called_sprites)
            self.assertNotIn(speaking_surf, called_sprites)

    def test_trigger_animation_manual_control(self):
        frame = pygame.Surface((64, 64))
        self.renderer.transition_player.register_sequence("page_flip", [frame])
        self.renderer.transition_player.register_sequence("get_out_tinker_box", [frame])
        self.assertFalse(self.renderer.transition_player.is_playing)

        result = self.renderer.trigger_animation("page_flip")
        self.assertTrue(result)
        self.assertTrue(self.renderer.transition_player.is_playing)
        self.assertEqual(self.renderer.transition_player.active_sequence_id, "page_flip")

        result2 = self.renderer.trigger_animation("get_out_tinker_box")
        self.assertTrue(result2)
        self.assertEqual(self.renderer.transition_player.active_sequence_id, "get_out_tinker_box")

    def test_anim_debug_hud_toggle(self):
        self.assertFalse(self.renderer.show_anim_debug_hud)
        self.renderer.toggle_anim_debug_hud()
        self.assertTrue(self.renderer.show_anim_debug_hud)
        self.renderer.toggle_anim_debug_hud()
        self.assertFalse(self.renderer.show_anim_debug_hud)

    def test_full_frames_desk_view_locked_no_drift(self):
        base_surf = pygame.Surface((100, 100))
        self.renderer.sprites["base"] = base_surf
        self.renderer.asset_mode = "full_frames"
        self.renderer.camera_motion = True
        self.renderer.current_gaze_x = 0.9
        self.renderer.anim_time = 12.34

        self.renderer.render()
        canvas_rect = pygame.Rect(int(640*0.04), int(480*0.04), 640 - 2*int(640*0.04), 480 - 2*int(480*0.04)).inflate(-36, -36)
        bw, bh = base_surf.get_size()
        scale = max(canvas_rect.width / bw, canvas_rect.height / bh)
        target_size = (int(bw * scale), int(bh * scale))
        expected_x = canvas_rect.centerx - target_size[0] // 2
        expected_y = canvas_rect.centery - target_size[1] // 2
        self.assertEqual(self.renderer._last_frame_dest, (expected_x, expected_y))


if __name__ == "__main__":
    unittest.main()
