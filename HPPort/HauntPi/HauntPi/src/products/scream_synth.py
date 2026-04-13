import numpy as np, cv2, math, random

def _ease_in_out(t):  # 0..1
    return 0.5*(1-math.cos(math.pi*t))

def _shake_offsets(frame_idx, max_px):
    random.seed(frame_idx*1337)
    return random.randint(-max_px, max_px), random.randint(-max_px, max_px)

def synthesize_scream(face_aligned_bgr, fps=30, duration_sec=3, jaw_open_pct=0.18, shake_px=6, flicker=True):
    H, W = face_aligned_bgr.shape[:2]
    frames = int(fps*duration_sec)
    out_frames = []
    base = face_aligned_bgr.copy()

    # estimate mouth line ~ 60% height (works with our simple_align output); can be refined if landmarks available
    mouth_y = int(0.60*H)
    lower_mask = np.zeros((H, W), dtype=np.uint8)
    lower_mask[mouth_y:H, :] = 255

    for i in range(frames):
        t = i / (frames-1 + 1e-6)
        open_amt = _ease_in_out(t) * jaw_open_pct  # 0..jaw_open_pct of height
        shift = int(open_amt * H)

        # separate lower face and translate down with scaling (simulating jaw open)
        lower = base.copy()
        lower[:mouth_y, :] = 0
        M = np.float32([[1,0,0],[0,1,shift]])
        lowered = cv2.warpAffine(lower, M, (W,H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

        # create mouth cavity: black ellipse between mouth_y..mouth_y+shift
        mouth = base.copy()
        mouth[:] = 0
        cy = mouth_y + shift//2; ry = max(5, shift//2); rx = max(8, int(0.18*W))
        cv2.ellipse(mouth, (W//2, cy), (rx, ry), 0, 0, 360, (0,0,0), -1)

        # combine: upper face from base, lower from lowered, add mouth cavity
        frame = base.copy()
        mask = lower_mask > 0
        frame[mask] = lowered[mask]
        # carve mouth cavity
        cavity = mouth.sum(axis=2) > 0
        frame[cavity] = mouth[cavity]

        # tint & flicker
        if flicker and (i % 6 == 0):
            frame = cv2.convertScaleAbs(frame, alpha=1.1, beta=15)

        # subtle red tint as scream grows
        tint = int(40 * _ease_in_out(t))
        frame = cv2.add(frame, (0,0,tint,))

        # shake
        dx, dy = _shake_offsets(i, shake_px)
        M2 = np.float32([[1,0,dx],[0,1,dy]])
        frame = cv2.warpAffine(frame, M2, (W,H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

        # slight vignette
        y, x = np.ogrid[0:H, 0:W]
        cx, cy = W/2, H/2
        vg = ((x-cx)**2 + (y-cy)**2) / (max(W,H)**2)
        vignette = 1 - 0.35*vg
        frame = (frame * vignette[...,None]).astype(np.uint8)

        out_frames.append(frame)

    return out_frames
