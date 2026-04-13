#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import cv2
import numpy as np


def detect_face_markers(frame_bgr, expected=4, debug=False):
    H, W = frame_bgr.shape[:2]
    m = min(H, W)

    blur = cv2.GaussianBlur(frame_bgr, (5, 5), 0)
    hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)

    # Heuristics for tan/yellow/orange circles
    ranges = [
        ((5, 60, 120), (22, 255, 255)),   # orange-yellow
        ((20, 20, 160), (35, 180, 255)),  # light tan
    ]
    mask = np.zeros((H, W), dtype=np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_r = int(m * 0.04)
    max_r = int(m * 0.20)

    circles = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < np.pi * (min_r ** 2) * 0.4:
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

    # Sort by radius desc, then x asc; take expected
    circles.sort(key=lambda t: (-t[2], t[0]))
    circles = circles[:expected]
    # Left-to-right
    circles.sort(key=lambda t: t[0])

    if debug:
        dbg = frame_bgr.copy()
        for i, (x, y, r, _) in enumerate(circles):
            cv2.circle(dbg, (x, y), r, (0, 255, 0), 2)
            cv2.putText(dbg, f"{i}", (x-10, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2, cv2.LINE_AA)
        return circles, mask, dbg
    return circles


def main():
    ap = argparse.ArgumentParser(description="Auto-calibrate slot positions by detecting tan/yellow face circles")
    ap.add_argument("--template", required=True, help="Input template JSON with background_video and slots")
    ap.add_argument("--out", required=True, help="Output template JSON path")
    ap.add_argument("--expected", type=int, default=4, help="Expected number of markers to find")
    ap.add_argument("--anchor", choices=["center", "mouth_center"], default="center", help="Anchor type to use for slots")
    ap.add_argument("--debug-dir", default=None, help="If set, writes mask and overlay images here")
    args = ap.parse_args()

    tpath = Path(args.template)
    data = json.loads(tpath.read_text())
    video = data.get("background_video")
    if not video:
        raise SystemExit("Template must define background_video")
    cap = cv2.VideoCapture(video)
    ok, frame = cap.read(); cap.release()
    if not ok:
        raise SystemExit(f"Cannot open background video: {video}")

    det = detect_face_markers(frame, expected=args.expected, debug=args.debug_dir is not None)
    if args.debug_dir is not None:
        circles, mask, dbg = det
        dd = Path(args.debug_dir); dd.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dd / "mask.png"), mask)
        cv2.imwrite(str(dd / "overlay.png"), dbg)
    else:
        circles = det

    if not circles:
        raise SystemExit("No markers detected; adjust HSV ranges or supply --debug-dir")

    # Update slots left-to-right
    slots = data.get("slots", [])
    n = min(len(slots), len(circles))
    if n == 0:
        raise SystemExit("Template has no slots to update")
    for i in range(n):
        x, y, r, _ = circles[i]
        if args.anchor == "mouth_center":
            y = int(y + 0.12 * r)  # nudge down to rough mouth position
        slots[i]["position"] = [int(x), int(y)]
        slots[i]["anchor"] = args.anchor

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2))
    print(out_path)


if __name__ == "__main__":
    main()

