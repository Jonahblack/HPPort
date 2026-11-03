"""Main-thread scene intentions, compatible routes, and source-endpoint checkpoints."""

from collections import deque
import random
import time


class SceneDirector:
    def __init__(self, catalog, player, config=None, preview=False, clock=time.monotonic):
        self.catalog, self.player = catalog, player
        self.config = config or {}
        self.preview = preview
        self.clock = clock
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
        self._schedule_idle()
        self._schedule_activity()
        for spec in self.clips.values():
            if spec.get("available", True):
                player.register_video(spec)
        player.prepare("look_up")

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

    @property
    def ready_for_speech(self):
        return self.engaging and self.scene == self.target and self.active is None and not self.error

    @property
    def settled(self):
        return self.active is None and self.target is None and not self.error

    def request_engagement(self):
        if self.engaging:
            return
        self.return_scene = self.target or (self.clips[self.active]["exit_scene"] if self.active else self.scene)
        self.return_scene = self.catalog["scenes"].get(self.return_scene, {}).get("return_scene", self.return_scene)
        destination = self.catalog["scenes"].get(self.return_scene, {}).get("engagement_scene")
        self.target = destination or "engaged_book"
        self.engaging = True
        self._preview_action = None
        self.error = None

    def request_return(self):
        self.engaging = False
        self.target = self.return_scene
        self.error = None

    def request_action(self, name):
        spec = self.clips.get(name)
        if self.engaging or self.active or not spec or not self._enabled(spec):
            return False
        if self._route(self.scene, spec["entry_scene"]) is None:
            return False
        self.error = None
        self._preview_action = name
        self.target = spec["entry_scene"]
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
            self.player.prepare("look_up")
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
