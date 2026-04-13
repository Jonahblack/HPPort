from src.detection.motion import MotionDetector
import numpy as np
def test_motion_smoke():
    det = MotionDetector(min_score=0.01, failsafe_frames=10, debounce_ms=0)
    f0 = np.zeros((120,160,3), dtype=np.uint8)
    f1 = f0.copy(); f1[30:60,40:80] = 255
    assert det.poll(f0) is None
    assert det.poll(f1) is None or isinstance(det.poll(f1), dict)
