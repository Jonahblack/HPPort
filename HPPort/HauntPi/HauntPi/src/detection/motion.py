import cv2, numpy as np, time

class MotionDetector:
    def __init__(self, bg_history=500, var_threshold=50, min_score=0.02,
                 failsafe_frames=300, debounce_ms=1200):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=bg_history, varThreshold=var_threshold, detectShadows=True)
        self.min_score = float(min_score); self.failsafe_frames = int(failsafe_frames); self.debounce_ms = int(debounce_ms)
        self._last_trigger_ts = 0.0; self._frames_since_last = 0

    def poll(self, frame_bgr):
        fg = self.bg.apply(frame_bgr)
        score = float(np.sum(fg)) / (fg.shape[0] * fg.shape[1])
        self._frames_since_last += 1; now = time.time() * 1000.0
        if (score > self.min_score or self._frames_since_last >= self.failsafe_frames) and (now - self._last_trigger_ts >= self.debounce_ms):
            self._last_trigger_ts = now; self._frames_since_last = 0
            return {"triggered": True, "motion_score": score}
        return None
