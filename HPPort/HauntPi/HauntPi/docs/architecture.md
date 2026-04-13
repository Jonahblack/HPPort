# Architecture

```
camera → detection.motion (MOG2 score) + detection.hailo_person (YOLO "person" gate)
      → capture burst → faces.detect_res10 (boxes) → faces.landmarks (optional) → faces.align + faces.cutout
      → [Project A] products.jibjab_export + products.jibjab_compose → video
      → [Project B] products.scream_synth → video
```

- Hailo is used to confirm **person** presence (`label == "person"`, configurable confidence).
- Face detection uses OpenCV Res10 DNN (Caffe) — small/fast on Pi.
- Background removal uses `rembg` on the face crop only.
- Landmarks (if available via MediaPipe) improve alignment; pipeline still works without them.
