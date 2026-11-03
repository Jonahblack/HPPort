"""Monotonic display pacing independent of SDL millisecond timer quantization."""

import time


class FrameClock:
    def __init__(self, now=time.perf_counter, sleep=time.sleep):
        self.now, self.sleep = now, sleep
        self.deadline = None
        self.previous = now()

    def tick(self, fps):
        period = 1.0 / fps
        now = self.now()
        if self.deadline is None:
            self.deadline = now + period
        if now < self.deadline:
            self.sleep(self.deadline - now)
        finished = self.now()
        self.deadline += period
        if self.deadline < finished:
            self.deadline = finished + period
        elapsed = (finished - self.previous) * 1000
        self.previous = finished
        return elapsed
