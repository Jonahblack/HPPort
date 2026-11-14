"""Unit tests for SceneDirector routing, transitions, and night/away lifecycle."""

from pathlib import Path
import unittest

from renderer.asset_catalog import load_catalog
from renderer.scene_director import SceneDirector

MANIFEST = Path(__file__).resolve().parents[1] / "wilhelm_asset_manifest.json"


class FakePlayer:
    """Mock video player for deterministic scene director testing."""

    def __init__(self):
        self.sequences = {}
        self.played = []
        self.callback = None
        self.last_error = None
        self.current_frame_index = 0

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
        if callback:
            callback()

    def close(self):
        pass


class TestSceneDirectorRoutingAndNightTransitions(unittest.TestCase):

    def setUp(self):
        self.catalog = load_catalog(MANIFEST)
        self.player = FakePlayer()
        self.now = 1000.0
        self.director = SceneDirector(self.catalog, self.player, clock=lambda: self.now)

    def test_routes_to_away_and_return_are_resolvable(self):
        d = self.director
        # Reading -> away
        route_from_reading = d._route("reading", "away")
        self.assertEqual(route_from_reading, ["put_away_book", "walk_away"])

        # Tinkering -> away
        route_from_tinkering = d._route("tinkering", "away")
        self.assertEqual(route_from_tinkering, ["put_away_tinker", "walk_away"])

        # Away -> neutral
        route_to_neutral = d._route("away", "neutral")
        self.assertEqual(route_to_neutral, ["walk_in"])

        # Away -> reading (morning routine)
        route_to_reading = d._route("away", "reading")
        self.assertEqual(route_to_reading, ["walk_in", "get_out_book"])

    def test_night_departure_from_reading_to_away(self):
        d = self.director
        self.assertEqual(d.scene, "reading")

        # Initiate departure to away
        self.assertTrue(d.request_action("walk_away"))
        d.update()
        self.assertEqual(self.player.played, ["put_away_book"])

        # Finish packing up book
        self.player.finish()
        d.update()
        self.assertEqual(self.player.played, ["put_away_book", "walk_away"])
        self.assertFalse(d.settled)

        # Finish walking away
        self.player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertTrue(d.settled)
        self.assertFalse(d.ready_for_speech)

    def test_night_departure_from_tinkering_to_away(self):
        d = self.director
        # Move to tinkering first
        self.assertTrue(d.request_action("get_out_tinker_box"))
        d.update()
        self.player.finish()  # put_away_book
        d.update()
        self.player.finish()  # get_out_tinker_box
        d.update()
        self.assertEqual(d.scene, "tinkering")

        # Now depart for the night
        self.assertTrue(d.request_action("walk_away"))
        d.update()
        self.assertEqual(self.player.played[-1], "put_away_tinker")

        self.player.finish()
        d.update()
        self.assertEqual(self.player.played[-1], "walk_away")

        self.player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertTrue(d.settled)
        self.assertFalse(d.ready_for_speech)

    def test_summon_while_away_gates_readiness_until_walk_in_finishes(self):
        d = self.director
        # Put director in away scene
        d.scene = "away"
        d.target = None
        d.active = None
        d.engaging = False

        # Visitor summons Wilhelm
        d.request_engagement()
        d.update()
        self.assertEqual(self.player.played[-1], "walk_in")
        self.assertFalse(d.ready_for_speech)

        # Mid-walk: still not ready for speech
        d.update()
        self.assertFalse(d.ready_for_speech)

        # Walk-in finishes: Wilhelm is seated at neutral desk
        self.player.finish()
        d.update()
        self.assertEqual(d.scene, "neutral")
        self.assertTrue(d.ready_for_speech)

    def test_overnight_post_conversation_returns_to_away(self):
        d = self.director
        d.scene = "away"
        d.target = None
        d.active = None
        d.engaging = False

        # Summon and finish walk-in
        d.request_engagement()
        d.update()
        self.player.finish()
        d.update()
        self.assertEqual(d.scene, "neutral")
        self.assertTrue(d.ready_for_speech)

        # Post-conversation return requested
        d.request_return()
        d.update()
        self.assertEqual(self.player.played[-1], "walk_away")
        self.assertFalse(d.ready_for_speech)

        self.player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertTrue(d.settled)
        self.assertFalse(d.ready_for_speech)

    def test_morning_return_from_away_to_reading(self):
        d = self.director
        d.scene = "away"
        d.target = "reading"

        d.update()
        self.assertEqual(self.player.played[-1], "walk_in")
        self.player.finish()

        d.update()
        self.assertEqual(self.player.played[-1], "get_out_book")
        self.player.finish()

        d.update()
        self.assertEqual(d.scene, "reading")
        self.assertTrue(d.settled)

    def test_engagement_during_walk_away_completes_departure_then_returns(self):
        d = self.director
        d.scene = "neutral"
        d.target = "away"
        d.update()
        self.assertEqual(self.player.played[-1], "walk_away")

        # Visitor summons while he is mid-stride walking away
        d.request_engagement()
        d.update()
        # walk_away must finish first
        self.assertEqual(self.player.played[-1], "walk_away")
        self.assertFalse(d.ready_for_speech)

        # walk_away completes
        self.player.finish()
        d.update()
        # Immediately triggers walk_in to bring him back
        self.assertEqual(self.player.played[-1], "walk_in")
        self.assertFalse(d.ready_for_speech)

        self.player.finish()
        d.update()
        self.assertEqual(d.scene, "neutral")
        self.assertTrue(d.ready_for_speech)

    def test_decode_error_during_walk_away_disables_clip_and_sets_unresolved(self):
        d = self.director
        d.scene = "neutral"
        d.target = "away"
        d.update()
        self.assertEqual(self.player.played[-1], "walk_away")

        # Video decoding fails
        self.player.finish("ffmpeg decode error")
        d.update()
        self.assertEqual(d.scene, "unresolved")
        self.assertFalse(d.ready_for_speech)
        self.assertIn("walk_away", d.disabled)
        self.assertIsNotNone(d.error)

    def test_night_schedule_autonomous_departure_and_morning_return(self):
        hour = [14]
        config = {
            "schedule": {
                "enabled": True,
                "night_start_hour": 22,
                "night_end_hour": 7,
                "night_post_conversation_dwell_seconds": 90,
            }
        }
        player = FakePlayer()
        now = [1000.0]
        d = SceneDirector(
            self.catalog,
            player,
            config=config,
            clock=lambda: now[0],
            wall_clock=lambda: hour[0],
        )

        # Daytime: stays in reading during idle
        d.update(idle=True)
        self.assertEqual(d.scene, "reading")
        self.assertFalse(d.is_night_active)
        self.assertFalse(d.is_away)

        # Night begins (hour = 22)
        hour[0] = 22
        self.assertTrue(d.is_night_active)
        d.update(idle=True)
        self.assertEqual(player.played, ["put_away_book"])

        player.finish()
        d.update()
        self.assertEqual(player.played, ["put_away_book", "walk_away"])

        player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertTrue(d.is_away)
        self.assertTrue(d.is_empty_room)
        self.assertTrue(d.settled)

        # Stays quietly in away throughout the night
        now[0] += 3600
        d.update(idle=True)
        self.assertEqual(d.scene, "away")
        self.assertEqual(len(player.played), 2)  # No extra actions played

        # Morning arrives (hour = 7)
        hour[0] = 7
        self.assertFalse(d.is_night_active)
        d.update(idle=True)
        self.assertEqual(player.played[-1], "walk_in")

        player.finish()
        d.update()
        self.assertEqual(player.played[-1], "get_out_book")

        player.finish()
        d.update()
        self.assertEqual(d.scene, "reading")
        self.assertTrue(d.settled)
        self.assertFalse(d.is_away)

    def test_overnight_summon_dwell_window_and_re_departure(self):
        hour = [23]
        config = {
            "schedule": {
                "enabled": True,
                "night_start_hour": 22,
                "night_end_hour": 7,
                "night_post_conversation_dwell_seconds": 90,
            }
        }
        player = FakePlayer()
        now = [1000.0]
        d = SceneDirector(
            self.catalog,
            player,
            config=config,
            clock=lambda: now[0],
            wall_clock=lambda: hour[0],
        )
        d.scene = "away"
        d.target = None
        d.active = None
        d.engaging = False

        # Visitor summons Wilhelm while away at night
        d.request_engagement()
        d.update()
        self.assertEqual(player.played[-1], "walk_in")
        self.assertFalse(d.ready_for_speech)

        player.finish()
        d.update()
        self.assertEqual(d.scene, "neutral")
        self.assertTrue(d.ready_for_speech)

        # First conversation ends -> enters 90s dwell seated at neutral desk
        d.request_return()
        d.update()
        self.assertEqual(d.scene, "neutral")
        self.assertFalse(d.ready_for_speech)
        self.assertNotEqual(player.played[-1], "walk_away")  # Did not immediately leave!

        # 30 seconds into dwell, visitor asks another question
        now[0] += 30.0
        d.request_engagement()
        d.update()
        # Wilhelm is already seated at neutral desk: ready for speech immediately!
        self.assertEqual(d.scene, "neutral")
        self.assertTrue(d.ready_for_speech)
        self.assertEqual(player.played[-1], "walk_in")  # No redundant walk_in needed

        # Second conversation ends -> refreshes dwell window
        d.request_return()
        d.update()
        self.assertEqual(d.scene, "neutral")

        # 95 seconds elapse with no further visitor interaction -> dwell expires
        now[0] += 95.0
        d.update(idle=True)
        self.assertEqual(player.played[-1], "walk_away")

        player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertTrue(d.is_away)
        self.assertTrue(d.settled)

    def test_prolonged_absence_departure_and_active_summon_return(self):
        hour = [14]  # Daytime
        config = {
            "schedule": {
                "enabled": False,
                "prolonged_absence_seconds": 120,
            }
        }
        player = FakePlayer()
        now = [1000.0]
        d = SceneDirector(
            self.catalog,
            player,
            config=config,
            clock=lambda: now[0],
            wall_clock=lambda: hour[0],
        )

        d.update(idle=True)
        self.assertEqual(d.scene, "reading")

        # 125 seconds of absence / inactivity
        now[0] += 125.0
        d.update(idle=True)
        self.assertEqual(player.played, ["put_away_book"])

        player.finish()
        d.update()
        self.assertEqual(player.played, ["put_away_book", "walk_away"])

        player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertTrue(d.is_away)

        # Visitor approaches and engages
        d.request_engagement()
        d.update()
        self.assertEqual(player.played[-1], "walk_in")
        self.assertFalse(d.ready_for_speech)

        player.finish()
        d.update()
        self.assertEqual(d.scene, "neutral")
        self.assertTrue(d.ready_for_speech)

    def test_empty_room_alias_and_properties(self):
        d = self.director
        # Route alias
        self.assertEqual(d._route("reading", "empty_room"), ["put_away_book", "walk_away"])
        self.assertEqual(d._route("empty_room", "neutral"), ["walk_in"])

        # Action alias
        self.assertTrue(d.request_action("empty_room"))
        d.update()
        self.assertEqual(self.player.played, ["put_away_book"])
        self.player.finish()
        d.update()
        self.assertEqual(self.player.played, ["put_away_book", "walk_away"])
        self.player.finish()
        d.update()
        self.assertEqual(d.scene, "away")
        self.assertTrue(d.is_away)
        self.assertTrue(d.is_empty_room)


if __name__ == "__main__":
    unittest.main()
