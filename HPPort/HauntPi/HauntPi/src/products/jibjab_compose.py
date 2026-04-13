import json, math
from pathlib import Path
import numpy as np, cv2
from .jibjab_template import Template
from .markers import MarkerConfig, MarkerTracker

def load_bundle(bundle_dir: Path):
    man = json.loads((bundle_dir / "manifest.json").read_text())
    faces = []
    for e in man.get("faces", []):
        img = cv2.imread(str(bundle_dir / e["file"]), cv2.IMREAD_UNCHANGED)  # BGRA
        lmk = e.get("landmarks")
        faces.append({"image": img, "landmarks": (np.array(lmk) if lmk is not None else None)})
    return faces

def eye_line_angle(lmk):
    left_eye, right_eye = lmk[0], lmk[1]
    dx, dy = (right_eye[0]-left_eye[0]), (right_eye[1]-left_eye[1])
    return math.degrees(math.atan2(dy, dx))

def alpha_blend(bg_bgr, fg_bgra, x, y):
    h, w = fg_bgra.shape[:2]; H, W = bg_bgr.shape[:2]
    x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1: return bg_bgr
    fg_roi = fg_bgra[y0 - y : y0 - y + (y1 - y0), x0 - x : x0 - x + (x1 - x0)]
    bg_roi = bg_bgr[y0:y1, x0:x1]
    alpha = (fg_roi[:, :, 3:4] / 255.0)
    bg_bgr[y0:y1, x0:x1] = (alpha * fg_roi[:, :, :3] + (1 - alpha) * bg_roi).astype(np.uint8)
    return bg_bgr

def rotate_scale(image_bgra, angle_deg, out_size):
    h, w = image_bgra.shape[:2]
    M = cv2.getRotationMatrix2D((w/2, h/2), angle_deg, 1.0)
    rot = cv2.warpAffine(image_bgra, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT)
    return cv2.resize(rot, tuple(out_size), interpolation=cv2.INTER_AREA)

def compose_video(template_path, bundles, out_path):
    template = Template.load(template_path)
    # Load faces from all bundles (use all, in order)
    faces = []
    for b in bundles:
        arr = load_bundle(Path(b))
        if arr:
            faces.extend(arr)
    if not faces: raise RuntimeError("No faces loaded.")

    # Background
    if template.background_video:
        cap = cv2.VideoCapture(template.background_video)
        if not cap.isOpened(): raise RuntimeError(f"Cannot open background video: {template.background_video}")
        fps = template.fps or cap.get(cv2.CAP_PROP_FPS) or 30
        W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    else:
        assert template.resolution, "Template requires resolution when no background video"
        W, H = template.resolution; fps = template.fps; frames = template.duration_sec * fps; cap = None

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_path, fourcc, fps, (W, H))

    slots = template.slots or []
    if not slots:
        from types import SimpleNamespace
        slots = [SimpleNamespace(name=f"slot{i}", anchor="mouth_center", size=(200,240), offset=(0,0), rotation_from="eyes") for i in range(len(faces))]
    n = min(len(slots), len(faces))
    assigns = [{"slot": slots[i], "face": faces[i], "index": i} for i in range(n)]

    # Optional per-frame marker tracking
    tracker = None
    mt_conf = getattr(template, "marker_tracking", None)
    use_tracking = bool(mt_conf and getattr(mt_conf, 'enabled', False) and cap is not None and n > 0)
    if use_tracking:
        cfg = MarkerConfig(
            expected=getattr(mt_conf, 'expected', None) or n,
            hsv_ranges=getattr(mt_conf, 'hsv_ranges', None),
            min_r_ratio=getattr(mt_conf, 'min_r_ratio', 0.04),
            max_r_ratio=getattr(mt_conf, 'max_r_ratio', 0.20),
            smooth_alpha=getattr(mt_conf, 'smooth_alpha', 0.8),
            dropout_max=getattr(mt_conf, 'dropout_max', 8),
            max_match_dist_ratio=getattr(mt_conf, 'max_match_dist_ratio', 0.15),
            mouth_nudge_ratio=getattr(mt_conf, 'mouth_nudge_ratio', 0.12),
        )
        tracker = {"cfg": cfg, "state": None}

    for f in range(frames):
        if cap:
            ok, frame = cap.read()
            if not ok: break
        else:
            frame = np.zeros((H, W, 3), dtype=np.uint8)
        composed = frame.copy()
        tracked_positions = None
        if use_tracking:
            if tracker["state"] is None:
                tracker["state"] = MarkerTracker(tracker["cfg"], frame.shape)
            tracked_positions = tracker["state"].update(frame)
        for a in assigns:
            slot, face = a["slot"], a["face"]
            img, lmk = face["image"], face["landmarks"]
            angle = 0.0
            if slot.rotation_from and lmk is not None and slot.rotation_from == "eyes":
                try: angle = eye_line_angle(lmk)
                except: angle = 0.0
            fg = rotate_scale(img, angle, slot.size)
            if getattr(slot, "anchor", None) == "center":
                anchor_pt = (slot.size[0]//2, slot.size[1]//2)
            elif lmk is not None:
                idx_map = {"left_eye":0, "right_eye":1, "mouth_center":2, "chin":3}
                idx = idx_map.get(slot.anchor, 2)
                orig_h, orig_w = img.shape[:2]
                sx, sy = slot.size[0]/orig_w, slot.size[1]/orig_h
                pt = lmk[idx]; anchor_pt = (int(pt[0]*sx), int(pt[1]*sy))
            else:
                anchor_pt = (slot.size[0]//2, slot.size[1]//2)
            # place slots: tracking > absolute position > auto layout
            if use_tracking and tracked_positions is not None and len(tracked_positions) >= n and tracked_positions[a["index"]] is not None:
                tx, ty, tr = tracked_positions[a["index"]]
                x_slot, y_slot = int(tx), int(ty)
                if getattr(slot, "anchor", "mouth_center") == "mouth_center":
                    y_slot = int(y_slot + tracker["cfg"].mouth_nudge_ratio * tr)
                x_slot += slot.offset[0]; y_slot += slot.offset[1]
            elif getattr(slot, "position", None) is not None:
                x_slot, y_slot = int(slot.position[0]), int(slot.position[1])
                x_slot += slot.offset[0]; y_slot += slot.offset[1]
            else:
                pad = 40; total_w = n*(slot.size[0]+pad)-pad; x_start = (W-total_w)//2
                x_slot = x_start + a["index"]*(slot.size[0]+pad); y_slot = (H - slot.size[1])//2
                x_slot += slot.offset[0]; y_slot += slot.offset[1]
            x = x_slot - anchor_pt[0]; y = y_slot - anchor_pt[1]
            composed = alpha_blend(composed, fg, x, y)
        out.write(composed)
    out.release()
    if cap: cap.release()
    return out_path
