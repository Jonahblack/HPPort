"""Main-thread scene intentions, compatible routes, and source-endpoint checkpoints."""

from collections import deque
import datetime
import random
import time


class SceneDirector:
    def __init__(self, catalog, player, config=None, preview=False, clock=time.monotonic, wall_clock=None):
        self.catalog, self.player = catalog, player
        self.config = config or {}
        self.preview = preview
        self.clock = clock
        self.wall_clock = wall_clock
        self.scene = catalog["initial_scene"]
        self.clips = {c["id"]: c for c in catalog["clips"]}
        self.disabled = set()
        self.target = None
        self.active = None
        self.error = None
        self.engaging = False
        self.return_scene = self.scene
        self._generation = 0
        self._completed = deque()
        self._preview_action = None
        self._idle_suspended = False
        self._last_action = None

        # Schedule and absence configuration
        self.schedule_config = self.config.get("schedule", {})
        self.schedule_enabled = bool(self.schedule_config.get("enabled", False))
        self.night_start_hour = int(self.schedule_config.get("night_start_hour", 22))
        self.night_end_hour = int(self.schedule_config.get("night_end_hour", 7))
        self.night_post_conversation_dwell_seconds = float(
            self.schedule_config.get("night_post_conversation_dwell_seconds", 90)
        )
        self.prolonged_absence_seconds = float(
            self.schedule_config.get(
                "prolonged_absence_seconds",
                self.schedule_config.get("inactivity_timeout_seconds", 0),
            )
        )
        self._night_dwell_until = None
        self._last_active_time = self.clock()
        self.is_present = True

        self._schedule_idle()
        self._schedule_activity()
        for spec in self.clips.values():
            if spec.get("available", True):
                player.register_video(spec)
        eng = self.catalog["scenes"].get(self.scene, {}).get("engagement_scene")
        route = self._route(self.scene, eng) if eng else None
        player.prepare(route[0] if route else "look_up")

    def _schedule_idle(self):
        low = max(1, float(self.config.get("action_interval_min", 30)))
        high = max(low, float(self.config.get("action_interval_max", 65)))
        self.next_idle = self.clock() + random.uniform(low, high)

    def _schedule_activity(self):
        low = max(1, float(self.config.get("activity_interval_min", 180)))
        high = max(low, float(self.config.get("activity_interval_max", 420)))
        self.next_activity = self.clock() + random.uniform(low, high)

    def _enabled(self, spec):
        return spec["id"] not in self.disabled and self.player.has_sequence(spec["id"]) and (self.preview or spec.get("runtime_enabled", False))

    def _route(self, start, target):
        if start == "empty_room":
            start = "away"
        if target == "empty_room":
            target = "away"
        pending = deque([(start, [])])
        visited = {start}
        while pending:
            scene, route = pending.popleft()
            if scene == target:
                return route
            for spec in self.clips.values():
                dest = spec["exit_scene"]
                if self._enabled(spec) and spec["entry_scene"] == scene and dest not in visited:
                    visited.add(dest)
                    pending.append((dest, route + [spec["id"]]))
        return None

    def get_time(self):
        if self.wall_clock is not None:
            val = self.wall_clock()
            if isinstance(val, (int, float)):
                if isinstance(val, int) and 0 <= val < 24:
                    return val
                return datetime.datetime.fromtimestamp(val)
            return val
        return datetime.datetime.now()

    def is_night(self, current_time=None):
        if current_time is None:
            current_time = self.get_time()
        if isinstance(current_time, int):
            hour = current_time
        elif hasattr(current_time, "hour"):
            hour = current_time.hour
        elif isinstance(current_time, float):
            hour = datetime.datetime.fromtimestamp(current_time).hour
        else:
            hour = 12

        start = self.night_start_hour
        end = self.night_end_hour
        if start > end:
            return hour >= start or hour < end
        elif start < end:
            return start <= hour < end
        else:
            return False

    @property
    def is_night_active(self):
        return self.schedule_enabled and self.is_night()

    @property
    def is_away(self):
        return self.scene in ("away", "empty_room")

    @property
    def is_empty_room(self):
        return self.is_away

    @property
    def is_prolonged_absence(self):
        if self.prolonged_absence_seconds > 0 and not self.engaging:
            return (self.clock() - self._last_active_time) >= self.prolonged_absence_seconds
        return False

    @property
    def should_be_away(self):
        if self.engaging:
            return False
        if self.is_night_active:
            if self._night_dwell_until is not None and self.clock() < self._night_dwell_until:
                return False
            return True
        if self.is_prolonged_absence:
            return True
        return False

    def set_active(self):
        self._last_active_time = self.clock()
        self.is_present = True

    def set_presence(self, present: bool):
        self.is_present = bool(present)
        if present:
            self.set_active()

    @property
    def ready_for_speech(self):
        return self.engaging and self.scene == self.target and self.active is None and not self.error

    @property
    def settled(self):
        return self.active is None and self.target is None and not self.error

    def request_engagement(self):
        if self.engaging:
            return
        self._last_active_time = self.clock()
        self._night_dwell_until = None
        current = self.target or (self.clips[self.active]["exit_scene"] if self.active else self.scene)
        if current in ("away", "empty_room"):
            self.return_scene = "away"
            destination = "neutral"
        elif current == "neutral" and self.is_night_active:
            self.return_scene = "away"
            destination = "neutral"
        else:
            self.return_scene = self.catalog["scenes"].get(current, {}).get("return_scene", current)
            destination = self.catalog["scenes"].get(self.return_scene, {}).get("engagement_scene")
        self.target = destination or "engaged_book"
        self.engaging = True
        self._preview_action = None
        self.error = None

    def request_return(self):
        self.engaging = False
        self._last_active_time = self.clock()
        self.error = None
        if self.schedule_enabled and self.is_night():
            if self.scene in ("neutral", "engaged_neutral", "away", "empty_room") or self.return_scene in ("away", "empty_room"):
                if self.night_post_conversation_dwell_seconds > 0:
                    self._night_dwell_until = self.clock() + self.night_post_conversation_dwell_seconds
                    self.target = "neutral"
                    return
        self._night_dwell_until = None
        self.target = self.return_scene

    def request_action(self, name):
        if name not in self.clips:
            alias = {
                "return_to_tinker_box": "return_to_tinker",
                "look_up_tinker": "look_up_from_tinker_box",
                "empty_room": "walk_away",
                "away": "walk_away",
            }.get(name)
            if alias in self.clips:
                name = alias
        spec = self.clips.get(name)
        if self.engaging or self.active or not spec or not self._enabled(spec):
            return False
        entry = spec["entry_scene"]
        if self._route(self.scene, entry) is None:
            return False
        self._last_active_time = self.clock()
        self.error = None
        self._preview_action = name
        self.target = entry
        return True

    def _start(self, name):
        token = self._generation + 1
        def complete():
            self._completed.append((token, name, self.player.last_error,
                                    getattr(self.player, "current_frame_index", 0) >= 0))
        if self.player.play(name, on_complete=complete):
            self._generation = token
            self.active = name
            return True
        return False

    def update(self, idle=False):
        while self._completed:
            token, name, error, presented = self._completed.popleft()
            if token != self._generation or name != self.active:
                continue
            self.active = None
            if error:
                self.disabled.add(name)
                self.error = f"{name}: {error}"
                # Do not claim a stable scene after an incomplete prop-changing action.
                if presented:
                    self.scene = "unresolved"
                self.target = None
                self.engaging = False
                continue
            self.scene = self.clips[name]["exit_scene"]
            entry = self.catalog["scenes"][self.clips[name]["entry_scene"]]
            if entry["activity"] != self.catalog["scenes"][self.scene]["activity"]:
                self._schedule_activity()
            self._last_action = name
            self._schedule_idle()
        if self.error or self.active:
            # Preload the requested follow-up while the committed action finishes.
            if self.active and self.target:
                route = self._route(self.clips[self.active]["exit_scene"], self.target)
                if route:
                    self.player.prepare(route[0])
            return
        if self.target is not None:
            route = self._route(self.scene, self.target)
            if route is None:
                self.error = f"No enabled route from {self.scene} to {self.target}"
                return
            if route:
                self._start(route[0])
                return
            if self._preview_action:
                name, self._preview_action = self._preview_action, None
                self.target = None
                if not self._start(name):
                    self._preview_action, self.target = name, self.scene
                return
            if self.engaging:
                return  # Keep the target to make visual readiness explicit.
            self.target = None
            self._schedule_idle()
        if not idle:
            self._idle_suspended = True
            return
        if self._idle_suspended:
            self._schedule_idle()
            self._schedule_activity()
            self._idle_suspended = False

        # Night / Away Schedule and Prolonged Inactivity
        if self.should_be_away:
            if not self.is_away:
                self.target = "away"
                route = self._route(self.scene, self.target)
                if route:
                    self._start(route[0])
                return
            else:
                self._schedule_idle()
                self._schedule_activity()
                return
        elif self.is_away:
            daytime = self.catalog.get("initial_scene", "reading")
            self.target = daytime
            route = self._route(self.scene, self.target)
            if route:
                self._start(route[0])
            return

        if self.clock() >= self.next_activity:
            allowed = self.config.get("activities", ["reading", "tinkering"])
            candidates = []
            for name, scene in self.catalog["scenes"].items():
                engagement = scene.get("engagement_scene")
                if name != self.scene and name == scene.get("activity") and name in allowed and engagement:
                    # Activities must be reachable AND support a full engagement/return cycle.
                    if self._route(self.scene, name) and self._route(name, engagement) and self._route(engagement, name):
                        candidates.append(name)
            self._schedule_activity()
            if candidates:
                self.target = random.choice(candidates)
                return
        if self.clock() < self.next_idle:
            eng = self.catalog["scenes"].get(self.scene, {}).get("engagement_scene")
            route = self._route(self.scene, eng) if eng else None
            self.player.prepare(route[0] if route else "look_up")
            return
        choices = [c["id"] for c in self.clips.values() if self._enabled(c) and c.get("category") in ("activity_action", "resting_loop") and c["entry_scene"] == self.scene and c["exit_scene"] == self.scene]
        alternatives = [name for name in choices if name != self._last_action]
        if choices:
            self._start(random.choice(alternatives or choices))
        else:
            self._schedule_idle()

    def close(self):
        self._generation += 1
        self._completed.clear()
        self.player.close()
