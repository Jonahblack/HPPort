# JibJab Maker

1. Wait for motion + Hailo person gate.
2. Capture a short burst and pick the middle frame.
3. Detect faces (limit to 2), alpha-cutout each face, collect minimal landmarks.
4. Compose into a template video (or static background) per `assets/templates/.../template.json`.

`template.json` (simplified):

```json
{
  "name": "sample",
  "background_video": null,     // or "path/to/video.mp4"
  "fps": 30,
  "resolution": [1280, 720],    // required if no background_video
  "duration_sec": 5,
  "slots": [
    {"name":"slot0","anchor":"mouth_center","size":[220,260],"offset":[-120,-40],"rotation_from":"eyes"},
    {"name":"slot1","anchor":"mouth_center","size":[220,260],"offset":[120,-40],"rotation_from":"eyes"}
  ]
}

Positioning slots:
- Add optional `"position": [x, y]` per slot to place faces at absolute positions in the background video frame. The coordinates indicate where the chosen `anchor` point lands. If omitted, faces are auto-arranged horizontally.

Multiple faces:
- You can now pass bundles that contain multiple faces; the composer will use all faces in order and map them to slots in order.

Per-frame marker tracking:
- Optional `marker_tracking` on the template enables color-based detection of tan/yellow circular markers each frame.
- The composer assigns detections to slots by nearest neighbor from prior frame, applies exponential smoothing, and keeps last-known-good for short dropouts.
- When tracking is enabled and succeeds for a frame, slot `position` is ignored in favor of the tracked center (with a small vertical nudge when `anchor == "mouth_center"`). Otherwise, static `position` is used.
```
