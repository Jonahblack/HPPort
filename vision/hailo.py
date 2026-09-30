"""Raspberry Pi camera capture and CPU motion detection with Hailo diagnostics.

The legacy driver name is retained for configuration compatibility. Importing the
Hailo SDK does not activate inference; the current detector analyzes motion.
"""

import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

from vision.base import BaseVisionDetector


class HailoVision(BaseVisionDetector):
    """Camera-backed detector for Raspberry Pi 5 with graceful backend fallback."""

    def __init__(self, config: Dict[str, Any]):
        vision_cfg = config.get("vision", {})
        hardware_cfg = config.get("hardware", {})

        self.confidence_threshold = float(vision_cfg.get("confidence_threshold", 0.55))
        self.poll_interval = max(0.01, float(vision_cfg.get("poll_interval_seconds", 0.1)))
        self.cam_width = int(vision_cfg.get("camera_width", 320))
        self.cam_height = int(vision_cfg.get("camera_height", 240))
        self.target_fps = max(1, int(vision_cfg.get("camera_fps", 15)))
        self.analysis_width = max(32, int(vision_cfg.get("analysis_width", 320)))
        self.camera_backend = str(vision_cfg.get("camera_backend", "auto")).lower()
        self.camera_device_index = int(vision_cfg.get("camera_device_index", 0))

        self.model_path = os.path.join(
            hardware_cfg.get("models_dir", "/mnt/portrait/models"),
            "hailo",
            "yolov8s_person.hef",
        )

        self._running = False
        self._latest_detected = False
        self._latest_confidence = 0.0
        self._hailo_initialized = False
        self._camera_driver = "none"
        self._camera_error = ""
        self._manual_detect_until = 0.0

        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._fps_counter = 0.0
        self._frame_count = 0
        self._last_fps_calc = time.monotonic()
        self._bounding_box: Optional[Tuple[int, int, int, int]] = None
        self._prev_gray: Optional[np.ndarray] = None
        self._smoothed_gaze_x = 0.0
        self._smoothed_gaze_y = 0.0
        self._smoothed_distance = 1.0
        self._preview_frame = None
        self._preview_key = None
        self._preview_surface = None
        self._standby_frame = None
        self._opencv_configured = False

    def start(self) -> None:
        """Initialize Hailo runtime diagnostics and camera capture thread."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._prev_gray = None
        print(
            f"[Vision] Starting camera capture & motion detector "
            f"(Target: {self.cam_width}x{self.cam_height} @ {self.target_fps}fps, backend={self.camera_backend})..."
        )

        try:
            import hailo  # type: ignore  # noqa: F401

            print("[Vision] Hailo SDK available; inference is not configured. Using CPU motion detection.")
            self._hailo_initialized = True
        except ImportError:
            print("[Vision] Hailo SDK unavailable. Using CPU motion detection.")
            self._hailo_initialized = False

        if not os.path.exists(self.model_path):
            print(f"[Vision] Notice: HEF model not found at {self.model_path}. Camera preview will still run.")

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

    def simulate_detection(self, detected: bool, duration_seconds: float = 4.0) -> None:
        """Support manual wake testing from the keyboard in hardware mode."""
        if detected:
            self._manual_detect_until = time.monotonic() + duration_seconds
            print(f"[Vision] Manual detection override enabled for {duration_seconds:.1f}s.")
        else:
            self._manual_detect_until = 0.0
            print("[Vision] Manual detection override cleared.")

    def _capture_loop(self) -> None:
        """Grab frames from the first working backend and run simple motion detection."""
        source = self._open_camera_source()
        next_analysis = 0.0
        analysis = (False, 0.0, None)
        try:
            while self._running:
                loop_start = time.monotonic()
                frame_rgb = self._read_camera_frame(source) if source is not None else None
                if frame_rgb is None:
                    frame_rgb = self._build_standby_frame()
                    analysis = (False, 0.0, None)
                    self._prev_gray = None
                elif loop_start >= next_analysis:
                    analysis = self._analyze_frame(frame_rgb)
                    next_analysis = loop_start + self.poll_interval
                detected, confidence, bbox = analysis

                if loop_start < self._manual_detect_until:
                    detected = True
                    confidence = max(confidence, 0.94)
                    if bbox is None:
                        bbox = self._default_manual_bbox()

                if detected and bbox is not None:
                    bx, by, bw, bh = bbox
                    height, width = frame_rgb.shape[:2]
                    target_x = max(-1.0, min(1.0, (bx + bw / 2.0 - width / 2.0) / (width / 2.0)))
                    target_y = max(-1.0, min(1.0, (by + bh / 2.0 - height / 2.0) / (height / 2.0)))
                    target_dist = max(0.5, min(2.0, height * 0.45 / max(1.0, float(bh))))
                else:
                    target_x, target_y, target_dist = 0.0, 0.0, 1.0

                with self._frame_lock:
                    # Published frames are immutable snapshots. The display can
                    # retain a reference without copying camera-sized buffers.
                    self._latest_frame = frame_rgb
                    self._latest_detected = detected
                    self._latest_confidence = confidence
                    self._bounding_box = bbox
                    alpha = 0.18
                    self._smoothed_gaze_x += alpha * (target_x - self._smoothed_gaze_x)
                    self._smoothed_gaze_y += alpha * (target_y - self._smoothed_gaze_y)
                    self._smoothed_distance += alpha * (target_dist - self._smoothed_distance)

                self._frame_count += 1
                now = time.monotonic()
                if now - self._last_fps_calc >= 1.0:
                    self._fps_counter = self._frame_count / (now - self._last_fps_calc)
                    self._frame_count = 0
                    self._last_fps_calc = now

                interval = 1.0 / self.target_fps if source is not None else 0.25
                self._stop_event.wait(max(0.005, interval - (time.monotonic() - loop_start)))
        except Exception as exc:
            self._camera_error = f"Camera capture stopped: {exc}"
            print(f"[Vision] {self._camera_error}")
        finally:
            self._close_camera_source(source)
            self._running = False

    def _open_camera_source(self) -> Optional[Dict[str, Any]]:
        backends = self._candidate_backends()
        errors = []

        for backend in backends:
            try:
                if backend == "picamera2":
                    source = self._open_picamera2()
                elif backend == "gstreamer":
                    source = self._open_opencv_capture(self._libcamera_gstreamer_pipeline(), "gstreamer_libcamera")
                elif backend == "v4l2":
                    source = self._open_opencv_capture(self.camera_device_index, "v4l2_opencv", api_preference="v4l2")
                elif backend == "opencv":
                    source = self._open_opencv_capture(self.camera_device_index, "opencv_default")
                else:
                    continue
            except Exception as exc:
                errors.append(f"{backend}: {exc}")
                continue

            if source is not None:
                self._camera_error = ""
                return source

            errors.append(f"{backend}: unavailable")

        self._camera_driver = "standby"
        self._camera_error = "; ".join(errors) if errors else "No camera backend could be initialized."
        print(f"[Vision] Camera startup failed. {self._camera_error}")
        return None

    def _candidate_backends(self) -> Tuple[str, ...]:
        if self.camera_backend == "auto":
            return ("picamera2", "gstreamer", "v4l2", "opencv")
        mapping = {
            "picamera2": ("picamera2",),
            "gstreamer": ("gstreamer",),
            "v4l2": ("v4l2",),
            "opencv": ("opencv",),
        }
        return mapping.get(self.camera_backend, ("picamera2", "gstreamer", "v4l2", "opencv"))

    def _open_picamera2(self) -> Optional[Dict[str, Any]]:
        try:
            from picamera2 import Picamera2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Picamera2 is not installed") from exc

        picam = Picamera2()
        try:
            config = picam.create_video_configuration(
                # libcamera's BGR888 produces byte-ordered RGB NumPy pixels.
                main={"size": (self.cam_width, self.cam_height), "format": "BGR888"},
                controls={"FrameDurationLimits": (int(1_000_000 / self.target_fps), int(1_000_000 / self.target_fps))},
            )
            picam.configure(config)
            picam.start()
            time.sleep(0.2)

            test_frame = picam.capture_array()
            if test_frame is None or getattr(test_frame, "size", 0) == 0:
                raise RuntimeError("Picamera2 returned an empty frame")
        except Exception:
            picam.close()
            raise

        self._camera_driver = "picamera2"
        print("[Vision] Connected to Raspberry Pi CSI camera via Picamera2.")
        return {"type": "picamera2", "camera": picam}

    def _libcamera_gstreamer_pipeline(self) -> str:
        return (
            "libcamerasrc ! "
            f"video/x-raw,width={self.cam_width},height={self.cam_height},framerate={self.target_fps}/1 ! "
            "videoconvert ! appsink drop=true max-buffers=1 sync=false"
        )

    def _open_opencv_capture(
        self,
        source_ref: Any,
        driver_name: str,
        api_preference: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("opencv-python-headless is not installed") from exc

        cap_args = [source_ref]
        if api_preference == "v4l2":
            cap_args.append(cv2.CAP_V4L2)
        elif driver_name == "gstreamer_libcamera":
            cap_args.append(cv2.CAP_GSTREAMER)

        cap = cv2.VideoCapture(*cap_args)
        if not cap.isOpened():
            cap.release()
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cam_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cam_height)
        cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            return None

        self._camera_driver = driver_name
        source_label = source_ref if isinstance(source_ref, str) else f"/dev/video{self.camera_device_index}"
        print(f"[Vision] Connected to physical camera via {driver_name} ({source_label}).")
        return {"type": "opencv", "camera": cap}

    def _read_camera_frame(self, source: Dict[str, Any]) -> Optional[np.ndarray]:
        source_type = source["type"]

        if source_type == "picamera2":
            frame = source["camera"].capture_array()
            if frame is None:
                return None
            return self._normalize_to_rgb(frame)

        if source_type == "opencv":
            ok, frame = source["camera"].read()
            if not ok or frame is None:
                return None
            return self._normalize_to_rgb(frame, assume_bgr=True)

        return None

    def _close_camera_source(self, source: Optional[Dict[str, Any]]) -> None:
        if source is None:
            return

        try:
            if source["type"] == "picamera2":
                try:
                    source["camera"].stop()
                finally:
                    source["camera"].close()
            elif source["type"] == "opencv":
                source["camera"].release()
        except Exception:
            pass

    def _normalize_to_rgb(self, frame: np.ndarray, assume_bgr: bool = False) -> np.ndarray:
        if frame.ndim == 2:
            frame = np.stack([frame] * 3, axis=-1)
        elif frame.shape[2] == 4:
            frame = frame[:, :, :3]

        if assume_bgr:
            frame = frame[:, :, ::-1]

        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        return np.ascontiguousarray(frame)

    def _analyze_frame(self, frame_rgb: np.ndarray) -> Tuple[bool, float, Optional[Tuple[int, int, int, int]]]:
        try:
            import cv2  # type: ignore
        except ImportError:
            return False, 0.0, None

        if not self._opencv_configured:
            # Leave CPU capacity for speech recognition and local inference.
            cv2.setNumThreads(1)
            self._opencv_configured = True
        source_height, source_width = frame_rgb.shape[:2]
        analysis_width = min(source_width, self.analysis_width)
        analysis_height = max(1, round(source_height * analysis_width / source_width))
        if analysis_width < source_width:
            frame_rgb = cv2.resize(frame_rgb, (analysis_width, analysis_height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (11, 11), 0)

        if self._prev_gray is None or self._prev_gray.shape != gray.shape:
            self._prev_gray = gray
            return False, 0.0, None

        frame_delta = cv2.absdiff(self._prev_gray, gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self._prev_gray = gray

        largest_area = 0.0
        best_bbox = None
        reference_scale = (640 * 480) / (analysis_width * analysis_height)
        for contour in contours:
            area = cv2.contourArea(contour) * reference_scale
            if area < 1500 or area <= largest_area:
                continue

            x, y, box_width, box_height = cv2.boundingRect(contour)
            largest_area = area
            # Coordinates must refer to the original camera image for gaze/PiP.
            scale_x = source_width / analysis_width
            scale_y = source_height / analysis_height
            best_bbox = (round(x * scale_x), round(y * scale_y), round(box_width * scale_x), round(box_height * scale_y))

        if best_bbox is None:
            return False, 0.0, None

        confidence = min(0.98, max(0.60, largest_area / 8000.0))
        return confidence >= self.confidence_threshold, confidence, best_bbox

    def _default_manual_bbox(self) -> Tuple[int, int, int, int]:
        box_width = max(56, self.cam_width // 5)
        box_height = max(70, self.cam_height // 3)
        x = max(0, (self.cam_width - box_width) // 2)
        y = max(0, (self.cam_height - box_height) // 2)
        return (x, y, box_width, box_height)

    def _build_standby_frame(self) -> np.ndarray:
        if self._standby_frame is not None:
            return self._standby_frame
        frame = np.zeros((self.cam_height, self.cam_width, 3), dtype=np.uint8)
        frame[:, :] = [18, 24, 28]
        frame[::24, :, :] = [28, 36, 44]
        frame[:, ::24, :] = [28, 36, 44]

        cx = self.cam_width // 2
        cy = self.cam_height // 2
        frame[max(0, cy - 28) : min(self.cam_height, cy + 28), max(0, cx - 2) : min(self.cam_width, cx + 2), :] = [196, 167, 108]
        frame[max(0, cy - 2) : min(self.cam_height, cy + 2), max(0, cx - 28) : min(self.cam_width, cx + 28), :] = [196, 167, 108]

        self._standby_frame = frame
        return frame

    def is_person_detected(self) -> bool:
        if not self._running:
            return False
        if time.monotonic() < self._manual_detect_until:
            return True
        with self._frame_lock:
            return self._latest_detected

    def get_confidence(self) -> float:
        if time.monotonic() < self._manual_detect_until:
            return max(0.94, self._latest_confidence)
        with self._frame_lock:
            return self._latest_confidence

    def get_latest_frame(self, target_size: Optional[Tuple[int, int]] = None) -> Optional[Any]:
        """Return a cached preview; call from the display thread only."""
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            frame = self._latest_frame
            bbox = self._bounding_box
        key = (target_size, bbox)
        if frame is self._preview_frame and key == self._preview_key:
            return self._preview_surface

        try:
            import pygame  # type: ignore

            height, width, _ = frame.shape
            # frombuffer shares the immutable capture snapshot. Only the small
            # preview is copied/scaled before drawing detection annotations.
            surface = pygame.image.frombuffer(frame, (width, height), "RGB")
            preview_width, preview_height = target_size or (width, height)
            if (preview_width, preview_height) != (width, height):
                surface = pygame.transform.smoothscale(surface, (preview_width, preview_height))
            else:
                surface = surface.copy()

            if bbox is not None:
                bx, by, bw, bh = bbox
                bx = round(bx * preview_width / width)
                by = round(by * preview_height / height)
                bw = round(bw * preview_width / width)
                bh = round(bh * preview_height / height)
                rect = pygame.Rect(bx, by, bw, bh)
                pygame.draw.rect(surface, (52, 211, 153), rect, width=2)

                corner_radius = 8
                pygame.draw.line(surface, (56, 189, 248), (bx, by), (bx + corner_radius, by), 2)
                pygame.draw.line(surface, (56, 189, 248), (bx, by), (bx, by + corner_radius), 2)
                pygame.draw.line(surface, (56, 189, 248), (bx + bw, by + bh), (bx + bw - corner_radius, by + bh), 2)
                pygame.draw.line(surface, (56, 189, 248), (bx + bw, by + bh), (bx + bw, by + bh - corner_radius), 2)

            self._preview_frame = frame
            self._preview_key = key
            self._preview_surface = surface
            return surface
        except Exception:
            return None

    def get_status_info(self) -> Dict[str, Any]:
        manual_override = time.monotonic() < self._manual_detect_until
        with self._frame_lock:
            return {
                "driver": self._camera_driver,
                "hailo_initialized": self._hailo_initialized,
                "detector": "motion",
                "hailo_inference_active": False,
                "active": self._running,
                "fps": round(self._fps_counter, 1),
                "detected": self._latest_detected or manual_override,
                "confidence": round(max(self._latest_confidence, 0.94 if manual_override else 0.0), 2),
                "camera_error": self._camera_error,
                "model_path": self.model_path,
                "camera_backend": self.camera_backend,
            }

    def get_visitor_gaze(self) -> Tuple[float, float, float]:
        with self._frame_lock:
            return (
                round(float(self._smoothed_gaze_x), 3),
                round(float(self._smoothed_gaze_y), 3),
                round(float(self._smoothed_distance), 3),
            )

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        print("[Vision] Hailo detector & camera feed stopped.")
