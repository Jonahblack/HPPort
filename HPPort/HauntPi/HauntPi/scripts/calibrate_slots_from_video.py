#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import cv2


def load_template(path: Path):
    data = json.loads(path.read_text())
    return data


def save_template(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Click positions for slots on the background video frame")
    ap.add_argument("--template", required=True, help="Input template JSON with background_video and slots")
    ap.add_argument("--out", required=True, help="Output template JSON path")
    args = ap.parse_args()

    in_path = Path(args.template)
    out_path = Path(args.out)
    templ = load_template(in_path)
    video = templ.get("background_video")
    slots = templ.get("slots", [])
    if not video:
        raise SystemExit("Template must have background_video to calibrate positions")
    if not slots:
        raise SystemExit("Template must define slots to calibrate")

    cap = cv2.VideoCapture(video)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"Cannot open/read video: {video}")

    h, w = frame.shape[:2]
    disp = frame.copy()
    points = []
    idx = 0

    def on_mouse(event, x, y, flags, param):
        nonlocal idx
        if event == cv2.EVENT_LBUTTONDOWN and idx < len(slots):
            points.append((x, y))
            cv2.circle(disp, (x, y), 6, (0, 0, 255), -1)
            cv2.putText(disp, slots[idx].get("name", f"s{idx}"), (x+8, y-8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1, cv2.LINE_AA)
            idx += 1

    cv2.namedWindow("calibrate", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("calibrate", min(1280, w), min(720, h))
    cv2.setMouseCallback("calibrate", on_mouse)

    while True:
        cv2.imshow("calibrate", disp)
        key = cv2.waitKey(10) & 0xFF
        if idx >= len(slots):
            break
        if key == 27:  # ESC to abort
            cv2.destroyAllWindows()
            raise SystemExit("Aborted")

    cv2.destroyAllWindows()

    if len(points) != len(slots):
        raise SystemExit("Not enough points selected")

    # Write positions back into template
    for i, s in enumerate(templ["slots"]):
        s["position"] = [int(points[i][0]), int(points[i][1])]

    save_template(out_path, templ)
    print(out_path)


if __name__ == "__main__":
    main()

