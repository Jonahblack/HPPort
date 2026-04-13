import numpy as np, cv2
from .landmarks import mediapipe_landmarks

def simple_align(face_bgr, size=256):
    h, w = face_bgr.shape[:2]
    s = min(h, w)
    y0 = (h - s) // 2; x0 = (w - s) // 2
    crop = face_bgr[y0:y0+s, x0:x0+s]
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)

def landmarks_and_aligned(face_bgr, size=256):
    lm = mediapipe_landmarks(face_bgr)
    aligned = simple_align(face_bgr, size=size)
    return lm, aligned
