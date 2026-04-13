import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class MarkerConfig:
    expected: int
    # HSV ranges to detect the tan/yellow/orange face circles
    hsv_ranges: Optional[List[Tuple[Tuple[int, int, int], Tuple[int, int, int]]]] = None
    # min/max relative radius vs min(H, W)
    min_r_ratio: float = 0.04
    max_r_ratio: float = 0.20
    # smoothing factor for EMA (higher = smoother)
    smooth_alpha: float = 0.8
    # maximum frames to keep last-known-good when detection fails
    dropout_max: int = 8
    # max assignment distance as fraction of frame diagonal
    max_match_dist_ratio: float = 0.15
    # anchor nudge ratio (used when anchor == mouth_center)
    mouth_nudge_ratio: float = 0.12


def _default_hsv_ranges():
    # Two broad ranges that generally capture tan/yellow/orange in many scenes
    return [
        ((5, 60, 120), (22, 255, 255)),   # orange-yellow
        ((20, 20, 160), (35, 200, 255)),  # light tan
    ]


def detect_markers(frame_bgr, cfg: MarkerConfig, debug=False):
    H, W = frame_bgr.shape[:2]
    m = min(H, W)
    blur = cv2.GaussianBlur(frame_bgr, (5, 5), 0)
    hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
    ranges = cfg.hsv_ranges or _default_hsv_ranges()
    mask = np.zeros((H, W), dtype=np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_r = int(m * cfg.min_r_ratio)
    max_r = int(m * cfg.max_r_ratio)
    circles = []
    for c in contours:
        area = cv2.contourArea(c)
        if area <= 1:
            continue
        (x, y), r = cv2.minEnclosingCircle(c)
        r = int(r)
        if r < min_r or r > max_r:
            continue
        peri = cv2.arcLength(c, True) + 1e-6
        circularity = 4 * np.pi * area / (peri * peri)
        if circularity < 0.65:
            continue
        circles.append((int(x), int(y), r, circularity))
    # pick largest expected, then left->right
    circles.sort(key=lambda t: (-t[2], t[0]))
    circles = circles[: cfg.expected]
    circles.sort(key=lambda t: t[0])
    if not debug:
        return circles, mask, None
    dbg = frame_bgr.copy()
    for i, (x, y, r, _) in enumerate(circles):
        cv2.circle(dbg, (x, y), r, (0, 255, 0), 2)
        cv2.putText(dbg, f"{i}", (x - 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
    return circles, mask, dbg


class MarkerTracker:
    def __init__(self, cfg: MarkerConfig, frame_shape: Tuple[int, int, int]):
        self.cfg = cfg
        self.H, self.W = frame_shape[:2]
        self.prev = None  # list of (x, y, r)
        self.dropout = None  # list of counts
        self.diag = float(np.hypot(self.W, self.H))

    def _init_state(self, circles):
        base = [(c[0], c[1], c[2]) for c in circles]
        self.prev = base
        self.dropout = [0 for _ in base]
        return base

    def _match(self, circles):
        # nearest-neighbor from prev -> curr with distance cap
        if self.prev is None:
            return [(c[0], c[1], c[2]) for c in circles]
        used = set()
        matched = []
        max_d = self.diag * self.cfg.max_match_dist_ratio
        for (px, py, pr) in self.prev:
            best_j, best_d = -1, 1e9
            for j, c in enumerate(circles):
                if j in used:
                    continue
                d = float(np.hypot(c[0] - px, c[1] - py))
                if d < best_d:
                    best_d, best_j = d, j
            if best_j >= 0 and best_d <= max_d:
                used.add(best_j)
                matched.append((circles[best_j][0], circles[best_j][1], circles[best_j][2]))
            else:
                matched.append(None)  # miss
        return matched

    def update(self, frame_bgr) -> Optional[List[Tuple[int, int, int]]]:
        circles, _, _ = detect_markers(frame_bgr, self.cfg, debug=False)
        if self.prev is None:
            if not circles:
                return None
            return self._init_state(circles)

        matched = self._match(circles)
        out = []
        alpha = self.cfg.smooth_alpha
        for i, m in enumerate(matched):
            if m is None:
                # dropout: keep last known, increment counter
                self.dropout[i] += 1
                if self.dropout[i] > self.cfg.dropout_max:
                    # give up until we see a new detection: keep previous stale but don't smooth
                    out.append(self.prev[i])
                else:
                    out.append(self.prev[i])
                continue
            self.dropout[i] = 0
            px, py, pr = self.prev[i]
            mx, my, mr = m
            sx = int(alpha * px + (1 - alpha) * mx)
            sy = int(alpha * py + (1 - alpha) * my)
            sr = int(alpha * pr + (1 - alpha) * mr)
            out.append((sx, sy, sr))
        self.prev = out
        return out

