"""Bounded background decoding; pygame surfaces and callbacks stay on the display thread."""

from collections import deque
from dataclasses import dataclass
import math
import queue
import threading
import time

import pygame


@dataclass(frozen=True)
class VideoFrame:
    index: int
    rgb: object


class FrameDecoder:
    """One local video, with a byte-limited queue and cancellable producer."""

    def __init__(self, spec, memory_bytes, max_width=960, capture_factory=None):
        self.spec = spec
        self.memory_bytes = memory_bytes
        self.max_width = max_width
        self.frames = queue.Queue(maxsize=1)
        self.cancelled = threading.Event()
        self.ready = threading.Event()
        self.done = threading.Event()
        self.error = None
        self.fps = float(spec.get("source_fps", 24))
        self.count = 0
        self.size = None
        self.queue_bytes = 0
        self._capture_factory = capture_factory
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"video-{spec['id']}")
        self.thread.start()

    def _run(self):
        cap = None
        try:
            import cv2
            if self._capture_factory:
                cap = self._capture_factory(self.spec["path"])
            else:
                # Avoid spawning a machine-sized codec pool for each prefetched clip.
                if hasattr(cv2, "CAP_PROP_N_THREADS"):
                    try:
                        cap = cv2.VideoCapture(self.spec["path"], cv2.CAP_FFMPEG,
                                               [cv2.CAP_PROP_N_THREADS, 1])
                    except cv2.error:
                        cap = None
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    cap = cv2.VideoCapture(self.spec["path"])
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open {self.spec['path']}")
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not math.isfinite(fps) or fps <= 0:
                raise ValueError("Video has no valid frame rate")
            if abs(fps - self.fps) > 0.05:
                raise ValueError(f"FPS mismatch: manifest {self.fps}, media {fps}")
            width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            start = self.spec.get("start_frame", 0)
            end = self.spec.get("end_frame") or total
            if width <= 0 or height <= 0 or not 0 <= start < end <= total:
                raise ValueError("Invalid video dimensions or source range")
            scale = min(1.0, self.max_width / width)
            # Leave room for the producer, pending presentation frame and retained endpoint.
            scale = min(scale, math.sqrt(self.memory_bytes / (width * height * 3 * 5)))
            self.size = (max(1, int(width * scale)), max(1, int(height * scale)))
            frame_bytes = self.size[0] * self.size[1] * 3
            slots = max(1, min(12, int(self.memory_bytes // frame_bytes) - 4))
            self.frames = queue.Queue(maxsize=slots)
            self.queue_bytes = slots * frame_bytes
            self.count = end - start
            if start:
                if not cap.set(cv2.CAP_PROP_POS_FRAMES, start):
                    raise RuntimeError("Could not seek to source in-point")
            for index in range(self.count):
                if self.cancelled.is_set():
                    break
                ok, bgr = cap.read()
                if not ok:
                    raise RuntimeError(f"Video ended early at frame {index}/{self.count}")
                if (width, height) != self.size:
                    bgr = cv2.resize(bgr, self.size, interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                while not self.cancelled.is_set():
                    try:
                        self.frames.put(VideoFrame(index, rgb), timeout=0.05)
                        self.ready.set()
                        break
                    except queue.Full:
                        continue
        except Exception as exc:
            self.error = str(exc)
        finally:
            if cap is not None:
                cap.release()
            self.done.set()

    def close(self):
        self.cancelled.set()


class BufferedVideoPlayer:
    """Present every source frame, freeze on underflow, and retain the actual endpoint.

    At most one active and one prefetched decoder share the configured RGB budget.
    No OpenCV I/O, bulk image loading, or whole-clip scaling runs on the display thread.
    """

    def __init__(self, memory_mb=64, max_width=960, clock=time.monotonic, decoder_factory=FrameDecoder,
                 preparation_timeout=15):
        self.memory_bytes = int(memory_mb * 1024 * 1024)
        if self.memory_bytes < 1024 * 1024 or max_width < 16:
            raise ValueError("Video budget must be >= 1 MiB and width >= 16")
        self.max_width = max_width
        self.clock = clock
        self.decoder_factory = decoder_factory
        self.preparation_timeout = preparation_timeout
        self.sequences = {}
        self.sequence_metadata = {}
        self.active_sequence_id = None
        self.is_playing = False
        self.is_locked = False
        self.current_frame_index = 0
        self.frames = ()  # Compatibility for diagnostics; videos are never stored as whole clips.
        self.last_surface = None
        self.last_error = None
        self.stalls = 0
        self.preparation_waits = 0
        self.last_playback = None
        self._active = None
        self._prefetch = None
        self._retired = deque()
        self._callback = None
        self._next_due = None
        self._last_poll = None
        self._outgoing = None
        self._fade_ms = 0
        self._started = None
        self._scaled = None
        self._scaled_key = None
        self._starved = False

    def register_video(self, spec):
        self.sequences[spec["id"]] = spec
        self.sequence_metadata[spec["id"]] = {"fps": spec["source_fps"], "label": spec["id"]}

    def has_sequence(self, name):
        return name in self.sequences

    def _retire(self, decoder):
        if decoder is not None:
            decoder.close()
            self._retired.append(decoder)

    def prepare(self, name):
        self._retired = deque(d for d in self._retired if d.thread.is_alive())
        if name not in self.sequences:
            return False
        if self._active and self.active_sequence_id == name:
            return True
        if self._prefetch and self._prefetch.spec["id"] == name:
            return True
        if self._prefetch:
            self._retire(self._prefetch)
            self._prefetch = None
        # A cancelled decoder must release its buffers before replacing its budget slot.
        if self._retired:
            return False
        self._prefetch = self.decoder_factory(self.sequences[name], self.memory_bytes // 2, self.max_width)
        return True

    def play(self, name, on_complete=None, outgoing_surface=None, **_):
        if self.is_playing or not self.prepare(name):
            return False
        self._active, self._prefetch = self._prefetch, None
        self.active_sequence_id = name
        self.current_frame_index = -1
        self.is_playing = self.is_locked = True
        self._callback = on_complete
        self._next_due = self._started = self._last_poll = None
        self._starved = False
        self._requested = self.clock()
        self._initial_stalls = self.stalls
        self._outgoing = outgoing_surface if outgoing_surface is not None else self.last_surface
        self._fade_ms = max(0, self.sequences[name].get("crossfade_ms", 0))
        self.last_error = None
        return True

    def get_native_size(self):
        return self._active.size if self._active and self._active.size else (self.last_surface.get_size() if self.last_surface else (1280, 720))

    def get_progress(self):
        if not self.is_playing:
            return 1.0 if self.last_surface is not None else 0.0
        count = self._active.count if self._active else 0
        return min(1.0, max(0.0, (self.current_frame_index + 1) / count)) if count else 0.0

    def _finish(self, error=None):
        callback, self._callback = self._callback, None
        self.is_playing = self.is_locked = False
        self.last_error = error
        now = self.clock()
        self.last_playback = {
            "id": self.active_sequence_id,
            "preparation_seconds": (self._started if self._started is not None else now) - self._requested,
            "presentation_seconds": now - self._started if self._started is not None else 0,
            "frames_presented": self.current_frame_index + 1,
            "underflow_events": self.stalls - self._initial_stalls,
            "error": error,
        }
        self._retire(self._active)
        self._active = None
        self._outgoing = None
        if callback:
            callback()  # Director enqueues completion; it never starts another clip from here.

    def update(self, target_size=None):
        now = self.clock()
        decoder = self._active
        if self.is_playing and decoder:
            if self._started is None and now - self._requested > self.preparation_timeout:
                self._finish("Video preparation timed out")
            elif decoder.error:
                self._finish(decoder.error)
            elif self._next_due is None or now + 1e-8 >= self._next_due:
                try:
                    frame = decoder.frames.get_nowait()
                except queue.Empty:
                    if decoder.done.is_set() and self.current_frame_index == decoder.count - 1 and decoder.count:
                        self._finish()
                    elif not self._starved:
                        if self._started is None:
                            self.preparation_waits += 1
                        else:
                            self.stalls += 1
                        self._starved = True
                else:
                    if self._started is None:
                        self._started = now
                    period = 1.0 / decoder.fps
                    if self._next_due is None or self._starved or now - self._next_due > period * 2:
                        self._next_due = now + period
                    else:
                        self._next_due += period
                    self._starved = False
                    self.current_frame_index = frame.index
                    # frombuffer retains the NumPy allocation; no worker touches it after enqueue.
                    self.last_surface = pygame.image.frombuffer(frame.rgb, decoder.size, "RGB")
                    if pygame.display.get_surface() is not None:
                        # Display-native pixels use SDL's fast blit/scale path instead of 24-bit RGB.
                        self.last_surface = self.last_surface.convert()
                    self._scaled_key = None
        self._last_poll = now
        surface = self.last_surface
        if surface is None:
            return self._outgoing
        key = (id(surface), target_size)
        if self._scaled_key != key:
            self._scaled = pygame.transform.smoothscale(surface, target_size) if target_size and surface.get_size() != target_size else surface
            self._scaled_key = key
        result = self._scaled
        if self.is_playing and self._outgoing is not None and self._started is not None and self._fade_ms:
            alpha = min(1.0, (now - self._started) * 1000 / self._fade_ms)
            if alpha < 1:
                outgoing = self._outgoing
                if outgoing.get_size() != result.get_size():
                    outgoing = pygame.transform.smoothscale(outgoing, result.get_size())
                blended = outgoing.copy()
                top = result.copy()
                top.set_alpha(round(alpha * 255))
                blended.blit(top, (0, 0))
                return blended
            self._outgoing = None
        return result

    def get_current_frame(self):
        return self.last_surface

    def stop(self):
        self._retire(self._active)
        self._active = None
        self._callback = None
        self.is_playing = self.is_locked = False

    def close(self):
        self.stop()
        self._retire(self._prefetch)
        self._prefetch = None
        for decoder in self._retired:
            decoder.thread.join(timeout=1)
        self._retired.clear()
