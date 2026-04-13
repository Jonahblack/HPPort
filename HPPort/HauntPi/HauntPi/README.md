# HauntPi — Raspberry Pi 5 + Hailo Haunted House Video System

Two apps sharing a common core:

1) **JibJab Maker (2 faces)** — Detects people, captures head crops, removes background, and composites them into a Halloween template video (skeletons/zombies/etc.).  
2) **Screamer Maker (1 face)** — Detects a person, captures face, and synthesizes a short frightening "scream" video from a single image (lightweight; no heavy GAN needed).

**Hardware:** Raspberry Pi 5, Hailo AI Hat, Raspberry Pi Camera Module.  
**Software:** OpenCV + rembg (+ optional MediaPipe), Hailo SDK runtime.

> Put your Hailo `.hef` in `models/` and the OpenCV Res10 files (`deploy.prototxt`, `res10_300x300_ssd_iter_140000.caffemodel`).

## Quick Start

```bash
pip install -r requirements.txt
# Place models:
# models/deploy.prototxt
# models/res10_300x300_ssd_iter_140000.caffemodel
# models/yolov5m.hef

# 1) Run JibJab capture → auto-compose
python -m src.apps.jibjab_capture_and_make --hef models/yolov5m.hef

# 2) Run Screamer capture → auto-synthesize
python -m src.apps.screamer_capture_and_make --hef models/yolov5m.hef
```

Outputs are written under `runs/<timestamp>/`.

- JibJab: `jibjab/face_XX.png`, `manifest.json`, and the composed `jibjab.mp4`.  
- Screamer: `screamer/face_256.png`, `screamer.mp4`.

See **docs/** for guides and template format.

## Use Video as Background

The sample JibJab template now uses `assets/MicrosoftTeams-video.mp4` as its background. To quickly test without a camera or Hailo:

```bash
# 1) Create a simple face bundle from one or two images
python scripts/make_bundle_from_images.py --images path/to/face1.png [path/to/face2.png] --out runs/demo_bundle

# 2) Compose onto the Teams video background (uses absolute slot positions if present)
python scripts/compose_jibjab.py --template assets/templates/sample/template.json --bundles runs/demo_bundle --out runs/jibjab_teams.mp4
```

Notes:
- If input images lack alpha, they are treated as fully opaque; landmarks are optional and omitted in this quick path.
- Slots, sizing, and offsets come from `assets/templates/sample/template.json` and can be tweaked for your video.

## Four Witches (4 faces)

- Template with 4 slots: `assets/templates/witches/template.json` (points to the Teams video).
- Update capture to collect up to 4 faces (`settings/jibjab.json` already set).
- To calibrate exact positions for your video, click the slot locations on the first video frame:

```bash
python scripts/calibrate_slots_from_video.py --template assets/templates/witches/template.json --out assets/templates/witches/template.calibrated.json

# Then compose using the calibrated template
python scripts/compose_jibjab.py --template assets/templates/witches/template.calibrated.json --bundles runs/demo_bundle --out runs/jibjab_witches.mp4
```

### Auto calibration via color markers (no clicking)

If your background shows tan/yellow circular face markers (like the witches), auto-detect their centers and write positions into a new template:

```bash
python scripts/auto_calibrate_slots_from_markers.py \
  --template assets/templates/witches/template.json \
  --out assets/templates/witches/template.auto.json \
  --expected 4 --anchor center --debug-dir runs/auto_calib_debug

# Then compose using the auto-calibrated template
python scripts/compose_jibjab.py --template assets/templates/witches/template.auto.json --bundles runs/demo_bundle --out runs/jibjab_witches.mp4
```

Notes:
- Use `--anchor mouth_center` to nudge positions slightly down from circle center if you want the face's mouth to land on the marker center.
- Debug images (`mask.png`, `overlay.png`) show what was detected; adjust HSV ranges in the script if needed.

### Per-frame marker tracking (faces follow motion)

Enable the built-in tracker to follow the tan/yellow circles each frame and place faces accordingly with smoothing and dropout fallback. The witches template already enables this:

```json
{
  "marker_tracking": {
    "enabled": true,
    "expected": 4,
    "smooth_alpha": 0.85,
    "dropout_max": 10
  }
}
```

Compose using the witches template and your bundle; faces will follow the markers through the video automatically:

```bash
python scripts/compose_jibjab.py --template assets/templates/witches/template.json --bundles runs/demo_bundle --out runs/jibjab_witches_tracked.mp4
```

Robustness:
- Exponential smoothing prevents jitter; `dropout_max` keeps last-known-good positions during brief detection misses.
- If tracking is unavailable for a frame, the composer falls back to static `position` values.
