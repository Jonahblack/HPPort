import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path


def _bootstrap_hauntpi_imports() -> None:
    hauntpi_root = Path(__file__).resolve().parent / "HauntPi" / "HauntPi"
    if hauntpi_root.exists():
        hauntpi_path = str(hauntpi_root)
        if hauntpi_path not in sys.path:
            sys.path.insert(0, hauntpi_path)


_bootstrap_hauntpi_imports()

try:
    from src.common.camera import Camera
except Exception:  # pragma: no cover - runtime dependency
    Camera = None

try:
    from src.detection.hailo_person import HailoPerson
except Exception:  # pragma: no cover - runtime dependency
    HailoPerson = None

try:
    from src.detection.motion import MotionDetector
except Exception:  # pragma: no cover - runtime dependency
    MotionDetector = None


@dataclass
class CameraStatus:
    available: bool = False
    mode: str = "disabled"
    last_person_seen_at: float = 0.0
    last_trigger_at: float = 0.0
    last_error: str = ""


class PersonTriggerService:
    def __init__(self, config: dict, root_dir: Path):
        self.config = config
        self.root_dir = root_dir
        self.status = CameraStatus()
        self._camera = None
        self._person_detector = None
        self._motion_detector = None
        self._thread = None
        self._running = False
        self._pending_trigger = False
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.config.get("enabled", True):
            self.status.mode = "disabled"
            return
        try:
            self._init_pipeline()
        except Exception as exc:
            self.status.available = False
            self.status.mode = "unavailable"
            self.status.last_error = str(exc)
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="camera-trigger", daemon=True)
        self._thread.start()

    def _init_pipeline(self) -> None:
        if Camera is None:
            raise RuntimeError("Camera backend is unavailable.")

        self._camera = Camera(
            index=int(self.config.get("index", 0)),
            width=int(self.config.get("width", 1280)),
            height=int(self.config.get("height", 720)),
            fps=int(self.config.get("fps", 20)),
            backend=str(self.config.get("backend", "auto")),
        )

        hef_path = self.root_dir / str(self.config.get("hef_path", "models/yolov5m.hef"))
        if HailoPerson is not None and hef_path.exists():
            self._person_detector = HailoPerson(
                hef_path=str(hef_path),
                threshold=float(self.config.get("hailo_threshold", 0.55)),
            )
            self.status.mode = "hailo_person"
        elif MotionDetector is not None and self.config.get("motion_fallback_enabled", True):
            self._motion_detector = MotionDetector()
            self.status.mode = "motion_fallback"
        else:
            raise RuntimeError("No person or motion detector is available.")

        self.status.available = True

    def _run_loop(self) -> None:
        poll_interval = float(self.config.get("poll_interval_seconds", 0.12))
        cooldown_seconds = float(self.config.get("cooldown_seconds", 15.0))
        self.status.last_trigger_at = time.monotonic() - cooldown_seconds

        while self._running:
            try:
                ok, frame = self._camera.read()
                if not ok or frame is None:
                    time.sleep(poll_interval)
                    continue

                triggered = False
                if self._person_detector is not None:
                    detections = self._person_detector.persons(frame)
                    if detections:
                        self.status.last_person_seen_at = time.monotonic()
                        triggered = True
                elif self._motion_detector is not None:
                    event = self._motion_detector.poll(frame)
                    if event:
                        self.status.last_person_seen_at = time.monotonic()
                        triggered = True

                if triggered:
                    now = time.monotonic()
                    if now - self.status.last_trigger_at >= cooldown_seconds:
                        with self._lock:
                            self._pending_trigger = True
                        self.status.last_trigger_at = now
                time.sleep(poll_interval)
            except Exception as exc:
                self.status.last_error = str(exc)
                self.status.available = False
                self.status.mode = "unavailable"
                self._running = False

    def consume_trigger(self) -> bool:
        with self._lock:
            pending = self._pending_trigger
            self._pending_trigger = False
            return pending

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._camera:
            try:
                self._camera.release()
            except Exception:
                pass
